"""직방 service 공통(단기임대 목록): 방 종류·옵션 표시 이름, 목록 줄 모델, 할인 조건 글, 요약 → 매물 변환."""

from pydantic import Field

from jibsa.core.listing import (
    Listing,
    format_manwon,
    join_address,
    m2_to_pyeong,
    normalize_date,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.response.stay.base import (
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
)
from jibsa.providers.zigbang.service.common.base import sent_or_none

from typing import Annotated


# 단기임대 검색 결과 줄(`ZigbangStayListing`)과 상세가 같이 쓰는 것, 검색 조건과 상세가 같이 쓰는 이름표.
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


def stay_item_url(stay_id: int | str) -> str:
    """단기임대 매물 웹 페이지 주소. 로그인 없이 열린다."""
    return f'https://www.zigbang.com/stay/item/{stay_id}'


class ZigbangStayListing(Listing):
    """직방 단기임대 서비스 매물. 요금이 주 단위라 월세·월 관리비 대신 주당 금액을 준다."""

    weekly_rent_manwon: Annotated[
        float | None,
        Field(description='주당 임대료 (만원)')
    ] = None
    weekly_manage_cost_manwon: Annotated[
        float | None,
        Field(description='주당 관리비 (만원)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    discounts: Annotated[
        list[str] | None,
        Field(description="할인 조건 (예: '4주 이상 10% 할인')")
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 요금이 주 단위라 월세·월 관리비가 해당 없다
        return super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}


def _discount_amount_text(amount_won: float | None) -> str | None:
    """할인 금액(원)을 'N만원' 으로 (반올림 없이 원 단위까지, 2,500원 → '0.25만원'). 금액이 없거나 0 이하면 None (할인이 아니다)."""
    if not amount_won or amount_won <= 0:
        return None
    return f'{format_manwon(won_to_manwon(amount_won) or 0)}만원'


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
        amount = _discount_amount_text(discount.discount_amount)
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
        url=stay_item_url(summary.id),
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
        registered_at=normalize_date(summary.reviewed_at),
        weekly_rent_manwon=won_to_manwon(summary.weekly_rent),
        weekly_manage_cost_manwon=won_to_manwon(summary.weekly_manage_cost),
        room_count=summary.room_count,
        bathroom_count=summary.bathroom_count,
        discounts=sent_or_none(summary, 'discounts', stay_discounts(summary.discounts, summary.weekly_rent)),
    )
