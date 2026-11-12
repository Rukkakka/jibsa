"""요청 모델: 단지 비교와 주변 단지 (compare, nearby-complexes)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnComplexTradeType

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
    """GraphQL `complexesByOriginalComplexIds` 쿼리 변수 (웹의 `ComplexListPanelMapPinsQuery`, 지도 단지 목록 카드).

    웹은 지도 필터가 비었으면 `tradeType: 'BUY'`·`exclusiveUseArea: null` 로 부른다 (complexFilter `d()`, 2026-11-12 번들).
    예전에 쓰던 `ComplexNearbySectionCardsQuery`(ba9845…)는 11월 번들에 없어 웹에 남은 이 쿼리로 바꿨다 (#215).
    """

    original_ids: Annotated[
        list[str],
        Field(min_length=1, description='숫자 단지 ID (258개도 한 번에 된다, 2026-11-12 실측)', alias='originalIds')
    ]
    trade_type: Annotated[
        DaangnComplexTradeType,
        Field(description='카드의 최근 실거래 거래 유형 (jibsa 는 읽지 않는다)', alias='tradeType')
    ] = 'BUY'


class DaangnComplexRegionRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId` 쿼리 변수 (웹의 `ComplexIdSeoQuery`, 단지 페이지의 지역·이름).

    단지 비교 칸(`ComplexCompareColumnQuery`)의 지역에는 동 ID 가 없어(Relay id 만) 이 쿼리로 동 ID 를 받는다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]
