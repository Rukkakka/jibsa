"""동 안 핫플레이스 (hot-places)."""
from jibsa.core.listing import (
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.common import REGION_INFO_PAGE_LIMIT
from jibsa.providers.dabang.api.models.request.neighborhood.hot_places import (
    DabangRegionInfoHotPlacesV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.neighborhood.hot_places import (
    DabangHotPlaceModel,
)
from jibsa.providers.dabang.service.common.constants import REGION_INFO_MAX_LIMIT
from jibsa.providers.dabang.service.common.models import DabangPage
from jibsa.providers.dabang.service.common.paging import (
    fetch_pages,
    region_info_list_notes,
)
from jibsa.providers.dabang.service.neighborhood.common import base_month
from jibsa.providers.dabang.service.neighborhood.constants import (
    HOT_PLACE_GUIDE_LABELS,
    HOT_PLACE_TYPE_BY_LABEL,
)
from jibsa.providers.dabang.service.neighborhood.models import (
    DabangHotPlace,
    DabangHotPlacesResult,
)
from jibsa.providers.dabang.service.region.models import DabangDong


def get_hot_places(client: DabangClient, dong: DabangDong, *, type_label: str, limit: int) -> DabangHotPlacesResult:
    """동 안 핫플레이스 (웹 동네정보 '핫플레이스', 30곳마다 요청 1회). 미쉐린·블루리본 가이드에 오른 식당을 다방 목록 순으로 준다.

    사진 주소는 내보내지 않는다.
    """
    place, gid = dong
    update_dates: list[str | None] = []

    def fetch(page: int) -> DabangPage[DabangHotPlaceModel] | None:
        result = client.run_request_region_info_hot_places_v5(DabangRegionInfoHotPlacesV5RequestParameterModel(
            region_gid=gid, type=HOT_PLACE_TYPE_BY_LABEL[type_label], page=page,
        )).result
        if result is None:
            return None
        update_dates.append(result.update_date)
        return DabangPage(result.list_ or [], result.total, bool(result.has_more), result.null_items('list_'))

    pages = fetch_pages(fetch, limit, page_size=REGION_INFO_PAGE_LIMIT, max_limit=REGION_INFO_MAX_LIMIT)
    places = [
        DabangHotPlace(
            name=row.restaurant_name, guide=HOT_PLACE_GUIDE_LABELS.get(row.type or ''),
            address=normalize_address(row.address or None),
            labels=row.label_list or [],
        )
        for row in pages.rows
    ]
    # 가이드 종류를 아직 고르지 않았을 때만 좁히라고 권한다
    narrow = '가이드 종류(--type 미쉐린·블루리본) 조건' if type_label == '전체' else None
    notes = region_info_list_notes(pages, limit, subject=f'{place.name} 핫플레이스', narrow=narrow)
    return DabangHotPlacesResult(
        region=place,
        type=type_label,
        basis="다방 동네정보 '핫플레이스': 미쉐린·블루리본 가이드에 오른 식당 (출처 미쉐린·블루리본)",
        base_month=base_month(update_dates),
        total=pages.total,
        returned=len(places),
        has_more=pages.has_more,
        places=places,
        notes=notes,
    )
