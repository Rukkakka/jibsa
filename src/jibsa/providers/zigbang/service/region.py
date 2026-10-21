"""지역·역·좌표 해석과 동 경계 (search locations, 모든 검색의 지역 해석)."""

import re

from jibsa.core.errors import (
    JibsaError,
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
    legal_dong_hint,
    quoted,
)
from jibsa.core.listing import note
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.region import (
    ZigbangLocalPolygonV2RequestParameterModel,
    ZigbangSearchServiceType,
    ZigbangSearchV2RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.service.common import (
    ZigbangBoundary,
    ZigbangRegion,
    region_from_search_item,
)


# room·store·stay 의 --radius 최대. 동 경계 검색도 이 원보다 지도 칸이 많으면 반경으로 바꾼다 (wide_boundary_note)
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


def _retry_hint(address: str, name: str) -> str:
    """다른 후보로 다시 검색하는 법. 구 이름을 뒤에 붙이면('신사동 강남구') 직방이 동 대신 학교 같은
    다른 결과를 먼저 주므로, 다른 후보의 시·군·구를 앞에 붙인 검색어를 예로 든다 ('강남구 신사동')."""
    district = next((word for word in reversed(address.split()) if word[-1] in '시군구'), None)
    if district is None:
        return '구 이름을 앞에 붙여 다시 검색하세요'
    return f"'{district} {name}' 처럼 구 이름을 앞에 붙여 다시 검색하세요"


def region_notes(
    query: str,
    items: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> list[str]:
    """고른 지역이 모호할 때 결과에 붙일 안내. 같은 이름의 지역(동·구)이 여러 곳이면 고르지 않고 멈춘다.

    같은 이름·같은 종류 결과가 여러 곳이면 (신사동, 양평역, 종로1가) 후보를 알린다. 이름이 비슷하기만 한
    결과(세종 → 세종동·세종로)나 종류가 다른 결과(신사동 → 신사역)는 세지 않는다. 넓은 지역 안내는 반경으로
    찾을 때만 맞아 `wide_area_note` 로 따로 붙인다.

    지역은 첫 곳으로 찾으면 소스마다 다른 곳을 찾는다 (2026-10-15 실측: 신사동은 직방 첫 곳이 은평구, 당근은 강남구,
    네이버는 REGION_AMBIGUOUS). 그래서 네이버처럼 후보를 알리고 멈춘다. 역은 네이버·당근처럼 첫 역으로 찾고 안내한다.
    전체 주소('서울특별시 강남구 신사동')는 직방이 학교만 찾아 주므로 구 이름을 붙인 검색어를 권한다.

    Raises:
        RegionAmbiguousError: 같은 이름의 지역(동·구)이 여러 곳일 때.
    """
    same = [item for item in items if item.type == best.type and item.name == best.name]
    addresses = list(dict.fromkeys(item.description for item in same if item.description))
    if len(addresses) < 2:
        return []
    if best.type == 'address':
        raise RegionAmbiguousError(query, addresses, len(addresses), hint=_retry_hint(addresses[0], best.name))
    return [note(
        '모호',
        f"{quoted(query, '은/는')} 여러 곳에 있습니다 ({', '.join(addresses)}). "
        f'첫 번째인 {addresses[0]} 기준으로 검색했습니다. 다른 곳이면 {_retry_hint(addresses[1], best.name)}',
    )]


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
    """지역명·역명을 반경 검색 중심점으로 바꾸고(지역(address) 결과 우선), 모호하거나 넓은 지역이면 안내
    (`region_notes`·`wide_area_note`)를 함께 준다.

    `items` 는 같은 검색어로 이미 받은 `search_regions` 결과다. 주면 지역 검색을 다시 하지 않는다.

    Raises:
        RegionNotFoundError: 좌표가 있는 결과가 하나도 없을 때.
        RegionAmbiguousError: 같은 이름의 지역(동·구)이 여러 곳일 때 (`region_notes`).
    """
    region, notes, split_note, _ = resolve_region_scope(client, query, items=items)
    wide_note = wide_area_note(query, region, radius_km)
    return region, notes + [note for note in (wide_note, split_note) if note]


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
) -> tuple[ZigbangRegion, list[str], str | None, list[ZigbangRegion]]:
    """`resolve_region_with_notes` 와 같고, '○가' 로 나뉜 동의 안내와 동들을 따로 준다.

    같은 이름의 동 없이 '<검색어>N가' 로만 나뉜 동(성수동 → 성수동1가·2가)이면 그 동들을 준다 (첫 동이 검색 중심).
    경계로 찾는 쪽은 경계를 합치고 안내를 빼며, 그 밖에는 안내만 붙인다. 넓은 지역 안내(`wide_area_note`)는
    넣지 않아, 반경으로 찾는 쪽이 붙인다.

    어느 동을 합칠지는 `best_region_item`·`ga_dong_siblings`·`ga_dong_split`·`ga_dong_note` 만 판단한다
    (`resolve_apt_region` 도 같은 헬퍼를 쓴다). 명령마다 다른 건 합치는 방법뿐이라(room·store 는 경계를 합치고, stay 는
    동마다 검색 API, apt 는 동마다 지역 목록) 범위 객체 하나로 묶지 않는다.

    Returns:
        (검색 중심, 안내, ○가 안내 또는 None, 합칠 ○가 동 (없으면 [])).

    Raises:
        RegionNotFoundError: 좌표가 있는 결과가 하나도 없을 때.
        RegionAmbiguousError: 같은 이름의 지역(동·구)이 여러 곳일 때 (`region_notes`).
    """
    items = search_regions(client, query) if items is None else items
    if not items:
        raise RegionNotFoundError(query, hint=legal_dong_hint(query))
    best = best_region_item(query, items) or items[0]
    siblings = ga_dong_siblings(query, items, best)
    split = ga_dong_split(query, siblings, best)
    return (
        region_from_search_item(best),
        region_notes(query, items, best),
        ga_dong_note(query, siblings, best),
        [region_from_search_item(item) for item in split],
    )


def ga_dong_siblings(
    query: str,
    items: list[ZigbangSearchItemModel],
    best: ZigbangSearchItemModel,
) -> list[ZigbangSearchItemModel]:
    """'<검색어>N가' 이름의 법정동 후보 (성수동 → 성수동1가·성수동2가). 고른 지역과 같은 시·구만 센다.

    '○가' 동은 이름이 검색어와 달라 `region_notes` 의 같은 이름 안내에 걸리지 않는데, 첫 후보만 찾으면
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
    구 매물이 조용히 빠진다 (분당구 255건만 찾고 수정구 558건·중원구 116건이 빠짐). 아파트는 구마다 지역 목록을 받아 합친다.
    """
    city = _dong_name(query)
    if not city.endswith('시') or not (best.name or '').startswith(f'{city} ') or not best.description:
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


def geocoding_failed(zigbang_error: Exception, naver_error: Exception) -> JibsaError:
    """당근 단독 명령이 역·장소 이름의 좌표를 직방·네이버 어디서도 찾지 못했을 때의 에러.

    당근 명령은 동이 아닌 이름을 직방 지역 검색으로 찾고, 직방이 막히거나 실패하면(서버 오류·네트워크·응답 형식)
    네이버로 다시 찾는다. 네이버도 막혔거나 실패했거나 못 찾는 이름(대학교 등)일 때 쓴다. 당근 동 이름 검색과
    좌표 검색은 직방·네이버를 거치지 않아 지금도 된다. 실패한 소스가 직방임을 `source` 로 알린다. 직방 요청 제한은
    그 에러(RATE_LIMITED, 남은 시간)를 그대로 쓰고, 그 밖의 실패는 UPSTREAM_ERROR 로 바꾼다. 그대로 올리면 명령의
    소스(daangn)로 보고돼 에이전트가 멀쩡한 당근을 버린다.
    """
    if isinstance(naver_error, RateLimitedError):
        reason = '네이버도 막혀 있습니다'
    elif isinstance(naver_error, RegionNotFoundError):
        reason = '네이버 지역 검색으로는 찾지 못했습니다'
    else:
        reason = '네이버 지역 검색도 실패했습니다'
    blocked = isinstance(zigbang_error, RateLimitedError)
    hint = (
        f"역·장소 이름은 직방 지역 검색으로 위치를 찾는데 직방이 {'막혀 있고' if blocked else '실패했고'}, {reason}. "
        '당근 동 이름(예: 역삼동)으로 찾거나 --lat/--lng 로 좌표를 직접 주세요'
    )
    if isinstance(zigbang_error, RateLimitedError):
        zigbang_error.hint = hint
        zigbang_error.details['source'] = 'zigbang'
        return zigbang_error
    return JibsaError(
        code='UPSTREAM_ERROR',
        message=f'직방 지역 검색이 실패했습니다 ({type(zigbang_error).__name__}: {zigbang_error})',
        hint=hint,
        details={'source': 'zigbang'},
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

    지도 칸마다 요청 1회라 큰 읍·면은 경계 검색이 수백 번 요청한다 (2026-10-10 실측: 홍천 내면은 상가 851칸,
    원룸 41칸 × 유형 수). 반경 5km 원은 상가(정밀도 6) 159칸, 원룸(정밀도 5) 11칸이다.

    경계 검색이 이어지면 검색 함수가 같은 칸을 다시 계산하지만, 이 검사를 통과한 경계는 칸이 적어 칸 목록을 넘기지
    않는다 (2026-10-11 실측: 역삼동 상가 14칸 2ms, 울릉읍 64칸 21ms. 홍천 내면 851칸 140ms 는 여기서 반경으로 바뀐다).
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
