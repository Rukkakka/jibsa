"""동네정보 기능(neighborhood)의 상수: 동네정보 주제·순위 종류 이름표, 핫플레이스 가이드, 인기 매물 이름표."""
from jibsa.providers.dabang.api.models.request.neighborhood.hot_places import (
    DabangHotPlaceType,
)
from jibsa.providers.dabang.api.models.request.neighborhood.info import (
    DabangAmenitySummaryType,
    DabangLifeSafetySummaryType,
    DabangMobilitySummaryType,
    DabangRegionInfoCountTopic,
    DabangSchoolSummaryType,
)
from jibsa.providers.dabang.api.models.request.neighborhood.popular import (
    DabangPopularPriceType,
)
from jibsa.providers.dabang.service.common.constants import (
    VILLA_LABEL,
    ListingKind,
)

from typing import Literal


NeighborhoodTopic = Literal['매물', '거래', '시세', '인구', '학교', '편의', '교통', '안전']
NEIGHBORHOOD_TOPICS: tuple[NeighborhoodTopic, ...] = ('매물', '거래', '시세', '인구', '학교', '편의', '교통', '안전')
COUNT_TOPIC_BY_LABEL: dict[str, DabangRegionInfoCountTopic] = {
    '학교': 'school',
    '편의': 'amenity',
    '교통': 'mobility',
    '안전': 'life-safety',
}

# --ranks: 학교·편의·교통·안전 탭의 요약 칸 종류 (웹 이름표, 요청 값). 웹 요약 칸의 고르기 순서 그대로다 (school·facility·
# traffic·life-safety 청크 tabList, 2026-11-13). 종류마다 요청 1회. 요청 값은 주제마다 그 탭의 Literal 로 검사한다
SCHOOL_RANK_TYPE_BY_LABEL: dict[str, DabangSchoolSummaryType] = {
    '어린이집': 'NURSERY_SCHOOL', '유치원': 'KINDER_SCHOOL', '초등학교': 'ELEMENTARY_SCHOOL', '중학교': 'MIDDLE_SCHOOL',
    '고등학교': 'HIGH_SCHOOL',
}
AMENITY_RANK_TYPE_BY_LABEL: dict[str, DabangAmenitySummaryType] = {
    '생활 편의시설': 'LIVING', '의료시설': 'MEDICAL', '외식시설': 'DINING', '대형 쇼핑시설': 'SHOPPING', '체육시설': 'SPORTS',
}
MOBILITY_RANK_TYPE_BY_LABEL: dict[str, DabangMobilitySummaryType] = {
    '교통시설': 'TRANSIT', '주차시설': 'PARKING_LOT', '주유시설': 'CHARGE_STATION', '차량관리시설': 'MAINTENANCE_SHOP',
}
LIFE_SAFETY_RANK_TYPE_BY_LABEL: dict[str, DabangLifeSafetySummaryType] = {
    '안전시설': 'SAFETY_FACILITY', '안전기관': 'SAFETY_ORGANIZATION', '불편요소': 'INCONVENIENCE',
}
RANK_TYPES_BY_TOPIC: dict[str, dict[str, str]] = {
    '학교': dict(SCHOOL_RANK_TYPE_BY_LABEL),
    '편의': dict(AMENITY_RANK_TYPE_BY_LABEL),
    '교통': dict(MOBILITY_RANK_TYPE_BY_LABEL),
    '안전': dict(LIFE_SAFETY_RANK_TYPE_BY_LABEL),
}
RANK_TOPICS: tuple[str, ...] = tuple(RANK_TYPES_BY_TOPIC)

# 출력 키 (주제 라벨 → 결과 필드)
FIELD_BY_TOPIC: dict[str, str] = {
    '매물': 'listings',
    '거래': 'trades',
    '시세': 'prices',
    '인구': 'population',
    '학교': 'schools',
    '편의': 'amenities',
    '교통': 'transport',
    '안전': 'safety',
}

# 핫플레이스 가이드 고르기 (웹 이름표 → 요청 값, hot-place 청크 2026-11-13)와 줄의 가이드 이름표
HOT_PLACE_TYPE_BY_LABEL: dict[str, DabangHotPlaceType] = {'전체': 'ALL', '미쉐린': 'MICHELIN_GUIDE', '블루리본': 'BLUE_RIBBON'}
HOT_PLACE_GUIDE_LABELS: dict[str, str] = {value: label for label, value in HOT_PLACE_TYPE_BY_LABEL.items() if value != 'ALL'}

POPULAR_PRICE_BY_TRADE: dict[str, DabangPopularPriceType] = {'월세': 'MONTHLY_RENT', '전세': 'LEASE', '매매': 'SALE'}
POPULAR_KIND_BY_BUILDING: dict[str, ListingKind] = {VILLA_LABEL: 'villa', '오피스텔': 'officetel', '아파트': 'apt'}
# 유형을 섞어 받으면 칸에 건물 유형이 없다. 오피스텔·아파트는 그 이름으로, 주택·빌라는 방 개수('원룸'·'투룸')로 표시한다
# (2026-10-25 실측: 역삼동·대치동 유형별 50건씩)
POPULAR_KIND_BY_ROOM_TYPE: dict[str, ListingKind] = {'오피스텔': 'officetel', '아파트': 'apt'}
POPULAR_MAX_LIMIT: int = 100
