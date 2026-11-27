"""응답 모델: 전국에서 지금 많이 보는 단지·동 (trending-complexes)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangFluctuationModel(DabangBaseResponseModel):
    """앞 기간 대비 순위 변동 (type: UP·DOWN·STEADY·NEW)."""

    type: Annotated[
        str | None,
        Field(description='변동 종류')
    ] = None
    rank: Annotated[
        int | None,
        Field(description='변동 폭')
    ] = None


class DabangWatchRankingItemModel(DabangBaseResponseModel):
    """조회 순위 한 칸. 단지면 `complexId`·`complexName`·`address`, 동이면 `dongCode`·`dongName`·`stateName` 이다."""

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    watch_count: Annotated[
        int | None,
        Field(description="기간 안 조회한 사람 수 (웹은 'N명' 으로 보여 준다)", alias='watchCount')
    ] = None
    fluctuation: Annotated[
        DabangFluctuationModel | None,
        Field(description='순위 변동')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID', alias='complexId')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='complexName')
    ] = None
    address: Annotated[
        str | None,
        Field(description='단지 동까지의 주소')
    ] = None
    dong_code: Annotated[
        str | None,
        Field(description='동 코드 (법정동코드 앞 8자리)', alias='dongCode')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description="동 이름 ('의정부시 의정부동')", alias='dongName')
    ] = None
    state_name: Annotated[
        str | None,
        Field(description='시·도', alias='stateName')
    ] = None


class DabangWatchRankingsResultModel(DabangBaseResponseModel):
    """조회 순위 `result`."""

    format_base_period: Annotated[
        str | None,
        Field(description="기준 기간 ('26.10.12 ~ 26.10.18', '26.10.25 17:09 기준')", alias='formatBasePeriod')
    ] = None
    list_: Annotated[
        list[DabangWatchRankingItemModel],
        Field(description='순위', alias='list')
    ] = []


class DabangRealTimeWatchRankingsV5ResponseModel(DabangV5ResponseModel[DabangWatchRankingsResultModel]):
    """`GET /api/v5/real-time-watch-rankings/{unit}` 응답."""
