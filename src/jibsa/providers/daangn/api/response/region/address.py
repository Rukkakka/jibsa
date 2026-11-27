"""응답 모델: 도로명 주소 검색과 주소 → 좌표 (search locations 의 주소)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import Annotated


class DaangnAddressModel(DaangnBaseResponseModel):
    """도로명 주소 검색 결과 하나 (웹 검색창 주소 칸의 한 줄: 도로명 주소, 아래에 지번 주소)."""

    region_address: Annotated[
        str | None,
        Field(description="지번 주소 (예: '서울특별시 강남구 역삼동 737 강남파이낸스센터')", alias='regionAddress')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description="도로명 주소 (예: '서울특별시 강남구 테헤란로 152 (역삼동)')", alias='roadAddress')
    ] = None
    original_road_address: Annotated[
        str | None,
        Field(description='원본 도로명 주소. unitByAddress 에 그대로 보낸다', alias='originalRoadAddress')
    ] = None
    bd_mgt_sn: Annotated[
        str | None,
        Field(description='건물 관리 번호. unitByAddress 에 그대로 보낸다', alias='bdMgtSn')
    ] = None


class DaangnAddressEdgeModel(DaangnBaseResponseModel):
    """주소 연결의 edge."""

    node: Annotated[
        DaangnAddressModel | None,
        Field(description='주소')
    ] = None


class DaangnAddressConnectionModel(DaangnBaseResponseModel):
    """주소 연결."""

    edges: Annotated[
        list[DaangnAddressEdgeModel],
        Field(description='주소 후보')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchAddressDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_address: Annotated[
        DaangnAddressConnectionModel | None,
        Field(description='주소 검색 결과', alias='searchAddress')
    ] = None


class DaangnSearchAddressResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchAddress` 응답 (웹 `fetchAddressResultQuery`)."""

    data: Annotated[
        DaangnSearchAddressDataModel | None,
        Field(description='결과')
    ] = None


class DaangnUnitPlaceModel(DaangnBaseResponseModel):
    """주소에 있는 단지(`PropComplex`) 또는 건물(`PropBuilding`). 단지는 `name`, 건물은 `buildingName` 으로 온다."""

    id: Annotated[
        str | None,
        Field(description='Relay 노드 ID')
    ] = None
    original_id: Annotated[
        str | None,
        Field(description='숫자 ID (단지면 단지 ID)', alias='originalId')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름 (단지만)')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물 이름 (건물만)', alias='buildingName')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='좌표')
    ] = None


class DaangnUnitModel(DaangnBaseResponseModel):
    """주소의 위치. 웹은 `location`, 없으면 단지·건물 좌표를 쓴다 (MapShell `_s`)."""

    location: Annotated[
        DaangnCoordinateModel | None,
        Field(description='주소 좌표')
    ] = None
    complex: Annotated[
        DaangnUnitPlaceModel | None,
        Field(description='그 주소의 당근 단지. 없으면 null')
    ] = None
    building: Annotated[
        DaangnUnitPlaceModel | None,
        Field(description='그 주소의 건물. 없으면 null')
    ] = None


class DaangnUnitByAddressOutputModel(DaangnBaseResponseModel):
    """`unitByAddress` 결과. 주소를 못 찾으면 `unit` 이 null 이다."""

    unit: Annotated[
        DaangnUnitModel | None,
        Field(description='주소의 위치')
    ] = None


class DaangnUnitByAddressDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    unit_by_address: Annotated[
        DaangnUnitByAddressOutputModel | None,
        Field(description='주소 → 위치 결과', alias='unitByAddress')
    ] = None


class DaangnUnitByAddressResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `unitByAddress` 응답 (웹 `getPlaceByJusoAddressQuery`)."""

    data: Annotated[
        DaangnUnitByAddressDataModel | None,
        Field(description='결과')
    ] = None
