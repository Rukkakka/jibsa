"""매물 검색 (search listings room·villa·officetel·apt) 과 매물 상세 (listing)."""

from datetime import datetime

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
    within_radius,
)
from jibsa.core.listing import (
    KST,
    UPDATE_MAYBE_NEEDED,
    Listing,
    ListingDetail,
    TradeType,
    limit_notes,
    listing_as,
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    note,
    parking_label,
    won_to_manwon,
    years_ago,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    DabangBboxModel,
    DabangListFilters,
    DabangSearchType,
)
from jibsa.providers.dabang.api.request.listing import (
    DabangNewRoomDetailV3RequestParameterModel,
    DabangRoomGetRoomIdV3RequestParameterModel,
    DabangRoomListCategoryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.common import DabangRoomItemModel
from jibsa.providers.dabang.api.response.listing import DabangNewRoomDetailRoomModel
from jibsa.providers.dabang.service.common import (
    CATEGORY_BY_KIND,
    LISTING_NUMBER_PATTERN,
    MAX_LIST_LIMIT,
    OFFICETEL_TYPE,
    SOURCE,
    ZOOM_BY_SEARCH_TYPE,
    DabangListing,
    DabangListingConditions,
    DabangPage,
    DabangPages,
    DabangPlace,
    ListingKind,
    bbox_of,
    fetch_pages,
    filters_of,
    floor_label,
    is_complex_type,
    is_missing_id,
    listing_url,
    manwon_from_text,
    page_cap_note,
    premium_note,
    room_item_to_listing,
    room_type_of,
)
from jibsa.providers.dabang.service.region import dong_bbox

from typing import (
    Annotated,
    Any,
    NamedTuple,
)


# 상세 화면이 '비공개 처리된 매물' 로 닫는 상태 (room 청크 `[0,3,4].includes(t.room.status)`, 2026-10-25)
HIDDEN_STATUSES: frozenset[int] = frozenset({0, 3, 4})
TRADE_BY_SELLING_CODE: dict[int, TradeType] = {0: '월세', 1: '전세', 2: '매매'}
# 관리비 포함 항목 코드 → 이름 (listing-request 청크의 표, 2026-10-25)
MANAGE_ITEM_LABELS: dict[str, str] = {
    'PUBLIC_USE_RATES': '공용 관리비',
    'ELECTRIC_RATES': '전기',
    'WATER_RATES': '수도',
    'INTERNET_RATES': '인터넷',
    'HEATING_RATES': '난방',
    'GAS_RATES': '가스',
    'TV_RATES': 'TV',
    'ETC_USE_RATES': '기타 관리비',
}
# 정액 관리비 세부 항목 코드 → 이름 (listing-request 청크의 표 F01 공용·F11 전기 … F99 기타, 2026-10-26). 이름은 위 표와 맞춘다
FIXED_FEE_ITEM_LABELS: dict[str, str] = {
    'F01': '공용 관리비',
    'F11': '전기',
    'F12': '수도',
    'F13': '가스',
    'F14': '난방',
    'F15': '인터넷',
    'F16': 'TV',
    'F99': '기타 관리비',
}
# 정액 관리비 세부 항목 중 관리비에 든 정액. 나머지(ACTUAL_EXPENSE)는 웹에 '실비' 로 보이고 따로 낸다
FIXED_FEE_TYPE: str = 'FIXED_FEE'
# 공용(F01)은 정액·실비 표시와 상관없이 웹이 금액과 함께 보여 주고 관리비 합계에 넣는다 (safety-option-chunk `E` 의 `h`, 2026-11-13)
COMMON_FEE_CODE: str = 'F01'
# 관리비 부과 방식 (safety-option-chunk `w`, 2026-11-13). 웹은 확인불가에는 표시를 붙이지 않고 상세보기에 '확인불가' 로 쓴다
MANAGE_CHARGE_TYPE_LABELS: dict[str, str] = {
    'FIXED_FEE_CHARGE': '정액관리비',
    'ETC_FEE_CHARGE': '기타부과',
    'UNABLE_CHECK': '확인불가',
}
FIXED_FEE_CHARGE: str = 'FIXED_FEE_CHARGE'
ETC_FEE_CHARGE: str = 'ETC_FEE_CHARGE'
# 웹이 관리비 상세보기(항목별)를 여는 입력 방식. 그 밖(SIMPLE)은 포함 항목 글(maintenance_items_str)만 괄호로 보인다 (room-chunk)
DETAIL_INPUT_TYPE: str = 'DETAIL'
# 정액관리비 중 항목마다 정액·실비를 적은 세부 종류 (세부 종류가 없거나 비어도 웹은 이쪽으로 본다). 10만원 미만(BELOW_…)·세부
# 미고지(ABOVE_…_NO_DETAILS) 정액관리비와 기타부과는 포함 항목 코드(maintenance_etc_fee_charge_detail)로 보인다
ITEMIZED_FIXED_FEE_DETAIL_TYPE: str = 'ABOVE_FIXED_FEE_THRESHOLD'
# 에어컨 종류 옵션. 웹은 에어컨 목록(airConditionerTypeList)의 이름을 '에어컨' 없이 옵션에 섞어 보여 준다 (listing-request 청크)
AIR_CONDITIONER_OPTIONS: frozenset[str] = frozenset({'벽걸이형', '스탠드형', '천장형'})
ELEVATOR_BY_TEXT: dict[str, bool] = {'있음': True, '없음': False}
# --details 로 상세를 붙이는 매물 수 (직방·당근과 같다). 한 건에 요청 1회
DETAILS_MAX: int = 30


class DabangDetailedListing(DabangListing):
    """`--details` 로 매물 상세를 1회 더 받아 사용승인일(`approved_at`)을 채우고 건물 용도를 붙인 목록 매물."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (단독주택, 공동주택, 근린생활시설 ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다. 모르면 null')
    ] = None


class DabangListingDetail(ListingDetail):
    """다방 매물 상세. 단기임대는 월세 매물에 붙는 표시라 `short_lease_term` 으로 받는 기간을 알린다."""

    listing_number: Annotated[
        int | None,
        Field(description='다방 화면의 매물번호')
    ] = None
    manage_cost_charge_type: Annotated[
        str | None,
        Field(description="관리비 부과 방식 (다방 표시 '정액관리비'·'기타부과'·'확인불가'). 모르면 null")
    ] = None
    manage_cost_excludes: Annotated[
        list[str] | None,
        Field(description="관리비에 들지 않고 실비로 따로 내는 항목 (다방 상세보기의 '실비', 예 ['전기', '수도']). 정액관리비를 항목마다 적은 매물만 알고 그 밖은 null")
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 공급 + 주차장 등 기타 공용. 다방이 오피스텔에 주는 값). 오피스텔에만 키가 있고 모르면 null')
    ] = None
    with_tenant: Annotated[
        bool,
        Field(description='세입자를 끼고 파는 매매 (다방 기 보증금/월세 표시). 매매만')
    ] = False
    tenant_deposit_manwon: Annotated[
        float | None,
        Field(description='세입자 낀 매매의 기존 보증금·전세금 (만원). with_tenant 가 true 일 때만 키가 있고 읽지 못하면 null')
    ] = None
    tenant_rent_manwon: Annotated[
        float | None,
        Field(description='세입자 낀 매매의 기존 월세 (만원). 기존 세입자가 월세일 때만 키가 있다')
    ] = None
    lh_lease: Annotated[
        bool,
        Field(description='LH 전세임대 가능 (다방 표시). 매매는 키가 없다')
    ] = False
    leasehold_registration: Annotated[
        bool,
        Field(description='임차권 등기명령 매물 (다방 경고: 기존 임차인의 권리가 우선 적용되니 확인 후 거래)')
    ] = False
    unregistered_building: Annotated[
        bool,
        Field(description="미등기 건물 (다방 '미등기건물' 표시)")
    ] = False
    non_compliant_building: Annotated[
        bool | None,
        Field(description="위반건축물 여부 (다방 '해당'·'해당없음'). 다방이 알려 주지 않으면 null")
    ] = None
    short_lease_term: Annotated[
        str | None,
        Field(description="단기임대를 받는 기간 (예 '1개월(이상 협의가능)'). 단기임대를 받지 않는 매물은 키가 없다")
    ] = None
    direction_criterion: Annotated[
        str | None,
        Field(description='방향 기준 (안방·거실)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 (개별난방 등)')
    ] = None
    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (단독주택, 공동주택, 근린생활시설 ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다')
    ] = None
    loan: Annotated[
        str | None,
        Field(description="융자 (예 '시세대비 30%미만'). 모르면 null")
    ] = None
    safety: Annotated[
        list[str] | None,
        Field(description='보안 시설 (CCTV, 현관보안 ...)')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (오피스텔·아파트). dabang complex·search listings --complex 에 넘긴다')
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.trade_type != '월세' or self.short_lease_term is None:
            fields = fields | {'short_lease_term'}
        # 상세 유형은 '오피스텔(분리형)'·'원룸(분리형,복층)' 처럼 구조를 붙여 온다 (2026-10-25 실측). 다방이 단지 ID 를 주면
        # 유형과 상관없이 두고, 없을 때만 유형으로 해당 없음(키 삭제)과 모름(null)을 가른다
        if self.complex_id is None and not is_complex_type(self.property_type):
            fields = fields | {'complex_id'}
        # 다방은 계약면적을 오피스텔에만 주고 다른 유형은 0 으로 준다 (2026-11-13 실측: 상세 46건 중 오피스텔 5건만 값이 있다).
        # 오피스텔인데 값이 없으면 해당 없음이 아니라 모름(null)이라 키를 둔다 (공급면적과 같다)
        if self.contract_area_m2 is None and not self.property_type.startswith(OFFICETEL_TYPE):
            fields = fields | {'contract_area_m2'}
        # 세입자 낀 매물·LH 전세임대는 웹이 거래 유형과 상관없이 표시만 보고 보여 준다. 해당 없는 거래는 키를 빼되 다방이
        # 표시를 붙였으면 웹처럼 둔다
        if self.trade_type != '매매' and not self.with_tenant:
            fields = fields | {'with_tenant'}
        if not self.with_tenant:
            fields = fields | {'tenant_deposit_manwon', 'tenant_rent_manwon'}
        elif self.tenant_deposit_manwon is not None and self.tenant_rent_manwon is None:
            # 기존 세입자가 전세라 월세가 없다 ('20억')
            fields = fields | {'tenant_rent_manwon'}
        if self.trade_type == '매매' and not self.lh_lease:
            fields = fields | {'lh_lease'}
        return fields


class DabangListPosition(BaseModel):
    """매물 검색을 이어 받을 위치 (`--next`). 받은 매물 수가 아니라 다방 쪽 번호와 그 쪽에서 쓴 칸으로 기억한다.

    다방 목록은 번호 쪽 넘김이고 한 쪽이 24건보다 적게 올 때가 있다 (2026-11-13 웹 캡처: 아파트 강남역 1쪽 23건, 대치동 2쪽
    23건). 예전처럼 받은 수로 쪽을 셈하면(`수 // 24 + 1` 쪽의 `수 % 24` 번째) 23건짜리 1쪽 뒤에 2쪽 첫 건까지 받아 24건을
    주고, 다음 호출이 2쪽을 처음부터 다시 받아 같은 매물이 또 나왔다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    page: Annotated[
        int,
        Field(ge=1, description='다음에 물을 다방 쪽 번호')
    ] = 1
    skip: Annotated[
        int,
        Field(ge=0, description='그 쪽에서 앞 결과가 이미 쓴 칸 수 (그다음 칸부터 받는다)')
    ] = 0
    received: Annotated[
        int,
        Field(ge=0, description="앞 결과들까지 받은 매물 수. '[일부] N번째부터' 안내에만 쓴다")
    ] = 0
    bbox: Annotated[
        DabangBboxModel | None,
        Field(description='아파트 동 검색의 동 경계 사각형. 남기면 이어 받을 때 경계를 다시 받지 않는다')
    ] = None


class DabangSearchResult(BaseModel):
    """매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치')
    ]
    scope: Annotated[
        str,
        Field(description="찾은 범위 ('역삼동 안', '강남역 다방 역 반경 750m', '반경 1km')")
    ]
    radius_km: Annotated[
        float | None,
        Field(description='반경 (km). 역·좌표·--radius 검색만')
    ] = None
    total: Annotated[
        int | None,
        Field(description='다방이 센 범위 안 매물 수 (limit·jibsa 제외 전). 반경·아파트 동 검색은 반경·동을 덮는 사각형 안의 수다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='같은 조건으로 더 받을 매물이 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        DabangListPosition | None,
        Field(exclude=True, description='이어 받을 위치 (다음 쪽 번호·그 쪽에서 쓴 칸·받은 수). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[SerializeAsAny[Listing]],
        Field(description='다방 목록 순 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='범위·제외·일부 안내. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_radius(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.radius_km is None:
            data.pop('radius_km', None)
        return data


class _Target(NamedTuple):
    """다방에 물을 범위 (동 하나, 역 하나, 대학 하나, 지도 범위 하나)."""

    search_type: DabangSearchType
    code: str | None = None
    place_id: int | None = None
    bbox: DabangBboxModel | None = None


class _Fetched(NamedTuple):
    pages: DabangPages[DabangRoomItemModel]
    # 목록과 함께 온 광고(중개사별 추천 매물) 수
    premium: int


def _fetch(
    client: DabangClient,
    kind: ListingKind,
    target: _Target,
    filters: DabangListFilters,
    *,
    budget: int,
    page: int,
    skip: int,
) -> _Fetched:
    """범위 하나에서 `page` 쪽의 `skip` 칸 뒤부터(다방 목록 순) `budget` 건을 받는다 (쪽 따라가기는 `fetch_pages`)."""
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
        # 광고는 첫 쪽에만 와서 쪽마다 더해도 같은 광고를 두 번 세지 않는다 (2026-10-28 실측: 역삼동 원룸 1~3쪽 광고 8·0·0건)
        premium += sum(len(group.room_list) for group in result.premium_list)
        return DabangPage(result.room_list, result.total, bool(result.has_more))

    pages = fetch_pages(fetch, budget, page=page, skip=skip)
    return _Fetched(pages, premium)


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
            'approved_at 으로 확인하세요',
        ))

    addresses = {place.gid: place.address} if place.gid is not None and place.address else {}
    fetched = _fetch(
        client, kind, target, filters_of(kind, conditions), budget=limit, page=resume.page, skip=resume.skip,
    )
    pages = fetched.pages
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
        page=pages.page, skip=pages.skip, received=resume.received + len(pages.rows), bbox=bbox,
    ) if has_more else None
    # 더 받을 매물이 없으면 '다시 채우지 않음' 이라 하지 않는다. 그 말에 더 있는지 헷갈렸다 (2026-11-11 LLM 사용 시험: 반곡동
    # 아파트 7건 중 다른 동 4건을 빼고 has_more false)
    refill = '(뺀 만큼 다시 채우지 않음)' if has_more else '(더 받을 매물 없음)'
    if outside:
        notes.append(note('제외', f'반경을 덮는 사각형에서 받은 매물 중 반경 {filter_radius:g}km 밖 {outside}건을 뺐습니다 {refill}'))
    if other_dong:
        notes.append(note('제외', f'동 경계를 덮는 사각형에서 받은 매물 중 다른 동 {other_dong}건을 뺐습니다 {refill}'))
    if unreadable:
        notes.append(note('제외', f'가격·거래 유형을 읽지 못한 {unreadable}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}'))
    if duplicate:
        notes.append(note('제외', f'다방 목록에 두 번 나온 매물 {duplicate}건은 한 번만 넣었습니다 (다시 채우지 않음)'))
    notes += premium_note(fetched.premium)
    notes += limit_notes(
        pages.total, len(collected), limit, max_limit=MAX_LIST_LIMIT, narrow=f"조건·{'반경' if radius_km is not None else '지역'}",
        order='다방 목록', approximate=approximate, inspected=len(pages.rows), offset=resume.received,
        resumable=has_more, has_more=has_more,
    )
    if pages.capped:
        notes.append(page_cap_note(len(pages.rows), limit, next_step='결과의 next 로 이어 받으세요'))
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


def _price_fields(room: DabangNewRoomDetailRoomModel, trade_type: TradeType) -> dict[str, float]:
    """`price_info` 에서 그 거래 유형 칸의 금액. 칸은 [보증금 또는 매매가, 월세, 거래 유형 코드] 다.

    맞는 칸이 없으면 금액을 모름(null)으로 둔다. 다른 거래 유형 칸의 금액을 이 거래의 가격으로 내지 않는다
    (2026-10-26 실측: 역삼동 빌라 월세 1건·전세 2건 모두 거래 유형 코드가 맞는 칸 하나뿐).
    """
    code = room.selling_type
    entry = next((row for row in room.price_info if len(row) >= 3 and int(row[2]) == code), None)
    if entry is None:
        return {}
    if trade_type == '월세':
        return {'deposit_manwon': entry[0], 'rent_manwon': entry[1]}
    if trade_type == '전세':
        return {'deposit_manwon': entry[0]}
    return {'price_manwon': entry[0]}


class _ManageCost(NamedTuple):
    manwon: float | None
    includes: list[str] | None
    excludes: list[str] | None


def _manage_cost(room: DabangNewRoomDetailRoomModel) -> _ManageCost:
    """월 관리비(만원), 포함 항목, 실비로 따로 내는 항목. 웹 관리비 칸과 상세보기(safety-option-chunk `E`, room-chunk)를 따른다.

    관리비가 '없음' 이면 0 과 포함 항목 [], 금액은 있는데 항목을 모르면 항목 None. 실비 항목은 정액관리비를 항목마다 적은
    매물만 안다.
    """
    if room.maintenance_cost is None:
        if (room.maintenance_cost_str or '').strip() == '없음':
            return _ManageCost(0.0, [], None)
        return _ManageCost(None, None, None)
    cost = won_to_manwon(room.maintenance_cost)
    if room.maintenance_input_type != DETAIL_INPUT_TYPE:
        # 웹은 세부 입력이 아닌 매물(입력 방식이 없으면 SIMPLE 로 본다)에 포함 항목 글만 괄호로 보여 준다
        return _ManageCost(cost, list(room.maintenance_items_str) or None, None)
    charge = room.maintenance_charge_type
    fixed_items = room.maintenance_fixed_fee_charge_detail_list
    detail_type = room.maintenance_charge_detail_type
    if charge == FIXED_FEE_CHARGE and (not detail_type or detail_type == ITEMIZED_FIXED_FEE_DETAIL_TYPE):
        if not fixed_items:
            return _ManageCost(cost, None, None)
        # 항목마다 정액(관리비에 듦)·실비(따로 냄)로 온다. 공용(F01)은 실비로 와도 웹이 금액과 함께 보여 주고 관리비 합계에 넣어
        # 든 항목으로 본다. 예전에는 정액 항목만 넣어, 공용이 실비로 온 매물이 '포함 항목 없음' 으로 읽혔다 (2026-11-13 웹 대조:
        # 6ae45e683b53321aea64a773 관리비 20만원, 상세보기 '공용 200,000원 · 사용료 실비')
        includes: list[str] = []
        excludes: list[str] = []
        for item in fixed_items:
            included = item.detail_code == COMMON_FEE_CODE or item.detail_cost_formulated_type == FIXED_FEE_TYPE
            (includes if included else excludes).append(FIXED_FEE_ITEM_LABELS.get(item.detail_code, item.detail_code))
        return _ManageCost(cost, includes, excludes)
    if charge in (FIXED_FEE_CHARGE, ETC_FEE_CHARGE) and room.maintenance_etc_fee_charge_detail is not None:
        # 10만원 미만·세부 미고지 정액관리비와 기타부과는 '포함 항목' 코드만 온다. 따로 내는 항목은 웹도 보여 주지 않는다
        codes = room.maintenance_etc_fee_charge_detail.detail_include_types
        return _ManageCost(cost, [MANAGE_ITEM_LABELS.get(code, code) for code in codes] or None, None)
    # 확인불가는 웹도 항목을 보여 주지 않는다
    return _ManageCost(cost, None, None)


def _tenant_prices(title: str | None) -> dict[str, float | None]:
    """세입자 낀 매매의 기존 보증금/월세 글('20억', '1억/50')을 만원으로. 읽지 못하면 둘 다 None (모름)."""
    # 리뷰 오탐 (2026-11-14): 금액 글자 읽기는 manwon_from_text 하나가 맡고 여기는 거래 유형 없이 조각 수로 보증금/월세를
    # 정해(읽지 못하면 두 키 null) listing_prices(거래 유형별, 못 읽으면 None)와 계약이 다르다.
    values = [manwon_from_text(part) for part in (title or '').split('/')]
    if len(values) == 1 and values[0] is not None:
        return {'tenant_deposit_manwon': values[0]}
    if len(values) == 2 and None not in values:
        return {'tenant_deposit_manwon': values[0], 'tenant_rent_manwon': values[1]}
    return {'tenant_deposit_manwon': None, 'tenant_rent_manwon': None}


def resolve_listing_id(client: DabangClient, listing_ref: str) -> str:
    """매물 ID 를 그대로, 매물번호(숫자)는 매물 ID 로 바꿔 돌려준다 (요청 1회).

    Raises:
        ListingUnavailableError: 매물번호에 해당하는 매물이 없을 때.
    """
    if not LISTING_NUMBER_PATTERN.fullmatch(listing_ref):
        return listing_ref
    try:
        found = client.run_request_room_get_room_id_v3(DabangRoomGetRoomIdV3RequestParameterModel(seq=int(listing_ref)))
    except HTTPStatusError as exc:
        if is_missing_id(exc, in_path=False):
            # 400 '존재하지 않는 방입니다.' 는 없는 번호라 사유를 넘기지 않는다. 사유가 있으면 다른 소스 ID 힌트가 빠진다
            # (2026-10-25 실측: 직방 ID 47123456 을 넣으면 이 응답)
            raise ListingUnavailableError(SOURCE, listing_ref) from None
        raise
    if not found.room_id:
        raise ListingUnavailableError(SOURCE, listing_ref)
    # 응답 room_id 를 그대로 상세 요청(24자리 16진수)에 넣는다. 매물 ID 꼴로만 와서 형식을 따로 막지 않는다 (core/schema.py,
    # 2026-10-26 실측: 매물번호 55861462 → 69aa437a89300d7e5b7251a9)
    return found.room_id


def get_listing(client: DabangClient, listing_ref: str) -> DabangListingDetail:
    """매물 상세 (요청 1회, 매물번호면 2회). 본문·중개사·사진·좌표는 옮기지 않는다.

    Raises:
        ListingUnavailableError: 없는 매물(400 "존재하지 않는 매물입니다."), 비공개(status 0·3·4), 계약 완료,
            모르는 거래 유형.
    """
    room_id = resolve_listing_id(client, listing_ref)
    try:
        response = client.run_request_new_room_detail_v3(DabangNewRoomDetailV3RequestParameterModel(room_id=room_id))
    except HTTPStatusError as exc:
        if is_missing_id(exc, in_path=False):
            # 400 '존재하지 않는 매물입니다.' 도 없는 ID 라 사유를 넘기지 않는다 (`resolve_listing_id` 와 같다)
            raise ListingUnavailableError(SOURCE, listing_ref) from None
        raise
    room = response.room
    if room.status in HIDDEN_STATUSES:
        raise ListingUnavailableError(SOURCE, listing_ref, status=str(room.status))
    if room.is_contract:
        raise ListingUnavailableError(SOURCE, listing_ref, status='contract')
    trade_type = TRADE_BY_SELLING_CODE.get(room.selling_type if room.selling_type is not None else -1)
    if trade_type is None:
        raise ListingUnavailableError(SOURCE, listing_ref, reason='UNKNOWN_TRADE_TYPE')
    manage = _manage_cost(room)
    charge = room.maintenance_charge_type
    parking_count = room.parking_num
    # 웹은 이 표시들이 없으면(null) 없는 것으로 보고 아무것도 보여 주지 않는다 (safety-option-chunk 의 `?? false`). 위반건축물만
    # null 이면 그 줄을 감추고 true·false 를 '해당'·'해당없음' 으로 보여 준다 (room-chunk, 2026-11-13)
    with_tenant = bool(room.is_take_tenant)
    return DabangListingDetail(
        source=SOURCE,
        id=room.id,
        url=listing_url(room.id),
        trade_type=trade_type,
        property_type=room.room_type_str or '매물',
        room_type=room_type_of(room.room_type_str),
        title=room.title,
        manage_cost_manwon=manage.manwon,
        manage_cost_includes=manage.includes,
        manage_cost_charge_type=MANAGE_CHARGE_TYPE_LABELS.get(charge, charge) if charge else None,
        manage_cost_excludes=manage.excludes,
        area_m2=room.room_size,
        area_pyeong=m2_to_pyeong(room.room_size),
        # 오피스텔은 공급면적 칸에 0 을 주기도 한다 (2026-10-26 실측: 강남역투웨니퍼스트 6ad6eb6fcac3561f038ec567). 모름이다
        supply_area_m2=room.provision_size or None,
        # 다른 유형은 계약면적을 0 으로 준다. 웹은 오피스텔에 '전용/계약면적' 으로 보여 준다 (room-chunk)
        contract_area_m2=room.contract_size or None,
        with_tenant=with_tenant,
        **(_tenant_prices(room.take_tenant_price_title) if with_tenant else {}),
        lh_lease=bool(room.is_lh_lease),
        leasehold_registration=bool(room.is_leasehold),
        unregistered_building=bool(room.is_new_construction),
        non_compliant_building=room.is_non_compliant_building,
        floor=floor_label(room.room_floor_str),
        building_floor=floor_label(room.building_floor_str),
        address=room.full_jibun_address_str,
        registered_at=normalize_date(room.saved_time_str),
        approved_at=normalize_date(room.building_approval_date_str),
        room_count=room.beds_num,
        bathroom_count=room.bath_num,
        direction=room.direction_str,
        direction_criterion=room.direction_measurement_base_type_str,
        move_in=move_in_label(room.moving_date),
        parking=parking_label(room.parking, f'총 {parking_count:g}대' if parking_count else None),
        elevator=ELEVATOR_BY_TEXT.get(room.elevator_str or ''),
        options=None if room.room_options is None else [
            f'{option.name} 에어컨' if option.name in AIR_CONDITIONER_OPTIONS else option.name for option in room.room_options
        ],
        safety=None if room.safeties is None else [safety.name for safety in room.safeties],
        heating=room.heating,
        residence_type=', '.join(room.building_use_types_str) or None,
        loan=None if room.loan_str in (None, '', '-') else room.loan_str,
        short_lease_term=room.short_lease_str,
        complex_id=room.complex_id,
        listing_number=room.seq,
        **_price_fields(room, trade_type),
    )



def attach_details(
    client: DabangClient,
    result: DabangSearchResult,
    *,
    built_within_years: int | None = None,
) -> DabangSearchResult:
    """목록 앞 `DETAILS_MAX` 건에 상세(`get_listing`, 1회씩)의 사용승인일과 건물 용도를 붙인다 (`--details`).

    목록 칸에는 사용승인일이 없어 `--built-within`(연도로 센다) 결과를 날짜로 따지려면 매물마다 상세를 열어야 했다
    (2026-10-31 에이전트 검증: opus 두 번 모두 역삼동 원룸 17건의 상세를 하나씩 불렀다). 상세에서 내려간 매물은 뺀다
    (만료 매물은 내보내지 않는다). 31번째부터는 사용승인일·건물 용도를 모름(null)으로 둔다.
    `built_within_years` 를 주면 오늘 기준 그 햇수가 넘은 매물을 승인일과 함께 `notes` 로 짚는다 (빼지는 않는다. 서버 필터
    결과라 다시 거르지 않는다). 연도 기준 안내만 보고 2016-02 승인 건물을 '10년 이내' 로 추천한 일이 있었다 (2026-10-31 재검증).
    """
    listings: list[Listing] = []
    gone = 0
    for index, listing in enumerate(result.listings):
        if not isinstance(listing, DabangListing):
            listings.append(listing)
            continue
        if index >= DETAILS_MAX:
            listings.append(listing_as(DabangDetailedListing, listing))
            continue
        try:
            detail = get_listing(client, listing.id)
        except ListingUnavailableError:
            gone += 1
            continue
        dated = listing.model_copy(update={'approved_at': detail.approved_at or listing.approved_at})
        listings.append(listing_as(DabangDetailedListing, dated, residence_type=detail.residence_type))
    notes = []
    if gone:
        # 검색이 만든 안내('이 N건이 전부입니다' 등)는 빼기 전 개수라 returned 와 다를 수 있다
        notes.append(note('제외', f'{gone}건은 상세를 보니 거래가 끝나 뺐습니다 (앞 안내의 건수는 빼기 전 기준)'))
    if len(result.listings) > DETAILS_MAX:
        notes.append(f'사용승인일·건물 용도(--details)는 앞 {DETAILS_MAX}건에만 붙였습니다')
    if built_within_years is not None:
        cutoff = years_ago(datetime.now(KST).date(), built_within_years)
        older = [listing for listing in listings if listing.approved_at and listing.approved_at < cutoff]
        if older:
            notes.append(note(
                '참고',
                f'이 중 {len(older)}건은 오늘 기준 {built_within_years}년이 넘었습니다 ({cutoff} 전 승인): '
                + ', '.join(f'{listing.id}({listing.approved_at})' for listing in older),
            ))
    return result.model_copy(update={'listings': listings, 'returned': len(listings), 'notes': result.notes + notes})
