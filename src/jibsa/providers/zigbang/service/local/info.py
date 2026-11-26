"""동·구의 지역 정보 (region-info): 단지·세대 수, 평형대별 직방시세, 월별 거래량, 평당가 추이, 구의 인구·세대."""

import re
from datetime import datetime

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    KST,
    AmountRange,
    Result,
    lookup_failure_note,
    note,
    null_items_note,
    read_month,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.local.info import (
    ZigbangLocalsPynChartPriceRequestParameterModel,
    ZigbangLocalsRequestParameterModel,
    ZigbangLocalsTotalHouseholdsTimeRequestParameterModel,
    ZigbangLocalsTotalPeopleTimeRequestParameterModel,
    ZigbangLocalsTradingVolumeChartRequestParameterModel,
    ZigbangPynAreaType,
)
from jibsa.providers.zigbang.api.response.local.info import (
    ZigbangLocalPriceModel,
    ZigbangLocalsPynChartPriceDataModel,
)
from jibsa.providers.zigbang.service.common.base import (
    OPTIONAL_LOOKUP_ERRORS,
    UNEXPECTED_FORMAT_TEXT,
    ZigbangEstimatedPrice,
    sale_price_range,
    text_or_none,
)
from jibsa.providers.zigbang.service.local.base import (
    ZigbangLocalModel,
    ZigbangLocalRegion,
    local_region_of,
    resolve_local_area,
)

from typing import (
    Annotated,
    Literal,
)


# 평당 추이 그래프의 평형대 탭 (`--range`). 직방 서버의 pynAreaType 값 그대로다 (2026-11-22 실측: 모두 200)
PRICE_RANGES: tuple[ZigbangPynAreaType, ...] = (
    '전체', '10평이하', '10평대', '20평대', '30평대', '40평대', '50평대', '60평대이상',
)
# 지역 정보 `price` 의 평형대 구분(area) → 웹 평형 이름표 (2026-11-19 번들 지역정보 화면 `e_`). 'total' 먼저, 그다음 작은 평형대부터다
AREA_LABELS: dict[str, str] = {
    'total': '전체',
    '0': '10평 이하',
    '10': '10평대',
    '20': '20평대',
    '30': '30평대',
    '40': '40평대',
    '50': '50평대',
    '60': '60평대 이상',
}
# 지역 정보 머리 문구 ('39 단지 · 23,634 세대'). 웹 머리가 이 글자를 그린다
DESCRIPTION_PATTERN: re.Pattern[str] = re.compile(r'([\d,]+)\s*단지\s*·\s*([\d,]+)\s*세대')
# 웹 인구 그래프가 보내는 기간 길이 (2026-11-19 캡처: startDate=202110&endDate=202610). 번들에서 근거는 찾지 못했다
POPULATION_YEARS: int = 5
PRICE_TREND_EMPTY_ALL: str = '직방 시세가 있는 아파트 단지가 없습니다'
PRICE_TREND_EMPTY_RANGE: str = '선택하신 평형대의 단지가 없습니다'


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


def _description_counts(description: str | None) -> tuple[int | None, int | None]:
    """머리 문구('4,923 단지 · 1,876,379 세대')에서 (단지 수, 세대수). 읽지 못하면 둘 다 None."""
    match = DESCRIPTION_PATTERN.fullmatch((description or '').strip())
    if match is None:
        return None, None
    return int(match.group(1).replace(',', '')), int(match.group(2).replace(',', ''))


def _sale_price_bounds(prices: list[ZigbangLocalPriceModel] | None) -> tuple[int | float | None, int | float | None]:
    """전체 평형('total')의 (최저, 최고) 매매가. 웹이 쓰는 값이고 0 은 웹이 그리지 않아 null 이다."""
    total = next((price for price in prices or [] if price.area == 'total'), None)
    if total is None:
        return None, None
    return total.min_sales_price or None, total.max_sales_price or None


def _estimated_prices(prices: list[ZigbangLocalPriceModel] | None) -> list[ZigbangRegionEstimatedPrice] | None:
    """평형대별 직방시세. 웹 평형 탭처럼 평균 매매·전월세 평당가가 0 인 평형대를 빼고 (값이 없는 칸은 남긴다), 전체 먼저 작은 평형대 순이다. 최저·최고 매매가 0 은 null 이다."""
    if prices is None:
        return None
    order = list(AREA_LABELS)
    kept = [price for price in prices if price.sales_price != 0 and price.rent_price != 0]
    kept.sort(key=lambda price: order.index(price.area) if price.area in order else len(order))
    return [
        ZigbangRegionEstimatedPrice(
            # 표에 없는 구분은 직방 글자 그대로 둔다
            pyeong_range=AREA_LABELS.get(price.area, price.area) if price.area is not None else None,
            estimated_prices={'sale': None if price.sales_price is None else ZigbangEstimatedPrice(price_per_pyeong_manwon=price.sales_price)},
            # 전체 줄의 최저·최고는 결과 머리의 estimated_ranges 와 같은 칸이라 같은 규칙(0 은 웹이 그리지 않아 null)이다
            estimated_ranges={'sale': sale_price_range(price.min_sales_price or None, price.max_sales_price or None)},
        )
        for price in kept
    ]


def _year_month(value: int | None) -> str | None:
    """YYYYMM 정수를 'YYYY-MM' 으로. 읽지 못하면 None."""
    if value is None:
        return None
    year, month = divmod(value, 100)
    if not (1000 <= year <= 9999 and 1 <= month <= 12):
        return None
    return f'{year:04d}-{month:02d}'


def _lookup_failure(what: str, exc: Exception, unknown: str) -> str:
    """덤 조회 실패 안내. 갈래별 문장은 공통 함수 `lookup_failure_note` 가 정한다."""
    return lookup_failure_note(exc, '직방', what, f'{unknown} 값을 모릅니다 (직방 웹 지역 정보 화면에서 확인)')


def _missing_list(what: str, unknown: str) -> str:
    """덤 조회가 예외 없이 끝났는데 직방이 목록을 주지 않았다는 `[실패]` 안내. 정상 응답은 늘 목록을 주므로 응답 형식이 바뀐 것이다."""
    return note(
        '실패',
        f'직방이 {what} 주지 않았습니다. {UNEXPECTED_FORMAT_TEXT}. {unknown} 값을 모릅니다 (직방 웹 지역 정보 화면에서 확인)',
    )


def _price_trend(
    data: ZigbangLocalsPynChartPriceDataModel,
    price_range: ZigbangPynAreaType,
    region_name: str | None,
) -> tuple[ZigbangPriceTrend | None, list[str]]:
    """평당가 추이와 안내. 줄이 1개 이하이면 웹 문구를, 빈 항목을 뺐으면 `[제외]` 를 안내한다.

    줄 종류는 위치가 아니라 직방 지역 정보의 이름(`region_name`)과 같은 줄이 지역이다 (빈 항목을 빼면 위치가 밀린다).
    줄 수는 뺀 빈 항목까지 센다.
    """
    if data.lines is None:
        return None, []
    notes: list[str] = []
    dropped = data.null_items('lines')
    if dropped:
        notes.append(null_items_note('직방 지역 평당가 추이 줄', dropped))
    if len(data.lines) + dropped <= 1:
        if price_range == '전체':
            notes.append(note('참고', f"평당가 추이 줄이 1개 이하입니다. 직방 웹은 이때 그래프 대신 '{PRICE_TREND_EMPTY_ALL}' 라고 알립니다"))
        else:
            notes.append(note(
                '참고',
                f"{price_range} 평당가 추이 줄이 1개 이하입니다. 직방 웹은 이때 그래프 대신 '{PRICE_TREND_EMPTY_RANGE}' 라고 알립니다. "
                '다른 평형대는 --range 로 고르세요',
            ))
    lines: list[ZigbangPriceTrendLine] = []
    for line in data.lines:
        # 이름과 종류는 앞뒤 공백을 뗀 같은 값으로 판정한다 (빈 글자는 이름 없음이라 종류도 모름)
        label = text_or_none(line.label)
        lines.append(ZigbangPriceTrendLine(
            name=label,
            kind=None if label is None or region_name is None else ('지역' if label == region_name else '단지'),
            months=None if line.data is None else [
                # 직방시세 0 은 값 없음이다 (단지 추이·평형대별 시세와 같다). 점은 남기고 값만 모름이다
                ZigbangPriceTrendPoint(month=read_month(point.date, '시세 추이 월'), price_per_pyeong_manwon=None if point.price == 0 else point.price)
                for point in line.data
            ],
        ))
    return ZigbangPriceTrend(pyeong_range=price_range, lines=lines), notes


def get_region_info(
    client: ZigbangClient,
    query: str,
    *,
    price_range: ZigbangPynAreaType = '전체',
) -> ZigbangRegionInfoResult:
    """동·구의 지역 정보를 직방 웹 지역정보 화면과 같은 값으로 모은다 (동 요청 4회, 구 요청 6회: 지역 검색 1회 + 지역 정보 1회 + 덤 거래량·평당가 추이(구는 인구·세대도)).

    지역 정보(`locals`)가 본 조회이고 404 면 직방에 그 지역 정보가 없다고 알린다 (NOT_FOUND). 나머지는 덤 조회라 본 조회 뒤에 부르고, 하나가 실패하면(요청 제한
    포함) 그 값만 null 로 두고 `[실패]` 로 알린다 (인구와 세대는 따로). 평형대(`price_range`)는 평당가 추이 그래프만 정하고 평형대별 시세
    (`by_pyeong_range`)는 늘 모든 평형대다. 덤 조회가 예외 없이 끝났어도 직방이 목록을 주지 않으면 `[실패]` + 업데이트 문구로 알린다.

    Raises:
        JibsaError: 시·도 이름일 때 (INVALID_ARGUMENT), 직방이 그 지역 정보를 주지 않을 때 (NOT_FOUND, 404).
        RegionNotFoundError: 동·구를 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 동·구가 여럿이거나 구가 있는 시·'○가' 로만 나뉜 동일 때.
    """
    area = resolve_local_area(client, query)
    try:
        local = client.run_request_locals(ZigbangLocalsRequestParameterModel(local_code=area.code))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise JibsaError(
                code='NOT_FOUND',
                message=f"직방에 '{area.region.name}' 지역 정보가 없습니다",
                hint='이웃 동·구 이름(동이면 그 동이 속한 구)으로 jibsa zigbang region-info 를 다시 부르세요',
            ) from None
        raise
    notes = list(area.notes)
    region = local_region_of(area, local.name)

    monthly_volumes: list[ZigbangRegionMonthlyVolume] | None = None
    try:
        volume = client.run_request_locals_trading_volume_chart(
            ZigbangLocalsTradingVolumeChartRequestParameterModel(local_code=area.code)
        )
    except OPTIONAL_LOOKUP_ERRORS as exc:
        notes.append(_lookup_failure('지역 거래량', exc, 'monthly_volumes'))
    else:
        months = volume.data.months if volume.data is not None else None
        if months is None:
            notes.append(_missing_list('지역 거래량 목록을', 'monthly_volumes'))
        monthly_volumes = None if months is None else [
            ZigbangRegionMonthlyVolume(
                month=read_month(month.date, '거래량 월'),
                trade_counts={'sale': month.sales_volume, 'jeonse': month.charter_volume, 'wolse': month.rent_volume},
            )
            for month in months
        ]

    price_trend: ZigbangPriceTrend | None = None
    price_movement: ZigbangPriceMovement | None = None
    try:
        trend = client.run_request_locals_pyn_chart_price(
            ZigbangLocalsPynChartPriceRequestParameterModel(local_code=area.code, pyn_area_type=price_range)
        )
    except OPTIONAL_LOOKUP_ERRORS as exc:
        notes.append(_lookup_failure('지역 평당가 추이', exc, 'price_trend·price_movement'))
    else:
        if trend.data is None:
            notes.append(_missing_list('지역 평당가 추이를', 'price_trend·price_movement'))
        else:
            if trend.data.lines is None:
                notes.append(_missing_list('지역 평당가 추이 줄 목록을', 'price_trend'))
            price_trend, trend_notes = _price_trend(trend.data, price_range, text_or_none(local.name))
            notes.extend(trend_notes)
            # 주 수와 흐름이 모두 있어야 낸다. 웹은 둘 중 하나라도 없거나 주 수가 0 이면 그리지 않는다 (번들 `components_PriceTrendText` 의 `!t||!n`)
            movement = trend.data.market_price_movement_info
            price_movement = (
                None
                if movement is None or not movement.updown_week_count or not movement.updown_sign
                else ZigbangPriceMovement(streak_weeks=movement.updown_week_count, direction=movement.updown_sign)
            )

    population: ZigbangRegionPopulation | None = None
    if area.level == '구':
        # 웹 인구 그래프와 같은 요청 기간 YYYYMM. 끝은 지난달(한국 시간)이고 시작은 그 5년 전 같은 달이다 (`POPULATION_YEARS`)
        today = datetime.now(KST).date()
        last_month = today.year * 12 + today.month - 2
        start_month = last_month - POPULATION_YEARS * 12
        start_date = f'{start_month // 12}{start_month % 12 + 1:02d}'
        end_date = f'{last_month // 12}{last_month % 12 + 1:02d}'
        people: list[ZigbangPopulationMonth] | None = None
        households: list[ZigbangHouseholdMonth] | None = None
        try:
            people_response = client.run_request_locals_total_people_time(
                ZigbangLocalsTotalPeopleTimeRequestParameterModel(local_code=area.code, start_date=start_date, end_date=end_date)
            )
        except OPTIONAL_LOOKUP_ERRORS as exc:
            notes.append(_lookup_failure('지역 인구', exc, 'population.people'))
        else:
            people = [
                ZigbangPopulationMonth(
                    month=_year_month(item.yearmonth),
                    population=item.age_all,
                    age_0_9=item.age_0_9,
                    age_10_19=item.age_10_19,
                    age_20_29=item.age_20_29,
                    age_30_39=item.age_30_39,
                    age_40_49=item.age_40_49,
                    age_50_59=item.age_50_59,
                    age_60_over=item.age_60_69,
                )
                for item in people_response.root
            ]
        try:
            households_response = client.run_request_locals_total_households_time(
                ZigbangLocalsTotalHouseholdsTimeRequestParameterModel(local_code=area.code, start_date=start_date, end_date=end_date)
            )
        except OPTIONAL_LOOKUP_ERRORS as exc:
            notes.append(_lookup_failure('지역 세대', exc, 'population.household_months'))
        else:
            households = [
                ZigbangHouseholdMonth(
                    month=_year_month(item.yearmonth),
                    household_count=item.people_all,
                    one=item.people_1,
                    two=item.people_2,
                    three=item.people_3,
                    four=item.people_4,
                    five_plus=item.people_5_,
                )
                for item in households_response.root
            ]
        population = ZigbangRegionPopulation(people=people, household_months=households)

    complexes, households_count = _description_counts(local.description)
    sale_min, sale_max = _sale_price_bounds(local.price)
    return ZigbangRegionInfoResult(
        region=region,
        complex_count=complexes,
        household_count=households_count,
        estimated_ranges={'sale': sale_price_range(sale_min, sale_max)},
        by_pyeong_range=_estimated_prices(local.price),
        monthly_volumes=monthly_volumes,
        price_trend=price_trend,
        price_movement=price_movement,
        population=population,
        notes=notes,
        not_applicable=frozenset() if area.level == '구' else frozenset({'population'}),
    )
