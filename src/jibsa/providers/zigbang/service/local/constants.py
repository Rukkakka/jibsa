"""직방 service 지역 화면 상수: 거래 유형·기간·정렬 이름표, 지역 해석 안내 문구, 지역 정보 평형대·인구 기준 (region-info·region-trades·region-ranking)."""

import re

from jibsa.providers.zigbang.api.models.request.common import (
    ZigbangAptTranType,
)
from jibsa.providers.zigbang.api.models.request.local.info import (
    ZigbangPynAreaType,
)
from jibsa.providers.zigbang.api.models.request.local.ranking import (
    ZigbangDanjiRankingSortType,
    ZigbangDanjiRankingViewPeriod,
)
from jibsa.providers.zigbang.api.models.request.local.trades import (
    ZigbangLocalTradeDealType,
    ZigbangLocalTradePeriodType,
)

from typing import (
    Literal,
)


LocalTrade = Literal['매매', '전세', '월세']
LocalRankingPeriod = Literal['이번주', '지난주', '이번달', '지난달', '올해', '작년']
LocalTradePeriod = Literal['오늘', '어제', '7일', '15일', '30일']

LOCAL_TRADES: tuple[LocalTrade, ...] = ('매매', '전세', '월세')
# 세 명령이 같은 말로 동·구를 찾는다. 서버는 시·도 코드(2자리)도 받지만 웹 지역 화면이 시·도를 보여 주는지 확인하지 못해 받지 않는다
LOCAL_SIDO_MESSAGE: str = '시·도 이름이라 조회할 수 없습니다 (동·구 단위로 조회합니다)'
LOCAL_SIDO_HINT: str = "구나 동 이름을 주세요 (예: '송파구', '가락동')"
# 지역 해석의 일반 hint 는 역 이름으로 다시 찾으라고 하지만 이 명령들은 역·학교·단지 이름을 받지 않는다
LOCAL_NOT_FOUND_HINT: str = "동·구 이름을 주세요 (예: '송파구', '가락동'). 역·학교·단지 이름은 받지 않습니다"
# region-info·region-trades·region-ranking 이 같이 쓴다 (세 명령 모두 직방 웹 지역 화면의 값이다)
LOCAL_RI_CHECK: str = '직방 지역 화면은 읍·면 단위입니다'
# 평당 추이 그래프의 평형대 탭 (`--range`). 직방 서버의 pynAreaType 값 그대로다 (2026-11-22 실측: 모두 200)
PRICE_RANGES: tuple[ZigbangPynAreaType, ...] = (
    '전체', '10평이하', '10평대', '20평대', '30평대', '40평대', '50평대', '60평대이상',
)
# 지역 정보 `price` 의 평형대 구분(area) → 웹 평형 이름표 (2026-11-19 번들 지역정보 화면 `e_`). 'total' 먼저, 그다음 작은 평형대부터다
AREA_LABELS: dict[str, str] = {
    'total': '전체',
    '0': '10평 이하',
    '10': '10평대',
    '20': '20평대',
    '30': '30평대',
    '40': '40평대',
    '50': '50평대',
    '60': '60평대 이상',
}
# 지역 정보 머리 문구 ('39 단지 · 23,634 세대'). 웹 머리가 이 글자를 그린다
DESCRIPTION_PATTERN: re.Pattern[str] = re.compile(r'([\d,]+)\s*단지\s*·\s*([\d,]+)\s*세대')
# 웹 인구 그래프가 보내는 기간 길이 (2026-11-19 캡처: startDate=202110&endDate=202610). 번들에서 근거는 찾지 못했다
POPULATION_YEARS: int = 5
PRICE_TREND_EMPTY_ALL: str = '직방 시세가 있는 아파트 단지가 없습니다'
PRICE_TREND_EMPTY_RANGE: str = '선택하신 평형대의 단지가 없습니다'
# 줄의 동(`dong`) 필드 설명. 실거래·랭킹 줄이 같이 쓴다
LOCAL_DONG_DESCRIPTION: str = (
    "줄이 속한 동 (직방이 준 local, 예: '가락동'). 구 단위 조회에만 있고 동 단위 조회는 서버가 빈 글자를 줘 키가 없다. "
    '구 단위인데 직방이 주지 않으면 null'
)
RANKING_PERIODS: tuple[LocalRankingPeriod, ...] = ('이번주', '지난주', '이번달', '지난달', '올해', '작년')
DEFAULT_RANKING_LIMIT: int = 10
# 쪽 크기. 서버는 11 이상이면 400 이다 (2026-11-22 실측)
RANKING_PAGE_SIZE: int = 10
# 웹이 보여 주는 최대 순위. 랭킹 화면은 `list.length>=100` 에서 넘기기를 멈추고 '단지 랭킹은 100위까지만 제공됩니다.' 를 보여 준다
# (2026-11-22 번들 `onEndReached`). 서버는 200위까지 주지만 101위부터는 웹에서 볼 수 없어 받지 않는다
RANKING_MAX_RANKS: int = 100
# 웹 기간 탭 → 서버 viewPeriod
VIEW_PERIOD_BY_LABEL: dict[LocalRankingPeriod, ZigbangDanjiRankingViewPeriod] = {
    '이번주': 'this_week',
    '지난주': 'last_week',
    '이번달': 'this_month',
    '지난달': 'last_month',
    '올해': 'this_year',
    '작년': 'last_year',
}
TRAN_TYPE_BY_TRADE: dict[LocalTrade, ZigbangAptTranType] = {'매매': 'trade', '전세': 'charter', '월세': 'rental'}
# 웹 정렬 이름 → 서버 sortType (2026-11-19 번들 `T`). 첫 항목이 지역 화면 '단지랭킹' 패널의 기본이고(랭킹 화면 주소를 바로 열면 평당가
# 높은순이다, 2026-11-22 웹 조사) 거래 유형마다 정렬이 다르다 (월세는 거래량뿐)
SORT_TYPE_BY_TRADE: dict[LocalTrade, dict[str, ZigbangDanjiRankingSortType]] = {
    '매매': {
        '거래량 많은순': 'volume_desc',
        '하락률 높은순': 'decrease_rate_desc',
        '상승률 높은순': 'increase_rate_desc',
        '시세 높은순': 'price_desc',
        '평당가 높은순': 'unit_price_desc',
        '인기 단지순': 'view_count_desc',
    },
    '전세': {
        '거래량 많은순': 'volume_desc',
        '하락률 높은순': 'decrease_rate_desc',
        '상승률 높은순': 'increase_rate_desc',
        '시세 높은순': 'price_desc',
        '전세가율 높은순': 'charter_rate_desc',
    },
    '월세': {'거래량 많은순': 'volume_desc'},
}
# 정렬마다 줄에 오는 칸 (2026-11-22 표본: 정렬 일곱 가지를 모두 불렀다). 거래량·시세·평당가·인기·전세가율은 사용승인일·총세대수가 오고, 하락률·상승률은
# 직전 거래 대비 값이 오며 사용승인일·총세대수는 오지 않는다. 하락·상승률의 가격 칸은 거래 유형이 정한다 (`_rank_of`)
RATE_FIELDS: frozenset[str] = frozenset({'latest_trade_date', 'prev_trade_diff_manwon', 'prev_trade_diff_percent', 'area_type'})
RANK_FIELDS_BY_SORT: dict[ZigbangDanjiRankingSortType, frozenset[str]] = {
    'volume_desc': frozenset({'trade_count', 'approved_date', 'household_count'}),
    'decrease_rate_desc': RATE_FIELDS,
    'increase_rate_desc': RATE_FIELDS,
    'price_desc': frozenset({'estimated_price_manwon', 'approved_date', 'household_count'}),
    'unit_price_desc': frozenset({'estimated_price_per_pyeong_manwon', 'approved_date', 'household_count'}),
    'view_count_desc': frozenset({'view_count', 'approved_date', 'household_count'}),
    'charter_rate_desc': frozenset({'jeonse_ratio_percent', 'gap_manwon', 'approved_date', 'household_count'}),
}
SORT_ONLY_FIELDS: frozenset[str] = frozenset({'price_manwon', 'deposit_manwon'}).union(*RANK_FIELDS_BY_SORT.values())
# 결과 머리에서 서버가 주지 않는 정렬이라 키를 뺄 날짜 (2026-11-22 표본): 시세·평당가·전세가율은 기준일(end_date)뿐이고, 인기는 갱신 시각이 없다
# (웹 머리 `56955`: 거래량·하락률·상승률은 '{시작} ~ {끝} 실거래 등록 기준 {갱신 시각} 업데이트', 인기는 '{시작} ~ {끝} 조회 기준', 그 밖은 '{기준일} 직방 시세 기준')
SORTS_WITH_START_DATE: frozenset[ZigbangDanjiRankingSortType] = frozenset({
    'volume_desc', 'decrease_rate_desc', 'increase_rate_desc', 'view_count_desc',
})
SORTS_WITH_UPDATED_AT: frozenset[ZigbangDanjiRankingSortType] = frozenset({
    'volume_desc', 'decrease_rate_desc', 'increase_rate_desc',
})
TRADE_PERIODS: tuple[LocalTradePeriod, ...] = ('오늘', '어제', '7일', '15일', '30일')
DEFAULT_TRADE_LIMIT: int = 20
# 웹 기간 탭 (2026-11-19 번들 `h`: 오늘·어제·최근 일주일·최근 15일·최근 30일) → 서버 periodType
PERIOD_TYPE_BY_LABEL: dict[LocalTradePeriod, ZigbangLocalTradePeriodType] = {
    '오늘': 'today',
    '어제': 'yesterday',
    '7일': 'last_7_days',
    '15일': 'last_15_days',
    '30일': 'last_30_days',
}
DEAL_TYPE_BY_TRADE: dict[LocalTrade, ZigbangLocalTradeDealType] = {'매매': 'sales', '전세': 'charter', '월세': 'rent'}
# 웹 정렬 이름 → 서버 sortSpec (2026-11-19 번들 `D`). 첫 항목이 웹 기본이다. 거래 유형마다 정렬이 다르다
SORT_SPEC_BY_TRADE: dict[LocalTrade, dict[str, str]] = {
    '매매': {
        '최신 등록순': 'sales_latest_registration',
        '가격 낮은순': 'sales_lowest_price',
        '가격 높은순': 'sales_highest_price',
        '시세 비교순': 'sales_market_price_comparison',
        '공시가격 대비 낮은순': 'sales_lower_than_public_price',
    },
    '전세': {
        '최신 등록순': 'charters_latest_registration',
        '가격 낮은순': 'charters_lowest_price',
        '가격 높은순': 'charters_highest_price',
        '전세가 비교순': 'charters_lease_price',
    },
    '월세': {
        '최신 등록순': 'rents_latest_registration',
        '월세 높은순': 'rents_highest_monthly_rent_price',
        '보증금 높은순': 'rents_highest_deposit',
    },
}
# 거래 유형에 해당하지 않아 출력에서 키를 뺄 칸. 월세는 웹 줄이 신고가·신저가·갱신·비교를 그리지 않아 뺀다 (응답에 와도 낸 칸이 없다)
SALE_ONLY_FIELDS: frozenset[str] = frozenset({
    'price_manwon',
    'estimated_price_diff_manwon',
    'estimated_price_diff_percent',
    'public_price_diff_manwon',
    'public_price_diff_percent',
    'presale_price_diff_manwon',
    'presale_price_diff_percent',
})
CHARTER_ONLY_FIELDS: frozenset[str] = frozenset({
    'jeonse_comparison_diff_manwon',
    'jeonse_comparison_diff_percent',
    'pre_move_in_contract',
    'renewal',
})
PREV_DIFF_FIELDS: frozenset[str] = frozenset({'prev_trade_diff_manwon', 'prev_trade_diff_percent'})
OFFER_DIFF_FIELDS: frozenset[str] = frozenset({'presale_price_diff_manwon', 'presale_price_diff_percent'})
NOT_APPLICABLE_BY_TRADE: dict[LocalTrade, frozenset[str]] = {
    '매매': frozenset({'deposit_manwon', 'rent_manwon'}) | CHARTER_ONLY_FIELDS,
    '전세': frozenset({'rent_manwon'}) | SALE_ONLY_FIELDS,
    '월세': frozenset({'new_high', 'new_low'}) | SALE_ONLY_FIELDS | CHARTER_ONLY_FIELDS | PREV_DIFF_FIELDS,
}
PRESALE_RIGHT: str = '입주권'
