"""응답 모델: 지역 최근 실거래 (region-trades)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import ZigbangBaseResponseModel

from typing import Annotated


class ZigbangLocalTradeModel(ZigbangBaseResponseModel):
    """지역 최근 실거래 한 건. 금액은 모두 만원 단위다. 거래 유형에 해당하지 않는 칸은 키가 없다 (월세료는 월세에만, 시세 대비는 매매에만).

    칸 이름은 2026-11-22 표본(매매·전세·월세)의 키와 같다. 전세 차액 칸(`charterPriceGap`·`charterPriceGapRate`)과 입주 전 계약 여부
    (`isPreMoveinCharterContract`)는 표본에 나타나지 않았지만 웹 번들(2026-11-19)이 읽는 이름으로 받아 둔다.
    """

    area_danji_id: Annotated[
        int | None,
        Field(description='단지 ID', alias='areaDanjiId')
    ] = None
    area_danji_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='areaDanjiName')
    ] = None
    room_type: Annotated[
        str | None,
        Field(description="평형 이름 (예: '110D', '83A')", alias='roomType')
    ] = None
    rt_deal_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)', alias='rtDealDate')
    ] = None
    local: Annotated[
        str | None,
        Field(description="구·동 이름 (예: '성동구 성수동1가'). 동 단위로 조회하면 빈 글자로 온다 (2026-11-22 표본). 구 조회는 동 이름만 온다 (2026-11-22 실측: 송파구 → '가락동')")
    ] = None
    is_new_highest: Annotated[
        bool | None,
        Field(description='신고가인지 (웹 배지)', alias='isNewHighest')
    ] = None
    is_new_lowest: Annotated[
        bool | None,
        Field(description='신저가인지 (웹 배지)', alias='isNewLowest')
    ] = None
    is_contract_renewal: Annotated[
        bool | None,
        Field(description="갱신 계약인지 (웹 '계약갱신' 배지)", alias='isContractRenewal')
    ] = None
    rt_price: Annotated[
        int | float | None,
        Field(description='매매가 또는 전세·월세 보증금 (만원)', alias='rtPrice')
    ] = None
    monthly_rent_price: Annotated[
        int | float | None,
        Field(description='월세 (만원). 월세 거래에만 온다', alias='monthlyRentPrice')
    ] = None
    offer_type: Annotated[
        str | None,
        Field(description="분양권·입주권 같은 거래 구분 ('분양권'·'입주권'). 해당할 때만 온다", alias='offerType')
    ] = None
    prev_rt_price_gap: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 차액 (만원, 0 이면 웹이 차이 없음)', alias='prevRtPriceGap')
    ] = None
    prev_rt_price_gap_rate: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%)', alias='prevRtPriceGapRate')
    ] = None
    market_price_gap: Annotated[
        int | float | None,
        Field(description='직방시세 대비 차액 (만원, 매매)', alias='marketPriceGap')
    ] = None
    market_price_gap_rate: Annotated[
        int | float | None,
        Field(description='직방시세 대비 변동률 (%)', alias='marketPriceGapRate')
    ] = None
    is_no_market_price_gap: Annotated[
        bool | None,
        Field(description="직방시세가 없는지 (참이거나 `offerType` 이 있으면 웹이 '직방시세 없음' 으로 보여 준다. 표본에서 참일 때 차액·변동률은 0 이었다)", alias='isNoMarketPriceGap')
    ] = None
    public_price_gap: Annotated[
        int | float | None,
        Field(description='공시가격 대비 차액 (만원, 매매)', alias='publicPriceGap')
    ] = None
    public_price_gap_rate: Annotated[
        int | float | None,
        Field(description='공시가격 대비 변동률 (%)', alias='publicPriceGapRate')
    ] = None
    is_no_public_price_gap: Annotated[
        bool | None,
        Field(description="공시가격이 없는지 (참이면 웹이 '공시가격 업데이트 예정' 으로 보여 준다)", alias='isNoPublicPriceGap')
    ] = None
    offer_price_gap: Annotated[
        int | float | None,
        Field(description='분양가 대비 차액 (만원, 분양권·입주권 매매)', alias='offerPriceGap')
    ] = None
    offer_price_gap_rate: Annotated[
        int | float | None,
        Field(description='분양가 대비 변동률 (%)', alias='offerPriceGapRate')
    ] = None
    is_no_offer_price_gap: Annotated[
        bool | None,
        Field(description='분양가 대비 값이 없는지 (참이면 웹은 분양가 대비 대신 직전 거래 대비를 보여 준다)', alias='isNoOfferPriceGap')
    ] = None
    charter_price_gap: Annotated[
        int | float | None,
        Field(description="전세 차액 (만원). 웹은 갱신 계약이면 '이전 전세가 대비', 아니면 '2년 전 평균 전세가 대비' 로 보여 준다", alias='charterPriceGap')
    ] = None
    charter_price_gap_rate: Annotated[
        int | float | None,
        Field(description='전세 차액의 변동률 (%)', alias='charterPriceGapRate')
    ] = None
    is_pre_movein_charter_contract: Annotated[
        bool | None,
        Field(description="입주 전 계약 거래인지 (참이면 웹이 차액 대신 '입주 전 계약 거래' 로 보여 준다)", alias='isPreMoveinCharterContract')
    ] = None


class ZigbangLocalTradesDataModel(ZigbangBaseResponseModel):
    """최근 실거래 쪽 하나. 키 이름이 `list` 라 `trades` 로 받는다 (속성 `list` 가 내장 `list` 를 가린다)."""

    trades: Annotated[
        list[ZigbangLocalTradeModel] | None,
        Field(description='이 쪽의 실거래. 끝 쪽을 넘기면 빈 목록이다 (2026-11-22 실측)', alias='list')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='기간 안 전체 건수', alias='totalCount')
    ] = None
    registration_info: Annotated[
        str | None,
        Field(description="기간과 등록 건수 문구 (예: '10. 23 ~ 11. 22 등록 135건')", alias='registrationInfo')
    ] = None
    is_updated: Annotated[
        bool | None,
        Field(description='갱신 여부', alias='isUpdated')
    ] = None


class ZigbangLocalsTradingHistoriesResponseModel(ZigbangBaseResponseModel):
    """지역 최근 실거래 응답. `data` 봉투에 싸여 온다."""

    data: Annotated[
        ZigbangLocalTradesDataModel | None,
        Field(description='최근 실거래 쪽')
    ] = None
