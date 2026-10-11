"""요청 모델: 동네 후기 요약 (region-reviews)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnMapReviewsRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/map/{name1}/{name2}/reviews` 경로 (구의 동네 후기 페이지). 구가 없는 시(세종)는 페이지가 없다."""

    name1: Annotated[
        str,
        Field(min_length=1, exclude=True, description='시/도 (예: 서울특별시)')
    ]
    name2: Annotated[
        str,
        Field(min_length=1, exclude=True, description='시/군/구 (예: 강남구, 용인시 처인구)')
    ]


class DaangnRegionByOriginalRegionIdRequestPayloadModel(RequestModel):
    """GraphQL `regionByOriginalRegionId` 쿼리 변수 (웹의 `MapDongNeighborhoodSummaryQuery`, 동네 후기 요약)."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID. 요약은 동에만 있다')
    ] = Field(alias='regionId')


class DaangnLivedReviewsByRegionRequestPayloadModel(RequestModel):
    """GraphQL `livedReviewsByRegion` 쿼리 변수 (웹의 `RegionLivedReviewListPanelQuery`, 동네 후기 목록)."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동 또는 구)')
    ] = Field(alias='regionId')
    first: Annotated[
        int,
        Field(ge=1, le=50, description='받을 후기 수. jibsa 는 후기가 있는지만 보므로 1')
    ] = 1
    after: Annotated[
        str | None,
        Field(description='다음 페이지 커서')
    ] = None
