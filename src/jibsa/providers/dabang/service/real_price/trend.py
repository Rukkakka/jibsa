"""평형 하나의 시세 흐름 (price-trend)."""


from jibsa.core.dates import read_month
from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    AmountRange,
    AmountSet,
)
from jibsa.core.notes import null_items_note
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.real_price.trend import (
    DabangRealPriceComplexChartsV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.real_price.trend import (
    DabangChartSeriesModel,
    DabangHighLowModel,
)
from jibsa.providers.dabang.service.real_price.common import (
    fetch_complex_space,
    primary_space,
)
from jibsa.providers.dabang.service.real_price.models.trend import (
    DabangPriceTrend,
    DabangTradeAverage,
    DabangTrendMonth,
)

from typing import (
    Literal,
)


def _average(value: float | None) -> float | None:
    """달 평균. 다방은 거래 없는 달에 앞 달 평균을 잇는데, 이을 앞 달 평균도 없으면(그때까지 거래가 없던 평형) 0 을 준다.
    0만원 평균은 없으니 모름(None)으로 둔다 (2026-10-26 실측: 거래가 한 번도 없는 6979662367f35b14fef7600dcb63 평형
    311325 는 36달 모두 0 인데 같은 응답에서 읽은 최근 평균 trade_averages 의 sale price_manwon 은 null).
    """
    return value or None


def _range(value: DabangHighLowModel | None, trade: Literal['매매', '전세']) -> AmountRange | None:
    """기간 하나의 최저·최고. 두 끝을 모두 모르면 None. 금액 칸은 매매 price_manwon, 전세 deposit_manwon 이다."""
    if value is None or (value.highest is None and value.lowest is None):
        return None
    if trade == '매매':
        return AmountRange(lowest=AmountSet(price_manwon=value.lowest), highest=AmountSet(price_manwon=value.highest))
    return AmountRange(lowest=AmountSet(deposit_manwon=value.lowest), highest=AmountSet(deposit_manwon=value.highest))


def _trade_periods(one_year: AmountRange | None, three_years: AmountRange | None) -> dict[str, AmountRange | None] | None:
    """한 거래의 기간별 범위. 두 기간 모두 모르면 그 거래가 None."""
    if one_year is None and three_years is None:
        return None
    return {'one_year': one_year, 'three_years': three_years}


def get_price_trend(client: DabangClient, complex_id: str, *, space_seq: int | None) -> DabangPriceTrend:
    """평형 하나의 36달 시세 흐름 (요청 1회, 평형을 안 주면 대표 평형을 찾느라 +1).

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, space_notes = primary_space(client, complex_id, verb='찾았습니다')
        notes += space_notes
    result = fetch_complex_space(
        lambda: client.run_request_real_price_complex_charts_v5(
            DabangRealPriceComplexChartsV5RequestParameterModel(complex_id=complex_id, space_seq=space_seq)
        ).result,
        complex_id,
        space_seq,
    )
    if result is None:
        raise JibsaError(code='NOT_FOUND', message=f'다방 시세 흐름이 없습니다: {complex_id}', hint='단지 ID·평형 번호를 확인하세요')
    sale = result.sale or DabangChartSeriesModel()
    lease = result.lease_monthly or DabangChartSeriesModel()
    lease_by_month = {row.date: row for row in lease.statistics}
    gap_rows = (result.gap.statistics or []) if result.gap else []
    gap_by_month = {row.date: row for row in gap_rows if row.date is not None}
    # 달 목록은 매매 쪽으로 만든다. 매매·전월세는 늘 같은 36달이고, 매매가 한 건도 없는 평형도 sale 이 null 이 아니라
    # 거래 0건인 36달로 온다 (2026-10-25 실측: 은마·오피스텔 2곳 8개 평형, 매매 0건인 메이플자이 299902)
    months = [
        DabangTrendMonth(
            month=read_month(row.date, '시세 흐름 달'),
            trade_averages={
                'sale': None if (sale_average := _average(row.average_price)) is None else AmountSet(price_manwon=sale_average),
                'jeonse': None if (lease_average := (
                    _average(lease_by_month[row.date].average_price) if row.date in lease_by_month else None
                )) is None else AmountSet(deposit_manwon=lease_average),
            },
            trade_counts={
                'sale': row.volume,
                'jeonse': lease_by_month[row.date].lease_volume if row.date in lease_by_month else None,
                'wolse': lease_by_month[row.date].monthly_volume if row.date in lease_by_month else None,
            },
            # 웹 갭 그래프는 전세가율이 0 이면 '-' 로 쓴다 (`leaseRate||'-'`). 0% 전세가율은 없으니 모름(None)으로 둔다
            jeonse_ratio_percent=gap_by_month[row.date].lease_rate or None if row.date in gap_by_month else None,
            # 리뷰 오탐 (2026-11-13, 근거 고침 2026-11-20): 평균이 없는 달에 갭이 큰 숫자로 나온다는 지적. 웹 갭 그래프 툴팁
            # (ic_24_cook_gray600 청크)은 그 달 gap.statistics 의 rangeAveragePrice 를 그대로 그리고(price-unit 청크 `S` 는 숫자가
            # 아니면 '-'), 한쪽 평균만 없는 달에도 서버가 갭을 null 로 준다 (2026-11-20 은마 817: 202601 매매 null·전세 70212 →
            # 갭 null, 202611 매매 307750·전세 null → 갭 null). 서버 값을 그대로 내도 모름이 숫자로 나오지 않는다
            gap_manwon=gap_by_month[row.date].range_average_price if row.date in gap_by_month else None,
        )
        for row in sale.statistics
    ]
    # 달 목록을 매매 쪽으로 만들어서 거기서 빈 항목을 뺐으면 그 달이 목록에서 빠졌다
    if dropped := sale.null_items('statistics'):
        notes.append(null_items_note('다방 시세 흐름 매매 월별', dropped))
    gap = result.gap.recent_info if result.gap else None
    year = result.year_price
    per_space = sale.per_space
    lease_per_space = lease.per_space
    return DabangPriceTrend(
        complex_id=complex_id,
        pyeong_id=space_seq,
        trade_averages={
            'sale': None if per_space is None or (
                per_space.average_price is None and per_space.average_pyeong_price is None
            ) else DabangTradeAverage(
                price_manwon=per_space.average_price,
                price_per_pyeong_manwon=per_space.average_pyeong_price,
            ),
            'jeonse': None if lease_per_space is None or lease_per_space.average_price is None else DabangTradeAverage(
                deposit_manwon=lease_per_space.average_price,
            ),
        },
        jeonse_ratio_percent=gap.lease_rate if gap else None,
        gap_manwon=gap.range_average_price if gap else None,
        trade_ranges=None if year is None else {
            'sale': _trade_periods(
                _range(year.sale.one_year if year.sale else None, '매매'),
                _range(year.sale.three_years if year.sale else None, '매매'),
            ),
            'jeonse': _trade_periods(
                _range(year.lease.one_year if year.lease else None, '전세'),
                _range(year.lease.three_years if year.lease else None, '전세'),
            ),
        },
        months=months,
        notes=notes,
    )
