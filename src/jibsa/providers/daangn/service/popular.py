"""구 안 인기 매물 순위 (popular-listings)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import Listing
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.popular import (
    DaangnGetViewRankingArticlesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import DaangnArticleModel
from jibsa.providers.daangn.service.common import (
    SALES_TYPE_BY_PROPERTY_TYPE,
    DaangnRegion,
    article_to_listing,
    complex_building_notes,
    is_available,
    label_codes,
    listing_as,
    listing_budget_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import with_center_sido

from typing import Annotated


class DaangnRankedListing(Listing):
    """조회수 순위 매물."""

    rank: Annotated[
        int,
        Field(description='조회수 순위 (거래 불가로 뺀 매물 자리는 비운다)')
    ]


class DaangnPopularListingsResult(BaseModel):
    """조회수 많은 매물 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnRegion, Field(description='기준 동 (순위는 그 구 전체)')]
    returned: Annotated[int, Field(description='반환한 매물 수')]
    listings: Annotated[list[DaangnRankedListing], Field(description='조회수 순위 순 매물')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='순위 범위·제외 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def list_popular_listings(
    client: DaangnClient,
    region: DaangnRegion,
    *,
    property_types: list[str] | None = None,
    limit: int = 20,
) -> DaangnPopularListingsResult:
    """동이 속한 구에서 조회수 많은 매물 (`getViewRankingArticles`, 요청 1회). 순위가 매겨진 매물은 100건쯤이다.

    받은 매물 수로 예산을 세고, 거래 불가로 뺀 매물은 다시 채우지 않는다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_get_view_ranking_articles(
        DaangnGetViewRankingArticlesRequestPayloadModel(
            region_id=region.region_id,
            sales_types=label_codes(property_types, SALES_TYPE_BY_PROPERTY_TYPE) or [],
            limit=limit,
        )
    )
    ranking = unwrap_graphql(response, response.data.get_view_ranking_articles if response.data else None, '인기 매물')
    articles = ranking.articles[:limit]
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[DaangnRankedListing] = []
    shown: list[DaangnArticleModel] = []
    for rank, article in enumerate(articles, start=1):
        if not is_available(article):
            continue
        listing = article_to_listing(with_center_sido(client, article, region, sido_cache), None)
        if listing is not None:
            listings.append(listing_as(DaangnRankedListing, listing, rank=rank))
            shown.append(article)
    return DaangnPopularListingsResult(
        region=region,
        returned=len(listings),
        listings=listings,
        # 순위 범위는 동이 속한 구다. 세종은 시·군·구가 없어(name2 '') 그 동 안에서만 매긴다 (2026-10-11 실측: 새롬동 7건·
        # 아름동 4건·반곡동 1건·소담동 0건이 모두 그 동 매물. 자곡동은 강남구 다른 동 매물 28건)
        notes=[
            f'순위는 {region.name2} 전체 조회수 기준입니다' if region.name2
            else f'구가 없는 지역이라 순위는 {region.name3} 안 조회수 기준입니다'
        ]
        + listing_budget_notes(limit, len(articles), len(listings), has_more=False)
        + complex_building_notes(shown),
    )
