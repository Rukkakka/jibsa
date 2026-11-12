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


class DaangnCommuteStationsRequestPayloadModel(RequestModel):
    """GraphQL `commuteStations` 쿼리 변수 (웹의 `CommuteMapViewPinsQuery`, 회사 역에서 지하철로 갈 수 있고 매물 조건에 맞는 매물이 있는
    역 전부. 2026-11-13 실측: 강남역 조건 없음 411곳, 아파트 전세 285곳, 연세 0곳).

    웹 출퇴근 지도는 역 핀·'보고 있는 지역' 탭·역 상세의 시간을 이 쿼리 하나로 받고(useNearestStation 의 `u`), 가까운 순 목록만
    `commuteFeed` 로 20곳씩 넘긴다. 페이지가 없어 갈 수 있는 역(서버 상한 지하철 60분)이 한 번에 온다. 예전에는 `commuteFeed` 를
    50곳씩 4쪽까지 넘기며 시간 순이라는 실측 전제로 앞부분을 끊었다 (#215, 2026-11-12 번들 대조).
    """

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
