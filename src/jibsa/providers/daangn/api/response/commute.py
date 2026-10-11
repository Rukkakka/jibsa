"""응답 모델: 출퇴근 역 기준 매물 검색 (search commute)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCommuteStationArticleConnectionModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 출퇴근 (nearestCommuteStation, commuteFeed,
# commuteStationArticleConnection)
# ---------------------------------------------------------------------------

class DaangnNearestCommuteStationModel(ResponseModel):
    """회사에서 가장 가까운 역."""

    station_name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지)")
    ] = Field(alias='stationName')
    line_number: Annotated[
        list[str],
        Field(description='노선')
    ] = Field(default=[], alias='lineNumber')
    walking_minutes_to_station: Annotated[
        int | None,
        Field(description='회사에서 역까지 도보 (분)')
    ] = Field(default=None, alias='walkingMinutesToStation')


class DaangnNearestCommuteStationDataModel(ResponseModel):
    """GraphQL `data`."""

    nearest_commute_station: Annotated[
        DaangnNearestCommuteStationModel | None,
        Field(description='가장 가까운 역. 근처에 역이 없으면 null')
    ] = Field(default=None, alias='nearestCommuteStation')


class DaangnNearestCommuteStationResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `nearestCommuteStation` 응답."""

    data: Annotated[
        DaangnNearestCommuteStationDataModel | None,
        Field(description='결과')
    ] = None


class DaangnCommuteStationModel(ResponseModel):
    """출퇴근 피드의 역."""

    station_name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지)")
    ] = Field(alias='stationName')
    line_number: Annotated[
        list[str],
        Field(description='노선')
    ] = Field(default=[], alias='lineNumber')


class DaangnCommuteWaypointModel(ResponseModel):
    """경로의 역 하나 (타는 역·갈아타는 역·내리는 역)."""

    station_name: Annotated[
        str | None,
        Field(description='역 이름')
    ] = Field(default=None, alias='stationName')
    line_name: Annotated[
        str | None,
        Field(description='노선')
    ] = Field(default=None, alias='lineName')


class DaangnCommuteReachableStationModel(ResponseModel):
    """회사 역에서 지하철로 갈 수 있는 역."""

    duration_minutes: Annotated[
        int | None,
        Field(description='회사 역까지 지하철 시간 (분)')
    ] = Field(default=None, alias='durationMinutes')
    transfer_count: Annotated[
        int | None,
        Field(description='환승 횟수')
    ] = Field(default=None, alias='transferCount')
    route_waypoints: Annotated[
        list[DaangnCommuteWaypointModel],
        Field(description='경로')
    ] = Field(default=[], alias='routeWaypoints')
    station: Annotated[
        DaangnCommuteStationModel | None,
        Field(description='역')
    ] = None


class DaangnCommuteStationEdgeModel(ResponseModel):
    """출퇴근 피드 edge."""

    node: Annotated[
        DaangnCommuteReachableStationModel | None,
        Field(description='역')
    ] = None


class DaangnCommuteFeedModel(ResponseModel):
    """출퇴근 피드 연결. 지하철 시간이 짧은 순이다."""

    edges: Annotated[
        list[DaangnCommuteStationEdgeModel],
        Field(description='역')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnCommuteFeedDataModel(ResponseModel):
    """GraphQL `data`."""

    commute_feed: Annotated[
        DaangnCommuteFeedModel | None,
        Field(description='갈 수 있는 역')
    ] = Field(default=None, alias='commuteFeed')


class DaangnCommuteFeedResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `commuteFeed` 응답."""

    data: Annotated[
        DaangnCommuteFeedDataModel | None,
        Field(description='결과')
    ] = None


class DaangnCommuteStationArticleConnectionDataModel(ResponseModel):
    """GraphQL `data`."""

    commute_station_article_connection: Annotated[
        DaangnCommuteStationArticleConnectionModel | None,
        Field(description='역 주변 매물')
    ] = Field(default=None, alias='commuteStationArticleConnection')


class DaangnCommuteStationArticleConnectionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `commuteStationArticleConnection` 응답."""

    data: Annotated[
        DaangnCommuteStationArticleConnectionDataModel | None,
        Field(description='결과')
    ] = None
