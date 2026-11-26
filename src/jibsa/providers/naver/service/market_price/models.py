"""단지·평형별 기관 시세 추이의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.naver.service.common.models import NaverMarketBand

from typing import Annotated


class NaverMarketPricePoint(BaseModel):
    """한 기준일의 기관 시세 (만원). (`naver complex --pyeong` 의 `estimated_prices` 원소와 같은 모양)"""

    model_config = ConfigDict(
        extra='forbid',
    )

    base_date: Annotated[
        str | None,
        Field(description="시세 기준일 (YYYY-MM-DD). 네이버가 날짜 자리를 빈 값·'-' 로 주면 null, 날짜로 읽지 못하면 null ([참고] 안내)")
    ]
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


class NaverMarketPriceSeries(BaseModel):
    """한 기관의 기간 안 시세."""

    model_config = ConfigDict(
        extra='forbid',
    )

    provider: Annotated[
        str,
        Field(description='시세 기관 (한국부동산원, KB부동산, 부동산뱅크)')
    ]
    weeks: Annotated[
        list[NaverMarketPricePoint],
        Field(description='기준일별 시세 (오래된 것부터, 보통 주 1회). 점마다 base_date 가 있다')
    ]


class NaverMarketPriceHistory(Result):
    """평형의 기관별 시세 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 번호')
    ]
    period: Annotated[
        str,
        Field(description='기간 (3개월, 1년, 3년, 5년)')
    ]
    start_date: Annotated[
        str,
        Field(description='기간 시작일 (YYYY-MM-DD)')
    ]
    providers: Annotated[
        list[NaverMarketPriceSeries],
        Field(description='기관별 시세. 시세가 없는 평형이면 []')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
