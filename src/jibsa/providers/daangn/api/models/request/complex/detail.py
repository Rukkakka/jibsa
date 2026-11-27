"""요청 모델: 단지 정보 (complex)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnComplexesRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/complexes/{originalId}` 경로."""

    original_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='숫자 단지 ID (PropComplex.originalId)')
    ]
