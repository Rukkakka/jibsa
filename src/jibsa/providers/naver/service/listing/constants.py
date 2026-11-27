"""매물 상세의 코드표(시설·난방·입주·건물 유형 ...)·세금 표와 단지 매물 목록의 쪽 크기."""

import re

from jibsa.providers.naver.api.request.common import NaverRealEstateType
from jibsa.providers.naver.service.common.constants import (
    ENTRANCE_CODE_BY_NAME,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
)

from typing import get_args


# 서버가 받는 매물 유형 코드 전부 (`NaverRealEstateType`). 매물 상세가 응답의 유형 코드를 요청에 다시 넣기 전에 확인한다
KNOWN_REAL_ESTATE_TYPES: frozenset[str] = frozenset(get_args(NaverRealEstateType))


# 상세 detailInfo.shape 도 같은 코드다. 방 1개 매물의 room_type 이름으로 쓴다
ONE_ROOM_TYPE_BY_SHAPE: dict[str, str] = {code: f'{name}원룸' for name, code in ONE_ROOM_SHAPE_CODE_BY_NAME.items()}


DIRECTION_BY_CODE: dict[str, str] = {
    'EE': '동향',
    'WW': '서향',
    'SS': '남향',
    'NN': '북향',
    'ES': '남동향',
    'SE': '남동향',
    'WS': '남서향',
    'SW': '남서향',
    'EN': '북동향',
    'NE': '북동향',
    'WN': '북서향',
    'NW': '북서향',
}


# 입주 시기 코드 (네이버 웹 번들의 ARTICLE_MOVING_IN_TYPE 과 대조, 2026-11-16): MV001 즉시입주, MV002 이내입주,
# MV003 이후입주, MV004 지정날짜. EARLY / MID / LATE 는 movingInDate 의 달 초순·중순·하순이다.
MOVING_IN_LABELS: dict[str, str] = {
    'MV001': '즉시입주',
}


# 웹은 '2026년 12월 01일 이내입주' 처럼 날짜 뒤에 이내·이후를 붙여 보여 준다. 날짜만 내면 둘이 구분되지 않는다
MOVING_IN_BOUND_LABELS: dict[str, str] = {
    'MV002': '이내',
    'MV003': '이후',
}


MOVING_IN_PERIOD_LABELS: dict[str, str] = {
    'EARLY': '초순',
    'MID': '중순',
    'LATE': '하순',
}


# 기간 코드(초순·중순·하순)는 달만 있으면 돼 연월만 온 날짜(2026-11·202611·2026.11)도 받는다
YEAR_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^(\d{4})[-./]?(\d{2})$')


# 관리비 확인 불가 사유 코드 중 '없음' (웹 번들의 UNABLE_CHECK_DETAIL_CODE_TYPE, 2026-11-16)
MANAGE_COST_NONE_REASON: str = '99'


# 관리비 항목 코드 (사이트 관리비 상세보기 화면과 대조, 2026-10-10). 이름은 당근·직방 manage_cost_includes 와 맞춘다
MANAGE_COST_ITEM_LABELS: dict[str, str] = {
    '01': '공용',
    '11': '전기',
    '12': '수도',
    '13': '가스',
    '14': '난방',
    '15': '인터넷',
    '16': 'TV',
    '99': '기타',
}


# 시설 코드 이름. 2026-11-17 네이버 웹 번들의 시설 이름 표와 똑같이 화면 글자 그대로 쓴다. 그 뒤 네이버가 더한 코드는 이 표에
# 없어 '알 수 없는 시설 (코드)' 로 낸다 (2026-10-24: 사설경비·에어컨·가스오븐·소파가 빠져 PRIVATE_SECURITY 같은 영어 코드가 options 에 그대로 나갔다).
# ELEVATOR 는 options 가 아니라 has_elevator 로 낸다
# 리뷰 오탐 (2026-11-17): 직방·당근의 options 글자(인덕션 등)와 다르다. options 는 소스끼리 글자를 맞추는 약속이 없고
# 네이버는 화면 글자를 따른다
# 리뷰 오탐 (2026-11-17): 표에서 지운 DRESSING_TABLE·DRYER·GAS_RANGE·OVEN·ROOF_TOP·CENTRAL·DOOR_LOCK 은 첫 커밋의 추정 이름이고 웹 시설 표(ARTICLE_FACILITY_*)에 없다
FACILITY_LABELS: dict[str, str] = {
    # 생활시설
    'AIRCON': '에어컨',
    'BATHTUB': '욕조',
    'BED': '침대',
    'BIDET': '비데',
    'BUILT_IN_CLOSET': '붙박이장',
    'CLOSET': '옷장',
    'CLOTHES_DRYER': '건조기',
    'DESK': '책상',
    'DINING_TABLE': '식탁',
    'DISH_WASHER': '식기세척기',
    'GAS_OVEN': '가스오븐',
    'GAS_STOVE': '가스레인지',
    'INDUCTION_RANGE': '인덕션레인지',
    'MICROWAVE': '전자레인지',
    'REFRIGERATOR': '냉장고',
    'SHOE_RACK': '신발장',
    'SOFA': '소파',
    'SHOWER_BOOTH': '샤워부스',
    'SINK': '싱크대',
    'TV': 'TV',
    'WASHING_MACHINE': '세탁기',
    # 보안시설
    'GUARD': '경비원',
    'VIDEO_PHONE': '비디오폰',
    'INTER_PHONE': '인터폰',
    'PRIVATE_SECURITY': '사설경비',
    'CARD_KEY': '카드키',
    'CCTV': 'CCTV',
    'ENTRANCE_SECURITY': '현관보안',
    'SECURITY_WINDOW': '방범창',
    # 기타시설
    'FIRE_ALARM': '화재경보기',
    'VERANDA': '베란다',
    'TERRACE': '테라스',
    'YARD': '마당',
    'DELIVERY_BOX': '무인택배함',
    # 냉방시설
    'WALL': '벽걸이에어컨',
    'STAND': '스탠드에어컨',
    'CEILING': '천장에어컨',
}


# 난방 방식·난방 연료·현관 구조 코드 (네이버 웹 번들 대조, 2026-11-17). 웹은 난방 한 칸에 '개별난방 / 도시가스' 로 이어 보여 주지만
# jibsa 는 방식(heating)과 연료(heating_fuel)를 따로 낸다
HEATING_LABELS: dict[str, str] = {
    'HT001': '개별난방',
    'HT002': '중앙난방',
    'HT003': '개별냉난방',
    'HT004': '중앙냉난방',
    'HT005': '지역난방',
    'HT006': '지역냉난방',
}


HEATING_FUEL_LABELS: dict[str, str] = {
    'HF001': '도시가스',
    'HF002': '열병합',
    'HF003': '기름',
    'HF004': '전기',
    'HF005': '심야전기',
    'HF006': '태양열',
    'HF007': 'LPG',
    'HF008': '지열',
}


# 네이버 표의 이름이 '미노출' 인 난방 코드. 중개사가 알리지 않은 것이라 값이 없는 것과 같아 모름(null)으로 낸다
UNDISCLOSED_HEATING_CODES: frozenset[str] = frozenset({'HT000', 'HF000'})


ENTRANCE_LABELS: dict[str, str] = {code: name for name, code in ENTRANCE_CODE_BY_NAME.items()}


# 웹이 난방·현관·주차를 매물이 아니라 단지 값으로 채우는 단지 유형: 아파트 A01·오피스텔 A02·재건축 A04·아파트분양권 B01·
# 오피스텔분양권 B02 (웹 isComplexType, 2026-11-17 번들 청크 0l4pkwg0qhg2t 의 ArticleComplexInfo). 단지형 빌라(A05~A07,
# `VILLA_COMPLEX_CODES`)는 다른 화면(ArticleVillaBuildingInfo)이라 규칙이 다르다 (`facility_values`)
COMPLEX_INFO_TYPES: frozenset[str] = frozenset({'A01', 'A02', 'A04', 'B01', 'B02'})


# 웹이 건축물 정보 칸을 그리는 건축물대장 유형 15개 (웹 isBuildingRegistrationType, 2026-11-18 번들 청크 0l4pkwg0qhg2t 의
# ArticleBuildingInfo, 번들 REAL_ESTATE_TYPE 대조). 매물에 주차 대수가 없을 때 건축물대장 대수로 채우는 유형이다 (`_building_parking`)
BUILDING_REGISTRATION_TYPES: frozenset[str] = frozenset({
    'C01', 'C02', 'C03', 'C04', 'C06',
    'D01', 'D02', 'D03', 'D04', 'D05',
    'E01', 'E02', 'E04', 'F01', 'Z00',
})


# 건물 세부 유형 코드 (articleDetailInfo.buildingType). 네이버 웹 번들의 ARTICLE_BUILDING_TYPE_MAP 과 같다 (2026-11-17 대조)
BUILDING_TYPE_LABELS: dict[str, str] = {
    'C0101': '일반원룸',
    'C0102': '빌라다세대',
    'C0103': '다가구',
    'C0104': '오피스텔',
    'C0105': '원룸형 아파트',
    'C0106': '기타',
    'C0107': '도시형생활주택',
    'C0108': '일반원룸',
    'C0109': '빌라다세대',
    'C0110': '다가구',
    'C0111': '오피스텔',
    'C0112': '도시형생활주택',
    'C0113': '기타',
    'C0201': '다세대',
    'C0202': '연립',
    'C0203': '빌라',
    'C0204': '기타',
    'C0301': '단독',
    'C0302': '다가구',
    'C0401': '전원주택',
    'C0402': '농가',
    'C0403': '별장',
    'C0404': '펜션',
    'C0601': '한옥주택',
    'C0602': '한옥주택',
    'D0101': '대형사무실',
    'D0102': '중소형사무실',
    'D0103': '공동사무실',
    'D0104': '오피스텔',
    'D0105': '일반사무실',
    'D0201': '단지내상가',
    'D0202': '지하상가',
    'D0203': '일반상가',
    'D0204': '복합상가',
    'D0301': '빌딩',
    'D0302': '상가건물',
    'D0303': '상가주택',
    'D0304': '숙박시설',
    'D0305': '상업시설',
    'D0306': '레저/스포츠/위락',
    'D0307': '특수시설',
    'D0308': '기타',
    'E0101': '여관/모텔',
    'E0102': '호텔',
    'E0103': '콘도',
    'E0104': '펜션',
    'E0105': '기타',
    'E0106': '모텔',
    'E0107': '여관/모텔/호텔',
    'E0201': '공장',
    'E0202': '창고',
    'E0203': '지식산업센터',
    'E0204': '기타',
    'E0301': '전',
    'E0302': '답',
    'E0303': '과수원',
    'E0304': '목장용지',
    'E0305': '임야',
    'E0306': '광천지',
    'E0307': '염전',
    'E0308': '대',
    'E0309': '공장용지',
    'E0310': '학교용지',
    'E0311': '주차장',
    'E0312': '주유소용지',
    'E0313': '창고용지',
    'E0314': '도로',
    'E0315': '철도용지',
    'E0316': '제방',
    'E0317': '하천',
    'E0318': '구거',
    'E0319': '유지',
    'E0320': '양어장',
    'E0321': '수도용지',
    'E0322': '공원',
    'E0323': '체육용지',
    'E0324': '유원지',
    'E0325': '종교용지',
    'E0326': '사적지',
    'E0327': '묘지',
    'E0328': '잡종지',
    'E0329': '기타',
    'F0101': '단독',
    'F0102': '다가구',
    'F0103': '다세대',
    'F0104': '연립빌라',
    'F0105': '기타',
    'F0106': '단독/다가구',
    'F0107': '다세대/연립',
}


# 웹 제목은 건물 이름 뒤에 건물 하위 이름(nonComplexBuildingSubName)을 붙이는 매물이 정해져 있다 (getArticleNameParts, 2026-11-17
# 번들 대조). 매물 유형이 C01·D05 이거나, 매물 유형과 건물 세부 유형이 이 표의 짝일 때뿐이고 그 밖에는 건물 이름만 쓴다
BUILDING_SUB_NAME_REAL_ESTATE_TYPES: frozenset[str] = frozenset({'C01', 'D05'})


BUILDING_SUB_NAME_BUILDING_TYPES: dict[str, frozenset[str]] = {
    'C02': frozenset({'C0202', 'C0203'}),
    'C03': frozenset({'C0302'}),
}


# 웹 매물 화면의 위치 칸(ArticleBuildingInfo, 번들 청크 0l4pkwg0qhg2t)은 매물 유형이 이 표에 있으면 지번을 articleDetailInfo.isJibunAddressExposed
# 가 true 일 때만 보인다 (없으면 숨김). 표에 없는 유형은 건물 세부 유형이 단독(C0301)일 때만 그 값을 따르고 나머지는 늘 보인다
JIBUN_EXPOSURE_REAL_ESTATE_TYPES: frozenset[str] = frozenset({
    'D01', 'D02', 'D03', 'D04', 'E01', 'E02', 'E03', 'E04', 'F01', 'Z00', 'C04', 'C06',
})


JIBUN_EXPOSURE_BUILDING_TYPE: str = 'C0301'


# 매매 매물 상세에만 붙이는 세금 필드 (요청을 아끼려고 전월세는 세금을 조회하지 않는다. 원룸·고시원과 일반분양권이 아닌 분양권은
# 웹에 세금 칸이 없어 매매여도 조회하지 않는다. 분양권은 분양 상태를 모르면 칸이 있는지 몰라 요청하지 않고 모름(null)으로 둔다.
# 중개보수는 직거래가 아님이 확인된 매물만 모든 거래 유형에서 조회한다)
SALE_TAX_FIELDS: frozenset[str] = frozenset({
    'acquisition_tax_manwon', 'property_tax_manwon', 'comprehensive_real_estate_tax_manwon',
})


# 세금 칸이 없는 매물 유형 (원룸 C01·고시원 G01). 웹 getArticleTaxExposeInfo (2026-11-17 번들 대조, 청크 0n-xsnd22pdxz) 는
# 이 둘에 세금 칸을 그리지 않는다
NO_TAX_TYPES: frozenset[str] = frozenset({'C01', 'G01'})


# 분양권(B01)·오피스텔분양권(B02). 웹 getArticleTaxExposeInfo 는 이 둘이면 매매이면서 분양권 상태(preSaleStatusType)가
# 일반분양권('10')일 때만 세금 칸을 그린다 (2026-11-17 번들 대조, 둔촌동 분양권 2661144592 '10'·2659804873 '20')
PRE_SALE_TYPES: frozenset[str] = frozenset({'B01', 'B02'})


GENERAL_PRE_SALE_STATUS: str = '10'


# 세 세금을 모두 그리는 매매 유형 (아파트 A01·재건축 A04·빌라 단지 A05~A07). 그 밖의 유형은 취득세만 그린다. 일반분양권이
# 아닌 분양권 매매는 세금 칸이 없어, 분양 상태를 모르는 분양권 매매는 칸이 있는지 몰라 요청하지 않는다 (`draws_sale_taxes`)
# 리뷰 오탐 (2026-11-17): A05~A07 은 common.VILLA_COMPLEX_CODES 와 코드가 같지만 규칙이 다르다 (그쪽은 학교 조회 itemType=villa 를 물을 단지형 빌라, 이쪽은 웹 getArticleTaxExposeInfo 가 세 세금을 모두 그리는 유형). 합치면 한쪽 변경이 다른 쪽에 번진다
ALL_TAX_TYPES: frozenset[str] = frozenset({'A01', 'A04', 'A05', 'A06', 'A07'})


COMPLEX_PAGE_SIZE: int = 30


# 단지 매물 목록 요청 상한 (빌라 단지로 다시 묻는 1회 포함). limit 건까지만 받고, 받은 뒤 중복·모르는 거래 유형으로
# 빠져도 그만큼 다시 받지 않는다
MAX_COMPLEX_ARTICLE_PAGE_REQUESTS: int = 5
