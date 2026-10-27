from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangV5ResponseModel

from typing import Annotated


class DabangRealPriceHistoryModel(ResponseModel):
    """실거래 한 건 (만원, 국토부 신고 기준).

    매매는 `tradePrice`, 전세는 `deposit`, 월세는 `deposit`·`monthlyPrice` 에 온다. `isRelease` 는 해제된 거래다.
    `priceType` 은 SALE·LEASE·MONTHLY (2026-10-25 실측).

    Args:
        contract_date: 계약일 ('26.01.14').
        price_type: 'SALE', 'LEASE', 'MONTHLY'.
        format_floor: 층 (모르면 'null' 글자로 온다).
        size: 전용면적 (㎡, 단지 없는 매물 실거래만).
    """

    contract_date: Annotated[
        str | None,
        Field(description="계약일 ('26.01.14')", alias='contractDate')
    ] = None
    price_type: Annotated[
        str | None,
        Field(description='SALE·LEASE·MONTHLY', alias='priceType')
    ] = None
    format_floor: Annotated[
        str | None,
        Field(description='층', alias='formatFloor')
    ] = None
    trade_price: Annotated[
        float | None,
        Field(description='매매가 (만원)', alias='tradePrice')
    ] = None
    deposit: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    monthly_price: Annotated[
        float | None,
        Field(description='월세 (만원)', alias='monthlyPrice')
    ] = None
    size: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    is_release: Annotated[
        bool | None,
        Field(description='해제된 거래', alias='isRelease')
    ] = None
    is_direct: Annotated[
        bool | None,
        Field(description='직거래', alias='isDirect')
    ] = None


class DabangRealPriceComplexHistoriesResultModel(ResponseModel):
    """단지 실거래 `result`."""

    list_: Annotated[
        list[DabangRealPriceHistoryModel],
        Field(description='최근 계약 순 실거래', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRealPriceComplexHistoriesV5ResponseModel(DabangV5ResponseModel[DabangRealPriceComplexHistoriesResultModel]):
    """`GET /api/v5/real-price/complex/histories` 응답."""


class DabangRealPriceHouseHistoryResultModel(ResponseModel):
    """단지 없는 매물 실거래 `result`. 그 건물이 아니라 같은 동의 같은 건물 유형 거래다 (`historyBaseType: DONG`,
    역삼동 단독·다가구 전월세 4,447건, 2026-10-25 실측).
    """

    dong_name: Annotated[
        str | None,
        Field(description='동 이름', alias='dongName')
    ] = None
    history_base_type: Annotated[
        str | None,
        Field(description="거래를 모은 범위 ('DONG')", alias='historyBaseType')
    ] = None
    building_view_type: Annotated[
        str | None,
        Field(description="건물 유형 ('DETACHED' 단독·다가구 등)", alias='buildingViewType')
    ] = None
    histories: Annotated[
        list[DabangRealPriceHistoryModel],
        Field(description='최근 계약 순 실거래')
    ] = []
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRealPriceHouseHistoryV5ResponseModel(DabangV5ResponseModel[DabangRealPriceHouseHistoryResultModel]):
    """`GET /api/v5/real-price/house/history` 응답."""


class DabangChartStatisticModel(ResponseModel):
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


class DabangChartPerSpaceModel(ResponseModel):
    """평형의 최근 평균 (만원)."""

    average_price: Annotated[
        float | None,
        Field(description='평균가', alias='averagePrice')
    ] = None
    average_pyeong_price: Annotated[
        float | None,
        Field(description='평당 평균가', alias='averagePyeongPrice')
    ] = None


class DabangChartSeriesModel(ResponseModel):
    """매매 또는 전월세 시세 흐름."""

    statistics: Annotated[
        list[DabangChartStatisticModel],
        Field(description='36달')
    ] = []
    per_space: Annotated[
        DabangChartPerSpaceModel | None,
        Field(description='최근 평균', alias='perSpace')
    ] = None


class DabangChartGapRecentModel(ResponseModel):
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


class DabangChartGapModel(ResponseModel):
    """매매·전세 차이."""

    recent_info: Annotated[
        DabangChartGapRecentModel | None,
        Field(description='최근', alias='recentInfo')
    ] = None


class DabangHighLowModel(ResponseModel):
    """기간 안 최고·최저 (만원)."""

    highest: Annotated[
        float | None,
        Field(description='최고')
    ] = None
    lowest: Annotated[
        float | None,
        Field(description='최저')
    ] = None


class DabangYearPriceRangeModel(ResponseModel):
    """1년·3년 최고·최저."""

    one_year: Annotated[
        DabangHighLowModel | None,
        Field(description='1년', alias='oneYear')
    ] = None
    three_years: Annotated[
        DabangHighLowModel | None,
        Field(description='3년', alias='threeYears')
    ] = None


class DabangYearPriceModel(ResponseModel):
    """매매·전세 1년·3년 최고·최저."""

    sale: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='매매')
    ] = None
    lease: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='전세')
    ] = None


class DabangRealPriceComplexChartsResultModel(ResponseModel):
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
