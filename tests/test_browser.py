import pytest
from httpx import (
    ConnectError,
    HTTPStatusError,
    ProxyError,
    Request,
)

from jibsa.core.browser import (
    REFRESH_SECONDS,
    BrowserOptions,
    CertificateError,
    CorsBlockedError,
    EntryPageError,
    _BlockedResponses,
    _BrowserState,
    _FailedFetch,
    _proxy_settings,
    _to_response,
    returning_cookies,
    usable_cookies,
)
from jibsa.core.ratelimit import (
    RateLimitedError,
    RateLimiter,
    RateLimitPolicy,
)


NOW = 1_000_000.0
ENTRY = 'https://fin.land.naver.com/'


def saved(opened_ago: float, cookies: list[dict], page_url: str = 'https://fin.land.naver.com/map') -> dict:
    return {'opened_at': NOW - opened_ago, 'page_url': page_url, 'cookies': cookies}


# --- saved cookies ----------------------------------------------------------

def test_saved_cookies_are_reused_within_refresh_window() -> None:
    cookies = [
        {'name': 'NNB', 'expires': NOW + 86400},
        {'name': 'SRT5', 'expires': NOW - 1},
        {'name': 'session', 'expires': -1},
    ]
    # 만료된 쿠키만 빼고 넣는다. 세션 쿠키(expires -1)는 첫 화면을 다시 열 때까지 이어 쓴다
    assert [cookie['name'] for cookie in usable_cookies(saved(60, cookies), ENTRY, 'NNB', NOW) or []] == ['NNB', 'session']


def test_entry_page_reopens_after_refresh_window_or_without_ready_cookie() -> None:
    nnb = [{'name': 'NNB', 'expires': NOW + 86400}]
    assert usable_cookies(saved(REFRESH_SECONDS, nnb), ENTRY, 'NNB', NOW) is None
    # 시계가 뒤로 가 첫 화면을 연 시각이 미래면 믿지 않는다
    assert usable_cookies(saved(-60, nnb), ENTRY, 'NNB', NOW) is None
    assert usable_cookies(saved(60, [{'name': 'NNB', 'expires': NOW - 1}]), ENTRY, 'NNB', NOW) is None
    assert usable_cookies({}, ENTRY, 'NNB', NOW) is None
    # 업데이트로 첫 화면 출처가 바뀌면 옛 주소로 띄우지 않는다 (띄우면 다른 출처로 보고 명령이 실패했다)
    assert usable_cookies(saved(60, nnb, 'https://m.land.naver.com/map'), ENTRY, 'NNB', NOW) is None


def test_reopened_entry_page_keeps_persistent_cookies_only() -> None:
    cookies = [
        {'name': 'NNB', 'expires': NOW + 86400},
        {'name': 'SRT30', 'expires': NOW - 1},
        {'name': 'session', 'expires': -1},
    ]
    # 30분 뒤 첫 화면을 다시 열 때는 브라우저를 닫았다 다시 온 사람처럼 살아 있는 영구 쿠키만 넣는다 (넣지 않으면 NNB 가
    # 새로 발급됐다). 첫 화면 출처가 바뀌었으면 넣지 않는다
    assert [cookie['name'] for cookie in returning_cookies(saved(REFRESH_SECONDS, cookies), ENTRY, NOW)] == ['NNB']
    assert returning_cookies(saved(REFRESH_SECONDS, cookies, 'https://m.land.naver.com/map'), ENTRY, NOW) == []


# --- entry page -------------------------------------------------------------

def test_entry_429_cooldown_follows_retry_after() -> None:
    # 첫 화면 API 의 429 도 우리 요청의 429 처럼 정책 값과 Retry-After 중 긴 쪽으로 쉰다. 정책 값만 쓰면 서버가 600초
    # 쉬라고 한 사이트에 120초 뒤 다시 보냈다. 사이트 밖(광고) 응답의 Retry-After 로는 늘리지 않는다
    limiter = RateLimiter('zigbang', RateLimitPolicy(cooldown=120))
    state = _BrowserState(BrowserOptions(
        source='zigbang', entry_url='https://www.zigbang.com/', api_hosts=frozenset({'apis.zigbang.com'}),
        rate_limiter=limiter,
    ))
    state.page_url = 'https://www.zigbang.com/'
    state.on_entry_rate_limited('https://ad.doubleclick.net/pixel', '3600', main_document=False)
    state.on_entry_rate_limited('https://apis.zigbang.com/v2/app/notice', '600', main_document=False)
    with pytest.raises(RateLimitedError) as caught:
        state.finish_entry(200)
    assert 590 < caught.value.retry_after <= 600


def test_entry_server_error_keeps_saved_visitor_cookies() -> None:
    state = _BrowserState(BrowserOptions(source='naver', entry_url=ENTRY, ready_cookie='NNB'))
    state.page_url = ENTRY
    # 5xx 는 사이트 장애라 그 첫 화면의 쿠키로 덮지도, 다시 넣은 방문자 쿠키를 버리지도 않는다 (버리면 재시도가 새 NNB 를 받았다)
    assert not state.keeps_entry_cookies(503)
    with pytest.raises(HTTPStatusError):
        state.finish_entry(503)
    assert state.leave_saved and not state.discard
    # 차단 화면(4xx)은 거부된 방문자라 남기지 않고 옛 쿠키도 버린다. 429 는 쿨다운 뒤 풀렸는지 보려고 남긴다
    state.reset()
    state.page_url = ENTRY
    assert not state.keeps_entry_cookies(403)
    with pytest.raises(EntryPageError):
        state.finish_entry(403)
    assert state.discard
    assert state.keeps_entry_cookies(429) and state.keeps_entry_cookies(200)


# --- proxy ------------------------------------------------------------------

def test_proxy_settings_translate_curl_schemes_and_reject_what_chromium_cannot_use() -> None:
    assert _proxy_settings('socks5h://127.0.0.1:1080', ENTRY) == {'server': 'socks5://127.0.0.1:1080'}
    # 에러 메시지에 비밀번호를 싣지 않는다
    for proxy in ('http://user:secret@proxy:80a', 'socks5://user:secret@127.0.0.1:1080', 'ftp://user:secret@proxy:21'):
        with pytest.raises(ProxyError) as caught:
            _proxy_settings(proxy, ENTRY)
        assert 'secret' not in str(caught.value)


def test_proxy_settings_skip_scheme_only_no_proxy_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    # 개발자 셸의 프록시 변수를 지운다. urllib 은 소문자를 먼저 봐서 https_proxy 가 있으면 아래 값을 덮었다
    for name in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    # 스킴만 적은 항목은 IndexError 로 모든 명령을 INTERNAL_ERROR 로 만들었다
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy:3128')
    monkeypatch.setenv('NO_PROXY', 'localhost,http://')
    assert _proxy_settings(None, ENTRY) == {'server': 'http://proxy:3128', 'bypass': 'localhost'}


# --- failed fetch -----------------------------------------------------------

FETCH_FAILED = {'requestUrl': 'https://apis.zigbang.com/v2/search', 'error': 'TypeError', 'message': 'Failed to fetch'}


def failed_fetch(error_text: str, cors_error: str | None = None, status: int | None = None, preflight: bool = False) -> _FailedFetch:
    return _FailedFetch(error_text, cors_error, (status, {}) if status is not None else None, preflight)


def test_failed_fetch_is_classified_by_chromium_event() -> None:
    request = Request('GET', FETCH_FAILED['requestUrl'])

    def convert(failed: _FailedFetch | None) -> object:
        return _to_response(request, FETCH_FAILED, 20, {}, failed)

    # 프록시에 닿지 못한 것은 재시도하지 않는 ProxyError (남긴 쿠키로 띄우면 우리 요청에서 처음 드러난다)
    with pytest.raises(ProxyError):
        convert(failed_fetch('net::ERR_PROXY_CONNECTION_FAILED'))
    with pytest.raises(ConnectError, match='ERR_NAME_NOT_RESOLVED'):
        convert(failed_fetch('net::ERR_NAME_NOT_RESOLVED'))
    # 인증서를 믿지 못한 것도 재시도하지 않는다 (ConnectError 로 내면 3번 보낸 뒤 '네트워크 상태를 확인하라'로 끝났다)
    with pytest.raises(CertificateError):
        convert(failed_fetch('net::ERR_CERT_AUTHORITY_INVALID'))
    # CORS 에 막힌 응답은 상태로 다룬다. 2xx 는 본문이 없어 CorsBlockedError
    assert convert(failed_fetch('net::ERR_FAILED', 'MissingAllowOriginHeader', 429)).status_code == 429
    with pytest.raises(CorsBlockedError):
        convert(failed_fetch('net::ERR_FAILED', 'MissingAllowOriginHeader', 200))
    # 사전 요청(OPTIONS)만 거절됐으면 429·5xx 만 응답으로 만든다. 403 을 넘기면 '없는 ID'로 읽혔다
    assert convert(failed_fetch('net::ERR_FAILED', 'PreflightInvalidStatus', 429, preflight=True)).status_code == 429
    with pytest.raises(CorsBlockedError, match='사전 요청 HTTP 403'):
        convert(failed_fetch('net::ERR_FAILED', 'PreflightMissingAllowOriginHeader', 403, preflight=True))


def test_cors_failure_waits_for_blocked_status_event() -> None:
    # CDP 는 실패 이벤트와 받은 상태 이벤트의 순서를 정하지 않는다. 실패만 보고 멈추면 막힌 429 가 CorsBlockedError 가 됐다
    url = FETCH_FAILED['requestUrl']
    blocked = _BlockedResponses()
    blocked._on_request({'requestId': '1', 'type': 'Fetch', 'request': {'url': url}})
    blocked._on_failed({'requestId': '1', 'errorText': 'net::ERR_FAILED', 'corsErrorStatus': {'corsError': 'MissingAllowOriginHeader'}})
    assert not blocked.settled(url)
    blocked._on_response({'requestId': '1', 'statusCode': 429, 'headers': {'Retry-After': '60'}})
    assert blocked.settled(url)
    assert blocked.pop(url) == _FailedFetch('net::ERR_FAILED', 'MissingAllowOriginHeader', (429, {'Retry-After': '60'}), False)


# --- response headers -------------------------------------------------------

def test_non_ascii_response_headers_keep_server_bytes() -> None:
    # fetch 는 헤더 값을 바이트 하나당 글자 하나로 준다. 문자열 그대로 httpx 에 넣으면 UnicodeEncodeError 가 나 정상 응답이
    # PARSE_ERROR 가 됐다. Playwright 가 이미 풀어 준 값(page_headers)은 UTF-8 로 넣는다
    url = FETCH_FAILED['requestUrl']

    def convert(fetched: list[list[str]], page: dict[str, str]) -> object:
        result = {'requestUrl': url, 'url': url, 'status': 200, 'headers': fetched, 'body': ''}
        return _to_response(Request('GET', url), result, 20, {url: page}, None)

    utf8 = convert([['x-msg', '역삼동'.encode().decode('latin-1')], ['content-encoding', 'gzip']], {'x-name': '역삼동'})
    assert (utf8.headers['x-msg'], utf8.headers['x-name']) == ('역삼동', '역삼동')
    # 브라우저가 이미 푼 본문의 헤더는 뺀다
    assert 'content-encoding' not in utf8.headers
    latin1 = convert([['content-disposition', 'attachment; filename="caf\xe9.json"']], {})
    assert latin1.headers['content-disposition'] == 'attachment; filename="café.json"'
