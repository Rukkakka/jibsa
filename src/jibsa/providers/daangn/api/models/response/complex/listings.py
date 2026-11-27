"""응답 모델: 단지 매물 (search listings --complex)."""

from pydantic import Field

from jibsa.providers.daangn.api.models.response.common import (
    DaangnArticleModel,
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId { complex { articles } } (단지 매물 목록)
# ---------------------------------------------------------------------------

class DaangnArticleEdgeModel(DaangnBaseResponseModel):
    """매물 연결 edge."""

    node: Annotated[
        DaangnArticleModel | None,
        Field(description='매물 카드 (articleFeed 카드와 같은 필드. 지역에 시·도가 없다)')
    ] = None


class DaangnArticleConnectionModel(DaangnBaseResponseModel):
    """매물 연결."""

    edges: Annotated[
        list[DaangnArticleEdgeModel],
        Field(description='매물')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnComplexArticlesComplexModel(DaangnBaseResponseModel):
    """단지 (매물 연결만 받는다)."""

    articles: Annotated[
        DaangnArticleConnectionModel | None,
        Field(description='단지의 현재 매물')
    ] = None


class DaangnComplexArticlesOutputModel(DaangnBaseResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexArticlesComplexModel | None,
        Field(description='단지')
    ] = None


class DaangnComplexArticlesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexArticlesOutputModel | None,
        Field(description='단지 조회 결과', alias='complexByOriginalId')
    ] = None


class DaangnComplexArticlesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL 단지 매물 목록 응답."""

    data: Annotated[
        DaangnComplexArticlesDataModel | None,
        Field(description='결과')
    ] = None
