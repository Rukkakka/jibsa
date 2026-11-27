"""`listings.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Listing,
    Result,
)

from typing import (
    Annotated,
)


class DaangnComplexListingsResult(Result):
    """단지 하나의 매물 목록.

    `notes`: 일부만 보여 준다·더 받지 못하고 멈췄다는 안내, 거래를 몰라 뺀 매물·빈 항목을 뺐다는 안내, 원룸·투룸으로 올린 단지 매물 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지')
    ]
    listings: Annotated[
        list[Listing],
        Field(description='단지 매물 (당근 단지 화면 순)')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
