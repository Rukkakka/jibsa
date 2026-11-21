"""응답 모델: 구 안 인기 매물 순위 (popular-listings)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


class DaangnViewRankingModel(DaangnBaseResponseModel):
    """조회수 순위 매물 목록."""

    articles: Annotated[
        list[DaangnArticleModel],
        Field(description='순위 순 매물 (카드 전체 필드)')
    ] = []


class DaangnGetViewRankingArticlesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    get_view_ranking_articles: Annotated[
        DaangnViewRankingModel | None,
        Field(description='조회수 순위', alias='getViewRankingArticles')
    ] = None


class DaangnGetViewRankingArticlesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `getViewRankingArticles` 응답."""

    data: Annotated[
        DaangnGetViewRankingArticlesDataModel | None,
        Field(description='결과')
    ] = None
