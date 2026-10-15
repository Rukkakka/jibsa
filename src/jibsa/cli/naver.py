import re
from collections.abc import Iterable

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
from jibsa.core.geo import DEFAULT_RADIUS_KM
from jibsa.core.korean import is_ri_code
from jibsa.core.listing import normalize_address
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.service.common import (
    AREA_BASES,
    COMPLEX_SORT_TYPE_BY_NAME,
    MAX_LIST_LIMIT,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    PERIOD_YEARS_BY_NAME,
    SEARCH_CODES_BY_PROPERTY,
    SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
    NaverTradeConditions,
    dong_key,
    dong_label,
)
from jibsa.providers.naver.service.complex import get_complex
from jibsa.providers.naver.service.listing import (
    get_listing,
    list_complex_articles,
)
from jibsa.providers.naver.service.market_price import get_market_price_history
from jibsa.providers.naver.service.real_price import get_real_prices
from jibsa.providers.naver.service.redevelopment import (
    REDEVELOPMENT_SORT_TYPE_BY_NAME,
    get_redevelopment,
    list_redevelopment_areas,
    list_redevelopment_articles,
)
from jibsa.providers.naver.service.region import (
    NaverRegion,
    ga_dong_regions,
    legal_division_code_at,
    list_regions,
    resolve_complex_number,
    resolve_search_region,
)
from jibsa.providers.naver.service.school import get_school
from jibsa.providers.naver.service.search import (
    AREA_COMPLEX_CODES_BY_TYPE,
    BATHROOM_CODE_BY_NAME,
    COMPLEX_LIST_SORT_TYPE_BY_NAME,
    DEFAULT_SEARCH_PROPERTY_TYPES,
    DIRECTION_FILTER_CODE_BY_NAME,
    ENTRANCE_CODE_BY_NAME,
    FACILITY_CODE_BY_NAME,
    FLOOR_CODE_BY_NAME,
    LOAN_CODE_BY_NAME,
    MOVE_IN_CODE_BY_NAME,
    PARKING_CODE_BY_NAME,
    ROOM_COUNT_CODE_BY_NAME,
    NaverListingConditions,
    list_area_complexes,
    search_area,
)
from jibsa.providers.naver.service.trend import (
    TREND_PERIOD_BY_NAME,
    TREND_PYEONG_RANGES,
    TREND_TRADE_CODE_BY_NAME,
    get_district_trend,
)

from typing import Annotated


SOURCE: str = 'naver'
TRADE_TYPES: tuple[str, ...] = tuple(TRADE_CODE_BY_NAME)
# 지역 이름과 좌표를 함께 주면 좌표로 찾는다. 이름 주변을 찾았다고 오해하지 않게 알린다
COORDINATES_OVER_QUERY_NOTE: str = "--lat/--lng 좌표를 검색 중심으로 썼습니다. '{query}' 는 위치를 찾는 데 쓰지 않고 region.name 에만 붙였습니다"
PROPERTY_TYPES: tuple[str, ...] = tuple(SEARCH_CODES_BY_PROPERTY)
# str.isdigit·isalnum 은 '²'·한글도 통과시켜 int() 가 PARSE_ERROR 를 내거나 요청 모델의 영어 오류가 나온다
NUMBER_PATTERN: re.Pattern[str] = re.compile(r'[0-9]+')
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(r'[A-Za-z0-9]+')

app = typer.Typer(
    help=(
        '네이버 부동산: 아파트·오피스텔·빌라 단지/매물/실거래가 (로그인 불필요). '
        '원본은 원 단위지만 출력은 만원으로 환산. 요청이 잦으면 수 분간 차단(429)되니 아껴 쓸 것'
    ),
    no_args_is_help=True,
)

search_app = typer.Typer(help='지역에서 매물 또는 단지를 찾는다', no_args_is_help=True)
app.add_typer(search_app, name='search')


def _complex_number(client: NaverClient, complex_: str) -> tuple[int, bool | None, list[str]]:
    """단지 번호면 그대로, 이름이면 네이버 단지 검색으로 번호를 찾는다 (빌라 단지인지와 비슷한 후보 안내를 함께 준다)."""
    # 붙여 넣은 번호의 앞뒤 공백(' 8928')을 먼저 떼야 번호를 이름으로 찾지 않는다
    complex_ = complex_.strip()
    if NUMBER_PATTERN.fullmatch(complex_) is None:
        return resolve_complex_number(client, complex_)
    if int(complex_) < 1:
        raise typer.BadParameter('단지 번호는 1 이상입니다', param_hint='COMPLEX')
    return int(complex_), None, []


def _split_dongs(values: list[str] | None) -> list[str]:
    """`--dong 101 --dong 102동` 과 `--dong 101,102동` 을 모두 받는다 (이름 확인은 동 목록 조회 뒤)."""
    return list(dict.fromkeys(part.strip() for value in values or [] for part in value.split(',') if part.strip()))


# 직방(zigbang search)의 동 경계 검색과 같은 안내
WHOLE_DONG_NOTE: str = '{name} 경계 안을 찾았습니다 (반경으로 찾으려면 --radius)'
# 지역 매물 검색의 목록 옵션에 없는 값을 이 명령에서 주는 법 (split_csv 의 에러 힌트). 이 명령의 다른 옵션 값과, 뜻이 같은
# 다른 소스 표현이다 (직방 --room 오픈형원룸·--condition 즉시입주·--bathroom 1, 당근 --option 주차가능·--room-count 2개).
# '2개'·'3개' 는 욕실 수 값과 겹치지만 거절되는 곳은 --room 이 흔해 방 수로 안내한다. 네이버는 반지하를 따로 두지 않고
# 지하층(B1)으로 준다
LISTING_USAGE_BY_VALUE: dict[str, str] = {
    **{value: f'--room {value}' for value in ROOM_COUNT_CODE_BY_NAME},
    **{value: f'--floor {value}' for value in FLOOR_CODE_BY_NAME},
    **{value: f'--direction {value}' for value in DIRECTION_FILTER_CODE_BY_NAME},
    **{value: f'--bathroom {value}' for value in BATHROOM_CODE_BY_NAME},
    **{value: f'--facility {value}' for value in FACILITY_CODE_BY_NAME},
    **{value: f'--one-room-shape {value}' for value in ONE_ROOM_SHAPE_CODE_BY_NAME},
    **{value: f'--move-in {value}' for value in MOVE_IN_CODE_BY_NAME},
    **{value: f'--parking {value}' for value in PARKING_CODE_BY_NAME},
    '주차가능': '--facility 주차',
    '복층형원룸': '--facility 복층',
    '오픈형원룸': '--one-room-shape 오픈형',
    '분리형원룸': '--one-room-shape 분리형',
    '즉시입주': '--move-in 바로입주',
    '반지하': '--floor 지하층',
    '2개': '--room 투룸',
    '3개': '--room 쓰리룸',
    '4개이상': '--room 포룸이상',
    '1': '--bathroom 1개',
    '2': '--bathroom 2개',
    '3': '--bathroom 3개,4개이상',
}


def _check_choice(value: object, allowed: Iterable[object], option: str) -> None:
    """하나만 받는 옵션의 값이 허용값인지 본다."""
    if value not in allowed:
        raise typer.BadParameter(
            f"허용되지 않는 값입니다: '{value}'. 가능한 값: {', '.join(map(str, allowed))}", param_hint=option,
        )


def _price_trade_types(
    trade: list[str] | None,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
) -> tuple[list[str], list[str]]:
    """--trade 를 확인하고, 거래 유형을 주지 않았으면 가격 조건에 맞는 거래 유형을 추론한다 (`infer_trade_types`)."""
    return infer_trade_types(
        split_csv(trade, TRADE_TYPES, '--trade'),
        rent=rent_min is not None or rent_max is not None,
        price=price_min is not None or price_max is not None,
        deposit=deposit_min is not None or deposit_max is not None,
    )


def _reject_options(mode: str, options: dict[str, object]) -> None:
    """모드(--complex·--redevelopment)가 받지 않는 옵션을 주었으면 한꺼번에 알린다. 값이 None 이면 주지 않은 것이다."""
    invalid = [name for name, value in options.items() if value is not None]
    if invalid:
        raise typer.BadParameter(f"{mode}와 함께 사용할 수 없습니다: {', '.join(invalid)}", param_hint=mode)


def _require_location(query: str | None, lat: float | None, lng: float | None) -> None:
    """지역 이름이나 좌표가 있어야 한다. 좌표를 하나만 줬으면 '둘 다 주세요' 가 맞는 안내라 먼저 본다."""
    require_korea(lat, lng)
    if query is None and (lat is None or lng is None):
        raise typer.BadParameter('지역 이름 또는 --lat/--lng 를 주세요', param_hint='QUERY')


def _resolve_location(
    client: NaverClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float | None,
    *,
    radius_search: bool = True,
) -> tuple[NaverRegion, str, list[str]]:
    """검색 위치, 그 종류, 안내. 좌표를 주면 좌표(종류 '좌표')가 이름보다 앞선다.

    반경으로 찾지 않는 명령(trend)은 `radius_search=False` 로 '반경 안만 검색했습니다' 안내를 받지 않는다.

    이름은 네이버 주소 검색 → 자동완성(동 → 역 → 단지)으로 찾는다. 못 찾으면 REGION_NOT_FOUND, 여러 곳이면
    REGION_AMBIGUOUS, 막히면 RATE_LIMITED 로 끝낸다 (다른 소스로 대신 찾지 않는다).
    """
    if lat is not None and lng is not None:
        notes = [COORDINATES_OVER_QUERY_NOTE.format(query=query)] if query is not None else []
        return NaverRegion(name=query or f'{lat},{lng}', lat=lat, lng=lng), '좌표', notes
    # 좌표가 없으면 _require_location 이 이름을 요구했다
    assert query is not None
    return resolve_search_region(client, query, (radius or DEFAULT_RADIUS_KM) if radius_search else None)


def _whole_dong(region: NaverRegion, kind: str, radius: float | None) -> bool:
    """동 이름으로 찾았고 반경을 주지 않았으면 반경 대신 동 경계 안 전체를 찾는다 (법정동 코드가 있을 때만)."""
    return kind == '동' and radius is None and region.legal_division_code is not None


def _merged_region(region: NaverRegion, dongs: list[NaverRegion]) -> NaverRegion:
    """합쳐 찾은 '○가' 동들을 직방처럼 한 지역으로 보인다 (이름 '성수동1가·성수동2가', 중심은 처음 찾은 동, 코드 없음)."""
    names = '·'.join(dong.name for dong in dongs)
    parent = (region.address or '').rsplit(' ', 1)[0]
    return NaverRegion(name=names, address=f'{parent} {names}'.strip(), lat=region.lat, lng=region.lng)


def _search_scope(region: NaverRegion, whole_dong: bool, radius: float | None) -> dict[str, object]:
    """어디를 찾았는지. 동 경계로 찾았으면 boundary(동 이름), 아니면 radius_km 다 (직방 search 와 같다)."""
    return {'boundary': region.name} if whole_dong else {'radius_km': radius or DEFAULT_RADIUS_KM}


@app.command('complex')
def complex_command(
    complex_: Annotated[
        str,
        typer.Argument(
            metavar='COMPLEX',
            help='단지 번호 (fin.land.naver.com/complexes/{번호}) 또는 단지 이름 (예: 개포자이). 이름이면 네이버 단지 검색으로 번호를 찾는다',
        )
    ],
    pyeong: Annotated[
        list[int] | None,
        typer.Option('--pyeong', min=1, help='평형 번호 (평형 ID, 평수 아님; 결과의 pyeongs[].number). 주면 매물 수·호가 범위를 그 평형만으로 센다. 하나만 주면 그 평형의 관리비·시세·최근 3년 실거래 요약도 붙인다 (요청 4회 추가). 반복 가능')
    ] = None,
    dong: Annotated[
        list[str] | None,
        typer.Option('--dong', help='동 이름 (예: 104 또는 104동). 주면 매물 수·호가 범위를 그 동만으로 센다. 반복하거나 쉼표로 구분')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 정보·거래유형별 매물 수·호가 범위·평형 목록. 결과의 complex_number 를 search listings --complex·real-price 에 넘긴다.

    예: jibsa naver complex 개포자이 --pyeong 1   # 1번 평형 매물 수·호가·관리비·시세·실거래 요약
    """
    dong_names = _split_dongs(dong)
    with handle_errors(SOURCE), NaverClient() as client:
        complex_number, villa, notes = _complex_number(client, complex_)
        summary = get_complex(client, complex_number, pyeong_numbers=pyeong, dong_names=dong_names, villa=villa)
        scope: list[str] = []
        if pyeong:
            scope.append(f"{', '.join(map(str, dict.fromkeys(pyeong)))}번 평형")
        if dong_names:
            scope.append(', '.join(dong_label(key) for key in dict.fromkeys(map(dong_key, dong_names))))
        if scope:
            notes.append(
                f"article_counts·호가 범위는 {' · '.join(scope)} 매물만 센 값입니다 (단지 정보와 pyeongs 는 단지 전체)"
            )
        emit(summary, pretty, notes=notes + summary.notes)


@search_app.command('complexes')
def complexes_command(
    query: Annotated[
        str | None,
        typer.Argument(help="주소·동·역·단지 이름 (예: 역삼동, 강남역, '역삼동 719-28'). 동 이름이면 동 안 단지 전체. --lat/--lng 를 주면 생략")
    ] = None,
    lat: Annotated[float | None, typer.Option(help='중심 위도')] = None,
    lng: Annotated[float | None, typer.Option(help='중심 경도')] = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"단지 유형: {', '.join(AREA_COMPLEX_CODES_BY_TYPE)} (빌라는 단지로 등록된 연립·다세대). 반복하거나 쉼표로 구분. 기본 아파트")
    ] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동 이름으로 찾았을 때 주면 동 전체 대신 동 중심 반경으로 찾는다')
    ] = None,
    sort: Annotated[
        str,
        typer.Option('--sort', help=f"정렬: {', '.join(COMPLEX_LIST_SORT_TYPE_BY_NAME)}. 네이버가 정렬해 준다")
    ] = '인기순',
    include_empty: Annotated[bool, typer.Option('--include-empty', help='매물이 없는 단지도 (기본은 매물 있는 단지만)')] = False,
    household_min: Annotated[int | None, typer.Option(min=0, help='세대수 하한')] = None,
    household_max: Annotated[int | None, typer.Option(min=0, help='세대수 상한')] = None,
    building_age_min: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 하한 (년). 5면 5년 이상')] = None,
    building_age_max: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 상한 (년). 5 면 5년 이내 단지')] = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='최대 결과 수')] = 30,
    pretty: PrettyOption = None,
) -> None:
    """지역 안 단지 목록 (세대수·준공일·매물 수·호가 범위). 결과의 complex_number 를 complex·search listings --complex 에 넘긴다.

    위치는 naver search listings 와 같이 찾는다. 동 이름이면 동 경계 안 단지 전체(boundary), 그 밖은 반경 안(radius_km)이다.

    예: jibsa naver search complexes 역삼동 --sort 세대수순
    """
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    property_types = split_csv(property_type, tuple(AREA_COMPLEX_CODES_BY_TYPE), '--type')
    _check_choice(sort, COMPLEX_LIST_SORT_TYPE_BY_NAME, '--sort')
    validate_ranges(('household', household_min, household_max), ('building-age', building_age_min, building_age_max))

    with handle_errors(SOURCE), NaverClient() as client:
        region, kind, notes = _resolve_location(client, query, lat, lng, radius)
        whole_dong = _whole_dong(region, kind, radius)
        if whole_dong:
            notes.append(WHOLE_DONG_NOTE.format(name=region.name))
        result = list_area_complexes(
            client,
            region.lat,
            region.lng,
            radius_km=radius or DEFAULT_RADIUS_KM,
            legal_division_code=region.legal_division_code if whole_dong else None,
            property_types=property_types,
            sort=sort,
            listed_only=not include_empty,
            household_min=household_min,
            household_max=household_max,
            building_age_min=building_age_min,
            building_age_max=building_age_max,
            limit=limit,
        )
        emit(
            {'region': region.model_dump(mode='json'), **_search_scope(region, whole_dong, radius), **result.model_dump(mode='json')},
            pretty,
            notes=notes + result.notes,
        )


def _trade_conditions(
    trade: list[str] | None,
    sort: str,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
) -> tuple[NaverTradeConditions, list[str]]:
    """단지·재개발 구역 매물 목록의 거래 유형·가격·정렬을 확인하고 조건 묶음과 거래 유형 추론 안내를 준다.

    지역 검색보다 받는 조건이 적다.
    """
    trade_types, trade_notes = _price_trade_types(trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max)
    validate_ranges(('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max), ('price', price_min, price_max))
    _check_choice(sort, COMPLEX_SORT_TYPE_BY_NAME, '--sort')
    with handle_errors(SOURCE):
        conditions = NaverTradeConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
        )
    return conditions, trade_notes


def _search_complex_listings(
    complex_: str,
    conditions: NaverTradeConditions,
    trade_notes: list[str],
    *,
    pyeong: list[int] | None,
    dong: list[str] | None,
    sort: str,
    limit: int,
    pretty: bool | None,
) -> None:
    """단지의 매물 목록 (기본 네이버 랭킹 순). 가격 조건은 네이버 서버 필터로 거른다.

    예: jibsa naver search listings --complex 개포자이 --trade 매매 --dong 104 --price-max 300000 --sort 가격낮은순
    """
    dong_names = _split_dongs(dong)
    with handle_errors(SOURCE), NaverClient() as client:
        complex_number, villa, notes = _complex_number(client, complex_)
        result = list_complex_articles(
            client,
            complex_number,
            conditions=conditions,
            pyeong_numbers=pyeong,
            dong_names=dong_names,
            sort=sort,
            villa=villa,
            limit=limit,
        )
        # 이름으로 찾았으면 고른 단지 번호를 함께 줘야 real-price·complex 로 이어 조회할 수 있다
        emit(
            {'complex_number': complex_number, **result.model_dump(mode='json')},
            pretty,
            notes=trade_notes + notes + result.notes,
        )


def _search_redevelopment_listings(
    area_number: int,
    conditions: NaverTradeConditions,
    trade_notes: list[str],
    *,
    sort: str,
    limit: int,
    pretty: bool | None,
) -> None:
    """재개발 구역 하나의 매물 목록 (기본 네이버 랭킹 순). 가격 조건은 네이버 서버 필터로 거른다."""
    with handle_errors(SOURCE), NaverClient() as client:
        result = list_redevelopment_articles(client, area_number, conditions=conditions, sort=sort, limit=limit)
        emit(
            {'redevelopment_number': area_number, **result.model_dump(mode='json')},
            pretty,
            notes=trade_notes + result.notes,
        )


@search_app.command('redevelopment')
def redevelopment_command(
    query: Annotated[
        str | None,
        typer.Argument(help='주소·동·역·단지 이름 (예: 한남동, 한강진역). 동 이름이면 동 안 구역 전체. --lat/--lng 를 주면 생략')
    ] = None,
    lat: Annotated[float | None, typer.Option(help='중심 위도')] = None,
    lng: Annotated[float | None, typer.Option(help='중심 경도')] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동 이름으로 찾았을 때 주면 동 전체 대신 동 중심 반경으로 찾는다')
    ] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 매매, 전세, 월세, 단기임대. 주면 그 거래 매물이 1건 이상인 구역만 남긴다. 반복하거나 쉼표로 구분. 기본은 거르지 않음')
    ] = None,
    sort: Annotated[
        str,
        typer.Option('--sort', help=f"정렬: {', '.join(REDEVELOPMENT_SORT_TYPE_BY_NAME)}. 네이버가 정렬해 준다")
    ] = '매물수순',
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='최대 결과 수')] = 30,
    pretty: PrettyOption = None,
) -> None:
    """지역 안 재개발 구역 (사업 단계·세대수·거래 유형별 매물 수·매매 호가). 결과의 redevelopment_number 를 search listings --redevelopment 에 넘긴다.

    위치는 naver search listings 와 같이 찾는다. 동 이름이면 동 경계 안 구역 전체(boundary), 그 밖은 반경 안(radius_km)이다.
    네이버는 한 구역을 법정동마다 따로 등록하기도 해 같은 이름이 여러 번 나올 수 있다 (legal_division 으로 구분).

    예: jibsa naver search redevelopment 한남동
    """
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    trade_types = split_csv(trade, TRADE_TYPES, '--trade')
    _check_choice(sort, REDEVELOPMENT_SORT_TYPE_BY_NAME, '--sort')

    with handle_errors(SOURCE), NaverClient() as client:
        region, kind, notes = _resolve_location(client, query, lat, lng, radius)
        whole_dong = _whole_dong(region, kind, radius)
        if whole_dong:
            notes.append(WHOLE_DONG_NOTE.format(name=region.name))
        result = list_redevelopment_areas(
            client,
            region.lat,
            region.lng,
            radius_km=radius or DEFAULT_RADIUS_KM,
            legal_division_code=region.legal_division_code if whole_dong else None,
            legal_division_name=(region.address or region.name) if whole_dong else None,
            trade_types=trade_types,
            sort=sort,
            limit=limit,
        )
        emit(
            {'region': region.model_dump(mode='json'), **_search_scope(region, whole_dong, radius), **result.model_dump(mode='json')},
            pretty,
            notes=notes + result.notes,
        )


@app.command('trend')
def trend_command(
    query: Annotated[
        str | None,
        typer.Argument(help='동·구 이름 (예: 역삼동, 강남구). 역·주소·단지면 그 자리의 법정동. --lat/--lng 를 주면 생략')
    ] = None,
    lat: Annotated[float | None, typer.Option(help='위도 (그 자리의 법정동)')] = None,
    lng: Annotated[float | None, typer.Option(help='경도 (그 자리의 법정동)')] = None,
    trade: Annotated[
        str,
        typer.Option('--trade', help=f"거래 유형: {', '.join(TREND_TRADE_CODE_BY_NAME)} (네이버가 월세 추이는 주지 않는다)")
    ] = '매매',
    period: Annotated[
        str,
        typer.Option('--period', help=f"기간: {', '.join(TREND_PERIOD_BY_NAME)}")
    ] = '1년',
    pyeong_range: Annotated[
        int | None,
        typer.Option('--pyeong-range', help=f"평형대 하한 (평): {', '.join(map(str, TREND_PYEONG_RANGES))}. 30 이면 30~40평. 기본 전체")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """동네 아파트 주간 추이: 매물 수·평균 평당 호가(만원)·실거래 건수. 오피스텔·빌라 추이는 네이버가 주지 않는다 (요청 3회).

    예: jibsa naver trend 역삼동 --trade 전세 --period 3년 --pyeong-range 30
    """
    _require_location(query, lat, lng)
    _check_choice(trade, TREND_TRADE_CODE_BY_NAME, '--trade')
    _check_choice(period, TREND_PERIOD_BY_NAME, '--period')
    if pyeong_range is not None:
        _check_choice(pyeong_range, TREND_PYEONG_RANGES, '--pyeong-range')

    with handle_errors(SOURCE), NaverClient() as client:
        region, kind, notes = _resolve_location(client, query, lat, lng, None, radius_search=False)
        division: str | None
        code, division = region.legal_division_code, normalize_address(region.address or region.name)
        # 리 코드(…21)는 네이버가 매물 수·호가·거래를 모두 0 으로 준다 (장현리 매물 0, 같은 진접읍 1,394, 2026-10-10)
        ri = is_ri_code(code)
        if ri or kind == '주소':
            # 번지·도로명 주소는 이름이 법정동 이름이 아니라서('역삼동 719-28'), 리는 추이가 없어서 그 자리의
            # 법정동으로 찾는다. 좌표로 찾으면 리 자리는 읍·면 코드가 온다 (장현리 → 진접읍 4136025300)
            code = None
        # 단지는 자동완성이 준 단지의 법정동 코드를 그대로 써 좌표 조회를 아끼지만, 역·좌표처럼 그 자리의 동 추이라고 알린다
        at_spot = code is None or kind == '단지'
        if code is None:
            # 역·행정동·좌표는 법정동 코드가 없어 그 자리의 법정동으로 본다
            found = legal_division_code_at(client, region.lat, region.lng)
            if found is None:
                # 입력이 틀린 게 아니라 그 자리에 법정동이 없는 것이다 (바다 좌표 35.5,125.8 → searchByCoordinate 빈 결과, 2026-10-10)
                raise RegionNotFoundError(region.name, hint="동·구 이름(예: '역삼동')으로 다시 주세요")
            code, division = found[0], normalize_address(found[1])
        if ri:
            notes.append(f"'{region.name}': 리 단위 추이는 네이버가 주지 않아 {division} 추이입니다")
        elif at_spot:
            notes.append(f"'{region.name}' 자리의 법정동({division}) 추이입니다")
        trend = get_district_trend(client, code, trade_type=trade, period=period, pyeong_range=pyeong_range)
        emit({'legal_division': division, **trend.model_dump(mode='json')}, pretty, notes=notes)


@app.command('real-price')
def real_price_command(
    complex_number: Annotated[int, typer.Argument(min=1, help='단지 번호')],
    pyeong: Annotated[int, typer.Option('--pyeong', min=1, help='평형 번호 (평형 ID, 평수 아님; complex 결과의 pyeongs[].number)')],
    trade: Annotated[str, typer.Option('--trade', help='매매, 전세, 월세')] = '매매',
    pages: Annotated[
        int | None,
        typer.Option(min=1, max=10, help='가져올 페이지 수 (페이지당 10건, 기본 1). --period 와 함께 쓸 수 없다')
    ] = None,
    period: Annotated[
        str | None,
        typer.Option('--period', help=f"기간: {', '.join(PERIOD_YEARS_BY_NAME)}. 주면 페이지 대신 그 기간 안 거래를 모두 준다")
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """평형별 실거래가 (국토부 신고 기준, 최근 순).

    예: jibsa naver real-price 12345 --pyeong 2 --trade 전세 --period 3년
    """
    trade_types = split_csv([trade], ('매매', '전세', '월세'), '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    if period is not None:
        _check_choice(period, PERIOD_YEARS_BY_NAME, '--period')
        if pages is not None:
            raise typer.BadParameter('--period 와 --pages 는 함께 쓸 수 없습니다. 기간이면 --period 만 주세요', param_hint='--pages')
    with handle_errors(SOURCE), NaverClient() as client:
        result = get_real_prices(
            client, complex_number, pyeong, trade_type=trade_types[0], pages=pages or 1, period=period,
        )
        emit(result, pretty, notes=result.notes)


@app.command('market-price')
def market_price_command(
    complex_: Annotated[
        str,
        typer.Argument(metavar='COMPLEX', help='단지 번호 또는 단지 이름 (예: 개포자이)')
    ],
    pyeong: Annotated[int, typer.Option('--pyeong', min=1, help='평형 번호 (평형 ID, 평수 아님; complex 결과의 pyeongs[].number)')],
    period: Annotated[
        str,
        typer.Option('--period', help=f"기간: {', '.join(PERIOD_YEARS_BY_NAME)}")
    ] = '1년',
    pretty: PrettyOption = None,
) -> None:
    """평형의 기관별 시세 추이 (한국부동산원·KB부동산·부동산뱅크, 주별 매매·전세 시세와 전세가율, 만원). 요청 1회.

    시세는 기관 추정값이다. 실제 거래는 real-price 로 본다.

    예: jibsa naver market-price 개포자이 --pyeong 1 --period 3년
    """
    _check_choice(period, PERIOD_YEARS_BY_NAME, '--period')
    with handle_errors(SOURCE), NaverClient() as client:
        complex_number, villa, notes = _complex_number(client, complex_)
        emit(get_market_price_history(client, complex_number, pyeong, period=period, villa=villa), pretty, notes=notes)


@app.command('redevelopment')
def redevelopment_detail_command(
    area_number: Annotated[
        int,
        typer.Argument(min=1, metavar='REDEVELOPMENT_NUMBER', help='재개발 구역 번호 (search redevelopment 결과의 redevelopment_number)')
    ],
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 매매, 전세, 월세, 단기임대. 주면 매물 수·호가 범위를 그 거래만으로 센다. 반복하거나 쉼표로 구분')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """재개발 구역 하나: 계획 세대수·시공사·용적률·건폐율·사업 단계와 거래 유형별 매물 수·호가 범위 (요청 2회).

    매물 목록은 search listings --redevelopment 로 본다.

    예: jibsa naver redevelopment 10017678 --trade 매매
    """
    trade_types = split_csv(trade, TRADE_TYPES, '--trade')
    with handle_errors(SOURCE), NaverClient() as client:
        detail = get_redevelopment(client, area_number, trade_types=trade_types)
        notes = [f"article_counts·호가 범위는 {', '.join(trade_types)} 매물만 센 값입니다"] if trade_types else []
        emit(detail, pretty, notes=notes)


@app.command('regions')
def regions_command(
    query: Annotated[
        str | None,
        typer.Argument(help='시·도 (서울, 경기도, 충북) 또는 시·군·구 (강남구, 성남시, 부산시 중구). 생략하면 시·도 전체')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """지역의 바로 아래 지역 목록과 법정동 코드: 시·도 → 시·군·구, 시·군·구 → 읍·면·동 (요청 1~3회).

    동네를 하나씩 찾아볼 때 동 이름 목록을 얻는 데 쓴다. 결과의 name 을 search listings·trend 등에 넣는다.

    예: jibsa naver regions 강남구
    """
    with handle_errors(SOURCE), NaverClient() as client:
        result = list_regions(client, query)
        emit(result, pretty, notes=result.notes)


@app.command('school')
def school_command(
    school_code: Annotated[
        str,
        typer.Argument(metavar='SCHOOL_CODE', help='학교 코드 (complex·listing 결과의 schools[].school_code, 예: B100000747)')
    ],
    complex_: Annotated[
        str | None,
        typer.Option('--complex', help='단지 번호 또는 이름. 주면 그 단지에서 이 학교에 배정되는 동을 붙인다 (요청 2~3회 추가)')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """초등학교 상세: 학생 수·학급당/교원당 학생 수와 시·구 평균, 운영 구분, 개교일 (학교알리미 공시, 요청 1회).

    전화·홈페이지는 주지 않는다. 학교 배정은 교육청 학구도로 확인한다.

    예: jibsa naver school B100000747 --complex 개포자이
    """
    school_code = school_code.strip()
    if SCHOOL_CODE_PATTERN.fullmatch(school_code) is None:
        raise typer.BadParameter('학교 코드는 영문·숫자입니다 (예: B100000747)', param_hint='SCHOOL_CODE')
    with handle_errors(SOURCE), NaverClient() as client:
        notes: list[str] = []
        complex_number, villa = None, None
        if complex_ is not None:
            complex_number, villa, notes = _complex_number(client, complex_)
        emit(get_school(client, school_code, complex_number=complex_number, villa=villa), pretty, notes=notes)


@app.command('listing')
def listing_command(
    item_id: Annotated[str, typer.Argument(help='매물 ID (search listings 결과의 id)')],
    pretty: PrettyOption = None,
) -> None:
    """매물 상세 (가격·면적·층·방향·입주일·관리비·시설). 사진·상세 설명·문의는 url 의 원 사이트에서."""
    # 단지 번호처럼 붙여 넣은 공백을 떼고 먼저 검사한다. 요청 모델의 pattern 검사에 맡기면 영어 오류가 나온다
    item_id = item_id.strip()
    if NUMBER_PATTERN.fullmatch(item_id) is None:
        raise typer.BadParameter('매물 ID 는 숫자입니다 (search listings 결과의 id)', param_hint='ITEM_ID')
    with handle_errors(SOURCE), NaverClient() as client:
        emit(get_listing(client, item_id), pretty)


def _listing_conditions(
    *,
    property_type: list[str] | None,
    trade: list[str] | None,
    sort: str | None,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
    manage_cost_min: int | None,
    manage_cost_max: int | None,
    room: list[str] | None,
    area_min: float | None,
    area_max: float | None,
    area_basis: str,
    floor: list[str] | None,
    direction: list[str] | None,
    bathroom: list[str] | None,
    facility: list[str] | None,
    one_room_shape: list[str] | None,
    move_in: list[str] | None,
    loan: str | None,
    photo_only: bool,
    household_min: int | None,
    household_max: int | None,
    parking: list[str] | None,
    entrance: list[str] | None,
    building_age_min: int | None,
    building_age_max: int | None,
    subway_minutes: int | None,
    owner_verified: bool,
) -> tuple[NaverListingConditions, list[str]]:
    """지역 매물 검색(search listings) 옵션을 확인해 조건 묶음과 거래 유형 추론 안내로 바꾼다.

    Raises:
        typer.BadParameter: 모르는 라벨이거나 범위가 거꾸로일 때.
    """
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type')
    trade_types, trade_notes = _price_trade_types(trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max)
    room_types = split_csv(room, tuple(ROOM_COUNT_CODE_BY_NAME), '--room', LISTING_USAGE_BY_VALUE)
    floors = split_csv(floor, tuple(FLOOR_CODE_BY_NAME), '--floor', LISTING_USAGE_BY_VALUE)
    directions = split_csv(direction, tuple(DIRECTION_FILTER_CODE_BY_NAME), '--direction', LISTING_USAGE_BY_VALUE)
    bathrooms = split_csv(bathroom, tuple(BATHROOM_CODE_BY_NAME), '--bathroom', LISTING_USAGE_BY_VALUE)
    facilities = split_csv(facility, tuple(FACILITY_CODE_BY_NAME), '--facility', LISTING_USAGE_BY_VALUE)
    one_room_shapes = split_csv(one_room_shape, tuple(ONE_ROOM_SHAPE_CODE_BY_NAME), '--one-room-shape', LISTING_USAGE_BY_VALUE)
    move_in_types = split_csv(move_in, tuple(MOVE_IN_CODE_BY_NAME), '--move-in', LISTING_USAGE_BY_VALUE)
    parking_types = split_csv(parking, tuple(PARKING_CODE_BY_NAME), '--parking', LISTING_USAGE_BY_VALUE)
    entrances = split_csv(entrance, tuple(ENTRANCE_CODE_BY_NAME), '--entrance')
    _check_choice(area_basis, AREA_BASES, '--area-basis')
    if sort is not None:
        _check_choice(sort, SORT_TYPE_BY_NAME, '--sort')
    if loan is not None:
        _check_choice(loan, LOAN_CODE_BY_NAME, '--loan')
    validate_ranges(
        ('deposit', deposit_min, deposit_max),
        ('rent', rent_min, rent_max),
        ('price', price_min, price_max),
        ('manage-cost', manage_cost_min, manage_cost_max),
        ('area', area_min, area_max),
        ('household', household_min, household_max),
        ('building-age', building_age_min, building_age_max),
    )
    with handle_errors(SOURCE):
        conditions = NaverListingConditions(
            trade_types=trade_types,
            deposit_min=deposit_min,
            deposit_max=deposit_max,
            rent_min=rent_min,
            rent_max=rent_max,
            price_min=price_min,
            price_max=price_max,
            property_types=property_types,
            room_types=room_types,
            area_min=area_min,
            area_max=area_max,
            area_basis=area_basis,
            floors=floors,
            directions=directions,
            manage_cost_min=manage_cost_min,
            manage_cost_max=manage_cost_max,
            bathrooms=bathrooms,
            facilities=facilities,
            one_room_shapes=one_room_shapes,
            move_in=move_in_types,
            loan=loan,
            photo_only=photo_only,
            household_min=household_min,
            household_max=household_max,
            parking=parking_types,
            entrances=entrances,
            building_age_min=building_age_min,
            building_age_max=building_age_max,
            subway_minutes=subway_minutes,
            owner_verified_only=owner_verified,
        )
    return conditions, trade_notes


@search_app.command('listings')
def search_command(
    query: Annotated[
        str | None,
        typer.Argument(help="주소·동·역·단지 이름 (예: '역삼동 719-28', 테헤란로 152, 역삼동, 강남역, 개포자이). 동 이름이면 동 전체를 찾는다. --lat/--lng 를 주면 생략")
    ] = None,
    complex_: Annotated[str | None, typer.Option('--complex', help='단지 이름 또는 번호. 지역·좌표와 함께 사용할 수 없다')] = None,
    redevelopment: Annotated[
        int | None,
        typer.Option('--redevelopment', min=1, help='재개발 구역 번호 (search redevelopment 결과의 redevelopment_number). 그 구역 매물을 찾는다. 지역·좌표·--complex 와 함께 사용할 수 없다')
    ] = None,
    pyeong: Annotated[list[int] | None, typer.Option('--pyeong', min=1, help='--complex 전용: 평형 ID (평수 아님). 반복 가능')] = None,
    dong: Annotated[list[str] | None, typer.Option('--dong', help='--complex 전용: 동 이름 (104 또는 104동). 반복하거나 쉼표로 구분')] = None,
    lat: Annotated[float | None, typer.Option(help='중심 위도')] = None,
    lng: Annotated[float | None, typer.Option(help='중심 경도')] = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"{', '.join(PROPERTY_TYPES)}. 반복하거나 쉼표로 구분. 기본 주거용 ({'·'.join(DEFAULT_SEARCH_PROPERTY_TYPES)}). 빌라에는 단지형 연립·다세대도 들어간다")
    ] = None,
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='매매, 전세, 월세, 단기임대. 반복하거나 쉼표로 구분. 기본 전체')
    ] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 반경 안 매물이 모자라면 반경 밖 가까운 매물도 나온다. 동 이름으로 찾았을 때 주면 동 전체 대신 동 중심 반경으로 찾는다')
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=MAX_LIST_LIMIT, help='최대 결과 수')] = 30,
    deposit_min: DepositMinOption = None,
    deposit_max: DepositMaxOption = None,
    rent_min: RentMinOption = None,
    rent_max: RentMaxOption = None,
    price_min: PriceMinOption = None,
    price_max: PriceMaxOption = None,
    manage_cost_min: Annotated[int | None, typer.Option(min=0, help='관리비 하한 (만원)')] = None,
    manage_cost_max: Annotated[int | None, typer.Option(min=0, help='관리비 상한 (만원)')] = None,
    room: Annotated[
        list[str] | None,
        typer.Option('--room', help=f"방 수: {', '.join(ROOM_COUNT_CODE_BY_NAME)} (원룸=방 1개, 포룸이상=방 4개 이상). 반복하거나 쉼표로 구분")
    ] = None,
    area_min: Annotated[float | None, typer.Option(min=0, help='면적 하한 (㎡, 1평=3.3㎡). 기준은 --area-basis')] = None,
    area_max: Annotated[float | None, typer.Option(min=0, help='면적 상한 (㎡). 기준은 --area-basis')] = None,
    area_basis: Annotated[
        str,
        typer.Option('--area-basis', help=f"--area-min/max 의 면적 기준: {', '.join(AREA_BASES)}. 결과의 area_m2 는 기준과 무관하게 전용면적")
    ] = '전용',
    floor: Annotated[
        list[str] | None,
        typer.Option('--floor', help=f"층: {', '.join(FLOOR_CODE_BY_NAME)}. 반복하거나 쉼표로 구분 (꼭대기 층은 고층이자 탑층)")
    ] = None,
    direction: Annotated[
        list[str] | None,
        typer.Option('--direction', help=f"방향: {', '.join(DIRECTION_FILTER_CODE_BY_NAME)}. 반복하거나 쉼표로 구분")
    ] = None,
    bathroom: Annotated[
        list[str] | None,
        typer.Option('--bathroom', help=f"욕실 수: {', '.join(BATHROOM_CODE_BY_NAME)}. 반복하거나 쉼표로 구분")
    ] = None,
    facility: Annotated[
        list[str] | None,
        typer.Option('--facility', help=f"시설: {', '.join(FACILITY_CODE_BY_NAME)}. 여러 개면 모두 갖춘 매물만")
    ] = None,
    one_room_shape: Annotated[
        list[str] | None,
        typer.Option('--one-room-shape', help=f"원룸 구조: {', '.join(ONE_ROOM_SHAPE_CODE_BY_NAME)}. 분리형에는 방이 여럿인 매물도 들어가니 원룸만 보려면 --room 원룸 과 함께. 구조를 입력한 매물만 걸려 아파트·오피스텔·단지형 빌라는 모두, 다른 매물도 일부 빠진다")
    ] = None,
    move_in: Annotated[
        list[str] | None,
        typer.Option('--move-in', help=f"입주 가능일: {', '.join(MOVE_IN_CODE_BY_NAME)}. 반복하거나 쉼표로 구분")
    ] = None,
    loan: Annotated[
        str | None,
        typer.Option('--loan', help=f"융자금: {', '.join(LOAN_CODE_BY_NAME)}. 없음은 중개사가 융자 없음을 명시한 매물만이라 많이 줄어든다")
    ] = None,
    photo_only: Annotated[bool, typer.Option('--photo-only', help='사진 있는 매물만')] = False,
    household_min: Annotated[int | None, typer.Option(min=0, help='단지 세대수 하한. 단지가 없는 빌라 대부분이 빠진다')] = None,
    household_max: Annotated[int | None, typer.Option(min=0, help='단지 세대수 상한. 단지가 없는 빌라 대부분이 빠진다')] = None,
    parking: Annotated[
        list[str] | None,
        typer.Option('--parking', help=f"단지 주차: {', '.join(PARKING_CODE_BY_NAME)}. 여러 개면 모두 해당. 단지가 없는 빌라 대부분이 빠진다")
    ] = None,
    entrance: Annotated[
        list[str] | None,
        typer.Option('--entrance', help=f"단지 현관 구조: {', '.join(ENTRANCE_CODE_BY_NAME)}. 단지가 없는 빌라 대부분이 빠진다")
    ] = None,
    building_age_min: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 하한 (년). 5면 5년 이상')] = None,
    building_age_max: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 상한 (년). 5 면 5년 이내 건물')] = None,
    subway_minutes: Annotated[
        int | None,
        typer.Option(min=1, max=25, help='역세권: 지하철역까지 걸어서 이 분 안인 매물만 (분)')
    ] = None,
    owner_verified: Annotated[bool, typer.Option(help='집주인 확인 매물만')] = False,
    sort: Annotated[
        str | None,
        typer.Option(
            '--sort',
            help=f"정렬: {', '.join(SORT_TYPE_BY_NAME)}. 기본은 가까운순, 동 전체 검색이면 랭킹순. 가까운순 말고는 네이버 정렬 그대로 준다 (distance_km 순이 아님). 동 이름에 가까운순을 주면 동 중심 반경으로 찾는다",
        )
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """매물을 조회한다. 주소·역·단지는 그 지점 반경 안을 가까운 순으로, 동 이름은 그 동 전체를 랭킹순으로 찾는다.

    결과에 boundary(동 이름)가 있으면 법정동 경계 안 매물이고 전체 수(total)도 정확하다. radius_km 가 있으면
    그 반경 안이다 (zigbang search 와 같다). 같은 이름의 동·주소가 여러 곳이면 REGION_AMBIGUOUS 로 멈추니 시·구를 붙여 다시 검색한다.
    결과의 title 에 단지명이 들어 있다.

    조건은 모두 네이버 서버 필터로 거른다. 목록에는 방 수가 없어 room_type 은 null 이다
    (방 수는 listing 의 room_count). 빌라에는 단지로 등록된 연립·다세대도 들어간다.

    가까운 순은 약 200m 단위 근사다 (네이버가 매물을 지도 칸 단위로 주기 때문). 가장 가까운 매물이라고 단정하지 않는다.

    address 는 동까지다 (네이버 목록이 번지를 주지 않음). 번지까지 있는 주소는 listing 에서.

    예: jibsa naver search listings 역삼동 -t 오피스텔 --trade 월세 --deposit-max 3000 --rent-max 150
    """
    # 단지·재개발 구역 매물 목록이 받지 않는 지역 검색 조건 (기본값이면 주지 않은 것으로 None)
    area_options = {
        '--lat': lat, '--lng': lng, '--radius': radius,
        '--type': property_type, '--manage-cost-min': manage_cost_min, '--manage-cost-max': manage_cost_max,
        '--room': room, '--area-min': area_min, '--area-max': area_max,
        '--floor': floor, '--direction': direction, '--bathroom': bathroom,
        '--facility': facility, '--one-room-shape': one_room_shape, '--move-in': move_in,
        '--loan': loan, '--household-min': household_min, '--household-max': household_max,
        '--parking': parking, '--entrance': entrance,
        '--building-age-min': building_age_min, '--building-age-max': building_age_max,
        '--subway-minutes': subway_minutes,
        '--area-basis': None if area_basis == '전용' else area_basis,
        '--photo-only': photo_only or None,
        '--owner-verified': owner_verified or None,
    }
    if redevelopment is not None:
        _reject_options('--redevelopment', {
            '지역 이름(QUERY)': query, '--complex': complex_, '--pyeong': pyeong, '--dong': dong, **area_options,
        })
        conditions, trade_notes = _trade_conditions(
            trade, sort or '랭킹순', deposit_min, deposit_max, rent_min, rent_max, price_min, price_max,
        )
        _search_redevelopment_listings(
            redevelopment, conditions, trade_notes, sort=sort or '랭킹순', limit=limit, pretty=pretty,
        )
        return
    if complex_ is not None:
        _reject_options('--complex', {'지역 이름(QUERY)': query, **area_options})
        conditions, trade_notes = _trade_conditions(
            trade, sort or '랭킹순', deposit_min, deposit_max, rent_min, rent_max, price_min, price_max,
        )
        _search_complex_listings(
            complex_, conditions, trade_notes, pyeong=pyeong, dong=dong, sort=sort or '랭킹순', limit=limit, pretty=pretty,
        )
        return
    if pyeong is not None or dong is not None:
        raise typer.BadParameter('--pyeong·--dong은 --complex와 함께 사용하세요', param_hint='--complex')
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    conditions, trade_notes = _listing_conditions(
        property_type=property_type, trade=trade, sort=sort,
        deposit_min=deposit_min, deposit_max=deposit_max, rent_min=rent_min, rent_max=rent_max,
        price_min=price_min, price_max=price_max, manage_cost_min=manage_cost_min, manage_cost_max=manage_cost_max,
        room=room, area_min=area_min, area_max=area_max, area_basis=area_basis, floor=floor, direction=direction,
        bathroom=bathroom, facility=facility, one_room_shape=one_room_shape, move_in=move_in, loan=loan,
        photo_only=photo_only, household_min=household_min, household_max=household_max, parking=parking,
        entrance=entrance, building_age_min=building_age_min, building_age_max=building_age_max,
        subway_minutes=subway_minutes, owner_verified=owner_verified,
    )

    # 지역 이름을 찾는 요청과 매물 요청이 같은 클라이언트를 쓴다
    with handle_errors(SOURCE), NaverClient() as client:
        region, kind, notes = _resolve_location(client, query, lat, lng, radius)
        # 동 이름이면 동 전체를 찾는다. 반경이나 가까운순을 직접 주면 그 뜻대로 동 중심 반경으로 찾는다
        whole_dong = _whole_dong(region, kind, radius) and sort != '가까운순'
        dongs = [region]
        if whole_dong and region.ga_base is not None:
            # '○가' 로 나뉜 동(성수동)은 직방처럼 모두 찾아 합친다. 한 곳만 찾았다는 안내는 뺀다
            dongs = ga_dong_regions(client, region)
            if len(dongs) > 1 and region.ga_note in notes:
                notes.remove(region.ga_note)
                region = _merged_region(region, dongs)
        if whole_dong:
            notes.append(WHOLE_DONG_NOTE.format(name=region.name))

        result = search_area(
            client,
            region.lat,
            region.lng,
            conditions=conditions,
            radius_km=radius or DEFAULT_RADIUS_KM,
            sort=sort or ('랭킹순' if whole_dong else '가까운순'),
            legal_division_codes=[dong.legal_division_code for dong in dongs if dong.legal_division_code] if whole_dong else None,
            limit=limit,
        )
        # 직방처럼 어디를 얼마나 찾았는지 함께 준다. 서비스는 좌표만 받아
        # 지역을 모르므로(단지 매물 목록과 결과 모델을 같이 쓴다) 지역을 아는 여기서 붙인다
        emit(
            {
                'region': region.model_dump(mode='json'),
                **_search_scope(region, whole_dong, radius),
                **result.model_dump(mode='json'),
            },
            pretty,
            notes=trade_notes + notes + result.notes,
        )
