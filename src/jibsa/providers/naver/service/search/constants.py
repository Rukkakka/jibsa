"""네이버 지도 매물 검색·지역 단지 목록의 상수: 필터 코드표, 안내 문구, 쪽 크기와 요청 상한."""

from jibsa.core.notes import note
from jibsa.providers.naver.api.models.request.common import (
    NaverDirectionType,
    NaverFloorType,
    NaverLoanRatioType,
    NaverMoveInType,
    NaverOptionType,
    NaverParkingType,
    NaverRealEstateType,
    NaverRoomCount,
)
from jibsa.providers.naver.api.models.request.search.complexes import (
    NaverComplexSortType,
)


# 면적 필터 기준. 전용이면 filtersExclusiveSpace 를 켠다. 결과의 area_m2 가 전용면적이라 기본은 전용
AREA_BASES: tuple[str, ...] = ('전용', '공급')


# 유형을 주지 않으면 주거용 전체 (재건축·분양권·재개발·비주거는 빼고).
DEFAULT_SEARCH_PROPERTY_TYPES: tuple[str, ...] = ('아파트', '오피스텔', '빌라', '원룸', '단독·다가구', '전원주택', '상가주택')


# 지도 필터 코드. 방 수는 방 구조 이름(`Listing.room_type`)으로 받되 원룸은 방 1개 전체(오픈형·분리형·복층형)다.
# 코드는 fin.land 지도 URL 과 매물 수·상세 대조로 확인했다 (2026-10-08).
ROOM_COUNT_CODE_BY_NAME: dict[str, NaverRoomCount] = {
    '원룸': 'RCF01',
    '투룸': 'RCF02',
    '쓰리룸': 'RCF03',
    '포룸이상': 'RCF04',
}


FLOOR_CODE_BY_NAME: dict[str, NaverFloorType] = {
    '1층': 'FLF01',
    '저층': 'FLF02',
    '중층': 'FLF03',
    '고층': 'FLF04',
    '탑층': 'FLF05',
    '지하층': 'FLF06',
}


DIRECTION_FILTER_CODE_BY_NAME: dict[str, NaverDirectionType] = {
    '동향': 'EE',
    '서향': 'WW',
    '남향': 'SS',
    '북향': 'NN',
    '북동향': 'EN',
    '남동향': 'ES',
    '북서향': 'WN',
    '남서향': 'WS',
}


BATHROOM_CODE_BY_NAME: dict[str, NaverRoomCount] = {
    '1개': 'RCF01',
    '2개': 'RCF02',
    '3개': 'RCF03',
    '4개이상': 'RCF04',
}


# 코드마다 서로 다른 지도 칸의 매물 4건씩을 상세(basicInfo)와 대조했다. 주차 가능·에어컨·엘리베이터·풀옵션은
# 표본으로 가르지 못해 사이트 URL(주차 가능+에어컨 = OPF02·OPF05)과 소거로 정했다.
FACILITY_CODE_BY_NAME: dict[str, NaverOptionType] = {
    '엘리베이터': 'OPF01',
    '주차': 'OPF02',
    '보안시설': 'OPF03',
    '풀옵션': 'OPF04',
    '에어컨': 'OPF05',
    '테라스': 'OPF06',
    '베란다': 'OPF07',
    '마당': 'OPF08',
    '복층': 'OPF09',
}


# 원룸 구조는 상세에 구조(shape)가 있는 매물에만 걸린다. 단지 매물(아파트·오피스텔·재건축·단지형 빌라·분양권)은
# 구조 값이 없어 모두 빠지고 (역삼동 방 1개: 아파트 435건·오피스텔 2,074건 → 0건, 대치동 재건축 1,024건 → 0건),
# 원룸·빌라·상가주택 등도 중개사가 구조를 입력하지 않은 매물은 빠진다 (역삼동 원룸 전세 35건 → 26건, 빠진 매물은
# shape 가 null. 상가주택 73건 → 11건, 2026-10-10). 서버 필터라 다시 거르지 않고 줄 때마다 알린다
ONE_ROOM_SHAPE_NOTE: str = note(
    '제외',
    '원룸 구조(오픈형·분리형)는 중개사가 구조를 입력한 매물만 걸립니다. 단지로 등록된 매물(아파트·오피스텔·단지형 빌라)은 '
    '구조 값이 없어 모두 빠지고, 다른 매물도 구조를 입력하지 않았으면 빠집니다. 빠짐없이 보려면 --one-room-shape 없이 '
    '--room 원룸 으로 찾고 listing 의 room_type 으로 구조를 확인하세요',
)


MOVE_IN_CODE_BY_NAME: dict[str, NaverMoveInType] = {
    '바로입주': 'MVF01',
    '90일내': 'MVF02',
}


LOAN_CODE_BY_NAME: dict[str, NaverLoanRatioType] = {
    '없음': '00',
    '30%이하': '10',
}


PARKING_CODE_BY_NAME: dict[str, NaverParkingType] = {
    '세대당1대': 'PKF01',
    '세대당1.5대': 'PKF02',
    '전기차충전': 'PKF03',
}


COMPLEX_FILTER_NOTE: str = note(
    '제외', '세대수·단지 주차는 네이버에 단지로 등록된 매물에만 있어, 단지가 없는 매물(빌라 대부분)은 빠졌습니다',
)


# 현관 구조는 단지 여부가 아니라 매물에 현관 구조가 등록됐는지로 걸린다 (2026-11-17 실측: 연남동 빌라 --entrance 계단식에
# 단지가 아닌 빌라 2661884425·2661802815·2661884583 이 남고, --household-min·--parking 에는 셋 다 빠졌다)
ENTRANCE_FILTER_NOTE: str = note(
    '제외', '현관 구조가 등록된 매물만 걸려, 등록되지 않은 매물은 빠졌습니다 (단지가 아닌 빌라도 등록돼 있으면 나옵니다)',
)


# 세대수·단지 주차 조건과 함께면 단지 아닌 매물은 그 조건이 이미 빼므로 ENTRANCE_FILTER_NOTE 의 괄호 말을 뺀다 (2026-11-17 실측:
# 연남동 -t 빌라 --entrance 계단식 --household-min 1 32건 중 5건을 열어 보니 모두 단지 매물이었다)
ENTRANCE_WITH_COMPLEX_FILTER_NOTE: str = note('제외', '현관 구조가 등록된 매물만 걸려, 등록되지 않은 매물은 빠졌습니다')


BOUNDED_PAGE_SIZE: int = 30


MAX_BOUNDED_PAGE_REQUESTS: int = 10


# 동·시·군·구 경계 전체 검색(legalDivisionArticleList)의 페이지 크기. 서버 상한이 30 이다 (50부터 400, 2026-10-09 확인).
# limit 건까지만 받고, 받은 뒤 중복·모르는 거래 유형으로 빠져도 그만큼 다시 받지 않는다
LEGAL_DIVISION_PAGE_SIZE: int = 30


MAX_LEGAL_DIVISION_PAGE_REQUESTS: int = 5


# 지역 단지 목록(naver complexes). 페이지는 30곳(사이트 COMPLEX_PAGINATION_SIZE), 요청은 이 횟수에서 멈춘다
AREA_COMPLEX_CODES_BY_TYPE: dict[str, tuple[NaverRealEstateType, ...]] = {
    '아파트': ('A01',),
    '오피스텔': ('A02',),
    # 단지로 등록된 연립·다세대·도시형생활주택. 역삼동만 779곳이고 대부분 매물이 없다
    '빌라': ('A05', 'A06', 'A07'),
    # 이름은 `SEARCH_CODES_BY_PROPERTY` 와 같다. 응답 모양이 아파트와 같다 (2026-11-18 실측: 재건축 A04 대치동 5곳,
    # 분양권 B01 둔촌동 1곳, 오피스텔분양권 B02 는 넷 지역 모두 0곳이고 서버 답 그대로 낸다)
    '재건축': ('A04',),
    '분양권': ('B01',),
    '오피스텔분양권': ('B02',),
}


COMPLEX_LIST_SORT_TYPE_BY_NAME: dict[str, NaverComplexSortType] = {
    '인기순': 'POPULARITY_DESC',
    '세대수순': 'HOUSEHOLD_NUMBER_DESC',
    '최근입주순': 'USE_APPROVAL_DATE_DESC',
    '매물수순': 'ARTICLE_COUNT_DESC',
}


COMPLEX_LIST_PAGE_SIZE: int = 30


MAX_COMPLEX_LIST_PAGE_REQUESTS: int = 4


RADIUS_EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형 또는 검색 범위(반경) 밖의'


COMPLEX_EXCLUDED_REASON: str = '중복이거나 단지 정보를 알 수 없는'


COMPLEX_RADIUS_EXCLUDED_REASON: str = '중복이거나 단지 정보·위치를 알 수 없거나 검색 범위(반경) 밖의'
