"""두 기능 이상이 쓰는 다방 결과 모델·변환·상수 (매물 목록은 search listings 와 단지 매물이 같이 쓴다)."""
import re
from math import (
    ceil,
    isfinite,
)

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    Listing,
    Source,
    TradeType,
    m2_to_pyeong,
    note,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    ALL_ROOM_COUNTS,
    ALL_ROOM_FLOORS,
    ALL_ROOM_TYPES,
    UNBOUNDED_MAX,
    DabangAptFiltersModel,
    DabangBboxModel,
    DabangCategory,
    DabangComplexV5RequestParameterModel,
    DabangHouseVillaFiltersModel,
    DabangListFilters,
    DabangOfficetelFiltersModel,
    DabangOneTwoFiltersModel,
    DabangPointModel,
    DabangRangeModel,
    DabangRoomCount,
    DabangRoomFloor,
    DabangRoomType,
    DabangSearchType,
    DabangSellingType,
)
from jibsa.providers.dabang.api.response.common import (
    DabangComplexResultModel,
    DabangRoomItemModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


SOURCE: Source = 'dabang'
# 다방 목록 한 쪽 크기. 서버가 정하고 `limit` 을 보내도 무시한다 (2026-10-25 실측: limit=100 에도 24건)
PAGE_SIZE: int = 24
DEFAULT_LIST_LIMIT: int = 24
MAX_LIST_LIMIT: int = 120
# --limit 최대값을 채우는 쪽 수 (120 = 5쪽). 목록마다 쪽 수 상한으로 쓴다
MAX_LIST_PAGES: int = ceil(MAX_LIST_LIMIT / PAGE_SIZE)
MANWON_PER_EOK: int = 10000
# 매물·단지 주소. 서버가 지도 화면으로 넘겨 준다 (2026-10-25 실측: /room/{id} → 302 /map/onetwo?…detail_type=room,
# /complex/{id} → 302 /map/apt?…detail_type=complex). 상세의 짧은 주소(redirect.dabangapp.com)도 /room/{id} 로 넘긴다
LISTING_URL: str = 'https://www.dabangapp.com/room/{room_id}'
COMPLEX_URL: str = 'https://www.dabangapp.com/complex/{complex_id}'
LISTING_ID_PATTERN: re.Pattern[str] = re.compile(r'^[0-9a-f]{24}$')
# 매물번호는 0 으로 시작하지 않는다. '00000' 같은 값은 요청 모델(seq > 0)의 영어 메시지 대신 CLI 의 형식 오류로 막는다
LISTING_NUMBER_PATTERN: re.Pattern[str] = re.compile(r'^[1-9]\d{4,9}$')
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(r'^[0-9a-f]{28}$')
# 다방 매물 종류 표시 뒤에 붙는 단기임대 표시 ('오피스텔 • 단기'). 단기임대는 따로 있는 거래가 아니라 월세 매물이 1개월 이상
# 단기 계약도 받는다는 뜻이다 (상세 short_lease_str '1개월(이상 협의가능)', 보증금 1000·월세 90 같은 보통 월세에도 붙는다,
# 2026-10-25 실측: 역삼동 원룸 월세 423건 중 275건)
SHORT_LEASE_MARK: str = '단기'

# 명령의 매물 유형 → 다방 목록 유형
ListingKind = Literal['room', 'villa', 'officetel', 'apt']
CATEGORY_BY_KIND: dict[ListingKind, DabangCategory] = {
    'room': 'one-two',
    'villa': 'house-villa',
    'officetel': 'officetel',
    'apt': 'apt',
}
KIND_LABELS: dict[ListingKind, str] = {'room': '원룸·투룸', 'villa': '주택·빌라', 'officetel': '오피스텔', 'apt': '아파트'}
TRADE_BY_PRICE_TYPE_NAME: dict[str, TradeType] = {'월세': '월세', '전세': '전세', '매매': '매매'}
SELLING_TYPE_BY_TRADE: dict[str, DabangSellingType] = {'월세': 'MONTHLY_RENT', '전세': 'LEASE', '매매': 'SELL'}
# 원룸·투룸 목록은 매매를 받지 않는다 (매매만 보내면 무시하고 월세를 준다, 2026-10-25 실측)
TRADE_TYPES_BY_KIND: dict[ListingKind, tuple[TradeType, ...]] = {
    'room': ('월세', '전세'),
    'villa': ('월세', '전세', '매매'),
    'officetel': ('월세', '전세', '매매'),
    'apt': ('월세', '전세', '매매'),
}
FLOOR_FILTER_BY_LABEL: dict[str, DabangRoomFloor] = {
    '1층': 'GROUND_FIRST',
    '2층이상': 'GROUND_SECOND_OVER',
    '반지하': 'SEMI_BASEMENT',
    '옥탑': 'ROOFTOP',
}
ROOM_TYPE_FILTER_BY_LABEL: dict[str, DabangRoomType] = {'원룸': 'ONE_ROOM', '투룸': 'TWO_ROOM'}
# 방 개수. FOUR_ROOM 은 웹 필터의 '4개 이상' 이다
ROOM_COUNT_FILTER_BY_LABEL: dict[str, DabangRoomCount] = {
    '원룸': 'ONE_ROOM',
    '투룸': 'TWO_ROOM',
    '쓰리룸': 'THREE_ROOM',
    '포룸이상': 'FOUR_ROOM',
}
ROOM_LABELS_BY_KIND: dict[ListingKind, tuple[str, ...]] = {
    'room': tuple(ROOM_TYPE_FILTER_BY_LABEL),
    'villa': tuple(ROOM_COUNT_FILTER_BY_LABEL),
    'officetel': tuple(ROOM_COUNT_FILTER_BY_LABEL),
    'apt': tuple(ROOM_COUNT_FILTER_BY_LABEL),
}
# 기타 조건 라벨 → 필터 필드. 유형마다 받는 필드가 다르다 (filter-init 청크, 2026-10-25)
CONDITION_FIELD_BY_LABEL: dict[str, str] = {
    '주차': 'can_parking',
    '엘리베이터': 'has_elevator',
    '단기임대': 'is_short_lease',
    '분리형': 'is_division',
    '복층': 'is_duplex',
}
CONDITIONS_BY_KIND: dict[ListingKind, tuple[str, ...]] = {
    'room': ('주차', '엘리베이터', '단기임대', '분리형', '복층'),
    'villa': ('주차', '엘리베이터', '단기임대'),
    'officetel': ('주차', '엘리베이터', '단기임대'),
    'apt': ('단기임대',),
}
# 단지가 있는 매물 유형. 상세 유형은 '오피스텔(분리형)' 처럼 뒤에 구조를 붙여 와서 앞부분으로 본다
COMPLEX_PROPERTY_TYPES: tuple[str, ...] = ('오피스텔', '아파트')
# 목록 면적이 전용이 아니라 공급면적인 매물 유형 (`room_item_to_listing`)
APARTMENT_TYPE: str = '아파트'
SchoolLevel = Literal['초등학교', '중학교', '고등학교']
SCHOOL_LEVELS: tuple[SchoolLevel, ...] = ('초등학교', '중학교', '고등학교')
# 웹 지도 확대 수준 (동 14, 역·대학 15, 지도 범위 16). 동·역 검색에도 필수라 보낸다 (빠지면 400 "줌은 필수값 입니다")
ZOOM_BY_SEARCH_TYPE: dict[DabangSearchType, int] = {'region': 14, 'subway': 15, 'univ': 15, 'bbox': 16}

# 가격 글자: '1000', '3억9000', '22억', '31억 3,000' (단지 목록은 띄어쓰기·쉼표), '61.1억'
MANWON_TEXT_PATTERN: re.Pattern[str] = re.compile(r'^(?:(\d+(?:\.\d+)?)억)?(\d+(?:\.\d+)?)?$')
FLOOR_NUMBER_PATTERN: re.Pattern[str] = re.compile(r'^(지하)?(\d+)층$')
# 수 글자: '1,074개', '60위', '24명', '대학교 163명'
COUNT_TEXT_PATTERN: re.Pattern[str] = re.compile(r'\d[\d,]*')
# 세대수 글자: '아파트 · 48년차 · 615세대' (단지 목록), '594세대' (분양 목록), '11년차ㆍ3636세대ㆍ…' (거래 순위)
HOUSEHOLDS_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d[\d,]*)\s*세대')
# 연차 글자: 세대수와 같은 칸에 온다 ('48년차', '11년차')
YEARS_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d+)\s*년차')
# 다방 층 글자 → jibsa 표기 (normalize_floor 가 맞추는 직방 표기). 다방은 반지하를 '반지층' 으로 쓴다 (2026-10-25 역삼동 목록)
FLOOR_LABELS: dict[str, str] = {'반지층': '반지하'}


def listing_url(room_id: str) -> str:
    return LISTING_URL.format(room_id=room_id)


def complex_url(complex_id: str) -> str:
    return COMPLEX_URL.format(complex_id=complex_id)


def bbox_of(south: float, north: float, west: float, east: float) -> DabangBboxModel:
    """(남, 북, 서, 동) 을 다방 지도 범위로."""
    return DabangBboxModel(sw=DabangPointModel(lat=south, lng=west), ne=DabangPointModel(lat=north, lng=east))


def manwon_from_text(text: str | None) -> float | None:
    """다방 금액 글자를 만원 숫자로 바꾼다 ('3억9000' → 39000, '22억' → 220000, '31억 3,000' → 313000, '1000' → 1000).

    억 앞뒤의 띄어쓰기와 천 단위 쉼표는 무시한다. 금액 꼴이 아니면('준비중', 빈 글자) None.
    """
    if text is None:
        return None
    compact = text.replace(',', '').replace(' ', '')
    match = MANWON_TEXT_PATTERN.fullmatch(compact)
    if not compact or match is None or (match.group(1) is None and match.group(2) is None):
        return None
    value = float(match.group(1) or 0) * MANWON_PER_EOK + float(match.group(2) or 0)
    return round(value, 1) if isfinite(value) else None


def count_of(text: str | None) -> int | None:
    """'1,074개'·'60위'·'대학교 163명' 같은 글자의 (첫) 숫자. 없으면 None."""
    match = COUNT_TEXT_PATTERN.search(text or '')
    return int(match.group().replace(',', '')) if match else None


def household_count(text: str | None) -> int | None:
    """세대수 글자('615세대', '1,234 세대')의 세대수. 단지 목록·분양 목록·거래 순위가 함께 쓴다. 없으면 None."""
    match = HOUSEHOLDS_TEXT_PATTERN.search(text or '')
    return int(match.group(1).replace(',', '')) if match else None


def building_years(text: str | None) -> int | None:
    """연차 글자('48년차')의 연차. 단지 목록·거래 순위가 함께 쓴다. 없으면 None."""
    match = YEARS_TEXT_PATTERN.search(text or '')
    return int(match.group(1)) if match else None


def listing_prices(trade_type: TradeType, price_title: str | None) -> dict[str, float] | None:
    """목록 가격 글자를 거래 유형에 맞는 금액 필드로 바꾼다 (월세 '1000/63' → 보증금 1000·월세 63). 읽지 못하면 None."""
    parts = (price_title or '').split('/')
    values = [manwon_from_text(part) for part in parts]
    if any(value is None for value in values):
        return None
    if trade_type == '월세' and len(values) == 2:
        return {'deposit_manwon': values[0] or 0, 'rent_manwon': values[1] or 0}
    if trade_type == '전세' and len(values) == 1:
        return {'deposit_manwon': values[0] or 0}
    if trade_type == '매매' and len(values) == 1:
        return {'price_manwon': values[0] or 0}
    return None


def floor_label(text: str | None) -> str | None:
    """다방 층 글자를 jibsa 표기로 ('5층' → '5', '지하1층' → '지하1', '고층'·'반지하'·'옥탑' 은 그대로)."""
    if text is None or not text.strip():
        return None
    value = text.strip()
    match = FLOOR_NUMBER_PATTERN.fullmatch(value)
    if match is not None:
        return f"{'지하' if match.group(1) else ''}{int(match.group(2))}"
    return FLOOR_LABELS.get(value, value)


def parse_room_desc(desc: str | None) -> tuple[str | None, float | None, float | None]:
    """목록 설명 '5층, 19.83m², 관리비 7만' 을 (층, 면적 ㎡, 관리비 만원) 으로 나눈다. 없는 값은 None (모름).

    '관리비 없음' 은 0 이다 (상세도 관리비 없음으로 준다, 2026-10-25 실측). 면적은 원룸·빌라·오피스텔이면 상세의
    전용면적(`room_size`), 아파트면 공급면적(`provision_size`)이다 (`room_item_to_listing`).
    """
    floor: str | None = None
    area: float | None = None
    manage: float | None = None
    for token in (part.strip() for part in (desc or '').split(',')):
        if token.endswith(('m²', '㎡')):
            try:
                area = float(token.rstrip('m²㎡').strip())
            except ValueError:
                area = None
        elif token.startswith('관리비'):
            amount = token.removeprefix('관리비').strip()
            manage = 0.0 if amount in ('없음', '0') else manwon_from_text(amount.removesuffix('만'))
        elif token.endswith('층') or token in ('반지하', '옥탑', '옥탑방'):
            floor = floor_label(token)
    return floor, area, manage


class DabangListing(Listing):
    """다방 매물 (목록). 가격·층·면적·관리비는 다방 목록 글자를 읽은 값이다.

    목록의 주소는 동 이름뿐이다 (찾은 동의 매물만 시·구까지). 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는
    표시라 `trade_type` 은 '월세' 이고 `short_lease` 로 알린다. 아파트 면적은 공급면적이라 `supply_area_m2` 에 둔다.
    """

    listing_number: Annotated[
        int | None,
        Field(description='다방 화면의 매물번호 (listing 에 id 대신 줄 수 있다)')
    ] = None
    short_lease: Annotated[
        bool,
        Field(description='단기임대(1개월 이상) 계약도 받는 월세 매물. 보증금이 월세 한두 달치(예 95/95)면 단기 계약 가격일 수 있다')
    ] = False
    complex_name: Annotated[
        str | None,
        Field(description='단지·건물 이름 (오피스텔·아파트)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 다방 목록은 아파트 면적을 공급면적으로만 줘서 아파트에만 있고 area_m2 는 null 이다 (전용은 listing)')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.trade_type != '월세':
            fields = fields | {'short_lease'}
        if self.complex_name is None and not is_complex_type(self.property_type):
            fields = fields | {'complex_name'}
        if self.supply_area_m2 is None and not self.property_type.startswith(APARTMENT_TYPE):
            fields = fields | {'supply_area_m2'}
        return fields


def is_complex_type(property_type: str) -> bool:
    """단지가 있는 유형인지 ('오피스텔', '오피스텔(분리형)', '아파트')."""
    return property_type.startswith(COMPLEX_PROPERTY_TYPES)


def property_label(room_type_name: str | None, kind: ListingKind) -> tuple[str, bool]:
    """목록 매물 종류 표시를 (매물 유형, 단기임대 표시) 로 나눈다 ('오피스텔 • 단기' → ('오피스텔', True)).

    주택·빌라 목록은 방 개수('원룸', '투룸')로 표시해 건물 종류를 알 수 없어 '빌라' 로 둔다.
    """
    base, _, mark = (room_type_name or '').partition('•')
    short = SHORT_LEASE_MARK in mark
    if kind == 'villa':
        return '빌라', short
    return base.strip() or KIND_LABELS[kind], short


def room_type_of(room_type_name: str | None) -> str | None:
    """방 구조는 다방이 투룸·쓰리룸으로 밝힐 때만 준다. '원룸' 은 오픈형·분리형을 알 수 없어 None (모름).

    상세는 구조를 괄호로 붙여 준다 ('투룸(복층)', 2026-10-25 실측: 목록에서 '투룸' 인 매물 6acdf475f0bb4161a878293c).
    """
    base = (room_type_name or '').partition('•')[0].partition('(')[0].strip()
    return base if base in ('투룸', '쓰리룸') else None


def room_item_to_listing(
    item: DabangRoomItemModel,
    kind: ListingKind,
    *,
    center: tuple[float, float] | None = None,
    addresses: dict[int, str] | None = None,
) -> DabangListing | None:
    """목록 매물 한 칸을 `DabangListing` 으로. 거래 유형·가격을 읽지 못하면 None (부르는 쪽이 빼고 알린다).

    Args:
        center: 거리를 잴 검색 중심 (역·좌표 검색). 없으면 거리 없음.
        addresses: 동 번호 → 시·도부터 이은 동 이름. 찾은 동의 매물만 시·구까지 붙인다.
    """
    trade_type = TRADE_BY_PRICE_TYPE_NAME.get(item.price_type_name or '')
    if trade_type is None:
        return None
    prices = listing_prices(trade_type, item.price_title)
    if prices is None:
        return None
    property_type, short = property_label(item.room_type_name, kind)
    floor, area, manage = parse_room_desc(item.room_desc)
    # 아파트 칸의 면적은 전용이 아니라 공급면적이다. 아파트 목록·단지 매물·인기 매물과 원룸·투룸 목록에 섞인 아파트 모두
    # 같다 (2026-10-26 실측: 세연파크뷰 목록 94.53㎡ = 상세 공급, 전용 83.58㎡ / 원룸·투룸 목록의 대치더블유타워(도시형)
    # 47.27㎡ = 공급, 전용 33.78㎡). 오피스텔·빌라·원룸은 전용과 같다 (역삼SK허브블루 35.34㎡ = 19A 전용)
    apartment = kind == 'apt' or property_type.startswith(APARTMENT_TYPE)
    location = item.random_location
    distance = None
    if center is not None and location is not None:
        distance = round(haversine_km(center[0], center[1], location.lat, location.lng), 2)
    address = (addresses or {}).get(item.gid or 0) or item.dong_name
    return DabangListing(
        source=SOURCE,
        id=item.id,
        url=listing_url(item.id),
        trade_type=trade_type,
        property_type=property_type,
        room_type=room_type_of(item.room_type_name),
        title=item.room_title,
        manage_cost_manwon=manage,
        area_m2=None if apartment else area,
        area_pyeong=None if apartment else m2_to_pyeong(area),
        supply_area_m2=area if apartment else None,
        floor=floor,
        address=address,
        lat=location.lat if location else None,
        lng=location.lng if location else None,
        distance_km=distance,
        listing_number=item.seq,
        short_lease=short and trade_type == '월세',
        complex_name=item.complex_name,
        **prices,
    )


class DabangListingConditions(RequestModel):
    """다방 매물 검색 조건 (한국어 라벨·만원). 모두 다방 서버가 거른다."""

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형 (비면 그 유형의 전체)')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(ge=0, description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(ge=0, description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(ge=0, description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(ge=0, description='매매가 상한 (만원)')
    ] = None
    rent_includes_manage_cost: Annotated[
        bool,
        Field(description='월세 범위를 월세 + 관리비로 볼지')
    ] = False
    area_pyeong_min: Annotated[
        int | None,
        Field(ge=0, description='방 크기 하한 (평)')
    ] = None
    area_pyeong_max: Annotated[
        int | None,
        Field(ge=0, description='방 크기 상한 (평)')
    ] = None
    built_within_years: Annotated[
        int | None,
        Field(ge=0, description='사용승인 뒤 이 햇수 이내')
    ] = None
    floors: Annotated[
        list[str],
        Field(description='층 라벨 (1층, 2층이상, 반지하, 옥탑)')
    ] = []
    rooms: Annotated[
        list[str],
        Field(description='방 개수 라벨 (원룸, 투룸, 쓰리룸, 포룸이상)')
    ] = []
    conditions: Annotated[
        list[str],
        Field(description='기타 조건 라벨 (주차, 엘리베이터, 단기임대, 분리형, 복층)')
    ] = []
    households_min: Annotated[
        int | None,
        Field(ge=0, description='세대수 하한 (아파트)')
    ] = None
    households_max: Annotated[
        int | None,
        Field(ge=0, description='세대수 상한 (아파트)')
    ] = None


def range_of(minimum: int | None, maximum: int | None) -> DabangRangeModel:
    """다방은 범위 값을 999999 까지만 받는다 (넘으면 400 '최대값은 999999 이하로 입력해주세요', 2026-10-25 실측).
    그보다 큰 상한은 999999 로 줄여 보낸다 (압구정·청담·한남동 아파트 매매도 98억까지라 빠지는 매물을 보지 못했다).
    큰 하한은 CLI 가 막는다.
    """
    return DabangRangeModel(min=minimum or 0, max=UNBOUNDED_MAX if maximum is None else min(maximum, UNBOUNDED_MAX))


def filters_of(kind: ListingKind, conditions: DabangListingConditions) -> DabangListFilters:
    """검색 조건을 다방 유형 필터로 바꾼다. 주지 않은 항목은 '전체' 값이다 (다방은 항목이 빠지면 400).

    CLI 가 유형마다 받는 조건만 열어 두므로, 그 유형에 없는 조건은 여기 오지 않는다.
    """
    category = CATEGORY_BY_KIND[kind]
    flags = {CONDITION_FIELD_BY_LABEL[label]: True for label in conditions.conditions if label in CONDITIONS_BY_KIND[kind]}
    common: dict[str, Any] = {
        'deposit_range': range_of(conditions.deposit_min, conditions.deposit_max),
        'price_range': range_of(conditions.rent_min, conditions.rent_max),
        'is_include_maintenance': conditions.rent_includes_manage_cost,
        'pyeong_range': range_of(conditions.area_pyeong_min, conditions.area_pyeong_max),
        'use_approval_date_range': range_of(None, conditions.built_within_years),
        'is_short_lease': flags.pop('is_short_lease', False),
    }
    selling = [SELLING_TYPE_BY_TRADE[trade] for trade in conditions.trade_types or TRADE_TYPES_BY_KIND[kind]]
    floors = [FLOOR_FILTER_BY_LABEL[label] for label in conditions.floors] or list(ALL_ROOM_FLOORS)
    if category == 'one-two':
        return DabangOneTwoFiltersModel(
            **common,
            **flags,
            selling_type_list=[code for code in selling if code != 'SELL'],
            room_floor_list=floors,
            room_type_list=[ROOM_TYPE_FILTER_BY_LABEL[label] for label in conditions.rooms] or list(ALL_ROOM_TYPES),
        )
    sale: dict[str, Any] = {
        **common,
        **flags,
        'selling_type_list': selling,
        'trade_range': range_of(conditions.price_min, conditions.price_max),
        'room_count_list': [ROOM_COUNT_FILTER_BY_LABEL[label] for label in conditions.rooms] or list(ALL_ROOM_COUNTS),
    }
    if category == 'house-villa':
        return DabangHouseVillaFiltersModel(**sale, room_floor_list=floors)
    if category == 'officetel':
        return DabangOfficetelFiltersModel(**sale)
    return DabangAptFiltersModel(**sale, household_num_range=range_of(conditions.households_min, conditions.households_max))


class DabangPlace(BaseModel):
    """찾은 위치 (동·역·대학·좌표). 동 번호·코드·역 번호는 다방 요청에만 쓰고 출력하지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    kind: Annotated[
        Literal['dong', 'station', 'university', 'point'],
        Field(description='위치 종류')
    ]
    name: Annotated[
        str,
        Field(description='이름')
    ]
    # 역·대학·좌표도 어느 동 안에 있어 주소·법정동코드는 해당 없음(키 삭제)이 아니라 다방이 주지 않은 모름(null)이다.
    # 네이버(역은 null)·직방 역 검색의 region 과 같다
    address: Annotated[
        str | None,
        Field(description='시·도부터 이은 이름 (동). 역·대학·좌표는 다방이 주지 않아 null')
    ] = None
    lat: Annotated[
        float,
        Field(description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='중심 경도')
    ]
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리). 역·대학·좌표는 다방이 주지 않아 null')
    ] = None
    code: Annotated[
        str | None,
        Field(exclude=True, description='다방 동 코드 (법정동코드 앞 8자리)')
    ] = None
    gid: Annotated[
        int | None,
        Field(exclude=True, description='다방 동 번호')
    ] = None
    place_id: Annotated[
        int | None,
        Field(exclude=True, description='다방 역·대학 번호')
    ] = None
    radius_m: Annotated[
        int | None,
        Field(exclude=True, description='다방 역 검색 반경 (m)')
    ] = None


def middle_place(places: list[DabangPlace]) -> DabangPlace:
    """반경 검색의 중심. '○가' 동 여럿이면 이름을 이어 붙이고 동 중심들의 가운데로 한다. 첫 동 중심만 쓰면 '합쳐 찾았다' 고
    알리면서 뒤 동 쪽을 반경 밖으로 뺀다 (2026-10-26 실측: 성수동 --radius 0.5 가 성수동1가 중심 반경만 찾았다).
    """
    if len(places) == 1:
        return places[0]
    return places[0].model_copy(update={
        'name': '·'.join(place.name for place in places),
        'lat': sum(place.lat for place in places) / len(places),
        'lng': sum(place.lng for place in places) / len(places),
    })


def premium_note(count: int) -> list[str]:
    """목록과 함께 온 광고(중개사별 추천 매물)를 뺐다는 안내."""
    if count <= 0:
        return []
    return [note('제외', f'다방 광고 칸(중개사 추천 매물) {count}건은 넣지 않았습니다')]


def is_missing_id(exc: HTTPStatusError, *, in_path: bool = True) -> bool:
    """사용자 ID 로 묻는 요청의 '없는 ID' 응답인지: 400·404, 그리고 ID 가 경로에 들어가는 요청이면 본문이 빈 403.

    다방은 없는 주소에 404 대신 403 빈 응답을 준다. 요청 제한(429)과 다르다 (2026-10-25 실측: 아무 경로나
    `/api/v5/room-list/category/one-two/nothing-here` 를 넣어도 403 빈 본문). 클라이언트(`raise_for_status`) 한 곳에서 바꾸지
    않고 사용자 ID 로 묻는 요청만 부른다.

    ID 가 쿼리로 가는 요청(`in_path=False`)은 없는 ID 에 403 을 주지 않는다 (2026-10-27 실측: 분양 `detail2?id=` 는 400,
    `transit/near`·`real-price/house/history` 는 빈 결과, `region?code=99999` 는 다른 지역). 그 403 은 다방 주소가 바뀐
    것이라 UPSTREAM_ERROR 로 두어야 '없는 ID' 로 오해하지 않고 매일 감시도 고장으로 본다. 본문이 있는 403 은 차단 페이지일 수
    있어 어느 쪽이든 없는 ID 로 보지 않는다 (부르는 쪽이 다시 던져 UPSTREAM_ERROR 가 된다).
    """
    status = exc.response.status_code
    return status in (400, 404) or (in_path and status == 403 and not exc.response.content.strip())


def complex_not_found(complex_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f'다방 단지를 찾지 못했습니다: {complex_id}',
        hint='jibsa dabang search locations <단지 이름> 이나 search complexes 결과의 complex_id 를 그대로 주세요',
    )


def fetch_complex(client: DabangClient, complex_id: str) -> DabangComplexResultModel:
    """단지 상세 (요청 1회, 단지 정보·평형·대표 평형). 없는 단지 ID 는 NOT_FOUND (단지 정보·단지 매물·실거래가 같이 쓴다)."""
    try:
        result = client.run_request_complex_v5(DabangComplexV5RequestParameterModel(complex_id=complex_id)).result
    except HTTPStatusError as exc:
        if is_missing_id(exc):
            raise complex_not_found(complex_id) from None
        raise
    if result is None:
        raise complex_not_found(complex_id)
    return result
