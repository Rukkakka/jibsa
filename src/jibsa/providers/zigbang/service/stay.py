"""단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from collections.abc import Callable
from datetime import (
    datetime,
    timezone,
)

from httpx import (
    HTTPStatusError,
    Response,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
    within_radius,
)
from jibsa.core.korean import is_ri_code
from jibsa.core.listing import (
    Listing,
    ListingDetail,
    beyond_radius_notes,
    by_distance,
    join_address,
    limit_notes,
    m2_to_pyeong,
    normalize_date,
    won_to_manwon,
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
    stay_days,
)
from jibsa.providers.zigbang.api.response.stay import (
    ZigbangGuestItemsPriceCalculationResponseModel,
    ZigbangGuestItemsResponseModel,
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
)
from jibsa.providers.zigbang.service.common import (
    ZigbangBoundary,
    ZigbangRegion,
    drop_unused_scope,
    unavailable_on_404,
)
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
StaySort = Literal['distance', 'price', 'newest']
STAY_SORTS: tuple[StaySort, ...] = ('distance', 'price', 'newest')
STAY_AVAILABILITY_RADIUS_KM: float = 0.3
STAY_PRICE_ERRORS: dict[str, str] = {
    'MIN_CONTRACT_PERIOD': '계약 기간이 이 매물의 최소 계약 기간보다 짧습니다',
    'MAX_CONTRACT_PERIOD': '계약 기간이 이 매물의 최대 계약 기간보다 깁니다',
}
# 직방 단기임대 매물은 웹 매물 페이지가 없고 직방 앱에서만 열린다.
STAY_URL: str = 'https://www.zigbang.com/home/short-term-rental'
STAY_APP_NOTE: str = (
    '직방 단기임대 매물은 웹 매물 페이지가 없어 url 이 직방 단기임대 안내 페이지입니다. '
    '매물 확인·예약은 직방 앱의 단기임대 탭에서 제목으로 찾으세요'
)


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
        Field(description='검색 반경 (km). 동 경계로 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description='반경 대신 찾은 동·구 등 지역 이름. 반경으로 찾았으면 키가 없다')
    ] = None
    total_in_radius: Annotated[
        int,
        Field(description='반경(동 경계로 찾았으면 경계) 안 조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    listings: Annotated[
        list[ZigbangStayListing],
        Field(description='선택한 정렬 순서의 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='앱에서만 열린다·일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unused_scope(handler(self))


def stay_discount_label(discount: ZigbangStayDiscountModel) -> str | None:
    """할인 조건 한 줄. 꺼진 할인은 None."""
    if discount.is_active is False:
        return None
    if discount.discount_rate:
        amount = f'{discount.discount_rate:g}%'
    elif discount.discount_amount:
        amount = f'{won_to_manwon(discount.discount_amount):g}만원'
    else:
        return None
    if discount.discount_type == 'LONG_TERM' and discount.condition_weeks:
        return f'{discount.condition_weeks}주 이상 {amount} 할인'
    if discount.discount_type == 'INSTANT':
        return f'즉시 {amount} 할인'
    return f'{amount} 할인'


def stay_discounts(discounts: list[ZigbangStayDiscountModel]) -> list[str]:
    return [label for label in (stay_discount_label(discount) for discount in discounts) if label]


def stay_summary_to_listing(
    summary: ZigbangStayItemSummaryModel,
    distance_km: float | None = None,
) -> ZigbangStayListing:
    address = summary.address
    return ZigbangStayListing(
        source='zigbang',
        id=f'stay-{summary.id}',
        url=STAY_URL,
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
        weekly_rent_manwon=won_to_manwon(summary.weekly_rent),
        weekly_manage_cost_manwon=won_to_manwon(summary.weekly_manage_cost),
        room_count=summary.room_count,
        bathroom_count=summary.bathroom_count,
        discounts=stay_discounts(summary.discounts),
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
    sort: StaySort = 'distance',
    radius_km: float = 1.0,
    limit: int = 20,
    boundary: ZigbangBoundary | None = None,
    use_search_api: bool = False,
    whole_address: bool = False,
    extra_regions: list[ZigbangRegion] | None = None,
) -> ZigbangStaySearchResult:
    """직방 단기임대를 거리·가격·최근 등록 순으로 조회한다. 지역 전체 또는 반경·동 경계를 지원한다.

    직방 단기임대는 원룸·빌라의 '단기' 거래와 다른 별도 서비스(주 단위 계약, stay-apis)다.
    모든 조건(`conditions`)은 서버에서 거른다 (주당 요금은 만원). 라벨(오피스텔, 에어컨, 지하 ...)은 서버 코드로 바꿔 보낸다.
    use_search_api 면 이름 검색으로 보고 반경 밖을 자르며, 검색 API 로 ID 를 받는 건 지역 전체·동 경계일 때뿐이다
    (반경 안 매물은 지도 핀에 모두 있다). whole_address는 지역 전체를 조회한다.
    extra_regions 는 지역 전체로 함께 찾을 동 ('○가' 로 나뉜 성수동1가·2가 등)이나 구가 있는 시의 나머지 구 (성남시 수정구·중원구).
    지역마다 검색 API 를 1회 더 부르고 매물 ID 를 합친 뒤 정렬·limit 을 적용한다. 리는 검색 API 가 local3(그 위 읍·면)으로
    찾아 `boundary` 를 읍·면 이름으로 낸다.

    Raises:
        RegionNotFoundError: 검색 API 가 지역을 찾지 못했을 때 (세종의 동, `_stay_region_search`).
    """
    check_stay_sort(sort)
    conditions = conditions or ZigbangStayConditions()
    filters = stay_filter_of(conditions)
    context = _stay_search_context(region, sort, filters) if use_search_api else None
    address_scope = context is not None and context.type == 'address' and whole_address
    if address_scope:
        boundary = None
    # 이름 검색·가격순·최신순은 요약을 받은 뒤 반경으로 자른다
    radius_cut = (context is not None or sort != 'distance') and not address_scope and boundary is None
    # 검색 API 응답 ID (부른 순서대로, 응답 순서 그대로). 지역 전체 가격순·최신순은 이 순서로 앞쪽만 요약을 받는다
    search_lists: list[list[int]] = []
    # 반경으로 자르면 검색 API 를 부르지 않는다. 반경 안 매물은 지도 핀에 모두 있고, 지역 검색 ID 는 구·동 전체라 반경 밖
    # 요약까지 받게 된다 (2026-10-11 실측: 강남구·마포구·역삼동·성수동·강남역·홍대입구역에서 핀에 없는 검색 ID 25개 모두
    # 반경 밖, 강남구 1km 가격순 by-ids 4회 → 1회)
    if context is not None and not radius_cut:
        search_lists = _stay_search_ids(client, context, region, (extra_regions or []) if address_scope else [])
    search_ids = {item_id for ids in search_lists for item_id in ids}
    # 전용 API에는 반경 파라미터가 없어 지도 칸으로 원하는 반경의 후보를 보완한다.
    hashes = [] if address_scope else scope_geohashes(region, radius_km, boundary, STAY_GEOHASH_PRECISION)
    pins = _stay_pins(client, region, hashes, filters, boundary)

    # 지도 칸은 반경보다 넓어 반경 밖 핀은 요약을 받아도 버리므로 미리 뺀다 (2026-10-10 실측: 강남역 1km 핀 130개 중
    # 반경 안 57개, by-ids 3회 → 1회)
    if radius_cut:
        pins = {item_id: distance for item_id, distance in pins.items() if distance <= radius_km}
    nearest = [item_id for item_id, _ in sorted(pins.items(), key=lambda entry: entry[1])[:limit]]
    # 지역 전체 가격순·최신순은 검색 API 가 같은 기준(주당 임대료+관리비, 등록 시각)으로 정렬해 준다 (2026-10-11 실측:
    # 강남구·마포구 343건, 날짜·방 수·가격 조건을 줘도 역전 0건). 지역마다 앞 limit 개만 요약을 받아 아래에서 합쳐 정렬하고 자른다
    server_sorted = address_scope and sort != 'distance'
    if sort == 'distance' and (radius_cut or context is None):
        # 거리순은 가까운 핀 limit 개만 요약을 받는다
        candidate_ids = nearest
    elif server_sorted:
        candidate_ids = sorted({item_id for ids in search_lists for item_id in ids[:limit]})
    else:
        # 검색 ID에는 위치가 없고 정렬 값은 요약에만 있어 후보 요약을 모두 받은 뒤 반경·정렬·limit 을 적용한다.
        # 지역 전체 거리순도 위치가 요약에만 있어 상한을 두지 않는다 (2026-10-11 실측: 서울시 전체 1,491건이 by-ids 30회·약 7초)
        candidate_ids = sorted(search_ids | pins.keys())
    listings, accepted_ids, sort_keys = _stay_summaries(
        client, region, candidate_ids, conditions, pins,
        sort=sort, boundary=boundary, radius_cut=radius_cut, radius_km=radius_km,
    )

    if sort == 'distance':
        listings.sort(key=by_distance)
    else:
        listings.sort(key=lambda listing: sort_keys[listing.id])
    order = {'distance': '검색 중심에서 가까운', 'price': '주당 임대료·관리비 합계가 낮은', 'newest': '최근 등록된'}[sort]
    if context is not None or sort != 'distance':
        if radius_cut and sort == 'distance':
            # 거리순 이름 검색은 가까운 핀만 요약을 받아, 받지 않은 반경 안 핀도 센다
            in_radius = len(pins.keys() | accepted_ids)
        elif server_sorted:
            # 앞쪽만 요약을 받아 검색 ID 수로 센다. by-ids 가 빼는 매물은 검색에도 없다 (2026-10-11 실측: 서울시 1,491건·강남구
            # 156건·마포구 187건 모두 같음)
            in_radius = len(search_ids)
        else:
            in_radius = len(listings)
        listings = listings[:limit]
        scope_notes = limit_notes(in_radius, len(listings), limit, order=order, narrow=STAY_NARROW, radius=radius_cut)
    elif boundary is not None:
        in_radius = len(pins)
        scope_notes = limit_notes(in_radius, len(listings), limit, order=f'{boundary.name} 중심에서 가까운', narrow=STAY_NARROW)
    else:
        in_radius = sum(1 for distance in pins.values() if within_radius(distance, radius_km))
        scope_notes = limit_notes(in_radius, len(listings), limit, narrow=STAY_NARROW, radius=True) + beyond_radius_notes(listings, radius_km)
    return ZigbangStaySearchResult(
        region=region,
        radius_km=None if boundary or address_scope else radius_km,
        boundary=(
            (region.local3 if is_ri_code(region.legal_division_code) and region.local3 else region.name) if address_scope
            else boundary.name if boundary else None
        ),
        total_in_radius=in_radius,
        returned=len(listings),
        listings=listings,
        notes=[STAY_APP_NOTE] + scope_notes,
    )


def _stay_search_context(
    region: ZigbangRegion,
    sort: StaySort,
    filters: dict[str, Any],
) -> ZigbangGuestItemsSearchRequestParameterModel | None:
    """이름으로 찾은 지역의 검색 API 요청. 검색 API 가 받지 않는 지역(좌표·시·도 없는 주소)이면 None."""
    if region.search_type not in {'address', 'subway', 'school', 'university'}:
        return None
    if region.search_type == 'address' and not region.local1:
        return None
    return ZigbangGuestItemsSearchRequestParameterModel(
        type=region.search_type,
        sort={'price': 'PRICE_ASC', 'newest': 'NEWEST'}.get(sort),
        local1=region.local1 if region.search_type == 'address' else None,
        local2=region.local2 if region.search_type == 'address' else None,
        local3=region.local3 if region.search_type == 'address' else None,
        lat=region.lat if region.search_type != 'address' else None,
        lng=region.lng if region.search_type != 'address' else None,
        **filters,
    )


def _stay_search_ids(
    client: ZigbangClient,
    context: ZigbangGuestItemsSearchRequestParameterModel,
    region: ZigbangRegion,
    extra_regions: list[ZigbangRegion],
) -> list[list[int]]:
    """검색 API 로 지역(과 함께 찾을 지역)마다 매물 ID 를 받는다. 지역마다 응답 순서 그대로다."""
    search_lists = [_stay_region_search(client, context, region.name)]
    # '○가' 동·구가 있는 시의 구는 검색 중심과 같은 시·구에서만 오고 local1 이 늘 있어 (2026-10-11 실측: '○가' 동 13곳,
    # 성남시·수원시 구) model_copy 로 다시 검증하지 않는다
    for extra in extra_regions:
        search_lists.append(_stay_region_search(client, context.model_copy(update={
            'local1': extra.local1, 'local2': extra.local2, 'local3': extra.local3,
        }), extra.name))
    return search_lists


def _stay_pins(
    client: ZigbangClient,
    region: ZigbangRegion,
    hashes: list[str],
    filters: dict[str, Any],
    boundary: ZigbangBoundary | None,
) -> dict[int, float]:
    """지도 칸마다 단기임대 핀을 받아 매물 ID → 검색 중심에서 거리로 모은다. 동 경계 밖 핀은 뺀다."""
    pins: dict[int, float] = {}
    for geohash in hashes:
        response = _stay_search_call(
            client.run_request_guest_items_markers,
            ZigbangGuestItemsMarkersRequestParameterModel(geohash=geohash, **filters),
        )
        for marker in response.markers:
            if outside_boundary(boundary, marker.lat, marker.lng):
                continue
            pins[marker.id] = haversine_km(region.lat, region.lng, marker.lat, marker.lng)
    return pins


def _stay_summaries(
    client: ZigbangClient,
    region: ZigbangRegion,
    candidate_ids: list[int],
    conditions: ZigbangStayConditions,
    pins: dict[int, float],
    *,
    sort: StaySort,
    boundary: ZigbangBoundary | None,
    radius_cut: bool,
    radius_km: float,
) -> tuple[list[ZigbangStayListing], set[int], dict[str, tuple[bool, float, int]]]:
    """후보 요약을 받아 범위 밖을 뺀 매물, 받아들인 매물 ID, 가격·최신순 정렬 키를 준다."""
    listings: list[ZigbangStayListing] = []
    accepted_ids: set[int] = set()
    sort_keys: dict[str, tuple[bool, float, int]] = {}
    # 만료 단기임대는 by-ids 가 응답에서 뺀다 (비노출·REJECTED·PENDING·404 를 섞어 보내면 노출 중인 것만 온다).
    # 그래서 상세(get_stay_listing)처럼 status·checkStatus 를 다시 보지 않는다.
    for start in range(0, len(candidate_ids), STAY_BY_IDS_BATCH_SIZE):
        batch = set(candidate_ids[start:start + STAY_BY_IDS_BATCH_SIZE])
        summaries = _stay_search_call(
            client.run_request_guest_items_by_ids,
            ZigbangGuestItemsByIdsRequestParameterModel(
                item_ids=sorted(batch), check_in_date=conditions.check_in, check_out_date=conditions.check_out,
                flexibility=conditions.flexibility,
            ),
        )
        for summary in summaries.items:
            if summary.id not in batch or summary.id in accepted_ids:
                continue
            distance = pins.get(summary.id)
            # 경계 검사(outside_boundary)는 좌표가 있을 때만 한다. 좌표 없는 요약은 경계 검사에 None 이 가지 않고, 아래에서
            # 경계 안으로 거른 핀(pins)에 있으면 남고 없으면 빠진다 (2026-10-11 리뷰 오탐 확인. 실측: by-ids 응답 4건의
            # 요약 30건 모두 좌표 있음)
            if summary.lat is not None and summary.lng is not None:
                distance = haversine_km(region.lat, region.lng, summary.lat, summary.lng)
                if outside_boundary(boundary, summary.lat, summary.lng):
                    continue
            if radius_cut and (distance is None or distance > radius_km):
                continue
            if boundary is not None and summary.id not in pins:
                if summary.lat is None or summary.lng is None:
                    continue
            accepted_ids.add(summary.id)
            listing = stay_summary_to_listing(summary, distance)
            listings.append(listing)
            key = _stay_sort_key(summary, sort)
            if key is not None:
                sort_keys[listing.id] = key
    return listings, accepted_ids, sort_keys


def _stay_sort_key(
    summary: ZigbangStayItemSummaryModel,
    sort: StaySort,
) -> tuple[bool, float, int] | None:
    """가격순·최신순 정렬 키 (모르는 값은 뒤로). 거리순이면 None."""
    if sort == 'price':
        known = summary.weekly_rent is not None and summary.weekly_manage_cost is not None
        price = (summary.weekly_rent or 0) + (summary.weekly_manage_cost or 0)
        return (not known, price, summary.id)
    if sort == 'newest':
        # 출력 날짜는 일 단위라 원 응답의 등록 시각으로 정렬한다.
        try:
            moment = datetime.fromisoformat((summary.reviewed_at or '').replace('Z', '+00:00'))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            timestamp = moment.timestamp()
        except ValueError:
            timestamp = None
        return (timestamp is None, -(timestamp or 0), summary.id)
    return None


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
    manage_cost = 0.0 if detail.is_weekly_manage_cost_absent else won_to_manwon(detail.weekly_manage_cost)
    includes = detail.manage_cost_includes
    return ZigbangStayListingDetail(
        source='zigbang',
        id=f'stay-{detail.id}',
        url=STAY_URL,
        trade_type='단기임대',
        property_type=STAY_BUILDING_TYPE_LABELS.get(detail.building_type or '', detail.building_type or '단기임대'),
        title=detail.title,
        deposit_manwon=won_to_manwon(detail.deposit),
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
        options=[STAY_OPTION_LABELS.get(option.option_name, option.option_name) for option in detail.item_options],
        manage_cost_includes=None if includes is None else [
            {'gas': '가스', 'water': '수도', 'electricity': '전기'}.get(key, key)
            for key, included in includes.items() if included
        ],
        nearby_subways=[
            f'{station.name} ({station.description})' if station.description else station.name
            for station in detail.nearby_stations
        ],
        weekly_rent_manwon=won_to_manwon(detail.weekly_rent),
        weekly_manage_cost_manwon=manage_cost,
        cleaning_fee_manwon=0.0 if detail.cleaning_fee_free else won_to_manwon(detail.cleaning_fee),
        discounts=stay_discounts(detail.discounts),
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
        reason = _stay_price_error(exc.response)
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


def _stay_search_call(call: Callable[[StayParameter], StayResponse], parameter: StayParameter) -> StayResponse:
    """단기임대 검색 API 를 부르고, 기간이 허용 범위 밖이라는 400 은 입력 오류(INVALID_ARGUMENT)로 바꾼다."""
    try:
        return call(parameter)
    except HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        try:
            body = exc.response.json()
        except ValueError:
            raise exc from None
        if not isinstance(body, dict) or body.get('error') not in STAY_PERIOD_ERRORS:
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

    세종의 동은 local1·local2 를 어떻게 줘도 REGION_NOT_FOUND 다 (2026-10-11 실측: 반곡동을 세종특별자치시·세종시 ×
    세종·없음·세종시 조합 모두 400, 세종특별자치시 전체·양평읍·역삼동·치평동은 200). 소스 장애(UPSTREAM_ERROR)로 보이지
    않게 바꾸고, CLI 가 지도 칸(동 경계·반경) 검색으로 다시 찾는다.
    """
    try:
        return _stay_search_call(client.run_request_guest_items_search, context).item_ids
    except HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        try:
            body = exc.response.json()
        except ValueError:
            raise exc from None
        if not isinstance(body, dict) or body.get('error') != 'REGION_NOT_FOUND':
            raise
        raise RegionNotFoundError(name, hint='--radius 로 반경 검색하세요') from None


def _stay_price_error(response: Response) -> str | None:
    # 400 본문은 늘 객체이고 message 는 문자열 또는 형식 오류 배열이다 (2026-10-11 실측 6종)
    try:
        message = response.json().get('message')
    except ValueError:
        return None
    return message if isinstance(message, str) else None


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
        rent_manwon=won_to_manwon(price.total_rent),
        manage_cost_manwon=won_to_manwon(price.total_manage_cost),
        cleaning_fee_manwon=won_to_manwon(cleaning),
        discount_manwon=won_to_manwon(discount),
        discounts=[
            f'{discount.name} {discount.rate:g}%' if discount.rate is not None else discount.name
            for discount in price.discounts
            if discount.name
        ],
        service_fee_manwon=won_to_manwon(price.platform_fee),
        deposit_manwon=won_to_manwon(price.deposit),
        total_payment_manwon=won_to_manwon(price.total_guest_payment),
    )
