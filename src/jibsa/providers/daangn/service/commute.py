"""출퇴근 역 기준 매물 검색 (search commute)."""

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
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnCoordinateInputModel,
    DaangnPropertyFilterModel,
)
from jibsa.providers.daangn.api.request.commute import (
    DaangnCommuteFeedRequestPayloadModel,
    DaangnCommuteStationArticleConnectionRequestPayloadModel,
    DaangnNearestCommuteStationRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.api.response.commute import DaangnNearestCommuteStationModel
from jibsa.providers.daangn.service.common import (
    DaangnListingConditions,
    DaangnRegion,
    article_to_listing,
    complex_building_notes,
    is_available,
    listing_budget_notes,
    trade_of,
    trade_unselected_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    region_or_none,
    station_article_edges,
    with_center_sido,
)

from typing import (
    Annotated,
    NamedTuple,
)


# 출퇴근 검색: 매물을 찾아볼 역 수(역마다 요청 1회)와 갈 수 있는 역 목록을 넘겨 보는 최대 페이지
COMMUTE_MAX_STATIONS: int = 10
# 역 목록은 50곳씩이다. 매물은 가까운 10곳만 찾으므로 넘는 역은 더 받지 않고 notes 로 알린다
# (2026-10-11 실측: 강남역 60분 안 411곳 = 9쪽, 4쪽 마지막 역 35분)
COMMUTE_FEED_MAX_PAGES: int = 4
# 당근 출퇴근 지도가 주는 지하철 시간 상한 (2026-10-11 실측: 강남역 411곳·양평역 42곳 모두 60분에서 목록이 끝났다)
COMMUTE_SERVER_MAX_MINUTES: int = 60
# 도보 시간을 몰라 통근 시간(commute_minutes)이 null 인 매물은 지하철 시간에 이만큼 더해 정렬한다 (도보를 아는 매물보다 뒤로)
COMMUTE_UNKNOWN_WALK_MINUTES: int = 30


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


class DaangnCommuteListing(Listing):
    """출퇴근 검색 매물. 회사까지 가는 역·시간을 붙인다. `distance_km` 는 회사까지의 직선거리다.

    타는 역·지하철 시간·환승은 역마다 묶고 정렬하는 데 쓰고 출력하지 않는다. 출력에서는 매물이 들어 있는 역 묶음
    (`DaangnCommuteStationListings`)에 한 번만 있다 (매물마다 되풀이하면 출력의 13%가 같은 값이었다).
    """

    commute_station: Annotated[
        str,
        Field(exclude=True, description='타는 역 (매물 주변 역). 출력은 역 묶음의 station_name')
    ]
    subway_minutes: Annotated[
        int,
        Field(exclude=True, description='타는 역에서 회사 역까지 지하철 시간 (분). 출력은 역 묶음에')
    ]
    transfers: Annotated[
        int | None,
        Field(exclude=True, description='환승 횟수. 출력은 역 묶음에')
    ]
    walk_to_station_minutes: Annotated[
        int | None,
        Field(description='매물에서 타는 역까지 도보 (분). 당근이 알려 주지 않으면 null')
    ] = None
    commute_minutes: Annotated[
        int | None,
        Field(description='예상 통근 시간 (분) = 매물→역 도보 + 지하철 + 회사 역→회사 도보. 기다리는 시간은 넣지 않는다')
    ] = None


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
        Field(description='이 역 주변 매물 (통근 시간 짧은 순)')
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
        Field(description=(
            '지하철 시간 상한 안에 갈 수 있는 역 수 (회사 역 0분 포함, stations 와 같은 기준). '
            '역 목록은 200곳까지만 받아, 더 있으면 notes 로 알린다'
        ))
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
        Field(exclude=True, description='찾아본 역 범위 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def search_commute(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    max_minutes: int = 30,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnCommuteResult:
    """회사 위치까지 지하철로 `max_minutes` 안에 갈 수 있는 역 주변 매물을 찾는다 (당근 웹 출퇴근 지도와 같다).

    회사 좌표 → 가장 가까운 역(`nearestCommuteStation`) → 그 역에서 갈 수 있는 역(`commuteFeed`, 지하철 시간
    짧은 순) → 가까운 역부터 최대 10곳의 주변 매물(`commuteStationArticleConnection`)을 모은다. 역 주변 매물은
    `articlesByOriginalArticleIds` 카드와 필드·값이 같아 (2026-10-11 실측: 역삼역 20건·합정역 20건 모두 같음) 역 주변 목록
    (`search_station`)처럼 카드를 다시 받지 않는다.

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
    region = region_or_none(client, lat, lng) if found.stations_by_id else None
    listings, shown, unselected = _commute_listings(client, found, conditions, (lat, lng), region, workplace)

    listings.sort(key=lambda listing: (
        listing.commute_minutes if listing.commute_minutes is not None else listing.subway_minutes + COMMUTE_UNKNOWN_WALK_MINUTES,
        listing.distance_km or 0,
    ))
    notes = reach.notes + trade_unselected_notes(unselected) + complex_building_notes(shown)
    if reach.unknown_times:
        notes.append('지하철 시간을 모르는 역은 --max-minutes 조건을 확인할 수 없어 제외했습니다')
    if len(stations) > len(searched):
        notes.append(
            f'지하철 {max_minutes}분 안에 갈 수 있는 역 {len(stations)}곳{" 이상" if reach.truncated else ""} 중 '
            f'가까운 {len(searched)}곳 주변만 찾았습니다. '
            '더 멀리 보려면 조건을 좁히거나 jibsa daangn search listings <역 이름> 으로 그 역 주변을 찾으세요'
        )
    groups: list[DaangnCommuteStationListings] = []
    # 역마다 같은 안내('더 보려면 --limit 을 늘리거나…')가 역 수만큼 되풀이되지 않게 안내 문장마다 역을 모은다
    station_notes: dict[str, list[str]] = {}
    for name, minutes, transfers in searched:
        station_listings = [listing for listing in listings if listing.commute_station == name]
        inspected = found.inspected_by_station[name]
        groups.append(DaangnCommuteStationListings(
            station_name=name, subway_minutes=minutes, transfers=transfers,
            inspected=inspected, returned=len(station_listings), listings=station_listings,
        ))
        for text in listing_budget_notes(limit, inspected, len(station_listings), has_more=found.has_more_by_station[name]):
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


# (역 이름, 지하철 시간, 환승)
_Station = tuple[str, int, int | None]


def _station_note(name: str, text: str) -> str:
    """역 이름을 붙인 안내. 종류 태그가 있으면 태그 뒤에 넣는다 (앞에 붙이면 태그를 못 알아봐 [참고] 가 또 붙는다)."""
    for kind in NOTE_KINDS:
        tag = f'[{kind}] '
        if text.startswith(tag):
            return f'{tag}{name}: {text.removeprefix(tag)}'
    return f'{name}: {text}'


class _Reachable(NamedTuple):
    """회사 역에서 지하철 시간 상한 안에 갈 수 있는 역 (`_reachable_stations`)."""

    stations: list[_Station]
    notes: list[str]
    # 지하철 시간을 모르는 역이 있었는지
    unknown_times: bool
    # 역 목록을 COMMUTE_FEED_MAX_PAGES 쪽까지 받고도 시간 상한 안 역이 남았는지
    truncated: bool


class _StationArticles(NamedTuple):
    """역마다 받은 매물 (`_station_articles`). 역 안에서는 중복을 제거하고, 역 사이에서는 같은 매물을 각각 유지한다."""

    stations_by_id: dict[str, list[_Station]]
    articles_by_id: dict[str, DaangnArticleModel]
    inspected_by_station: dict[str, int]
    has_more_by_station: dict[str, bool]


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
            hint='지하철역이 있는 위치로 다시 찾거나, jibsa daangn search listings 로 회사 주변 반경을 찾으세요',
        )
    nearest = unwrap_graphql(response, nearest, '가까운 역')
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
    """출퇴근 역 목록을 넘기며 지하철 `max_minutes` 분 안 역을 모은다. 회사 역 자체도 지하철 0분으로 넣는다.

    같은 역이 여러 경로로 오면 지하철 시간이 가장 짧은 경로를 쓰고, 가까운 순으로 정렬한다.
    """
    # (역 이름, 지하철 시간, 환승) — 회사 역 자체도 지하철 0분으로 넣는다
    stations: list[tuple[str, int, int | None]] = [(nearest.station_name, 0, 0)]
    feed_notes: list[str] = []
    unknown_station_times = False
    # 역 목록을 COMMUTE_FEED_MAX_PAGES 쪽까지 받고도 시간 상한 안 역이 남았는지
    feed_truncated = False
    after = None
    for _ in range(COMMUTE_FEED_MAX_PAGES):
        feed_response = client.run_request_commute_feed(
            DaangnCommuteFeedRequestPayloadModel(
                after=after,
                from_station_name=nearest.station_name,
                property_filter=property_filter,
            )
        )
        feed = unwrap_graphql(feed_response, feed_response.data.commute_feed if feed_response.data else None, '출퇴근 역')
        reachable = [edge.node for edge in feed.edges if edge.node and edge.node.station]
        unknown_station_times |= any(node.duration_minutes is None for node in reachable)
        stations += [
            (node.station.station_name, node.duration_minutes, node.transfer_count)
            for node in reachable
            if node.station and node.duration_minutes is not None and node.duration_minutes <= max_minutes
        ]
        page_info = feed.page_info
        if (
            not reachable
            or (reachable[-1].duration_minutes is not None and reachable[-1].duration_minutes > max_minutes)
            or page_info is None
            or not page_info.has_next_page
        ):
            break
        if not page_info.end_cursor or page_info.end_cursor == after:
            feed_notes.append('출퇴근 역의 다음 페이지 커서가 없거나 반복되어 조회를 중단했습니다')
            break
        after = page_info.end_cursor
    else:
        feed_truncated = True
        feed_notes.append(
            f'출퇴근 역 목록을 {COMMUTE_FEED_MAX_PAGES}쪽까지만 받아 지하철 '
            f'{min(max_minutes, COMMUTE_SERVER_MAX_MINUTES)}분 안 역이 더 있습니다. reachable_stations 는 받은 역까지만 센 수입니다'
        )
    if max_minutes > COMMUTE_SERVER_MAX_MINUTES:
        feed_notes.append(
            f'당근 출퇴근 지도는 지하철 {COMMUTE_SERVER_MAX_MINUTES}분 안 역까지만 줍니다. '
            f'--max-minutes {max_minutes} 이어도 {COMMUTE_SERVER_MAX_MINUTES}분까지의 역만 찾았습니다'
        )

    # 같은 역이 여러 경로로 오면 지하철 시간이 가장 짧은 경로를 쓴다.
    stations = list({station[0]: station for station in sorted(stations, key=lambda station: -station[1])}.values())
    stations.sort(key=lambda station: station[1])
    return _Reachable(stations, feed_notes, unknown_station_times, feed_truncated)


def _station_articles(
    client: DaangnClient,
    searched: list[_Station],
    property_filter: DaangnPropertyFilterModel,
    limit: int,
) -> _StationArticles:
    """역마다 주변 매물을 `limit` 건까지 받는다."""
    stations_by_id: dict[str, list[_Station]] = {}
    articles_by_id: dict[str, DaangnArticleModel] = {}
    inspected_by_station: dict[str, int] = {}
    has_more_by_station: dict[str, bool] = {}
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

        edges, has_more, _ = station_article_edges(fetch, limit)
        inspected_by_station[station[0]] = len(edges)
        has_more_by_station[station[0]] = has_more
        seen: set[str] = set()
        for edge in edges[:limit]:
            article = edge.node.article if edge.node else None
            if article is not None and article.original_id not in seen:
                seen.add(article.original_id)
                stations_by_id.setdefault(article.original_id, []).append(station)
                articles_by_id.setdefault(article.original_id, article)
    return _StationArticles(stations_by_id, articles_by_id, inspected_by_station, has_more_by_station)


def _commute_listings(
    client: DaangnClient,
    found: _StationArticles,
    conditions: DaangnListingConditions,
    center: tuple[float, float],
    region: DaangnRegion | None,
    workplace: DaangnCommuteStation,
) -> tuple[list[DaangnCommuteListing], list[DaangnArticleModel], int]:
    """받은 매물을 역마다 통근 시간을 붙인 매물로 바꾼다. 내보낸 원본 매물과, 거래 조건을 고르지 못해 뺀 수도 준다."""
    listings: list[DaangnCommuteListing] = []
    shown: list[DaangnArticleModel] = []
    sido_cache: dict[tuple[str, str], str | None] = {}
    # 서버 필터를 통과했지만 검색에 맞는 거래 조건을 고르지 못해 뺀 매물 수
    unselected = 0
    for article in found.articles_by_id.values():
        if not is_available(article):
            continue
        trade = trade_of(article, center, conditions)
        if trade is None:
            unselected += 1
            continue
        # 구 이름이 회사 동네와 같으면 같은 시·도로 본다. 지하철 시간이 짧은 역 COMMUTE_MAX_STATIONS 곳만 보므로
        # 이름이 같은 다른 시·도의 구(서울 중구·인천 중구)까지 닿지 않는다 (2026-10-10 실측: 시청역은
        # --max-minutes 90 이어도 6분 안 역 10곳에서 멈춘다)
        base = article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
        if base is None:
            continue
        shown.append(article)
        for station_name, subway_minutes, transfers in found.stations_by_id.get(article.original_id, []):
            walk = next(
                (
                    item.duration_minutes for item in article.subway_stations
                    if item.station and item.station.station_name == station_name
                ),
                None,
            )
            commute = None
            if walk is not None and workplace.walk_minutes is not None:
                commute = walk + subway_minutes + workplace.walk_minutes
            listings.append(listing_as(
                DaangnCommuteListing,
                base,
                commute_station=station_name,
                subway_minutes=subway_minutes,
                transfers=transfers,
                walk_to_station_minutes=walk,
                commute_minutes=commute,
            ))

    return listings, shown, unselected
