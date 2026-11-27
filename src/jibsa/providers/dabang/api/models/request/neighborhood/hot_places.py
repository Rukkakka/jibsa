"""요청 모델: 동 안 핫플레이스 (hot-places)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    REGION_INFO_PAGE_LIMIT,
)

from typing import (
    Annotated,
    Literal,
)


DabangHotPlaceType = Literal['ALL', 'MICHELIN_GUIDE', 'BLUE_RIBBON']


class DabangRegionInfoHotPlacesV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/hot-places` 쿼리 (동 안 미쉐린·블루리본 식당, 웹 동네정보 '핫플레이스').

    Args:
        region_gid: 다방 동 번호.
        type: 'ALL' 전체, 'MICHELIN_GUIDE' 미쉐린, 'BLUE_RIBBON' 블루리본 (웹 고르기 값).
        limit: 한 쪽 수 (웹 값 30).
        page: 쪽 번호 (1부터).
    """

    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]
    type: Annotated[
        DabangHotPlaceType,
        Field(description='가이드 종류')
    ] = 'ALL'
    limit: Annotated[
        int,
        Field(ge=1, le=REGION_INFO_PAGE_LIMIT, description='한 쪽 수')
    ] = REGION_INFO_PAGE_LIMIT
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
