"""아파트 매물 검색 (search listings apt): 지역 목록과 반경(nearby-danjis) 검색."""

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
from jibsa.core.korean import (
    is_dong_code,
    is_ri_code,
    quoted,
)
from jibsa.core.listing import (
    Listing,
    TradeType,
    in_range,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
    ZigbangNearbyDanjisRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.common import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjiRoomTypeModel,
    ZigbangSearchItemModel,
)
from jibsa.providers.zigbang.service.common import (
    APT_TRAN_TYPE_BY_TRADE,
    DANJI_CATALOG_PAGE_SIZE,
    ZigbangAptListing,
    ZigbangRegion,
    apt_pagination_notes,
    catalog_to_listing,
    region_from_search_item,
)
from jibsa.providers.zigbang.service.region import (
    best_region_item,
    city_gu_items,
    ga_dong_note,
    ga_dong_siblings,
    ga_dong_split,
    region_notes,
    search_regions,
)

from typing import Annotated


def merged_dong_region(
    region: ZigbangRegion,
    parts: list[ZigbangRegion],
    center: tuple[float, float] | None = None,
) -> ZigbangRegion:
    """'○가' 동들(성수동1가·2가)을 함께 찾은 결과의 검색 중심. room·store·stay·apt 가 같은 모양으로 낸다.

    이름·주소의 동을 '성수동1가·성수동2가' 로 바꾸고, 중심은 `center`(없으면 동 중심들의 가운데)로 옮기며,
    한 동의 법정동코드는 뗀다.
    """
    names = '·'.join(part.name for part in parts)
    lat, lng = center or (sum(part.lat for part in parts) / len(parts), sum(part.lng for part in parts) / len(parts))
    parent = (region.address or '').rsplit(' ', 1)[0]
    return region.model_copy(update={
        'name': names, 'address': f'{parent} {names}'.strip(), 'lat': lat, 'lng': lng, 'legal_division_code': None,
    })


def merged_gu_region(region: ZigbangRegion, parts: list[ZigbangRegion]) -> ZigbangRegion:
    """구가 있는 시의 구들(성남시 분당구·수정구)을 함께 찾은 아파트 결과의 검색 중심. `merged_dong_region` 의 구 판이다.

    이름은 '성남시 분당구·수정구·중원구', 주소는 '경기도 성남시 분당구·수정구·중원구' 로 찾은 구만 적고, 중심은 구 중심들의
    가운데로 옮기며, 한 구의 법정동코드는 뗀다.
    """
    city = region.name.split()[0]
    gus = '·'.join(part.name.split()[-1] for part in parts)
    parent = (region.address or '').rsplit(' ', 1)[0]
    return region.model_copy(update={
        'name': f'{city} {gus}',
        'address': f'{parent} {gus}'.strip(),
        'lat': sum(part.lat for part in parts) / len(parts),
        'lng': sum(part.lng for part in parts) / len(parts),
        'legal_division_code': None,
    })


APT_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세')
# 한 번에 받는 아파트 매물 수. 지역 목록(locals)은 20 을 넘으면 400 이고, 단지 목록(danjis)은 50 도 같은 순서·내용으로
# 준다 (2026-10-10 실측: 헬리오시티 120건 20건씩 6회 = 50건씩 3회, 요청 모델 상한이 50)
LOCAL_CATALOG_PAGE_SIZE: int = 20


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
        Field(description='조회한 직방 지역 코드 (법정동코드 앞 2·5·8자리). 여러 동을 함께 찾았으면 쉼표로 잇는다')
    ]
    total: Annotated[
        int,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
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
    `resolve_apt_region` 이 시·도를 반경 검색으로 넘겨 여기에는 오지 않는다. 구가 있는 시의 시 코드(성남시 41130)도
    0건이라 구들을 함께 찾는다 (`city_gu_items`).
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
) -> tuple[ZigbangRegion, list[str], list[ZigbangRegion]]:
    """아파트 검색 지역을 찾는다. 아파트는 반경이 아니라 동·구 단위로 조회하므로 지역 결과가 필요하다.

    같은 이름의 동 없이 '○가' 로만 나뉜 동(성수동 → 성수동1가·2가)이면 검색 중심 동과 함께 찾을 나머지 동들을
    세 번째 값으로 준다. 구가 있는 시(성남시)면 같은 자리에 나머지 구들을 준다. `items` 는 같은 검색어로 이미 받은
    `search_regions` 결과다. 주면 지역 검색을 다시 하지 않는다.

    Raises:
        RegionNotFoundError: 법정동코드가 있는 지역 결과가 없거나(역 이름만 준 경우 등) 시·도일 때. 직방 지역 목록은
            시·도 코드에 늘 0건이라(`local_code_of`) CLI 가 반경 검색으로 넘긴다.
        RegionAmbiguousError: 같은 이름의 동·구가 여러 곳일 때 (`region_notes`).
    """
    items = search_regions(client, query) if items is None else items
    best = best_region_item(query, items, require_code=True)
    code = best.source.legal_division_code if best and best.source else None
    if best is None or code is None or code.endswith('00000000'):
        # 행정동(역삼1동)은 직방 지역 검색이 0건이라(2026-10-11 실측: 역삼1동·화곡제1동·상계3.4동·월곡1동) CLI 의 반경 검색
        # 위치 찾기가 행정동 힌트를 낸다. 여기서 낸 에러는 CLI 가 잡아 반경 검색으로 넘어가므로 힌트를 따로 고르지 않는다
        raise RegionNotFoundError(
            query,
            hint="아파트는 동·구 단위로 조회합니다. 역·시·도 이름 대신 동 이름(예: '역삼동')이나 구 이름(예: '강남구')으로 다시 검색하세요",
        )
    # 구 단위로 조회해 넓은 지역 안내(wide_area_note)는 붙이지 않는다
    notes = region_notes(query, items, best)
    gus = city_gu_items(query, items, best)
    if gus:
        return region_from_search_item(best), notes, [region_from_search_item(item) for item in gus if item is not best]
    if is_ri_code(code):
        # 리는 읍·면 지역 목록으로 찾는다 (local_code_of). 지역 결과의 local3 이 그 읍·면이다 (2026-10-11 실측: 양근리 → 양평읍)
        town = best.source.local3 if best.source and best.source.local3 else '읍·면'
        notes.append(
            f"{quoted(query, '은/는')} 리 단위라 직방 아파트 목록이 받지 않아 상위 {town} 전체 매물을 찾았습니다. "
            '리 주변만 보려면 --radius 로 반경 검색하세요'
        )
    # 지역 결과는 모두 법정동코드가 있어 (2026-10-11 실측: '○가' 동 145건·그 밖의 지역 25건) 형제 동은 코드로 다시 거르지 않는다
    siblings = ga_dong_siblings(query, items, best)
    split = ga_dong_split(query, siblings, best)
    if split:
        # 동마다 지역 목록을 받아 합친다 (search_apt_listings 의 extra_regions). 검색 중심 동은 빼고 준다
        return region_from_search_item(best), notes, [region_from_search_item(item) for item in split if item is not best]
    split_note = ga_dong_note(query, siblings, best)
    return region_from_search_item(best), notes + ([split_note] if split_note else []), []


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


def _pyeong_supply_matches(room_type: ZigbangDanjiRoomTypeModel, minimum: float | None, maximum: float | None) -> bool:
    """평형 이름(공급면적 ㎡, 예: '80C' 는 공급 80.xx㎡)이 공급면적 조건에 들 수 있는지.

    이름은 소수점을 버린 값이라 양쪽에 1㎡ 여유를 두고 고른다. 정확한 조건은 받은 매물에서 다시 거른다.
    이름에 숫자가 없으면 모르니 고른다.
    """
    label = room_type.room_type_title.m2 if room_type.room_type_title else None
    match = re.match(r'\d+', label or '')
    if match is None:
        return True
    area = int(match.group())
    return (minimum is None or area + 1 >= minimum) and (maximum is None or area - 1 <= maximum)


class ZigbangAptConditions(RequestModel):
    """아파트 매물 조건 (search listings apt). 금액은 만원, 면적은 ㎡.

    거래 유형·가격은 서버에서 거른다. 전용면적은 직방이 받지 않아 받은 뒤에 거르고, 공급면적은 지역 목록이면 서버에,
    반경 검색이면 단지 평형으로 거른다.
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
    extra_regions: list[ZigbangRegion] | None = None,
) -> ZigbangAptSearchResult:
    """지역(동·구) 안의 아파트 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다.

    `extra_regions` 는 함께 찾을 동 ('○가' 로 나뉜 성수동1가·2가 등) 또는 구가 있는 시의 나머지 구 (성남시 수정구·중원구).
    한 지역이 예산을 다 쓰지 않도록 남은 예산을 아직 끝나지 않은 지역 수로 나눠 번갈아 받는다 (지역 하나면 그 지역만 받는다).

    웹 아파트 지도의 지역 매물 목록과 같다. 반경 검색이 아니라 거리가 없다. 거래 유형·가격(만원) 조건은
    서버에서 거른다. 면적은 다른 유형과 같게 전용면적(㎡)으로 받는데, 직방 지역 목록은 공급면적 조건만
    받아 전용면적은 받은 뒤에 거른다. 공급면적은 supply_area_min/max_m2로 서버에 전달한다. 실제로 받은 원본 개수로 조회 예산을 계산하며 제외된 만큼 추가 조회하지 않는다.
    """
    conditions = conditions or ZigbangAptConditions()
    _validate_apt_supply_area(conditions.supply_area_min_m2, conditions.supply_area_max_m2)
    regions = [region, *(extra_regions or [])]
    for part in regions:
        if part.legal_division_code is None:
            raise RegionNotFoundError(part.name)
    local_codes = [local_code_of(part.legal_division_code or '') for part in regions]
    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in conditions.trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    if conditions.trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다
        return ZigbangAptSearchResult(region=region, local_code=local_codes[0], total=0, returned=0, listings=[])
    listings: list[ZigbangAptListing] = []
    totals = [0] * len(local_codes)
    offsets = [0] * len(local_codes)
    done = [False] * len(local_codes)
    asked = [False] * len(local_codes)
    inspected = 0
    seen: set[str] = set()
    filter_area = conditions.area_min_m2 is not None or conditions.area_max_m2 is not None
    while inspected < limit and not all(done):
        active = [index for index, finished in enumerate(done) if not finished]
        share = max(1, (limit - inspected) // len(active))
        for index in active:
            if inspected >= limit:
                break
            page_size = min(LOCAL_CATALOG_PAGE_SIZE, share, limit - inspected)
            asked[index] = True
            response = client.run_request_locals_item_catalogs(
                ZigbangLocalsItemCatalogsRequestParameterModel(
                    local_code=local_codes[index],
                    tran_types=tran_types,
                    sales_price_min=conditions.price_min,
                    sales_price_max=conditions.price_max,
                    deposit_min=conditions.deposit_min,
                    deposit_max=conditions.deposit_max,
                    rent_min=conditions.rent_min,
                    rent_max=conditions.rent_max,
                    supply_area_min_m2=conditions.supply_area_min_m2,
                    supply_area_max_m2=conditions.supply_area_max_m2,
                    offset=offsets[index],
                    limit=page_size,
                )
            )
            totals[index] = response.count
            inspected += len(response.catalogs)
            for catalog in response.catalogs:
                listing = catalog_to_listing(catalog, response.local1)
                if listing is not None and listing.id not in seen and area_matches(listing, conditions.area_min_m2, conditions.area_max_m2):
                    seen.add(listing.id)
                    listings.append(listing)
            offsets[index] += len(response.catalogs)
            if not response.catalogs or offsets[index] >= response.count:
                done[index] = True
    total = sum(totals)
    listings = listings[:limit]
    # --limit 이 동 수보다 작으면 뒤쪽 동은 한 번도 부르지 않는다 (문래동 1가~6가 + --limit 3 → 1~3가만).
    # 결과·안내에는 실제로 부른 동만 넣는다
    searched = [part for part, was_asked in zip(regions, asked) if was_asked]
    skipped = [part.name for part, was_asked in zip(regions, asked) if not was_asked]
    notes = apt_pagination_notes(total, len(listings), limit, inspected)
    if filter_area:
        # 받은 원본(limit 건) 안에서만 거르므로 맞는 매물이 더 있어도 적게 나온다 (2026-10-09 실측: 대치동
        # 전용 150㎡ 이상이 20건 중 2건, 공급 190㎡ 이상 서버 조건으로는 20건 중 19건)
        notes.append(
            f'전용면적 조건은 직방이 받지 않아 받아 온 {inspected}건에서만 거릅니다. total({total}건)은 전용면적으로 거르기 전 수입니다'
            + (
                '. 조건에 맞는 매물이 더 있을 수 있으니, 빠짐없이 찾으려면 직방이 서버에서 거르는 공급면적 조건'
                '(--supply-area-min/--supply-area-max)으로 다시 찾으세요. 아파트 공급면적은 대개 전용면적의 1.1~1.5배'
                '(중간 1.3배 안팎)이니 넉넉히 잡고 결과의 area_m2 로 전용면적을 확인하세요'
                if len(listings) < limit else ''
            )
        )
    if is_dong_code(region.legal_division_code):
        # 아파트가 적은 동은 직방 지역 목록이 이웃 동 단지를 대신 준다 (2026-10-10 실측: 문래동1가 목록 40건이 모두
        # 대림동·영등포동). 서버가 준 결과라 빼지 않고 알린다. 목록의 local3 는 늘 와서(실측 22개 동 364건)
        # 주소 마지막 단어가 곧 단지의 동이다
        searched_names = {part.name for part in searched}
        others = [
            dong for listing in listings
            if (dong := (listing.address or '').rsplit(' ', 1)[-1]) and dong not in searched_names
        ]
        if others:
            names = list(dict.fromkeys(others))
            shown = '·'.join(names[:5]) + (f' 등 {len(names)}곳' if len(names) > 5 else '')
            notes.append(
                f'{len(listings)}건 중 {len(others)}건은 다른 동({shown}) 단지 매물입니다. '
                '직방 지역 목록은 동 안에 아파트가 적으면 이웃 동 단지도 함께 줍니다. address 로 위치를 확인하세요'
            )
    head: list[str] = []
    # 함께 찾는 지역은 '○가' 동이거나 구가 있는 시의 구다 (resolve_apt_region)
    unit = '동' if is_dong_code(regions[0].legal_division_code) else '구'
    if len(searched) > 1:
        # 작은 동은 직방 지역 목록이 이웃 동 단지를 대신 줘 동끼리 겹친다 (2026-10-10 실측: 문래동1가 목록은 모두
        # 대림동·영등포동 단지). 겹친 매물은 한 번만 내보내지만 total 은 동마다의 집계를 더한 값이다
        head.append(
            f"{'·'.join(part.name for part in searched)}를 함께 찾았습니다 (--limit 예산을 {unit}마다 나눠 씁니다). "
            + (
                'total 은 동마다 직방이 집계한 수를 더한 값이라 겹치는 매물이 두 번 세어졌을 수 있습니다'
                if unit == '동' else 'total 은 구마다 직방이 집계한 수를 더한 값입니다'
            )
        )
        region = merged_dong_region(region, searched) if unit == '동' else merged_gu_region(region, searched)
    if skipped:
        head.append(
            f"--limit({limit})이 함께 찾을 {unit} 수({len(regions)})보다 작아 {'·'.join(skipped)}는 찾지 않았습니다. "
            f'모두 찾으려면 --limit 을 {len(regions)} 이상으로 주세요'
        )
    notes = head + notes
    return ZigbangAptSearchResult(
        region=region,
        local_code=','.join(code for code, was_asked in zip(local_codes, asked) if was_asked),
        total=total,
        returned=len(listings),
        listings=listings,
        notes=notes,
    )


APT_NEAR_MAX_RADIUS_KM: float = 2.0
# 단지마다 요청이 하나씩 들어 훑는 단지 수에 상한을 둔다 (강남역 1km 안 단지 54곳)
APT_NEAR_MAX_COMPLEXES: int = 30
# 면적 조건은 서버가 받지 않아 맞는 단지가 멀리 있기 쉬워 더 훑는다. 2026-10-10 실측: 강남역 1km 안 공급 50㎡ 이하
# 매물이 있는 단지 3곳이 가까운 순 40·49·50번째라 30곳 상한에서는 찾지 못했다
APT_NEAR_MAX_COMPLEXES_WITH_AREA: int = 60


class ZigbangAptNearSearchResult(BaseModel):
    """아파트 반경 검색 결과. 가까운 단지부터 그 단지 매물을 모은다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float,
        Field(description='검색 반경 (km)')
    ]
    complexes_in_radius: Annotated[
        int,
        Field(description='반경 안 아파트 단지 수')
    ]
    complexes_scanned: Annotated[
        int,
        Field(description='매물을 조회한 단지 수 (가까운 순). limit 이 차거나 상한에 닿으면 멈춘다')
    ]
    total: Annotated[
        int,
        Field(description='조회한 단지 안에서 조건에 맞는 매물 수 (limit 적용 전). 조회하지 않은 단지는 세지 않는다')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    listings: Annotated[
        list[ZigbangAptListing],
        Field(description='단지가 가까운 순의 매물. distance_km 는 단지까지 거리')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def search_apt_listings_near(
    client: ZigbangClient,
    region: ZigbangRegion,
    *,
    conditions: ZigbangAptConditions | None = None,
    radius_km: float = 1.0,
    limit: int = 20,
    max_complexes: int = APT_NEAR_MAX_COMPLEXES,
    max_complexes_with_area: int = APT_NEAR_MAX_COMPLEXES_WITH_AREA,
) -> ZigbangAptNearSearchResult:
    """중심점 반경 안의 아파트 매물을 가까운 단지부터 `limit` 건 조회한다.

    직방에 반경 안 아파트 매물을 한 번에 주는 API 가 열려 있지 않아, 반경 안 단지를 가까운 순으로 받고
    (1회) 단지마다 매물 목록을 받는다 (단지당 1회 이상). 조건이 까다로우면 매물 없는 단지를 많이 훑으므로
    `max_complexes` 곳(면적 조건이 있으면 `max_complexes_with_area` 곳)에서 멈추고 `notes` 로 알린다.
    공급면적 조건이 있으면 단지마다 평형 목록을 먼저 받아(1회) 맞는 평형만 요청해, 큰 평형이 예산을 쓰지 않게 한다. 거래 유형·가격 조건은 서버에서, 전용·공급면적은 받은 뒤에
    거른다 (단지 매물 API 에 면적 조건이 없다). 매물의 `distance_km` 는 단지까지 거리다.
    """
    conditions = conditions or ZigbangAptConditions()
    _validate_apt_supply_area(conditions.supply_area_min_m2, conditions.supply_area_max_m2)
    trade_types = conditions.trade_types
    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    # 아파트에는 단기임대가 없다. 조건을 비워 보내면 전체가 오므로 단지 목록부터 조회하지 않는다
    skip = bool(trade_types) and not tran_types
    danjis = [] if skip else client.run_request_nearby_danjis(
        ZigbangNearbyDanjisRequestParameterModel(lat=region.lat, lng=region.lng, radius=radius_km)
    ).danjis
    supply_filtered = conditions.supply_area_min_m2 is not None or conditions.supply_area_max_m2 is not None
    area_filtered = supply_filtered or conditions.area_min_m2 is not None or conditions.area_max_m2 is not None
    if area_filtered:
        max_complexes = max_complexes_with_area
    listings: list[ZigbangAptListing] = []
    total = 0
    scanned = 0
    inspected = 0
    seen: set[str] = set()
    for danji in danjis[:max_complexes]:
        if inspected >= limit:
            break
        scanned += 1
        distance_km = None if danji.distance_m is None else round(danji.distance_m / 1000, 2)
        room_type_ids: list[int] = []
        if supply_filtered:
            # 평형 목록만 보려는 요청이라 받은 1건은 쓰지 않고 예산에도 넣지 않는다 (평형을 지정해도 목록은 같다)
            probe = client.run_request_danjis_item_catalogs(
                ZigbangDanjisItemCatalogsRequestParameterModel(danji_id=danji.id, limit=1)
            )
            room_type_ids = [
                room_type.id for room_type in probe.room_types
                if _pyeong_supply_matches(room_type, conditions.supply_area_min_m2, conditions.supply_area_max_m2)
            ]
            # 평형 목록은 매물 유무와 상관없이 단지의 모든 평형이 와 빈 채로 오지 않는다. 고른 평형이 없으면 조건에 맞는 평형이
            # 없는 것이다 (2026-10-18 실측: 강남역 1km 단지 53곳 중 앞 10곳 모두 평형 2~10개, 매물 0건 단지도 같음).
            # 2026-10-18 리뷰 오탐 확인
            if not room_type_ids:
                continue
        offset = 0
        while inspected < limit:
            page_size = min(DANJI_CATALOG_PAGE_SIZE, limit - inspected)
            response = client.run_request_danjis_item_catalogs(
                ZigbangDanjisItemCatalogsRequestParameterModel(
                    danji_id=danji.id,
                    tran_types=tran_types,
                    room_type_ids=room_type_ids,
                    sales_price_min=conditions.price_min,
                    sales_price_max=conditions.price_max,
                    deposit_min=conditions.deposit_min,
                    deposit_max=conditions.deposit_max,
                    rent_min=conditions.rent_min,
                    rent_max=conditions.rent_max,
                    offset=offset,
                    limit=page_size,
                )
            )
            if offset == 0:
                total += response.total_count
            inspected += len(response.catalogs)
            for catalog in response.catalogs:
                listing = catalog_to_listing(catalog, danji.local1)
                if listing is None or listing.id in seen or not area_matches(listing, conditions.area_min_m2, conditions.area_max_m2):
                    continue
                # 단지 매물 API 는 공급면적 필터가 없어 요약의 값으로 거른다
                if not in_range(listing.supply_area_m2, conditions.supply_area_min_m2, conditions.supply_area_max_m2):
                    continue
                seen.add(listing.id)
                listings.append(listing.model_copy(update={'distance_km': distance_km}))
            offset += len(response.catalogs)
            if inspected >= limit or not response.catalogs or offset >= response.total_count:
                break

    listings = listings[:limit]
    # 반경 안 단지를 다 훑고 예산도 남았으면 빠진 매물이 없어 알리지 않는다. 단지 상한에 걸리면 --limit 을 늘려도
    # 못 찾아, --limit 안내 대신 서버가 공급면적을 거르는 동·구 검색을 권한다
    area_capped = area_filtered and len(listings) < limit and (scanned < len(danjis) or inspected >= limit)
    notes = apt_pagination_notes(
        total, len(listings), limit, inspected, has_more=len(danjis) > scanned, suggest_limit=not area_capped,
    )
    unscanned = len(danjis) - scanned
    if unscanned > 0 and scanned >= max_complexes and inspected < limit:
        notes.append(
            f'반경 안 아파트 단지 {len(danjis)}곳 중 가까운 {scanned}곳만 매물을 조회했습니다 (단지마다 요청이 들어 '
            f'{max_complexes}곳에서 멈춥니다). 더 보려면 반경을 줄이거나 거래 유형·가격 조건을 넓히거나, '
            '--radius 없이 동 이름으로 jibsa zigbang search listings apt <동> 을 쓰면 동 전체를 빠짐없이 봅니다'
        )
    if conditions.area_min_m2 is not None or conditions.area_max_m2 is not None:
        notes.append('아파트 면적 조건은 직방이 받지 않아 받은 매물에서 거릅니다. total 은 면적으로 거르기 전 수입니다')
    if supply_filtered:
        notes.append(
            '아파트 반경 검색의 공급면적 조건은 단지마다 맞는 평형만 요청한 뒤 받은 매물에서 다시 거릅니다. '
            'total 은 공급면적으로 거르기 전 수입니다'
        )
    if area_capped:
        notes.append(
            f'반경 검색은 면적을 서버에서 거르지 못해 반경 안 단지 {len(danjis)}곳 중 가까운 {scanned}곳만 훑었습니다. '
            '특정 면적의 아파트를 빠짐없이 찾으려면 --radius 없이 동·구 이름과 --supply-area-min/--supply-area-max 로 '
            '찾으세요 (동·구 검색은 공급면적을 서버에서 거릅니다. 공급면적은 대개 전용면적의 1.1~1.5배)'
        )
    return ZigbangAptNearSearchResult(
        region=region,
        radius_km=radius_km,
        complexes_in_radius=len(danjis),
        complexes_scanned=scanned,
        total=total,
        returned=len(listings),
        listings=listings,
        notes=notes,
    )
