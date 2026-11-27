"""단지 평형과 단지 없는 매물의 실거래 (real-price)."""
from collections.abc import Callable
from datetime import datetime

from jibsa.core.dates import KST
from jibsa.core.errors import JibsaError
from jibsa.core.listing import normalize_floor
from jibsa.core.notes import (
    SAME_AREA_PYEONG_TRADES_NOTE,
    UPDATE_MAYBE_NEEDED,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.real_price.trades import (
    REAL_PRICE_PAGE_LIMIT,
    DabangRealPriceComplexHistoriesV5RequestParameterModel,
    DabangRealPriceHouseHistoryV5RequestParameterModel,
    DabangRealPriceHouseInitV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.real_price.trades import (
    DabangRealPriceHistoryModel,
    DabangRealPriceHouseHistoryResultModel,
    DabangRealPriceHouseInitResultModel,
    DabangRealPriceHouseScopeModel,
)
from jibsa.providers.dabang.service.common.constants import COMPLEX_URL, LISTING_URL
from jibsa.providers.dabang.service.common.paging import more_after
from jibsa.providers.dabang.service.common.text import contract_date
from jibsa.providers.dabang.service.real_price.common import (
    fetch_complex_space,
    primary_space,
)
from jibsa.providers.dabang.service.real_price.constants import (
    BUILDING_VIEW_LABELS,
    REAL_PRICE_MAX_PAGES,
    SEARCH_TYPE_BY_TRADE,
    TRADE_BY_PRICE_TYPE,
    TRADE_BY_SEARCH_TYPE,
    RealPriceTrade,
)
from jibsa.providers.dabang.service.real_price.models.trades import (
    AreaKind,
    DabangRealPrice,
    DabangRealPriceResult,
)

from typing import (
    NamedTuple,
)


class _Page(NamedTuple):
    """실거래 한 쪽 (단지·매물 응답에서 같은 뜻의 칸)."""

    histories: list[DabangRealPriceHistoryModel]
    total: int | None
    has_more: bool
    # 다방이 줄 목록에 섞어 줘서 뺀 빈 항목 수
    dropped: int = 0


class _Collected(NamedTuple):
    prices: list[DabangRealPrice]
    total: int | None
    has_more: bool
    unknown: int
    dropped: int


def period_months(years: int, today: datetime | None = None) -> tuple[str, str]:
    """`years` 년 기간의 (시작 달, 끝 달) `YYYYMM`. 화면처럼 이번 달을 끝으로 `12 × years` 달 (3년 = 36달)."""
    now = today or datetime.now(KST)
    end = now.year * 12 + now.month - 1
    start = end - 12 * years + 1
    return f'{start // 12:04d}{start % 12 + 1:02d}', f'{now.year:04d}{now.month:02d}'


def _unknown_trade_note(count: int) -> list[str]:
    """거래 유형을 모르는 줄을 뺀 안내. 다방 실거래는 SALE·LEASE·MONTHLY 셋뿐이다 (2026-10-25 실측: 단지 10곳 567건)."""
    return [note('제외', f'거래 유형을 읽지 못한 실거래 {count}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}')] if count else []


def _real_price(row: DabangRealPriceHistoryModel, *, area_kind: AreaKind = 'none') -> DabangRealPrice | None:
    """실거래 한 줄. 거래 유형을 모르면 None (부르는 쪽이 빼고 알린다)."""
    trade_type = TRADE_BY_PRICE_TYPE.get(row.price_type or '')
    if trade_type is None:
        return None
    contract = row.contract_date
    floor = row.format_floor if row.format_floor not in (None, '', 'null') else None
    return DabangRealPrice(
        trade_type=trade_type,
        trade_date=contract_date(contract, '계약일'),
        # 지하는 음수로 온다 ('-1', 2026-10-25 실측: 망원동 다세대 매매 50건 중 6건)
        floor=normalize_floor(str(int(floor))) if floor and floor.lstrip('-').isdecimal() else floor,
        area_m2=row.size if area_kind == 'exclusive' else None,
        total_floor_area_m2=row.size if area_kind == 'total_floor' else None,
        house_type=row.building_type if area_kind == 'total_floor' else None,
        price_manwon=row.trade_price,
        deposit_manwon=row.deposit,
        rent_manwon=row.monthly_price,
        cancelled=row.is_release,
        deal_type=None if row.is_direct is None else '직거래' if row.is_direct else '중개거래',
        registered=row.is_registration,
        newly_added=row.is_new,
        area_kind=area_kind,
    )


def _month(value: str) -> str:
    return f'{value[:4]}-{value[4:]}'


def _page_size(limit: int) -> int:
    """실거래 한 쪽 크기. 모든 쪽을 같은 크기로 묻는다 (`_collect`)."""
    return min(REAL_PRICE_PAGE_LIMIT, limit)


def _collect(fetch: Callable[[int, int], _Page | None], limit: int, *, area_kind: AreaKind = 'none') -> _Collected:
    """실거래를 `limit` 줄까지 쪽마다 받는다. `fetch(page, page_size)` 는 한 쪽을 주고, 결과가 없으면 None.

    다방은 (page - 1) × limit 번째부터 준다. 쪽마다 크기를 바꾸면 앞 쪽과 겹쳐 쪽 크기를 고정하고 넘치는 건 자른다
    (2026-10-25 실측: 50건 다음 10건을 물으니 11~20번째를 다시 줬다). limit 은 받은 줄 수로 센다. 거래 유형을 읽지 못해
    뺀 줄만큼 다음 쪽을 더 받지 않는다. 빈 쪽이 오면 서버 hasMore 가 true 여도 더 없다고 보고 멈춘다 (`more_after`).
    """
    prices: list[DabangRealPrice] = []
    total: int | None = None
    has_more = False
    received = unknown = dropped = 0
    page_size = _page_size(limit)
    for page in range(1, REAL_PRICE_MAX_PAGES + 1):
        fetched = fetch(page, page_size)
        if fetched is None:
            break
        total = fetched.total if total is None else total
        dropped += fetched.dropped
        page_rows = fetched.histories[:limit - received]
        received += len(page_rows)
        rows = [_real_price(row, area_kind=area_kind) for row in page_rows]
        prices += [price for price in rows if price is not None]
        unknown += rows.count(None)
        # 빈 항목만 온 쪽은 빈 쪽이 아니다 (빈 항목은 뺀 칸이라 limit 으로 세지 않아 다음 쪽 번호는 어긋나지 않는다)
        slots = len(fetched.histories) + fetched.dropped
        has_more = more_after(fetched.has_more, slots, cut=len(fetched.histories) - len(page_rows))
        if not fetched.has_more or not slots or received >= limit:
            break
    return _Collected(prices, total, has_more, unknown, dropped)


def get_real_prices(
    client: DabangClient,
    complex_id: str,
    *,
    space_seq: int | None,
    trade: RealPriceTrade,
    years: int,
    limit: int,
) -> DabangRealPriceResult:
    """단지 평형 하나의 실거래 (최근 계약 순). 평형을 안 주면 다방 대표 평형으로 찾는다 (요청 +1).

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, space_notes = primary_space(client, complex_id, verb='찾았습니다')
        notes += space_notes
    from_month, to_month = period_months(years)

    def fetch(page: int, page_size: int) -> _Page | None:
        result = fetch_complex_space(
            lambda: client.run_request_real_price_complex_histories_v5(DabangRealPriceComplexHistoriesV5RequestParameterModel(
                complex_id=complex_id, space_seq=space_seq, from_date=from_month, to_date=to_month,
                search_type=SEARCH_TYPE_BY_TRADE[trade], page=page, limit=page_size,
            )).result,
            complex_id,
            space_seq,
        )
        return _Page(result.list_, result.total, bool(result.has_more), result.null_items('list_')) if result else None

    collected = _collect(fetch, limit)
    if collected.dropped:
        notes.append(null_items_note('다방 실거래', collected.dropped))
    return DabangRealPriceResult(
        complex_id=complex_id,
        pyeong_id=space_seq,
        trade_tab=trade,
        start_month=_month(from_month),
        end_month=_month(to_month),
        total=collected.total,
        returned=len(collected.prices),
        has_more=collected.has_more,
        trades=collected.prices,
        url=COMPLEX_URL.format(complex_id),
        notes=notes + ([SAME_AREA_PYEONG_TRADES_NOTE] if collected.prices else []) + _unknown_trade_note(collected.unknown),
    )


def _listing_scope(scope: DabangRealPriceHouseScopeModel, building_view_type: str | None) -> tuple[str | None, list[str]]:
    """매물 실거래의 범위 이름(`basis`)과 안내. 웹 제목처럼 `historyBaseType` 을 따르고, 모르는 값이면 범위를 짐작하지 않는다.

    건물 유형(`building_view_type`)은 거래 줄의 면적 키(`area_kind`)를 정한 값과 같은 값을 받아, 안내의 건물 이름·면적 기준이
    거래 줄과 어긋나지 않게 한다. 동 이름·범위는 `scope` 에서 읽는다.
    """
    building = BUILDING_VIEW_LABELS.get(building_view_type or '', building_view_type or '')
    if building_view_type == 'MULTIPLEX':
        area = '면적(area_m2)은 전용면적입니다. 면적·층을 보고 비슷한 집만 견주세요'
    else:
        area = '면적(total_floor_area_m2)은 다방이 연면적이라 부르는 값이라 매물 전용면적과 기준이 다릅니다. 그대로 견주지 마세요'
    place = ' '.join(part for part in (scope.dong_name, building) if part)
    if scope.history_base_type == 'JIBUN':
        # 요청한 매물의 건물이라 범위가 요청과 다르지 않다 ([참고]). 같은 동 거래만 [범위] 다
        return f'이 집 ({place})' if place else '이 집', [note(
            '참고', f'이 매물과 같은 지번 건물(이 집)의 실거래입니다 (다방 매물 화면과 같은 범위). 같은 건물의 다른 집 거래도 들 수 있습니다. {area}',
        )]
    if scope.history_base_type == 'DONG':
        target = f'같은 동의 같은 건물 유형({place})' if place else '같은 동의 같은 건물 유형'
        return place or None, [note('범위', f'이 매물 건물이 아니라 {target} 실거래입니다 (다방 매물 화면과 같은 범위). {area}')]
    return None, [note(
        '참고', f'다방이 거래를 모은 범위(historyBaseType: {scope.history_base_type})를 알아보지 못했습니다. {area}. {UPDATE_MAYBE_NEEDED}',
    )]


def _init_trade(init: DabangRealPriceHouseInitResultModel) -> RealPriceTrade | None:
    """실거래 첫 화면(`house/init`)이 알려 주는 매물의 거래 유형. 모르는 searchType 이면 None."""
    return TRADE_BY_SEARCH_TYPE.get(init.search_type or '')


def _listing_not_found(listing_id: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f'다방이 이 매물의 실거래를 주지 않았습니다: {listing_id} (없는 매물이거나 단지 매물)',
        hint='단지 없는 매물(빌라·주택·원룸)의 ID 를 주세요. 오피스텔·아파트 매물은 jibsa dabang listing <ID> 결과의 '
        'complex_id 로 jibsa dabang real-price <complex_id>',
    )


def get_listing_real_prices(
    client: DabangClient,
    listing_id: str,
    *,
    trade: RealPriceTrade | None,
    years: int,
    limit: int,
) -> DabangRealPriceResult:
    """단지 없는 매물(빌라·주택·원룸)의 실거래. 다방 매물 화면처럼 이 집(같은 지번) 또는 같은 동의 같은 건물 유형 거래다.

    `trade` 를 주지 않으면 웹처럼 실거래 첫 화면(`house/init`)을 먼저 받아 매물의 거래 유형을 따른다 (매매 매물은 매매, 월세·
    전세 매물은 전월세, 요청 +1). `trade` 를 주면 첫 화면을 받지 않는다. 범위(이 집 / 같은 동)·동·건물 유형은 받은 거래 목록
    (`house/history`)의 첫 쪽이 알려 주고, 범위는 거래 유형마다 달라 그 값을 쓴다. 목록이 범위를 주지 않을 때만 첫 화면으로
    매물을 확인한다 (없는 매물·단지 매물은 둘 다 빈 결과).

    Raises:
        JibsaError: 매물이 없거나 단지 매물일 때 (NOT_FOUND), `trade` 없이 부르는데 다방이 매물의 거래 유형(searchType)을
            알려 주지 않을 때 (UPSTREAM_ERROR).
    """
    from_month, to_month = period_months(years)

    def house_init() -> DabangRealPriceHouseInitResultModel | None:
        return client.run_request_real_price_house_init_v5(DabangRealPriceHouseInitV5RequestParameterModel(
            room_id=listing_id, from_date=from_month, to_date=to_month,
        )).result

    # 없는 매물·단지 매물(오피스텔·아파트)에는 에러 대신 거래 유형·동·범위가 빈 결과를 준다. 거래가 0건인 매물도 동·범위는 온다
    # (2026-10-25 실측: 없는 ID·강남역 오피스텔 매물은 dongName·historyBaseType null, 도곡동 단독 1년 매매 0건은 '도곡동'·'DONG'.
    # 2026-11-13 실측: 없는 ID 의 house/init 도 searchType·dongName·historyBaseType 이 모두 null. 2026-11-14 실측: 매물 7곳 ×
    # 매매·전월세의 house/history 는 0건인 기간에도 dongName·historyBaseType·buildingViewType 을 줬고 init 과 같았다)
    notes: list[str] = []
    init: DabangRealPriceHouseInitResultModel | None = None
    init_trade: RealPriceTrade | None = None
    if trade is None:
        init = house_init()
        if init is None or not init.is_known_listing:
            raise _listing_not_found(listing_id)
        init_trade = _init_trade(init)
        if init_trade is None:
            raise JibsaError(
                code='UPSTREAM_ERROR',
                message=f'다방이 이 매물의 실거래 거래 유형을 알려 주지 않았습니다 (searchType: {init.search_type})',
                hint=f'--trade 매매 또는 --trade 전월세 를 주세요. {UPDATE_MAYBE_NEEDED}',
            )
        trade = init_trade
        notes.append(note('거래', f'--trade 를 주지 않아 다방 매물 화면처럼 매물의 거래 유형대로 {trade} 실거래를 찾았습니다'))
    search_type = SEARCH_TYPE_BY_TRADE[trade]

    def history(page: int, page_size: int) -> DabangRealPriceHouseHistoryResultModel | None:
        # 매물 ID 가 쿼리로 가서 없는 매물에도 에러가 아니라 빈 결과가 온다. 그래서 4xx·403 은 다방 주소가 바뀐 것으로 둔다
        return client.run_request_real_price_house_history_v5(DabangRealPriceHouseHistoryV5RequestParameterModel(
            room_id=listing_id, from_date=from_month, to_date=to_month,
            search_type=search_type, page=page, limit=page_size,
        )).result

    first = history(1, _page_size(limit))
    if init is None and (first is None or first.history_base_type is None):
        init = house_init()
        init_trade = _init_trade(init) if init is not None else None
    known = [model for model in (first, init) if model is not None and model.is_known_listing]
    if not known:
        raise _listing_not_found(listing_id)
    # 범위는 거래 유형마다 다르다 (2026-11-13 리뷰·실측: 역삼동 월세 다세대 6ac9b09a…는 전월세 JIBUN 2건, 매매 DONG 585건).
    # 받은 목록(`history`)이 알려 주는 범위를 쓰고, `init` 의 범위는 매물의 거래 유형 것이라 그 유형을 찾을 때만 쓴다. 둘 다
    # 아니면 범위를 모른다고 알린다 (`_listing_scope`)
    scope: DabangRealPriceHouseScopeModel
    if first is not None and first.history_base_type is not None:
        scope = first
    elif init is not None and init.history_base_type is not None and init_trade == trade:
        scope = init
    else:
        scope = known[0].model_copy(update={'history_base_type': None})
    # 건물 유형은 거래 줄의 면적 키와 안내의 건물 이름·면적 기준이 함께 쓴다 (목록 첫 쪽이 비어 있으면 첫 화면 값)
    building = next((model.building_view_type for model in known if model.building_view_type), None)
    area_kind: AreaKind = 'exclusive' if building == 'MULTIPLEX' else 'total_floor'

    def fetch(page: int, page_size: int) -> _Page | None:
        result = first if page == 1 else history(page, page_size)
        return None if result is None else _Page(result.histories, result.total, bool(result.has_more), result.null_items('histories'))

    collected = _collect(fetch, limit, area_kind=area_kind)
    basis, scope_notes = _listing_scope(scope, building)
    notes += scope_notes + _unknown_trade_note(collected.unknown)
    if collected.dropped:
        notes.append(null_items_note('다방 실거래', collected.dropped))
    return DabangRealPriceResult(
        listing_id=listing_id,
        trade_tab=trade,
        start_month=_month(from_month),
        end_month=_month(to_month),
        basis=basis,
        total=collected.total,
        returned=len(collected.prices),
        has_more=collected.has_more,
        trades=collected.prices,
        url=LISTING_URL.format(listing_id),
        notes=notes,
    )
