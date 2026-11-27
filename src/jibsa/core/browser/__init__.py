"""httpx 요청을 사이트 페이지를 연 브라우저 안의 `fetch` 로 보내는 transport.

httpx `Client`·`AsyncClient` 의 `transport` 만 바꾸므로 base_url·auth·요청 제한 훅·재시도는 그대로 돈다.
첫 요청 때 scrapling `StealthySession` 으로 위장한 Chromium 을 띄워 사이트 첫 화면(`entry_url`)을 실제로 연다.
사이트 JS 가 돌며 심은 쿠키와 페이지 주소(Referer)·UA·`sec-ch-ua` 를 브라우저가 그대로 붙여 요청한다.
TLS·HTTP/2 지문은 브라우저 것이라 일반 Chrome 과 같다. scrapling 은 그 위에 사이트 JS 의 봇 검사에 걸리는
흔적(`navigator.webdriver`, Web Worker 언어 불일치, 화면 크기 등)을 감춘다.

CLI 는 명령마다 새 프로세스라 브라우저도 매번 빈 쿠키로 뜬다. 그래서 명령이 끝날 때 쿠키를
`<state_dir>/browser/<source>.json` 에 남기고, 첫 화면을 연 지 `REFRESH_SECONDS` 안이면 다음 명령은 첫 화면을
다시 열지 않고 남긴 쿠키로 바로 요청한다. 첫 화면을 열 때 페이지가 스스로 부르는 사이트 API 는 요청 제한 훅을
거치지 않아 `RateLimiter.record` 로 따로 센다.

브라우저 일은 transport 마다 띄운 전용 스레드 하나에서 받은 차례대로 한다 (`_BrowserThread`). patchright 동기 API 는
asyncio 이벤트 루프 안에서 부를 수 없지만 이 스레드에는 루프가 돌지 않아, 동기 `BrowserTransport` 는 어느 스레드·루프에서
불려도 이 스레드에 일을 넘기고 기다린다. 비동기 `AsyncBrowserTransport` 는 동기 transport 를 감싸 같은 일을 넘기고 `await` 로
기다린다 (`AsyncBrowserTransport.handle_async_request`). 그래서 흐름(`_open_page`·요청 보내기)은 한 벌이고, 동시에 온 요청도 이
스레드가 차례로 해 잠금이 없다. 예전에는 비동기 흐름을 patchright 비동기 API 로 따로 두어 고칠 때마다 함께 맞추고 동시성
잠금(`asyncio.Lock`)을 따로 두었다 (2026-11-10 리뷰로 합침). CLI 와 매일 API 감시는 동기 transport 만 쓴다. 비동기 쪽은
CI 의 브라우저 확인(`scripts/ci/browser_check.py` 5번)이 가짜 사이트로 띄워 보고, 실제 사이트는 고친 사람이 `AsyncClient` 로
직접 불러 확인한다.
scrapling·patchright 는 브라우저를 띄울 때 함수 안에서 불러온다.
patchright 를 불러오는 데 0.1초쯤 걸려 (2026-11-09 실측, jibsa CLI 전체는 0.7초) 브라우저를 쓰지 않는 명령까지
느려지지 않게 하려는 것이다. `urllib.request` 는 맨 위에서 불러온다. httpx 가 이미 불러오는 모듈이라(`httpx._auth`) 함수
안으로 옮겨도 CLI 가 빨라지지 않는다 (2026-11-10 `python -X importtime` 확인).
"""

from .errors import (
    CERT_HINT,
    PROXY_HINT,
    CertificateError,
    CorsBlockedError,
    EntryOpenError,
    EntryPageError,
    EntryStatusError,
)
from .fetch import (
    BODY_CHUNK_BYTES,
    NAVIGATION_EXTENSION,
)
from .install import install_chromium
from .session import (
    DISCARD_STATE_STATUSES,
    BrowserOptions,
)
from .transport import (
    AsyncBrowserTransport,
    BrowserTransport,
)
