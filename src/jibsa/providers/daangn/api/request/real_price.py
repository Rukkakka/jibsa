"""요청 모델: 단지·매물·지역 실거래가와 시세 추이 (real-price, region-real-price, price-trend)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnExclusiveUseAreaModel

from typing import (
    Annotated,
    Literal,
)


class DaangnComplexByOriginalIdRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId` 쿼리 변수 (웹의 `useTransactionComplexPagination_Query`, 단지 실거래가).

    매매(`buy*`)와 전월세(`borrow*`)를 한 번에 받는다. 웹처럼 두 연결의 크기를 모두 보낸다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]
    buy_first: Annotated[
        int,
        Field(ge=1, le=100, description='매매 거래 수 (서버는 100 까지 준다)', alias='buyFirst')
    ] = 1
    buy_after: Annotated[
        str | None,
        Field(description='매매 다음 페이지 커서', alias='buyAfter')
    ] = None
    borrow_first: Annotated[
        int,
        Field(ge=1, le=100, description='전월세 거래 수 (서버는 100 까지 준다)', alias='borrowFirst')
    ] = 1
    borrow_after: Annotated[
        str | None,
        Field(description='전월세 다음 페이지 커서', alias='borrowAfter')
    ] = None
    exclusive_use_area_group: Annotated[
        int | None,
        Field(gt=0, description='전용면적 묶음 (단지 평형의 전용면적 ㎡ 정수, 예: 84). 없으면 전체', alias='exclusiveUseAreaGroup')
    ] = None


class DaangnArticleByOriginalArticleIdRequestPayloadModel(RequestModel):
    """GraphQL `articleByOriginalArticleId` 쿼리 변수 (웹의 `useTransactionArticlePagination_Query`, 매물 실거래가).

    매물이 있는 건물(단지)의 비슷한 면적 실거래를 매매(`buy*`)·전월세(`borrow*`)로 나눠 받는다.
    """

    article_id: Annotated[
        str,
        Field(min_length=1, description='숫자 매물 ID', alias='articleId')
    ]
    buy_first: Annotated[
        int,
        Field(ge=1, le=100, description='매매 거래 수', alias='buyFirst')
    ] = 1
    buy_after: Annotated[
        str | None,
        Field(description='매매 다음 페이지 커서', alias='buyAfter')
    ] = None
    borrow_first: Annotated[
        int,
        Field(ge=1, le=100, description='전월세 거래 수', alias='borrowFirst')
    ] = 1
    borrow_after: Annotated[
        str | None,
        Field(description='전월세 다음 페이지 커서', alias='borrowAfter')
    ] = None


DaangnRealsaleTradeType = Literal['SALE', 'BORROW']
DaangnRealsaleSort = Literal['LATEST', 'TRADE_PRICE_DESC']


class DaangnRealsaleFeedInputModel(RequestModel):
    """`realsaleFeed` 의 `input`."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동 또는 구)', alias='regionId')
    ]
    trade_type: Annotated[
        DaangnRealsaleTradeType | None,
        Field(description='SALE(매매) / BORROW(전월세). 없으면 둘 다. 전세·월세를 따로 고르는 값은 없다', alias='tradeType')
    ] = None
    sort: Annotated[
        DaangnRealsaleSort | None,
        Field(description='LATEST(최근 공개 순) / TRADE_PRICE_DESC(가격 높은 순, SALE 만. BORROW 와 함께면 "알 수 없는 오류")')
    ] = None
    include_previous_days: Annotated[
        bool,
        Field(description='False 면 가장 최근 공개일의 거래만 온다. 웹 지역 패널처럼 이전 공개일까지 받는다', alias='includePreviousDays')
    ] = True


class DaangnRealsaleFeedRequestPayloadModel(RequestModel):
    """GraphQL `realsaleFeed` 쿼리 변수 (웹의 `RealsaleFeedListQuery`, 지역 최근 실거래)."""

    count: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 거래 수')
    ] = 20
    cursor: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnRealsaleFeedInputModel,
        Field(description='지역·거래 유형·정렬')
    ]


class DaangnRealsaleNewHighFeedInputModel(RequestModel):
    """`realsaleNewHighFeed` 의 `input`. 신고가는 매매만이라 거래 유형이 없다."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동 또는 구)', alias='regionId')
    ]
    sort: Annotated[
        DaangnRealsaleSort,
        Field(description='웹은 TRADE_PRICE_DESC 로 보낸다')
    ] = 'TRADE_PRICE_DESC'
    include_previous_days: Annotated[
        bool,
        Field(
            description='False(웹 기본)면 가장 최근 공개일의 신고가만 와서 그날 신고가가 없으면 빈 목록이다. 이전 공개일까지 받는다 '
            '(2026-10-11 실측: 강남구·송파구 등 6곳 모두 빈 목록, 이 값을 켜면 강남구 9~10월 신고가가 왔다)',
            alias='includePreviousDays'
        )
    ] = True


class DaangnRealsaleNewHighFeedRequestPayloadModel(RequestModel):
    """GraphQL `realsaleNewHighFeed` 쿼리 변수 (웹의 `NewHighFeedListQuery`, 지역 신고가)."""

    count: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 거래 수')
    ] = 20
    cursor: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnRealsaleNewHighFeedInputModel,
        Field(description='지역')
    ]


DaangnPriceChartTradeType = Literal['BUY', 'BORROW']


class DaangnComplexPriceChartRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId { complex { priceChart } }` 쿼리 변수 (웹의 `ComplexComparePriceChartQuery`, 단지 시세 차트).

    루트 필드가 단지 실거래가·단지 매물 목록과 같은 `complexByOriginalId` 라 action id 는
    `complex_price_chart` 로 구분한다. 웹 쿼리는 늘 15년(180개월)치를 받는다.
    """

    original_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='originalId')
    ]
    chart_trade_types: Annotated[
        list[DaangnPriceChartTradeType],
        Field(min_length=1, max_length=1, description='BUY(매매) 또는 BORROW(전세). 웹은 하나만 보낸다', alias='chartTradeTypes')
    ]
    exclude_monthly_rent: Annotated[
        bool,
        Field(description='전세(BORROW)에서 월세를 뺄지. 웹은 전세면 True, 매매면 False', alias='excludeMonthlyRent')
    ]
    skip_chart: Annotated[
        bool,
        Field(description='True 면 차트를 받지 않는다. 웹은 매매·전세면 False', alias='skipChart')
    ] = False
    exclusive_use_area: Annotated[
        DaangnExclusiveUseAreaModel | None,
        Field(description='전용면적 범위. 웹은 평형의 전용면적 정수 n 으로 {min: n, max: n + 1} 을 보낸다. 없으면 전 평형', alias='exclusiveUseArea')
    ] = None
