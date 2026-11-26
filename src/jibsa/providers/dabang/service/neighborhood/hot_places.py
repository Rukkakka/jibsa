"""동 안 핫플레이스 (hot-places)."""
from jibsa.core.listing import (
    normalize_address,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import REGION_INFO_PAGE_LIMIT
from jibsa.providers.dabang.api.request.neighborhood.hot_places import (
    DabangHotPlaceType,
    DabangRegionInfoHotPlacesV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.neighborhood.hot_places import (
    DabangHotPlaceModel,
)
from jibsa.providers.dabang.service.common.functions import (
    REGION_INFO_MAX_LIMIT,
    DabangPage,
    fetch_pages,
    region_info_list_notes,
)
from jibsa.providers.dabang.service.neighborhood.base import _base_month
from jibsa.providers.dabang.service.neighborhood.models import (
    DabangHotPlace,
    DabangHotPlacesResult,
)
from jibsa.providers.dabang.service.region.functions import DabangDong


# 핫플레이스 가이드 고르기 (웹 이름표 → 요청 값, hot-place 청크 2026-11-13)와 줄의 가이드 이름표
HOT_PLACE_TYPE_BY_LABEL: dict[str, DabangHotPlaceType] = {'전체': 'ALL', '미쉐린': 'MICHELIN_GUIDE', '블루리본': 'BLUE_RIBBON'}
HOT_PLACE_GUIDE_LABELS: dict[str, str] = {value: label for label, value in HOT_PLACE_TYPE_BY_LABEL.items() if value != 'ALL'}


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
        base_month=_base_month(update_dates),
        total=pages.total,
        returned=len(places),
        has_more=pages.has_more,
        places=places,
        notes=notes,
    )
