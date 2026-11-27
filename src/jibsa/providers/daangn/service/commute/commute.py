"""출퇴근 역 기준 매물 검색의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""

from itertools import pairwise

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    Listing,
    listing_as,
)
from jibsa.core.notes import (
    NOTE_KINDS,
    UPDATE_MAYBE_NEEDED,
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.common import (
    DaangnCoordinateInputModel,
    DaangnPropertyFilterModel,
    is_empty_property_filter,
)
from jibsa.providers.daangn.api.models.request.commute import (
    DaangnCommuteStationArticleConnectionRequestPayloadModel,
    DaangnCommuteStationsRequestPayloadModel,
    DaangnNearestCommuteStationRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.api.models.response.commute import (
    DaangnCommuteReachableStationModel,
    DaangnCommuteWaypointModel,
    DaangnNearestCommuteStationModel,
)
from jibsa.providers.daangn.service.common.constants import STATION_PAGE_SIZE
from jibsa.providers.daangn.service.common.listing import (
    article_to_listing,
    complex_building_notes,
    is_available,
    listing_budget_notes,
    no_trade_notes,
    trade_of,
)
from jibsa.providers.daangn.service.common.location import (
    station_base_name,
    station_name,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
    DaangnRegion,
)
from jibsa.providers.daangn.service.common.nearby import (
    connection_edges,
    hidden_location_notes,
    walk_minutes_to,
)
from jibsa.providers.daangn.service.common.response import (
    cursor_stopped_note,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.commute.constants import (
    COMMUTE_MAX_STATIONS,
    COMMUTE_MAX_WALK_TO_STATION,
    COMMUTE_SERVER_MAX_MINUTES,
    COMMUTE_STATION_DEFAULT_LIMIT,
    COMMUTE_STATION_MAX_LIMIT,
)
from jibsa.providers.daangn.service.commute.models import (
    DaangnCommuteLeg,
    DaangnCommuteListing,
    DaangnCommuteResult,
    DaangnCommuteStation,
    DaangnCommuteStationListings,
)
from jibsa.providers.daangn.service.region.area import (
    region_or_none,
    with_center_sido,
)

from typing import (
    NamedTuple,
)


class _Station(NamedTuple):
    """찾아볼 역 하나 (`_reachable_stations`): 이름, 회사 역까지 지하철 시간, 환승 횟수, 경로."""

    name: str
    minutes: int
    transfers: int | None
    # 출근 방향 구간. 모르면 None (`_route`)
    route: list[DaangnCommuteLeg] | None


class _Reachable(NamedTuple):
    """회사 역에서 지하철 시간 상한 안에 갈 수 있고 조건에 맞는 매물이 있는 역 (`_reachable_stations`)."""

    stations: list[_Station]
    notes: list[str]
    # 지하철 시간을 모르는 역 수 (서버가 준 역 중)
    unknown_time_count: int
    # 시간 상한과 상관없이 서버가 시간을 알려 준 역(조건에 맞는 매물이 있는 역)이 있었는지. 시간을 모르는 역은 상한을 늘려도 들어오지 않아 세지 않는다
    offered: bool


class _StationArticlesUnknown(Exception):
    """역 하나의 첫 쪽에 매물 목록(edges)이 없다 (`_station_articles`). 빈 목록이 아니라 모름이라 그 역만 알리고 다음 역으로 간다."""


class _StationArticles(NamedTuple):
    """역마다 받은 매물 (`_station_articles`). 역 안에서는 중복을 제거하고, 역 사이에서는 같은 매물을 각각 유지한다."""

    articles_by_id: dict[str, DaangnArticleModel]
    # 역마다 받은 매물 ID (서버 순서)
    ids_by_station: dict[str, list[str]]
    # 역마다 예산에 센 수 (빼고 읽은 빈 edge 포함)와 그중 빈 edge 수
    inspected_by_station: dict[str, int]
    dropped_by_station: dict[str, int]
    has_more_by_station: dict[str, bool]
    # 다음이 있다면서 이어 받을 쪽을 주지 않아 멈춘 역 (`connection_edges` 의 stopped)
    stopped_stations: set[str]
    # 역 주변 매물 목록에서 빈 edge 를 빼고 읽은 안내 (역 이름을 붙였다)
    notes: list[str]
    # 당근이 첫 쪽의 매물 목록(edges)을 주지 않아 매물을 모르는 역
    unknown_stations: set[str]


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
        reach.notes + found.notes + no_trade_notes(found.articles_by_id.values()) + complex_building_notes(shown)
        + hidden_location_notes(shown)
    )
    # 서버가 준 역이 모두 지하철 시간을 모르는 경우. 일부만 모르면 아래 두 안내가 맞고, 모두 모르면 '시간 안에 역이 없다' 가 아니라
    # '시간을 몰라 확인할 수 없다' 이므로 두 안내를 이 하나로 바꾼다 (둘째 안내가 역이 아예 없다고 읽혔다, 2026-11-19 리뷰)
    all_unknown = reach.unknown_time_count > 0 and not reach.offered
    if reach.unknown_time_count and not all_unknown:
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
        if all_unknown:
            message = (
                f'당근이 준 역 {reach.unknown_time_count}곳 모두 지하철 시간을 몰라 --max-minutes 안인지 확인할 수 없습니다. {nearby}'
            )
        elif reach.offered:
            # 상한 밖에는 조건에 맞는 매물이 있는 역이 있다 (지하철 시간을 모르는 역은 세지 않는다)
            message = (
                f'지하철 {max_minutes}분 안에는 조건에 맞는 매물이 있는 역이 없습니다. '
                + ('더 먼 역은 --max-minutes 를 늘리고, ' if max_minutes < COMMUTE_SERVER_MAX_MINUTES else '')
                + nearby
            )
        else:
            # 조건을 하나도 주지 않았으면 넓힐 조건이 없다
            widen = '' if is_empty_property_filter(property_filter) else '조건을 넓히거나, '
            message = (
                f'회사 역에서 지하철 {COMMUTE_SERVER_MAX_MINUTES}분 안에 조건에 맞는 매물이 있는 역이 없습니다 (당근은 조건에 맞는 '
                f'매물이 있는 역만 줍니다). {widen}{nearby}'
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
    unknown_names: list[str] = []
    for name, minutes, transfers, route in searched:
        if name in found.unknown_stations:
            # 당근이 이 역의 매물 목록을 주지 않았다. 없다([])는 뜻이 아니라 모름(null)이라 --limit 안내 대신 알린다
            unknown_names.append(name)
            groups.append(DaangnCommuteStationListings(
                station_name=name, subway_minutes=minutes, transfers=transfers, route=route,
                one_way_minutes=minutes + workplace.walk_minutes if workplace.walk_minutes is not None else None,
                inspected=0, returned=0, listings=None,
            ))
            continue
        station_listings = [listing for listing in listings if listing.commute_station == name]
        inspected = found.inspected_by_station[name]
        dropped = found.dropped_by_station[name]
        groups.append(DaangnCommuteStationListings(
            station_name=name, subway_minutes=minutes, transfers=transfers, route=route,
            one_way_minutes=minutes + workplace.walk_minutes if workplace.walk_minutes is not None else None,
            inspected=inspected, returned=len(station_listings), listings=station_listings,
        ))
        # 역 목록이 다음이 있다면서 이어 받을 쪽을 주지 않아 멈췄으면 --limit 안내 대신 멈췄다고 알린다 (`connection_edges`)
        stopped = name in found.stopped_stations
        for text in listing_budget_notes(
            limit, inspected, len(station_listings), max_limit=COMMUTE_STATION_MAX_LIMIT, has_more=found.has_more_by_station[name],
            narrow='조건', narrowable=not stopped, dropped=dropped,
        ) + ([note('일부', cursor_stopped_note('역 주변 매물', f'{inspected - dropped}건'))] if stopped else []):
            station_notes.setdefault(text, []).append(name)
    notes += [
        _station_note(f'찾아본 {len(searched)}곳 모두' if len(names) == len(searched) > 1 else '·'.join(names), text)
        for text, names in station_notes.items()
    ]
    if unknown_names:
        notes.append(note(
            '실패',
            f"당근이 {'·'.join(unknown_names)} 주변 매물 목록을 주지 않았습니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}",
        ))
    return DaangnCommuteResult(
        workplace_station=workplace,
        max_minutes=max_minutes,
        reachable_station_count=len(stations),
        returned=len(listings),
        unique_returned=len({listing.id for listing in listings}),
        stations=groups,
        listings=listings,
        notes=notes,
    )


# 리뷰 오탐 (2026-11-19, 근거 고침 2026-11-20): 노선 꼬리가 붙은 역(양평역(경의중앙선))의 이름 비교가 어긋나도 틀린 경로는 나가지
# 않는다. 꼬리가 어긋나면 `stops[-1][0] != station_name(boarding)` 이라 `_route` 가 None(모름)을 준다 (실측: 왕십리역 60분 447곳
# 중 꼬리 역 2곳은 waypoint 이름에도 꼬리가 같이 와 route 가 채워졌다)
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
        DaangnCommuteLeg(from_station_name=later, to_station_name=name, line=line)
        for (name, line), (later, _) in reversed(list(pairwise(stops)))
    ]


def _station_note(name: str, text: str) -> str:
    """역 이름을 붙인 안내. 종류 태그가 있으면 태그 뒤에 넣는다 (앞에 붙이면 태그를 못 알아봐 [참고] 가 또 붙는다)."""
    for kind in NOTE_KINDS:
        tag = f'[{kind}] '
        if text.startswith(tag):
            return f'{tag}{name}: {text.removeprefix(tag)}'
    return f'{name}: {text}'


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
            hint=f'지하철역이 있는 위치로 다시 찾거나, jibsa daangn search listings --lat {lat} --lng {lng} 로 회사 주변 지도 범위를 찾으세요',
        )
    nearest = unwrap_graphql(response, nearest, '가까운 역', conditions=False)
    walk = nearest.walking_minutes_to_station
    if walk is not None and walk > COMMUTE_MAX_WALK_TO_STATION:
        # 예전에는 도보 60분이 넘어도 그 역으로 찾았다. 웹은 이때 출퇴근 목록을 열지 않는다 (#215)
        raise JibsaError(
            code='NOT_FOUND',
            message=f'회사 위치에서 걸어서 {COMMUTE_MAX_WALK_TO_STATION}분 안에 지하철역이 없습니다 (가장 가까운 {station_name(nearest.station_name)}까지 {walk}분)',
            hint=f'지하철역이 있는 위치로 다시 찾거나, jibsa daangn search listings --lat {lat} --lng {lng} 로 회사 주변 지도 범위를 찾으세요',
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
        conditions=not is_empty_property_filter(property_filter),
    )
    reachable = [node for node in reachable if node.station]
    unknown_time_count = sum(1 for node in reachable if node.duration_minutes is None)
    timed = sorted(
        (node for node in reachable if node.duration_minutes is not None and node.duration_minutes <= max_minutes),
        key=lambda node: node.duration_minutes or 0,
    )
    # 역 이름이 곧 역 키다. 이름으로 겹침을 지우면 두 역이 합쳐진다는 2026-11-13 리뷰 지적은 오탐 (근거 고침 2026-11-20): 다음 단계의
    # 역 주변 매물 요청이 역 이름 하나만 받아(request/commute.py 의 station_name) 이름이 같은 두 역을 따로 조회할 길이 없다. 같은 이름이면
    # 같은 요청이라, 시간순으로 세운 뒤 setdefault 로 가장 짧은 시간의 경로 하나를 남기는 것이 그 요청과 맞다. 서버는 같은 이름 역을
    # 노선 꼬리로 갈라 준다 (2026-11-13 왕십리역: 서울5호선 '양평역' 34분, 경의중앙선 '양평역(경의중앙선)' 58분)
    first_routes: dict[str, _Station] = {}
    dropped_waypoints = 0
    for node in timed:
        assert node.station is not None and node.duration_minutes is not None
        # 경유역 목록에서 빈 항목을 빼고 읽었으면 어느 역이 빠졌는지 몰라 경로를 짐작하지 않는다 (null)
        dropped = node.null_items('route_waypoints')
        dropped_waypoints += dropped
        first_routes.setdefault(
            node.station.station_name,
            _Station(
                node.station.station_name, node.duration_minutes, node.transfer_count,
                None if dropped else _route(node.route_waypoints, nearest.station_name, node.station.station_name),
            ),
        )
    feed_notes: list[str] = []
    # 갈 수 있는 역 목록에서 빈 항목을 뺐으면 가까운 역을 고르는 목록이 모자란다. 값은 그대로 두고 알리기만 한다
    dropped_stations = response.data.null_items('commute_stations') if response.data else 0
    if dropped_stations:
        feed_notes.append(null_items_note('당근 출퇴근 역', dropped_stations))
    if dropped_waypoints:
        feed_notes.append(null_items_note('당근 출퇴근 경로 역', dropped_waypoints, ('route',)))
    if max_minutes > COMMUTE_SERVER_MAX_MINUTES:
        feed_notes.append(note(
            '범위',
            f'당근 출퇴근 지도는 지하철 {COMMUTE_SERVER_MAX_MINUTES}분 안 역까지만 줍니다. '
            f'--max-minutes {max_minutes} 이어도 {COMMUTE_SERVER_MAX_MINUTES}분까지의 역만 찾았습니다',
        ))
    return _Reachable(list(first_routes.values()), feed_notes, unknown_time_count, offered=any(node.duration_minutes is not None for node in reachable))


def _station_articles(
    client: DaangnClient,
    searched: list[_Station],
    property_filter: DaangnPropertyFilterModel,
    limit: int,
) -> _StationArticles:
    """역마다 주변 매물을 `limit` 건까지 받는다."""
    filtered = not is_empty_property_filter(property_filter)
    articles_by_id: dict[str, DaangnArticleModel] = {}
    ids_by_station: dict[str, list[str]] = {}
    inspected_by_station: dict[str, int] = {}
    dropped_by_station: dict[str, int] = {}
    has_more_by_station: dict[str, bool] = {}
    stopped_stations: set[str] = set()
    notes: list[str] = []
    unknown_stations: set[str] = set()
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
            connection = unwrap_graphql(
                response,
                response.data.commute_station_article_connection if response.data else None,
                '역 주변 매물',
                conditions=filtered,
            )
            # 첫 쪽의 목록이 null 이면 이 역의 매물은 모름이다. 이어 받는 쪽은 `connection_edges` 가 멈춤으로 본다
            if connection.edges is None and after is None:
                raise _StationArticlesUnknown
            return connection

        edge_notes: list[str] = []
        try:
            edges, has_more, _, stopped, dropped = connection_edges(fetch, limit, STATION_PAGE_SIZE, notes=edge_notes)
        except _StationArticlesUnknown:
            unknown_stations.add(station[0])
            continue
        notes += [_station_note(station[0], text) for text in edge_notes]
        # 조회 예산에 센 수라 빼고 읽은 빈 edge 도 센다. 빼면 예산을 다 쓰고 더 있는데도 받은 수가 limit 에 못 미쳐 [일부] 안내가 빠진다
        inspected_by_station[station[0]] = len(edges) + dropped
        dropped_by_station[station[0]] = dropped
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
    return _StationArticles(
        articles_by_id, ids_by_station, inspected_by_station, dropped_by_station, has_more_by_station, stopped_stations, notes,
        unknown_stations,
    )


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
                walk_minutes=walk_minutes_to(article, station_base_name(name)),
            ))
    return listings, list(shown.values())
