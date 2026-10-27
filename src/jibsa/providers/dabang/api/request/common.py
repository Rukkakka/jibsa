from pydantic import (
    Field,
    field_serializer,
    model_validator,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
    Self,
)


# 다방 범위 필터의 '상한 없음'. 웹 필터 초기값이 {min: 0, max: 999999} 다 (filter-init 청크, 2026-10-25)
UNBOUNDED_MAX: int = 999999
# 다방 단지 ID (28자리 16진수, 예: 58291f830ff9bd73a07ca123c632)
COMPLEX_ID_PATTERN_TEXT: str = r'^[0-9a-f]{28}$'

DabangCategory = Literal['one-two', 'house-villa', 'officetel', 'apt']
DabangComplexCategory = Literal['officetel', 'apt']
DabangSearchType = Literal['region', 'subway', 'univ', 'bbox']
DabangSellingType = Literal['MONTHLY_RENT', 'LEASE', 'SELL']
DabangRoomFloor = Literal['GROUND_FIRST', 'GROUND_SECOND_OVER', 'SEMI_BASEMENT', 'ROOFTOP']
DabangRoomType = Literal['ONE_ROOM', 'TWO_ROOM']
DabangRoomCount = Literal['ONE_ROOM', 'TWO_ROOM', 'THREE_ROOM', 'FOUR_ROOM']

ALL_SELLING_TYPES: tuple[DabangSellingType, ...] = ('MONTHLY_RENT', 'LEASE', 'SELL')
ALL_ROOM_FLOORS: tuple[DabangRoomFloor, ...] = ('GROUND_FIRST', 'GROUND_SECOND_OVER', 'SEMI_BASEMENT', 'ROOFTOP')
ALL_ROOM_TYPES: tuple[DabangRoomType, ...] = ('ONE_ROOM', 'TWO_ROOM')
ALL_ROOM_COUNTS: tuple[DabangRoomCount, ...] = ('ONE_ROOM', 'TWO_ROOM', 'THREE_ROOM', 'FOUR_ROOM')


class DabangRangeModel(RequestModel):
    """필터의 범위 하나. 금액은 만원, 방 크기는 평, 사용승인은 연차(년)다.

    Args:
        min: 하한. Defaults to 0.
        max: 상한. 999999 는 상한 없음. Defaults to 999999.
    """

    min: Annotated[
        int,
        Field(ge=0, description='하한')
    ] = 0
    max: Annotated[
        int,
        Field(ge=0, description='상한 (999999 는 상한 없음)')
    ] = UNBOUNDED_MAX

    @model_validator(mode='after')
    def ordered(self) -> Self:
        if self.min > self.max:
            raise ValueError(f'범위의 하한({self.min})이 상한({self.max})보다 큽니다')
        return self


class DabangFiltersModel(RequestModel):
    """네 매물 유형 필터가 같이 받는 항목. 다방은 유형마다 받는 항목이 다르고, 하나라도 빠지면 400 으로 빠진 항목을
    알려 준다 ("주차가능 여부는 필수값 입니다", 2026-10-25 실측). 그래서 사용자가 주지 않은 항목도 '전체' 값으로 채워 보낸다.

    Args:
        deposit_range: 보증금·전세금 (만원).
        price_range: 월세 (만원).
        is_include_maintenance: 월세 범위를 월세 + 관리비로 볼지. Defaults to False.
        pyeong_range: 방 크기 (평, 정수).
        use_approval_date_range: 사용승인 뒤 지난 햇수.
        deal_type_list: 거래 주체. 웹은 늘 중개(`AGENT`)만 보낸다 (직거래 `DIRECT` 는 역삼동 0건, 2026-10-25 실측).
        is_short_lease: True 면 단기임대 가능 매물만. Defaults to False.
    """

    deposit_range: Annotated[
        DabangRangeModel,
        Field(description='보증금·전세금 (만원)', alias='depositRange')
    ] = Field(default_factory=DabangRangeModel)
    price_range: Annotated[
        DabangRangeModel,
        Field(description='월세 (만원)', alias='priceRange')
    ] = Field(default_factory=DabangRangeModel)
    is_include_maintenance: Annotated[
        bool,
        Field(description='월세 범위를 월세 + 관리비로 볼지', alias='isIncludeMaintenance')
    ] = False
    pyeong_range: Annotated[
        DabangRangeModel,
        Field(description='방 크기 (평)', alias='pyeongRange')
    ] = Field(default_factory=DabangRangeModel)
    use_approval_date_range: Annotated[
        DabangRangeModel,
        Field(description='사용승인 뒤 지난 햇수 (년)', alias='useApprovalDateRange')
    ] = Field(default_factory=DabangRangeModel)
    deal_type_list: Annotated[
        list[Literal['AGENT']],
        Field(description='거래 주체 (중개만)', alias='dealTypeList')
    ] = ['AGENT']
    is_short_lease: Annotated[
        bool,
        Field(description='단기임대 가능 매물만', alias='isShortLease')
    ] = False


class DabangOneTwoFiltersModel(DabangFiltersModel):
    """원룸·투룸(`one-two`) 필터. 매매는 받지 않는다 (매매만 보내면 무시하고 월세를 준다, 2026-10-25 실측)."""

    selling_type_list: Annotated[
        list[Literal['MONTHLY_RENT', 'LEASE']],
        Field(min_length=1, description='거래 유형', alias='sellingTypeList')
    ] = ['MONTHLY_RENT', 'LEASE']
    room_floor_list: Annotated[
        list[DabangRoomFloor],
        Field(min_length=1, description='층', alias='roomFloorList')
    ] = list(ALL_ROOM_FLOORS)
    room_type_list: Annotated[
        list[DabangRoomType],
        Field(min_length=1, description='방 개수 (원룸·투룸)', alias='roomTypeList')
    ] = list(ALL_ROOM_TYPES)
    can_parking: Annotated[
        bool,
        Field(description='주차 가능만', alias='canParking')
    ] = False
    has_elevator: Annotated[
        bool,
        Field(description='엘리베이터 있는 매물만', alias='hasElevator')
    ] = False
    has_pano: Annotated[
        bool,
        Field(description='360° VR 사진이 있는 매물만 (사진 기능이라 jibsa 는 늘 False)', alias='hasPano')
    ] = False
    is_division: Annotated[
        bool,
        Field(description='분리형 원룸만', alias='isDivision')
    ] = False
    is_duplex: Annotated[
        bool,
        Field(description='복층만', alias='isDuplex')
    ] = False


class DabangSaleFiltersModel(DabangFiltersModel):
    """매매를 받는 유형(빌라·오피스텔·아파트)이 같이 받는 항목."""

    selling_type_list: Annotated[
        list[DabangSellingType],
        Field(min_length=1, description='거래 유형', alias='sellingTypeList')
    ] = list(ALL_SELLING_TYPES)
    trade_range: Annotated[
        DabangRangeModel,
        Field(description='매매가 (만원)', alias='tradeRange')
    ] = Field(default_factory=DabangRangeModel)
    room_count_list: Annotated[
        list[DabangRoomCount],
        Field(min_length=1, description='방 개수 (FOUR_ROOM 은 4개 이상)', alias='roomCountList')
    ] = list(ALL_ROOM_COUNTS)


class DabangHouseVillaFiltersModel(DabangSaleFiltersModel):
    """주택·빌라(`house-villa`) 필터."""

    room_floor_list: Annotated[
        list[DabangRoomFloor],
        Field(min_length=1, description='층', alias='roomFloorList')
    ] = list(ALL_ROOM_FLOORS)
    can_parking: Annotated[
        bool,
        Field(description='주차 가능만', alias='canParking')
    ] = False
    has_elevator: Annotated[
        bool,
        Field(description='엘리베이터 있는 매물만', alias='hasElevator')
    ] = False
    has_pano: Annotated[
        bool,
        Field(description='360° VR 사진이 있는 매물만 (jibsa 는 늘 False)', alias='hasPano')
    ] = False


class DabangOfficetelFiltersModel(DabangSaleFiltersModel):
    """오피스텔(`officetel`) 필터. 층 조건은 받지 않는다."""

    parking_num_range: Annotated[
        DabangRangeModel,
        Field(description='주차 대수 (뜻을 확인하지 않아 jibsa 는 늘 전체)', alias='parkingNumRange')
    ] = Field(default_factory=DabangRangeModel)
    can_parking: Annotated[
        bool,
        Field(description='주차 가능만', alias='canParking')
    ] = False
    has_elevator: Annotated[
        bool,
        Field(description='엘리베이터 있는 매물만', alias='hasElevator')
    ] = False
    has_pano: Annotated[
        bool,
        Field(description='360° VR 사진이 있는 매물만 (jibsa 는 늘 False)', alias='hasPano')
    ] = False


class DabangAptFiltersModel(DabangSaleFiltersModel):
    """아파트(`apt`) 필터. 층·주차·엘리베이터 조건은 받지 않는다."""

    household_num_range: Annotated[
        DabangRangeModel,
        Field(description='세대수', alias='householdNumRange')
    ] = Field(default_factory=DabangRangeModel)
    parking_num_range: Annotated[
        DabangRangeModel,
        Field(description='주차 대수 (뜻을 확인하지 않아 jibsa 는 늘 전체)', alias='parkingNumRange')
    ] = Field(default_factory=DabangRangeModel)
    has_take_tenant: Annotated[
        bool,
        Field(description='세입자가 있는 채로 파는 매물만으로 보인다 (뜻을 확인하지 않아 jibsa 는 늘 False)', alias='hasTakeTenant')
    ] = False


DabangListFilters = DabangOneTwoFiltersModel | DabangHouseVillaFiltersModel | DabangOfficetelFiltersModel | DabangAptFiltersModel
FILTERS_MODEL_BY_CATEGORY: dict[DabangCategory, type[DabangFiltersModel]] = {
    'one-two': DabangOneTwoFiltersModel,
    'house-villa': DabangHouseVillaFiltersModel,
    'officetel': DabangOfficetelFiltersModel,
    'apt': DabangAptFiltersModel,
}


class DabangPointModel(RequestModel):
    """지도 범위의 꼭짓점."""

    lat: Annotated[
        float,
        Field(ge=-90, le=90, description='위도')
    ]
    lng: Annotated[
        float,
        Field(ge=-180, le=180, description='경도')
    ]


class DabangBboxModel(RequestModel):
    """지도 범위 (남서·북동 꼭짓점)."""

    sw: Annotated[
        DabangPointModel,
        Field(description='남서 꼭짓점')
    ]
    ne: Annotated[
        DabangPointModel,
        Field(description='북동 꼭짓점')
    ]


class DabangCategoryListRequestParameterModel(RequestModel):
    """매물·단지 지도 목록(`.../category/{category}/{search_type}`)의 공통 쿼리.

    `filters`·`bbox` 는 JSON 문자열로 보낸다. `zoom` 과 `useMap` 은 동·역 검색에도 필수다 (빠지면 400 "줌은 필수값 입니다",
    2026-10-25 실측). 한 쪽 크기는 24건 고정이고 `limit` 을 보내도 무시한다.

    Args:
        category: 매물 유형 (경로).
        search_type: 찾는 방식 (경로). region 은 `code`, subway·univ 는 `id`, bbox 는 `bbox` 가 있어야 한다.
        filters: 매물 유형에 맞는 필터.
        code: 법정동 코드 앞 8자리 (region).
        id: 역·대학 번호 (subway·univ).
        bbox: 지도 범위 (bbox).
        zoom: 지도 확대 수준. 웹 값(동 14, 역 15, 지도 16)을 쓴다.
        use_map: 지도 종류. 웹은 늘 'naver'.
        page: 쪽 번호 (1부터).
    """

    category: Annotated[
        DabangCategory,
        Field(exclude=True, description='매물 유형 (경로)')
    ]
    search_type: Annotated[
        DabangSearchType,
        Field(exclude=True, description='찾는 방식 (경로)')
    ]
    filters: Annotated[
        DabangListFilters,
        Field(description='매물 유형 필터 (JSON 으로 보낸다)')
    ]
    code: Annotated[
        str | None,
        Field(pattern=r'^\d{8}$', description='법정동 코드 앞 8자리 (region)')
    ] = None
    id: Annotated[
        int | None,
        Field(gt=0, description='역·대학 번호 (subway·univ)')
    ] = None
    bbox: Annotated[
        DabangBboxModel | None,
        Field(description='지도 범위 (bbox, JSON 으로 보낸다)')
    ] = None
    zoom: Annotated[
        int,
        Field(ge=1, le=21, description='지도 확대 수준')
    ]
    use_map: Annotated[
        Literal['naver'],
        Field(description='지도 종류', alias='useMap')
    ] = 'naver'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호 (1부터)')
    ] = 1

    @field_serializer('filters', 'bbox')
    def as_json(self, value: DabangListFilters | DabangBboxModel | None) -> str | None:
        return None if value is None else value.model_dump_json(by_alias=True)

    @model_validator(mode='after')
    def target_matches_search_type(self) -> Self:
        if self.search_type == 'region' and self.code is None:
            raise ValueError('동 검색(region)에는 법정동 코드(code)가 있어야 합니다')
        if self.search_type in ('subway', 'univ') and self.id is None:
            raise ValueError('역·대학 검색에는 번호(id)가 있어야 합니다')
        if self.search_type == 'bbox' and self.bbox is None:
            raise ValueError('지도 범위 검색(bbox)에는 bbox 가 있어야 합니다')
        if self.category == 'apt' and self.search_type in ('region', 'univ'):
            # 아파트는 지도 범위·역 검색만 있다. 동 검색 주소는 403 빈 응답이다 (없는 주소와 같다, 2026-10-25 실측)
            raise ValueError('다방 아파트 목록은 동·대학 검색을 받지 않습니다 (지도 범위·역만)')
        if not isinstance(self.filters, FILTERS_MODEL_BY_CATEGORY[self.category]):
            raise ValueError(f'{self.category} 목록에 맞지 않는 필터입니다: {type(self.filters).__name__}')
        return self


class DabangComplexV5RequestParameterModel(RequestModel):
    """`GET /api/v5/complex/{complex_id}` 의 경로 값.

    Args:
        complex_id: 단지 ID (28자리 16진수).
    """

    complex_id: Annotated[
        str,
        Field(exclude=True, pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID (경로)')
    ]


class DabangV3RequestParameterModel(RequestModel):
    """옛 방식(`/api/3/`) 엔드포인트의 공통 쿼리. 웹은 헤더 대신 주소 뒤에 이 값을 붙인다."""

    api_version: Annotated[
        Literal['3.0.1'],
        Field(description='API 버전')
    ] = '3.0.1'
    call_type: Annotated[
        Literal['web'],
        Field(description='부르는 곳')
    ] = 'web'
    version: Annotated[
        Literal['1'],
        Field(description='앱 버전')
    ] = '1'
