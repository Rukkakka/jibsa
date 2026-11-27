"""`info.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.zigbang.api.models.request.local.info import ZigbangPynAreaType
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice
from jibsa.providers.zigbang.service.local.models.common import (
    ZigbangLocalModel,
    ZigbangLocalRegion,
)

from typing import (
    Annotated,
    Literal,
)


class ZigbangRegionEstimatedPrice(BaseModel):
    """평형대 하나의 직방시세 (웹 지역 화면의 평형 탭). 직방이 실거래를 분석해 낸 추정값이고 실거래가가 아니다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_range: Annotated[
        str | None,
        Field(description="평형대 (웹 이름표 그대로: 전체·10평 이하·10평대~50평대·60평대 이상). `--range` 값('10평이하'·'60평대이상')과 빈칸이 다르다. 표에 없는 구분은 직방 글자 그대로")
    ]
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description="평균 직방시세. 'sale' 키 하나이고 안은 price_per_pyeong_manwon (평균 매매 평당가, 만원/3.3㎡). 직방이 주지 않으면 \"sale\": null")
    ]
    estimated_ranges: Annotated[
        dict[str, AmountRange | None],
        Field(description="직방시세 매매가 범위 (만원). 'sale' 키 하나이고 lowest 최저·highest 최고는 price_manwon. 두 끝이 모두 주지 않거나 0 이면 \"sale\": null, 한 끝만 그러면 그 price_manwon 만 null")
    ]


class ZigbangRegionMonthlyVolume(BaseModel):
    """한 달의 거래량 (건). 웹 그래프의 '전체' 는 세 거래 유형의 합이지만 합은 내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="거래 유형별 건수. 늘 'sale'·'jeonse'·'wolse' 세 키이고 직방이 주지 않은 유형은 null")
    ]


class ZigbangPriceTrendPoint(BaseModel):
    """평당가 추이의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ]
    price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 평당가 (만원/3.3㎡). 직방이 주지 않거나 0(값 없음)이면 null')
    ]


class ZigbangPriceTrendLine(BaseModel):
    """평당가 추이의 줄 하나 (단지 또는 그 지역)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='줄 이름 (직방이 준 label: 단지 이름 또는 지역 이름)')
    ]
    kind: Annotated[
        Literal['단지', '지역'] | None,
        Field(description="이름이 region.name 과 같으면 '지역', 아니면 '단지'. 줄 이름이나 지역 이름을 모르면 null")
    ]
    months: Annotated[
        list[ZigbangPriceTrendPoint] | None,
        Field(description='월별 평당가 (오래된 달부터). 직방이 주지 않으면 null')
    ]


class ZigbangPriceTrend(BaseModel):
    """지역 평당가 추이 그래프 (웹: 평당가 높은 단지 최대 3개와 지역 1줄)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_range: Annotated[
        ZigbangPynAreaType,
        Field(description="평형대 (--range 값: 전체·10평이하·10평대·20평대·30평대·40평대·50평대·60평대이상). by_pyeong_range[].pyeong_range 의 웹 이름표('10평 이하')와 빈칸이 다르다")
    ]
    lines: Annotated[
        list[ZigbangPriceTrendLine],
        Field(description='줄 (직방 순서: 평당가 높은 단지 최대 3개 다음에 지역). 줄이 1개 이하이면 웹은 그래프를 그리지 않아 notes 로 알린다')
    ]


class ZigbangPriceMovement(BaseModel):
    """시세 흐름 (웹 평당가 그래프 위 문구: '3주 연속 시세가 상승하고 있어요')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    streak_weeks: Annotated[
        int,
        Field(description='같은 흐름이 이어진 주 수')
    ]
    direction: Annotated[
        str,
        Field(description='흐름 (상승·하락·지속. 그 밖의 값이 오면 직방 글자 그대로)')
    ]


class ZigbangPopulationMonth(BaseModel):
    """한 달의 연령대별 인구 (명). 일곱 연령대의 합이 population 과 같다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM)')
    ]
    population: Annotated[
        int | None,
        Field(description='전체 인구 (명). 직방이 주지 않으면 null')
    ]
    age_0_9: Annotated[
        int | None,
        Field(description='0~9세 (명)')
    ]
    age_10_19: Annotated[
        int | None,
        Field(description='10~19세 (명)')
    ]
    age_20_29: Annotated[
        int | None,
        Field(description='20~29세 (명)')
    ]
    age_30_39: Annotated[
        int | None,
        Field(description='30~39세 (명)')
    ]
    age_40_49: Annotated[
        int | None,
        Field(description='40~49세 (명)')
    ]
    age_50_59: Annotated[
        int | None,
        Field(description='50~59세 (명)')
    ]
    age_60_over: Annotated[
        int | None,
        Field(description="60세 이상 (명). 직방 칸 이름은 age_60_69 지만 일곱 칸의 합이 전체와 같아 60세 이상 전체다 (2026-11-22 실측: 서울·송파구·성남시 분당구). 웹 범례는 '60대 이상'")
    ]


class ZigbangHouseholdMonth(BaseModel):
    """한 달의 가구원 수별 세대 (세대)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM)')
    ]
    household_count: Annotated[
        int | None,
        Field(description='전체 세대 (세대). 직방이 주지 않으면 null')
    ]
    one: Annotated[
        int | None,
        Field(description='1인 세대')
    ]
    two: Annotated[
        int | None,
        Field(description='2인 세대')
    ]
    three: Annotated[
        int | None,
        Field(description='3인 세대')
    ]
    four: Annotated[
        int | None,
        Field(description='4인 세대')
    ]
    five_plus: Annotated[
        int | None,
        Field(description='5인 이상 세대')
    ]


class ZigbangRegionPopulation(BaseModel):
    """구의 월별 인구와 세대 (웹 지역 화면의 인구·세대 그래프). 요청 기간은 웹과 같이 다섯 해 전 달부터 지난달까지다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    people: Annotated[
        list[ZigbangPopulationMonth] | None,
        Field(description='월별 연령대별 인구 (오래된 달부터). 직방이 빈 목록을 주면 [], 받지 못했으면 null')
    ]
    household_months: Annotated[
        list[ZigbangHouseholdMonth] | None,
        Field(description='월별 가구원 수별 세대 (오래된 달부터). 직방이 빈 목록을 주면 [], 받지 못했으면 null')
    ]


class ZigbangRegionInfoResult(ZigbangLocalModel, Result):
    """동·구의 지역 정보 (직방 웹 지역정보 화면 /home/apt/locals/{지역 코드}).

    `notes`: 덤 조회 실패 안내(조회를 받지 못했거나 직방이 목록을 주지 않았을 때의 `[실패]`)와 평당가 추이 줄이 모자란다는 안내. CLI 가 결과 위에 붙인다
    """

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    complex_count: Annotated[
        int | None,
        Field(description="단지 수 (웹 머리 '39 단지 · 23,634 세대' 의 글자에서 읽은 값). 읽지 못하면 null")
    ]
    household_count: Annotated[
        int | None,
        Field(description='세대수 (웹 머리 글자에서 읽은 값). 읽지 못하면 null')
    ]
    estimated_ranges: Annotated[
        dict[str, AmountRange | None],
        Field(description=(
            "전체 평형의 직방시세 매매가 범위 (만원. 웹 '매매 {최저} ~ {최고}'). 'sale' 키 하나이고 lowest 최저·highest 최고는 price_manwon. "
            '두 끝이 모두 주지 않거나 0 이면 "sale": null, 한 끝만 그러면 그 price_manwon 만 null'
        ))
    ]
    by_pyeong_range: Annotated[
        list[ZigbangRegionEstimatedPrice] | None,
        Field(
            description=(
                '평형대별 직방시세 (직방이 실거래를 분석한 추정값이며 실거래가가 아니다). 웹 평형 탭처럼 전체를 먼저, 그다음 작은 평형대부터이고 '
                '평균 매매 평당가나 전월세 평당가가 0 인 평형대는 뺀다. 직방이 주지 않으면 null, 모두 빠졌으면 []'
            )
        )
    ]
    monthly_volumes: Annotated[
        list[ZigbangRegionMonthlyVolume] | None,
        Field(
            description=(
                '월별 거래량 (직방 순서: 오래된 달부터, 약 37개월). 마지막 달은 이번 달이라 아직 채워지는 중이다. 거래량 조회를 받지 못했거나 직방이 목록을 주지 않았으면 null ([실패])'
            )
        )
    ]
    price_trend: Annotated[
        ZigbangPriceTrend | None,
        Field(description='평당가 추이 (--range 평형대). 평당가 추이 조회를 받지 못했거나 직방이 줄 목록을 주지 않았으면 null ([실패])')
    ]
    price_movement: Annotated[
        ZigbangPriceMovement | None,
        Field(description='시세 흐름 (평당가 추이 응답). 직방이 주 수와 흐름을 모두 주지 않았거나(웹도 그리지 않는다) 평당가 추이 조회를 받지 못했거나 직방이 평당가 추이를 주지 않았으면 null ([실패])')
    ]
    population: Annotated[
        ZigbangRegionPopulation | None,
        Field(description='인구·세대 (구만. 동은 서버가 빈 목록을 주고 웹도 인구 탭이 없어 키가 없다)')
    ] = None
