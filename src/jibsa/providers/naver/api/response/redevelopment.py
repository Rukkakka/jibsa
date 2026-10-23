"""응답 모델: 재개발 구역 목록·정보·매물 (search redevelopment, redevelopment, search listings --redevelopment)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverBuildingRatioInfoModel,
    NaverComplexArticleStatsModel,
    NaverCoordinatesModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverRedevelopmentModel(ResponseModel):
    """재개발 구역 하나의 기본 정보. 조합 전화번호와 좌표도 오지만 쓰지 않는다."""

    name: Annotated[
        str | None,
        Field(description='구역 이름')
    ] = None
    legal_division_address: Annotated[
        str | None,
        Field(description='대표 법정동 (예: 서울시 용산구 한남동)', alias='legalDivisionAddress')
    ] = None
    total_household_number: Annotated[
        int | None,
        Field(description='계획 세대수', alias='totalHouseholdNumber')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사', alias='constructionCompany')
    ] = None
    building_ratio_info: Annotated[
        NaverBuildingRatioInfoModel | None,
        Field(description='계획 용적률·건폐율', alias='buildingRatioInfo')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 이주및철거)', alias='businessStep')
    ] = None


class NaverRedevelopmentAreaPinModel(ResponseModel):
    """재개발 구역 지도 마커. 반경 안인지 가리는 데만 쓰고 좌표는 출력하지 않는다."""

    redevelopment_area_number: Annotated[
        int,
        Field(description='구역 번호', alias='redevelopmentAreaNumber')
    ]
    coordinates: Annotated[
        NaverCoordinatesModel | None,
        Field(description='구역 대표 좌표')
    ] = None
    legal_division_name: Annotated[
        str | None,
        Field(description='구역이 속한 법정동 (예: 서울시 용산구 이태원동)', alias='legalDivisionName')
    ] = None


class NaverRedevelopmentAreaMarkersModel(ResponseModel):
    """재개발 구역 마커 목록. 페이지 없이 사각형 안을 다 준다."""

    total_count: Annotated[
        int,
        Field(description='마커 수', alias='totalCount')
    ] = 0
    pins: Annotated[
        list[NaverRedevelopmentAreaPinModel],
        Field(description='마커')
    ] = []


class NaverComplexRedevelopmentAreaListV1ResponseModel(NaverResponseModel[NaverRedevelopmentAreaPageModel]):
    """`POST /front-api/v1/complex/redevelopmentArea/list` 응답."""


class NaverComplexRedevelopmentAreaLegalDivisionListV1ResponseModel(NaverResponseModel[NaverRedevelopmentAreaPageModel]):
    """`POST /front-api/v1/complex/redevelopmentArea/legalDivisionList` 응답."""


class NaverComplexRedevelopmentAreaMarkersV1ResponseModel(NaverResponseModel[NaverRedevelopmentAreaMarkersModel]):
    """`POST /front-api/v1/complex/redevelopmentArea/markers` 응답."""


class NaverComplexRedevelopmentAreaArticleListV1ResponseModel(NaverResponseModel[NaverArticlePageModel]):
    """`POST /front-api/v1/complex/redevelopmentArea/articleList` 응답."""


class NaverComplexRedevelopmentV1ResponseModel(NaverResponseModel[NaverRedevelopmentModel]):
    """`GET /front-api/v1/complex/redevelopment` 응답."""


class NaverComplexRedevelopmentAreaArticleStatsV1ResponseModel(NaverResponseModel[NaverComplexArticleStatsModel]):
    """`GET /front-api/v1/complex/redevelopmentArea/articleStats` 응답. 단지 매물 통계와 같은 모양이다."""
