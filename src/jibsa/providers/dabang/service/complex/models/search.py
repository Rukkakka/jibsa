"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountSet,
    Result,
)
from jibsa.providers.dabang.service.common.models import (
    DabangPlace,
)

from typing import (
    Annotated,
)


class DabangComplexSummary(BaseModel):
    """단지 목록의 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID. dabang complex·search listings --complex·real-price 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description='입주 N년차 (사용승인한 해를 1년차로 센다. 연식 age_years 보다 1 크다)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 매물 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (다방이 주지 않은 수는 null)")
    ]
    latest_trades: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 가장 최근 실거래가 (평형과 상관없이 단지의 가장 최근 거래. 다방 목록 카드와 같다). 키는 'sale'(price_manwon)·"
            "'jeonse'(deposit_manwon) 늘 두 개이고 거래가 없거나 받지 못하면 null (complex 의 latest_trades 와 같다)"
        ))
    ]


class DabangComplexListResult(Result):
    """단지 목록.

    `notes`: 범위·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치')
    ]
    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description='다방이 센 범위 안 단지 수 (반경·아파트 동 검색은 사각형 안의 수)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    complexes: Annotated[
        list[DabangComplexSummary],
        Field(description='다방 목록 순 단지')
    ]
