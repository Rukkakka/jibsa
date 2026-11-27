"""브라우저 전용 스레드와 httpx 동기·비동기 transport 본체 (`BrowserTransport`·`AsyncBrowserTransport`)."""

import asyncio
import base64
import logging
import queue
import threading
import time
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from concurrent.futures import (
    Future,
    wait,
)
from contextlib import suppress
from functools import partial

from httpx import (
    AsyncBaseTransport,
    BaseTransport,
    ConnectError,
    Request,
    Response,
)

from jibsa.core.browser.cookies import (
    EntryCookies,
    load_state,
    returning_cookies,
    usable_cookies,
)
from jibsa.core.browser.errors import (
    CERT_HINT,
    CERT_NET_ERROR,
    PROXY_HINT,
    PROXY_NET_ERRORS,
    SITE_PROXY_NET_ERRORS,
    EntryConnectError,
    EntryPageError,
    first_line,
    launch_error,
    playwright_error,
    playwright_timeout_error,
    proxy_error,
)
from jibsa.core.browser.fetch import (
    BODY_CHUNK_BYTES,
    BODY_DROP_SCRIPT,
    BODY_SLICE_SCRIPT,
    FETCH_SCRIPT,
    BlockedResponses,
    browser_owned,
    fetch_arguments,
    to_response,
)
from jibsa.core.browser.session import (
    BrowserOptions,
    BrowserState,
)

from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
)


if TYPE_CHECKING:
    from patchright.sync_api import (
        BrowserContext,
        CDPSession,
        Page,
        Route,
    )
    from patchright.sync_api import Response as PageResponse
    from scrapling.fetchers import StealthySession


logger = logging.getLogger(__name__)

_R = TypeVar('_R')
# 첫 화면 문서(DOMContentLoaded)를 기다리는 시간. 넘으면 EntryPageError(NETWORK_ERROR)
ENTRY_TIMEOUT_MS: float = 40_000
# 그 뒤 load 를 기다리는 시간. 넘어도 실패시키지 않고 그때까지 받은 쿠키로 넘어간다. load 는 사이트 밖 광고·분석 스크립트
# (구글 태그 매니저 등)까지 기다려, 그 호스트를 응답 없이 버리는 망에서는 사이트 API 가 멀쩡해도 첫 화면이 40초 뒤 실패했다
# (2026-11-09 실측: www.googletagmanager.com 을 응답 없는 주소로 돌리니 직방·당근 모두 40초 시간 초과). 정상 load 는
# 1~3초였다 (같은 날 실측: 직방 1.3초, 다방 1.9초, 당근 1.0초, 네이버 쿠키 기다림까지 3.1초)
ENTRY_LOAD_TIMEOUT_MS: float = 10_000
# 첫 화면 load 뒤 사이트 JS 가 자기 API 를 부르며 쿠키를 심는다. load 시점엔 0~6개였다가 2초 안에 8개가 다 생긴다
# (2026-11-09 fin.land.naver.com 실측). networkidle 은 쿠키가 0개일 때 끝나기도 해 기준으로 쓰지 않는다
READY_COOKIE_TIMEOUT_SECONDS: float = 5.0
READY_COOKIE_POLL_MS: float = 200
# 첫 화면에서 받지 않는 정적 파일. 쿠키는 문서와 사이트 JS·API 응답으로 생겨 이것들을 막아도 같다
# (2026-11-09 fin.land.naver.com 실측: 막아도 쿠키 8개 그대로, 정적 37건 덜 받고 load 1.8초).
# 사이트 자체 API 는 막지 않는다. 막으면 NNB·NAC 등 쿠키가 생기지 않는다 (같은 날 실측: 쿠키 1개)
BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({'image', 'font', 'media', 'stylesheet'})
BLOCKED_HOSTS: frozenset[str] = frozenset({'map.pstatic.net'})
# 위 둘을 막는 CDP Fetch 패턴 (CDP 리소스 종류는 첫 글자가 대문자다). route 로 막으면 patchright 가 CORS 사전 요청을 서버에
# 보내지 않아(`UNROUTE_BEHAVIOR`) 첫 화면 JS 가 커스텀 헤더로 부르는 사이트 API(직방 apis.zigbang.com 4건, 당근 GraphQL
# 2건 등)에 OPTIONS 가 빠졌다. CDP Fetch 는 이 패턴에 맞는 요청만 멈춰, 나머지 요청과 사전 요청은 브라우저가 그대로 보낸다
# (2026-11-10 로컬 실측: route 면 OPTIONS 없이 GET 만, Fetch 면 OPTIONS → GET, 이미지·CSS 는 둘 다 막힘)
BLOCKED_FETCH_PATTERNS: tuple[dict[str, str], ...] = (
    *({'urlPattern': '*', 'resourceType': kind.capitalize(), 'requestStage': 'Request'} for kind in sorted(BLOCKED_RESOURCE_TYPES)),
    *({'urlPattern': f'*://{host}/*', 'requestStage': 'Request'} for host in sorted(BLOCKED_HOSTS)),
)
# 서버에 묻지 않고 탭을 띄울 때 돌려주는 빈 페이지 (`_fulfill_blank`). 아이콘을 data: 로 두어 favicon 요청이 나가지 않는다
BLANK_PAGE_HTML: str = '<link rel="icon" href="data:,">'
# 본문 없는 4xx·5xx 문서에서 Chromium 이 이동(goto)을 실패시키는 오류. 응답을 돌려주지 않아 `_launch` 가 `response` 이벤트로 받아 둔
# 문서 상태로 판정한다
HTTP_RESPONSE_CODE_NET_ERROR: str = 'net::ERR_HTTP_RESPONSE_CODE_FAILURE'
# fetch 가 실패했을 때 그 요청의 CDP 이벤트(`BlockedResponses`)를 기다리는 시간. evaluate 결과보다 10ms 안쪽으로 늦게 왔다
# (2026-11-09 로컬 실측: 동기·비동기 각 30번, 바로 보면 6·10번이 아직 없었고 10ms 한 번 기다리면 모두 왔다)
BLOCKED_RESPONSE_WAIT_SECONDS: float = 1.0
BLOCKED_RESPONSE_POLL_MS: float = 10
# route 가 하나라도 걸린 탭에서는 patchright 가 CORS 사전 요청(OPTIONS)을 서버에 보내지 않고 브라우저 안에서 허용(204)으로
# 답하고 HTTP 캐시도 끈다 (patchright coreBundle.js `needsRequestInterception`). 실제 Chrome 과 달리 직방·당근 API 에
# OPTIONS 없이 본 요청만 가므로, route 는 빈 탭 띄우기(`_fulfill_blank`)에만 잠깐 쓰고 모두 걷는다. 첫 화면의 정적 파일은
# route 가 아니라 CDP Fetch 로 막는다 (`BLOCKED_FETCH_PATTERNS`)
# (2026-11-09 로컬 실측: route 가 있으면 사전 요청을 403 으로 거절하는 서버에도 본 요청이 200, 걷으면 OPTIONS 가 간다)
UNROUTE_BEHAVIOR: Literal['ignoreErrors'] = 'ignoreErrors'

# 브라우저 스레드의 일이 끝나기를 기다리며 Ctrl+C 를 확인하는 간격 (`BrowserTransport._wait`). 끝까지 한 번에 기다리면
# Windows 에서는 그 기다림(lock)이 Ctrl+C 로 끊기지 않는다. 일이 끝나면 바로 돌아와 요청이 늦어지지는 않는다
WAIT_POLL_SECONDS: float = 0.1


class _BrowserThread:
    """한 transport(비동기 transport 가 감싼 것 포함)의 브라우저 일을 받은 차례대로 하는 데몬 스레드.

    patchright 동기 API 는 asyncio 루프가 도는 스레드에서 부를 수 없고, 부를 때마다 그 스레드에 자기 asyncio 루프를 '도는
    루프'로 남기며, 한 번 띄운 브라우저는 띄운 스레드에서만 다룰 수 있다 (2026-11-09 실측: 남은 루프 때문에 같은 스레드에서
    `asyncio.run` 이 실패하고 다른 소스의 브라우저를 띄우지 못했다). 그래서 브라우저 일은 늘 이 스레드에서만 한다. 부른
    스레드에는 아무것도 남지 않아 CLI 메인 스레드, asyncio 루프 안(Jupyter), 여러 작업 스레드 어디서 불러도 같다.
    예전에는 CLI 메인 스레드에서 바로 부르고 남은 루프를 asyncio 비공개 함수(`_set_running_loop`)로 걷어 냈다.

    데몬 스레드라 프로세스가 끝날 때 기다리지 않는다. Ctrl+C 로 끊긴 명령은 하던 브라우저 일(첫 화면이면 Chromium 띄우기에 문서 40초·load 10초·쿠키 5초까지)을 기다리지
    않고 바로 끝나고, 드라이버(node)는 파이프가 끊기면 Chromium 을 닫고 끝난다.
    """

    def __init__(self) -> None:
        self._jobs: queue.SimpleQueue[tuple[Callable[..., Any], tuple[Any, ...], Future[Any]] | None] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, name='jibsa-browser', daemon=True)
        self._thread.start()

    @property
    def ident(self) -> int | None:
        return self._thread.ident

    def _run(self) -> None:
        while (job := self._jobs.get()) is not None:
            function, args, future = job
            # 차례를 기다리는 사이 취소된 일(비동기 요청의 `asyncio.wait_for` 시간 초과 등, `AsyncBrowserTransport.handle_async_request`)은 돌리지
            # 않는다. 돌리면 아무도 기다리지 않는 요청을 사이트로 보내고, 취소된 Future 에 결과를 넣다 InvalidStateError 로 이
            # 스레드가 끝난다. 돌기 시작한 일은 취소되지 않는다
            if future.set_running_or_notify_cancel():
                try:
                    result = function(*args)
                except BaseException as error:
                    # 부른 스레드가 `future.result()` 로 그대로 받는다
                    future.set_exception(error)
                else:
                    future.set_result(result)
            # 다음 일을 기다리는 동안 마지막 일(transport 의 메서드)을 붙잡으면 닫지 않은 transport 가 메모리에서 정리되지
            # 않았다 (2026-11-10 리뷰). 브라우저 자체는 닫아야 끝난다 (`BrowserTransport` docstring)
            del job, function, args, future
            result = None

    def submit(self, function: Callable[..., _R], *args: Any) -> 'Future[_R]':
        future: Future[_R] = Future()
        self._jobs.put((function, args, future))
        return future

    def stop(self) -> None:
        """앞에 넣은 일을 마치면 스레드를 끝낸다."""
        self._jobs.put(None)


class BrowserTransport(BaseTransport):
    """사이트 첫 화면을 연 브라우저 페이지에서 요청을 `fetch` 로 보낸다 (동기 `Client` 용).

    닫아야(`close`, 클라이언트의 `with`) 브라우저 스레드와 Chromium 이 끝나고 쿠키가 남는다. 닫지 않으면 프로세스가 끝날
    때까지 남는다. 메모리에서 정리될 때 자동으로 닫지는 않는다 (브라우저 일은 브라우저 스레드에서만 할 수 있어서다).

    Args:
        options: 설정 (`BrowserOptions`).
    """

    def __init__(self, options: BrowserOptions) -> None:
        self._state = BrowserState(options)
        self._session: StealthySession | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        # 탭마다 CORS 에 막힌 응답 기록
        self._blocked: dict[Page, BlockedResponses] = {}
        # 브라우저 일을 하는 스레드. 첫 브라우저 일 때 `_submit` 이 띄운다
        self._thread: _BrowserThread | None = None
        # `_thread`·`_closed` 와 일 넣기를 함께 지킨다. 넣기를 잠금 밖에서 하면 다른 스레드의 close 가 넣은 끝 표시 뒤에 들어가
        # 영영 돌지 않고 기다림이 멈췄다 (2026-11-10 리뷰)
        self._thread_lock = threading.Lock()
        self._closed = False
        # 기다리다 Ctrl+C·비동기 취소로 끊긴 브라우저 일 (`_abandon`). 그중 아직 도는 일이 있으면 `close` 가 기다리지 않는다
        self._abandoned: list[Future[Any]] = []

    def _submit(self, function: Callable[..., _R], *args: Any) -> 'Future[_R]':
        """브라우저 일을 이 transport 의 브라우저 스레드(`_BrowserThread`)에 넣는다.

        브라우저 스레드는 `_handle_request`·`_close` 만 돌리고 둘 다 요청을 다시 보내지 않아, 이 함수를 브라우저 스레드에서
        부르는 일은 없다. 예전 `_call` 이 모든 브라우저 일을 이 길로 넘길 때는 자기를 기다려 멈춘 적이 있어(2026-11-09 실측)
        그때는 막아 두었다 (2026-11-23 리뷰로 지움).

        Raises:
            RuntimeError: 닫은 뒤에 불렸을 때. httpx 가 닫힌 클라이언트에 내는 것과 같다. 여러 스레드가 같이 쓰다 한 스레드가
                닫은 경우이고, 닫힌 transport 에 브라우저를 다시 띄우지 않는다.
        """
        with self._thread_lock:
            if self._closed:
                raise RuntimeError('닫힌 클라이언트로는 요청할 수 없습니다 (브라우저를 이미 닫았습니다)')
            if self._thread is None:
                self._thread = _BrowserThread()
            return self._thread.submit(function, *args)

    def _wait(self, future: 'Future[_R]') -> _R:
        """브라우저 스레드의 일이 끝나기를 기다린다. Ctrl+C 를 `WAIT_POLL_SECONDS` 마다 확인한다.

        기다리다 Ctrl+C 로 끊기면 브라우저 일은 그대로 두고 바로 돌아간다. patchright 객체는 브라우저 스레드에서만 다룰 수
        있어 다른 스레드에서 끊을 수 없다. 그 뒤의 `close` 는 그 일이 아직 돌고 있으면 기다리지 않는다 (`_abandon`).
        """
        try:
            while not future.done():
                wait((future,), timeout=WAIT_POLL_SECONDS)
        except BaseException:
            self._abandon(future)
            raise
        return future.result()

    def _abandon(self, future: 'Future[Any]') -> None:
        """기다리다 끊긴(Ctrl+C·비동기 취소) 브라우저 일을 남긴다. 이미 끝난 일은 걷어 낸다.

        켜고 끄는 표시로 두었을 때는 끊긴 일이 끝난 뒤에도 다음 일이 성공해야만 꺼져, 다음 일이 에러로 끝나거나 더 부르지 않으면
        아무 일도 돌지 않는데 `close` 가 닫기를 기다리지 않았다. 비동기 클라이언트는 닫기 전에 프로세스가 끝나 쿠키를 남기지도,
        403 으로 정한 버리기를 하지도 못했다 (2026-11-10 리뷰 재현: 시간 초과 뒤 에러·시간 초과 뒤 요청 없음에서 `aclose` 0초).
        일마다 끝났는지 보므로, 다른 일이 끝났다고 아직 도는 끊긴 일을 기다리지도 않는다.
        """
        with self._thread_lock:
            self._abandoned = [job for job in self._abandoned if not job.done()] + [future]

    def _open_page(self) -> 'Page':
        if self._page is not None:
            return self._page
        self._state.raise_if_entry_failed()
        try:
            return self._launch()
        except Exception as error:
            self._state.remember_if_fatal(error)
            raise

    def _watch_blocked(self, context: 'BrowserContext', page: 'Page') -> None:
        """탭의 막힌 응답(`BlockedResponses`)을 받아 두고, 우리 요청의 CORS 사전 요청을 요청 제한에 센다 (`count_preflight`)."""
        blocked = BlockedResponses()
        session = context.new_cdp_session(page)
        blocked.listen(session)
        _count_preflights(session, self._state)
        session.send('Network.enable')
        self._blocked[page] = blocked

    def _launch(self) -> 'Page':
        # 모듈 docstring 대로 브라우저를 쓸 때만 불러온다
        from scrapling.fetchers import StealthySession

        state = self._state
        state.reset()
        started = time.perf_counter()
        saved = load_state(state.options.source)
        cookies: Sequence[Mapping[str, Any]] | None = usable_cookies(
            saved, state.options.entry_url, state.options.ready_cookie, time.time(),
        )
        from_saved = cookies is not None
        entry_status: int | None = None
        entry_document_retry_after: str | None = None
        self._session = StealthySession(**state.session_options())

        # 첫 화면 탭의 main frame 문서가 받은 마지막 4xx·5xx (상태, Retry-After). 본문 없는 4xx·5xx 문서면 goto 가 응답을 돌려주지 않고
        # 실패해(`HTTP_RESPONSE_CODE_NET_ERROR`) 이 값으로 첫 화면을 판정한다 (아래 `except` 갈래). 리다이렉트 뒤의 문서면 마지막 것이 남는다
        failed_document: list[tuple[int, str | None]] = []

        def on_entry_response(response: 'PageResponse') -> None:
            if response.status < 400:
                return
            # 첫 화면 탭의 main frame 문서 응답인지 본다 (iframe 광고 문서는 아니다). 드라이버에 묻지 않는 속성만 본다.
            # `response` 이벤트 리스너 안이라 예외를 내지 않는다 (`count_preflight` 와 같은 이유). patchright 의 `request.frame`
            # 은 서비스 워커 요청과 frame 이 생기기 전에 보낸 이동 요청(새 창의 첫 이동)에서 Error 를 낸다. 첫 화면 탭에서는
            # 생기지 않지만 (`session_options` 의 서비스 워커 주석) 생기면 main frame 문서가 아니라고 본다 (2026-11-10 리뷰)
            request = response.request
            try:
                main_document = request.is_navigation_request() and request.frame.parent_frame is None
            except playwright_error():
                main_document = False
            retry_after = response.headers.get('retry-after')
            if main_document:
                failed_document[:] = [(response.status, retry_after)]
            if response.status == 429:
                state.on_entry_rate_limited(response.url, retry_after, main_document)

        try:
            self._session.start()
            context: BrowserContext = self._session.context
            page = context.new_page()
        except (playwright_error(), OSError) as error:
            # OSError: patchright 드라이버(node)를 실행하지 못했다 (실행 권한 없음·지워짐·보안 프로그램이 막음). 잡지 않으면
            # INTERNAL_ERROR 에 asyncio 'Future exception was never retrieved' traceback 이 stderr 로 더 나갔다 (2026-11-09 실측)
            self._close()
            raise launch_error(error) from error
        except BaseException:
            # 그 밖의 이유로 끝나도 띄운 브라우저를 남기지 않는다. 남기면 다음 `_launch` 가 `_session` 을 덮어
            # Chromium 이 프로세스가 끝날 때까지 남았다 (2026-11-10 리뷰). 아래 두 블록도 같다
            self._close()
            raise
        # 사이트 첫 화면 문서를 기다리는 중인지. 그때의 시간 초과만 첫 화면 실패다 (`_entry_error`)
        opening_entry = False
        try:
            page.on('request', lambda page_request: state.count_request(page_request.resource_type, page_request.url))
            if cookies is not None:
                state.page_url, state.opened_at = saved['page_url'], saved['opened_at']
                try:
                    # add_cookies 는 SetCookieParam(TypedDict)을 받는데 patchright 가 그 타입을 공개하지 않는다 (`_impl` 에만
                    # 있다). 쿠키는 jibsa 가 남긴 JSON 이라 Mapping 이고, 내부 모듈을 import 해 cast 하면 patchright 를 올릴 때
                    # 깨질 수 있어 오류 코드를 붙여 둔다. 아래 returning 도 같다
                    context.add_cookies(cookies)  # type: ignore[arg-type]
                except playwright_error():
                    # 브라우저가 남긴 쿠키를 받지 않으면 다음 시도·명령도 같으니 버린다. 재시도는 첫 화면부터 연다. 버리는 것은
                    # 이때뿐이다. 빈 페이지 띄우기의 시간 초과처럼 브라우저가 잠깐 멈춘 실패에 버리면 멀쩡한 쿠키를 버리고
                    # 재시도가 첫 화면부터 열었다 (2026-11-10 리뷰: 한 번 일부러 시간 초과를 내니 파일이 지워지고 첫 화면을 다시 엶)
                    state.discard_saved(saved['opened_at'])
                    raise
                how = '남긴 쿠키'
            else:
                returning = returning_cookies(saved, state.options.entry_url, time.time())
                if returning:
                    try:
                        context.add_cookies(returning)  # type: ignore[arg-type]  # 위 남긴 쿠키와 같은 이유
                    except playwright_error() as error:
                        # 브라우저가 받지 않으면 빈 채로 연다. 첫 화면을 연 뒤 남기는 쿠키가 이 쿠키를 덮는다
                        logger.warning('남긴 방문자 쿠키를 넣지 못해 빈 채로 엽니다: %s', first_line(error))
                        returning = []
                static = _watch_entry(context, page, state)
                page.on('response', on_entry_response)
                opening_entry = True
                response = page.goto(state.options.entry_url, wait_until='domcontentloaded', timeout=ENTRY_TIMEOUT_MS)
                opening_entry = False
                entry_status = response.status if response else None
                entry_document_retry_after = response.headers.get('retry-after') if response else None
                # 첫 화면 문서가 4xx·5xx 면 load·ready_cookie 를 기다리지 않고 바로 `finish_entry` 로 멈춘다. 기다리면 그동안
                # 막힌 사이트에 페이지 요청이 더 나가고, 오류 화면이 심지 않는 ready_cookie 를 5초 기다렸다 (2026-11-10 로컬
                # 실측: 503 첫 화면이 ready_cookie 가 있으면 5.6초, 없으면 0.5초에 실패). 첫 화면 API 가 429 를 받았을
                # 때(`entry_429`)도 같은 이유로 쿠키를 더 기다리지 않는다
                entry_failed = entry_status is not None and entry_status >= 400
                if not entry_failed:
                    try:
                        page.wait_for_load_state('load', timeout=ENTRY_LOAD_TIMEOUT_MS)
                    except playwright_timeout_error():
                        logger.info(
                            '첫 화면(%s) load 가 %g초 안에 끝나지 않아 기다리지 않고 넘어갑니다 (사이트 밖 스크립트가 늦을 수 있음)',
                            state.options.entry_url, ENTRY_LOAD_TIMEOUT_MS / 1000,
                        )
                cookies = context.cookies()
                deadline = time.monotonic() + READY_COOKIE_TIMEOUT_SECONDS
                # 시간 안에 다 심지 않아도 멈추지 않고 이 쿠키로 요청한다. ready_cookie 가 없으면 남긴 쿠키는 다음 명령이 쓰지
                # 않아 첫 화면을 다시 연다 (`usable_cookies`)
                entry_cookies = EntryCookies(state.options.ready_cookie, returning)
                while (
                    not entry_failed and not state.entry_429 and not entry_cookies.ready(cookies, time.monotonic())
                    and time.monotonic() < deadline
                ):
                    page.wait_for_timeout(READY_COOKIE_POLL_MS)
                    cookies = context.cookies()
                static.detach()
                page.remove_listener('response', on_entry_response)
                state.page_url, state.opened_at = page.url, time.time()
                how = f'첫 화면 HTTP {entry_status or "-"}, 페이지 요청 {state.routed}건, 이어 쓴 쿠키 {len(returning)}개'
            # 마지막으로 연 페이지 주소를 서버에 묻지 않고 브라우저 안에서 빈 페이지로 띄운다 (Referer 가 그 주소다). 새로 연
            # 첫 화면도 쿠키를 다 받은 뒤 빈 페이지로 바꿔, 명령 동안 사이트 JS 가 API·지도 타일을 더 부르지 않게 한다
            page.route(lambda url: url == state.page_url, partial(_fulfill_blank, state))
            page.goto(state.page_url, wait_until='commit')
            page.unroute_all(behavior=UNROUTE_BEHAVIOR)
            self._watch_blocked(context, page)
        except BaseException as error:
            if (
                opening_entry and failed_document and isinstance(error, playwright_error())
                and HTTP_RESPONSE_CODE_NET_ERROR in first_line(error)
            ):
                # 본문 없는 4xx·5xx 첫 화면 문서라 goto 가 응답 대신 오류를 냈다. 받아 둔 문서 상태로 본문이 있을 때와 같이
                # 판정한다 (403 은 `blocked`·옛 쿠키 버리기, 429 는 쿨다운, 5xx 는 Retry-After 대로 재시도). 판정하지 않으면
                # 연결 오류(`EntryConnectError`)로 보고 브라우저를 새로 띄워 첫 화면을 세 번 열고 `NETWORK_ERROR` 로 안내했다
                # (2026-11-24 확인: 가짜 첫 화면으로 재현). `finish_entry` 가 첫 화면 요청을 요청 제한에 남기므로
                # (`record_entry_requests`) 따로 부르지 않는다. `_context` 를 `_close` 보다 먼저 둔다: `_close` 는 컨텍스트가
                # 있을 때만 `finish` 를 불러 `finish_entry` 가 켠 `discard` 대로 옛 쿠키 파일을 지우는데, 두지 않으면 거부된
                # 방문자 쿠키 파일이 남는다. `opened_at` 도 둔다: 새로 여는 갈래는 goto 가 성공한 뒤에야 넣어 여기서는 0 이고,
                # 0 이면 `discard_saved` 가 옛 쿠키 파일을 다른 프로세스가 새로 연 것으로 여겨 지우지 않는다. 쿠키는 남기지
                # 않는다 (본문이 없어 첫 화면 JS 가 돌지 않았고 `page_url` 이 비어 `finish` 가 남기지 않는다). `finish_entry` 는
                # 상태가 400 이상이면 모든 갈래에서 예외를 내므로 이 갈래는 늘 아래 `raise` 로 끝난다
                status, retry_after = failed_document[0]
                self._context = context
                state.opened_at = time.time()
                try:
                    state.finish_entry(status, retry_after)
                except BaseException as entry_error:
                    self._close()
                    raise entry_error from error
            self._close()
            state.record_entry_requests()
            if not isinstance(error, playwright_error()):
                raise
            raise _entry_error(error, state.options.entry_url, opening_entry) from error
        # 탭(`_page`)은 첫 화면이 제대로 열린 것을 확인한 뒤에 내놓는다. 컨텍스트는 실패했을 때 `_close` 가 쿠키를 버리도록
        # 먼저 둔다 (`finish`)
        self._context = context
        if not from_saved and state.keeps_entry_cookies(entry_status):
            # 새로 연 첫 화면의 쿠키는 확인(`finish_entry`) 전에 바로 남긴다. 같은 명령 안에서 새로 만든 같은 소스 클라이언트가
            # 첫 화면을 다시 열지 않게 하고, 429 로 멈춰도 쿨다운 뒤 남긴 쿠키로 요청 1건만 보내 풀렸는지
            # 보게 한다 (본문 없는 429 첫 화면은 goto 가 실패해 위 `except` 갈래로 가므로 쿠키를 남기지 않는다). 확인 뒤에
            # 남겼을 때는 쿠키 파일이 없던 상태(첫 실행, 403 으로 버린 뒤)에서 429 로 멈추면 `finish` 가
            # 파일이 없다고 남기지 않았다 (2026-11-10 리뷰). 4xx·5xx·다른 출처면 남기지 않는다 (`keeps_entry_cookies`). 4xx·다른
            # 출처는 `finish_entry` 가 discard 를 켜 `_close` 가 옛 파일을 지우고, 5xx 는 옛 파일을 그대로 둔다(`leave_saved`).
            # 명령이 끝날 때(`close`) 그때의 쿠키로 다시 남긴다
            state.save(cookies)
        try:
            state.finish_entry(entry_status, entry_document_retry_after)
        except BaseException:
            self._close()
            raise
        self._page = page
        state.log_opened(started, how, cookies)
        return page

    def handle_request(self, request: Request) -> Response:
        # 브라우저 일을 브라우저 스레드에서 부르고 끝나기를 기다린다 (`_submit`, `_wait`)
        return self._wait(self._submit(self._handle_request, request))

    def _handle_request(self, request: Request) -> Response:
        # 모든 요청을 첫 화면 탭에서 보낸다. 예전에는 첫 화면 출처의 CORS 를 허용하지 않는 호스트(당근 옛 지역 API)를 그 주소의
        # 빈 탭에서 보내는 '출처 탭' 장치가 있었는데, 쓰던 API 를 뺀 뒤 쓰는 소스가 없어 지웠다 (#215, 2026-11-12)
        page = self._open_page()
        arguments, timeout = fetch_arguments(request, self._state.options.timeout, self._state.navigation_headers)
        self._state.on_send(str(request.url))
        page_headers: dict[str, dict[str, str]] = {}

        def on_page_response(page_response: 'PageResponse') -> None:
            if page_response.request.resource_type == 'fetch':
                page_headers[page_response.url] = page_response.headers

        try:
            blocked = self._blocked[page]
            page.on('response', on_page_response)
            try:
                result = page.evaluate(FETCH_SCRIPT, arguments)
                deadline = time.monotonic() + BLOCKED_RESPONSE_WAIT_SECONDS
                while (
                    result.get('error') == 'TypeError' and not blocked.settled(result['requestUrl'])
                    and time.monotonic() < deadline
                ):
                    page.wait_for_timeout(BLOCKED_RESPONSE_POLL_MS)
                if 'bodyId' in result:
                    # `FETCH_SCRIPT` 가 브라우저 안에 둔 큰 본문을 `BODY_CHUNK_BYTES` 씩 읽고 브라우저 안의 것은 지운다
                    body_id = result.pop('bodyId')
                    size = result['size']
                    try:
                        result['content'] = b''.join(
                            base64.b64decode(
                                page.evaluate(BODY_SLICE_SCRIPT, [body_id, start, min(start + BODY_CHUNK_BYTES, size)])
                            )
                            for start in range(0, size, BODY_CHUNK_BYTES)
                        )
                    finally:
                        # 읽다 실패해도 지운다. 탭이 이미 닫혔으면 본문도 함께 사라졌다
                        with suppress(playwright_error()):
                            page.evaluate(BODY_DROP_SCRIPT, body_id)
            finally:
                page.remove_listener('response', on_page_response)
        except playwright_error() as error:
            # 탭·브라우저가 닫혔으면 다시 써도 같은 에러다. 큰 본문을 나눠 읽다가 본문이 없어졌으면 탭은 살아 있어도
            # 페이지가 다른 곳으로 넘어가 evaluate 세계가 바뀐 것이라, 이 탭이 아직 첫 화면인지 알 수 없다. 어느 쪽이든 닫고 재시도에서
            # 남긴 쿠키로 다시 띄운다 (2026-11-12 리뷰에서 검토하고 그대로 둠)
            self._close()
            raise ConnectError(f'브라우저 요청 실패: {first_line(error)}', request=request) from error
        response = to_response(request, result, timeout, page_headers, blocked.pop(result['requestUrl']))
        self._state.on_response(response.status_code)
        return response

    def close(self) -> None:
        """브라우저를 닫는다. 브라우저 스레드가 앞의 일을 마친 뒤 닫고(쿠키를 남기고) 끝나며, 그때까지 기다린다.

        기다리다 Ctrl+C·비동기 취소로 끊긴 브라우저 일이 아직 돌고 있으면 기다리지 않는다 (`_abandon`). CLI 는 바로 끝나 그
        명령에서 바뀐 쿠키는 남지 않는다 (첫 화면을 새로 열었으면 연 즉시 남겼다). 오래 도는 프로세스(Jupyter)에서는 브라우저
        스레드가 하던 일을 마친 뒤 닫는다.
        """
        with self._thread_lock:
            thread, self._thread = self._thread, None
            self._closed = True
            if thread is None:
                return
            # 브라우저 스레드에서 `close` 를 부르는 곳은 없다 (`_submit` 과 같다. 2026-11-23 리뷰로 재진입 갈래를 지움)
            future = thread.submit(self._close)
            thread.stop()
        if not any(not job.done() for job in self._abandoned):
            self._wait(future)

    def _close(self) -> None:
        session, context = self._session, self._context
        self._session = self._context = self._page = None
        self._blocked.clear()
        if session is None:
            return
        try:
            if context is not None:
                cookies: Sequence[Mapping[str, Any]] | None = None
                try:
                    cookies = context.cookies()
                except Exception as error:
                    # 브라우저가 이미 죽었으면(메모리 부족·강제 종료) 쿠키를 읽지 못한다. 그래도 finish 는 불러 403 으로 정한
                    # 버리기와 더 나간 요청 수를 남긴다. 한 줄로 부르면 finish 가 불리지 않아 거부된 쿠키 파일이 남고, 재시도와
                    # 다음 명령들이 그 쿠키를 이어 썼다 (2026-11-10 리뷰: Chromium 을 강제 종료해 재현)
                    logger.warning('브라우저 쿠키를 읽지 못했습니다: %s', first_line(error))
                self._state.finish(cookies)
        except Exception as error:
            logger.warning('브라우저 쿠키를 정리하지 못했습니다: %s', error)
        finally:
            with suppress(Exception):
                session.close()


class AsyncBrowserTransport(AsyncBaseTransport):
    """`BrowserTransport` 의 비동기판 (`AsyncClient` 용). 감싼 동기 transport 의 브라우저 스레드에 일을 넘기고 `await` 로 기다린다.

    흐름(첫 화면 열기·요청 보내기)은 동기 transport 와 한 벌이다 (`AsyncBrowserTransport.handle_async_request`). 동시에 보낸 요청
    (`asyncio.gather`)은 브라우저 스레드가 받은 차례대로 하나씩 보낸다. 예전에는 같은 흐름을 patchright 비동기 API 로 따로 두어
    고칠 때마다 함께 맞춰야 했고(리뷰에서 찾은 버그도 두 벌에 함께 있었다) 동시성 잠금을 따로 두었다 (2026-11-10 리뷰로 합침).
    탭이 하나라 차례로 보내도 요청 제한 간격(0.5초) 때문에 실제 요청에서는 차이가 없다 (같은 날 가짜 사이트 실측: 8건, 응답
    300ms 에 3.81초).

    설정은 감쌀 동기 transport 를 만들 때 준다 (`AsyncBrowserTransport(BrowserTransport(BrowserOptions(...)))`). 예전에는 동기
    transport 의 인자를 시그니처·docstring 째 베껴 위치 인자로 넘겨, 인자를 더하거나 순서를 바꾸면 세 곳을 함께 고쳐야 했고 같은
    타입이 이어지는 자리에서 어긋나도 타입 검사가 잡지 못했다.

    Args:
        transport: 감쌀 동기 transport. 이 transport 를 닫으면(`aclose`) 함께 닫힌다.
    """

    def __init__(self, transport: BrowserTransport) -> None:
        self._sync = transport

    async def handle_async_request(self, request: Request) -> Response:
        # 비동기 본문(async iterator)은 브라우저 스레드에서 sync read() 로 읽을 수 없어 먼저 읽어 둔다. 읽은 본문은
        # `fetch_arguments` 가 쓴다
        await request.aread()
        # `BrowserTransport.handle_request` 의 비동기판이다. 브라우저 스레드의 일을 이벤트 루프를 막지 않고 기다린다.
        # 기다리다 취소되면(`asyncio.wait_for` 시간 초과 등) Ctrl+C 를 받은 `_wait` 처럼 하던 브라우저 일은 그대로 두고 바로
        # 돌아가고, 그 뒤의 `close` 는 그 일이 아직 돌고 있으면 기다리지 않는다 (`_abandon`). 아직 차례를 기다리던 일은 돌리지
        # 않는다 (`_BrowserThread._run`). 작업 스레드(`asyncio.to_thread`)에서 `BrowserTransport.handle_request` 로 기다리면
        # 취소돼도 그 스레드가 브라우저 일을 끝까지 기다려, 닫기와 `asyncio.run` 이 그만큼(첫 화면이면 Chromium 띄우기에 문서 40초·load 10초·쿠키 5초까지) 늦었다
        # (2026-11-10 리뷰: 8초 걸리는 첫 화면에서 `aclose` 8.04초)
        future = self._sync._submit(self._sync._handle_request, request)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            self._sync._abandon(future)
            raise

    async def aclose(self) -> None:
        # 닫기는 브라우저 스레드가 쿠키를 남기고 브라우저를 닫을 때까지 기다리므로 작업 스레드에서 해 이벤트 루프를 막지 않는다
        await asyncio.to_thread(self._sync.close)


def _entry_error(error: Exception, entry_url: str, opening_entry: bool) -> Exception:
    """첫 화면 탭을 준비하다 난 patchright 에러를 재시도 술어가 아는 에러로 바꾼다. 모두 첫 화면 단계 실패(`EntryOpenError`)다.

    사이트 첫 화면 문서를 기다리다 난 시간 초과(`opening_entry`)는 `EntryPageError`, 프록시에 닿지 못한 것은
    `ProxyError`, 프록시가 이 사이트만 거절한 것은 `EntryPageError`(NETWORK_ERROR, 프록시 hint), 인증서를 믿지
    못한 것(`net::ERR_CERT_*`)은 `EntryPageError`(NETWORK_ERROR, `CERT_HINT`)로 낸다. 모두 다시 열어도 같아 재시도하지
    않는다. 그 밖의 시간 초과(서버에 묻지 않고 띄우는 빈 페이지, 쿠키 넣기 등)는 사이트가 아니라
    브라우저가 멈춘 것이라 다른 연결 실패처럼 재시도하는 `EntryConnectError` 다. 재시도는 브라우저를 새로 띄운다. 첫 화면
    시간 초과로 내면 60초 동안 기억돼(`remember_if_fatal`) 다시 띄우면 됐을 실패를 '첫 화면을 40초 안에 열지 못했다'로 잘못
    알렸다 (2026-11-10 리뷰).

    본문 없는 4xx·5xx 첫 화면 문서(`HTTP_RESPONSE_CODE_NET_ERROR`)는 `_launch` 가 받아 둔 문서 상태로 `finish_entry` 를 불러
    판정하므로 보통 여기로 오지 않는다. 받아 둔 문서가 없을 때만 마지막 줄의 `EntryConnectError` 가 된다.
    """
    line = first_line(error)
    if isinstance(error, playwright_timeout_error()):
        if opening_entry:
            return EntryPageError(
                code='NETWORK_ERROR',
                message=f'브라우저로 첫 화면({entry_url})을 {ENTRY_TIMEOUT_MS / 1000:g}초 안에 열지 못했습니다: {line}',
                hint='사이트가 느리거나 네트워크·프록시가 막혔을 수 있습니다. 잠시 뒤 한 번만 다시 부르고, 같으면 다른 소스를 쓰세요',
            )
        return EntryConnectError(f'브라우저 탭을 준비하다 시간이 초과됐습니다: {line}')
    if any(code in line for code in SITE_PROXY_NET_ERRORS):
        return EntryPageError(
            code='NETWORK_ERROR',
            message=f'프록시가 첫 화면({entry_url}) 연결을 거절했습니다: {line}',
            hint=PROXY_HINT,
        )
    if any(code in line for code in PROXY_NET_ERRORS):
        return proxy_error(line)
    if CERT_NET_ERROR in line:
        return EntryPageError(
            code='NETWORK_ERROR',
            message=f'브라우저가 첫 화면({entry_url})의 인증서를 믿지 못했습니다: {line}',
            hint=CERT_HINT,
        )
    return EntryConnectError(f'브라우저로 첫 화면을 열지 못했습니다: {line}')


def _count_preflights(session: 'CDPSession', state: 'BrowserState') -> None:
    """CDP 세션의 `Network.requestWillBeSent` 중 CORS 사전 요청(OPTIONS)을 요청 제한에 센다 (`BrowserState.count_preflight`).

    사전 요청 표식은 `BlockedResponses._on_request` 와 같다. `Network.enable` 은 부르는 쪽이 보낸다.
    """

    def on_request(event: dict[str, Any]) -> None:
        initiator = event.get('initiator') or {}
        if initiator.get('type') == 'preflight':
            state.count_preflight(event['request']['url'])

    session.on('Network.requestWillBeSent', on_request)


def _watch_entry(context: 'BrowserContext', page: 'Page', state: 'BrowserState') -> 'CDPSession':
    """첫 화면을 여는 동안 정적 파일을 CDP Fetch 로 막고(`BLOCKED_FETCH_PATTERNS`), 첫 화면 JS 가 보낸 CORS 사전 요청을
    요청 제한에 센다 (`BrowserState.count_preflight`). 첫 화면을 다 연 뒤 `detach` 한다."""
    session = context.new_cdp_session(page)

    def fail(event: dict[str, Any]) -> None:
        # 떼는(`detach`) 사이에 온 요청은 답할 세션이 없다. 그 에러를 두면 patchright 가 traceback 을 stderr 로 내보냈다
        # (2026-11-10 다방 실측). 떼면 Chromium 이 멈춘 요청을 풀어 주고, 첫 화면은 곧 빈 페이지로 바뀐다
        with suppress(playwright_error()):
            session.send('Fetch.failRequest', {'requestId': event['requestId'], 'errorReason': 'BlockedByClient'})

    session.on('Fetch.requestPaused', fail)
    _count_preflights(session, state)
    session.send('Fetch.enable', {'patterns': list(BLOCKED_FETCH_PATTERNS)})
    session.send('Network.enable')
    return session


def _fulfill_blank(state: 'BrowserState', route: 'Route') -> None:
    """탭을 이 주소로 띄울 때만 서버에 묻지 않고 브라우저 안에서 빈 페이지를 돌려준다 (그 출처의 탭만 필요할 때).

    같은 주소로 보내는 우리 fetch 는 다음 route 로 넘겨 서버에 보낸다. 넘기지 않으면 남긴 쿠키로 띄운 당근 지도 페이지와
    같은 주소의 HTML 요청까지 빈 페이지가 되어 PARSE_ERROR 가 났다 (2026-11-09 감시 실행).

    빈 페이지에도 아이콘 링크(`data:`)를 둔다. 없으면 Chromium 이 스스로 그 사이트의 `/favicon.ico` 를 쿠키를 실어 요청했고,
    이 요청은 route·`request` 이벤트·CDP Fetch 어디에도 잡히지 않아 요청 제한에도 세지 않았다 (2026-11-10 로컬 재현).

    이때 크롬이 페이지를 열며 붙인 헤더(`accept`·`upgrade-insecure-requests`)를 남겨 둔다 (`navigation_headers`). 페이지 HTML
    요청에 붙여 웹에서 페이지를 열 때와 같게 한다. 값이 크롬 버전마다 달라(Chromium 156 은 `accept` 에 `image/jxl` 이 있다)
    고정하지 않고 띄울 때마다 읽는다. 서버로 나가는 첫 화면 문서 요청과 같은 값이다 (2026-11-12 실측). 브라우저를 띄울 때마다
    이 빈 페이지를 거치므로(첫 화면을 새로 열 때도, 남긴 쿠키로 띄울 때도) 쿠키 파일에 남기지 않는다.
    """
    if route.request.is_navigation_request():
        state.navigation_headers = {
            name: value for name, value in route.request.headers.items() if not browser_owned(name)
        }
        route.fulfill(status=200, content_type='text/html', body=BLANK_PAGE_HTML)
    else:
        route.fallback()
