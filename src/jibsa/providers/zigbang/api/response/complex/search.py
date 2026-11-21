"""응답 모델: 역·학교·동·구 주변 아파트 단지 (search complexes)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/subways/{subwayId}
# ---------------------------------------------------------------------------

class ZigbangSubwayAptModel(ResponseModel):
    """역 주변 아파트 단지 하나. 단지 좌표(`lat`·`lng`)도 오지만 읽지 않는다."""

    id: Annotated[
        int,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    old_address: Annotated[
        str | None,
        Field(description="지번 주소 (예: '서울시 서초구 서초동 1319-13', 시·도를 줄여 준다)", alias='구주소')
    ] = None
    household: Annotated[
        str | None,
        Field(description="세대수 문구 (예: '38세대')")
    ] = None
    distance_num: Annotated[
        int | None,
        Field(description='역에서의 거리 (m)', alias='distanceNum')
    ] = None


class ZigbangSubwaysResponseModel(ResponseModel):
    """역 정보와 역에서 1.5km 안 아파트 단지 (거리순, 2026-11-15 실측: 강남역 112곳)."""

    id: Annotated[
        int,
        Field(description='역 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='역 이름')
    ] = None
    apt_list: Annotated[
        list[ZigbangSubwayAptModel],
        Field(description='역 주변 단지 (가까운 순)', alias='aptList')
    ] = []


# ---------------------------------------------------------------------------
# GET /apt/danjis/ids
# ---------------------------------------------------------------------------

class ZigbangDanjisIdsResponseModel(ResponseModel):
    """주변 단지 ID 를 요청한 순서(조회수 순)로."""

    count: Annotated[
        int | None,
        Field(description='주변 단지 전체 수 (limit 적용 전)')
    ] = None
    ids: Annotated[
        list[int],
        Field(description='단지 ID (요청한 순서)')
    ] = []
