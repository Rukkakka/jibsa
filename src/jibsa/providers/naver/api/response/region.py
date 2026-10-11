"""응답 모델: 지역·역·단지 이름과 좌표 해석, 시·도·시·군·구 목록 (regions, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverCoordinatesModel,
    NaverResponseModel,
    T,
)

from typing import (
    Annotated,
    Generic,
)


class NaverAddressElementsModel(ResponseModel):
    """주소 구성 요소."""

    sido: Annotated[
        str | None,
        Field(description='시·도')
    ] = None
    sigugun: Annotated[
        str | None,
        Field(description='시·군·구')
    ] = None
    dongmyun: Annotated[
        str | None,
        Field(description='동·읍·면 (행정동일 수도 있다)')
    ] = None
    ri: Annotated[
        str | None,
        Field(description='리')
    ] = None
    jibun: Annotated[
        str | None,
        Field(description='번지')
    ] = None
    build_number: Annotated[
        str | None,
        Field(description='도로명 건물번호')
    ] = Field(default=None, alias='buildNumber')
    bcode: Annotated[
        str | None,
        Field(description='법정동 코드. 행정동(역삼1동 등)은 빈 문자열')
    ] = None


class NaverAddressModel(ResponseModel):
    """주소 검색 결과 한 곳."""

    full_address: Annotated[
        str | None,
        Field(description='전체 주소')
    ] = Field(default=None, alias='fullAddress')
    item_level: Annotated[
        int | None,
        Field(description='주소 단위. 5 시·도/시·군·구, 8 동·읍·면, 12 번지·건물')
    ] = Field(default=None, alias='itemLevel')
    x: Annotated[
        float | None,
        Field(description='경도')
    ] = None
    y: Annotated[
        float | None,
        Field(description='위도')
    ] = None
    address_elements: Annotated[
        NaverAddressElementsModel | None,
        Field(description='주소 구성 요소')
    ] = Field(default=None, alias='addressElements')


class NaverAddressListModel(ResponseModel):
    """지번 또는 도로명 주소 결과."""

    total_count: Annotated[
        int,
        Field(description='전체 결과 수')
    ] = Field(default=0, alias='totalCount')
    items: Annotated[
        list[NaverAddressModel],
        Field(description='결과 (앞 페이지)')
    ] = Field(default=[], alias='list')


class NaverAddressSearchModel(ResponseModel):
    """maps-search/address 결과. 못 찾으면 type 과 두 목록이 모두 null 이다."""

    type: Annotated[
        str | None,
        Field(description='jibun-address / road-address')
    ] = None
    jibun_address: Annotated[
        NaverAddressListModel | None,
        Field(description='지번 주소 결과')
    ] = Field(default=None, alias='jibunAddress')
    road_address: Annotated[
        NaverAddressListModel | None,
        Field(description='도로명 주소 결과')
    ] = Field(default=None, alias='roadAddress')


class NaverLegalDivisionInfoModel(ResponseModel):
    """지역 목록의 지역 하나 (시·도 목록, 하위 지역 목록)."""

    legal_division_number: Annotated[
        str,
        Field(description='법정동 코드 (10자리)')
    ] = Field(alias='legalDivisionNumber')
    legal_division_name: Annotated[
        str | None,
        Field(description='지역 이름 (하위 목록은 그 단위 이름만, 예: 개포동)')
    ] = Field(default=None, alias='legalDivisionName')
    legal_division_level_type: Annotated[
        str | None,
        Field(description='단위 (SI 시·도, GUN 시·군·구, EUP 읍·면·동)')
    ] = Field(default=None, alias='legalDivisionLevelType')
    city_full_name: Annotated[
        str | None,
        Field(description='시·도 정식 이름 (시·도 목록만, 예: 서울특별시)')
    ] = Field(default=None, alias='cityFullName')
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='중심 좌표')
    ] = None


class NaverAutocompletePageModel(ResponseModel, Generic[T]):
    """자동완성 결과 한 페이지. 사이트 검색창과 같은 순서로 온다."""

    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 여부')
    ] = Field(default=None, alias='hasNextPage')
    total_count: Annotated[
        int | None,
        Field(description='전체 결과 수')
    ] = Field(default=None, alias='totalCount')
    items: Annotated[
        list[T],
        Field(description='결과 목록')
    ] = Field(default=[], alias='list')


class NaverAutocompleteLegalDivisionModel(ResponseModel):
    """법정동 자동완성 결과. 시·구 단위도 온다 ('강남구' → 강남구 자신과 그 아래 동들)."""

    legal_division_number: Annotated[
        str,
        Field(description='법정동 코드 (10자리)')
    ] = Field(alias='legalDivisionNumber')
    legal_division_name: Annotated[
        str,
        Field(description='전체 이름 (예: 서울시 강남구 역삼동). 마지막 단어가 그 지역 이름')
    ] = Field(alias='legalDivisionName')
    legal_division_level_type: Annotated[
        str | None,
        Field(description='단위. EUP 읍·면·동, GUN 시·군·구 (그 위 단위 값은 미확인)')
    ] = Field(default=None, alias='legalDivisionLevelType')
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='중심 좌표')
    ] = None


class NaverSubwayLineModel(ResponseModel):
    """지하철 노선."""

    name: Annotated[
        str,
        Field(description='노선 이름 (예: 2호선, 신분당)')
    ]


class NaverAutocompleteSubwayStationModel(ResponseModel):
    """지하철역 자동완성 결과."""

    station_name: Annotated[
        str,
        Field(description='역 이름 (예: 강남역)')
    ] = Field(alias='stationName')
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='역 좌표')
    ] = None
    line_infos: Annotated[
        list[NaverSubwayLineModel],
        Field(description='지나는 노선')
    ] = Field(default=[], alias='lineInfos')


class NaverAutocompleteComplexModel(ResponseModel):
    """단지 자동완성 결과."""

    complex_number: Annotated[
        int,
        Field(description='단지 번호')
    ] = Field(alias='complexNumber')
    complex_name: Annotated[
        str,
        Field(description='단지 이름')
    ] = Field(alias='complexName')
    type: Annotated[
        str | None,
        Field(description='매물 유형 코드 (A01 아파트 등)')
    ] = None
    legal_division_name: Annotated[
        str | None,
        Field(description='단지가 있는 법정동 전체 이름')
    ] = Field(default=None, alias='legalDivisionName')
    legal_division_number: Annotated[
        str | None,
        Field(description='법정동 코드 (10자리)')
    ] = Field(default=None, alias='legalDivisionNumber')
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='단지 좌표')
    ] = None


class NaverSearchAutocompleteLegalDivisionsV1ResponseModel(
    NaverResponseModel[NaverAutocompletePageModel[NaverAutocompleteLegalDivisionModel]]
):
    """`GET /front-api/v1/search/autocomplete/legalDivisions` 응답."""


class NaverSearchAutocompleteSubwayStationsV1ResponseModel(
    NaverResponseModel[NaverAutocompletePageModel[NaverAutocompleteSubwayStationModel]]
):
    """`GET /front-api/v1/search/autocomplete/subwayStations` 응답."""


class NaverSearchAutocompleteComplexesV1ResponseModel(
    NaverResponseModel[NaverAutocompletePageModel[NaverAutocompleteComplexModel]]
):
    """`GET /front-api/v1/search/autocomplete/complexes` 응답."""


class NaverMapsSearchAddressV1ResponseModel(NaverResponseModel[NaverAddressSearchModel]):
    """`GET /front-api/v1/maps-search/address` 응답."""


class NaverLegalDivisionInfoListByLevelV1ResponseModel(NaverResponseModel[list[NaverLegalDivisionInfoModel]]):
    """`GET /front-api/v1/legalDivision/infoListByLevel` 응답."""


class NaverLegalDivisionSubInfoListV1ResponseModel(NaverResponseModel[list[NaverLegalDivisionInfoModel]]):
    """`GET /front-api/v1/legalDivision/subInfoList` 응답."""
