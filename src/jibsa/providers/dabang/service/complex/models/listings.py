"""`listings.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
)
from jibsa.providers.dabang.service.complex.constants import (
    DEFAULT_COMPLEX_SORT,
)

from typing import (
    Annotated,
)


class DabangComplexListingsResult(Result):
    """단지 하나의 매물.

    `notes`: 평형·제외·일부 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    pyeong_ids: Annotated[
        list[int] | None,
        Field(description='고른 평형 ID. null 이면 전체 평형')
    ] = None
    sort: Annotated[
        str,
        Field(description="매물 순서 (다방 웹 단지 매물 정렬: '랭킹순'·'최신순'·'높은가격순'·'낮은가격순'·'면적넓은순'·'면적좁은순')")
    ] = DEFAULT_COMPLEX_SORT
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 매물이 있는지')
    ] = False
    listings: Annotated[
        list[DabangListing],
        Field(description='sort 순서 그대로의 매물 (다방이 정렬한 순서)')
    ]
