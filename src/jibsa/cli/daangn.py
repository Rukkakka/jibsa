import logging
import re
from collections.abc import (
    Callable,
    Iterator,
)
from contextlib import contextmanager

import typer

from jibsa.cli.options import (
    DepositMaxOption,
    DepositMinOption,
    FieldsOption,
    PrettyOption,
    PriceMaxOption,
    PriceMinOption,
    RentMaxOption,
    RentMinOption,
)
from jibsa.cli.output import (
    ChangedUsage,
    HintedBadParameter,
    UsageHints,
    emit,
    handle_errors,
    infer_trade_types,
    require_finite,
    require_korea,
    split_csv,
    validate_ranges,
)
from jibsa.cli.paging import (
    NextOption,
    decode_next,
    encode_next,
)
from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.korean import (
    particle,
    quoted,
)
from jibsa.core.listing import (
    Listing,
    note,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.service.common import (
    BUILDING_APPROVAL_FILTER_BY_LABEL,
    COMMUTE_STATION_MAX_LIMIT,
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    DEAL_FILTER_BY_LABEL,
    FLOOR_FILTER_BY_LABEL,
    LISTING_MAX_LIMIT,
    MAP_ZOOM_MAX,
    MAP_ZOOM_MIN,
    OPTION_FILTER_BY_LABEL,
    OPTIONAL_LOOKUP_ERRORS,
    POINT_ZOOM,
    POPULAR_PROPERTY_TYPES,
    PROPERTY_TYPES,
    REAL_PRICE_TRADE_TYPES,
    ROOM_COUNT_FILTER_BY_LABEL,
    STRUCTURE_FILTER_BY_LABEL,
    TRADE_TYPES,
    DaangnListingConditions,
    DaangnRegion,
    FeedQueryRejectedError,
    partial_failure_note,
)
from jibsa.providers.daangn.service.commute import (
    COMMUTE_STATION_DEFAULT_LIMIT,
    search_commute,
)
from jibsa.providers.daangn.service.compare import (
    NEARBY_COMPLEXES_MAX,
    compare_complexes,
    list_nearby_complexes,
)
from jibsa.providers.daangn.service.complex import (
    COMPLEX_CANDIDATE_LIMIT,
    COMPLEX_SORT_BY_LABEL,
    DEFAULT_COMPLEX_TRADE_TYPE,
    DaangnBoundsComplexesResult,
    DaangnComplexConditions,
    DaangnComplexListingsResult,
    DaangnRegionComplexesResult,
    get_complex,
    list_bounds_complexes,
    list_complex_listings,
    list_region_complexes,
    list_trending_complexes,
    search_complexes,
    trending_region_of,
)
from jibsa.providers.daangn.service.listing import (
    DETAILS_MAX,
    attach_details,
    get_listing,
)
from jibsa.providers.daangn.service.neighborhood import (
    LIFESTYLE_INDICATORS,
    recommend_neighborhoods,
)
from jibsa.providers.daangn.service.popular import (
    POPULAR_MAX_LIMIT,
    list_popular_listings,
)
from jibsa.providers.daangn.service.real_price import (
    PRICE_CHART_TRADE_BY_TRADE_TYPE,
    PRICE_TREND_PERIODS,
    REAL_PRICE_MAX_LIMIT,
    DaangnRealPriceBaseResult,
    get_listing_real_prices,
    get_price_trend,
    get_real_prices,
    get_region_real_prices,
)
from jibsa.providers.daangn.service.region import (
    UNIVERSITY_CANDIDATES,
    DaangnAddress,
    DaangnArea,
    DaangnStation,
    DaangnUniversity,
    SimilarAreasError,
    find_address,
    find_station,
    find_university,
    map_query_rejected_error,
    region_by_coordinate,
    resolve_area,
    resolve_dong,
    same_station_notes,
    search_areas,
    search_stations,
    search_universities,
    station_label,
    university_label,
)
from jibsa.providers.daangn.service.review import (
    TOP_COMPLEXES_MAX,
    get_region_reviews,
)
from jibsa.providers.daangn.service.school import (
    COMPARE_MAX_COMPLEXES,
    SCHOOL_CANDIDATE_LIMIT,
    get_preschool,
    get_school,
    list_preschools,
    search_school_candidates,
)
from jibsa.providers.daangn.service.search import (
    DaangnDongSearchResult,
    DaangnMapSearchResult,
    DaangnStationSearchResult,
    DaangnUniversitySearchResult,
    property_type_notes,
    search_dong,
    search_map_area,
    search_station,
    search_university,
)

from typing import (
    Annotated,
    Any,
)


logger = logging.getLogger(__name__)
# --details 를 붙일 수 있는 매물 검색 결과 (동·지도 범위·역·대학·단지)
ListingsResult = (
    DaangnDongSearchResult | DaangnMapSearchResult | DaangnStationSearchResult | DaangnUniversitySearchResult
    | DaangnComplexListingsResult
)


SOURCE: str = 'daangn'

app = typer.Typer(
    help=(
        '당근부동산: 당근 웹 화면과 같은 동·지도 범위·역·대학 주변 매물 (직거래 포함, 로그인 불필요, 금액은 만원). '
        '조건은 당근 웹 지도 필터와 같고 당근 서버에서 건다'
    ),
    no_args_is_help=True,
)

search_app = typer.Typer(help='매물·지역·단지·통근 검색', no_args_is_help=True)
app.add_typer(search_app, name='search')

LatOption = Annotated[float | None, typer.Option(help='중심 위도 (지역 이름 대신)')]
LngOption = Annotated[float | None, typer.Option(help='중심 경도 (지역 이름 대신)')]
StationOption = Annotated[
    str | None,
    typer.Option(
        '--station',
        help="지하철역 이름 (예: 역삼역). 이름이 같은 역이 여럿이면 첫 역이고, 노선을 붙이면 그 역 (예: '서울5호선 양평역')",
    ),
]
UniversityOption = Annotated[
    str | None,
    typer.Option(
        '--university',
        help="대학 이름 (예: 연세대학교). 캠퍼스가 여럿이면 캠퍼스까지 붙인다 (예: '연세대학교 신촌캠퍼스')",
    ),
]
AddressOption = Annotated[
    str | None,
    typer.Option(
        '--address',
        help=(
            "도로명 주소 (예: '테헤란로 152'). 당근 웹 검색창 주소 검색과 같이 후보를 찾아 그 좌표를 가운데에 둔 지도 화면 범위다. "
            "후보가 여럿이면 REGION_AMBIGUOUS 로 알리니 후보의 도로명 주소 그대로 다시 준다"
        ),
    ),
]
# 지도 범위 검색의 줌. 매물 검색은 구·좌표·주소, 단지 목록은 좌표로만 지도 범위를 찾아 도움말을 따로 둔다. 예전에는 단지
# 목록도 매물 검색 도움말을 써 '구 이름·--address' 라고 했지만 단지 목록은 구 이름에 --zoom 을 막고 --address 가 없다
# (2026-11-12 리뷰)
ZoomOption = Annotated[
    int | None,
    typer.Option(
        min=MAP_ZOOM_MIN,
        max=MAP_ZOOM_MAX,
        help=(
            f'구 이름·--lat/--lng·--address 로 찾을 때 웹 지도 줌 ({MAP_ZOOM_MIN}~{MAP_ZOOM_MAX}). 범위는 웹 데스크톱 지도 화면이다. '
            f'기본은 웹과 같다 (구 12, 좌표·주소 {POINT_ZOOM}: 약 1.6×1.7km). 1 작으면 가로·세로가 2배'
        ),
    ),
]
ComplexZoomOption = Annotated[
    int | None,
    typer.Option(
        min=MAP_ZOOM_MIN,
        max=MAP_ZOOM_MAX,
        help=(
            f'--lat/--lng 로 찾을 때 웹 지도 줌 ({MAP_ZOOM_MIN}~{MAP_ZOOM_MAX}). 범위는 웹 데스크톱 지도 화면이다. '
            f'기본은 웹과 같다 ({POINT_ZOOM}: 약 1.6×1.7km). 1 작으면 가로·세로가 2배'
        ),
    ),
]

# 매물 조건 옵션. search listings(--complex 포함)·search commute 가 같이 쓴다 (_listing_conditions)
PropertyTypeOption = Annotated[
    list[str] | None,
    typer.Option('--type', '-t', help=f"{', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 전체. 투룸은 투룸 이상 (쓰리룸·포룸 포함)"),
]
# search listings 의 -t. --complex 와 조건이 하나도 없는 --university 는 웹처럼 기본 종류가 달라 적는다 (2026-11-12 리뷰: '기본 전체'
# 만 있어 단지 안 상가가 빠지는 줄 몰랐다). search commute 의 --university 는 회사 위치라 같은 문구를 쓰지 않는다
ListingPropertyTypeOption = Annotated[
    list[str] | None,
    typer.Option(
        '--type', '-t',
        help=(
            f"{', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 전체 (--complex 는 당근 웹 단지 화면처럼 아파트·주택·오피스텔·원룸·투룸, "
            "조건이 하나도 없는 --university 는 원룸·투룸·오피스텔). 투룸은 투룸 이상 (쓰리룸·포룸 포함)"
        ),
    ),
]
TradeOption = Annotated[
    list[str] | None,
    typer.Option('--trade', help='매매, 전세, 월세, 단기임대, 연세 (1년치 월세를 한 번에 내는 제주 거래). 기본 전체'),
]
# 연세 범위 (웹은 제주에서만 연세 칩·연세 범위를 보여 주지만 서버는 어느 지역에서나 받는다)
YearlyRentMinOption = Annotated[int | None, typer.Option(min=0, help='연세 하한 (만원, 1년치). --trade 연세 와 함께')]
YearlyRentMaxOption = Annotated[int | None, typer.Option(min=0, help='연세 상한 (만원, 1년치). --trade 연세 와 함께')]
WithManageCostOption = Annotated[
    bool,
    typer.Option('--with-manage-cost', help='월세 범위를 월세 + 관리비로 비교 (당근 "관리비 포함"). --rent-min/--rent-max 와 함께'),
]
AreaMinOption = Annotated[float | None, typer.Option(min=0, help='유형별 면적 하한 (㎡): 일반 매물 전용, 주택·건물·공장 연면적, 토지 대지면적')]
AreaMaxOption = Annotated[float | None, typer.Option(min=0, help='유형별 면적 상한 (㎡): 일반 매물 전용, 주택·건물·공장 연면적, 토지 대지면적')]
FloorOption = Annotated[
    list[str] | None,
    typer.Option('--floor', help=f"층수: {', '.join(FLOOR_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분"),
]
RoomCountOption = Annotated[
    list[str] | None,
    typer.Option('--room-count', help=f"방 개수: {', '.join(ROOM_COUNT_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분"),
]
StructureOption = Annotated[
    list[str] | None,
    typer.Option('--structure', help=f"방 구조: {', '.join(STRUCTURE_FILTER_BY_LABEL)}. -t 원룸 과 함께"),
]
# search complexes 의 단지 사용승인일도 같다
ApprovalOption = Annotated[
    str | None,
    typer.Option('--approval', help=f"사용승인일: {', '.join(BUILDING_APPROVAL_FILTER_BY_LABEL)} 중 하나"),
]
DealOption = Annotated[
    str | None,
    typer.Option('--deal', help=f"거래 방식: {', '.join(DEAL_FILTER_BY_LABEL)} (직거래 = 집주인이 직접 올린 매물)"),
]
ExtraOption = Annotated[
    list[str] | None,
    typer.Option('--option', help=f"기타 조건: {', '.join(OPTION_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분"),
]
MoveInNowOption = Annotated[bool, typer.Option('--move-in-now', help='즉시 입주 가능한 매물만')]
NO_APPLIANCE_FILTER: str = '당근에는 가전·가구 옵션 조건이 없습니다'
NO_DIRECTION_FILTER: str = '당근에는 방향 조건이 없습니다'
NO_BATHROOM_FILTER: str = '당근에는 욕실 수 조건이 없습니다'
AREA_IN_M2: str = '당근 면적은 ㎡ 로 주세요: --area-min·--area-max (1평 = 3.3058㎡)'
MANAGE_COST_WITH_RENT: str = '당근은 관리비만 따로 거르지 않습니다. 월세와 관리비 합으로 거르려면 --rent-max 와 --with-manage-cost'
# 같은 이름 지역을 고르던 --city 를 없앤 명령 (#215). 동·구를 받는 명령은 매물 검색을 포함해 모두 CHANGED_USAGE 가 이 안내를 준다. 매물 검색도
# LISTING_HINTS 에 두었더니 '-' 로 시작하는 안내라 옵션 줄로 읽혀 '이 명령에서는 이렇게 주세요: --city 를 없앴습니다' 가 됐다 (2026-11-12 리뷰)
SAME_NAME_REGION_HINT: str = "같은 이름 지역은 '강남구 신사동'·'서울 중구' 처럼 이름 앞에 구·시·도를 붙여 주세요"
CITY_REMOVED_HINT: str = f'--city 를 없앴습니다. {SAME_NAME_REGION_HINT}'
# 매물 조건 옵션에 다른 소스 표현을 옮겨 쓴 사용법 오류의 안내. 매물 조건을 같이 받는 search listings·search commute 가 함께 쓴다.
# 위치·범위 옵션의 안내는 명령마다 따로 둔다 (LISTING_HINTS·COMMUTE_HINTS)
CONDITION_OPTION_HINTS: dict[str, str] = {
    '--condition': '--option',
    '--facility': '--option',
    '--room': '--room-count 2개 (방 1개는 -t 원룸)',
    '--one-room-shape': '--structure 오픈형',
    '--move-in': '--move-in-now',
    '--bathroom': NO_BATHROOM_FILTER,
    '--direction': NO_DIRECTION_FILTER,
    '--sort': '당근 동·지도 범위 목록은 최근 게시 순, 역·대학 주변 목록은 당근 목록 순으로만 줍니다',
    '--area-pyeong-min': AREA_IN_M2,
    '--area-pyeong-max': AREA_IN_M2,
    '--manage-cost-min': MANAGE_COST_WITH_RENT,
    '--manage-cost-max': MANAGE_COST_WITH_RENT,
}
# 매물 검색에 다른 소스 표현을 옮겨 쓴 사용법 오류의 힌트 (UsageHints). 이 명령의 다른 옵션 값과, 뜻이 같은 다른 소스
# 표현이다 (직방 --condition 반려동물·전세대출·주차·즉시입주, --room 오픈형원룸·투룸, --floor 옥탑방, 네이버 --facility)
LISTING_HINTS: UsageHints = UsageHints(
    by_value={
        **{value: f'--floor {value}' for value in FLOOR_FILTER_BY_LABEL},
        **{value: f'--room-count {value}' for value in ROOM_COUNT_FILTER_BY_LABEL},
        **{value: f'--structure {value}' for value in STRUCTURE_FILTER_BY_LABEL},
        **{value: f'--option {value}' for value in OPTION_FILTER_BY_LABEL},
        **dict.fromkeys(
            ('에어컨', '냉장고', '세탁기', '가스레인지', '인덕션', '전자레인지', '책상', '책장', '침대', '옷장', '신발장', '싱크대', '풀옵션'),
            NO_APPLIANCE_FILTER,
        ),
        '반려동물': '--option 반려동물가능',
        '전세대출': '--option 대출가능',
        '주차': '--option 주차가능',
        '옥탑방': '--option 옥탑',
        '복층형원룸': '--option 복층',
        '오픈형원룸': '--structure 오픈형',
        '분리형원룸': '--structure 분리형',
        '원룸': '-t 원룸',
        '투룸': '--room-count 2개',
        '쓰리룸': '--room-count 3개',
        '포룸이상': '--room-count 4개이상',
        '즉시입주': '--move-in-now',
        '바로입주': '--move-in-now',
        '지하층': '--floor 반지하',
        '지상': '--floor 1층,2~5층,6~9층,10층이상',
    },
    by_option_value={
        '--type': {
            '빌라': '당근에는 빌라 분류가 없습니다. 작성자가 방 수로 고른 -t 원룸,투룸 으로 찾으세요 (투룸은 투룸 이상)',
            '쓰리룸': '-t 투룸 (투룸 이상)',
            '단독·다가구': '-t 주택',
        },
    },
    by_option={
        **CONDITION_OPTION_HINTS,
        '--radius': (
            '당근 웹에는 반경이 없어 지도 화면 범위로 찾습니다. 범위 크기는 --zoom 으로 줍니다 (구 이름·--lat/--lng·--address 와 함께. '
            '--station·--university 주변 목록은 당근이 범위를 정합니다)'
        ),
        '--expand': '당근 웹에 주변 동을 합쳐 보는 기능이 없어 뺐습니다. 주변 동은 동마다 따로 찾으세요',
    },
)
# 통근 검색은 역 주변 매물 목록이라 단지 세대수·주차대수 조건을 서버가 받지 않아 옵션을 두지 않는다 (2026-10-31 실측:
# 강남역 10분 안 역들의 아파트 전세 19건이 --household-min 500 을 줘도 같았다). search listings 에서 옮겨 쓰면 동 이름 검색으로 안내한다
COMPLEX_CONDITION_IN_COMMUTE: str = (
    '통근 검색(역 주변 매물 목록)은 단지 세대수·주차대수 조건을 받지 않습니다. 이 조건은 '
    'jibsa daangn search listings <동 이름> -t 아파트 --household-min … 처럼 동 이름으로 찾으세요'
)
# 통근 검색의 안내는 매물 조건 안내에 통근 검색의 위치·범위 안내를 더한다. 매물 검색의 안내를 통째로 물려받았더니 통근 검색에
# 한 번도 없던 --city·--expand 를 '없앴습니다'·'뺐습니다' 라고 했다 (2026-11-12 리뷰)
COMMUTE_HINTS: UsageHints = LISTING_HINTS._replace(by_option={
    **CONDITION_OPTION_HINTS,
    '--city': f'통근 검색에는 --city 가 없습니다. 회사 위치의 {SAME_NAME_REGION_HINT}',
    '--expand': '통근 검색에는 --expand 가 없습니다. 어느 역까지 넣을지는 --max-minutes(회사 역까지 지하철 시간)로 정합니다',
    # 매물 검색의 --radius 안내(--zoom 으로 범위)는 통근 검색에 --zoom 이 없어 맞지 않는다 (2026-11-12 리뷰). 매물 검색에도
    # --radius 가 없어 역 하나는 반경 없이 역 주변 목록으로 안내한다 (같은 날 리뷰: 안내대로 --radius 를 주면 또 오류였다)
    '--radius': (
        '통근 검색은 반경을 받지 않고 역마다 당근 역 주변 매물을 줍니다. 어느 역까지 넣을지는 --max-minutes(회사 역까지 지하철 시간)로 '
        '정합니다. 역 하나의 주변 매물은 jibsa daangn search listings --station <역> 으로 찾으세요 (범위는 당근이 정합니다)'
    ),
    '--zoom': (
        '통근 검색은 지도 화면 범위를 받지 않고 역마다 당근 역 주변 매물을 줍니다. 어느 역까지 넣을지는 --max-minutes 로 정합니다'
    ),
    '--household-min': COMPLEX_CONDITION_IN_COMMUTE,
    '--household-max': COMPLEX_CONDITION_IN_COMMUTE,
    '--parking-min': COMPLEX_CONDITION_IN_COMMUTE,
})
# 지역 자리에 준 이름이 단지 이름일 때 (`_complex_name_hint`): 찾은 단지 ID 로 부를 명령, 단지를 못 찾았을 때 찾는 법
COMPLEX_COMMANDS_HINT: str = (
    '단지 정보는 jibsa daangn complex <ID>, 실거래는 real-price <ID>, 매물은 search listings --complex <ID> 로 찾으세요'
)
COMPLEX_NAME_SEARCH_HINT: str = '단지 이름이면 jibsa daangn search locations <단지 이름> 으로 단지 ID 를 찾으세요'


@contextmanager
def _complex_name_hint(
    client: DaangnClient, query: str, *, station_alternative: str = '', station_hint: str = '',
) -> Iterator[None]:
    """동·구를 받는 명령(search listings·search commute·region-real-price·region-reviews·search complexes)에 단지 이름을 주어
    지역을 못 찾았으면, 단지 ID 와 단지 명령을 힌트로 알린다.

    전에는 '동·구 이름으로 다시 찾으라' 만 알려 에이전트가 단지 ID 를 찾는 데 호출을 한 번 더 썼다 (2026-10-31 재검증:
    search complexes 헬리오시티 → REGION_NOT_FOUND → search locations 헬리오시티). 지역을 못 찾았거나 비슷한 지역만 있을
    때만 단지 후보를 3곳 묻는다 (요청 1회). 단지 검색이 실패하면 `search_complexes` 가 None(모름)을 주고, `_complexes_named` 가
    빈 목록처럼 받아(`or []`) 원래 힌트에 찾는 법만 붙인다.

    역 이름은 단지 이름이라고 하지 않고 역이라고 알린다. 이름에 역 이름이 들어간 단지(강남역우정에쉐르)가 있어 '강남역' 을
    '단지 이름입니다' 라고 했다 (2026-11-11 LLM 사용 시험: search complexes 강남역). 그런 단지는 뒤에 덧붙인다.

    비슷한 지역만 있을 때(`SimilarAreasError`)도 단지 후보를 묻는다. 지역 검색이 단지 이름에 엉뚱한 지역을 비슷하다고 주어
    단지 힌트가 빠졌다 (2026-11-12 리뷰·실측: search complexes 은마 → 충청남도 홍성군 은하면만 권했다). 이때는 '역삼' → 역삼동
    처럼 지역을 찾던 이름일 수도 있어 단지 이름이라고 하지 않고, 지역 후보는 두고 단지 후보를 뒤에 덧붙인다.

    Args:
        station_alternative: 역 이름일 때 덧붙일 다른 방법 (단지 목록은 다방·네이버의 역 반경 단지 목록). 마침표 없이 준다.
        station_hint: 역 이름을 받는 다른 입력이 있는 명령(search listings 의 --station)에서 역 이름일 때의 안내. 주면
            '동·구로만 찾는다' 대신 이것을 쓴다. 마침표 없이 준다.
    """
    try:
        yield
    except SimilarAreasError as exc:
        found = _complexes_named(client, query)
        exc.hint = f"{(exc.hint or '').rstrip('.')}. " + (
            f"단지 이름이면 이름에 {quoted(query, '이/가')} 들어간 단지: {found}. {COMPLEX_COMMANDS_HINT}" if found
            else COMPLEX_NAME_SEARCH_HINT
        )
        raise
    except RegionNotFoundError as exc:
        found = _complexes_named(client, query)
        if query.replace(' ', '').endswith('역'):
            hint = f"{quoted(query, '은/는')} 역 이름입니다. " + (
                station_hint or '이 명령은 동·구로만 찾으니 역이 있는 동 이름(예: 역삼동)으로 찾으세요'
            )
            if station_alternative:
                hint += f'. {station_alternative}'
            if found:
                hint += f". 이름에 {quoted(query, '이/가')} 들어간 단지: {found}. {COMPLEX_COMMANDS_HINT}"
            raise RegionNotFoundError(query, hint=hint) from None
        if not found:
            raise RegionNotFoundError(query, hint=f"{(exc.hint or '').rstrip('.')}. {COMPLEX_NAME_SEARCH_HINT}") from None
        raise RegionNotFoundError(
            query, hint=f"{quoted(query, '은/는')} 동·구가 아니라 단지 이름입니다: {found}. {COMPLEX_COMMANDS_HINT}",
        ) from None


def _station_named(client: DaangnClient, name: str) -> DaangnStation:
    """`--station` 의 역 (`find_station`). 없으면 search listings·search commute 가 같은 힌트로 끝난다.

    Raises:
        RegionNotFoundError: 이름이 같은 지하철역이 없을 때. 전에는 두 명령이 힌트를 따로 써 출퇴근 검색에는 역 후보를 보는
            법이 빠져 있었다 (2026-11-12 리뷰).
    """
    found = find_station(client, name)
    if found is None:
        raise RegionNotFoundError(
            name,
            hint=(
                "이름이 같은 지하철역이 없습니다. 역 이름(예: '역삼역')으로 다시 주세요. "
                "역 후보는 'jibsa daangn search locations <이름>' 의 stations 에 있습니다"
            ),
        )
    return found


def _complexes_named(client: DaangnClient, query: str) -> str:
    """이름에 `query` 가 들어간 단지 후보(3곳까지)를 'ID(주소)' 로 잇는다 (요청 1회). 없거나 단지 검색이 실패하면 ''."""
    key = query.replace(' ', '')
    candidates = search_complexes(client, query, limit=3, notes=[]) or []
    return ', '.join(
        f'{candidate.complex_id}({candidate.address or candidate.name})'
        for candidate in candidates if key in candidate.name.replace(' ', '')
    )


def _manage_cost_filtered_note(how: str) -> str:
    """--with-manage-cost 결과에 관리비가 null 인 매물이 있을 때의 안내. `how` 는 관리비 금액을 보는 법.

    당근 서버가 월세+관리비로 걸렀지만 목록 카드에는 관리비가 없다 (docs/daangn.md). 2026-10-31 에이전트 검증: 관리비가 null 이라
    '월세+관리비를 확인할 수 없다' 며 조건에 맞는 매물을 모두 뺐다. 문서에만 있던 내용이라 결과 옆에 둔다
    """
    return note(
        '참고',
        '--with-manage-cost 로 당근이 월세+관리비 기준으로 걸렀습니다. 목록에는 관리비가 없어 manage_cost_manwon 이 '
        f'null 이어도 조건에는 맞습니다. 관리비 금액은 {how}',
    )


# 사용법 오류가 난 명령(command_path)으로 힌트 표를 찾는다 (jibsa.cli.app.run). 통근 검색도 매물 조건을 같이 받는다
USAGE_HINTS: dict[str, UsageHints] = {
    'jibsa daangn search listings': LISTING_HINTS,
    'jibsa daangn search commute': COMMUTE_HINTS,
}
# 단지 ID 자리에 단지·지역 이름처럼 숫자가 아닌 값이나 preschools 의 예전 사용법을 줬을 때 단지 ID 를 찾는 법.
# 다음에 할 일을 알리는 힌트라 '--help 로 사용법을 확인하세요' 를 붙이지 않는다 (UsageHints·--fields·--next 힌트와 같다)
COMPLEX_ID_HINT: str = (
    "단지 ID 는 'jibsa daangn search complexes <동>' 이나 'jibsa daangn search locations <단지 이름>' 으로 찾습니다"
)
# 개발 호재 명령을 뺀 뒤 재개발·재건축 구역을 보는 곳
REDEVELOPMENT_HINT: str = (
    "당근 웹이 개발 호재를 없애 이 명령을 뺐습니다. 재개발·재건축 구역은 'jibsa naver search redevelopment <지역>' 으로 "
    "찾고 'jibsa naver redevelopment <구역 번호>' 로 봅니다"
)
# real-price --month 의 계약 연월 (YYYY-MM). 서버에는 YYYYMM 으로 보낸다
MONTH_PATTERN: re.Pattern[str] = re.compile(r'\d{4}-(0[1-9]|1[0-2])')
# 동·구를 받는 명령(지역 실거래·후기·단지 목록)의 지역 인자
REGION_ARGUMENT_HELP: str = "동 이름(예: '역삼동') 또는 구 이름(예: '강남구', '수원시 장안구'). 같은 이름이 여러 곳이면 '강남구 신사동' 처럼 구·시·도를 붙인다"
# 예전 문서(0.12.0 까지)대로 부른 사용법 오류에 바뀐 사용법을 알린다 (jibsa.cli.app.changed_usage_hint, #192). 없앤 명령은
# 그룹 경로 뒤에 그 이름을 붙여 찾는다. preschools 는 뺀 옵션을 줬을 때만 알리고, 지역·역 이름(띄어 써도)은 단지 ID
# 검사(`complex_id_value`)가 알린다
CHANGED_USAGE: dict[str, ChangedUsage] = {
    'jibsa daangn preschools': ChangedUsage(
        f'이 명령은 지역·역 이름·반경 대신 단지 ID 하나만 받습니다 (예: jibsa daangn preschools 10697092). {COMPLEX_ID_HINT}',
        removed_options=frozenset({'--lat', '--lng', '--radius', '--type', '-t', '--limit'}),
    ),
    'jibsa daangn price-trend': ChangedUsage(
        "--years 를 없앴습니다. 당근 웹 시세 그래프 탭처럼 --period '1년'·'3년'·'전체' 로 주세요 (예: --period 3년)",
        removed_options=frozenset({'--years'}),
    ),
    'jibsa daangn good-neighborhoods': ChangedUsage(
        '--limit 을 없앴습니다. 당근 웹 좋은 동네 추천처럼 늘 5곳입니다. 다른 동은 --region 으로 지역을 바꿔 찾으세요',
        removed_options=frozenset({'--limit'}),
    ),
    'jibsa daangn developments': ChangedUsage(REDEVELOPMENT_HINT),
    'jibsa daangn development': ChangedUsage(REDEVELOPMENT_HINT),
    **{
        f'jibsa daangn {command}': ChangedUsage(CITY_REMOVED_HINT, removed_options=frozenset({'--city'}))
        for command in ('search listings', 'region-reviews', 'search complexes')
    },
    # 동·구를 다 받지 않는 명령은 공용 안내의 예시('강남구 신사동'·'서울 중구')를 따르면 또 막힌다. 인기 급상승 단지는 동을 받지
    # 않아 예전 사용법('역삼동 --city 강남구')의 --city 값인 구를 권한다 (2026-11-13 리뷰·실측: '강남구 신사동' 을 따르면 '동입니다')
    'jibsa daangn trending-complexes': ChangedUsage(
        '--city 를 없앴습니다. 이 명령은 동을 받지 않고 시·도·구 이름 하나를 받습니다. --city 에 주던 구 이름을 그대로 주세요 '
        "(예: jibsa daangn trending-complexes 강남구, 같은 이름 구는 '서울 중구' 처럼 시·도를 붙입니다). 지역을 빼면 전국입니다",
        removed_options=frozenset({'--city'}),
    ),
    'jibsa daangn popular-listings': ChangedUsage(
        "--city 를 없앴습니다. 이 명령은 동 이름만 받습니다. 같은 이름 동은 '강남구 신사동' 처럼 동 이름 앞에 구·시·도를 붙여 주세요",
        removed_options=frozenset({'--city'}),
    ),
    # 지역 실거래 정렬은 당근 웹처럼 서버 값 하나(매매 가격 순·전월세 최신 순)라 --sort 를 없앴다 (#215). 힌트는 명령마다
    # 하나라 두 옵션을 함께 앞에 둔다 (--sort 만 줬는데 --city 안내부터 읽지 않게, 2026-11-12 리뷰)
    'jibsa daangn region-real-price': ChangedUsage(
        f'--city·--sort 를 없앴습니다. {SAME_NAME_REGION_HINT}. '
        '정렬은 당근 웹처럼 매매는 가격 순(최근 공개일부터), 전세·월세는 최신 순으로 정해져 있습니다',
        removed_options=frozenset({'--city', '--sort'}),
    ),
    # 학교는 같은 이름이 여러 곳이면 후보의 학교 코드로 고른다 (#215)
    'jibsa daangn school': ChangedUsage(
        '--city 를 없앴습니다. 같은 이름 학교가 여러 곳이면 에러의 candidates 에 나온 school_code 로 다시 부르세요 '
        '(예: jibsa daangn school B100000749)',
        removed_options=frozenset({'--city'}),
    ),
}
# --trade 없이 가격만 준 매물 검색의 안내 (_listing_conditions)
NO_TRADE_WITH_PRICE_NOTE: str = (
    '--trade 없이 가격 조건만 주면 당근 웹처럼 거래 유형을 고르지 않아, 그 금액이 없는 다른 거래(전세·매매 등) 매물도 나옵니다. '
    '한 거래 유형만 찾으려면 --trade 를 함께 주세요 (예: --trade 월세)'
)
# 아파트 단지 조건. 단지 하나를 보는 --complex 와는 함께 쓸 수 없다
HouseholdMinOption = Annotated[int | None, typer.Option(min=0, help='단지 세대수 하한 (-t 를 주지 않거나 아파트·오피스텔을 넣을 때)')]
HouseholdMaxOption = Annotated[int | None, typer.Option(min=0, help='단지 세대수 상한 (-t 를 주지 않거나 아파트·오피스텔을 넣을 때)')]
ParkingMinOption = Annotated[float | None, typer.Option(min=0, help='세대당 주차대수 하한 (-t 를 주지 않거나 아파트·오피스텔을 넣을 때)')]


def complex_id_value(value: str) -> int:
    """단지 ID 인자·옵션의 값 검사 (`parser`). 숫자가 아니면(단지·지역 이름) 단지 ID 를 찾는 법을 힌트로 붙인다.

    Click 정수 검사는 'not a valid int range' 와 --help 안내만 줘, 단지 이름을 준 에이전트가 단지 ID 를 찾는 법을 알 수
    없었다 (2026-11-11 리뷰: complex·real-price 등 6곳). 다른 ID 인자의 Click 정수 검사처럼 int() 로 읽어 받는 꼴이 같다
    (앞뒤 공백·CR 도 받는다). 자릿수는 막지 않는다. 당근은 단지 ID 를 문자열로 받아 19자리에도 단지를 찾지 못했다고
    답하고 (2026-11-11 실측), 4300자가 넘는 숫자는 int() 가 ValueError 를 내 여기서 같은 힌트로 막힌다.

    인자 이름은 Click 이 채운다 ('complex_id', '--complex'). 함수 이름은 터미널(Rich) --help 에 인자 형식
    `<complex_id_value>` 로 보여 앞에 `_` 를 붙이지 않는다. 에이전트가 받는 파이프 --help 에는 인자 형식이 나오지 않아
    `<int>` 로 보이게 할 ParamType 은 따로 두지 않는다.
    """
    try:
        complex_id = int(value)
    except ValueError:
        complex_id = 0
    if complex_id < 1:
        # 값 뒤에 조사를 붙이지 않는다 (숫자·ID 도 온다, code-style 1절)
        raise HintedBadParameter(f"단지 ID 가 아닙니다: '{value}'. 1 이상의 숫자 단지 ID 를 받습니다", None, COMPLEX_ID_HINT)
    return complex_id


def _require_one_place(name: str | None, lat: float | None, lng: float | None, param_hint: str, what: str) -> None:
    """이름과 좌표 중 정확히 하나를 받는다. 둘 다 주면 어느 쪽으로 찾았는지 헷갈린다.

    `what` 은 이 명령이 이름 자리에 받는 것 ('동·구 이름'). 전에는 늘 '동 이름' 이라 구 이름도 받는 search complexes, 역·대학·단지
    이름도 받는 search locations 에서 받는 입력을 좁게 알렸다 (2026-11-12 리뷰).
    """
    require_korea(lat, lng)
    has_coordinate = lat is not None and lng is not None
    if name is None and not has_coordinate:
        raise typer.BadParameter(f'{what} 또는 --lat/--lng 를 주세요', param_hint=param_hint)
    if name is not None and has_coordinate:
        raise typer.BadParameter(
            f"{what}{particle(what, '과/와')} --lat/--lng 는 함께 줄 수 없습니다. 하나만 주세요", param_hint=param_hint,
        )


def _listing_conditions(
    *,
    property_type: list[str] | None,
    trade: list[str] | None,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
    with_manage_cost: bool,
    area_min: float | None,
    area_max: float | None,
    floor: list[str] | None,
    room_count: list[str] | None,
    structure: list[str] | None,
    approval: str | None,
    deal: str | None,
    option: list[str] | None,
    move_in_now: bool,
    yearly_rent_min: int | None = None,
    yearly_rent_max: int | None = None,
    household_min: int | None = None,
    household_max: int | None = None,
    parking_min: float | None = None,
) -> tuple[DaangnListingConditions, list[str]]:
    """매물 검색 옵션(search listings·commute·--complex 공통)을 검색 조건 묶음으로 바꾼다.

    --trade 없이 금액 조건만 줬다는 안내와 매물 종류 안내를 함께 돌려준다. 조건 조합이 잘못되면 묶음을
    만들 때 ValidationError 가 나므로 `handle_errors` 안에서 부른다.

    Raises:
        typer.BadParameter: 모르는 라벨이거나 사용승인일·거래 방식을 둘 이상 줬을 때, 월세 범위 없이 --with-manage-cost 를 줬을 때,
            준 --trade 에 금액 조건이 걸릴 거래가 없을 때 (연세만 + 월세 범위, 연세 없이 연세 범위 등).
    """
    if with_manage_cost and rent_min is None and rent_max is None:
        # 월세 범위의 비교 기준만 바꾸는 옵션이라 혼자서는 서버가 거르지 않는다 (2026-10-23 실측: 세종 반곡동 월세 122건이
        # 옵션을 줘도 122건). 받아 두면 관리비까지 따져 거른 줄 안다
        raise typer.BadParameter('월세 범위를 월세 + 관리비로 비교하는 옵션이라 --rent-min/--rent-max 와 함께 주세요', param_hint='--with-manage-cost')
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type', LISTING_HINTS)
    has_rent = rent_min is not None or rent_max is not None
    has_yearly = yearly_rent_min is not None or yearly_rent_max is not None
    has_price = price_min is not None or price_max is not None
    has_deposit = deposit_min is not None or deposit_max is not None
    trade_types: list[str] = split_csv(trade, TRADE_TYPES, '--trade')
    trade_notes: list[str] = []
    if has_rent and trade_types and set(trade_types) == {'연세'}:
        # 연세 금액을 월세 범위로 옮겨 쓰기 쉽다. 아래 공통 검사도 막지만 '월세·단기임대 거래에만' 만 알려 연세 범위 옵션을
        # 알리지 않는다. 당근 웹도 연세만 고르면 월세 범위를 보여 주지 않는다 (services2 `$c`: 월세 범위는 MONTH·SHORT 일 때만)
        raise HintedBadParameter(
            '--trade 연세 에는 월세가 없어 --rent-min/--rent-max 를 적용할 수 없습니다',
            '--trade',
            '연세(1년치를 한 번에 내는 금액) 범위는 --yearly-rent-min/--yearly-rent-max 로 주세요 (만원). 보증금은 --deposit-min/--deposit-max',
        )
    if trade_types:
        # 준 거래 유형에 가격 조건이 걸릴 유형이 없으면(전세 + 월세 상한, 월세 + 연세 상한) 서버가 조건을 무시해 입력 오류로 막는다.
        # 준 유형은 그대로다. 연세는 당근에만 있어 안내에 당근 거래 유형(`TRADE_TYPES`)을 쓴다
        trade_types, trade_notes = infer_trade_types(
            trade_types, rent=has_rent, price=has_price, deposit=has_deposit, yearly=has_yearly, allowed=TRADE_TYPES,
        )
    elif has_rent or has_price or has_deposit or has_yearly:
        # 당근 웹은 거래 유형을 고르지 않으면 가격 범위만 보내 그 금액이 없는 다른 거래 매물도 나온다. 예전에는 jibsa 가 가격
        # 조건으로 거래 유형을 짐작해 넣었다. 웹처럼 짐작하지 않고 알린다 (#215, 2026-11-11 사용자 결정)
        trade_notes.append(note('참고', NO_TRADE_WITH_PRICE_NOTE))
    approvals = split_csv([approval] if approval else None, tuple(BUILDING_APPROVAL_FILTER_BY_LABEL), '--approval')
    deals = split_csv([deal] if deal else None, tuple(DEAL_FILTER_BY_LABEL), '--deal')
    if len(approvals) > 1 or len(deals) > 1:
        raise typer.BadParameter('사용승인일과 거래 방식은 하나만 받습니다', param_hint='--approval / --deal')
    conditions = DaangnListingConditions(
        property_types=property_types,
        trade_types=trade_types,
        deposit_min=deposit_min,
        deposit_max=deposit_max,
        rent_min=rent_min,
        rent_max=rent_max,
        yearly_rent_min=yearly_rent_min,
        yearly_rent_max=yearly_rent_max,
        price_min=price_min,
        price_max=price_max,
        rent_includes_manage_cost=with_manage_cost,
        area_min=area_min,
        area_max=area_max,
        floors=split_csv(floor, tuple(FLOOR_FILTER_BY_LABEL), '--floor', LISTING_HINTS),
        room_counts=split_csv(room_count, tuple(ROOM_COUNT_FILTER_BY_LABEL), '--room-count', LISTING_HINTS),
        structures=split_csv(structure, tuple(STRUCTURE_FILTER_BY_LABEL), '--structure', LISTING_HINTS),
        building_approval=approvals[0] if approvals else None,
        deal=deals[0] if deals else None,
        options=split_csv(option, tuple(OPTION_FILTER_BY_LABEL), '--option', LISTING_HINTS),
        move_in_now=move_in_now,
        household_min=household_min,
        household_max=household_max,
        parking_min=parking_min,
    )
    return conditions, trade_notes + property_type_notes(property_types, conditions.structures)


@search_app.command('locations')
def region_command(
    keyword: Annotated[
        str | None,
        typer.Argument(help='지역·역·대학·학교·단지 이름 (예: 역삼동, 강남구, 역삼역, 연세대학교, 은마). --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    limit: Annotated[int, typer.Option(min=1, max=COMPLEX_LIST_MAX_LIMIT, help='최대 단지 후보 수 (다른 후보에는 적용하지 않음). 이름이 맞는 단지가 앞에 온다')] = COMPLEX_CANDIDATE_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """당근 웹 지도 검색창처럼 이름에 맞는 지역·지하철역·대학·초중고·단지 후보를 칸별로 준다 (기본 --limit 이면 요청 5회, 단지 후보 50곳마다 1회 더). 좌표면 그 동.

    결과의 이름을 그대로 다른 명령에 넘긴다: 지역은 search listings <지역>, 역은 --station, 대학은 --university,
    학교는 school, 단지는 complex_id 를 --complex·complex 에.
    """
    _require_one_place(keyword, lat, lng, 'KEYWORD', '지역·역·대학·학교·단지 이름')
    with handle_errors(SOURCE), DaangnClient() as client:
        if lat is not None and lng is not None:
            try:
                region = region_by_coordinate(client, lat, lng)
            except FeedQueryRejectedError:
                raise map_query_rejected_error('search locations') from None
            emit({'lat': lat, 'lng': lng, 'results': [region.model_dump()]}, pretty)
            return
        # 좌표가 없으면 _require_one_place 가 이름을 요구했다
        assert keyword is not None
        query = ' '.join(keyword.split())
        # 웹 검색창처럼 검색어를 통째로 보낸다. 지역 검색은 띄어 쓴 이름도 받아 resolve_area(마지막 낱말로 찾고 앞 낱말로 좁힘)와
        # 같은 곳을 준다 (2026-11-12 실측: '강남구 신사동' → 서울특별시 강남구 신사동 1곳. 2026-11-12 리뷰 오탐)
        results = [_area_result(area) for area in search_areas(client, query)]
        # 지역 칸 말고는 덤 후보라, 한 칸이 실패해도 다른 칸과 받은 후보는 돌려주고 notes 로 알린다 (search_complexes 와 같다).
        # 실패한 칸은 '후보 없음'([]) 이 아니라 모름(null) 이다. 요청 제한은 다음 칸도 같은 제한에 걸리므로 바로 올린다
        notes: list[str] = []
        stations = _optional_section(notes, '역 검색', '역 후보를', lambda: [
            {'name': station_label(station)} for station in search_stations(client, query)
        ])
        # 대학 칸도 검색어를 통째로 보낸다 (웹 검색창과 같다). --university(find_university)는 첫 낱말로 찾아 맞추지만, 통째로
        # 보내도 캠퍼스까지 붙인 이름을 찾아 두 길이 같은 캠퍼스를 준다 (2026-11-12 실측: '연세대학교 신촌캠퍼스'·'서울대학교
        # 관악캠퍼스' → 그 캠퍼스 1곳씩. 2026-11-12 리뷰 오탐)
        universities = _optional_section(notes, '대학 검색', '대학 후보를', lambda: _university_candidates(client, query, notes))
        schools = _optional_section(notes, '학교 검색', '학교 후보를', lambda: _school_candidates(client, query, notes))
        found_complexes = search_complexes(client, query, limit=limit, notes=notes)
        complexes = None if found_complexes is None else [candidate.model_dump() for candidate in found_complexes]
        emit({
            'keyword': query,
            'results': results,
            'stations': stations,
            'universities': universities,
            'schools': schools,
            'complexes': complexes,
        }, pretty, notes=notes)


def _area_result(area: DaangnArea) -> dict[str, Any]:
    """지역 후보 하나. 비어 있는 시·군·구(시·도·세종 동)·동(시·도·구)은 해당 없음이라 키를 뺀다."""
    return {
        'level': area.level,
        'name1': area.name1,
        **({'name2': area.name2} if area.name2 else {}),
        **({'name3': area.name3} if area.name3 else {}),
        'region_id': area.region_id,
    }


def _university_candidates(client: DaangnClient, query: str, notes: list[str]) -> list[dict[str, Any]]:
    """`search locations` 의 대학 칸. 대학 검색이 받는 수(`UNIVERSITY_CANDIDATES`)만큼 다 와 잘렸을 수 있으면 `notes` 로 알린다.

    당근 대학 검색은 다음 쪽을 주지 않는다. 알리지 않으면 잘린 목록이 전부로 읽혀 뒤의 캠퍼스·대학원이 당근에 없다고 볼 수 있다
    (2026-11-13 리뷰: 20곳만 받던 때 고려대학교 23곳 중 치의학대학원 안암캠퍼스 등 3곳이 알림 없이 빠졌다).
    """
    pois, cut = search_universities(client, query)
    if cut:
        notes.append(note(
            '일부',
            f'{quoted(query, "이/가")} 들어간 대학이 {UNIVERSITY_CANDIDATES}곳보다 많을 수 있어 당근 순서로 앞 {UNIVERSITY_CANDIDATES}곳만 '
            '봤습니다. 찾는 캠퍼스·대학원이 없으면 그 이름까지 붙여 다시 찾으세요',
        ))
    return [
        {'name': university_label(poi), **({'address': poi.jibun_address} if poi.jibun_address else {})}
        for poi in pois
    ]


def _school_candidates(client: DaangnClient, query: str, notes: list[str]) -> list[dict[str, Any]]:
    """`search locations` 의 학교 칸. 첫 `SCHOOL_CANDIDATE_LIMIT` 곳에서 잘렸으면 `notes` 로 알린다.

    알리지 않으면 잘린 목록이 전부로 읽혀 찾는 학교가 당근에 없다고 볼 수 있다 ('중앙초등학교' 는 86곳, 2026-11-12 리뷰).
    """
    found, has_more = search_school_candidates(client, query)
    if has_more:
        notes.append(note(
            '일부',
            f'{quoted(query, "이/가")} 들어간 학교가 {SCHOOL_CANDIDATE_LIMIT}곳보다 많아 당근 순서로 앞 {SCHOOL_CANDIDATE_LIMIT}곳만 '
            '봤습니다. 이름이 그대로 같은 학교가 먼저 옵니다. 찾는 학교가 없으면 이름 앞에 지역을 붙여 다시 찾으세요',
        ))
    return [
        {'name': school.sch_nm, **({'address': school.sch_addr} if school.sch_addr else {}), 'school_code': school.sch_cd}
        for school in found
    ]


def _optional_section(
    notes: list[str], what: str, subject: str, fetch: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]] | None:
    """`search locations` 의 덤 칸 하나. 실패하면(요청 제한 제외) None(모름)과 그 이유를 `notes` 에 남긴다.

    빈 목록으로 두면 그 이름의 역·대학·학교가 없다는 뜻으로 읽혀 None 이다 (값이 없을 때의 규칙, 2026-11-12 리뷰).
    """
    try:
        return fetch()
    except RateLimitedError:
        raise
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn %s failed (%s); continuing without it', what, exc)
        notes.append(note('실패', partial_failure_note(exc, what, subject)))
        return None


def _station_resume(station: DaangnStation) -> dict[str, Any]:
    """역 주변 목록을 이어 받을 때 역을 다시 찾지 않도록 이어 받기 표에 담을 역 (역 ID 는 출력에서 빠져 따로 담는다)."""
    return {'m': 'station', 'station': {**station.model_dump(), 'station_id': station.station_id}}


def _university_resume(university: DaangnUniversity) -> dict[str, Any]:
    """대학 주변 목록을 이어 받을 때 대학을 다시 찾지 않도록 이어 받기 표에 담을 대학 (대학 ID 는 출력에서 빠져 따로 담는다)."""
    return {'m': 'university', 'university': {**university.model_dump(), 'university_id': university.university_id}}


def _require_one_target(
    region: str | None,
    station: str | None,
    university: str | None,
    lat: float | None,
    lng: float | None,
    param_hint: str,
    address: str | None = None,
) -> None:
    """지역 이름·`--station`·`--university`·`--address`·`--lat/--lng` 중 정확히 하나를 받는다 (웹 검색창에서 칸 하나를 고르는 것과 같다)."""
    require_korea(lat, lng)
    given = [value is not None for value in (region, station, university, address)] + [lat is not None and lng is not None]
    if sum(given) == 0:
        raise typer.BadParameter('지역 이름, --station, --university, --address, --lat/--lng 중 하나를 주세요', param_hint=param_hint)
    if sum(given) > 1:
        raise typer.BadParameter(
            '지역 이름, --station, --university, --address, --lat/--lng 는 함께 줄 수 없습니다. 하나만 주세요', param_hint=param_hint,
        )


# 지역 이름을 받는 매물·통근 검색이 지역을 못 찾았을 때 덧붙이는 다른 입력
OTHER_PLACE_INPUTS: str = '역은 --station, 대학은 --university, 도로명 주소는 --address, 좌표는 --lat/--lng 로 찾습니다'


@search_app.command('listings')
def search_command(
    region: Annotated[
        str | None,
        typer.Argument(help="동·구 이름 (예: 역삼동, 강남구, '강남구 신사동'). 동은 웹 지도에서 동을 누른 목록(그 동 매물만), 구는 웹 지도의 구 화면 범위 목록")
    ] = None,
    station: StationOption = None,
    university: UniversityOption = None,
    address: AddressOption = None,
    complex_id: Annotated[
        int | None,
        typer.Option(
            '--complex', parser=complex_id_value, metavar='<int>',
            help='단지 ID. 지역·좌표 대신 해당 단지의 현재 매물 조회. -t 를 안 주면 당근 웹 단지 화면처럼 아파트·주택·오피스텔·원룸·투룸만 (상가 등은 -t 로)',
        )
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    zoom: ZoomOption = None,
    property_type: ListingPropertyTypeOption = None,
    trade: TradeOption = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    yearly_rent_min: YearlyRentMinOption = None,
    yearly_rent_max: YearlyRentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    with_manage_cost: WithManageCostOption = False,
    area_min: AreaMinOption = None,
    area_max: AreaMaxOption = None,
    floor: FloorOption = None,
    room_count: RoomCountOption = None,
    structure: StructureOption = None,
    approval: ApprovalOption = None,
    deal: DealOption = None,
    option: ExtraOption = None,
    move_in_now: MoveInNowOption = False,
    household_min: HouseholdMinOption = None,
    household_max: HouseholdMaxOption = None,
    parking_min: ParkingMinOption = None,
    limit: Annotated[int, typer.Option(min=1, max=LISTING_MAX_LIMIT, help='조회할 매물 수 (제외 전)')] = 20,
    details: Annotated[
        bool,
        typer.Option(
            '--details',
            help=f'매물마다 상세를 1회씩 더 받아 목록에 없는 관리비·등록일·번지 주소·사용승인일·방 구조를 채운다. 요청이 매물 수만큼 늘어난다 (앞 {DETAILS_MAX}건)',
        ),
    ] = False,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """당근 웹에서 매물 목록이 나오는 화면과 같은 목록을 준다. 조건은 당근 서버에서 건다.

    동 이름은 웹 지도에서 동을 누른 목록처럼 그 동 매물만 최근 게시 순으로 준다. 구 이름, --lat/--lng, --address(도로명 주소
    의 좌표)는 웹 지도 화면(데스크톱 기준, --zoom)의 매물 목록을 최근 순으로, --station 은 웹 역 화면의 역 주변 목록을 역까지
    도보 분(walk_minutes)과 함께, --university 는 웹 대학 페이지의 대학 주변 목록을 준다. 이름은 당근 웹 검색창과 같이 정확히
    같은 곳만 찾는다.

    예: jibsa daangn search listings 역삼동 -t 원룸 --trade 월세 --deposit-max 1000 --rent-max 70 --option 반려동물가능
    예: jibsa daangn search listings --station 역삼역 -t 원룸 --trade 월세 --option 반려동물가능
    예: jibsa daangn search listings --university '연세대학교 신촌캠퍼스' -t 원룸 --trade 월세 --limit 10 --details
    예: jibsa daangn search listings --address '테헤란로 152' -t 오피스텔 --trade 월세
    예: jibsa daangn search listings 노형동 --trade 연세 --yearly-rent-max 1000

    결과에 next 가 있으면 같은 지역·조건에 --next <결과의 next 값> 을 붙여 이어 받는다. 이어 받을 때는 지역·역·대학을 다시 찾지 않는다.
    """
    position = decode_next(next_)
    require_finite('--parking-min', parking_min)
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('yearly-rent', yearly_rent_min, yearly_rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
        ('household', household_min, household_max),
    )
    complex_conditions = (household_min, household_max, parking_min)
    if complex_id is not None:
        if any(value is not None for value in (region, station, university, address, lat, lng, zoom, *complex_conditions)):
            raise typer.BadParameter(
                '--complex는 지역·역·대학·주소·좌표·줌·세대수·주차대수 조건과 함께 사용할 수 없습니다', param_hint='--complex',
            )
    else:
        _require_one_target(region, station, university, lat, lng, 'REGION', address=address)
    if zoom is not None and (station is not None or university is not None):
        raise typer.BadParameter(
            '--zoom 은 구 이름·--lat/--lng·--address 로 지도 화면 범위를 찾을 때만 씁니다. 역·대학 주변 목록은 당근이 범위를 정합니다',
            param_hint='--zoom',
        )
    if (station is not None or university is not None) and any(value is not None for value in complex_conditions):
        # 역 주변 매물 목록은 단지 세대수·주차대수 조건을 받지 않는다 (2026-10-31 실측: 강남역 아파트 전세 5억 이하에
        # --household-min 500·--parking-min 1.5 를 줘도 안 줘도 같은 4건이고 도시형·17세대 단지가 섞였다). 웹은 이 조건을 보내고
        # 서버가 무시해 결과가 조용히 틀리므로 막는다. 예전에는 반경 검색으로 바꿔 찾았다 (#215 에서 뺌)
        raise typer.BadParameter(
            '역·대학 주변 목록은 단지 세대수·주차대수 조건을 받지 않습니다. 이 조건은 동 이름으로 찾으세요',
            param_hint='--household-min / --household-max / --parking-min',
        )

    def emit_listings(result: ListingsResult, notes: list[str], resume: dict[str, Any] | None) -> None:
        # 서비스가 준 다음 위치에 검색 방식·찾은 위치를 더해 이어 받기 표를 만든다 (단지 매물은 이어 받지 않는다)
        next_position = getattr(result, 'next_position', None)
        next_token = encode_next({**resume, **next_position}) if resume is not None and next_position else None
        if details:
            # 결과마다 매물 모델이 달라(동·지도·역·대학·단지) 공통 Listing 으로 넘긴다. 하위 모델은 그대로 남는다
            found: list[Listing] = list(result.listings)
            listings, detail_notes = attach_details(client, found)
            result = result.model_copy(update={'listings': listings, 'returned': len(listings)})
            notes = notes + detail_notes
        elif with_manage_cost and any(listing.manage_cost_manwon is None for listing in result.listings):
            notes = notes + [_manage_cost_filtered_note('--details 로 채웁니다 (매물당 요청 1회)')]
        emit(result, pretty, notes=notes, next_token=next_token, fields=fields)

    def emit_map(
        center_lat: float,
        center_lng: float,
        map_zoom: int,
        place_notes: list[str],
        *,
        region: DaangnRegion | None = None,
        after: str | None = None,
        total: int | None = None,
        found_address: DaangnAddress | None = None,
        sidos: list[list[str]] | None = None,
    ) -> None:
        try:
            map_result = search_map_area(
                client, center_lat, center_lng, zoom=map_zoom, conditions=conditions, limit=limit, region=region,
                after=after, total=total, address=found_address, sidos=sidos,
            )
        except FeedQueryRejectedError:
            raise map_query_rejected_error('search listings') from None
        scope = [] if after is not None else [note(
            '범위',
            f'당근 웹 지도 화면(데스크톱, 줌 {map_zoom}, 가로 {map_result.width_km:g}km × 세로 {map_result.height_km:g}km) 안 '
            '매물을 웹 목록처럼 최근 순으로 줍니다. distance_km 는 화면 가운데까지의 거리라 순서와 상관없습니다. '
            '범위를 바꾸려면 --zoom 을 주세요 (1 작으면 가로·세로 2배)',
        )]
        emit_listings(
            map_result, common_notes + place_notes + scope + map_result.notes,
            {
                'm': 'map', 'lat': center_lat, 'lng': center_lng, 'zoom': map_zoom,
                **({'address': found_address.model_dump()} if found_address else {}),
            },
        )

    def resume_search(position: dict[str, Any]) -> None:
        # 앞 결과가 찾은 위치(지도 범위·역·대학·동)로 바로 이어 받는다. 위치를 찾는 요청과 그 안내는 첫 결과에만 있다
        mode = position['m']
        # 앞 결과가 찾은 동·시·도는 다시 찾지 않는다 (요청을 아낀다). 동을 못 찾았으면(None) 서비스가 다시 찾아 본다
        found_region = DaangnRegion.model_validate(position['region']) if position.get('region') else None
        sidos = position.get('sidos')
        if mode == 'map':
            emit_map(
                float(position['lat']), float(position['lng']), int(position['zoom']), [], region=found_region,
                after=str(position['after']), total=position.get('total'),
                found_address=DaangnAddress.model_validate(position['address']) if position.get('address') else None,
                sidos=sidos,
            )
        elif mode == 'station':
            found_station = DaangnStation.model_validate(position['station'])
            station_result = search_station(
                client, found_station, conditions=conditions, limit=limit, after=str(position['after']), region=found_region,
                sidos=sidos,
            )
            emit_listings(station_result, common_notes + station_result.notes, _station_resume(found_station))
        elif mode == 'university':
            found_university = DaangnUniversity.model_validate(position['university'])
            university_result = search_university(
                client, found_university, conditions=conditions, limit=limit, after=str(position['after']),
                region=found_region, sidos=sidos,
            )
            emit_listings(university_result, common_notes + university_result.notes, _university_resume(found_university))
        else:
            area = DaangnArea.model_validate(position['area'])
            dong_result = search_dong(
                client, area, conditions=conditions, limit=limit, after=str(position['after']), total=position.get('total'),
                received=int(position.get('received') or 0),
            )
            emit_listings(dong_result, common_notes + dong_result.notes, {'m': 'dong', 'area': area.model_dump()})

    with handle_errors(SOURCE), DaangnClient() as client:
        conditions, common_notes = _listing_conditions(
            property_type=property_type, trade=trade,
            deposit_min=deposit_min, deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max,
            price_min=price_min, price_max=price_max, with_manage_cost=with_manage_cost,
            area_min=area_min, area_max=area_max, floor=floor, room_count=room_count,
            structure=structure, approval=approval, deal=deal, option=option, move_in_now=move_in_now,
            yearly_rent_min=yearly_rent_min, yearly_rent_max=yearly_rent_max,
            household_min=household_min, household_max=household_max, parking_min=parking_min,
        )
        if position is not None:
            resume_search(position)
            return
        if complex_id is not None:
            # 단지 하나의 현재 매물 (당근 단지 화면 순이라 거리가 없다)
            complex_result = list_complex_listings(client, complex_id, conditions=conditions, limit=limit)
            emit_listings(complex_result, common_notes + complex_result.notes, None)
            return
        if lat is not None and lng is not None:
            emit_map(lat, lng, zoom or POINT_ZOOM, [])
            return
        if address is not None:
            # 웹 검색창 주소 모드처럼 후보 하나의 좌표를 받아 그 자리의 지도 화면 범위 목록이다 (좌표 검색과 같은 줌)
            found_address = find_address(client, address)
            emit_map(found_address.lat, found_address.lng, zoom or POINT_ZOOM, [note(
                '범위',
                f'{found_address.label} 의 좌표를 가운데에 둔 지도 화면 범위입니다',
            )], found_address=found_address)
            return
        if station is not None:
            found_station = _station_named(client, station)
            station_result = search_station(client, found_station, conditions=conditions, limit=limit)
            emit_listings(station_result, common_notes + [note(
                '범위',
                f'{found_station.name} 주변 매물을 당근 웹 역 화면의 목록 순서로 줍니다 (walk_minutes 는 역까지 도보 분)',
            )] + same_station_notes(found_station) + station_result.notes, _station_resume(found_station))
            return
        if university is not None:
            found_university = find_university(client, university)
            university_result = search_university(client, found_university, conditions=conditions, limit=limit)
            emit_listings(university_result, common_notes + [note(
                '범위',
                f'{found_university.name} 주변 매물을 당근 웹 대학 페이지의 목록 순서로 줍니다 (범위는 당근이 정한다. '
                'distance_km 는 대학까지의 직선거리)',
            )] + university_result.notes, _university_resume(found_university))
            return
        # _require_one_target 이 나머지는 지역 이름을 요구했다
        assert region is not None
        with _complex_name_hint(client, region, station_hint=f"역 주변 매물은 --station '{region}' 으로 찾습니다"):
            area = resolve_area(client, region, other_inputs=OTHER_PLACE_INPUTS)
        if area.level == '동':
            # 동인지 구인지는 이름을 찾아야 알아(--zoom 은 구 이름에 쓴다) 지역을 찾은 뒤에 막는다. 이름 모양('…동')으로 짐작하지
            # 않는다 (2026-11-12 리뷰 오탐: 요청 전에 막으라고 했다)
            if zoom is not None:
                raise typer.BadParameter(
                    '--zoom 은 구 이름·--lat/--lng·--address 로 지도 화면 범위를 찾을 때만 씁니다. 동은 그 동 매물 목록이라 범위가 없습니다',
                    param_hint='--zoom',
                )
            result = search_dong(client, area, conditions=conditions, limit=limit)
            emit_listings(result, common_notes + result.notes, {'m': 'dong', 'area': area.model_dump()})
            return
        district = DaangnRegion(name1=area.name1, name2=area.name2, region_id=area.region_id)
        emit_map(area.lat, area.lng, zoom or area.zoom, [note(
            '범위',
            f'{area.full_name}{particle(area.full_name, "은/는")} 구라 웹 지도의 구 화면처럼 구 중심의 지도 범위로 찾았습니다. '
            '범위가 사각형이라 이웃 구 매물도 섞이고 구 전체가 다 들어가지 않을 수 있습니다. 동 하나는 동 이름으로 찾으세요',
        )], region=district)


@app.command('listing')
def item_command(
    item_id: Annotated[int, typer.Argument(min=1, help='당근 매물 ID (search listings 결과의 id)')],
    trade: Annotated[
        str | None,
        typer.Option(
            '--trade',
            help='보여 줄 거래 조건: 매매, 전세, 월세, 단기임대, 연세. search listings 결과의 trade_type 을 넘기면 목록과 같은 가격이 나온다. 기본은 대표 조건이고, 매물에 없는 조건이면 대표 조건을 보여 주고 notes 로 알린다',
        )
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (옵션·관리비·입주일·주차). 사진·상세 설명·문의는 url 의 원 사이트에서."""
    trade_type = split_csv([trade], TRADE_TYPES, '--trade') if trade is not None else []
    if len(trade_type) > 1:
        raise typer.BadParameter(f"거래 조건은 하나만 받습니다 ({', '.join(TRADE_TYPES)} 중 하나)", param_hint='--trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        detail = get_listing(client, item_id, trade_type[0] if trade_type else None)
        emit(detail, pretty, notes=detail.notes)


@app.command('complex')
def complex_command(
    complex_id: Annotated[
        int,
        typer.Argument(
            parser=complex_id_value, help='단지 ID (search locations <단지 이름> 의 complexes, 아파트·오피스텔 listing 의 complex_id)'
        )
    ],
    pretty: PrettyOption = None,
) -> None:
    """단지 정보·평형·가까운 역·학교·현재 매물 수. 거주 후기는 수만 주고 내용은 url 의 원 사이트에서."""
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_complex(client, complex_id)
        emit(result, pretty, notes=result.notes)


@app.command('real-price')
def real_price_command(
    complex_id: Annotated[
        int | None,
        typer.Argument(
            parser=complex_id_value,
            help='단지 ID (search locations <단지 이름> 의 complexes, 아파트·오피스텔 listing 의 complex_id). --item 을 주면 생략',
        )
    ] = None,
    item: Annotated[
        int | None,
        typer.Option('--item', min=1, help='매물 ID. 단지 대신 그 매물이 있는 건물의 비슷한 면적 실거래를 본다')
    ] = None,
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세 중 하나')] = '매매',
    area: Annotated[
        int | None,
        typer.Option(min=1, help='아파트형이 아닌 단지의 전용면적 묶음 (complex 결과의 pyeongs[].area_group, 예: 84). 단지로 볼 때만. 아파트형은 당근 웹처럼 --pyeong 으로만 고른다. 기본 전체 평형')
    ] = None,
    pyeong: Annotated[
        int | None,
        typer.Option(
            '--pyeong', min=1,
            help='공급 평형 묶음 (complex 결과의 pyeongs[].pyeong, 예: 32). 아파트형 단지만, 당근 웹 평형 탭과 같다. 기본 전체 평형',
        )
    ] = None,
    # 기본 120건(약 4~5천 토큰)이지만 낮추지 않는다. 에이전트는 대개 가이드의 '처음에는 작게' 를 따라 --limit 을 직접 준다
    # (2026-10-23 에이전트 검증: 이 명령을 부른 sonnet 2명 모두 --limit 8 을 줬다. 기본값으로 부른 건 검증에서 뺀 haiku 뿐이다)
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    years: Annotated[
        int | None,
        typer.Option(
            min=1, max=30,
            help='최근 몇 년 안 계약만 (오늘 기준). 당근은 기간을 받지 않아 최근 계약부터 넘기다 그 앞 거래가 나오면 멈춘다. 기본 기간 없음',
        ),
    ] = None,
    month: Annotated[
        str | None,
        typer.Option(
            '--month',
            help='한 달의 계약만 (YYYY-MM, 예: 2026-08. 당근 웹 시세 그래프에서 달을 누른 목록). 단지로 볼 때만, --years 와 함께 쓰지 않는다',
        ),
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 또는 매물 건물의 실거래가 (국토부 신고 기준, 최근 계약 순). cancelled: true 는 해제된 거래.

    예: jibsa daangn real-price 10667600 --pyeong 32 --years 3 --limit 1200
    예: jibsa daangn real-price 10667600 --pyeong 32 --month 2026-08
    """
    if (complex_id is None) == (item is None):
        raise typer.BadParameter('단지 ID 와 --item 중 하나만 주세요', param_hint='COMPLEX_ID / --item')
    if item is not None and (area is not None or pyeong is not None):
        raise typer.BadParameter('--area·--pyeong 은 단지 ID 로 볼 때만 씁니다 (매물은 비슷한 면적 거래가 온다)', param_hint='--area / --pyeong')
    if month is not None:
        if item is not None:
            # 웹 매물 실거래 쿼리(useTransactionArticlePagination_Query)에는 계약 연월 변수가 없다 (2026-11-12 번들 대조)
            raise typer.BadParameter('--month 는 단지 ID 로 볼 때만 씁니다 (당근 매물 건물 실거래는 달을 받지 않는다)', param_hint='--month')
        if years is not None:
            raise typer.BadParameter('--month(한 달)와 --years(최근 몇 년)는 함께 쓸 수 없습니다. 하나만 주세요', param_hint='--month / --years')
        if not MONTH_PATTERN.fullmatch(month):
            raise typer.BadParameter(f"계약 연월은 YYYY-MM 으로 주세요 (예: 2026-08): '{month}'", param_hint='--month')
    if area is not None and pyeong is not None:
        raise typer.BadParameter('--area(전용면적 묶음)와 --pyeong(공급 평형) 중 하나만 주세요', param_hint='--area / --pyeong')
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        result: DaangnRealPriceBaseResult
        if item is not None:
            result = get_listing_real_prices(client, item, trade_type=trade_types[0], limit=limit, years=years)
        else:
            # 위에서 단지 ID 와 --item 중 정확히 하나만 받았다
            assert complex_id is not None
            result = get_real_prices(
                client, complex_id, trade_type=trade_types[0], area_group=area, pyeong=pyeong, limit=limit, years=years,
                month=month,
            )
        emit(result, pretty, notes=result.notes)


@app.command('region-real-price')
def region_real_price_command(
    region: Annotated[str, typer.Argument(help=REGION_ARGUMENT_HELP)],
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세 중 하나')] = '매매',
    new_high: Annotated[
        bool, typer.Option('--new-high', help='이전 최고가를 넘은 신고가 매매만 (가격 높은 순). 당근 웹처럼 가장 최근 공개일 것만')
    ] = False,
    previous_days: Annotated[
        bool, typer.Option('--previous-days', help='--new-high 와 함께: 이전 공개일의 신고가까지 (당근 웹은 최근 공개일만)')
    ] = False,
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """동·구의 최근 실거래 또는 신고가 (국토부 신고 기준). 아파트 외에 빌라·오피스텔 거래도 섞인다.

    정렬은 당근 웹 실거래 화면처럼 매매는 가격 순(최근 공개일부터, 같은 날 안에서 가격 높은 순), 전세·월세는 최신 순이다.
    """
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    if new_high and trade_types[0] != '매매':
        raise typer.BadParameter('신고가는 매매만 있습니다', param_hint='--new-high / --trade')
    if previous_days and not new_high:
        raise typer.BadParameter('--previous-days 는 --new-high 와 함께 씁니다 (일반 실거래는 늘 이전 공개일까지 준다)', param_hint='--previous-days')
    with handle_errors(SOURCE), DaangnClient() as client, _complex_name_hint(client, region):
        result = get_region_real_prices(
            client,
            region,
            trade_type=trade_types[0],
            new_high=new_high,
            previous_days=previous_days,
            limit=limit,
        )
        emit(result, pretty, notes=result.notes)


@search_app.command('commute')
def commute_command(
    workplace: Annotated[
        str | None,
        typer.Argument(help="회사가 있는 동·구 이름 (예: 역삼동, '강남구 신사동'). 그 중심을 회사 위치로 본다. 역은 --station, 대학은 --university, 좌표는 --lat/--lng")
    ] = None,
    station: Annotated[
        str | None,
        typer.Option('--station', help="회사 근처 지하철역 이름 (예: 강남역). 노선을 붙이면 그 역 (예: '서울5호선 양평역')"),
    ] = None,
    university: Annotated[
        str | None,
        typer.Option('--university', help="회사 위치로 볼 대학 이름 (예: '연세대학교 신촌캠퍼스')"),
    ] = None,
    address: Annotated[
        str | None,
        typer.Option('--address', help="회사 도로명 주소 (예: '테헤란로 152'). 당근 웹 검색창 주소 검색과 같이 찾은 좌표를 회사 위치로 본다"),
    ] = None,
    lat: Annotated[float | None, typer.Option(help='회사 위도 (이름 대신)')] = None,
    lng: Annotated[float | None, typer.Option(help='회사 경도 (이름 대신)')] = None,
    max_minutes: Annotated[
        int,
        typer.Option(min=1, max=90, help='타는 역에서 회사 역까지 지하철 시간 상한 (분)')
    ] = 30,
    property_type: PropertyTypeOption = None,
    trade: TradeOption = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    yearly_rent_min: YearlyRentMinOption = None,
    yearly_rent_max: YearlyRentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    with_manage_cost: WithManageCostOption = False,
    area_min: AreaMinOption = None,
    area_max: AreaMaxOption = None,
    floor: FloorOption = None,
    room_count: RoomCountOption = None,
    structure: StructureOption = None,
    approval: ApprovalOption = None,
    deal: DealOption = None,
    option: ExtraOption = None,
    move_in_now: MoveInNowOption = False,
    limit: Annotated[int, typer.Option(min=1, max=COMMUTE_STATION_MAX_LIMIT, help='역당 최대 매물 수 (100건씩 페이지를 넘겨 받는다)')] = COMMUTE_STATION_DEFAULT_LIMIT,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """회사까지 지하철로 갈 수 있는 역 주변 매물을 역별로 찾는다 (당근 웹 출퇴근 지도).

    회사에서 가장 가까운 역을 찾고, 그 역까지 --max-minutes 안에 오는 역들 중 가까운 역부터 최대 10곳의
    주변 매물을 모은다. 조건은 search listings 와 같고 당근 서버에서 건다.

    예: jibsa daangn search commute --station 강남역 --max-minutes 20 -t 원룸 --trade 월세 --rent-max 70
    예: jibsa daangn search commute --address '테헤란로 152' --max-minutes 20 -t 원룸 --trade 월세
    """
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('yearly-rent', yearly_rent_min, yearly_rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
    )
    _require_one_target(workplace, station, university, lat, lng, 'WORKPLACE', address=address)
    with handle_errors(SOURCE), DaangnClient() as client:
        conditions, notes = _listing_conditions(
            property_type=property_type, trade=trade,
            deposit_min=deposit_min, deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max,
            price_min=price_min, price_max=price_max, with_manage_cost=with_manage_cost,
            area_min=area_min, area_max=area_max, floor=floor, room_count=room_count,
            structure=structure, approval=approval, deal=deal, option=option, move_in_now=move_in_now,
            yearly_rent_min=yearly_rent_min, yearly_rent_max=yearly_rent_max,
        )
        # 당근 웹 출퇴근 지도는 회사 위치를 카카오 장소 검색으로 찾는다. 당근 API 가 아니라 옮기지 않고, 당근 웹 검색창이 찾는
        # 역·대학·동·구의 좌표를 회사 위치로 쓴다 (#215)
        if station is not None:
            found_station = _station_named(client, station)
            lat, lng = found_station.lat, found_station.lng
            notes += same_station_notes(found_station) + [note('범위', f'{found_station.name}을 회사 위치로 보았습니다')]
        elif university is not None:
            found_university = find_university(client, university)
            lat, lng = found_university.lat, found_university.lng
            notes.append(note('범위', f"{quoted(found_university.name, '을/를')} 회사 위치로 보았습니다"))
        elif address is not None:
            found_address = find_address(client, address)
            lat, lng = found_address.lat, found_address.lng
            notes.append(note('범위', f'{found_address.label} 의 좌표를 회사 위치로 보았습니다'))
        elif workplace is not None:
            with _complex_name_hint(client, workplace, station_hint=f"회사 근처 역이면 --station '{workplace}' 으로 주세요"):
                area = resolve_area(client, workplace, other_inputs=OTHER_PLACE_INPUTS)
            lat, lng = area.lat, area.lng
            notes.append(note('범위', f'{area.full_name} 중심(당근 지역 검색의 중심 좌표)을 회사 위치로 보았습니다'))
        # _require_one_target 이 넷 중 하나를 요구했다
        assert lat is not None and lng is not None
        try:
            result = search_commute(
                client,
                lat,
                lng,
                max_minutes=max_minutes,
                conditions=conditions,
                limit=limit,
            )
        except FeedQueryRejectedError:
            raise JibsaError(
                code='UPSTREAM_ERROR',
                message='당근 출퇴근 API 가 바뀌어(웹 쿼리 해시 거절) 출퇴근 검색을 할 수 없습니다',
                hint='jibsa daangn search listings --station <역 이름> 으로 역 주변을 찾으세요. jibsa 업데이트가 필요합니다',
            ) from None
        if with_manage_cost and any(listing.manage_cost_manwon is None for listing in result.listings):
            notes.append(_manage_cost_filtered_note('jibsa daangn listing <id> 로 봅니다'))
        emit(result, pretty, notes=notes + result.notes, fields=fields)


@app.command('region-reviews')
def region_reviews_command(
    region: Annotated[str, typer.Argument(help=REGION_ARGUMENT_HELP)],
    top: Annotated[int, typer.Option(min=1, max=TOP_COMPLEXES_MAX, help='후기 많은 단지 수 (당근 구 후기 페이지의 20곳까지)')] = TOP_COMPLEXES_MAX,
    pretty: PrettyOption = None,
) -> None:
    """동네 거주 후기가 있는지·몇 개인지와 후기 많은 단지. 후기 내용은 url 의 원 사이트에서."""
    with handle_errors(SOURCE), DaangnClient() as client, _complex_name_hint(client, region):
        result = get_region_reviews(client, region, top=top)
        emit(result, pretty, notes=result.notes)


@search_app.command('complexes')
def complexes_command(
    region: Annotated[
        str | None,
        typer.Argument(help=f'{REGION_ARGUMENT_HELP}. --lat/--lng 를 주면 생략 (그 좌표의 웹 지도 화면 범위 단지)'),
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    zoom: ComplexZoomOption = None,
    complex_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(COMPLEX_TYPE_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분. 아파트는 주상복합 포함. 기본 전체")
    ] = None,
    trade: Annotated[
        str | None,
        typer.Option('--trade', help='매매, 전세, 월세 중 하나. 가격 조건과 단지마다 붙는 최근 실거래의 거래 유형. 기본 매매 (웹처럼 주지 않으면 거래 유형을 단지 조건으로 보내지 않는다)')
    ] = None,
    deposit_min: Annotated[int | None, typer.Option(min=0, help='보증금/전세금 하한 (만원, 전세·월세. 예전 실거래 기준)')] = None,
    deposit_max: Annotated[int | None, typer.Option(min=0, help='보증금/전세금 상한 (만원, 전세·월세. 예전 실거래 기준)')] = None,
    rent_min: Annotated[int | None, typer.Option(min=0, help='월세 하한 (만원, 월세. 예전 실거래 기준)')] = None,
    rent_max: Annotated[int | None, typer.Option(min=0, help='월세 상한 (만원, 월세. 예전 실거래 기준)')] = None,
    price_min: Annotated[int | None, typer.Option(min=0, help='매매가 하한 (만원, 매매. 예전 실거래 기준)')] = None,
    price_max: Annotated[int | None, typer.Option(min=0, help='매매가 상한 (만원, 매매. 예전 실거래 기준)')] = None,
    area_min: Annotated[float | None, typer.Option(min=0, help='전용면적 하한 (㎡, 1평=3.3㎡)')] = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='전용면적 상한 (㎡)')] = None,
    approval: ApprovalOption = None,
    household_min: Annotated[int | None, typer.Option(min=0, help='세대수 하한')] = None,
    household_max: Annotated[int | None, typer.Option(min=0, help='세대수 상한')] = None,
    parking_min: Annotated[float | None, typer.Option(min=0, help='세대당 주차대수 하한')] = None,
    sort: Annotated[
        str,
        typer.Option('--sort', help=f"{', '.join(COMPLEX_SORT_BY_LABEL)} 중 하나. 입주일 순은 사용승인일 순과 어긋날 수 있다")
    ] = '세대수',
    limit: Annotated[int, typer.Option(min=1, max=COMPLEX_LIST_MAX_LIMIT, help='최대 단지 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """동·구 또는 좌표(--lat/--lng)의 웹 지도 화면 범위의 단지 목록 (당근 지도 단지 탭). 세대수·가격·입주일 순으로 정렬하고, 조건은 당근 서버에서 건다.

    가격 조건은 지금 매물이 아니라 단지의 예전 실거래 가격 기준이다. 지금 매물은 search listings --complex <complex_id> 로 본다.

    예: jibsa daangn search complexes '강남구 역삼동' -t 아파트 --sort 가격높은순 --household-min 500
    예: jibsa daangn search complexes --lat 37.5006 --lng 127.0366 --zoom 14 -t 오피스텔
    """
    _require_one_place(region, lat, lng, 'REGION', '동·구 이름')
    if zoom is not None and region is not None:
        raise typer.BadParameter('--zoom 은 --lat/--lng 로 지도 화면 범위를 찾을 때만 씁니다. 동·구는 그 지역 단지 목록이라 범위가 없습니다', param_hint='--zoom')
    require_finite('--parking-min', parking_min)
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
        ('household', household_min, household_max),
    )
    trade_types = split_csv([trade] if trade else None, REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) > 1:
        raise typer.BadParameter('거래 유형은 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    sorts = split_csv([sort], tuple(COMPLEX_SORT_BY_LABEL), '--sort')
    if len(sorts) != 1:
        raise typer.BadParameter(f"정렬은 하나만 받습니다 ({', '.join(COMPLEX_SORT_BY_LABEL)} 중 하나)", param_hint='--sort')
    approvals = split_csv([approval] if approval else None, tuple(BUILDING_APPROVAL_FILTER_BY_LABEL), '--approval')
    if len(approvals) > 1:
        raise typer.BadParameter('사용승인일은 하나만 받습니다', param_hint='--approval')
    trade_type = trade_types[0] if trade_types else DEFAULT_COMPLEX_TRADE_TYPE
    # 거래 유형에 없는 가격 조건은 당근이 무시하므로 조건이 걸린 줄 알지 않도록 막는다
    if trade_type != '매매' and (price_min is not None or price_max is not None):
        raise typer.BadParameter('매매가 조건은 --trade 매매 일 때만 씁니다', param_hint='--price-min / --price-max')
    if trade_type == '매매' and (deposit_min is not None or deposit_max is not None):
        raise typer.BadParameter('보증금 조건은 --trade 전세 또는 월세 일 때만 씁니다', param_hint='--deposit-min / --deposit-max')
    if trade_type != '월세' and (rent_min is not None or rent_max is not None):
        raise typer.BadParameter('월세 조건은 --trade 월세 일 때만 씁니다', param_hint='--rent-min / --rent-max')
    with handle_errors(SOURCE), DaangnClient() as client:
        conditions = DaangnComplexConditions(
            complex_types=split_csv(complex_type, tuple(COMPLEX_TYPE_FILTER_BY_LABEL), '--type'),
            trade_type=trade_types[0] if trade_types else None,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            area_min=area_min,
            area_max=area_max,
            building_approval=approvals[0] if approvals else None,
            household_min=household_min,
            household_max=household_max,
            parking_min=parking_min,
        )
        result: DaangnRegionComplexesResult | DaangnBoundsComplexesResult
        if lat is not None and lng is not None:
            try:
                result = list_bounds_complexes(
                    client, lat, lng, zoom=zoom or POINT_ZOOM, conditions=conditions, sort=sorts[0], limit=limit,
                )
            except FeedQueryRejectedError:
                raise map_query_rejected_error('search complexes') from None
            emit(result, pretty, notes=[note(
                '범위',
                f'당근 웹 지도 화면(데스크톱, 줌 {result.zoom}, 가로 {result.width_km:g}km × 세로 {result.height_km:g}km) 안 단지를 '
                '웹 단지 탭처럼 줍니다. 범위를 바꾸려면 --zoom 을 주세요 (1 작으면 가로·세로 2배)',
            )] + result.notes)
            return
        # _require_one_place 가 좌표가 없으면 지역 이름을 요구했다
        assert region is not None
        with _complex_name_hint(
            client, region,
            station_alternative='역 근처 단지는 jibsa dabang search complexes <역 이름> 이나 jibsa naver search complexes <역 이름> 으로 찾으세요',
        ):
            result = list_region_complexes(client, region, conditions=conditions, sort=sorts[0], limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('school')
def school_command(
    name: Annotated[
        str,
        typer.Argument(help="학교 이름 (예: '역삼초등학교'. 일부만 줘도 된다) 또는 학교 코드 (예: B100000749). 여러 곳이면 후보의 school_code 로 다시 부른다")
    ],
    complex_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(COMPLEX_TYPE_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분. 아파트는 주상복합 포함. 기본 전체")
    ] = None,
    household_min: Annotated[int | None, typer.Option(min=0, help='세대수 하한 (소규모 빌라형 단지를 뺄 때)')] = None,
    limit: Annotated[int, typer.Option(min=1, max=COMPLEX_LIST_MAX_LIMIT, help='최대 단지 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """학교 정보와 그 학교에 배정되는 단지 (초등학교만, 당근 웹과 같은 순서). 요청 2회, 이름이 '○○초등학교' 처럼 끝나면 3회,
    학교 코드면 1회.

    예: jibsa daangn school 역삼초등학교 -t 아파트 --household-min 100
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_school(
            client,
            name,
            complex_types=split_csv(complex_type, tuple(COMPLEX_TYPE_FILTER_BY_LABEL), '--type'),
            household_min=household_min,
            limit=limit,
        )
        emit(result, pretty, notes=result.notes)


@app.command('price-trend')
def price_trend_command(
    complex_id: Annotated[
        int,
        typer.Argument(
            parser=complex_id_value,
            help='단지 ID (complexes·school·search locations <단지 이름> 결과, 아파트·오피스텔 listing 의 complex_id)',
        )
    ],
    pyeong: Annotated[
        int | None,
        typer.Option('--pyeong', min=1, help='공급 평형 묶음 (complex 결과의 pyeongs[].pyeong, 예: 32). 아파트형 단지만. 기본 대표 평형')
    ] = None,
    area: Annotated[
        int | None,
        typer.Option(min=1, help='아파트형이 아닌 단지의 전용면적 묶음 (complex 결과의 pyeongs[].area_group, 예: 84). 아파트형은 당근 웹처럼 --pyeong 으로만 고른다. 기본 대표 평형')
    ] = None,
    trade: Annotated[
        str,
        typer.Option('--trade', help=f"{', '.join(PRICE_CHART_TRADE_BY_TRADE_TYPE)} 중 하나 (월세 시세 그래프는 없다)")
    ] = '매매',
    period: Annotated[
        str,
        typer.Option('--period', help=f"{', '.join(PRICE_TREND_PERIODS)} 중 하나 (당근 웹 시세 그래프 탭). 보여 줄 기간이자 변화율을 보는 기간")
    ] = '1년',
    pretty: PrettyOption = None,
) -> None:
    """단지 시세 추이: 당근 웹 단지 화면 시세 그래프의 월별 평균 실거래가(국토부 신고 기준)와 기간 변화율. 평형 하나로 본다. 요청 2회.

    예: jibsa daangn price-trend 10667600 --pyeong 33 --trade 매매 --period 3년
    """
    trade_types = split_csv([trade], tuple(PRICE_CHART_TRADE_BY_TRADE_TYPE), '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('시세 추이는 매매, 전세 중 하나만 받습니다', param_hint='--trade')
    periods = split_csv([period], tuple(PRICE_TREND_PERIODS), '--period')
    if len(periods) != 1:
        raise typer.BadParameter(f"기간은 하나만 받습니다 ({', '.join(PRICE_TREND_PERIODS)} 중 하나)", param_hint='--period')
    if area is not None and pyeong is not None:
        raise typer.BadParameter('--area(전용면적 묶음)와 --pyeong(공급 평형) 중 하나만 주세요', param_hint='--area / --pyeong')
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_price_trend(
            client, complex_id, trade_type=trade_types[0], pyeong=pyeong, area_group=area, period=periods[0],
        )
        emit(result, pretty, notes=result.notes)


@app.command('preschools')
def preschools_command(
    complex_id: Annotated[
        int,
        typer.Argument(
            parser=complex_id_value,
            help='단지 ID (search complexes·search locations <단지 이름> 결과, 아파트·오피스텔 listing 의 complex_id)',
        )
    ],
    pretty: PrettyOption = None,
) -> None:
    """단지 근처 어린이집·유치원 (당근 단지 화면 학군의 유치원 탭과 같은 목록·순서). 요청 1회.

    지역·역 이름이나 반경으로는 찾지 않는다. 어린이집·유치원 구분과 운영 정보는 preschool 로 본다.

    예: jibsa daangn preschools 10697092
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        result = list_preschools(client, complex_id)
        emit(result, pretty, notes=result.notes)


@app.command('preschool')
def preschool_command(
    preschool_id: Annotated[int, typer.Argument(min=1, help='시설 번호 (preschools 결과의 id)')],
    pretty: PrettyOption = None,
) -> None:
    """어린이집·유치원 하나의 운영 시간·설립 유형·정원·학급·교사 수. 정원은 지금 다니는 원아 수가 아니다. 전화번호는 주지 않는다. 요청 1회.

    예: jibsa daangn preschool 33710
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        emit(get_preschool(client, preschool_id), pretty)


@app.command('compare')
def compare_command(
    complex_ids: Annotated[
        list[int],
        typer.Argument(
            parser=complex_id_value,
            help=f'단지 ID 여러 개 (최대 {COMPARE_MAX_COMPLEXES}개, search locations·search complexes·complex 결과)',
        )
    ],
    area: Annotated[
        float | None,
        typer.Option(min=1, help='비교할 전용면적 (㎡, 예: 84). 모든 단지를 이 면적과 가장 비슷한 평형으로 본다. 기본은 당근 웹처럼 첫 단지 대표 평형')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 여러 곳을 당근 웹 비교처럼 평형 하나씩 나란히: 세대수·준공·주차, 배정 학교, 역, 그 평형의 KB 시세·최근 실거래(매매·전세·월세),
    평균 호가, 월 관리비. 단지마다 요청 1회.

    예: jibsa daangn compare 10697092 10699673 10697091 --area 84
    """
    if len(set(complex_ids)) > COMPARE_MAX_COMPLEXES:
        raise typer.BadParameter(f'단지는 최대 {COMPARE_MAX_COMPLEXES}개까지 비교합니다', param_hint='COMPLEX_IDS')
    require_finite('--area', area)
    with handle_errors(SOURCE), DaangnClient() as client:
        result = compare_complexes(client, complex_ids, area_m2=area)
        emit(result, pretty, notes=result.notes)


@app.command('nearby-complexes')
def nearby_complexes_command(
    complex_id: Annotated[int, typer.Argument(parser=complex_id_value, help='기준 단지 ID')],
    limit: Annotated[int, typer.Option(min=1, max=NEARBY_COMPLEXES_MAX, help='최대 단지 수')] = 50,
    pretty: PrettyOption = None,
) -> None:
    """기준 단지와 같은 동의 다른 단지 (세대수·거래 유형별 현재 매물 수, 세대수 많은 순). 요청 3회.

    예: jibsa daangn nearby-complexes 10697092 --limit 20
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        result = list_nearby_complexes(client, complex_id, limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('good-neighborhoods')
def good_neighborhoods_command(
    lifestyle: Annotated[
        str,
        typer.Option('--lifestyle', help=f"{', '.join(LIFESTYLE_INDICATORS)} 중 하나 (당근 웹 좋은 동네 추천의 카드)")
    ],
    region: Annotated[
        list[str] | None,
        typer.Option('--region', help="시·도(예: 서울) 또는 시·군·구(예: 강남구, '서울 중구'). 시·도는 '서울시'·'충북' 같은 줄임말도 되고, 전남광주통합특별시(전남)는 광주·전남을 함께 찾고, 옛 이름(광주·광주광역시·전라남도)은 그 한 곳만 찾는다. 구가 있는 시는 '분당구'·'성남시 분당구' 로 한 구를, '수원시' 로 그 시의 구 모두를 찾는다. 반복하거나 쉼표로 구분. 기본 서울 (당근 웹 첫 화면, 전국은 없다)")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """라이프스타일에 맞는 살기 좋은 동 5곳 (당근 웹 좋은 동네 추천, 통계 지표 기준). 요청 2회.

    후기 요약 글은 주지 않는다. 동은 행정동이라, 매물은 법정동 이름으로 search listings 에서 찾는다.

    예: jibsa daangn good-neighborhoods --lifestyle 직장인자취 --region 서울
    """
    lifestyles = split_csv([lifestyle], tuple(LIFESTYLE_INDICATORS), '--lifestyle')
    if len(lifestyles) != 1:
        raise typer.BadParameter(f"라이프스타일은 하나만 받습니다 ({', '.join(LIFESTYLE_INDICATORS)} 중 하나)", param_hint='--lifestyle')
    regions = [name for item in region or [] for name in item.split(',') if name.strip()]
    with handle_errors(SOURCE), DaangnClient() as client:
        result = recommend_neighborhoods(client, lifestyles[0], regions=[name.strip() for name in regions])
        emit(result, pretty, notes=result.notes)


@app.command('trending-complexes')
def trending_complexes_command(
    region: Annotated[
        str | None,
        typer.Argument(help="시·도 또는 구 이름 (예: 서울, 강남구, '성남시 분당구'). 빼거나 '전국' 이면 전국. 동은 받지 않는다")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """당근 웹의 인기 급상승 단지: 어제 대비 오늘 조회가 급상승한 단지 (50곳까지). 전국은 요청 1회, 지역은 2회.

    예: jibsa daangn trending-complexes 서울
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        name = ' '.join((region or '').split())
        # 웹은 전국·시·도 탭과 시·군·구 페이지로만 부른다. 동을 주면 trending_region_of 가 그 구를 권한다 (#215)
        area = None if name in ('', '전국') else resolve_area(client, name, levels=frozenset({'구', '시도'}))
        result = list_trending_complexes(client, trending_region_of(area))
        emit(result, pretty, notes=result.notes)


@app.command('popular-listings')
def popular_listings_command(
    dong: Annotated[str, typer.Argument(help='동 이름 (예: 역삼동). 순위는 그 동이 속한 구 전체다 (구가 없는 세종은 그 동 안)')],
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(POPULAR_PROPERTY_TYPES)} 중 하나 (당근 웹 순위 화면이 받는 종류). 기본 전체")
    ] = None,
    limit: Annotated[
        int, typer.Option(min=1, max=POPULAR_MAX_LIMIT, help=f'조회할 매물 수 (제외 전). 웹처럼 {POPULAR_MAX_LIMIT}위까지')
    ] = POPULAR_MAX_LIMIT,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """구 전체에서 조회수 많은 매물 순위 (당근 웹처럼 30위까지). 요청 2회.

    예: jibsa daangn popular-listings 역삼동 -t 원룸
    """
    # 하나만 받지만 목록으로 받는다. 한 값 옵션은 -t 원룸 -t 투룸 처럼 반복하면 Click 이 에러 없이 마지막 값만 남겨 투룸 순위만
    # 줬다 (2026-11-12 리뷰. 당근의 다른 명령 -t 는 반복을 받는다)
    property_types = split_csv(property_type, POPULAR_PROPERTY_TYPES, '--type')
    if len(property_types) > 1:
        # 웹 순위 화면은 URL 로 종류 하나만 받아 부른다 (salesTypes:[종류]). 여러 종류를 한 순위로 섞어 보여 주는 화면은 없다
        raise typer.BadParameter('매물 종류는 하나만 받습니다 (당근 웹 순위 화면은 종류 하나로 열린다)', param_hint='--type')
    with handle_errors(SOURCE), DaangnClient() as client:
        result = list_popular_listings(
            client, resolve_dong(client, dong), property_type=property_types[0] if property_types else None, limit=limit,
        )
        emit(result, pretty, notes=property_type_notes(property_types) + result.notes, fields=fields)
