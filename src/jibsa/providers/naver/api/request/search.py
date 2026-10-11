"""요청 모델: 지도 매물 검색과 지역 단지 목록 (search listings, search complexes)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
    NaverBoundingBoxModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


NaverComplexSortType = Literal['POPULARITY_DESC', 'HOUSEHOLD_NUMBER_DESC', 'USE_APPROVAL_DATE_DESC', 'ARTICLE_COUNT_DESC']
"""단지 목록 정렬. 인기순, 세대수순, 최근입주순, 매물수순 (사이트 COMPLEX_LIST_SORT_TYPE, 2026-10-09)."""


class NaverArticleMapArticleClustersV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/map/articleClusters` 본문."""

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='매물 필터')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트')
    ] = Field(alias='boundingBox')
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='클러스터 해상도. 클수록 클러스터가 작아진다')
    ] = 15
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')


class NaverArticlePagingRequestModel(RequestModel):
    """클러스터 매물 페이지 요청. 첫 요청은 seed/lastInfo 없이 보낸다."""

    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기. 응답이 매물당 수십 KB 라 작게 유지한다')
    ] = 20
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')
    article_sort_type: Annotated[
        NaverArticleSortType,
        Field(description='정렬')
    ] = Field(default='RANKING_DESC', alias='articleSortType')
    seed: Annotated[
        str | None,
        Field(description='서버가 첫 응답에 주는 정렬 seed')
    ] = None
    last_info: Annotated[
        Any,
        Field(description='커서. 응답의 lastInfo 를 그대로 (리스트 또는 정수)')
    ] = Field(default=None, alias='lastInfo')


class NaverArticleBoundedArticlesV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/boundedArticles` 본문. 사이트 지도 옆 매물 목록이 쓴다.

    사각형 안 매물을 `articlePagingRequest.articleSortType` 순으로 준다 (가까운 순은 없다).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='articleClusters 와 같은 필터')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트')
    ] = Field(alias='boundingBox')
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='지도 줌. 사이트는 매물 표시 최소 줌 이상에서만 부른다')
    ] = 16
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)')
    ] = Field(default_factory=NaverArticlePagingRequestModel, alias='articlePagingRequest')
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')


class NaverArticleLegalDivisionArticleListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/legalDivisionArticleList` 본문. 법정동 하나의 매물 전체를 정렬해 준다.

    `filter.legalDivisionNumbers` 에 동 코드 하나, `legalDivisionType` 은 EUP 이다. 구·시 단위(GU·SI)는
    400 이다. 페이지는 30건까지 (50부터 400). 지도 필터가 그대로 걸린다 (2026-10-09 확인).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='articleClusters 와 같은 필터 + 법정동 코드')
    ]
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청 (정렬 포함, size 30 이하)')
    ] = Field(default_factory=NaverArticlePagingRequestModel, alias='articlePagingRequest')


class NaverComplexPagingRequestModel(RequestModel):
    """단지 목록 페이지 요청. 첫 요청은 seed 없이 lastInfo [] 로 보낸다."""

    size: Annotated[
        int,
        Field(ge=1, le=30, description='페이지 크기. 사이트 COMPLEX_PAGINATION_SIZE 30')
    ] = 30
    complex_sort_type: Annotated[
        NaverComplexSortType,
        Field(description='정렬')
    ] = Field(default='POPULARITY_DESC', alias='complexSortType')
    seed: Annotated[
        str | None,
        Field(description='서버가 첫 응답에 주는 정렬 seed')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로')
    ] = Field(default=[], alias='lastInfo')


class NaverComplexLegalDivisionComplexListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/legalDivisionComplexList` 본문. 법정동 하나의 단지 전체.

    `filter.legalDivisionNumbers` 에 동 코드 하나, `legalDivisionType` 은 EUP. 지도 필터가 그대로 걸리고
    `hasArticle` 이면 매물 있는 단지만 준다 (역삼동 아파트 160 → 114곳, 2026-10-09 확인).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터 + 법정동 코드')
    ]
    complex_paging_request: Annotated[
        NaverComplexPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)')
    ] = Field(default_factory=NaverComplexPagingRequestModel, alias='complexPagingRequest')
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')


class NaverComplexBoundedComplexesV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/boundedComplexes` 본문. 사각형 안 단지 (사이트 지도 옆 단지 목록)."""

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트')
    ] = Field(alias='boundingBox')
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='지도 줌. 사이트는 단지 마커 최소 줌 이상에서만 부른다')
    ] = 16
    complex_paging_request: Annotated[
        NaverComplexPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)')
    ] = Field(default_factory=NaverComplexPagingRequestModel, alias='complexPagingRequest')
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값')
    ] = Field(default='PC', alias='userChannelType')


class NaverArticleClusteredArticlesV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/clusteredArticles` 본문."""

    cluster_id: Annotated[
        str,
        Field(pattern=r'^\d+/\d+/\d+$', description='클러스터 ID ({zoom}/{x}/{y})')
    ] = Field(alias='clusterId')
    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='articleClusters 와 같은 필터')
    ]
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청')
    ] = Field(default_factory=NaverArticlePagingRequestModel, alias='articlePagingRequest')
