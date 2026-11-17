"""지역·역·단지 이름과 좌표 해석, 시·도·시·군·구 목록 (regions, 모든 검색의 지역 해석)."""

import re
from collections.abc import Callable

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
    CITY_NAMES_NOT_SIDO,
    SIDO_OFFICIAL_NAMES,
    normalize_address,
    note,
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
    NaverAutocompletePageModel,
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
    TypeVar,
)


def _lat_lng(coordinates: NaverCoordinatesModel | None) -> tuple[float, float]:
    """자동완성 후보의 (위도, 경도). 좌표가 없는 후보는 부르는 쪽이 먼저 멈춘다."""
    assert coordinates is not None
    return coordinates.y_coordinate, coordinates.x_coordinate


# 같은 이름 지역·역을 안내할 때 보여 줄 후보 수
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


def _station_candidate(station: NaverAutocompleteSubwayStationModel) -> str:
    """같은 이름 역 후보 글. 역 이름·노선이 같은 역이 따로 와서('시청역(1호선)' 이 대전·부산) 좌표로 다시 찾게 한다."""
    if station.coordinates is None:
        return f'{_station_label(station)} (좌표 없음)'
    # 받은 좌표를 그대로 쓴다. ':g' 는 유효숫자 6자리라 경도가 소수 셋째 자리(최대 약 44m 오차)로 잘린다
    lat, lng = _lat_lng(station.coordinates)
    return f'{_station_label(station)} --lat {lat} --lng {lng}'


AutocompleteItemT = TypeVar('AutocompleteItemT')
# 이름이 맞는 후보를 모으려고 받는 자동완성 쪽 수 (첫 쪽 포함). 법정동·역은 한 쪽 5곳이라 15곳까지 본다
MAX_AUTOCOMPLETE_PAGES: int = 3


def _collect_matching(
    fetch: Callable[[int], NaverAutocompletePageModel[AutocompleteItemT]],
    first: NaverAutocompletePageModel[AutocompleteItemT],
    matches: Callable[[AutocompleteItemT], bool],
) -> tuple[list[AutocompleteItemT], bool]:
    """자동완성 첫 쪽 뒤로 이름이 맞는 후보가 이어지면 다음 쪽을 더 받아 모은다 (웹 검색창의 '더보기' 와 같은 요청).

    법정동·역 자동완성은 이름이 맞는 곳을 앞에, 이름 일부만 맞는 곳을 뒤에 준다 (2026-11-17 실측: '중구' 첫 쪽 5곳이 모두
    중구이고 둘째 쪽부터 중구 안의 동, '강남구' 는 강남구 다음에 그 안의 동, '시청역' 은 시청역 3곳 다음에 시청.용인대역).
    그래서 받은 쪽의 마지막 후보까지 이름이 맞고 다음 쪽이 남았을 때만 다음 쪽을 받는다. 마지막 후보가 이름이 다르면
    이름이 맞는 후보는 다 받은 것이다.

    Args:
        fetch: 쪽 번호(0부터)로 자동완성 한 쪽을 받는 함수.
        first: 이미 받은 첫 쪽.
        matches: 이름이 맞는 후보인지.

    Returns:
        tuple[list, bool]: 받은 후보 전체 (사이트 순서), 이름이 맞는 후보가 아직 남았을 수 있는지 (쪽 상한에 닿았거나
            다음 쪽이 있다면서 빈 쪽을 줬을 때).
    """
    items = list(first.items)
    page = first
    pages = 1
    while items and matches(items[-1]) and _has_more(page.total_count, page.has_next_page, len(items)):
        if pages >= MAX_AUTOCOMPLETE_PAGES:
            return items, True
        page = fetch(pages)
        pages += 1
        if not page.items:
            return items, True
        items.extend(page.items)
    return items, False


def _wide_region_unit(code: str | None) -> str:
    """넓은 지역 안내의 단위. 법정동 코드 앞 두 자리 뒤가 모두 0 이면 시·도다.

    주소 검색은 시·도 이름(서울, 전라남도)도 지역 하나로 준다 (서울 bcode 1100000000, 시·군·구 칸 빈 값, 2026-10-10).
    """
    return '시·도' if code and len(code) == 10 and code[2:] == '0' * 8 else '시·군·구'


def _find_legal_division(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, list[str]] | None:
    """동 자동완성으로 법정동을 찾는다. 같은 이름이 여러 곳이면 고르지 않고 후보를 알린다.

    예전에는 첫 번째로 찾고 다른 곳을 `notes` 로 알리는 길도 있었는데, 그 길을 쓰던 `resolve_region_with_notes` 를 뺀 뒤 부르는
    곳이 모두 멈추는 쪽이라 지웠다 (2026-11-12 리뷰).
    이름은 검색어의 끝 단어로 맞춘다 ('수정구 신흥' 은 '신흥'). 이름이 끝 단어(끝말을 붙인 이름 포함)와 같은 곳이 없으면 웹
    검색창처럼 후보를 보여 주고 고르게 한다. 후보가 하나뿐이면 그곳으로 찾고 `[참고]` 로 알린다. 후보가 모두 검색어의
    '○가' 동('부민' → 부민동1가·2가·3가)이면 `_check_ga_dongs` 로 다른 시·구까지 '○가' 동을 모아, 둘 이상이거나 다음 쪽이
    남아 하나뿐인지 모르면 고르지 않고 멈추고, 한 곳뿐이면 그 동을 쓴다 (이미 받은 자동완성을 다시 쓸 수 있으면 다시
    부르지 않는다).
    이름이 맞는 동이 첫 쪽에 하나뿐이어도 다음 쪽이 남았으면 뒤쪽에 같은 이름의 동이 더 있을 수 있다. 이름 전체로 주소 검색
    1회를 더 해 하나뿐인지 확인하고, 확인할 수 없으면 고르지 않고 후보를 알린다 (2026-11-16 결정).
    좌표 없는 후보도 후보로 센다 (웹 검색창에는 후보로 보인다). 고른 동에 좌표가 없으면 다른 후보로 바꾸지 않고 멈춘다.

    Raises:
        RegionAmbiguousError: 같은 이름이 여러 곳일 때 ('신사' → 강남구·은평구·관악구 신사동), 이름이 같은 곳이 첫 쪽에
            하나뿐인데 다음 쪽이 남았고 하나뿐인지 확인할 수 없을 때, 이름이 같은 곳 없이 후보가 여럿일 때, '○가' 로
            나뉜 동의 앞 이름일 때.
        JibsaError: 고른 동에 좌표가 없으면 REGION_NOT_FOUND.
    """
    page = unwrap(
        client.run_request_search_autocomplete_legal_divisions_v1(
            NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=query)
        ),
        '지역 검색',
    )
    # 좌표 없는 후보도 센다. 먼저 빼면 웹에는 후보가 둘인데 하나가 좌표 없을 때 남은 하나를 '하나뿐' 으로 골라 버린다
    items = page.items
    if not items:
        return None
    # 자동완성은 한 쪽에 다섯 곳만 줘서 다음 쪽이 있으면 전체 수(totalCount)로 센다 ('송정' 은 첫 쪽 다섯 곳이 모두
    # 송정동이고 totalCount 14, 2026-10-11). totalCount 는 '중앙동1가' 같은 비슷한 이름도 세어 조금 많을 수 있다
    more = _has_more(page.total_count, page.has_next_page, len(items))
    notes: list[str] = []
    # 이름은 끝 단어로 맞춘다. 검색어 전체('수정구 신흥')로 만들면 비교하는 끝 단어('신흥동')와 늘 달라 이름이 안 맞는다
    words = query.split()
    query_word = words[-1]
    # 동·구 이름을 끝말 없이 줘도('신흥', '해운대') 그 이름의 곳을 고른다. 첫 결과로 고르면 '신흥' 이 인천 신흥동1가가
    # 되고 같은 이름 신흥동 여러 곳(대전 동구·성남 수정구 …)을 알리지 않는다 (2026-10-11)
    names = {query_word, *(query_word + suffix for suffix in DIVISION_NAME_SUFFIXES)}
    named = next((item for item in items if _last_word(item.legal_division_name) in names), None)
    ga_bases = [_ga_dong_base(query_word, _last_word(item.legal_division_name)) for item in items]
    ga_base: str | None = None
    if named is not None:
        best = named
    elif all(base is not None for base in ga_bases):
        best = items[0]
        ga_base = ga_bases[0]
    else:
        # 이름이 다른 후보 중 첫 곳을 고르면 웹에서 사람이 고르는 것을 임의로 고르는 것이다
        _stop_unless_only(query, [normalize_address(item.legal_division_name) for item in items], more, page.total_count)
        best = items[0]
        address = normalize_address(best.legal_division_name)
        notes.append(note('참고', f"'{query}': 동 이름으로 {address}{particle(address, '을/를')} 찾았습니다"))
    if named is not None:
        # 이름이 맞는 곳은 끝말과 상관없이 모두 센다 ('신평' → 부산 신평동·당진 신평면. 웹 검색창은 둘 다 보여 준다).
        # 첫 이름의 끝말('신평동')만 세면 다른 끝말의 곳을 후보로도 알리지 않고 하나뿐이라 고른다
        same = [item for item in items if _last_word(item.legal_division_name) in names]
        if len({_last_word(item.legal_division_name) for item in same}) >= 2:
            # 아래 주소 검색은 이름 전체('신평동') 하나만 물어 다른 끝말의 곳이 후보에서 빠지므로 받은 후보로 멈춘다
            raise RegionAmbiguousError(
                query,
                [normalize_address(item.legal_division_name) for item in same[:MAX_CANDIDATE_NOTES]],
                _candidate_count(len(same), page.total_count, more),
            )
    else:
        same = [item for item in items if _last_word(item.legal_division_name) == _last_word(best.legal_division_name)]
    # 이름이 맞는 동이 첫 쪽에 하나뿐이어도 다음 쪽이 남았으면 뒤쪽에 같은 이름 동이 더 있을 수 있다 (실제 '신흥' 응답에서
    # 성남 신흥동만 빼면 대전 신흥동 하나만 남아 안내 없이 동 경계로 썼다). 하나뿐인지 확인하지 못하면 고르지 않는다 (2026-11-16 결정)
    if len(same) >= 2 or (named is not None and more):
        full_name = _last_word(best.legal_division_name)
        confirmed = False
        if query_word != full_name:
            # 끝말 없는 이름('신흥')은 주소 검색이 못 찾지만 이름 전체('신흥동')로는 같은 이름 동을 모두 준다 (신흥동 14곳.
            # 자동완성은 대전·성남 2곳에 totalCount 12, 신사 2곳 ↔ 신사동 3곳, 2026-10-11). 그래서 이름 전체로 1회 더 물어
            # `search listings 신흥동` 과 같은 후보로 멈춘다
            others, others_total = _search_address(client, ' '.join([*words[:-1], full_name]))
            if others_total > 1:
                raise RegionAmbiguousError(
                    query, [item.full_address for item in others[:MAX_CANDIDATE_NOTES] if item.full_address], others_total,
                )
            # 주소 검색 1곳이 고른 동과 같은 곳일 때만 하나뿐이다. 주소 검색은 자동완성(법정동)에 없는 곳도 bcode 를 비워
            # 섞어 준다 ('신흥동' 14곳 중 부천 오정구·인천 제물포구 등 4곳, 2026-11-16 실측). 그 1곳이 다른 곳이면 고른 동과
            # 합쳐 두 곳인데 하나뿐이라 고르게 된다 (2026-11-16 리뷰). bcode 가 비었으면 같은 곳인지 몰라 확인하지 못한 것이다
            elements = others[0].address_elements if others_total == 1 and others else None
            confirmed = elements is not None and elements.bcode == best.legal_division_number
        if len(same) >= 2:
            raise RegionAmbiguousError(
                query,
                [normalize_address(item.legal_division_name) for item in same[:MAX_CANDIDATE_NOTES]],
                _candidate_count(len(same), page.total_count, more),
            )
        if not confirmed:
            # 검색어가 이미 이름 전체라 위 주소 검색을 건너뛰었거나 주소 검색이 결과를 주지 않아 하나뿐인지 알 수 없다
            raise RegionAmbiguousError(
                query,
                [normalize_address(item.legal_division_name) for item in items[:MAX_CANDIDATE_NOTES]],
                _candidate_count(len(items), page.total_count, more),
            )
    if ga_base is not None and is_dong_code(best.legal_division_number):
        # 주소 검색이 못 찾은 '○가' 동의 앞 이름('부민')은 자동완성이 1가·2가·3가를 모두 주는데 첫 동을 고르면 다른 동이
        # 빠진다 (2026-10-30 실측: 부민 → 부산 서구 부민동1가·2가·3가). `_find_address` 처럼 '○가' 동이 여럿이면 멈춘다.
        # `_check_ga_dongs` 가 앞 이름으로 부르는 자동완성이 방금 받은 쪽과 같으면 다시 부르지 않는다: 검색어가 한 단어이고
        # 앞 이름 그대로면('충정로') 같은 keyword 를 두 번 부르는 것이고, 앞 이름보다 짧아도('부민') 다음 쪽이 없으면 방금 받은
        # 결과가 '부민동' 의 결과를 모두 담는다 (2026-11-16 실측: 둘의 후보가 같았다). 시·구를 붙인 검색어('서구 부민')는
        # keyword 가 달라 다시 부른다
        reuse = page if len(words) == 1 and (query_word == ga_base or not more) else None
        _check_ga_dongs(
            client, query, ga_base, best.legal_division_number, normalize_address(best.legal_division_name), page=reuse,
        )
    # 단위는 GUN·EUP 만 온다. 서울·경기도 같은 시·도는 그 안의 구(GUN)로 오고, 리는 자동완성에 나오지 않는다
    # (검색어 16개, 2026-10-09 확인). 그래서 EUP 가 아니면 시·군·구로 본다.
    if radius_km is not None and best.legal_division_level_type not in (None, 'EUP'):
        notes.append(note(
            '범위',
            f"'{query}': {_wide_region_unit(best.legal_division_number)} 단위의 넓은 지역이라 중심({normalize_address(best.legal_division_name)})에서 "
            f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요',
        ))
    if best.coordinates is None:
        # 후보를 다른 곳으로 바꾸지 않는다 (웹에서 사람이 고르는 것을 임의로 고르는 것이라). `_find_complex` 와 같다
        address = normalize_address(best.legal_division_name)
        raise JibsaError(
            code='REGION_NOT_FOUND',
            message=f"{quoted(query, '은/는')} {address}{particle(address, '을/를')} 찾았지만 네이버가 좌표를 주지 않아 위치로 쓸 수 없습니다",
            hint='번지·도로명 주소로 다시 검색하거나 --lat/--lng 로 찾으세요',
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
) -> tuple[NaverRegion, list[str]] | None:
    """역 자동완성으로 역을 찾는다. 이름이 검색어나 검색어+'역' 과 같은 역을 쓴다.

    이름이 같은 역이 없으면 웹 검색창처럼 후보를 보여 주고 고르게 한다 (2026-11-16 실측: '서울대' → 서울대입구역·
    서울대벤처타운역, '인천공항' → 인천공항1터미널역·2터미널역). 후보가 하나뿐이면 그 역으로 찾고 `[참고]` 로 알린다.
    이름이 같은 역이 여러 곳이어도 고르지 않고 후보를 알린다 (2026-11-17 실측: '시청역' 은 서울·대전·부산 시청역이 따로
    온다. 첫 역을 고르면 웹에서 사람이 고르는 것을 임의로 고르는 것이다). 역 이름·노선이 같은 역이 있어 후보에 좌표를
    붙여 좌표로 다시 찾게 한다. 같은 이름 역이 첫 쪽 끝까지 이어지면 다음 쪽도 받아 센다 (`_collect_matching`).
    좌표 없는 후보도 후보로 센다 (웹 검색창에는 후보로 보인다). 고른 역에 좌표가 없으면 다른 후보로 바꾸지 않고 멈춘다.

    Raises:
        RegionAmbiguousError: 이름이 같은 역이 여럿이거나 남은 쪽에 더 있을 수 있을 때, 이름이 같은 역 없이 후보가 여럿일 때.
        JibsaError: 고른 역에 좌표가 없으면 REGION_NOT_FOUND.
    """
    def fetch(number: int) -> NaverAutocompletePageModel[NaverAutocompleteSubwayStationModel]:
        return unwrap(
            client.run_request_search_autocomplete_subway_stations_v1(
                NaverSearchAutocompleteSubwayStationsV1RequestParameterModel(keyword=query, page=number)
            ),
            '역 검색',
        )

    page = fetch(0)
    items = page.items
    if not items:
        return None
    names = (query, f'{query}역')
    named = next((item for item in items if item.station_name in names), None)
    if named is None:
        _stop_unless_only(
            query,
            [_station_label(item) for item in items],
            _has_more(page.total_count, page.has_next_page, len(items)),
            page.total_count,
            hint=f"후보의 역 이름 그대로 다시 검색하세요 (예: '{items[0].station_name}')",
        )
        best = items[0]
        notes = [note('참고', f"'{query}': 역 이름으로 {_station_label(best)}{particle(best.station_name, '을/를')} 찾았습니다")]
    else:
        best = named
        notes = []
        name = named.station_name
        collected, incomplete = _collect_matching(fetch, page, lambda item: item.station_name == name)
        same = [item for item in collected if item.station_name == name]
        if len(same) >= 2 or incomplete:
            raise RegionAmbiguousError(
                query,
                [_station_candidate(item) for item in same[:MAX_CANDIDATE_NOTES]],
                None if incomplete else len(same),
                hint='역 이름만으로는 고를 수 없어 후보에 붙은 --lat/--lng 로 다시 검색하세요',
            )
    if best.coordinates is None:
        # 후보를 다른 곳으로 바꾸지 않는다 (웹에서 사람이 고르는 것을 임의로 고르는 것이라). `_find_complex` 와 같다
        raise JibsaError(
            code='REGION_NOT_FOUND',
            message=f"{quoted(query, '은/는')} {_station_label(best)}{particle(best.station_name, '을/를')} 찾았지만 네이버가 좌표를 주지 않아 위치로 쓸 수 없습니다",
            hint='역 둘레의 동 이름·주소로 다시 검색하거나 --lat/--lng 로 찾으세요',
        )
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=best.station_name,
        lat=lat,
        lng=lng,
    )
    return region, notes


def _search_complexes(
    client: NaverClient,
    keyword: str,
) -> tuple[list[NaverAutocompleteComplexModel], int | None, bool | None]:
    """단지 이름 자동완성 첫 페이지(10건)와 전체 수(totalCount)·다음 쪽 여부(hasNextPage). 사이트 검색창과 같은 요청·순서다."""
    page = unwrap(
        client.run_request_search_autocomplete_complexes_v1(
            NaverSearchAutocompleteComplexesV1RequestParameterModel(keyword=keyword)
        ),
        '단지 검색',
    )
    return page.items, page.total_count, page.has_next_page


def _complex_label(item: NaverAutocompleteComplexModel) -> str:
    """단지 후보 글 ('래미안 (서울특별시 강남구 개포동, 단지 번호 12345)')."""
    address = normalize_address(item.legal_division_name)
    return f'{item.complex_name} ({address}, 단지 번호 {item.complex_number})' if address else (
        f'{item.complex_name} (단지 번호 {item.complex_number})'
    )


def _has_more(total: int | None, has_next_page: bool | None, received: int) -> bool:
    """자동완성에 받은 쪽 뒤로 후보가 더 남았는지. hasNextPage 거나 전체 수(totalCount)가 받은 수보다 크면 남았다.

    totalCount 가 비어 와도 hasNextPage 로 안다 (웹 검색창의 '더보기' 도 hasNextPage 를 본다).
    """
    return bool(has_next_page) or (total is not None and total > received)


def _candidate_count(found: int, total: int | None, more: bool) -> int | None:
    """REGION_AMBIGUOUS 의 candidate_count. 다음 쪽이 남았으면 전체 수(totalCount), 아니면 찾은 수.

    다음 쪽이 남았는데 전체 수가 비어 오면 모름(None)이다. 찾은 수를 쓰면 받은 첫 쪽이 전부인 것처럼 말한다.
    """
    if not more:
        return found
    return max(total, found) if total is not None else None


def _stop_unless_only(
    query: str,
    labels: list[str],
    more: bool,
    total: int | None,
    *,
    hint: str | None = None,
    shown: int = MAX_CANDIDATE_NOTES,
) -> None:
    """이름이 맞는 후보가 없을 때. 후보가 둘 이상이거나 다음 쪽이 남았으면 고르지 않고 REGION_AMBIGUOUS 로 멈춘다.

    후보가 하나뿐이면 돌아오고, 부르는 쪽이 그 후보로 찾고 `[참고]` 로 알린다 (웹 검색창이 보여 줄 후보 하나 그대로다).

    Args:
        labels: 받은 후보 전체의 후보 글 (사이트 순서).
        shown: 에러 후보에 넣을 수. 단지는 받은 10건을 모두 넣는다.

    Raises:
        RegionAmbiguousError: 후보가 둘 이상이거나 다음 쪽이 남았을 때.
    """
    if len(labels) >= 2 or more:
        raise RegionAmbiguousError(query, labels[:shown], _candidate_count(len(labels), total, more), hint=hint)


def _pick_complex(
    query: str,
    items: list[NaverAutocompleteComplexModel],
    total: int | None,
    has_next_page: bool | None,
    hint: Callable[[NaverAutocompleteComplexModel], str],
) -> tuple[NaverAutocompleteComplexModel, list[str]]:
    """단지 이름 자동완성 후보에서 단지 하나와 안내를 고른다. 고를 수 없으면 후보를 알린다.

    네이버 웹 검색창은 후보 목록을 보여 주고 사람이 고른다 (2026-11-16 웹 대조: '현대' 첫 10건 중 이름이 정확히 '현대' 인
    단지가 5곳, 전체 3,924건). 그래서 이름이 정확히 같은 후보가 하나이거나 후보가 하나뿐일 때만 그 단지로 정하고, 첫 후보를
    임의로 고르지 않는다. 이름이 다른 단지 하나로 정했으면 어느 단지인지 안내한다.
    다만 다음 쪽이 남았으면(hasNextPage 거나 전체 수가 받은 후보 수보다 크면) 웹이 '더보기' 로 다음 쪽(page=1, 2…)을 더
    보여 주는 경우라 뒤쪽에 이름이 같은 단지가 더 있을 수 있다 (2026-11-16 '한양' 실측: 전체 852건, 정확히 '한양' 인 단지가
    첫 쪽(page=0)에 1~2곳(첫 쪽 순서가 요청마다 달랐다), page=1 에 2곳, page=2 에 1곳). 다음 쪽을 더 부르지 않고, 이때는
    정확히 같은 이름이 하나여도 후보가 하나여도 고르지 않는다. totalCount 가 비어 와도 hasNextPage 로 다음 쪽을 안다
    (같은 모듈의 동·역 자동완성도 `_has_more` 로 같게 본다).

    Args:
        query: 사용자가 준 단지 이름.
        items: 자동완성 후보 (사이트 순서).
        total: 자동완성 전체 수 (totalCount). 비어 올 수 있다 (다음 쪽이 남았는데 비면 `candidate_count` 는 null, `_candidate_count`).
        has_next_page: 자동완성의 다음 쪽 여부 (hasNextPage).
        hint: 후보가 여럿일 때 다시 묻는 법을 만드는 함수 (부르는 명령마다 다르다). 예로 들 단지 후보를 받는다.
            정확히 같은 이름의 후보가 있으면 그중 첫 곳, 없으면 첫 후보다 (이름이 다른 단지를 예로 들지 않게).

    Raises:
        RegionAmbiguousError: 다음 쪽이 남았거나, 이름이 정확히 같은 후보가 여럿이거나, 정확히 같은 이름 없이 후보가 여럿일 때.
    """
    exact = [item for item in items if item.complex_name == query]
    has_more = _has_more(total, has_next_page, len(items))
    if not has_more and len(exact) == 1:
        return exact[0], []
    # 후보가 여럿이거나 다음 쪽이 남았으면 여기서 멈춘다 (받은 후보를 모두 알린다). 돌아오면 후보가 하나뿐이다
    _stop_unless_only(
        query,
        [_complex_label(item) for item in items],
        has_more,
        total,
        hint=hint((exact or items)[0]),
        shown=len(items),
    )
    only = items[0]
    return only, [note('참고', f"'{query}': 단지 이름으로 {_complex_label(only)} 단지를 찾았습니다")]


def _find_complex(
    client: NaverClient,
    query: str,
    listing_search: bool,
) -> tuple[NaverRegion, list[str]] | None:
    """단지 이름 자동완성으로 단지를 찾아 그 좌표를 위치로 쓴다 (`_pick_complex`).

    Args:
        listing_search: `search listings` 에서 부르는지. 그때만 단지 안 매물을 단지 번호(`--complex`)로 찾으라고 알린다.

    Raises:
        RegionAmbiguousError: 단지를 하나로 정할 수 없을 때.
        JibsaError: 정한 단지에 좌표가 없으면 REGION_NOT_FOUND (단지는 찾았지만 위치로 쓸 수 없다).
    """
    found, total, has_next_page = _search_complexes(client, query)
    if not found:
        return None

    def ambiguous_hint(item: NaverAutocompleteComplexModel) -> str:
        listings = (
            '단지 안 매물은 후보의 단지 번호로 찾으세요 '
            f'(예: jibsa naver search listings --complex {item.complex_number}). '
        ) if listing_search else ''
        # 후보 글에는 동까지의 주소만 있어(번지·도로명 없음) 그 동 이름으로 찾으면 단지 둘레가 아니라 동 전체가 된다.
        # `complex` 가 주는 번지 주소로 찾으면 그 지점 둘레를 반경으로 찾는다
        return (
            f'{listings}단지 둘레는 jibsa naver complex <후보의 단지 번호> 의 address(번지 주소)로 다시 검색하세요 '
            f'(예: jibsa naver complex {item.complex_number})'
        )

    best, notes = _pick_complex(query, found, total, has_next_page, hint=ambiguous_hint)
    if best.coordinates is None:
        # 단지는 찾았으니 '지역을 찾지 못했습니다' 와 단지 이름으로 다시 검색하라는 힌트(같은 에러가 되풀이된다)를 주지 않는다
        listings = (
            f'단지 안 매물은 단지 번호로 찾고 (jibsa naver search listings --complex {best.complex_number}), '
        ) if listing_search else ''
        raise JibsaError(
            code='REGION_NOT_FOUND',
            message=f"{quoted(query, '은/는')} {_complex_label(best)} 단지로 찾았지만 네이버가 좌표를 주지 않아 위치로 쓸 수 없습니다",
            hint=f'{listings}둘레는 jibsa naver complex {best.complex_number} 의 address(번지 주소)로 다시 검색하거나 --lat/--lng 로 찾으세요',
        )
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=best.complex_name,
        address=normalize_address(best.legal_division_name),
        lat=lat,
        lng=lng,
        legal_division_code=best.legal_division_number,
    )
    return region, notes


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


def _ga_dong_base(name: str, dong: str) -> str | None:
    """찾은 동이 검색어 끝 단어 `name` 의 '○가' 동이면 '○가' 를 뗀 앞 이름 ('성수동'·'성수' → 성수동1가 의 성수동). 아니면 None.

    주소 검색은 '동' 을 뺀 '성수' 에도 '성수동' 처럼 성수동1가 한 곳만 준다 (2026-10-28 실측). 검색어 바로 뒤에 숫자+'가' 가
    올 때만 '○가' 동으로 보면 '성수' 는 사이에 '동' 이 껴 1가만 찾고 안내도 없었다 (2026-10-28 리뷰).
    """
    match = re.fullmatch(r'(.+?)\d+가', dong)
    if match is None or match.group(1) not in (name, f'{name}동'):
        return None
    return match.group(1)


def _check_ga_dongs(
    client: NaverClient,
    query: str,
    base: str,
    code: str,
    address: str | None,
    *,
    page: NaverAutocompletePageModel[NaverAutocompleteLegalDivisionModel] | None = None,
) -> None:
    """'○가' 동의 앞 이름(성수동 → 성수동1가·성수동2가)으로 찾았을 때 '○가' 동이 둘 이상이면 고르지 않고 멈춘다.

    네이버 웹 검색창은 '성수동' 에 법정동 자동완성으로 성수동1가·성수동2가를 따로 보여 주고 고른 동 하나만 연다 (2026-11-16
    웹 대조). 첫 동을 고르거나 여러 동을 합치면 웹에서 볼 수 없는 결과라, 후보를 모두 알려 동 하나를 골라 다시 묻게 한다.
    같은 앞 이름의 '○가' 동은 다른 시·구에도 있다 (충정로1가는 중구, 충정로2가·3가는 서대문구). 그래서 웹 검색창처럼 앞
    이름으로 법정동 자동완성을 1회 불러 모은다. 다음 쪽이 없으면 그것만으로 다 본 것이고 (2026-11-16 실측: '성수동' 2곳·
    '충정로' 3곳·'부민동' 3곳, 다음 쪽 없음), 다음 쪽이 있으면('을지로' 7곳 중 첫 쪽 5곳, '종로' 는 첫 쪽이 종로구·청운동 등이라
    '○가' 동 0곳) 찾은 동의 시·구 하위 지역 목록을 1회 더 불러 합친다. 그래서 요청은 0~2회다 (이미 받은 자동완성 쪽을
    넘기면 다시 부르지 않는다). 검색어에 시·구를 붙였으면 ('서대문구 충정로') 그 시·구의 동만 센다. 같은 동의 '○가' 는
    몇 곳뿐이라(부민동 1가~3가) 자르지 않는다 (다방 `resolve_places` 와 같다). '○가' 동이 한 곳뿐이면 그 동을 그대로 쓴다. 다만 자동완성 다음 쪽이
    남았으면 하위 지역 목록이 덮지 않는 다른 시·구의 '○가' 동이 뒤쪽에 있을 수 있어, 한 곳뿐이어도 고르지 않고 멈춘다.

    Args:
        query: 사용자가 준 검색어 ('성수동', '성동구 성수').
        base: '○가' 를 뗀 앞 이름 (`_ga_dong_base`).
        code: 찾은 '○가' 동의 법정동 코드.
        address: 찾은 '○가' 동의 전체 주소. 하위 지역 목록은 동 이름만 줘('성수동2가') 후보 주소의 시·구를 여기서 붙인다.
        page: 앞 이름(`base`)으로 이미 받은 법정동 자동완성 쪽. 주면 다시 부르지 않고 이 쪽을 쓴다.
            Defaults to None (앞 이름으로 부른다).

    Raises:
        RegionAmbiguousError: '○가' 동이 둘 이상이거나, 한 곳뿐인데 자동완성 다음 쪽이 남았을 때 (candidate_count null).
    """
    pattern = re.compile(rf'{re.escape(base)}(\d+)가')
    found_address = normalize_address(address) or ''
    parent = ' '.join(found_address.split()[:-1])
    # 법정동 코드 → (시·구, '○가' 번호, 동 이름, 전체 주소)
    found: dict[str, tuple[str, int, str, str]] = {}

    def add(number: str, full_address: str) -> None:
        words = full_address.split()
        match = pattern.fullmatch(words[-1]) if words else None
        if match is not None and number not in found:
            found[number] = (' '.join(words[:-1]), int(match.group(1)), words[-1], full_address)

    if page is None:
        page = unwrap(
            client.run_request_search_autocomplete_legal_divisions_v1(
                NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=base)
            ),
            '지역 검색',
        )
    for item in page.items:
        add(item.legal_division_number, normalize_address(item.legal_division_name))
    if found_address:
        add(code, found_address)
    # 다음 쪽이 남았는지는 다른 자동완성 판정과 같게 본다 (hasNextPage 가 비어도 totalCount 가 받은 수보다 크면 남았다)
    more = _has_more(page.total_count, page.has_next_page, len(page.items))
    if more:
        for sub in _sub_regions(client, 'GUN', code[:5] + '00000'):
            add(sub.legal_division_number, f'{parent} {_last_word(sub.legal_division_name or "")}'.strip())
    # 시·구를 붙인 검색어('서대문구 충정로')는 그 시·구에서 찾았으니 붙인 이름이 주소에 없는 다른 시·구의 '○가' 동은 후보가
    # 아니다. 찾은 동과 같은 시·구(코드 앞 다섯 자리)의 동은 늘 센다
    prefix = set((normalize_address(' '.join(query.split()[:-1])) or '').split())
    entries = [
        entry for number, entry in found.items()
        if number[:5] == code[:5] or prefix <= set(entry[0].split())
    ]
    if len(entries) < 2 and not more:
        return
    if len(entries) < 2:
        # 하위 지역 목록은 찾은 동의 시·구만 덮어, 자동완성 다음 쪽에 다른 시·구의 '○가' 동이 있으면 빠진다. 하나뿐인지
        # 알 수 없어 고르지 않는다 (2026-11-17 리뷰. 이름이 맞는 동이 첫 쪽에 하나뿐인데 다음 쪽이 남았을 때와 같다)
        example = ' '.join([*query.split()[:-1], entries[0][2]]) if entries else None
        raise RegionAmbiguousError(
            query,
            [entry[3] for entry in entries],
            None,
            hint=(
                f"다른 시·구에도 '{base}○가' 동이 더 있을 수 있어 고르지 않았습니다. "
                + (f"'{example}' 처럼 " if example else '')
                + '동 이름 전체로 다시 검색하세요'
            ),
        )
    # 시·구는 받은 순서를 지키고 그 안에서 '○가' 번호 순이다
    parents = list(dict.fromkeys(entry[0] for entry in entries))
    entries.sort(key=lambda entry: (parents.index(entry[0]), entry[1]))
    example = ' '.join([*query.split()[:-1], entries[0][2]])
    raise RegionAmbiguousError(
        query,
        [entry[3] for entry in entries],
        len(entries),
        hint=f"'{example}' 처럼 동 하나를 골라 다시 검색하세요",
    )


def _find_address(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, str, list[str]] | None:
    """사이트 검색창의 주소 검색. 번지·도로명이면 그 지점, 법정동이면 그 동, 시·군·구면 넓은 지역이다.

    동 이름 일부('송정')로 찾은 동은 동 이름 전체로 1회 더 물어 같은 이름 동이 여러 곳인지 본다 ('○가' 동은 '성수' →
    성수동처럼 앞 이름으로). '○가' 동의 앞 이름('성수'·'성수동')이면 다른 시·구까지 '○가' 동을 1~2회 더 물어
    (`_check_ga_dongs`) 둘 이상이면 멈춘다.

    Raises:
        RegionAmbiguousError: 같은 이름의 동·주소가 여러 곳일 때 (신사동 3곳, 중앙동 1 은 21곳, 송정 15곳), '○가' 로
            나뉜 동의 앞 이름일 때 (성수동 → 성수동1가·성수동2가, 충정로 → 중구 충정로1가·서대문구 충정로2가·3가).
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
    dong = elements.dongmyun or ''
    ga_base = _ga_dong_base(words[-1], dong) if is_dong_code(code) and not elements.ri else None
    # '○가' 동은 '○가' 를 뗀 앞 이름('성수' → 성수동)이 동 이름 전체다. 끝 단어가 그보다 짧을 때만 다시 묻는다. 번지('신사동
    # 535-1' → '신사동 신사동')나 앞 이름 그대로('성수동')까지 다시 물어 요청만 1회 늘었고 (2026-10-23 리뷰), '성수' 를
    # '성수동1가' 로 다시 물으면 그 한 곳만 와 앞 이름이 여러 곳인지 볼 수 없었다 (2026-10-28 리뷰)
    full_name = ga_base or dong
    if is_dong_code(code) and not elements.ri and dong.startswith(words[-1]) and full_name != words[-1]:
        # 동 이름 일부는 주소 검색이 대표 한 곳만 준다 ('송정' 은 부산 해운대구 송정동 1곳, '송정동' 은 15곳.
        # '역삼'·'역삼동' 은 둘 다 강남구 역삼동 1곳, 2026-10-11). 그래서 동 이름 전체로 다시 물어 여러 곳이면 멈춘다
        same, same_total = _search_address(client, ' '.join([*words[:-1], full_name]))
        if same_total > 1:
            raise RegionAmbiguousError(
                query, [other.full_address for other in same[:MAX_CANDIDATE_NOTES] if other.full_address], same_total,
            )
    if ga_base:
        # 주소 검색은 '성수동' 에 성수동1가 한 곳만 주고 2가가 있다는 것은 알리지 않는다 (2026-10-15 실측)
        # ga_base 는 is_dong_code(code) 일 때만 채운다
        assert code is not None
        _check_ga_dongs(client, query, ga_base, code, item.full_address)
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
            notes.append(note(
                '범위',
                f"'{query}': 리 단위는 경계 검색을 지원하지 않아 중심({full_address})에서 반경 {radius_km:g}km 안만 "
                '검색했습니다' + ('. 리 전체를 보려면 --radius 를 늘리세요 (최대 3km)' if radius_km < 3 else ''),
            ))
    elif elements.dongmyun:
        # 행정동(역삼1동, 관악구 신사동)은 법정동 코드가 비어 있어 동 경계로 찾을 수 없다
        kind, name = '지역', elements.dongmyun
        if radius_km is not None:
            notes.append(note(
                '범위',
                f"'{query}': 행정동이라 동 경계로 찾을 수 없어 중심({full_address})에서 반경 {radius_km:g}km 안만 "
                '검색했습니다. 법정동 이름(예: 역삼1동 → 역삼동)으로 검색하면 동 전체를 찾습니다',
            ))
    else:
        kind, name = '지역', _last_word(full_address)
        if radius_km is not None:
            notes.append(note(
                '범위',
                f"'{query}': {_wide_region_unit(code)} 단위의 넓은 지역이라 중심({full_address})에서 "
                f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요',
            ))
    region = NaverRegion(name=name, address=full_address, lat=item.y, lng=item.x, legal_division_code=code)
    return region, kind, notes


def resolve_search_region(
    client: NaverClient,
    query: str,
    radius_km: float | None = 1.0,
    *,
    # 리뷰 오탐 (2026-11-17): 호출부마다 달라야 할 인자(체크리스트 design-2)가 아니라 꺼진 상태가 정상인 기능 스위치다.
    # `--complex` 는 `search listings` 옵션이라 거기서만 켜고, search complexes·search redevelopment·trend 는 False 가 맞다
    listing_search: bool = False,
) -> tuple[NaverRegion, str, list[str]]:
    """`naver search listings` 등의 검색어를 검색 위치와 그 종류로 바꾼다.

    주소 검색 → 동 → 역 → 단지 순으로 찾고 처음 나온 결과를 쓴다. '역' 으로 끝나면 역을 먼저 찾는다
    (주소 검색이 역 이름을 찾지 못해 요청 1회가 헛돈다). 대개 요청 1회다 (동 이름 일부('송정')면 1회 더. 주소 검색으로 찾은
    '○가' 동('성수동')은 법정동 자동완성 1회에 그 다음 쪽이 있으면 하위 지역 목록 1회 더, 주소 검색이 못 찾아 자동완성으로
    찾은 앞 이름은 '충정로' 면 받은 자동완성을 다시 써 더 들지 않고, '부민' 이면 다음 쪽이 없을 때만 다시 쓰고 남았으면
    '부민동' 자동완성 1회 더, 둘 다 다음 쪽이 있으면 하위 지역 목록 1회 더. 이름이 맞는
    동이 자동완성 첫 쪽에 하나뿐이고 다음 쪽이 있으면 주소 검색 1회 더, 이름이 같은 역이 역 자동완성 첫 쪽 끝까지 이어지면
    다음 쪽 최대 2회 더). 검색어는 앞뒤 공백을 뗀다. 각 종류 안에서 이름이 맞는 곳이
    없거나 같은 이름이 여럿이면 고르지 않고 후보를 알린다 (후보가 하나뿐이면 그곳으로 찾고 `[참고]`).
    `radius_km` 는 안내에만 쓰고, 반경으로 찾지 않는 호출부(trend)는 None 을 넘겨 '반경 안만 검색했습니다' 안내를
    받지 않는다. 반경 검색이어도 '○가' 동의 앞 이름이면 멈춘다 (중심으로 쓸 동을 임의로 고르는 것이라).

    Args:
        listing_search: `search listings` 에서 부르는지. 단지 이름 후보가 여럿이거나 좌표가 없을 때 단지 안 매물을 단지
            번호(`--complex`)로 찾으라는 힌트를 이때만 붙인다 (다른 명령에는 다음 할 일이 아니다).

    Returns:
        tuple[NaverRegion, str, list[str]]: 위치, 종류('주소', '동', '역', '단지', '지역'), 안내.
            '동' 이면 법정동 코드가 있어 동 전체를 검색할 수 있다.

    Raises:
        RegionAmbiguousError: 같은 이름의 동·주소·역·단지가 여러 곳이거나, 이름이 맞는 동·역 없이 후보가 여럿이거나,
            이름이 맞는 동이 자동완성 첫 쪽에 하나뿐인데 다음 쪽이 남았고 하나뿐인지 확인할 수 없거나,
            '○가' 로 나뉜 동(성수동1가·성수동2가)의 앞 이름일 때.
        RegionNotFoundError: 넷 다 결과가 없을 때.
        JibsaError: 동·역·단지 이름으로 정한 곳에 좌표가 없으면 REGION_NOT_FOUND (그곳을 찾았다고 알린다). 검색어가
            공백뿐이면 요청 없이 INVALID_ARGUMENT.
    """
    def legal_division(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_legal_division(client, query, radius_km)
        if found is None:
            return None
        region, notes = found
        code = region.legal_division_code
        if code is None or not is_dong_code(code):
            return region, '지역', notes
        return region, '동', notes

    def station(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_subway_station(client, query)
        return None if found is None else (found[0], '역', found[1])

    def complex_(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_complex(client, query, listing_search)
        return None if found is None else (found[0], '단지', found[1])

    # 웹 검색창은 앞뒤 공백을 떼고 보낸다 (번들 검색창 `e.trim()`). 떼지 않으면 '파크리오 ' 가 이름이 정확히 같은 단지를
    # 못 맞춰 후보 3곳으로 멈추고, 역 이름('강남역 ')도 이름 비교와 '역' 끝 검사에서 어긋난다 (2026-11-17 리뷰)
    query = query.strip()
    if not query:
        # 공백뿐인 검색어는 네 검색을 헛돌고(요청 4회) 끝 단어도 없다 (`_find_legal_division` 의 `words[-1]`)
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='검색어가 비었습니다',
            hint='동·역·주소·단지 이름을 주거나 --lat/--lng 로 좌표를 주세요',
        )
    # 부르는 곳이 같게 (client, query, radius_km) 를 넘기므로 역·단지도 radius_km 를 받되 쓰지 않는다
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
    """단지 이름을 단지 번호로 바꾼다. 이름이 똑같은 단지가 하나이거나 후보가 하나뿐일 때만 정한다 (`_pick_complex`).
    다음 쪽 후보가 남았으면(hasNextPage 거나 전체 수가 받은 수보다 크면) 그때도 정하지 않는다.

    Returns:
        tuple[int, bool | None, list[str]]: 단지 번호, 빌라 단지인지 (`complex_is_villa`), 안내.

    Raises:
        JibsaError: 단지를 찾지 못하면 NOT_FOUND.
        RegionAmbiguousError: 후보가 여럿이라 정할 수 없을 때. 후보에 단지 번호를 붙여 번호로 다시 묻게 한다.
    """
    items, total, has_next_page = _search_complexes(client, name)
    if not items:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"'{name}' 에 해당하는 네이버 단지를 찾지 못했습니다",
            # 이름을 줄이라고 하면 흔한 이름('래미안' 303곳)이 되어 후보가 첫 쪽 10건을 넘어 고르지 않는다 (`_pick_complex`)
            hint='단지 이름의 오타·띄어쓰기를 고치거나 단지 번호(fin.land.naver.com/complexes/{번호})로 다시 조회하세요. '
            '흔한 이름(예: 래미안)만 주면 후보가 많아 고르지 않습니다',
        )
    best, notes = _pick_complex(
        name,
        items,
        total,
        has_next_page,
        # 단지 이름을 받는 명령(complex·market-price·school·search listings --complex)이 함께 써서 예시에 명령을 적지 않는다
        hint=lambda example: f'단지 이름 대신 후보의 단지 번호를 주세요 (예: {example.complex_number})',
    )
    return best.complex_number, complex_is_villa(best.type), notes


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
    # `SIDO_OFFICIAL_NAMES` 에서는 옛 광주광역시지만 한 단어로 오면 경기도 광주시로 찾는다 (`CITY_NAMES_NOT_SIDO`). 시·도를
    # 붙인 '광주시 광산구' 는 경기도 광주시에 구가 없어 전남광주통합특별시로 본다
    province = None if query in CITY_NAMES_NOT_SIDO else _find_province(provinces, query)
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
    def fetch(number: int) -> NaverAutocompletePageModel[NaverAutocompleteLegalDivisionModel]:
        return unwrap(
            client.run_request_search_autocomplete_legal_divisions_v1(
                NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=keyword, page=number)
            ),
            '지역 검색',
        )

    def is_exact(item: NaverAutocompleteLegalDivisionModel) -> bool:
        return item.legal_division_name == keyword or item.legal_division_name.endswith(f' {keyword}')

    # 자동완성은 한 쪽에 다섯 곳만 줘서 첫 쪽이 모두 이름이 맞으면 같은 이름이 다음 쪽에 더 있을 수 있다 ('중구' 는 첫 쪽
    # 5곳이 모두 중구, 2026-11-17). 첫 쪽 수를 전체로 말하지 않게 이름이 맞는 곳이 끝날 때까지 다음 쪽을 받는다
    items, incomplete = _collect_matching(fetch, fetch(0), is_exact)
    exact = [item for item in items if is_exact(item)]
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
    same = [
        item.legal_division_name or item.legal_division_number for item in exact
        if item.legal_division_level_type == best.legal_division_level_type
    ]
    if len(same) > 1 or incomplete:
        # 첫 곳으로 고르면 다른 곳의 동 목록이 나온다. search listings 처럼 후보를 알리고 멈춘다 (2026-10-15).
        # 쪽 상한에 닿아 다 받지 못했으면 하나뿐이어도 고르지 않고 수는 모름이다
        candidates = [normalize_address(name) or name for name in same[:MAX_CANDIDATE_NOTES]]
        raise RegionAmbiguousError(
            query, candidates, None if incomplete else len(same),
            hint=f"시·도 이름을 붙여 다시 주세요 (예: '{candidates[0]}')",
        )
    notes = []
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
