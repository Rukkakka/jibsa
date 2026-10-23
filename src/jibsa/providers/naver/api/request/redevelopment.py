"""요청 모델: 재개발 구역 목록·정보·매물 (search redevelopment, redevelopment, search listings --redevelopment)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
    NaverBoundingBoxModel,
    NaverPriceFilterModel,
    NaverTradeType,
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

    `filter.legalDivisionNumbers` 에 동 코드 하나, `legalDivisionType` 은 EUP (한남동 → 한남2·3구역, 2026-10-10).
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


class NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel(NaverPriceFilterModel):
    """`POST /front-api/v1/complex/redevelopmentArea/articleList` 본문. 재개발 구역 하나의 매물.

    페이지는 30건까지 (31부터 400). 가격 키·정렬은 단지 매물 목록과 같고 서버가 거른다
    (한남4구역 매매 41건 → 50억 이하 19건, 2026-10-10 확인). 원 단위다.
    """

    size: Annotated[
        int,
        Field(ge=1, le=30, description='페이지 크기')
    ] = 30
    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호 (redevelopmentArea/list 의 redevelopmentAreaNumber)', alias='redevelopmentAreaNumber')
    ]
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체', alias='tradeTypes')
    ] = []
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
        Field(description='첫 응답의 seed. 첫 요청은 빼고, 이후 그대로 넘긴다')
    ] = None
    last_info: Annotated[
        list[Any],
        Field(description='커서. 첫 요청은 [], 이후 응답의 lastInfo 를 그대로', alias='lastInfo')
    ] = []


class NaverComplexRedevelopmentV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/complex/redevelopment` 쿼리. 재개발 구역 하나의 기본 정보."""

    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호', alias='redevelopmentAreaNumber')
    ]


class NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel(NaverPriceFilterModel):
    """`GET /front-api/v1/complex/redevelopmentArea/articleStats` 쿼리. 구역 매물 수와 호가 범위.

    배열은 단지 매물 집계처럼 `tradeTypes[]=A1` 로 키에 `[]` 를 붙여 반복한다. 가격 키는 구역 매물 목록과 같고 원 단위다.
    """

    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호', alias='redevelopmentAreaNumber')
    ]
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체', alias='tradeTypes[]')
    ] = []
