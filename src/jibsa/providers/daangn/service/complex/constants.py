"""단지 기능(complex)의 상수: 후보·쪽 크기, 단지 매물 쪽 수, 단지 목록 거래·정렬 이름표, 사용승인일 패턴."""

import re

from jibsa.providers.daangn.api.models.request.common import (
    DaangnComplexTradeType,
    DaangnSalesType,
)
from jibsa.providers.daangn.api.models.request.complex.search import DaangnComplexSort


# 단지 이름 검색 후보 수. 당근 단지 검색은 이름이 조금 비슷한 단지까지 이름이 맞는 순으로 100곳 넘게 줘서, 찾는 단지는 앞쪽에
# 있고 나머지는 토큰만 쓴다 (2026-10-31 실측: '헬리오시티' 100곳 중 관련 5곳이 1~5위, '은마' 1~5위, '래미안대치팰리스' 1위,
# '잠실엘스'·'목동신시가지' 앞쪽 모두 관련. 120 이면 이름 하나 찾는 데 약 4,900토큰). 더 있으면 --limit 을 늘리라고 알린다
COMPLEX_CANDIDATE_LIMIT: int = 20


# 단지 후보(searchComplexes)·지역 단지(complexes)를 한 번에 받는 수 (서버 최대 50). 단지 후보·지역 단지·단지 매물은 남은
# 한도만큼(first)만 요청하고, 서버도 first 만큼만 준다 (2026-10-11 실측: 단지 매물 first 3·7 → 3·7건). 그래도 비공식
# API 라 넘게 주면 [:limit] 로 자르고, 잘린 만큼을 has_more('더 있음') 로 센다
COMPLEX_PAGE_SIZE: int = 50


# 단지 정보의 중·고등학교는 학군 전체(수십 곳)가 와서, 당근 웹 학군 카드처럼 `_web_school_card` 규칙으로 남긴 앞 몇 곳만
# 보여 준다 (ComplexSchoolSection `slice(0,2)`)
NEAREST_SCHOOLS: int = 2


# 단지 매물 목록은 20건씩 최대 6페이지. 제외된 만큼 추가 조회하지 않는다
COMPLEX_LISTINGS_PAGE_SIZE: int = 20


COMPLEX_LISTINGS_MAX_PAGES: int = 6


# 웹이 조건 없는 화면에 기본으로 보내는 매물 종류. 단지 매물 패널(`ComplexArticleListPanel` 의 `F`)은 늘 주거 5종이 기본이다
# (2026-11-12 번들 대조)
COMPLEX_LISTING_DEFAULT_SALES_TYPES: tuple[DaangnSalesType, ...] = ('APART', 'HOUSE', 'OFFICETEL', 'ONE_ROOM', 'TWO_ROOM')


COMPLEX_TRADE_BY_TRADE_TYPE: dict[str, DaangnComplexTradeType] = {'매매': 'BUY', '전세': 'BORROW', '월세': 'MONTH'}


# 웹 지도 단지 탭의 기본 거래 유형 (ChatPanelActionsContext `d`: 거래 칩이 없으면 BUY)
DEFAULT_COMPLEX_TRADE_TYPE: str = '매매'


COMPLEX_SORT_BY_LABEL: dict[str, DaangnComplexSort] = {
    '세대수': 'HOUSEHOLD_COUNT_DESC',
    '가격높은순': 'TRADE_PRICE_DESC',
    '가격낮은순': 'TRADE_PRICE_ASC',
    '입주최신순': 'MOVE_IN_DATE_DESC',
    '입주오래된순': 'MOVE_IN_DATE_ASC',
}


# 입주일 순은 사용승인일 순과 어긋나는 단지가 섞여 온다 (2026-10 역삼동 실측)
MOVE_IN_SORT_NOTE: str = (
    '입주일 순은 당근이 정한 순서라 사용승인일(approved_date) 순서와 어긋나는 단지가 있습니다. '
    '새 단지·오래된 단지는 approved_date 로 다시 확인하세요'
)


APPROVAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'(\d{4})\.(\d{2})\.(\d{2})')
