"""요청 모델: 재개발 구역 정보 (redevelopment)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.models.request.common import (
    NaverPriceFilterModel,
    NaverTradeType,
)

from typing import (
    Annotated,
)


class NaverComplexRedevelopmentV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/complex/redevelopment` 쿼리. 재개발 구역 하나의 기본 정보."""

    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호', alias='redevelopmentAreaNumber')
    ]


class NaverComplexRedevelopmentAreaArticleStatsV1RequestParameterModel(NaverPriceFilterModel):
    """`GET /front-api/v1/complex/redevelopmentArea/articleStats` 쿼리. 구역 매물 수와 호가 범위.

    배열은 단지 매물 집계처럼 `tradeTypes[]=A1` 로 키에 `[]` 를 붙여 반복한다. 가격 키는 구역 매물 목록과 같고 원 단위다.
    """

    redevelopment_area_number: Annotated[
        int,
        Field(gt=0, description='재개발 구역 번호', alias='redevelopmentAreaNumber')
    ]
    trade_types: Annotated[
        list[NaverTradeType],
        Field(description='거래 유형 필터. 비우면 전체', alias='tradeTypes[]')
    ] = []
