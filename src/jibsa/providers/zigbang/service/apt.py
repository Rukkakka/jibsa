"""아파트 매물 검색 (search listings apt): 동·구 지역 목록과 좌표가 속한 동 찾기."""

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.geo import encode_geohash
from jibsa.core.korean import (
    is_dong_code,
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    Listing,
    TradeType,
    in_range,
    note,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
    ZigbangLocalsPolygonRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.service.common import (
    APT_TRAN_TYPE_BY_TRADE,
    ZigbangAptListing,
    ZigbangRegion,
    apt_pagination_notes,
    catalog_to_listing,
    region_from_search_item,
)
from jibsa.providers.zigbang.service.region import (
    best_region_item,
    city_gu_items,
    divided_region_error,
    ga_dong_note,
    ga_dong_siblings,
    ga_dong_split,
    search_regions,
    settled_item,
)

from typing import (
    Annotated,
    Any,
)


APT_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세')
# 한 번에 받는 아파트 매물 수. 지역 목록(locals)은 20 을 넘으면 400 이고, 단지 목록(danjis)은 50 도 같은 순서·내용으로
# 준다 (2026-10-10 실측: 헬리오시티 120건 20건씩 6회 = 50건씩 3회, 요청 모델 상한이 50)
LOCAL_CATALOG_PAGE_SIZE: int = 20


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
        ZigbangRegion,
        Field(description='검색한 지역')
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


def local_code_of(legal_division_code: str) -> str:
    """법정동코드 10자리를 직방 아파트 지역 코드로 줄인다.

    직방은 시·군·구 5자리, 읍·면·동 8자리로 찾는다. 10자리를 그대로 보내면 에러 없이 0건이다. 리(10자리 끝 두
    자리가 00 이 아님)는 읍·면 8자리로 올린다 (2026-10-11 실측: 양근리 4183025021 은 0건, 양평읍 41830250 은 88건).
    시·도 2자리도 에러 없이 늘 0건이라 (2026-10-11 실측: 11·41·26·36 모두 0건, 강남구 11680 은 1683건)
    `resolve_apt_region` 이 시·도를 `RegionNotFoundError` 로 거절해 여기에는 오지 않는다. 구가 있는 시의 시 코드(성남시
    41130)도 0건이라 (2026-11-15 실측) `resolve_apt_region` 이 어느 구인지 묻는다 (`city_gu_items`).
    """
    if legal_division_code.endswith('00000000'):
        return legal_division_code[:2]
    if legal_division_code.endswith('00000'):
        return legal_division_code[:5]
    return legal_division_code[:8]


def resolve_apt_region(
    client: ZigbangClient,
    query: str,
    *,
    items: list[ZigbangSearchItemModel] | None = None,
) -> tuple[ZigbangRegion, list[str]]:
    """아파트 검색 지역(동·구 하나)과 결과에 붙일 안내를 찾는다. 아파트는 반경이 아니라 동·구 단위로 조회한다.

    웹 지역 매물 화면(`/home/apt/items/{지역 코드}`)은 지역 코드 하나의 목록만 보여 준다 (2026-11-15 캡처). 그래서
    '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)이나 구가 있는 시(성남시 → 분당구·수정구·중원구)는 목록을 합치지 않고
    어느 동·구인지 묻는다. `items` 는 같은 검색어로 이미 받은 `search_regions` 결과다. 주면 지역 검색을 다시 하지 않는다.

    Returns:
        (검색할 동·구, 안내).

    Raises:
        RegionNotFoundError: 법정동코드가 있는 지역 결과가 없거나(역 이름만 준 경우 등) 시·도일 때. 직방 지역 목록은
            시·도 코드에 늘 0건이다 (`local_code_of`).
        RegionAmbiguousError: 같은 이름의 동·구가 여러 곳일 때 (`settled_item`), '○가' 로만 나뉜 동이거나 구가 있는
            시일 때 (`divided_region_error`).
    """
    items = search_regions(client, query) if items is None else items
    best = best_region_item(query, items, require_code=True)
    # 같은 이름 동·구는 room·store·stay 와 같이 검색어 앞 낱말로 가리고, 가려지지 않으면 묻는다
    best = settled_item(query, items, best) if best is not None else None
    code = best.source.legal_division_code if best and best.source else None
    if best is None or code is None or code.endswith('00000000'):
        # 행정동(역삼1동)은 직방 지역 검색이 0건이라(2026-10-11 실측: 역삼1동·화곡제1동·상계3.4동·월곡1동) CLI 의 위치
        # 찾기가 행정동 힌트를 낸다. 역 이름이면 CLI 가 이 에러를 잡아 그 위치가 속한 동(`apt_dong_at`)으로 찾는다
        raise RegionNotFoundError(
            query,
            hint="아파트는 동·구 단위로 조회합니다. 동 이름(예: '역삼동')이나 구 이름(예: '강남구'), 역 이름(예: '강남역')으로 다시 검색하세요",
        )
    # 구 단위로 조회해 넓은 지역 안내(wide_area_note)는 붙이지 않는다
    notes: list[str] = []
    gus = city_gu_items(query, items, best)
    if gus:
        raise divided_region_error(query, [region_from_search_item(item) for item in gus])
    # 지역 결과는 모두 법정동코드가 있어 (2026-10-11 실측: '○가' 동 145건·그 밖의 지역 25건) 형제 동은 코드로 다시 거르지 않는다
    siblings = ga_dong_siblings(query, items, best)
    split = ga_dong_split(query, siblings, best)
    if split:
        raise divided_region_error(query, [region_from_search_item(item) for item in split])
    if is_ri_code(code):
        # 리는 읍·면 지역 목록으로 찾는다 (local_code_of). 지역 결과의 local3 이 그 읍·면이다 (2026-10-11 실측: 양근리 → 양평읍)
        town = best.source.local3 if best.source and best.source.local3 else '읍·면'
        notes.append(note(
            '범위',
            f"{quoted(query, '은/는')} 리 단위라 직방 아파트 목록이 받지 않아 상위 {town} 전체 매물을 찾았습니다. "
            'address 로 위치를 확인하세요',
        ))
    split_note = ga_dong_note(query, siblings, best)
    return region_from_search_item(best), notes + ([split_note] if split_note else [])


# 좌표가 속한 동을 물을 geohash 정밀도. 칸이 크면 옆 동이 잡힌다 (2026-11-15 실측: 강남역은 정밀도 5 에 논현동, 6 에 역삼동,
# 7·8 에 서초동, 9·10·12 에 역 주소와 같은 역삼동. 역삼동 한가운데는 8~12 모두 역삼동)
APT_DONG_GEOHASH_PRECISION: int = 10


def apt_dong_at(client: ZigbangClient, lat: float, lng: float) -> ZigbangRegion:
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
    return ZigbangRegion(name=response.name or code, lat=lat, lng=lng, legal_division_code=f'{code}00')


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

    거래 유형·가격·공급면적은 서버에서 거른다. 전용면적은 직방이 받지 않아 받은 뒤에 거른다.
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


def search_apt_listings(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangAptConditions | None = None,
    limit: int = 20,
    start: dict[str, Any] | None = None,
) -> ZigbangAptSearchResult:
    """지역(동·구 하나) 안의 아파트 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다.

    웹 지역 매물 화면(`/home/apt/items/{지역 코드}`)이 부르는 지역 목록(`/apt/locals/{코드}/item-catalogs`)과 같다
    (2026-11-15 캡처). 반경 검색이 아니라 거리가 없다. 거래 유형·가격(만원) 조건은 서버에서 거른다. 면적은 다른 유형과
    같게 전용면적(㎡)으로 받는데, 직방 지역 목록은 공급면적 조건만 받아 전용면적은 받은 뒤에 거른다. 공급면적은
    supply_area_min/max_m2로 서버에 전달한다. 실제로 받은 원본 개수로 조회 예산을 계산하며 제외된 만큼 추가 조회하지 않는다.

    `start` 는 이어 받기(`--next`) 위치다. 앞서 받은 수(`offset`)부터 직방 offset 으로 받는다. 지역 목록은 같은 이름이면
    같은 순서로 나온다 (resolve_apt_region).

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
                offset=offset,
                limit=min(LOCAL_CATALOG_PAGE_SIZE, limit - inspected),
            )
        )
        total = response.count
        inspected += len(response.catalogs)
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, response.local1)
            if listing is not None and area_matches(listing, conditions.area_min_m2, conditions.area_max_m2):
                listings.append(listing)
        offset += len(response.catalogs)
        done = not response.catalogs or offset >= response.count
    has_more = not done
    notes = apt_pagination_notes(
        len(listings), limit, inspected, has_more=has_more, resumable=has_more, resumed=start is not None, narrow='조건·지역',
    )
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
