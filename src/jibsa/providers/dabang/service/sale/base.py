"""분양 기능(sale)의 목록·일정이 같이 쓰는 것: 분양 단지 줄 변환."""


from jibsa.core.listing import (
    normalize_address,
)
from jibsa.providers.dabang.api.response.sale.base import DabangSaleInLotsRowModel
from jibsa.providers.dabang.service.common.functions import (
    manwon_from_text,
)

from typing import (
    Any,
)


# 목록의 가격 이름표가 이 값이면 금액이 임대 보증금이라 `deposit_manwon` 에 담는다 (군포대야미 A-1블록 6년 분양전환공공임대 55A
# 다방 임대가 8561 = 모집공고 임대보증금 85,614,000원, 2026-11-25. '보증금' 은 예전 지도 목록 이름표)
RENTAL_PRICE_KINDS: frozenset[str] = frozenset({'임대가', '보증금'})


def _in_lots_fields(item: DabangSaleInLotsRowModel) -> dict[str, Any]:
    """분양 지역 목록(`list/search3`)·청약 일정 표(`list/schedule/search`) 한 줄의 상태·유형·주소·세대수·가격 칸.

    두 목록은 같은 줄 꼴이라 `DabangSaleSummary`·`DabangSaleScheduleSale` 가 같이 쓴다. 웹 목록의 세대수 칸은 분양
    세대수(`lots_household_num`)다. 응답 줄은 공통 칸을 부모(`DabangSaleInLotsRowModel`)로 올렸지만 출력 모델 두 개의 필드
    선언은 올리지 않는다 (pydantic 은 부모 필드를 앞에 둬 search sales 의 키 순서가 presale_id·name 보다 앞으로 바뀐다).
    """
    amount_key = 'deposit_manwon' if item.price_supply_type_str in RENTAL_PRICE_KINDS else 'price_manwon'
    return {
        'status': item.state_title,
        'complex_type': item.building_types_title,
        'supply_type': item.supply_type_title,
        'address': normalize_address(item.address),
        'presale_household_count': item.lots_household_num,
        'household_count': item.total_household_num,
        'price_kind': item.price_supply_type_str,
        amount_key: manwon_from_text(item.price_str),
    }
