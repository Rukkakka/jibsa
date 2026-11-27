"""순위(region-ranking·trade-rankings·trending-complexes)의 이름표·탭·기간·패턴·값 종류."""
import re

from jibsa.providers.dabang.api.request.common import DabangRoomBuildingCategory
from jibsa.providers.dabang.api.request.ranking.region import (
    DabangRankingPriceType,
    DabangRegionInfoRankingMetric,
    DabangRegionInfoTopic,
    DabangRoomRankingMetric,
)
from jibsa.providers.dabang.api.request.ranking.trade import DabangTradeBaseOn
from jibsa.providers.dabang.api.request.ranking.trending import DabangWatchBaseOn
from jibsa.providers.dabang.service.common.constants import (
    POPULAR_BUILDING_BY_LABEL,
    VILLA_LABEL,
)

from typing import Literal


RANKING_TRADE_BY_LABEL: dict[str, DabangRankingPriceType] = {'매매': 'SALE', '전세': 'LEASE', '월세': 'MONTHLY_RENT'}

REGION_RANKING_MAX_LIMIT: int = 100
# 동네정보 '매물정보' 랭킹 (room-info 청크, 2026-11-13). 매물 유형에 주택/빌라가 있는 순위는 이 화면뿐이라 -t 빌라 로 고른다.
# 항목은 매물수·거래량·선호도, 동 순위만 있다 (빌라 이름은 service/common/constants.py 의 `VILLA_LABEL`)
ROOM_RANKING_METRIC_BY_LABEL: dict[str, DabangRoomRankingMetric] = {
    '매물수': 'room-count', '거래량': 'trade-volume', '선호도': 'reaction-score',
}
# -t 라벨 → 매물 유형 값과 웹 고르기 이름. 웹 순서(주택/빌라·오피스텔·아파트)대로 둔다. 값은 인기 매물(`popular-listings`)의
# 매물 유형과 같은 buildingCategoryList 라 그 표에서 만들고, 웹 이름이 라벨과 다른 빌라만 따로 적는다
ROOM_RANKING_WEB_NAME_BY_LABEL: dict[str, str] = {VILLA_LABEL: '주택/빌라'}
ROOM_RANKING_BUILDING_BY_LABEL: dict[str, tuple[DabangRoomBuildingCategory, str]] = {
    label: (value, ROOM_RANKING_WEB_NAME_BY_LABEL.get(label, label)) for label, value in POPULAR_BUILDING_BY_LABEL.items()
}
# 웹 동네정보 탭 이름 (어느 랭킹 화면의 순위인지). 부동산 순위는 '시세정보', 매물 유형 순위는 '매물정보' 탭이다
TAB_BY_TOPIC: dict[DabangRegionInfoTopic, str] = {
    'school': '학군', 'population': '인구수', 'amenity': '편의시설', 'mobility': '교통/차량', 'life-safety': '생활안전',
}
REAL_ESTATE_TAB: str = '시세정보'
ROOM_TAB: str = '매물정보'
AGE_YEARS_PATTERN: re.Pattern[str] = re.compile(r'(\d+)\s*년')
# 기준 달 글자: '26년 10월'
MONTH_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d{2})년\s*(\d{1,2})월')
ValueKind = Literal['price', 'count', 'percent', 'change', 'age', 'score', 'population-change', 'count-change']

# --kind 값: 웹 고르기 이름에서 띄어쓰기·'/'·괄호를 뺀 것 (school·facility·traffic·life-safety 청크, 2026-10-25)
ACADEMY_KIND_BY_LABEL: dict[str, str] = {
    '입시': 'ADMISSION_EXAM', '예체능': 'ARTS_SPORTS', '외국어': 'FOREIGN_LANGUAGE', '특성화': 'SPECIALIZED',
    '종합': 'COMPREHENSIVE', '인문사회': 'HUMANITIES_SOCIAL', '코딩': 'PROGRAMMING',
}
FACILITY_KIND_BY_LABEL: dict[DabangRegionInfoRankingMetric, dict[str, str]] = {
    'living': {'편의점': 'CONVENIENCE_STORE', '세탁소': 'LAUNDRY', '헬스장': 'GYM', '공원': 'PARK', '도서관': 'LIBRARY'},
    'medical': {'병원': 'HOSPITAL', '의원': 'CLINIC', '약국': 'PHARMACY', '응급의료센터': 'EMERGENCY'},
    'dining': {'음식점': 'FOOD', '카페': 'CAFE', '주점': 'BAR'},
    'shopping': {'대형마트': 'LARGE_STORE', '백화점': 'DEPARTMENT_STORE', '복합쇼핑몰': 'SHOPPING_MALL'},
    'sports': {
        '수영장': 'SWIMMING_POOL', '테니스장': 'TENNIS_COURT', '암벽장': 'CLIMBING_WALL', '골프장': 'GOLF_COURSE',
        '축구장': 'SOCCER_FIELD', '야구장': 'BASEBALL_FIELD', '당구장': 'BILLIARD_ROOM', '체육관': 'GYM', '기타': 'ETC',
    },
    'transit': {'지하철': 'SUBWAY', '버스': 'BUS_STOP'},
    'parking-lot': {'공영': 'PUBLIC_PARKING_LOT', '민영': 'COMMERCIAL_PARKING_LOT'},
    'charge-station': {'주유소': 'GAS_STATION', '전기차충전소': 'EV_CHARGING_STATION'},
    'maintenance-shop': {'자동차수리점': 'CAR_REPAIR_SHOP', '세차장': 'CAR_WASH', '타이어전문점': 'TIRE_SHOP'},
    'safety-facility': {'CCTV': 'CCTV', '가로등': 'STREET_LAMP'},
    'safety-organization': {
        '경찰서': 'POLICE_STATION', '지구대파출소': 'LOCAL_SUBSTATION', '치안센터': 'SECURITY_CENTER', '소방서': 'FIRE_STATION',
        '119안전센터': 'SAFETY_CENTER',
    },
    'inconvenience': {'공사현장': 'CONSTRUCTION', '소음구역': 'NOISE'},
}

# 항목의 값 종류마다 늘 해당하는 값 칸
VALUE_FIELDS_BY_KIND: dict[ValueKind, frozenset[str]] = {
    'price': frozenset({'value_manwon'}),
    'count': frozenset({'count'}),
    'percent': frozenset({'percent'}),
    'change': frozenset({'change_manwon', 'change_percent', 'prev_price_manwon'}),
    'age': frozenset({'age_years'}),
    'score': frozenset({'score'}),
    'population-change': frozenset({'count', 'prev_count', 'change_count', 'change_percent'}),
    'count-change': frozenset({'count', 'prev_count', 'change_count', 'change_percent'}),
}

# 동·읍·면·리 이름 ('역삼동', '역삼1동', '봉담읍', '남면', '종로1가'). 동 범위를 받지 않는 곳에서 장소 검색 없이 동을 알아본다
DONG_NAME_PATTERN: re.Pattern[str] = re.compile(r'^[가-힣0-9]+(?:[동읍면리]|\d가)$')

TRADE_PERIOD_BY_LABEL: dict[str, DabangTradeBaseOn] = {
    '이번주': 'CURRENT_WEEK',
    '지난주': 'LAST_WEEK',
    '이번달': 'CURRENT_MONTH',
    '지난달': 'LAST_MONTH',
    '올해': 'CURRENT_YEAR',
}
# 막 시작한 기간은 다방이 아직 세지 않아 순위가 빈다 (2026-10-26 월 아침 실측: 이번주 0곳, 지난주·이번달은 있음). 비면 권할 기간
PREVIOUS_TRADE_PERIOD: dict[str, str] = {'이번주': '지난주', '이번달': '지난달', '올해': '지난달'}

WATCH_PERIOD_BY_LABEL: dict[str, DabangWatchBaseOn] = {
    '방금전': 'JUST_BEFORE',
    '어제': 'YESTERDAY',
    '지난주': 'LAST_WEEK',
    '지난달': 'LAST_MONTH',
}

FLUCTUATION_LABELS: dict[str, str] = {'UP': '상승', 'DOWN': '하락', 'STEADY': '유지', 'NEW': '신규'}
