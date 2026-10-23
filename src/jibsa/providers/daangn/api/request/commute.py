"""요청 모델: 출퇴근 역 기준 매물 검색 (search commute)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnCoordinateInputModel,
    DaangnPropertyFilterModel,
)

from typing import Annotated


class DaangnNearestCommuteStationRequestPayloadModel(RequestModel):
    """GraphQL `nearestCommuteStation` 쿼리 변수 (웹의 `CommuteMapViewNearestQuery`, 회사에서 가장 가까운 역)."""

    coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='회사 좌표')
    ]


class DaangnCommuteFeedRequestPayloadModel(RequestModel):
    """GraphQL `commuteFeed` 쿼리 변수 (웹의 `CommuteMapViewFeedPaginationQuery`).

    첫 페이지용 `CommuteMapViewFeedQuery` 는 `after` 를 무시해 늘 첫 페이지를 주므로 페이지 넘김 쿼리를 쓴다.
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 역 수')
    ] = 50
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    from_station_name: Annotated[
        str,
        Field(min_length=1, description="출발(회사) 역 이름 ('역' 까지, 예: 강남역)", alias='fromStationName')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)


class DaangnCommuteStationArticleConnectionRequestPayloadModel(RequestModel):
    """GraphQL `commuteStationArticleConnection` 쿼리 변수 (웹의 `CommuteStationDetailPaginationQuery`, 역 주변 매물).

    첫 페이지용 `CommuteStationDetailQuery` 와 결과가 같고 `after` 를 받아 페이지 넘김 쿼리 하나만 쓴다.
    """

    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 매물 수 (서버는 100 까지 준다)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    station_name: Annotated[
        str,
        Field(min_length=1, description="역 이름 ('역' 까지, 예: 신논현역)", alias='stationName')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
