"""응답 모델: 매물·단지·분양 둘레의 지하철역·버스 노선과 주변 시설 (nearby)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
    Meters,
)

from typing import Annotated


class DabangNearLineModel(DabangBaseResponseModel):
    """역 노선."""

    name: Annotated[
        str | None,
        Field(description="노선 ('2호선')")
    ] = None


class DabangNearStationModel(DabangBaseResponseModel):
    """가까운 지하철역 하나."""

    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    distance: Annotated[
        Meters,
        Field(description='거리 (m). 정수로 온다 (2026-11-20 실측: 은마 transit/near 역·버스 정류장 모두 int, 소수는 주변 시설 near 의 pois 만). 웹(distance-km-m 청크 x)도 반올림 없이 그대로 보인다. 소수로 와도 단지 정보 전체가 깨지지 않게 Meters 로 받는다')
    ] = None
    line_list: Annotated[
        list[DabangNearLineModel],
        Field(description='노선', alias='lineList')
    ] = []


class DabangNearStationsModel(DabangBaseResponseModel):
    """반경 안 지하철역."""

    list_: Annotated[
        list[DabangNearStationModel],
        Field(description='가까운 순 역', alias='list')
    ] = []
    radius: Annotated[
        int | None,
        Field(description='반경 (m, 1000)')
    ] = None


class DabangNearRoutesModel(DabangBaseResponseModel):
    """반경 안 버스 노선 (노선마다 첫·막차, 배차가 오지만 jibsa 는 수만 쓴다)."""

    list_: Annotated[
        list[dict[str, object]],
        Field(description='버스 노선', alias='list')
    ] = []
    radius: Annotated[
        int | None,
        Field(description='반경 (m, 500)')
    ] = None


class DabangTransitNearResultModel(DabangBaseResponseModel):
    """매물·단지 둘레 교통 `result`."""

    subway: Annotated[
        DabangNearStationsModel | None,
        Field(description='지하철역')
    ] = None
    route: Annotated[
        DabangNearRoutesModel | None,
        Field(description='버스 노선')
    ] = None


class DabangTransitNearV5ResponseModel(DabangV5ResponseModel[DabangTransitNearResultModel]):
    """`GET /api/v5/transit/near/{target}` 응답."""


class DabangNearPoiModel(DabangBaseResponseModel):
    """가까운 시설 하나 (좌표도 오지만 모델에 두지 않는다)."""

    name: Annotated[
        str | None,
        Field(description='이름 (CCTV·치안은 없다)')
    ] = None
    distance: Annotated[
        float | None,
        Field(description='거리 (m)')
    ] = None


class DabangNearGroupModel(DabangBaseResponseModel):
    """시설 종류 하나. `query` 는 카카오 장소 분류와 같은 코드(MT1·CS2·CE7·BK9·PM9·PO3·SW8)와 다방 코드(BS·POLICE·CCTV·NS·KS·
    ES·MS·HS)다. 웹 이름표는 distance-km-m 청크에 있다 (2026-11-13: BS 버스, SW8 지하철역, MT1 마트, CS2 편의점, CE7 카페,
    BK9 은행, PM9 약국, PO3 관공서, POLICE 치안, CCTV, NS 어린이집, KS 유치원, ES 초등학교, MS 중학교, HS 고등학교).
    치안은 이름 대신 `gubun`('지구대'), CCTV 는 `usage`('생활방범')가 온다.
    """

    query: Annotated[
        str,
        Field(description='시설 종류 코드')
    ]
    pois: Annotated[
        list[DabangNearPoiModel],
        Field(description='시설. 편의 종류는 거리순 15곳까지, 어린이집·CCTV 는 순서가 섞여 온다 (2026-11-13 실측)')
    ] = []


class DabangNearResultModel(DabangBaseResponseModel):
    """가까운 시설 `result`."""

    convenience: Annotated[
        list[DabangNearGroupModel],
        Field(description='편의·교통')
    ] = []
    safety: Annotated[
        list[DabangNearGroupModel],
        Field(description='안전')
    ] = []
    education: Annotated[
        list[DabangNearGroupModel],
        Field(description='교육')
    ] = []


class DabangNearV5ResponseModel(DabangV5ResponseModel[DabangNearResultModel]):
    """`GET /api/v5/{target}/{target_id}/near` 응답."""


class DabangPetPlaceModel(DabangBaseResponseModel):
    """반려동물 장소 하나. 전화(`phone`)도 오지만 모델에 두지 않는다."""

    name: Annotated[
        str | None,
        Field(description='이름')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소', alias='roadAddress')
    ] = None
    distance: Annotated[
        Meters,
        Field(description='거리 (m)')
    ] = None
    category_list: Annotated[
        list[str] | None,
        Field(description="분류 ('가정,생활', '반려동물', '동물병원', 웹은 '#' 꼬리표로 보여 준다). null 이면 꼬리표 없음", alias='categoryList')
    ] = None


class DabangPetPlaceGroupModel(DabangBaseResponseModel):
    """반려동물 장소 종류 하나 (웹 '펫세권' 탭)."""

    query: Annotated[
        str | None,
        Field(description="종류 코드 ('HOSPITAL', 'SHOP', 'CAFE', 'HOTEL')")
    ] = None
    name: Annotated[
        str | None,
        Field(description="종류 이름 ('동물병원', '미용실', '카페', '호텔')")
    ] = None
    place_list: Annotated[
        list[DabangPetPlaceModel] | None,
        Field(description='가까운 순 장소 (10곳까지, 2026-11-14 실측). null 이면 장소 없음', alias='placeList')
    ] = None


class DabangPetPlacesResultModel(DabangBaseResponseModel):
    """반려동물 장소 `result`."""

    radius: Annotated[
        int | None,
        Field(description='반경 (m, 2000)')
    ] = None
    pet_place_list: Annotated[
        list[DabangPetPlaceGroupModel] | None,
        Field(description='종류별 장소. null 이면 모름', alias='petPlaceList')
    ] = None


class DabangPetPlacesV5ResponseModel(DabangV5ResponseModel[DabangPetPlacesResultModel]):
    """`GET /api/v5/pet-places` 응답."""


class DabangCarShareZoneModel(DabangBaseResponseModel):
    """카셰어링 존 하나."""

    zone_type: Annotated[
        str | None,
        Field(description="업체 ('SOCAR' 쏘카존, 'GREENCAR' 그린존)", alias='zoneType')
    ] = None
    zone_name: Annotated[
        str | None,
        Field(description='존 이름', alias='zoneName')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    distance: Annotated[
        Meters,
        Field(description='거리 (m)')
    ] = None


class DabangCarShareZoneResultModel(DabangBaseResponseModel):
    """카셰어링 존 `result`."""

    radius: Annotated[
        int | None,
        Field(description='반경 (m, 2000)')
    ] = None
    zone_list: Annotated[
        list[DabangCarShareZoneModel] | None,
        Field(description='가까운 순 존. null 이면 모름', alias='zoneList')
    ] = None


class DabangPublicDataCarShareZoneV5ResponseModel(DabangV5ResponseModel[DabangCarShareZoneResultModel]):
    """`GET /api/v5/public-data/{target}/car-share-zone` 응답."""
