from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangV5ResponseModel

from typing import Annotated


class DabangNearLineModel(ResponseModel):
    """역 노선."""

    name: Annotated[
        str | None,
        Field(description="노선 ('2호선')")
    ] = None


class DabangNearStationModel(ResponseModel):
    """가까운 지하철역 하나."""

    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    distance: Annotated[
        float | None,
        Field(description='거리 (m)')
    ] = None
    line_list: Annotated[
        list[DabangNearLineModel],
        Field(description='노선', alias='lineList')
    ] = []


class DabangNearStationsModel(ResponseModel):
    """반경 안 지하철역."""

    list_: Annotated[
        list[DabangNearStationModel],
        Field(description='가까운 순 역', alias='list')
    ] = []
    radius: Annotated[
        int | None,
        Field(description='반경 (m, 1000)')
    ] = None


class DabangNearRoutesModel(ResponseModel):
    """반경 안 버스 노선 (노선마다 첫·막차, 배차가 오지만 jibsa 는 수만 쓴다)."""

    list_: Annotated[
        list[dict[str, object]],
        Field(description='버스 노선', alias='list')
    ] = []
    radius: Annotated[
        int | None,
        Field(description='반경 (m, 500)')
    ] = None


class DabangTransitNearResultModel(ResponseModel):
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


class DabangNearPoiModel(ResponseModel):
    """가까운 시설 하나 (좌표도 오지만 모델에 두지 않는다)."""

    name: Annotated[
        str | None,
        Field(description='이름 (CCTV·경찰은 없다)')
    ] = None
    distance: Annotated[
        float | None,
        Field(description='거리 (m)')
    ] = None


class DabangNearGroupModel(ResponseModel):
    """시설 종류 하나. `query` 는 카카오 장소 분류와 같은 코드다 (CS2 편의점, CE7 카페, BK9 은행, PO3 공공기관, SW8 지하철역)
    와 다방 코드(BS 버스정류장, POLICE, CCTV, NS 어린이집, KS 유치원, ES 초등학교, MS 중학교, HS 고등학교). 2026-10-25 실측.
    """

    query: Annotated[
        str,
        Field(description='시설 종류 코드')
    ]
    pois: Annotated[
        list[DabangNearPoiModel],
        Field(description='가까운 순 시설')
    ] = []


class DabangNearResultModel(ResponseModel):
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


class DabangAveragePriceModel(ResponseModel):
    """역(또는 동) 둘레 평균 매물가 한 칸. 웹은 '평균 매물가' 로 보여 준다 (지금 올라온 매물 가격의 평균, map 청크).

    Args:
        building_category: HOUSE_VILLA·OFFICETEL·APT.
        room_type: ONE_ROOM·TWO_ROOM.
        lease: 전세 평균 ('2억1333', 만원 글자). 없으면 null.
        monthly_rent: 월세 평균 ('7937/65' 보증금/월세). 없으면 null.
    """

    building_category: Annotated[
        str | None,
        Field(description='건물 유형', alias='buildingCategory')
    ] = None
    room_type: Annotated[
        str | None,
        Field(description='방 개수', alias='roomType')
    ] = None
    lease: Annotated[
        str | None,
        Field(description='전세 평균 (만원 글자)')
    ] = None
    monthly_rent: Annotated[
        str | None,
        Field(description='월세 평균 (보증금/월세 만원 글자)', alias='monthlyRent')
    ] = None


class DabangMarkerStationModel(ResponseModel):
    """지도 집계의 역 표시 하나."""

    id: Annotated[
        int,
        Field(description='역 번호')
    ]
    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    radius: Annotated[
        int | None,
        Field(description='역 반경 (m)')
    ] = None
    average_price_list: Annotated[
        list[DabangAveragePriceModel] | None,
        Field(description='평균 매물가 (원룸·투룸 집계에만 온다)', alias='averagePriceList')
    ] = None


class DabangMarkersResultModel(ResponseModel):
    """지도 집계 `result` (동·칸·단지 표시도 오지만 jibsa 는 역 표시만 쓴다)."""

    subway_list: Annotated[
        list[DabangMarkerStationModel],
        Field(description='역 표시', alias='subwayList')
    ] = []


class DabangMarkersCategoryV5ResponseModel(DabangV5ResponseModel[DabangMarkersResultModel]):
    """`GET /api/v5/markers/category/{category}` 응답."""
