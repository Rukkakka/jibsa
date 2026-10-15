"""매물 검색 조건과 동·반경·역 주변 매물 검색 (search listings)."""

import logging
import re
from collections import Counter

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    UnsupportedRegionError,
)
from jibsa.core.geo import (
    haversine_km,
    within_radius,
)
from jibsa.core.korean import (
    ADMIN_DONG_NUMBER,
    legal_dong_hint,
    particle,
)
from jibsa.core.listing import (
    Listing,
    beyond_radius_notes,
    listing_as,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnLocationFilterModel,
    DaangnPropertyFilterModel,
)
from jibsa.providers.daangn.api.request.search import (
    DaangnArticleFeedInputModel,
    DaangnArticleFeedRequestPayloadModel,
    DaangnArticleMapPointsInputModel,
    DaangnArticleMapPointsRequestPayloadModel,
    DaangnArticlesByOriginalArticleIdsRequestPayloadModel,
    DaangnArticlesCountInputModel,
    DaangnArticlesCountRequestPayloadModel,
    DaangnMapRequestParameterModel,
    DaangnSubwayStationArticleConnectionRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.api.response.region import DaangnLocationModel
from jibsa.providers.daangn.api.response.search import (
    DaangnArticleFeedModel,
    DaangnArticleFeedResponseModel,
    DaangnArticlePointModel,
    DaangnMapResponseModel,
)
from jibsa.providers.daangn.service.common import (
    OPTIONAL_LOOKUP_ERRORS,
    DaangnListingConditions,
    DaangnRegion,
    FeedQueryRejectedError,
    article_to_listing,
    complex_building_notes,
    is_available,
    listing_budget_notes,
    partial_failure_note,
    trade_of,
    trade_unselected_notes,
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnStation,
    bounds_around,
    region_or_none,
    search_locations,
    sido_of,
    station_article_edges,
    with_center_sido,
    with_sido,
)

from typing import (
    Annotated,
    Literal,
)


logger = logging.getLogger(__name__)
# 당근 매물 종류는 작성자가 고른 하나뿐이라 같은 오피스텔 건물의 방 1개도 원룸·오피스텔로 갈린다
# (2026-10-10 실측: 엘리젠트 단지 매물 3건 중 1건만 원룸, 2건은 오피스텔로 올라 있었다)
ONE_ROOM_NOTE: str = (
    '-t 원룸은 작성자가 원룸으로 올린 매물만이라 방 1개 아파트·주택은 빠지고 방 2개 매물이 섞일 수 있습니다 '
    '(방 수는 --details 나 listing 의 room_type)'
)
ONE_ROOM_OFFICETEL_NOTE: str = '원룸형 오피스텔도 보려면 -t 원룸,오피스텔'
OFFICETEL_NOTE: str = (
    '-t 오피스텔은 작성자가 오피스텔로 올린 매물만이라 원룸으로 올린 오피스텔은 빠집니다 (함께 보려면 -t 원룸,오피스텔)'
)
# 투룸(TWO_ROOM)으로 찾을 때 붙이는 안내
TWO_ROOM_NOTE: str = (
    '-t 투룸은 투룸 이상(쓰리룸·포룸이상 포함)을 함께 찾습니다. 방 구조는 매물의 room_type 으로 확인하고, '
    'null 이면(당근 목록) item 의 room_count 로 확인하세요'
)
FEED_PAGE_SIZE: int = 20
# 동마다 받는 피드 페이지 상한 (첫 페이지 포함). 동마다 최대 120건이다
MAX_FEED_PAGES: int = 6
# 지도 번호의 정보를 20개씩 조회하며 요청한 ID 수를 조회 예산으로 계산한다.
CARD_CHUNK_SIZE: int = 20
# 핀은 넓은 범위에서 이 개수로 잘린다 (2026-10 실측). 잘리면 어떤 핀이 빠졌는지 알 수 없다
PIN_LIMIT: int = 10000
FEED_FALLBACK_NOTE: str = (
    '당근 필터 API 를 쓸 수 없어(웹 쿼리가 바뀜) 예전 방식으로 동마다 최근 20건만 받아 조건을 적용했습니다. '
    '조건에 맞는 매물이 더 있을 수 있으니 jibsa 를 업데이트하세요'
)
# 조건 없이 찾다가 다음 페이지 피드가 거절됐을 때. 건 조건이 없어 '조건을 적용했다' 고 하지 않는다
FEED_FALLBACK_PLAIN_NOTE: str = (
    '당근 매물 피드 API 를 쓸 수 없어(웹 쿼리가 바뀜) 예전 방식으로 동마다 최근 20건만 받았습니다. '
    '매물이 더 있을 수 있으니 jibsa 를 업데이트하세요'
)
# 행정동·법정동 이름 끝 ('역삼1동', '화곡제1동', '상계3.4동', '화곡본동', '역삼동'). 떼고 남은 이름이 같으면 같은 동네다.
# 점 번호를 빼면 '상계3.4동' 이 '상계3.' 이 되어 같은 구로 채울 때 상계동과 다른 동으로 골랐다 (2026-10-11 실측: 노원구
# 동 목록의 상계3.4동·상계6.7동·중계2.3동)
DONG_SUFFIX_PATTERN: re.Pattern[str] = re.compile(rf'({ADMIN_DONG_NUMBER}|본)?동$')


class DaangnDongListing(Listing):
    """동 이름 검색 매물. 당근은 조회한 동의 주변 동 매물을 섞어 주므로(`neighbor_notes`) 동 안 매물인지 표시한다."""

    in_regions: Annotated[
        bool | None,
        Field(description='조회한 동(regions) 안 매물이면 true, 당근이 섞어 준 주변 동 매물이면 false. 매물의 동을 모르면 null')
    ] = None


class DaangnSearchResult(BaseModel):
    """동 단위 매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    regions: Annotated[
        list[DaangnRegion],
        Field(description='실제로 매물을 조회한 동 (확장 포함). 한도를 다 써서 못 본 동과 지도 페이지가 없는 동은 notes 로 알린다')
    ]
    total: Annotated[
        int | None,
        Field(description=(
            '조회한 동들의 매물 수 합 (당근 집계). 조건이 있으면 조건에 맞는 수, 없으면 동 전체 수다. '
            '당근이 섞어 주는 주변 동 매물까지 세고, 동마다 1000 에서 잘린다. 모르면 null'
        ))
    ] = None
    fetched: Annotated[
        int,
        Field(description=(
            '받아 온 원본 매물 수 (중복·거래 불가·조건 불일치로 뺀 매물 포함). 모든 동이 limit 하나를 나눠 쓰고, '
            '한 동에서는 20건씩 최대 6페이지(120건)까지 받는다. 조건은 당근 서버에서 건다'
        ))
    ]
    returned: Annotated[
        int,
        Field(description='필터 후 반환한 매물 수')
    ]
    listings: Annotated[
        list[DaangnDongListing],
        Field(description='동별 피드 순서(최근 게시 순) 매물. 주변 동 매물이 섞여 오고 in_regions 로 구분한다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='전체 매물 수의 의미와 주변 동 매물이 섞였다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


class DaangnAreaSearchResult(BaseModel):
    """좌표 반경 매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='검색 중심이 속한 당근 동 (모르면 null)')
    ] = None
    radius_km: Annotated[
        float,
        Field(description='검색 반경 (km)')
    ]
    total: Annotated[
        int,
        Field(description='반경 안에서 조건(당근 서버에서 건 것)에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    listings: Annotated[
        list[Listing],
        Field(description='가까운 순 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='반경 밖 매물을 이어 붙였거나 일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def no_map_page_error(name3: str, query: str | None = None) -> UnsupportedRegionError:
    """당근에 지도(매물) 페이지가 없는 동. 노형동은 있고 이도이동은 없는 식이라 기준은 모른다.

    당근 동 이름이 검색어와 다르면(이도이동 → 이도2동) 둘 다 보여 준다. 당근 이름만
    보이면 엉뚱한 곳을 조회한 것으로 오해할 수 있기 때문이다.

    검색어가 행정동(역삼1동)이면 당근 지역 검색에는 나오지만 매물 지도는 법정동만 있어 늘 없다. 그때는 다른
    소스로 보내지 않고 법정동 이름으로 다시 찾게 한다 (2026-10-11 실측: /map/서울특별시/강남구/역삼1동 404,
    역삼동 200). 당근 이름(이도2동)이 아니라 검색어로 본다. 법정동(이도이동)을 넣었는데 당근이 행정동으로 바꾼
    경우는 숫자를 떼도 법정동이 아니다.
    """
    renamed = query is not None and query != name3
    hint = legal_dong_hint(query) if query else None
    if hint:
        return UnsupportedRegionError(
            code='REGION_NOT_FOUND',
            message=f"당근 매물 지도에는 행정동 '{name3}' 페이지가 없습니다",
            hint=hint,
            skip_note=f'daangn 은 행정동({name3}) 매물 페이지가 없습니다. {hint}',
        )
    return UnsupportedRegionError(
        code='REGION_NOT_SUPPORTED',
        message=f"당근은 '{name3}'" + (f" (검색어 '{query}')" if renamed else '') + ' 지역의 매물 페이지를 제공하지 않습니다',
        hint='근처 다른 동 이름으로 검색하거나 다른 소스를 쓰세요',
        skip_note=f'daangn 은 이 지역({name3}' + (f", 검색어 '{query}'" if renamed else '') + ')의 매물 페이지를 제공하지 않습니다. 근처 다른 동 이름으로 검색해 보세요',
    )


def _dong_stem(name3: str) -> str:
    """행정동과 그 법정동을 같은 이름으로 본다 ('역삼1동'·'역삼동' → '역삼', '화곡제1동'·'화곡본동' → '화곡')."""
    return DONG_SUFFIX_PATTERN.sub('', name3)


def expand_regions(
    client: DaangnClient,
    regions: list[DaangnRegion],
    articles: list[DaangnArticleModel],
    count: int,
    sido_cache: dict[tuple[str, str], str | None],
    *,
    missing: list[str] | None = None,
    lookup: bool = True,
) -> tuple[list[DaangnRegion], list[str]]:
    """첫 동(`regions[0]`) 주변 동 `count` 개와, 같은 구로 채웠을 때의 안내.

    당근 피드는 동을 지정해도 주변 동네 매물을 섞어 주므로(`neighbor_notes`), 첫 동 피드
    `articles` 에 많이 나온 동부터 고른다. 당근이 가깝다고 본 동이라 구 경계를 넘을 수 있다.
    모자라면 같은 구의 동 목록(가까운 순 아님)으로 채운다. 이미 조회하는 동과 그 행정동
    ('역삼동' 의 '역삼1동')은 같은 동네라 고르지 않는다. 지도 페이지가 없는 동(`missing`)은 이름만 다시 고르지 않고
    같은 동네의 다른 동은 막지 않는다. 행정동으로 찾으면 그 법정동이 바로 찾던 동네라서다 (2026-10-11 실측: 역삼1동
    --expand 2 가 같은 구 목록 맨 앞의 역삼동을 빼고 대치동·청담동만 골랐다). `lookup` 이 False 면 요청하지 않고
    시·도까지 온 피드의 주변 동만 고른다 (조회하지 못할 동의 이름만 알릴 때).

    같은 구 동 목록은 덤 조회라 실패하면(요청 제한 제외) 그때까지 고른 동만 돌려주고 이유를 안내에 붙인다. 첫 동에서
    받아 둔 매물을 잃지 않기 위함이다. 요청 제한은 고른 동의 지도 페이지도 같은 제한에 걸리므로 바로 올린다.

    Raises:
        RateLimitedError: 같은 구 동 목록 차례에 요청 제한에 걸렸을 때.
    """
    primary = regions[0]
    missing = missing or []
    taken = {_dong_stem(region.name3) for region in regions if region.name3 not in missing}
    taken_names = {region.name3 for region in regions}
    chosen: list[DaangnRegion] = []

    neighbors = Counter(
        (article.region.name1, article.region.name2 or '', article.region.name3, article.region.original_id)
        for article in articles
        if article.region is not None and article.region.name3 and article.region.original_id is not None
    )
    for (name1, name2, name3, region_id), _ in neighbors.most_common():
        if len(chosen) >= count:
            break
        if name3 in taken_names or _dong_stem(name3) in taken:
            continue
        # 주변 동 매물은 시·도 없이 오기도 하는데, 지도 페이지 경로에는 시·도가 필요하다
        name1 = name1 or (sido_of(client, name2, name3, sido_cache) if lookup else None)
        if name1 is None:
            continue
        taken.add(_dong_stem(name3))
        chosen.append(DaangnRegion(name1=name1, name2=name2, name3=name3, region_id=region_id))

    filled: list[str] = []
    notes: list[str] = []
    locations: list[DaangnLocationModel] = []
    if lookup and len(chosen) < count and primary.name2:
        try:
            locations = search_locations(client, primary.name2)
        except RateLimitedError:
            raise
        except OPTIONAL_LOOKUP_ERRORS as exc:
            logger.warning('daangn district dong list failed (%s); expanding with feed neighbors only', exc)
            notes.append(partial_failure_note(exc, '같은 구 동 목록', '주변 동을 더'))
    for location in locations:
        if len(chosen) >= count:
            break
        name3 = location.name3 or location.name
        if (
            location.name1 != primary.name1 or location.name2 != primary.name2
            or name3 in taken_names or _dong_stem(name3) in taken
        ):
            continue
        taken.add(_dong_stem(name3))
        chosen.append(DaangnRegion(name1=primary.name1, name2=primary.name2, name3=name3, region_id=location.id))
        filled.append(name3)

    if filled:
        # 안내 문장은 끝에 마침표가 없어 다른 안내와 이어 붙일 수 있다
        notes.append(
            f'{primary.name3} 피드에 섞여 온 주변 동이 {len(chosen) - len(filled)}곳뿐이라 '
            f"나머지는 같은 구의 다른 동({', '.join(filled)})으로 채웠습니다. 가까운 동이 아닐 수 있습니다"
        )
    return chosen, notes


def total_notes(
    total: int | None,
    fetched: int,
    filtered: Literal['server', 'client'] | None = None,
    *,
    complete: bool = False,
    region_count: int = 1,
    map_only: bool = False,
) -> list[str]:
    """매물 수가 무엇을 센 수인지와, 그중 무엇을 받았는지 알린다.

    조건이 있으면 당근이 조건으로 센 수(`articlesCount`), 없으면 조건 없이 센 동 전체 수다.
    어느 쪽이든 당근 피드가 섞어 주는 주변 동 매물까지 세고, 동마다 1000 에서 잘린다.

    Args:
        total: 조회한 동들의 매물 수 합 (모르면 None).
        fetched: 실제로 받은 매물 수.
        filtered: 조건을 건 곳. 'server' 면 당근 서버가 조건에 맞는 매물만 주었고, 'client' 면
            (필터 API 를 쓸 수 없을 때) 받아 온 최근 매물에 직접 걸었다. None 이면 조건이 없다.
        complete: 모든 동에서 피드를 끝까지 받았으면 True.
        region_count: 조회한 동 수. 여럿이면 동끼리 겹치는 주변 동 매물이 합에 두 번 들어갈 수 있다.
        map_only: 피드를 쓸 수 없어 동마다 지도 페이지(최근 20건)만 받았으면 True. 조건이 없을 때만 의미가 있다.
    """
    if total is None:
        return []
    what = '조건에 맞는 매물을 ' if filtered else ''
    overlap = ', 여러 동이라 겹칠 수 있음' if region_count > 1 else ''
    head = f'total {total}건은 {what}주변 동 매물까지 센 당근 집계입니다 (동마다 1000에서 잘림{overlap})'
    if filtered == 'client':
        return [f'{head}. 조건은 받아 온 최근 {fetched}건(동마다 최대 20건)에만 걸었으니 더 있을 수 있습니다']
    if complete:
        return [f'{head}. {fetched}건을 모두 받았습니다']
    per_region = FEED_PAGE_SIZE if map_only else FEED_PAGE_SIZE * MAX_FEED_PAGES
    return [f'{head}. 그중 최근 {fetched}건을 받았습니다 (동마다 최대 {per_region}건)']


def skipped_region_notes(
    unsearched: list[str],
    missing: list[str],
    limit: int,
    *,
    query: str | None = None,
) -> list[str]:
    """조회하려던 동 중 실제로 조회하지 못한 동을 알린다. 에이전트가 그 동을 따로 찾을 수 있게 이름을 준다.

    Args:
        unsearched: 앞 동에서 `limit` 를 다 써서 조회하지 못한 동 (확장한 동).
        missing: 당근 지도 페이지가 없는(404) 동.
        limit: 조회 한도.
        query: 검색어 동(첫 동)도 지도 페이지가 없을 때의 검색어. 행정동이면 법정동으로 다시 찾으라고 덧붙인다.
            --expand 로 주변 동은 조회돼 `no_map_page_error` 까지 가지 않으면 이 안내가 빠졌다 (2026-10-11 실측:
            역삼1동 --expand 2 가 대치동만 조회하고 '지도 페이지가 없어' 만 알렸다).
    """
    notes: list[str] = []
    if unsearched:
        names = ', '.join(unsearched)
        notes.append(
            f"{names}{particle(names, '은/는')} --limit {limit}건을 앞 동에서 다 써서 조회하지 못했습니다. "
            '더 보려면 --limit 을 늘리거나 그 동을 따로 찾으세요'
        )
    if missing:
        names = ', '.join(missing)
        hint = legal_dong_hint(query) if query else None
        notes.append(f"{names}{particle(names, '은/는')} 당근 지도 페이지가 없어 조회하지 못했습니다" + (f'. {hint}' if hint else ''))
    return notes


def neighbor_notes(regions: list[DaangnRegion], dongs: list[str | None]) -> list[str]:
    """돌려주는 매물 중 조회한 동이 아닌 매물이 있으면 그 사실을 알린다.

    당근 지도 피드는 동 ID 로 걸러 달라고 해도 주변 동네 매물을 섞어 준다 (은평구 신사동
    20건 중 13건이 고양시 향동동). 가까운 매물이라 빼지 않고, 동 단위 결과로 오해하지 않도록
    알린다.

    Args:
        regions: 조회한 동.
        dongs: 돌려주는 매물마다의 동 이름 (모르면 None).
    """
    requested = list(dict.fromkeys(region.name3 for region in regions))
    others = [dong for dong in dongs if dong is not None and dong not in requested]
    if not others:
        return []
    names = ', '.join(dict.fromkeys(others))
    return [f'{len(dongs)}건 중 {len(others)}건은 당근이 섞어 준 주변 동({names}) 매물입니다 (in_regions: false)']


def _server_only_conditions(property_filter: DaangnPropertyFilterModel) -> list[str]:
    """받아 온 매물로는 확인할 수 없어 서버에서만 걸 수 있는 조건 (wire 이름)."""
    client_side = {'salesTypes', 'tradeTypes', 'depositPay', 'monthlyPay', 'pricePay', 'minArea', 'maxArea', 'areaUnit'}
    return [key for key in property_filter.model_dump(by_alias=True, exclude_none=True) if key not in client_side]


def unwrap_feed(response: DaangnArticleFeedResponseModel) -> DaangnArticleFeedModel:
    """GraphQL 응답에서 피드를 꺼낸다 (`unwrap_graphql`)."""
    return unwrap_graphql(response, response.data.article_feed if response.data else None, '매물 피드')


def count_listings(
    client: DaangnClient,
    region: DaangnRegion,
    property_filter: DaangnPropertyFilterModel,
    *,
    notes: list[str],
) -> int | None:
    """동에서 조건에 맞는 매물 수 (`articlesCount`). 피드가 섞어 주는 주변 동 매물까지 센다.

    수는 안내와 피드를 끝까지 받을지 정하는 데만 쓰여, 조회가 실패하면(해시 거절·GraphQL 에러·
    HTTP 에러·응답 형식 변경) None 을 돌려주고 검색은 계속하며 이유를 `notes` 에 한 번만 붙인다. 요청 제한은 다음
    요청도 막히므로 그대로 올린다.

    Raises:
        RateLimitedError: 요청 제한에 걸렸을 때.
    """
    payload = DaangnArticlesCountRequestPayloadModel(
        input=DaangnArticlesCountInputModel(
            location_filter=DaangnLocationFilterModel(original_region_id=region.region_id),
            property_filter=property_filter,
        )
    )
    try:
        response = client.run_request_articles_count(payload)
        return unwrap_graphql(response, response.data.count if response.data else None, '매물 수')
    except RateLimitedError:
        raise
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn articlesCount failed (%s); continuing without count', exc)
        note = partial_failure_note(exc, '매물 수', '조건에 맞는 전체 매물 수를')
        if note not in notes:
            notes.append(note)
        return None


def feed_rejected_error(conditions: list[str]) -> JibsaError:
    """서버에서만 걸 수 있는 조건을 줬는데 필터 API 를 쓸 수 없을 때."""
    return JibsaError(
        code='UPSTREAM_ERROR',
        message='당근 필터 API 가 바뀌어(웹 쿼리 해시 거절) 이 조건을 걸 수 없습니다: ' + ', '.join(conditions),
        hint='-t, --trade, 가격·면적 범위만 남겨 다시 찾으면 동마다 최근 20건에 조건을 적용해 줍니다. jibsa 업데이트가 필요합니다',
    )


def property_type_notes(property_types: list[str], structures: list[str] | None = None) -> list[str]:
    """매물 종류 조건의 한계를 알린다. 당근 종류는 작성자가 고른 것이라 건물·방 수와 어긋날 수 있다."""
    notes: list[str] = []
    if '원룸' in property_types:
        notes.append(ONE_ROOM_NOTE)
        if '오피스텔' not in property_types:
            notes.append(ONE_ROOM_OFFICETEL_NOTE)
    elif '오피스텔' in property_types:
        notes.append(OFFICETEL_NOTE)
    if '투룸' in property_types:
        notes.append(TWO_ROOM_NOTE)
    # 방 구조(subSalesTypes)를 주면 당근은 거의 원룸만 돌려준다 (2026-10-10 실측: 원룸·오피스텔 등 + 분리형 →
    # 동 20건 모두 원룸, 역 20건·통근 50건 중 단지 없는 오피스텔 1건씩만 섞임)
    others = [property_type for property_type in property_types if property_type != '원룸']
    if structures and others:
        notes.append(
            f"--structure 를 주면 당근은 거의 원룸만 돌려주어 함께 준 {', '.join(others)} 매물은 대부분 빠집니다. "
            '다른 유형도 보려면 --structure 없이 따로 찾으세요'
        )
    return notes


class _FeedScan(BaseModel):
    """동마다 피드를 받아 모으는 동안의 상태 (`search_listings`). 조회 예산은 받은 원본 수로 센다."""

    conditions: DaangnListingConditions
    limit: Annotated[
        int,
        Field(description='조회 할당량 (--limit)')
    ]
    matched: Annotated[
        list[tuple[DaangnArticleModel, DaangnTradeModel, tuple[float, float] | None]],
        Field(description='조건에 맞는 (매물, 고른 거래 조건, 거리를 잴 중심)')
    ] = Field(default_factory=list)
    seen: Annotated[
        set[str],
        Field(description='이미 받은 매물 번호')
    ] = Field(default_factory=set)
    fetched: Annotated[
        int,
        Field(description='받은 원본 매물 수 (할당량을 쓴 만큼)')
    ] = 0
    unselected: Annotated[
        int,
        Field(description='서버 필터를 통과했지만 검색에 맞는 거래 조건을 고르지 못해 뺀 매물 수')
    ] = 0
    use_feed: Annotated[
        bool,
        Field(description='필터 API 를 쓸 수 있는지. 쓸 수 없게 되면 False 로 바뀌고 남은 동도 지도 페이지 20건만 쓴다')
    ] = True
    fallback_notes: Annotated[
        list[str],
        Field(description='필터 API 대신 지도 페이지를 썼다는 안내')
    ] = Field(default_factory=list)

    def take(self, articles: list[DaangnArticleModel], center: tuple[float, float] | None, server: bool) -> None:
        """받은 매물을 걸러 조건에 맞는 매물을 `matched` 에 넣는다.

        `server` 면 서버가 조건을 건 피드라 유형은 다시 거르지 않고 거래 조건만 고른다.
        아니면(조건 없는 지도 페이지) 유형·거래·금액·면적을 직접 확인한다.
        """
        for article in articles:
            self.fetched += 1
            if article.original_id in self.seen:
                continue
            self.seen.add(article.original_id)
            if not is_available(article):
                continue
            trade = trade_of(article, center, self.conditions, server=server)
            if trade is not None:
                self.matched.append((article, trade, center))
            elif server:
                self.unselected += 1


def search_listings(
    client: DaangnClient,
    regions: list[DaangnRegion],
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    query: str | None = None,
    expand: int = 0,
    split_budget: bool = False,
) -> DaangnSearchResult:
    """동마다 최근 매물을 조건으로 걸러 받아 `Listing` 으로 바꾼다.

    동마다 지도 페이지(SSR)로 동 정보(중심 좌표, 전체 매물 수, 주변 동)를 받는다. 조건이
    있으면 조건에 맞는 매물 수를 `articlesCount` 로 받고(`count_listings`), 매물은 GraphQL
    `articleFeed` 로 당근 서버가 거른 것을 받는다. 조건이 없으면 지도 페이지의 첫 20건에 이어
    `articleFeed` 로 다음 페이지를 받는다. 실제로 조회한 원본 수가 `limit`에 도달하면 멈추며
    중복·거래 불가·조건 불일치로 제외된 만큼 추가 조회하지 않는다. 동마다 최대 6페이지를 조회한다.

    필터 API 가 쿼리 해시를 거절하면(웹이 쿼리를 바꿈) 예전처럼 지도 페이지의 최근 20건에
    유형·거래·가격·면적 조건을 직접 걸고 `notes` 로 알린다. 그 밖의 조건은 받아 온 매물로
    확인할 수 없어 에러다.

    거래 조건이 여러 개인 매물은 대표 조건부터 보고, 가격 조건을 통과하는 첫 조건으로 내보낸다.

    피드 순서(최근 게시 순)로 `limit` 건을 고른다.

    피드에는 주변 동네 매물이 섞여 오는데, 가까운 매물이라 빼지 않고 `notes` 로 알린다.
    시·도가 빠진 매물은 돌려줄 매물에 한해 당근 지역 검색으로 채운다 (동마다 1회).

    `split_budget` 이면 '○가' 동(성수동1가·2가)처럼 나란히 찾는 동들이 `limit` 을 남은 동 수로 나눠 쓴다. 앞 동이
    예산을 다 써서 뒤 동을 못 보는 일을 막으려고, 지도 첫 페이지 20건도 그 몫까지만 쓴다.

    `expand` 를 주면 첫 동의 피드를 받은 뒤 주변 동을 그만큼 더 조회한다 (`expand_regions`).
    결과의 `regions` 에는 실제로 조회한 동만 들어간다. 앞 동에서 `limit` 를 다 써서 못 본 동과
    지도 페이지가 없는 동은 빼고 `notes` 로 알린다 (`skipped_region_notes`).

    Raises:
        UnsupportedRegionError: 조회한 동 모두 당근 지도 페이지가 없을 때 (404).
        JibsaError: 피드 조회가 실패했을 때, 또는 필터 API 를 쓸 수 없는데 서버에서만 걸 수 있는
            조건을 줬을 때 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    has_conditions = property_filter != DaangnPropertyFilterModel()
    scan = _FeedScan(conditions=conditions, limit=limit)
    # 조회한 동마다의 매물 수 (모르면 None). 하나라도 모르면 합을 내지 않는다
    counts: list[int | None] = []
    # 모든 동에서 피드를 끝까지 받았는지
    complete = True
    # 지도 페이지를 받아 실제로 조회한 동과, 지도 페이지가 없는 동
    searched: list[DaangnRegion] = []
    missing: list[str] = []
    sido_cache: dict[tuple[str, str], str | None] = {}
    expand_notes: list[str] = []
    # 매물 수를 받지 못한 이유 (count_listings)
    count_notes: list[str] = []
    # 거리(`distance_km`)를 잴 검색 중심. 처음 조회한 동의 중심이다. 확장한 동의 매물도 이 중심에서 재야 한 결과 안의
    # 거리끼리 비교된다 (2026-10-11 실측: 동마다 제 중심에서 재면 역삼동 --expand 의 서초구 잠원동 매물이 1.18km 였다)
    search_center: tuple[float, float] | None = None

    regions = list(regions)
    index = 0
    # 주변 동은 첫 동을 받은 뒤 그 지도 페이지 매물로 골라 regions 끝에 붙여 이어서 조회한다
    first_articles: list[DaangnArticleModel] = []
    pending_expand = expand > 0
    while scan.fetched < limit:
        if pending_expand and index == 1:
            # 첫 동을 받고도 조회 예산이 남았을 때만 고른다. 시·도 채우기·같은 구 채우기에 요청이 들기 때문이다
            neighbors, expand_notes = expand_regions(client, regions, first_articles, expand, sido_cache, missing=missing)
            regions += neighbors
            pending_expand = False
        if index >= len(regions):
            break
        region = regions[index]
        index += 1
        try:
            page = client.run_request_map(
                DaangnMapRequestParameterModel(name1=region.name1, name2=region.name2, name3=region.name3)
            )
        except HTTPStatusError as exc:
            # 지도 페이지가 없는 동은 404 다. 확장한 동 중 일부만 없으면 나머지로 진행한다.
            if exc.response.status_code != 404:
                raise
            page = None
        if index == 1 and page is not None:
            first_articles = page.articles
        if page is None:
            missing.append(region.name3)
            continue
        searched.append(region)
        # 조건이 없으면 지도 페이지의 동 전체 수가 곧 조건에 맞는 수다
        count = count_listings(client, region, property_filter, notes=count_notes) if has_conditions else page.total_count
        counts.append(count)
        _remember_sidos(sido_cache, region, page)
        if search_center is None and page.region and page.region.center_coordinate:
            coordinate = page.region.center_coordinate
            if coordinate.lat is not None and coordinate.lon is not None:
                search_center = (coordinate.lat, coordinate.lon)
        center = search_center

        if split_budget:
            scan.limit = scan.fetched + (limit - scan.fetched) // (len(regions) - index + 1)
        more = _read_feed(client, scan, region, page, center, count, has_conditions=has_conditions, cap_map_page=split_budget)
        # 필터 API 를 쓸 수 없어 조건 없는 지도 페이지만 봤으면 조건에 맞는 매물을 다 봤는지 알 수 없다
        if (count is None or scan.fetched < sum(value or 0 for value in counts)) or more or index < len(regions):
            complete = False

    if pending_expand and index > 0:
        # 첫 동에서 예산을 다 써서 주변 동은 조회하지 못한다. 못 본 동을 알리도록 요청 없이 피드의 주변 동만 고른다
        # (2026-10-11 실측: 기본 --limit 20 이면 첫 지도 페이지 20건으로 늘 예산을 다 써서, 고르기만 하고 쓰지 않을
        # 같은 구 동 목록을 받느라 요청이 하나 더 나갔다)
        neighbors, expand_notes = expand_regions(
            client, regions, first_articles, expand, sido_cache, missing=missing, lookup=False,
        )
        regions += neighbors
        if neighbors:
            complete = False

    if regions and len(missing) == len(regions):
        raise no_map_page_error(', '.join(missing), query)

    listings, shown, dongs = _matched_listings(client, scan.matched[:limit], sido_cache)
    requested = {region.name3 for region in searched}
    dong_listings = [
        listing_as(DaangnDongListing, listing, in_regions=None if dong is None else dong in requested)
        for listing, dong in zip(listings, dongs, strict=True)
    ]

    total = sum(count for count in counts if count is not None) if counts and None not in counts else None
    filtered: Literal['server', 'client'] | None = None
    if has_conditions:
        filtered = 'server' if scan.use_feed else 'client'
    return DaangnSearchResult(
        regions=searched,
        total=total,
        fetched=scan.fetched,
        returned=len(dong_listings),
        listings=dong_listings,
        notes=(
            scan.fallback_notes
            + expand_notes
            # 이미 조회한 동이 다시 들어와 있으면 못 봤다고 하지 않는다
            + skipped_region_notes(
                [region.name3 for region in regions[index:] if region not in searched], missing, limit,
                query=query if regions and regions[0].name3 in missing else None,
            )
            + total_notes(
                total, scan.fetched, filtered, complete=complete, region_count=len(counts), map_only=not scan.use_feed,
            )
            + count_notes
            + truncation_notes(len(scan.matched), limit)
            + listing_budget_notes(
                limit, scan.fetched, len(listings), has_more=not complete, eligible=len(scan.matched), narrowable=scan.use_feed,
            )
            + trade_unselected_notes(scan.unselected)
            + neighbor_notes(searched, dongs)
            + complex_building_notes(shown)
        ),
    )


def _remember_sidos(
    sido_cache: dict[tuple[str, str], str | None],
    region: DaangnRegion,
    page: DaangnMapResponseModel,
) -> None:
    """조회한 동과 지도 페이지 매물로 이미 아는 시·도를 캐시에 넣는다.

    GraphQL 피드의 매물은 시·도 없이 온다. 미리 넣어 두어 돌려줄 매물마다 지역 검색을 하지 않게 한다.
    """
    sido_cache.setdefault((region.name2, region.name3), region.name1)
    for article in page.articles:
        known = article.region
        if known is not None and known.name1 and known.name3:
            sido_cache.setdefault((known.name2 or '', known.name3), known.name1)


def _read_feed(
    client: DaangnClient,
    scan: _FeedScan,
    region: DaangnRegion,
    page: DaangnMapResponseModel,
    center: tuple[float, float] | None,
    count: int | None,
    *,
    has_conditions: bool,
    cap_map_page: bool = False,
) -> bool:
    """동 하나의 매물을 조회 예산·페이지 상한까지 받는다. 받을 페이지가 더 남았으면 True.

    `cap_map_page` 면 지도 첫 페이지도 남은 예산(`scan.limit`)까지만 쓴다 (`search_listings` 의 `split_budget`).
    """
    if has_conditions and scan.use_feed:
        # 지도 페이지의 첫 20건은 조건 없는 피드라 쓰지 않고 첫 페이지부터 받는다
        pages, cursor, more = 0, None, True
    else:
        articles = page.articles[:max(0, scan.limit - scan.fetched)] if cap_map_page else page.articles
        scan.take(articles, center, server=False)
        pages, cursor, more = 1, page.end_cursor, bool(page.has_next_page and page.end_cursor)
    if count == 0:
        # 조건에 맞는 매물이 없으면 받을 것도 남은 것도 없다. 피드를 끝까지 본 것으로 친다
        more = False
    while scan.use_feed and more and pages < MAX_FEED_PAGES and scan.fetched < scan.limit:
        payload = DaangnArticleFeedRequestPayloadModel(
            first=min(FEED_PAGE_SIZE, scan.limit - scan.fetched),
            after=cursor,
            input=DaangnArticleFeedInputModel(
                location_filter=DaangnLocationFilterModel(original_region_id=region.region_id),
                property_filter=scan.conditions.property_filter,
            ),
        )
        try:
            feed = unwrap_feed(client.run_request_article_feed(payload))
        except FeedQueryRejectedError as exc:
            logger.warning('daangn articleFeed persisted query rejected (%s); falling back to map page', exc)
            # 거절은 동이 아니라 해시에 달려 있어 한 번 실행 안에서는 첫 피드 요청에서 거절되거나 끝까지 받아진다
            # (2026-10-11 실측: 같은 동에 웹 해시는 성공, 다른 해시는 PersistedQueryNotFound). 앞 동은 서버 필터,
            # 뒤 동은 대체 조회로 섞이는 건 실행 중에 웹이 배포될 때뿐이라 그 경우의 안내(total_notes)는 따로 맞추지 않는다.
            server_only = _server_only_conditions(scan.conditions.property_filter)
            if server_only:
                raise feed_rejected_error(server_only) from None
            scan.use_feed = False
            scan.fallback_notes = [FEED_FALLBACK_NOTE if has_conditions else FEED_FALLBACK_PLAIN_NOTE]
            if pages == 0:
                scan.take(page.articles, center, server=False)
            break
        pages += 1
        articles = [edge.node.article for edge in feed.edges if edge.node and edge.node.article]
        scan.take(articles, center, server=has_conditions)
        page_info = feed.page_info
        cursor = page_info.end_cursor if page_info else None
        more = bool(page_info and page_info.has_next_page and cursor)
    return more


def _matched_listings(
    client: DaangnClient,
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel, tuple[float, float] | None]],
    sido_cache: dict[tuple[str, str], str | None],
) -> tuple[list[Listing], list[DaangnArticleModel], list[str | None]]:
    """고른 매물을 `Listing` 으로 바꾼다 (시·도가 빠졌으면 채운다). 내보낸 원본 매물과 그 동 이름도 함께 준다."""
    listings: list[Listing] = []
    shown: list[DaangnArticleModel] = []
    dongs: list[str | None] = []
    for article, trade, center in matched:
        article = with_sido(client, article, sido_cache)
        listing = article_to_listing(article, center, trade=trade)
        if listing is not None:
            listings.append(listing)
            shown.append(article)
            dongs.append(article.region.name3 if article.region else None)
    return listings, shown, dongs


def _nearest_points(points: list[DaangnArticlePointModel], lat: float, lng: float) -> list[tuple[str, float]]:
    """핀을 (매물 ID, 거리 km) 로 바꿔 가까운 순으로 돌려준다. 좌표 없는 핀과 중복 ID 는 뺀다."""
    nearest: dict[str, float] = {}
    for point in points:
        coordinate = point.coordinate
        if coordinate is None or coordinate.lat is None or coordinate.lon is None:
            continue
        nearest.setdefault(point.original_article_id, haversine_km(lat, lng, coordinate.lat, coordinate.lon))
    return sorted(nearest.items(), key=lambda entry: entry[1])


class DaangnStationListing(Listing):
    """역 주변 매물. `distance_km` 는 역까지의 직선거리다."""

    walk_minutes: Annotated[
        int | None,
        Field(description='매물에서 역까지 도보 (분). 당근이 알려 주지 않으면 null')
    ] = None


class DaangnStationSearchResult(BaseModel):
    """역 주변 매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station: Annotated[
        DaangnStation,
        Field(description='찾은 역')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지')
    ]
    listings: Annotated[
        list[DaangnStationListing],
        Field(description='당근 웹 역 주변 목록 순서 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도·제외 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def search_station(
    client: DaangnClient,
    station: DaangnStation,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnStationSearchResult:
    """역 주변 매물을 당근 웹의 역 주변 목록 순서로 `limit` 건 조회한다 (`subwayStationArticleConnection`).

    조건(`DaangnListingConditions`)은 당근 서버에서 건다. 카드에 상태·거래 조건·역별 도보 시간이 다 있어 카드를
    다시 받지 않는다. 요청당 100건이고, 받은 카드 수로 예산을 세며 뺀 매물은 다시 채우지 않는다.
    카드에는 시·도가 없어 역이 속한 동(`getRegionByCoordinate`)의 시·도로 같은 구의 동을 채운다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter

    def fetch(size: int, after: str | None) -> DaangnCommuteStationArticleConnectionModel:
        response = client.run_request_subway_station_article_connection(
            DaangnSubwayStationArticleConnectionRequestPayloadModel(
                subway_station_poi_id=station.station_id,
                first=size,
                after=after,
                property_filter=property_filter,
            )
        )
        return unwrap_graphql(
            response,
            response.data.subway_station_article_connection if response.data else None,
            '역 주변 매물',
        )

    edges, has_more = station_article_edges(fetch, limit)
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]
    inspected = len(articles)

    # 동 이름은 시·도 채우기에만 쓰여, 못 찾아도 매물은 보여 줄 수 있다. 받은 매물이 없으면 묻지 않는다
    region = region_or_none(client, station.lat, station.lng) if articles else None

    center = (station.lat, station.lng)
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[DaangnStationListing] = []
    shown: list[DaangnArticleModel] = []
    seen: set[str] = set()
    unselected = 0
    for article in articles[:limit]:
        if article.original_id in seen or not is_available(article):
            continue
        seen.add(article.original_id)
        trade = trade_of(article, center, conditions)
        if trade is None:
            unselected += 1
            continue
        listing = article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
        if listing is None:
            continue
        shown.append(article)
        walk = next(
            (
                item.duration_minutes for item in article.subway_stations
                if item.station and item.station.station_name == station.name
            ),
            None,
        )
        listings.append(listing_as(DaangnStationListing, listing, walk_minutes=walk))

    return DaangnStationSearchResult(
        station=station,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=(
            listing_budget_notes(limit, inspected, len(listings), has_more=has_more)
            + trade_unselected_notes(unselected)
            + complex_building_notes(shown)
        ),
    )


def search_area(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    radius_km: float = 1.0,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnAreaSearchResult:
    """좌표 반경 안의 매물을 가까운 순으로 `limit` 건 조회한다 (당근 웹 지도와 같은 방식).

    반경을 감싸는 좌표 범위의 핀(매물 ID·좌표)을 조건을 걸어 받고(`articleMapPoints`), 가까운
    순으로 20개씩 카드를 받아(`articlesByOriginalArticleIds`) `Listing` 으로 바꾼다. 조건 이름과
    값은 `DaangnListingConditions` 를 보며, 모두 당근 서버에서 건다. 동 단위 검색(`search_listings`)과
    달리 동 피드를 페이지로 넘기지 않아 주변 동 매물이 섞이거나 동마다 페이지 상한에 걸리지 않는다.

    반경 안 매물이 `limit` 보다 적으면 반경을 감싸는 범위의 반경 밖 매물도 가까운 순으로 이어
    준다 (직방과 같다). 검색 중심의 동은 `getRegionByCoordinate` 로 찾아 `region` 에 넣고, 카드에
    빠진 시·도를 채우는 데 쓴다. 찾지 못해도 검색은 계속한다.

    Raises:
        FeedQueryRejectedError: 핀·카드 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter

    # 동 이름은 결과 표시와 시·도 채우기에만 쓰여, 못 찾아도 매물 검색은 할 수 있다. 못 찾은 이유는 notes 로
    region_notes: list[str] = []
    region = region_or_none(client, lat, lng, notes=region_notes)

    response = client.run_request_article_map_points(
        DaangnArticleMapPointsRequestPayloadModel(
            input=DaangnArticleMapPointsInputModel(
                location_filter=bounds_around(lat, lng, radius_km),
                property_filter=property_filter,
            )
        )
    )
    points = unwrap_graphql(
        response,
        response.data.article_map_points if response.data else None,
        '지도 매물',
    )
    nearest = _nearest_points(points, lat, lng)
    # 반경 밖 안내(beyond_radius_notes)와 같은 기준(표시 거리)으로 센다
    total = sum(1 for _, distance in nearest if within_radius(distance, radius_km))

    center = (lat, lng)
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel]] = []
    # 서버 필터를 통과했지만 검색에 맞는 거래 조건을 고르지 못해 뺀 매물 수
    unselected = 0
    inspected = 0
    for start in range(0, min(len(nearest), limit), CARD_CHUNK_SIZE):
        ids = [article_id for article_id, _ in nearest[start:min(start + CARD_CHUNK_SIZE, limit)]]
        inspected += len(ids)
        cards_response = client.run_request_articles_by_original_article_ids(
            DaangnArticlesByOriginalArticleIdsRequestPayloadModel(original_article_ids=ids)
        )
        cards = unwrap_graphql(
            cards_response,
            cards_response.data.articles if cards_response.data else None,
            '매물 카드',
        )
        # 카드 순서는 보장되지 않아 핀의 가까운 순으로 되돌린다
        by_id = {card.original_id: card for card in cards}
        for article_id in ids:
            article = by_id.get(article_id)
            if article is None or not is_available(article):
                continue
            trade = trade_of(article, center, conditions)
            if trade is not None:
                matched.append((article, trade))
            else:
                unselected += 1

    # 카드에는 시·도가 없다. 검색 중심과 같은 구의 동은 같은 시·도로 보고(반경 몇 km 안에 같은 이름의
    # 다른 시·도 구가 붙어 있지는 않다), 나머지는 돌려줄 매물에 한해 동마다 지역 검색으로 채운다
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[Listing] = []
    shown: list[DaangnArticleModel] = []
    for article, trade in matched[:limit]:
        listing = article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
        if listing is not None:
            listings.append(listing)
            shown.append(article)

    notes: list[str] = []
    if len(points) >= PIN_LIMIT:
        notes.append(
            f'당근은 넓은 범위의 매물을 {PIN_LIMIT}건에서 잘라 주어 가까운 매물이 빠졌을 수 있습니다. '
            '--radius 를 줄이거나 유형·거래·가격 조건을 좁히세요'
        )
    return DaangnAreaSearchResult(
        region=region,
        radius_km=radius_km,
        total=total,
        returned=len(listings),
        listings=listings,
        notes=(
            region_notes
            + notes
            # 핀이 PIN_LIMIT 에서 잘려도 complete 를 넘기지 않는다. 반경 원이 받은 범위(사각형) 넓이의 79% 라 핀 10000개 중
            # 반경 안이 limit(최대 120)보다 적을 수 없다 (2026-10-11 실측: 역삼동 반경 5km, 10000개 중 8809개가 반경 안)
            + beyond_radius_notes(listings, radius_km)
            # 핀은 가까운 순이라 반경 안 핀이 앞에 온다. 사각형 모서리(반경 밖) 핀은 limit 을 늘려도 반경 밖 매물만 더
            # 나오므로 '더 있음' 으로 세지 않는다 (2026-10-11 실측: 반경 0.1km 핀 29개 중 반경 안 19개, limit 25 → 120 이 반경 밖 4건만 더)
            + listing_budget_notes(limit, inspected, len(listings), has_more=total > inspected, eligible=len(matched))
            + trade_unselected_notes(unselected)
            + complex_building_notes(shown)
        ),
    )
