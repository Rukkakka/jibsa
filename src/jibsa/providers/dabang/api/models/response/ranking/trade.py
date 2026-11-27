"""응답 모델: 전국에서 기간 안 거래가 많은 단지 (trade-rankings)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangTradeRankingItemModel(DabangBaseResponseModel):
    """거래 순위 한 칸."""

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 수', alias='tradeCount')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID', alias='complexId')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='complexName')
    ] = None
    description: Annotated[
        str | None,
        Field(description="'11년차ㆍ3636세대ㆍ서울특별시 송파구 문정동'")
    ] = None


class DabangTradeRankingsResultModel(DabangBaseResponseModel):
    """거래 순위 `result`."""

    format_base_period: Annotated[
        str | None,
        Field(description="기준 기간 ('26.10.19 ~ 26.10.25')", alias='formatBasePeriod')
    ] = None
    list_: Annotated[
        list[DabangTradeRankingItemModel],
        Field(description='순위', alias='list')
    ] = []


class DabangRealPriceTradeRankingsComplexV5ResponseModel(DabangV5ResponseModel[DabangTradeRankingsResultModel]):
    """`GET /api/v5/real-price/trade/rankings/complex` 응답."""
