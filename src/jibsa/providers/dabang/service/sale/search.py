"""분양 단지 목록 (search sales)."""


from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
)
from jibsa.core.listing import (
    normalize_address,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.sale.search import (
    ALL_SALE_BUILDING_TYPES,
    ALL_SALE_STATES,
    ALL_SALE_SUPPLY_TYPES,
    SALE_BUILDING_TYPE_NUMBERS,
    SALE_SEARCH_PAGE_SIZE,
    SALE_STATE_NUMBERS,
    SALE_SUPPLY_TYPE_NUMBERS,
    DabangSaleInLotsFiltersModel,
    DabangSaleInLotsListSearch3V3RequestParameterModel,
    DabangSaleInLotsSearchFiltersModel,
    DabangSaleListCategoryBboxV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.sale.search import (
    DabangSaleInLotsItemModel,
    DabangSaleItemModel,
)
from jibsa.providers.dabang.service.common.bbox import bbox_of
from jibsa.providers.dabang.service.common.constants import MAX_LIST_LIMIT, SALE_URL
from jibsa.providers.dabang.service.common.models import (
    DabangPage,
    DabangPages,
    DabangPlace,
)
from jibsa.providers.dabang.service.common.paging import (
    fetch_pages,
    more_list_notes,
)
from jibsa.providers.dabang.service.common.text import (
    household_count,
    manwon_from_text,
)
from jibsa.providers.dabang.service.region.models import DabangScope
from jibsa.providers.dabang.service.region.region import (
    dong_bbox,
)
from jibsa.providers.dabang.service.sale.common import in_lots_fields
from jibsa.providers.dabang.service.sale.constants import (
    RENTAL_PRICE_KINDS,
    SALE_BUILDING_TYPE_BY_LABEL,
    SALE_STATE_BY_LABEL,
    SALE_SUPPLY_BY_LABEL,
)
from jibsa.providers.dabang.service.sale.models.search import (
    DabangSaleListResult,
    DabangSaleSummary,
)

from typing import (
    Any,
)


def _summary(item: DabangSaleItemModel) -> DabangSaleSummary:
    """지도 목록(`sale-list/category/bbox`)의 한 줄. 총세대수가 오지 않는다."""
    amount = manwon_from_text(item.price_title)
    return DabangSaleSummary(
        presale_id=item.id,
        name=item.building_name,
        status=item.state_name,
        complex_type=item.building_type_title,
        supply_type=item.supply_type_name,
        address=normalize_address(item.address),
        presale_household_count=household_count(item.household_num_title),
        price_kind=item.supply_price_type_name,
        **({'deposit_manwon': amount} if item.supply_price_type_name in RENTAL_PRICE_KINDS else {'price_manwon': amount}),
        next_schedule=item.schedule_title,
        url=SALE_URL.format(item.id),
    )


def _sale_list_notes(pages: DabangPages[Any], limit: int, *, in_box: bool, narrow_end: str) -> list[str]:
    """분양 목록(지도·지역)의 [일부] 안내.

    Args:
        in_box: 지도 목록(범위 사각형)이면 True. 다방이 센 수가 사각형 안 수라 '약' 을 붙인다.
        narrow_end: 좁히라고 권할 범위 ('반경' 또는 '지역').
    """
    total, received = pages.total, len(pages.rows)
    narrow = f'건물 유형·분양 상태·공급 유형 조건·{narrow_end}'
    among = f" {'약 ' if in_box else ''}{total}곳 중" if total is not None else ''
    # --limit 이 이미 최대값이면 늘리라고 하지 않고 좁힐 조건을 권한다 (2026-11-10 리뷰: --limit 120 에도 '--limit 을 늘리세요' 뿐)
    seen = f'범위 사각형 안 분양 단지{among} 다방 목록 순 앞 {received}곳을 봤습니다' if in_box else (
        f'분양 단지{among} 다방 목록 순 앞 {received}곳입니다'
    )
    dropped = [null_items_note('다방 분양 단지', pages.dropped)] if pages.dropped else []
    return dropped + more_list_notes(pages, limit, seen=seen, max_limit=MAX_LIST_LIMIT, narrow=narrow)


def search_sales(
    client: DabangClient,
    *,
    place: DabangPlace | None = None,
    scope: DabangScope | None = None,
    dong: DabangPlace | None = None,
    radius_km: float | None = None,
    building_types: list[str] | None = None,
    states: list[str] | None = None,
    supply_types: list[str] | None = None,
    limit: int,
) -> DabangSaleListResult:
    """분양 단지 (다방 목록 순, 24곳씩).

    전국·시·도·시·군·구(`scope`)는 웹 분양 지역 목록(`list/search3`)과 같은 주소로 받아 목록·순서·`total` 이 웹과 같다.
    동·역·대학·좌표는 지도 목록(`sale-list/category/bbox`)이다. 웹도 그 범위는 지도에서 본다. 지도 목록은 범위(사각형)만
    받아, 동은 경계를 덮는 사각형으로 받고 주소가 그 동인 단지만 남긴다 (분양 칸에는 좌표·동 번호가 없어 주소로 본다).
    역·대학·좌표는 반경을 덮는 사각형이다 (좌표가 없어 반경 밖을 뺄 수 없다). 추천 칸(지도 목록 `recommendList`, 지역 목록
    `features`)은 웹 목록에 없어 넣지 않는다.

    Args:
        place: 역·대학·좌표 (반경 사각형).
        scope: 전국·시·도·시·군·구 (지역 목록).
        dong: 동 (경계 사각형).
    """
    if scope is not None:
        # 지역 목록 필터. 고르지 않은 항목은 웹 초기값처럼 빈 목록(전체)으로 보낸다
        region_filters = DabangSaleInLotsSearchFiltersModel(
            building_type=[SALE_BUILDING_TYPE_NUMBERS[SALE_BUILDING_TYPE_BY_LABEL[label]] for label in building_types or []],
            state=[SALE_STATE_NUMBERS[SALE_STATE_BY_LABEL[label]] for label in states or []],
            supply_type=[SALE_SUPPLY_TYPE_NUMBERS[SALE_SUPPLY_BY_LABEL[label]] for label in supply_types or []],
        )
        return _search_region_sales(client, scope, region_filters, limit)
    notes: list[str] = []
    prefixes: list[str] = []
    if dong is not None:
        bbox = dong_bbox(client, dong)
        prefixes = [dong.address or dong.name]
        scope_name = f'{dong.name} 안'
    else:
        assert place is not None  # CLI 가 셋 중 하나를 준다
        radius = radius_km or DEFAULT_RADIUS_KM
        bbox = bbox_of(*box_around(place.lat, place.lng, radius))
        scope_name = f'{place.name} 반경 {radius:g}km (사각형)'
    filters = DabangSaleInLotsFiltersModel(
        building_type_list=[SALE_BUILDING_TYPE_BY_LABEL[label] for label in building_types or []] or list(ALL_SALE_BUILDING_TYPES),
        state_list=[SALE_STATE_BY_LABEL[label] for label in states or []] or list(ALL_SALE_STATES),
        supply_type_list=[SALE_SUPPLY_BY_LABEL[label] for label in supply_types or []] or list(ALL_SALE_SUPPLY_TYPES),
    )

    def fetch(page: int) -> DabangPage[DabangSaleItemModel] | None:
        result = client.run_request_sale_list_category_bbox_v5(
            DabangSaleListCategoryBboxV5RequestParameterModel(filters=filters, bbox=bbox, page=page)
        ).result
        if result is None:
            return None
        return DabangPage(result.sale_list, result.total, bool(result.has_more), result.null_items('sale_list'))

    # 쪽 수는 limit 을 24건으로 나눠 정하지 않고 limit 이 찰 때까지 받는다 (`fetch_pages`). limit 은 받은 단지 수로 센다
    pages = fetch_pages(fetch, limit)
    sales: list[DabangSaleSummary] = []
    outside = 0
    for item in pages.rows:
        address = normalize_address(item.address) or ''
        if prefixes and not any(address == prefix or address.startswith(f'{prefix} ') for prefix in prefixes):
            outside += 1
            continue
        sales.append(_summary(item))
    if outside:
        notes.append(note('제외', f'경계를 덮는 사각형에서 받은 단지 중 주소가 다른 {outside}곳을 뺐습니다 (뺀 만큼 다시 채우지 않음)'))
    # 역·대학·좌표(place)는 반경 사각형이라 반경을, 동은 지역을 좁히라고 한다
    notes += _sale_list_notes(pages, limit, in_box=True, narrow_end='반경' if place is not None else '지역')
    return DabangSaleListResult(
        scope=scope_name, total=pages.total, returned=len(sales), has_more=pages.has_more, presales=sales, notes=notes,
    )


def _search_region_sales(
    client: DabangClient, scope: DabangScope, filters: DabangSaleInLotsSearchFiltersModel, limit: int,
) -> DabangSaleListResult:
    """전국·시·도·시·군·구 안 분양 단지 (웹 분양 지역 목록 `list/search3`, 24곳씩). 거르지 않고 다방 목록 그대로 낸다.

    웹은 시·군·구를 고르면 시·도 코드와 시·군·구 코드를 함께 보낸다 (2026-11-13 캡처: 강남구 `state_code=11&city_code=11680`).
    두 값은 범위를 찾은 시·도 목록·시·군·구 목록(`resolve_scope`)의 `code` 다. 웹 지역 고르기도 같은 목록의 값을 보낸다.
    """
    state_code = scope.state_code if scope.kind in ('state', 'district') else None
    city_code = scope.code if scope.kind == 'district' else None
    recommended = 0

    def fetch(page: int) -> DabangPage[DabangSaleInLotsItemModel]:
        nonlocal recommended
        result = client.run_request_sale_in_lots_list_search3_v3(DabangSaleInLotsListSearch3V3RequestParameterModel(
            page=page, state_code=state_code, city_code=city_code, filters=filters,
        ))
        if page == 1:
            recommended = len(result.features or [])
        # 줄 목록이 null 이면 빈 쪽이라 거기서 멈춘다
        return DabangPage(
            result.sale_in_lotses or [], result.total, bool(result.has_more), result.null_items('sale_in_lotses'),
        )

    # 지역 목록의 쪽 크기는 분양 검색 요청의 값이다 (지도 목록은 매물 목록과 같은 기본값)
    pages = fetch_pages(fetch, limit, page_size=SALE_SEARCH_PAGE_SIZE)
    notes: list[str] = []
    if recommended:
        notes.append(note('제외', f'다방 추천 칸(features) {recommended}곳은 웹 분양 목록에 없어 넣지 않았습니다'))
    notes += _sale_list_notes(pages, limit, in_box=False, narrow_end='지역')
    return DabangSaleListResult(
        scope=scope.name if scope.kind == 'national' else f'{scope.name} 안', total=pages.total, returned=len(pages.rows),
        has_more=pages.has_more, presales=[
            DabangSaleSummary(
                presale_id=item.id, name=item.building_name, **in_lots_fields(item), next_schedule=item.title, url=SALE_URL.format(item.id),
            )
            for item in pages.rows
        ],
        notes=notes,
    )
