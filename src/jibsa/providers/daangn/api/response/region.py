"""응답 모델: 동네·역·주소·좌표 해석과 실거래 지역 (search locations, 모든 검색의 지역 해석)."""

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
# GET www.daangn.com/kr/api/v1/regions/keyword
# ---------------------------------------------------------------------------

class DaangnLocationModel(ResponseModel):
    """당근 지역 한 건."""

    id: Annotated[
        int,
        Field(description='지역 ID')
    ]
    name: Annotated[
        str,
        Field(description='지역 이름')
    ]
    name1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    name2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    name3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    name1_id: Annotated[
        int | None,
        Field(description='시/도 ID. 구가 없는 세종 전체를 조회할 때 쓴다 (세종은 name2Id 가 0)', alias='name1Id')
    ] = None
    name2_id: Annotated[
        int | None,
        Field(description='시/군/구 ID. 같은 구의 동을 모을 때 쓴다', alias='name2Id')
    ] = None
    depth: Annotated[
        int,
        Field(description='행정 단계. 3 이면 동/읍/면')
    ]


class DaangnRegionsKeywordV1ResponseModel(ResponseModel):
    """지역명 검색 응답."""

    locations: Annotated[
        list[DaangnLocationModel],
        Field(description='후보 지역. 동명이 여러 지역에 있으면 여러 개')
    ] = []


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
# POST realty.kr.karrotmarket.com/graphql — 역·주소 검색, 역 주변 매물
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


class DaangnAddressModel(ResponseModel):
    """주소 검색 결과 하나."""

    region_address: Annotated[
        str | None,
        Field(description='지번 주소 (건물 이름이 붙기도 한다)', alias='regionAddress')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소 (괄호 안에 동·건물 이름)', alias='roadAddress')
    ] = None


class DaangnAddressEdgeModel(ResponseModel):
    """주소 연결의 edge."""

    node: Annotated[
        DaangnAddressModel | None,
        Field(description='주소')
    ] = None


class DaangnSearchAddressModel(ResponseModel):
    """주소 연결."""

    edges: Annotated[
        list[DaangnAddressEdgeModel],
        Field(description='주소')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchAddressDataModel(ResponseModel):
    """GraphQL `data`."""

    search_address: Annotated[
        DaangnSearchAddressModel | None,
        Field(description='주소 검색 결과', alias='searchAddress')
    ] = None


class DaangnSearchAddressResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchAddress` 응답."""

    data: Annotated[
        DaangnSearchAddressDataModel | None,
        Field(description='결과')
    ] = None


class DaangnGeocodedAddressModel(ResponseModel):
    """주소 → 좌표 결과."""

    point: Annotated[
        DaangnCoordinateModel | None,
        Field(description='좌표')
    ] = None


class DaangnGeocodeAddressDataModel(ResponseModel):
    """GraphQL `data`."""

    geocode_address: Annotated[
        DaangnGeocodedAddressModel | None,
        Field(description='좌표. 주소가 아니면 null', alias='geocodeAddress')
    ] = None


class DaangnGeocodeAddressResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `geocodeAddress` 응답."""

    data: Annotated[
        DaangnGeocodeAddressDataModel | None,
        Field(description='결과')
    ] = None
