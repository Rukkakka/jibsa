"""출퇴근 역 기준 매물 검색 (search commute)."""


from itertools import pairwise

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    NOTE_KINDS,
    Listing,
    listing_as,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnCoordinateInputModel,
    DaangnPropertyFilterModel,
)
from jibsa.providers.daangn.api.request.commute import (
    DaangnCommuteStationArticleConnectionRequestPayloadModel,
    DaangnCommuteStationsRequestPayloadModel,
    DaangnNearestCommuteStationRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.api.response.commute import (
    DaangnCommuteReachableStationModel,
    DaangnCommuteWaypointModel,
    DaangnNearestCommuteStationModel,
)
from jibsa.providers.daangn.service.common import (
    COMMUTE_STATION_MAX_LIMIT,
    DaangnListingConditions,
    DaangnNearbyListing,
    DaangnRegion,
    article_to_listing,
    complex_building_notes,
    connection_edges,
    cursor_stopped_note,
    hidden_location_notes,
    is_available,
    listing_budget_notes,
    no_trade_notes,
    station_base_name,
    station_name,
    trade_of,
    unwrap_graphql,
    walk_minutes_to,
)
from jibsa.providers.daangn.service.region import (
    STATION_PAGE_SIZE,
    region_or_none,
    with_center_sido,
)

from typing import (
    Annotated,
    NamedTuple,
)


# 출퇴근 검색: 매물을 찾아볼 역 수 (역마다 요청 1회). 갈 수 있는 역 목록(`commuteStations`)은 요청 1회로 전부 받아 상한이 없다
COMMUTE_MAX_STATIONS: int = 10
# 역당 매물 수 기본값. 10곳 × 5건 = 50건으로 docs/llm.md 의 '한 번에 50건 이하' 에 맞는다. 매물 목록처럼 20 이면 셸 출력을
# 잘라 보여 주는 에이전트가 뒤쪽 역을 못 본다 (2026-10-23 실측: 강남역 20분 원룸 월세 10역 186건·86,469자)
COMMUTE_STATION_DEFAULT_LIMIT: int = 5
# 당근 출퇴근 지도가 주는 지하철 시간 상한 (2026-10-11 실측: 강남역 411곳·양평역 42곳 모두 60분에서 목록이 끝났다)
COMMUTE_SERVER_MAX_MINUTES: int = 60
# 회사에서 가장 가까운 역까지 이 도보 분을 넘으면 웹 출퇴근 지도는 '근처에 지하철역이 없어요' 로 끝낸다 (useNearestStation 의 `s`)
COMMUTE_MAX_WALK_TO_STATION: int = 60


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
    walk_to_station_minutes: Annotated[
        int | None,
        Field(description='매물에서 타는 역까지 도보 (분). 당근이 알려 주지 않으면 null. 역 묶음의 one_way_minutes 에 더하면 문 앞까지의 편도다')
    ] = None


class DaangnCommuteLeg(BaseModel):
    """출근 방향 경로의 한 구간: 한 노선을 타고 `from_station` 에서 `to_station` 까지 간다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    from_station: Annotated[
        str,
        Field(description="이 구간을 타는 역 ('역' 까지). 첫 구간은 역 묶음의 station_name, 그다음은 앞 구간의 to_station")
    ]
    to_station: Annotated[
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
        list[DaangnCommuteListing],
        Field(description='이 역 주변 매물 (당근이 준 순서)')
    ]


class DaangnCommuteResult(BaseModel):
    """출퇴근 검색 결과."""

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
    reachable_stations: Annotated[
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
    notes: Annotated[
        list[str],
        Field(exclude=True, description='찾아본 역 범위·조회 한도·제외 안내. CLI 가 결과 위에 붙인다')
    ] = []


def search_commute(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    max_minutes: int = 30,
    conditions: DaangnListingConditions | None = None,
    limit: int = COMMUTE_STATION_DEFAULT_LIMIT,
) -> DaangnCommuteResult:
    """회사 위치까지 지하철로 `max_minutes` 안에 갈 수 있는 역 주변 매물을 찾는다 (당근 웹 출퇴근 지도와 같다).

    회사 좌표 → 가장 가까운 역(`nearestCommuteStation`) → 그 역에서 갈 수 있고 조건에 맞는 매물이 있는 역 전부(`commuteStations`, 요청 1회) →
    지하철 시간 짧은 역부터 최대 10곳의 주변 매물(`commuteStationArticleConnection`)을 모은다. 역 주변 매물은
    `articlesByOriginalArticleIds` 카드와 필드·값이 같아 (2026-10-11 실측: 역삼역 20건·합정역 20건 모두 같음) 역 주변 목록
    (`search_station`)처럼 카드를 다시 받지 않는다. 역 묶음의 `one_way_minutes` 는 웹 목록의 '편도 N분'(회사 도보 + 지하철)이다.
    예전에 매물마다 주던 합산 통근 시간(매물 도보 + 지하철 + 회사 도보)은 웹에 없는 계산이라 뺐다 (#215).

    Raises:
        JibsaError: 회사 근처에 역이 없으면 NOT_FOUND, GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 출퇴근 쿼리를 바꿨을 때.
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    nearest, workplace = _workplace_station(client, lat, lng)
    reach = _reachable_stations(client, nearest, property_filter, max_minutes)
    stations = reach.stations
    searched = stations[:COMMUTE_MAX_STATIONS]
    found = _station_articles(client, searched, property_filter, limit)

    # 동 이름은 시·도 채우기에만 쓰여, 못 찾아도 매물은 보여 줄 수 있다. 받은 매물이 없으면 묻지 않는다
    region = region_or_none(client, lat, lng) if found.articles_by_id else None
    listings, shown = _commute_listings(client, found, searched, conditions, (lat, lng), region)
    notes = (
        reach.notes + no_trade_notes(found.articles_by_id.values()) + complex_building_notes(shown) + hidden_location_notes(shown)
    )
    if reach.unknown_times:
        # 받은 매물을 뺀 것이 아니라 찾을 역을 줄인 것이라 [제외] 가 아니라 [범위] 다 (아래 역 수 안내와 같다)
        notes.append(note('범위', '지하철 시간을 모르는 역은 --max-minutes 조건을 확인할 수 없어 제외했습니다'))
    if not stations:
        # 당근은 조건에 맞는 매물이 있는 역만 주어(`_reachable_stations`) 0곳은 역이 없다는 뜻이 아니다. 예전에는 '갈 수 있는 역이
        # 없습니다' 라고 해 조건 탓을 역 탓으로 읽게 했다 (2026-11-13 실측: 강남역 --trade 연세 는 0곳, 같은 3분 안에 역 5곳).
        # 회사 역은 웹 목록처럼 넣지 않으니 그 주변을 볼 명령을 알린다. 0곳은 정상 결과라 에러가 아니다 (2026-11-12 리뷰).
        # 이름만 주면 같은 이름의 다른 역(경의중앙선 양평역)으로 찾을 수 있어, `find_station` 이 받는 노선 붙인 이름
        # ('서울5호선 양평역')으로 권한다 (2026-11-12 리뷰). 출퇴근 API 의 노선 꼬리('양평역(경의중앙선)')는 역 검색이 모르는
        # 이름이라 뗀다. 예전에는 '경의중앙선 양평역(경의중앙선)역' 을 권해 따르면 REGION_NOT_FOUND 였다 (2026-11-13 리뷰·실측)
        workplace_label = ' '.join(
            part for part in ('·'.join(workplace.lines), station_name(station_base_name(nearest.station_name))) if part
        )
        nearby = f"회사 역({workplace_label}) 주변은 jibsa daangn search listings --station '{workplace_label}' 으로 보세요"
        if reach.offered:
            # 상한 밖(또는 지하철 시간을 모르는 역)에는 조건에 맞는 매물이 있는 역이 있다
            message = (
                f'지하철 {max_minutes}분 안에는 조건에 맞는 매물이 있는 역이 없습니다. '
                + ('더 먼 역은 --max-minutes 를 늘리고, ' if max_minutes < COMMUTE_SERVER_MAX_MINUTES else '')
                + nearby
            )
        else:
            message = (
                f'회사 역에서 지하철 {COMMUTE_SERVER_MAX_MINUTES}분 안에 조건에 맞는 매물이 있는 역이 없습니다 (당근은 조건에 맞는 '
                f'매물이 있는 역만 줍니다). 조건을 넓히거나, {nearby}'
            )
        notes.append(note('범위', message))
    if len(stations) > len(searched):
        notes.append(note(
            '범위',
            f'지하철 {max_minutes}분 안에 조건에 맞는 매물이 있는 역 {len(stations)}곳 중 가까운 {len(searched)}곳 주변만 찾았습니다. '
            # 찾는 역은 조건과 상관없이 지하철 시간 짧은 COMMUTE_MAX_STATIONS 곳이라 '조건을 좁히거나' 는 따라 해도 더 먼 역이
            # 나오지 않는다 (2026-11-11 리뷰)
            '더 먼 역은 jibsa daangn search listings --station <역 이름> 으로 그 역 주변을 따로 찾으세요',
        ))
    groups: list[DaangnCommuteStationListings] = []
    # 역마다 같은 안내('더 보려면 --limit 을 늘리거나…')가 역 수만큼 되풀이되지 않게 안내 문장마다 역을 모은다
    station_notes: dict[str, list[str]] = {}
    for name, minutes, transfers, route in searched:
        station_listings = [listing for listing in listings if listing.commute_station == name]
        inspected = found.inspected_by_station[name]
        groups.append(DaangnCommuteStationListings(
            station_name=name, subway_minutes=minutes, transfers=transfers, route=route,
            one_way_minutes=minutes + workplace.walk_minutes if workplace.walk_minutes is not None else None,
            inspected=inspected, returned=len(station_listings), listings=station_listings,
        ))
        # 역 목록이 다음이 있다면서 이어 받을 쪽을 주지 않아 멈췄으면 --limit 안내 대신 멈췄다고 알린다 (`connection_edges`)
        stopped = name in found.stopped_stations
        for text in listing_budget_notes(
            limit, inspected, len(station_listings), max_limit=COMMUTE_STATION_MAX_LIMIT, has_more=found.has_more_by_station[name],
            narrowable=not stopped,
        ) + ([note('일부', cursor_stopped_note('역 주변 매물', f'{inspected}건'))] if stopped else []):
            station_notes.setdefault(text, []).append(name)
    notes += [
        _station_note(f'찾아본 {len(searched)}곳 모두' if len(names) == len(searched) > 1 else '·'.join(names), text)
        for text, names in station_notes.items()
    ]
    return DaangnCommuteResult(
        workplace_station=workplace,
        max_minutes=max_minutes,
        reachable_stations=len(stations),
        returned=len(listings),
        unique_returned=len({listing.id for listing in listings}),
        stations=groups,
        listings=listings,
        notes=notes,
    )


class _Station(NamedTuple):
    """찾아볼 역 하나 (`_reachable_stations`): 이름, 회사 역까지 지하철 시간, 환승 횟수, 경로."""

    name: str
    minutes: int
    transfers: int | None
    # 출근 방향 구간. 모르면 None (`_route`)
    route: list[DaangnCommuteLeg] | None


def _route(waypoints: list[DaangnCommuteWaypointModel], workplace: str, boarding: str) -> list[DaangnCommuteLeg] | None:
    """`commuteStations` 의 경로(`routeWaypoints`)를 타는 역(`boarding`)에서 회사 역(`workplace`)으로 가는 구간으로. 모양이 다르면 None.

    서버 경로는 회사 역에서 시작해 갈아타는 역을 지나 타는 역에서 끝나고, 역마다의 `lineName` 은 그 역에서 다음 역까지 구간의
    노선이다 (마지막 역은 앞 구간 노선을 되풀이한다). 웹 역 상세(CommuteStationDetailView)는 이 순서를 뒤집지 않고 그대로 그린다.
    그대로 내보내면 '이 역에서 타는 노선' 으로 읽혀 틀리기 쉬워, 뒤에서부터 (다음 역 → 이 역, 이 역의 노선) 구간을 만든다. 역·노선은
    서버 경로 그대로이고 방향만 다르다 (2026-11-13 번들 2026-11-v73 대조, 강남역·여의도역 회사 828경로 실측: 모두 역 수 = 환승 + 2,
    마지막 노선 = 앞 구간 노선, 처음 = 회사 역, 끝 = 타는 역). 역이 둘보다 적거나, 역·노선 이름이 빠졌거나, 처음이 회사 역·끝이
    타는 역이 아니면 방향·노선을 짐작하지 않고 None(모름)이다. 경로가 없거나 빈 목록이어도 경로를 모르는 것이라 None 이다.
    역 이름은 다른 역 이름처럼 '역' 을 붙인다 (`station_name`).
    """
    stops = [
        (station_name(point.station_name), point.line_name)
        for point in waypoints if point.station_name and point.line_name
    ]
    if (
        len(stops) < 2 or len(stops) < len(waypoints)
        or stops[0][0] != station_name(workplace) or stops[-1][0] != station_name(boarding)
    ):
        return None
    return [
        DaangnCommuteLeg(from_station=later, to_station=name, line=line)
        for (name, line), (later, _) in reversed(list(pairwise(stops)))
    ]


def _station_note(name: str, text: str) -> str:
    """역 이름을 붙인 안내. 종류 태그가 있으면 태그 뒤에 넣는다 (앞에 붙이면 태그를 못 알아봐 [참고] 가 또 붙는다)."""
    for kind in NOTE_KINDS:
        tag = f'[{kind}] '
        if text.startswith(tag):
            return f'{tag}{name}: {text.removeprefix(tag)}'
    return f'{name}: {text}'


class _Reachable(NamedTuple):
    """회사 역에서 지하철 시간 상한 안에 갈 수 있고 조건에 맞는 매물이 있는 역 (`_reachable_stations`)."""

    stations: list[_Station]
    notes: list[str]
    # 지하철 시간을 모르는 역이 있었는지
    unknown_times: bool
    # 시간 상한과 상관없이 서버가 준 역(조건에 맞는 매물이 있는 역)이 있었는지
    offered: bool


class _StationArticles(NamedTuple):
    """역마다 받은 매물 (`_station_articles`). 역 안에서는 중복을 제거하고, 역 사이에서는 같은 매물을 각각 유지한다."""

    articles_by_id: dict[str, DaangnArticleModel]
    # 역마다 받은 매물 ID (서버 순서)
    ids_by_station: dict[str, list[str]]
    inspected_by_station: dict[str, int]
    has_more_by_station: dict[str, bool]
    # 다음이 있다면서 이어 받을 쪽을 주지 않아 멈춘 역 (`connection_edges` 의 stopped)
    stopped_stations: set[str]


def _workplace_station(
    client: DaangnClient,
    lat: float,
    lng: float,
) -> tuple[DaangnNearestCommuteStationModel, DaangnCommuteStation]:
    """회사 위치에서 가장 가까운 지하철역.

    Raises:
        JibsaError: 근처에 지하철역이 없을 때 (NOT_FOUND).
    """
    response = client.run_request_nearest_commute_station(
        DaangnNearestCommuteStationRequestPayloadModel(coordinate=DaangnCoordinateInputModel(lat=lat, lon=lng))
    )
    nearest = response.data.nearest_commute_station if response.data else None
    if nearest is None and not response.errors:
        raise JibsaError(
            code='NOT_FOUND',
            message='회사 위치 근처에서 지하철역을 찾지 못했습니다',
            hint='지하철역이 있는 위치로 다시 찾거나, jibsa daangn search listings --lat <위도> --lng <경도> 로 회사 주변 지도 범위를 찾으세요',
        )
    nearest = unwrap_graphql(response, nearest, '가까운 역')
    walk = nearest.walking_minutes_to_station
    if walk is not None and walk > COMMUTE_MAX_WALK_TO_STATION:
        # 예전에는 도보 60분이 넘어도 그 역으로 찾았다. 웹은 이때 출퇴근 목록을 열지 않는다 (#215)
        raise JibsaError(
            code='NOT_FOUND',
            message=f'회사 위치에서 걸어서 {COMMUTE_MAX_WALK_TO_STATION}분 안에 지하철역이 없습니다 (가장 가까운 {station_name(nearest.station_name)}까지 {walk}분)',
            hint='지하철역이 있는 위치로 다시 찾거나, jibsa daangn search listings --lat <위도> --lng <경도> 로 회사 주변 지도 범위를 찾으세요',
        )
    workplace = DaangnCommuteStation(
        name=nearest.station_name,
        lines=nearest.line_number,
        walk_minutes=nearest.walking_minutes_to_station,
    )
    return nearest, workplace


def _reachable_stations(
    client: DaangnClient,
    nearest: DaangnNearestCommuteStationModel,
    property_filter: DaangnPropertyFilterModel,
    max_minutes: int,
) -> _Reachable:
    """회사 역에서 갈 수 있는 역 전부(`commuteStations`, 요청 1회)에서 지하철 `max_minutes` 분 안 역을 시간 짧은 순으로 모은다.

    서버는 매물 조건(`propertyFilter`)에 맞는 매물이 있는 역만 준다 (2026-11-13 실측: 강남역 조건 없음 411곳, 아파트 전세 285곳
    (양재시민의숲역 빠짐), 연세 0곳). 그래서 역 수와 '역이 없다' 는 늘 조건에 맞는 매물이 있는 역 기준이다.

    웹 출퇴근 지도는 이 목록으로 역 핀을 찍고 '보고 있는 지역' 탭에서 지하철 시간 순으로 세운다 (CommuteFeed 의 `k`:
    `toSorted((e,t)=>e.durationMinutes-t.durationMinutes)`). jibsa 도 시간 순(같으면 서버 순서)으로 세워 가까운 역부터 찾는다.
    같은 역이 여러 경로로 오면 가장 짧은 경로를 쓴다. 회사 역은 웹 목록처럼 넣지 않는다 (예전에는 지하철 0분 역으로 맨 앞에 넣었다,
    #215). 서버는 지하철 60분 안 역까지만 준다 (`COMMUTE_SERVER_MAX_MINUTES`). 예전에는 `commuteFeed` 를 50곳씩 4쪽까지 넘기며
    시간 순이라는 실측 전제로 앞부분을 끊어 역 수를 덜 세기도 했다 (#215, 2026-11-12 번들 대조).

    Raises:
        JibsaError: GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 웹이 출퇴근 쿼리를 바꿨을 때.
    """
    response = client.run_request_commute_stations(
        DaangnCommuteStationsRequestPayloadModel(from_station_name=nearest.station_name, property_filter=property_filter)
    )
    reachable: list[DaangnCommuteReachableStationModel] = unwrap_graphql(
        response, response.data.commute_stations if response.data else None, '출퇴근 역',
    )
    reachable = [node for node in reachable if node.station]
    unknown_station_times = any(node.duration_minutes is None for node in reachable)
    timed = sorted(
        (node for node in reachable if node.duration_minutes is not None and node.duration_minutes <= max_minutes),
        key=lambda node: node.duration_minutes or 0,
    )
    # 역 이름이 곧 역 키다. 같은 이름 역도 서버가 노선 꼬리로 이름을 갈라 주고(2026-11-13 왕십리역 실측: 서울5호선 '양평역' 34분,
    # 경의중앙선 '양평역(경의중앙선)' 58분. 강남·여의도·왕십리 응답 모두 겹치는 이름 0), 역 주변 매물 쿼리도 이름 하나만 받는다.
    # 이름으로 겹침을 지우면 두 역이 합쳐진다는 2026-11-13 리뷰 지적은 오탐
    first_routes: dict[str, _Station] = {}
    for node in timed:
        assert node.station is not None and node.duration_minutes is not None
        first_routes.setdefault(
            node.station.station_name,
            _Station(
                node.station.station_name, node.duration_minutes, node.transfer_count,
                _route(node.route_waypoints, nearest.station_name, node.station.station_name),
            ),
        )
    feed_notes: list[str] = []
    if max_minutes > COMMUTE_SERVER_MAX_MINUTES:
        feed_notes.append(note(
            '범위',
            f'당근 출퇴근 지도는 지하철 {COMMUTE_SERVER_MAX_MINUTES}분 안 역까지만 줍니다. '
            f'--max-minutes {max_minutes} 이어도 {COMMUTE_SERVER_MAX_MINUTES}분까지의 역만 찾았습니다',
        ))
    return _Reachable(list(first_routes.values()), feed_notes, unknown_station_times, offered=bool(reachable))


def _station_articles(
    client: DaangnClient,
    searched: list[_Station],
    property_filter: DaangnPropertyFilterModel,
    limit: int,
) -> _StationArticles:
    """역마다 주변 매물을 `limit` 건까지 받는다."""
    articles_by_id: dict[str, DaangnArticleModel] = {}
    ids_by_station: dict[str, list[str]] = {}
    inspected_by_station: dict[str, int] = {}
    has_more_by_station: dict[str, bool] = {}
    stopped_stations: set[str] = set()
    for station in searched:
        # 역마다 받은 매물 수로 예산을 세고, 100건씩 다음 페이지를 이어 받는다
        def fetch(size: int, after: str | None) -> DaangnCommuteStationArticleConnectionModel:
            response = client.run_request_commute_station_article_connection(
                DaangnCommuteStationArticleConnectionRequestPayloadModel(
                    first=size,
                    after=after,
                    station_name=station[0],
                    property_filter=property_filter,
                )
            )
            return unwrap_graphql(
                response,
                response.data.commute_station_article_connection if response.data else None,
                '역 주변 매물',
            )

        edges, has_more, _, stopped = connection_edges(fetch, limit, STATION_PAGE_SIZE)
        inspected_by_station[station[0]] = len(edges)
        has_more_by_station[station[0]] = has_more
        if stopped:
            stopped_stations.add(station[0])
        seen: set[str] = set()
        for edge in edges:
            article = edge.node.article if edge.node else None
            if article is not None and article.original_id not in seen:
                seen.add(article.original_id)
                articles_by_id.setdefault(article.original_id, article)
                ids_by_station.setdefault(station[0], []).append(article.original_id)
    return _StationArticles(articles_by_id, ids_by_station, inspected_by_station, has_more_by_station, stopped_stations)


def _commute_listings(
    client: DaangnClient,
    found: _StationArticles,
    searched: list[_Station],
    conditions: DaangnListingConditions,
    center: tuple[float, float],
    region: DaangnRegion | None,
) -> tuple[list[DaangnCommuteListing], list[DaangnArticleModel]]:
    """받은 매물을 역마다 역까지 도보 분을 붙인 매물로 바꾼다. 역 순서·역 안 매물 순서는 서버 순서 그대로다.

    예전에는 모든 매물을 예상 통근 시간 순으로 다시 세웠다. 웹은 역마다 서버가 준 순서로 보여 줘 그대로 둔다 (#215).
    내보낸 원본 매물도 준다.
    """
    listings: list[DaangnCommuteListing] = []
    shown: dict[str, DaangnArticleModel] = {}
    sido_cache: dict[tuple[str, str], str | None] = {}
    bases: dict[str, Listing | None] = {}
    for name, *_ in searched:
        for article_id in found.ids_by_station.get(name, []):
            article = found.articles_by_id[article_id]
            if article_id not in bases:
                trade = trade_of(article, conditions) if is_available(article) else None
                # 카드에 없는 시·도는 지역 검색으로 채운다 (`with_center_sido`·`sido_of`. 회사 동네의 시·도는 세종 매물에만
                # 바로 쓰고, 이름이 같은 다른 시·도의 구·동은 카드의 지역 ID 로 가른다)
                bases[article_id] = (
                    article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
                    if trade is not None else None
                )
            base = bases[article_id]
            if base is None:
                continue
            shown.setdefault(article_id, article)
            listings.append(listing_as(
                DaangnCommuteListing,
                base,
                commute_station=name,
                # 매물 카드의 인근 역 이름에는 출퇴근 API 의 노선 꼬리가 없다 (2026-11-13 실측: 출퇴근 '양평역(경의중앙선)' 주변
                # 매물 카드는 '양평역'. 꼬리째 견주면 그 역 매물의 도보가 모두 null 이었다)
                walk_to_station_minutes=walk_minutes_to(article, station_base_name(name)),
            ))
    return listings, list(shown.values())
