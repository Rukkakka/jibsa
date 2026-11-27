"""`trend.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import DaangnKbEstimatedPrices

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnPricePoint(BaseModel):
    """월별 평균 실거래가 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str,
        Field(description='계약 연월 (YYYY-MM)')
    ]
    average_manwon: Annotated[
        float | None,
        Field(description='그 달 실거래 평균가 (만원, 전세는 보증금)')
    ] = None
    trade_count: Annotated[
        int | None,
        Field(description='그 달 거래 수. 적으면 평균이 튈 수 있다')
    ] = None


class DaangnPriceTrendSummary(BaseModel):
    """기간 안의 첫 거래 달과 마지막 거래 달 평균가 비교 (당근 웹 시세 그래프의 'N개월간 X% 상승' 과 같은 계산)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    start_month: Annotated[
        str,
        Field(description='기간 안 첫 거래 달 (YYYY-MM)')
    ]
    start_average_manwon: Annotated[
        float,
        Field(description='첫 거래 달 평균가 (만원)')
    ]
    end_month: Annotated[
        str,
        Field(description='기간 안 마지막 거래 달 (YYYY-MM)')
    ]
    end_average_manwon: Annotated[
        float,
        Field(description='마지막 거래 달 평균가 (만원)')
    ]
    span_months: Annotated[
        int,
        Field(description='두 달 사이 개월 수 (웹의 "N개월간"·"N년간")')
    ]
    change_percent: Annotated[
        float,
        Field(description='첫 거래 달 대비 마지막 거래 달 변화율 (%, 소수 첫째 자리, 오르면 양수). 당근 웹 시세 그래프와 같은 반올림이다')
    ]
    change_manwon: Annotated[
        float,
        Field(description='마지막 거래 달 평균가 - 첫 거래 달 평균가 (만원)')
    ]


class DaangnKbSale(BaseModel):
    """최근 KB 매매 시세 (만원, 당근 웹 시세 그래프의 KB 시세 띠). 이름은 단지 비교의 `DaangnKbRange` 와 맞췄다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    low_manwon: Annotated[
        float | None,
        Field(description='하위 평균가 (만원)')
    ] = None
    high_manwon: Annotated[
        float | None,
        Field(description='상위 평균가 (만원)')
    ] = None


class DaangnChartEstimatedPrices(DaangnKbEstimatedPrices):
    """KB 시세 (출처 `provider`, 기준일 `base_date`). `sale` 안에 하위·상위 평균가가 있다. 단지 비교의 `DaangnCompareEstimatedPrices` 와 달리 매매만 있다."""

    sale: Annotated[
        DaangnKbSale | None,
        Field(description='KB 매매 시세. 하위·상위를 모두 모르면 null')
    ]


class DaangnPriceTrendResult(Result):
    """단지 시세 추이 (국토부 실거래 월별 평균, 당근 웹 단지 화면 시세 그래프).

    `notes`: 평균의 한계, 평형·기간 안내, 시세 그래프를 받지 못한 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='당근 단지 ID')
    ]
    trade_type: Annotated[
        str,
        Field(description='매매 / 전세')
    ]
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (아파트형 단지). 전용면적 묶음으로 봤거나 평형 묶음이 없는 단지면 키가 없다')
    ] = None
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (㎡). 공급 평형으로 봤거나 평형 묶음이 없는 단지면 키가 없다')
    ] = None
    period: Annotated[
        Literal['1년', '3년', '전체'],
        Field(description='months 기간이자 변화율을 보는 기간')
    ]
    recent_average_manwon: Annotated[
        float | None,
        Field(description='최근 3개월(이번 달과 그 전 3개월) 거래 수 가중 평균 (만원). 없으면 12개월 안 마지막 거래 달. 그것도 없거나 당근이 시세 그래프를 주지 않았으면 null. 당근이 빈 항목을 줘 셀 수 없어도, 연월이나 평균 가격을 주지 않은 시세 점을 뺐어도 null')
    ] = None
    recent_trade_count: Annotated[
        int | None,
        Field(description='recent_average_manwon 의 거래 수. 당근이 빈 항목을 줘 셀 수 없거나 연월이나 평균 가격을 주지 않은 시세 점을 뺐으면 null')
    ] = None
    estimated_prices: Annotated[
        DaangnChartEstimatedPrices | None,
        Field(description='이 평형의 최근 KB 매매 시세 (sale 키 안 하위·상위 평균가, 조사 기준일). 당근이 주지 않으면 null')
    ] = None
    total_trade_count: Annotated[
        int | None,
        Field(description='months 기간의 거래 수. 당근이 시세 그래프를 주지 않았거나 빈 항목을 줘 셀 수 없거나 연월이나 평균 가격을 주지 않은 시세 점을 뺐으면 null (모름)')
    ]
    summary: Annotated[
        DaangnPriceTrendSummary | None,
        Field(description='기간 안 첫·마지막 거래 달 비교. 거래 달이 둘이 안 되거나 당근이 시세 그래프를 주지 않았으면 null. 당근이 빈 항목을 줘 셀 수 없어도, 연월이나 평균 가격을 주지 않은 시세 점을 뺐어도 null')
    ] = None
    months: Annotated[
        list[DaangnPricePoint] | None,
        Field(description='월별 평균 (오래된 달부터). 거래가 없는 달은 빠진다. 평형 묶음이 없는 단지는 당근 웹처럼 그래프가 없어 []. 당근이 시세 그래프를 주지 않았으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지')
    ]

    @model_serializer(mode='wrap')
    def drop_other_pyeong_kind(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 평형은 공급 평형이나 전용면적 묶음 중 하나로 고르므로 다른 쪽은 해당 없음이라 키를 뺀다. 평형 묶음이 없는 단지는 고른
        # 평형이 없어(그래프도 없다) 둘 다 뺀다
        data: dict[str, Any] = handler(self)
        for field in ('pyeong', 'area_group'):
            if data.get(field) is None:
                data.pop(field, None)
        return data
