"""응답 모델: 지역·역·좌표 해석과 동 경계 (search locations, 모든 검색의 지역 해석)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel

from typing import Annotated


# 경계 꼭짓점 [경도, 위도]. 값이 모자란 점은 응답 형식 변경이라 모델 검증(PARSE_ERROR)에서 막는다. 통과시키면 geohash 계산의
# point[1] 이 IndexError 를 내 jibsa 내부 오류(INTERNAL_ERROR)로 안내된다
GeoJsonPoint = Annotated[list[float], Field(min_length=2)]


# ---------------------------------------------------------------------------
# GET /v2/search
# ---------------------------------------------------------------------------

class ZigbangSearchV2ResponseModel(ResponseModel):
    """지역/역/단지 검색 응답."""

    success: Annotated[
        bool,
        Field(description='요청 성공 여부')
    ]
    items: Annotated[
        list[ZigbangSearchItemModel],
        Field(description='검색 결과. 관련도 순')
    ] = []


# ---------------------------------------------------------------------------
# GET /v2/local/polygon
# ---------------------------------------------------------------------------

class ZigbangGeoJsonModel(ResponseModel):
    """행정구역 경계 (GeoJSON)."""

    type: Annotated[
        str | None,
        Field(description='GeoJSON 종류. 조각이 하나인 동도 늘 MultiPolygon 이다 (2026-10-10 실측 34곳)')
    ] = None
    coordinates: Annotated[
        list[list[list[GeoJsonPoint]]],
        Field(description='[폴리곤[링[[경도, 위도]]]]. 링 첫째는 바깥, 나머지는 구멍')
    ] = []


class ZigbangLocalPolygonV2ResponseModel(ResponseModel):
    """geohash 칸 중심이 속한 행정구역과 경계."""

    code: Annotated[
        str | None,
        Field(description='직방 지역 코드 (법정동코드 앞 2·5·8자리)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='지역 이름')
    ] = None
    geojson: Annotated[
        ZigbangGeoJsonModel | None,
        Field(description='경계. polygon=true 가 아니면 null')
    ] = None
