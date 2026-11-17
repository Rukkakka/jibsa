"""응답 모델: 단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET stay-apis.zigbang.com/guest/items/markers
# ---------------------------------------------------------------------------

class ZigbangStayMarkerModel(ResponseModel):
    """단기임대 매물 위치 핀. 웹 지도 목록은 화면 안 핀을 이 값들로 세운다 (번들 `sortStayMarkers`)."""

    id: Annotated[
        int,
        Field(description='단기임대 매물 ID')
    ]
    lat: Annotated[
        float,
        Field(description='위도 (요약 by-ids 의 좌표와 같다. 2026-11-15 실측 71건)')
    ]
    lng: Annotated[
        float,
        Field(description='경도')
    ]
    weekly_price: Annotated[
        int | None,
        Field(
            description='주당 임대료+관리비 (만원, 만원 미만 버림. 2026-11-15 실측 71건 모두). 웹 지도 목록 가격순의 기준',
            alias='weeklyPrice'
        )
    ] = None
    has_discount: Annotated[
        bool | None,
        Field(description='할인 여부', alias='hasDiscount')
    ] = None
    reviewed_at: Annotated[
        str | None,
        Field(description='검수 완료(노출 시작) 일시 (UTC ISO 8601, 요약과 같다). 웹 지도 목록 최신순의 기준', alias='reviewedAt')
    ] = None
    total_score: Annotated[
        float | None,
        Field(description='직방 추천 점수 (예: 0.85). 웹 지도 목록 추천순의 기준 (높을수록 앞)', alias='totalScore')
    ] = None


class ZigbangGuestItemsSearchResponseModel(ResponseModel):
    """지역·역·학교 조건에 맞는 단기임대 ID 목록. 요청한 정렬(`sort`) 순서이고, 웹 검색 결과 목록이 이 순서 그대로다."""

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
