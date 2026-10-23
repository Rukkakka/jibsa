"""요청 모델: 단지 비교와 주변 단지 (compare, nearby-complexes)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnSalesType

from typing import Annotated


class DaangnComplexCompareRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId` 비교 칸 쿼리 변수 (웹의 `ComplexCompareColumnQuery`, 단지 하나 요청 1회)."""

    original_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='originalId')
    ]


class DaangnNearbyComplexesRequestPayloadModel(RequestModel):
    """GraphQL `complexes` 쿼리 변수 (웹의 `ComplexNearbySectionQuery`, 같은 동 단지)."""

    first: Annotated[
        int,
        Field(ge=1, le=1200, description='받을 단지 수. 페이지 정보 없이 이만큼 한 번에 준다 (웹은 300, 화곡동은 703곳이다)')
    ] = 300
    region3_id: Annotated[
        int,
        Field(gt=0, description='당근 동 ID', alias='region3Id')
    ]


class DaangnComplexesByOriginalComplexIdsRequestPayloadModel(RequestModel):
    """GraphQL `complexesByOriginalComplexIds` 쿼리 변수 (웹의 `ComplexNearbySectionCardsQuery`, 단지 카드)."""

    complex_ids: Annotated[
        list[str],
        Field(min_length=1, description='숫자 단지 ID (255개도 한 번에 된다)', alias='complexIds')
    ]
    sales_types: Annotated[
        list[DaangnSalesType],
        Field(description='현재 매물 수를 셀 매물 종류. 빈 목록이면 전체', alias='salesTypes')
    ] = []
