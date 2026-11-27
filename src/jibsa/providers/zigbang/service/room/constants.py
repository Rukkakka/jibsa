"""직방 service 방 매물 상수: 매물 종류·구조 선택지, 관리비·주차·이동 시간 이름표, 목록 검색 한도 (search listings room·listing)."""

from typing import (
    Literal,
)


ZigbangPropertyType = Literal['원룸', '오피스텔', '빌라']

# 기존 상세(/v3/items)의 주차 문장과 가능 여부
LEGACY_PARKING_AVAILABLE: dict[str, bool] = {'주차 가능': True, '주차 불가능': False, '주차 불가': False}
# 새 주거 상세가 아파트 매물에 주는 404 의 본문 code. 없는 매물의 404 는 code 가 없다 (2026-11-15 실측)
APT_DETAIL_NOT_SUPPORTED_CODE: str = 'ITEM_QUERY_DETAIL_SERVICE_TYPE_NOT_SUPPORTED'
NORMAL_MANAGE_COST_LABEL: str = '일반(공용) 관리비'
ETC_MANAGE_COST_LABEL: str = '기타 관리비'
FIXED_MANAGE_COST_TYPE: str = 'FixedManageCost'
UNKNOWN_MANAGE_COST_TYPE: str = 'UnknownManageCost'
# 관리비 부과 기준(`manageCostCriteria`)·부과 방식(`basis`) 코드 → 웹 문구 (2026-11-19 번들 `_app` 의 코드표 그대로). 코드 '04'(기준)·'07'(방식)은
# 중개사가 직접 쓴 글자(`manageCostCriteriaEtcDescription`·`basisEtcDescription`)를 웹이 그대로 보여 준다. 표에 없는 코드는 모름(null)으로 둔다
MANAGE_COST_PERIOD_LABELS: dict[str, str] = {
    '01': '직전 월 관리비 기준',
    '02': '최근 3개월 관리비 평균',
    '03': '최근 1년 관리비 평균',
}
MANAGE_COST_PERIOD_ETC_CODE: str = '04'
MANAGE_COST_METHOD_LABELS: dict[str, str] = {
    '01': '관리규약에 따라 부과해요.',
    '02': '공용관리비는 면적/세대별로 부과하고, 사용료는 사용량에 따라 부과해요.',
    '03': '전체 사용량을 세대수로 나누어 부과해요.',
    '04': '세대별 사용량(별도 계량기)에 따라 부과해요.',
    '05': '중개 의뢰인이 세부내역을 고지하지 않아 전세입자 등을 통해 추정된 관리비를 안내해요.',
    '06': '관리비 월 10만원 미만이에요.',
}
MANAGE_COST_METHOD_ETC_CODE: str = '07'
# 정액 관리비가 항목별 내역을 알리지 않았을 때 웹이 보여 주는 설명의 방식 코드 (`renderManageCostData` 가 `I.gW["05"]` 를 쓴다)
MANAGE_COST_UNINFORMED_CODE: str = '05'
# 주변 시설의 이동 수단. 웹(`mapTransportType`)은 'car' 만 차로 보고 'foot' 과 모르는 값은 도보로 그린다
CAR_TRANSPORT: str = 'car'
WALKING_LABEL: str = '도보'
CAR_LABEL: str = '차'
# 건물 실거래의 거래 유형 (직방 `sales_type`). 그 밖의 값이면 거래 유형을 모름(null)으로 둔다
BUILDING_TRADE_TYPES: tuple[str, ...] = ('매매', '전세', '월세')
PROPERTY_TYPES: tuple[ZigbangPropertyType, ...] = ('원룸', '오피스텔', '빌라')
GEOHASH_PRECISION: int = 5
# 방 하나짜리 구조. 원룸 유형은 이 구조만 서버에 요청한다 (직방 원룸 목록에는 투룸 오피스텔도 섞여 온다)
# 방 하나짜리 아파트는 아파트 목록에만 있고 아파트 API 에는 방 구조 조건이 없다. 공급면적 50㎡ 이하로 찾으면
# 대부분 방 1개다 (2026-10-10 실측: 역삼동 32건 중 단지별 6건 상세에서 5건이 방 1개)
ONE_ROOM_STRUCTURES: tuple[str, ...] = ('오픈형원룸', '분리형원룸', '복층형원룸')
# --details 로 상세를 붙이는 매물 수. 한 건에 요청 1회라 목록이 길면 오래 걸린다
DETAILS_MAX: int = 30
