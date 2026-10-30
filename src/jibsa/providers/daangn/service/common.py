"""당근 service 공통: GraphQL 응답 풀기, 여러 모듈이 쓰는 결과 모델·매물 변환·안내 문구·상수."""

from collections.abc import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    UPDATE_MAYBE_NEEDED,
    UPDATE_NEEDED,
    Listing,
    in_range,
    join_address,
    m2_to_pyeong,
    normalize_date,
    note,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnAmountRangeModel,
    DaangnBuildingApprovalDate,
    DaangnComplexType,
    DaangnDealType,
    DaangnFloor,
    DaangnOption,
    DaangnPropertyFilterModel,
    DaangnRoomCount,
    DaangnSalesType,
    DaangnSubSalesType,
    DaangnTradeType,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnGraphQLResponseModel,
    DaangnRegionComplexNodeModel,
    DaangnTradeModel,
)

from typing import (
    Annotated,
    Any,
    TypeVar,
)


PROPERTY_TYPE_BY_SALES_TYPE: dict[str, str] = {
    'APART': '아파트',
    'OFFICETEL': '오피스텔',
    'OPEN_ONE_ROOM': '원룸',
    'SPLIT_ONE_ROOM': '원룸',
    'TWO_ROOM': '투룸',
    'HOUSE': '주택',
    'STORE': '상가',
    'OFFICE': '사무실',
    'BUILDING': '건물',
    'LAND': '토지',
    'FACTORY': '공장·창고',
}
# 당근 TWO_ROOM 은 '투룸 이상'이라 쓰리룸·포룸도 들어 있다. 방 구조는 방 수로만 알 수 있는데
# 지도 피드(목록)에는 방 수가 없어 목록은 원룸 구조만, 상세는 방 수로 정한다 (`room_type_of`).
ROOM_TYPE_BY_SALES_TYPE: dict[str, str] = {
    'OPEN_ONE_ROOM': '오픈형원룸',
    'SPLIT_ONE_ROOM': '분리형원룸',
}
# 단지 건물에 있는지 알릴 원룸·투룸 카테고리 (`complex_building_notes`)
ROOM_SALES_TYPES: frozenset[str] = frozenset({'OPEN_ONE_ROOM', 'SPLIT_ONE_ROOM', 'TWO_ROOM'})
PROPERTY_TYPES: tuple[str, ...] = ('아파트', '오피스텔', '원룸', '투룸', '주택', '상가', '사무실', '건물', '토지', '공장·창고')
TRADE_TYPE_BY_TRADE: dict[str, str] = {
    'MONTH': '월세',
    'BORROW': '전세',
    'BUY': '매매',
    # 단기임대 (ShortTrade). 월세처럼 보증금·월세가 있다.
    'SHORT': '단기임대',
}
TRADE_TYPES: tuple[str, ...] = ('매매', '전세', '월세', '단기임대')
# 필터로 보내는 매물 종류. 원룸(ONE_ROOM)은 오픈형·분리형 원룸을 함께 찾는다
SALES_TYPE_BY_PROPERTY_TYPE: dict[str, DaangnSalesType] = {
    '아파트': 'APART',
    '오피스텔': 'OFFICETEL',
    '원룸': 'ONE_ROOM',
    '투룸': 'TWO_ROOM',
    '주택': 'HOUSE',
    '상가': 'STORE',
    '사무실': 'OFFICE',
    '건물': 'BUILDING',
    '토지': 'LAND',
    '공장·창고': 'FACTORY',
}
TRADE_FILTER_BY_TRADE_TYPE: dict[str, DaangnTradeType] = {
    '월세': 'MONTH',
    '전세': 'BORROW',
    '매매': 'BUY',
    '단기임대': 'SHORT',
}
# 아래 필터 라벨은 당근 웹 지도 필터의 이름 그대로다 (띄어쓰기만 뺐다)
FLOOR_FILTER_BY_LABEL: dict[str, DaangnFloor] = {
    '반지하': 'SEMI_BASEMENT',
    '1층': 'FIRST',
    '2~5층': 'SECOND_TO_FIFTH',
    '6~9층': 'SIX_TO_NINTH',
    '10층이상': 'TENTH_OR_MORE',
}
ROOM_COUNT_FILTER_BY_LABEL: dict[str, DaangnRoomCount] = {
    '2개': 'TWO',
    '3개': 'THREE',
    '4개이상': 'FOUR_OR_MORE',
}
STRUCTURE_FILTER_BY_LABEL: dict[str, DaangnSubSalesType] = {
    '오픈형': 'OPEN_ROOM',
    '분리형': 'SPLIT_ROOM',
}
BUILDING_APPROVAL_FILTER_BY_LABEL: dict[str, DaangnBuildingApprovalDate] = {
    '5년이내': 'LESS_5YEARS',
    '10년이내': 'LESS_10YEARS',
    '15년이내': 'LESS_15YEARS',
    '20년이내': 'LESS_20YEARS',
    '25년이내': 'LESS_25YEARS',
    '30년이내': 'LESS_30YEARS',
    '30년이상': 'MORE_30YEARS',
}
DEAL_FILTER_BY_LABEL: dict[str, DaangnDealType] = {
    '직거래': 'DIRECT',
    '중개': 'BROKER',
}
OPTION_FILTER_BY_LABEL: dict[str, DaangnOption] = {
    '주차가능': 'PARKING',
    '반려동물가능': 'PET',
    '대출가능': 'MORTGAGE',
    '엘리베이터': 'ELEVATOR',
    '옥탑': 'ROOFTOP',
    '복층': 'LOFT',
}
# 웹이 쿼리를 바꿔 해시가 목록에서 빠졌을 때의 에러 코드
PERSISTED_QUERY_REJECTED_CODES: frozenset[str] = frozenset({'PERSISTED_QUERY_NOT_IN_LIST', 'PERSISTED_QUERY_NOT_FOUND'})
# 월세가 있는 거래 조건
MONTHLY_TRADES: frozenset[str] = frozenset({'MONTH', 'SHORT'})
# 층을 숫자 대신 밝힌 값 (당근 웹 표기)
AMBIGUOUS_FLOOR_LABELS: dict[str, str] = {
    'LOW': '저층',
    'MIDDLE': '중층',
    'HIGH': '고층',
}
# 단지 유형 (당근 웹 표기)
COMPLEX_TYPE_LABELS: dict[str, str] = {
    'APARTMENT': '아파트',
    'OFFICETEL': '오피스텔',
    'MIXED_USE': '주상복합',
    'LIVING_ACCOMMODATION': '생활숙박시설',
    'REDEVELOPMENT': '재개발',
}
# 실거래가 거래 유형 (당근은 매매와 전월세를 나눠 주고, 전월세는 type 으로 가른다)
REAL_PRICE_TRADE_TYPES: tuple[str, ...] = ('매매', '전세', '월세')
# 매물 목록(search listings)의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`listing_budget_notes`)가 함께 쓴다
LISTING_MAX_LIMIT: int = 120
# 역당 매물 수 상한 (CLI --limit 최대). 100건씩 페이지를 넘겨 받는다. 역마다 같은 상한 안내(`listing_budget_notes`)를 붙여서
# 매물 목록 상한과 같아야 한다
COMMUTE_STATION_MAX_LIMIT: int = LISTING_MAX_LIMIT
# 단지 목록(search complexes, search locations 의 단지 후보, school 의 배정 단지)의 --limit 최대값.
# CLI 옵션의 max 와 `list_region_complexes`·`search_complexes`·`get_school` 의 상한 안내가 함께 쓴다
COMPLEX_LIST_MAX_LIMIT: int = 1200
# 지역 단지 목록 (웹 지도 단지 탭): 단지 유형·거래 유형·정렬 라벨 → 당근 값
COMPLEX_TYPE_FILTER_BY_LABEL: dict[str, DaangnComplexType] = {'아파트': 'APARTMENT', '오피스텔': 'OFFICETEL'}
# 단지마다 보여 줄 최근 실거래 수 (당근은 10건을 준다)
COMPLEX_RECENT_TRADES: int = 3
PRICE_TREND_MAX_YEARS: int = 15


class DaangnRegion(BaseModel):
    """조회한 동."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name1: Annotated[
        str,
        Field(description='시/도')
    ]
    name2: Annotated[
        str,
        Field(description='시/군/구. 세종처럼 없으면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    name3: Annotated[
        str,
        Field(description='읍/면/동')
    ]
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]

    @model_serializer(mode='wrap')
    def drop_missing_district(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 세종은 시·군·구가 없어 당근이 name2 를 '' 로 준다 (해당 없음). 이어 받기 표에서 다시 읽을 때는 기본값 '' 로 돌아온다
        if not self.name2:
            data.pop('name2', None)
        return data


class FeedQueryRejectedError(JibsaError):
    """GraphQL 이 persisted query 해시를 거절했을 때. 웹이 쿼리를 바꿨다는 신호다.

    대체 경로가 있는 곳(동 검색의 지도 페이지, 단지 후보 등)은 이 예외를 먼저 잡아 처리하고,
    따로 처리하지 않은 명령은 `JibsaError` 라 `UPSTREAM_ERROR` 로 나간다.

    Args:
        codes: GraphQL 이 준 에러 코드 (예: PERSISTED_QUERY_NOT_IN_LIST).
        what: 에러 메시지에 쓸 조회 이름 (예: '매물 피드'). Defaults to '조회'.
    """

    def __init__(self, codes: str, what: str = '조회') -> None:
        super().__init__(
            code='UPSTREAM_ERROR',
            message=f'당근 {what} API 가 바뀌어(웹 쿼리 해시 거절) 조회할 수 없습니다 ({codes})',
            hint='jibsa 업데이트가 필요합니다. 그동안 다른 소스(직방·네이버)를 쓰세요',
        )


def is_available(article: DaangnArticleModel) -> bool:
    """거래 가능한 매물인지. 진행 중(ON_GOING)이고 숨김·노출 제한이 없어야 한다.

    노출 제한은 SSR 스토어에는 `invisibleReason`, GraphQL 피드에는 `invisibleInfos` 로 온다.
    """
    return (
        article.status == 'ON_GOING'
        and not article.is_hide
        and article.invisible_reason is None
        and not article.invisible_infos
    )


def article_url(original_id: str | int) -> str:
    return f'https://realty.daangn.com/articles/{original_id}'


def trades_preferred_first(article: DaangnArticleModel) -> list[DaangnTradeModel]:
    known = [trade for trade in article.trades if trade.type in TRADE_TYPE_BY_TRADE]
    return sorted(known, key=lambda trade: not trade.preferred)


def _preferred_trade(article: DaangnArticleModel) -> DaangnTradeModel | None:
    trades = trades_preferred_first(article)
    return trades[0] if trades else None


def floor_of(article: DaangnArticleModel) -> str | None:
    """해당 층. 작성자가 층을 저층·중층·고층으로만 밝혔으면(숫자 층은 비어 있다) 그 표기를 쓴다."""
    if article.is_ambiguous_floor and article.ambiguous_floor:
        return AMBIGUOUS_FLOOR_LABELS.get(article.ambiguous_floor, article.ambiguous_floor)
    return article.floor


def property_type_of(article: DaangnArticleModel) -> str:
    sales_type = article.sales_type.type if article.sales_type else 'UNKNOWN'
    return PROPERTY_TYPE_BY_SALES_TYPE.get(sales_type, sales_type)


def room_type_of(article: DaangnArticleModel) -> str | None:
    """방 구조. 방 수를 알면(상세) 유형과 상관없이 방 수로 투룸·쓰리룸·포룸이상을 가리고,
    방 1개거나 방 수를 모르면(목록) 원룸 구조(오픈형·분리형)를 쓴다. 그 밖은 None.

    원룸 카테고리에도 방 2개 매물이 있어 방 수를 먼저 본다 (2026-10-10 실측: 분리형원룸으로 올린 방 2개 매물).
    """
    count = article.room_count
    if count is not None and count >= 2:
        if count == 2:
            return '투룸'
        if count == 3:
            return '쓰리룸'
        return '포룸이상'
    sales_type = article.sales_type.type if article.sales_type else None
    return ROOM_TYPE_BY_SALES_TYPE.get(sales_type or '')


class DaangnNearbyListing(Listing):
    """검색 중심(동 중심·역·반경 중심·회사)에서 거리를 재는 당근 매물. 거리를 모르면 키를 빼지 않고 null(모름)로 낸다.

    공통 `Listing` 은 `distance_km` 가 None 이면 중심 없는 조회로 보고 키를 뺀다 (해당 없음). 중심이 있는데 매물 위치를
    모르면(주소를 숨긴 매물, `article_to_listing`) 해당 없음이 아니라 모름이다.
    """

    def not_applicable_fields(self) -> frozenset[str]:
        return super().not_applicable_fields() - {'distance_km'}


def article_to_listing(
    article: DaangnArticleModel,
    center: tuple[float, float] | None = None,
    fallback_title: str | None = None,
    trade: DaangnTradeModel | None = None,
) -> Listing | None:
    """Article 하나를 공통 `Listing` 으로 바꾼다. 거래 조건이 없으면 None.

    `trade` 를 주지 않으면 대표(preferred) 조건을 쓴다. 금액은 원래 만원 단위다.
    제목은 목록과 상세가 같도록 작성자 소개(`addressInfo`) → 건물 이름 →
    `fallback_title`(상세 페이지의 자동 요약) 순으로 고른다. `center` 를 주면 거리를 재고
    `DaangnNearbyListing` 으로 준다 (거리를 모르면 null).
    """
    trade = trade or _preferred_trade(article)
    if trade is None:
        return None

    # 주소를 숨긴 매물(isHideAddress)의 공개 좌표는 실제 위치가 아니어서 거리를 재지 않는다 (null, `hidden_location_notes`).
    # 2026-10-28 실측: 강남역 역 주변 100건 중 숨긴 18건은 역까지 도보 1~6분인데 공개 좌표가 역에서 0.35~1.78km, 숨기지 않은
    # 82건은 모두 0.21km 안 (출퇴근 역별 매물 100건도 같은 18:82). 숨긴 매물은 지도 핀에 없고 상세 주소도 동까지만 온다
    coordinate = None if article.is_hide_address else article.public_coordinate
    lat = coordinate.lat if coordinate else None
    lng = coordinate.lon if coordinate else None
    distance = None
    if center is not None and lat is not None and lng is not None:
        distance = round(haversine_km(center[0], center[1], lat, lng), 2)

    region = article.region
    address = article.public_jibun_address
    if address is None and region is not None:
        address = join_address(region.name1, region.name2, region.name3)

    model = Listing if center is None else DaangnNearbyListing
    return model(
        source='daangn',
        id=article.original_id,
        url=article_url(article.original_id),
        trade_type=TRADE_TYPE_BY_TRADE[trade.type],
        property_type=property_type_of(article),
        room_type=room_type_of(article),
        title=article.address_info or article.building_name or fallback_title or None,
        price_manwon=trade.price if trade.type == 'BUY' else None,
        deposit_manwon=trade.deposit if trade.type != 'BUY' else None,
        rent_manwon=trade.monthly_pay if trade.type in MONTHLY_TRADES else None,
        manage_cost_manwon=article.total_manage_cost,
        area_m2=article.area,
        area_pyeong=m2_to_pyeong(article.area),
        floor=floor_of(article),
        building_floor=article.top_floor,
        address=address,
        lat=lat,
        lng=lng,
        distance_km=distance,
        # 지도 피드(목록)에는 날짜 필드가 아예 없어 search 결과는 None 이다. 등록일은
        # 상세 페이지에만 있다. 매물마다 상세를 더 조회하면 동마다 최대 20회 요청이
        # 늘어(약 10초) 목록에서는 채우지 않는다. 필요하면 daangn listing 으로 확인한다.
        registered_at=normalize_date(article.published_at),
        # 사용승인일도 상세 페이지에만 있어 목록에서는 None 이다.
        approved_at=normalize_date(article.building_approval_date),
    )


def _matches(
    listing: Listing,
    property_types: list[str] | None,
    trade_types: list[str] | None,
    deposit: tuple[int | None, int | None],
    rent: tuple[int | None, int | None],
    price: tuple[int | None, int | None],
    area: tuple[float | None, float | None] = (None, None),
) -> bool:
    if property_types and listing.property_type not in property_types:
        return False
    if trade_types and listing.trade_type not in trade_types:
        return False
    if listing.deposit_manwon is not None or listing.trade_type != '매매':
        if not in_range(listing.deposit_manwon, *deposit):
            return False
    if listing.trade_type in ('월세', '단기임대') and not in_range(listing.rent_manwon, *rent):
        return False
    if listing.trade_type == '매매' and not in_range(listing.price_manwon, *price):
        return False
    return in_range(listing.area_m2, *area)


def _matching_trade(
    article: DaangnArticleModel,
    center: tuple[float, float] | None,
    *,
    property_types: list[str] | None,
    trade_types: list[str] | None,
    deposit: tuple[int | None, int | None],
    rent: tuple[int | None, int | None],
    price: tuple[int | None, int | None],
    area: tuple[float | None, float | None],
) -> DaangnTradeModel | None:
    """조건을 통과하는 첫 거래 조건. 대표 조건부터 본다.

    거래 조건이 여러 개(예: 매매 + 월세)면 대표 조건만 보면 월세로 찾을 때 빠진다.
    서버가 거른 매물도 어느 거래 조건이 맞았는지는 알려 주지 않아 다시 본다.

    거래마다 `Listing` 을 만들어 비교하는 건 금액·면적·관리비 정규화를 `article_to_listing` 한 곳에 두기 위해서다.
    비용은 무시할 만하다 (2026-10-11 실측: 역삼역 120건 검색 1.58초 중 0.011초, 0.7%. 나머지는 네트워크).
    """
    for trade in trades_preferred_first(article):
        listing = article_to_listing(article, center, trade=trade)
        if listing is not None and _matches(listing, property_types, trade_types, deposit, rent, price, area):
            return trade
    return None


def amount_range(low: int | None, high: int | None) -> DaangnAmountRangeModel | None:
    if low is None and high is None:
        return None
    return DaangnAmountRangeModel(min_amount=low, max_amount=high)


def label_codes(labels: list[str] | None, codes: Mapping[str, str]) -> list[str] | None:
    return [codes[label] for label in labels] if labels else None


class DaangnListingConditions(RequestModel):
    """매물 검색 조건 (한국어 라벨). 당근 웹 지도 필터(`property_filter`)와 받은 매물의 거래 조건 고르기
    (`trade_of`)에 같이 쓴다. 매물 검색 명령은 모두 이 묶음을 넘긴다.

    라벨은 `PROPERTY_TYPES`·`TRADE_TYPES` 와 `*_FILTER_BY_LABEL` 의 키다. 만들 때 필터로 바꿔 보아
    조건 조합이 잘못됐으면 요청을 보내기 전에 멈춘다.

    Raises:
        ValidationError: 원룸이 아닌데 방 구조를, 아파트만이 아닌데 세대수·주차대수를 줬을 때.
    """

    property_types: Annotated[
        list[str] | None,
        Field(description='매물 종류 (PROPERTY_TYPES)')
    ] = None
    trade_types: Annotated[
        list[str] | None,
        Field(description='거래 유형 (TRADE_TYPES)')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    rent_includes_manage_cost: Annotated[
        bool,
        Field(description='월세 범위를 월세 + 관리비로 비교')
    ] = False
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    floors: Annotated[
        list[str] | None,
        Field(description='층 (FLOOR_FILTER_BY_LABEL)')
    ] = None
    room_counts: Annotated[
        list[str] | None,
        Field(description='방 개수 (ROOM_COUNT_FILTER_BY_LABEL)')
    ] = None
    structures: Annotated[
        list[str] | None,
        Field(description='원룸 방 구조 (STRUCTURE_FILTER_BY_LABEL)')
    ] = None
    building_approval: Annotated[
        str | None,
        Field(description='사용승인일 (BUILDING_APPROVAL_FILTER_BY_LABEL)')
    ] = None
    deal: Annotated[
        str | None,
        Field(description='거래 방식 (DEAL_FILTER_BY_LABEL)')
    ] = None
    options: Annotated[
        list[str] | None,
        Field(description='옵션 (OPTION_FILTER_BY_LABEL)')
    ] = None
    move_in_now: Annotated[
        bool,
        Field(description='즉시 입주')
    ] = False
    household_min: Annotated[
        int | None,
        Field(description='세대수 하한 (아파트만)')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한 (아파트만)')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한 (아파트만)')
    ] = None

    _property_filter: DaangnPropertyFilterModel = PrivateAttr()

    def model_post_init(self, context: Any) -> None:
        self._property_filter = property_filter_of(self)

    @property
    def property_filter(self) -> DaangnPropertyFilterModel:
        """당근 웹 지도 필터 (`propertyFilter`). 조건이 없으면 빈 필터다."""
        return self._property_filter


def property_filter_of(conditions: DaangnListingConditions) -> DaangnPropertyFilterModel:
    """한국어 라벨 조건을 당근 웹 지도 필터(`propertyFilter`)로 바꾼다.

    Raises:
        ValidationError: 원룸이 아닌데 방 구조를, 아파트만이 아닌데 세대수·주차대수를 줬을 때.
    """
    return DaangnPropertyFilterModel(
        sales_types=label_codes(conditions.property_types, SALES_TYPE_BY_PROPERTY_TYPE) or [],
        trade_types=label_codes(conditions.trade_types, TRADE_FILTER_BY_TRADE_TYPE),
        deposit_pay=amount_range(conditions.deposit_min, conditions.deposit_max),
        monthly_pay=amount_range(conditions.rent_min, conditions.rent_max),
        price_pay=amount_range(conditions.price_min, conditions.price_max),
        monthly_pay_includes_manage_cost=conditions.rent_includes_manage_cost or None,
        min_area=conditions.area_min,
        max_area=conditions.area_max,
        floor=label_codes(conditions.floors, FLOOR_FILTER_BY_LABEL),
        room_counts=label_codes(conditions.room_counts, ROOM_COUNT_FILTER_BY_LABEL),
        sub_sales_types=label_codes(conditions.structures, STRUCTURE_FILTER_BY_LABEL),
        building_approval_date=label_codes(
            [conditions.building_approval] if conditions.building_approval else None,
            BUILDING_APPROVAL_FILTER_BY_LABEL,
        ),
        deal_type=DEAL_FILTER_BY_LABEL[conditions.deal] if conditions.deal else None,
        options=label_codes(conditions.options, OPTION_FILTER_BY_LABEL),
        move_in_now=conditions.move_in_now or None,
        min_household_count=conditions.household_min,
        max_household_count=conditions.household_max,
        min_parking_per_household=conditions.parking_min,
    )


def trade_of(
    article: DaangnArticleModel,
    center: tuple[float, float] | None,
    conditions: DaangnListingConditions,
    *,
    server: bool = True,
) -> DaangnTradeModel | None:
    """검색 조건에 맞는 첫 거래 조건 (`_matching_trade`).

    `server` 면 당근 서버가 이 조건으로 거른 매물이다. 유형과 면적은 서버에 맡긴다 (면적은 서버가 유형마다
    다른 면적(공급·대지)으로 볼 수 있다). 관리비 포함 월세의 하한도 서버에 맡기고, 월세 자체가 총액 상한을
    넘는 조건만 뺀다. 아니면(조건 없는 지도 페이지) 유형·거래·금액·면적을 직접 확인한다.
    """
    return _matching_trade(
        article,
        center,
        property_types=None if server else conditions.property_types,
        trade_types=conditions.trade_types,
        deposit=(conditions.deposit_min, conditions.deposit_max),
        rent=(
            (None, conditions.rent_max) if conditions.rent_includes_manage_cost and server
            else (conditions.rent_min, conditions.rent_max)
        ),
        price=(conditions.price_min, conditions.price_max),
        area=(None, None) if server else (conditions.area_min, conditions.area_max),
    )


T = TypeVar('T')


def unwrap_graphql(response: DaangnGraphQLResponseModel, value: T | None, what: str) -> T:
    """GraphQL 응답에서 결과(`value`, 응답의 `data` 에서 꺼낸 값)를 꺼낸다.

    Args:
        response: GraphQL 응답.
        value: `response.data` 에서 꺼낸 결과. 없으면 None.
        what: 에러 메시지에 쓸 조회 이름 (예: '매물 피드').

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR). 잘못된 조건 조합도 이유 없이 여기로 온다.
    """
    codes = {(error.extensions or {}).get('code') for error in response.errors}
    if codes & PERSISTED_QUERY_REJECTED_CODES:
        raise FeedQueryRejectedError(', '.join(sorted(code for code in codes if code)), what)
    if response.errors or value is None:
        message = next((error.message for error in response.errors if error.message), None)
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'당근 {what} 조회가 실패했습니다' + (f': {message}' if message else ''),
            hint='조건을 줄여(층·방 개수·사용승인일 등) 다시 시도하거나, 잠시 뒤 다시 시도하세요',
        )
    return value


# 덤 조회(매물 수·시·도·좌표의 동·단지 후보·후기 수)와 대체 경로가 있는 조회(역 검색·위치 찾기)가 잡는 실패.
# 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`: HTTPError, 응답 형식 변경의 ValueError)에 JibsaError(해시 거절·GraphQL
# 에러·요청 제한)를 더한다. 요청 제한을 바로 올릴 곳은 이보다 먼저 잡는다.
# 전에는 ValueError 를 잡지 않아 덤 조회 하나가 차단 페이지를 받으면 모아 둔 매물(최대 120건)까지 잃고 PARSE_ERROR 로
# 끝났다. 2026-10-11 사용자 결정으로 결과는 돌려주고 `notes` 로 알린다 (주된 조회는 그대로 PARSE_ERROR).
# 걸리는 다른 경우도 결과는 맞다 (2026-10-11 실측):
# - 공백 검색어(' ')는 위치 찾기 요청 모델의 ValidationError 가 잡혀 직방으로 넘어가 REGION_NOT_FOUND 로 끝난다.
#   직방·네이버도 같은 입력에 REGION_NOT_FOUND 를 낸다.
# - 상태 폴더 오류(StateDirError, JibsaError)도 잡히지만 다음 요청(직방 넘김 포함)이 같은 이유로 실패해 결국 그 에러와
#   '다른 소스로 다시 시도하지 마세요' 힌트로 끝난다 (쓰기 막힌 폴더에서 daangn search listings 강남역 --radius 1)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, JibsaError)


def partial_failure_note(exc: Exception, what: str, missing: str) -> str:
    """덤으로 받는 조회가 실패했을 때 `notes` 에 붙일 안내. 이미 받은 결과는 버리지 않고 이 안내만 붙인다.

    주된 결과를 받는 조회가 실패하면 쓰지 않고 에러로 끝낸다. 실패 이유마다 다음 행동이 달라
    (업데이트·기다리기·다시 시도) 이유를 문구에 넣는다.

    Args:
        exc: 조회가 낸 예외 (`OPTIONAL_LOOKUP_ERRORS` 중 하나).
        what: 조회 이름 (예: '단지 검색').
        missing: 받지 못한 것, 조사까지 (예: '단지 후보를').
    """
    if isinstance(exc, FeedQueryRejectedError):
        return f'당근 {what} API 가 바뀌어(웹 쿼리 해시 거절) {missing} 받지 못했습니다. {UPDATE_NEEDED}'
    if isinstance(exc, RateLimitedError):
        return f'요청 제한에 걸려 {missing} 받지 못했습니다. {exc.message}'
    if isinstance(exc, JibsaError) and exc.code == 'UPSTREAM_ERROR':
        # unwrap_graphql 의 GraphQL 에러. 서버 5xx 는 HTTPStatusError 로 와서 여기 오지 않는다
        return f'{missing} 받지 못했습니다: {exc.message}. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
    if isinstance(exc, JibsaError):
        return f'{missing} 받지 못했습니다: {exc.message}'
    if isinstance(exc, ValueError):
        return (
            f'당근 {what} 응답이 예상한 형식이 아니라 {missing} 받지 못했습니다. '
            f'차단 페이지이거나 API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
        )
    return f'당근 {what} 요청이 실패해 {missing} 받지 못했습니다 ({type(exc).__name__}). 잠시 뒤 다시 시도하세요'


def truncation_notes(
    received: int,
    limit: int,
    *,
    subject: str = '매물',
    unit: str = '건',
    max_limit: int | None = None,
    narrow: str | None = None,
) -> list[str]:
    """받은 유효 결과를 출력 한도로 자를 때 실제 개수와 다음에 할 일을 알린다.

    `max_limit` 를 주면 `--limit` 이 최대값보다 작을 때 늘리라고, `narrow`(좁힐 옵션)를 주면 좁히라고 덧붙인다.
    `--limit` 이 이미 최대값이면 늘리라는 안내는 옵션 검사에서 막히므로 붙이지 않는다 (2026-10-11 실측: preschools
    강남역 --radius 3 --limit 200 에 205곳). 매물 목록(`listing_budget_notes`)·실거래처럼 `--limit` 안내를 따로 붙이는
    호출부는 `max_limit` 를 넘기지 않는다. 같은 말이 두 번 나온다 (2026-10-11 실측: daangn search listings 역삼동
    --limit 2 에 '검색 범위를 좁혀 주세요' 가 두 번).
    """
    if received <= limit:
        return []
    text = f'조회된 {subject} {received}{unit} 중 --limit {limit} 에 맞춰 {limit}{unit}만 보여드립니다'
    steps = ([f'--limit 을 최대 {max_limit}까지 늘리'] if max_limit is not None and limit < max_limit else []) + (
        [f'{narrow} 로 좁히'] if narrow else []
    )
    if steps:
        text += '. ' + '거나 '.join(steps) + '세요'
    return [note('일부', text)]


def listing_budget_notes(
    limit: int,
    inspected: int,
    returned: int,
    *,
    has_more: bool,
    eligible: int | None = None,
    narrowable: bool = True,
    resumable: bool = False,
    resumed: bool = False,
) -> list[str]:
    """조회한 원본은 제외 여부와 무관하게 예산에 포함한다.

    `has_more` 가 False 면 서버에 더 받을 매물이 없다. 그때 '추가 조회하지 않았다' 고 하면 LLM 이 limit 을
    늘려 다시 조회하므로 끝까지 받았다고 알린다 (2026-10-11 실측: 오산역 매매 limit 120, 55건 반환·has_more false).

    Args:
        narrowable: `--limit`·필터로 더 받을 수 있는지. 피드를 쓸 수 없어 동마다 지도 페이지 20건만 받을 때는
            limit 을 늘리거나 필터를 걸어도 그 20건 안이라 False 로 주어 그 안내를 붙이지 않는다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        resumed: 이어 받기(`--next`)로 앞 결과 다음부터 받았으면 True. 이번 쪽만 센 수를 전부라고 하지 않는다.
    """
    notes: list[str] = []
    excluded = inspected - returned if eligible is None else inspected - eligible + min(eligible, limit) - returned
    if excluded > 0 and returned < limit:
        head = f'{inspected}건을 받아 중복·거래 불가·조건 불일치를 빼고 {returned}건입니다'
        notes.append(note('제외', f'{head} (뺀 만큼 다시 채우지 않음)' if has_more else f'{head} (더 받을 매물 없음)'))
    elif returned < limit and not has_more and resumed:
        # 이어 받은 마지막 쪽에서 '이 N건이 전부' 라고 하면 앞 결과의 매물을 빼고 센 말이 된다 (2026-10-28 실측: 사근동 원룸
        # 월세 3쪽째 1건에 '이 1건이 전부입니다', 앞 두 쪽에서 6건을 받았다)
        notes.append(
            f'앞 결과에 이어 남은 매물 {returned}건을 받았고, 더 받을 매물은 없습니다'
            if returned else '앞 결과 뒤로 더 받을 매물이 없습니다'
        )
    elif returned < limit and not has_more:
        notes.append(f'조건에 맞는 매물은 이 {returned}건이 전부입니다')
    if not narrowable:
        return notes
    if has_more and resumable:
        notes.append(note('일부', '더 있습니다. 이어 보려면 결과의 next 를 --next 로 주세요'))
    elif has_more and limit >= LISTING_MAX_LIMIT:
        notes.append(note('일부', f'--limit 의 최대값은 {LISTING_MAX_LIMIT}입니다. 더 보려면 조건을 좁히세요'))
    elif has_more and inspected >= limit:
        notes.append(note('일부', '더 보려면 --limit 을 늘리거나 조건을 좁히세요'))
    return notes


def complex_building_notes(articles: list[DaangnArticleModel]) -> list[str]:
    """원룸·투룸으로 올렸지만 오피스텔·아파트 같은 단지에 있는 매물을 알린다. 매물은 빼지 않는다."""
    found: list[str] = []
    for article in articles:
        if article.sales_type is None or article.sales_type.type not in ROOM_SALES_TYPES:
            continue
        complex_ = article.complex
        building = COMPLEX_TYPE_LABELS.get(complex_.type or '') if complex_ else None
        if complex_ is None or building is None:
            continue
        found.append(f'{article.original_id}({complex_.name or "단지 이름 없음"}, {building})')
    if not found:
        return []
    shown = ', '.join(found[:5]) + (f' 외 {len(found) - 5}건' if len(found) > 5 else '')
    return [
        f'원룸·투룸으로 올렸지만 단지 건물에 있는 매물 {len(found)}건: {shown}. '
        'property_type 은 작성자가 고른 종류이고, 건물 종류는 이 안내와 listing 의 complex_type 으로 확인하세요'
    ]


def hidden_location_notes(articles: list[DaangnArticleModel]) -> list[str]:
    """주소를 숨긴 매물의 `distance_km` 가 null 인 이유를 알린다 (`article_to_listing`). 매물은 빼지 않는다."""
    count = sum(1 for article in articles if article.is_hide_address)
    if not count:
        return []
    return [note(
        '참고',
        f'distance_km 가 null 인 {count}건은 작성자가 주소를 숨긴 매물이라 당근이 실제 위치가 아닌 좌표를 주어 거리를 모릅니다 '
        '(주소도 동까지만 공개)',
    )]


def trade_unselected_notes(count: int) -> list[str]:
    """서버 필터를 통과했지만 검색에 맞는 거래 조건을 고르지 못해 뺀 매물을 알린다.

    임의의 대표 가격을 내보내지 않으려고 뺀다 (provider-conventions 의 서버 필터 절).
    """
    if count <= 0:
        return []
    return [note(
        '제외',
        f'서버 필터를 통과한 매물 {count}건은 응답의 거래 조건 중 검색한 거래 유형·금액에 맞는 것을 확인할 수 없어 '
        '(금액이 빠졌거나 관리비 포함 금액처럼 목록만으로 계산할 수 없음) 제외했습니다. 제외된 수만큼 추가 조회하지 않았습니다',
    )]


def complex_url(complex_id: str | int) -> str:
    return f'https://realty.daangn.com/complexes/{complex_id}'


def complex_not_found(complex_id: str | int) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f'당근 단지를 찾지 못했습니다: {complex_id}',
        hint=(
            "단지 ID 는 'jibsa daangn search locations <단지 이름>' 의 complexes 나 아파트·오피스텔 매물 "
            'item 의 complex_id 에서 얻습니다'
        ),
    )


def station_name(name: str) -> str:
    return name if name.endswith('역') else f'{name}역'


class DaangnRecentTrade(BaseModel):
    """단지 목록에 붙는 최근 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
            data.pop(field, None)
        return data


class DaangnRegionComplex(BaseModel):
    """지역 단지 목록의 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='당근 단지 ID (complex·items·real-price 에 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...). 모르면 null')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (매매·전세·월세)')
    ]
    recent_trades: Annotated[
        list[DaangnRecentTrade],
        Field(description=f'요청한 거래 유형의 최근 실거래 (최근 계약 순, 최대 {COMPLEX_RECENT_TRADES}건). 계약일·층은 없다')
    ] = []
    near_station: Annotated[
        bool | None,
        Field(description='역에서 가까운 단지인지 (당근 기준). 모르면 null')
    ] = None
    has_reviews: Annotated[
        bool,
        Field(description='거주 후기가 있는지. 내용은 url 의 단지 페이지에서 본다')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지')
    ]


def _recent_trades(node: DaangnRegionComplexNodeModel, trade_type: str) -> list[DaangnRecentTrade]:
    """단지 카드의 최근 실거래에서 요청한 거래 유형만 골라 앞에서부터 `COMPLEX_RECENT_TRADES` 건.

    전월세는 전세·월세가 섞여 오므로 월세가 0 이면 전세로 본다. 해제(취소)된 매매는 뺀다.
    """
    trades: list[DaangnRecentTrade] = []
    for edge in node.transactions.edges if node.transactions else []:
        transaction = edge.node
        if transaction is None or transaction.deal_canceled:
            continue
        if trade_type == '매매':
            if transaction.deal_amount is None:
                continue
            trade = DaangnRecentTrade(
                trade_type=trade_type,
                area_m2=transaction.exclusive_use_area,
                price_manwon=transaction.deal_amount,
            )
        else:
            monthly = bool(transaction.monthly_rent)
            if transaction.deposit is None or monthly != (trade_type == '월세'):
                continue
            trade = DaangnRecentTrade(
                trade_type=trade_type,
                area_m2=transaction.exclusive_use_area,
                deposit_manwon=transaction.deposit,
                rent_manwon=transaction.monthly_rent if monthly else None,
            )
        trades.append(trade)
        if len(trades) >= COMPLEX_RECENT_TRADES:
            break
    return trades


def region_complex_of(node: DaangnRegionComplexNodeModel, trade_type: str) -> DaangnRegionComplex:
    """단지 카드를 `DaangnRegionComplex` 로 바꾼다. 후기 본문·요약은 내보내지 않고 있는지만 알린다."""
    danji = node.danji
    counts = node.live_article_count
    return DaangnRegionComplex(
        complex_id=node.original_id,
        name=node.name,
        property_type=COMPLEX_TYPE_LABELS.get(node.type or '', node.type),
        households=danji.households if danji else None,
        approved_at=normalize_date(danji.build_date) if danji else None,
        listing_counts={
            '매매': counts.buy if counts else None,
            '전세': counts.borrow if counts else None,
            '월세': counts.month if counts else None,
        },
        recent_trades=_recent_trades(node, trade_type),
        near_station=node.near_station,
        has_reviews=bool(node.lived_reviews and node.lived_reviews.edges) or node.lived_review_summary is not None,
        url=complex_url(node.original_id),
    )


def complex_list_notes(complexes: list[DaangnRegionComplex]) -> list[str]:
    """단지 목록(지역 단지·학교 배정 단지) 공통 안내: 최근 실거래에 날짜가 없고, 후기는 있는지만 알린다.

    매번 같은 안내지만 원룸 종류 안내처럼 docs/llm.md 로 옮기지 않는다. 가이드는 모든 세션이 읽어 이 명령을 쓰지 않는
    세션까지 토큰을 쓰고, 여기서는 이 명령을 부를 때만 나온다 (2026-10-23 실측: `search complexes 대치동` 안내 두 개
    162자 / 출력 21,471자, 0.8%).
    """
    notes: list[str] = []
    if any(complex_.recent_trades for complex_ in complexes):
        notes.append('recent_trades 는 당근 단지 목록의 최근 실거래라 계약일·층이 없습니다. 날짜까지 보려면 real-price <complex_id> 를 쓰세요')
    if any(complex_.has_reviews for complex_ in complexes):
        notes.append('거주 후기는 있는지(has_reviews)만 알려 줍니다. 후기 내용은 url 의 단지 페이지에서 확인하세요')
    return notes
