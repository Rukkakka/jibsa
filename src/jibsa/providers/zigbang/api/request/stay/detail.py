"""요청 모델: 단기임대 상세 (listing stay-*)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class ZigbangGuestItemsRequestParameterModel(RequestModel):
    """`GET stay-apis.zigbang.com/guest/items/{itemId}` 경로."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단기임대 매물 ID. 경로에 들어간다')
    ]
