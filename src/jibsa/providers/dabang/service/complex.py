"""단지 (search complexes · complex · search listings --complex)."""
from httpx import HTTPStatusError
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
from jibsa.core.http import OPTIONAL_LOOKUP_BASE_ERRORS
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    limit_notes,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    note,
    won_to_manwon,
)
from jibsa.core.ratelimit import RateLimitedError
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
    DabangComplexRoomFiltersModel,
    DabangComplexSummaryV5RequestParameterModel,
    DabangRoomListCategoryComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import (
    DabangComplexResultModel,
    DabangComplexSchoolModel,
    DabangComplexSpaceModel,
)
from jibsa.providers.dabang.api.response.complex import (
    DabangComplexListItemModel,
    DabangLatelyPriceModel,
)
from jibsa.providers.dabang.service.common import (
    MAX_LIST_PAGES,
    PAGE_SIZE,
    ZOOM_BY_SEARCH_TYPE,
    DabangListing,
    DabangListingConditions,
    DabangPlace,
    ListingKind,
    SchoolLevel,
    bbox_of,
    building_years,
    complex_url,
    count_of,
    fetch_complex,
    filters_of,
    floor_label,
    household_count,
    manwon_from_text,
    middle_place,
    premium_note,
    room_item_to_listing,
)
from jibsa.providers.dabang.service.region import dongs_bbox

from typing import (
    Annotated,
    Any,
    Literal,
)


ComplexKind = Literal['아파트', '오피스텔']
CATEGORY_BY_COMPLEX_KIND: dict[ComplexKind, DabangComplexCategory] = {'아파트': 'apt', '오피스텔': 'officetel'}
LISTING_KIND_BY_CATEGORY: dict[DabangComplexCategory, ListingKind] = {'apt': 'apt', 'officetel': 'officetel'}
COMPLEX_KIND_BY_TYPE: dict[str, ComplexKind] = {'APT': '아파트', 'OFFICETEL': '오피스텔'}
NEAREST_SCHOOLS: int = 2
# 요약 면적('115.54㎡')과 평형표 면적이 같은지 볼 때 허용하는 차 (둘 다 소수 둘째 자리라 반올림 차만 둔다)
AREA_MATCH_TOLERANCE_M2: float = 0.01
# 덤 조회(최근 실거래 요약)가 실패해도 단지 정보는 돌려줄 예외. 세 소스 공통 범위에 요청 제한(분당 상한 대기·429 쿨다운)을
# 더한다. 받아 둔 단지 정보까지 버리지 않는다 (당근 `OPTIONAL_LOOKUP_ERRORS` 와 같은 뜻)
OPTIONAL_LOOKUP_ERRORS: tuple[type[Exception], ...] = (*OPTIONAL_LOOKUP_BASE_ERRORS, RateLimitedError)


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
        Field(description='최근 매매 실거래가 (만원, 다방이 고른 대표 평형)')
    ] = None
    recent_lease_manwon: Annotated[
        float | None,
        Field(description='최근 전세 실거래가 (만원)')
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
    places: list[DabangPlace],
    *,
    limit: int,
    radius_km: float | None = None,
) -> DabangComplexListResult:
    """지역 안 단지 목록 (다방 목록 순, 24곳씩). 조건 없이 그 범위의 단지를 모두 준다 (매물 없는 단지 포함).

    찾는 방식은 매물 검색과 같다. 아파트는 동·대학 검색이 없어 동은 경계를 덮는 사각형으로 받아 그 동 단지만 남긴다.
    """
    category = CATEGORY_BY_COMPLEX_KIND[complex_kind]
    filters = DabangAptFiltersModel() if category == 'apt' else DabangOfficetelFiltersModel()
    place = middle_place(places) if radius_km is not None else places[0]
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
        if len(places) > 1:
            notes.append(note('범위', f'{place.name} 중심들의 가운데에서 반경 {radius_km:g}km 를 덮는 사각형을 찾았습니다'))
    elif place.kind == 'station':
        search_type, place_id, scope = 'subway', place.place_id, f'{place.name} 다방 역 반경'
    elif place.kind == 'university':
        # 여기 오는 것은 오피스텔뿐이다 (아파트 대학은 위에서 반경으로 바꾼다). 오피스텔 단지 목록은 대학 검색이 된다
        # (2026-10-26 실측: 홍익대학교 -t 오피스텔 정상, 403 은 아파트 단지 목록만)
        search_type, place_id, scope = 'univ', place.place_id, f'{place.name} 둘레'
    elif category == 'apt' or len(places) > 1:
        # 아파트는 동 검색이 없다. '○가' 동 여럿도 한 사각형으로 받아 그 동들 단지만 남긴다
        search_type, bbox = 'bbox', dongs_bbox(client, places)
        keep_gids = frozenset(part.gid for part in places if part.gid is not None)
        scope = f"{'·'.join(part.name for part in places)} 안"
    else:
        search_type, code, scope = 'region', place.code, f'{place.name} 안'
    complexes: list[DabangComplexSummary] = []
    # limit 은 받은 단지 수로 센다. 다른 동이라 뺀 단지만큼 다음 쪽을 더 받지 않는다 (매물 목록과 같다)
    received = 0
    other_dong = duplicate = 0
    # 다방 단지 목록은 쪽마다 순서가 흔들려 앞 쪽 끝의 단지를 다음 쪽 첫머리에 다시 준다 (정렬 옵션이 없다). 2026-10-26 실측:
    # 잠실동 아파트 1쪽 23·24번째(신동아로쟌뷰·갤러리아팰리스)가 2쪽 1·2번째로 다시 와 3쪽까지 71줄 중 단지는 69곳이었다
    seen_ids: set[str] = set()
    total: int | None = None
    has_more = False
    page = 1
    while received < limit and page <= MAX_LIST_PAGES:
        result = client.run_request_complex_list_category_v5(DabangComplexListCategoryV5RequestParameterModel(
            category=category, search_type=search_type, filters=filters, code=code, id=place_id, bbox=bbox,
            zoom=ZOOM_BY_SEARCH_TYPE[search_type], page=page,
        )).result
        if result is None:
            break
        total = result.total if total is None else total
        # limit 에 닿아 쪽 중간에서 멈추면 남은 칸이 있어 더 있다 (다른 동을 빼는 범위도 본 칸까지만 센다)
        seen = 0
        for item in result.list_:
            if received >= limit:
                break
            received += 1
            seen += 1
            if item.complex_id in seen_ids:
                duplicate += 1
                continue
            seen_ids.add(item.complex_id)
            if keep_gids is not None and item.gid not in keep_gids:
                other_dong += 1
                continue
            complexes.append(_summary(item))
        has_more = bool(result.has_more) or seen < len(result.list_)
        if not result.has_more:
            break
        page += 1
    if other_dong:
        notes.append(note('제외', f'동 경계를 덮는 사각형에서 받은 단지 중 다른 동 {other_dong}곳을 뺐습니다'))
    if duplicate:
        notes.append(note('제외', f'다방이 다음 쪽에 다시 준 단지 {duplicate}곳은 한 번만 넣었습니다 (다시 채우지 않음)'))
    if has_more and received >= limit:
        notes.append(note('일부', f'단지가 더 있습니다 (다방 목록 순 앞 {received}곳을 봤습니다). 더 보려면 --limit 을 늘리거나 더 좁은 동·역으로 찾으세요'))
    region = place if len(places) == 1 else place.model_copy(update={'name': '·'.join(part.name for part in places)})
    return DabangComplexListResult(
        region=region, scope=scope, total=total, returned=len(complexes), has_more=has_more, complexes=complexes, notes=notes,
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


class DabangAreaPrice(BaseModel):
    """평당 평균가 비교 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        str,
        Field(description="범위 ('해당 단지', 동 이름, 구 이름)")
    ]
    sale_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='매매 평당 평균가 (만원)')
    ] = None
    lease_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='전세 평당 평균가 (만원)')
    ] = None


class DabangRecentTrade(BaseModel):
    """최근 실거래 한 건 (단지 요약)."""

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
    space_seq: Annotated[
        int | None,
        Field(description='거래한 평형 번호 (pyeongs[].space_seq). 평형을 알아보지 못하면 null')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='거래한 평형의 전용면적 (㎡). 평형을 알아보지 못하면 null')
    ] = None


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
        str,
        Field(description='학교 이름')
    ]
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
    pyeongs: Annotated[
        list[DabangPyeong],
        Field(description='평형')
    ]
    primary_space_seq: Annotated[
        int | None,
        Field(description='다방 대표 평형 번호 (real-price·price-trend 에 --pyeong 이 없을 때 쓴다)')
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice],
        Field(description='평당 평균가 비교 (이 단지·동·구)')
    ]
    recent_sale: Annotated[
        DabangRecentTrade | None,
        Field(description='최근 매매 실거래 (없거나 받지 못하면 null)')
    ] = None
    recent_lease: Annotated[
        DabangRecentTrade | None,
        Field(description='최근 전세 실거래 (없거나 받지 못하면 null)')
    ] = None
    schools: Annotated[
        list[DabangComplexSchool] | None,
        Field(description='배정 초등학교와 단지가 든 학교군의 가까운 중·고등학교 2곳씩. 모르면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='덤 조회 실패 안내')
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


def _recent(trade: DabangLatelyPriceModel | None, spaces: list[DabangComplexSpaceModel]) -> DabangRecentTrade | None:
    """단지 요약의 최근 거래. 요약 면적은 전용이 아니라 아파트는 공급면적, 오피스텔은 계약면적이고 평형 번호가 없어
    평형표에서 그 면적인 평형을 찾아 전용면적을 낸다 (2026-10-26 실측: 은마 매매 115.54㎡ = 34평 공급, 전용 84.43㎡ /
    역삼SK허브블루 매매 55.19㎡ = 16평 계약, 전용 30.06㎡).
    """
    if trade is None or trade.format_price is None:
        return None
    text = (trade.format_room_size or '').rstrip('㎡m²').strip()
    try:
        size = float(text) if text else None
    except ValueError:
        size = None
    space = next((
        space for space in spaces
        if size is not None and any(
            value is not None and abs(value - size) < AREA_MATCH_TOLERANCE_M2 for value in (space.supply_space, space.contract_space)
        )
    ), None)
    return DabangRecentTrade(
        price_manwon=manwon_from_text(trade.format_price),
        trade_date=normalize_date(f'20{trade.format_contract_date}') if trade.format_contract_date else None,
        floor=floor_label(trade.format_floor),
        space_seq=space.space_seq if space else None,
        area_m2=space.room_space if space else None,
    )


def _floor_int(value: str | None) -> int | None:
    return int(value) if value and value.isdecimal() else None


def _category_of(result: DabangComplexResultModel) -> DabangComplexCategory:
    """단지 상세의 유형 (아파트·오피스텔). 단지 매물·요약 요청의 경로 값이다."""
    return 'officetel' if result.complex.complex_type == 'OFFICETEL' else 'apt'


def _summary_failure_note(exc: Exception) -> str:
    """최근 실거래 요약을 받지 못한 안내. 실패 이유마다 다음 행동이 달라(업데이트·다시 시도) 이유를 넣는다.

    다방이 요청을 거절했거나(4xx) 응답 형식이 바뀌면 업데이트 안내를 붙인다 (매일 감시가 고장으로 본다). 요청 제한·서버
    오류(5xx)·연결 실패는 사이트가 바뀐 것이 아니라 붙이지 않는다 (감시는 확인 못 함으로 본다).
    """
    unknown = 'recent_sale·recent_lease 는 모름(null)입니다. 실거래는 real-price 로 보세요'
    if isinstance(exc, RateLimitedError):
        return note('실패', f'요청 제한에 걸려 최근 실거래 요약을 받지 못했습니다 ({exc.message}). {unknown}')
    if isinstance(exc, ValueError) or (isinstance(exc, HTTPStatusError) and exc.response.status_code < 500):
        return note('실패', f'다방이 최근 실거래 요약 요청을 거절했거나 응답 형식이 바뀌었습니다. {unknown}. {UPDATE_MAYBE_NEEDED}')
    return note('실패', f'다방 최근 실거래 요약 요청이 실패했습니다 ({type(exc).__name__}). 잠시 뒤 다시 시도하세요. {unknown}')


def get_complex(client: DabangClient, complex_id: str) -> DabangComplexDetail:
    """단지 정보 (요청 2회: 단지 상세 + 최근 실거래 요약). 사진·관리사무소 전화·광고 중개사는 옮기지 않는다.

    최근 실거래 요약은 덤이라 실패해도 단지 정보는 돌려주고 recent_sale·recent_lease 를 모름(null)으로 둔다.
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
        notes.append(_summary_failure_note(exc))
    education = result.education
    schools = None
    if education is not None:
        # 중·고등학교는 거리순으로 온다 (2026-10-25 실측: 은마 중 17곳·고 22곳, 오피스텔 중 7곳·고 22곳)
        schools = (
            [_school(school, '초등학교') for school in education.elementary_school]
            + [_school(school, '중학교') for school in education.middle_school[:NEAREST_SCHOOLS]]
            + [_school(school, '고등학교') for school in education.high_school[:NEAREST_SCHOOLS]]
        )
    approved = info.building_approval_date_name
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
        pyeongs=[
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
        primary_space_seq=result.primary_space_seq,
        area_prices=[
            DabangAreaPrice(
                scope=price.scope,
                sale_per_pyeong_manwon=price.trade_average_pyeong_price,
                lease_per_pyeong_manwon=price.lease_average_pyeong_price,
            )
            for price in result.area_average_price
        ],
        recent_sale=_recent(summary.sell_lately_price, result.spaces) if summary else None,
        recent_lease=_recent(summary.lease_lately_price, result.spaces) if summary else None,
        schools=schools,
        url=complex_url(info.complex_id),
        notes=notes,
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
        Field(description='다방 목록 순 매물')
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
    limit: int,
) -> DabangComplexListingsResult:
    """단지 하나의 매물 (다방 목록 순, 24건씩). 요청은 단지 상세 1회 + 쪽마다 1회.

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    conditions = conditions or DabangListingConditions()
    result = fetch_complex(client, complex_id)
    category = _category_of(result)
    kind = LISTING_KIND_BY_CATEGORY[category]
    all_seqs = [space.space_seq for space in result.spaces]
    unknown = [seq for seq in space_seqs or [] if seq not in all_seqs]
    if unknown:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"이 단지에 없는 평형 번호입니다: {', '.join(map(str, unknown))}",
            hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].space_seq 를 주세요',
        )
    filters = filters_of(kind, conditions)
    assert isinstance(filters, DabangAptFiltersModel | DabangOfficetelFiltersModel)  # 단지는 아파트·오피스텔뿐이다
    room_filters = DabangComplexRoomFiltersModel(
        selling_type_list=filters.selling_type_list,
        # 단지 상세는 평형을 늘 하나 이상 준다 (2026-10-25 실측: 아파트·오피스텔·주상복합·재건축 62곳 모두).
        # 평형 없는 단지는 보지 못해 따로 다루지 않는다
        space_seq_list=space_seqs or all_seqs,
    )
    listings: list[DabangListing] = []
    received = premium = unreadable = duplicate = 0
    # 단지 목록(`search_complexes`)처럼 쪽이 겹칠 수 있어 같은 매물은 한 번만 넣는다. 다방 단지 매물은 적어 둘째 쪽을 실제로
    # 받아 보지 못했다 (2026-10-26 실측: 가장 많은 곳이 아파트 14건 잠실 우성4차·개포 현대2차, 오피스텔 8건 빅토리아)
    seen_ids: set[str] = set()
    total: int | None = None
    has_more = False
    page = 1
    while len(listings) + unreadable + duplicate < limit and page <= MAX_LIST_PAGES:
        page_result = client.run_request_room_list_category_complex_v5(DabangRoomListCategoryComplexV5RequestParameterModel(
            category=category, complex_id=complex_id, main_filters=filters, filters=room_filters, page=page,
        )).result
        if page_result is None:
            break
        total = page_result.total if total is None else total
        premium += sum(len(group.room_list) for group in page_result.premium_list)
        rows = page_result.room_list[:limit - received]
        for item in rows:
            received += 1
            if item.id in seen_ids:
                duplicate += 1
                continue
            seen_ids.add(item.id)
            listing = room_item_to_listing(item, kind)
            if listing is None:
                unreadable += 1
                continue
            listings.append(listing)
        has_more = len(rows) < len(page_result.room_list) or bool(page_result.has_more)
        if not page_result.has_more or len(page_result.room_list) < PAGE_SIZE:
            break
        page += 1
    notes: list[str] = []
    if unreadable:
        notes.append(note('제외', f'가격·거래 유형을 읽지 못한 {unreadable}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}'))
    if duplicate:
        notes.append(note('제외', f'다방이 다음 쪽에 다시 준 매물 {duplicate}건은 한 번만 넣었습니다 (다시 채우지 않음)'))
    notes += premium_note(premium)
    notes += limit_notes(total, len(listings), limit, order='다방 목록 순', inspected=received, has_more=has_more)
    return DabangComplexListingsResult(
        complex_id=complex_id,
        name=result.complex.complex_name,
        space_seqs=space_seqs,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
    )

