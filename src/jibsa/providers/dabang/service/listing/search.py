"""매물 검색 (search listings room·villa·officetel·apt)."""
from datetime import datetime

from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
    within_radius,
)
from jibsa.core.listing import (
    KST,
    NEXT_HINT,
    limit_notes,
    note,
    null_items_note,
    years_ago,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    DabangBboxModel,
    DabangSearchType,
)
from jibsa.providers.dabang.api.request.listing import (
    DabangRoomListCategoryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import DabangRoomItemModel
from jibsa.providers.dabang.service.common.bbox import bbox_of
from jibsa.providers.dabang.service.common.constants import (
    CATEGORY_BY_KIND,
    MAX_LIST_LIMIT,
    ZOOM_BY_SEARCH_TYPE,
    ListingKind,
)
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
    DabangListingConditions,
    DabangPage,
    DabangPlace,
)
from jibsa.providers.dabang.service.common.paging import (
    duplicate_note,
    fetch_pages,
    fetch_stop_notes,
    room_list_page,
)
from jibsa.providers.dabang.service.common.room import (
    filters_of,
    premium_note,
    room_item_to_listing,
    unreadable_note,
)
from jibsa.providers.dabang.service.listing.models import (
    DabangListPosition,
    DabangSearchResult,
)
from jibsa.providers.dabang.service.region.region import dong_bbox

from typing import NamedTuple


class _Target(NamedTuple):
    """다방에 물을 범위 (동 하나, 역 하나, 대학 하나, 지도 범위 하나)."""

    search_type: DabangSearchType
    code: str | None = None
    place_id: int | None = None
    bbox: DabangBboxModel | None = None




def search_listings(
    client: DabangClient,
    kind: ListingKind,
    place: DabangPlace,
    *,
    conditions: DabangListingConditions | None = None,
    limit: int,
    radius_km: float | None = None,
    resume: DabangListPosition | None = None,
) -> DabangSearchResult:
    """한 유형의 매물을 다방 목록 순으로 받는다. 조건은 모두 다방 서버가 거른다.

    찾는 방식은 위치에 따라 정한다: 동은 그 동 안(`region`), 역은 다방이 정한 역 반경(`subway`), 대학은 대학 둘레(`univ`),
    좌표나 `radius_km` 는 반경을 덮는 지도 범위(`bbox`)로 받고 반경 밖은 뺀다. 아파트는 동·대학 검색이 없어 동은 경계를 덮는
    지도 범위로 받아 그 동 매물만 남기고, 대학은 반경으로 찾는다.

    Args:
        place: 찾은 위치 (`resolve_places`, 좌표는 kind='point').
        limit: 받을 매물 수 (받은 수로 센다. 뺀 만큼 다시 채우지 않는다).
        radius_km: 반경 검색이면 반경 (km).
        resume: 이어 받기(`--next`)면 앞 결과의 `next_position`. 그 쪽의 남은 칸부터 받는다.
    """
    conditions = conditions or DabangListingConditions()
    resume = resume or DabangListPosition()
    center = (place.lat, place.lng)
    notes: list[str] = []
    keep_gids: frozenset[int] | None = None
    distance_center: tuple[float, float] | None = center
    filter_radius: float | None = None
    approximate = False
    bbox: DabangBboxModel | None = None
    if radius_km is None and place.kind == 'point':
        radius_km = DEFAULT_RADIUS_KM
    if radius_km is None and place.kind == 'university' and kind == 'apt':
        radius_km = DEFAULT_RADIUS_KM
        notes.append(note('범위', f'다방 아파트 목록은 대학 검색이 없어 {place.name} 반경 {radius_km:g}km 안을 찾았습니다'))
    if radius_km is not None:
        target = _Target('bbox', bbox=bbox_of(*box_around(place.lat, place.lng, radius_km)))
        filter_radius, approximate = radius_km, True
        scope = f'{place.name} 반경 {radius_km:g}km'
    elif place.kind == 'station':
        target = _Target('subway', place_id=place.place_id)
        if place.radius_m:
            radius_km = place.radius_m / 1000
        scope = f"{place.name} 다방 역 반경{f' {place.radius_m}m' if place.radius_m else ''}"
        notes.append(note('범위', f'{scope} 안을 찾았습니다 (반경을 정하려면 --radius)'))
    elif place.kind == 'university':
        target = _Target('univ', place_id=place.place_id)
        scope = f'{place.name} 둘레 (다방 대학 검색 범위)'
        notes.append(note('범위', f'{scope}를 찾았습니다 (반경을 정하려면 --radius)'))
    elif kind == 'apt':
        # 아파트 목록에는 동 검색이 없다 (403). 동 경계를 덮는 지도 범위로 받아 그 동 매물(동 번호)만 남긴다.
        # 사각형은 이어 받기 표에 남겨 --next 마다 동 경계(요청 1회)를 다시 받지 않는다
        bbox = resume.bbox or dong_bbox(client, place)
        target = _Target('bbox', bbox=bbox)
        keep_gids = frozenset({place.gid} if place.gid is not None else ())
        distance_center, approximate = None, True
        scope = f'{place.name} 안'
        notes.append(note('범위', f'{scope}을 찾았습니다. 다방 아파트 목록은 동 검색이 없어 동 경계를 덮는 사각형으로 받아 그 동 매물만 남겼습니다'))
    else:
        target = _Target('region', code=place.code)
        distance_center = None
        scope = f'{place.name} 안'
        notes.append(note('범위', f'{scope}을 찾았습니다 (반경으로 찾으려면 --radius)'))
    if conditions.built_within_years is not None:
        # 다방은 사용승인 날짜가 아니라 연도로 센다 (2026-10-31 실측: --built-within 2 에 2024-02-21 승인, 10 에 2016-02-03 승인
        # 건물이 들어오고 그 앞 해 승인은 없었다). 목록에 사용승인일이 없어 다시 거를 수 없으니 실제 기준 날짜를 알린다.
        # 날짜로 '10년 이내' 를 믿은 에이전트가 2016-10-17 승인 건물을 10년 이내로 추천했다. 연도 기준만 알리자 그 연도 기준을
        # 사용자의 '10년 이내' 로 받아 2016-02 승인 건물을 추천해(2026-10-31 재검증), 오늘 기준 날짜와 함께 알린다
        years = conditions.built_within_years
        today = datetime.now(KST).date()
        notes.append(note(
            '참고',
            f'다방은 사용승인 연도로 셉니다. --built-within {years} 결과에는 {today.year - years}-01-01 이후 승인이 모두 들어가, '
            f'오늘 기준 {years}년 이내({years_ago(today, years)} 이후 승인)가 아닌 건물도 섞입니다. 날짜로 고르려면 --details 의 '
            'approved_date 로 확인하세요',
        ))

    addresses = {place.gid: place.address} if place.gid is not None and place.address else {}
    filters = filters_of(kind, conditions)
    # 목록과 함께 온 광고(중개사별 추천 매물) 수
    premium = 0

    def fetch(number: int) -> DabangPage[DabangRoomItemModel] | None:
        nonlocal premium
        result = client.run_request_room_list_category_v5(DabangRoomListCategoryV5RequestParameterModel(
            category=CATEGORY_BY_KIND[kind],
            search_type=target.search_type,
            filters=filters,
            code=target.code,
            id=target.place_id,
            bbox=target.bbox,
            zoom=ZOOM_BY_SEARCH_TYPE[target.search_type],
            page=number,
        )).result
        if result is None:
            return None
        page, count = room_list_page(result)
        premium += count
        return page

    # 범위 하나에서 resume 쪽의 남은 칸부터(다방 목록 순) limit 건을 받는다 (쪽 따라가기는 fetch_pages)
    pages = fetch_pages(fetch, limit, page=resume.page, skip=resume.skip)
    collected: list[DabangListing] = []
    seen: set[str] = set()
    unreadable = outside = other_dong = duplicate = 0
    for item in pages.rows:
        if item.id in seen:
            duplicate += 1
            continue
        seen.add(item.id)
        if keep_gids is not None and item.gid not in keep_gids:
            other_dong += 1
            continue
        listing = room_item_to_listing(item, kind, center=distance_center, addresses=addresses)
        if listing is None:
            unreadable += 1
            continue
        # 반경 거르기는 거리를 아는 매물만 한다. 다방 목록은 좌표(randomLocation)를 늘 줘서 거리를 모르는 매물이 없다
        # (2026-10-25 실측: 지도 범위 5곳 452건 모두 있음)
        if filter_radius is not None and listing.distance_km is not None and not within_radius(listing.distance_km, filter_radius):
            outside += 1
            continue
        collected.append(listing)
    has_more = pages.has_more
    next_position = DabangListPosition(
        page=pages.page, skip=pages.skip, received=resume.received + len(pages.rows) + pages.dropped_used, bbox=bbox,
    ) if has_more else None
    # 더 받을 매물이 없으면 '다시 채우지 않음' 이라 하지 않는다. 그 말에 더 있는지 헷갈렸다 (2026-11-11 LLM 사용 시험: 반곡동
    # 아파트 7건 중 다른 동 4건을 빼고 has_more false)
    refill = '(뺀 만큼 다시 채우지 않음)' if has_more else '(더 받을 매물 없음)'
    if outside:
        notes.append(note('제외', f'반경을 덮는 사각형에서 받은 매물 중 반경 {filter_radius:g}km 밖 {outside}건을 뺐습니다 {refill}'))
    if other_dong:
        notes.append(note('제외', f'동 경계를 덮는 사각형에서 받은 매물 중 다른 동 {other_dong}건을 뺐습니다 {refill}'))
    notes += unreadable_note(unreadable)
    notes += duplicate_note(duplicate)
    notes += premium_note(premium)
    if pages.dropped:
        notes.append(null_items_note('다방 매물', pages.dropped))
    notes += limit_notes(
        pages.total, len(collected), limit, max_limit=MAX_LIST_LIMIT, narrow=f"조건·{'반경' if radius_km is not None else '지역'}",
        order='다방 목록', approximate=approximate, inspected=len(pages.rows), offset=resume.received,
        resumable=has_more, has_more=has_more,
    )
    notes += fetch_stop_notes(pages, limit, cap_next=NEXT_HINT, cut_next=NEXT_HINT)
    return DabangSearchResult(
        region=place,
        scope=scope,
        radius_km=radius_km,
        total=pages.total,
        returned=len(collected),
        has_more=has_more,
        next_position=next_position,
        listings=collected,
        notes=notes,
    )
