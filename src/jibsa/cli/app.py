import json
import logging
import sys
import unicodedata
from collections.abc import Sequence
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import typer
from typer._click.exceptions import (  # Typer 0.27 은 Click 을 내부에 포함한다. 비공개 경로라 Typer 업그레이드 시 확인 필요.
    ClickException,
    NoArgsIsHelpError,
    UsageError,
)

from jibsa.cli import (
    daangn,
    naver,
    zigbang,
)
from jibsa.cli.output import (
    emit,
    emit_error,
    handle_errors,
    split_csv,
)
from jibsa.core.errors import JibsaError
from jibsa.core.ratelimit import state_dir
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.zigbang.api.client import ZigbangClient

from typing import Annotated


# SIGINT 로 끝난 프로세스의 관례적인 exit code (128 + 2). Typer 도 KeyboardInterrupt 를 이 값으로 바꾼다.
INTERRUPTED_EXIT_CODE: int = 130
INTERRUPTED_HINT: str = '호출한 쪽이 실행을 끊었습니다. 결과가 필요하면 같은 명령을 다시 실행하세요'
# 설치본에는 pyproject.toml 의 force-include 로 패키지 안에, 편집 가능 설치에는 저장소 docs/ 에만 있다
GUIDE_FILE: str = 'llm.md'
GUIDE_URL: str = 'https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md'
# `git log --oneline` 과 같은 짧은 커밋 해시 길이
SHORT_COMMIT_LENGTH: int = 7

app = typer.Typer(
    name='jibsa',
    help=(
        '부동산 매물 조회 CLI (직방·네이버·당근). 결과는 JSON 으로 stdout 에, 에러는 '
        '{"error": {...}} JSON 으로 stderr 에 쓴다. 금액은 모두 만원 단위. '
        'LLM 에이전트는 처음 쓰기 전에 `jibsa guide` 를 읽는다.'
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(zigbang.app, name='zigbang')
app.add_typer(naver.app, name='naver')
app.add_typer(daangn.app, name='daangn')


def show_version(value: bool) -> None:
    """`--version` 이 주어지면 버전 한 줄을 stdout 에 쓰고 명령을 실행하지 않고 끝낸다."""
    if not value:
        return
    # 메타데이터가 없는 깨진 설치도 에러 JSON 으로 낸다
    with handle_errors('version'):
        typer.echo(version_text())
    raise typer.Exit()


@app.callback()
def configure_logging(
    verbose: Annotated[bool, typer.Option('--verbose', '-v', help='재시도 등 진행 로그를 stderr 에 출력')] = False,
    version: Annotated[
        bool,
        typer.Option('--version', callback=show_version, is_eager=True, help='설치된 jibsa 버전을 출력하고 끝낸다'),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.ERROR,
        format='%(levelname)s %(name)s: %(message)s',
    )


@app.command('limits')
def limits_command(
    reset: Annotated[
        list[str] | None,
        typer.Option('--reset', help='쿨다운·요청 기록을 지울 소스 (zigbang, naver, daangn). 반복하거나 쉼표로 구분')
    ] = None,
    pretty: Annotated[
        bool | None,
        typer.Option('--pretty/--compact', help='JSON 들여쓰기'),
    ] = None,
) -> None:
    """소스별 요청 제한 상태 (쿨다운 남은 시간, 최근 1분 요청 수, 정책).

    상태는 모든 jibsa 프로세스가 공유한다 (JIBSA_STATE_DIR, 기본 ~/.cache/jibsa).
    """
    clients = {
        'zigbang': ZigbangClient,
        'naver': NaverClient,
        'daangn': DaangnClient,
    }
    sources = split_csv(reset, tuple(clients), '--reset')
    # 상태 파일을 읽고 쓰므로 권한·디스크 오류도 에러 JSON 으로 낸다
    with handle_errors('limits'):
        for source in sources:
            clients[source]().rate_limiter.reset()
        emit(
            {
                'state_dir': str(state_dir()),
                'sources': [client().rate_limiter.status() for client in clients.values()],
            },
            pretty,
        )


@app.command('guide')
def guide_command() -> None:
    """LLM 에이전트용 사용 가이드를 출력한다 (명령 고르기, 출력 읽기, 에러 대응).

    `--help` 처럼 JSON 이 아닌 마크다운 텍스트를 stdout 에 쓴다. 네트워크 요청은 보내지 않는다.
    """
    # 파일이 없는 깨진 설치도 에러 JSON 으로 낸다
    with handle_errors('guide'):
        typer.echo(read_guide(), nl=False)


def read_guide() -> str:
    """패키지에 들어 있는 가이드를, 없으면(편집 가능 설치) 저장소의 `docs/llm.md` 를 읽는다.

    Raises:
        JibsaError: 둘 다 없을 때 (`INTERNAL_ERROR`, 설치가 깨짐).
    """
    packaged = files('jibsa').joinpath(GUIDE_FILE)
    if packaged.is_file():
        return packaged.read_text(encoding='utf-8')
    # src/jibsa/cli/app.py → 저장소 루트
    in_repo = Path(__file__).resolve().parents[3] / 'docs' / GUIDE_FILE
    if in_repo.is_file():
        return in_repo.read_text(encoding='utf-8')
    # 일반 내부 오류 힌트(다른 소스를 쓰라는 안내)는 여기에 맞지 않는다
    raise JibsaError(
        code='INTERNAL_ERROR',
        message=f'설치된 jibsa 에 LLM 가이드 파일({GUIDE_FILE})이 없습니다',
        hint=f'README 의 설치 방법대로 jibsa 를 다시 설치하세요. 같은 내용은 {GUIDE_URL} 에서도 볼 수 있습니다',
    )


def version_text() -> str:
    """`jibsa --version` 이 쓰는 한 줄 (`jibsa 0.2.0 (커밋 a1b2c3d)`).

    버전은 pyproject.toml 에만 적고 설치 메타데이터에서 읽는다. 사용자는 `main` 을 git 주소로 설치해 릴리스 사이의
    커밋도 버전이 같으므로, pip·uv 가 남긴 `direct_url.json`(PEP 610)의 커밋을 붙인다. 편집 가능 설치는 저장소
    코드를 그대로 따라가 버전만으로는 어느 코드인지 알 수 없어 `(개발 설치)` 를 붙인다.
    """
    dist = distribution('jibsa')
    text = f'jibsa {dist.version}'
    origin = json.loads(dist.read_text('direct_url.json') or '{}')
    commit = origin.get('vcs_info', {}).get('commit_id')
    if commit:
        return f'{text} (커밋 {commit[:SHORT_COMMIT_LENGTH]})'
    if origin.get('dir_info', {}).get('editable'):
        return f'{text} (개발 설치)'
    return text


def run(argv: Sequence[str] | None = None) -> int:
    """CLI 를 실행하고 exit code 를 돌려준다.

    Typer 를 standalone 모드 없이 돌려 사용법 오류도 `{"error": {...}}` JSON 으로
    stderr 에 쓴다 (exit 2). 그래서 stdout 은 결과 JSON, stderr 는 에러 JSON 이라는
    규칙에 예외가 없다. 인자 없이 실행하면 `--help` 처럼 도움말을 stdout 에 쓴다.
    Ctrl+C 로 끊기면 INTERRUPTED 에러 JSON 을 쓰고 130 으로 끝난다.
    """
    # macOS 에서 복사한 한글은 자모가 나뉜 NFD 로 올 수 있다. 직방·당근 검색은 NFD 를 다른 글자로 봐 0건을 준다
    # (2026-10-11 실측: NFD '역삼동' 이 직방·당근 REGION_NOT_FOUND, 네이버만 정상). 화면에는 같아 보여 원인을 알 수 없다
    args = [unicodedata.normalize('NFC', arg) for arg in (sys.argv[1:] if argv is None else argv)]
    try:
        result = app(args=args, prog_name='jibsa', standalone_mode=False)
    except NoArgsIsHelpError as exc:
        typer.echo(exc.format_message())
        return 0
    except UsageError as exc:
        command = exc.ctx.command_path if exc.ctx is not None else 'jibsa'
        emit_error(
            'INVALID_ARGUMENT',
            exc.format_message(),
            getattr(exc, 'hint', None) or f"'{command} --help' 로 사용법을 확인하세요",
            command=command,
        )
        return exc.exit_code
    except ClickException as exc:
        emit_error('CLI_ERROR', exc.format_message())
        return exc.exit_code
    except typer.Abort:
        # 프롬프트 입력 중 EOF. jibsa 에는 프롬프트가 없지만 중단은 모두 같은 코드로 알린다
        emit_error('INTERRUPTED', '중단되었습니다', INTERRUPTED_HINT)
        return 1
    if result == INTERRUPTED_EXIT_CODE:
        # Typer 는 KeyboardInterrupt 를 아무것도 쓰지 않고 Exit(130) 으로 바꿔 돌려준다.
        # handle_errors 도 BaseException 인 KeyboardInterrupt 는 잡지 않으므로 여기서 에러 JSON 을 쓴다
        emit_error('INTERRUPTED', '인터럽트(Ctrl+C, SIGINT)로 중단되었습니다', INTERRUPTED_HINT)
        return result
    return result if isinstance(result, int) else 0


def main() -> None:
    sys.exit(run())
