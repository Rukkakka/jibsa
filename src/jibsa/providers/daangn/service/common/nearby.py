"""당근 주변 매물 연결(edges) 이어 받기·가려진 위치 안내·도보 분."""

from collections.abc import (
    Callable,
    Sequence,
)

from jibsa.core.listing import (
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnPageInfoModel,
)
from jibsa.providers.daangn.service.common.response import next_cursor

from typing import (
    Generic,
    NamedTuple,
    Protocol,
    TypeVar,
)


_EdgeT_co = TypeVar('_EdgeT_co', covariant=True)


class DaangnListingNode(Protocol):
    """매물 목록 edge 의 node (`connection_edges`). 매물은 `article` 에 든다."""

    @property
    def article(self) -> object | None: ...


class DaangnListingEdge(Protocol):
    """매물 목록의 edge (`connection_edges`). node 가 null 이거나 node 의 `article` 이 null 인 edge 는 받은 항목으로 세지 않는다 (`next_cursor`)."""

    @property
    def node(self) -> DaangnListingNode | None: ...


EdgeT = TypeVar('EdgeT', bound=DaangnListingEdge)


class DaangnListingConnection(Protocol[_EdgeT_co]):
    """쪽마다 `edges`·`pageInfo` 를 주는 매물 목록 (`connection_edges`). 동·지도 범위 피드와 역·대학 주변 매물이 이 꼴이다."""

    @property
    def edges(self) -> Sequence[_EdgeT_co] | None: ...

    @property
    def page_info(self) -> DaangnPageInfoModel | None: ...

    def null_items(self, *names: str) -> int: ...


class ConnectionEdges(NamedTuple, Generic[EdgeT]):
    """`connection_edges` 가 이어 받은 매물 목록."""

    edges: list[EdgeT]
    # 서버에 더 있는지. 멈췄을 때(`stopped`)도 서버가 더 있다고 했으니 True 다
    has_more: bool
    # 다음 쪽 커서. 더 없거나 멈췄으면 None 이라 이어 받기(`--next`)를 내지 않는다
    cursor: str | None
    # 다음이 있다면서 빈 쪽·커서 없음·같은 커서 되풀이를 줘 멈췄는지 (`next_cursor`). 호출부가 `cursor_stopped_note` 로 알린다
    stopped: bool
    # 빼고 읽은 빈 edge(null) 수. 예산(`limit`)에는 받은 자리로 세었으므로, 받은 수를 예산과 견주는 호출부(출퇴근 역별 매물)는
    # `len(edges)` 에 더한다
    dropped: int


def connection_edges(
    fetch: Callable[[int, str | None], DaangnListingConnection[EdgeT]],
    limit: int,
    page_size: int,
    *,
    after: str | None = None,
    full_page_more: Callable[[list[EdgeT]], bool] | None = None,
    notes: list[str] | None = None,
) -> ConnectionEdges[EdgeT]:
    """매물 목록을 `page_size` 건씩 `limit` 건까지 이어 받는다. 동·지도 범위·역·대학 주변 목록과 출퇴근 역별 매물이 함께 쓴다.

    받은 edge 수(빼고 읽은 빈 edge 포함)로 예산을 세고 뺄 매물을 채우지 않는다. 다음이 있다면서 빈 쪽·커서 없음·같은 커서 되풀이를 주면 다른 목록처럼
    (`next_cursor`) 멈추고 `stopped` 로 알린다. 앞 쪽이 다음이 있다고 해서 이어 받은 쪽(`--next` 로 받은 첫 쪽도 포함)이
    페이지 정보나 edges 없이(null) 오면 그 쪽을 세지 않고 멈춘다. 목록 끝은 늘 hasNextPage=False 로 오므로(`next_cursor`) 응답이 바뀐
    것이고, 다른 목록의 `stalled_page` 와 같은 기준이다 (2026-11-19 리뷰·재현: 동 목록 둘째 쪽만 pageInfo null 로 바꾸니 40건·
    has_more false 로 '이 40건이 전부' 라고 했다. 그 동은 6584건). 첫 쪽(`after` 없음)의 페이지 정보가 null 이면 서버가 더 있다고
    한 적이 없어 끝으로 본다. 예전에는 그 커서를 그대로 돌려줘, 빈 쪽 뒤에도 같은 자리의 `next` 가 나와
    `--next` 로 따라가면 같은 빈 쪽·같은 `next` 가 되풀이됐다 (2026-11-12 리뷰. 실측 응답의 끝 쪽은 늘 hasNextPage=False 였다:
    역삼동 토지 매매 1만원 이하 0건은 edges 0·커서 없음·False). 예전에는 동·지도 범위 목록과 역·대학 주변 목록이 같은 반복문을
    따로 두었다 (2026-11-12 리뷰).

    Args:
        fetch: (받을 수, 커서) → 한 쪽.
        limit: 최대 매물 수.
        page_size: 한 번에 받을 수 (웹과 같은 크기나 서버가 한 번에 주는 최대).
        after: 이어 받기(`--next`)에서 시작할 커서. 없으면 처음부터.
        full_page_more: 쪽이 요청한 수만큼 찼는데 서버 `hasNextPage` 가 false 일 때 다음 쪽이 있는지 (지금까지 받은 edge 를
            받는다). 동 목록이 매물이 남았는데 false 를 줘서 쓴다 (`search_dong`). 없으면 서버 값을 따른다. 다음 쪽을 받기 전에
            물어, 더 없다는 것을 아는 호출부가 빈 쪽을 받지 않게 한다 (2026-11-12 리뷰: 예전에는 쪽이 꽉 차면 늘 다음 쪽을 받고
            끝난 뒤에 '더 있음' 을 바로잡아, 매물이 딱 20건인 동의 --limit 40 이 빈 쪽을 한 번 더 받았다).
        notes: 빈 edge(null)를 빼고 읽었으면 그 안내를 덧붙일 목록. 없으면 안내하지 않는다.

    Returns:
        받은 edge, 서버에 더 있는지, 다음 쪽 커서, 멈췄는지 (`ConnectionEdges`).
    """
    edges: list[EdgeT] = []
    cursor, has_more = after, False
    null_edges = 0

    def finish(more: bool, next_after: str | None, stopped: bool) -> ConnectionEdges[EdgeT]:
        if null_edges and notes is not None:
            notes.append(null_items_note('당근 매물', null_edges))
        return ConnectionEdges(edges, more, next_after, stopped, null_edges)

    # 예산은 받은 자리로 센다. 서버가 준 빈 edge(null)도 한 자리라, 빼고 읽은 자리를 다시 받아 채우지 않는다 (받은 수로 세고 버린
    # 것은 채우지 않는 limit 원칙. 단지 목록·단지 매물도 같다). 뺀 수는 `finish` 가 [제외] 로 알린다
    while len(edges) + null_edges < limit:
        size = min(page_size, limit - len(edges) - null_edges)
        page = fetch(size, cursor)
        page_info = page.page_info
        page_edges = page.edges
        # 이어 받은 쪽의 pageInfo·edges 가 null 이면 앞 쪽이 다음이 있다고 했는데 이 쪽을 주지 않은 것이라 같은 기준으로 멈춘다
        if cursor is not None and (page_info is None or page_edges is None):
            return finish(True, None, True)
        if page_edges is None:
            # 첫 쪽의 edges 가 null 이면 목록이 비었는지 모른다. 빈 목록으로 바꾸지 않고 응답이 바뀐 것으로 본다 (PARSE_ERROR).
            # 출퇴근 역별 매물은 이 전에 `_station_articles` 가 역 하나의 모름으로 받아 이곳에 오지 않는다
            raise ValueError('매물 목록의 첫 쪽에 edges 가 없습니다 (null)')
        edges += page_edges
        # 서버는 빈 edge(null)도 한 자리로 세어 `size` 만큼 준다. 빼고 읽은 수를 더해야 꽉 찬 쪽을 알아본다
        page_null_edges = page.null_items('edges')
        null_edges += page_null_edges
        server_more = bool(page_info and page_info.has_next_page)
        has_more = server_more or (
            full_page_more is not None and len(page_edges) + page_null_edges >= size and full_page_more(edges)
        )
        if not has_more:
            return finish(False, None, False)
        # 매물이 든 edge(`node.article` 이 있는 것)만 센다 (`next_cursor`). edge 수나 node 수를 넘기면 매물이 모두 null 인 쪽도 받은
        # 쪽으로 보아 멈추지 않고, 결과 0건에 이어 받기(next)가 나왔다 (2026-11-12 검증: 역삼역 역 주변 목록의 node 를 모두 null
        # 로 바꾼 실측 응답. 2026-11-19 리뷰·재현: node 는 있고 article 만 null 인 쪽도 같았다)
        received = sum(1 for edge in page_edges if edge.node is not None and edge.node.article is not None)
        cursor = next_cursor(page_info, cursor, received=received)
        if cursor is None:
            # 서버는 더 없다고 했는데 꽉 찬 쪽으로 짐작한 것(`full_page_more`)이면 커서가 없어도 멈춤이 아니라 끝이다
            return finish(server_more, None, server_more)
    return finish(has_more, cursor, False)


def hidden_location_notes(articles: list[DaangnArticleModel]) -> list[str]:
    """주소를 숨긴 매물의 `distance_km` 가 null 인 이유를 알린다 (`article_to_listing`). 매물은 빼지 않는다."""
    count = sum(1 for article in articles if article.is_hide_address)
    if not count:
        return []
    return [note(
        '참고',
        f'distance_km 가 null 인 {count}건은 작성자가 주소를 숨긴 매물이라 당근이 실제 위치가 아닌 좌표를 주어 거리를 모릅니다 '
        '(주소도 동까지만 공개)',
    )]


def walk_minutes_to(article: DaangnArticleModel, name: str) -> int | None:
    """매물 카드의 인근 역(`subwayStations`) 중 이름이 `name` 인 역까지 도보 (분). 그 역이 없으면 None.

    역 주변 매물(`search_station`, 찾은 역 이름)과 출퇴근 매물(`_commute_listings`, 출퇴근 경로의 역 이름)이 같이 쓴다. 예전에는
    두 곳이 같은 식을 따로 두었다 (2026-11-12 리뷰).

    리뷰 오탐 (2026-11-19, 근거 고침 2026-11-20): 인근 역은 이름으로 첫 일치만 쓴다 (`next(...)`). 서버는 같은 역을 이름 하나에
    노선 여럿으로 묶어 주므로 (인근 역 모델의 `line_number` 가 목록이다. 신촌역 사례) 한 역이 이름이 겹쳐 둘로 오지 않는다.
    이름이 같은 다른 역(양평역 5호선·경의중앙선)은 서로 멀어 한 매물 카드의 인근 역에 함께 오지 않을 것이라는 건 추론이다.
    덧붙임 근거: 2026-11-20 양평역 매물 171장에서 같은 이름이 두 번 나온 카드는 0장이었다.
    """
    return next(
        (item.duration_minutes for item in article.subway_stations if item.station and item.station.station_name == name),
        None,
    )
