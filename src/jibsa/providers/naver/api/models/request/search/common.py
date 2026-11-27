"""요청 모델: 지도 매물 검색·지역 단지 목록이 같이 쓰는 것."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.models.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
    NaverBoundingBoxModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class NaverArticleMapArticleClustersV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/map/articleClusters` 본문."""

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='매물 필터')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트', alias='boundingBox')
    ]
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='클러스터 해상도. 클수록 클러스터가 작아진다')
    ] = 15
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'


class NaverArticlePagingRequestModel(RequestModel):
    """클러스터 매물 페이지 요청. 첫 요청은 seed/lastInfo 없이 보낸다."""

    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기. 응답이 매물당 수십 KB 라 작게 유지한다')
    ] = 20
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    article_sort_type: Annotated[
        NaverArticleSortType,
        Field(description='정렬', alias='articleSortType')
    ] = 'RANKING_DESC'
    seed: Annotated[
        str | None,
        Field(description='서버가 첫 응답에 주는 정렬 seed')
    ] = None
    last_info: Annotated[
        Any,
        Field(description='커서. 응답의 lastInfo 를 그대로 (리스트 또는 정수)', alias='lastInfo')
    ] = None


class NaverArticleClusteredArticlesV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/clusteredArticles` 본문."""

    cluster_id: Annotated[
        str,
        Field(pattern=r'^\d+/\d+/\d+$', description='클러스터 ID ({zoom}/{x}/{y})', alias='clusterId')
    ]
    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='articleClusters 와 같은 필터')
    ]
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청', alias='articlePagingRequest')
    ] = Field(default_factory=NaverArticlePagingRequestModel)
