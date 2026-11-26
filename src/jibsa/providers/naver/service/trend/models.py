"""법정동 매물 수·호가·거래 추이의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    NumberRange,
    Result,
)

from typing import Annotated


class NaverWeeklyCount(BaseModel):
    """주별 건수."""

    model_config = ConfigDict(
        extra='forbid',
    )

    week_start: Annotated[
        str | None,
        Field(description='그 주 첫날 (YYYY-MM-DD)')
    ] = None
    count: Annotated[
        int | float | None,
        Field(description='건수')
    ] = None


class NaverWeeklyPrice(BaseModel):
    """주별 평당 호가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    week_start: Annotated[
        str | None,
        Field(description='그 주 첫날 (YYYY-MM-DD)')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평균 평당 호가 (만원)')
    ] = None


class NaverListingCountTrend(BaseModel):
    """주간 매물 수 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    period_average: Annotated[
        int | float | None,
        Field(description='기간 평균 매물 수')
    ] = None
    latest: Annotated[
        int | float | None,
        Field(description='최근 주 매물 수')
    ] = None
    count_range: Annotated[
        NumberRange | None,
        Field(description='기간 중 주별 매물 수의 가장 적은 주(lowest)와 가장 많은 주(highest). 네이버가 두 값을 모두 주지 않으면 null')
    ] = None
    change_percent: Annotated[
        float | None,
        Field(description='기간 첫 주 대비 최근 주 증감률 (%)')
    ] = None
    weeks: Annotated[
        list[NaverWeeklyCount],
        Field(description='주별 평균 매물 수 (오래된 주부터)')
    ] = []


class NaverPriceTrend(BaseModel):
    """주간 평당 호가 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    latest_manwon: Annotated[
        float | None,
        Field(description='최근 주 평균 평당 호가 (만원). 네이버가 주간 목록에 빈 항목을 줘 최근 주를 알 수 없으면 null')
    ] = None
    weeks: Annotated[
        list[NaverWeeklyPrice],
        Field(description='주별 평균 평당 호가 (오래된 주부터)')
    ] = []


class NaverTradeCountTrend(BaseModel):
    """주간 실거래 건수 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    period_average: Annotated[
        int | float | None,
        Field(description='기간 평균 주간 거래 건수')
    ] = None
    latest: Annotated[
        int | None,
        Field(description='최근 주 거래 건수')
    ] = None
    weeks: Annotated[
        list[NaverWeeklyCount],
        Field(description='주별 거래 건수 (오래된 주부터)')
    ] = []


class NaverDistrictTrend(Result):
    """동네 아파트 주간 추이 (매물 수·평당 호가·실거래 건수).

    `notes`: 덤 조회가 실패한 [실패] 안내 등. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(description='거래 유형 (매매, 전세)')
    ]
    period: Annotated[
        str,
        Field(description='기간 (1개월, 6개월, 1년, 3년, 5년)')
    ]
    pyeong_range: Annotated[
        str,
        Field(description="평형대 (예: '30~40평'). 전체면 '전체'")
    ]
    listing_count_trend: Annotated[
        NaverListingCountTrend | None,
        Field(description='주간 매물 수. 조회 실패면 null')
    ] = None
    asking_price_per_pyeong: Annotated[
        NaverPriceTrend | None,
        Field(description='주간 평균 평당 호가. 조회 실패면 null')
    ] = None
    trade_count_trend: Annotated[
        NaverTradeCountTrend | None,
        Field(description='주간 실거래 건수. 조회 실패면 null')
    ] = None
