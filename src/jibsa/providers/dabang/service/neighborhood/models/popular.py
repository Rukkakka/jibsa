"""`popular.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializeAsAny,
)

from jibsa.core.listing import (
    Listing,
    Result,
)
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
    DabangPlace,
)

from typing import (
    Annotated,
)


class DabangRankedListing(DabangListing):
    """동 안 인기 매물 (순위가 붙은 다방 매물)."""

    rank: Annotated[
        int | None,
        Field(description='다방 선호도(조회수·찜수·문의수를 합친 점수) 순위. 1이 가장 높다. 다방이 빈 항목을 줘 그 쪽의 순위를 셀 수 없으면 null')
    ]


class DabangPopularResult(Result):
    """동 안 인기 매물.

    `notes`: 제외·일부 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    total: Annotated[
        int | None,
        Field(description='순위가 있는 매물 수 (고른 유형·거래 유형 안)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='순위가 더 있는지')
    ] = False
    listings: Annotated[
        list[SerializeAsAny[Listing]],
        Field(description='선호도 높은 순 매물')
    ]
