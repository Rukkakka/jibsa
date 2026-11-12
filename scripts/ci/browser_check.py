"""이 운영체제에서 jibsa 브라우저가 제대로 도는지 가짜 사이트로 확인한다 (CI 의 '브라우저 확인' 잡, `.github/workflows/ci.yml`).

pytest 는 가짜 응답만 써서 Chromium 을 띄우지 않는다. 그래서 운영체제마다 달라지는 브라우저 쪽(Chromium 띄우기, 브라우저 안의
요청, 막힌 응답 알아보기, Ctrl+C, 끝난 뒤 프로세스 정리)은 여기서 본다. 실제 사이트에는 요청하지 않는다. 이 컴퓨터에 웹 서버
두 개를 띄운다: 첫 화면과 데이터를 주는 사이트(entry)와, 다른 출처에서 CORS 없이 429 를 주는 사이트(blocked). 상태 폴더는
임시 폴더라 실제 쿠키·요청 제한 기록을 건드리지 않는다. CI 는 한 줄 설치 스크립트로 설치한 jibsa 의 Python 으로 돌린다.

    python scripts/ci/browser_check.py

1. 첫 화면을 열고, 그 안에서 보낸 요청(GET·POST)이 데이터와 쿠키를 받아 오는지. 1MB 넘는 본문을 브라우저 안에 두었다가 나눠
   받는지(`_read_body`), 응답 헤더가 늦거나 본문이 멈추면 timeout 에 맞춰 `ReadTimeout` 으로 끝나는지, 본문이 멈춘 429 는
   429 로 알아보는지도 본다. 실제 소스 응답은 1초 안팎·1MB 미만이라 이 경로들은 여기서만 돈다
2. 다시 띄우면 첫 화면을 열지 않고 남긴 쿠키로 바로 요청하는지
3. 다른 출처가 CORS 없이 준 429 를 Retry-After 와 함께 429 로 알아보는지. 브라우저는 이런 응답을 가려 fetch 가 이유 없이
   실패하므로 jibsa 는 CDP 네트워크 이벤트로 상태를 알아낸다 (`_BlockedResponses`). 그래야 요청 제한이 쿨다운을 건다.
   이 확인에서만 Chromium 의 로컬 네트워크 접근 차단을 끈다 (`allow_local_network`)
4. 느린 첫 화면을 여는 중에 Ctrl+C 를 받으면 1초 안에 끝나고, 끝난 뒤 Chromium·드라이버(node)가 남지 않는지.
   CI 에는 키보드가 없어 `_thread.interrupt_main()` 으로 흉내 낸다. 메인 스레드가 브라우저 스레드를 기다리는 동안 Ctrl+C 를
   듣는지가 Windows 에서 갈리는 곳이라(`WAIT_POLL_SECONDS`) 그 흉내로 확인된다
5. 비동기 transport(`AsyncBrowserTransport`)도 첫 화면을 열고 GET·POST 를 보내는지. CLI·매일 감시는 동기 transport 만 써서
   비동기 쪽은 여기서만 띄워 본다. 비동기 transport 는 동기 transport 를 감싸 브라우저 스레드에 일을 넘기는데, 그 넘기기
   (본문 미리 읽기·`await` 로 기다리기·닫기)가 맞는지 여기서 알 수 있다
6. 사이트 API 에 닿은 요청을 요청 제한에 빠짐없이 한 번씩 세는지. 첫 화면이 스스로 부른 API 와 브라우저가 다른 출처로 보낸
   CORS 사전 요청(OPTIONS)은 httpx 훅을 거치지 않아 transport 가 따로 센다 (`RateLimiter.record`, `count_preflight`).
   AGENTS.md 의 '모든 HTTP 요청은 요청 제한을 거친다'를 브라우저에서 지키는 계산이라, Chromium·patchright 가 이벤트를 바꿔
   빠지거나 두 번 세면 여기서 알 수 있다. 이 확인은 첫 화면 사이트와 CORS 를 허용하는 다른 출처 API 사이트를 따로 띄운다

하나라도 틀리면 exit 1 이다.
"""
import _thread
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import urlsplit


# 실제 쿠키·요청 제한 기록 대신 임시 폴더를 쓴다 (jibsa 는 부를 때마다 이 환경 변수를 읽는다)
os.environ.setdefault('JIBSA_STATE_DIR', tempfile.mkdtemp(prefix='jibsa-browser-check-'))

from httpx import (  # noqa: E402
    AsyncClient,
    Client,
    ReadTimeout,
    Response,
)
from scrapling.engines._browsers import _base as scrapling_base  # noqa: E402

from jibsa.core.browser import (  # noqa: E402
    BODY_CHUNK_BYTES,
    AsyncBrowserTransport,
    BrowserOptions,
    BrowserTransport,
)
from jibsa.core.ratelimit import (  # noqa: E402
    RateLimiter,
    RateLimitPolicy,
)


# 첫 화면 JS 가 심는 쿠키. jibsa 는 이 쿠키가 생길 때까지 기다리고, 남긴 쿠키를 쓸 수 있는지 이것으로 본다
READY_COOKIE: str = 'ready'
# 다른 출처 요청에 붙이는 헤더. 기본 허용 헤더가 아니라 브라우저가 CORS 사전 요청(OPTIONS)을 먼저 보낸다 (6번 확인)
PREFLIGHT_HEADER: str = 'x-check'
# 1MB 넘는 응답 본문. jibsa 는 이보다 큰 본문을 evaluate 한 번에 받지 않고 브라우저 안에 두었다가 나눠 읽는다 (`BODY_CHUNK_BYTES`)
BIG_BODY: bytes = json.dumps({'data': 'x' * (2 * BODY_CHUNK_BYTES + 1)}).encode()
# 멈춘 본문 응답이 첫 조각 뒤 침묵하는 시간과 그 요청의 timeout. timeout 이 더 짧아야 본문 유휴 timeout 이 난다
STALL_SECONDS: float = 5
STALL_TIMEOUT_SECONDS: float = 2
# 본문이 멈춘 429 응답의 Retry-After. 본문을 다 받지 못해도 상태·헤더로 429 를 알아봐야 요청 제한이 쿨다운을 건다
STALL_RETRY_AFTER: str = '7'
# 느린 첫 화면이 응답하기까지 걸리는 시간. Ctrl+C 가 이보다 훨씬 빨리 끝내야 한다
SLOW_SECONDS: float = 30
# Ctrl+C 를 보낸 뒤 KeyboardInterrupt 가 나고 클라이언트를 닫기까지 허용하는 시간
INTERRUPT_LIMIT_SECONDS: float = 1.0
# 끝난 뒤 Chromium·드라이버가 사라지기를 기다리는 시간
LEFTOVER_WAIT_SECONDS: float = 10
# 이 문자열이 명령줄에 든 프로세스를 jibsa 가 띄운 Chromium·드라이버로 본다 (Chromium 은 ms-playwright 폴더에 있고,
# 드라이버는 `node ... run-driver` 다. 운영체제마다 같다)
BROWSER_PROCESS_MARKERS: tuple[str, ...] = ('ms-playwright', 'run-driver')

failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {what}", flush=True)
    if not ok:
        failures.append(what)


class QuietHandler(BaseHTTPRequestHandler):
    """요청마다 찍는 로그를 끈 핸들러. `site` 는 `Site` 가 붙인다."""

    site: 'Site'

    def log_message(self, format: str, *args: object) -> None:
        pass


class Site:
    """가짜 사이트 하나 (127.0.0.1 의 빈 포트). 받은 요청 수를 경로마다 센다."""

    def __init__(self, handler: type[QuietHandler]) -> None:
        self.counts: dict[str, int] = {}
        # 느린 첫 화면 요청이 들어왔는지 (Ctrl+C 를 보낼 때를 고른다)
        self.slow_started = threading.Event()
        bound = type(handler.__name__, (handler,), {'site': self})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), bound)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/'


class EntryHandler(QuietHandler):

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _count(self) -> None:
        path = self.path.split('?')[0]
        self.site.counts[path] = self.site.counts.get(path, 0) + 1

    def do_GET(self) -> None:
        self._count()
        if self.path == '/':
            # 서버 쿠키(sid)와 첫 화면 JS 쿠키(ready)를 같이 심는다
            page = f"<html><body><script>document.cookie = '{READY_COOKIE}=1; path=/'</script></body></html>"
            self._send(200, page.encode(), 'text/html', {'Set-Cookie': 'sid=abc; Path=/'})
        elif self.path == '/api/data':
            payload = {'ok': True, 'cookie': self.headers.get('Cookie', '')}
            self._send(200, json.dumps(payload).encode(), 'application/json')
        elif self.path == '/api/big':
            self._send(200, BIG_BODY, 'application/json')
        elif self.path == '/api/stall-head':
            # 응답 헤더를 보내지 않고 멈춘다
            time.sleep(STALL_SECONDS)
        elif self.path in ('/api/stall', '/api/stall-429'):
            # 본문 한 조각을 보내고 멈춘다 (Content-Length 없이 보내 끝을 알 수 없게 한다)
            self.send_response(429 if self.path == '/api/stall-429' else 200)
            self.send_header('Content-Type', 'application/json')
            if self.path == '/api/stall-429':
                self.send_header('Retry-After', STALL_RETRY_AFTER)
            self.end_headers()
            self.wfile.write(b'["a"')
            self.wfile.flush()
            time.sleep(STALL_SECONDS)
        elif self.path == '/slow':
            self.site.slow_started.set()
            time.sleep(SLOW_SECONDS)
            self._send(200, b'<html></html>', 'text/html')
        else:
            self._send(404, b'', 'text/plain')

    def do_POST(self) -> None:
        self._count()
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self._send(200, body, 'application/json')


class BlockedHandler(QuietHandler):
    """다른 출처. `Access-Control-Allow-Origin` 없이 429 를 줘, 브라우저 fetch 는 상태를 읽지 못한다 (사이트 앞 방화벽 차단처럼)."""

    def do_GET(self) -> None:
        self.send_response(429)
        self.send_header('Retry-After', '7')
        self.send_header('Content-Length', '0')
        self.end_headers()


class CountingEntryHandler(EntryHandler):
    """첫 화면이 같은 출처 API 를 3번, 다른 출처 API(`api_url`)를 사전 요청이 따라가는 헤더로 1번 부른다 (6번 확인).

    요청이 모두 끝난 뒤에 준비 쿠키를 심는다. jibsa 는 이 쿠키를 보고 첫 화면을 떠나므로, 떠날 때 서버가 받은 수가 정해진다.
    """

    api_url: str = ''

    def do_GET(self) -> None:
        self._count()
        if self.path != '/':
            self._send(200, b'{}', 'application/json')
            return
        script = (
            "Promise.all([fetch('/api/a'), fetch('/api/b'), fetch('/api/c'),"
            f" fetch('{self.api_url}api/entry', {{headers: {{'{PREFLIGHT_HEADER}': '1'}}}})])"
            f".then(() => {{ document.cookie = '{READY_COOKIE}=1; path=/' }})"
        )
        self._send(200, f'<html><body><script>{script}</script></body></html>'.encode(), 'text/html')


class CorsApiHandler(QuietHandler):
    """다른 출처 API. CORS 와 `PREFLIGHT_HEADER` 를 허용하고, 받은 요청을 메서드와 경로로 센다 (6번 확인)."""

    def _reply(self, status: int, body: bytes) -> None:
        key = f"{self.command} {self.path.split('?')[0]}"
        self.site.counts[key] = self.site.counts.get(key, 0) + 1
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', PREFLIGHT_HEADER)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._reply(204, b'')

    def do_GET(self) -> None:
        self._reply(200, b'{"ok": true}')


def client(source: str, entry_url: str) -> Client:
    options = BrowserOptions(source=source, entry_url=entry_url, ready_cookie=READY_COOKIE)
    return Client(transport=BrowserTransport(options), timeout=20)


def check_requests(entry: Site) -> None:
    with client('browser-check', entry.url) as first:
        data = first.get(f'{entry.url}api/data')
        check(data.status_code == 200 and data.json().get('ok') is True, '1. 첫 화면을 열고 GET 요청으로 데이터를 받음')
        cookie = data.json().get('cookie', '')
        check(f'{READY_COOKIE}=1' in cookie and 'sid=abc' in cookie, f'1. 요청에 첫 화면이 심은 쿠키가 실림 ({cookie!r})')
        echo = first.post(f'{entry.url}api/echo', json={'q': '역삼동'})
        check(echo.json() == {'q': '역삼동'}, '1. POST 본문이 그대로 감')
        big = first.get(f'{entry.url}api/big')
        check(
            big.status_code == 200 and big.content == BIG_BODY,
            f'1. 1MB 넘는 본문({len(BIG_BODY)}바이트)을 브라우저 안에 두었다가 나눠 받음 (HTTP {big.status_code}, {len(big.content)}바이트)',
        )
        # 너무 일찍 끝나도(타이머 단위 실수 등으로 정상 응답이 잘림) 실패로 본다
        for what, path, said in (('헤더가 오지 않는 응답이', 'stall-head', '응답이'), ('멈춘 본문이', 'stall', '응답 본문이')):
            started = time.monotonic()
            try:
                first.get(f'{entry.url}api/{path}', timeout=STALL_TIMEOUT_SECONDS)
            except ReadTimeout as error:
                took = time.monotonic() - started
                check(
                    said in str(error) and STALL_TIMEOUT_SECONDS * 0.9 <= took < STALL_SECONDS,
                    f'1. {what} {STALL_TIMEOUT_SECONDS:g}초 timeout 에 ReadTimeout 으로 끝남 ({took:.1f}초, {error})',
                )
            else:
                check(False, f'1. {what} ReadTimeout 으로 끝남 (끝나지 않고 응답이 왔다)')
        limited = first.get(f'{entry.url}api/stall-429', timeout=STALL_TIMEOUT_SECONDS)
        retry_after = limited.headers.get('retry-after')
        check(
            limited.status_code == 429 and retry_after == STALL_RETRY_AFTER,
            f'1. 본문이 멈춘 429 를 Retry-After 와 함께 429 로 알아봄 (HTTP {limited.status_code}, Retry-After {retry_after})',
        )
    check(entry.counts.get('/') == 1, f"1. 첫 화면을 한 번 열었음 ({entry.counts.get('/')}번)")

    with client('browser-check', entry.url) as second:
        data = second.get(f'{entry.url}api/data')
        check(entry.counts.get('/') == 1, f"2. 다시 띄울 때 첫 화면을 열지 않음 (첫 화면 {entry.counts.get('/')}번)")
        check(f'{READY_COOKIE}=1' in data.json().get('cookie', ''), '2. 남긴 쿠키로 요청함')


def check_async_requests(entry: Site) -> None:
    async def run() -> tuple[Response, Response]:
        options = BrowserOptions(source='browser-check-async', entry_url=entry.url, ready_cookie=READY_COOKIE)
        transport = AsyncBrowserTransport(BrowserTransport(options))
        async with AsyncClient(transport=transport, timeout=20) as checker:
            return (
                await checker.get(f'{entry.url}api/data'),
                await checker.post(f'{entry.url}api/echo', json={'q': '역삼동'}),
            )

    data, echo = asyncio.run(run())
    cookie = data.json().get('cookie', '') if data.status_code == 200 else ''
    check(f'{READY_COOKIE}=1' in cookie, f'5. 비동기 transport 로 첫 화면을 열고 쿠키를 실어 GET 함 ({cookie!r})')
    check(echo.json() == {'q': '역삼동'}, '5. 비동기 transport 로 POST 본문이 그대로 감')


@contextmanager
def allow_local_network() -> Iterator[None]:
    """(이 확인에서만) Chromium 의 로컬 네트워크 접근 차단(Local Network Access)을 끈 채 브라우저를 띄우게 한다.

    jibsa 는 첫 화면 탭을 브라우저 안에서 만든 빈 페이지로 바꿔 두는데(`_fulfill_blank`), Chromium 은 주소가 없는 이 페이지를
    인터넷 페이지로 보고 127.0.0.1 의 다른 포트(가짜 차단 사이트)로 가는 요청을 `LocalNetworkAccessPermissionDenied` 로
    막는다 (2026-11-10 로컬 실측). 실제 사이트는 인터넷 주소라 이 차단과 무관하다.

    scrapling 이 넘기는 `--disable-features` 값에 하나를 더한다. 같은 스위치를 하나 더 넘기면 안 된다: scrapling 은
    extra_flags 를 받으면 플래그를 `list(set(...))` 로 합쳐 순서가 실행마다(PYTHONHASHSEED) 바뀌고, Chromium 은 같은 스위치의
    마지막 값만 써서 이 확인이 무작위로 실패했다 (2026-11-10 실측: 시드 0·1·5 실패, 2·3·4 통과). scrapling 은 이 목록을
    import 할 때 자기 모듈로 가져가 그쪽(`_base`)을 바꾼다. 목록을 옮기거나 `--disable-features` 를 빼면 여기서 실패해 알 수 있다.
    """
    original = (scrapling_base.DEFAULT_ARGS, scrapling_base.STEALTH_ARGS)
    patched = tuple(
        tuple(f'{arg},LocalNetworkAccessChecks' if arg.startswith('--disable-features=') else arg for arg in args)
        for args in original
    )
    if patched == original:
        raise RuntimeError('scrapling 이 --disable-features 를 넘기지 않아 로컬 네트워크 접근 차단을 끌 수 없다')
    scrapling_base.DEFAULT_ARGS, scrapling_base.STEALTH_ARGS = patched  # type: ignore[assignment]
    try:
        yield
    finally:
        scrapling_base.DEFAULT_ARGS, scrapling_base.STEALTH_ARGS = original


def check_blocked(entry: Site, blocked: Site) -> None:
    with allow_local_network(), client('browser-check', entry.url) as checker:
        limited = checker.get(f'{blocked.url}limited')
    check(
        limited.status_code == 429 and limited.headers.get('retry-after') == '7',
        f"3. CORS 없이 막힌 429 를 알아봄 (HTTP {limited.status_code}, Retry-After {limited.headers.get('retry-after')})",
    )


def check_request_counts() -> None:
    api = Site(CorsApiHandler)
    entry = Site(type('CountingEntry', (CountingEntryHandler,), {'api_url': api.url}))
    hosts = frozenset({urlsplit(entry.url).netloc, urlsplit(api.url).netloc})
    limiter = RateLimiter('browser-check-count', RateLimitPolicy(min_interval=0, max_per_minute=1000))
    transport = BrowserTransport(BrowserOptions(
        source='browser-check-count', entry_url=entry.url, ready_cookie=READY_COOKIE, api_hosts=hosts,
        rate_limiter=limiter,
    ))
    # 실제 클라이언트처럼 우리 요청은 httpx 훅이 센다 (`BaseHTTPClient.rate_limit_hooks`)
    with allow_local_network(), Client(transport=transport, timeout=20, event_hooks=limiter.event_hooks()) as counted:
        ours = counted.get(f'{api.url}api/ours', headers={PREFLIGHT_HEADER: '1'})
    check(
        ours.status_code == 200 and api.counts.get('OPTIONS /api/ours') == 1,
        f"6. 다른 출처로 보낸 우리 요청에 사전 요청이 따라감 (HTTP {ours.status_code}, OPTIONS {api.counts.get('OPTIONS /api/ours')}번)",
    )
    # 첫 화면 문서(/)와 favicon 은 사이트 API 가 아니라 세지 않는다
    reached = sum(count for path, count in entry.counts.items() if path.startswith('/api/')) + sum(api.counts.values())
    recorded = limiter.status()['requests_last_minute']
    check(reached == recorded, f'6. 사이트 API 에 닿은 요청을 요청 제한에 한 번씩 셈 (서버가 받은 {reached}건, 기록 {recorded}건)')
    if reached != recorded:
        print(f'     첫 화면 사이트 {entry.counts}, 다른 출처 API {api.counts}', flush=True)


def browser_processes() -> dict[int, str]:
    """jibsa 가 띄운 Chromium·드라이버로 보이는 프로세스 (pid → 명령줄)."""
    if sys.platform == 'win32':
        command = [
            'powershell', '-NoProfile', '-Command',
            "Get-CimInstance Win32_Process | ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.CommandLine }",
        ]
    else:
        command = ['ps', '-axo', 'pid=,command=']
    out = subprocess.run(command, capture_output=True, text=True, errors='replace', check=False).stdout
    found: dict[int, str] = {}
    for line in out.splitlines():
        pid, _, cmdline = line.strip().partition(' ')
        if pid.isdigit() and any(marker in cmdline for marker in BROWSER_PROCESS_MARKERS):
            found[int(pid)] = cmdline[:150]
    return found


def interrupt_child() -> None:
    """(따로 띄운 프로세스) 느린 첫 화면을 여는 중에 Ctrl+C 를 흉내 내고 걸린 시간을 알린다."""
    entry = Site(EntryHandler)
    fired: list[float] = []

    def fire() -> None:
        # 브라우저가 첫 화면을 요청한 뒤(Chromium 은 이미 떴다) 보낸다. 2분 안에 요청이 안 오면 보내지 않아 아래에서 실패한다
        if entry.slow_started.wait(120):
            time.sleep(0.5)
            fired.append(time.monotonic())
            _thread.interrupt_main()

    threading.Thread(target=fire, daemon=True).start()
    try:
        with client('browser-check-slow', f'{entry.url}slow') as slow:
            slow.get(f'{entry.url}api/data')
    except KeyboardInterrupt:
        # with 를 빠져나오며 클라이언트를 닫았다. 하던 브라우저 일을 기다리지 않아야 한다
        print(json.dumps({'closed_after': time.monotonic() - fired[0]}), flush=True)
        return
    print(json.dumps({'error': 'Ctrl+C 를 받기 전에 요청이 끝났다'}), flush=True)


def check_interrupt() -> None:
    before = browser_processes()
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, __file__, '--interrupt-child'], capture_output=True, text=True, errors='replace',
        timeout=SLOW_SECONDS + 120, check=False,
    )
    took = time.monotonic() - started
    results = [json.loads(line) for line in done.stdout.splitlines() if line.startswith('{')]
    closed_after = results[-1].get('closed_after') if results else None
    check(
        closed_after is not None and closed_after < INTERRUPT_LIMIT_SECONDS,
        f'4. Ctrl+C 뒤 {INTERRUPT_LIMIT_SECONDS:g}초 안에 끝남 '
        f'(Ctrl+C → 닫기까지 {closed_after if closed_after is None else round(closed_after, 2)}초, 프로세스 전체 {took:.1f}초)',
    )
    if closed_after is None:
        print(done.stdout[-2000:], done.stderr[-2000:], sep='\n', flush=True)

    deadline = time.monotonic() + LEFTOVER_WAIT_SECONDS
    leftover = {pid: cmd for pid, cmd in browser_processes().items() if pid not in before}
    while leftover and time.monotonic() < deadline:
        time.sleep(0.5)
        leftover = {pid: cmd for pid, cmd in browser_processes().items() if pid not in before}
    check(not leftover, f'4. 끝난 뒤 Chromium·드라이버가 남지 않음 (남은 프로세스 {len(leftover)}개)')
    for pid, cmd in leftover.items():
        print(f'     {pid} {cmd}', flush=True)


def main() -> None:
    if '--interrupt-child' in sys.argv:
        interrupt_child()
        return
    print(f'상태 폴더: {os.environ["JIBSA_STATE_DIR"]}', flush=True)
    entry = Site(EntryHandler)
    check_requests(entry)
    check_blocked(entry, Site(BlockedHandler))
    check_interrupt()
    check_async_requests(entry)
    check_request_counts()
    if failures:
        print(f'\n{len(failures)}개 실패', flush=True)
        sys.exit(1)
    print('\n모두 통과', flush=True)


if __name__ == '__main__':
    main()
