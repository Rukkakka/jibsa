"""소스 전체(여러 기능)가 같이 쓰는 다방 상수·코드표·선택지 별칭."""
import re

from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    Source,
    TradeType,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.dabang.api.client import DABANG_WEB_URL
from jibsa.providers.dabang.api.models.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    REGION_INFO_PAGE_LIMIT,
    DabangCategory,
    DabangRoomBuildingCategory,
    DabangRoomCount,
    DabangRoomFloor,
    DabangRoomType,
    DabangSchoolEstablishmentType,
    DabangSearchType,
    DabangSellingType,
)

from typing import Literal


SOURCE: Source = 'dabang'
# 다방 목록 한 쪽 크기. 서버가 정하고 `limit` 을 보내도 무시한다 (2026-10-25 실측: limit=100 에도 24건). 매물 목록은 다음 쪽이
# 있어도 23건만 줄 때가 있어(2026-11-13 웹 캡처: 아파트 강남역 1쪽) 이어 받을 위치를 이 크기로 셈하지 않는다 (`DabangListPosition`)
PAGE_SIZE: int = 24
DEFAULT_LIST_LIMIT: int = 24
MAX_LIST_LIMIT: int = 120
MANWON_PER_EOK: int = 10000
# search schools·hot-places 의 --limit. 다방 동네정보 목록은 30줄씩 주고(31 이상은 400) 웹도 30줄씩 쪽을 넘긴다. 쪽 넘김을 4쪽까지 한 번에 받는다
REGION_INFO_DEFAULT_LIMIT: int = REGION_INFO_PAGE_LIMIT
REGION_INFO_MAX_LIMIT: int = REGION_INFO_PAGE_LIMIT * 4
# 매물·단지 주소. 서버가 지도 화면으로 넘겨 준다 (2026-10-25 실측: /room/{id} → 302 /map/onetwo?…detail_type=room,
# /complex/{id} → 302 /map/apt?…detail_type=complex). 상세의 짧은 주소(redirect.dabangapp.com)도 /room/{id} 로 넘긴다
# 출력 url 칸의 웹 페이지 주소 틀 (`.format(번호)`)
LISTING_URL: str = f'{DABANG_WEB_URL}/room/{{}}'
COMPLEX_URL: str = f'{DABANG_WEB_URL}/complex/{{}}'
# 분양 페이지. 서버가 지도 화면으로 넘겨 준다 (2026-10-25 실측: /sale-in-lots/{id} → 302 /map/sale-in-lots?…)
SALE_URL: str = f'{DABANG_WEB_URL}/sale-in-lots/{{}}'
COMPLEX_ID_PATTERN: re.Pattern[str] = re.compile(COMPLEX_ID_PATTERN_TEXT)
# 다방 매물 종류 표시 뒤에 붙는 단기임대 표시 ('오피스텔 • 단기'). 단기임대는 따로 있는 거래가 아니라 월세 매물이 1개월 이상
# 단기 계약도 받는다는 뜻이다 (상세 short_lease_str '1개월(이상 협의가능)', 보증금 1000·월세 90 같은 보통 월세에도 붙는다,
# 2026-10-25 실측: 역삼동 원룸 월세 423건 중 275건)
SHORT_LEASE_MARK: str = '단기'

# 명령의 매물 유형 → 다방 목록 유형
ListingKind = Literal['room', 'villa', 'officetel', 'apt']
CATEGORY_BY_KIND: dict[ListingKind, DabangCategory] = {
    'room': 'one-two',
    'villa': 'house-villa',
    'officetel': 'officetel',
    'apt': 'apt',
}
KIND_LABELS: dict[ListingKind, str] = {'room': '원룸·투룸', 'villa': '주택·빌라', 'officetel': '오피스텔', 'apt': '아파트'}
# 주택/빌라 유형의 이름 (인기 매물·동네정보 매물 유형·순위 `-t` 가 같이 쓴다)
VILLA_LABEL: str = '빌라'
POPULAR_BUILDING_BY_LABEL: dict[str, DabangRoomBuildingCategory] = {VILLA_LABEL: 'HOUSE_VILLA', '오피스텔': 'OFFICETEL', '아파트': 'APT'}
# 설립 구분 이름. 웹 동네정보 '학군' 상세 목록의 탭 이름 그대로다 (school-regional 청크, 2026-11-13). 학교·유치원은 국공립·사립,
# 어린이집은 공공·민간·가정·직장·협동이다. 웹 '전체' 탭은 값을 보내지 않는 것이라 옵션을 주지 않으면 된다
ESTABLISHMENT_BY_LABEL: dict[str, DabangSchoolEstablishmentType] = {'국공립': 'PUBLIC', '사립': 'PRIVATE'}
NURSERY_ESTABLISHMENT_BY_LABEL: dict[str, DabangSchoolEstablishmentType] = {
    '공공': 'PUBLIC',
    '민간': 'PRIVATE',
    '가정': 'HOME',
    '직장': 'WORKPLACE',
    '협동': 'COOPERATIVE',
}
ComplexKind = Literal['아파트', '오피스텔']
ComplexType = Literal['APT', 'OFFICETEL']
# 단지 유형 (이름, 코드) 짝. 두 방향 표가 이 한 곳에서 나온다
_COMPLEX_KIND_TYPES: tuple[tuple[ComplexKind, ComplexType], ...] = (('아파트', 'APT'), ('오피스텔', 'OFFICETEL'))
COMPLEX_KINDS: tuple[ComplexKind, ...] = tuple(kind for kind, _ in _COMPLEX_KIND_TYPES)
COMPLEX_KIND_BY_TYPE: dict[str, ComplexKind] = {type_: kind for kind, type_ in _COMPLEX_KIND_TYPES}
COMPLEX_TYPE_BY_LABEL: dict[str, ComplexType] = {kind: type_ for kind, type_ in _COMPLEX_KIND_TYPES}
TRADE_BY_PRICE_TYPE_NAME: dict[str, TradeType] = {'월세': '월세', '전세': '전세', '매매': '매매'}
SELLING_TYPE_BY_TRADE: dict[str, DabangSellingType] = {'월세': 'MONTHLY_RENT', '전세': 'LEASE', '매매': 'SELL'}
# 원룸·투룸 목록은 매매를 받지 않는다 (매매만 보내면 무시하고 월세를 준다, 2026-10-25 실측)
TRADE_TYPES_BY_KIND: dict[ListingKind, tuple[TradeType, ...]] = {
    'room': ('월세', '전세'),
    'villa': ('월세', '전세', '매매'),
    'officetel': ('월세', '전세', '매매'),
    'apt': ('월세', '전세', '매매'),
}
FLOOR_FILTER_BY_LABEL: dict[str, DabangRoomFloor] = {
    '1층': 'GROUND_FIRST',
    '2층이상': 'GROUND_SECOND_OVER',
    '반지하': 'SEMI_BASEMENT',
    '옥탑': 'ROOFTOP',
}
ROOM_TYPE_FILTER_BY_LABEL: dict[str, DabangRoomType] = {'원룸': 'ONE_ROOM', '투룸': 'TWO_ROOM'}
# 방 개수. FOUR_ROOM 은 웹 필터의 '4개 이상' 이다
ROOM_COUNT_FILTER_BY_LABEL: dict[str, DabangRoomCount] = {
    '원룸': 'ONE_ROOM',
    '투룸': 'TWO_ROOM',
    '쓰리룸': 'THREE_ROOM',
    '포룸이상': 'FOUR_ROOM',
}
ROOM_LABELS_BY_KIND: dict[ListingKind, tuple[str, ...]] = {
    'room': tuple(ROOM_TYPE_FILTER_BY_LABEL),
    'villa': tuple(ROOM_COUNT_FILTER_BY_LABEL),
    'officetel': tuple(ROOM_COUNT_FILTER_BY_LABEL),
    'apt': tuple(ROOM_COUNT_FILTER_BY_LABEL),
}
# 기타 조건 라벨 → 필터 필드. 유형마다 받는 필드가 다르다 (filter-init 청크, 2026-10-25). '세안고' 는 웹 아파트 '추가필터' 의
# 이름 그대로다 (세입자가 있는 채로 파는 매매 매물, filter 청크 2026-11-13)
CONDITION_FIELD_BY_LABEL: dict[str, str] = {
    '주차': 'can_parking',
    '엘리베이터': 'has_elevator',
    '단기임대': 'is_short_lease',
    '분리형': 'is_division',
    '복층': 'is_duplex',
    '세안고': 'has_take_tenant',
}
CONDITIONS_BY_KIND: dict[ListingKind, tuple[str, ...]] = {
    'room': ('주차', '엘리베이터', '단기임대', '분리형', '복층'),
    'villa': ('주차', '엘리베이터', '단기임대'),
    'officetel': ('주차', '엘리베이터', '단기임대'),
    'apt': ('단기임대', '세안고'),
}

SchoolLevel = Literal['초등학교', '중학교', '고등학교']
SCHOOL_LEVELS: tuple[SchoolLevel, ...] = ('초등학교', '중학교', '고등학교')
# 웹 지도 확대 수준 (동 14, 역·대학 15, 지도 범위 16). 동·역 검색에도 필수라 보낸다 (빠지면 400 "줌은 필수값 입니다")
ZOOM_BY_SEARCH_TYPE: dict[DabangSearchType, int] = {'region': 14, 'subway': 15, 'univ': 15, 'bbox': 16}

# 가격 글자: '1000', '3억9000', '22억', '31억 3,000' (단지 목록은 띄어쓰기·쉼표), '61.1억'
MANWON_TEXT_PATTERN: re.Pattern[str] = re.compile(r'^(?:(\d+(?:\.\d+)?)억)?(\d+(?:\.\d+)?)?$')
FLOOR_NUMBER_PATTERN: re.Pattern[str] = re.compile(r'^(지하)?(\d+)층$')
# 숫자 글자: '1,074개', '60위', '대학교 163명', '4.1명', '5.52:1', '261/1071', '115.54㎡', '-0.6%', '+2.6%'
NUMBER_TEXT_PATTERN: re.Pattern[str] = re.compile(r'([+-]?)(\d[\d,]*(?:\.\d+)?)')
# 세대수 글자: '아파트 · 48년차 · 615세대' (단지 목록), '594세대' (분양 목록), '11년차ㆍ3636세대ㆍ…' (거래 순위)
HOUSEHOLDS_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d[\d,]*)\s*세대')
# 연차 글자: 세대수와 같은 칸에 온다 ('48년차', '11년차')
YEARS_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d+)\s*년차')
# 다방 층 글자 → jibsa 표기 (normalize_floor 가 맞추는 직방 표기). 다방은 반지하를 '반지층' 으로 쓴다 (2026-10-25 역삼동 목록)
FLOOR_LABELS: dict[str, str] = {'반지층': '반지하'}
# 덤 조회(최근 실거래 요약·대출 계산 조건·`--details` 의 매물 상세)가 실패해도 이미 받은 결과는 돌려줄 예외. 세 소스 공통 범위에
# 요청 제한(분당 상한 대기·429 쿨다운)을 더한다. 받아 둔 단지 정보·매물 목록까지 버리지 않는다 (당근 `OPTIONAL_LOOKUP_ERRORS` 와 같은 뜻)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)
# 없는 ID 의 400 사유에 늘 든 말. 2026-10-28 실측: 매물번호 '존재하지 않는 방입니다.', 매물 상세 '존재하지 않는 매물입니다.',
# 단지·단지 둘레 '존재하지 않는 단지입니다.', 매물 둘레 '존재하지 않는 방입니다.', 분양 '존재하지 않는 분양정보입니다.'
MISSING_ID_MESSAGE: str = '존재하지 않'

# 목록 면적이 전용이 아니라 공급면적인 매물 유형 (`room_item_to_listing`)
APARTMENT_TYPE: str = '아파트'
# 다방이 계약면적을 주는 매물 유형 (`DabangListingDetail.contract_area_m2`)
OFFICETEL_TYPE: str = '오피스텔'
# 단지가 있는 매물 유형. 상세 유형은 '오피스텔(분리형)' 처럼 뒤에 구조를 붙여 와서 앞부분으로 본다
COMPLEX_PROPERTY_TYPES: tuple[str, ...] = (OFFICETEL_TYPE, APARTMENT_TYPE)
