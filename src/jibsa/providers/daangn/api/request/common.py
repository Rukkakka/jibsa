"""여러 기능이 같이 쓰는 요청 모델·필터 값과 기반 모델."""

from math import isfinite

from pydantic import (
    Field,
    SerializationInfo,
    field_serializer,
    model_validator,
)

from jibsa.core.korean import particle
from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Any,
    Literal,
    Self,
)


# 아래 코드값은 당근 웹(realty.daangn.com) 지도 필터가 보내는 값 그대로다. 모르는 값을 보내면
# 서버가 이유 없이 "알 수 없는 오류" 를 주므로 Literal 로 미리 막는다.
DaangnSalesType = Literal[
    'APART', 'ONE_ROOM', 'TWO_ROOM', 'OFFICETEL', 'STORE', 'HOUSE', 'OFFICE', 'BUILDING', 'FACTORY', 'LAND',
]
# 연세(YEAR)는 1년치 월세를 한 번에 내는 제주 거래다. 웹은 제주에서만 '연세' 칩을 보여 주지만 서버는 어느 지역에서나
# 받는다 (2026-11-13 실측: 노형동 tradeTypes ['YEAR'] 는 연세 매물만)
DaangnTradeType = Literal['MONTH', 'BORROW', 'BUY', 'SHORT', 'YEAR']
DaangnFloor = Literal['SEMI_BASEMENT', 'FIRST', 'SECOND_TO_FIFTH', 'SIX_TO_NINTH', 'TENTH_OR_MORE']
DaangnRoomCount = Literal['TWO', 'THREE', 'FOUR_OR_MORE']
DaangnSubSalesType = Literal['OPEN_ROOM', 'SPLIT_ROOM']
DaangnBuildingApprovalDate = Literal[
    'LESS_5YEARS', 'LESS_10YEARS', 'LESS_15YEARS', 'LESS_20YEARS', 'LESS_25YEARS', 'LESS_30YEARS', 'MORE_30YEARS',
]
DaangnDealType = Literal['DIRECT', 'BROKER']
DaangnOption = Literal['PARKING', 'PET', 'MORTGAGE', 'ELEVATOR', 'ROOFTOP', 'LOFT']


def _validate_range(low: float | None, high: float | None, label: str) -> None:
    if any(value is not None and not isfinite(value) for value in (low, high)):
        raise ValueError(f"{label}{particle(label, '은/는')} 유한한 숫자여야 합니다")
    if low is not None and high is not None and low > high:
        raise ValueError(f'{label} 하한은 상한보다 클 수 없습니다')


def _validate_area_household(
    model: 'DaangnPropertyFilterModel | DaangnComplexFilterModel',
) -> None:
    """매물·단지 조건에 같이 있는 면적·세대수·주차 범위를 검사하고, 면적 조건이 있으면 단위를 채운다."""
    _validate_range(model.min_area, model.max_area, '면적')
    _validate_range(model.min_household_count, model.max_household_count, '세대수')
    _validate_range(model.min_parking_per_household, None, '세대당 주차 대수')
    if model.min_area is not None or model.max_area is not None:
        model.area_unit = 'SQUARE_METER'


def _area_text(value: float | None) -> str | None:
    # 면적은 문자열로 보내야 한다. 숫자로 보내면 "알 수 없는 오류" 가 난다. 1e+06 같은 지수 표기도 서버가
    # 숫자로 읽는다 (2026-10-10 실측: --area-max 999999·1000000·1234567 결과 수가 같았다). 유효숫자 6자리라 1만㎡ 미만은
    # 소수 둘째 자리까지 그대로 가고(84.95 → '84.95'), 그보다 큰 값이 반올림돼도 결과 수가 같아 경계가 바뀌지 않는다.
    # 2026-10-18 리뷰 오탐 확인
    return None if value is None else f'{value:g}'


class DaangnAmountRangeModel(RequestModel):
    """금액 범위 (만원). 한쪽만 줘도 된다."""

    min_amount: Annotated[
        int | None,
        Field(ge=0, description='하한 (만원)', alias='minAmount')
    ] = None
    max_amount: Annotated[
        int | None,
        Field(ge=0, description='상한 (만원)', alias='maxAmount')
    ] = None

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        _validate_range(self.min_amount, self.max_amount, '금액')
        return self


class DaangnPropertyFilterModel(RequestModel):
    """`articleFeed` 의 `input.propertyFilter`. 당근 웹 지도 필터와 같은 조건이다.

    빈 목록·꺼진 조건은 웹처럼 보내지 않도록 None 으로 둔다. `salesTypes` 만은 웹이 늘
    보내므로 빈 목록(전체)도 보낸다.
    """

    sales_types: Annotated[
        list[DaangnSalesType],
        Field(description='매물 종류. 빈 목록이면 전체. ONE_ROOM 은 오픈형·분리형 원룸을 함께 찾는다', alias='salesTypes')
    ] = []
    trade_types: Annotated[
        list[DaangnTradeType] | None,
        Field(min_length=1, description='거래 유형', alias='tradeTypes')
    ] = None
    deposit_pay: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='보증금·전세금 범위 (만원)', alias='depositPay')
    ] = None
    monthly_pay: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='월세 범위 (만원)', alias='monthlyPay')
    ] = None
    yearly_pay: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='연세 범위 (만원). 웹은 제주에서만 보여 준다 (PriceFiltersSection 의 isJeju)', alias='yearlyPay')
    ] = None
    price_pay: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='매매가 범위 (만원)', alias='pricePay')
    ] = None
    monthly_pay_includes_manage_cost: Annotated[
        bool | None,
        Field(description='True 면 월세 범위를 월세 + 관리비로 비교한다', alias='monthlyPayIncludesManageCost')
    ] = None
    min_area: Annotated[
        float | None,
        Field(ge=0, description='전용면적 하한 (㎡)', alias='minArea')
    ] = None
    max_area: Annotated[
        float | None,
        Field(ge=0, description='전용면적 상한 (㎡)', alias='maxArea')
    ] = None
    area_unit: Annotated[
        Literal['SQUARE_METER'] | None,
        Field(description='면적 단위. 면적 조건이 있으면 자동으로 SQUARE_METER', alias='areaUnit')
    ] = None
    floor: Annotated[
        list[DaangnFloor] | None,
        Field(min_length=1, description='층')
    ] = None
    room_counts: Annotated[
        list[DaangnRoomCount] | None,
        Field(min_length=1, description='방 개수', alias='roomCounts')
    ] = None
    sub_sales_types: Annotated[
        list[DaangnSubSalesType] | None,
        Field(min_length=1, description='원룸 방 구조 (오픈형·분리형)', alias='subSalesTypes')
    ] = None
    building_approval_date: Annotated[
        list[DaangnBuildingApprovalDate] | None,
        Field(min_length=1, max_length=1, description='사용승인일. 웹은 하나만 골라 목록으로 보낸다', alias='buildingApprovalDate')
    ] = None
    deal_type: Annotated[
        DaangnDealType | None,
        Field(description='거래 방식 (직거래·중개)', alias='dealType')
    ] = None
    options: Annotated[
        list[DaangnOption] | None,
        Field(min_length=1, description='기타 조건 (주차·반려동물·대출·엘리베이터·옥탑·복층)')
    ] = None
    move_in_now: Annotated[
        bool | None,
        Field(description='True 면 즉시 입주 가능한 매물만', alias='moveInNow')
    ] = None
    min_household_count: Annotated[
        int | None,
        Field(ge=0, description='단지 세대수 하한 (유형 전체·아파트·오피스텔)', alias='minHouseholdCount')
    ] = None
    max_household_count: Annotated[
        int | None,
        Field(ge=0, description='단지 세대수 상한 (유형 전체·아파트·오피스텔)', alias='maxHouseholdCount')
    ] = None
    min_parking_per_household: Annotated[
        float | None,
        Field(ge=0, description='세대당 주차 대수 하한 (유형 전체·아파트·오피스텔)', alias='minParkingPerHousehold')
    ] = None

    @model_validator(mode='after')
    def validate_conditions(self) -> Self:
        _validate_area_household(self)
        if self.sub_sales_types and 'ONE_ROOM' not in self.sales_types:
            raise ValueError('방 구조(오픈형·분리형) 조건은 원룸을 찾을 때만 쓸 수 있습니다')
        complex_conditions = (self.min_household_count, self.max_household_count, self.min_parking_per_household)
        # 웹은 유형을 고르지 않았거나(전체) 아파트·오피스텔이 들어 있을 때만 세대수·주차대수 조건을 보낸다 (ChatPanelActionsContext
        # 의 `Gc`). 서버도 그때 실제로 건다 (2026-11-11 실측: 역삼동 전체 1000 → 세대수 1000 이상 40건, 오피스텔 895 → 0건)
        if any(value is not None for value in complex_conditions) and not (
            not self.sales_types or 'APART' in self.sales_types or 'OFFICETEL' in self.sales_types
        ):
            raise ValueError('세대수·주차대수 조건은 유형을 고르지 않거나 아파트·오피스텔을 넣어 찾을 때 쓸 수 있습니다')
        return self

    @field_serializer('min_area', 'max_area')
    def serialize_area(self, value: float | None) -> str | None:
        return _area_text(value)


def is_empty_property_filter(property_filter: DaangnPropertyFilterModel) -> bool:
    """조건이 하나도 없는 필터인지 (웹 지도 필터 atom 이 null 인 상태. `salesTypes` 는 늘 있어 빈 목록이면 없는 것으로 본다).

    기본값 모델과 비교해, None 이 아닌 기본값을 가진 필드가 늘어도 빈 조건으로 본다 (2026-11-12 리뷰).
    """
    return property_filter == DaangnPropertyFilterModel()


def with_null_property_filter(
    property_filter: DaangnPropertyFilterModel,
    data: dict[str, Any],
    info: SerializationInfo,
) -> dict[str, Any]:
    """`input` 모델의 매물 조건이 하나도 없으면 직렬화 결과에 null 로 넣는다 (`input` 모델의 `model_serializer` 용).

    웹은 동 클러스터 목록(`articleByClusterId`)과 지역 거품(`articleClusters`)에 조건이 없으면 `propertyFilter: null` 을 명시해
    보낸다 (mapQueryFilter 의 atom 이 null, 2026-11-12 번들 대조). GraphQL 은 변수 생략과 null 을 구분할 수 있어 웹과 같게 null
    을 보낸다. client 가 변수를 `exclude_none` 으로 직렬화해도 여기서 넣은 null 은 남는다. 빈 조건인지(`is_empty_property_filter`)
    여기서 가려 부르는 쪽은 조건을 그대로 넘긴다. 예전에는 부르는 쪽이 빈 조건을 None 으로 바꿔 넘겨야 해서, 빠뜨리면 빈 필터
    `{salesTypes: []}` 가 나갔다 (2026-11-12 리뷰. 결과는 같았다: 역삼동 둘레 거품 142개·역삼동 6,426건).

    키 이름은 직렬화하는 이름을 따른다 (alias 면 `propertyFilter`, 아니면 `property_filter`). 늘 `propertyFilter` 로 넣으면 alias
    없이 직렬화할 때 `property_filter` 와 `propertyFilter: None` 이 함께 나왔다 (2026-11-12 리뷰).
    """
    if is_empty_property_filter(property_filter):
        data['propertyFilter' if info.by_alias else 'property_filter'] = None
    return data


class DaangnCoordinateInputModel(RequestModel):
    """GraphQL 좌표 입력. 서버가 문자열만 받는다 (숫자로 보내면 "알 수 없는 오류")."""

    lat: Annotated[
        float,
        Field(ge=-90, le=90, description='위도')
    ]
    lon: Annotated[
        float,
        Field(ge=-180, le=180, description='경도')
    ]

    @field_serializer('lat', 'lon')
    def serialize_degree(self, value: float) -> str:
        return f'{value:.6f}'


class DaangnBoundsLocationFilterModel(RequestModel):
    """좌표 범위 지역 조건 (웹 지도 화면의 북동·남서 꼭짓점). 지도 범위 매물 목록·매물 수·지도 범위 단지 목록이 함께 쓴다."""

    ne_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='북동 꼭짓점', alias='neCoordinate')
    ]
    sw_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='남서 꼭짓점', alias='swCoordinate')
    ]


# 지역 단지 목록(웹 지도 단지 탭)의 코드값. 매물 조건(`DaangnSalesType` 등)과 이름·값이 다르다
DaangnComplexType = Literal['APARTMENT', 'OFFICETEL']
DaangnComplexTradeType = Literal['BUY', 'BORROW', 'MONTH']


class DaangnComplexFilterModel(RequestModel):
    """지역 단지 목록의 `input.propertyFilter` (웹의 complexFilter).

    지도 매물 조건(`DaangnPropertyFilterModel`)을 단지용 이름으로 옮긴 것이라 키가 다르다
    (`salesTypes` → `type`, `tradeTypes` → `tradeType`, `pricePay` → `price` ...). 매물 조건을 그대로
    보내면 "알 수 없는 오류" 가 난다. 아파트(APARTMENT)는 주상복합도 함께 찾는다.
    """

    type: Annotated[
        list[DaangnComplexType] | None,
        Field(min_length=1, description='단지 유형. 없으면 전체 (주상복합·도시형 포함)')
    ] = None
    trade_type: Annotated[
        list[DaangnComplexTradeType] | None,
        Field(min_length=1, description='거래 유형', alias='tradeType')
    ] = None
    deposit: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='보증금·전세금 범위 (만원)')
    ] = None
    monthly_pay: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='월세 범위 (만원)', alias='monthlyPay')
    ] = None
    price: Annotated[
        DaangnAmountRangeModel | None,
        Field(description='매매가 범위 (만원)')
    ] = None
    building_approval_date: Annotated[
        list[DaangnBuildingApprovalDate] | None,
        Field(min_length=1, max_length=1, description='사용승인일. 웹은 하나만 골라 목록으로 보낸다', alias='buildingApprovalDate')
    ] = None
    min_area: Annotated[
        float | None,
        Field(ge=0, description='전용면적 하한 (㎡)', alias='minArea')
    ] = None
    max_area: Annotated[
        float | None,
        Field(ge=0, description='전용면적 상한 (㎡)', alias='maxArea')
    ] = None
    area_unit: Annotated[
        Literal['SQUARE_METER'] | None,
        Field(description='면적 단위. 면적 조건이 있으면 자동으로 SQUARE_METER', alias='areaUnit')
    ] = None
    min_household_count: Annotated[
        int | None,
        Field(ge=0, description='세대수 하한', alias='minHouseholdCount')
    ] = None
    max_household_count: Annotated[
        int | None,
        Field(ge=0, description='세대수 상한', alias='maxHouseholdCount')
    ] = None
    min_parking_per_household: Annotated[
        float | None,
        Field(ge=0, description='세대당 주차 대수 하한', alias='minParkingPerHousehold')
    ] = None

    @model_validator(mode='after')
    def validate_area_unit(self) -> Self:
        _validate_area_household(self)
        return self

    @field_serializer('min_area', 'max_area')
    def serialize_area(self, value: float | None) -> str | None:
        return _area_text(value)


class DaangnExclusiveUseAreaModel(RequestModel):
    """단지마다 보여 줄 최근 실거래의 전용면적 범위 (㎡). 웹은 한쪽이 없으면 0 / 2^53-1 로 채운다."""

    min: Annotated[
        float,
        Field(ge=0, description='하한 (㎡)')
    ] = 0
    max: Annotated[
        float,
        Field(ge=0, description='상한 (㎡)')
    ] = 2 ** 53 - 1
