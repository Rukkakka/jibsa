"""직방 service 지역 화면의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.zigbang.api.request.local.info import ZigbangPynAreaType
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice

from typing import (
    Annotated,
    Any,
    Literal,
)


LocalLevel = Literal['동', '구']
LocalTrade = Literal['매매', '전세', '월세']

# 줄의 동(`dong`) 필드 설명. 실거래·랭킹 줄이 같이 쓴다
LOCAL_DONG_DESCRIPTION: str = (
    "줄이 속한 동 (직방이 준 local, 예: '가락동'). 구 단위 조회에만 있고 동 단위 조회는 서버가 빈 글자를 줘 키가 없다. "
    '구 단위인데 직방이 주지 않으면 null'
)


class ZigbangLocalRegion(BaseModel):
    """지역 화면 명령 결과의 머리: 조회한 동·구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동·구 이름. region-info 는 직방 지역 정보의 이름 (예: 성남시 분당구), 그 밖은 찾은 지역 이름. 리는 상위 읍·면으로 찾아 notes 로 알린다')
    ]
    level: Annotated[
        LocalLevel,
        Field(description="조회 단위. 시·군·구는 '구', 읍·면·동은 '동' (리는 상위 읍·면이라 '동')")
    ]
    address: Annotated[
        str | None,
        Field(description='찾은 지역의 전체 주소')
    ]
    legal_division_code: Annotated[
        str,
        Field(description='법정동코드 (10자리). 직방이 지역 화면에 쓰는 5자리(구)·8자리(동) 코드 뒤를 0 으로 채운 값이다. 리는 상위 읍·면 코드다')
    ]


class ZigbangLocalModel(BaseModel):
    """결과·줄의 기반. 해당 없는 칸은 출력에서 키를 뺀다 (`not_applicable`).

    같은 모델이 거래 유형·정렬·조회 단위마다 다른 칸을 내므로, 만들 때 뺄 칸 이름을 정해 넘긴다. 값을 모르는 칸은 키를 두고 null 이다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    not_applicable: Annotated[
        frozenset[str],
        Field(exclude=True, description='이 결과·줄에 해당하지 않아 출력에서 키를 뺄 칸 이름. 출력하지 않는다')
    ] = frozenset()

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.not_applicable:
            data.pop(field, None)
        return data


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


LocalRankingPeriod = Literal['이번주', '지난주', '이번달', '지난달', '올해', '작년']


class ZigbangDanjiRank(ZigbangLocalModel):
    """단지 랭킹 한 줄. 정렬마다 오는 칸이 달라 해당하지 않는 칸은 키가 없다. 금액은 만원이다."""

    rank: Annotated[
        int | None,
        Field(description='순위 (직방 rankingNumber). 같은 값이면 같은 순위로 오고 다음 순위가 건너뛴다 (예: 1·1·1·4). 직방이 주지 않으면 null')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 건수 (건, 거래량 많은순만)')
    ]
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 하락률·상승률 정렬에는 키가 없다). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    household_count: Annotated[
        int | None,
        Field(description='총세대수 (하락률·상승률 정렬에는 키가 없다)')
    ]
    latest_trade_date: Annotated[
        str | None,
        Field(description='가장 최근 계약일 (YYYY-MM-DD, 하락률·상승률 정렬만). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래가 (만원, 매매의 하락률·상승률 정렬만)')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래의 보증금 (만원, 전세의 하락률·상승률 정렬만)')
    ]
    prev_trade_diff_manwon: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 차액 (만원, 하락률·상승률 정렬만)')
    ]
    prev_trade_diff_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, 하락률·상승률 정렬만)')
    ]
    area_type: Annotated[
        str | None,
        Field(description='가장 최근 거래의 평형 이름 (하락률·상승률 정렬만)')
    ]
    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 (만원, 시세 높은순만). 웹 설명: 단지 중 가장 시세가 높은 타입을 기준으로 한 값이라 공급 면적별 차이가 있다')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 기준 평당가 (만원/3.3㎡, 평당가 높은순만)')
    ]
    view_count: Annotated[
        int | None,
        Field(description='기간 안 조회수 (인기 단지순만)')
    ]
    jeonse_ratio_percent: Annotated[
        int | float | None,
        Field(description='직방 매매 시세 대비 전세 시세 비율 (%, 전세가율 높은순만)')
    ]
    gap_manwon: Annotated[
        int | float | None,
        Field(description='매매 시세와 전세 시세의 차이 (만원, 전세가율 높은순만)')
    ]


class ZigbangRegionRankingResult(ZigbangLocalModel, Result):
    """동·구의 단지 랭킹 (직방 웹 지역 화면 '단지랭킹', 웹처럼 100위까지).

    `notes`: 일부만 받았다는 안내·100위까지만 본다는 안내·쪽을 받지 못했다는 안내. CLI 가 결과 위에 붙인다
    """

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 거래량 많은순)')
    ]
    period: Annotated[
        LocalRankingPeriod,
        Field(description='기간. 시세 높은순·평당가 높은순·전세가율 높은순은 기간과 상관없이 시세 기준일의 순위다')
    ]
    start_date: Annotated[
        str | None,
        Field(description='집계 시작일 (YYYY-MM-DD, 한국 날짜. 서버는 UTC 로 주지만 한국 날짜로 바꾼다). 거래량·하락률·상승률·인기 정렬만 있고 시세·평당가·전세가율에는 키가 없다. 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    end_date: Annotated[
        str | None,
        Field(description='집계 끝 날짜 (YYYY-MM-DD, 한국 날짜). 거래량·하락률·상승률은 집계 기간의 끝, 시세·평당가·전세가율은 직방 시세 기준일, 인기는 조회 집계의 끝이다. 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    updated_at: Annotated[
        str | None,
        Field(description='갱신 시각 (YYYY-MM-DD HH:MM, 한국 시간). 거래량·하락률·상승률 정렬만 있고 시세·평당가·전세가율·인기는 서버가 주지 않아 키가 없다. 읽지 못하면 null')
    ]
    total: Annotated[
        int | None,
        Field(description='직방이 준 순위 수 (count). 서버가 200 에서 막아 실제 단지가 더 많을 수 있고 웹은 100위까지만 보여 준다. 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='웹이 보여 주는 100위 안에 --limit 을 늘리면 더 받을 수 있는 단지가 남았는지 (직방이 목록을 순위 수보다 일찍 끝내면 false. 이어 받기는 없다)')
    ]
    rankings: Annotated[
        list[ZigbangDanjiRank],
        Field(description='단지 랭킹 (직방 순위 순서 그대로)')
    ]


LocalTradePeriod = Literal['오늘', '어제', '7일', '15일', '30일']


class ZigbangRegionTrade(ZigbangLocalModel):
    """지역 최근 실거래 한 줄. 거래 유형에 해당하지 않는 칸은 키가 없다 (매매 가격·비교는 매매만, 보증금은 전세·월세, 월세료는 월세만).

    웹은 정렬마다 비교 한 가지(직전 거래·직방시세·공시가격·분양가·전세가)만 그리지만, 여기서는 같은 응답의 비교 칸을 모두 낸다. 금액은 만원이다.
    """

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    area_type: Annotated[
        str | None,
        Field(description="평형 이름 (웹 '{평형 이름}㎡', 예: 110D). 직방이 주지 않으면 null")
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내). 목록은 계약일 순이 아니라 등록일 기준이다')
    ]
    presale: Annotated[
        str | None,
        Field(description='분양권·입주권 거래 (해당할 때만 키가 있다. real-price 의 presale 과 같다)')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='매매가 (만원). 매매만 있고 전세·월세는 키가 없다')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='보증금·전세금 (만원). 전세·월세만 있고 매매는 키가 없다')
    ]
    rent_manwon: Annotated[
        int | float | None,
        Field(description='월세 (만원). 월세만 있고 매매·전세는 키가 없다')
    ]
    prev_trade_diff_manwon: Annotated[
        int | float | None,
        Field(
            description=(
                "직전 거래 대비 차액 (만원, 매매·전세). 직방이 칸을 주지 않으면 null (웹 '직전거래 없음'), 0 은 웹 '차이 없음'. "
                '입주권 줄은 웹이 그리지 않아 키가 없고, 입주 전 계약 전세 줄도 웹이 그리지 않아 null. 월세는 키가 없다'
            )
        )
    ]
    prev_trade_diff_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, prev_trade_diff_manwon 과 같은 규칙)')
    ]
    estimated_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="직방시세 대비 차액 (만원, 매매만). 분양권·입주권이거나 직방시세가 없으면(isNoMarketPriceGap) 웹이 '직방시세 없음' 이라 null. 직방시세가 있는데 0 이면 진짜 0")
    ]
    estimated_price_diff_percent: Annotated[
        int | float | None,
        Field(description='직방시세 대비 변동률 (%, estimated_price_diff_manwon 과 같은 규칙)')
    ]
    public_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="공시가격 대비 차액 (만원, 매매만). 공시가격이 없으면(isNoPublicPriceGap) 웹이 '공시가격 업데이트 예정' 이라 null. 공시가격이 있는데 0 이면 진짜 0")
    ]
    public_price_diff_percent: Annotated[
        int | float | None,
        Field(description='공시가격 대비 변동률 (%, public_price_diff_manwon 과 같은 규칙)')
    ]
    presale_price_diff_manwon: Annotated[
        int | float | None,
        Field(description='분양가 대비 차액 (만원, 분양권·입주권 매매 줄에만 키가 있다). 직방이 분양가 대비 값을 주지 않으면(isNoOfferPriceGap) null')
    ]
    presale_price_diff_percent: Annotated[
        int | float | None,
        Field(description='분양가 대비 변동률 (%, presale_price_diff_manwon 과 같은 규칙)')
    ]
    jeonse_comparison_diff_manwon: Annotated[
        int | float | None,
        Field(description="전세가 비교 차액 (만원, 전세만). 웹 '전세가 비교': 갱신 거래(renewal)는 이전 전세가 대비, 아니면 2년 전 평균 전세가 대비. 입주 전 계약 거래(pre_move_in_contract)는 웹이 차액을 그리지 않아 null")
    ]
    jeonse_comparison_diff_percent: Annotated[
        int | float | None,
        Field(description='전세가 비교 변동률 (%, jeonse_comparison_diff_manwon 과 같은 규칙)')
    ]
    pre_move_in_contract: Annotated[
        bool | None,
        Field(description="입주 전 계약 거래 (웹 '입주 전 계약 거래', 전세만). 직방이 칸을 주지 않으면 false")
    ]
    new_high: Annotated[
        bool | None,
        Field(description='신고가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    new_low: Annotated[
        bool | None,
        Field(description='신저가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    renewal: Annotated[
        bool | None,
        Field(description="갱신 계약 (웹 '계약갱신' 배지, 전세만. 매매에는 웹이 그리지 않아 키가 없고, 월세는 직방이 값을 줘도 웹이 그리지 않아 키가 없다). 직방이 칸을 주지 않으면 false")
    ]


class ZigbangRegionTradesResult(ZigbangLocalModel, Result):
    """동·구의 최근 실거래 (직방 웹 지역 화면 '실거래', 등록일 기준). 기간이 오늘이 아니면 `updated_today` 키가 없다.

    `notes`: 일부만 받았다는 안내·실거래가 없다는 안내·아직 반영 전이라는 안내·빈 항목을 빼고 읽었다는 안내. CLI 가 결과 위에 붙인다
    """

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    period: Annotated[
        LocalTradePeriod,
        Field(description='등록 기간. 오늘·어제·7일(최근 일주일)·15일·30일')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 최신 등록순)')
    ]
    registered_period: Annotated[
        str | None,
        Field(
            description=(
                "직방이 준 기간과 등록 건수 문구 (예: '10. 23 ~ 11. 22 등록 135건'). 직방이 주지 않으면 null. "
                '기간이 오늘이고 직방이 아직 반영 전(updated_today false)이면 웹처럼 숨겨 null'
            )
        )
    ]
    updated_today: Annotated[
        bool | None,
        Field(
            description=(
                "직방이 오늘 등록된 실거래를 반영했는지 (직방은 매일 낮 12시에 반영한다. false 면 직방 웹은 '오늘 12시에 실거래가 업데이트 될 예정입니다' 를 보여 준다). "
                '--period 오늘 일 때만 있고 다른 기간은 키가 없다. 직방이 주지 않으면 null'
            )
        )
    ]
    total: Annotated[
        int | None,
        Field(description='기간 안 등록된 실거래 전체 건수 (limit 적용 전). 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 실거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='--limit 을 늘리면 더 받을 수 있는 실거래가 남았는지 (직방이 --limit 보다 적게 줘 더 받을 수 없으면 false. 이어 받기는 없다)')
    ]
    trades: Annotated[
        list[ZigbangRegionTrade],
        Field(description='최근 실거래 (정렬 순서 그대로)')
    ]
