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
from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
    UnsupportedRegionError,
)
from jibsa.core.geo import DEFAULT_RADIUS_KM
from jibsa.core.korean import particle
from jibsa.core.listing import (
    KST,
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    UNBOUNDED_MAX,
    DabangBboxModel,
)
from jibsa.providers.dabang.api.response.region import DabangLocSearchResultModel
from jibsa.providers.dabang.service.common import (
    COMPLEX_ID_PATTERN,
    CONDITIONS_BY_KIND,
    DEFAULT_LIST_LIMIT,
    FLOOR_FILTER_BY_LABEL,
    LISTING_ID_PATTERN,
    LISTING_NUMBER_PATTERN,
    MAX_LIST_LIMIT,
    ROOM_LABELS_BY_KIND,
    SCHOOL_LEVELS,
    TRADE_TYPES_BY_KIND,
    DabangListingConditions,
    DabangPlace,
    ListingKind,
    middle_place,
)
from jibsa.providers.dabang.service.complex import (
    get_complex,
    list_complex_listings,
    search_complexes,
)
from jibsa.providers.dabang.service.listing import (
    get_listing,
    search_listings,
)
from jibsa.providers.dabang.service.nearby import (
    get_nearby,
    get_station_prices,
)
from jibsa.providers.dabang.service.neighborhood import (
    NEIGHBORHOOD_TOPICS,
    POPULAR_BUILDING_BY_LABEL,
    POPULAR_MAX_LIMIT,
    POPULAR_PRICE_BY_TRADE,
    get_neighborhood,
    get_popular_listings,
    single_dong,
)
from jibsa.providers.dabang.service.ranking import (
    METRIC_BY_LABEL,
    REGION_RANKING_MAX_LIMIT,
    TRADE_PERIOD_BY_LABEL,
    WATCH_PERIOD_BY_LABEL,
    InfoMetricSpec,
    get_region_ranking,
    get_trade_rankings,
    get_watch_rankings,
)
from jibsa.providers.dabang.service.real_price import (
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_MAX_YEARS,
    RealPriceTrade,
    get_listing_real_prices,
    get_price_trend,
    get_real_prices,
)
from jibsa.providers.dabang.service.region import (
    DISTRICT_PATTERN,
    NATIONAL_NAMES,
    DabangScope,
    legal_division_code,
    resolve_places,
    resolve_scope,
    search_locations,
    state_name,
)
from jibsa.providers.dabang.service.sale import (
    SALE_BUILDING_TYPE_BY_LABEL,
    SALE_STATE_BY_LABEL,
    SALE_SUPPLY_BY_LABEL,
    get_sale,
    get_sale_schedule,
    search_sales,
)
from jibsa.providers.dabang.service.school import (
    SCHOOL_CODE_PATTERN,
    get_school,
)

from typing import (
    Annotated,
    Any,
)


SOURCE: str = 'dabang'
MAX_RADIUS_KM: float = 5.0
REAL_PRICE_TRADES: tuple[str, ...] = ('매매', '전월세')
COMPLEX_KINDS: tuple[str, ...] = ('아파트', '오피스텔')
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
        '--details': '다방 상세는 jibsa dabang listing <id> 로 봅니다',
        '--sort': '다방 매물은 다방 목록 순으로만 줍니다',
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
        'search listings --complex), 상세(listing), 실거래(real-price, price-trend), 동네·주변(neighborhood, popular-listings, '
        'nearby, station-prices), 학교(school), 분양(search sales, sale, sale-schedule), 순위(trending-complexes, trade-rankings, '
        'region-ranking) '
        '(로그인 불필요, 금액은 만원 단위)'
    ),
    no_args_is_help=True,
)
search_app = typer.Typer(
    help='다방 장소 후보(locations), 매물 찾기(listings room·villa·officetel·apt), 단지 목록(complexes)',
    no_args_is_help=True,
)
app.add_typer(search_app, name='search')
listings_app = typer.Typer(
    help='매물 유형별 검색(room 원룸·투룸, villa 주택·빌라, officetel, apt) 또는 --complex 로 단지 매물',
    invoke_without_command=True,
)
search_app.add_typer(listings_app, name='listings')

QueryArgument = Annotated[
    str | None,
    typer.Argument(help="동·역·대학 이름 (예: 역삼동, '강남구 신사동', 강남역, 홍익대학교). --lat/--lng 를 주면 생략")
]
LatOption = Annotated[float | None, typer.Option(help='중심 위도 (이름 대신)')]
LngOption = Annotated[float | None, typer.Option(help='중심 경도 (이름 대신)')]
RadiusOption = Annotated[
    float | None,
    typer.Option(
        min=0.1,
        max=MAX_RADIUS_KM,
        help=(
            f'반경 (km). 주면 이름의 중심에서 반경을 덮는 사각형으로 받고 반경 밖은 뺀다. 없으면 동은 그 동 안, 역은 다방이 정한 '
            f'역 반경, 대학은 대학 둘레, 좌표는 {DEFAULT_RADIUS_KM:g}km'
        ),
    ),
]
LimitOption = Annotated[
    int, typer.Option(min=1, max=MAX_LIST_LIMIT, help=f'받을 매물 수 (제외 전, 다방은 24건씩 준다, 최대 {MAX_LIST_LIMIT})'),
]
RentIncludesManageOption = Annotated[
    bool, typer.Option('--rent-includes-manage-cost', help='--rent-min/--rent-max 를 월세 + 관리비로 본다 (다방 필터)'),
]
AreaPyeongMinOption = Annotated[int | None, typer.Option(min=0, help='방 크기 하한 (평, 정수)')]
AreaPyeongMaxOption = Annotated[int | None, typer.Option(min=0, help='방 크기 상한 (평, 정수)')]
BuiltWithinOption = Annotated[int | None, typer.Option(min=0, help='사용승인 뒤 이 햇수 이내 건물만 (년)')]
FloorOption = Annotated[
    list[str] | None,
    typer.Option('--floor', help=f"층: {', '.join(FLOOR_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분 (OR). 기본 전체"),
]


def _room_option(kind: ListingKind) -> object:
    return typer.Option('--room', help=f"방 개수: {', '.join(ROOM_LABELS_BY_KIND[kind])}. 반복하거나 쉼표로 구분 (OR). 기본 전체")


def _condition_option(kind: ListingKind) -> object:
    return typer.Option('--condition', help=f"기타 조건: {', '.join(CONDITIONS_BY_KIND[kind])}. 반복하거나 쉼표로 구분 (AND)")


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


def _places(client: DabangClient, query: str | None, lat: float | None, lng: float | None) -> tuple[list[DabangPlace], list[str]]:
    if lat is not None and lng is not None:
        return [DabangPlace(kind='point', name=query or f'{lat},{lng}', lat=lat, lng=lng)], []
    return resolve_places(client, query or '')


def _place_state(place: DabangPlace) -> dict[str, Any]:
    """이어 받기 표에 남길 위치. 출력하지 않는 다방 번호(동 코드·동 번호·역 번호)도 넣어야 장소 검색 없이 이어 받는다."""
    return {**place.model_dump(), 'code': place.code, 'gid': place.gid, 'place_id': place.place_id, 'radius_m': place.radius_m}


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
    limit: int,
    next_: str | None,
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
    )
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, TRADE_TYPES_BY_KIND[kind], '--trade', LISTING_HINTS),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
        allowed=TRADE_TYPES_BY_KIND[kind],
    )
    floors = split_csv(floor, tuple(FLOOR_FILTER_BY_LABEL), '--floor', LISTING_HINTS)
    rooms = split_csv(room, ROOM_LABELS_BY_KIND[kind], '--room', LISTING_HINTS)
    conditions_ = split_csv(condition, CONDITIONS_BY_KIND[kind], '--condition', LISTING_HINTS)
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
        )
        if position is not None and 'places' in position:
            # 이어 받기는 첫 결과가 찾은 위치를 그대로 쓴다. 장소 검색을 다시 묻지 않고, 그사이 다방 검색 순서가 바뀌어도
            # 같은 동·역에서 이어 받는다
            places = [DabangPlace.model_validate(item) for item in position['places']]
            notes = [str(item) for item in position.get('place_notes', [])]
        else:
            places, notes = _places(client, query, lat, lng)
        offsets = {str(key): int(value) for key, value in (position or {}).get('offsets', {}).items()}
        finished = {
            str(key): (int(done), None if counted is None else int(counted))
            for key, (done, counted) in (position or {}).get('finished', {}).items()
        }
        saved_bbox = (position or {}).get('bbox')
        result = search_listings(
            client, kind, places, conditions=conditions, limit=limit, radius_km=radius, offsets=offsets or None,
            finished=finished or None, bbox=DabangBboxModel.model_validate(saved_bbox) if saved_bbox else None,
        )
        next_position = result.next_position
        if next_position is not None:
            next_position = {**next_position, 'places': [_place_state(place) for place in places], 'place_notes': notes}
        emit(result, pretty, notes=trade_notes + notes + result.notes, next_token=encode_next(next_position), fields=fields)


@search_app.command('locations')
def locations_command(
    query: Annotated[str, typer.Argument(help='동·역·대학·단지 이름 (예: 역삼동, 강남역, 홍익대학교, 은마)')],
    limit: Annotated[int, typer.Option(min=1, max=50, help='종류마다 최대 후보 수')] = 10,
    pretty: PrettyOption = None,
) -> None:
    """이름으로 다방의 동·역·대학·단지·분양 후보를 찾는다 (요청 1회).

    complexes[].complex_id 를 jibsa dabang complex·search listings --complex·real-price 에, sales[].sale_id 를 sale 에 넘긴다.

    예: jibsa dabang search locations 강남역
        jibsa dabang search locations 은마
    """
    with handle_errors(SOURCE), DabangClient() as client:
        result = search_locations(client, query, ['REGION', 'SUBWAY', 'UNIV', 'COMPLEX', 'SALE_IN_LOTS'])
        emit(
            {
                'query': query,
                'regions': [
                    {
                        'name': region.name,
                        'address': normalize_address(region.full_name),
                        'legal_division_code': legal_division_code(region.code),
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
                'sales': [
                    {'sale_id': sale.id, 'name': sale.name, 'state': sale.format_state, 'address': normalize_address(sale.address)}
                    for sale in result.sale_in_lots_list[:limit]
                ],
            },
            pretty,
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
    area_pyeong_min: AreaPyeongMinOption = None,
    area_pyeong_max: AreaPyeongMaxOption = None,
    built_within: BuiltWithinOption = None,
    floor: FloorOption = None,
    room: Annotated[list[str] | None, _room_option('room')] = None,
    condition: Annotated[list[str] | None, _condition_option('room')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """원룸·투룸 (다방 '원룸·투룸' 목록). 원룸은 방 하나짜리라 원룸형 오피스텔도 나온다. 매매는 없다.

    다방 목록 순으로 준다 (거리순이 아니다). 단기임대를 받는 월세 매물은 short_lease: true 다.

    예: jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
        jibsa dabang search listings room 강남역 --room 투룸 --condition 주차,엘리베이터
        jibsa dabang search listings room 역삼동 --trade 월세 --next <앞 결과의 next>
    """
    _search(
        'room', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=None, price_max=None, rent_includes_manage_cost=rent_includes_manage_cost,
        area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max, built_within=built_within, floor=floor, room=room,
        condition=condition, households_min=None, households_max=None, limit=limit, next_=next_, fields=fields, pretty=pretty,
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
    area_pyeong_min: AreaPyeongMinOption = None,
    area_pyeong_max: AreaPyeongMaxOption = None,
    built_within: BuiltWithinOption = None,
    floor: FloorOption = None,
    room: Annotated[list[str] | None, _room_option('villa')] = None,
    condition: Annotated[list[str] | None, _condition_option('villa')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """주택·빌라 (다방 '주택·빌라' 목록). 방 하나짜리 빌라도 나온다 (property_type '빌라').

    예: jibsa dabang search listings villa 성수동 --trade 전세 --deposit-max 30000 --room 투룸,쓰리룸
    """
    _search(
        'villa', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=floor, room=room, condition=condition, households_min=None, households_max=None,
        limit=limit, next_=next_, fields=fields, pretty=pretty,
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
    area_pyeong_min: AreaPyeongMinOption = None,
    area_pyeong_max: AreaPyeongMaxOption = None,
    built_within: BuiltWithinOption = None,
    room: Annotated[list[str] | None, _room_option('officetel')] = None,
    condition: Annotated[list[str] | None, _condition_option('officetel')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """오피스텔 (다방 '오피스텔' 목록). 층 조건은 없다.

    예: jibsa dabang search listings officetel 강남역 --trade 월세 --rent-max 100 --condition 주차
    """
    _search(
        'officetel', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min,
        deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=None, room=room, condition=condition, households_min=None, households_max=None,
        limit=limit, next_=next_, fields=fields, pretty=pretty,
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
    area_pyeong_min: AreaPyeongMinOption = None,
    area_pyeong_max: AreaPyeongMaxOption = None,
    built_within: BuiltWithinOption = None,
    room: Annotated[list[str] | None, _room_option('apt')] = None,
    condition: Annotated[list[str] | None, _condition_option('apt')] = None,
    households_min: Annotated[int | None, typer.Option(min=0, help='단지 세대수 하한')] = None,
    households_max: Annotated[int | None, typer.Option(min=0, help='단지 세대수 상한')] = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """아파트 (다방 '아파트' 목록, 주상복합·도시형 포함). 다방이 동 검색을 주지 않아 동 이름은 동 경계를 덮는 사각형으로 받아
    그 동 매물만 남긴다 (다른 동 매물만큼 returned 가 줄 수 있다).

    예: jibsa dabang search listings apt 대치동 --trade 매매 --price-max 300000
        jibsa dabang search listings apt 강남역 --trade 전세 --households-min 500
    """
    _search(
        'apt', query=query, lat=lat, lng=lng, radius=radius, trade=trade, deposit_min=deposit_min, deposit_max=deposit_max,
        rent_min=rent_min, rent_max=rent_max, price_min=price_min, price_max=price_max,
        rent_includes_manage_cost=rent_includes_manage_cost, area_pyeong_min=area_pyeong_min, area_pyeong_max=area_pyeong_max,
        built_within=built_within, floor=None, room=room, condition=condition, households_min=households_min,
        households_max=households_max, limit=limit, next_=next_, fields=fields, pretty=pretty,
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


@listings_app.callback()
def complex_listings_command(
    ctx: typer.Context,
    complex_id: Annotated[str | None, typer.Option('--complex', help='아파트·오피스텔 단지 ID (28자리)')] = None,
    pyeong: Annotated[
        list[str] | None,
        typer.Option('--pyeong', metavar='<int>', help='평형 번호 (complex 결과의 pyeongs[].space_seq). 반복하거나 쉼표로 구분 (OR). 기본 전체'),
    ] = None,
    trade: Annotated[list[str] | None, typer.Option('--trade', help='거래 유형: 월세, 전세, 매매. 반복하거나 쉼표로 구분. 기본 전체')] = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    limit: LimitOption = DEFAULT_LIST_LIMIT,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 하나의 매물 (다방 목록 순). 조건은 다방 서버가 거른다. 상세는 결과의 id 로 jibsa dabang listing <id>.

    예: jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 전세
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
        result = list_complex_listings(client, value, conditions=conditions, space_seqs=space_seqs, limit=limit)
        emit(result, pretty, notes=trade_notes + result.notes, fields=fields)


@search_app.command('complexes')
def complexes_command(
    query: QueryArgument = None,
    complex_type: Annotated[str, typer.Option('--type', '-t', help='단지 유형: 아파트, 오피스텔')] = '아파트',
    lat: LatOption = None,
    lng: LngOption = None,
    radius: RadiusOption = None,
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
    chosen_type = _one([complex_type], COMPLEX_KINDS, '--type', '아파트')
    with handle_errors(SOURCE), DabangClient() as client:
        places, notes = _places(client, query, lat, lng)
        result = search_complexes(client, '오피스텔' if chosen_type == '오피스텔' else '아파트', places, limit=limit, radius_km=radius)
        emit(result, pretty, notes=notes + result.notes)


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
        emit(get_listing(client, value), pretty)


@app.command('complex')
def complex_command(
    complex_id: Annotated[str, typer.Argument(help='단지 ID (search locations·search complexes 결과의 complex_id)')],
    pretty: PrettyOption = None,
) -> None:
    """단지 정보: 세대수·동 수·주차·층·용적률·건폐율·시공사·사용승인일, 평형(pyeongs[].space_seq), 평당가 비교, 최근 실거래, 학교.

    예: jibsa dabang complex 58291f830ff9bd73a07ca123c632
    """
    value = _require_complex_id(complex_id)
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_complex(client, value)
        emit(result, pretty, notes=result.notes)


@app.command('school')
def school_command(
    school_code: Annotated[str, typer.Argument(help='학교 코드 (complex 결과 schools[].school_code, 예: S010000704)')],
    level: Annotated[
        str,
        typer.Option('--level', help='초등학교, 중학교, 고등학교 (complex 결과 schools[].level). 코드와 맞아야 한다'),
    ],
    pretty: PrettyOption = None,
) -> None:
    """학교 하나의 학교알리미 공시: 학급당·교원당 학생 수(시·도·시·군·구 평균과 비교), 중학교 고교 유형별 진학률, 고등학교 대학 진학률.

    학교 코드는 complex 결과의 schools[] 에서 옮긴다. 전화·홈페이지·좌표는 주지 않는다.

    예: jibsa dabang school S010000704 --level 중학교
    """
    value = school_code.strip()
    if SCHOOL_CODE_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(f"학교 코드는 영문·숫자입니다: '{school_code}'", param_hint='SCHOOL_CODE')
    if level not in SCHOOL_LEVELS:
        raise typer.BadParameter(f"허용되지 않는 값입니다: '{level}'. 가능한 값: {', '.join(SCHOOL_LEVELS)}", param_hint='--level')
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_school(client, value, level), pretty)


@app.command('real-price')
def real_price_command(
    complex_id: Annotated[str | None, typer.Argument(help='단지 ID. 단지 없는 매물은 빼고 --listing')] = None,
    listing: Annotated[
        str | None,
        typer.Option('--listing', help='단지 없는 매물(빌라·주택·원룸)의 매물 ID. 그 동의 같은 건물 유형 실거래를 준다'),
    ] = None,
    pyeong: Annotated[
        int | None, typer.Option('--pyeong', min=1, help='평형 번호 (complex 결과의 pyeongs[].space_seq). 기본 다방 대표 평형'),
    ] = None,
    trade: Annotated[str, typer.Option('--trade', help='매매 또는 전월세 (전세·월세를 함께 준다)')] = '매매',
    years: Annotated[
        int, typer.Option('--years', min=1, max=REAL_PRICE_MAX_YEARS, help=f'최근 몇 년 (1~{REAL_PRICE_MAX_YEARS}, 다방은 {REAL_PRICE_MAX_YEARS}년까지)'),
    ] = REAL_PRICE_MAX_YEARS,
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 30,
    pretty: PrettyOption = None,
) -> None:
    """실거래가 (국토부 신고 기준, 최근 계약 순). cancelled: true 는 해제된 거래.

    예: jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --trade 매매
        jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --pyeong 817 --trade 전월세 --years 1
        jibsa dabang real-price --listing 6abb32f72f9f803f9c6f3830 --trade 전월세
    """
    if (complex_id is None) == (listing is None):
        raise typer.BadParameter('단지 ID 와 --listing 중 하나만 주세요', param_hint='COMPLEX_ID')
    chosen_trade = _one([trade], REAL_PRICE_TRADES, '--trade', '매매')
    real_trade: RealPriceTrade = '전월세' if chosen_trade == '전월세' else '매매'
    if listing is not None:
        if pyeong is not None:
            raise typer.BadParameter('--pyeong 은 단지 실거래에만 씁니다', param_hint='--pyeong')
        listing_id = listing.strip()
        if LISTING_ID_PATTERN.fullmatch(listing_id) is None:
            raise typer.BadParameter(f"다방 매물 ID(24자리)가 아닙니다: '{listing}'", param_hint='--listing')
        with handle_errors(SOURCE), DabangClient() as client:
            result = get_listing_real_prices(client, listing_id, trade=real_trade, years=years, limit=limit)
            emit(result, pretty, notes=result.notes)
        return
    value = _require_complex_id(complex_id or '')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_real_prices(client, value, space_seq=pyeong, trade=real_trade, years=years, limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('price-trend')
def price_trend_command(
    complex_id: Annotated[str, typer.Argument(help='단지 ID')],
    pyeong: Annotated[
        int | None, typer.Option('--pyeong', min=1, help='평형 번호 (complex 결과의 pyeongs[].space_seq). 기본 다방 대표 평형'),
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """평형 하나의 36달 시세 흐름: 달마다 매매·전세 평균 실거래가와 거래 수, 전세가율, 1년·3년 최고·최저 (요청 1회).

    예: jibsa dabang price-trend 58291f830ff9bd73a07ca123c632 --pyeong 817
    """
    value = _require_complex_id(complex_id)
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_price_trend(client, value, space_seq=pyeong)
        emit(result, pretty, notes=result.notes)


@app.command('neighborhood')
def neighborhood_command(
    query: Annotated[str, typer.Argument(help="법정동 이름 (예: 역삼동, '강남구 신사동')")],
    topic: Annotated[
        list[str] | None,
        typer.Option('--topic', help=f"주제: {', '.join(NEIGHBORHOOD_TOPICS)}. 반복하거나 쉼표로 구분. 기본 전체 (주제마다 요청 1회)"),
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """다방 동네정보: 매물 수·거래량·아파트/오피스텔 평균가·인구(전국·시도·구 순위 포함)와 학교·편의·교통·안전 시설 수.

    예: jibsa dabang neighborhood 역삼동
        jibsa dabang neighborhood 역삼동 --topic 매물,인구,학교
    """
    topics = split_csv(topic, NEIGHBORHOOD_TOPICS, '--topic')
    with handle_errors(SOURCE), DabangClient() as client:
        places, notes = resolve_places(client, query)
        result = get_neighborhood(client, single_dong(places, query), topics)
        emit(result, pretty, notes=notes)


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
        places, notes = resolve_places(client, query)
        result = get_popular_listings(
            client, single_dong(places, query), building_types=building_types, trade_types=trade_types, limit=limit,
        )
        emit(result, pretty, notes=notes + result.notes, fields=fields)


@app.command('nearby')
def nearby_command(
    target_id: Annotated[
        str, typer.Argument(help='매물 ID (검색 결과의 id, 24자리) 또는 단지 ID (complex_id, 28자리)'),
    ],
    pretty: PrettyOption = None,
) -> None:
    """매물·단지 둘레: 1km 안 지하철역(노선·거리), 500m 안 버스 노선 수, 가장 가까운 버스정류장·편의점·카페·은행·공공기관·경찰과
    어린이집~고등학교 (요청 2회). 거리는 직선 거리(m)다.

    예: jibsa dabang nearby 6abb32f72f9f803f9c6f3830
        jibsa dabang nearby 58291f830ff9bd73a07ca123c632
    """
    value = target_id.strip()
    if LISTING_ID_PATTERN.fullmatch(value) is None and COMPLEX_ID_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(
            f"다방 매물 ID(24자리)나 단지 ID(28자리)가 아닙니다: '{target_id}'. 매물번호는 jibsa dabang listing 결과의 id 로 바꿔 주세요",
            param_hint='TARGET_ID',
        )
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_nearby(client, value), pretty)


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
        places, notes = resolve_places(client, station)
        emit(get_station_prices(client, places[0]), pretty, notes=notes)


SALE_ID_HELP: str = '분양 ID (search sales·search locations 결과의 sale_id, 28자리)'
WATCH_UNITS: tuple[str, ...] = ('단지', '동')
RANKING_UNITS: tuple[str, ...] = ('동', '단지')
RANKING_ORDERS: tuple[str, ...] = ('높은순', '낮은순')
TRADE_RANKING_TRADES: tuple[str, ...] = ('매매', '전세')


def _one(values: list[str] | None, allowed: tuple[str, ...], option: str, default: str) -> str:
    """하나만 받는 라벨 옵션 (`split_csv` 로 검사하고 여럿이면 막는다)."""
    chosen = split_csv(values, allowed, option)
    if len(chosen) > 1:
        raise typer.BadParameter(f"하나만 주세요: {', '.join(chosen)}", param_hint=option)
    return chosen[0] if chosen else default


def _is_scope_name(query: str) -> bool:
    """전국·시·도·시·군·구 이름처럼 보이는지 ('전국', '서울', '경기도', '강남구', '성남시 분당구')."""
    text = query.strip()
    words = text.split()
    return text in NATIONAL_NAMES or state_name(text) is not None or bool(words and DISTRICT_PATTERN.fullmatch(words[-1]))


def _sales_scope(client: DabangClient, query: str) -> tuple[DabangScope | None, DabangLocSearchResultModel | None]:
    """분양을 시·군·구 범위로 찾을 이름이면 그 범위, 동·역·대학 이름이면 None.

    이름 모양만 보면 '홍대입구'·'을지로입구' 같은 역도 '구' 로 끝나 시·군·구로 보인다. 범위로 찾지 못한 이름은 None 으로
    돌려 동·역으로 다시 찾게 한다 (2026-10-25 실측: '홍대입구' 가 REGION_NOT_FOUND 로 끝났다).

    Returns:
        (범위, 장소 검색 결과). 시·군·구 모양 이름은 여기서 장소 검색을 한 번 받아 `resolve_scope` 에 주고, 범위로 찾지
        못하면 그 결과를 돌려 `resolve_places` 가 같은 요청을 또 보내지 않게 한다.

    Raises:
        UnsupportedRegionError: '전국'·시·도 이름일 때 (분양은 시·군·구까지만 찾는다). 요청 없이 이름으로 막는다.
    """
    if not _is_scope_name(query):
        return None, None
    text = query.strip()
    # 전국·시·도는 시·도 목록을 묻기 전에 막는다 ('서울시' 도 '시' 로 끝나지만 시·도다). `resolve_scope` 는 이 두 경우에만
    # 시·군·구가 아닌 범위를 주므로, 아래에서 받는 범위는 늘 시·군·구다
    if text in NATIONAL_NAMES or state_name(text) is not None:
        raise UnsupportedRegionError(
            code='REGION_NOT_SUPPORTED',
            message=f"분양은 시·도·전국 범위로 찾지 않습니다: '{text}'",
            hint="시·군·구 이름(예: '강남구')이나 동·역 이름으로 찾으세요. 날짜별 전국 일정은 jibsa dabang sale-schedule",
            skip_note=f"{text}{particle(text, '은/는')} 범위가 넓어 건너뛰었습니다",
        )
    searched = search_locations(client, text)
    try:
        scope = resolve_scope(client, query, searched=searched)
    except RegionNotFoundError:
        return None, searched
    return scope, searched


@search_app.command('sales')
def sales_command(
    query: Annotated[
        str | None,
        typer.Argument(help="동·시군구·역·대학 이름 (예: 역삼동, 강남구, '성남시 분당구', 강남역). --lat/--lng 를 주면 생략"),
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=MAX_RADIUS_KM, help=f'역·대학·좌표 둘레 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 반경을 덮는 사각형으로 찾는다'),
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
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='받을 분양 단지 수 (제외 전, 다방은 24곳씩 준다)')] = DEFAULT_LIST_LIMIT,
    pretty: PrettyOption = None,
) -> None:
    """분양 단지 (새 아파트·오피스텔 청약). 상태·공급 유형·다음 일정·대표 분양가를 다방 목록 순으로 준다.

    상세(일정·평형별 분양가)는 결과의 sale_id 로 jibsa dabang sale <sale_id>.

    예: jibsa dabang search sales 강남구 --state 분양예정,접수중
        jibsa dabang search sales 강남역 --radius 3 -t 아파트
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    building_types = split_csv(building_type, tuple(SALE_BUILDING_TYPE_BY_LABEL), '--type')
    states = split_csv(state, tuple(SALE_STATE_BY_LABEL), '--state')
    supplies = split_csv(supply, tuple(SALE_SUPPLY_BY_LABEL), '--supply')
    with handle_errors(SOURCE), DabangClient() as client:
        find = partial(search_sales, client, building_types=building_types, states=states, supply_types=supplies, limit=limit)
        notes: list[str] = []
        point = lat is not None and lng is not None
        # --radius 를 줘도 시·군·구 이름인지 먼저 본다. 보지 않으면 시·군·구를 동·역으로 찾아 '시·군·구 전체를 찾지 못한다' 는
        # 매물 검색용 에러로 끝난다 (2026-10-26 실측: search sales 강남구 --radius 2)
        scope, searched = _sales_scope(client, query or '') if not point else (None, None)
        if scope is not None and radius is not None:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"시·군·구 범위에는 --radius 를 주지 않습니다: '{query}'",
                hint='시·군·구 안 분양 전체는 --radius 를 빼고, 반경으로 찾으려면 동·역 이름이나 --lat/--lng 에 --radius 를 주세요',
            )
        if point:
            result = find(place=DabangPlace(kind='point', name=query or f'{lat},{lng}', lat=lat, lng=lng), radius_km=radius)
        elif scope is not None:
            result = find(scope=scope)
        else:
            places, notes = resolve_places(client, query or '', searched=searched)
            if radius is None and places[0].kind == 'dong':
                result = find(places=places)
            else:
                result = find(place=middle_place(places), radius_km=radius)
        emit(result, pretty, notes=notes + result.notes)


@app.command('sale')
def sale_command(
    sale_id: Annotated[str, typer.Argument(help=SALE_ID_HELP)],
    pretty: PrettyOption = None,
) -> None:
    """분양 단지 하나: 상태·공급 유형·세대수·시공사/시행사, 일정(모집공고~입주), 평형별 분양가·세대수, 모집공고·청약홈 주소.

    상담 전화는 주지 않는다. 확인·문의는 url 의 원 사이트나 모집공고에서.

    예: jibsa dabang sale 6a7a774cf962bc11cafe5cd6d0f1
    """
    value = sale_id.strip()
    if COMPLEX_ID_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(f"다방 분양 ID(28자리)가 아닙니다: '{sale_id}'", param_hint='SALE_ID')
    with handle_errors(SOURCE), DabangClient() as client:
        emit(get_sale(client, value), pretty)


@app.command('sale-schedule')
def sale_schedule_command(
    from_date: Annotated[
        str | None, typer.Option('--from', help='시작 날 (YYYY-MM-DD). 기본 오늘 (한국 날짜)'),
    ] = None,
    days: Annotated[int, typer.Option(min=1, max=7, help='며칠 (1~7, 다방은 7일까지)')] = 7,
    region: Annotated[
        str | None, typer.Option('--region', help='시·도 (예: 서울, 경기, 충청북도). 일정 글의 시·도로 jibsa 가 거른다'),
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=300, help='최대 일정 수')] = 50,
    pretty: PrettyOption = None,
) -> None:
    """날짜별 전국 청약 일정 (청약 접수·특별공급·당첨자발표 등, 요청 1회).

    예: jibsa dabang sale-schedule --region 서울
        jibsa dabang sale-schedule --from 2026-11-02 --days 3
    """
    try:
        start = date.fromisoformat(from_date) if from_date else datetime.now(KST).date()
    except ValueError:
        raise typer.BadParameter(f"YYYY-MM-DD 꼴로 주세요: '{from_date}'", param_hint='--from') from None
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_sale_schedule(client, start=start, days=days, region=region, limit=limit)
        emit(result, pretty, notes=result.notes)


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
    chosen_type = _one(complex_type, ('아파트', '오피스텔'), '--type', '아파트')
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
    chosen_type = _one(complex_type, ('아파트', '오피스텔'), '--type', '아파트')
    chosen_trade = _one(trade, TRADE_RANKING_TRADES, '--trade', '매매')
    chosen_period = _one(period, tuple(TRADE_PERIOD_BY_LABEL), '--period', '이번주')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_trade_rankings(client, complex_type=chosen_type, trade=chosen_trade, period=chosen_period, limit=limit)
        emit(result, pretty, notes=result.notes)


REAL_ESTATE_METRICS: tuple[str, ...] = tuple(label for label, spec in METRIC_BY_LABEL.items() if not isinstance(spec, InfoMetricSpec))
INFO_METRICS: tuple[str, ...] = tuple(label for label, spec in METRIC_BY_LABEL.items() if isinstance(spec, InfoMetricSpec))


@app.command('region-ranking')
def region_ranking_command(
    scope: Annotated[str, typer.Argument(help="범위: 시·군·구(예: 강남구, '성남시 분당구'), 시·도(예: 서울), 전국")],
    by: Annotated[
        str,
        typer.Option('--by', help=(
            f"항목. 부동산(동·단지): {', '.join(REAL_ESTATE_METRICS)} (전세가율·갭가격은 --unit 단지만). "
            f"동네정보(동만): {', '.join(INFO_METRICS)}"
        )),
    ],
    unit: Annotated[list[str] | None, typer.Option('--unit', help='동 또는 단지. 기본 동')] = None,
    complex_type: Annotated[list[str] | None, typer.Option('--type', '-t', help='단지 유형: 아파트, 오피스텔. 기본 아파트 (부동산 항목만, 세대수·연식은 받지 않음)')] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help=(
            '거래 유형. 평균가·평당가·시세증감·최고가증감은 매매·전세 중 하나(기본 매매), 거래량·매물수·선호도는 매매·전세·월세 '
            '여럿(기본 전체)'
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
    limit: Annotated[int, typer.Option(min=1, max=REGION_RANKING_MAX_LIMIT, help='최대 순위 수 (부동산 50곳, 동네정보 30곳마다 요청 1회)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """범위 안 동·단지 순위 (다방 부동산·동네정보 랭킹).

    부동산: 평균가·평당가·거래량·매물수·시세증감·최고가증감·선호도·세대수·연식, 단지는 전세가율·갭가격도. 금액은 국토교통부
    실거래, 매물수·선호도는 다방 기준이다. 동네정보(동만): 진학률(중학교 → 과학고·외국어고·자사고·예술체육고, 고등학교 →
    대학교·전문대학, 학교알리미), 학원·학교 수, 인구·인구증감, 편의·교통·안전 시설 수.

    예: jibsa dabang region-ranking 강남구 --by 평균가
        jibsa dabang region-ranking 서울 --by 전세가율 --unit 단지 --limit 10
        jibsa dabang region-ranking 강남구 --by 과학고진학률
        jibsa dabang region-ranking 서울 --by 학원수 --kind 입시
    """
    if by not in METRIC_BY_LABEL:
        raise typer.BadParameter(f"허용되지 않는 값입니다: '{by}'. 가능한 값: {', '.join(METRIC_BY_LABEL)}", param_hint='--by')
    spec = METRIC_BY_LABEL[by]
    chosen_unit = _one(unit, RANKING_UNITS, '--unit', '동')
    trades = split_csv(trade, ('매매', '전세', '월세'), '--trade')
    chosen_kind: str | None = None
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
        if not spec.complex_type and complex_type:
            # 다방이 단지 유형을 받지 않는 항목이라 요청에서 빠진다. 받아 두면 오피스텔 순위로 잘못 읽는다
            raise typer.BadParameter(f'{by} 순위는 단지 유형을 받지 않습니다', param_hint='--type')
        if spec.trade == 'one' and (len(trades) > 1 or '월세' in trades):
            raise typer.BadParameter(f'{by} 순위는 매매·전세 중 하나만 받습니다', param_hint='--trade')
    chosen_type = _one(complex_type, ('아파트', '오피스텔'), '--type', '아파트')
    chosen_order = _one(order, RANKING_ORDERS, '--order', '높은순')
    with handle_errors(SOURCE), DabangClient() as client:
        result = get_region_ranking(
            client,
            resolve_scope(client, scope),
            metric_label=by,
            unit='단지' if chosen_unit == '단지' else '동',
            complex_type=chosen_type,
            trades=trades,
            order='낮은순' if chosen_order == '낮은순' else '높은순',
            limit=limit,
            kind_label=chosen_kind,
        )
        emit(result, pretty, notes=result.notes)
