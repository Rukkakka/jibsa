"""동네·역·주소·좌표 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석)."""

import logging
import re
from collections.abc import Callable

from httpx import (
    HTTPStatusError,
    TransportError,
)
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
from jibsa.core.geo import box_around
from jibsa.core.korean import quoted
from jibsa.core.listing import (
    SIDO_OFFICIAL_NAMES,
    join_address,
    note,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel
from jibsa.providers.daangn.api.request.region import (
    DaangnGeocodeAddressRequestPayloadModel,
    DaangnGetRegionByCoordinateRequestPayloadModel,
    DaangnQueryInputModel,
    DaangnRegionsKeywordV1RequestParameterModel,
    DaangnSearchAddressRequestPayloadModel,
    DaangnSearchSubwayStationPoisRequestPayloadModel,
)
from jibsa.providers.daangn.api.request.search import (
    DaangnBoundsLocationFilterModel,
    DaangnMapRequestParameterModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteArticleEdgeModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.api.response.region import (
    DaangnAddressModel,
    DaangnLocationModel,
    DaangnSubwayStationPoiModel,
)
from jibsa.providers.daangn.service.common import (
    OPTIONAL_LOOKUP_ERRORS,
    DaangnRegion,
    partial_failure_note,
    station_name,
    unwrap_graphql,
)

from typing import (
    Annotated,
    Literal,
)


logger = logging.getLogger(__name__)
# 검색어 끝의 도로명 주소 ('테헤란로 152', '강남대로118길 63', '테헤란로152')
ROAD_ADDRESS_PATTERN: re.Pattern[str] = re.compile(r'(?P<key>\S+(?:로|길))\s*(?P<number>\d+(?:-\d+)?)$')
# 검색어 끝의 지번 주소 ('역삼동 736-1', '양근리 산 12'). 도로명이 아닐 때만 본다
LOT_ADDRESS_PATTERN: re.Pattern[str] = re.compile(r'(?P<key>\S+(?:동|가|리|읍|면))\s*(?P<number>(?:산\s*)?\d+(?:-\d+)?)$')
# 주소 검색 후보 수. 같은 주소가 여러 시·군·구에 있는지 보려고 웹(4개)보다 많이 받는다
ADDRESS_SEARCH_SIZE: int = 10


# 지역 검색(regions/keyword)이 한 번에 주는 최대 후보 수 (2026-10-11 실측: 창원시·서울 100건에서 잘림)
REGION_KEYWORD_MAX_RESULTS: int = 100
# 같은 이름 지역으로 멈출 때 보여 줄 후보 수 (네이버와 같다). 나머지는 전체 수(candidate_count)로만 알린다 (중앙동 58곳)
AMBIGUOUS_CANDIDATES_SHOWN: int = 5
# 시·도 줄임말 표(SIDO_OFFICIAL_NAMES)에 있지만 그 자체로 시 이름인 것. 광주광역시가 전남광주통합특별시로 합쳐진 뒤
# '광주시' 는 경기도 광주시뿐이라 `place_in` 이 시·도로 넓히지 않는다 (2026-10-12 실측: '송정동 --city 광주시' 가
# 경기도 광주시 송정동과 전남광주통합특별시 광산구 송정동 두 곳에 맞아 '--city 로 지정하세요' 라고 안내했다)
CITY_NAMES_NOT_SIDO: frozenset[str] = frozenset({'광주시'})


def search_locations(client: DaangnClient, keyword: str) -> list[DaangnLocationModel]:
    """지역명 후보 중 동/읍/면(depth 3)만 돌려준다."""
    response = client.run_request_regions_keyword_v1(
        DaangnRegionsKeywordV1RequestParameterModel(keyword=keyword)
    )
    return [location for location in response.locations if location.depth == 3]


def ri_region_error(query: str) -> UnsupportedRegionError:
    """'리' 단위 지역. 당근 지역은 읍·면·동까지라 찾을 수 없다."""
    return UnsupportedRegionError(
        code='REGION_NOT_FOUND',
        message=f"'{query}' 는 리 단위라 당근에서 찾을 수 없습니다 (당근은 읍·면·동까지만 다룹니다)",
        hint='상위 지역(읍·면) 이름으로 다시 검색하세요',
        skip_note='daangn 은 리 단위 지역을 다루지 않습니다 (읍·면·동까지만). 상위 지역 이름으로 검색하면 당근 결과도 받을 수 있습니다',
    )


def place_in(place: str, *texts: str | None) -> bool:
    """지역 이름 한 마디(`place`)로 시작하는 단어가 주소 조각 중 하나에 있는지.

    단어 앞부분만 본다. '강남' 은 '강남구' 에 맞지만 '남구' 는 '강남구', '동구' 는 '성동구' 에 맞지 않는다
    (2026-10-11 실측: 글자가 들어 있는지만 보면 '송정동 --city 동구' 가 대구 동구가 아닌 서울 성동구 송정동을 골랐다).
    당근은 시·도를 정식 명칭으로만 써서, 줄임말·옛 이름('서울시'·'강원도'·'전라남도')은 정식 명칭으로도 찾는다
    (2026-10-10 실측: '서울시' 는 '서울특별시' 에 들어 있지 않아 --city 와 주소 검색이 못 찾았다).
    시 이름이기도 한 줄임말(`CITY_NAMES_NOT_SIDO`, '광주시')은 정식 명칭으로 넓히지 않는다.
    """
    official = place if place in CITY_NAMES_NOT_SIDO else SIDO_OFFICIAL_NAMES.get(place, place)
    prefixes = (place, official)
    return any(word.startswith(prefixes) for text in texts if text for word in text.split())


def resolve_regions(
    client: DaangnClient,
    query: str,
    *,
    city: str | None = None,
    notes: list[str] | None = None,
    station_hint: bool = False,
    merge_ga: bool = False,
) -> list[DaangnRegion]:
    """지역명을 조회할 동으로 바꾼다.

    동 이름과 정확히 같은 후보를 우선하고, `city` 가 있으면 시/도·구 이름이
    그 이름으로 시작하는 후보만 남긴다 (시·도 줄임말 포함, `place_in`). 주변 동 확장은
    첫 동의 피드를 봐야 해서 `search_listings(expand=...)` 가 한다. `notes` 를 주면 조회한 동이
    검색어와 다를 때(`region_notes`)의 안내를 붙인다.

    같은 이름의 동이 여러 곳이면 고르지 않고 멈춘다. 첫 곳으로 찾으면 소스마다 다른 곳을 찾는다
    (2026-10-15 실측: 신사동은 당근 첫 곳이 강남구, 직방은 은평구, 네이버는 REGION_AMBIGUOUS).

    Raises:
        UnsupportedRegionError: 후보가 없고 '리' 단위 이름일 때.
        RegionNotFoundError: 그 밖에 후보가 없을 때.
        RegionAmbiguousError: 같은 이름의 동이 여러 곳일 때.
    """
    # 앞뒤 공백이 남으면 동 이름과 정확히 같은 후보가 없어 같은 이름 동 검사를 건너뛰고 첫 후보를 고른다
    # (2026-10-18 실측: '신사동 ' 은 REGION_AMBIGUOUS 없이 강남구 신사동으로 조회했다)
    query = query.strip()
    candidates = search_locations(client, query)
    if city:
        candidates = [location for location in candidates if place_in(city, location.name1, location.name2)]
    if not candidates:
        if query.endswith('리'):
            raise ri_region_error(query)
        # 당근은 동·읍·면 이름으로만 찾고 좌표 옵션이 없어 기본 힌트(역 이름, --lat/--lng)가 맞지 않는다
        raise RegionNotFoundError(
            query,
            hint="동·읍·면 이름(예: '역삼동')으로 다시 검색하세요. 'jibsa daangn search locations <이름>' 으로 후보를 확인할 수 있습니다",
        )
    exact = list({location.id: location for location in candidates if location.name3 == query}.values())
    if len(exact) > 1:
        exact = _dongs_with_map(client, exact, notes) or exact[:1]
    if len(exact) > 1:
        raise RegionAmbiguousError(
            query,
            [
                join_address(location.name1, location.name2, location.name3) or query
                for location in exact[:AMBIGUOUS_CANDIDATES_SHOWN]
            ],
            len(exact),
            hint=_narrow_city_hint(city, exact[0].name2 or exact[0].name1 or ''),
        )
    if merge_ga and not exact:
        siblings = _ga_dong_siblings(query, candidates)
        if len(siblings) > 1:
            return siblings
    primary = exact[0] if exact else candidates[0]
    # name1 이 비면 지도 요청 모델(min_length=1)이 입력 오류(INVALID_ARGUMENT)로 내지만, 비어 오는 일이 없어 막지 않는다
    # (2026-10-11 실측: 이름 12개로 받은 후보 154곳, 시·도 16곳 모두 name1 있음. name2 는 구가 없는 세종만 빈 문자열이고
    # 요청 모델이 받는다). 2026-10-11 리뷰 오탐 확인
    region = DaangnRegion(
        name1=primary.name1 or '',
        name2=primary.name2 or '',
        name3=primary.name3 or primary.name,
        region_id=primary.id,
    )
    if notes is not None:
        # 당근은 리를 상위 읍·면으로 준다. 원본에 리 이름이 없고 이름이 비슷한 동도 섞여 와서, 리가 있을 수 있는
        # 읍·면 후보만 같은 이름의 리로 센다 (2026-10-10 실측: '오리' 는 퇴촌면·장안읍 등 읍·면 7곳과 여수 오림동)
        same_ri = [
            join_address(location.name1, location.name2, location.name3, query) or query
            for location in {location.id: location for location in candidates}.values()
            if query.endswith('리') and location.id != primary.id and (location.name3 or '').endswith(('읍', '면'))
        ]
        notes += region_notes(query, region, same_ri=same_ri, station_hint=station_hint)
    return [region]


def _ga_dong_siblings(query: str, candidates: list[DaangnLocationModel]) -> list[DaangnRegion]:
    """'○가' 로 나뉜 동(성수동 → 성수동1가·성수동2가)을 '가' 번호 순으로 준다. 첫 후보와 같은 시·구만 센다.

    당근 지역 검색은 '성수동' 에 두 동을 함께 주는데 예전에는 첫 후보(성수동2가)만 찾아 1가 매물이 빠졌다 (2026-10-15
    실측). 직방·네이버처럼 모두 찾는다 (`search_listings` 가 동 피드를 시각 순으로 합친다).
    """
    pattern = re.compile(rf'{re.escape(query.split()[-1])}(\d+)가')
    found: dict[int, tuple[int, DaangnLocationModel]] = {}
    for location in candidates:
        match = pattern.fullmatch(location.name3 or '')
        if match is not None:
            found.setdefault(location.id, (int(match.group(1)), location))
    if not found:
        return []
    ordered = sorted(found.values(), key=lambda entry: entry[0])
    parent = (ordered[0][1].name1, ordered[0][1].name2)
    return [
        DaangnRegion(name1=location.name1 or '', name2=location.name2 or '', name3=location.name3 or '', region_id=location.id)
        for _, location in ordered
        if (location.name1, location.name2) == parent
    ]


def _dongs_with_map(
    client: DaangnClient,
    locations: list[DaangnLocationModel],
    notes: list[str] | None = None,
) -> list[DaangnLocationModel]:
    """같은 이름 동 후보 중 당근 매물 지도가 있는 곳(법정동)만 남긴다. 앞 `AMBIGUOUS_CANDIDATES_SHOWN` 곳만 지도를 1회씩 본다.

    당근 지역 검색은 행정동도 같은 이름 후보로 주는데(역삼동 → 강남구 역삼동, 용인시 처인구 역삼동) 매물 지도는 법정동만
    있어 행정동 지도는 404 다 (2026-10-15 실측: 처인구 역삼동·관악구 신사동). 직방·네이버는 역삼동을 한 곳으로 보니, 지도가
    있는 곳만 세어야 소스끼리 같은 이름을 같게 센다. 404 가 아닌 오류(서버 오류·페이지 구조가 바뀌어 읽지 못함)로 확인하지
    못한 후보는 남기고 `notes` 로 알리며, 보지 않은 뒤쪽 후보도 남긴다. 실거래·단지 목록·후기는 지도 페이지를 쓰지 않아, 이 확인이
    실패했다고 명령까지 실패하면 안 된다. 요청 제한과 연결 실패·시간 초과는 다음 요청도 같은 이유로 실패해 바로 올린다.
    남기면 같은 이름 후보로 멈춰(REGION_AMBIGUOUS) 원인이 가려지고, 응답 없는 서버를 후보마다 재시도하며 기다린다.

    Raises:
        RateLimitedError: 지도 페이지 차례에 요청 제한에 걸렸을 때.
        TransportError: 재시도 뒤에도 연결 실패·시간 초과일 때.
    """
    kept: list[DaangnLocationModel] = []
    for location in locations[:AMBIGUOUS_CANDIDATES_SHOWN]:
        try:
            client.run_request_map(DaangnMapRequestParameterModel(
                name1=location.name1 or '', name2=location.name2 or '', name3=location.name3 or location.name,
            ))
        except (RateLimitedError, TransportError):
            raise
        except OPTIONAL_LOOKUP_ERRORS as exc:
            if isinstance(exc, HTTPStatusError) and exc.response.status_code == 404:
                continue
            name = join_address(location.name1, location.name2, location.name3) or location.name
            logger.warning('daangn map page check for %r failed (%s); keeping the candidate', name, exc)
            if notes is not None:
                notes.append(note('실패', partial_failure_note(exc, '매물 지도', f'{name}에 매물 지도가 있는지 확인한 결과를')))
        kept.append(location)
    return kept + locations[AMBIGUOUS_CANDIDATES_SHOWN:]


def _narrow_city_hint(city: str | None, example: str) -> str:
    """같은 이름 지역으로 멈출 때 다시 묻는 법. `example` 은 첫 후보의 구(동일 때)나 시·도(구일 때)다."""
    if city:
        return f"--city '{city}' 에도 여러 곳이 맞습니다. 구 이름으로 좁히세요 (예: --city {example})"
    return f'--city 로 시·도나 구를 지정하세요 (예: --city {example})'


def region_notes(
    query: str,
    region: DaangnRegion,
    *,
    same_ri: list[str] | None = None,
    station_hint: bool = False,
) -> list[str]:
    """조회한 당근 동이 검색어와 다를 때 결과에 붙일 안내 (`resolve_regions` 가 붙인다). 안내는 하나로 낸다.

    리는 당근이 상위 읍·면으로 찾아 주므로(양근리 → 양평읍) 결과가 그 리 안의 매물만이
    아니다. 이름이 바뀐 동(이도이동 → 이도2동)도 엉뚱한 곳으로 오해하지 않도록 알린다.
    같은 이름의 리가 다른 곳에도 있으면(`same_ri`, '시·도 시·군·구 읍·면 리') 그곳과 `--city` 를 알린다.
    역 이름도 받는 명령(search listings)은 `station_hint` 로 리 이름이 역 이름과 겹칠 수 있다고 덧붙인다
    (2026-10-10 실측: 가오리 → 부안군 상서면 (가오리역은 서울 강북구), 오리 → 광주시 퇴촌면 (오리역은 성남 분당)).
    """
    if region.name3 == query:
        return []
    # 세종은 시·군·구가 없어 name2 가 '' 라 시·도를 쓴다 (2026-10-11 실측: 용포리 → '상위 지역인  금남면' 으로 앞이 비었다)
    place = f'{region.name2 or region.name1} {region.name3}'
    elsewhere = ''
    if same_ri:
        more = ' 등' if len(same_ri) > 3 else ''
        elsewhere = (
            f". 같은 이름의 리가 다른 곳에도 있으니({', '.join(same_ri[:3])}{more}) "
            '그곳이면 --city 로 시·도나 구를 지정하세요'
        )
    # 리는 읍·면 아래에만 있다. 동으로 찾았으면(청량리 → 청량리동) 리가 아니라 이름이 비슷한 동이다
    if query.endswith('리') and region.name3.endswith(('읍', '면')):
        ri_note = (
            f"당근에는 리 단위 지역이 없어 상위 지역인 {place} 전체 매물로 조회했습니다 (검색어 '{query}'). "
            f'{query} 안의 매물만이 아닙니다'
        ) + elsewhere
        if station_hint:
            ri_note += f". 역을 찾았다면 '{query}역' 처럼 '역'을 붙여 다시 검색하세요"
        return [note('범위', ri_note)]
    return [note('범위', f"당근에서는 {place} 기준으로 조회했습니다 (검색어 '{query}')" + elsewhere)]


def with_sido(
    client: DaangnClient,
    article: DaangnArticleModel,
    cache: dict[tuple[str, str], str | None],
) -> DaangnArticleModel:
    """시·도(`region.name1`)가 빠진 매물에 당근 지역 검색으로 시·도를 채운다.

    피드에 섞여 온 주변 동 매물은 시·도 없이 오기도 한다 ('고양시 덕양구 향동동'). 동마다
    한 번만 검색하고, 찾지 못하거나 검색이 실패하면 그대로 둔다 (주소가 시·군·구부터 나온다).
    요청 제한(`RateLimitedError`)도 실패로 보고 넘어간다. 주소를 다듬다 받아 둔 매물을 잃지 않기 위함이다.
    세종은 시·군·구가 없어 name2 가 '' 로 오는데(2026-10-11 실측: 매물·지역 검색 모두) 그때도 채운다. 빼면 주소가
    '반곡동' 처럼 동만 나간다.
    """
    region = article.region
    if region is None or region.name1 or not region.name3:
        return article
    name1 = sido_of(client, region.name2 or '', region.name3, cache)
    if name1 is None:
        return article
    return article.model_copy(update={'region': region.model_copy(update={'name1': name1})})


def with_center_sido(
    client: DaangnClient,
    article: DaangnArticleModel,
    center: DaangnRegion | None,
    cache: dict[tuple[str, str], str | None],
) -> DaangnArticleModel:
    """검색 중심 동(`center`)과 구 이름이 같은 매물은 중심 동의 시·도로, 나머지는 `with_sido` 로 채운다.

    역·반경·출퇴근·인기 매물 카드에는 시·도가 없다. 검색 중심 가까이의 매물이라 구 이름이 같으면 같은 시·도로
    보고 지역 검색을 하지 않는다. 이름이 같은 다른 시·도의 구까지 닿지 않는 이유는 부르는 곳에 적었다.
    """
    known = article.region
    if center is not None and known is not None and (known.name2 or '') == center.name2 and known.name3:
        cache.setdefault((known.name2 or '', known.name3), center.name1)
    return with_sido(client, article, cache)


def sido_of(
    client: DaangnClient,
    name2: str,
    name3: str,
    cache: dict[tuple[str, str], str | None],
) -> str | None:
    """구·동 이름으로 시·도를 찾는다. 동마다 한 번만 검색하고, 실패하면(요청 제한 포함) None."""
    key = (name2, name3)
    if key not in cache:
        try:
            locations = search_locations(client, name3)
        except OPTIONAL_LOOKUP_ERRORS:
            locations = []
        cache[key] = next(
            (location.name1 for location in locations if location.name2 == name2 and location.name1),
            None,
        )
    return cache[key]


def region_by_coordinate(client: DaangnClient, lat: float, lng: float) -> DaangnRegion:
    """좌표가 속한 당근 동을 찾는다 (`getRegionByCoordinate`).

    Raises:
        UnsupportedRegionError: 좌표가 동에 속하지 않을 때 (바다 등).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_get_region_by_coordinate(
        DaangnGetRegionByCoordinateRequestPayloadModel(
            coordinate=DaangnCoordinateInputModel(lat=lat, lon=lng)
        )
    )
    found = response.data.get_region_by_coordinate if response.data else None
    if not response.errors and (found is None or found.depth != 3 or not found.name3 or found.original_id is None):
        raise UnsupportedRegionError(
            code='REGION_NOT_FOUND',
            message=f'좌표 ({lat}, {lng}) 가 속한 당근 동을 찾지 못했습니다',
            hint='육지 안의 좌표를 주거나 동 이름으로 검색하세요',
            skip_note=f'daangn 은 좌표 ({lat}, {lng}) 가 속한 동을 찾지 못해 건너뛰었습니다',
        )
    region = unwrap_graphql(response, found, '좌표 지역')
    return DaangnRegion(
        name1=region.name1 or '',
        name2=region.name2 or '',
        name3=region.name3 or '',
        region_id=region.original_id or 0,
    )


def region_or_none(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    notes: list[str] | None = None,
) -> DaangnRegion | None:
    """좌표가 속한 당근 동 (`region_by_coordinate`). 찾지 못하거나 조회가 실패하면 None.

    결과 표시와 시·도 채우기에만 쓰는 곳에서 부른다. 요청 제한도 실패로 보고 넘어간다
    (`with_sido` 와 같다). 받아 둔 매물을 동 이름 때문에 잃지 않기 위함이다. 동을 결과에 내보내는
    곳(반경 검색의 `region`)은 `notes` 를 넘겨, 동이 null 인 이유를 알린다 (`partial_failure_note`).
    시·도 채우기에만 쓰는 곳은 결과에 빠지는 게 없어(시·도는 `with_sido` 가 다시 찾는다) 넘기지 않는다.
    """
    try:
        return region_by_coordinate(client, lat, lng)
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn region of coordinate (%s, %s) not found (%s); continuing without region', lat, lng, exc)
        if notes is not None:
            notes.append(note('실패', partial_failure_note(exc, '좌표 지역', '검색 중심의 동 이름을')))
        return None


def map_query_rejected_error() -> JibsaError:
    """좌표 검색(`region_by_coordinate`, `search_area`)의 쿼리 해시가 거절됐을 때의 CLI 에러."""
    return JibsaError(
        code='UPSTREAM_ERROR',
        message='당근 지도 API 가 바뀌어(웹 쿼리 해시 거절) 좌표로 조회할 수 없습니다',
        hint="동 이름으로 검색하세요 (예: 'jibsa daangn search listings 역삼동'). jibsa 업데이트가 필요합니다",
    )


def bounds_around(lat: float, lng: float, radius_km: float) -> DaangnBoundsLocationFilterModel:
    """반경을 감싸는 좌표 범위."""
    south, north, west, east = box_around(lat, lng, radius_km)
    return DaangnBoundsLocationFilterModel(
        ne_coordinate=DaangnCoordinateInputModel(lat=north, lon=east),
        sw_coordinate=DaangnCoordinateInputModel(lat=south, lon=west),
    )


# 역 주변 매물은 요청당 100건까지 준다 (2026-10-10 실측: first=200 이어도 100건)
STATION_PAGE_SIZE: int = 100


def station_article_edges(
    fetch: Callable[[int, str | None], DaangnCommuteStationArticleConnectionModel],
    limit: int,
    *,
    after: str | None = None,
) -> tuple[list[DaangnCommuteArticleEdgeModel], bool, str | None]:
    """역 주변 매물을 `STATION_PAGE_SIZE` 건씩 `limit` 건까지 이어 받는다. 역 주변 목록과 출퇴근 역별 매물이 함께 쓴다.

    받은 수로 예산을 세고 뺄 매물을 채우지 않는다. limit 최대 120 이라 요청 2번 안에 끝나 커서 반복 검사를 두지 않는다.

    Args:
        fetch: (받을 수, 커서) → 한 페이지.
        limit: 최대 매물 수.
        after: 이어 받기(`--next`)에서 시작할 커서. 없으면 처음부터.

    Returns:
        (받은 edge, 서버에 더 있는지, 다음 페이지 커서).
    """
    edges: list[DaangnCommuteArticleEdgeModel] = []
    has_more = False
    while len(edges) < limit:
        connection = fetch(min(STATION_PAGE_SIZE, limit - len(edges)), after)
        edges += connection.edges
        page_info = connection.page_info
        has_more = bool(page_info and page_info.has_next_page and page_info.end_cursor)
        after = page_info.end_cursor if page_info else None
        if not connection.edges or not has_more:
            break
    return edges, has_more, after


class DaangnStation(BaseModel):
    """당근 역 검색으로 찾은 지하철역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지, 예: 역삼역)")
    ]
    lines: Annotated[
        list[str],
        Field(description='노선 (예: 서울2호선)')
    ]
    lat: Annotated[
        float,
        Field(description='역 위도')
    ]
    lng: Annotated[
        float,
        Field(description='역 경도')
    ]
    station_id: Annotated[
        str,
        Field(exclude=True, description='당근 역 ID (역 주변 매물 조회에 쓴다)')
    ]
    others: Annotated[
        list[str],
        Field(exclude=True, description="이름이 같아 고르지 않은 다른 역 ('서울5호선 양평역'). 안내에 쓴다")
    ] = []


class DaangnPlace(BaseModel):
    """당근 역·주소 검색으로 찾은 위치."""

    name: Annotated[
        str,
        Field(description='찾은 이름 (역 이름 또는 도로명 주소)')
    ]
    lat: float
    lng: float
    notes: Annotated[
        list[str],
        Field(description='이름이 같은 다른 역 안내')
    ] = []


def _station_label(lines: list[str], name: str) -> str:
    """노선을 붙인 역 이름 ('서울5호선 양평역'). 같은 이름의 역을 노선으로 구분한다."""
    return ' '.join(part for part in ('·'.join(lines), station_name(name)) if part)


def same_station_notes(station: DaangnStation, hint: str) -> list[str]:
    """같은 이름의 역이 여러 곳이라 첫 역으로 찾았을 때의 안내. `hint` 는 다른 역을 고르는 방법이다."""
    if not station.others:
        return []
    return [note(
        '모호',
        f"{quoted(station.name, '이/가')} 여러 곳이라 {_station_label(station.lines, station.name)} 기준으로 찾았습니다 "
        f"(다른 곳: {', '.join(station.others)}). {hint}",
    )]


def _station_in_city(
    client: DaangnClient,
    stations: list[DaangnSubwayStationPoiModel],
    city: str,
    name: str,
) -> DaangnSubwayStationPoiModel:
    """`city` 에 있는 첫 역. 역 검색에는 주소가 없어 역 좌표가 속한 동을 찾아 본다 (`region_by_coordinate`, 역마다 1회).

    Raises:
        RegionNotFoundError: `city` 에 맞는 역이 없을 때. 같은 이름 역이 있는 곳을 힌트로 준다.
    """
    places: list[str] = []
    for station in stations:
        assert station.coordinate is not None and station.coordinate.lat is not None and station.coordinate.lon is not None
        region = region_by_coordinate(client, station.coordinate.lat, station.coordinate.lon)
        if place_in(city, region.name1, region.name2):
            return station
        places.append(f'{_station_label(station.line_names, station.station_name)}({region.name1} {region.name2})')
    raise RegionNotFoundError(
        name,
        hint=f"{quoted(name, '은/는')} {', '.join(places)} 에 있어 --city '{city}' 에 맞는 역이 없습니다. --city 를 바꾸거나 빼 보세요",
    )


def find_station(client: DaangnClient, name: str, *, city: str | None = None) -> DaangnStation | None:
    """이름이 지하철역이면 그 역을 돌려준다 (`searchSubwayStationPois`). 이름이 정확히 같은 역만 본다.

    역 검색은 앞부분이 같은 역을 모두 주므로 ('강남' → 강남구청, 강남대), '역' 을 뗀 이름이 같은 역만 고른다.
    같은 이름의 역이 여러 곳이면 (2026-10-11 실측: 양평 → 경의중앙선·서울5호선, 중앙 → 서울4호선·부산1호선) 처음 것을
    쓰고 (당근 웹도 첫 결과로 연다) 다른 역을 `others` 에 담는다. `city` 를 주면 그 시·도·구에 있는 첫 역을 쓴다
    (`_station_in_city`, 역마다 요청 1회).

    Raises:
        RegionNotFoundError: `city` 에 맞는 역이 없을 때.
    """
    query = name.strip().removesuffix('역')
    if not query:
        return None
    response = client.run_request_search_subway_station_pois(
        DaangnSearchSubwayStationPoisRequestPayloadModel(input=DaangnQueryInputModel(query=query))
    )
    stations = unwrap_graphql(
        response,
        response.data.search_subway_station_pois if response.data else None,
        '역 검색',
    )
    same = [
        station for station in stations
        if station.station_name == query and station.coordinate
        and station.coordinate.lat is not None and station.coordinate.lon is not None
    ]
    if not same:
        return None
    chosen = _station_in_city(client, same, city, name) if city is not None else same[0]
    assert chosen.coordinate is not None and chosen.coordinate.lat is not None and chosen.coordinate.lon is not None
    return DaangnStation(
        name=station_name(chosen.station_name),
        lines=chosen.line_names,
        lat=chosen.coordinate.lat,
        lng=chosen.coordinate.lon,
        station_id=chosen.id,
        # --city 로 골랐으면 다른 역을 알리지 않는다
        others=[] if city is not None else [
            _station_label(station.line_names, station.station_name) for station in same[1:]
        ],
    )


def _address_matches(query: str, address: DaangnAddressModel) -> bool:
    """주소 검색 후보가 검색어가 가리키는 곳인지.

    검색어 끝이 도로명(`…로/길 번호`)이나 지번(`…동/가/리/읍/면 번지`)이면 번호까지 같은 후보만 맞다고
    본다 ('테헤란로 15' 에 '테헤란로2길 15' 는 아니다). 앞에 붙인 시·구('서울 강남구', '서울시 강남구')도 후보
    주소에 있어야 한다 (시·도 줄임말 포함, `place_in`). 주소 모양이 아니면 지번 주소 끝의 건물 이름이 검색어와
    같은 후보만 맞다 ('63빌딩' 에 'PA63빌딩' 은 아니다). 동 이름만 주면 주소 검색은 번지·건물 이름이 붙은 주소만
    줘서 ('서울특별시 강남구 신사동 523-4 신사동씨티빌') 여기서 맞지 않고 직방으로 넘어간다
    (2026-10-10 실측: 신사동·중앙동 각 10건).
    """
    road = re.sub(r'\s*\(.*\)$', '', address.road_address or '')
    # 산 번지는 '산 12'·'산12' 를 같게 본다
    lot = re.sub(r'산\s+(\d)', r'산\1', address.region_address or '')
    if found := ROAD_ADDRESS_PATTERN.search(query):
        text = road
    elif found := LOT_ADDRESS_PATTERN.search(query):
        text = lot
    else:
        return lot.endswith(f' {query}')
    number = re.escape(found['number'].replace(' ', ''))
    if not re.search(rf'(^|\s){re.escape(found["key"])}\s*{number}(\s|$)', text):
        return False
    return all(place_in(token, lot, road) for token in query[:found.start()].split())


def find_place(client: DaangnClient, name: str) -> DaangnPlace | None:
    """역 이름이나 주소·건물 이름을 당근 검색으로 좌표로 바꾼다. 확실하지 않으면 None.

    역은 이름이 같은 역만 쓰고 (`find_station`), 역이 아니면 주소 검색으로 찾는다 (`find_address`).
    요청은 많아야 3회다.

    Raises:
        RegionAmbiguousError: 검색어에 맞는 주소가 여러 시·군·구에 있을 때.
    """
    station = find_station(client, name)
    if station is not None:
        return DaangnPlace(
            name=station.name,
            lat=station.lat,
            lng=station.lng,
            notes=same_station_notes(station, '다른 역이면 --lat/--lng 로 그 위치를 주세요'),
        )
    return find_address(client, name)


def find_address(client: DaangnClient, name: str) -> DaangnPlace | None:
    """주소·건물 이름을 당근 주소 검색으로 좌표로 바꾼다. 확실하지 않으면 None. 역 검색을 이미 했으면 이것만 부른다.

    주소 검색(`searchAddress`)은 건물 이름도 찾지만 비슷한 이름을 먼저 주기도 해서 (2026-10-10 실측: 연세대학교 →
    아산 '연세대학교 연세유업', 고려대학교 → '고려대학교구로병원', 63빌딩 → 'PA63빌딩', 테헤란로 15 → '테헤란로2길 15')
    검색어가 가리키는 곳과 같은 결과만 쓴다 (`_address_matches`). 맞는 결과가 여러 시·군·구에 있으면 고르지 않는다
    ('중앙로 1' 은 10곳 넘게 나온다). 그 결과의 도로명 주소를 `geocodeAddress` 로 좌표로 바꾼다. 요청은 많아야 2회다.

    Raises:
        RegionAmbiguousError: 검색어에 맞는 주소가 여러 시·군·구에 있을 때.
    """
    query = name.strip()
    response = client.run_request_search_address(
        DaangnSearchAddressRequestPayloadModel(input=DaangnQueryInputModel(query=query), first=ADDRESS_SEARCH_SIZE)
    )
    found = unwrap_graphql(response, response.data.search_address if response.data else None, '주소 검색')
    addresses = [edge.node for edge in found.edges if edge.node is not None and _address_matches(query, edge.node)]
    if not addresses:
        return None
    # 시·도와 시·군·구 (지번 주소 앞 두 마디). 일반구('창원시 성산구')는 시 하나로 묶이지만, 한 시 안에서는
    # 도로명·동 이름이 겹치지 않아 두 구가 함께 맞는 결과는 없었다 (2026-10-10 실측: 창원 중앙동, 천안 송정리,
    # 포항 신흥리). 세 마디로 늘리면 서울처럼 구 다음이 동인 곳은 같은 구도 동마다 다른 곳으로 센다
    areas: dict[str, DaangnAddressModel] = {}
    for candidate in addresses:
        areas.setdefault(' '.join((candidate.region_address or '').split()[:2]), candidate)
    if len(areas) > 1:
        error = RegionAmbiguousError(
            query,
            [candidate.road_address or candidate.region_address or '' for candidate in areas.values()][:5],
            len(areas),
        )
        if found.page_info and found.page_info.has_next_page:
            # 받은 후보만 세었다. 더 있을 수 있다
            error.message = f"'{query}' 에 해당하는 곳이 {len(areas)}곳 이상입니다"
        raise error
    address = addresses[0]
    # 도로명 주소의 괄호(동·건물 이름)는 좌표 변환이 받지 않는다
    road = re.sub(r'\s*\(.*\)$', '', address.road_address or '') or address.region_address
    if not road:
        return None
    geocode_response = client.run_request_geocode_address(DaangnGeocodeAddressRequestPayloadModel(query=road))
    geocoded = unwrap_graphql(geocode_response, geocode_response.data.geocode_address if geocode_response.data else None, '주소 좌표')
    point = geocoded.point
    if point is None or point.lat is None or point.lon is None:
        return None
    return DaangnPlace(name=address.road_address or road, lat=point.lat, lng=point.lon)


class DaangnRealsaleRegion(BaseModel):
    """지역 실거래를 조회한 동 또는 구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="지역 이름 (예: '서울특별시 강남구 역삼동', '서울특별시 강남구')")
    ]
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]
    level: Annotated[
        Literal['동', '구'],
        Field(description='동(읍·면 포함) 또는 구(시·군 포함, 구가 없는 세종은 세종특별자치시 전체)')
    ]
    name1: Annotated[
        str,
        Field(exclude=True, description='시/도. 후기 페이지 경로에 쓴다')
    ] = ''
    name2: Annotated[
        str,
        Field(exclude=True, description='시/군/구. 후기 페이지 경로에 쓴다')
    ] = ''
    name3: Annotated[
        str,
        Field(exclude=True, description='읍/면/동 (동일 때만)')
    ] = ''


def _sejong_realsale_region(client: DaangnClient, query: str, whole: bool) -> tuple[DaangnRealsaleRegion, list[str]]:
    """세종 전체를 시·도 ID 로 고른다 (`resolve_realsale_region`). `whole` 이 아니면 동 이름으로 다시 묻는다.

    '세종시'·'세종특별자치시' 는 지역 검색이 빈 목록이라 '세종' 으로 찾는다 (2026-10-11 실측: '세종' 은 세종 읍·면·동을 준다).
    """
    dongs = [location for location in search_locations(client, '세종') if location.name1 == '세종특별자치시']
    sido_id = next((location.name1_id for location in dongs if location.name1_id), None)
    if whole and sido_id is not None:
        return (
            DaangnRealsaleRegion(name='세종특별자치시', region_id=sido_id, level='구', name1='세종특별자치시'),
            ['세종은 구가 없어 세종특별자치시 전체로 조회했습니다'],
        )
    names = list(dict.fromkeys(location.name3 for location in dongs if location.name3))
    shown = names[:5]
    raise JibsaError(
        code='REGION_AMBIGUOUS',
        message=f"{quoted(query, '은/는')} 구가 없는 시라 시 전체로는 조회할 수 없습니다",
        hint=(
            f"세종의 동 이름으로 다시 주세요 (예: '{shown[0]}'). 찾은 동: {', '.join(shown)}{' 등' if len(names) > len(shown) else ''}"
            if shown else "세종의 동 이름(예: '반곡동')으로 다시 주세요"
        ),
        details={'candidates': shown, 'candidate_count': len(names)},
    )


def resolve_realsale_region(
    client: DaangnClient,
    query: str,
    *,
    city: str | None = None,
    sejong_whole: bool = False,
) -> tuple[DaangnRealsaleRegion, list[str]]:
    """지역 실거래를 볼 동 또는 구를 고른다.

    동 이름과 같은 후보가 있으면 그 동, 아니면 시/군/구 이름과 같은 구를 쓴다. 같은 이름이 여러 곳이면
    고르지 않고 후보와 `--city` 를 알리며 멈춘다 (`resolve_regions` 와 같다).

    세종(세종·세종시·세종특별자치시)은 시·군·구가 없어 예전에는 첫 동(조치원읍)으로 대신 찾았다. 세종 시·도 ID 로 부르면
    실거래는 세종 전체가 오지만 단지 목록은 0건이고 구 후기 페이지도 없다 (2026-10-11 실측: ID 1241 실거래 50건이 도담동·
    나성동 등 여러 동, 단지 목록 0건). 그래서 `sejong_whole` 이면 세종 전체로 고르고, 아니면 동 이름으로 다시 묻는다.

    Raises:
        RegionNotFoundError: 후보가 없을 때.
        RegionAmbiguousError: 같은 이름의 동·구가 여러 곳일 때.
        JibsaError: 구가 있는 시('수원시')나 세종 전체를 받을 수 없을 때 REGION_AMBIGUOUS.
    """
    if SIDO_OFFICIAL_NAMES.get(query, query) == '세종특별자치시':
        return _sejong_realsale_region(client, query, sejong_whole)
    candidates = search_locations(client, query)
    if city:
        candidates = [location for location in candidates if place_in(city, location.name1, location.name2)]
    if not candidates:
        raise RegionNotFoundError(
            query,
            hint="동 이름(예: '역삼동')이나 구 이름(예: '강남구')으로 다시 찾으세요. 같은 이름이 여러 곳이면 --city 로 좁힙니다",
        )

    # regions/keyword 는 같은 id 를 두 번 주지 않아 중복을 빼지 않는다. 같은 이름 후보는 서로 다른 지역이다
    # (2026-10-11 실측: 역삼동 2곳·신사동 3곳·중앙동 58곳·송정동 14곳·오리 8곳 모두 id 중복 없음)
    notes: list[str] = []
    dongs = [location for location in candidates if location.name3 == query]
    if len(dongs) > 1:
        dongs = _dongs_with_map(client, dongs, notes) or dongs[:1]
    if dongs:
        options = [
            (DaangnRealsaleRegion(
                name=join_address(location.name1, location.name2, location.name3) or query,
                region_id=location.id,
                level='동',
                name1=location.name1 or '',
                name2=location.name2 or '',
                name3=location.name3 or '',
            ))
            for location in dongs
        ]
    else:
        gus: dict[int, DaangnRealsaleRegion] = {}
        for location in candidates:
            name2 = location.name2 or ''
            if location.name2_id and (name2 == query or name2.endswith(f' {query}')):
                gus.setdefault(location.name2_id, DaangnRealsaleRegion(
                    name=join_address(location.name1, name2) or query,
                    region_id=location.name2_id,
                    level='구',
                    name1=location.name1 or '',
                    name2=name2,
                ))
        options = list(gus.values())

    if not options:
        # 구가 있는 시('수원시')는 이름이 같은 구가 없고 '수원시 팔달구' 처럼 시 이름이 붙은 구만 온다. 동 하나로 대신 찾으면
        # 시를 물었는데 동 하나의 결과가 나와(2026-10-11 실측: 수원시 → 인계동) 구를 골라 다시 묻게 한다
        city_gus = list(dict.fromkeys(
            location.name2 for location in candidates if location.name2 and location.name2.startswith(f'{query} ')
        ))
        if city_gus:
            more = ' 등' if len(candidates) >= REGION_KEYWORD_MAX_RESULTS else ''
            raise JibsaError(
                code='REGION_AMBIGUOUS',
                message=f"{quoted(query, '은/는')} 구가 있는 시라 시 전체로는 조회할 수 없습니다",
                hint=f"구 이름으로 다시 주세요 (예: '{city_gus[0]}'). 찾은 구: {', '.join(city_gus)}{more}",
                details={'candidates': city_gus, 'candidate_count': len(city_gus)},
            )
        first = candidates[0]
        options = [DaangnRealsaleRegion(
            name=join_address(first.name1, first.name2, first.name3) or query,
            region_id=first.id,
            level='동',
            name1=first.name1 or '',
            name2=first.name2 or '',
            name3=first.name3 or first.name,
        )]
        notes.append(note('범위', f"{quoted(query, '과/와')} 이름이 같은 동·구가 없어 {options[0].name} 기준으로 조회했습니다"))
    elif len(options) > 1:
        # 첫 곳으로 찾으면 다른 소스와 다른 곳을 찾는다 (resolve_regions 와 같은 이유). 구는 시·도로 좁힌다 (중구 → --city 서울)
        top = options[0]
        raise RegionAmbiguousError(
            query,
            [option.name for option in options[:AMBIGUOUS_CANDIDATES_SHOWN]],
            len(options),
            hint=_narrow_city_hint(city, top.name2 if top.level == '동' else top.name1),
        )
    return options[0], notes
