"""단기임대 매물 검색 (search listings stay)."""

from collections.abc import Callable

from httpx import HTTPStatusError

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.http import error_body
from jibsa.core.korean import is_ri_code
from jibsa.core.listing import (
    join_address,
    limit_notes,
    normalize_address,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.stay.common import (
    STAY_SEARCH_MAX_DAYS,
    STAY_SEARCH_MIN_DAYS,
    ZigbangGuestItemsByIdsRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.request.stay.search import (
    ZigbangGuestItemsMarkersRequestParameterModel,
    ZigbangGuestItemsSearchRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.response.stay.common import (
    ZigbangStayItemSummaryModel,
)
from jibsa.providers.zigbang.api.models.response.stay.search import (
    ZigbangStayMarkerModel,
)
from jibsa.providers.zigbang.service.common.constants import (
    MAX_LIST_LIMIT,
)
from jibsa.providers.zigbang.service.common.models import (
    ZigbangBoundary,
    ZigbangRegion,
)
from jibsa.providers.zigbang.service.region import (
    outside_boundary,
    scope_geohashes,
)
from jibsa.providers.zigbang.service.stay.common import (
    stay_summary_to_listing,
)
from jibsa.providers.zigbang.service.stay.constants import (
    STAY_BUILDING_TYPE_BY_LABEL,
    STAY_BY_IDS_BATCH_SIZE,
    STAY_DISCOUNT_TYPE_BY_LABEL,
    STAY_FLOOR_TYPE_BY_LABEL,
    STAY_GEOHASH_PRECISION,
    STAY_NARROW,
    STAY_OPTION_BY_LABEL,
    STAY_PERIOD_ERRORS,
    STAY_SERVER_SORTS,
    STAY_SORT_ORDERS,
    STAY_SORTS,
    STAY_SUBWAY_RADIUS_KM,
    StaySort,
)
from jibsa.providers.zigbang.service.stay.models.search import (
    ZigbangStayConditions,
    ZigbangStaySearchResult,
)

from typing import (
    Any,
    TypeVar,
)


StayResponse = TypeVar('StayResponse')
StayParameter = TypeVar('StayParameter')


def check_stay_sort(sort: str) -> StaySort:
    """단기임대 정렬 값을 검사해 돌려준다. CLI 는 지역을 찾기 전에 같은 검사로 막는다.

    Raises:
        JibsaError: `STAY_SORTS` 에 없는 값일 때 (INVALID_ARGUMENT).
    """
    if sort not in STAY_SORTS:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='지원하지 않는 단기임대 정렬입니다',
            hint=f"--sort {', '.join(STAY_SORTS)} 중 하나를 주세요",
        )
    return sort


def stay_distance_sort_error() -> JibsaError:
    """역 가까운 순(`distance`)을 역 이름 검색이 아닌 곳에 줬을 때의 에러. CLI 는 좌표·`--radius` 와 함께 준 것을 지역을 찾기
    전에, 서비스는 찾은 곳이 역이 아닌 것을 매물을 받기 전에 같은 에러로 막는다."""
    return JibsaError(
        code='INVALID_ARGUMENT',
        message='역 가까운 순(--sort distance)은 --radius 없이 역 이름으로 찾을 때만 됩니다',
        hint='--sort recommended·price·newest 중 하나를 쓰거나 --radius 없이 역 이름으로 검색하세요',
    )


def search_stay_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangStayConditions | None = None,
    sort: StaySort = 'recommended',
    radius_km: float = 1.0,
    limit: int = 20,
    boundary: ZigbangBoundary | None = None,
    use_search_api: bool = False,
    whole_address: bool = False,
) -> ZigbangStaySearchResult:
    """직방 단기임대를 웹 정렬(추천·낮은 가격·최근 등록·역 가까운 순)로 조회한다.

    직방 단기임대는 원룸·빌라의 '단기' 거래와 다른 별도 서비스(주 단위 계약, stay-apis)다.
    모든 조건(`conditions`)은 서버에서 거른다 (주당 요금은 만원). 라벨(오피스텔, 에어컨, 지하 ...)은 서버 코드로 바꿔 보낸다.
    두 경로 모두 받은 매물을 다시 거르거나 다시 세우지 않고, 고른 순서의 앞 `limit` 개만 요약(by-ids)을 받는다.

    - 검색 API (`use_search_api`: 역·학교·대학 이름, `whole_address` 인 동·구 이름): 웹 검색 결과 목록처럼 정렬을 서버에
      보내고(`guest/items/search`) 응답 ID 순서 그대로 낸다. 반경으로 자르지 않는다. 역은 직방이 역에서 약 1km 안을 주어
      `radius_km` 를 1 로 내고, 동·구는 동 경계가 아니라 이웃 동 매물이 섞여 와 `[범위]` 로 알린다. 리는 검색 API 가
      local3(그 위 읍·면)으로 찾아 `boundary` 를 읍·면 이름으로 낸다.
    - 지도 핀 (좌표·`--radius`·동 경계 `boundary`, 검색 API 가 받지 않는 지역): 반경(또는 동 경계)을 덮는 지도 칸의 핀 중
      범위 안만 남기고 웹 지도 목록처럼 핀 값으로 세운다 (`stay_marker_order`).

    역 가까운 순(`distance`)은 웹처럼 역 이름 검색(검색 API `type=subway`)에서만 된다.

    Raises:
        JibsaError: 역 이름 검색이 아닌데 `distance` 를 줬을 때 (INVALID_ARGUMENT, 매물 요청을 보내기 전에).
        RegionNotFoundError: 검색 API 가 지역을 찾지 못했을 때 (2026-10 의 세종의 동, `_search_stay_by_search_api`).
    """
    check_stay_sort(sort)
    if sort == 'distance' and not (use_search_api and region.search_type == 'subway'):
        # 직방 검색 API 는 역 검색이 아니면 400 STATION_SORT_REQUIRES_SUBWAY 를 주고, 웹 지도 목록도 역 기준점이 없으면
        # 추천순으로 바꾼다 (2026-11-15 실측·번들 `sortStayMarkers`)
        raise stay_distance_sort_error()
    conditions = conditions or ZigbangStayConditions()
    # 단기임대 조건을 지도 핀·검색 API 요청 필드로 바꾼다
    filters: dict[str, Any] = dict(
        weekly_price_min=conditions.weekly_price_min,
        weekly_price_max=conditions.weekly_price_max,
        room_count=conditions.room_count,
        building_types=[STAY_BUILDING_TYPE_BY_LABEL[label] for label in conditions.building_types],
        size_min_m2=conditions.area_min_m2,
        size_max_m2=conditions.area_max_m2,
        discount_types=[STAY_DISCOUNT_TYPE_BY_LABEL[label] for label in conditions.discounts],
        pet_allowed=conditions.pet_allowed or None,
        is_duplex=conditions.duplex,
        options=[STAY_OPTION_BY_LABEL[label] for label in conditions.options],
        has_parking=conditions.parking or None,
        has_elevator=conditions.elevator or None,
        floor_types=[STAY_FLOOR_TYPE_BY_LABEL[label] for label in conditions.floors],
        check_in_date=conditions.check_in,
        check_out_date=conditions.check_out,
        flexibility=conditions.flexibility,
    )
    # 이름으로 찾은 지역의 검색 API 요청. 검색 API 가 받지 않는 지역(좌표·시·도 없는 주소)이거나, 동·구인데 지역 검색으로
    # 찾으라는 표시(`whole_address`)가 없으면 지도 핀으로 찾는다
    context: ZigbangGuestItemsSearchRequestParameterModel | None = None
    if (
        use_search_api
        and region.search_type in {'address', 'subway', 'school', 'university'}
        and (region.search_type != 'address' or (region.local1 and whole_address))
    ):
        context = ZigbangGuestItemsSearchRequestParameterModel(
            type=region.search_type,
            sort=STAY_SERVER_SORTS[sort],
            local1=region.local1 if region.search_type == 'address' else None,
            local2=region.local2 if region.search_type == 'address' else None,
            local3=region.local3 if region.search_type == 'address' else None,
            lat=region.lat if region.search_type != 'address' else None,
            lng=region.lng if region.search_type != 'address' else None,
            **filters,
        )
    if context is not None:
        return _search_stay_by_search_api(client, region, context, conditions, sort=sort, limit=limit)
    return _search_stay_by_markers(
        client, region, filters, conditions, sort=sort, radius_km=radius_km, limit=limit, boundary=boundary,
    )


def _search_stay_by_search_api(
    client: ZigbangClient,
    region: ZigbangRegion,
    context: ZigbangGuestItemsSearchRequestParameterModel,
    conditions: ZigbangStayConditions,
    *,
    sort: StaySort,
    limit: int,
) -> ZigbangStaySearchResult:
    """검색 API 가 정렬해 준 ID 순서 그대로 앞 `limit` 개의 요약을 받는다. `total` 은 검색 ID 수다.

    by-ids 가 빼는 매물(그사이 내려간 매물)은 다시 채우지 않는다. 검색 ID 에는 위치가 없어 `distance_km` 는 요약 좌표로 잰다.
    """
    # 세종의 동은 local1·local2 를 어떻게 줘도 REGION_NOT_FOUND 였다 (2026-10-11 실측: 반곡동을 세종특별자치시·세종시 ×
    # 세종·없음·세종시 조합 모두 400, 세종특별자치시 전체·양평읍·역삼동·치평동은 200). 2026-11-10 에는 반곡동·어진동·나성동
    # 모두 local1=세종특별자치시·local2=세종 으로 200 이라 이 경로를 타지 않는다. 다시 막힐 수 있어 남겨 두며, 지역을 찾지 못했다는
    # 400 은 소스 장애(UPSTREAM_ERROR)로 보이지 않게 `RegionNotFoundError` 로 바꾸고 CLI 가 지도 칸(동 경계·반경) 검색으로
    # 다시 찾는다. 이 경로를 타면 직방이 바뀐 것이라 CLI 의 대체 경로 안내에 업데이트 문구가 붙는다.
    try:
        found_ids = _stay_search_call(client.run_request_guest_items_search, context).item_ids
    except HTTPStatusError as exc:
        body = _stay_400_body(exc)
        if body is None or body.get('error') != 'REGION_NOT_FOUND':
            raise
        # `normalize_address` 로 세종의 겹친 시 이름을 뺀다. 직방은 세종의 동을 local1 '세종특별자치시'·local2 '세종'·local3
        # '반곡동' 으로 줘서, 그대로 이으면(`join_address`) '세종특별자치시 세종 반곡동' 이 된다 (2026-11-10 리뷰·실측. 직방 지역
        # 검색의 주소는 '세종특별자치시 반곡동'). 앞 조각으로 시작하는 조각을 빼던 것을 `normalize_address` 로 바꿨다 (2026-11-11
        # 리뷰: local2 가 '세종시' 로 오면 빼지 못했다)
        raise RegionNotFoundError(
            normalize_address(join_address(context.local1, context.local2, context.local3)) or region.name,
            hint='--radius 로 반경 검색하세요',
        ) from None
    ids = list(dict.fromkeys(found_ids))
    head = ids[:limit]
    listings = [
        stay_summary_to_listing(
            summary,
            None if summary.lat is None or summary.lng is None else haversine_km(region.lat, region.lng, summary.lat, summary.lng),
        )
        for summary in _stay_summaries(client, head, conditions)
    ]
    has_more = len(ids) > len(head)
    address_scope = context.type == 'address'
    notes = limit_notes(
        len(ids), len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f"{STAY_NARROW}·{'지역' if address_scope else '반경'}",
        order=STAY_SORT_ORDERS[sort], inspected=len(head), has_more=has_more,
    )
    area = None
    if address_scope:
        area = region.local3 if is_ri_code(region.legal_division_code) and region.local3 else region.name
        notes.append(note(
            '범위', f'직방 단기임대 지역 검색 결과라 {area} 밖 이웃 동 매물이 섞일 수 있습니다 (매물의 address 로 동을 확인하세요)',
        ))
    elif context.type != 'subway':
        notes.append(note(
            '범위', '직방 단기임대 학교 검색 결과라 범위는 직방이 정하고 반경으로 자르지 않았습니다. 반경으로 찾으려면 --radius 를 주세요',
        ))
    return ZigbangStaySearchResult(
        region=region,
        radius_km=STAY_SUBWAY_RADIUS_KM if context.type == 'subway' else None,
        boundary=area,
        total=len(ids),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )


def _search_stay_by_markers(
    client: ZigbangClient,
    region: ZigbangRegion,
    filters: dict[str, Any],
    conditions: ZigbangStayConditions,
    *,
    sort: StaySort,
    radius_km: float,
    limit: int,
    boundary: ZigbangBoundary | None,
) -> ZigbangStaySearchResult:
    """반경(또는 동 경계) 안 지도 핀을 웹 지도 목록 순서로 세워 앞 `limit` 개의 요약을 받는다. `total` 은 범위 안 핀 수다."""
    # 지도 칸마다 단기임대 핀을 받아 매물 ID → (핀, 검색 중심에서 거리)로 모은다. 동 경계 밖 핀은 뺀다.
    # 핀 좌표는 요약(by-ids) 좌표와 같아 (2026-11-15 실측 71건) 핀으로 범위를 정하고 거리를 잰다. 핀 목록에서 빈 항목(null)을 빼고
    # 읽은 수를 함께 센다 (받은 칸 전부의 합).
    pins: dict[int, tuple[ZigbangStayMarkerModel, float]] = {}
    dropped = 0
    for geohash in scope_geohashes(region, radius_km, boundary, STAY_GEOHASH_PRECISION):
        response = _stay_search_call(
            client.run_request_guest_items_markers,
            ZigbangGuestItemsMarkersRequestParameterModel(geohash=geohash, **filters),
        )
        dropped += response.null_items('markers')
        for marker in response.markers:
            if outside_boundary(boundary, marker.lat, marker.lng):
                continue
            pins[marker.id] = (marker, haversine_km(region.lat, region.lng, marker.lat, marker.lng))
    if boundary is None:
        # 지도 칸은 반경보다 넓어 반경 밖 핀은 요약을 받지 않고 뺀다 (반올림 없이 잰 거리)
        pins = {item_id: pin for item_id, pin in pins.items() if pin[1] <= radius_km}
    head = stay_marker_order([marker for marker, _ in pins.values()], sort)[:limit]
    listings = [stay_summary_to_listing(summary, pins[summary.id][1]) for summary in _stay_summaries(client, head, conditions)]
    has_more = len(pins) > len(head)
    notes = limit_notes(
        len(pins), len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f"{STAY_NARROW}·{'지역' if boundary else '반경'}",
        order=STAY_SORT_ORDERS[sort], inspected=len(head), has_more=has_more,
    )
    if dropped:
        notes.append(null_items_note('직방 단기임대 지도 핀', dropped))
    return ZigbangStaySearchResult(
        region=region,
        radius_km=None if boundary else radius_km,
        boundary=boundary.name if boundary else None,
        total=len(pins),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )


def _marker_weekly_total_won(marker: ZigbangStayMarkerModel) -> int | float:
    """웹 지도 목록 가격순의 비교 값 (번들 `getWeeklyTotalPrice`). 핀이 준 주당 합계(원)가 있으면 그 값, 없으면 만원 단위 `weeklyPrice` 를 원으로."""
    if marker.weekly_total_price is not None:
        return marker.weekly_total_price
    return (marker.weekly_price or 0) * 10000


def stay_marker_order(markers: list[ZigbangStayMarkerModel], sort: StaySort) -> list[int]:
    """지도 핀을 웹 지도 목록 순서로 세운 매물 ID (번들 `sortStayMarkers`).

    추천순은 `totalScore` 높은 순, 같으면 ID 큰 순이다 (`compareRecommended`). 가격순은 `weeklyTotalPrice`(주당 임대료+관리비,
    원)가 숫자이면 그 값, 아니면 `weeklyPrice`(만원 미만 버림) × 10000 으로 낮은 순이고 (`getWeeklyTotalPrice`), 최신순은
    `reviewedAt` 늦은 순(문자열 비교)이다. 둘 다 같은 값이면 추천순 규칙을 따른다. 역 가까운 순은 역 기준점이 없으면 웹도
    추천순으로 바꾸는데, 지도 경로에서는 `search_stay_listings` 가 먼저 막는다. 값이 없으면 점수·가격은 0, 등록 시각은 가장
    이른 것으로 본다 (2026-11-19 실측: 핀 1,608개 모두 weeklyTotalPrice 가 있었고 weeklyPrice 는 그 값을 만원 미만 버린 것이었다).
    """
    # 정렬은 안정적이라(reverse=True 여도) 추천순으로 먼저 세운 뒤 기준 값으로 다시 세우면 같은 값끼리 추천순이 남는다
    ranked = sorted(markers, key=lambda marker: (-(marker.total_score or 0), -marker.id))
    if sort == 'price':
        ranked.sort(key=_marker_weekly_total_won)
    elif sort == 'newest':
        ranked.sort(key=lambda marker: marker.reviewed_at or '', reverse=True)
    return [marker.id for marker in ranked]


def _stay_summaries(
    client: ZigbangClient,
    item_ids: list[int],
    conditions: ZigbangStayConditions,
) -> list[ZigbangStayItemSummaryModel]:
    """매물 요약을 `item_ids` 순서대로 받는다. 응답에 없는 매물은 빠진다."""
    summaries: dict[int, ZigbangStayItemSummaryModel] = {}
    # 만료 단기임대는 by-ids 가 응답에서 뺀다 (비노출·REJECTED·PENDING·404 를 섞어 보내면 노출 중인 것만 온다).
    # 그래서 상세(get_stay_listing)처럼 status·checkStatus 를 다시 보지 않는다.
    for start in range(0, len(item_ids), STAY_BY_IDS_BATCH_SIZE):
        batch = item_ids[start:start + STAY_BY_IDS_BATCH_SIZE]
        response = _stay_search_call(
            client.run_request_guest_items_by_ids,
            ZigbangGuestItemsByIdsRequestParameterModel(
                item_ids=batch, check_in_date=conditions.check_in, check_out_date=conditions.check_out,
                flexibility=conditions.flexibility,
            ),
        )
        requested = set(batch)
        for summary in response.items:
            if summary.id in requested:
                summaries.setdefault(summary.id, summary)
    return [summaries[item_id] for item_id in item_ids if item_id in summaries]


def _stay_400_body(exc: HTTPStatusError) -> dict[str, Any] | None:
    """단기임대 API 가 400 으로 준 본문 객체 (`error` 코드·`message`). 400 이 아니거나 JSON 객체가 아니면 None."""
    return error_body(exc) if exc.response.status_code == 400 else None


def _stay_search_call(call: Callable[[StayParameter], StayResponse], parameter: StayParameter) -> StayResponse:
    """단기임대 검색 API 를 부르고, 기간이 허용 범위 밖이라는 400 은 입력 오류(INVALID_ARGUMENT)로 바꾼다."""
    try:
        return call(parameter)
    except HTTPStatusError as exc:
        body = _stay_400_body(exc)
        if body is None or body.get('error') not in STAY_PERIOD_ERRORS:
            raise
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 단기임대 검색 기간 오류: {body.get('message') or body.get('error')}",
            hint=(
                f'--check-in 부터 마지막으로 머무는 날 --check-out 까지 이용일로 세어 '
                f'{STAY_SEARCH_MIN_DAYS}~{STAY_SEARCH_MAX_DAYS}일로 주세요 (1주 = 11-02~11-08)'
            ),
        ) from None
