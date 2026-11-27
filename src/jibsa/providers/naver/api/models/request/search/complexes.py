"""요청 모델: 지역 단지 목록 (search complexes)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.models.request.common import (
    NaverArticleFilterModel,
    NaverBoundingBoxModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


NaverComplexSortType = Literal['POPULARITY_DESC', 'HOUSEHOLD_NUMBER_DESC', 'USE_APPROVAL_DATE_DESC', 'ARTICLE_COUNT_DESC']
"""단지 목록 정렬. 인기순, 세대수순, 최근입주순, 매물수순 (사이트 COMPLEX_LIST_SORT_TYPE, 2026-10-09)."""


class NaverComplexPagingRequestModel(RequestModel):
    """단지 목록 페이지 요청. 첫 요청은 seed 없이 lastInfo [] 로 보낸다."""

    size: Annotated[
        int,
        Field(ge=1, le=30, description='페이지 크기. 사이트 COMPLEX_PAGINATION_SIZE 30')
    ] = 30
    complex_sort_type: Annotated[
        NaverComplexSortType,
        Field(description='정렬', alias='complexSortType')
    ] = 'POPULARITY_DESC'
    seed: Annotated[
        str | None,
        Field(description='서버가 첫 응답에 주는 정렬 seed')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로', alias='lastInfo')
    ] = []


class NaverComplexLegalDivisionComplexListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/legalDivisionComplexList` 본문. 법정동 하나의 단지 전체.

    `filter.legalDivisionNumbers` 에 법정동 코드 하나, `legalDivisionType` 은 동이면 EUP, 구·군이면 GUN (성동구 아파트
    148곳, 2026-11-18). 지도 필터가 그대로 걸리고
    `hasArticle` 이면 매물 있는 단지만 준다 (역삼동 아파트 160 → 114곳, 2026-10-09 확인).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터 + 법정동 코드')
    ]
    complex_paging_request: Annotated[
        NaverComplexPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)', alias='complexPagingRequest')
    ] = Field(default_factory=NaverComplexPagingRequestModel)
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'


class NaverComplexBoundedComplexesV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/boundedComplexes` 본문. 사각형 안 단지 (사이트 지도 옆 단지 목록)."""

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트', alias='boundingBox')
    ]
    precision: Annotated[
        int,
        Field(ge=10, le=18, description='지도 줌. 높을수록 중심 근처만 줘서 반경에 맞춰 고른다 (service.search.common.bounded_precision)')
    ] = 16
    complex_paging_request: Annotated[
        NaverComplexPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)', alias='complexPagingRequest')
    ] = Field(default_factory=NaverComplexPagingRequestModel)
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
