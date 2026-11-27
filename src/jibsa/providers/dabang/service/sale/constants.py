"""분양 기능(sale)의 상수: 임대 가격 이름표·날짜 패턴·`--building-type`·`--state`·`--supply` 이름표·청약 일정 한도."""
import re

from jibsa.providers.dabang.api.models.request.sale.search import (
    DabangSaleBuildingType,
    DabangSaleState,
    DabangSaleSupplyType,
)


# 목록의 가격 이름표가 이 값이면 금액이 임대 보증금이라 `deposit_manwon` 에 담는다 (군포대야미 A-1블록 6년 분양전환공공임대 55A
# 다방 임대가 8561 = 모집공고 임대보증금 85,614,000원, 2026-11-25. '보증금' 은 예전 지도 목록 이름표)
RENTAL_PRICE_KINDS: frozenset[str] = frozenset({'임대가', '보증금'})

# 분양 일정 날짜 꼴: '26.09.07' (날), '26.08월' (달)
SALE_DAY_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})\.(\d{1,2})$')
SALE_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})월$')
# `sale_date` 가 바꾼 꼴
SALE_ISO_DAY_PATTERN: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}-\d{2}$')
SALE_ISO_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}$')

# 웹은 공급 유형 코드가 4·5(공공임대·민간임대)면 가격 이름표를 '임대가', 아니면 '분양가' 로 쓴다 (ic_24_download 청크 `x`,
# 2026-11-13. 민간임대 6acca80f… 화면 '임대가 4억7770')
RENTAL_SUPPLY_TYPES: frozenset[int] = frozenset({4, 5})

GIVEN_AMOUNT_FIELDS: tuple[str, ...] = ('price_manwon', 'deposit_manwon')
"""분양가·임대 보증금 칸. 생성할 때 넘기지 않은 칸은 해당 없음이라 키를 빼고(`drop_unset_fields`), 넘긴 None 은 null 이다."""

# sale-schedule 의 --limit 최대값. CLI 옵션의 max 와 더 보는 법 안내가 함께 쓴다
SALE_SCHEDULE_MAX_LIMIT: int = 300
# 청약 일정 글: '[청약접수] 인천 인천계양 A17블록 … (~10/27)'
SCHEDULE_REGION_PATTERN: re.Pattern[str] = re.compile(r'^(?:\[[^\]]+\]\s*)+(\S+)')

SALE_BUILDING_TYPE_BY_LABEL: dict[str, DabangSaleBuildingType] = {
    '아파트': 'APT',
    '오피스텔': 'OFFICETEL',
    '도시형생활주택': 'URBAN_HOUSE',
    '지식산업센터': 'KNOWLEDGE_INDUSTRY_CENTER',
}
SALE_STATE_BY_LABEL: dict[str, DabangSaleState] = {
    '분양예정': 'EXPECTED',
    '접수중': 'ACCEPTING',
    '접수마감': 'ACCEPT_COMPLETE',
    '입주예정': 'MOVE_IN_EXPECTED',
    '입주모집': 'MOVE_IN_RECRUIT',
}
SALE_SUPPLY_BY_LABEL: dict[str, DabangSaleSupplyType] = {
    '공공분양': 'PUBLIC_SALE',
    '민간분양': 'PRIVATE_SALE',
    '공공임대': 'PUBLIC_RENTAL',
    '민간임대': 'PRIVATE_RENTAL',
}
