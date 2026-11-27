"""응답 모델: 인기 단지 (trending-complexes)."""

from pydantic import (
    Field,
)

from jibsa.providers.daangn.api.models.response.common import (
    DaangnBaseResponseModel,
    DaangnCompareRegionModel,
    DaangnGraphQLResponseModel,
    LooseFloat,
)

from typing import (
    Annotated,
)


class DaangnTrendingRealsaleNodeModel(DaangnBaseResponseModel):
    """인기 단지 평형의 최근 매매가."""

    trade_price: Annotated[
        int | None,
        Field(description='매매가 (만원)', alias='tradePrice')
    ] = None


class DaangnTrendingRealsaleEdgeModel(DaangnBaseResponseModel):
    """실거래 edge."""

    node: Annotated[
        DaangnTrendingRealsaleNodeModel | None,
        Field(description='실거래')
    ] = None


class DaangnTrendingRealsaleConnectionModel(DaangnBaseResponseModel):
    """실거래 연결 (최근 1건)."""

    edges: Annotated[
        list[DaangnTrendingRealsaleEdgeModel] | None,
        Field(description='실거래. null 이거나 키가 없으면 실거래 목록을 모르는 것이고(0건이면 []), 빈 목록으로 바꾸지 않는다')
    ] = None


class DaangnTrendingPyInfoModel(DaangnBaseResponseModel):
    """인기 단지 평형."""

    households: Annotated[
        int | None,
        Field(description='이 평형의 세대수', alias='ptpTotHsehCnt')
    ] = None
    exclusive_area: Annotated[
        LooseFloat,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    sale_realsale: Annotated[
        DaangnTrendingRealsaleConnectionModel | None,
        Field(description='최근 매매', alias='saleRealsale')
    ] = None


class DaangnTrendingAreaGroupModel(DaangnBaseResponseModel):
    """인기 단지 전용면적 묶음."""

    is_representative: Annotated[
        bool | None,
        Field(description='대표 평형', alias='isRepresentative')
    ] = None
    py_infos: Annotated[
        list[DaangnTrendingPyInfoModel],
        Field(description='평형', alias='pyInfos')
    ] = []


class DaangnTrendingDanjiModel(DaangnBaseResponseModel):
    """인기 단지 공공 정보."""

    exclusive_area_groups: Annotated[
        list[DaangnTrendingAreaGroupModel],
        Field(description='전용면적 묶음', alias='exclusiveAreaGroups')
    ] = []


class DaangnTrendingComplexModel(DaangnBaseResponseModel):
    """인기 급상승 단지. 사진(`imagesV2`)은 읽지 않는다."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='APARTMENT ...')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approval_date_text: Annotated[
        str | None,
        Field(description="사용승인 문구 (예: '사용승인일 2022.04.28(4년차)')", alias='approvalDateText')
    ] = None
    region: Annotated[
        DaangnCompareRegionModel | None,
        Field(description='시·도·구')
    ] = None
    proptier_danji: Annotated[
        DaangnTrendingDanjiModel | None,
        Field(description='평형·최근 매매', alias='proptierDanji')
    ] = None


class DaangnTrendingComplexesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    trending_complexes: Annotated[
        list[DaangnTrendingComplexModel],
        Field(description='인기 순 단지', alias='trendingComplexes')
    ] = []


class DaangnTrendingComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `trendingComplexes` 응답."""

    data: Annotated[
        DaangnTrendingComplexesDataModel | None,
        Field(description='결과')
    ] = None
