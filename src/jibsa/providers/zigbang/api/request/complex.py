"""요청 모델: 아파트 단지·오피스텔 건물 정보와 단지 매물 목록 (complex, search listings --complex)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import (
    ZigbangItemsFiltersRequestParameterModel,
    ZigbangOfficetelOrderMixin,
)

from typing import Annotated


class ZigbangItemsOfficetelsBuildingV1RequestParameterModel(ZigbangItemsFiltersRequestParameterModel, ZigbangOfficetelOrderMixin):
    """`GET /house/property/v1/items/officetels/{buildingId}` 경로 + 쿼리.

    건물 안의 매물. 가격·관리비는 만원이고 상세 조건은 지도 목록과 같다.
    """

    building_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='오피스텔 건물 ID (검색 결과의 id). 경로에 들어가며 쿼리로는 보내지 않는다')
    ]


class ZigbangDanjisSchoolsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/schools` 경로. 아파트 단지의 학군."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]
