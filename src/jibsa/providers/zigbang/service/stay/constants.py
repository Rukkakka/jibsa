"""직방 service 단기임대 상수: 정렬·건물·옵션 이름표, 환불 정책·일정 이름표, 검색 한도 (search listings stay·listing)."""

from jibsa.core.listing import (
    note,
)
from jibsa.providers.zigbang.api.client import ZIGBANG_WEB_URL
from jibsa.providers.zigbang.api.request.stay.search import (
    ZigbangStayBuildingType,
    ZigbangStayDiscountType,
    ZigbangStayFloorType,
    ZigbangStayOption,
    ZigbangStaySearchSort,
)

from typing import (
    Literal,
)


# 웹 정렬 넷과 같다: 추천순(기본), 낮은 가격순, 최근 등록순, 역 가까운 순. 역 가까운 순은 웹도 지하철역 검색에서만 고를 수
# 있다 (2026-11-15 웹)
StaySort = Literal['recommended', 'price', 'newest', 'distance']

# 단기임대 검색 결과 줄(`ZigbangStayListing`)과 상세의 '임대인의 다른 방' 이 같이 쓰는 것, 검색 조건과 상세가 같이 쓰는 이름표.
# 방 종류 표시 이름은 목록 줄·상세와 검색 조건(`service/stay/search.py` 의 STAY_BUILDING_TYPE_BY_LABEL)이 같이 쓴다
STAY_BUILDING_TYPE_LABELS: dict[str, str] = {
    'OFFICETEL': '오피스텔',
    'APARTMENT': '아파트',
    'VILLA': '빌라',
    'ONEROOM': '원룸',
    'HOUSE': '주택',
    'COMMERCIAL_HOUSE': '상가주택',
    'GOSIWON': '고시원',
    'PENSION': '펜션',
    'SHAREHOUSE': '셰어하우스',
    'GUESTHOUSE': '게스트하우스',
    'RESIDENTIAL_HOTEL': '레지던스',
}
# 옵션 표시 이름은 상세 `options` 와 검색 조건(`service/stay/search.py` 의 STAY_OPTION_BY_LABEL)이 같이 쓴다
STAY_OPTION_LABELS: dict[str, str] = {
    'AIR_CONDITIONER': '에어컨',
    'BED': '침대',
    'GAS_RANGE': '가스레인지',
    'INDUCTION': '인덕션',
    'REFRIGERATOR': '냉장고',
    'SINK': '싱크대',
    'TV': 'TV',
    'WASHING_MACHINE': '세탁기',
    'WIFI': '와이파이',
    'AIR_PURIFIER': '공기청정기',
    'WATER_PURIFIER': '정수기',
    'CLOSET': '옷장',
    'COFFEE_MACHINE': '커피머신',
    'DESK': '책상',
    'DINING_TABLE': '식탁',
    'DISHWASHER': '식기세척기',
    'DRYER': '건조기',
    'ELECTRIC_KETTLE': '전기포트',
    'MICROWAVE': '전자레인지',
    'RICE_COOKER': '전기밥솥',
    'SOFA': '소파',
    'TOASTER': '토스터',
    'VANITY': '화장대',
    'BATHTUB': '욕조',
    'BIDET': '비데',
    'CABLE_TV': '케이블TV',
    'CCTV': 'CCTV',
    'DOOR_LOCK': '도어락',
    'DRYING_RACK': '빨래건조대',
    'MANAGEMENT_OFFICE': '관리사무소',
    'OTT': 'OTT',
    'VACUUM_CLEANER': '청소기',
    'BALCONY': '발코니',
}
STAY_REFUND_POLICY_LABELS: dict[str, str] = {
    'FLEXIBLE': '유연',
    'STANDARD': '표준',
    'STRICT': '엄격',
}
# 위약금 표. 직방 응답은 정책 이름(refundPolicy)만 주고 표는 웹 번들(`RefundPolicySection`)에 고정돼 있어 옮겨 적은 것이다
# (2026-11-17). 직방이 표를 바꾸면 주 1회 감시(`scripts/monitor/api_check.py` 의 `WEEKLY_CHECKS`)가 알린다. 값은 (취소 시점,
# 위약금) 다섯 쌍이고 글자는 웹 표기 그대로다
STAY_REFUND_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    'FLEXIBLE': (
        ('입주 14일전', '없음'),
        ('입주 7일전', '임대료의 15%'),
        ('입주 3일전', '임대료의 30%'),
        ('입주 1일전', '임대료의 40%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STANDARD': (
        ('입주 14일전', '임대료의 10%'),
        ('입주 7일전', '임대료의 30%'),
        ('입주 3일전', '임대료의 40%'),
        ('입주 1일전', '임대료의 50%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STRICT': (
        ('입주 14일전', '임대료의 20%'),
        ('입주 7일전', '임대료의 50%'),
        ('입주 3일전', '임대료의 60%'),
        ('입주 1일전', '임대료의 70%'),
        ('입주 당일 이후', '취소불가'),
    ),
}
STAY_PARKING_METHOD_LABELS: dict[str, str] = {
    'SELF': '자주식',
    'MECHANICAL': '기계식',
}
# 입주·퇴실 방식 (웹 표기. 모르는 코드는 웹도 그대로 쓴다)
STAY_CHECK_METHOD_LABELS: dict[str, str] = {
    'SELF': '비대면',
    'MEET': '임대인 대면',
    'KEYBOX': '키박스',
}
# 달력에서 막힌 날의 종류. 웹이 날짜를 막는 일정 종류(STAY_UNAVAILABLE_SCHEDULES)가 이 표의 키라 한쪽만 고치지 않는다
STAY_SCHEDULE_KIND_LABELS: dict[str, str] = {
    'RESERVED': '예약',
    'BLOCKED': '막힘',
}
# 웹 날짜 고르기 창이 받는 가장 늦은 마지막 날은 입주일 + 83일이다 (번들 `getMaxCheckOut`)
STAY_MAX_CHECK_OUT_DAYS: int = 83
# 웹이 날짜를 막는 일정 종류 (번들 `isUnavailableSchedule`). 이름 표(STAY_SCHEDULE_KIND_LABELS)의 키와 같아 표를 고치면 따라간다
STAY_UNAVAILABLE_SCHEDULES: frozenset[str] = frozenset(STAY_SCHEDULE_KIND_LABELS)
# 상세에 싣는 '임대인의 다른 방' 수. 웹은 모두 받아 가로 카드로 보여 주지만 jibsa 는 앞쪽만 내고 전체 수를 따로 알린다
STAY_HOST_OTHER_LIMIT: int = 10
# 방 종류·옵션의 표시 이름(STAY_BUILDING_TYPE_LABELS·STAY_OPTION_LABELS)은 상세·목록 줄과 같이 써서 `stay.constants` 에 있고, 아래는 그 거꾸로 표다
STAY_BUILDING_TYPE_BY_LABEL: dict[str, ZigbangStayBuildingType] = {
    label: code for code, label in STAY_BUILDING_TYPE_LABELS.items()  # type: ignore[misc]
}
STAY_OPTION_BY_LABEL: dict[str, ZigbangStayOption] = {
    label: code for code, label in STAY_OPTION_LABELS.items()  # type: ignore[misc]
}
# 직방 웹 층 필터의 다섯 선택지 (2026-11-17). 10층 매물은 2-10층에 들고, 11층이상의 코드는 FLOOR_10_PLUS 다
# (FLOOR_11_OVER 는 서버가 400 을 준다)
STAY_FLOOR_TYPE_BY_LABEL: dict[str, ZigbangStayFloorType] = {
    '지하': 'BASEMENT',
    '1층': 'FIRST',
    '2-10층': 'FLOOR_2_10',
    '11층이상': 'FLOOR_10_PLUS',
    '옥탑': 'ROOFTOP',
}
STAY_DISCOUNT_TYPE_BY_LABEL: dict[str, ZigbangStayDiscountType] = {
    '장기계약': 'LONG_TERM',
    '즉시': 'INSTANT',
}
STAY_GEOHASH_PRECISION: int = 5
# 결과가 limit 보다 많을 때 좁히라고 권할 조건. 주 단위 단기임대에는 거래 유형·매물 유형 옵션이 없다
STAY_NARROW: str = '방 종류·가격·날짜 조건'
STAY_BY_IDS_BATCH_SIZE: int = 50
STAY_SORTS: tuple[StaySort, ...] = ('recommended', 'price', 'newest', 'distance')
STAY_SERVER_SORTS: dict[StaySort, ZigbangStaySearchSort] = {
    'recommended': 'RECOMMENDED',
    'price': 'PRICE_ASC',
    'newest': 'NEWEST',
    'distance': 'STATION_DISTANCE_ASC',
}
# limit_notes 의 '… 순으로' 앞말
STAY_SORT_ORDERS: dict[StaySort, str] = {
    'recommended': '직방 추천',
    'price': '주당 임대료·관리비 합계가 낮은',
    'newest': '최근 등록된',
    'distance': '역에서 가까운',
}
# 역 검색(type=subway)은 직방이 역에서 약 1km 안만 준다 (2026-11-15 실측: 강남역 71건, 가장 먼 것 0.979km)
STAY_SUBWAY_RADIUS_KM: float = 1.0
# 날짜를 준 검색의 금액·가격순이 기간 비용이 아니라는 안내. 2026-10-31 에이전트 검증: 강남역 4주 가격순 1위를 주당 32만 × 4 =
# 128만으로 답했지만 청소비·이용료를 더한 실제 결제는 151만 2천이었고, 주당 요금 3위는 기간 비용으로 4위였다. 기간 비용은
# 웹이 로그인했을 때만 계산해 보여 주어(2026-11-15) jibsa 는 내지 않는다
STAY_WEEKLY_PRICE_NOTE: str = note(
    '참고',
    '목록 금액과 가격순은 주당 임대료+관리비 기준이라 청소비·직방 이용료·장기 할인이 빠져 있습니다. 그 기간에 실제로 내는 돈은 '
    '직방에 로그인해야 계산해 보여 줘서 jibsa 는 주지 않습니다. 청소비·보증금·할인 조건은 listing stay-… 상세에서 보세요',
)
# 단기임대 검색 API 의 기간 오류. 로컬에서 7~84일을 먼저 막지만 직방이 제한을 바꿔도 소스 장애로 보이지 않게 한다
STAY_PERIOD_ERRORS: frozenset[str] = frozenset({'MIN_DURATION_VIOLATION', 'MAX_DURATION_VIOLATION'})
# 단기임대 매물 웹 페이지 주소 틀 (`.format(매물 번호)`). 로그인 없이 열린다
STAY_URL: str = f'{ZIGBANG_WEB_URL}/stay/item/{{}}'
