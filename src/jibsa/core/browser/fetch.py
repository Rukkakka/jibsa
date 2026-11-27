"""브라우저 안에서 도는 fetch 스크립트, httpx 요청을 그 인자로 바꾸기, fetch 결과·CDP 이벤트를 httpx 응답으로 바꾸기."""

import base64
from collections.abc import (
    Iterable,
    Mapping,
)

from httpx import (
    ConnectError,
    ReadTimeout,
    Request,
    Response,
)

from jibsa.core.browser.errors import (
    CERT_NET_ERROR,
    PROXY_NET_ERRORS,
    CertificateError,
    CorsBlockedError,
    proxy_error,
)

from typing import (
    Any,
    NamedTuple,
)


# fetch 가 바꿀 수 없거나 브라우저 값을 그대로 쓸 헤더 (UA·Origin·Referer·쿠키·언어는 연 페이지 기준으로 브라우저가 붙인다)
BROWSER_OWNED_HEADERS: frozenset[str] = frozenset({
    'accept-charset', 'accept-encoding', 'accept-language', 'access-control-request-headers',
    'access-control-request-method', 'connection', 'content-length', 'cookie', 'cookie2', 'date', 'dnt', 'expect',
    'host', 'keep-alive', 'origin', 'referer', 'set-cookie', 'te', 'trailer', 'transfer-encoding', 'upgrade',
    'user-agent', 'via',
})
BROWSER_OWNED_HEADER_PREFIXES: tuple[str, ...] = ('proxy-', 'sec-')
# 사이트 페이지 HTML 을 받는 요청에 다는 httpx 요청 extension (`extensions={NAVIGATION_EXTENSION: True}`). 웹에서는 fetch 가
# 아니라 페이지 열기라, 크롬이 페이지를 열 때 붙이는 헤더(`BrowserState.navigation_headers`)를 붙인다 (`fetch_arguments`)
NAVIGATION_EXTENSION: str = 'jibsa_navigation'
# 브라우저가 압축을 풀어 본문을 주므로, 남겨 두면 httpx 가 한 번 더 풀려다 깨진다
DECODED_RESPONSE_HEADERS: frozenset[str] = frozenset({'content-encoding', 'content-length', 'transfer-encoding'})
# 본문이 이보다 크면 evaluate 한 번에 돌려주지 않고 브라우저 안에 두었다가 이만큼씩 나눠 읽는다 (`_handle_request`). patchright 는
# evaluate 결과가 크면 넘기는 시간이 크기보다 훨씬 빨리 는다. 같은 본문(97MB, 네트워크 없이 브라우저 안에서 만든 것)을 한 번에 넘기면
# 44초, 1MB 씩이면 2.2초, 4MB 씩 2.7초, 16MB 씩 8.4초였다 (2026-11-11 로컬 실측). jibsa 소스 응답은 작아(1초 안팎) 평소엔 한 번에
# 돌려주는 쪽만 탄다
BODY_CHUNK_BYTES: int = 1 << 20
# 브라우저 setTimeout 이 받는 가장 긴 시간(ms). 이보다 길면 기다리지 않고 바로 울린다 (2026-11-12 로컬 실측: timeout 3,000,000초는
# 0초에 ReadTimeout, 2,147,483초는 정상). `BaseHTTPClient.timeout` 은 상한이 없어 `fetch_arguments` 가 여기서 자르고, 에러
# 메시지의 초도 자른 값으로 적는다
MAX_TIMER_MS: int = 2**31 - 1
# credentials 는 fetch 기본값(same-origin)이다. 같은 출처면 쿠키가 실리고 다른 출처(다방 동 경계 CDN 등)에는 안 실린다.
# 'include' 로 두면 `Access-Control-Allow-Origin: *` 인 다른 출처 응답을 브라우저가 거절한다 (2026-11-09 다방 CDN 실측).
# redirect 는 모든 소스가 브라우저 안에서 따라간다. 'manual' 이면 fetch 가 상태 0 인 opaqueredirect 를 줘 상태·Location 을 볼
# 수 없어서, httpx 클라이언트의 follow_redirects 대로 httpx 가 따라가게 둘 수 없다. 같은 출처 redirect 는 사이트 웹처럼 따라가고
# (끝이 JSON 이 아니면 PARSE_ERROR), CORS 를 허용하지 않는 다른 출처(로그인·보안 확인 화면)로 넘기면 fetch 가 실패해
# 첫 응답(3xx)을 `BlockedResponses` 로 돌려준다. 그래서 따라가지 않던 예전 httpx 처럼 UPSTREAM_ERROR 가 된다.
# blob 을 base64 로 바꾸는 JS 함수 (FileReader 가 만든 data URL 의 쉼표 뒤). `FETCH_SCRIPT`·`BODY_SLICE_SCRIPT` 가 함께 쓴다.
# 빈 blob 도 `data:application/octet-stream;base64,` 라 빈 문자열이 된다 (2026-11-12 로컬 실측)
BLOB_BASE64_SCRIPT: str = """(blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result.slice(reader.result.indexOf(',') + 1));
  reader.onerror = () => reject(reader.error);
  reader.readAsDataURL(blob);
})"""
# requestUrl 은 브라우저가 정리한 요청 주소로, CDP 이벤트의 요청 주소와 맞춰 보는 데 쓴다.
# timeoutMs 는 응답 헤더가 올 때까지와 본문 조각 사이 간격의 제한이다 (`fetch_arguments`). 본문을 조각마다 읽어 그 사이를 잰다.
# 헤더가 늦으면 fetch 를 끊어 AbortError 다. 본문이 멈추면 이미 받은 상태·헤더에 error 'BodyTimeout' 을 붙여 돌려준다
# (`to_response` 가 3xx 이상이면 본문 없는 응답으로 만든다).
# 본문이 inlineBytes 보다 크면 본문 대신 bodyId 를 돌려주고 본문은 이 evaluate 세계의 전역(`__jibsaBodies`)에 둔다
# (`BODY_SLICE_SCRIPT` 로 읽고 `BODY_DROP_SCRIPT` 로 지운다). patchright 의 evaluate 는 사이트 JS 와 다른 격리된 세계에서 돌아
# 사이트 JS 에는 이 전역이 보이지 않는다 (2026-11-11 로컬 실측: evaluate 로 둔 전역이 페이지 main world 에서는 undefined)
FETCH_SCRIPT: str = """async ({url, method, headers, body, timeoutMs, inlineBytes}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let requestUrl = url;
  const readWithin = (reader, ms) => new Promise((resolve, reject) => {
    const idle = setTimeout(() => resolve(null), ms);
    reader.read().then(
      (chunk) => { clearTimeout(idle); resolve(chunk); },
      (error) => { clearTimeout(idle); reject(error); },
    );
  });
  const readAll = async (reader) => {
    const chunks = [];
    while (true) {
      const chunk = await readWithin(reader, timeoutMs);
      if (chunk === null) {
        reader.cancel().catch(() => {});
        return null;
      }
      if (chunk.done) return new Blob(chunks);
      chunks.push(chunk.value);
    }
  };
  const base64 = """ + BLOB_BASE64_SCRIPT + """;
  try {
    requestUrl = new URL(url, location.href).href;
    const init = {method, headers, redirect: 'follow', signal: controller.signal};
    if (body !== null) init.body = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
    const response = await fetch(url, init);
    clearTimeout(timer);
    const meta = {requestUrl, url: response.url, status: response.status, headers: [...response.headers]};
    const blob = response.body ? await readAll(response.body.getReader()) : new Blob([]);
    if (blob === null) return {...meta, error: 'BodyTimeout'};
    if (blob.size <= inlineBytes) return {...meta, body: await base64(blob)};
    const bodies = globalThis.__jibsaBodies || (globalThis.__jibsaBodies = new Map());
    globalThis.__jibsaBodyCount = (globalThis.__jibsaBodyCount || 0) + 1;
    const bodyId = String(globalThis.__jibsaBodyCount);
    bodies.set(bodyId, blob);
    return {...meta, bodyId, size: blob.size};
  } catch (error) {
    return {requestUrl, error: error.name, message: String(error.message || error)};
  } finally {
    clearTimeout(timer);
  }
}"""
# `FETCH_SCRIPT` 가 브라우저 안에 둔 본문(bodyId)의 [start, end) 바이트를 base64 로 돌려준다 (`_handle_request`). 본문이 없으면(그 사이
# 격리 세계가 바뀜) 이유가 보이게 던져 `ConnectError` 메시지에 실린다. 그냥 읽으면 `Cannot read properties of undefined` 로만
# 보였다 (2026-11-12 로컬 실측. 같은 실측에서 3MB 본문을 세 번에 나눠 읽는 동안 전역은 유지됐다)
BODY_SLICE_SCRIPT: str = """async ([bodyId, start, end]) => {
  const blob = globalThis.__jibsaBodies?.get(bodyId);
  if (!blob) throw new Error(`브라우저에 둔 응답 본문(${bodyId})이 없습니다`);
  const base64 = """ + BLOB_BASE64_SCRIPT + """;
  return base64(blob.slice(start, end));
}"""
BODY_DROP_SCRIPT: str = """(bodyId) => { globalThis.__jibsaBodies?.delete(bodyId); }"""


class _FailedFetch(NamedTuple):
    """fetch 가 `TypeError` 로만 끝난 요청을 CDP 이벤트로 본 것 (`BlockedResponses.pop`).

    Attributes:
        error_text: Chromium 네트워크 오류 (`net::ERR_PROXY_CONNECTION_FAILED` 등). fetch 의 `TypeError` 에는 없다.
        cors_error: CORS 로 막혔으면 그 이유 (`PreflightMissingAllowOriginHeader` 등), 아니면 None.
        response: 받은 첫 응답의 (상태, 헤더). 본 요청이 응답을 못 받고 CORS 사전 요청(OPTIONS)만 받았으면 그 응답.
        preflight: `response` 가 사전 요청의 응답인지.
    """

    error_text: str
    cors_error: str | None
    response: tuple[int, dict[str, str]] | None
    preflight: bool


class BlockedResponses:
    """한 탭에서 fetch 가 `TypeError` 로만 끝난 요청의 Chromium 오류와 받은 응답의 상태·헤더를 CDP 이벤트로 받아 둔다.

    fetch 는 실패 이유를 `TypeError: Failed to fetch` 하나로만 알려, 프록시에 닿지 못한 것과 CORS 에 막힌 것을 가를 수 없다.
    `Access-Control-Allow-Origin` 이 없는 다른 출처 응답(WAF 가 주는 429·5xx, 로그인 화면으로 넘기는 3xx)은 Playwright
    `response` 이벤트도 오지 않는다. CDP `Network.responseReceivedExtraInfo` 에는 받은 상태와 헤더(`Retry-After` 포함)가
    그대로 오고, `Network.loadingFailed` 에는 Chromium 오류(`errorText`)와 CORS 로 막혔는지(`corsErrorStatus`)가 온다
    (2026-11-09 로컬 실측). 그래서 막힌 429 도 요청 제한 훅이 쿨다운을 걸고, 5xx 는 재시도하며, 프록시 오류는 `ProxyError` 로 낸다.
    본문을 받다 끊긴 응답은 CORS 표시가 없어 그대로 전송 오류다.
    넘겨진(redirect) 요청은 같은 요청 ID 로 다시 오므로 요청 ID 마다 처음 주소와 첫 응답(우리가 보낸 주소의 응답)을 남긴다.
    CORS 사전 요청(OPTIONS)은 다른 요청 ID 로 오고 `initiator` 에 본 요청 ID 가 있다. 사전 요청이 거절되면 본 요청은 응답
    없이 `corsErrorStatus` 만 받으므로(같은 날 실측: 다방 동 경계 CDN 에 `csrf` 헤더를 붙이면 사전 요청 403), 사전 요청의
    응답을 본 요청에 이어 둔다.

    우리 요청은 주소로 찾으므로 탭마다 한 번에 요청 하나만 보낸다 (브라우저 스레드가 차례로 보낸다, `_BrowserThread`).
    같은 주소(당근 GraphQL 은 모두 같은 주소)로 동시에 보내면 나중 요청이 앞 요청의 ID 를 덮어, 막힌 429 를 한쪽은 받고
    한쪽은 ConnectError 로 받았다 (2026-11-09 로컬 실측: 비동기 동시 POST 두 건을 3번 보내 3번 모두).
    """

    def __init__(self) -> None:
        self._id_by_url: dict[str, str] = {}
        self._url_by_id: dict[str, str] = {}
        # 사전 요청 ID → 본 요청 ID
        self._preflight_for: dict[str, str] = {}
        self._first_response: dict[str, tuple[int, dict[str, str]]] = {}
        # 요청 ID → (Chromium 오류, CORS 로 막힌 이유)
        self._failed: dict[str, tuple[str, str | None]] = {}

    def listen(self, session: Any) -> None:
        """CDP 세션에 이벤트를 단다. 부르는 쪽이 이어서 `Network.enable` 을 보낸다."""
        session.on('Network.requestWillBeSent', self._on_request)
        session.on('Network.responseReceivedExtraInfo', self._on_response)
        session.on('Network.loadingFailed', self._on_failed)

    def _on_request(self, event: Mapping[str, Any]) -> None:
        request_id = event['requestId']
        initiator = event.get('initiator') or {}
        if initiator.get('type') == 'preflight' and initiator.get('requestId'):
            self._preflight_for[request_id] = initiator['requestId']
        if event.get('type') == 'Fetch' and request_id not in self._url_by_id:
            self._url_by_id[request_id] = event['request']['url']
            self._id_by_url[event['request']['url']] = request_id

    def _on_response(self, event: Mapping[str, Any]) -> None:
        # 요청 이벤트보다 먼저 올 수도 있어 요청 ID 로만 남긴다 (CDP 는 두 이벤트의 순서를 정하지 않는다)
        self._first_response.setdefault(event['requestId'], (event['statusCode'], dict(event.get('headers') or {})))

    def _on_failed(self, event: Mapping[str, Any]) -> None:
        cors = event.get('corsErrorStatus')
        self._failed[event['requestId']] = (
            event.get('errorText') or '', (cors.get('corsError') or 'unknown') if cors else None,
        )

    def _preflight_response(self, request_id: str) -> tuple[int, dict[str, str]] | None:
        for preflight_id, main_id in self._preflight_for.items():
            if main_id == request_id and preflight_id in self._first_response:
                return self._first_response[preflight_id]
        return None

    def settled(self, request_url: str) -> bool:
        """그 주소로 보낸 마지막 요청의 실패 이벤트가 왔고, CORS 로 막혔으면 받은 응답(상태·헤더)도 왔는지.

        CDP 는 `responseReceivedExtraInfo` 와 `loadingFailed` 의 순서를 정하지 않는다 (`_on_response`). 실패만 보고 멈추면
        막힌 429·5xx 의 상태를 놓쳐 `CorsBlockedError` 가 되고 쿨다운·재시도를 건너뛴다 (2026-11-10 리뷰). 그래서 CORS
        실패면 응답까지 기다린다. 사전 요청(OPTIONS)이 거절된 것(`corsError` 에 'Preflight' 가 든다)이면 본 요청은 나가지
        않아 사전 요청의 응답을 기다린다. 응답이 끝내 없는 CORS 실패는 부르는 쪽의 시간(`BLOCKED_RESPONSE_WAIT_SECONDS`)만큼
        더 기다리는데, 실패한 요청에서만이다.
        """
        request_id = self._id_by_url.get(request_url)
        failed = self._failed.get(request_id) if request_id is not None else None
        if request_id is None or failed is None:
            return False
        cors_error = failed[1]
        if cors_error is None:
            return True
        if 'Preflight' in cors_error:
            return self._preflight_response(request_id) is not None
        return request_id in self._first_response

    def pop(self, request_url: str) -> _FailedFetch | None:
        """그 주소로 보낸 마지막 요청의 실패 기록. 실패 이벤트가 오지 않았으면 None.

        남긴 기록은 모두 지운다. 탭마다 한 번에 요청 하나만 보내므로 남은 기록은 모두 이 요청이나 지난 요청 것이다. CORS 사전
        요청(OPTIONS)과 늦게 온 이벤트도 요청 ID 로 남아, 이 요청 것만 지우면 요청마다 쌓였다 (2026-11-09 실측: 직방 요청
        2건 뒤 `_first_response` 3개).
        """
        request_id = self._id_by_url.get(request_url)
        failed = self._failed.get(request_id) if request_id is not None else None
        result = None
        if request_id is not None and failed is not None:
            response = self._first_response.get(request_id)
            preflight = False
            if response is None:
                response = self._preflight_response(request_id)
                preflight = response is not None
            result = _FailedFetch(*failed, response=response, preflight=preflight)
        self._id_by_url.clear()
        self._url_by_id.clear()
        self._preflight_for.clear()
        self._first_response.clear()
        self._failed.clear()
        return result


def browser_owned(name: str) -> bool:
    """fetch 에 넘기지 않고 브라우저 값을 그대로 쓸 헤더인지 (`BROWSER_OWNED_HEADERS`·`BROWSER_OWNED_HEADER_PREFIXES`)."""
    lowered = name.lower()
    return lowered in BROWSER_OWNED_HEADERS or lowered.startswith(BROWSER_OWNED_HEADER_PREFIXES)


def fetch_arguments(
    request: Request, default_timeout: float, navigation_headers: Mapping[str, str],
) -> tuple[dict[str, Any], float]:
    """`FETCH_SCRIPT` 에 넘길 인자와 timeout(초). 브라우저가 정하는 헤더는 뺀다.

    헤더는 provider 가 붙인 것(사이트 웹 코드가 붙이는 헤더, 2026-11-12 소스별 실측)을 그대로 넘긴다. 페이지 HTML 요청
    (`NAVIGATION_EXTENSION`)은 그 위에 크롬이 페이지를 열 때 붙이는 헤더(`navigation_headers`)를 얹는다. 웹에서는 페이지
    열기라 `sec-fetch-mode: navigate` 등도 다르지만 `sec-*` 는 fetch 가 바꿀 수 없어 브라우저 값(`cors`)이 나간다.

    본문은 sync `read()` 로 읽는다. 비동기 transport 는 부르기 전에 `aread()` 로 읽어 둔다 (이미 읽은 본문은 그대로 준다).

    timeout 은 httpx 의 read 값을 응답 헤더가 올 때까지(CORS 사전 요청·연결 포함)와 본문 조각 사이 간격의 제한으로 쓴다. httpx 의
    읽기 제한처럼 조금씩 계속 오는 응답은 전체가 timeout 보다 길어도 받는다. 예전에는 fetch 하나 전체의 제한이라 조금씩 계속 오는
    22초짜리 응답이 20초에 `ReadTimeout` 이었다 (2026-11-10 로컬 실측). jibsa 소스 응답은 1초 안팎이라(같은 날 실측) 평소엔
    차이가 없다. client 의 timeout 을 httpx 의 timeout 과 같은 뜻으로 두려고 조각 사이로 잰다.
    요청 하나 전체의 상한은 따로 두지 않는다. 조각이 timeout 안에 끝없이 이어지는 응답은 브라우저 스레드를 Ctrl+C 까지 붙잡지만,
    예전 httpx 도 읽기 제한만 있어 같았고 jibsa 소스 응답은 1초 안팎에 끝나는 JSON 이라 그런 응답이 없다. 상한을 두면 timeout 에
    두 번째 뜻이 생긴다 (2026-11-12 리뷰에서 검토하고 그대로 둠).

    요청에 timeout 이 없으면 클라이언트의 timeout(`default_timeout`)을 쓴다. httpx 는 인증 흐름(httpx `Auth`)이 만든 요청에
    timeout 을 붙이지 않아, 고정값을 쓰면 `timeout=60` 클라이언트에서도 그 요청만 20초에 끊겼다 (2026-11-10 로컬 실측, 그때
    있던 직방 익명 토큰 요청. 예전 httpx 는 이 요청을 시간 제한 없이 기다렸다).
    read 가 None(httpx `Timeout(None)`, 무제한)이어도 무제한으로 두지 않고 클라이언트 timeout 을 쓴다. 브라우저 fetch 를
    끝없이 기다리면 그 transport 의 브라우저 스레드가 묶여 Ctrl+C 로만 풀린다. CLI 는 늘 숫자 timeout 이라(`BaseHTTPClient
    .timeout` 은 0보다 큰 수) 라이브러리에서 무제한을 준 경우만 다르다 (2026-11-10 리뷰에서 검토하고 그대로 둠).
    """
    headers = {name: value for name, value in request.headers.items() if not browser_owned(name)}
    if request.extensions.get(NAVIGATION_EXTENSION):
        headers.update(navigation_headers)
    content = request.read()
    timeout = min((request.extensions.get('timeout') or {}).get('read') or default_timeout, MAX_TIMER_MS / 1000)
    return {
        'url': str(request.url),
        'method': request.method,
        'headers': headers,
        'body': base64.b64encode(content).decode() if content else None,
        'timeoutMs': timeout * 1000,
        'inlineBytes': BODY_CHUNK_BYTES,
    }, timeout


def _response_headers(headers: Iterable[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
    """브라우저가 준 응답 헤더를 httpx 응답에 넣을 바이트 쌍으로 바꾼다. 브라우저가 이미 푼 본문의 헤더는 뺀다.

    fetch 는 헤더 값을 바이트 하나당 글자 하나(latin-1)인 문자열로 준다. 문자열 그대로 넣으면 httpx 가 ASCII 로 바꾸다
    `UnicodeEncodeError`(ValueError) 를 내, 값에 한글·é 같은 글자가 있는 헤더 하나로 정상 응답이 PARSE_ERROR 가 됐다 (예전
    httpx 전송은 받았다, 2026-11-10 리뷰·로컬 재현). latin-1 로 되돌리면 서버가 보낸 바이트 그대로다. Playwright·CDP 가 이미
    UTF-8 로 풀어 준 값처럼 latin-1 로 안 되는 글자가 있으면 UTF-8 로 넣는다. httpx 는 헤더 바이트를 ASCII·UTF-8·latin-1
    순으로 읽는다.
    """
    def raw(text: str) -> bytes:
        try:
            return text.encode('latin-1')
        except UnicodeEncodeError:
            return text.encode('utf-8')

    return [(raw(name), raw(value)) for name, value in headers if name.lower() not in DECODED_RESPONSE_HEADERS]


def _fetched_headers(result: dict[str, Any], page_headers: Mapping[str, Mapping[str, str]]) -> list[tuple[str, str]]:
    """fetch 가 받은 응답 헤더에, CORS 가 페이지 JS 에 감춘 헤더를 브라우저 `response` 이벤트의 헤더(`page_headers`)로 채운다."""
    headers = [(name, value) for name, value in result['headers']]
    shown = {name for name, _ in headers}
    return headers + [(name, value) for name, value in page_headers.get(result['url'], {}).items() if name not in shown]


def to_response(
    request: Request,
    result: dict[str, Any],
    timeout: float,
    page_headers: Mapping[str, Mapping[str, str]],
    failed: _FailedFetch | None
) -> Response:
    """`FETCH_SCRIPT` 결과를 httpx 응답으로 바꾼다. fetch 실패는 재시도 술어가 아는 httpx 예외로 낸다.

    다른 출처 응답은 CORS 가 허용한 헤더만 페이지 JS 에 보여 `Retry-After` 등이 빠진다 (직방 apis.zigbang.com 은
    `Access-Control-Expose-Headers` 가 없다, 2026-11-09 실측). 브라우저 `response` 이벤트가 받은 전체 헤더(`page_headers`,
    최종 URL 별)에서 빠진 것을 채운다.

    fetch 가 실패하면 `failed`(`BlockedResponses.pop`)로 이유를 가른다.

    - CORS 에 막혔는데 응답을 받았으면 그 상태·헤더로 본문 없는 응답을 만든다. 그러면 429 는 요청 제한 훅이, 3xx·4xx·5xx 는
      `raise_for_status` 와 재시도 술어가 예전(httpx)처럼 다룬다. 2xx 는 본문이 있어야 하는 응답이라 빈 본문으로 넘기지 않고
      `CorsBlockedError` 로 낸다 (빈 본문 200 이 성공으로 넘어갔다, 2026-11-09 로컬 실측).
    - CORS 사전 요청(OPTIONS)이 거절돼 본 요청이 나가지 못했으면, 사전 요청이 받은 429·5xx 만 응답으로 만든다 (예전 httpx 는
      사전 요청 없이 본 요청이 그 응답을 받았다). 그 밖의 사전 요청 실패는 사이트가 이 요청 헤더를 허용하지 않는 것이라
      `CorsBlockedError` 다. 사전 요청의 403·404 를 응답으로 넘기면 404·403 을 '없는 ID'로 읽는 호출부(다방 `is_missing_id`
      등)가 없는 매물로 알린다.
    - 프록시 오류(`PROXY_NET_ERRORS`)는 재시도하지 않는 `ProxyError`, 인증서
      오류(`CERT_NET_ERROR`)는 재시도하지 않는 `CertificateError`, 그 밖의 연결 실패는 Chromium 오류를 메시지에 붙인
      `ConnectError` 다. 첫 화면을 남긴 쿠키로 띄우면 서버에 묻지 않아, 프록시·인증서 오류는 우리 요청에서 처음 드러난다.
    """
    if result.get('error') == 'BodyTimeout':
        # 본문이 멈췄어도 상태·헤더는 받았다. 3xx 이상은 CORS 에 막힌 응답처럼 본문 없이 넘겨 429 는 요청 제한 훅이 Retry-After 로
        # 쿨다운을 걸고, 그 밖은 `raise_for_status`·재시도 술어가 다룬다 (예전 httpx 도 응답 훅이 본문을 읽기 전에 돌았다).
        # 2xx 는 본문이 있어야 하는 응답이라 `ReadTimeout` 이다
        if result['status'] >= 300:
            return Response(
                status_code=result['status'],
                headers=_response_headers(_fetched_headers(result, page_headers)),
                content=b'',
                request=request,
            )
        raise ReadTimeout(f'브라우저 요청의 응답 본문이 {timeout:.10g}초 동안 오지 않았습니다', request=request)
    if 'error' in result:
        if result['error'] == 'AbortError':
            raise ReadTimeout(f'브라우저 요청의 응답이 {timeout:.10g}초 안에 오지 않았습니다', request=request)
        if failed is not None and failed.cors_error is not None:
            status = failed.response[0] if failed.response is not None else None
            if failed.response is not None and status is not None and (
                status >= 300 and not failed.preflight or status == 429 or status >= 500
            ):
                return Response(
                    status_code=status,
                    headers=_response_headers(failed.response[1].items()),
                    content=b'',
                    request=request,
                )
            received = '' if status is None else f'{"CORS 사전 요청 " if failed.preflight else ""}HTTP {status} 응답, '
            raise CorsBlockedError(
                f'브라우저가 CORS 로 응답을 막았습니다 ({request.url.host}, {received}{failed.cors_error})',
                request=request,
            )
        if failed is not None and failed.error_text.startswith(PROXY_NET_ERRORS):
            raise proxy_error(failed.error_text, request)
        if failed is not None and failed.error_text.startswith(CERT_NET_ERROR):
            raise CertificateError(f'브라우저가 {request.url.host} 의 인증서를 믿지 못했습니다: {failed.error_text}', request=request)
        reason = f' ({failed.error_text})' if failed is not None and failed.error_text else ''
        raise ConnectError(f'브라우저 fetch 실패: {result["error"]}: {result["message"]}{reason}', request=request)
    return Response(
        status_code=result['status'],
        headers=_response_headers(_fetched_headers(result, page_headers)),
        # 큰 본문은 `_handle_request` 가 조각으로 읽어 `content` 에 넣었다
        content=result['content'] if 'content' in result else base64.b64decode(result['body']),
        request=request,
    )
