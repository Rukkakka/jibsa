"""요청 모델: 지역 실거래가 (region-real-price)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


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
