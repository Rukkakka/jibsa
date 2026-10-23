"""요청 모델: 생활 방식에 맞는 동네 추천 (good-neighborhoods)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnLivableRegionScopesRequestPayloadModel(RequestModel):
    """GraphQL `livableRegionScopes` 쿼리 변수 (웹의 `GoodNeighborhoodRegionQuery`, 좋은 동네 추천 지역 목록)."""

    base_year: Annotated[
        str,
        Field(min_length=4, max_length=4, description='통계 기준 연도 (웹은 2025)', alias='baseYear')
    ]


class DaangnNeighborhoodIndicatorModel(RequestModel):
    """좋은 동네 추천 지표 하나 (예: C004 1인 가구 많은)."""

    id: Annotated[
        str,
        Field(min_length=1, description='지표 코드')
    ]
    weight: Annotated[
        int,
        Field(ge=1, description='가중치. 웹은 늘 3')
    ] = 3
    prefer_high: Annotated[
        bool,
        Field(description='True 면 값이 클수록 좋다 (집값 저렴한 은 False)', alias='preferHigh')
    ]


class DaangnRecommendNeighborhoodsInputModel(RequestModel):
    """`recommendNeighborhoods` 의 `input`."""

    indicators: Annotated[
        list[DaangnNeighborhoodIndicatorModel],
        Field(min_length=1, description='지표 (웹은 라이프스타일마다 3개)')
    ]
    base_year: Annotated[
        str,
        Field(min_length=4, max_length=4, description='통계 기준 연도', alias='baseYear')
    ]
    region_cd_prefixes: Annotated[
        list[str],
        Field(description='시·도 또는 시·군·구 코드 (livableRegionScopes). 빈 목록이면 전국', alias='regionCdPrefixes')
    ] = []
    limit: Annotated[
        int,
        Field(ge=1, description='받을 동 수 (웹은 5, 서버는 요청한 만큼 준다)')
    ] = 5


class DaangnRecommendNeighborhoodsRequestPayloadModel(RequestModel):
    """GraphQL `recommendNeighborhoods` 쿼리 변수 (웹의 `GoodNeighborhoodResultQuery`, 좋은 동네 추천)."""

    input: Annotated[
        DaangnRecommendNeighborhoodsInputModel,
        Field(description='지표·지역·개수')
    ]
