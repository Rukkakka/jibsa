from math import (
    asin,
    ceil,
    cos,
    radians,
    sin,
    sqrt,
)


GEOHASH_BASE32: str = '0123456789bcdefghjkmnpqrstuvwxyz'
EARTH_RADIUS_KM: float = 6371.0088
KM_PER_LAT_DEGREE: float = 110.574
# 세 소스 공통 기본 검색 반경 (km). 출력의 radius_km·검색 범위를 소스끼리 같게 둔다
DEFAULT_RADIUS_KM: float = 1.0
# 한국 매물 좌표 범위. 마라도(33.1)~북쪽 접경, 서해 섬~독도(131.9)를 넉넉히 덮는다.
KOREA_LAT_RANGE: tuple[float, float] = (33.0, 39.0)
KOREA_LNG_RANGE: tuple[float, float] = (124.0, 132.0)


def encode_geohash(lat: float, lng: float, precision: int = 5) -> str:
    """Encode a coordinate as a geohash of `precision` characters.

    정밀도 5 는 약 4.9km, 6 은 약 1.2km 크기의 셀이다.
    """
    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]
    chars: list[str] = []
    bits = 0
    bit_count = 0
    is_lng = True
    while len(chars) < precision:
        value, bounds = (lng, lng_range) if is_lng else (lat, lat_range)
        middle = (bounds[0] + bounds[1]) / 2
        bits <<= 1
        if value >= middle:
            bits |= 1
            bounds[0] = middle
        else:
            bounds[1] = middle
        is_lng = not is_lng
        bit_count += 1
        if bit_count == 5:
            chars.append(GEOHASH_BASE32[bits])
            bits = 0
            bit_count = 0
    return ''.join(chars)


def geohash_bounds(geohash: str) -> tuple[float, float, float, float]:
    """geohash 칸의 (남, 북, 서, 동) 경계."""
    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]
    is_lng = True
    for char in geohash:
        bits = GEOHASH_BASE32.index(char)
        for shift in range(4, -1, -1):
            bounds = lng_range if is_lng else lat_range
            middle = (bounds[0] + bounds[1]) / 2
            if bits >> shift & 1:
                bounds[0] = middle
            else:
                bounds[1] = middle
            is_lng = not is_lng
    return lat_range[0], lat_range[1], lng_range[0], lng_range[1]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two coordinates, in kilometres."""
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def box_around(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """반경 `radius_km` 원을 감싸는 사각형의 (남, 북, 서, 동). 세 소스가 지도 범위를 같은 계산으로 잡는다."""
    lat_delta = radius_km / KM_PER_LAT_DEGREE
    lng_delta = radius_km / (KM_PER_LAT_DEGREE * max(cos(radians(lat)), 1e-6))
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def geohashes_covering(
    lat: float,
    lng: float,
    radius_km: float,
    precision: int = 5,
) -> list[str]:
    """Geohash cells that together cover a circle of `radius_km`.

    원을 감싸는 사각형을 셀 절반 이하 간격의 격자로 샘플링해 겹치는 셀을 모으고, 원에 닿지 않는
    모서리 셀은 뺀다. 간격이 셀보다 넓으면 셀 줄을 건너뛰어 반경 안 매물을 놓친다
    (고정 9×9 격자일 때 정밀도 6·반경 4km 에서 중심 0.16km 옆 셀까지 빠졌다).
    """
    cells = _cells_in_box(*box_around(lat, lng, radius_km), precision)
    return [cell for cell in cells if _cell_distance_km(lat, lng, cell) <= radius_km]


def _cells_in_box(south: float, north: float, west: float, east: float, precision: int) -> list[str]:
    """사각형과 겹치는 geohash 칸. 사각형을 칸 절반 이하 간격의 격자로 샘플링한다 (변 위의 점도 포함)."""
    cell_south, cell_north, cell_west, cell_east = geohash_bounds(encode_geohash(south, west, precision))
    lat_steps = max(8, ceil(2 * (north - south) / (cell_north - cell_south)))
    lng_steps = max(8, ceil(2 * (east - west) / (cell_east - cell_west)))
    cells: dict[str, None] = {}
    for i in range(lat_steps + 1):
        for j in range(lng_steps + 1):
            cells.setdefault(encode_geohash(
                south + (north - south) * i / lat_steps,
                west + (east - west) * j / lng_steps,
                precision,
            ))
    return list(cells)


def geohashes_touching(polygons: 'MultiPolygon', precision: int) -> list[str]:
    """MultiPolygon 에 닿는 geohash 칸.

    조각마다 감싸는 사각형의 칸 중 경계 꼭짓점이 들어 있거나 칸 모서리가 경계 안인 칸만 남긴다. 경계 전체를
    감싸는 원을 덮으면 섬이 흩어진 읍·면은 바다 칸이 대부분이다 (2026-10-10 실측 정밀도 6: 울릉읍 12,215칸 →
    64칸, 역삼동 28칸 → 14칸). 동 경계는 꼭짓점이 촘촘해 경계선이 지나는 칸에는 꼭짓점이 들어 있다.
    """
    vertex_cells = {
        encode_geohash(point[1], point[0], precision) for rings in polygons for ring in rings for point in ring
    }
    corner_inside: dict[tuple[int, float, float], bool] = {}
    cells: dict[str, None] = {}
    for part, rings in enumerate(polygons):
        if not rings or not rings[0]:
            continue
        lats = [point[1] for point in rings[0]]
        lngs = [point[0] for point in rings[0]]
        for cell in _cells_in_box(min(lats), max(lats), min(lngs), max(lngs), precision):
            if cell in cells:
                continue
            if cell in vertex_cells:
                cells[cell] = None
                continue
            south, north, west, east = geohash_bounds(cell)
            for corner_lat, corner_lng in ((south, west), (south, east), (north, west), (north, east)):
                # 이웃 칸과 모서리를 나눠 써서 조각마다 한 번만 잰다
                key = (part, corner_lat, corner_lng)
                if key not in corner_inside:
                    corner_inside[key] = in_multipolygon(corner_lat, corner_lng, [rings])
                if corner_inside[key]:
                    cells[cell] = None
                    break
    return list(cells)


def _cell_distance_km(lat: float, lng: float, geohash: str) -> float:
    """점에서 geohash 칸까지의 가장 가까운 거리 (점이 칸 안이면 0)."""
    south, north, west, east = geohash_bounds(geohash)
    return haversine_km(lat, lng, min(max(lat, south), north), min(max(lng, west), east))


def in_korea(lat: float, lng: float) -> bool:
    """좌표가 한국 매물을 찾을 수 있는 범위 안인지."""
    return (
        KOREA_LAT_RANGE[0] <= lat <= KOREA_LAT_RANGE[1]
        and KOREA_LNG_RANGE[0] <= lng <= KOREA_LNG_RANGE[1]
    )


# GeoJSON MultiPolygon 좌표: [폴리곤[링[[경도, 위도], ...], ...], ...]. 링 첫째는 바깥, 나머지는 구멍.
MultiPolygon = list[list[list[list[float]]]]


def _in_ring(lat: float, lng: float, ring: list[list[float]]) -> bool:
    """점이 닫힌 링 안에 있는지 (광선 교차법)."""
    inside = False
    count = len(ring)
    for index in range(count):
        lng1, lat1 = ring[index][0], ring[index][1]
        lng2, lat2 = ring[index - 1][0], ring[index - 1][1]
        if (lat1 > lat) != (lat2 > lat):
            crossing = lng1 + (lat - lat1) * (lng2 - lng1) / (lat2 - lat1)
            if lng < crossing:
                inside = not inside
    return inside


def in_multipolygon(lat: float, lng: float, polygons: MultiPolygon) -> bool:
    """점이 GeoJSON MultiPolygon 안에 있는지. 구멍(안쪽 링) 안이면 밖으로 본다."""
    for rings in polygons:
        if not rings or not _in_ring(lat, lng, rings[0]):
            continue
        if not any(_in_ring(lat, lng, hole) for hole in rings[1:]):
            return True
    return False


def multipolygon_bounds(polygons: MultiPolygon) -> tuple[float, float, float]:
    """MultiPolygon 을 감싸는 원의 (중심 위도, 중심 경도, 반지름 km). 경계를 덮는 geohash 칸을 고르는 데 쓴다."""
    points = [point for rings in polygons for ring in rings for point in ring]
    lats = [point[1] for point in points]
    lngs = [point[0] for point in points]
    center_lat = (min(lats) + max(lats)) / 2
    center_lng = (min(lngs) + max(lngs)) / 2
    radius_km = max(
        haversine_km(center_lat, center_lng, corner_lat, corner_lng)
        for corner_lat in (min(lats), max(lats))
        for corner_lng in (min(lngs), max(lngs))
    )
    return center_lat, center_lng, radius_km
