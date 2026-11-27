"""동·지도 범위 매물 검색 (search listings 의 동 이름·좌표·주소)."""

import logging

from jibsa.core.listing import note
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.common import (
    DaangnBoundsLocationFilterModel,
    DaangnPropertyFilterModel,
    is_empty_property_filter,
)
from jibsa.providers.daangn.api.models.request.search.map import (
    DaangnArticleByClusterIdInputModel,
    DaangnArticleByClusterIdRequestPayloadModel,
    DaangnArticleClustersInputModel,
    DaangnArticleClustersRequestPayloadModel,
    DaangnArticleFeedInputModel,
    DaangnArticleFeedRequestPayloadModel,
    DaangnArticlesCountInputModel,
    DaangnArticlesCountRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.search.map import (
    DaangnArticleFeedEdgeModel,
    DaangnArticleFeedModel,
    DaangnArticleFeedResponseModel,
)
from jibsa.providers.daangn.service.common.constants import OPTIONAL_LOOKUP_ERRORS
from jibsa.providers.daangn.service.common.location import map_view_bounds
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
    DaangnRegion,
)
from jibsa.providers.daangn.service.common.nearby import connection_edges
from jibsa.providers.daangn.service.common.response import (
    partial_failure_note,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region.area import (
    region_or_none,
    sido_cache_from_rows,
    sido_cache_rows,
)
from jibsa.providers.daangn.service.region.models.address import DaangnAddress
from jibsa.providers.daangn.service.region.models.area import DaangnArea
from jibsa.providers.daangn.service.search.common import (
    listing_notes,
    to_listings,
)
from jibsa.providers.daangn.service.search.constants import (
    COUNT_CAP,
    FEED_PAGE_SIZE,
    MAP_RESOLUTION_BY_ZOOM,
    MAP_RESOLUTION_MIN,
    REGION_CLUSTER_ZOOM,
)
from jibsa.providers.daangn.service.search.models.map import (
    DaangnDongSearchResult,
    DaangnMapSearchResult,
)


logger = logging.getLogger(__name__)


def map_resolution(zoom: float) -> int:
    """웹 데스크톱 지도가 줌마다 목록·매물 수 요청에 보내는 `resolution` (H3 해상도)."""
    return next((resolution for low, resolution in MAP_RESOLUTION_BY_ZOOM if zoom >= low), MAP_RESOLUTION_MIN)


def unwrap_feed(response: DaangnArticleFeedResponseModel, *, conditions: bool) -> DaangnArticleFeedModel:
    """GraphQL 응답에서 피드를 꺼낸다 (`unwrap_graphql`). `conditions` 는 요청에 사용자가 고른 매물 조건이 들어갔는지다."""
    return unwrap_graphql(response, response.data.article_feed if response.data else None, '매물 피드', conditions=conditions)


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
        return unwrap_graphql(
            response, response.data.count if response.data else None, '매물 수', conditions=not is_empty_property_filter(property_filter),
        )
    except OPTIONAL_LOOKUP_ERRORS as exc:
        _count_failed(notes, exc, 'articlesCount', '조건에 맞는 전체 매물 수를')
        return None


def _count_failed(notes: list[str], exc: Exception, query: str, subject: str) -> None:
    """매물 수 조회 실패를 기록하고 이유를 `notes` 에 한 번만 붙인다. 지도 범위 수와 동 거품 수가 같이 쓴다."""
    logger.warning('daangn %s failed (%s); continuing without count', query, exc)
    failed = note('실패', partial_failure_note(exc, '매물 수', subject))
    if failed not in notes:
        notes.append(failed)


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
        clusters = unwrap_graphql(
            response, response.data.article_clusters if response.data else None, '지역 거품',
            conditions=not is_empty_property_filter(property_filter),
        )
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
    filtered = not is_empty_property_filter(property_filter)

    def fetch(size: int, after: str | None) -> DaangnArticleFeedModel:
        response = client.run_request_article_by_cluster_id(
            DaangnArticleByClusterIdRequestPayloadModel(
                first=size,
                after=after,
                input=DaangnArticleByClusterIdInputModel(cluster_id=f'REGION:{area.region_id}', property_filter=property_filter),
            )
        )
        return unwrap_graphql(response, response.data.article_by_cluster_id if response.data else None, '동 매물', conditions=filtered)

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
    edges, has_more, cursor, stopped, _ = connection_edges(
        fetch, limit, FEED_PAGE_SIZE, after=after, full_page_more=full_page_more, notes=notes,
    )
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]
    count()
    received += len(articles)
    # 그 동의 클러스터 목록이라 모두 그 동 매물이다. 그 동의 구·동 이름은 동의 시·도로 미리 채워 시·도를 따로 찾지 않는다 (구
    # 이름만 같은 다른 시·도의 동은 이 목록에 오지 않는다). 이어 받기 표에 담지 않는다
    converted = to_listings(
        client, articles, conditions, (area.lat, area.lng), region, {(region.sigungu, region.dong): region.sido},
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
        notes=notes + listing_notes(
            limit, articles, shown, has_more=has_more, resumable=resumable, resumed=resumed, stopped=stopped,
        ),
    )


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
    filtered = not is_empty_property_filter(property_filter)
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
        ), conditions=filtered)

    # 지도 범위 목록(`articleFeed`)은 동 목록과 달리 `hasNextPage` 가 맞아 꽉 찬 쪽으로 짐작하지 않는다 (2026-11-12 실측: 홍천군
    # 내면 둘레 줌 10 은 20건씩 true 로 이어지고, 줌 12 는 13건 = 매물 수 13)
    notes: list[str] = []
    edges, has_more, cursor, stopped, _ = connection_edges(fetch, limit, FEED_PAGE_SIZE, after=after, notes=notes)
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]

    # 매물 수·동 이름은 안내와 시·도 채우기에만 쓰여 못 받아도 매물은 보여 준다. 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이
    # 되면 첫 화면 실패를 삼키고 본 조회가 브라우저를 다시 띄운다. 2026-11-10 리뷰)
    resumed = after is not None
    if total is None and not resumed:
        total = count_listings(client, bounds, property_filter, notes=notes, resolution=resolution)
    # 동은 결과의 region 으로 나가 매물이 없어도 찾는다. null 은 '모름' 이라 찾지 않고 null 을 주면 당근이 위치를 못 찾은
    # 것으로 읽힌다 (2026-11-12 리뷰·실측: 역삼동 좌표 토지 매매 1만원 이하 0건에 region null). 역·대학 주변 목록은 동을 시·도
    # 채우기에만 써 매물이 없으면 묻지 않는다. 앞 쪽에서 못 찾았으면 이어 받는 쪽도 다시 묻고, 또 실패하면 그 쪽의 region 도
    # null 이라 실패 안내를 그 쪽에도 붙인다. 범위·집계 안내처럼 첫 쪽에만 붙이면 뒤 쪽의 null 이 '당근이 위치를 못 찾음' 으로
    # 읽힌다. 동을 못 찾거나 조회가 실패하면 `region_or_none` 이 region 을 null 로 두고 `[실패]` 안내를 붙인다 (`notes` 를 넘긴다.
    # 못 찾은 경우의 에러도 `JibsaError` 라 `OPTIONAL_LOOKUP_ERRORS` 에 잡힌다). 그래서 null 이 안내 없이
    # 나가는 길은 없다 (2026-11-12 리뷰 오탐, 근거 고침 2026-11-20)
    if region is None:
        region = region_or_none(client, lat, lng, notes=notes)

    sido_cache = sido_cache_from_rows(sidos)
    converted = to_listings(client, articles, conditions, (lat, lng), region, sido_cache)
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
        notes=notes + listing_notes(
            limit, articles, [article for article, _ in converted], has_more=has_more, resumable=resumable, resumed=resumed,
            stopped=stopped,
        ),
    )
