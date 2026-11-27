"""요청 모델: 분양 단지 목록 (search sales)."""

from pydantic import (
    Field,
    field_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    DabangBboxModel,
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
)


DabangSaleBuildingType = Literal['APT', 'OFFICETEL', 'URBAN_HOUSE', 'KNOWLEDGE_INDUSTRY_CENTER']
DabangSaleState = Literal['EXPECTED', 'ACCEPTING', 'ACCEPT_COMPLETE', 'MOVE_IN_EXPECTED', 'MOVE_IN_RECRUIT']
DabangSaleScheduleState = Literal[
    'RECRUITMENT', 'SPECIAL_SUPPLY', 'FIRST_PRIORITY', 'SECOND_PRIORITY', 'ACCEPTANCE', 'ANNOUNCEMENT',
    'CONTRACT_TERM', 'EXPECTED_MOVE_IN_DATE', 'COMPLETION_PERIOD',
]
DabangSaleSupplyType = Literal['PUBLIC_SALE', 'PRIVATE_SALE', 'PUBLIC_RENTAL', 'PRIVATE_RENTAL']
ALL_SALE_BUILDING_TYPES: tuple[DabangSaleBuildingType, ...] = ('APT', 'OFFICETEL', 'URBAN_HOUSE', 'KNOWLEDGE_INDUSTRY_CENTER')
ALL_SALE_STATES: tuple[DabangSaleState, ...] = ('EXPECTED', 'ACCEPTING', 'ACCEPT_COMPLETE', 'MOVE_IN_EXPECTED', 'MOVE_IN_RECRUIT')
ALL_SALE_SCHEDULE_STATES: tuple[DabangSaleScheduleState, ...] = (
    'RECRUITMENT', 'SPECIAL_SUPPLY', 'FIRST_PRIORITY', 'SECOND_PRIORITY', 'ACCEPTANCE', 'ANNOUNCEMENT',
    'CONTRACT_TERM', 'EXPECTED_MOVE_IN_DATE', 'COMPLETION_PERIOD',
)
ALL_SALE_SUPPLY_TYPES: tuple[DabangSaleSupplyType, ...] = ('PUBLIC_SALE', 'PRIVATE_SALE', 'PUBLIC_RENTAL', 'PRIVATE_RENTAL')
# 웹 분양 지역 목록(`list/search3`)의 필터는 이름 대신 번호다 (supply-type 청크의 `numValue`, 2026-11-13)
SALE_BUILDING_TYPE_NUMBERS: dict[DabangSaleBuildingType, int] = {'APT': 2, 'OFFICETEL': 0, 'URBAN_HOUSE': 1, 'KNOWLEDGE_INDUSTRY_CENTER': 3}
SALE_STATE_NUMBERS: dict[DabangSaleState, int] = {
    'EXPECTED': 0, 'ACCEPTING': 3, 'ACCEPT_COMPLETE': 4, 'MOVE_IN_EXPECTED': 5, 'MOVE_IN_RECRUIT': 2,
}
SALE_SUPPLY_TYPE_NUMBERS: dict[DabangSaleSupplyType, int] = {
    'PUBLIC_SALE': 0, 'PRIVATE_SALE': 1, 'PUBLIC_RENTAL': 4, 'PRIVATE_RENTAL': 5,
}

# 웹 분양 지역 목록의 쪽 크기 (list 청크 `limit:24`)
SALE_SEARCH_PAGE_SIZE: int = 24


class DabangSaleInLotsFiltersModel(RequestModel):
    """분양 지도 목록 필터. 웹 초기값처럼 주지 않은 항목은 모두 고른다 (filter-init 청크, 2026-10-25).

    Args:
        building_type_list: 건물 유형.
        state_list: 분양 상태 (분양예정·접수중·접수마감·입주예정·입주모집).
        schedule_state_list: 일정 단계. jibsa 는 늘 전체.
        supply_type_list: 공급 유형 (공공·민간 분양·임대).
    """

    building_type_list: Annotated[
        list[DabangSaleBuildingType],
        Field(min_length=1, description='건물 유형', alias='buildingTypeList')
    ] = list(ALL_SALE_BUILDING_TYPES)
    state_list: Annotated[
        list[DabangSaleState],
        Field(min_length=1, description='분양 상태', alias='stateList')
    ] = list(ALL_SALE_STATES)
    schedule_state_list: Annotated[
        list[DabangSaleScheduleState],
        Field(min_length=1, description='일정 단계', alias='scheduleStateList')
    ] = list(ALL_SALE_SCHEDULE_STATES)
    supply_type_list: Annotated[
        list[DabangSaleSupplyType],
        Field(min_length=1, description='공급 유형', alias='supplyTypeList')
    ] = list(ALL_SALE_SUPPLY_TYPES)


class DabangSaleListCategoryBboxV5RequestParameterModel(RequestModel):
    """`GET /api/v5/sale-list/category/bbox` 쿼리 (지도 범위 안 분양 단지, 24곳씩).

    Args:
        filters: 분양 필터 (JSON).
        bbox: 지도 범위 (JSON).
        zoom: 지도 확대 수준.
        use_map: 웹 값 'naver'.
        page: 쪽 번호 (1부터).
    """

    filters: Annotated[
        DabangSaleInLotsFiltersModel,
        Field(description='분양 필터 (JSON)')
    ] = Field(default_factory=DabangSaleInLotsFiltersModel)
    bbox: Annotated[
        DabangBboxModel,
        Field(description='지도 범위 (JSON)')
    ]
    zoom: Annotated[
        int,
        Field(ge=1, le=21, description='지도 확대 수준')
    ] = 14
    use_map: Annotated[
        Literal['naver'],
        Field(description='지도 종류', alias='useMap')
    ] = 'naver'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1

    @field_serializer('filters', 'bbox')
    def as_json(self, value: DabangSaleInLotsFiltersModel | DabangBboxModel) -> str:
        return value.model_dump_json(by_alias=True)


class DabangSaleInLotsSearchFiltersModel(RequestModel):
    """분양 지역 목록 필터 (번호 목록). 빈 목록이 전체다 (웹 초기값, 2026-11-13 list 청크).

    Args:
        building_type: 건물 유형 번호 (`SALE_BUILDING_TYPE_NUMBERS`).
        state: 분양 상태 번호 (`SALE_STATE_NUMBERS`).
        new_schedule_state: 일정 단계 번호. jibsa 는 늘 전체(빈 목록).
        supply_type: 공급 유형 번호 (`SALE_SUPPLY_TYPE_NUMBERS`).
    """

    building_type: Annotated[
        list[int],
        Field(description='건물 유형')
    ] = []
    state: Annotated[
        list[int],
        Field(description='분양 상태')
    ] = []
    new_schedule_state: Annotated[
        list[int],
        Field(description='일정 단계')
    ] = []
    supply_type: Annotated[
        list[int],
        Field(description='공급 유형')
    ] = []


class DabangSaleInLotsListSearch3V3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/list/search3` 쿼리 (웹 분양 지역 목록, 24곳씩).

    시·도·시·군·구를 주지 않으면 전국이다 (2026-11-13 웹 캡처: 전국 total 1143).

    Args:
        keyword: 웹 값 'ALL'.
        page: 쪽 번호 (1부터).
        limit: 쪽 크기 (웹 24. 더 크게 받는지는 확인하지 않았다).
        state_code: 시·도 코드 (2자리, `region/states`·`loc/state` 의 code). 전국은 없음.
        city_code: 시·군·구 코드 (5자리, `loc/city` 의 code). 시·도 전체·전국은 없음.
        filters: 필터 (JSON).
    """

    keyword: Annotated[
        Literal['ALL'],
        Field(description='검색어 (웹 값)')
    ] = 'ALL'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
    limit: Annotated[
        int,
        Field(ge=1, le=SALE_SEARCH_PAGE_SIZE, description='쪽 크기 (웹 값 24)')
    ] = SALE_SEARCH_PAGE_SIZE
    state_code: Annotated[
        str | None,
        Field(pattern=r'^\d{2}$', description='시·도 코드')
    ] = None
    city_code: Annotated[
        str | None,
        Field(pattern=r'^\d{5}$', description='시·군·구 코드')
    ] = None
    filters: Annotated[
        DabangSaleInLotsSearchFiltersModel,
        Field(description='필터 (JSON)')
    ] = Field(default_factory=DabangSaleInLotsSearchFiltersModel)

    @field_serializer('filters')
    def as_json(self, value: DabangSaleInLotsSearchFiltersModel) -> str:
        return value.model_dump_json()
