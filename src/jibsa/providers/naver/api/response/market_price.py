"""응답 모델: 단지·평형별 기관 시세 추이 (market-price)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverPriceRangeModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverMarketPriceHistoryModel(ResponseModel):
    """한 시세 제공처의 기간 안 주별 시세 (원). 키는 시세 기준일 (YYYY-MM-DD)."""

    cp: Annotated[
        str | None,
        Field(description='제공처 (kab 한국부동산원, kbstar KB부동산, neonet 부동산뱅크)')
    ] = None
    deal_prices: Annotated[
        dict[str, int | None],
        Field(description='기준일별 매매 시세 평균', alias='dealPrices')
    ] = {}
    deposit_prices: Annotated[
        dict[str, int | None],
        Field(description='기준일별 전세 시세 평균', alias='depositPrices')
    ] = {}
    deal_price_ranges: Annotated[
        dict[str, NaverPriceRangeModel | None],
        Field(description='기준일별 매매 시세 범위', alias='dealPriceRanges')
    ] = {}
    deposit_price_ranges: Annotated[
        dict[str, NaverPriceRangeModel | None],
        Field(description='기준일별 전세 시세 범위', alias='depositPriceRanges')
    ] = {}
    lease_per_deal_rates: Annotated[
        dict[str, NaverPriceRangeModel | None],
        Field(description='기준일별 전세가율 범위 (%)', alias='leasePerDealRates')
    ] = {}


class NaverComplexMarketPriceListV1ResponseModel(NaverResponseModel[list[NaverMarketPriceHistoryModel]]):
    """`GET /front-api/v1/complex/marketPrice/list` 응답."""
