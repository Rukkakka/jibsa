"""네이버 service 공통 상수: 여러 기능이 쓰는 거래·유형 코드표, 정렬·한도, 안내 문구, 모델 설명 글."""

from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.providers.naver.api.client import NAVER_WEB_URL
from jibsa.providers.naver.api.request.common import (
    NaverArticleSortType,
    NaverEntranceType,
    NaverOneRoomShape,
    NaverRealEstateType,
)

from typing import Literal


TRADE_CODE_BY_NAME: dict[str, str] = {
    '매매': 'A1',
    '전세': 'B1',
    '월세': 'B2',
    '단기임대': 'B3',
}


TRADE_NAME_BY_CODE: dict[str, str] = {code: name for name, code in TRADE_CODE_BY_NAME.items()}


# 매매·전세만 받는 조회의 거래 유형 이름 → 코드 (동네 추이·빌라 평당 실거래가. 네이버가 월세 값은 주지 않는다)
SALE_JEONSE_CODE_BY_NAME: dict[str, Literal['A1', 'B1']] = {'매매': 'A1', '전세': 'B1'}


OFFICETEL_CODE: str = 'A02'


# 지도 검색에 보내는 매물 유형 코드. 네이버는 단지로 등록된 빌라를 C02 가 아닌 A05(연립 단지)·A06(다세대 단지)로
# 따로 분류해, C02 만 보내면 빌라의 약 30% 가 빠진다 (역삼동 1km: C02 1124건, A05 33건, A06 408건).
# fin.land 지도의 빌라 필터와 같게 A07(도시형생활주택 단지)까지 함께 보낸다.
SEARCH_CODES_BY_PROPERTY: dict[str, tuple[NaverRealEstateType, ...]] = {
    '아파트': ('A01',),
    '오피스텔': ('A02',),
    '빌라': ('C02', 'A05', 'A06', 'A07'),
    '원룸': ('C01',),
    '단독·다가구': ('C03',),
    '전원주택': ('C04',),
    '상가주택': ('D05',),
    '한옥': ('C06',),
    '고시원': ('G01',),
    '재건축': ('A04',),
    '분양권': ('B01',),
    '오피스텔분양권': ('B02',),
    '재개발': ('F01',),
    '사무실': ('D01',),
    '상가': ('D02',),
    '건물': ('D03',),
    '상가건물': ('D04',),
    '숙박': ('E01',),
    '공장·창고': ('E02',),
    '토지': ('E03',),
    '지식산업센터': ('E04',),
    '기타': ('Z00',),
}


PROPERTY_NAME_BY_CODE: dict[str, str] = {
    code: name for name, codes in SEARCH_CODES_BY_PROPERTY.items() for code in codes
}


ONE_ROOM_SHAPE_CODE_BY_NAME: dict[str, NaverOneRoomShape] = {
    '오픈형': '10',
    '분리형': '20',
}


# 현관 구조 (검색 조건 이름 → 코드). 상세의 현관 구조 글자도 이 표의 반대 방향이다
ENTRANCE_CODE_BY_NAME: dict[str, NaverEntranceType] = {
    '계단식': '10',
    '복도식': '20',
    '복합식': '30',
}


# 확인 방식(verificationInfo.verificationType) → 확인 배지. 네이버 웹 번들 대조 (2026-11-17: 상수 VERIFICATION_TYPE,
# 목록 PropertyBadgeList.tsx, 이름표 함수 getOwnerLabel). 이 밖의 코드(NONE, DOC, TEL, DOCV2, NDOC2, LESR, LH, FT, JOINT)와
# 표에 없는 코드는 웹도 방식 배지를 붙이지 않는다 (날짜 배지와 'HUG 안심임대인' 은 따로 있어 여기서 다루지 않는다)
OWNER_VERIFICATION_TYPES: frozenset[str] = frozenset({'MOBL', 'OWNER', 'NDOC1'})


SITE_VERIFICATION_TYPES: frozenset[str] = frozenset({'SITE', 'S_VR'})


# 웹은 비주거 매물의 집주인 배지를 '소유자' 로 바꿔 보여 준다. 고시원(G01) 같이 이 열 개에 없는 유형은 '집주인' 이다
NON_RESIDENTIAL_TYPES: frozenset[str] = frozenset({'D01', 'D02', 'E04', 'D03', 'D04', 'E01', 'E02', 'Z00', 'E03', 'F01'})


WON_PER_MANWON: int = 10_000


# 검색 모드(search listings·complexes·redevelopment, --complex·--redevelopment)의 --limit 최대값.
# CLI 옵션의 max 와 상한 안내(`pagination_notes`)가 함께 쓴다
MAX_LIST_LIMIT: int = 120


# 매물 목록 정렬. 네이버 웹 정렬(ARTICLE_SORT_TYPE)의 여섯이고 거리순은 없다. 반경 검색은 반경을 감싼 사각형 안 매물
# 목록(boundedArticles)을, 동 전체는 동 매물 목록을 이 정렬 그대로 받는다
SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType] = {
    '랭킹순': 'RANKING_DESC',
    '가격낮은순': 'PRICE_ASC',
    '가격높은순': 'PRICE_DESC',
    '최신순': 'DATE_DESC',
    '면적좁은순': 'SPACE_ASC',
    '면적넓은순': 'SPACE_DESC',
}


# 단지·재개발 구역 매물 목록 정렬. 지역 매물 검색과 같은 표라 별칭으로 둔다. 가까운순은 이쪽에 원래 없어 그 안내(cli 의
# NEAREST_SORT_HINT)는 search_command 가 지역 검색 모드에만 붙인다
COMPLEX_SORT_TYPE_BY_NAME: dict[str, NaverArticleSortType] = SORT_TYPE_BY_NAME


ASKING_RANGES_DESCRIPTION: str = (
    '거래 유형별 호가 범위 {sale·jeonse·wolse·short_term: {lowest, highest}}. sale 은 price_manwon, jeonse 는 deposit_manwon, wolse·short_term 은 보증금·월세 짝 '
    '(deposit_manwon·rent_manwon). 월세·단기임대의 두 끝은 월세 최저·최고가 아니라 가격순 첫 매물의 짝이라 rent_manwon 이 거꾸로일 수 있다 '
    '(빌라 단지는 월세가 대개 없다). 그 거래 매물이 없거나(네이버가 값을 주지 않거나 0) 가격 정보가 없는 거래 유형은 키가 없고, 네이버가 호가 정보 '
    '자체를 주지 않으면 null. 한 끝만 비면 그 끝 금액만 null. 월세·단기임대는 한 짝의 월세만 0 이면 그 rent_manwon 만 null, '
    '한 짝이 보증금·월세 모두 0 이면 그 짝 두 값 모두 null'
)


"""`NaverComplexSummary`·`NaverAreaComplex`·`NaverSchoolComplex` 의 `asking_ranges` 설명. 모델끼리 필드를 함께 쓸 수 없어 상수로 공유한다. `confirmed_date` 설명(`CONFIRMED_AT_DESCRIPTION`)도 목록·상세가 함께 쓴다."""


MARKET_PRICE_PROVIDER_NAMES: dict[str, str] = {'kab': '한국부동산원', 'kbstar': 'KB부동산', 'neonet': '부동산뱅크'}


# 부가 정보 조회에서 그 값만 모름(None)으로 두는 오류: 세 소스 공통 범위(`OPTIONAL_LOOKUP_BASE_ERRORS`, 압축이 깨진
# 응답도 HTTPError)만 잡는다. 요청 제한(RateLimitedError)은 JibsaError 라 잡지 않아 그대로 올라간다.
# 제한을 끈 정책(RateLimitPolicy(enabled=False))이면 429 가 HTTPStatusError 로 와 여기서 모름이 되지만, 그 정책은
# 라이브러리로 직접 만들 때만 쓰이고 CLI 는 늘 켜 둔다 (core/ratelimit.py on_rate_limited, 2026-10-11 확인).
# ValidationError 는 람다 안에서 만드는 요청 모델 오류도 잡지만, 요청 값은 CLI 가 검증한 값이나 네이버 응답 값
# (법정동 코드 10자리, 단지 유형 코드 등)이라 사용자 입력으로는 생기지 않는다 (2026-10-10 확인)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = OPTIONAL_LOOKUP_BASE_ERRORS


# 단지형 빌라(연립·다세대·도시형생활주택 단지). 학교는 이 유형이면 villa 로 묻는다
VILLA_COMPLEX_CODES: frozenset[str] = frozenset({'A05', 'A06', 'A07'})


SCHOOL_ALLOCATION_LABELS: dict[str, str] = {'01': '배정', '02': '선택'}


HUG_SAFE_LESSOR_BADGE: str = 'HUG 안심임대인'


DONG_LETTER_BY_SPELLING: dict[str, str] = {
    '에이': 'A', '비': 'B', '씨': 'C', '디': 'D', '이': 'E', '에프': 'F', '지': 'G', '에이치': 'H',
}


"""한글로 쓴 영문 동 이름. 단지마다 'A' 로도 '에이' 로도 온다 (성재하이빌 '에이'·'비', 2026-10-09 확인)."""


# `pagination_notes` 의 제외 사유. 반경 밖은 사각형으로 받아 반경으로 거르는 검색(반경 매물·단지·재개발 구역)에만 있다.
# 동 전체·단지·재개발 구역 매물은 반경 없이 받아, '반경 밖' 이라고 하면 쓸 수 없는 --radius 를 바꾸게 만든다.
# 목록 응답에는 매물 상태·노출 여부 필드가 없어 거래 불가로 빼는 매물은 없다. 빼는 것은 번호가 같은 중복과 모르는 거래 유형
# 코드(`article_info_to_listing`)뿐이다 (2026-10-14 실측: 역삼동 동 전체 목록 20건의 모든 키에 상태 필드 없음)
# 단지 목록(`search.py` `list_area_complexes`)은 거래 유형으로 빼지 않고 본문(단지 정보)이 없는 단지를 뺀다. 위치가 없는 단지는
# 반경 안인지 알 수 없는 반경 검색에서만 빼고, 경계 검색은 위치로 빼지 않는다 (2026-11-24 리뷰)
EXCLUDED_REASON: str = '중복이거나 알 수 없는 거래 유형인'


# 반경 검색의 서버 집계(total)가 센 범위. 반경 원이 아니라 그 원을 감싼 사각형 안이라 반경 안 수보다 크다
RADIUS_TOTAL_BASIS: str = '반경을 감싼 사각형 안'


# real-price·market-price 의 --period (이름 → 달 수). 웹 실거래·시세 기간 선택지는 startDate 로 보내는 3개월·3년·5년이고 1년은 jibsa 가 더한 값이다
PERIOD_MONTHS_BY_NAME: dict[str, int] = {'3개월': 3, '1년': 12, '3년': 36, '5년': 60}


BADGES_DESCRIPTION: str = (
    "네이버 화면의 확인 배지 (집주인·소유자·현장). 확인 정보가 있으면 그 뒤에 집주인이 HUG 안심임대인일 때 'HUG 안심임대인' 이 붙는다. "
    '방식 배지·HUG 배지가 모두 없으면 [], 모르면 null. 전화·서류로 확인한 매물과 확인하지 않은 매물도 HUG 안심임대인이면 '
    "['HUG 안심임대인'] 이라, 비어 있지 않다고 집주인·현장 확인 매물인 것은 아니다"
)


"""목록 매물(`NaverListing`)과 상세(`NaverListingDetail`)의 `badges` 설명. 두 모델은 상속이 갈려 필드를 함께 쓸 수 없다."""


CONFIRMED_AT_DESCRIPTION: str = (
    "네이버가 매물을 확인한 날 (YYYY-MM-DD). 웹 목록은 협회 매물이 아니면 이 날짜로 '25.11.17. 확인매물' 날짜 배지를, 협회 매물이면 "
    "노출 시작일(`registered_date`)로 '등록' 배지를 그린다. 목록과 상세의 글자 규칙이 달라 날짜만 낸다. 모르면 null"
)


# 매물 유형(realEstateType)마다 웹 화면이 칸을 아예 그리지 않는 필드. 키째 뺀다 (칸이 있는데 값을 모르면 null 이다). 상세(`NaverListingDetail`)와
# 목록(`NaverListing`)이 함께 쓴다. 목록 모델에 없는 필드 이름은 출력에서 그냥 지나간다.
# 2026-11-17 네이버 웹 번들 대조: 기본 정보 칸은 청크 0n-xsnd22pdxz 의 getBasicInfoSpaceTarget·면적 함수, 건축물 정보
# ArticleBuildingInfo 는 isBuildingRegistrationType 유형만, 시설 ArticleFacilityInfo 는 토지_임야(E03) 만 제외 (청크 0l4pkwg0qhg2t)
NOT_APPLICABLE_FIELDS_BY_TYPE: dict[str, frozenset[str]] = {
    # 토지
    'E03': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'has_elevator', 'options',
    }),
    # 고시원: 시설 칸은 있어 has_elevator·options 는 남긴다
    'G01': frozenset({
        'room_count', 'bathroom_count', 'room_type', 'direction', 'floor', 'building_floor', 'area_m2', 'area_pyeong',
        'supply_area_m2', 'approved_date', 'heating', 'heating_fuel', 'entrance', 'parking', 'loan_manwon',
    }),
    # 재개발
    'F01': frozenset({'room_count', 'bathroom_count', 'room_type', 'area_m2', 'area_pyeong', 'supply_area_m2'}),
    # 사무실·상가·지식산업센터: 웹은 방/욕실 대신 '화장실 수' 만 그린다 (bathroom_count 는 남긴다)
    **dict.fromkeys(('D01', 'D02', 'E04'), frozenset({'room_count', 'room_type'})),
    # 건물·상가건물·숙박·공장창고·기타: 웹은 해당층 대신 지상/지하 층수만 그리고 공급면적 칸이 없다 (building_floor 는 그대로)
    **dict.fromkeys(('D03', 'D04', 'E01', 'E02', 'Z00'), frozenset({'room_count', 'room_type', 'floor', 'supply_area_m2'})),
}


# 묶음이 아니거나 중개사마다 호가가 같으면 해당 없는(키를 빼는) 필드
GROUP_FIELDS: tuple[str, ...] = ('realtor_count', 'asking_range')
# 출력 url 칸의 매물·단지 웹 페이지 주소 틀 (`.format(번호)`)
ARTICLE_URL: str = f'{NAVER_WEB_URL}/articles/{{}}'
COMPLEX_URL: str = f'{NAVER_WEB_URL}/complexes/{{}}'
