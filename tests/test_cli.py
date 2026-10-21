import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import typer

from jibsa.cli.app import (
    app,
    run,
)


def stderr_error(capsys: pytest.CaptureFixture[str]) -> dict:
    captured = capsys.readouterr()
    assert captured.out == ''
    return json.loads(captured.err)['error']


@pytest.mark.parametrize(
    'argv',
    [
        ['zigbang', 'search', 'listings', 'room', '역삼동', '-t', '공장'],  # split_csv 의 BadParameter (힌트 표에 없는 값)
        ['naver', 'search', 'listings', '역삼동', '--foo'],  # 없는 옵션
        ['nope'],                                         # 없는 명령
        ['zigbang', 'listing'],                              # 필수 인자 누락
        ['naver', 'search', 'listings', '--lat', '37.5', '--lng', '127.0', '--sort', '거리순'],  # 없는 정렬
        ['naver', 'real-price', 'abc', '--pyeong', '1'],                   # 타입 오류 (complex·items 는 단지 이름도 받는다)
        ['naver', 'search', 'listings', '역삼동', '--limit', '121'],  # 조회 한도 초과
        ['naver', 'search', 'complexes', '역삼동', '--limit', '121'],
        ['naver', 'real-price', '100001'],                 # 필수 평형 번호 누락
        ['naver', 'complex', '100001', '--pyeong', '0'],   # 평형 ID 는 1부터
        ['zigbang', 'search', 'listings', 'room', '역삼동', '--radius', '9'],  # 범위 오류
        ['naver', 'real-price', '100001', '--pyeong', '1', '--trade', '매매,전세'],  # 하나만 받는 옵션에 여러 값
        ['naver', 'real-price', '100001', '--pyeong', '1', '--period', '2년'],         # 없는 기간
        ['naver', 'real-price', '100001', '--pyeong', '1', '--period', '1년', '--pages', '2'],  # 기간과 페이지를 함께
        ['naver', 'market-price', '100001', '--pyeong', '1', '--period', '10년'],
        ['daangn', 'search', 'listings'],                                        # 동 이름도 좌표도 없음
        ['daangn', 'search', 'listings', '역삼동', '--lat', '37.5', '--lng', '127.0'],  # 동 이름과 좌표를 함께
        ['daangn', 'search', 'listings', '--lat', '37.5', '--lng', '127.0', '--expand', '2'],  # 동 이름 전용 옵션
        ['daangn', 'search', 'listings', '역삼동', '--radius', '2', '--expand', '1'],  # 반경 검색에 동 단위 전용 옵션
        ['daangn', 'search', 'locations'],                                        # 동 이름도 좌표도 없음
        ['daangn', 'real-price'],                                    # 단지 ID 도 --item 도 없음
        ['daangn', 'real-price', '100', '--item', '200'],            # 단지 ID 와 --item 을 함께
        ['daangn', 'real-price', '--item', '200', '--area', '84'],   # --area 는 단지로 볼 때만
        ['daangn', 'region-real-price', '강남구', '--new-high', '--trade', '전세'],  # 신고가는 매매만
        ['daangn', 'region-real-price', '강남구', '--trade', '월세', '--sort', '가격'],  # 가격 순은 매매만
        ['daangn', 'search', 'commute'],                                       # 회사 위치도 좌표도 없음
        ['daangn', 'search', 'listings', '역삼동', '--deposit-min', '2000', '--deposit-max', '1000'],
        ['daangn', 'search', 'listings', '--complex', '100', '--rent-min', '80', '--rent-max', '60'],
        ['daangn', 'search', 'commute', '강남역', '--area-min', '30', '--area-max', '20'],
        ['daangn', 'search', 'complexes', '역삼동', '--household-min', '500', '--household-max', '100'],
        ['daangn', 'search', 'listings', '역삼동', '--area-min', 'nan'],
        ['naver', 'trend', '역삼동', '--trade', '월세'],                        # 네이버가 월세 추이를 주지 않는다
        ['naver', 'trend', '역삼동', '--pyeong-range', '35'],                   # 평형대는 10평 단위
        ['naver', 'search', 'listings', '한남동', '--redevelopment', '9000001'],  # 구역과 지역을 함께
        ['naver', 'search', 'listings', '--redevelopment', '9000001', '--room', '원룸'],  # 구역 매물에 없는 조건
        ['zigbang', 'search', 'listings', 'room', '역삼동', '--trade', '전세', '--rent-max', '50'],  # 서버가 무시하는 가격 조건
        ['zigbang', 'search', 'listings', '--complex', 'apt-100', '--trade', '단기임대'],   # 아파트 단지에 없는 거래
    ],
)
def test_usage_errors_are_json_with_exit_2(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_request(*args, **kwargs) -> None:
        raise AssertionError('입력 오류 검증에서 HTTP 요청을 보내면 안 됩니다')

    monkeypatch.setattr(httpx.Client, 'send', unexpected_request)
    assert run(argv) == 2
    error = stderr_error(capsys)
    assert error['code'] == 'INVALID_ARGUMENT'
    assert error['hint'].endswith("--help' 로 사용법을 확인하세요")


@pytest.mark.parametrize('command,place,options', [
    (['search', 'listings'], '역삼동', ['-t', '오피스텔', '--structure', '분리형']),
    (['search', 'listings'], '역삼동', ['-t', '원룸', '--household-min', '100']),
    (['search', 'commute'], '강남역', ['-t', '오피스텔', '--structure', '분리형']),
    (['search', 'commute'], '강남역', ['--floor', '잘못된층']),
])
def test_daangn_invalid_filters_do_not_request_location(
    command: list[str],
    place: str,
    options: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list = []

    def unexpected_request(*args, **kwargs) -> None:
        requests.append(args)
        raise AssertionError('잘못된 검색 조건으로 위치를 조회하면 안 됩니다')

    monkeypatch.setattr(httpx.Client, 'send', unexpected_request)
    assert run(['daangn', *command, place, *options]) == 2
    assert stderr_error(capsys)['code'] == 'INVALID_ARGUMENT'
    assert requests == []


def test_jibsa_invalid_argument_exits_2_with_own_hint(capsys: pytest.CaptureFixture[str]) -> None:
    # 조회 중에야 알 수 있는 입력 오류(JibsaError)도 사용법 오류와 같은 exit 2 이고, 자기 힌트는 그대로 둔다
    assert run(['zigbang', 'search', 'listings', 'room', '역삼동', '-t', '원룸', '--without-random']) == 2
    error = stderr_error(capsys)
    assert error['code'] == 'INVALID_ARGUMENT'
    assert '--without-random' in error['hint']


def test_limits_state_dir_failure_is_json_error(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 상태 디렉터리 자리에 파일이 있으면 만들 수 없다. traceback 대신 에러 JSON 이어야 한다
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('')
    monkeypatch.setenv('JIBSA_STATE_DIR', str(blocker))
    assert run(['limits']) == 1
    error = stderr_error(capsys)
    assert error['code'] == 'INTERNAL_ERROR'
    assert error['source'] == 'limits'


def test_success_exit_zero_and_json_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(['limits', '--compact']) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)['sources']
    assert captured.err == ''


def test_listing_output_hides_coordinates(capsys: pytest.CaptureFixture[str]) -> None:
    from jibsa.cli.output import emit
    from jibsa.core.listing import Listing

    listing = Listing(source='zigbang', id='1', url='https://example.com/1', trade_type='월세', property_type='원룸', lat=37.0, lng=127.0)
    emit({'listings': [listing.model_dump(mode='json', exclude_none=True)]}, pretty=False)
    payload = json.loads(capsys.readouterr().out)
    assert 'lat' not in payload['listings'][0]


@pytest.mark.parametrize('command', ['zigbang search listings room', 'naver search listings'])
@pytest.mark.parametrize('coordinate', [['--lat', '37.5'], ['--lng', '127.0']])
@pytest.mark.parametrize('query', [['역삼동'], []])
def test_one_coordinate_alone_is_rejected(
    command: str,
    coordinate: list[str],
    query: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 지역명과 함께 줘도 좌표 하나는 조용히 무시되므로 요청 전에 막는다.
    # 지역명이 없어도 '지역 이름을 주세요' 가 아니라 '둘 다 주세요' 로 안내한다.
    assert run([*command.split(), *query, *coordinate]) == 2
    error = stderr_error(capsys)
    assert error['code'] == 'INVALID_ARGUMENT'
    assert error['message'] == '--lat 과 --lng 는 함께 주어야 합니다'


def test_notes_come_first_and_vanish_when_empty(capsys: pytest.CaptureFixture[str]) -> None:
    from jibsa.cli.output import emit

    emit({'returned': 0}, pretty=False, notes=['안내'])
    assert list(json.loads(capsys.readouterr().out)) == ['notes', 'returned']
    emit({'returned': 0}, pretty=False, notes=[])
    assert list(json.loads(capsys.readouterr().out)) == ['returned']


def fake_upstream(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    """모든 실제 HTTP 전송을 `response` 로 바꾼다."""
    def handle_request(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', handle_request)


def test_non_json_response_is_parse_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # 차단 페이지처럼 HTML 이 오면 traceback 이 아니라 에러 JSON 이어야 한다
    fake_upstream(monkeypatch, httpx.Response(200, text='<html>blocked</html>'))
    assert run(['naver', 'complex', '100001']) == 1
    assert stderr_error(capsys)['code'] == 'PARSE_ERROR'


def test_response_validation_error_is_not_invalid_argument(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 응답 형식이 바뀐 것은 입력 오류(exit 2)가 아니다
    fake_upstream(monkeypatch, httpx.Response(200, json={'isSuccess': True, 'result': {'name': None}}))
    assert run(['naver', 'complex', '100001']) == 1
    assert stderr_error(capsys)['code'] == 'PARSE_ERROR'


def test_unexpected_exception_is_internal_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError('boom')

    monkeypatch.setattr('jibsa.cli.naver.get_complex', broken)
    assert run(['naver', 'complex', '100001']) == 1
    assert stderr_error(capsys)['code'] == 'INTERNAL_ERROR'


def test_keyboard_interrupt_is_json_error_with_exit_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Typer 는 KeyboardInterrupt 를 아무것도 쓰지 않고 Exit(130) 으로 바꾼다. stderr 가 비면 안 된다
    def interrupted(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr('jibsa.cli.naver.get_complex', interrupted)
    assert run(['naver', 'complex', '100001']) == 130
    error = stderr_error(capsys)
    assert error['code'] == 'INTERRUPTED'
    assert error['hint']


def test_naver_search_naver_rate_limit_is_naver_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 지역 조회에서 네이버가 막히면 네이버 에러로 끝낸다
    from jibsa.core.ratelimit import RateLimitedError

    def rate_limited(*args, **kwargs):
        raise RateLimitedError('naver', 900.0, 'cooldown')

    monkeypatch.setattr('jibsa.cli.naver.resolve_search_region', rate_limited)
    assert run(['naver', 'search', 'listings', '역삼동']) == 1
    error = stderr_error(capsys)
    assert (error['code'], error['source']) == ('RATE_LIMITED', 'naver')


def test_daangn_coordinate_search_with_rejected_map_query_is_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import jibsa.cli.daangn as daangn_cli
    from jibsa.providers.daangn.service.common import FeedQueryRejectedError

    def rejected(*args, **kwargs):
        raise FeedQueryRejectedError('PERSISTED_QUERY_NOT_IN_LIST')

    monkeypatch.setattr(daangn_cli, 'search_area', rejected)
    monkeypatch.setattr(daangn_cli, 'region_by_coordinate', rejected)
    for argv in (['daangn', 'search', 'listings', '--lat', '37.5', '--lng', '127.0'], ['daangn', 'search', 'locations', '--lat', '37.5', '--lng', '127.0']):
        assert run(argv) == 1
        error = stderr_error(capsys)
        assert (error['code'], error['source']) == ('UPSTREAM_ERROR', 'daangn')
        assert '동 이름으로' in error['hint']


@pytest.mark.parametrize('naver', ['found', 'not-found', 'blocked'])
def test_daangn_geocode_falls_back_to_naver_when_zigbang_blocked(monkeypatch: pytest.MonkeyPatch, naver: str) -> None:
    import jibsa.cli.daangn as daangn_cli
    from jibsa.core.errors import RegionNotFoundError
    from jibsa.core.ratelimit import RateLimitedError
    from jibsa.providers.naver.service.region import NaverRegion

    # 실제 함수처럼 radius_km 는 키워드로만 받는다. 위치 인자로 부르면 TypeError 라 그 실수를 잡는다
    def zigbang(client, name, *, radius_km):
        raise RateLimitedError('zigbang', 120, 'cooldown')

    def naver_region(client, name, radius_km):
        if naver == 'blocked':
            raise RateLimitedError('naver', 900, 'cooldown')
        if naver == 'not-found':
            raise RegionNotFoundError(name)
        return NaverRegion(name='역삼역', lat=37.5006, lng=127.0364), []

    # 당근 역·주소 검색이 확실히 찾지 못한 이름이라 직방으로 넘어간다
    monkeypatch.setattr(daangn_cli, 'find_place', lambda client, name: None)
    monkeypatch.setattr(daangn_cli, 'resolve_region_with_notes', zigbang)
    monkeypatch.setattr(daangn_cli, 'resolve_naver_region', naver_region)
    if naver == 'found':
        region, notes, finder = daangn_cli._geocode('역삼역', 1.0)
        assert (region.lat, region.lng, finder) == (37.5006, 127.0364, '네이버')
        assert notes == ["직방이 요청 제한으로 막혀 있어 '역삼역' 위치를 네이버 지역 검색으로 찾았습니다"]
        return
    # 네이버로도 못 찾으면 막힌 직방의 에러에, 지금 되는 방법(당근 동 이름, 좌표)을 안내한다
    with pytest.raises(RateLimitedError) as exc:
        daangn_cli._geocode('서울대학교', 1.0)
    assert exc.value.details['source'] == 'zigbang'
    assert ('네이버도 막혀' if naver == 'blocked' else '네이버 지역 검색으로는 찾지 못했습니다') in exc.value.hint
    assert '당근 동 이름' in exc.value.hint and '어느 소스로도' not in exc.value.hint


# --- 매일 API 감시 ---

def test_every_source_command_is_in_api_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    # 비공식 API 는 언제 바뀔지 몰라 매일 새벽 소스 명령을 모두 실제로 불러 본다 (scripts/monitor/api_check.py).
    # 새 명령을 만들고 감시 목록에 넣지 않으면 그 명령은 깨져도 모른다
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'monitor' / 'api_check.py'
    spec = importlib.util.spec_from_file_location('api_check', path)
    assert spec is not None and spec.loader is not None
    monitor = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, 'api_check', monitor)  # dataclass 가 자기 모듈을 찾는다
    spec.loader.exec_module(monitor)

    leaves: set[tuple[str, ...]] = set()
    groups: set[tuple[str, ...]] = set()

    def walk(command: object, path: tuple[str, ...]) -> None:
        commands = getattr(command, 'commands', None)
        if not commands:
            leaves.add(path)
            return
        groups.add(path)
        for name, sub in commands.items():
            walk(sub, (*path, name))

    walk(typer.main.get_command(app), ())
    source_commands = {leaf for leaf in leaves if leaf[0] in ('zigbang', 'naver', 'daangn')}
    monitored = {step.command for steps in monitor.GROUPS.values() for step in steps}
    assert source_commands - monitored == set()
    # 그룹 옵션으로 부르는 경로(search listings --complex)도 있어 그룹까지는 받는다. 그 밖은 없는 명령(오타)이다
    assert monitored - source_commands - groups == set()
