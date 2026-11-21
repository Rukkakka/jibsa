"""원룸·빌라·오피스텔 매물 상세 (listing): 새 주거 상세 + 등록일·단기임대 요약과 건물 학군 덤 (아파트 상세는 apt, ID 분기는 listing)."""

from collections.abc import Callable

from httpx import HTTPStatusError

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.http import error_body
from jibsa.core.listing import (
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    parking_label,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import (
    ZigbangItemsListV1RequestPayloadModel,
)
from jibsa.providers.zigbang.api.request.room.base import (
    ZigbangItemsDetailV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.request.room.detail import (
    ZigbangBlsSchoolZonesV1RequestParameterModel,
    ZigbangItemsV3RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.room.base import (
    ZigbangItemsDetailV1ManageCostModel,
    ZigbangItemsDetailV1ResponseModel,
    ZigbangManageCostEntryModel,
    ZigbangManageCostUsageFeeModel,
)
from jibsa.providers.zigbang.api.response.room.detail import (
    ZigbangBlsSchoolZonesV1ResponseModel,
    ZigbangItemDetailModel,
)
from jibsa.providers.zigbang.service.common.base import (
    DIRECTION_LABELS,
    NEAREST_SCHOOLS,
    SCHOOL_LOOKUP_ERRORS,
    ZigbangListingDetail,
    item_url,
    officetel_complex_id,
    school_label,
    sent_or_none,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.common.room import (
    trade_type_of,
)
from jibsa.providers.zigbang.service.region import to_int


# 기존 상세(/v3/items)의 주차 문장과 가능 여부
LEGACY_PARKING_AVAILABLE: dict[str, bool] = {'주차 가능': True, '주차 불가능': False, '주차 불가': False}
# 새 주거 상세가 아파트 매물에 주는 404 의 본문 code. 없는 매물의 404 는 code 가 없다 (2026-11-15 실측)
APT_DETAIL_NOT_SUPPORTED_CODE: str = 'ITEM_QUERY_DETAIL_SERVICE_TYPE_NOT_SUPPORTED'
# 정액 관리비 사용료 항목 (관리비 포함 항목 include 가 쓰는 이름, 응답에서 그 항목을 꺼내는 함수). 순서는 웹 매물 화면의
# 순서라 응답 모델의 필드 순서와 다르다. 필드를 직접 읽어 이름이 어긋나면 mypy 가 잡는다
USAGE_FEES: tuple[tuple[str, Callable[[ZigbangManageCostUsageFeeModel], ZigbangManageCostEntryModel | None]], ...] = (
    ('전기', lambda usage: usage.electricity),
    ('수도', lambda usage: usage.water),
    ('가스', lambda usage: usage.gas),
    ('난방', lambda usage: usage.heating),
    ('인터넷', lambda usage: usage.internet),
    ('TV', lambda usage: usage.tv),
)
NORMAL_MANAGE_COST_LABEL: str = '일반(공용) 관리비'
ETC_MANAGE_COST_LABEL: str = '기타 관리비'
# 웹 매물 화면의 관리비 항목 순서 (`getFixedManageCostDetailKeys`, 2026-11-15 번들). 웹은 include 목록도 이 이름 순서로
# 정렬하고, 이 이름이 아니면 원래 순서대로 뒤에 둔다. 웹의 기타 관리비 이름은 붙여 쓴 '기타관리비' 라, include 에
# 띄어 써 오는 '기타 관리비' 는 맨 뒤로 간다 (2026-11-15 실측: 50905571 의 include 가 일반·기타·인터넷·TV 순)
MANAGE_COST_ORDER: dict[str, int] = {
    name: index for index, name in enumerate((NORMAL_MANAGE_COST_LABEL, *(label for label, _ in USAGE_FEES), '기타관리비'))
}
FIXED_MANAGE_COST_TYPE: str = 'FixedManageCost'
UNKNOWN_MANAGE_COST_TYPE: str = 'UnknownManageCost'


def _distance_text(meters: int | None) -> str | None:
    if meters is None:
        return None
    return f'{meters}m' if meters < 1000 else f'{meters / 1000:.1f}km'


def building_schools(response: ZigbangBlsSchoolZonesV1ResponseModel) -> list[str]:
    """원룸·빌라·오피스텔 건물 학군을 `danji_schools` 와 같은 문구로 바꾼다 (거리는 m 정수로 온다)."""
    labels: list[str | None] = []
    if response.elementary:
        labels += [
            school_label(school.name, '배정', _distance_text(school.distance))
            for school in response.elementary.schools
        ]
    for level in (response.middle, response.high):
        if level:
            zone = level.school_zone.zone_name if level.school_zone else None
            nearest = sorted(level.schools, key=lambda school: school.distance if school.distance is not None else 10**9)
            labels += [
                school_label(school.name, zone, _distance_text(school.distance))
                for school in nearest[:NEAREST_SCHOOLS]
            ]
    return [label for label in labels if label]


def _usage_fee_items(usage: ZigbangManageCostUsageFeeModel | None) -> list[tuple[str, ZigbangManageCostEntryModel]]:
    """사용료 여섯 항목을 웹 순서로 (이름, 항목) 으로. 키가 빠진 항목은 웹처럼 해당 없음으로 본다."""
    return [
        (label, (entry_of(usage) if usage else None) or ZigbangManageCostEntryModel(type='not_applicable'))
        for label, entry_of in USAGE_FEES
    ]


def manage_cost_includes(manage: ZigbangItemsDetailV1ManageCostModel) -> list[str] | None:
    """관리비에 든 항목을 웹 매물 화면(`renderManageCostData`, 2026-11-15 번들)과 같은 규칙으로 고른다.

    `include` 목록은 실비로 따로 내는 사용료까지 포함으로 담는다. 웹은 정액 관리비(`FixedManageCost`)면 항목별로
    '일반(공용) 관리비 220,000원 / 전기 실비 …' 처럼 보여 주므로, 관리비 금액에 실제로 든 항목만 낸다: 금액이 있는
    일반(공용) 관리비, 정액 사용료 항목, 금액이 있는 기타 관리비. 실비·해당 없음·미제공 항목은 넣지 않는다.
    항목별 내역을 알리지 않았거나(`hasInformed` false, 또는 키가 없는데 여섯 항목이 모두 미제공·해당 없음) 실비 관리비이거나
    `detail` 이 없으면 웹처럼 `include` 목록을 `MANAGE_COST_ORDER` 순서로 정렬해 낸다. `hasInformed` 가 null 로 오면 웹처럼
    (`void 0===e.hasInformed` 는 null 이 아니다) 항목별로 본다. `detail` 이 없고 관리비 금액도 없으면(0·null) 웹은
    '관리비 없음' 만 보여 주고 항목을 그리지 않아 빈 목록이다. 정액 관리비의 항목도 웹 순서다
    (일반(공용) 관리비, 사용료, 기타 관리비). 확인 불가(`UnknownManageCost`)는 부르는 쪽(`detail_to_listing`)이 거른다.
    """
    listed = sent_or_none(manage, 'includes', sorted(
        (entry.name for entry in manage.includes if entry.name),
        key=lambda name: MANAGE_COST_ORDER.get(name, len(MANAGE_COST_ORDER)),
    ))
    detail = manage.detail
    if detail is None:
        # 웹(`!manageCost.amount`)처럼 `amount` 로 본다. `amount` 가 비고(0·null) `fee` 만 있는 매물은 `detail_to_listing` 이 먼저 모름으로 뺀다
        return listed if manage.amount else []
    # 리뷰 오탐 (2026-11-15): 실비 관리비(ActualManageCost)도 웹은 include 이름으로 포함 항목을 그린다. detailIncludes 는
    # '전기료'·'수도료' 처럼 이름이 달라 쓰면 웹과 어긋난다 (실측 50987398 웹 '일반(공용) 관리비, 전기, 수도, 가스, 기타 관리비'
    # = include. 실비 매물 6건 모두 두 목록의 항목은 같고 이름만 다름)
    if detail.type != FIXED_MANAGE_COST_TYPE:
        return listed
    usage = _usage_fee_items(detail.usage_fee)
    if detail.has_informed is False:
        return listed
    if 'has_informed' not in detail.model_fields_set and all(entry.type in ('unknown', 'not_applicable') for _, entry in usage):
        return listed
    includes: list[str] = []
    if detail.normal_manage_cost and (detail.normal_manage_cost.amount or 0) > 0:
        includes.append(NORMAL_MANAGE_COST_LABEL)
    includes += [label for label, entry in usage if entry.type == 'fixed' and (entry.amount or 0) > 0]
    etc = detail.etc_manage_cost
    if etc and not etc.is_unknown and (etc.amount or 0) > 0:
        # 리뷰 오탐 (2026-11-15): 중개사가 쓴 설명을 이름으로 내는 것이 맞다. 웹(`renderManageCostData`)도 '기타 관리비' 소제목
        # 아래 줄의 이름표로 description 을 쓴다 (실측 50893092: '주차비 5,000원')
        includes.append(etc.description or ETC_MANAGE_COST_LABEL)
    return includes


def _manage_cost_manwon(manage: ZigbangItemsDetailV1ManageCostModel) -> float | None:
    """주거 상세 관리비 금액 (만원). 웹 매물 화면의 관리비 절이 그리는 금액을 원 단위까지 낸다.

    내역이 있으면 웹(`renderManageCostData`, 2026-11-15 번들)처럼 정액 `totalAmount`·실비 `avgManageCost`(원)다. 웹은 `fee` 를
    읽지 않고, 내역이 없으면 `amount` × 10000 원을 그린다. `amount`(만원)는 직방이 0.1만원 아래를 버린 값이라(실측 51105591:
    amount 37.5, fee 375700) 그때는 목록 카드처럼 원 단위 `fee` 를 쓴다 (개발 가이드 "웹과 다른 점"). 원 단위 금액이 없을 때만
    `amount` 다. 내역이 없고 금액도 없으면(0·null) 웹은 '관리비 없음' 이라 0 이다 (포함 항목도 빈 목록, `manage_cost_includes`).
    """
    detail = manage.detail
    if detail is not None:
        won = detail.total_amount if detail.type == FIXED_MANAGE_COST_TYPE else detail.avg_manage_cost
        if won is not None:
            return won_to_manwon(won)
    if manage.fee is not None:
        return won_to_manwon(manage.fee)
    return (manage.amount or 0) if detail is None else manage.amount


def detail_to_listing(
    response: ZigbangItemsDetailV1ResponseModel,
    *,
    legacy: ZigbangItemDetailModel | None = None,
    registered_at: str | None = None,
    short_term: bool = False,
) -> ZigbangListingDetail:
    """새 주거 상세(`/items/{id}/detail`) 응답을 `ZigbangListingDetail` 로 바꾼다 (원룸·빌라·오피스텔).

    사진·본문·중개사 정보는 응답에 있어도 옮기지 않는다 (원 사이트에서 확인).
    입주일(`moveInAt`)이 null 이면 기존 상세(`/v3/items`, `legacy`)의 입주 문구로 보완하고, 그때는 주차도
    기존 상세의 문구를 쓴다. 상세 응답에는 등록일이 없어 요약 응답의 `reg_date` 를 `registered_at` 으로 받는다.
    없으면 모름(None). 단기임대 여부도 상세 응답에는 없어 요약 응답(`trade_type_of`)에서 `short_term` 으로 받는다.
    관리비가 확인 불가(`UnknownManageCost`)면 웹처럼 금액도 항목도 모름(None)이다. 금액은 `_manage_cost_manwon` 이 정한다.
    """
    item = response.item
    residence = item.residence
    price = item.price
    manage = item.manage_cost
    if manage is not None and manage.detail is not None and manage.detail.type == UNKNOWN_MANAGE_COST_TYPE:
        # 웹은 '관리비 확인 불가' 로 보여 주고 금액도 항목도 내지 않는다
        manage = None
    if manage is not None and manage.detail is None and not manage.amount and manage.fee:
        # 내역이 없으면 웹은 `amount` 만 보고(0·null) '관리비 없음' 으로 보여 주는데 `fee` 에는 금액이 있다. 어느 쪽이 맞는지
        # 몰라 틀릴 수 있는 금액을 내지 않고 금액도 항목도 모름(None)이다 (2026-11-15 사용자 결정)
        manage = None
    manage_cost = _manage_cost_manwon(manage) if manage is not None else None
    origin = item.address.origin
    address = origin.full_text if origin else None
    if item.address.jibun and origin and origin.local1:
        address = f'{origin.local1} {item.address.jibun}'
    move_in: str | None
    if residence.move_in_at is not None:
        extra = residence.move_in_extra
        move_in = move_in_label(f'{residence.move_in_at} ({extra})' if extra else residence.move_in_at)
    else:
        # null을 즉시 입주로 추측하지 않고 기존 상세의 문장('즉시 입주 가능 (협의 가능)')을 같은 꼴로 바꿔 쓴다
        move_in = move_in_label(legacy.movein_date) if legacy else None
    parking = parking_label(residence.parking)
    if parking is None and legacy is not None and legacy.parking_available_text is not None:
        # 기존 상세는 '주차 가능'·'주차 불가능' 문장으로 준다 (2026-10-15 실측 6건). 다른 문장이면 그대로 둔다
        text = legacy.parking_available_text
        parking = parking_label(LEGACY_PARKING_AVAILABLE.get(text)) or text

    detail = ZigbangListingDetail(
        source='zigbang',
        id=str(item.id),
        url=item_url(item.service_type, item.id),
        trade_type='단기임대' if short_term and item.sales_type == '월세' else item.sales_type,
        property_type=item.service_type,
        room_type=residence.room_type,
        title=item.title,
        price_manwon=price.sales if price and item.sales_type == '매매' else None,
        deposit_manwon=price.deposit if price and item.sales_type != '매매' else None,
        rent_manwon=price.rent if price and item.sales_type == '월세' else None,
        manage_cost_manwon=manage_cost,
        area_m2=residence.area_m2,
        area_pyeong=m2_to_pyeong(residence.area_m2),
        floor=residence.floor,
        building_floor=residence.building_floor,
        address=address,
        lat=item.location.lat if item.location else None,
        lng=item.location.lng if item.location else None,
        registered_at=normalize_date(registered_at),
        bathroom_count=to_int(residence.bathroom_count),
        direction=DIRECTION_LABELS.get(residence.direction or '', residence.direction),
        move_in=move_in,
        approved_at=normalize_date(residence.approved_at),
        parking=parking,
        elevator=residence.elevator,
        options=sent_or_none(item, 'options', [option.name for option in item.options if option.name]),
        manage_cost_includes=manage_cost_includes(manage) if manage else None,
        nearby_subways=sent_or_none(response, 'subways', [
            f'{subway.name} ({subway.description})' if subway.description else subway.name
            for subway in response.subways
        ]),
        # 표시 문구를 정규화하지 않는다. 코드는 원룸·빌라가 대부분 '그외'라 문구가 더 정확하다 (2026-10-10 실측).
        # 원본 문구 끝에 공백이 붙어 오기도 해('주택   ') 앞뒤 공백만 뗀다
        residence_type=(residence.residence_description or residence.residence_type or '').strip() or None,
        total_parking_count=residence.total_parking_count,
        household_count=residence.household_count,
        direction_criterion=residence.direction_criterion,
    )
    if item.service_type == '오피스텔':
        return detail.model_copy(update={
            'complex_id': officetel_complex_id(item.building_id) if item.building_id else None,
            'complex_name': response.danji.name if response.danji else None,
        })
    return detail


def get_listing(client: ZigbangClient, item_id: int) -> ZigbangListingDetail | None:
    """숫자 ID 매물의 상세를 조회한다. 원룸·빌라·오피스텔은 새 주거 상세 + 등록일·단기임대 요약이고, 입주일이 null 이면
    기존 상세 1회, 필지가 있으면 건물 학군 1회를 더한다 (학군은 실패하면 모름).

    새 주거 상세는 아파트 매물에 본문 code 가 `APT_DETAIL_NOT_SUPPORTED_CODE` 인 404 를 준다. 그때는 아파트 상세를 부르지 않고
    None 을 돌려준다. 웹 아파트 매물 화면처럼 아파트 상세 1회로 만드는 일은 분기 모듈 `listing` 의 `get_listing`(라이브러리 입구,
    `get_any_listing` 의 숫자 ID 갈래도 이것을 부른다)이 맡는다 (기능 모듈끼리는 서로 가져다 쓰지 않는다).

    Returns:
        매물 상세. 새 주거 상세가 아파트 매물이라고 알리면 None.

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 상태가 open 이 아닐 때 (상태가 없을 때 포함).
        JibsaError: 거래 중인 매물인데 거래 유형·매물 유형이 없을 때 (PARSE_ERROR).
    """
    structured: ZigbangItemsDetailV1ResponseModel | None
    with unavailable_on_404(item_id):
        try:
            structured = client.run_request_items_detail_v1(
                ZigbangItemsDetailV1RequestParameterModel(item_id=item_id)
            )
        except HTTPStatusError as exc:
            # 리뷰 오탐 (2026-11-15): 주거 상세는 아파트 매물에 200 을 주지 않고 이 code 의 404 만 준다 (실측 51174606·51183455).
            # 200 이 오면 엔드포인트 동작이 바뀐 것이라(매일 API 감시가 볼 일) 아파트 여부를 다시 확인하는 가드는 두지 않는다
            if exc.response.status_code != 404 or (error_body(exc) or {}).get('code') != APT_DETAIL_NOT_SUPPORTED_CODE:
                raise
            structured = None
    if structured is None:
        return None
    if structured.item.status != 'open':
        raise ListingUnavailableError('zigbang', item_id, status=structured.item.status)
    # 내려간 매물 안내가 먼저다. 살아 있는 매물인데 유형이 없으면 거래·매물 유형과 url 을 만들 수 없다
    missing = [
        name for name, value in (('salesType', structured.item.sales_type), ('serviceType', structured.item.service_type))
        if value is None
    ]
    if missing:
        raise JibsaError(
            code='PARSE_ERROR',
            message=f"직방 매물 상세(/items/{item_id}/detail)에 없는 필드: {', '.join(missing)}",
            hint='비공식 API 응답 형식이 바뀌었을 수 있습니다. 다른 소스를 쓰세요',
            details={'item_id': item_id},
        )
    residence = structured.item.residence
    legacy = None
    if residence.move_in_at is None:
        # null을 즉시 입주로 추측하지 않고 기존 API의 설명으로 보완한다.
        # 실측: 두 API 의 status 는 늘 같다(open·close·cancel).
        with unavailable_on_404(item_id):
            legacy = client.run_request_items_v3(ZigbangItemsV3RequestParameterModel(item_id=item_id))
        if legacy.item.status != 'open':
            raise ListingUnavailableError('zigbang', item_id, status=legacy.item.status)
    # 상세에는 등록일과 단기임대 여부가 없어 목록과 같은 값(reg_date, contract)을 요약 API 에서 받아 온다.
    # 요약의 status(노출 여부)는 다시 보지 않는다. 2026-10-10 실측 180건: 요약 true ↔ 상세 open,
    # false ↔ close·cancel, 요약 없음 ↔ 404 로 늘 같았다
    summaries = client.run_request_items_list_v1(
        ZigbangItemsListV1RequestPayloadModel(item_ids=[item_id])
    )
    summary = next((summary for summary in summaries.items if summary.item_id == item_id), None)
    schools = None
    pnu = structured.item.address.pnu
    if pnu:
        try:
            schools = building_schools(client.run_request_bls_school_zones_v1(
                ZigbangBlsSchoolZonesV1RequestParameterModel(pnu=pnu)
            ))
        except SCHOOL_LOOKUP_ERRORS:
            # 학군을 못 받아도 매물 상세는 돌려준다 (모름)
            schools = None
    detail = detail_to_listing(
        structured,
        legacy=legacy.item if legacy else None,
        registered_at=summary.reg_date if summary else None,
        short_term=summary is not None and trade_type_of(summary) == '단기임대',
    )
    return detail if schools is None else detail.model_copy(update={'schools': schools})
