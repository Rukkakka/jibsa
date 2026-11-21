"""직방 service 공통(원룸·빌라·오피스텔 목록): 거래 유형·방 구조 표, 매물 조건, 요약 → 매물 변환, 섹션 순서 목록, 제외 안내."""

from collections.abc import (
    Callable,
    Iterable,
)

from pydantic import Field

from jibsa.core.listing import (
    TradeType,
    join_address,
    m2_to_pyeong,
    normalize_date,
    note,
    won_to_manwon,
)
from jibsa.core.schema import (
    RequestModel,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangFloorFilter,
    ZigbangItemsListV1RequestPayloadModel,
    ZigbangOptionFilter,
    ZigbangRoomTypeFilter,
    ZigbangSalesType,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangItemPinModel,
    ZigbangItemSectionModel,
    ZigbangItemSummaryModel,
)
from jibsa.providers.zigbang.service.common.base import (
    ZigbangListing,
    item_url,
    officetel_complex_id,
)

from typing import (
    Annotated,
    Protocol,
)


TRADE_TYPES: tuple[TradeType, ...] = ('전세', '월세', '매매', '단기임대')
# jibsa 거래 유형 → 직방 거래 유형 필터 값. 단기임대만 이름이 다르다.
SALES_TYPE_BY_TRADE: dict[str, ZigbangSalesType] = {
    '전세': '전세',
    '월세': '월세',
    '매매': '매매',
    '단기임대': '단기',
}
SHORT_TERM_CONTRACT: str = '단기'
ITEMS_LIST_BATCH_SIZE: int = 15
# 웹 목록이 섹션을 잇는 순서: VIP → 안심추천 → 안심일반 → 추천(원룸 목록은 '이 지역 오피스텔') → 일반 (2026-11-15 번들 `_app` 의
# `createSectionsToUpdate`·`loadItemsV2`. 실측: 강남역 3km 지도 칸 18곳 모두 다섯 섹션을 이 순서로 주고 빈 섹션도 ids [] 로 둔다)
SECTION_ORDER: tuple[str, ...] = ('VIP', 'PREMIUM_RECOMMEND', 'PREMIUM', 'RECOMMEND', 'NORMAL')
ROOM_TYPE_BY_CODE: dict[str, str] = {
    '01': '오픈형원룸',
    '02': '분리형원룸',
    '03': '복층형원룸',
    '04': '투룸',
    '05': '쓰리룸',
    '06': '포룸이상',
}
ROOM_TYPES: tuple[str, ...] = tuple(ROOM_TYPE_BY_CODE.values())
# 방 구조 라벨 → 목록 API 의 방 구조 필터 값. 쓰리룸·포룸이상만 필터 이름이 다르다.
ROOM_TYPE_FILTER_BY_LABEL: dict[str, ZigbangRoomTypeFilter] = {
    '오픈형원룸': '오픈형원룸',
    '분리형원룸': '분리형원룸',
    '복층형원룸': '복층형원룸',
    '투룸': '투룸',
    '쓰리룸': '쓰리룸플러스',
    '포룸이상': '포룸플러스',
}
FLOOR_FILTERS: tuple[ZigbangFloorFilter, ...] = ('지상', '반지하', '옥탑방', '1층')
OPTION_FILTERS: tuple[ZigbangOptionFilter, ...] = (
    '에어컨', '냉장고', '세탁기', '가스레인지', '인덕션', '전자레인지',
    '책상', '책장', '침대', '옷장', '신발장', '싱크대',
)
# 기타 조건 라벨 → 목록 요청 모델의 참/거짓 필드.
CONDITION_FIELD_BY_LABEL: dict[str, str] = {
    '즉시입주': 'immediate_move',
    '남향': 'south_facing',
    '엘리베이터': 'elevator',
    '주차': 'parking',
    'CCTV': 'cctv',
    '반려동물': 'pet',
    '전세대출': 'loan_lease',
    '전기차충전': 'ev_station',
}
CONDITIONS: tuple[str, ...] = tuple(CONDITION_FIELD_BY_LABEL)
# 원룸·빌라·오피스텔 매물 요약·상세의 배지 코드. 웹은 배지 목록에 이 코드가 정확히 있는지로 꼬리표를 붙인다 (2026-11-19 번들
# `useVerifiedItemTag`·`useLessorHugTag`). 'ITEM_VERIFICATION_FAILED' 는 실매물 확인이 아니다
VERIFICATION_BADGE: str = 'ITEM_VERIFICATION'
HUG_BADGE: str = 'HUG'


def trade_type_of(summary: ZigbangItemSummaryModel) -> str:
    """요약 응답의 거래 유형. 직방은 단기임대를 월세로 주고 `contract` 로만 구분한다.

    그대로 옮기면 보증금이 월세 한두 달치(예: 75/75)인 단기임대가 싼 월세로 보인다.
    """
    if summary.sales_type == '월세' and summary.contract == SHORT_TERM_CONTRACT:
        return '단기임대'
    return summary.sales_type


def badge_flag(badges: list[str] | None, code: str) -> bool | None:
    """배지 목록에 `code` 가 정확히 있는지. 목록을 받지 못했으면(None) 모름(None), 빈 목록이면 없다(False).

    웹 꼬리표(`useVerifiedItemTag` 의 실매물 확인, `useLessorHugTag` 의 HUG안심임대인)가 같은 식(`badges.includes`)이다.
    """
    return None if badges is None else code in badges


def summary_to_listing(
    summary: ZigbangItemSummaryModel,
    distance_km: float | None = None,
    building_id: int | None = None,
) -> ZigbangListing:
    """요약 응답 한 건을 `ZigbangListing` 으로 바꾼다.

    매매 매물은 요약 응답의 `deposit` 에 매매가가 들어오므로 `price_manwon` 으로
    옮긴다. 관리비는 웹 목록 카드와 같은 값(`listed_manage_cost`, 원 단위)을 만원으로 환산한다: 0 이면 0(웹 '관리비 없음'),
    null 이면 모름. 금액은 원 단위까지 낸다. 웹 카드는 0.1만원 아래를 버려 보여 준다 (_app 번들 toManWonText
    `Math.floor(fee/1e4*10)/10`, 375,700원 → 37.5, jibsa 37.57). 면적은 `size_m2`
    (공급면적) 대신 `전용면적` 을 쓴다. 단기임대는 `trade_type_of` 로 구분한다.
    요약에는 오피스텔 건물 ID 가 없어 지도 핀의 `buildingId` 를 `building_id` 로 받는다. HUG 안심임대인·실매물 확인은 웹 목록 카드처럼
    카드의 배지 목록(`listed_badges`: `itemSummaries[].badges`, 키가 없으면 `items[].badges`)으로 정한다 (`badge_flag`).
    """
    is_sale = summary.sales_type == '매매'
    # `size_m2` 는 공급면적이라(오피스텔은 전용의 2배 넘게 나오기도 한다) 전용면적을 우선한다.
    # 원룸·빌라는 둘이 같아 전용면적이 빠졌을 때 대신 쓰지만, 오피스텔은 전용으로 잘못 읽히므로 모름(None)으로 둔다.
    area_m2 = summary.exclusive_area.m2 if summary.exclusive_area else None
    if area_m2 is None and summary.service_type != '오피스텔':
        area_m2 = summary.size_m2

    return ZigbangListing(
        source='zigbang',
        id=str(summary.item_id),
        url=item_url(summary.service_type, summary.item_id),
        trade_type=trade_type_of(summary),
        property_type=summary.service_type,
        room_type=ROOM_TYPE_BY_CODE.get(summary.room_type or ''),
        title=summary.title,
        price_manwon=summary.deposit if is_sale else None,
        deposit_manwon=None if is_sale else summary.deposit,
        rent_manwon=summary.rent if summary.sales_type == '월세' else None,
        # 리뷰 오탐 (2026-11-15): 관리비 확인 불가(UnknownManageCost) 매물은 itemSummaries[].fee 가 0 이 아니라 null 이라
        # 목록·상세 모두 모름이다 (서초동 오피스텔 51031039 실측). 목록은 웹 카드의 fee 를 그대로 따른다
        manage_cost_manwon=won_to_manwon(summary.listed_manage_cost),
        area_m2=area_m2,
        area_pyeong=m2_to_pyeong(area_m2),
        floor=summary.floor,
        building_floor=summary.building_floor,
        address=join_address(
            summary.address1,
            summary.address_origin.address2 if summary.address_origin else None,
        ),
        lat=summary.location.lat if summary.location else None,
        lng=summary.location.lng if summary.location else None,
        distance_km=None if distance_km is None else round(distance_km, 2),
        registered_at=normalize_date(summary.reg_date),
        complex_id=officetel_complex_id(building_id) if building_id else None,
        hug_lessor=badge_flag(summary.listed_badges, HUG_BADGE),
        actual_listing_checked=badge_flag(summary.listed_badges, VERIFICATION_BADGE),
    )


class ZigbangRoomConditions(RequestModel):
    """원룸·빌라·오피스텔 매물 조건 (search listings room, search listings --complex). 금액은 만원.

    라벨은 `TRADE_TYPES`·`ROOM_TYPES`·`FLOOR_FILTERS`·`OPTION_FILTERS`·`CONDITIONS` 의 값이다. 값의 범위·조합은
    CLI 가 먼저 검사한다. 거래 유형·가격은 `filters` 처럼 유형마다 따로 넣고, 나머지는 `room_filter_of` 로 바꾼다.
    """

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형. 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    room_types: Annotated[
        list[str],
        Field(description='방 구조 (ROOM_TYPES). 비면 유형별 기본')
    ] = []
    manage_cost_min: Annotated[
        int | None,
        Field(description='월 관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='월 관리비 상한 (만원)')
    ] = None
    no_manage_cost: Annotated[
        bool,
        Field(description='관리비 없는 매물만')
    ] = False
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    area_min_pyeong: Annotated[
        float | None,
        Field(description='면적 하한 (평)')
    ] = None
    area_max_pyeong: Annotated[
        float | None,
        Field(description='면적 상한 (평)')
    ] = None
    floors: Annotated[
        list[ZigbangFloorFilter],
        Field(description='층 (FLOOR_FILTERS, OR)')
    ] = []
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수 (3 은 3개 이상)')
    ] = None
    options: Annotated[
        list[ZigbangOptionFilter],
        Field(description='옵션 (OPTION_FILTERS, AND)')
    ] = []
    extra_conditions: Annotated[
        list[str],
        Field(description='기타 조건 (CONDITIONS, AND)')
    ] = []


def room_filter_of(conditions: ZigbangRoomConditions) -> dict[str, object]:
    """관리비·면적·층·욕실·옵션·시설 조건을 원룸·빌라·오피스텔 요청 필드로 바꾼다 (지도 목록과 오피스텔 건물 공통)."""
    return {
        'manage_cost_min': conditions.manage_cost_min,
        'manage_cost_max': conditions.manage_cost_max,
        'no_manage_cost': conditions.no_manage_cost or None,
        'size_min_m2': conditions.area_min_m2,
        'size_max_m2': conditions.area_max_m2,
        'size_min_pyeong': conditions.area_min_pyeong,
        'size_max_pyeong': conditions.area_max_pyeong,
        'floors': conditions.floors,
        'bathroom_count': conditions.bathroom_count,
        'options': conditions.options,
        **{CONDITION_FIELD_BY_LABEL[condition]: True for condition in conditions.extra_conditions},
    }


class SectionedPins(Protocol):
    """핀과 섹션을 함께 주는 응답 (지도 칸·역 반경·오피스텔 건물)."""

    @property
    def items(self) -> list[ZigbangItemPinModel]: ...

    @property
    def sections(self) -> list[ZigbangItemSectionModel]: ...


def section_ordered_ids(
    responses: Iterable[SectionedPins],
    keep: Callable[[ZigbangItemPinModel | None], bool] = lambda pin: True,
) -> list[int]:
    """응답들(지도 칸 여럿이면 칸 순서)의 매물 ID 를 웹 목록 순서로 잇는다. 지도 목록(`room.search`)과 오피스텔 건물 매물이 함께 쓴다.

    섹션 종류는 `SECTION_ORDER` 순서이고, 종류마다 응답 순서대로 잇는다. 처음 보는 섹션 종류는 아는 종류 뒤에 처음 나온
    순서로, 어느 섹션에도 없는 핀은 잃지 않게 맨 뒤에 응답·핀 순서로 붙인다. 같은 매물이 두 번 오면 앞의 것만 둔다.
    `keep` 은 섹션의 매물이면 그 핀(핀이 없으면 None)을, 섹션 밖이면 핀을 받아 남길지 정한다 (범위 안인지).

    응답마다의 섹션 순서를 합치면 빈 섹션을 뺀 칸이 있을 때 섹션의 앞뒤가 뒤집혔다 (2026-11-16 리뷰: [안심일반, 일반] 칸 뒤에
    [VIP, 안심추천, 일반] 칸이 오면 VIP·안심추천이 안심일반 뒤로 갔다). 순서표로 정해 두 화면의 규칙이 따로 갈리지 않게 한다.
    """
    by_section: dict[str, list[int]] = {}
    unsectioned: list[int] = []
    for response in responses:
        pins = {pin.id: pin for pin in response.items}
        sectioned: set[int] = set()
        for section in response.sections:
            sectioned.update(section.ids)
            by_section.setdefault(section.type, []).extend(
                item_id for item_id in section.ids if keep(pins.get(item_id))
            )
        unsectioned += [pin.id for pin in response.items if pin.id not in sectioned and keep(pin)]
    order = [kind for kind in SECTION_ORDER if kind in by_section]
    order += [kind for kind in by_section if kind not in SECTION_ORDER]
    return list(dict.fromkeys([*(item_id for kind in order for item_id in by_section[kind]), *unsectioned]))


def tradeable_summaries(client: ZigbangClient, ids: list[int]) -> list[ZigbangItemSummaryModel]:
    """`ids` 의 요약을 15개씩 받아 거래 중인 전세·월세·매매(단기임대 포함)만 준다. 뺀 매물은 다시 채우지 않는다.

    받은 뒤에는 거래 불가와 지원하지 않는 거래 종류만 뺀다. 유형·거래 유형·방 구조는 서버가 걸었으므로 다시 거르지
    않는다 (2026-10-10 실측: 원룸·빌라·오피스텔 월세·전세·단기임대와 방 구조 조건 200건, 오피스텔 건물 3곳 34건 모두 조건 안).
    """
    summaries: list[ZigbangItemSummaryModel] = []
    for start in range(0, len(ids), ITEMS_LIST_BATCH_SIZE):
        batch = ids[start:start + ITEMS_LIST_BATCH_SIZE]
        requested = set(batch)
        response = client.run_request_items_list_v1(ZigbangItemsListV1RequestPayloadModel(item_ids=batch))
        for summary in response.items:
            # 방어용. 실측으로는 요청한 매물만 오지만(2026-10-10 오피스텔 건물 8곳 108건), 끼어 온 매물은 뺀다
            if summary.item_id not in requested:
                continue
            # 내려간 매물. 상태를 알려 주지 않으면(필드가 빠지면) 만료 매물이 섞일 수 있어 함께 뺀다
            if summary.status is not True or summary.sales_type not in ('전세', '월세', '매매'):
                continue
            summaries.append(summary)
    return summaries


def excluded_notes(
    limit: int, inspected: int, returned: int, *, order: str = '직방 목록 순으로 앞의', has_more: bool = True,
) -> list[str]:
    """요약을 받은 뒤 뺀 매물이 있어 `limit` 보다 적게 돌려줄 때의 안내. 뺀 만큼 다시 조회하지 않는다.

    Args:
        order: 요약을 받은 매물을 고른 기준. 원룸·빌라·오피스텔 목록과 건물 매물 목록 모두 직방 목록 순이다.
        has_more: 결과의 `has_more`. 더 받을 매물이 없으면 다시 채우지 않는다는 말 대신 더 받을 매물이 없다고 한다 (당근
            `listing_budget_notes` 와 같다).
    """
    if returned >= limit or inspected <= returned:
        return []
    return [note(
        '제외',
        f'{order} 매물 {inspected}건 중 거래 불가·지원하지 않는 거래 종류를 빼고 {returned}건입니다 '
        + ('(뺀 만큼 다시 채우지 않음)' if has_more else '(더 받을 매물 없음)'),
    )]
