"""세 소스의 모든 CLI 명령을 실제로 불러 비공식 API 가 깨졌는지 본다 (매일 새벽 `.github/workflows/api-monitor.yml`).

매일 실행은 `DAILY_GROUPS`(직방·당근)만 돈다. 네이버는 GitHub 러너에서 응답을 받지 못해 매일 실행에서 빼고, 필요할 때 로컬에서
`run naver` 로 돌린다.

명령마다 셋으로 나눈다 (references/development.md '매일 API 감시').

- 정상: exit 0 이고 정한 칸(`Step.expect`)에 값이 있음
- 고장: 응답 형식 오류·서버 거절·내부 오류 같은 에러, 정한 칸이 비어 있음, JSON 이 아닌 출력, 대체 경로로 돌았다는 안내
  ('jibsa 를 업데이트하세요'). 결과가 0건일 리 없는 곳(역삼동·강남역·강남구 등)만 찾아서, 비어 있으면 사이트가 바뀐 것으로 본다
- 확인 못 함: 요청 제한·네트워크 오류·서버 5xx·방금 내려간 매물·시간 초과, 앞 명령이 넘길 번호를 주지 않아 건너뛴 명령.
  사이트가 바뀐 것인지 알 수 없다

    python scripts/monitor/api_check.py run zigbang --out result-zigbang.json
    python scripts/monitor/api_check.py report result-*.json [--issues] [--dry-run]

새 CLI 명령이나 매물을 찾는 새 방식(다른 API 를 쓰는 경로)을 만들면 GROUPS 에 넣는다. tests/test_cli.py 가 CLI 명령 목록과 대조한다.
"""

import argparse
import datetime
import json
import os
import string
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing import Any


@dataclass(frozen=True)
class Capture:
    """결과에서 뒤 명령에 넘길 값 하나. 목록 칸의 항목 중 조건에 맞는 첫 항목에서 꺼낸다.

    Args:
        name: 뒤 명령 인자의 `{name}` 에 채울 이름. 이미 담긴 이름이면 덮어쓰지 않는다.
        items: 결과의 목록 칸 (예: `listings`).
        field: 항목에서 꺼낼 칸 (예: `id`). 숫자면 문자열로 바꾼다.
        prefix: 이 글자로 시작하는 값만 (직방 단지 ID 의 `apt-`·`officetel-`).
        largest: 주면 이 칸이 가장 큰 항목에서 꺼낸다 (거래가 있을 평형을 고르려고 세대수가 가장 많은 평형).
    """

    name: str
    items: str
    field: str
    prefix: str = ''
    largest: str = ''


@dataclass(frozen=True)
class Step:
    """감시할 명령 하나.

    Args:
        label: 결과 표에 쓰는 이름.
        command: CLI 명령 경로 (예: `('zigbang', 'search', 'listings', 'room')`). 그룹 옵션으로 부르는 경로는 그룹까지
            (`('zigbang', 'search', 'listings')` + `--complex`).
        args: 인자. `{name}` 은 앞 명령의 `Capture` 값으로 채운다.
        expect: 값이 있어야 정상인 칸. 점으로 이어 안쪽 칸을 가리킨다 (`listing_count.weekly`).
        captures: 이 결과에서 뒤 명령에 넘길 값.
    """

    label: str
    command: tuple[str, ...]
    args: tuple[str, ...]
    expect: str
    captures: tuple[Capture, ...] = ()


# 명령 하나가 요청 제한 대기(최대 60초)를 몇 번 거쳐도 끝날 시간
COMMAND_TIMEOUT_SECONDS: int = 300

ROOM: tuple[str, ...] = ('zigbang', 'search', 'listings', 'room')
APT: tuple[str, ...] = ('zigbang', 'search', 'listings', 'apt')
ZIGBANG_LISTINGS: tuple[str, ...] = ('zigbang', 'search', 'listings')
ZIGBANG_LISTING: tuple[str, ...] = ('zigbang', 'listing')
NAVER_LISTINGS: tuple[str, ...] = ('naver', 'search', 'listings')
DAANGN_LISTINGS: tuple[str, ...] = ('daangn', 'search', 'listings')

# 러너 하나가 소스 하나를 돈다. 러너마다 IP 와 요청 제한 상태가 따로라 한 소스가 막혀도 다른 소스 검사는 그대로 된다.
# 매물 검색은 찾는 방식(동 이름 경계·역 반경·좌표 반경·단지)마다 쓰는 API 가 달라 방식별로 부른다. --limit 은 작게 준다
# (감시는 결과가 있는지만 보고, 네이버는 요청 제한이 가장 엄격하다)
GROUPS: dict[str, tuple[Step, ...]] = {
    'zigbang': (
        Step('지역 찾기 역삼동', ('zigbang', 'search', 'locations'), ('역삼동',), 'results'),
        Step('원룸 동 경계 역삼동', ROOM, ('역삼동', '--limit', '2'), 'listings', (Capture('room', 'listings', 'id'),)),
        Step('원룸 상세', ZIGBANG_LISTING, ('{room}',), 'id'),
        # 오피스텔 건물은 매물이 있는 건물이어야 해서 매물 목록에서 고른다
        Step(
            '원룸 역 반경 강남역', ROOM, ('강남역', '--limit', '5'), 'listings',
            (Capture('officetel', 'listings', 'complex_id', prefix='officetel-'),),
        ),
        Step(
            '아파트 동 목록 역삼동', APT, ('역삼동', '--limit', '2'), 'listings',
            (Capture('apt', 'listings', 'complex_id', prefix='apt-'), Capture('apt_listing', 'listings', 'id')),
        ),
        Step('아파트 상세', ZIGBANG_LISTING, ('{apt_listing}',), 'id'),
        Step('아파트 역 반경 강남역', APT, ('강남역', '--radius', '1', '--limit', '2'), 'listings'),
        Step('아파트 단지', ('zigbang', 'complex'), ('{apt}',), 'name'),
        Step('아파트 실거래가', ('zigbang', 'real-price'), ('{apt}', '--limit', '3'), 'transactions'),
        Step('아파트 단지 매물', ZIGBANG_LISTINGS, ('--complex', '{apt}', '--limit', '2'), 'listings'),
        Step('오피스텔 건물', ('zigbang', 'complex'), ('{officetel}',), 'name'),
        Step('오피스텔 건물 매물', ZIGBANG_LISTINGS, ('--complex', '{officetel}', '--limit', '2'), 'listings'),
        Step(
            '상가 역 반경 강남역', ('zigbang', 'search', 'listings', 'store'), ('강남역', '--limit', '2'), 'listings',
            (Capture('store', 'listings', 'id'),),
        ),
        Step('상가 상세', ZIGBANG_LISTING, ('{store}',), 'id'),
        Step(
            '단기임대 지역 강남구', ('zigbang', 'search', 'listings', 'stay'), ('강남구', '--limit', '2'), 'listings',
            (Capture('stay', 'listings', 'id'),),
        ),
        Step('단기임대 상세', ZIGBANG_LISTING, ('{stay}',), 'id'),
        Step('단기임대 역 반경 강남역', ('zigbang', 'search', 'listings', 'stay'), ('강남역', '--radius', '1', '--limit', '2'), 'listings'),
    ),
    'naver': (
        Step('하위 지역 강남구', ('naver', 'regions'), ('강남구',), 'regions'),
        Step('동네 추이 역삼동', ('naver', 'trend'), ('역삼동',), 'listing_count.weekly'),
        Step('매물 동 전체 역삼동', NAVER_LISTINGS, ('역삼동', '--limit', '2'), 'listings', (Capture('article', 'listings', 'id'),)),
        Step('매물 상세', ('naver', 'listing'), ('{article}',), 'id'),
        Step('매물 역 반경 강남역', NAVER_LISTINGS, ('강남역', '--limit', '2'), 'listings'),
        Step(
            '단지 목록 역삼동', ('naver', 'search', 'complexes'), ('역삼동', '--sort', '세대수순', '--limit', '1'), 'complexes',
            (Capture('complex', 'complexes', 'complex_number'),),
        ),
        Step(
            '단지', ('naver', 'complex'), ('{complex}',), 'pyeongs',
            (Capture('pyeong', 'pyeongs', 'number', largest='household_count'), Capture('school', 'schools', 'school_code')),
        ),
        Step('평형 실거래가', ('naver', 'real-price'), ('{complex}', '--pyeong', '{pyeong}'), 'transactions'),
        Step('평형 시세', ('naver', 'market-price'), ('{complex}', '--pyeong', '{pyeong}'), 'providers'),
        Step('학교', ('naver', 'school'), ('{school}',), 'school_code'),
        Step('단지 매물', NAVER_LISTINGS, ('--complex', '{complex}', '--limit', '2'), 'listings'),
        Step(
            '재개발 구역 한남동', ('naver', 'search', 'redevelopment'), ('한남동', '--limit', '1'), 'areas',
            (Capture('redevelopment', 'areas', 'redevelopment_number'),),
        ),
        Step('재개발 구역', ('naver', 'redevelopment'), ('{redevelopment}',), 'redevelopment_number'),
        Step('재개발 구역 매물', NAVER_LISTINGS, ('--redevelopment', '{redevelopment}', '--limit', '2'), 'listings'),
    ),
    'daangn': (
        Step('지역 찾기 역삼동', ('daangn', 'search', 'locations'), ('역삼동',), 'results'),
        # 지도 페이지(SSR)를 읽는 경로. 역삼동은 같은 이름 후보가 둘이라 후보마다 지도 페이지를 확인하는 경로도 지난다
        Step('매물 동 역삼동', DAANGN_LISTINGS, ('역삼동', '--limit', '2'), 'listings', (Capture('article', 'listings', 'id'),)),
        Step('매물 상세', ('daangn', 'listing'), ('{article}',), 'id'),
        # 조건이 있으면 지도 페이지 대신 필터 API(articleFeed·articlesCount)로 받는다
        Step('매물 동 조건 역삼동 월세', DAANGN_LISTINGS, ('역삼동', '--trade', '월세', '--limit', '2'), 'listings'),
        Step('매물 역 강남역', DAANGN_LISTINGS, ('강남역', '--limit', '2'), 'listings'),
        Step('매물 반경 강남역', DAANGN_LISTINGS, ('강남역', '--radius', '0.5', '--limit', '2'), 'listings'),
        Step('출퇴근 강남역', ('daangn', 'search', 'commute'), ('강남역', '--limit', '2'), 'stations'),
        Step(
            '단지 목록 역삼동', ('daangn', 'search', 'complexes'), ('역삼동', '--limit', '2'), 'complexes',
            (Capture('complex', 'complexes', 'complex_id'),),
        ),
        Step('단지', ('daangn', 'complex'), ('{complex}',), 'name'),
        Step('단지 실거래가', ('daangn', 'real-price'), ('{complex}', '--limit', '3'), 'transactions'),
        Step('단지 시세 추이', ('daangn', 'price-trend'), ('{complex}',), 'points'),
        Step(
            '같은 동 단지', ('daangn', 'nearby-complexes'), ('{complex}', '--limit', '2'), 'complexes',
            (Capture('neighbor', 'complexes', 'complex_id'),),
        ),
        Step('단지 비교', ('daangn', 'compare'), ('{complex}', '{neighbor}'), 'complexes'),
        Step('학교 역삼초등학교', ('daangn', 'school'), ('역삼초등학교',), 'complexes'),
        Step('동 실거래 역삼동', ('daangn', 'region-real-price'), ('역삼동', '--limit', '3'), 'transactions'),
        Step('동네 후기 강남구', ('daangn', 'region-reviews'), ('강남구', '--top', '3'), 'top_complexes'),
        Step(
            '개발 호재 한남동', ('daangn', 'developments'), ('한남동', '--limit', '2'), 'developments',
            (Capture('development', 'developments', 'id'),),
        ),
        Step('개발 사업', ('daangn', 'development'), ('{development}',), 'name'),
        Step(
            '어린이집 역삼역', ('daangn', 'preschools'), ('역삼역', '--limit', '2'), 'preschools',
            (Capture('preschool', 'preschools', 'id'),),
        ),
        Step('어린이집', ('daangn', 'preschool'), ('{preschool}',), 'name'),
        Step(
            '좋은 동네 서울', ('daangn', 'good-neighborhoods'), ('--lifestyle', '직장인자취', '--region', '서울', '--limit', '3'),
            'neighborhoods',
        ),
        Step('인기 단지 역삼동', ('daangn', 'trending-complexes'), ('역삼동',), 'complexes'),
        Step('인기 매물 역삼동', ('daangn', 'popular-listings'), ('역삼동', '--limit', '3'), 'listings'),
    ),
}

# 매일 실행(워크플로 matrix)이 도는 소스. matrix 와 같게 둔다. 네이버는 GitHub 러너에서 응답을 받지 못해 로컬에서만 돌린다
DAILY_GROUPS: tuple[str, ...] = ('zigbang', 'daangn')

OK: str = 'ok'
BROKEN: str = 'broken'
UNKNOWN: str = 'unknown'
STATUS_LABELS: dict[str, str] = {OK: '✅ 정상', BROKEN: '❌ 고장', UNKNOWN: '⚠️ 확인 못 함'}
# 사이트가 바뀐 것인지 알 수 없는 에러. 그 밖의 에러 코드(PARSE_ERROR, INTERNAL_ERROR, NOT_FOUND, REGION_NOT_FOUND 등)는 고장이다
UNKNOWN_CODES: frozenset[str] = frozenset({'RATE_LIMITED', 'NETWORK_ERROR', 'LISTING_UNAVAILABLE'})
# 웹 쿼리가 바뀌어 예전 방식으로 돌았다는 안내 (당근 FEED_FALLBACK_NOTE). 결과는 나오지만 고쳐야 한다
DEGRADED_MARKER: str = 'jibsa 를 업데이트하세요'

BROKEN_LABEL: str = 'api-broken'
BLOCKED_LABEL: str = 'api-blocked'
# 같은 소스가 이만큼 연속으로 확인 못 함이면 알린다 (오늘 포함)
BLOCKED_STREAK: int = 3
WORKFLOW_FILE: str = 'api-monitor.yml'
REPORT_ARTIFACT: str = 'report'


# --- 조회 ---

def _error(stderr: str) -> dict[str, Any] | None:
    """stderr 의 에러 JSON (`--verbose` 로그 뒤 마지막 `{` 줄)."""
    for line in reversed(stderr.splitlines()):
        if line.startswith('{'):
            try:
                body = json.loads(line).get('error')
            except ValueError:
                return None
            return body if isinstance(body, dict) else None
    return None


def _is_unknown(error: dict[str, Any]) -> bool:
    code = error.get('code')
    if code in UNKNOWN_CODES:
        return True
    # 서버 5xx 는 사이트가 바뀐 것이 아니다. 4xx 와 상태 없는 UPSTREAM_ERROR(웹 쿼리 해시 거절 등)는 요청이 맞지 않게 된 것이라 고장이다
    status = error.get('status')
    return code == 'UPSTREAM_ERROR' and isinstance(status, int) and status >= 500


def _value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _present(value: Any) -> bool:
    return value is not None and value != '' and value != [] and value != {}


def _capture(data: dict[str, Any], capture: Capture) -> str | None:
    items = data.get(capture.items)
    if not isinstance(items, list):
        return None
    found = [
        item for item in items
        if isinstance(item, dict) and _present(item.get(capture.field)) and str(item[capture.field]).startswith(capture.prefix)
    ]
    if capture.largest:
        found.sort(key=lambda item: item[capture.largest] if isinstance(item.get(capture.largest), int | float) else -1, reverse=True)
    return str(found[0][capture.field]) if found else None


def _names(step: Step) -> list[str]:
    """인자에 채워야 하는 `{name}` 들."""
    return [name for arg in step.args for _, name, _, _ in string.Formatter().parse(arg) if name]


def _run_step(step: Step, values: dict[str, str]) -> tuple[str, str, dict[str, Any] | None]:
    """(판정, 내용, stdout JSON)."""
    command = [*step.command, *(arg.format(**values) for arg in step.args)]
    print(f"::group::jibsa {' '.join(command)}", flush=True)
    try:
        done = subprocess.run(
            [sys.executable, '-m', 'jibsa', '--verbose', *command],
            capture_output=True, text=True, encoding='utf-8', timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print('::endgroup::', flush=True)
        return UNKNOWN, f'{COMMAND_TIMEOUT_SECONDS}초 안에 끝나지 않음', None
    # 요청 로그만 남긴다. 결과(매물 제목·주소)는 공개 실행 기록에 남기지 않고, 고장일 때만 앞부분을 남긴다
    print(done.stderr.strip())
    status, detail, data = _judge(step, done)
    if status != OK:
        print(done.stdout.strip()[:1000])
    print('::endgroup::', flush=True)
    return status, detail, data


def _judge(step: Step, done: subprocess.CompletedProcess[str]) -> tuple[str, str, dict[str, Any] | None]:
    if done.returncode == 0:
        try:
            data = json.loads(done.stdout)
        except ValueError:
            return BROKEN, 'stdout 이 JSON 이 아님', None
        if not isinstance(data, dict):
            return BROKEN, 'stdout 이 JSON 객체가 아님', None
        degraded = [note for note in data.get('notes') or [] if isinstance(note, str) and DEGRADED_MARKER in note]
        if degraded:
            return BROKEN, f'대체 경로로 돌았음: {degraded[0][:200]}', data
        value = _value(data, step.expect)
        if not _present(value):
            return BROKEN, f'{step.expect} 칸이 비어 있음', data
        return OK, f'{len(value)}건' if isinstance(value, list) else f'{step.expect} 있음', data
    error = _error(done.stderr)
    if error is None:
        return BROKEN, f'exit {done.returncode}, 에러 JSON 없음', None
    detail = ' '.join(str(part) for part in (error.get('code'), error.get('status')) if part)
    message = str(error.get('message') or '').replace('\n', ' ')
    return (UNKNOWN if _is_unknown(error) else BROKEN), f'{detail}: {message[:200]}', None


def run_group(name: str) -> dict[str, Any]:
    """소스 하나의 명령을 차례로 부른다. 앞 명령이 넘길 번호를 주지 않은 명령은 건너뛴다 (확인 못 함)."""
    values: dict[str, str] = {}
    steps: list[dict[str, str]] = []
    for step in GROUPS[name]:
        line = ' '.join(step.command)
        missing = [field for field in _names(step) if field not in values]
        if missing:
            steps.append({
                'label': step.label, 'command': line, 'status': UNKNOWN,
                'detail': f"앞 명령 결과에 {', '.join(missing)} 값이 없어 건너뜀",
            })
            continue
        status, detail, data = _run_step(step, values)
        for capture in step.captures:
            found = _capture(data, capture) if data else None
            if found is not None:
                values.setdefault(capture.name, found)
        steps.append({'label': step.label, 'command': line, 'status': status, 'detail': detail})
    return {'group': name, 'date': datetime.date.today().isoformat(), 'status': _overall([step['status'] for step in steps]), 'steps': steps}


def _overall(statuses: list[str]) -> str:
    if BROKEN in statuses:
        return BROKEN
    return UNKNOWN if UNKNOWN in statuses else OK


# --- 결과 정리 ---

def _table(results: list[dict[str, Any]]) -> str:
    rows = ['| 소스 | 명령 | 결과 | 내용 |', '| --- | --- | --- | --- |']
    for result in results:
        for step in result['steps']:
            detail = step['detail'].replace('|', '\\|')
            rows.append(f"| {result['group']} | {step['label']} (`{step['command']}`) | {STATUS_LABELS[step['status']]} | {detail} |")
    return '\n'.join(rows)


def _run_link(text: str = '실행 기록') -> str:
    server, repository, run_id = (os.environ.get(key) for key in ('GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'))
    return f' ([{text}]({server}/{repository}/actions/runs/{run_id}))' if server and repository and run_id else ''


def _gh(*args: str, write: bool = False, dry_run: bool = False) -> str:
    """gh CLI. `dry_run` 이면 이슈·라벨을 바꾸는 명령은 보내지 않고 출력만 한다."""
    if write and dry_run:
        print('[dry-run] gh', ' '.join(args))
        return ''
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True, encoding='utf-8').stdout


def _open_issue(label: str) -> int | None:
    issues = json.loads(_gh('issue', 'list', '--label', label, '--state', 'open', '--json', 'number', '--limit', '1'))
    return issues[0]['number'] if issues else None


def _previous_reports(count: int) -> list[dict[str, Any]]:
    """앞선 예약·수동 실행의 소스별 판정 (가까운 것부터). 결과 파일이 없는 실행(만료·실패)을 만나면 거기서 멈춘다."""
    try:
        runs = json.loads(_gh('run', 'list', '--workflow', WORKFLOW_FILE, '--status', 'completed', '--limit', '20', '--json', 'databaseId,event'))
    except subprocess.CalledProcessError:
        # 워크플로가 아직 기본 브랜치에 없으면(첫 실행 전) 실행 목록을 묻지 못한다
        return []
    current = os.environ.get('GITHUB_RUN_ID')
    reports: list[dict[str, Any]] = []
    for run in runs:
        if len(reports) == count:
            break
        if run['event'] not in ('schedule', 'workflow_dispatch') or str(run['databaseId']) == current:
            continue
        with tempfile.TemporaryDirectory() as folder:
            try:
                _gh('run', 'download', str(run['databaseId']), '--name', REPORT_ARTIFACT, '--dir', folder)
            except subprocess.CalledProcessError:
                break
            reports.append(json.loads((Path(folder) / 'report.json').read_text(encoding='utf-8')))
    return reports


def _update_issues(results: list[dict[str, Any]], dry_run: bool) -> None:
    """고장은 api-broken, 사흘 연속 확인 못 함은 api-blocked 이슈로 알린다. 다시 모두 괜찮아지면 닫는다."""
    table, link = _table(results), _run_link()
    statuses = {result['group']: result['status'] for result in results}
    broken = [group for group, status in statuses.items() if status == BROKEN]
    _gh('label', 'create', BROKEN_LABEL, '--color', 'd73a4a', '--description', '매일 API 감시가 찾은 고장', '--force', write=True, dry_run=dry_run)
    _gh('label', 'create', BLOCKED_LABEL, '--color', 'fbca04', '--description', '매일 API 감시가 며칠째 확인하지 못함', '--force', write=True, dry_run=dry_run)

    number = _open_issue(BROKEN_LABEL)
    if broken:
        body = f"{datetime.date.today()} 감시에서 고장: {', '.join(broken)}{link}\n\n{table}"
        if number is None:
            _gh('issue', 'create', '--label', BROKEN_LABEL, '--title', f"API 감시: 고장 ({', '.join(broken)})", '--body', body,
                write=True, dry_run=dry_run)
        else:
            _gh('issue', 'comment', str(number), '--body', body, write=True, dry_run=dry_run)
    elif number is not None and all(status == OK for status in statuses.values()):
        _gh('issue', 'close', str(number), '--comment', f'{datetime.date.today()} 감시에서 모두 정상이다{link}', write=True, dry_run=dry_run)

    previous = [{result['group']: result['status'] for result in report['results']} for report in _previous_reports(BLOCKED_STREAK - 1)]
    streak = [
        group for group, status in statuses.items()
        if status == UNKNOWN and len(previous) == BLOCKED_STREAK - 1 and all(report.get(group) == UNKNOWN for report in previous)
    ]
    number = _open_issue(BLOCKED_LABEL)
    if streak and number is None:
        body = (f"{BLOCKED_STREAK}일 연속 확인 못 함: {', '.join(streak)}{_run_link('오늘 실행 기록')}. 요청 제한·서버 오류 등으로 "
                f'고장인지 알 수 없는 상태가 이어진다. 막힘이 계속되면 그 소스를 덜 자주 돌리는 것을 검토한다.\n\n{table}')
        _gh('issue', 'create', '--label', BLOCKED_LABEL, '--title', f"API 감시: {BLOCKED_STREAK}일째 확인 못 함 ({', '.join(streak)})",
            '--body', body, write=True, dry_run=dry_run)
    elif number is not None and UNKNOWN not in statuses.values():
        _gh('issue', 'close', str(number), '--comment', f'{datetime.date.today()} 감시에서 확인 못 함이 없다{link}', write=True, dry_run=dry_run)


def report(paths: list[str], *, issues: bool, dry_run: bool) -> int:
    """소스별 결과 파일을 모아 표를 남기고, 고장이 있으면 1 을 돌려준다 (실행이 실패로 끝나 GitHub 이 메일로 알린다)."""
    found = {}
    for path in paths:
        # 결과 파일이 하나도 없으면 셸이 글롭(result-*.json)을 그대로 넘긴다
        if not Path(path).is_file():
            continue
        result = json.loads(Path(path).read_text(encoding='utf-8'))
        found[result['group']] = result
    # 매일 도는 소스 중 결과 파일이 없는 것은 조회 잡이 감시 코드나 설치에서 실패한 것이다. 로컬에서 돌린 다른 소스 결과도 함께 싣는다
    results = [
        found.get(group) or {
            'group': group, 'status': BROKEN,
            'steps': [{'label': '조회 잡', 'command': '-', 'status': BROKEN, 'detail': '결과 파일 없음 (조회 잡 실패)'}],
        }
        for group in [*DAILY_GROUPS, *(group for group in found if group not in DAILY_GROUPS)]
    ]
    text = f'## API 감시 {datetime.date.today()}\n\n{_table(results)}\n'
    print(text)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as file:
            file.write(text)
    Path('report.json').write_text(json.dumps({'results': results}, ensure_ascii=False), encoding='utf-8')
    if issues:
        _update_issues(results, dry_run)
    return 1 if any(result['status'] == BROKEN for result in results) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='action', required=True)
    run = commands.add_parser('run', help='소스 하나의 명령을 부르고 결과를 JSON 파일로 쓴다')
    run.add_argument('group', choices=list(GROUPS))
    run.add_argument('--out', required=True)
    collect = commands.add_parser('report', help='결과 파일을 모아 표를 남기고 이슈를 고친다')
    collect.add_argument('paths', nargs='*')
    collect.add_argument('--issues', action='store_true', help='고장·연속 확인 못 함을 이슈로 알린다 (예약·수동 실행만)')
    collect.add_argument('--dry-run', action='store_true', help='이슈·라벨을 바꾸지 않고 보낼 gh 명령만 출력한다')
    options = parser.parse_args()
    if options.action == 'run':
        result = run_group(options.group)
        Path(options.out).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        print(_table([result]))
        return 0
    return report(options.paths, issues=options.issues, dry_run=options.dry_run)


if __name__ == '__main__':
    sys.exit(main())
