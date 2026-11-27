"""응답 모델: 지역 이름 검색과 좌표로 지역 찾기 (search locations, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.providers.daangn.api.models.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionModel,
)

from typing import Annotated


class DaangnGetRegionByCoordinateDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    get_region_by_coordinate: Annotated[
        DaangnRegionModel | None,
        Field(description='좌표가 속한 가장 작은 지역 (보통 동, depth 3). 바다 등이면 null', alias='getRegionByCoordinate')
    ] = None


class DaangnGetRegionByCoordinateResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `getRegionByCoordinate` 응답."""

    data: Annotated[
        DaangnGetRegionByCoordinateDataModel | None,
        Field(description='결과')
    ] = None


class DaangnSearchRegionNodeModel(DaangnRegionModel):
    """지역 검색 결과 하나. 법정동(depth 3)·구(2)·시·도(1)다.

    구가 있는 시의 구는 name2 에 시 이름이 붙는다 ('수원시 권선구'). 시 자체('수원시')는 따로 오지 않는다. 구가 없는 세종의
    동은 name2 가 '' 이고 parentRegion 이 null 이다 (2026-11-11 실측).
    """

    name: Annotated[
        str,
        Field(description='지역 이름 (동은 동 이름, 구는 name2, 시·도는 name1)')
    ]
    map_view_default_zoom_level: Annotated[
        int | None,
        Field(description='웹 지도가 이 지역을 열 때의 레벨. 줌은 19 에서 이 값을 뺀다 (동 5 → 14, 구 7 → 12, 시·도 9 → 10)', alias='mapViewDefaultZoomLevel')
    ] = None


class DaangnSearchRegionEdgeModel(DaangnBaseResponseModel):
    """지역 연결의 edge."""

    node: Annotated[
        DaangnSearchRegionNodeModel | None,
        Field(description='지역')
    ] = None


class DaangnSearchRegionConnectionModel(DaangnBaseResponseModel):
    """지역 연결."""

    edges: Annotated[
        list[DaangnSearchRegionEdgeModel],
        Field(description='지역 (시·도 → 구 → 동, 각각 가나다순)')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchRegionDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_region: Annotated[
        DaangnSearchRegionConnectionModel | None,
        Field(description='지역 검색 결과', alias='searchRegion')
    ] = None


class DaangnSearchRegionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchRegion` 응답."""

    data: Annotated[
        DaangnSearchRegionDataModel | None,
        Field(description='결과')
    ] = None
