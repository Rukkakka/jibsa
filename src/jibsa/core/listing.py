import math
import re
from collections.abc import (
    Callable,
    Container,
    Sequence,
)
from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
)
from functools import wraps

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from jibsa.core.dates import (
    add_unread_date,
    iso_date,
    reset_unread_dates,
    unread_date_notes,
)
from jibsa.core.notes import (
    NULL_ITEMS_PHRASE,
    null_items_total_note,
)
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
    overload,
)


P = ParamSpec('P')
R = TypeVar('R')
SQUARE_METERS_PER_PYEONG: float = 3.305785
# 입주 가능일 문구 끝의 괄호 설명 ('2026.10.15 이후 입주 가능 (입주협의)')
MOVE_IN_PAREN_PATTERN: re.Pattern[str] = re.compile(r'^(.*?)\s*\(([^()]*)\)$')
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

# 소스 이름 -> 안내에 쓰는 사이트 이름. 응답에서 뺀 빈 항목의 공통 안내(`null_items_total_note`)와 못 읽은 날짜 안내(`unread_date_notes`)에 쓴다
SITE_NAMES: dict[str, str] = {
    'zigbang': '직방',
    'naver': '네이버',
    'daangn': '당근',
    'dabang': '다방',
}


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


def by_distance(listing: 'Listing') -> tuple[bool, float]:
    """가까운 순 정렬 키. 거리를 모르는 매물은 가장 가깝다고 내보내지 않도록 맨 뒤로 보낸다."""
    return listing.distance_km is None, listing.distance_km or 0


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
