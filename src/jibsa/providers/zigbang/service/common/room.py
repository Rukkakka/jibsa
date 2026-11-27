"""직방 service 공통(원룸·빌라·오피스텔 목록): 거래 유형·방 구조 표, 매물 조건, 요약 → 매물 변환, 섹션 순서 목록, 제외 안내."""

from collections.abc import (
    Callable,
    Iterable,
)

from jibsa.core.listing import (
    join_address,
    m2_to_pyeong,
    note,
    null_items_note,
    read_date,
    won_to_manwon,
)
from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.client import ZIGBANG_WEB_URL, ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangItemsListV1RequestPayloadModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangItemPinModel,
    ZigbangItemSectionModel,
    ZigbangItemSummaryModel,
)
from jibsa.providers.zigbang.service.common.constants import (
    CONDITION_FIELD_BY_LABEL,
    HUG_BADGE,
    ITEMS_LIST_BATCH_SIZE,
    ROOM_TYPE_BY_CODE,
    SECTION_ORDER,
    SHORT_TERM_CONTRACT,
    VERIFICATION_BADGE,
    WEB_PATH_BY_SERVICE_TYPE,
)
from jibsa.providers.zigbang.service.common.ids import officetel_complex_id
from jibsa.providers.zigbang.service.common.models import (
    ZigbangListing,
    ZigbangRoomConditions,
)

from typing import (
    NamedTuple,
    Protocol,
)


class SectionedPins(Protocol):
    """핀과 섹션을 함께 주는 응답 (지도 칸·역 반경·오피스텔 건물)."""

    @property
    def items(self) -> list[ZigbangItemPinModel]: ...

    @property
    def sections(self) -> list[ZigbangItemSectionModel]: ...


class TradeableSummaries(NamedTuple):
    """`tradeable_summaries` 의 결과: 거래 중인 요약 목록과, 요약 응답에서 뺀 빈 항목(null)의 수."""

    items: list[ZigbangItemSummaryModel]
    null_items: int


def item_url(service_type: str | None, item_id: int) -> str:
    path = WEB_PATH_BY_SERVICE_TYPE.get(service_type or '', 'oneroom')
    return f'{ZIGBANG_WEB_URL}/home/{path}/items/{item_id}'


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
        registered_date=read_date(summary.reg_date, '등록일'),
        complex_id=officetel_complex_id(building_id) if building_id else None,
        hug_lessor=badge_flag(summary.listed_badges, HUG_BADGE),
        actual_listing_checked=badge_flag(summary.listed_badges, VERIFICATION_BADGE),
    )


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


def pin_null_notes(what: str, responses: Iterable[ResponseModel]) -> list[str]:
    """핀(`items`)·섹션(`sections`) 목록에서 빈 항목(null)을 빼고 읽었으면 그 안내, 없으면 빈 목록. `section_ordered_ids` 로 세운 목록을 쓰는 곳이 부른다.

    빈 항목은 어느 섹션·어느 매물인지 알 수 없어 그 매물이 목록에서 빠졌을 수 있다. 목록 순서·수(`total`)는 받은 핀·섹션으로 센 값이라
    빠진 만큼 모자랄 수 있다고만 알린다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 (예: '직방 지도 매물 핀·섹션').
        responses: 핀과 섹션을 준 응답들 (지도 칸 여럿이면 칸마다).
    """
    dropped = sum(response.null_items('items', 'sections') for response in responses)
    return [null_items_note(what, dropped)] if dropped else []


def tradeable_summaries(client: ZigbangClient, ids: list[int]) -> TradeableSummaries:
    """`ids` 의 요약을 15개씩 받아 거래 중인 전세·월세·매매(단기임대 포함)만 준다. 뺀 매물은 다시 채우지 않는다.

    받은 뒤에는 거래 불가와 지원하지 않는 거래 종류만 뺀다. 유형·거래 유형·방 구조는 서버가 걸었으므로 다시 거르지
    않는다 (2026-10-10 실측: 원룸·빌라·오피스텔 월세·전세·단기임대와 방 구조 조건 200건, 오피스텔 건물 3곳 34건 모두 조건 안).
    요약 응답의 `items` 에서 빈 항목(null)을 빼고 읽은 수는 `null_items` 로 함께 준다. 빈 항목은 어느 매물인지 알 수 없어
    거래 불가로 뺀 것과 이유가 다르므로 `excluded_notes` 가 따로 밝힌다.
    """
    summaries: list[ZigbangItemSummaryModel] = []
    dropped = 0
    for start in range(0, len(ids), ITEMS_LIST_BATCH_SIZE):
        batch = ids[start:start + ITEMS_LIST_BATCH_SIZE]
        requested = set(batch)
        response = client.run_request_items_list_v1(ZigbangItemsListV1RequestPayloadModel(item_ids=batch))
        dropped += response.null_items('items')
        for summary in response.items:
            # 방어용. 실측으로는 요청한 매물만 오지만(2026-10-10 오피스텔 건물 8곳 108건), 끼어 온 매물은 뺀다
            if summary.item_id not in requested:
                continue
            # 내려간 매물. 상태를 알려 주지 않으면(필드가 빠지면) 만료 매물이 섞일 수 있어 함께 뺀다
            if summary.status is not True or summary.sales_type not in ('전세', '월세', '매매'):
                continue
            summaries.append(summary)
    return TradeableSummaries(summaries, dropped)


def excluded_notes(
    limit: int, inspected: int, returned: int, *, order: str = '직방 목록 순으로 앞의', has_more: bool = True,
    null_items: int = 0,
) -> list[str]:
    """요약을 받은 뒤 뺀 매물이 있어 `limit` 보다 적게 돌려줄 때의 안내. 뺀 만큼 다시 조회하지 않는다.

    Args:
        order: 요약을 받은 매물을 고른 기준. 원룸·빌라·오피스텔 목록과 건물 매물 목록 모두 직방 목록 순이다.
        has_more: 결과의 `has_more`. 더 받을 매물이 없으면 다시 채우지 않는다는 말 대신 더 받을 매물이 없다고 한다 (당근
            `listing_budget_notes` 와 같다).
        null_items: 요약 응답에서 빈 항목(null)으로 뺀 수 (`tradeable_summaries`). 0보다 크면 뺀 이유에 보탠다.
    """
    if returned >= limit or inspected <= returned:
        return []
    reason = '거래 불가·지원하지 않는 거래 종류를'
    if null_items:
        reason = f'거래 불가·지원하지 않는 거래 종류와 직방이 빈 항목으로 준 매물 {null_items}건을'
    return [note(
        '제외',
        f'{order} 매물 {inspected}건 중 {reason} 빼고 {returned}건입니다 '
        + ('(뺀 만큼 다시 채우지 않음)' if has_more else '(더 받을 매물 없음)'),
    )]
