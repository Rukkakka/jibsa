"""단지 매물 목록 (search listings --complex): 아파트 단지와 오피스텔 건물의 매물."""

from jibsa.core.errors import JibsaError
from jibsa.core.listing import Listing
from jibsa.core.notes import (
    limit_notes,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.complex.common import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.service.common.apt import (
    apt_pagination_notes,
    catalog_null_notes,
    catalog_to_listing,
)
from jibsa.providers.zigbang.service.common.constants import (
    APT_TRAN_TYPE_BY_TRADE,
    MAX_LIST_LIMIT,
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    UNEXPECTED_FORMAT_TEXT,
)
from jibsa.providers.zigbang.service.common.danji import fetch_danji
from jibsa.providers.zigbang.service.common.ids import parse_complex_id
from jibsa.providers.zigbang.service.common.models import ZigbangRoomConditions
from jibsa.providers.zigbang.service.common.room import (
    excluded_notes,
    pin_null_notes,
    room_filter_of,
    section_ordered_ids,
    summary_to_listing,
    tradeable_summaries,
)
from jibsa.providers.zigbang.service.complex.common import fetch_building
from jibsa.providers.zigbang.service.complex.constants import DANJI_CATALOG_PAGE_SIZE
from jibsa.providers.zigbang.service.complex.models.listings import (
    ZigbangComplexListingsResult,
)


def list_complex_listings(
    client: ZigbangClient,
    complex_id: str,
    *,
    conditions: ZigbangRoomConditions | None = None,
    pyeong_ids: list[int] | None = None,
    limit: int = 20,
) -> ZigbangComplexListingsResult:
    """단지 하나의 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다.

    아파트는 단지 정보(시·도 주소용)와 단지 매물 목록(같은 호·거래 유형을 묶은 카탈로그)을 50건씩,
    오피스텔은 건물의 매물 핀·섹션을 받아 웹 건물 화면처럼 섹션 순서로 세운 뒤 15개씩 요약을 받는다
    (`_list_officetel_building_listings`). 거래 유형·가격(만원)·평형 조건은 서버에서
    거른다. 평형은 아파트만 있다. 관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔만 받으며
    건물 API 에 그대로 보내 서버에서 거른다.

    응답 목록에 빈 항목(null)이 섞여 오면 빼고 읽되 아파트는 직방 offset 이 그 자리도 세므로 받은 수(`offset`·`inspected`)에 더해 센다.
    오피스텔 건물은 핀·섹션의 빈 항목을 `[제외]` 로만 알린다 (`catalog_null_notes`·`pin_null_notes`).

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나, 오피스텔에 평형 조건을 줬거나,
            아파트에 오피스텔 전용 조건을 줬거나, 단지에 없는 평형 ID 를 줬을 때 (INVALID_ARGUMENT).
            없는 단지일 때 (NOT_FOUND).
    """
    conditions = conditions or ZigbangRoomConditions()
    kind, number = parse_complex_id(complex_id)
    building_filters: dict[str, object] = {
        # 오피스텔 건물 매물은 섞지 않은 순서로 받는다 (지도 목록과 같다, room.search_listings). 아파트는 이 값을 쓰지 않는다
        'without_random': True if kind == 'officetel' else None,
        'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in conditions.room_types],
        **room_filter_of(conditions),
    }
    if kind == 'apt' and any(value is not None and value != [] for value in building_filters.values()):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔 건물에서만 사용할 수 있습니다',
            hint='해당 조건을 빼거나 officetel-... 건물 ID 를 사용하세요',
        )
    trade_types = conditions.trade_types
    if kind == 'officetel':
        if pyeong_ids:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message='오피스텔 건물에는 평형 조건이 없습니다',
                hint='--pyeong 을 빼고 다시 조회하세요. 평형은 아파트 단지(apt-...)에만 있습니다',
            )
        return _list_officetel_building_listings(
            client, complex_id, number, conditions=conditions, limit=limit, filters=building_filters,
        )

    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    # 단지 매물 목록에는 시·도가 없어 단지 정보에서 받는다 (없는 단지도 여기서 알 수 있다)
    local1 = fetch_danji(client, complex_id, number).local1
    if trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다.
        # 없는 단지가 0건 성공으로 보이지 않도록 단지를 확인한 뒤에 돌려준다
        return ZigbangComplexListingsResult(complex_id=complex_id, total=0, returned=0, listings=[])
    listings: list[Listing] = []
    total = 0
    offset = 0
    inspected = 0
    # 목록에서 뺀 빈 항목 수와, 카탈로그의 묶인 매물 ID 목록에서 뺀 빈 항목 수 (`catalog_null_notes`)
    dropped_catalogs = 0
    dropped_id_lists = 0
    # 평형 목록(`danjiRoomTypes`)에서 뺀 빈 항목 수. 평형 ID 를 확인할 수 없을 때만 안내한다
    dropped_room_types = 0
    # 직방이 평형 목록을 주지 않아(모름) 평형 ID 를 확인하지 못했는지
    room_types_unknown = False
    seen: set[str] = set()
    while inspected < limit:
        page_size = min(DANJI_CATALOG_PAGE_SIZE, limit - inspected)
        response = client.run_request_danjis_item_catalogs(
            ZigbangDanjisItemCatalogsRequestParameterModel(
                danji_id=number,
                tran_types=tran_types,
                room_type_ids=pyeong_ids or [],
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
            if response.room_types is None:
                # 평형 목록이 없으면(모름) 평형이 없는 단지(빈 목록)와 달라, 확인하지 않고 그 평형으로 찾은 뒤 알린다
                room_types_unknown = bool(pyeong_ids)
            elif response.null_items('room_types'):
                # 평형 목록에서 빈 항목을 뺐으면 준 평형 ID 가 그 항목이었을 수 있어 단지에 있는지 확인하지 않는다
                dropped_room_types = response.null_items('room_types') if pyeong_ids else 0
            else:
                # 단지에 없는 평형이면 0건 대신 에러로 알린다. 단지 매물 목록은 없는 평형에도 빈 성공을 준다.
                # 평형 조건을 줘도 응답의 평형 목록(danjiRoomTypes)은 단지 전체라 첫 페이지로 확인한다 (2026-10-12 실측:
                # apt-68579 에 평형 999 를 주면 0건과 평형 30개, 조건 없이도 같은 30개). 평형 목록이 비어 오면(평형이 아직 없는
                # 단지) 확인하지 않는다
                known = {room_type.id for room_type in response.room_types}
                unknown = [pyeong_id for pyeong_id in pyeong_ids or [] if pyeong_id not in known]
                if known and unknown:
                    raise JibsaError(
                        code='INVALID_ARGUMENT',
                        message=f"{complex_id} 단지에 없는 평형 ID 입니다: {', '.join(map(str, unknown))}",
                        hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 --pyeong 에 주세요',
                    )
        total = response.total_count
        # 직방 offset 은 빈 항목(null)도 한 자리로 센다. 빈 항목을 빼고 읽었어도 받은 자리 수에 더해야 같은 매물을 다시 받거나 일찍 멈추지 않는다
        received = len(response.catalogs) + response.null_items('catalogs')
        dropped_catalogs += response.null_items('catalogs')
        dropped_id_lists += sum(catalog.null_items('item_id_list') for catalog in response.catalogs)
        inspected += received
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, local1)
            if listing is not None and listing.id not in seen:
                seen.add(listing.id)
                listings.append(listing)
        offset += received
        if not received or offset >= total:
            break
    listings = listings[:limit]
    notes = apt_pagination_notes(
        # 단지 하나라 지역 대신 단지 매물의 조건만 좁히라고 한다 (오피스텔 건물·다방 단지 매물과 같다)
        len(listings), limit, inspected, has_more=offset < total, narrow='거래 유형·평형·가격 조건',
    ) + catalog_null_notes('직방 단지', dropped_catalogs, dropped_id_lists)
    if dropped_room_types:
        # 평형 ID 가 단지에 있는지 볼 수 없어 확인하지 않고 그 평형으로 찾았다
        notes.append(null_items_note('직방 단지 평형', dropped_room_types))
    if room_types_unknown:
        notes.append(note(
            '참고',
            f'직방이 단지 평형 목록을 주지 않아 --pyeong 평형 ID 가 이 단지의 것인지 확인하지 못했습니다. {UNEXPECTED_FORMAT_TEXT}',
        ))
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=offset < total,
        listings=listings,
        notes=notes,
    )


def _list_officetel_building_listings(
    client: ZigbangClient,
    complex_id: str,
    building_id: int,
    *,
    conditions: ZigbangRoomConditions,
    limit: int,
    filters: dict[str, object],
) -> ZigbangComplexListingsResult:
    """오피스텔 건물 하나의 매물을 웹 건물 화면 순서로 `limit` 건 조회한다 (건물 핀 1회 + 요약 15개에 1회).

    웹 건물 화면처럼 섹션 순서대로 매물 ID 를 잇는다 (2026-11-15 번들 `loadItemsV2`: `sections.flatMap(ids)`. 실측
    officetel-20227: 핀 순서는 51154972·51094170·51155651 인데 섹션은 안심추천 51094170·51155651, 안심일반 51154972). 핀
    순서는 이 순서와 달라 쓰지 않고, 어느 섹션에도 없는 핀만 잃지 않게 맨 뒤에 핀 순서로 붙인다 (지도 목록과 같은
    `section_ordered_ids`). 섹션 안은 서버가 섞지 않은 순서(`withoutRandom`)로 받는다. 앞 `limit` 개의 요약을 받아 그 순서대로 낸다.
    """
    response = fetch_building(
        client,
        complex_id,
        ZigbangItemsOfficetelsBuildingV1RequestParameterModel(
            building_id=building_id,
            sales_types=[SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types],
            deposit_min=conditions.deposit_min,
            deposit_max=conditions.deposit_max,
            rent_min=conditions.rent_min,
            rent_max=conditions.rent_max,
            sales_price_min=conditions.price_min,
            sales_price_max=conditions.price_max,
            **filters,
        )
    )
    ids = section_ordered_ids([response])
    # 조회 예산은 요약을 받는 매물 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    scanned = ids[:limit]
    tradeable = tradeable_summaries(client, scanned)
    summaries = {summary.item_id: summary for summary in tradeable.items}
    # 요약 응답 순서에 기대지 않고 섹션 순서로 세운다
    listings: list[Listing] = [
        summary_to_listing(summaries[item_id], building_id=building_id) for item_id in scanned if item_id in summaries
    ]
    # 건물 매물은 서버가 거래 유형으로 이미 걸러 준 거래 중 매물뿐이라 매물 수가 곧 조건에 맞는 수다.
    total = len(ids)
    has_more = len(scanned) < total
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=(
            # 아래 [일부] 안내의 '직방 목록 순으로' 와 같은 말로 쓴다 (한 응답에 '순서로'·'순으로' 가 섞였다, 2026-11-10 리뷰)
            excluded_notes(
                limit, len(scanned), len(listings), order='직방 목록 순으로 앞의', has_more=has_more,
                null_items=tradeable.null_items,
            )
            # 요약을 받은 핀 수(inspected)로 limit 에 닿았는지 본다. 받은 뒤 거래 불가로 뺀 만큼 다시 채우지 않아, 돌려준 수로
            # 보면 1건만 빠져도 안내가 사라진다. 단지 하나라 지역·반경 대신 단지 매물의 조건만 좁히라고 한다. 오피스텔 건물에는
            # 평형 조건이 없어(--pyeong 은 INVALID_ARGUMENT) 오피스텔에만 있는 방 구조·면적 조건을 권한다 (2026-11-10 실측:
            # officetel-2795 --limit 5 에 '평형' 을 권했다)
            + limit_notes(
                total, len(listings), limit, max_limit=MAX_LIST_LIMIT, order='직방 목록',
                narrow='거래 유형·방 구조·면적·가격 조건', inspected=len(scanned), has_more=has_more,
            )
            + pin_null_notes('직방 오피스텔 건물 매물 핀·섹션', [response])
        ),
    )
