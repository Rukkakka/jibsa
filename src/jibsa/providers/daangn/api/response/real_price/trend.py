"""응답 모델: 시세 추이 (price-trend)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — node(id:) { priceChart } (단지 시세 차트)
# ---------------------------------------------------------------------------

class DaangnPriceChartPointModel(DaangnBaseResponseModel):
    """월별 평균 실거래가 한 점. 거래가 없는 달은 오지 않는다. 금액은 **원** 단위다 (다른 당근 API 와 다르다)."""

    year_month: Annotated[
        str | None,
        Field(description="계약 연월 (YYYYMM, 예: '202608'). 값이 없으면 null·빈 문자열·'-' 로 올 수 있다", alias='yearMonth')
    ] = None
    average_amount: Annotated[
        float | None,
        Field(description='그 달 실거래 평균가 (원). 전세는 보증금', alias='averageAmount')
    ] = None
    transaction_count: Annotated[
        int | None,
        Field(description='그 달 거래 수', alias='transactionCount')
    ] = None



class DaangnKbSaleSummaryModel(DaangnBaseResponseModel):
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



class DaangnPriceChartModel(DaangnBaseResponseModel):
    """단지 시세 차트."""

    average_points: Annotated[
        list[DaangnPriceChartPointModel] | None,
        Field(description='월별 평균 (오래된 달부터). null 이면 그래프 자료를 주지 않은 것 (모름)', alias='averagePoints')
    ] = []
    latest_kb_sale: Annotated[
        DaangnKbSaleSummaryModel | None,
        Field(description='최근 KB 매매 시세 (웹 그래프의 KB 시세 띠). 전세 그래프에도 매매 시세가 온다. 없으면 null', alias='latestKbSale')
    ] = None



class DaangnComplexPriceChartNodeModel(DaangnBaseResponseModel):
    """시세 그래프를 받은 단지 노드."""

    id: Annotated[
        str | None,
        Field(description='Relay 노드 ID')
    ] = None
    price_chart: Annotated[
        DaangnPriceChartModel | None,
        Field(description='시세 차트', alias='priceChart')
    ] = None



class DaangnComplexPriceChartDataModel(DaangnBaseResponseModel):
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
