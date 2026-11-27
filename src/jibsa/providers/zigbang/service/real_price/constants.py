"""직방 service 실거래가 상수: 거래 유형·한도·거래 방식 이름표, 국토부 거래일 형식 (real-price)."""

import re

from jibsa.core.listing import (
    TradeType,
)

from typing import (
    Literal,
)


# 실거래 조회가 받는 거래 유형. '전체' 는 직방이 매매와 전월세를 계약일 최신 순으로 합쳐 주는 조회 (웹 실거래 탭의 기본)
RealPriceTradeType = Literal['매매', '전세', '월세', '전체']

REAL_PRICE_TRADE_TYPES: tuple[RealPriceTradeType, ...] = ('매매', '전세', '월세', '전체')
REAL_PRICE_DEAL_TYPE_BY_TRADE: dict[str, str] = {'매매': 'sales', '전세': 'rent', '월세': 'rent', '전체': 'all'}
TRADE_BY_RT_DEAL_TYPE: dict[str, TradeType] = {'sales': '매매', 'charter': '전세', 'rent': '월세'}
REAL_PRICE_CATEGORY_BY_METHOD: dict[str, str] = {'relay': '중개거래', 'direct': '직거래'}
REAL_PRICE_PAGE_SIZE: int = 50
# 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건, 당근과 같다). 매매는 --limit 1200 도 24쪽이면 된다
REAL_PRICE_MAX_PAGES: int = 24
# real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES
RT_DEAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2,4})\.\s*(\d{1,2})\.\s*(\d{1,2})')
