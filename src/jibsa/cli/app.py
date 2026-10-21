import inspect
import json
import logging
import re
import sys
import unicodedata
from collections.abc import Sequence
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import typer
from typer._click import (  # Typer 0.27 은 Click 을 내부에 포함한다. 비공개 경로라 Typer 업그레이드 시 확인 필요.
    Command,
    Context,
    HelpFormatter,
)
from typer._click.exceptions import (
    BadParameter,
    ClickException,
    NoArgsIsHelpError,
    NoSuchOption,
    UsageError,
)
from typer.core import (
    TyperCommand,
    TyperGroup,
)

from jibsa.cli import (
    daangn,
    naver,
    zigbang,
)
from jibsa.cli.output import (
    UsageHints,
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
# `jibsa guide <주제>` 로 읽는 사용 문서
GUIDE_TOPICS: dict[str, str] = {
    'common': 'common.md',
    'zigbang': 'zigbang.md',
    'naver': 'naver.md',
    'daangn': 'daangn.md',
}
HEADING_PATTERN: re.Pattern[str] = re.compile(r'^(#{2,4})\s+(.*)$')
BACKTICK_PATTERN: re.Pattern[str] = re.compile(r'`([^`]+)`')
GUIDE_URL: str = 'https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md'
# `git log --oneline` 과 같은 짧은 커밋 해시 길이
SHORT_COMMIT_LENGTH: int = 7
# 터미널이 아닐 때 도움말 폭. 옵션 설명이 줄바꿈 없이 한 줄에 들어가게 넉넉히 잡는다
PLAIN_HELP_WIDTH: int = 1000
# 다른 소스 표현을 옮겨 쓴 사용법 오류에 힌트를 주는 명령 (UsageHints)
USAGE_HINTS: dict[str, UsageHints] = {**zigbang.USAGE_HINTS, **naver.USAGE_HINTS, **daangn.USAGE_HINTS}

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
def guide_command(
    topic: Annotated[
        str | None,
        typer.Argument(help=f"사용 문서: {', '.join(GUIDE_TOPICS)}. 없으면 LLM 가이드")
    ] = None,
    section: Annotated[
        str | None,
        typer.Argument(help="절 제목에 든 글자 (예: 'search listings', 'listing', '출력 읽기'). 주면 그 절만 쓴다")
    ] = None,
    whole: Annotated[
        bool,
        typer.Option('--all', help='소스 문서를 절 목록 대신 통째로 쓴다'),
    ] = False,
) -> None:
    """LLM 에이전트용 사용 가이드를 출력한다 (명령 고르기, 출력 읽기, 에러 대응).

    소스 이름만 주면 그 소스 사용 문서(옵션 표·반환값·주의사항)의 절 목록을, 절 이름까지 주면 그 절만 쓴다.
    소스 문서는 가이드의 3~5배라 통째로 쓰면 셸 출력이 잘려 필요한 절만 읽는다 (통째로는 --all). 설치한 버전과
    내용이 맞다. `--help` 처럼 JSON 이 아닌 마크다운 텍스트를 stdout 에 쓴다. 네트워크 요청은 보내지 않는다.

    예: jibsa guide
        jibsa guide daangn
        jibsa guide daangn 'search listings'
        jibsa guide zigbang listing
    """
    if topic is not None and topic not in GUIDE_TOPICS:
        raise typer.BadParameter(
            f"허용되지 않는 값입니다: '{topic}'. 가능한 값: {', '.join(GUIDE_TOPICS)}", param_hint='TOPIC',
        )
    # 파일이 없는 깨진 설치와 없는 절도 에러 JSON 으로 낸다
    with handle_errors('guide'):
        text = read_guide(GUIDE_TOPICS[topic] if topic else GUIDE_FILE)
        if section:
            text = guide_section(text, section, topic or 'llm')
        elif topic and not whole:
            text = guide_contents(text, topic)
        typer.echo(text, nl=False)


def read_guide(name: str = GUIDE_FILE) -> str:
    """패키지에 들어 있는 문서를, 없으면(편집 가능 설치) 저장소의 `docs/<name>` 을 읽는다.

    Raises:
        JibsaError: 둘 다 없을 때 (`INTERNAL_ERROR`, 설치가 깨짐).
    """
    packaged = files('jibsa').joinpath(name)
    if packaged.is_file():
        return packaged.read_text(encoding='utf-8')
    # src/jibsa/cli/app.py → 저장소 루트
    in_repo = Path(__file__).resolve().parents[3] / 'docs' / name
    if in_repo.is_file():
        return in_repo.read_text(encoding='utf-8')
    # 일반 내부 오류 힌트(다른 소스를 쓰라는 안내)는 여기에 맞지 않는다
    raise JibsaError(
        code='INTERNAL_ERROR',
        message=f'설치된 jibsa 에 문서 파일({name})이 없습니다',
        hint=f'README 의 설치 방법대로 jibsa 를 다시 설치하세요. 같은 내용은 {GUIDE_URL} 에서도 볼 수 있습니다',
    )


def guide_contents(text: str, topic: str) -> str:
    """소스 문서의 제목과 절 목록(`##`·`###`). 절 하나는 `guide_section` 으로 읽는다.

    소스 문서를 통째로 쓰면 3만~4만 자라 셸 출력을 잘라 보여 주는 에이전트는 앞부분만 본다 (2026-10-20 실측: 직방
    3.2만·네이버 2.7만·당근 3.9만 자).
    """
    lines = text.splitlines()
    title = next((line for line in lines if line.startswith('# ')), f'# {topic}')
    entries: list[str] = []
    for line in lines:
        match = HEADING_PATTERN.match(line)
        if match and len(match.group(1)) <= 3:
            entries.append(f"{'  ' * (len(match.group(1)) - 2)}- {match.group(2).strip()}")
    commands = [code for line in lines if (match := HEADING_PATTERN.match(line)) for code in BACKTICK_PATTERN.findall(match.group(2))]
    example = f"jibsa guide {topic} '{commands[0]}'" if commands else f"jibsa guide {topic} '<절 제목 일부>'"
    return (
        f'{title}\n\n'
        f"문서 전체는 {len(text):,}자라 절 목록만 쓴다. 필요한 절만 `jibsa guide {topic} '<절 제목 일부>'` 로 읽는다 "
        f'(예: `{example}`). 통째로는 `jibsa guide {topic} --all`.\n\n'
        + '\n'.join(entries) + '\n'
    )


def guide_section(text: str, query: str, topic: str) -> str:
    """문서에서 제목에 `query` 가 든 절(그 아래 하위 절 포함)만 이어 붙인다. 대소문자·백틱은 가리지 않는다.

    제목의 백틱 안 명령 이름과 똑같은 절이 있으면 그 절만 고른다 (`listing` 이 `search listings room` 까지 고르지 않게).

    Raises:
        JibsaError: 맞는 절이 없을 때 (`NOT_FOUND`, 힌트에 큰 절 제목).
    """
    def plain(value: str) -> str:
        return value.replace('`', '').casefold().strip()

    lines = text.splitlines(keepends=True)
    headings = [
        (index, len(match.group(1)), match.group(2).strip())
        for index, line in enumerate(lines)
        if (match := HEADING_PATTERN.match(line.rstrip('\n')))
    ]
    exact = {index for index, _, title in headings if plain(query) in (plain(code) for code in BACKTICK_PATTERN.findall(title))}
    picked: list[str] = []
    covered_until = -1
    for position, (index, level, title) in enumerate(headings):
        matched = index in exact if exact else plain(query) in plain(title)
        if index < covered_until or not matched:
            continue
        end = next((later for later, later_level, _ in headings[position + 1:] if later_level <= level), len(lines))
        picked.append(''.join(lines[index:end]).rstrip('\n') + '\n')
        covered_until = end
    if not picked:
        titles = [title.replace('`', '') for _, level, title in headings if level == 2]
        raise JibsaError(
            code='NOT_FOUND',
            message=f"{topic} 문서에서 찾지 못한 절 제목: '{query}'",
            hint=f"절 제목: {' / '.join(titles)}",
        )
    return '\n'.join(picked)


def version_text() -> str:
    """`jibsa --version` 이 쓰는 한 줄 (`jibsa 0.2.0 (커밋 a1b2c3d)`).

    버전은 pyproject.toml 에만 적고 설치 메타데이터에서 읽는다. `main` 을 git 주소로 설치하면 릴리스 사이의 커밋도
    버전이 같으므로, pip·uv 가 남긴 `direct_url.json`(PEP 610)의 커밋을 붙인다. PyPI 설치는 버전만 쓴다. 편집 가능
    설치는 저장소 코드를 그대로 따라가 버전만으로는 어느 코드인지 알 수 없어 `(개발 설치)` 를 붙인다.
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


class PlainHelpFormatter(HelpFormatter):
    """터미널이 아닐 때 쓰는 Click 도움말 형식. 폭을 넓게 잡고 설명은 docstring 의 줄바꿈대로 쓴다.

    Click 기본 형식은 설명 문단의 줄을 이어 붙여 예시 명령 여러 개가 한 줄로 붙는다. Rich 도움말(터미널)처럼
    줄바꿈을 그대로 둔다.
    """

    def __init__(self, indent_increment: int = 2, width: int | None = None, max_width: int | None = None) -> None:
        super().__init__(indent_increment, width=PLAIN_HELP_WIDTH, max_width=PLAIN_HELP_WIDTH)

    def write_text(self, text: str) -> None:
        indent = ' ' * self.current_indent
        for line in text.splitlines():
            self.write(f'{indent}{line}\n' if line.strip() else '\n')


class PlainHelpContext(Context):
    formatter_class = PlainHelpFormatter


def use_plain_help(command: Command) -> None:
    """도움말을 Rich 표 대신 Click 줄글로 쓰게 명령 트리 전체를 바꾼다. stdout 이 터미널이 아닐 때 쓴다.

    Rich 는 터미널이 아니면 폭을 80칸으로 잡아 옵션 설명을 '…' 로 자르고, 테두리·줄 맞춤 공백이 출력의 대부분이다
    (2026-10-15 실측: `zigbang search listings room --help` 9.7KB 중 공백 74%, 잘린 곳 8). 셸로 부르는 LLM 은 늘
    이 경우다. 명령 목록의 설명은 Click 기본이 첫 문장에서 자르므로 Rich 처럼 첫 문단 전체를 쓴다.
    """
    if isinstance(command, TyperCommand | TyperGroup):
        command.rich_markup_mode = None
    command.context_class = PlainHelpContext
    if command.short_help is None and command.help:
        first_paragraph = inspect.cleandoc(command.help).partition('\f')[0].split('\n\n')[0]
        command.short_help = ' '.join(first_paragraph.split())
    if isinstance(command, TyperGroup):
        for subcommand in command.commands.values():
            use_plain_help(subcommand)


def run(argv: Sequence[str] | None = None) -> int:
    """CLI 를 실행하고 exit code 를 돌려준다.

    Typer 를 standalone 모드 없이 돌려 사용법 오류도 `{"error": {...}}` JSON 으로
    stderr 에 쓴다 (exit 2). 그래서 stdout 은 결과 JSON, stderr 는 에러 JSON 이라는
    규칙에 예외가 없다. 인자 없이 실행하면 `--help` 처럼 도움말을 stdout 에 쓴다.
    stdout 이 터미널이 아니면 도움말을 Rich 표 대신 줄글로 쓴다 (`use_plain_help`).
    Ctrl+C 로 끊기면 INTERRUPTED 에러 JSON 을 쓰고 130 으로 끝난다.
    """
    # macOS 에서 복사한 한글은 자모가 나뉜 NFD 로 올 수 있다. 직방·당근 검색은 NFD 를 다른 글자로 봐 0건을 준다
    # (2026-10-11 실측: NFD '역삼동' 이 직방·당근 REGION_NOT_FOUND, 네이버만 정상). 화면에는 같아 보여 원인을 알 수 없다
    args = [unicodedata.normalize('NFC', arg) for arg in (sys.argv[1:] if argv is None else argv)]
    cli = typer.main.get_command(app)
    if not sys.stdout.isatty():
        use_plain_help(cli)
    try:
        result = cli.main(args=args, prog_name='jibsa', standalone_mode=False)
    except NoArgsIsHelpError as exc:
        typer.echo(exc.format_message())
        return 0
    except UsageError as exc:
        command = exc.ctx.command_path if exc.ctx is not None else 'jibsa'
        emit_error(
            'INVALID_ARGUMENT',
            exc.format_message(),
            getattr(exc, 'hint', None)
            or foreign_usage_hint(exc, command, args, cli)
            or f"'{command} --help' 로 사용법을 확인하세요",
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


def foreign_usage_hint(exc: UsageError, command: str, args: Sequence[str], cli: Command) -> str | None:
    """없는 옵션이나 숫자로 못 바꾸는 값에, 이 명령에서 주는 법을 찾는다 (`UsageHints`). 목록 옵션의 틀린 값은 `split_csv` 가 본다.

    다른 소스 명령을 옮겨 쓴 오류가 대부분이다 (직방에 네이버 `--facility`, 직방 `--bathroom` 에 네이버 값 `1개`).
    표에 없는 옵션이면 그 옵션이 있는 다른 소스의 매물 검색 명령을 알려, 이 명령에는 그 조건이 없다는 것을 알게 한다.
    """
    hints = USAGE_HINTS.get(command)
    if hints is None:
        return None
    if isinstance(exc, NoSuchOption):
        names = [exc.option_name]
    elif isinstance(exc, BadParameter) and exc.param is not None:
        names = list(exc.param.opts)
    else:
        return None
    long_name = next((name for name in names if name.startswith('--')), names[0])
    hint = hints.hint(long_name, _option_value(args, names))
    if hint or not isinstance(exc, NoSuchOption):
        return hint
    elsewhere = [path for path in USAGE_HINTS if path != command and _has_option(cli, path, long_name)]
    # 하위 명령과 같은 옵션을 받는 그룹(직방 search listings --complex)은 하위 명령만 알린다
    elsewhere = [path for path in elsewhere if not any(other.startswith(f'{path} ') for other in elsewhere)]
    if not elsewhere:
        return None
    return f"{long_name} 옵션은 {', '.join(elsewhere)} 에 있습니다. 이 명령의 옵션은 '{command} --help' 로 확인하세요"


def _option_value(args: Sequence[str], names: Sequence[str]) -> str | None:
    """`args` 에서 옵션(`names` 중 하나)에 준 마지막 값. `--옵션=값` 과 `--옵션 값` 을 모두 본다. 값이 없으면 None."""
    value = None
    for index, arg in enumerate(args):
        name, equals, inline = arg.partition('=')
        if name not in names:
            continue
        if equals:
            value = inline
        elif index + 1 < len(args) and not args[index + 1].startswith('-'):
            value = args[index + 1]
    return value


def _has_option(cli: Command, path: str, option: str) -> bool:
    """`path`(`jibsa naver search listings`) 명령에 `option` 이 있는지."""
    command: Command | None = cli
    for name in path.split()[1:]:
        command = command.commands.get(name) if isinstance(command, TyperGroup) else None
    return command is not None and any(option in param.opts for param in command.params)


def main() -> None:
    sys.exit(run())
