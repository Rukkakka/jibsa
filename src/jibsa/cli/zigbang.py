import typer

from jibsa.cli.options import (
    DepositMaxOption,
    DepositMinOption,
    PrettyOption,
    PriceMaxOption,
    PriceMinOption,
    RentMaxOption,
    RentMinOption,
)
from jibsa.cli.output import (
    emit,
    handle_errors,
    infer_trade_types,
    require_finite,
    require_korea,
    split_csv,
    validate_ranges,
)
from jibsa.core.errors import RegionNotFoundError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    multipolygon_bounds,
)
from jibsa.core.korean import (
    is_ri_code,
    particle,
    quoted,
)
from jibsa.core.listing import normalize_address
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.stay import (
    ZigbangGuestItemsFiltersRequestParameterModel,
    ZigbangGuestItemsPriceCalculationRequestPayloadModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.service.apt import (
    APT_NEAR_MAX_RADIUS_KM,
    APT_TRADE_TYPES,
    ZigbangAptConditions,
    merged_dong_region,
    merged_gu_region,
    resolve_apt_region,
    search_apt_listings,
    search_apt_listings_near,
)
from jibsa.providers.zigbang.service.common import (
    COMPLEX_ID_PATTERN,
    CONDITIONS,
    FLOOR_FILTERS,
    MAX_LIST_LIMIT,
    OPTION_FILTERS,
    ROOM_TYPES,
    TRADE_TYPES,
    ZigbangBoundary,
    ZigbangRegion,
    ZigbangRoomConditions,
)
from jibsa.providers.zigbang.service.complex import (
    get_complex,
    list_complex_listings,
    search_regions_and_complexes,
)
from jibsa.providers.zigbang.service.detail import (
    LISTING_ID_PATTERN,
    get_any_listing,
)
from jibsa.providers.zigbang.service.listing import (
    GEOHASH_PRECISION,
    PROPERTY_TYPES,
    check_without_random,
    search_listings,
    unsearchable_note,
    unsearchable_types,
)
from jibsa.providers.zigbang.service.real_price import (
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_TRADE_TYPES,
    get_real_prices,
)
from jibsa.providers.zigbang.service.region import (
    MAX_RADIUS_KM,
    city_gu_regions,
    dong_boundary,
    merge_dong_boundaries,
    resolve_region_scope,
    resolve_region_with_notes,
    search_regions,
    wide_area_note,
    wide_boundary_note,
)
from jibsa.providers.zigbang.service.stay import (
    STAY_BUILDING_TYPE_BY_LABEL,
    STAY_DISCOUNT_TYPE_BY_LABEL,
    STAY_FLOOR_TYPE_BY_LABEL,
    STAY_GEOHASH_PRECISION,
    STAY_OPTION_BY_LABEL,
    ZigbangStayConditions,
    check_stay_sort,
    search_stay_listings,
)
from jibsa.providers.zigbang.service.store import (
    STORE_BUSINESS_NAMES,
    STORE_GEOHASH_PRECISION,
    STORE_TRADE_TYPES,
    ZigbangStoreConditions,
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

app = typer.Typer(
    help=(
        '직방: 매물 찾기(search listings room·apt·store·stay), 지역·단지(search locations, complex, search listings --complex, real-price), 상세(listing) '
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


ScopeRadiusOption = Annotated[
    float | None,
    typer.Option(
        min=0.1,
        max=MAX_RADIUS_KM,
        help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동 이름에 --radius 를 주지 않으면 반경 대신 그 동 경계 안을 찾는다. 반경 안 매물이 모자라면 반경 밖 가까운 매물도 나온다',
    ),
]


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
    region, notes, split_note, split = resolve_region_scope(client, query or '', items=items)
    boundary = None
    if radius is None:
        # '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)은 경계를 합쳐 모두 찾는다
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
        notes.append(f'동 이름이라 반경 대신 {boundary.name} 경계 안을 찾았습니다. 위치 기준으로 찾으려면 --radius 를 주세요')
    return region, notes, boundary, radius_km


def _require_center(query: str | None, lat: float | None, lng: float | None) -> None:
    # 좌표를 하나만 줬으면 '지역 이름을 주세요' 보다 '둘 다 주세요' 가 맞는 안내라 먼저 본다
    require_korea(lat, lng)
    if query is None and (lat is None or lng is None):
        raise typer.BadParameter('지역 이름 또는 --lat/--lng 를 주세요', param_hint='QUERY')


search_app = typer.Typer(
    help=(
        '직방 장소 후보(locations)와 매물 찾기: 원룸·오피스텔·빌라(room), 아파트(apt), 상가·사무실(store), 단기임대 서비스(stay). '
        '상세는 결과의 id 로 jibsa zigbang listing <id>'
    ),
    no_args_is_help=True,
)
app.add_typer(search_app, name='search')


listings_app = typer.Typer(help='매물 유형별 검색 또는 --complex로 단지 매물 검색', invoke_without_command=True)
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
        regions, complexes = search_regions_and_complexes(client, query)
        items = regions[:limit]
        complexes = complexes[:limit]
        emit(
            {
                'query': query,
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
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='확인할 가까운 매물 수 (제외 전)')] = 15,
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
    without_random: Annotated[
        bool, typer.Option('--without-random', help='오피스텔 서버의 무작위 섞기 해제. 검색 결과는 거리순 유지'),
    ] = False,
    pretty: PrettyOption = None,
) -> None:
    """원룸·오피스텔·빌라를 검색 중심에서 가까운 순으로 조회한다. 모든 조건은 직방 서버에서 거른다.

    동 이름을 주고 --radius 를 주지 않으면 반경 대신 그 동 경계 안의 매물을 동 중심에서 가까운 순으로 준다.
    역·학교 이름, 구·시 이름, --lat/--lng, --radius 는 반경 검색이다.
    역으로 식별된 검색은 역 전용 API 를 사용하고 반경 밖 매물은 포함하지 않는다.

    예: jibsa zigbang search listings room 역삼동 -t 원룸 --trade 월세 --deposit-max 1000 --rent-max 70
        jibsa zigbang search listings room 역삼동 -t 빌라,오피스텔 --room 투룸 --trade 전세 --condition 전세대출,엘리베이터
        jibsa zigbang search listings room 신림역 --floor 지상 --option 에어컨,세탁기 --manage-cost-max 10
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
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
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type')
    if without_random:
        with handle_errors(SOURCE):
            check_without_random(property_types or list(PROPERTY_TYPES))
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, TRADE_TYPES, '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
    )
    room_types = split_csv(room, ROOM_TYPES, '--room')
    floors = split_csv(floor, FLOOR_FILTERS, '--floor')
    options = split_csv(option, OPTION_FILTERS, '--option')
    extra_conditions = split_csv(condition, CONDITIONS, '--condition')
    skipped_types = unsearchable_types(property_types, trade_types)
    if skipped_types:
        trade_notes.append(unsearchable_note(skipped_types))
    if '단기임대' in trade_types:
        trade_notes.append(STAY_SERVICE_NOTE)

    with handle_errors(SOURCE), ZigbangClient() as client:
        conditions = ZigbangRoomConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            room_types=room_types,
            manage_cost_min=manage_cost_min,
            manage_cost_max=manage_cost_max,
            no_manage_cost=no_manage_cost,
            area_min_m2=area_min,
            area_max_m2=area_max,
            area_min_pyeong=area_pyeong_min,
            area_max_pyeong=area_pyeong_max,
            floors=floors,
            bathroom_count=bathroom,
            options=options,
            extra_conditions=extra_conditions,
            without_random=without_random,
        )
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
        )
        emit(result, pretty, notice=True, notes=trade_notes + notes + result.notes)


@listings_app.command('apt')
def search_apt_command(
    query: Annotated[
        str | None,
        typer.Argument(help='동·구 이름 (예: 역삼동, 강남구) 또는 역 이름 (예: 강남역). --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[
        float | None,
        typer.Option(
            min=0.1,
            max=APT_NEAR_MAX_RADIUS_KM,
            help=f'반경 (km, 최대 {APT_NEAR_MAX_RADIUS_KM:g}). 주면 동·구 전체 대신 반경 안 단지를 가까운 순으로 훑는다. 역 이름·좌표면 기본 {DEFAULT_RADIUS_KM:g}km',
        ),
    ] = None,
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
        float | None, typer.Option(min=0, help='공급면적 하한 (㎡). 동·구는 서버에서, 반경 검색은 받은 뒤 거른다'),
    ] = None,
    supply_area_max: Annotated[
        float | None, typer.Option(min=0, help='공급면적 상한 (㎡). 동·구는 서버에서, 반경 검색은 받은 뒤 거른다'),
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """아파트 매물. 동·구 이름이면 그 동·구 전체(직방 목록 순, 거리 없음), 역 이름·좌표·--radius 면 반경 검색.

    반경 검색은 반경 안 단지를 가까운 순으로 단지마다 조회해(단지당 요청 1회, 최대 30곳) 느리고 요청이 많다.
    결과는 같은 호·거래 유형의 매물을 묶은 것이다 (listing_count). 상세는 결과의 id 로 jibsa zigbang listing <id>.

    예: jibsa zigbang search listings apt 강남구 --trade 매매 --price-max 200000
        jibsa zigbang search listings apt 역삼동 --trade 전세 --area-min 59
        jibsa zigbang search listings apt 강남역 --radius 1 --trade 전세
        jibsa zigbang search listings apt 역삼동 --supply-area-min 80 --supply-area-max 110
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
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
        )
        notes: list[str] = []
        items = None
        if lat is None and radius is None:
            # 동·구 이름이면 그 동·구 전체를 준다. 동·구가 아니면(역 등) 반경으로 찾는데, 지역 검색 결과는 다시 쓴다
            items = search_regions(client, query or '')
            try:
                district, notes, extra = resolve_apt_region(client, query or '', items=items)
            except RegionNotFoundError:
                notes = [f"{quoted(query or '', '은/는')} 동·구가 아니라 그 위치에서 반경 {DEFAULT_RADIUS_KM:g}km 안 아파트를 찾았습니다"]
            else:
                result = search_apt_listings(client, district, conditions=conditions, limit=limit, extra_regions=extra)
                emit(result, pretty, notice=True, notes=trade_notes + notes + result.notes)
                return
        radius_km = radius or DEFAULT_RADIUS_KM
        region, region_notes = _region(client, query, lat, lng, radius_km, items)
        near = search_apt_listings_near(client, region, conditions=conditions, radius_km=radius_km, limit=limit)
        emit(near, pretty, notice=True, notes=trade_notes + region_notes + notes + near.notes)


def _require_complex_id(complex_id: str, param_hint: str = 'COMPLEX_ID') -> None:
    if COMPLEX_ID_PATTERN.match(complex_id.strip()) is None:
        raise typer.BadParameter(
            f"직방 단지 ID 형식이 아닙니다: '{complex_id}'. jibsa zigbang search locations <단지 이름> 결과의 "
            "complex_id 를 그대로 주세요 (예: apt-68579, officetel-20227)",
            param_hint=param_hint,
        )


ComplexIdArgument = Annotated[
    str,
    typer.Argument(help='단지 ID. search locations 결과의 complexes[].complex_id 나 search 결과의 complex_id (예: apt-68579, officetel-20227)'),
]


@app.command('complex')
def complex_command(
    complex_id: ComplexIdArgument,
    pretty: PrettyOption = None,
) -> None:
    """단지 정보와 지금 올라온 매물 수. 아파트는 거래 유형별 매물 수와 평형 목록(search listings --complex --pyeong 값)도 준다.

    예: jibsa zigbang complex apt-68579
    """
    _require_complex_id(complex_id)
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_complex(client, complex_id.strip())
        emit(result, pretty, notes=result.notes)


@listings_app.callback()
def complex_listings_command(
    ctx: typer.Context,
    complex_id: Annotated[str | None, typer.Option('--complex', help='아파트·오피스텔 단지 ID (apt-… / officetel-…)')] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 전세, 월세, 매매, 단기임대(오피스텔만). 반복하거나 쉼표로 구분. 기본 전체')
    ] = None,
    pyeong: Annotated[
        list[int] | None,
        typer.Option('--pyeong', min=1, help='평형 ID (complex 결과의 pyeongs[].id, 아파트만). 반복 가능 (OR)')
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
    without_random: Annotated[
        bool, typer.Option('--without-random', help='오피스텔 서버의 무작위 섞기 해제. 서버 목록 순으로 반환'),
    ] = False,
    pretty: PrettyOption = None,
) -> None:
    """단지 하나의 매물 목록 (직방 목록 순, 거리가 없다). 조건은 직방 서버에서 거른다.

    상세는 결과의 id 로 jibsa zigbang listing <id>.

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
    if limit is None:
        limit = 15 if complex_id.strip().startswith('officetel-') else 20
    room_types = split_csv(room, ROOM_TYPES, '--room')
    floors = split_csv(floor, FLOOR_FILTERS, '--floor')
    options = split_csv(option, OPTION_FILTERS, '--option')
    extra_conditions = split_csv(condition, CONDITIONS, '--condition')
    if no_manage_cost and (manage_cost_min is not None or manage_cost_max is not None):
        raise typer.BadParameter('--no-manage-cost 는 관리비 범위와 함께 쓸 수 없습니다', param_hint='--no-manage-cost')
    validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
        ('manage-cost', manage_cost_min, manage_cost_max),
        ('area', area_min, area_max),
        ('area-pyeong', area_pyeong_min, area_pyeong_max),
    )
    has_building_filters = (
        any(value is not None for value in (manage_cost_min, manage_cost_max, area_min, area_max, area_pyeong_min, area_pyeong_max, bathroom))
        or no_manage_cost or room_types or floors or options or extra_conditions
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
        apt_trade_notes.append(f"아파트 단지에는 단기임대가 없어 {'·'.join(given_trades)}만 찾았습니다")
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
        conditions = ZigbangRoomConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            room_types=room_types,
            manage_cost_min=manage_cost_min,
            manage_cost_max=manage_cost_max,
            no_manage_cost=no_manage_cost,
            area_min_m2=area_min,
            area_max_m2=area_max,
            area_min_pyeong=area_pyeong_min,
            area_max_pyeong=area_pyeong_max,
            floors=floors,
            bathroom_count=bathroom,
            options=options,
            extra_conditions=extra_conditions,
            without_random=without_random,
        )
        result = list_complex_listings(
            client,
            complex_id.strip(),
            conditions=conditions,
            pyeong_ids=pyeong,
            limit=limit,
        )
        emit(result, pretty, notice=True, notes=trade_notes + result.notes)


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
                '대분류는 휴게음식점, 일반음식/주류점, 스포츠/마사지/오락, 판매업, 기타'
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
    pretty: PrettyOption = None,
) -> None:
    """상가·사무실을 검색 중심에서 가까운 순으로 조회한다. 가격은 요약을 받은 뒤 거른다. 모르는 금액은 제외한다.

    상세는 결과의 id(store-123) 로 jibsa zigbang listing <id>.

    예: jibsa zigbang search listings store 성수동 --trade 임대 --first-floor --business 카페/커피
        jibsa zigbang search listings store 강남역 --area-min 66 --radius 0.5
    """
    _require_center(query, lat, lng)
    require_finite('--radius', radius)
    if trade is not None and trade not in STORE_TRADE_TYPES:
        raise typer.BadParameter(
            f"허용되지 않는 값입니다: '{trade}'. 가능한 값: {', '.join(STORE_TRADE_TYPES)}",
            param_hint='--trade',
        )
    # 금액 범위는 store_price_trade 가 거꾸로 된 범위를 거절한다. 면적은 float 이라 inf 가 typer 의 min=0 을 통과해
    # 요청 JSON 인코딩에서 PARSE_ERROR 로 끝났다 (2026-10-11 실측: --area-min inf). 상한이 '미만' 이라 같은 값도 막아야 해서
    # validate_ranges(min > max 만 거절) 대신 유한한지만 보고 범위는 아래 검사 하나로 본다
    require_finite('--area-min', area_min)
    require_finite('--area-max', area_max)
    if area_min is not None and area_max is not None and area_min >= area_max:
        raise typer.BadParameter('--area-max 는 --area-min 보다 커야 합니다', param_hint='--area-max')
    with handle_errors(SOURCE):
        effective_trade = store_price_trade(trade or '전체', {
            'deposit_manwon': (deposit_min, deposit_max),
            'rent_manwon': (rent_min, rent_max),
            'price_manwon': (price_min, price_max),
            'manage_cost_manwon': (manage_cost_min, manage_cost_max),
            'key_money_manwon': (key_money_min, key_money_max),
        })
    price_notes = []
    if trade is None and effective_trade != '전체':
        price_notes.append(f'가격 조건에 맞춰 거래 유형을 {effective_trade}로 좁혔습니다')
    businesses = split_csv(business, STORE_BUSINESS_NAMES, '--business')
    with handle_errors(SOURCE), ZigbangClient() as client:
        region, notes, boundary, radius_km = _scope(client, query, lat, lng, radius, STORE_GEOHASH_PRECISION)
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
            boundary=boundary,
            limit=limit,
        )
        emit(result, pretty, notice=True, notes=price_notes + notes + result.notes)


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
        typer.Option(min=0.1, max=MAX_RADIUS_KM, help='검색 반경 (km, 기본 1). 동·구 이름에 지역 전체, 역·학교·좌표는 반경 검색'),
    ] = None,
    sort: Annotated[
        str,
        typer.Option('--sort', help='distance 가까운 순 (기본), price 주당 임대료+관리비 낮은 순, newest 최근 등록순'),
    ] = 'distance',
    limit: LimitOption = 15,
    pretty: PrettyOption = None,
) -> None:
    """직방 단기임대(주 단위 계약) 매물을 거리·가격·최근 등록 순으로 조회한다. 금액은 주당 만원.

    원룸·빌라의 '단기임대' 거래(search room --trade 단기임대)와 다른 별도 서비스다. 매물은 직방 앱에서만 열린다.
    상세는 결과의 id(stay-123) 로 jibsa zigbang listing <id>.

    예: jibsa zigbang search listings stay 강남역 --weekly-rent-max 50 --building 오피스텔 --option 세탁기,와이파이
        jibsa zigbang search listings stay 역삼동 --check-in 2026-11-01 --check-out 2026-11-28 --rooms 1
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
    if structure is not None and structure not in STAY_STRUCTURES:
        raise typer.BadParameter(
            f"허용되지 않는 값입니다: '{structure}'. 가능한 값: {', '.join(STAY_STRUCTURES)}",
            param_hint='--structure',
        )
    buildings = split_csv(building, tuple(STAY_BUILDING_TYPE_BY_LABEL), '--building')
    discounts = split_csv(discount, tuple(STAY_DISCOUNT_TYPE_BY_LABEL), '--discount')
    options = split_csv(option, tuple(STAY_OPTION_BY_LABEL), '--option')
    floors = split_csv(floor, tuple(STAY_FLOOR_TYPE_BY_LABEL), '--floor')
    with handle_errors(SOURCE), ZigbangClient() as client:
        radius_km = radius or DEFAULT_RADIUS_KM
        split: list[ZigbangRegion] = []
        gus: list[ZigbangRegion] = []
        split_note: str | None = None
        items: list[ZigbangSearchItemModel] | None = None
        if lat is not None and lng is not None:
            region, notes = _region(client, query, lat, lng, radius_km)
        else:
            items = search_regions(client, query or '')
            region, notes, split_note, split = resolve_region_scope(client, query or '', items=items)
            gus = city_gu_regions(query or '', items)
        whole_address = lat is None and radius is None and region.search_type == 'address' and bool(region.local1)
        extra: list[ZigbangRegion] = []
        if whole_address and split:
            # '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)은 각 동을 지역 전체로 찾아 합친다.
            # 가까운 순은 동 중심들의 가운데에서 잰다
            extra = [part for part in split if part.name != region.name]
            region = merged_dong_region(region, split)
            split_note = None
        elif whole_address and gus:
            # 구가 있는 시(성남시)는 직방 지역 검색이 시 대신 구들을 줘서 첫 구만 찾으면 나머지 구가 빠진다 (2026-10-11 실측:
            # 분당구 35건만 찾고 수정구 등이 빠짐). 아파트처럼 구마다 지역 검색을 불러 합친다
            extra = [part for part in gus if part.name != region.name]
            region = merged_gu_region(region, gus)
        if split_note:
            notes.append(split_note)
        if whole_address and is_ri_code(region.legal_division_code) and region.local3:
            # 직방 지역 결과에는 리가 없고 local3 이 그 위 읍·면이라 검색 API 가 읍·면 전체를 준다 (2026-10-11 실측: 양근리 →
            # 양평읍 창대리 매물)
            notes.append(
                f"{quoted(region.name, '은/는')} 리 단위라 직방 단기임대 지역 검색이 상위 {region.local3} 전체를 찾았습니다. "
                '리 주변만 보려면 --radius 를 주세요'
            )
        elif whole_address:
            notes.append(f'반경 대신 {region.name} 지역 전체를 검색했습니다. 반경으로 찾으려면 --radius 를 주세요')
        boundary = dong_boundary(client, region) if lat is None and radius is None and not whole_address else None
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
                use_search_api=lat is None,
                whole_address=whole_address,
                extra_regions=extra,
                boundary=boundary,
            )
        except RegionNotFoundError:
            if not whole_address:
                raise
            # 세종의 동은 단기임대 지역 검색이 찾지 못한다 (_stay_region_search). room·store 처럼 동 경계(넓거나 없으면 반경)
            # 안 지도 칸으로 다시 찾는다
            missing = region.address or region.name
            region, notes, boundary, radius_km = _scope(client, query, lat, lng, radius, STAY_GEOHASH_PRECISION, items=items)
            notes.insert(0, f"직방 단기임대 지역 검색이 {missing}{particle(missing, '을/를')} 찾지 못해 지역 전체 대신 지도로 찾았습니다")
            result = search_stay_listings(
                client, region, conditions=conditions, sort=stay_sort, radius_km=radius_km, limit=limit, boundary=boundary,
            )
        emit(result, pretty, notice=True, notes=notes + result.notes)


@app.command('real-price')
def real_price_command(
    complex_id: Annotated[
        str,
        typer.Argument(help='아파트 단지 ID (search locations 결과의 complexes[].complex_id, search listings apt·listing의 complex_id, 예: apt-68579)'),
    ],
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세 중 하나')] = '매매',
    pyeong: Annotated[
        int | None,
        typer.Option('--pyeong', min=1, help='평형 ID (complex 결과의 pyeongs[].id). 기본 전체 평형')
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """아파트 단지 실거래가 (국토부 신고 기준, 최근 계약 순). cancelled: true 는 해제된 거래.

    예: jibsa zigbang real-price apt-68579 --trade 매매
        jibsa zigbang real-price apt-68579 --trade 전세 --pyeong 400085 --limit 10
    """
    _require_complex_id(complex_id)
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    with handle_errors(SOURCE), ZigbangClient() as client:
        result = get_real_prices(client, complex_id.strip(), trade_type=trade_types[0], pyeong_id=pyeong, limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('listing')
def listing_command(
    item_id: Annotated[
        str,
        typer.Argument(help="직방 매물 ID. 검색 결과의 id 그대로 (search 는 숫자, store 는 'store-123', stay 는 'stay-123', 아파트 제휴 매물은 'coalition-123')")
    ],
    check_in: Annotated[
        str | None,
        typer.Option(help='단기임대(stay-…)만: 입주일 (YYYY-MM-DD). --check-out 과 함께 주면 기간 비용·예약 가능 여부를 붙인다')
    ] = None,
    check_out: Annotated[str | None, typer.Option(help='단기임대(stay-…)만: 마지막으로 머무는 날 (YYYY-MM-DD). 직방은 이 날까지 이용일로 센다 (1주 = 11-02~11-08). --check-in 과 함께')] = None,
    pet: Annotated[bool, typer.Option('--pet', help='단기임대(stay-…)만: 반려동물 동반 (기간 비용에 반려동물 청소비가 붙는다)')] = False,
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (옵션·관리비·입주일·주차). 사진·상세 설명·문의는 url 의 원 사이트에서.

    단기임대는 --check-in/--check-out 을 주면 그 기간의 총비용과 예약이 비어 있는지(period_cost)도 준다.

    예: jibsa zigbang listing stay-3783 --check-in 2026-11-02 --check-out 2026-11-29
    """
    if LISTING_ID_PATTERN.match(item_id.strip()) is None:
        raise typer.BadParameter(
            f"직방 매물 ID 형식이 아닙니다: '{item_id}'. 검색 결과의 id 를 그대로 주세요 (예: 12345, store-123, stay-123, coalition-123)",
            param_hint='ITEM_ID',
        )
    if (check_in is None) != (check_out is None):
        raise typer.BadParameter('--check-in 과 --check-out 은 함께 주세요', param_hint='--check-in')
    if pet and check_in is None:
        raise typer.BadParameter('--pet 은 --check-in/--check-out 과 함께 주세요', param_hint='--pet')
    if item_id.strip().startswith('stay-') and check_in is not None and check_out is not None:
        with handle_errors(SOURCE):
            ZigbangGuestItemsPriceCalculationRequestPayloadModel(
                item_id=int(item_id.strip().removeprefix('stay-')),
                check_in_date=check_in, check_out_date=check_out, has_pet=pet,
            )
    with handle_errors(SOURCE), ZigbangClient() as client:
        emit(
            get_any_listing(client, item_id, check_in=check_in, check_out=check_out, pet=pet),
            pretty,
            notice=True,
        )
