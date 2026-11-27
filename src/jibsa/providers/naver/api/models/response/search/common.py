"""응답 모델: 지도 매물 검색·지역 단지 목록이 같이 쓰는 것."""

from pydantic import Field

from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
    NaverBaseResponseModel,
    NaverCoordinatesModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverClusterModel(NaverBaseResponseModel):
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


class NaverClustersModel(NaverBaseResponseModel):
    """지도 클러스터 목록."""

    total_count: Annotated[
        int,
        Field(description='뷰포트 안 전체 매물 수', alias='totalCount')
    ] = 0
    clusters: Annotated[
        list[NaverClusterModel],
        Field(description='클러스터')
    ] = []


class NaverArticleMapArticleClustersV1ResponseModel(NaverResponseModel[NaverClustersModel]):
    """`POST /front-api/v1/article/map/articleClusters` 응답."""


class NaverArticleClusteredArticlesV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/article/clusteredArticles` 응답."""
