"""응답 모델: 생활 방식에 맞는 동네 추천 (good-neighborhoods)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import DaangnGraphQLResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 좋은 동네 추천, 인기 단지·매물
# ---------------------------------------------------------------------------

class DaangnLivableSigunguModel(ResponseModel):
    """추천 지역 시·군·구."""

    code: Annotated[str, Field(description='SGIS 시·군·구 코드 (예: 11230)')]
    name: Annotated[str, Field(description='이름 (예: 강남구)')]


class DaangnLivableSidoModel(ResponseModel):
    """추천 지역 시·도."""

    code: Annotated[str, Field(description='SGIS 시·도 코드 (예: 11)')]
    name: Annotated[str, Field(description='이름 (예: 서울특별시)')]
    sigungus: Annotated[
        list[DaangnLivableSigunguModel],
        Field(description='시·군·구')
    ] = []


class DaangnLivableRegionScopesDataModel(ResponseModel):
    """GraphQL `data`."""

    livable_region_scopes: Annotated[
        list[DaangnLivableSidoModel],
        Field(description='시·도 (17곳)')
    ] = Field(default=[], alias='livableRegionScopes')


class DaangnLivableRegionScopesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `livableRegionScopes` 응답."""

    data: Annotated[
        DaangnLivableRegionScopesDataModel | None,
        Field(description='결과')
    ] = None


class DaangnRecommendedNeighborhoodModel(ResponseModel):
    """추천 동 하나. 동은 행정동이다 (예: 역삼1동)."""

    sgg_nm: Annotated[
        str | None,
        Field(description='시·군·구')
    ] = Field(default=None, alias='sggNm')
    emd_nm: Annotated[
        str | None,
        Field(description='행정동')
    ] = Field(default=None, alias='emdNm')
    region_id: Annotated[
        str | None,
        Field(description='당근 동 ID (법정동)')
    ] = Field(default=None, alias='regionId')
    rank: Annotated[
        int | None,
        Field(description='순위')
    ] = None
    one_line_description: Annotated[
        str | None,
        Field(description='한 줄 설명')
    ] = Field(default=None, alias='oneLineDescription')


class DaangnRecommendNeighborhoodsDataModel(ResponseModel):
    """GraphQL `data`."""

    recommend_neighborhoods: Annotated[
        list[DaangnRecommendedNeighborhoodModel],
        Field(description='순위 순 추천 동')
    ] = Field(default=[], alias='recommendNeighborhoods')


class DaangnRecommendNeighborhoodsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `recommendNeighborhoods` 응답."""

    data: Annotated[
        DaangnRecommendNeighborhoodsDataModel | None,
        Field(description='결과')
    ] = None
