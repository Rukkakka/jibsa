"""출퇴근 역 기준 매물 검색의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnNearbyListing,
)

from typing import (
    Annotated,
)


class DaangnCommuteStation(BaseModel):
    """회사에서 가장 가까운 역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='역 이름')
    ]
    lines: Annotated[
        list[str],
        Field(description='노선')
    ] = []
    walk_minutes: Annotated[
        int | None,
        Field(description='회사에서 역까지 도보 (분)')
    ] = None


class DaangnCommuteListing(DaangnNearbyListing):
    """출퇴근 검색 매물. 타는 역까지 도보 분을 붙인다. `distance_km` 는 회사까지의 직선거리다.

    타는 역은 역마다 묶는 데만 쓰고 출력하지 않는다. 타는 역·지하철 시간·환승은 매물이 들어 있는 역 묶음
    (`DaangnCommuteStationListings`)에 한 번만 있다 (매물마다 되풀이하면 출력의 13%가 같은 값이었다).
    """

    commute_station: Annotated[
        str,
        Field(exclude=True, description='타는 역 (매물 주변 역). 출력은 역 묶음의 station_name')
    ]
    walk_minutes: Annotated[
        int | None,
        Field(description='매물에서 타는 역까지 도보 (분). 당근이 알려 주지 않으면 null. 역 묶음의 one_way_minutes 에 더하면 문 앞까지의 편도다')
    ] = None


class DaangnCommuteLeg(BaseModel):
    """출근 방향 경로의 한 구간: 한 노선을 타고 `from_station_name` 에서 `to_station_name` 까지 간다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    from_station_name: Annotated[
        str,
        Field(description="이 구간을 타는 역 ('역' 까지). 첫 구간은 역 묶음의 station_name, 그다음은 앞 구간의 to_station_name")
    ]
    to_station_name: Annotated[
        str,
        Field(description="이 구간에서 내리는 역 ('역' 까지). 갈아타는 역이고, 마지막 구간은 회사 역 (workplace_station)")
    ]
    line: Annotated[
        str,
        Field(description='이 구간의 노선 (예: 서울3호선)')
    ]


class DaangnCommuteStationListings(BaseModel):
    """역 하나의 매물. 같은 매물이 다른 역에도 포함될 수 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station_name: Annotated[
        str,
        Field(description='타는 역 (매물 주변 역)')
    ]
    subway_minutes: Annotated[
        int,
        Field(description='이 역에서 회사 역까지 지하철 시간 (분)')
    ]
    transfers: Annotated[
        int | None,
        Field(description='환승 횟수')
    ]
    route: Annotated[
        list[DaangnCommuteLeg] | None,
        Field(description=(
            '이 역에서 회사 역까지 지하철 경로를 출근 방향 구간으로 (구간 수 = 환승 + 1). 역·노선은 당근 출퇴근 지도의 역 상세 경로와 같다. '
            '당근이 경로를 주지 않았거나 경로 모양이 달라 읽을 수 없으면 null'
        ))
    ]
    one_way_minutes: Annotated[
        int | None,
        Field(description="당근 웹 출퇴근 목록의 '편도 N분' = 이 역에서 회사 역까지 지하철 + 회사 역에서 회사까지 도보. 회사 도보를 모르면 null")
    ] = None
    inspected: Annotated[
        int,
        Field(description='이 역에서 받은 매물 수 (조회 예산에 센 수, 제외 전)')
    ]
    returned: Annotated[
        int,
        Field(description='이 역에서 반환한 매물 수')
    ]
    listings: Annotated[
        list[DaangnCommuteListing] | None,
        Field(description='이 역 주변 매물 (당근이 준 순서). 당근이 이 역의 매물 목록을 주지 않으면 null (빈 목록 []과 다르다. 모름이다)')
    ]


class DaangnCommuteResult(Result):
    """출퇴근 검색 결과.

    `notes`: 찾아본 역 범위·조회 한도·제외 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    workplace_station: Annotated[
        DaangnCommuteStation,
        Field(description='회사에서 가장 가까운 역')
    ]
    max_minutes: Annotated[
        int,
        Field(description='타는 역에서 회사 역까지 지하철 시간 상한 (분)')
    ]
    reachable_station_count: Annotated[
        int,
        Field(description='지하철 시간 상한 안에서 조건에 맞는 매물이 있는 역 수 (당근은 그런 역만 준다. stations 와 같은 기준, 회사 역은 들지 않는다)')
    ]
    returned: Annotated[
        int,
        Field(description='역별 반환 건수의 합 (역 사이 중복 포함)')
    ]
    listings: Annotated[
        list[DaangnCommuteListing],
        Field(exclude=True, description='역별 결과를 합친 내부 목록')
    ]
    unique_returned: Annotated[
        int,
        Field(description='역 사이 중복을 뺀 매물 수')
    ] = 0
    stations: Annotated[
        list[DaangnCommuteStationListings],
        Field(description='찾아본 역마다의 매물 (지하철 시간 짧은 순)')
    ] = []
