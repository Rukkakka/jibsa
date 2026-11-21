"""요청 모델: 원룸·빌라·오피스텔 매물 상세 (listing): 기존 상세, 건물 학군."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


class ZigbangItemsV3RequestParameterModel(RequestModel):
    """`GET /v3/items/{itemId}` 경로 + 쿼리."""

    item_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='매물 ID. 경로에 들어가며 쿼리로는 보내지 않는다')
    ]
    domain: Annotated[
        Literal['zigbang'],
        Field(description='서비스 도메인. 고정값')
    ] = 'zigbang'


class ZigbangBlsSchoolZonesV1RequestParameterModel(RequestModel):
    """`GET /house/property/v1/bls/{pnu}/school_zones` 경로. 원룸·빌라·오피스텔 건물(필지)의 학군."""

    pnu: Annotated[
        str,
        Field(pattern=r'^\d{19}$', exclude=True, description='필지 고유번호 (19자리, 매물 상세의 pnu). 경로에 들어간다')
    ]
