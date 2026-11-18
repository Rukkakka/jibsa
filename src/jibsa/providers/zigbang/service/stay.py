"""단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from collections.abc import Callable
from datetime import (
    date,
    datetime,
    timedelta,
)

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
    RegionNotFoundError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.http import error_body
from jibsa.core.korean import is_ri_code
from jibsa.core.listing import (
    KST,
    Listing,
    ListingDetail,
    format_manwon,
    join_address,
    limit_notes,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    note,
    won_to_manwon,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.stay import (
    STAY_SEARCH_MAX_DAYS,
    STAY_SEARCH_MIN_DAYS,
    ZigbangGuestItemsByIdsRequestParameterModel,
    ZigbangGuestItemsMarkersRequestParameterModel,
    ZigbangGuestItemsRequestParameterModel,
    ZigbangGuestItemsSearchRequestParameterModel,
    ZigbangStayBuildingType,
    ZigbangStayDiscountType,
    ZigbangStayFloorType,
    ZigbangStayOption,
    ZigbangStaySearchSort,
    validate_stay_dates,
)
from jibsa.providers.zigbang.api.response.stay import (
    ZigbangGuestItemsResponseModel,
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
    ZigbangStayMarkerModel,
    ZigbangStayScheduleModel,
)
from jibsa.providers.zigbang.service.common import (
    MAX_LIST_LIMIT,
    ZigbangBoundary,
    ZigbangRegion,
    drop_unused_scope,
    sent_or_none,
    text_or_none,
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
    Self,
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
# 직방 웹 층 필터의 다섯 선택지 (2026-11-17). 10층 매물은 2-10층에 들고, 11층이상의 코드는 FLOOR_10_PLUS 다
# (FLOOR_11_OVER 는 서버가 400 을 준다)
STAY_FLOOR_TYPE_BY_LABEL: dict[str, ZigbangStayFloorType] = {
    '지하': 'BASEMENT',
    '1층': 'FIRST',
    '2-10층': 'FLOOR_2_10',
    '11층이상': 'FLOOR_10_PLUS',
    '옥탑': 'ROOFTOP',
}
STAY_DISCOUNT_TYPE_BY_LABEL: dict[str, ZigbangStayDiscountType] = {
    '장기계약': 'LONG_TERM',
    '즉시': 'INSTANT',
}
STAY_REFUND_POLICY_LABELS: dict[str, str] = {
    'FLEXIBLE': '유연',
    'STANDARD': '표준',
    'STRICT': '엄격',
}
# 위약금 표. 직방 응답은 정책 이름(refundPolicy)만 주고 표는 웹 번들(`RefundPolicySection`)에 고정돼 있어 옮겨 적은 것이다
# (2026-11-17). 직방이 표를 바꾸면 주 1회 감시(`scripts/monitor/api_check.py` 의 `WEEKLY_CHECKS`)가 알린다. 값은 (취소 시점,
# 위약금) 다섯 쌍이고 글자는 웹 표기 그대로다
STAY_REFUND_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    'FLEXIBLE': (
        ('입주 14일전', '없음'),
        ('입주 7일전', '임대료의 15%'),
        ('입주 3일전', '임대료의 30%'),
        ('입주 1일전', '임대료의 40%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STANDARD': (
        ('입주 14일전', '임대료의 10%'),
        ('입주 7일전', '임대료의 30%'),
        ('입주 3일전', '임대료의 40%'),
        ('입주 1일전', '임대료의 50%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STRICT': (
        ('입주 14일전', '임대료의 20%'),
        ('입주 7일전', '임대료의 50%'),
        ('입주 3일전', '임대료의 60%'),
        ('입주 1일전', '임대료의 70%'),
        ('입주 당일 이후', '취소불가'),
    ),
}
STAY_PARKING_METHOD_LABELS: dict[str, str] = {
    'SELF': '자주식',
    'MECHANICAL': '기계식',
}
# 입주·퇴실 방식 (웹 표기. 모르는 코드는 웹도 그대로 쓴다)
STAY_CHECK_METHOD_LABELS: dict[str, str] = {
    'SELF': '비대면',
    'MEET': '임대인 대면',
    'KEYBOX': '키박스',
}
# 달력에서 막힌 날의 종류. 웹이 날짜를 막는 일정 종류(STAY_UNAVAILABLE_SCHEDULES)가 이 표의 키라 한쪽만 고치지 않는다
STAY_SCHEDULE_KIND_LABELS: dict[str, str] = {
    'RESERVED': '예약',
    'BLOCKED': '막힘',
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
# limit_notes 의 '… 순으로' 앞말
STAY_SORT_ORDERS: dict[StaySort, str] = {
    'recommended': '직방 추천',
    'price': '주당 임대료·관리비 합계가 낮은',
    'newest': '최근 등록된',
    'distance': '역에서 가까운',
}
# 역 검색(type=subway)은 직방이 역에서 약 1km 안만 준다 (2026-11-15 실측: 강남역 71건, 가장 먼 것 0.979km)
STAY_SUBWAY_RADIUS_KM: float = 1.0
# 웹 날짜 고르기 창이 받는 가장 늦은 마지막 날은 입주일 + 83일이다 (번들 `getMaxCheckOut`)
STAY_MAX_CHECK_OUT_DAYS: int = 83
# 웹이 날짜를 막는 일정 종류 (번들 `isUnavailableSchedule`). 이름 표(STAY_SCHEDULE_KIND_LABELS)의 키와 같아 표를 고치면 따라간다
STAY_UNAVAILABLE_SCHEDULES: frozenset[str] = frozenset(STAY_SCHEDULE_KIND_LABELS)


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


class ZigbangStayRefundRule(BaseModel):
    """위약금 표의 한 행. 직방 웹 위약금 정보 표와 같다."""

    when: Annotated[
        str,
        Field(description="취소 시점 (예: '입주 7일전')")
    ]
    penalty: Annotated[
        str,
        Field(description="위약금 (예: '임대료의 30%', '없음', '취소불가')")
    ]


class ZigbangStayUnavailablePeriod(BaseModel):
    """예약할 수 없는 기간 하나."""

    start: Annotated[
        str,
        Field(description='시작일 (YYYY-MM-DD)')
    ]
    end: Annotated[
        str,
        Field(description='끝날 (YYYY-MM-DD, 이 날까지 막힌다)')
    ]
    kind: Annotated[
        str,
        Field(description="종류 ('예약' 다른 손님이 예약함, '막힘' 임대인이 막음)")
    ]


class ZigbangStayListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 단기임대 매물. 입주일·마지막 날을 주면 예약 가능 여부(`available`)가 붙는다."""

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
        Field(description='환불 정책 (유연, 표준, 엄격. 직방 웹 위약금 정보의 이름)')
    ] = None
    refund_rules: Annotated[
        list[ZigbangStayRefundRule] | None,
        Field(description='위약금 표 (취소 시점별 위약금 5행, 직방 웹 위약금 정보 표와 같다). 정책을 모르거나 표에 없는 정책이면 null')
    ] = None
    kitchen_count: Annotated[
        int | None,
        Field(description='주방 수. 0 이면 0')
    ] = None
    living_room_count: Annotated[
        int | None,
        Field(description='거실 수. 0 이면 0')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='주차 대수. 주차 불가면 키가 없고, 가능한데 직방이 대수를 주지 않으면 null')
    ] = None
    parking_method: Annotated[
        str | None,
        Field(description="주차 방식 ('자주식', '기계식'). 주차 불가면 키가 없고, 직방이 주지 않으면 null")
    ] = None
    pet_allowed: Annotated[
        bool | None,
        Field(description=(
            '반려동물 동반 가능 여부 (직방 웹 옵션의 반려동물 분류. options 에는 들어 있지 않다). '
            '직방이 옵션 목록을 주지 않으면 null (직방 웹은 이때 동반 불가로 그린다)'
        ))
    ] = None
    pet_cleaning_fee_manwon: Annotated[
        float | None,
        Field(description=(
            '반려동물을 데려올 때 추가 청소비 (만원). 직방 웹은 동반 가능 여부와 상관없이 0 보다 크면 보여 준다. '
            '동반 가능이면 0 이면 0, 직방이 주지 않으면 null. 동반 불가면 0 보다 클 때만 값이 있고 아니면 키가 없다. '
            '동반 가능 여부를 모를 때(pet_allowed null)는 0 보다 크면 그 값, 아니면 null'
        ))
    ] = None
    check_in_time: Annotated[
        str | None,
        Field(description="입주 시각 ('15:00')")
    ] = None
    check_out_time: Annotated[
        str | None,
        Field(description="퇴실 시각 ('11:00')")
    ] = None
    check_in_method: Annotated[
        str | None,
        Field(description="입주 방식 ('비대면', '임대인 대면', '키박스')")
    ] = None
    check_out_method: Annotated[
        str | None,
        Field(description="퇴실 방식 ('비대면', '임대인 대면', '키박스')")
    ] = None
    unavailable_periods: Annotated[
        list[ZigbangStayUnavailablePeriod] | None,
        Field(description='예약할 수 없는 기간 (예약됐거나 임대인이 막은 날, 직방이 1년 뒤까지 준다). 없으면 [], 직방이 일정을 주지 않으면 null')
    ] = None

    available: Annotated[
        bool | None,
        Field(description=(
            '입주일·마지막 날을 줬을 때 그 기간을 예약할 수 있는지. 직방 웹 날짜 고르기 창 규칙 그대로, 입주일이 오늘 이후이고 '
            '기간이 최소 계약 주(min_contract_weeks) 이상·84일 이하이며, 입주일부터 마지막 날 전날까지 예약된·막힌 날이 없고 '
            '마지막 날이 막힌 날이 아니면 true. 직방이 일정을 주지 않으면 null'
        ))
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}
        # 날짜를 주지 않은 조회에는 예약 가능 여부가 해당 없다. 날짜를 주면 get_stay_listing 이 모를 때(None)도 값을
        # 넣어(model_copy) model_fields_set 에 든다
        if 'available' not in self.model_fields_set:
            fields = fields | {'available'}
        # 주차 불가면 대수·방식이, 반려동물 동반 불가이면서 추가 청소비가 없거나 0 이면 그 청소비가 해당 없다.
        # stay_detail_to_listing 이 해당 없으면 값을 넣지 않아 model_fields_set 에 들지 않는다 (모를 때는 None 을 넣어 든다)
        return fields | {
            name for name in ('parking_count', 'parking_method', 'pet_cleaning_fee_manwon')
            if name not in self.model_fields_set
        }


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
        list[ZigbangStayListing],
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
    return f'{format_manwon(won_to_manwon(amount_won) or 0)}만원'


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
        weekly_rent_manwon=won_to_manwon(summary.weekly_rent),
        weekly_manage_cost_manwon=won_to_manwon(summary.weekly_manage_cost),
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
    """주차 가능 여부를 직방 웹 표기로 바꾼다 (LIMITED 는 '제한적 가능', 2026-11-17 번들).

    요금(FREE 무료·PAID 유료)은 웹 상세(`AdditionalInfoSection`)처럼 가능(AVAILABLE)·제한적 가능(LIMITED) 둘 다에 붙인다.
    모르는 코드는 그대로 낸다.
    """
    if detail.parking_type is None:
        return None
    available = {'AVAILABLE': '가능', 'LIMITED': '제한적 가능', 'UNAVAILABLE': '불가'}.get(
        detail.parking_type, detail.parking_type,
    )
    fee = {'PAID': '유료', 'FREE': '무료'}.get(detail.parking_fee or '')
    return f'{available} ({fee})' if fee and detail.parking_type in ('AVAILABLE', 'LIMITED') else available


def stay_refund_rules(refund_policy: str | None) -> list[ZigbangStayRefundRule] | None:
    """정책 코드의 위약금 표. 코드가 없거나 표에 없으면 None (웹은 표준 표를 보여 주지만 모르는 정책을 표준이라고 단정하지 않는다)."""
    rules = STAY_REFUND_RULES.get(refund_policy or '')
    return None if rules is None else [ZigbangStayRefundRule(when=when, penalty=penalty) for when, penalty in rules]


def stay_unavailable_periods(schedules: list[ZigbangStayScheduleModel] | None) -> list[ZigbangStayUnavailablePeriod] | None:
    """웹 달력이 막는 일정(예약·막힘)을 기간으로. 일정이 없으면 [], 직방이 일정을 주지 않았으면 None.

    날짜가 없거나 틀렸거나 끝날이 첫날보다 앞인 일정은 웹처럼 아무 날도 막지 않아 뺀다 (`_schedule_dates`). 날짜는 `date` 로 읽은 값의 YYYY-MM-DD 로 낸다.
    """
    if schedules is None:
        return None
    periods = []
    for schedule in schedules:
        if schedule.schedule_type not in STAY_UNAVAILABLE_SCHEDULES or (covered := _schedule_dates(schedule)) is None:
            continue
        first, last = covered
        periods.append(ZigbangStayUnavailablePeriod(
            start=first.isoformat(),
            end=last.isoformat(),
            kind=STAY_SCHEDULE_KIND_LABELS.get(schedule.schedule_type or '', schedule.schedule_type or ''),
        ))
    return periods


def _stay_label(labels: dict[str, str], raw: str | None) -> str | None:
    """직방 코드를 한국어 이름으로 바꾼다. 빈 글자는 모름(None), 표에 없는 코드는 원래 코드를 그대로 낸다."""
    code = text_or_none(raw)
    return labels.get(code, code) if code else None


def stay_detail_to_listing(
    detail: ZigbangGuestItemsResponseModel,
    registered_at: str | None = None,
) -> ZigbangStayListingDetail:
    """단기임대 상세를 `ZigbangStayListingDetail` 로 바꾼다. 사진·본문·호스트 정보는 옮기지 않는다.

    웹 옵션 목록은 반려동물 분류(PET_FRIENDLY)를 빼고 세고 '반려동물 동반 가능/불가' 로 따로 보여 주므로, `options` 에서
    빼고 `pet_allowed` 로 옮긴다 (직방이 옵션 목록 `itemOptions` 를 주지 않았으면 모름 None). 주차 불가의 대수·방식은 해당
    없어 값을 넣지 않는다. 추가 청소비는 웹이 동반 가능 여부와 상관없이 0 보다 크면 보여 주므로, 동반 가능이면 직방 값(0 이면
    0), 동반 불가·모름이면 0 보다 클 때 그 값을 내고 아니면 동반 불가는 값을 넣지 않고(`not_applicable_fields` 가 키를 뺀다)
    모름은 None 을 넣는다.
    """
    manage_cost = 0.0 if detail.is_weekly_manage_cost_absent else won_to_manwon(detail.weekly_manage_cost)
    includes = detail.manage_cost_includes
    # 리뷰 오탐 (2026-11-17): optionName 은 보지 않는다. 직방 웹(AdditionalInfoSection·OptionSection)도 category 만 본다
    pet_allowed = (
        None if sent_or_none(detail, 'item_options', []) is None
        else any(option.category == 'PET_FRIENDLY' for option in detail.item_options)
    )
    conditional: dict[str, Any] = {}
    if detail.parking_type != 'UNAVAILABLE':
        conditional['parking_count'] = detail.parking_count
        conditional['parking_method'] = _stay_label(STAY_PARKING_METHOD_LABELS, detail.parking_method)
    pet_cleaning_fee = won_to_manwon(detail.pet_cleaning_fee)
    if pet_allowed or (pet_cleaning_fee is not None and pet_cleaning_fee > 0):
        conditional['pet_cleaning_fee_manwon'] = pet_cleaning_fee
    elif pet_allowed is None:
        conditional['pet_cleaning_fee_manwon'] = None
    return ZigbangStayListingDetail(
        source='zigbang',
        id=f'stay-{detail.id}',
        url=stay_item_url(detail.id),
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
        options=sent_or_none(
            detail, 'item_options',
            [
                STAY_OPTION_LABELS.get(option.option_name, option.option_name)
                for option in detail.item_options if option.category != 'PET_FRIENDLY'
            ],
        ),
        manage_cost_includes=None if includes is None else [
            {'gas': '가스', 'water': '수도', 'electricity': '전기'}.get(key, key)
            for key, included in includes.items() if included
        ],
        nearby_subways=sent_or_none(detail, 'nearby_stations', [
            f'{station.name} ({station.description})' if station.description else station.name
            for station in detail.nearby_stations
        ]),
        weekly_rent_manwon=won_to_manwon(detail.weekly_rent),
        weekly_manage_cost_manwon=manage_cost,
        cleaning_fee_manwon=0.0 if detail.cleaning_fee_free else won_to_manwon(detail.cleaning_fee),
        discounts=sent_or_none(detail, 'discounts', stay_discounts(detail.discounts, detail.weekly_rent)),
        min_contract_weeks=detail.min_contract_weeks,
        max_contract_weeks=detail.max_contract_weeks,
        max_guests=detail.max_guests,
        duplex=detail.is_duplex,
        refund_policy=_stay_label(STAY_REFUND_POLICY_LABELS, detail.refund_policy),
        refund_rules=stay_refund_rules(detail.refund_policy),
        kitchen_count=detail.kitchen_count,
        living_room_count=detail.living_room_count,
        pet_allowed=pet_allowed,
        check_in_time=text_or_none(detail.checkin_time),
        check_out_time=text_or_none(detail.checkout_time),
        check_in_method=_stay_label(STAY_CHECK_METHOD_LABELS, detail.checkin_method),
        check_out_method=_stay_label(STAY_CHECK_METHOD_LABELS, detail.checkout_method),
        unavailable_periods=stay_unavailable_periods(detail.schedules),
        **conditional,
    )


class ZigbangStayPeriod(RequestModel):
    """단기임대 상세에 준 입주일·마지막 날 (listing stay-… --check-in/--check-out). 서버에 보내지 않고 예약 가능 여부만 따진다."""

    check_in: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='입주일 (YYYY-MM-DD)')
    ]
    check_out: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='마지막으로 머무는 날 (YYYY-MM-DD)')
    ]

    @model_validator(mode='after')
    def valid_dates(self) -> Self:
        validate_stay_dates(self.check_in, self.check_out)
        return self


def get_stay_listing(
    client: ZigbangClient,
    item_id: int,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
) -> ZigbangStayListingDetail:
    """단기임대 매물 하나의 상세를 조회한다 (상세 + 노출 시작일용 요약, 2회 호출).

    입주일·마지막 날(`check_in`·`check_out`)을 주면 상세의 일정(`schedules`)으로 그 기간을 예약할 수 있는지(`available`)를
    웹 날짜 고르기 창 규칙대로 붙인다 (`stay_range_available`, 요청이 늘지 않는다). 그 기간의 총비용은 웹이 로그인했을 때만
    요금 계산(`price-calculation`)을 불러 보여 주어 내지 않는다 (2026-11-15 웹: 로그인하지 않으면 날짜를 골라도 주당 금액만).

    Raises:
        ValidationError: 없는 날짜이거나 지난 입주일이거나 마지막 날이 입주일보다 뒤가 아닐 때 (요청 전에, CLI 는 INVALID_ARGUMENT).
        ListingUnavailableError: 없는 매물(404)이거나 노출 중이 아니거나 검수가 끝나지 않았을 때.
    """
    period = None if check_in is None or check_out is None else ZigbangStayPeriod(check_in=check_in, check_out=check_out)
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
    if period is None:
        return listing
    available = None if detail.schedules is None else stay_range_available(
        detail.schedules, detail.min_contract_weeks, period.check_in, period.check_out, datetime.now(KST).date(),
    )
    return listing.model_copy(update={'available': available})


def stay_range_available(
    schedules: list[ZigbangStayScheduleModel],
    min_contract_weeks: int | None,
    check_in: str,
    check_out: str,
    today: date,
) -> bool:
    """입주일~마지막 날(`check_out`)을 예약할 수 있는지. 웹 날짜 고르기 창 규칙 그대로다 (번들 `resolveScheduleAutofill` 의
    `isRangeAvailable`, 일정 유연성 0).

    입주일이 오늘보다 앞이거나, 두 날짜 사이 일수가 최소 계약 주 × 7 − 1 보다 적거나(최소 계약 주가 없으면 1주, 1일보다 적게
    보지 않는다), 마지막 날이 입주일 + 83일보다 뒤면 불가다. 그 밖에는 예약된·막힌 일정이 덮는 날(시작·끝 날 포함,
    `generateDateRange`)에 입주일~마지막 날 전날이 하루라도 들거나, 마지막 날이 막힌(BLOCKED) 날이면 불가다
    (`isStayRangeFreeOfOccupancy`). 날짜가 없거나 틀린 일정은 웹처럼 아무 날도 덮지 않는다.
    """
    start = date.fromisoformat(check_in)
    end = date.fromisoformat(check_out)
    weeks = 1 if min_contract_weeks is None else min_contract_weeks
    if start < today or (end - start).days < max(1, 7 * weeks - 1) or end > start + timedelta(days=STAY_MAX_CHECK_OUT_DAYS):
        return False
    last_night = end - timedelta(days=1)
    for schedule in schedules:
        if schedule.schedule_type not in STAY_UNAVAILABLE_SCHEDULES or (covered := _schedule_dates(schedule)) is None:
            continue
        first, last = covered
        if first <= last_night and last >= start:
            return False
        if schedule.schedule_type == 'BLOCKED' and first <= end <= last:
            return False
    return True


def _schedule_dates(schedule: ZigbangStayScheduleModel) -> tuple[date, date] | None:
    """일정이 덮는 첫날·끝날. 날짜가 없거나 틀렸거나 끝날이 첫날보다 앞이면 웹(`generateDateRange`)처럼 덮는 날이 없어 None."""
    try:
        first = date.fromisoformat(schedule.start_date or '')
        last = date.fromisoformat(schedule.end_date or '')
    except ValueError:
        return None
    return (first, last) if first <= last else None


# 날짜를 준 검색의 금액·가격순이 기간 비용이 아니라는 안내. 2026-10-31 에이전트 검증: 강남역 4주 가격순 1위를 주당 32만 × 4 =
# 128만으로 답했지만 청소비·이용료를 더한 실제 결제는 151만 2천이었고, 주당 요금 3위는 기간 비용으로 4위였다. 기간 비용은
# 웹이 로그인했을 때만 계산해 보여 주어(2026-11-15) jibsa 는 내지 않는다
STAY_WEEKLY_PRICE_NOTE: str = note(
    '참고',
    '목록 금액과 가격순은 주당 임대료+관리비 기준이라 청소비·직방 이용료·장기 할인이 빠져 있습니다. 그 기간에 실제로 내는 돈은 '
    '직방에 로그인해야 계산해 보여 줘서 jibsa 는 주지 않습니다. 청소비·보증금·할인 조건은 listing stay-… 상세에서 보세요',
)


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
