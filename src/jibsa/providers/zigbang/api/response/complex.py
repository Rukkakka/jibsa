"""응답 모델: 아파트 단지·오피스텔 건물 정보와 단지 매물 목록 (complex, search listings --complex)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.zigbang.api.response.common import (
    ZigbangAddressOriginModel,
    ZigbangItemPinModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /house/property/v1/items/officetels/{buildingId}
# ---------------------------------------------------------------------------

class ZigbangOfficetelBuildingModel(ResponseModel):
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
        Field(description='조건에 맞는 매물 수')
    ] = Field(default=None, alias='itemCount')


class ZigbangItemsOfficetelsBuildingV1ResponseModel(ResponseModel):
    """오피스텔 건물 하나의 매물 핀과 건물 정보. 핀 모양은 지도 목록과 같다."""

    items: Annotated[
        list[ZigbangItemPinModel],
        Field(description='건물 안 매물 핀. 건물 하나라 좌표가 모두 같다')
    ] = []
    building: Annotated[
        ZigbangOfficetelBuildingModel,
        Field(description='건물 정보')
    ]


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/schools
# ---------------------------------------------------------------------------

class ZigbangDanjiSchoolModel(ResponseModel):
    """단지 주변 학교 하나."""

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    distance: Annotated[
        str | None,
        Field(description="단지에서 거리 문구 (예: '180m', '1.1km')")
    ] = None


class ZigbangDanjiSchoolLevelModel(ResponseModel):
    """학교급(초·중·고) 하나의 학구·학교군과 학교."""

    zone_name: Annotated[
        str | None,
        Field(description='통학구역(초등) 또는 학교군(중·고) 이름')
    ] = Field(default=None, alias='zoneName')
    schools: Annotated[
        list[ZigbangDanjiSchoolModel],
        Field(description='통학구역·학교군 안의 학교 (가까운 순)')
    ] = Field(default=[], alias='list')


class ZigbangDanjisSchoolsResponseModel(ResponseModel):
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
