"""`trend.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountRange,
    AmountSet,
    Result,
)

from typing import (
    Annotated,
)


class DabangTrendMonth(BaseModel):
    """시세 흐름의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='달 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ] = None
    trade_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 평균 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 늘 두 개. 거래 없는 달은 다방이 앞 달 평균을 "
            '잇고, 이을 평균도 없으면 그 거래가 null'
        ))
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 거래 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (모르면 null)")
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='그 달 전세가율 (%, 다방 갭 그래프). 매매·전세 평균이 없으면 null')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='그 달 매매 평균 − 전세 평균 (만원, 다방 갭 그래프). 없으면 null')
    ] = None


class DabangTradeAverage(AmountSet):
    """최근 평균 (만원). 매매는 평당 평균(`price_per_pyeong_manwon`)도 함께 낸다."""

    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당 평균 (만원). 매매에만 있다')
    ] = None


class DabangPriceTrend(Result):
    """평형 하나의 시세 흐름 (월별 평균 실거래가, 국토부 신고 기준).

    `notes`: 평형 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID')
    ]
    trade_averages: Annotated[
        dict[str, DabangTradeAverage | None],
        Field(description=(
            "거래별 최근 평균 (만원). 키는 'sale'(price_manwon, 평당 평균 price_per_pyeong_manwon)·'jeonse'(deposit_manwon) 늘 두 개이고 "
            '다방이 그 거래 평균을 주지 않으면 그 거래가 null. 일부 칸만 모르면 그 칸만 null'
        ))
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='전세가율 (%) = 전세 평균 / 매매 평균')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='매매 평균 − 전세 평균 (만원)')
    ] = None
    trade_ranges: Annotated[
        dict[str, dict[str, AmountRange | None] | None] | None,
        Field(description=(
            "기간별 최저·최고 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 아래 기간 'one_year'·'three_years'이고, 기간 안 "
            '두 끝을 모두 모르면 그 기간은 null, 두 기간 모두 모르면 그 거래가 null. 다방이 기간별 값을 주지 않으면 전체가 null'
        ))
    ] = None
    months: Annotated[
        list[DabangTrendMonth],
        Field(description='오래된 달부터 36달')
    ]
