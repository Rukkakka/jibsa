"""요청 모델: 동 안 인기 매물 (popular-listings)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    DabangRoomBuildingCategory,
)

from typing import (
    Annotated,
    Literal,
)


DabangPopularPriceType = Literal['MONTHLY_RENT', 'LEASE', 'SALE']
# 인기 매물 한 번에 받을 수 있는 수 (웹은 30, 50 까지 확인, 2026-10-25)
POPULAR_ROOM_PAGE_LIMIT: int = 50


class DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/room/regional/popular-room` 쿼리 (동 안 인기 매물).

    Args:
        region_gid: 다방 동 번호.
        building_category_list: 매물 유형 (주택·빌라, 오피스텔, 아파트). 같은 키를 값마다 반복해 보낸다.
        price_type_list: 거래 유형.
        sort: 선호도 높은 순 (웹 값 'DESC').
        limit: 한 쪽 매물 수 (최대 50).
        page: 쪽 번호 (1부터).
    """

    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]
    building_category_list: Annotated[
        list[DabangRoomBuildingCategory],
        Field(min_length=1, description='매물 유형', alias='buildingCategoryList')
    ] = ['HOUSE_VILLA', 'OFFICETEL', 'APT']
    price_type_list: Annotated[
        list[DabangPopularPriceType],
        Field(min_length=1, description='거래 유형', alias='priceTypeList')
    ] = ['MONTHLY_RENT', 'LEASE', 'SALE']
    sort: Annotated[
        Literal['DESC'],
        Field(description='선호도 높은 순')
    ] = 'DESC'
    limit: Annotated[
        int,
        Field(ge=1, le=POPULAR_ROOM_PAGE_LIMIT, description='한 쪽 매물 수')
    ] = POPULAR_ROOM_PAGE_LIMIT
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
