"""직방 단지 기능(search·trend·info·models)의 상수·코드표와 선택지 별칭."""

import re

from jibsa.providers.zigbang.api.client import ZIGBANG_WEB_URL
from jibsa.providers.zigbang.api.models.request.complex.search import (
    ZigbangDanjiOrder,
    ZigbangDanjiPlaceType,
)
from jibsa.providers.zigbang.api.models.request.complex.trend import (
    ZigbangPriceChartDealType,
    ZigbangPriceChartPeriod,
)
from jibsa.providers.zigbang.service.common.constants import ComplexKind

from typing import Literal


ZigbangComplexPlaceType = Literal['역', '학교', '동', '구']

ZigbangPriceTrendPeriod = Literal['1년', '3년', '전체']
ZigbangPyeongTrendTrade = Literal['전체', '매매', '전월세']

ZigbangComplexOrder = Literal['인기', '최근입주', '시세급변동', '평당가']

# 단지 정보에서 한쪽 유형에만 있는 필드. 다른 유형은 출력에서 키를 뺀다
APT_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({
    'dong_count', 'approved_date', 'construction_company', 'parking_per_household',
    'floor_area_ratio_percent', 'heating', 'listing_counts', 'pyeongs', 'review_count', 'schools',
    'estimated_ranges', 'estimated_prices', 'ranking', 'related_complexes', 'land_trade_permits',
})
OFFICETEL_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({'completed_month', 'has_elevator'})

COMPLEX_KIND_BY_SEARCH_TYPE: dict[str, ComplexKind] = {
    'apartment': 'apt',
    'officetel': 'officetel',
}
PROPERTY_TYPE_BY_COMPLEX_KIND: dict[ComplexKind, str] = {
    'apt': '아파트',
    'officetel': '오피스텔',
}

DANJI_CATALOG_PAGE_SIZE: int = 50

# 학교 주변 단지의 거리 문구 (예: '462m', '1.1km'). 웹 학교 응답에는 숫자 거리가 없다
DISTANCE_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d+(?:\.\d+)?)\s*(km|m)')
# 단지 카드(`danjis/details`)를 한 번에 받는 수. 웹 더보기 화면이 15곳씩 보낸다
DANJI_CARD_BATCH_SIZE: int = 15

COMPLEX_ORDERS: tuple[ZigbangComplexOrder, ...] = ('인기', '최근입주', '시세급변동', '평당가')
# 웹 탭 이름 → `danjis/ids`·`danjis/details` 의 order
DANJI_ORDER_BY_LABEL: dict[ZigbangComplexOrder, ZigbangDanjiOrder] = {
    '인기': 'viewCount',
    '최근입주': 'newest',
    '시세급변동': 'priceChange',
    '평당가': 'areaPrice',
}
# 웹 탭 설명 (2026-11-19 웹 캡처). 카드 둘째 줄(highlight)의 뜻도 탭마다 다르다
COMPLEX_ORDER_DESCRIPTIONS: dict[ZigbangComplexOrder, str] = {
    '인기': '사용자들이 많이 본 단지 순서',
    '최근입주': '곧 입주 예정이거나 최근 1년 내 입주한 단지',
    '시세급변동': '1주간 시세가 급변동한 단지',
    '평당가': '평당 가격이 높은 단지 순서',
}
# 그 조건에 든 단지만 담는 탭. 순서가 아니라 부분 목록이라 total 이 그 곳의 전체 단지 수가 아니다
# (2026-11-20 실측: 강남역 인기 112곳·최근입주 2곳·시세급변동 55곳, 가락동 최근입주 1곳)
SUBSET_ORDERS: tuple[ZigbangComplexOrder, ...] = ('최근입주', '시세급변동')
# 웹 목록 이름. 동·구는 지역 화면의 최근입주 목록뿐이라 따로 없다
TAB_TITLE_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '주변단지', '학교': '배정단지', '동': '', '구': ''}
# [일부] 안내가 단지를 부르는 말. 학교는 같은 결과의 순서 안내(`TAB_TITLE_BY_PLACE_TYPE`)와 어긋나지 않게 '배정단지' 다
SCOPE_NAME_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '주변 단지', '학교': '배정단지', '동': '단지', '구': '단지'}
SEARCH_TYPE_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, ZigbangDanjiPlaceType] = {
    '역': 'subway',
    '학교': 'school',
    '동': 'local',
    '구': 'local',
}
# 주변 단지 정보(`subways`·`schools`)가 있고 거리를 주는 곳. 동·구는 없다
AROUND_PLACE_TYPES: tuple[ZigbangComplexPlaceType, ...] = ('역', '학교')
# 주변 단지 정보(역 `subways`·학교 상세 `schools` 의 배정단지)에서 오는 값. 학교 쪽에는 주소가 없어 주소는 단지 카드에서 받는다
AROUND_FIELDS_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {'역': '이름·주소·세대수·거리', '학교': '이름·세대수·거리'}
# 단지 카드(`danjis/details`)에서 오는 값. 동·구는 주변 단지 정보가 없어 이름·주소·세대수도 카드에서 받는다
CARD_FIELDS_BY_PLACE_TYPE: dict[ZigbangComplexPlaceType, str] = {
    '역': 'highlight',
    '학교': '주소·highlight',
    '동': '이름·주소·세대수·highlight',
    '구': '이름·주소·세대수·highlight',
}
# 웹 학교 화면 하단 안내
SCHOOL_ASSIGNMENT_NOTICE: str = '학군배정 정보는 지역에 따라 실제 배정과 다소 차이가 있을 수 있습니다 (직방 웹 학교 화면 하단 안내)'
# 직방 학교급(stage) → 학교 이름의 급. 모르는 값은 원문 그대로 낸다
SCHOOL_LEVEL_BY_STAGE: dict[str, str] = {'elementary': '초등학교', 'middle': '중학교', 'high': '고등학교'}

# 웹 기간 탭 이름 (번들 `convertDueNameForZams`: 최근1년·최근3년·전체기간, 기본은 두 번째인 최근3년)을 jibsa 는 1년·3년·전체 로 쓴다 → 요청의 period
PRICE_TREND_PERIODS: tuple[ZigbangPriceTrendPeriod, ...] = ('1년', '3년', '전체')
DEFAULT_PRICE_TREND_PERIOD: ZigbangPriceTrendPeriod = '3년'
CHART_PERIOD_BY_LABEL: dict[ZigbangPriceTrendPeriod, ZigbangPriceChartPeriod] = {
    '1년': '1y',
    '3년': '3y',
    '전체': 'all',
}
# 웹 평형 그래프의 거래 탭 이름 (번들 `convertStatusForZams`) → 요청의 dealType
PYEONG_TREND_TRADES: tuple[ZigbangPyeongTrendTrade, ...] = ('전체', '매매', '전월세')
DEFAULT_PYEONG_TREND_TRADE: ZigbangPyeongTrendTrade = '전체'
DEAL_TYPE_BY_TRADE: dict[ZigbangPyeongTrendTrade, ZigbangPriceChartDealType] = {
    '전체': 'all',
    '매매': 'sales',
    '전월세': 'rent',
}
# 웹은 비교 단지를 하나만 고르게 하고 서버는 셋까지 실측했다 (2026-11-22 표본: 단지·비교 셋·구 다섯 줄)
MAX_COMPARE_DANJIS: int = 3
# 비교 후보 안내(hint)에 적는 후보 수. 후보는 보통 세 곳 안팎이다 (2026-11-19 캡처: 헬리오시티 3곳)
MAX_CANDIDATES_IN_HINT: int = 10

# 역 이름으로 역을 찾지 못했을 때 `search complexes` 가 권하는 말 (지역 검색 0건의 REGION_NOT_FOUND 와 역 결과 없음의 INVALID_ARGUMENT 가 같이 쓴다).
# 이 명령에는 좌표 옵션이 없어 기본 안내(--lat/--lng)를 쓰지 않는다
STATION_QUERY_HINT: str = "역 이름 전체를 주세요 (예: 강남역). 학교는 '해누리중학교', 동·구는 '가락동'·'송파구' 처럼 주세요"

# 세대수 문구 (예: '38세대', '1,161세대'). 관련 단지(complex)와 주변 단지 카드·학교·역 응답(search complexes)이 쓴다
HOUSEHOLD_TEXT_PATTERN: re.Pattern[str] = re.compile(r'([\d,]+)\s*세대')
# 오피스텔 단지 매물 웹 페이지 주소 틀. 웹은 건물 ID 를 이 경로의 area_danji_id 자리에 넣는다
OFFICETEL_DANJI_ITEMS_URL: str = f'{ZIGBANG_WEB_URL}/home/officetel/danjis/{{}}/items'
