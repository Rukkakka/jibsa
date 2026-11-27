"""전국에서 지금 많이 보는 단지·동 (trending-complexes)."""

from jibsa.core.korean import full_legal_division_code
from jibsa.core.listing import (
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.ranking.trending import (
    DabangRealTimeWatchRankingsV5RequestParameterModel,
)
from jibsa.providers.dabang.service.common.constants import (
    COMPLEX_TYPE_BY_LABEL,
)
from jibsa.providers.dabang.service.ranking.constants import (
    FLUCTUATION_LABELS,
    WATCH_PERIOD_BY_LABEL,
)
from jibsa.providers.dabang.service.ranking.models import (
    DabangWatchRanking,
    DabangWatchRankings,
)

from typing import (
    Literal,
)


def get_watch_rankings(
    client: DabangClient, *, unit: Literal['단지', '동'], complex_type: str, period: str, limit: int,
) -> DabangWatchRankings:
    """전국에서 지금 많이 보는 단지·동 (요청 1회, 다방은 늘 50곳). 지역으로 좁히지 못한다."""
    result = client.run_request_real_time_watch_rankings_v5(DabangRealTimeWatchRankingsV5RequestParameterModel(
        unit='complex' if unit == '단지' else 'region',
        complex_type=COMPLEX_TYPE_BY_LABEL[complex_type],
        base_on=WATCH_PERIOD_BY_LABEL[period],
    )).result
    rows = (result.list_ if result else [])[:limit]
    return DabangWatchRankings(
        unit=unit,
        complex_type=complex_type,
        period=period,
        base_period=result.format_base_period if result else None,
        returned=len(rows),
        rankings=[
            DabangWatchRanking(
                rank=row.rank,
                unit=unit,
                complex_id=row.complex_id,
                name=row.complex_name or row.dong_name,
                address=normalize_address(row.address) if unit == '단지' else row.state_name,
                legal_division_code=full_legal_division_code(row.dong_code) if row.dong_code else None,
                viewer_count=row.watch_count,
                change=(
                    None if row.fluctuation is None or row.fluctuation.type is None
                    else f'{FLUCTUATION_LABELS.get(row.fluctuation.type, row.fluctuation.type)} {row.fluctuation.rank}'
                    if row.fluctuation.type in ('UP', 'DOWN') and row.fluctuation.rank
                    else FLUCTUATION_LABELS.get(row.fluctuation.type, row.fluctuation.type)
                ),
            )
            for row in rows
        ],
    )
