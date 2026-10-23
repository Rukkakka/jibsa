"""응답 모델: 지도 매물 검색과 지역 단지 목록 (search listings, search complexes)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverComplexListPageModel,
    NaverCoordinatesModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverClusterModel(ResponseModel):
    """지도 클러스터."""

    cluster_id: Annotated[
        str,
        Field(description='클러스터 ID ({zoom}/{x}/{y})', alias='clusterId')
    ]
    coordinates: Annotated[
        NaverCoordinatesModel,
        Field(description='클러스터 중심')
    ]
    article_count: Annotated[
        int,
        Field(description='클러스터 안 매물 수', alias='articleCount')
    ]


class NaverClustersModel(ResponseModel):
    """지도 클러스터 목록."""

    total_count: Annotated[
        int,
        Field(description='뷰포트 안 전체 매물 수', alias='totalCount')
    ] = 0
    clusters: Annotated[
        list[NaverClusterModel],
        Field(description='클러스터')
    ] = []


class NaverComplexLegalDivisionComplexListV1ResponseModel(NaverResponseModel[NaverComplexListPageModel]):
    """`POST /front-api/v1/complex/legalDivisionComplexList` 응답."""


class NaverComplexBoundedComplexesV1ResponseModel(NaverResponseModel[NaverComplexListPageModel]):
    """`POST /front-api/v1/complex/boundedComplexes` 응답."""


class NaverArticleLegalDivisionArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/legalDivisionArticleList` 응답. 지도 매물 목록과 같은 모양이다."""


class NaverArticleMapArticleClustersV1ResponseModel(NaverResponseModel[NaverClustersModel]):
    """`POST /front-api/v1/article/map/articleClusters` 응답."""


class NaverArticleBoundedArticlesV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/boundedArticles` 응답."""


class NaverArticleClusteredArticlesV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/clusteredArticles` 응답."""
