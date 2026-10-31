# Code Style

`src/jibsa/**`, `tests/**`, 마크다운 문서에 적용하는 형식 규칙. provider 모듈 고유의 설계 규칙
(action id 명명, 모델 배치, 재시도)은 [provider-conventions.md](provider-conventions.md), 검증·테스트 원칙은
[개발 환경](README.md#검증과-테스트) 에 있다.

§2 따옴표, §3 import 순서·절대 import, §5 타입 힌트는 ruff·mypy 가 검사한다 ([코드 검사](README.md#코드-검사)).
§4 의 별칭·기본값 위치는 `tests/test_schema.py` 가 검사한다 (ruff·mypy 는 잡지 못한다).
§3 의 "둘 이상이면 괄호로 여러 줄" 과 나머지 절은 도구가 잡지 못하니 직접 지킨다.

## 1. 언어

- 주석, docstring 본문, 에러 `message`/`hint`, CLI 도움말은 **한국어**로 쓴다.
- docstring 섹션 이름(`Args`, `Returns`, `Raises`, `Attributes`, `Example`)은 Google 스타일 영어 그대로.
- `core/http.py` 처럼 영어로 쓰인 docstring 은 그대로 두어도 된다. 한 docstring 안에서 섞는 것도 허용한다
  (재시도 문단은 영어, 소스 특이사항은 한국어 — client 메서드 참고).
- 문구에서 변수 뒤에 조사를 붙일 때, 지역·역·단지 이름처럼 끝 글자가 바뀌는 한글 이름은 `jibsa.core.korean` 의
  `particle`·`quoted` 로 고른다 (`'가락동' 과`, `'강남구' 와`). 숫자·ID·옵션 값·영어 필드 이름은 읽는 법에 따라 받침이
  달라 조사가 필요 없게 문장을 바꾼다 (`허용되지 않는 값입니다: '{value}'`). 끝 글자가 늘 정해진 값(`○가` 동,
  `--rent-min/--rent-max`)은 조사를 그대로 쓴다.
- 주석은 **왜** 그렇게 하는지를 적는다. 비공식 API 의 이상한 동작을 피하는 코드는 그 동작을 주석으로 남긴다
  (예: `# 없으면 일부 매물(오피스텔 등) 상세가 "x-zigbang-platform 를 확인해 주세요" 404 를 준다.`).

## 2. 문자열

- 문자열 리터럴은 `'` 를 쓴다. 안에 `'` 가 들어가면 `"` 를 쓴다.
- docstring 은 `"""`.

```python
source_name: ClassVar[str] = 'zigbang'
message=f"'{query}' 에 해당하는 지역을 찾지 못했습니다"
```

## 3. Import

- 그룹 순서, 그룹 사이 빈 줄 하나:
  1. 표준 라이브러리 (`collections.abc` 포함, `typing` 제외)
  2. 외부 라이브러리 (`httpx`, `pydantic`, `tenacity`, `typer`)
  3. 프로젝트 (`jibsa.*`)
  4. `typing`
- `from x import ...` 로 둘 이상 가져오면 괄호로 여러 줄, 한 줄에 하나, 마지막에 쉼표.
- 프로젝트 import 는 ruff(isort)가 모듈 이름순으로 정렬한다. `jibsa.core.*` → `jibsa.providers.<source>.api.*`
  (`client` → `request.*` → `response.*`) → `jibsa.providers.<source>.service.*` 는 이름순이면서 의존 깊이 순이다.
- 절대 import (`from jibsa...`) 를 쓴다. 패키지 `__init__.py` 의 re-export 만 상대 import (`from .client import ...`).
- 순환 import 를 피하려고 함수 안에서 import 할 때는 이유를 주석으로 남긴다 (`RateLimiter._retry_after` 참고).

```python
from collections.abc import Callable
from functools import cached_property

from httpx import (
    AsyncClient,
    Client,
)
from pydantic import Field

from jibsa.core.http import (
    BaseHTTPClient,
    create_base_url,
)
from jibsa.providers.zigbang.api.request.region import ZigbangSearchV2RequestParameterModel

from typing import (
    Annotated,
    ClassVar,
)
```

## 4. Pydantic 선언

필드 하나는 `Annotated` 안의 `Field()` 와 대입 위치의 기본값, 두 곳에 나눠 쓴다. pydantic 은 두 곳을
모두 읽지만 정적 타입 검사기(mypy, Pylance)는 대입 위치만 읽고 그걸로 생성자(`__init__`) 시그니처를 만든다.
그래서 무엇을 어디에 둘지는 "검사기가 이 값을 알아야 하는가" 로 정한다. pydantic 공식 문서는 두 형식을
모두 지원하고, 별칭은 "타입 검사기가 별칭 대신 필드 이름을 쓰게 하려면 annotated pattern 을 쓰라" 고 안내한다
([Fields](https://pydantic.dev/docs/validation/latest/concepts/fields/)). 아래는 이 프로젝트가 고른 규칙이다.

| 넣을 것 | 위치 | 이유 |
| --- | --- | --- |
| 제약 (`ge`, `gt`, `le`, `min_length`, `max_length`, `pattern`), `description`, `exclude`, `repr` | `Annotated` 안 `Field()` | 검사기가 알 필요가 없다. 대입 위치에 두면 필수 필드(`x: int = Field(gt=0)`)도 읽는 사람에게 기본값이 있는 것처럼 보인다 |
| `alias` | `Annotated` 안 `Field()` | Pylance(pyright)가 읽으면 생성자 인자 이름이 별칭(camelCase)으로 바뀐다. 모델은 `validate_by_name=True` 라 코드에서 필드 이름(snake_case)으로 만든다 |
| 기본값 | 대입 위치 `= value` | 검사기가 읽어야 선택 인자로 안다 |
| `default_factory` | 대입 위치 `= Field(default_factory=...)` | 위와 같다. 모델 인스턴스처럼 호출해서 만들어야 하는 기본값에만 쓴다. 대입 위치에 `Field()` 가 남는 유일한 경우 |

- 별칭을 쓰는 모델은 `validate_by_name=True` 인 `RequestModel`·`ResponseModel` 을 상속한다. 이 설정 없이
  `alias` 를 `Annotated` 안에 두면 검사기는 필드 이름을 받는다고 보는데 런타임은 별칭만 받아 서로 어긋난다.
- `alias` 위치는 Pylance 에만 영향을 준다. mypy 의 `pydantic.mypy` 플러그인은 `validate_by_name=True` 를 보고
  위치와 상관없이 필드 이름으로 생성자를 만든다. mypy·ruff 가 잡지 못해 `tests/test_schema.py` 가 대입 위치의 `Field()` 에
  `default_factory` 말고 다른 인자가 있는지와 별칭이 있는 모델이 필드 이름을 받는지를 검사한다.
- 별칭은 `alias_generator` 로 자동 생성하지 않고 필드마다 적는다. 원본 응답의 키(`walkingDistance`)로 코드를 검색할 수
  있어야 하고, 자동 변환으로 나오지 않는 키(`roomCnt`, 한글 키, `__typename` 등 136개)가 많은데 응답 모델은
  `extra='allow'` 라 별칭을 빠뜨리면 에러 없이 `None` 이 된다. 직방 상가 요청 본문(`item_ids`, `sales_type`)처럼
  snake_case 로 보내야 하는 필드는 자동 변환이 보내는 이름까지 바꾼다.
- `Field(...)`(ellipsis)로 필수를 강조하지 않는다. 기본값이 없으면 필수다.
- `X | None` 은 선택 필드가 아니다. **기본값이 있어야** 선택이다.
- 목록·집합·딕셔너리 기본값도 값으로 쓴다 (`= []`, `= set()`, `= {}`). pydantic 이 인스턴스마다 복사하므로 공유되지 않는다.
- 필드 선언은 여러 줄로 쓰고, 모델 필드에는 `description` 을 단다 (CLI 출력 의미가 드러나도록).

```python
# 제약 + 기본값
timeout: Annotated[
    int,
    Field(gt=0)
] = 20

# 제약 + 별칭 + 기본값
deposit_max: Annotated[
    int | None,
    Field(ge=0, description='보증금 상한 (만원)', alias='depositMax')
] = None

# 필수 + 별칭: 대입이 없다
bounding_box: Annotated[
    NaverBoundingBoxModel,
    Field(description='지도 뷰포트', alias='boundingBox')
]

# 목록 기본값
type_list: Annotated[
    list[NaverTransportSubwayLineModel],
    Field(description='노선', alias='typeList')
] = []

# 팩토리 기본값
redevelopment_area_paging_request: Annotated[
    NaverRedevelopmentAreaPagingRequestModel,
    Field(description='페이지 요청 (정렬 포함)', alias='redevelopmentAreaPagingRequest')
] = Field(default_factory=NaverRedevelopmentAreaPagingRequestModel)

# 비밀 값
token: Annotated[
    str | None,
    Field(repr=False)
] = None
```

- 모델 설정은 `model_config = ConfigDict(extra='forbid')` 를 기본으로 한다. 응답 모델만 `ResponseModel` 을
  상속해 `extra='allow'`.
- 고정 선택지는 `Literal` 별칭으로 모듈 위에 정의한다 (`Source`, `TradeType`, `ZigbangSalesType`).

## 5. 타입 힌트

- 모든 함수 인자와 반환 타입에 힌트를 단다.
- 내장 제네릭(`list[...]`, `dict[...]`, `tuple[...]`)과 `X | None` 을 쓴다. `typing.List`, `Optional` 은 쓰지 않는다.
- 런타임은 Python 3.11 이상이라 `from __future__ import annotations` 는 넣지 않는다.
- `typing` 에서는 내장·`collections.abc` 대체가 없는 이름만 가져온다 (`Annotated`, `Any`, `ClassVar`,
  `Literal`, `TypeVar`, `Generic`).
- `Callable`, `Iterator`, `Awaitable`, `Generator` 등은 `collections.abc` 에서 가져온다.
- 공개 상수는 타입을 단다: `PROPERTY_TYPES: tuple[ZigbangPropertyType, ...] = (...)`.

## 6. Docstring

Google 스타일. 공개 모델·클래스에는 다음 순서로 (해당 없는 섹션은 뺀다):

- **요약** — 한 줄, 필요하면 짧은 문단.
- **Args** — 생성자/모델 필드. 기본값이 있으면 `Defaults to ...`.
- **Attributes** — 캐시·파생 속성 (`base_url`, `rate_limiter`).
- **Raises** — 호출자가 처리해야 할 예외와 조건.
- **Example** — `>>>` 사용 예.

### 메서드·함수

- 요약 한 줄 (client 메서드는 HTTP 메서드 + 경로: ``via `GET /v2/search` ``).
- 재시도 동작 (`zigbang_retry` 같은 재시도 데코레이터가 붙은 경우).
- **Args** — 각 인자와 핵심 필드.
- **Returns** — 반환 타입과 담긴 내용.
- **Raises** — 직접 던지는 애플리케이션 에러만. 전송 에러를 모두 나열하지 않는다.

같은 동작을 반복하는 메서드는 다른 메서드를 가리켜 줄이고(`Same retry behaviour as ...`),
async 변형은 `Async variant of ...` 한 줄로 쓴다. 비공개 헬퍼는 필요할 때만 한 줄 docstring.

## 7. 상수와 이름

- 매직 넘버는 모듈 상단의 대문자 상수로 뺀다 (`ITEMS_LIST_BATCH_SIZE = 15`, `GEOHASH_PRECISION = 5`).
- 코드값 → 한국어 라벨 매핑은 `<WHAT>_BY_<KEY>` / `<WHAT>_LABELS` dict 상수로 둔다
  (`ROOM_TYPE_BY_CODE`, `DIRECTION_LABELS`).
- 비공개 헬퍼는 `_` 로 시작한다.

## 8. 테스트 코드

언제 테스트를 추가하고 무엇을 돌리는지는 [검증과 테스트](README.md#검증과-테스트)에 있다. 여기는 테스트 코드의 형식만 다룬다.

- 파일은 `tests/test_<source>.py`, `test_<module>.py`. 섹션은 `# --- request models ---` 같은 구분 주석으로 나눈다. 테스트를 지워 비게 된 구분 주석은 함께 지운다.
- 테스트 함수 이름은 동작을 영어 문장으로: `test_closed_items_are_excluded`.
- HTTP 는 `httpx.MockTransport` 로 가짜 응답. 이미 만든 client 에 끼울 때는
  `client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=...)`.
- 서비스 조합은 `monkeypatch.setattr('jibsa.cli.naver.get_complex', fake)` 처럼 바꿔 끼운다.
