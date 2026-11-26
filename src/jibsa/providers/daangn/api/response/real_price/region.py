"""응답 모델: 지역 실거래가 (region-real-price)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnComplexRefModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRealsaleDanjiModel,
    FloorText,
    LooseFloat,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — realsaleFeed / realsaleNewHighFeed (지역 실거래)
# ---------------------------------------------------------------------------

class DaangnRealsaleModel(DaangnBaseResponseModel):
    """지역 피드의 실거래 한 건. 금액은 **만원**, 날짜는 YYYYMMDD 문자열."""

    id: Annotated[
        str | None,
        Field(description='거래 ID')
    ] = None
    trade_type: Annotated[
        str | None,
        Field(description='SALE(매매) / BORROW(전월세, 월세가 0 이면 전세)', alias='tradeType')
    ] = None
    trade_price: Annotated[
        int | None,
        Field(description='매매가 (만원). 전월세는 0', alias='tradePrice')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (만원). 매매는 0')
    ] = None
    month_rent_fee: Annotated[
        int | None,
        Field(description='월세 (만원). 매매·전세는 0', alias='monthRentFee')
    ] = None
    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    floor: Annotated[
        FloorText,
        Field(description='층 (숫자로 온다)')
    ] = None
    contact_date: Annotated[
        str | None,
        Field(description='계약일 (YYYYMMDD)', alias='contactDate')
    ] = None
    cancel: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None
    transaction_type: Annotated[
        str | None,
        Field(description='BROKERED(중개거래) / DIRECT(직거래). 매매만', alias='transactionType')
    ] = None
    lease_contract_type: Annotated[
        str | None,
        Field(description='NEW / RENEWAL (전월세만)', alias='leaseContractType')
    ] = None



class DaangnPriceInsightModel(DaangnBaseResponseModel):
    """이전 최고가와의 비교 (매매)."""

    previous_max_price: Annotated[
        int | None,
        Field(description='이전 최고가 (만원)', alias='previousMaxPrice')
    ] = None
    previous_max_contact_date: Annotated[
        str | None,
        Field(description='이전 최고가 계약일 (YYYYMMDD)', alias='previousMaxContactDate')
    ] = None
    is_new_high: Annotated[
        bool | None,
        Field(description='신고가인지', alias='isNewHigh')
    ] = None



class DaangnRealsaleFeedItemModel(DaangnBaseResponseModel):
    """지역 실거래 피드 한 칸."""

    realsale: Annotated[
        DaangnRealsaleModel | None,
        Field(description='거래')
    ] = None
    data_date: Annotated[
        str | None,
        Field(description='공개일 (YYYYMMDD). 신고가 피드에는 없다', alias='dataDate')
    ] = None
    danji: Annotated[
        DaangnRealsaleDanjiModel | None,
        Field(description='건물·단지')
    ] = None
    complex: Annotated[
        DaangnComplexRefModel | None,
        Field(description='당근 단지 (daangn complex 로 이어 본다). 없으면 null')
    ] = None
    region_name: Annotated[
        str | None,
        Field(description="동까지의 주소 (예: '서울 강남구 역삼동')", alias='regionName')
    ] = None
    price_insight: Annotated[
        DaangnPriceInsightModel | None,
        Field(description='이전 최고가 비교 (매매)', alias='priceInsight')
    ] = None



class DaangnRealsaleFeedEdgeModel(DaangnBaseResponseModel):
    """지역 실거래 피드 edge."""

    node: Annotated[
        DaangnRealsaleFeedItemModel | None,
        Field(description='피드 칸')
    ] = None



class DaangnRealsaleFeedModel(DaangnBaseResponseModel):
    """지역 실거래 피드 연결."""

    edges: Annotated[
        list[DaangnRealsaleFeedEdgeModel],
        Field(description='피드 칸')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None



class DaangnRealsaleFeedDataModel(DaangnBaseResponseModel):
    """GraphQL `data` (`realsaleFeed`)."""

    realsale_feed: Annotated[
        DaangnRealsaleFeedModel | None,
        Field(description='최근 실거래', alias='realsaleFeed')
    ] = None



class DaangnRealsaleFeedResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `realsaleFeed` 응답."""

    data: Annotated[
        DaangnRealsaleFeedDataModel | None,
        Field(description='결과')
    ] = None



class DaangnRealsaleNewHighFeedDataModel(DaangnBaseResponseModel):
    """GraphQL `data` (`realsaleNewHighFeed`)."""

    realsale_new_high_feed: Annotated[
        DaangnRealsaleFeedModel | None,
        Field(description='신고가 매매', alias='realsaleNewHighFeed')
    ] = None



class DaangnRealsaleNewHighFeedResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `realsaleNewHighFeed` 응답."""

    data: Annotated[
        DaangnRealsaleNewHighFeedDataModel | None,
        Field(description='결과')
    ] = None



class DaangnRealsaleFeedSummaryModel(DaangnBaseResponseModel):
    """지역 실거래 화면 머리의 매매 요약 (`realsaleFeedSummary`)."""

    data_date: Annotated[
        str | None,
        Field(description='가장 최근 공개일 (YYYYMMDD)', alias='dataDate')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='그 공개일의 매매 거래 수', alias='saleCount')
    ] = None



class DaangnRealsaleNewHighSummaryModel(DaangnBaseResponseModel):
    """지역 실거래 화면 머리의 신고가 요약 (`realsaleNewHighFeedSummary`)."""

    new_high_count: Annotated[
        int | None,
        Field(description='가장 최근 공개일의 신고가 수', alias='newHighCount')
    ] = None



class DaangnRealsaleFeedSummaryDataModel(DaangnBaseResponseModel):
    """GraphQL `data` (`realsaleFeedSummary` + `realsaleNewHighFeedSummary`)."""

    realsale_feed_summary: Annotated[
        DaangnRealsaleFeedSummaryModel | None,
        Field(description='매매 요약', alias='realsaleFeedSummary')
    ] = None
    realsale_new_high_feed_summary: Annotated[
        DaangnRealsaleNewHighSummaryModel | None,
        Field(description='신고가 요약', alias='realsaleNewHighFeedSummary')
    ] = None



class DaangnRealsaleFeedSummaryResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `realsaleFeedSummary` 응답 (웹 `RealsaleFeedTitleSummaryQuery`)."""

    data: Annotated[
        DaangnRealsaleFeedSummaryDataModel | None,
        Field(description='결과')
    ] = None
