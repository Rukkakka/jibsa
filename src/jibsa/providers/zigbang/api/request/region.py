"""요청 모델: 지역·역·좌표 해석과 동 경계 (search locations, 모든 검색의 지역 해석)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


ZigbangSearchServiceType = Literal['원룸', '오피스텔', '아파트', '빌라']


class ZigbangSearchV2RequestParameterModel(RequestModel):
    """`GET /v2/search` 쿼리. 지역·역·단지명을 좌표와 법정동코드로 바꾼다."""

    q: Annotated[
        str,
        Field(min_length=1, description='검색어 (예: 역삼동, 강남역)')
    ]
    service_type: Annotated[
        ZigbangSearchServiceType,
        Field(description='검색 대상 서비스. 아파트면 아파트 단지, 오피스텔이면 오피스텔 건물도 결과에 나온다')
    ] = Field(default='원룸', alias='serviceType')
    lease_yn: Annotated[
        Literal['Y', 'N'],
        Field(description='단기임대 검색 여부')
    ] = Field(default='N', alias='leaseYn')


class ZigbangLocalPolygonV2RequestParameterModel(RequestModel):
    """`GET /v2/local/polygon` 쿼리. geohash 칸 중심이 속한 행정구역과 그 경계."""

    geohash: Annotated[
        str,
        Field(
            pattern=r'^[0-9bcdefghjkmnpqrstuvwxyz]{5,9}$',
            description='찾을 위치. 정밀도 7(약 150m)이면 작은 동도 대개 맞게 잡힌다 (6 이하는 옆 동이 잡히기도 하고, 7 에서 옆 동이면 8 로 다시 묻는다)'
        )
    ]
    level: Annotated[
        Literal['local1', 'local2', 'local3'],
        Field(description='행정 단계 (local1 시·도, local2 시·군·구, local3 읍·면·동)')
    ] = 'local3'
    polygon: Annotated[
        bool,
        Field(description='경계 좌표(geojson)를 받을지. False 면 geojson 이 null 이다')
    ] = True
