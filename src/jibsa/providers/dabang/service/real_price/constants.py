"""실거래가 기능(real_price)의 상수: 거래 유형 이름표·조회 한도·건물 종류 이름."""
from jibsa.core.listing import TradeType
from jibsa.providers.dabang.api.models.request.real_price.trades import (
    REAL_PRICE_PAGE_LIMIT,
    DabangRealPriceSearchType,
)

from typing import Literal


RealPriceTrade = Literal['매매', '전월세']

SEARCH_TYPE_BY_TRADE: dict[RealPriceTrade, DabangRealPriceSearchType] = {'매매': 'SALE', '전월세': 'LEASE'}
TRADE_BY_SEARCH_TYPE: dict[str, RealPriceTrade] = {search_type: trade for trade, search_type in SEARCH_TYPE_BY_TRADE.items()}

TRADE_BY_PRICE_TYPE: dict[str, TradeType] = {'SALE': '매매', 'LEASE': '전세', 'MONTHLY': '월세'}
REAL_PRICE_MAX_YEARS: int = 3
REAL_PRICE_MAX_PAGES: int = 4
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_LIMIT * REAL_PRICE_MAX_PAGES

BUILDING_VIEW_LABELS: dict[str, str] = {'DETACHED': '단독·다가구', 'MULTIPLEX': '다세대·연립', 'APARTMENT': '아파트', 'OFFICETEL': '오피스텔'}
