"""요청 모델: 단지 비교 칸(complex_compare). compare 와 다른 기능(common·real_price 의 평형·시세 칸)이 같이 쓴다."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnComplexCompareRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId` 비교 칸 쿼리 변수 (웹의 `ComplexCompareColumnQuery`, 단지 하나 요청 1회)."""

    original_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='originalId')
    ]
