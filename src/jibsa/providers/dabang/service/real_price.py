"""실거래가 (real-price), 시세 흐름 (price-trend), 평형대 평당가와 주변 단지 비교 (nearby-complexes)."""
from collections.abc import Callable
from datetime import datetime

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    KST,
    NOT_APPLICABLE_PRICE_FIELDS,
    SAME_AREA_PYEONG_TRADES_NOTE,
    UPDATE_MAYBE_NEEDED,
    AmountRange,
    AmountSet,
    TradeType,
    normalize_address,
    normalize_floor,
    note,
    null_items_note,
    read_month,
    with_floor_number,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.real_price import (
    REAL_PRICE_PAGE_LIMIT,
    DabangRealPriceComplexChartsV5RequestParameterModel,
    DabangRealPriceComplexHistoriesV5RequestParameterModel,
    DabangRealPriceComplexPricePerPyV5RequestParameterModel,
    DabangRealPriceHouseHistoryV5RequestParameterModel,
    DabangRealPriceHouseInitV5RequestParameterModel,
    DabangRealPriceSearchType,
)
from jibsa.providers.dabang.api.response.real_price import (
    DabangChartSeriesModel,
    DabangHighLowModel,
    DabangNearComplexModel,
    DabangRealPriceHistoryModel,
    DabangRealPriceHouseHistoryResultModel,
    DabangRealPriceHouseInitResultModel,
    DabangRealPriceHouseScopeModel,
)
from jibsa.providers.dabang.service.common import (
    COMPLEX_KIND_BY_TYPE,
    DabangAreaPrice,
    area_price,
    building_years,
    complex_not_found,
    complex_url,
    contract_date,
    error_message,
    fetch_complex,
    first_space_notes,
    listing_url,
    more_after,
    primary_space_of,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
    TypeVar,
)


T = TypeVar('T')

RealPriceTrade = Literal['매매', '전월세']
SEARCH_TYPE_BY_TRADE: dict[RealPriceTrade, DabangRealPriceSearchType] = {'매매': 'SALE', '전월세': 'LEASE'}
TRADE_BY_SEARCH_TYPE: dict[str, RealPriceTrade] = {search_type: trade for trade, search_type in SEARCH_TYPE_BY_TRADE.items()}
# 매물 실거래 줄의 면적 칸. 단지 실거래는 평형으로 고르므로 면적이 없다(none). 매물 실거래는 웹처럼 다세대·연립(MULTIPLEX)이면
# 전용면적·층, 그 밖(DETACHED 단독·다가구)이면 연면적·주택유형(매매만)이다 (room 청크 `ii` 가 MULTIPLEX 만 `Kr`, 나머지는 `ei`)
AreaKind = Literal['none', 'exclusive', 'total_floor']
TRADE_BY_PRICE_TYPE: dict[str, TradeType] = {'SALE': '매매', 'LEASE': '전세', 'MONTHLY': '월세'}
REAL_PRICE_MAX_YEARS: int = 3
REAL_PRICE_MAX_PAGES: int = 4
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_LIMIT * REAL_PRICE_MAX_PAGES


def period_months(years: int, today: datetime | None = None) -> tuple[str, str]:
    """`years` 년 기간의 (시작 달, 끝 달) `YYYYMM`. 화면처럼 이번 달을 끝으로 `12 × years` 달 (3년 = 36달)."""
    now = today or datetime.now(KST)
    end = now.year * 12 + now.month - 1
    start = end - 12 * years + 1
    return f'{start // 12:04d}{start % 12 + 1:02d}', f'{now.year:04d}{now.month:02d}'


class DabangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 금액은 키가 없다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형 (매매·전세·월세)')
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 ('5', '지하1'). 모르면 null. 바로 뒤 floor_number 는 몇 층인지 아는 층의 숫자 (지하는 음수, 모르면 null)")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, --listing 의 다세대·연립 거래만. 단지는 평형으로 고른다)')
    ] = None
    total_floor_area_m2: Annotated[
        float | None,
        Field(description='연면적 (㎡, 다방 화면의 이름. --listing 의 단독·다가구 거래만. 매물 전용면적과 기준이 달라 그대로 견주지 않는다)')
    ] = None
    house_type: Annotated[
        str | None,
        Field(description="주택 유형 ('단독', '다가구', --listing 의 단독·다가구 매매만)")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금·전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제된 거래')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description="거래 방식 ('직거래'·'중개거래'). 다방이 직거래 여부를 주지 않으면 null")
    ] = None
    # 리뷰 오탐 (2026-11-13): 단독·다가구 줄에 isRegistration 이 없어 키를 빼야 한다는 지적. 웹 단독·다가구 표(room 청크 `ei`)도
    # 다세대 표처럼 `e.isRegistration` 이 참이면 등기 표시를 그린다. 다방이 이 줄에 값을 주지 않을 뿐이라 해당 없음이 아니라 모름(null)이다
    registered: Annotated[
        bool | None,
        Field(description='등기된 거래 (다방 화면의 등기 표시). 다방이 주지 않으면 null (단독·다가구 거래)')
    ] = None
    newly_added: Annotated[
        bool | None,
        Field(description='다방이 새 거래로 표시한 거래 (화면의 새 거래 표시)')
    ] = None
    area_kind: Annotated[
        AreaKind,
        Field(exclude=True, description='낼 면적 키 (단지 실거래는 없음)')
    ] = 'none'

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        dropped = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.area_kind != 'exclusive':
            dropped.add('area_m2')
        if self.area_kind != 'total_floor':
            dropped |= {'total_floor_area_m2', 'house_type'}
        else:
            # 웹 단독·다가구 표에는 층 칸이 없고(`ei`) 원본 층도 'null' 글자다. 주택유형은 매매 표에만 있다
            dropped.add('floor')
            if self.trade_type != '매매':
                dropped.add('house_type')
        for field in dropped:
            data.pop(field, None)
        return with_floor_number(data)


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


class DabangRealPriceResult(BaseModel):
    """실거래 내역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 실거래만)')
    ] = None
    listing_id: Annotated[
        str | None,
        Field(description='매물 ID (--listing 만)')
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID (단지 실거래만)')
    ] = None
    trade_tab: Annotated[
        RealPriceTrade,
        Field(description='매매 또는 전월세')
    ]
    start_month: Annotated[
        str,
        Field(description='조회 시작 달 (YYYY-MM)')
    ]
    end_month: Annotated[
        str,
        Field(description='조회 끝 달 (YYYY-MM)')
    ]
    basis: Annotated[
        str | None,
        Field(description=(
            "거래를 모은 범위 (--listing 만): '이 집 (망원동 다세대·연립)' 은 이 매물과 같은 지번 건물, '역삼동 단독·다가구' 는 "
            '그 동의 같은 건물 유형. 다방이 범위를 알려 주지 않으면 null'
        ))
    ] = None
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='기간 안에 더 오래된 거래가 더 있는지')
    ]
    trades: Annotated[
        list[DabangRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    url: Annotated[
        str,
        Field(description='단지·매물 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평형·범위 안내')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('complex_id', 'listing_id', 'pyeong_id'):
            if data.get(key) is None:
                data.pop(key, None)
        # 기준 범위는 매물 실거래(--listing)에만 해당한다. 그때 비면 모름(null)으로 남긴다
        if self.listing_id is None:
            data.pop('basis', None)
        return data


def _month(value: str) -> str:
    return f'{value[:4]}-{value[4:]}'


BUILDING_VIEW_LABELS: dict[str, str] = {'DETACHED': '단독·다가구', 'MULTIPLEX': '다세대·연립', 'APARTMENT': '아파트', 'OFFICETEL': '오피스텔'}


def _fetch_complex_space(fetch: Callable[[], T], complex_id: str, space_seq: int) -> T:
    """단지 평형 요청 하나. 없는 단지·평형이라는 다방 오류를 NOT_FOUND·INVALID_ARGUMENT 로 바꾼다.

    Raises:
        JibsaError: 없는 단지·평형일 때. 다른 HTTP 오류는 그대로 올린다.
    """
    try:
        return fetch()
    except HTTPStatusError as exc:
        # 다방은 없는 단지·평형에 400 과 사유를 준다 (2026-10-25 실측: 평형 1 → '존재하지 않는 평형 정보입니다.',
        # 없는 단지 → histories '존재하지 않는 단지입니다.'·charts '존재하지 않는 단지 정보입니다.'). 단지 ID 가 쿼리로 가서 403 은
        # 없는 단지가 아니라 다방 주소가 바뀐 것이다 (`is_missing_id`).
        if exc.response.status_code == 400:
            message = error_message(exc) or ''
            if '평형' in message:
                raise JibsaError(
                    code='INVALID_ARGUMENT',
                    message=f'이 단지에 없는 평형 번호입니다: {space_seq}',
                    hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 주세요',
                ) from None
            if '단지' in message:
                raise complex_not_found(complex_id) from None
        raise


def primary_space(client: DabangClient, complex_id: str, *, verb: str) -> tuple[int, list[str]]:
    """`--pyeong` 을 안 준 조회의 (평형 번호, 대표 평형으로 조회했다는 안내들) (단지 상세 1회).

    다방이 대표를 주지 않으면(없거나 0) 웹처럼 첫 평형을 고른다. 그때 평형 목록에서 빈 항목을 뺐으면 그 안내가 더 붙는다.

    Args:
        verb: 안내 끝말 ('찾았습니다'·'비교했습니다').

    Raises:
        JibsaError: 단지가 없거나 평형이 없을 때 (NOT_FOUND).
    """
    result = fetch_complex(client, complex_id)
    chosen = primary_space_of(result)
    if chosen is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방 단지의 평형을 찾지 못했습니다: {complex_id}',
            hint='jibsa dabang complex <단지ID> 결과의 pyeongs[].pyeong_id 를 --pyeong 으로 주세요',
        )
    seq, from_dabang = chosen
    name = next((space.pyeong_type for space in result.spaces or [] if space.space_seq == seq), None)
    return seq, [primary_space_note(name or str(seq), seq, verb=verb, from_dabang=from_dabang), *first_space_notes(result)]


def primary_space_note(name: str, space_seq: int, *, verb: str, from_dabang: bool) -> str:
    """`--pyeong` 을 안 줘 대표 평형으로 조회했다는 안내 (`verb`: '찾았습니다'·'비교했습니다').

    Args:
        from_dabang: 다방이 대표 평형을 줬는지. 아니면 다방 웹처럼 첫 평형을 고른 것이라 그렇게 알린다.
    """
    if not from_dabang:
        return note(
            '참고',
            f'--pyeong 을 주지 않았고 다방이 대표 평형을 주지 않아 다방 웹처럼 첫 평형({name}, pyeong_id {space_seq})으로 {verb}. '
            '다른 평형은 complex 결과의 pyeongs 에서 고르세요',
        )
    return note(
        '참고',
        f'--pyeong 을 주지 않아 다방 대표 평형({name}, pyeong_id {space_seq})으로 {verb}. '
        '다른 평형은 complex 결과의 pyeongs 에서 고르세요',
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
        result = _fetch_complex_space(
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
        url=complex_url(complex_id),
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
        url=listing_url(listing_id),
        notes=notes,
    )


class DabangTrendMonth(BaseModel):
    """시세 흐름의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='달 (YYYY-MM). 읽지 못하면 null ([참고] 안내)')
    ] = None
    trade_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 평균 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 늘 두 개. 거래 없는 달은 다방이 앞 달 평균을 "
            '잇고, 이을 평균도 없으면 그 거래가 null'
        ))
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 거래 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (모르면 null)")
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='그 달 전세가율 (%, 다방 갭 그래프). 매매·전세 평균이 없으면 null')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='그 달 매매 평균 − 전세 평균 (만원, 다방 갭 그래프). 없으면 null')
    ] = None


class DabangTradeAverage(AmountSet):
    """최근 평균 (만원). 매매는 평당 평균(`price_per_pyeong_manwon`)도 함께 낸다."""

    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당 평균 (만원). 매매에만 있다')
    ] = None


class DabangPriceTrend(BaseModel):
    """평형 하나의 시세 흐름 (월별 평균 실거래가, 국토부 신고 기준)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID')
    ]
    trade_averages: Annotated[
        dict[str, DabangTradeAverage | None],
        Field(description=(
            "거래별 최근 평균 (만원). 키는 'sale'(price_manwon, 평당 평균 price_per_pyeong_manwon)·'jeonse'(deposit_manwon) 늘 두 개이고 "
            '다방이 그 거래 평균을 주지 않으면 그 거래가 null. 일부 칸만 모르면 그 칸만 null'
        ))
    ]
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description='전세가율 (%) = 전세 평균 / 매매 평균')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='매매 평균 − 전세 평균 (만원)')
    ] = None
    trade_ranges: Annotated[
        dict[str, dict[str, AmountRange | None] | None] | None,
        Field(description=(
            "기간별 최저·최고 실거래가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 아래 기간 'one_year'·'three_years'이고, 기간 안 "
            '두 끝을 모두 모르면 그 기간은 null, 두 기간 모두 모르면 그 거래가 null. 다방이 기간별 값을 주지 않으면 전체가 null'
        ))
    ] = None
    months: Annotated[
        list[DabangTrendMonth],
        Field(description='오래된 달부터 36달')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평형 안내')
    ] = []


def _average(value: float | None) -> float | None:
    """달 평균. 다방은 거래 없는 달에 앞 달 평균을 잇는데, 이을 앞 달 평균도 없으면(그때까지 거래가 없던 평형) 0 을 준다.
    0만원 평균은 없으니 모름(None)으로 둔다 (2026-10-26 실측: 거래가 한 번도 없는 6979662367f35b14fef7600dcb63 평형
    311325 는 36달 모두 0 인데 같은 응답에서 읽은 최근 평균 trade_averages 의 sale price_manwon 은 null).
    """
    return value or None


def _range(value: DabangHighLowModel | None, trade: Literal['매매', '전세']) -> AmountRange | None:
    """기간 하나의 최저·최고. 두 끝을 모두 모르면 None. 금액 칸은 매매 price_manwon, 전세 deposit_manwon 이다."""
    if value is None or (value.highest is None and value.lowest is None):
        return None
    if trade == '매매':
        return AmountRange(lowest=AmountSet(price_manwon=value.lowest), highest=AmountSet(price_manwon=value.highest))
    return AmountRange(lowest=AmountSet(deposit_manwon=value.lowest), highest=AmountSet(deposit_manwon=value.highest))


def _trade_periods(one_year: AmountRange | None, three_years: AmountRange | None) -> dict[str, AmountRange | None] | None:
    """한 거래의 기간별 범위. 두 기간 모두 모르면 그 거래가 None."""
    if one_year is None and three_years is None:
        return None
    return {'one_year': one_year, 'three_years': three_years}


def get_price_trend(client: DabangClient, complex_id: str, *, space_seq: int | None) -> DabangPriceTrend:
    """평형 하나의 36달 시세 흐름 (요청 1회, 평형을 안 주면 대표 평형을 찾느라 +1).

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, space_notes = primary_space(client, complex_id, verb='찾았습니다')
        notes += space_notes
    result = _fetch_complex_space(
        lambda: client.run_request_real_price_complex_charts_v5(
            DabangRealPriceComplexChartsV5RequestParameterModel(complex_id=complex_id, space_seq=space_seq)
        ).result,
        complex_id,
        space_seq,
    )
    if result is None:
        raise JibsaError(code='NOT_FOUND', message=f'다방 시세 흐름이 없습니다: {complex_id}', hint='단지 ID·평형 번호를 확인하세요')
    sale = result.sale or DabangChartSeriesModel()
    lease = result.lease_monthly or DabangChartSeriesModel()
    lease_by_month = {row.date: row for row in lease.statistics}
    gap_rows = (result.gap.statistics or []) if result.gap else []
    gap_by_month = {row.date: row for row in gap_rows if row.date is not None}
    # 달 목록은 매매 쪽으로 만든다. 매매·전월세는 늘 같은 36달이고, 매매가 한 건도 없는 평형도 sale 이 null 이 아니라
    # 거래 0건인 36달로 온다 (2026-10-25 실측: 은마·오피스텔 2곳 8개 평형, 매매 0건인 메이플자이 299902)
    months = [
        DabangTrendMonth(
            month=read_month(row.date, '시세 흐름 달'),
            trade_averages={
                'sale': None if (sale_average := _average(row.average_price)) is None else AmountSet(price_manwon=sale_average),
                'jeonse': None if (lease_average := (
                    _average(lease_by_month[row.date].average_price) if row.date in lease_by_month else None
                )) is None else AmountSet(deposit_manwon=lease_average),
            },
            trade_counts={
                'sale': row.volume,
                'jeonse': lease_by_month[row.date].lease_volume if row.date in lease_by_month else None,
                'wolse': lease_by_month[row.date].monthly_volume if row.date in lease_by_month else None,
            },
            # 웹 갭 그래프는 전세가율이 0 이면 '-' 로 쓴다 (`leaseRate||'-'`). 0% 전세가율은 없으니 모름(None)으로 둔다
            jeonse_ratio_percent=gap_by_month[row.date].lease_rate or None if row.date in gap_by_month else None,
            # 리뷰 오탐 (2026-11-13, 근거 고침 2026-11-20): 평균이 없는 달에 갭이 큰 숫자로 나온다는 지적. 웹 갭 그래프 툴팁
            # (ic_24_cook_gray600 청크)은 그 달 gap.statistics 의 rangeAveragePrice 를 그대로 그리고(price-unit 청크 `S` 는 숫자가
            # 아니면 '-'), 한쪽 평균만 없는 달에도 서버가 갭을 null 로 준다 (2026-11-20 은마 817: 202601 매매 null·전세 70212 →
            # 갭 null, 202611 매매 307750·전세 null → 갭 null). 서버 값을 그대로 내도 모름이 숫자로 나오지 않는다
            gap_manwon=gap_by_month[row.date].range_average_price if row.date in gap_by_month else None,
        )
        for row in sale.statistics
    ]
    # 달 목록을 매매 쪽으로 만들어서 거기서 빈 항목을 뺐으면 그 달이 목록에서 빠졌다
    if dropped := sale.null_items('statistics'):
        notes.append(null_items_note('다방 시세 흐름 매매 월별', dropped))
    gap = result.gap.recent_info if result.gap else None
    year = result.year_price
    per_space = sale.per_space
    lease_per_space = lease.per_space
    return DabangPriceTrend(
        complex_id=complex_id,
        pyeong_id=space_seq,
        trade_averages={
            'sale': None if per_space is None or (
                per_space.average_price is None and per_space.average_pyeong_price is None
            ) else DabangTradeAverage(
                price_manwon=per_space.average_price,
                price_per_pyeong_manwon=per_space.average_pyeong_price,
            ),
            'jeonse': None if lease_per_space is None or lease_per_space.average_price is None else DabangTradeAverage(
                deposit_manwon=lease_per_space.average_price,
            ),
        },
        jeonse_ratio_percent=gap.lease_rate if gap else None,
        gap_manwon=gap.range_average_price if gap else None,
        trade_ranges=None if year is None else {
            'sale': _trade_periods(
                _range(year.sale.one_year if year.sale else None, '매매'),
                _range(year.sale.three_years if year.sale else None, '매매'),
            ),
            'jeonse': _trade_periods(
                _range(year.lease.one_year if year.lease else None, '전세'),
                _range(year.lease.three_years if year.lease else None, '전세'),
            ),
        },
        months=months,
        notes=notes,
    )


class DabangNearbyComplex(BaseModel):
    """반경 1km 주변 단지 하나 (평당가 비교)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (complex·real-price 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (동까지, '서울특별시 강남구 대치동')")
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description="그 평형대 평당가 (만원). nearby 의 'sale' 아래는 매매, 'jeonse' 아래는 전세. 다방 웹이 빈 칸으로 두는 값은 null")
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description="입주 N년차 (사용승인한 해를 1년차로 센다. 다방 '입주 37년차')")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='이 단지에서 거리 (m, 다방 값. 웹 목록은 거리를 그리지 않는다)')
    ] = None


class DabangNearbyComplexes(BaseModel):
    """단지 평형대 평당가와 반경 1km 주변 단지 비교 (다방 웹 단지 화면 평당가 칸의 기본 탭 'N평대 비교')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='고른 평형 ID (그 평형이 든 평형대로 비교한다)')
    ]
    # 리뷰 오탐 (2026-11-14): 'N평대 비교' 탭을 주지 않는 것은 다방이 값을 주지 않은 모름이라 키를 빼지 않고 null 로 둔다
    # (해당 없음 아님). 웹도 이때 이 탭을 그리지 않는다 (소스 가이드 평형대 평당가 비교)
    pyeong_range: Annotated[
        str | None,
        Field(description="비교한 평형대 (다방 탭 이름 '30평대 비교' 의 '30평대'). 다방이 이 평형에 평형대 탭을 주지 않으면 null")
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice] | None,
        Field(description=(
            "그 평형대의 평당 평균가 (이 단지·동·구, 만원). 다방 웹이 '정보 없음' 으로 쓰는 값(없거나 0)은 그 거래가 null. "
            "다방이 이 평형에 평형대 탭을 주지 않거나 이 목록을 null 로 주면 목록 전체가 null"
        ))
    ] = None
    nearby: Annotated[
        dict[str, list[DabangNearbyComplex] | None],
        Field(description=(
            "반경 1km 주변 단지의 거래별 평당가. 키는 'sale'·'jeonse' 늘 두 개. 'sale'은 다방 순서 그대로(평당가가 있는 단지를 가까운 "
            "순으로 앞에), 'jeonse'는 다방 웹 전월세 탭 순서 그대로. 다방이 평형대 탭이나 주변 단지(nearComplexes)나 그 거래 쪽을 "
            'null 로 주면 그 값이 null, 주었는데 그 쪽이 비었으면 []'
        ))
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평형 안내')
    ] = []


def _nearby_complex(row: DabangNearComplexModel) -> DabangNearbyComplex | None:
    # 웹은 단지 ID 가 없는 줄을 그리지 않는다 (complex 청크 `nn`: `if(!e.complexId)return null`)
    if not row.complex_id:
        return None
    return DabangNearbyComplex(
        complex_id=row.complex_id,
        name=row.complex_name,
        complex_type=COMPLEX_KIND_BY_TYPE.get(row.complex_type or ''),
        address=normalize_address(row.address),
        # 리뷰 오탐 (2026-11-14): 주변 단지 평당가는 0 을 null 로 바꾸지 않는다. 웹 complex 청크 `nn` 은 `averagePyeongPrice ?? ''` 를
        # 가격 글자로 바꿔 null 은 '-', 0 은 '0원' 으로 그린다 (area_prices 막대 `Yt` 와 다르다)
        price_per_pyeong_manwon=row.average_pyeong_price,
        household_count=row.household_num,
        occupancy_years=building_years(row.complex_desc),
        distance_m=row.distance,
    )


def get_nearby_complexes(client: DabangClient, complex_id: str, *, space_seq: int | None) -> DabangNearbyComplexes:
    """평형대 평당가와 반경 1km 주변 단지 비교 (요청 1회, 평형을 안 주면 대표 평형을 찾느라 +1).

    다방 웹 단지 화면 평당가 칸의 기본 탭('N평대 비교')이다. 다방이 탭 이름을 비워 주면 웹은 이 탭을 그리지 않고 '전체 평형
    비교'(complex 결과 area_prices)만 보여 주므로 area_prices 와 nearby 의 sale·jeonse 를 모름(null)으로 두고 안내를 낸다.

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, space_notes = primary_space(client, complex_id, verb='비교했습니다')
        notes += space_notes
    result = _fetch_complex_space(
        lambda: client.run_request_real_price_complex_price_per_py_v5(
            DabangRealPriceComplexPricePerPyV5RequestParameterModel(complex_id=complex_id, space_seq=space_seq)
        ).result,
        complex_id,
        space_seq,
    )
    tab = (result.pyeong_range_tab_name or '').strip() if result else ''
    if result is None or not tab:
        notes.append(note(
            '참고',
            f"다방이 이 평형(pyeong_id {space_seq})에는 'N평대 비교' 를 주지 않습니다 (다방 웹도 이 탭 없이 '전체 평형 비교' 만 "
            f'보여 줍니다). 단지 전체 평형의 평당가 비교는 jibsa dabang complex {complex_id} 의 area_prices 로 보세요',
        ))
        return DabangNearbyComplexes(
            complex_id=complex_id, pyeong_id=space_seq, nearby={'sale': None, 'jeonse': None}, url=complex_url(complex_id), notes=notes,
        )
    near = result.near_complexes
    # 매매·전월세 쪽이 null 이면 그 쪽은 모름(null), 비어 있으면 []
    sale_rows = [_nearby_complex(row) for row in near.trade] if near and near.trade is not None else None
    lease_rows = [_nearby_complex(row) for row in near.lease] if near and near.lease is not None else None
    skipped = (sale_rows or []).count(None) + (lease_rows or []).count(None)
    if skipped:
        notes.append(note('제외', f'단지 ID 가 없는 주변 단지 {skipped}줄은 다방 웹처럼 넣지 않았습니다'))
    return DabangNearbyComplexes(
        complex_id=complex_id,
        pyeong_id=space_seq,
        pyeong_range=tab.removesuffix('비교').strip(),
        area_prices=None if result.area_average_price is None else [area_price(price) for price in result.area_average_price],
        nearby={
            'sale': None if sale_rows is None else [row for row in sale_rows if row is not None],
            'jeonse': None if lease_rows is None else [row for row in lease_rows if row is not None],
        },
        url=complex_url(complex_id),
        notes=notes,
    )
