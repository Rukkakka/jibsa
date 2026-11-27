"""지역 안 단지 목록 (search complexes)."""
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
)
from jibsa.core.listing import (
    AmountSet,
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.common import (
    DabangAptFiltersModel,
    DabangBboxModel,
    DabangOfficetelFiltersModel,
    DabangSearchType,
)
from jibsa.providers.dabang.api.models.request.complex.search import (
    DabangComplexListCategoryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.complex.search import (
    DabangComplexListItemModel,
)
from jibsa.providers.dabang.service.common.bbox import bbox_of
from jibsa.providers.dabang.service.common.constants import (
    COMPLEX_KIND_BY_TYPE,
    MAX_LIST_LIMIT,
    ZOOM_BY_SEARCH_TYPE,
    ComplexKind,
)
from jibsa.providers.dabang.service.common.models import (
    DabangPage,
    DabangPlace,
)
from jibsa.providers.dabang.service.common.paging import (
    duplicate_note,
    fetch_pages,
    more_list_notes,
)
from jibsa.providers.dabang.service.common.text import (
    building_years,
    household_count,
    manwon_from_text,
)
from jibsa.providers.dabang.service.complex.constants import CATEGORY_BY_COMPLEX_KIND
from jibsa.providers.dabang.service.complex.models.search import (
    DabangComplexListResult,
    DabangComplexSummary,
)
from jibsa.providers.dabang.service.region.region import dong_bbox


def _summary(item: DabangComplexListItemModel) -> DabangComplexSummary:
    counts = item.room_count
    price = item.real_price
    sale = manwon_from_text(price.sale) if price else None
    lease = manwon_from_text(price.lease) if price else None
    return DabangComplexSummary(
        complex_id=item.complex_id,
        name=item.complex_name,
        complex_type=COMPLEX_KIND_BY_TYPE.get(item.complex_type or ''),
        occupancy_years=building_years(item.complex_desc),
        household_count=household_count(item.complex_desc),
        address=normalize_address(item.address),
        listing_count=counts.total_count if counts else None,
        listing_counts={
            'sale': counts.sell_count if counts else None,
            'jeonse': counts.lease_count if counts else None,
            'wolse': counts.monthly_rent_count if counts else None,
        },
        latest_trades={
            'sale': None if sale is None else AmountSet(price_manwon=sale),
            'jeonse': None if lease is None else AmountSet(deposit_manwon=lease),
        },
    )


def search_complexes(
    client: DabangClient,
    complex_kind: ComplexKind,
    place: DabangPlace,
    *,
    limit: int,
    radius_km: float | None = None,
) -> DabangComplexListResult:
    """지역 안 단지 목록 (다방 목록 순, 24곳씩). 조건 없이 그 범위의 단지를 모두 준다 (매물 없는 단지 포함).

    찾는 방식은 매물 검색과 같다. 아파트는 동·대학 검색이 없어 동은 경계를 덮는 사각형으로 받아 그 동 단지만 남긴다.
    """
    category = CATEGORY_BY_COMPLEX_KIND[complex_kind]
    filters = DabangAptFiltersModel() if category == 'apt' else DabangOfficetelFiltersModel()
    notes: list[str] = []
    keep_gids: frozenset[int] | None = None
    search_type: DabangSearchType
    code = place_id = None
    bbox: DabangBboxModel | None = None
    if radius_km is None and place.kind == 'point':
        radius_km = DEFAULT_RADIUS_KM
    if radius_km is None and place.kind == 'university' and category == 'apt':
        radius_km = DEFAULT_RADIUS_KM
        notes.append(note('범위', f'다방 아파트 단지 목록은 대학 검색이 없어 {place.name} 반경 {radius_km:g}km 를 덮는 사각형을 찾았습니다'))
    if radius_km is not None:
        south, north, west, east = box_around(place.lat, place.lng, radius_km)
        search_type, bbox, scope = 'bbox', bbox_of(south, north, west, east), f'{place.name} 반경 {radius_km:g}km (사각형)'
    elif place.kind == 'station':
        search_type, place_id, scope = 'subway', place.place_id, f'{place.name} 다방 역 반경'
    elif place.kind == 'university':
        # 여기 오는 것은 오피스텔뿐이다 (아파트 대학은 위에서 반경으로 바꾼다). 오피스텔 단지 목록은 대학 검색이 된다
        # (2026-10-26 실측: 홍익대학교 -t 오피스텔 정상, 403 은 아파트 단지 목록만)
        search_type, place_id, scope = 'univ', place.place_id, f'{place.name} 둘레'
    elif category == 'apt':
        # 아파트는 동 검색이 없다. 동 경계를 덮는 사각형으로 받아 그 동 단지만 남긴다
        search_type, bbox = 'bbox', dong_bbox(client, place)
        keep_gids = frozenset({place.gid} if place.gid is not None else ())
        scope = f'{place.name} 안'
    else:
        search_type, code, scope = 'region', place.code, f'{place.name} 안'

    def fetch(page: int) -> DabangPage[DabangComplexListItemModel] | None:
        result = client.run_request_complex_list_category_v5(DabangComplexListCategoryV5RequestParameterModel(
            category=category, search_type=search_type, filters=filters, code=code, id=place_id, bbox=bbox,
            zoom=ZOOM_BY_SEARCH_TYPE[search_type], page=page,
        )).result
        return None if result is None else DabangPage(result.list_, result.total, bool(result.has_more), result.null_items('list_'))

    # limit 은 받은 단지 수로 센다. 다른 동이라 뺀 단지만큼 다음 쪽을 더 받지 않는다 (매물 목록과 같다)
    pages = fetch_pages(fetch, limit)
    total, has_more, received = pages.total, pages.has_more, len(pages.rows)
    complexes: list[DabangComplexSummary] = []
    other_dong = duplicate = 0
    # 다방 단지 목록은 쪽마다 순서가 흔들려 앞 쪽 끝의 단지를 다음 쪽 첫머리에 다시 준다 (정렬 옵션이 없다). 2026-10-26 실측:
    # 잠실동 아파트 1쪽 23·24번째(신동아로쟌뷰·갤러리아팰리스)가 2쪽 1·2번째로 다시 와 3쪽까지 71줄 중 단지는 69곳이었다
    seen_ids: set[str] = set()
    for item in pages.rows:
        if item.complex_id in seen_ids:
            duplicate += 1
            continue
        seen_ids.add(item.complex_id)
        if keep_gids is not None and item.gid not in keep_gids:
            other_dong += 1
            continue
        complexes.append(_summary(item))
    if other_dong:
        notes.append(note('제외', f'동 경계를 덮는 사각형에서 받은 단지 중 다른 동 {other_dong}곳을 뺐습니다'))
    notes += duplicate_note(duplicate, what='단지', unit='곳')
    # 조건 옵션이 없어 범위만 권한다. 동은 지역을, 역·대학·좌표는 반경을 권한다. --radius 가 없어도 역은 다방이 정한 역
    # 반경·대학은 대학 둘레라 더 좁은 지역이 없고 --radius 로 좁힌다 (limit_notes 의 radius 설명, 분양 search_sales 와 같다.
    # 2026-11-11 리뷰·실측: 강남역 --limit 1 이 범위 '강남역 다방 역 반경' 에 '지역을 좁히세요')
    narrow = '반경' if radius_km is not None or place.kind != 'dong' else '지역'
    if has_more and received >= limit and keep_gids is not None and other_dong:
        # 동 검색은 동을 덮는 사각형의 다방 목록에서 그 동만 남겨, 늘려도 다른 동이 대부분이다. '지역을 좁히세요' 는 이미 동
        # 하나라 따를 수 없었고 total 도 사각형 안 수였다 (2026-11-11 LLM 사용 시험: 반포동 --limit 60 에 반포동 6곳, total 348).
        # 그 동 단지를 빠짐없이 주는 당근·네이버 동 단지 목록을 알린다
        grow = (
            '--limit 을 늘리면 더 보지만 다른 동이 대부분입니다. ' if limit < MAX_LIST_LIMIT
            else f'--limit 의 최대값은 {MAX_LIST_LIMIT}입니다. '
        )
        notes.append(note(
            '일부',
            f'단지가 더 있습니다 (동을 덮는 사각형의 다방 목록 순 앞 {received}곳 중 이 동 {len(complexes)}곳, total 은 사각형 안 수). '
            + grow + '동 안 단지를 빠짐없이 보려면 jibsa daangn search complexes <동> 이나 jibsa naver search complexes <동> 으로 찾으세요',
        ))
    else:
        # 위 가지는 받은 수가 limit 이상이라 멈춤 안내(`fetch_stop_notes`)와 함께 나오지 않는다
        # --limit 이 이미 최대값이면 늘리라고 하지 않는다 (2026-11-10 리뷰·실측: 역삼동 --limit 120 에 '--limit 을 늘리거나')
        notes += more_list_notes(
            pages, limit, seen=f'단지가 더 있습니다 (다방 목록 순 앞 {received}곳을 봤습니다)', max_limit=MAX_LIST_LIMIT,
            narrow=narrow,
        )
    return DabangComplexListResult(
        region=place, scope=scope, total=total, returned=len(complexes), has_more=has_more, complexes=complexes, notes=notes,
    )
