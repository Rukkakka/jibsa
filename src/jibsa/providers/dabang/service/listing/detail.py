"""매물 상세 (listing)."""
from datetime import datetime

from httpx import HTTPStatusError

from jibsa.core.dates import (
    KST,
    holding_unread_dates,
    keep_unread_dates,
    read_date,
    years_ago,
)
from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    Listing,
    listing_as,
    m2_to_pyeong,
    move_in_label,
    parking_label,
    won_to_manwon,
)
from jibsa.core.notes import (
    LookupFailures,
    lookup_failure_reason,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.listing import (
    DabangNewRoomDetailV3RequestParameterModel,
    DabangRoomGetRoomIdV3RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.listing import (
    DabangNewRoomDetailRoomModel,
)
from jibsa.providers.dabang.service.common.constants import (
    LISTING_URL,
    OPTIONAL_LOOKUP_ERRORS,
    SOURCE,
)
from jibsa.providers.dabang.service.common.error import is_missing_id
from jibsa.providers.dabang.service.common.models import DabangListing
from jibsa.providers.dabang.service.common.room import room_type_of
from jibsa.providers.dabang.service.common.text import (
    floor_label,
    manwon_from_text,
)
from jibsa.providers.dabang.service.listing.constants import (
    AIR_CONDITIONER_OPTIONS,
    COMMON_FEE_CODE,
    DETAIL_INPUT_TYPE,
    DETAILS_MAX,
    ELEVATOR_BY_TEXT,
    ETC_FEE_CHARGE,
    FIXED_FEE_CHARGE,
    FIXED_FEE_ITEM_LABELS,
    FIXED_FEE_TYPE,
    HIDDEN_STATUSES,
    ITEMIZED_FIXED_FEE_DETAIL_TYPE,
    LISTING_NUMBER_PATTERN,
    MANAGE_CHARGE_TYPE_LABELS,
    MANAGE_ITEM_LABELS,
    TRADE_BY_SELLING_CODE,
)
from jibsa.providers.dabang.service.listing.models.common import DabangSearchResult
from jibsa.providers.dabang.service.listing.models.detail import (
    DabangDetailedListing,
    DabangListingDetail,
)

from typing import NamedTuple


class _ManageCost(NamedTuple):
    manwon: float | None
    includes: list[str] | None
    excludes: list[str] | None
    # 정액관리비 항목 목록에서 뺀 빈 항목 수 (뺐으면 포함·실비 항목을 모른다)
    dropped: int = 0


def _manage_cost(room: DabangNewRoomDetailRoomModel) -> _ManageCost:
    """월 관리비(만원), 포함 항목, 실비로 따로 내는 항목. 웹 관리비 칸과 상세보기(safety-option-chunk `E`, room-chunk)를 따른다.

    관리비가 '없음' 이면 0 과 포함 항목 [], 금액은 있는데 항목을 모르면 항목 None. 실비 항목은 정액관리비를 항목마다 적은
    매물만 안다.
    """
    if room.maintenance_cost is None:
        if (room.maintenance_cost_str or '').strip() == '없음':
            return _ManageCost(0.0, [], None)
        return _ManageCost(None, None, None)
    cost = won_to_manwon(room.maintenance_cost)
    if room.maintenance_input_type != DETAIL_INPUT_TYPE:
        # 웹은 세부 입력이 아닌 매물(입력 방식이 없으면 SIMPLE 로 본다)에 포함 항목 글만 괄호로 보여 준다
        return _ManageCost(cost, list(room.maintenance_items_str) or None, None)
    charge = room.maintenance_charge_type
    fixed_items = room.maintenance_fixed_fee_charge_detail_list
    detail_type = room.maintenance_charge_detail_type
    if charge == FIXED_FEE_CHARGE and (not detail_type or detail_type == ITEMIZED_FIXED_FEE_DETAIL_TYPE):
        dropped = room.null_items('maintenance_fixed_fee_charge_detail_list')
        if dropped:
            # 뺀 항목이 포함인지 실비인지 모르니 받은 항목만으로 포함·실비 목록을 만들면 틀린 목록이 완전한 값처럼 나간다
            return _ManageCost(cost, None, None, dropped)
        if not fixed_items:
            return _ManageCost(cost, None, None)
        # 항목마다 정액(관리비에 듦)·실비(따로 냄)로 온다. 공용(F01)은 실비로 와도 웹이 금액과 함께 보여 주고 관리비 합계에 넣어
        # 든 항목으로 본다. 예전에는 정액 항목만 넣어, 공용이 실비로 온 매물이 '포함 항목 없음' 으로 읽혔다 (2026-11-13 웹 대조:
        # 6ae45e683b53321aea64a773 관리비 20만원, 상세보기 '공용 200,000원 · 사용료 실비')
        includes: list[str] = []
        excludes: list[str] = []
        for item in fixed_items:
            included = item.detail_code == COMMON_FEE_CODE or item.detail_cost_formulated_type == FIXED_FEE_TYPE
            (includes if included else excludes).append(FIXED_FEE_ITEM_LABELS.get(item.detail_code, item.detail_code))
        return _ManageCost(cost, includes, excludes)
    if charge in (FIXED_FEE_CHARGE, ETC_FEE_CHARGE) and room.maintenance_etc_fee_charge_detail is not None:
        # 10만원 미만·세부 미고지 정액관리비와 기타부과는 '포함 항목' 코드만 온다. 따로 내는 항목은 웹도 보여 주지 않는다
        # 포함 항목 코드를 주지 않으면 모름(None), 빈 목록이면 비어 있음([])이다 (항목별 분기와 같다)
        codes = room.maintenance_etc_fee_charge_detail.detail_include_types
        return _ManageCost(cost, None if codes is None else [MANAGE_ITEM_LABELS.get(code, code) for code in codes], None)
    # 확인불가는 웹도 항목을 보여 주지 않는다
    return _ManageCost(cost, None, None)


def resolve_listing_id(client: DabangClient, listing_ref: str) -> str:
    """매물 ID 를 그대로, 매물번호(숫자)는 매물 ID 로 바꿔 돌려준다 (요청 1회).

    Raises:
        ListingUnavailableError: 매물번호에 해당하는 매물이 없을 때.
    """
    if not LISTING_NUMBER_PATTERN.fullmatch(listing_ref):
        return listing_ref
    try:
        found = client.run_request_room_get_room_id_v3(DabangRoomGetRoomIdV3RequestParameterModel(seq=int(listing_ref)))
    except HTTPStatusError as exc:
        if is_missing_id(exc, in_path=False):
            # 400 '존재하지 않는 방입니다.' 는 없는 번호라 사유를 넘기지 않는다. 사유가 있으면 다른 소스 ID 힌트가 빠진다
            # (2026-10-25 실측: 직방 ID 47123456 을 넣으면 이 응답)
            raise ListingUnavailableError(SOURCE, listing_ref) from None
        raise
    if not found.room_id:
        raise ListingUnavailableError(SOURCE, listing_ref)
    # 응답 room_id 를 그대로 상세 요청(24자리 16진수)에 넣는다. 매물 ID 꼴로만 와서 형식을 따로 막지 않는다 (core/schema.py,
    # 2026-10-26 실측: 매물번호 55861462 → 69aa437a89300d7e5b7251a9)
    return found.room_id


def get_listing(client: DabangClient, listing_ref: str) -> DabangListingDetail:
    """매물 상세 (요청 1회, 매물번호면 2회). 본문·중개사·사진·좌표는 옮기지 않는다.

    Raises:
        ListingUnavailableError: 없는 매물(400 "존재하지 않는 매물입니다."), 비공개(status 0·3·4), 계약 완료,
            모르는 거래 유형.
    """
    room_id = resolve_listing_id(client, listing_ref)
    try:
        response = client.run_request_new_room_detail_v3(DabangNewRoomDetailV3RequestParameterModel(room_id=room_id))
    except HTTPStatusError as exc:
        if is_missing_id(exc, in_path=False):
            # 400 '존재하지 않는 매물입니다.' 도 없는 ID 라 사유를 넘기지 않는다 (`resolve_listing_id` 와 같다)
            raise ListingUnavailableError(SOURCE, listing_ref) from None
        raise
    room = response.room
    if room.status in HIDDEN_STATUSES:
        raise ListingUnavailableError(SOURCE, listing_ref, status=str(room.status))
    if room.is_contract:
        raise ListingUnavailableError(SOURCE, listing_ref, status='contract')
    trade_type = TRADE_BY_SELLING_CODE.get(room.selling_type if room.selling_type is not None else -1)
    if trade_type is None:
        raise ListingUnavailableError(SOURCE, listing_ref, reason='UNKNOWN_TRADE_TYPE')
    manage = _manage_cost(room)
    charge = room.maintenance_charge_type
    parking_count = room.parking_num
    # 웹은 이 표시들이 없으면(null) 없는 것으로 보고 아무것도 보여 주지 않는다 (safety-option-chunk 의 `?? false`). 위반건축물만
    # null 이면 그 줄을 감추고 true·false 를 '해당'·'해당없음' 으로 보여 준다 (room-chunk, 2026-11-13)
    with_tenant = bool(room.is_take_tenant)
    notes = [null_items_note('다방 관리비 항목', manage.dropped, ('manage_cost_includes', 'manage_cost_excludes'))] if manage.dropped else []
    # 세입자 낀 매매의 기존 보증금/월세 글('20억', '1억/50')을 만원으로. 읽지 못하면 둘 다 None (모름)이고, with_tenant 가 거짓이면 글을 읽지 않는다.
    # 리뷰 오탐 (2026-11-14): 이 계산은 금액 글자 읽기를 manwon_from_text 하나에 맡기고 거래 유형 없이 조각 수로 보증금/월세를
    # 정해(읽지 못하면 두 키 null) listing_prices(거래 유형별, 못 읽으면 None)와 계약이 다르다.
    tenant_prices: dict[str, float | None] = {}
    if with_tenant:
        tenant_values = [manwon_from_text(part) for part in (room.take_tenant_price_title or '').split('/')]
        if len(tenant_values) == 1 and tenant_values[0] is not None:
            tenant_prices = {'tenant_deposit_manwon': tenant_values[0]}
        elif len(tenant_values) == 2 and None not in tenant_values:
            tenant_prices = {'tenant_deposit_manwon': tenant_values[0], 'tenant_rent_manwon': tenant_values[1]}
        else:
            tenant_prices = {'tenant_deposit_manwon': None, 'tenant_rent_manwon': None}
    # `price_info` 에서 그 거래 유형 칸의 금액. 칸은 [보증금 또는 매매가, 월세, 거래 유형 코드] 다.
    # 맞는 칸이 없으면 금액을 모름(null)으로 둔다. 다른 거래 유형 칸의 금액을 이 거래의 가격으로 내지 않는다
    # (2026-10-26 실측: 역삼동 빌라 월세 1건·전세 2건 모두 거래 유형 코드가 맞는 칸 하나뿐).
    price_entry = next((row for row in room.price_info if len(row) >= 3 and int(row[2]) == room.selling_type), None)
    prices: dict[str, float] = {}
    if price_entry is not None:
        if trade_type == '월세':
            prices = {'deposit_manwon': price_entry[0], 'rent_manwon': price_entry[1]}
        elif trade_type == '전세':
            prices = {'deposit_manwon': price_entry[0]}
        else:
            prices = {'price_manwon': price_entry[0]}
    return DabangListingDetail(
        source=SOURCE,
        id=room.id,
        url=LISTING_URL.format(room.id),
        trade_type=trade_type,
        property_type=room.room_type_str or '매물',
        room_type=room_type_of(room.room_type_str),
        title=room.title,
        manage_cost_manwon=manage.manwon,
        manage_cost_includes=manage.includes,
        manage_cost_charge_type=MANAGE_CHARGE_TYPE_LABELS.get(charge, charge) if charge else None,
        manage_cost_excludes=manage.excludes,
        area_m2=room.room_size,
        area_pyeong=m2_to_pyeong(room.room_size),
        # 오피스텔은 공급면적 칸에 0 을 주기도 한다 (2026-10-26 실측: 강남역투웨니퍼스트 6ad6eb6fcac3561f038ec567). 모름이다
        supply_area_m2=room.provision_size or None,
        # 다른 유형은 계약면적을 0 으로 준다. 웹은 오피스텔에 '전용/계약면적' 으로 보여 준다 (room-chunk)
        contract_area_m2=room.contract_size or None,
        with_tenant=with_tenant,
        **tenant_prices,
        lh_jeonse=bool(room.is_lh_lease),
        leasehold_registration=bool(room.is_leasehold),
        unregistered_building=bool(room.is_new_construction),
        non_compliant_building=room.is_non_compliant_building,
        floor=floor_label(room.room_floor_str),
        building_floor=floor_label(room.building_floor_str),
        address=room.full_jibun_address_str,
        registered_date=read_date(room.saved_time_str, '등록일'),
        approved_date=read_date(room.building_approval_date_str, '사용승인일'),
        room_count=room.beds_num,
        bathroom_count=room.bath_num,
        direction=room.direction_str,
        direction_criterion=room.direction_measurement_base_type_str,
        move_in=move_in_label(room.moving_date),
        parking=parking_label(room.parking, f'총 {parking_count:g}대' if parking_count else None),
        has_elevator=ELEVATOR_BY_TEXT.get(room.elevator_str or ''),
        options=None if room.room_options is None else [
            f'{option.name} 에어컨' if option.name in AIR_CONDITIONER_OPTIONS else option.name for option in room.room_options
        ],
        safety=None if room.safeties is None else [safety.name for safety in room.safeties],
        heating=room.heating,
        residence_type=', '.join(room.building_use_types_str) or None,
        loan=None if room.loan_str in (None, '', '-') else room.loan_str,
        short_term_period=room.short_lease_str,
        complex_id=room.complex_id,
        listing_number=room.seq,
        notes=notes,
        **prices,
    )


def attach_details(
    client: DabangClient,
    result: DabangSearchResult,
    *,
    built_within_years: int | None = None,
) -> DabangSearchResult:
    """목록 앞 `DETAILS_MAX` 건에 상세(`get_listing`, 1회씩)의 사용승인일과 건물 용도를 붙인다 (`--details`).

    목록 칸에는 사용승인일이 없어 `--built-within`(연도로 센다) 결과를 날짜로 따지려면 매물마다 상세를 열어야 했다
    (2026-10-31 에이전트 검증: opus 두 번 모두 역삼동 원룸 17건의 상세를 하나씩 불렀다). 상세에서 내려간 매물은 뺀다
    (만료 매물은 내보내지 않는다). 31번째부터는 사용승인일·건물 용도를 모름(null)으로 둔다.

    상세 한 건이 만료 말고 다른 이유로 실패해도(요청 제한·서버 오류·응답 형식 변경, `OPTIONAL_LOOKUP_ERRORS`) 이미 받은 목록을
    버리지 않는다 (2026-11-19 리뷰). 그 매물은 목록 값 그대로 두고 사용승인일·건물 용도만 31번째부터와 같이 모름(null)이며,
    `[실패]` 안내 하나에 건수와 이유(거절·응답 형식 변경이 한 건이라도 있으면 그 이유(요청 제한도 왔으면 덧붙임), 없으면
    요청 제한, 없으면 첫 실패 이유. `LookupFailures`)를 적는다. 요청 제한이면 다음 요청도 같은
    제한에 걸리므로 (앞에 다른 실패가 있었어도) 남은 매물은 요청하지 않고 같이 목록 값으로 둔다.
    `built_within_years` 를 주면 오늘 기준 그 햇수가 넘은 매물을 승인일과 함께 `notes` 로 짚는다 (빼지는 않는다. 서버 필터
    결과라 다시 거르지 않는다). 연도 기준 안내만 보고 2016-02 승인 건물을 '10년 이내' 로 추천한 일이 있었다 (2026-10-31 재검증).
    """
    listings: list[Listing] = []
    gone = 0
    failures = LookupFailures()
    for index, listing in enumerate(result.listings):
        if not isinstance(listing, DabangListing):
            listings.append(listing)
            continue
        if index >= DETAILS_MAX:
            listings.append(listing_as(DabangDetailedListing, listing))
            continue
        if failures.stopped:
            # 요청 제한에 걸렸으면 다음 요청도 같은 제한에 걸린다
            failures.skip()
            listings.append(listing_as(DabangDetailedListing, listing))
            continue
        try:
            with holding_unread_dates() as dates:
                detail = get_listing(client, listing.id)
        except ListingUnavailableError:
            gone += 1
            continue
        except OPTIONAL_LOOKUP_ERRORS as exc:
            failures.add(exc)
            listings.append(listing_as(DabangDetailedListing, listing))
            continue
        dated = listing.model_copy(update={'approved_date': detail.approved_date or listing.approved_date})
        # 결과에 옮기는 칸은 사용승인일뿐이라 그 칸이 null 로 나갈 때만 알린다
        if dated.approved_date is None:
            keep_unread_dates(dates, only=('사용승인일',))
        listings.append(listing_as(DabangDetailedListing, dated, residence_type=detail.residence_type))
    notes = []
    if gone:
        # 검색이 만든 안내('이 N건이 전부입니다' 등)는 빼기 전 개수라 returned 와 다를 수 있다
        notes.append(note('제외', f'{gone}건은 상세를 보니 거래가 끝나 뺐습니다 (앞 안내의 건수는 빼기 전 기준)'))
    reason = failures.reason(lambda exc: lookup_failure_reason(exc, '다방', '매물 상세'))
    if reason is not None:
        notes.append(note(
            '실패',
            f'매물 {failures.count}건의 상세(사용승인일·건물 용도)를 받지 못해 목록 값만 넣었습니다: {reason}',
        ))
    if len(result.listings) > DETAILS_MAX:
        notes.append(f'사용승인일·건물 용도(--details)는 앞 {DETAILS_MAX}건에만 붙였습니다')
    if built_within_years is not None:
        cutoff = years_ago(datetime.now(KST).date(), built_within_years)
        older = [listing for listing in listings if listing.approved_date and listing.approved_date < cutoff]
        if older:
            notes.append(note(
                '참고',
                f'이 중 {len(older)}건은 오늘 기준 {built_within_years}년이 넘었습니다 ({cutoff} 전 승인): '
                + ', '.join(f'{listing.id}({listing.approved_date})' for listing in older),
            ))
    return result.model_copy(update={'listings': listings, 'returned': len(listings), 'notes': result.notes + notes})
