"""단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from collections.abc import Callable

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
    RegionNotFoundError,
)
from jibsa.core.geo import (
    geohashes_covering,
    haversine_km,
)
from jibsa.core.http import error_body
from jibsa.core.korean import is_ri_code
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    format_manwon,
    join_address,
    limit_notes,
    listing_as,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    note,
    won_to_manwon_exact,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.stay import (
    STAY_SEARCH_MAX_DAYS,
    STAY_SEARCH_MIN_DAYS,
    ZigbangGuestItemsByIdsRequestParameterModel,
    ZigbangGuestItemsMarkersRequestParameterModel,
    ZigbangGuestItemsPriceCalculationRequestPayloadModel,
    ZigbangGuestItemsRequestParameterModel,
    ZigbangGuestItemsSearchRequestParameterModel,
    ZigbangStayBuildingType,
    ZigbangStayDiscountType,
    ZigbangStayFloorType,
    ZigbangStayOption,
    ZigbangStaySearchSort,
    stay_days,
)
from jibsa.providers.zigbang.api.response.stay import (
    ZigbangGuestItemsPriceCalculationResponseModel,
    ZigbangGuestItemsResponseModel,
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
    ZigbangStayMarkerModel,
)
from jibsa.providers.zigbang.service.common import (
    MAX_LIST_LIMIT,
    ZigbangBoundary,
    ZigbangRegion,
    drop_unused_scope,
    sent_or_none,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.listing import DETAILS_MAX
from jibsa.providers.zigbang.service.region import (
    outside_boundary,
    scope_geohashes,
)

from typing import (
    Annotated,
    Any,
    Literal,
    TypeVar,
)


STAY_BUILDING_TYPE_LABELS: dict[str, str] = {
    'OFFICETEL': '오피스텔',
    'APARTMENT': '아파트',
    'VILLA': '빌라',
    'ONEROOM': '원룸',
    'HOUSE': '주택',
    'COMMERCIAL_HOUSE': '상가주택',
    'GOSIWON': '고시원',
    'PENSION': '펜션',
    'SHAREHOUSE': '셰어하우스',
    'GUESTHOUSE': '게스트하우스',
    'RESIDENTIAL_HOTEL': '레지던스',
}
STAY_BUILDING_TYPE_BY_LABEL: dict[str, ZigbangStayBuildingType] = {
    label: code for code, label in STAY_BUILDING_TYPE_LABELS.items()  # type: ignore[misc]
}
STAY_OPTION_LABELS: dict[str, str] = {
    'AIR_CONDITIONER': '에어컨',
    'BED': '침대',
    'GAS_RANGE': '가스레인지',
    'INDUCTION': '인덕션',
    'REFRIGERATOR': '냉장고',
    'SINK': '싱크대',
    'TV': 'TV',
    'WASHING_MACHINE': '세탁기',
    'WIFI': '와이파이',
    'AIR_PURIFIER': '공기청정기',
    'WATER_PURIFIER': '정수기',
    'CLOSET': '옷장',
    'COFFEE_MACHINE': '커피머신',
    'DESK': '책상',
    'DINING_TABLE': '식탁',
    'DISHWASHER': '식기세척기',
    'DRYER': '건조기',
    'ELECTRIC_KETTLE': '전기포트',
    'MICROWAVE': '전자레인지',
    'RICE_COOKER': '전기밥솥',
    'SOFA': '소파',
    'TOASTER': '토스터',
    'VANITY': '화장대',
    'BATHTUB': '욕조',
    'BIDET': '비데',
    'CABLE_TV': '케이블TV',
    'CCTV': 'CCTV',
    'DOOR_LOCK': '도어락',
    'DRYING_RACK': '빨래건조대',
    'MANAGEMENT_OFFICE': '관리사무소',
    'OTT': 'OTT',
    'VACUUM_CLEANER': '청소기',
    'BALCONY': '발코니',
}
STAY_OPTION_BY_LABEL: dict[str, ZigbangStayOption] = {
    label: code for code, label in STAY_OPTION_LABELS.items()  # type: ignore[misc]
}
STAY_FLOOR_TYPE_BY_LABEL: dict[str, ZigbangStayFloorType] = {
    '지하': 'BASEMENT',
    '1층': 'FIRST',
    '옥탑': 'ROOFTOP',
}
STAY_DISCOUNT_TYPE_BY_LABEL: dict[str, ZigbangStayDiscountType] = {
    '장기계약': 'LONG_TERM',
    '즉시': 'INSTANT',
}
STAY_REFUND_POLICY_LABELS: dict[str, str] = {
    'FLEXIBLE': '유연',
    'STANDARD': '보통',
    'STRICT': '엄격',
}
STAY_GEOHASH_PRECISION: int = 5
# 결과가 limit 보다 많을 때 좁히라고 권할 조건. 주 단위 단기임대에는 거래 유형·매물 유형 옵션이 없다
STAY_NARROW: str = '방 종류·가격·날짜 조건'
STAY_BY_IDS_BATCH_SIZE: int = 50
# 웹 정렬 넷과 같다: 추천순(기본), 낮은 가격순, 최근 등록순, 역 가까운 순. 역 가까운 순은 웹도 지하철역 검색에서만 고를 수
# 있다 (2026-11-15 웹)
StaySort = Literal['recommended', 'price', 'newest', 'distance']
STAY_SORTS: tuple[StaySort, ...] = ('recommended', 'price', 'newest', 'distance')
STAY_SERVER_SORTS: dict[StaySort, ZigbangStaySearchSort] = {
    'recommended': 'RECOMMENDED',
    'price': 'PRICE_ASC',
    'newest': 'NEWEST',
    'distance': 'STATION_DISTANCE_ASC',
}
STAY_AVAILABILITY_RADIUS_KM: float = 0.3
STAY_PRICE_ERRORS: dict[str, str] = {
    'MIN_CONTRACT_PERIOD': '계약 기간이 이 매물의 최소 계약 기간보다 짧습니다',
    'MAX_CONTRACT_PERIOD': '계약 기간이 이 매물의 최대 계약 기간보다 깁니다',
}
# limit_notes 의 '… 순으로' 앞말
STAY_SORT_ORDERS: dict[StaySort, str] = {
    'recommended': '직방 추천',
    'price': '주당 임대료·관리비 합계가 낮은',
    'newest': '최근 등록된',
    'distance': '역에서 가까운',
}
# 역 검색(type=subway)은 직방이 역에서 약 1km 안만 준다 (2026-11-15 실측: 강남역 71건, 가장 먼 것 0.979km)
STAY_SUBWAY_RADIUS_KM: float = 1.0


def stay_item_url(stay_id: int | str) -> str:
    """단기임대 매물 웹 페이지 주소. 로그인 없이 열린다."""
    return f'https://www.zigbang.com/stay/item/{stay_id}'


class ZigbangStayListing(Listing):
    """직방 단기임대 서비스 매물. 요금이 주 단위라 월세·월 관리비 대신 주당 금액을 준다."""

    weekly_rent_manwon: Annotated[
        float | None,
        Field(description='주당 임대료 (만원)')
    ] = None
    weekly_manage_cost_manwon: Annotated[
        float | None,
        Field(description='주당 관리비 (만원)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    discounts: Annotated[
        list[str] | None,
        Field(description="할인 조건 (예: '4주 이상 10% 할인')")
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 요금이 주 단위라 월세·월 관리비가 해당 없다
        return super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}


class ZigbangStayPeriodCost(BaseModel):
    """입주·퇴거일을 준 단기임대 상세의 기간 비용 (만원). 직방 요금 계산 그대로다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    check_in: Annotated[
        str,
        Field(description='입주일 (YYYY-MM-DD)')
    ]
    check_out: Annotated[
        str,
        Field(description='마지막으로 머무는 날 (YYYY-MM-DD). 직방은 이 날까지 이용일로 센다 (1주 = 11-02~11-08)')
    ]
    available: Annotated[
        bool | None,
        Field(description='그 기간에 예약이 비어 있는지. 같은 날짜로 지도 검색에 나오면 true. 좌표가 없거나 기간이 지도 검색이 받는 7~84일 밖이라 확인 못 하면 null')
    ] = None
    days: Annotated[
        int | None,
        Field(description='이용 일수 (입주일·마지막 날 포함)')
    ] = None
    weeks: Annotated[
        int | None,
        Field(description='이용 일수 중 온전한 주 수')
    ] = None
    remaining_days: Annotated[
        int | None,
        Field(description='주 단위로 떨어지지 않고 남는 일수. 0 이 아니면 그 일수만큼 일할 요금이 붙는다')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='기간 임대료 (만원, 할인 전)')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='기간 관리비 (만원)')
    ] = None
    cleaning_fee_manwon: Annotated[
        float | None,
        Field(description='청소비 (만원, 반려동물 청소비 포함)')
    ] = None
    discount_manwon: Annotated[
        float | None,
        Field(description='할인 합계 (만원, 프로모션 포함)')
    ] = None
    discounts: Annotated[
        list[str],
        Field(description='적용된 할인 (예: 장기계약 할인 5%)')
    ] = []
    service_fee_manwon: Annotated[
        float | None,
        Field(description='직방 이용료 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원, 퇴거 후 돌려받는다)')
    ] = None
    total_payment_manwon: Annotated[
        float | None,
        Field(description='내는 돈 총액 (만원). 돌려받는 보증금이 들어 있다')
    ] = None


class ZigbangStayPricedListing(ZigbangStayListing):
    """`--details` 로 기간 요금 계산을 1회 더 받아 기간 비용을 붙인 단기임대 매물."""

    period_cost: Annotated[
        ZigbangStayPeriodCost | None,
        Field(description='입주·퇴거일의 기간 비용 (직방 요금 계산). 앞 30건 밖이거나 직방이 계산을 거절했으면 null')
    ] = None


class ZigbangStayListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 단기임대 매물. 입주·퇴거일을 주면 `period_cost` 가 붙는다."""

    weekly_rent_manwon: Annotated[
        float | None,
        Field(description='주당 임대료 (만원)')
    ] = None
    weekly_manage_cost_manwon: Annotated[
        float | None,
        Field(description='주당 관리비 (만원). 관리비가 없으면 0')
    ] = None
    cleaning_fee_manwon: Annotated[
        float | None,
        Field(description='청소비 (만원). 무료면 0')
    ] = None
    discounts: Annotated[
        list[str] | None,
        Field(description='할인 조건')
    ] = None
    min_contract_weeks: Annotated[
        int | None,
        Field(description='최소 계약 주 수')
    ] = None
    max_contract_weeks: Annotated[
        int | None,
        Field(description='최대 계약 주 수')
    ] = None
    max_guests: Annotated[
        int | None,
        Field(description='최대 인원')
    ] = None
    duplex: Annotated[
        bool | None,
        Field(description='복층 여부')
    ] = None
    refund_policy: Annotated[
        str | None,
        Field(description='환불 정책 (유연, 보통, 엄격)')
    ] = None

    period_cost: Annotated[
        ZigbangStayPeriodCost | None,
        Field(description='입주·퇴거일을 줬을 때의 기간 비용과 예약 가능 여부')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}
        # 날짜를 주지 않은 조회에는 기간 비용이 해당 없다
        if self.period_cost is None:
            fields = fields | {'period_cost'}
        return fields


class ZigbangStaySearchResult(BaseModel):
    """직방 단기임대 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description=(
            '검색 반경 (km). 역 이름 검색은 직방이 역에서 약 1km 안을 주어 1. 동·구 등 지역 이름·동 경계·학교 이름으로 찾았으면 '
            '키가 없다'
        ))
    ] = None
    boundary: Annotated[
        str | None,
        Field(description=(
            '반경 대신 찾은 지역 이름. 동·구 이름이면 직방 단기임대 지역 검색 결과라 이웃 동 매물이 섞일 수 있고, 동 경계로 '
            '찾았으면 그 경계 안만이다. 반경으로 찾았으면 키가 없다'
        ))
    ] = None
    total: Annotated[
        int,
        Field(description='범위 안 조건에 맞는 매물 수 (limit 적용 전). 이름 검색이면 직방 검색 결과 수, 지도로 찾았으면 반경·동 경계 안 핀 수')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위 안에 요약을 받지 않은 매물이 더 있는지 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        # --details 의 period_cost 까지 내보낸다 (SerializeAsAny 가 없으면 ZigbangStayListing 필드만 나간다)
        list[SerializeAsAny[ZigbangStayListing]],
        Field(description='선택한 정렬 순서의 매물 (직방이 준 순서 또는 웹 지도 목록과 같은 순서)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unused_scope(handler(self))


def _discount_amount_text(amount_won: float | None) -> str | None:
    """할인 금액(원)을 'N만원' 으로 (반올림 없이 원 단위까지, 2,500원 → '0.25만원'). 금액이 없거나 0 이하면 None (할인이 아니다)."""
    if not amount_won or amount_won <= 0:
        return None
    return f'{format_manwon(won_to_manwon_exact(amount_won) or 0)}만원'


def stay_discount_label(discount: ZigbangStayDiscountModel, weekly_rent: int | None) -> str | None:
    """할인 조건 한 줄. 웹 상세(`DiscountDetailList`)가 그리지 않는 할인은 None.

    웹은 장기계약·즉시입주 할인만 그린다. 장기계약은 주 수·할인율·주당 임대료가 모두 0보다 클 때만 '{주}주 이상 {율}% 할인' 이고
    할인 금액은 쓰지 않는다. 즉시입주는 금액만 보고(0 이하면 None) 입주 시점 조건을 붙인다. 주 수·할인율·조건 일수가 null 이면
    웹처럼 0 으로 본다 (조건 일수 0 은 오늘). 웹은 할인의 `isActive` 를 보지 않아 꺼진 할인도 그리므로 여기서도 거르지 않는다
    (2026-11-15 번들 `DiscountDetailList`·목록 카드 `pickDiscountTextsForCard`. 실측 강남역·홍대입구역 할인 124건은 모두 true).
    """
    if discount.discount_type == 'LONG_TERM':
        weeks = discount.condition_weeks or 0
        rate = discount.discount_rate or 0
        if weeks <= 0 or rate <= 0 or (weekly_rent or 0) <= 0:
            return None
        return f'{weeks}주 이상 {rate:g}% 할인'
    if discount.discount_type == 'INSTANT':
        amount = _discount_amount_text(discount.discount_amount)
        if amount is None:
            # 리뷰 오탐 (2026-11-15): --discount 즉시 결과에서 즉시 할인이 빠지지 않는다. 웹이 금액 없는 즉시 할인을 숨기고,
            # 실측 강남역 --discount 즉시 의 즉시 할인 27건은 모두 금액(discountAmount)이 있었다 (할인율만 있는 것 0건)
            return None
        days = discount.condition_days or 0
        return f'오늘 입주 시 {amount} 할인' if days == 0 else f'오늘부터 {days}일 이내 입주 시 {amount} 할인'
    return None


def stay_discounts(discounts: list[ZigbangStayDiscountModel], weekly_rent: int | None) -> list[str]:
    return [label for label in (stay_discount_label(discount, weekly_rent) for discount in discounts) if label]


def stay_summary_to_listing(
    summary: ZigbangStayItemSummaryModel,
    distance_km: float | None = None,
) -> ZigbangStayListing:
    address = summary.address
    return ZigbangStayListing(
        source='zigbang',
        id=f'stay-{summary.id}',
        url=stay_item_url(summary.id),
        trade_type='단기임대',
        property_type=STAY_BUILDING_TYPE_LABELS.get(summary.building_type or '', summary.building_type or '단기임대'),
        title=summary.title,
        area_m2=summary.size_m2,
        area_pyeong=m2_to_pyeong(summary.size_m2),
        floor=summary.floor,
        address=join_address(
            address.local1 if address else None,
            address.local2 if address else None,
            address.local3 if address else None,
            address.local4 if address else None,
        ),
        lat=summary.lat,
        lng=summary.lng,
        distance_km=None if distance_km is None else round(distance_km, 2),
        registered_at=normalize_date(summary.reviewed_at),
        weekly_rent_manwon=won_to_manwon_exact(summary.weekly_rent),
        weekly_manage_cost_manwon=won_to_manwon_exact(summary.weekly_manage_cost),
        room_count=summary.room_count,
        bathroom_count=summary.bathroom_count,
        discounts=sent_or_none(summary, 'discounts', stay_discounts(summary.discounts, summary.weekly_rent)),
    )


def check_stay_sort(sort: str) -> StaySort:
    """단기임대 정렬 값을 검사해 돌려준다. CLI 는 지역을 찾기 전에 같은 검사로 막는다.

    Raises:
        JibsaError: `STAY_SORTS` 에 없는 값일 때 (INVALID_ARGUMENT).
    """
    if sort not in STAY_SORTS:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='지원하지 않는 단기임대 정렬입니다',
            hint=f"--sort {', '.join(STAY_SORTS)} 중 하나를 주세요",
        )
    return sort


def stay_distance_sort_error() -> JibsaError:
    """역 가까운 순(`distance`)을 역 이름 검색이 아닌 곳에 줬을 때의 에러. CLI 는 좌표·`--radius` 와 함께 준 것을 지역을 찾기
    전에, 서비스는 찾은 곳이 역이 아닌 것을 매물을 받기 전에 같은 에러로 막는다."""
    return JibsaError(
        code='INVALID_ARGUMENT',
        message='역 가까운 순(--sort distance)은 --radius 없이 역 이름으로 찾을 때만 됩니다',
        hint='--sort recommended·price·newest 중 하나를 쓰거나 --radius 없이 역 이름으로 검색하세요',
    )


class ZigbangStayConditions(RequestModel):
    """단기임대 매물 조건 (search listings stay). 주당 요금은 만원, 면적은 ㎡. 라벨은 `stay_filter_of` 가 서버 코드로 바꾼다."""

    weekly_price_min: Annotated[
        int | None,
        Field(description='주당 요금 하한 (만원)')
    ] = None
    weekly_price_max: Annotated[
        int | None,
        Field(description='주당 요금 상한 (만원)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    building_types: Annotated[
        list[str],
        Field(description='건물 유형 (STAY_BUILDING_TYPE_BY_LABEL)')
    ] = []
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    discounts: Annotated[
        list[str],
        Field(description='할인 (STAY_DISCOUNT_TYPE_BY_LABEL)')
    ] = []
    pet_allowed: Annotated[
        bool,
        Field(description='반려동물 가능만')
    ] = False
    duplex: Annotated[
        bool | None,
        Field(description='복층이면 True, 아니면 False, 상관없으면 None')
    ] = None
    options: Annotated[
        list[str],
        Field(description='옵션 (STAY_OPTION_BY_LABEL)')
    ] = []
    parking: Annotated[
        bool,
        Field(description='주차 가능만')
    ] = False
    elevator: Annotated[
        bool,
        Field(description='엘리베이터 있는 매물만')
    ] = False
    floors: Annotated[
        list[str],
        Field(description='층 (STAY_FLOOR_TYPE_BY_LABEL)')
    ] = []
    check_in: Annotated[
        str | None,
        Field(description='입주일 (YYYY-MM-DD)')
    ] = None
    check_out: Annotated[
        str | None,
        Field(description='퇴거일 (YYYY-MM-DD)')
    ] = None
    flexibility: Annotated[
        int | None,
        Field(description='입주일 앞뒤로 허용하는 날 수')
    ] = None


def stay_filter_of(conditions: ZigbangStayConditions) -> dict[str, Any]:
    """단기임대 조건을 지도 핀·검색 API 요청 필드로 바꾼다."""
    return dict(
        weekly_price_min=conditions.weekly_price_min,
        weekly_price_max=conditions.weekly_price_max,
        room_count=conditions.room_count,
        building_types=[STAY_BUILDING_TYPE_BY_LABEL[label] for label in conditions.building_types],
        size_min_m2=conditions.area_min_m2,
        size_max_m2=conditions.area_max_m2,
        discount_types=[STAY_DISCOUNT_TYPE_BY_LABEL[label] for label in conditions.discounts],
        pet_allowed=conditions.pet_allowed or None,
        is_duplex=conditions.duplex,
        options=[STAY_OPTION_BY_LABEL[label] for label in conditions.options],
        has_parking=conditions.parking or None,
        has_elevator=conditions.elevator or None,
        floor_types=[STAY_FLOOR_TYPE_BY_LABEL[label] for label in conditions.floors],
        check_in_date=conditions.check_in,
        check_out_date=conditions.check_out,
        flexibility=conditions.flexibility,
    )


def search_stay_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangStayConditions | None = None,
    sort: StaySort = 'recommended',
    radius_km: float = 1.0,
    limit: int = 20,
    boundary: ZigbangBoundary | None = None,
    use_search_api: bool = False,
    whole_address: bool = False,
) -> ZigbangStaySearchResult:
    """직방 단기임대를 웹 정렬(추천·낮은 가격·최근 등록·역 가까운 순)로 조회한다.

    직방 단기임대는 원룸·빌라의 '단기' 거래와 다른 별도 서비스(주 단위 계약, stay-apis)다.
    모든 조건(`conditions`)은 서버에서 거른다 (주당 요금은 만원). 라벨(오피스텔, 에어컨, 지하 ...)은 서버 코드로 바꿔 보낸다.
    두 경로 모두 받은 매물을 다시 거르거나 다시 세우지 않고, 고른 순서의 앞 `limit` 개만 요약(by-ids)을 받는다.

    - 검색 API (`use_search_api`: 역·학교·대학 이름, `whole_address` 인 동·구 이름): 웹 검색 결과 목록처럼 정렬을 서버에
      보내고(`guest/items/search`) 응답 ID 순서 그대로 낸다. 반경으로 자르지 않는다. 역은 직방이 역에서 약 1km 안을 주어
      `radius_km` 를 1 로 내고, 동·구는 동 경계가 아니라 이웃 동 매물이 섞여 와 `[범위]` 로 알린다. 리는 검색 API 가
      local3(그 위 읍·면)으로 찾아 `boundary` 를 읍·면 이름으로 낸다.
    - 지도 핀 (좌표·`--radius`·동 경계 `boundary`, 검색 API 가 받지 않는 지역): 반경(또는 동 경계)을 덮는 지도 칸의 핀 중
      범위 안만 남기고 웹 지도 목록처럼 핀 값으로 세운다 (`stay_marker_order`).

    역 가까운 순(`distance`)은 웹처럼 역 이름 검색(검색 API `type=subway`)에서만 된다.

    Raises:
        JibsaError: 역 이름 검색이 아닌데 `distance` 를 줬을 때 (INVALID_ARGUMENT, 매물 요청을 보내기 전에).
        RegionNotFoundError: 검색 API 가 지역을 찾지 못했을 때 (2026-10 의 세종의 동, `_stay_region_search`).
    """
    check_stay_sort(sort)
    if sort == 'distance' and not (use_search_api and region.search_type == 'subway'):
        # 직방 검색 API 는 역 검색이 아니면 400 STATION_SORT_REQUIRES_SUBWAY 를 주고, 웹 지도 목록도 역 기준점이 없으면
        # 추천순으로 바꾼다 (2026-11-15 실측·번들 `sortStayMarkers`)
        raise stay_distance_sort_error()
    conditions = conditions or ZigbangStayConditions()
    filters = stay_filter_of(conditions)
    context = _stay_search_context(region, sort, filters, whole_address) if use_search_api else None
    if context is not None:
        return _search_stay_by_search_api(client, region, context, conditions, sort=sort, limit=limit)
    return _search_stay_by_markers(
        client, region, filters, conditions, sort=sort, radius_km=radius_km, limit=limit, boundary=boundary,
    )


def _search_stay_by_search_api(
    client: ZigbangClient,
    region: ZigbangRegion,
    context: ZigbangGuestItemsSearchRequestParameterModel,
    conditions: ZigbangStayConditions,
    *,
    sort: StaySort,
    limit: int,
) -> ZigbangStaySearchResult:
    """검색 API 가 정렬해 준 ID 순서 그대로 앞 `limit` 개의 요약을 받는다. `total` 은 검색 ID 수다.

    by-ids 가 빼는 매물(그사이 내려간 매물)은 다시 채우지 않는다. 검색 ID 에는 위치가 없어 `distance_km` 는 요약 좌표로 잰다.
    """
    ids = list(dict.fromkeys(_stay_region_search(client, context, _searched_area(context) or region.name)))
    head = ids[:limit]
    listings = [
        stay_summary_to_listing(
            summary,
            None if summary.lat is None or summary.lng is None else haversine_km(region.lat, region.lng, summary.lat, summary.lng),
        )
        for summary in _stay_summaries(client, head, conditions)
    ]
    has_more = len(ids) > len(head)
    address_scope = context.type == 'address'
    notes = limit_notes(
        len(ids), len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f"{STAY_NARROW}·{'지역' if address_scope else '반경'}",
        order=STAY_SORT_ORDERS[sort], inspected=len(head), has_more=has_more,
    )
    area = None
    if address_scope:
        area = region.local3 if is_ri_code(region.legal_division_code) and region.local3 else region.name
        notes.append(note(
            '범위', f'직방 단기임대 지역 검색 결과라 {area} 밖 이웃 동 매물이 섞일 수 있습니다 (매물의 address 로 동을 확인하세요)',
        ))
    elif context.type != 'subway':
        notes.append(note(
            '범위', '직방 단기임대 학교 검색 결과라 범위는 직방이 정하고 반경으로 자르지 않았습니다. 반경으로 찾으려면 --radius 를 주세요',
        ))
    return ZigbangStaySearchResult(
        region=region,
        radius_km=STAY_SUBWAY_RADIUS_KM if context.type == 'subway' else None,
        boundary=area,
        total=len(ids),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )


def _search_stay_by_markers(
    client: ZigbangClient,
    region: ZigbangRegion,
    filters: dict[str, Any],
    conditions: ZigbangStayConditions,
    *,
    sort: StaySort,
    radius_km: float,
    limit: int,
    boundary: ZigbangBoundary | None,
) -> ZigbangStaySearchResult:
    """반경(또는 동 경계) 안 지도 핀을 웹 지도 목록 순서로 세워 앞 `limit` 개의 요약을 받는다. `total` 은 범위 안 핀 수다."""
    pins = _stay_pins(client, region, scope_geohashes(region, radius_km, boundary, STAY_GEOHASH_PRECISION), filters, boundary)
    if boundary is None:
        # 지도 칸은 반경보다 넓어 반경 밖 핀은 요약을 받지 않고 뺀다 (반올림 없이 잰 거리)
        pins = {item_id: pin for item_id, pin in pins.items() if pin[1] <= radius_km}
    head = stay_marker_order([marker for marker, _ in pins.values()], sort)[:limit]
    listings = [stay_summary_to_listing(summary, pins[summary.id][1]) for summary in _stay_summaries(client, head, conditions)]
    has_more = len(pins) > len(head)
    notes = limit_notes(
        len(pins), len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f"{STAY_NARROW}·{'지역' if boundary else '반경'}",
        order=STAY_SORT_ORDERS[sort], inspected=len(head), has_more=has_more,
    )
    return ZigbangStaySearchResult(
        region=region,
        radius_km=None if boundary else radius_km,
        boundary=boundary.name if boundary else None,
        total=len(pins),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )


def stay_marker_order(markers: list[ZigbangStayMarkerModel], sort: StaySort) -> list[int]:
    """지도 핀을 웹 지도 목록 순서로 세운 매물 ID (번들 `sortStayMarkers`).

    추천순은 `totalScore` 높은 순, 같으면 ID 큰 순이다 (`compareRecommended`). 가격순은 `weeklyPrice`(주당 임대료+관리비,
    만원 미만 버림) 낮은 순, 최신순은 `reviewedAt` 늦은 순(문자열 비교)이고, 둘 다 같은 값이면 추천순 규칙을 따른다.
    역 가까운 순은 역 기준점이 없으면 웹도 추천순으로 바꾸는데, 지도 경로에서는 `search_stay_listings` 가 먼저 막는다.
    값이 없으면 점수·가격은 0, 등록 시각은 가장 이른 것으로 본다 (2026-11-15 실측: 핀 2,313개 모두 값이 있었다).
    """
    # 정렬은 안정적이라(reverse=True 여도) 추천순으로 먼저 세운 뒤 기준 값으로 다시 세우면 같은 값끼리 추천순이 남는다
    ranked = sorted(markers, key=lambda marker: (-(marker.total_score or 0), -marker.id))
    if sort == 'price':
        ranked.sort(key=lambda marker: marker.weekly_price or 0)
    elif sort == 'newest':
        ranked.sort(key=lambda marker: marker.reviewed_at or '', reverse=True)
    return [marker.id for marker in ranked]


def _stay_search_context(
    region: ZigbangRegion,
    sort: StaySort,
    filters: dict[str, Any],
    whole_address: bool,
) -> ZigbangGuestItemsSearchRequestParameterModel | None:
    """이름으로 찾은 지역의 검색 API 요청. 검색 API 가 받지 않는 지역(좌표·시·도 없는 주소)이거나, 동·구인데 지역 검색으로
    찾으라는 표시(`whole_address`)가 없으면 None."""
    if region.search_type not in {'address', 'subway', 'school', 'university'}:
        return None
    if region.search_type == 'address' and not (region.local1 and whole_address):
        return None
    return ZigbangGuestItemsSearchRequestParameterModel(
        type=region.search_type,
        sort=STAY_SERVER_SORTS[sort],
        local1=region.local1 if region.search_type == 'address' else None,
        local2=region.local2 if region.search_type == 'address' else None,
        local3=region.local3 if region.search_type == 'address' else None,
        lat=region.lat if region.search_type != 'address' else None,
        lng=region.lng if region.search_type != 'address' else None,
        **filters,
    )


def _searched_area(context: ZigbangGuestItemsSearchRequestParameterModel) -> str | None:
    """검색 API 에 보낸 지역 (local1~3, 주소 검색이 아니면 None). 지역을 못 찾았다는 에러에 이 이름을 댄다.

    `normalize_address` 로 세종의 겹친 시 이름을 뺀다. 직방은 세종의 동을 local1 '세종특별자치시'·local2 '세종'·local3
    '반곡동' 으로 줘서, 그대로 이으면(`join_address`) '세종특별자치시 세종 반곡동' 이 된다 (2026-11-10 리뷰·실측. 직방 지역
    검색의 주소는 '세종특별자치시 반곡동'). 앞 조각으로 시작하는 조각을 빼던 것을 이 함수로 바꿨다 (2026-11-11 리뷰: local2 가
    '세종시' 로 오면 빼지 못했다).
    """
    return normalize_address(join_address(context.local1, context.local2, context.local3))


def _stay_pins(
    client: ZigbangClient,
    region: ZigbangRegion,
    hashes: list[str],
    filters: dict[str, Any],
    boundary: ZigbangBoundary | None,
) -> dict[int, tuple[ZigbangStayMarkerModel, float]]:
    """지도 칸마다 단기임대 핀을 받아 매물 ID → (핀, 검색 중심에서 거리)로 모은다. 동 경계 밖 핀은 뺀다.

    핀 좌표는 요약(by-ids) 좌표와 같아 (2026-11-15 실측 71건) 핀으로 범위를 정하고 거리를 잰다.
    """
    pins: dict[int, tuple[ZigbangStayMarkerModel, float]] = {}
    for geohash in hashes:
        response = _stay_search_call(
            client.run_request_guest_items_markers,
            ZigbangGuestItemsMarkersRequestParameterModel(geohash=geohash, **filters),
        )
        for marker in response.markers:
            if outside_boundary(boundary, marker.lat, marker.lng):
                continue
            pins[marker.id] = (marker, haversine_km(region.lat, region.lng, marker.lat, marker.lng))
    return pins


def _stay_summaries(
    client: ZigbangClient,
    item_ids: list[int],
    conditions: ZigbangStayConditions,
) -> list[ZigbangStayItemSummaryModel]:
    """매물 요약을 `item_ids` 순서대로 받는다. 응답에 없는 매물은 빠진다."""
    summaries: dict[int, ZigbangStayItemSummaryModel] = {}
    # 만료 단기임대는 by-ids 가 응답에서 뺀다 (비노출·REJECTED·PENDING·404 를 섞어 보내면 노출 중인 것만 온다).
    # 그래서 상세(get_stay_listing)처럼 status·checkStatus 를 다시 보지 않는다.
    for start in range(0, len(item_ids), STAY_BY_IDS_BATCH_SIZE):
        batch = item_ids[start:start + STAY_BY_IDS_BATCH_SIZE]
        response = _stay_search_call(
            client.run_request_guest_items_by_ids,
            ZigbangGuestItemsByIdsRequestParameterModel(
                item_ids=batch, check_in_date=conditions.check_in, check_out_date=conditions.check_out,
                flexibility=conditions.flexibility,
            ),
        )
        requested = set(batch)
        for summary in response.items:
            if summary.id in requested:
                summaries.setdefault(summary.id, summary)
    return [summaries[item_id] for item_id in item_ids if item_id in summaries]


def stay_parking(detail: ZigbangGuestItemsResponseModel) -> str | None:
    if detail.parking_type is None:
        return None
    available = {'AVAILABLE': '가능', 'UNAVAILABLE': '불가'}.get(detail.parking_type, detail.parking_type)
    fee = {'PAID': '유료', 'FREE': '무료'}.get(detail.parking_fee or '')
    return f'{available} ({fee})' if fee and available == '가능' else available


def stay_detail_to_listing(
    detail: ZigbangGuestItemsResponseModel,
    registered_at: str | None = None,
) -> ZigbangStayListingDetail:
    """단기임대 상세를 `ZigbangStayListingDetail` 로 바꾼다. 사진·본문·호스트 정보는 옮기지 않는다."""
    manage_cost = 0.0 if detail.is_weekly_manage_cost_absent else won_to_manwon_exact(detail.weekly_manage_cost)
    includes = detail.manage_cost_includes
    return ZigbangStayListingDetail(
        source='zigbang',
        id=f'stay-{detail.id}',
        url=stay_item_url(detail.id),
        trade_type='단기임대',
        property_type=STAY_BUILDING_TYPE_LABELS.get(detail.building_type or '', detail.building_type or '단기임대'),
        title=detail.title,
        deposit_manwon=won_to_manwon_exact(detail.deposit),
        area_m2=detail.size_m2,
        area_pyeong=m2_to_pyeong(detail.size_m2),
        floor=detail.floor,
        address=detail.address,
        lat=detail.lat,
        lng=detail.lng,
        registered_at=normalize_date(registered_at),
        room_count=detail.room_count,
        bathroom_count=detail.bathroom_count,
        parking=stay_parking(detail),
        elevator=detail.has_elevator,
        options=sent_or_none(
            detail, 'item_options',
            [STAY_OPTION_LABELS.get(option.option_name, option.option_name) for option in detail.item_options],
        ),
        manage_cost_includes=None if includes is None else [
            {'gas': '가스', 'water': '수도', 'electricity': '전기'}.get(key, key)
            for key, included in includes.items() if included
        ],
        nearby_subways=sent_or_none(detail, 'nearby_stations', [
            f'{station.name} ({station.description})' if station.description else station.name
            for station in detail.nearby_stations
        ]),
        weekly_rent_manwon=won_to_manwon_exact(detail.weekly_rent),
        weekly_manage_cost_manwon=manage_cost,
        cleaning_fee_manwon=0.0 if detail.cleaning_fee_free else won_to_manwon_exact(detail.cleaning_fee),
        discounts=sent_or_none(detail, 'discounts', stay_discounts(detail.discounts, detail.weekly_rent)),
        min_contract_weeks=detail.min_contract_weeks,
        max_contract_weeks=detail.max_contract_weeks,
        max_guests=detail.max_guests,
        duplex=detail.is_duplex,
        refund_policy=STAY_REFUND_POLICY_LABELS.get(detail.refund_policy or '', detail.refund_policy),
    )


def get_stay_listing(
    client: ZigbangClient,
    item_id: int,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
    pet: bool = False,
) -> ZigbangStayListingDetail:
    """단기임대 매물 하나의 상세를 조회한다 (상세 + 노출 시작일용 요약, 2회 호출).

    입주·퇴거일을 주면 기간 비용(`period_cost`)을 직방 요금 계산으로 붙이고, 같은 날짜로 매물 주변 지도를
    조회해 예약이 비어 있는지도 본다 (요금 계산은 예약 여부를 보지 않는다). 요청이 2~5회 늘어난다.

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 노출 중이 아니거나 검수가 끝나지 않았을 때.
        JibsaError: 지난 입주일이거나 계약 기간(최소·최대 주)을 벗어났을 때 (INVALID_ARGUMENT).
    """
    listing_id = f'stay-{item_id}'
    with unavailable_on_404(listing_id):
        detail = client.run_request_guest_items(ZigbangGuestItemsRequestParameterModel(item_id=item_id))
    if detail.status is not True or detail.check_status != 'COMPLETE':
        raise ListingUnavailableError(
            'zigbang',
            listing_id,
            status=None if detail.status is None else str(detail.status).lower(),
            reason=detail.check_status,
        )
    # 상세에는 노출 시작일(reviewedAt)이 없어 목록과 같은 값을 요약에서 받는다
    summaries = client.run_request_guest_items_by_ids(
        ZigbangGuestItemsByIdsRequestParameterModel(item_ids=[item_id])
    )
    summary = next((summary for summary in summaries.items if summary.id == item_id), None)
    listing = stay_detail_to_listing(detail, summary.reviewed_at if summary else None)
    if check_in is None or check_out is None:
        return listing
    price = _calculate_stay_price(client, detail, check_in, check_out, pet)
    available = _stay_available(client, detail, check_in, check_out)
    return listing.model_copy(update={'period_cost': stay_period_cost(price, check_in, check_out, available)})


# 날짜를 준 검색의 금액·가격순이 기간 비용이 아니라는 안내. 2026-10-31 에이전트 검증: 강남역 4주 가격순 1위를 주당 32만 × 4 =
# 128만으로 답했지만 청소비·이용료를 더한 실제 결제는 151만 2천이었고, 주당 요금 3위는 기간 비용으로 4위였다
STAY_WEEKLY_PRICE_NOTE: str = note(
    '참고',
    '목록 금액과 가격순은 주당 임대료+관리비 기준이라 청소비·직방 이용료·장기 할인이 빠져 있습니다. 그 기간에 실제로 내는 돈은 '
    f'--details 로 앞 {DETAILS_MAX}건에 period_cost 를 붙여 보세요 (매물당 요청 1회)',
)


def attach_stay_period_costs(
    client: ZigbangClient,
    result: ZigbangStaySearchResult,
    conditions: ZigbangStayConditions,
) -> ZigbangStaySearchResult:
    """날짜를 준 단기임대 검색의 앞 `DETAILS_MAX` 건에 기간 비용(`period_cost`)을 붙인다 (`--details`, 매물당 요금 계산 1회).

    상세(`get_stay_listing`)와 같은 요금 계산이지만 상세·요약·예약 확인은 다시 받지 않는다. 검색이 같은 날짜로 지도를
    걸렀으니 예약은 비어 있다고 보되, `--flexibility` 로 날짜를 넓혔으면 그 날짜가 비었는지 몰라 `available` 을 null 로 둔다.
    `--pet`(반려동물 허용 매물만)을 줬으면 반려동물을 데려간다고 보고 반려동물 청소비를 넣는다. 정렬은 바꾸지 않는다.
    직방이 계산을 거절한 매물(계약 기간 밖, 그사이 내려감)은 `period_cost` 를 null 로 두고 `notes` 로 알린다.
    """
    check_in, check_out = conditions.check_in, conditions.check_out
    # CLI 가 --details 에 날짜를 요구한다
    assert check_in is not None and check_out is not None
    available = None if conditions.flexibility else True
    listings: list[ZigbangStayListing] = []
    rejected = 0
    for index, listing in enumerate(result.listings):
        if index >= DETAILS_MAX:
            listings.append(listing_as(ZigbangStayPricedListing, listing))
            continue
        try:
            price = client.run_request_guest_items_price_calculation(
                ZigbangGuestItemsPriceCalculationRequestPayloadModel(
                    item_id=int(listing.id.removeprefix('stay-')), check_in_date=check_in, check_out_date=check_out,
                    has_pet=conditions.pet_allowed,
                )
            )
        except HTTPStatusError as exc:
            if exc.response.status_code not in (400, 404):
                raise
            rejected += 1
            listings.append(listing_as(ZigbangStayPricedListing, listing))
            continue
        listings.append(listing_as(
            ZigbangStayPricedListing, listing, period_cost=stay_period_cost(price, check_in, check_out, available),
        ))
    notes = [note(
        '참고',
        '정렬은 주당 임대료+관리비 기준 그대로입니다. 그 기간에 실제로 내는 돈은 period_cost.total_payment_manwon 에서 '
        'deposit_manwon(돌려받는 보증금)을 뺀 값입니다',
    )]
    if rejected:
        notes.append(note('실패', f'{rejected}건은 직방이 이 기간 요금 계산을 거절해 period_cost 가 null 입니다 (계약 기간 밖 등)'))
    if len(result.listings) > DETAILS_MAX:
        notes.append(f'기간 비용(--details)은 앞 {DETAILS_MAX}건에만 붙였습니다')
    return result.model_copy(update={'listings': listings, 'notes': result.notes + notes})


def _calculate_stay_price(
    client: ZigbangClient,
    detail: ZigbangGuestItemsResponseModel,
    check_in: str,
    check_out: str,
    pet: bool,
) -> ZigbangGuestItemsPriceCalculationResponseModel:
    try:
        return client.run_request_guest_items_price_calculation(
            ZigbangGuestItemsPriceCalculationRequestPayloadModel(
                item_id=detail.id, check_in_date=check_in, check_out_date=check_out, has_pet=pet,
            )
        )
    except HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        # 400 본문은 늘 객체이고 message 는 문자열 또는 형식 오류 배열이다 (2026-10-11 실측 6종)
        message = (_stay_400_body(exc) or {}).get('message')
        reason = message if isinstance(message, str) else None
        weeks = f'{detail.min_contract_weeks or "?"}~{detail.max_contract_weeks or "?"}주'
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=STAY_PRICE_ERRORS.get(reason or '', reason or '직방이 기간 요금 계산을 거절했습니다'),
            hint=f'입주일은 한국 날짜 기준 오늘 이후로, 계약 기간은 이 매물의 {weeks} 안으로 --check-in/--check-out 을 다시 주세요',
        ) from None


# 단기임대 검색 API 의 기간 오류. 로컬에서 7~84일을 먼저 막지만 직방이 제한을 바꿔도 소스 장애로 보이지 않게 한다
STAY_PERIOD_ERRORS: frozenset[str] = frozenset({'MIN_DURATION_VIOLATION', 'MAX_DURATION_VIOLATION'})
StayResponse = TypeVar('StayResponse')
StayParameter = TypeVar('StayParameter')


def _stay_400_body(exc: HTTPStatusError) -> dict[str, Any] | None:
    """단기임대 API 가 400 으로 준 본문 객체 (`error` 코드·`message`). 400 이 아니거나 JSON 객체가 아니면 None."""
    return error_body(exc) if exc.response.status_code == 400 else None


def _stay_search_call(call: Callable[[StayParameter], StayResponse], parameter: StayParameter) -> StayResponse:
    """단기임대 검색 API 를 부르고, 기간이 허용 범위 밖이라는 400 은 입력 오류(INVALID_ARGUMENT)로 바꾼다."""
    try:
        return call(parameter)
    except HTTPStatusError as exc:
        body = _stay_400_body(exc)
        if body is None or body.get('error') not in STAY_PERIOD_ERRORS:
            raise
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 단기임대 검색 기간 오류: {body.get('message') or body.get('error')}",
            hint=(
                f'--check-in 부터 마지막으로 머무는 날 --check-out 까지 이용일로 세어 '
                f'{STAY_SEARCH_MIN_DAYS}~{STAY_SEARCH_MAX_DAYS}일로 주세요 (1주 = 11-02~11-08)'
            ),
        ) from None


def _stay_region_search(
    client: ZigbangClient,
    context: ZigbangGuestItemsSearchRequestParameterModel,
    name: str,
) -> list[int]:
    """단기임대 검색 API 로 매물 ID 를 받는다. 지역을 찾지 못했다는 400 은 `RegionNotFoundError` 로 바꾼다.

    세종의 동은 local1·local2 를 어떻게 줘도 REGION_NOT_FOUND 였다 (2026-10-11 실측: 반곡동을 세종특별자치시·세종시 ×
    세종·없음·세종시 조합 모두 400, 세종특별자치시 전체·양평읍·역삼동·치평동은 200). 2026-11-10 에는 반곡동·어진동·나성동
    모두 local1=세종특별자치시·local2=세종 으로 200 이라 이 경로를 타지 않는다. 다시 막힐 수 있어 남겨 두며, 소스
    장애(UPSTREAM_ERROR)로 보이지 않게 바꾸고 CLI 가 지도 칸(동 경계·반경) 검색으로 다시 찾는다. 이 경로를 타면 직방이
    바뀐 것이라 CLI 의 대체 경로 안내에 업데이트 문구가 붙는다.
    """
    try:
        return _stay_search_call(client.run_request_guest_items_search, context).item_ids
    except HTTPStatusError as exc:
        body = _stay_400_body(exc)
        if body is None or body.get('error') != 'REGION_NOT_FOUND':
            raise
        raise RegionNotFoundError(name, hint='--radius 로 반경 검색하세요') from None


def _stay_available(
    client: ZigbangClient,
    detail: ZigbangGuestItemsResponseModel,
    check_in: str,
    check_out: str,
) -> bool | None:
    """같은 날짜로 매물 주변 지도 칸을 조회해 이 매물이 나오면 예약이 비어 있다고 본다. 좌표가 없으면 None.

    지도 검색은 입주일과 마지막 날을 포함해 7~84일만 받는다. 요금 계산은 매물 계약 범위만 보므로, 그 밖의
    기간(지금은 없지만 12주보다 길게 받는 매물 등)은 확인하지 않고 모름(None)으로 둔다.
    """
    if detail.lat is None or detail.lng is None:
        return None
    if not STAY_SEARCH_MIN_DAYS <= stay_days(check_in, check_out) <= STAY_SEARCH_MAX_DAYS:
        return None
    # 지도 좌표가 상세 좌표와 조금 달라 칸 경계를 넘을 수 있어 주변 칸까지 본다
    for geohash in geohashes_covering(detail.lat, detail.lng, STAY_AVAILABILITY_RADIUS_KM, STAY_GEOHASH_PRECISION):
        markers = client.run_request_guest_items_markers(
            ZigbangGuestItemsMarkersRequestParameterModel(
                geohash=geohash, check_in_date=check_in, check_out_date=check_out,
            )
        )
        if any(marker.id == detail.id for marker in markers.markers):
            return True
    return False


def stay_period_cost(
    price: ZigbangGuestItemsPriceCalculationResponseModel,
    check_in: str,
    check_out: str,
    available: bool | None,
) -> ZigbangStayPeriodCost:
    """요금 계산 응답(원)을 만원 단위 기간 비용으로 바꾼다."""
    cleaning = None
    if price.cleaning_fee is not None or price.pet_cleaning_fee is not None:
        cleaning = (price.cleaning_fee or 0) + (price.pet_cleaning_fee or 0)
    discount = None
    if price.total_discount_amount is not None or price.total_promotion_discount is not None:
        discount = (price.total_discount_amount or 0) + (price.total_promotion_discount or 0)
    return ZigbangStayPeriodCost(
        check_in=check_in,
        check_out=check_out,
        available=available,
        days=price.total_days,
        weeks=price.weeks,
        remaining_days=price.remaining_days,
        rent_manwon=won_to_manwon_exact(price.total_rent),
        manage_cost_manwon=won_to_manwon_exact(price.total_manage_cost),
        cleaning_fee_manwon=won_to_manwon_exact(cleaning),
        discount_manwon=won_to_manwon_exact(discount),
        discounts=[
            f'{discount.name} {discount.rate:g}%' if discount.rate is not None else discount.name
            for discount in price.discounts
            if discount.name
        ],
        service_fee_manwon=won_to_manwon_exact(price.platform_fee),
        deposit_manwon=won_to_manwon_exact(price.deposit),
        total_payment_manwon=won_to_manwon_exact(price.total_guest_payment),
    )
