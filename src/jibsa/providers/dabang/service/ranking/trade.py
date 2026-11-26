"""전국에서 기간 안 거래가 많은 단지 (trade-rankings)."""

from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.ranking.trade import (
    DabangRealPriceTradeRankingsComplexV5RequestParameterModel,
    DabangTradeBaseOn,
)
from jibsa.providers.dabang.service.common.functions import (
    COMPLEX_TYPE_BY_LABEL,
    building_years,
    household_count,
)
from jibsa.providers.dabang.service.ranking.models import (
    DabangTradeRanking,
    DabangTradeRankings,
)


TRADE_PERIOD_BY_LABEL: dict[str, DabangTradeBaseOn] = {
    '이번주': 'CURRENT_WEEK',
    '지난주': 'LAST_WEEK',
    '이번달': 'CURRENT_MONTH',
    '지난달': 'LAST_MONTH',
    '올해': 'CURRENT_YEAR',
}
# 막 시작한 기간은 다방이 아직 세지 않아 순위가 빈다 (2026-10-26 월 아침 실측: 이번주 0곳, 지난주·이번달은 있음). 비면 권할 기간
PREVIOUS_TRADE_PERIOD: dict[str, str] = {'이번주': '지난주', '이번달': '지난달', '올해': '지난달'}


def get_trade_rankings(
    client: DabangClient, *, complex_type: str, trade: str, period: str, limit: int,
) -> DabangTradeRankings:
    """전국에서 기간 안 거래가 많은 단지 (요청 1회, 다방은 50곳을 준다)."""
    result = client.run_request_real_price_trade_rankings_complex_v5(DabangRealPriceTradeRankingsComplexV5RequestParameterModel(
        complex_type=COMPLEX_TYPE_BY_LABEL[complex_type],
        real_price_type='SALE' if trade == '매매' else 'LEASE',
        base_on=TRADE_PERIOD_BY_LABEL[period],
    )).result
    rankings = []
    # 웹처럼 50곳을 받아 자른다. limit 을 작게(2) 보내면 다방이 500 을 준다 (2026-10-25 실측: 같은 조건 limit 50 은 200)
    for row in (result.list_ if result else [])[:limit]:
        # '11년차ㆍ3636세대ㆍ서울특별시 송파구 문정동'. 주소 칸을 골라야 해 칸으로 나눠 읽는다
        # 설명이 비면 주소도 모름(null)이다
        parts = [part.strip() for part in (row.description or '').split('ㆍ')]
        address = next((part for part in parts if part and not part.endswith(('년차', '세대'))), None)
        rankings.append(DabangTradeRanking(
            rank=row.rank, complex_id=row.complex_id, name=row.complex_name, trade_count=row.trade_count,
            occupancy_years=building_years(row.description), household_count=household_count(row.description),
            address=normalize_address(address),
        ))
    notes = []
    if not rankings and period in PREVIOUS_TRADE_PERIOD:
        notes.append(note('참고', (
            f'{period} 순위가 비었습니다. 기간이 막 시작돼 다방이 아직 세지 않았을 수 있습니다. '
            f'--period {PREVIOUS_TRADE_PERIOD[period]} 로 보세요'
        )))
    return DabangTradeRankings(
        complex_type=complex_type,
        trade_type=trade,
        period=period,
        base_period=result.format_base_period if result else None,
        returned=len(rankings),
        rankings=rankings,
        notes=notes,
    )
