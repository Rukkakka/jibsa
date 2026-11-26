"""요청 모델: 역 둘레 평균 매물가 (station-prices)."""
from pydantic import (
    Field,
    field_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    DabangBboxModel,
    DabangCategory,
    DabangListFilters,
)

from typing import (
    Annotated,
    Literal,
)


class DabangMarkersCategoryV5RequestParameterModel(RequestModel):
    """`GET /api/v5/markers/category/{category}` 쿼리 (지도 집계: 동·칸·역 표시와 역 주변 평균 매물가).

    Args:
        category: 매물 유형 (경로).
        filters: 그 유형의 필터 (JSON 으로 보낸다).
        bbox: 지도 범위 (JSON 으로 보낸다).
        zoom: 지도 확대 수준. 16 이면 역 표시가 온다.
        use_map: 웹 값 'naver'.
    """

    category: Annotated[
        DabangCategory,
        Field(exclude=True, description='매물 유형 (경로)')
    ]
    filters: Annotated[
        DabangListFilters,
        Field(description='유형 필터 (JSON)')
    ]
    bbox: Annotated[
        DabangBboxModel,
        Field(description='지도 범위 (JSON)')
    ]
    zoom: Annotated[
        int,
        Field(ge=1, le=21, description='지도 확대 수준')
    ] = 16
    use_map: Annotated[
        Literal['naver'],
        Field(description='지도 종류', alias='useMap')
    ] = 'naver'

    @field_serializer('filters', 'bbox')
    def as_json(self, value: DabangListFilters | DabangBboxModel) -> str:
        return value.model_dump_json(by_alias=True)
