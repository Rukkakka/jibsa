"""상가·사무실 매물 검색·상세의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""


from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import haversine_km
from jibsa.core.korean import (
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    TradeType,
    in_range,
    join_address,
    m2_to_pyeong,
    parking_label,
)
from jibsa.core.notes import (
    limit_notes,
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.store import (
    ZigbangStoreArticleStoresListV2RequestPayloadModel,
    ZigbangStoreArticleStoresV2RequestPayloadModel,
    ZigbangStoreArticleStoreV2RequestParameterModel,
    ZigbangStoreBusinessModel,
    ZigbangStoreCircleModel,
    ZigbangStoreSalesType,
)
from jibsa.providers.zigbang.api.models.response.store import (
    ZigbangStoreSummaryModel,
)
from jibsa.providers.zigbang.service.common.constants import (
    MAX_LIST_LIMIT,
)
from jibsa.providers.zigbang.service.common.models import ZigbangRegion
from jibsa.providers.zigbang.service.common.text import (
    sent_or_none,
)
from jibsa.providers.zigbang.service.common.unavailable import (
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.store.constants import (
    MIN_SCAN_PINS,
    SCAN_FACTOR,
    STORE_BUSINESSES_BY_CATEGORY,
    STORE_FLOOR_PATTERN,
    STORE_LIST_BATCH_SIZE,
    STORE_NARROW,
    STORE_OFFICE_BUSINESS,
    STORE_PARKING_AVAILABLE,
    STORE_SERVER_NARROW,
    STORE_TRADE_BY_TITLE,
    STORE_URL,
    STORE_VACANT_NARROW,
    STORE_VACANT_SECTION,
    STORE_VACANT_SERVER_NARROW,
)
from jibsa.providers.zigbang.service.store.models import (
    ZigbangStoreConditions,
    ZigbangStoreListing,
    ZigbangStoreListingDetail,
    ZigbangStoreSearchResult,
)


def store_floor(floor: str | None) -> str | None:
    """상가 층 표기('4층', '지하1층')를 매물 공통 표기('4', '지하1')로 맞춘다."""
    if floor is None:
        return None
    match = STORE_FLOOR_PATTERN.match(floor.strip())
    if match is None:
        return floor
    basement, number = match.groups()
    return f'지하{number}' if basement else number


def store_parking(text: str | None) -> str | None:
    """상가 주차 문구('가능 - 자주식 6대')를 매물 공통 꼴('가능 (자주식 6대)')로 맞춘다. 다른 문구는 그대로 둔다."""
    if not text:
        return None
    status, _, detail = text.partition(' - ')
    available = STORE_PARKING_AVAILABLE.get(status.strip())
    return text if available is None else parking_label(available, detail.strip() or None)


def store_trade(summary: ZigbangStoreSummaryModel) -> TradeType:
    """상가 거래 유형. 응답의 `sales_title`(매매·전세·월세)을 그대로 쓰고, 없거나 다른 값이면 예전 규칙으로 정한다.

    웹 상가 카드·상세는 거래 이름을 `sales_title` 로 정한다 (2026-11-17 번들 `StoreItemCard`·`createMetaData`: 매매면
    매매금액, 전세·월세면 보증금액을 쓴다). 요약·상세 응답 모두 이 필드가 있다. `sales_title` 을 못 쓸 때는 매매가
    아니면 임대이고, 월세금액이 있으면 월세, 없으면 전세로 정한다. 지금까지 본 약 2,000건에서는 두 규칙의 답이 같았다
    (2026-10-10 실측: 7개 역 1,709건 중 임대 1,649건 모두 월세 > 0, 매매는 월세 0, 2026-11-17 상가 130건도 같다.
    `sales_title` 은 월세·매매뿐이고 전세 상가는 0건). 다만 `sales_title` 이 월세인데 월세금액이 0 이면 웹처럼 월세로
    낸다 (`rent_manwon` 은 0).
    """
    title = STORE_TRADE_BY_TITLE.get(summary.sales_title or '')
    if title is not None:
        return title
    if summary.sales_type == '매매':
        return '매매'
    return '월세' if summary.rent else '전세'


def store_businesses(names: list[str]) -> list[ZigbangStoreBusinessModel]:
    """업종·대분류 이름을 웹과 같은 대분류별 업종 조건으로 묶는다. 대분류 이름은 그 안의 업종 전체.

    CLI 는 `split_csv` 로 먼저 막는다.

    Raises:
        JibsaError: 직방 상가 업종·대분류가 아닌 이름이 있을 때 (INVALID_ARGUMENT).
    """
    chosen: dict[str, list[str]] = {}
    for name in names:
        if name in STORE_BUSINESSES_BY_CATEGORY:
            chosen.setdefault(name, []).extend(STORE_BUSINESSES_BY_CATEGORY[name])
            continue
        category = next(
            (category for category, businesses in STORE_BUSINESSES_BY_CATEGORY.items() if name in businesses),
            None,
        )
        if category is None:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f"직방 상가 업종이 아닙니다: '{name}'",
                hint='jibsa zigbang search listings store --help 에서 --business 값을 확인하세요',
            )
        chosen.setdefault(category, []).append(name)
    return [
        ZigbangStoreBusinessModel(category=category, businesses=list(dict.fromkeys(businesses)))
        for category, businesses in chosen.items()
    ]


def store_price_trade(
    trade: ZigbangStoreSalesType,
    bounds: dict[str, tuple[int | None, int | None]],
) -> ZigbangStoreSalesType:
    """상가 가격 범위를 검증하고 가격 조건에 맞는 임대·매매 유형을 정한다.

    CLI 는 지역을 찾기 전에 이 함수로 막고 좁힌 거래 유형을 안내하며, `search_store_listings` 도 다시 부른다.

    Raises:
        JibsaError: 범위가 음수·거꾸로이거나, 임대·매매 가격 조건을 섞었거나 `trade` 와 맞지 않을 때 (INVALID_ARGUMENT).
    """
    def invalid(message: str) -> JibsaError:
        return JibsaError(
            code='INVALID_ARGUMENT', message=message,
            hint='jibsa zigbang search listings store --help 에서 가격·거래 유형 조건을 확인하세요',
        )

    for field, (minimum, maximum) in bounds.items():
        option = field.removesuffix('_manwon').replace('_', '-')
        if any(value is not None and value < 0 for value in (minimum, maximum)):
            raise invalid(f'--{option}-min/max 는 0 이상이어야 합니다')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise invalid(f'--{option}-max 는 --{option}-min 이상이어야 합니다')
    rental = any(
        any(value is not None for value in bounds[field])
        for field in ('deposit_manwon', 'rent_manwon', 'key_money_manwon')
    )
    sale = any(value is not None for value in bounds['price_manwon'])
    if rental and sale:
        raise invalid('보증금·월세·권리금 조건과 매매가 조건은 함께 쓸 수 없습니다')
    if (rental and trade == '매매') or (sale and trade == '임대'):
        raise invalid('--trade 와 가격 조건이 맞지 않습니다. 보증금·월세·권리금은 임대, 매매가는 매매에만 쓰세요')
    return '임대' if rental else '매매' if sale else trade


def _store_price_matches(
    listing: ZigbangStoreListing,
    bounds: dict[str, tuple[int | None, int | None]],
) -> bool:
    for field, (minimum, maximum) in bounds.items():
        if minimum is None and maximum is None:
            continue
        if field in ('deposit_manwon', 'key_money_manwon') and listing.trade_type == '매매':
            return False
        if field == 'rent_manwon' and listing.trade_type != '월세':
            return False
        if not in_range(getattr(listing, field), minimum, maximum):
            return False
    return True


def store_region_codes(dongs: list[ZigbangRegion]) -> tuple[list[str], list[str]]:
    """동 이름으로 찾을 때 `지역` 에 보낼 법정동 코드(10자리)와 안내.

    직방은 모르는 코드에 에러 없이 전국 매물을 준다 (2026-11-15 실측: 리 코드 4183025021 → 57,782건). 그래서 리는 그 위
    읍·면 코드(앞 8자리 + '00')로 바꿔 읍·면 전체를 찾고 알리며, 코드가 없는 동은 전국 목록을 내지 않게 막는다.

    Raises:
        JibsaError: 법정동 코드(10자리)가 없는 동이 있을 때 (REGION_NOT_SUPPORTED).
    """
    codes: list[str] = []
    notes: list[str] = []
    for dong in dongs:
        code = dong.legal_division_code or ''
        if len(code) != 10 or not (code.isascii() and code.isdigit()):
            raise JibsaError(
                code='REGION_NOT_SUPPORTED',
                message=f"직방 지역 검색 결과에 '{dong.name}' 의 법정동 코드(10자리)가 없어 그 동 안을 찾을 수 없습니다",
                hint=f"--radius 를 주면 '{dong.name}' 중심에서 반경으로 찾습니다 (예: --radius 1)",
            )
        if is_ri_code(code):
            code = f'{code[:8]}00'
            notes.append(note(
                '범위',
                f"{quoted(dong.name, '은/는')} 리라 그 리가 속한 읍·면 전체를 찾았습니다. 직방 상가는 리 단위로 찾지 못합니다 "
                '(반경으로 찾으려면 --radius)',
            ))
        codes.append(code)
    return list(dict.fromkeys(codes)), notes


def search_store_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangStoreConditions | None = None,
    radius_km: float = 1.0,
    limit: int = 20,
    dongs: list[ZigbangRegion] | None = None,
) -> ZigbangStoreSearchResult:
    """중심점 반경(또는 `dongs` 동) 안의 상가·사무실을 직방 목록 순서 그대로 `limit` 건 조회한다.

    웹 상가 검색처럼 범위 안 위치 목록을 한 번에 받고 그 순서대로 앞에서부터 요약을 받는다 (2026-11-15 번들
    `HomeStoreListScreenModel.loadItems`: 응답 순서대로 15건씩, 정렬 없음). 순서는 거리순이 아니고, `distance_km` 는
    검색 중심에서 잰 거리다. 반경은 원(`상권`)으로 보내고, `dongs` 가 있으면 반경 대신 그 동들의 법정동 코드(`지역`)로
    찾는다 (`store_region_codes`). 서버가 범위 안 매물만 준다.

    거래 유형(임대·매매), 1층, 업종, 면적(㎡, 상한은 미만)은 서버에서 거른다.
    가격 조건은 요약을 받은 뒤 거른다 (상·하한 포함, 모르는 금액은 제외). 권리금 조건을 걸면 권리금이 해당 없는
    사무실(`key_money_manwon` 키 없음)도 빠지므로, 권리금만 아니면 다른 가격 조건에 맞던 수를 `notes` 로 알린다.
    직방 목록 앞의 후보를 조회
    상한(max(limit * SCAN_FACTOR, MIN_SCAN_PINS))까지 확인하며, 전체 후보를 확인하지 못하면 안내한다.
    업종 조건을 걸면 직방이 그 업종과 무관한 범위 안 공실을 '이 지역 비어있는 상가' 묶음으로 따로 주는데, 웹 지도 목록처럼
    업종 매물 뒤에 그 묶음을 잇는다 (`HomeStoreListScreenModel`: 칸마다 일반 ID 를 앞에, 공실 ID 를 뒤에 이어 요약을
    받는다). 공실 묶음에서 온 줄은 `vacant_section` 이 true 다. 두 묶음에 같은 ID 가 있으면 앞 것만 둔다.
    위치 묶음 목록에 빈 항목(null)이 섞여 오면 빼고 읽되 그 묶음의 매물을 몰라 `total` 은 null 이고, 묶음 안 위치 목록의 빈 항목은
    `[제외]` 로만 알린다.

    Raises:
        JibsaError: `dongs` 에 법정동 코드가 없는 동이 있을 때 (`store_region_codes`).
    """
    conditions = conditions or ZigbangStoreConditions()
    bounds = {
        'deposit_manwon': (conditions.deposit_min, conditions.deposit_max),
        'rent_manwon': (conditions.rent_min, conditions.rent_max),
        'price_manwon': (conditions.price_min, conditions.price_max),
        'manage_cost_manwon': (conditions.manage_cost_min, conditions.manage_cost_max),
        'key_money_manwon': (conditions.key_money_min, conditions.key_money_max),
    }
    trade = store_price_trade(conditions.trade, bounds)
    filter_price = any(value is not None for pair in bounds.values() for value in pair)
    business_conditions = store_businesses(conditions.businesses or [])
    circles: list[ZigbangStoreCircleModel] | None = None
    region_codes: list[str] | None = None
    scope_notes: list[str] = []
    if dongs:
        region_codes, scope_notes = store_region_codes(dongs)
    else:
        circles = [ZigbangStoreCircleModel(lat=region.lat, lng=region.lng, radius=round(radius_km * 1000))]
    response = client.run_request_store_article_stores_v2(
        ZigbangStoreArticleStoresV2RequestPayloadModel(
            circles=circles,
            region_codes=region_codes,
            sales_type=trade,
            first_floor=conditions.first_floor,
            businesses=business_conditions,
            area_min_m2=conditions.area_min_m2,
            area_max_m2=conditions.area_max_m2,
        )
    )
    # 위치 묶음(섹션)에서 빈 항목(null)을 뺐으면 그 묶음의 매물을 몰라 전체 수(total)를 알 수 없다. 묶음 안 위치 목록에서 뺀 빈 항목은
    # 그 매물이 목록에서 빠졌을 수 있다고만 알린다
    dropped_sections = response.null_items('sections')
    dropped_locations = sum(section.null_items('item_locations') for section in response.sections)
    # 직방 목록 순서대로 매물 ID → 좌표
    pins: dict[int, tuple[float, float]] = {}
    vacant: set[int] = set()
    # 업종 묶음 뒤에 공실 묶음을 잇는다. 공실 묶음은 업종 조건을 걸 때만 차고(2026-10-18 실측: 성수역 0.3km 업종 조건
    # 없이 일반 묶음 393건, 공실 묶음 0건), 그 업종 묶음에 든 매물을 뺀 범위 안 공실이라 두 묶음은 겹치지 않는다
    # (2026-11-19 실측: 역삼역 500m 카페/커피 일반 23·공실 332, 겹침 0). 그래도 겹치면 앞(업종 묶음) 것만 둔다
    for vacant_pass in (False, True):
        for section in response.sections:
            if (section.title == STORE_VACANT_SECTION) != vacant_pass:
                continue
            for location in section.item_locations:
                if location.item_id in pins:
                    continue
                pins[location.item_id] = (location.lat, location.lng)
                if vacant_pass:
                    vacant.add(location.item_id)

    scan_cap = max(limit * SCAN_FACTOR, MIN_SCAN_PINS)
    candidates = list(pins)[:scan_cap]
    listings: list[ZigbangStoreListing] = []
    inspected = 0
    matched = 0
    # 권리금 조건 때문에만 빠진 권리금 해당 없음 사무실 수
    key_money_bounds = bounds['key_money_manwon']
    other_bounds = {field: pair for field, pair in bounds.items() if field != 'key_money_manwon'}
    office_no_key_money = 0
    for start in range(0, len(candidates), STORE_LIST_BATCH_SIZE):
        if len(listings) >= limit:
            break
        batch = candidates[start:start + STORE_LIST_BATCH_SIZE]
        inspected += len(batch)
        summaries = client.run_request_store_article_stores_list_v2(
            ZigbangStoreArticleStoresListV2RequestPayloadModel(item_ids=batch)
        )
        # 요약 응답의 순서에 기대지 않고 보낸 순서(직방 목록 순서)대로 놓는다
        summary_by_id = {summary.item_id: summary for summary in summaries.items}
        for item_id in batch:
            summary = summary_by_id.get(item_id)
            if summary is None or summary.status != 'open':
                continue
            lat, lng = pins[item_id]
            trade_type = store_trade(summary)
            listing = ZigbangStoreListing(
                source='zigbang',
                id=f'store-{summary.item_id}',
                url=STORE_URL.format(summary.item_id),
                trade_type=trade_type,
                property_type='상가',
                title=summary.title,
                price_manwon=summary.sales_price if trade_type == '매매' else None,
                deposit_manwon=None if trade_type == '매매' else summary.deposit,
                rent_manwon=summary.rent if trade_type == '월세' else None,
                manage_cost_manwon=summary.manage_cost,
                area_m2=summary.size_m2,
                area_pyeong=m2_to_pyeong(summary.size_m2),
                floor=store_floor(summary.floor),
                address=join_address(summary.local1, summary.local2, summary.local3),
                lat=lat,
                lng=lng,
                distance_km=round(haversine_km(region.lat, region.lng, lat, lng), 2),
                business=summary.business,
                key_money_manwon=summary.key_money,
                vacant_section=(item_id in vacant) if (business_conditions or vacant) else None,
            )
            # 거래 유형은 서버가 걸었으므로 다시 거르지 않는다 (2026-10-10 실측: 역삼역·성수동 임대·매매 662건 모두 조건 안)
            if not _store_price_matches(listing, bounds):
                if (
                    any(value is not None for value in key_money_bounds)
                    and listing.business == STORE_OFFICE_BUSINESS
                    and listing.key_money_manwon is None
                    and _store_price_matches(listing, other_bounds)
                ):
                    office_no_key_money += 1
                continue
            matched += 1
            listings.append(listing)

    # --limit 에 맞춰 잘라 낸 매물. 후보 요약을 다 받았어도 잘린 매물이 있으면 더 있다 (2026-10-21 실측: 성수역 반경
    # 0.2km 범위 안 35건을 한 묶음에 다 받고 3건만 주며 has_more false 였다)
    cut = listings[limit:]
    listings = listings[:limit]
    pin_count = len(pins)
    total: int | None = None if dropped_sections else pin_count
    has_more = inspected < pin_count or bool(cut)
    area = '지역' if dongs else '반경'
    # 공실 줄은 업종과 상관없어 업종 조건으로 줄지 않는다. 공실 묶음이 있으면 업종 조건은 권하지 않는다
    narrow = STORE_VACANT_NARROW if vacant else STORE_NARROW
    server_narrow = STORE_VACANT_SERVER_NARROW if vacant else STORE_SERVER_NARROW
    if filter_price:
        notes = [
            '가격 조건은 요약을 받은 뒤 거릅니다. '
            + (f'total({total}건)은 가격 적용 전 직방 목록의 매물 수이고, 그중 앞의' if total is not None else '직방 목록 앞의')
            + f' {inspected}건의 요약을 요청해 거래 가능하고 가격 조건에 맞는 {matched}건을 확인했습니다'
        ]
        # 가격 조건이 있으면 limit_notes 의 [일부] 를 쓰지 않으므로, 더 있다는 안내와 다음 할 일을 여기서 붙인다. 후보 조회
        # 상한도 --limit 에 비례해(SCAN_FACTOR) --limit 을 늘리면 더 확인한다 (2026-11-10 리뷰·실측: 성수역 0.2km --rent-max
        # 1000 --limit 5 는 34건 중 5건, 0.8km --limit 120 은 '150건만 조회했습니다' 에서 끝나 다음 할 일이 없었다)
        # 후보 조회 상한에서 멈췄으면 가격 조건은 권하지 않는다. 가격은 직방 목록 앞의 후보를 상한까지 고른 뒤 거르므로, 좁혀도
        # 같은 후보만 다시 보고 일치 수만 준다. 미확인 후보에 닿는 건 --limit(상한이 비례)과 서버가 거르는 조건·범위다
        # (2026-11-11 리뷰·실측: 성수역 0.8km --limit 5 를 --rent-max 50 에서 30 으로 좁혀도 같은 60건만 보고 242건이 미확인)
        capped = inspected < pin_count and len(listings) < limit
        hint = more_hint(limit, MAX_LIST_LIMIT, f'{server_narrow if capped else narrow}·{area}')
        if inspected < pin_count:
            notes.append(note(
                '일부',
                f"{'후보 조회 상한' if capped else '결과 개수 제한'}으로 직방 목록 앞의 후보 {inspected}건만 조회했습니다 "
                # 상한이 --limit 에 비례한다는 말이 없으면 '--limit 을 늘리라' 와 따로 정해진 상한으로 읽혀 늘리지 않았다
                # (2026-11-11 LLM 사용 시험: 성수역 --rent-max 50 --limit 20 의 '조회 상한 100건' 에 --limit 대신 반경만 좁힘)
                f'(조회 상한은 --limit 의 {SCAN_FACTOR}배·최소 {MIN_SCAN_PINS}건이라 {scan_cap}건, '
                f"미확인 후보 {pin_count - inspected}건{'' if total is not None else ' 이상'}). 전체 가격 조건 일치 수는 모릅니다. {hint}",
            ))
        elif has_more:
            # 위 분기가 아니면 has_more 는 확인한 일치 매물이 --limit 에 잘렸다는 뜻이다
            notes.append(note('일부', f'확인한 가격 조건 일치 매물 중 직방 목록 앞의 {len(listings)}건만 보여 줍니다. {hint}'))
    else:
        notes = limit_notes(
            total, len(listings), limit, max_limit=MAX_LIST_LIMIT, narrow=f'{narrow}·{area}', order='직방 목록',
            inspected=inspected, has_more=has_more,
        )
    if office_no_key_money:
        notes.append(note(
            '제외',
            f'권리금 조건을 걸어 확인한 후보 중 권리금이 해당 없는 사무실 {office_no_key_money}건을 뺐습니다 '
            '(직방이 사무실에는 권리금을 주지 않습니다). 사무실도 보려면 권리금 조건 없이 검색하세요',
        ))
    if vacant and total is not None:
        # 공실 묶음은 업종 조건에 맞는 매물이 아니라 직방이 업종과 무관하게 따로 주는 묶음이라 [참고] 로 알린다.
        # 이번 쪽에 공실 줄이 없어도 total 에는 들어 있으니 늘 알린다. total 을 모를 때는 이 수의 짜임을 말할 수 없어 알리지 않는다
        base = '업종 매물' if business_conditions else '일반 매물'
        notes.append(note(
            '참고',
            f'total({total}건)은 {base} {total - len(vacant)}건과 그 뒤에 직방 웹처럼 이어 주는 이 지역 비어있는 상가'
            f'(업종과 상관없는 공실, vacant_section true) {len(vacant)}건을 합친 수입니다. 공실 줄은 업종 조건으로 줄지 않습니다',
        ))
    null_notes: list[str] = []
    if dropped_sections:
        null_notes.append(null_items_note('직방 상가 위치 묶음', dropped_sections, ('total',)))
    if dropped_locations:
        # 위치 목록에서 뺐으면 그 매물이 목록에서 빠졌을 수 있다
        null_notes.append(null_items_note('직방 상가 위치', dropped_locations))
    return ZigbangStoreSearchResult(
        region=region,
        radius_km=None if dongs else radius_km,
        boundary='·'.join(dong.name for dong in dongs) if dongs else None,
        total=total,
        inspected_in_radius=inspected if filter_price else None,
        price_matched_in_radius=matched if filter_price else None,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=scope_notes + notes + null_notes,
    )


def get_store_listing(client: ZigbangClient, item_id: int) -> ZigbangStoreListingDetail:
    """상가 매물 하나의 상세를 조회한다. 연락처·사진·본문은 옮기지 않는다.

    Raises:
        ListingUnavailableError: 없는 매물(404)이거나 상태가 open 이 아닐 때.
    """
    listing_id = f'store-{item_id}'
    with unavailable_on_404(listing_id):
        response = client.run_request_store_article_store_v2(
            ZigbangStoreArticleStoreV2RequestParameterModel(item_id=item_id)
        )
    if response.item.status != 'open':
        raise ListingUnavailableError('zigbang', listing_id, status=response.item.status)
    item = response.item
    trade_type = store_trade(item)
    elevator = {'있음': True, '없음': False}.get(item.elevator or '')
    return ZigbangStoreListingDetail(
        source='zigbang',
        id=f'store-{item.item_id}',
        url=STORE_URL.format(item.item_id),
        trade_type=trade_type,
        property_type='상가',
        title=item.title,
        price_manwon=item.sales_price if trade_type == '매매' else None,
        deposit_manwon=None if trade_type == '매매' else item.deposit,
        rent_manwon=item.rent if trade_type == '월세' else None,
        manage_cost_manwon=item.manage_cost,
        area_m2=item.size_m2,
        area_pyeong=m2_to_pyeong(item.size_m2),
        floor=store_floor(item.floor),
        building_floor=store_floor(item.floor_all),
        address=join_address(item.local1, item.local2, item.local3),
        lat=item.lat,
        lng=item.lng,
        parking=store_parking(item.parking),
        has_elevator=elevator,
        nearby_stations=sent_or_none(response, 'subways', [
            f'{subway.name} ({subway.description})' if subway.description else subway.name
            for subway in response.subways
        ]),
        business=item.business,
        key_money_manwon=item.key_money,
        recommended_business=item.recommended_business,
        vacancy=item.section_type,
        lease_unit=item.lease_unit,
        interior=item.interior,
        toilet=item.toilet,
        heating=item.heating,
    )
