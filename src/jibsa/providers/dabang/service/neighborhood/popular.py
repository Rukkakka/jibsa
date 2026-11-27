"""동 안 인기 매물 (popular-listings)."""
from jibsa.core.listing import (
    Listing,
    limit_notes,
    listing_as,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.neighborhood.popular import (
    POPULAR_ROOM_PAGE_LIMIT,
    DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel,
)
from jibsa.providers.dabang.service.common.constants import (
    POPULAR_BUILDING_BY_LABEL,
    ListingKind,
)
from jibsa.providers.dabang.service.common.paging import more_after
from jibsa.providers.dabang.service.common.room import (
    room_item_to_listing,
    unreadable_note,
)
from jibsa.providers.dabang.service.neighborhood.constants import (
    POPULAR_KIND_BY_BUILDING,
    POPULAR_KIND_BY_ROOM_TYPE,
    POPULAR_MAX_LIMIT,
    POPULAR_PRICE_BY_TRADE,
)
from jibsa.providers.dabang.service.neighborhood.models.popular import (
    DabangPopularResult,
    DabangRankedListing,
)
from jibsa.providers.dabang.service.region.models import DabangDong


def get_popular_listings(
    client: DabangClient,
    dong: DabangDong,
    *,
    building_types: list[str],
    trade_types: list[str],
    limit: int,
) -> DabangPopularResult:
    """동 안 인기 매물 (다방 선호도 높은 순, 50건마다 요청 1회).

    매물 유형을 하나만 고르면 그 유형으로, 여럿이면 칸의 표시로 `property_type` 을 붙인다 (방 개수 표시는 빌라다).
    """
    place, gid = dong
    labels = building_types or list(POPULAR_BUILDING_BY_LABEL)
    kind: ListingKind | None = POPULAR_KIND_BY_BUILDING[labels[0]] if len(labels) == 1 else None
    listings: list[Listing] = []
    received = unreadable = dropped = 0
    total: int | None = None
    has_more = False
    page = 1
    # 다방은 (page - 1) × limit 번째부터 준다. 쪽마다 크기를 바꾸면 앞 쪽과 겹쳐 쪽 크기를 고정하고 넘치는 건 자른다
    # (2026-10-25 실측: 50건 다음 20건을 물으니 21~40위를 다시 줬다)
    page_size = min(POPULAR_ROOM_PAGE_LIMIT, limit)
    while received < limit:
        result = client.run_request_region_info_room_regional_popular_room_v5(
            DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel(
                region_gid=gid,
                building_category_list=[POPULAR_BUILDING_BY_LABEL[label] for label in labels],
                price_type_list=[POPULAR_PRICE_BY_TRADE[trade] for trade in trade_types or POPULAR_PRICE_BY_TRADE],
                limit=page_size,
                page=page,
            )
        ).result
        if result is None:
            break
        total = result.total if total is None else total
        rows = result.list_[:limit - received]
        # 이 쪽에서 빈 항목을 뺐으면 어느 자리가 빠졌는지 몰라 쪽 안 순위를 셀 수 없다 (다음 쪽은 쪽 번호로 세어 영향이 없다)
        page_dropped = result.null_items('list_')
        dropped += page_dropped
        for index, item in enumerate(rows):
            received += 1
            item_kind = kind or POPULAR_KIND_BY_ROOM_TYPE.get((item.room_type_name or '').partition('•')[0].strip(), 'villa')
            # 인기 매물 칸에는 동 번호(gid)가 없다 (모두 그 동 매물이다). 동 번호 자리 0 에 찾은 동 주소를 두어 주소를 채운다
            listing = room_item_to_listing(item, item_kind, addresses={0: place.address or place.name})
            if listing is None:
                unreadable += 1
                continue
            # 순위는 받은 수가 아니라 읽은 쪽과 칸으로 센다. 다방이 한 쪽을 덜 채워도 다음 쪽은 (page - 1) × 쪽 크기 번째부터라
            # 받은 수로 세면 그 뒤 순위가 앞으로 당겨진다
            listings.append(listing_as(
                DabangRankedListing, listing, rank=None if page_dropped else (page - 1) * page_size + index + 1,
            ))
        # 잘라 낸 줄이 있으면 더 있고, 빈 쪽이면 hasMore 가 와도 더 없다 (`more_after`)
        has_more = more_after(bool(result.has_more), len(result.list_), cut=len(result.list_) - len(rows))
        if not result.has_more or not result.list_:
            break
        page += 1
    notes: list[str] = []
    notes += unreadable_note(unreadable)
    if dropped:
        notes.append(null_items_note('다방 인기 매물', dropped, ('rank',)))
    # 동 하나(resolve_dong)의 순위라 좁힐 지역이 없어 이 명령의 -t·--trade 만 권한다 (2026-11-10 리뷰·실측: 역삼동 --limit 100
    # 600건에 '조건·지역을 좁히세요'). 이미 하나씩 골랐으면 더 좁힐 조건이 없어 권하지 않고, 한쪽만 골랐으면 다른 쪽만 권한다
    one_building = len(building_types or []) == 1
    one_trade = len(trade_types or []) == 1
    narrow = (
        None if one_building and one_trade
        else '거래 유형 조건' if one_building
        else '매물 유형 조건' if one_trade
        else '매물 유형·거래 유형 조건'
    )
    notes += limit_notes(
        total, len(listings), limit, max_limit=POPULAR_MAX_LIMIT, order='선호도 높은', narrow=narrow,
        inspected=received, has_more=has_more,
    )
    return DabangPopularResult(region=place, total=total, returned=len(listings), has_more=has_more, listings=listings, notes=notes)
