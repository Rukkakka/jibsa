"""응답 모델: 원룸·빌라·오피스텔 매물 검색 (search listings room): 지도 칸·역 반경 목록의 핀과 섹션."""

from pydantic import Field

from jibsa.providers.zigbang.api.models.response.common import (
    ZigbangBaseResponseModel,
    ZigbangItemPinModel,
    ZigbangItemSectionModel,
    ZigbangLatLngModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/{onerooms|officetels|villas}
# ---------------------------------------------------------------------------

class ZigbangSubwayLineModel(ZigbangBaseResponseModel):
    """지하철 노선."""

    name: Annotated[
        str,
        Field(description='노선명 (예: 2호선)')
    ]
    code: Annotated[
        str | None,
        Field(description='노선 코드')
    ] = None


class ZigbangSubwayModel(ZigbangBaseResponseModel):
    """타일 안의 지하철역."""

    id: Annotated[
        int,
        Field(description='역 ID')
    ]
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    location: Annotated[
        ZigbangLatLngModel | None,
        Field(description='역 좌표')
    ] = None
    lines: Annotated[
        list[ZigbangSubwayLineModel],
        Field(description='지나는 노선')
    ] = []


class ZigbangItemsResponseModel(ZigbangBaseResponseModel):
    """geohash 타일 매물 목록 응답 (원룸·오피스텔·빌라 공통)."""

    items: Annotated[
        list[ZigbangItemPinModel],
        Field(description='타일 안의 모든 매물 핀')
    ] = []
    sections: Annotated[
        list[ZigbangItemSectionModel],
        Field(description='노출 구역별 매물 ID')
    ] = []
    subways: Annotated[
        list[ZigbangSubwayModel],
        Field(description='타일 안의 지하철역')
    ] = []


class ZigbangItemsOneroomsV1ResponseModel(ZigbangItemsResponseModel):
    """원룸 목록 응답."""


class ZigbangItemsOfficetelsV1ResponseModel(ZigbangItemsResponseModel):
    """오피스텔 목록 응답."""


class ZigbangItemsVillasV1ResponseModel(ZigbangItemsResponseModel):
    """빌라 목록 응답."""


class ZigbangItemsSubwaysOneroomsV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 원룸 매물 핀. 지도 목록과 같은 응답 모양이다."""


class ZigbangItemsSubwaysOfficetelsV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 오피스텔 매물 핀. 지도 목록과 같은 응답 모양이다."""


class ZigbangItemsSubwaysVillasV1ResponseModel(ZigbangItemsResponseModel):
    """역 반경 안 빌라 매물 핀. 지도 목록과 같은 응답 모양이다."""
