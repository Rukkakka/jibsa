"""단지 비교와 주변 단지의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    AmountSet,
    NumberRange,
    Result,
    with_floor_number,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnKbEstimatedPrices,
    DaangnRegion,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnAskingAverage(AmountSet):
    """호가 매물의 평균 금액 (만원). 금액 칸은 거래에 맞는 것 하나다 (매매 `price_manwon`, 전세·월세 `deposit_manwon`)."""

    count: Annotated[int, Field(description='평균을 낸 거래 조건 수')]


class DaangnCompareSchool(BaseModel):
    """배정 학교."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    distance_m: Annotated[
        float | None,
        Field(description='거리 (m, 당근 값 그대로. 소수일 수 있다)')
    ] = None
    walk_minutes: Annotated[
        float | None,
        Field(description='도보 (분, 당근 값 그대로. 소수일 수 있다)')
    ] = None


class DaangnCompareSubway(BaseModel):
    """주변 역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[str, Field(description="역 이름 ('역' 까지)")]
    line: Annotated[
        str | None,
        Field(description='노선 (예: 2호선)')
    ] = None
    distance_m: Annotated[
        float | None,
        Field(description='거리 (m, 당근 값 그대로. 소수일 수 있다)')
    ] = None
    walk_minutes: Annotated[
        float | None,
        Field(description='도보 (분, 당근 값 그대로. 소수일 수 있다)')
    ] = None


class DaangnKbRange(BaseModel):
    """KB 시세 범위 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    low_manwon: Annotated[
        int | None,
        Field(description='하위가')
    ] = None
    mid_manwon: Annotated[
        int | None,
        Field(description='일반가')
    ] = None
    high_manwon: Annotated[
        int | None,
        Field(description='상위가')
    ] = None


class DaangnKbMonthly(BaseModel):
    """KB 월세 시세 (만원). 웹은 '보증금 / 월세 상위' 와 그 아래 '월차임 하위~상위' 로 보여 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    deposit_manwon: Annotated[
        int | None,
        Field(description='보증금')
    ] = None
    rent_low_manwon: Annotated[
        int | None,
        Field(description='월세 하위')
    ] = None
    rent_high_manwon: Annotated[
        int | None,
        Field(description='월세 상위')
    ] = None


class DaangnCompareEstimatedPrices(DaangnKbEstimatedPrices):
    """KB 시세 (출처 `provider`, 기준일 `base_date`). 거래 칸(sale·jeonse·wolse)이 키이고, 그 거래의 시세가 없으면 null 이다."""

    sale: Annotated[
        DaangnKbRange | None,
        Field(description='KB 매매 시세')
    ] = None
    jeonse: Annotated[
        DaangnKbRange | None,
        Field(description='KB 전세 시세')
    ] = None
    wolse: Annotated[
        DaangnKbMonthly | None,
        Field(description='KB 월세 시세')
    ] = None


class DaangnCompareRecentTrade(BaseModel):
    """평형 최근 실거래 하나 (만원). 거래 유형에 없는 금액은 키를 뺀다 (해당 없음: 매매는 보증금·월세, 전세는 매매가·월세, 월세는 매매가)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예: '3', '지하1'). 숫자는 floor_number")
    ] = None
    price_manwon: Annotated[
        int | None,
        Field(description='매매가 (매매만)')
    ] = None
    deposit_manwon: Annotated[
        int | None,
        Field(description='보증금 (전세·월세만)')
    ] = None
    rent_manwon: Annotated[
        int | None,
        Field(description='월세 (월세만)')
    ] = None
    trade_type: Annotated[
        Literal['매매', '전세', '월세'],
        Field(exclude=True, description='거래 유형. 해당 없는 금액 키를 고르는 데만 쓴다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 전세 칸도 월세 기준으로 빼면 당근이 주는 월세 0 이 'rent_manwon: 0' 으로 남았다 (2026-11-12 리뷰)
        for field in NOT_APPLICABLE_PRICE_FIELDS[self.trade_type]:
            data.pop(field, None)
        return with_floor_number(data)


class DaangnComparePyeong(BaseModel):
    """비교한 평형 하나의 KB 시세와 최근 실거래 (당근 웹 비교 화면이 단지마다 고르는 평형)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (아파트형 단지, real-price·price-trend --pyeong). 아니면 키가 없다')
    ] = None
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음. 아파트형이 아닌 단지만 real-price·price-trend --area 에 넘긴다 (아파트형은 pyeong 을 --pyeong 에)')
    ] = None
    representative: Annotated[
        bool,
        Field(description='대표 평형 묶음인지')
    ] = False
    type_name: Annotated[
        str | None,
        Field(description="평형 타입 (예: 'A')")
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='이 평형 세대수')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    estimated_prices: Annotated[
        DaangnCompareEstimatedPrices | None,
        Field(description='KB 시세. 세 거래와 기준일이 모두 없으면 null, 아니면 sale·jeonse·wolse 키를 늘 두고 시세가 없는 거래는 null')
    ] = None
    latest_trades: Annotated[
        dict[str, DaangnCompareRecentTrade | None],
        Field(description=(
            '이 평형의 거래별 최근 실거래 (sale·jeonse·wolse). 최근 실거래가 없는 거래는 키가 없고, 세 거래 모두 없으면 {}. '
            '당근이 실거래 칸이나 그 목록을 주지 않거나 목록에 빈 항목이 섞이면 있는지 몰라 그 거래 키가 null, 빈 목록이면 키 없음'
        ))
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 공급 평형 묶음은 아파트형 단지에만 있다
        data: dict[str, Any] = handler(self)
        if self.pyeong is None:
            data.pop('pyeong', None)
        return data


class DaangnComplexComparison(BaseModel):
    """단지 하나의 비교 칸. 후기 요약 글은 내보내지 않는다 (후기 수만)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소 (첫 건물)')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소 (첫 건물)')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 꼭대기 층수의 최소(lowest)·최대(highest). 모르면 null')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='현재 매물 수')
    ] = None
    asking_averages: Annotated[
        dict[str, DaangnAskingAverage],
        Field(description=(
            "현재 호가 매물(아파트 매물 앞 30건)의 거래별 평균 (당근 웹 비교 화면의 '평균 호가'). 거래 키(sale·jeonse·wolse)이고 월세는 웹처럼 보증금 평균이다. "
            '매물이 없는 거래는 키가 없고 세 거래 모두 없으면 {}'
        ))
    ] = {}
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='비교한 평형의 월 관리비 추정 (만원, K-apt). 받은 달들의 ㎡당 관리비 평균 × 전용면적이다 (웹과 같다)')
    ] = None
    manage_cost_per_m2_manwon: Annotated[
        float | None,
        Field(description='받은 달들의 ㎡당 관리비 평균 (만원, K-apt)')
    ] = None
    manage_cost_period: Annotated[
        str | None,
        Field(description='관리비 평균을 낸 달 (YYYY-MM~YYYY-MM)')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수 (내용은 url 에서)')
    ] = None
    schools: Annotated[
        list[DaangnCompareSchool] | None,
        Field(description='배정 학교. 단지 공공 정보가 없으면 null (모름)')
    ] = None
    stations: Annotated[
        list[DaangnCompareSubway] | None,
        Field(description='주변 역. 단지 공공 정보가 없으면 null (모름)')
    ] = None
    pyeong: Annotated[
        DaangnComparePyeong | None,
        Field(description='비교한 평형의 시세·실거래 (첫 단지는 대표 평형, 나머지는 그 전용면적과 가장 비슷한 평형). 단지 공공 정보가 없으면 null (모름)')
    ] = None
    url: Annotated[str, Field(description='당근 단지 페이지')]


class DaangnCompareResult(Result):
    """단지 비교 결과.

    `notes`: 비교한 평형 기준과 평균 호가 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    returned: Annotated[int, Field(description='비교한 단지 수')]
    complexes: Annotated[list[DaangnComplexComparison], Field(description='넣은 순서대로 단지')]


class DaangnNearbyComplex(BaseModel):
    """같은 동 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (sale·jeonse·wolse)')
    ]


class DaangnNearbyComplexesResult(Result):
    """같은 동 단지 목록.

    `notes`: 조회 한도 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='기준 단지 ID')]
    region: Annotated[DaangnRegion, Field(description='기준 단지가 있는 동')]
    total: Annotated[
        int | None,
        Field(description='기준 단지를 뺀 같은 동 단지 수 (limit 적용 전). 1200곳에서 잘리면 notes 로 알린다. 당근이 빈 항목을 줘 셀 수 없으면 null')
    ]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    sort: Annotated[str, Field(description="정렬. 늘 '세대수' (많은 순. jibsa 정렬이며 웹 검색 엔진용 본문은 단지 ID 순 10곳이다)")]
    complexes: Annotated[list[DaangnNearbyComplex], Field(description='세대수 많은 순 단지')]
