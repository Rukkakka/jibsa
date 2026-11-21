"""지역·역·좌표 해석과 동 경계, 아파트 동·구 지역 해석 (search locations, 모든 검색의 지역 해석)."""

import re

from jibsa.core.errors import (
    RegionAmbiguousError,
    RegionNotFoundError,
)
from jibsa.core.geo import (
    encode_geohash,
    geohashes_covering,
    geohashes_touching,
    in_multipolygon,
)
from jibsa.core.korean import (
    is_dong_code,
    is_ri_code,
    legal_dong_hint,
    quoted,
)
from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.region import (
    ZigbangLocalPolygonV2RequestParameterModel,
    ZigbangSearchServiceType,
    ZigbangSearchV2RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.service.common.base import (
    ZigbangBoundary,
    ZigbangRegion,
)


# room·store·stay 의 --radius 최대. room·stay 의 동 경계 검색도 이 원보다 지도 칸이 많으면 반경으로 바꾼다 (wide_boundary_note)
MAX_RADIUS_KM: float = 5.0


def search_regions(
    client: ZigbangClient,
    query: str,
    *,
    service_type: ZigbangSearchServiceType = '원룸',
) -> list[ZigbangSearchItemModel]:
    """`/v2/search` 결과 중 좌표가 있는 것만 돌려준다.

    기본(원룸)으로 찾으면 지역·역·학교·대학교가 나오고, 아파트 단지는 `service_type='아파트'`, 오피스텔 건물은
    `service_type='오피스텔'` 로 따로 찾아야 나온다 (2026-10-10 실측: 원룸으로는 헬리오시티·래미안대치팰리스 0건).
    """
    response = client.run_request_search_v2(
        ZigbangSearchV2RequestParameterModel(q=query, service_type=service_type)
    )
    return [
        item
        for item in response.items
        if item.lat is not None and item.lng is not None
    ]


def region_from_search_item(item: ZigbangSearchItemModel) -> ZigbangRegion:
    return ZigbangRegion(
        name=item.name,
        # 설명은 정식 시·도 이름으로 오지만 세종 학교는 '세종특별자치시  반곡동' 처럼 공백이 두 칸이라 정규화한다 (2026-10-11)
        address=normalize_address(item.description),
        search_type=item.type,
        local1=normalize_address(item.source.local1) if item.source and item.source.local1 else None,
        local2=item.source.local2 if item.source else None,
        local3=item.source.local3 if item.source else None,
        subway_id=item.id if item.type == 'subway' and item.id > 0 else None,
        lat=item.lat,
        lng=item.lng,
        legal_division_code=item.source.legal_division_code if item.source else None,
    )


def _prefix_words(address: str, name: str) -> list[tuple[str, str]]:
    """후보 주소에서 검색어 앞에 붙여 볼 낱말과 그 단위. 시·군·구 → 동 → 시·도 순이다.

    주소 첫 낱말은 시·도라('서울특별시 중구', '세종특별자치시 반곡동') 시·군·구로 보지 않는다.
    """
    words = address.split()
    district = next((word for word in reversed(words[1:]) if word[-1] in '시군구' and word != name), None)
    prefixes: list[tuple[str, str]] = []
    if district is not None:
        prefixes.append((district, district[-1]))
    if words and words[-1] not in (name, district) and words[-1][-1] not in '시군구':
        prefixes.append((words[-1], '동' if words[-1][-1] in '동가' else words[-1][-1]))
    if len(words) > 1:
        prefixes.append((words[0], '시·도'))
    return prefixes


def _retry_hint(same: list[ZigbangSearchItemModel], name: str) -> str:
    """다른 후보로 다시 검색하는 법. 예로 드는 검색어는 후보 하나로 가려지는 것(`_qualified_item`)만 쓴다.

    구 이름을 뒤에 붙이면('신사동 강남구') 직방이 동 대신 학교 같은 다른 결과를 먼저 주므로, 후보 주소의 낱말을 앞에 붙인
    검색어를 예로 든다. 시·군·구 → 동 → 시·도 순으로 붙여 본다: 다른 구의 같은 이름 동은 '강남구 신사동', 후보가 모두 같은
    시·군·구면(신촌역: 서대문구 창천동·신촌동) '창천동 신촌역', 같은 이름 구(중구)는 '서울특별시 중구' 다 (2026-11-16 실측:
    직방은 '서울특별시 중구'·'서울 중구' 에 서울 중구 하나만 준다). 후보 하나로 가려지지 않는 검색어를 들면 따라도 같은 에러가
    되풀이됐다 (2026-11-16 리뷰: 중구에 '구 이름을 앞에 붙이라' 고 했다).
    """
    for item in same:
        for word, unit in _prefix_words(item.description or '', name):
            example = f'{word} {name}'
            if _qualified_item(example, same) is item:
                return f"'{example}' 처럼 {unit} 이름을 앞에 붙여 다시 검색하세요"
    return '후보(candidates) 주소의 시·도·구·동 이름을 앞에 붙여 다시 검색하세요'


def _qualified_item(query: str, same: list[ZigbangSearchItemModel]) -> ZigbangSearchItemModel | None:
    """같은 이름 후보 가운데 검색어의 앞 낱말(구·동 이름)이 주소에 모두 든 곳이 하나뿐이면 그 후보(첫 결과). 아니면 None.

    직방은 '신촌동 신촌역' 에도 서대문구 창천동·신촌동의 두 신촌역을 함께 준다 (2026-11-15 실측). 사용자가 붙인 낱말로
    가릴 수 있으면 임의로 고르는 것이 아니라 그 후보로 찾는다. 주소까지 같은 결과는 같은 곳으로 본다 (`settled_item` 도
    주소로 후보를 센다).
    """
    qualifiers = query.split()[:-1]
    if not qualifiers:
        return None
    matched = [item for item in same if all(word in (item.description or '').split() for word in qualifiers)]
    return matched[0] if matched and len({item.description for item in matched}) == 1 else None


def settled_item(
    query: str,
    items: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> ZigbangSearchItemModel:
    """고른 곳과 이름·종류가 같은 후보 가운데 검색할 곳 하나를 정한다. 여러 곳이면 고르지 않고 멈춘다.

    검색어 앞 낱말로 후보 하나가 가려지면(`_qualified_item`) 그 후보, 같은 이름·같은 종류 후보가 한 곳이면 `best` 다.
    이름이 비슷하기만 한 결과(세종 → 세종동·세종로)나 종류가 다른 결과(신사동 → 신사역)는 세지 않는다.

    첫 곳으로 찾으면 엉뚱한 곳의 결과가 조용히 나온다 (2026-10-15 실측: 신사동은 직방 첫 곳이 은평구. 2026-11-15 실측:
    양평역은 첫 곳이 서울 영등포구이고 경기 양평군 양평역은 안내로만 알렸다). 지역·역·학교 모두 같은 이름의 후보 중 하나를
    임의로 고르지 않는다 (docs/development/provider-conventions.md '웹 화면과의 대응'. 웹 검색창도 후보를 보여 주고
    사용자가 고른다). 전체 주소('서울특별시 강남구 신사동')는 직방이 학교만 찾아 주므로 낱말 하나를 붙인 검색어를 권한다
    (`_retry_hint`). 모든 검색이 이 함수로 정해, 검색어 앞 낱말로 가리는 규칙이 명령마다 다르지 않다.

    Raises:
        RegionAmbiguousError: 같은 이름·같은 종류의 후보가 여러 곳일 때.
    """
    same = [item for item in items if item.type == best.type and item.name == best.name]
    qualified = _qualified_item(query, same)
    if qualified is not None:
        return qualified
    addresses = list(dict.fromkeys(item.description for item in same if item.description))
    if len(addresses) < 2:
        return best
    raise RegionAmbiguousError(query, addresses, len(addresses), hint=_retry_hint(same, best.name or query))


def wide_area_note(query: str, region: ZigbangRegion, radius_km: float) -> str | None:
    """지역 결과의 주소가 시·도·군·구로 끝나면 (서울, 강남구, 세종시) 중심 반경만 검색했다는 안내. 아니면 None.

    반경으로 찾을 때만 붙인다 (동 경계·지역 전체·동·구 목록 검색에는 붙이지 않는다). 단어 수가 아니라 끝 글자로
    본다 (세종 반곡동은 두 단어지만 동).
    """
    words = (region.address or '').split()
    if region.search_type != 'address' or not words or words[-1][-1] not in '시도군구':
        return None
    unit = '시·도' if len(words) == 1 else '시·군·구'
    return note(
        '범위',
        f"{quoted(query, '은/는')} {unit} 단위의 넓은 지역이라 중심({region.address})에서 "
        f'반경 {radius_km:g}km 안만 검색했습니다. 동·역 이름으로 좁혀 검색하세요',
    )


def resolve_region_with_notes(
    client: ZigbangClient,
    query: str,
    *,
    radius_km: float = 1.0,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, list[str]]:
    """지역명·역명을 반경 검색 중심점으로 바꾸고(지역(address) 결과 우선), 넓은 지역이거나 '○가' 로 나뉜 동이면 안내
    (`wide_area_note`·`ga_dong_note`)를 함께 준다. 같은 이름 후보가 여러 곳이면 멈춘다 (`settled_item`).

    `items` 는 같은 검색어로 이미 받은 `search_regions` 결과다. 주면 지역 검색을 다시 하지 않는다.

    Raises:
        RegionNotFoundError: 좌표가 있는 결과가 하나도 없을 때.
        RegionAmbiguousError: 같은 이름·같은 종류의 후보(동·구·역·학교)가 여러 곳일 때 (`settled_item`).
    """
    region, split_note, _ = resolve_region_scope(client, query, items=items)
    wide_note = wide_area_note(query, region, radius_km)
    return region, [note for note in (wide_note, split_note) if note]


def _dong_name(query: str) -> str:
    """검색어의 마지막 낱말. '○가' 동은 이 이름으로 비교한다.

    `_retry_hint` 가 권하는 대로 구 이름을 앞에 붙여도('성동구 성수동') 직방은 같은 동 후보를 주는데, 검색어 전체로
    비교하면 '○가' 동을 합치지 못했다 (2026-10-11 실측: '성동구 성수동' 은 2가 누락, '서구 부민동' 은 남부민동을 고름).
    """
    words = query.split()
    return words[-1] if words else ''


def best_region_item(
    query: str,
    items: list[ZigbangSearchItemModel],
    *,
    require_code: bool = False,
) -> ZigbangSearchItemModel | None:
    """검색 중심으로 쓸 지역(address) 결과. 지역 결과가 없으면 None.

    첫 지역 결과를 고르되, 그 이름이 검색어(마지막 낱말)와 다르고 '<검색어>N가' 동이 있으면 첫 '○가' 동을 고른다.
    직방은 '부민동' 을 [남부민동, 부민동1가, 부민동2가, 부민동3가] 순서로 줘서 첫 결과를 고르면 다른 동을
    찾는다 (2026-10-10 실측). 같은 이름의 지역이 뒤에 있어도 첫 결과를 둔다 (남동 → 남동구, 하동 → 하동군).
    `require_code` 면 법정동코드가 있는 지역만 본다 (아파트 지역 목록은 코드로 부른다).
    """
    name = _dong_name(query)
    regions = [
        item for item in items
        if item.type == 'address' and (not require_code or (item.source and item.source.legal_division_code))
    ]
    if not regions:
        return None
    if regions[0].name != name and name.endswith('동'):
        pattern = re.compile(rf'{re.escape(name)}\d+가')
        return next((item for item in regions if item.name and pattern.fullmatch(item.name)), regions[0])
    return regions[0]


def resolve_region_scope(
    client: ZigbangClient,
    query: str,
    *,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, str | None, list[ZigbangRegion]]:
    """`resolve_region_with_notes` 와 같되 넓은 지역 안내 없이, '○가' 로 나뉜 동의 안내와 동들을 따로 준다.

    같은 이름의 동 없이 '<검색어>N가' 로만 나뉜 동(성수동 → 성수동1가·2가)이면 그 동들을 준다 (첫 동이 검색 중심).
    동 안을 찾는 쪽은 그 동들을 함께 찾고 안내를 빼며, 그 밖에는 안내만 붙인다. 넓은 지역 안내(`wide_area_note`)는
    넣지 않아, 반경으로 찾는 쪽이 붙인다.

    어느 동이 함께 걸리는지는 `best_region_item`·`ga_dong_siblings`·`ga_dong_split`·`ga_dong_note` 만 판단한다
    (`resolve_apt_region` 도 같은 헬퍼를 쓴다). 그 동들을 어떻게 다룰지는 명령마다 다르다: room 은 지도 칸의 핀을 합친
    경계로 좁히고, store 는 서버에 동 코드를 함께 보내며, 지역 하나의 목록만 있는 apt·stay 는 합치지 않고 어느 동인지
    묻는다 (`divided_region_error`).

    Returns:
        (검색 중심, ○가 안내 또는 None, 합칠 ○가 동 (없으면 [])).

    Raises:
        RegionNotFoundError: 좌표가 있는 결과가 하나도 없을 때.
        RegionAmbiguousError: 같은 이름·같은 종류의 후보(동·구·역·학교)가 여러 곳일 때 (`settled_item`).
    """
    items = search_regions(client, query) if items is None else items
    if not items:
        raise RegionNotFoundError(query, hint=legal_dong_hint(query))
    # 같은 이름 후보가 여럿이어도 검색어 앞 낱말로 하나가 가려지면 그 후보가 검색 중심이다 ('신촌동 신촌역')
    best = settled_item(query, items, best_region_item(query, items) or items[0])
    siblings = ga_dong_siblings(query, items, best)
    split = ga_dong_split(query, siblings, best)
    return (
        region_from_search_item(best),
        ga_dong_note(query, siblings, best),
        [region_from_search_item(item) for item in split],
    )


def resolve_station(client: ZigbangClient, query: str) -> ZigbangRegion | None:
    """역 이름을 역 하나로 바꾼다 (역만 받는 명령: search complexes). 검색어(마지막 낱말)와 이름이 같은 역이 없으면 None.

    다른 검색처럼 지역(address) 결과를 먼저 고르면, 동 이름('신사동')에 같은 이름 동의 `REGION_AMBIGUOUS` 를 내고 그 힌트
    ('은평구 신사동')를 따르면 '역이 아닙니다' 가 됐다 (2026-11-16 리뷰). 역 결과만 보고, 같은 이름 역이 여럿이면 다른
    검색과 같이 멈춘다 ('창천동 신촌역' 은 검색어 앞 낱말로 가린다).

    Raises:
        RegionNotFoundError: 좌표가 있는 결과가 하나도 없을 때.
        RegionAmbiguousError: 같은 이름의 역이 여러 곳일 때 (`settled_item`).
    """
    items = search_regions(client, query)
    if not items:
        raise RegionNotFoundError(query, hint=legal_dong_hint(query))
    name = _dong_name(query)
    station = next((item for item in items if item.type == 'subway' and item.name == name), None)
    return region_from_search_item(settled_item(query, items, station)) if station else None


def ga_dong_siblings(
    query: str,
    items: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> list[ZigbangSearchItemModel]:
    """'<검색어>N가' 이름의 법정동 후보 (성수동 → 성수동1가·성수동2가). 고른 지역과 같은 시·구만 센다.

    '○가' 동은 이름이 검색어와 달라 `settled_item` 의 같은 이름 검사에 걸리지 않는데, 첫 후보만 찾으면
    나머지 '○가' 가 조용히 빠진다 (2026-10-10 실측: 성수동은 1가만 찾아 2가 상가 217건이 빠짐).
    """
    name = _dong_name(query)
    if best.type != 'address' or not name.endswith('동') or not best.description:
        return []
    parent = best.description.rsplit(' ', 1)[0]
    pattern = re.compile(rf'{re.escape(name)}\d+가')
    return [
        item for item in items
        if item.type == 'address' and item.name and pattern.fullmatch(item.name)
        and item.description and item.description.rsplit(' ', 1)[0] == parent
    ]


def ga_dong_split(
    query: str,
    siblings: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> list[ZigbangSearchItemModel]:
    """함께 찾을 '○가' 동 (검색 중심 포함). 검색어와 같은 이름의 동이 따로 있거나(당산동) 고른 지역이 '○가' 동이
    아니면 [] 라 그 동만 찾는다."""
    return [] if best.name == _dong_name(query) or best not in siblings else siblings


def ga_dong_note(query: str, siblings: list[ZigbangSearchItemModel], best: ZigbangSearchItemModel) -> str | None:
    """'○가' 동이 검색에서 빠졌다는 안내. 나뉜 동이 없으면 None."""
    names = [item.name for item in siblings if item.name]
    others = [name for name in names if name != best.name]
    if not others:
        return None

    def span(values: list[str]) -> str:
        return '·'.join(values) if len(values) <= 3 else f'{values[0]}~{values[-1]}'

    # '○가' 로 끝나 조사는 받침 없는 꼴(는·를·로)로 고정한다
    if best.name == _dong_name(query):
        return note(
            '범위',
            f'이번 검색은 {best.name}만 찾았습니다. {span(others)}는 따로 있는 동이라 빠졌습니다. '
            '함께 보려면 각각 검색하거나 --radius 로 위치 기준으로 찾으세요',
        )
    return note(
        '범위', f"{quoted(query, '은/는')} {span(names)}로 나뉘어 있어 {best.name}를 기준으로 찾았습니다. 다른 곳도 보려면 각각 검색하세요",
    )


def city_gu_items(
    query: str,
    items: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> list[ZigbangSearchItemModel]:
    """구가 있는 시(성남시)를 찾았으면 그 시의 구 결과 (검색 중심 포함). 아니면 [].

    직방 지역 검색은 구가 있는 시를 시 대신 그 구들로 준다 (2026-10-11 실측: 성남시 → 분당구·수정구·중원구, 수원시 4곳,
    창원시 5곳, 고양·용인·부천시 3곳, 포항시 2곳). 시 코드(성남시 41130)의 아파트 목록은 0건이라 첫 구만 찾으면 나머지
    구 매물이 조용히 빠진다 (분당구 255건만 찾고 수정구 558건·중원구 116건이 빠짐). 그래서 아파트·단기임대는 첫 구로 찾지 않고
    어느 구인지 묻는다 (`divided_region_error`).

    '시' 를 떼고 쓴 이름('성남')도 같은 시로 본다. 직방은 '성남' 에도 그 시의 구들을 맨 앞에 주는데, '시' 가 붙은 이름만
    보면 첫 구만 찾고 다른 구가 빠졌다는 안내도 없었다 (2026-10-28 실측: 성남·안양·고양 모두 구들이 맨 앞이고 같은 이름의
    동은 그 뒤, '성남' 아파트는 분당구 283건만 찾았다). 검색 중심이 '<이름>시 ○구' 가 아니면
    (동 이름 등 다른 뜻) 그대로 [] 다.
    """
    city = _dong_name(query)
    if not city.endswith('시'):
        city += '시'
    if not (best.name or '').startswith(f'{city} ') or not best.description:
        return []
    parent = best.description.rsplit(' ', 1)[0]
    return [
        item for item in items
        if item.type == 'address' and (item.name or '').startswith(f'{city} ')
        and item.source and (item.source.legal_division_code or '').endswith('00000')
        and (item.description or '').rsplit(' ', 1)[0] == parent
    ]


def city_gu_regions(query: str, items: list[ZigbangSearchItemModel]) -> list[ZigbangRegion]:
    """구가 있는 시(성남시)면 그 시의 구들 (검색 중심 구가 먼저). 아니면 []. 검색 중심은 `resolve_region_scope` 와 같이 고른다."""
    best = best_region_item(query, items)
    return [region_from_search_item(item) for item in city_gu_items(query, items, best)] if best else []


def merged_dong_region(
    region: ZigbangRegion,
    parts: list[ZigbangRegion],
    center: tuple[float, float] | None = None,
) -> ZigbangRegion:
    """'○가' 동들(성수동1가·2가)을 함께 찾은 결과의 검색 중심. room·store 가 같은 모양으로 낸다.

    이름·주소의 동을 '성수동1가·성수동2가' 로 바꾸고, 중심은 `center`(없으면 동 중심들의 가운데)로 옮기며,
    한 동의 법정동코드는 뗀다. 아파트·단기임대는 동들을 합치지 않아(`divided_region_error`) 쓰지 않는다.
    """
    names = '·'.join(part.name for part in parts)
    lat, lng = center or (sum(part.lat for part in parts) / len(parts), sum(part.lng for part in parts) / len(parts))
    parent = (region.address or '').rsplit(' ', 1)[0]
    return region.model_copy(update={
        'name': names, 'address': f'{parent} {names}'.strip(), 'lat': lat, 'lng': lng, 'legal_division_code': None,
    })


def divided_region_error(query: str, parts: list[ZigbangRegion]) -> RegionAmbiguousError:
    """검색어가 직방이 따로 보여 주는 지역 여럿에 걸릴 때의 에러: '○가' 로 나뉜 동(성수동 → 성수동1가·2가), 구가 있는 시
    (성남시 → 분당구·수정구·중원구).

    지역 하나의 목록만 있는 조회(아파트 지역 목록, 단기임대 지역 검색)가 쓴다. 웹은 그 동·구를 하나씩 따로 보여 주고
    (2026-11-15 실측: 아파트 성남시 코드 41130 은 0건, 단기임대 검색창은 성수동1가·2가를 따로 준다), 목록 여럿을 합친
    순서·수는 웹에 없어 합치지 않고 어느 곳인지 묻는다. 지도 칸의 핀을 좁히는 room, 동 코드 여럿을 서버가 한 번에 받는
    store 는 합친 범위로 찾는다.
    """
    first = parts[0].name if parts else query
    unit = '구 이름까지' if first.split()[-1].endswith('구') else '동 이름을 정확히'
    return RegionAmbiguousError(
        query,
        [part.address or part.name for part in parts],
        len(parts),
        hint=f"'{first}' 처럼 {unit} 주세요",
    )


def local_code_of(legal_division_code: str) -> str:
    """법정동코드 10자리를 직방 아파트 지역 코드로 줄인다.

    직방은 시·군·구 5자리, 읍·면·동 8자리로 찾는다. 10자리를 그대로 보내면 에러 없이 0건이다. 리(10자리 끝 두
    자리가 00 이 아님)는 읍·면 8자리로 올린다 (2026-10-11 실측: 양근리 4183025021 은 0건, 양평읍 41830250 은 88건).
    시·도 2자리도 에러 없이 늘 0건이라 (2026-10-11 실측: 11·41·26·36 모두 0건, 강남구 11680 은 1683건)
    `resolve_apt_region` 이 시·도를 `RegionNotFoundError` 로 거절해 여기에는 오지 않는다. 구가 있는 시의 시 코드(성남시
    41130)도 0건이라 (2026-11-15 실측) `resolve_apt_region` 이 어느 구인지 묻는다 (`city_gu_items`).
    """
    if legal_division_code.endswith('00000000'):
        return legal_division_code[:2]
    if legal_division_code.endswith('00000'):
        return legal_division_code[:5]
    return legal_division_code[:8]


def resolve_apt_region(
    client: ZigbangClient,
    query: str,
    *,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, list[str]]:
    """아파트 검색 지역(동·구 하나)과 결과에 붙일 안내를 찾는다. 아파트는 반경이 아니라 동·구 단위로 조회한다.

    웹 지역 매물 화면(`/home/apt/items/{지역 코드}`)은 지역 코드 하나의 목록만 보여 준다 (2026-11-15 캡처). 그래서
    '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)이나 구가 있는 시(성남시 → 분당구·수정구·중원구)는 목록을 합치지 않고
    어느 동·구인지 묻는다. `items` 는 같은 검색어로 이미 받은 `search_regions` 결과다. 주면 지역 검색을 다시 하지 않는다.

    Returns:
        (검색할 동·구, 안내).

    Raises:
        RegionNotFoundError: 법정동코드가 있는 지역 결과가 없거나(역 이름만 준 경우 등) 시·도일 때. 직방 지역 목록은
            시·도 코드에 늘 0건이다 (`local_code_of`).
        RegionAmbiguousError: 같은 이름의 동·구가 여러 곳일 때 (`settled_item`), '○가' 로만 나뉜 동이거나 구가 있는
            시일 때 (`divided_region_error`).
    """
    items = search_regions(client, query) if items is None else items
    best = best_region_item(query, items, require_code=True)
    # 같은 이름 동·구는 room·store·stay 와 같이 검색어 앞 낱말로 가리고, 가려지지 않으면 묻는다
    best = settled_item(query, items, best) if best is not None else None
    code = best.source.legal_division_code if best and best.source else None
    if best is None or code is None or code.endswith('00000000'):
        # 행정동(역삼1동)은 직방 지역 검색이 0건이라(2026-10-11 실측: 역삼1동·화곡제1동·상계3.4동·월곡1동) CLI 의 위치
        # 찾기가 행정동 힌트를 낸다. 역 이름이면 CLI 가 이 에러를 잡아 그 위치가 속한 동(`apt_dong_at`)으로 찾는다
        raise RegionNotFoundError(
            query,
            hint="아파트는 동·구 단위로 조회합니다. 동 이름(예: '역삼동')이나 구 이름(예: '강남구'), 역 이름(예: '강남역')으로 다시 검색하세요",
        )
    # 구 단위로 조회해 넓은 지역 안내(wide_area_note)는 붙이지 않는다
    notes: list[str] = []
    gus = city_gu_items(query, items, best)
    if gus:
        raise divided_region_error(query, [region_from_search_item(item) for item in gus])
    # 지역 결과는 모두 법정동코드가 있어 (2026-10-11 실측: '○가' 동 145건·그 밖의 지역 25건) 형제 동은 코드로 다시 거르지 않는다
    siblings = ga_dong_siblings(query, items, best)
    split = ga_dong_split(query, siblings, best)
    if split:
        raise divided_region_error(query, [region_from_search_item(item) for item in split])
    if is_ri_code(code):
        # 리는 읍·면 지역 목록으로 찾는다 (local_code_of). 지역 결과의 local3 이 그 읍·면이다 (2026-10-11 실측: 양근리 → 양평읍)
        town = best.source.local3 if best.source and best.source.local3 else '읍·면'
        notes.append(note(
            '범위',
            f"{quoted(query, '은/는')} 리 단위라 직방 아파트 목록이 받지 않아 상위 {town} 전체 매물을 찾았습니다. "
            'address 로 위치를 확인하세요',
        ))
    split_note = ga_dong_note(query, siblings, best)
    return region_from_search_item(best), notes + ([split_note] if split_note else [])


def merge_dong_boundaries(client: ZigbangClient, regions: list[ZigbangRegion]) -> ZigbangBoundary | None:
    """'○가' 동들의 경계를 하나로 합친다 (동마다 경계 요청 1회). 받은 경계가 없으면 None."""
    boundaries = [boundary for region in regions if (boundary := dong_boundary(client, region)) is not None]
    if not boundaries:
        return None
    return ZigbangBoundary(
        name='·'.join(boundary.name for boundary in boundaries),
        code=boundaries[0].code,
        polygons=[polygon for boundary in boundaries for polygon in boundary.polygons],
    )


def to_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, '') else None
    except ValueError:
        return None


# 경계를 물을 geohash 정밀도. 7 에서 옆 동이 잡히면 8 로 한 번 더 묻는다
BOUNDARY_GEOHASH_PRECISIONS: tuple[int, ...] = (7, 8)


def dong_boundary(client: ZigbangClient, region: ZigbangRegion) -> ZigbangBoundary | None:
    """지역이 읍·면·동이면 그 경계를 받는다 (1~2회 호출). 동이 아니거나 다른 동이 잡히면 None.

    경계 API 는 geohash 칸 중심이 속한 동을 주는데, 칸이 크면(정밀도 6 이하) 작은 동은 옆 동이 잡혀
    정밀도 7 로 묻고 법정동코드가 같은지 확인한다. 7 에서도 옆 동이 잡히면 8 로 한 번 더 묻는다 (2026-10-10
    실측: '○가' 동 64곳 중 6곳(부민동2가 등)이 7 에서 옆 동, 8 에서 모두 맞음).

    동 코드인데 None 이 되는 경우는 실측으로 없었다. 직방 지역 검색의 동 중심은 늘 그 동 경계 안이라 8 까지 물으면
    맞는다 (2026-10-11 실측: 강변·해안·섬처럼 모양이 복잡한 읍·면·동 28곳 모두 중심이 경계 안이고 경계를 받음).
    그래서 호출하는 쪽은 경계를 못 받아 반경으로 찾게 된 경우의 안내를 따로 두지 않는다.

    검색 결과의 종류(type)는 따로 보지 않는다. 법정동코드는 지역·아파트 결과에만 있고(역·학교·대학교 결과에는 키가
    없다), room·store·stay 가 쓰는 기본(원룸) 검색에는 아파트 결과가 나오지 않아 동 경계는 지역 결과로만 찾는다
    (2026-10-10 실측 15곳).
    """
    if not is_dong_code(region.legal_division_code):
        return None
    code = (region.legal_division_code or '')[:8]
    for precision in BOUNDARY_GEOHASH_PRECISIONS:
        response = client.run_request_local_polygon_v2(
            ZigbangLocalPolygonV2RequestParameterModel(geohash=encode_geohash(region.lat, region.lng, precision))
        )
        if response.code == code:
            break
    else:
        return None
    if response.geojson is None or not response.geojson.coordinates:
        return None
    return ZigbangBoundary(name=response.name or region.name, code=code, polygons=response.geojson.coordinates)


def scope_geohashes(
    region: ZigbangRegion,
    radius_km: float,
    boundary: ZigbangBoundary | None,
    precision: int,
) -> list[str]:
    """반경(또는 동 경계)을 덮는 geohash 칸."""
    if boundary is None:
        return geohashes_covering(region.lat, region.lng, radius_km, precision)
    return geohashes_touching(boundary.polygons, precision)


def wide_boundary_note(
    region: ZigbangRegion,
    boundary: ZigbangBoundary,
    precision: int,
    radius_km: float,
) -> str | None:
    """동 경계에 닿는 지도 칸이 반경 `MAX_RADIUS_KM` 원보다 많으면, 경계 대신 중심 반경으로 찾는다는 안내. 아니면 None.

    지도 칸마다 요청 1회라 큰 읍·면은 경계 검색이 요청을 많이 보낸다 (2026-10-10 실측: 홍천 내면은 원룸 41칸 × 유형 수).
    반경 5km 원은 원룸(정밀도 5) 11칸이다. 상가는 지도 칸 대신 서버의 동 코드 조회를 써서 이 검사를 거치지 않는다.

    경계 검색이 이어지면 검색 함수가 같은 칸을 다시 계산하지만, 이 검사를 통과한 경계는 칸이 적어 칸 목록을 넘기지
    않는다.
    """
    cells = len(geohashes_touching(boundary.polygons, precision))
    if cells <= len(geohashes_covering(region.lat, region.lng, MAX_RADIUS_KM, precision)):
        return None
    return note(
        '범위',
        f'{boundary.name} 경계가 넓어(지도 칸 {cells}개) 경계 대신 중심에서 반경 {radius_km:g}km 안만 찾았습니다. '
        '범위를 바꾸려면 --radius 를 주거나 역 이름으로 찾으세요',
    )


def outside_boundary(boundary: ZigbangBoundary | None, lat: float, lng: float) -> bool:
    """동 경계로 찾을 때 경계 밖이면 True. 반경 검색이면 늘 False."""
    return boundary is not None and not in_multipolygon(lat, lng, boundary.polygons)
