"""요청 모델: 시세 추이 (price-trend)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnExclusiveUseAreaModel

from typing import (
    Annotated,
    Literal,
)


DaangnPriceChartTradeType = Literal['BUY', 'BORROW']



class DaangnComplexPriceChartRequestPayloadModel(RequestModel):
    """GraphQL `node(id:) { ... on PropComplex { priceChart } }` 쿼리 변수 (웹 단지 화면의 `useTransactionComplexRefetchQuery`).

    웹 단지 화면의 시세 그래프다. 쿼리가 늘 15년(periodMonths 180)치를 받는다. 아파트형 단지는 고른 공급 평형의 평형 타입
    코드(`ptpCds`)로, 그 밖은 전용면적 묶음 g 로 `exclusiveUseAreaGroup: g`·`exclusiveUseArea: {min: g, max: g + 1}` 를 보낸다
    (2026-11-12 번들 대조). 루트가 `node` 라 action id 는 `complex_price_chart` 로 부른다. 예전에 쓰던 단지 비교 화면의 차트
    (`ComplexComparePriceChartQuery`)는 전용면적으로만 거를 수 있어 32평·33평이 한 그래프에 섞였다 (#215).
    """

    id: Annotated[
        str,
        Field(min_length=1, description='단지 Relay 노드 ID (단지 비교 칸 쿼리의 id)')
    ]
    chart_trade_type: Annotated[
        DaangnPriceChartTradeType,
        Field(description='BUY(매매) 또는 BORROW(전세)', alias='chartTradeType')
    ]
    ptp_cds: Annotated[
        list[int] | None,
        Field(description='평형 타입 코드 (아파트형 단지의 공급 평형 묶음)', alias='ptpCds')
    ] = None
    exclusive_use_area_group: Annotated[
        int | None,
        Field(gt=0, description='전용면적 묶음 (㎡ 정수)', alias='exclusiveUseAreaGroup')
    ] = None
    exclusive_use_area: Annotated[
        DaangnExclusiveUseAreaModel | None,
        Field(description='전용면적 범위. 전용면적 묶음 g 면 {min: g, max: g + 1}', alias='exclusiveUseArea')
    ] = None
