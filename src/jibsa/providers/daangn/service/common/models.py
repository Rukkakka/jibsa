"""당근 service 공통의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from collections.abc import (
    Mapping,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    Listing,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnAmountRangeModel,
    DaangnBuildingApprovalDate,
    DaangnDealType,
    DaangnFloor,
    DaangnOption,
    DaangnPropertyFilterModel,
    DaangnRoomCount,
    DaangnSalesType,
    DaangnSubSalesType,
    DaangnTradeType,
)

from typing import (
    Annotated,
    Any,
)


# 필터로 보내는 매물 종류. 원룸(ONE_ROOM)은 오픈형·분리형 원룸을 함께 찾는다
SALES_TYPE_BY_PROPERTY_TYPE: dict[str, DaangnSalesType] = {
    '아파트': 'APART',
    '오피스텔': 'OFFICETEL',
    '원룸': 'ONE_ROOM',
    '투룸': 'TWO_ROOM',
    '주택': 'HOUSE',
    '상가': 'STORE',
    '사무실': 'OFFICE',
    '건물': 'BUILDING',
    '토지': 'LAND',
    '공장·창고': 'FACTORY',
}


TRADE_FILTER_BY_TRADE_TYPE: dict[str, DaangnTradeType] = {
    '월세': 'MONTH',
    '전세': 'BORROW',
    '매매': 'BUY',
    '단기임대': 'SHORT',
    '연세': 'YEAR',
}


# 아래 필터 라벨은 당근 웹 지도 필터의 이름 그대로다 (띄어쓰기만 뺐다)
FLOOR_FILTER_BY_LABEL: dict[str, DaangnFloor] = {
    '반지하': 'SEMI_BASEMENT',
    '1층': 'FIRST',
    '2~5층': 'SECOND_TO_FIFTH',
    '6~9층': 'SIX_TO_NINTH',
    '10층이상': 'TENTH_OR_MORE',
}


ROOM_COUNT_FILTER_BY_LABEL: dict[str, DaangnRoomCount] = {
    '2개': 'TWO',
    '3개': 'THREE',
    '4개이상': 'FOUR_OR_MORE',
}


STRUCTURE_FILTER_BY_LABEL: dict[str, DaangnSubSalesType] = {
    '오픈형': 'OPEN_ROOM',
    '분리형': 'SPLIT_ROOM',
}


BUILDING_APPROVAL_FILTER_BY_LABEL: dict[str, DaangnBuildingApprovalDate] = {
    '5년이내': 'LESS_5YEARS',
    '10년이내': 'LESS_10YEARS',
    '15년이내': 'LESS_15YEARS',
    '20년이내': 'LESS_20YEARS',
    '25년이내': 'LESS_25YEARS',
    '30년이내': 'LESS_30YEARS',
    '30년이상': 'MORE_30YEARS',
}


DEAL_FILTER_BY_LABEL: dict[str, DaangnDealType] = {
    '직거래': 'DIRECT',
    '중개': 'BROKER',
}


OPTION_FILTER_BY_LABEL: dict[str, DaangnOption] = {
    '주차가능': 'PARKING',
    '반려동물가능': 'PET',
    '대출가능': 'MORTGAGE',
    '엘리베이터': 'ELEVATOR',
    '옥탑': 'ROOFTOP',
    '복층': 'LOFT',
}


# 단지마다 보여 줄 최근 실거래 수 (당근은 10건을 준다)
COMPLEX_RECENT_TRADES: int = 3


def region_name_parts(sido: str, sigungu: str = '', dong: str = '') -> dict[str, str]:
    """검색 중심 지역의 이름 칸 (`name`·`sido`·`sigungu`·`dong`). 출력의 지역 칸 규칙을 한 곳에 둔다.

    `name` 은 가장 작은 단위 이름이다 (동, 없으면 시·군·구, 없으면 시·도). 빈 단계는 해당 없음이라 키를 뺀다. 세종은 시·군·구가
    없어(당근이 name2 를 '' 로 준다) `sigungu` 가 없고, 구를 찾은 결과(지도 범위 검색)는 `dong` 이 없다.
    """
    parts = {'name': dong or sigungu or sido, 'sido': sido}
    if sigungu:
        parts['sigungu'] = sigungu
    if dong:
        parts['dong'] = dong
    return parts


class DaangnRegion(BaseModel):
    """조회한 동이나 구 (구는 `dong` 이 빈 문자열이다. 구 이름의 지도 범위 검색)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sido: Annotated[
        str,
        Field(description='시/도')
    ]
    sigungu: Annotated[
        str,
        Field(description='시/군/구. 세종처럼 없으면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    dong: Annotated[
        str,
        Field(description='읍/면/동. 구를 찾은 결과(지도 범위 검색)는 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]

    @model_validator(mode='before')
    @classmethod
    def ignore_name(cls, data: Any) -> Any:
        # 출력의 name 은 sido·sigungu·dong 에서 만든 값이라(`region_name_parts`) 이어 받기 표의 dump 를 다시 읽을 때는 버린다
        if isinstance(data, dict) and 'name' in data:
            return {key: value for key, value in data.items() if key != 'name'}
        return data

    @model_serializer
    def with_name(self) -> dict[str, Any]:
        return {**region_name_parts(self.sido, self.sigungu, self.dong), 'region_id': self.region_id}


class DaangnNearbyListing(Listing):
    """검색 중심(동 중심·역·대학·지도 화면 가운데·회사)에서 거리를 재는 당근 매물. 거리를 모르면 키를 빼지 않고 null(모름)로 낸다.

    공통 `Listing` 은 `distance_km` 가 None 이면 중심 없는 조회로 보고 키를 뺀다 (해당 없음). 중심이 있는데 매물 위치를
    모르면(주소를 숨긴 매물, `article_to_listing`) 해당 없음이 아니라 모름이다.
    """

    def not_applicable_fields(self) -> frozenset[str]:
        return super().not_applicable_fields() - {'distance_km'}


class DaangnKbEstimatedPrices(BaseModel):
    """KB 시세의 공통 칸. 출력 맨 앞에 출처 `provider`('KB부동산')를 붙인다. 거래 칸(`sale`·`jeonse`·`wolse`)은 이름 그대로 출력 키다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    base_date: Annotated[
        str | None,
        Field(description='KB 시세 조사 기준일 (YYYY-MM-DD)')
    ] = None

    @model_serializer(mode='wrap')
    def with_provider(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {'provider': 'KB부동산', **data}


def amount_range(low: int | None, high: int | None) -> DaangnAmountRangeModel | None:
    if low is None and high is None:
        return None
    return DaangnAmountRangeModel(min_amount=low, max_amount=high)


def label_codes(labels: list[str] | None, codes: Mapping[str, str]) -> list[str] | None:
    return [codes[label] for label in labels] if labels else None


class DaangnListingConditions(RequestModel):
    """매물 검색 조건 (한국어 라벨). 당근 웹 지도 필터(`property_filter`)와 받은 매물의 보여 줄 거래 고르기
    (`trade_of`)에 같이 쓴다. 매물 검색 명령은 모두 이 묶음을 넘긴다.

    라벨은 `PROPERTY_TYPES`·`TRADE_TYPES` 와 `*_FILTER_BY_LABEL` 의 키다. 만들 때 필터로 바꿔 보아
    조건 조합이 잘못됐으면 요청을 보내기 전에 멈춘다.

    Raises:
        ValidationError: 원룸이 아닌데 방 구조를, 아파트·오피스텔이 없는 유형에 세대수·주차대수를 줬을 때.
    """

    property_types: Annotated[
        list[str] | None,
        Field(description='매물 종류 (PROPERTY_TYPES)')
    ] = None
    trade_types: Annotated[
        list[str] | None,
        Field(description='거래 유형 (TRADE_TYPES)')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    yearly_rent_min: Annotated[
        int | None,
        Field(description='연세 하한 (만원)')
    ] = None
    yearly_rent_max: Annotated[
        int | None,
        Field(description='연세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    rent_includes_manage_cost: Annotated[
        bool,
        Field(description='월세 범위를 월세 + 관리비로 비교')
    ] = False
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    floors: Annotated[
        list[str] | None,
        Field(description='층 (FLOOR_FILTER_BY_LABEL)')
    ] = None
    room_counts: Annotated[
        list[str] | None,
        Field(description='방 개수 (ROOM_COUNT_FILTER_BY_LABEL)')
    ] = None
    structures: Annotated[
        list[str] | None,
        Field(description='원룸 방 구조 (STRUCTURE_FILTER_BY_LABEL)')
    ] = None
    building_approval: Annotated[
        str | None,
        Field(description='사용승인일 (BUILDING_APPROVAL_FILTER_BY_LABEL)')
    ] = None
    deal: Annotated[
        str | None,
        Field(description='거래 방식 (DEAL_FILTER_BY_LABEL)')
    ] = None
    options: Annotated[
        list[str] | None,
        Field(description='옵션 (OPTION_FILTER_BY_LABEL)')
    ] = None
    move_in_now: Annotated[
        bool,
        Field(description='즉시 입주')
    ] = False
    household_min: Annotated[
        int | None,
        Field(description='세대수 하한 (유형 전체·아파트·오피스텔)')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한 (유형 전체·아파트·오피스텔)')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한 (유형 전체·아파트·오피스텔)')
    ] = None

    _property_filter: DaangnPropertyFilterModel = PrivateAttr()

    def model_post_init(self, context: Any) -> None:
        self._property_filter = property_filter_of(self)

    @property
    def property_filter(self) -> DaangnPropertyFilterModel:
        """당근 웹 지도 필터 (`propertyFilter`). 조건이 없으면 빈 필터다."""
        return self._property_filter


def property_filter_of(conditions: DaangnListingConditions) -> DaangnPropertyFilterModel:
    """한국어 라벨 조건을 당근 웹 지도 필터(`propertyFilter`)로 바꾼다.

    Raises:
        ValidationError: 원룸이 아닌데 방 구조를, 아파트·오피스텔이 없는 유형에 세대수·주차대수를 줬을 때.
    """
    return DaangnPropertyFilterModel(
        sales_types=label_codes(conditions.property_types, SALES_TYPE_BY_PROPERTY_TYPE) or [],
        trade_types=label_codes(conditions.trade_types, TRADE_FILTER_BY_TRADE_TYPE),
        deposit_pay=amount_range(conditions.deposit_min, conditions.deposit_max),
        monthly_pay=amount_range(conditions.rent_min, conditions.rent_max),
        yearly_pay=amount_range(conditions.yearly_rent_min, conditions.yearly_rent_max),
        price_pay=amount_range(conditions.price_min, conditions.price_max),
        monthly_pay_includes_manage_cost=conditions.rent_includes_manage_cost or None,
        min_area=conditions.area_min,
        max_area=conditions.area_max,
        floor=label_codes(conditions.floors, FLOOR_FILTER_BY_LABEL),
        room_counts=label_codes(conditions.room_counts, ROOM_COUNT_FILTER_BY_LABEL),
        sub_sales_types=label_codes(conditions.structures, STRUCTURE_FILTER_BY_LABEL),
        building_approval_date=label_codes(
            [conditions.building_approval] if conditions.building_approval else None,
            BUILDING_APPROVAL_FILTER_BY_LABEL,
        ),
        deal_type=DEAL_FILTER_BY_LABEL[conditions.deal] if conditions.deal else None,
        options=label_codes(conditions.options, OPTION_FILTER_BY_LABEL),
        move_in_now=conditions.move_in_now or None,
        min_household_count=conditions.household_min,
        max_household_count=conditions.household_max,
        min_parking_per_household=conditions.parking_min,
    )


class DaangnRecentTrade(BaseModel):
    """단지 목록에 붙는 최근 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
            data.pop(field, None)
        return data


class DaangnRegionComplex(BaseModel):
    """지역 단지 목록의 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='당근 단지 ID (complex·items·real-price 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름. 당근이 주지 않으면 null')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...). 당근이 주지 않으면 null, 표에 없는 코드는 원래 코드')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (sale·jeonse·wolse)')
    ]
    recent_trades: Annotated[
        list[DaangnRecentTrade] | None,
        Field(description=(
            f'요청한 거래 유형의 최근 실거래 (최근 계약 순, 최대 {COMPLEX_RECENT_TRADES}건, 학교 배정 단지는 1건). 계약일·층은 없다. '
            '당근이 실거래 연결(transactions)이나 그 목록(edges)을 null 로 주면 null (모름), 거래가 없으면 []'
        ))
    ] = []
    near_station: Annotated[
        bool | None,
        Field(description='역에서 가까운 단지인지 (당근 기준). 모르면 null')
    ] = None
    has_reviews: Annotated[
        bool | None,
        Field(description='거주 후기가 있는지. 후기 요약이 없고 당근이 후기 연결(livedReviews)이나 그 목록(edges)을 null 로 주면 null (모름). 내용은 url 의 단지 페이지에서 본다')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지')
    ]
