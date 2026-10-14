"""법정동 매물 수·호가·거래 추이 (trend).

사이트 지역 화면의 아파트 매물 수·평당 호가·실거래 건수 (주별). 아파트 매매·전세만 값이 있다
(오피스텔·빌라는 0, 월세는 400, 2026-10-10 확인).
"""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import won_to_manwon
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.trend import (
    NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel,
    NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel,
    NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel,
    NaverTrendOffset,
)
from jibsa.providers.naver.service.common import result_or_none

from typing import (
    Annotated,
    Literal,
)


TREND_PERIOD_BY_NAME: dict[str, NaverTrendOffset] = {
    '1개월': 'P-1M',
    '6개월': 'P-6M',
    '1년': 'P-1Y',
    '3년': 'P-3Y',
    '5년': 'P-5Y',
}
TREND_TRADE_CODE_BY_NAME: dict[str, Literal['A1', 'B1']] = {
    '매매': 'A1',
    '전세': 'B1',
}
# 평형대 하한 (평)과 폭. 사이트처럼 10평 단위로 하한~하한+10 평
TREND_PYEONG_RANGES: tuple[int, ...] = (10, 20, 30, 40, 50)
TREND_PYEONG_RANGE_WIDTH: int = 10


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
        int | None,
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
        int | None,
        Field(description='기간 평균 매물 수')
    ] = None
    latest: Annotated[
        int | None,
        Field(description='최근 주 매물 수')
    ] = None
    min: Annotated[
        int | None,
        Field(description='기간 중 가장 적은 주')
    ] = None
    max: Annotated[
        int | None,
        Field(description='기간 중 가장 많은 주')
    ] = None
    change_rate_pct: Annotated[
        float | None,
        Field(description='기간 첫 주 대비 최근 주 증감률 (%)')
    ] = None
    weekly: Annotated[
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
        Field(description='최근 주 평균 평당 호가 (만원)')
    ] = None
    weekly: Annotated[
        list[NaverWeeklyPrice],
        Field(description='주별 평균 평당 호가 (오래된 주부터)')
    ] = []


class NaverTradeCountTrend(BaseModel):
    """주간 실거래 건수 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    period_average: Annotated[
        int | None,
        Field(description='기간 평균 주간 거래 건수')
    ] = None
    latest: Annotated[
        int | None,
        Field(description='최근 주 거래 건수')
    ] = None
    weekly: Annotated[
        list[NaverWeeklyCount],
        Field(description='주별 거래 건수 (오래된 주부터)')
    ] = []


class NaverDistrictTrend(BaseModel):
    """동네 아파트 주간 추이 (매물 수·평당 호가·실거래 건수)."""

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
    listing_count: Annotated[
        NaverListingCountTrend | None,
        Field(description='주간 매물 수. 조회 실패면 null')
    ] = None
    price_per_pyeong: Annotated[
        NaverPriceTrend | None,
        Field(description='주간 평균 평당 호가. 조회 실패면 null')
    ] = None
    trade_count: Annotated[
        NaverTradeCountTrend | None,
        Field(description='주간 실거래 건수. 조회 실패면 null')
    ] = None


def get_district_trend(
    client: NaverClient,
    legal_division_code: str,
    *,
    trade_type: str = '매매',
    period: str = '1년',
    pyeong_range: int | None = None,
) -> NaverDistrictTrend:
    """법정동(또는 구)의 아파트 주간 매물 수·평당 호가·실거래 건수 (3회 호출).

    하나가 실패하면 그 값만 모름(None)으로 두고, 셋 다 실패하면 에러다.

    Args:
        trade_type: `TREND_TRADE_CODE_BY_NAME` 의 이름 (매매, 전세).
        period: `TREND_PERIOD_BY_NAME` 의 이름.
        pyeong_range: 평형대 하한 (`TREND_PYEONG_RANGES`). 주면 하한~하한+`TREND_PYEONG_RANGE_WIDTH` 평만.

    Raises:
        JibsaError: 셋 다 조회에 실패하면 UPSTREAM_ERROR.
    """
    query = {
        'legal_division_number': legal_division_code,
        'trade_type': TREND_TRADE_CODE_BY_NAME[trade_type],
        'offset': TREND_PERIOD_BY_NAME[period],
        'pyeong_range_lower': pyeong_range,
        'pyeong_range_upper': None if pyeong_range is None else pyeong_range + TREND_PYEONG_RANGE_WIDTH,
    }
    # 동·구뿐 아니라 시·도 코드도 세 엔드포인트가 200 으로 답한다 (서울 1100000000, 2026-10-10). 429 는 응답 훅이
    # RateLimitedError 로 바꿔 result_or_none 이 삼키지 않으므로, 셋 다 실패한 UPSTREAM_ERROR 는 일시 장애다
    counts = result_or_none(lambda: client.run_request_legal_division_article_count_weekly_info_v1(
        NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel(**query)
    ))
    prices = result_or_none(lambda: client.run_request_legal_division_pyeong_price_weekly_list_v1(
        NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel(**query)
    ))
    trades = result_or_none(lambda: client.run_request_legal_division_real_trade_count_weekly_list_v1(
        NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel(**query)
    ))
    if counts is None and prices is None and trades is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message='네이버 동네 추이를 받지 못했습니다',
            hint='법정동·구 이름으로 다시 찾거나 잠시 뒤 다시 시도하세요',
        )
    price_weekly = [
        NaverWeeklyPrice(week_start=point.first_day_of_week, price_per_pyeong_manwon=won_to_manwon(point.average_pyeong_price))
        for point in prices or []
    ]
    return NaverDistrictTrend(
        trade_type=trade_type,
        period=period,
        pyeong_range='전체' if pyeong_range is None else f'{pyeong_range}~{pyeong_range + TREND_PYEONG_RANGE_WIDTH}평',
        listing_count=None if counts is None else NaverListingCountTrend(
            period_average=counts.period_average_count,
            latest=counts.latest_weekly_count,
            min=counts.min_weekly_count,
            max=counts.max_weekly_count,
            change_rate_pct=counts.count_change_rate,
            weekly=[NaverWeeklyCount(week_start=point.first_day_of_week, count=point.average_count) for point in counts.weekly_counts],
        ),
        price_per_pyeong=None if prices is None else NaverPriceTrend(
            # 주간 목록 3종은 모두 오래된 주부터 온다. 매물 수·거래 건수의 서버 최신값(latest...)도 마지막 주와 같다
            # (2026-10-14 실측: 역삼동 52주 3종 모두 오름차순, latestWeeklyCount = 마지막 주 averageCount)
            latest_manwon=price_weekly[-1].price_per_pyeong_manwon if price_weekly else None,
            weekly=price_weekly,
        ),
        trade_count=None if trades is None else NaverTradeCountTrend(
            period_average=trades.period_average_trade_count,
            latest=trades.latest_weekly_trade_count,
            weekly=[NaverWeeklyCount(week_start=point.first_day_of_week, count=point.trade_count) for point in trades.weekly_counts],
        ),
    )
