"""응답 모델: 동 안 핫플레이스 (hot-places)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangHotPlaceModel(DabangBaseResponseModel):
    """핫플레이스 식당 하나. 사진 주소(`thumbnail`)와 요리 종류 코드(`cuisineType`, 웹은 사진이 없을 때 아이콘만 고른다)도 오지만
    모델에 두지 않는다.
    """

    restaurant_name: Annotated[
        str | None,
        Field(description='식당 이름', alias='restaurantName')
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (없으면 웹은 '주소 정보를 확인하고 있어요.')")
    ] = None
    label_list: Annotated[
        list[str] | None,
        Field(description="꼬리표 ('한식(일반한식)', '솥밥'). null 이면 꼬리표 없음으로 읽는다", alias='labelList')
    ] = None
    type: Annotated[
        str | None,
        Field(description="가이드 ('MICHELIN_GUIDE' 미쉐린, 'BLUE_RIBBON' 블루리본)")
    ] = None


class DabangHotPlacesResultModel(DabangBaseResponseModel):
    """핫플레이스 `result`."""

    update_date: Annotated[
        str | None,
        Field(description="기준 달 ('26.05')", alias='updateDate')
    ] = None
    list_: Annotated[
        list[DabangHotPlaceModel] | None,
        Field(description='식당. null 이면 빈 쪽으로 읽는다', alias='list')
    ] = None
    total: Annotated[
        int | None,
        Field(description='전체 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRegionInfoHotPlacesV5ResponseModel(DabangV5ResponseModel[DabangHotPlacesResultModel]):
    """`GET /api/v5/region-info/hot-places` 응답."""
