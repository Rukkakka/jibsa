"""단지 (search complexes · complex · search listings --complex)."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
)
from jibsa.core.listing import (
    limit_notes,
    lookup_failure_note,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    note,
    won_to_manwon,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    DabangAptFiltersModel,
    DabangBboxModel,
    DabangComplexCategory,
    DabangOfficetelFiltersModel,
    DabangSearchType,
)
from jibsa.providers.dabang.api.request.complex import (
    DabangComplexListCategoryV5RequestParameterModel,
    DabangComplexLoanCalcConditionV5RequestParameterModel,
    DabangComplexRoomFiltersModel,
    DabangComplexRoomOrder,
    DabangComplexSummaryV5RequestParameterModel,
    DabangRoomListCategoryComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import (
    DabangComplexChildcareModel,
    DabangComplexResultModel,
    DabangComplexSchoolModel,
    DabangComplexSpaceModel,
    DabangRoomItemModel,
)
from jibsa.providers.dabang.api.response.complex import (
    DabangComplexListItemModel,
    DabangLatelyPriceModel,
)
from jibsa.providers.dabang.service.common import (
    COMPLEX_KIND_BY_TYPE,
    MAX_LIST_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    ZOOM_BY_SEARCH_TYPE,
    ComplexKind,
    DabangAreaPrice,
    DabangListing,
    DabangListingConditions,
    DabangPage,
    DabangPlace,
    ListingKind,
    SchoolLevel,
    area_price,
    bbox_of,
    building_years,
    complex_url,
    count_of,
    duplicate_note,
    fetch_complex,
    fetch_pages,
    fetch_stop_notes,
    filters_of,
    first_space_notes,
    floor_label,
    household_count,
    manwon_from_text,
    more_list_notes,
    narrow_again,
    number_of,
    premium_note,
    primary_space_of,
    room_item_to_listing,
    room_list_page,
    unreadable_note,
)
from jibsa.providers.dabang.service.region import dong_bbox

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


# 최근 거래의 면적을 내는 키. 다방 요약의 면적은 아파트면 공급, 오피스텔이면 계약이다
RecentAreaKey = Literal['supply_area_m2', 'contract_area_m2']
CATEGORY_BY_COMPLEX_KIND: dict[ComplexKind, DabangComplexCategory] = {'아파트': 'apt', '오피스텔': 'officetel'}
LISTING_KIND_BY_CATEGORY: dict[DabangComplexCategory, ListingKind] = {'apt': 'apt', 'officetel': 'officetel'}
# 중·고등학교·어린이집·유치원은 가까운 순 3곳. 웹 '주변 보육/교육시설' 탭이 3곳씩 보이고 '더보기' 로 3곳씩 늘린다
# (education 청크 `Y`·`X`·`Q`·`$` = 3, 2026-11-13)
NEAREST_SCHOOLS: int = 3
# 단지 응답의 설립 유형 글자를 다방 학군 화면(`search schools`·`school`)의 이름으로 맞춘다. 다방은 같은 시설을 화면마다 다르게
# 부른다 (2026-11-14 실측: 방배본동 행복한 어린이집은 단지 화면 '국공립'·상세 '공공', 서울서래초병설유치원은 단지 화면
# '공립'·상세 '국공립'). 표에 없는 글자는 그대로 낸다
# 리뷰 오탐 (2026-11-14): nurseries·kindergartens 는 v0.12.0 뒤 Unreleased 에 처음 생긴 필드라 값 정리가 호환 깨짐이 아니다
# (CHANGELOG 의 호환 깨짐 절에 적지 않는다)
NURSERY_ESTABLISHMENT_LABELS: dict[str, str] = {'국공립': '공공'}
KINDER_ESTABLISHMENT_LABELS: dict[str, str] = {'공립': '국공립'}
# 요약 면적('115.54㎡')과 평형표 면적이 같은지 볼 때 허용하는 차 (둘 다 소수 둘째 자리라 반올림 차만 둔다)
AREA_MATCH_TOLERANCE_M2: float = 0.01


class ComplexSort(NamedTuple):
    """단지 매물 정렬 하나."""

    # 다방 요청의 order 값
    order: DabangComplexRoomOrder
    # `[일부]` 안내에 쓰는 정렬 이름 ('… 순으로 앞 N건')
    text: str


# 단지 매물 정렬 (--sort). 다방 웹 단지 매물 탭의 정렬 메뉴 이름 그대로다 (complex 청크 `xt`, 2026-11-13. 기본 랭킹순). 은마
# 5건이 낮은가격순 30억7000 → 34억, 높은가격순은 그 반대로 왔다 (같은 날 실측). 다방이 정렬한 순서를 그대로 낸다
COMPLEX_SORT_BY_LABEL: dict[str, ComplexSort] = {
    '랭킹순': ComplexSort('RANKING', '다방 랭킹'),
    '최신순': ComplexSort('LATEST', '다방 최신'),
    '높은가격순': ComplexSort('SELLING_HIGHEST', '다방 높은 가격'),
    '낮은가격순': ComplexSort('SELLING_LOWEST', '다방 낮은 가격'),
    '면적넓은순': ComplexSort('ROOM_SIZE_LARGEST', '다방 넓은 면적'),
    '면적좁은순': ComplexSort('ROOM_SIZE_SMALLEST', '다방 좁은 면적'),
}
DEFAULT_COMPLEX_SORT: str = '랭킹순'


class DabangComplexSummary(BaseModel):
    """단지 목록의 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID. dabang complex·search listings --complex·real-price 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    years: Annotated[
        int | None,
        Field(description='입주 연차 (년)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수')
    ] = None
    rent_listing_count: Annotated[
        int | None,
        Field(description='월세 매물 수')
    ] = None
    lease_listing_count: Annotated[
        int | None,
        Field(description='전세 매물 수')
    ] = None
    sale_listing_count: Annotated[
        int | None,
        Field(description='매매 매물 수')
    ] = None
    recent_sale_manwon: Annotated[
        float | None,
        Field(description='최근 매매 실거래가 (만원, 평형과 상관없이 단지의 가장 최근 거래. 다방 목록 카드와 같다)')
    ] = None
    recent_lease_manwon: Annotated[
        float | None,
        Field(description='최근 전세 실거래가 (만원, 평형과 상관없이 단지의 가장 최근 거래)')
    ] = None


class DabangComplexListResult(BaseModel):
    """단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치')
    ]
    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description='다방이 센 범위 안 단지 수 (반경·아파트 동 검색은 사각형 안의 수)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    complexes: Annotated[
        list[DabangComplexSummary],
        Field(description='다방 목록 순 단지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='범위·제외 안내')
    ] = []


def _summary(item: DabangComplexListItemModel) -> DabangComplexSummary:
    counts = item.room_count
    price = item.real_price
    return DabangComplexSummary(
        complex_id=item.complex_id,
        name=item.complex_name,
        complex_type=COMPLEX_KIND_BY_TYPE.get(item.complex_type or ''),
        years=building_years(item.complex_desc),
        household_count=household_count(item.complex_desc),
        address=normalize_address(item.address),
        listing_count=counts.total_count if counts else None,
        rent_listing_count=counts.monthly_rent_count if counts else None,
        lease_listing_count=counts.lease_count if counts else None,
        sale_listing_count=counts.sell_count if counts else None,
        recent_sale_manwon=manwon_from_text(price.sale) if price else None,
        recent_lease_manwon=manwon_from_text(price.lease) if price else None,
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



class DabangPyeong(BaseModel):
    """단지의 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    space_seq: Annotated[
        int,
        Field(description='평형 번호. real-price·price-trend·search listings --complex 의 --pyeong 값')
    ]
    name: Annotated[
        str | None,
        Field(description="평형 이름 (아파트는 공급 평 '30', 오피스텔은 '13B1')")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 대개 null')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 오피스텔)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='월 관리비 총액 (만원, 다방 단지 정보)')
    ] = None


class DabangRecentTrade(BaseModel):
    """최근 실거래 한 건 (단지 요약). 면적은 다방 화면처럼 아파트는 공급면적, 오피스텔은 계약면적 키 하나만 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_manwon: Annotated[
        float | None,
        Field(description='매매가 또는 전세금 (만원)')
    ] = None
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='거래 공급면적 (㎡, 아파트. 다방 화면의 면적)')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='거래 계약면적 (㎡, 오피스텔. 다방 화면의 면적)')
    ] = None
    space_seq: Annotated[
        int | None,
        Field(description='거래한 평형 번호 (pyeongs[].space_seq). 면적이 맞는 평형이 하나일 때만, 없거나 여럿이면 null')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='거래한 평형의 전용면적 (㎡). space_seq 가 null 이면 null')
    ] = None
    area_key: Annotated[
        RecentAreaKey,
        Field(exclude=True, description='단지 유형에 맞는 면적 키')
    ] = 'supply_area_m2'

    @model_serializer(mode='wrap')
    def drop_other_area(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        data.pop('contract_area_m2' if self.area_key == 'supply_area_m2' else 'supply_area_m2', None)
        return data


class DabangComplexSchool(BaseModel):
    """단지 근처 학교 하나. 진학 인원은 중학교·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    level: Annotated[
        SchoolLevel,
        Field(description='초등학교 / 중학교 / 고등학교. school 명령의 --level 값')
    ]
    school_code: Annotated[
        str | None,
        Field(description='학교 코드. jibsa dabang school <school_code> --level <level> 로 학교 상세를 본다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='학교 이름 (다방이 주지 않으면 null)')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description='설립 (공립, 사립)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선 거리 (m)')
    ] = None
    district: Annotated[
        str | None,
        Field(description='초등학교는 단지가 든 통학구역(배정 학구), 중·고등학교는 단지가 든 학교군')
    ] = None
    students_per_class: Annotated[
        int | None,
        Field(description='학급당 학생 수')
    ] = None
    special_high_entrants: Annotated[
        int | None,
        Field(description='특목고(과학고·외고·국제고·예술고 등) 진학 인원 (명, 중학교, 학교알리미 공시)')
    ] = None
    autonomous_high_entrants: Annotated[
        int | None,
        Field(description='자율형(자사고·자공고) 고등학교 진학 인원 (명, 중학교, 학교알리미 공시)')
    ] = None
    university_entrants: Annotated[
        int | None,
        Field(description='대학교(4년제) 진학 인원 (명, 고등학교, 학교알리미 공시)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_levels(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level != '중학교':
            data.pop('special_high_entrants', None)
            data.pop('autonomous_high_entrants', None)
        if self.level != '고등학교':
            data.pop('university_entrants', None)
        return data


class DabangChildcare(BaseModel):
    """단지 근처 어린이집·유치원 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    code: Annotated[
        str | None,
        Field(description='다방 시설 코드. jibsa dabang school <code> --level 어린이집 (nurseries) 또는 --level 유치원 (kindergartens) 으로 상세를 본다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='시설 이름 (다방이 주지 않으면 null)')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description="설립 유형 (어린이집 '공공'·'민간'·'가정'·'직장'·'협동', 유치원 '국공립'·'사립'. search schools·school 과 같은 이름)")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선 거리 (m)')
    ] = None
    children_per_teacher: Annotated[
        float | None,
        Field(description='교사당 아동 수')
    ] = None


class DabangComplexDetail(BaseModel):
    """단지 정보."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    lowest_floor: Annotated[
        int | None,
        Field(description='최저층')
    ] = None
    highest_floor: Annotated[
        int | None,
        Field(description='최고층')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    building_coverage_ratio: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    builder: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방')
    ] = None
    fuel: Annotated[
        str | None,
        Field(description='연료')
    ] = None
    entrance: Annotated[
        str | None,
        Field(description='현관 구조 (계단식·복도식)')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수')
    ] = None
    recent_deal_count: Annotated[
        int | None,
        Field(description="최근 거래 수 (다방 화면의 '최근 거래수 N건', 다방이 기간을 밝히지 않는다)")
    ] = None
    tags: Annotated[
        list[str],
        Field(description="다방 단지 꼬리표 (예: '입주 5년차', '고속터미널역 도보 7분', '초품아'). 없으면 []")
    ] = []
    pyeongs: Annotated[
        list[DabangPyeong] | None,
        Field(description='평형. null 이면 다방이 평형을 주지 않은 것이라 모름')
    ]
    primary_space_seq: Annotated[
        int | None,
        Field(description=(
            '대표 평형 번호 (real-price·price-trend·nearby-complexes 에 --pyeong 이 없을 때 쓴다). 다방이 대표를 주지 않으면 '
            '다방 웹처럼 첫 평형이고, 평형이 없으면 null'
        ))
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice] | None,
        Field(description=(
            "평당 평균가 비교 (이 단지·동·구, 다방 웹 평당가 칸의 '전체 평형 비교' 탭). 기본 탭 'N평대 비교' 는 "
            'jibsa dabang nearby-complexes <complex_id>. null 이면 다방이 주지 않은 것이라 모름'
        ))
    ]
    recent_sale: Annotated[
        DabangRecentTrade | None,
        Field(description='최근 매매 실거래 (없거나 받지 못하면 null)')
    ] = None
    recent_lease: Annotated[
        DabangRecentTrade | None,
        Field(description='최근 전세 실거래 (없거나 받지 못하면 null)')
    ] = None
    overheated_district: Annotated[
        bool | None,
        Field(description=(
            "다방 대출 계산기가 대출 비율을 50%로 묶는 지역인지 (다방 단지 대출 계산 조건 isOverheatedDistrict). 웹 대출 계산기는 "
            "true 면 대출 가능액을 집값의 절반으로 셈하고, 자본금이 모자랄 때 '투기지역 (대출 비율 50% 제한) 입니다.' 라고 알린다. "
            "받지 못하면 null"
        ))
    ] = None
    schools: Annotated[
        list[DabangComplexSchool] | None,
        Field(description=f'배정 초등학교와 단지가 든 학교군의 가까운 중·고등학교 {NEAREST_SCHOOLS}곳씩. 모르면 null')
    ] = None
    nurseries: Annotated[
        list[DabangChildcare] | None,
        Field(description=f'가까운 어린이집 {NEAREST_SCHOOLS}곳. 없으면 [], 모르면 null')
    ] = None
    kindergartens: Annotated[
        list[DabangChildcare] | None,
        Field(description=f'가까운 유치원 {NEAREST_SCHOOLS}곳. 없으면 [], 모르면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='덤 조회 실패·최근 거래 평형 안내')
    ] = []


def _school(school: DabangComplexSchoolModel, level: SchoolLevel) -> DabangComplexSchool:
    return DabangComplexSchool(
        level=level,
        school_code=school.code,
        name=school.name,
        establishment=school.establish_divide,
        distance_m=school.distance,
        district=school.hakgudo_name,
        students_per_class=count_of(school.avg_students_per_class),
        special_high_entrants=count_of(school.total_enter_special_high_school),
        autonomous_high_entrants=count_of(school.total_enter_autonomous_high_school),
        university_entrants=count_of(school.enter_university),
    )


def _childcare(facility: DabangComplexChildcareModel) -> DabangChildcare:
    # 어린이집은 `type`, 유치원은 `establishDivide` 에 설립 유형이 온다
    if facility.type:
        establishment: str | None = NURSERY_ESTABLISHMENT_LABELS.get(facility.type, facility.type)
    elif facility.establish_divide:
        establishment = KINDER_ESTABLISHMENT_LABELS.get(facility.establish_divide, facility.establish_divide)
    else:
        establishment = None
    return DabangChildcare(
        code=facility.code,
        name=facility.name,
        establishment=establishment,
        distance_m=facility.distance,
        children_per_teacher=number_of(facility.child_per_teacher),
    )


def _recent(
    trade: DabangLatelyPriceModel | None,
    spaces: list[DabangComplexSpaceModel] | None,
    category: DabangComplexCategory,
    label: str,
) -> tuple[DabangRecentTrade | None, list[str]]:
    """단지 요약의 최근 거래와 안내. 요약 면적은 전용이 아니라 아파트는 공급면적, 오피스텔은 계약면적이고 평형 번호가 없다
    (2026-10-26 실측: 은마 매매 115.54㎡ = 34평 공급, 전용 84.43㎡ / 역삼SK허브블루 매매 55.19㎡ = 16평 계약, 전용 30.06㎡).

    웹 요약은 면적만 보여 주므로 그 면적을 그대로 내고, 평형표에서 그 면적인 평형이 하나뿐일 때만 평형 번호·전용면적을 붙인다.
    공급면적이 같은 평형이 여럿인 단지가 있어 고르지 않는다 (2026-11-13 실측: 삼호1차 82.08㎡ 는 3526(24A)·286028(24C)).
    다방이 평형 목록을 주지 않으면(`spaces` 가 None) 맞출 평형이 없어 평형 번호·전용면적이 null 이다. '평형 없음' 같은 안내는
    쓰지 않는다 (모르는 것이라 pyeongs 가 null 이고, 이 두 칸은 원래 맞는 평형이 하나가 아니면 null 이다).
    """
    if trade is None or trade.format_price is None:
        return None, []
    size = number_of(trade.format_room_size)
    matches = [
        space for space in spaces or []
        if size is not None and any(
            value is not None and abs(value - size) < AREA_MATCH_TOLERANCE_M2 for value in (space.supply_space, space.contract_space)
        )
    ]
    space = matches[0] if len(matches) == 1 else None
    notes: list[str] = []
    if len(matches) > 1:
        candidates = ', '.join(f'{match.space_seq}({match.pyeong_type})' if match.pyeong_type else str(match.space_seq) for match in matches)
        # 고르지 않고 비운 것이라 '하나를 골랐다' 는 뜻의 [모호] 가 아니라 [참고] 로 알린다 (output-contract.md 의 꼬리표)
        notes.append(note(
            '참고',
            f'최근 {label} 거래의 면적 {size:g}㎡ 인 평형이 여럿이라 space_seq·area_m2 를 null 로 두었습니다. 후보 평형: {candidates}',
        ))
    area_key: RecentAreaKey = 'contract_area_m2' if category == 'officetel' else 'supply_area_m2'
    return DabangRecentTrade(
        price_manwon=manwon_from_text(trade.format_price),
        trade_date=normalize_date(f'20{trade.format_contract_date}') if trade.format_contract_date else None,
        floor=floor_label(trade.format_floor),
        supply_area_m2=size if area_key == 'supply_area_m2' else None,
        contract_area_m2=size if area_key == 'contract_area_m2' else None,
        space_seq=space.space_seq if space else None,
        area_m2=space.room_space if space else None,
        area_key=area_key,
    ), notes


def _floor_int(value: str | None) -> int | None:
    return int(value) if value and value.isdecimal() else None


def _category_of(result: DabangComplexResultModel) -> DabangComplexCategory:
    """단지 상세의 유형 (아파트·오피스텔). 단지 매물·요약 요청의 경로 값이다."""
    return 'officetel' if result.complex.complex_type == 'OFFICETEL' else 'apt'


def get_complex(client: DabangClient, complex_id: str) -> DabangComplexDetail:
    """단지 정보 (요청 3회: 단지 상세 + 최근 실거래 요약 + 대출 계산 조건). 사진·관리사무소 전화·광고 중개사는 옮기지 않는다.

    최근 실거래 요약과 대출 계산 조건은 덤이라 실패해도 단지 정보는 돌려주고 recent_sale·recent_lease·overheated_district 를
    모름(null)으로 둔다.
    """
    result = fetch_complex(client, complex_id)
    info = result.complex
    category = _category_of(result)
    notes: list[str] = []
    try:
        summary = client.run_request_complex_summary_v5(
            DabangComplexSummaryV5RequestParameterModel(complex_type=category, complex_id=complex_id)
        ).result
    except OPTIONAL_LOOKUP_ERRORS as exc:
        summary = None
        notes.append(lookup_failure_note(exc, '다방', '최근 실거래 요약', 'recent_sale·recent_lease 는 모름(null)입니다. 실거래는 real-price 로 보세요'))
    # 웹 단지 화면이 단지 상세 바로 뒤에 부르는 대출 계산 조건이다 (complex 청크 `je`). 금리는 다방 계산기 기본값이라 내지 않는다
    try:
        loan = client.run_request_complex_loan_calc_condition_v5(
            DabangComplexLoanCalcConditionV5RequestParameterModel(complex_id=complex_id)
        ).result
    except OPTIONAL_LOOKUP_ERRORS as exc:
        loan = None
        notes.append(lookup_failure_note(exc, '다방', '대출 계산 조건', 'overheated_district 는 모름(null)입니다'))
    else:
        # 요청은 성공했는데 result 나 is_overheated_district 를 주지 않은 경우 (예외일 때의 안내와 겹치지 않게 else)
        if loan is None or loan.is_overheated_district is None:
            notes.append(note('실패', '다방이 대출 계산 조건 값을 주지 않아 overheated_district 는 모름(null)입니다'))
    education = result.education
    schools = nurseries = kindergartens = None
    if education is not None:
        # 중·고등학교는 거리순으로 온다 (2026-10-25 실측: 은마 중 17곳·고 22곳, 오피스텔 중 7곳·고 22곳). 목록이 null 로 오면
        # 그 목록은 모름이다 (단지 38곳 실측에서는 늘 목록이었고 없으면 [] 였다, 2026-11-14)
        levels: tuple[tuple[SchoolLevel, list[DabangComplexSchoolModel] | None, int | None], ...] = (
            ('초등학교', education.elementary_school, None),
            ('중학교', education.middle_school, NEAREST_SCHOOLS),
            ('고등학교', education.high_school, NEAREST_SCHOOLS),
        )
        if any(rows is not None for _, rows, _ in levels):
            schools = [_school(school, level) for level, rows, count in levels for school in (rows or [])[:count]]
            # 다른 학교급은 목록인데 null 로 온 학교급은 schools 에 빠져 '그 학교급 없음' 처럼 보여 모름이라고 알린다
            notes += [
                note('참고', f'다방이 {level} 목록을 주지 않아 schools 에 {level}가 없습니다 (없다는 뜻이 아니라 모름)')
                for level, rows, _ in levels if rows is None
            ]
        if education.nursery_school is not None:
            nurseries = [_childcare(facility) for facility in education.nursery_school[:NEAREST_SCHOOLS]]
        if education.kinder_school is not None:
            kindergartens = [_childcare(facility) for facility in education.kinder_school[:NEAREST_SCHOOLS]]
    recent_sale, sale_notes = _recent(summary.sell_lately_price if summary else None, result.spaces, category, '매매')
    recent_lease, lease_notes = _recent(summary.lease_lately_price if summary else None, result.spaces, category, '전세')
    approved = info.building_approval_date_name
    primary = primary_space_of(result)
    return DabangComplexDetail(
        complex_id=info.complex_id,
        name=info.complex_name,
        complex_type=info.complex_type_name or COMPLEX_KIND_BY_TYPE.get(info.complex_type or ''),
        address=normalize_address(info.jibun_address or info.address),
        road_address=normalize_address(info.road_address),
        household_count=info.household_num,
        building_count=info.building_num,
        parking_count=info.parking_num,
        parking_per_household=info.parking_average,
        lowest_floor=_floor_int(info.complex_lowest_floor),
        highest_floor=_floor_int(info.complex_highest_floor),
        floor_area_ratio=info.floor_area_ratio,
        building_coverage_ratio=info.building_coverage_ratio,
        builder=info.provider_name,
        approved_at=normalize_date(approved) if approved else None,
        heating=info.heat_type_name,
        fuel=info.fuel_type_name,
        entrance=info.entrance_type_name,
        listing_count=result.room_count,
        recent_deal_count=info.recent_deal_count,
        tags=info.hash_tags,
        pyeongs=None if result.spaces is None else [
            DabangPyeong(
                space_seq=space.space_seq,
                name=space.pyeong_type,
                area_m2=space.room_space,
                area_pyeong=m2_to_pyeong(space.room_space),
                supply_area_m2=space.supply_space,
                contract_area_m2=space.contract_space,
                room_count=space.beds_num,
                bathroom_count=space.bath_num,
                manage_cost_manwon=won_to_manwon(space.maintenance_total_price),
            )
            for space in result.spaces
        ],
        primary_space_seq=primary[0] if primary else None,
        area_prices=None if result.area_average_price is None else [area_price(price) for price in result.area_average_price],
        recent_sale=recent_sale,
        recent_lease=recent_lease,
        overheated_district=loan.is_overheated_district if loan else None,
        schools=schools,
        nurseries=nurseries,
        kindergartens=kindergartens,
        url=complex_url(info.complex_id),
        notes=notes + sale_notes + lease_notes + first_space_notes(result),
    )


class DabangComplexListingsResult(BaseModel):
    """단지 하나의 매물."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    space_seqs: Annotated[
        list[int] | None,
        Field(description='고른 평형 번호. null 이면 전체 평형')
    ] = None
    sort: Annotated[
        str,
        Field(description="매물 순서 (다방 웹 단지 매물 정렬: '랭킹순'·'최신순'·'높은가격순'·'낮은가격순'·'면적넓은순'·'면적좁은순')")
    ] = DEFAULT_COMPLEX_SORT
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 매물이 있는지')
    ] = False
    listings: Annotated[
        list[DabangListing],
        Field(description='sort 순서 그대로의 매물 (다방이 정렬한 순서)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평형·제외·일부 안내')
    ] = []


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
    category = _category_of(result)
    kind = LISTING_KIND_BY_CATEGORY[category]
    # 다방이 평형 목록을 주지 않으면(None) 어떤 번호가 없는지 모르니 막지 않고 그대로 보낸다 (모르는데 '없다' 고 하지 않는다)
    all_seqs = None if result.spaces is None else [space.space_seq for space in result.spaces]
    unknown = [seq for seq in space_seqs or [] if all_seqs is not None and seq not in all_seqs]
    if unknown:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"이 단지에 없는 평형 번호입니다: {', '.join(map(str, unknown))}",
            hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].space_seq 를 주세요',
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
        space_seqs=space_seqs,
        sort=sort,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )

