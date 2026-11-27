"""요청 모델: 동네 후기 (region-reviews)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnMapReviewsRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/map/{name1}/{name2}/reviews` (구의 동네 후기 페이지)와 `.../{name3}/reviews` (동의 동네 후기 페이지) 경로.

    구가 없는 시(세종)는 시·도 아래 동이 바로 있어 동 이름을 `name2` 자리에 넣고 `name3` 은 비운다
    (`/map/세종특별자치시/반곡동/reviews`, 구 후기 페이지 모양).
    """

    name1: Annotated[
        str,
        Field(min_length=1, exclude=True, description='시/도 (예: 서울특별시)')
    ]
    name2: Annotated[
        str,
        Field(min_length=1, exclude=True, description='시/군/구 (예: 강남구, 용인시 처인구). 구가 없는 시(세종)는 동 이름 (예: 반곡동)')
    ]
    region_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='이 페이지가 가리키는 당근 지역 ID (구 또는 동). 페이지 스토어에는 다른 지역의 목록도 섞여 있어 이 ID 의 것만 읽는다')
    ]
    name3: Annotated[
        str | None,
        Field(min_length=1, exclude=True, description='읍/면/동 (예: 역삼동). 주면 그 동의 후기 페이지, 없으면 구의 후기 페이지')
    ] = None


class DaangnLivedReviewsByRegionRequestPayloadModel(RequestModel):
    """GraphQL `livedReviewsByRegion` 쿼리 변수 (웹의 `RegionLivedReviewListPanelQuery`, 동네 후기 목록)."""

    region_id: Annotated[
        int,
        Field(gt=0, description='당근 지역 ID (동 또는 구)', alias='regionId')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='받을 후기 수. jibsa 는 후기가 있는지만 보므로 1')
    ] = 1
    after: Annotated[
        str | None,
        Field(description='다음 페이지 커서')
    ] = None
