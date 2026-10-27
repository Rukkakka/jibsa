"""위치 찾기: 동·역·대학 이름을 다방 검색 방식(동 코드·역 번호·대학 번호)으로 바꾸고, 동 경계를 받는다."""
import re

from httpx import HTTPStatusError
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
    quoted,
)
from jibsa.core.listing import (
    SIDO_OFFICIAL_NAMES,
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangBboxModel
from jibsa.providers.dabang.api.request.region import (
    DabangGeojsonRegionRequestParameterModel,
    DabangLocColumn,
    DabangLocSearchV5RequestParameterModel,
    DabangRegionStatesV5RequestParameterModel,
    DabangRegionV5RequestParameterModel,
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
    is_missing_id,
)

from typing import (
    Annotated,
    Literal,
)


# 같은 이름 후보를 에러에 몇 곳까지 보일지
AMBIGUOUS_CANDIDATES: int = 5
# 시·군·구 이름 ('강남구', '성남시', '양평군'). 다방 장소 검색은 시·군·구를 주지 않고 그 안의 동을 준다 (2026-10-25 실측)
DISTRICT_PATTERN: re.Pattern[str] = re.compile(r'^[가-힣]+[구군시]$')
REGION_HINT: str = (
    "동 이름(예: '역삼동', 같은 이름이 여럿이면 '강남구 신사동'), 역 이름(예: '강남역'), 대학 이름(예: '홍익대학교')으로 "
    '찾거나 --lat/--lng 로 좌표를 주세요'
)
SCOPE_HINT: str = "'전국', 시·도 이름(예: '서울'), 시·군·구 이름(예: '강남구', '성남시 분당구') 중 하나를 주세요"


def search_locations(
    client: DabangClient, query: str, columns: list[DabangLocColumn] | None = None,
) -> DabangLocSearchResultModel:
    """다방 장소 검색 (동·역·대학·단지, `columns` 를 주면 그 종류만. 요청 1회).

    다방은 괄호가 든 검색어에 0건을 준다 ('연세대학교(원주캠퍼스)' 0건, '연세대학교 원주캠퍼스' 는 그 캠퍼스가 첫 후보,
    2026-10-25 실측). 결과에 나온 이름을 그대로 다시 넣어도 찾도록 괄호를 띄어 보낸다.
    """
    parameter = DabangLocSearchV5RequestParameterModel(search_keyword=' '.join(re.sub(r'[()]', ' ', query).split()))
    if columns:
        parameter = parameter.model_copy(update={'column_list': columns})
    response = client.run_request_loc_search_v5(parameter)
    return response.result or DabangLocSearchResultModel()


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


def _matches_context(full_name: str | None, words: list[str]) -> bool:
    """'강남구 신사동' 의 앞 낱말(시·도·구·시)이 후보의 전체 이름에 모두 들었는지. 시·도는 줄여 써도 된다 ('서울 신사동')."""
    parts = (full_name or '').split()
    return all(word in parts or SIDO_OFFICIAL_NAMES.get(word) in parts for word in words)


def _words(query: str, hint: str) -> list[str]:
    """검색어의 낱말. 비었으면 INVALID_ARGUMENT (빈 글자는 장소 검색 전에 막는다)."""
    words = query.split()
    if not words:
        raise JibsaError(code='INVALID_ARGUMENT', message='검색어가 비었습니다', hint=hint)
    return words


def resolve_places(
    client: DabangClient, query: str, *, searched: DabangLocSearchResultModel | None = None,
) -> tuple[list[DabangPlace], list[str]]:
    """이름을 다방에서 찾을 위치로 바꾼다. 동은 그 동(이름이 같은 '○가' 동이 여럿이면 모두), 역·대학은 하나.

    고르는 순서: 이름이 똑같은 동 → 역 → 대학 → '○동N가' 로 나뉜 동. '역' 으로 끝나면 역을 먼저 본다.

    Args:
        searched: 같은 이름으로 이미 받은 장소 검색 결과. 주면 다시 묻지 않는다.

    Returns:
        (위치 목록, 안내). 위치는 동 여럿일 때만 둘 이상이다.

    Raises:
        RegionAmbiguousError: 이름이 같은 동이 여러 시·구에 있을 때 (구 이름을 붙이게 한다).
        UnsupportedRegionError: 시·군·구 이름일 때 (다방은 시·군·구 전체를 찾지 못한다).
        RegionNotFoundError: 찾지 못했을 때.
    """
    text = query.strip()
    words = _words(text, REGION_HINT)
    last, context = words[-1], words[:-1]
    result = searched if searched is not None else search_locations(client, text)
    regions = [region for region in result.region_list if _matches_context(region.full_name, context)]
    exact = [region for region in regions if region.name == last]
    stations = [station for station in result.subway_list if station.name in (last, f'{last}역')]
    # 이름이 똑같은 대학을 먼저 본다. '연세대' 는 연세대학교·연세대학교(원주캠퍼스)·연세대학교(국제캠퍼스)에 맞는다 (2026-10-25 실측)
    universities = (
        [univ for univ in result.univ_list if univ.name == last]
        or [univ for univ in result.univ_list if univ.name.startswith(last)]
    )
    notes: list[str] = []

    def station_place() -> DabangPlace:
        station = stations[0]
        if len(stations) > 1:
            notes.append(note('모호', f"{quoted(station.name, '이/가')} 여러 곳이라 첫 역으로 찾았습니다"))
        lat, lng = _lat_lng(station.location, station.name)
        return DabangPlace(
            kind='station',
            name=station.name,
            lat=lat,
            lng=lng,
            place_id=station.id,
            radius_m=station.radius,
        )

    if last.endswith('역') and stations:
        return [station_place()], notes
    if len(exact) == 1:
        return [place_of_region(exact[0])], notes
    if len(exact) > 1:
        candidates = [normalize_address(region.full_name) or region.name for region in exact]
        raise RegionAmbiguousError(text, candidates[:AMBIGUOUS_CANDIDATES], len(candidates))
    if stations:
        return [station_place()], notes
    if universities:
        univ = universities[0]
        if len(universities) > 1:
            others = ', '.join(f"'{other.name}'" for other in universities[1:AMBIGUOUS_CANDIDATES])
            notes.append(note('모호', f"{quoted(last, '이/가')} 대학 {len(universities)}곳에 맞아 첫 곳({univ.name})으로 찾았습니다. 다른 곳은 이름을 따옴표로 감싸 그대로 주세요 ({others})"))
        lat, lng = _lat_lng(univ.location, univ.name)
        return [DabangPlace(
            kind='university',
            name=univ.name,
            lat=lat,
            lng=lng,
            place_id=univ.id,
        )], notes
    split = [region for region in regions if re.fullmatch(re.escape(last) + r'\d+가', region.name)]
    if split:
        cities = {normalize_address(region.full_name or '').rsplit(' ', 1)[0] for region in split}
        if len(cities) > 1:
            raise RegionAmbiguousError(text, sorted(cities)[:AMBIGUOUS_CANDIDATES], len(cities))
        places = [place_of_region(region) for region in sorted(split, key=lambda region: region.name)]
        if len(places) > 1:
            # --limit 을 동마다 나누는 것은 동 목록(region)을 동마다 받는 매물 검색뿐이라 그 안내는 search_listings 가 붙인다.
            # 아파트·단지·분양은 동들을 덮는 사각형 하나로 받는다
            notes.append(note('범위', f"{'·'.join(place.name for place in places)}를 합쳐 찾았습니다"))
        return places, notes
    if DISTRICT_PATTERN.fullmatch(last) and result.region_list:
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
    그래서 시·군·구 경계(`scope_bbox`)처럼 없을 때를 대신하지 않고, 403 은 UPSTREAM_ERROR 로 두어 스펙 변경으로 알린다.
    """
    return client.run_request_geojson_region(DabangGeojsonRegionRequestParameterModel(code=code)).coordinates


def _covering_bbox(boundaries: list[MultiPolygon]) -> DabangBboxModel:
    """경계들을 모두 덮는 지도 범위 (동 경계·시군구 경계)."""
    points = [point for boundary in boundaries for polygon in boundary for ring in polygon for point in ring]
    lats = [point[1] for point in points]
    lngs = [point[0] for point in points]
    return bbox_of(min(lats), max(lats), min(lngs), max(lngs))


def dongs_bbox(client: DabangClient, places: list[DabangPlace]) -> DabangBboxModel:
    """동들의 경계를 모두 덮는 지도 범위 (동마다 경계 요청 1회). 동 검색이 없는 아파트와 '○가' 동을 한 번에 찾을 때 쓴다."""
    # 동 코드는 장소 검색 응답 값이다. 늘 8자리라 요청 모델의 꼴(8자리)을 벗어나지 않아 따로 막지 않는다 (core/schema.py,
    # 2026-10-26 실측: 중구·신사동·효자동·성수동 장소 검색의 동 61곳 모두 8자리). 시·군·구 범위의 앞 5자리도 같다
    return _covering_bbox([dong_boundary(client, place.code or '') for place in places])


NATIONAL_NAMES: frozenset[str] = frozenset({'전국', '전체', '대한민국'})
# 시·도 표(`SIDO_OFFICIAL_NAMES`)에 옛 광주광역시로 있지만 범위로는 시·군·구인 이름. 당근 `--city`·네이버 `regions` 처럼
# 경기도 광주시로 본다 (옛 광주광역시는 '광주'·'전남광주'). 2026-10-26 실측: 시·도로 보면 region-ranking 광주시 가 안내 없이
# 전남광주통합특별시 순위를 주고, search sales 광주시 는 시·도 범위라며 막혔다
DISTRICT_NOT_STATE_NAMES: frozenset[str] = frozenset({'광주시'})


def state_name(text: str) -> str | None:
    """시·도 줄임말·정식 이름이면 정식 이름 ('충북'·'충청북도' → '충청북도'), 아니면 None. '광주시' 는 경기도 광주시라 None."""
    if text in DISTRICT_NOT_STATE_NAMES:
        return None
    return SIDO_OFFICIAL_NAMES.get(text) or (text if text in SIDO_OFFICIAL_NAMES.values() else None)


class DabangScope(BaseModel):
    """순위·분양 범위: 전국, 시·도, 시·군·구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    kind: Annotated[
        Literal['national', 'state', 'district'],
        Field(description='범위 종류 (전국·시도·시군구)')
    ]
    name: Annotated[
        str,
        Field(description="범위 이름 ('전국', '서울특별시', '서울특별시 강남구')")
    ]
    code: Annotated[
        str | None,
        Field(description='법정동 코드 앞자리 (시·도 2, 시·군·구 5자리)')
    ] = None
    gid: Annotated[
        int | None,
        Field(exclude=True, description='다방 지역 번호 (전국은 없음)')
    ] = None
    lat: Annotated[
        float | None,
        Field(exclude=True, description='중심 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(exclude=True, description='중심 경도')
    ] = None


def _region_by_code(client: DabangClient, code: str) -> DabangRegionModel | None:
    try:
        return client.run_request_region_v5(DabangRegionV5RequestParameterModel(code=code)).result
    except HTTPStatusError as exc:
        # 코드는 쿼리로 간다. 모르는 코드에는 에러 대신 다른 지역을 준다 (2026-10-27 실측: 99999 → 서초동)
        if is_missing_id(exc, in_path=False):
            return None
        raise


def resolve_scope(client: DabangClient, query: str, *, searched: DabangLocSearchResultModel | None = None) -> DabangScope:
    """'전국'·시·도·시·군·구 이름을 범위로 바꾼다. 시·도는 시·도 목록(요청 1회), 시·군·구는 장소 검색의 동 코드 앞 5자리로
    다방 지역을 받는다 (요청 2회). 구가 있는 시(성남시)는 다방 지역이 아니라 구 이름을 붙이게 한다.

    Args:
        searched: 같은 이름으로 이미 받은 장소 검색 결과. 주면 다시 묻지 않는다.

    Raises:
        RegionAmbiguousError: 시·군·구 이름이 여러 시·도에 있을 때 ('중구').
        UnsupportedRegionError: 구가 있는 시일 때 ('성남시').
        RegionNotFoundError: 범위로 알아볼 수 없는 이름일 때.
    """
    text = query.strip()
    if text in NATIONAL_NAMES:
        return DabangScope(kind='national', name='전국')
    official = state_name(text)
    if official is not None:
        states = client.run_request_region_states_v5(DabangRegionStatesV5RequestParameterModel()).result or []
        state = next((item for item in states if item.name == official or item.short_name == text), None)
        if state is not None:
            location = state.location
            return DabangScope(
                kind='state', name=state.name, code=state.code, gid=state.gid,
                lat=location.lat if location else None, lng=location.lng if location else None,
            )
    words = _words(text, SCOPE_HINT)
    last = words[-1]
    if DISTRICT_PATTERN.fullmatch(last):
        # 시·군·구 이름마다 처음 나온 동 하나 ('중구' 는 서울·부산·대구·대전·울산, 2026-10-25 실측)
        districts: dict[str, tuple[DabangLocRegionModel, list[str], int]] = {}
        for region in (searched if searched is not None else search_locations(client, text)).region_list:
            parts = (region.full_name or '').split()
            if last not in parts[1:3] or not _matches_context(region.full_name, words):
                continue
            index = parts.index(last)
            districts.setdefault(' '.join(parts[:index + 1]), (region, parts, index))
        if len(districts) > 1:
            names = sorted(normalize_address(name) for name in districts)
            raise RegionAmbiguousError(
                text, names[:AMBIGUOUS_CANDIDATES], len(names), hint=f"시·도를 붙여 다시 주세요 (예: '{names[0]}')",
            )
        for region, parts, index in districts.values():
            if index == 1 and len(parts) > 3 and parts[2].endswith('구'):
                # 구가 있는 시(경기도 성남시 수정구 …)는 다방 지역이 아니다. 시 코드(41130)를 물으면 다른 지역(서초동)을
                # 돌려준다 (2026-10-25 실측). 구 이름을 붙이게 한다
                raise UnsupportedRegionError(
                    code='REGION_NOT_SUPPORTED',
                    message=f"다방은 구가 있는 시 전체를 범위로 받지 않습니다: '{text}'",
                    hint=f"구 이름을 붙여 주세요 (예: '{last} {parts[2]}')",
                    skip_note=f'{text} 는 구가 있는 시라 건너뛰었습니다',
                )
            # 동 코드(늘 8자리, `dongs_bbox` 참고)의 앞 5자리라 요청 모델의 꼴을 벗어나지 않는다
            code = region.code[:5]
            found = _region_by_code(client, code)
            # 모르는 코드에 다른 지역을 줄 수 있어 코드가 같은지 본다
            if found is not None and found.code == code:
                location = found.location
                return DabangScope(
                    kind='district', name=normalize_address(' '.join(parts[:index + 1])), code=found.code, gid=found.gid,
                    lat=location.lat if location else None, lng=location.lng if location else None,
                )
    raise RegionNotFoundError(text, hint=SCOPE_HINT)


def scope_bbox(client: DabangClient, scope: DabangScope) -> DabangBboxModel | None:
    """시·군·구 경계를 덮는 지도 범위 (경계 요청 1회). 경계 파일이 없으면 None."""
    if scope.kind != 'district' or scope.code is None:
        return None
    try:
        polygons = client.run_request_geojson_region(DabangGeojsonRegionRequestParameterModel(code=scope.code)).coordinates
    except HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            return None
        raise
    return _covering_bbox([polygons])
