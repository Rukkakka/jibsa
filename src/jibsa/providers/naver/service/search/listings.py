"""지도 매물 검색 (search listings)."""

from jibsa.core.dates import keep_unread_dates
from jibsa.core.korean import is_district_code
from jibsa.core.listing import Listing
from jibsa.core.notes import note
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
)
from jibsa.providers.naver.api.models.request.search.common import (
    NaverArticlePagingRequestModel,
)
from jibsa.providers.naver.api.models.request.search.listings import (
    NaverArticleBoundedArticlesV1RequestPayloadModel,
    NaverArticleLegalDivisionArticleListV1RequestPayloadModel,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
)
from jibsa.providers.naver.service.common.constants import (
    ENTRANCE_CODE_BY_NAME,
    EXCLUDED_REASON,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    SEARCH_CODES_BY_PROPERTY,
    SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
    WON_PER_MANWON,
)
from jibsa.providers.naver.service.common.listing import (
    group_sort_notes,
    listing_keeper,
    price_sort_notes,
)
from jibsa.providers.naver.service.common.models import (
    NaverListingsResult,
    PageScan,
)
from jibsa.providers.naver.service.common.paging import (
    area_scope,
    boundary_filter,
    bounding_box,
    pagination_notes,
    scan_null_items_notes,
    scan_pages,
)
from jibsa.providers.naver.service.common.response import (
    unwrap,
)
from jibsa.providers.naver.service.search.common import (
    bounded_precision,
    filter_range,
)
from jibsa.providers.naver.service.search.constants import (
    BATHROOM_CODE_BY_NAME,
    BOUNDED_PAGE_SIZE,
    COMPLEX_FILTER_NOTE,
    DEFAULT_SEARCH_PROPERTY_TYPES,
    DIRECTION_FILTER_CODE_BY_NAME,
    ENTRANCE_FILTER_NOTE,
    ENTRANCE_WITH_COMPLEX_FILTER_NOTE,
    FACILITY_CODE_BY_NAME,
    FLOOR_CODE_BY_NAME,
    LEGAL_DIVISION_PAGE_SIZE,
    LOAN_CODE_BY_NAME,
    MAX_BOUNDED_PAGE_REQUESTS,
    MAX_LEGAL_DIVISION_PAGE_REQUESTS,
    MOVE_IN_CODE_BY_NAME,
    ONE_ROOM_SHAPE_NOTE,
    PARKING_CODE_BY_NAME,
    RADIUS_EXCLUDED_REASON,
    ROOM_COUNT_CODE_BY_NAME,
)
from jibsa.providers.naver.service.search.models.listings import NaverListingConditions

from typing import (
    Any,
)


def resume_cursor(position: dict[str, Any] | None) -> tuple[str | None, Any] | None:
    """이어 받기 위치에 담긴 (seed, lastInfo). 목록 처음부터면 None."""
    if not position or position.get('seed') is None and position.get('last_info') is None:
        return None
    return position.get('seed'), position.get('last_info')


def cursor_position(cursor: tuple[str | None, Any] | None) -> dict[str, Any]:
    """`resume_cursor` 가 되읽을 수 있게 (seed, lastInfo) 를 이어 받기 위치로 담는다."""
    if cursor is None:
        return {}
    return {'seed': cursor[0], 'last_info': cursor[1]}


def _search_listing_pages(
    client: NaverClient,
    lat: float,
    lng: float,
    *,
    radius_km: float,
    legal_division_code: str | None,
    filter_: NaverArticleFilterModel,
    sort_type: NaverArticleSortType,
    filter_notes: list[str],
    limit: int,
    start: dict[str, Any] | None = None,
) -> NaverListingsResult:
    """반경 안이나 법정동 안 매물을 네이버 정렬 순서 그대로 모은다 (30건에 1회).

    `legal_division_code` 를 주면 그 경계 안 목록(legalDivisionArticleList)이라 경계 안 매물만 오고 전체 수(`total`)도
    정확하다 (역삼동 4,401건 / 같은 중심 1km 사각형 7,803건, 2026-10-09). 코드는 읍·면·동이거나 시·군·구다
    (`boundary_filter` 가 코드로 단위를 정한다. 성동구 + GUN 도 같은 API·같은 나눔이다, 2026-11-18 실측). 거리(`distance_km`)는
    `lat`/`lng`(경계 중심)에서 잰 값이다. 목록 API 는 코드를 하나만 받는다 (2026-10-15 실측: 둘이면 400). 요청은
    `MAX_LEGAL_DIVISION_PAGE_REQUESTS` 회에서 멈춘다.

    아니면 지도 범위 목록(boundedArticles)이다. 서버는 반경을 감싼 사각형 안을 정렬해 주므로 반경 밖(모서리) 매물은
    뺀다. 제외된 수만큼 추가 조회하지 않는다. 좌표를 모르는 매물은 반경 안인지 알 수 없어 뺀다. 요청은
    `MAX_BOUNDED_PAGE_REQUESTS` 회에서 멈춘다.

    `start` 는 이어 받기 위치(목록 커서)다.
    """
    listings: dict[str, Listing] = {}
    held: dict[str, list[tuple[str, str]]] = {}
    by_boundary = legal_division_code is not None
    boundary_label = '시·군·구' if is_district_code(legal_division_code) else '동'
    if legal_division_code is not None:
        filter_ = boundary_filter(filter_, legal_division_code)
    box = None if by_boundary else bounding_box(lat, lng, radius_km)
    scan = PageScan(limit=limit, max_requests=MAX_LEGAL_DIVISION_PAGE_REQUESTS if by_boundary else MAX_BOUNDED_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel:
        paging = NaverArticlePagingRequestModel(size=size, article_sort_type=sort_type, seed=seed, last_info=last_info)
        if box is None:
            return unwrap(
                client.run_request_article_legal_division_article_list_v1(
                    NaverArticleLegalDivisionArticleListV1RequestPayloadModel(filter=filter_, article_paging_request=paging)
                ),
                f'{boundary_label} 매물 목록',
                hint=None,
            )
        return unwrap(
            client.run_request_article_bounded_articles_v1(
                NaverArticleBoundedArticlesV1RequestPayloadModel(
                    filter=filter_, bounding_box=box, precision=bounded_precision(radius_km), article_paging_request=paging,
                )
            ),
            '매물 목록',
            hint=None,
        )

    scan_pages(
        scan, fetch, listing_keeper(listings, (lat, lng), None if by_boundary else radius_km, held=held),
        page_size=LEGAL_DIVISION_PAGE_SIZE if by_boundary else BOUNDED_PAGE_SIZE, start=resume_cursor(start),
    )
    total, inspected, truncated = scan.total, scan.received, scan.truncated
    next_position = cursor_position(scan.cursor) or None

    result = list(listings.values())[:limit]
    for listing in result:
        keep_unread_dates(held.get(listing.id, ()))
    notes: list[str] = []
    area = area_scope(legal_division_code, radius_km)
    if truncated:
        notes.append(note(
            '일부',
            (
                f'네이버 차단을 피하려고 {boundary_label} 전체에서 {inspected}건까지만 '
                f'훑었습니다. 조건에 맞는 매물이 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요'
            ) if by_boundary else (
                f'네이버 차단을 피하려고 정렬 순서로 {inspected}건까지만 훑었습니다. '
                f'반경 안 매물이 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요'
            ),
        ))
    notes += filter_notes
    notes += pagination_notes(
        total, len(result), limit, inspected, truncated=truncated,
        excluded_reason=EXCLUDED_REASON if by_boundary else RADIUS_EXCLUDED_REASON,
        resumable=next_position is not None, resumed=start is not None,
        scope=area.scope, total_basis=area.total_basis, null_items=scan.null_items,
        stalled=scan.stopped_short(resumed=start is not None), exhausted=scan.exhausted, narrow=area.narrow,
    )
    notes += scan_null_items_notes(scan, '네이버 매물')
    # 멈추면 커서가 None 이라 next_position 도 None 이다. has_more 는 true 이고 next 는 없다 (CLI 는 next_position 이 있을 때만 next 를 붙인다)
    return NaverListingsResult(
        total=total, returned=len(result),
        has_more=next_position is not None or scan.stopped_short(resumed=start is not None), next_position=next_position,
        listings=result, notes=notes,
    )


def search_area(
    client: NaverClient,
    lat: float,
    lng: float,
    *,
    conditions: NaverListingConditions | None = None,
    radius_km: float = 1.0,
    sort: str = '랭킹순',
    legal_division_code: str | None = None,
    limit: int = 30,
    start: dict[str, Any] | None = None,
) -> NaverListingsResult:
    """좌표 반경 안이나 법정동·시·군·구 안의 매물을 네이버 정렬 순서 그대로 모은다.

    `legal_division_code` 를 주면 그 동·시·군·구 경계 안 목록, 아니면 반경을 감싼 사각형 안 목록에서 반경 밖 매물을 뺀다
    (`_search_listing_pages`). 둘 다 네이버 웹 지도의 매물 목록이 쓰는 API 이고, 네이버 정렬에는
    거리순이 없어 결과도 `distance_km` 순이 아니다. 받은 매물 수가 `limit` 에 닿거나 요청 상한에 닿으면 멈추고,
    받은 뒤 뺀 매물만큼 다시 채우지 않는다.

    조건은 모두 서버 필터로 보내 조건에 맞는 매물만 받고, 받은 뒤 다시 거르지 않는다
    (2026-10-10 실측: 가격 조건 4종 118건과 단지 매물 38건 모두 조건 안). 서버는 키 이름이 틀리면 조용히
    무시하므로, 필터 키를 바꿀 때는 원본 응답이 조건 안인지 live 테스트로 확인한다. 금액은 만원으로 받아 원으로 바꿔 보낸다.
    세대수·단지 주차는 단지로 등록된 매물에만 있어 주면 단지가 없는 빌라 대부분이 빠지고, 현관 구조는 등록되지 않은
    매물이 빠진다 (둘 다 `notes` 로 알린다).

    Args:
        conditions: 매물 조건 (`NaverListingConditions`). 비면 주거용 전체.
        sort: 정렬 (`SORT_TYPE_BY_NAME` 의 이름).
        legal_division_code: 법정동 코드. 주면 반경 대신 그 경계 전체를 찾고 `lat`/`lng` 는 거리 계산에만 쓴다.
        start: 이어 받기(`--next`) 위치로, 앞 결과의 `next_position` 이다. 결과의 `next_position` 은 더 받을 게 남았을 때만 있다.
    """
    conditions = conditions or NaverListingConditions()
    # 지도 매물 검색 조건을 네이버 매물 필터로 바꾼다. 금액은 원으로 바꿔 보낸다
    filter_ = NaverArticleFilterModel(
        # 비우면 단기임대(B3)까지 전체. 직방·당근과 같이 거래 유형을 주지 않으면 모두 보여 준다
        trade_types=[TRADE_CODE_BY_NAME[trade] for trade in conditions.trade_types or TRADE_CODE_BY_NAME],
        real_estate_types=[
            code
            for name in conditions.property_types or DEFAULT_SEARCH_PROPERTY_TYPES
            for code in SEARCH_CODES_BY_PROPERTY[name]
        ],
        is_authorized_by_owner=conditions.owner_verified_only,
        has_article_photo=conditions.photo_only,
        # 비우면 사각형 안 매물을 동과 무관하게 모두 준다. 좌표로 법정동을 몇 군데 찍어 채우면
        # 사각형에 걸쳤지만 찍히지 않은 동의 매물이 통째로 빠진다 (2026-10-07 확인)
        legal_division_numbers=[],
        # 가격 필터는 원 단위다
        deal_price=filter_range(conditions.price_min, conditions.price_max, WON_PER_MANWON),
        warranty_price=filter_range(conditions.deposit_min, conditions.deposit_max, WON_PER_MANWON),
        rent_price=filter_range(conditions.rent_min, conditions.rent_max, WON_PER_MANWON),
        management_fee=filter_range(conditions.manage_cost_min, conditions.manage_cost_max, WON_PER_MANWON),
        # 기본은 jibsa 의 area_m2 와 같은 전용면적. 공급이면 스위치를 꺼 더 큰 공급면적으로 비교한다
        space=filter_range(conditions.area_min, conditions.area_max),
        filters_exclusive_space=conditions.area_basis == '전용' and (
            conditions.area_min is not None or conditions.area_max is not None
        ),
        household_number=filter_range(conditions.household_min, conditions.household_max),
        approval_elapsed_year=filter_range(conditions.building_age_min, conditions.building_age_max),
        loan_ratio_type=LOAN_CODE_BY_NAME[conditions.loan] if conditions.loan else None,
        room_count=[ROOM_COUNT_CODE_BY_NAME[name] for name in conditions.room_types],
        bath_room_count=[BATHROOM_CODE_BY_NAME[name] for name in conditions.bathrooms],
        floor_types=[FLOOR_CODE_BY_NAME[name] for name in conditions.floors],
        direction_types=[DIRECTION_FILTER_CODE_BY_NAME[name] for name in conditions.directions],
        option_types=[FACILITY_CODE_BY_NAME[name] for name in conditions.facilities],
        one_room_shape_types=[ONE_ROOM_SHAPE_CODE_BY_NAME[name] for name in conditions.one_room_shapes],
        move_in_types=[MOVE_IN_CODE_BY_NAME[name] for name in conditions.move_in],
        parking_types=[PARKING_CODE_BY_NAME[name] for name in conditions.parking],
        entrance_types=[ENTRANCE_CODE_BY_NAME[name] for name in conditions.entrances],
        # 사이트처럼 하한 0 을 함께 보낸다 (역삼역 주변 오피스텔 월세 1062건 → 5분 이내 670건, 2026-10-08)
        walking_minute_to_subway_station=(
            filter_range(0, conditions.subway_minutes) if conditions.subway_minutes is not None else None
        ),
    )
    # 서버 필터가 특정 매물 유형을 통째로 빼는 조건은 notes 로 알린다 (결과는 다시 거르지 않는다)
    filter_notes: list[str] = []
    has_complex_filter = (
        conditions.household_min is not None or conditions.household_max is not None or bool(conditions.parking)
    )
    if has_complex_filter:
        filter_notes.append(COMPLEX_FILTER_NOTE)
    if conditions.entrances:
        filter_notes.append(ENTRANCE_WITH_COMPLEX_FILTER_NOTE if has_complex_filter else ENTRANCE_FILTER_NOTE)
    if conditions.one_room_shapes:
        filter_notes.append(ONE_ROOM_SHAPE_NOTE)
    sort_type = SORT_TYPE_BY_NAME[sort]
    # 경계 전체·반경 정렬 모두 같은 서버 가격순이다
    filter_notes += price_sort_notes(sort_type, conditions.trade_types)
    result = _search_listing_pages(
        client, lat, lng, radius_km=radius_km, legal_division_code=legal_division_code, filter_=filter_,
        sort_type=sort_type, filter_notes=filter_notes, limit=limit, start=start,
    )
    # 결과의 안내 맨 뒤('이 N건이 전부입니다' 등) 앞에 둘 필요가 없어 끝에 붙인다
    return result.model_copy(update={'notes': result.notes + group_sort_notes(sort_type, result.listings)})
