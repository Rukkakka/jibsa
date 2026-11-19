import re

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
    HintedBadParameter,
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
from jibsa.core.errors import (
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.geo import DEFAULT_RADIUS_KM
from jibsa.core.korean import (
    is_district_code,
    is_ri_code,
)
from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.service.common import (
    AREA_BASES,
    ENTRANCE_CODE_BY_NAME,
    MAX_LIST_LIMIT,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    PERIOD_MONTHS_BY_NAME,
    SALE_JEONSE_CODE_BY_NAME,
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
    WIDE_REGION_NOTE_MARK,
    NaverRegion,
    city_district_names,
    legal_division_code_at,
    list_regions,
    only_district_of_province,
    resolve_complex_number,
    resolve_redevelopment_number,
    resolve_search_region,
)
from jibsa.providers.naver.service.school import (
    MAX_SCHOOL_COMPLEX_LIMIT,
    SCHOOL_COMPLEX_SORT_TYPE_BY_NAME,
    get_school,
    list_school_complexes,
)
from jibsa.providers.naver.service.search import (
    AREA_COMPLEX_CODES_BY_TYPE,
    BATHROOM_CODE_BY_NAME,
    COMPLEX_LIST_SORT_TYPE_BY_NAME,
    DEFAULT_SEARCH_PROPERTY_TYPES,
    DIRECTION_FILTER_CODE_BY_NAME,
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
    NATIONWIDE_CODE,
    NATIONWIDE_NAME,
    TREND_PERIOD_BY_NAME,
    TREND_PYEONG_RANGES,
    get_district_trend,
)

from typing import (
    Annotated,
    Literal,
)


SOURCE: str = 'naver'
TRADE_TYPES: tuple[str, ...] = tuple(TRADE_CODE_BY_NAME)
# 지역 이름과 좌표를 함께 주면 좌표로 찾는다. 이름 주변을 찾았다고 오해하지 않게 알린다
COORDINATES_OVER_QUERY_NOTE: str = note(
    '범위', "--lat/--lng 좌표를 검색 중심으로 썼습니다. '{query}' 는 위치를 찾는 데 쓰지 않고 region.name 에만 붙였습니다",
)
PROPERTY_TYPES: tuple[str, ...] = tuple(SEARCH_CODES_BY_PROPERTY)
# str.isdigit·isalnum 은 '²'·한글도 통과시켜 int() 가 PARSE_ERROR 를 내거나 요청 모델의 영어 오류가 나온다
NUMBER_PATTERN: re.Pattern[str] = re.compile(r'[0-9]+')
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(r'[A-Za-z0-9]+')
# school --complexes 의 기본 정렬·단지 수 (웹 학교 상세와 같다). --sort·--limit 을 --complexes 없이 줬는지 가리려고 옵션 기본값은 None 이다
SCHOOL_COMPLEX_DEFAULT_SORT: str = '거리순'
SCHOOL_COMPLEX_DEFAULT_LIMIT: int = 20

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
    """단지 번호면 그대로, 이름이면 네이버 단지 검색으로 번호를 찾는다 (빌라 단지인지와 안내를 함께 준다). 후보가 여럿이면 REGION_AMBIGUOUS."""
    # 붙여 넣은 번호의 앞뒤 공백(' 8928')을 먼저 떼야 번호를 이름으로 찾지 않는다
    complex_ = complex_.strip()
    if NUMBER_PATTERN.fullmatch(complex_) is None:
        return resolve_complex_number(client, complex_)
    if int(complex_) < 1:
        raise typer.BadParameter('단지 번호는 1 이상입니다', param_hint='COMPLEX')
    return int(complex_), None, []


def _redevelopment_number(client: NaverClient, area: str, param_hint: str) -> tuple[int, list[str]]:
    """구역 번호면 그대로, 이름이면 네이버 재개발 구역 검색으로 번호를 찾는다 (안내를 함께 준다). 후보가 여럿이면 REGION_AMBIGUOUS.

    Args:
        param_hint: 구역을 받은 인자·옵션 이름 (번호가 0 일 때의 사용법 오류에 쓴다).
    """
    # 붙여 넣은 번호의 앞뒤 공백(' 10017678')을 먼저 떼야 번호를 이름으로 찾지 않는다
    area = area.strip()
    if NUMBER_PATTERN.fullmatch(area) is None:
        return resolve_redevelopment_number(client, area)
    if int(area) < 1:
        raise typer.BadParameter('재개발 구역 번호는 1 이상입니다', param_hint=param_hint)
    return int(area), []


def _split_dongs(values: list[str] | None) -> list[str]:
    """`--dong 101 --dong 102동` 과 `--dong 101,102동` 을 모두 받는다 (이름 확인은 동 목록 조회 뒤)."""
    return list(dict.fromkeys(part.strip() for value in values or [] for part in value.split(',') if part.strip()))


# 직방(zigbang search)의 동 경계 검색과 같은 안내. 동과 시·군·구 경계 검색이 함께 쓴다
WHOLE_BOUNDARY_NOTE: str = note('범위', '{name} 경계 안을 찾았습니다 (반경으로 찾으려면 --radius)')
# 시·군·구가 하나뿐인 시·도(세종)를 그 시·군·구 경계로 찾았다는 안내. 시·도 코드는 경계로 보낼 수 없어 그 아래 하나뿐인 시·군·구를 쓴다
SOLE_DISTRICT_NOTE: str = note(
    '범위', '시·군·구가 {district} 하나뿐이라 {name} 경계 안을 찾았습니다 (반경으로 찾으려면 --radius)',
)
# 반경 없이 시·군·구 경계 전체(GUN)로 찾는 지역 이름의 끝말. 구·군은 바로 경계로 찾는다. 시는 구가 없을 때만 경계로 찾는다.
# 구 있는 시(성남시 4113000000)는 시 코드 + GUN 이 오류 없이 0건이라 코드·이름만으로 구 없는 시(구리시 4131000000)와 가를 수
# 없다 (2026-11-18 실측). 그래서 시는 `city_district_names` 로 구가 있는지 본다 (요청 1회)
DISTRICT_NAME_SUFFIXES: tuple[str, ...] = ('구', '군')
CITY_NAME_SUFFIX: str = '시'
# search listings 의 단지·재개발 모드가 받는 옵션. 받지 않는 옵션을 준 에러의 힌트에 쓴다 (`_reject_options`)
MODE_ACCEPTED_OPTIONS: dict[str, str] = {
    '--complex': (
        '단지 모드는 거래 유형·평형(--pyeong)·동(--dong)·가격·정렬·--limit 만 받습니다. 면적으로 고르려면 '
        'naver complex <단지> 결과의 pyeongs[] 에서 exclusive_m2 로 평형 번호(number)를 찾아 --pyeong 으로 주세요'
    ),
    '--redevelopment': '재개발 모드는 거래 유형·가격·정렬·--limit 만 받습니다',
}
NO_PET_FILTER: str = '네이버에는 반려동물 조건이 없습니다 (직방 --condition 반려동물, 당근 --option 반려동물가능)'
# 없앤 search listings --sort 가까운순 (지역 검색에만 안내한다). 지도 칸 여러 개의 매물을 합쳐 거리로 다시 세운 목록이라 네이버 웹에 없었다
NEAREST_SORT_HINT: str = (
    '네이버 정렬에는 거리순이 없어 가까운순을 없앴습니다. 가까운 매물은 --radius 를 줄이거나 결과의 distance_km 로 고르세요'
)
AREA_IN_M2: str = '네이버 면적은 ㎡ 로 주세요: --area-min·--area-max (1평 = 3.3058㎡)'
# 지역 매물 검색에 다른 소스 표현을 옮겨 쓴 사용법 오류의 힌트 (UsageHints). 이 명령의 다른 옵션 값과, 뜻이 같은 다른 소스
# 표현이다 (직방 --room 오픈형원룸·--condition 즉시입주, 당근 --option 주차가능·--room-count 2개). '2개'·'3개' 는 욕실 수
# 값과 겹치지만 거절되는 곳은 --room 이 흔해 방 수로 안내한다. 네이버는 반지하를 따로 두지 않고 지하층(B1)으로 준다
LISTING_HINTS: UsageHints = UsageHints(
    by_value={
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
        '지상': '--floor 1층,저층,중층,고층,탑층',
        '2개': '--room 투룸',
        '3개': '--room 쓰리룸',
        '4개이상': '--room 포룸이상',
        '반려동물': NO_PET_FILTER,
        '반려동물가능': NO_PET_FILTER,
        '주택': '-t 단독·다가구',
    },
    by_option_value={
        # 숫자만 준 값은 옵션마다 뜻이 달라 그 옵션에서만 안내한다. 한 표에 두면 --room 2 에 --bathroom 2개 를 안내했다
        '--room': {'1': '--room 원룸', '2': '--room 투룸', '3': '--room 쓰리룸', '4': '--room 포룸이상'},
        # 직방 --bathroom 은 숫자(3 은 3개 이상)다
        '--bathroom': {'1': '--bathroom 1개', '2': '--bathroom 2개', '3': '--bathroom 3개,4개이상'},
        # 없앤 --sort 가까운순의 안내 (지역 검색에만)
        '--sort': {'가까운순': NEAREST_SORT_HINT},
    },
    by_option={
        '--condition': '--facility (시설) 이나 --move-in (입주) · --direction (방향)',
        '--option': '--facility',
        '--room-count': '--room 투룸',
        '--structure': '--one-room-shape 오픈형',
        '--move-in-now': '--move-in 바로입주',
        '--city': "네이버에는 --city 가 없습니다. 지역 이름 앞에 시·구를 붙이세요 (예: '강남구 신사동')",
        '--details': '네이버 목록에는 상세를 붙이지 않습니다. 고른 매물만 jibsa naver listing <id> 로 보세요',
        '--expand': '주변까지 보려면 --radius 로 반경을 넓히세요 (최대 3km)',
        '--with-manage-cost': '네이버는 월세와 관리비를 따로 거릅니다: --rent-max 와 --manage-cost-max',
        '--deal': '네이버에는 직거래 조건이 없습니다. 직거래는 jibsa daangn search listings --deal 직거래 로 찾으세요',
        '--area-pyeong-min': AREA_IN_M2,
        '--area-pyeong-max': AREA_IN_M2,
    },
)
# 사용법 오류가 난 명령(command_path)으로 힌트 표를 찾는다 (jibsa.cli.app.run)
USAGE_HINTS: dict[str, UsageHints] = {'jibsa naver search listings': LISTING_HINTS}


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
    """모드(--complex·--redevelopment)가 받지 않는 옵션을 주었으면 한꺼번에 알린다. 값이 None 이면 주지 않은 것이다.

    힌트에 그 모드가 받는 옵션을 적는다. `--help` 만 알리면 단지 매물을 면적(--area-min)으로 거르려던 에이전트가 평형
    번호(--pyeong)로 고르는 법을 몰라 다시 틀렸다 (2026-10-24 에이전트 검증: 헬리오시티 84㎡ 매물).
    """
    invalid = [name for name, value in options.items() if value is not None]
    if invalid:
        raise HintedBadParameter(
            f"{mode}와 함께 사용할 수 없습니다: {', '.join(invalid)}",
            mode,
            f"{MODE_ACCEPTED_OPTIONS[mode]}. 'jibsa naver search listings --help' 로 사용법을 확인하세요",
        )


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
    listing_search: bool = False,
) -> tuple[NaverRegion, str, list[str]]:
    """검색 위치, 그 종류, 안내. 좌표를 주면 좌표(종류 '좌표')가 이름보다 앞선다.

    반경으로 찾지 않는 명령(trend)은 `radius_search=False` 로 '반경 안만 검색했습니다' 안내를 받지 않는다.
    `listing_search` 는 `search listings` 에서만 켠다 (단지 이름 후보에 `--complex` 힌트를 붙인다, `resolve_search_region`).

    이름은 네이버 주소 검색 → 자동완성(동 → 역 → 단지)으로 찾는다. 못 찾으면 REGION_NOT_FOUND, 여러 곳이면
    REGION_AMBIGUOUS, 막히면 RATE_LIMITED 로 끝낸다 (다른 소스로 대신 찾지 않는다).
    """
    if lat is not None and lng is not None:
        notes = [COORDINATES_OVER_QUERY_NOTE.format(query=query)] if query is not None else []
        return NaverRegion(name=query or f'{lat},{lng}', lat=lat, lng=lng), '좌표', notes
    # 좌표가 없으면 _require_location 이 이름을 요구했다
    assert query is not None
    return resolve_search_region(
        client, query, (radius or DEFAULT_RADIUS_KM) if radius_search else None, listing_search=listing_search,
    )


def _is_city_region(region: NaverRegion, kind: str) -> bool:
    """구가 있는지 물어볼 시 이름인가. 종류가 '지역'이고 법정동 코드가 시·군·구 단위이며 이름이 시(`CITY_NAME_SUFFIX`)로 끝난다."""
    code = region.legal_division_code
    return kind == '지역' and code is not None and is_district_code(code) and region.name.endswith(CITY_NAME_SUFFIX)


def _districts_of_city(client: NaverClient, region: NaverRegion, kind: str) -> list[str] | None:
    """구가 있는 시(성남시)면 그 구 이름 목록. 시 이름이 아니거나 구 없는 시면 [] (요청 없음·1회).

    시 이름(`_is_city_region`)만 `city_district_names` 로 구를 묻는다 (요청 1회). 조회가 실패하거나 구 이름을 모르면 None 이다.
    """
    code = region.legal_division_code
    if code is None or not _is_city_region(region, kind):
        return []
    return city_district_names(client, code)


def _boundary_unit(
    client: NaverClient, region: NaverRegion, kind: str, radius: float | None,
) -> tuple[str | None, list[str] | None]:
    """반경을 주지 않았을 때 반경 대신 경계 안 전체로 찾을 지역이면 그 경계의 단위('동' 또는 '시·군·구'), 아니면 None. 구 있는 시면 그 구 이름도 준다.

    동 이름(종류 '동')은 동 경계(EUP)다. 시·군·구(GUN)는 종류 '지역' 중 법정동 코드가 시·군·구 단위이고 이름이 구·군이거나
    구 없는 시인 곳이다 (시·도는 아니다, `DISTRICT_NAME_SUFFIXES`). 이름이 시면 구가 있는지 `city_district_names` 로 1회
    물어 구가 있으면 경계가 아니라 None 과 그 구 이름을 준다 (구 있는 시는 시 전체로 찾을 수 없다). 모두 법정동 코드가 있을
    때만이다.

    두 번째 값은 구 이름 목록이고 [] 는 알릴 구 이름이 없다는 뜻이다 (구 있는 시가 아니거나, 반경을 줘 구를 확인하지 않았다).
    구가 있는지 확인하지 못하면 (None, None) 이다 (구가 있는 시인지 모른다. 시 전체로 찾으면 오류 없이 0건일 수 있어 경계로
    찾지 않는다).
    """
    code = region.legal_division_code
    if radius is not None or code is None:
        return None, []
    if kind == '동':
        return '동', []
    if kind != '지역' or not is_district_code(code):
        return None, []
    if region.name.endswith(DISTRICT_NAME_SUFFIXES):
        return '시·군·구', []
    if not _is_city_region(region, kind):
        return None, []
    districts = _districts_of_city(client, region, kind)
    if districts is None:
        return None, None
    if districts:
        return None, districts
    # 구 없는 시는 경계로 찾는다
    return '시·군·구', []


def _is_province_region(region: NaverRegion, kind: str) -> bool:
    """시·도 이름인가. 종류가 '지역'이고 법정동 코드 앞 두 자리 뒤가 모두 0 이다 (3600000000, `_wide_region_unit` 과 같은 판정)."""
    code = region.legal_division_code
    return kind == '지역' and code is not None and len(code) == 10 and code[2:] == '0' * 8


def _sole_district(
    client: NaverClient, region: NaverRegion, kind: str, radius: float | None,
) -> tuple[str, str] | None | Literal['unknown']:
    """반경을 주지 않은 시·도 이름이 시·군·구 하나뿐인 시·도(세종)면 그 (시·군·구 코드, 이름), 조회가 실패하면 'unknown', 그 밖은 None.

    시·도 이름일 때만 `only_district_of_province` 로 묻는다 (요청 1회). 서울·경기도처럼 시·군·구가 여럿이면 None 이라 지금처럼
    중심 반경으로 찾는다.
    """
    code = region.legal_division_code
    if radius is not None or code is None or not _is_province_region(region, kind):
        return None
    return only_district_of_province(client, code)


def _search_scope(region: NaverRegion, whole: bool, radius: float | None) -> dict[str, object]:
    """어디를 찾았는지. 경계로 찾았으면 boundary(동·시·군·구 이름), 아니면 radius_km 다 (직방 search 와 같다)."""
    return {'boundary': region.name} if whole else {'radius_km': radius or DEFAULT_RADIUS_KM}


def _area_location(
    client: NaverClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
    radius: float | None,
    *,
    listing_search: bool = False,
) -> tuple[NaverRegion, list[str], str | None, dict[str, object]]:
    """지역 안을 찾는 명령(search listings·complexes·redevelopment)의 검색 위치, 안내, 경계 법정동 코드, 찾은 범위.

    동·구·군과 구 없는 시 이름이고 반경을 주지 않았으면 그 경계 안 전체를 찾아 법정동 코드를 주고(단위는 코드로 정해진다,
    `boundary_filter`), 아니면 코드가 None 이라 반경 안을 찾는다. 구 있는 시(성남시)는 시 전체로 찾을 수 없어 반경으로 찾고
    구 이름을 알린다. 구가 있는 시인지 확인하지 못해도 반경으로 찾고 그 사실을 알린다 (이름이 시일 때만 요청 1회 늘어난다).
    시·도 이름은 시·군·구가 하나뿐인 시·도(세종)면 그 시·군·구 경계 전체로 찾는다 (이름이 시·도일 때만 요청 1회 늘어난다).
    서울·경기도처럼 시·군·구가 여럿이면 중심 반경이고, 하나뿐인지 확인하지 못해도 반경으로 찾고 그 사실을 알린다.
    범위는 결과에 붙이는 boundary 또는 radius_km 다 (`_search_scope`).
    """
    region, kind, notes = _resolve_location(client, query, lat, lng, radius, listing_search=listing_search)
    sole = _sole_district(client, region, kind, radius)
    if isinstance(sole, tuple):
        # 시·군·구가 하나뿐인 시·도(세종)는 그 시·군·구 경계가 시·도 전체다. 지역 해석의 '시·도 단위의 넓은 지역이라 … 반경 안만
        # 검색했습니다' 안내는 경계로 찾으면 맞지 않아 뺀다. 결과 범위의 이름은 사용자가 준 이름이다
        district_code, district_name = sole
        notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
        notes.append(SOLE_DISTRICT_NOTE.format(name=region.name, district=district_name))
        return region, notes, district_code, _search_scope(region, True, radius)
    if sole == 'unknown':
        notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
        notes.append(note(
            '실패',
            f"'{query}': 시·도 아래 시·군·구를 확인하지 못해 시·도 전체 대신 중심({region.address or region.name})에서 "
            f"반경 {DEFAULT_RADIUS_KM:g}km 안만 찾았습니다. 동·역 이름으로 좁혀 검색하세요",
        ))
        return region, notes, None, _search_scope(region, False, radius)
    unit, city_districts = _boundary_unit(client, region, kind, radius)
    if unit is None:
        if city_districts is None:
            # 지역 해석이 붙인 '넓은 지역이라 … 반경 안만 검색했습니다' 안내 대신 구를 확인하지 못해 반경으로 찾았다는 이유를 알린다
            # (이유가 다른 두 안내를 함께 내지 않는다)
            notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
            notes.append(note(
                '실패',
                f"'{query}': 구가 있는 시인지 확인하지 못해 시 전체 대신 중심({region.address or region.name})에서 "
                f"반경 {DEFAULT_RADIUS_KM:g}km 안만 찾았습니다. "
                f"jibsa naver regions '{region.name}' 로 구 이름이 나오면 구 이름으로 찾으세요",
            ))
        elif city_districts:
            # 지역 해석이 붙인 '시·군·구 단위의 넓은 지역이라 …' 안내 대신 구 있는 시라서라는 이유와 구 이름을 알린다
            notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
            notes.append(note(
                '범위',
                f"'{query}': 구가 있는 시라 시 전체로 찾을 수 없어 중심({region.address or region.name})에서 "
                f"반경 {DEFAULT_RADIUS_KM:g}km 안만 검색했습니다. 구 이름({', '.join(city_districts)})으로 찾으면 그 구 전체를 찾습니다",
            ))
        elif radius is not None and kind == '지역' and region.legal_division_code and is_district_code(region.legal_division_code):
            # 지역 해석의 '시·군·구 단위의 넓은 지역이라 …' 안내는 --radius 를 줬기 때문에 반경으로 찾았다는 사실과 어긋난다.
            # 그 안내가 있었을 때만 바꾼다 (구 있는 시인지는 묻지 않아 시 경우도 한 문장에 담는다)
            if any(WIDE_REGION_NOTE_MARK in text for text in notes):
                notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
                notes.append(note(
                    '범위',
                    f"'{query}': --radius 를 줘 중심({region.address or region.name})에서 반경 {radius:g}km 안만 검색했습니다. "
                    '--radius 를 빼면 그 구·군·시 경계 전체를 찾습니다 (구가 있는 시는 구 이름으로 찾으세요)',
                ))
        return region, notes, None, _search_scope(region, False, radius)
    if unit == '시·군·구':
        # 지역 해석은 시·군·구 이름이면 늘 '반경 안만 검색했습니다' 를 붙인다. 경계로 찾으면 맞지 않는 안내라 뺀다
        notes = [text for text in notes if WIDE_REGION_NOTE_MARK not in text]
    notes.append(WHOLE_BOUNDARY_NOTE.format(name=region.name))
    return region, notes, region.legal_division_code, _search_scope(region, True, radius)


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
        list[str] | None,
        typer.Option('--pyeong', metavar='<int>', help='평형 번호 (평형 ID, 평수 아님; 결과의 pyeongs[].number). 주면 매물 수·호가 범위를 그 평형만으로 센다. 하나만 주면 그 평형의 관리비·시세·최근 3년(없으면 5년) 실거래 요약과 3개월 평균 실거래·평당가도 붙인다 (요청 최대 8회 추가). 반복하거나 쉼표로 구분')
    ] = None,
    dong: Annotated[
        list[str] | None,
        typer.Option('--dong', help='동 이름 (예: 104 또는 104동). 주면 매물 수·호가 범위를 그 동만으로 센다. 반복하거나 쉼표로 구분')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """단지 정보·거래유형별 매물 수·호가 범위·평형 목록·평형 묶음(pyeong_groups). 결과의 complex_number 를 search listings --complex·real-price 에 넘긴다.

    예: jibsa naver complex 개포자이 --pyeong 1   # 1번 평형 매물 수·호가·관리비·시세·실거래 요약
    """
    dong_names = _split_dongs(dong)
    pyeong_numbers = split_ints(pyeong, '--pyeong')
    with handle_errors(SOURCE), NaverClient() as client:
        complex_number, villa, notes = _complex_number(client, complex_)
        summary = get_complex(client, complex_number, pyeong_numbers=pyeong_numbers, dong_names=dong_names, villa=villa)
        scope: list[str] = []
        if pyeong_numbers:
            scope.append(f"{', '.join(map(str, pyeong_numbers))}번 평형")
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
        typer.Argument(help="주소·동·구·역·단지 이름 (예: 역삼동, 성동구, 강남역, '역삼동 719-28'). 동·구·군·구 없는 시·세종 이름이면 그 경계 안 단지 전체. --lat/--lng 를 주면 생략")
    ] = None,
    lat: Annotated[float | None, typer.Option(help='중심 위도')] = None,
    lng: Annotated[float | None, typer.Option(help='중심 경도')] = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option('--type', '-t', help=f"단지 유형: {', '.join(AREA_COMPLEX_CODES_BY_TYPE)} (빌라는 단지로 등록된 연립·다세대). 반복하거나 쉼표로 구분. 기본 아파트")
    ] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동·구·군·구 없는 시·세종 이름으로 찾았을 때 주면 경계 전체 대신 그 중심 반경으로 찾는다')
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

    위치는 naver search listings 와 같이 찾는다. 동·구·군·구 없는 시·세종 이름이면 그 경계 안 단지 전체(boundary), 그 밖은 반경 안(radius_km)이다.

    예: jibsa naver search complexes 역삼동 --sort 세대수순
    """
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    property_types = split_csv(property_type, tuple(AREA_COMPLEX_CODES_BY_TYPE), '--type')
    sort = check_choice(sort, COMPLEX_LIST_SORT_TYPE_BY_NAME, '--sort')
    validate_ranges(('household', household_min, household_max), ('building-age', building_age_min, building_age_max))

    with handle_errors(SOURCE), NaverClient() as client:
        region, notes, code, scope = _area_location(client, query, lat, lng, radius)
        result = list_area_complexes(
            client,
            region.lat,
            region.lng,
            radius_km=radius or DEFAULT_RADIUS_KM,
            legal_division_code=code,
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
            {'region': region.model_dump(mode='json'), **scope, **result.model_dump(mode='json')},
            pretty,
            notes=notes + result.notes,
        )


def _trade_conditions(
    trade: list[str] | None,
    deposit_min: int | None,
    deposit_max: int | None,
    rent_min: int | None,
    rent_max: int | None,
    price_min: int | None,
    price_max: int | None,
) -> tuple[NaverTradeConditions, list[str]]:
    """단지·재개발 구역 매물 목록의 거래 유형·가격을 확인하고 조건 묶음과 거래 유형 추론 안내를 준다.

    지역 검색보다 받는 조건이 적다.
    """
    trade_types, trade_notes = _price_trade_types(trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max)
    validate_ranges(('deposit', deposit_min, deposit_max), ('rent', rent_min, rent_max), ('price', price_min, price_max))
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
    fields: list[str] | None,
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
            fields=fields,
            fields_source=result,
        )


def _search_redevelopment_listings(
    area: str,
    conditions: NaverTradeConditions,
    trade_notes: list[str],
    *,
    sort: str,
    limit: int,
    pretty: bool | None,
    fields: list[str] | None,
) -> None:
    """재개발 구역 하나(번호 또는 이름)의 매물 목록 (기본 네이버 랭킹 순). 가격 조건은 네이버 서버 필터로 거른다."""
    with handle_errors(SOURCE), NaverClient() as client:
        # 이름으로 찾았으면 고른 구역 번호를 함께 줘야 redevelopment 로 이어 조회할 수 있다
        area_number, notes = _redevelopment_number(client, area, '--redevelopment')
        result = list_redevelopment_articles(client, area_number, conditions=conditions, sort=sort, limit=limit)
        emit(
            {'redevelopment_number': area_number, **result.model_dump(mode='json')},
            pretty,
            notes=trade_notes + notes + result.notes,
            fields=fields,
            fields_source=result,
        )


@search_app.command('redevelopment')
def redevelopment_command(
    query: Annotated[
        str | None,
        typer.Argument(help='주소·동·구·역·단지 이름 (예: 한남동, 성동구, 한강진역). 동·구·군·구 없는 시·세종 이름이면 그 경계 안 구역 전체. --lat/--lng 를 주면 생략')
    ] = None,
    lat: Annotated[float | None, typer.Option(help='중심 위도')] = None,
    lng: Annotated[float | None, typer.Option(help='중심 경도')] = None,
    radius: Annotated[
        float | None,
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 동·구·군·구 없는 시·세종 이름으로 찾았을 때 주면 경계 전체 대신 그 중심 반경으로 찾는다')
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

    위치는 naver search listings 와 같이 찾는다. 동·구·군·구 없는 시·세종 이름이면 그 경계 안 구역 전체(boundary), 그 밖은 반경 안(radius_km)이다.
    네이버는 한 구역을 법정동마다 따로 등록하기도 해 같은 이름이 여러 번 나올 수 있다 (구역 번호 redevelopment_number 로
    구분한다. 반경 결과는 legal_division 도 다르지만 동·구·군·구 없는 시·세종 경계 결과의 legal_division 은 모두 그 경계다).

    예: jibsa naver search redevelopment 한남동
    """
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    trade_types = split_csv(trade, TRADE_TYPES, '--trade')
    sort = check_choice(sort, REDEVELOPMENT_SORT_TYPE_BY_NAME, '--sort')

    with handle_errors(SOURCE), NaverClient() as client:
        region, notes, code, scope = _area_location(client, query, lat, lng, radius)
        result = list_redevelopment_areas(
            client,
            region.lat,
            region.lng,
            radius_km=radius or DEFAULT_RADIUS_KM,
            legal_division_code=code,
            legal_division_name=(region.address or region.name) if code is not None else None,
            trade_types=trade_types,
            sort=sort,
            limit=limit,
        )
        emit(
            {'region': region.model_dump(mode='json'), **scope, **result.model_dump(mode='json')},
            pretty,
            notes=notes + result.notes,
        )


def _trend_district(
    client: NaverClient,
    query: str | None,
    lat: float | None,
    lng: float | None,
) -> tuple[str, str | None, list[str]]:
    """trend 가 추이를 볼 법정동 코드, 그 이름, 안내. 이름·좌표로 지역을 찾고 리·주소·역·좌표는 그 자리의 법정동으로 바꾼다.

    구 있는 시(성남시)는 네이버가 시 코드의 추이를 매물 수·거래 수 모두 0 으로 줘서(2026-11-18 실측) 구 이름을 알리며
    REGION_AMBIGUOUS 로 멈춘다. 이름이 시일 때만 구가 있는지 묻는 요청 1회가 는다.
    """
    region, kind, notes = _resolve_location(client, query, lat, lng, None, radius_search=False)
    districts = _districts_of_city(client, region, kind)
    if districts:
        # 리뷰 오탐 (2026-11-18): message 는 REGION_AMBIGUOUS 공통 문구('… 해당하는 곳이 N곳'), 시 → 구 안내는 hint 가 한다
        raise RegionAmbiguousError(
            query or region.name,
            candidates=districts,
            total=len(districts),
            hint=(
                '구가 있는 시는 네이버가 시 전체 추이를 주지 않습니다. 구를 골라 다시 부르세요 '
                f"(예: jibsa naver trend '{districts[0]}')"
            ),
        )
    if districts is None:
        notes.append(note(
            '실패',
            f"'{region.name}': 구가 있는 시인지 확인하지 못했습니다. 구가 있는 시면 네이버가 시 추이를 0 으로 주니, "
            f"값이 모두 0 이면 jibsa naver regions '{region.name}' 로 구 이름을 보고 구 이름으로 다시 부르세요",
        ))
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
        notes.append(note('범위', f"'{region.name}': 리 단위 추이는 네이버가 주지 않아 {division} 추이입니다"))
    elif at_spot:
        notes.append(note('범위', f"'{region.name}' 자리의 법정동({division}) 추이입니다"))
    return code, division, notes


@app.command('trend')
def trend_command(
    query: Annotated[
        str | None,
        typer.Argument(help=f'동·구 이름 (예: 역삼동, 강남구) 또는 {NATIONWIDE_NAME}. 역·주소·단지면 그 자리의 법정동. --lat/--lng 를 주면 생략')
    ] = None,
    lat: Annotated[float | None, typer.Option(help='위도 (그 자리의 법정동)')] = None,
    lng: Annotated[float | None, typer.Option(help='경도 (그 자리의 법정동)')] = None,
    trade: Annotated[
        str,
        typer.Option('--trade', help=f"거래 유형: {', '.join(SALE_JEONSE_CODE_BY_NAME)} (네이버가 월세 추이는 주지 않는다)")
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

    전국은 지역을 찾지 않고 네이버 홈의 전국(시·도 전체) 추이를 그대로 준다.

    예: jibsa naver trend 역삼동 --trade 전세 --period 3년 --pyeong-range 30
    예: jibsa naver trend 전국
    """
    _require_location(query, lat, lng)
    trade = check_choice(trade, SALE_JEONSE_CODE_BY_NAME, '--trade')
    period = check_choice(period, TREND_PERIOD_BY_NAME, '--period')
    if pyeong_range is not None:
        pyeong_range = check_choice(pyeong_range, TREND_PYEONG_RANGES, '--pyeong-range')

    with handle_errors(SOURCE), NaverClient() as client:
        division: str | None
        notes: list[str]
        # 좌표를 함께 주면 좌표가 이름보다 앞서(`_resolve_location`) '전국' 도 이름으로 쓰지 않는다
        if query is not None and query.strip() == NATIONWIDE_NAME and lat is None and lng is None:
            code, division, notes = NATIONWIDE_CODE, NATIONWIDE_NAME, []
        else:
            code, division, notes = _trend_district(client, query, lat, lng)
        trend = get_district_trend(client, code, trade_type=trade, period=period, pyeong_range=pyeong_range)
        if trend.trade_count is not None:
            # 거래는 계약 주에 세어지는데 신고가 계약 뒤 30일 안이라 최근 주일수록 덜 모였다. 안내가 없으면 줄어드는 끝을
            # 거래가 줄었다고 전했다 (2026-11-11 LLM 사용 시험·실측: 마포구 6개월 주간 거래 19·13·6·0, latest 0)
            notes.append(note(
                '참고',
                '실거래는 계약 뒤 30일 안에 신고해 최근 4주쯤의 trade_count 는 신고가 덜 모여 적게 나옵니다 '
                '(마지막 주 0건도 거래가 없었다는 뜻이 아닐 수 있습니다). 거래 흐름은 한 달 넘게 지난 주로 보세요',
            ))
        emit({'legal_division': division, **trend.model_dump(mode='json')}, pretty, notes=notes + trend.notes)


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
        typer.Option('--period', help=f"기간: {', '.join(PERIOD_MONTHS_BY_NAME)}. 주면 페이지 대신 그 기간 안 거래를 모두 준다. --pages·--group 과 함께 쓸 수 없다")
    ] = None,
    group: Annotated[
        bool,
        typer.Option('--group', help='같은 평형 묶음(complex 결과의 pyeong_groups)의 실거래를 함께 준다. 거래마다 평형은 알 수 없다. --period·--around-km 과 함께 쓸 수 없다')
    ] = False,
    around_km: Annotated[
        float | None,
        typer.Option(
            '--around-km', min=0.1, max=1.0,
            help='빌라 단지의 주변 실거래 범위 (km, 단지 중심에서 사방으로). 빼면 네이버 웹 작은 지도 크기(서울에서 남북 약 190m·동서 약 365m, 남쪽일수록 조금 넓다). 아파트 단지에는 쓸 수 없다. --group 과 함께 쓸 수 없다',
        )
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """평형별 실거래가 (국토부 신고 기준, 최근 순). 빌라 단지는 웹 빌라 실거래 탭의 두 칸도 준다: 최근 5년 평당 실거래가(매매·전세)와 주변 실거래(범위 안 10건까지).

    요청은 아파트 단지 1회+쪽 수(거래가 없으면 단지 종류 확인 1~2회 더)이고, 빌라 단지는 평당 실거래가 1회(월세는 없음)·단지 좌표 1회·주변 실거래 1회가 더 든다.

    예: jibsa naver real-price 12345 --pyeong 2 --trade 전세 --period 3년
    예: jibsa naver real-price 12345 --pyeong 2 --group --pages 2
    예: jibsa naver real-price 572549 --pyeong 4 --trade 전세 --around-km 0.5
    """
    require_finite('--around-km', around_km)
    trade_types = split_csv([trade], ('매매', '전세', '월세'), '--trade')
    if len(trade_types) != 1:
        raise typer.BadParameter('실거래가는 거래 유형을 하나만 받습니다 (매매, 전세, 월세 중 하나)', param_hint='--trade')
    if period is not None:
        period = check_choice(period, PERIOD_MONTHS_BY_NAME, '--period')
        if pages is not None:
            raise typer.BadParameter('--period 와 --pages 는 함께 쓸 수 없습니다. 기간이면 --period 만 주세요', param_hint='--pages')
        if group:
            raise typer.BadParameter('--group 과 --period 는 함께 쓸 수 없습니다. 묶음 실거래는 --pages 로 페이지를 넘기세요', param_hint='--group')
    if group and around_km is not None:
        # 평형 묶음은 아파트 단지에만 있고 주변 실거래는 빌라 단지에만 있어, 어느 단지에도 함께 쓸 수 없다
        raise typer.BadParameter('--group 은 아파트 단지, --around-km 은 빌라 단지에만 쓸 수 있어 함께 쓸 수 없습니다. 하나만 주세요', param_hint='--around-km')
    with handle_errors(SOURCE), NaverClient() as client:
        result = get_real_prices(
            client, complex_number, pyeong, trade_type=trade_types[0], pages=pages or 1, period=period, group=group,
            around_km=around_km,
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
        typer.Option('--period', help=f"기간: {', '.join(PERIOD_MONTHS_BY_NAME)}")
    ] = '1년',
    pretty: PrettyOption = None,
) -> None:
    """평형의 기관별 시세 추이 (한국부동산원·KB부동산·부동산뱅크, 주별 매매·전세 시세와 전세가율, 만원). 요청 1회.

    시세는 기관 추정값이다. 실제 거래는 real-price 로 본다.

    예: jibsa naver market-price 개포자이 --pyeong 1 --period 3년
    """
    period = check_choice(period, PERIOD_MONTHS_BY_NAME, '--period')
    with handle_errors(SOURCE), NaverClient() as client:
        complex_number, villa, notes = _complex_number(client, complex_)
        emit(get_market_price_history(client, complex_number, pyeong, period=period, villa=villa), pretty, notes=notes)


@app.command('redevelopment')
def redevelopment_detail_command(
    area: Annotated[
        str,
        typer.Argument(metavar='REDEVELOPMENT', help='재개발 구역 번호(search redevelopment 결과의 redevelopment_number) 또는 이름 (예: 성수전략정비구역제3지구). 같은 이름이 여러 구역이면 후보의 구역 번호를 준다')
    ],
    trade: Annotated[
        list[str] | None,
        typer.Option('--trade', help='거래 유형: 매매, 전세, 월세, 단기임대. 주면 매물 수·호가 범위를 그 거래만으로 센다. 반복하거나 쉼표로 구분')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """재개발 구역 하나: 계획 세대수·시공사·용적률·건폐율·사업 단계와 거래 유형별 매물 수·호가 범위 (요청 2회).

    매물 목록은 search listings --redevelopment 로 본다. 이름으로 찾으면 구역 검색 요청 1회가 는다.

    예: jibsa naver redevelopment 10017678 --trade 매매
    예: jibsa naver redevelopment 성수전략정비구역제3지구
    """
    trade_types = split_csv(trade, TRADE_TYPES, '--trade')
    with handle_errors(SOURCE), NaverClient() as client:
        area_number, notes = _redevelopment_number(client, area, 'REDEVELOPMENT')
        detail = get_redevelopment(client, area_number, trade_types=trade_types)
        if trade_types:
            notes.append(f"article_counts·호가 범위는 {', '.join(trade_types)} 매물만 센 값입니다")
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
    complexes: Annotated[
        bool,
        typer.Option('--complexes', help='이 학교에 배정되는 단지 목록(assigned_complexes: 단지 정보·매물 수·호가·배정 동)을 붙인다 (20곳마다 요청 1회 추가)')
    ] = False,
    sort: Annotated[
        str | None,
        typer.Option('--sort', help=f"--complexes 전용 정렬: {', '.join(SCHOOL_COMPLEX_SORT_TYPE_BY_NAME)} (기본 {SCHOOL_COMPLEX_DEFAULT_SORT}, 학교에서 가까운 순)")
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option('--limit', min=1, max=MAX_SCHOOL_COMPLEX_LIMIT, help=f'--complexes 전용: 최대 단지 수 (기본 {SCHOOL_COMPLEX_DEFAULT_LIMIT})')
    ] = None,
    pretty: PrettyOption = None,
) -> None:
    """초등학교 상세: 학생 수·학급당/교원당 학생 수와 시·구 평균, 운영 구분, 개교일 (학교알리미 공시, 요청 1회).

    --complex 를 주면 요청이 2~3회 더 든다 (이름으로 주면 단지 검색 1회 포함). --complexes 를 주면 20곳마다 1회씩(최대 5회) 더 든다.
    전화·홈페이지는 주지 않는다. 학교 배정은 교육청 학구도로 확인한다. --complexes 를 주면 이 학교에 배정되는 단지(assigned_complexes)도 본다.

    예: jibsa naver school B100000747 --complex 개포자이
    예: jibsa naver school B100000747 --complexes --sort 세대수순
    """
    school_code = school_code.strip()
    if SCHOOL_CODE_PATTERN.fullmatch(school_code) is None:
        raise typer.BadParameter('학교 코드는 영문·숫자입니다 (예: B100000747)', param_hint='SCHOOL_CODE')
    if not complexes and (sort is not None or limit is not None):
        raise typer.BadParameter('--sort·--limit 은 --complexes 와 함께 사용하세요', param_hint='--complexes')
    sort = check_choice(SCHOOL_COMPLEX_DEFAULT_SORT if sort is None else sort, SCHOOL_COMPLEX_SORT_TYPE_BY_NAME, '--sort')
    with handle_errors(SOURCE), NaverClient() as client:
        notes: list[str] = []
        complex_number, villa = None, None
        if complex_ is not None:
            complex_number, villa, notes = _complex_number(client, complex_)
        school = get_school(client, school_code, complex_number=complex_number, villa=villa)
        if not complexes:
            emit(school, pretty, notes=notes + school.notes)
            return
        assigned = list_school_complexes(
            client, school_code, sort=sort, limit=SCHOOL_COMPLEX_DEFAULT_LIMIT if limit is None else limit,
        )
        emit(
            {**school.model_dump(mode='json'), 'assigned_complexes': assigned.model_dump(mode='json')},
            pretty,
            notes=notes + school.notes + assigned.notes,
        )


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
        detail = get_listing(client, item_id)
        emit(detail, pretty, notes=detail.notes)


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
    property_types = split_csv(property_type, PROPERTY_TYPES, '--type', LISTING_HINTS)
    trade_types, trade_notes = _price_trade_types(trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max)
    room_types = split_csv(room, tuple(ROOM_COUNT_CODE_BY_NAME), '--room', LISTING_HINTS)
    floors = split_csv(floor, tuple(FLOOR_CODE_BY_NAME), '--floor', LISTING_HINTS)
    directions = split_csv(direction, tuple(DIRECTION_FILTER_CODE_BY_NAME), '--direction', LISTING_HINTS)
    bathrooms = split_csv(bathroom, tuple(BATHROOM_CODE_BY_NAME), '--bathroom', LISTING_HINTS)
    facilities = split_csv(facility, tuple(FACILITY_CODE_BY_NAME), '--facility', LISTING_HINTS)
    one_room_shapes = split_csv(one_room_shape, tuple(ONE_ROOM_SHAPE_CODE_BY_NAME), '--one-room-shape', LISTING_HINTS)
    move_in_types = split_csv(move_in, tuple(MOVE_IN_CODE_BY_NAME), '--move-in', LISTING_HINTS)
    parking_types = split_csv(parking, tuple(PARKING_CODE_BY_NAME), '--parking', LISTING_HINTS)
    entrances = split_csv(entrance, tuple(ENTRANCE_CODE_BY_NAME), '--entrance')
    area_basis = check_choice(area_basis, AREA_BASES, '--area-basis')
    if loan is not None:
        loan = check_choice(loan, LOAN_CODE_BY_NAME, '--loan')
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
        typer.Argument(help="주소·동·구·역·단지 이름 (예: '역삼동 719-28', 테헤란로 152, 역삼동, 성동구, 강남역, 개포자이). 동·구·군·구 없는 시·세종 이름이면 그 경계 전체를 찾는다. --lat/--lng 를 주면 생략")
    ] = None,
    complex_: Annotated[str | None, typer.Option('--complex', help='단지 이름 또는 번호. 지역·좌표와 함께 사용할 수 없다')] = None,
    redevelopment: Annotated[
        str | None,
        typer.Option('--redevelopment', help='재개발 구역 번호(search redevelopment 결과의 redevelopment_number) 또는 이름 (예: 성수전략정비구역제3지구). 그 구역 매물을 찾는다. 같은 이름이 여러 구역이면 후보의 구역 번호를 준다. 지역·좌표·--complex 와 함께 사용할 수 없다')
    ] = None,
    pyeong: Annotated[list[str] | None, typer.Option('--pyeong', metavar='<int>', help='--complex 전용: 평형 ID (평수 아님). 반복하거나 쉼표로 구분')] = None,
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
        typer.Option(min=0.1, max=3.0, help=f'검색 반경 (km, 기본 {DEFAULT_RADIUS_KM:g}). 반경 밖 매물은 뺀다. 동·구·군·구 없는 시·세종 이름으로 찾았을 때 주면 경계 전체 대신 그 중심 반경으로 찾는다')
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
        typer.Option('--entrance', help=f"현관 구조: {', '.join(ENTRANCE_CODE_BY_NAME)}. 현관 구조가 등록된 매물만 걸려 등록되지 않은 매물이 빠진다 (단지가 아닌 빌라도 등록돼 있으면 나온다)")
    ] = None,
    building_age_min: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 하한 (년). 5면 5년 이상')] = None,
    building_age_max: Annotated[int | None, typer.Option(min=0, help='사용승인 후 지난 햇수 상한 (년). 5 면 5년 이내 건물')] = None,
    subway_minutes: Annotated[
        int | None,
        typer.Option(min=1, max=25, help='역세권: 지하철역까지 걸어서 이 분 안인 매물만 (분)')
    ] = None,
    owner_verified: Annotated[bool, typer.Option(help='집주인 확인 매물만')] = False,
    sort: Annotated[
        str,
        typer.Option(
            '--sort',
            help=f"정렬: {', '.join(SORT_TYPE_BY_NAME)}. 네이버 정렬 그대로 준다 (네이버에는 거리순이 없어 distance_km 순이 아님)",
        )
    ] = '랭킹순',
    next_: NextOption = None,
    fields: FieldsOption = None,
    pretty: PrettyOption = None,
) -> None:
    """매물을 조회한다. 주소·역·단지는 그 지점 반경 안을, 동·구·군·구 없는 시·세종 이름은 그 경계 전체를 네이버 정렬(기본 랭킹순)로 찾는다.

    결과에 boundary(동·구·군·구 없는 시·세종 이름)가 있으면 그 법정동·시·군·구 경계 안 매물이고 전체 수(total)도 정확하다. radius_km 가 있으면
    그 반경 안이다 (zigbang search 와 같다). 같은 이름의 동·주소가 여러 곳이면 REGION_AMBIGUOUS 로 멈추니 시·구를 붙여 다시 검색한다.
    '○가' 로 나뉜 동의 앞 이름(성수동 → 성수동1가·성수동2가)이나 여러 단지에 맞는 단지 이름도 REGION_AMBIGUOUS 로 후보를 알린다.
    결과의 title 에 단지명이 들어 있다.

    조건은 모두 네이버 서버 필터로 거른다. 목록에는 방 수가 없어 room_type 은 null 이다
    (토지·사무실·상가·건물처럼 방 칸이 없는 유형은 키가 없다) (방 수는 listing 의 room_count). 빌라에는 단지로 등록된 연립·다세대도 들어간다.

    address 는 동까지다 (네이버 목록이 번지를 주지 않음). 번지까지 있는 주소는 listing 에서.

    예: jibsa naver search listings 역삼동 -t 오피스텔 --trade 월세 --deposit-max 3000 --rent-max 150
    예: jibsa naver search listings --redevelopment 성수전략정비구역제3지구 --trade 매매   # 재개발 구역 이름 (같은 이름이 여러 구역이면 후보의 번호)

    결과에 next 가 있으면 같은 지역·조건에 --next <결과의 next 값> 을 붙여 이어 받는다. 이어 받을 때는 지역을 다시 찾지 않아 네이버 요청이 준다.
    단지·재개발 구역 매물(--complex·--redevelopment)은 이어 받지 않는다.
    """
    position = decode_next(next_)
    # 지역·단지·재개발 구역 모드가 같은 정렬 표를 쓴다 (다듬은 값을 넘겨야 서비스의 표 조회가 맞는다). 가까운순 안내는
    # 지역 검색 모드에만 붙인다 (단지·재개발 모드는 --radius 를 받지 않고 distance_km 도 없다)
    sort = check_choice(
        sort, SORT_TYPE_BY_NAME, '--sort', hints=LISTING_HINTS if complex_ is None and redevelopment is None else None,
    )
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
            trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max,
        )
        _search_redevelopment_listings(
            redevelopment, conditions, trade_notes, sort=sort, limit=limit, pretty=pretty, fields=fields,
        )
        return
    if complex_ is not None:
        _reject_options('--complex', {'지역 이름(QUERY)': query, **area_options})
        conditions, trade_notes = _trade_conditions(
            trade, deposit_min, deposit_max, rent_min, rent_max, price_min, price_max,
        )
        _search_complex_listings(
            complex_, conditions, trade_notes, pyeong=split_ints(pyeong, '--pyeong'), dong=dong, sort=sort, limit=limit,
            pretty=pretty,
            fields=fields,
        )
        return
    if pyeong is not None or dong is not None:
        raise typer.BadParameter('--pyeong·--dong은 --complex와 함께 사용하세요', param_hint='--complex')
    _require_location(query, lat, lng)
    require_finite('--radius', radius)
    conditions, trade_notes = _listing_conditions(
        property_type=property_type, trade=trade,
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
        if position is not None:
            # 앞 결과가 찾은 지역·경계·정렬로 바로 이어 받는다. 지역을 찾는 요청과 그 안내는 첫 결과에만 있다
            target = position['target']
            resumed_region = NaverRegion.model_validate(target['region'])
            result = search_area(
                client, resumed_region.lat, resumed_region.lng, conditions=conditions, radius_km=radius or DEFAULT_RADIUS_KM,
                sort=target['sort'], legal_division_code=target['code'],
                limit=limit, start=position,
            )
            emit(
                {'region': target['region'], **target['scope'], **result.model_dump(mode='json')},
                pretty,
                notes=trade_notes + result.notes,
                next_token=encode_next({'target': target, **result.next_position}) if result.next_position else None,
                fields=fields,
                fields_source=result,
            )
            return
        # 동·구·군·구 없는 시·세종 이름이면 그 경계 전체를 찾는다. 반경을 직접 주면 그 뜻대로 중심 반경으로 찾는다.
        # '○가' 로 나뉜 동(성수동)은 위치 해석에서 REGION_AMBIGUOUS 로 멈춰 동 경계는 늘 동 하나다 (네이버 웹도 동 하나씩 연다)
        region, notes, code, scope = _area_location(client, query, lat, lng, radius, listing_search=True)
        result = search_area(
            client,
            region.lat,
            region.lng,
            conditions=conditions,
            radius_km=radius or DEFAULT_RADIUS_KM,
            sort=sort,
            legal_division_code=code,
            limit=limit,
        )
        # 직방처럼 어디를 얼마나 찾았는지(scope) 함께 준다. 서비스는 좌표만 받아
        # 지역을 모르므로(단지 매물 목록과 결과 모델을 같이 쓴다) 지역을 아는 여기서 붙인다.
        # 이어 받기 표에는 찾은 지역·경계(동·시·군·구)·정렬을 담아 다음에 지역을 다시 찾지 않는다
        target = {
            'region': region.model_dump(mode='json'), 'scope': scope, 'sort': sort, 'code': code,
        }
        emit(
            {
                'region': region.model_dump(mode='json'),
                **scope,
                **result.model_dump(mode='json'),
            },
            pretty,
            notes=trade_notes + notes + result.notes,
            next_token=encode_next({'target': target, **result.next_position}) if result.next_position else None,
            fields=fields,
            fields_source=result,
        )
