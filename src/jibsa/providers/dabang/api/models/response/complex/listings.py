"""응답 모델: 단지 매물 목록 (search listings --complex)."""
from jibsa.providers.dabang.api.models.response.common import (
    DabangRoomListResponseModel,
)


class DabangRoomListCategoryComplexV5ResponseModel(DabangRoomListResponseModel):
    """`GET /api/v5/room-list/category/{category}/complex` 응답 (단지 하나의 매물)."""
