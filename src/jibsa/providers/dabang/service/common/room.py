"""다방 목록 한 칸(방 매물)을 `DabangListing` 으로 바꾸고 조건을 필터로 만들기, 목록 안내."""
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    TradeType,
    m2_to_pyeong,
    note,
)
from jibsa.providers.dabang.api.request.common import (
    ALL_ROOM_COUNTS,
    ALL_ROOM_FLOORS,
    ALL_ROOM_TYPES,
    UNBOUNDED_MAX,
    DabangAptFiltersModel,
    DabangHouseVillaFiltersModel,
    DabangListFilters,
    DabangOfficetelFiltersModel,
    DabangOneTwoFiltersModel,
    DabangRangeModel,
)
from jibsa.providers.dabang.api.response.common import DabangRoomItemModel
from jibsa.providers.dabang.service.common.constants import (
    APARTMENT_TYPE,
    CATEGORY_BY_KIND,
    CONDITION_FIELD_BY_LABEL,
    CONDITIONS_BY_KIND,
    FLOOR_FILTER_BY_LABEL,
    KIND_LABELS,
    LISTING_URL,
    ROOM_COUNT_FILTER_BY_LABEL,
    ROOM_TYPE_FILTER_BY_LABEL,
    SELLING_TYPE_BY_TRADE,
    SHORT_LEASE_MARK,
    SOURCE,
    TRADE_BY_PRICE_TYPE_NAME,
    TRADE_TYPES_BY_KIND,
    ListingKind,
)
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
    DabangListingConditions,
)
from jibsa.providers.dabang.service.common.text import (
    floor_label,
    manwon_from_text,
    number_of,
)

from typing import Any


def listing_prices(trade_type: TradeType, price_title: str | None) -> dict[str, float] | None:
    """목록 가격 글자를 거래 유형에 맞는 금액 필드로 바꾼다 (월세 '1000/63' → 보증금 1000·월세 63). 읽지 못하면 None."""
    parts = (price_title or '').split('/')
    values = [manwon_from_text(part) for part in parts]
    if any(value is None for value in values):
        return None
    if trade_type == '월세' and len(values) == 2:
        return {'deposit_manwon': values[0] or 0, 'rent_manwon': values[1] or 0}
    if trade_type == '전세' and len(values) == 1:
        return {'deposit_manwon': values[0] or 0}
    if trade_type == '매매' and len(values) == 1:
        return {'price_manwon': values[0] or 0}
    return None


def parse_room_desc(desc: str | None) -> tuple[str | None, float | None, float | None]:
    """목록 설명 '5층, 19.83m², 관리비 7만' 을 (층, 면적 ㎡, 관리비 만원) 으로 나눈다. 없는 값은 None (모름).

    '관리비 없음' 은 0 이다 (상세도 관리비 없음으로 준다, 2026-10-25 실측). 면적은 원룸·빌라·오피스텔이면 상세의
    전용면적(`room_size`), 아파트면 공급면적(`provision_size`)이다 (`room_item_to_listing`).
    """
    floor: str | None = None
    area: float | None = None
    manage: float | None = None
    for token in (part.strip() for part in (desc or '').split(',')):
        if token.endswith(('m²', '㎡')):
            area = number_of(token)
        elif token.startswith('관리비'):
            amount = token.removeprefix('관리비').strip()
            manage = 0.0 if amount in ('없음', '0') else manwon_from_text(amount.removesuffix('만'))
        elif token.endswith('층') or token in ('반지하', '옥탑', '옥탑방'):
            floor = floor_label(token)
    return floor, area, manage


def property_label(room_type_name: str | None, kind: ListingKind) -> tuple[str, bool]:
    """목록 매물 종류 표시를 (매물 유형, 단기임대 표시) 로 나눈다 ('오피스텔 • 단기' → ('오피스텔', True)).

    주택·빌라 목록은 방 개수('원룸', '투룸')로 표시해 건물 종류를 알 수 없어 '빌라' 로 둔다.
    """
    base, _, mark = (room_type_name or '').partition('•')
    short = SHORT_LEASE_MARK in mark
    if kind == 'villa':
        return '빌라', short
    return base.strip() or KIND_LABELS[kind], short


def room_type_of(room_type_name: str | None) -> str | None:
    """방 구조는 다방이 투룸·쓰리룸으로 밝힐 때만 준다. '원룸' 은 오픈형·분리형을 알 수 없어 None (모름).

    상세는 구조를 괄호로 붙여 준다 ('투룸(복층)', 2026-10-25 실측: 목록에서 '투룸' 인 매물 6acdf475f0bb4161a878293c).
    """
    base = (room_type_name or '').partition('•')[0].partition('(')[0].strip()
    return base if base in ('투룸', '쓰리룸') else None


def room_item_to_listing(
    item: DabangRoomItemModel,
    kind: ListingKind,
    *,
    center: tuple[float, float] | None = None,
    addresses: dict[int, str] | None = None,
) -> DabangListing | None:
    """목록 매물 한 칸을 `DabangListing` 으로. 거래 유형·가격을 읽지 못하면 None (부르는 쪽이 빼고 알린다).

    Args:
        center: 거리를 잴 검색 중심 (역·좌표 검색). 없으면 거리 없음.
        addresses: 동 번호 → 시·도부터 이은 동 이름. 찾은 동의 매물만 시·구까지 붙인다.
    """
    trade_type = TRADE_BY_PRICE_TYPE_NAME.get(item.price_type_name or '')
    if trade_type is None:
        return None
    prices = listing_prices(trade_type, item.price_title)
    if prices is None:
        return None
    property_type, short = property_label(item.room_type_name, kind)
    floor, area, manage = parse_room_desc(item.room_desc)
    # 아파트 칸의 면적은 전용이 아니라 공급면적이다. 아파트 목록·단지 매물·인기 매물과 원룸·투룸 목록에 섞인 아파트 모두
    # 같다 (2026-10-26 실측: 세연파크뷰 목록 94.53㎡ = 상세 공급, 전용 83.58㎡ / 원룸·투룸 목록의 대치더블유타워(도시형)
    # 47.27㎡ = 공급, 전용 33.78㎡). 오피스텔·빌라·원룸은 전용과 같다 (역삼SK허브블루 35.34㎡ = 19A 전용)
    apartment = kind == 'apt' or property_type.startswith(APARTMENT_TYPE)
    location = item.random_location
    distance = None
    if center is not None and location is not None:
        distance = round(haversine_km(center[0], center[1], location.lat, location.lng), 2)
    address = (addresses or {}).get(item.gid or 0) or item.dong_name
    return DabangListing(
        source=SOURCE,
        id=item.id,
        url=LISTING_URL.format(item.id),
        trade_type=trade_type,
        property_type=property_type,
        room_type=room_type_of(item.room_type_name),
        title=item.room_title,
        manage_cost_manwon=manage,
        area_m2=None if apartment else area,
        area_pyeong=None if apartment else m2_to_pyeong(area),
        supply_area_m2=area if apartment else None,
        floor=floor,
        address=address,
        lat=location.lat if location else None,
        lng=location.lng if location else None,
        distance_km=distance,
        listing_number=item.seq,
        short_term=short and trade_type == '월세',
        complex_name=item.complex_name,
        **prices,
    )


def range_of(minimum: int | None, maximum: int | None) -> DabangRangeModel:
    """다방은 범위 값을 999999 까지만 받는다 (넘으면 400 '최대값은 999999 이하로 입력해주세요', 2026-10-25 실측).
    그보다 큰 상한은 999999 로 줄여 보낸다 (압구정·청담·한남동 아파트 매매도 98억까지라 빠지는 매물을 보지 못했다).
    큰 하한은 CLI 가 막는다.
    """
    return DabangRangeModel(min=minimum or 0, max=UNBOUNDED_MAX if maximum is None else min(maximum, UNBOUNDED_MAX))


def filters_of(kind: ListingKind, conditions: DabangListingConditions) -> DabangListFilters:
    """검색 조건을 다방 유형 필터로 바꾼다. 주지 않은 항목은 '전체' 값이다 (다방은 항목이 빠지면 400).

    CLI 가 유형마다 받는 조건만 열어 두므로, 그 유형에 없는 조건은 여기 오지 않는다.
    """
    category = CATEGORY_BY_KIND[kind]
    flags = {CONDITION_FIELD_BY_LABEL[label]: True for label in conditions.conditions if label in CONDITIONS_BY_KIND[kind]}
    common: dict[str, Any] = {
        'deposit_range': range_of(conditions.deposit_min, conditions.deposit_max),
        'price_range': range_of(conditions.rent_min, conditions.rent_max),
        'is_include_maintenance': conditions.rent_includes_manage_cost,
        'pyeong_range': range_of(conditions.area_pyeong_min, conditions.area_pyeong_max),
        'use_approval_date_range': range_of(None, conditions.built_within_years),
        'is_short_lease': flags.pop('is_short_lease', False),
    }
    selling = [SELLING_TYPE_BY_TRADE[trade] for trade in conditions.trade_types or TRADE_TYPES_BY_KIND[kind]]
    floors = [FLOOR_FILTER_BY_LABEL[label] for label in conditions.floors] or list(ALL_ROOM_FLOORS)
    if category == 'one-two':
        return DabangOneTwoFiltersModel(
            **common,
            **flags,
            selling_type_list=[code for code in selling if code != 'SELL'],
            room_floor_list=floors,
            room_type_list=[ROOM_TYPE_FILTER_BY_LABEL[label] for label in conditions.rooms] or list(ALL_ROOM_TYPES),
        )
    sale: dict[str, Any] = {
        **common,
        **flags,
        'selling_type_list': selling,
        'trade_range': range_of(conditions.price_min, conditions.price_max),
        'room_count_list': [ROOM_COUNT_FILTER_BY_LABEL[label] for label in conditions.rooms] or list(ALL_ROOM_COUNTS),
    }
    if category == 'house-villa':
        return DabangHouseVillaFiltersModel(**sale, room_floor_list=floors)
    parking = range_of(conditions.parking_per_household_min, None)
    if category == 'officetel':
        return DabangOfficetelFiltersModel(**sale, parking_num_range=parking)
    return DabangAptFiltersModel(
        **sale, household_num_range=range_of(conditions.households_min, conditions.households_max), parking_num_range=parking,
    )


def premium_note(count: int) -> list[str]:
    """목록과 함께 온 광고(중개사별 추천 매물)를 뺐다는 안내."""
    if count <= 0:
        return []
    return [note('제외', f'다방 광고 칸(중개사 추천 매물) {count}건은 넣지 않았습니다')]


def unreadable_note(count: int) -> list[str]:
    """가격·거래 유형을 읽지 못해 뺀 매물이 있다는 안내."""
    if count <= 0:
        return []
    return [note('제외', f'가격·거래 유형을 읽지 못한 {count}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}')]
