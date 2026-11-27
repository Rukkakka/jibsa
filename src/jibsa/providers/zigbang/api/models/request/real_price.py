"""요청 모델: 아파트 실거래가 (real-price)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


ZigbangRtDealType = Literal['sales', 'rent', 'all']


class ZigbangDanjisRtPricesRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/rt-prices` 경로 + 쿼리. 단지 실거래가 (국토부 신고, 최근 계약 순).

    `offset` 은 건너뛸 건수가 아니라 쪽 번호(0부터)다. 쪽 크기는 `limit` 이다.
    """

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어가며 쿼리로는 보내지 않는다')
    ]
    deal_type: Annotated[
        ZigbangRtDealType,
        Field(description="거래 유형 (sales 매매, rent 전세·월세, all 전체). 'trade'·'charter' 는 400 이다", alias='dealType')
    ]
    offset: Annotated[
        int,
        Field(ge=0, description='쪽 번호 (0부터)')
    ] = 0
    limit: Annotated[
        int,
        Field(ge=1, le=200, description='쪽 크기')
    ] = 50


class ZigbangDanjisRoomTypesRtPricesRequestParameterModel(ZigbangDanjisRtPricesRequestParameterModel):
    """`GET /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/rt-prices` 경로 + 쿼리. 평형 하나의 실거래가."""

    room_type_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='평형 ID (complex 의 pyeongs[].id). 경로에 들어간다')
    ]
