"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    with_floor_number,
)
from jibsa.core.schema import drop_unset_fields
from jibsa.providers.naver.service.common.models import (
    NaverMarketBand,
)

from typing import (
    Annotated,
    Any,
)


class NaverComplexMaintenanceFee(BaseModel):
    """평형의 월 관리비 (만원, 네이버가 단지 관리비 자료로 보여 주는 값)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    latest_month: Annotated[
        str | None,
        Field(description='가장 최근 달 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ] = None
    latest_manage_cost_manwon: Annotated[
        float | None,
        Field(description='가장 최근 달 관리비 (만원)')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='월평균 관리비 (만원)')
    ] = None
    summer_manage_cost_manwon: Annotated[
        float | None,
        Field(description='여름 평균 관리비 (만원)')
    ] = None
    winter_manage_cost_manwon: Annotated[
        float | None,
        Field(description='겨울 평균 관리비 (만원, 난방비 때문에 높다)')
    ] = None


class NaverMarketPrice(BaseModel):
    """한 기관의 최신 시세 (만원). 기관이 추정한 값이라 실제 거래가가 아니다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    provider: Annotated[
        str,
        Field(description='시세 기관 (한국부동산원, KB부동산, 부동산뱅크)')
    ]
    base_date: Annotated[
        str | None,
        Field(description='시세 기준일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ] = None
    sale: Annotated[
        NaverMarketBand | None,
        Field(description='매매 시세 (평균·하위·상위, 만원). 세 값을 모두 모르면 null, 일부만 모르면 그 칸만 null')
    ]
    jeonse: Annotated[
        NaverMarketBand | None,
        Field(description='전세 시세 (평균·하위·상위, 만원). 세 값을 모두 모르면 null, 일부만 모르면 그 칸만 null')
    ]
    jeonse_ratio_low_percent: Annotated[
        float | None,
        Field(description='전세가율 하한 (%). 시세가 없으면(0 포함) null')
    ] = None
    jeonse_ratio_high_percent: Annotated[
        float | None,
        Field(description='전세가율 상한 (%). 시세가 없으면(0 포함) null')
    ] = None


class NaverRealPriceExtreme(BaseModel):
    """실거래 요약의 최저·최고 거래 한 건. 매매는 `price_manwon`, 전세는 `deposit_manwon` 만 있다 (전세금을 `price_manwon` 에 담지 않는다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원). 매매 거래에만 있다')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='전세 보증금 (만원). 전세 거래에만 있다')
    ] = None
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 네이버가 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 ('3'·'지하1'). 바로 뒤의 floor_number 는 층 숫자 (지하는 음수)")
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래. 직거래는 가족 간 거래처럼 시세와 동떨어진 값일 수 있다')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 거래 유형에 맞는 금액 칸만 만들어 넘긴다 (넘기지 않은 칸은 해당 없음이라 키를 뺀다)
        data = drop_unset_fields(self, handler(self), ('price_manwon', 'deposit_manwon'))
        return with_floor_number(data)


class NaverRealPriceRange(BaseModel):
    """실거래 요약의 최저·최고 거래 (두 끝이 거래 한 건이라 금액 범위 모델 대신 쓴다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    lowest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최저가 거래')
    ]
    highest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최고가 거래')
    ]


class NaverRealPriceTradeSummary(BaseModel):
    """한 거래 유형의 기간 안 실거래 요약."""

    model_config = ConfigDict(
        extra='forbid',
    )

    start_date: Annotated[
        str | None,
        Field(description='3년 안에 거래가 없어 5년으로 다시 받았을 때만 있는 시작일 (YYYY-MM-DD, 5년 전 오늘). 3년으로 받았으면 키가 없다')
    ] = None
    average_manwon: Annotated[
        float | None,
        Field(description='평균 거래가 (만원)')
    ] = None
    recent_3m_average_manwon: Annotated[
        float | None,
        Field(description='최근 3개월 평균 거래가 (만원). 3개월 안 거래가 없거나 조회 실패면 null')
    ] = None
    trade_range: Annotated[
        NaverRealPriceRange | None,
        Field(description='최저·최고가 거래 {lowest, highest}. 매매는 price_manwon, 전세는 deposit_manwon. 두 거래를 모두 모르면 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.start_date is None:
            data.pop('start_date', None)
        return data


class NaverRealPriceSummary(BaseModel):
    """평형의 최근 실거래 요약 (매매·전세)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    start_date: Annotated[
        str,
        Field(description='이 날짜 이후 거래 (YYYY-MM-DD, 3년 전 오늘). 3년 안 거래가 없는 유형은 5년으로 다시 받고 그 유형의 요약에 start_date 가 따로 있다')
    ]
    sale: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='매매. 5년 안에도 거래가 없거나 조회 실패면 null')
    ] = None
    jeonse: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='전세. 5년 안에도 거래가 없거나 조회 실패면 null')
    ] = None


class NaverPricePerPyeongRegion(BaseModel):
    """평당가 비교의 지역 하나 (웹 막대 하나)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='지역 이름 (서버 값 그대로, 예: 가락동·송파구·서울시)')
    ] = None
    level: Annotated[
        str | None,
        Field(description='지역 단위 (읍·면·동, 시·군·구, 시·도)')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='그 지역 평균 평당 호가 (만원/평). 없으면(0 포함) null')
    ] = None


class NaverPricePerPyeong(BaseModel):
    """한 거래 유형의 평당 호가와 같은 지역 평균 비교."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='이 평형의 평당 호가 (만원/평)')
    ] = None
    base_date: Annotated[
        str | None,
        Field(description='기준 주 첫날 (YYYY-MM-DD). 지역 목록에서 가장 늦은 날이고, 날짜를 읽지 못한 지역이 하나라도 있거나 지역 목록이 비었거나 주지 않으면 null (읽지 못한 날짜는 [참고] 안내)')
    ] = None
    regions: Annotated[
        list[NaverPricePerPyeongRegion] | None,
        Field(description='지역별 평균 평당 호가. 웹 막대 순서(동·구·시). 네이버가 지역 목록을 주지 않으면(null) null (모름), 빈 목록을 주면 []')
    ] = None
