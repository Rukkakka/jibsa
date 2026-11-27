"""주변·역 둘레 평균 매물가의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountSet,
    Result,
)
from jibsa.providers.dabang.service.nearby.constants import NEAR_PLACES_PER_TYPE

from typing import (
    Annotated,
    Any,
)


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
