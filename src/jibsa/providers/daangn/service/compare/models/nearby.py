"""`nearby.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnRegion,
)

from typing import (
    Annotated,
)


class DaangnNearbyComplex(BaseModel):
    """같은 동 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (sale·jeonse·wolse)')
    ]


class DaangnNearbyComplexesResult(Result):
    """같은 동 단지 목록.

    `notes`: 조회 한도 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='기준 단지 ID')]
    region: Annotated[DaangnRegion, Field(description='기준 단지가 있는 동')]
    total: Annotated[
        int | None,
        Field(description='기준 단지를 뺀 같은 동 단지 수 (limit 적용 전). 1200곳에서 잘리면 notes 로 알린다. 당근이 빈 항목을 줘 셀 수 없으면 null')
    ]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    sort: Annotated[str, Field(description="정렬. 늘 '세대수' (많은 순. jibsa 정렬이며 웹 검색 엔진용 본문은 단지 ID 순 10곳이다)")]
    complexes: Annotated[list[DaangnNearbyComplex], Field(description='세대수 많은 순 단지')]
