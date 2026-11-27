"""직방 service 공통(단기임대 목록): 방 종류·옵션 표시 이름, 할인 조건 글, 요약 → 매물 변환. 목록 줄 모델은 stay.models 에 있다."""

from jibsa.core.listing import (
    format_manwon,
    join_address,
    m2_to_pyeong,
    read_date,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.models.response.stay.common import (
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
)
from jibsa.providers.zigbang.service.common.text import (
    sent_or_none,
)
from jibsa.providers.zigbang.service.stay.constants import (
    STAY_BUILDING_TYPE_LABELS,
    STAY_URL,
)
from jibsa.providers.zigbang.service.stay.models import ZigbangStayListing


def stay_discount_label(discount: ZigbangStayDiscountModel, weekly_rent: int | None) -> str | None:
    """할인 조건 한 줄. 웹 상세(`DiscountDetailList`)가 그리지 않는 할인은 None.

    웹은 장기계약·즉시입주 할인만 그린다. 장기계약은 주 수·할인율·주당 임대료가 모두 0보다 클 때만 '{주}주 이상 {율}% 할인' 이고
    할인 금액은 쓰지 않는다. 즉시입주는 금액만 보고(0 이하면 None) 입주 시점 조건을 붙인다. 주 수·할인율·조건 일수가 null 이면
    웹처럼 0 으로 본다 (조건 일수 0 은 오늘). 웹은 할인의 `isActive` 를 보지 않아 꺼진 할인도 그리므로 여기서도 거르지 않는다
    (2026-11-15 번들 `DiscountDetailList`·목록 카드 `pickDiscountTextsForCard`. 실측 강남역·홍대입구역 할인 124건은 모두 true).
    """
    if discount.discount_type == 'LONG_TERM':
        weeks = discount.condition_weeks or 0
        rate = discount.discount_rate or 0
        if weeks <= 0 or rate <= 0 or (weekly_rent or 0) <= 0:
            return None
        return f'{weeks}주 이상 {rate:g}% 할인'
    if discount.discount_type == 'INSTANT':
        # 할인 금액(원)을 'N만원' 으로 (반올림 없이 원 단위까지, 2,500원 → '0.25만원'). 금액이 없거나 0 이하면 None (할인이 아니다)
        amount = (
            None if not discount.discount_amount or discount.discount_amount <= 0
            else f'{format_manwon(won_to_manwon(discount.discount_amount) or 0)}만원'
        )
        if amount is None:
            # 리뷰 오탐 (2026-11-15): --discount 즉시 결과에서 즉시 할인이 빠지지 않는다. 웹이 금액 없는 즉시 할인을 숨기고,
            # 실측 강남역 --discount 즉시 의 즉시 할인 27건은 모두 금액(discountAmount)이 있었다 (할인율만 있는 것 0건)
            return None
        days = discount.condition_days or 0
        return f'오늘 입주 시 {amount} 할인' if days == 0 else f'오늘부터 {days}일 이내 입주 시 {amount} 할인'
    return None


def stay_discounts(discounts: list[ZigbangStayDiscountModel], weekly_rent: int | None) -> list[str]:
    return [label for label in (stay_discount_label(discount, weekly_rent) for discount in discounts) if label]


def stay_summary_to_listing(
    summary: ZigbangStayItemSummaryModel,
    distance_km: float | None = None,
) -> ZigbangStayListing:
    address = summary.address
    return ZigbangStayListing(
        source='zigbang',
        id=f'stay-{summary.id}',
        url=STAY_URL.format(summary.id),
        trade_type='단기임대',
        property_type=STAY_BUILDING_TYPE_LABELS.get(summary.building_type or '', summary.building_type or '단기임대'),
        title=summary.title,
        area_m2=summary.size_m2,
        area_pyeong=m2_to_pyeong(summary.size_m2),
        floor=summary.floor,
        address=join_address(
            address.local1 if address else None,
            address.local2 if address else None,
            address.local3 if address else None,
            address.local4 if address else None,
        ),
        lat=summary.lat,
        lng=summary.lng,
        distance_km=None if distance_km is None else round(distance_km, 2),
        registered_date=read_date(summary.reviewed_at, '등록일'),
        weekly_rent_manwon=won_to_manwon(summary.weekly_rent),
        weekly_manage_cost_manwon=won_to_manwon(summary.weekly_manage_cost),
        room_count=summary.room_count,
        bathroom_count=summary.bathroom_count,
        discounts=sent_or_none(summary, 'discounts', stay_discounts(summary.discounts, summary.weekly_rent)),
    )
