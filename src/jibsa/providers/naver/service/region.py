"""지역·역·단지 이름과 좌표 해석, 시·도·시·군·구 목록 (regions, 모든 검색의 지역 해석)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.korean import (
    is_dong_code,
    particle,
    quoted,
)
from jibsa.core.listing import (
    SIDO_OFFICIAL_NAMES,
    normalize_address,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverLegalDivisionSearchByCoordinateV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.region import (
    NaverLegalDivisionInfoListByLevelV1RequestParameterModel,
    NaverLegalDivisionSubInfoListV1RequestParameterModel,
    NaverMapsSearchAddressV1RequestParameterModel,
    NaverSearchAutocompleteComplexesV1RequestParameterModel,
    NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel,
    NaverSearchAutocompleteSubwayStationsV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import NaverCoordinatesModel
from jibsa.providers.naver.api.response.region import (
    NaverAddressElementsModel,
    NaverAddressModel,
    NaverAutocompleteComplexModel,
    NaverAutocompleteLegalDivisionModel,
    NaverAutocompleteSubwayStationModel,
    NaverLegalDivisionInfoModel,
)
from jibsa.providers.naver.service.common import (
    VILLA_COMPLEX_CODES,
    unwrap,
)

from typing import (
    Annotated,
    Literal,
)


def _lat_lng(coordinates: NaverCoordinatesModel | None) -> tuple[float, float]:
    """자동완성 후보의 (위도, 경도). 좌표 없는 후보는 미리 빼고 부른다."""
    assert coordinates is not None
    return coordinates.y_coordinate, coordinates.x_coordinate


# 같은 이름 지역·비슷한 이름 단지를 안내할 때 보여 줄 후보 수
MAX_CANDIDATE_NOTES: int = 5


class NaverRegion(BaseModel):
    """검색 중심점. 직방 지역 검색 결과(`ZigbangRegion`)와 같은 모양이라 출력의 `region` 이 어느 쪽으로 찾든 같다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='지역·역·단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='전체 주소 (역은 null)')
    ] = None
    lat: Annotated[
        float,
        Field(description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='중심 경도')
    ]
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리, 역은 null)')
    ] = None


# 끝말 없이 준 지역 이름('송정', '해운대')에 붙여 이름 전체로 보는 끝말
DIVISION_NAME_SUFFIXES: tuple[str, ...] = ('동', '구', '시', '군', '읍', '면')


def _last_word(name: str) -> str:
    """전체 이름의 마지막 단어 ('서울시 강남구 역삼동' → 역삼동)."""
    return name.split()[-1] if name.split() else name


def _station_label(station: NaverAutocompleteSubwayStationModel) -> str:
    lines = ', '.join(line.name for line in station.line_infos)
    return f'{station.station_name}({lines})' if lines else station.station_name


def _other_candidates_note(query: str, chosen: str, others: list[tuple[str, float, float]]) -> str:
    """같은 이름이 여러 곳일 때 안내. 다른 곳은 좌표로 다시 찾게 한다 (구 이름을 붙인 검색어는 확인하지 않았다)."""
    # 받은 좌표를 그대로 쓴다. ':g' 는 유효숫자 6자리라 경도가 소수 셋째 자리(최대 약 44m 오차)로 잘린다
    retry = ', '.join(f'{label} --lat {lat} --lng {lng}' for label, lat, lng in others[:MAX_CANDIDATE_NOTES])
    return (
        f"'{query}': 같은 이름이 여러 곳에 있어 첫 번째인 {chosen} 기준으로 검색했습니다. "
        f'다른 곳이면 좌표로 다시 검색하세요: {retry}'
    )


def _wide_region_unit(code: str | None) -> str:
    """넓은 지역 안내의 단위. 법정동 코드 앞 두 자리 뒤가 모두 0 이면 시·도다.

    주소 검색은 시·도 이름(서울, 전라남도)도 지역 하나로 준다 (서울 bcode 1100000000, 시·군·구 칸 빈 값, 2026-10-10).
    """
    return '시·도' if code and len(code) == 10 and code[2:] == '0' * 8 else '시·군·구'


def _find_legal_division(
    client: NaverClient,
    query: str,
    radius_km: float | None,
    *,
    stop_if_ambiguous: bool = False,
) -> tuple[NaverRegion, list[str]] | None:
    """동 자동완성으로 법정동을 찾는다. 같은 이름이 여러 곳이면 첫 번째로 찾고 다른 곳을 안내한다.

    Raises:
        RegionAmbiguousError: `stop_if_ambiguous` 인데 같은 이름이 여러 곳일 때 ('신사' → 강남구·은평구·관악구 신사동).
    """
    page = unwrap(
        client.run_request_search_autocomplete_legal_divisions_v1(
            NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=query)
        ),
        '지역 검색',
    )
    items = [item for item in page.items if item.coordinates is not None]
    if not items:
        return None
    # 동·구 이름을 끝말 없이 줘도('신흥', '해운대') 그 이름의 곳을 고른다. 첫 결과로 고르면 '신흥' 이 인천 신흥동1가가
    # 되고 같은 이름 신흥동 여러 곳(대전 동구·성남 수정구 …)을 알리지 않는다 (2026-10-11)
    names = {query, *(query + suffix for suffix in DIVISION_NAME_SUFFIXES)}
    best = next((item for item in items if _last_word(item.legal_division_name) in names), items[0])
    notes: list[str] = []
    same = [item for item in items if _last_word(item.legal_division_name) == _last_word(best.legal_division_name)]
    if len(same) >= 2 and stop_if_ambiguous:
        words = query.split()
        full_name = _last_word(best.legal_division_name)
        if words[-1] != full_name:
            # 끝말 없는 이름('신흥')은 주소 검색이 못 찾지만 이름 전체('신흥동')로는 같은 이름 동을 모두 준다 (신흥동 14곳.
            # 자동완성은 대전·성남 2곳에 totalCount 12, 신사 2곳 ↔ 신사동 3곳, 2026-10-11). 그래서 이름 전체로 1회 더 물어
            # `search listings 신흥동` 과 같은 후보로 멈춘다
            others, others_total = _search_address(client, ' '.join([*words[:-1], full_name]))
            if others_total > 1:
                raise RegionAmbiguousError(
                    query, [item.full_address for item in others[:MAX_CANDIDATE_NOTES] if item.full_address], others_total,
                )
        # 자동완성은 한 쪽에 다섯 곳만 줘서 다음 쪽이 있으면 전체 수(totalCount)로 센다 ('송정' 은 첫 쪽 다섯 곳이 모두
        # 송정동이고 totalCount 14, 2026-10-11). totalCount 는 '중앙동1가' 같은 비슷한 이름도 세어 조금 많을 수 있다
        total = max(page.total_count or 0, len(same)) if page.has_next_page else len(same)
        raise RegionAmbiguousError(
            query, [normalize_address(item.legal_division_name) for item in same[:MAX_CANDIDATE_NOTES]], total,
        )
    if len(same) >= 2:
        notes.append(_other_candidates_note(query, normalize_address(best.legal_division_name), [
            (normalize_address(item.legal_division_name), *_lat_lng(item.coordinates))
            for item in same
            if item is not best
        ]))
    # 단위는 GUN·EUP 만 온다. 서울·경기도 같은 시·도는 그 안의 구(GUN)로 오고, 리는 자동완성에 나오지 않는다
    # (검색어 16개, 2026-10-09 확인). 그래서 EUP 가 아니면 시·군·구로 본다.
    if radius_km is not None and best.legal_division_level_type not in (None, 'EUP'):
        notes.append(
            f"'{query}': {_wide_region_unit(best.legal_division_number)} 단위의 넓은 지역이라 중심({normalize_address(best.legal_division_name)})에서 "
            f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요'
        )
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=_last_word(best.legal_division_name),
        # 자동완성은 '서울시 강남구 역삼동'·'세종시 세종시 반곡동' 처럼 줘 매물 주소처럼 정식 이름으로 바꾼다 (2026-10-11)
        address=normalize_address(best.legal_division_name),
        lat=lat,
        lng=lng,
        legal_division_code=best.legal_division_number,
    )
    return region, notes


def _find_subway_station(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, list[str]] | None:
    items = [
        item
        for item in unwrap(
            client.run_request_search_autocomplete_subway_stations_v1(
                NaverSearchAutocompleteSubwayStationsV1RequestParameterModel(keyword=query)
            ),
            '역 검색',
        ).items
        if item.coordinates is not None
    ]
    if not items:
        return None
    names = (query, f'{query}역')
    best = next((item for item in items if item.station_name in names), items[0])
    same = [item for item in items if item.station_name == best.station_name and item is not best]
    notes = [
        _other_candidates_note(query, _station_label(best), [
            (_station_label(item), *_lat_lng(item.coordinates)) for item in same
        ])
    ] if same else []
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=best.station_name,
        lat=lat,
        lng=lng,
    )
    return region, notes


def search_complexes(client: NaverClient, keyword: str) -> list[NaverAutocompleteComplexModel]:
    """단지 이름 자동완성 첫 페이지. 사이트 검색창과 같은 순서다."""
    return unwrap(
        client.run_request_search_autocomplete_complexes_v1(
            NaverSearchAutocompleteComplexesV1RequestParameterModel(keyword=keyword)
        ),
        '단지 검색',
    ).items


def _complex_candidates_note(query: str, best: NaverAutocompleteComplexModel, items: list[NaverAutocompleteComplexModel]) -> str | None:
    others = [item for item in items if item is not best][:MAX_CANDIDATE_NOTES]
    if not others:
        return None
    listed = ', '.join(f'{item.complex_name}({item.complex_number})' for item in others)
    return f"'{query}': 이름이 비슷한 단지가 더 있어 {best.complex_name}({best.complex_number}) {particle(best.complex_name, '을/를')} 골랐습니다. 다른 단지: {listed}"


def _pick_complex(query: str, items: list[NaverAutocompleteComplexModel]) -> NaverAutocompleteComplexModel:
    return next((item for item in items if item.complex_name == query), items[0])


def _find_complex(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, list[str]] | None:
    items = [item for item in search_complexes(client, query) if item.coordinates is not None]
    if not items:
        return None
    best = _pick_complex(query, items)
    note = _complex_candidates_note(query, best, items)
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=best.complex_name,
        address=normalize_address(best.legal_division_name),
        lat=lat,
        lng=lng,
        legal_division_code=best.legal_division_number,
    )
    return region, [note] if note else []


def resolve_region_with_notes(
    client: NaverClient,
    query: str,
    radius_km: float = 1.0,
) -> tuple[NaverRegion, list[str]]:
    """지역·역·단지 이름을 검색 중심점으로 바꾼다. 모호하거나 넓은 지역이면 안내를 함께 준다.

    네이버 검색창 자동완성을 동 → 역 → 단지 순으로 찾고 처음 나온 결과를 쓴다. '역' 으로 끝나면
    역을 먼저 찾는다. 찾을 때마다 요청이 하나씩 들어 대개 1회, 많아야 3회다.

    Raises:
        RegionNotFoundError: 셋 다 결과가 없을 때.
    """
    lookups = [_find_legal_division, _find_subway_station, _find_complex]
    if query.endswith('역'):
        lookups = [_find_subway_station, _find_legal_division, _find_complex]
    for lookup in lookups:
        found = lookup(client, query, radius_km)
        if found is not None:
            return found
    raise RegionNotFoundError(query)


# 주소 검색 itemLevel 이 이 값 이상이면 번지·건물 단위다 (5 시·도/시·군·구, 8 동·읍·면, 12 번지·건물)
ADDRESS_LOT_ITEM_LEVEL: int = 12


def _search_address(client: NaverClient, query: str) -> tuple[list[NaverAddressModel], int]:
    """사이트 검색창의 주소 검색 결과(좌표 있는 것)와 전체 수."""
    result = unwrap(
        client.run_request_maps_search_address_v1(NaverMapsSearchAddressV1RequestParameterModel(query=query)),
        '주소 검색',
    )
    block = result.road_address if result.type == 'road-address' else result.jibun_address
    if block is None:
        return [], 0
    items = [item for item in block.items if item.x is not None and item.y is not None]
    # 목록은 앞 10곳만 와서(중앙동 37곳) 개수는 totalCount 로 센다. 좌표 없는 항목은 실제로 오지 않아
    # (검색어 24개, 2026-10-09 확인) 걸러진 항목 때문에 totalCount 가 부풀 일은 없다.
    return items, max(block.total_count, len(items)) if items else 0


def _find_address(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, str, list[str]] | None:
    """사이트 검색창의 주소 검색. 번지·도로명이면 그 지점, 법정동이면 그 동, 시·군·구면 넓은 지역이다.

    동 이름 일부('송정')로 찾은 동은 동 이름 전체로 1회 더 물어 같은 이름 동이 여러 곳인지 본다.

    Raises:
        RegionAmbiguousError: 같은 이름의 동·주소가 여러 곳일 때 (신사동 3곳, 중앙동 1 은 21곳, 송정 15곳).
    """
    items, total = _search_address(client, query)
    if not items:
        return None
    if total > 1:
        raise RegionAmbiguousError(
            query, [item.full_address for item in items[:MAX_CANDIDATE_NOTES] if item.full_address], total,
        )
    item = items[0]
    elements = item.address_elements or NaverAddressElementsModel()
    code = elements.bcode or None
    words = query.split()
    if is_dong_code(code) and not elements.ri and elements.dongmyun and words[-1] != elements.dongmyun:
        # 동 이름 일부는 주소 검색이 대표 한 곳만 준다 ('송정' 은 부산 해운대구 송정동 1곳, '송정동' 은 15곳.
        # '역삼'·'역삼동' 은 둘 다 강남구 역삼동 1곳, 2026-10-11). 그래서 동 이름 전체로 다시 물어 여러 곳이면 멈춘다
        same, same_total = _search_address(client, ' '.join([*words[:-1], elements.dongmyun]))
        if same_total > 1:
            raise RegionAmbiguousError(
                query, [other.full_address for other in same[:MAX_CANDIDATE_NOTES] if other.full_address], same_total,
            )
    full_address = item.full_address or query
    notes: list[str] = []
    if (item.item_level or 0) >= ADDRESS_LOT_ITEM_LEVEL or elements.jibun or elements.build_number:
        kind, name = '주소', full_address
    elif is_dong_code(code) and not elements.ri:
        kind, name = '동', elements.dongmyun or _last_word(full_address)
    elif elements.ri:
        # 리 코드(…21)를 legalDivisionArticleList 에 넣으면 리 자리를 무시하고 읍·면 전체를 준다 (문호리·수입리·
        # 서종면 모두 850건, 2026-10-09 확인). 그래서 동 경계 대신 반경이다. 리는 넓어(문호리 약 5×7km) 반경을 키우게 알린다
        kind, name = '지역', elements.ri
        if radius_km is not None:
            notes.append(
                f"'{query}': 리 단위는 경계 검색을 지원하지 않아 중심({full_address})에서 반경 {radius_km:g}km 안만 "
                '검색했습니다' + ('. 리 전체를 보려면 --radius 를 늘리세요 (최대 3km)' if radius_km < 3 else '')
            )
    elif elements.dongmyun:
        # 행정동(역삼1동, 관악구 신사동)은 법정동 코드가 비어 있어 동 경계로 찾을 수 없다
        kind, name = '지역', elements.dongmyun
        if radius_km is not None:
            notes.append(
                f"'{query}': 행정동이라 동 경계로 찾을 수 없어 중심({full_address})에서 반경 {radius_km:g}km 안만 "
                '검색했습니다. 법정동 이름(예: 역삼1동 → 역삼동)으로 검색하면 동 전체를 찾습니다'
            )
    else:
        kind, name = '지역', _last_word(full_address)
        if radius_km is not None:
            notes.append(
                f"'{query}': {_wide_region_unit(code)} 단위의 넓은 지역이라 중심({full_address})에서 "
                f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요'
            )
    region = NaverRegion(name=name, address=full_address, lat=item.y, lng=item.x, legal_division_code=code)
    return region, kind, notes


def resolve_search_region(
    client: NaverClient,
    query: str,
    radius_km: float | None = 1.0,
) -> tuple[NaverRegion, str, list[str]]:
    """`naver search listings` 의 검색어를 검색 위치와 그 종류로 바꾼다.

    주소 검색 → 동 → 역 → 단지 순으로 찾고 처음 나온 결과를 쓴다. '역' 으로 끝나면 역을 먼저 찾는다
    (주소 검색이 역 이름을 찾지 못해 요청 1회가 헛돈다). 대개 요청 1회다 (동 이름 일부('송정')면 1회 더). 당근의 위치 찾기는
    `resolve_region_with_notes` (동 → 역 → 단지)를 쓴다. `radius_km` 는 안내에만 쓰고, 반경으로 찾지 않는 호출부(trend)는
    None 을 넘겨 '반경 안만 검색했습니다' 안내를 받지 않는다.

    Returns:
        tuple[NaverRegion, str, list[str]]: 위치, 종류('주소', '동', '역', '단지', '지역'), 안내.
            '동' 이면 법정동 코드가 있어 동 전체를 검색할 수 있다.

    Raises:
        RegionAmbiguousError: 같은 이름의 동·주소가 여러 곳일 때.
        RegionNotFoundError: 넷 다 결과가 없을 때.
    """
    def legal_division(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_legal_division(client, query, radius_km, stop_if_ambiguous=True)
        if found is None:
            return None
        region, notes = found
        return region, '동' if is_dong_code(region.legal_division_code) else '지역', notes

    def station(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_subway_station(client, query, radius_km)
        return None if found is None else (found[0], '역', found[1])

    def complex_(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_complex(client, query, radius_km)
        return None if found is None else (found[0], '단지', found[1])

    lookups = [_find_address, legal_division, station, complex_]
    if query.endswith('역'):
        lookups = [station, _find_address, legal_division, complex_]
    for lookup in lookups:
        found = lookup(client, query, radius_km)
        if found is not None:
            return found
    raise RegionNotFoundError(
        query,
        hint="주소(예: '역삼동 719-28', '테헤란로 152'), 동 이름(예: '역삼동'), 역 이름(예: '강남역'), "
        '단지 이름으로 다시 검색하거나 --lat/--lng 로 좌표를 직접 주세요',
    )


def resolve_complex_number(client: NaverClient, name: str) -> tuple[int, bool | None, list[str]]:
    """단지 이름을 단지 번호로 바꾼다. 이름이 똑같은 단지를 우선하고, 후보가 더 있으면 안내를 함께 준다.

    Returns:
        tuple[int, bool | None, list[str]]: 단지 번호, 빌라 단지인지 (`complex_is_villa`), 안내.

    Raises:
        JibsaError: 단지를 찾지 못하면 NOT_FOUND.
    """
    items = search_complexes(client, name)
    if not items:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"'{name}' 에 해당하는 네이버 단지를 찾지 못했습니다",
            hint='단지 이름을 줄이거나(예: 래미안) 단지 번호(fin.land.naver.com/complexes/{번호})로 다시 조회하세요',
        )
    best = _pick_complex(name, items)
    note = _complex_candidates_note(name, best, items)
    return best.complex_number, complex_is_villa(best.type), [note] if note else []


def complex_is_villa(code: str | None) -> bool | None:
    """단지 유형 코드로 빌라 단지인지 본다. 아파트·오피스텔 단지면 False, 모르는 코드면 None.

    자동완성의 유형은 빌라 단지가 A06, 아파트가 A01, 오피스텔이 A02 다. A01·A02 는 아파트 단지
    엔드포인트가 답한다 (2026-10-09 확인).
    """
    if code in VILLA_COMPLEX_CODES:
        return True
    if code in ('A01', 'A02'):
        return False
    return None


def legal_division_code_at(client: NaverClient, lat: float, lng: float) -> tuple[str, str | None] | None:
    """좌표가 속한 법정동 코드와 이름. 그 자리에 법정동이 없으면 None.

    Raises:
        JibsaError: 실패 응답(isSuccess false)이면 UPSTREAM_ERROR. 법정동 없음으로 보지 않는다.
    """
    response = client.run_request_legal_division_search_by_coordinate_v1(
        NaverLegalDivisionSearchByCoordinateV1RequestParameterModel(latitude=lat, longitude=lng)
    )
    # 바다처럼 법정동이 없는 좌표는 isSuccess true·result null 이다 (34.0,125.0·37.55,124.5·90,180, 2026-10-11).
    # 잘못된 좌표(-90,-180·경도 빠짐·문자)는 실패 봉투가 아니라 HTTP 400 FST_ERR_VALIDATION 이라, 이 엔드포인트의
    # 실패 봉투(isSuccess false)는 실측으로 재현되지 않았다. 다른 엔드포인트처럼 실패 봉투가 오면 법정동 없음으로 보지 않는다
    if response.is_success and response.result is None:
        return None
    division = unwrap(response, '좌표의 법정동')
    if not division.legal_division_number:
        return None
    return division.legal_division_number, division.legal_division_name


REGION_LEVEL_LABELS: dict[str, str] = {'SI': '시·도', 'GUN': '시·군·구', 'EUP': '읍·면·동'}
# 합쳐진 시·도의 옛 이름. 시·도 목록에 광주광역시·전라남도 없이 전남광주통합특별시(네이버 이름 '전남광주시') 하나만
# 있고, 그 아래에 광산구 등 광주의 구와 강진군 등 전남의 군 27곳이 있다 (2026-10-10). 시·도는 `SIDO_OFFICIAL_NAMES` 로
# 찾고, 이 이름으로 찾았으면 옛 이름이라고 알린다
FORMER_PROVINCE_NAMES: frozenset[str] = frozenset({'전라남도', '전남', '광주광역시', '광주'})
# `SIDO_OFFICIAL_NAMES` 에서는 옛 광주광역시지만, 한 단어로 오면 경기도 광주시로 찾는 이름. 시·도를 붙인
# '광주시 광산구' 는 경기도 광주시에 구가 없어 전남광주통합특별시로 본다
CITY_NOT_PROVINCE_NAMES: frozenset[str] = frozenset({'광주시'})
# 옛 이름이 다른 시·도의 시와 겹칠 때 덧붙이는 안내 (search listings '광주' 는 경기도 광주시와 겹쳐 REGION_AMBIGUOUS, 2026-10-10)
FORMER_PROVINCE_NAME_HINTS: dict[str, str] = {
    '광주': "경기도 광주시는 '광주시' 로 찾으세요",
}


class NaverRegionEntry(BaseModel):
    """지역 목록의 지역 하나. 지역 후보라 중심 좌표를 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='지역 이름 (예: 강남구, 개포동, 성남시 분당구). 다른 명령의 지역 인자에 넣는다')
    ]
    level: Annotated[
        str | None,
        Field(description='단위 (시·도, 시·군·구, 읍·면·동)')
    ] = None
    legal_division_code: Annotated[
        str,
        Field(description='법정동 코드 (10자리)')
    ]
    lat: Annotated[
        float | None,
        Field(description='중심 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='중심 경도')
    ] = None


class NaverRegionList(BaseModel):
    """지역 하나의 바로 아래 지역 목록 (지역을 주지 않으면 시·도 전체)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    parent: Annotated[
        str | None,
        Field(description='상위 지역 (예: 서울시 강남구). 시·도 전체 목록이면 null')
    ] = None
    parent_code: Annotated[
        str | None,
        Field(description='상위 지역 법정동 코드. 시·도 전체 목록이거나 구가 있는 시면 null')
    ] = None
    regions: Annotated[
        list[NaverRegionEntry],
        Field(description='하위 지역 (네이버 순서, 대개 가나다순)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='같은 이름이 여러 곳일 때 안내 등. CLI 가 결과 위에 붙인다')
    ] = []


def _region_entry(item: NaverLegalDivisionInfoModel, name: str | None = None) -> NaverRegionEntry:
    coordinates = item.coordinates
    return NaverRegionEntry(
        name=name or item.legal_division_name or item.legal_division_number,
        level=REGION_LEVEL_LABELS.get(item.legal_division_level_type or ''),
        legal_division_code=item.legal_division_number,
        lat=coordinates.y_coordinate if coordinates else None,
        lng=coordinates.x_coordinate if coordinates else None,
    )


def _find_province(provinces: list[NaverLegalDivisionInfoModel], name: str) -> NaverLegalDivisionInfoModel | None:
    """시·도를 부르는 이름(서울·서울시·서울특별시·충북·전라북도·광주 등)에 맞는 시·도. 시·도 이름이 아니면 None.

    줄임말·옛 이름은 매물 주소와 같은 `SIDO_OFFICIAL_NAMES` 로 정식 명칭(`cityFullName`)에 맞춘다. 네이버 이름
    (`legalDivisionName`: 서울시·전북도)도 받는다.
    """
    official = SIDO_OFFICIAL_NAMES.get(name, name)
    return next(
        (item for item in provinces if official == item.city_full_name or name == item.legal_division_name),
        None,
    )


def _sub_regions(client: NaverClient, level: Literal['SI', 'GUN'], code: str) -> list[NaverLegalDivisionInfoModel]:
    return unwrap(
        client.run_request_legal_division_sub_info_list_v1(
            NaverLegalDivisionSubInfoListV1RequestParameterModel(legal_division_level_type=level, legal_division_number=code)
        ),
        '하위 지역',
    )


def list_regions(client: NaverClient, query: str | None = None) -> NaverRegionList:
    """지역 하나의 바로 아래 지역 (2~3회 호출). 지역을 주지 않으면 시·도 전체 (1회 호출).

    시·도 이름(서울, 경기도, 충북)이면 시·군·구, 시·군·구 이름(강남구, 부산시 중구)이면 읍·면·동을 준다. 시·군·구가 하나뿐인
    세종(세종·세종시)은 그 아래 읍·면·동을 준다.
    구가 있는 시(성남시)는 네이버가 시를 따로 두지 않아 시·도 목록에서 그 시의 구를 골라 준다.

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        JibsaError: 읍·면·동처럼 하위 지역이 없는 단위면 NOT_FOUND.
    """
    provinces = unwrap(
        client.run_request_legal_division_info_list_by_level_v1(NaverLegalDivisionInfoListByLevelV1RequestParameterModel()),
        '시·도 목록',
    )
    if query is None:
        return NaverRegionList(regions=[_region_entry(item, item.city_full_name) for item in provinces])
    query = query.strip()
    province = None if query in CITY_NOT_PROVINCE_NAMES else _find_province(provinces, query)
    if province is not None:
        name = province.city_full_name or province.legal_division_name
        # _find_province 가 둘 중 하나의 이름으로 찾았다
        assert name is not None
        children = _sub_regions(client, 'SI', province.legal_division_number)
        notes = [
            f"{name} 의 하위 지역입니다. 네이버 시·도 목록에는 옛 이름 '{query}' 대신 {name} 만 있습니다"
            + (f'. {FORMER_PROVINCE_NAME_HINTS[query]}' if query in FORMER_PROVINCE_NAME_HINTS else '')
        ] if query in FORMER_PROVINCE_NAMES else []
        if len(children) == 1 and children[0].legal_division_level_type == 'GUN':
            # 세종은 시·군·구가 '세종시' 하나뿐이고 그 이름이 시·도 별칭('세종시' → 세종특별자치시)이라, 시·군·구 목록을 주면
            # 'regions 세종시' 가 다시 같은 목록을 준다 (2026-10-11 실측). 하나뿐이면 그 아래 읍·면·동을 준다 (요청 1회 더)
            only = children[0]
            return NaverRegionList(
                parent=name,
                parent_code=only.legal_division_number,
                regions=[_region_entry(item) for item in _sub_regions(client, 'GUN', only.legal_division_number)],
                notes=notes + [f"{name}{particle(name, '은/는')} 시·군·구가 {only.legal_division_name} 하나뿐이라 그 아래 읍·면·동입니다"],
            )
        return NaverRegionList(
            parent=name,
            parent_code=province.legal_division_number,
            regions=[_region_entry(item) for item in children],
            notes=notes,
        )

    # 자동완성은 네이버식 시·도 이름('서울시 강남구')으로만 찾는다. 정식 명칭('서울특별시 강남구'·'부산광역시 중구')은
    # 빈 목록이고, '서울 강남구' 는 '서울시 강남구' 를 주지만 검색어와 이름이 달라 맞춰 볼 수 없다 (2026-10-10).
    # 옛 이름('광주 광산구')은 빈 목록이다 (2026-10-11). 그래서 첫 단어가 시·도 이름이면 시·도 목록의 네이버 이름
    # (legalDivisionName, '전남광주시')으로 바꿔 묻고 맞춰 본다
    words = query.split()
    named = _find_province(provinces, words[0]) if len(words) > 1 else None
    keyword = ' '.join([named.legal_division_name, *words[1:]]) if named and named.legal_division_name else query
    items = unwrap(
        client.run_request_search_autocomplete_legal_divisions_v1(
            NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=keyword)
        ),
        '지역 검색',
    ).items
    exact = [
        item for item in items
        if item.legal_division_name == keyword or item.legal_division_name.endswith(f' {keyword}')
    ]
    if not exact:
        # 구가 있는 시는 시 자신 대신 그 아래 구가 온다 ('성남시' → 경기도 성남시 수정구 …). 시·도 목록에서
        # '성남시 ' 로 시작하는 구를 모두 고른다 (자동완성은 한 쪽에 다섯 곳만 준다).
        # 시·도를 붙인 '경기도 성남시'·'경기 성남시' 도 자동완성이 같은 구를 주므로, 구 이름 앞의 단어들이
        # 검색어 단어들로 끝나는지 본다 (단어 하나씩 비교하면 여러 단어 검색어는 늘 REGION_NOT_FOUND, 2026-10-10)
        query_words = (normalize_address(keyword) or keyword).split()

        def city_words(item: NaverAutocompleteLegalDivisionModel) -> list[str]:
            return (normalize_address(item.legal_division_name) or '').split()[:-1]

        under = next(
            (
                item for item in items
                if item.legal_division_level_type == 'GUN' and city_words(item)[-len(query_words):] == query_words
            ),
            None,
        )
        if under is None:
            raise RegionNotFoundError(query, hint='시·도(서울, 경기도)나 시·군·구(강남구, 부산시 중구) 이름으로 다시 주세요')
        parent = city_words(under)
        entries = [
            _region_entry(item)
            for item in _sub_regions(client, 'SI', under.legal_division_number)
            if (item.legal_division_name or '').startswith(f'{parent[-1]} ')
        ]
        return NaverRegionList(parent=' '.join(parent), regions=entries)

    # 시·군·구를 먼저 본다 (하위 지역이 있는 쪽)
    exact.sort(key=lambda item: item.legal_division_level_type != 'GUN')
    best = exact[0]
    notes = []
    others = [
        item.legal_division_name for item in exact[1:]
        if item.legal_division_level_type == best.legal_division_level_type
    ]
    if others:
        listed = ', '.join(others[:MAX_CANDIDATE_NOTES])
        notes.append(
            f"'{query}': 같은 이름이 여러 곳에 있어 첫 번째인 {best.legal_division_name} 의 하위 지역입니다. "
            f"다른 곳이면 시·도 이름을 붙여 주세요 (예: '{others[0]}'). 다른 곳: {listed}"
        )
    if best.legal_division_level_type != 'GUN':
        raise JibsaError(
            code='NOT_FOUND',
            message=f"{quoted(best.legal_division_name, '은/는')} 읍·면·동이라 하위 지역이 없습니다",
            hint='시·도(서울, 경기도)나 시·군·구(강남구) 이름을 주세요. 동은 search listings 등에 바로 넣으면 됩니다',
        )
    return NaverRegionList(
        parent=normalize_address(best.legal_division_name),
        parent_code=best.legal_division_number,
        regions=[_region_entry(item) for item in _sub_regions(client, 'GUN', best.legal_division_number)],
        notes=notes,
    )
