"""요청 모델: 지도 매물 검색 (search listings)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverBoundingBoxModel,
)
from jibsa.providers.naver.api.request.search.base import (
    NaverArticlePagingRequestModel,
)

from typing import (
    Annotated,
    Literal,
)


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
        Field(description='지도 뷰포트', alias='boundingBox')
    ]
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='지도 줌. 높을수록 중심 근처만 줘서 반경에 맞춰 고른다 (service.common.functions.bounded_precision)')
    ] = 16
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)', alias='articlePagingRequest')
    ] = Field(default_factory=NaverArticlePagingRequestModel)
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'


class NaverArticleLegalDivisionArticleListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/article/legalDivisionArticleList` 본문. 법정동 하나의 매물 전체를 정렬해 준다.

    `filter.legalDivisionNumbers` 에 법정동 코드 하나, `legalDivisionType` 은 동이면 EUP, 구·군이면 GUN 이다 ('GU' 는
    400, 성동구 GUN 전세 totalCount 1103·seed/lastInfo 쪽 나눔이 동과 같다, 2026-11-18). 페이지는 30건까지 (50부터 400).
    지도 필터가 그대로 걸린다 (2026-10-09 확인).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='articleClusters 와 같은 필터 + 법정동 코드')
    ]
    article_paging_request: Annotated[
        NaverArticlePagingRequestModel,
        Field(description='페이지 요청 (정렬 포함, size 30 이하)', alias='articlePagingRequest')
    ] = Field(default_factory=NaverArticlePagingRequestModel)
