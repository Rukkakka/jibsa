"""transport 설정(`BrowserOptions`)과 한 명령 동안의 브라우저 상태·요청 기록(`BrowserState`)."""

import json
import logging
import time
import urllib.request
from collections.abc import (
    Mapping,
    Sequence,
)
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit

from httpx import (
    ProxyError,
    Request,
    Response,
)

from jibsa.core.browser.cookies import (
    has_cookie,
    load_state,
    origin,
    state_path,
)
from jibsa.core.browser.errors import (
    EntryPageError,
    EntryStatusError,
)
from jibsa.core.browser.proxy import proxy_settings
from jibsa.core.errors import JibsaError
from jibsa.core.ratelimit import (
    RateLimitedError,
    RateLimiter,
)
from jibsa.core.state import (
    StateDirError,
    write_text_atomic,
)

from typing import Any


logger = logging.getLogger(__name__)

# transport 를 timeout 없이 만들었을 때, 요청에 timeout 이 없으면 쓰는 값 (초). BaseHTTPClient.timeout 기본값과 같다.
# BaseHTTPClient 는 자기 timeout 을 넘긴다 (`_browser_options`)
DEFAULT_TIMEOUT_SECONDS: float = 20.0
# 우리 요청이 이 상태를 받으면 남긴 쿠키를 버려 다음 명령이 첫 화면부터 연다 (거부된 방문자 쿠키를 이어 쓰지 않는다).
# 소스가 403 을 다른 뜻으로 쓰면(다방은 없는 주소) `discard_statuses` 로 바꾼다.
# 429 는 넣지 않는다. 요청량·IP 단위 차단이라 쿠키를 바꿔도 풀리지 않고 (네이버 차단 화면에 IP 가 찍힌다), 버리면 쿨다운
# 뒤 첫 명령이 아직 막혀 있을지 모르는 사이트에 첫 화면 요청을 20건쯤 한꺼번에 보낸다. 남겨 두면 요청 1건으로 풀렸는지 본다
DISCARD_STATE_STATUSES: frozenset[int] = frozenset({403})
# 요청 제한에 세는 페이지 요청 종류. 사이트가 JS 파일도 API 와 같은 호스트에서 주면(다방 /_next/static) 그것까지 세지 않는다
COUNTED_RESOURCE_TYPES: frozenset[str] = frozenset({'xhr', 'fetch'})
# 다시 열어도 같은 첫 화면 실패(`BrowserState.remember_if_fatal`)를 소스별로 기억하는 시간. 같은 명령 안에서 실패를 삼킨
# 덤 조회 뒤의 요청이나 새로 만든 같은 소스 클라이언트가 브라우저를 다시 띄워 첫 화면 요청을 또 보내고 40초를 또 기다리지
# 않게 한다. 라이브러리로 오래 쓰는 프로세스는 이 시간이 지나면 다시 연다
FAILED_ENTRY_MEMORY_SECONDS: float = 60
# 첫 화면 문서가 이 상태면 사이트가 이 접속(IP·봇)을 막은 것으로 보고 에러에 `blocked: true` 를 붙인다
# (`BrowserState.finish_entry`). 업데이트로 풀리지 않으니 에이전트는 업데이트를 권하지 않고, 매일 API 감시
# (`scripts/monitor/api_check.py`)는 고장이 아니라 확인 못 함으로 센다. 그 밖의 4xx(404 등)는 첫 화면 주소가 바뀌었을 수 있다.
# 예전에는 감시가 hint 문구를 맞춰 봐, hint 가 다른 막힘 에러를 고장으로 셌다 (2026-11-10 리뷰)
ENTRY_BLOCKED_STATUSES: frozenset[int] = frozenset({401, 403, 451})
# (소스, proxy, 환경 변수 프록시, verify) → (실패 시각, 에러). 프록시·인증서 설정이 다른 클라이언트에는 앞 실패를 다시 내지
# 않는다 (`BrowserState._failure_key`)
_FailureKey = tuple[str, str | None, tuple[tuple[str, str], ...] | None, bool]
_failed_entries: dict[_FailureKey, tuple[float, Exception]] = {}


@dataclass(frozen=True, kw_only=True)
class BrowserOptions:
    """`BrowserTransport` 의 설정. 모두 키워드로만 받는다.

    transport 와 `BrowserState` 가 이 객체 하나를 받는다. 예전에는 같은 인자 10개를 `BaseHTTPClient._browser_options` 의 dict,
    `BrowserTransport.__init__`, `BrowserState.__init__` 에 따로 적고 dict 를 `**` 로 풀어 넘겨, 하나를 빠뜨리거나 이름을 틀려도
    타입 검사가 잡지 못하고 기본값으로 돌았다 (2026-11-12 리뷰). 같은 타입의 인자(`ready_cookie`·`proxy` 는 둘 다
    `str | None`)를 위치로 넘기면 순서가 어긋나도 잡지 못해 키워드로만 받는다.

    Args:
        source: 소스 이름. 쿠키 파일 이름이 된다.
        entry_url: 처음 열 사이트 화면 (`https://fin.land.naver.com/`). 요청 주소와 출처가 같아야 CORS 에 걸리지 않는다.
        ready_cookie: 첫 화면을 연 뒤 생길 때까지 기다리고, 남긴 쿠키를 쓸 수 있는지 볼 쿠키 이름.
            None 이면 load 까지만 기다린다. Defaults to None.
        api_hosts: 사이트 API 호스트. 첫 화면이 이 호스트로 보낸 요청을 요청 제한에 센다. 비우면 만들 때 `entry_url` 의
            호스트로 채운다. Defaults to frozenset().
        discard_statuses: 우리 요청이 받으면 남긴 쿠키를 버릴 HTTP 상태. Defaults to `DISCARD_STATE_STATUSES`.
        rate_limiter: 소스의 요청 제한기. Defaults to None.
        proxy: 브라우저가 쓸 프록시 URL. Defaults to None.
        verify: TLS 인증서 검증. False 면 브라우저가 인증서 오류를 무시한다. Defaults to True.
        timeout: 요청에 httpx timeout 이 없을 때 쓰는 값(초). 클라이언트의 timeout 을 넘긴다 (`fetch_arguments`).
            Defaults to `DEFAULT_TIMEOUT_SECONDS`.
    """

    source: str
    entry_url: str
    ready_cookie: str | None = None
    api_hosts: frozenset[str] = frozenset()
    discard_statuses: frozenset[int] = DISCARD_STATE_STATUSES
    rate_limiter: RateLimiter | None = None
    proxy: str | None = None
    verify: bool = True
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        # 빈 api_hosts 를 여기서 채워, 쓰는 쪽이 모두 `options.api_hosts` 하나만 읽게 한다. 따로 채운 값을 두면 빈 원래 값을
        # 잘못 읽어 첫 화면 요청을 하나도 세지 않을 수 있다 (2026-11-12 리뷰). frozen 이라 object.__setattr__ 로 넣는다
        if not self.api_hosts:
            object.__setattr__(self, 'api_hosts', frozenset({urlsplit(self.entry_url).netloc}))


class BrowserState:
    """transport 의 설정(`options`)과 한 명령 동안의 기록."""

    def __init__(self, options: BrowserOptions) -> None:
        self.options = options
        self.reset()

    def session_options(self) -> dict[str, Any]:
        """scrapling `StealthySession` 에 넘길 설정."""
        # google_search 는 scrapling fetch() 의 Referer 를 구글로 바꾸는 옵션이라 끈다 (우리는 fetch() 를 쓰지 않는다).
        # scrapling 은 컨텍스트에 ignore_https_errors=True 를 기본으로 넣어 인증서를 검사하지 않는다. additional_args 가 그보다
        # 우선하므로 여기서 되돌린다. Chromium 은 인증서 파일을 받지 않고 내장 목록과 OS 에 설치된 인증서를 믿는다
        # (2026-11-09 실측: 테스트 CA 가 서명한 로컬 서버를 기본값은 통과, False 로 덮어쓰면 ERR_CERT_AUTHORITY_INVALID)
        # 프록시는 scrapling 의 `proxy` 가 아니라 Playwright 설정으로 바로 넘긴다 (`proxy_settings`). 바로 연결은 Chromium 의
        # `--no-proxy-server` 라 OS 프록시 설정도 보지 않는다
        # 서비스 워커는 scrapling 기본값(service_workers='allow')을 그대로 둔다. 네 사이트 모두 첫 화면이 서비스 워커를 등록하지
        # 않는다 (2026-11-10 실측: 첫 화면을 새로 열고 3초 뒤에도 등록 0개, 페이지를 제어하는 워커 없음). 위장 기본값을 바꾸지
        # 않으려고 막지 않는다. 사이트가 서비스 워커를 쓰기 시작하면 그 워커가 처리한 요청은 page.route 가 가로채지 못해
        # (Playwright 의 알려진 제한) 서버에 묻지 않을 빈 페이지 이동이 서버로 가니, 그때 additional_args 에
        # service_workers='block' 을 넣는다
        additional_args: dict[str, Any] = {'ignore_https_errors': not self.options.verify}
        extra_flags: list[str] = []
        proxy = proxy_settings(self.options.proxy, self.options.entry_url)
        if proxy == 'direct':
            extra_flags.append('--no-proxy-server')
        elif proxy is not None:
            additional_args['proxy'] = proxy
        return {
            'headless': True, 'locale': 'ko-KR', 'timezone_id': 'Asia/Seoul', 'google_search': False,
            'additional_args': additional_args, 'extra_flags': extra_flags,
        }

    def reset(self) -> None:
        # 브라우저를 통과한 사이트 API 요청 수 (첫 화면 + 우리 요청), 그중 첫 화면을 다 연 시점까지의 수, 우리 요청 수
        self.routed = 0
        self.routed_at_open = 0
        self.ours = 0
        self.entry_429 = False
        # 첫 화면에서 받은 429 의 `Retry-After` 중 가장 긴 것 (초). 없으면 None
        self.entry_retry_after: float | None = None
        # 명령이 끝날 때 남긴 쿠키를 버린다 (거부된 방문자 쿠키)
        self.discard = False
        # 명령이 끝날 때 남긴 쿠키 파일을 건드리지 않는다 (첫 화면 5xx: 사이트 장애라 방문자 쿠키를 버리지도, 이 첫 화면의
        # 쿠키로 덮지도 않는다. 파일의 첫 화면 시각이 그대로라 다음 명령이 그 쿠키를 넣고 첫 화면을 다시 연다)
        self.leave_saved = False
        self.page_url = ''
        self.opened_at = 0.0
        # 크롬이 페이지를 열 때 붙인 헤더 (`_fulfill_blank` 가 채운다). 페이지 HTML 요청에 붙인다 (`NAVIGATION_EXTENSION`)
        self.navigation_headers: dict[str, str] = {}

    def count_request(self, resource_type: str, url: str) -> None:
        """첫 화면 탭의 `request` 이벤트마다 부른다. route 는 탭을 다 띄운 뒤 걷으므로 이벤트로 센다 (`UNROUTE_BEHAVIOR`)."""
        if resource_type in COUNTED_RESOURCE_TYPES and urlsplit(url).netloc in self.options.api_hosts:
            self.routed += 1

    def count_preflight(self, url: str) -> None:
        """브라우저가 사이트 API 로 보낸 CORS 사전 요청(OPTIONS)을 요청 제한에 바로 남긴다 (CDP `Network.requestWillBeSent`).

        사전 요청은 요청 제한 훅도 페이지 `request` 이벤트도 거치지 않아 세지 않으면 서버로 가는 요청이 정책보다 많다. 직방
        apis.zigbang.com 은 `Access-Control-Max-Age` 가 없어(브라우저는 5초만 기억한다) 주소가 다른 요청마다 OPTIONS 가
        따라가, 검색 2건에 서버로 4건이 갔는데 요청 제한은 2건만 셌다 (2026-11-10 실측). 당근 GraphQL 도 같다. 첫 화면과
        같은 출처로 가는 요청(네이버 front-api·다방)은 사전 요청이 없다. CDP 이벤트
        처리 중이라 상태 파일을 쓰지 못해도 올리지 않는다. 올리면 patchright 가 traceback 을 stderr 로 내고, 다음 브라우저
        호출에서 그 에러를 다시 만들다 TypeError 로 바꿔 내 명령이 INTERNAL_ERROR 로 끝났다 (2026-11-10 리뷰: `record` 는
        OSError 를 `StateDirError` 로 바꿔 올리는데 OSError 만 잡고 있었다).

        사전 요청마다 상태 파일을 한 번씩 쓴다 (잠금·읽기·쓰기). 모아 두었다 한 번에 쓰지 않는 것은 비용이 작고(2026-11-10
        실측: 직방 검색 한 번에 13번, 합쳐 3.5ms 로 명령 시간의 0.1% 미만) 미뤄 쓰면 그사이 다른 jibsa 프로세스가 이 요청을
        세지 못하고, 쓰기 전에 프로세스가 끝나면 센 요청이 사라지기 때문이다.
        """
        if self.options.rate_limiter is None or urlsplit(url).netloc not in self.options.api_hosts:
            return
        try:
            self.options.rate_limiter.record(1)
        except (StateDirError, OSError) as error:
            # 잠금 풀기·잠금 파일 닫기의 OSError(Windows `msvcrt`)는 `record` 가 StateDirError 로 감싸지 않는다 (2026-11-10 리뷰)
            logger.warning('CORS 사전 요청을 요청 제한에 남기지 못했습니다: %s', error)

    def on_entry_rate_limited(self, url: str, retry_after: str | None, main_document: bool) -> None:
        """첫 화면 탭이 429 응답을 받을 때마다 부른다 (`page` 의 `response` 이벤트).

        사이트 API 호스트의 429 면 첫 화면에서 멈추게 표시하고(`entry_429`), 그 응답과 첫 화면 문서(`main_document`)의
        429 에서 `Retry-After` 를 남겨 `finish_entry` 가 쿨다운에 쓴다. 우리 요청의 429(`RateLimiter.on_rate_limited`)처럼
        정책 값과 서버 값 중 긴 쪽으로 쉬려는 것이다. 정책 값만 쓰면 서버가 더 쉬라고 한 사이트에 일찍 다시 보냈다
        (2026-11-10 리뷰: Retry-After 600 에 쿨다운 120초). 사이트 밖(광고·분석) 응답의 429 는 보지 않는다. 그 값으로
        쿨다운이 늘지 않게 한다.

        첫 화면 단계에서 보지 못하는 429 가 둘 있다. 다른 출처 API 가 CORS 허용(`Access-Control-Allow-Origin`) 없이 준
        429 는 브라우저가 `response` 이벤트를 주지 않고(직방 `apis.zigbang.com`·당근 `realty.kr.karrotmarket.com`, 다방·네이버는
        같은 출처라 해당 없음), load·쿠키 기다림 뒤에 온 응답은 리스너를 뗀 뒤라 보지 않는다. 둘 다 다음 우리 요청이 같은 429 를
        받아 `Retry-After` 대로 쉬므로(`BlockedResponses`) 손해는 요청 1건이다 (2026-11-10 로컬 실측: CORS 없는 429 에 첫
        화면은 통과하고 다음 요청에서 쿨다운 600초). 첫 화면 탭에 CDP 기록을 미리 붙이면 잡을 수 있지만 그만큼 복잡해져
        두었다. 실제 첫 화면 API 응답은 리스너를 떼기 0.1~0.6초 전에 왔다 (같은 날 실측: 직방 4건, 다방 11건, 당근 1건).
        """
        api = urlsplit(url).netloc in self.options.api_hosts
        if api:
            self.entry_429 = True
        if not (api or main_document) or not retry_after:
            return
        # 순환 import 를 피하려고 여기서 가져온다 (core.http 가 이 모듈을 불러온다)
        from jibsa.core.http import retry_after_seconds

        seconds = retry_after_seconds(retry_after)
        if seconds is not None:
            self.entry_retry_after = max(self.entry_retry_after or 0.0, seconds)

    def finish_entry(self, status: int | None, retry_after: str | None) -> None:
        """첫 화면 요청을 요청 제한에 남기고, 첫 화면이 제대로 열리지 않았으면 멈춘다.

        쿠키는 4xx·다른 출처면 버리고(거부된 방문자), 5xx 면 남긴 파일을 그대로 두고(`leave_saved`), 429 면 남긴다.

        첫 화면 요청은 미리 슬롯을 잡지 않고 연 뒤에 센다. 몇 건일지 열어 보기 전에는 모르고(네이버 18~22건), 사람이 페이지를
        열 때 나가는 묶음과 같다. 그래서 첫 화면을 새로 여는 명령(소스마다 30분에 한 번, 남긴 쿠키를 버린 뒤)은 분당 상한을
        그 묶음만큼 넘을 수 있고, 이어지는 우리 요청이 그만큼 기다린다. 쿨다운은 요청 제한 훅이 슬롯을 잡을 때 보고,
        슬롯을 기다렸으면 기다린 뒤에도 다시 본다(`RateLimiter.acquire`). 기다리지 않았으면 Chromium 을 띄우는 몇 초 사이에 다른
        프로세스가 건 쿨다운은 보지 못해 첫 화면과 그 요청 한 건이 나갈 수 있고, 그다음 요청부터 막힌다. 드물고 나가는 양이 사람이
        한 번 여는 것과 같아 코드로 막지 않았다 (2026-11-23 리뷰).

        Args:
            status: 새로 연 첫 화면 문서의 HTTP 상태. 남긴 쿠키로 띄웠으면 None.
            retry_after: 새로 연 첫 화면 문서의 Retry-After 헤더. 없거나 남긴 쿠키로 띄웠으면 None.

        Raises:
            RateLimitedError: 첫 화면 문서나 그 페이지의 사이트 API 요청이 429 를 받았고 요청 제한이 켜져 있을 때. 쿨다운은
                정책 값과 그 429 의 `Retry-After` 중 긴 쪽이다 (`on_entry_rate_limited`). 꺼져 있으면 멈추지 않고(문서가
                429 면 아래 HTTPStatusError), 우리 요청이 받는 429 를 보통 재시도가 다룬다 (`RateLimiter.on_rate_limited`
                와 같다). 직방처럼 첫 화면 호스트가 `api_hosts` 에 없어도 문서의 429 는 센다.
            EntryStatusError: 첫 화면 문서가 5xx(또는 요청 제한을 끈 429)일 때. HTTPStatusError 라 재시도한다.
            EntryPageError: 첫 화면 문서가 5xx(또는 요청 제한을 끈 429)인데 `Retry-After` 가 재시도 대기 상한(60초)보다 길
                때 (UPSTREAM_ERROR, 429 는 RATE_LIMITED. `retry_after_seconds` 를 붙인다). 첫 화면 문서가 그 밖의 4xx 일 때
                (차단 화면 등, UPSTREAM_ERROR). HTTPStatusError 로 내면 404·빈
                403 을 '없는 ID'로 읽는 호출부(다방 `is_missing_id`, 직방 `unavailable_on_404` 등)가 차단을 없는 매물로 알린다.
                첫 화면이 다른 출처(로그인·보안 확인 화면 등)로 넘어갔을 때도 (UPSTREAM_ERROR). 그 페이지에서 보내는 요청은
                출처가 달라 CORS 로 막히므로, 남겨 두면 다음 명령들도 실패한다. message 에는 넘어간 곳의 출처만 싣는다.
        """
        self.routed_at_open = self.routed
        self.record_entry_requests()
        # 429 면 쿠키를 버리지 않는다. `DISCARD_STATE_STATUSES` 에 429 를 넣지 않은 것과 같은 이유로, 쿨다운 뒤 첫 명령이 남긴
        # 쿠키로 요청 1건만 보내 풀렸는지 본다. 버리면 아직 막혀 있을지 모르는 사이트에 첫 화면 요청을 20건쯤 다시 보낸다
        # (2026-11-09 리뷰: 첫 화면 API 하나가 429 인 것처럼 꾸미니 쿠키가 지워졌다). `ready_cookie` 를 못 받았으면 남긴
        # 쿠키를 쓰지 않아(`usable_cookies`) 다시 연다
        if self.entry_429 or status == 429:
            if self.options.rate_limiter is not None and self.options.rate_limiter.policy.enabled:
                blocked_until = self.options.rate_limiter.block(self.entry_retry_after)
                raise RateLimitedError(self.options.source, blocked_until - time.time(), 'cooldown')
        if status is not None and (status >= 500 or status == 429):
            if status >= 500:
                # 사이트 장애라 방문자를 거부한 것이 아니다. 버리면 다시 넣은 방문자 쿠키(네이버 NNB 등)까지 지워 재시도가
                # 새 방문자로 열었다 (2026-11-10 로컬 실측: 503 한 번에 vid=old 를 지우고 재시도가 vid=new 를 받음)
                self.leave_saved = True
            # 순환 import 를 피하려고 여기서 가져온다 (core.http 가 이 모듈을 불러온다)
            from jibsa.core.http import (
                RETRY_MAX_WAIT_SECONDS,
                retry_after_seconds,
            )

            wait = retry_after_seconds(retry_after) if retry_after else None
            if wait is not None and wait > RETRY_MAX_WAIT_SECONDS:
                # 재시도는 상한(60초)까지만 쉬어, 더 오래 기다리라는 사이트에 첫 화면 요청(20건쯤)을 그보다 일찍 다시 보냈다.
                # 다시 열지 않고 멈춘다 (2026-11-23 리뷰)
                seconds = int(wait + 0.999)
                raise EntryPageError(
                    code='RATE_LIMITED' if status == 429 else 'UPSTREAM_ERROR',
                    message=(
                        f'{self.options.source} 첫 화면({self.options.entry_url}) 응답이 HTTP {status} 이고 '
                        f'{seconds}초 뒤에 다시 오라고 합니다'
                    ),
                    # 5xx 는 `handle_errors` 의 첫 화면 5xx hint 처럼 사이트 장애라고 밝힌다. docs/llm.md 가 UPSTREAM_ERROR 에
                    # 업데이트를 권하되 hint 가 사이트 장애를 가리키면 권하지 않게 한다
                    hint=(
                        f'사이트 첫 화면이 서버 오류를 줬습니다. 사이트 장애일 수 있으니 {seconds}초가 지난 뒤 다시 부르고, '
                        '그사이에는 다른 소스를 쓰세요'
                        if status >= 500 else f'{seconds}초가 지난 뒤 다시 부르고, 그사이에는 다른 소스를 쓰세요'
                    ),
                    details={'status': status, 'retry_after_seconds': seconds},
                )
            request = Request('GET', self.options.entry_url)
            # 문서의 Retry-After 를 실어 재시도(`wait_retry_after`)가 그만큼 쉬게 한다. 싣지 않으면 1초 간격으로 첫 화면을 다시 열었다 (2026-11-23 리뷰)
            # ASCII 가 아닌 값은 httpx 가 헤더로 받지 않아(UnicodeEncodeError) 싣지 않고 1초 쉰다 (같은 날 리뷰)
            headers = {'Retry-After': retry_after} if retry_after and retry_after.isascii() else None
            raise EntryStatusError(
                f'첫 화면({self.options.entry_url}) 응답이 HTTP {status} 입니다',
                request=request,
                response=Response(status, headers=headers, request=request),
            )
        if status is not None and status >= 400:
            self.discard = True
            if status in ENTRY_BLOCKED_STATUSES:
                raise EntryPageError(
                    code='UPSTREAM_ERROR',
                    message=f'{self.options.source} 첫 화면({self.options.entry_url}) 응답이 HTTP {status} 입니다',
                    hint='사이트가 이 접속을 막았을 수 있습니다. 업데이트로는 풀리지 않으니 다른 소스를 쓰세요',
                    details={'status': status, 'blocked': True},
                )
            raise EntryPageError(
                code='UPSTREAM_ERROR',
                message=f'{self.options.source} 첫 화면({self.options.entry_url}) 응답이 HTTP {status} 입니다',
                hint='사이트 첫 화면 주소가 바뀌었을 수 있습니다. 다른 소스를 쓰세요',
                details={'status': status},
            )
        if origin(self.page_url) != origin(self.options.entry_url):
            self.discard = True
            # 순환 import 를 피하려고 여기서 가져온다 (core.http 가 이 모듈을 불러온다)
            from jibsa.core.http import strip_userinfo

            # 넘어간 주소의 경로·쿼리·사용자 정보에 토큰이 실릴 수 있어 출처(스킴·호스트·포트)만 싣는다 (2026-11-24 확인)
            parts = urlsplit(self.page_url)
            host = strip_userinfo(parts.netloc)
            shown = f'{parts.scheme}://{host}' if host else f'{parts.scheme}:'
            raise EntryPageError(
                code='UPSTREAM_ERROR',
                message=f'{self.options.source} 첫 화면이 다른 출처({shown})로 넘어갔습니다',
                hint='사이트가 보안 확인·로그인 화면으로 넘겼거나 첫 화면 주소가 바뀌었을 수 있습니다. 다른 소스를 쓰세요',
            )

    def keeps_entry_cookies(self, status: int | None) -> bool:
        """새로 연 첫 화면의 쿠키를 확인(`finish_entry`) 전에 남길지. 문서가 4xx·5xx(429 제외)거나 다른 출처면 남기지 않는다.

        확인 전에 남기는 것은 429 로 멈춰도 쿠키가 남게 하려는 것이다 (`_launch`). 거부된 첫 화면(4xx·다른 출처)의 쿠키까지
        먼저 쓰면 닫을 때 지우기 전에 프로세스가 끝났을 때(Ctrl+C) 다음 명령들이 그 쿠키를 30분 동안 이어 썼다 (2026-11-10
        리뷰: 쓰고 지우기까지 약 1ms). 5xx 첫 화면의 쿠키로 덮으면 다시 넣은 방문자 쿠키의 첫 화면 시각이 새것이 되어, 다음
        명령들이 장애 화면에서 받은 쿠키를 30분 동안 썼다.
        """
        if status is not None and status >= 400 and status != 429:
            return False
        return origin(self.page_url) == origin(self.options.entry_url)

    def record_entry_requests(self) -> None:
        """첫 화면을 열며 페이지가 보낸 사이트 API 요청을 요청 제한에 남긴다. 연 뒤(`finish_entry`)와 열다 실패했을 때 부른다.

        남기지 못해도(상태 폴더 오류) 경고만 남긴다. 에러를 내면 그 뒤의 판정(429 쿨다운 저장, 5xx 재시도, 4xx 차단)이나 열다
        난 원래 에러(시간 초과 등)를 덮었다 (2026-11-23 리뷰: 429 첫 화면에 쿨다운이 남지 않고 INTERNAL_ERROR 로 끝났다).
        """
        if self.options.rate_limiter is None:
            return
        try:
            self.options.rate_limiter.record(self.routed)
        except (StateDirError, OSError) as error:
            logger.warning('첫 화면 요청을 요청 제한에 남기지 못했습니다: %s', error)

    def raise_if_entry_failed(self) -> None:
        """이 소스의 첫 화면이 `FAILED_ENTRY_MEMORY_SECONDS` 안에 다시 열어도 같은 이유로 실패했으면 그 에러를 다시 낸다.

        같은 소스라도 proxy(주지 않았으면 환경 변수 프록시)·verify 가 다른 클라이언트는 따로 본다 (`_failure_key`). 프록시를
        고쳐 새로 만든 클라이언트가 앞 클라이언트의 ProxyError 를 받았다 (2026-11-09 리뷰). 기억해 둔 예외 객체가 아니라 같은
        내용의 새 객체로 던진다 (이유는 본문 주석).
        """
        failed = _failed_entries.get(self._failure_key())
        if failed is not None and time.monotonic() - failed[0] < FAILED_ENTRY_MEMORY_SECONDS:
            error = failed[1]
            # 기억해 둔 에러(`_failed_entries`)와 같은 종류·속성의 새 객체를 `__init__` 을 거치지 않고 만들어 던진다. 같은 객체를
            # 다시 던지면 던질 때마다 traceback 에 프레임이 이어 붙어 길어지고(2026-11-09 확인: 2·4·6개), 앞에서 붙은
            # `__context__` 가 남아 관계없는 에러가 이어지며, 여러 스레드가 함께 던지면 `__traceback__` 이 섞였다 (2026-11-10 리뷰:
            # 스레드 2개 4만 번에 1번). `copy.copy` 는 `args` 로 `__init__` 을 다시 불러 인자가 다른 JibsaError 서브클래스
            # (code·message…)에서 TypeError 가 난다
            fresh = BaseException.__new__(type(error), *error.args)
            fresh.__dict__.update(error.__dict__)
            fresh.__cause__ = error.__cause__
            fresh.__suppress_context__ = error.__suppress_context__
            raise fresh

    def remember_if_fatal(self, error: Exception) -> None:
        """첫 화면을 띄우다 난 에러 중 재시도하지 않는 것(시간 초과·다른 출처·차단 화면·60초 넘게 기다리라는 5xx·프록시·Chromium)을 기억한다.

        재시도하는 실패(ConnectError, 5xx HTTPStatusError)는 기억하지 않는다. 429 쿨다운은 요청 제한 상태 파일이 기억한다.
        상태 폴더 오류(`StateDirError`: 잠금·바꿔치기 경합 등)도 다시 열면 풀릴 수 있어 기억하지 않는다 (2026-11-23 리뷰).
        덤 조회가 이 실패를 삼키면(`OPTIONAL_LOOKUP_BASE_ERRORS` 는 ProxyError 를, 당근은 JibsaError 도 잡는다) 기억하지 않을 때
        다음 요청이 다시 연다. `EntryPageError`·`BROWSER_UNAVAILABLE` 은 JibsaError 다.
        """
        if isinstance(error, ProxyError) or (
            isinstance(error, JibsaError) and not isinstance(error, (RateLimitedError, StateDirError))
        ):
            _failed_entries[self._failure_key()] = (time.monotonic(), error)

    def _failure_key(self) -> _FailureKey:
        """`_failed_entries` 의 키. `proxy` 를 주지 않았으면 브라우저가 읽는 환경 변수 프록시(`proxy_settings`)도 넣는다.

        넣지 않았을 때는 환경 변수(`HTTPS_PROXY` 등)를 고친 뒤 새로 만든 클라이언트가 앞 실패를 그대로 받았다 (2026-11-10
        실측: 죽은 `HTTPS_PROXY` 로 실패한 뒤 지워도 0.0초 만에 같은 ProxyError). 환경 변수가 없을 때 Chromium 이
        보는 OS 프록시 설정(GNOME·Windows·macOS)을 바꾼 것은 알 수 없어 `FAILED_ENTRY_MEMORY_SECONDS` 가 지나야 다시 연다.
        """
        env_proxies = (
            None if self.options.proxy is not None else tuple(sorted(urllib.request.getproxies_environment().items()))
        )
        return self.options.source, self.options.proxy, env_proxies, self.options.verify

    def on_send(self, url: str) -> None:
        # 첫 화면 탭에서 `count_request` 가 센 우리 요청을 같은 조건(사이트 API 호스트)으로 센다. 첫 화면 JS 가 더 부른
        # 요청 수를 routed 에서 빼려는 것이라, 응답이 아니라 보낼 때 세야 실패한 요청도 routed 와 맞는다
        if urlsplit(url).netloc in self.options.api_hosts:
            self.ours += 1

    def on_response(self, status: int) -> None:
        if status in self.options.discard_statuses:
            self.discard = True

    def save(self, cookies: Sequence[Mapping[str, Any]]) -> None:
        """쿠키 상태를 남긴다. 쿠키는 다음 명령을 빠르게 할 뿐이라 못 써도 명령은 실패시키지 않는다.

        페이지가 받은 쿠키를 모두 남긴다. 광고·분석용 제3자 쿠키도 들어 있지만(2026-11-10 실측: 직방 37개 중 23개, 다방
        23개 중 13개) 남긴 쿠키로 띄우면 빈 페이지라 그 호스트로 요청이 나가지 않아 어디로도 보내지지 않는다 (같은 날 실측:
        직방 명령 하나에서 나간 요청은 서버에 묻지 않는 첫 화면 주소의 빈 페이지와 `apis.zigbang.com` 뿐). 로그인 없는 익명
        방문자 쿠키라 거르지 않고, 상태 폴더의 다른 파일처럼 기본 권한으로 쓴다.
        """
        path = state_path(self.options.source)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, json.dumps({
                'opened_at': self.opened_at, 'page_url': self.page_url, 'cookies': [dict(cookie) for cookie in cookies],
            }))
        except OSError as error:
            logger.warning('브라우저 쿠키를 남기지 못했습니다 (%s): %s', path, error)

    def discard_saved(self, opened_at: float) -> None:
        """남긴 쿠키를 버린다. 파일의 첫 화면 시각이 `opened_at` 보다 늦으면 다른 프로세스가 새로 연 것이라 두고 간다.

        같은 쿠키로 함께 뜬 두 명령이 둘 다 403 을 받으면, 먼저 버린 뒤 다음 명령이 새로 받은 쿠키를 나중 명령이 지웠다
        (2026-11-10 리뷰). 읽고 지우는 사이는 잠그지 않는다. 겹쳐도 다음 명령이 첫 화면을 다시 열 뿐이다.
        """
        current_opened_at = load_state(self.options.source).get('opened_at')
        if isinstance(current_opened_at, (int, float)) and current_opened_at > opened_at:
            return
        with suppress(OSError):
            state_path(self.options.source).unlink()

    def finish(self, cookies: Sequence[Mapping[str, Any]] | None) -> None:
        """첫 화면을 연 뒤 페이지 JS 가 더 부른 요청을 요청 제한에 남기고, 쿠키를 남기거나 버린다.

        브라우저가 이미 죽어 쿠키를 읽지 못했으면(`cookies` 가 None) 요청 수와 버리기만 하고 남기지 않는다 (`_close`).

        남기거나 버릴 때 그사이 다른 jibsa 프로세스가 한 일을 덮지 않는다. 파일이 없으면 다른 프로세스가 403 을 받아 버린
        것이다 (첫 화면을 새로 열었으면 `finish_entry` 전에 바로 남겼고, 남긴 쿠키로 띄웠으면 그 파일이 있었다). 파일의 첫 화면 시각이 더 늦으면
        다른 프로세스가 첫 화면을 새로 연 것이다. 덮으면 거부된 쿠키나 옛 쿠키가 되살아나 다음 명령들이 30분 동안 이어 썼다
        (2026-11-10 리뷰). 읽고 쓰는 사이는 잠그지 않는다. 겹쳐도 다음 명령이 403 을 받아 다시 버린다.

        `extra` 에는 첫 화면 탭에서 보낸 우리 fetch 가 같은 출처로 넘겨진(redirect) 횟수도 든다. 넘겨질 때마다 서버로 요청이
        실제로 한 번 더 나가므로 세는 것이 맞다. 예전 httpx 도 redirect 마다 요청 훅을 불러 셌다 (`httpx/_client.py`
        `_send_handling_redirects`, 2026-11-10 리뷰에서 확인).
        """
        extra = self.routed - self.routed_at_open - self.ours
        if extra > 0 and self.options.rate_limiter is not None:
            try:
                self.options.rate_limiter.record(extra)
            except (StateDirError, OSError) as error:
                # 남기지 못해도 아래 쿠키 버리기는 한다. 올리면 `_close` 가 경고만 남기고 403 으로 정한 버리기를 건너뛰어, 거부된
                # 쿠키를 다음 명령들이 30분 동안 이어 썼다 (2026-11-24 확인, `record_entry_requests` 와 같은 처리)
                logger.warning('첫 화면 뒤 페이지 요청을 요청 제한에 남기지 못했습니다: %s', error)
        if self.discard:
            self.discard_saved(self.opened_at)
            return
        if cookies is None or self.leave_saved or not self.page_url:
            return
        current = load_state(self.options.source)
        current_opened_at = current.get('opened_at')
        if not current:
            return
        if isinstance(current_opened_at, (int, float)) and current_opened_at > self.opened_at:
            return
        self.save(cookies)

    def log_opened(self, started: float, how: str, cookies: Sequence[Mapping[str, object]]) -> None:
        ready = ''
        if self.options.ready_cookie is not None:
            ready = f', {self.options.ready_cookie} {"있음" if has_cookie(cookies, self.options.ready_cookie) else "없음"}'
        logger.info(
            '브라우저 준비 %.2f초 (%s, 쿠키 %d개%s, 첫 화면을 연 지 %d분)',
            time.perf_counter() - started, how, len(cookies), ready, (time.time() - self.opened_at) // 60,
        )
