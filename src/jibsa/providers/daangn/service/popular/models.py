"""구 안 인기 매물 순위의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Listing,
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnRegion,
)

from typing import Annotated


class DaangnRankedListing(Listing):
    """조회수 순위 매물."""

    rank: Annotated[
        int | None,
        Field(description='조회수 순위 (거래 불가로 뺀 매물 자리는 비운다). 당근이 빈 항목을 줘 셀 수 없으면 null')
    ]


class DaangnPopularListingsResult(Result):
    """조회수 많은 매물 목록.

    `notes`: 순위 범위·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnRegion, Field(description='기준 동 (순위는 그 구 전체)')]
    returned: Annotated[int, Field(description='반환한 매물 수')]
    listings: Annotated[list[DaangnRankedListing], Field(description='조회수 순위 순 매물')]
