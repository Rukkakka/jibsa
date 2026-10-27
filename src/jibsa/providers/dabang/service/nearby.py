"""주변 (nearby) 과 역 둘레 평균 매물가 (station-prices)."""
from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import box_around
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangOneTwoFiltersModel
from jibsa.providers.dabang.api.request.nearby import (
    DabangMarkersCategoryV5RequestParameterModel,
    DabangNearTarget,
    DabangNearV5RequestParameterModel,
    DabangTransitNearV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.nearby import DabangNearGroupModel
from jibsa.providers.dabang.service.common import (
    COMPLEX_ID_PATTERN,
    DabangPlace,
    bbox_of,
    complex_url,
    is_missing_id,
    listing_url,
    manwon_from_text,
)

from typing import Annotated


# 가까운 시설 종류 코드 → 이름 (카카오 장소 분류 코드와 다방 코드). 지하철역(SW8)은 transit/near 의 역 목록으로, CCTV 는
# 이름·범위가 없어 쓰지 않는다. 다방은 대상마다 다른 종류를 준다 (2026-10-26 실측: 매물은 BS·SW8·CS2·CE7·BK9·PO3,
# 단지는 BS·SW8·MT1·CS2·BK9·PM9, 둘 다 POLICE). 웹에 코드 이름표가 없어 이름은 카카오 분류 뜻대로 붙인다
NEAR_LABELS: dict[str, str] = {
    'BS': '버스정류장',
    'MT1': '마트',
    'CS2': '편의점',
    'CE7': '카페',
    'BK9': '은행',
    'PM9': '약국',
    'PO3': '공공기관',
    'POLICE': '경찰',
}
SCHOOL_LABELS: dict[str, str] = {'NS': '어린이집', 'KS': '유치원', 'ES': '초등학교', 'MS': '중학교', 'HS': '고등학교'}
BUILDING_LABELS: dict[str, str] = {'HOUSE_VILLA': '빌라', 'OFFICETEL': '오피스텔', 'APT': '아파트'}
ROOM_LABELS: dict[str, str] = {'ONE_ROOM': '원룸', 'TWO_ROOM': '투룸'}
# 역 둘레 평균 매물가를 받으려고 역을 덮는 지도 범위 (km). 확대 수준 16 이면 범위 안 역 표시에 평균이 붙는다
STATION_BOX_KM: float = 0.3


class DabangNearbyStation(BaseModel):
    """가까운 지하철역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    lines: Annotated[
        list[str],
        Field(description='노선')
    ]
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m, 직선)')
    ] = None


class DabangNearestPlace(BaseModel):
    """가장 가까운 시설 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str,
        Field(description='시설 종류')
    ]
    name: Annotated[
        str | None,
        Field(description='이름 (경찰은 다방이 이름을 주지 않아 null)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m, 직선)')
    ] = None


class DabangNearby(BaseModel):
    """매물·단지 둘레 교통과 가까운 시설."""

    model_config = ConfigDict(
        extra='forbid',
    )

    target: Annotated[
        str,
        Field(description="'매물' 또는 '단지'")
    ]
    id: Annotated[
        str,
        Field(description='매물 ID 또는 단지 ID')
    ]
    stations: Annotated[
        list[DabangNearbyStation],
        Field(description='반경(station_radius_m) 안 지하철역, 가까운 순')
    ]
    station_radius_m: Annotated[
        int | None,
        Field(description='역을 찾은 반경 (m)')
    ] = None
    bus_route_count: Annotated[
        int | None,
        Field(description='반경(bus_radius_m) 안 정류장을 지나는 버스 노선 수')
    ] = None
    bus_radius_m: Annotated[
        int | None,
        Field(description='버스 노선을 센 반경 (m)')
    ] = None
    nearest: Annotated[
        list[DabangNearestPlace],
        Field(description='종류마다 가장 가까운 시설 (매물: 버스정류장·편의점·카페·은행·공공기관·경찰, 단지: 버스정류장·마트·편의점·은행·약국·경찰). 다방이 찾지 못한 종류는 없다')
    ]
    schools: Annotated[
        list[DabangNearestPlace],
        Field(description='종류마다 가장 가까운 어린이집·유치원·초·중·고등학교 (배정 학교가 아니다). 다방 범위 안에 없는 종류는 없다')
    ]
    url: Annotated[
        str,
        Field(description='매물·단지 페이지 URL')
    ]


def _nearest(groups: list[DabangNearGroupModel], labels: dict[str, str]) -> list[DabangNearestPlace]:
    places = []
    for group in groups:
        label = labels.get(group.query)
        if label is None or not group.pois:
            continue
        poi = min(group.pois, key=lambda item: item.distance if item.distance is not None else float('inf'))
        places.append(DabangNearestPlace(
            type=label, name=poi.name, distance_m=None if poi.distance is None else round(poi.distance),
        ))
    return places


def get_nearby(client: DabangClient, target_id: str) -> DabangNearby:
    """매물(24자리 ID)·단지(28자리 ID) 둘레의 지하철역·버스 노선과 가까운 시설 (요청 2회). 시설 좌표는 내보내지 않는다.

    Raises:
        JibsaError: 없는 ID 일 때 (NOT_FOUND).
    """
    target: DabangNearTarget = 'complex' if COMPLEX_ID_PATTERN.fullmatch(target_id) else 'room'
    # 없는 ID 는 ID 가 경로에 들어가는 시설 요청으로 가린다 (400). 교통 요청은 ID 가 쿼리로 가서 없는 ID 에도 빈 결과를 주므로
    # (2026-10-27 실측) 그 에러는 다방 주소가 바뀐 것이다 (`is_missing_id`)
    try:
        near = client.run_request_near_v5(DabangNearV5RequestParameterModel(target=target, target_id=target_id)).result
    except HTTPStatusError as exc:
        if is_missing_id(exc):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방에서 찾지 못한 {"단지" if target == "complex" else "매물"}입니다: {target_id}',
                hint='ID 를 같은 소스(dabang) 결과에서 그대로 옮겼는지 확인하세요',
            ) from None
        raise
    transit = client.run_request_transit_near_v5(DabangTransitNearV5RequestParameterModel(target=target, target_id=target_id)).result
    subway = transit.subway if transit else None
    route = transit.route if transit else None
    return DabangNearby(
        target='단지' if target == 'complex' else '매물',
        id=target_id,
        stations=[
            DabangNearbyStation(
                name=station.name,
                lines=[line.name for line in station.line_list if line.name],
                distance_m=None if station.distance is None else round(station.distance),
            )
            for station in (subway.list_ if subway else [])
        ],
        station_radius_m=subway.radius if subway else None,
        bus_route_count=len(route.list_) if route else None,
        bus_radius_m=route.radius if route else None,
        nearest=_nearest((near.convenience + near.safety) if near else [], NEAR_LABELS),
        schools=_nearest(near.education if near else [], SCHOOL_LABELS),
        url=complex_url(target_id) if target == 'complex' else listing_url(target_id),
    )


class DabangStationPrice(BaseModel):
    """역 둘레 평균 매물가 한 칸 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    building_type: Annotated[
        str,
        Field(description='건물 유형 (빌라, 오피스텔, 아파트)')
    ]
    room: Annotated[
        str,
        Field(description='방 개수 (원룸, 투룸)')
    ]
    lease_average_manwon: Annotated[
        float | None,
        Field(description='전세 매물 평균 전세금 (만원). 매물이 없으면 null')
    ] = None
    rent_deposit_average_manwon: Annotated[
        float | None,
        Field(description='월세 매물 평균 보증금 (만원)')
    ] = None
    rent_average_manwon: Annotated[
        float | None,
        Field(description='월세 매물 평균 월세 (만원)')
    ] = None


class DabangStationPrices(BaseModel):
    """역 둘레 평균 매물가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station: Annotated[
        str,
        Field(description='역 이름')
    ]
    radius_m: Annotated[
        int | None,
        Field(description='다방 역 반경 (m). 이 안 매물의 평균이다')
    ] = None
    basis: Annotated[
        str,
        Field(description='무엇의 평균인지')
    ]
    prices: Annotated[
        list[DabangStationPrice],
        Field(description='건물 유형 × 방 개수별 평균')
    ]


def get_station_prices(client: DabangClient, place: DabangPlace) -> DabangStationPrices:
    """역 둘레 평균 매물가 (원룸·투룸 지도 집계 1회). 다방 화면의 '평균 매물가' 로, 실거래가가 아니라 지금 올라온 매물 가격의
    평균이다. 다방 원룸·투룸 목록(방 1~2개)으로 셈해 쓰리룸 이상은 없다.

    Raises:
        JibsaError: 역이 아니거나 (INVALID_ARGUMENT), 다방이 그 역의 평균을 주지 않을 때 (NOT_FOUND).
    """
    if place.kind != 'station' or place.place_id is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'역 이름이 아닙니다: {place.name}',
            hint="지하철역 이름(예: '강남역')을 주세요",
        )
    result = client.run_request_markers_category_v5(DabangMarkersCategoryV5RequestParameterModel(
        category='one-two',
        filters=DabangOneTwoFiltersModel(),
        bbox=bbox_of(*box_around(place.lat, place.lng, STATION_BOX_KM)),
    )).result
    station = next((item for item in (result.subway_list if result else []) if item.id == place.place_id), None)
    if station is None or station.average_price_list is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방이 {place.name}의 평균 매물가를 주지 않았습니다',
            hint='역 둘레 매물은 jibsa dabang search listings room <역> 으로 직접 보세요',
        )
    prices = []
    for item in station.average_price_list:
        deposit, _, rent = (item.monthly_rent or '').partition('/')
        prices.append(DabangStationPrice(
            building_type=BUILDING_LABELS.get(item.building_category or '', item.building_category or ''),
            room=ROOM_LABELS.get(item.room_type or '', item.room_type or ''),
            lease_average_manwon=manwon_from_text(item.lease),
            rent_deposit_average_manwon=manwon_from_text(deposit) if rent else None,
            rent_average_manwon=manwon_from_text(rent) if rent else None,
        ))
    return DabangStationPrices(
        station=station.name,
        radius_m=station.radius,
        basis="다방 '평균 매물가': 역 반경 안에 지금 올라온 원룸·투룸 목록 매물(방 1~2개)의 평균 (실거래가 아님)",
        prices=prices,
    )
