"""응답 모델: 아파트 단지 학군 (complex)."""

from pydantic import Field

from jibsa.providers.zigbang.api.models.response.common import (
    ZigbangBaseResponseModel,
)

from typing import Annotated


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
