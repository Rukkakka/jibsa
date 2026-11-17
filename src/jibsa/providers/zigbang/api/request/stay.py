"""요청 모델: 단기임대 매물 검색과 상세 (search listings stay, listing stay-*)."""

from datetime import (
    date,
    datetime,
)

from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.listing import KST
from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
    Self,
)


ZigbangStayBuildingType = Literal[
    'OFFICETEL', 'APARTMENT', 'VILLA', 'ONEROOM', 'HOUSE', 'COMMERCIAL_HOUSE',
    'GOSIWON', 'PENSION', 'SHAREHOUSE', 'GUESTHOUSE', 'RESIDENTIAL_HOTEL',
]
ZigbangStayDiscountType = Literal['LONG_TERM', 'INSTANT']
ZigbangStayFloorType = Literal['BASEMENT', 'FIRST', 'ROOFTOP']
ZigbangStayOption = Literal[
    'AIR_CONDITIONER', 'BED', 'GAS_RANGE', 'INDUCTION', 'REFRIGERATOR', 'SINK', 'TV',
    'WASHING_MACHINE', 'WIFI', 'AIR_PURIFIER', 'WATER_PURIFIER', 'CLOSET', 'COFFEE_MACHINE', 'DESK',
    'DINING_TABLE', 'DISHWASHER', 'DRYER', 'ELECTRIC_KETTLE', 'MICROWAVE', 'RICE_COOKER',
    'SOFA', 'TOASTER', 'VANITY', 'BATHTUB', 'BIDET', 'CABLE_TV', 'CCTV', 'DOOR_LOCK',
    'DRYING_RACK', 'MANAGEMENT_OFFICE', 'OTT', 'VACUUM_CLEANER', 'BALCONY',
]
# 웹 정렬 넷과 같다: 추천순(기본), 낮은 가격순, 최근 등록순, 역 가까운 순 (2026-11-15 웹)
ZigbangStaySearchSort = Literal['RECOMMENDED', 'PRICE_ASC', 'NEWEST', 'STATION_DISTANCE_ASC']


# 단기임대 지도·지역 검색이 받는 기간 (입주일과 마지막 날을 모두 센 일수). 2026-10-10 실측: 두 API 모두
# 6일은 400 MIN_DURATION_VIOLATION, 85일은 400 MAX_DURATION_VIOLATION. 매물 59건의 최대 계약도 모두 12주였다
STAY_SEARCH_MIN_DAYS: int = 7
STAY_SEARCH_MAX_DAYS: int = 84


def stay_days(check_in: str, check_out: str) -> int:
    """이용 일수. 직방은 --check-out 을 마지막으로 머무는 날로 보고 이용일에 센다 (11-02~11-08 = 7일)."""
    return (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days + 1


def validate_stay_dates(check_in: str, check_out: str) -> None:
    """입주일·마지막 날이 실제 날짜이고, 입주일이 한국 날짜로 오늘 이후이며, 마지막 날이 입주일보다 뒤인지 본다.

    Raises:
        ValueError: 위 조건을 어길 때 (요청 모델 검증 안에서 불러 CLI 는 INVALID_ARGUMENT).
    """
    # 2026-10-09 비로그인 API 실측: 검색은 오늘 입주를 허용하고 과거는 400. 2027-02-30 은 검색에서 500 이므로 서버에 맡기지
    # 않고 달력을 검증한다. 상세(listing stay-…)는 날짜를 서버에 보내지 않지만, 웹 날짜 고르기 창도 지난 날을 고를 수 없어
    # 같은 검사를 한다. 기간이 매물 계약 범위에 맞는지는 매물마다 달라(최소 1~8주) 여기서 보지 않는다
    try:
        start = date.fromisoformat(check_in)
        end = date.fromisoformat(check_out)
    except ValueError:
        raise ValueError('입주일·마지막 날은 실제 존재하는 YYYY-MM-DD 날짜여야 합니다') from None
    if start < datetime.now(KST).date():
        raise ValueError('입주일은 한국 날짜 기준 오늘 이후여야 합니다')
    if end <= start:
        raise ValueError('마지막으로 머무는 날(--check-out)은 입주일보다 뒤여야 합니다')


def _validate_stay_search_period(check_in: str, check_out: str) -> None:
    days = stay_days(check_in, check_out)
    if not STAY_SEARCH_MIN_DAYS <= days <= STAY_SEARCH_MAX_DAYS:
        raise ValueError(
            f'단기임대 검색 기간은 입주일과 마지막 날을 포함해 {STAY_SEARCH_MIN_DAYS}~{STAY_SEARCH_MAX_DAYS}일'
            f'(1~12주)이어야 합니다 (지금 {days}일). 예: 1주 = 2026-11-02~2026-11-08'
        )


class ZigbangStayDatesMixin(RequestModel):
    """단기임대 검색(지도·지역)과 요약(by-ids)이 함께 받는 입주·퇴거일. 둘 다 검색 기간(7~84일)을 받는다."""

    check_in_date: Annotated[
        str | None,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='입주 희망일 (YYYY-MM-DD)', alias='checkInDate')
    ] = None
    check_out_date: Annotated[
        str | None,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='마지막으로 머무는 날 (YYYY-MM-DD, 이용일에 센다)', alias='checkOutDate')
    ] = None
    flexibility: Annotated[
        int | None,
        Field(ge=0, description='일정을 앞뒤로 며칠까지 유연하게 볼지')
    ] = None

    @model_validator(mode='after')
    def dates_together(self) -> Self:
        # 하나만 보내면 서버가 400 "입주일과 퇴거일을 모두 선택해주세요" 를 준다
        if (self.check_in_date is None) != (self.check_out_date is None):
            raise ValueError('입주일과 퇴거일은 함께 주어야 합니다')
        if self.flexibility is not None and self.check_in_date is None:
            raise ValueError('일정 유연성은 입주일·퇴거일과 함께 써야 합니다')
        if self.check_in_date is not None and self.check_out_date is not None:
            validate_stay_dates(self.check_in_date, self.check_out_date)
            _validate_stay_search_period(self.check_in_date, self.check_out_date)
        return self


class ZigbangGuestItemsFiltersRequestParameterModel(ZigbangStayDatesMixin):
    """직방 단기임대 지도·지역 검색의 공통 필터.

    요금은 **주당 만원** 이다. 배열 필터는 같은 키를 반복해 보낸다 (`options=A&options=B`).
    방 종류·할인·층은 OR, 옵션은 AND 다. 입주·퇴거일은 함께 보내야 한다.
    """

    weekly_price_min: Annotated[
        int | None,
        Field(ge=0, description='주당 요금 하한 (만원)', alias='minWeeklyPrice')
    ] = None
    weekly_price_max: Annotated[
        int | None,
        Field(ge=0, description='주당 요금 상한 (만원)', alias='maxWeeklyPrice')
    ] = None
    room_count: Annotated[
        int | None,
        Field(ge=1, le=4, description='방 수. 1~3 은 정확히 그 수, 4 는 4개 이상', alias='roomCount')
    ] = None
    building_types: Annotated[
        list[ZigbangStayBuildingType],
        Field(description='방 종류 (OR)', alias='buildingTypes')
    ] = []
    size_min_m2: Annotated[
        float | None,
        Field(ge=0, description='전용면적 하한 (㎡)', alias='minSizeM2')
    ] = None
    size_max_m2: Annotated[
        float | None,
        Field(ge=0, description='전용면적 상한 (㎡)', alias='maxSizeM2')
    ] = None
    discount_types: Annotated[
        list[ZigbangStayDiscountType],
        Field(description='할인 (OR). LONG_TERM 장기 계약 할인, INSTANT 즉시 할인', alias='discountTypes')
    ] = []
    pet_allowed: Annotated[
        bool | None,
        Field(description='반려동물 허용', alias='petAllowed')
    ] = None
    is_duplex: Annotated[
        bool | None,
        Field(description='복층 구조 (False 면 단층만)', alias='isDuplex')
    ] = None
    options: Annotated[
        list[ZigbangStayOption],
        Field(description='옵션 (AND)')
    ] = []
    has_parking: Annotated[
        bool | None,
        Field(description='주차 가능', alias='hasParking')
    ] = None
    has_elevator: Annotated[
        bool | None,
        Field(description='엘리베이터', alias='hasElevator')
    ] = None
    floor_types: Annotated[
        list[ZigbangStayFloorType],
        Field(description='층 (OR). BASEMENT 지하, FIRST 1층, ROOFTOP 옥탑', alias='floorTypes')
    ] = []


class ZigbangGuestItemsMarkersRequestParameterModel(ZigbangGuestItemsFiltersRequestParameterModel):
    """`GET /guest/items/markers` 지도 칸 검색."""

    geohash: Annotated[
        str,
        Field(pattern=r'^[0-9bcdefghjkmnpqrstuvwxyz]{4,7}$', description='지도 타일 geohash')
    ]


class ZigbangGuestItemsSearchRequestParameterModel(ZigbangGuestItemsFiltersRequestParameterModel):
    """`GET /guest/items/search` 지역·역·학교 검색. 응답 ID는 by-ids로 조회한다.

    반경 지정은 지원하지 않는다. 지역은 local1~3, 역·학교는 lat/lng를 사용한다. 역(`subway`)은 서버가 역에서 약 1km 안만
    주고, 지역(`address`)은 동 경계가 아니라 이웃 동 매물도 섞여 온다 (2026-11-15 실측: 강남역 71건 중 가장 먼 것 0.979km,
    성수동2가 34건 중 성수동2가는 17건이고 화양동 9·자양동 5·성수동1가 3건).
    """

    type: Annotated[
        Literal['address', 'subway', 'school', 'university'],
        Field(description='지역·역·학교 검색 유형')
    ]
    local1: Annotated[
        str | None,
        Field(description=(
            "시·도 이름. 직방 검색의 줄임말('서울시', '강원도', '전남광주시')과 정식 명칭을 똑같이 받는다 "
            "(2026-10-10 실측 8곳 같은 건수). 모르는 이름('서울', '광주광역시')은 0건이 아니라 400 REGION_NOT_FOUND"
        ))
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시·군·구 이름')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍·면·동 이름')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='역·학교 검색 중심 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='역·학교 검색 중심 경도')
    ] = None

    sort: Annotated[
        ZigbangStaySearchSort | None,
        Field(description=(
            '정렬. RECOMMENDED 추천순(안 보내도 같은 순서, 2026-11-15 실측 강남역 71건·역삼동 64건), PRICE_ASC 주당 '
            '임대료+관리비 낮은 순, NEWEST 등록 시각 늦은 순, STATION_DISTANCE_ASC 역에서 가까운 순(subway 만). '
            'PRICE_ASC·STATION_DISTANCE_ASC 는 같은 값이면 ID 큰 순이고, 같은 요청은 늘 같은 순서다 (2026-11-15 실측)'
        ))
    ] = None

    @model_validator(mode='after')
    def context_required(self) -> Self:
        if self.type == 'address':
            if not self.local1:
                raise ValueError('지역 검색에는 시·도 이름이 필요합니다')
        elif self.lat is None or self.lng is None:
            raise ValueError('역·학교 검색에는 위도와 경도가 필요합니다')
        if (self.lat is None) != (self.lng is None):
            raise ValueError('위도와 경도는 함께 주어야 합니다')
        # 서버가 400 STATION_SORT_REQUIRES_SUBWAY '역 가까운 순은 지하철역 검색에서만 사용 가능합니다' 를 준다
        # (2026-11-15 실측: address·university)
        if self.sort == 'STATION_DISTANCE_ASC' and self.type != 'subway':
            raise ValueError('역 가까운 순은 지하철역 검색에서만 쓸 수 있습니다')
        return self


class ZigbangGuestItemsByIdsRequestParameterModel(ZigbangStayDatesMixin):
    """`GET stay-apis.zigbang.com/guest/items/by-ids` 쿼리. 단기임대 매물 요약."""

    item_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=100, description='요약을 받을 매물 ID 목록 (같은 키 반복)', alias='itemIds')
    ]


class ZigbangGuestItemsRequestParameterModel(RequestModel):
    """`GET stay-apis.zigbang.com/guest/items/{itemId}` 경로."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단기임대 매물 ID. 경로에 들어간다')
    ]
