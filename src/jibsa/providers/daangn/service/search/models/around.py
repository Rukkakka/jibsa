"""`around.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnNearbyListing,
)
from jibsa.providers.daangn.service.region.models.station import DaangnStation
from jibsa.providers.daangn.service.region.models.university import DaangnUniversity

from typing import (
    Annotated,
    Any,
)


class DaangnStationListing(DaangnNearbyListing):
    """역 주변 매물. `distance_km` 는 역까지의 직선거리다."""

    walk_minutes: Annotated[
        int | None,
        Field(description='매물에서 역까지 도보 (분). 당근이 알려 주지 않으면 null')
    ] = None


class DaangnStationSearchResult(Result):
    """역 주변 매물 검색 결과.

    `notes`: 조회 한도·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnStation,
        Field(description='찾은 역 (검색 중심). 다른 검색의 region 과 같은 자리라 이름을 맞췄다')
    ]
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
        Field(exclude=True, description='이어 받을 위치 ({"after": 당근 커서, "region": 역의 동, "sidos": 찾은 시·도}). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[DaangnStationListing],
        Field(description='당근 웹 역 주변 목록 순서 매물')
    ]


class DaangnUniversitySearchResult(Result):
    """대학 주변 매물 검색 결과 (웹 대학 페이지의 매물 목록).

    `notes`: 조회 한도·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnUniversity,
        Field(description='찾은 대학 캠퍼스 (검색 중심). 다른 검색의 region 과 같은 자리라 이름을 맞췄다')
    ]
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
        Field(exclude=True, description='이어 받을 위치 ({"after": 당근 커서, "region": 대학이 있는 동, "sidos": 찾은 시·도}). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[DaangnNearbyListing],
        Field(description='웹 대학 페이지 목록 순서 매물 (대체로 가까운 순). distance_km 는 대학까지의 직선거리다')
    ]
