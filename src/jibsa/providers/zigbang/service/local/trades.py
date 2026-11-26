"""동·구의 최근 실거래 (region-trades): 직방 웹 지역 화면의 '실거래' 패널과 더보기 화면의 등록일 기준 목록."""

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    more_hint,
    note,
    null_items_note,
    read_date,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.local.trades import (
    ZigbangLocalsTradingHistoriesRequestParameterModel,
    ZigbangLocalTradeDealType,
    ZigbangLocalTradePeriodType,
)
from jibsa.providers.zigbang.api.response.local.trades import ZigbangLocalTradeModel
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    UPSTREAM_RETRY_HINT,
    apt_complex_id,
    text_or_none,
)
from jibsa.providers.zigbang.service.local.base import (
    dong_not_applicable,
    local_region_of,
    local_sort_of,
    resolve_local_area,
)
from jibsa.providers.zigbang.service.local.models import (
    LocalLevel,
    LocalTrade,
    LocalTradePeriod,
    ZigbangRegionTrade,
    ZigbangRegionTradesResult,
)


TRADE_PERIODS: tuple[LocalTradePeriod, ...] = ('오늘', '어제', '7일', '15일', '30일')
DEFAULT_TRADE_LIMIT: int = 20
# 웹 기간 탭 (2026-11-19 번들 `h`: 오늘·어제·최근 일주일·최근 15일·최근 30일) → 서버 periodType
PERIOD_TYPE_BY_LABEL: dict[LocalTradePeriod, ZigbangLocalTradePeriodType] = {
    '오늘': 'today',
    '어제': 'yesterday',
    '7일': 'last_7_days',
    '15일': 'last_15_days',
    '30일': 'last_30_days',
}
DEAL_TYPE_BY_TRADE: dict[LocalTrade, ZigbangLocalTradeDealType] = {'매매': 'sales', '전세': 'charter', '월세': 'rent'}
# 웹 정렬 이름 → 서버 sortSpec (2026-11-19 번들 `D`). 첫 항목이 웹 기본이다. 거래 유형마다 정렬이 다르다
SORT_SPEC_BY_TRADE: dict[LocalTrade, dict[str, str]] = {
    '매매': {
        '최신 등록순': 'sales_latest_registration',
        '가격 낮은순': 'sales_lowest_price',
        '가격 높은순': 'sales_highest_price',
        '시세 비교순': 'sales_market_price_comparison',
        '공시가격 대비 낮은순': 'sales_lower_than_public_price',
    },
    '전세': {
        '최신 등록순': 'charters_latest_registration',
        '가격 낮은순': 'charters_lowest_price',
        '가격 높은순': 'charters_highest_price',
        '전세가 비교순': 'charters_lease_price',
    },
    '월세': {
        '최신 등록순': 'rents_latest_registration',
        '월세 높은순': 'rents_highest_monthly_rent_price',
        '보증금 높은순': 'rents_highest_deposit',
    },
}
# 거래 유형에 해당하지 않아 출력에서 키를 뺄 칸. 월세는 웹 줄이 신고가·신저가·갱신·비교를 그리지 않아 뺀다 (응답에 와도 낸 칸이 없다)
SALE_ONLY_FIELDS: frozenset[str] = frozenset({
    'price_manwon',
    'estimated_price_diff_manwon',
    'estimated_price_diff_percent',
    'public_price_diff_manwon',
    'public_price_diff_percent',
    'presale_price_diff_manwon',
    'presale_price_diff_percent',
})
CHARTER_ONLY_FIELDS: frozenset[str] = frozenset({
    'jeonse_comparison_diff_manwon',
    'jeonse_comparison_diff_percent',
    'pre_move_in_contract',
    'renewal',
})
PREV_DIFF_FIELDS: frozenset[str] = frozenset({'prev_trade_diff_manwon', 'prev_trade_diff_percent'})
OFFER_DIFF_FIELDS: frozenset[str] = frozenset({'presale_price_diff_manwon', 'presale_price_diff_percent'})
NOT_APPLICABLE_BY_TRADE: dict[LocalTrade, frozenset[str]] = {
    '매매': frozenset({'deposit_manwon', 'rent_manwon'}) | CHARTER_ONLY_FIELDS,
    '전세': frozenset({'rent_manwon'}) | SALE_ONLY_FIELDS,
    '월세': frozenset({'new_high', 'new_low'}) | SALE_ONLY_FIELDS | CHARTER_ONLY_FIELDS | PREV_DIFF_FIELDS,
}
PRESALE_RIGHT: str = '입주권'


def _trade_of(item: ZigbangLocalTradeModel, trade: LocalTrade, level: LocalLevel) -> ZigbangRegionTrade:
    """실거래 한 건을 줄로 바꾼다. 칸이 거래 유형·분양권·입주권·조회 단위에 해당하지 않으면 키를 뺀다 (`not_applicable`).

    비교 칸은 웹이 '없음' 으로 그리는 경우(분양권·입주권의 직방시세 대비, `isNo*Gap` 이 참)에 null 이고, 거짓인 0 은 진짜 0 이다.
    """
    presale = text_or_none(item.offer_type)
    pre_move_in = bool(item.is_pre_movein_charter_contract)
    absent = set(NOT_APPLICABLE_BY_TRADE[trade]) | dong_not_applicable(level)
    if presale is None:
        absent |= {'presale'} | OFFER_DIFF_FIELDS
    if presale == PRESALE_RIGHT:
        # 웹은 입주권 줄에 직전 거래 대비를 그리지 않는다 (번들 `offerType!=="입주권"`)
        absent |= PREV_DIFF_FIELDS
    # 입주 전 계약 전세는 웹이 직전 거래·전세가 비교 차액을 그리지 않는다
    hide_prev = trade == '전세' and pre_move_in
    return ZigbangRegionTrade(
        complex_id=None if item.area_danji_id is None else apt_complex_id(item.area_danji_id),
        complex_name=text_or_none(item.area_danji_name),
        dong=text_or_none(item.local),
        area_type=text_or_none(item.room_type),
        trade_date=read_date(item.rt_deal_date, '계약일'),
        presale=presale,
        price_manwon=item.rt_price,
        deposit_manwon=item.rt_price,
        rent_manwon=item.monthly_rent_price,
        prev_trade_diff_manwon=None if hide_prev else item.prev_rt_price_gap,
        prev_trade_diff_percent=None if hide_prev else item.prev_rt_price_gap_rate,
        estimated_price_diff_manwon=None if presale is not None or item.is_no_market_price_gap is True else item.market_price_gap,
        estimated_price_diff_percent=None if presale is not None or item.is_no_market_price_gap is True else item.market_price_gap_rate,
        public_price_diff_manwon=None if item.is_no_public_price_gap is True else item.public_price_gap,
        public_price_diff_percent=None if item.is_no_public_price_gap is True else item.public_price_gap_rate,
        presale_price_diff_manwon=None if item.is_no_offer_price_gap is True else item.offer_price_gap,
        presale_price_diff_percent=None if item.is_no_offer_price_gap is True else item.offer_price_gap_rate,
        jeonse_comparison_diff_manwon=None if pre_move_in else item.charter_price_gap,
        jeonse_comparison_diff_percent=None if pre_move_in else item.charter_price_gap_rate,
        pre_move_in_contract=pre_move_in,
        new_high=bool(item.is_new_highest),
        new_low=bool(item.is_new_lowest),
        renewal=bool(item.is_contract_renewal),
        not_applicable=frozenset(absent),
    )


def get_region_trades(
    client: ZigbangClient,
    query: str,
    *,
    trade: LocalTrade = '매매',
    period: LocalTradePeriod = '오늘',
    sort: str | None = None,
    limit: int = DEFAULT_TRADE_LIMIT,
) -> ZigbangRegionTradesResult:
    """동·구의 최근 실거래를 직방 웹 지역 화면 '실거래' 와 같은 요청(등록일 기준, 거래 유형·기간·정렬)으로 `limit` 건 받는다 (요청 2회: 지역 검색 + 실거래 1쪽).

    웹은 10건씩 끝까지 넘겨 보지만 여기서는 쪽 크기를 `limit` 으로 키워 한 번에 받는다 (한 번에 더 받기. 서버는 limit=1000 에도 전부 줬다).
    서버가 정렬한 순서·수 그대로이고 다시 거르지 않는다. 정렬 이름은 지역을 찾기 전에 검사한다.
    기간이 오늘일 때 응답의 `isUpdated` 가 false 면(직방은 매일 낮 12시에 그날 실거래를 반영한다) 웹처럼 기간 문구(`registered_period`)를 숨겨 null 로 두고
    '없습니다' 대신 아직 반영 전이라고 알린다 (웹 더보기 화면·지역 화면 패널 번들 청크 6096·5314 가 `isUpdated===false` 일 때 문구를 숨기고 '오늘 12시에 실거래가 업데이트 될 예정입니다' 를 보여 준다).
    `isUpdated` 가 없으면 모름이라 갱신 전으로 보지 않는다.

    Raises:
        JibsaError: 그 거래에 없는 정렬일 때·시·도 이름일 때 (INVALID_ARGUMENT), 직방이 실거래 목록을 주지 않았을 때 (UPSTREAM_ERROR).
        RegionNotFoundError: 동·구를 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 동·구가 여럿이거나 구가 있는 시·'○가' 로만 나뉜 동일 때.
    """
    sort_label, sort_spec = local_sort_of(trade, sort, SORT_SPEC_BY_TRADE[trade])
    area = resolve_local_area(client, query)
    response = client.run_request_locals_trading_histories(ZigbangLocalsTradingHistoriesRequestParameterModel(
        page=1,
        local_code=area.code,
        deal_type=DEAL_TYPE_BY_TRADE[trade],
        sort_spec=sort_spec,
        period_type=PERIOD_TYPE_BY_LABEL[period],
        limit=limit,
    ))
    data = response.data
    items = data.trades if data is not None else None
    if data is None or items is None:
        # 목록이 없으면 '실거래가 없습니다' 와 가려지지 않으므로 결과를 만들지 않는다 (빈 기간은 trades 가 [] 로 온다)
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message='직방이 실거래 목록을 주지 않았습니다',
            hint=UPSTREAM_RETRY_HINT,
        )
    notes = list(area.notes)
    trades = [_trade_of(item, trade, area.level) for item in items]
    # 빈 항목도 서버가 센 한 자리라 받은 수에 더한다. 목록을 그대로 보여 주지만 total 과 견주는 has_more 가 이 수를 쓴다
    dropped = data.null_items('trades')
    received = len(trades) + dropped
    total = data.total_count
    # 갱신 여부는 오늘 기간에만 웹이 보여 준다. null 은 모름이라 갱신 전으로 보지 않는다
    not_updated = period == '오늘' and data.is_updated is False
    if dropped:
        notes.append(null_items_note('직방 지역 실거래', dropped))
    # 서버는 요청한 수까지 다 주므로 받은 수가 요청한 수에 닿았을 때만 더 있을 수 있다
    has_more = received >= limit and (total is None or total > received)
    if not_updated:
        notes.append(note(
            '참고',
            "직방은 매일 낮 12시에 그날 등록된 실거래를 반영하는데 아직 반영 전입니다 (직방 웹: '오늘 12시에 실거래가 업데이트 될 예정입니다'). "
            '어제 등록분은 --period 어제 로 보세요',
        ))
    elif total == 0 and not trades:
        notes.append(note(
            '참고',
            '이 기간에 등록된 실거래가 없습니다. --period 30일 처럼 기간을 넓혀 보세요' if period != '30일'
            else '최근 30일 동안 등록된 실거래가 없습니다',
        ))
    if total is not None and total > received and received < limit:
        notes.append(note('참고', f'직방이 실거래 수를 {total}건이라 주었지만 목록은 {received}건만 와서 더 받을 수 없습니다'))
    if has_more:
        # 하루 단위 기간(오늘·어제)은 더 좁힐 수 없다
        narrow = None if period in ('오늘', '어제') else '--period 기간'
        head = (
            # 보여 준 수(returned)로 센다 (region-ranking 과 같다). 뺀 빈 항목은 [제외] 가 알린다
            f'조건에 맞는 실거래 {total}건 중 {len(trades)}건입니다' if total is not None
            else f'실거래 {len(trades)}건을 받았습니다. 직방이 전체 건수를 주지 않아 더 있을 수 있습니다'
        )
        notes.append(note('일부', f'{head}. {more_hint(limit, MAX_LIST_LIMIT, narrow)}. 다른 쪽 거래는 --sort 로 순서를 바꿔 보세요'))
    return ZigbangRegionTradesResult(
        region=local_region_of(area),
        trade_type=trade,
        period=period,
        sort=sort_label,
        registered_period=None if not_updated else text_or_none(data.registration_info),
        updated_today=data.is_updated,
        total=total,
        returned=len(trades),
        has_more=has_more,
        trades=trades,
        notes=notes,
        not_applicable=frozenset() if period == '오늘' else frozenset({'updated_today'}),
    )
