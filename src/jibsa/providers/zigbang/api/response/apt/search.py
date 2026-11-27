"""응답 모델: 아파트 매물 검색 (search listings apt)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import (
    ZigbangBaseResponseModel,
    ZigbangItemCatalogModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/locals/{localCode}/item-catalogs
# ---------------------------------------------------------------------------

class ZigbangLocalsItemCatalogsResponseModel(ZigbangBaseResponseModel):
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
# GET /apt/locals/polygon
# ---------------------------------------------------------------------------

class ZigbangLocalsPolygonResponseModel(ZigbangBaseResponseModel):
    """geohash 칸 중심이 속한 동 (예: `{code: '11650108', name: '서초동', geojson: null}`). 경계(geojson)는 읽지 않는다."""

    code: Annotated[
        str | None,
        Field(description='직방 지역 코드. local3 이면 법정동코드 앞 8자리 (2026-11-15 실측)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='동 이름')
    ] = None
