from collections.abc import Mapping

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
    HintedUsageError,
    UsageHints,
    check_choice,
    emit,
    handle_errors,
    infer_trade_types,
    require_finite,
    require_korea,
    split_csv,
    split_ints,
    validate_ranges,
)
from jibsa.cli.paging import (
    NextOption,
    decode_next,
    encode_next,
)
from jibsa.core.errors import RegionNotFoundError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    multipolygon_bounds,
)
from jibsa.core.korean import (
    is_dong_code,
    is_ri_code,
    particle,
    quoted,
)
from jibsa.core.listing import normalize_address
from jibsa.core.notes import (
    UPDATE_MAYBE_NEEDED,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.stay.search import (
    ZigbangGuestItemsFiltersRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.service.apt.constants import (
    APT_TRADE_TYPES,
)
from jibsa.providers.zigbang.service.apt.detail import (
    get_catalog,
)
from jibsa.providers.zigbang.service.apt.models.search import ZigbangAptConditions
from jibsa.providers.zigbang.service.apt.search import (
    apt_dong_at,
    search_apt_listings,
)
from jibsa.providers.zigbang.service.common.constants import (
    COMPLEX_ID_PATTERN,
    CONDITIONS,
    FLOOR_FILTERS,
    MAX_LIST_LIMIT,
    OPTION_FILTERS,
    ROOM_TYPES,
    TRADE_TYPES,
)
from jibsa.providers.zigbang.service.common.models import (
    ZigbangBoundary,
    ZigbangRegion,
    ZigbangRoomConditions,
)
from jibsa.providers.zigbang.service.common.room import (
    room_filter_of,
)
from jibsa.providers.zigbang.service.complex.constants import (
    COMPLEX_ORDERS,
    DEFAULT_PRICE_TREND_PERIOD,
    DEFAULT_PYEONG_TREND_TRADE,
    MAX_COMPARE_DANJIS,
    PRICE_TREND_PERIODS,
    PYEONG_TREND_TRADES,
)
from jibsa.providers.zigbang.service.complex.info import (
    get_complex,
    search_regions_and_complexes,
)
from jibsa.providers.zigbang.service.complex.listings import (
    list_complex_listings,
)
from jibsa.providers.zigbang.service.complex.search import (
    school_has_assigned_complexes,
    search_place_complexes,
)
from jibsa.providers.zigbang.service.complex.trend import (
    get_price_trend,
    get_pyeong_price_trend,
)
from jibsa.providers.zigbang.service.listing import get_any_listing
from jibsa.providers.zigbang.service.local.constants import (
    DEFAULT_RANKING_LIMIT,
    DEFAULT_TRADE_LIMIT,
    LOCAL_TRADES,
    PRICE_RANGES,
    RANKING_MAX_RANKS,
    RANKING_PERIODS,
    SORT_SPEC_BY_TRADE,
    SORT_TYPE_BY_TRADE,
    TRADE_PERIODS,
)
from jibsa.providers.zigbang.service.local.info import (
    get_region_info,
)
from jibsa.providers.zigbang.service.local.ranking import (
    get_region_ranking,
)
from jibsa.providers.zigbang.service.local.trades import (
    get_region_trades,
)
from jibsa.providers.zigbang.service.real_price.constants import (
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_TRADE_TYPES,
)
from jibsa.providers.zigbang.service.real_price.real_price import (
    get_real_prices,
)
from jibsa.providers.zigbang.service.region import (
    MAX_RADIUS_KM,
    city_gu_search_items,
    divided_region_error,
    dong_boundary,
    merge_dong_boundaries,
    merged_dong_region,
    region_from_search_item,
    region_scope_items,
    resolve_apt_region,
    resolve_region_scope,
    resolve_region_with_notes,
    search_regions,
    wide_area_note,
    wide_boundary_note,
)
from jibsa.providers.zigbang.service.room.constants import (
    DETAILS_MAX,
    GEOHASH_PRECISION,
    PROPERTY_TYPES,
)
from jibsa.providers.zigbang.service.room.search import (
    attach_building_use,
    search_listings,
    unsearchable_note,
    unsearchable_types,
)
from jibsa.providers.zigbang.service.stay.constants import (
    STAY_BUILDING_TYPE_BY_LABEL,
    STAY_DISCOUNT_TYPE_BY_LABEL,
    STAY_FLOOR_TYPE_BY_LABEL,
    STAY_GEOHASH_PRECISION,
    STAY_OPTION_BY_LABEL,
    STAY_WEEKLY_PRICE_NOTE,
)
from jibsa.providers.zigbang.service.stay.models.search import ZigbangStayConditions
from jibsa.providers.zigbang.service.stay.search import (
    check_stay_sort,
    search_stay_listings,
    stay_distance_sort_error,
)
from jibsa.providers.zigbang.service.store.constants import (
    STORE_BUSINESS_NAMES,
    STORE_TRADE_TYPES,
)
from jibsa.providers.zigbang.service.store.models import ZigbangStoreConditions
from jibsa.providers.zigbang.service.store.store import (
    search_store_listings,
    store_price_trade,
)

from typing import Annotated


SOURCE: str = 'zigbang'
STAY_SERVICE_NOTE: str = (
    '단기임대는 중개사가 올린 원룸·오피스텔·빌라 단기 계약 매물입니다. 직방이 따로 운영하는 주 단위 '
    '단기임대 서비스는 매물이 달라 jibsa zigbang search listings stay 로 찾습니다'
)
STAY_STRUCTURES: tuple[str, ...] = ('복층', '단층')
# room·--complex 에 다른 소스 표현을 옮겨 쓴 사용법 오류의 힌트 (UsageHints). 이 명령의 다른 옵션 값과, 뜻이 같은 다른 소스
# 표현이다 (당근 --option 반려동물가능·대출가능, --structure 오픈형, --room-count 2개, 네이버 --move-in 바로입주·--facility)
ROOM_HINTS: UsageHints = UsageHints(
    by_value={
        **{value: f'--room {value}' for value in ROOM_TYPES},
        **{value: f'--floor {value}' for value in FLOOR_FILTERS},
        **{value: f'--option {value}' for value in OPTION_FILTERS},
        **{value: f'--condition {value}' for value in CONDITIONS},
        '반려동물가능': '--condition 반려동물',
        '대출가능': '--condition 전세대출',
        '주차가능': '--condition 주차',
        '바로입주': '--condition 즉시입주',
        '옥탑': '--floor 옥탑방',
        '지하층': '--floor 반지하',
        '복층': '--room 복층형원룸',
        '오픈형': '--room 오픈형원룸',
        '분리형': '--room 분리형원룸',
        '원룸': '-t 원룸',
        '2개': '--room 투룸',
        '3개': '--room 쓰리룸',
        '4개이상': '--room 포룸이상',
    },
    by_option_value={
        # 네이버 --bathroom 은 '1개', 직방은 숫자다. '2개' 가 방 수(--room 투룸)로 가지 않게 이 옵션에서 먼저 본다
        '--bathroom': {'1개': '--bathroom 1', '2개': '--bathroom 2', '3개': '--bathroom 3', '4개이상': '--bathroom 3'},
        '--type': {
            '투룸': '--room 투룸',
            '쓰리룸': '--room 쓰리룸',
            '아파트': 'jibsa zigbang search listings apt',
            '상가': 'jibsa zigbang search listings store',
            '사무실': 'jibsa zigbang search listings store',
        },
    },
    by_option={
        '--facility': '--option (가전·가구) 이나 --condition (엘리베이터·주차 등)',
        '--room-count': '--room 투룸',
        '--structure': '--room 오픈형원룸',
        '--one-room-shape': '--room 오픈형원룸',
        '--move-in': '--condition 즉시입주',
        '--move-in-now': '--condition 즉시입주',
        '--direction': '--condition 남향 (직방은 남향만 거른다)',
        '--city': "직방에는 --city 가 없습니다. 지역 이름 앞에 구 이름을 붙이세요 (예: '강남구 신사동')",
        '--deal': '직방에는 직거래 조건이 없습니다. 직거래는 jibsa daangn search listings --deal 직거래 로 찾으세요',
        '--sort': '직방 room 은 직방 목록 순서(안심추천·안심일반·일반)로만 줍니다. 가까운 매물은 결과의 distance_km 로 고르세요',
        '--with-manage-cost': '직방은 월세와 관리비를 따로 거릅니다: --rent-max 와 --manage-cost-max',
        '--expand': '주변까지 보려면 --radius 로 반경을 넓히세요 (최대 5km)',
    },
)
APT_HINTS: UsageHints = UsageHints(
    by_option={
        '--type': '아파트만 찾는 명령이라 -t 없이 부르세요. 원룸·오피스텔·빌라는 jibsa zigbang search listings room',
        '-t': '아파트만 찾는 명령이라 -t 없이 부르세요. 원룸·오피스텔·빌라는 jibsa zigbang search listings room',
        '--pyeong': '평형은 단지 매물에서 고릅니다: jibsa zigbang search listings --complex <apt-ID> --pyeong <평형 ID>',
        '--area-pyeong-min': '면적은 ㎡ 로 주세요: --area-min (전용) 이나 --supply-area-min (공급), 1평 = 3.3058㎡',
        '--area-pyeong-max': '면적은 ㎡ 로 주세요: --area-max (전용) 이나 --supply-area-max (공급), 1평 = 3.3058㎡',
    },
)
# 사용법 오류가 난 명령(command_path)으로 힌트 표를 찾는다 (jibsa.cli.app.run)
USAGE_HINTS: dict[str, UsageHints] = {
    'jibsa zigbang search listings room': ROOM_HINTS,
    'jibsa zigbang search listings': ROOM_HINTS,
    'jibsa zigbang search listings apt': APT_HINTS,
}
# 없앤 옵션을 준 사용법 오류에 바뀐 사용법을 알린다 (jibsa.cli.app.changed_usage_hint). '-' 로 시작하는 안내를 USAGE_HINTS 에
# 두면 옵션 줄로 읽혀 '이 명령에서는 이렇게 주세요: --without-random 은 없앴습니다' 가 되고, 표에 없으면 다른 명령에 있다며 room·
# 다른 소스를 권했다 (2026-11-16 리뷰: apt --radius)
WITHOUT_RANDOM_REMOVED: ChangedUsage = ChangedUsage(
    '--without-random 을 없앴습니다. 오피스텔은 늘 직방이 섞지 않은 순서로 받으니 옵션 없이 부르세요',
    removed_options=frozenset({'--without-random'}),
)
CHANGED_USAGE: dict[str, ChangedUsage] = {
    'jibsa zigbang search listings room': WITHOUT_RANDOM_REMOVED,
    'jibsa zigbang search listings': WITHOUT_RANDOM_REMOVED,
    'jibsa zigbang search listings apt': ChangedUsage(
        '--radius 를 없앴습니다. 아파트는 직방 웹처럼 동·구 하나의 매물 목록이라 동·구 이름으로 찾고, 역·학교 이름과 '
        '--lat/--lng 는 그 위치가 속한 동의 목록을 줍니다. 역 주변 단지는 jibsa zigbang search complexes <역 이름> 으로 찾으세요',
        removed_options=frozenset({'--radius'}),
    ),
    'jibsa zigbang search listings stay': ChangedUsage(
        '--details 를 없앴습니다. 직방 웹은 기간 요금을 로그인해야 보여 줘 기간 비용(period_cost)을 뺐습니다. 그 기간을 예약할 수 '
        '있는지는 jibsa zigbang listing stay-<ID> --check-in <날짜> --check-out <날짜> 의 available 로 보세요',
        removed_options=frozenset({'--details'}),
    ),
    'jibsa zigbang listing': ChangedUsage(
        '--pet 을 없앴습니다. 직방 웹은 기간 요금을 로그인해야 보여 줘 반려동물 청소비를 넣던 기간 비용(period_cost)을 뺐습니다. '
        '날짜를 주면 예약 가능 여부 available 만 붙습니다. 반려동물 가능 매물은 jibsa zigbang search listings stay --pet 으로 찾으세요',
        removed_options=frozenset({'--pet'}),
    ),
}

app = typer.Typer(
    help=(
        '직방: 매물 찾기(search listings room·apt·store·stay), 지역·단지(search locations, 역·학교·동·구 주변 단지 search complexes, complex, '
        'search listings --complex, real-price, 단지 직방시세 추이 price-trend), 동·구 지역 화면(지역 정보 region-info, 최근 실거래 region-trades, 단지 랭킹 region-ranking), '
        '상세(listing, 아파트 같은 호 묶음 catalog) '
        '(로그인 불필요, 금액은 만원 단위)'
    ),
    no_args_is_help=True,
)

QueryArgument = Annotated[
    str | None,
    typer.Argument(help='검색 중심 지역·역 이름 (예: 역삼동, 강남역). --lat/--lng 를 주면 생략')
]
LatOption = Annotated[float | None, typer.Option(help='중심 위도 (query 대신)')]
LngOption = Annotated[float | None, typer.Option(help='중심 경도 (query 대신)')]
LimitOption = Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='최대 결과 수')]
AptLimitOption = Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help=f'조회할 매물 수 (제외 전, 최대 {MAX_LIST_LIMIT}건)')]
AreaMinOption = Annotated[float | None, typer.Option(min=0, help='면적 하한 (㎡)')]
AreaMaxOption = Annotated[float | None, typer.Option(min=0, help='면적 상한 (㎡)')]
AreaPyeongMinOption = Annotated[float | None, typer.Option(min=0, help='면적 하한 (평). ㎡ 조건과 함께 주면 둘 다 만족')]
AreaPyeongMaxOption = Annotated[float | None, typer.Option(min=0, help='면적 상한 (평)')]

ScopeRadiusOption = Annotated[
    float | None,
    typer.Option(
        min=0.1,
        max=MAX_RADIUS_KM,
        help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동 이름에 --radius 를 주지 않으면 반경 대신 그 동 안을 찾는다. 반경 안 매물이 모자라도 반경 밖 매물로 채우지 않는다',
    ),
]

search_app = typer.Typer(
    help=(
        '직방 장소 후보(locations), 역·학교·동·구 주변 아파트 단지(complexes)와 매물 찾기: 원룸·오피스텔·빌라(room), 아파트(apt), '
        '상가·사무실(store), 단기임대 서비스(stay). '
        '상세는 결과의 id 로 jibsa zigbang listing <id>'
    ),
    no_args_is_help=True,
)

# 이 그룹의 --help 는 콜백(`complex_listings_command`) docstring 이 아니라 이 help 를 보여 준다. 콜백 docstring 의 안내를 여기에도 둔다
listings_app = typer.Typer(
    help=(
        '매물 유형별 검색 또는 --complex로 단지 매물 검색.\n\n'
        '--complex 결과의 상세는 id 로 jibsa zigbang listing <id>. 아파트의 가격 범위(mixed_prices true) 줄은 가격이 묶음 '
        '최저가라 매물별 가격은 jibsa zigbang catalog <catalog_id>.'
    ),
    invoke_without_command=True,
)

ComplexIdArgument = Annotated[
    str,
    typer.Argument(help='단지 ID. search locations 결과의 complexes[].complex_id 나 search 결과의 complex_id (예: apt-68579, officetel-20227)'),
]

RegionQueryArgument = Annotated[
    str,
    typer.Argument(help='동·구 이름 (예: 송파구, 가락동). 시·도, 역·학교·단지 이름은 받지 않는다'),
]


def _region(
    client: ZigbangClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, list[str]]:
    """지역 이름이나 좌표를 검색 중심점으로 바꾼다. `items` 는 같은 검색어로 이미 받은 지역 검색 결과다."""
    if lat is not None and lng is not None:
        return ZigbangRegion(name=query or f'{lat},{lng}', lat=lat, lng=lng), []
    return resolve_region_with_notes(client, query or '', radius_km=radius, items=items)


def _scope(
    client: ZigbangClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float | None,
    precision: int,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, list[str], ZigbangBoundary | None, float]:
    """검색 중심과 범위를 정한다. 동 이름에 --radius·좌표가 없으면 반경 대신 그 동 경계를 쓴다.

    경계에 닿는 지도 칸(`precision`)이 반경 5km 원보다 많으면(큰 읍·면) 경계 대신 중심 반경으로 찾는다.
    `items` 는 같은 검색어로 이미 받은 지역 검색 결과다.

    Returns:
        (검색 중심, 안내, 동 경계 또는 None, 반경 km).
    """
    radius_km = radius or DEFAULT_RADIUS_KM
    if lat is not None and lng is not None:
        region, notes = _region(client, query, lat, lng, radius_km)
        return region, notes, None, radius_km
    region, split_note, split_items = resolve_region_scope(client, query or '', items=items)
    notes = []
    boundary = None
    if radius is None:
        # '○가' 동의 좌표는 동 안을 찾을 때만 쓴다 (반경 검색은 쓰지 않아 좌표가 없어도 막히지 않게 여기서 바꾼다)
        split = [region_from_search_item(item) for item in split_items]
        # '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)은 경계를 합쳐 그 안의 핀을 모두 찾는다 (room, stay 의 지도 대체 경로)
        boundary = merge_dong_boundaries(client, split) if split else dong_boundary(client, region)
        if split and boundary is not None:
            # 첫 동 중심에서 재면 다른 '○가' 매물이 늘 멀게 나와, 합친 범위의 가운데를 검색 중심으로 쓴다.
            # 경계를 받은 동만 이름에 넣는다 (못 받은 동은 아래 split_note 로 알린다)
            center_lat, center_lng, _ = multipolygon_bounds(boundary.polygons)
            merged = [part for part in split if part.name in boundary.name.split('·')] or split
            region = merged_dong_region(region, merged, (center_lat, center_lng))
            if boundary.name.count('·') + 1 == len(split):
                split_note = None
    if boundary is not None and (wide_note := wide_boundary_note(region, boundary, precision, radius_km)):
        notes.append(wide_note)
        boundary = None
    if boundary is None and (wide_note := wide_area_note(query or '', region, radius_km)):
        notes.append(wide_note)
    if split_note:
        notes.append(split_note)
    if boundary is not None:
        notes.append(note('범위', f'{boundary.name} 경계 안을 찾았습니다 (반경으로 찾으려면 --radius)'))
    return region, notes, boundary, radius_km


def _store_scope(
    client: ZigbangClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float | None,
) -> tuple[ZigbangRegion, list[str], list[ZigbangRegion] | None, float]:
    """상가 검색 중심과 범위를 정한다. 동 이름에 --radius·좌표가 없으면 반경 대신 그 동(직방 서버의 법정동 코드 조회)을 찾는다.

    '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)은 그 동들을 함께 넘긴다 (서버가 코드 여럿을 한 번에 받는다). 리·구·시·역·학교
    이름은 중심 반경으로 찾는다.

    Returns:
        (검색 중심, 안내, 찾을 동들 또는 None, 반경 km).
    """
    radius_km = radius or DEFAULT_RADIUS_KM
    if lat is not None and lng is not None:
        region, notes = _region(client, query, lat, lng, radius_km)
        return region, notes, None, radius_km
    region, split_note, split_items = resolve_region_scope(client, query or '')
    notes = []
    dongs: list[ZigbangRegion] | None = None
    if radius is None and is_dong_code(region.legal_division_code):
        # '○가' 동의 좌표는 동 안을 찾을 때만 쓴다 (반경 검색은 쓰지 않아 좌표가 없어도 막히지 않게 여기서 바꾼다)
        split = [region_from_search_item(item) for item in split_items]
        dongs = split or [region]
        if split:
            region = merged_dong_region(region, split)
            split_note = None
        notes.append(note('범위', f'{region.name} 안을 찾았습니다 (반경으로 찾으려면 --radius)'))
    elif wide_note := wide_area_note(query or '', region, radius_km):
        notes.append(wide_note)
    if split_note:
        notes.append(split_note)
    return region, notes, dongs, radius_km


def _require_center(query: str | None, lat: float | None, lng: float | None) -> None:
    # 좌표를 하나만 줬으면 '지역 이름을 주세요' 보다 '둘 다 주세요' 가 맞는 안내라 먼저 본다
    require_korea(lat, lng)
    if query is None and (lat is None or lng is None):
        raise typer.BadParameter('지역 이름 또는 --lat/--lng 를 주세요', param_hint='QUERY')


def _room_conditions(
    *,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
    room: list[str] | None,
    manage_cost_min: int | None,
    manage_cost_max: int | None,
    no_manage_cost: bool,
    area_min: float | None,
    area_max: float | None,
    area_pyeong_min: float | None,
    area_pyeong_max: float | None,
    floor: list[str] | None,
    bathroom: int | None,
    option: list[str] | None,
    condition: list[str] | None,
) -> ZigbangRoomConditions:
    """room 과 --complex 가 같이 받는 가격·방·건물 조건을 조회 전에 검사해 조건 모델로 만든다. 거래 유형은 비워 둔다.

    두 명령이 같은 조건을 같은 검사로 받도록 범위(`validate_ranges`)·관리비 없음과 관리비 범위 함께 쓰기·목록 값(`split_csv`)을
    여기 한 곳에서 본다. 인자에 기본값이 없어 한쪽 명령에서 조건을 빠뜨리면 mypy 가 잡는다. 거래 유형은 명령마다 고르는
    방식이 달라(아파트 단지는 단기임대 제외) 부르는 쪽이 `model_copy(update={'trade_types': ...})` 로 넣는다.
    조건 모델 검증 오류가 입력 오류(INVALID_ARGUMENT)로 나가도록 `handle_errors` 안에서 부른다.

    Raises:
        typer.BadParameter: 범위가 거꾸로이거나 유한하지 않을 때, --no-manage-cost 와 관리비 범위를 함께 줬을 때,
            목록 값이 허용 밖일 때.
    """
    validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
        ('manage-cost', manage_cost_min, manage_cost_max),
        ('area', area_min, area_max),
        ('area-pyeong', area_pyeong_min, area_pyeong_max),
    )
    if no_manage_cost and (manage_cost_min is not None or manage_cost_max is not None):
        raise typer.BadParameter('--no-manage-cost 는 관리비 범위와 함께 쓸 수 없습니다', param_hint='--no-manage-cost')
    return ZigbangRoomConditions(
        deposit_min=deposit_min,
        deposit_max=deposit_max,
        rent_min=rent_min,
        rent_max=rent_max,
        price_min=price_min,
        price_max=price_max,
        room_types=split_csv(room, ROOM_TYPES, '--room', ROOM_HINTS),
        manage_cost_min=manage_cost_min,
        manage_cost_max=manage_cost_max,
        no_manage_cost=no_manage_cost,
        area_min_m2=area_min,
        area_max_m2=area_max,
        area_min_pyeong=area_pyeong_min,
        area_max_pyeong=area_pyeong_max,
        floors=split_csv(floor, FLOOR_FILTERS, '--floor', ROOM_HINTS),
        bathroom_count=bathroom,
        options=split_csv(option, OPTION_FILTERS, '--option', ROOM_HINTS),
        extra_conditions=split_csv(condition, CONDITIONS, '--condition', ROOM_HINTS),
    )


app.add_typer(search_app, name='search')


search_app.add_typer(listings_app, name='listings')


@search_app.command('locations')
def locations_command(
    query: Annotated[str, typer.Argument(help='지역·역·학교·단지 이름 (예: 역삼동, 강남역, 디에이치퍼스티어아이파크)')],
    limit: Annotated[int, typer.Option(min=1, max=1200, help='지역·단지 후보 각각의 최대 결과 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """지역/역 이름을 좌표와 법정동코드로 바꾸고, 이름이 맞는 아파트 단지·오피스텔 건물 후보도 찾는다.

    complexes[].complex_id 를 jibsa zigbang complex·search listings --complex 에 넘긴다. 직방 검색은 예전 이름·별칭으로도
    맞추므로 주소·세대수를 보고 원하는 단지인지 확인한다.

    예: jibsa zigbang search locations 디에이치퍼스티어아이파크
    """
    with handle_errors(SOURCE), ZigbangClient() as client:
        regions, complexes = search_regions_and_complexes(client, query, limit=limit)
        items = regions[:limit]
        emit(
            {
                'query': query,
                # 리뷰 오탐 (2026-11-25): 직방 results 는 주소·역·학교 후보가 섞여(type) 용어집이 regions 로 바꾸는 '지역만 담은 results' 가 아니다 (다방은 지역 regions·역 stations 를 나눠 준다)
                'results': [
                    {
                        'type': item.type,
                        'name': item.name,
                        'address': normalize_address(item.description),
                        'lat': item.lat,
                        'lng': item.lng,
                        'legal_division_code': item.source.legal_division_code if item.source else None,
                    }
                    for item in items
                ],
                'complexes': [candidate.model_dump() for candidate in complexes],
            },
            pretty,
        )


@search_app.command('complexes')
def complexes_command(
    query: Annotated[str, typer.Argument(help='역·학교·동·구 이름 (예: 강남역, 해누리중학교, 가락동)')],
    order: Annotated[
        str | None,
        typer.Option(
            '--order',
            help=(
                f"직방 웹 탭: {', '.join(COMPLEX_ORDERS)}. 최근입주·시세급변동은 그 조건에 든 단지만 담는다 (total 도 그 수). "
                '기본 역·학교는 인기, 동·구는 최근입주 (동·구는 최근입주만 받는다)'
            )
        )
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help=f'받을 단지 수 (최대 {MAX_LIST_LIMIT}곳)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """역·학교·동·구 주변 아파트 단지를 직방 웹 아파트 지도의 단지 목록(--order 탭) 그대로 준다.

    이름 끝이 '역' 이면 역(1.5km 안 '<역> 주변단지'), '학교' 면 학교('<학교> 배정단지'), 그 밖은 동·구다. 목록은 --order
    탭(인기·최근입주·시세급변동·평당가)으로 고르고 가까운 순이 아니다. 최근입주·시세급변동은 순서가 아니라 그 조건에 든 단지만
    담은 목록이라 total 도 그 수이고 그 곳의 전체 단지 수가 아니다. 역·학교는 단지마다 거리(distance_km)가 있으니 가까운
    단지는 그 값으로 고른다. 동·구는 웹 지역 화면에 최근입주 목록뿐이라 --order 는 최근입주만 받고 거리가 없다. highlight 는
    웹 단지 카드 둘째 줄이고 --order 마다 뜻이 다르다 (인기는 지역 순위, 최근입주는 입주 시기, 시세급변동은 1주 변동률,
    평당가는 평당가). 학교는 결과 맨 끝의 school 에 학교 정보(학생 수·입학생·학급·학비·급식비와 같은 구 평균, 진학 현황)가 붙고 배정단지가
    없어도 나온다. 단지 매물은 결과의 complex_id 로 jibsa zigbang search listings --complex <complex_id>, 단지 정보는
    jibsa zigbang complex <complex_id>.

    예: jibsa zigbang search complexes 강남역 --limit 10
        jibsa zigbang search complexes 해누리중학교 --order 평당가
        jibsa zigbang search complexes 가락동
    """
    chosen_order = check_choice(order, COMPLEX_ORDERS, '--order') if order is not None else None
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = search_place_complexes(client, query, order=chosen_order, limit=limit)
        emit(result, pretty)


@listings_app.command('room')
def search_room_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"매물 유형: {', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 전체. 원룸은 방 하나짜리라 원룸형 오피스텔도 나온다 (방 1개짜리 아파트는 search listings apt 로)")
    ] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 전세, 월세, 매매, 단기임대. 반복하거나 쉼표로 구분. 기본 전체 (월세에는 단기임대가 빠진다)')
    ] = None,
    room: Annotated[
        list[str] | None,
        typer.Option(
            '--room',
            help=f"방 구조: {', '.join(ROOM_TYPES)}. 반복하거나 쉼표로 구분 (OR). 원룸 카테고리=원룸형 3종(빌라 건물 원룸 포함), 빌라=투룸 이상, 오피스텔=원룸형·투룸·쓰리룸 이상"
        )
    ] = None,
    radius: ScopeRadiusOption = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='직방 목록 순으로 확인할 매물 수 (제외 전). 종류가 여럿이면 종류별로 고르게 나눈다')] = 15,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    manage_cost_min: Annotated[int | None, typer.Option(min=0, help='월 관리비 하한 (만원)')] = None,
    manage_cost_max: Annotated[int | None, typer.Option(min=0, help='월 관리비 상한 (만원)')] = None,
    no_manage_cost: Annotated[bool, typer.Option('--no-manage-cost', help='관리비 없는 매물만 (관리비 범위와 함께 못 씀)')] = False,
    area_min: AreaMinOption = None,
    area_max: AreaMaxOption = None,
    area_pyeong_min: AreaPyeongMinOption = None,
    area_pyeong_max: AreaPyeongMaxOption = None,
    floor: Annotated[
        list[str] | None,
        typer.Option('--floor', help=f"층: {', '.join(FLOOR_FILTERS)}. 반복하거나 쉼표로 구분 (OR). 지상은 반지하·옥탑방 제외")
    ] = None,
    bathroom: Annotated[int | None, typer.Option(min=1, max=3, help='욕실 수. 1·2 는 정확히 그 수, 3 은 3개 이상')] = None,
    option: Annotated[
        list[str] | None,
        typer.Option('--option', help=f"옵션: {', '.join(OPTION_FILTERS)}. 반복하거나 쉼표로 구분 (AND, 모두 갖춘 매물)")
    ] = None,
    condition: Annotated[
        list[str] | None,
        typer.Option('--condition', help=f"기타 조건: {', '.join(CONDITIONS)}. 반복하거나 쉼표로 구분 (AND)")
    ] = None,
    details: Annotated[
        bool,
        typer.Option(
            '--details',
            help=(
                f'매물마다 상세를 1회씩 더 받아 건물 용도(residence_type, 근린생활시설·고시원 등)와 사용승인일(approved_date)을 붙인다. '
                f'요청이 매물 수만큼 늘어난다 (앞 {DETAILS_MAX}건). 직방에는 연식 조건이 없어 연식은 이것으로 본다'
            ),
        ),
    ] = False,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """원룸·오피스텔·빌라를 직방 목록 순서(안심추천 → 안심일반 → 일반)로 조회한다. 모든 조건은 직방 서버에서 거른다.

    거리순이 아니다. 매물마다 검색 중심에서의 거리(distance_km)가 있으니 가까운 매물은 그 값으로 고른다.
    종류를 여럿 찾으면(기본은 원룸·오피스텔·빌라 모두) --limit 을 종류별로 고르게 나눠 종류별 묶음으로 준다.
    동 이름을 주고 --radius 를 주지 않으면 반경 대신 그 동 경계 안의 매물을 준다.
    역 이름은 직방 역 주변 목록(반경은 --radius), 학교·구·시 이름과 --lat/--lng 는 반경 검색이다. 반경 밖 매물은 나오지 않는다.

    예: jibsa zigbang search listings room 역삼동 -t 원룸 --trade 월세 --deposit-max 1000 --rent-max 70
        jibsa zigbang search listings room 역삼동 -t 빌라,오피스텔 --room 투룸 --trade 전세 --condition 전세대출,엘리베이터
        jibsa zigbang search listings room 신림역 --floor 지상 --option 에어컨,세탁기 --manage-cost-max 10
        jibsa zigbang search listings room 성수동 -t 원룸 --trade 월세 --limit 10 --details
        jibsa zigbang search listings room 성수동 -t 원룸 --trade 월세 --limit 10 --next <앞 결과의 next>
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    position = decode_next(next_)
    with handle_errors(SOURCE):
        conditions = _room_conditions(
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            room=room,
            manage_cost_min=manage_cost_min,
            manage_cost_max=manage_cost_max,
            no_manage_cost=no_manage_cost,
            area_min=area_min,
            area_max=area_max,
            area_pyeong_min=area_pyeong_min,
            area_pyeong_max=area_pyeong_max,
            floor=floor,
            bathroom=bathroom,
            option=option,
            condition=condition,
        )
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type', ROOM_HINTS)
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, TRADE_TYPES, '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
    )
    conditions = conditions.model_copy(update={'trade_types': trade_types})
    skipped_types = unsearchable_types(property_types, trade_types)
    if skipped_types:
        trade_notes.append(unsearchable_note(skipped_types))
    if '단기임대' in trade_types:
        trade_notes.append(STAY_SERVICE_NOTE)

    with handle_errors(SOURCE), ZigbangClient() as client:
        region, notes, boundary, radius_km = _scope(client, query, lat, lng, radius, GEOHASH_PRECISION)
        result = search_listings(
            client,
            region,
            conditions=conditions,
            property_types=property_types,
            radius_km=radius_km,
            limit=limit,
            boundary=boundary,
            subway_id=region.subway_id,
            start=position,
        )
        if details:
            result = attach_building_use(client, result)
        emit(result, pretty, notes=trade_notes + notes, next_token=encode_next(result.next_position), fields=fields)


@listings_app.command('apt')
def search_apt_command(
    query: Annotated[
        str | None,
        typer.Argument(help='동·구 이름 (예: 역삼동, 강남구). 역 이름(예: 강남역)을 주면 그 역이 속한 동을 찾는다. --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 매매, 전세, 월세. 반복하거나 쉼표로 구분. 기본 전체')
    ] = None,
    limit: AptLimitOption = 20,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    area_min: Annotated[float | None, typer.Option(min=0, help='전용면적 하한 (㎡). 직방이 받지 않아 받은 뒤 거른다')] = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='전용면적 상한 (㎡). 직방이 받지 않아 받은 뒤 거른다')] = None,
    supply_area_min: Annotated[
        float | None, typer.Option(min=0, help='공급면적 하한 (㎡). 직방 서버에서 거른다'),
    ] = None,
    supply_area_max: Annotated[
        float | None, typer.Option(min=0, help='공급면적 상한 (㎡). 직방 서버에서 거른다'),
    ] = None,
    no_new_sale: Annotated[
        bool,
        typer.Option('--no-new-sale', help='신규분양 매물을 빼고 본다 (직방 웹의 "신규 분양 포함" 을 끈 목록)'),
    ] = False,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """아파트 매물. 동·구 하나의 직방 지역 목록을 직방 순서 그대로 준다 (거리 없음).

    역·학교 이름이나 --lat/--lng 를 주면 그 위치가 속한 동의 목록을 준다 (직방 웹 지도의 '○○동 주변 매물보기').
    그 위치에서 가까운 순이 아니고 이웃 동은 빠진다. 성수동(성수동1가·2가)·성남시(분당구·수정구·중원구)처럼 직방이
    따로 보여 주는 지역 여럿에 걸리는 이름은 REGION_AMBIGUOUS 로 후보를 알려 주니 하나를 골라 다시 찾는다.
    결과는 같은 호·거래 유형의 매물을 묶은 것이다 (realtor_count 는 같은 호를 올린 중개사 수). 상세는 결과의 id 로 jibsa zigbang listing <id>.
    가격 범위(mixed_prices true) 줄은 가격이 묶음 최저가라 매물별 가격은 jibsa zigbang catalog <catalog_id>.

    예: jibsa zigbang search listings apt 강남구 --trade 매매 --price-max 200000
        jibsa zigbang search listings apt 역삼동 --trade 전세 --area-min 59
        jibsa zigbang search listings apt 강남역 --trade 전세
        jibsa zigbang search listings apt 역삼동 --supply-area-min 80 --supply-area-max 110
        jibsa zigbang search listings apt 파주시 --no-new-sale

    --no-new-sale 은 신규분양 매물(listing_kind 신규분양)을 빼고 total 도 그만큼 준다. 단지 매물(--complex)에는 없다.

    결과에 next 가 있으면 같은 지역·조건에 --next <결과의 next 값> 을 붙여 이어 받는다.
    """
    position = decode_next(next_)
    _require_center(query, lat, lng)
    validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
        ('area', area_min, area_max),
        ('supply-area', supply_area_min, supply_area_max),
    )
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, APT_TRADE_TYPES, '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
        allowed=APT_TRADE_TYPES,
    )
    with handle_errors(SOURCE), ZigbangClient() as client:
        conditions = ZigbangAptConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            area_min_m2=area_min,
            area_max_m2=area_max,
            supply_area_min_m2=supply_area_min,
            supply_area_max_m2=supply_area_max,
            exclude_new_sale=no_new_sale,
        )
        if lat is not None and lng is not None:
            district = apt_dong_at(client, lat, lng)
            notes = [note(
                '범위',
                f"좌표가 속한 {district.name}의 아파트 목록입니다 (직방 웹 지도의 '{district.name} 주변 매물보기'). "
                '좌표에서 가까운 순이 아니고 이웃 동은 빠집니다',
            )]
        else:
            items = search_regions(client, query or '')
            try:
                district, notes = resolve_apt_region(client, query or '', items=items)
            except RegionNotFoundError:
                # 동·구가 아닌 곳(역·학교)은 웹 아파트 지도처럼 그 위치가 속한 동의 목록으로 찾는다. 반경 안 단지의 매물을 거리순으로
                # 잇는 목록은 웹에 없다 (2026-11-15 캡처: 역을 고르면 주변 단지 목록과 지도 가운데 동의 매물 목록만 있다).
                # 지역(시·도, 행정동처럼 결과가 없는 이름)은 동 이름으로 다시 찾으라는 에러를 그대로 낸다. 좌표를 보지 않으므로
                # 좌표 없는 시·도가 좌표 에러(UPSTREAM_ERROR)로 바뀌지 않게, 지역으로 바꾸기 전의 검색 결과로 먼저 가른다
                place_item, _ = region_scope_items(query or '', items)
                if place_item.type == 'address':
                    raise
                place = region_from_search_item(place_item)
                district = apt_dong_at(client, place.lat, place.lng)
                # `search complexes` 에 권할 검색어. 검색어 끝 낱말이 찾은 곳의 이름이면 그 검색어 전체다. 사용자가 구·동 낱말을 붙여 같은
                # 이름의 역·학교 중 하나를 가렸으면('영등포구 양평역') 이름만 권하면 그 명령이 어느 곳인지 다시 묻고 멈춘다
                # (REGION_AMBIGUOUS). 공백이 있으면 작은따옴표로 감싼다
                words = (query or '').split()
                chosen = ' '.join(words) if words and words[-1] == place.name else place.name
                complexes_command_text = 'jibsa zigbang search complexes ' + (f"'{chosen}'" if len(chosen.split()) > 1 else chosen)
                # search complexes 가 찾는 역·학교만 권한다. 배정단지 목록이 없는 학교(학교 코드가 없거나 'NL_' 로 시작)는 그 명령이
                # INVALID_ARGUMENT 라 권하지 않는다 (`school_has_assigned_complexes`)
                notes = [note(
                    '범위',
                    f"{quoted(query or '', '은/는')} 동·구가 아니라 그 위치가 속한 {district.name}의 아파트 목록을 찾았습니다 "
                    f"(직방 웹 지도의 '{district.name} 주변 매물보기'). {place.name}에서 가까운 순이 아니고 이웃 동은 빠집니다"
                    + (
                        f'. 역 주변 단지는 {complexes_command_text}'
                        if place.subway_id is not None
                        else f'. 학교 배정단지는 {complexes_command_text}'
                        if place.search_type == 'school' and school_has_assigned_complexes(place_item) else ''
                    ),
                )]
        result = search_apt_listings(client, district, conditions=conditions, limit=limit, start=position)
        emit(result, pretty, notes=trade_notes + notes, next_token=encode_next(result.next_position), fields=fields)


def _require_complex_id(complex_id: str, param_hint: str = 'COMPLEX_ID') -> None:
    if COMPLEX_ID_PATTERN.match(complex_id.strip()) is None:
        raise typer.BadParameter(
            f"직방 단지 ID 형식이 아닙니다: '{complex_id}'. jibsa zigbang search locations <단지 이름> 결과의 "
            "complex_id 를 그대로 주세요 (예: apt-68579, officetel-20227)",
            param_hint=param_hint,
        )


@app.command('complex')
def complex_command(
    complex_id: ComplexIdArgument,
    pretty: PrettyOption = None,
) -> None:
    """단지 정보와 지금 올라온 매물 수. 아파트는 거래 유형별 매물 수와 평형 목록(search listings --complex --pyeong 값), 평형별 면적·관리비·직방시세, 단지 직방시세·순위·함께 보면 좋은 단지·토지거래허가도 준다.

    예: jibsa zigbang complex apt-68579
    """
    _require_complex_id(complex_id)
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_complex(client, complex_id.strip())
        emit(result, pretty)


@listings_app.callback()
def complex_listings_command(
    ctx: typer.Context,
    complex_id: Annotated[str | None, typer.Option('--complex', help='아파트·오피스텔 단지 ID (apt-… / officetel-…)')] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 전세, 월세, 매매, 단기임대(오피스텔만). 반복하거나 쉼표로 구분. 기본 전체')
    ] = None,
    pyeong: Annotated[
        list[str] | None,
        typer.Option('--pyeong', metavar='<int>', help='평형 ID (complex 결과의 pyeongs[].pyeong_id, 아파트만. 아파트 매물의 pyeong_id 와 같은 번호). 반복하거나 쉼표로 구분 (OR)')
    ] = None,
    limit: Annotated[int | None, typer.Option(min=1, max=MAX_LIST_LIMIT, help='최대 결과 수. 기본 아파트 20, 오피스텔 15')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    room: Annotated[
        list[str] | None,
        typer.Option('--room', help=f"방 구조 (오피스텔만): {', '.join(ROOM_TYPES)}. 반복하거나 쉼표로 구분 (OR)")
    ] = None,
    manage_cost_min: Annotated[int | None, typer.Option(min=0, help='월 관리비 하한 (만원, 오피스텔만)')] = None,
    manage_cost_max: Annotated[int | None, typer.Option(min=0, help='월 관리비 상한 (만원, 오피스텔만)')] = None,
    no_manage_cost: Annotated[bool, typer.Option('--no-manage-cost', help='관리비 없는 매물만 (오피스텔만, 관리비 범위와 함께 못 씀)')] = False,
    area_min: Annotated[float | None, typer.Option(min=0, help='전용면적 하한 (㎡, 오피스텔만)')] = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='전용면적 상한 (㎡, 오피스텔만)')] = None,
    area_pyeong_min: Annotated[float | None, typer.Option(min=0, help='면적 하한 (평, 오피스텔만)')] = None,
    area_pyeong_max: Annotated[float | None, typer.Option(min=0, help='면적 상한 (평, 오피스텔만)')] = None,
    floor: Annotated[
        list[str] | None,
        typer.Option('--floor', help=f"층 (오피스텔만): {', '.join(FLOOR_FILTERS)}. 반복하거나 쉼표로 구분 (OR)")
    ] = None,
    bathroom: Annotated[int | None, typer.Option(min=1, max=3, help='욕실 수 (오피스텔만). 1·2 는 정확히 그 수, 3 은 3개 이상')] = None,
    option: Annotated[
        list[str] | None,
        typer.Option('--option', help=f"옵션 (오피스텔만): {', '.join(OPTION_FILTERS)}. 반복하거나 쉼표로 구분 (AND)")
    ] = None,
    condition: Annotated[
        list[str] | None,
        typer.Option('--condition', help=f"시설 조건 (오피스텔만): {', '.join(CONDITIONS)}. 반복하거나 쉼표로 구분 (AND)")
    ] = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 하나의 매물 목록 (직방 목록 순, 거리가 없다). 조건은 직방 서버에서 거른다.

    상세는 결과의 id 로 jibsa zigbang listing <id>. 아파트의 가격 범위(mixed_prices true) 줄은 가격이 묶음 최저가라
    매물별 가격은 jibsa zigbang catalog <catalog_id>.

    예: jibsa zigbang search listings --complex apt-68579 --trade 전세 --deposit-max 150000
        jibsa zigbang search listings --complex officetel-20227 --trade 월세 --rent-max 100 --option 침대 --condition 반려동물
    """
    if ctx.invoked_subcommand is not None:
        supplied = [
            name for name in ctx.params
            if (source := ctx.get_parameter_source(name)) is not None and source.name == 'COMMANDLINE'
        ]
        if supplied:
            raise typer.BadParameter(
                '유형별 검색 옵션은 room·apt·store·stay 뒤에 지정하세요. --complex 모드와 함께 사용할 수 없습니다',
            )
        return
    if complex_id is None:
        raise typer.BadParameter('--complex를 주거나 room·apt·store·stay 중 하나를 선택하세요', param_hint='--complex')
    # 단지 모드는 위치 인자가 아니라 --complex 옵션으로 받는다
    _require_complex_id(complex_id, param_hint='--complex')
    pyeong_ids = split_ints(pyeong, '--pyeong')
    if limit is None:
        limit = 15 if complex_id.strip().startswith('officetel-') else 20
    with handle_errors(SOURCE):
        conditions = _room_conditions(
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            room=room,
            manage_cost_min=manage_cost_min,
            manage_cost_max=manage_cost_max,
            no_manage_cost=no_manage_cost,
            area_min=area_min,
            area_max=area_max,
            area_pyeong_min=area_pyeong_min,
            area_pyeong_max=area_pyeong_max,
            floor=floor,
            bathroom=bathroom,
            option=option,
            condition=condition,
        )
    has_building_filters = bool(conditions.room_types) or any(
        value is not None and value != [] for value in room_filter_of(conditions).values()
    )
    if complex_id.strip().startswith('apt-') and has_building_filters:
        raise typer.BadParameter('관리비·방 구조·면적·층·욕실·옵션·시설 조건은 officetel-... 건물 ID 에만 사용할 수 있습니다')
    is_apt = complex_id.strip().startswith('apt-')
    given_trades = split_csv(trade, TRADE_TYPES, '--trade')
    apt_trade_notes: list[str] = []
    if is_apt and '단기임대' in given_trades:
        # search listings apt 처럼 조회 전에 알린다. 그대로 보내면 단기임대만일 때 안내 없이 0건이고
        # 단지가 있는지도 확인하지 않았다 (2026-10-10 실측: 없는 단지 ID 도 0건 성공)
        given_trades = [trade_type for trade_type in given_trades if trade_type != '단기임대']
        if not given_trades:
            raise typer.BadParameter(
                '아파트 단지에는 단기임대가 없습니다. 단기임대는 오피스텔 건물(officetel-…)에만 있습니다',
                param_hint='--trade',
            )
        apt_trade_notes.append(note('거래', f"아파트 단지에는 단기임대가 없어 {'·'.join(given_trades)}만 찾았습니다"))
    trade_types, trade_notes = infer_trade_types(
        given_trades,
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
        # 보증금 조건만 주면 전세·월세·단기임대로 좁히는데, 아파트에는 단기임대가 없다
        allowed=APT_TRADE_TYPES if is_apt else None,
    )
    trade_notes = apt_trade_notes + trade_notes
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = list_complex_listings(
            client,
            complex_id.strip(),
            conditions=conditions.model_copy(update={'trade_types': trade_types}),
            pyeong_ids=pyeong_ids,
            limit=limit,
        )
        emit(result, pretty, notes=trade_notes, fields=fields)


@listings_app.command('store')
def store_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    trade: Annotated[
        str | None,
        typer.Option('--trade', help=f"거래 유형: {', '.join(STORE_TRADE_TYPES)} (임대는 월세·전세). 기본 전체")
    ] = None,
    business: Annotated[
        list[str] | None,
        typer.Option(
            '--business',
            help=(
                '업종 또는 업종 대분류 (예: 카페/커피, 편의점/슈퍼, 휴게음식점). 반복하거나 쉼표로 구분 (OR). '
                '대분류는 휴게음식점, 일반음식/주류점, 스포츠/마사지/오락, 판매업, 기타. '
                '결과 뒤에 직방 웹처럼 이 지역 비어있는 상가(업종과 상관없는 공실, vacant_section true) 줄이 이어지고 total 에 든다. '
                '업종 조건으로 공실 줄은 줄지 않는다'
            )
        )
    ] = None,
    first_floor: Annotated[bool, typer.Option('--first-floor', help='1층 매물만')] = False,
    area_min: AreaMinOption = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='면적 상한 (㎡, 미만)')] = None,
    deposit_min: Annotated[int | None, typer.Option(min=0, help='보증금/전세금 하한 (만원, 포함)')] = None,
    deposit_max: Annotated[int | None, typer.Option(min=0, help='보증금/전세금 상한 (만원, 포함)')] = None,
    rent_min: Annotated[int | None, typer.Option(min=0, help='월세 하한 (만원, 포함)')] = None,
    rent_max: Annotated[int | None, typer.Option(min=0, help='월세 상한 (만원, 포함)')] = None,
    price_min: Annotated[int | None, typer.Option(min=0, help='매매가 하한 (만원, 포함)')] = None,
    price_max: Annotated[int | None, typer.Option(min=0, help='매매가 상한 (만원, 포함)')] = None,
    manage_cost_min: Annotated[int | None, typer.Option(min=0, help='월 관리비 하한 (만원, 포함)')] = None,
    manage_cost_max: Annotated[int | None, typer.Option(min=0, help='월 관리비 상한 (만원, 포함)')] = None,
    key_money_min: Annotated[int | None, typer.Option(min=0, help='권리금 하한 (만원, 포함)')] = None,
    key_money_max: Annotated[int | None, typer.Option(min=0, help='권리금 상한 (만원, 포함)')] = None,
    radius: ScopeRadiusOption = None,
    limit: LimitOption = 15,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """상가·사무실을 직방 목록 순서 그대로 조회한다 (거리순 아님, 거리는 distance_km). 가격은 요약을 받은 뒤 거른다. 모르는 금액은 제외한다.

    동 이름을 주고 --radius 를 주지 않으면 그 동 안을, 역·구 이름·좌표·--radius 는 중심에서 반경 안을 찾는다.

    직방이 이 지역 비어있는 상가(업종과 상관없는 공실) 묶음을 주면 직방 웹처럼 결과 뒤에 그 줄(vacant_section true)이 이어지고
    total 에 든다 (업종 조건이 없어도). 업종 조건으로 공실 줄은 줄지 않으니 업종 매물만 보려면 vacant_section 이 false 인 줄을 읽는다.

    상세는 결과의 id(store-123) 로 jibsa zigbang listing <id>.

    예: jibsa zigbang search listings store 성수동 --trade 임대 --first-floor --business 카페/커피
        jibsa zigbang search listings store 강남역 --area-min 66 --radius 0.5
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    store_trade = check_choice(trade, STORE_TRADE_TYPES, '--trade') if trade is not None else '전체'
    # 금액 범위는 store_price_trade 가 거꾸로 된 범위를 거절한다. 면적은 float 이라 inf 가 typer 의 min=0 을 통과해
    # 요청 JSON 인코딩에서 PARSE_ERROR 로 끝났다 (2026-10-11 실측: --area-min inf). 상한이 '미만' 이라 같은 값도 막아야 해서
    # validate_ranges(min > max 만 거절) 대신 유한한지만 보고 범위는 아래 검사 하나로 본다
    require_finite('--area-min', area_min)
    require_finite('--area-max', area_max)
    # 상한이 '미만' 이라 0 은 맞는 매물이 없다. 요청 모델(gt=0)이 지역 검색·경계 요청을 보낸 뒤 영어 메시지로 막던 것을
    # 요청 전에 막는다 (2026-10-12 실측: --area-max 0 이 요청 3회 뒤 'Input should be greater than 0')
    if area_max is not None and area_max <= 0:
        raise typer.BadParameter('--area-max 는 0 보다 커야 합니다 (상한은 미만 조건)', param_hint='--area-max')
    if area_min is not None and area_max is not None and area_min >= area_max:
        raise typer.BadParameter('--area-max 는 --area-min 보다 커야 합니다', param_hint='--area-max')
    with handle_errors(SOURCE):
        effective_trade = store_price_trade(store_trade, {
            'deposit_manwon': (deposit_min, deposit_max),
            'rent_manwon': (rent_min, rent_max),
            'price_manwon': (price_min, price_max),
            'manage_cost_manwon': (manage_cost_min, manage_cost_max),
            'key_money_manwon': (key_money_min, key_money_max),
        })
    price_notes = []
    if trade is None and effective_trade != '전체':
        price_notes.append(note('거래', f'가격 조건에 맞춰 거래 유형을 {effective_trade}로 좁혔습니다'))
    businesses = split_csv(business, STORE_BUSINESS_NAMES, '--business')
    with handle_errors(SOURCE), ZigbangClient() as client:
        region, notes, dongs, radius_km = _store_scope(client, query, lat, lng, radius)
        result = search_store_listings(
            client,
            region,
            conditions=ZigbangStoreConditions(
                trade=effective_trade,
                first_floor=first_floor,
                businesses=businesses,
                area_min_m2=area_min,
                area_max_m2=area_max,
                deposit_min=deposit_min,
                deposit_max=deposit_max,
                rent_min=rent_min,
                rent_max=rent_max,
                price_min=price_min,
                price_max=price_max,
                manage_cost_min=manage_cost_min,
                manage_cost_max=manage_cost_max,
                key_money_min=key_money_min,
                key_money_max=key_money_max,
            ),
            radius_km=radius_km,
            dongs=dongs,
            limit=limit,
        )
        emit(result, pretty, notes=price_notes + notes, fields=fields)


@listings_app.command('stay')
def stay_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    weekly_rent_min: Annotated[int | None, typer.Option(min=0, help='주당 요금 하한 (만원)')] = None,
    weekly_rent_max: Annotated[int | None, typer.Option(min=0, help='주당 요금 상한 (만원)')] = None,
    rooms: Annotated[int | None, typer.Option(min=1, max=4, help='방 수. 1~3 은 정확히 그 수, 4 는 4개 이상')] = None,
    building: Annotated[
        list[str] | None,
        typer.Option('--building', help=f"방 종류: {', '.join(STAY_BUILDING_TYPE_BY_LABEL)}. 반복하거나 쉼표로 구분 (OR)")
    ] = None,
    area_min: Annotated[float | None, typer.Option(min=0, help='전용면적 하한 (㎡)')] = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='전용면적 상한 (㎡)')] = None,
    discount: Annotated[
        list[str] | None,
        typer.Option('--discount', help=f"할인: {', '.join(STAY_DISCOUNT_TYPE_BY_LABEL)}. 반복하거나 쉼표로 구분 (OR)")
    ] = None,
    pet: Annotated[bool, typer.Option('--pet', help='반려동물 허용 매물만')] = False,
    structure: Annotated[str | None, typer.Option('--structure', help='구조: 복층, 단층')] = None,
    option: Annotated[
        list[str] | None,
        typer.Option('--option', help=f"옵션: {', '.join(STAY_OPTION_BY_LABEL)}. 반복하거나 쉼표로 구분 (AND)")
    ] = None,
    parking: Annotated[bool, typer.Option('--parking', help='주차 가능 매물만')] = False,
    elevator: Annotated[bool, typer.Option('--elevator', help='엘리베이터 있는 매물만')] = False,
    floor: Annotated[
        list[str] | None,
        typer.Option('--floor', help=f"층: {', '.join(STAY_FLOOR_TYPE_BY_LABEL)}. 반복하거나 쉼표로 구분 (OR)")
    ] = None,
    check_in: Annotated[str | None, typer.Option(help='입주 희망일 (YYYY-MM-DD). --check-out 과 함께')] = None,
    check_out: Annotated[str | None, typer.Option(help='마지막으로 머무는 날 (YYYY-MM-DD). 직방은 이 날까지 이용일로 센다 (4주 = 11-01~11-28). --check-in 과 함께')] = None,
    flexibility: Annotated[int | None, typer.Option(min=0, max=30, help='일정을 앞뒤로 며칠까지 유연하게 볼지 (--check-in 과 함께)')] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=MAX_RADIUS_KM, help='검색 반경 (km). 주면 이름 검색도 그 중심에서 반경 안의 지도 매물을 찾는다. 안 주면 역·학교·동·구 이름은 직방 단기임대 검색 결과 그대로, 좌표는 1km'),
    ] = None,
    # 다른 명령의 --sort 와 달리 값이 영어지만 바꾸지 않는다 (바꾸면 호환 깨짐). 2026-10-31 에이전트 검증에서 이 명령을 쓴
    # 2명 모두 --help 대로 --sort price 를 줬고, 한국어 값을 주면 에러 hint 가 값들을 알린다
    sort: Annotated[
        str,
        typer.Option(
            '--sort',
            help=(
                'recommended 직방 추천순 (기본), price 주당 임대료+관리비 낮은 순, newest 최근 등록순, '
                'distance 역에서 가까운 순 (--radius 없는 역 이름 검색에서만)'
            ),
        ),
    ] = 'recommended',
    limit: LimitOption = 15,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """직방 단기임대(주 단위 계약) 매물을 직방 추천순(기본)·가격·최근 등록 순으로 조회한다. 금액은 주당 만원.

    원룸·빌라의 '단기임대' 거래(search room --trade 단기임대)와 다른 별도 서비스다.
    역·학교·동·구 이름은 직방 단기임대 검색 결과를 직방 순서 그대로 준다 (역은 역에서 1km 안, 동·구는 이웃 동 매물이 섞일 수
    있다). --radius 나 --lat/--lng 를 주면 그 중심에서 반경 안의 지도 매물을 준다. 가까운 매물은 distance_km 로 고른다.
    상세는 결과의 id(stay-123) 로 jibsa zigbang listing <id>. 금액은 주당 임대료+관리비이고, 기간 전체 비용은 직방이 로그인한
    사용자에게만 계산해 줘서 주지 않는다.

    예: jibsa zigbang search listings stay 강남역 --weekly-rent-max 50 --building 오피스텔 --option 세탁기,와이파이
        jibsa zigbang search listings stay 역삼동 --check-in 2026-11-01 --check-out 2026-11-28 --rooms 1 --sort price
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    validate_ranges(
        ('weekly-rent', weekly_rent_min, weekly_rent_max),
        ('area', area_min, area_max),
    )
    with handle_errors(SOURCE):
        ZigbangGuestItemsFiltersRequestParameterModel(
            check_in_date=check_in, check_out_date=check_out, flexibility=flexibility,
        )
        stay_sort = check_stay_sort(sort)
        if stay_sort == 'distance' and (radius is not None or lat is not None):
            # 좌표·반경은 찾은 곳과 상관없이 늘 막히는 조합이라 지역 검색 요청 전에 막는다. 이름은 역인지 알아야 해 서비스가 막는다
            raise stay_distance_sort_error()
    if structure is not None:
        structure = check_choice(structure, STAY_STRUCTURES, '--structure')
    buildings = split_csv(building, tuple(STAY_BUILDING_TYPE_BY_LABEL), '--building')
    discounts = split_csv(discount, tuple(STAY_DISCOUNT_TYPE_BY_LABEL), '--discount')
    options = split_csv(option, tuple(STAY_OPTION_BY_LABEL), '--option')
    floors = split_csv(floor, tuple(STAY_FLOOR_TYPE_BY_LABEL), '--floor')
    with handle_errors(SOURCE), ZigbangClient() as client:
        radius_km = radius or DEFAULT_RADIUS_KM
        split_note: str | None = None
        items: list[ZigbangSearchItemModel] | None = None
        # 이름으로 찾고 --radius 를 주지 않았으면 직방 단기임대 검색(역·학교·동·구)의 결과를 그대로 받는다
        by_name = lat is None and radius is None
        whole_address = False
        if lat is not None and lng is not None:
            region, notes = _region(client, query, lat, lng, radius_km)
        else:
            items = search_regions(client, query or '')
            if by_name:
                # 어느 동·구인지 묻는 것은 좌표를 쓰지 않는다. 지역으로 바꾸기 전의 검색 결과로 먼저 판단해, 좌표 없는 동이 섞여도
                # 묻는 에러가 좌표 에러(UPSTREAM_ERROR)로 바뀌지 않게 한다
                best, split_items = region_scope_items(query or '', items)
                whole_address = best.type == 'address' and bool(best.source and best.source.local1)
                if whole_address and (divided := split_items or city_gu_search_items(query or '', items)):
                    # '○가' 로 나뉜 동(성수동 → 성수동1가·2가)과 구가 있는 시(성남시)는 직방 검색창이 동·구를 따로 준다. 지역 검색
                    # 여럿을 합친 순서·수는 웹에 없어 합치지 않고 어느 곳인지 묻는다 (2026-11-15 실측: 성수동2가 검색에 성수동1가
                    # 매물도 온다)
                    raise divided_region_error(query or '', divided)
            region, split_note, _ = resolve_region_scope(client, query or '', items=items)
            notes = []
        if split_note:
            notes.append(split_note)
        if whole_address and is_ri_code(region.legal_division_code) and region.local3:
            # 직방 지역 결과에는 리가 없고 local3 이 그 위 읍·면이라 검색 API 가 읍·면 전체를 준다 (2026-10-11 실측: 양근리 →
            # 양평읍 창대리 매물)
            notes.append(note(
                '범위',
                f"{quoted(region.name, '은/는')} 리 단위라 직방 단기임대 지역 검색이 상위 {region.local3} 기준으로 찾았습니다. "
                '리 주변만 보려면 --radius 를 주세요',
            ))
        boundary = dong_boundary(client, region) if by_name and not whole_address else None
        if boundary is not None and (wide_note := wide_boundary_note(region, boundary, STAY_GEOHASH_PRECISION, radius_km)):
            notes.append(wide_note)
            boundary = None
        if not whole_address and boundary is None and (wide_note := wide_area_note(query or '', region, radius_km)):
            notes.append(wide_note)
        conditions = ZigbangStayConditions(
            weekly_price_min=weekly_rent_min,
            weekly_price_max=weekly_rent_max,
            room_count=rooms,
            building_types=buildings,
            area_min_m2=area_min,
            area_max_m2=area_max,
            discounts=discounts,
            pet_allowed=pet,
            duplex=None if structure is None else structure == '복층',
            options=options,
            parking=parking,
            elevator=elevator,
            floors=floors,
            check_in=check_in,
            check_out=check_out,
            flexibility=flexibility,
        )
        try:
            result = search_stay_listings(
                client,
                region,
                conditions=conditions,
                sort=stay_sort,
                radius_km=radius_km,
                limit=limit,
                use_search_api=by_name,
                whole_address=whole_address,
                boundary=boundary,
            )
        except RegionNotFoundError as exc:
            if not whole_address:
                raise
            # 단기임대 지역 검색이 동을 찾지 못하면(2026-10 의 세종의 동, _search_stay_by_search_api) room·store 처럼 동 경계(넓거나
            # 없으면 반경) 안 지도 칸으로 다시 찾는다
            missing = exc.query
            region, notes, boundary, radius_km = _scope(client, query, lat, lng, radius, STAY_GEOHASH_PRECISION, items=items)
            # 대체 경로로 찾았으니 [실패] 다 (docs/common.md 의 태그 정의). 지금은 매물이 없는 곳까지
            # 지역 검색이 찾아 이 경로를 타면 직방이 바뀐 것이라 업데이트 문구를 붙인다. 매일 API 감시는 업데이트 문구 없는 [실패]
            # 를 잠깐 실패한 덤 조회로 보아, 대체 경로도 0건이면 고장 대신 확인 못 함으로 넘겼다 (2026-11-10 리뷰·실측: 세종
            # 반곡동·나성동, 매물 0건인 인제군 서화면·울릉군 울릉읍, 양근리·애월읍 모두 지역 검색이 찾았다)
            notes.insert(0, note(
                '실패',
                f"직방 단기임대 지역 검색이 {missing}{particle(missing, '을/를')} 찾지 못해 지역 전체 대신 지도로 찾았습니다. "
                f'직방 지역 검색이 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}',
            ))
            result = search_stay_listings(
                client, region, conditions=conditions, sort=stay_sort, radius_km=radius_km, limit=limit, boundary=boundary,
            )
        if check_in is not None and result.listings:
            notes.append(STAY_WEEKLY_PRICE_NOTE)
        emit(result, pretty, notes=notes, fields=fields)


@app.command('real-price')
def real_price_command(
    complex_id: Annotated[
        str,
        typer.Argument(help='아파트 단지 ID (search locations 결과의 complexes[].complex_id, search listings apt·listing의 complex_id, 예: apt-68579)'),
    ],
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세, 전체 중 하나. 전체는 매매와 전월세를 계약일 최신 순으로 한 목록에 주고, 거래마다 trade_type 이 붙는다')] = '매매',
    pyeong: Annotated[
        int | None,
        typer.Option('--pyeong', min=1, help='평형 ID (complex 결과의 pyeongs[].pyeong_id, 아파트 매물의 pyeong_id 와 같은 번호). 기본 전체 평형')
    ] = None,
    # 기본 120건(약 4~5천 토큰)이지만 낮추지 않는다. 에이전트는 대개 가이드의 '처음에는 작게' 를 따라 --limit 을 직접 준다
    # (2026-10-23 에이전트 검증: 당근 실거래를 부른 sonnet 2명 모두 --limit 8 을 줬다. 직방 실거래는 부르지 않았다)
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """아파트 단지 실거래가 (국토부 신고 기준, 최근 계약 순, 매매·전세·월세 또는 전체). cancelled: true 는 해제된 거래.

    예: jibsa zigbang real-price apt-68579 --trade 매매
        jibsa zigbang real-price apt-68579 --trade 전세 --pyeong 400085 --limit 10
        jibsa zigbang real-price apt-68579 --trade 전체 --limit 10
    """
    _require_complex_id(complex_id)
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세, 전체 중 하나)', param_hint='--trade')
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_real_prices(client, complex_id.strip(), trade_type=trade_types[0], pyeong_id=pyeong, limit=limit)
        emit(result, pretty)


@app.command('price-trend')
def price_trend_command(
    complex_id: Annotated[
        str,
        typer.Argument(help='아파트 단지 ID (complex 결과의 complex_id, 예: apt-38487). 오피스텔은 시세 추이가 없다'),
    ],
    period: Annotated[
        str,
        typer.Option('--period', help=f"기간 (웹 기간 탭): {', '.join(PRICE_TREND_PERIODS)}")
    ] = DEFAULT_PRICE_TREND_PERIOD,
    compare: Annotated[
        list[str] | None,
        typer.Option(
            '--compare',
            metavar='<complex_id>',
            help=(
                f'함께 볼 비교 단지 ID (결과의 comparable_complexes 에 있는 단지만). 반복하거나 쉼표로 구분, 최대 {MAX_COMPARE_DANJIS}곳 '
                '(웹은 1곳). --pyeong 과 함께 못 쓴다'
            )
        )
    ] = None,
    pyeong: Annotated[
        int | None,
        typer.Option('--pyeong', min=1, help='평형 ID (complex 결과의 pyeongs[].pyeong_id). 주면 그 평형의 월별 시세·거래 추이를 준다 (단지 추이 대신)')
    ] = None,
    trade: Annotated[
        str | None,
        typer.Option('--trade', help=f"평형 추이의 거래 탭: {', '.join(PYEONG_TREND_TRADES)} (기본 {DEFAULT_PYEONG_TREND_TRADE}). --pyeong 과 함께 쓴다")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """아파트 단지의 직방시세 추이 (직방 웹 단지 화면 직방시세 그래프 '3.3㎡ 당 평균가격').

    직방시세는 직방이 실거래를 분석한 추정값이고 실거래가가 아니다 (실거래는 real-price). 기본은 단지의 매매 직방시세 평당가(만원/3.3㎡)를
    월별로 보여 주는 줄 (조회 단지와 그 구. 직방시세가 없는 단지는 구 줄만)이고 --compare 로 비교 단지를 더 붙인다. 줄은 직방이 단지 ID 오름차순으로 주고 구를 끝에 붙여
    첫 줄이 조회 단지가 아닐 수 있으니 줄의 kind 로 가른다. 비교할 만한 단지는 결과의 comparable_complexes 에 있다 (웹 '단지 비교하기'
    후보). 요청은 2회 (그래프, 비교 후보). 후보는 덤 조회라 실패하면 comparable_complexes 만 null 이지만, --compare 를 주면 후보를 먼저 받아
    그 안에서만 고르게 해서(웹과 같다) 후보 조회가 실패하면 에러다.

    --pyeong 을 주면 그 평형의 월별 직방시세와 거래(최저·최고가·건수·전달 대비 변화)를 --trade 탭(전체·매매·전월세)으로 보여 준다
    (요청 2회: 단지 평형 정보로 평형 확인, 평형 시세 그래프). 거래 점·전세가율은 내지 않는다.

    예: jibsa zigbang price-trend apt-38487
        jibsa zigbang price-trend apt-38487 --period 1년 --compare apt-16629
        jibsa zigbang price-trend apt-38487 --pyeong 161661 --trade 매매
    """
    _require_complex_id(complex_id)
    chosen_period = check_choice(period, PRICE_TREND_PERIODS, '--period')
    chosen_trade = check_choice(trade, PYEONG_TREND_TRADES, '--trade') if trade is not None else None
    # `--compare apt-1 --compare apt-2` 와 `--compare apt-1,apt-2` 를 모두 받는다 (형식만 본다)
    compare_ids: list[str] = []
    for value in compare or []:
        for part in value.split(','):
            if part.strip():
                _require_complex_id(part, param_hint='--compare')
                compare_ids.append(part.strip())
    if pyeong is not None and compare_ids:
        raise HintedUsageError('--compare 와 --pyeong 은 함께 쓸 수 없습니다', '단지끼리 견주려면 --pyeong 을 빼세요')
    if chosen_trade is not None and pyeong is None:
        raise HintedUsageError('--trade 는 평형 추이(--pyeong)에만 있습니다', '--trade 는 --pyeong 과 함께 씁니다 (평형 ID 는 complex 결과의 pyeongs[].pyeong_id)')
    with handle_errors(SOURCE), ZigbangClient() as client:
        if pyeong is not None:
            pyeong_result = get_pyeong_price_trend(
                client,
                complex_id.strip(),
                pyeong,
                period=chosen_period,
                trade=chosen_trade or DEFAULT_PYEONG_TREND_TRADE,
            )
            emit(pyeong_result, pretty)
        else:
            result = get_price_trend(client, complex_id.strip(), period=chosen_period, compare=compare_ids)
            emit(result, pretty)


def _sort_help(sorts_by_trade: Mapping[str, Mapping[str, object]]) -> str:
    """`--sort` 도움말. 정렬은 거래 유형마다 다르고 각 거래의 첫 정렬이 기본이다 (웹 이름 그대로, 빈칸 없이도 받는다)."""
    return '; '.join(f"{trade}: {', '.join(sorts)}" for trade, sorts in sorts_by_trade.items())


@app.command('region-info')
def region_info_command(
    query: RegionQueryArgument,
    price_range: Annotated[
        str,
        typer.Option('--range', help=f"평당가 추이 그래프의 평형대: {', '.join(PRICE_RANGES)}. 평형대별 시세(by_pyeong_range)는 늘 모든 평형대다")
    ] = '전체',
    pretty: PrettyOption = None,
) -> None:
    """동·구의 지역 정보 (직방 웹 지역정보 화면): 단지·세대 수, 평형대별 직방시세, 월별 거래량, 평당가 추이, 구는 인구·세대도.

    직방시세(estimated_ranges·by_pyeong_range)는 직방이 실거래를 분석한 추정값이고 실거래가가 아니다. 평당가 추이(price_trend)는 웹 그래프처럼 평당가 높은
    단지 최대 3개와 그 지역 줄이고 --range 로 평형대를 고른다. 요청은 지역 검색과 지역 정보에 거래량·평당가 추이를 더해 동 4회, 구는
    인구·세대까지 6회다. 거래량·평당가 추이·인구·세대는 덤 조회라 하나가 실패하면 그 값만 null 이고 [실패] 로 알린다.

    예: jibsa zigbang region-info 송파구
        jibsa zigbang region-info 가락동 --range 30평대
    """
    chosen_range = check_choice(price_range, PRICE_RANGES, '--range')
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_region_info(client, query, price_range=chosen_range)
        emit(result, pretty)


@app.command('region-trades')
def region_trades_command(
    query: RegionQueryArgument,
    trade: Annotated[str, typer.Option('--trade', help=f"{', '.join(LOCAL_TRADES)} 중 하나")] = '매매',
    period: Annotated[str, typer.Option('--period', help=f"등록 기간: {', '.join(TRADE_PERIODS)} (7일 = 웹 최근 일주일)")] = '오늘',
    sort: Annotated[
        str | None,
        typer.Option('--sort', help=f'정렬 (거래마다 다르고 첫 정렬이 기본, 빈칸 없이도 받는다). {_sort_help(SORT_SPEC_BY_TRADE)}')
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help=f'받을 실거래 수 (최대 {MAX_LIST_LIMIT}건)')] = DEFAULT_TRADE_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """동·구의 최근 실거래 (직방 웹 지역 화면 '실거래', 등록일 기준 목록이라 계약일 순이 아니다).

    직방 웹은 10건씩 넘겨 보지만 여기서는 --limit 건을 한 번에 받는다 (요청은 지역 검색과 실거래 2회). 정렬마다 웹이 보여 주는 비교가 다르지만
    같은 응답의 비교(직전 거래·직방시세·공시가격·분양가·전세가 대비)를 모두 준다. 직방은 매일 낮 12시에 그날 실거래를 반영해 그 전에는
    오늘이 비고 updated_today 가 false 다. 오늘 등록된 거래가 없으면 --period 로 기간을 넓힌다.
    구 단위 조회는 줄마다 dong 이 있다.

    예: jibsa zigbang region-trades 송파구 --period 7일 --limit 10
        jibsa zigbang region-trades 가락동 --trade 전세 --sort 가격높은순 --period 30일
    """
    chosen_trade = check_choice(trade, LOCAL_TRADES, '--trade')
    chosen_period = check_choice(period, TRADE_PERIODS, '--period')
    # 정렬 이름은 거래마다 달라 서비스가 지역 검색 전에 검사한다
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_region_trades(client, query, trade=chosen_trade, period=chosen_period, sort=sort, limit=limit)
        emit(result, pretty)


@app.command('region-ranking')
def region_ranking_command(
    query: RegionQueryArgument,
    trade: Annotated[str, typer.Option('--trade', help=f"{', '.join(LOCAL_TRADES)} 중 하나")] = '매매',
    sort: Annotated[
        str | None,
        typer.Option('--sort', help=f'순위 기준 (거래마다 다르고 첫 기준이 기본, 빈칸 없이도 받는다). {_sort_help(SORT_TYPE_BY_TRADE)}')
    ] = None,
    period: Annotated[
        str,
        typer.Option('--period', help=f"집계 기간: {', '.join(RANKING_PERIODS)}. 시세·평당가·전세가율 순위는 기간과 상관없이 시세 기준일 순위다")
    ] = '이번달',
    limit: Annotated[
        int,
        typer.Option(min=1, max=RANKING_MAX_RANKS, help=f'받을 단지 수 (최대 {RANKING_MAX_RANKS}곳. 직방 웹도 {RANKING_MAX_RANKS}위까지만 보여 준다)')
    ] = DEFAULT_RANKING_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """동·구의 단지 랭킹 (직방 웹 지역 화면 '단지랭킹'): 거래량·하락률·상승률·시세·평당가·인기·전세가율 순위.

    웹 랭킹 화면처럼 10건씩 쪽을 넘겨 받아(요청은 지역 검색 1회와 ceil(--limit / 10) 쪽) 앞 --limit 곳을 준다. 서버는 200위까지 주지만
    웹이 100위까지만 보여 줘 101위부터는 받지 않는다. 같은 순위가 여럿일 수 있다 (1·1·1·4). 정렬마다 줄에 오는 값이 다르다:
    거래량(trade_count), 하락·상승률(price_manwon·prev_trade_diff_manwon·prev_trade_diff_percent), 시세(estimated_price_manwon), 평당가
    (estimated_price_per_pyeong_manwon), 인기(view_count), 전세가율(jeonse_ratio_percent·gap_manwon). 구 단위 조회는 줄마다 dong 이 있다.

    예: jibsa zigbang region-ranking 송파구
        jibsa zigbang region-ranking 송파구 --sort 하락률높은순 --period 지난달
        jibsa zigbang region-ranking 가락동 --trade 전세 --sort 전세가율높은순 --limit 20
    """
    chosen_trade = check_choice(trade, LOCAL_TRADES, '--trade')
    chosen_period = check_choice(period, RANKING_PERIODS, '--period')
    # 순위 기준 이름은 거래마다 달라 서비스가 지역 검색 전에 검사한다
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_region_ranking(client, query, trade=chosen_trade, sort=sort, period=chosen_period, limit=limit)
        emit(result, pretty)


@app.command('listing')
def listing_command(
    item_id: Annotated[
        str,
        typer.Argument(help="직방 매물 ID. 검색 결과의 id 그대로 (search 는 숫자, store 는 'store-123', stay 는 'stay-123', 아파트 제휴 매물은 'coalition-123')")
    ],
    check_in: Annotated[
        str | None,
        typer.Option(help='단기임대(stay-…)만: 입주일 (YYYY-MM-DD). --check-out 과 함께 주면 그 기간에 예약할 수 있는지(available)를 붙인다')
    ] = None,
    check_out: Annotated[str | None, typer.Option(help='단기임대(stay-…)만: 마지막으로 머무는 날 (YYYY-MM-DD). 직방은 이 날까지 이용일로 센다 (1주 = 11-02~11-08). --check-in 과 함께')] = None,
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (옵션·관리비·입주일·주차). 사진·상세 설명·문의는 url 의 원 사이트에서.

    단기임대는 --check-in/--check-out 을 주면 그 기간에 예약할 수 있는지(available)도 준다 (직방 웹 달력이 막는 날짜 기준).

    예: jibsa zigbang listing stay-3783 --check-in 2026-11-02 --check-out 2026-11-29
    """
    # ID 형식과 단기임대 날짜는 서비스(`get_any_listing`)가 요청 전에 검사해 INVALID_ARGUMENT 로 낸다 (클라이언트는 첫 요청 때
    # 브라우저를 띄우므로 with 안에서 검사해도 비용이 없다)
    if (check_in is None) != (check_out is None):
        raise typer.BadParameter('--check-in 과 --check-out 은 함께 주세요', param_hint='--check-in')
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_any_listing(client, item_id, check_in=check_in, check_out=check_out)
        emit(result, pretty)


@app.command('catalog')
def catalog_command(
    catalog_id: Annotated[
        str,
        typer.Argument(help='아파트 매물 묶음 ID. search listings apt·search listings --complex <apt-…> 결과의 catalog_id 그대로 (예: 8260358-trade)')
    ],
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """같은 호를 여러 중개사가 올린 아파트 매물 묶음(직방 웹 묶음 화면)의 매물 전부. 매물마다 가격·관리비·입주일 등 listing 상세와 같은 필드.

    검색 결과의 mixed_prices 가 true 면 가격이 묶음 최저가라, 매물별 가격을 이 명령 한 번으로 본다 (매물은 20건마다 요청 1회,
    다 받은 뒤 호 정보 요청 1회를 더 해 호의 직방시세·공시가격·분양가를 붙인다. 호 정보를 못 받으면 그 값만 null 이고 [실패] 로 알린다).

    예: jibsa zigbang catalog 8260358-trade --fields id,price_manwon,floor,move_in
    """
    # 묶음 ID 형식은 서비스(`parse_catalog_id`)가 요청 전에 검사해 INVALID_ARGUMENT 로 낸다
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_catalog(client, catalog_id.strip())
        emit(result, pretty, fields=fields)
