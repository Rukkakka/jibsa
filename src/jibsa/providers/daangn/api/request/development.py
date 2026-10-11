"""요청 모델: 개발 호재 목록·상세 (developments, development)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel

from typing import (
    Annotated,
    Literal,
)


DaangnDevelopmentCategory = Literal['ROAD', 'RAIL', 'HOUSING']


class DaangnDevelopmentDistrictsInputModel(RequestModel):
    """`developmentDistricts` 의 `input`. 좌표 범위 안의 개발 사업을 모두 준다 (페이지 없음)."""

    sw_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='남서 꼭짓점')
    ] = Field(alias='swCoordinate')
    ne_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='북동 꼭짓점')
    ] = Field(alias='neCoordinate')
    categories: Annotated[
        list[DaangnDevelopmentCategory],
        Field(min_length=1, description='ROAD(도로) / RAIL(철도) / HOUSING(정비사업)')
    ]


class DaangnDevelopmentDistrictsRequestPayloadModel(RequestModel):
    """GraphQL `developmentDistricts` 쿼리 변수 (웹의 `DevelopmentDistrictOverlayQuery`, 지도 개발 호재)."""

    input: Annotated[
        DaangnDevelopmentDistrictsInputModel,
        Field(description='좌표 범위·분류')
    ]


class DaangnDevelopmentByBusiNoRequestPayloadModel(RequestModel):
    """GraphQL `developmentByBusiNo` 쿼리 변수 (웹의 `DevelopmentDetailQuery`, 개발 사업 상세)."""

    dev_busi_no: Annotated[
        int,
        Field(gt=0, description='사업 번호 (developmentDistricts 의 devBusiNo)')
    ] = Field(alias='devBusiNo')
