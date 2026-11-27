"""당근 service 공통 상수: 여러 기능이 쓰는 코드표·이름표·한도."""

import re

from jibsa.core.errors import JibsaError
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    ListingStatus,
    TradeType,
)
from jibsa.providers.daangn.api.client import DAANGN_WEB_URL
from jibsa.providers.daangn.api.models.request.common import (
    DaangnBuildingApprovalDate,
    DaangnComplexType,
    DaangnDealType,
    DaangnFloor,
    DaangnOption,
    DaangnRoomCount,
    DaangnSalesType,
    DaangnSubSalesType,
    DaangnTradeType,
)


PROPERTY_TYPE_BY_SALES_TYPE: dict[str, str] = {
    'APART': '아파트',
    'OFFICETEL': '오피스텔',
    'OPEN_ONE_ROOM': '원룸',
    'SPLIT_ONE_ROOM': '원룸',
    'TWO_ROOM': '투룸',
    'HOUSE': '주택',
    'STORE': '상가',
    'OFFICE': '사무실',
    'BUILDING': '건물',
    'LAND': '토지',
    'FACTORY': '공장·창고',
}


# 당근 TWO_ROOM 은 '투룸 이상'이라 쓰리룸·포룸도 들어 있다. 방 구조는 방 수로만 알 수 있는데
# 지도 피드(목록)에는 방 수가 없어 목록은 원룸 구조만, 상세는 방 수로 정한다 (`room_type_of`).
ROOM_TYPE_BY_SALES_TYPE: dict[str, str] = {
    'OPEN_ONE_ROOM': '오픈형원룸',
    'SPLIT_ONE_ROOM': '분리형원룸',
}


# 단지 건물에 있는지 알릴 원룸·투룸 카테고리 (`complex_building_notes`)
ROOM_SALES_TYPES: frozenset[str] = frozenset({'OPEN_ONE_ROOM', 'SPLIT_ONE_ROOM', 'TWO_ROOM'})


PROPERTY_TYPES: tuple[str, ...] = ('아파트', '오피스텔', '원룸', '투룸', '주택', '상가', '사무실', '건물', '토지', '공장·창고')


# 출퇴근 API 가 같은 이름 역 뒤에 붙이는 노선 꼬리 ('양평역(경의중앙선)', `station_name`)
STATION_LINE_SUFFIX_PATTERN: re.Pattern[str] = re.compile(r'\s*\([^()]*\)$')


TRADE_TYPE_BY_TRADE: dict[str, TradeType] = {
    'MONTH': '월세',
    'BORROW': '전세',
    'BUY': '매매',
    # 단기임대 (ShortTrade). 월세처럼 보증금·월세가 있다.
    'SHORT': '단기임대',
    # 연세 (YearTrade). 1년치 월세를 한 번에 내는 제주 거래라 보증금·연세(yearlyPay)가 있고 월세는 없다
    'YEAR': '연세',
}


TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세', '단기임대', '연세')


# 내보내는 매물의 거래 상태 (웹 목록·상세의 표시 그대로). 거래완료(TRADED)는 만료 매물이라 없다 (`is_available`)
LISTING_STATUS_BY_STATUS: dict[str, ListingStatus] = {'ON_GOING': '판매중', 'RESERVED': '예약중'}


# 웹이 쿼리를 바꿔 해시가 목록에서 빠졌을 때의 에러 코드
PERSISTED_QUERY_REJECTED_CODES: frozenset[str] = frozenset({'PERSISTED_QUERY_NOT_IN_LIST', 'PERSISTED_QUERY_NOT_FOUND'})


# 월세가 있는 거래 조건
MONTHLY_TRADES: frozenset[str] = frozenset({'MONTH', 'SHORT'})


# 층을 숫자 대신 밝힌 값 (당근 웹 표기)
AMBIGUOUS_FLOOR_LABELS: dict[str, str] = {
    'LOW': '저층',
    'MIDDLE': '중층',
    'HIGH': '고층',
}


# 단지 유형 (당근 웹 표기)
COMPLEX_TYPE_LABELS: dict[str, str] = {
    'APARTMENT': '아파트',
    'OFFICETEL': '오피스텔',
    'MIXED_USE': '주상복합',
    'LIVING_ACCOMMODATION': '생활숙박시설',
    'REDEVELOPMENT': '재개발',
}


# 당근 웹이 평형을 공급 평 묶음(supplyPyeongAreaGroups)으로 고르는 아파트형 단지 (services2 `Os`). 그 밖은 전용면적 묶음이다
APARTMENT_COMPLEX_TYPES: frozenset[str] = frozenset({'APARTMENT', 'MIXED_USE', 'REDEVELOPMENT'})


# 실거래가 거래 유형 (당근은 매매와 전월세를 나눠 주고, 전월세는 type 으로 가른다)
REAL_PRICE_TRADE_TYPES: tuple[str, ...] = ('매매', '전세', '월세')


# 매물 목록(search listings)의 --limit 최대값. CLI 옵션의 max 와 상한 안내(`listing_budget_notes`)가 함께 쓴다
LISTING_MAX_LIMIT: int = 120


# 단지 목록(search complexes, search locations 의 단지 후보, school 의 배정 단지)의 --limit 최대값.
# CLI 옵션의 max 와 `list_region_complexes`·`search_complexes`·`get_school` 의 상한 안내가 함께 쓴다
COMPLEX_LIST_MAX_LIMIT: int = 1200


# 지역 단지 목록 (웹 지도 단지 탭): 단지 유형·거래 유형·정렬 라벨 → 당근 값
COMPLEX_TYPE_FILTER_BY_LABEL: dict[str, DaangnComplexType] = {'아파트': 'APARTMENT', '오피스텔': 'OFFICETEL'}


# 웹 지도 화면 (데스크톱). 지도 범위 매물 목록(`search`)과 지도 범위 단지 목록(`complex`)이 함께 쓴다. jibsa 는 화면이 없어 웹을 데스크톱 1440×900 창으로 열었을 때의 범위를 쓴다. 웹은 지도 왼쪽의
# 메뉴(180px)와 매물 목록 패널(400px + 여백 16px)을 뺀 영역의 북동·남서 꼭짓점을 목록 범위로 보내고, 고른 곳을 그 영역의
# 가운데에 둔다 (MapView 의 `Wi`, mapPanelOffset). 지도 타일은 512px 이다 (maplibre)
MAP_VIEW_WIDTH_PX: int = 1440 - 180 - 416


MAP_VIEW_HEIGHT_PX: int = 900


MAP_TILE_PX: int = 512


# 지도 목록을 여는 줌 범위. 웹 데스크톱은 줌 8 부터 '매물 N개' 칩을 띄운다 (MapShell)
MAP_ZOOM_MIN: int = 8


MAP_ZOOM_MAX: int = 18


# 역·대학·좌표를 고르면 웹 지도가 여는 줌 (검색창 선택의 `rs`)
POINT_ZOOM: int = 15


# 덤 조회(매물 수·시·도·좌표의 동·단지 후보·후기 수·검색창 후보)가 잡는 실패.
# 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`: HTTPError, 응답 형식 변경의 ValueError)에 JibsaError(해시 거절·GraphQL
# 에러·요청 제한)를 더한다. 요청 제한을 바로 올릴 곳은 이보다 먼저 잡는다.
# 전에는 ValueError 를 잡지 않아 덤 조회 하나가 차단 페이지를 받으면 모아 둔 매물(최대 120건)까지 잃고 PARSE_ERROR 로
# 끝났다. 2026-10-11 사용자 결정으로 결과는 돌려주고 `notes` 로 알린다 (주된 조회는 그대로 PARSE_ERROR).
# 걸리는 다른 경우도 결과는 맞다 (2026-10-11 실측):
# - 상태 폴더 오류(StateDirError, JibsaError)도 잡히지만 다음 요청이 같은 이유로 실패해 결국 그 에러와
#   '다른 소스로 다시 시도하지 마세요' 힌트로 끝난다
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, JibsaError)


# 역·대학 주변 매물(`connection_edges`)은 요청당 100건까지 준다 (2026-10-10 실측: first=200 이어도 100건)
STATION_PAGE_SIZE: int = 100


# 필터로 보내는 매물 종류. 원룸(ONE_ROOM)은 오픈형·분리형 원룸을 함께 찾는다
SALES_TYPE_BY_PROPERTY_TYPE: dict[str, DaangnSalesType] = {
    '아파트': 'APART',
    '오피스텔': 'OFFICETEL',
    '원룸': 'ONE_ROOM',
    '투룸': 'TWO_ROOM',
    '주택': 'HOUSE',
    '상가': 'STORE',
    '사무실': 'OFFICE',
    '건물': 'BUILDING',
    '토지': 'LAND',
    '공장·창고': 'FACTORY',
}


TRADE_FILTER_BY_TRADE_TYPE: dict[str, DaangnTradeType] = {
    '월세': 'MONTH',
    '전세': 'BORROW',
    '매매': 'BUY',
    '단기임대': 'SHORT',
    '연세': 'YEAR',
}


# 아래 필터 라벨은 당근 웹 지도 필터의 이름 그대로다 (띄어쓰기만 뺐다)
FLOOR_FILTER_BY_LABEL: dict[str, DaangnFloor] = {
    '반지하': 'SEMI_BASEMENT',
    '1층': 'FIRST',
    '2~5층': 'SECOND_TO_FIFTH',
    '6~9층': 'SIX_TO_NINTH',
    '10층이상': 'TENTH_OR_MORE',
}


ROOM_COUNT_FILTER_BY_LABEL: dict[str, DaangnRoomCount] = {
    '2개': 'TWO',
    '3개': 'THREE',
    '4개이상': 'FOUR_OR_MORE',
}


STRUCTURE_FILTER_BY_LABEL: dict[str, DaangnSubSalesType] = {
    '오픈형': 'OPEN_ROOM',
    '분리형': 'SPLIT_ROOM',
}


BUILDING_APPROVAL_FILTER_BY_LABEL: dict[str, DaangnBuildingApprovalDate] = {
    '5년이내': 'LESS_5YEARS',
    '10년이내': 'LESS_10YEARS',
    '15년이내': 'LESS_15YEARS',
    '20년이내': 'LESS_20YEARS',
    '25년이내': 'LESS_25YEARS',
    '30년이내': 'LESS_30YEARS',
    '30년이상': 'MORE_30YEARS',
}


DEAL_FILTER_BY_LABEL: dict[str, DaangnDealType] = {
    '직거래': 'DIRECT',
    '중개': 'BROKER',
}


OPTION_FILTER_BY_LABEL: dict[str, DaangnOption] = {
    '주차가능': 'PARKING',
    '반려동물가능': 'PET',
    '대출가능': 'MORTGAGE',
    '엘리베이터': 'ELEVATOR',
    '옥탑': 'ROOFTOP',
    '복층': 'LOFT',
}


# 단지마다 보여 줄 최근 실거래 수 (당근은 10건을 준다)
COMPLEX_RECENT_TRADES: int = 3
# 출력 url 칸의 매물·단지 웹 페이지 주소 틀 (`.format(번호)`)
ARTICLE_URL: str = f'{DAANGN_WEB_URL}/articles/{{}}'
COMPLEX_URL: str = f'{DAANGN_WEB_URL}/complexes/{{}}'
