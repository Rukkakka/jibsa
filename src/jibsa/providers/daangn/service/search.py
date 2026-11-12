"""매물 검색 조건과 동·지도 범위·역·대학 주변 매물 검색 (search listings)."""

import logging
from collections.abc import Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    listing_as,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnBoundsLocationFilterModel,
    DaangnPropertyFilterModel,
    is_empty_property_filter,
)
from jibsa.providers.daangn.api.request.search import (
    DaangnArticleByClusterIdInputModel,
    DaangnArticleByClusterIdRequestPayloadModel,
    DaangnArticleClustersInputModel,
    DaangnArticleClustersRequestPayloadModel,
    DaangnArticleFeedInputModel,
    DaangnArticleFeedRequestPayloadModel,
    DaangnArticlesCountInputModel,
    DaangnArticlesCountRequestPayloadModel,
    DaangnSubwayStationArticleConnectionRequestPayloadModel,
    DaangnUniversityArticleConnectionRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.api.response.search import (
    DaangnArticleFeedEdgeModel,
    DaangnArticleFeedModel,
    DaangnArticleFeedResponseModel,
)
from jibsa.providers.daangn.service.common import (
    COUNT_CAP,
    LISTING_MAX_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    UNIVERSITY_DEFAULT_SALES_TYPES,
    DaangnListingConditions,
    DaangnNearbyListing,
    DaangnRegion,
    article_to_listing,
    complex_building_notes,
    connection_edges,
    cursor_stopped_note,
    hidden_location_notes,
    is_available,
    listing_budget_notes,
    map_resolution,
    map_view_bounds,
    no_trade_notes,
    partial_failure_note,
    trade_of,
    unwrap_graphql,
    walk_minutes_to,
)
from jibsa.providers.daangn.service.region import (
    STATION_PAGE_SIZE,
    DaangnAddress,
    DaangnArea,
    DaangnStation,
    DaangnUniversity,
    region_or_none,
    sido_cache_from_rows,
    sido_cache_rows,
    with_center_sido,
)

from typing import (
    Annotated,
    Any,
    NamedTuple,
)


logger = logging.getLogger(__name__)
FEED_PAGE_SIZE: int = 20
# 웹 지도가 동 거품(`articleClusters`, zoomLevel 8)을 그리는 줌. 지역 거품은 줌 8 이상 13 미만에서만 요청하고, 동 거품 줌
# (mapDev `regionDongMinZoom` 12) 미만은 구 거품(7)이다 (2026-11-12 번들 대조: MapView `Mt`·`Pt`·`Ft`, mapDev `s`)
REGION_CLUSTER_ZOOM: int = 12


def unwrap_feed(response: DaangnArticleFeedResponseModel) -> DaangnArticleFeedModel:
    """GraphQL 응답에서 피드를 꺼낸다 (`unwrap_graphql`)."""
    return unwrap_graphql(response, response.data.article_feed if response.data else None, '매물 피드')


def count_listings(
    client: DaangnClient,
    location_filter: DaangnBoundsLocationFilterModel,
    property_filter: DaangnPropertyFilterModel,
    *,
    notes: list[str],
    resolution: int,
) -> int | None:
    """지도 범위에서 조건에 맞는 매물 수 (`articlesCount`, 1000 에서 잘린다). 동 목록은 동 거품 수(`count_dong_listings`)를 쓴다.

    `resolution` 은 목록과 같은 줌의 H3 해상도다 (`map_resolution`, 웹도 목록·매물 수에 같은 값을 보낸다).

    수는 안내에만 쓰여, 조회가 실패하면(해시 거절·GraphQL 에러·HTTP 에러·응답 형식 변경·요청 제한) None 을 돌려주고
    검색은 계속하며 이유를 `notes` 에 한 번만 붙인다 (시·도 채우기 `with_sido` 와 같다). 매물을 받은 뒤에 세므로, 요청 제한을 올리면 받은
    매물까지 잃는다 (2026-11-12 리뷰·실측: 이 조회만 요청 제한을 내게 바꾸니 좌표 검색이 받은 매물 없이 RATE_LIMITED 로 끝났다).
    """
    payload = DaangnArticlesCountRequestPayloadModel(
        input=DaangnArticlesCountInputModel(
            location_filter=location_filter,
            property_filter=property_filter,
            resolution=resolution,
        )
    )
    try:
        response = client.run_request_articles_count(payload)
        return unwrap_graphql(response, response.data.count if response.data else None, '매물 수')
    except OPTIONAL_LOOKUP_ERRORS as exc:
        _count_failed(notes, exc, 'articlesCount', '조건에 맞는 전체 매물 수를')
        return None


def _count_failed(notes: list[str], exc: Exception, query: str, subject: str) -> None:
    """매물 수 조회 실패를 기록하고 이유를 `notes` 에 한 번만 붙인다. 지도 범위 수와 동 거품 수가 같이 쓴다."""
    logger.warning('daangn %s failed (%s); continuing without count', query, exc)
    failed = note('실패', partial_failure_note(exc, '매물 수', subject))
    if failed not in notes:
        notes.append(failed)


def property_type_notes(property_types: list[str], structures: list[str] | None = None) -> list[str]:
    """매물 종류 조건의 한계를 알린다. 당근 종류는 작성자가 고른 것이라 건물·방 수와 어긋날 수 있다."""
    # 원룸·오피스텔·투룸 종류의 한계(작성자가 고른 종류, 투룸은 투룸 이상)는 찾을 때마다 같은 안내라 docs/llm.md 로 옮겼다
    notes: list[str] = []
    # 방 구조(subSalesTypes)를 주면 당근은 거의 원룸만 돌려준다 (2026-10-10 실측: 원룸·오피스텔 등 + 분리형 →
    # 동 20건 모두 원룸, 역 20건·통근 50건 중 단지 없는 오피스텔 1건씩만 섞임)
    others = [property_type for property_type in property_types if property_type != '원룸']
    if structures and others:
        notes.append(note(
            '제외',
            f"--structure 를 주면 당근은 거의 원룸만 돌려주어 함께 준 {', '.join(others)} 매물은 대부분 빠집니다. "
            '다른 유형도 보려면 --structure 없이 따로 찾으세요',
        ))
    return notes


class DaangnDongSearchResult(BaseModel):
    """동 매물 검색 결과 (웹 지도의 동 클러스터 매물 목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion,
        Field(description='찾은 동')
    ]
    total: Annotated[
        int | None,
        Field(description='동 안에서 조건에 맞는 매물 수 (웹 지도의 동 거품 "매물 N개"). 받지 못하면 null')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(
            exclude=True,
            description='이어 받을 위치 ({"after": 당근 커서, "total": 앞에서 센 수, "received": 지금까지 받은 원본 수}). 더 없으면 None',
        )
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 목록 순서(최근 순) 매물. 모두 그 동 매물이다. distance_km 는 동 중심까지의 직선거리다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='매물 수·조회 한도 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def _to_listings(
    client: DaangnClient,
    articles: list[DaangnArticleModel],
    conditions: DaangnListingConditions,
    center: tuple[float, float],
    region: DaangnRegion | None,
    sido_cache: dict[tuple[str, str], str | None],
) -> list[tuple[DaangnArticleModel, DaangnNearbyListing]]:
    """받은 매물을 목록 순서대로 (원본, 결과 매물) 로 바꾼다. 동·지도 범위·역·대학 검색이 같이 쓴다.

    겹친 매물, 거래할 수 없는 매물(`is_available`), 보여 줄 거래가 없는 매물(`trade_of`)은 빼고 다시 채우지 않는다. 카드에
    시·도가 빠지면 지역 검색으로 채운다 (`with_center_sido`. 검색 중심 동 `region` 은 세종 매물에만 바로 쓴다). `sido_cache` 는
    찾은 시·도이고 이어 받기 표에 담아 다음 쪽이 같은 구·동을 다시 찾지 않게 한다 (`sido_cache_rows`). 받은 매물을 `[:limit]` 로 자르지 않는다. 서버가 `first` 만큼만
    주고 요청 크기도 limit 을 넘지 않는다 (2026-11-12 실측: 동 목록 first 2·7 → 2·7건, 지도 범위 목록 3 → 3건, 역 주변 목록 3·7 →
    3·7건). 자르면 이어 받기 커서가 잘린 매물 뒤를 가리켜 그 매물이 빠진다 (2026-11-12 리뷰 오탐).
    겹친 매물은 한 번에 받은 매물 안에서만 뺀다. 이어 받은 쪽(`--next`)과 앞 쪽은 커서로 이어져 겹치지 않는다 (2026-11-12 리뷰
    오탐에 실측: 서버가 `hasNextPage: false` 를 준 뒤 이어 받은 홍천군 내면 20+6건, 역삼동 20+20건이 limit 40 한 번과 순서까지 같았다).
    """
    seen: set[str] = set()
    converted: list[tuple[DaangnArticleModel, DaangnNearbyListing]] = []
    for article in articles:
        if article.original_id in seen or not is_available(article):
            continue
        seen.add(article.original_id)
        trade = trade_of(article, conditions)
        if trade is None:
            continue
        listing = article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
        if isinstance(listing, DaangnNearbyListing):
            converted.append((article, listing))
    return converted


def _listing_notes(
    limit: int,
    articles: list[DaangnArticleModel],
    shown: list[DaangnArticleModel],
    *,
    has_more: bool,
    resumable: bool,
    resumed: bool,
    stopped: bool,
) -> list[str]:
    """받은 수·뺀 매물·거래 조건·단지 건물·숨긴 주소 안내. 동·지도 범위·역·대학 검색이 같이 쓴다 (`shown` 은 결과에 넣은 원본).

    `stopped` 는 목록이 다음이 있다면서 이어 받을 쪽을 주지 않아 멈췄는지다 (`connection_edges`). --limit 을 늘려도 같은
    자리에서 멈춰 --limit 안내 대신 멈췄다고 알린다.
    """
    stopped_notes = [note('일부', cursor_stopped_note('매물 목록', f'{len(articles)}건'))] if stopped else []
    return (
        listing_budget_notes(
            limit, len(articles), len(shown), max_limit=LISTING_MAX_LIMIT, has_more=has_more,
            narrowable=not stopped, resumable=resumable, resumed=resumed,
        )
        + stopped_notes
        + no_trade_notes(articles)
        + complex_building_notes(shown)
        + hidden_location_notes(shown)
    )


class _AroundListings(NamedTuple):
    """역·대학 주변 목록에서 한 번 받은 매물 (`_around_listings`)."""

    converted: list[tuple[DaangnArticleModel, DaangnNearbyListing]]
    has_more: bool
    next_position: dict[str, Any] | None
    notes: list[str]


def _around_listings(
    client: DaangnClient,
    fetch: Callable[[int, str | None], DaangnCommuteStationArticleConnectionModel],
    center: tuple[float, float],
    conditions: DaangnListingConditions,
    *,
    limit: int,
    after: str | None,
    region: DaangnRegion | None,
    sidos: list[list[str]] | None,
) -> _AroundListings:
    """역·대학 주변 목록을 `limit` 건 받아 결과 매물로 바꾼다. 같은 연결 타입이라 `search_station`·`search_university` 가 같이 쓴다.

    요청당 100건이고, 받은 카드 수로 예산을 세며 뺀 매물은 다시 채우지 않는다. 카드에는 시·도가 없어 지역 검색으로 채운다
    (`with_center_sido`). 검색 중심이 속한 동(`getRegionByCoordinate`)은 그때 세종 매물에만 쓰여, 못 찾아도 매물은 보여 줄 수
    있다. 받은 매물이 없으면 묻지 않는다. `region`·`sidos` 는 앞 결과가 찾은 동과 시·도다 (주면 다시 찾지 않는다). 예전에는 두
    검색이 이 흐름을 따로 두었다 (2026-11-12 리뷰).
    """
    edges, has_more, cursor, stopped = connection_edges(fetch, limit, STATION_PAGE_SIZE, after=after)
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]
    if region is None and articles:
        region = region_or_none(client, *center)
    sido_cache = sido_cache_from_rows(sidos)
    converted = _to_listings(client, articles, conditions, center, region, sido_cache)
    resumable = bool(has_more and cursor)
    return _AroundListings(
        converted=converted,
        has_more=has_more,
        next_position=(
            {'after': cursor, 'region': region.model_dump() if region else None, 'sidos': sido_cache_rows(sido_cache)}
            if resumable else None
        ),
        notes=_listing_notes(
            limit, articles, [article for article, _ in converted],
            has_more=has_more, resumable=resumable, resumed=after is not None, stopped=stopped,
        ),
    )


def count_dong_listings(
    client: DaangnClient,
    area: DaangnArea,
    property_filter: DaangnPropertyFilterModel,
    *,
    notes: list[str],
) -> int | None:
    """동 안에서 조건에 맞는 매물 수 (웹 지도의 동 거품 "매물 N개", `articleClusters`).

    웹은 지도 화면 범위와 조건으로 지역 거품을 받아 거품마다 수를 보여 준다 (MapView 의 `na`, 동 단위는 zoomLevel 8). 웹이 동
    거품을 그리는 줌(`REGION_CLUSTER_ZOOM`)의 동 중심 화면 범위로 물어 그 동 거품의 수를 쓴다. 조건이 없으면 웹처럼 필터를 null
    로 보낸다. 동 피드의 `articlesCount` 는 주변 동까지 세고 1000 에서 잘려 쓰지 않는다 (2026-11-11 실측: 역삼동 월세 100 이하 거품
    726건, articlesCount 1000). 지역 경계는 받지 않는다 (`includeBoundaries: false`, 모바일 웹과 같다). 받으면 화면 안 동 140여 곳의
    경계로 응답이 1.4MB 였다 (2026-11-12 실측: 역삼동 1,380,628 → 18,173바이트, 거품 수는 같다). 수는 안내와 다음 쪽을 받을지
    정하는 데만 쓰여, 조회가 실패하면(요청 제한 포함) None 을 돌려주고 이유를 `notes` 에 붙인다. 요청 제한을 올리면 받은 매물까지
    잃는다 (2026-11-12 리뷰·실측: 이 조회만 요청 제한을 내게 바꾸니 역삼동이 받은 매물 없이 RATE_LIMITED 로 끝났다). 수를 몰라
    다음 쪽을 받다가 그 요청이 막히면 그때는 본 조회의 요청 제한이라 그대로 올라간다.
    """
    bounds, _, _ = map_view_bounds(area.lat, area.lng, REGION_CLUSTER_ZOOM)
    payload = DaangnArticleClustersRequestPayloadModel(
        input=DaangnArticleClustersInputModel(location_filter=bounds, property_filter=property_filter)
    )
    try:
        response = client.run_request_article_clusters(payload)
        clusters = unwrap_graphql(response, response.data.article_clusters if response.data else None, '지역 거품')
    except OPTIONAL_LOOKUP_ERRORS as exc:
        _count_failed(notes, exc, 'articleClusters', '조건에 맞는 동 매물 수를')
        return None
    # 조건에 맞는 매물이 없는 동도 거품이 count 0 으로 와서 None(모름)이 아니라 0 이 된다 (2026-11-12 실측: 역삼동 매매 1만원
    # 이하 → total 0). 응답에 그 동 거품이 없으면 None 이고 안내를 붙이지 않는다. 동 중심 화면이라 거품이 빠질 일이 없어서다
    # (2026-11-12 리뷰 지적에 실측: 백령면·울릉읍·울릉 북면·연평면(0건)·흑산면·기린면·내면·수완동 8곳 모두 거품이 왔다)
    return next((cluster.count for cluster in clusters if cluster.original_id == f'REGION:{area.region_id}'), None)


def search_dong(
    client: DaangnClient,
    area: DaangnArea,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    after: str | None = None,
    total: int | None = None,
    received: int = 0,
) -> DaangnDongSearchResult:
    """동 하나의 매물을 웹 지도의 동 클러스터 목록처럼 최근 순으로 `limit` 건 조회한다 (`articleByClusterId`).

    조건이 있든 없든 같은 목록을 써서 그 동 매물만 준다. 웹의 동 페이지(검색 엔진용 첫 화면)는 조건 없이 주변 동 매물을 섞은
    `articleFeed(originalRegionId)` 를 보여 주지만, 조건을 건 목록과 지도에서 동을 누른 목록은 이 목록이다. 같은 동 이름이
    조건 유무로 범위가 달라지지 않게 늘 이 목록을 쓴다 (#215, 2026-11-11 사용자 결정). 예전에는 동 피드를 받아 주변 동 매물을
    `in_regions: false` 로 표시했다 (역삼동 20건 중 12건이 논현·삼성동).

    20건씩 받고(웹과 같다) 받은 수로 예산을 세며 뺀 매물은 다시 채우지 않는다. 서버의 `hasNextPage` 가 틀리게 와서 쪽이 꽉 차면
    다음 쪽도 받는다 (`connection_edges`). 그렇게 짐작한 '더 있음' 만 동 거품 수(`total`)로 끈다. 받은 수가 거품 수에 닿으면 더 없다.
    서버가 `hasNextPage: true` 라고 한 것은 웹도 다음 쪽을 부르므로 그대로 따른다.
    `after`·`total`·`received` 는 이어 받기(`--next`)에서 앞 결과가 남긴 커서, 매물 수, 앞에서 받은 원본 수다. 매물 수는 앞에서
    셌으면 다시 세지 않고, 못 셌으면(None) 이어 받을 때 다시 센다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    region = area.as_region()

    def fetch(size: int, after: str | None) -> DaangnArticleFeedModel:
        response = client.run_request_article_by_cluster_id(
            DaangnArticleByClusterIdRequestPayloadModel(
                first=size,
                after=after,
                input=DaangnArticleByClusterIdInputModel(cluster_id=f'REGION:{area.region_id}', property_filter=property_filter),
            )
        )
        return unwrap_graphql(response, response.data.article_by_cluster_id if response.data else None, '동 매물')

    notes: list[str] = []
    resumed = after is not None
    # 앞에서 수를 못 셌으면(None) 이어 받을 때도 다시 센다. 수가 없으면 짐작한 '더 있음' 을 끄지 못해 마지막 쪽 뒤에 빈 쪽을 한 번 더
    # 받는다 (2026-11-12 리뷰: 첫 쪽에서 거품 조회가 실패하면 이어 받기 내내 total 이 None 이었다). 지도 범위 수는 안내에만 쓰여
    # 다시 세지 않는다. 세는 것은 첫 쪽을 받은 뒤다 (덤 조회가 첫 요청이 되면 첫 화면 실패를 삼킨다, `search_map_area`)
    counted = total is not None

    def count() -> int | None:
        nonlocal total, counted
        if not counted:
            total, counted = count_dong_listings(client, area, property_filter, notes=notes), True
        return total

    def full_page_more(edges: list[DaangnArticleFeedEdgeModel]) -> bool:
        # 쪽이 꽉 차 다음이 있다고 짐작한 것만 거품 수로 끈다. 거품 수만큼 받았으면 다음 쪽은 비어, 다음 쪽을 받기 전에 본다
        # (2026-11-12 리뷰·실측: 역삼동 원룸 월세 보증금 70 이하·월세 55~185 는 거품 20건이고, 받은 뒤에 끄던 때는 --limit 40
        # 이 요청 4번으로 --limit 20 보다 빈 쪽 한 번이 많았다). 앞 결과가 받은 수(received)를 모르면 0 부터 세어 끄지 못할 뿐
        # 매물을 놓치지 않는다. 서버가 더 있다고 한 것은 끄지 않는다. 거품 수와 목록이 어긋나면 받은 수가 거품 수에 닿아도 목록에
        # 매물이 남아, 끄면 그 매물을 놓친다 (2026-11-12 리뷰). 받은 수는 매물이 든 edge 만 센다. 거품 수는 매물 수라 빈 edge 까지
        # 세면 매물이 남았는데 일찍 꺼 놓칠 수 있다. 빈 edge 가 오더라도 마지막에 빈 쪽을 한 번 더 받을 뿐이다 (2026-11-12 리뷰:
        # edge 로 세라는 지적에 놓치지 않는 쪽을 골랐다)
        known = count()
        return known is None or received + sum(1 for edge in edges if edge.node and edge.node.article) < known

    # 동 목록(`articleByClusterId`)은 매물이 남았는데도 `hasNextPage` 를 false 로 준다 (2026-11-12 실측: 홍천군 내면은 거품
    # 26건인데 20건 쪽이 false 이고 커서로 이어 받으면 나머지가 왔다. 인제군 기린면 15건은 1·5건 쪽이 true, 7·14건 쪽이 false 로
    # 들쭉날쭉했다). 당근 웹도 이 값을 믿어 목록이 20건에서 멈추는데, 당근 버그라 따르지 않는다 (2026-11-12 사용자 결정)
    edges, has_more, cursor, stopped = connection_edges(
        fetch, limit, FEED_PAGE_SIZE, after=after, full_page_more=full_page_more,
    )
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]
    count()
    received += len(articles)
    # 그 동의 클러스터 목록이라 모두 그 동 매물이다. 그 동의 구·동 이름은 동의 시·도로 미리 채워 시·도를 따로 찾지 않는다 (구
    # 이름만 같은 다른 시·도의 동은 이 목록에 오지 않는다). 이어 받기 표에 담지 않는다
    converted = _to_listings(
        client, articles, conditions, (area.lat, area.lng), region, {(region.name2, region.name3): region.name1},
    )
    shown = [article for article, _ in converted]
    resumable = bool(has_more and cursor)
    return DaangnDongSearchResult(
        region=region,
        total=total,
        returned=len(converted),
        has_more=has_more,
        next_position={'after': cursor, 'total': total, 'received': received} if resumable else None,
        listings=[listing for _, listing in converted],
        notes=notes + _listing_notes(
            limit, articles, shown, has_more=has_more, resumable=resumable, resumed=resumed, stopped=stopped,
        ),
    )


class DaangnStationListing(DaangnNearbyListing):
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

    region: Annotated[
        DaangnStation,
        Field(description='찾은 역 (검색 중심). 다른 검색의 region 과 같은 자리라 이름을 맞췄다')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"after": 당근 커서, "region": 역의 동, "sidos": 찾은 시·도}). 더 없으면 None')
    ] = None
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
    after: str | None = None,
    region: DaangnRegion | None = None,
    sidos: list[list[str]] | None = None,
) -> DaangnStationSearchResult:
    """역 주변 매물을 당근 웹의 역 주변 목록 순서로 `limit` 건 조회한다 (`subwayStationArticleConnection`).

    조건(`DaangnListingConditions`)은 당근 서버에서 건다. 카드에 상태·거래 조건·역별 도보 시간이 다 있어 카드를
    다시 받지 않는다. 받는 방식은 대학 주변 목록과 같다 (`_around_listings`).
    `after`·`region`·`sidos` 는 이어 받기(`--next`)에서 앞 결과가 남긴 당근 커서, 역의 동, 찾은 시·도다 (주면 다시 찾지 않는다).

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

    found = _around_listings(
        client, fetch, (station.lat, station.lng), conditions, limit=limit, after=after, region=region, sidos=sidos,
    )
    listings = [
        listing_as(DaangnStationListing, listing, walk_minutes=walk_minutes_to(article, station.name))
        for article, listing in found.converted
    ]
    return DaangnStationSearchResult(
        region=station,
        returned=len(listings),
        has_more=found.has_more,
        next_position=found.next_position,
        listings=listings,
        notes=found.notes,
    )


class DaangnMapSearchResult(BaseModel):
    """지도 화면 범위 매물 검색 결과 (웹 지도의 매물 목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='찾은 구 (구 이름으로 찾았을 때) 또는 화면 가운데가 속한 동 (좌표·주소로 찾았을 때). 모르면 null')
    ] = None
    address: Annotated[
        DaangnAddress | None,
        Field(description='--address 로 찾은 도로명 주소와 그 좌표 (화면 가운데). 주소로 찾지 않았으면 키가 없다')
    ] = None
    zoom: Annotated[
        int,
        Field(description='웹 지도 줌. 범위는 데스크톱 지도 화면(1440×900 창에서 목록 패널을 뺀 영역) 기준이다')
    ]
    width_km: Annotated[
        float,
        Field(description='화면 범위의 가로 (km)')
    ]
    height_km: Annotated[
        float,
        Field(description='화면 범위의 세로 (km)')
    ]
    total: Annotated[
        int | None,
        Field(description='화면 범위 안에서 조건에 맞는 매물 수 (당근 집계, 1000 에서 잘린다). 모르면 null')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(
            exclude=True,
            description='이어 받을 위치 ({"after": 당근 커서, "total": 앞에서 센 수, "region": 결과의 region, "sidos": 찾은 시·도}). 더 없으면 None',
        )
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 지도 목록 순서(최근 순) 매물. distance_km 는 화면 가운데까지의 직선거리다 (순서와는 상관없다)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='범위·매물 수·조회 한도 안내. CLI 가 notice 아래에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_missing_address(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 구·좌표로 찾은 결과에 주소는 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.address is None:
            data.pop('address', None)
        return data


def search_map_area(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    zoom: int,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    region: DaangnRegion | None = None,
    after: str | None = None,
    total: int | None = None,
    address: DaangnAddress | None = None,
    sidos: list[list[str]] | None = None,
) -> DaangnMapSearchResult:
    """(`lat`, `lng`) 를 가운데에 둔 웹 지도 화면 범위의 매물을 웹 지도 목록처럼 최근 순으로 `limit` 건 조회한다.

    웹 지도 목록과 같이 `articleFeed` 에 화면 범위와 줌의 `resolution` 을 넣어 20건씩 받는다 (`map_view_bounds`). 조건은
    당근 서버에서 건다. jibsa 는 순서를 바꾸거나 범위 밖 매물을 붙이지 않고, 화면 가운데까지의 거리만 참고로 붙인다.
    매물 수는 같은 범위의 `articlesCount` 다 (1000 에서 잘린다). 매물 카드에 시·도가 없어 지역 검색으로 채운다
    (`with_center_sido`). 구 이름이 `region`(구로 찾았으면 그 구, 없으면 화면 가운데의 동)과 같아도 넓은 화면에는 다른 시·도의
    같은 이름 구가 들어와 중심의 시·도로 채우지 않는다.

    `after`·`total`·`region`·`sidos` 는 이어 받기(`--next`)에서 앞 결과가 남긴 값이다 (주면 다시 묻지 않는다). 앞 결과가 동을 못
    찾았으면(`region` 이 None) 역·대학 주변 목록처럼 이어 받기에서도 다시 찾는다. `address` 는 `--address` 로 찾은 주소다
    (좌표는 그 주소의 좌표고, 결과에 그대로 싣는다).

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    bounds, width_km, height_km = map_view_bounds(lat, lng, zoom)
    resolution = map_resolution(zoom)

    def fetch(size: int, after: str | None) -> DaangnArticleFeedModel:
        return unwrap_feed(client.run_request_article_feed(
            DaangnArticleFeedRequestPayloadModel(
                first=size,
                after=after,
                input=DaangnArticleFeedInputModel(
                    location_filter=bounds, property_filter=property_filter, resolution=resolution,
                ),
            )
        ))

    # 지도 범위 목록(`articleFeed`)은 동 목록과 달리 `hasNextPage` 가 맞아 꽉 찬 쪽으로 짐작하지 않는다 (2026-11-12 실측: 홍천군
    # 내면 둘레 줌 10 은 20건씩 true 로 이어지고, 줌 12 는 13건 = 매물 수 13)
    edges, has_more, cursor, stopped = connection_edges(fetch, limit, FEED_PAGE_SIZE, after=after)
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]

    # 매물 수·동 이름은 안내와 시·도 채우기에만 쓰여 못 받아도 매물은 보여 준다. 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이
    # 되면 첫 화면 실패를 삼키고 본 조회가 브라우저를 다시 띄운다. 2026-11-10 리뷰)
    notes: list[str] = []
    resumed = after is not None
    if total is None and not resumed:
        total = count_listings(client, bounds, property_filter, notes=notes, resolution=resolution)
    # 동은 결과의 region 으로 나가 매물이 없어도 찾는다. null 은 '모름' 이라 찾지 않고 null 을 주면 당근이 위치를 못 찾은
    # 것으로 읽힌다 (2026-11-12 리뷰·실측: 역삼동 좌표 토지 매매 1만원 이하 0건에 region null). 역·대학 주변 목록은 동을 시·도
    # 채우기에만 써 매물이 없으면 묻지 않는다. 앞 쪽에서 못 찾았으면 이어 받는 쪽도 다시 묻고, 또 실패하면 그 쪽의 region 도
    # null 이라 실패 안내를 그 쪽에도 붙인다. 범위·집계 안내처럼 첫 쪽에만 붙이면 뒤 쪽의 null 이 '당근이 위치를 못 찾음' 으로
    # 읽힌다. 동을 못 찾는 것은 사실상 조회 실패뿐이다. 바닷가 앞바다 좌표도 바다에 닿은 동을 준다 (2026-11-12 리뷰 오탐에 실측:
    # 해운대 앞바다 35.12,129.19 → 중동, 35.08,129.20 → 용호동, 영종도 앞 37.45,126.40 → 을왕동)
    if region is None:
        region = region_or_none(client, lat, lng, notes=notes)

    sido_cache = sido_cache_from_rows(sidos)
    converted = _to_listings(client, articles, conditions, (lat, lng), region, sido_cache)
    # 다른 첫 쪽 안내처럼 처음에만 알린다. 이어 받을 때는 표가 total 을 넘겨 줘 쪽마다 붙었다 (2026-11-12 리뷰)
    if total is not None and total >= COUNT_CAP and not resumed:
        notes.append(note('참고', f'total {total}건은 당근 집계가 {COUNT_CAP}에서 잘린 수입니다. 화면 범위 안 매물은 더 많을 수 있습니다'))
    resumable = bool(has_more and cursor)
    return DaangnMapSearchResult(
        region=region,
        address=address,
        zoom=zoom,
        width_km=width_km,
        height_km=height_km,
        total=total,
        returned=len(converted),
        has_more=has_more,
        next_position=(
            {
                'after': cursor, 'total': total, 'region': region.model_dump() if region else None,
                'sidos': sido_cache_rows(sido_cache),
            }
            if resumable else None
        ),
        listings=[listing for _, listing in converted],
        notes=notes + _listing_notes(
            limit, articles, [article for article, _ in converted], has_more=has_more, resumable=resumable, resumed=resumed,
            stopped=stopped,
        ),
    )


class DaangnUniversitySearchResult(BaseModel):
    """대학 주변 매물 검색 결과 (웹 대학 페이지의 매물 목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnUniversity,
        Field(description='찾은 대학 캠퍼스 (검색 중심). 다른 검색의 region 과 같은 자리라 이름을 맞췄다')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"after": 당근 커서, "region": 대학이 있는 동, "sidos": 찾은 시·도}). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 대학 페이지 목록 순서 매물 (대체로 가까운 순). distance_km 는 대학까지의 직선거리다')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도·제외 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def search_university(
    client: DaangnClient,
    university: DaangnUniversity,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    after: str | None = None,
    region: DaangnRegion | None = None,
    sidos: list[list[str]] | None = None,
) -> DaangnUniversitySearchResult:
    """대학 주변 매물을 웹 대학 페이지의 목록 순서로 `limit` 건 조회한다 (`universityArticleConnection`).

    역 주변 목록(`search_station`)과 같은 연결 타입이라 같은 방식으로 받는다 (`_around_listings`). 대학 둘레 범위는 당근
    서버가 정한다. 조건은 당근 서버에서 건다. `after`·`region`·`sidos` 는 이어 받기(`--next`)에서 앞 결과가 남긴 커서, 대학이
    있는 동, 찾은 시·도다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    default_types = is_empty_property_filter(property_filter)
    if default_types:
        # 웹 대학 페이지는 지도 필터가 하나도 없을 때만 원룸·투룸·오피스텔을 기본으로 보낸다 (MapShell `Ff` 의 `??ke`, 조건이
        # 하나라도 있으면 그 필터 그대로). 역 주변 목록은 빈 필터(전체)가 기본이라 다르다 (2026-11-12 번들 대조)
        property_filter = property_filter.model_copy(update={'sales_types': list(UNIVERSITY_DEFAULT_SALES_TYPES)})

    def fetch(size: int, after: str | None) -> DaangnCommuteStationArticleConnectionModel:
        response = client.run_request_university_article_connection(
            DaangnUniversityArticleConnectionRequestPayloadModel(
                school_poi_id=university.university_id,
                first=size,
                after=after,
                property_filter=property_filter,
            )
        )
        return unwrap_graphql(
            response,
            response.data.university_article_connection if response.data else None,
            '대학 주변 매물',
        )

    found = _around_listings(
        client, fetch, (university.lat, university.lng), conditions, limit=limit, after=after, region=region, sidos=sidos,
    )
    return DaangnUniversitySearchResult(
        region=university,
        returned=len(found.converted),
        has_more=found.has_more,
        next_position=found.next_position,
        listings=[listing for _, listing in found.converted],
        notes=(
            # 범위 안내는 다른 검색처럼 첫 결과에만 붙인다 (이어 받기는 같은 조건이다)
            (
                [note('범위', '조건이 없어 당근 웹 대학 페이지처럼 원룸·투룸·오피스텔만 찾았습니다. 다른 종류는 -t 로 고르세요')]
                if default_types and after is None else []
            )
            + found.notes
        ),
    )
