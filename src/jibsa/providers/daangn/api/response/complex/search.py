"""응답 모델: 단지 이름 검색·지역·지도 범위 단지 목록 (search complexes)."""

from pydantic import (
    Field,
)

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionComplexNodeModel,
)

from typing import (
    Annotated,
)


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByClusterId (동·구 단지 목록)
# ---------------------------------------------------------------------------

class DaangnRegionComplexEdgeModel(DaangnBaseResponseModel):
    """지역 단지 목록의 edge."""

    node: Annotated[
        DaangnRegionComplexNodeModel | None,
        Field(description='단지')
    ] = None



class DaangnRegionComplexesModel(DaangnBaseResponseModel):
    """지역 단지 목록 연결. 요청한 정렬 순이다."""

    edges: Annotated[
        list[DaangnRegionComplexEdgeModel],
        Field(description='단지')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None



class DaangnComplexByClusterIdDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_cluster_id: Annotated[
        DaangnRegionComplexesModel | None,
        Field(description='단지 목록', alias='complexByClusterId')
    ] = None



class DaangnComplexByClusterIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexByClusterId` 응답 (동·구 단지 목록)."""

    data: Annotated[
        DaangnComplexByClusterIdDataModel | None,
        Field(description='결과')
    ] = None



# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchComplexes (지도 범위 단지 목록, 카드는 동·구 단지 목록과 같다)
# ---------------------------------------------------------------------------

class DaangnSearchComplexesViewportDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_complexes: Annotated[
        DaangnRegionComplexesModel | None,
        Field(description='화면 범위 안 단지 목록', alias='searchComplexes')
    ] = None



class DaangnSearchComplexesViewportResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchComplexes` 응답 (지도 범위 단지 목록, 웹 `ComplexListPanelViewportQuery`)."""

    data: Annotated[
        DaangnSearchComplexesViewportDataModel | None,
        Field(description='결과')
    ] = None
