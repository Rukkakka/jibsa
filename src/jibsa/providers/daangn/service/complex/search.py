"""단지 이름 검색·지역·지도 범위 단지 목록 (search complexes)."""

from collections.abc import Callable

from jibsa.core.listing import (
    holding_unread_dates,
    keep_unread_dates,
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.common import (
    DaangnComplexFilterModel,
    DaangnExclusiveUseAreaModel,
)
from jibsa.providers.daangn.api.models.request.complex.search import (
    DaangnComplexByClusterIdInputModel,
    DaangnComplexByClusterIdRequestPayloadModel,
    DaangnSearchComplexesViewportInputModel,
    DaangnSearchComplexesViewportRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.complex.search import (
    DaangnRegionComplexesModel,
)
from jibsa.providers.daangn.service.common.complex import (
    complex_list_notes,
    region_complex_of,
)
from jibsa.providers.daangn.service.common.constants import (
    BUILDING_APPROVAL_FILTER_BY_LABEL,
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    POINT_ZOOM,
)
from jibsa.providers.daangn.service.common.location import map_view_bounds
from jibsa.providers.daangn.service.common.models import (
    DaangnRegionComplex,
    amount_range,
    label_codes,
)
from jibsa.providers.daangn.service.common.response import (
    cursor_stopped_note,
    next_cursor,
    stalled_page,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.complex.constants import (
    COMPLEX_PAGE_SIZE,
    COMPLEX_SORT_BY_LABEL,
    COMPLEX_TRADE_BY_TRADE_TYPE,
    DEFAULT_COMPLEX_TRADE_TYPE,
    MOVE_IN_SORT_NOTE,
)
from jibsa.providers.daangn.service.complex.models import (
    DaangnBoundsComplexesResult,
    DaangnComplexConditions,
    DaangnRegionComplexesResult,
)
from jibsa.providers.daangn.service.region.area import (
    region_or_none,
    resolve_realsale_region,
)


def complex_filter_of(conditions: DaangnComplexConditions) -> DaangnComplexFilterModel:
    """지역 단지 목록 조건을 웹 단지 탭 필터로 바꾼다.

    `propertyFilter.tradeType` 은 웹이 거래 유형 칩을 골랐을 때만 보낸다 (complexFilter 의 `p`: `tradeType: r.length>0 ? r : void 0`,
    기본 필터는 `tradeTypes: []`). jibsa 는 `--trade` 를 줬거나 가격 조건이 있을 때만 넣고, 보여 줄 실거래의 거래 유형은 최상위
    `tradeType`(기본 BUY)으로만 보낸다 (2026-11-12 번들 대조. 예전에는 기본 매매를 늘 필터에도 넣었다).
    """
    has_price = any(
        value is not None for value in (
            conditions.deposit_min, conditions.deposit_max, conditions.rent_min, conditions.rent_max,
            conditions.price_min, conditions.price_max,
        )
    )
    return DaangnComplexFilterModel(
        type=label_codes(conditions.complex_types, COMPLEX_TYPE_FILTER_BY_LABEL),
        trade_type=(
            [COMPLEX_TRADE_BY_TRADE_TYPE[conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE]]
            if conditions.trade_type is not None or has_price else None
        ),
        deposit=amount_range(conditions.deposit_min, conditions.deposit_max),
        monthly_pay=amount_range(conditions.rent_min, conditions.rent_max),
        price=amount_range(conditions.price_min, conditions.price_max),
        building_approval_date=label_codes(
            [conditions.building_approval] if conditions.building_approval else None, BUILDING_APPROVAL_FILTER_BY_LABEL,
        ),
        min_area=conditions.area_min,
        max_area=conditions.area_max,
        min_household_count=conditions.household_min,
        max_household_count=conditions.household_max,
        min_parking_per_household=conditions.parking_min,
    )



def has_complex_conditions(conditions: DaangnComplexConditions) -> bool:
    """사용자가 단지 조건을 하나라도 줬는지 (기본값 모델과 견준다). 에러 hint 가 조건을 줄이라고 권할지 정한다."""
    return conditions != DaangnComplexConditions()



def list_region_complexes(
    client: DaangnClient,
    query: str,
    *,
    conditions: DaangnComplexConditions | None = None,
    sort: str = '세대수',
    limit: int = 120,
) -> DaangnRegionComplexesResult:
    """동·구의 단지 목록을 정렬해 받는다 (웹 지도 단지 탭에서 지역 거품을 누른 목록, `complexByClusterId`).

    웹처럼 `REGION:<동·구 ID>` 클러스터로 부른다. 예전에는 동·구 ID 를 지도 범위 쿼리(`searchComplexes`)에 넣었는데 웹은 그렇게
    부르지 않는다. 결과는 같았다 (2026-11-12 실측: 역삼동 첫 50곳이 순서·커서까지 같음, #215). 단지마다 최근 실거래는 웹
    카드(1건)보다 많은 3건이다 (jibsa 개선, 2026-11-12 사용자 결정).

    지역은 `resolve_realsale_region` 으로 고른다 (동 또는 구). 조건은 웹 단지 탭 필터와 같고 당근
    서버에서 건다. 가격 조건은 지금 매물 가격이 아니라 단지의 과거 실거래 가격으로 거른다 (2026-10 역삼동
    실측: '월세 50 이하' 20곳 중 지금 월세 매물이 있는 곳은 7곳, 최근 실거래에 50 이하 월세가 있는 곳은 17곳).
    단지 유형 '아파트' 는 주상복합도 함께 찾고, 유형을 주지 않으면 도시형 생활주택도
    섞인다. `conditions.trade_type` 은 가격 조건과 단지마다 붙는 최근 실거래의 거래 유형이다. 면적 조건은 단지
    조건과 최근 실거래 면적에 함께 건다 (웹과 같다).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        FeedQueryRejectedError: 웹이 단지 목록 쿼리를 바꿨을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnComplexConditions()
    trade_type = conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE
    region, notes = resolve_realsale_region(client, query)
    complex_filter = complex_filter_of(conditions)
    filtered = has_complex_conditions(conditions)
    exclusive_use_area = _exclusive_use_area(conditions)

    def fetch(first: int, after: str | None) -> DaangnRegionComplexesModel:
        response = client.run_request_complex_by_cluster_id(
            DaangnComplexByClusterIdRequestPayloadModel(
                first=first,
                after=after,
                input=DaangnComplexByClusterIdInputModel(
                    cluster_id=f'REGION:{region.region_id}',
                    property_filter=complex_filter,
                    sort=COMPLEX_SORT_BY_LABEL[sort],
                ),
                trade_type=COMPLEX_TRADE_BY_TRADE_TYPE[trade_type],
                exclusive_use_area=exclusive_use_area,
            )
        )
        return unwrap_graphql(response, response.data.complex_by_cluster_id if response.data else None, '지역 단지 목록', conditions=filtered)

    complexes, has_more = _collect_complexes(fetch, trade_type, limit, sort, notes, narrow='지역·단지 유형·세대수·가격 조건')
    return DaangnRegionComplexesResult(
        region=region,
        trade_type=trade_type,
        sort=sort,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )



def _exclusive_use_area(conditions: DaangnComplexConditions) -> DaangnExclusiveUseAreaModel | None:
    """면적 조건을 단지마다 보여 줄 최근 실거래의 전용면적 범위로. 조건이 없으면 None (전체)."""
    if conditions.area_min is None and conditions.area_max is None:
        return None
    return DaangnExclusiveUseAreaModel(
        min=conditions.area_min or 0,
        **({'max': conditions.area_max} if conditions.area_max is not None else {}),
    )



def _collect_complexes(
    fetch: Callable[[int, str | None], DaangnRegionComplexesModel],
    trade_type: str,
    limit: int,
    sort: str,
    notes: list[str],
    *,
    narrow: str,
) -> tuple[list[DaangnRegionComplex], bool]:
    """단지 목록을 50곳씩 `limit` 곳까지 커서로 이어 받는다. 동·구 클러스터 목록과 지도 범위 목록이 함께 쓴다.

    받은 수로 예산을 세고 같은 단지는 한 번만 넣는다. 커서가 멈추면(`stalled_page`·`next_cursor`) 받은 것만 주고 알린다.

    Args:
        fetch: (받을 수, 커서) → 한 쪽.
        trade_type: 단지마다 붙는 최근 실거래의 거래 유형.
        limit: 최대 단지 수.
        sort: 정렬 라벨 (입주일 순이면 안내를 붙인다).
        notes: 안내를 덧붙일 목록.
        narrow: 더 남았을 때 좁히라고 권할 조건 (`more_hint`).

    Returns:
        (단지, 더 있는지).
    """
    complexes: list[DaangnRegionComplex] = []
    seen: set[str] = set()
    # 단지별로 못 읽은 날짜를 맡아 뒀다가 자른 뒤 남은 단지의 것만 안내에 센다
    held: dict[str, list[tuple[str, str]]] = {}
    after: str | None = None
    inspected = 0
    # 서버는 빈 edge(null)도 한 자리로 세므로 빼고 읽은 수를 받은 자리에 더한다
    null_edges = 0
    # 당근이 단지 ID 를 주지 않아 뺀 단지 수. 받은 수(inspected)에는 세어 예산은 그대로다
    no_id_count = 0
    has_more = False
    stopped = False
    while inspected < limit:
        connection = fetch(min(COMPLEX_PAGE_SIZE, limit - inspected), after)
        if stalled_page(connection.page_info, after):
            stopped = True
            break
        null_edges += connection.null_items('edges')
        inspected += len(connection.edges) + connection.null_items('edges')
        nodes = [edge.node for edge in connection.edges if edge.node]
        for node in nodes:
            if node.original_id is None:
                no_id_count += 1
                continue
            with holding_unread_dates() as dates:
                complex_ = region_complex_of(node, trade_type)
            if complex_.complex_id not in seen:
                seen.add(complex_.complex_id)
                complexes.append(complex_)
                held[complex_.complex_id] = dates
        page_info = connection.page_info
        has_more = bool(page_info and page_info.has_next_page)
        if inspected >= limit or not has_more:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 에 닿은 것이 아니라
        # --limit 을 늘려도 더 받지 못하니, 아래의 --limit 안내 대신 멈췄다고 알린다
        cursor = next_cursor(page_info, after, received=len(nodes))
        if cursor is None:
            stopped = True
            break
        after = cursor
    # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
    has_more = has_more or len(complexes) > limit
    complexes = complexes[:limit]
    for complex_ in complexes:
        keep_unread_dates(held[complex_.complex_id])
    if stopped:
        notes.append(note('일부', cursor_stopped_note('단지 목록', f'{len(complexes)}곳') + '. 지원되는 필터로 범위를 좁히세요'))
    elif has_more:
        # 멈추지 않고 더 남았으면 --limit 에 닿은 것이다 (루프는 inspected >= limit 일 때만 has_more 를 남기고 끝난다).
        # 같은 단지가 두 번 오면 한 번만 넣어 limit 보다 적을 수 있어, 숫자는 보여 준 수로 쓴다
        notes.append(note('일부', f'단지가 더 있어 앞 {len(complexes)}곳만 보여 줍니다. ' + more_hint(limit, COMPLEX_LIST_MAX_LIMIT, narrow)))
    if no_id_count:
        notes.append(note('제외', f'당근이 단지 ID 를 주지 않은 {no_id_count}곳은 뺐습니다'))
    if null_edges:
        notes.append(null_items_note('당근 지역 단지', null_edges))
    if sort.startswith('입주'):
        notes.append(MOVE_IN_SORT_NOTE)
    notes += complex_list_notes(complexes)
    return complexes, has_more



def list_bounds_complexes(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    zoom: int = POINT_ZOOM,
    conditions: DaangnComplexConditions | None = None,
    sort: str = '세대수',
    limit: int = 120,
) -> DaangnBoundsComplexesResult:
    """(`lat`, `lng`) 를 가운데에 둔 웹 지도 화면 범위의 단지 목록 (웹 지도 단지 탭의 '이 영역 단지', `searchComplexes`).

    웹은 지도 화면의 북동·남서 꼭짓점을 `input.locationFilter` 로 보내고 조건·정렬·거래 유형은 동·구 클러스터 목록과 같다
    (ComplexListPanel `Z`, 2026-11-12 번들 대조). 범위는 지도 범위 매물 목록과 같은 데스크톱 화면 계산(`map_view_bounds`)이고
    줌 기본도 좌표 매물 검색과 같은 15 다. 화면 가운데의 동(`region`)은 결과 표시용 덤 조회라 실패해도 단지는 돌려준다.

    Raises:
        FeedQueryRejectedError: 웹이 단지 목록 쿼리를 바꿨을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnComplexConditions()
    trade_type = conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE
    complex_filter = complex_filter_of(conditions)
    filtered = has_complex_conditions(conditions)
    exclusive_use_area = _exclusive_use_area(conditions)
    bounds, width_km, height_km = map_view_bounds(lat, lng, zoom)
    notes: list[str] = []

    def fetch(first: int, after: str | None) -> DaangnRegionComplexesModel:
        response = client.run_request_search_complexes_viewport(
            DaangnSearchComplexesViewportRequestPayloadModel(
                first=first,
                after=after,
                input=DaangnSearchComplexesViewportInputModel(
                    location_filter=bounds,
                    property_filter=complex_filter,
                    sort=COMPLEX_SORT_BY_LABEL[sort],
                ),
                trade_type=COMPLEX_TRADE_BY_TRADE_TYPE[trade_type],
                exclusive_use_area=exclusive_use_area,
            )
        )
        return unwrap_graphql(response, response.data.search_complexes if response.data else None, '지도 범위 단지 목록', conditions=filtered)

    complexes, has_more = _collect_complexes(fetch, trade_type, limit, sort, notes, narrow='범위(--zoom)·단지 유형·세대수·가격 조건')
    # 동 이름은 결과 표시에만 쓰여 못 찾아도 단지는 보여 준다. 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이 되면 첫 화면 실패를 삼킨다).
    # 단지가 없어도 찾는다. null 은 '모름' 이라 찾지 않고 null 을 주면 당근이 위치를 못 찾은 것으로 읽힌다 (2026-11-12 리뷰·실측:
    # 역삼동 좌표 세대수 99999 이상 0곳에 region null. 매물 지도 검색과 같다)
    region = region_or_none(client, lat, lng, notes=notes)
    return DaangnBoundsComplexesResult(
        region=region,
        zoom=zoom,
        width_km=width_km,
        height_km=height_km,
        trade_type=trade_type,
        sort=sort,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )
