from datetime import date

from pydantic import (
    Field,
    field_serializer,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    DabangBboxModel,
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
    Self,
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
# 청약 일정 한 번에 받을 수 있는 날 수. 그보다 길면 400 "최대 일주일의 데이터를 요청할 수 있습니다." (2026-10-25 실측: 10-26~11-01 은 200)
SALE_SCHEDULE_MAX_DAYS: int = 7


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


class DabangSaleInLotsDetail2V3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/detail2` 쿼리 (분양 단지 하나).

    Args:
        id: 분양 ID (28자리 16진수).
    """

    id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='분양 ID')
    ]


class DabangSaleInLotsListScheduleV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/list/schedule` 쿼리 (날짜별 청약 일정, 최대 7일).

    Args:
        from_date: 시작 날 (YYYY-MM-DD).
        to_date: 끝 날 (YYYY-MM-DD, 시작 날부터 7일 안).
    """

    from_date: Annotated[
        date,
        Field(description='시작 날', alias='from')
    ]
    to_date: Annotated[
        date,
        Field(description='끝 날', alias='to')
    ]

    @field_serializer('from_date', 'to_date')
    def as_text(self, value: date) -> str:
        return value.isoformat()

    @model_validator(mode='after')
    def within_a_week(self) -> Self:
        days = (self.to_date - self.from_date).days + 1
        if days < 1:
            raise ValueError(f'끝 날({self.to_date})이 시작 날({self.from_date})보다 빠릅니다')
        if days > SALE_SCHEDULE_MAX_DAYS:
            raise ValueError(f'다방 청약 일정은 한 번에 {SALE_SCHEDULE_MAX_DAYS}일까지 받습니다 ({days}일)')
        return self
