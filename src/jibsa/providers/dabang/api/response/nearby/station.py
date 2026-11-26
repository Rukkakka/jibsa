"""응답 모델: 역 둘레 평균 매물가 (station-prices)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangAveragePriceModel(DabangBaseResponseModel):
    """역(또는 동) 둘레 평균 매물가 한 칸. 웹은 '평균 매물가' 로 보여 준다 (지금 올라온 매물 가격의 평균, map 청크).

    Args:
        building_category: HOUSE_VILLA·OFFICETEL·APT.
        room_type: ONE_ROOM·TWO_ROOM.
        lease: 전세 평균 ('2억1333', 만원 글자). 없으면 null.
        monthly_rent: 월세 평균 ('7937/65' 보증금/월세). 없으면 null.
    """

    building_category: Annotated[
        str | None,
        Field(description='건물 유형', alias='buildingCategory')
    ] = None
    room_type: Annotated[
        str | None,
        Field(description='방 개수', alias='roomType')
    ] = None
    lease: Annotated[
        str | None,
        Field(description='전세 평균 (만원 글자)')
    ] = None
    monthly_rent: Annotated[
        str | None,
        Field(description='월세 평균 (보증금/월세 만원 글자)', alias='monthlyRent')
    ] = None


class DabangMarkerStationModel(DabangBaseResponseModel):
    """지도 집계의 역 표시 하나."""

    id: Annotated[
        int,
        Field(description='역 번호')
    ]
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    radius: Annotated[
        int | None,
        Field(description='역 반경 (m)')
    ] = None
    average_price_list: Annotated[
        list[DabangAveragePriceModel] | None,
        Field(description='평균 매물가 (원룸·투룸 집계에만 온다)', alias='averagePriceList')
    ] = None


class DabangMarkersResultModel(DabangBaseResponseModel):
    """지도 집계 `result` (동·칸·단지 표시도 오지만 jibsa 는 역 표시만 쓴다)."""

    subway_list: Annotated[
        list[DabangMarkerStationModel],
        Field(description='역 표시', alias='subwayList')
    ] = []


class DabangMarkersCategoryV5ResponseModel(DabangV5ResponseModel[DabangMarkersResultModel]):
    """`GET /api/v5/markers/category/{category}` 응답."""
