"""요청 모델: 구 안 인기 매물 순위 (popular-listings)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnSalesType

from typing import Annotated


class DaangnGetViewRankingArticlesRequestPayloadModel(RequestModel):
    """GraphQL `getViewRankingArticles` 쿼리 변수 (웹의 `PopularArticleRankingPanelQuery`, 조회수 많은 매물).

    동 ID 를 줘도 그 구 전체 순위가 온다. 순위가 매겨진 매물은 100건쯤이다 (2026-10-10 실측).
    """

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동)')
    ] = Field(alias='regionId')
    sales_types: Annotated[
        list[DaangnSalesType],
        Field(description='매물 종류. 빈 목록이면 전체')
    ] = Field(default=[], alias='salesTypes')
    limit: Annotated[
        int,
        Field(ge=1, description='받을 매물 수 (웹은 30)')
    ] = 30
