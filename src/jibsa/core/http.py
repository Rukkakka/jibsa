import asyncio
import json
import logging
import re
from abc import (
    ABC,
    abstractmethod,
)
from collections.abc import (
    Awaitable,
    Callable,
)
from datetime import (
    datetime,
    timezone,
)
from email.utils import parsedate_to_datetime
from functools import cached_property
from math import isfinite
from types import TracebackType
from urllib.parse import (
    urlsplit,
    urlunsplit,
)

from httpx import (
    AsyncClient,
    Client,
    HTTPError,
    HTTPStatusError,
    NetworkError,
    RemoteProtocolError,
    Response,
    TimeoutException,
    TransportError,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from tenacity import RetryCallState

from jibsa.core.browser import (
    DISCARD_STATE_STATUSES,
    AsyncBrowserTransport,
    BrowserTransport,
)
from jibsa.core.ratelimit import (
    RateLimiter,
    RateLimitPolicy,
)

from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    TypeVar,
)


logger = logging.getLogger(__name__)

# 덤 조회(부가 정보·주소 다듬기 등)가 실패해도 주된 결과는 돌려줄 때 세 소스가 공통으로 잡는 실패: 재시도 뒤에도 남은
# HTTP 오류·timeout·연결 오류(HTTPError)와 응답 모양이 바뀐 경우(ValueError: JSON·UTF-8 해석 실패, pydantic
# ValidationError). 소스마다 더 잡는 것은 각 소스가 더한다 (직방 학군은 요청 제한, 당근은 GraphQL 에러를 담은 JibsaError).
# ValueError 는 jibsa 자체의 값 변환 실패도 잡지만, 응답 문자열을 숫자·날짜로 바꾸다 나는 실패도 형식 변경이라 가르지
# 않는다 (handle_errors 가 ValueError 를 PARSE_ERROR 로 보는 것과 같다)
OPTIONAL_LOOKUP_BASE_ERRORS: tuple[type[Exception], ...] = (HTTPError, ValueError)
# 다시 보내면 나을 수 있는 전송 오류: 시간 초과, 연결·읽기·쓰기 실패, 서버가 응답 중 끊음. 프록시 거절(ProxyError)·
# 지원하지 않는 URL(UnsupportedProtocol)·요청 형식 오류(LocalProtocolError)처럼 다시 보내도 같은 TransportError 는 빼서
# 재시도 대기와 요청 제한 슬롯을 쓰지 않는다 (2026-10-14 확인: CONNECT 를 403 으로 거절하는 프록시에 3번 시도)
RETRYABLE_TRANSPORT_ERRORS: tuple[type[TransportError], ...] = (TimeoutException, NetworkError, RemoteProtocolError)

BODY_PREVIEW_LIMIT: int = 2048
RETRY_BODY_PREVIEW_LIMIT: int = 200
SENSITIVE_KEY_PATTERN: re.Pattern[str] = re.compile(
    r'(token|secret|password|passwd|api[-_]?key|access[-_]?key|'
    r'private[-_]?key|service[-_]?key|authorization|cookie|credential)',
    re.IGNORECASE,
)
SENSITIVE_TEXT_PATTERN: re.Pattern[str] = re.compile(
    r'([\w-]*(?:token|secret|password|passwd|api[-_]?key|access[-_]?key|'
    r'private[-_]?key|service[-_]?key|authorization|cookie|credential)'
    r'[\w-]*\s*[=:]\s*)'
    r'([^,\s&}\n]+)',
    re.IGNORECASE,
)

_T = TypeVar('_T', bound='BaseHTTPClient')


def create_base_url(schema: Literal['https', 'http'], host: str) -> str:
    return f'{schema}://{host}'


def bearer_authorization(token: str) -> str:
    """Render `token` as an `Authorization` header value.

    Accepts either the bare token or one already carrying the `Bearer ` prefix,
    so a caller copying the header value verbatim does not end up sending
    `Bearer Bearer ...`.
    """
    token = token.strip()
    if token.startswith('Bearer '):
        return token
    return f'Bearer {token}'


def _redact_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: '<redacted>'
            if SENSITIVE_KEY_PATTERN.search(str(key))
            else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    return SENSITIVE_TEXT_PATTERN.sub(r'\1<redacted>', value)


def _safe_request_url(url: object) -> str:
    parts = urlsplit(str(url))
    netloc = parts.netloc.rsplit('@', 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, '', ''))


class ResponseStatusError(HTTPStatusError):
    """`HTTPStatusError` whose message carries a truncated response body."""


def _request_origin(exc: HTTPStatusError) -> str:
    """Name the request behind a status error without assuming one was attached.

    `HTTPStatusError.request` raises rather than returning None when the error
    was built without one, so the attribute is never read unguarded.
    """
    try:
        request = exc.request
    except RuntimeError:
        return '<unknown request>'
    return f'{request.method} {_safe_request_url(request.url)}'


def _body_preview(response: Response, limit: int = BODY_PREVIEW_LIMIT) -> str:
    """Render a response body short enough to sit inside an exception message.

    A body that was never read raises rather than returning text, so every
    failure here resolves to a marker instead of propagating.
    """
    try:
        body = response.text
    except Exception:
        return '<unread>'

    body = body.strip()
    if not body:
        return '<empty>'

    try:
        body = json.dumps(
            _redact_json(json.loads(body)),
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError):
        body = _redact_text(body)

    if len(body) > limit:
        return f'{body[:limit]}... (truncated, {len(body)} chars)'
    return body


def raise_for_status(response: Response, limit: int = BODY_PREVIEW_LIMIT) -> None:
    """`Response.raise_for_status` that keeps the error body in the message.

    비공식 API 는 거절 사유를 본문에만 담아 보내므로(예: 직방의 "원룸의 경우 매매
    거래 유형은 존재하지 않습니다"), 본문을 잘라 예외 메시지에 붙인다. 헤더는
    인증정보가 있으므로 넣지 않는다.

    Raises:
        ResponseStatusError: If the response carries a `4xx` or `5xx` status.
            It subclasses `HTTPStatusError`, so retry predicates that match on
            that type are unaffected.
    """
    try:
        response.raise_for_status()
    except HTTPStatusError as exc:
        raise ResponseStatusError(
            f'{_request_origin(exc)} -> '
            f'{response.status_code} {response.reason_phrase}\n'
            f'Response body: {_body_preview(response, limit)}',
            request=exc.request,
            response=exc.response,
        ) from None


def describe_failed_attempt(
    exc: BaseException | None,
    limit: int = RETRY_BODY_PREVIEW_LIMIT,
) -> str:
    """Render a failed attempt as one line for the retry log."""
    if exc is None:
        return '<no exception recorded>'
    if not isinstance(exc, HTTPStatusError):
        return f'{type(exc).__name__}: {exc}'

    body = ' '.join(_body_preview(exc.response, limit).split())
    return (
        f'{_request_origin(exc)} -> '
        f'{exc.response.status_code} {exc.response.reason_phrase} '
        f'| body: {body}'
    )


def should_retry_idempotent(exc: BaseException) -> bool:
    if isinstance(exc, HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return isinstance(exc, RETRYABLE_TRANSPORT_ERRORS)


def should_retry_non_idempotent(exc: BaseException) -> bool:
    """상태를 바꾸는 호출용 재시도 술어. 지금은 조회만 있어 쓰는 곳이 없지만 일부러 남겨 둔다.

    재시도 규약(docs/development/provider-conventions.md '재시도')이 상태를 바꾸는 호출에 이 술어를 쓰라고 정해 두었다.
    timeout·transport 오류는 서버에 이미 닿았을 수 있어 다시 보내지 않는다.
    """
    if isinstance(exc, HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return False


def retry_after_seconds(header: str) -> float | None:
    """Read a `Retry-After` value in either form RFC 9110 allows.

    Args:
        header (str): Raw header value, as delay-seconds or an HTTP-date.

    Returns:
        float | None: Seconds to wait, or None when the value parses as
            neither form.
    """
    try:
        seconds = float(header)
    except ValueError:
        pass
    else:
        return seconds if isfinite(seconds) else None

    try:
        deadline = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if deadline is None:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - datetime.now(timezone.utc)).total_seconds()


def wait_retry_after(
    retry_state: RetryCallState,
    default: float = 1.0,
    maximum: float = 60.0,
) -> float:
    """Honour a rate-limit `Retry-After` header, capped at `maximum` seconds.

    Waits `default` seconds when the failure carries no usable header.
    """
    outcome = retry_state.outcome
    if outcome is None:
        return default

    exc = outcome.exception()
    if not isinstance(exc, HTTPStatusError):
        return default

    header = exc.response.headers.get('Retry-After')
    if not header:
        return default

    seconds = retry_after_seconds(header)
    if seconds is None:
        return default

    return min(max(seconds, 0.0), maximum)


def log_retry_before_sleep(retry_state: RetryCallState) -> None:
    outcome = retry_state.outcome
    next_action = retry_state.next_action
    if outcome is None or next_action is None:
        return

    logger.warning(
        'Attempt %s failed: %s | Retrying in %ss...',
        retry_state.attempt_number,
        describe_failed_attempt(outcome.exception()),
        next_action.sleep,
    )


class BaseHTTPClient(BaseModel, ABC):
    """Shared base model for the httpx-based provider clients.

    Defines the connection options every provider shares and a unified
    lifecycle for the sync/async httpx clients. Subclasses declare their own
    `host` and build `_client` / `_async_client` with ``@cached_property``.

    Args:
        url_schema: `base_url` 의 스킴. 요청은 https 첫 화면을 연 브라우저가 보내 http 요청은 브라우저가 혼합 콘텐츠로
            막으므로 'https' 만 받는다. 서브클래스의 호스트 필드(`host` 등)를 바꾸면 `browser_api_hosts`·
            `browser_no_cors_hosts` 는 따라 바뀌지만 첫 화면(`browser_entry_url`)은 그대로다. 첫 화면 탭에서 보내는
            호스트를 다른 출처로 바꾸면 그 서버가 첫 화면 출처의 CORS 를 허용해야 한다. Defaults to 'https'.
        verify: TLS 인증서 검증. 요청은 Chromium 이 보내므로 켜기·끄기만 받는다 (Chromium 은 인증서 파일을 받지 않고
            내장 목록과 OS 에 설치된 인증서를 믿는다). Defaults to True.
        proxy: 브라우저가 쓸 프록시 URL. Defaults to None.
        timeout: 브라우저 요청 하나가 끝나야 하는 시간(초). httpx 처럼 연결·읽기 단계마다가 아니라 연결부터 본문 끝까지
            전체다 (`core.browser._fetch_arguments`). Defaults to 20.
        rate_limit: 프로세스 간 공유 요청 제한 정책. None 이면 클래스의
            `default_rate_limit` 을 쓴다. Defaults to None.

    Attributes:
        source_name: 요청 제한 상태 파일 이름 (서브클래스가 지정).
        default_rate_limit: 서브클래스 기본 제한 정책.
        rate_limiter: `source_name` 과 정책으로 만든 `RateLimiter`. 서브클래스는
            `rate_limit_hooks()` / `async_rate_limit_hooks()` 를 httpx 클라이언트의
            `event_hooks` 로 넘긴다.
        browser_entry_url: 브라우저가 처음 열 사이트 화면 (서브클래스가 지정). 서브클래스는
            `browser_transport()` / `async_browser_transport()` 를 httpx 클라이언트의 `transport` 로 넘긴다.
        browser_ready_cookie: 첫 화면을 연 뒤 생길 때까지 기다리고, 남긴 쿠키를 쓸 수 있는지 볼 쿠키 이름.
        browser_api_hosts: 첫 화면이 보낸 요청을 요청 제한에 셀 사이트 API 호스트. 비면 `browser_entry_url` 의 호스트.
            호스트 필드에서 만드는 property 라, 호스트 필드를 바꿔도 맞는다 (서브클래스가 덮어쓴다).
        browser_discard_statuses: 우리 요청이 받으면 남긴 쿠키를 버릴 HTTP 상태.
        browser_no_cors_hosts: 첫 화면 출처에서 부르는 것을 CORS 로 허용하지 않아 그 호스트 주소의 빈 탭에서 보낼 호스트.
            `browser_api_hosts` 처럼 호스트 필드에서 만드는 property 다.
    """

    source_name: ClassVar[str] = 'default'
    default_rate_limit: ClassVar[dict[str, object]] = {}
    browser_entry_url: ClassVar[str] = ''
    browser_ready_cookie: ClassVar[str | None] = None
    browser_discard_statuses: ClassVar[frozenset[int]] = DISCARD_STATE_STATUSES

    model_config = ConfigDict(
        extra='forbid',
    )

    url_schema: Literal['https'] = 'https'

    verify: bool = True

    proxy: str | None = None

    timeout: Annotated[
        int,
        Field(gt=0)
    ] = 20

    rate_limit: RateLimitPolicy | None = None

    @cached_property
    def rate_limiter(self) -> RateLimiter:
        policy = self.rate_limit or RateLimitPolicy(**self.default_rate_limit)
        return RateLimiter(self.source_name, policy)

    def rate_limit_hooks(self) -> dict[str, list[Callable[..., None]]]:
        return self.rate_limiter.event_hooks()

    def async_rate_limit_hooks(self) -> dict[str, list[Callable[..., Awaitable[None]]]]:
        # async 쪽(이 훅, `_async_client`, provider 의 `arun_request_*`)은 CLI 가 부르지 않지만 라이브러리로 쓸 때의 공개 API 라
        # 일부러 둔다 (provider-conventions.md '요청 메서드'). 호출부 0건은 죽은 코드가 아니다. 2026-10-11 실측: 세 소스
        # arun_request_* 를 한 번씩 실제로 불러 모두 200 (직방 search_v2, 당근 livable_region_scopes, 네이버 시·도 목록)
        return self.rate_limiter.async_event_hooks()

    @property
    def browser_api_hosts(self) -> frozenset[str]:
        # 호스트를 클래스 상수로 따로 적으면 호스트 필드를 바꿨을 때 어긋나 요청이 엉뚱한 탭에서 나간다 (2026-11-09 리뷰)
        return frozenset()

    @property
    def browser_no_cors_hosts(self) -> frozenset[str]:
        return frozenset()

    def _browser_options(self) -> dict[str, Any]:
        return {
            'source': self.source_name, 'entry_url': self.browser_entry_url, 'ready_cookie': self.browser_ready_cookie,
            'api_hosts': self.browser_api_hosts, 'discard_statuses': self.browser_discard_statuses,
            'no_cors_hosts': self.browser_no_cors_hosts, 'rate_limiter': self.rate_limiter, 'proxy': self.proxy,
            'verify': self.verify, 'timeout': self.timeout,
        }

    def browser_transport(self) -> BrowserTransport:
        """사이트 첫 화면을 연 브라우저로 요청을 보내는 transport (`core/browser.py`). 프록시도 브라우저가 쓴다."""
        return BrowserTransport(**self._browser_options())

    def async_browser_transport(self) -> AsyncBrowserTransport:
        """`browser_transport()` 의 비동기판."""
        return AsyncBrowserTransport(**self._browser_options())

    @property
    @abstractmethod
    def _client(self) -> Client:
        """
        Synchronous HTTP client. Subclasses must override this with
        ``@cached_property`` so `close()` can locate it via
        ``__dict__.pop('_client', None)``. ``@cached_property`` cannot be
        combined with ``@abstractmethod``, so the abstract declaration stays a
        plain property.
        """
        ...

    @property
    @abstractmethod
    def _async_client(self) -> AsyncClient:
        """
        Asynchronous HTTP client. Subclasses must override this with
        ``@cached_property``; see ``_client``.
        """
        ...

    def close(self) -> None:
        """
        Close the sync client only: an async client cannot be closed from
        sync code. If ``arun_request_*`` was used, close with ``aclose()`` or
        ``async with`` instead (a plain ``with`` leaves the async pool open).
        """
        client: Client | None = self.__dict__.pop('_client', None)
        if client is not None:
            client.close()

    async def aclose(self) -> None:
        """
        Close the async client and the sync client too. 동기 클라이언트의 브라우저는 브라우저 스레드가 앞의 일(첫 화면이면 최대
        40초)을 마친 뒤 닫아(`core/browser.py` `_BrowserThread`), 다른 스레드에서 기다려 이벤트 루프를 막지 않는다.
        """
        async_client: AsyncClient | None = self.__dict__.pop('_async_client', None)
        if async_client is not None:
            await async_client.aclose()
        await asyncio.to_thread(self.close)

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> None:
        self.close()

    async def __aenter__(self: _T) -> _T:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> None:
        await self.aclose()

