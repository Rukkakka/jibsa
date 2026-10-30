"""매물 검색 (search listings room·villa·officetel·apt) 과 매물 상세 (listing)."""

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
from jibsa.core.korean import particle
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    Listing,
    ListingDetail,
    TradeType,
    limit_notes,
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    note,
    parking_label,
    won_to_manwon,
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
    MAX_LIST_PAGES,
    PAGE_SIZE,
    SOURCE,
    ZOOM_BY_SEARCH_TYPE,
    DabangListing,
    DabangListingConditions,
    DabangPlace,
    ListingKind,
    bbox_of,
    filters_of,
    floor_label,
    is_complex_type,
    is_missing_id,
    listing_url,
    middle_place,
    premium_note,
    room_item_to_listing,
    room_type_of,
)
from jibsa.providers.dabang.service.region import dongs_bbox

from typing import (
    Annotated,
    Any,
    NamedTuple,
)


# 한 번 검색에 받을 수 있는 쪽 수 (--limit 최대값을 채우는 쪽 수, 첫 쪽을 중간부터 받으면 한 쪽 더)
MAX_PAGES_PER_TARGET: int = MAX_LIST_PAGES + 1
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
# 정액 관리비 세부 항목 중 관리비에 든 항목. 나머지(ACTUAL_EXPENSE)는 실비로 따로 낸다
FIXED_FEE_TYPE: str = 'FIXED_FEE'
# 에어컨 종류 옵션. 웹은 에어컨 목록(airConditionerTypeList)의 이름을 '에어컨' 없이 옵션에 섞어 보여 준다 (listing-request 청크)
AIR_CONDITIONER_OPTIONS: frozenset[str] = frozenset({'벽걸이형', '스탠드형', '천장형'})
ELEVATOR_BY_TEXT: dict[str, bool] = {'있음': True, '없음': False}


class DabangListingDetail(ListingDetail):
    """다방 매물 상세. 단기임대는 월세 매물에 붙는 표시라 `short_lease_term` 으로 받는 기간을 알린다."""

    listing_number: Annotated[
        int | None,
        Field(description='다방 화면의 매물번호')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
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
        return fields


class DabangSearchResult(BaseModel):
    """매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치 (동을 여럿 합쳐 찾았으면 첫 동, 이름은 합친 이름)')
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
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"offsets": {범위: 받은 수}}). 더 없으면 None')
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
    """다방에 물을 범위 하나 (동 하나, 역 하나, 지도 범위 하나)."""

    key: str
    search_type: DabangSearchType
    code: str | None = None
    place_id: int | None = None
    bbox: DabangBboxModel | None = None


class _Fetched(NamedTuple):
    items: list[DabangRoomItemModel]
    total: int | None
    has_more: bool
    premium: int
    # 마지막 쪽에서 몫을 넘어 받지 않은 칸과 그 뒤에 쪽이 더 있는지. 남은 몫을 더 받을 때 같은 쪽을 다시 묻지 않는다
    spare: tuple[DabangRoomItemModel, ...] = ()
    more_pages: bool = False



def _fetch(
    client: DabangClient,
    kind: ListingKind,
    target: _Target,
    filters: DabangListFilters,
    *,
    start: int,
    budget: int,
    previous: _Fetched | None = None,
) -> _Fetched:
    """범위 하나에서 `start` 번째(다방 목록 순)부터 `budget` 건을 받는다. 한 쪽이 24건 고정이라 쪽 중간부터도 받는다.

    `previous` 는 같은 범위를 이번 검색에서 앞서 받은 결과다. 그 마지막 쪽에 남긴 칸을 먼저 쓰고, 모자랄 때만 다음 쪽을 묻는다.
    """
    items: list[DabangRoomItemModel] = []
    if previous is not None:
        items = list(previous.spare[:budget])
        if len(items) >= budget or not previous.more_pages:
            left = previous.spare[len(items):]
            return _Fetched(items, None, bool(left) or previous.more_pages, 0, left, previous.more_pages)
        start += len(previous.spare)
    total: int | None = None
    premium = 0
    page, skip = start // PAGE_SIZE + 1, start % PAGE_SIZE
    spare: tuple[DabangRoomItemModel, ...] = ()
    more_pages = False
    for _ in range(MAX_PAGES_PER_TARGET):
        if len(items) >= budget:
            break
        result = client.run_request_room_list_category_v5(DabangRoomListCategoryV5RequestParameterModel(
            category=CATEGORY_BY_KIND[kind],
            search_type=target.search_type,
            filters=filters,
            code=target.code,
            id=target.place_id,
            bbox=target.bbox,
            zoom=ZOOM_BY_SEARCH_TYPE[target.search_type],
            page=page,
        )).result
        if result is None:
            break
        if total is None:
            total = result.total
        # 광고는 첫 쪽에만 와서 쪽마다 더해도 같은 광고를 두 번 세지 않는다 (2026-10-28 실측: 역삼동 원룸 1~3쪽 광고 8·0·0건)
        premium += sum(len(group.room_list) for group in result.premium_list)
        rows = result.room_list[skip:]
        taken = rows[:budget - len(items)]
        items += taken
        more_pages = bool(result.has_more) and bool(result.room_list)
        if len(taken) < len(rows):
            spare = tuple(rows[len(taken):])
            break
        if not more_pages:
            break
        page, skip = page + 1, 0
    # 몫을 쪽 끝에서 딱 채워 남긴 칸이 없어도 다음 쪽이 있으면 더 있다. 2026-10-26 실측: 인후동 원룸 --limit 48 은 1가가 첫 쪽
    # 24건을 다 받고 다음 쪽이 없다고 남겨, 2가가 남긴 몫을 1가에 물을 때 받지 않고 끝내 226건 중 37건만 냈다
    return _Fetched(items, total, bool(spare) or more_pages, premium, spare, more_pages)


def _budgets(limit: int, count: int) -> list[int]:
    """`limit` 을 범위 수로 나눈다 (앞 범위가 나머지를 가진다)."""
    share, rest = divmod(limit, count)
    return [share + (1 if index < rest else 0) for index in range(count)]


def search_listings(
    client: DabangClient,
    kind: ListingKind,
    places: list[DabangPlace],
    *,
    conditions: DabangListingConditions | None = None,
    limit: int,
    radius_km: float | None = None,
    offsets: dict[str, int] | None = None,
    finished: dict[str, tuple[int, int | None]] | None = None,
    bbox: DabangBboxModel | None = None,
) -> DabangSearchResult:
    """한 유형의 매물을 다방 목록 순으로 받는다. 조건은 모두 다방 서버가 거른다.

    찾는 방식은 위치에 따라 정한다: 동은 그 동 안(`region`), 역은 다방이 정한 역 반경(`subway`), 대학은 대학 둘레(`univ`),
    좌표나 `radius_km` 는 반경을 덮는 지도 범위(`bbox`)로 받고 반경 밖은 뺀다. 아파트는 동·대학 검색이 없어 동은 경계를 덮는
    지도 범위로 받아 그 동 매물만 남기고, 대학은 반경으로 찾는다. 동이 여럿('○가' 동)이면 `limit` 을 나눠 동마다 받는다.

    Args:
        places: 찾은 위치 (`resolve_places`, 좌표는 kind='point' 하나).
        limit: 받을 매물 수 (받은 수로 센다. 뺀 만큼 다시 채우지 않는다).
        radius_km: 반경 검색이면 반경 (km).
        offsets: 이어 받기(`--next`)면 범위마다 앞서 받은 수.
        finished: 이어 받기면 앞 결과까지 끝낸 범위마다 (받은 수, 다방이 센 수). 다시 받지 않고 total·몇 번째에만 더한다.
        bbox: 이어 받기면 앞 결과가 남긴 동 경계 사각형 (아파트 동 검색). 주면 경계를 다시 받지 않는다.
    """
    conditions = conditions or DabangListingConditions()
    place = middle_place(places) if radius_km is not None else places[0]
    center = (place.lat, place.lng)
    notes: list[str] = []
    keep_gids: frozenset[int] | None = None
    distance_center: tuple[float, float] | None = center
    filter_radius: float | None = None
    approximate = False
    if radius_km is None and place.kind == 'point':
        radius_km = DEFAULT_RADIUS_KM
    if radius_km is None and place.kind == 'university' and kind == 'apt':
        radius_km = DEFAULT_RADIUS_KM
        notes.append(note('범위', f'다방 아파트 목록은 대학 검색이 없어 {place.name} 반경 {radius_km:g}km 안을 찾았습니다'))
    if radius_km is not None:
        targets = [_Target('bbox', 'bbox', bbox=bbox_of(*box_around(place.lat, place.lng, radius_km)))]
        filter_radius, approximate = radius_km, True
        scope = f'{place.name} 반경 {radius_km:g}km'
        if len(places) > 1:
            notes.append(note('범위', f'{place.name} 중심들의 가운데에서 반경 {radius_km:g}km 안을 찾았습니다'))
    elif place.kind == 'station':
        targets = [_Target(f'subway:{place.place_id}', 'subway', place_id=place.place_id)]
        if place.radius_m:
            radius_km = place.radius_m / 1000
        scope = f"{place.name} 다방 역 반경{f' {place.radius_m}m' if place.radius_m else ''}"
        notes.append(note('범위', f'{scope} 안을 찾았습니다 (반경을 정하려면 --radius)'))
    elif place.kind == 'university':
        targets = [_Target(f'univ:{place.place_id}', 'univ', place_id=place.place_id)]
        scope = f'{place.name} 둘레 (다방 대학 검색 범위)'
        notes.append(note('범위', f'{scope}를 찾았습니다 (반경을 정하려면 --radius)'))
    elif kind == 'apt':
        # 아파트 목록에는 동 검색이 없다 (403). 동 경계를 덮는 지도 범위로 받아 그 동 매물(동 번호)만 남긴다.
        # 사각형은 이어 받기 표에 남겨 --next 마다 동 경계(동마다 요청 1회)를 다시 받지 않는다
        bbox = bbox or dongs_bbox(client, places)
        targets = [_Target('bbox', 'bbox', bbox=bbox)]
        keep_gids = frozenset(part.gid for part in places if part.gid is not None)
        distance_center, approximate = None, True
        scope = f"{'·'.join(part.name for part in places)} 안"
        if len(places) == 1:
            notes.append(note('범위', f'{scope}을 찾았습니다. 다방 아파트 목록은 동 검색이 없어 동 경계를 덮는 사각형으로 받아 그 동 매물만 남겼습니다'))
    else:
        targets = [_Target(part.code or '', 'region', code=part.code) for part in places]
        distance_center = None
        scope = f"{'·'.join(part.name for part in places)} 안"
    if targets[0].search_type == 'region' and len(targets) == 1:
        notes.append(note('범위', f'{scope}을 찾았습니다 (반경으로 찾으려면 --radius)'))
    elif targets[0].search_type == 'region':
        notes.append(note('범위', '--limit 을 동마다 나눠 받았습니다 (한 동이 몫보다 덜 주면 남은 몫은 매물이 남은 다른 동이 받음)'))

    addresses = {part.gid: part.address for part in places if part.gid is not None and part.address}
    offsets = offsets or {}
    finished = dict(finished or {})
    total: int | None = None
    done_before = 0
    active: list[_Target] = []
    for target in targets:
        if offsets and target.key not in offsets:
            # 이어 받기에서 앞 결과가 끝낸 범위는 다시 받지 않는다 (next 에는 더 받을 범위만 남긴다). 그 범위의 수는 이어 받기
            # 표에서 더해 total·몇 번째가 첫 결과와 같게 한다 (성수동 원룸 1가 6건·2가 20건을 --limit 12 로: 둘 다 26건)
            done, done_total = finished.get(target.key, (0, None))
            done_before += done
            if done_total is not None:
                total = (total or 0) + done_total
            continue
        active.append(target)
    positions = {target.key: offsets.get(target.key, 0) for target in active}
    fetches: dict[str, _Fetched] = {}
    totals: dict[str, int | None] = {}
    rows: dict[str, list[DabangRoomItemModel]] = {target.key: [] for target in active}
    premium = 0
    filters = filters_of(kind, conditions)

    def ask(target: _Target, budget: int) -> int:
        """범위 하나에서 `budget` 건을 더 받고 받은 수를 돌려준다."""
        nonlocal premium
        previous = fetches.get(target.key)
        fetched = _fetch(client, kind, target, filters, start=positions[target.key], budget=budget, previous=previous)
        if previous is None:
            totals[target.key] = fetched.total
        premium += fetched.premium
        fetches[target.key] = fetched
        positions[target.key] += len(fetched.items)
        rows[target.key] += fetched.items
        return len(fetched.items)

    # 몫은 아직 끝나지 않은 범위끼리 나누고, 앞 범위가 몫보다 적게 주고 끝나면 남은 몫을 다음 범위가 받는다
    # (받은 뒤 뺀 매물은 다시 채우지 않는다). 동이 --limit 보다 많아 몫이 없는 동은 묻지 않고 이어 받기로 넘긴다
    # (을지로1가~7가를 --limit 3 으로 찾을 때)
    carry = 0
    for target, share in zip(active, _budgets(limit, len(active))):
        budget = share + carry
        carry = budget - ask(target, budget) if budget > 0 else 0
    # 뒤 범위가 남긴 몫은 매물이 남은 앞 범위부터 받는다. 2026-10-25 실측: 문래동 원룸 --limit 6 은 동마다 1건씩 나눠
    # 6가의 남은 몫을 버려, 3가에 2건이 남았는데도 7건 중 5건만 냈다
    for target in active:
        if carry <= 0:
            break
        fetched = fetches.get(target.key)
        if fetched is None or fetched.has_more:
            carry -= ask(target, carry)
    next_offsets: dict[str, int] = {}
    for target in active:
        fetched = fetches.get(target.key)
        if fetched is None or fetched.has_more:
            next_offsets[target.key] = positions[target.key]
        else:
            finished[target.key] = (positions[target.key], totals[target.key])
    total_known = [count for count in totals.values() if count is not None]
    if total_known:
        total = (total or 0) + sum(total_known)
    unasked = [target.key for target in active if target.key not in fetches]
    collected: list[DabangListing] = []
    seen: set[str] = set()
    received = sum(len(items) for items in rows.values())
    unreadable = outside = other_dong = duplicate = 0
    for item in (item for target in active for item in rows[target.key]):
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
    has_more = bool(next_offsets)
    # 이어 받을 범위만 남기면 끝난 범위를 다시 받지 않는다
    next_position: dict[str, Any] | None = {'offsets': next_offsets} if has_more else None
    if next_position is not None and finished:
        next_position['finished'] = {key: list(counts) for key, counts in finished.items()}
    if next_position is not None and keep_gids is not None and bbox is not None:
        next_position['bbox'] = bbox.model_dump()
    if unasked:
        # 묻지 않은 동의 매물 수를 몰라 전체 수도 모른다
        total = None
        names = {part.code: part.name for part in places}
        skipped = '·'.join(names.get(key, key) for key in unasked)
        notes.append(note('일부', f"--limit 이 동 수보다 작아 {skipped}{particle(skipped, '은/는')} 아직 찾지 않았습니다 (total 모름). 이어 보려면 결과의 next 를 --next 로 주세요"))
    if outside:
        notes.append(note('제외', f'반경을 덮는 사각형에서 받은 매물 중 반경 {filter_radius:g}km 밖 {outside}건을 뺐습니다 (뺀 만큼 다시 채우지 않음)'))
    if other_dong:
        notes.append(note('제외', f'동 경계를 덮는 사각형에서 받은 매물 중 다른 동 {other_dong}건을 뺐습니다 (뺀 만큼 다시 채우지 않음)'))
    if unreadable:
        notes.append(note('제외', f'가격·거래 유형을 읽지 못한 {unreadable}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}'))
    if duplicate:
        notes.append(note('제외', f'다방 목록에 두 번 나온 매물 {duplicate}건은 한 번만 넣었습니다 (다시 채우지 않음)'))
    notes += premium_note(premium)
    notes += limit_notes(
        total, len(collected), limit, order='다방 목록 순', approximate=approximate, inspected=received,
        offset=sum(offsets.values()) + done_before, resumable=has_more, has_more=has_more, radius=radius_km is not None,
    )
    region = place if len(places) == 1 else place.model_copy(update={'name': '·'.join(part.name for part in places)})
    return DabangSearchResult(
        region=region,
        scope=scope,
        radius_km=radius_km,
        total=total,
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


def _manage_cost(room: DabangNewRoomDetailRoomModel) -> tuple[float | None, list[str] | None]:
    """월 관리비(만원)와 포함 항목. 관리비가 '없음' 이면 0 과 [], 금액은 있는데 항목을 모르면 항목 None."""
    if room.maintenance_cost is None:
        if (room.maintenance_cost_str or '').strip() == '없음':
            return 0.0, []
        return None, None
    includes = list(room.maintenance_items_str)
    if not includes and room.maintenance_etc_fee_charge_detail is not None:
        includes = [MANAGE_ITEM_LABELS.get(code, code) for code in room.maintenance_etc_fee_charge_detail.detail_include_types]
    if not includes and room.maintenance_fixed_fee_charge_detail_list:
        # 정액 관리비 10만원 이상은 항목마다 정액(관리비에 듦)·실비(따로 냄)로 온다. 웹처럼 정액 항목만 관리비에 든 것으로 본다
        # (2026-10-26 실측: 6ac7072d7857540badc794a7 관리비 10만원 = 공용 F01 정액, 전기~TV F11~F16 실비)
        return won_to_manwon(room.maintenance_cost), [
            FIXED_FEE_ITEM_LABELS.get(item.detail_code, item.detail_code)
            for item in room.maintenance_fixed_fee_charge_detail_list
            if item.detail_cost_formulated_type == FIXED_FEE_TYPE
        ]
    return won_to_manwon(room.maintenance_cost), includes or None


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
    manage_cost, includes = _manage_cost(room)
    parking_count = room.parking_num
    return DabangListingDetail(
        source=SOURCE,
        id=room.id,
        url=listing_url(room.id),
        trade_type=trade_type,
        property_type=room.room_type_str or '매물',
        room_type=room_type_of(room.room_type_str),
        title=room.title,
        manage_cost_manwon=manage_cost,
        manage_cost_includes=includes,
        area_m2=room.room_size,
        area_pyeong=m2_to_pyeong(room.room_size),
        # 오피스텔은 공급면적 칸에 0 을 주기도 한다 (2026-10-26 실측: 강남역투웨니퍼스트 6ad6eb6fcac3561f038ec567). 모름이다
        supply_area_m2=room.provision_size or None,
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

