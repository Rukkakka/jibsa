"""요청 모델: 전국에서 지금 많이 보는 단지·동 (trending-complexes)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.ranking.common import (
    DabangRankingComplexType,
    DabangRankingUnit,
)

from typing import (
    Annotated,
    Literal,
)


DabangWatchBaseOn = Literal['JUST_BEFORE', 'YESTERDAY', 'LAST_WEEK', 'LAST_MONTH']


class DabangRealTimeWatchRankingsV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-time-watch-rankings/{unit}` 쿼리 (전국에서 지금 많이 보는 단지·동, 늘 50곳).

    Args:
        unit: 'complex' 단지, 'region' 동 (경로).
        complex_type: 아파트·오피스텔.
        base_on: 방금전·어제·지난주·지난달 (웹 고르기 값).
        limit: 웹 값 50 (적게 줘도 50곳을 준다, 2026-10-25 실측).
    """

    unit: Annotated[
        DabangRankingUnit,
        Field(exclude=True, description='단지·동 (경로)')
    ]
    complex_type: Annotated[
        DabangRankingComplexType,
        Field(description='단지 유형', alias='complexType')
    ] = 'APT'
    base_on: Annotated[
        DabangWatchBaseOn,
        Field(description='기간', alias='baseOn')
    ] = 'JUST_BEFORE'
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='순위 수')
    ] = 50
