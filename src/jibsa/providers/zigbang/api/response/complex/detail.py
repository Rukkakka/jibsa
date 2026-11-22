"""응답 모델: 아파트 단지·오피스텔 건물 정보와 단지 매물 목록·학군 (complex, search listings --complex)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangBaseResponseModel,
    ZigbangItemCatalogModel,
    ZigbangItemPinModel,
    ZigbangItemSectionModel,
)
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangDanjiRoomTypeModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/officetels/{buildingId}
# ---------------------------------------------------------------------------

class ZigbangOfficetelBuildingModel(ZigbangBaseResponseModel):
    """오피스텔 건물 정보."""

    id: Annotated[
        int,
        Field(description='건물 ID')
    ]
    name: Annotated[
        str,
        Field(description='건물 이름')
    ]
    address: Annotated[
        ZigbangAddressOriginModel | None,
        Field(description='행정 주소 (지번 없음)')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 유무')
    ] = None
    established: Annotated[
        str | None,
        Field(description='준공 연월 (YYYYMM)')
    ] = None
    household: Annotated[
        str | None,
        Field(description='세대수 (문자열)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층수 (문자열)')
    ] = None
    item_count: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수', alias='itemCount')
    ] = None


class ZigbangItemsOfficetelsBuildingV1ResponseModel(ZigbangBaseResponseModel):
    """오피스텔 건물 하나의 매물 핀과 건물 정보. 핀 모양은 지도 목록과 같다."""

    items: Annotated[
        list[ZigbangItemPinModel],
        Field(description='건물 안 매물 핀. 건물 하나라 좌표가 모두 같다. 순서는 sections 를 이은 순서와 다르다')
    ] = []
    sections: Annotated[
        list[ZigbangItemSectionModel],
        Field(description=(
            '노출 구역별 매물 ID. 웹 건물 화면은 이 순서로 이어 매물을 세운다 (2026-11-15 번들 `loadItemsV2`: '
            '`sections.flatMap(ids)`)'
        ))
    ] = []
    building: Annotated[
        ZigbangOfficetelBuildingModel,
        Field(description='건물 정보')
    ]


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/schools
# ---------------------------------------------------------------------------

class ZigbangDanjiSchoolModel(ZigbangBaseResponseModel):
    """단지 주변 학교 하나."""

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    distance: Annotated[
        str | None,
        Field(description="단지에서 거리 문구 (예: '180m', '1.1km')")
    ] = None


class ZigbangDanjiSchoolLevelModel(ZigbangBaseResponseModel):
    """학교급(초·중·고) 하나의 학구·학교군과 학교."""

    zone_name: Annotated[
        str | None,
        Field(description='통학구역(초등) 또는 학교군(중·고) 이름', alias='zoneName')
    ] = None
    schools: Annotated[
        list[ZigbangDanjiSchoolModel],
        Field(description='통학구역·학교군 안의 학교 (가까운 순)', alias='list')
    ] = []


class ZigbangDanjisSchoolsResponseModel(ZigbangBaseResponseModel):
    """아파트 단지의 학군. 통학구역·학교군 밖 주변 학교(etcList)는 읽지 않는다."""

    elementary: Annotated[
        ZigbangDanjiSchoolLevelModel | None,
        Field(description='초등학교 (통학구역)')
    ] = None
    middle: Annotated[
        ZigbangDanjiSchoolLevelModel | None,
        Field(description='중학교 (학교군)')
    ] = None
    high: Annotated[
        ZigbangDanjiSchoolLevelModel | None,
        Field(description='고등학교 (학교군)')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/item-catalogs
# ---------------------------------------------------------------------------

class ZigbangDanjisItemCatalogsResponseModel(ZigbangBaseResponseModel):
    """단지 하나의 아파트 매물 카탈로그 응답. 카탈로그 모양은 지역 목록과 같다."""

    total_count: Annotated[
        int,
        Field(description='조건에 맞는 카탈로그 수 (페이지 무관)', alias='totalCount')
    ] = 0
    count_by_tran_type: Annotated[
        dict[str, int],
        Field(description='거래 유형(trade·charter·rental)별 카탈로그 수. 거래 유형 조건을 반영한다', alias='itemCountPerTranType')
    ] = {}
    room_types: Annotated[
        list[ZigbangDanjiRoomTypeModel],
        Field(description='단지의 평형 목록', alias='danjiRoomTypes')
    ] = []
    catalogs: Annotated[
        list[ZigbangItemCatalogModel],
        Field(description='이번 페이지의 카탈로그', alias='list')
    ] = []
