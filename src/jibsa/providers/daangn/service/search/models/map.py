"""`map.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnNearbyListing,
    DaangnRegion,
)
from jibsa.providers.daangn.service.region.models.address import DaangnAddress

from typing import (
    Annotated,
    Any,
)


class DaangnDongSearchResult(Result):
    """동 매물 검색 결과 (웹 지도의 동 클러스터 매물 목록).

    `notes`: 매물 수·조회 한도 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion,
        Field(description='찾은 동')
    ]
    total: Annotated[
        int | None,
        Field(description='동 안에서 조건에 맞는 매물 수 (웹 지도의 동 거품 "매물 N개"). 받지 못하면 null')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(
            exclude=True,
            description='이어 받을 위치 ({"after": 당근 커서, "total": 앞에서 센 수, "received": 지금까지 받은 원본 수}). 더 없으면 None',
        )
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 목록 순서(최근 순) 매물. 모두 그 동 매물이다. distance_km 는 동 중심까지의 직선거리다')
    ]


class DaangnMapSearchResult(Result):
    """지도 화면 범위 매물 검색 결과 (웹 지도의 매물 목록).

    `notes`: 범위·매물 수·조회 한도 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='찾은 구 (구 이름으로 찾았을 때) 또는 화면 가운데가 속한 동 (좌표·주소로 찾았을 때). 모르면 null')
    ] = None
    address: Annotated[
        DaangnAddress | None,
        Field(description='--address 로 찾은 도로명 주소와 그 좌표 (화면 가운데). 주소로 찾지 않았으면 키가 없다')
    ] = None
    zoom: Annotated[
        int,
        Field(description='웹 지도 줌. 범위는 데스크톱 지도 화면(1440×900 창에서 목록 패널을 뺀 영역) 기준이다')
    ]
    width_km: Annotated[
        float,
        Field(description='화면 범위의 가로 (km)')
    ]
    height_km: Annotated[
        float,
        Field(description='화면 범위의 세로 (km)')
    ]
    total: Annotated[
        int | None,
        Field(description='화면 범위 안에서 조건에 맞는 매물 수 (당근 집계, 1000 에서 잘린다). 모르면 null')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ]
    next_position: Annotated[
        dict[str, Any] | None,
        Field(
            exclude=True,
            description='이어 받을 위치 ({"after": 당근 커서, "total": 앞에서 센 수, "region": 결과의 region, "sidos": 찾은 시·도}). 더 없으면 None',
        )
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 지도 목록 순서(최근 순) 매물. distance_km 는 화면 가운데까지의 직선거리다 (순서와는 상관없다)')
    ]

    @model_serializer(mode='wrap')
    def drop_missing_address(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 구·좌표로 찾은 결과에 주소는 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.address is None:
            data.pop('address', None)
        return data
