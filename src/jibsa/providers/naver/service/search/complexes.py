"""지역 단지 목록 (search complexes)."""

from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    holding_unread_dates,
    join_address,
    keep_unread_dates,
    normalize_address,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
)
from jibsa.providers.naver.api.request.search.complexes import (
    NaverComplexBoundedComplexesV1RequestPayloadModel,
    NaverComplexLegalDivisionComplexListV1RequestPayloadModel,
    NaverComplexPagingRequestModel,
)
from jibsa.providers.naver.api.response.common import (
    NaverComplexListItemModel,
    NaverComplexListPageModel,
    NaverResponseModel,
)
from jibsa.providers.naver.service.common.constants import (
    COMPLEX_URL,
    TRADE_CODE_BY_NAME,
)
from jibsa.providers.naver.service.common.models import (
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
from jibsa.providers.naver.service.common.price import (
    complex_row_fields,
)
from jibsa.providers.naver.service.common.response import (
    unwrap,
)
from jibsa.providers.naver.service.search.common import (
    bounded_precision,
    filter_range,
)
from jibsa.providers.naver.service.search.constants import (
    AREA_COMPLEX_CODES_BY_TYPE,
    COMPLEX_EXCLUDED_REASON,
    COMPLEX_LIST_PAGE_SIZE,
    COMPLEX_LIST_SORT_TYPE_BY_NAME,
    COMPLEX_RADIUS_EXCLUDED_REASON,
    MAX_COMPLEX_LIST_PAGE_REQUESTS,
)
from jibsa.providers.naver.service.search.models import (
    NaverAreaComplex,
    NaverAreaComplexesResult,
)

from typing import (
    Any,
)


def _area_complex(item: NaverComplexListItemModel, center: tuple[float, float]) -> NaverAreaComplex | None:
    entry = item.complex or item.villa
    if entry is None:
        return None
    info = entry.complex_info or entry.villa_info
    if info is None:
        return None
    coordinates = info.address.coordinates if info.address else None
    address = None
    if info.address is not None:
        # 단지 목록의 sector 는 '서울시 강남구 역삼동' 처럼 시·구까지 붙어 온다 (단지 정보 API 는 동만)
        sector = info.address.sector or ''
        base = sector if ' ' in sector else join_address(info.address.city, info.address.division, sector)
        address = normalize_address(join_address(base, info.address.jibun))
    return NaverAreaComplex(
        complex_id=info.complex_number,
        name=info.name,
        address=address,
        distance_km=round(
            haversine_km(center[0], center[1], coordinates.y_coordinate, coordinates.x_coordinate), 2,
        ) if coordinates else None,
        url=COMPLEX_URL.format(info.complex_number),
        **complex_row_fields(
            type_code=info.type,
            households=info.total_household_number,
            dong_count=info.building_count,
            use_approval_date=info.use_approval_date,
            counts=entry.article_count_info,
            prices=entry.article_price_info,
        ),
    )


def list_area_complexes(
    client: NaverClient,
    lat: float,
    lng: float,
    *,
    radius_km: float = 1.0,
    legal_division_code: str | None = None,
    property_types: list[str] | None = None,
    sort: str = '인기순',
    listed_only: bool = True,
    household_min: int | None = None,
    household_max: int | None = None,
    building_age_min: int | None = None,
    building_age_max: int | None = None,
    limit: int = 30,
) -> NaverAreaComplexesResult:
    """지역 안 단지를 네이버 정렬 순서대로 모은다 (30곳에 1회, 최대 `MAX_COMPLEX_LIST_PAGE_REQUESTS` 회).

    `legal_division_code` 를 주면 그 법정동·시·군·구 안 단지 전체(legalDivisionComplexList), 아니면 반경을
    감싼 사각형 안 단지(boundedComplexes)에서 반경 밖을 뺀다. 코드가 시·군·구면 시·군·구 경계(GUN), 아니면 읍·면·동 경계(EUP)다
    (`boundary_filter`). 응답의 대표 사진과 주민 댓글 본문은 옮기지 않는다.

    Args:
        property_types: 단지 유형 (`AREA_COMPLEX_CODES_BY_TYPE` 의 이름). Defaults to 아파트.
        sort: 정렬 (`COMPLEX_LIST_SORT_TYPE_BY_NAME` 의 이름).
        listed_only: 매물이 있는 단지만 (사이트 '매물 있는 단지만'). 빌라 단지는 대부분 매물이 없다.
    """
    filter_ = NaverArticleFilterModel(
        trade_types=list(TRADE_CODE_BY_NAME.values()),
        real_estate_types=[code for name in property_types or ['아파트'] for code in AREA_COMPLEX_CODES_BY_TYPE[name]],
        has_article=listed_only,
        household_number=filter_range(household_min, household_max),
        approval_elapsed_year=filter_range(building_age_min, building_age_max),
    )
    if legal_division_code is not None:
        filter_ = boundary_filter(filter_, legal_division_code)
    sort_type = COMPLEX_LIST_SORT_TYPE_BY_NAME[sort]
    complexes: dict[int, NaverAreaComplex] = {}
    held_complexes: dict[int, list[tuple[str, str]]] = {}
    scan = PageScan(limit=limit, max_requests=MAX_COMPLEX_LIST_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverComplexListPageModel:
        paging = NaverComplexPagingRequestModel(size=size, complex_sort_type=sort_type, seed=seed, last_info=last_info or [])
        response: NaverResponseModel[NaverComplexListPageModel]
        if legal_division_code is not None:
            response = client.run_request_complex_legal_division_complex_list_v1(
                NaverComplexLegalDivisionComplexListV1RequestPayloadModel(filter=filter_, complex_paging_request=paging)
            )
        else:
            response = client.run_request_complex_bounded_complexes_v1(
                NaverComplexBoundedComplexesV1RequestPayloadModel(
                    filter=filter_, bounding_box=bounding_box(lat, lng, radius_km), precision=bounded_precision(radius_km),
                    complex_paging_request=paging,
                )
            )
        return unwrap(response, '단지 목록', hint=None)

    def keep(item: NaverComplexListItemModel) -> int | None:
        with holding_unread_dates() as dates:
            complex_ = _area_complex(item, (lat, lng))
        if complex_ is None:
            return None
        # 사각형 모서리(반경 밖) 단지는 뺀다. 좌표를 모르면 반경 안인지 알 수 없어 뺀다
        if complex_.complex_id not in complexes and (
            legal_division_code is not None or (complex_.distance_km is not None and complex_.distance_km <= radius_km)
        ):
            complexes[complex_.complex_id] = complex_
            held_complexes[complex_.complex_id] = dates
        return complex_.complex_id

    scan_pages(scan, fetch, keep, page_size=COMPLEX_LIST_PAGE_SIZE)
    total, inspected, truncated = scan.total, scan.received, scan.truncated

    result = list(complexes.values())[:limit]
    for complex_row in result:
        keep_unread_dates(held_complexes.get(complex_row.complex_id, ()))
    notes: list[str] = []
    area = area_scope(legal_division_code, radius_km)
    if truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 {inspected}곳까지만 훑었습니다. 단지가 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요',
        ))
    notes += pagination_notes(
        total, len(result), limit, inspected, subject='단지', truncated=truncated,
        excluded_reason=COMPLEX_EXCLUDED_REASON if legal_division_code is not None else COMPLEX_RADIUS_EXCLUDED_REASON,
        scope=area.scope, total_basis=area.total_basis, null_items=scan.null_items,
        stalled=scan.stopped_short(resumed=False), exhausted=scan.exhausted, narrow=area.narrow,
    )
    notes += scan_null_items_notes(scan, '네이버 지역 단지')
    return NaverAreaComplexesResult(total=total, returned=len(result), complexes=result, notes=notes)
