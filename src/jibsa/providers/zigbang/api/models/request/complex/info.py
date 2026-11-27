"""요청 모델: 아파트 단지 학군 (complex)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class ZigbangDanjisSchoolsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/schools` 경로. 아파트 단지의 학군."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]
