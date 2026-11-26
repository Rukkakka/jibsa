"""단기임대 상세 (listing stay-*): 상세·후기 요약·임대인의 다른 방·예약 가능 여부."""

from datetime import (
    date,
    datetime,
    timedelta,
)

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    KST,
    ListingDetail,
    NumberRange,
    lookup_failure_note,
    m2_to_pyeong,
    null_items_note,
    number_range,
    read_date,
    won_to_manwon,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.stay.base import (
    ZigbangGuestItemsByIdsRequestParameterModel,
    validate_stay_dates,
)
from jibsa.providers.zigbang.api.request.stay.detail import (
    ZigbangGuestItemsHostRequestParameterModel,
    ZigbangGuestItemsRequestParameterModel,
    ZigbangGuestItemsReviewsRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.stay.detail import (
    ZigbangGuestItemsResponseModel,
    ZigbangStayScheduleModel,
)
from jibsa.providers.zigbang.service.common.base import (
    OPTIONAL_LOOKUP_ERRORS,
    sent_or_none,
    text_or_none,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.stay.base import (
    STAY_BUILDING_TYPE_LABELS,
    STAY_OPTION_LABELS,
    ZigbangStayListing,
    stay_discounts,
    stay_item_url,
    stay_summary_to_listing,
)

from typing import (
    Annotated,
    Any,
    Self,
)


STAY_REFUND_POLICY_LABELS: dict[str, str] = {
    'FLEXIBLE': '유연',
    'STANDARD': '표준',
    'STRICT': '엄격',
}
# 위약금 표. 직방 응답은 정책 이름(refundPolicy)만 주고 표는 웹 번들(`RefundPolicySection`)에 고정돼 있어 옮겨 적은 것이다
# (2026-11-17). 직방이 표를 바꾸면 주 1회 감시(`scripts/monitor/api_check.py` 의 `WEEKLY_CHECKS`)가 알린다. 값은 (취소 시점,
# 위약금) 다섯 쌍이고 글자는 웹 표기 그대로다
STAY_REFUND_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    'FLEXIBLE': (
        ('입주 14일전', '없음'),
        ('입주 7일전', '임대료의 15%'),
        ('입주 3일전', '임대료의 30%'),
        ('입주 1일전', '임대료의 40%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STANDARD': (
        ('입주 14일전', '임대료의 10%'),
        ('입주 7일전', '임대료의 30%'),
        ('입주 3일전', '임대료의 40%'),
        ('입주 1일전', '임대료의 50%'),
        ('입주 당일 이후', '취소불가'),
    ),
    'STRICT': (
        ('입주 14일전', '임대료의 20%'),
        ('입주 7일전', '임대료의 50%'),
        ('입주 3일전', '임대료의 60%'),
        ('입주 1일전', '임대료의 70%'),
        ('입주 당일 이후', '취소불가'),
    ),
}
STAY_PARKING_METHOD_LABELS: dict[str, str] = {
    'SELF': '자주식',
    'MECHANICAL': '기계식',
}
# 입주·퇴실 방식 (웹 표기. 모르는 코드는 웹도 그대로 쓴다)
STAY_CHECK_METHOD_LABELS: dict[str, str] = {
    'SELF': '비대면',
    'MEET': '임대인 대면',
    'KEYBOX': '키박스',
}
# 달력에서 막힌 날의 종류. 웹이 날짜를 막는 일정 종류(STAY_UNAVAILABLE_SCHEDULES)가 이 표의 키라 한쪽만 고치지 않는다
STAY_SCHEDULE_KIND_LABELS: dict[str, str] = {
    'RESERVED': '예약',
    'BLOCKED': '막힘',
}
# 상세에 싣는 '임대인의 다른 방' 수. 웹은 모두 받아 가로 카드로 보여 주지만 jibsa 는 앞쪽만 내고 전체 수를 따로 알린다
STAY_HOST_OTHER_LIMIT: int = 10
# 웹 날짜 고르기 창이 받는 가장 늦은 마지막 날은 입주일 + 83일이다 (번들 `getMaxCheckOut`)
STAY_MAX_CHECK_OUT_DAYS: int = 83
# 웹이 날짜를 막는 일정 종류 (번들 `isUnavailableSchedule`). 이름 표(STAY_SCHEDULE_KIND_LABELS)의 키와 같아 표를 고치면 따라간다
STAY_UNAVAILABLE_SCHEDULES: frozenset[str] = frozenset(STAY_SCHEDULE_KIND_LABELS)


class ZigbangStayRefundRule(BaseModel):
    """위약금 표의 한 행. 직방 웹 위약금 정보 표와 같다."""

    when: Annotated[
        str,
        Field(description="취소 시점 (예: '입주 7일전')")
    ]
    penalty: Annotated[
        str,
        Field(description="위약금 (예: '임대료의 30%', '없음', '취소불가')")
    ]


class ZigbangStayUnavailablePeriod(BaseModel):
    """예약할 수 없는 기간 하나."""

    start_date: Annotated[
        str,
        Field(description='시작일 (YYYY-MM-DD)')
    ]
    end_date: Annotated[
        str,
        Field(description='끝날 (YYYY-MM-DD, 이 날까지 막힌다)')
    ]
    kind: Annotated[
        str,
        Field(description="종류 ('예약' 다른 손님이 예약함, '막힘' 임대인이 막음)")
    ]


class ZigbangStayListingDetail(ListingDetail):
    """상세 조회로 보강한 직방 단기임대 매물. 입주일·마지막 날을 주면 예약 가능 여부(`available`)가 붙는다.

    `notes`: 후기 요약·임대인의 다른 방 조회가 실패했다는 안내와, 직방이 빈 항목을 줘 모름(null)으로 둔 칸의 안내. CLI 가 결과 위에 붙인다
    """

    weekly_rent_manwon: Annotated[
        float | None,
        Field(description='주당 임대료 (만원)')
    ] = None
    weekly_manage_cost_manwon: Annotated[
        float | None,
        Field(description='주당 관리비 (만원). 관리비가 없으면 0')
    ] = None
    cleaning_fee_manwon: Annotated[
        float | None,
        Field(description='청소비 (만원). 무료면 0')
    ] = None
    discounts: Annotated[
        list[str] | None,
        Field(description='할인 조건')
    ] = None
    contract_weeks_range: Annotated[
        NumberRange | None,
        Field(description='계약할 수 있는 주 수 범위 (lowest 최소, highest 최대). 직방이 한쪽만 주면 그 끝만 null, 둘 다 주지 않으면 null')
    ] = None
    max_guests: Annotated[
        int | None,
        Field(description='최대 인원')
    ] = None
    duplex: Annotated[
        bool | None,
        Field(description='복층 여부')
    ] = None
    refund_policy: Annotated[
        str | None,
        Field(description='환불 정책 (유연, 표준, 엄격. 직방 웹 위약금 정보의 이름)')
    ] = None
    refund_rules: Annotated[
        list[ZigbangStayRefundRule] | None,
        Field(description='위약금 표 (취소 시점별 위약금 5행, 직방 웹 위약금 정보 표와 같다). 정책을 모르거나 표에 없는 정책이면 null')
    ] = None
    kitchen_count: Annotated[
        int | None,
        Field(description='주방 수. 0 이면 0')
    ] = None
    living_room_count: Annotated[
        int | None,
        Field(description='거실 수. 0 이면 0')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='주차 대수. 주차 불가면 키가 없고, 가능한데 직방이 대수를 주지 않으면 null')
    ] = None
    parking_method: Annotated[
        str | None,
        Field(description="주차 방식 ('자주식', '기계식'). 주차 불가면 키가 없고, 직방이 주지 않으면 null")
    ] = None
    pet_allowed: Annotated[
        bool | None,
        Field(description=(
            '반려동물 동반 가능 여부 (직방 웹 옵션의 반려동물 분류. options 에는 들어 있지 않다). '
            '직방이 옵션 목록을 주지 않으면 null (직방 웹은 이때 동반 불가로 그린다). 직방이 옵션 목록에 빈 항목을 줘 반려동물 분류가 '
            '없다고 단정할 수 없을 때도 null'
        ))
    ] = None
    pet_cleaning_fee_manwon: Annotated[
        float | None,
        Field(description=(
            '반려동물을 데려올 때 추가 청소비 (만원). 직방 웹은 동반 가능 여부와 상관없이 0 보다 크면 보여 준다. '
            '동반 가능이면 0 이면 0, 직방이 주지 않으면 null. 동반 불가면 0 보다 클 때만 값이 있고 아니면 키가 없다. '
            '동반 가능 여부를 모를 때(pet_allowed null)는 0 보다 크면 그 값, 아니면 null'
        ))
    ] = None
    check_in_time: Annotated[
        str | None,
        Field(description="입주 시각 ('15:00')")
    ] = None
    check_out_time: Annotated[
        str | None,
        Field(description="퇴실 시각 ('11:00')")
    ] = None
    check_in_method: Annotated[
        str | None,
        Field(description="입주 방식 ('비대면', '임대인 대면', '키박스')")
    ] = None
    check_out_method: Annotated[
        str | None,
        Field(description="퇴실 방식 ('비대면', '임대인 대면', '키박스')")
    ] = None
    unavailable_periods: Annotated[
        list[ZigbangStayUnavailablePeriod] | None,
        Field(description='예약할 수 없는 기간 (예약됐거나 임대인이 막은 날, 직방이 1년 뒤까지 준다). 없으면 [], 직방이 일정을 주지 않거나 빈 항목을 줘 셀 수 없으면 null')
    ] = None

    available: Annotated[
        bool | None,
        Field(description=(
            '입주일·마지막 날을 줬을 때 그 기간을 예약할 수 있는지. 직방 웹 날짜 고르기 창 규칙 그대로, 입주일이 오늘 이후이고 '
            '기간이 최소 계약 주(contract_weeks_range.lowest) 이상·84일 이하이며, 입주일부터 마지막 날 전날까지 예약된·막힌 날이 없고 '
            '마지막 날이 막힌 날이 아니면 true. 직방이 일정을 주지 않거나 빈 항목을 줘 셀 수 없으면 null'
        ))
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='후기 수 (직방 웹 상세의 후기 배지). 후기가 없으면 0, 후기 조회가 실패했으면 null')
    ] = None
    review_rating: Annotated[
        float | None,
        Field(description=(
            "평균 평점 (직방 원값, 웹은 소수 첫째 자리로 반올림해 '★ 4.8' 로 보여 준다). 항목별 점수(청결·위치 등)는 직방에 없다. "
            '후기가 없으면(review_count 0) 키가 없고, 후기 조회가 실패했으면 null'
        ))
    ] = None
    host_other_listings: Annotated[
        list[ZigbangStayListing] | None,
        Field(description=(
            f"같은 임대인의 다른 단기임대 매물 (직방 웹 상세 맨 아래 '임대인의 다른 방', 지금 매물 제외). 직방 순서(검수 시각 늦은 순) "
            f'그대로 앞 {STAY_HOST_OTHER_LIMIT}건이고 전체 수는 host_other_listing_count 다. 없으면 [], 임대인을 모르거나 조회가 '
            '실패했거나 직방이 목록을 주지 않거나 빈 항목만 줘 있는지 알 수 없으면 null'
        ))
    ] = None
    host_other_listing_count: Annotated[
        int | None,
        Field(description=(
            '임대인의 다른 매물 전체 수 (host_other_listings 보다 많을 수 있다). 다른 방이 없으면 0, 임대인을 모르거나 조회가 '
            '실패했거나 직방이 수를 주지 않거나 빈 항목을 줘 셀 수 없으면 null'
        ))
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}
        # 후기가 없으면 평점도 없다 (직방은 평균 0 을 주지만 웹도 평점을 그리지 않는다)
        if self.review_count == 0:
            fields = fields | {'review_rating'}
        # 날짜를 주지 않은 조회에는 예약 가능 여부가 해당 없다. 날짜를 주면 get_stay_listing 이 모를 때(None)도 값을
        # 넣어(model_copy) model_fields_set 에 든다
        if 'available' not in self.model_fields_set:
            fields = fields | {'available'}
        # 주차 불가면 대수·방식이, 반려동물 동반 불가이면서 추가 청소비가 없거나 0 이면 그 청소비가 해당 없다.
        # stay_detail_to_listing 이 해당 없으면 값을 넣지 않아 model_fields_set 에 들지 않는다 (모를 때는 None 을 넣어 든다)
        return fields | {
            name for name in ('parking_count', 'parking_method', 'pet_cleaning_fee_manwon')
            if name not in self.model_fields_set
        }


def stay_parking(detail: ZigbangGuestItemsResponseModel) -> str | None:
    """주차 가능 여부를 직방 웹 표기로 바꾼다 (LIMITED 는 '제한적 가능', 2026-11-17 번들).

    요금(FREE 무료·PAID 유료)은 웹 상세(`AdditionalInfoSection`)처럼 가능(AVAILABLE)·제한적 가능(LIMITED) 둘 다에 붙인다.
    모르는 코드는 그대로 낸다.
    """
    if detail.parking_type is None:
        return None
    available = {'AVAILABLE': '가능', 'LIMITED': '제한적 가능', 'UNAVAILABLE': '불가'}.get(
        detail.parking_type, detail.parking_type,
    )
    fee = {'PAID': '유료', 'FREE': '무료'}.get(detail.parking_fee or '')
    return f'{available} ({fee})' if fee and detail.parking_type in ('AVAILABLE', 'LIMITED') else available


def stay_unavailable_periods(schedules: list[ZigbangStayScheduleModel] | None) -> list[ZigbangStayUnavailablePeriod] | None:
    """웹 달력이 막는 일정(예약·막힘)을 기간으로. 일정이 없으면 [], 직방이 일정을 주지 않았으면 None.

    날짜가 없거나 틀렸거나 끝날이 첫날보다 앞인 일정은 웹처럼 아무 날도 막지 않아 뺀다 (`_schedule_dates`). 날짜는 `date` 로 읽은 값의 YYYY-MM-DD 로 낸다.
    """
    if schedules is None:
        return None
    periods = []
    for schedule in schedules:
        if schedule.schedule_type not in STAY_UNAVAILABLE_SCHEDULES or (covered := _schedule_dates(schedule)) is None:
            continue
        first, last = covered
        periods.append(ZigbangStayUnavailablePeriod(
            start_date=first.isoformat(),
            end_date=last.isoformat(),
            kind=STAY_SCHEDULE_KIND_LABELS.get(schedule.schedule_type or '', schedule.schedule_type or ''),
        ))
    return periods


def _stay_label(labels: dict[str, str], raw: str | None) -> str | None:
    """직방 코드를 한국어 이름으로 바꾼다. 빈 글자는 모름(None), 표에 없는 코드는 원래 코드를 그대로 낸다."""
    code = text_or_none(raw)
    return labels.get(code, code) if code else None


def stay_detail_to_listing(
    detail: ZigbangGuestItemsResponseModel,
    registered_at: str | None = None,
) -> ZigbangStayListingDetail:
    """단기임대 상세를 `ZigbangStayListingDetail` 로 바꾼다. 사진·본문·호스트 정보는 옮기지 않는다.

    웹 옵션 목록은 반려동물 분류(PET_FRIENDLY)를 빼고 세고 '반려동물 동반 가능/불가' 로 따로 보여 주므로, `options` 에서
    빼고 `pet_allowed` 로 옮긴다 (직방이 옵션 목록 `itemOptions` 를 주지 않았으면 모름 None). 주차 불가의 대수·방식은 해당
    없어 값을 넣지 않는다. 추가 청소비는 웹이 동반 가능 여부와 상관없이 0 보다 크면 보여 주므로, 동반 가능이면 직방 값(0 이면
    0), 동반 불가·모름이면 0 보다 클 때 그 값을 내고 아니면 동반 불가는 값을 넣지 않고(`not_applicable_fields` 가 키를 뺀다)
    모름은 None 을 넣는다.
    """
    manage_cost = 0.0 if detail.is_weekly_manage_cost_absent else won_to_manwon(detail.weekly_manage_cost)
    includes = detail.manage_cost_includes
    # 리뷰 오탐 (2026-11-17): optionName 은 보지 않는다. 직방 웹(AdditionalInfoSection·OptionSection)도 category 만 본다
    pet_allowed: bool | None = None
    if sent_or_none(detail, 'item_options', []) is not None:
        # 옵션 목록에서 빈 항목(null)을 뺐으면 반려동물 분류가 그 항목이었을 수 있어 분류가 없다고 동반 불가로 단정하지 않는다
        pet_allowed = True if any(option.category == 'PET_FRIENDLY' for option in detail.item_options) else (
            None if detail.null_items('item_options') else False
        )
    conditional: dict[str, Any] = {}
    if detail.parking_type != 'UNAVAILABLE':
        conditional['parking_count'] = detail.parking_count
        conditional['parking_method'] = _stay_label(STAY_PARKING_METHOD_LABELS, detail.parking_method)
    pet_cleaning_fee = won_to_manwon(detail.pet_cleaning_fee)
    if pet_allowed or (pet_cleaning_fee is not None and pet_cleaning_fee > 0):
        conditional['pet_cleaning_fee_manwon'] = pet_cleaning_fee
    elif pet_allowed is None:
        conditional['pet_cleaning_fee_manwon'] = None
    # 정책 코드의 위약금 표. 코드가 없거나 표에 없으면 None (웹은 표준 표를 보여 주지만 모르는 정책을 표준이라고 단정하지 않는다)
    refund_table = STAY_REFUND_RULES.get(detail.refund_policy or '')
    return ZigbangStayListingDetail(
        source='zigbang',
        id=f'stay-{detail.id}',
        url=stay_item_url(detail.id),
        trade_type='단기임대',
        property_type=STAY_BUILDING_TYPE_LABELS.get(detail.building_type or '', detail.building_type or '단기임대'),
        title=detail.title,
        deposit_manwon=won_to_manwon(detail.deposit),
        area_m2=detail.size_m2,
        area_pyeong=m2_to_pyeong(detail.size_m2),
        floor=detail.floor,
        address=detail.address,
        lat=detail.lat,
        lng=detail.lng,
        registered_date=read_date(registered_at, '등록일'),
        room_count=detail.room_count,
        bathroom_count=detail.bathroom_count,
        parking=stay_parking(detail),
        has_elevator=detail.has_elevator,
        options=sent_or_none(
            detail, 'item_options',
            [
                STAY_OPTION_LABELS.get(option.option_name, option.option_name)
                for option in detail.item_options if option.category != 'PET_FRIENDLY'
            ],
        ),
        manage_cost_includes=None if includes is None else [
            {'gas': '가스', 'water': '수도', 'electricity': '전기'}.get(key, key)
            for key, included in includes.items() if included
        ],
        nearby_stations=sent_or_none(detail, 'nearby_stations', [
            f'{station.name} ({station.description})' if station.description else station.name
            for station in detail.nearby_stations
        ]),
        weekly_rent_manwon=won_to_manwon(detail.weekly_rent),
        weekly_manage_cost_manwon=manage_cost,
        cleaning_fee_manwon=0.0 if detail.cleaning_fee_free else won_to_manwon(detail.cleaning_fee),
        discounts=sent_or_none(detail, 'discounts', stay_discounts(detail.discounts, detail.weekly_rent)),
        contract_weeks_range=number_range(detail.min_contract_weeks, detail.max_contract_weeks),
        max_guests=detail.max_guests,
        duplex=detail.is_duplex,
        refund_policy=_stay_label(STAY_REFUND_POLICY_LABELS, detail.refund_policy),
        refund_rules=None if refund_table is None else [
            ZigbangStayRefundRule(when=when, penalty=penalty) for when, penalty in refund_table
        ],
        kitchen_count=detail.kitchen_count,
        living_room_count=detail.living_room_count,
        pet_allowed=pet_allowed,
        check_in_time=text_or_none(detail.checkin_time),
        check_out_time=text_or_none(detail.checkout_time),
        check_in_method=_stay_label(STAY_CHECK_METHOD_LABELS, detail.checkin_method),
        check_out_method=_stay_label(STAY_CHECK_METHOD_LABELS, detail.checkout_method),
        # 일정에서 빈 항목(null)을 뺐으면 그 항목이 예약된·막힌 날이었을 수 있어 예약할 수 없는 기간을 모른다
        unavailable_periods=None if detail.null_items('schedules') else stay_unavailable_periods(detail.schedules),
        **conditional,
    )


class ZigbangStayPeriod(RequestModel):
    """단기임대 상세에 준 입주일·마지막 날 (listing stay-… --check-in/--check-out). 서버에 보내지 않고 예약 가능 여부만 따진다."""

    check_in: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='입주일 (YYYY-MM-DD)')
    ]
    check_out: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='마지막으로 머무는 날 (YYYY-MM-DD)')
    ]

    @model_validator(mode='after')
    def valid_dates(self) -> Self:
        validate_stay_dates(self.check_in, self.check_out)
        return self


def get_stay_listing(
    client: ZigbangClient,
    item_id: int,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
) -> ZigbangStayListingDetail:
    """단기임대 매물 하나의 상세를 조회한다 (상세 + 노출 시작일용 요약 + 후기 요약 + 임대인의 다른 방, 4회 호출).

    후기 요약(`review_count`·`review_rating`)과 임대인의 다른 방(`host_other_listings`)은 덤이라 조회가 실패하면(요청 제한 포함)
    그 값만 null 로 두고 `notes` 에 `[실패]` 안내를 붙여 상세는 돌려준다 (임대인 ID 가 없어 요청하지 않은 다른 방은 안내가 없다, 3회).

    입주일·마지막 날(`check_in`·`check_out`)을 주면 상세의 일정(`schedules`)으로 그 기간을 예약할 수 있는지(`available`)를
    웹 날짜 고르기 창 규칙대로 붙인다 (`stay_range_available`, 요청이 늘지 않는다). 일정 목록에 빈 항목(null)이 섞여 와서 뺐으면
    그 항목이 막힌 날이었을 수 있어 `available`·`unavailable_periods` 는 null 이고 `[제외]` 로 알린다. 그 기간의 총비용은 웹이 로그인했을 때만
    요금 계산(`price-calculation`)을 불러 보여 주어 내지 않는다 (2026-11-15 웹: 로그인하지 않으면 날짜를 골라도 주당 금액만).

    Raises:
        ValidationError: 없는 날짜이거나 지난 입주일이거나 마지막 날이 입주일보다 뒤가 아닐 때 (요청 전에, CLI 는 INVALID_ARGUMENT).
        ListingUnavailableError: 없는 매물(404)이거나 노출 중이 아니거나 검수가 끝나지 않았을 때.
    """
    period = None if check_in is None or check_out is None else ZigbangStayPeriod(check_in=check_in, check_out=check_out)
    listing_id = f'stay-{item_id}'
    with unavailable_on_404(listing_id):
        detail = client.run_request_guest_items(ZigbangGuestItemsRequestParameterModel(item_id=item_id))
    if detail.status is not True or detail.check_status != 'COMPLETE':
        raise ListingUnavailableError(
            'zigbang',
            listing_id,
            status=None if detail.status is None else str(detail.status).lower(),
            reason=detail.check_status,
        )
    # 상세에는 노출 시작일(reviewedAt)이 없어 목록과 같은 값을 요약에서 받는다
    summaries = client.run_request_guest_items_by_ids(
        ZigbangGuestItemsByIdsRequestParameterModel(item_ids=[item_id])
    )
    summary = next((summary for summary in summaries.items if summary.id == item_id), None)
    listing = stay_detail_to_listing(detail, summary.reviewed_at if summary else None)
    # 후기 수·평균 평점 (웹 상세 후기 배지의 `fetchItemReviewSummary` 와 같은 호출). 없는 매물도 200 에 빈 응답이라 상세로 매물이
    # 있는 것을 확인한 뒤에만 부른다. 후기 글·작성자·사진은 읽지 않는다.
    reviews: dict[str, Any]
    review_notes: list[str] = []
    try:
        review_response = client.run_request_guest_items_reviews(ZigbangGuestItemsReviewsRequestParameterModel(item_id=item_id, limit=1))
    except OPTIONAL_LOOKUP_ERRORS as exc:
        reviews = dict(review_count=None, review_rating=None)
        review_notes = [lookup_failure_note(
            exc, '직방', '후기 정보', 'review_count·review_rating 값을 모릅니다 (url 의 직방 페이지에서 확인)',
        )]
    else:
        review_summary = review_response.summary
        review_count = review_summary.review_count if review_summary else None
        # 후기가 없으면(0) 평점 키는 not_applicable_fields 가 뺀다. 값은 직방 원값 그대로 둔다
        reviews = dict(
            review_count=review_count, review_rating=review_summary.average_rating if review_summary and review_count else None,
        )
    # 같은 임대인의 다른 방 (웹 상세 맨 아래 '임대인의 다른 방', 지금 매물 제외). 앞 `STAY_HOST_OTHER_LIMIT` 건과 전체 수다.
    # 임대인 ID 가 없거나 0 이하면 부르지 않고 둘 다 null 이다 (안내 없음). 서버 순서(검수 시각 늦은 순)를 그대로 낸다.
    # 응답에 목록이 없거나 null 이면 `host_other_listings` 는 null 이고 (모름), 전체 수는 직방이 준 값 그대로다.
    # 내려간 방(status false)은 서버가 목록과 totalCount 에서 뺀다 (2026-11-20 실측: 임대인 4747 의 4120, 1556 의 1200 이 빠졌다).
    # 웹 상세 화면도 이 응답을 거르지 않고 그대로 그려(번들 useGuestHostItems·StayItemDetailScreen) 상태를 다시 보지 않는다.
    host_others: dict[str, Any]
    host_notes: list[str] = []
    if detail.host_id is None or detail.host_id <= 0:
        host_others = dict(host_other_listings=None, host_other_listing_count=None)
    else:
        try:
            host_response = client.run_request_guest_items_host(ZigbangGuestItemsHostRequestParameterModel(
                host_id=detail.host_id, exclude_item_id=item_id, page=1, limit=STAY_HOST_OTHER_LIMIT,
            ))
        except OPTIONAL_LOOKUP_ERRORS as exc:
            # 다른 방을 못 받아도 매물 상세는 돌려준다 (모름)
            host_others = dict(host_other_listings=None, host_other_listing_count=None)
            host_notes = [lookup_failure_note(
                exc, '직방', '임대인의 다른 방 정보',
                'host_other_listings·host_other_listing_count 값을 모릅니다 (url 의 직방 페이지에서 확인)',
            )]
        else:
            host_items = host_response.items
            host_count = host_response.total_count
            # 직방이 수를 주지 않아도 다른 방이 하나도 없으면 0 이다 (목록 자체를 모르면 수도 모른다)
            if host_count is None and host_items is not None and not host_items:
                if dropped := host_response.null_items('items'):
                    # 목록에서 빈 항목(null)을 빼서 비었을 뿐 다른 방이 없는 것인지 알 수 없다. 없음([])·0 이 아니라 둘 다 모름이다.
                    # 직방이 준 수(total_count)가 있으면 그 값이 맞아 이 분기에 오지 않는다
                    host_notes.append(null_items_note(
                        '직방 임대인의 다른 방', dropped, ('host_other_listings', 'host_other_listing_count'),
                    ))
                    host_items = None
                else:
                    host_count = 0
            host_others = dict(
                host_other_listings=None if host_items is None else [stay_summary_to_listing(summary) for summary in host_items[:STAY_HOST_OTHER_LIMIT]],
                host_other_listing_count=host_count,
            )
    null_notes: list[str] = []
    if dropped := detail.null_items('schedules'):
        null_notes.append(null_items_note(
            '직방 단기임대 예약 일정', dropped, ('unavailable_periods', 'available') if period is not None else ('unavailable_periods',),
        ))
    # 옵션(`itemOptions`)에서 빈 항목을 뺐는데 반려동물 분류를 찾지 못했으면 `pet_allowed` 를 모른다 (찾았으면 그 목록은 늘어놓기만 해 안내하지 않는다)
    if (dropped := detail.null_items('item_options')) and listing.pet_allowed is None:
        # 반려동물 동반 가능 여부를 모를 때 추가 청소비는 0 보다 크면 그 값이고 아니면 null 이다 (`pet_cleaning_fee_manwon`)
        null_notes.append(null_items_note(
            '직방 단기임대 옵션', dropped,
            ('pet_allowed', 'pet_cleaning_fee_manwon') if listing.pet_cleaning_fee_manwon is None else ('pet_allowed',),
        ))
    notes = review_notes + host_notes + null_notes
    listing = listing.model_copy(update={**reviews, **host_others, 'notes': notes})
    if period is None:
        return listing
    # 일정에서 빈 항목(null)을 뺐으면 그 항목이 예약된·막힌 날이었을 수 있어 예약 가능 여부를 모른다
    available = None if detail.schedules is None or detail.null_items('schedules') else stay_range_available(
        detail.schedules, detail.min_contract_weeks, period.check_in, period.check_out, datetime.now(KST).date(),
    )
    return listing.model_copy(update={'available': available})


def stay_range_available(
    schedules: list[ZigbangStayScheduleModel],
    min_contract_weeks: int | None,
    check_in: str,
    check_out: str,
    today: date,
) -> bool:
    """입주일~마지막 날(`check_out`)을 예약할 수 있는지. 웹 날짜 고르기 창 규칙 그대로다 (번들 `resolveScheduleAutofill` 의
    `isRangeAvailable`, 일정 유연성 0).

    입주일이 오늘보다 앞이거나, 두 날짜 사이 일수가 최소 계약 주 × 7 − 1 보다 적거나(최소 계약 주가 없으면 1주, 1일보다 적게
    보지 않는다), 마지막 날이 입주일 + 83일보다 뒤면 불가다. 그 밖에는 예약된·막힌 일정이 덮는 날(시작·끝 날 포함,
    `generateDateRange`)에 입주일~마지막 날 전날이 하루라도 들거나, 마지막 날이 막힌(BLOCKED) 날이면 불가다
    (`isStayRangeFreeOfOccupancy`). 날짜가 없거나 틀린 일정은 웹처럼 아무 날도 덮지 않는다.
    """
    start = date.fromisoformat(check_in)
    end = date.fromisoformat(check_out)
    weeks = 1 if min_contract_weeks is None else min_contract_weeks
    if start < today or (end - start).days < max(1, 7 * weeks - 1) or end > start + timedelta(days=STAY_MAX_CHECK_OUT_DAYS):
        return False
    last_night = end - timedelta(days=1)
    for schedule in schedules:
        if schedule.schedule_type not in STAY_UNAVAILABLE_SCHEDULES or (covered := _schedule_dates(schedule)) is None:
            continue
        first, last = covered
        if first <= last_night and last >= start:
            return False
        if schedule.schedule_type == 'BLOCKED' and first <= end <= last:
            return False
    return True


def _schedule_dates(schedule: ZigbangStayScheduleModel) -> tuple[date, date] | None:
    """일정이 덮는 첫날·끝날. 날짜가 없거나 틀렸거나 끝날이 첫날보다 앞이면 웹(`generateDateRange`)처럼 덮는 날이 없어 None."""
    try:
        first = date.fromisoformat(schedule.start_date or '')
        last = date.fromisoformat(schedule.end_date or '')
    except ValueError:
        return None
    return (first, last) if first <= last else None
