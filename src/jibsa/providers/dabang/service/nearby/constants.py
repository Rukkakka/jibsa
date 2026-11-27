"""주변(nearby)·역 둘레 평균 매물가(station-prices)의 이름표·종류 코드표·한도."""
from jibsa.providers.dabang.api.models.request.nearby.places import DabangNearTarget
from jibsa.providers.dabang.service.common.constants import (
    COMPLEX_URL,
    LISTING_URL,
    POPULAR_BUILDING_BY_LABEL,
    SALE_URL,
)

from typing import Literal


# 종류마다 내는 가까운 시설 수. 웹은 받은 시설 전부(편의 종류는 15곳)를 지도에 찍는다
NEAR_PLACES_PER_TYPE: int = 3

# 가까운 시설 종류 코드 → 이름. 웹 주변 지도의 이름표 그대로다 (distance-km-m 청크, 2026-11-13: BS 버스, PO3 관공서,
# POLICE 치안 …). 지하철역(SW8)은 transit/near 의 역 목록으로, CCTV 는 이름이 없어 쓰지 않는다. 다방은 대상마다 다른 종류를
# 준다 (2026-10-26 실측: 매물은 BS·SW8·CS2·CE7·BK9·PO3, 단지는 BS·SW8·MT1·CS2·BK9·PM9, 둘 다 POLICE). 분양은 단지와 같은
# 종류를 준다 (2026-11-13 실측: 호반써밋 풍무Ⅱ BS·SW8·MT1·CS2·BK9·PM9·POLICE·CCTV)
NEAR_LABELS: dict[str, str] = {
    'BS': '버스',
    'MT1': '마트',
    'CS2': '편의점',
    'CE7': '카페',
    'BK9': '은행',
    'PM9': '약국',
    'PO3': '관공서',
    'POLICE': '치안',
}
SCHOOL_LABELS: dict[str, str] = {'NS': '어린이집', 'KS': '유치원', 'ES': '초등학교', 'MS': '중학교', 'HS': '고등학교'}
# 대상 → 결과의 target 이름과 없는 ID 안내에 쓰는 이름
TARGET_LABELS: dict[DabangNearTarget, str] = {'room': '매물', 'complex': '단지', 'sale': '분양'}

# --with 로 더 받는 생활 정보와 받는 대상. 반려동물 장소(웹 '펫세권')는 웹이 단지 화면에서만 부르고 매물·분양 ID 로는 빈
# 목록이다. 카셰어링 존(웹 'Car세권')은 매물·단지만 되고 분양은 403 이다 (dong-info 청크 2026-11-13, 2026-11-14 실측)
NearbyExtra = Literal['반려동물', '카셰어링']
NEARBY_EXTRAS: tuple[NearbyExtra, ...] = ('반려동물', '카셰어링')
EXTRA_TARGETS: dict[NearbyExtra, tuple[DabangNearTarget, ...]] = {'반려동물': ('complex',), '카셰어링': ('room', 'complex')}
# 카셰어링 업체 코드 → 웹 이름표
CAR_SHARE_LABELS: dict[str, str] = {'SOCAR': '쏘카존', 'GREENCAR': '그린존'}

# 인기 매물 건물 유형 표(`POPULAR_BUILDING_BY_LABEL`)의 반대 방향 (건물 유형 코드 → 이름)
BUILDING_LABEL_BY_CATEGORY: dict[str, str] = {category: label for label, category in POPULAR_BUILDING_BY_LABEL.items()}

ROOM_LABELS: dict[str, str] = {'ONE_ROOM': '원룸', 'TWO_ROOM': '투룸'}

# 역 둘레 평균 매물가를 받으려고 역을 덮는 지도 범위 (km). 확대 수준 16 이면 범위 안 역 표시에 평균이 붙는다
STATION_BOX_KM: float = 0.3
# 대상 → 매물·단지·분양 페이지 주소 틀
URL_BY_TARGET: dict[DabangNearTarget, str] = {'room': LISTING_URL, 'complex': COMPLEX_URL, 'sale': SALE_URL}
