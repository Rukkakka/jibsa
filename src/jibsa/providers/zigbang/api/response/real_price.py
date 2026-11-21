"""응답 모델: 아파트 실거래가 (real-price)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangRoomTypeTitleModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/rt-prices, /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/rt-prices
# ---------------------------------------------------------------------------

class ZigbangRtPriceModel(ResponseModel):
    """실거래 한 건. 금액은 **만원** 이다."""

    rt_id: Annotated[
        int | None,
        Field(description='실거래 ID', alias='rtId')
    ] = None
    deal_date: Annotated[
        str | None,
        Field(description="계약일 ('26. 9. 8' 처럼 두 자리 연도)", alias='rtDealDate')
    ] = None
    floor: Annotated[
        int | None,
        Field(description='층', alias='rtFloor')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, 문자열로 온다)', alias='rtArea')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='거래 유형 (sales 매매, charter 전세, rent 월세)', alias='rtDealType')
    ] = None
    price: Annotated[
        int | None,
        Field(description='매매가 또는 보증금·전세금 (만원)', alias='rtPrice')
    ] = None
    price_rent: Annotated[
        int | None,
        Field(description='월세 (만원, 월세만)', alias='rtPriceRent')
    ] = None
    room_type_id: Annotated[
        str | None,
        Field(description='평형 ID', alias='roomTypeId')
    ] = None
    area_infos: Annotated[
        list[ZigbangRoomTypeTitleModel],
        Field(description='평형 이름', alias='areaInfos')
    ] = []
    method: Annotated[
        str | None,
        Field(description='거래 방식 (relay 중개거래, 해제된 거래는 null)')
    ] = None
    offer_type: Annotated[
        str | None,
        Field(description='분양권·입주권 거래면 그 이름 (매매만)', alias='offerType')
    ] = None
    is_cancellation: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래', alias='isCancellation')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description="동 ('132' 처럼 '동' 없이 온다). 키는 늘 있고 값은 매매에만 온다 (전월세는 null)", alias='dongName')
    ] = None
    is_registration: Annotated[
        bool | None,
        Field(description='등기까지 마무리된 거래 (매매만, 2023년 1월 이후 계약부터 표시, 참일 때만 키가 온다)', alias='isRegistration')
    ] = None
    is_new_highest: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 높은 거래가를 경신한 거래 (매매·전세, 참일 때만 키가 온다)', alias='isNewHighest')
    ] = None
    is_new_lowest: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 낮은 거래가를 경신한 거래 (매매·전세, 참일 때만 키가 온다)', alias='isNewLowest')
    ] = None
    pyn_price: Annotated[
        int | None,
        Field(description='공급면적 3.3㎡당 가격 (만원, 직방이 계산해 반올림한 값, 매매만)', alias='pynPrice')
    ] = None
    charter_rate: Annotated[
        float | None,
        Field(description='전세가율 (0~1 비율, 자르지 않은 값). 전세이고 평형을 지정한 조회에서만 온다', alias='charterRate')
    ] = None
    offer_price_diff: Annotated[
        int | None,
        Field(description='분양가 대비 차액 (만원, 양수면 거래가가 분양가보다 높다). 분양권 매매에서만 온다', alias='offerPriceDiff')
    ] = None


class ZigbangDanjisRtPricesResponseModel(ResponseModel):
    """단지 실거래가 한 쪽 (최근 계약 순)."""

    transactions: Annotated[
        list[ZigbangRtPriceModel],
        Field(description='이번 쪽의 실거래', alias='data')
    ] = []
    has_next: Annotated[
        bool,
        Field(description='다음 쪽이 있는지', alias='hasNext')
    ] = False
    pyeongs: Annotated[
        dict[str, list[ZigbangRoomTypeTitleModel]],
        Field(description='단지의 평형 ID → 평형 이름. 평형을 지정해도 단지 전체가 오고, 없는 단지면 비어 있다', alias='areaInfos')
    ] = {}


class ZigbangDanjisRoomTypesRtPricesResponseModel(ZigbangDanjisRtPricesResponseModel):
    """평형 하나의 실거래가 한 쪽."""
