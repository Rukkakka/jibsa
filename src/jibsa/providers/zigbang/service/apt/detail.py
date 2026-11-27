"""아파트 매물 상세 (listing)와 매물 묶음·호 정보 (catalog)의 조회·변환."""

from httpx import HTTPStatusError

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.listing import (
    TradeType,
    join_address,
    lookup_failure_note,
    m2_to_pyeong,
    move_in_label,
    note,
    null_items_note,
    parking_label,
    read_date,
    won_to_manwon,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.apt.detail import (
    ZigbangItemCatalogsHoInfoRequestParameterModel,
    ZigbangItemCatalogsItemsRequestParameterModel,
    ZigbangItemCatalogsRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.request.common import (
    ZigbangAptItemSource,
    ZigbangAptTranType,
)
from jibsa.providers.zigbang.api.models.response.apt.detail import (
    ZigbangAptItemModel,
    ZigbangHoPriceInfoModel,
)
from jibsa.providers.zigbang.service.apt.constants import (
    CATALOG_ID_HINT,
    CATALOG_ID_PATTERN,
    CATALOG_PAGE_SIZE,
)
from jibsa.providers.zigbang.service.apt.models import (
    ZigbangCatalogResult,
    ZigbangPublicPrice,
)
from jibsa.providers.zigbang.service.common.apt import (
    apt_catalog_id,
    apt_item_source,
    apt_listing_id,
    apt_listing_kind,
)
from jibsa.providers.zigbang.service.common.constants import (
    APT_CATALOG_URL,
    APT_ITEM_URL,
    APT_TRAN_TYPE_BY_TRADE,
    DIRECTION_LABELS,
    MAX_LIST_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    TRADE_BY_APT_TRAN_TYPE,
)
from jibsa.providers.zigbang.service.common.ids import apt_complex_id
from jibsa.providers.zigbang.service.common.models import ZigbangListingDetail
from jibsa.providers.zigbang.service.common.price import estimated_prices_of
from jibsa.providers.zigbang.service.common.text import text_or_none
from jibsa.providers.zigbang.service.common.unavailable import unavailable_on_404


def get_apt_listing(client: ZigbangClient, item_id: int, item_source: ZigbangAptItemSource = 'zigbang') -> ZigbangListingDetail:
    """아파트 매물(직방, 또는 `coalition` 이면 집주인이 내놓았거나 신규분양인 제휴 매물) 하나의 상세를 아파트 상세(`/apt/item-catalogs/items`) 1회로 조회한다.

    웹 아파트 매물 화면(`/home/apt/item/v2/{id}/{출처}/0`)이 부르는 상세는 이것 하나다 (2026-11-15 실측). 주거 상세·`/v3/items` 는
    아파트에 404 다. 상태 필드가 없고 내려간 매물은 404 다. 이 상세는 주거 상세가 아파트 매물이라고 알린 숫자 ID 나
    `coalition-` ID 로만 부르므로, 404 는 다른 소스 ID 가 아니라 직방 아파트 매물이 없거나 내려간 것이다 (`APT_ITEM_NOT_FOUND`).

    Raises:
        ListingUnavailableError: 없는 매물(404, `APT_ITEM_NOT_FOUND`)이거나 거래 유형을 모를 때.
    """
    listing_id = apt_listing_id(item_id, item_source)
    with unavailable_on_404(listing_id, reason='APT_ITEM_NOT_FOUND'):
        apt = client.run_request_item_catalogs_items(
            ZigbangItemCatalogsItemsRequestParameterModel(item_id=item_id, item_source=item_source)
        ).item
    return apt_item_to_listing(apt, item_source)


def apt_item_to_listing(
    apt: ZigbangAptItemModel,
    item_source: ZigbangAptItemSource,
    trade_type: TradeType | None = None,
) -> ZigbangListingDetail:
    """아파트 상세(`/apt/item-catalogs/items`) 응답을 `ZigbangListingDetail` 로 바꾼다 (직방·제휴 매물).

    거래 유형은 `trade_type` 을 주면 그것을, 아니면 응답의 `tranType` 을 쓴다. 묶음(`get_catalog`)은 요청한 거래 유형으로
    받은 매물이라 그 거래 유형을 넘긴다 (웹 묶음 화면도 매물의 `tranType` 으로 거르지 않는다).

    제목·층·방향이 빈 글자면 주소처럼 모름(None)이다. 층은 직방 매물이면 '저'·'중'·'고' 그대로다 (웹 아파트 화면에도 정확한 층이 없다). 주소는 지번 주소(`oldAddress`)다.
    직방 매물은 지번이 빈 문자열이라 모름(None)이다: 응답의 `address` 는 도로명이라 매물 출력에 내지 않고(출력 규약), 웹 매물
    화면도 지번을 보여 주지 않는다 (2026-11-15 웹 캡처: 단지 API 도 부르지 않는다). 지번은 단지(`complex_id`)에서 본다.
    등록일·인근 역·엘리베이터·방 구조·세대수는 이 응답에 없어 모름(None)이다. 건축물 용도(`residence_type`)는 `realType`(중개대상물 종류, 예 '아파트')이고 제휴 매물은 키가 없어 모름(None)이다.
    평형(`roomTypeInfo`)은 ID·이름(평 기준)으로 내고, 확인 시각(`effectivenessUpdatedAt`)은 웹의 '2주 전 확인' 대신 한국 날짜로 낸다.
    실매물 확인 배지·위반 건축물 여부·HUG 안심임대인·찜 수는 직방이 준 값 그대로다 (위반 건축물은 제휴 매물에 키가 없어 모름(None)). 총 주차 대수(`parkingCount`)는 제휴 매물에 오지 않아 모름(None)이다. 관리비는
    확인 불가거나 모르는 종류거나 0원이면 모름(None)이다. 관리비 미포함 항목·부과 기준(`periodBasis`)·부과 방식(`costBasisDescription`)은 관리비 금액과
    같은 칸의 값을 직방 응답 순서·문구 그대로 낸다 (웹은 기타 관리비의 '상세보기' 창에 보여 준다). 옵션은 아파트 상세에 옵션 칸이 없어 (2026-10-11 실측 19건) 모름(None)으로 둔다.

    Raises:
        ListingUnavailableError: `trade_type` 을 주지 않았는데 응답의 거래 유형을 모를 때 (UNKNOWN_TRADE_TYPE).
    """
    listing_id = apt_listing_id(apt.item_id, item_source)
    trade_type = trade_type or TRADE_BY_APT_TRAN_TYPE.get(apt.tran_type or '')
    if trade_type is None:
        raise ListingUnavailableError('zigbang', listing_id, reason='UNKNOWN_TRADE_TYPE')
    is_sale = trade_type == '매매'
    cost = apt.manage_cost.amount if apt.manage_cost else None
    # '거실기준' 을 새 주거 상세의 방향 기준('거실')과 같은 꼴로 맞춘다
    criterion = (apt.direction_base or '').strip().removesuffix('기준').strip() or None
    direction = text_or_none(apt.direction)
    room_type = apt.room_type_info
    return ZigbangListingDetail(
        source='zigbang',
        id=listing_id,
        url=APT_ITEM_URL.format(apt.item_id, item_source),
        trade_type=trade_type,
        property_type='아파트',
        title=text_or_none(apt.item_title),
        price_manwon=apt.deposit if is_sale else None,
        deposit_manwon=None if is_sale else apt.deposit,
        rent_manwon=apt.rent if trade_type == '월세' else None,
        # 0원이면 웹(`getManagementFee`, 2026-11-15 번들)은 관리비 칸을 빈 글자로 두어 '관리비 없음' 이 아니라 모름(None)이다
        manage_cost_manwon=won_to_manwon(cost.monthly_cost) if cost and cost.monthly_cost else None,
        area_m2=apt.size_m2,
        area_pyeong=m2_to_pyeong(apt.size_m2),
        floor=text_or_none(apt.floor),
        building_floor=str(apt.building_floor) if apt.building_floor is not None else None,
        address=text_or_none(apt.old_address),
        room_count=apt.room_count,
        bathroom_count=apt.bathroom_count,
        direction=DIRECTION_LABELS.get(direction.upper(), direction) if direction else None,
        move_in=move_in_label(apt.movein_date),
        approved_date=read_date(apt.approval_date, '사용승인일'),
        parking=parking_label(None, f'세대당 {apt.parking_count_by_household:g}대') if apt.parking_count_by_household is not None else None,
        options=None,
        manage_cost_includes=cost.include_items if cost else None,
        complex_id=apt_complex_id(apt.area_danji_id) if apt.area_danji_id else None,
        complex_name=join_address(apt.area_danji_name, apt.area_building_name),
        supply_area_m2=apt.size_contract_m2,
        parking_count=apt.parking_count,
        direction_criterion=criterion,
        listing_kind=apt_listing_kind(apt.item_type),
        pyeong_id=room_type.danji_room_type_id if room_type else None,
        pyeong_name=text_or_none(room_type.room_type_title.p) if room_type and room_type.room_type_title else None,
        confirmed_date=read_date(apt.effectiveness_updated_at, '매물 확인일'),
        actual_listing_checked=apt.is_actual_item_checked,
        non_compliant_building=apt.has_violations,
        residence_type=text_or_none(apt.real_type),
        hug_lessor=apt.is_hug_lessor,
        favorite_count=apt.zzim_count,
        manage_cost_excludes=cost.exclude_items if cost else None,
        manage_cost_period=text_or_none(cost.period_basis) if cost else None,
        manage_cost_method=text_or_none(cost.cost_basis_description) if cost else None,
    )


def _empty_catalog_error(catalog_id: str) -> JibsaError:
    """묶음에 매물이 없을 때의 에러. 첫 쪽이 404 든 200 빈 목록이든 같은 에러를 낸다."""
    return JibsaError(
        code='LISTING_UNAVAILABLE',
        message=(
            f'거래할 수 있는 매물이 없는 직방 아파트 묶음입니다: {catalog_id} '
            '(모두 내려갔거나 그 호에 그 거래 유형 매물이 없음)'
        ),
        hint='이 묶음은 빼고 search listings apt·search listings --complex <apt-…> 로 현재 매물을 다시 찾으세요',
        details={'catalog_id': catalog_id, 'reason': 'EMPTY_CATALOG'},
    )


def _known_price(value: float | None) -> float | None:
    """호 정보의 금액. 직방은 값이 없는 호에 0 을 주기도 해 0 도 값이 없는 것(None)으로 본다 (0만원 시세·분양가·공시가격은 없다)."""
    return value or None


def catalog_public_prices(price_info: ZigbangHoPriceInfoModel | None) -> list[ZigbangPublicPrice] | None:
    """호의 공시가격을 응답 순서(최근 해부터) 그대로 낸다. 공시가격(원)은 만원으로 환산한다.

    호 정보나 그 안의 `publicPrices` 가 없거나 null 이면 빈 목록이 아니라 모름(None)이다. 공시가격이 없는 호는 빈 목록이다.
    금액이 0 원인 해는 항목을 빼지 않고 금액만 모름(None)으로 낸다 (공시가격 0원은 실제 값이 아니다).
    """
    if price_info is None or price_info.public_prices is None:
        return None
    return [
        ZigbangPublicPrice(
            year=price.year, public_price_manwon=won_to_manwon(_known_price(price.price)), change_percent=price.compare_price_rate,
        )
        for price in price_info.public_prices
    ]


def get_catalog(client: ZigbangClient, catalog_id: str) -> ZigbangCatalogResult:
    """같은 호를 올린 아파트 매물 묶음의 매물을 웹 묶음 화면과 같은 API(`/apt/item-catalogs/{areaHoId}`)로 받는다.

    웹처럼 20건씩 `itemCount` 까지 받되(앞 `MAX_LIST_LIMIT` 건까지), 웹은 스크롤할 때마다 다음 20건을 받고 여기서는 한 번에
    끝까지 받는다. 매물마다 아파트 상세와 같은 꼴이라 `apt_item_to_listing` 으로 바꿔, 매물마다 상세를 따로 부르지 않는다.
    순서는 직방이 준 그대로다 (웹도 다시 세우지 않는다). 상세를 볼 수 없는 출처(직방·제휴 밖)의 매물은 목록의 `listing_ids`
    처럼 빼고 그 수를 `[제외]` 로 알린다 (2026-11-15 헬리오시티·은마 묶음 270건은 모두 직방·제휴였다). 거래 유형은 묶음 ID 의
    것을 쓴다 (매물의 `tranType` 이 비어도 웹 묶음 화면처럼 빼지 않는다).

    쪽의 매물 목록에 빈 항목(null)이 섞여 오면 빼고 읽되 받은 수(`received`)·쪽이 가득 찼는지에는 더해 센다 (빈 항목만 온 쪽은 빈 쪽이
    아니다). 빈 항목은 `[제외]` 로 따로 알리고 '상세를 볼 수 없는 출처' 수에 섞지 않는다.

    받는 도중 직방이 다음 쪽을 주지 않으면(받는 사이 묶음이 줄어 404, 또는 빈 쪽) 받은 데까지 내고 `[일부]` 로 알린다.
    직방이 `itemCount` 를 주지 않으면(`total` null) 쪽이 가득(`CATALOG_PAGE_SIZE`) 찬 동안 상한까지 받고, 덜 찬 쪽이나
    404·빈 쪽이 오면 끝으로 본다. `(최대 N건)` 안내는 상한에 닿아 멈췄을 때만이다.

    매물을 다 받은 뒤 호 정보(`/apt/item-catalogs/{areaHoId}/ho-info`) 1회를 더 받아 웹 묶음 화면 '시세 정보' 탭의 직방시세·공시가격·
    분양가를 붙인다. 덤 조회라 실패하면(`OPTIONAL_LOOKUP_ERRORS`) 그 값들만 모름(null)으로 두고 `[실패]` 로 알린다. 요청은 매물
    `CATALOG_PAGE_SIZE` 건에 1회씩과 호 정보 1회다.

    Raises:
        JibsaError: 묶음 ID 형식이 아닐 때 (INVALID_ARGUMENT). 묶음에 매물이 없을 때 (LISTING_UNAVAILABLE, reason
            `EMPTY_CATALOG`. 모두 내려갔거나 그 호에 그 거래 유형 매물이 없음. 첫 쪽이 404 이거나 200 빈 목록). 묶음 ID 는
            매물 ID 가 아니라 `listing_id` 대신 `catalog_id` 로 싣는다.
    """
    area_ho_id, tran_type = parse_catalog_id(catalog_id)
    trade_type = TRADE_BY_APT_TRAN_TYPE[tran_type]
    catalog_id = apt_catalog_id(area_ho_id, tran_type)
    listings: list[ZigbangListingDetail] = []
    received = 0
    # 쪽의 매물 목록에서 뺀 빈 항목(null) 수. 직방 offset·쪽 수는 빈 항목도 한 자리로 센다
    dropped = 0
    total: int | None = None
    last_page_full = False
    cut_short = False
    while True:
        try:
            page = client.run_request_item_catalogs(ZigbangItemCatalogsRequestParameterModel(
                area_ho_id=area_ho_id, tran_type=tran_type, offset=received, limit=CATALOG_PAGE_SIZE,
            ))
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            if not received:
                raise _empty_catalog_error(catalog_id) from None
            # 알린 수에 못 미쳤으면 받는 사이 묶음이 줄어 뒤 쪽이 없어졌다. 수를 모르면 끝까지 받은 것으로 본다. 받은 데까지 낸다
            cut_short = total is not None
            break
        page_count = len(page.items) + page.null_items('items')
        if not page_count:
            if not received:
                # 첫 쪽이 200 빈 목록이어도 404 와 같은 빈 묶음이다 (itemCount 와 상관없이)
                raise _empty_catalog_error(catalog_id)
            # 둘째 쪽부터의 빈 쪽도 404 와 같다. 이 쪽의 itemCount 는 줄어든 뒤의 수라 쓰지 않고 앞 쪽이 알린 수로 본다
            cut_short = total is not None
            break
        total = page.item_count
        received += page_count
        dropped += page.null_items('items')
        last_page_full = page_count >= CATALOG_PAGE_SIZE
        for apt in page.items:
            if (source := apt_item_source(apt.item_source)) is not None:
                listings.append(apt_item_to_listing(apt, source, trade_type))
        if total is None:
            # 묶음 수를 모르면 쪽이 가득 찬 동안만 다음 쪽을 받는다
            if not last_page_full or received >= MAX_LIST_LIMIT:
                break
            continue
        if received >= min(total, MAX_LIST_LIMIT):
            break
    notes: list[str] = []
    # 빈 항목은 출처를 알 수 없어 '상세를 볼 수 없는 출처' 로 세지 않고 따로 알린다
    skipped = received - dropped - len(listings)
    if skipped > 0:
        notes.append(note(
            '제외', f'묶음 매물 {received - dropped}건 중 상세를 볼 수 없는 출처 {skipped}건을 뺐습니다',
        ))
    if dropped:
        notes.append(null_items_note('직방 묶음 매물', dropped))
    if total is None:
        has_more = received >= MAX_LIST_LIMIT and last_page_full
    else:
        has_more = received < total
    # cut_short 는 받은 수가 직방이 알린 수(total)에 못 미친 채 멈췄을 때만 서므로 has_more 는 늘 참이다
    if cut_short:
        notes.append(note(
            '일부',
            f'직방이 다음 쪽 매물을 주지 않아 {received}건에서 멈췄습니다 (직방이 알린 묶음 {total}건, 받는 사이 묶음이 바뀌었을 수 '
            '있음). 다시 부르거나 url 의 직방 묶음 화면에서 보세요',
        ))
    elif has_more and total is None:
        notes.append(note(
            '일부',
            f'직방이 묶음 매물 수를 알려 주지 않아 앞 {received}건만 받았습니다 (최대 {MAX_LIST_LIMIT}건, 더 있을 수 있음). '
            '나머지는 url 의 직방 묶음 화면에서 보세요',
        ))
    elif has_more:
        notes.append(note(
            '일부',
            f'묶음 매물 {total}건 중 앞 {received}건만 받았습니다 (최대 {MAX_LIST_LIMIT}건). 나머지는 url 의 직방 묶음 화면에서 보세요',
        ))
    # 호 정보는 덤이라 매물을 다 받은 뒤에 부르고, 못 받아도 받은 매물은 낸다
    price_info: ZigbangHoPriceInfoModel | None = None
    try:
        price_info = client.run_request_item_catalogs_ho_info(
            ZigbangItemCatalogsHoInfoRequestParameterModel(area_ho_id=area_ho_id)
        ).price_info
    except OPTIONAL_LOOKUP_ERRORS as exc:
        notes.append(lookup_failure_note(
            exc, '직방', '호 정보', '직방시세·공시가격·분양가를 모릅니다 (url 의 직방 묶음 화면에서 확인)',
        ))
    zigbang_price = price_info.zigbang_price if price_info else None
    sale = zigbang_price.trade if zigbang_price else None
    jeonse = zigbang_price.charter if zigbang_price else None
    presale = price_info.presale if price_info else None
    return ZigbangCatalogResult(
        catalog_id=catalog_id,
        url=APT_CATALOG_URL.format(area_ho_id, tran_type),
        trade_type=trade_type,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
        estimated_prices=estimated_prices_of(
            _known_price(sale.price if sale else None),
            _known_price(sale.pyeong_price if sale else None),
            _known_price(jeonse.price if jeonse else None),
            _known_price(jeonse.pyeong_price if jeonse else None),
        ),
        public_prices=catalog_public_prices(price_info),
        presale_price_manwon=_known_price(presale.ho if presale else None),
        presale_price_average_manwon=_known_price(presale.average_ho if presale else None),
        type_presale_price_manwon=_known_price(presale.room_type if presale else None),
        presale_price_per_pyeong_manwon=_known_price(presale.pyeong_price if presale else None),
    )


def parse_catalog_id(catalog_id: str) -> tuple[int, ZigbangAptTranType]:
    """`catalog_id` 를 (호 ID, 거래 유형 코드) 로 나눈다. 거래 유형(한글)은 `TRADE_BY_APT_TRAN_TYPE` 으로 꺼낸다.

    `zigbang catalog` 명령은 형식을 따로 검사하지 않고 이 에러를 그대로 낸다.

    Raises:
        JibsaError: 형식이 맞지 않을 때 (INVALID_ARGUMENT).
    """
    match = CATALOG_ID_PATTERN.match(catalog_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 아파트 묶음 ID 형식이 아닙니다: '{catalog_id}'",
            hint=CATALOG_ID_HINT,
        )
    # 정규식이 이 표의 코드만 받으므로 늘 찾는다. 글자를 표의 값으로 바꿔 거래 유형 코드 타입으로 돌려준다
    tran_type = next(code for code in APT_TRAN_TYPE_BY_TRADE.values() if code == match.group(2))
    return int(match.group(1)), tran_type
