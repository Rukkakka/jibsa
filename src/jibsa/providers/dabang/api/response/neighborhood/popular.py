"""응답 모델: 동 안 인기 매물 (popular-listings)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangRoomItemModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangPopularRoomResultModel(DabangBaseResponseModel):
    """인기 매물 `result`. 매물 칸은 목록 칸과 같은 꼴이지만 동 번호·좌표가 없다."""

    list_: Annotated[
        list[DabangRoomItemModel],
        Field(description='선호도 높은 순 매물', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='순위가 있는 매물 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel(DabangV5ResponseModel[DabangPopularRoomResultModel]):
    """`GET /api/v5/region-info/room/regional/popular-room` 응답."""
