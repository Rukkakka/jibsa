"""당근 service 공통: GraphQL 응답 풀기, 여러 모듈이 쓰는 결과 모델·매물 변환·안내 문구·상수."""

import math
import re
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from math import floor

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
    NEXT_HINT,
    NOT_APPLICABLE_PRICE_FIELDS,
    UPDATE_MAYBE_NEEDED,
    UPDATE_NEEDED,
    Listing,
    ListingStatus,
    TradeType,
    join_address,
    m2_to_pyeong,
    more_hint,
    normalize_date,
    note,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnAmountRangeModel,
    DaangnBoundsLocationFilterModel,
    DaangnBuildingApprovalDate,
    DaangnComplexType,
    DaangnCoordinateInputModel,
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
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionComplexNodeModel,
    DaangnTradeModel,
)

from typing import (
    Annotated,
    Any,
    Generic,
    NamedTuple,
    Protocol,
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
# 웹이 조건 없는 화면에 기본으로 보내는 매물 종류. 대학 페이지(`UniversityArticleListPanel` 의 `Go`)는 지도 필터가 비었을 때
# 원룸·투룸·오피스텔, 단지 매물 패널(`ComplexArticleListPanel` 의 `F`)은 늘 주거 5종이 기본이다 (2026-11-12 번들 대조).
# 역 주변·동·지도 범위 목록은 빈 목록(전체)이 기본이다
UNIVERSITY_DEFAULT_SALES_TYPES: tuple[DaangnSalesType, ...] = ('ONE_ROOM', 'TWO_ROOM', 'OFFICETEL')
COMPLEX_LISTING_DEFAULT_SALES_TYPES: tuple[DaangnSalesType, ...] = ('APART', 'HOUSE', 'OFFICETEL', 'ONE_ROOM', 'TWO_ROOM')
# 출퇴근 API 가 같은 이름 역 뒤에 붙이는 노선 꼬리 ('양평역(경의중앙선)', `station_name`)
STATION_LINE_SUFFIX_PATTERN: re.Pattern[str] = re.compile(r'\s*\([^()]*\)$')
# 웹 인기 매물 순위 화면이 받는 매물 종류 (`mapSearchSchema` 의 `Qe`: 그 밖의 종류가 URL 에 오면 순위 화면을 열지 않는다)
POPULAR_PROPERTY_TYPES: tuple[str, ...] = ('원룸', '투룸', '아파트', '오피스텔')
TRADE_TYPE_BY_TRADE: dict[str, TradeType] = {
    'MONTH': '월세',
    'BORROW': '전세',
    'BUY': '매매',
    # 단기임대 (ShortTrade). 월세처럼 보증금·월세가 있다.
    'SHORT': '단기임대',
    # 연세 (YearTrade). 1년치 월세를 한 번에 내는 제주 거래라 보증금·연세(yearlyPay)가 있고 월세는 없다
    'YEAR': '연세',
}
TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세', '단기임대', '연세')
# 내보내는 매물의 거래 상태 (웹 목록·상세의 표시 그대로). 거래완료(TRADED)는 만료 매물이라 없다 (`is_available`)
LISTING_STATUS_BY_STATUS: dict[str, ListingStatus] = {'ON_GOING': '판매중', 'RESERVED': '예약중'}
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
    '연세': 'YEAR',
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
# 당근 웹이 평형을 공급 평 묶음(supplyPyeongAreaGroups)으로 고르는 아파트형 단지 (services2 `Os`). 그 밖은 전용면적 묶음이다
APARTMENT_COMPLEX_TYPES: frozenset[str] = frozenset({'APARTMENT', 'MIXED_USE', 'REDEVELOPMENT'})
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

# 웹 지도 화면 (데스크톱). 지도 범위 매물 목록(`search`)과 지도 범위 단지 목록(`complex`)이 함께 쓴다. jibsa 는 화면이 없어 웹을 데스크톱 1440×900 창으로 열었을 때의 범위를 쓴다. 웹은 지도 왼쪽의
# 메뉴(180px)와 매물 목록 패널(400px + 여백 16px)을 뺀 영역의 북동·남서 꼭짓점을 목록 범위로 보내고, 고른 곳을 그 영역의
# 가운데에 둔다 (MapView 의 `Wi`, mapPanelOffset). 지도 타일은 512px 이다 (maplibre)
MAP_VIEW_WIDTH_PX: int = 1440 - 180 - 416
MAP_VIEW_HEIGHT_PX: int = 900
MAP_TILE_PX: int = 512
# 지도 목록을 여는 줌 범위. 웹 데스크톱은 줌 8 부터 '매물 N개' 칩을 띄운다 (MapShell)
MAP_ZOOM_MIN: int = 8
MAP_ZOOM_MAX: int = 18
# 역·대학·좌표를 고르면 웹 지도가 여는 줌 (검색창 선택의 `rs`)
POINT_ZOOM: int = 15
# 웹 데스크톱의 줌 → H3 해상도 (mapDev 의 `T`). 위에서부터 처음 맞는 하한을 쓰고, 다 아니면 `MAP_RESOLUTION_MIN`
MAP_RESOLUTION_BY_ZOOM: tuple[tuple[float, int], ...] = ((17.5, 11), (16.5, 10), (15, 9), (14, 8), (13, 7), (12.5, 6))
MAP_RESOLUTION_MIN: int = 5
# articlesCount 는 이 수에서 잘린다 (웹은 '999+' 로 보여 준다)
COUNT_CAP: int = 1000


def map_resolution(zoom: float) -> int:
    """웹 데스크톱 지도가 줌마다 목록·매물 수 요청에 보내는 `resolution` (H3 해상도)."""
    return next((resolution for low, resolution in MAP_RESOLUTION_BY_ZOOM if zoom >= low), MAP_RESOLUTION_MIN)


def map_view_bounds(lat: float, lng: float, zoom: int) -> tuple[DaangnBoundsLocationFilterModel, float, float]:
    """(`lat`, `lng`) 를 가운데에 둔 웹 데스크톱 지도 화면의 범위와 그 가로·세로 (km).

    maplibre 처럼 Web Mercator 픽셀 좌표로 화면 크기만큼 넓혀 꼭짓점을 구한다. 위도 37.5° 에서 줌 15 는 약 1.6×1.7km,
    줌 12 는 약 12.8×13.6km 다.
    """
    world = MAP_TILE_PX * 2 ** zoom
    sin_lat = math.sin(math.radians(lat))
    x = (lng + 180) / 360 * world
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * world

    def unproject(px: float, py: float) -> tuple[float, float]:
        return math.degrees(math.atan(math.sinh(math.pi - 2 * math.pi * py / world))), px / world * 360 - 180

    north, west = unproject(x - MAP_VIEW_WIDTH_PX / 2, y - MAP_VIEW_HEIGHT_PX / 2)
    south, east = unproject(x + MAP_VIEW_WIDTH_PX / 2, y + MAP_VIEW_HEIGHT_PX / 2)
    bounds = DaangnBoundsLocationFilterModel(
        ne_coordinate=DaangnCoordinateInputModel(lat=north, lon=east),
        sw_coordinate=DaangnCoordinateInputModel(lat=south, lon=west),
    )
    return bounds, round(haversine_km(lat, west, lat, east), 1), round(haversine_km(north, lng, south, lng), 1)


class DaangnRegion(BaseModel):
    """조회한 동이나 구 (구는 `name3` 가 빈 문자열이다. 구 이름의 지도 범위 검색)."""

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
        Field(description='읍/면/동. 구를 찾은 결과(지도 범위 검색)는 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]

    @model_serializer(mode='wrap')
    def drop_missing_district(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 세종은 시·군·구가 없어 당근이 name2 를 '' 로 준다 (해당 없음). 구를 찾은 결과는 name3 이 '' 다. 이어 받기 표에서 다시
        # 읽을 때는 기본값 '' 로 돌아온다
        for key in ('name2', 'name3'):
            if not getattr(self, key):
                data.pop(key, None)
        return data


class FeedQueryRejectedError(JibsaError):
    """GraphQL 이 persisted query 해시를 거절했을 때. 웹이 쿼리를 바꿨다는 신호다.

    대체 경로나 따로 안내할 말이 있는 곳(단지 후보, 지도 범위·출퇴근 검색 등)은 이 예외를 먼저 잡아 처리하고,
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
    """내보낼 매물인지. 판매중(ON_GOING)이나 예약중(RESERVED)이고 숨김·노출 제한이 없어야 한다.

    거래완료(TRADED)는 만료 매물이라 뺀다. 예약중은 계약이 깨질 수 있어 당근 웹처럼 보여 주고 `status` 로 알린다 (2026-11-11
    사용자 결정). 숨김(작성자가 내림)과 노출 제한(당근이 막음)은 웹 상세도 매물 대신 안내 문구를 보여 주는 매물이다. 노출 제한은
    SSR 스토어에는 `invisibleReason`, GraphQL 피드에는 `invisibleInfos` 로 온다.

    비활성 중개소 매물은 여기서 보지 않는다. 목록 카드의 `bizProfile` 에는 중개소 상태가 없고(id·badges 만) 상세 SSR 에만
    `status` 가 있다 (2026-11-11 실측). 당근 웹도 목록에는 그 매물을 그대로 보여 주고 상세에서만 "비활성화된 중개소의
    매물이에요" 로 막아, jibsa 도 웹처럼 상세(`listing`·`--details`)에서만 막는다 (`listing._inactive_broker`). 목록에서 막으려면
    매물마다 상세를 받아야 해 요청이 매물 수만큼 늘고 웹과도 달라진다 (2026-11-11 사용자 결정).
    """
    return (
        article.status in LISTING_STATUS_BY_STATUS
        and not article.is_hide
        and article.invisible_reason is None
        and not article.invisible_infos
    )


def article_url(original_id: str | int) -> str:
    return f'https://realty.daangn.com/articles/{original_id}'


def trades_preferred_first(article: DaangnArticleModel) -> list[DaangnTradeModel]:
    """jibsa 가 아는 거래(`TRADE_TYPE_BY_TRADE`)를 대표(preferred) 거래 먼저 세운다.

    웹 목록(`services2` 의 `Fo`)의 후보 BORROW·BUY·MONTH·SHORT·YEAR 와 같다. 예전에는 제주 연세(YEAR)를 표현하지 않아
    빼서, 연세가 대표인 매물은 웹과 다른 거래를 보여 주고 연세만 있는 매물은 목록에서 빠졌다 (2026-11-13 연세 지원).
    """
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
    """검색 중심(동 중심·역·대학·지도 화면 가운데·회사)에서 거리를 재는 당근 매물. 거리를 모르면 키를 빼지 않고 null(모름)로 낸다.

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
        status=LISTING_STATUS_BY_STATUS.get(article.status or ''),
        property_type=property_type_of(article),
        room_type=room_type_of(article),
        title=article.address_info or article.building_name or fallback_title or None,
        price_manwon=trade.price if trade.type == 'BUY' else None,
        deposit_manwon=trade.deposit if trade.type != 'BUY' else None,
        rent_manwon=trade.monthly_pay if trade.type in MONTHLY_TRADES else None,
        # 연세는 월로 나누지 않고 당근 웹 카드('연세 1,000 / 1,400만원')처럼 1년치 그대로 준다
        yearly_rent_manwon=trade.yearly_pay if trade.type == 'YEAR' else None,
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


def amount_range(low: int | None, high: int | None) -> DaangnAmountRangeModel | None:
    if low is None and high is None:
        return None
    return DaangnAmountRangeModel(min_amount=low, max_amount=high)


def label_codes(labels: list[str] | None, codes: Mapping[str, str]) -> list[str] | None:
    return [codes[label] for label in labels] if labels else None


class DaangnListingConditions(RequestModel):
    """매물 검색 조건 (한국어 라벨). 당근 웹 지도 필터(`property_filter`)와 받은 매물의 보여 줄 거래 고르기
    (`trade_of`)에 같이 쓴다. 매물 검색 명령은 모두 이 묶음을 넘긴다.

    라벨은 `PROPERTY_TYPES`·`TRADE_TYPES` 와 `*_FILTER_BY_LABEL` 의 키다. 만들 때 필터로 바꿔 보아
    조건 조합이 잘못됐으면 요청을 보내기 전에 멈춘다.

    Raises:
        ValidationError: 원룸이 아닌데 방 구조를, 아파트·오피스텔이 없는 유형에 세대수·주차대수를 줬을 때.
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
    yearly_rent_min: Annotated[
        int | None,
        Field(description='연세 하한 (만원)')
    ] = None
    yearly_rent_max: Annotated[
        int | None,
        Field(description='연세 상한 (만원)')
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
        Field(description='세대수 하한 (유형 전체·아파트·오피스텔)')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한 (유형 전체·아파트·오피스텔)')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한 (유형 전체·아파트·오피스텔)')
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
        ValidationError: 원룸이 아닌데 방 구조를, 아파트·오피스텔이 없는 유형에 세대수·주차대수를 줬을 때.
    """
    return DaangnPropertyFilterModel(
        sales_types=label_codes(conditions.property_types, SALES_TYPE_BY_PROPERTY_TYPE) or [],
        trade_types=label_codes(conditions.trade_types, TRADE_FILTER_BY_TRADE_TYPE),
        deposit_pay=amount_range(conditions.deposit_min, conditions.deposit_max),
        monthly_pay=amount_range(conditions.rent_min, conditions.rent_max),
        yearly_pay=amount_range(conditions.yearly_rent_min, conditions.yearly_rent_max),
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


def trade_of(article: DaangnArticleModel, conditions: DaangnListingConditions) -> DaangnTradeModel | None:
    """매물 카드에 보여 줄 거래 하나를 당근 웹 목록처럼 고른다 (웹 `services2` 의 `Fo`). 거래 조건이 없으면 None.

    웹은 거래 유형만 보고 금액은 다시 보지 않는다. 거래가 하나면 그것, 검색한 거래 유형(없으면 모든 유형)과 겹치는 거래가
    하나면 그것, 겹치는 거래가 없으면 대표(preferred) 거래, 여럿이면 그중 대표 거래나 첫 거래다. 예전에는 jibsa 가 금액 조건까지
    다시 보고 맞는 거래가 없으면 매물을 뺐는데, 당근 서버가 조건에 맞다고 준 매물을 웹보다 적게 보여 줘 웹처럼 바꿨다 (#215).
    """
    trades = trades_preferred_first(article)
    if not trades:
        return None
    wanted = {TRADE_FILTER_BY_TRADE_TYPE[trade_type] for trade_type in conditions.trade_types or TRADE_TYPES}
    matching = [trade for trade in trades if trade.type in wanted]
    # trades_preferred_first 가 대표 거래를 앞에 두어, 웹 `Fo` 의 갈래(거래 하나, 겹치는 거래 하나·여럿·없음)가 모두 그 목록의
    # 첫 거래다: 겹치는 거래가 있으면 그중 대표 거래나 첫 거래, 없으면 대표 거래 (2026-11-12 리뷰로 한 줄로 줄임)
    return (matching or trades)[0]


def no_trade_notes(articles: Iterable[DaangnArticleModel]) -> list[str]:
    """받은 매물 중 jibsa 가 아는 거래(`TRADE_TYPE_BY_TRADE`)가 없어 뺀 매물을 알린다 (`trade_of` 가 None).

    거래 조건이 비었거나 당근이 새 거래 유형만 올린 매물이다. 웹 목록(`Fo`)의 후보 다섯(매매·전세·월세·단기임대·연세)을 모두
    다뤄 지금은 나오지 않는다 (2026-11-13 연세 지원 전에는 제주 연세만 올린 매물이 여기로 빠졌다: 노형동 40건 중 13건).
    거래 조건을 못 골라 뺀 매물은 사유를 알린다 (AGENTS.md). 예산 안내(`listing_budget_notes`)의 사유 목록만으로는 서버
    조건에 맞는 매물이 왜 빠졌는지 알 수 없었다 (2026-11-12 리뷰). 거래 불가 매물은 거기서 세므로 여기서 세지 않는다.
    """
    count = len({
        article.original_id for article in articles if is_available(article) and not trades_preferred_first(article)
    })
    if count == 0:
        return []
    return [note(
        '제외',
        f"{'·'.join(TRADE_TYPES)} 거래가 없는 매물 {count}건은 jibsa 가 가격을 보여 줄 수 없어 뺐습니다. 당근 웹에서는 보일 수 있습니다",
    )]


def js_round(value: float) -> int:
    """JS `Math.round` 처럼 .5 를 늘 올려 반올림한다. 당근 웹과 숫자를 맞출 때 쓴다.

    Python `round` 는 .5 를 짝수로 보내 (2.5 → 2) 웹과 1 씩 달라진다.
    """
    return floor(value + 0.5)


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


# 덤 조회(매물 수·시·도·좌표의 동·단지 후보·후기 수·검색창 후보)가 잡는 실패.
# 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`: HTTPError, 응답 형식 변경의 ValueError)에 JibsaError(해시 거절·GraphQL
# 에러·요청 제한)를 더한다. 요청 제한을 바로 올릴 곳은 이보다 먼저 잡는다.
# 전에는 ValueError 를 잡지 않아 덤 조회 하나가 차단 페이지를 받으면 모아 둔 매물(최대 120건)까지 잃고 PARSE_ERROR 로
# 끝났다. 2026-10-11 사용자 결정으로 결과는 돌려주고 `notes` 로 알린다 (주된 조회는 그대로 PARSE_ERROR).
# 걸리는 다른 경우도 결과는 맞다 (2026-10-11 실측):
# - 상태 폴더 오류(StateDirError, JibsaError)도 잡히지만 다음 요청이 같은 이유로 실패해 결국 그 에러와
#   '다른 소스로 다시 시도하지 마세요' 힌트로 끝난다
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


def next_cursor(page_info: DaangnPageInfoModel | None, after: str | None, *, received: int) -> str | None:
    """다음 페이지가 있다는 쪽에서 이어 받을 커서. 빈 쪽·커서 없음·같은 커서 되풀이면 None 이라 그만 받는다.

    단지 후보·지역 단지·단지 매물·실거래 목록과 매물 목록(`connection_edges`)이 함께 쓴다. 호출부는 `has_next_page` 를 먼저
    보고 부르며, None 이면 멈춘 까닭을 안내한다. 목록 끝은 늘 항목과 함께 hasNextPage=False 로 와서(2026-11-10 실측: 역삼동 지역 단지 113곳 3쪽·
    헬리오시티 단지 후보 100곳 2쪽, 단지가 0곳인 서화면·북면은 edges 0·False), 다음이 있다면서 빈 쪽을 주면 끝이 아니라
    비정상이다. 그래서 '목록 끝' 으로 조용히 넘기지 않는다.

    네 목록(단지 후보·지역 단지·단지 매물·실거래)의 반복문을 커서 반복자 하나로 모으지 않는다. 반복문마다 --limit 예산을
    세는 법(단지 후보는 node, 지역 단지·단지 매물은 edge), 멈춤 밖의 끝 조건(실거래 --years 기간), 실패 처리(단지 후보는 받은
    데까지 돌려줌, 단지 매물은 단지가 없으면 NOT_FOUND)가 달라 반복자가 그만큼 갈래를 받아야 한다. 멈춤 판단만 `stalled_page`(세기 전)와 이 함수(센 뒤)에 모아 반복문마다 같은 자리에서 부른다
    (2026-11-11 리뷰가 반복자로 모으자고 했다).

    Args:
        page_info: 방금 받은 쪽의 페이지 정보.
        after: 그 쪽을 요청할 때 쓴 커서.
        received: 그 쪽에서 받은 쓸 수 있는 항목 수. node 가 null 인 edge 는 세지 않는다. 호출부마다 edge 수와 node 수를 섞어 넘기면 같은 쪽을 한쪽은 빈 쪽으로 멈추고 한쪽은 계속 받는다
            (2026-11-10 리뷰. 그날 실측 응답에는 null node 가 없었다: 헬리오시티 단지 후보 2쪽).
    """
    if not received or page_info is None or not page_info.end_cursor or page_info.end_cursor == after:
        return None
    return page_info.end_cursor


def stalled_page(page_info: DaangnPageInfoModel | None, after: str | None) -> bool:
    """다음이 있다던 쪽 뒤에 받은 쪽이 셀 수 없는 쪽인지. 호출부는 그 쪽을 세기 전에 멈춘다 (`cursor_stopped_note`).

    호출부는 다음이 있다는 쪽에서만 `after` 로 다음 쪽을 받으므로, `after` 가 있으면 앞 쪽이 다음이 있다고 한 것이다.
    그 뒤에 받은 쪽이 아래 둘 중 하나면 멈춘다.

    - 페이지 정보가 없다(null). 목록 끝은 늘 hasNextPage=False 로 오므로(`next_cursor`) 응답이 바뀐 것이다. 이 검사가 없을
      때는 다섯 목록 모두 has_more false 로 조용히 끝내 받은 일부를 전부처럼 냈다 (2026-11-11 리뷰·실측: 강남구 지역 실거래
      --limit 60 의 2쪽만 pageInfo null 로 바꾸니 50건·has_more false 에 멈춤 안내가 없었다).
    - 다음이 있다면서 요청한 커서를 그대로 돌려줬다. `next_cursor` 도 되풀이를 보지만 그 쪽을 센 뒤라, 되풀이된 쪽이
      --limit 의 남은 몫을 채우면 멈춤이 아니라 --limit 에 닿은 것으로 알렸다 (2026-11-10 리뷰: 지역 단지 --limit 100 의
      2쪽이 1쪽 50곳을 되풀이하면 '앞 50곳만 보여 줍니다. 더 보려면 --limit 을 늘리거나'). 다음이 없다는 마지막 쪽은
      되풀이로 보지 않는다 (실거래 `_collect_pages` 주석의 실측).
    """
    if after is None:
        return False
    if page_info is None:
        return True
    return bool(page_info.has_next_page) and page_info.end_cursor == after


def cursor_stopped_note(subject: str, received: str) -> str:
    """`next_cursor` 가 None 이라 멈췄을 때 안내의 본문 (태그와 다음에 할 일은 호출부가 붙인다).

    목록 끝은 늘 hasNextPage=False 로 오므로(`next_cursor`) 응답이 바뀌었을 수 있다. 업데이트 문구를 넣어 매일 API 감시가
    결과가 비지 않은 날에도 고장으로 센다 (2026-11-10 리뷰: 2쪽에서 멈춘 역삼동 단지 50곳이 감시에서 정상으로 넘어갔다).

    태그와 다음 할 일을 여기서 정하지 않는 것은 멈춤이 결과에 끼치는 영향이 목록마다 달라서다. 단지 후보·지역 단지·단지
    매물은 못 받은 것이 결과에서 빠져 [일부] 다. 실거래는 멈춘 까닭을 [참고] 로, 더 있다는 말과 사이트 안내를 [일부] 하나로
    따로 낸다. 매물 목록(`connection_edges`: 동·지도 범위·역·대학 주변, 출퇴근 역별 매물)은 --limit 을 늘려도 같은 자리에서
    멈춰 [일부] 다 (2026-11-10 리뷰가 태그를 여기서 고르자고 했으나, 실측 출력으로 보니 다른 것은 위 차이 때문이었다).

    Args:
        subject: 무엇의 목록인지 (예: '단지 후보').
        received: 멈출 때까지 받은 수와 단위 (예: '50곳').
    """
    return (
        f'당근이 {subject} 다음 페이지가 있다고 하면서 이어 받을 페이지를 주지 않아 {received}에서 멈췄습니다. '
        f'API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
    )


class DaangnListingEdge(Protocol):
    """매물 목록의 edge (`connection_edges`). node 가 null 인 edge 는 받은 항목으로 세지 않는다 (`next_cursor`)."""

    @property
    def node(self) -> object | None: ...


_EdgeT_co = TypeVar('_EdgeT_co', covariant=True)
EdgeT = TypeVar('EdgeT', bound=DaangnListingEdge)


class DaangnListingConnection(Protocol[_EdgeT_co]):
    """쪽마다 `edges`·`pageInfo` 를 주는 매물 목록 (`connection_edges`). 동·지도 범위 피드와 역·대학 주변 매물이 이 꼴이다."""

    @property
    def edges(self) -> Sequence[_EdgeT_co]: ...

    @property
    def page_info(self) -> DaangnPageInfoModel | None: ...


class ConnectionEdges(NamedTuple, Generic[EdgeT]):
    """`connection_edges` 가 이어 받은 매물 목록."""

    edges: list[EdgeT]
    # 서버에 더 있는지. 멈췄을 때(`stopped`)도 서버가 더 있다고 했으니 True 다
    has_more: bool
    # 다음 쪽 커서. 더 없거나 멈췄으면 None 이라 이어 받기(`--next`)를 내지 않는다
    cursor: str | None
    # 다음이 있다면서 빈 쪽·커서 없음·같은 커서 되풀이를 줘 멈췄는지 (`next_cursor`). 호출부가 `cursor_stopped_note` 로 알린다
    stopped: bool


def connection_edges(
    fetch: Callable[[int, str | None], DaangnListingConnection[EdgeT]],
    limit: int,
    page_size: int,
    *,
    after: str | None = None,
    full_page_more: Callable[[list[EdgeT]], bool] | None = None,
) -> ConnectionEdges[EdgeT]:
    """매물 목록을 `page_size` 건씩 `limit` 건까지 이어 받는다. 동·지도 범위·역·대학 주변 목록과 출퇴근 역별 매물이 함께 쓴다.

    받은 edge 수로 예산을 세고 뺄 매물을 채우지 않는다. 다음이 있다면서 빈 쪽·커서 없음·같은 커서 되풀이를 주면 다른 목록처럼
    (`next_cursor`) 멈추고 `stopped` 로 알린다. 예전에는 그 커서를 그대로 돌려줘, 빈 쪽 뒤에도 같은 자리의 `next` 가 나와
    `--next` 로 따라가면 같은 빈 쪽·같은 `next` 가 되풀이됐다 (2026-11-12 리뷰. 실측 응답의 끝 쪽은 늘 hasNextPage=False 였다:
    역삼동 토지 매매 1만원 이하 0건은 edges 0·커서 없음·False). 예전에는 동·지도 범위 목록과 역·대학 주변 목록이 같은 반복문을
    따로 두었다 (2026-11-12 리뷰).

    Args:
        fetch: (받을 수, 커서) → 한 쪽.
        limit: 최대 매물 수.
        page_size: 한 번에 받을 수 (웹과 같은 크기나 서버가 한 번에 주는 최대).
        after: 이어 받기(`--next`)에서 시작할 커서. 없으면 처음부터.
        full_page_more: 쪽이 요청한 수만큼 찼는데 서버 `hasNextPage` 가 false 일 때 다음 쪽이 있는지 (지금까지 받은 edge 를
            받는다). 동 목록이 매물이 남았는데 false 를 줘서 쓴다 (`search_dong`). 없으면 서버 값을 따른다. 다음 쪽을 받기 전에
            물어, 더 없다는 것을 아는 호출부가 빈 쪽을 받지 않게 한다 (2026-11-12 리뷰: 예전에는 쪽이 꽉 차면 늘 다음 쪽을 받고
            끝난 뒤에 '더 있음' 을 바로잡아, 매물이 딱 20건인 동의 --limit 40 이 빈 쪽을 한 번 더 받았다).

    Returns:
        받은 edge, 서버에 더 있는지, 다음 쪽 커서, 멈췄는지 (`ConnectionEdges`).
    """
    edges: list[EdgeT] = []
    cursor, has_more = after, False
    while len(edges) < limit:
        size = min(page_size, limit - len(edges))
        page = fetch(size, cursor)
        edges += page.edges
        page_info = page.page_info
        server_more = bool(page_info and page_info.has_next_page)
        has_more = server_more or (full_page_more is not None and len(page.edges) >= size and full_page_more(edges))
        if not has_more:
            return ConnectionEdges(edges, False, None, False)
        # node 가 null 인 edge 는 세지 않는다 (`next_cursor`). edge 수를 넘기면 node 가 모두 null 인 쪽도 받은 쪽으로 보아 멈추지
        # 않고, 결과 0건에 이어 받기(next)가 나왔다 (2026-11-12 검증: 역삼역 역 주변 목록의 node 를 모두 null 로 바꾼 실측 응답)
        cursor = next_cursor(page_info, cursor, received=sum(1 for edge in page.edges if edge.node is not None))
        if cursor is None:
            # 서버는 더 없다고 했는데 꽉 찬 쪽으로 짐작한 것(`full_page_more`)이면 커서가 없어도 멈춤이 아니라 끝이다
            return ConnectionEdges(edges, server_more, None, server_more)
    return ConnectionEdges(edges, has_more, cursor, False)


def truncation_notes(
    received: int,
    limit: int,
    *,
    subject: str = '매물',
    unit: str = '건',
    max_limit: int | None = None,
) -> list[str]:
    """받은 유효 결과를 출력 한도로 자를 때 실제 개수와 다음에 할 일을 알린다.

    `max_limit` 를 주면 `--limit` 이 최대값보다 작을 때 늘리라고 덧붙인다. `--limit` 이 이미 최대값이면 늘리라는
    안내는 옵션 검사에서 막히므로 붙이지 않는다. 매물 목록(`listing_budget_notes`)처럼 `--limit` 안내를 따로 붙이는
    호출부는 `max_limit` 를 넘기지 않는다. 같은 말이 두 번 나온다 (2026-10-11 실측: daangn search listings 역삼동
    --limit 2 에 '검색 범위를 좁혀 주세요' 가 두 번). 실거래는 반대로 `max_limit` 를 넘기고, 이 안내가 나오면 따로
    붙이던 '--limit 을 늘리면' 안내를 빼서 [일부] 를 하나만 낸다 (`_collect_pages`).
    """
    if received <= limit:
        return []
    text = f'조회된 {subject} {received}{unit} 중 --limit {limit} 에 맞춰 {limit}{unit}만 보여 줍니다'
    if max_limit is not None and limit < max_limit:
        text += f'. --limit 을 최대 {max_limit}까지 늘리세요'
    return [note('일부', text)]


def listing_budget_notes(
    limit: int,
    inspected: int,
    returned: int,
    *,
    max_limit: int,
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
        max_limit: 그 명령의 `--limit` 최대값. 이미 최대값이면 늘리라고 하지 않는다 (`limit_notes` 와 같이 기본값 없이 받는다.
            인기 매물은 30, 나머지는 120).
        narrowable: `--limit`·필터로 더 받을 수 있는지. 단지 매물처럼 다음 페이지를 이어 받지 못해 멈췄을 때는 limit 을
            늘리거나 필터를 걸어도 더 받지 못해 False 로 주어 그 안내를 붙이지 않는다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        resumed: 이어 받기(`--next`)로 앞 결과 다음부터 받았으면 True. 이번 쪽만 센 수를 전부라고 하지 않는다.
    """
    notes: list[str] = []
    excluded = inspected - returned if eligible is None else inspected - eligible + min(eligible, limit) - returned
    if excluded > 0 and returned < limit:
        # 당근은 받은 매물을 조건으로 다시 거르지 않아(`trade_of`) 뺀 사유는 이 셋뿐이다. 예전 문구의 '조건 불일치' 는 #215
        # 뒤로 없는 사유라, 거래를 못 고른 매물만 빠진 결과도 서버가 조건에 안 맞는 매물을 준 것처럼 읽혔다 (2026-11-12 리뷰.
        # 그때는 제주 연세만 있는 매물이 빠졌고, 2026-11-13 연세 지원 뒤로는 아는 거래가 하나도 없는 매물만 빠진다)
        head = f'{inspected}건을 받아 중복·거래 불가·거래 조건이 없는 매물을 빼고 {returned}건입니다'
        notes.append(note('제외', f'{head} (뺀 만큼 다시 채우지 않음)' if has_more else f'{head} (더 받을 매물 없음)'))
    elif returned < limit and not has_more and resumed:
        # 이어 받은 마지막 쪽에서 '이 N건이 전부' 라고 하면 앞 결과의 매물을 빼고 센 말이 된다 (2026-10-28 실측: 사근동 원룸
        # 월세 3쪽째 1건에 '이 1건이 전부입니다', 앞 두 쪽에서 6건을 받았다)
        notes.append(
            f'앞 결과에 이어 남은 매물 {returned}건을 받았고, 더 받을 매물은 없습니다'
            if returned else '앞 결과 뒤로 더 받을 매물이 없습니다'
        )
    elif returned < limit and not has_more:
        # 0건이면 '이 0건이 전부입니다' 대신 없다고 한다 (2026-11-11 LLM 사용 시험: 출퇴근 '판교역: … 이 0건이 전부입니다')
        notes.append(f'조건에 맞는 매물은 이 {returned}건이 전부입니다' if returned else '조건에 맞는 매물이 없습니다')
    if not narrowable:
        return notes
    if has_more and resumable:
        notes.append(note('일부', f'더 있습니다. {NEXT_HINT}'))
    elif has_more and (limit >= max_limit or inspected >= limit):
        # 좁힐 것에 지역·범위를 붙이지 않는다. 단지 매물·출퇴근 역별 매물은 좁힐 범위가 없고, 인기 매물은 --limit 이 최대값보다
        # 작을 때만 더 있다고 해 늘리면 된다. 매물 검색(동·지도·역·대학)은 더 있으면 늘 next 로 이어 받게 해 이 안내는 이어 받기가
        # 깨졌을 때(피드 시각을 못 읽음·커서를 잃음·목록이 커서 없이 다음이 있다고 함)만 나간다 (2026-11-11 리뷰·실측: 역삼역·역삼동
        # --limit 3 모두 next 를 줬다)
        notes.append(note('일부', more_hint(limit, max_limit, '조건')))
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


def coordinate_point(coordinate: DaangnCoordinateModel | None) -> tuple[float, float] | None:
    """좌표의 (위도, 경도). 좌표가 없거나 위도·경도 중 하나라도 없으면 None."""
    if coordinate is None or coordinate.lat is None or coordinate.lon is None:
        return None
    return coordinate.lat, coordinate.lon


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
    """'역' 까지 붙인 역 이름 ('역삼' → '역삼역'). 노선 꼬리('양평역(경의중앙선)')가 있으면 꼬리 앞 이름을 본다.

    출퇴근 API 는 같은 이름 역을 가르려 이름 뒤에 노선을 붙인다 (2026-11-13 실측: 서울5호선 '양평역', 경의중앙선
    '양평역(경의중앙선)'). 꼬리까지 보고 '역' 을 붙이면 '양평역(경의중앙선)역' 이 되었다 (2026-11-13 리뷰).
    """
    base = station_base_name(name)
    return name if base.endswith('역') else f'{base}역{name[len(base):]}'


def station_base_name(name: str) -> str:
    """출퇴근 API 역 이름에서 노선 꼬리를 뗀 이름 ('양평역(경의중앙선)' → '양평역'). 역 검색(`find_station`)은 꼬리 없는 이름만 안다."""
    return STATION_LINE_SUFFIX_PATTERN.sub('', name)


def walk_minutes_to(article: DaangnArticleModel, name: str) -> int | None:
    """매물 카드의 인근 역(`subwayStations`) 중 이름이 `name` 인 역까지 도보 (분). 그 역이 없으면 None.

    역 주변 매물(`search_station`, 찾은 역 이름)과 출퇴근 매물(`_commute_listings`, 출퇴근 경로의 역 이름)이 같이 쓴다. 예전에는
    두 곳이 같은 식을 따로 두었다 (2026-11-12 리뷰).
    """
    return next(
        (item.duration_minutes for item in article.subway_stations if item.station and item.station.station_name == name),
        None,
    )


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
        Field(description=f'요청한 거래 유형의 최근 실거래 (최근 계약 순, 최대 {COMPLEX_RECENT_TRADES}건, 학교 배정 단지는 1건). 계약일·층은 없다')
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


def _recent_trades(node: DaangnRegionComplexNodeModel, trade_type: str, max_trades: int) -> list[DaangnRecentTrade]:
    """단지 카드의 최근 실거래에서 요청한 거래 유형만 골라 앞에서부터 `max_trades` 건.

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
        if len(trades) >= max_trades:
            break
    return trades


def region_complex_of(
    node: DaangnRegionComplexNodeModel, trade_type: str, max_trades: int = COMPLEX_RECENT_TRADES,
) -> DaangnRegionComplex:
    """단지 카드를 `DaangnRegionComplex` 로 바꾼다. 후기 본문·요약은 내보내지 않고 있는지만 알린다.

    최근 실거래는 `max_trades` 건까지다. 당근 웹 단지 카드(ComplexListItem)는 취소되지 않은 첫 1건만 보여 주는데, 지역 단지
    목록은 더 많이 보여 주는 jibsa 개선으로 3건을 두고(2026-11-12 사용자 결정), 학교 배정 단지는 웹처럼 1건이다.
    """
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
        recent_trades=_recent_trades(node, trade_type, max_trades),
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
