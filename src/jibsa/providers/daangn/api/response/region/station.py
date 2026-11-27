"""응답 모델: 역 이름 검색 (search locations 의 역)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


class DaangnSubwayStationPoiModel(DaangnBaseResponseModel):
    """역 검색 결과 하나. 역 이름에 '역' 이 붙지 않는다 (예: 역삼)."""

    id: Annotated[
        str,
        Field(description='역 ID (subwayStationArticleConnection 에 넘긴다)')
    ]
    station_name: Annotated[
        str,
        Field(description='역 이름', alias='stationName')
    ]
    line_names: Annotated[
        list[str],
        Field(description='노선 (예: 서울2호선)', alias='lineNames')
    ] = []
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='역 좌표')
    ] = None


class DaangnSearchSubwayStationPoisDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_subway_station_pois: Annotated[
        list[DaangnSubwayStationPoiModel],
        Field(description='앞부분이 같은 역 (최대 50)', alias='searchSubwayStationPois')
    ] = []


class DaangnSearchSubwayStationPoisResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchSubwayStationPois` 응답."""

    data: Annotated[
        DaangnSearchSubwayStationPoisDataModel | None,
        Field(description='결과')
    ] = None
