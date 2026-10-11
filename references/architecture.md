# Architecture

jibsa 의 계층 구조와, 명령 하나가 실행될 때 요청이 흐르는 경로. 형식 규칙은
[code-style.md](code-style.md), provider 모듈 작성 규칙은
[provider-conventions.md](provider-conventions.md), 출력 형식은
[output-contract.md](output-contract.md), 소스 고유 구현은 [직방](providers/zigbang.md)·[네이버](providers/naver.md)·[당근](providers/daangn.md)
개발 가이드를 본다.

## 계층

```
cli/                 Typer 명령. 인자 검증 → service 호출 → emit / handle_errors
 └─ providers/<source>/service/     여러 엔드포인트를 묶어 Listing 으로 정규화 (기능별 모듈)
     └─ providers/<source>/api/        소스 API 그대로: client.py (엔드포인트 하나 = 메서드 하나, run_request_*),
                                        request/·response/ 모델
         └─ core/http.py BaseHTTPClient   httpx 클라이언트 + 요청 제한 훅
```

각 계층은 아래 계층만 안다. 새 소스를 추가하면 `cli/app.py` 의 `limits` 명령 client 목록도 함께 고친다.

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

- 공통 필드: `url_schema`, `verify`, `proxy`, `timeout`, `user_agent`, `rate_limit`.
  `extra='forbid'` 라 오타 난 설정은 생성 시점에 실패한다.
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
  `JIBSA_STATE_DIR` > `$XDG_CACHE_HOME/jibsa` > `~/.cache/jibsa`.
- `RateLimiter.reserve()` 가 `flock` 잠금 안에서 다음 슬롯을 예약하고, 실제 대기(`sleep`)는
  잠금 밖에서 한다. Windows 는 `fcntl` 이 없어 잠금 없이 동작한다.
- 슬롯까지 `max_wait`(60초)보다 오래 기다려야 하면 기다리지 않고
  `RateLimitedError(reason='budget')`.
- 429 응답을 받으면 `on_rate_limited` 가 쿨다운을 걸고 곧바로
  `RateLimitedError(reason='cooldown')` 를 던진다. 쿨다운(최소 2분)이 재시도 대기 상한(60초)보다
  길어 tenacity 재시도는 어차피 로컬에서 거절되기 때문이다. `RateLimitedError` 는
  `HTTPStatusError` 가 아니므로 재시도 대상이 아니다.
- 연결 방식: `BaseHTTPClient.rate_limit_hooks()` / `async_rate_limit_hooks()` 를 httpx
  클라이언트의 `event_hooks` 로 넘긴다. 요청 전 훅이 슬롯을 기다리고, 응답 훅이 429 를 처리한다.

소스별 기본 정책 값은 각 client 의 `default_rate_limit` ClassVar 에 있다. 사용자에게 보여 주는 정책 표는
[공통 사용 규칙](../docs/common.md#요청-제한과-limits)에 있으니, 정책을 바꾸면 그 표도 함께 고친다.
