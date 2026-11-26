"""응답 모델: 평형 하나의 시세 흐름 (price-trend)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangChartStatisticModel(DabangBaseResponseModel):
    """시세 흐름의 한 달 (만원). 거래가 없는 달도 앞 달 평균을 이어 준다 (`volume: 0`)."""

    date: Annotated[
        str,
        Field(description='달 (YYYYMM)')
    ]
    average_price: Annotated[
        float | None,
        Field(description='평균가 (만원)', alias='averagePrice')
    ] = None
    volume: Annotated[
        int | None,
        Field(description='거래 수 (전월세는 전세 + 월세)')
    ] = None
    lease_volume: Annotated[
        int | None,
        Field(description='전세 거래 수 (전월세만)', alias='leaseVolume')
    ] = None
    monthly_volume: Annotated[
        int | None,
        Field(description='월세 거래 수 (전월세만)', alias='monthlyVolume')
    ] = None


class DabangChartPerSpaceModel(DabangBaseResponseModel):
    """평형의 최근 평균 (만원)."""

    average_price: Annotated[
        float | None,
        Field(description='평균가', alias='averagePrice')
    ] = None
    average_pyeong_price: Annotated[
        float | None,
        Field(description='평당 평균가', alias='averagePyeongPrice')
    ] = None


class DabangChartSeriesModel(DabangBaseResponseModel):
    """매매 또는 전월세 시세 흐름."""

    statistics: Annotated[
        list[DabangChartStatisticModel],
        Field(description='36달')
    ] = []
    per_space: Annotated[
        DabangChartPerSpaceModel | None,
        Field(description='최근 평균', alias='perSpace')
    ] = None


class DabangChartGapRecentModel(DabangBaseResponseModel):
    """최근 매매·전세 평균과 차이, 전세가율."""

    trade_average_price: Annotated[
        float | None,
        Field(description='매매 평균 (만원)', alias='tradeAveragePrice')
    ] = None
    lease_average_price: Annotated[
        float | None,
        Field(description='전세 평균 (만원)', alias='leaseAveragePrice')
    ] = None
    range_average_price: Annotated[
        float | None,
        Field(description='매매 − 전세 (만원)', alias='rangeAveragePrice')
    ] = None
    lease_rate: Annotated[
        float | None,
        Field(description='전세가율 (%)', alias='leaseRate')
    ] = None


class DabangChartGapStatisticModel(DabangChartGapRecentModel):
    """달마다 매매·전세 평균과 차이, 전세가율. 아직 거래가 없는 이번 달은 모두 null 로 온다 (2026-11-13 웹 캡처: 은마 202611)."""

    date: Annotated[
        str | None,
        Field(description='달 (YYYYMM). 없으면 그 줄은 어느 달인지 몰라 쓰지 않는다')
    ] = None


class DabangChartGapModel(DabangBaseResponseModel):
    """매매·전세 차이."""

    statistics: Annotated[
        list[DabangChartGapStatisticModel] | None,
        Field(description='36달. null 이면 모름')
    ] = None
    recent_info: Annotated[
        DabangChartGapRecentModel | None,
        Field(description='최근', alias='recentInfo')
    ] = None


class DabangHighLowModel(DabangBaseResponseModel):
    """기간 안 최고·최저 (만원)."""

    highest: Annotated[
        float | None,
        Field(description='최고')
    ] = None
    lowest: Annotated[
        float | None,
        Field(description='최저')
    ] = None


class DabangYearPriceRangeModel(DabangBaseResponseModel):
    """1년·3년 최고·최저."""

    one_year: Annotated[
        DabangHighLowModel | None,
        Field(description='1년', alias='oneYear')
    ] = None
    three_years: Annotated[
        DabangHighLowModel | None,
        Field(description='3년', alias='threeYears')
    ] = None


class DabangYearPriceModel(DabangBaseResponseModel):
    """매매·전세 1년·3년 최고·최저."""

    sale: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='매매')
    ] = None
    lease: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='전세')
    ] = None


class DabangRealPriceComplexChartsResultModel(DabangBaseResponseModel):
    """시세 흐름 `result`. `leaseMonthly` 의 평균가는 전세 평균이다 (`perSpace` 가 `gap.recentInfo.leaseAveragePrice` 와 같다,
    2026-10-25 실측: 26000 = 26000).
    """

    sale: Annotated[
        DabangChartSeriesModel | None,
        Field(description='매매')
    ] = None
    lease_monthly: Annotated[
        DabangChartSeriesModel | None,
        Field(description='전월세 (평균가는 전세)', alias='leaseMonthly')
    ] = None
    gap: Annotated[
        DabangChartGapModel | None,
        Field(description='매매·전세 차이')
    ] = None
    year_price: Annotated[
        DabangYearPriceModel | None,
        Field(description='1년·3년 최고·최저', alias='yearPrice')
    ] = None


class DabangRealPriceComplexChartsV5ResponseModel(DabangV5ResponseModel[DabangRealPriceComplexChartsResultModel]):
    """`GET /api/v5/real-price/complex/charts` 응답."""
