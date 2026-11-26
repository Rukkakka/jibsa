"""시세 추이 (price-trend)."""

from datetime import (
    date,
    datetime,
)

from jibsa.core.errors import (
    JibsaError,
)
from jibsa.core.listing import (
    KST,
    UPDATE_MAYBE_NEEDED,
    js_to_fixed,
    note,
    null_items_note,
    read_date,
    won_to_manwon,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import DaangnExclusiveUseAreaModel
from jibsa.providers.daangn.api.request.real_price.trend import (
    DaangnComplexPriceChartRequestPayloadModel,
    DaangnPriceChartTradeType,
)
from jibsa.providers.daangn.api.response.real_price.trend import (
    DaangnPriceChartModel,
)
from jibsa.providers.daangn.service.common.functions import (
    compare_column,
    complex_url,
    is_year_month,
    pyeong_null_items,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.real_price.base import (
    choose_pyeong,
)
from jibsa.providers.daangn.service.real_price.models import (
    DaangnChartEstimatedPrices,
    DaangnKbSale,
    DaangnPricePoint,
    DaangnPriceTrendResult,
    DaangnPriceTrendSummary,
)

from typing import (
    Literal,
    cast,
)


# 단지 시세 추이의 거래 유형 (라벨 → 당근 값). 차트는 매매·전세만 있다. 변화율은 웹처럼 기간의 첫 거래 달과 마지막 거래 달을
# 견주고(`get_price_trend`), 그 달의 거래가 적으면 `PRICE_TREND_FEW_TRANSACTIONS` 로 알린다
PRICE_CHART_TRADE_BY_TRADE_TYPE: dict[str, DaangnPriceChartTradeType] = {'매매': 'BUY', '전세': 'BORROW'}



# 시세 추이 기간: 당근 웹 시세 그래프의 탭 (1년·3년·전체, PriceChart `X`). 전체는 쿼리가 받는 15년(180개월)이다
PRICE_TREND_PERIODS: dict[str, int] = {'1년': 12, '3년': 36, '전체': 180}



# 웹 그래프 머리의 '최근 3개월 평균': 이번 달과 그 전 3개월 (4개 달)
PRICE_TREND_RECENT_MONTHS: int = 3



# 마지막 거래가 이만큼 지났으면 오래된 시세라고 알린다
PRICE_TREND_STALE_MONTHS: int = 6



# 비교하는 달의 거래가 이보다 적으면 변화율이 튈 수 있다고 알린다
PRICE_TREND_FEW_TRANSACTIONS: int = 3



def estimated_prices_of(chart: DaangnPriceChartModel | None) -> DaangnChartEstimatedPrices | None:
    """시세 그래프 응답의 `latestKbSale`(원)을 만원으로. 없으면 None (모름).

    웹은 KB 시세를 매매 그래프의 띠로만 그리지만 응답에는 전세 그래프에도 함께 와서 거래 유형과 상관없이 낸다. KB 월세·전세 시세는
    이 응답에 없다 (단지 비교 `compare` 의 `pyeong.estimated_prices` 에 있다).
    """
    kb = chart.latest_kb_sale if chart else None
    if kb is None:
        return None
    low = won_to_manwon(kb.lower)
    high = won_to_manwon(kb.upper)
    return DaangnChartEstimatedPrices(
        base_date=read_date(kb.survey_base_date, 'KB 시세 기준일'),
        sale=None if low is None and high is None else DaangnKbSale(low_manwon=low, high_manwon=high),
    )



def _month_label(index: int) -> str:
    return f'{index // 12:04d}-{index % 12 + 1:02d}'



def get_price_trend(
    client: DaangnClient,
    complex_id: int,
    *,
    trade_type: str = '매매',
    pyeong: int | None = None,
    area_group: int | None = None,
    period: str = '1년',
    today: date | None = None,
) -> DaangnPriceTrendResult:
    """단지의 월별 평균 실거래가와 변화율을 당근 웹 단지 화면의 시세 그래프처럼 받는다 (요청 2회: 단지 비교 칸 → 시세 그래프).

    웹처럼 평형 하나로 본다. `pyeong`(아파트형의 공급 평형)·`area_group`(전용면적 묶음)이 없으면 웹이 처음 보여 주는 대표
    평형이다. 크기가 다른 평형을 섞은 평균은 큰 평형 거래가 몰린 달에 튀어 추이가 틀어져서, 예전의 '모든 평형 평균' 기본을
    바꿨다 (#215, 2026-11-12 사용자 결정). 고를 평형이 없는 단지(평형 묶음이 없거나 대표 묶음에 평형 값이 없다)는 웹처럼 그래프를
    받지 않고 빈 `months` 를 준다 (요청 1회). 기간은 웹 탭(1년·3년·전체)이고, 오늘(한국 날짜)이 든 달과 그 전 N개월의 거래 달을
    `months` 로 준다. 변화율은 웹(PriceChart `Z`)처럼 기간 안 첫 거래 달과 마지막 거래 달 평균을 견준다. 예전에는 마지막 거래 달
    까지 3개월과 N년 전 3개월을 가중 평균해 웹과 숫자가 달랐다 (2026-11-12 실측: 헬리오시티 32평 1년, 웹 -0.6%). 변화율의 반올림은
    계산 자리 주석에 있다. 당근이 시세 그래프를 주지 않으면(`priceChart` null) 거래 달이 없는 것이 아니라
    모름이라 `months`·`total_trade_count` 를 null 로 내고 알린다. 거래가 있는데 연월이나 평균 가격이 없는 점은 빼고 알리며, 어느 달의
    얼마인지 몰라 `total_trade_count`·`summary`·`recent_*` 도 빈 항목을 뺐을 때처럼 null 이다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND, 고를 수 없는 평형이면 INVALID_ARGUMENT, 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 시세 그래프 쿼리를 바꿨을 때.
    """
    column = compare_column(client, complex_id)
    choice = choose_pyeong(column, pyeong=pyeong, area_group=area_group, representative=True)
    # 평형을 정하지 않아 대표 평형을 골랐을 때 그 후보 목록에서 빈 항목을 빼고 읽었으면 고른 평형이 웹의 대표 평형이 아닐 수 있다
    dropped_pyeongs = pyeong_null_items(column) if pyeong is None and area_group is None else 0
    pyeong_notes = [null_items_note('당근 대표 평형 후보', dropped_pyeongs)] if dropped_pyeongs else []
    if choice is None:
        # 웹 단지 화면 가격 칸(ComplexTopicPanel)은 고른 평형(`k`)이 없으면 그래프를 그리지 않고 '아직 등록된 실거래가가 없어요'
        # 만 보여 준다 (`xe=…&&k!=null`). 예전에는 평형 거르기 없이 그래프를 받아 모든 평형을 섞은 평균을 냈다 (2026-11-12 번들 대조)
        return DaangnPriceTrendResult(
            complex_id=str(complex_id),
            trade_type=trade_type,
            period=cast(Literal['1년', '3년', '전체'], period),
            total_trade_count=0,
            months=[],
            url=complex_url(complex_id),
            notes=[note(
                '참고',
                "당근에 이 단지 평형 묶음 정보가 없어 당근 웹도 시세 그래프 없이 '아직 등록된 실거래가가 없어요' 로 보여 줍니다",
            )] + pyeong_notes,
        )
    if column.id is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message='당근 단지 비교 칸에 노드 ID 가 없어 시세 그래프를 받지 못했습니다',
            hint=f'응답 형식이 바뀌었을 수 있습니다. {UPDATE_MAYBE_NEEDED}',
        )
    group = choice.area_group if not choice.ptp_cds else None
    response = client.run_request_complex_price_chart(
        DaangnComplexPriceChartRequestPayloadModel(
            id=column.id,
            chart_trade_type=PRICE_CHART_TRADE_BY_TRADE_TYPE[trade_type],
            ptp_cds=choice.ptp_cds or None,
            exclusive_use_area_group=group,
            exclusive_use_area=DaangnExclusiveUseAreaModel(min=group, max=group + 1) if group is not None else None,
        )
    )
    node = unwrap_graphql(response, response.data.node if response.data else None, '시세 그래프', conditions=False)
    # 그래프를 주지 않았으면(null) 거래가 있는 달이 0개인 것이 아니라 모름이다. 그래프가 왔는데 거래 달이 없으면 months 는 []
    # 점 목록(averagePoints)이 null 인 것도 그래프를 주지 않은 것과 같은 모름이다 ([] 는 거래 달 0개)
    chart = node.price_chart
    no_graph = chart is None or chart.average_points is None
    chart_points = (chart.average_points if chart else None) or []
    # 달 목록에서 빈 항목을 빼고 읽은 수. 어느 달이 빠졌는지 몰라 달 목록으로 계산한 값은 모른다 (null)
    dropped = chart.null_items('average_points') if chart else 0

    monthly: dict[int, tuple[float, int]] = {}
    unreadable = 0
    for point in chart_points:
        # 거래 수가 없거나 0 인 점은 거래가 없는 달이라 말없이 넘긴다
        if not point.transaction_count:
            continue
        average = won_to_manwon(point.average_amount)
        year_month = point.year_month
        # 거래가 있는데 평균 가격이 없거나 0 이거나(0 은 실제 거래가가 아니라 빈 값이다. 넣으면 변화율이 0 으로 나뉜다), 연월이
        # 없거나 꼴이 틀린 점(null·''·'-' 등)은 어느 달의 얼마인지 몰라 뺀다 (int 로 읽다 명령 전체가 실패하지 않게). 뺀 점이 기간
        # 안 첫 달·마지막 달·최근 3개월이었을 수 있어 달 목록으로 계산한 값(total_trade_count·summary·recent_*)은 모른다 (null).
        # 당근 웹 시세 그래프도 달을 모르는 점은 그리지 못할 것이다 (jibsa 가 웹으로 확인하지는 않았다)
        if not average or year_month is None or not is_year_month(year_month):
            unreadable += 1
            continue
        # 'YYYYMM' 을 달 번호로 바꾼다 (달끼리 빼면 개월 수)
        monthly[int(year_month[:4]) * 12 + int(year_month[4:6]) - 1] = (average, point.transaction_count)

    # 실거래 달은 한국 날짜라 컴퓨터 시간대와 상관없이 한국 시간으로 센다 (UTC 컴퓨터는 매달 1일 0~9시에 지난달이 된다)
    today = today or datetime.now(KST).date()
    this_month = today.year * 12 + today.month - 1
    # 웹은 new Date(올해, 이번 달 - N, 1) 부터라 이번 달까지 N+1 개 달이다 (1년이면 작년 같은 달부터)
    shown = sorted(index for index in monthly if index >= this_month - PRICE_TREND_PERIODS[period])
    points = [
        DaangnPricePoint(month=_month_label(index), average_manwon=monthly[index][0], trade_count=monthly[index][1])
        for index in shown
    ]
    # 최근 N개월 거래 수로 가중 평균한 평균가와 거래 수. 거래가 없으면 None
    recent_points = [value for index, value in monthly.items() if index >= this_month - PRICE_TREND_RECENT_MONTHS]
    recent_count = sum(transactions for _, transactions in recent_points)
    recent: tuple[float, int] | None = (
        round(sum(average * transactions for average, transactions in recent_points) / recent_count, 4), recent_count,
    ) if recent_count else None
    if recent is None:
        last = max((index for index in monthly if index >= this_month - 12), default=None)
        recent = monthly[last] if last is not None else None

    notes: list[str] = []
    chosen = f'{choice.pyeong}평' if choice.pyeong is not None else f'{choice.area_group}㎡'
    if pyeong is None and area_group is None:
        option = '--pyeong (complex 의 pyeongs[].pyeong)' if choice.pyeong is not None else '--area (complex 의 pyeongs[].area_group)'
        # 단지 전체를 물었는데 웹 기본값으로 평형 하나만 본 것이라 [범위] 다 (search listings --university 의 기본 종류와 같다)
        notes.append(note('범위', f'평형을 정하지 않아 당근 웹처럼 대표 평형({chosen})으로 봅니다. 다른 평형은 {option} 으로 주세요'))
    summary = None
    if no_graph:
        notes.append(note('실패', f'당근이 이 평형의 시세 그래프 자료를 주지 않았습니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'))
    elif dropped:
        notes.append(null_items_note(
            '당근 시세 그래프 월별 평균', dropped, ('total_trade_count', 'summary', 'recent_average_manwon', 'recent_trade_count'),
        ))
    elif unreadable:
        # 연월이나 평균 가격을 모르는 점을 뺐으면 summary 는 모름(null)이다. 아래 [제외] 안내가 알리므로 여기서는 더하지 않는다
        pass
    elif len(shown) < 2:
        # '전체' 탭은 15년(PRICE_TREND_PERIODS)이라 '최근 전체 동안' 이 되지 않게 기간을 풀어 쓴다
        span = f'전체 기간(최근 {PRICE_TREND_PERIODS[period] // 12}년)' if period == '전체' else f'최근 {period}'
        notes.append(note(
            '참고',
            f'{span} 동안 {chosen} {trade_type} 거래가 있는 달이 {len(shown)}개라 변화율을 내지 못했습니다 '
            '(당근 웹도 이 기간 탭을 막습니다)',
        ))
    else:
        first, last_index = shown[0], shown[-1]
        start, end = monthly[first], monthly[last_index]
        # 변화율은 웹 식이다 (usePriceChartFragment `b`, 2026-11-19 번들: `r = 끝 - 시작; i = r / 시작 * 100; Math.abs(i).toFixed(1)` 에 상승·하락
        # 부호). Python `round`(은행가 반올림)가 아니라 공용 `js_to_fixed`(JS `toFixed` 와 같은 반올림)로 맞춘다 (1.25 → 1.3).
        # 웹은 차이가 500만원 미만이거나 0.0 이면 변화율을 보여 주지 않지만 jibsa 는 값을 계속 낸다
        change = (end[0] - start[0]) / start[0] * 100
        rounded = js_to_fixed(abs(change), 1)
        # 0.0 으로 반올림되면 부호를 붙이지 않는다 (-0.0 이 되지 않게)
        change_percent = float(-rounded) if change < 0 and rounded else float(rounded)
        summary = DaangnPriceTrendSummary(
            start_month=_month_label(first),
            start_average_manwon=start[0],
            end_month=_month_label(last_index),
            end_average_manwon=end[0],
            span_months=last_index - first,
            change_percent=change_percent,
            change_manwon=round(end[0] - start[0], 4),
        )
        if min(start[1], end[1]) < PRICE_TREND_FEW_TRANSACTIONS:
            notes.append(note(
                '참고',
                f'비교한 달의 거래가 적어({_month_label(first)} {start[1]}건, {_month_label(last_index)} {end[1]}건) 변화율이 실제 '
                '시세 변화와 크게 다를 수 있습니다. months 의 흐름을 함께 보세요',
            ))
    if shown and not dropped and not unreadable and this_month - shown[-1] >= PRICE_TREND_STALE_MONTHS:
        notes.append(f'마지막 거래가 {_month_label(shown[-1])} 에 있어 최근 시세와 다를 수 있습니다')
    if shown:
        notes.append('월별 평균은 그 달 실거래 평균이라 거래가 적은 달(trade_count)은 튈 수 있습니다')
    if unreadable:
        if dropped:
            # 빈 항목 안내(null_items_note)가 네 칸이 null 이라고 이미 알렸다
            notes.append(note('제외', f'당근이 연월이나 평균 가격을 주지 않은 시세 점 {unreadable}개는 뺐습니다'))
        else:
            notes.append(note(
                '제외',
                f'당근이 연월이나 평균 가격을 주지 않은 시세 점 {unreadable}개는 뺐습니다. 어느 달의 얼마인지 몰라 '
                'total_trade_count, summary, recent_average_manwon, recent_trade_count 값은 알 수 없어 null 입니다',
            ))
    return DaangnPriceTrendResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        pyeong=choice.pyeong,
        area_group=choice.area_group,
        period=cast(Literal['1년', '3년', '전체'], period),
        recent_average_manwon=recent[0] if recent and not dropped and not unreadable else None,
        recent_trade_count=recent[1] if recent and not dropped and not unreadable else None,
        estimated_prices=estimated_prices_of(chart),
        total_trade_count=sum(monthly[index][1] for index in shown) if not no_graph and not dropped and not unreadable else None,
        summary=summary,
        months=points if not no_graph else None,
        url=complex_url(complex_id),
        notes=notes + pyeong_notes,
    )
