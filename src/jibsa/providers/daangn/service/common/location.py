"""당근 좌표·웹 지도 화면 범위·역 이름 다듬기."""

import math

from jibsa.core.geo import haversine_km
from jibsa.providers.daangn.api.models.request.common import (
    DaangnBoundsLocationFilterModel,
    DaangnCoordinateInputModel,
)
from jibsa.providers.daangn.api.models.response.common import DaangnCoordinateModel
from jibsa.providers.daangn.service.common.constants import (
    MAP_TILE_PX,
    MAP_VIEW_HEIGHT_PX,
    MAP_VIEW_WIDTH_PX,
    STATION_LINE_SUFFIX_PATTERN,
)


def map_view_bounds(lat: float, lng: float, zoom: int) -> tuple[DaangnBoundsLocationFilterModel, float, float]:
    """(`lat`, `lng`) 를 가운데에 둔 웹 데스크톱 지도 화면의 범위와 그 가로·세로 (km).

    maplibre 처럼 Web Mercator 픽셀 좌표로 화면 크기만큼 넓혀 꼭짓점을 구한다. 위도 37.5° 에서 줌 15 는 약 1.6×1.7km,
    줌 12 는 약 12.8×13.6km 다.
    """
    world = MAP_TILE_PX * 2 ** zoom
    sin_lat = math.sin(math.radians(lat))
    x = (lng + 180) / 360 * world
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * world

    def unproject(px: float, py: float) -> tuple[float, float]:
        return math.degrees(math.atan(math.sinh(math.pi - 2 * math.pi * py / world))), px / world * 360 - 180

    north, west = unproject(x - MAP_VIEW_WIDTH_PX / 2, y - MAP_VIEW_HEIGHT_PX / 2)
    south, east = unproject(x + MAP_VIEW_WIDTH_PX / 2, y + MAP_VIEW_HEIGHT_PX / 2)
    bounds = DaangnBoundsLocationFilterModel(
        ne_coordinate=DaangnCoordinateInputModel(lat=north, lon=east),
        sw_coordinate=DaangnCoordinateInputModel(lat=south, lon=west),
    )
    return bounds, round(haversine_km(lat, west, lat, east), 1), round(haversine_km(north, lng, south, lng), 1)


def coordinate_point(coordinate: DaangnCoordinateModel | None) -> tuple[float, float] | None:
    """좌표의 (위도, 경도). 좌표가 없거나 위도·경도 중 하나라도 없으면 None."""
    if coordinate is None or coordinate.lat is None or coordinate.lon is None:
        return None
    return coordinate.lat, coordinate.lon


def station_name(name: str) -> str:
    """'역' 까지 붙인 역 이름 ('역삼' → '역삼역'). 노선 꼬리('양평역(경의중앙선)')가 있으면 꼬리 앞 이름을 본다.

    출퇴근 API 는 같은 이름 역을 가르려 이름 뒤에 노선을 붙인다 (2026-11-13 실측: 서울5호선 '양평역', 경의중앙선
    '양평역(경의중앙선)'). 꼬리까지 보고 '역' 을 붙이면 '양평역(경의중앙선)역' 이 되었다 (2026-11-13 리뷰).
    """
    base = station_base_name(name)
    return name if base.endswith('역') else f'{base}역{name[len(base):]}'


def station_base_name(name: str) -> str:
    """출퇴근 API 역 이름에서 노선 꼬리를 뗀 이름 ('양평역(경의중앙선)' → '양평역'). 역 검색(`find_station`)은 꼬리 없는 이름만 안다."""
    return STATION_LINE_SUFFIX_PATTERN.sub('', name)
