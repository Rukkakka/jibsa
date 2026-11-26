"""동·구의 최근 실거래 (region-trades): 직방 웹 지역 화면의 '실거래' 패널과 더보기 화면의 등록일 기준 목록."""

from pydantic import Field

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
    LOCAL_DONG_DESCRIPTION,
    LocalLevel,
    LocalTrade,
    ZigbangLocalModel,
    ZigbangLocalRegion,
    dong_not_applicable,
    local_region_of,
    local_sort_of,
    resolve_local_area,
)

from typing import (
    Annotated,
    Literal,
)


LocalTradePeriod = Literal['오늘', '어제', '7일', '15일', '30일']
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


class ZigbangRegionTrade(ZigbangLocalModel):
    """지역 최근 실거래 한 줄. 거래 유형에 해당하지 않는 칸은 키가 없다 (매매 가격·비교는 매매만, 보증금은 전세·월세, 월세료는 월세만).

    웹은 정렬마다 비교 한 가지(직전 거래·직방시세·공시가격·분양가·전세가)만 그리지만, 여기서는 같은 응답의 비교 칸을 모두 낸다. 금액은 만원이다.
    """

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    area_type: Annotated[
        str | None,
        Field(description="평형 이름 (웹 '{평형 이름}㎡', 예: 110D). 직방이 주지 않으면 null")
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내). 목록은 계약일 순이 아니라 등록일 기준이다')
    ]
    presale: Annotated[
        str | None,
        Field(description='분양권·입주권 거래 (해당할 때만 키가 있다. real-price 의 presale 과 같다)')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='매매가 (만원). 매매만 있고 전세·월세는 키가 없다')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='보증금·전세금 (만원). 전세·월세만 있고 매매는 키가 없다')
    ]
    rent_manwon: Annotated[
        int | float | None,
        Field(description='월세 (만원). 월세만 있고 매매·전세는 키가 없다')
    ]
    prev_trade_diff_manwon: Annotated[
        int | float | None,
        Field(
            description=(
                "직전 거래 대비 차액 (만원, 매매·전세). 직방이 칸을 주지 않으면 null (웹 '직전거래 없음'), 0 은 웹 '차이 없음'. "
                '입주권 줄은 웹이 그리지 않아 키가 없고, 입주 전 계약 전세 줄도 웹이 그리지 않아 null. 월세는 키가 없다'
            )
        )
    ]
    prev_trade_diff_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, prev_trade_diff_manwon 과 같은 규칙)')
    ]
    estimated_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="직방시세 대비 차액 (만원, 매매만). 분양권·입주권이거나 직방시세가 없으면(isNoMarketPriceGap) 웹이 '직방시세 없음' 이라 null. 직방시세가 있는데 0 이면 진짜 0")
    ]
    estimated_price_diff_percent: Annotated[
        int | float | None,
        Field(description='직방시세 대비 변동률 (%, estimated_price_diff_manwon 과 같은 규칙)')
    ]
    public_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="공시가격 대비 차액 (만원, 매매만). 공시가격이 없으면(isNoPublicPriceGap) 웹이 '공시가격 업데이트 예정' 이라 null. 공시가격이 있는데 0 이면 진짜 0")
    ]
    public_price_diff_percent: Annotated[
        int | float | None,
        Field(description='공시가격 대비 변동률 (%, public_price_diff_manwon 과 같은 규칙)')
    ]
    presale_price_diff_manwon: Annotated[
        int | float | None,
        Field(description='분양가 대비 차액 (만원, 분양권·입주권 매매 줄에만 키가 있다). 직방이 분양가 대비 값을 주지 않으면(isNoOfferPriceGap) null')
    ]
    presale_price_diff_percent: Annotated[
        int | float | None,
        Field(description='분양가 대비 변동률 (%, presale_price_diff_manwon 과 같은 규칙)')
    ]
    jeonse_comparison_diff_manwon: Annotated[
        int | float | None,
        Field(description="전세가 비교 차액 (만원, 전세만). 웹 '전세가 비교': 갱신 거래(renewal)는 이전 전세가 대비, 아니면 2년 전 평균 전세가 대비. 입주 전 계약 거래(pre_move_in_contract)는 웹이 차액을 그리지 않아 null")
    ]
    jeonse_comparison_diff_percent: Annotated[
        int | float | None,
        Field(description='전세가 비교 변동률 (%, jeonse_comparison_diff_manwon 과 같은 규칙)')
    ]
    pre_move_in_contract: Annotated[
        bool | None,
        Field(description="입주 전 계약 거래 (웹 '입주 전 계약 거래', 전세만). 직방이 칸을 주지 않으면 false")
    ]
    new_high: Annotated[
        bool | None,
        Field(description='신고가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    new_low: Annotated[
        bool | None,
        Field(description='신저가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    renewal: Annotated[
        bool | None,
        Field(description="갱신 계약 (웹 '계약갱신' 배지, 전세만. 매매에는 웹이 그리지 않아 키가 없고, 월세는 직방이 값을 줘도 웹이 그리지 않아 키가 없다). 직방이 칸을 주지 않으면 false")
    ]


class ZigbangRegionTradesResult(ZigbangLocalModel):
    """동·구의 최근 실거래 (직방 웹 지역 화면 '실거래', 등록일 기준). 기간이 오늘이 아니면 `updated_today` 키가 없다."""

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    period: Annotated[
        LocalTradePeriod,
        Field(description='등록 기간. 오늘·어제·7일(최근 일주일)·15일·30일')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 최신 등록순)')
    ]
    registered_period: Annotated[
        str | None,
        Field(
            description=(
                "직방이 준 기간과 등록 건수 문구 (예: '10. 23 ~ 11. 22 등록 135건'). 직방이 주지 않으면 null. "
                '기간이 오늘이고 직방이 아직 반영 전(updated_today false)이면 웹처럼 숨겨 null'
            )
        )
    ]
    updated_today: Annotated[
        bool | None,
        Field(
            description=(
                "직방이 오늘 등록된 실거래를 반영했는지 (직방은 매일 낮 12시에 반영한다. false 면 직방 웹은 '오늘 12시에 실거래가 업데이트 될 예정입니다' 를 보여 준다). "
                '--period 오늘 일 때만 있고 다른 기간은 키가 없다. 직방이 주지 않으면 null'
            )
        )
    ]
    total: Annotated[
        int | None,
        Field(description='기간 안 등록된 실거래 전체 건수 (limit 적용 전). 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 실거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='--limit 을 늘리면 더 받을 수 있는 실거래가 남았는지 (직방이 --limit 보다 적게 줘 더 받을 수 없으면 false. 이어 받기는 없다)')
    ]
    trades: Annotated[
        list[ZigbangRegionTrade],
        Field(description='최근 실거래 (정렬 순서 그대로)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 받았다는 안내·실거래가 없다는 안내·아직 반영 전이라는 안내·빈 항목을 빼고 읽었다는 안내. CLI 가 결과 위에 붙인다')
    ] = []


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
