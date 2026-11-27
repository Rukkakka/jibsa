"""브라우저 transport 의 에러 종류와 playwright·Chromium 에러를 jibsa·httpx 에러로 바꾸는 함수."""

import sys

from httpx import (
    ConnectError,
    HTTPStatusError,
    ProxyError,
    Request,
    TransportError,
)

from jibsa.core.errors import JibsaError


# 브라우저가 프록시에 닿지 못했거나 프록시가 CONNECT 를 거절했을 때의 Chromium 네트워크 오류(앞부분). httpx 의 ProxyError 처럼
# 다시 보내도 같아 재시도하지 않는다. 첫 화면(`_entry_error`, patchright 에러 문구)과 우리 요청(`to_response`, CDP
# `loadingFailed.errorText`)에 같이 쓴다 (2026-11-09 실측: 닫힌 포트를 프록시로 주면 둘 다 net::ERR_PROXY_CONNECTION_FAILED)
PROXY_NET_ERRORS: tuple[str, ...] = ('net::ERR_PROXY_', 'net::ERR_TUNNEL_CONNECTION_FAILED', 'net::ERR_NO_SUPPORTED_PROXIES')
# 그중 프록시가 이 사이트로의 연결만 거절한 것. 나머지(프록시에 닿지 못함·쓸 수 없는 프록시)는 모든 사이트가 같다
SITE_PROXY_NET_ERRORS: tuple[str, ...] = ('net::ERR_TUNNEL_CONNECTION_FAILED',)
# 프록시 오류의 hint. 환경 변수가 없으면 Chromium 이 OS 프록시 설정(PAC 포함)을 쓴다. NO_PROXY=* 는 OS 프록시도 건너뛴다
# (`proxy_settings`). CLI `handle_errors` 가 ProxyError 에, `_entry_error` 가 첫 화면의 사이트별 거절에 붙인다
PROXY_HINT: str = (
    '프록시 설정을 확인하세요: HTTPS_PROXY·ALL_PROXY 환경 변수, 없으면 OS 프록시 설정(VPN·회사 PAC 포함). '
    '프록시 없이 바로 연결하려면 NO_PROXY=* 로 실행하세요 (OS 프록시도 건너뜁니다)'
)
# 브라우저가 첫 화면의 인증서를 믿지 못했을 때의 hint. Chromium 은 SSL_CERT_FILE·SSL_CERT_DIR 을 보지 않아 회사망·보안
# 프로그램의 인증서는 OS 저장소에 있어야 한다. 다시 열어도 같아 재시도하지 않는다 (2026-11-10 로컬 실측: 테스트 CA 를
# SSL_CERT_FILE 로 주면 httpx 는 200, 브라우저는 net::ERR_CERT_AUTHORITY_INVALID 로 Chromium 을 세 번 띄운 뒤
# '네트워크 상태를 확인하라'로 끝났다)
CERT_HINT: str = (
    '회사망이나 보안 프로그램이 HTTPS 를 검사하면 그 인증서를 OS 에 설치해야 브라우저가 믿습니다 (Windows 인증서 저장소, '
    'macOS 키체인, Linux 는 ~/.pki/nssdb). SSL_CERT_FILE 은 쓰지 않습니다. 다시 불러도 같으니 사용자에게 알리세요'
)
# 브라우저가 인증서를 믿지 못한 Chromium 네트워크 오류(앞부분). 첫 화면(`_entry_error`)과 우리 요청(`to_response`)에 같이 쓴다
CERT_NET_ERROR: str = 'net::ERR_CERT_'


class EntryOpenError(Exception):
    """브라우저를 띄워 사이트 첫 화면을 여는 단계에서 실패했다는 표식. 같은 클라이언트의 본 요청도 같은 단계부터 다시 한다.

    첫 화면 단계의 실패만 따로 다룰 곳이 잡는다. 재시도 술어와 CLI 에러 매핑은 원래 종류대로 다루도록 실제 에러는 이것과
    httpx·jibsa 에러를 함께 물려받는다 (`EntryConnectError`, `EntryStatusError`, `EntryPageError`).
    """


class EntryConnectError(ConnectError, EntryOpenError):
    """첫 화면을 여는 단계의 연결 실패. ConnectError 라 재시도한다."""


class EntryStatusError(HTTPStatusError, EntryOpenError):
    """첫 화면 문서가 5xx(또는 요청 제한을 끈 429)였다. HTTPStatusError 라 재시도한다.

    API 응답이 아니므로 상태 코드에 소스 고유 뜻을 붙이는 호출부(다방 학교 상세의 500 = 코드·단계 틀림)는
    `EntryOpenError` 를 먼저 걸러 낸다. 거르지 않으면 사이트 장애를 입력 오류로 안내하고 재시도도 하지 않았다
    (2026-11-10 로컬 실측).
    """


class EntryPageError(JibsaError, EntryOpenError):
    """사이트 첫 화면을 제대로 열지 못했다 (시간 초과·프록시가 사이트를 거절함·인증서 오류는 NETWORK_ERROR, 차단 응답·다른 출처로 넘어감·60초 넘게 기다리라는 5xx 는 UPSTREAM_ERROR).

    재시도하지 않는다. 다시 열면 브라우저를 새로 띄우고 첫 화면 요청을 20건쯤 또 보내며, 시간 초과면 40초를 또 기다린다.
    소스별로 `FAILED_ENTRY_MEMORY_SECONDS` 동안 기억한다 (`BrowserState.remember_if_fatal`). 전송 오류(`HTTPError`)가 아닌
    jibsa 에러라 덤 조회(`OPTIONAL_LOOKUP_BASE_ERRORS`)가 삼키지 않는다. 같은 클라이언트의 본 요청도 같은 에러로 끝나므로
    결과는 같다.
    """


class BrowserUnavailableError(JibsaError):
    """Chromium 을 띄우지 못했다 (BROWSER_UNAVAILABLE). 설치·시스템 라이브러리·드라이버 문제라 모든 소스가 같이 실패한다."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(code='BROWSER_UNAVAILABLE', message=message, hint=hint)


class CorsBlockedError(TransportError):
    """브라우저가 CORS 로 응답을 막아 읽을 수 없다 (`to_response`).

    다른 출처 응답이 2xx 인데 `Access-Control-Allow-Origin` 이 없거나, CORS 사전 요청(OPTIONS)이 거절돼 본 요청이 나가지
    못했을 때다. 3xx·4xx·5xx 응답은 본문 없이도 상태로 다룰 수 있어 `BlockedResponses` 의 상태로 응답을 만들지만, 2xx 를
    빈 본문으로 넘기면 빈 결과나 PARSE_ERROR 가 되어 원인이 가려진다. 사이트의 CORS 설정이 바뀐 것이라 다시 보내도 같아
    재시도하지 않는다 (재시도 술어의 `RETRYABLE_TRANSPORT_ERRORS` 에 들지 않는다). CLI 는 UPSTREAM_ERROR 로 낸다 (`handle_errors`).

    AGENTS.md 의 '새 에러는 JibsaError 로' 를 일부러 따르지 않는다. transport 가 내는 전송 오류라 httpx `TransportError` 여야
    덤 조회(`OPTIONAL_LOOKUP_BASE_ERRORS` 의 `HTTPError`)가 삼켜 주된 결과는 돌려준다. JibsaError 로 내면 덤 조회 하나(다방
    동 경계 CDN 등)의 CORS 변경이 명령 전체를 실패시킨다. 코드·hint 는 `handle_errors` 가 붙인다 (`ProxyError` 와 같다).
    """


class CertificateError(TransportError):
    """브라우저가 우리 요청의 사이트 인증서를 믿지 못했다 (`net::ERR_CERT_*`, `to_response`).

    회사망·보안 프로그램이 HTTPS 를 검사하는데 그 인증서가 OS 에 없으면 다시 보내도 같아 재시도하지 않는다
    (`RETRYABLE_TRANSPORT_ERRORS` 에 들지 않는다). 첫 화면의 인증서 오류는 `_entry_error` 가 `EntryPageError` 로 내지만,
    남긴 쿠키로 띄운 30분 동안은 첫 화면을 서버에 묻지 않아 우리 요청에서 처음 드러난다 (2026-11-10 로컬 실측: ConnectError 로
    3번 보낸 뒤 '네트워크 상태를 확인하라'로 끝났다). `CorsBlockedError`·`ProxyError` 처럼 덤 조회가 삼키도록 httpx 전송
    오류로 두고, CLI 는 NETWORK_ERROR 와 `CERT_HINT` 를 붙인다 (`handle_errors`).
    """


def playwright_error() -> type[Exception]:
    """patchright 에러 클래스. 동기·비동기 API 가 같은 클래스를 쓴다."""
    # 모듈 docstring 대로 브라우저를 쓸 때만 불러온다
    from patchright.sync_api import Error
    return Error


def playwright_timeout_error() -> type[Exception]:
    """patchright 시간 초과 에러 클래스. 동기·비동기 API 가 같은 클래스를 쓴다."""
    # 모듈 docstring 대로 브라우저를 쓸 때만 불러온다
    from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
    return PlaywrightTimeoutError


def first_line(error: Exception) -> str:
    return (str(error).splitlines() or [''])[0]


def _missing_libraries_hint() -> str:
    return (
        f"리눅스는 Chromium 이 쓰는 시스템 라이브러리가 없으면 'sudo {sys.executable} -m patchright install-deps chromium' "
        "을 한 번 실행한 뒤 'jibsa install-browser' 로 확인하세요"
    )


def launch_error(error: Exception) -> BrowserUnavailableError:
    """Chromium 을 띄우다 난 에러. 모든 소스가 같이 실패하고 다시 띄워도 같아 재시도하지 않는 jibsa 에러로 낸다."""
    if isinstance(error, OSError):
        # patchright 드라이버(node)를 실행하지 못했다. Chromium·시스템 라이브러리가 아니라 설치된 jibsa 쪽 문제다
        return BrowserUnavailableError(
            message=f'브라우저 드라이버(patchright)를 실행하지 못했습니다: {error}',
            hint=(
                'jibsa 설치가 깨졌거나 보안 프로그램이 드라이버 실행을 막았을 수 있습니다. jibsa 를 다시 설치하고, 같은 에러면 '
                'message 의 원인을 사용자에게 알리세요'
            ),
        )
    if isinstance(error, playwright_timeout_error()):
        # 시스템 라이브러리가 아니라 늦게 뜬 것이다. 띄우기 제한 시간(Playwright 기본 3분)을 다시 기다리지 않게 재시도는 하지 않는다
        return BrowserUnavailableError(
            message=f'Chromium 이 제시간에 뜨지 않았습니다: {first_line(error)}',
            hint=(
                '컴퓨터가 바쁘거나 보안 프로그램이 Chromium 첫 실행을 검사 중일 수 있습니다. 잠시 뒤 한 번 다시 실행하고, 같으면 '
                'message 의 원인을 사용자에게 알리세요'
            ),
        )
    # Chromium 이 없거나 시스템 라이브러리가 없어 못 띄운 에러면 설치 안내가 든 jibsa 에러를 내고, 아니면 아래 일반 에러를 낸다
    text = str(error)
    if "Executable doesn't exist" in text:
        return BrowserUnavailableError(
            message='브라우저로 요청할 수 없습니다: Chromium 이 설치되어 있지 않습니다',
            hint="'jibsa install-browser' 로 Chromium 을 설치하세요 (jibsa 를 업데이트한 뒤에도 한 번 실행합니다)",
        )
    # Playwright 계열이 시스템 라이브러리가 없을 때 내는 문구 (사전 검사 문구, 실행 파일의 동적 링크 실패)
    if 'missing dependencies' in text or 'error while loading shared libraries' in text:
        return BrowserUnavailableError(
            message='브라우저로 요청할 수 없습니다: Chromium 에 필요한 시스템 라이브러리가 없습니다',
            hint=_missing_libraries_hint(),
        )
    return BrowserUnavailableError(
        message=f'Chromium 을 띄우지 못했습니다: {first_line(error)}',
        hint=_missing_libraries_hint() if sys.platform.startswith('linux') else (
            "'jibsa install-browser' 로 설치와 실행을 확인하세요. 같은 에러면 message 의 원인"
            '(보안 프로그램이 실행을 막았는지 등)을 사용자에게 알리세요'
        ),
    )


def proxy_error(net_error: str, request: Request | None = None) -> ProxyError:
    """Chromium 프록시 오류를 `ProxyError` 로 만든다. 프록시가 이 사이트 연결만 거절한 것(`SITE_PROXY_NET_ERRORS`)은 메시지로 가른다.

    예전에는 프록시에 아예 닿지 못한 것을 `ProxyUnreachableError` 로 따로 두어, 실패하면 다른 소스로 넘기던 곳(당근 위치 찾기)이
    어느 소스로 보내도 같은 실패를 넘기지 않게 했다. 그 넘기기를 뺀 뒤 가르는 곳이 없어 하나로 합쳤다 (2026-11-12 리뷰).
    """
    site_refused = any(code in net_error for code in SITE_PROXY_NET_ERRORS)
    reason = '프록시가 이 사이트 연결을 거절했습니다' if site_refused else '브라우저가 프록시로 연결하지 못했습니다'
    return ProxyError(f'{reason}: {net_error}', request=request)
