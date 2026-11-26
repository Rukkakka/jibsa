"""응답 모델: 주변 단지 목록 (nearby-complexes)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnGraphQLResponseModel,
    DaangnRegionModel,
    DaangnTradeArticleCountModel,
)

from typing import Annotated


class DaangnNearbyComplexNodeModel(DaangnBaseResponseModel):
    """같은 동 단지 (이름·유형만)."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT / OFFICETEL ...')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None



class DaangnNearbyComplexEdgeModel(DaangnBaseResponseModel):
    """같은 동 단지 edge."""

    node: Annotated[
        DaangnNearbyComplexNodeModel | None,
        Field(description='단지')
    ] = None



class DaangnNearbyComplexesModel(DaangnBaseResponseModel):
    """같은 동 단지 연결 (한 번에 전부, 2026-10-10 실측: 역삼동 255곳)."""

    edges: Annotated[
        list[DaangnNearbyComplexEdgeModel],
        Field(description='단지')
    ] = []



class DaangnNearbyComplexesDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complexes: Annotated[
        DaangnNearbyComplexesModel | None,
        Field(description='같은 동 단지')
    ] = None



class DaangnNearbyComplexesResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexes` 응답 (웹의 `ComplexNearbySectionQuery`)."""

    data: Annotated[
        DaangnNearbyComplexesDataModel | None,
        Field(description='결과')
    ] = None



class DaangnComplexCardDanjiModel(DaangnBaseResponseModel):
    """단지 카드의 공공 정보."""

    total_tot_hseh_cnt: Annotated[
        int | None,
        Field(description='세대수', alias='totalTotHsehCnt')
    ] = None



class DaangnComplexCardModel(DaangnBaseResponseModel):
    """단지 카드 (세대수·현재 매물 수)."""

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
        Field(description='APARTMENT / OFFICETEL ...')
    ] = None
    proptier_danji: Annotated[
        DaangnComplexCardDanjiModel | None,
        Field(description='공공 정보', alias='proptierDanji')
    ] = None
    live_article_count: Annotated[
        DaangnTradeArticleCountModel | None,
        Field(description='거래 유형별 현재 매물 수 (지도 단지 카드에는 total 이 없다)', alias='liveArticleCount')
    ] = None



class DaangnComplexesByOriginalComplexIdsDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complexes_by_original_complex_ids: Annotated[
        list[DaangnComplexCardModel],
        Field(description='단지 카드 (ID 255개도 한 번에 된다)', alias='complexesByOriginalComplexIds')
    ] = []



class DaangnComplexesByOriginalComplexIdsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexesByOriginalComplexIds` 응답 (웹의 `ComplexListPanelMapPinsQuery`)."""

    data: Annotated[
        DaangnComplexesByOriginalComplexIdsDataModel | None,
        Field(description='결과')
    ] = None



class DaangnComplexRegionComplexModel(DaangnBaseResponseModel):
    """단지 페이지의 단지 (유형·지역만 읽는다)."""

    original_id: Annotated[
        str,
        Field(description='단지 ID', alias='originalId')
    ]
    type: Annotated[
        str | None,
        Field(description='APARTMENT / OFFICETEL / ETC ...')
    ] = None
    region: Annotated[
        DaangnRegionModel | None,
        Field(description='단지가 있는 동 (originalId·depth 3)')
    ] = None



class DaangnComplexRegionOutputModel(DaangnBaseResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 complex 가 null 이다."""

    complex: Annotated[
        DaangnComplexRegionComplexModel | None,
        Field(description='단지')
    ] = None



class DaangnComplexRegionDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexRegionOutputModel | None,
        Field(description='단지', alias='complexByOriginalId')
    ] = None



class DaangnComplexRegionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `complexByOriginalId` 응답 (웹의 `ComplexIdSeoQuery`)."""

    data: Annotated[
        DaangnComplexRegionDataModel | None,
        Field(description='결과')
    ] = None
