import math
import re
from calendar import monthrange
from collections.abc import (
    Callable,
    Container,
    Iterable,
    Iterator,
    Sequence,
)
from contextlib import contextmanager
from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
)
from functools import wraps

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from jibsa.core.korean import particle
from jibsa.core.ratelimit import RateLimitedError
from jibsa.core.schema import (
    drop_unset_fields,
    null_item_tally,
    reset_null_item_tally,
)

from typing import (
    Annotated,
    Any,
    Literal,
    ParamSpec,
    TypeVar,
    get_args,
    overload,
)


P = ParamSpec('P')
R = TypeVar('R')
SQUARE_METERS_PER_PYEONG: float = 3.305785
KST: timezone = timezone(timedelta(hours=9), 'KST')
# 구분자가 없으면 8자리만 받는다. 월·일을 한 자리로도 받으면 연월('202411')이 2024-01-01 로 읽힌다.
# '년 월 일' 은 직방 사용승인일에 섞여 온다 ('1984년 10월 26일', '일' 이 빠진 '2011년 7월 1', 2026-10-15 실측)
DATE_DIGITS_PATTERN: re.Pattern[str] = re.compile(
    r'^(\d{4})(?:(\d{2})(\d{2})|[-./](\d{1,2})[-./](\d{1,2})|년\s*(\d{1,2})월\s*(\d{1,2})일?)\.?$'
)
# 입주 가능일 문구 끝의 괄호 설명 ('2026.10.15 이후 입주 가능 (입주협의)')
MOVE_IN_PAREN_PATTERN: re.Pattern[str] = re.compile(r'^(.*?)\s*\(([^()]*)\)$')
ISO_DATE_PATTERN: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# 연월 칸의 'YYYY-MM'·'YYYY.M'·'YYYYMM'. 구분자 없이는 두 자리 달만 받는다
YEAR_MONTH_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d{4})(?:[-.](\d{1,2})|(\d{2}))')
MOVE_IN_NOW: str = '즉시입주'
# 입주 문구 괄호 안에서 협의 가능으로 읽는 설명 (띄어쓰기를 지우고 견준다). 다른 설명은 그대로 붙인다 (`move_in_label`)
MOVE_IN_NEGOTIABLE: str = '협의가능'
# 네이버 매물의 지하층 표기 ('B1' = 지하 1층)
BASEMENT_FLOOR_PATTERN: re.Pattern[str] = re.compile(r'^B(\d+)$')
RELATIVE_FLOOR_LABELS: dict[str, str] = {'저': '저층', '중': '중층', '고': '고층'}

# 거래 유형별로 원래 존재하지 않는 가격 필드. 출력에서 키째 뺀다. 연세(당근 제주)만 1년치 월세 `yearly_rent_manwon` 이 있고
# 월세 `rent_manwon` 은 없다 (연세를 월세로 나눈 값은 당근 웹에도 없다)
NOT_APPLICABLE_PRICE_FIELDS: dict[str, frozenset[str]] = {
    '매매': frozenset({'deposit_manwon', 'rent_manwon', 'yearly_rent_manwon'}),
    '전세': frozenset({'price_manwon', 'rent_manwon', 'yearly_rent_manwon'}),
    '월세': frozenset({'price_manwon', 'yearly_rent_manwon'}),
    '단기임대': frozenset({'price_manwon', 'yearly_rent_manwon'}),
    '연세': frozenset({'price_manwon', 'rent_manwon'}),
}

# 시·도 줄임말 → 정식 명칭. 직방·네이버는 '서울시'·'강원도'·'제주도' 처럼 줄이거나 옛 이름을 쓰고
# 당근은 정식 명칭을 써서, 합친 결과에서 같은 지역이 달라 보이지 않도록 정식 명칭으로 맞춘다.
SIDO_OFFICIAL_NAMES: dict[str, str] = {
    '서울': '서울특별시',
    '서울시': '서울특별시',
    '부산': '부산광역시',
    '부산시': '부산광역시',
    '대구': '대구광역시',
    '대구시': '대구광역시',
    '인천': '인천광역시',
    '인천시': '인천광역시',
    # 광주광역시·전라남도는 전남광주통합특별시로 합쳐졌다 (2026-10-10 실측: 당근·직방·네이버 모두 이 이름).
    # 주소 첫 단어만 보므로 경기도 광주시('경기도 광주시 …')와 섞이지 않는다.
    '광주': '전남광주통합특별시',
    '광주시': '전남광주통합특별시',
    '광주광역시': '전남광주통합특별시',
    # 네이버 자동완성·시·도 목록과 직방은 '전남광주시 광산구' 처럼 줄인다 (2026-10-11 네이버 실측)
    '전남광주': '전남광주통합특별시',
    '전남광주시': '전남광주통합특별시',
    '대전': '대전광역시',
    '대전시': '대전광역시',
    '울산': '울산광역시',
    '울산시': '울산광역시',
    '세종': '세종특별자치시',
    '세종시': '세종특별자치시',
    '경기': '경기도',
    '강원': '강원특별자치도',
    '강원도': '강원특별자치도',
    '충북': '충청북도',
    '충남': '충청남도',
    '전북': '전북특별자치도',
    # 네이버 시·도 목록의 이름 (legalDivisionName, 2026-10-11)
    '전북도': '전북특별자치도',
    '전라북도': '전북특별자치도',
    '전남': '전남광주통합특별시',
    '전라남도': '전남광주통합특별시',
    '경북': '경상북도',
    '경남': '경상남도',
    '제주': '제주특별자치도',
    '제주도': '제주특별자치도',
}
# 시·도 표에 옛 광주광역시로 있지만 사용자가 지역 이름으로 주면 경기도 광주시인 이름 (옛 광주광역시는 '광주'·'전남광주').
# 주소 첫 단어는 늘 시·도라 주소 정규화는 표를 그대로 쓰고, 사용자가 준 이름을 시·도로 넓힐 때만 이 이름을 뺀다.
# 소스마다 따로 두면 한쪽만 빠뜨린다 (2026-10-28: 다방 동 이름 앞 낱말 '광주시' 가 빠져 '광주시 송정동' 이 두 곳에 맞았다)
CITY_NAMES_NOT_SIDO: frozenset[str] = frozenset({'광주시'})

Source = Literal['naver', 'zigbang', 'daangn', 'dabang']
# 연세는 1년치 월세를 한 번에 내는 제주 거래로, 당근만 준다 (YearTrade)
TradeType = Literal['매매', '전세', '월세', '단기임대', '연세']
# 네 소스가 함께 쓰는 거래 유형. 연세가 없는 소스의 거래 유형 안내(`infer_trade_types`)에 연세를 섞지 않는다
SHARED_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세', '단기임대')
# 예약 상태를 알려 주는 소스(당근)의 거래 상태. 거래완료는 내보내지 않는다 (만료 매물)
ListingStatus = Literal['판매중', '예약중']

# 이 명령이 받은 날짜 중 값이 있는데 날짜로 읽지 못한 원래 글자 (안내에 쓰는 칸 이름 -> 받은 차례대로의 글자). `read_date`·`move_in_label` 이
# 모으고 `cli.output.emit` 이 칸마다 [참고] 안내 한 줄로 붙인다 (`unread_date_notes`). 명령 시작에 `handle_errors` 가 `reset_unread_dates` 로
# 비운다. 응답에서 뺀 빈 항목의 합(`core.schema.null_item_tally`)과 같은 방식이라 변환 함수마다 notes 를 넘기지 않는다
# 파이썬에서 부르는 정문(`jibsa.providers.<source>`) 함수는 `with_notes` 가 부를 때마다 비우고 결과 `notes` 에 붙인다
_unread_dates: dict[str, list[str]] = {}
# `holding_unread_dates` 블록이 받는 곳. 안쪽 블록이 끝이다
_held_unread_dates: list[list[tuple[str, str]]] = []
# 매물 목록 `--fields` 에서 고를 수 있는 날짜 칸의 안내 이름 -> 출력 칸 이름. 소스가 이 이름으로 `read_date`·`move_in_label` 을 부른다.
# `--fields` 로 칸을 고르지 않았으면 `unread_date_notes` 가 그 안내를 뺀다
UNREAD_DATE_FIELDS: dict[str, str] = {
    '등록일': 'registered_date',
    '사용승인일': 'approved_date',
    '매물 확인일': 'confirmed_date',
    '입주일': 'move_in',
}
# 소스 이름 -> 안내에 쓰는 사이트 이름. 응답에서 뺀 빈 항목의 공통 안내(`null_items_total_note`)와 못 읽은 날짜 안내(`unread_date_notes`)에 쓴다
SITE_NAMES: dict[str, str] = {
    'zigbang': '직방',
    'naver': '네이버',
    'daangn': '당근',
    'dabang': '다방',
}

# 결과 notes 의 종류. 안내 앞에 '[일부] ' 처럼 붙여 LLM 이 문장을 다 읽지 않고도 무엇을 알리는지 가른다 (docs/llm.md).
# 일부: 더 받을 매물이 있다 / 범위: 찾은 범위가 요청과 다르다 / 제외: 받은 것 중 뺀 매물·후보가 있다 / 모호: 이름이 여러 곳이라
# 하나를 골랐다 / 거래: 거래 유형을 짐작해 좁혔다 / 실패: 덤 조회가 실패했거나 대체 경로로 찾았다 / 참고: 그 밖에 읽을 때 알 것
NoteKind = Literal['일부', '범위', '제외', '모호', '거래', '실패', '참고']
NOTE_KINDS: tuple[str, ...] = get_args(NoteKind)
# 결과는 냈지만 소스가 바뀌어 jibsa 를 고쳐야 한다는 `notes` 끝말. 매일 API 감시(scripts/monitor/api_check.py)가 이 말로
# 고장을 찾으니 손으로 쓰지 않고 이 상수를 쓴다. 차단 페이지일 수도 있는 형식 오류·GraphQL 에러(당근)나 읽지 못한 글자(다방)처럼
# 단정하지 못하면 MAYBE 를 쓰고, 감시는 주된 조회의 PARSE_ERROR·상태 없는 UPSTREAM_ERROR 처럼 둘 다 고장으로 센다
UPDATE_NEEDED: str = 'jibsa 업데이트가 필요합니다'
UPDATE_MAYBE_NEEDED: str = 'jibsa 업데이트가 필요할 수 있습니다'
# 빈 항목 안내(`null_items_note`·`null_items_total_note`)가 같이 쓰는 문구. 결과 notes 에 이미 빈 항목 안내가 있는지 이 말로 가른다
NULL_ITEMS_PHRASE: str = '개가 와서 빼고 읽었습니다'
# 이어 받을 수 있는 결과의 [일부] 안내 끝말. 예전 '결과의 next 를 --next 로 주세요' 는 --next 만 붙이라는 말로 읽혀,
# 값 없이 붙인 호출이 "Option '--next' requires an argument." 로 막혔다 (2026-11-10)
NEXT_HINT: str = '이어 보려면 같은 명령에 --next <결과의 next 값> 을 붙이세요'

# 한국어 거래 이름(매물 trade_type 값·--trade 입력) → 거래별로 묶은 출력 객체의 키. 키는 용어집 낱말이라 코드 속성 이름과 같다:
# 외국에도 있는 거래는 영어 뜻, 한국에만 있는 임대 제도는 소리대로 쓴다 (출력 규약 '칸 이름 규칙')
TRADE_KEY_BY_NAME: dict[str, str] = {
    '매매': 'sale',
    '전세': 'jeonse',
    '월세': 'wolse',
    '단기임대': 'short_term',
    '연세': 'yeonse',
    '전월세': 'jeonse_wolse',
}


class AmountSet(BaseModel):
    """거래 하나의 금액 묶음 (범위의 한 끝, 거래별 평균 등). 칸 이름은 매물 금액 칸과 같다.

    생성할 때 넘긴 칸만 출력한다. 넘긴 None 은 모름(null)이고, 넘기지 않은 칸은 그 거래에 해당 없음이라 키가 없다
    (매매는 price_manwon, 전세는 deposit_manwon, 월세·단기임대는 deposit_manwon·rent_manwon 만 넘긴다).
    """

    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 또는 전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    converted_price_manwon: Annotated[
        float | None,
        Field(description='전월세 환산가 (만원). 직방 평형 시세 추이의 전월세 거래 범위에만 있다')
    ] = None

    @model_serializer(mode='wrap')
    def keep_given_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unset_fields(self, handler(self), type(self).model_fields)


class AmountRange(BaseModel):
    """금액 범위. 두 끝은 거래 하나의 금액 묶음이다 (월세는 보증금·월세 짝)."""

    lowest: Annotated[
        AmountSet | None,
        Field(description='낮은 쪽 끝')
    ]
    highest: Annotated[
        AmountSet | None,
        Field(description='높은 쪽 끝')
    ]


class NumberRange(BaseModel):
    """숫자 하나짜리 범위 (단지 동 층수, 계약 주 수 등)."""

    lowest: Annotated[
        int | float | None,
        Field(description='낮은 쪽 끝. 모르면 null')
    ]
    highest: Annotated[
        int | float | None,
        Field(description='높은 쪽 끝. 모르면 null')
    ]


class Result(BaseModel):
    """명령이 돌려주는 결과의 공통 부모. `notes` 는 CLI 가 결과 맨 위 `notes` 로 붙이는 안내다 (출력 JSON 의 칸이 아니다).

    결과 모델마다 `notes` 에 어떤 안내가 들어가는지는 그 모델 docstring 의 `notes`: 문단에 적는다.
    """

    notes: Annotated[
        list[str],
        Field(exclude=True, description='CLI 가 결과 맨 위 notes 로 붙이는 안내. 출력 칸이 아니다')
    ] = []


class Listing(BaseModel):
    """소스와 무관하게 정규화한 매물 한 건 (목록 결과).

    jibsa 는 탐색용이라 매물을 고르는 데 필요한 정보만 담고, 사진·연락처·
    본문처럼 원 사이트를 대신하게 되는 정보는 담지 않는다. 확인과
    문의는 `url` 의 원 사이트에서 한다.

    소스마다 가격 단위가 다르므로(네이버: 원, 직방·당근: 만원) 모든 금액은
    **만원** 으로 통일한다. LLM 이 단위를 혼동하지 않도록 필드명에 단위를 붙인다.

    출력에서 값이 없는 필드는 의미에 따라 다르게 나타낸다.

    - 해당 없음 (그 거래 유형에 원래 없는 항목, 예: 월세의 `price_manwon`): 키를 뺀다
    - 모름 (해당은 되지만 소스가 알려 주지 않은 항목): `null`

    목록에서 소스가 늘 주지 않는 필드(당근 `manage_cost_manwon`·`registered_date`, 네이버
    `room_type`)도 키를 빼지 않고 `null` 이다. 키를 빼면 해당 없음으로 읽혀 관리비 없는 매물로 셈한다 (`null` 이면 상세를
    보라고 docs/llm.md 가 이른다). 결과 전체가 같은 값인 `source`·`trade_type` 도 소스를 섞어 비교할 때 매물 하나만 보고
    읽도록 남긴다. 출력을 줄이는 길은 `--fields` 다 (2026-10-23 실측: 직방 room 30건 14,424자 → docs/llm.md 권장 9필드
    7,540자, 48% 감소. 당근 목록에서 늘 null 인 세 필드는 매물 출력의 15%).

    Args:
        source: 매물을 가져온 소스.
        id: 소스 안에서의 매물 ID. 상세 명령에 그대로 넘긴다.
        url: 원 사이트 매물 페이지 URL.
        trade_type: 거래 유형.
        status: 거래 상태 ('판매중', '예약중'). 예약 상태를 알려 주는 소스(당근)만 채운다. 그 밖의 소스는 해당 없음이라
            출력에서 키를 뺀다. Defaults to None.
        property_type: 매물 유형 (원룸, 오피스텔, 빌라, 아파트 ...). 소스가 유형을 주지 않으면 null.
        room_type: 방 구조 (오픈형원룸 ... 포룸이상). 소스가 알려줄 때만.
            Defaults to None.
        title: 매물 한 줄 제목. Defaults to None.
        price_manwon: 매매가(만원). Defaults to None.
        deposit_manwon: 보증금 또는 전세금(만원). Defaults to None.
        rent_manwon: 월세(만원). Defaults to None.
        yearly_rent_manwon: 연세(만원). 1년치 월세를 한 번에 내는 제주 거래(당근 연세)에만 있다.
            Defaults to None.
        manage_cost_manwon: 월 관리비(만원). Defaults to None.
        area_m2: 전용면적(㎡). Defaults to None.
        area_pyeong: 전용면적(평). Defaults to None.
        floor: 해당 층 (예 '3', '반지하', '지하1', '옥탑'). 숫자로 온 지하층은
            `normalize_floor` 로 맞춘다. Defaults to None.
        building_floor: 건물 전체 층수. Defaults to None.
        address: 지번 주소. 소스가 번지를 주면 번지까지, 아니면 동까지. 시·도는 정식
            명칭으로 맞춘다 (`normalize_address`). Defaults to None.
        lat: 위도. 거리 계산용이며 출력하지 않는다. Defaults to None.
        lng: 경도. 거리 계산용이며 출력하지 않는다. Defaults to None.
        distance_km: 검색 중심점에서의 거리(km). Defaults to None.
        registered_date: 등록·노출 시작일 (YYYY-MM-DD). Defaults to None.
        approved_date: 사용승인일 (YYYY-MM-DD).
            Defaults to None.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    source: Annotated[
        Source,
        Field(description='매물을 가져온 소스')
    ]
    id: Annotated[
        str,
        Field(description='소스 안에서의 매물 ID. 상세 명령에 그대로 넘긴다')
    ]
    url: Annotated[
        str,
        Field(description='원 사이트 매물 페이지 URL. 확인·문의·계약은 여기서')
    ]
    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형')
    ]
    status: Annotated[
        ListingStatus | None,
        Field(description='거래 상태 (판매중, 예약중). 예약중은 계약이 깨질 수 있어 내보낸다. 예약 상태가 없는 소스는 키를 뺀다')
    ] = None
    property_type: Annotated[
        str | None,
        Field(description='매물 유형 (원룸, 오피스텔, 빌라, 아파트 ...). 소스가 유형을 주지 않으면 null')
    ]
    room_type: Annotated[
        str | None,
        Field(description='방 구조 (오픈형원룸, 분리형원룸, 복층형원룸, 투룸, 쓰리룸, 포룸이상). 소스가 알려줄 때만. 당근 투룸 이상은 목록에 방 수가 없어 null')
    ] = None
    title: Annotated[
        str | None,
        Field(description='매물 한 줄 제목')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 또는 전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    yearly_rent_manwon: Annotated[
        float | None,
        Field(description='연세 (만원, 1년치를 한 번에 낸다. 월세 아님). 제주 연세 거래(당근)에만 있고 그 밖에는 키가 없다')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='월 관리비 (만원)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="해당 층 (예 '3', '반지하', '지하1', '옥탑', '중층'). 출력에는 숫자 floor_number 가 뒤에 붙는다")
    ] = None
    building_floor: Annotated[
        str | None,
        Field(description='건물 전체 층수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소 (소스가 주면 번지까지, 아니면 동까지)')
    ] = None
    lat: Annotated[
        float | None,
        Field(exclude=True, description='위도. 거리 계산용, 출력 안 함')
    ] = None
    lng: Annotated[
        float | None,
        Field(exclude=True, description='경도. 거리 계산용, 출력 안 함')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심점에서의 거리 (km)')
    ] = None
    registered_date: Annotated[
        str | None,
        Field(description='등록·노출 시작일 (YYYY-MM-DD, 한국 날짜)')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None

    @field_validator('address')
    @classmethod
    def official_sido_name(cls, value: str | None) -> str | None:
        return normalize_address(value)

    @field_validator('floor')
    @classmethod
    def unified_floor_label(cls, value: str | None) -> str | None:
        return normalize_floor(value)

    def not_applicable_fields(self) -> frozenset[str]:
        """이 매물에 원래 존재하지 않는 필드. 출력에서 키째 뺀다.

        거래 유형에 없는 가격 필드와, 검색 중심점 없이 조회해 거리가 없는
        경우(단지 매물 목록 등)의 `distance_km`, 예약 상태를 알려 주지 않는 소스의 `status` 다.
        """
        fields = NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset())
        if self.distance_km is None:
            fields = fields | {'distance_km'}
        if self.status is None:
            fields = fields | {'status'}
        return fields

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.not_applicable_fields():
            data.pop(field, None)
        # 층이 해당 없는 매물(네이버 토지 등)은 floor 키가 없어 층 숫자도 붙지 않는다
        # 층이 '3'·'지하1'·'중층' 처럼 섞여 와 층으로 거르거나 정렬하기 어려워 숫자를 floor 바로 뒤에 붙인다
        return with_floor_number(data)


ListingT = TypeVar('ListingT', bound=Listing)


class ListingDetail(Listing, Result):
    """상세 조회로 보강한 매물. 매물을 고르는 데 필요한 사실만 더한다.

    사진, 본문, 중개사 연락처, 도로명 주소, 조회수는 담지 않는다.

    `move_in`·`parking` 은 모든 소스가 같은 꼴이다 (`move_in_label`·`parking_label`: '2026-10-24', '즉시입주',
    뒤에 ' (협의 가능)' / '가능', '불가', '가능 (총 4대)'). 네이버 `move_in` 만 '2026-12-01 이내'·'2026-12-01 이후'·
    '2026-11 초순'(중순·하순도)도 쓴다. 네이버 단지 유형(아파트·오피스텔·재건축·분양권) `parking` 만 가능·불가 없이 단지 대수
    `'단지 전체 N대 (세대당 M대)'` 다 (웹 칸에 주차가능여부가 없어 `parking_label` 을 쓰지 않는다). `nearby_stations` 는 소스 표기대로라 괄호 안 내용이 소스마다 다르다 (노선 / 도보 분).

    Args:
        room_count: 방 수. Defaults to None.
        bathroom_count: 욕실 수. Defaults to None.
        direction: 방향. Defaults to None.
        move_in: 입주 가능일. Defaults to None.
        parking: 주차 가능 여부·대수. Defaults to None.
        has_elevator: 엘리베이터 유무. Defaults to None.
        options: 옵션·시설. 소스가 주지 않으면 None, 줬는데 없으면 []. Defaults to None.
        manage_cost_includes: 관리비 포함 항목. Defaults to None.
        nearby_stations: 인근 지하철역. Defaults to None.
    """

    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    direction: Annotated[
        str | None,
        Field(description='방향')
    ] = None
    move_in: Annotated[
        str | None,
        Field(
            description="입주 가능일 ('2026-10-24', '즉시입주', 협의 가능하면 뒤에 ' (협의 가능)'. 네이버는 "
            "'2026-12-01 이내'·'2026-12-01 이후'·'2026-11 초순'·연월만 온 '2026-12' 도, 날짜 없이 협의만 가능하면 '협의 가능')"
        )
    ] = None
    parking: Annotated[
        str | None,
        Field(description="주차 ('가능', '불가', 대수가 있으면 '가능 (총 4대)'. 가능 여부를 모르면 대수만)")
    ] = None
    has_elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 유무')
    ] = None
    options: Annotated[
        list[str] | None,
        Field(description='옵션·시설 (에어컨, 세탁기 ...). 소스가 알려 주지 않으면 null')
    ] = None
    manage_cost_includes: Annotated[
        list[str] | None,
        Field(description='관리비 포함 항목. 소스가 알려 주지 않거나 소스가 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    nearby_stations: Annotated[
        list[str] | None,
        Field(description='인근 지하철역. 소스가 알려 주지 않으면 null. 직방은 노선, 당근은 도보 시간을 붙인다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 상세 조회에는 검색 중심점이 없어 거리가 해당 없다.
        return super().not_applicable_fields() | {'distance_km'}


def m2_to_pyeong(m2: float | None) -> float | None:
    if m2 is None:
        return None
    return round(m2 / SQUARE_METERS_PER_PYEONG, 1)


def won_to_manwon(won: float | int | str | None) -> float | None:
    """원 단위 값을 만원 단위로 바꾼다. 금액은 원 단위까지 낸다 (375,700원 → 37.57).

    빈 값이나 숫자가 아닌 문자열은 None. 만원 소수 넷째 자리가 1원이라, 1원 아래만 반올림해 부동소수점 찌꺼기를 지운다
    (docs/development/output-contract.md 금액 절).
    """
    if won is None or won == '':
        return None
    try:
        return round(float(won) / 10_000, 4)
    except (TypeError, ValueError):
        return None


def format_manwon(value: float | int) -> str:
    """만원 금액을 글자(라벨·안내 문구)로 쓴다. 반올림하지 않고 원 단위까지 쓴다 (37.57 → '37.57', 3.0 → '3').

    `:g` 는 유효숫자 6자리라 12345.6789 를 '12345.7' 로 줄이므로 쓰지 않는다. 천 단위 쉼표는 넣지 않는다.
    """
    if isinstance(value, int):
        return str(value)
    return f'{round(value, 4):.4f}'.rstrip('0').rstrip('.')


def js_round(value: float) -> int:
    """JS `Math.round` 처럼 .5 를 늘 올려 반올림한다. 사이트 웹(JS Math.round)과 숫자를 맞출 때 쓴다.

    Python `round` 는 .5 를 짝수로 보내 (2.5 → 2) 웹과 1 씩 달라진다.
    """
    return math.floor(value + 0.5)


def js_to_fixed(value: float, digits: int) -> Decimal:
    """JS `Number.prototype.toFixed(digits)` 처럼 소수 `digits` 자리로 반올림한다. 사이트 웹과 숫자를 맞출 때 쓴다.

    `toFixed` 는 float 의 정확한 이진 값으로 반올림하고 정확히 반이면 0 에서 먼 쪽으로 올린다. 그래서 정확한 값(`Decimal(value)`)을
    `ROUND_HALF_UP` 으로 맞춘다. Python `f'{x:.2f}'`·`round` 는 정확히 반인 값을 짝수로 보내고(84.125 → 84.12, 웹 84.13),
    `Decimal(str(x))` 는 이진 값이 반보다 조금 작은 소수를 올린다(0.15 → 0.2, 웹 0.1. 0.15 의 이진 값은 0.1499…) (2026-11-20 리뷰:
    다방 거리·당근 면적이 따로 흉내 내다 어긋났다). 기본 정밀도(28자리)면 1e26 부터 `InvalidOperation` 이라 float 최댓값(약 1.8e308)도
    담게 넉넉히 준다. JS 는 1e21 이상을 지수 표기로 내지만 jibsa 는 소수 자리를 그대로 낸다. 유한한 값만 받는다.
    """
    return Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP, context=Context(prec=400))


@overload
def normalize_address(address: str) -> str: ...


@overload
def normalize_address(address: None) -> None: ...


@overload
def normalize_address(address: str | None) -> str | None: ...


def normalize_address(address: str | None) -> str | None:
    """주소 첫 단어(시·도)를 정식 명칭으로 바꾼다 ('서울시 강남구' → '서울특별시 강남구').

    세종은 시·군·구가 없는데 소스가 '세종시 세종 반곡동'·'세종시 세종시 반곡동' 처럼 시를 한 번 더
    넣으므로 그 단어를 뺀다. 첫 단어가 이미 정식 명칭이어도 뺀다 (2026-10-10 실측: 직방 아파트 목록은
    '세종특별자치시 세종 반곡동', 2026-10-11 실측: 직방 상가 목록·상세는 local1·local2 가 둘 다
    '세종특별자치시'). 모르는 시·도거나 공백뿐이면 그대로 둔다.
    """
    words = address.split() if address else []
    if not words:
        return address
    first, *rest = words
    sido = SIDO_OFFICIAL_NAMES.get(first) or (first if first in SIDO_OFFICIAL_NAMES.values() else None)
    if sido is None:
        return address
    if sido == '세종특별자치시' and rest and rest[0] in ('세종', '세종시', '세종특별자치시'):
        rest = rest[1:]
    return ' '.join([sido, *rest])


def join_address(*parts: str | None) -> str | None:
    """주소 조각(시/구/동/번지)을 빈 값 없이 이어 붙인다."""
    address = ' '.join(part for part in parts if part)
    return address or None


def normalize_floor(floor: str | None) -> str | None:
    """숫자·B 로 온 지하층을 직방 표기에 맞추고 ('0.5' → '반지하', '-1'·'B1' → '지하1'), 저·중·고를 저층·중층·고층으로 맞춘다.

    당근은 반지하를 0.5, 지하를 음수로, 네이버는 지하를 음수나 'B1' 로 준다. 직방은 처음부터
    '반지하' 로 준다. 층을 숫자 대신 밝힌 매물은 직방·네이버가 '저'·'중'·'고', 당근이 '저층'·'중층'·'고층' 으로 준다
    (2026-10-20 실측: 강남역·역삼동 목록). 그 밖의 값('3', '옥탑방' ...)은 그대로 둔다.
    """
    if floor is None:
        return None
    if floor in RELATIVE_FLOOR_LABELS:
        return RELATIVE_FLOOR_LABELS[floor]
    basement = BASEMENT_FLOOR_PATTERN.match(floor)
    if basement is not None:
        return f'지하{int(basement.group(1))}'
    try:
        number = float(floor)
    except ValueError:
        return floor
    if number == 0.5:
        return '반지하'
    if number < 0 and number.is_integer():
        return f'지하{int(-number)}'
    return floor


def floor_number(floor: str | None) -> int | None:
    """정규화한 층(`normalize_floor`)의 숫자. 지상은 양수, 지하는 음수다 ('3' → 3, '지하1' → -1).

    반지하·저층·옥탑처럼 몇 층인지 모르는 표기는 None (모름)이다. 층으로 거르거나 정렬할 때 쓴다.
    """
    if floor is None:
        return None
    # isdigit 은 int() 가 못 읽는 위첨자('²')도 받아 직렬화 중에 ValueError 가 난다. isdecimal 은 int() 가 읽는 숫자만 받는다
    if floor.isdecimal():
        return int(floor)
    if floor.startswith('지하') and floor[2:].isdecimal():
        return -int(floor[2:])
    return None


def insert_after(data: dict[str, Any], anchor: str, key: str, value: Any) -> dict[str, Any]:
    """`anchor` 키 바로 뒤에 `key` 를 넣은 새 dict. `anchor` 가 없으면 맨 뒤에 넣는다 (출력 JSON 의 키 순서를 맞출 때)."""
    if anchor not in data:
        return {**data, key: value}
    result: dict[str, Any] = {}
    for name, item in data.items():
        result[name] = item
        if name == anchor:
            result[key] = value
    return result


def rescale(value: float | int | None, factor: str) -> float | None:
    """단위를 바꾸는 곱셈. 부동소수점 찌꺼기 없이 곱하고 반올림하지 않는다. None 은 None.

    예: `rescale(0.6523, '100')` → 65.23, `rescale(850, '0.001')` → 0.85, `rescale(0.85, '1000')` → 850.0.
    """
    if value is None:
        return None
    return float(Decimal(str(value)) * Decimal(factor))


def floor_text(value: int | str | None) -> str | None:
    """거래·실거래 행의 층 값을 매물과 같은 글자로 쓴다. None 은 None (`3` → '3', `-1` → '지하1')."""
    if value is None:
        return None
    return normalize_floor(str(value))


def with_floor_number(data: dict[str, Any]) -> dict[str, Any]:
    """직렬화한 dict 에 `floor` 키가 있으면 바로 뒤에 `floor_number` 를 붙인다. 층 키가 없으면(해당 없음) 그대로 돌려준다."""
    if 'floor' not in data:
        return data
    return insert_after(data, 'floor', 'floor_number', floor_number(data['floor']))


def years_ago(today: date, years: int) -> str:
    """`years` 년 전 같은 날 (2월 29일이면 28일). 실거래 기간(`--period`·`--years`)의 시작일이다."""
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def months_ago(today: date, months: int) -> str:
    """`months` 개월 전 같은 날 (그 달에 없는 날이면 그 달 말일). 실거래·시세 기간(`--period`)의 시작일이다.

    12 의 배수는 `years_ago` 와 같은 날을 준다 (2월 29일 → 평년 2월 28일).
    """
    index = today.year * 12 + today.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return today.replace(year=year, month=month, day=min(today.day, monthrange(year, month)[1])).isoformat()


def normalize_date(value: str | None) -> str | None:
    """날짜를 한국 날짜 기준 `YYYY-MM-DD` 로 맞춘다.

    `20100706`, `2018.04.27`, `1995-10-26 `, `1991년 6월 5일` 같은 날짜와, 시각이 붙은 일시도 받는다.
    일시는 시각을 버리고 날짜만 남긴다 (네이버가 날짜만 주므로 소스끼리 맞춘다).
    시간대가 없으면 한국 시간으로 보고, UTC(`...Z`)는 한국 시간으로 바꾼 뒤 날짜를
    뽑는다 (UTC 15시 이후는 한국 날짜로 다음 날). 읽을 수 없으면 앞뒤 공백만 지운
    원래 값을 돌려준다 (정보를 버리지 않는다). 연월만 있는 값(`202411`, `2024.11`)도 그대로 둔다.
    소스가 값이 없다는 표시로 주는 `-` 는 값이 아니라 None 이다 (빈 글자도 None).
    """
    if value is None:
        return None
    text = value.strip()
    if text == '-':
        return None
    match = DATE_DIGITS_PATTERN.match(text)
    if match is not None:
        year, month, day = (int(part) for part in match.groups() if part is not None)
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return text
    try:
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text or None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(KST).date().isoformat()


def iso_date(value: str | None) -> str | None:
    """날짜 글자를 `YYYY-MM-DD` 로 읽으면 그 값, 읽지 못하면(연월만·'-'·빈 값·문장·없는 날짜) None.

    입주일처럼 날짜인지 가려야 할 때 쓴다 (`normalize_date` 는 못 읽으면 원래 값을 돌려준다). 꼴만 맞고 없는
    날짜('0000-00-00'·'2026-02-30')는 `normalize_date` 가 원래 값 그대로 돌려줘 꼴만 보면 날짜로 통과하므로 달력으로 확인한다.
    출력 날짜 칸에는 못 읽은 글자를 `[참고]` 로 알리는 `read_date` 를 쓴다.
    """
    text = normalize_date(value)
    if text is None or not ISO_DATE_PATTERN.match(text):
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def reset_unread_dates() -> None:
    """못 읽은 날짜 모음을 비운다. 명령이 시작할 때 `cli.output.handle_errors` 가, 정문 함수를 부르기 전에 `with_notes` 가 부른다."""
    _unread_dates.clear()


def add_unread_date(what: str, raw: str) -> None:
    """값이 있는데 날짜·연월로 읽지 못한 원래 글자를 명령 모음에 넣는다. `holding_unread_dates` 블록 안이면 그 블록이 받는다."""
    entry = raw.strip()
    if _held_unread_dates:
        _held_unread_dates[-1].append((what, entry))
    else:
        _unread_dates.setdefault(what, []).append(entry)


@contextmanager
def holding_unread_dates() -> Iterator[list[tuple[str, str]]]:
    """블록 안에서 모은 못 읽은 날짜를 명령 모음에 넣지 않고 돌려준다 ((칸 이름, 원래 글자) 목록).

    변환한 뒤에 거르거나(반경·중복) 자르는(`--limit`) 목록이 출력에 남지 않는 항목의 날짜까지 세지 않도록, 항목마다 이 블록
    안에서 바꾸고 최종 목록이 정해진 뒤 남은 항목의 것만 `keep_unread_dates` 로 넣는다.
    """
    held: list[tuple[str, str]] = []
    _held_unread_dates.append(held)
    try:
        yield held
    finally:
        _held_unread_dates.pop()


def keep_unread_dates(held: Iterable[tuple[str, str]], *, only: Container[str] | None = None) -> None:
    """`holding_unread_dates` 가 돌려준 것을 명령 모음에 넣는다. `only` 를 주면 그 칸 이름만 넣는다."""
    for what, raw in held:
        if only is None or what in only:
            add_unread_date(what, raw)


def read_date(value: str | None, what: str, *, raw: str | None = None) -> str | None:
    """출력 날짜 칸의 값을 `YYYY-MM-DD` 로 읽는다 (output-contract.md 날짜 칸 규칙).

    소스가 값 없음으로 준 것(None·빈 글자·'-')은 안내 없이 None 이다. 값이 있는데 날짜로 읽지 못하면(연월만·문장·달력에
    없는 날) 받은 글자를 내지 않고 None 을 돌려주며, 원래 글자를 `what` 칸으로 모아 `emit` 이 `[참고]` 로 알리게 한다.
    거르기·비교처럼 출력 칸이 아닌 자리는 `iso_date`·`normalize_date` 를 쓴다 (여기 쓰면 안내가 붙는다).

    Args:
        value: 소스가 준 날짜 글자.
        what: 안내에 쓰는 한국어 칸 이름 ('사용승인일', '계약일'). 같은 이름은 한 줄로 모인다.
        raw: 안내에 보일 원래 글자. 부르는 쪽이 글자를 조립해 넘길 때 소스가 준 글자를 준다 (다방 '20' + 계약일).
    """
    text = normalize_date(value)
    if text is None:
        return None
    date = iso_date(text)
    if date is None:
        add_unread_date(what, text if raw is None else raw)
    return date


def read_month(value: str | None, what: str, *, raw: str | None = None) -> str | None:
    """출력 연월 칸(`_month`)을 `YYYY-MM` 으로 읽는다. 'YYYY-MM'·'YYYYMM'·'YYYY.MM' 을 받는다.

    값 없음(None·빈 글자·'-')은 안내 없이 None 이다. 값이 있는데 못 읽으면(꼴이 다르거나 13월) None 을 돌려주고
    원래 글자를 `what` 칸으로 모은다 (`read_date` 와 같다).
    """
    if value is None:
        return None
    text = value.strip()
    if text in ('', '-'):
        return None
    match = YEAR_MONTH_TEXT_PATTERN.fullmatch(text)
    month = (match.group(2) or match.group(3)) if match else None
    if match is not None and month is not None and 1 <= int(month) <= 12:
        return f'{match.group(1)}-{int(month):02d}'
    add_unread_date(what, text if raw is None else raw)
    return None


def unread_date_notes(site: str, fields: Container[str] | None = None) -> list[str]:
    """이 명령에서 읽지 못한 날짜를 칸마다 `[참고]` 한 줄로. 모은 것이 없으면 빈 목록. `collected_notes` 가 모아 `cli.output.emit`·`with_notes` 가 notes 끝에 붙인다.

    Args:
        site: 사이트 이름 ('직방', '네이버', '당근', '다방'). 조사는 끝 글자에 맞춘다.
        fields: `--fields` 로 고른 칸. 고르지 않은 날짜 칸의 안내는 출력에 그 칸이 없어 뺀다.
    """
    notes: list[str] = []
    for what, texts in _unread_dates.items():
        if fields is not None and what in UNREAD_DATE_FIELDS and UNREAD_DATE_FIELDS[what] not in fields:
            continue
        # 예는 겹치지 않게 앞 셋만 보인다 (같은 글자가 여러 건이면 한 번만)
        examples = ', '.join(f"'{text}'" for text in list(dict.fromkeys(texts))[:3])
        subject = f"{site}{particle(site, '이/가')} 준 {what}"
        if len(texts) == 1:
            body = f"{subject}{particle(what, '을/를')} 읽지 못해 null 로 냈습니다 ({examples})"
        else:
            body = f'{subject} {len(texts)}건을 읽지 못해 null 로 냈습니다 (예: {examples})'
        notes.append(note('참고', f'{body}. 사이트 화면에서 확인하세요'))
    return notes


def move_in_label(value: str | None, *, negotiable: bool = False) -> str | None:
    """입주 가능일을 모든 소스가 같은 꼴로 쓴다: 날짜는 `YYYY-MM-DD`, 날짜 없이 바로면 `즉시입주`, 협의 가능하면
    뒤에 ` (협의 가능)`.

    직방 옛 상세 API 의 문장('즉시 입주 가능 (협의가능)', '2026.10.15 이후 입주 가능 (입주협의)')도 받는다. 괄호 안이
    '협의가능'(띄어쓰기 무시)이면 협의 가능, 즉시입주면 뺀다. 그 밖의 설명('입주협의'·'현세입자 빠른협의')은 직방 웹 화면처럼
    뒤에 그대로 붙인다 (2026-11-26 사용자 결정: 전에는 '협의' 가 든 설명을 모두 '협의 가능' 으로 바꿔 중개사가 쓴 뜻이 사라졌다).
    날짜를 읽지 못하면 모름(None)이고 원래 문구는 `[참고]` 안내로 알린다 (`read_date`). 날짜 자리가 비었거나 `-` 면 소스가
    값 없음으로 준 것이라 안내 없는 모름이다.
    """
    # 소스가 값 없음으로 주는 '-' 는 안내 없는 모름이다 (read_date 와 같다)
    if value is None or value.strip() in ('', '-'):
        return None
    text = value.strip()
    match = MOVE_IN_PAREN_PATTERN.match(text)
    head, extra = (match.group(1).strip(), match.group(2).strip()) if match else (text, '')
    if extra.replace(' ', '') == MOVE_IN_NEGOTIABLE:
        negotiable, extra = True, ''
    elif extra.replace(' ', '') == MOVE_IN_NOW:
        extra = ''
    head = head.replace('이후 입주 가능', '').strip()
    if head in ('', '-'):
        # 날짜 자리가 값 없음이면 괄호 설명만 있어도 안내 없는 모름이다 (read_date 와 같다)
        return None
    if '즉시' in head:
        label = MOVE_IN_NOW
    else:
        date = iso_date(head)
        if date is None:
            # 못 읽은 입주일은 받은 글자를 내지 않고 모름(None)이다. 원래 글자(괄호 안 협의 문구 포함)는 `[참고]` 안내로 알린다
            # (`read_date` 와 같다, 2026-11-26 사용자 결정)
            add_unread_date('입주일', text)
            return None
        label = date
    if extra:
        label += f' ({extra})'
    return with_negotiable(label, negotiable)


def with_negotiable(label: str, negotiable: bool | None) -> str:
    """입주 시기 글자 뒤에 협의 가능이면 ` (협의 가능)` 을 붙인다. 소스마다 같은 꼴로 쓰도록 접미사를 한 곳에 둔다."""
    return label + (' (협의 가능)' if negotiable else '')


def parking_label(available: bool | None, detail: str | None = None) -> str | None:
    """주차를 모든 소스가 같은 꼴로 쓴다: `가능`·`불가`, 대수가 있으면 괄호로 붙인다 (`가능 (총 4대)`). 가능 여부를 모르면 대수만."""
    status = None if available is None else '가능' if available else '불가'
    if status and detail:
        return f'{status} ({detail})'
    return status or detail


def in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    """범위 조건에 맞는지. 조건이 있는데 값을 모르면 맞지 않는다고 본다 (서버가 받지 않아 받은 뒤 거르는 조건에 쓴다).

    직방 아파트·상가(면적·공급면적·상가 조건)가 같은 규칙으로 거르게 한 곳에 둔다.
    """
    if minimum is None and maximum is None:
        return True
    return value is not None and (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def note(kind: NoteKind, text: str) -> str:
    """종류 태그를 붙인 안내 (`'[일부] 조건에 맞는 매물 ...'`). 태그 없이 둔 안내는 출력할 때 [참고] 가 붙는다 (`tagged_notes`)."""
    return f'[{kind}] {text}'


# 평형 하나를 묻는 실거래(네이버·다방)는 국토부 신고에 평형 타입이 없어 전용면적이 같은 평형끼리 같은 거래를 준다.
# 2026-10-31 실측: 헬리오시티 84㎡대 네이버 평형 5개(11·12·13·14·16)가 3년 매매 165건 안팎을 서로 164~166건씩 겹쳐 주어
# 합치면 1,309건이 실제 329건이었고, 다방 84.98㎡ 평형 둘(168340·168341)도 1년 32건 중 31건이 같았다. 에이전트가 평형별로
# 받아 더하면 몇 배로 세고, 평형 하나만 보면 그 타입 거래만 본 줄 안다 (docs 에만 적어 두었을 때 둘 다 일어났다)
SAME_AREA_PYEONG_TRADES_NOTE: str = note(
    '참고',
    '국토부 신고에 평형 타입이 없어 전용면적이 같은 다른 평형에도 같은 거래가 들어 있습니다. 평형 여러 개의 거래를 합칠 때는 '
    '같은 날·층·금액을 한 번만 세세요',
)


def null_items_note(what: str, count: int, unknown: Sequence[str] = ()) -> str:
    """사이트가 객체 목록 안에 빈 항목(null)을 줘서 빼고 읽었다는 안내. 그 목록으로 계산한 값을 모를 때 이 안내를 함께 낸다.

    응답 모델이 목록 칸의 null 원소를 빼고 그 수를 센다 (`ResponseModel.null_items`). 서비스는 그 목록으로 세거나 계산한 값을
    틀린 채로 내지 않고 null 로 두거나 목록 길이에 뺀 수를 더해 센 뒤, 이 안내로 알린다. 끝말이 `UPDATE_MAYBE_NEEDED` 라
    매일 API 감시(scripts/monitor/api_check.py)가 이런 응답을 고장으로 알린다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 (예: '직방 단지 매물', '네이버 관리비 항목').
        count: 빼고 읽은 빈 항목 수.
        unknown: 그 때문에 알 수 없어 null 로 둔 출력 칸 이름. 비면 그 문장을 쓰지 않는다 (자리를 세는 값만 바로잡은 경우).
    """
    names = ', '.join(unknown)
    unknown_text = f' {names} 값은 알 수 없어 null 입니다.' if names else ''
    return note('제외', f'{what} 목록에 빈 항목 {count}{NULL_ITEMS_PHRASE}.{unknown_text} {UPDATE_MAYBE_NEEDED}')


def null_items_total_note(site: str, count: int) -> str:
    """응답 어디에서든 빈 항목(null) `count` 개를 빼고 읽었다는 공통 안내. 어느 목록인지는 말하지 않는다.

    계산에 쓰지 않고 보여 주기만 하는 목록도 조용히 빼지 않게, 명령이 뺀 수의 합이 0 보다 크고 결과 notes 에 `null_items_note` 가
    없을 때 `collected_notes` 를 거쳐 `cli.output.emit`·`with_notes` 가 붙인다 (`core.schema.null_item_tally`). 끝말이 `UPDATE_MAYBE_NEEDED` 라 매일 API 감시가 알린다.

    Args:
        site: 사이트 이름 ('직방', '네이버', '당근', '다방').
        count: 응답에서 빼고 읽은 빈 항목 수.
    """
    return null_items_note(f'{site} 응답의', count)


def collected_notes(site: str, notes: Sequence[str], fields: Container[str] | None = None) -> list[str]:
    """명령(또는 정문 함수 한 번) 동안 모은 안내: 못 읽은 날짜 `[참고]`(`unread_date_notes`)와, 응답에서 빈 항목을 뺐는데
    `notes` 에 빈 항목 안내가 없으면 공통 `[제외]` 안내(`null_items_total_note`). `cli.output.emit` 과 정문 함수를 감싸는 `with_notes` 가 쓴다.

    Args:
        site: 사이트 이름 ('직방', '네이버', '당근', '다방').
        notes: 이 안내 앞에 이미 있는 안내. 빈 항목 안내가 이미 있는지 본다.
        fields: `--fields` 로 고른 칸. 고르지 않은 날짜 칸의 안내는 뺀다.
    """
    collected = unread_date_notes(site, fields)
    count = null_item_tally()
    if count > 0 and not any(NULL_ITEMS_PHRASE in text for text in [*notes, *collected]):
        collected.append(null_items_total_note(site, count))
    return collected


def with_notes(source: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """정문(`jibsa.providers.<source>`) 함수를 감싼다. 부르기 전에 못 읽은 날짜·뺀 빈 항목 모음을 비우고, 결과가 `Result` 면
    `collected_notes` 를 결과 `notes` 끝에 붙인다. 파이썬에서 바로 불러도 CLI 출력과 같은 안내를 받고, 앞 호출의 안내가 섞이지 않는다.

    service 함수 정의에는 쓰지 않는다: CLI 는 감싸지 않은 service 함수를 쓰고 명령 하나가 여러 함수를 부르므로, 감싸면 뒤 호출이 앞의 안내를
    지우고 `emit` 이 같은 안내를 또 붙인다. 모음이 전역이라 여러 스레드에서 동시에 부르면 안내가 섞일 수 있다.

    Args:
        source: 소스 이름 ('zigbang', 'naver', 'daangn', 'dabang'). `SITE_NAMES` 로 안내의 사이트 이름을 정한다.
    """
    site = SITE_NAMES[source]

    def wrap(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            reset_unread_dates()
            reset_null_item_tally()
            result = func(*args, **kwargs)
            if isinstance(result, Result):
                result.notes = [*result.notes, *collected_notes(site, result.notes)]
            return result

        return wrapper

    return wrap


def is_rejected(exc: Exception | None) -> bool:
    """덤 조회 실패가 거절·형식 변경인지: ValueError, 4xx, `exc` 가 None(`isSuccess` false). 서버 오류(5xx)·연결 실패는 아니다.

    참이면 업데이트 안내를 붙여 매일 API 감시가 고장으로 잡는다. 네 소스가 같은 기준을 쓴다 (네이버·다방·직방은 `lookup_failure_note`·
    `lookup_failure_reason`, 당근 `needs_update` 는 이 기준에 당근만의 실패를 더한다).
    """
    return exc is None or isinstance(exc, ValueError) or (isinstance(exc, HTTPStatusError) and exc.response.status_code < 500)


class LookupFailures:
    """덤 조회를 여러 번 하는 반복(`--details` 등)의 실패를 모아 안내 이유를 고른다.

    이유는 실패 순서가 아니라 다음 할 일로 고른다 (업데이트 필요 > 요청 제한 > 서버 오류·연결 실패). 예전에는 첫 실패만
    알려 5xx 다음 403 이면 '잠시 뒤' 만 나가 매일 감시가 거절을 놓쳤다 (2026-11-20 리뷰·사용자 결정). 종류마다 첫 예외만
    남긴다. `needs_update` 는 소스가 업데이트 안내를 붙이는 갈래와 같게 넘긴다 (기본은 `lookup_failure_reason` 의 갈래, 당근은
    `needs_update`).

    Attributes:
        count: 실패한 수 + 요청 제한 뒤라 요청하지 않은 수.
    """

    def __init__(self, needs_update: Callable[[Exception], bool] = is_rejected) -> None:
        self._needs_update = needs_update
        self.count = 0
        self._rate_limited: RateLimitedError | None = None
        self._update_needed: Exception | None = None
        self._other: Exception | None = None

    def add(self, exc: Exception) -> None:
        """실패 하나를 센다. 종류(요청 제한·업데이트 필요·그 밖)마다 첫 예외만 남긴다."""
        self.count += 1
        if isinstance(exc, RateLimitedError):
            if self._rate_limited is None:
                self._rate_limited = exc
        elif self._needs_update(exc):
            if self._update_needed is None:
                self._update_needed = exc
        elif self._other is None:
            self._other = exc

    def skip(self) -> None:
        """요청 제한 뒤라 요청하지 않은 매물을 센다."""
        self.count += 1

    @property
    def stopped(self) -> bool:
        """요청 제한이 왔는지. 참이면 부르는 쪽이 남은 매물을 요청하지 않는다 (다음 요청도 같은 제한에 걸린다)."""
        return self._rate_limited is not None

    def reason(self, describe: Callable[[Exception], str]) -> str | None:
        """안내 이유 (`describe` 로 만든 문장). 실패가 없으면 None.

        업데이트 필요가 있으면 그 이유 (요청 제한도 왔으면 덧붙임), 없으면 요청 제한, 없으면 그 밖의 첫 실패 이유다.
        업데이트가 필요하면 그 밖의 실패(5xx 등)는 말하지 않는다.
        """
        if self._update_needed is not None:
            text = describe(self._update_needed)
            if self._rate_limited is not None:
                text += f'. 요청 제한에도 걸려 그 뒤로는 요청하지 않았습니다. {self._rate_limited.message}'
            return text
        if self._rate_limited is not None:
            return describe(self._rate_limited)
        if self._other is not None:
            return describe(self._other)
        return None


def lookup_failure_reason(exc: Exception | None, site: str, what: str) -> str:
    """덤 조회 실패의 이유 한 구절 (`note('실패', ...)` 문장 뒤에 이어 쓴다). 실패 이유마다 다음 행동이 달라 이유를 넣는다.

    사이트가 요청을 거절했거나(4xx) 응답 형식이 바뀌면 업데이트 안내를 붙인다 (매일 감시가 고장으로 본다). 요청 제한·서버
    오류(5xx)·연결 실패는 사이트가 바뀐 것이 아니라 붙이지 않는다 (감시는 확인 못 함으로 본다).

    Args:
        exc: 실패 예외. None 이면 응답이 isSuccess false 였던 것이라 거절로 본다 (네이버).
        site: 사이트 이름 ('다방', '직방'). 조사는 끝 글자에 맞춘다.
        what: 받지 못한 것 ('매물 상세').
    """
    if isinstance(exc, RateLimitedError):
        return f'요청 제한에 걸렸습니다. {exc.message}'
    if is_rejected(exc):
        return f"{site}{particle(site, '이/가')} {what} 요청을 거절했거나 응답 형식이 바뀌었습니다. {UPDATE_MAYBE_NEEDED}"
    return f'{site} {what} 요청이 실패했습니다 ({type(exc).__name__}). 잠시 뒤 다시 시도하세요'


def lookup_failure_note(exc: Exception | None, site: str, what: str, unknown: str) -> str:
    """덤 조회를 받지 못한 `[실패]` 안내. 무슨 일 → 할 일 → 모름이 된 칸 순서라 모름이 된 칸이 늘 끝이다.

    요청 제한이 아니면 `lookup_failure_reason` 의 문장에 모름이 된 칸을 잇는다. 요청 제한만 따로 쓰는 것은 reason 이 받지 못한 것을 말하는 앞 문장 뒤에
    이어 쓰는 구절이라 무엇을 받지 못했는지 넣지 않기 때문이다.

    Args:
        exc: 실패 예외. `None` 이면 응답이 `isSuccess` false 였던 것이라 거절로 본다 (네이버).
        site: 사이트 이름 ('다방', '네이버'). 조사는 끝 글자에 맞춘다.
        what: 받지 못한 조회 이름 ('최근 실거래 요약').
        unknown: 그 실패로 모름이 된 칸과 다음 할 일 (끝에 마침표 없음).
    """
    if isinstance(exc, RateLimitedError):
        return note('실패', f"요청 제한에 걸려 {what}{particle(what, '을/를')} 받지 못했습니다. {exc.message}. {unknown}")
    return note('실패', f'{lookup_failure_reason(exc, site, what)}. {unknown}')


def more_hint(limit: int, max_limit: int, narrow: str | None, *, option: str = '--limit') -> str:
    """결과가 더 남았을 때 더 보는 법 (끝에 마침표 없음). `--limit` 이 이미 최대값이면 늘리라고 하지 않는다.

    늘리면 옵션 검사에서 `INVALID_ARGUMENT` 로 막힌다. 소스마다 따로 쓰던 '--limit 의 최대값은 N입니다…' 를 여기 모은다.
    따로 고치다 반경 검색 일부만 '반경' 으로 바뀌었다 (2026-11-10 리뷰·실측: 직방 아파트 강남역 --limit 120·네이버 반경
    단지 강남역이 '조건·지역을 좁히세요', 직방 상가 강남역은 '…조건·반경을 좁히세요').

    Args:
        limit: 요청한 `--limit`.
        max_limit: 그 명령의 `--limit` 최대값.
        narrow: 좁히라고 권할 것. 그 명령에 있는 옵션만 적는다 (예: '조건·반경', '거래 유형·업종·가격 조건·지역').
            None 이면 좁힐 조건을 권하지 않고 `--limit` 만 말한다 (다방 동네정보 목록처럼 좁힐 옵션을 이미 골랐을 때).
        option: 개수를 정하는 옵션 이름. 당근 `region-reviews` 는 `--limit` 이 없고 `--top` 이다 (2026-11-20).
    """
    if narrow is None:
        if limit >= max_limit:
            return f'{option} 의 최대값은 {max_limit}입니다'
        return f'더 보려면 {option} 을 늘리세요'
    target = f"{narrow}{particle(narrow, '을/를')}"
    if limit >= max_limit:
        return f'{option} 의 최대값은 {max_limit}입니다. 더 보려면 {target} 좁히세요'
    return f'더 보려면 {option} 을 늘리거나 {target} 좁히세요'


def tagged_notes(notes: list[str]) -> list[str]:
    """출력할 안내마다 종류 태그를 붙인다. 이미 붙었으면 그대로, 없으면 [참고]. 같은 안내는 한 번만 남긴다."""
    tagged = [
        text if any(text.startswith(f'[{kind}] ') for kind in NOTE_KINDS) else note('참고', text)
        for text in notes
    ]
    return list(dict.fromkeys(tagged))


def by_distance(listing: 'Listing') -> tuple[bool, float]:
    """가까운 순 정렬 키. 거리를 모르는 매물은 가장 가깝다고 내보내지 않도록 맨 뒤로 보낸다."""
    return listing.distance_km is None, listing.distance_km or 0


def limit_notes(
    total: int | None,
    returned: int,
    limit: int,
    *,
    max_limit: int,
    narrow: str | None,
    order: str = '검색 중심에서 가까운',
    approximate: bool = False,
    inspected: int,
    offset: int = 0,
    resumable: bool = False,
    has_more: bool | None,
) -> list[str]:
    """조건에 맞는 매물이 `limit` 보다 많아 일부만 돌려줄 때의 안내.

    "역삼동" 처럼 넓게 찾으면 네이버만 4천 건이 넘는데, 몇십 건만 받은 LLM 이 그게 전부라고
    오해하지 않도록 알리고 조건이나 지역을 좁히게 한다.

    Args:
        total: 조건에 맞는 매물 수 (모르면 None).
        returned: 돌려준 매물 수.
        limit: 요청한 최대 결과 수.
        max_limit: 그 명령의 `--limit` 최대값. 이미 최대값이면 늘리라고 하지 않는다. 늘리면 옵션 검사에서 막혀
            `INVALID_ARGUMENT` 가 난다 (2026-11-10 실측: 직방 stay 서울시 --limit 120 1917건·store 역삼역 --limit 120
            2580건에 '--limit 을 늘리거나'). 빠뜨리면 같은 문제가 다시 생기므로 기본값 없이 받는다.
        narrow: 좁히라고 권할 것 전체 (`more_hint`). 그 명령에 있는 옵션만 적고, 동 경계·시군구 검색이면 '·지역', 역·좌표·
            --radius 의 반경 검색이면 '·반경' 을 붙인다 (예: 상가 반경 검색 '거래 유형·업종·가격 조건·반경'). 반경 검색에 '지역'
            을 권하면 강남역처럼 이미 좁게 찾은 검색에도 '더 좁은 지역' 이 붙고, 단지 하나의 매물처럼 좁힐 범위가 없는데 붙이면
            다방 단지 매물이 '조건·지역을 좁히세요' 라고 했다 (2026-11-10 리뷰). 예전에는 '조건'·지역 기본값과 반경·범위 플래그로
            받았는데, 빠뜨려도 조용히 '조건·지역' 이 나가 `max_limit` 처럼 기본값 없이 받는다 (`pagination_notes`·
            `apt_pagination_notes` 와 같다, 2026-11-11 리뷰). None 이면 좁힐 조건을 권하지 않는다 (좁힐 옵션을 이미 모두 골랐을 때).
        order: 돌려준 매물을 고른 기준. 뒤에 '순으로' 를 붙여 쓴다 (예: '검색 중심에서 가까운', '최근 게시된', '다방 목록').
        approximate: `total` 이 근사값이면 True ('약 N건').
        inspected: 요약을 받아 확인한 매물 수 (조회 예산). `returned` 대신 이 값으로 `limit` 에 닿았는지 본다.
            받은 뒤 거래 불가로 뺀 매물만큼 다시 채우지 않으므로, 1건만 빠져도 `returned < limit` 이 되어 안내가
            사라지던 문제를 막는다 (직방 역삼동 원룸 --limit 15 에서 1건이 빠지면 '약 660건' 안내가 없었다).
        offset: 이어 받은 검색(`--next`)에서 앞서 받은 매물 수. 몇 번째부터인지 알린다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        has_more: 결과의 `has_more`. False 면 안내하지 않는다. `total` 은 거래 불가로 빼기 전 수라 `returned` 와 견주면, 범위 안
            매물을 다 받고 1건만 빠져도 '더 보려면 --limit 을 늘리라' 고 했다 (직방 동 경계 안 15건을 --limit 15 로 다 받고 1건이
            빠진 경우, 2026-10-23 리뷰). `max_limit` 처럼 빠뜨리지 않게 기본값 없이 받는다.
    """
    if inspected < limit or has_more is False:
        return []
    if total is None or total <= offset + returned:
        return []
    # 전체 수를 먼저 말하고 그중 몇 건을 보여 주는지 잇는다. 예전 '약 41건 중 검색 중심에서 가까운 1건입니다' 는 무엇이
    # 1건인지 바로 와닿지 않았다 (2026-11-10). 1건만 준 까닭으로 --limit 을 들지 않는다: 확인한 뒤 뺀 매물이 있으면
    # '--limit 15 라 14건' 처럼 어긋나고, 이어 받을 수 있는 검색에서 next 대신 --limit 을 늘려 처음부터 다시 찾게 한다
    found = f"조건에 맞는 매물이 {'약 ' if approximate else ''}{total}건"
    start = f'{offset + 1}번째부터 ' if offset else ''
    if returned:
        shown = f"{found} 있고, 그중 {order} 순으로 {start}{returned}건{'을' if offset else '만'} 보여 줍니다"
    else:
        # 확인한 매물이 모두 빠지면(거래 불가 등) '0건만 보여 줍니다' 가 되어 따로 쓴다
        shown = f'{found} 있지만, {order} 순으로 {start}확인한 매물이 모두 빠져 보여 줄 매물이 없습니다'
    # 안내 문장은 끝에 마침표가 없어 다른 안내와 이어 붙일 수 있다
    if resumable:
        return [note('일부', f'{shown}. {NEXT_HINT}')]
    return [note('일부', f'{shown}. {more_hint(limit, max_limit, narrow)}')]


def number_range(lowest: int | float | None, highest: int | float | None) -> NumberRange | None:
    """두 끝으로 만든 숫자 범위 (동 층수, 계약 주 수 등). 두 끝을 모두 모르면 범위도 모름(None)이고, 한 끝만 모르면 그 끝만 null 이다."""
    if lowest is None and highest is None:
        return None
    return NumberRange(lowest=lowest, highest=highest)


def listing_field_names() -> frozenset[str]:
    """출력에 나올 수 있는 매물 필드 이름 (`Listing` 과 소스별 하위 모델·상세, `floor_number`). `--fields` 를 검증한다.

    하위 모델은 소스 모듈을 불러온 뒤에야 보이므로 명령을 모두 등록한 뒤(옵션을 읽을 때) 부른다.
    """
    names = {'floor_number'}
    models: list[type[Listing]] = [Listing]
    while models:
        model = models.pop()
        names.update(name for name, field in model.model_fields.items() if not field.exclude)
        models.extend(model.__subclasses__())
    return frozenset(names)


def listing_as(model: type[ListingT], listing: Listing, **extra: Any) -> ListingT:
    """`listing` 을 필드를 더한 하위 모델(역 도보 시간·통근 시간·순위·상세·건물 용도)로 옮긴다.

    `model_dump()` 는 출력에서 빼는 필드(`lat`·`lng` 처럼 `exclude=True`)를 버리므로 쓰지 않고 필드 값을 그대로 옮긴다.
    """
    return model(**{name: getattr(listing, name) for name in type(listing).model_fields}, **extra)
