# Provider Conventions

`providers/<source>/` 모듈을 쓰는 규칙. 형식 규칙은 [code-style.md](code-style.md),
계층 구조와 요청 제한은 [architecture.md](architecture.md) 를 본다.

## 모듈 구성

```
providers/<source>/
├── __init__.py       # 자주 쓰는 공개 진입점만 re-export (CLI 는 service 모듈에서 바로 가져와 전부 내보낼 필요는 없다)
├── api/              # 아래층: 소스 API 를 그대로 옮긴 것. service 를 가져다 쓰지 않는다
│   ├── __init__.py   # 안내 docstring 만
│   ├── client.py     # <Source>Client(BaseHTTPClient) + run_request_* / arun_request_*
│   ├── request/      # 요청 파라미터·본문 모델 (service 와 같은 모듈 이름, 기준 7)
│   └── response/     # 응답 모델 (최상위 + 중첩 모델 모두, service 와 같은 모듈 이름, 기준 7)
└── service/          # 윗층: api 를 조합해 Listing 으로 정규화
    ├── __init__.py   # 모듈 안내 docstring 만 (re-export 없음)
    ├── common.py     # 두 모듈 이상이 쓰는 결과 모델·URL·안내 문구·상수
    ├── region.py     # 지역 이름·좌표 해석
    └── <기능>.py      # CLI 명령 묶음 하나 (listing, complex, real_price …)
```

- jibsa 에는 `dto.py` 가 없다. 중첩·공통 응답 모델(`ZigbangItemPinModel`,
  `NaverResponseModel[T]` 등)도 `response/` 에 둔다 (여러 기능이 쓰면 `response/common.py`). 공통 베이스는 최상위
  모델보다 위에 둔다.
- service 결과 모델(`ZigbangSearchResult`, `NaverComplexSummary`, `<Source>ListingDetail` 등)은
  CLI 출력용이므로 그 기능의 service 모듈에 두고 `BaseModel` + `extra='forbid'` 로 만든다.
- HTML 파싱처럼 소스 고유의 응답 처리 단계가 있으면 `api/` 안의 별도 모듈로 뺀다 (당근의 `api/relay.py`, `api/parser.py`).
- import 는 `service` → `api` 한 방향이다. `api/` 는 소스 API 를 그대로 옮긴 아래층이라 service·CLI 를 모른다.

### service 모듈을 나누는 기준

1. **모듈 하나는 CLI 명령 묶음 하나를 맡는다.** 명령 이름만 알면 고칠 파일을 찾을 수 있게 한다. 그 기능의 결과 모델·변환
   함수·안내 문구는 같은 모듈에 둔다. 소스별 명령 ↔ 모듈 대응은 각 소스 개발 가이드의 '명령과 요청 흐름' 표에 있다
   ([직방](providers/zigbang.md#명령과-요청-흐름)·[네이버](providers/naver.md#명령과-요청-흐름)·[당근](providers/daangn.md#명령과-요청-흐름)).
2. **두 모듈 이상이 쓰는 심볼은 `common` 에 둔다.** 한 모듈만 쓰면 그 모듈에 둔다.
3. **import 는 `common` → `region` → 기능 모듈 → 분기 모듈 방향으로만 한다.** 기능 모듈끼리는 서로 가져다 쓰지 않는다.
   두 기능 모듈이 같이 쓰게 되면 그 심볼을 `common` 으로 옮긴다 (기준 2). 분기 모듈(직방 `detail`: `listing` 명령의 ID
   분기)만 기능 모듈을 가져다 쓴다.
4. **모듈이 1,000줄을 넘으면 기능을 다시 나눈다** (당근 `complex` 에서 비교·주변 단지를 `compare` 로 뺐다).
5. **새 명령은 맞는 모듈에 넣는다.** 맞는 모듈이 없으면 새 모듈을 만들고 소스 문서의 표에 한 줄 추가한다.
6. CLI 와 테스트는 하위 모듈에서 바로 가져온다 (`from jibsa.providers.zigbang.service.stay import ...`).
   테스트가 상수를 바꿔 끼울 때(`monkeypatch.setattr`)도 그 상수를 쓰는 함수가 있는 모듈을 고친다.
7. **요청·응답 모델(`request/`·`response/`)은 service 와 같은 모듈 이름으로 나눈다.** 엔드포인트의 요청·응답 모델은
   그 엔드포인트를 부르는 service 모듈과 같은 이름의 모듈에 둔다 (`service/stay.py` 가 부르면 `request/stay.py`·
   `response/stay.py`). 그래서 기능 하나를 고칠 때 같은 이름의 세 파일만 보면 된다.
   - 두 기능 이상이 부르는 엔드포인트의 모델, 여러 기능의 모델이 같이 쓰는 중첩 모델, 기반 모델은 `common` 에 둔다.
     그래서 기능 모듈은 같은 패키지의 `common` 만 가져다 쓴다.
   - service 가 부르지 않는 엔드포인트(라이브러리용)는 경로가 같은 기능 모듈에 둔다.
   - 모듈이 작아도(모델 하나여도) 같은 이름으로 둔다. `client.py` 는 클래스 하나라 나누지 않는다.

## Action id 명명

엔드포인트마다 경로에서 **action id** 를 만들고, 그 엔드포인트의 모든 심볼을 action id 로 짓는다.
경로 파라미터는 빼고, 남은 세그먼트를 snake_case 로 `_` 로 이은 뒤 버전 세그먼트(`vN`)를 끝으로 옮긴다.
서비스 공통 접두어는 버린다.

| 소스 | 엔드포인트 | 버리는 접두어 | Action id |
| --- | --- | --- | --- |
| 직방 | `/house/property/v1/items/onerooms` | `/house/property` | `items_onerooms_v1` |
| 직방 | `/v3/items/{itemId}` | — | `items_v3` |
| 네이버 | `/front-api/v1/complex/pyeongList` | `/front-api` | `complex_pyeong_list_v1` |
| 네이버 | `/front-api/v1/complex/v2/pyeong/realPrice` (경로 가운데 버전이 또 있으면 그 버전) | `/front-api` | `complex_pyeong_real_price_v2` |
| 당근 | `/kr/api/v1/regions/keyword` | `/kr/api` | `regions_keyword_v1` |
| 당근 | `/map/{name1}/{name2}/{name3}` (페이지) | — | `map` |
| 당근 | `POST /graphql` 의 `articleFeed` (GraphQL) | — | `article_feed` |

GraphQL 은 오퍼레이션의 루트 필드 이름을 snake_case 로 쓴다. 루트 필드가 같은 오퍼레이션이 여럿이거나
페이지 action id 와 겹치면 뜻이 드러나는 이름으로 구분한다. 당근의 전체 목록과 구분한 사례는
[당근 개발 가이드](providers/daangn.md#action-id-목록)에 있다.

`{Action}` 은 PascalCase (`items_onerooms_v1` → `ItemsOneroomsV1`), 접두어는 소스 이름(`Zigbang`,
`Naver`, `Daangn`).

| 심볼 | 패턴 | 예 |
| --- | --- | --- |
| 엔드포인트 ClassVar | `{action}_endpoint` | `items_onerooms_v1_endpoint` |
| sync 메서드 | `run_request_{action}` | `run_request_items_onerooms_v1` |
| async 메서드 | `arun_request_{action}` | `arun_request_items_onerooms_v1` |
| 요청 파라미터 | `<Source>{Action}RequestParameterModel` | `ZigbangItemsOneroomsV1RequestParameterModel` |
| 요청 본문 | `<Source>{Action}RequestPayloadModel` | `ZigbangItemsListV1RequestPayloadModel` |
| 응답 | `<Source>{Action}ResponseModel` | `ZigbangItemsOneroomsV1ResponseModel` |

- 본문이 있는 엔드포인트만 `RequestPayloadModel` 을 쓰고, 메서드 인자 이름도 `payload` 로 한다.
  쿼리·경로만 있으면 `RequestParameterModel` 과 `parameter`.
- 엔드포인트 ClassVar 에는 경로 파라미터를 `{snake_case}` 자리표시자로 남기고 메서드에서
  `.format(item_id=parameter.item_id)` 로 채운다. 경로 파라미터 필드는 `Field(exclude=True)` 로
  쿼리 직렬화에서 뺀다.
- 경로를 action id 규칙대로 만들기 어렵다면 client 클래스 docstring 에 그 소스의 규칙을 한 문단으로
  적는다 (각 client 의 docstring 참고).
- 응답 모양이 같은 엔드포인트는 공통 베이스를 두고 빈 서브클래스로 action id 이름을 붙인다
  (`ZigbangItemsResponseModel` → `ZigbangItemsOneroomsV1ResponseModel`).

## Client 클래스

- `BaseHTTPClient` 를 상속하고 다음을 선언한다.
  - 엔드포인트 ClassVar 들
  - `source_name: ClassVar[str]` — 요청 제한 상태 파일 이름. `Source` Literal 값과 같게.
  - `default_rate_limit: ClassVar[dict[str, object]]` — `RateLimitPolicy` 필드
  - `host: str` 필드와 `base_url` property (`create_base_url` 사용)
  - `base_header` property — `User-Agent` 는 `self.user_agent`
- `_client` / `_async_client` 는 `@cached_property` 로 만들고 반드시
  `event_hooks=self.rate_limit_hooks()` (async 는 `async_rate_limit_hooks()`), `verify`, `timeout`,
  `proxy` 를 넘긴다.
- 토큰 같은 비밀 값 필드는 `Field(repr=False)`.

## 요청 메서드

엔드포인트마다 sync·async 쌍을 만든다. 본문은 같은 모양을 따른다.
CLI 와 service 는 sync 만 쓰고 async 변형(`arun_request_*`, `_async_client`, `async_rate_limit_hooks`)은 jibsa 를 라이브러리로
쓸 때의 공개 API 다. 저장소 안 호출부가 없어도 죽은 코드가 아니니 지우지 않는다. 엔드포인트를 고치면 async 쪽도 함께 고치고,
의심되면 그 메서드를 한 번 실제로 불러 확인한다 (2026-10-11 세 소스 모두 실제 호출로 동작 확인).
재시도 데코레이터는 client 모듈에 소스별로 한 번만 정의하고(`zigbang_retry`, `daangn_retry`,
`naver_retry`) 메서드에는 그 이름만 붙인다. 정책을 바꿀 때 한 곳만 고치면 된다.

```python
zigbang_retry = retry(
    retry=retry_if_exception(should_retry_idempotent),
    stop=stop_after_attempt(3),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)

@zigbang_retry
def run_request_items_onerooms_v1(
    self,
    parameter: ZigbangItemsOneroomsV1RequestParameterModel
) -> ZigbangItemsOneroomsV1ResponseModel:
    """..."""
    response = self._client.get(
        url=self.items_onerooms_v1_endpoint,
        params=parameter.model_dump(by_alias=True, exclude_none=True)
    )
    raise_for_status(response=response)
    return ZigbangItemsOneroomsV1ResponseModel.model_validate(response.json())
```

- **재시도.** 조회 전용이면 POST 라도 `should_retry_idempotent` (5xx/429 + timeout/transport).
  상태를 바꾸는 호출이 생기면 `should_retry_non_idempotent`. jibsa 에는 현재 조회만 있다.
  네이버는 예외다 ([네이버 개발 가이드](providers/naver.md)).
- **`raise_for_status`** 는 httpx 메서드가 아니라 `core.http.raise_for_status` 를 쓴다. 비공식 API 는
  거절 사유를 본문에만 담으므로 본문을 잘라(민감 키는 가림) 예외 메시지에 붙인다.
- **직렬화.** 쿼리는 `model_dump(by_alias=True, exclude_none=True)`, 본문은 `json=` 으로 같은 값을 넘긴다.
- **해석하지 않는다.** 메서드는 검증된 응답 모델을 그대로 돌려준다. 네이버의 `isSuccess: false` 처럼
  200 안의 실패도 여기서 판정하지 않고 service 의 `unwrap()` 이 처리한다.
- **docstring.** 첫 줄에 HTTP 메서드와 경로, 이어서 재시도 동작과 "요청 제한이 켜져 있으면 429 는 재시도
  없이 `RateLimitedError` 로 끝난다"를 적는다. 같은 동작을 반복하는 메서드는
  `Same retry behaviour as run_request_...` 로 줄이고, async 변형은
  `Async variant of run_request_...` 한 줄로 쓴다. 자세한 형식은
  [code-style.md](code-style.md#6-docstring).

## 요청·응답 모델

- 요청 모델은 `core.schema.RequestModel` (`extra='forbid'`, `populate_by_name=True`),
  응답 모델은 `ResponseModel` (`extra='allow'`) 을 상속한다. 비공식 API 가 예고 없이 필드를 더하므로
  응답 모델은 모르는 필드를 버리지 않는다.
- 응답 필드는 **소스가 빠뜨릴 수 있으면 `X | None = None`** 으로 둔다. 실제 응답에서 늘 오는 것을
  확인한 필드만 필수로 한다. 비공식 API 라 엄격한 필수 필드는 파싱 실패로 이어진다.
- 와이어 이름이 다르면 `Field(alias='camelCase')`. 기본값·별칭은 대입 위치에, 제약·`description` 은
  `Annotated` 안에 둔다 ([code-style.md](code-style.md#4-pydantic-선언)).
- 서버가 요구하는 특이한 직렬화는 모델의 `@model_serializer` 로 처리한다
  (예: 직방 `salesTypes[0]=전세&salesTypes[1]=월세`).
- 서버가 거절할 조합은 요청 모델의 `@field_validator` 로 미리 막는다 (예: 원룸 + 매매,
  `items/list` 15개 초과). CLI 에서 `ValidationError` 는 `INVALID_ARGUMENT` (exit 2) 가 된다.

## Service 함수

- 첫 인자는 client. 옵션은 키워드 전용(`*,`)으로 받는다.
- 소스 응답을 `Listing` / `ListingDetail` (또는 그 서브클래스 `<Source>ListingDetail`) 로 바꾼다.
  금액은 만원(`won_to_manwon`), 날짜는 `normalize_date`, 면적 평은 `m2_to_pyeong`,
  주소는 `join_address`. 본문(매물 설명)은 옮기지 않는다 (`output-contract.md` 의 내보내지 않는 정보).
- **만료 판정은 service 에서 한다.** 목록은 거래 불가 매물을 건너뛰고, 상세는
  `ListingUnavailableError(source, id, status=..., reason=...)` 를 던진다. 404 도
  `ListingUnavailableError` 로 바꾼다.
- 지역을 찾지 못하면 `RegionNotFoundError`, 소스가 그 지역을 다루지 않으면 `UnsupportedRegionError`.
- 원 사이트 URL 은 `article_url()` / `item_url()` 같은 헬퍼로 만든다.
- 요청 수를 늘리는 변경은 요청 제한 상한과 함께 검토한다.
- 목록 페이지 루프는 받은 개수로 할당량을 세고, 받은 뒤 뺀 매물은 다시 채우지 않는다
  (`output-contract.md` 의 개수 상한).

### 검색 조건 묶음

검색 조건이 많은 service 함수는 조건을 모델 하나로 받는다 (`search_listings(client, region, conditions=..., limit=...)`).

- 모델 이름은 `<Source><Kind>Conditions` 이고 `RequestModel` 을 상속한다 (`ZigbangRoomConditions`,
  `NaverListingConditions`, `DaangnListingConditions`). 값은 한국어 라벨·만원 그대로 두고 필드마다 `description` 을 단다.
- "어떤 매물인지"(거래 유형·가격·면적·층·옵션 …)만 담는다. 지역·반경·`limit`·정렬처럼 "어디서 몇 개 찾을지"는 함수
  인자로 따로 받는다.
- 목록 필드의 기본값은 `[]`(조건 없음)다. service 함수의 `conditions` 는 키워드 전용이고 `None` 이면 빈 조건이다.
- 요청 필드로 바꾸는 함수는 `<무엇>_filter_of(conditions)` 로 짓는다 (`room_filter_of`, `listing_filter_of`,
  `price_filter_of`, `complex_filter_of`). 같은 조건을 여러 요청이 쓰면 이 함수를 같이 쓴다.
- 입력 검사(범위·라벨·조합)는 CLI 에서 한다 (`split_csv`, `validate_ranges`, `typer.BadParameter`). 에러 문구와 exit
  code 가 출력 계약이라, 검사를 모델로 옮겨 경로를 바꾸지 않는다. 모델은 `handle_errors` 안에서 만든다. 모델이 조합을
  검사하는 소스는 그 소스 개발 가이드에 적는다.
- 여러 모듈이 쓰는 모델은 `service/common.py`, 한 기능만 쓰면 그 모듈에 둔다 ([나누는 기준](#service-모듈을-나누는-기준)).
- 소스마다 다른 점(필드 이름, 일부 명령만 받는 조건)은 그 소스 개발 가이드에 적는다.
- CLI 옵션 별칭 중 세 소스가 도움말까지 똑같이 쓰는 것(`PrettyOption`, 보증금·월세·매매가 하한·상한)은 `cli/options.py`
  에 둔다. 도움말이 다르면 각 소스 CLI 에 둔다.

## 서버 필터와 클라이언트 후처리

모든 provider 의 검색 구현은 아래 원칙을 따른다. 서버 필터를 적용한 조회와 조건 없는
목록을 받아 직접 거르는 대체 조회를 구분한다. 소스별로 어떤 경로가 서버 필터이고 무엇을
직접 거르는지는 각 provider 개발 가이드의 "페이지네이션과 조건 처리"에 적는다. 구현이 이
기준과 다르면 그 가이드에 위치와 이유를 적고, 가이드에 없다고 기준을 따른다고 단정하지 말고
코드를 확인한다.

### 서버 필터를 적용한 조회

1. 지원하는 검색 조건을 소스의 의미에 맞게 요청 모델로 변환해 서버에 보낸다.
2. 서버가 적용한 조건은 존중한다. 응답을 공통 모델로 정규화한 뒤 같은 조건을 다시 해석해
   매물을 제외하지 않는다. 특히 소스의 카테고리를 실제 건물 용도나 방 개수로 간주하지 않는다.
3. 중복 ID 와 거래 불가 매물은 제거한다. 거래 가능 여부는 응답에 제공된 상태·숨김·노출 제한
   정보로 판단하며, 목록에 없는 정보를 확인하려고 매물마다 상세를 자동 조회하지 않는다.
4. 한 매물에 여러 거래 조건이 있으면 검색에 맞는 거래 조건을 골라 그 가격을 출력한다.
   예를 들어 전세와 월세가 함께 있는 매물이 월세 검색에 반환되면 월세 조건을 출력한다.
   이는 매물 유형을 다시 거르는 작업과 구분한다.

거래 조건 선택에는 요청한 거래 유형과 해당 금액 범위를 사용한다. 관리비 포함 금액처럼
서버가 계산한 조건을 응답 필드만으로 재현할 수 없으면 누락 값을 0 으로 가정하거나
다른 기준으로 대체하지 않는다. 검색에 맞는 거래 조건을 선택할 수 없는 경우에는 임의의
대표 가격을 출력하지 않고, 해당 매물을 제외한 사유와 확인 한계를 결과의 `notes` 로 알린다.

응답의 카테고리가 요청 조건과 다르다는 이유만으로 서버 필터 실패를 단정하지 않는다.
필터 동작이 의심되면 클라이언트 후처리 전 원본 응답과 요청 조건을 대조해 확인하고,
확인된 소스 고유 예외는 해당 provider 개발 가이드에 근거와 처리 방법을 기록한다.

### 서버 필터 없는 대체 조회

서버 필터를 사용할 수 없어 조건 없는 목록으로 대체 조회한 경우에는 응답에서 확인 가능한
유형·거래·금액·면적 조건을 클라이언트가 적용한다. 조건을 판정할 값이 없으면 임의로
통과시키지 않는다. 제공되지 않는 필드에 의존하는 조건은 조회 전에 오류로 알리거나,
해당 매물을 제외하고 확인 한계를 `notes` 로 알린다. 소스별 처리 방식은 개발 가이드에 적는다.

서버가 적용한 조건과 클라이언트가 적용해야 하는 조건을 구분해 전달한다. 일부 조건만
서버가 지원하는 경우에도 이미 적용한 조건을 중복 검사하지 않는다. 대체 조회의 검색 범위,
조회 한도와 누락 가능성을 결과에 알리고, 제외한 매물 수만큼 추가 조회하지 않는 공통
조회 한도 규칙을 유지한다.

## 새 엔드포인트 추가 순서

1. 실제 응답을 확인하고, 엔드포인트 설명과 필드 의미는 별도 문서 대신 `api/client.py` docstring 과
   `api/response/` 모델에 적는다.
2. 그 엔드포인트를 부를 기능의 `api/request/<기능>.py` / `api/response/<기능>.py` 에 모델([기준 7](#service-모듈을-나누는-기준)),
   `api/client.py` 에 ClassVar + sync/async 메서드.
3. 필요하면 [나누는 기준](#service-모듈을-나누는-기준)에 맞는 service 모듈에서 조합한다. 자주 쓰는 공개 진입점이면
   provider `__init__.py` 에 re-export 한다 (`service/__init__.py` 에는 하지 않는다).
4. CLI 직접 조회로 실제 동작을 확인한다. 테스트는 [추가 기준](development.md#검증과-테스트)에 맞을 때만
   픽스처 + `httpx.MockTransport` 로 추가한다. 픽스처는 그 테스트가 읽을 때만
   `tests/fixtures/<source>/<action_id>.json` 으로 만든다. 실제 응답 구조를 본뜨되 값은 모두 가상으로 바꾸고
   (매물·단지 번호, 주소, 가격, 제목·본문, 사진 URL, 중개사 정보), 모델이 읽지 않는 필드는 뺀다.
   실제 응답은 커밋하지 않는다.
