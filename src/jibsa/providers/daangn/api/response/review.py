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
# 동네 후기 — GET /map/{name1}/{name2}/reviews (SSR Relay 스토어), regionByOriginalRegionId,
# livedReviewsByRegion. 후기 본문·요약 글은 읽지 않는다 (개수만 쓰고 원 사이트로 안내한다).
# ---------------------------------------------------------------------------

class DaangnReviewComplexModel(ResponseModel):
    """구에서 거주 후기가 많은 단지."""

    original_id: Annotated[
        str,
        Field(description='숫자 단지 ID', alias='originalId')
    ]
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
        Field(description='거주 후기 수', alias='livedReviewCount')
    ] = None


class DaangnMapReviewsResponseModel(ResponseModel):
    """구의 동네 후기 페이지에서 추출한 것 (후기 많은 순 단지 20곳)."""

    complexes: Annotated[
        list[DaangnReviewComplexModel],
        Field(description='후기 많은 단지')
    ] = []


class DaangnLivedReviewsConnectionModel(ResponseModel):
    """동네 후기 연결. 본문은 읽지 않고 있는지만 본다."""

    edges: Annotated[
        list[dict[str, Any]],
        Field(description='후기 (읽지 않는다)')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnReviewRegionModel(ResponseModel):
    """후기 목록 쿼리에 함께 오는 지역 (`reviewRegion: regionByOriginalRegionId`)."""

    lived_review_count: Annotated[
        int | None,
        Field(description='지역의 동네 후기 수 (웹 모바일 후기 화면의 "후기 N개 더 보기")', alias='livedReviewCount')
    ] = None


class DaangnLivedReviewsByRegionDataModel(ResponseModel):
    """GraphQL `data`."""

    lived_reviews_by_region: Annotated[
        DaangnLivedReviewsConnectionModel | None,
        Field(description='동네 후기', alias='livedReviewsByRegion')
    ] = None
    review_region: Annotated[
        DaangnReviewRegionModel | None,
        Field(description='후기 수를 담은 지역', alias='reviewRegion')
    ] = None


class DaangnLivedReviewsByRegionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `livedReviewsByRegion` 응답."""

    data: Annotated[
        DaangnLivedReviewsByRegionDataModel | None,
        Field(description='결과')
    ] = None
