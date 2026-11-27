"""매물 기능(listing)의 상수: 매물 상세의 관리비 항목·옵션 이름표와 매물 ID·번호 패턴."""
import re

from jibsa.core.listing import TradeType
from jibsa.providers.dabang.api.request.common import LISTING_ID_PATTERN_TEXT


# 상세 화면이 '비공개 처리된 매물' 로 닫는 상태 (room 청크 `[0,3,4].includes(t.room.status)`, 2026-10-25)
HIDDEN_STATUSES: frozenset[int] = frozenset({0, 3, 4})
TRADE_BY_SELLING_CODE: dict[int, TradeType] = {0: '월세', 1: '전세', 2: '매매'}
# 관리비 포함 항목 코드 → 이름 (listing-request 청크의 표, 2026-10-25)
MANAGE_ITEM_LABELS: dict[str, str] = {
    'PUBLIC_USE_RATES': '공용 관리비',
    'ELECTRIC_RATES': '전기',
    'WATER_RATES': '수도',
    'INTERNET_RATES': '인터넷',
    'HEATING_RATES': '난방',
    'GAS_RATES': '가스',
    'TV_RATES': 'TV',
    'ETC_USE_RATES': '기타 관리비',
}
# 정액 관리비 세부 항목 코드 → 이름 (listing-request 청크의 표 F01 공용·F11 전기 … F99 기타, 2026-10-26). 이름은 위 표와 맞춘다
FIXED_FEE_ITEM_LABELS: dict[str, str] = {
    'F01': '공용 관리비',
    'F11': '전기',
    'F12': '수도',
    'F13': '가스',
    'F14': '난방',
    'F15': '인터넷',
    'F16': 'TV',
    'F99': '기타 관리비',
}
# 정액 관리비 세부 항목 중 관리비에 든 정액. 나머지(ACTUAL_EXPENSE)는 웹에 '실비' 로 보이고 따로 낸다
FIXED_FEE_TYPE: str = 'FIXED_FEE'
# 공용(F01)은 정액·실비 표시와 상관없이 웹이 금액과 함께 보여 주고 관리비 합계에 넣는다 (safety-option-chunk `E` 의 `h`, 2026-11-13)
COMMON_FEE_CODE: str = 'F01'
# 관리비 부과 방식 (safety-option-chunk `w`, 2026-11-13). 웹은 확인불가에는 표시를 붙이지 않고 상세보기에 '확인불가' 로 쓴다
MANAGE_CHARGE_TYPE_LABELS: dict[str, str] = {
    'FIXED_FEE_CHARGE': '정액관리비',
    'ETC_FEE_CHARGE': '기타부과',
    'UNABLE_CHECK': '확인불가',
}
FIXED_FEE_CHARGE: str = 'FIXED_FEE_CHARGE'
ETC_FEE_CHARGE: str = 'ETC_FEE_CHARGE'
# 웹이 관리비 상세보기(항목별)를 여는 입력 방식. 그 밖(SIMPLE)은 포함 항목 글(maintenance_items_str)만 괄호로 보인다 (room-chunk)
DETAIL_INPUT_TYPE: str = 'DETAIL'
# 정액관리비 중 항목마다 정액·실비를 적은 세부 종류 (세부 종류가 없거나 비어도 웹은 이쪽으로 본다). 10만원 미만(BELOW_…)·세부
# 미고지(ABOVE_…_NO_DETAILS) 정액관리비와 기타부과는 포함 항목 코드(maintenance_etc_fee_charge_detail)로 보인다
ITEMIZED_FIXED_FEE_DETAIL_TYPE: str = 'ABOVE_FIXED_FEE_THRESHOLD'
# 에어컨 종류 옵션. 웹은 에어컨 목록(airConditionerTypeList)의 이름을 '에어컨' 없이 옵션에 섞어 보여 준다 (listing-request 청크)
AIR_CONDITIONER_OPTIONS: frozenset[str] = frozenset({'벽걸이형', '스탠드형', '천장형'})
ELEVATOR_BY_TEXT: dict[str, bool] = {'있음': True, '없음': False}
# --details 로 상세를 붙이는 매물 수 (직방·당근과 같다). 한 건에 요청 1회
DETAILS_MAX: int = 30

LISTING_ID_PATTERN: re.Pattern[str] = re.compile(LISTING_ID_PATTERN_TEXT)
# 매물번호는 0 으로 시작하지 않는다. '00000' 같은 값은 요청 모델(seq > 0)의 영어 메시지 대신 CLI 의 형식 오류로 막는다
LISTING_NUMBER_PATTERN: re.Pattern[str] = re.compile(r'^[1-9]\d{4,9}$')
