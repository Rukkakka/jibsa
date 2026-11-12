"""구 안 인기 매물 순위 (popular-listings)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Listing,
    listing_as,
)
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
    listing_budget_notes,
    no_trade_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import with_center_sido

from typing import Annotated


# 당근 웹 인기 매물 순위 화면(`PopularArticleRankingPanel`)이 늘 30건(`limit:30`)을 받아 30위까지만 보여 준다. 서버는 구마다
# 100건쯤까지 순위를 주지만 웹에 없는 31위 뒤는 내지 않고, 기본값도 웹과 같은 30 으로 둔다 (#215, 2026-11-11 사용자 결정. 예전에는
# 최대 100·기본 20 이었다)
POPULAR_MAX_LIMIT: int = 30


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
    property_type: str | None = None,
    limit: int = POPULAR_MAX_LIMIT,
) -> DaangnPopularListingsResult:
    """동이 속한 구에서 조회수 많은 매물 (`getViewRankingArticles`, 요청 1회). 웹처럼 30위까지다 (`POPULAR_MAX_LIMIT`).

    웹 순위 화면(`PopularArticleRankingPanel`)은 탭 없이 URL(`popular_articles=<지역 ID>:<종류>`)로 종류 하나를 받아
    `salesTypes:[종류]` 로 부르고, 종류는 원룸·투룸·아파트·오피스텔만 받는다 (`POPULAR_PROPERTY_TYPES`, 그 밖은 화면을 열지
    않는다. 이 종류만 주는 것은 CLI 의 `--type` 이 검사한다). 종류를 주지 않으면 빈 목록(전체)을 보낸다. 웹에는 전체 순위 화면이 없지만(홈 CEO 그리드만 구 ID·전체·12건)
    서버가 받아 구 전체 순위를 주어 남겨 둔다 (2026-11-12 번들 대조). 받은 매물 수로 예산을 세고, 거래 불가·거래 조건이 없어 뺀 매물은
    다시 채우지 않는다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
        JibsaError: 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
    """
    response = client.run_request_get_view_ranking_articles(
        DaangnGetViewRankingArticlesRequestPayloadModel(
            region_id=region.region_id,
            sales_types=[SALES_TYPE_BY_PROPERTY_TYPE[property_type]] if property_type else [],
            limit=limit,
        )
    )
    ranking = unwrap_graphql(response, response.data.get_view_ranking_articles if response.data else None, '인기 매물')
    articles = ranking.articles[:limit]
    # 순위는 그 동이 속한 구 안이라 카드는 모두 그 구 매물이다. 구 이름은 그 동의 시·도로 미리 채워 시·도를 따로 찾지 않는다
    # (`search_dong` 과 같다). 예전에는 카드마다 구 이름으로 찾아 여러 시·도에 있는 구 이름이면 그 이름 검색을 끝까지 받았다
    # (2026-11-13 리뷰·실측: '서울 중구 명동2가' 가 요청 5회. 도움말은 2회). 세종은 구가 없어(name2 '') `with_center_sido` 가 채운다
    sido_cache: dict[tuple[str, str], str | None] = {(region.name2, ''): region.name1} if region.name2 else {}
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
        # 서버가 순위를 limit 건에서 잘라 주므로 limit 건을 다 받았으면 뒤 순위가 남아 있다 (2026-10-14 실측: 역삼동
        # --limit 30 에서 30건을 받고 1건을 빼자 '더 조회할 매물이 없습니다' 라고 했다)
        + listing_budget_notes(
            limit, len(articles), len(listings), max_limit=POPULAR_MAX_LIMIT,
            has_more=len(articles) >= limit and limit < POPULAR_MAX_LIMIT,
        )
        # 아는 거래(매매·전세·월세·단기임대·연세)가 없는 매물만 빠진다. 예전에는 연세를 빼 제주 순위가 크게 비었다 (2026-11-12 실측:
        # 연동 30위 중 12건이 연세만 있어 빠졌다)
        + no_trade_notes(articles)
        + complex_building_notes(shown),
    )
