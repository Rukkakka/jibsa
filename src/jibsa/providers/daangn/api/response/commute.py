"""응답 모델: 출퇴근 역 기준 매물 검색 (search commute)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCommuteStationArticleConnectionModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 출퇴근 (nearestCommuteStation, commuteStations,
# commuteStationArticleConnection)
# ---------------------------------------------------------------------------

class DaangnNearestCommuteStationModel(ResponseModel):
    """회사에서 가장 가까운 역."""

    station_name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지)", alias='stationName')
    ]
    line_number: Annotated[
        list[str],
        Field(description='노선', alias='lineNumber')
    ] = []
    walking_minutes_to_station: Annotated[
        int | None,
        Field(description='회사에서 역까지 도보 (분)', alias='walkingMinutesToStation')
    ] = None


class DaangnNearestCommuteStationDataModel(ResponseModel):
    """GraphQL `data`."""

    nearest_commute_station: Annotated[
        DaangnNearestCommuteStationModel | None,
        Field(description='가장 가까운 역. 근처에 역이 없으면 null', alias='nearestCommuteStation')
    ] = None


class DaangnNearestCommuteStationResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `nearestCommuteStation` 응답."""

    data: Annotated[
        DaangnNearestCommuteStationDataModel | None,
        Field(description='결과')
    ] = None


class DaangnCommuteStationModel(ResponseModel):
    """`commuteStations` 항목의 역 (`DaangnCommuteReachableStationModel.station`)."""

    station_name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지)", alias='stationName')
    ]
    line_number: Annotated[
        list[str],
        Field(description='노선', alias='lineNumber')
    ] = []


class DaangnCommuteWaypointModel(ResponseModel):
    """경로의 역 하나 (회사 역·갈아타는 역·타는 역)."""

    station_name: Annotated[
        str | None,
        Field(description="역 이름 ('역' 까지)", alias='stationName')
    ] = None
    line_name: Annotated[
        str | None,
        Field(description='이 역에서 경로의 다음 역까지 구간의 노선. 마지막 역(타는 역)은 앞 구간 노선을 되풀이한다', alias='lineName')
    ] = None


class DaangnCommuteReachableStationModel(ResponseModel):
    """회사 역에서 지하철로 갈 수 있는 역."""

    duration_minutes: Annotated[
        int | None,
        Field(description='회사 역까지 지하철 시간 (분)', alias='durationMinutes')
    ] = None
    transfer_count: Annotated[
        int | None,
        Field(description='환승 횟수', alias='transferCount')
    ] = None
    route_waypoints: Annotated[
        list[DaangnCommuteWaypointModel],
        Field(description='경로: 회사 역에서 시작해 갈아타는 역을 지나 타는 역(station)에서 끝난다. 역 수 = 환승 + 2', alias='routeWaypoints')
    ] = []
    station: Annotated[
        DaangnCommuteStationModel | None,
        Field(description='역')
    ] = None


class DaangnCommuteStationsDataModel(ResponseModel):
    """GraphQL `data`."""

    commute_stations: Annotated[
        list[DaangnCommuteReachableStationModel] | None,
        Field(description='회사 역에서 지하철로 갈 수 있는 역 전부 (서버 상한 60분). 순서는 정해져 있지 않다', alias='commuteStations')
    ] = None


class DaangnCommuteStationsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `commuteStations` 응답."""

    data: Annotated[
        DaangnCommuteStationsDataModel | None,
        Field(description='결과')
    ] = None


class DaangnCommuteStationArticleConnectionDataModel(ResponseModel):
    """GraphQL `data`."""

    commute_station_article_connection: Annotated[
        DaangnCommuteStationArticleConnectionModel | None,
        Field(description='역 주변 매물', alias='commuteStationArticleConnection')
    ] = None


class DaangnCommuteStationArticleConnectionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `commuteStationArticleConnection` 응답."""

    data: Annotated[
        DaangnCommuteStationArticleConnectionDataModel | None,
        Field(description='결과')
    ] = None
