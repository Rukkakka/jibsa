"""단지·매물·지역 실거래가와 시세 추이의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    Result,
    with_floor_number,
)
from jibsa.providers.daangn.service.common.models import DaangnKbEstimatedPrices
from jibsa.providers.daangn.service.region.models import DaangnRealsaleRegion

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예: '3', '지하1'). 숫자는 floor_number")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    registered: Annotated[
        bool | None,
        Field(description='등기까지 마친 거래 (매매만). 당근이 등기일을 주지 않은 거래는 false')
    ] = None
    presale: Annotated[
        str | None,
        Field(description='분양권 / 입주권 거래 (매매만). 일반 거래(소유 구분 REGISTERED_OWNER)는 키가 없고, 당근이 소유 구분을 주지 않았으면 null (모름), 표에 없는 코드는 원래 코드')
    ] = None
    not_presale: Annotated[
        bool,
        Field(exclude=True, description='분양권·입주권이 아닌 일반 거래인지 (소유 구분 REGISTERED_OWNER). presale 키를 빼는 데만 쓰고 출력하지 않는다')
    ] = False
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 배지 '재계약'). 재계약은 새 계약보다 낮게 잡히는 경우가 많다. 당근이 주지 않으면 null, 표에 없는 코드는 원래 코드")
    ] = None
    renewal_right: Annotated[
        bool | None,
        Field(description="계약갱신요구권을 쓴 계약 (전월세만, 당근 웹 배지 '갱신'. 인상률 상한이 있어 시세보다 낮다). 당근이 주지 않으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields |= {'contract_type', 'renewal_right'}
        else:
            fields |= {'cancelled', 'registered', 'presale'}
        if self.not_presale:
            fields.add('presale')
        for field in fields:
            data.pop(field, None)
        return with_floor_number(data)


class DaangnRealPriceBaseResult(Result):
    """실거래 내역 공통.

    `notes`: 전월세를 넘겨 본 범위, 거래가 없는 이유 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool | None,
        Field(description='더 오래된 거래가 더 있는지 (--years 를 줬으면 그 기간 안에서). 당근이 거래 목록을 주지 않았으면 null (모름)')
    ]
    start_date: Annotated[
        str | None,
        Field(description='--years 로 준 기간의 시작일 (YYYY-MM-DD, 이날부터 계약). 주지 않았으면 키가 없다')
    ] = None
    month: Annotated[
        str | None,
        Field(description='--month 로 준 계약 연월 (YYYY-MM). 그 달 거래만이다. 주지 않았으면 키가 없다')
    ] = None
    trades: Annotated[
        list[DaangnRealPrice] | None,
        Field(description='최근 계약 순 실거래. 거래가 없으면 [], 당근이 거래 목록을 주지 않았으면 null (모름)')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.unused_keys():
            data.pop(field, None)
        return data

    def unused_keys(self) -> list[str]:
        """해당 없음이라 출력에서 뺄 키. 결과마다 더할 키는 이 메서드를 넓힌다 (직렬화 함수를 복사하지 않는다)."""
        return [field for field in ('start_date', 'month') if getattr(self, field) is None]


class DaangnRealPriceResult(DaangnRealPriceBaseResult):
    """단지 실거래 내역."""

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (--area). null 이면 전체 평형. --pyeong 으로 골랐으면 키가 없다')
    ] = None
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (--pyeong 으로 고른 아파트형 단지 평형). 주지 않았으면 키가 없다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 그래프는 여기서 본다)')
    ]

    def unused_keys(self) -> list[str]:
        # 평형은 공급 평형(--pyeong)이나 전용면적 묶음(--area) 중 하나로 고른다. --pyeong 이면 area_group 이 null 로 남아 그
        # 설명('null 이면 전체 평형')대로 거르지 않은 것으로 읽혔다 (2026-11-12 리뷰·실측: 헬리오시티 --pyeong 32)
        return super().unused_keys() + ['pyeong' if self.pyeong is None else 'area_group']


class DaangnListingRealPriceResult(DaangnRealPriceBaseResult):
    """매물이 있는 건물(단지)의 비슷한 면적 실거래 내역."""

    listing_id: Annotated[
        str,
        Field(description='매물 ID')
    ]
    url: Annotated[
        str,
        Field(description='매물 페이지 URL')
    ]


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


class DaangnRegionRealPrice(BaseModel):
    """지역 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형·피드에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]
    from_new_high_feed: Annotated[
        bool,
        Field(exclude=True, description='신고가 피드인지. 신고가 피드에 없는 published_date 키를 빼는 데만 쓴다')
    ] = False

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    published_date: Annotated[
        str | None,
        Field(description='실거래가 공개된 날 (YYYY-MM-DD). 신고가 피드에는 없다')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물·단지 이름')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='당근 단지 ID (daangn complex·real-price 에 넘긴다). 당근 단지가 아니면 키가 없다')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예: '3', '지하1'). 숫자는 floor_number")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래. 웹처럼 매매·전월세 모두 (전월세는 드물다)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 카드 배지 '갱신' 은 재계약이다). 당근이 주지 않으면 null, 표에 없는 코드는 원래 코드. 갱신요구권 사용 여부는 지역 피드에 없다")
    ] = None
    new_high: Annotated[
        bool | None,
        Field(description="이 거래가 이 단지·평형의 신고가인지 (매매만, 당근 웹 카드의 '신고가' 배지. 해제된 거래는 false)")
    ] = None
    prev_high_manwon: Annotated[
        float | None,
        Field(description='직전 최고가 (만원, 매매만). 당근이 비교 자료를 주지 않으면 null')
    ] = None
    prev_high_date: Annotated[
        str | None,
        Field(description='직전 최고가 계약일 (YYYY-MM-DD, 매매만)')
    ] = None
    prev_high_diff_percent: Annotated[
        float | None,
        Field(description="직전 최고가 대비 변화율 (%, 소수 둘째 자리, 매매만. 당근 웹 카드의 '직전 최고가 대비 ±N%' 와 같은 비율이고 웹은 정수로 보여 준다). 해제된 거래나 직전 최고가가 없으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('contract_type')
        else:
            # 거래 취소는 웹 카드가 거래 유형과 상관없이 보여 준다 (`yc` 의 `s.cancel===!0`). 직거래 표시와 신고가·직전 최고가는
            # 매매에만 둔다 (웹 카드도 SALE 에만 계산한다)
            fields |= {'deal_type', 'new_high', 'prev_high_manwon', 'prev_high_date', 'prev_high_diff_percent'}
        if self.from_new_high_feed:
            fields.add('published_date')
        if self.complex_id is None:
            fields.add('complex_id')
        for field in fields:
            data.pop(field, None)
        return with_floor_number(data)


class DaangnRealsaleSummary(BaseModel):
    """지역 실거래 화면 머리의 요약 (웹 'MM월 DD일 매매 N건 · 신고가 N건')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    latest_published_date: Annotated[
        str | None,
        Field(description='가장 최근 공개일 (YYYY-MM-DD)')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='그 공개일의 매매 거래 수')
    ] = None
    new_high_count: Annotated[
        int | None,
        Field(description='그 공개일의 신고가 수')
    ] = None


class DaangnRegionRealPriceResult(Result):
    """동·구의 최근 실거래 또는 신고가.

    `notes`: 지역을 고른 방법, 넘겨 본 범위 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    new_high_only: Annotated[
        bool,
        Field(description='신고가 매매만 모았는지')
    ]
    sort: Annotated[
        str,
        Field(description='가격 (매매·신고가: 최근 공개일부터, 같은 날 안에서 가격 높은 순. 당근 웹과 같다) / 최신 (전세·월세: 최근 공개 순)')
    ]
    summary: Annotated[
        DaangnRealsaleSummary | None,
        Field(description='가장 최근 공개일과 그날의 매매·신고가 수 (웹 실거래 화면 머리). 받지 못하면 null 이고 notes 가 알린다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 있는지')
    ]
    trades: Annotated[
        list[DaangnRegionRealPrice],
        Field(description='실거래')
    ]
