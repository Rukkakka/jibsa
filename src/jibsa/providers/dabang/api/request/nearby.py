from pydantic import (
    Field,
    field_serializer,
    model_serializer,
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


DabangNearTarget = Literal['room', 'complex']


class DabangTransitNearV5RequestParameterModel(RequestModel):
    """`GET /api/v5/transit/near/{target}` 쿼리 (매물·단지 둘레 지하철역 1km·버스 노선 500m).

    쿼리 키가 대상에 따라 `roomId`·`complexId` 로 바뀐다 (웹 `{[`${e}Id`]: t}`).

    Args:
        target: 'room' 또는 'complex' (경로).
        target_id: 매물 ID 또는 단지 ID.
    """

    target: Annotated[
        DabangNearTarget,
        Field(description='대상 (경로)')
    ]
    target_id: Annotated[
        str,
        Field(pattern=r'^[0-9a-f]{24}$|^[0-9a-f]{28}$', description='매물 ID(24자리) 또는 단지 ID(28자리)')
    ]

    @model_serializer(mode='plain')
    def as_query(self) -> dict[str, str]:
        return {f'{self.target}Id': self.target_id}


class DabangNearV5RequestParameterModel(RequestModel):
    """`GET /api/v5/{target}/{target_id}/near` 의 경로 값 (가까운 편의·안전·교육 시설).

    Args:
        target: 'room' 또는 'complex'.
        target_id: 매물 ID 또는 단지 ID.
    """

    target: Annotated[
        DabangNearTarget,
        Field(exclude=True, description='대상 (경로)')
    ]
    target_id: Annotated[
        str,
        Field(exclude=True, pattern=r'^[0-9a-f]{24}$|^[0-9a-f]{28}$', description='매물 ID 또는 단지 ID (경로)')
    ]


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
