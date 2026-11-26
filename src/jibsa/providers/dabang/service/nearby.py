"""주변 (nearby: 매물·단지·분양) 과 역 둘레 평균 매물가 (station-prices)."""
from collections.abc import Callable

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import box_around
from jibsa.core.listing import (
    AmountSet,
    Result,
    js_round,
    js_to_fixed,
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import DabangOneTwoFiltersModel
from jibsa.providers.dabang.api.request.nearby import (
    DabangCarShareTarget,
    DabangMarkersCategoryV5RequestParameterModel,
    DabangNearTarget,
    DabangNearV5RequestParameterModel,
    DabangPetPlacesV5RequestParameterModel,
    DabangPublicDataCarShareZoneV5RequestParameterModel,
    DabangTransitNearV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.nearby import (
    DabangCarShareZoneModel,
    DabangNearGroupModel,
    DabangNearPoiModel,
    DabangPetPlaceModel,
)
from jibsa.providers.dabang.service.common import (
    BUILDING_LABEL_BY_CATEGORY,
    COMPLEX_ID_PATTERN,
    DabangPlace,
    bbox_of,
    complex_url,
    is_missing_id,
    listing_url,
    manwon_from_text,
    sale_url,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


# 가까운 시설 종류 코드 → 이름. 웹 주변 지도의 이름표 그대로다 (distance-km-m 청크, 2026-11-13: BS 버스, PO3 관공서,
# POLICE 치안 …). 지하철역(SW8)은 transit/near 의 역 목록으로, CCTV 는 이름이 없어 쓰지 않는다. 다방은 대상마다 다른 종류를
# 준다 (2026-10-26 실측: 매물은 BS·SW8·CS2·CE7·BK9·PO3, 단지는 BS·SW8·MT1·CS2·BK9·PM9, 둘 다 POLICE). 분양은 단지와 같은
# 종류를 준다 (2026-11-13 실측: 호반써밋 풍무Ⅱ BS·SW8·MT1·CS2·BK9·PM9·POLICE·CCTV)
NEAR_LABELS: dict[str, str] = {
    'BS': '버스',
    'MT1': '마트',
    'CS2': '편의점',
    'CE7': '카페',
    'BK9': '은행',
    'PM9': '약국',
    'PO3': '관공서',
    'POLICE': '치안',
}
SCHOOL_LABELS: dict[str, str] = {'NS': '어린이집', 'KS': '유치원', 'ES': '초등학교', 'MS': '중학교', 'HS': '고등학교'}
# 대상 → 결과의 target 이름과 없는 ID 안내에 쓰는 이름
TARGET_LABELS: dict[DabangNearTarget, str] = {'room': '매물', 'complex': '단지', 'sale': '분양'}
# 대상 → 매물·단지·분양 페이지 주소
URL_BY_TARGET: dict[DabangNearTarget, Callable[[str], str]] = {'room': listing_url, 'complex': complex_url, 'sale': sale_url}
# 종류마다 내는 가까운 시설 수. 웹은 받은 시설 전부(편의 종류는 15곳)를 지도에 찍는다
NEAR_PLACES_PER_TYPE: int = 3
ROOM_LABELS: dict[str, str] = {'ONE_ROOM': '원룸', 'TWO_ROOM': '투룸'}
# --with 로 더 받는 생활 정보와 받는 대상. 반려동물 장소(웹 '펫세권')는 웹이 단지 화면에서만 부르고 매물·분양 ID 로는 빈
# 목록이다. 카셰어링 존(웹 'Car세권')은 매물·단지만 되고 분양은 403 이다 (dong-info 청크 2026-11-13, 2026-11-14 실측)
NearbyExtra = Literal['반려동물', '카셰어링']
NEARBY_EXTRAS: tuple[NearbyExtra, ...] = ('반려동물', '카셰어링')
EXTRA_TARGETS: dict[NearbyExtra, tuple[DabangNearTarget, ...]] = {'반려동물': ('complex',), '카셰어링': ('room', 'complex')}
# 카셰어링 업체 코드 → 웹 이름표
CAR_SHARE_LABELS: dict[str, str] = {'SOCAR': '쏘카존', 'GREENCAR': '그린존'}
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


class DabangNearPlace(BaseModel):
    """가까운 시설 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='이름 (치안은 다방이 이름을 주지 않아 null)')
    ] = None
    distance_m: Annotated[
        int | float | None,
        Field(description='거리 (m, 직선, 다방 값). 1m 미만은 소수 한 자리 (웹과 같다)')
    ] = None


class DabangNearPlaces(BaseModel):
    """시설 종류 하나와 가까운 순 시설."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str,
        Field(description='시설 종류 (다방 화면 이름표)')
    ]
    places: Annotated[
        list[DabangNearPlace],
        Field(description=f'가까운 순 시설 {NEAR_PLACES_PER_TYPE}곳까지 (다방이 덜 주면 있는 만큼)')
    ]


class DabangPetPlace(BaseModel):
    """반려동물 장소 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='이름')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m, 직선, 다방 값)')
    ] = None
    categories: Annotated[
        list[str],
        Field(description="분류 (웹 '#' 꼬리표, '반려동물'·'동물병원')")
    ]


class DabangPetPlaces(BaseModel):
    """반려동물 장소 종류 하나와 가까운 순 장소."""

    model_config = ConfigDict(
        extra='forbid',
    )

    type: Annotated[
        str | None,
        Field(description="종류 (웹 탭 이름: '동물병원', '미용실', '카페', '호텔')")
    ] = None
    places: Annotated[
        list[DabangPetPlace],
        Field(description=f'가까운 순 {NEAR_PLACES_PER_TYPE}곳까지')
    ]


class DabangPetPlacesResult(BaseModel):
    """단지 둘레 반려동물 장소 (웹 '펫세권')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    radius_m: Annotated[
        int | None,
        Field(description='다방이 찾은 반경 (m)')
    ] = None
    types: Annotated[
        list[DabangPetPlaces],
        Field(description='종류마다 가까운 순 장소. 다방이 찾지 못한 종류는 없다')
    ]


class DabangCarShareZone(BaseModel):
    """카셰어링 존 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    service: Annotated[
        str | None,
        Field(description="업체 (웹 이름표 '쏘카존'·'그린존')")
    ] = None
    name: Annotated[
        str | None,
        Field(description='존 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m, 직선, 다방 값)')
    ] = None


class DabangCarShareResult(BaseModel):
    """매물·단지 둘레 카셰어링 존 (웹 'Car세권')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    radius_m: Annotated[
        int | None,
        Field(description='다방이 찾은 반경 (m)')
    ] = None
    zones: Annotated[
        list[DabangCarShareZone],
        Field(description=f'가까운 순 {NEAR_PLACES_PER_TYPE}곳까지')
    ]


class DabangNearby(Result):
    """매물·단지·분양 둘레 교통과 가까운 시설."""

    model_config = ConfigDict(
        extra='forbid',
    )

    target: Annotated[
        str,
        Field(description="'매물', '단지' 또는 '분양'")
    ]
    listing_id: Annotated[
        str | None,
        Field(description="매물 ID. target 이 '매물'일 때만 있다")
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description="단지 ID. target 이 '단지'일 때만 있다")
    ] = None
    presale_id: Annotated[
        str | None,
        Field(description="분양 ID. target 이 '분양'일 때만 있다")
    ] = None
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
        list[DabangNearPlaces],
        Field(description=(
            f'종류마다 가까운 순 시설 {NEAR_PLACES_PER_TYPE}곳까지 (매물: 버스·편의점·카페·은행·관공서·치안, '
            '단지·분양: 버스·마트·편의점·은행·약국·치안). 다방이 찾지 못한 종류는 없다'
        ))
    ]
    schools: Annotated[
        list[DabangNearPlaces],
        Field(description=(
            f'종류마다 가까운 순 어린이집·유치원·초·중·고등학교 {NEAR_PLACES_PER_TYPE}곳까지 (배정 학교가 아니다). '
            '다방 범위 안에 없는 종류는 없다'
        ))
    ]
    pet_places: Annotated[
        DabangPetPlacesResult | None,
        Field(description='단지 둘레 반려동물 장소 (--with 반려동물 일 때만)')
    ] = None
    car_share: Annotated[
        DabangCarShareResult | None,
        Field(description='둘레 카셰어링 존 (--with 카셰어링 일 때만)')
    ] = None
    url: Annotated[
        str,
        Field(description='매물·단지·분양 페이지 URL')
    ]
    extras: Annotated[
        list[str],
        Field(exclude=True, description='--with 로 고른 생활 정보')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unrequested(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 대상 ID 는 target 에 맞는 키 하나만 낸다
        for key in ('listing_id', 'complex_id', 'presale_id'):
            if data[key] is None:
                del data[key]
        if '반려동물' not in self.extras:
            data.pop('pet_places', None)
        if '카셰어링' not in self.extras:
            data.pop('car_share', None)
        return data


def _by_distance(item: DabangPetPlaceModel | DabangCarShareZoneModel | DabangNearPoiModel) -> float:
    return item.distance if item.distance is not None else float('inf')


def _pet_places(client: DabangClient, complex_id: str) -> DabangPetPlacesResult | None:
    """단지 둘레 반려동물 장소 (요청 1회). 종류마다 다방 거리 값으로 가까운 순 `NEAR_PLACES_PER_TYPE` 곳. 전화는 내보내지 않는다."""
    result = client.run_request_pet_places_v5(DabangPetPlacesV5RequestParameterModel(complex_id=complex_id)).result
    # 종류 목록을 null 로 주면 result 가 없을 때처럼 모름(null)이다
    if result is None or result.pet_place_list is None:
        return None
    return DabangPetPlacesResult(radius_m=result.radius, types=[
        DabangPetPlaces(type=group.name, places=[
            DabangPetPlace(
                name=place.name, road_address=normalize_address(place.road_address),
                distance_m=place.distance, categories=place.category_list or [],
            )
            for place in sorted(group.place_list, key=_by_distance)[:NEAR_PLACES_PER_TYPE]
        ])
        for group in result.pet_place_list if group.place_list
    ])


def _car_share(client: DabangClient, target: DabangCarShareTarget, target_id: str) -> DabangCarShareResult | None:
    """매물·단지 둘레 카셰어링 존 (요청 1회). 다방 거리 값으로 가까운 순 `NEAR_PLACES_PER_TYPE` 곳 (웹도 3곳씩 '더보기')."""
    result = client.run_request_public_data_car_share_zone_v5(
        DabangPublicDataCarShareZoneV5RequestParameterModel(target=target, target_id=target_id)
    ).result
    # 존 목록을 null 로 주면 result 가 없을 때처럼 모름(null)이다
    if result is None or result.zone_list is None:
        return None
    return DabangCarShareResult(radius_m=result.radius, zones=[
        DabangCarShareZone(
            service=CAR_SHARE_LABELS.get(zone.zone_type or '', zone.zone_type), name=zone.zone_name,
            address=normalize_address(zone.address), distance_m=zone.distance,
        )
        for zone in sorted(result.zone_list, key=_by_distance)[:NEAR_PLACES_PER_TYPE]
    ])


def _nearest(groups: list[DabangNearGroupModel], labels: dict[str, str]) -> list[DabangNearPlaces]:
    """종류마다 다방 거리 값으로 가까운 순 `NEAR_PLACES_PER_TYPE` 곳. 편의 종류는 거리순으로 오지만 어린이집은 섞여 와
    (2026-11-13 실측: 역삼동 매물 어린이집 6곳) 거리로 다시 세운다. 거리를 모르는 시설은 뒤로 보낸다."""
    result = []
    for group in groups:
        label = labels.get(group.query)
        if label is None or not group.pois:
            continue
        # 리뷰 오탐 (2026-11-14, 근거 고침 2026-11-20): 시설 거리는 소수로 온다 (실측 88.58277413). 정밀한 거리로 세운 뒤 내보낼
        # 때만 웹 `d` 식(아래 `distance_m`)으로 반올림하려고 역·반려동물·카셰어링처럼 `Meters` 로 받지 않는다. 먼저 반올림하면
        # 같은 m 의 두 곳이 서버 순서를 따른다
        pois = sorted(group.pois, key=_by_distance)
        # distance_m 는 웹이 시설 거리를 보여 주는 식과 같게 맞춘다 (distance-km-m 청크 `d`: `e<1 ? parseFloat(e.toFixed(1)) : Math.round(e)`).
        # 1m 미만은 소수 한 자리, 그 위는 .5 를 올려 정수로 만든다. Python `round` 는 .5 를 짝수로 보내 웹과 1 씩 달라지고
        # `f'{x:.1f}'`·`Decimal(str(x))` 도 JS `toFixed(1)` 과 어긋나는 값이 있어(0.25 → 웹 0.3, 0.15 → 웹 0.1) 소수 한 자리는 공용
        # `js_to_fixed` 로 맞춘다 (2026-11-20 리뷰: 예전 `Decimal(str(x))` 는 0.15 를 0.2 로 냈다)
        result.append(DabangNearPlaces(type=label, places=[
            DabangNearPlace(
                name=poi.name,
                distance_m=(
                    None if poi.distance is None
                    else float(js_to_fixed(poi.distance, 1)) if poi.distance < 1
                    else js_round(poi.distance)
                ),
            )
            for poi in pois[:NEAR_PLACES_PER_TYPE]
        ]))
    return result


def get_nearby(
    client: DabangClient, target_id: str, *, sale: bool = False, extras: list[NearbyExtra] | None = None,
) -> DabangNearby:
    """매물(24자리 ID)·단지(28자리 ID)·분양(`sale`, 28자리 ID) 둘레의 지하철역·버스 노선과 종류마다 가까운 시설 3곳
    (요청 2회). 시설 좌표·전화는 내보내지 않는다.

    Args:
        sale: `target_id` 가 분양 ID 인지. 분양 ID 와 단지 ID 는 둘 다 28자리라 길이로 가르지 못해 부르는 쪽이 알린다.
        extras: 더 받을 생활 정보 (반려동물은 단지만, 카셰어링은 매물·단지만). 하나마다 요청 1회. Defaults to None.

    Raises:
        JibsaError: 없는 ID 일 때 (NOT_FOUND), 그 대상에 없는 생활 정보를 고를 때 (INVALID_ARGUMENT).
    """
    target: DabangNearTarget = 'sale' if sale else 'complex' if COMPLEX_ID_PATTERN.fullmatch(target_id) else 'room'
    chosen = extras or []
    for extra in chosen:
        # 대상에 없는 생활 정보는 요청 전에 막는다. 다방은 빈 목록(반려동물)이나 403(분양 카셰어링)을 줘 없다로 잘못 읽힌다
        # 리뷰 오탐 (2026-11-14): extra 는 NearbyExtra Literal 의 고정 라벨('반려동물'·'카셰어링')이라 끝 글자에 늘 받침이 있어 조사를
        # 그대로 쓴다 (code-style 의 '끝 글자가 늘 정해진 값')
        if target not in EXTRA_TARGETS[extra]:
            where = '·'.join(TARGET_LABELS[item] for item in EXTRA_TARGETS[extra])
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'--with {extra}은 {where}에만 있습니다 ({TARGET_LABELS[target]}에는 다방이 주지 않습니다)',
                hint=f'{where} ID 로 다시 주거나 --with 에서 {extra}을 빼세요',
            )
    # 없는 ID 는 ID 가 경로에 들어가는 시설 요청으로 가린다 (400). 교통 요청은 ID 가 쿼리로 가서 없는 ID 에도 빈 결과를 주므로
    # (2026-10-27 실측) 그 에러는 다방 주소가 바뀐 것이다 (`is_missing_id`)
    try:
        near = client.run_request_near_v5(DabangNearV5RequestParameterModel(target=target, target_id=target_id)).result
    except HTTPStatusError as exc:
        if is_missing_id(exc):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방에서 찾지 못한 {TARGET_LABELS[target]}입니다: {target_id}',
                hint=(
                    '분양 ID 는 jibsa dabang search sales 결과의 presale_id 를 그대로 주세요 (단지 ID 는 --sale 없이 줍니다)'
                    if sale else 'ID 를 같은 소스(dabang) 결과에서 그대로 옮겼는지 확인하세요'
                    + (' (분양 ID 는 단지 ID 와 자릿수가 같습니다. search sales 의 presale_id 면 --sale <ID> 로 주세요)' if target == 'complex' else '')
                ),
            ) from None
        raise
    transit = client.run_request_transit_near_v5(DabangTransitNearV5RequestParameterModel(target=target, target_id=target_id)).result
    subway = transit.subway if transit else None
    route = transit.route if transit else None
    return DabangNearby(
        target=TARGET_LABELS[target],
        listing_id=target_id if target == 'room' else None,
        complex_id=target_id if target == 'complex' else None,
        presale_id=target_id if target == 'sale' else None,
        stations=[
            DabangNearbyStation(
                name=station.name,
                lines=[line.name for line in station.line_list if line.name],
                distance_m=station.distance,
            )
            for station in (subway.list_ if subway else [])
        ],
        station_radius_m=subway.radius if subway else None,
        bus_route_count=len(route.list_) if route else None,
        bus_radius_m=route.radius if route else None,
        nearest=_nearest((near.convenience + near.safety) if near else [], NEAR_LABELS),
        schools=_nearest(near.education if near else [], SCHOOL_LABELS),
        pet_places=_pet_places(client, target_id) if '반려동물' in chosen else None,
        car_share=_car_share(client, 'room' if target == 'room' else 'complex', target_id) if '카셰어링' in chosen else None,
        url=URL_BY_TARGET[target](target_id),
        extras=chosen,
    )


class DabangStationPrice(BaseModel):
    """역 둘레 평균 매물가 한 칸 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    property_type: Annotated[
        str,
        Field(description='매물 유형 (빌라, 오피스텔, 아파트)')
    ]
    room_type: Annotated[
        str,
        Field(description='방 개수 (원룸, 투룸)')
    ]
    asking_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 평균 매물가 (만원). 키는 'jeonse'(평균 전세금 deposit_manwon)·'wolse'(평균 보증금 deposit_manwon, "
            "평균 월세 rent_manwon) 늘 두 개다. 다방이 그 거래 평균을 주지 않으면(웹은 '-') 그 거래가 null(모름)이다. 월세는 보증금·월세 중 하나만 모르면 그 칸만 null 이다. "
            '다방이 매물 수를 주지 않아 그 거래 매물이 없는 것인지는 가를 수 없다'
        ))
    ]


class DabangStationPrices(Result):
    """역 둘레 평균 매물가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station_name: Annotated[
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
        monthly_deposit = manwon_from_text(deposit) if rent else None
        monthly_rent = manwon_from_text(rent) if rent else None
        prices.append(DabangStationPrice(
            property_type=BUILDING_LABEL_BY_CATEGORY.get(item.building_category or '', item.building_category or ''),
            room_type=ROOM_LABELS.get(item.room_type or '', item.room_type or ''),
            asking_averages={
                'jeonse': None if (lease := manwon_from_text(item.lease)) is None else AmountSet(deposit_manwon=lease),
                'wolse': None if monthly_deposit is None and monthly_rent is None else AmountSet(
                    deposit_manwon=monthly_deposit,
                    rent_manwon=monthly_rent,
                ),
            },
        ))
    return DabangStationPrices(
        station_name=station.name,
        radius_m=station.radius,
        basis="다방 '평균 매물가': 역 반경 안에 지금 올라온 원룸·투룸 목록 매물(방 1~2개)의 평균 (실거래가 아님)",
        prices=prices,
    )
