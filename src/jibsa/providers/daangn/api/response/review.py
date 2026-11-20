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
# 동네 후기 — GET /map/{name1}/{name2}[/{name3}]/reviews (SSR Relay 스토어), regionByOriginalRegionId,
# livedReviewsByRegion. 후기 본문·요약 글은 읽지 않는다 (개수만 쓰고 원 사이트로 안내한다).
# ---------------------------------------------------------------------------

class DaangnReviewComplexModel(ResponseModel):
    """구·동 후기 페이지의 단지 (후기 많은 순)."""

    original_id: Annotated[
        str | None,
        Field(description='숫자 단지 ID. 당근이 주지 않으면 null', alias='originalId')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름. 당근이 주지 않으면 null')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT, OFFICETEL ... (스토어에 우연히 실린 것만 있어 일부 단지에는 없다)')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 동 후기 페이지는 후기 없는 단지도 null·0 으로 준다', alias='livedReviewCount')
    ] = None


class DaangnReviewDongModel(ResponseModel):
    """구 후기 페이지의 동별 후기 수 (`livedReviewDongPagesByRegion`)."""

    region_id: Annotated[
        int,
        Field(description='동의 당근 지역 ID', alias='regionId')
    ]
    name: Annotated[
        str | None,
        Field(description='동 이름 (스토어의 `Region` 레코드 name3). 레코드를 못 찾으면 null')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='그 동의 거주 후기 수', alias='livedReviewCount')
    ] = None


class DaangnReviewBuildingModel(ResponseModel):
    """구·동 후기 페이지의 건물별 후기 수 (`livedReviewBuildingPagesByRegion` 의 `building`)."""

    original_id: Annotated[
        str,
        Field(description='숫자 건물 ID (건물 후기 페이지 `/lived-reviews/buildings/{ID}` 에 쓴다)', alias='originalId')
    ]
    building_name: Annotated[
        str | None,
        Field(description='건물 이름. 없는 건물이 많다', alias='buildingName')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddress')
    ] = None
    lived_review_count: Annotated[
        int | None,
        Field(description='그 건물의 거주 후기 수', alias='livedReviewCount')
    ] = None


class DaangnMapReviewsResponseModel(ResponseModel):
    """구·동의 동네 후기 페이지에서 추출한 것."""

    complexes: Annotated[
        list[DaangnReviewComplexModel],
        Field(description='단지 (후기 많은 순, 구 페이지 20곳·동 페이지 500곳까지, 후기 없는 단지도 뒤에 온다)')
    ] = []
    dongs: Annotated[
        list[DaangnReviewDongModel] | None,
        Field(description='동별 후기 수 (후기 많은 순). 스토어에 키가 없으면 None (동 후기 페이지). 구가 없는 시의 동 페이지처럼 빈 배열이 오면 []')
    ] = None
    buildings: Annotated[
        list[DaangnReviewBuildingModel] | None,
        Field(description='건물별 후기 수 (후기 많은 순). 스토어에 키가 없으면 None')
    ] = None


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
