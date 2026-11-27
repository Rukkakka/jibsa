"""실거래가·시세 흐름·단지 비교의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    AmountRange,
    AmountSet,
    Result,
    TradeType,
    with_floor_number,
)
from jibsa.providers.dabang.service.common.models import DabangAreaPrice
from jibsa.providers.dabang.service.real_price.constants import RealPriceTrade

from typing import (
    Annotated,
    Any,
    Literal,
)


# 매물 실거래 줄의 면적 칸. 단지 실거래는 평형으로 고르므로 면적이 없다(none). 매물 실거래는 웹처럼 다세대·연립(MULTIPLEX)이면
# 전용면적·층, 그 밖(DETACHED 단독·다가구)이면 연면적·주택유형(매매만)이다 (room 청크 `ii` 가 MULTIPLEX 만 `Kr`, 나머지는 `ei`)
AreaKind = Literal['none', 'exclusive', 'total_floor']


class DabangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 금액은 키가 없다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형 (매매·전세·월세)')
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 ('5', '지하1'). 모르면 null. 바로 뒤 floor_number 는 몇 층인지 아는 층의 숫자 (지하는 음수, 모르면 null)")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, --listing 의 다세대·연립 거래만. 단지는 평형으로 고른다)')
    ] = None
    total_floor_area_m2: Annotated[
        float | None,
        Field(description='연면적 (㎡, 다방 화면의 이름. --listing 의 단독·다가구 거래만. 매물 전용면적과 기준이 달라 그대로 견주지 않는다)')
    ] = None
    house_type: Annotated[
        str | None,
        Field(description="주택 유형 ('단독', '다가구', --listing 의 단독·다가구 매매만)")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금·전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제된 거래')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description="거래 방식 ('직거래'·'중개거래'). 다방이 직거래 여부를 주지 않으면 null")
    ] = None
    # 리뷰 오탐 (2026-11-13): 단독·다가구 줄에 isRegistration 이 없어 키를 빼야 한다는 지적. 웹 단독·다가구 표(room 청크 `ei`)도
    # 다세대 표처럼 `e.isRegistration` 이 참이면 등기 표시를 그린다. 다방이 이 줄에 값을 주지 않을 뿐이라 해당 없음이 아니라 모름(null)이다
    registered: Annotated[
        bool | None,
        Field(description='등기된 거래 (다방 화면의 등기 표시). 다방이 주지 않으면 null (단독·다가구 거래)')
    ] = None
    newly_added: Annotated[
        bool | None,
        Field(description='다방이 새 거래로 표시한 거래 (화면의 새 거래 표시)')
    ] = None
    area_kind: Annotated[
        AreaKind,
        Field(exclude=True, description='낼 면적 키 (단지 실거래는 없음)')
    ] = 'none'

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        dropped = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.area_kind != 'exclusive':
            dropped.add('area_m2')
        if self.area_kind != 'total_floor':
            dropped |= {'total_floor_area_m2', 'house_type'}
        else:
            # 웹 단독·다가구 표에는 층 칸이 없고(`ei`) 원본 층도 'null' 글자다. 주택유형은 매매 표에만 있다
            dropped.add('floor')
            if self.trade_type != '매매':
                dropped.add('house_type')
        for field in dropped:
            data.pop(field, None)
        return with_floor_number(data)


class DabangRealPriceResult(Result):
    """실거래 내역.

    `notes`: 평형·범위 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 실거래만)')
    ] = None
    listing_id: Annotated[
        str | None,
        Field(description='매물 ID (--listing 만)')
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID (단지 실거래만)')
    ] = None
    trade_tab: Annotated[
        RealPriceTrade,
        Field(description='매매 또는 전월세')
    ]
    start_month: Annotated[
        str,
        Field(description='조회 시작 달 (YYYY-MM)')
    ]
    end_month: Annotated[
        str,
        Field(description='조회 끝 달 (YYYY-MM)')
    ]
    basis: Annotated[
        str | None,
        Field(description=(
            "거래를 모은 범위 (--listing 만): '이 집 (망원동 다세대·연립)' 은 이 매물과 같은 지번 건물, '역삼동 단독·다가구' 는 "
            '그 동의 같은 건물 유형. 다방이 범위를 알려 주지 않으면 null'
        ))
    ] = None
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='기간 안에 더 오래된 거래가 더 있는지')
    ]
    trades: Annotated[
        list[DabangRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    url: Annotated[
        str,
        Field(description='단지·매물 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('complex_id', 'listing_id', 'pyeong_id'):
            if data.get(key) is None:
                data.pop(key, None)
        # 기준 범위는 매물 실거래(--listing)에만 해당한다. 그때 비면 모름(null)으로 남긴다
        if self.listing_id is None:
            data.pop('basis', None)
        return data


class DabangTrendMonth(BaseModel):
    """시세 흐름의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='달 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ] = None
    trade_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 평균 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 늘 두 개. 거래 없는 달은 다방이 앞 달 평균을 "
            '잇고, 이을 평균도 없으면 그 거래가 null'
        ))
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 거래 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (모르면 null)")
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='그 달 전세가율 (%, 다방 갭 그래프). 매매·전세 평균이 없으면 null')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='그 달 매매 평균 − 전세 평균 (만원, 다방 갭 그래프). 없으면 null')
    ] = None


class DabangTradeAverage(AmountSet):
    """최근 평균 (만원). 매매는 평당 평균(`price_per_pyeong_manwon`)도 함께 낸다."""

    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당 평균 (만원). 매매에만 있다')
    ] = None


class DabangPriceTrend(Result):
    """평형 하나의 시세 흐름 (월별 평균 실거래가, 국토부 신고 기준).

    `notes`: 평형 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID')
    ]
    trade_averages: Annotated[
        dict[str, DabangTradeAverage | None],
        Field(description=(
            "거래별 최근 평균 (만원). 키는 'sale'(price_manwon, 평당 평균 price_per_pyeong_manwon)·'jeonse'(deposit_manwon) 늘 두 개이고 "
            '다방이 그 거래 평균을 주지 않으면 그 거래가 null. 일부 칸만 모르면 그 칸만 null'
        ))
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='전세가율 (%) = 전세 평균 / 매매 평균')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='매매 평균 − 전세 평균 (만원)')
    ] = None
    trade_ranges: Annotated[
        dict[str, dict[str, AmountRange | None] | None] | None,
        Field(description=(
            "기간별 최저·최고 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 아래 기간 'one_year'·'three_years'이고, 기간 안 "
            '두 끝을 모두 모르면 그 기간은 null, 두 기간 모두 모르면 그 거래가 null. 다방이 기간별 값을 주지 않으면 전체가 null'
        ))
    ] = None
    months: Annotated[
        list[DabangTrendMonth],
        Field(description='오래된 달부터 36달')
    ]


class DabangNearbyComplex(BaseModel):
    """반경 1km 주변 단지 하나 (평당가 비교)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (complex·real-price 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (동까지, '서울특별시 강남구 대치동')")
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description="그 평형대 평당가 (만원). nearby 의 'sale' 아래는 매매, 'jeonse' 아래는 전세. 다방 웹이 빈 칸으로 두는 값은 null")
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description="입주 N년차 (사용승인한 해를 1년차로 센다. 다방 '입주 37년차')")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='이 단지에서 거리 (m, 다방 값. 웹 목록은 거리를 그리지 않는다)')
    ] = None


class DabangNearbyComplexes(Result):
    """단지 평형대 평당가와 반경 1km 주변 단지 비교 (다방 웹 단지 화면 평당가 칸의 기본 탭 'N평대 비교').

    `notes`: 평형 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='고른 평형 ID (그 평형이 든 평형대로 비교한다)')
    ]
    # 리뷰 오탐 (2026-11-14): 'N평대 비교' 탭을 주지 않는 것은 다방이 값을 주지 않은 모름이라 키를 빼지 않고 null 로 둔다
    # (해당 없음 아님). 웹도 이때 이 탭을 그리지 않는다 (소스 가이드 평형대 평당가 비교)
    pyeong_range: Annotated[
        str | None,
        Field(description="비교한 평형대 (다방 탭 이름 '30평대 비교' 의 '30평대'). 다방이 이 평형에 평형대 탭을 주지 않으면 null")
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice] | None,
        Field(description=(
            "그 평형대의 평당 평균가 (이 단지·동·구, 만원). 다방 웹이 '정보 없음' 으로 쓰는 값(없거나 0)은 그 거래가 null. "
            "다방이 이 평형에 평형대 탭을 주지 않거나 이 목록을 null 로 주면 목록 전체가 null"
        ))
    ] = None
    nearby: Annotated[
        dict[str, list[DabangNearbyComplex] | None],
        Field(description=(
            "반경 1km 주변 단지의 거래별 평당가. 키는 'sale'·'jeonse' 늘 두 개. 'sale'은 다방 순서 그대로(평당가가 있는 단지를 가까운 "
            "순으로 앞에), 'jeonse'는 다방 웹 전월세 탭 순서 그대로. 다방이 평형대 탭이나 주변 단지(nearComplexes)나 그 거래 쪽을 "
            'null 로 주면 그 값이 null, 주었는데 그 쪽이 비었으면 []'
        ))
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
