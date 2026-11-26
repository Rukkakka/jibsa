"""응답 모델: 단지 기능(complex)의 상세·검색·인기 단지가 같이 쓰는 것."""

from pydantic import (
    Field,
)

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import (
    Annotated,
)


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchComplexes
# ---------------------------------------------------------------------------

class DaangnBuildingModel(DaangnBaseResponseModel):
    """단지의 건물 (동) 하나."""

    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddress')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소. 비어 오기도 한다', alias='jibunAddress')
    ] = None



class DaangnBuildingEdgeModel(DaangnBaseResponseModel):
    """건물 연결의 edge."""

    node: Annotated[
        DaangnBuildingModel | None,
        Field(description='건물')
    ] = None



class DaangnBuildingConnectionModel(DaangnBaseResponseModel):
    """건물 연결."""

    edges: Annotated[
        list[DaangnBuildingEdgeModel],
        Field(description='건물')
    ] = []



class DaangnSearchComplexNodeModel(DaangnBaseResponseModel):
    """이름으로 찾은 단지."""

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
        Field(description='APARTMENT, OFFICETEL, MIXED_USE ...')
    ] = None
    buildings: Annotated[
        DaangnBuildingConnectionModel | None,
        Field(description='건물 (웹 쿼리가 3개까지 받는다)')
    ] = None



class DaangnSearchComplexEdgeModel(DaangnBaseResponseModel):
    """단지 검색 연결의 edge."""

    node: Annotated[
        DaangnSearchComplexNodeModel | None,
        Field(description='단지')
    ] = None



class DaangnSearchComplexesModel(DaangnBaseResponseModel):
    """`searchComplexes` 연결. 이름이 비슷한 순이며 전국 단지가 섞인다."""

    edges: Annotated[
        list[DaangnSearchComplexEdgeModel],
        Field(description='단지')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None



class DaangnSearchComplexesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_complexes: Annotated[
        DaangnSearchComplexesModel | None,
        Field(description='단지 검색 결과', alias='searchComplexes')
    ] = None



class DaangnSearchComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchComplexes` 응답."""

    data: Annotated[
        DaangnSearchComplexesDataModel | None,
        Field(description='결과')
    ] = None
