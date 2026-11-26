from datetime import (
    date,
    datetime,
)
from functools import partial

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
from jibsa.core.errors import JibsaError
from jibsa.core.geo import DEFAULT_RADIUS_KM
from jibsa.core.korean import full_legal_division_code
from jibsa.core.listing import (
    KST,
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    REGION_INFO_PAGE_LIMIT,
    UNBOUNDED_MAX,
)
from jibsa.providers.dabang.service.common.functions import (
    COMPLEX_ID_PATTERN,
    COMPLEX_KINDS,
    CONDITIONS_BY_KIND,
    DEFAULT_LIST_LIMIT,
    EDUCATION_LEVELS,
    FLOOR_FILTER_BY_LABEL,
    LISTING_ID_PATTERN,
    LISTING_NUMBER_PATTERN,
    MAX_LIST_LIMIT,
    POPULAR_BUILDING_BY_LABEL,
    REGION_INFO_DEFAULT_LIMIT,
    REGION_INFO_MAX_LIMIT,
    ROOM_LABELS_BY_KIND,
    TRADE_TYPES_BY_KIND,
    VILLA_LABEL,
    ListingKind,
)
from jibsa.providers.dabang.service.common.models import (
    DabangListingConditions,
    DabangPlace,
)
from jibsa.providers.dabang.service.complex.functions import (
    COMPLEX_SORT_BY_LABEL,
    get_complex,
    list_complex_listings,
    search_complexes,
)
from jibsa.providers.dabang.service.complex.models import DEFAULT_COMPLEX_SORT
from jibsa.providers.dabang.service.listing.functions import (
    attach_details,
    get_listing,
    search_listings,
)
from jibsa.providers.dabang.service.listing.models import DabangListPosition
from jibsa.providers.dabang.service.nearby.functions import (
    NEARBY_EXTRAS,
    NearbyExtra,
    get_nearby,
    get_station_prices,
)
from jibsa.providers.dabang.service.neighborhood.functions import (
    HOT_PLACE_TYPE_BY_LABEL,
    NEIGHBORHOOD_TOPICS,
    POPULAR_MAX_LIMIT,
    POPULAR_PRICE_BY_TRADE,
    RANK_TOPICS,
    RANK_TYPES_BY_TOPIC,
    get_hot_places,
    get_neighborhood,
    get_popular_listings,
)
from jibsa.providers.dabang.service.ranking.functions import (
    METRIC_BY_LABEL,
    RANKING_TRADE_BY_LABEL,
    REGION_RANKING_MAX_LIMIT,
    ROOM_RANKING_METRIC_BY_LABEL,
    TRADE_PERIOD_BY_LABEL,
    WATCH_PERIOD_BY_LABEL,
    InfoMetricSpec,
    check_scope_name,
    get_region_ranking,
    get_trade_rankings,
    get_watch_rankings,
    is_room_ranking,
    takes_dong_scope,
)
from jibsa.providers.dabang.service.real_price.functions import (
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_MAX_YEARS,
    SEARCH_TYPE_BY_TRADE,
    get_listing_real_prices,
    get_nearby_complexes,
    get_price_trend,
    get_real_prices,
)
from jibsa.providers.dabang.service.real_price.models import RealPriceTrade
from jibsa.providers.dabang.service.region.functions import (
    find_scope,
    is_national_or_state,
    resolve_dong,
    resolve_places,
    resolve_scope,
    search_locations,
)
from jibsa.providers.dabang.service.sale.functions import (
    SALE_BUILDING_TYPE_BY_LABEL,
    SALE_SCHEDULE_MAX_LIMIT,
    SALE_STATE_BY_LABEL,
    SALE_SUPPLY_BY_LABEL,
    get_sale,
    get_sale_schedule,
    search_sales,
)
from jibsa.providers.dabang.service.school.functions import (
    SCHOOL_CODE_PATTERN,
    establishment_labels,
    get_school,
    search_schools,
)

from typing import (
    Annotated,
    Literal,
)


SOURCE: str = 'dabang'
MIN_RADIUS_KM: float = 0.1
MAX_RADIUS_KM: float = 5.0
# search locations 의 --limit 최대값. 다방 장소 검색이 종류마다 50곳까지 준다
LOCATIONS_MAX_LIMIT: int = 50
# 방 크기 조건(pyeongRange)의 기준 면적. 다방 웹 필터 이름표를 따른다 (room-size-type-chunk, 2026-11-13). 목록의 area_m2 는 전용이고
# 아파트는 supply_area_m2 가 공급이다. 오피스텔 강남역 --area-pyeong-min 17 은 23건 모두 전용 17평 미만이었다 (같은 날 실측)
AREA_BASIS_BY_KIND: dict[ListingKind, str] = {
    'room': "다방 '매물유형별 기준면적' 으로 걸어 결과 area_m2(전용)와 기준이 다를 수 있다",
    'villa': '전용면적 기준',
    'officetel': '계약면적 기준. 결과 area_m2 는 전용이라 더 작게 나온다',
    'apt': '공급면적 기준 (결과 supply_area_m2)',
}
REAL_PRICE_TRADES: tuple[RealPriceTrade, ...] = tuple(SEARCH_TYPE_BY_TRADE)
# 다른 소스 표현을 옮겨 쓴 사용법 오류의 힌트 (UsageHints). 이 명령에 없는 조건은 없다고 알린다
LISTING_HINTS: UsageHints = UsageHints(
    by_value={
        '주차가능': '--condition 주차',
        '엘리베이터': '--condition 엘리베이터',
        '단기': '--condition 단기임대',
        '분리형원룸': '--condition 분리형',
        '복층형원룸': '--condition 복층',
        '오픈형원룸': '--room 원룸',
        '옥탑방': '--floor 옥탑',
        '지상': '--floor 1층,2층이상',
        '2개': '--room 투룸',
        '3개': '--room 쓰리룸',
        '4개이상': '--room 포룸이상',
        '단기임대': '--condition 단기임대 (다방 단기임대는 월세 매물에 붙는 표시다)',
        '반려동물': '다방에는 반려동물 조건이 없습니다. 반려동물은 jibsa zigbang search listings room --condition 반려동물 로 찾으세요',
        '반려동물가능': '다방에는 반려동물 조건이 없습니다. 반려동물은 jibsa zigbang search listings room --condition 반려동물 로 찾으세요',
        '전세대출': '다방에는 전세대출 조건이 없습니다. 융자는 listing 상세의 loan 으로 봅니다',
    },
    by_option={
        '--type': '다방은 매물 유형을 하위 명령으로 고릅니다: search listings room·villa·officetel·apt',
        '-t': '다방은 매물 유형을 하위 명령으로 고릅니다: search listings room·villa·officetel·apt',
        '--area-min': '다방은 방 크기를 평으로만 거릅니다: --area-pyeong-min (1평 = 3.3058㎡)',
        '--area-max': '다방은 방 크기를 평으로만 거릅니다: --area-pyeong-max (1평 = 3.3058㎡)',
        '--manage-cost-max': '다방은 관리비를 따로 거르지 않습니다. 월세+관리비 상한은 --rent-max 와 --rent-includes-manage-cost',
        '--manage-cost-min': '다방은 관리비를 따로 거르지 않습니다',
        '--no-manage-cost': '다방은 관리비를 따로 거르지 않습니다',
        '--option': '다방은 가전·가구 옵션으로 거르지 않습니다. 시설은 --condition 주차,엘리베이터',
        '--facility': '--condition 주차,엘리베이터',
        '--bathroom': '다방에는 욕실 수 조건이 없습니다',
        '--details': '다방 --details 는 search listings room·villa·officetel·apt 뒤에 줍니다. 단지 매물 상세는 jibsa dabang listing <id> 로 봅니다',
        '--sort': (
            '다방 동·역·대학 매물 목록은 다방 목록 순으로만 줍니다 (다방 웹에도 정렬이 없습니다). 단지 매물은 '
            'search listings --complex <단지 ID> --sort 로 정렬합니다'
        ),
        '--parking-min': '세대당 주차 대수(--parking-min)는 search listings officetel·apt 에서 1 이상의 정수로 줍니다. 주차 가능 여부는 --condition 주차',
        '--room-count': '--room 투룸',
        '--structure': '--condition 분리형 이나 --condition 복층',
        '--move-in': '다방에는 입주일 조건이 없습니다',
        '--move-in-now': '다방에는 입주일 조건이 없습니다',
        '--city': "같은 이름의 동이 여럿이면 구 이름을 붙이세요 (예: '강남구 신사동')",
    },
)
USAGE_HINTS: dict[str, UsageHints] = {
    'jibsa dabang search listings room': LISTING_HINTS,
    'jibsa dabang search listings villa': LISTING_HINTS,
    'jibsa dabang search listings officetel': LISTING_HINTS,
    'jibsa dabang search listings apt': LISTING_HINTS,
    'jibsa dabang search listings': LISTING_HINTS,
}

app = typer.Typer(
    help=(
        '다방: 매물 찾기(search listings room·villa·officetel·apt), 장소·단지(search locations, search complexes, complex, '
        'search listings --complex), 상세(listing), 실거래·시세(real-price, price-trend, nearby-complexes), 동네·주변(neighborhood, '
        'popular-listings, hot-places, nearby, station-prices), 학교·유치원·어린이집(search schools, school), 분양(search sales, sale, '
        'sale-schedule), 순위(trending-complexes, trade-rankings, region-ranking) '
        '(로그인 불필요, 금액은 만원 단위)'
    ),
    no_args_is_help=True,
)
search_app = typer.Typer(
    help='다방 장소 후보(locations), 매물 찾기(listings room·villa·officetel·apt), 단지 목록(complexes), 분양(sales), 동 안 학교 목록(schools)',
    no_args_is_help=True,
)

listings_app = typer.Typer(
    help='매물 유형별 검색(room 원룸·투룸, villa 주택·빌라, officetel, apt) 또는 --complex 로 단지 매물',
    invoke_without_command=True,
)

QueryArgument = Annotated[
    str | None,
    typer.Argument(help="동·역·대학 이름 (예: 역삼동, '강남구 신사동', 강남역, 홍익대학교). --lat/--lng 를 주면 생략")
]
LatOption = Annotated[float | None, typer.Option(help='중심 위도 (이름 대신)')]
LngOption = Annotated[float | None, typer.Option(help='중심 경도 (이름 대신)')]

LimitOption = Annotated[
    int, typer.Option(min=1, max=MAX_LIST_LIMIT, help=f'받을 매물 수 (제외 전, 다방은 24건씩 준다, 최대 {MAX_LIST_LIMIT})'),
]
RegionInfoLimitOption = Annotated[
    int, typer.Option(min=1, max=REGION_INFO_MAX_LIMIT, help=f'받을 수 (다방은 {REGION_INFO_PAGE_LIMIT}곳씩 준다. 그만큼마다 요청 1회)'),
]
PrimaryPyeongOption = Annotated[
    int | None, typer.Option('--pyeong', min=1, help='평형 번호 (complex 결과의 pyeongs[].pyeong_id). 기본 다방 대표 평형'),
]
RentIncludesManageOption = Annotated[
    bool, typer.Option('--rent-includes-manage-cost', help='--rent-min/--rent-max 를 월세 + 관리비로 본다 (다방 필터)'),
]
DetailsOption = Annotated[
    bool,
    typer.Option(
        '--details',
        help='매물마다 상세를 1회씩 더 받아 사용승인일(approved_date)과 건물 용도(residence_type)를 붙인다. 요청이 매물 수만큼 늘어난다 (앞 30건)',
    ),
]
BuiltWithinOption = Annotated[
    int | None,
    typer.Option(min=0, help='사용승인 뒤 이 햇수 이내 건물만 (년). 다방은 연도로 세어 10 이면 10년 전 해의 1월 1일 이후 승인'),
]
FloorOption = Annotated[
    list[str] | None,
    typer.Option('--floor', help=f"층: {', '.join(FLOOR_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분 (OR). 기본 전체"),
]
ParkingMinOption = Annotated[
    int | None,
    typer.Option(
        '--parking-min',
        min=1,
        help=(
            "단지 세대당 주차 대수 하한 (대, 정수). 다방 웹 주차 필터의 '세대당 1대 이상'·'2대 이상'. "
            '이 매물에 주차할 수 있는지와는 다른 조건이다'
        ),
    ),
]

SALE_ID_HELP: str = '분양 ID (search sales·search locations 결과의 presale_id, 28자리)'

# --ranks 도움말: 주제마다 종류 수 ('학교 5·편의 5·교통 4·안전 3'), 고른 주제를 모두 받을 때의 요청 수. 종류마다 요청 1회다
RANK_TYPE_COUNTS: str = '·'.join(f'{topic} {len(types)}' for topic, types in RANK_TYPES_BY_TOPIC.items())
RANK_ALL_REQUESTS: int = sum(len(types) for types in RANK_TYPES_BY_TOPIC.values())

WATCH_UNITS: tuple[str, ...] = ('단지', '동')
RANKING_UNITS: tuple[str, ...] = ('동', '단지')
RANKING_ORDERS: tuple[str, ...] = ('높은순', '낮은순')
TRADE_RANKING_TRADES: tuple[str, ...] = ('매매', '전세')

REAL_ESTATE_METRICS: tuple[str, ...] = tuple(label for label, spec in METRIC_BY_LABEL.items() if not isinstance(spec, InfoMetricSpec))
INFO_METRICS: tuple[str, ...] = tuple(label for label, spec in METRIC_BY_LABEL.items() if isinstance(spec, InfoMetricSpec))


app.add_typer(search_app, name='search')


search_app.add_typer(listings_app, name='listings')


def _radius_option(help: str) -> object:
    """반경 옵션 (km). 범위는 명령마다 같고 도움말만 다르다 (매물·단지·분양 검색)."""
    return typer.Option('--radius', min=MIN_RADIUS_KM, max=MAX_RADIUS_KM, help=help)


RadiusOption = Annotated[
    float | None,
    _radius_option(
        f'반경 (km). 주면 이름의 중심에서 반경을 덮는 사각형으로 받고 반경 밖은 뺀다. 없으면 동은 그 동 안, 역은 다방이 정한 '
        f'역 반경, 대학은 대학 둘레, 좌표는 {DEFAULT_RADIUS_KM:g}km'
    ),
]
ComplexRadiusOption = Annotated[
    float | None,
    _radius_option(
        f'반경 (km). 주면 이름의 중심에서 반경을 덮는 사각형으로 받는다 (단지 목록은 사각형 모서리의 반경 밖 단지도 빼지 않는다). '
        f'없으면 동은 그 동 안, 역은 다방이 정한 역 반경, 대학은 대학 둘레(아파트는 {DEFAULT_RADIUS_KM:g}km 사각형), '
        f'좌표는 {DEFAULT_RADIUS_KM:g}km 사각형'
    ),
]


def _room_option(kind: ListingKind) -> object:
    return typer.Option('--room', help=f"방 개수: {', '.join(ROOM_LABELS_BY_KIND[kind])}. 반복하거나 쉼표로 구분 (OR). 기본 전체")


def _area_option(kind: ListingKind, bound: str) -> object:
    return typer.Option(min=0, help=f'방 크기 {bound} (평, 정수). {AREA_BASIS_BY_KIND[kind]}')


def _condition_option(kind: ListingKind) -> object:
    labels = CONDITIONS_BY_KIND[kind]
    # '세안고' 는 다방 웹 필터 이름 그대로라 뜻을 붙인다
    meaning = ' (세안고: 세입자가 있는 채로 파는 매매 매물)' if '세안고' in labels else ''
    return typer.Option('--condition', help=f"기타 조건: {', '.join(labels)}{meaning}. 반복하거나 쉼표로 구분 (AND)")


def _trade_option(kind: ListingKind) -> object:
    return typer.Option('--trade', help=f"거래 유형: {', '.join(TRADE_TYPES_BY_KIND[kind])}. 반복하거나 쉼표로 구분. 기본 전체")


def _require_center(query: str | None, lat: float | None, lng: float | None) -> None:
    require_korea(lat, lng)
    if query is None and (lat is None or lng is None):
        raise typer.BadParameter('동·역·대학 이름 또는 --lat/--lng 를 주세요', param_hint='QUERY')


def _validate_ranges(*ranges: tuple[str, int | None, int | None]) -> None:
    """`validate_ranges` 에 더해 다방이 받지 않는 큰 하한을 조회 전에 막는다.

    다방은 범위 값을 999999 까지만 받는다 (넘으면 400 '최소값은 999999 이하로 입력해주세요', 2026-10-25 실측). 큰 상한은
    `range_of` 가 999999 로 줄여 보낸다.
    """
    validate_ranges(*ranges)
    for name, low, _ in ranges:
        if low is not None and low > UNBOUNDED_MAX:
            raise typer.BadParameter(
                f'다방은 {UNBOUNDED_MAX} 보다 큰 하한을 받지 않습니다 (금액은 만원이라 약 100억): {low}', param_hint=f'--{name}-min',
            )


def _place(client: DabangClient, query: str | None, lat: float | None, lng: float | None) -> DabangPlace:
    if lat is not None and lng is not None:
        return DabangPlace(kind='point', name=query or f'{lat},{lng}', lat=lat, lng=lng)
    return resolve_places(client, query or '')


def _search(
    kind: ListingKind,
    *,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float | None,
    trade: list[str] | None,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
    rent_includes_manage_cost: bool,
    area_pyeong_min: int | None,
    area_pyeong_max: int | None,
    built_within: int | None,
    floor: list[str] | None,
    room: list[str] | None,
    condition: list[str] | None,
    households_min: int | None,
    households_max: int | None,
    parking_per_household_min: int | None,
    limit: int,
    next_: str | None,
    details: bool,
    fields: list[str] | None,
    pretty: bool | None,
) -> None:
    """네 유형 매물 검색이 같이 쓰는 처리. 유형에 없는 옵션은 명령이 열지 않아 None 으로 온다."""
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    position = decode_next(next_)
    _validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
        ('area-pyeong', area_pyeong_min, area_pyeong_max),
        ('households', households_min, households_max),
        ('parking', parking_per_household_min, None),
    )
    given_trades = split_csv(trade, TRADE_TYPES_BY_KIND[kind], '--trade', LISTING_HINTS)
    conditions_ = split_csv(condition, CONDITIONS_BY_KIND[kind], '--condition', LISTING_HINTS)
    if conditions_ and '단기임대' in conditions_ and '세안고' in conditions_:
        # 세안고는 매매, 단기임대는 월세 매물 조건이라 함께 맞는 매물이 없다. 단기임대가 거래를 월세로 좁힌 뒤 아래 세안고 검사에
        # 맡기면 --trade 매매 를 이미 줬어도 매매를 넣으라고 안내한다 (2026-11-13 리뷰)
        raise typer.BadParameter(
            '--condition 세안고(매매 매물 조건)와 단기임대(월세 매물 조건)는 함께 쓸 수 없습니다. 둘 중 하나만 주세요',
            param_hint='--condition',
        )
    short_lease_notes: list[str] = []
    if conditions_ and '단기임대' in conditions_:
        # 다방 단기임대는 월세 매물에 붙는 표시라 서버가 이 조건을 월세에만 건다. 거래 유형을 주지 않으면 전세가 그대로 섞여
        # 왔다 (2026-11-11 LLM 사용 시험·실측: 정자동 room --condition 단기임대 10건 중 전세 7건). 거르는 것은 서버라 월세만
        # 묻고 알린다. 월세로 정한 뒤 가격 조건을 견주므로 매매가 조건과 함께 주면 infer_trade_types 가 입력 오류로 막는다
        if given_trades and '월세' not in given_trades:
            raise typer.BadParameter(
                f"--trade {','.join(given_trades)} 에는 단기임대 매물이 없습니다. "
                '다방 단기임대는 월세 매물에 붙는 표시라 --trade 월세 와 함께 쓰세요',
                param_hint='--condition',
            )
        if not given_trades and (price_min is not None or price_max is not None):
            # 월세로 정한 뒤 infer_trade_types 에 맡기면 주지 않은 '--trade 월세 에는 해당 금액이 없어' 로 막혀 까닭을 알 수 없다
            raise typer.BadParameter(
                '다방 단기임대는 월세 매물이라 매매가 조건(--price-min/--price-max)과 함께 쓸 수 없습니다',
                param_hint='--condition',
            )
        if given_trades != ['월세']:
            given_trades = ['월세']
            short_lease_notes.append(note(
                '거래', '--condition 단기임대 는 다방이 월세 매물에만 걸어 월세만 검색했습니다 (전세·매매는 단기임대로 거를 수 없습니다)',
            ))
    trade_types, trade_notes = infer_trade_types(
        given_trades,
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
        allowed=TRADE_TYPES_BY_KIND[kind],
    )
    trade_notes = short_lease_notes + trade_notes
    if conditions_ and '세안고' in conditions_ and trade_types and '매매' not in trade_types:
        # 세안고(세입자가 있는 채로 파는 매물)는 매매 조건이다. 다방 웹도 거래 유형에 매매가 있을 때만 이 필터를 보여 주고 매매를
        # 빼면 끈다 (filter 청크 2026-11-13). 매매 없이 보내면 웹에 없는 조합이 된다
        raise typer.BadParameter(
            f"--condition 세안고 는 매매 매물 조건인데 검색할 거래 유형({','.join(trade_types)})에 매매가 없습니다. "
            '다방 웹도 거래 유형에 매매가 있을 때만 세안고를 보여 줍니다. --trade 에 매매를 넣으세요',
            param_hint='--condition',
        )
    floors = split_csv(floor, tuple(FLOOR_FILTER_BY_LABEL), '--floor', LISTING_HINTS)
    rooms = split_csv(room, ROOM_LABELS_BY_KIND[kind], '--room', LISTING_HINTS)
    with handle_errors(SOURCE), DabangClient() as client:
        conditions = DabangListingConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            rent_includes_manage_cost=rent_includes_manage_cost,
            area_pyeong_min=area_pyeong_min,
            area_pyeong_max=area_pyeong_max,
            built_within_years=built_within,
            floors=floors,
            rooms=rooms,
            conditions=conditions_,
            households_min=households_min,
            households_max=households_max,
            parking_per_household_min=parking_per_household_min,
        )
        if position is not None and 'place' in position:
            # 이어 받기는 첫 결과가 찾은 위치를 그대로 쓴다. 장소 검색을 다시 묻지 않고, 그사이 다방 검색 순서가 바뀌어도
            # 같은 동·역에서 이어 받는다
            place = DabangPlace.model_validate(position['place'])
        else:
            place = _place(client, query, lat, lng)
        resume = DabangListPosition.model_validate(position['list']) if position is not None and 'list' in position else None
        result = search_listings(
            client, kind, place, conditions=conditions, limit=limit, radius_km=radius, resume=resume,
        )
        next_position = None
        if result.next_position is not None:
            next_position = {'list': result.next_position.model_dump(mode='json'), 'place': {
                # 이어 받기 표에 남길 위치. 출력하지 않는 다방 번호(동 코드·동 번호·역 번호)도 넣어야 장소 검색 없이 이어 받는다
                **place.model_dump(), 'code': place.code, 'gid': place.gid, 'place_id': place.place_id, 'radius_m': place.radius_m,
            }}
        if details:
            result = attach_details(client, result, built_within_years=built_within)
        emit(result, pretty, notes=trade_notes, next_token=encode_next(next_position), fields=fields)


@search_app.command('locations')
def locations_command(
    query: Annotated[str, typer.Argument(help='동·역·대학·단지 이름 (예: 역삼동, 강남역, 홍익대학교, 은마)')],
    limit: Annotated[
        int, typer.Option(min=1, max=LOCATIONS_MAX_LIMIT, help=f'종류마다 최대 후보 수 (다방은 종류마다 {LOCATIONS_MAX_LIMIT}곳까지 준다)'),
    ] = 10,
    pretty: PrettyOption = None,
) -> None:
    """이름으로 다방의 동·역·대학·단지·분양 후보를 찾는다 (요청 1회). 후보는 다방 순서 그대로다.

    complexes[].complex_id 를 jibsa dabang complex·search listings --complex·real-price 에, presales[].presale_id 를 sale 에 넘긴다.

    예: jibsa dabang search locations 강남역
        jibsa dabang search locations 은마
    """
    with handle_errors(SOURCE), DabangClient() as client:
        result = search_locations(client, query, ['REGION', 'SUBWAY', 'UNIV', 'COMPLEX', 'SALE_IN_LOTS'])
        # 다방 웹은 받은 후보를 모두 보여 준다. 종류마다 앞 --limit 곳만 주므로 자른 종류가 있으면 알린다
        counts = {
            '동': len(result.region_list),
            '역': len(result.subway_list),
            '대학': len(result.univ_list),
            '단지': len(result.complex_list),
            '분양': len(result.sale_in_lots_list),
        }
        cut = [f'{label} {count}곳 중 {limit}곳' for label, count in counts.items() if count > limit]
        notes = [note(
            '일부', f"종류마다 다방 순서로 앞 {limit}곳만 보여 줍니다 ({', '.join(cut)}). 더 보려면 --limit 을 늘리세요 (최대 {LOCATIONS_MAX_LIMIT})",
        )] if cut else []
        emit(
            {
                'query': query,
                'regions': [
                    {
                        'name': region.name,
                        'address': normalize_address(region.full_name),
                        'legal_division_code': full_legal_division_code(region.code),
                        'lat': region.location.lat if region.location else None,
                        'lng': region.location.lng if region.location else None,
                    }
                    for region in result.region_list[:limit]
                ],
                'stations': [
                    {
                        'name': station.name,
                        'lines': [line.full_name for line in station.line_list if line.full_name],
                        'radius_m': station.radius,
                        'lat': station.location.lat if station.location else None,
                        'lng': station.location.lng if station.location else None,
                    }
                    for station in result.subway_list[:limit]
                ],
                'universities': [
                    {
                        'name': univ.name,
                        'lat': univ.location.lat if univ.location else None,
                        'lng': univ.location.lng if univ.location else None,
                    }
                    for univ in result.univ_list[:limit]
                ],
                'complexes': [
                    {
                        'complex_id': complex_.id,
                        'name': complex_.name,
                        'complex_type': complex_.format_type,
                        'address': normalize_address(complex_.address),
                    }
                    for complex_ in result.complex_list[:limit]
                ],
                'presales': [
                    {'presale_id': sale.id, 'name': sale.name, 'status': sale.format_state, 'address': normalize_address(sale.address)}
                    for sale in result.sale_in_lots_list[:limit]
                ],
            },
            pretty,
            notes=notes,
        )


@listings_app.command('room')
def room_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: RadiusOption = None,
    trade: Annotated[list[str] | None, _trade_option('room')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    rent_includes_manage_cost: RentIncludesManageOption = False,
    area_pyeong_min: Annotated[int | None, _area_option('room', '하한')] = None,
    area_pyeong_max: Annotated[int | None, _area_option('room', '상한')] = None,
    built_within: BuiltWithinOption = None,
    floor: FloorOption = None,
    room: Annotated[list[str] | None, _room_option('room')] = None,
    condition: Annotated[list[str] | None, _condition_option('room')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    details: DetailsOption = False,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """원룸·투룸 (다방 '원룸·투룸' 목록). 원룸은 방 하나짜리라 원룸형 오피스텔도 나온다. 매매는 없다.

    다방 목록 순으로 준다 (거리순이 아니다). 단기임대를 받는 월세 매물은 short_term: true 다.

    예: jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
        jibsa dabang search listings room 강남역 --room 투룸 --condition 주차,엘리베이터
        jibsa dabang search listings room 역삼동 --trade 월세 --next <앞 결과의 next>
    """
    _search(
        'room', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=None, price_max=None, rent_includes_manage_cost=rent_includes_manage_cost,
        area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max, built_within=built_within, floor=floor, room=room,
        condition=condition, households_min=None, households_max=None, parking_per_household_min=None, limit=limit, next_=next_,
        details=details, fields=fields, pretty=pretty,
    )


@listings_app.command('villa')
def villa_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: RadiusOption = None,
    trade: Annotated[list[str] | None, _trade_option('villa')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    rent_includes_manage_cost: RentIncludesManageOption = False,
    area_pyeong_min: Annotated[int | None, _area_option('villa', '하한')] = None,
    area_pyeong_max: Annotated[int | None, _area_option('villa', '상한')] = None,
    built_within: BuiltWithinOption = None,
    floor: FloorOption = None,
    room: Annotated[list[str] | None, _room_option('villa')] = None,
    condition: Annotated[list[str] | None, _condition_option('villa')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    details: DetailsOption = False,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """주택·빌라 (다방 '주택·빌라' 목록). 방 하나짜리 빌라도 나온다 (property_type '빌라').

    예: jibsa dabang search listings villa 성수동1가 --trade 전세 --deposit-max 30000 --room 투룸,쓰리룸
    """
    _search(
        'villa', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=floor, room=room, condition=condition, households_min=None, households_max=None,
        parking_per_household_min=None, limit=limit, next_=next_, details=details, fields=fields, pretty=pretty,
    )


@listings_app.command('officetel')
def officetel_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: RadiusOption = None,
    trade: Annotated[list[str] | None, _trade_option('officetel')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    rent_includes_manage_cost: RentIncludesManageOption = False,
    area_pyeong_min: Annotated[int | None, _area_option('officetel', '하한')] = None,
    area_pyeong_max: Annotated[int | None, _area_option('officetel', '상한')] = None,
    built_within: BuiltWithinOption = None,
    room: Annotated[list[str] | None, _room_option('officetel')] = None,
    condition: Annotated[list[str] | None, _condition_option('officetel')] = None,
    parking_per_household_min: ParkingMinOption = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    details: DetailsOption = False,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """오피스텔 (다방 '오피스텔' 목록). 층 조건은 없다.

    예: jibsa dabang search listings officetel 강남역 --trade 월세 --rent-max 100 --condition 주차
        jibsa dabang search listings officetel 강남역 --parking-min 1
    """
    _search(
        'officetel', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min,
        deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=None, room=room, condition=condition, households_min=None, households_max=None,
        parking_per_household_min=parking_per_household_min, limit=limit, next_=next_, details=details, fields=fields,
        pretty=pretty,
    )


@listings_app.command('apt')
def apt_command(
    query: QueryArgument = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: RadiusOption = None,
    trade: Annotated[list[str] | None, _trade_option('apt')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    rent_includes_manage_cost: RentIncludesManageOption = False,
    area_pyeong_min: Annotated[int | None, _area_option('apt', '하한')] = None,
    area_pyeong_max: Annotated[int | None, _area_option('apt', '상한')] = None,
    built_within: BuiltWithinOption = None,
    room: Annotated[list[str] | None, _room_option('apt')] = None,
    condition: Annotated[list[str] | None, _condition_option('apt')] = None,
    households_min: Annotated[int | None, typer.Option(min=0, help='단지 세대수 하한')] = None,
    households_max: Annotated[int | None, typer.Option(min=0, help='단지 세대수 상한')] = None,
    parking_per_household_min: ParkingMinOption = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    details: DetailsOption = False,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """아파트 (다방 '아파트' 목록, 주상복합·도시형 포함). 다방이 동 검색을 주지 않아 동 이름은 동 경계를 덮는 사각형으로 받아
    그 동 매물만 남긴다 (다른 동 매물만큼 returned 가 줄 수 있다).

    예: jibsa dabang search listings apt 대치동 --trade 매매 --price-max 300000
        jibsa dabang search listings apt 강남역 --trade 전세 --households-min 500
        jibsa dabang search listings apt 강남역 --trade 매매 --condition 세안고
    """
    _search(
        'apt', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=None, room=room, condition=condition, households_min=households_min,
        households_max=households_max, parking_per_household_min=parking_per_household_min, limit=limit, next_=next_,
        details=details, fields=fields, pretty=pretty,
    )


def _require_complex_id(complex_id: str, param_hint: str = 'COMPLEX_ID') -> str:
    value = complex_id.strip()
    if COMPLEX_ID_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(
            f"다방 단지 ID 형식이 아닙니다: '{complex_id}'. jibsa dabang search locations <단지 이름> 결과의 complex_id "
            '(28자리, 예: 58291f830ff9bd73a07ca123c632)를 그대로 주세요',
            param_hint=param_hint,
        )
    return value


def _require_sale_id(sale_id: str, param_hint: str = 'SALE_ID') -> str:
    value = sale_id.strip()
    # 분양 ID 는 단지 ID 와 같은 28자리다
    if COMPLEX_ID_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(f"다방 분양 ID(28자리)가 아닙니다: '{sale_id}'", param_hint=param_hint)
    return value


@listings_app.callback()
def complex_listings_command(
    ctx: typer.Context,
    complex_id: Annotated[str | None, typer.Option('--complex', help='아파트·오피스텔 단지 ID (28자리)')] = None,
    pyeong: Annotated[
        list[str] | None,
        typer.Option('--pyeong', metavar='<int>', help='평형 번호 (complex 결과의 pyeongs[].pyeong_id). 반복하거나 쉼표로 구분 (OR). 기본 전체'),
    ] = None,
    trade: Annotated[list[str] | None, typer.Option('--trade', help='거래 유형: 월세, 전세, 매매. 반복하거나 쉼표로 구분. 기본 전체')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    sort: Annotated[
        list[str] | None,
        typer.Option('--sort', help=(
            f"단지 매물 순서 (다방 웹 단지 매물 정렬): {', '.join(COMPLEX_SORT_BY_LABEL)}. 기본 {DEFAULT_COMPLEX_SORT}. "
            '다방이 정렬한 순서 그대로 준다'
        )),
    ] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 하나의 매물 (기본 다방 랭킹순, --sort 로 다방 웹 정렬). 조건은 다방 서버가 거른다. 상세는 결과의 id 로
    jibsa dabang listing <id>.

    예: jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 전세
        jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 매매 --sort 낮은가격순
    """
    if ctx.invoked_subcommand is not None:
        supplied = [
            name for name in ctx.params
            if (source := ctx.get_parameter_source(name)) is not None and source.name == 'COMMANDLINE'
        ]
        if supplied:
            raise typer.BadParameter('유형별 검색 옵션은 room·villa·officetel·apt 뒤에 주세요. --complex 와 함께 쓸 수 없습니다')
        return
    if complex_id is None:
        raise typer.BadParameter('--complex 를 주거나 room·villa·officetel·apt 중 하나를 고르세요', param_hint='--complex')
    value = _require_complex_id(complex_id, '--complex')
    space_seqs = split_ints(pyeong, '--pyeong')
    chosen_sort = _one(sort, tuple(COMPLEX_SORT_BY_LABEL), '--sort', DEFAULT_COMPLEX_SORT)
    _validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
    )
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, TRADE_TYPES_BY_KIND['apt'], '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
        allowed=TRADE_TYPES_BY_KIND['apt'],
    )
    with handle_errors(SOURCE), DabangClient() as client:
        conditions = DabangListingConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
        )
        result = list_complex_listings(
            client, value, conditions=conditions, space_seqs=space_seqs, sort=chosen_sort, limit=limit,
        )
        emit(result, pretty, notes=trade_notes, fields=fields)


@search_app.command('complexes')
def complexes_command(
    query: QueryArgument = None,
    complex_type: Annotated[str, typer.Option('--type', '-t', help='단지 유형: 아파트, 오피스텔')] = '아파트',
    lat: LatOption = None,
    lng: LngOption = None,
    radius: ComplexRadiusOption = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='받을 단지 수 (제외 전, 다방은 24곳씩 준다)')] = DEFAULT_LIST_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """동·역·대학 둘레의 아파트·오피스텔 단지 목록 (다방 목록 순). 단지마다 연차·세대수·거래 유형별 매물 수·최근 실거래가.

    매물이 없는 단지도 나온다. 결과의 complex_id 를 complex·search listings --complex·real-price 에 넘긴다.

    예: jibsa dabang search complexes 대치동
        jibsa dabang search complexes 강남역 -t 오피스텔
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    chosen_type = check_choice(complex_type, COMPLEX_KINDS, '--type')
    with handle_errors(SOURCE), DabangClient() as client:
        place = _place(client, query, lat, lng)
        result = search_complexes(client, chosen_type, place, limit=limit, radius_km=radius)
        emit(result, pretty)


@app.command('listing')
def listing_command(
    listing_ref: Annotated[
        str,
        typer.Argument(help='다방 매물 ID (검색 결과의 id, 24자리) 또는 다방 화면의 매물번호 (listing_number, 숫자)'),
    ],
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (가격·관리비와 포함 항목·면적·층·방향·입주일·주차·옵션·건물 용도). 사진·설명·문의는 url 의 원 사이트에서.

    예: jibsa dabang listing 6abb32f72f9f803f9c6f3830
        jibsa dabang listing 59136486
    """
    value = listing_ref.strip()
    if LISTING_ID_PATTERN.fullmatch(value) is None and LISTING_NUMBER_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(
            f"다방 매물 ID·매물번호 형식이 아닙니다: '{listing_ref}'. 검색 결과의 id(24자리)나 listing_number 를 그대로 주세요",
            param_hint='LISTING_REF',
        )
    with handle_errors(SOURCE), DabangClient() as client:
        detail = get_listing(client, value)
        emit(detail, pretty)


@app.command('complex')
def complex_command(
    complex_id: Annotated[str, typer.Argument(help='단지 ID (search locations·search complexes 결과의 complex_id)')],
    pretty: PrettyOption = None,
) -> None:
    """단지 정보: 세대수·동 수·주차·층·용적률·건폐율·시공사·사용승인일·최근 거래 수·꼬리표, 평형(pyeongs[].pyeong_id), 평당가 비교,
    최근 실거래, 대출 비율 50% 제한 지역 여부, 학교·어린이집·유치원 (요청 3회).

    예: jibsa dabang complex 58291f830ff9bd73a07ca123c632
    """
    value = _require_complex_id(complex_id)
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_complex(client, value)
        emit(result, pretty)


@app.command('school')
def school_command(
    school_code: Annotated[
        str,
        typer.Argument(help=(
            '학교·유치원·어린이집 코드 (complex 결과 schools[].school_code·nurseries[].school_code·kindergartens[].school_code, search schools '
            '결과의 school_code. 예: S010000704)'
        )),
    ],
    level: Annotated[
        str,
        typer.Option('--level', help=(
            f"{', '.join(EDUCATION_LEVELS)} (complex 결과 schools[].level, nurseries 는 어린이집, kindergartens 는 유치원, "
            'search schools 결과의 level). 코드와 맞아야 한다'
        )),
    ],
    pretty: PrettyOption = None,
) -> None:
    """학교·유치원·어린이집 하나의 공시 (요청 1회).

    학교(학교알리미): 학급당·교원당 학생 수(시·도·시·군·구 평균과 비교), 중학교 고교 유형별 진학률, 고등학교 대학 진학률.
    유치원(유치원알리미)·어린이집(어린이집정보공개포털): 설립 유형·운영 시간·통학버스·원아 구성·교사 급수별 수·교사 1명당 아동 수·
    제공 서비스, 유치원은 홈페이지와 통학 차량 수도. 유치원 원비는 주지 않는다 (결과 url 의 공시 페이지에서 본다).
    전화·좌표는 주지 않는다 (학교는 홈페이지도).

    예: jibsa dabang school S010000704 --level 중학교
        jibsa dabang school 11650000153 --level 어린이집
    """
    value = school_code.strip()
    if SCHOOL_CODE_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(f"코드는 영문·숫자·'-' 입니다: '{school_code}'", param_hint='SCHOOL_CODE')
    chosen_level = check_choice(level, EDUCATION_LEVELS, '--level')
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_school(client, value, chosen_level), pretty)


@search_app.command('schools')
def schools_command(
    query: Annotated[str, typer.Argument(help="법정동 이름 (예: 역삼동, '강남구 신사동')")],
    level: Annotated[
        str,
        typer.Option('--level', help=f"{', '.join(EDUCATION_LEVELS)} 중 하나 (다방 동네정보 학군 목록의 탭)"),
    ],
    establishment: Annotated[
        str | None,
        typer.Option('--establishment', help=(
            '설립 구분 (다방 탭 이름 그대로). 초·중·고등학교·유치원: 국공립·사립, 어린이집: 공공·민간·가정·직장·협동. 기본 전체'
        )),
    ] = None,
    limit: RegionInfoLimitOption = REGION_INFO_DEFAULT_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """동 안 학교·유치원·어린이집 목록 (다방 동네정보 '학군' 상세 목록과 같은 목록·순서·전체 수).

    줄마다 코드·이름·설립 구분·주소, 중·고등학교는 특목고·자사고 진학률도. 결과의 school_code 와 level 을
    jibsa dabang school <school_code> --level <level> 에 그대로 넘긴다.

    예: jibsa dabang search schools 역삼동 --level 초등학교
        jibsa dabang search schools 역삼동 --level 어린이집 --establishment 공공
    """
    chosen_level = check_choice(level, EDUCATION_LEVELS, '--level')
    # 빈 값은 주지 않은 것과 같이 전체다
    given_establishment = (establishment or '').strip()
    chosen_establishment = check_choice(
        given_establishment, establishment_labels(chosen_level), '--establishment',
        context=f'--level {chosen_level} 의 설립 구분',
    ) if given_establishment else None
    with handle_errors(SOURCE), DabangClient() as client:
        result = search_schools(
            client, resolve_dong(client, query, subject='동 안 학교', elsewhere=None), chosen_level,
            establishment=chosen_establishment, limit=limit,
        )
        emit(result, pretty)


@app.command('real-price')
def real_price_command(
    complex_id: Annotated[str | None, typer.Argument(help='단지 ID. 단지 없는 매물은 빼고 --listing')] = None,
    listing: Annotated[
        str | None,
        typer.Option(
            '--listing',
            help='단지 없는 매물(빌라·주택·원룸)의 매물 ID. 다방 매물 화면처럼 이 집(같은 지번) 또는 같은 동의 같은 건물 유형 실거래를 준다',
        ),
    ] = None,
    pyeong: PrimaryPyeongOption = None,
    trade: Annotated[
        str | None,
        typer.Option('--trade', help=(
            f"{' 또는 '.join(REAL_PRICE_TRADES)} (전세·월세를 함께 준다). 기본: 단지는 매매, --listing 은 다방 매물 화면처럼 매물의 거래 유형 "
            '(매매 매물은 매매, 월세·전세 매물은 전월세)'
        )),
    ] = None,
    years: Annotated[
        int, typer.Option('--years', min=1, max=REAL_PRICE_MAX_YEARS, help=f'최근 몇 년 (1~{REAL_PRICE_MAX_YEARS}, 다방은 {REAL_PRICE_MAX_YEARS}년까지)'),
    ] = REAL_PRICE_MAX_YEARS,
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 30,
    pretty: PrettyOption = None,
) -> None:
    """실거래가 (국토부 신고 기준, 최근 계약 순). cancelled: true 는 해제된 거래.

    예: jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --trade 매매
        jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --pyeong 817 --trade 전월세 --years 1
        jibsa dabang real-price --listing 6abb32f72f9f803f9c6f3830
    """
    if (complex_id is None) == (listing is None):
        raise typer.BadParameter('단지 ID 와 --listing 중 하나만 주세요', param_hint='COMPLEX_ID')
    given_trade = check_choice(trade, REAL_PRICE_TRADES, '--trade') if trade is not None else None
    if listing is not None:
        if pyeong is not None:
            raise typer.BadParameter('--pyeong 은 단지 실거래에만 씁니다', param_hint='--pyeong')
        listing_id = listing.strip()
        if LISTING_ID_PATTERN.fullmatch(listing_id) is None:
            raise typer.BadParameter(f"다방 매물 ID(24자리)가 아닙니다: '{listing}'", param_hint='--listing')
        with handle_errors(SOURCE), DabangClient() as client:
            result = get_listing_real_prices(client, listing_id, trade=given_trade, years=years, limit=limit)
            emit(result, pretty)
        return
    value = _require_complex_id(complex_id or '')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_real_prices(client, value, space_seq=pyeong, trade=given_trade or '매매', years=years, limit=limit)
        emit(result, pretty)


@app.command('price-trend')
def price_trend_command(
    complex_id: Annotated[str, typer.Argument(help='단지 ID')],
    pyeong: PrimaryPyeongOption = None,
    pretty: PrettyOption = None,
) -> None:
    """평형 하나의 36달 시세 흐름: 달마다 매매·전세 평균 실거래가와 거래 수, 전세가율, 1년·3년 최고·최저 (요청 1회).

    예: jibsa dabang price-trend 58291f830ff9bd73a07ca123c632 --pyeong 817
    """
    value = _require_complex_id(complex_id)
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_price_trend(client, value, space_seq=pyeong)
        emit(result, pretty)


@app.command('nearby-complexes')
def nearby_complexes_command(
    complex_id: Annotated[str, typer.Argument(help='단지 ID')],
    pyeong: PrimaryPyeongOption = None,
    pretty: PrettyOption = None,
) -> None:
    """평형대 평당가 비교 (다방 단지 화면 평당가 칸의 기본 탭 'N평대 비교', 요청 1회. --pyeong 이 없으면 +1).

    그 평형이 든 평형대(예: 30평대)의 이 단지·동·구 매매·전세 평당가와, 반경 1km 주변 단지의 매매·전세 평당가·세대수·연차·거리를
    다방 순서 그대로 준다. 단지 전체 평형의 비교('전체 평형 비교' 탭)는 complex 결과의 area_prices 다.

    예: jibsa dabang nearby-complexes 58291f830ff9bd73a07ca123c632
        jibsa dabang nearby-complexes 58291f830ff9bd73a07ca123c632 --pyeong 818
    """
    value = _require_complex_id(complex_id)
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_nearby_complexes(client, value, space_seq=pyeong)
        emit(result, pretty)


@app.command('neighborhood')
def neighborhood_command(
    query: Annotated[str, typer.Argument(help="법정동 이름 (예: 역삼동, '강남구 신사동')")],
    topic: Annotated[
        list[str] | None,
        typer.Option('--topic', help=f"주제: {', '.join(NEIGHBORHOOD_TOPICS)}. 반복하거나 쉼표로 구분. 기본 전체 (주제마다 요청 1회)"),
    ] = None,
    ranks: Annotated[
        bool,
        typer.Option('--ranks', help=(
            '학교·편의·교통·안전 주제의 종류마다 합계·구성과 전국·시도·구 순위를 더한다 (다방 동네정보 탭의 요약 칸). 종류마다 요청 '
            f'1회 더: {RANK_TYPE_COUNTS} (모두면 {RANK_ALL_REQUESTS}회). --topic 으로 주제를 좁히면 그 주제의 종류만 받는다'
        )),
    ] = False,
    pretty: PrettyOption = None,
) -> None:
    """다방 동네정보: 매물 수·거래량·아파트/오피스텔 평균가·인구(전국·시도·구 순위 포함)와 학교·편의·교통·안전 시설 수.
    --ranks 면 학교·편의·교통·안전도 종류마다 순위(ranks)를 붙인다.

    예: jibsa dabang neighborhood 역삼동
        jibsa dabang neighborhood 역삼동 --topic 매물,인구,학교
        jibsa dabang neighborhood 역삼동 --topic 편의,안전 --ranks
    """
    topics = split_csv(topic, NEIGHBORHOOD_TOPICS, '--topic')
    if ranks and topics and not any(item in RANK_TOPICS for item in topics):
        raise typer.BadParameter(
            f"--ranks 는 {'·'.join(RANK_TOPICS)} 주제의 순위입니다. --topic 에 그 주제를 넣거나 --ranks 를 빼세요", param_hint='--ranks',
        )
    with handle_errors(SOURCE), DabangClient() as client:
        dong = resolve_dong(
            client, query, subject='동네정보', elsewhere='jibsa dabang station-prices <역> 이나 search listings',
        )
        result = get_neighborhood(client, dong, topics, ranks=ranks)
        emit(result, pretty)


@app.command('hot-places')
def hot_places_command(
    query: Annotated[str, typer.Argument(help="법정동 이름 (예: 역삼동, '강남구 신사동')")],
    type_: Annotated[
        str,
        typer.Option('--type', '-t', help=f"가이드: {', '.join(HOT_PLACE_TYPE_BY_LABEL)} (다방 웹 고르기 이름 그대로). 기본 전체"),
    ] = '전체',
    limit: RegionInfoLimitOption = REGION_INFO_DEFAULT_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """동 안 핫플레이스: 미쉐린·블루리본 가이드에 오른 식당의 이름·가이드·주소·꼬리표 (다방 동네정보 '핫플레이스', 다방 목록 순).

    base_month 는 다방이 모은 기준 달이다. 사진은 주지 않는다.

    예: jibsa dabang hot-places 역삼동
        jibsa dabang hot-places 역삼동 --type 미쉐린
    """
    chosen_type = check_choice(type_, HOT_PLACE_TYPE_BY_LABEL, '--type')
    with handle_errors(SOURCE), DabangClient() as client:
        dong = resolve_dong(client, query, subject='핫플레이스', elsewhere=None)
        result = get_hot_places(client, dong, type_label=chosen_type, limit=limit)
        emit(result, pretty)


@app.command('popular-listings')
def popular_listings_command(
    query: Annotated[str, typer.Argument(help="법정동 이름 (예: 역삼동, '강남구 신사동')")],
    building_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"매물 유형: {', '.join(POPULAR_BUILDING_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체"),
    ] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help=f"거래 유형: {', '.join(POPULAR_PRICE_BY_TRADE)}. 반복하거나 쉼표로 구분. 기본 전체"),
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=POPULAR_MAX_LIMIT, help='받을 매물 수 (다방은 50건씩 준다)')] = 20,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """동 안 인기 매물 순위. 다방 선호도(조회수·찜수·문의수를 합친 점수) 높은 순이다 (rank 1 이 가장 높다).

    예: jibsa dabang popular-listings 역삼동 -t 빌라,오피스텔 --trade 월세 --limit 10
    """
    building_types = split_csv(building_type, tuple(POPULAR_BUILDING_BY_LABEL), '--type')
    trade_types = split_csv(trade, tuple(POPULAR_PRICE_BY_TRADE), '--trade')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_popular_listings(
            client, resolve_dong(client, query, subject='인기 매물', elsewhere='jibsa dabang search listings'),
            building_types=building_types, trade_types=trade_types, limit=limit,
        )
        emit(result, pretty, fields=fields)


@app.command('nearby')
def nearby_command(
    target_id: Annotated[
        str | None, typer.Argument(help='매물 ID (검색 결과의 id, 24자리) 또는 단지 ID (complex_id, 28자리). 분양은 빼고 --sale'),
    ] = None,
    sale: Annotated[
        str | None,
        typer.Option(
            '--sale',
            help=f'{SALE_ID_HELP}. 단지 ID 와 길이가 같아 옵션으로 받는다. 다방 분양 화면의 주변 정보',
        ),
    ] = None,
    with_: Annotated[
        list[str] | None,
        typer.Option('--with', help=(
            f"더 받을 생활 정보: {', '.join(NEARBY_EXTRAS)}. 반복하거나 쉼표로 구분. 하나마다 요청 1회 더. 반려동물(웹 '펫세권', "
            "2km 안 동물병원·미용실 등)은 단지만, 카셰어링(웹 'Car세권', 2km 안 쏘카존·그린존)은 매물·단지만 된다"
        )),
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """매물·단지·분양 둘레: 1km 안 지하철역(노선·거리), 500m 안 버스 노선 수, 종류마다 가까운 순 3곳 (매물은 버스·편의점·카페·
    은행·관공서·치안, 단지·분양은 버스·마트·편의점·은행·약국·치안)과 어린이집~고등학교 (요청 2회). 거리는 직선 거리(m)다.
    --with 반려동물·카셰어링 이면 가까운 순 3곳(반려동물은 종류마다)을 더한다. 전화번호는 주지 않는다.

    예: jibsa dabang nearby 6abb32f72f9f803f9c6f3830
        jibsa dabang nearby 58291f830ff9bd73a07ca123c632 --with 반려동물,카셰어링
        jibsa dabang nearby --sale 68f1ac43f6e4d16e5bf6b7fb2469
    """
    extras: list[NearbyExtra] = split_csv(with_, NEARBY_EXTRAS, '--with')
    if (target_id is None) == (sale is None):
        raise typer.BadParameter('매물·단지 ID 와 --sale 중 하나만 주세요', param_hint='TARGET_ID')
    if sale is not None:
        value = _require_sale_id(sale, '--sale')
    else:
        value = (target_id or '').strip()
        if LISTING_ID_PATTERN.fullmatch(value) is None and COMPLEX_ID_PATTERN.fullmatch(value) is None:
            raise typer.BadParameter(
                f"다방 매물 ID(24자리)나 단지 ID(28자리)가 아닙니다: '{target_id}'. 매물번호는 jibsa dabang listing 결과의 id 로 바꿔 주세요",
                param_hint='TARGET_ID',
            )
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_nearby(client, value, sale=sale is not None, extras=extras), pretty)


@app.command('station-prices')
def station_prices_command(
    station: Annotated[str, typer.Argument(help='지하철역 이름 (예: 강남역)')],
    pretty: PrettyOption = None,
) -> None:
    """역 둘레 평균 매물가: 빌라·오피스텔·아파트 × 원룸·투룸별 평균 전세금과 월세 보증금·월세 (요청 2회).

    다방 화면의 '평균 매물가' 로, 실거래가가 아니라 지금 다방 역 반경 안에 올라온 매물 가격의 평균이다. 쓰리룸 이상은 없다.

    예: jibsa dabang station-prices 강남역
    """
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_station_prices(client, resolve_places(client, station, only='station')), pretty)


def _one(values: list[str] | None, allowed: tuple[str, ...], option: str, default: str) -> str:
    """여러 번 줄 수 있게 열어 둔 옵션에서 하나만 받는다 (`split_csv` 로 검사하고 여럿이면 막는다).

    값이 하나뿐인 `str` 옵션은 `check_choice` 로 검사한다.
    """
    chosen = split_csv(values, allowed, option)
    if len(chosen) > 1:
        raise typer.BadParameter(f"하나만 주세요: {', '.join(chosen)}", param_hint=option)
    return chosen[0] if chosen else default


def _scope_radius_error(query: str | None) -> JibsaError:
    """분양 범위(전국·시·도·시·군·구) 이름에 --radius 를 준 에러. 범위를 찾기 전·후 두 자리가 같은 에러를 쓴다."""
    return JibsaError(
        code='INVALID_ARGUMENT',
        message=f"전국·시·도·시·군·구 범위에는 --radius 를 주지 않습니다: '{query}'",
        hint='그 범위 안 분양 전체는 --radius 를 빼고, 반경으로 찾으려면 동·역 이름이나 --lat/--lng 에 --radius 를 주세요',
    )


@search_app.command('sales')
def sales_command(
    query: Annotated[
        str | None,
        typer.Argument(
            help="동·시군구·시도·역·대학 이름이나 '전국' (예: 역삼동, 강남구, '성남시 분당구', 서울, 강남역). --lat/--lng 를 주면 생략",
        ),
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[
        float | None,
        _radius_option(f'역·대학·좌표 둘레 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 반경을 덮는 사각형으로 찾는다'),
    ] = None,
    building_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"건물 유형: {', '.join(SALE_BUILDING_TYPE_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체"),
    ] = None,
    state: Annotated[
        list[str] | None,
        typer.Option('--state', help=f"분양 상태: {', '.join(SALE_STATE_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체"),
    ] = None,
    supply: Annotated[
        list[str] | None,
        typer.Option('--supply', help=f"공급 유형: {', '.join(SALE_SUPPLY_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체"),
    ] = None,
    limit: Annotated[
        int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='받을 분양 단지 수 (동 이름이면 주소로 거르기 전, 다방은 24곳씩 준다)'),
    ] = DEFAULT_LIST_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """분양 단지 (새 아파트·오피스텔 청약). 상태·공급 유형·다음 일정·대표 분양가를 다방 목록 순으로 준다.

    전국·시·도·시·군·구는 다방 분양 지역 목록(웹 '분양정보' 목록)과 같은 목록·순서·총 수다. 동·역·대학·좌표는 지도 목록이다.
    상세(일정·평형별 분양가)는 결과의 presale_id 로 jibsa dabang sale <presale_id>.

    예: jibsa dabang search sales 강남구 --state 분양예정,접수중
        jibsa dabang search sales 서울 -t 아파트
        jibsa dabang search sales 강남역 --radius 3 -t 아파트
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    building_types = split_csv(building_type, tuple(SALE_BUILDING_TYPE_BY_LABEL), '--type')
    states = split_csv(state, tuple(SALE_STATE_BY_LABEL), '--state')
    supplies = split_csv(supply, tuple(SALE_SUPPLY_BY_LABEL), '--supply')
    with handle_errors(SOURCE), DabangClient() as client:
        find = partial(search_sales, client, building_types=building_types, states=states, supply_types=supplies, limit=limit)
        point = lat is not None and lng is not None
        # 전국·시·도 이름은 시·도 목록 요청 1회를 쓰기 전에 막는다. 시·군·구 모양 이름은 범위로 못 찾으면 동·역으로 다시 찾으므로
        # find_scope 뒤에서 본다
        if not point and radius is not None and is_national_or_state((query or '').strip()):
            raise _scope_radius_error(query)
        # --radius 를 줘도 범위 이름인지 먼저 본다. 보지 않으면 시·군·구를 동·역으로 찾아 '시·군·구 전체를 찾지 못한다' 는
        # 매물 검색용 에러로 끝난다 (2026-10-26 실측: search sales 강남구 --radius 2)
        scope, searched = find_scope(client, query or '') if not point else (None, None)
        if scope is not None and radius is not None:
            raise _scope_radius_error(query)
        if point:
            result = find(place=DabangPlace(kind='point', name=query or f'{lat},{lng}', lat=lat, lng=lng), radius_km=radius)
        elif scope is not None:
            result = find(scope=scope)
        else:
            place = resolve_places(client, query or '', searched=searched)
            if radius is None and place.kind == 'dong':
                result = find(dong=place)
            else:
                result = find(place=place, radius_km=radius)
        emit(result, pretty)


@app.command('sale')
def sale_command(
    sale_id: Annotated[str, typer.Argument(help=SALE_ID_HELP)],
    pretty: PrettyOption = None,
) -> None:
    """분양 단지 하나: 상태·공급 유형·세대수·시공사/시행사, 일정(모집공고~입주), 평형별 분양가·세대수, 모집공고·청약홈 주소.

    상담 전화는 주지 않는다. 확인·문의는 url 의 원 사이트나 모집공고에서.

    예: jibsa dabang sale 6a7a774cf962bc11cafe5cd6d0f1
    """
    value = _require_sale_id(sale_id)
    with handle_errors(SOURCE), DabangClient() as client:
        detail = get_sale(client, value)
        emit(detail, pretty)


@app.command('sale-schedule')
def sale_schedule_command(
    from_date: Annotated[
        str | None, typer.Option('--from', help='시작 날 (YYYY-MM-DD). 기본 오늘 (한국 날짜)'),
    ] = None,
    days: Annotated[int, typer.Option(min=1, max=7, help='며칠 (1~7, 다방은 7일까지)')] = 7,
    region: Annotated[
        str | None,
        typer.Option(
            '--region',
            help='시·도 (예: 서울, 경기, 충청북도). 상세를 받아(--details 와 같다) 주소의 시·도로 jibsa 가 거른다. 일정이 있는 날마다 요청 1회 더',
        ),
    ] = None,
    details: Annotated[
        bool,
        typer.Option(
            '--details',
            help='줄마다 분양 단지의 주소·건물 유형·공급 유형·세대수·가격을 붙인다 (다방 청약 일정에서 날짜를 누르면 나오는 표). 내보낼 줄이 든 날마다 요청 1회 더',
        ),
    ] = False,
    limit: Annotated[int, typer.Option(min=1, max=SALE_SCHEDULE_MAX_LIMIT, help='최대 일정 수')] = 50,
    pretty: PrettyOption = None,
) -> None:
    """날짜별 전국 청약 일정 (청약 접수·특별공급·당첨자발표 등, 요청 1회. --details·--region 이면 날마다 1회 더).

    예: jibsa dabang sale-schedule --region 서울
        jibsa dabang sale-schedule --from 2026-11-02 --days 3 --details
    """
    try:
        start = date.fromisoformat(from_date) if from_date else datetime.now(KST).date()
    except ValueError:
        raise typer.BadParameter(f"YYYY-MM-DD 꼴로 주세요: '{from_date}'", param_hint='--from') from None
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_sale_schedule(client, start=start, days=days, region=region, details=details, limit=limit)
        emit(result, pretty)


@app.command('trending-complexes')
def trending_complexes_command(
    complex_type: Annotated[list[str] | None, typer.Option('--type', '-t', help='단지 유형: 아파트, 오피스텔. 기본 아파트')] = None,
    period: Annotated[
        list[str] | None, typer.Option('--period', help=f"기간: {', '.join(WATCH_PERIOD_BY_LABEL)}. 기본 방금전"),
    ] = None,
    unit: Annotated[list[str] | None, typer.Option('--unit', help='단지 또는 동. 기본 단지')] = None,
    limit: Annotated[int, typer.Option(min=1, max=50, help='최대 순위 수 (다방은 50곳까지 준다)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """전국에서 지금 다방 조회가 많은 단지·동 순위 (요청 1회). 지역으로 좁히지 못한다.

    예: jibsa dabang trending-complexes
        jibsa dabang trending-complexes -t 오피스텔 --period 지난주 --unit 동
    """
    chosen_type = _one(complex_type, COMPLEX_KINDS, '--type', '아파트')
    chosen_period = _one(period, tuple(WATCH_PERIOD_BY_LABEL), '--period', '방금전')
    chosen_unit = _one(unit, WATCH_UNITS, '--unit', '단지')
    with handle_errors(SOURCE), DabangClient() as client:
        emit(
            get_watch_rankings(
                client, unit='동' if chosen_unit == '동' else '단지', complex_type=chosen_type, period=chosen_period, limit=limit,
            ),
            pretty,
        )


@app.command('trade-rankings')
def trade_rankings_command(
    complex_type: Annotated[list[str] | None, typer.Option('--type', '-t', help='단지 유형: 아파트, 오피스텔. 기본 아파트')] = None,
    trade: Annotated[list[str] | None, typer.Option('--trade', help='매매 또는 전세. 기본 매매')] = None,
    period: Annotated[
        list[str] | None, typer.Option('--period', help=f"기간: {', '.join(TRADE_PERIOD_BY_LABEL)}. 기본 이번주"),
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=50, help='최대 순위 수')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """전국에서 기간 안 실거래(국토교통부 신고)가 많은 단지 순위 (요청 1회).

    예: jibsa dabang trade-rankings
        jibsa dabang trade-rankings --trade 전세 --period 이번달
    """
    chosen_type = _one(complex_type, COMPLEX_KINDS, '--type', '아파트')
    chosen_trade = _one(trade, TRADE_RANKING_TRADES, '--trade', '매매')
    chosen_period = _one(period, tuple(TRADE_PERIOD_BY_LABEL), '--period', '이번주')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_trade_rankings(client, complex_type=chosen_type, trade=chosen_trade, period=chosen_period, limit=limit)
        emit(result, pretty)


@app.command('region-ranking')
def region_ranking_command(
    scope: Annotated[
        str,
        typer.Argument(help=(
            "범위: 시·군·구(예: 강남구, '성남시 분당구'), 시·도(예: 서울), 전국. --unit 단지 의 부동산 항목은 동(예: 역삼동, "
            "'강남구 신사동')도 받는다 (그 동 안 단지 순위)"
        )),
    ],
    by: Annotated[
        str,
        typer.Option('--by', help=(
            f"항목. 부동산(동·단지): {', '.join(REAL_ESTATE_METRICS)} (전세가율·갭가격은 --unit 단지만). "
            f"동네정보(동만): {', '.join(INFO_METRICS)}"
        )),
    ],
    unit: Annotated[list[str] | None, typer.Option('--unit', help='동 또는 단지. 기본 동')] = None,
    complex_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=(
            '단지 유형: 아파트, 오피스텔 (부동산 항목만, 세대수·연식은 받지 않음). 평균가·평당가·시세증감·최고가증감은 하나(기본 아파트), '
            '거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 주지 않거나 둘 다 주면(반복하거나 쉼표로 구분) 아파트·오피스텔 합산(다방 웹 기본). '
            f"{VILLA_LABEL}(주택/빌라)를 넣으면 매물수·거래량·선호도를 다방 동네정보 '매물정보' 탭 순위(동만)로 받는다: 고른 매물 유형 "
            f"({VILLA_LABEL}·오피스텔·아파트) 합산. 아파트·오피스텔만 주면 '시세정보' 탭 순위다"
        )),
    ] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help=(
            '거래 유형. 평균가·평당가·시세증감·최고가증감은 매매·전세 중 하나(기본 매매), 거래량·매물수·거래증감·매물증감·선호도는 '
            f"{'·'.join(RANKING_TRADE_BY_LABEL)} 여럿(기본 전체, 반복하거나 쉼표로 구분)"
        )),
    ] = None,
    kind: Annotated[
        list[str] | None,
        typer.Option('--kind', help=(
            '동네정보 항목의 종류 하나. 학원수: 입시(기본)·예체능·외국어·특성화·종합·인문사회·코딩, 학교 수: 국공립·사립, '
            '어린이집수: 공공·민간·가정·직장·협동, 시설: 의료시설은 병원·의원·약국·응급의료센터처럼 그 시설의 종류. 기본 전체'
        )),
    ] = None,
    order: Annotated[list[str] | None, typer.Option('--order', help='높은순 또는 낮은순. 기본 높은순')] = None,
    limit: Annotated[int, typer.Option(min=1, max=REGION_RANKING_MAX_LIMIT, help='최대 순위 수 (부동산 50곳, 동네정보·-t 빌라 30곳마다 요청 1회)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """범위 안 동·단지 순위 (다방 부동산·동네정보 랭킹).

    부동산(동네정보 '시세정보' 탭, 아파트·오피스텔): 평균가·평당가·거래량·매물수·시세증감·최고가증감·거래증감(전월대비)·
    매물증감(최근 30일 전 대비)·선호도·세대수·연식, 단지는 전세가율·갭가격도. 금액은 국토교통부 실거래, 매물수·매물증감·선호도는
    다방 기준이다. 단지 순위는 동 안으로도 좁힌다. -t 빌라 를 주면 매물수·거래량·선호도를 '매물정보' 탭(주택/빌라 포함)으로 받는다.
    동네정보(동만): 진학률(중학교 → 과학고·외국어고·자사고·예술체육고, 고등학교 → 대학교·전문대학, 학교알리미), 학원·학교 수,
    인구·인구증감, 편의·교통·안전 시설 수.

    예: jibsa dabang region-ranking 강남구 --by 평균가
        jibsa dabang region-ranking 서울 --by 전세가율 --unit 단지 --limit 10
        jibsa dabang region-ranking 역삼동 --by 평균가 --unit 단지
        jibsa dabang region-ranking 강남구 --by 거래증감
        jibsa dabang region-ranking 강남구 --by 매물수 -t 빌라
        jibsa dabang region-ranking 강남구 --by 과학고진학률
        jibsa dabang region-ranking 서울 --by 학원수 --kind 입시
    """
    by = check_choice(by, METRIC_BY_LABEL, '--by')
    spec = METRIC_BY_LABEL[by]
    chosen_unit = _one(unit, RANKING_UNITS, '--unit', '동')
    trades = split_csv(trade, tuple(RANKING_TRADE_BY_LABEL), '--trade')
    chosen_kind: str | None = None
    complex_types = split_csv(complex_type, (*COMPLEX_KINDS, VILLA_LABEL), '--type')
    if is_room_ranking(complex_types) and not isinstance(spec, InfoMetricSpec):
        # 주택/빌라 순위는 동네정보 '매물정보' 탭뿐이고 그 탭에는 매물수·거래량·선호도의 동 순위만 있다 (room-info 청크 2026-11-13)
        if by not in ROOM_RANKING_METRIC_BY_LABEL:
            raise typer.BadParameter(
                f"{VILLA_LABEL}(주택/빌라) 순위는 {'·'.join(ROOM_RANKING_METRIC_BY_LABEL)}만 있습니다 (다방 동네정보 '매물정보' 탭). "
                f'{by} 순위는 아파트·오피스텔만 받습니다',
                param_hint='--type',
            )
        if chosen_unit != '동':
            raise typer.BadParameter(f"{VILLA_LABEL}(주택/빌라) 순위는 동 단위만 있습니다 (다방 동네정보 '매물정보' 탭)", param_hint='--unit')
    if isinstance(spec, InfoMetricSpec):
        if chosen_unit != '동':
            raise typer.BadParameter(f'{by} 순위는 동 단위만 있습니다', param_hint='--unit')
        if trades:
            raise typer.BadParameter(f'{by} 순위는 거래 유형을 받지 않습니다', param_hint='--trade')
        if kind and not spec.kinds:
            raise typer.BadParameter(f'{by} 순위는 종류를 받지 않습니다', param_hint='--kind')
        if complex_type:
            raise typer.BadParameter(f'{by} 순위는 단지 유형을 받지 않습니다', param_hint='--type')
        if spec.kinds:
            chosen_kind = _one(kind, tuple(spec.kinds), '--kind', '') or None
    else:
        if spec.complex_only and chosen_unit != '단지':
            raise typer.BadParameter(f'{by} 순위는 단지 단위에만 있습니다. --unit 단지 를 주세요', param_hint='--by')
        if kind:
            raise typer.BadParameter(f'--kind 는 동네정보 항목만 받습니다: {by}', param_hint='--kind')
        if spec.trade == 'none' and trades:
            raise typer.BadParameter(f'{by} 순위는 거래 유형을 받지 않습니다', param_hint='--trade')
        if spec.types == 'none' and complex_types:
            # 다방이 단지 유형을 받지 않는 항목이라 요청에서 빠진다. 받아 두면 오피스텔 순위로 잘못 읽는다
            raise typer.BadParameter(f'{by} 순위는 단지 유형을 받지 않습니다', param_hint='--type')
        if spec.types == 'one' and len(set(complex_types)) > 1:
            # 웹도 이 항목은 유형을 하나만 고른다 (합산 순위가 없다)
            raise typer.BadParameter(f'{by} 순위는 아파트·오피스텔 중 하나만 받습니다', param_hint='--type')
        if spec.trade == 'one' and (len(trades) > 1 or '월세' in trades):
            raise typer.BadParameter(f'{by} 순위는 매매·전세 중 하나만 받습니다', param_hint='--trade')
    chosen_order = _one(order, RANKING_ORDERS, '--order', '높은순')
    ranking_unit: Literal['동', '단지'] = '단지' if chosen_unit == '단지' else '동'
    with handle_errors(SOURCE), DabangClient() as client:
        check_scope_name(scope, metric_label=by, unit=ranking_unit, complex_types=complex_types)
        result = get_region_ranking(
            client,
            resolve_scope(client, scope, dong=takes_dong_scope(by, ranking_unit)),
            metric_label=by,
            unit=ranking_unit,
            complex_types=complex_types,
            trades=trades,
            order='낮은순' if chosen_order == '낮은순' else '높은순',
            limit=limit,
            kind_label=chosen_kind,
        )
        emit(result, pretty)
