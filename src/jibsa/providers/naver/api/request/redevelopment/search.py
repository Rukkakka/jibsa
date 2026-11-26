"""요청 모델: 재개발 구역 목록 (search redevelopment)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverBoundingBoxModel,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


NaverRedevelopmentAreaSortType = Literal['ARTICLE_COUNT_DESC', 'HOUSEHOLD_NUMBER_DESC']
"""재개발 구역 목록 정렬. 매물수순, 세대수순 (사이트 RedevelopmentAreaPagingRequestDtoSortType, 2026-10-10)."""


class NaverRedevelopmentAreaPagingRequestModel(RequestModel):
    """재개발 구역 목록 페이지 요청. 첫 요청은 seed 없이 lastInfo [] 로 보낸다."""

    size: Annotated[
        int,
        Field(ge=1, le=30, description='페이지 크기. 31부터 400 (2026-10-10 확인)')
    ] = 30
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    sort_type: Annotated[
        NaverRedevelopmentAreaSortType,
        Field(description='정렬', alias='sortType')
    ] = 'ARTICLE_COUNT_DESC'
    seed: Annotated[
        str | None,
        Field(description='서버가 첫 응답에 주는 정렬 seed')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로', alias='lastInfo')
    ] = []


class NaverComplexRedevelopmentAreaListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/redevelopmentArea/list` 본문. 사각형 안 재개발 구역 (사이트 지도 옆 목록).

    줌이 결과를 바꾼다. 12 이하는 400, 13 이 가장 넓게 주고 높을수록 중심 근처만 준다 (한남동 반경 1km 사각형:
    13 → 17곳, 15 → 10곳, 16 → 7곳, 2026-10-10). service 는 반경 안을 빠뜨리지 않는 14 로 받고 마커 좌표로 반경 밖을 뺀다.
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터 (realEstateTypes F01)')
    ]
    bounding_box: Annotated[
        NaverBoundingBoxModel,
        Field(description='지도 뷰포트', alias='boundingBox')
    ]
    precision: Annotated[
        int,
        Field(ge=13, le=18, description='지도 줌. 12 이하는 400')
    ] = 14
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    redevelopment_area_paging_request: Annotated[
        NaverRedevelopmentAreaPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)', alias='redevelopmentAreaPagingRequest')
    ] = Field(default_factory=NaverRedevelopmentAreaPagingRequestModel)


class NaverComplexRedevelopmentAreaLegalDivisionListV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/redevelopmentArea/legalDivisionList` 본문. 법정동 하나 안의 재개발 구역.

    `filter.legalDivisionNumbers` 에 법정동 코드 하나, `legalDivisionType` 은 동이면 EUP (한남동 → 한남2·3구역, 2026-10-10),
    구·군이면 GUN (성동구 10곳, 2026-11-18. 구 단위 응답에는 `legalDivisionAddress` 가 없다).
    """

    filter: Annotated[
        NaverArticleFilterModel,
        Field(description='지도 필터 + 법정동 코드')
    ]
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
    redevelopment_area_paging_request: Annotated[
        NaverRedevelopmentAreaPagingRequestModel,
        Field(description='페이지 요청 (정렬 포함)', alias='redevelopmentAreaPagingRequest')
    ] = Field(default_factory=NaverRedevelopmentAreaPagingRequestModel)


class NaverComplexRedevelopmentAreaMarkersV1RequestPayloadModel(RequestModel):
    """`POST /front-api/v1/complex/redevelopmentArea/markers` 본문. 사각형 안 구역 마커 (좌표). 페이지 없이 다 준다."""

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
        Field(ge=13, le=18, description='지도 줌. 목록과 같은 값을 줘야 같은 구역이 온다')
    ] = 14
    user_channel_type: Annotated[
        Literal['PC'],
        Field(description='고정값', alias='userChannelType')
    ] = 'PC'
