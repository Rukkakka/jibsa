"""매물·단지·분양 둘레의 지하철역·버스 노선과 주변 시설 (nearby)."""
from collections.abc import Callable

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    js_round,
    js_to_fixed,
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.nearby.places import (
    DabangCarShareTarget,
    DabangNearTarget,
    DabangNearV5RequestParameterModel,
    DabangPetPlacesV5RequestParameterModel,
    DabangPublicDataCarShareZoneV5RequestParameterModel,
    DabangTransitNearV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.nearby.places import (
    DabangCarShareZoneModel,
    DabangNearGroupModel,
    DabangNearPoiModel,
    DabangPetPlaceModel,
)
from jibsa.providers.dabang.service.common.functions import (
    COMPLEX_ID_PATTERN,
    complex_url,
    is_missing_id,
    listing_url,
    sale_url,
)
from jibsa.providers.dabang.service.nearby.models import (
    NEAR_PLACES_PER_TYPE,
    DabangCarShareResult,
    DabangCarShareZone,
    DabangNearby,
    DabangNearbyStation,
    DabangNearPlace,
    DabangNearPlaces,
    DabangPetPlace,
    DabangPetPlaces,
    DabangPetPlacesResult,
)

from typing import Literal


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

# --with 로 더 받는 생활 정보와 받는 대상. 반려동물 장소(웹 '펫세권')는 웹이 단지 화면에서만 부르고 매물·분양 ID 로는 빈
# 목록이다. 카셰어링 존(웹 'Car세권')은 매물·단지만 되고 분양은 403 이다 (dong-info 청크 2026-11-13, 2026-11-14 실측)
NearbyExtra = Literal['반려동물', '카셰어링']
NEARBY_EXTRAS: tuple[NearbyExtra, ...] = ('반려동물', '카셰어링')
EXTRA_TARGETS: dict[NearbyExtra, tuple[DabangNearTarget, ...]] = {'반려동물': ('complex',), '카셰어링': ('room', 'complex')}
# 카셰어링 업체 코드 → 웹 이름표
CAR_SHARE_LABELS: dict[str, str] = {'SOCAR': '쏘카존', 'GREENCAR': '그린존'}


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
