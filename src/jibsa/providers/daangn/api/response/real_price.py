"""응답 모델: 단지·매물·지역 실거래가와 시세 추이 (real-price, region-real-price, price-trend)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnComplexRefModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRealsaleDanjiModel,
    DaangnTransactionConnectionModel,
    FloorText,
    LooseFloat,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId (단지 실거래가)
# ---------------------------------------------------------------------------

class DaangnComplexTransactionsModel(ResponseModel):
    """단지의 실거래 연결 두 개 (웹 쿼리의 별칭)."""

    buy_transactions: Annotated[
        DaangnTransactionConnectionModel | None,
        Field(description='매매', alias='buyTransactions')
    ] = None
    borrow_transactions: Annotated[
        DaangnTransactionConnectionModel | None,
        Field(description='전세·월세', alias='borrowTransactions')
    ] = None


class DaangnComplexByOriginalIdModel(ResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexTransactionsModel | None,
        Field(description='단지')
    ] = None


class DaangnComplexByOriginalIdDataModel(ResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexByOriginalIdModel | None,
        Field(description='단지 조회 결과', alias='complexByOriginalId')
    ] = None


class DaangnComplexByOriginalIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexByOriginalId` (단지 실거래가) 응답."""

    data: Annotated[
        DaangnComplexByOriginalIdDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleByOriginalArticleId (매물 실거래가)
# ---------------------------------------------------------------------------

class DaangnArticleByOriginalArticleIdDataModel(ResponseModel):
    """GraphQL `data`. 실거래 연결 모양은 단지 실거래가와 같다."""

    article_by_original_article_id: Annotated[
        DaangnComplexTransactionsModel | None,
        Field(description='매물 (실거래 연결만 받는다). 없는 매물이면 null 과 recordNotFound 에러', alias='articleByOriginalArticleId')
    ] = None


class DaangnArticleByOriginalArticleIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleByOriginalArticleId` (매물 실거래가) 응답."""

    data: Annotated[
        DaangnArticleByOriginalArticleIdDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — realsaleFeed / realsaleNewHighFeed (지역 실거래)
# ---------------------------------------------------------------------------

class DaangnRealsaleModel(ResponseModel):
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


class DaangnPriceInsightModel(ResponseModel):
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


class DaangnRealsaleFeedItemModel(ResponseModel):
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


class DaangnRealsaleFeedEdgeModel(ResponseModel):
    """지역 실거래 피드 edge."""

    node: Annotated[
        DaangnRealsaleFeedItemModel | None,
        Field(description='피드 칸')
    ] = None


class DaangnRealsaleFeedModel(ResponseModel):
    """지역 실거래 피드 연결."""

    edges: Annotated[
        list[DaangnRealsaleFeedEdgeModel],
        Field(description='피드 칸')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnRealsaleFeedDataModel(ResponseModel):
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


class DaangnRealsaleNewHighFeedDataModel(ResponseModel):
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


class DaangnRealsaleFeedSummaryModel(ResponseModel):
    """지역 실거래 화면 머리의 매매 요약 (`realsaleFeedSummary`)."""

    data_date: Annotated[
        str | None,
        Field(description='가장 최근 공개일 (YYYYMMDD)', alias='dataDate')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='그 공개일의 매매 거래 수', alias='saleCount')
    ] = None


class DaangnRealsaleNewHighSummaryModel(ResponseModel):
    """지역 실거래 화면 머리의 신고가 요약 (`realsaleNewHighFeedSummary`)."""

    new_high_count: Annotated[
        int | None,
        Field(description='가장 최근 공개일의 신고가 수', alias='newHighCount')
    ] = None


class DaangnRealsaleFeedSummaryDataModel(ResponseModel):
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


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — node(id:) { priceChart } (단지 시세 차트)
# ---------------------------------------------------------------------------

class DaangnPriceChartPointModel(ResponseModel):
    """월별 평균 실거래가 한 점. 거래가 없는 달은 오지 않는다. 금액은 **원** 단위다 (다른 당근 API 와 다르다)."""

    year_month: Annotated[
        str,
        Field(description="계약 연월 (YYYYMM, 예: '202608')", alias='yearMonth')
    ]
    average_amount: Annotated[
        float | None,
        Field(description='그 달 실거래 평균가 (원). 전세는 보증금', alias='averageAmount')
    ] = None
    transaction_count: Annotated[
        int | None,
        Field(description='그 달 거래 수', alias='transactionCount')
    ] = None


class DaangnKbSaleSummaryModel(ResponseModel):
    """시세 차트에 붙는 최근 KB 매매 시세 (`latestKbSale`). 금액은 **원** 단위다 (2026-11-12 실측: 역삼래미안 27억~29.1억)."""

    survey_base_date: Annotated[
        str | None,
        Field(description='KB 시세 조사 기준일 (YYYYMMDD)', alias='surveyBaseDate')
    ] = None
    lower: Annotated[
        float | None,
        Field(description='하위 평균가 (원)')
    ] = None
    upper: Annotated[
        float | None,
        Field(description='상위 평균가 (원)')
    ] = None


class DaangnPriceChartModel(ResponseModel):
    """단지 시세 차트."""

    average_points: Annotated[
        list[DaangnPriceChartPointModel],
        Field(description='월별 평균 (오래된 달부터)', alias='averagePoints')
    ] = []
    latest_kb_sale: Annotated[
        DaangnKbSaleSummaryModel | None,
        Field(description='최근 KB 매매 시세 (웹 그래프의 KB 시세 띠). 전세 그래프에도 매매 시세가 온다. 없으면 null', alias='latestKbSale')
    ] = None


class DaangnComplexPriceChartNodeModel(ResponseModel):
    """시세 그래프를 받은 단지 노드."""

    id: Annotated[
        str | None,
        Field(description='Relay 노드 ID')
    ] = None
    price_chart: Annotated[
        DaangnPriceChartModel | None,
        Field(description='시세 차트', alias='priceChart')
    ] = None


class DaangnComplexPriceChartDataModel(ResponseModel):
    """GraphQL `data`."""

    node: Annotated[
        DaangnComplexPriceChartNodeModel | None,
        Field(description='단지 노드. 없는 노드면 null')
    ] = None


class DaangnComplexPriceChartResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `node(id:) { priceChart }` 응답 (웹 `useTransactionComplexRefetchQuery`)."""

    data: Annotated[
        DaangnComplexPriceChartDataModel | None,
        Field(description='결과')
    ] = None
