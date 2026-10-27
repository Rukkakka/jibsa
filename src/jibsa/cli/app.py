import inspect
import json
import logging
import re
import shlex
import sys
import unicodedata
from collections.abc import Sequence
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import typer
from typer._click import (  # Typer 0.26 부터 Click 을 내부에 포함한다. 비공개 경로라 Typer 업그레이드 시 확인 필요.
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
    dabang,
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
from jibsa.providers.dabang.api.client import DabangClient
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
    'dabang': 'dabang.md',
}
HEADING_PATTERN: re.Pattern[str] = re.compile(r'^(#{2,4})\s+(.*)$')
BACKTICK_PATTERN: re.Pattern[str] = re.compile(r'`([^`]+)`')
# 안내 표가 없는 명령에 없는 옵션을 줬을 때 이 명령의 옵션을 알리는 소스 (`foreign_usage_hint`)
SOURCE_COMMANDS: frozenset[str] = frozenset({'zigbang', 'naver', 'daangn', 'dabang'})
# 하위 명령 자리에 온 지역 이름을 알아본다 (`subcommand_hint`)
HANGUL_PATTERN: re.Pattern[str] = re.compile(r'[가-힣]')
GUIDE_URL: str = 'https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md'
# `git log --oneline` 과 같은 짧은 커밋 해시 길이
SHORT_COMMIT_LENGTH: int = 7
# 터미널이 아닐 때 도움말 폭. 옵션 설명이 줄바꿈 없이 한 줄에 들어가게 넉넉히 잡는다
PLAIN_HELP_WIDTH: int = 1000
# 다른 소스 표현을 옮겨 쓴 사용법 오류에 힌트를 주는 명령 (UsageHints)
USAGE_HINTS: dict[str, UsageHints] = {
    **zigbang.USAGE_HINTS, **naver.USAGE_HINTS, **daangn.USAGE_HINTS, **dabang.USAGE_HINTS,
}

app = typer.Typer(
    name='jibsa',
    help=(
        '부동산 매물 조회 CLI (직방·네이버·당근·다방). 결과는 JSON 으로 stdout 에, 에러는 '
        '{"error": {...}} JSON 으로 stderr 에 쓴다. 금액은 모두 만원 단위. '
        'LLM 에이전트는 처음 쓰기 전에 `jibsa guide` 를 읽는다.'
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(zigbang.app, name='zigbang')
app.add_typer(naver.app, name='naver')
app.add_typer(daangn.app, name='daangn')
app.add_typer(dabang.app, name='dabang')


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
        typer.Option('--reset', help='쿨다운·요청 기록을 지울 소스 (zigbang, naver, daangn, dabang). 반복하거나 쉼표로 구분')
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
        'dabang': DabangClient,
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
    # 따옴표 없이 준 여러 단어(`jibsa guide daangn search listings`)도 한 절 이름으로 잇는다. 하나만 받으면 Typer 가
    # 'unexpected extra argument' 로 막았다 (2026-10-23 실측)
    section: Annotated[
        list[str] | None,
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
        query = ' '.join(section or []).strip()
        if query:
            text = guide_section(text, query, topic or 'llm')
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
        command = exc.ctx.command_path if exc.ctx is not None else _command_path_of(cli, args)
        emit_error(
            'INVALID_ARGUMENT',
            exc.format_message(),
            getattr(exc, 'hint', None)
            or misplaced_option_hint(exc, command, args, cli)
            or foreign_usage_hint(exc, command, args, cli)
            or subcommand_hint(exc)
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


def _command_path_of(cli: Command, args: Sequence[str]) -> str:
    """문맥(ctx) 없이 온 사용법 오류의 명령 경로. 인자에서 하위 명령 이름을 따라 내려간다 (옵션은 건너뛴다).

    Typer 에 든 Click 파서는 값이 빠진 옵션(`... --sort` 로 끝남)을 ctx 없이 던져, 에러가 `jibsa` 명령으로 `'jibsa --help'`
    를 안내했다 (2026-10-24 에이전트 검증: `naver search listings --complex … --sort`).
    """
    path, command = ['jibsa'], cli
    for arg in args:
        if isinstance(command, TyperGroup) and arg in command.commands:
            path.append(arg)
            command = command.commands[arg]
        elif not arg.startswith('-'):
            break
    return ' '.join(path)


def misplaced_option_hint(exc: UsageError, command: str, args: Sequence[str], cli: Command) -> str | None:
    """하위 명령의 옵션을 그 명령 이름보다 앞(`jibsa --compact daangn school …`)에 준 호출에, 명령 끝에 주라고 알린다.

    가이드의 '--compact 를 붙인다' 를 읽은 에이전트가 맨 앞에 붙여 'jibsa --help' 만 안내받았다 (2026-10-24 에이전트 검증).
    값을 받는 옵션이면 그 값도 빼고 명령 경로를 찾는다.
    """
    if not isinstance(exc, NoSuchOption):
        return None
    option = exc.option_name
    index = args.index(option) if option in args else -1
    for skip in (1, 2):
        rest = [*args[:index], *args[index + skip:]] if index >= 0 else list(args)
        path = _command_path_of(cli, rest)
        target = _find_command(cli, path)
        if path != command and target is not None and any(
            option in param.opts or option in param.secondary_opts for param in target.params
        ):
            # 옵션 이름 뒤에 조사를 붙이지 않는다 (code-style 1절)
            return f"{option} 옵션은 '{path}' 뒤에 준다 (예: {path} … {option}). '{path} --help' 로 사용법을 확인하세요"
    return None


def foreign_usage_hint(exc: UsageError, command: str, args: Sequence[str], cli: Command) -> str | None:
    """없는 옵션이나 숫자로 못 바꾸는 값에, 이 명령에서 주는 법을 찾는다 (`UsageHints`). 목록 옵션의 틀린 값은 `split_csv` 가 본다.

    다른 소스 명령을 옮겨 쓴 오류가 대부분이다 (직방에 네이버 `--facility`, 직방 `--bathroom` 에 네이버 값 `1개`).
    표가 있는 매물 검색 명령에서 표에 없는 옵션이면 그 옵션이 있는 다른 매물 검색 명령을 알려, 이 명령에는 그 조건이 없다는
    것을 알게 한다. 표가 있는 명령까지 명령 트리 전체로 넓히면 단기임대 `stay` 처럼 다른 상품의 명령을 알려 되돌렸다
    (2026-10-24 리뷰: `room --parking` 이 `stay` 를 알렸다).

    표가 없는 소스 명령(상세·단지·실거래 등)은 이 명령의 옵션을 알린다 (2026-10-23 에이전트 검증: 상세 `daangn listing` 에
    검색의 `--fields` 를 붙여 5번 틀리고 --help 로 이 명령의 옵션을 본 뒤에야 뺐다). 그 옵션이 있는 다른 명령을 알리면
    같은 일을 다른 이름으로 하는 옵션을 가렸다 (2026-10-24 실측: `naver real-price --limit` 에 search 명령 3개를 알렸지만
    이 명령에서 거래 수를 정하는 옵션은 `--pages`·`--period` 다).
    """
    hints = USAGE_HINTS.get(command)
    if isinstance(exc, NoSuchOption):
        names = [exc.option_name]
    elif isinstance(exc, BadParameter) and exc.param is not None and hints is not None:
        names = list(exc.param.opts)
    else:
        return None
    long_name = next((name for name in names if name.startswith('--')), names[0])
    if hints is None:
        return _own_options_hint(cli, command, long_name)
    hint = hints.hint(long_name, _option_value(args, names))
    if hint or not isinstance(exc, NoSuchOption):
        return hint
    elsewhere = [path for path in USAGE_HINTS if path != command and _has_option(cli, path, long_name)]
    # 하위 명령과 같은 옵션을 받는 그룹(직방 search listings --complex)은 하위 명령만 알린다
    elsewhere = [path for path in elsewhere if not any(other.startswith(f'{path} ') for other in elsewhere)]
    if not elsewhere:
        return None
    return f"{long_name} 옵션은 {', '.join(elsewhere)} 에 있습니다. '{command} --help' 로 사용법을 확인하세요"


def _own_options_hint(cli: Command, command: str, option: str) -> str | None:
    """안내 표가 없는 소스 명령에 없는 옵션을 줬을 때, 이 명령의 옵션을 알린다. 소스 밖 명령(guide·limits)과 루트는 None."""
    source = command.split()[1:2]
    found = _find_command(cli, command)
    if not source or source[0] not in SOURCE_COMMANDS or found is None:
        return None
    options = [
        next((name for name in param.opts if name.startswith('--')), param.opts[0])
        for param in found.params
        if param.param_type_name == 'option'
    ]
    return f"{command} 에는 {option} 옵션이 없습니다. 이 명령의 옵션: {', '.join(options)}. '{command} --help' 로 사용법을 확인하세요"


def subcommand_hint(exc: UsageError) -> str | None:
    """그룹에 없는 하위 명령에 그 그룹의 하위 명령을 알린다 (`jibsa zigbang search listings 역삼동`).

    네이버·당근 `search listings` 는 지역을 바로 받아, 직방도 그렇게 부르다 유형(room·apt·store·stay)을 빼먹기 쉽다
    (2026-10-23 실측: 'No such command' 에 --help 만 안내했다). 하위 명령이 모두 끝 명령이고 빠뜨린 자리에 한글(지역
    이름)이 왔을 때만 예시를 붙인다. 하위 그룹이 섞인 곳(`jibsa naver`)은 첫 하위 명령이 그 이름을 받는다는 보장이 없다.
    예시는 매물 검색(`listings`)이 있으면 그것으로 든다 (지역을 하위 명령 자리에 준 사람은 대개 매물을 찾는다). 한글·영숫자와
    `.,·/-` 밖의 글자가 든 이름은 셸 따옴표로 감싸 그대로 붙여 넣어도 인자 하나가 되게 한다.
    """
    context = exc.ctx
    # Click 은 이름을 repr 로 감싸(작은따옴표가 든 이름은 큰따옴표) 마침표를 붙이고, 비슷한 이름이 있으면 'Did you mean' 을 잇는다
    match = re.match(r"No such command (['\"])(.*?)\1\.", exc.message)
    if context is None or match is None or not isinstance(context.command, TyperGroup):
        return None
    group = context.command
    commands = {name: group.get_command(context, name) for name in group.list_commands(context)}
    names = [name for name, command in commands.items() if command is not None and not command.hidden]
    if not names:
        return None
    word = match.group(2)
    # 이름 뒤에 조사를 붙이지 않는다 (영어·숫자도 온다, code-style 1절)
    hint = f"{context.command_path} 에 없는 하위 명령입니다. 하위 명령: {', '.join(names)}"
    # 'Did you mean' 이 붙은 오타(`listings역삼동`)는 click 이 고칠 이름을 이미 알려 예시를 붙이지 않는다. click 이 비슷한
    # 이름을 못 찾아도 명령 이름에 지역을 붙여 쓴 오타면 예시가 'room listings역삼동' 처럼 되어 붙이지 않는다 (명령 이름은
    # 소문자라 'DMC역' 같은 지역 이름과 가른다)
    glued = re.match(r'[a-z][a-z-]*', word)
    typo = 'Did you mean' in exc.message or (glued is not None and glued.group() in {*names, *context.command_path.split()})
    if HANGUL_PATTERN.search(word) and not typo and not any(isinstance(commands[name], TyperGroup) for name in names):
        example = 'listings' if 'listings' in names else names[0]
        shown = word if re.fullmatch(r'[\w.,·/-]+', word) else shlex.quote(word)
        hint += f' (지역 이름이면 하위 명령 뒤에 준다. 예: {context.command_path} {example} {shown})'
    # 다른 사용법 오류처럼 --help 안내로 끝낸다 (test_usage_errors_are_json_with_exit_2)
    return f"{hint}. '{context.command_path} --help' 로 사용법을 확인하세요"


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


def _find_command(cli: Command, path: str) -> Command | None:
    """`path`(`jibsa naver search listings`) 의 명령. 없으면 None."""
    command: Command | None = cli
    for name in path.split()[1:]:
        command = command.commands.get(name) if isinstance(command, TyperGroup) else None
    return command


def _has_option(cli: Command, path: str, option: str) -> bool:
    """`path`(`jibsa naver search listings`) 명령에 `option` 이 있는지."""
    command = _find_command(cli, path)
    return command is not None and any(option in param.opts for param in command.params)


def main() -> None:
    sys.exit(run())
