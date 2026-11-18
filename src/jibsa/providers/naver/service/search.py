"""지도 매물 검색과 지역 단지 목록 (search listings, search complexes)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    Listing,
    join_address,
    normalize_address,
    normalize_date,
    note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverArticleFilterModel,
    NaverArticleSortType,
    NaverDirectionType,
    NaverFloorType,
    NaverLoanRatioType,
    NaverMoveInType,
    NaverOptionType,
    NaverParkingType,
    NaverRangeModel,
    NaverRealEstateType,
    NaverRoomCount,
)
from jibsa.providers.naver.api.request.search import (
    NaverArticleBoundedArticlesV1RequestPayloadModel,
    NaverArticleLegalDivisionArticleListV1RequestPayloadModel,
    NaverArticlePagingRequestModel,
    NaverComplexBoundedComplexesV1RequestPayloadModel,
    NaverComplexLegalDivisionComplexListV1RequestPayloadModel,
    NaverComplexPagingRequestModel,
    NaverComplexSortType,
)
from jibsa.providers.naver.api.response.common import (
    NaverArticlePageModel,
    NaverComplexListAddressModel,
    NaverComplexListItemModel,
    NaverComplexListPageModel,
    NaverResponseModel,
)
from jibsa.providers.naver.service.common import (
    ENTRANCE_CODE_BY_NAME,
    EXCLUDED_REASON,
    ONE_ROOM_SHAPE_CODE_BY_NAME,
    PROPERTY_NAME_BY_CODE,
    RADIUS_EXCLUDED_REASON,
    SEARCH_CODES_BY_PROPERTY,
    SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
    WON_PER_MANWON,
    NaverListingsResult,
    NaverTradeConditions,
    PageScan,
    area_scope,
    bounded_precision,
    bounding_box,
    complex_url,
    cursor_position,
    dong_filter,
    group_sort_notes,
    listing_keeper,
    pagination_notes,
    price_sort_notes,
    resume_cursor,
    scan_pages,
    trade_article_counts,
    unwrap,
    won_to_manwon_range,
)

from typing import (
    Annotated,
    Any,
)


# 유형을 주지 않으면 주거용 전체 (재건축·분양권·재개발·비주거는 빼고).
DEFAULT_SEARCH_PROPERTY_TYPES: tuple[str, ...] = ('아파트', '오피스텔', '빌라', '원룸', '단독·다가구', '전원주택', '상가주택')
# 지도 필터 코드. 방 수는 방 구조 이름(`Listing.room_type`)으로 받되 원룸은 방 1개 전체(오픈형·분리형·복층형)다.
# 코드는 fin.land 지도 URL 과 매물 수·상세 대조로 확인했다 (2026-10-08).
ROOM_COUNT_CODE_BY_NAME: dict[str, NaverRoomCount] = {
    '원룸': 'RCF01',
    '투룸': 'RCF02',
    '쓰리룸': 'RCF03',
    '포룸이상': 'RCF04',
}
FLOOR_CODE_BY_NAME: dict[str, NaverFloorType] = {
    '1층': 'FLF01',
    '저층': 'FLF02',
    '중층': 'FLF03',
    '고층': 'FLF04',
    '탑층': 'FLF05',
    '지하층': 'FLF06',
}
DIRECTION_FILTER_CODE_BY_NAME: dict[str, NaverDirectionType] = {
    '동향': 'EE',
    '서향': 'WW',
    '남향': 'SS',
    '북향': 'NN',
    '북동향': 'EN',
    '남동향': 'ES',
    '북서향': 'WN',
    '남서향': 'WS',
}
BATHROOM_CODE_BY_NAME: dict[str, NaverRoomCount] = {
    '1개': 'RCF01',
    '2개': 'RCF02',
    '3개': 'RCF03',
    '4개이상': 'RCF04',
}
# 코드마다 서로 다른 지도 칸의 매물 4건씩을 상세(basicInfo)와 대조했다. 주차 가능·에어컨·엘리베이터·풀옵션은
# 표본으로 가르지 못해 사이트 URL(주차 가능+에어컨 = OPF02·OPF05)과 소거로 정했다.
FACILITY_CODE_BY_NAME: dict[str, NaverOptionType] = {
    '엘리베이터': 'OPF01',
    '주차': 'OPF02',
    '보안시설': 'OPF03',
    '풀옵션': 'OPF04',
    '에어컨': 'OPF05',
    '테라스': 'OPF06',
    '베란다': 'OPF07',
    '마당': 'OPF08',
    '복층': 'OPF09',
}
# 원룸 구조는 상세에 구조(shape)가 있는 매물에만 걸린다. 단지 매물(아파트·오피스텔·재건축·단지형 빌라·분양권)은
# 구조 값이 없어 모두 빠지고 (역삼동 방 1개: 아파트 435건·오피스텔 2,074건 → 0건, 대치동 재건축 1,024건 → 0건),
# 원룸·빌라·상가주택 등도 중개사가 구조를 입력하지 않은 매물은 빠진다 (역삼동 원룸 전세 35건 → 26건, 빠진 매물은
# shape 가 null. 상가주택 73건 → 11건, 2026-10-10). 서버 필터라 다시 거르지 않고 줄 때마다 알린다
ONE_ROOM_SHAPE_NOTE: str = note(
    '제외',
    '원룸 구조(오픈형·분리형)는 중개사가 구조를 입력한 매물만 걸립니다. 단지로 등록된 매물(아파트·오피스텔·단지형 빌라)은 '
    '구조 값이 없어 모두 빠지고, 다른 매물도 구조를 입력하지 않았으면 빠집니다. 빠짐없이 보려면 --one-room-shape 없이 '
    '--room 원룸 으로 찾고 listing 의 room_type 으로 구조를 확인하세요',
)
MOVE_IN_CODE_BY_NAME: dict[str, NaverMoveInType] = {
    '바로입주': 'MVF01',
    '90일내': 'MVF02',
}
LOAN_CODE_BY_NAME: dict[str, NaverLoanRatioType] = {
    '없음': '00',
    '30%이하': '10',
}
PARKING_CODE_BY_NAME: dict[str, NaverParkingType] = {
    '세대당1대': 'PKF01',
    '세대당1.5대': 'PKF02',
    '전기차충전': 'PKF03',
}
COMPLEX_FILTER_NOTE: str = note(
    '제외', '세대수·단지 주차는 네이버에 단지로 등록된 매물에만 있어, 단지가 없는 매물(빌라 대부분)은 빠졌습니다',
)
# 현관 구조는 단지 여부가 아니라 매물에 현관 구조가 등록됐는지로 걸린다 (2026-11-17 실측: 연남동 빌라 --entrance 계단식에
# 단지가 아닌 빌라 2661884425·2661802815·2661884583 이 남고, --household-min·--parking 에는 셋 다 빠졌다)
ENTRANCE_FILTER_NOTE: str = note(
    '제외', '현관 구조가 등록된 매물만 걸려, 등록되지 않은 매물은 빠졌습니다 (단지가 아닌 빌라도 등록돼 있으면 나옵니다)',
)
# 세대수·단지 주차 조건과 함께면 단지 아닌 매물은 그 조건이 이미 빼므로 ENTRANCE_FILTER_NOTE 의 괄호 말을 뺀다 (2026-11-17 실측:
# 연남동 -t 빌라 --entrance 계단식 --household-min 1 32건 중 5건을 열어 보니 모두 단지 매물이었다)
ENTRANCE_WITH_COMPLEX_FILTER_NOTE: str = note('제외', '현관 구조가 등록된 매물만 걸려, 등록되지 않은 매물은 빠졌습니다')
BOUNDED_PAGE_SIZE: int = 30
MAX_BOUNDED_PAGE_REQUESTS: int = 10
# 동 전체 검색(legalDivisionArticleList)의 페이지 크기. 서버 상한이 30 이다 (50부터 400, 2026-10-09 확인).
# limit 건까지만 받고, 받은 뒤 중복·모르는 거래 유형으로 빠져도 그만큼 다시 받지 않는다
LEGAL_DIVISION_PAGE_SIZE: int = 30
MAX_LEGAL_DIVISION_PAGE_REQUESTS: int = 5
# 지역 단지 목록(naver complexes). 페이지는 30곳(사이트 COMPLEX_PAGINATION_SIZE), 요청은 이 횟수에서 멈춘다
AREA_COMPLEX_CODES_BY_TYPE: dict[str, tuple[NaverRealEstateType, ...]] = {
    '아파트': ('A01',),
    '오피스텔': ('A02',),
    # 단지로 등록된 연립·다세대·도시형생활주택. 역삼동만 779곳이고 대부분 매물이 없다
    '빌라': ('A05', 'A06', 'A07'),
    # 이름은 `SEARCH_CODES_BY_PROPERTY` 와 같다. 응답 모양이 아파트와 같다 (2026-11-18 실측: 재건축 A04 대치동 5곳,
    # 분양권 B01 둔촌동 1곳, 오피스텔분양권 B02 는 넷 지역 모두 0곳이고 서버 답 그대로 낸다)
    '재건축': ('A04',),
    '분양권': ('B01',),
    '오피스텔분양권': ('B02',),
}
COMPLEX_LIST_SORT_TYPE_BY_NAME: dict[str, NaverComplexSortType] = {
    '인기순': 'POPULARITY_DESC',
    '세대수순': 'HOUSEHOLD_NUMBER_DESC',
    '최근입주순': 'USE_APPROVAL_DATE_DESC',
    '매물수순': 'ARTICLE_COUNT_DESC',
}
COMPLEX_LIST_PAGE_SIZE: int = 30
MAX_COMPLEX_LIST_PAGE_REQUESTS: int = 4


def _filter_range(low: float | None, high: float | None, scale: int = 1) -> NaverRangeModel | None:
    """하한·상한을 서버 필터 범위로 바꾼다. 둘 다 없으면 None (키째 빠져 제한 없음)."""
    if low is None and high is None:
        return None
    return NaverRangeModel(
        min=None if low is None else low * scale,
        max=None if high is None else high * scale,
    )


class NaverAreaComplex(BaseModel):
    """지역 단지 목록의 단지 한 곳. 좌표·대표 사진·주민 댓글은 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_number: Annotated[
        int,
        Field(description='단지 번호 (naver complex / items / real-price 에 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 빌라, 재건축, 분양권, 오피스텔분양권)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심(동이면 동 중심)에서의 거리 (km)')
    ] = None
    article_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수. 서버가 매물 수를 주지 않으면 null (모름)')
    ] = None
    sale_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 호가 [최저, 최고] (만원). 매매 매물이 없으면 null')
    ] = None
    jeonse_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 호가 [최저, 최고] (만원). 전세 매물이 없으면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class NaverAreaComplexesResult(BaseModel):
    """지역 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 단지 수 (동이면 동 안, 반경이면 반경을 감싸는 사각형 안. limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[NaverAreaComplex],
        Field(description='단지 (네이버 정렬 순서)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내 등. CLI 가 notice 아래에 붙인다')
    ] = []


def _complex_list_address(address: NaverComplexListAddressModel | None) -> str | None:
    """단지 목록의 sector 는 '서울시 강남구 역삼동' 처럼 시·구까지 붙어 온다 (단지 정보 API 는 동만)."""
    if address is None:
        return None
    sector = address.sector or ''
    base = sector if ' ' in sector else join_address(address.city, address.division, sector)
    return normalize_address(join_address(base, address.jibun))


def _area_complex(item: NaverComplexListItemModel, center: tuple[float, float]) -> NaverAreaComplex | None:
    entry = item.complex or item.villa
    if entry is None:
        return None
    info = entry.complex_info or entry.villa_info
    if info is None:
        return None
    coordinates = info.address.coordinates if info.address else None
    counts = entry.article_count_info
    prices = entry.article_price_info
    return NaverAreaComplex(
        complex_number=info.complex_number,
        name=info.name,
        property_type=PROPERTY_NAME_BY_CODE.get(info.type or '', info.type),
        address=_complex_list_address(info.address),
        households=info.total_household_number,
        dong_count=info.building_count,
        approved_at=normalize_date(info.use_approval_date),
        distance_km=round(
            haversine_km(center[0], center[1], coordinates.y_coordinate, coordinates.x_coordinate), 2,
        ) if coordinates else None,
        article_counts=trade_article_counts(counts) if counts else None,
        sale_asking_range_manwon=won_to_manwon_range(prices.deal_min_price, prices.deal_max_price) if prices else None,
        jeonse_asking_range_manwon=won_to_manwon_range(prices.rent_min_price, prices.rent_max_price) if prices else None,
        url=complex_url(info.complex_number),
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

    `legal_division_code` 를 주면 그 법정동 안 단지 전체(legalDivisionComplexList), 아니면 반경을 감싼 사각형 안
    단지(boundedComplexes)에서 반경 밖을 뺀다. 응답의 대표 사진과 주민 댓글 본문은 옮기지 않는다.

    Args:
        property_types: 단지 유형 (`AREA_COMPLEX_CODES_BY_TYPE` 의 이름). Defaults to 아파트.
        sort: 정렬 (`COMPLEX_LIST_SORT_TYPE_BY_NAME` 의 이름).
        listed_only: 매물이 있는 단지만 (사이트 '매물 있는 단지만'). 빌라 단지는 대부분 매물이 없다.
    """
    filter_ = NaverArticleFilterModel(
        trade_types=list(TRADE_CODE_BY_NAME.values()),
        real_estate_types=[code for name in property_types or ['아파트'] for code in AREA_COMPLEX_CODES_BY_TYPE[name]],
        has_article=listed_only,
        household_number=_filter_range(household_min, household_max),
        approval_elapsed_year=_filter_range(building_age_min, building_age_max),
    )
    if legal_division_code is not None:
        filter_ = dong_filter(filter_, legal_division_code)
    sort_type = COMPLEX_LIST_SORT_TYPE_BY_NAME[sort]
    complexes: dict[int, NaverAreaComplex] = {}
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
        return unwrap(response, '단지 목록')

    def keep(item: NaverComplexListItemModel) -> int | None:
        complex_ = _area_complex(item, (lat, lng))
        if complex_ is None:
            return None
        # 사각형 모서리(반경 밖) 단지는 뺀다. 좌표를 모르면 반경 안인지 알 수 없어 뺀다
        if legal_division_code is not None or (complex_.distance_km is not None and complex_.distance_km <= radius_km):
            complexes.setdefault(complex_.complex_number, complex_)
        return complex_.complex_number

    scan_pages(scan, fetch, keep, page_size=COMPLEX_LIST_PAGE_SIZE)
    total, inspected, truncated = scan.total, scan.received, scan.truncated

    result = list(complexes.values())[:limit]
    notes: list[str] = []
    area = area_scope(legal_division_code, radius_km)
    if truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 {inspected}곳까지만 훑었습니다. 단지가 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요',
        ))
    notes += pagination_notes(
        total, len(result), limit, inspected, subject='단지', truncated=truncated,
        excluded_reason=EXCLUDED_REASON if legal_division_code is not None else RADIUS_EXCLUDED_REASON,
        scope=area.scope, total_basis=area.total_basis, narrow=area.narrow,
    )
    return NaverAreaComplexesResult(total=total, returned=len(result), complexes=result, notes=notes)


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

    `legal_division_code` 를 주면 그 동 경계 안 목록(legalDivisionArticleList)이라 동 안 매물만 오고 전체 수(`total`)도
    정확하다 (역삼동 4,401건 / 같은 중심 1km 사각형 7,803건, 2026-10-09). 거리(`distance_km`)는 `lat`/`lng`(동 중심)에서
    잰 값이다. 목록 API 는 동 코드를 하나만 받는다 (2026-10-15 실측: 둘이면 400). 요청은 `MAX_LEGAL_DIVISION_PAGE_REQUESTS`
    회에서 멈춘다.

    아니면 지도 범위 목록(boundedArticles)이다. 서버는 반경을 감싼 사각형 안을 정렬해 주므로 반경 밖(모서리) 매물은
    뺀다. 제외된 수만큼 추가 조회하지 않는다. 좌표를 모르는 매물은 반경 안인지 알 수 없어 뺀다. 요청은
    `MAX_BOUNDED_PAGE_REQUESTS` 회에서 멈춘다.

    `start` 는 이어 받기 위치(목록 커서)다.
    """
    listings: dict[str, Listing] = {}
    by_dong = legal_division_code is not None
    if legal_division_code is not None:
        filter_ = dong_filter(filter_, legal_division_code)
    box = None if by_dong else bounding_box(lat, lng, radius_km)
    scan = PageScan(limit=limit, max_requests=MAX_LEGAL_DIVISION_PAGE_REQUESTS if by_dong else MAX_BOUNDED_PAGE_REQUESTS)

    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel:
        paging = NaverArticlePagingRequestModel(size=size, article_sort_type=sort_type, seed=seed, last_info=last_info)
        if box is None:
            return unwrap(
                client.run_request_article_legal_division_article_list_v1(
                    NaverArticleLegalDivisionArticleListV1RequestPayloadModel(filter=filter_, article_paging_request=paging)
                ),
                '동 매물 목록',
            )
        return unwrap(
            client.run_request_article_bounded_articles_v1(
                NaverArticleBoundedArticlesV1RequestPayloadModel(
                    filter=filter_, bounding_box=box, precision=bounded_precision(radius_km), article_paging_request=paging,
                )
            ),
            '매물 목록',
        )

    scan_pages(
        scan, fetch, listing_keeper(listings, (lat, lng), None if by_dong else radius_km),
        page_size=LEGAL_DIVISION_PAGE_SIZE if by_dong else BOUNDED_PAGE_SIZE, start=resume_cursor(start),
    )
    total, inspected, truncated = scan.total, scan.received, scan.truncated
    next_position = cursor_position(scan.cursor) or None

    result = list(listings.values())[:limit]
    notes: list[str] = []
    area = area_scope(legal_division_code, radius_km)
    if truncated:
        notes.append(note(
            '일부',
            (
                f'네이버 차단을 피하려고 동 전체에서 {inspected}건까지만 '
                f'훑었습니다. 조건에 맞는 매물이 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요'
            ) if by_dong else (
                f'네이버 차단을 피하려고 정렬 순서로 {inspected}건까지만 훑었습니다. '
                f'반경 안 매물이 더 있을 수 있으니 {area.narrow_action} 다시 검색하세요'
            ),
        ))
    notes += filter_notes
    notes += pagination_notes(
        total, len(result), limit, inspected, truncated=truncated,
        excluded_reason=EXCLUDED_REASON if by_dong else RADIUS_EXCLUDED_REASON,
        resumable=next_position is not None, resumed=start is not None,
        scope=area.scope, total_basis=area.total_basis, narrow=area.narrow,
    )
    return NaverListingsResult(
        total=total, returned=len(result), has_more=next_position is not None, next_position=next_position,
        listings=result, notes=notes,
    )


class NaverListingConditions(NaverTradeConditions):
    """지도 매물 검색 조건 (search listings). 금액은 만원, 면적은 ㎡.

    모두 서버 필터로 보내고 받은 뒤 다시 거르지 않는다 (`listing_filter_of`). 목록 안의 여러 값은 시설·단지 주차만
    모두 해당(AND)이고 나머지는 하나라도 해당(OR)이다. 세대수·단지 주차는 단지로 등록된 매물에만 있고, 현관 구조는
    등록된 매물(단지가 아닌 빌라 포함)에만 걸린다.
    """

    property_types: Annotated[
        list[str],
        Field(description='매물 유형 (PROPERTY_TYPES). 비면 주거용 (DEFAULT_SEARCH_PROPERTY_TYPES)')
    ] = []
    room_types: Annotated[
        list[str],
        Field(description='방 수 (ROOM_COUNT_CODE_BY_NAME). 목록에는 방 수가 없어 서버에서만 거른다')
    ] = []
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    area_basis: Annotated[
        str,
        Field(description='면적 기준 (AREA_BASES). 전용이면 전용면적, 공급이면 공급면적으로 비교한다')
    ] = '전용'
    floors: Annotated[
        list[str],
        Field(description='층 (FLOOR_CODE_BY_NAME)')
    ] = []
    directions: Annotated[
        list[str],
        Field(description='방향 (DIRECTION_FILTER_CODE_BY_NAME)')
    ] = []
    manage_cost_min: Annotated[
        int | None,
        Field(description='관리비 하한 (만원)')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(description='관리비 상한 (만원)')
    ] = None
    bathrooms: Annotated[
        list[str],
        Field(description='욕실 수 (BATHROOM_CODE_BY_NAME)')
    ] = []
    facilities: Annotated[
        list[str],
        Field(description='시설 (FACILITY_CODE_BY_NAME). 모두 갖춘 매물만')
    ] = []
    one_room_shapes: Annotated[
        list[str],
        Field(description='원룸 구조 (ONE_ROOM_SHAPE_CODE_BY_NAME). 분리형에는 방이 여럿인 매물도 들어가고, 구조를 입력하지 않은 매물(단지 매물은 전부)은 빠진다')
    ] = []
    move_in: Annotated[
        list[str],
        Field(description='입주 가능일 (MOVE_IN_CODE_BY_NAME)')
    ] = []
    loan: Annotated[
        str | None,
        Field(description='융자금 조건 (LOAN_CODE_BY_NAME)')
    ] = None
    photo_only: Annotated[
        bool,
        Field(description='사진 있는 매물만')
    ] = False
    household_min: Annotated[
        int | None,
        Field(description='단지 세대수 하한')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='단지 세대수 상한')
    ] = None
    parking: Annotated[
        list[str],
        Field(description='단지 주차 조건 (PARKING_CODE_BY_NAME). 모두 해당하는 매물만')
    ] = []
    entrances: Annotated[
        list[str],
        Field(description='현관 구조 (ENTRANCE_CODE_BY_NAME)')
    ] = []
    building_age_min: Annotated[
        int | None,
        Field(description='사용승인 후 지난 햇수 하한')
    ] = None
    building_age_max: Annotated[
        int | None,
        Field(description='사용승인 후 지난 햇수 상한')
    ] = None
    subway_minutes: Annotated[
        int | None,
        Field(description='지하철역까지 걸어서 이 분 안인 매물만 (역세권)')
    ] = None
    owner_verified_only: Annotated[
        bool,
        Field(description='집주인 확인 매물만')
    ] = False


def listing_filter_of(conditions: NaverListingConditions) -> NaverArticleFilterModel:
    """지도 매물 검색 조건을 네이버 매물 필터로 바꾼다. 금액은 원으로 바꿔 보낸다."""
    return NaverArticleFilterModel(
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
        deal_price=_filter_range(conditions.price_min, conditions.price_max, WON_PER_MANWON),
        warranty_price=_filter_range(conditions.deposit_min, conditions.deposit_max, WON_PER_MANWON),
        rent_price=_filter_range(conditions.rent_min, conditions.rent_max, WON_PER_MANWON),
        management_fee=_filter_range(conditions.manage_cost_min, conditions.manage_cost_max, WON_PER_MANWON),
        # 기본은 jibsa 의 area_m2 와 같은 전용면적. 공급이면 스위치를 꺼 더 큰 공급면적으로 비교한다
        space=_filter_range(conditions.area_min, conditions.area_max),
        filters_exclusive_space=conditions.area_basis == '전용' and (
            conditions.area_min is not None or conditions.area_max is not None
        ),
        household_number=_filter_range(conditions.household_min, conditions.household_max),
        approval_elapsed_year=_filter_range(conditions.building_age_min, conditions.building_age_max),
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
            _filter_range(0, conditions.subway_minutes) if conditions.subway_minutes is not None else None
        ),
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
    """좌표 반경 안이나 법정동 안의 매물을 네이버 정렬 순서 그대로 모은다.

    `legal_division_code` 를 주면 그 동 경계 안 목록, 아니면 반경을 감싼 사각형 안 목록에서 반경 밖 매물을 뺀다
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
        legal_division_code: 법정동 코드. 주면 반경 대신 그 동 전체를 찾고 `lat`/`lng` 는 거리 계산에만 쓴다.
        start: 이어 받기(`--next`) 위치로, 앞 결과의 `next_position` 이다. 결과의 `next_position` 은 더 받을 게 남았을 때만 있다.
    """
    conditions = conditions or NaverListingConditions()
    filter_ = listing_filter_of(conditions)
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
    # 동 전체·반경 정렬 모두 같은 서버 가격순이다
    filter_notes += price_sort_notes(sort_type, conditions.trade_types)
    result = _search_listing_pages(
        client, lat, lng, radius_km=radius_km, legal_division_code=legal_division_code, filter_=filter_,
        sort_type=sort_type, filter_notes=filter_notes, limit=limit, start=start,
    )
    # 결과의 안내 맨 뒤('이 N건이 전부입니다' 등) 앞에 둘 필요가 없어 끝에 붙인다
    return result.model_copy(update={'notes': result.notes + group_sort_notes(sort_type, result.listings)})
