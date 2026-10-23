"""응답 모델: 단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/markers
# ---------------------------------------------------------------------------

class ZigbangStayMarkerModel(ResponseModel):
    """단기임대 매물 위치 핀."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    lat: Annotated[
        float,
        Field(description='위도')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]
    weekly_price: Annotated[
        int | None,
        Field(description='주당 요금 (만원, 반올림)', alias='weeklyPrice')
    ] = None
    has_discount: Annotated[
        bool | None,
        Field(description='할인 여부', alias='hasDiscount')
    ] = None


class ZigbangGuestItemsSearchResponseModel(ResponseModel):
    """지역·역·학교 조건에 맞는 단기임대 ID 목록."""

    item_ids: Annotated[
        list[int],
        Field(description='조건에 맞는 단기임대 매물 ID', alias='itemIds')
    ]
    total_count: Annotated[
        int,
        Field(
            description='서버 검색 결과 수. itemIds 를 자르지 않아 늘 itemIds 수와 같다 '
            '(페이지 인자 없음. 2026-10-11 실측: 서울시 1,491·경기도 568건)',
            alias='totalCount'
        )
    ]


class ZigbangGuestItemsMarkersResponseModel(ResponseModel):
    """단기임대 매물 위치 응답."""

    markers: Annotated[
        list[ZigbangStayMarkerModel],
        Field(description='geohash 칸 안의 매물 핀')
    ] = []


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/by-ids, /guest/items/{itemId}
# ---------------------------------------------------------------------------

class ZigbangStayAddressModel(ResponseModel):
    """단기임대 매물 주소 (동까지)."""

    local1: Annotated[
        str | None,
        Field(description='시/도 (예: 서울시)')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    local4: Annotated[
        str | None,
        Field(description='리')
    ] = None


class ZigbangStayDiscountModel(ResponseModel):
    """단기임대 할인 조건."""

    discount_type: Annotated[
        str,
        Field(description='할인 종류 (LONG_TERM 장기 계약, INSTANT 즉시)', alias='discountType')
    ]
    condition_weeks: Annotated[
        int | None,
        Field(description='장기 할인이 붙는 최소 계약 주 수', alias='conditionWeeks')
    ] = None
    condition_days: Annotated[
        int | None,
        Field(description='즉시 할인이 붙는 조건 일 수', alias='conditionDays')
    ] = None
    discount_rate: Annotated[
        float | None,
        Field(description='할인율 (%)', alias='discountRate')
    ] = None
    discount_amount: Annotated[
        int | None,
        Field(description='할인 금액 (원)', alias='discountAmount')
    ] = None
    is_active: Annotated[
        bool | None,
        Field(description='할인 적용 중 여부', alias='isActive')
    ] = None


class ZigbangStayItemSummaryModel(ResponseModel):
    """단기임대 매물 요약. 금액은 **원** 단위다."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    title: Annotated[
        str | None,
        Field(description='매물 제목')
    ] = None
    address: Annotated[
        ZigbangStayAddressModel | None,
        Field(description='주소 (동까지)')
    ] = None
    thumbnail_url: Annotated[
        str | None,
        Field(description='대표 이미지 URL', alias='thumbnailUrl')
    ] = None
    weekly_rent: Annotated[
        int | None,
        Field(description='주당 임대료 (원)', alias='weeklyRent')
    ] = None
    weekly_manage_cost: Annotated[
        int | None,
        Field(description='주당 관리비 (원)', alias='weeklyManageCost')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='방 종류 (OFFICETEL, APARTMENT, VILLA ...)', alias='buildingType')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='roomCount')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='bathroomCount')
    ] = None
    size_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='sizeM2')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='해당 층')
    ] = None
    discounts: Annotated[
        list[ZigbangStayDiscountModel],
        Field(description='할인 조건')
    ] = []
    lat: Annotated[
        float | None,
        Field(description='위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='경도')
    ] = None
    reviewed_at: Annotated[
        str | None,
        Field(description='검수 완료(노출 시작) 일시 (UTC ISO 8601)', alias='reviewedAt')
    ] = None


class ZigbangGuestItemsByIdsResponseModel(ResponseModel):
    """단기임대 매물 요약 배치 응답. 내려간 매물은 빠진다."""

    items: Annotated[
        list[ZigbangStayItemSummaryModel],
        Field(description='매물 요약')
    ] = []


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
        Field(description='주차 (AVAILABLE, UNAVAILABLE ...)', alias='parkingType')
    ] = None
    parking_fee: Annotated[
        str | None,
        Field(description='주차비 (PAID, FREE)', alias='parkingFee')
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


# ---------------------------------------------------------------------------
# POST stay-apis.zigbang.com/guest/items/{itemId}/price-calculation
# ---------------------------------------------------------------------------

class ZigbangStayPriceDiscountModel(ResponseModel):
    """기간 요금에 적용된 할인."""

    type: Annotated[
        str | None,
        Field(description='할인 종류 (LONG_TERM 장기계약, INSTANT 즉시 ...)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='할인 이름 (예: 장기계약 할인)')
    ] = None
    rate: Annotated[
        float | None,
        Field(description='할인율 (%)')
    ] = None
    saved_amount: Annotated[
        int | None,
        Field(description='할인 금액 (**원**)', alias='savedAmount')
    ] = None


class ZigbangGuestItemsPriceCalculationResponseModel(ResponseModel):
    """단기임대 기간 요금 계산. 금액은 모두 **원** 단위다. 그 날짜에 예약이 비어 있는지는 보지 않는다.

    `totalGuestPayment` = `totalAmount`(임대료 + 관리비 + 청소비 − 할인) + `platformFee` + `oneTimePayment`
    (보증금 + 청소비 등 한 번 내는 돈) 이다.
    """

    total_days: Annotated[
        int | None,
        Field(description='계약 일수', alias='totalDays')
    ] = None
    weeks: Annotated[
        int | None,
        Field(description='계약 주 수 (일수를 7로 나눈 몫)')
    ] = None
    remaining_days: Annotated[
        int | None,
        Field(description='주 단위로 나누고 남은 일수', alias='remainingDays')
    ] = None
    total_rent: Annotated[
        int | None,
        Field(description='기간 임대료 (원, 할인 전)', alias='totalRent')
    ] = None
    total_manage_cost: Annotated[
        int | None,
        Field(description='기간 관리비 (원)', alias='totalManageCost')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (원, 돌려받는 돈)')
    ] = None
    cleaning_fee: Annotated[
        int | None,
        Field(description='청소비 (원)', alias='cleaningFee')
    ] = None
    pet_cleaning_fee: Annotated[
        int | None,
        Field(description='반려동물 청소비 (원)', alias='petCleaningFee')
    ] = None
    discounts: Annotated[
        list[ZigbangStayPriceDiscountModel],
        Field(description='적용된 할인')
    ] = []
    total_discount_amount: Annotated[
        int | None,
        Field(description='할인 합계 (원)', alias='totalDiscountAmount')
    ] = None
    total_promotion_discount: Annotated[
        int | None,
        Field(description='프로모션 할인 합계 (원)', alias='totalPromotionDiscount')
    ] = None
    platform_fee: Annotated[
        int | None,
        Field(description='직방 이용료 (원)', alias='platformFee')
    ] = None
    total_guest_payment: Annotated[
        int | None,
        Field(description='세입자가 내는 총액 (원, 보증금 포함)', alias='totalGuestPayment')
    ] = None
