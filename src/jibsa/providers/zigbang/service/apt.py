"""아파트 매물 검색 (search listings apt)과 아파트 매물 상세·매물 묶음 (listing, catalog): 동·구 지역 목록, 좌표가 속한 동 찾기, 상세, 묶음 (동·구 이름 해석은 region)."""

import re

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
    RegionNotFoundError,
)
from jibsa.core.geo import encode_geohash
from jibsa.core.korean import is_dong_code
from jibsa.core.listing import (
    Listing,
    TradeType,
    in_range,
    iso_date,
    join_address,
    lookup_failure_note,
    m2_to_pyeong,
    move_in_label,
    normalize_date,
    note,
    null_items_note,
    parking_label,
    won_to_manwon,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangItemCatalogsHoInfoRequestParameterModel,
    ZigbangItemCatalogsItemsRequestParameterModel,
    ZigbangItemCatalogsRequestParameterModel,
    ZigbangLocalsItemCatalogsRequestParameterModel,
    ZigbangLocalsPolygonRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.common import ZigbangAptItemSource
from jibsa.providers.zigbang.api.response.apt import (
    ZigbangAptItemModel,
    ZigbangHoPriceInfoModel,
)
from jibsa.providers.zigbang.service.common.apt import (
    APT_TRAN_TYPE_BY_TRADE,
    TRADE_BY_APT_TRAN_TYPE,
    ZigbangAptListing,
    apt_catalog_id,
    apt_catalog_url,
    apt_item_source,
    apt_item_url,
    apt_listing_id,
    apt_listing_kind,
    apt_pagination_notes,
    catalog_null_notes,
    catalog_to_listing,
    parse_catalog_id,
)
from jibsa.providers.zigbang.service.common.base import (
    DIRECTION_LABELS,
    MAX_LIST_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    ZigbangAptRegion,
    ZigbangListingDetail,
    apt_complex_id,
    text_or_none,
    unavailable_on_404,
)
from jibsa.providers.zigbang.service.region import local_code_of

from typing import (
    Annotated,
    Any,
)


APT_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세')
# 한 번에 받는 아파트 매물 수. 지역 목록(locals)은 20 을 넘으면 400 이고, 단지 목록(danjis)은 50 도 같은 순서·내용으로
# 준다 (2026-10-10 실측: 헬리오시티 120건 20건씩 6회 = 50건씩 3회, 요청 모델 상한이 50)
LOCAL_CATALOG_PAGE_SIZE: int = 20
# 웹 묶음 화면이 한 번에 받는 매물 수 (`useItemCatalogDetail`, 2026-11-15 번들)
CATALOG_PAGE_SIZE: int = 20


def apt_resume_changed_error() -> JibsaError:
    """이어 받기(`--next`) 표의 지역이 다시 찾은 지역과 다를 때. 처음부터 다시 주면 앞 결과와 겹치는데 알 수 없다."""
    return JibsaError(
        code='INVALID_ARGUMENT',
        message='앞 결과 뒤로 직방 지역 검색 결과가 바뀌어 이어 받을 수 없습니다',
        hint='--next 없이 같은 지역·조건으로 다시 검색하세요',
    )


class ZigbangAptSearchResult(BaseModel):
    """아파트 지역 매물 검색 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangAptRegion,
        Field(description='검색한 동·구. 좌표(lat·lng)는 이름으로 찾았는데 직방이 주지 않았으면 모름(null)')
    ]
    local_code: Annotated[
        str,
        Field(description='조회한 직방 지역 코드 (법정동코드 앞 5·8자리)')
    ]
    total: Annotated[
        int,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='직방 목록에 아직 받지 않은 매물이 남았는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 (지역 코드 code, 앞서 받은 수 offset). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[ZigbangAptListing],
        Field(description='직방이 보여 주는 순서의 매물')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


# 좌표가 속한 동을 물을 geohash 정밀도. 칸이 크면 옆 동이 잡힌다 (2026-11-15 실측: 강남역은 정밀도 5 에 논현동, 6 에 역삼동,
# 7·8 에 서초동, 9·10·12 에 역 주소와 같은 역삼동. 역삼동 한가운데는 8~12 모두 역삼동)
APT_DONG_GEOHASH_PRECISION: int = 10


def apt_dong_at(client: ZigbangClient, lat: float, lng: float) -> ZigbangAptRegion:
    """좌표가 속한 동을 찾는다 (요청 1회). 역 이름·좌표로 아파트를 찾을 때 그 동의 지역 목록을 보게 한다.

    웹 아파트 지도의 '○○동 주변 매물보기' 처럼 `GET /apt/locals/polygon` 이 준 동이다 (2026-11-15 캡처). 검색 중심은
    받은 좌표 그대로다.

    Raises:
        RegionNotFoundError: 직방이 그 위치의 동(8자리 지역 코드)을 주지 않을 때.
    """
    response = client.run_request_locals_polygon(
        ZigbangLocalsPolygonRequestParameterModel(geohash=encode_geohash(lat, lng, APT_DONG_GEOHASH_PRECISION))
    )
    code = response.code
    if code is None or not re.fullmatch(r'\d{8}', code):
        raise RegionNotFoundError(
            f'{lat}, {lng}',
            hint="아파트는 동·구 단위로 조회합니다. 동 이름(예: '역삼동')이나 구 이름(예: '강남구')으로 검색하세요",
        )
    return ZigbangAptRegion(name=response.name or code, lat=lat, lng=lng, legal_division_code=f'{code}00')


def area_matches(listing: Listing, area_min_m2: float | None, area_max_m2: float | None) -> bool:
    """전용면적 조건에 맞는지. 조건이 있는데 면적을 모르면 맞지 않는다고 본다."""
    return in_range(listing.area_m2, area_min_m2, area_max_m2)


def _validate_apt_supply_area(minimum: float | None, maximum: float | None) -> None:
    """잘못된 공급면적 범위는 HTTP 요청 전에 거절한다."""
    if any(value is not None and value < 0 for value in (minimum, maximum)):
        raise JibsaError(
            code='INVALID_ARGUMENT', message='공급면적은 0 이상이어야 합니다',
            hint='--supply-area-min/max 에 ㎡ 단위의 0 이상 값을 주세요',
        )
    if minimum is not None and maximum is not None and minimum > maximum:
        raise JibsaError(
            code='INVALID_ARGUMENT', message='공급면적 상한은 하한 이상이어야 합니다',
            hint='--supply-area-min/max 범위를 확인하세요',
        )


class ZigbangAptConditions(RequestModel):
    """아파트 매물 조건 (search listings apt). 금액은 만원, 면적은 ㎡.

    거래 유형·가격·공급면적·신규분양 제외는 서버에서 거른다. 전용면적은 직방이 받지 않아 받은 뒤에 거른다.
    """

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형 (APT_TRADE_TYPES). 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    area_min_m2: Annotated[
        float | None,
        Field(description='전용면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='전용면적 상한 (㎡)')
    ] = None
    supply_area_min_m2: Annotated[
        float | None,
        Field(description='공급면적 하한 (㎡)')
    ] = None
    supply_area_max_m2: Annotated[
        float | None,
        Field(description='공급면적 상한 (㎡)')
    ] = None
    exclude_new_sale: Annotated[
        bool,
        Field(description="신규분양 매물을 빼고 볼지 (웹의 '신규 분양 포함' 을 끈 목록). 거짓이면 서버 기본(분양 포함)이다")
    ] = False


def search_apt_listings(
    client: ZigbangClient,
    region: ZigbangAptRegion,
    *,
    conditions: ZigbangAptConditions | None = None,
    limit: int = 20,
    start: dict[str, Any] | None = None,
) -> ZigbangAptSearchResult:
    """지역(동·구 하나) 안의 아파트 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다. 지역 코드(`legal_division_code`)로만 찾아 좌표는 쓰지 않는다.

    웹 지역 매물 화면(`/home/apt/items/{지역 코드}`)이 부르는 지역 목록(`/apt/locals/{코드}/item-catalogs`)과 같다
    (2026-11-15 캡처). 반경 검색이 아니라 거리가 없다. 거래 유형·가격(만원) 조건은 서버에서 거른다. 면적은 다른 유형과
    같게 전용면적(㎡)으로 받는데, 직방 지역 목록은 공급면적 조건만 받아 전용면적은 받은 뒤에 거른다. 공급면적은
    supply_area_min/max_m2로 서버에 전달한다. 실제로 받은 원본 개수로 조회 예산을 계산하며 제외된 만큼 추가 조회하지 않는다.

    `exclude_new_sale` 이면 지역 목록 요청마다 `includeOfferItem=false` 를 보내 신규분양 카드를 뺀다 (웹의 '신규 분양 포함' 끔,
    `total` 도 그만큼 준다). 이어 받는 쪽에도 보내야 쪽이 겹치지 않는다. 단지 목록(`/apt/danjis/{id}/item-catalogs`)은 이 값을
    무시해 (2026-11-17 실측) 거기에는 넣지 않는다.

    `start` 는 이어 받기(`--next`) 위치다. 앞서 받은 수(`offset`)부터 직방 offset 으로 받는다. 지역 목록은 같은 이름이면
    같은 순서로 나온다 (resolve_apt_region). 응답 목록에 빈 항목(null)이 섞여 오면 빼고 읽되, 직방 offset 은 그 자리도 세므로 받은
    수(`offset`·`inspected`)에 더해 센다 (`catalog_null_notes` 가 알린다).

    Raises:
        JibsaError: 이어 받기 표의 지역 코드(`code`)가 다시 찾은 지역과 다르거나 표 모양이 예전 것일 때 (INVALID_ARGUMENT).
    """
    conditions = conditions or ZigbangAptConditions()
    _validate_apt_supply_area(conditions.supply_area_min_m2, conditions.supply_area_max_m2)
    if region.legal_division_code is None:
        raise RegionNotFoundError(region.name)
    local_code = local_code_of(region.legal_division_code)
    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in conditions.trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    if conditions.trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다
        return ZigbangAptSearchResult(region=region, local_code=local_code, total=0, returned=0, listings=[])
    listings: list[ZigbangAptListing] = []
    total = 0
    offset = 0
    done = False
    if start is not None:
        # 다른 동의 offset 으로 받거나, 처음부터 다시 줘도 알 수 없다. 여러 동을 합치던 예전 표(codes)도 여기서 막는다
        if start.get('code') != local_code:
            raise apt_resume_changed_error()
        offset = int(start['offset'])
    inspected = 0
    # 목록에서 뺀 빈 항목 수와, 카탈로그의 묶인 매물 ID 목록에서 뺀 빈 항목 수 (`catalog_null_notes`)
    dropped_catalogs = 0
    dropped_id_lists = 0
    filter_area = conditions.area_min_m2 is not None or conditions.area_max_m2 is not None
    while inspected < limit and not done:
        response = client.run_request_locals_item_catalogs(
            ZigbangLocalsItemCatalogsRequestParameterModel(
                local_code=local_code,
                tran_types=tran_types,
                sales_price_min=conditions.price_min,
                sales_price_max=conditions.price_max,
                deposit_min=conditions.deposit_min,
                deposit_max=conditions.deposit_max,
                rent_min=conditions.rent_min,
                rent_max=conditions.rent_max,
                supply_area_min_m2=conditions.supply_area_min_m2,
                supply_area_max_m2=conditions.supply_area_max_m2,
                # 웹 기본 화면(분양 포함)과 같게 거짓이면 값을 보내지 않는다. 끄면 모든 쪽에 보낸다 (첫 쪽만 보내면 분양 카드 수만큼 겹친다)
                include_offer_item=False if conditions.exclude_new_sale else None,
                offset=offset,
                limit=min(LOCAL_CATALOG_PAGE_SIZE, limit - inspected),
            )
        )
        total = response.count
        # 직방 offset 은 빈 항목(null)도 한 자리로 센다. 빈 항목을 빼고 읽었어도 받은 자리 수에 더해야 같은 매물을 다시 받거나 일찍 멈추지 않는다
        received = len(response.catalogs) + response.null_items('catalogs')
        dropped_catalogs += response.null_items('catalogs')
        dropped_id_lists += sum(catalog.null_items('item_id_list') for catalog in response.catalogs)
        inspected += received
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, response.local1)
            if listing is not None and area_matches(listing, conditions.area_min_m2, conditions.area_max_m2):
                listings.append(listing)
        offset += received
        done = not received or offset >= response.count
    has_more = not done
    notes = apt_pagination_notes(
        len(listings), limit, inspected, has_more=has_more, resumable=has_more, resumed=start is not None, narrow='조건·지역',
    ) + catalog_null_notes('직방 지역 아파트', dropped_catalogs, dropped_id_lists)
    if filter_area:
        # 받은 원본(limit 건) 안에서만 거르므로 맞는 매물이 더 있어도 적게 나온다 (2026-10-09 실측: 대치동
        # 전용 150㎡ 이상이 20건 중 2건, 공급 190㎡ 이상 서버 조건으로는 20건 중 19건)
        notes.append(
            f'전용면적 조건은 직방이 받지 않아 받아 온 {inspected}건에서만 거릅니다. total({total}건)은 전용면적으로 거르기 전 수입니다'
            + (
                '. 조건에 맞는 매물이 더 있을 수 있으니, 빠짐없이 찾으려면 직방이 서버에서 거르는 공급면적 조건'
                '(--supply-area-min/--supply-area-max)으로 다시 찾으세요. 아파트 공급면적은 대개 전용면적의 1.1~1.5배'
                '(중간 1.3배 안팎)이니 넉넉히 잡고 결과의 area_m2 로 전용면적을 확인하세요'
                # 동 목록을 끝까지 받았으면 거른 뒤 남은 것이 전부다
                if len(listings) < limit and has_more else ''
            )
        )
    if is_dong_code(region.legal_division_code):
        # 직방 지역 목록은 그 동 단지를 먼저 주고 이웃 동 단지를 이어서 주며, total 도 이웃 동까지 센다. 아파트가 적은 동은
        # 처음부터 이웃 동이다 (2026-10-10 실측: 문래동1가 목록 40건이 모두 대림동·영등포동. 2026-11-11 실측: 대치동 전세
        # total 391 에 1쪽 대치동 50건, 2쪽 개포동 41·도곡동 7·대치동 2, 3쪽부터 이웃 동만). 서버가 준 결과라 빼지 않고 알린다.
        # 이웃 동이 대부분인 쪽부터는 이어 받아도 그 동 매물이 거의 없다고 알린다. 안 알리니 에이전트가 이웃 동만 나오는 쪽을
        # 7번 더 받았다 (2026-11-11 LLM 사용 시험). 목록의 local3 는 늘 와서(실측 22개 동 364건) 주소 마지막 단어가 곧 단지의 동이다
        others = [
            dong for listing in listings
            if (dong := (listing.address or '').rsplit(' ', 1)[-1]) and dong != region.name
        ]
        if others:
            names = list(dict.fromkeys(others))
            shown = '·'.join(names[:5]) + (f' 등 {len(names)}곳' if len(names) > 5 else '')
            notes.append(note(
                '범위',
                f'{len(listings)}건 중 {len(others)}건은 다른 동({shown}) 단지 매물입니다. '
                '직방 지역 목록은 그 동 단지 뒤에 이웃 동 단지를 이어서 주고, total 도 이웃 동까지 센 수입니다. '
                + ('이웃 동이 대부분인 쪽부터는 이어 받아도 그 동 매물이 거의 없습니다. ' if len(others) * 2 > len(listings) else '')
                + 'address 로 위치를 확인하세요',
            ))
    return ZigbangAptSearchResult(
        region=region,
        local_code=local_code,
        total=total,
        returned=len(listings),
        has_more=has_more,
        next_position={'code': local_code, 'offset': offset} if has_more else None,
        listings=listings,
        notes=notes,
    )


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
        url=apt_item_url(apt.item_id, item_source),
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
        approved_at=normalize_date(apt.approval_date),
        parking=parking_label(None, f'세대당 {apt.parking_count_by_household:g}대') if apt.parking_count_by_household is not None else None,
        options=None,
        manage_cost_includes=cost.include_items if cost else None,
        complex_id=apt_complex_id(apt.area_danji_id) if apt.area_danji_id else None,
        complex_name=join_address(apt.area_danji_name, apt.area_building_name),
        supply_area_m2=apt.size_contract_m2,
        total_parking_count=apt.parking_count,
        direction_criterion=criterion,
        listing_kind=apt_listing_kind(apt.item_type),
        pyeong_id=room_type.danji_room_type_id if room_type else None,
        pyeong_name=text_or_none(room_type.room_type_title.p) if room_type and room_type.room_type_title else None,
        confirmed_at=iso_date(apt.effectiveness_updated_at),
        actual_listing_checked=apt.is_actual_item_checked,
        non_compliant_building=apt.has_violations,
        residence_type=text_or_none(apt.real_type),
        hug_lessor=apt.is_hug_lessor,
        zzim_count=apt.zzim_count,
        manage_cost_excludes=cost.exclude_items if cost else None,
        manage_cost_period=text_or_none(cost.period_basis) if cost else None,
        manage_cost_method=text_or_none(cost.cost_basis_description) if cost else None,
    )


class ZigbangPublicPrice(BaseModel):
    """호의 공시가격 한 해."""

    model_config = ConfigDict(
        extra='forbid',
    )

    year: Annotated[
        int,
        Field(description='공시 연도')
    ]
    price_manwon: Annotated[
        float | None,
        Field(description='공시가격 (만원, 직방이 원 단위로 준 값을 환산). 0 이거나 직방이 주지 않으면 null (모름)')
    ] = None
    change_rate: Annotated[
        float | None,
        Field(description='전년 대비 변동률 (%, 부호 있음. 예: 26.9, -28, 0. 웹은 절댓값과 색으로 그린다). 직방이 주지 않으면 null')
    ] = None


class ZigbangCatalogResult(BaseModel):
    """같은 호·거래 유형의 아파트 매물 묶음 (catalog). 호의 직방시세·공시가격·분양가(호 정보)도 함께 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    catalog_id: Annotated[
        str,
        Field(description='묶음 ID (검색 결과의 catalog_id)')
    ]
    url: Annotated[
        str,
        Field(description='직방 웹 묶음 화면 (중개사별 매물 목록)')
    ]
    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형')
    ]
    total: Annotated[
        int | None,
        Field(description='묶음의 매물 수 (직방 itemCount. 상세를 볼 수 없는 출처도 센다). 직방이 묶음 수를 주지 않으면 모름(null)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description=(
            f'직방이 알린 묶음 매물 수(total)보다 덜 받았는지 (앞 {MAX_LIST_LIMIT}건까지만 받고, 직방이 다음 쪽을 주지 않으면 거기서 멈춘다). '
            f'total 이 null 이면 {MAX_LIST_LIMIT}건에 닿아 멈췄고 마지막 쪽이 가득 찼을 때 true (더 있을 수 있음)'
        ))
    ] = False
    listings: Annotated[
        list[ZigbangListingDetail],
        Field(description='묶음 매물 (직방이 준 순서 그대로). 매물마다 listing 상세와 같은 필드')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description=(
            '뺀 매물·일부만 받았다는 안내와, 호 정보를 받지 못해 직방시세·공시가격·분양가를 모른다는 [실패] 안내. '
            'CLI 가 notice 아래에 붙인다'
        ))
    ] = []
    estimated_sale_price_manwon: Annotated[
        float | None,
        Field(description=(
            "이 호의 직방시세® 매매가 (만원. 웹 묶음 화면 '시세 정보' 탭). 직방이 실거래를 분석해 낸 추정값이라 호가·실거래가가 아니다. "
            '직방이 주지 않거나 0 이면 null'
        ))
    ] = None
    estimated_sale_price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='직방시세® 매매 평당가 (만원, 3.3㎡당). 직방이 주지 않거나 0 이면 null')
    ] = None
    estimated_jeonse_price_manwon: Annotated[
        float | None,
        Field(description='이 호의 직방시세® 전세가 (만원). 추정값이다. 직방이 주지 않거나 0 이면 null')
    ] = None
    estimated_jeonse_price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='직방시세® 전세 평당가 (만원, 3.3㎡당). 직방이 주지 않거나 0 이면 null')
    ] = None
    public_prices: Annotated[
        list[ZigbangPublicPrice] | None,
        Field(description='공시가격 (직방 응답 순서, 최근 해부터). 공시가격이 없으면 [], 호 정보를 받지 못했거나 직방이 주지 않으면 null')
    ] = None
    presale_price_manwon: Annotated[
        float | None,
        Field(description=(
            "이 호의 분양가 (만원, 직방 `ho분양가`). 웹은 이 값이 있으면 이 값을 '이 매물 분양가' 로 보여 준다 (`ho분양가 ?? roomType분양가`). "
            '직방이 주지 않거나 0 이면 null'
        ))
    ] = None
    presale_average_price_manwon: Annotated[
        float | None,
        Field(description=(
            "같은 타입의 평균 분양가 (만원, 직방 `averageHo분양가`). 웹은 호 분양가(`presale_price_manwon`)가 있을 때만 "
            "'이 매물과 같은 타입의 평균 분양가는 …입니다' 로 함께 보여 준다. 직방이 주지 않거나 0 이면 null"
        ))
    ] = None
    presale_type_price_manwon: Annotated[
        float | None,
        Field(description=(
            "이 호가 속한 타입(평형)의 분양가 (만원, 직방 `roomType분양가`). 웹은 호 분양가가 없을 때 이 값을 '이 매물 분양가' 로 보여 주고 "
            "'호 분양가 정보를 확인할 수 없어서 이 타입의 평균 분양가를 표시합니다' 를 붙인다. 직방이 주지 않거나 0 이면 null"
        ))
    ] = None
    presale_price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description=(
            '분양가 평당가 (만원, 3.3㎡당, 직방 `pyeongPrice`). 웹이 이 매물 분양가로 보여 주는 값(호 분양가가 있으면 그 호, 없으면 타입 분양가)의 '
            '평당가다 (2026-11-19 표본 12966062: 타입 분양가 88,560 ÷ 공급 32.7평 = 2,712, 호 분양가는 null). 직방이 주지 않거나 0 이면 null'
        ))
    ] = None


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
            year=price.year, price_manwon=won_to_manwon(_known_price(price.price)), change_rate=price.compare_price_rate,
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
        url=apt_catalog_url(area_ho_id, tran_type),
        trade_type=trade_type,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=notes,
        estimated_sale_price_manwon=_known_price(sale.price if sale else None),
        estimated_sale_price_per_pyeong_manwon=_known_price(sale.pyeong_price if sale else None),
        estimated_jeonse_price_manwon=_known_price(jeonse.price if jeonse else None),
        estimated_jeonse_price_per_pyeong_manwon=_known_price(jeonse.pyeong_price if jeonse else None),
        public_prices=catalog_public_prices(price_info),
        presale_price_manwon=_known_price(presale.ho if presale else None),
        presale_average_price_manwon=_known_price(presale.average_ho if presale else None),
        presale_type_price_manwon=_known_price(presale.room_type if presale else None),
        presale_price_per_pyeong_manwon=_known_price(presale.pyeong_price if presale else None),
    )
