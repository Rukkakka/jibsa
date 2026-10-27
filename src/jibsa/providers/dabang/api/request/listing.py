from pydantic import Field

from jibsa.providers.dabang.api.request.common import (
    DabangCategoryListRequestParameterModel,
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
)


class DabangRoomListCategoryV5RequestParameterModel(DabangCategoryListRequestParameterModel):
    """`GET /api/v5/room-list/category/{category}/{search_type}` 쿼리 (매물 지도 목록)."""


class DabangNewRoomDetailV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/new-room/detail` 쿼리.

    Args:
        room_id: 매물 ID (24자리 16진수).
    """

    room_id: Annotated[
        str,
        Field(pattern=r'^[0-9a-f]{24}$', description='매물 ID')
    ]


class DabangRoomGetRoomIdV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/room/get-room-id` 쿼리. 화면의 매물번호를 매물 ID 로 바꾼다.

    Args:
        seq: 매물번호.
        type: 웹이 늘 0 을 보낸다. Defaults to 0.
    """

    seq: Annotated[
        int,
        Field(gt=0, description='매물번호')
    ]
    type: Annotated[
        Literal[0],
        Field(description='웹이 늘 보내는 값')
    ] = 0
