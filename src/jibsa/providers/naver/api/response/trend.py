"""응답 모델: 법정동 매물 수·호가·거래 추이 (trend)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import NaverResponseModel

from typing import Annotated


class NaverWeeklyPointModel(ResponseModel):
    """동네 주간 추이의 한 주. 지표에 따라 averageCount·averagePyeongPrice·tradeCount 중 하나가 온다."""

    first_day_of_week: Annotated[
        str | None,
        Field(description='그 주 첫날 (YYYY-MM-DD)', alias='firstDayOfWeek')
    ] = None
    average_count: Annotated[
        int | None,
        Field(description='그 주 평균 매물 수', alias='averageCount')
    ] = None
    average_pyeong_price: Annotated[
        int | None,
        Field(description='그 주 평균 평당 호가 (원)', alias='averagePyeongPrice')
    ] = None
    trade_count: Annotated[
        int | None,
        Field(description='그 주 실거래 건수', alias='tradeCount')
    ] = None


class NaverArticleCountWeeklyInfoModel(ResponseModel):
    """동네 주간 매물 수."""

    period_average_count: Annotated[
        int | None,
        Field(description='기간 평균 매물 수', alias='periodAverageCount')
    ] = None
    min_weekly_count: Annotated[
        int | None,
        Field(description='기간 중 가장 적은 주', alias='minWeeklyCount')
    ] = None
    max_weekly_count: Annotated[
        int | None,
        Field(description='기간 중 가장 많은 주', alias='maxWeeklyCount')
    ] = None
    latest_weekly_count: Annotated[
        int | None,
        Field(description='최근 주', alias='latestWeeklyCount')
    ] = None
    count_change_rate: Annotated[
        float | None,
        Field(description='기간 첫 주 대비 최근 주 증감률 (%)', alias='countChangeRate')
    ] = None
    weekly_counts: Annotated[
        list[NaverWeeklyPointModel],
        Field(description='주별 값', alias='weeklyCounts')
    ] = []


class NaverRealTradeCountWeeklyModel(ResponseModel):
    """동네 주간 실거래 건수."""

    period_average_trade_count: Annotated[
        int | None,
        Field(description='기간 평균 주간 거래 건수', alias='periodAverageTradeCount')
    ] = None
    latest_weekly_trade_count: Annotated[
        int | None,
        Field(description='최근 주 거래 건수', alias='latestWeeklyTradeCount')
    ] = None
    weekly_counts: Annotated[
        list[NaverWeeklyPointModel],
        Field(description='주별 값', alias='weeklyCounts')
    ] = []


class NaverLegalDivisionArticleCountWeeklyInfoV1ResponseModel(NaverResponseModel[NaverArticleCountWeeklyInfoModel]):
    """`GET /front-api/v1/legalDivision/articleCountWeeklyInfo` 응답."""


class NaverLegalDivisionPyeongPriceWeeklyListV1ResponseModel(NaverResponseModel[list[NaverWeeklyPointModel]]):
    """`GET /front-api/v1/legalDivision/pyeongPriceWeeklyList` 응답."""


class NaverLegalDivisionRealTradeCountWeeklyListV1ResponseModel(NaverResponseModel[NaverRealTradeCountWeeklyModel]):
    """`GET /front-api/v1/legalDivision/realTradeCountWeeklyList` 응답."""
