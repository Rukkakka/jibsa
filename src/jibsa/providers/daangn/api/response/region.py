"""응답 모델: 지역·역·대학·좌표 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — getRegionByCoordinate
# ---------------------------------------------------------------------------

class DaangnGetRegionByCoordinateDataModel(ResponseModel):
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


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 지도 검색창의 지역·대학 검색 (searchRegion, searchSchoolPois)
# ---------------------------------------------------------------------------

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


class DaangnSearchRegionEdgeModel(ResponseModel):
    """지역 연결의 edge."""

    node: Annotated[
        DaangnSearchRegionNodeModel | None,
        Field(description='지역')
    ] = None


class DaangnSearchRegionConnectionModel(ResponseModel):
    """지역 연결."""

    edges: Annotated[
        list[DaangnSearchRegionEdgeModel],
        Field(description='지역 (시·도 → 구 → 동, 각각 가나다순)')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchRegionDataModel(ResponseModel):
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


class DaangnSchoolPoiModel(ResponseModel):
    """대학 검색 결과 하나 (캠퍼스 하나)."""

    id: Annotated[
        str,
        Field(description='대학 ID (universityArticleConnection 의 schoolPoiId 로 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='대학 이름. 캠퍼스가 여럿이면 모두 같다 (예: 연세대학교)')
    ]
    full_name: Annotated[
        str | None,
        Field(description='캠퍼스까지 붙인 이름 (예: 연세대학교 신촌캠퍼스). 캠퍼스가 하나뿐이면 null 이기도 하다', alias='fullName')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='대학 좌표')
    ] = None


class DaangnSchoolPoiEdgeModel(ResponseModel):
    """대학 연결의 edge."""

    node: Annotated[
        DaangnSchoolPoiModel | None,
        Field(description='대학')
    ] = None


class DaangnSchoolPoiConnectionModel(ResponseModel):
    """대학 연결."""

    edges: Annotated[
        list[DaangnSchoolPoiEdgeModel],
        Field(description='대학')
    ] = []


class DaangnSearchSchoolPoisDataModel(ResponseModel):
    """GraphQL `data`."""

    search_school_pois: Annotated[
        DaangnSchoolPoiConnectionModel | None,
        Field(description='대학 검색 결과', alias='searchSchoolPois')
    ] = None


class DaangnSearchSchoolPoisResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchSchoolPois` 응답."""

    data: Annotated[
        DaangnSearchSchoolPoisDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 역 검색
# ---------------------------------------------------------------------------

class DaangnSubwayStationPoiModel(ResponseModel):
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


class DaangnSearchSubwayStationPoisDataModel(ResponseModel):
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


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 주소 검색 (searchAddress) 과 주소 → 좌표 (unitByAddress)
# ---------------------------------------------------------------------------

class DaangnAddressModel(ResponseModel):
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


class DaangnAddressEdgeModel(ResponseModel):
    """주소 연결의 edge."""

    node: Annotated[
        DaangnAddressModel | None,
        Field(description='주소')
    ] = None


class DaangnAddressConnectionModel(ResponseModel):
    """주소 연결."""

    edges: Annotated[
        list[DaangnAddressEdgeModel],
        Field(description='주소 후보')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchAddressDataModel(ResponseModel):
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


class DaangnUnitPlaceModel(ResponseModel):
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


class DaangnUnitModel(ResponseModel):
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


class DaangnUnitByAddressOutputModel(ResponseModel):
    """`unitByAddress` 결과. 주소를 못 찾으면 `unit` 이 null 이다."""

    unit: Annotated[
        DaangnUnitModel | None,
        Field(description='주소의 위치')
    ] = None


class DaangnUnitByAddressDataModel(ResponseModel):
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
