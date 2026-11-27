"""직방 service 상가 상수: 거래·업종 이름표, 층 형식, 검색 한도와 서버 좁히기 조건 (search listings store·listing)."""

import re

from jibsa.core.listing import (
    TradeType,
)
from jibsa.providers.zigbang.api.client import ZIGBANG_WEB_URL
from jibsa.providers.zigbang.api.request.store import (
    ZigbangStoreSalesType,
)


SCAN_FACTOR: int = 5
MIN_SCAN_PINS: int = 60
STORE_TRADE_TYPES: tuple[ZigbangStoreSalesType, ...] = ('임대', '매매')
# 결과가 limit 보다 많을 때 좁히라고 권할 조건. 상가에는 매물 유형 옵션이 없다
STORE_NARROW: str = '거래 유형·업종·가격 조건'
# 그중 서버가 거르는 조건. 가격 조건은 받은 뒤 거르므로 후보 조회 상한에 걸렸을 때는 이것만 권한다
STORE_SERVER_NARROW: str = '거래 유형·업종'
# 이 지역 비어있는 상가(공실) 묶음이 있을 때의 위 두 문구. 공실 줄은 업종과 상관없어 업종 조건으로 줄지 않으니 업종은 권하지 않는다
STORE_VACANT_NARROW: str = '거래 유형·가격 조건'
STORE_VACANT_SERVER_NARROW: str = '거래 유형'
# 웹 상가 업종 필터의 대분류와 업종. 대분류 이름을 주면 그 안의 업종 전체다 (웹의 '전체').
STORE_BUSINESSES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    '휴게음식점': ('베이커리', '카페/커피', '패스트푸드/피자', '분식', '치킨/닭요리'),
    '일반음식/주류점': ('한식/고기집', '일식/해산물', '중식', '퓨전/쌀국수', '양식/레스토랑', '기타주점'),
    '스포츠/마사지/오락': ('골프/헬스', '요가/마사지', '노래방/PC방/당구장'),
    '판매업': (
        '화장품', '가구/가전', '주방/인테리어', '건강/미용식품', '애견/애완/동물', '액세서리',
        '의류/멀티샵', '편의점/슈퍼', '정육/수산/반찬', '약국', '문구/펜시', '기타소매',
    ),
    '기타': ('숙박/펜션', '학원/학업관련', '미용/네일/피부관리', '병원', '부동산중개소', '기타'),
}
# 업종 '기타' 는 대분류 '기타' 와 이름이 같아 대분류로 읽는다 (그 안의 업종 전체).
STORE_BUSINESS_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys([*STORE_BUSINESSES_BY_CATEGORY, *(b for bs in STORE_BUSINESSES_BY_CATEGORY.values() for b in bs)])
)
STORE_LIST_BATCH_SIZE: int = 50
STORE_VACANT_SECTION: str = '이 지역 비어있는 상가'
STORE_FLOOR_PATTERN: re.Pattern[str] = re.compile(r'^(지하)?\s*(\d+)\s*층$')
# 상가 주차 문구 앞의 가능 여부 ('가능 - 자주식 6대')
STORE_PARKING_AVAILABLE: dict[str, bool] = {'가능': True, '불가': False, '불가능': False}
# 웹 상가 카드·상세가 거래 이름으로 쓰는 응답의 `sales_title` 값
STORE_TRADE_BY_TITLE: dict[str, TradeType] = {'매매': '매매', '전세': '전세', '월세': '월세'}
# 상가 응답에 방·욕실·방향·입주·옵션 정보가 아예 없어(2026-10-10 실측: 상세 원본 키 35개, 상세 12건·목록 10건 모두 비어 있음)
# 모름이 아니라 해당 없음으로 키를 뺀다
STORE_NOT_APPLICABLE_FIELDS: frozenset[str] = frozenset({'room_type'})
STORE_NOT_APPLICABLE_DETAIL_FIELDS: frozenset[str] = STORE_NOT_APPLICABLE_FIELDS | frozenset({
    'room_count', 'bathroom_count', 'direction', 'move_in', 'options', 'manage_cost_includes',
})
# 업종 '사무실' 에는 권리금이 없다. 웹 상세는 이 업종이면 권리금 줄을 숨기고, 직방도 값을 주지 않는다 (2026-11-17 번들
# `renderItemInfoData`, 상가 340건 중 권리금이 없는 199건이 모두 사무실). 그래서 직방이 값을 주지 않은 사무실은 모름이
# 아니라 해당 없음으로 `key_money_manwon` 키를 뺀다. 값을 줬으면(0 포함) 그대로 낸다. 권리금 조건을 걸면 이런 사무실은
# 빼고(해당 없음을 0 으로 치지 않는다) `search_store_listings` 가 [제외] 로 알린다
STORE_OFFICE_BUSINESS: str = '사무실'
# 상가 매물 웹 페이지 주소 틀 (`.format(매물 번호)`)
STORE_URL: str = f'{ZIGBANG_WEB_URL}/home/store/items/{{}}'
