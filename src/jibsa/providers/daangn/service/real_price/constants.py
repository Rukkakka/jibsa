"""실거래가(real-price·region-real-price·price-trend)의 상수: 계약 종류·쪽 크기·정렬·시세 추이 기준."""

from jibsa.providers.daangn.api.models.request.real_price.trend import (
    DaangnPriceChartTradeType,
)


# 전월세 계약 종류 (서버 contractType·leaseContractType). 웹 배지(ComplexTopicPanel `pd`)는 RENEWAL 을 '재계약', 갱신요구권을 쓴
# 계약(useRenewalOfContractRight)을 '갱신' 으로 따로 보여 준다
CONTRACT_TYPE_LABELS: dict[str, str] = {'NEW': '신규', 'RENEWAL': '재계약'}


# 실거래 한 번에 받는 수와, 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건)
REAL_PRICE_PAGE_SIZE: int = 50


REAL_PRICE_MAX_PAGES: int = 24


# real-price·region-real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES


# 매매 실거래의 소유 구분 (서버 ownership). 분양권·입주권만 라벨이 있고, 일반 거래(REGISTERED_OWNER)는 분양권이 아니라 해당 없음이다
PRESALE_LABELS: dict[str, str] = {'PRE_SALE_RIGHT': '분양권', 'PRE_SALE_OWNER': '입주권'}


NOT_PRESALE_OWNERSHIP: str = 'REGISTERED_OWNER'


# 매매 실거래의 거래 방식 (서버 transactionType)
DEAL_TYPE_LABELS: dict[str, str] = {'DIRECT': '직거래', 'BROKERED': '중개거래'}


# '직전 최고가 대비' 비율의 소수 자릿수 (`previous_high_change_percent`). 웹 카드는 정수로 보여 준다
PREVIOUS_HIGH_PERCENT_DIGITS: int = 2


# 지역 실거래 피드 정렬. 웹 실거래 화면은 매매를 가격 순(`TRADE_PRICE_DESC`)으로만 부른다 (RealsaleFeedListQuery `Z`). 전월세는
# 웹에 없고 서버가 가격 순을 거절해 최신 순(`LATEST`)이다. 둘 다 서버 값이라 고르는 옵션은 두지 않는다 (2026-11-12 번들 대조)
REALSALE_SORT_BY_TRADE_TYPE: dict[str, str] = {'매매': 'TRADE_PRICE_DESC', '전세': 'LATEST', '월세': 'LATEST'}


REALSALE_SORT_LABEL_BY_SORT: dict[str, str] = {'TRADE_PRICE_DESC': '가격', 'LATEST': '최신'}


# 단지 시세 추이의 거래 유형 (라벨 → 당근 값). 차트는 매매·전세만 있다. 변화율은 웹처럼 기간의 첫 거래 달과 마지막 거래 달을
# 견주고(`get_price_trend`), 그 달의 거래가 적으면 `PRICE_TREND_FEW_TRANSACTIONS` 로 알린다
PRICE_CHART_TRADE_BY_TRADE_TYPE: dict[str, DaangnPriceChartTradeType] = {'매매': 'BUY', '전세': 'BORROW'}


# 시세 추이 기간: 당근 웹 시세 그래프의 탭 (1년·3년·전체, PriceChart `X`). 전체는 쿼리가 받는 15년(180개월)이다
PRICE_TREND_PERIODS: dict[str, int] = {'1년': 12, '3년': 36, '전체': 180}


# 웹 그래프 머리의 '최근 3개월 평균': 이번 달과 그 전 3개월 (4개 달)
PRICE_TREND_RECENT_MONTHS: int = 3


# 마지막 거래가 이만큼 지났으면 오래된 시세라고 알린다
PRICE_TREND_STALE_MONTHS: int = 6


# 비교하는 달의 거래가 이보다 적으면 변화율이 튈 수 있다고 알린다
PRICE_TREND_FEW_TRANSACTIONS: int = 3
