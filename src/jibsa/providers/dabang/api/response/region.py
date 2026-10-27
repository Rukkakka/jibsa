from pydantic import (
    Field,
    ValidationInfo,
    field_validator,
)

from jibsa.core.geo import MultiPolygon
from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import (
    DabangLocationModel,
    DabangV5ResponseModel,
)

from typing import (
    Annotated,
    Any,
)


class DabangLocRegionModel(ResponseModel):
    """장소 검색의 동 하나. 시·군·구는 오지 않는다 ('강남구' 를 찾으면 강남구의 동들이 온다, 2026-10-25 실측).

    Args:
        code: 법정동 코드 앞 8자리 (예: '11680101').
        gid: 다방 동 번호. 매물 목록의 `gid` 와 같다.
        name: 동 이름.
        full_name: 시·도부터 이은 이름.
        location: 동 중심 좌표.
    """

    code: Annotated[
        str,
        Field(description='법정동 코드 앞 8자리')
    ]
    gid: Annotated[
        int,
        Field(description='다방 동 번호')
    ]
    name: Annotated[
        str,
        Field(description='동 이름')
    ]
    full_name: Annotated[
        str | None,
        Field(description='전체 이름', alias='fullName')
    ] = None
    location: Annotated[
        DabangLocationModel | None,
        Field(description='중심 좌표')
    ] = None


class DabangLocLineModel(ResponseModel):
    """역의 노선 하나."""

    full_name: Annotated[
        str | None,
        Field(description="노선 이름 ('2호선')", alias='fullName')
    ] = None


class DabangLocSubwayModel(ResponseModel):
    """장소 검색의 역 하나.

    Args:
        id: 다방 역 번호 (강남역 20).
        name: 역 이름.
        radius: 다방이 역 검색에 쓰는 반경 (m, 강남역 750).
        line_list: 노선.
        location: 역 좌표.
    """

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
        Field(description='역 검색 반경 (m)')
    ] = None
    line_list: Annotated[
        list[DabangLocLineModel],
        Field(description='노선', alias='lineList')
    ] = []
    location: Annotated[
        DabangLocationModel | None,
        Field(description='역 좌표')
    ] = None


class DabangLocUnivModel(ResponseModel):
    """장소 검색의 대학 하나."""

    id: Annotated[
        int,
        Field(description='대학 번호')
    ]
    name: Annotated[
        str,
        Field(description='대학 이름')
    ]
    location: Annotated[
        DabangLocationModel | None,
        Field(description='대학 좌표')
    ] = None


class DabangLocComplexModel(ResponseModel):
    """장소 검색의 단지 하나 (아파트·오피스텔)."""

    id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    type: Annotated[
        str | None,
        Field(description="'APT' 또는 'OFFICETEL'")
    ] = None
    format_type: Annotated[
        str | None,
        Field(description="'아파트' 또는 '오피스텔'", alias='formatType')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None


class DabangLocSaleModel(ResponseModel):
    """장소 검색의 분양 단지 하나."""

    id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    name: Annotated[
        str,
        Field(description='분양 단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    format_state: Annotated[
        str | None,
        Field(description="분양 상태 ('입주예정')", alias='formatState')
    ] = None


class DabangLocSearchResultModel(ResponseModel):
    """장소 검색 `result`."""

    region_list: Annotated[
        list[DabangLocRegionModel],
        Field(description='동', alias='regionList')
    ] = []
    subway_list: Annotated[
        list[DabangLocSubwayModel],
        Field(description='역', alias='subwayList')
    ] = []
    univ_list: Annotated[
        list[DabangLocUnivModel],
        Field(description='대학', alias='univList')
    ] = []
    complex_list: Annotated[
        list[DabangLocComplexModel],
        Field(description='단지', alias='complexList')
    ] = []
    sale_in_lots_list: Annotated[
        list[DabangLocSaleModel],
        Field(description='분양 단지', alias='saleInLotsList')
    ] = []


class DabangLocSearchV5ResponseModel(DabangV5ResponseModel[DabangLocSearchResultModel]):
    """`GET /api/v5/loc/search` 응답."""


class DabangGeojsonRegionResponseModel(ResponseModel):
    """동 경계 파일. 응답은 GeoJSON geometry 하나다 (역삼동은 `MultiPolygon`, 2026-10-25 실측). `Polygon` 이 와도
    `MultiPolygon` 좌표로 맞춘다.

    Args:
        type: 'MultiPolygon' 또는 'Polygon'.
        coordinates: MultiPolygon 좌표 ([폴리곤[링[[경도, 위도], ...]]]).
    """

    type: Annotated[
        str,
        Field(description='GeoJSON 종류')
    ]
    coordinates: Annotated[
        MultiPolygon,
        Field(description='MultiPolygon 좌표')
    ]

    @field_validator('coordinates', mode='before')
    @classmethod
    def as_multipolygon(cls, value: Any, info: ValidationInfo) -> Any:
        if info.data.get('type') == 'Polygon':
            return [value]
        return value


class DabangRegionModel(ResponseModel):
    """다방 지역 하나 (시·도·시·군·구·동).

    Args:
        gid: 다방 지역 번호. 동네정보 순위의 범위(`scopeRegionGid`)로 쓴다.
        code: 법정동 코드 앞자리 (시·도 2, 시·군·구 5, 동 8자리).
        short_name: 줄인 이름 ('서울').
    """

    gid: Annotated[
        int,
        Field(description='다방 지역 번호')
    ]
    code: Annotated[
        str,
        Field(description='법정동 코드 앞자리')
    ]
    name: Annotated[
        str,
        Field(description='이름')
    ]
    short_name: Annotated[
        str | None,
        Field(description='줄인 이름', alias='shortName')
    ] = None
    location: Annotated[
        DabangLocationModel | None,
        Field(description='중심 좌표')
    ] = None


class DabangRegionV5ResponseModel(DabangV5ResponseModel[DabangRegionModel]):
    """`GET /api/v5/region` 응답."""


class DabangRegionStatesV5ResponseModel(DabangV5ResponseModel[list[DabangRegionModel]]):
    """`GET /api/v5/region/states` 응답 (시·도 목록. 광주·전남은 '전남광주통합특별시' 코드 12)."""
