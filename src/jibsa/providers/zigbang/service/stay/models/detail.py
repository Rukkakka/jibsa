"""`detail.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from jibsa.core.listing import (
    ListingDetail,
    NumberRange,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.models.request.stay.common import validate_stay_dates
from jibsa.providers.zigbang.service.stay.constants import (
    STAY_HOST_OTHER_LIMIT,
)
from jibsa.providers.zigbang.service.stay.models.common import ZigbangStayListing

from typing import (
    Annotated,
    Self,
)


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
