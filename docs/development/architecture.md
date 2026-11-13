# Architecture

jibsa 의 계층 구조와, 명령 하나가 실행될 때 요청이 흐르는 경로. 형식 규칙은
[code-style.md](code-style.md), provider 모듈 작성 규칙은
[provider-conventions.md](provider-conventions.md), 출력 형식은
[output-contract.md](output-contract.md), 소스 고유 구현은 [직방](providers/zigbang.md)·[네이버](providers/naver.md)·[당근](providers/daangn.md)·[다방](providers/dabang.md)
개발 가이드를 본다.

## 계층

```
cli/                 Typer 명령. 인자 검증 → service 호출 → emit / handle_errors
 └─ providers/<source>/service/     여러 엔드포인트를 묶어 Listing 으로 정규화 (기능별 모듈)
     └─ providers/<source>/api/        소스 API 그대로: client.py (엔드포인트 하나 = 메서드 하나, run_request_*),
                                        request/·response/ 모델
         └─ core/http.py BaseHTTPClient   httpx 클라이언트 + 요청 제한 훅
             └─ core/browser.py BrowserTransport   httpx 요청을 사이트 첫 화면을 연 Chromium 안의 fetch 로 보낸다
```

각 계층은 아래 계층만 안다. 새 소스를 추가하면 `cli/app.py` 의 `limits` 명령 client 목록도 함께 고친다.

소스끼리는 서로 모른다. `providers/<source>/` 와 `cli/<source>.py` 는 다른 소스의 provider·CLI 코드를 import 하지 않고, 공통
코드(`core/`, `cli/output.py` 등)만 쓴다. 한 소스가 못 찾은 이름을 다른 소스로 대신 찾으면 그 소스 웹과 다른 결과가 나오고,
한 소스의 요청 제한·장애가 다른 소스 명령으로 번진다. 예전에는 당근이 못 찾은 이름의 좌표를 직방(막히면 네이버)으로 찾았다
(#215 에서 뺌). 다른 소스가 필요하면 에러 `hint` 에 그 명령을 글로만 알린다 (`jibsa naver search redevelopment …`). 소스 목록을
모두 아는 곳은 `cli/app.py`(명령 등록, `limits`)뿐이다. `tests/test_cli.py` 의 `test_sources_do_not_import_each_other` 가 막는다.

- **client** 는 HTTP 호출과 응답 검증만 한다. 응답을 `<Source>{Action}ResponseModel`
  로 검증해 돌려줄 뿐, 만원 환산이나 만료 판정 같은 해석은 하지 않는다.
- **service** 는 client 메서드를 조합해 검색·상세 흐름을 만들고, 소스 응답을
  `core.listing.Listing` / `ListingDetail` 로 바꾼다. 만료 매물 거르기, 단위 환산,
  주소 조립, `JibsaError` 변환이 여기서 일어난다. 함수는 첫 인자로 client 를 받는다
  (`search_listings(client, region, ...)`).
- **cli** 는 옵션 파싱(`split_csv`, `require_korea`), client 생성(`with XxxClient() as client`),
  출력(`emit`)만 한다. 비즈니스 로직을 넣지 않는다.

검색 service 가 서버 필터 결과를 어떻게 다루는지는
[서버 필터와 클라이언트 후처리](provider-conventions.md#서버-필터와-클라이언트-후처리)를 따른다.

## BaseHTTPClient

`core/http.py` 의 `BaseHTTPClient(BaseModel, ABC)` 가 모든 provider client 의 기반이다.
pydantic 모델이 **검증된 설정 객체**이자 **httpx 클라이언트 팩토리** 역할을 함께 한다.

- 공통 필드: `url_schema`, `verify`, `proxy`, `timeout`, `rate_limit`. `extra='forbid'` 라 오타 난 설정은 생성 시점에 실패한다.
  UA 는 브라우저가 맡아 필드가 없다. `verify`·`proxy` 는 브라우저에 넘긴다. `verify` 는 Chromium 이 받는 켜기·끄기만 받는다
  (Chromium 은 인증서 파일을 받지 않고 내장 목록과 OS 에 설치된 인증서를 믿는다). `timeout` 은 응답 헤더가 올 때까지(연결 포함)와
  본문 조각 사이 간격의 제한이다. httpx 의 읽기 제한처럼 조금씩 계속 오는 응답은 전체가 더 길어도 받는다 (`core.browser._fetch_arguments`).
- 브라우저 설정: ClassVar `browser_entry_url`(처음 열 화면)·`browser_ready_cookie`·`browser_discard_statuses` 와, 호스트
  필드에서 만드는 property `browser_api_hosts` (호스트 필드를 바꿔도 어긋나지 않게). 서브클래스는
  `browser_transport()` / `async_browser_transport()` 를 httpx 클라이언트의 `transport` 로 넘긴다
  ([브라우저 요청](#브라우저-요청)).
- 서브클래스는 `_client` / `_async_client` 를 `@cached_property` 로 만든다. `close()` 가
  `self.__dict__.pop('_client', None)` 으로 꺼내 닫으므로 이름이 정확히 같아야 한다.
  (`@cached_property` 와 `@abstractmethod` 는 함께 쓸 수 없어 베이스에서는 일반 property 로 선언한다.)
- `close()` 는 sync 만, `aclose()` 는 async 와 sync 를 모두 닫는다. 닫은 뒤 다시 접근하면
  새 클라이언트를 만들므로 인스턴스를 재사용할 수 있다.
- `with` / `async with` 를 지원한다. CLI 와 service 호출부는 항상 컨텍스트 매니저로 쓴다.

## 요청 제한

`core/ratelimit.py`. 비공식 API 가 봇 차단(429)을 걸기 때문에, **같은 소스를 쓰는 모든
jibsa 프로세스가 하나의 상태 파일을 공유**한다. LLM 이 명령을 연달아 실행해도 간격이 지켜진다.

- 상태 파일: `<state_dir>/ratelimit/<source>.json`. `state_dir` 은
  `JIBSA_STATE_DIR` > `$XDG_CACHE_HOME/jibsa` > `~/.cache/jibsa`. 같은 폴더의 `next/` 에는 매물 검색
  이어 받기 표(`jibsa.cli.paging`)를 하루 동안 둔다.
- `RateLimiter.reserve()` 가 `flock` 잠금 안에서 다음 슬롯을 예약하고, 실제 대기(`sleep`)는
  잠금 밖에서 한다. Windows 는 `fcntl` 이 없어 `msvcrt.locking` 으로 같은 잠금을 건다.
- 슬롯까지 `max_wait`(60초)보다 오래 기다려야 하면 기다리지 않고
  `RateLimitedError(reason='budget')`.
- 429 응답을 받으면 `on_rate_limited` 가 쿨다운을 걸고 곧바로
  `RateLimitedError(reason='cooldown')` 를 던진다. 쿨다운(최소 2분)이 재시도 대기 상한(60초)보다
  길어 tenacity 재시도는 어차피 로컬에서 거절되기 때문이다. `RateLimitedError` 는
  `HTTPStatusError` 가 아니므로 재시도 대상이 아니다.
- 연결 방식: `BaseHTTPClient.rate_limit_hooks()` / `async_rate_limit_hooks()` 를 httpx
  클라이언트의 `event_hooks` 로 넘긴다. 요청 전 훅이 슬롯을 기다리고, 응답 훅이 429 를 처리한다.
  훅은 transport 바깥이라 브라우저로 보내는 요청도 그대로 거친다.
- 브라우저가 첫 화면을 열 때 페이지 JS 가 스스로 부르는 사이트 API(XHR·fetch)는 훅을 거치지 않아
  `RateLimiter.record(n)` 으로 최근 요청에 남긴다 (분당 상한에 든다). 첫 화면을 열다 실패해도 그때까지 나간 요청을 남긴다.
  브라우저가 다른 출처 API 에 보내는 CORS 사전 요청(OPTIONS)도 훅을 거치지 않아, CDP 로 보고 나갈 때마다 1건씩 남긴다
  (`count_preflight`, 첫 화면과 우리 요청 모두). 사전 요청 결과를 기억하라는 헤더가 없는 사이트는 요청마다 OPTIONS 가 따라가,
  세지 않으면 서버로 가는 요청이 정책의 2배까지 된다 (직방 실측은 [직방 브라우저 요청](providers/zigbang.md#브라우저-요청)).
  당근 GraphQL 도 다른 출처라 사전 요청이 따라가고, 같은 출처로 보내는 네이버·다방은 사전 요청이 없다.
  `scripts/ci/browser_check.py` 의 6번이 가짜 사이트로 서버가 받은 수와 기록한 수가 같은지 본다.
  첫 화면 문서나 그 요청 중 429 가 있으면 쿨다운을 건다 (제한을 끈 정책이면 걸지 않고, 우리 요청이 받는 429 를 보통 재시도가
  다룬다). 쿨다운은 우리 요청의 429 처럼 정책 값과 그 응답의 `Retry-After` 중 긴 쪽이고, 사이트 밖(광고·분석) 응답의 429 는
  보지 않는다. 다른 출처 API 가 CORS 허용 없이 준 429(직방·당근)와 load·쿠키 기다림 뒤에 온 429 는 첫 화면 단계에서 보지
  못하지만, 다음 우리 요청이 같은 429 를 받아 쉬므로 손해는 요청 1건이라 두었다 (`_BrowserState.on_entry_rate_limited`). 첫 화면을 연 뒤 페이지 JS 가 더 부른 요청은 명령이 끝날 때 센다 (탭을 빈 페이지로 바꿔 거의 없다). 첫 화면 탭에서
  보낸 우리 요청 중 사이트 API 호스트로 간 것만 보낼 때 세어 빼므로, 다른 호스트로 간 요청이나 실패한 요청 때문에 어긋나지 않는다.
- 첫 화면 요청은 미리 슬롯을 잡지 않고 연 뒤에 센다. 몇 건일지 열기 전에는 모르고(네이버 18~22건), 사람이 페이지를 열 때
  나가는 묶음과 같기 때문이다. 그래서 첫 화면을 새로 여는 명령(소스마다 30분에 한 번, 남긴 쿠키를 버린 뒤)은 분당 상한을 그
  묶음만큼 넘을 수 있고, 이어지는 우리 요청이 그만큼 기다린다. 일부러 둔 것이다. 쿨다운은 훅이 슬롯을 기다린 뒤에도 다시 보므로
  (`RateLimiter.acquire`) 첫 화면이 쿨다운 중인 사이트로 나가지는 않는다.

소스별 기본 정책 값은 각 client 의 `default_rate_limit` ClassVar 에 있다. 사용자에게 보여 주는 정책 표는
[공통 사용 규칙](../common.md#요청-제한과-limits)에 있으니, 정책을 바꾸면 그 표도 함께 고친다.

## 브라우저 요청

`core/browser.py`. 모든 요청은 httpx `Client` 의 `transport` 자리에 끼운 `BrowserTransport` 가 보낸다. base_url·auth·
요청 제한 훅·재시도는 httpx 그대로이고, 맨 아래 전송만 바뀐다.

```
client.get(...) → 요청 제한 훅 → BrowserTransport.handle_request
  첫 요청: scrapling StealthySession 으로 Chromium 을 띄워
    - 남긴 쿠키가 있고 첫 화면을 연 지 30분 안이면: 쿠키를 넣고 마지막 페이지 주소를 서버에 묻지 않고 띄운다
    - 아니면: 남긴 쿠키 중 만료 시각이 있고 살아 있는 것(방문자 식별 쿠키)을 넣고, 정적 파일은 CDP Fetch 로 막은 채
      browser_entry_url 을 실제로 열고 (문서 최대 40초, 그 뒤 load 는 최대 10초만 기다린다)
      browser_ready_cookie 가 있고, 이번 방문에서 사이트가 쿠키를 심거나 바꿨고, 그 뒤 0.5초 동안 쿠키가 더
      바뀌지 않을 때까지 기다린 뒤 (최대 5초. 문서가 4xx·5xx 면 둘 다 기다리지 않고 멈춘다)
      그 주소를 같은 빈 페이지로 바꾼다 (명령 동안 사이트 JS 가 API·지도 타일을 더 부르지 않는다).
      연 즉시 쿠키를 남겨, 같은 명령 안에서 새로 만든 같은 소스 클라이언트는 다시 열지 않는다
  그 페이지 안에서 fetch → 응답을 httpx.Response 로 바꿔 돌려준다 → 응답 훅
client.close() → 쿠키를 <state_dir>/browser/<source>.json 에 남기고 브라우저를 닫는다
```

- 헤더: 사이트 웹이 실제로 보내는 것과 같게 한다 (2026-11-12 네 소스 실측). 두 가지로 나뉜다.
  - 크롬이 붙이는 헤더는 크롬 값을 쓴다. UA·Origin·Referer·쿠키·Accept-Language·`sec-*` 는 fetch 에 넘기지 않아 브라우저가
    연 페이지 기준으로 붙인다. 웹에서 페이지 열기인 요청(당근 상세 HTML 등)은 `extensions={NAVIGATION_EXTENSION: True}` 를
    달면, 크롬이 페이지를 열 때 붙이는 `accept`·`upgrade-insecure-requests` 를 붙인다. 이 값은 크롬 버전마다 달라 고정하지 않고
    브라우저를 띄울 때마다 빈 페이지 띄우기(`_fulfill_blank`)에서 읽는다. `sec-fetch-*` 는 fetch 가 바꿀 수 없어 `cors` 로 나간다.
  - 사이트 웹 코드(axios·ky 등)가 붙이는 헤더는 provider 에 하드코딩한다. client 의 `base_header` 는 모든 요청에 붙는 헤더만
    두고, API 묶음마다 다른 헤더(다방 `V5_HEADERS`, 직방 `APT_HEADERS`, 당근 `graphql_header`)는 요청마다 `headers=` 로 붙인다.
    웹이 붙이지 않는 헤더는 넣지 않는다. 묶음마다 헤더가 다르고(다방 v5 만 `d-*`, 직방 `/apt` 만 `sdk-version`) 요청·페이지마다
    바뀌는 값(네이버 `sentry-trace`·`x-attest`)도 섞여, 첫 화면에서 자동으로 배워 쓰지 않는다. 헤더를 넣거나 고칠 때는 웹이 그
    API 에 실제로 붙이는지 실측(CDP `Network.requestWillBeSent`)이나 번들로 확인하고 날짜를 남긴다. 요청마다 바뀌는 웹 헤더는
    값 규칙을 따로 정하기 전에는 넣지 않는다.
- 쿠키: fetch 의 기본값(`same-origin`)이라 같은 출처에만 실린다. `include` 로 두면 `Access-Control-Allow-Origin: *`
  인 다른 출처 응답을 브라우저가 거절한다.
- CORS: 모든 요청을 첫 화면 탭에서 보내므로 사이트 API 는 첫 화면 출처의 CORS 를 허용해야 한다. 예전에는 허용하지 않는
  호스트를 그 주소의 빈 탭에서 보내는 '출처 탭' 장치가 있었지만, 쓰던 당근 옛 지역 API 를 #215 에서 빼 쓰는 소스가 없어
  지웠다. 다시 필요하면 git 기록(커밋 8a3930a)에서 되살린다.
- route 는 빈 탭 띄우기에만 잠깐 쓰고 탭을 다 띄운 뒤 걷는다. route 가 하나라도 걸려 있으면 patchright 가 CORS 사전
  요청(OPTIONS)을 서버에 보내지 않고 브라우저 안에서 허용으로 답해 실제 Chrome 과 달라진다. 그래서 첫 화면의 정적 파일은
  route 가 아니라 CDP Fetch(리소스 종류 패턴)로 막고, 페이지 요청은 route 가 아니라 `request` 이벤트로 센다. route 로 막을
  때는 첫 화면 JS 가 커스텀 헤더로 부르는 사이트 API(직방 4건, 당근 GraphQL 2건 등)에 OPTIONS 가 빠졌다 (2026-11-10 실측).
- 첫 화면을 다시 열 때(30분 뒤) 남긴 쿠키를 모두 버리면 사이트가 400일짜리 방문자 쿠키(네이버 `NNB`·`BUC`)를 새로 심어
  30분마다 새 방문자가 됐다. 브라우저를 닫았다 다시 온 사람처럼 만료 시각이 있는 쿠키만 넣고 연다 (`returning_cookies`).
- 응답 헤더: 다른 출처 응답은 CORS 가 허용한 헤더만 페이지 JS 에 보인다 (예: [직방](providers/zigbang.md#브라우저-요청)).
  빠진 헤더(`Retry-After` 등)는 브라우저 `response` 이벤트가 받은 전체 헤더로 채운다. 헤더 값은 바이트로 되돌려 httpx 에
  넣는다. 문자열 그대로 넣으면 한글 같은 글자가 든 헤더 하나로 정상 응답이 PARSE_ERROR 가 됐다 (`_response_headers`).
- CORS 에 막힌 응답: `Access-Control-Allow-Origin` 이 없는 다른 출처 응답(WAF 의 429·5xx 등)은 fetch 가 `TypeError` 로만
  실패하고 `response` 이벤트도 오지 않는다. 탭마다 CDP `Network` 이벤트(`responseReceivedExtraInfo`·`loadingFailed`)를
  받아 두었다가(`_BlockedResponses`) 그 상태·헤더로 본문 없는 응답을 만든다. 그래서 429 는 쿨다운, 5xx 는 재시도로
  예전(httpx)처럼 다룬다. 2xx 는 본문이 있어야 해 빈 본문으로 넘기지 않고 `CorsBlockedError`(재시도하지 않음, CLI 는
  `UPSTREAM_ERROR`)로 낸다. CORS 사전 요청(OPTIONS)이 거절돼 본 요청이 나가지 못하면 본 요청엔 응답이 없다. 사전 요청은
  다른 요청 ID 로 오고 `initiator` 가 본 요청을 가리켜 그 응답을 이어 둔다. 사전 요청이 받은 429·5xx 는 위처럼 응답으로
  만들고, 그 밖(헤더를 허용하지 않는 403 등)은 `CorsBlockedError` 다 (사전 요청의 403·404 를 응답으로 넘기면 '없는 ID'로
  읽힌다). CORS 표시가 없는 실패는 `loadingFailed.errorText`(Chromium 오류)로 가른다. 프록시에 닿지 못했으면
  (`net::ERR_PROXY_…` 등, `PROXY_NET_ERRORS`) 재시도하지 않는 `ProxyError`, 그 밖(연결 실패, 본문을 받다 끊김)은 오류를
  메시지에 붙인 `ConnectError` 다. 남긴 쿠키로 띄우면 서버에 묻지 않아 프록시 오류는 우리 요청에서 처음 드러난다. 기록은 주소로
  찾으므로 탭마다 한 번에 요청 하나만 보내고(브라우저 스레드가 차례로 보낸다), 요청이 끝나면 그 탭의 기록(CORS 사전 요청 것 포함)을 비운다.
- redirect: 모든 소스가 브라우저 안에서 따라간다. fetch 의 `redirect: 'manual'` 은 상태·Location 을 감춰 httpx 가 대신
  따라갈 수 없기 때문이다. 같은 출처 redirect 는 사이트 웹처럼 따라가고(끝이 JSON 이 아니면 `PARSE_ERROR`), CORS 를
  허용하지 않는 다른 출처(로그인 화면 등)로 넘기면 위처럼 첫 응답(3xx)이 돌아와 `UPSTREAM_ERROR` 다.
- 시간 제한: 응답 헤더가 client 의 `timeout` 안에 오지 않거나 본문 조각 사이가 `timeout` 을 넘으면 `ReadTimeout` 이다
  ([BaseHTTPClient](#basehttpclient) 의 `timeout`). 본문은 브라우저 안에서 조각마다 읽어 그 사이를 잰다 (`FETCH_SCRIPT`).
  본문이 멈춰도 3xx 이상이면 받은 상태·헤더로 본문 없는 응답을 만든다. 그래야 429 는 요청 제한이 `Retry-After` 로 쿨다운을 건다.
  요청 하나 전체의 상한은 httpx 처럼 두지 않는다.
- 큰 본문: 1MB(`BODY_CHUNK_BYTES`)보다 큰 응답 본문은 브라우저 안에 두었다가 1MB 씩 나눠 파이썬으로 옮긴다 (`_read_body`).
  patchright 의 evaluate 결과는 클수록 넘기는 시간이 훨씬 빨리 늘어, 97MB 를 한 번에 넘기면 44초, 1MB 씩이면 2초쯤 걸렸다.
  jibsa 소스 응답은 1MB 미만이라 이 경로와 본문 조각 사이 시간 초과는 CI 의 `브라우저 확인`에서만 돈다.
- 남긴 쿠키 버리기: 우리 요청이 `browser_discard_statuses`(기본 403)를 받으면 버려 다음 명령이 첫 화면부터 연다.
  429 는 요청량·IP 차단이라 버리지 않는다 (쿨다운 뒤 첫 화면을 연 지 30분 안이면 요청 1건으로 풀렸는지 본다). 첫 화면이 제대로 열리지 않으면 멈춘다:
  문서나 첫 화면의 사이트 API 가 429 면 쿨다운(`RateLimitedError`, 첫 화면 호스트가 `browser_api_hosts` 에 없어도)이고 같은
  이유로 쿠키는 남긴다 (`browser_ready_cookie` 를 못 받았으면 다음 명령이 쓰지 않고 다시 연다). 그 밖에는 그 첫 화면의 쿠키를
  남기지 않는다 (`keeps_entry_cookies`): 5xx 면 재시도하는 `HTTPStatusError` 이고 옛 쿠키 파일은 그대로 둔다 (사이트 장애라
  방문자 쿠키를 버리지 않는다. 다음 시도가 그 쿠키를 넣고 다시 연다). 그 밖의 4xx 나 다른 출처(로그인·보안 확인 화면 등)로
  넘어가면 `EntryPageError`(`JibsaError`, `UPSTREAM_ERROR`)이고 옛 쿠키 파일도 버린다 (거부된 방문자). 401·403·451 은 접속 차단이라
  `blocked: true` 를 붙인다 (`ENTRY_BLOCKED_STATUSES`. 업데이트로 풀리지 않음을 에이전트와 매일 감시가 이 필드로 안다). 4xx 를
  `HTTPStatusError` 로 내지 않는 것은 404·빈 403 을 '없는 ID'로 읽는 호출부(다방 `is_missing_id`, 직방 `unavailable_on_404`
  등)가 차단을 없는 매물로 알리기 때문이다. 5xx 의 `EntryStatusError` 를 상태별로 읽는 호출부(다방 학교 상세의 500)는
  `EntryOpenError` 를 먼저 걸러 낸다. 브라우저가 남긴 쿠키를 받지 않으면(`add_cookies` 실패) 버린다. 남겨 두면 30분 동안 모든
  명령이 같은 이유로 실패한다. 그 밖의 실패(빈 페이지 띄우기 시간 초과 등)에는 버리지 않는다. 남긴 페이지 주소가 지금
  `browser_entry_url` 과 출처가 다르면 (업데이트로 첫 화면이 바뀜) 남긴 쿠키를 쓰지 않고 첫 화면부터 연다.
- 첫 화면 실패: 문서(DOMContentLoaded)를 40초 안에 받지 못하거나 인증서를 믿지 못하면 `EntryPageError`(`NETWORK_ERROR`),
  프록시 오류는 `ProxyError` 라 재시도하지 않는다. 남긴 쿠키로 띄운 뒤 우리 요청에서 처음 드러난 인증서 오류는
  `CertificateError`(전송 오류, `NETWORK_ERROR` 와 인증서 hint)라 역시 재시도하지 않는다. 재시도마다 브라우저를 새로 띄우고 첫 화면 요청을 20건쯤 다시 보내기 때문이다. 그 밖의
  연결 실패와 서버에 묻지 않고 띄우는 빈 페이지의 시간 초과(브라우저가 멈춘 것)는 `ConnectError` 라 재시도한다. 첫 화면을
  여는 단계의 실패는 모두 `EntryOpenError` 표식을 함께 단다 (`EntryPageError`, 재시도하는 `EntryConnectError`·5xx 의
  `EntryStatusError`). Chromium 이 Playwright 띄우기 제한 시간(3분) 안에 뜨지 않으면 `BROWSER_UNAVAILABLE` 이지만 시스템
  라이브러리 hint 대신 잠시 뒤 다시 실행하라는 hint 를 단다. load 는 10초까지만 기다리고 넘어가 실패로 보지 않는다. load 는 사이트 밖 광고·분석
  스크립트까지 기다려, 그 호스트를 응답 없이 버리는 망(회사 방화벽 등)에서는 사이트가 멀쩡해도 첫 화면이 실패했다. 문서가
  4xx·5xx 면 load·`browser_ready_cookie` 를 기다리지 않고, 첫 화면 API 가 429 를 받았으면 쿠키를 기다리지 않는다 (막힌 사이트에
  페이지 요청이 더 나가고, 오류 화면이 심지 않는 쿠키를 5초 기다렸다).
  재시도하지 않는 실패(위 둘과 차단 응답, Chromium 을 못 띄움)는 소스·`proxy`(주지 않았으면 환경 변수 프록시)·`verify` 별로
  60초 동안 기억해, 실패를 삼킨 덤 조회 뒤의 요청이나 새로 만든 같은 설정의 클라이언트가 첫 화면을 다시 열지 않고 같은 에러를
  바로 낸다. 환경 변수가 없을 때 Chromium 이 보는 OS 프록시 설정을 바꾼 것은 알 수 없어 60초가 지나야 다시 연다. `EntryPageError` 는
  전송 오류가 아닌 jibsa 에러라 덤 조회가 삼키지 않는다. 프록시 오류(설정 오류·프록시에 닿지 못함)는 `ProxyError` 다.
  프록시가 한 사이트로의 연결만 거절한 것(`net::ERR_TUNNEL_CONNECTION_FAILED`)은 첫 화면에서 났으면 `EntryPageError`
  (`NETWORK_ERROR`, 프록시 hint), 우리 요청에서 났으면 메시지로 가른 `ProxyError` 다.
- 우리 요청 중 탭·브라우저가 닫히는 등 patchright 에러가 나면 브라우저를 닫고 `ConnectError` 로 재시도한다. 재시도는 남긴
  쿠키로 다시 띄운다 (닫힌 탭을 다시 쓰면 같은 에러만 난다).
- 클라이언트를 닫아야(`with`·`close()`) 브라우저 스레드와 Chromium 이 끝나고 쿠키가 남는다. 닫지 않으면 프로세스가 끝날
  때까지 남고, 메모리에서 정리될 때 자동으로 닫지 않는다 (브라우저 일은 브라우저 스레드에서만 할 수 있다). 비동기 `aclose()`
  는 동기 클라이언트도 다른 스레드에서 닫아 이벤트 루프를 막지 않는다. 여러 스레드가 같이 쓰다 한 스레드가 닫으면 그 뒤
  요청은 httpx 처럼 `RuntimeError` 다. 쿠키 파일은 다른 jibsa 프로세스가 그사이 지웠거나 첫 화면을 더 늦게 새로 열었으면
  남기지도 지우지도 않는다 (`_BrowserState.finish`·`discard_saved`).
- 클라이언트마다 Chromium 을 따로 띄운다. 한 명령에서 같은 소스를 여러 번 부르면 클라이언트 하나를 넘겨 쓴다 (당근 위치
  찾기는 본 조회의 클라이언트로 한다). 소스끼리는 부르지 않아([계층](#계층)) 한 명령이 다른 소스의 Chromium 을 띄우지 않는다.
- 첫 화면에서 받지 않는 것: 이미지·폰트·미디어·스타일과 지도 타일. 쿠키는 그대로 생긴다. 사이트 자체 API 는
  막지 않는다 (네이버는 막으면 `NNB` 등이 생기지 않았다).
- Chromium 은 `jibsa install-browser` 가 받는다 (`install_chromium`). 내려받기 진행은 stderr 가 터미널이거나
  `--verbose` 일 때만 보이고, 파이프로 읽으면 stderr 에 에러 JSON 만 간다 (실패 원인은 에러의 `output`).
  Chromium 이 없거나 시스템 라이브러리가 없거나 patchright 드라이버를 실행하지 못하거나(`OSError`, 설치가 깨짐 등) 그 밖의
  이유로 못 띄우면 재시도 없이 `BROWSER_UNAVAILABLE` 이다. 힌트는 늘 붙인다 (리눅스는 시스템 라이브러리 설치, 드라이버 실행
  실패는 jibsa 재설치, 그 밖은 `jibsa install-browser` 로 다시 받아 띄워 보기).
- 브라우저 일은 늘 transport 마다 띄운 전용 데몬 스레드 하나에서 차례로 한다 (`_BrowserThread`). 비동기
  `AsyncBrowserTransport` 도 동기 transport 를 감싸 같은 스레드에 일을 넘기고 `await` 로 기다린다 (`_acall`. 흐름이 한 벌이고
  동시에 보낸 요청도 차례로 나간다. 기다리다 취소되면 Ctrl+C 처럼 하던 일을 기다리지 않는다). 따로 스레드를 두는 것은
  patchright 동기 API 가 asyncio 이벤트 루프 안에서 불리지 못하고, 부를 때마다 자기 asyncio 루프를 그 스레드의 '도는 루프'로
  남기며, 한 번 띄운 브라우저는 띄운 스레드에서만 다룰 수 있기 때문이다. 부른 스레드에는 아무것도 남지 않아 CLI 메인 스레드·asyncio 루프 안(Jupyter)·여러 작업 스레드 어디서 같은
  클라이언트를 불러도 되고, 한 프로세스에서 여러 소스의 브라우저를 띄워도 된다. 예전에는 CLI 메인
  스레드에서 바로 부르고 남은 루프를 asyncio 비공개 함수(`_set_running_loop`)로 걷어 냈는데, 그 때문에 메인 스레드에서 띄운
  클라이언트를 다른 스레드나 루프 안에서 쓰거나 닫으면 `RuntimeError` 였다 (2026-11-10 리뷰로 바꿈). 스레드를 오가는 비용은
  호출당 약 40µs 다 (같은 날 실측).
  Ctrl+C 는 메인 스레드가 브라우저 일을 기다리는 동안 0.1초마다 확인한다(`WAIT_POLL_SECONDS`, 한 번에 끝까지 기다리면 Windows
  에서 끊기지 않는다). 끊기면 하던 브라우저 일을 기다리지 않고 바로 끝내고(그 명령에서 바뀐 쿠키는 남기지 않는다), 데몬
  스레드라 프로세스 종료도 기다리지 않는다. 드라이버(node)는 파이프가 끊기면 Chromium 을 닫는다. 2026-11-10 리눅스 실측: 첫
  화면을 여는 중에 SIGINT 를 jibsa 에만 보내도, 프로세스 그룹 전체(터미널 Ctrl+C)에 보내도 0.2~0.3초 뒤 `INTERRUPTED` 한 줄만
  내고 끝났고 Chromium·드라이버가 남지 않았다 (바꾸기 전 메인 스레드 방식과 같다). 세 운영체제(Windows 포함)에서는 CI 의
  `브라우저 확인`이 가짜 사이트로 Ctrl+C 를 흉내 내 1초 안에 끝나는지와 남은 프로세스를 본다 (`scripts/ci/browser_check.py`,
  브라우저·설치 관련 파일을 고친 PR·릴리스·매주 월요일).
  CLI·매일 감시는 동기만 쓰므로 비동기 쪽을 고치면 `AsyncClient` 로 직접 불러 확인한다.
- 프록시: client 의 `proxy` 가 없으면 환경 변수(`HTTPS_PROXY`·`ALL_PROXY`·`NO_PROXY`)를 읽어 브라우저에 넘긴다.
  httpx 는 transport 를 넘기면 환경 변수 프록시를 쓰지 않고, Chromium 은 GNOME 리눅스·Windows·macOS 에서 환경 변수
  대신 OS 설정을 보기 때문이다. 환경 변수가 없으면 Chromium 이 OS 프록시 설정을 쓴다. `NO_PROXY=*` 는 httpx 처럼
  프록시를 아예 쓰지 않는다는 뜻이라 `--no-proxy-server` 로 OS 프록시도 건너뛴다. Chromium 은 http·https·socks4·socks5
  만 받아 `socks5h`·`socks4a` 는 socks5·socks4 로 바꿔 넘기고(Chromium 의 SOCKS 는 프록시가 이름을 푼다), 해석할 수
  없는 주소·쓸 수 없는 스킴·아이디·비밀번호가 있는 SOCKS 프록시는 `ProxyError` 로 멈춘다. CLI 는
  `ProxyError` 를 프록시 설정을 가리키는 hint(`PROXY_HINT`: 환경 변수, 없으면 OS 프록시 설정, 바로 연결하려면
  `NO_PROXY=*`)와 함께 `NETWORK_ERROR` 로 낸다.
