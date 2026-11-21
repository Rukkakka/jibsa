"""역·학교·동·구 주변 아파트 단지 (search complexes)."""


from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
)
from jibsa.core.korean import (
    quoted,
)
from jibsa.core.listing import (
    more_hint,
    normalize_address,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.search import (
    ZigbangDanjisIdsRequestParameterModel,
    ZigbangSubwaysRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.complex.search import ZigbangSubwayAptModel
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    SCHOOL_LOOKUP_ERRORS,
    apt_complex_id,
    apt_danji_url,
    household_count,
)
from jibsa.providers.zigbang.service.region import (
    resolve_station,
)

from typing import (
    Annotated,
)


# 역 주변 단지 순서가 거리순이 아니라는 안내. 웹 패널(주변단지 탭)과 더보기 화면 모두 거리순이 없다
STATION_COMPLEX_ORDER_NOTE: str = (
    '직방 웹 아파트 지도의 역 주변단지 목록처럼 조회수 순입니다 (가까운 순이 아님). 가까운 단지는 distance_m 으로 고르세요'
)


class ZigbangStationComplex(BaseModel):
    """역 주변 아파트 단지 하나. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ]
    households: Annotated[
        int | None,
        Field(description='세대수')
    ]
    distance_m: Annotated[
        int | None,
        Field(description='역에서의 거리 (m)')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class ZigbangStationComplexesResult(BaseModel):
    """역 주변 아파트 단지 목록 (조회수 순)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station: Annotated[
        str,
        Field(description='찾은 역 이름')
    ]
    station_address: Annotated[
        str | None,
        Field(description='역 주소')
    ] = None
    total: Annotated[
        int | None,
        Field(description='역에서 1.5km 안 단지 수 (limit 적용 전). 직방이 주지 않으면 모름(null)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='받지 않은 단지가 남았는지 (이어 받기는 없다. --limit 으로)')
    ]
    complexes: Annotated[
        list[ZigbangStationComplex],
        Field(description='직방 웹 주변단지 목록 순서(조회수 순)의 단지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='순서·일부만 보여 준다는 안내. CLI 가 결과 위에 붙인다')
    ] = []


def station_complex_of(danji_id: int, apt: ZigbangSubwayAptModel | None) -> ZigbangStationComplex:
    """단지 ID 와 역 주변 단지 정보로 결과 한 줄을 만든다. 역 주변 단지 정보에 없는 단지면 이름·주소·거리는 모름(null)이다."""
    return ZigbangStationComplex(
        complex_id=apt_complex_id(danji_id),
        name=apt.name if apt else None,
        address=normalize_address(apt.old_address) if apt else None,
        households=household_count(apt.household) if apt else None,
        distance_m=apt.distance_num if apt else None,
        url=apt_danji_url(danji_id),
    )


def search_station_complexes(client: ZigbangClient, query: str, *, limit: int = 20) -> ZigbangStationComplexesResult:
    """역 주변 아파트 단지를 직방 웹 '<역> 주변단지' 목록 순서(조회수 순)로 `limit` 곳 준다 (지역 검색 1회 + 2회 호출).

    순서와 수는 `/apt/danjis/ids`(웹 패널·더보기 화면과 같은 변수) 그대로이고 다시 세우지 않는다. 단지 이름·주소·세대수·
    역에서의 거리는 웹이 역을 고를 때 함께 부르는 `/apt/subways/{id}` 의 주변 단지에서 붙인다 (출력 보강, 2026-11-15
    실측: 강남역 112곳이 두 응답에 똑같이 있다). 두 응답이 어긋나 주변 단지에 없는 단지는 빼지 않고 이름·거리를 모름(null)으로
    두고 알린다. 이 덤 조회는 본 조회 뒤에 부르고, 실패(요청 제한 포함)하면 단지 ID 목록만 `[실패]` 안내와 함께 낸다.
    지역 검색은 역 결과만 본다 (`resolve_station`).

    Raises:
        JibsaError: 역이 아닌 이름일 때 (INVALID_ARGUMENT).
        RegionNotFoundError: 이름을 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 역이 여러 곳일 때.
    """
    place = resolve_station(client, query)
    if place is None or place.subway_id is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"역 이름을 주세요. {quoted(query, '은/는')} 직방 지역 검색에서 역이 아닙니다",
            hint=(
                '동·구의 단지는 jibsa zigbang search locations <단지 이름> 으로 찾거나 jibsa zigbang search listings apt <동> '
                '결과의 complex_id 를 쓰세요'
            ),
        )
    # 순서·수를 주는 본 조회를 먼저 받는다. 이름·주소·세대수·거리는 덤이라 실패해도 단지 ID 목록은 버리지 않는다
    response = client.run_request_danjis_ids(ZigbangDanjisIdsRequestParameterModel(subway_id=place.subway_id, limit=limit))
    notes: list[str] = []
    station_name: str | None = None
    apts: dict[int, ZigbangSubwayAptModel] = {}
    lookup_failed = False
    try:
        station = client.run_request_subways(ZigbangSubwaysRequestParameterModel(subway_id=place.subway_id))
    except SCHOOL_LOOKUP_ERRORS as exc:
        lookup_failed = True
        notes.append(note(
            '실패',
            f'직방 역 주변 단지 정보를 받지 못해({type(exc).__name__}) 단지 이름·주소·세대수·거리를 모릅니다 (url 의 단지 페이지에서 확인)',
        ))
    else:
        station_name = station.name
        apts = {apt.id: apt for apt in station.apt_list}
    ids = response.ids[:limit]
    complexes = [station_complex_of(danji_id, apts.get(danji_id)) for danji_id in ids]
    total = response.count
    # 직방이 단지 수를 주지 않으면 더 있는지 모른다. 꽉 찬 쪽이면 더 있을 수 있다고 본다 (catalog 과 같다)
    has_more = total > len(complexes) if total is not None else len(response.ids) >= limit
    unknown = sum(1 for danji_id in ids if danji_id not in apts)
    if unknown and not lookup_failed:
        notes.append(note('참고', f'{unknown}곳은 직방 역 주변 단지 정보에 없어 이름·주소·세대수·거리를 모릅니다 (url 의 단지 페이지에서 확인)'))
    notes.append(STATION_COMPLEX_ORDER_NOTE)
    if has_more:
        head = (
            f'주변 단지 {total}곳 중 앞 {len(complexes)}곳입니다' if total is not None
            else f'앞 {len(complexes)}곳입니다. 직방이 주변 단지 수를 주지 않아 더 있을 수 있습니다'
        )
        notes.append(note('일부', f'{head}. {more_hint(limit, MAX_LIST_LIMIT, None)}'))
    return ZigbangStationComplexesResult(
        station=station_name or place.name,
        station_address=place.address,
        total=total,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )
