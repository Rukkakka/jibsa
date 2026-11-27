"""응답 모델: 재개발 구역 목록 (search redevelopment)."""

from pydantic import Field

from jibsa.providers.naver.api.models.response.common import (
    NaverBaseResponseModel,
    NaverCoordinatesModel,
    NaverRedevelopmentAreaPageModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverRedevelopmentAreaPinModel(NaverBaseResponseModel):
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


class NaverRedevelopmentAreaMarkersModel(NaverBaseResponseModel):
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
