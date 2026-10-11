"""응답 모델: 동네 후기 요약 (region-reviews)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import (
    Annotated,
    Any,
)


# ---------------------------------------------------------------------------
# 동네 후기 — GET /map/{name1}/{name2}/reviews (RELAY_STORE), regionByOriginalRegionId,
# livedReviewsByRegion. 후기 본문·요약 글은 읽지 않는다 (개수만 쓰고 원 사이트로 안내한다).
# ---------------------------------------------------------------------------

class DaangnReviewComplexModel(ResponseModel):
    """구에서 거주 후기가 많은 단지."""

    original_id: Annotated[
        str,
        Field(description='숫자 단지 ID')
    ] = Field(alias='originalId')
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL ...')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='거주 후기 수')
    ] = Field(default=None, alias='livedReviewCount')


class DaangnMapReviewsResponseModel(ResponseModel):
    """구의 동네 후기 페이지에서 추출한 것 (후기 많은 순 단지 20곳)."""

    complexes: Annotated[
        list[DaangnReviewComplexModel],
        Field(description='후기 많은 단지')
    ] = []


class DaangnLivedReviewSummaryModel(ResponseModel):
    """동네 후기 요약. `overall`·`highlights` 같은 요약 글도 오지만 읽지 않는다."""

    source_review_count: Annotated[
        int | None,
        Field(description='요약에 쓰인 후기 수')
    ] = Field(default=None, alias='sourceReviewCount')


class DaangnRegionReviewSummaryModel(ResponseModel):
    """`regionByOriginalRegionId` 결과."""

    lived_review_summary: Annotated[
        DaangnLivedReviewSummaryModel | None,
        Field(description='동네 후기 요약. 구이거나 후기가 적으면 null')
    ] = Field(default=None, alias='livedReviewSummary')


class DaangnRegionByOriginalRegionIdDataModel(ResponseModel):
    """GraphQL `data`."""

    region_by_original_region_id: Annotated[
        DaangnRegionReviewSummaryModel | None,
        Field(description='지역')
    ] = Field(default=None, alias='regionByOriginalRegionId')


class DaangnRegionByOriginalRegionIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `regionByOriginalRegionId` (동네 후기 요약) 응답."""

    data: Annotated[
        DaangnRegionByOriginalRegionIdDataModel | None,
        Field(description='결과')
    ] = None


class DaangnLivedReviewsConnectionModel(ResponseModel):
    """동네 후기 연결. 본문은 읽지 않고 있는지만 본다."""

    edges: Annotated[
        list[dict[str, Any]],
        Field(description='후기 (읽지 않는다)')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnLivedReviewsByRegionDataModel(ResponseModel):
    """GraphQL `data`."""

    lived_reviews_by_region: Annotated[
        DaangnLivedReviewsConnectionModel | None,
        Field(description='동네 후기')
    ] = Field(default=None, alias='livedReviewsByRegion')


class DaangnLivedReviewsByRegionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `livedReviewsByRegion` 응답."""

    data: Annotated[
        DaangnLivedReviewsByRegionDataModel | None,
        Field(description='결과')
    ] = None
