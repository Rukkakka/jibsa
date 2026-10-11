"""요청 모델: 지역·역·단지 이름과 좌표 해석, 시·도·시·군·구 목록 (regions, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


class NaverLegalDivisionInfoListByLevelV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/legalDivision/infoListByLevel` 쿼리. 그 단위의 지역 전부 (SI 면 시·도 17곳)."""

    region_level_type: Annotated[
        Literal['SI'],
        Field(description='지역 단위. 시·도만 쓴다')
    ] = Field(default='SI', alias='regionLevelType')


class NaverLegalDivisionSubInfoListV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/legalDivision/subInfoList` 쿼리. 지역 하나의 바로 아래 지역.

    단위는 하위 목록을 볼 지역의 단위다. 시·도 코드에 SI 면 시·군·구, 시·군·구 코드에 GUN 이면 읍·면·동을 준다.
    구 코드에 SI 를 주면 그 구가 속한 시·도의 구를 준다. GU 는 400 이다 (2026-10-10 확인).
    """

    legal_division_level_type: Annotated[
        Literal['SI', 'GUN'],
        Field(description='지역 단위 (SI 시·도, GUN 시·군·구)')
    ] = Field(alias='legalDivisionLevelType')
    legal_division_number: Annotated[
        str,
        Field(pattern=r'^\d{10}$', description='법정동 코드')
    ] = Field(alias='legalDivisionNumber')


class NaverMapsSearchAddressV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/maps-search/address` 쿼리. 사이트 검색창의 주소 검색이다.

    지번(역삼동 719-28)·도로명(테헤란로 152)·동(역삼동)·시군구(강남구)를 찾는다. 역·단지 이름은 찾지 못한다.
    """

    query: Annotated[
        str,
        Field(min_length=1, description='주소')
    ]
    show_match_level: Annotated[
        bool,
        Field(description='결과에 matchLevel 을 붙인다 (사이트 기본값)')
    ] = Field(default=True, alias='showMatchLevel')


class NaverSearchAutocompleteRequestParameterModel(RequestModel):
    """자동완성 계열 GET 엔드포인트가 공유하는 쿼리."""

    keyword: Annotated[
        str,
        Field(min_length=1, description='검색어')
    ]
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0


class NaverSearchAutocompleteLegalDivisionsV1RequestParameterModel(NaverSearchAutocompleteRequestParameterModel):
    """`GET /front-api/v1/search/autocomplete/legalDivisions` 쿼리."""


class NaverSearchAutocompleteSubwayStationsV1RequestParameterModel(NaverSearchAutocompleteRequestParameterModel):
    """`GET /front-api/v1/search/autocomplete/subwayStations` 쿼리."""


class NaverSearchAutocompleteComplexesV1RequestParameterModel(NaverSearchAutocompleteRequestParameterModel):
    """`GET /front-api/v1/search/autocomplete/complexes` 쿼리."""
