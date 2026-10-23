"""응답 모델: 아파트 매물 검색 (search listings apt): 지역 목록과 반경(nearby-danjis) 검색."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import ZigbangItemCatalogModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/locals/{localCode}/item-catalogs
# ---------------------------------------------------------------------------

class ZigbangLocalsItemCatalogsResponseModel(ResponseModel):
    """지역 아파트 매물 카탈로그 응답."""

    local_code: Annotated[
        str | None,
        Field(description='조회한 지역 코드', alias='localCode')
    ] = None
    count: Annotated[
        int,
        Field(description='조건에 맞는 카탈로그 수 (페이지 무관)')
    ] = 0
    catalogs: Annotated[
        list[ZigbangItemCatalogModel],
        Field(description='이번 페이지의 카탈로그', alias='list')
    ] = []
    local1: Annotated[
        str | None,
        Field(description='시/도')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/nearby-danjis
# ---------------------------------------------------------------------------

class ZigbangNearbyDanjiModel(ResponseModel):
    """반경 안 아파트 단지 한 곳."""

    id: Annotated[
        int,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    local1: Annotated[
        str | None,
        Field(description='시/도 (예: 서울특별시)')
    ] = None
    local2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    local3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None
    lat: Annotated[
        float | None,
        Field(description='단지 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='단지 경도')
    ] = None
    household: Annotated[
        str | None,
        Field(description="세대수 문구 (예: '38세대')")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='중심에서 단지까지 거리 (m)', alias='distanceNum')
    ] = None


class ZigbangNearbyDanjisResponseModel(ResponseModel):
    """반경 안 아파트 단지 목록 (가까운 순)."""

    danjis: Annotated[
        list[ZigbangNearbyDanjiModel],
        Field(description='가까운 순 단지', alias='list')
    ] = []
