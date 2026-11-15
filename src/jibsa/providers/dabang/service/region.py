"""위치 찾기: 동·역·대학 이름을 다방 검색 방식(동 코드·역 번호·대학 번호)으로 바꾸고, 동 경계를 받는다."""
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
    UnsupportedRegionError,
)
from jibsa.core.geo import MultiPolygon
from jibsa.core.korean import (
    legal_dong_hint,
    particle,
)
from jibsa.core.listing import (
    CITY_NAMES_NOT_SIDO,
    SIDO_OFFICIAL_NAMES,
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangBboxModel
from jibsa.providers.dabang.api.request.region import (
    DabangGeojsonRegionRequestParameterModel,
    DabangLocColumn,
    DabangLocSearchV5RequestParameterModel,
    DabangRegionCitiesV5RequestParameterModel,
    DabangRegionStatesV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import DabangLocationModel
from jibsa.providers.dabang.api.response.region import (
    DabangLocRegionModel,
    DabangLocSearchResultModel,
    DabangRegionModel,
)
from jibsa.providers.dabang.service.common import (
    DabangPlace,
    bbox_of,
)

from typing import (
    Annotated,
    Literal,
)


# 같은 이름 후보를 에러에 몇 곳까지 보일지
AMBIGUOUS_CANDIDATES: int = 5
# 시·군·구 이름 ('강남구', '성남시', '양평군'). 다방 장소 검색은 시·군·구를 주지 않고 그 안의 동을 준다 (2026-10-25 실측).
# 낱말 하나를 볼 때는 '입구' 로 끝나는 역 이름을 거르는 `is_district_word` 를 쓴다
DISTRICT_PATTERN: re.Pattern[str] = re.compile(r'^[가-힣]+[구군시]$')
# 동·읍·면·리 이름 ('역삼동', '역삼1동', '봉담읍', '남면', '종로1가'). 동 범위를 받지 않는 곳에서 장소 검색 없이 동을 알아본다
DONG_NAME_PATTERN: re.Pattern[str] = re.compile(r'^[가-힣0-9]+(?:[동읍면리]|\d가)$')
REGION_HINT: str = (
    "동 이름(예: '역삼동', 같은 이름이 여럿이면 '강남구 신사동'), 역 이름(예: '강남역'), 대학 이름(예: '홍익대학교')으로 "
    '찾거나 --lat/--lng 로 좌표를 주세요'
)
SCOPE_HINT: str = "'전국', 시·도 이름(예: '서울'), 시·군·구 이름(예: '강남구', '성남시 분당구') 중 하나를 주세요"
# 동도 범위로 받는 곳(단지 순위)의 안내
DONG_SCOPE_HINT: str = (
    "'전국', 시·도 이름(예: '서울'), 시·군·구 이름(예: '강남구', '성남시 분당구'), 동 이름(예: '역삼동', '강남구 신사동') 중 "
    '하나를 주세요'
)


def search_locations(
    client: DabangClient, query: str, columns: list[DabangLocColumn] | None = None,
) -> DabangLocSearchResultModel:
    """다방 장소 검색 (동·역·대학·단지, `columns` 를 주면 그 종류만. 요청 1회).

    다방은 괄호가 든 검색어에 0건을 준다 ('연세대학교(원주캠퍼스)' 0건, '연세대학교 원주캠퍼스' 는 그 캠퍼스가 첫 후보,
    2026-10-25 실측). 결과에 나온 이름을 그대로 다시 넣어도 찾도록 괄호를 띄어 보낸다.
    """
    parameter = DabangLocSearchV5RequestParameterModel(search_keyword=_without_parens(query))
    if columns:
        parameter = parameter.model_copy(update={'column_list': columns})
    response = client.run_request_loc_search_v5(parameter)
    return response.result or DabangLocSearchResultModel()


def _without_parens(text: str) -> str:
    """괄호를 띄어 쓴 꼴 ('연세대학교(원주캠퍼스)' → '연세대학교 원주캠퍼스'). 다방은 괄호가 든 검색어에 0건을 준다."""
    return ' '.join(re.sub(r'[()]', ' ', text).split())


def legal_division_code(code: str) -> str:
    """다방 동 코드(법정동코드 앞 8자리)를 10자리 법정동코드로 ('11680101' → '1168010100')."""
    return code + '00' if len(code) == 8 else code


def _lat_lng(location: DabangLocationModel | None, name: str) -> tuple[float, float]:
    """후보 좌표. 없으면 (0, 0) 으로 채우지 않고 에러로 알린다 (거리·반경 사각형이 엉뚱해진다).

    장소 검색은 동·역·대학·단지마다 좌표를 준다 (2026-10-25 실측: 검색 17번, 1,383곳 모두). 응답 모델만 없을 때를 받는다.
    """
    if location is None:
        raise JibsaError(
            code='UPSTREAM_ERROR', message=f"다방이 '{name}' 의 좌표를 주지 않았습니다", hint='비공식 API 라 스펙이 바뀌었을 수 있습니다',
        )
    return location.lat, location.lng


def place_of_region(region: DabangLocRegionModel) -> DabangPlace:
    lat, lng = _lat_lng(region.location, region.name)
    # 세종은 다방 전체 이름에 시를 한 번 더 넣는다 ('세종특별자치시 세종 다솜동', 2026-10-25 실측). 정규화하지 않으면 출력이
    # 다른 소스와 다르고, 분양을 주소 앞부분으로 거를 때 정규화한 분양 주소('세종특별자치시 다솜동 …')와 맞지 않아 모두 빠진다
    return DabangPlace(
        kind='dong',
        name=region.name,
        address=normalize_address(region.full_name),
        lat=lat,
        lng=lng,
        legal_division_code=legal_division_code(region.code),
        code=region.code,
        gid=region.gid,
    )


def _matches_context(full_name: str | None, words: list[str], *, widen_city: bool = False) -> bool:
    """'강남구 신사동' 의 앞 낱말(시·도·구·시)이 후보의 전체 이름에 모두 들었는지. 시·도는 줄여 써도 된다 ('서울 신사동').

    시·도 넓히기는 `state_name` 으로 한다. '광주시' 를 시·도 표대로 전남광주통합특별시로 넓히면 '광주시 송정동' 이 경기도
    광주시 송정동과 광산구 송정동 둘에 맞아 REGION_AMBIGUOUS 로 끝났다 (2026-10-28 실측). `widen_city` 면 '광주시' 도
    시·도 표대로 넓힌다 (`_in_context`).
    """
    parts = (full_name or '').split()
    return all(
        word in parts or (SIDO_OFFICIAL_NAMES.get(word) if widen_city else state_name(word)) in parts for word in words
    )


def _in_context(regions: list[DabangLocRegionModel], words: list[str]) -> list[DabangLocRegionModel]:
    """앞 낱말(`words`)에 맞는 동. '광주시' 는 경기도 광주시로 먼저 맞춰 보고, 맞는 동이 없을 때만 옛 광주광역시로 본다.

    네이버 `regions` 와 같은 규칙이다 (한 단어 '광주시' 만 경기도 광주시, 경기도 광주시에 없는 구를 붙이면 전남광주통합특별시).
    경기도 광주시로만 맞추면 '광주시 광산구 송정동' 이 REGION_NOT_FOUND, search sales '광주시 광산구' 가 REGION_NOT_SUPPORTED
    로 끝났다 (2026-10-30 실측: 넓히면 광산구 송정동, 광산구 분양 8곳)
    """
    return (
        [region for region in regions if _matches_context(region.full_name, words)]
        or [region for region in regions if _matches_context(region.full_name, words, widen_city=True)]
    )


def _words(query: str, hint: str) -> list[str]:
    """검색어의 낱말. 비었으면 INVALID_ARGUMENT (빈 글자는 장소 검색 전에 막는다)."""
    words = query.split()
    if not words:
        raise JibsaError(code='INVALID_ARGUMENT', message='검색어가 비었습니다', hint=hint)
    return words


def resolve_places(
    client: DabangClient,
    query: str,
    *,
    searched: DabangLocSearchResultModel | None = None,
    only: Literal['dong', 'station'] | None = None,
) -> DabangPlace:
    """이름을 다방에서 찾을 위치 하나로 바꾼다 (동·역·대학).

    고르는 순서: 이름이 똑같은 동 → 역 → 대학 → '○동N가' 로 나뉜 동. '역' 으로 끝나면 역을 먼저 본다. 후보가 여럿이면
    고르지 않고 REGION_AMBIGUOUS 로 알린다. 다방 웹 검색창도 후보(성수동1가·성수동2가, 연세대학교·연세대학교(원주캠퍼스))를
    모두 보여 주고 사용자가 하나를 누르면 그 하나의 목록을 연다 (2026-11-13 웹 대조).

    Args:
        searched: 같은 이름으로 이미 받은 장소 검색 결과. 주면 다시 묻지 않는다.
        only: 그 종류만 받는 명령이 준다 (동네정보·인기 매물은 'dong', 역 둘레 평균 매물가는 'station'). 다른 종류의 후보가
            여럿이면 고르라고 알리지 않고 첫 후보를 돌려준다. 후보 하나를 골라 다시 줘도 그 명령이 받지 못하기 때문이다
            (2026-11-13 리뷰: `neighborhood 연세대` 가 대학을 고르라고 한 뒤 '동 이름만 받는다' 로 막았다). 부른 쪽이 종류를
            보고 INVALID_ARGUMENT 로 막으므로 이 첫 후보로 조회하는 일은 없다. Defaults to None (모든 종류를 받는다).

    Raises:
        RegionAmbiguousError: 이름이 같은 동이 여러 시·구에 있을 때, '○가' 로 나뉜 동·같은 이름의 역·앞부분이 맞는 대학이
            여럿일 때.
        UnsupportedRegionError: 시·군·구 이름일 때 (다방은 시·군·구 전체를 찾지 못한다).
        RegionNotFoundError: 찾지 못했을 때.
    """
    text = query.strip()
    words = _words(text, REGION_HINT)
    last, context = words[-1], words[:-1]
    result = searched if searched is not None else search_locations(client, text)
    regions = _in_context(result.region_list, context)
    exact = [region for region in regions if region.name == last]
    stations = [station for station in result.subway_list if station.name in (last, f'{last}역')]
    # 이름이 똑같은 대학을 먼저 본다. '연세대' 는 연세대학교·연세대학교(원주캠퍼스)·연세대학교(국제캠퍼스)에 맞는다 (2026-10-25 실측).
    # 띄어 쓴 캠퍼스 이름('연세대학교 원주캠퍼스')은 낱말 하나로는 맞지 않아 검색어 전체를 괄호 뺀 대학 이름과 견준다
    # (2026-10-28 실측: 마지막 낱말 '원주캠퍼스' 로만 견줘 REGION_NOT_FOUND 였다)
    spaced = _without_parens(text)
    universities = (
        [univ for univ in result.univ_list if univ.name == last or _without_parens(univ.name) == spaced]
        or [univ for univ in result.univ_list if univ.name.startswith(last)]
    )

    def station_place() -> DabangPlace:
        if len(stations) > 1 and only != 'dong':
            # 다방은 같은 이름의 역을 '양평역'·'양평역(중앙선)' 처럼 이름으로 가르지만(2026-11-13 실측), 이름이 똑같은 역이
            # 여럿 오면 첫 역을 고르지 않는다. 이름으로는 다시 가를 수 없어 노선을 붙여 보이고 좌표로 찾게 한다. 역만 받는
            # 명령(역 둘레 평균 매물가)은 좌표를 받지 않아 가를 길이 없다고 알린다
            candidates = [
                f"{station.name} ({', '.join(line.full_name for line in station.line_list if line.full_name) or '노선 모름'})"
                for station in stations
            ]
            located = f'jibsa dabang search locations {stations[0].name} 결과에서 역마다 좌표를 볼 수 있습니다'
            raise RegionAmbiguousError(
                text, candidates[:AMBIGUOUS_CANDIDATES], len(candidates),
                hint=(
                    f'이 명령은 역을 이름으로만 받아 이름이 같은 역을 가려 받지 못합니다. {located}'
                    if only == 'station' else f'{located}. 그 좌표를 --lat/--lng (와 --radius) 로 주세요'
                ),
            )
        station = stations[0]
        lat, lng = _lat_lng(station.location, station.name)
        return unpicked(DabangPlace(
            kind='station',
            name=station.name,
            lat=lat,
            lng=lng,
            place_id=station.id,
            radius_m=station.radius,
        ), len(stations))

    def unpicked(place: DabangPlace, count: int) -> DabangPlace:
        """`only` 와 다른 종류의 후보가 여럿일 때 돌려주는 첫 후보에는 사용자가 준 이름을 붙인다. 부른 쪽 에러 문구에 고르지도
        않은 첫 후보 이름('역 이름이 아닙니다: 성수동1가')이 아니라 준 이름('성수동')이 찍히게 한다."""
        # 리뷰 오탐 (2026-11-14): 이름을 바꾼 place 가 조회·출력에 쓰이는 일은 없다. only 를 주는 네 곳(neighborhood·
        # popular-listings·_dong_scope·station-prices)이 모두 돌려받은 종류를 바로 INVALID_ARGUMENT 로 거절한다. 종류 에러를 여기서
        # 내면 부른 쪽마다 다른 문구·hint(동네정보는 역 둘레 안내, 범위는 범위 hint)를 잃는다. 종류 검사(동이면서 gid 있음)가
        # single_dong 과 _dong_scope 에 한 줄씩 있는 것도 같은 이유로 둔다: 거절 문구·hint 가 호출마다 달라 합치려면 문구를 인자로
        # 받는 함수가 되고 조건 한 줄만 아낀다
        return place.model_copy(update={'name': text}) if count > 1 else place

    if last.endswith('역') and stations:
        return station_place()
    if len(exact) == 1 or (exact and only == 'station'):
        return unpicked(place_of_region(exact[0]), len(exact))
    if len(exact) > 1:
        candidates = [normalize_address(region.full_name) or region.name for region in exact]
        raise RegionAmbiguousError(text, candidates[:AMBIGUOUS_CANDIDATES], len(candidates))
    if stations:
        return station_place()
    if len(universities) > 1 and only is None:
        # 줄인 이름('연세대')이 여러 캠퍼스에 맞으면 첫 곳을 고르지 않는다. 후보 이름을 그대로 주면 이름이 똑같은 대학으로 찾는다.
        # 다방은 캠퍼스를 '연세대학교(원주캠퍼스)' 처럼 이름으로 가른다 (2026-11-14 대학 28개 이름 검색에 이름이 똑같은 대학 없음).
        # 그래도 이름이 똑같은 대학이 여럿 오면 이름으로는 다시 가를 수 없어, 같은 이름 역처럼 좌표로 찾게 한다
        names = [univ.name for univ in universities]
        if len(set(names)) == 1:
            hint = (
                f'이름이 같은 대학이 {len(names)}곳이라 이름으로는 가를 수 없습니다. jibsa dabang search locations {names[0]} '
                '결과에서 대학마다 좌표를 볼 수 있습니다. 그 좌표를 --lat/--lng (와 --radius) 로 주세요'
            )
        else:
            hint = f"대학 이름을 후보 그대로 따옴표로 감싸 다시 주세요 (예: '{names[0]}')"
        raise RegionAmbiguousError(text, names[:AMBIGUOUS_CANDIDATES], len(names), hint=hint)
    if universities:
        univ = universities[0]
        lat, lng = _lat_lng(univ.location, univ.name)
        return unpicked(DabangPlace(
            kind='university',
            name=univ.name,
            lat=lat,
            lng=lng,
            place_id=univ.id,
        ), len(universities))
    split = sorted(
        (region for region in regions if re.fullmatch(re.escape(last) + r'\d+가', region.name)), key=lambda region: region.name,
    )
    if split and only == 'station':
        return unpicked(place_of_region(split[0]), len(split))
    if split:
        cities = {normalize_address(region.full_name or '').rsplit(' ', 1)[0] for region in split}
        if len(cities) > 1:
            raise RegionAmbiguousError(text, sorted(cities)[:AMBIGUOUS_CANDIDATES], len(cities))
        if len(split) > 1:
            # '○가' 로 나뉜 동(성수동1가·2가)은 합쳐 찾지 않고 하나를 고르게 한다. 다방 웹도 따로 보여 주고 고른 동 하나의 목록만
            # 연다. 같은 동의 '○가' 는 몇 곳뿐이라(영등포동은 1가~8가) 자르지 않고 모두 보인다
            candidates = [normalize_address(region.full_name) or region.name for region in split]
            raise RegionAmbiguousError(
                text, candidates, len(candidates), hint=f"동 하나를 골라 그 이름으로 다시 주세요 (예: '{split[0].name}')",
            )
        return place_of_region(split[0])
    if is_district_word(last) and result.region_list:
        raise UnsupportedRegionError(
            code='REGION_NOT_SUPPORTED',
            message=f"다방은 시·군·구 전체를 찾지 못합니다: '{text}'",
            hint=f"그 안의 동 이름(예: '{' '.join((result.region_list[0].full_name or result.region_list[0].name).split()[-2:])}')이나 역 이름으로 찾거나, "
            '--lat/--lng 와 --radius 로 반경을 주세요',
            skip_note=f"다방은 시·군·구 전체를 찾지 못해 {text}{particle(text, '을/를')} 건너뛰었습니다",
        )
    raise RegionNotFoundError(text, hint=legal_dong_hint(text) or REGION_HINT)


def dong_boundary(client: DabangClient, code: str) -> MultiPolygon:
    """동 경계 (법정동코드 앞 8자리). 지도 집계가 동마다 주는 CDN 파일을 받는다 (요청 1회).

    장소 검색이 주는 동은 모두 경계 파일이 있다 (2026-10-25 실측: 읍·면·세종·전남광주·신도시 동 27곳 모두, 빈 좌표 없음).
    그래서 없을 때를 대신하지 않고, 403 은 UPSTREAM_ERROR 로 두어 스펙 변경으로 알린다.
    """
    return client.run_request_geojson_region(DabangGeojsonRegionRequestParameterModel(code=code)).coordinates


def _covering_bbox(boundary: MultiPolygon) -> DabangBboxModel:
    """경계를 덮는 지도 범위."""
    points = [point for polygon in boundary for ring in polygon for point in ring]
    lats = [point[1] for point in points]
    lngs = [point[0] for point in points]
    return bbox_of(min(lats), max(lats), min(lngs), max(lngs))


def dong_bbox(client: DabangClient, place: DabangPlace) -> DabangBboxModel:
    """동 경계를 덮는 지도 범위 (경계 요청 1회). 동 검색이 없는 아파트 목록과 지도 범위만 받는 단지·분양 목록에 쓴다."""
    # 동 코드는 장소 검색 응답 값이다. 늘 8자리라 요청 모델의 꼴(8자리)을 벗어나지 않아 따로 막지 않는다 (core/schema.py,
    # 2026-10-26 실측: 중구·신사동·효자동·성수동 장소 검색의 동 61곳 모두 8자리)
    return _covering_bbox(dong_boundary(client, place.code or ''))


NATIONAL_NAMES: frozenset[str] = frozenset({'전국', '전체', '대한민국'})


def state_name(text: str) -> str | None:
    """시·도 줄임말·정식 이름이면 정식 이름 ('충북'·'충청북도' → '충청북도'), 아니면 None. '광주시' 는 경기도 광주시라 None.

    '광주시'(`CITY_NAMES_NOT_SIDO`)를 시·도로 보면 2026-10-26 실측에서 region-ranking 광주시 가 안내 없이
    전남광주통합특별시 순위를 주고, search sales 광주시 는 시·도 범위라며 막혔다.
    """
    if text in CITY_NAMES_NOT_SIDO:
        return None
    return SIDO_OFFICIAL_NAMES.get(text) or (text if text in SIDO_OFFICIAL_NAMES.values() else None)


class DabangScope(BaseModel):
    """순위·분양 범위: 전국, 시·도, 시·군·구, 동 (동은 단지 순위만)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    kind: Annotated[
        Literal['national', 'state', 'district', 'dong'],
        Field(description='범위 종류 (전국·시도·시군구·동)')
    ]
    name: Annotated[
        str,
        Field(description="범위 이름 ('전국', '서울특별시', '서울특별시 강남구', '서울특별시 강남구 역삼동')")
    ]
    code: Annotated[
        str | None,
        Field(description='법정동 코드 (시·도 앞 2자리, 시·군·구 앞 5자리, 동 10자리)')
    ] = None
    state_code: Annotated[
        str | None,
        Field(exclude=True, description='시·도 코드 (2자리, 시·도·시·군·구. 시·군·구 목록을 받은 시·도)')
    ] = None
    gid: Annotated[
        int | None,
        Field(exclude=True, description='다방 지역 번호 (전국은 없음)')
    ] = None


def _states(client: DabangClient) -> list[DabangRegionModel]:
    """시·도 목록 (요청 1회)."""
    return client.run_request_region_states_v5(DabangRegionStatesV5RequestParameterModel()).result or []


def _state_of(states: list[DabangRegionModel], official: str, text: str) -> DabangRegionModel | None:
    """시·도 목록에서 정식 이름(`official`, `state_name(text)`)이나 사용자가 준 줄임말(`text`, '서울')에 맞는 시·도.

    부르는 쪽이 `state_name` 으로 시·도 이름인지 먼저 보고('광주시' 는 경기도 광주시라 시·도가 아니다) 시·도 목록을 받는다.
    """
    return next((state for state in states if state.name == official or state.short_name == text), None)


def _cities(client: DabangClient, state_code: str) -> list[DabangRegionModel]:
    """시·도 하나의 시·군·구 목록 (요청 1회). 웹 랭킹·분양 지역 고르기와 같은 목록이다."""
    return client.run_request_region_cities_v5(DabangRegionCitiesV5RequestParameterModel(state_code=state_code)).result or []


def _district_scope(state_name_: str, state_code: str, city: DabangRegionModel) -> DabangScope:
    return DabangScope(
        kind='district', name=normalize_address(f'{state_name_} {city.name}') or city.name, code=city.code, state_code=state_code,
        gid=city.gid,
    )


def _city_with_gu_error(text: str, example: str) -> UnsupportedRegionError:
    """구가 있는 시 전체('성남시')를 범위로 받지 않는다는 에러. `example` 은 구를 붙인 이름 ('성남시 분당구')."""
    return UnsupportedRegionError(
        code='REGION_NOT_SUPPORTED',
        message=f"다방은 구가 있는 시 전체를 범위로 받지 않습니다: '{text}'",
        hint=f"구 이름을 붙여 주세요 (예: '{example}')",
        skip_note=f'{text} 는 구가 있는 시라 건너뛰었습니다',
    )


def _pick_city(cities: list[DabangRegionModel], words: list[str], text: str) -> DabangRegionModel | None:
    """시·군·구 목록에서 이름('강남구', '성남시 분당구', '분당구')에 맞는 곳. 없으면 None.

    다방 시·군·구 목록은 구가 있는 시를 구마다 '성남시 분당구' 로 두고 시 하나('성남시')는 두지 않는다 (2026-11-13 캡처: 경기도
    47곳). 시 이름만 주면 그 시의 구를 붙이게 한다. 웹 지역 고르기도 시 전체를 고르지 못한다.

    Raises:
        RegionAmbiguousError: 마지막 낱말만 맞는 시·군·구가 그 시·도에 여럿일 때.
        UnsupportedRegionError: 구가 있는 시일 때 ('성남시').
    """
    name = ' '.join(words)
    exact = [city for city in cities if city.name == name]
    if exact:
        return exact[0]
    # '분당구' 처럼 시를 빼고 준 구. 앞 낱말이 있으면 그 낱말도 이름에 들어야 한다
    tail = [
        city for city in cities
        if city.name.split()[-1] == words[-1] and all(word in city.name.split() for word in words[:-1])
    ]
    if len(tail) > 1:
        names = [city.name for city in tail]
        raise RegionAmbiguousError(text, names[:AMBIGUOUS_CANDIDATES], len(names), hint=f"시를 붙여 다시 주세요 (예: '{names[0]}')")
    if tail:
        return tail[0]
    under = [city.name for city in cities if city.name.startswith(f'{name} ')]
    if under:
        # 구가 있는 시(경기도 성남시 수정구 …)는 다방 지역이 아니다. 웹 지역 고르기에도 시 전체가 없다
        raise _city_with_gu_error(text, under[0])
    return None


def is_national_or_state(text: str) -> bool:
    """'전국'·시·도 이름인지 ('서울시' 도 '시' 로 끝나지만 시·도다). 범위로 찾을 때 장소 검색을 쓰지 않는다."""
    return text in NATIONAL_NAMES or state_name(text) is not None


def _prefixed_state(words: list[str]) -> str | None:
    """시·도를 붙인 이름('서울 중구', '경기 성남시 분당구')이면 그 시·도의 정식 이름, 아니면 None. 범위로 찾을 때 장소 검색을
    쓰지 않는다."""
    return state_name(words[0]) if len(words) > 1 else None


def is_district_word(word: str) -> bool:
    """시·군·구 이름 모양의 낱말인지 ('강남구', '성남시', '양평군').

    '입구' 로 끝나면 시·군·구로 보지 않는다. '홍대입구'·'을지로입구'·'서울대입구' 같은 역 이름도 '구' 로 끝나지만 '입구' 로 끝나는
    시·군·구는 없다. 시·군·구로 보면 '서울 홍대입구' 가 시·도 목록·시·군·구 목록을 받고서야 못 찾는다 (요청 2회를 버린다).
    """
    return bool(DISTRICT_PATTERN.fullmatch(word)) and not word.endswith('입구')


def is_scope_name(query: str) -> bool:
    """전국·시·도·시·군·구 이름처럼 보이는지 ('전국', '서울', '경기도', '강남구', '성남시 분당구'). 마지막 낱말로 본다."""
    text = query.strip()
    words = text.split()
    return is_national_or_state(text) or bool(words and is_district_word(words[-1]))


def find_scope(client: DabangClient, query: str) -> tuple[DabangScope | None, DabangLocSearchResultModel | None]:
    """범위(전국·시·도·시·군·구) 이름이면 그 범위, 동·역·대학 이름이면 None (분양 지역 목록으로 찾을지 고른다).

    이름 모양(○구·○군·○시)만으로는 시·군·구인지 알 수 없다. 범위로 찾지 못한 이름은 None 으로 돌려 동·역으로 다시 찾게 한다
    (2026-10-25 실측: '홍대입구' 가 REGION_NOT_FOUND 로 끝났다. '입구' 로 끝나는 역 이름은 이제 `is_scope_name` 이 먼저 거른다).

    Returns:
        (범위, 장소 검색 결과). 시·도 없는 시·군·구 모양 이름은 여기서 장소 검색을 한 번 받아 `resolve_scope` 에 주고, 범위로
        찾지 못하면 그 결과를 돌려 `resolve_places` 가 같은 요청을 또 보내지 않게 한다. 전국·시·도와 시·도를 붙인 시·군·구
        ('서울 중구')는 장소 검색 없이 시·도·시·군·구 목록으로 찾아 장소 검색 결과는 None 이다.

    Raises:
        RegionAmbiguousError: 시·군·구 이름이 여러 시·도에 있을 때 ('중구').
        UnsupportedRegionError: 구가 있는 시일 때 ('성남시').
    """
    if not is_scope_name(query):
        return None, None
    text = query.strip()
    # 전국은 요청 없이, 시·도는 시·도 목록 1회. 찾지 못한 시·도 이름은 동·역으로 넘기지 않고 에러로 둔다
    if is_national_or_state(text):
        return resolve_scope(client, text), None
    searched = None if _prefixed_state(text.split()) is not None else search_locations(client, text)
    try:
        return resolve_scope(client, text, searched=searched), searched
    except RegionNotFoundError:
        return None, searched


def resolve_scope(
    client: DabangClient, query: str, *, searched: DabangLocSearchResultModel | None = None, dong: bool = False,
) -> DabangScope:
    """'전국'·시·도·시·군·구 이름을 범위로 바꾼다. 웹 랭킹·분양 지역 고르기처럼 시·도 목록(`region/states`)과 시·군·구 목록
    (`region/cities?stateCode=`)에서 이름으로 찾는다 (useSiGuDong 청크 2026-11-13).

    시·도는 시·도 목록 1회다. 시·군·구는 시·도를 붙인 이름('서울 중구')이면 시·도 목록과 그 시·도의 시·군·구 목록(요청 2회),
    시·도 없는 이름('강남구', '성남시 분당구')이면 장소 검색으로 그 이름의 시·군·구가 든 시·도를 찾고 그 시·도의 시·군·구 목록을
    받는다 (요청 2회). 시·군·구 목록은 시·도마다 따로라, 시·도 없는 이름을 목록만으로 찾으려면 시·도 17곳을 모두 받아야 한다.
    장소 검색은 동을 50곳까지만 줘 이름이 같은 시·군·구가 여러 시·도에 있을 때 후보에 빠진 시·도가 있을 수 있다.

    Args:
        searched: 같은 이름으로 이미 받은 장소 검색 결과. 주면 다시 묻지 않는다.
        dong: 동 이름도 범위로 받을지 (단지 순위). 동은 위치 찾기(`resolve_places`)로 찾아 장소 검색의 동 번호를 범위로 쓴다
            (요청 1회, 웹 단지 순위가 고른 동의 `gid` 를 보낸다). 시·군·구 모양(○구·○군·○시)의 이름은 동으로 보지 않는다.
            Defaults to False (분양 범위는 전국·시·도·시·군·구).

    Raises:
        RegionAmbiguousError: 시·군·구 이름이 여러 시·도에 있을 때 ('중구'), 동 이름이 여러 곳일 때.
        UnsupportedRegionError: 구가 있는 시일 때 ('성남시').
        RegionNotFoundError: 범위로 알아볼 수 없는 이름일 때.
        JibsaError: `dong` 인데 동이 아니라 역·대학 이름일 때 (INVALID_ARGUMENT).
    """
    text = query.strip()
    if text in NATIONAL_NAMES:
        return DabangScope(kind='national', name='전국')
    hint = DONG_SCOPE_HINT if dong else SCOPE_HINT
    official = state_name(text)
    if official is not None:
        state = _state_of(_states(client), official, text)
        if state is not None:
            return DabangScope(kind='state', name=state.name, code=state.code, state_code=state.code, gid=state.gid)
    words = _words(text, hint)
    last = words[-1]
    if dong and not is_district_word(last):
        return _dong_scope(client, text, searched)
    if not is_district_word(last):
        raise RegionNotFoundError(text, hint=hint)
    official = _prefixed_state(words)
    if official is not None:
        # 시·도를 붙인 이름('서울 중구', '경기 성남시 분당구')은 장소 검색 없이 그 시·도의 시·군·구 목록에서 찾는다. 장소 검색으로
        # 먼저 찾지 않는 까닭: 장소 검색은 이름이 같은 동을 50곳까지만 줘 붙인 시·도의 동이 빠질 수 있다 (2026-11-14 실측: '인천
        # 중구' 장소 검색의 동 50곳 중 인천 중구는 0곳, 대전 중구 12곳). 시·도의 시·군·구 목록은 그 시·도를 모두 준다
        state = _state_of(_states(client), official, words[0])
        if state is None:
            raise RegionNotFoundError(text, hint=hint)
        city = _pick_city(_cities(client, state.code), words[1:], text)
        if city is None:
            raise RegionNotFoundError(text, hint=hint)
        return _district_scope(state.name, state.code, city)
    # 시·도 없는 이름은 장소 검색이 주는 그 시·군·구의 동으로 시·도를 찾는다. 시·군·구 이름마다 처음 나온 동 하나 ('중구' 는
    # 서울·부산·대구·대전·울산, 2026-10-25 실측)
    districts: dict[str, tuple[DabangLocRegionModel, list[str], int]] = {}
    named = [
        region for region in (searched if searched is not None else search_locations(client, text)).region_list
        if last in (region.full_name or '').split()[1:3]
    ]
    for region in _in_context(named, words[:-1]):
        parts = (region.full_name or '').split()
        index = parts.index(last)
        districts.setdefault(' '.join(parts[:index + 1]), (region, parts, index))
    if len(districts) > 1:
        names = sorted(normalize_address(name) for name in districts)
        raise RegionAmbiguousError(text, names[:AMBIGUOUS_CANDIDATES], len(names), hint=f"시·도를 붙여 다시 주세요 (예: '{names[0]}')")
    for region, parts, index in districts.values():
        if index == 1 and len(parts) > 3 and parts[2].endswith('구'):
            # 구가 있는 시('경기도 성남시 수정구 …' 의 '성남시')는 시·군·구 목록에 시 하나로 없다. 목록을 받지 않고 막는다
            raise _city_with_gu_error(text, f'{last} {parts[2]}')
        # 동 코드(늘 8자리, `dong_bbox` 참고)의 앞 2자리가 시·도 코드다. 시·군·구 이름은 시·도 뒤부터 그 시·군·구까지의 낱말이다
        # ('경기도 성남시 분당구 …' → '성남시 분당구')
        state_code = region.code[:2]
        city = _pick_city(_cities(client, state_code), parts[1:index + 1], text)
        if city is not None:
            return _district_scope(parts[0], state_code, city)
    raise RegionNotFoundError(text, hint=hint)


def _dong_scope(client: DabangClient, text: str, searched: DabangLocSearchResultModel | None) -> DabangScope:
    """동 이름을 범위로 (위치 찾기 1회). 같은 이름의 동이 여럿이면 `resolve_places` 가 REGION_AMBIGUOUS 로 후보를 준다."""
    try:
        place = resolve_places(client, text, searched=searched, only='dong')
    except RegionNotFoundError:
        # 위치 찾기의 안내는 역·좌표 검색을 권해 범위 이름에 맞지 않는다
        raise RegionNotFoundError(text, hint=legal_dong_hint(text) or DONG_SCOPE_HINT) from None
    if place.kind != 'dong' or place.gid is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'범위로 받지 않는 이름입니다 (동 이름이 아닙니다): {place.name}',
            hint=DONG_SCOPE_HINT,
        )
    return DabangScope(kind='dong', name=place.address or place.name, code=place.legal_division_code, gid=place.gid)
