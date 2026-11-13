"""지역·역·단지 이름과 좌표 해석, 시·도·시·군·구 목록 (regions, 모든 검색의 지역 해석)."""

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
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
    Any,
    Literal,
)


def _lat_lng(coordinates: NaverCoordinatesModel | None) -> tuple[float, float]:
    """자동완성 후보의 (위도, 경도). 좌표 없는 후보는 미리 빼고 부른다."""
    assert coordinates is not None
    return coordinates.y_coordinate, coordinates.x_coordinate


# 같은 이름·비슷한 이름 후보를 알릴 때 보여 줄 후보 수
MAX_CANDIDATES_SHOWN: int = 5


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


def _ambiguous(
    query: str,
    candidates: list[Any],
    count: int | None,
    hint: str,
    message: str | None = None,
) -> JibsaError:
    """같은 이름 후보가 여럿(일 수 있어)이라 고르지 않고 멈추는 에러. 코드와 `details` 키는 `RegionAmbiguousError` 와 같다.

    웹 검색창도 같은 이름 후보를 목록으로만 보여 주고 사용자가 고른다 (2026-11-13 웹 대조). `candidates` 는 받은 후보
    전부이고 앞 `MAX_CANDIDATES_SHOWN` 곳만 싣는다. `count` 가 None 이면 받은 후보가 잘려 전체 수를 모른다 (모름 → null).
    후보가 한 곳인데 `count` 가 None 이면 받은 결과 뒤쪽에 같은 이름이 더 있을 수 있어 그 한 곳으로 정하지 않은 경우다
    (단지 '삼익' 은 자동완성 첫 쪽에 수서동 한 곳뿐이고 다음 쪽에 여의도·이촌 등 4곳이 더 있다, 2026-11-13 실측).
    `message` 를 주면 기본 문구 대신 쓴다.
    """
    if message is None and count is None and len(candidates) == 1:
        message = (
            f"{quoted(query, '과/와')} 이름이 같은 곳을 1곳 찾았지만 받은 결과가 잘려 같은 이름이 더 있을 수 있어 "
            '정하지 않았습니다'
        )
    elif message is None and count is None:
        message = f"'{query}' 에 해당하는 곳이 {len(candidates)}곳 이상입니다 (후보를 다 받지 못해 전체 수를 모릅니다)"
    elif message is None:
        message = f"'{query}' 에 해당하는 곳이 {count}곳입니다"
    return JibsaError(
        code='REGION_AMBIGUOUS',
        message=message,
        hint=hint,
        details={'candidates': candidates[:MAX_CANDIDATES_SHOWN], 'candidate_count': count},
    )


def _station_candidate(station: NaverAutocompleteSubwayStationModel) -> dict[str, Any]:
    """역 후보 (이름·노선·좌표). 역 자동완성에는 시·구가 없어(역 이름·노선·좌표만, 2026-11-13) 좌표로 다시 찾게 한다.

    받은 좌표를 그대로 싣는다 (':g' 는 유효숫자 6자리라 경도가 소수 셋째 자리로 잘린다).
    """
    lat, lng = _lat_lng(station.coordinates)
    return {'name': station.station_name, 'lines': [line.name for line in station.line_infos], 'lat': lat, 'lng': lng}


def _wide_region_unit(code: str | None) -> str:
    """넓은 지역 안내의 단위. 법정동 코드 앞 두 자리 뒤가 모두 0 이면 시·도다.

    주소 검색은 시·도 이름(서울, 전라남도)도 지역 하나로 준다 (서울 bcode 1100000000, 시·군·구 칸 빈 값, 2026-10-10).
    """
    return '시·도' if code and len(code) == 10 and code[2:] == '0' * 8 else '시·군·구'


def _autocomplete_legal_divisions(
    client: NaverClient,
    keyword: str,
) -> NaverAutocompletePageModel[NaverAutocompleteLegalDivisionModel]:
    """사이트 검색창의 지역 자동완성 첫 페이지 (다섯 곳)."""
    return unwrap(
        client.run_request_search_autocomplete_legal_divisions_v1(
            NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(keyword=keyword)
        ),
        '지역 검색',
    )


def _ga_dong_base(name: str, dong: str) -> str | None:
    """`dong` 이 검색어 끝 단어 `name` 의 '○가' 동이면 '○가' 를 뗀 앞 이름 ('성수동'·'성수' → 성수동1가 의 성수동). 아니면 None.

    주소 검색은 '동' 을 뺀 '성수' 에도 '성수동' 처럼 성수동1가 한 곳만 준다 (2026-10-28 실측). 검색어 바로 뒤에 숫자+'가' 가
    올 때만 '○가' 동으로 보면 '성수' 는 사이에 '동' 이 껴 1가만 찾고 안내도 없었다 (2026-10-28 리뷰).
    """
    match = re.fullmatch(r'(.+?)\d+가', dong)
    if match is None or match.group(1) not in (name, f'{name}동'):
        return None
    return match.group(1)


def _ga_dongs(
    items: list[NaverAutocompleteLegalDivisionModel],
    name: str,
) -> list[NaverAutocompleteLegalDivisionModel]:
    """자동완성 후보 중 `name`('성수'·'성수동')의 '○가' 동 (성수동1가·성수동2가)."""
    return [item for item in items if _ga_dong_base(name, _last_word(item.legal_division_name)) is not None]


def _ga_dong_ambiguous(query: str, dongs: list[NaverAutocompleteLegalDivisionModel], more: bool) -> JibsaError:
    """'○가' 로 나뉜 동(성수동 → 성수동1가·성수동2가)을 고르지 않고 후보로 주는 에러.

    동 매물 목록(legalDivisionArticleList)은 법정동 코드를 하나만 받고(둘이면 400, 2026-10-15 실측) 웹에도 두 동을 한 목록으로
    보는 화면이 없다. 웹 검색창은 '성수동' 에 성수동1가·성수동2가를 지역 후보로 따로 보여 사용자가 고른다 (2026-11-13 웹 대조).
    예전에는 동마다 `--limit` 을 나눠 찾아 합쳤다. `more` 는 자동완성에 다음 페이지가 있는지다 (있으면 전체 수를 모른다).
    """
    candidates = [normalize_address(item.legal_division_name) or item.legal_division_name for item in dongs]
    return _ambiguous(
        query, candidates, None if more else len(candidates),
        f"'○가' 로 나뉜 동은 하나씩 찾습니다. 찾을 동을 골라 그 주소로 다시 주세요 (예: '{candidates[0]}')",
    )


def _legal_division_label(item: NaverAutocompleteLegalDivisionModel) -> str:
    """동 자동완성 후보의 정식 주소 ('서울시 강남구 역삼동' → 서울특별시 강남구 역삼동)."""
    return normalize_address(item.legal_division_name) or item.legal_division_name


def _find_legal_division(
    client: NaverClient,
    query: str,
    radius_km: float | None,
    truncated: list[str],
) -> tuple[NaverRegion, list[str]] | None:
    """동 자동완성으로 법정동을 찾는다. 이름이 검색어와 같은 곳만 쓰고, 같은 이름이 여러 곳이면 고르지 않고 멈춘다.

    이름이 같은 곳이 없으면 '○가' 동('부민' → 부민동1가·2가·3가)을 후보로 멈추고, 그것도 없으면 None 이다 (예전에는 첫 후보를
    골랐다). 자동완성은 첫 쪽(다섯 곳)만 받아, 다음 쪽이 있으면 이름이 같은 곳이 한 곳뿐이어도 정하지 않고 멈춘다 (뒤쪽에 같은
    이름이 더 있을 수 있다). 다음 쪽이 있는데 이름이 같은 곳이 없으면 `truncated` 에 '동' 을 더하고 None 이다.

    Raises:
        JibsaError: 같은 이름이 여러 곳이거나 다음 쪽이 있어 더 있을 수 있을 때 REGION_AMBIGUOUS ('신사' → 강남구·은평구
            신사동, '○가' 로 나뉜 동, 같은 이름을 동 이름 전체로 다시 물은 주소 결과(`_unique_address`)).
    """
    page = _autocomplete_legal_divisions(client, query)
    more = bool(page.has_next_page)
    items = [item for item in page.items if item.coordinates is not None]
    if not items:
        return None
    words = query.split()
    # 동·구 이름을 끝말 없이 줘도('신흥', '해운대') 그 이름의 곳을 찾는다. 첫 결과로 고르면 '신흥' 이 인천 신흥동1가가
    # 되고 같은 이름 신흥동 여러 곳(대전 동구·성남 수정구 …)을 알리지 않는다 (2026-10-11)
    # 리뷰 오탐 (2026-11-13): 이 매칭은 주소 검색이 못 찾은 이름만 탄다. '강남'·'해운대' 는 주소 검색이 먼저 정한다
    # (강남 → 강남구·진주 강남동 2곳은 주소 검색 결과)
    names = {words[-1], *(words[-1] + suffix for suffix in DIVISION_NAME_SUFFIXES)}
    same = [item for item in items if _last_word(item.legal_division_name) in names]
    if not same:
        # 주소 검색이 못 찾은 '○가' 동의 앞 이름('부민')은 자동완성이 1가·2가·3가를 모두 준다 (2026-10-30 실측: 부민 → 부산 서구
        # 부민동1가·2가·3가). 한 곳만 있고 다음 쪽이 없으면 그곳이다
        same = _ga_dongs(items, words[-1])
        if len(same) > 1:
            raise _ga_dong_ambiguous(query, same, more)
        if not same:
            if more:
                truncated.append('동')
            return None
        if more:
            label = _legal_division_label(same[0])
            raise _ambiguous(
                query, [label], None,
                "검색 결과가 더 있어 '○가' 로 나뉜 동이 더 있을 수 있습니다. 찾을 동의 주소로 다시 주세요 "
                f"(예: '{label}')",
            )
    if len(same) > 1:
        full_names = {_last_word(item.legal_division_name) for item in same}
        full_name = next(iter(full_names))
        if len(full_names) == 1 and words[-1] != full_name:
            # 끝말 없는 이름('신흥')은 주소 검색이 못 찾지만 이름 전체('신흥동')로는 같은 이름 동을 모두 준다 (신흥동 14곳.
            # 자동완성은 대전·성남 2곳에 totalCount 12, 신사 2곳 ↔ 신사동 3곳, 2026-10-11). 그래서 이름 전체로 1회 더 물어
            # `search listings 신흥동` 과 같은 후보로 멈춘다
            others, others_total = _search_address(client, ' '.join([*words[:-1], full_name]))
            if others_total > 1:
                _unique_address(query, others, others_total)
        # 자동완성은 한 쪽에 다섯 곳만 줘서 다음 쪽이 있으면 전체 수를 모른다 (null). totalCount 는 '중앙동1가' 같은 비슷한
        # 이름도 세어 같은 이름의 수가 아니다 ('송정' 은 첫 쪽 다섯 곳이 모두 송정동이고 totalCount 14, 2026-10-11)
        candidates = [_legal_division_label(item) for item in same]
        raise _ambiguous(
            query, candidates, None if more else len(candidates),
            f'시·구를 붙여 정확한 주소로 다시 검색하세요 (예: {candidates[0]})',
        )
    if more:
        label = _legal_division_label(same[0])
        raise _ambiguous(
            query, [label], None,
            f'검색 결과가 더 있어 이름이 같은 곳이 더 있을 수 있습니다. 시·구를 붙여 정확한 주소로 다시 주세요 (예: {label})',
        )
    best = same[0]
    notes: list[str] = []
    # 단위는 GUN·EUP 만 온다. 서울·경기도 같은 시·도는 그 안의 구(GUN)로 오고, 리는 자동완성에 나오지 않는다
    # (검색어 16개, 2026-10-09 확인). 그래서 EUP 가 아니면 시·군·구로 본다.
    if radius_km is not None and best.legal_division_level_type not in (None, 'EUP'):
        notes.append(note(
            '범위',
            f"'{query}': {_wide_region_unit(best.legal_division_number)} 단위의 넓은 지역이라 중심({normalize_address(best.legal_division_name)})에서 "
            f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요',
        ))
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
    similar: list[dict[str, Any]],
    truncated: list[str],
) -> tuple[NaverRegion, list[str]] | None:
    """역 자동완성으로 이름이 검색어(또는 검색어+'역')와 같은 역을 찾는다.

    이름이 같은 역이 없으면 None 이고 `similar` 에 후보를 더한다 (다음 쪽이 있으면 `truncated` 에 '역' 도 더한다).
    자동완성은 첫 쪽만 받아, 다음 쪽이 있으면 이름이 같은 역이 한 곳뿐이어도 정하지 않는다 (뒤쪽에 더 있을 수 있다).

    Raises:
        JibsaError: 이름이 같은 역이 여러 곳이거나 다음 쪽이 있어 더 있을 수 있을 때 REGION_AMBIGUOUS ('신흥역' → 8호선 성남·
            대전 1호선, 2026-11-13 웹 대조).
    """
    page = unwrap(
        client.run_request_search_autocomplete_subway_stations_v1(
            NaverSearchAutocompleteSubwayStationsV1RequestParameterModel(keyword=query)
        ),
        '역 검색',
    )
    more = bool(page.has_next_page)
    items = [item for item in page.items if item.coordinates is not None]
    same = [item for item in items if item.station_name in (query, f'{query}역')]
    if len(same) > 1 or (same and more):
        # 역 자동완성에는 시·구가 없어 이름으로는 가를 수 없다. 좌표로 다시 찾게 한다
        candidates = [_station_candidate(item) for item in same]
        first = candidates[0]
        retry = f"lat·lng 를 --lat/--lng 로 주세요 (예: --lat {first['lat']} --lng {first['lng']})"
        hint = (
            '이름이 같은 역이 여러 곳입니다 (역 검색은 시·구를 주지 않아 노선·좌표로만 가릅니다. 대전 1호선도 1호선으로 옵니다). '
            f'고른 역의 {retry}'
        ) if len(same) > 1 else (
            '역 검색 결과가 더 있어 이름이 같은 역이 더 있을 수 있습니다 (역 검색은 시·구를 주지 않습니다). '
            f'노선·좌표가 맞으면 그 {retry}'
        )
        raise _ambiguous(query, candidates, None if more else len(candidates), hint)
    if not same:
        similar += [_station_candidate(item) for item in items]
        if more:
            truncated.append('역')
        return None
    best = same[0]
    lat, lng = _lat_lng(best.coordinates)
    return NaverRegion(name=best.station_name, lat=lat, lng=lng), []


def search_complexes(client: NaverClient, keyword: str) -> NaverAutocompletePageModel[NaverAutocompleteComplexModel]:
    """단지 이름 자동완성 첫 페이지. 사이트 검색창과 같은 순서다."""
    return unwrap(
        client.run_request_search_autocomplete_complexes_v1(
            NaverSearchAutocompleteComplexesV1RequestParameterModel(keyword=keyword)
        ),
        '단지 검색',
    )


def _complex_key(name: str) -> str:
    """단지 이름 비교 키. 띄어쓰기·영문 대소문자만 무시한다 ('역삼 IPARK' = '역삼IPARK')."""
    return ''.join(name.split()).casefold()


def _complex_candidate(item: NaverAutocompleteComplexModel, *, coordinates: bool) -> dict[str, Any]:
    """단지 후보 (이름·법정동·단지 번호). 위치로 찾는 명령이면 `--lat/--lng` 로 다시 찾게 좌표도 싣는다."""
    candidate: dict[str, Any] = {
        'name': item.complex_name,
        'legal_division': normalize_address(item.legal_division_name),
        'complex_number': item.complex_number,
    }
    if coordinates and item.coordinates is not None:
        candidate['lat'], candidate['lng'] = _lat_lng(item.coordinates)
    return candidate


def _same_name_complex(
    query: str,
    page: NaverAutocompletePageModel[NaverAutocompleteComplexModel],
    *,
    coordinates: bool,
) -> NaverAutocompleteComplexModel | None:
    """자동완성 첫 페이지에서 이름이 검색어와 똑같은 단지 하나. 없으면 None (첫 후보를 고르지 않는다).

    자동완성은 첫 쪽(10곳)만 받고 똑같은 이름을 앞에 모아 주지 않는다 ('한신', 2026-11-13 실측). 그래서 다음 쪽이 있으면
    똑같은 이름이 한 곳뿐이어도 정하지 않는다 ('삼익' 은 첫 쪽에 수서동 한 곳, 다음 쪽에 여의도·이촌 등 4곳). 흔한 구체
    이름(잠실엘스·래미안대치팰리스·헬리오시티)은 다음 쪽이 없어 그대로 정한다.

    Raises:
        JibsaError: 이름이 똑같은 단지가 여러 곳이거나 다음 쪽이 있어 더 있을 수 있으면 REGION_AMBIGUOUS ('현대' → 보령·
            용인·관악, 2026-11-13 웹 대조).
    """
    more = bool(page.has_next_page)
    items = [item for item in page.items if not coordinates or item.coordinates is not None]
    same = [item for item in items if _complex_key(item.complex_name) == _complex_key(query)]
    if not same or (len(same) == 1 and not more):
        return same[0] if same else None
    candidates = [_complex_candidate(item, coordinates=coordinates) for item in same]
    first = candidates[0]
    retry = (
        f"lat·lng 를 --lat/--lng 로 주세요 (예: --lat {first['lat']} --lng {first['lng']})"
        if coordinates else f"complex_number(단지 번호)로 다시 부르세요 (예: {first['complex_number']})"
    )
    hint = (
        f'이름이 같은 단지가 여러 곳입니다. legal_division 으로 고른 단지의 {retry}' if len(same) > 1
        else f'단지 검색 결과가 더 있어 이름이 같은 단지가 더 있을 수 있습니다. legal_division 이 맞으면 그 단지의 {retry}'
    )
    raise _ambiguous(query, candidates, None if more else len(candidates), hint)


def _find_complex(
    client: NaverClient,
    query: str,
    similar: list[dict[str, Any]],
    truncated: list[str],
) -> tuple[NaverRegion, list[str]] | None:
    """이름이 검색어와 똑같은 단지를 찾는다 (`_same_name_complex`).

    없으면 None 이고 `similar` 에 후보를 더한다 (다음 쪽이 있으면 `truncated` 에 '단지' 도 더한다).
    """
    page = search_complexes(client, query)
    best = _same_name_complex(query, page, coordinates=True)
    if best is None:
        similar += [_complex_candidate(item, coordinates=True) for item in page.items if item.coordinates is not None]
        if page.has_next_page:
            truncated.append('단지')
        return None
    lat, lng = _lat_lng(best.coordinates)
    region = NaverRegion(
        name=best.complex_name,
        address=normalize_address(best.legal_division_name),
        lat=lat,
        lng=lng,
        legal_division_code=best.legal_division_number,
    )
    return region, []


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


def _unique_address(query: str, items: list[NaverAddressModel], total: int) -> NaverAddressModel:
    """주소 검색 결과에서 검색 위치 하나. 여러 곳이면 고르지 않고 멈춘다.

    후보는 법정동 코드(bcode)가 있는 결과만이다. 웹 검색창의 지역 후보가 법정동만이라 ('신사동' → 은평구·강남구, 2026-11-13
    웹 대조) 행정동 결과(관악구 신사동, hcode 만 있음)는 뺀다. 법정동이 한 곳만 남으면 그곳이다. 법정동 결과가 없으면(행정동만
    여러 곳) 고를 수 없어 그 행정동들을 후보로 준다. 목록은 앞 10곳만 와서 뒤에 법정동이 더 있을 수 있으면 전체 수를 모르고,
    앞 10곳에 법정동이 한 곳뿐이어도 정하지 않는다 (2026-11-13 사용자 결정: 그 한 곳으로 정하지 않고 멈춘다).

    Raises:
        JibsaError: 법정동(없으면 행정동)이 여러 곳이거나 잘린 목록이라 더 있을 수 있을 때 REGION_AMBIGUOUS (신사동 2곳,
            중앙동 1 은 21곳, 송정 15곳).
    """
    if total <= 1:
        return items[0]
    complete = total == len(items)
    legal = [item for item in items if item.address_elements is not None and item.address_elements.bcode]
    if len(legal) == 1 and complete:
        return legal[0]
    pool = legal or items
    candidates = [item.full_address for item in pool if item.full_address]
    count = len(pool) if complete else None
    example = candidates[0] if candidates else '서울특별시 강남구 역삼동'
    hint = (
        f'같은 이름이 더 있을 수 있으니 시·구를 붙여 정확한 주소로 다시 주세요 (예: {example})'
        if count is None and len(candidates) == 1
        else f'시·구를 붙여 정확한 주소로 다시 검색하세요 (예: {example})'
    )
    raise _ambiguous(query, candidates, count, hint)


def _related_legal_dongs(item: NaverAddressModel) -> list[str]:
    """행정동 주소 결과의 관련 법정동 이름 (역삼1동 → 역삼동). 웹 검색창은 이 값을 그리지 않고 `[범위]` 안내에만 쓴다.

    응답 모델에 없는 키라 원본(`relatedRegionAddressList`, [{'address': '역삼동', 'linkQuery': '서울특별시 강남구 역삼동'}])에서
    읽는다 (2026-11-13 캡처). 모양이 다르면 빈 목록이다.
    """
    related = (item.model_extra or {}).get('relatedRegionAddressList')
    if not isinstance(related, list):
        return []
    return [entry['address'] for entry in related if isinstance(entry, dict) and isinstance(entry.get('address'), str)]


def _find_address(
    client: NaverClient,
    query: str,
    radius_km: float | None,
) -> tuple[NaverRegion, str, list[str]] | None:
    """사이트 검색창의 주소 검색. 번지·도로명이면 그 지점, 법정동이면 그 동, 시·군·구면 넓은 지역이다.

    동 이름 일부('송정')로 찾은 동은 동 이름 전체로 1회 더 물어 같은 이름 동이 여러 곳인지 본다. '○가' 동('성수동'·'성수' →
    성수동1가)이면 주소 결과의 시·군·구와 앞 이름으로 동 자동완성에 1회 더 물어 '○가' 동들을 후보로 멈춘다. '○가' 동을 한 곳
    이하로 받아도 1가로 정하지 않고 멈춘다. '성수동1가' 처럼 '○가' 까지 주면 그 동이다.

    Raises:
        JibsaError: 같은 이름의 동·주소가 여러 곳이거나 잘린 목록이라 더 있을 수 있을 때, '○가' 로 나뉜 동일 때
            REGION_AMBIGUOUS (`_unique_address`, `_ga_dong_ambiguous`).
    """
    items, total = _search_address(client, query)
    if not items:
        return None
    item = _unique_address(query, items, total)
    elements = item.address_elements or NaverAddressElementsModel()
    code = elements.bcode or None
    words = query.split()
    dong = elements.dongmyun or ''
    ga_base = _ga_dong_base(words[-1], dong) if is_dong_code(code) and not elements.ri else None
    if ga_base is not None:
        # 주소 검색은 '성수동'·'성수' 에 성수동1가 한 곳만 주고 2가가 있다는 것은 알리지 않는다 (2026-10-15 실측). 앞 이름을
        # 자동완성에 물으면 성수동1가·성수동2가를 모두 준다 (2026-11-13 캡처). 사용자 단어 대신 주소 결과의 시·군·구로 묻는다.
        # 자동완성은 정식 시·도 이름('서울특별시 성동구 성수동')을 받지 않아 빈 목록이고 1가로 조용히 정했다 (2026-11-13
        # 실측, 주소 결과의 sigugun 은 '성동구')
        page = _autocomplete_legal_divisions(client, ' '.join(filter(None, [elements.sigugun, ga_base])))
        dongs = _ga_dongs([dong_item for dong_item in page.items if dong_item.coordinates is not None], ga_base)
        if len(dongs) > 1:
            raise _ga_dong_ambiguous(query, dongs, bool(page.has_next_page))
        # 그래도 '○가' 동을 한 곳 이하로 받으면 다른 '○가' 동이 있는지 알 수 없어 1가로 정하지 않는다
        candidates = [_legal_division_label(dong_item) for dong_item in dongs] or [item.full_address or query]
        raise _ambiguous(
            query, candidates, None,
            f"'○가' 로 나뉜 동은 하나씩 찾습니다. 찾을 동의 주소로 다시 주세요 (예: '{candidates[0]}')",
            message=(
                f"{quoted(query, '은/는')} '○가' 로 나뉜 동인데 '○가' 동을 다 찾지 못해 "
                f'{candidates[0]} 로 정하지 않았습니다'
            ),
        )
    elif is_dong_code(code) and not elements.ri and dong.startswith(words[-1]) and dong != words[-1]:
        # 동 이름 일부는 주소 검색이 대표 한 곳만 준다 ('송정' 은 부산 해운대구 송정동 1곳, '송정동' 은 15곳.
        # '역삼'·'역삼동' 은 둘 다 강남구 역삼동 1곳, 2026-10-11). 그래서 동 이름 전체로 다시 물어 여러 곳이면 멈춘다.
        # 번지('신사동 535-1' → '신사동 신사동')나 이름 그대로('역삼동')는 다시 묻지 않는다 (2026-10-23 리뷰)
        same, same_total = _search_address(client, ' '.join([*words[:-1], dong]))
        if same_total > 1:
            _unique_address(query, same, same_total)
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
        # 행정동(역삼1동, 관악구 신사동)은 법정동 코드가 비어 있어 동 경계로 찾을 수 없다. 웹 검색창은 번지 없는 주소 결과를
        # 숨기고(`!!addressElements.jibun`) 지역 후보에도 행정동이 없다. 관련 법정동은 웹이 그리지 않는 응답의
        # `relatedRegionAddressList` 다 (2026-11-13 웹 대조: 역삼1동 → 단지 섹션만)
        kind, name = '지역', elements.dongmyun
        if radius_km is not None:
            related = _related_legal_dongs(item)
            example = (
                f"관련 법정동: {', '.join(related)}. 그 이름으로 검색하면 동 전체를 찾습니다" if related
                else '법정동 이름(예: 역삼1동 → 역삼동)으로 검색하면 동 전체를 찾습니다'
            )
            notes.append(note(
                '범위',
                f"'{query}': 행정동이라 동 경계로 찾을 수 없어 중심({full_address})에서 반경 {radius_km:g}km 안만 "
                f'검색했습니다. {example}',
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
) -> tuple[NaverRegion, str, list[str]]:
    """`naver search listings` 의 검색어를 검색 위치와 그 종류로 바꾼다.

    주소 검색 → 동 → 역 → 단지 순으로 찾고 처음 나온 결과를 쓴다. '역' 으로 끝나면 역을 먼저 찾는다
    (주소 검색이 역 이름을 찾지 못해 요청 1회가 헛돈다). 대개 요청 1회다 (동 이름 일부('송정')·'○가' 동이면 1회 더).
    동·역·단지는 이름이 검색어와 같은 곳만 쓰고, 같은 이름이 여러 곳이면 고르지 않고 멈춘다 (웹 검색창도 후보를 목록으로만
    보여 준다). `radius_km` 는 안내에만 쓰고, 반경으로 찾지 않는 호출부(trend)는 None 을 넘겨 '반경 안만 검색했습니다'
    안내를 받지 않는다.

    Returns:
        tuple[NaverRegion, str, list[str]]: 위치, 종류('주소', '동', '역', '단지', '지역'), 안내.
            '동' 이면 법정동 코드가 있어 동 전체를 검색할 수 있다.

    Raises:
        JibsaError: 같은 이름의 동·주소·역·단지나 '○가' 동이 여러 곳이면 REGION_AMBIGUOUS. 받은 결과가 잘려(다음 쪽이 있거나
            주소 결과가 10곳 넘음) 같은 이름이 한 곳만 보여도 정하지 않고 REGION_AMBIGUOUS(`candidate_count` null) 다. 넷 다
            이름이 같은 곳이 없으면 REGION_NOT_FOUND (이름이 비슷한 역·단지가 있으면 `candidates` 에 `--lat/--lng` 로 줄 좌표와
            함께 싣고, 받은 결과가 잘렸으면 뒤쪽에 있을 수 있다고 알린다).
    """
    # 이름이 같지 않아 쓰지 않은 역·단지 후보(REGION_AMBIGUOUS 후보와 같은 모양). 못 찾았을 때 후보로 준다
    similar: list[dict[str, Any]] = []
    # 다음 쪽이 있어 뒤쪽에 이름이 같은 곳이 있을 수 있는 검색 ('동', '역', '단지')
    truncated: list[str] = []

    def legal_division(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_legal_division(client, query, radius_km, truncated)
        if found is None:
            return None
        region, notes = found
        return region, '동' if is_dong_code(region.legal_division_code) else '지역', notes

    def station(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_subway_station(client, query, similar, truncated)
        return None if found is None else (found[0], '역', found[1])

    def complex_(client: NaverClient, query: str, radius_km: float | None) -> tuple[NaverRegion, str, list[str]] | None:
        found = _find_complex(client, query, similar, truncated)
        return None if found is None else (found[0], '단지', found[1])

    lookups = [_find_address, legal_division, station, complex_]
    if query.endswith('역'):
        lookups = [station, _find_address, legal_division, complex_]
    for lookup in lookups:
        found = lookup(client, query, radius_km)
        if found is not None:
            return found
    hint = (
        "주소(예: '역삼동 719-28', '테헤란로 152'), 동 이름(예: '역삼동'), 역 이름(예: '강남역'), "
        '단지 이름으로 다시 검색하거나 --lat/--lng 로 좌표를 직접 주세요'
    )
    if not similar and not truncated:
        raise RegionNotFoundError(query, hint=hint)
    message = f"{quoted(query, '과/와')} 이름이 같은 지역·역·단지를 찾지 못했습니다"
    if truncated:
        message += f" ({'·'.join(truncated)} 검색 결과가 잘려 뒤쪽에 이름이 같은 곳이 있을 수 있습니다)"
        hint = f'단지는 search complexes <동 이름> 으로 단지 번호를 찾아 --complex 로 주세요. 그 밖에는 {hint}'
    if similar:
        hint = (
            '이름이 비슷한 역·단지가 있습니다 (candidates). 맞는 곳이 있으면 그 lat·lng 를 --lat/--lng 로 주세요 '
            f'(단지 안 매물만은 --complex <complex_number>). 없으면 {hint}'
        )
    raise JibsaError(
        code='REGION_NOT_FOUND',
        message=message,
        hint=hint,
        details={'candidates': similar[:MAX_CANDIDATES_SHOWN]} if similar else None,
    )


def resolve_complex_number(client: NaverClient, name: str) -> tuple[int, bool | None]:
    """단지 이름을 단지 번호로 바꾼다. 이름이 똑같은 단지가 한 곳일 때만 그 단지다 (첫 후보를 고르지 않는다).

    자동완성 첫 쪽(10곳)만 보므로 다음 쪽이 있으면 똑같은 이름이 한 곳이어도 정하지 않는다 (`_same_name_complex`).

    Returns:
        tuple[int, bool | None]: 단지 번호, 빌라 단지인지 (`complex_is_villa`).

    Raises:
        JibsaError: 단지를 찾지 못하거나 이름이 똑같은 단지가 없으면 NOT_FOUND (비슷한 단지를 `candidates` 에 싣고, 다음 쪽이
            있으면 뒤쪽에 있을 수 있다고 알린다), 이름이 똑같은 단지가 여러 곳이거나 다음 쪽이 있어 더 있을 수 있으면
            REGION_AMBIGUOUS.
    """
    page = search_complexes(client, name)
    if not page.items:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"'{name}' 에 해당하는 네이버 단지를 찾지 못했습니다",
            hint='단지 이름을 줄이거나(예: 래미안) 단지 번호(fin.land.naver.com/complexes/{번호})로 다시 조회하세요',
        )
    best = _same_name_complex(name, page, coordinates=False)
    if best is None:
        shown = [_complex_candidate(item, coordinates=False) for item in page.items[:MAX_CANDIDATES_SHOWN]]
        retry = (
            '이름이 비슷한 단지가 있습니다 (candidates). 맞는 단지가 있으면 그 complex_number(단지 번호)로 다시 부르세요 '
            f"(예: {shown[0]['complex_number']})"
        )
        if page.has_next_page:
            # 자동완성은 똑같은 이름을 앞에 모아 주지 않는다 ('우성' 은 첫 쪽에 똑같은 이름이 없고 다음 쪽에 2곳, 2026-11-13 실측)
            total = f'결과 {page.total_count}곳 중' if page.total_count else '결과가 더 있는데'
            raise JibsaError(
                code='NOT_FOUND',
                message=(
                    f"'{name}' 단지 검색 결과 앞 {len(page.items)}곳에 이름이 같은 단지가 없습니다 "
                    f'({total} 앞쪽만 받아 뒤쪽에 있을 수 있습니다)'
                ),
                hint=(
                    f'{retry}. 없으면 단지 번호로 부르거나, search complexes <동 이름> 으로 그 동의 단지 번호를 찾아 '
                    '다시 부르세요'
                ),
                details={'candidates': shown},
            )
        raise JibsaError(
            code='NOT_FOUND',
            message=f"{quoted(name, '과/와')} 이름이 같은 네이버 단지가 없습니다",
            hint=retry,
            details={'candidates': shown},
        )
    return best.complex_number, complex_is_villa(best.type)


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


def _region_entries(items: list[NaverLegalDivisionInfoModel]) -> list[NaverRegionEntry]:
    """하위 지역 목록. 리(LI)는 뺀다.

    웹 지역 선택은 하위 지역 목록(subInfoList) 중 읍·면·동(EUP)까지만 보여 준다. 리는 좌표가 0,0 으로 와 위치로도 쓸 수 없다
    (2026-11-13 웹 대조: 세종 150곳 중 117곳이 리).
    """
    return [_region_entry(item) for item in items if item.legal_division_level_type != 'LI']


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
        JibsaError: 읍·면·동처럼 하위 지역이 없는 단위면 NOT_FOUND, 이름이 같은 시·군·구(동)가 여러 곳이면 REGION_AMBIGUOUS
            (자동완성 다음 쪽이 있으면 `candidate_count` null).
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
                regions=_region_entries(_sub_regions(client, 'GUN', only.legal_division_number)),
                notes=notes + [f"{name}{particle(name, '은/는')} 시·군·구가 {only.legal_division_name} 하나뿐이라 그 아래 읍·면·동입니다"],
            )
        return NaverRegionList(
            parent=name,
            parent_code=province.legal_division_number,
            regions=_region_entries(children),
            notes=notes,
        )

    # 자동완성은 네이버식 시·도 이름('서울시 강남구')으로만 찾는다. 정식 명칭('서울특별시 강남구'·'부산광역시 중구')은
    # 빈 목록이고, '서울 강남구' 는 '서울시 강남구' 를 주지만 검색어와 이름이 달라 맞춰 볼 수 없다 (2026-10-10).
    # 옛 이름('광주 광산구')은 빈 목록이다 (2026-10-11). 그래서 첫 단어가 시·도 이름이면 시·도 목록의 네이버 이름
    # (legalDivisionName, '전남광주시')으로 바꿔 묻고 맞춰 본다
    words = query.split()
    named = _find_province(provinces, words[0]) if len(words) > 1 else None
    keyword = ' '.join([named.legal_division_name, *words[1:]]) if named and named.legal_division_name else query
    page = _autocomplete_legal_divisions(client, keyword)
    items = page.items
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
    same = [
        item.legal_division_name or item.legal_division_number for item in exact
        if item.legal_division_level_type == best.legal_division_level_type
    ]
    if len(same) > 1:
        # 첫 곳으로 고르면 다른 곳의 동 목록이 나온다. search listings 처럼 후보를 알리고 멈춘다 (2026-10-15).
        # 자동완성은 다섯 곳만 줘서 다음 쪽이 있으면 전체 수를 모른다 ('송정동' 은 첫 쪽 5곳에 hasNextPage true·totalCount 14,
        # 2026-11-13 실측). 첫 쪽에 이름이 같은 곳이 한 곳뿐이면 그곳으로 보는 동작은 그대로 둔다 (2026-11-13 사용자 결정)
        candidates = [normalize_address(name) or name for name in same]
        raise _ambiguous(
            query, candidates, None if page.has_next_page else len(candidates),
            f"시·도 이름을 붙여 다시 주세요 (예: '{candidates[0]}')",
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
        regions=_region_entries(_sub_regions(client, 'GUN', best.legal_division_number)),
        notes=notes,
    )
