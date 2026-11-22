"""요청 모델: 아파트 단지 기능(complex)의 상세·시세 추이가 같이 쓰는 것."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class ZigbangDanjisRoomTypesRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/room_types` 경로. 아파트 단지의 평형(공급·전용면적·방·관리비·시세). 경로가 하이픈이 아니라 밑줄이다."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]
