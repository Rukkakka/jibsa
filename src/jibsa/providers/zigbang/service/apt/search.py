"""아파트 매물 검색 (search listings apt): 지역 목록 조회와 좌표가 속한 동 찾기."""

import re

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.geo import encode_geohash
from jibsa.core.korean import (
    full_legal_division_code,
    is_dong_code,
)
from jibsa.core.listing import (
    in_range,
    note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.apt.search import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
    ZigbangLocalsPolygonRequestParameterModel,
)
from jibsa.providers.zigbang.service.apt.constants import (
    APT_DONG_GEOHASH_PRECISION,
    LOCAL_CATALOG_PAGE_SIZE,
)
from jibsa.providers.zigbang.service.apt.models import (
    ZigbangAptConditions,
    ZigbangAptSearchResult,
)
from jibsa.providers.zigbang.service.common.apt import (
    apt_pagination_notes,
    catalog_null_notes,
    catalog_to_listing,
)
from jibsa.providers.zigbang.service.common.constants import APT_TRAN_TYPE_BY_TRADE
from jibsa.providers.zigbang.service.common.models import (
    ZigbangAptListing,
    ZigbangAptRegion,
)
from jibsa.providers.zigbang.service.region import local_code_of

from typing import Any


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
    return ZigbangAptRegion(name=response.name or code, lat=lat, lng=lng, legal_division_code=full_legal_division_code(code))


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
        JibsaError: 공급면적이 0 미만이거나 상한이 하한보다 작을 때, 이어 받기 표의 지역 코드(`code`)가 다시 찾은 지역과
            다르거나 표 모양이 예전 것일 때 (INVALID_ARGUMENT).
    """
    conditions = conditions or ZigbangAptConditions()
    # 잘못된 공급면적 범위는 HTTP 요청 전에 거절한다
    if any(value is not None and value < 0 for value in (conditions.supply_area_min_m2, conditions.supply_area_max_m2)):
        raise JibsaError(
            code='INVALID_ARGUMENT', message='공급면적은 0 이상이어야 합니다',
            hint='--supply-area-min/max 에 ㎡ 단위의 0 이상 값을 주세요',
        )
    if (
        conditions.supply_area_min_m2 is not None
        and conditions.supply_area_max_m2 is not None
        and conditions.supply_area_min_m2 > conditions.supply_area_max_m2
    ):
        raise JibsaError(
            code='INVALID_ARGUMENT', message='공급면적 상한은 하한 이상이어야 합니다',
            hint='--supply-area-min/max 범위를 확인하세요',
        )
    if region.legal_division_code is None:
        raise RegionNotFoundError(region.name)
    local_code = local_code_of(region.legal_division_code)
    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in conditions.trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    if conditions.trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다
        return ZigbangAptSearchResult(region=region, total=0, returned=0, listings=[])
    listings: list[ZigbangAptListing] = []
    total = 0
    offset = 0
    done = False
    if start is not None:
        # 다른 동의 offset 으로 받거나, 처음부터 다시 줘도 알 수 없다. 여러 동을 합치던 예전 표(codes)도 여기서 막는다
        if start.get('code') != local_code:
            # 이어 받기 표의 지역이 다시 찾은 지역과 다르다. 처음부터 다시 주면 앞 결과와 겹치는데 알 수 없다
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message='앞 결과 뒤로 직방 지역 검색 결과가 바뀌어 이어 받을 수 없습니다',
                hint='--next 없이 같은 지역·조건으로 다시 검색하세요',
            )
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
            # 전용면적 조건이 있는데 면적을 모르면 맞지 않는다고 본다
            if listing is not None and in_range(listing.area_m2, conditions.area_min_m2, conditions.area_max_m2):
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
        total=total,
        returned=len(listings),
        has_more=has_more,
        next_position={'code': local_code, 'offset': offset} if has_more else None,
        listings=listings,
        notes=notes,
    )
