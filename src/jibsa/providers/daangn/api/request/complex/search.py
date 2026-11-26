"""요청 모델: 단지 이름 검색·지역·지도 범위 단지 목록 (search complexes)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnBoundsLocationFilterModel,
    DaangnComplexFilterModel,
    DaangnComplexTradeType,
    DaangnExclusiveUseAreaModel,
)

from typing import (
    Annotated,
    Literal,
)


DaangnComplexSort = Literal[
    'HOUSEHOLD_COUNT_DESC', 'TRADE_PRICE_DESC', 'TRADE_PRICE_ASC', 'MOVE_IN_DATE_DESC', 'MOVE_IN_DATE_ASC',
]



class DaangnComplexByClusterIdInputModel(RequestModel):
    """동·구 단지 목록의 `input` (웹 지도 단지 탭에서 지역 거품을 누른 목록)."""

    cluster_id: Annotated[
        str,
        Field(pattern=r'^REGION:\d+$', description="지역 클러스터 ID ('REGION:<동·구 ID>')", alias='clusterId')
    ]
    property_filter: Annotated[
        DaangnComplexFilterModel,
        Field(description='단지 조건', alias='propertyFilter')
    ] = Field(default_factory=DaangnComplexFilterModel)
    sort: Annotated[
        DaangnComplexSort,
        Field(description='정렬. 웹 기본은 세대수 많은 순')
    ] = 'HOUSEHOLD_COUNT_DESC'



class DaangnComplexByClusterIdRequestPayloadModel(RequestModel):
    """GraphQL `complexByClusterId` 쿼리 변수 (웹의 `ComplexListPanelClusterPaginationQuery`, 동·구 단지 목록).

    웹은 매물 필터를 건 지도에서만 `listingFilter` 를 함께 보내고 기본은 null 이라 보내지 않는다 (2026-11-12 번들 대조).
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 단지 수 (서버가 50 까지 준다, 웹은 20)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnComplexByClusterIdInputModel,
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



class DaangnSearchComplexesViewportInputModel(RequestModel):
    """지도 범위 단지 목록의 `input` (웹 지도 단지 탭의 '이 영역 단지' 목록, `searchComplexes`).

    동·구 클러스터 목록(`DaangnComplexByClusterIdInputModel`)과 조건·정렬이 같고 클러스터 ID 자리에 화면 범위가 온다
    (ComplexListPanel `Z`: `input:{locationFilter, ...complexFilter, sort}`. 범위는 북동·남서 꼭짓점만이고 매물 목록의
    `resolution` 은 없다, 2026-11-12 번들 대조).
    """

    location_filter: Annotated[
        DaangnBoundsLocationFilterModel,
        Field(description='지도 화면의 좌표 범위', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnComplexFilterModel,
        Field(description='단지 조건', alias='propertyFilter')
    ] = Field(default_factory=DaangnComplexFilterModel)
    sort: Annotated[
        DaangnComplexSort,
        Field(description='정렬. 웹 기본은 세대수 많은 순')
    ] = 'HOUSEHOLD_COUNT_DESC'



class DaangnSearchComplexesViewportRequestPayloadModel(RequestModel):
    """GraphQL `searchComplexes` 쿼리 변수 (웹의 `ComplexListPanelViewportQuery`·`ComplexListPanelViewportPaginationQuery`, 지도 범위 단지 목록).

    단지 이름 검색(`DaangnSearchComplexesRequestPayloadModel`)과 루트 필드가 같지만 변수가 다른 다른 오퍼레이션이다.
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 단지 수 (웹은 20)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnSearchComplexesViewportInputModel,
        Field(description='화면 범위·단지 조건·정렬')
    ]
    trade_type: Annotated[
        DaangnComplexTradeType,
        Field(description='단지마다 보여 줄 최근 실거래의 거래 유형', alias='tradeType')
    ] = 'BUY'
    exclusive_use_area: Annotated[
        DaangnExclusiveUseAreaModel | None,
        Field(description='최근 실거래의 전용면적 범위. 없으면 전체', alias='exclusiveUseArea')
    ] = None
