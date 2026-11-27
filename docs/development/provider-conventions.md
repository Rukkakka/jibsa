# Provider Conventions

`providers/<source>/` 모듈을 쓰는 규칙. 형식 규칙은 [code-style.md](code-style.md),
계층 구조와 요청 제한은 [architecture.md](architecture.md) 를 본다.

## 모듈 구성

```
providers/<source>/
├── __init__.py       # 자주 쓰는 공개 진입점만 re-export, 함수는 `with_notes` 로 감싼다 (CLI 는 service 모듈에서 바로 가져와 전부 내보낼 필요는 없다)
├── api/              # 아래층: 소스 API 를 그대로 옮긴 것. service 를 가져다 쓰지 않는다
│   ├── __init__.py   # 안내 docstring 만
│   ├── client.py     # <Source>Client(BaseHTTPClient) + run_request_* / arun_request_*
│   └── models/       # 사이트 API 를 그대로 옮긴 pydantic 모델 (안내 docstring 만 있는 `__init__.py`)
│       ├── request/  # 요청 파라미터·본문 모델 (service 와 같은 기능 이름, 기준 7)
│       └── response/ # 응답 모델 (최상위 + 중첩 모델 모두, service 와 같은 기능 이름, 기준 7)
└── service/          # 윗층: api 를 조합해 Listing 으로 정규화
    ├── __init__.py   # 모듈 안내 docstring 만 (re-export 없음)
    ├── common/       # 여러 기능이 쓰는 것. 안의 파일은 모두 내용 이름 (기준 2)
    │   ├── __init__.py   # 모듈 안내 docstring 만 (re-export 없음)
    │   ├── constants.py  # 여러 기능이 쓰는 상수·코드표·이름표
    │   ├── models.py     # 여러 기능이 쓰는 결과·조건 모델과 그 모델이 쓰는 타입 별칭·작은 함수
    │   └── <내용>.py     # 내용 이름의 공용 함수 (response·listing·paging·price·text …. `common.py`·`functions.py` 같은 모음 파일은 두지 않는다)
    ├── region/       # 지역 이름·좌표 해석 (직방은 `region.py` 하나)
    └── <기능>/        # CLI 명령 묶음 하나 (real_price, store, complex …)
        ├── __init__.py   # 모듈 안내 docstring 만 (re-export 없음)
        ├── constants.py  # 그 기능만 쓰는 상수·코드표·이름표 (상수가 없으면 두지 않는다)
        ├── models.py     # 그 기능의 결과·조건 모델과, 모델이 정의·메서드에서 쓰는 타입 별칭·작은 함수
        ├── common.py     # 그 기능 폴더 안의 여러 파일이 같이 쓰는 함수 (필요할 때만)
        └── <명령·주제>.py  # 조회·변환 함수. 명령 하나인 폴더는 명령 이름 (`trend/trend.py`), 둘 이상이면 하는 일 이름 (`search.py`·`detail.py`, 기준 2)
```

- jibsa 에는 `dto.py` 가 없다. 중첩·공통 응답 모델(`ZigbangItemPinModel`,
  `NaverResponseModel[T]` 등)도 `api/models/response/` 에 둔다 (여러 기능이 쓰면 `response/common.py`). 공통 베이스는 최상위
  모델보다 위에 둔다.
- 소스마다 `api/models/response/common.py` 에 기반 응답 모델 `<Source>BaseResponseModel(ResponseModel)` 을 두고 그 소스의 모든
  응답 모델이 물려받는다 (응답 봉투 `NaverResponseModel[T]`·`DabangV5ResponseModel[T]`·`DaangnGraphQLResponseModel` 도 이
  기반 모델 위에 있다). 새 응답 모델도 `ResponseModel` 이 아니라 이 기반 모델을 물려받는다. 기반 모델의 wrap 검증기
  (`core/schema.py` 의 `validate_dropping_nulls`)가 목록 칸의 null 을 키가 없는 것으로 읽는 규칙(`drop_null_lists`)과 객체 목록 안의
  null 원소를 빼고 칸마다 세는 규칙(`drop_null_items`)을 부른다. 키가 없을 때와 같아서 기본값이 `[]` 인
  칸은 빈 목록이 되고, 키가 왔는지(`model_fields_set`, 직방 `sent_or_none`)로 모름을 가르는 칸은 모름이 된다. `| None` 칸은
  기본값이 목록이어도 건드리지 않아 null 이 그대로 모름(`None`)이다 (다방 단지 학교·어린이집, 네이버 재개발 역·지구). 이 규칙을 쓸지는
  소스마다 정한다 (소스 API 는 따로 바뀌어, 한 소스가 null 에 다른 뜻을 실으면 그 소스의 기반 모델만 고친다).
- 객체 목록 안의 null 원소(`[{…}, null]`)는 빼고 읽어 조회가 `PARSE_ERROR` 로 끝나지 않게 하고, 그 칸에서 뺀 수는 `null_items('칸 이름')` 으로
  읽는다 (이름을 주지 않으면 모든 칸의 합). 원소가 객체가 아닌 목록(`list[int]` 등)의 null 은 건드리지 않는다. **그 목록으로 합계·평균·개수·순위·
  대표 고르기를 하거나 쪽 넘김·`--limit` 자리를 세는 코드는 `null_items` 를 본다**: 계산한 값은 `null`(모름)로 두어 빼고 센 적은 값이 완전한
  값처럼 나가지 않게 하고, 자리를 세는 값은 `len(목록)` 에 뺀 수를 더해 (빈 항목도 서버가 센 한 자리다) 같은 항목을 다시 받거나 덜 받지
  않게 하며, 뺀 것은 `null_items_note`(`core/listing.py`)로 `[제외]` 안내를 붙인다. 이 안내의 끝말이 `UPDATE_MAYBE_NEEDED` 라 매일 API
  감시가 그런 응답을 고장으로 알린다. 목록을 그대로 보여 주기만 하면 뺀 것만으로 값이 틀리지 않아 `null_items` 를 보지 않아도 되고 자리별 안내도 만들지 않아도 된다: 명령 하나 동안 뺀 수는 `core.schema` 가 합으로 모으고(`reset_null_item_tally`·`add_null_item_tally`·`null_item_tally`, 기반 모델의 검증기와 루트 목록 모델 `DabangRootListModel` 이 더한다. 집계는 `handle_errors` 가 명령 시작에, 정문 함수는 `with_notes` 가 부를 때마다 0 으로 돌린다), `emit`(정문 함수는 `with_notes` 가 결과 `notes` 에)이 그 합이 0 보다 큰데 결과 `notes` 에 빈 항목 안내가 없으면 어느 목록인지 말하지 않는 공통 안내(`null_items_total_note`) 한 줄을 붙인다. 소스가 `null_items_note` 로 자리별 안내를 이미 붙였으면 공통 안내는 붙지 않는다.
- service 결과 모델(`ZigbangSearchResult`, `NaverComplexSummary`, `<Source>ListingDetail` 등)은
  CLI 출력용이므로 그 기능의 service 모듈에 두고 `extra='forbid'` 로 만든다. 명령이 돌려주는 결과 모델은 `BaseModel` 이 아니라
  `core.listing.Result` 를 물려받는다 ([Service 함수](#service-함수)). `Result` 에는 `extra='forbid'` 가 없어 모델마다 `model_config` 에 둔다.
- HTML 파싱처럼 소스 고유의 응답 처리 단계가 있으면 `api/` 안의 별도 모듈로 뺀다 (당근의 `api/relay.py`, `api/parser.py`).
- import 는 `service` → `api` 한 방향이다. `api/` 는 소스 API 를 그대로 옮긴 아래층이라 service·CLI 를 모른다.

### service 모듈을 나누는 기준

1. **기능 하나는 CLI 명령 묶음 하나를 맡는다.** 명령 이름만 알면 고칠 파일을 찾게 기능마다 그 이름의 폴더를 두고, 폴더 안 파일은 기준 2 의 이름으로 짓는다.
   `__init__.py` 에는 안내 docstring 만 둔다. 파일 하나로 충분한 모듈(직방 `region.py`·`listing.py`)은 폴더 없이 둔다. 소스별 명령 ↔ 모듈 대응은 각 소스 개발 가이드의 '명령과 요청 흐름' 표에 있다
   ([직방](providers/zigbang.md#명령과-요청-흐름)·[네이버](providers/naver.md#명령과-요청-흐름)·[당근](providers/daangn.md#명령과-요청-흐름)·[다방](providers/dabang.md#명령과-요청-흐름)).
2. **파일 이름은 내용과 자리로 정한다.**

   | 이름 | 뜻 |
   | --- | --- |
   | `service/common/` 폴더 | 소스 전체(여러 기능)가 같이 쓰는 것. 안의 파일은 모두 내용 이름이다 (`response.py`·`listing.py`·`paging.py`·`price.py` …). `common.py`·`functions.py`·`base.py` 같은 모음 파일은 두지 않고, 작은 도우미도 쓰는 곳에 맞는 내용 파일에 넣는다 |
   | `<기능>/common.py` | 그 기능 폴더 안의 여러 파일이 같이 쓰는 함수 |
   | `constants.py` | 상수·코드표·이름표(선택지 `Literal` 별칭 포함). 한 기능 폴더 안에서만 쓰면 그 폴더의 `constants.py`, 여러 기능이 쓰면 `service/common/constants.py` 한 곳이다 (같은 값을 두 폴더에 복사하지 않는다). 모델 정의에 쓰는 상수도 여기에 두고 `models.py` 가 가져다 쓴다. 폴더가 아니라 파일 하나뿐인 기능은 그 파일 안에 두고, 상수가 없는 폴더에는 만들지 않는다 |
   | `models.py` | 데이터 모양 (결과·조건 모델, 타입 별칭). 기능 폴더마다 하나이고 나누지 않는다 |
   | 명령·주제 파일 | 하는 일 이름 (`search.py`·`detail.py`·`facility.py`). 명령 하나인 폴더는 명령 이름이다 (`trend/trend.py`, `complex/complex.py`) |

   service 와 `api/models/` 모두 `functions.py`·`base.py` 라는 이름이 없고, 폴더 안 공용은 `common.py` 다. `api/models/request/`·`response/` 바로 아래 `common.py` 는 소스 전체가 같이 쓰는 요청·응답 모델이고, 그 아래 기능 폴더의 `common.py` 는 그 기능 안에서 같이 쓰는 요청·응답 모델이다 (기준 7). 직방은 `common/` 을 `constants`·`models`·`ids`·`text`·`unavailable`(바닥)과 `danji`·`price`·`room`·`apt`(주제)로 나누고, 당근은 `constants`·`models`·`response`·`location`·`listing`·`nearby`·`complex`, `region/` 은 `constants`·`models`·`common`·`area`·`station`·`university`·`address` 로 나눈다.
   다른 파일이 부르게 된 이름은 밑줄을 떼 공개한다. 값 안에 함수를 담은 표나 service 의 함수·모델로 만드는 값(다방 `METRIC_BY_LABEL`, 직방 `USAGE_FEES`)은 `constants.py` 로 옮기지 않고 쓰는 파일에 두며 바로 위에 이유 주석을 단다. 리터럴과 그 조합, 표준 라이브러리·`core`·`httpx`·api 모델 타입으로 만든 값(`re.compile(...)`, 예외 클래스 튜플)은 `constants.py` 로 간다.
3. **import 는 `constants` → `models` → `<기능>/common.py` → 명령·주제 파일 방향으로만 한다.** `service/common/` 은 두 층이다: 바닥 파일(`constants`·`models`·`response`·`text` 처럼 상수·모양·응답 꺼내기·이름표·글자 다듬기. 매물·단지 주소 틀은 `constants` 에 둔다)과 주제 파일(매물·쪽 넘김·시세·평형 등). 주제 파일은 바닥 파일만 가져다 쓰고 주제 파일끼리는 가져다 쓰지 않는다. 두 주제가 같이 쓰는 함수는 바닥 파일로 내린다. 바닥 파일은 모두 `constants` 를 가져다 쓸 수 있고, `constants` 를 뺀 바닥 파일끼리는 가져다 쓰지 않는다. 기능 폴더 안도 같다: 그 폴더의 `common.py` 가 바닥이고 명령·주제 파일끼리는 서로 가져다 쓰지 않는다 (입구 파일이 주제 파일을 부르는 것은 된다: 네이버 `listing/detail.py` → `facility`·`cost`·`nearby`). `models.py` 는 같은 기능의 함수 모듈을 가져다 쓰지 않는다. 기능 모듈은 다른 기능 모듈을 가져다 쓰지 않고, 두 기능이 같이 쓰게 되면 그 심볼을 `service/common/` 의 내용 파일(상수는 `common/constants.py`)로 옮긴다. 입구 모듈(직방 `listing`: `listing` 명령의 ID 분기)만 기능 모듈을 가져다 쓴다. 지역 해석(`region`)은 `service/common/` 바로 위층이라 기능 모듈이 가져다 쓸 수 있고, `region` 은 기능 모듈을 가져다 쓰지 않는다 (소스마다 `service/__init__.py` docstring 에 그 소스의 방향이 있다).
4. **한 파일에는 한 주제만 둔다. 주제가 섞이면 나눈다.** 섞임은 셋으로 본다: (1) 파일 안 함수를 쓰는 기능(명령)이 갈린다, (2) 서로 부르지 않는 덩어리가 한 파일에 있다, (3) 덩어리마다 부르는 API·웹 화면 칸이 다르다. 길이는 살펴볼 신호일 뿐 나누는 기준이 아니다. 명령 하나를 맡는 파일도 주제로 나눈다 (네이버 매물 상세는 입구 `listing/detail.py` 와 웹 구역별 `facility`·`cost`·`nearby`). 경계 사례는 기준대로 나눈다: 덩어리가 대략 100줄을 넘고 진입 명령이나 주제가 다르면 나눈다 (당근 `complex` 에서 비교·주변 단지를 `compare` 로 뺐다).
5. **새 명령은 맞는 모듈에 넣는다.** 맞는 모듈이 없으면 새 모듈을 만들고(기능이 폴더면 그 안의 명령·주제 파일) 소스 문서의
   표에 한 줄 추가한다.
6. CLI 와 테스트는 이름이 정의된 모듈에서 바로 가져온다 (`from jibsa.providers.zigbang.service.stay.search import ...`,
   상수는 `from jibsa.providers.zigbang.service.stay.constants import ...`,
   모델은 `from jibsa.providers.daangn.service.complex.models import ...`).
   테스트가 상수를 바꿔 끼울 때(`monkeypatch.setattr`)도 그 상수를 읽는 코드가 있는 모듈을 고친다 (함수가 `constants` 나 `models` 에서 가져다 쓰는 상수는 함수 모듈의 이름을 바꿔 끼운다).
7. **요청·응답 모델(`api/models/request/`·`api/models/response/`)은 service 와 같은 기능 이름으로 나눈다.** 엔드포인트의 요청·응답 모델은
   그 엔드포인트를 부르는 service 기능과 같은 이름의 모듈에 둔다 (명령 하나를 맡는 `service/review/` 가 부르면 `request/review.py`·`response/review.py`,
   명령 둘 이상을 맡아 폴더로 나뉜 `service/stay/search.py` 면 `request/stay/search.py`·`response/stay/search.py`, 당근 `service/complex/search.py` 면
   `request/complex/search.py`·`response/complex/search.py`, `service/search/map.py` 면 `request/search/map.py`, `service/region/area.py` 면 `request/region/area.py`). 그래서 기능 하나를 고칠 때 같은 이름의 세 곳만 보면 된다.
   service 의 `models.py` 는 결과·조건 모델이고 `request/`·`response/` 는 사이트 API 를 그대로 옮긴 모델이라 따로 둔다.
   - 명령 둘 이상이 같이 쓰는 모델(검색·상세가 같이 쓰는 요청·요약 모델 등)은 그 폴더의 `common.py` 에 둔다 (service 의 폴더 안 공용과 같은 이름). 명령 모듈끼리는 서로 가져다 쓰지 않는다. 같은 소스의 다른 기능·client 만 쓰는 모델(라이브러리용 엔드포인트 등)도 그 폴더의 `common` 이다.
   - 여러 기능이
     부르는 엔드포인트의 모델, 여러 기능의 모델이 같이 쓰는 중첩 모델, 기반 모델은 `common` 에 둔다.
     그래서 기능 모듈은 같은 패키지(`request/`·`response/`) 바로 아래 `common` 과 자기 폴더의 `common` 만 가져다 쓴다. 내용 이름 파일로
     나누는 `common/` 폴더는 service 에만 있고 `request/`·`response/` 의 소스 전체 공용은 `common.py` 하나다.
   - service 가 부르지 않는 엔드포인트(라이브러리용)는 그 기능 폴더의 `common`(명령 하나를 맡는 기능은 같은 이름의 모듈)에 둔다.
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
| 당근 | `/map/{name1}/{name2}/reviews` (페이지) | — | `map_reviews` |
| 당근 | `POST /graphql` 의 `articleFeed` (GraphQL) | — | `article_feed` |
| 다방 | `/api/v5/loc/search` · `/api/3/new-room/detail` (버전이 `3` 이면 `v3`) | `/api` | `loc_search_v5` · `new_room_detail_v3` |

GraphQL 은 오퍼레이션의 루트 필드 이름을 snake_case 로 쓴다. 루트 필드가 같은 오퍼레이션이 여럿이거나
페이지 action id 와 겹치면 뜻이 드러나는 이름으로 구분한다. 당근의 전체 목록과 구분한 사례는
[당근 개발 가이드](providers/daangn.md#action-id-목록)에 있다.

`{Action}` 은 PascalCase (`items_onerooms_v1` → `ItemsOneroomsV1`), 접두어는 소스 이름(`Zigbang`,
`Naver`, `Daangn`, `Dabang`).

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
  - `default_rate_limit: ClassVar[RateLimitPolicy]` — 소스 기본 요청 제한 정책
  - `host: str` 필드와 `base_url` property (`create_base_url` 사용)
  - `base_header` property — 사이트 웹 코드가 모든 요청에 붙이는 헤더만 (실측 날짜와 함께). API 묶음마다 다른 헤더는
    요청마다 `headers=` 로 붙이고, 웹이 붙이지 않는 헤더는 넣지 않는다. UA·Origin·Referer 는 브라우저가 붙인다
    ([브라우저 요청](architecture.md#브라우저-요청)의 헤더)
  - 브라우저 설정 ([브라우저 요청](architecture.md#브라우저-요청)):
    - `browser_entry_url` — 처음 열 사이트 화면. jibsa 는 load 뒤(`browser_ready_cookie` 가 있으면 그 쿠키를 다 받은 뒤)
      바로 빈 페이지로 떠나므로, 그때까지 사이트 자체 API 를 덜 부르는 화면을 고른다. 페이지에 오래 머물 때의 수와 다르다
      (당근 실측은 [당근 브라우저 요청](providers/daangn.md#브라우저-요청))
    - `browser_ready_cookie` — 사이트 API 가 요구하거나 브라우저 식별인 쿠키. 없으면 None
    - `browser_api_hosts` — 첫 화면이 부른 요청을 셀 사이트 API 호스트 (기본은 `browser_entry_url` 의 호스트). 요청은 모두
      첫 화면 탭에서 보내므로 사이트 API 가 첫 화면 출처의 CORS 를 허용해야 한다
    - 이것은 호스트 필드(`host`·`graphql_host` 등)에서 만드는 property 로 쓴다. 호스트를 상수로 따로 적으면 호스트 필드를
      바꿨을 때 어긋나, 첫 화면이 그 호스트로 보낸 요청과 CORS 사전 요청을 요청 제한에 세지 못하고 첫 화면에서 받은 그
      호스트의 429 도 놓친다 (`core/browser.py` 의 `count_request`·`count_preflight`·`on_entry_rate_limited`). 나머지는 ClassVar 다
    - `browser_discard_statuses` — 소스가 403 을 거부가 아닌 뜻으로 쓰면 바꾼다 (다방은 없는 주소)
- `_client` / `_async_client` 는 `@cached_property` 로 만들고 반드시
  `event_hooks=self.rate_limit_hooks()` (async 는 `async_rate_limit_hooks()`), `timeout`,
  `transport=self.browser_transport()` (async 는 `async_browser_transport()`) 를 넘긴다. `proxy` 는 넘기지 않는다
  (httpx 의 프록시 mount 가 transport 를 건너뛴다. 프록시는 브라우저가 쓴다).
- 새 소스는 첫 화면을 실제로 열어 쿠키(이름·수명), 첫 화면이 부르는 사이트 API 수, 요청할 호스트들의 CORS
  (`curl -X OPTIONS -H 'Origin: …'`)를 확인하고 그 결과를 소스 개발 가이드에 적는다.
- 토큰 같은 비밀 값 필드는 `Field(repr=False)`.

## 요청 메서드

엔드포인트마다 sync·async 쌍을 만든다. 본문은 같은 모양을 따른다.
CLI 와 service 는 sync 만 쓰고 async 변형(`arun_request_*`, `_async_client`, `async_rate_limit_hooks`)은 jibsa 를 라이브러리로
쓸 때의 공개 API 다. 저장소 안 호출부가 없어도 죽은 코드가 아니니 지우지 않는다. 엔드포인트를 고치면 async 쪽도 함께 고치고,
의심되면 그 메서드를 한 번 실제로 불러 확인한다 (2026-10-11 직방·당근·네이버 실제 호출로 동작 확인).
재시도 데코레이터는 client 모듈에 소스별로 한 번만 정의하고(`zigbang_retry`, `daangn_retry`,
`naver_retry`, `dabang_retry`) 메서드에는 그 이름만 붙인다. 다방은 500 을 다시 보내지 않는 학교 상세 전용
`dabang_education_retry` 가 하나 더 있다. 정책을 바꿀 때 한 곳만 고치면 된다.

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

- **재시도.** 조회 전용이면 POST 라도 `should_retry_idempotent` (5xx/429 + 다시 보내면 나을 수 있는 전송 오류 `RETRYABLE_TRANSPORT_ERRORS`).
  jibsa 에는 조회만 있다 (사용자 대신 상태를 바꾸는 호출은 넣지 않는다, AGENTS.md "로그인 없는 기능만").
  네이버는 예외다 ([네이버 개발 가이드](providers/naver.md)).
- **상태 코드에 뜻을 붙일 때.** 재시도 술어나 service 가 특정 상태를 소스 고유 뜻으로 읽으면(다방 학교 상세의 500)
  첫 화면 5xx(`EntryStatusError`)를 먼저 거른다 ([브라우저 요청](architecture.md#브라우저-요청)).
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

- 요청 모델은 `core.schema.RequestModel` (`extra='forbid'`), 응답 모델은 `ResponseModel` (`extra='allow'`) 을 소스의
  기반 응답 모델(`<Source>BaseResponseModel`, [모듈 구성](#모듈-구성))을 거쳐 상속한다. 둘 다 `validate_by_name=True` 라 코드에서는 필드 이름으로 만든다. 비공식 API 가 예고 없이 필드를
  더하므로 응답 모델은 모르는 필드를 버리지 않는다.
- 응답 필드는 **소스가 빠뜨릴 수 있으면 `X | None = None`** 으로 둔다. 실제 응답에서 늘 오는 것을
  확인한 필드만 필수로 한다. 비공식 API 라 엄격한 필수 필드는 파싱 실패로 이어진다.
- 와이어 이름이 다르면 `alias='camelCase'` 를 단다. 선언 위치는 [code-style.md](code-style.md#4-pydantic-선언) 를 따른다.
- 서버가 요구하는 특이한 직렬화는 모델의 `@model_serializer` 로 처리한다
  (예: 직방 `salesTypes[0]=전세&salesTypes[1]=월세`).
- 서버가 거절할 조합은 요청 모델의 `@field_validator` 로 미리 막는다 (예: 원룸 + 매매,
  `items/list` 15개 초과). CLI 에서 `ValidationError` 는 `INVALID_ARGUMENT` (exit 2) 가 된다.
- 응답 값(다음 페이지 커서·매물 유형 코드 등)으로 요청 모델을 만들 때도 검증 오류는 `INVALID_ARGUMENT`
  로 나가 "입력을 고치라" 고 잘못 안내된다. 그 값이 형식에서 벗어날 수 있으면 요청 모델을 만들기 전에 그 자리에서
  막아 알맞은 에러로 바꾼다 (네이버 매물 유형 `KNOWN_REAL_ESTATE_TYPES`). 실측으로 벗어나지 않는 값은
  막지 않고 그 자리에 근거를 적는다. 한 곳에서 가리지 않는 이유는 `core.schema.is_request_validation_error` 에 있다.

## Service 함수

- 첫 인자는 client. 옵션은 키워드 전용(`*,`)으로 받는다.
- 소스 응답을 `Listing` / `ListingDetail` (또는 그 서브클래스 `<Source>ListingDetail`) 로 바꾼다.
  금액은 만원(`won_to_manwon`), 날짜는 `read_date`(못 읽으면 `null` + `[참고]`, `output-contract.md` 의 금액·단위 날짜 규칙), 면적 평은 `m2_to_pyeong`,
  주소는 `join_address`. 본문(매물 설명)은 옮기지 않는다 (`output-contract.md` 의 내보내지 않는 정보).
- 명령이 돌려주는 결과 모델은 `core.listing.Result` 를 물려받고(`ListingDetail` 도 `Result` 다) `notes` 를 따로 정의하지 않는다.
  `notes` 는 출력 JSON 의 칸이 아니라 `emit` 이 결과 맨 위 `notes` 로 붙이는 안내다. 어떤 안내가 들어가는지는 모델 docstring 끝의 `` `notes`: `` 문단에 적는다.
  `emit` 은 결과의 `notes` 를 명령이 넘긴 `notes`(CLI 가 만든 안내) 뒤에 스스로 붙인다. 결과 앞에 모델에 없는 칸(지역·범위·단지 번호)을 붙일 때는 결과를 dict 로 풀지 않고
  `emit(result, …, head={…})` 로 준다. 결과 둘을 한 JSON 으로 합치는 곳(네이버 `school --complexes`)만 두 결과의 `notes` 를 넘긴다.
- **만료 판정은 service 에서 한다.** 목록은 거래 불가 매물을 건너뛰고, 상세는
  `ListingUnavailableError(source, id, status=..., reason=...)` 를 던진다. 404 도
  `ListingUnavailableError` 로 바꾼다.
- 지역을 찾지 못하면 `RegionNotFoundError`, 소스가 그 지역을 다루지 않으면 `JibsaError` (code `REGION_NOT_SUPPORTED`, 당근의 동에 속하지 않는 좌표는 `REGION_NOT_FOUND`).
- 원 사이트 URL(출력 `url` 칸)은 사이트 주소 상수 하나에서 만든다. 사이트 주소는 `api/client.py` 맨 위 상수(`NAVER_WEB_URL` 등, 웹과 API 가 같은 호스트면 `create_base_url(<SOURCE>_HOST)` 로 만들어 클라이언트 `host` 기본값·`browser_entry_url` 과 함께 쓴다)이고, 링크 틀은 `service` 의 `constants.py` 에 `ARTICLE_URL = f'{NAVER_WEB_URL}/articles/{{}}'` 꼴로 두어 `ARTICLE_URL.format(번호)` 로 쓴다 (여러 기능이 쓰면 `common/constants.py`, 한 폴더만 쓰면 그 폴더). 클라이언트 `host` 는 바꿀 수 있는 값이라 링크에 쓰지 않는다. 경로를 계산해야 하는 주소(직방 매물 종류별 경로 `item_url`, 당근 지도 `map_url`)만 함수로 두고 사이트 주소 상수를 쓴다.
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
- 요청 필드로 바꾸는 함수는 `<무엇>_filter_of(conditions)` 로 짓는다 (`room_filter_of`, `price_filter_of`,
  `complex_filter_of`). 같은 조건을 여러 요청이 쓰면 이 함수를 같이 쓴다.
- 입력 검사(범위·라벨·조합)는 CLI 에서 한다 (`split_csv`, `validate_ranges`, `typer.BadParameter`). 에러 문구와 exit
  code 가 출력 계약이라, 검사를 모델로 옮겨 경로를 바꾸지 않는다. 모델은 `handle_errors` 안에서 만든다. 모델이 조합을
  검사하는 소스는 그 소스 개발 가이드에 적는다.
- 여러 기능이 쓰는 모델은 `service/common/models.py`, 한 기능만 쓰면 그 기능의 `models.py` 에(기능 폴더 안에서만 쓰면 그 폴더의 `models.py`) 둔다 ([나누는 기준](#service-모듈을-나누는-기준)).
- 출력 칸의 이름·모양은 네 소스가 같은 용어집을 따른다. 새 칸을 만들 때는 [칸 이름 규칙](output-contract.md#칸-이름-규칙)대로 이름을 짓고 거래별 값은 영어 거래 키(`sale`·`jeonse`·`wolse`·`short_term`·`yeonse`)로 묶고, 한국어 거래 이름에서 키를 만들 때는 `core.listing.TRADE_KEY_BY_NAME` 을 쓴다.
- 소스마다 다른 점(일부 명령만 받는 조건, 사이트가 주는 값의 차이)은 그 소스 개발 가이드에 적는다.
- CLI 옵션 별칭 중 네 소스가 도움말까지 똑같이 쓰는 것(`PrettyOption`, 보증금·월세·매매가 하한·상한)은 `cli/options.py`
  에 둔다. 도움말이 다르면 각 소스 CLI 에 둔다.
- 같은 뜻의 조건도 옵션 이름·값은 소스 필터를 따라 다르다 (세대수 `--household-min` 과 다방 아파트 `--households-min`, 연식
  네이버 `--building-age-max 10`·당근 `--approval 10년이내`·다방 `--built-within 10`, 관리비 포함 월세 당근
  `--with-manage-cost`·다방 `--rent-includes-manage-cost`). 맞추려고 별칭을 늘리지 않는다. 2026-10-31 에이전트 검증
  (sonnet·opus, 이 조건들을 네 소스에 거는 부탁 6회)에서 모두 소스별 `--help` 를 먼저 읽고 이 이름으로 한 번도 틀리지
  않았다. 다른 소스 이름을 옮겨 쓰면 Click 의 비슷한 옵션 제안이나 소스별 `UsageHints` 가 이 명령의 옵션을 알린다.

## 웹 화면과의 대응

jibsa 는 사이트를 대체하는 도구가 아니라, 사이트가 로그인 없이 보여 주는 것을 에이전트가 JSON 으로 그대로 받게 하는 창이다
([README 원칙](../../README.md#원칙-사이트가-보여-주는-대로)). 그래서 모든 provider 는 아래 원칙을 따른다.

> **사이트가 보여 주는 사실과 어긋나지 않게 한다.** 결과의 매물·가격·순서·수는 그 사이트 웹에서도 같은 조건으로 볼 수 있는
> 것이어야 한다. 그래서 웹에 없는 결과를 만드는 일(다른 API 로 대신 찾기, 받은 결과를 다시 거르거나 합치거나 다시 세우기,
> 후보 중 하나를 임의로 고르기)은 하지 않는다. 그 안에서는 웹보다 편하게 만들어도 된다. 한 번에 더 받기, 탭을 한 번에 보기,
> 웹에 없는 조건으로 좁히기, 웹 UI 에 없지만 서버가 받는 조합을 쓰기는 모두 된다. 웹의 화면 구조·페이지 크기·클릭 순서를
> 그대로 따를 필요는 없다. 웹과 다르게 한 곳은 그 소스 개발 가이드의 "웹과 다른 점" 절에 무엇이 어떻게 다른지와 왜 그래도
> 사실이 어긋나지 않는지를 적는다.

판정 기준은 "웹과 같은가" 가 아니라 **"이 결과를 사이트에서도 얻을 수 있는가"** 다. 웹 화면을 그대로 베끼는 것이 목표가
아니고, 사이트에서 손으로 하면 닿는 결과 안에서는 개선해도 된다.

| 상황 | 판정 | 예 |
| --- | --- | --- |
| 웹에 있는데 jibsa 에 없는 기능 | 괜찮다. 넣을지는 따로 고른다 | 당근 추천 '함께 본 단지', 후기 본문, 카카오 장소 검색으로 회사 찾기 |
| jibsa 결과가 사이트에서 얻을 수 없는 것 | 안 된다 | 못 찾은 이름을 다른 소스로 찾기, 받은 매물을 금액으로 다시 거르기, 반경 순 재정렬, 같은 이름 후보 중 하나 고르기 |
| 같은 API 로 더 편하게 | 된다. 다른 점을 소스 개발 가이드에 적는다 | 한 번에 50건 받기, 매매·전세·월세를 한 번에, `--max-minutes` 로 좁히기 |

### 안 되는 것

- 그 화면이 쓰지 않는 API 로 대신 찾기 (다른 소스는 물론, 같은 소스의 다른 화면 API 도 결과가 다르면 안 된다. 당근의 중고거래
  지역 API 가 그랬다).
- 서버가 준 결과를 다시 거르기·합치기·다시 세우기 (여러 동을 커서로 합치기, 통근 시간 순 재정렬, 금액으로 매물 빼기).
- 같은 이름의 후보가 여럿일 때 하나를 임의로 고르기. `REGION_AMBIGUOUS` 로 묻는다.
- 웹에서 고를 수 없는 기본값·계산식 (대표 평형 고르는 규칙, 반올림, 기간 탭의 달 수, 관리비 계산). 웹 화면에서 고를 수 있는
  값을 기본으로 삼는 것은 [되는 것](#되는-것)이다.
- 웹이 보내지 않는 조건으로 결과를 바꾸기 (서버가 무시하는 조건을 보내 조용히 틀린 결과를 내는 것도 포함. 막거나 `notes`).

### 되는 것

결과 내용은 사이트에서도 손으로 하면 닿는 것이어야 하고, 어디가 다른지 소스 개발 가이드에 적는다.

- **한 번에 더 받기.** 페이지 크기를 서버가 받는 만큼 키우기 (실거래 50건), 커서를 이어 받기.
- **탭을 한 번에 보기.** 당근 `compare` 는 웹이 매매·전세·월세 탭을 하나씩 보여 주는 것을 한 번에 준다. 신고가 `--previous-days`
  는 웹이 보여 주지 않는 이전 공개일까지 같은 변수(`includePreviousDays`)로 받는다. `real-price` 는 평형을 안 주면 웹의 평형
  탭을 모두 합친 모든 평형이다 (거래마다 면적이 있다).
- **웹에 없는 조건으로 좁히기.** `--max-minutes`·`--years` 처럼 받은 결과의 부분집합만 남기는 조건. 서버가 받지 않는 조건이면
  판정할 값이 응답에 있어야 하고, 매물을 뺄 때는 `notes` 로 알린다 ([서버 필터와 클라이언트 후처리](#서버-필터와-클라이언트-후처리)).
- **웹 UI 에 없지만 서버가 받는 조합.** 종류 없는 당근 `popular-listings` 전체 순위, 지역 실거래의 전월세(`BORROW`).
- **웹에서 고를 수 있는 값을 기본으로.** 정렬·기간·유형처럼 웹 화면에서 고를 수 있는 값을 웹 기본과 다르게 jibsa 기본값으로
  삼기 (네이버 `trend --period` 기본 1년, 웹 위젯 기본 5년). 웹에서 그 값을 고르면 같은 결과다.
- **출력 보강.** 거리(`distance_km`)·시·도 채우기처럼 매물·가격·순서·수를 바꾸지 않는 덧붙임.

### 확인 방법

기능을 고치거나 새로 짤 때 그 화면이 실제로 하는 요청을 먼저 확인한다. 웹 번들에서 쿼리 이름·변수·기본값·정렬·계산 함수를
찾아 대조하고, 실제 호출로 결과를 확인한다 (요청은 최소로). 당근은 Relay persisted query 해시까지 번들의 것과 맞춘다. 다른
소스는 그 소스의 웹 요청(개발자 도구의 네트워크 탭, 요청 헤더·쿼리)을 본다. 확인한 날짜와 번들 심볼 이름을 괄호에 적는다
(`2026-11-12 번들 대조`, MapShell `Ff`).

### 적는 곳

웹과 다르게 한 곳은 그 소스 개발 가이드의 "웹과 다른 점" 절에 모은다
([당근](providers/daangn.md#웹과-다른-점)·[직방](providers/zigbang.md#웹과-다른-점)·[네이버](providers/naver.md#웹과-다른-점)·[다방](providers/dabang.md#웹과-다른-점)).
항목마다 무엇이 어떻게 다른지와 왜 그래도 사실이 어긋나지 않는지를 한 구절로 적는다. 리뷰에서 지적됐지만 고치지 않기로 한
차이도 오탐을 막기 위해 같은 절에 이유와 함께 적는다.

[서버 필터와 클라이언트 후처리](#서버-필터와-클라이언트-후처리)(받은 결과를 다시 거르지 않는다)와 architecture.md 의
[소스끼리는 서로 모른다](architecture.md#계층)(다른 소스로 대신 찾지 않는다)는 이 원칙의 하위 규칙이다.

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
   `api/models/response/` 모델에 적는다.
2. 그 엔드포인트를 부를 기능의 `api/models/request/<기능>.py` / `api/models/response/<기능>.py` (명령 둘 이상을 맡는 기능은 `<기능>/search.py` 처럼 service 와 같은 경로)에 모델([기준 7](#service-모듈을-나누는-기준)),
   `api/client.py` 에 ClassVar + sync/async 메서드.
3. 필요하면 [나누는 기준](#service-모듈을-나누는-기준)에 맞는 service 모듈에서 조합한다. 자주 쓰는 공개 진입점이면
   provider `__init__.py` 에 re-export 한다 (`service/__init__.py` 에는 하지 않는다). 함수는 `core.listing.with_notes('<source>')` 로 감싸
   내놓는다 (파이썬에서 불러도 결과 `notes` 에 못 읽은 날짜·뺀 빈 항목 안내가 들어간다. service 함수 정의에는 쓰지 않는다: CLI 는 감싸지 않은
   함수를 쓰고 명령 하나가 여러 함수를 부르므로, 감싸면 뒤 호출이 앞의 안내를 지우고 `emit` 이 같은 안내를 또 붙인다).
4. CLI 직접 조회로 실제 동작을 확인한다. 테스트는 [추가 기준](README.md#검증과-테스트)에 맞을 때만
   픽스처 + `httpx.MockTransport` 로 추가한다. 픽스처는 그 테스트가 읽을 때만
   `tests/fixtures/<source>/<action_id>.json` 으로 만든다. 실제 응답 구조를 본뜨되 값은 모두 가상으로 바꾸고
   (매물·단지 번호, 주소, 가격, 제목·본문, 사진 URL, 중개사 정보), 모델이 읽지 않는 필드는 뺀다.
   실제 응답은 커밋하지 않는다.
