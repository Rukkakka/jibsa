"""요청 모델: 원룸·빌라·오피스텔 매물 검색 (search listings room): 지도 칸·역 반경 목록."""


from pydantic import (
    Field,
    field_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.models.request.common import (
    ZigbangItemsFiltersRequestParameterModel,
    ZigbangOfficetelOrderMixin,
    ZigbangSalesType,
)

from typing import Annotated


class ZigbangOneroomSalesTypesMixin(RequestModel):
    """원룸 목록(지도 칸·역 반경)은 매매가 없다."""

    @field_validator('sales_types', check_fields=False)
    @classmethod
    def validate_sales_types(cls, v: list[ZigbangSalesType]) -> list[ZigbangSalesType]:
        if '매매' in v:
            raise ValueError("원룸은 '매매' 거래 유형을 지원하지 않습니다")
        return v


class ZigbangItemsRequestParameterModel(ZigbangItemsFiltersRequestParameterModel):
    """지도 칸(geohash) 목록 쿼리. 조건은 `ZigbangItemsFiltersRequestParameterModel` 과 같다."""

    geohash: Annotated[
        str,
        Field(
            pattern=r'^[0-9bcdefghjkmnpqrstuvwxyz]{4,7}$',
            description='지도 타일 geohash. 정밀도 5 ≈ 4.9km, 6 ≈ 1.2km'
        )
    ]


class ZigbangItemsOneroomsV1RequestParameterModel(ZigbangItemsRequestParameterModel, ZigbangOneroomSalesTypesMixin):
    """`GET /house/property/v1/items/onerooms` 쿼리. 원룸은 매매가 없다."""


class ZigbangItemsOfficetelsV1RequestParameterModel(ZigbangItemsRequestParameterModel, ZigbangOfficetelOrderMixin):
    """`GET /house/property/v1/items/officetels` 쿼리."""


class ZigbangItemsVillasV1RequestParameterModel(ZigbangItemsRequestParameterModel):
    """`GET /house/property/v1/items/villas` 쿼리."""


class ZigbangItemsSubwaysRequestParameterModel(ZigbangItemsFiltersRequestParameterModel):
    """역 반경 목록 공통 조건. 지하철 ID 는 경로에, 반경(km)은 쿼리에 보낸다."""

    subway_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='직방 검색 결과의 지하철 ID')
    ]
    radius: Annotated[
        float,
        Field(gt=0, le=5, description='역 중심 반경 (km)')
    ]


class ZigbangItemsSubwaysOneroomsV1RequestParameterModel(ZigbangItemsSubwaysRequestParameterModel, ZigbangOneroomSalesTypesMixin):
    """`GET /house/property/v1/items/subways/{subwayId}/onerooms` 조건."""


class ZigbangItemsSubwaysOfficetelsV1RequestParameterModel(ZigbangItemsSubwaysRequestParameterModel, ZigbangOfficetelOrderMixin):
    """`GET /house/property/v1/items/subways/{subwayId}/officetels` 조건."""


class ZigbangItemsSubwaysVillasV1RequestParameterModel(ZigbangItemsSubwaysRequestParameterModel):
    """`GET /house/property/v1/items/subways/{subwayId}/villas` 조건."""
