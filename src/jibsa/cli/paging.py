"""이어 받기 표(`next`). 매물 검색 결과의 `next` 를 같은 명령의 `--next` 로 주면 받은 매물 다음부터 이어 받는다.

`--limit` 을 늘려 다시 부르면 앞에서 받은 매물을 다시 요청하고 다시 출력한다. 표에는 명령과 지역·조건, 소스마다
어디까지 받았는지(`position`)를 담는다. 소스에 따라 찾은 지역도 담아 이어 받을 때 지역을 다시 찾지 않는다 (네이버
요청 제한을 아낀다). 표 안의 위치는 소스 서비스만 읽고, CLI 는 그대로 넘긴다.

표는 상태 폴더(요청 제한 상태와 같은 `state_dir()`)의 `next/<번호>.json` 에 두고 `next` 에는 짧은 번호만 준다.
표를 값에 그대로 담으면 찾은 지역·소스 커서 때문에 500~600자가 되어, 에이전트가 다음 명령에 베껴 쓰는 데 토큰이
들고 베끼다 틀리기 쉽다. 명령과 조건을 표에 담아 두어, 조건이 다른 검색에 주면 어느 옵션이 다른지 알린다.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import typer
from typer._click.globals import get_current_context

from jibsa.cli.output import HintedBadParameter
from jibsa.core.ratelimit import (
    StateDirError,
    state_dir,
)

from typing import (
    Annotated,
    Any,
)


# 이어 받는 동안 바꿔도 되는 옵션 (명령 함수의 인자 이름). 나머지(지역·조건·정렬)가 다르면 다른 검색이다
RESUMABLE_PARAMS: frozenset[str] = frozenset({'next_', 'limit', 'pretty', 'details', 'fields'})
# 표를 남겨 두는 시간. 에이전트는 보통 몇 분 안에 이어 받고, 오래된 소스 커서는 서버가 받지 않을 수 있다
NEXT_TTL_SECONDS: int = 24 * 60 * 60
# 번호 길이 (16진수). 하루 동안 쌓이는 표 수에서는 겹치지 않는다
TOKEN_LENGTH: int = 10
TOKEN_PATTERN: re.Pattern[str] = re.compile(f'[0-9a-f]{{{TOKEN_LENGTH}}}')
RESTART_HINT: str = '--next 를 빼고 같은 명령으로 처음부터 다시 찾으세요'

NextOption = Annotated[
    str | None,
    typer.Option(
        '--next',
        help=(
            '앞 결과의 next 값. 지역·조건을 그대로 두고 주면 받은 매물 다음부터 이어 받는다 (--limit 은 바꿀 수 있다). '
            '같은 컴퓨터에서 하루 동안 쓸 수 있다'
        ),
    ),
]


def _search() -> tuple[str, dict[str, Any]]:
    """지금 명령과 그 지역·조건. 값은 표에 저장했다 읽은 것과 같게(튜플은 목록으로) 맞춰 비교한다."""
    context = get_current_context()
    params = {key: value for key, value in context.params.items() if key not in RESUMABLE_PARAMS}
    return context.command_path, json.loads(json.dumps(params, ensure_ascii=False, default=str))


def _directory() -> Path:
    return state_dir() / 'next'


def _shown(value: Any) -> str:
    """조건이 다르다고 알릴 때 쓰는 값. 주지 않은 옵션·꺼진 플래그는 '없음'."""
    if value is None or value is False or value == []:
        return '없음'
    if value is True:
        return '켬'
    if isinstance(value, list):
        return ','.join(map(str, value))
    return f'{value:g}' if isinstance(value, float) else str(value)


def _differences(saved: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """표의 조건과 지금 조건이 다른 옵션을 명령의 옵션 순서로 알린다 (`--rent-max (앞: 70, 지금: 없음)`)."""
    labels: dict[str, str] = {}
    for param in get_current_context().command.params:
        if param.name is not None:
            # 옵션은 에이전트가 쓰는 긴 이름(--type), 위치 인자(지역 이름)는 도움말에 보이는 이름
            labels[param.name] = max(param.opts, key=len) if param.param_type_name == 'option' else param.human_readable_name
    names = [name for name in labels if name in saved or name in current]
    names += [name for name in dict.fromkeys([*saved, *current]) if name not in labels]
    return [
        f'{labels.get(name, name)} (앞: {_shown(saved.get(name))}, 지금: {_shown(current.get(name))})'
        for name in names
        if saved.get(name) != current.get(name)
    ]


def _prune(directory: Path, now: float) -> None:
    """하루 지난 표와 쓰다 남은 임시 파일을 지운다. 못 지워도(다른 프로세스가 먼저 지움 등) 이어 받기와 상관없다."""
    for path in directory.iterdir():
        try:
            if now - path.stat().st_mtime > NEXT_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def encode_next(position: dict[str, Any] | None) -> str | None:
    """서비스가 준 다음 위치를 표로 저장하고 그 번호를 `next` 로 돌려준다. 더 받을 게 없으면(None) None.

    번호는 표 내용에서 만들어, 같은 검색을 같은 위치까지 다시 받으면 같은 번호가 나온다.

    Raises:
        StateDirError: 상태 폴더에 표를 쓰지 못했을 때.
    """
    if position is None:
        return None
    command, params = _search()
    raw = json.dumps(
        {'command': command, 'params': params, 'position': position},
        ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    )
    token = hashlib.sha256(raw.encode()).hexdigest()[:TOKEN_LENGTH]
    directory = _directory()
    path = directory / f'{token}.json'
    tmp = directory / f'{token}.{os.getpid()}.tmp'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _prune(directory, time.time())
        tmp.write_text(raw, encoding='utf-8')
        tmp.replace(path)
    except OSError as exc:
        raise StateDirError(state_dir(), exc) from exc
    return token


def decode_next(token: str | None) -> dict[str, Any] | None:
    """`--next` 번호의 표를 읽어 서비스가 이어 받을 위치로 돌려준다. 주지 않았으면 None.

    명령의 오류 처리(`handle_errors`) 밖에서 부르므로 사용법 오류로만 끝낸다.

    Raises:
        HintedBadParameter: 번호 꼴이 아니거나, 표가 없거나(하루 지남·다른 컴퓨터) 읽을 수 없거나, 명령·지역·조건이
            표를 받은 검색과 다를 때.
    """
    if token is None:
        return None
    if not TOKEN_PATTERN.fullmatch(token):
        raise HintedBadParameter(f'next 값의 꼴이 아닙니다: {token!r}', '--next', '앞 결과의 next 를 그대로 주세요')
    path = _directory() / f'{token}.json'
    try:
        if time.time() - path.stat().st_mtime > NEXT_TTL_SECONDS:
            raise FileNotFoundError(path)
        record = json.loads(path.read_text(encoding='utf-8'))
        command, params, position = record['command'], record['params'], record['position']
        if not isinstance(params, dict) or not isinstance(position, dict):
            raise TypeError('표 형식이 다릅니다')
    except FileNotFoundError:
        raise HintedBadParameter(
            '이 next 의 이어 받기 표가 없습니다. 받은 지 하루가 지났거나 다른 컴퓨터·상태 폴더(JIBSA_STATE_DIR)에서 받은 값입니다',
            '--next',
            RESTART_HINT,
        ) from None
    except (OSError, ValueError, LookupError, TypeError) as exc:
        raise HintedBadParameter(
            f'이 next 의 이어 받기 표를 읽지 못했습니다 ({type(exc).__name__}: {exc})', '--next', RESTART_HINT,
        ) from None
    current_command, current_params = _search()
    if command != current_command:
        raise HintedBadParameter(
            f'다른 명령의 next 입니다 (받은 명령: {command})', '--next', f'같은 지역·조건으로 {command} 에 주세요',
        )
    differences = _differences(params, current_params)
    if differences:
        raise HintedBadParameter(
            '앞 검색과 지역·조건이 다릅니다: ' + '; '.join(differences),
            '--next',
            'next 를 받은 검색과 지역·조건을 똑같이 주세요 (--limit·--details·--fields 는 바꿀 수 있습니다). '
            '새 조건으로 찾으려면 --next 를 빼세요',
        )
    return position
