"""요청 모델: 전국에서 기간 안 거래가 많은 단지 (trade-rankings)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.ranking.common import (
    DabangRankingComplexType,
)

from typing import (
    Annotated,
    Literal,
)


DabangTradeBaseOn = Literal['CURRENT_WEEK', 'LAST_WEEK', 'CURRENT_MONTH', 'LAST_MONTH', 'CURRENT_YEAR']


class DabangRealPriceTradeRankingsComplexV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-price/trade/rankings/complex` 쿼리 (전국에서 거래 많은 단지).

    Args:
        complex_type: 아파트·오피스텔.
        real_price_type: 'SALE' 매매, 'LEASE' 전세.
        base_on: 이번주·지난주·이번달·지난달·올해 (웹 고르기 값).
        limit: 순위 수. 웹 값 50 을 쓴다 (작게 주면 500 을 줄 때가 있다, 2026-10-25 실측: limit 2 는 500, 50 은 200).
    """

    complex_type: Annotated[
        DabangRankingComplexType,
        Field(description='단지 유형', alias='complexType')
    ] = 'APT'
    real_price_type: Annotated[
        Literal['SALE', 'LEASE'],
        Field(description='매매·전세', alias='realPriceType')
    ] = 'SALE'
    base_on: Annotated[
        DabangTradeBaseOn,
        Field(description='기간', alias='baseOn')
    ] = 'CURRENT_WEEK'
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='순위 수')
    ] = 50
