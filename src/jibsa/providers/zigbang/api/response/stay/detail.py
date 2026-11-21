"""응답 모델: 단기임대 상세·후기·임대인의 다른 방 (listing stay-*)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.stay.base import (
    ZigbangStayDiscountModel,
    ZigbangStayItemSummaryModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/{itemId}
# ---------------------------------------------------------------------------

class ZigbangStayOptionModel(ResponseModel):
    """단기임대 옵션."""

    category: Annotated[
        str | None,
        Field(description='옵션 분류 (BASIC, ADDITIONAL, SECURITY_CONVENIENCE, PET_FRIENDLY)')
    ] = None
    option_name: Annotated[
        str,
        Field(description='옵션 코드 (AIR_CONDITIONER ...)', alias='optionName')
    ]


class ZigbangStayStationModel(ResponseModel):
    """단기임대 매물 인근 역."""

    id: Annotated[
        int | None,
        Field(description='역 ID')
    ] = None
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    description: Annotated[
        str | None,
        Field(description='노선 (예: 7호선,수인분당선)')
    ] = None


class ZigbangStayScheduleModel(ResponseModel):
    """단기임대 매물의 일정. 웹 날짜 고르기 창이 예약된·막힌 날을 이것으로 막는다."""

    schedule_type: Annotated[
        str | None,
        Field(description="일정 종류 ('RESERVED' 예약됨, 'BLOCKED' 호스트가 막음). 웹은 이 둘만 막는다", alias='scheduleType')
    ] = None
    start_date: Annotated[
        str | None,
        Field(description='시작일 (YYYY-MM-DD, 이 날부터 막힌다)', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='끝날 (YYYY-MM-DD, 이 날까지 막힌다)', alias='endDate')
    ] = None


class ZigbangGuestItemsResponseModel(ResponseModel):
    """단기임대 매물 상세. 금액은 **원** 단위다."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    status: Annotated[
        bool | None,
        Field(description='노출 중 여부')
    ] = None
    check_status: Annotated[
        str | None,
        Field(description="검수 상태 ('COMPLETE' 이면 검수 완료)", alias='checkStatus')
    ] = None
    host_id: Annotated[
        int | None,
        Field(description='임대인 ID. 임대인의 다른 방 조회(`/guest/items/host/{hostId}`)에 넘긴다. 키가 없으면 None (모름)', alias='hostId')
    ] = None
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    address: Annotated[
        str | None,
        Field(description="지번 주소 (예: '서울 강남구 삼성동 1-2')")
    ] = None
    new_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='newAddress')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='경도')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='방 종류 (OFFICETEL ...)', alias='buildingType')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='해당 층')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathroomCount')
    ] = None
    is_duplex: Annotated[
        bool | None,
        Field(description='복층 여부', alias='isDuplex')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='sizeM2')
    ] = None
    has_elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 유무', alias='hasElevator')
    ] = None
    parking_type: Annotated[
        str | None,
        Field(description='주차 (AVAILABLE, LIMITED, UNAVAILABLE)', alias='parkingType')
    ] = None
    parking_fee: Annotated[
        str | None,
        Field(description='주차비 (PAID, FREE)', alias='parkingFee')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='주차 대수. 가능·제한적 가능인데 없는 매물도 있고 불가면 없다', alias='parkingCount')
    ] = None
    parking_method: Annotated[
        str | None,
        Field(description='주차 방식 (SELF 자주식, MECHANICAL 기계식). 없을 수 있다', alias='parkingMethod')
    ] = None
    kitchen_count: Annotated[
        int | None,
        Field(description='주방 수 (0 도 온다)', alias='kitchenCount')
    ] = None
    living_room_count: Annotated[
        int | None,
        Field(description='거실 수 (0 도 온다)', alias='livingRoomCount')
    ] = None
    pet_cleaning_fee: Annotated[
        int | None,
        Field(description='반려동물을 데려올 때 추가 청소비 (원). 반려동물 가능인데 0 인 매물도 있다', alias='petCleaningFee')
    ] = None
    checkin_time: Annotated[
        str | None,
        Field(description="입주(체크인) 시각 ('15:00')", alias='checkinTime')
    ] = None
    checkout_time: Annotated[
        str | None,
        Field(description="퇴실(체크아웃) 시각 ('11:00')", alias='checkoutTime')
    ] = None
    checkin_method: Annotated[
        str | None,
        Field(description='입주 방식 (SELF 비대면, MEET 임대인 대면, KEYBOX 키박스)', alias='checkinMethod')
    ] = None
    checkout_method: Annotated[
        str | None,
        Field(description='퇴실 방식 (SELF 비대면, MEET 임대인 대면, KEYBOX 키박스)', alias='checkoutMethod')
    ] = None
    description: Annotated[
        str | None,
        Field(description='호스트가 쓴 상세 설명')
    ] = None
    weekly_rent: Annotated[
        int | None,
        Field(description='주당 임대료 (원)', alias='weeklyRent')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (원)')
    ] = None
    is_weekly_manage_cost_absent: Annotated[
        bool | None,
        Field(description='관리비 없음', alias='isWeeklyManageCostAbsent')
    ] = None
    weekly_manage_cost: Annotated[
        int | None,
        Field(description='주당 관리비 (원)', alias='weeklyManageCost')
    ] = None
    manage_cost_includes: Annotated[
        dict[str, bool] | None,
        Field(description='관리비 포함 여부 (gas, water, electricity)', alias='manageCostIncludes')
    ] = None
    cleaning_fee: Annotated[
        int | None,
        Field(description='청소비 (원)', alias='cleaningFee')
    ] = None
    cleaning_fee_free: Annotated[
        bool | None,
        Field(description='청소비 무료', alias='cleaningFeeFree')
    ] = None
    refund_policy: Annotated[
        str | None,
        Field(description='환불 정책 (FLEXIBLE, STANDARD, STRICT)', alias='refundPolicy')
    ] = None
    min_contract_weeks: Annotated[
        int | None,
        Field(description='최소 계약 주 수', alias='minContractWeeks')
    ] = None
    max_contract_weeks: Annotated[
        int | None,
        Field(description='최대 계약 주 수', alias='maxContractWeeks')
    ] = None
    max_guests: Annotated[
        int | None,
        Field(description='최대 인원', alias='maxGuests')
    ] = None
    discounts: Annotated[
        list[ZigbangStayDiscountModel],
        Field(description='할인 조건')
    ] = []
    item_options: Annotated[
        list[ZigbangStayOptionModel],
        Field(description='옵션', alias='itemOptions')
    ] = []
    nearby_stations: Annotated[
        list[ZigbangStayStationModel],
        Field(description='인근 역', alias='nearbyStations')
    ] = []
    created_at: Annotated[
        str | None,
        Field(description='등록 일시 (UTC ISO 8601)', alias='createdAt')
    ] = None
    schedules: Annotated[
        list[ZigbangStayScheduleModel] | None,
        Field(description=(
            '예약된·막힌 일정. 로그인 없이 온다 (2026-11-15 실측: 4114 는 BLOCKED 2026-11-11~2026-12-02 하나이고 웹 달력이 그 '
            '날짜를 막았다). 키가 없으면 None (모름)'
        ))
    ] = None


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/{itemId}/reviews
# ---------------------------------------------------------------------------

class ZigbangStayReviewSummaryModel(ResponseModel):
    """단기임대 후기 요약."""

    average_rating: Annotated[
        float | None,
        Field(description='평균 평점. 후기가 없으면 0 (2026-11-19 표본 28건 모두 0)', alias='averageRating')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='후기 수. 후기가 없으면 0', alias='reviewCount')
    ] = None


class ZigbangGuestItemsReviewsResponseModel(ResponseModel):
    """단기임대 후기 응답. 후기 목록(`reviews`)은 글·닉네임·사진이 들어 있어 읽지 않는다 (요약만 쓴다)."""

    summary: Annotated[
        ZigbangStayReviewSummaryModel | None,
        Field(description='평점·후기 수 요약. 없는 매물도 200 에 후기 0 건 요약이 온다 (2026-11-19 실측)')
    ] = None


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/host/{hostId}
# ---------------------------------------------------------------------------

class ZigbangGuestItemsHostResponseModel(ResponseModel):
    """같은 임대인의 다른 단기임대 매물. 항목은 요약(`by-ids`)과 키가 같다 (좋아요 여부(`isFavorite`)는 읽지 않는다)."""

    items: Annotated[
        list[ZigbangStayItemSummaryModel] | None,
        Field(description='이 쪽의 매물 요약 (금액은 원 단위). 키가 없거나 null 이면 None (모름)')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='임대인의 매물 수 (쪽과 상관없는 전체. 2026-11-19 임대인 5436 은 93, 1쪽 5건·limit 없이 93건)', alias='totalCount')
    ] = None
