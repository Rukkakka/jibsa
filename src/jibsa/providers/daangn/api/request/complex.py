"""요청 모델: 단지 정보·단지 이름 검색·지역 단지 목록·인기 단지·단지 매물 (complex, search complexes, trending-complexes, search listings --complex)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnComplexFilterModel,
    DaangnComplexTradeType,
    DaangnExclusiveUseAreaModel,
    DaangnLocationFilterModel,
    DaangnPropertyFilterModel,
)

from typing import (
    Annotated,
    Literal,
)


class DaangnComplexesRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/complexes/{originalId}` 경로."""

    original_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='숫자 단지 ID (PropComplex.originalId)')
    ]


class DaangnSearchComplexesInputModel(RequestModel):
    """`searchComplexes` 의 `input`."""

    name: Annotated[
        str,
        Field(min_length=1, description='단지 이름 (일부만 줘도 된다)')
    ]


class DaangnSearchComplexesRequestPayloadModel(RequestModel):
    """GraphQL `searchComplexes` 쿼리 변수 (웹의 `fetchComplexSearchResultQuery`)."""

    input: Annotated[
        DaangnSearchComplexesInputModel,
        Field(description='검색어')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 단지 수. 웹은 20')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None


class DaangnTrendingComplexesRequestPayloadModel(RequestModel):
    """GraphQL `trendingComplexes` 쿼리 변수 (웹의 `HomeTrendingComplexSectionListQuery`, 요즘 많이 보는 단지).

    지역 ID 는 문자열로 보내야 한다 (숫자면 "알 수 없는 오류"). 서버는 9곳쯤만 준다 (2026-10-10 실측).
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='받을 단지 수 (웹은 50)')
    ] = 50
    region_id: Annotated[
        str,
        Field(min_length=1, description='당근 지역 ID (동)', alias='regionId')
    ]


class DaangnComplexArticlesInputModel(RequestModel):
    """단지 매물 목록의 `input`."""

    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)


class DaangnComplexArticlesRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId { complex { articles } }` 쿼리 변수 (웹의 `ComplexArticleListPanelQuery`).

    루트 필드가 단지 실거래가와 같은 `complexByOriginalId` 라 action id 는 `complex_articles` 로 구분한다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 매물 수. 웹은 10')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnComplexArticlesInputModel,
        Field(description='매물 조건')
    ] = Field(default_factory=DaangnComplexArticlesInputModel)


DaangnComplexSort = Literal[
    'HOUSEHOLD_COUNT_DESC', 'TRADE_PRICE_DESC', 'TRADE_PRICE_ASC', 'MOVE_IN_DATE_DESC', 'MOVE_IN_DATE_ASC',
]


class DaangnRegionComplexesInputModel(RequestModel):
    """지역 단지 목록의 `input`."""

    location_filter: Annotated[
        DaangnLocationFilterModel,
        Field(description='지역 조건 (동 또는 구)', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnComplexFilterModel,
        Field(description='단지 조건', alias='propertyFilter')
    ] = Field(default_factory=DaangnComplexFilterModel)
    sort: Annotated[
        DaangnComplexSort,
        Field(description='정렬. 웹 기본은 세대수 많은 순')
    ] = 'HOUSEHOLD_COUNT_DESC'


class DaangnRegionComplexesRequestPayloadModel(RequestModel):
    """GraphQL `searchComplexes` 쿼리 변수 (웹의 `ComplexListPanelViewportQuery`, 지역 단지 목록).

    루트 필드가 단지 이름 검색과 같은 `searchComplexes` 라 action id 는 `region_complexes` 로 구분한다.
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 단지 수 (서버가 50 까지 준다)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnRegionComplexesInputModel,
        Field(description='지역·단지 조건·정렬')
    ]
    trade_type: Annotated[
        DaangnComplexTradeType,
        Field(description='단지마다 보여 줄 최근 실거래의 거래 유형. BORROW·MONTH 는 전월세가 섞여 온다', alias='tradeType')
    ] = 'BUY'
    exclusive_use_area: Annotated[
        DaangnExclusiveUseAreaModel | None,
        Field(description='최근 실거래의 전용면적 범위. 없으면 전체', alias='exclusiveUseArea')
    ] = None
