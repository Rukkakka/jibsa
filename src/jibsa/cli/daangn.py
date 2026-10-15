import logging
from collections.abc import Callable

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
from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
    UnsupportedRegionError,
)
from jibsa.core.geo import DEFAULT_RADIUS_KM
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.korean import quoted
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
    OPTION_FILTER_BY_LABEL,
    OPTIONAL_LOOKUP_ERRORS,
    PRICE_TREND_MAX_YEARS,
    PROPERTY_TYPES,
    REAL_PRICE_TRADE_TYPES,
    ROOM_COUNT_FILTER_BY_LABEL,
    STRUCTURE_FILTER_BY_LABEL,
    TRADE_TYPES,
    DaangnListingConditions,
    FeedQueryRejectedError,
)
from jibsa.providers.daangn.service.commute import search_commute
from jibsa.providers.daangn.service.compare import (
    NEARBY_COMPLEXES_MAX,
    compare_complexes,
    list_nearby_complexes,
)
from jibsa.providers.daangn.service.complex import (
    COMPLEX_SORT_BY_LABEL,
    DaangnComplexConditions,
    get_complex,
    list_complex_listings,
    list_region_complexes,
    list_trending_complexes,
    search_complexes,
)
from jibsa.providers.daangn.service.development import (
    DEVELOPMENT_CATEGORY_BY_LABEL,
    DEVELOPMENT_MAX_LIMIT,
    get_development,
    list_developments,
)
from jibsa.providers.daangn.service.listing import get_listing
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
    REAL_PRICE_MAX_LIMIT,
    REALSALE_SORT_BY_LABEL,
    DaangnRealPriceBaseResult,
    get_listing_real_prices,
    get_price_trend,
    get_real_prices,
    get_region_real_prices,
)
from jibsa.providers.daangn.service.region import (
    find_address,
    find_place,
    find_station,
    map_query_rejected_error,
    region_by_coordinate,
    resolve_regions,
    same_station_notes,
    search_locations,
)
from jibsa.providers.daangn.service.review import get_region_reviews
from jibsa.providers.daangn.service.school import (
    COMPARE_MAX_COMPLEXES,
    PRESCHOOL_MAX_LIMIT,
    PRESCHOOL_TYPE_BY_LABEL,
    get_preschool,
    get_school,
    list_preschools,
)
from jibsa.providers.daangn.service.search import (
    property_type_notes,
    search_area,
    search_listings,
    search_station,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.service.region import (
    resolve_region_with_notes as resolve_naver_region,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.service.common import ZigbangRegion
from jibsa.providers.zigbang.service.region import (
    geocoding_failed,
    resolve_region_with_notes,
)

from typing import Annotated


logger = logging.getLogger(__name__)


SOURCE: str = 'daangn'
# 직방 지역 검색이 이렇게 실패하면 네이버로 넘긴다: 요청 제한과 세 소스 공통 범위(서버 오류·네트워크·응답 형식).
# 직방이 찾지 못한 이름(REGION_NOT_FOUND)은 넘기지 않는다
GEOCODE_FALLBACK_ERRORS: tuple[type[Exception], ...] = (RateLimitedError, *OPTIONAL_LOOKUP_BASE_ERRORS)

app = typer.Typer(
    help=(
        '당근부동산: 동 단위 최근 매물 또는 좌표 반경 매물 (직거래 포함, 로그인 불필요, 금액은 만원). '
        '조건은 당근 웹 지도 필터와 같고 당근 서버에서 건다'
    ),
    no_args_is_help=True,
)

search_app = typer.Typer(help='매물·지역·단지·통근 검색', no_args_is_help=True)
app.add_typer(search_app, name='search')

LatOption = Annotated[float | None, typer.Option(help='중심 위도 (동 이름 대신)')]
LngOption = Annotated[float | None, typer.Option(help='중심 경도 (동 이름 대신)')]

# 매물 조건 옵션. search listings(--complex 포함)·search commute 가 같이 쓴다 (_listing_conditions)
PropertyTypeOption = Annotated[
    list[str] | None,
    typer.Option('--type', '-t', help=f"{', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 전체. 투룸은 투룸 이상 (쓰리룸·포룸 포함)"),
]
TradeOption = Annotated[list[str] | None, typer.Option('--trade', help='매매, 전세, 월세, 단기임대. 기본 전체')]
WithManageCostOption = Annotated[
    bool,
    typer.Option('--with-manage-cost', help='월세 범위를 월세 + 관리비로 비교 (당근 "관리비 포함")'),
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
# 매물 검색의 목록 옵션에 없는 값을 이 명령에서 주는 법 (split_csv 의 에러 힌트). 이 명령의 다른 옵션 값과, 뜻이 같은
# 다른 소스 표현이다 (직방 --condition 반려동물·전세대출·주차·즉시입주, --room 오픈형원룸·투룸, --floor 옥탑방)
LISTING_USAGE_BY_VALUE: dict[str, str] = {
    **{value: f'--floor {value}' for value in FLOOR_FILTER_BY_LABEL},
    **{value: f'--room-count {value}' for value in ROOM_COUNT_FILTER_BY_LABEL},
    **{value: f'--structure {value}' for value in STRUCTURE_FILTER_BY_LABEL},
    **{value: f'--option {value}' for value in OPTION_FILTER_BY_LABEL},
    '반려동물': '--option 반려동물가능',
    '전세대출': '--option 대출가능',
    '주차': '--option 주차가능',
    '옥탑방': '--option 옥탑',
    '복층형원룸': '--option 복층',
    '오픈형원룸': '--structure 오픈형',
    '분리형원룸': '--structure 분리형',
    '투룸': '--room-count 2개',
    '쓰리룸': '--room-count 3개',
    '포룸이상': '--room-count 4개이상',
    '즉시입주': '--move-in-now',
    '바로입주': '--move-in-now',
}
# 아파트 단지 조건. 단지 하나를 보는 --complex 와는 함께 쓸 수 없다
HouseholdMinOption = Annotated[int | None, typer.Option(min=0, help='단지 세대수 하한 (-t 아파트 만 줄 때)')]
HouseholdMaxOption = Annotated[int | None, typer.Option(min=0, help='단지 세대수 상한 (-t 아파트 만 줄 때)')]
ParkingMinOption = Annotated[float | None, typer.Option(min=0, help='세대당 주차대수 하한 (-t 아파트 만 줄 때)')]


def _require_one_place(name: str | None, lat: float | None, lng: float | None, param_hint: str) -> None:
    """동 이름과 좌표 중 정확히 하나를 받는다. 둘 다 주면 어느 쪽으로 찾았는지 헷갈린다."""
    require_korea(lat, lng)
    has_coordinate = lat is not None and lng is not None
    if name is None and not has_coordinate:
        raise typer.BadParameter('동 이름 또는 --lat/--lng 를 주세요', param_hint=param_hint)
    if name is not None and has_coordinate:
        raise typer.BadParameter('동 이름과 --lat/--lng 는 함께 줄 수 없습니다. 하나만 주세요', param_hint=param_hint)


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
    household_min: int | None = None,
    household_max: int | None = None,
    parking_min: float | None = None,
) -> tuple[DaangnListingConditions, list[str]]:
    """매물 검색 옵션(search listings·commute·--complex 공통)을 검색 조건 묶음으로 바꾼다.

    거래 유형을 금액 조건으로 짐작한 안내와 매물 종류 안내를 함께 돌려준다. 조건 조합이 잘못되면 묶음을
    만들 때 ValidationError 가 나므로 `handle_errors` 안에서 부른다.

    Raises:
        typer.BadParameter: 모르는 라벨이거나 사용승인일·거래 방식을 둘 이상 줬을 때.
    """
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type')
    trade_types, trade_notes = infer_trade_types(
        split_csv(trade, TRADE_TYPES, '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
    )
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
        price_min=price_min,
        price_max=price_max,
        rent_includes_manage_cost=with_manage_cost,
        area_min=area_min,
        area_max=area_max,
        floors=split_csv(floor, tuple(FLOOR_FILTER_BY_LABEL), '--floor', LISTING_USAGE_BY_VALUE),
        room_counts=split_csv(room_count, tuple(ROOM_COUNT_FILTER_BY_LABEL), '--room-count', LISTING_USAGE_BY_VALUE),
        structures=split_csv(structure, tuple(STRUCTURE_FILTER_BY_LABEL), '--structure', LISTING_USAGE_BY_VALUE),
        building_approval=approvals[0] if approvals else None,
        deal=deals[0] if deals else None,
        options=split_csv(option, tuple(OPTION_FILTER_BY_LABEL), '--option', LISTING_USAGE_BY_VALUE),
        move_in_now=move_in_now,
        household_min=household_min,
        household_max=household_max,
        parking_min=parking_min,
    )
    return conditions, trade_notes + property_type_notes(property_types, conditions.structures)


def _geocode(name: str, radius_km: float, *, check_station: bool = True) -> tuple[ZigbangRegion, list[str], str]:
    """지역·역 이름을 좌표로 바꾼다. 당근 역·주소 검색(`find_place`)을 먼저 쓰고, 당근이 확실히 찾지 못한
    이름(동·구, 대학교 같은 장소)은 직방 지역 검색으로, 직방이 막히거나 실패했을 때(서버 오류·네트워크·응답 형식)만
    네이버 검색창 자동완성으로 찾는다.
    부르는 쪽이 역 검색을 이미 했으면(`check_station=False`) 같은 요청을 다시 보내지 않고 주소 검색(`find_address`)만 한다.
    클라이언트를 받지 않고 직접 여는 것은 `_center`(developments·preschools)가 클라이언트를 열기 전에 부르기 때문이다.
    요청 수는 같다.

    당근 검색이 실패하면(요청 제한·쿼리 변경 포함) 직방으로 넘어간다. 네이버를 기본으로 쓰지 않는 것은
    대학교를 못 찾고 요청 제한이 더 빡빡해서다 (2026-10-09 실측: 역·동은 두 곳이 같은 위치,
    서울대학교·연세대학교는 네이버가 못 찾음). 주소가 여러 시·군·구에 맞으면 직방으로 넘기지 않고 에러를
    낸다. 직방은 주소를 찾지 못해 '찾지 못했다' 로 바뀌기 때문이다 (2026-10-10 실측: 테헤란로 152 도 못 찾음).

    Returns:
        (검색 중심, 안내, 위치를 찾은 곳 '당근', '직방' 또는 '네이버').

    Raises:
        RegionAmbiguousError: 당근 주소 검색에서 주소가 여러 시·군·구에 맞을 때 (`find_place`).
        RegionNotFoundError: 직방이 찾지 못했을 때.
        RateLimitedError: 직방이 막혔는데 네이버도 막혔거나 실패했거나 찾지 못했을 때 (`source` 는 zigbang, `geocoding_failed`).
        JibsaError: 직방이 그 밖의 이유로 실패했는데 네이버로도 찾지 못했을 때 (UPSTREAM_ERROR, `source` 는 zigbang).
    """
    try:
        with DaangnClient() as client:
            place = find_place(client, name) if check_station else find_address(client, name)
    except RegionAmbiguousError:
        raise
    except OPTIONAL_LOOKUP_ERRORS as exc:
        place = None
        logger.warning('daangn place search for %r failed (%s); falling back to zigbang', name, exc)
    if place is not None:
        return ZigbangRegion(name=place.name, address=place.name, lat=place.lat, lng=place.lng), place.notes, '당근'
    try:
        with ZigbangClient() as client:
            region, notes = resolve_region_with_notes(client, name, radius_km=radius_km)
            return region, notes, '직방'
    except GEOCODE_FALLBACK_ERRORS as exc:
        zigbang_error: Exception = exc
        logger.warning('zigbang region search for %r failed (%s); falling back to naver', name, exc)
    try:
        with NaverClient() as geocoder:
            found, notes = resolve_naver_region(geocoder, name, radius_km)
    except GEOCODE_FALLBACK_ERRORS as exc:
        raise geocoding_failed(zigbang_error, exc) from None
    except RegionNotFoundError as exc:
        raise geocoding_failed(zigbang_error, exc) from None
    reason = '요청 제한으로 막혀 있어' if isinstance(zigbang_error, RateLimitedError) else '지역 검색이 실패해'
    notes = [f"직방이 {reason} '{name}' 위치를 네이버 지역 검색으로 찾았습니다", *notes]
    # 직방 검색 중심과 필드가 같다
    return ZigbangRegion(**found.model_dump()), notes, '네이버'


@search_app.command('locations')
def region_command(
    keyword: Annotated[
        str | None,
        typer.Argument(help='동 이름 (예: 역삼동) 또는 단지 이름. 구 이름이면 그 구의 동 목록. --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    limit: Annotated[int, typer.Option(min=1, max=COMPLEX_LIST_MAX_LIMIT, help='최대 단지 후보 수 (지역 후보에는 적용하지 않음)')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """지역명이나 좌표를 당근 지역(시도/구/동)으로 바꾼다. 이름으로 찾으면 그 이름의 단지 후보(complexes)도 준다."""
    _require_one_place(keyword, lat, lng, 'KEYWORD')
    with handle_errors(SOURCE), DaangnClient() as client:
        if lat is not None and lng is not None:
            try:
                region = region_by_coordinate(client, lat, lng)
            except FeedQueryRejectedError:
                raise map_query_rejected_error() from None
            emit({'lat': lat, 'lng': lng, 'results': [region.model_dump()]}, pretty)
            return
        # 좌표가 없으면 _require_one_place 가 이름을 요구했다
        assert keyword is not None
        results = [
            {
                'name1': location.name1,
                'name2': location.name2,
                'name3': location.name3,
                'region_id': location.id,
            }
            for location in search_locations(client, keyword)
        ]
        notes: list[str] = []
        # 단지 검색이 실패해도 지역 결과와 받은 단지 후보는 돌려주고 notes 로 알린다 (search_complexes)
        complexes = [candidate.model_dump() for candidate in search_complexes(client, keyword, limit=limit, notes=notes)]
        emit({'keyword': keyword, 'results': results, 'complexes': complexes}, pretty, notes=notes)


def _search_not_dong(
    client: DaangnClient,
    dong: str,
    not_dong: JibsaError,
    *,
    city: str | None,
    expand: int,
    conditions: DaangnListingConditions,
    limit: int,
    radius_km: float,
    common_notes: list[str],
    pretty: bool | None,
    emit_area: Callable[[float, float, list[str]], None],
) -> None:
    """당근 동이 아닌 이름: 역이면 당근 역 주변 목록으로, 아니면(장소 이름) 그 위치의 반경으로 찾아 내보낸다.

    Raises:
        JibsaError: 위치도 찾지 못하면 `not_dong` (동을 찾지 못한 원래 에러).
    """
    if expand:
        # --expand 는 동 검색에만 쓴다. 역·장소 이름도 여기로 와서, 동 이름을 쓰라는 원래 힌트 대신
        # 옵션을 빼라고 알린다 (2026-10-11 실측: '강남역 --expand 1' 이 동 이름으로 다시 찾으라는 힌트를 냈다)
        raise RegionNotFoundError(
            dong,
            hint=(
                f"--expand 는 동 이름으로 찾을 때만 씁니다. {quoted(dong, '이/가')} 역·장소 이름이면 --expand 를 빼고 다시 "
                "검색하세요. 동 후보는 'jibsa daangn search locations <이름>' 으로 확인할 수 있습니다"
            ),
        ) from None
    # 역 검색·역 주변 목록이 실패하면 위치 반경으로 넘어가고 notes 로 알린다. 요청 제한은 넘어가도
    # 위치 찾기·반경 검색이 같은 제한에 걸리므로 바로 올린다. --city 는 같은 이름의 역을 고르는 데 쓰고
    # (양평역: 경기 양평군·서울 영등포구), 반경 검색에는 쓸 수 없어 그때의 실패는 넘기지 않는다
    station_notes: list[str] = []
    try:
        station = find_station(client, dong, city=city)
    except RateLimitedError:
        raise
    except OPTIONAL_LOOKUP_ERRORS as exc:
        if city is not None:
            raise
        station = None
        station_notes.append(f"당근 역 검색이 실패해 {quoted(dong, '이/가')} 역인지 확인하지 못하고 위치 반경으로 찾았습니다")
        logger.warning('daangn station search failed (%s); searching by radius', exc)
    if station is None and city is not None:
        raise RegionNotFoundError(
            dong,
            hint=(
                f"--city 는 동·역 이름으로 찾을 때만 씁니다. {quoted(dong, '이/가')} 장소 이름이면 --city 를 빼고 다시 검색하세요. "
                "동 이름이면 --city 를 바꾸거나 빼 보세요. 동 후보는 'jibsa daangn search locations <이름>' 으로 "
                '확인할 수 있습니다'
            ),
        ) from None
    if station is not None:
        station_notes += same_station_notes(station, '다른 역이면 --city 로 시·도나 구를 지정하세요')
        try:
            station_result = search_station(client, station, conditions=conditions, limit=limit)
        except RateLimitedError:
            raise
        except OPTIONAL_LOOKUP_ERRORS as exc:
            station_notes.append(f'당근 {station.name} 주변 매물 목록 조회가 실패해 역 위치 반경으로 찾았습니다')
            logger.warning('daangn station listings failed (%s); searching by radius', exc)
        else:
            emit(station_result, pretty, notes=common_notes + [
                f"{quoted(dong, '은/는')} 당근 역 주변 매물 목록으로 찾았습니다 (walk_minutes 는 역까지 도보 분). "
                '역에서 반경으로 찾으려면 --radius 를 주세요'
            ] + station_notes + station_result.notes)
            return
        # 역은 찾았으니 위치를 다시 찾지 않고 역 위치를 중심으로 쓴다
        emit_area(station.lat, station.lng, station_notes + [
            f"당근에 {quoted(dong, '이라는/라는')} 동이 없어 당근 지역 검색으로 찾은 위치({station.name})에서 "
            f'반경 {radius_km:g}km 안을 찾았습니다'
        ])
        return
    try:
        # 역 검색은 위에서 했으므로 위치 찾기에서 다시 하지 않는다
        center, geocode_notes, finder = _geocode(dong, radius_km, check_station=False)
    except RegionNotFoundError:
        raise not_dong from None
    emit_area(center.lat, center.lng, station_notes + geocode_notes + [
        f"당근에 {quoted(dong, '이라는/라는')} 동이 없어 {finder} 지역 검색으로 찾은 위치({center.address or center.name})에서 "
        f'반경 {radius_km:g}km 안을 찾았습니다'
    ])


@search_app.command('listings')
def search_command(
    dong: Annotated[
        str | None,
        typer.Argument(help='동 이름 (예: 역삼동). 역 이름(예: 역삼역)이면 당근 역 주변 매물, 장소 이름이면 그 위치 반경으로 찾는다. --lat/--lng 를 주면 생략')
    ] = None,
    complex_id: Annotated[int | None, typer.Option('--complex', min=1, help='단지 ID. 지역·좌표 대신 해당 단지의 현재 매물 조회')] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[
        float | None,
        typer.Option(
            min=0.1,
            max=5.0,
            help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 주면 동 이름도 그 위치 반경으로 찾는다. 반경 안 매물이 모자라면 반경 밖 가까운 매물도 나온다',
        )
    ] = None,
    city: Annotated[
        str | None,
        typer.Option(help="동·역 이름이 여러 곳일 때 시/도나 구로 좁힘 (예: '강남구', '경기도'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다). 장소 이름·반경 검색에는 쓰지 않는다")
    ] = None,
    expand: Annotated[
        int,
        typer.Option(min=0, max=10, help='주변 동을 몇 개 더 조회할지. 당근 피드에 섞여 오는 주변 동부터 고르고 (구 경계를 넘을 수 있음), 모자라면 같은 구의 다른 동으로 채운다')
    ] = 0,
    property_type: PropertyTypeOption = None,
    trade: TradeOption = None,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
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
    pretty: PrettyOption = None,
) -> None:
    """동의 최근 매물, 또는 한 위치의 반경 안 매물을 조회한다. 조건은 당근 서버에서 건다.

    동 이름만 주면 동마다 조건에 맞는 최근 매물을 최대 120건 받아 최근 게시 순으로 준다 (주변 동
    매물이 섞여 온다). 역 이름(역삼역)이면 당근 웹의 역 주변 매물 목록을 역까지 도보 분(walk_minutes)과 함께 준다.
    --lat/--lng 나 --radius 를 주거나 장소 이름을 주면 당근 웹 지도처럼 그 위치의 반경 안 매물을 가까운 순으로
    준다. 이름은 당근 역·주소 검색으로, 못 찾으면 직방 지역 검색으로 좌표를 찾는다.

    예: jibsa daangn search listings 역삼동 --city 강남구 -t 원룸 --trade 월세 --deposit-max 1000 --rent-max 70 --option 반려동물가능
    예: jibsa daangn search listings 역삼역 --radius 0.5 -t 원룸 --trade 월세 --option 반려동물가능
    """
    require_finite('--radius', radius)
    require_finite('--parking-min', parking_min)
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
        ('household', household_min, household_max),
    )
    if complex_id is not None:
        if dong is not None or any(value is not None for value in (lat, lng, radius, city, household_min, household_max, parking_min)) or expand:
            raise typer.BadParameter('--complex는 지역·좌표·반경·주변 동·세대수·주차대수 조건과 함께 사용할 수 없습니다', param_hint='--complex')
    else:
        _require_one_place(dong, lat, lng, 'DONG')
    by_area = lat is not None or radius is not None
    if by_area and (city is not None or expand):
        raise typer.BadParameter('--city 와 --expand 는 동 단위로 찾을 때(--lat/--lng·--radius 없이)만 씁니다', param_hint='--city / --expand')
    radius_km = radius if radius is not None else DEFAULT_RADIUS_KM

    def emit_area(center_lat: float, center_lng: float, place_notes: list[str]) -> None:
        try:
            area_result = search_area(client, center_lat, center_lng, radius_km=radius_km, conditions=conditions, limit=limit)
        except FeedQueryRejectedError:
            raise map_query_rejected_error() from None
        emit(area_result, pretty, notes=common_notes + place_notes + area_result.notes)

    with handle_errors(SOURCE), DaangnClient() as client:
        conditions, common_notes = _listing_conditions(
            property_type=property_type, trade=trade,
            deposit_min=deposit_min, deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max,
            price_min=price_min, price_max=price_max, with_manage_cost=with_manage_cost,
            area_min=area_min, area_max=area_max, floor=floor, room_count=room_count,
            structure=structure, approval=approval, deal=deal, option=option, move_in_now=move_in_now,
            household_min=household_min, household_max=household_max, parking_min=parking_min,
        )
        if complex_id is not None:
            # 단지 하나의 현재 매물 (당근 단지 화면 순이라 거리가 없다)
            complex_result = list_complex_listings(client, complex_id, conditions=conditions, limit=limit)
            emit(complex_result, pretty, notes=common_notes + complex_result.notes)
            return
        if lat is not None and lng is not None:
            emit_area(lat, lng, [])
            return
        # _require_one_place 가 좌표가 없으면 동 이름을 요구했다
        assert dong is not None
        if by_area:
            center, geocode_notes, finder = _geocode(dong, radius_km)
            emit_area(center.lat, center.lng, geocode_notes + [
                f"{quoted(dong, '은/는')} {finder} 지역 검색으로 찾은 위치({center.address or center.name})를 중심으로 찾았습니다"
            ])
            return
        try:
            place_notes: list[str] = []
            regions = resolve_regions(client, dong, city=city, notes=place_notes, station_hint=True, merge_ga=True)
        except (RegionNotFoundError, UnsupportedRegionError) as not_dong:
            # 당근 동이 아닌 이름은 역이면 당근 역 주변 목록으로, 아니면(장소 이름) 그 위치의 반경으로 찾는다.
            # '리'로 끝나는 역 이름(미아사거리·굽은다리)도 리 단위 에러(ri_region_error) 대신 여기로 온다.
            # 위치도 못 찾으면 원래 에러
            _search_not_dong(
                client, dong, not_dong, city=city, expand=expand, conditions=conditions, limit=limit,
                radius_km=radius_km, common_notes=common_notes, pretty=pretty, emit_area=emit_area,
            )
            return
        result = search_listings(
            client, regions, query=dong, expand=expand, conditions=conditions, limit=limit, split_budget=len(regions) > 1,
        )
        emit(
            result,
            pretty,
            notes=common_notes + place_notes + result.notes,
        )


@app.command('listing')
def item_command(
    item_id: Annotated[int, typer.Argument(min=1, help='당근 매물 ID (search listings 결과의 id)')],
    trade: Annotated[
        str | None,
        typer.Option(
            '--trade',
            help='보여 줄 거래 조건: 매매, 전세, 월세, 단기임대. search listings 결과의 trade_type 을 넘기면 목록과 같은 가격이 나온다. 기본은 대표 조건',
        )
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (옵션·관리비·입주일·주차). 사진·상세 설명·문의는 url 의 원 사이트에서."""
    trade_type = split_csv([trade], TRADE_TYPES, '--trade') if trade is not None else []
    if len(trade_type) > 1:
        raise typer.BadParameter('거래 조건은 하나만 받습니다 (매매, 전세, 월세, 단기임대 중 하나)', param_hint='--trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        emit(get_listing(client, item_id, trade_type[0] if trade_type else None), pretty)


@app.command('complex')
def complex_command(
    complex_id: Annotated[
        int,
        typer.Argument(min=1, help='단지 ID (search locations <단지 이름> 의 complexes, 아파트·오피스텔 listing 의 complex_id)')
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
        typer.Argument(min=1, help='단지 ID (search locations <단지 이름> 의 complexes, 아파트·오피스텔 listing 의 complex_id). --item 을 주면 생략')
    ] = None,
    item: Annotated[
        int | None,
        typer.Option('--item', min=1, help='매물 ID. 단지 대신 그 매물이 있는 건물의 비슷한 면적 실거래를 본다')
    ] = None,
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세 중 하나')] = '매매',
    area: Annotated[
        int | None,
        typer.Option(min=1, help='전용면적 묶음 (complex 결과의 pyeongs[].area_group, 예: 84). 단지로 볼 때만. 기본 전체 평형')
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """단지 또는 매물 건물의 실거래가 (국토부 신고 기준, 최근 계약 순). cancelled: true 는 해제된 거래."""
    if (complex_id is None) == (item is None):
        raise typer.BadParameter('단지 ID 와 --item 중 하나만 주세요', param_hint='COMPLEX_ID / --item')
    if item is not None and area is not None:
        raise typer.BadParameter('--area 는 단지 ID 로 볼 때만 씁니다 (매물은 비슷한 면적 거래가 온다)', param_hint='--area')
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        result: DaangnRealPriceBaseResult
        if item is not None:
            result = get_listing_real_prices(client, item, trade_type=trade_types[0], limit=limit)
        else:
            # 위에서 단지 ID 와 --item 중 정확히 하나만 받았다
            assert complex_id is not None
            result = get_real_prices(client, complex_id, trade_type=trade_types[0], area_group=area, limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('region-real-price')
def region_real_price_command(
    region: Annotated[str, typer.Argument(help="동 이름(예: '역삼동') 또는 구 이름(예: '강남구', '수원시 장안구')")],
    city: Annotated[
        str | None,
        typer.Option(help="같은 이름이 여러 곳일 때 시/도나 구로 좁힘 (예: '서울', '대구광역시'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세 중 하나')] = '매매',
    new_high: Annotated[bool, typer.Option('--new-high', help='이전 최고가를 넘은 신고가 매매만 (가격 높은 순)')] = False,
    sort: Annotated[str, typer.Option('--sort', help='최신 (최근 공개 순) 또는 가격 (가격 높은 순, 매매만)')] = '최신',
    limit: Annotated[int, typer.Option(min=1, max=REAL_PRICE_MAX_LIMIT, help='최대 거래 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """동·구의 최근 실거래 또는 신고가 (국토부 신고 기준). 아파트 외에 빌라·오피스텔 거래도 섞인다."""
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    sorts = split_csv([sort], tuple(REALSALE_SORT_BY_LABEL), '--sort')
    if len(sorts) != 1:
        raise typer.BadParameter('정렬은 하나만 받습니다 (최신, 가격 중 하나)', param_hint='--sort')
    if new_high and trade_types[0] != '매매':
        raise typer.BadParameter('신고가는 매매만 있습니다', param_hint='--new-high / --trade')
    if sorts[0] == '가격' and trade_types[0] != '매매':
        # 당근이 전월세의 가격 순 정렬을 이유 없이 거절한다
        raise typer.BadParameter('가격 순 정렬은 매매만 됩니다', param_hint='--sort / --trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_region_real_prices(
            client,
            region,
            city=city,
            trade_type=trade_types[0],
            new_high=new_high,
            sort=sorts[0],
            limit=limit,
        )
        emit(result, pretty, notes=result.notes)


@search_app.command('commute')
def commute_command(
    workplace: Annotated[
        str | None,
        typer.Argument(help='회사 위치 (역·장소·동 이름, 당근 역·주소 검색으로, 못 찾으면 직방 지역 검색으로 좌표를 찾는다). --lat/--lng 를 주면 생략')
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
    limit: Annotated[int, typer.Option(min=1, max=COMMUTE_STATION_MAX_LIMIT, help='역당 최대 매물 수 (100건씩 페이지를 넘겨 받는다)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """회사까지 지하철로 갈 수 있는 역 주변 매물을 역별로 찾는다 (당근 웹 출퇴근 지도).

    회사에서 가장 가까운 역을 찾고, 그 역까지 --max-minutes 안에 오는 역들 중 가까운 역부터 최대 10곳의
    주변 매물을 모은다. 조건은 search listings 와 같고 당근 서버에서 건다.

    예: jibsa daangn search commute 강남역 --max-minutes 20 -t 원룸 --trade 월세 --rent-max 70
    """
    require_finite('--parking-min', parking_min)
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
        ('household', household_min, household_max),
    )
    _require_one_place(workplace, lat, lng, 'WORKPLACE')
    with handle_errors(SOURCE), DaangnClient() as client:
        conditions, notes = _listing_conditions(
            property_type=property_type, trade=trade,
            deposit_min=deposit_min, deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max,
            price_min=price_min, price_max=price_max, with_manage_cost=with_manage_cost,
            area_min=area_min, area_max=area_max, floor=floor, room_count=room_count,
            structure=structure, approval=approval, deal=deal, option=option, move_in_now=move_in_now,
            household_min=household_min, household_max=household_max, parking_min=parking_min,
        )
        if lat is None or lng is None:
            # _require_one_place 가 좌표가 없으면 이름을 요구했다
            assert workplace is not None
            center, geocode_notes, finder = _geocode(workplace, DEFAULT_RADIUS_KM)
            lat, lng = center.lat, center.lng
            notes += geocode_notes + [
                f"{quoted(workplace, '은/는')} {finder} 지역 검색으로 찾은 위치({center.address or center.name})를 회사 위치로 보았습니다"
            ]
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
                hint='jibsa daangn search listings <역 이름> --radius 1 로 역 주변을 찾으세요. jibsa 업데이트가 필요합니다',
            ) from None
        emit(result, pretty, notes=notes + result.notes)


@app.command('region-reviews')
def region_reviews_command(
    region: Annotated[str, typer.Argument(help="동 이름(예: '역삼동') 또는 구 이름(예: '강남구', '수원시 장안구')")],
    city: Annotated[
        str | None,
        typer.Option(help="같은 이름이 여러 곳일 때 시/도나 구로 좁힘 (예: '서울', '대구광역시'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    top: Annotated[int, typer.Option(min=1, max=20, help='후기 많은 단지 수')] = 10,
    pretty: PrettyOption = None,
) -> None:
    """동네 거주 후기가 있는지·몇 개인지와 후기 많은 단지. 후기 내용은 url 의 원 사이트에서."""
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_region_reviews(client, region, city=city, top=top)
        emit(result, pretty, notes=result.notes)


@search_app.command('complexes')
def complexes_command(
    region: Annotated[str, typer.Argument(help="동 이름(예: '역삼동') 또는 구 이름(예: '강남구', '수원시 장안구')")],
    city: Annotated[
        str | None,
        typer.Option(help="같은 이름이 여러 곳일 때 시/도나 구로 좁힘 (예: '서울', '대구광역시'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    complex_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(COMPLEX_TYPE_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분. 아파트는 주상복합 포함. 기본 전체")
    ] = None,
    trade: Annotated[
        str,
        typer.Option('--trade', help='매매, 전세, 월세 중 하나. 가격 조건과 단지마다 붙는 최근 실거래의 거래 유형')
    ] = '매매',
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
    """동·구의 단지 목록 (당근 지도 단지 탭). 세대수·가격·입주일 순으로 정렬하고, 조건은 당근 서버에서 건다.

    가격 조건은 지금 매물이 아니라 단지의 예전 실거래 가격 기준이다. 지금 매물은 search listings --complex <complex_id> 로 본다.

    예: jibsa daangn search complexes 역삼동 --city 강남구 -t 아파트 --sort 가격높은순 --household-min 500
    """
    require_finite('--parking-min', parking_min)
    validate_ranges(
        ('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max),
        ('price', price_min, price_max), ('area', area_min, area_max),
        ('household', household_min, household_max),
    )
    trade_types = split_csv([trade], REAL_PRICE_TRADE_TYPES, '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('거래 유형은 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    sorts = split_csv([sort], tuple(COMPLEX_SORT_BY_LABEL), '--sort')
    if len(sorts) != 1:
        raise typer.BadParameter(f"정렬은 하나만 받습니다 ({', '.join(COMPLEX_SORT_BY_LABEL)} 중 하나)", param_hint='--sort')
    approvals = split_csv([approval] if approval else None, tuple(BUILDING_APPROVAL_FILTER_BY_LABEL), '--approval')
    if len(approvals) > 1:
        raise typer.BadParameter('사용승인일은 하나만 받습니다', param_hint='--approval')
    trade_type = trade_types[0]
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
            trade_type=trade_type,
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
        result = list_region_complexes(client, region, city=city, conditions=conditions, sort=sorts[0], limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('school')
def school_command(
    name: Annotated[str, typer.Argument(help="학교 이름 (예: '역삼초등학교'. 일부만 줘도 된다)")],
    city: Annotated[
        str | None,
        typer.Option(help="같은 이름의 학교가 여러 곳일 때 주소로 좁힘 (예: '강남구', '서울'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    complex_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(COMPLEX_TYPE_FILTER_BY_LABEL)}. 반복하거나 쉼표로 구분. 아파트는 주상복합 포함. 기본 전체")
    ] = None,
    household_min: Annotated[int | None, typer.Option(min=0, help='세대수 하한 (소규모 빌라형 단지를 뺄 때)')] = None,
    limit: Annotated[int, typer.Option(min=1, max=COMPLEX_LIST_MAX_LIMIT, help='최대 단지 수')] = 120,
    pretty: PrettyOption = None,
) -> None:
    """학교 정보와 그 학교에 배정되는 단지 (초등학교만, 세대수 많은 순). 요청 2회.

    예: jibsa daangn school 역삼초등학교 --city 강남구 -t 아파트 --household-min 100
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_school(
            client,
            name,
            city=city,
            complex_types=split_csv(complex_type, tuple(COMPLEX_TYPE_FILTER_BY_LABEL), '--type'),
            household_min=household_min,
            limit=limit,
        )
        emit(result, pretty, notes=result.notes)


@app.command('price-trend')
def price_trend_command(
    complex_id: Annotated[
        int,
        typer.Argument(min=1, help='단지 ID (complexes·school·search locations <단지 이름> 결과, 아파트·오피스텔 listing 의 complex_id)')
    ],
    area: Annotated[
        int | None,
        typer.Option(min=1, help='전용면적 묶음 (complex 결과의 pyeongs[].area_group, 예: 84). 기본 전 평형을 섞은 평균')
    ] = None,
    trade: Annotated[
        str,
        typer.Option('--trade', help=f"{', '.join(PRICE_CHART_TRADE_BY_TRADE_TYPE)} 중 하나 (월세 시세 그래프는 없다)")
    ] = '매매',
    years: Annotated[
        int,
        typer.Option(min=1, max=PRICE_TREND_MAX_YEARS, help='보여 줄 기간이자 변화율을 비교할 햇수')
    ] = 3,
    pretty: PrettyOption = None,
) -> None:
    """단지 시세 추이: 월별 평균 실거래가(국토부 신고 기준)와 N년 전 대비 변화율. 요청 1회.

    예: jibsa daangn price-trend 10697091 --area 84 --trade 매매 --years 3
    """
    trade_types = split_csv([trade], tuple(PRICE_CHART_TRADE_BY_TRADE_TYPE), '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('시세 추이는 매매, 전세 중 하나만 받습니다', param_hint='--trade')
    with handle_errors(SOURCE), DaangnClient() as client:
        result = get_price_trend(client, complex_id, trade_type=trade_types[0], area_group=area, years=years)
        emit(result, pretty, notes=result.notes)


def _center(place: str | None, lat: float | None, lng: float | None, radius_km: float) -> tuple[float, float, list[str]]:
    """지역·역·장소 이름 또는 좌표를 검색 중심으로 바꾼다 (`_geocode`). 이름이면 어디서 찾았는지 안내를 붙인다."""
    _require_one_place(place, lat, lng, 'PLACE')
    if lat is not None and lng is not None:
        return lat, lng, []
    assert place is not None
    center, notes, finder = _geocode(place, radius_km)
    return center.lat, center.lng, notes + [
        f"{quoted(place, '은/는')} {finder} 지역 검색으로 찾은 위치({center.address or center.name})를 중심으로 찾았습니다"
    ]


@app.command('developments')
def developments_command(
    place: Annotated[
        str | None,
        typer.Argument(help='검색 중심 지역·역·장소 이름 (예: 역삼역, 강남구). --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[float, typer.Option(min=0.1, max=5.0, help='검색 반경 (km)')] = DEFAULT_RADIUS_KM,
    category: Annotated[
        list[str] | None,
        typer.Option('--category', help=f"{', '.join(DEVELOPMENT_CATEGORY_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=DEVELOPMENT_MAX_LIMIT, help='최대 사업 수')] = 50,
    pretty: PrettyOption = None,
) -> None:
    """반경 안 개발 호재(도로·철도·정비사업)를 가까운 순으로. 요청 1회 (이름이면 위치 찾기 요청이 더 든다).

    예: jibsa daangn developments 역삼역 --radius 2 --category 정비사업
    """
    require_finite('--radius', radius)
    categories = split_csv(category, tuple(DEVELOPMENT_CATEGORY_BY_LABEL), '--category')
    with handle_errors(SOURCE):
        center_lat, center_lng, notes = _center(place, lat, lng, radius)
        with DaangnClient() as client:
            result = list_developments(client, center_lat, center_lng, radius_km=radius, categories=categories, limit=limit)
        emit(result, pretty, notes=notes + result.notes)


@app.command('development')
def development_command(
    development_id: Annotated[int, typer.Argument(min=1, help='사업 번호 (developments 결과의 id)')],
    pretty: PrettyOption = None,
) -> None:
    """개발 사업 하나의 종류·단계·규모·시공사·인가 날짜. 요청 1회.

    예: jibsa daangn development 1003444
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        emit(get_development(client, development_id), pretty)


@app.command('preschools')
def preschools_command(
    place: Annotated[
        str | None,
        typer.Argument(help='검색 중심 지역·역·장소 이름 (예: 역삼역). --lat/--lng 를 주면 생략')
    ] = None,
    lat: LatOption = None,
    lng: LngOption = None,
    radius: Annotated[float, typer.Option(min=0.1, max=3.0, help='검색 반경 (km)')] = DEFAULT_RADIUS_KM,
    preschool_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(PRESCHOOL_TYPE_BY_LABEL)}. 반복하거나 쉼표로 구분. 기본 전체")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=PRESCHOOL_MAX_LIMIT, help='최대 시설 수')] = 30,
    pretty: PrettyOption = None,
) -> None:
    """반경 안 어린이집·유치원을 가까운 순으로. 요청 1회 (이름이면 위치 찾기 요청이 더 든다).

    예: jibsa daangn preschools 역삼역 -t 어린이집
    """
    require_finite('--radius', radius)
    types = split_csv(preschool_type, tuple(PRESCHOOL_TYPE_BY_LABEL), '--type')
    with handle_errors(SOURCE):
        center_lat, center_lng, notes = _center(place, lat, lng, radius)
        with DaangnClient() as client:
            result = list_preschools(client, center_lat, center_lng, radius_km=radius, types=types, limit=limit)
        emit(result, pretty, notes=notes + result.notes)


@app.command('preschool')
def preschool_command(
    preschool_id: Annotated[int, typer.Argument(min=1, help='시설 번호 (preschools 결과의 id)')],
    pretty: PrettyOption = None,
) -> None:
    """어린이집·유치원 하나의 운영 시간·설립 유형·원아·반·교사 수. 전화번호는 주지 않는다. 요청 1회.

    예: jibsa daangn preschool 33710
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        emit(get_preschool(client, preschool_id), pretty)


@app.command('compare')
def compare_command(
    complex_ids: Annotated[
        list[int],
        typer.Argument(min=1, help=f'단지 ID 여러 개 (최대 {COMPARE_MAX_COMPLEXES}개, search locations·search complexes·complex 결과)')
    ],
    pretty: PrettyOption = None,
) -> None:
    """단지 여러 곳을 같은 항목으로 나란히: 세대수·준공·주차, 배정 학교, 역, 평형별 KB 시세·최근 실거래, 호가 범위, 관리비. 단지마다 요청 1회.

    예: jibsa daangn compare 10697092 10699673 10697091
    """
    if len(set(complex_ids)) > COMPARE_MAX_COMPLEXES:
        raise typer.BadParameter(f'단지는 최대 {COMPARE_MAX_COMPLEXES}개까지 비교합니다', param_hint='COMPLEX_IDS')
    with handle_errors(SOURCE), DaangnClient() as client:
        result = compare_complexes(client, complex_ids)
        emit(result, pretty, notes=result.notes)


@app.command('nearby-complexes')
def nearby_complexes_command(
    complex_id: Annotated[int, typer.Argument(min=1, help='기준 단지 ID')],
    limit: Annotated[int, typer.Option(min=1, max=NEARBY_COMPLEXES_MAX, help='최대 단지 수')] = 50,
    pretty: PrettyOption = None,
) -> None:
    """기준 단지와 같은 동의 다른 단지 (세대수·현재 매물 수, 세대수 많은 순). 요청 4회.

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
        typer.Option('--region', help="시·도(예: 서울) 또는 시·군·구(예: 강남구, '서울 중구'). 시·도는 '서울시'·'충북' 같은 줄임말도 되고, 전남광주통합특별시(전남)는 광주·전남을 함께 찾고, 옛 이름(광주·광주광역시·전라남도)은 그 한 곳만 찾는다. 구가 있는 시는 '분당구'·'성남시 분당구' 로 한 구를, '수원시' 로 그 시의 구 모두를 찾는다. 반복하거나 쉼표로 구분. 기본 전국")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=50, help='최대 동 수')] = 10,
    pretty: PrettyOption = None,
) -> None:
    """라이프스타일에 맞는 살기 좋은 동 순위 (당근 통계 지표 기준). 지역을 주면 요청 2회.

    후기 요약 글은 주지 않는다. 동은 행정동이라, 매물은 법정동 이름으로 search listings 에서 찾는다.

    예: jibsa daangn good-neighborhoods --lifestyle 직장인자취 --region 서울
    """
    lifestyles = split_csv([lifestyle], tuple(LIFESTYLE_INDICATORS), '--lifestyle')
    if len(lifestyles) != 1:
        raise typer.BadParameter(f"라이프스타일은 하나만 받습니다 ({', '.join(LIFESTYLE_INDICATORS)} 중 하나)", param_hint='--lifestyle')
    regions = [name for item in region or [] for name in item.split(',') if name.strip()]
    with handle_errors(SOURCE), DaangnClient() as client:
        result = recommend_neighborhoods(client, lifestyles[0], regions=[name.strip() for name in regions], limit=limit)
        emit(result, pretty, notes=result.notes)


@app.command('trending-complexes')
def trending_complexes_command(
    dong: Annotated[str, typer.Argument(help='동 이름 (예: 역삼동)')],
    city: Annotated[
        str | None,
        typer.Option(help="동명이 여러 곳일 때 시/도나 구로 좁힘 (예: '강남구'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """동 주변에서 요즘 많이 보는 단지 (서버가 9곳쯤 준다). 요청 2회.

    예: jibsa daangn trending-complexes 역삼동 --city 강남구
    """
    with handle_errors(SOURCE), DaangnClient() as client:
        place_notes: list[str] = []
        regions = resolve_regions(client, dong, city=city, notes=place_notes)
        result = list_trending_complexes(client, regions[0])
        emit(result, pretty, notes=place_notes + result.notes)


@app.command('popular-listings')
def popular_listings_command(
    dong: Annotated[str, typer.Argument(help='동 이름 (예: 역삼동). 순위는 그 동이 속한 구 전체다 (구가 없는 세종은 그 동 안)')],
    city: Annotated[
        str | None,
        typer.Option(help="동명이 여러 곳일 때 시/도나 구로 좁힘 (예: '강남구'. 시·도는 '서울시'·'강원도' 같은 줄임말도 된다)")
    ] = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 전체")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=POPULAR_MAX_LIMIT, help='조회할 매물 수 (제외 전)')] = 20,
    pretty: PrettyOption = None,
) -> None:
    """구 전체에서 조회수 많은 매물 순위 (순위가 매겨진 매물은 100건쯤). 요청 2회.

    예: jibsa daangn popular-listings 역삼동 -t 원룸
    """
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type')
    with handle_errors(SOURCE), DaangnClient() as client:
        place_notes: list[str] = []
        regions = resolve_regions(client, dong, city=city, notes=place_notes)
        result = list_popular_listings(client, regions[0], property_types=property_types, limit=limit)
        emit(
            result,
            pretty,
            notes=place_notes + property_type_notes(property_types) + result.notes,
        )
