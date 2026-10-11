"""응답 모델: 아파트 실거래가 (real-price)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import ZigbangRoomTypeTitleModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/rt-prices, /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/rt-prices
# ---------------------------------------------------------------------------

class ZigbangRtPriceModel(ResponseModel):
    """실거래 한 건. 금액은 **만원** 이다."""

    rt_id: Annotated[
        int | None,
        Field(description='실거래 ID')
    ] = Field(default=None, alias='rtId')
    deal_date: Annotated[
        str | None,
        Field(description="계약일 ('26. 9. 8' 처럼 두 자리 연도)")
    ] = Field(default=None, alias='rtDealDate')
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = Field(default=None, alias='rtFloor')
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, 문자열로 온다)')
    ] = Field(default=None, alias='rtArea')
    deal_type: Annotated[
        str | None,
        Field(description='거래 유형 (sales 매매, charter 전세, rent 월세)')
    ] = Field(default=None, alias='rtDealType')
    price: Annotated[
        int | None,
        Field(description='매매가 또는 보증금·전세금 (만원)')
    ] = Field(default=None, alias='rtPrice')
    price_rent: Annotated[
        int | None,
        Field(description='월세 (만원, 월세만)')
    ] = Field(default=None, alias='rtPriceRent')
    room_type_id: Annotated[
        str | None,
        Field(description='평형 ID')
    ] = Field(default=None, alias='roomTypeId')
    area_infos: Annotated[
        list[ZigbangRoomTypeTitleModel],
        Field(description='평형 이름')
    ] = Field(default=[], alias='areaInfos')
    method: Annotated[
        str | None,
        Field(description='거래 방식 (relay 중개거래, 해제된 거래는 null)')
    ] = None
    offer_type: Annotated[
        str | None,
        Field(description='분양권·입주권 거래면 그 이름 (매매만)')
    ] = Field(default=None, alias='offerType')
    is_cancellation: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래')
    ] = Field(default=None, alias='isCancellation')


class ZigbangDanjisRtPricesResponseModel(ResponseModel):
    """단지 실거래가 한 쪽 (최근 계약 순)."""

    transactions: Annotated[
        list[ZigbangRtPriceModel],
        Field(description='이번 쪽의 실거래')
    ] = Field(default=[], alias='data')
    has_next: Annotated[
        bool,
        Field(description='다음 쪽이 있는지')
    ] = Field(default=False, alias='hasNext')
    pyeongs: Annotated[
        dict[str, list[ZigbangRoomTypeTitleModel]],
        Field(description='단지의 평형 ID → 평형 이름. 평형을 지정해도 단지 전체가 오고, 없는 단지면 비어 있다')
    ] = Field(default={}, alias='areaInfos')


class ZigbangDanjisRoomTypesRtPricesResponseModel(ZigbangDanjisRtPricesResponseModel):
    """평형 하나의 실거래가 한 쪽."""
