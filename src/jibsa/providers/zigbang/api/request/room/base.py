"""요청 모델: 원룸·빌라·오피스텔 검색(search)·상세(detail)이 같이 쓰는 주거 상세 경로."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


# 주거 상세는 `get_listing`(room/detail)과 `attach_building_use`(room/search) 가 함께 부르는 엔드포인트라 요청·응답 모델을 모두 room 의
# base 에 둔다 (provider-conventions 기준 7)
class ZigbangItemsDetailV1RequestParameterModel(RequestModel):
    """`GET /house/property/v1/items/{itemId}/detail` 경로."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='매물 ID. 경로에 사용한다')
    ]
