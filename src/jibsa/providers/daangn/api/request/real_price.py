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
    ptp_cds: Annotated[
        list[int] | None,
        Field(
            description='평형 타입 코드. 웹은 아파트형 단지의 공급 평형을 이것으로 고르고 exclusiveUseAreaGroup 을 비운다 (2026-11-12 번들)',
            alias='ptpCds',
        )
    ] = None
    trade_year_month: Annotated[
        str | None,
        Field(
            pattern=r'^\d{6}$',
            description=(
                "계약 연월 (YYYYMM, 예: '202608'). 웹 단지 화면의 시세 그래프에서 달을 누르면 그 달 거래만 보여 주는 변수다 "
                '(ComplexTopicPanel `pe` 가 그래프 점의 yearMonth 를 그대로 보낸다). 없으면 전체 기간'
            ),
            alias='tradeYearMonth',
        )
    ] = None


class DaangnArticleByOriginalArticleIdRequestPayloadModel(RequestModel):
    """GraphQL `articleByOriginalArticleId` 쿼리 변수 (웹의 `useTransactionArticlePagination_Query`, 매물 실거래가).

    매물이 있는 건물(단지)의 비슷한 면적 실거래를 매매(`buy*`)·전월세(`borrow*`)로 나눠 받는다. 단지 실거래와 달리 계약 연월
    (`tradeYearMonth`) 변수가 없다 (2026-11-12 번들 대조: 변수는 articleId·buy*·borrow* 뿐).
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
            description='False 면 가장 최근 공개일의 신고가만 와서 그날 신고가가 없으면 빈 목록이다. 웹 신고가 화면(NewHighFeedListQuery)은 '
            '이 값을 보내지 않아(False) 기본은 웹과 같다. True 는 이전 공개일 신고가까지 받는 jibsa 옵션(--previous-days)이다 '
            '(2026-10-11 실측: 강남구·송파구 등 6곳 모두 빈 목록, 켜면 강남구 9~10월 신고가. 2026-11-12 실측: 강남구 3건·역삼동 0건, '
            '켜면 27건·2건)',
            alias='includePreviousDays'
        )
    ] = False


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


class DaangnRealsaleSummaryInputModel(RequestModel):
    """`realsaleFeedSummary`·`realsaleNewHighFeedSummary` 의 `input`. 지역 ID 하나다."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동 또는 구)', alias='regionId')
    ]


class DaangnRealsaleFeedSummaryRequestPayloadModel(RequestModel):
    """GraphQL `realsaleFeedSummary` + `realsaleNewHighFeedSummary` 쿼리 변수 (웹의 `RealsaleFeedTitleSummaryQuery`).

    웹 실거래 화면 머리의 'MM월 DD일 매매 N건 · 신고가 N건' 이다. 두 루트 필드가 한 오퍼레이션이라 지역 ID 를 두 번 보낸다
    (웹 `jc` 는 `{input:{regionId}, newHighInput:{regionId}}`).
    """

    input: Annotated[
        DaangnRealsaleSummaryInputModel,
        Field(description='매매 요약의 지역')
    ]
    new_high_input: Annotated[
        DaangnRealsaleSummaryInputModel,
        Field(description='신고가 요약의 지역 (같은 지역)', alias='newHighInput')
    ]


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
