"""단지 매물 목록 (search listings --complex)."""
from jibsa.core.errors import JibsaError
from jibsa.core.notes import limit_notes
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.common import (
    DabangAptFiltersModel,
    DabangOfficetelFiltersModel,
)
from jibsa.providers.dabang.api.models.request.complex.listings import (
    DabangComplexRoomFiltersModel,
    DabangRoomListCategoryComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.common import DabangRoomItemModel
from jibsa.providers.dabang.service.common.complex import fetch_complex
from jibsa.providers.dabang.service.common.constants import MAX_LIST_LIMIT
from jibsa.providers.dabang.service.common.models import (
    DabangListing,
    DabangListingConditions,
    DabangPage,
)
from jibsa.providers.dabang.service.common.paging import (
    duplicate_note,
    fetch_pages,
    fetch_stop_notes,
    narrow_again,
    room_list_page,
)
from jibsa.providers.dabang.service.common.room import (
    filters_of,
    premium_note,
    room_item_to_listing,
    unreadable_note,
)
from jibsa.providers.dabang.service.complex.common import category_of
from jibsa.providers.dabang.service.complex.constants import (
    COMPLEX_SORT_BY_LABEL,
    DEFAULT_COMPLEX_SORT,
    LISTING_KIND_BY_CATEGORY,
)
from jibsa.providers.dabang.service.complex.models.listings import (
    DabangComplexListingsResult,
)


def list_complex_listings(
    client: DabangClient,
    complex_id: str,
    *,
    conditions: DabangListingConditions | None = None,
    space_seqs: list[int] | None = None,
    sort: str = DEFAULT_COMPLEX_SORT,
    limit: int,
) -> DabangComplexListingsResult:
    """단지 하나의 매물 (`sort` 순, 24건씩). 요청은 단지 상세 1회 + 쪽마다 1회.

    Args:
        sort: 다방 웹 단지 매물 정렬 이름 (`COMPLEX_SORT_BY_LABEL`). 다방이 정렬한 순서를 다시 세우지 않는다.

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT),
        다방이 평형을 주지 않았는데 --pyeong 도 없을 때 (NOT_FOUND).
    """
    conditions = conditions or DabangListingConditions()
    result = fetch_complex(client, complex_id)
    category = category_of(result)
    kind = LISTING_KIND_BY_CATEGORY[category]
    # 다방이 평형 목록을 주지 않으면(None) 어떤 번호가 없는지 모르니 막지 않고 그대로 보낸다 (모르는데 '없다' 고 하지 않는다)
    all_seqs = None if result.spaces is None else [space.space_seq for space in result.spaces]
    unknown = [seq for seq in space_seqs or [] if all_seqs is not None and seq not in all_seqs]
    if unknown:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"이 단지에 없는 평형 번호입니다: {', '.join(map(str, unknown))}",
            hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 주세요',
        )
    # 단지 상세는 평형을 늘 하나 이상 준다 (2026-10-25 실측: 아파트·오피스텔·주상복합·재건축 62곳 모두). 요청은 평형 번호가
    # 하나 이상 있어야 해서, 평형을 안 주거나 비어 있고 --pyeong 도 없으면 보낼 번호가 없다
    seqs = space_seqs or all_seqs
    if not seqs:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방이 단지의 평형을 주지 않아 매물을 조회하지 못했습니다: {complex_id}',
            hint='평형 번호를 알면 --pyeong 으로 직접 주세요',
        )
    filters = filters_of(kind, conditions)
    assert isinstance(filters, DabangAptFiltersModel | DabangOfficetelFiltersModel)  # 단지는 아파트·오피스텔뿐이다
    room_filters = DabangComplexRoomFiltersModel(
        selling_type_list=filters.selling_type_list,
        space_seq_list=seqs,
    )
    order = COMPLEX_SORT_BY_LABEL[sort]
    premium = 0

    def fetch(page: int) -> DabangPage[DabangRoomItemModel] | None:
        nonlocal premium
        result = client.run_request_room_list_category_complex_v5(DabangRoomListCategoryComplexV5RequestParameterModel(
            category=category, complex_id=complex_id, main_filters=filters, filters=room_filters,
            order=order.order, page=page,
        )).result
        if result is None:
            return None
        page_rows, count = room_list_page(result)
        premium += count
        return page_rows

    # 쪽 수는 limit 을 24건으로 나눠 정하지 않고 limit 이 찰 때까지 받는다 (`fetch_pages`). 다방이 한 쪽을 23건만 줄 때가
    # 있어 다섯 쪽으로는 120건을 못 채울 수 있고, 단지 매물에는 이어 받기(--next)가 없어 남은 매물을 받을 길이 없다
    pages = fetch_pages(fetch, limit)
    total, has_more, received = pages.total, pages.has_more, len(pages.rows)
    listings: list[DabangListing] = []
    unreadable = duplicate = 0
    # 단지 목록(`search_complexes`)처럼 쪽이 겹칠 수 있어 같은 매물은 한 번만 넣는다. 다방 단지 매물은 적어 둘째 쪽을 실제로
    # 받아 보지 못했다 (2026-10-26 실측: 가장 많은 곳이 아파트 14건 잠실 우성4차·개포 현대2차, 오피스텔 8건 빅토리아)
    seen_ids: set[str] = set()
    for item in pages.rows:
        if item.id in seen_ids:
            duplicate += 1
            continue
        seen_ids.add(item.id)
        listing = room_item_to_listing(item, kind)
        if listing is None:
            unreadable += 1
            continue
        listings.append(listing)
    notes: list[str] = []
    notes += unreadable_note(unreadable)
    notes += duplicate_note(duplicate)
    notes += premium_note(premium)
    # 단지 하나라 지역·반경 대신 단지 매물의 조건만 좁히라고 한다
    narrow = '거래 유형·평형·가격 조건'
    notes += limit_notes(
        total, len(listings), limit, max_limit=MAX_LIST_LIMIT, order=order.text, narrow=narrow, inspected=received, has_more=has_more,
    )
    notes += fetch_stop_notes(pages, limit, cap_next=narrow_again(narrow))
    return DabangComplexListingsResult(
        complex_id=complex_id,
        name=result.complex.complex_name,
        pyeong_ids=space_seqs,
        sort=sort,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )
