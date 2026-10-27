"""실거래가 (real-price) 와 시세 흐름 (price-trend)."""
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
    UPDATE_MAYBE_NEEDED,
    TradeType,
    normalize_date,
    normalize_floor,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.real_price import (
    REAL_PRICE_PAGE_LIMIT,
    DabangRealPriceComplexChartsV5RequestParameterModel,
    DabangRealPriceComplexHistoriesV5RequestParameterModel,
    DabangRealPriceHouseHistoryV5RequestParameterModel,
    DabangRealPriceSearchType,
)
from jibsa.providers.dabang.api.response.real_price import (
    DabangChartSeriesModel,
    DabangHighLowModel,
    DabangRealPriceHistoryModel,
)
from jibsa.providers.dabang.service.common import (
    complex_not_found,
    complex_url,
    fetch_complex,
    listing_url,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


RealPriceTrade = Literal['매매', '전월세']
SEARCH_TYPE_BY_TRADE: dict[RealPriceTrade, DabangRealPriceSearchType] = {'매매': 'SALE', '전월세': 'LEASE'}
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
        Field(description='층. 모르면 null')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, 단지 없는 매물 실거래만. 단지는 평형으로 고른다)')
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
    direct: Annotated[
        bool | None,
        Field(description='직거래')
    ] = None
    show_area: Annotated[
        bool,
        Field(exclude=True, description='면적 키를 낼지 (단지 없는 매물 실거래만)')
    ] = False

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
            data.pop(field, None)
        if not self.show_area:
            data.pop('area_m2', None)
        return data


def _unknown_trade_note(count: int) -> list[str]:
    """거래 유형을 모르는 줄을 뺀 안내. 다방 실거래는 SALE·LEASE·MONTHLY 셋뿐이다 (2026-10-25 실측: 단지 10곳 567건)."""
    return [note('제외', f'거래 유형을 읽지 못한 실거래 {count}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}')] if count else []


def _real_price(row: DabangRealPriceHistoryModel, *, show_area: bool = False) -> DabangRealPrice | None:
    """실거래 한 줄. 거래 유형을 모르면 None (부르는 쪽이 빼고 알린다)."""
    trade_type = TRADE_BY_PRICE_TYPE.get(row.price_type or '')
    if trade_type is None:
        return None
    contract = row.contract_date
    floor = row.format_floor if row.format_floor not in (None, '', 'null') else None
    return DabangRealPrice(
        trade_type=trade_type,
        trade_date=normalize_date(f'20{contract}') if contract else None,
        # 지하는 음수로 온다 ('-1', 2026-10-25 실측: 망원동 다세대 매매 50건 중 6건)
        floor=normalize_floor(str(int(floor))) if floor and floor.lstrip('-').isdecimal() else floor,
        area_m2=row.size,
        price_manwon=row.trade_price,
        deposit_manwon=row.deposit,
        rent_manwon=row.monthly_price,
        cancelled=row.is_release,
        direct=row.is_direct,
        show_area=show_area,
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
    space_seq: Annotated[
        int | None,
        Field(description='평형 번호 (단지 실거래만)')
    ] = None
    trade: Annotated[
        RealPriceTrade,
        Field(description='매매 또는 전월세')
    ]
    from_month: Annotated[
        str,
        Field(description='조회 시작 달 (YYYY-MM)')
    ]
    to_month: Annotated[
        str,
        Field(description='조회 끝 달 (YYYY-MM)')
    ]
    basis: Annotated[
        str | None,
        Field(description="거래를 모은 범위 (--listing: '역삼동 단독·다가구' 처럼 그 동의 같은 건물 유형)")
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
    transactions: Annotated[
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
        for key in ('complex_id', 'listing_id', 'space_seq'):
            if data.get(key) is None:
                data.pop(key, None)
        # 기준 범위는 매물 실거래(--listing)에만 해당한다. 그때 비면 모름(null)으로 남긴다
        if self.listing_id is None:
            data.pop('basis', None)
        return data


def _month(value: str) -> str:
    return f'{value[:4]}-{value[4:]}'


BUILDING_VIEW_LABELS: dict[str, str] = {'DETACHED': '단독·다가구', 'MULTIPLEX': '다세대·연립', 'APARTMENT': '아파트', 'OFFICETEL': '오피스텔'}


def _error_message(exc: HTTPStatusError) -> str | None:
    """다방 400 본문의 사유 ("존재하지 않는 단지입니다." 등). 없거나 JSON 이 아니면 None."""
    try:
        body = exc.response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    message = body.get('msg')
    return message if isinstance(message, str) else None


def _complex_error(exc: HTTPStatusError, complex_id: str, space_seq: int) -> JibsaError | None:
    """단지 실거래·시세 흐름의 없는 단지·평형을 NOT_FOUND·INVALID_ARGUMENT 로 바꾼다 (아니면 None).

    다방은 없는 단지·평형에 400 과 사유를 준다 (2026-10-25 실측: 평형 1 → '존재하지 않는 평형 정보입니다.',
    없는 단지 → histories '존재하지 않는 단지입니다.'·charts '존재하지 않는 단지 정보입니다.'). 단지 ID 가 쿼리로 가서 403 은
    없는 단지가 아니라 다방 주소가 바뀐 것이다 (`is_missing_id`).
    """
    if exc.response.status_code != 400:
        return None
    message = _error_message(exc) or ''
    if '평형' in message:
        return JibsaError(
            code='INVALID_ARGUMENT',
            message=f'이 단지에 없는 평형 번호입니다: {space_seq}',
            hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].space_seq 를 주세요',
        )
    if '단지' in message:
        return complex_not_found(complex_id)
    return None


def primary_space_seq(client: DabangClient, complex_id: str) -> tuple[int, str]:
    """단지의 다방 대표 평형 번호와 이름 (단지 상세 1회).

    Raises:
        JibsaError: 단지가 없거나 평형이 없을 때 (NOT_FOUND).
    """
    result = fetch_complex(client, complex_id)
    if not result.spaces:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방 단지의 평형을 찾지 못했습니다: {complex_id}',
            hint='jibsa dabang complex <단지ID> 결과의 pyeongs[].space_seq 를 --pyeong 으로 주세요',
        )
    seq = result.primary_space_seq or result.spaces[0].space_seq
    name = next((space.pyeong_type for space in result.spaces if space.space_seq == seq), None)
    return seq, name or str(seq)


class _Page(NamedTuple):
    """실거래 한 쪽 (단지·매물 응답에서 같은 뜻의 칸)."""

    histories: list[DabangRealPriceHistoryModel]
    total: int | None
    has_more: bool


class _Collected(NamedTuple):
    prices: list[DabangRealPrice]
    total: int | None
    has_more: bool
    unknown: int


def _collect(fetch: Callable[[int, int], _Page | None], limit: int, *, show_area: bool = False) -> _Collected:
    """실거래를 `limit` 줄까지 쪽마다 받는다. `fetch(page, page_size)` 는 한 쪽을 주고, 결과가 없으면 None.

    다방은 (page - 1) × limit 번째부터 준다. 쪽마다 크기를 바꾸면 앞 쪽과 겹쳐 쪽 크기를 고정하고 넘치는 건 자른다
    (2026-10-25 실측: 50건 다음 10건을 물으니 11~20번째를 다시 줬다). limit 은 받은 줄 수로 센다. 거래 유형을 읽지 못해
    뺀 줄만큼 다음 쪽을 더 받지 않는다.
    """
    prices: list[DabangRealPrice] = []
    total: int | None = None
    has_more = False
    received = unknown = 0
    page_size = min(REAL_PRICE_PAGE_LIMIT, limit)
    for page in range(1, REAL_PRICE_MAX_PAGES + 1):
        fetched = fetch(page, page_size)
        if fetched is None:
            break
        total = fetched.total if total is None else total
        page_rows = fetched.histories[:limit - received]
        received += len(page_rows)
        rows = [_real_price(row, show_area=show_area) for row in page_rows]
        prices += [price for price in rows if price is not None]
        unknown += rows.count(None)
        has_more = fetched.has_more or len(page_rows) < len(fetched.histories)
        if not fetched.has_more or received >= limit:
            break
    return _Collected(prices, total, has_more, unknown)


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
        space_seq, name = primary_space_seq(client, complex_id)
        notes.append(f'--pyeong 을 주지 않아 다방 대표 평형({name}, space_seq {space_seq})으로 찾았습니다. 다른 평형은 complex 결과의 pyeongs 에서 고르세요')
    from_month, to_month = period_months(years)

    def fetch(page: int, page_size: int) -> _Page | None:
        try:
            result = client.run_request_real_price_complex_histories_v5(DabangRealPriceComplexHistoriesV5RequestParameterModel(
                complex_id=complex_id, space_seq=space_seq, from_date=from_month, to_date=to_month,
                search_type=SEARCH_TYPE_BY_TRADE[trade], page=page, limit=page_size,
            )).result
        except HTTPStatusError as exc:
            error = _complex_error(exc, complex_id, space_seq)
            if error is not None:
                raise error from None
            raise
        return _Page(result.list_, result.total, bool(result.has_more)) if result else None

    collected = _collect(fetch, limit)
    return DabangRealPriceResult(
        complex_id=complex_id,
        space_seq=space_seq,
        trade=trade,
        from_month=_month(from_month),
        to_month=_month(to_month),
        total=collected.total,
        returned=len(collected.prices),
        has_more=collected.has_more,
        transactions=collected.prices,
        url=complex_url(complex_id),
        notes=notes + _unknown_trade_note(collected.unknown),
    )


def get_listing_real_prices(
    client: DabangClient,
    listing_id: str,
    *,
    trade: RealPriceTrade,
    years: int,
    limit: int,
) -> DabangRealPriceResult:
    """단지 없는 매물(빌라·주택·원룸)의 실거래. 그 건물이 아니라 같은 동의 같은 건물 유형 거래다 (다방 매물 상세 화면과 같다).

    Raises:
        JibsaError: 매물이 없거나 단지 매물일 때 (NOT_FOUND).
    """
    from_month, to_month = period_months(years)
    basis: str | None = None

    def fetch(page: int, page_size: int) -> _Page | None:
        nonlocal basis
        # 매물 ID 가 쿼리로 가서 없는 매물에도 에러가 아니라 빈 결과가 온다. 그래서 4xx·403 은 다방 주소가 바뀐 것으로 둔다
        result = client.run_request_real_price_house_history_v5(DabangRealPriceHouseHistoryV5RequestParameterModel(
            room_id=listing_id, from_date=from_month, to_date=to_month,
            search_type=SEARCH_TYPE_BY_TRADE[trade], page=page, limit=page_size,
        )).result
        if result is None:
            return None
        if page == 1 and result.dong_name is None and result.history_base_type is None:
            # 없는 매물·단지 매물(오피스텔·아파트)에는 에러 대신 동·범위가 빈 0건을 준다. 거래가 0건인 매물도 동·범위는 온다
            # (2026-10-25 실측: 없는 ID·강남역 오피스텔 매물은 dongName·historyBaseType null, 도곡동 단독 1년 매매 0건은 '도곡동'·'DONG')
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방이 이 매물의 동 실거래를 주지 않았습니다: {listing_id} (없는 매물이거나 단지 매물)',
                hint='단지 없는 매물(빌라·주택·원룸)의 ID 를 주세요. 오피스텔·아파트 매물은 jibsa dabang listing <ID> 결과의 '
                'complex_id 로 jibsa dabang real-price <complex_id>',
            )
        if basis is None and result.dong_name:
            building = BUILDING_VIEW_LABELS.get(result.building_view_type or '', result.building_view_type or '')
            basis = f'{result.dong_name} {building}'.strip() if result.history_base_type == 'DONG' else result.dong_name
        return _Page(result.histories, result.total, bool(result.has_more))

    collected = _collect(fetch, limit, show_area=True)
    scope = f'같은 동의 같은 건물 유형({basis})' if basis else '같은 동의 같은 건물 유형'
    notes = [f'이 매물 건물이 아니라 {scope} 실거래입니다 (다방 매물 화면과 같은 범위). 면적(area_m2)을 보고 비슷한 집만 견주세요']
    notes += _unknown_trade_note(collected.unknown)
    return DabangRealPriceResult(
        listing_id=listing_id,
        trade=trade,
        from_month=_month(from_month),
        to_month=_month(to_month),
        basis=basis,
        total=collected.total,
        returned=len(collected.prices),
        has_more=collected.has_more,
        transactions=collected.prices,
        url=listing_url(listing_id),
        notes=notes,
    )


class DabangTrendMonth(BaseModel):
    """시세 흐름의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str,
        Field(description='달 (YYYY-MM)')
    ]
    sale_average_manwon: Annotated[
        float | None,
        Field(description='매매 평균 실거래가 (만원). 거래 없는 달은 다방이 앞 달 평균을 잇고, 이을 평균도 없으면 null')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='매매 거래 수')
    ] = None
    lease_average_manwon: Annotated[
        float | None,
        Field(description='전세 평균 실거래가 (만원). 매매와 같이 이을 평균이 없으면 null')
    ] = None
    lease_count: Annotated[
        int | None,
        Field(description='전세 거래 수')
    ] = None
    rent_count: Annotated[
        int | None,
        Field(description='월세 거래 수')
    ] = None


class DabangPriceRange(BaseModel):
    """기간 안 최고·최저 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    highest_manwon: Annotated[
        float | None,
        Field(description='최고 (만원)')
    ] = None
    lowest_manwon: Annotated[
        float | None,
        Field(description='최저 (만원)')
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
    space_seq: Annotated[
        int,
        Field(description='평형 번호')
    ]
    sale_average_manwon: Annotated[
        float | None,
        Field(description='최근 매매 평균 (만원)')
    ] = None
    sale_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='최근 매매 평당 평균 (만원)')
    ] = None
    lease_average_manwon: Annotated[
        float | None,
        Field(description='최근 전세 평균 (만원)')
    ] = None
    lease_rate_percent: Annotated[
        float | None,
        Field(description='전세가율 (%) = 전세 평균 / 매매 평균')
    ] = None
    gap_manwon: Annotated[
        float | None,
        Field(description='매매 평균 − 전세 평균 (만원)')
    ] = None
    sale_1y: Annotated[
        DabangPriceRange | None,
        Field(description='최근 1년 매매 최고·최저')
    ] = None
    sale_3y: Annotated[
        DabangPriceRange | None,
        Field(description='최근 3년 매매 최고·최저')
    ] = None
    lease_1y: Annotated[
        DabangPriceRange | None,
        Field(description='최근 1년 전세 최고·최저')
    ] = None
    lease_3y: Annotated[
        DabangPriceRange | None,
        Field(description='최근 3년 전세 최고·최저')
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
    311325 는 36달 모두 0 인데 같은 응답에서 읽은 최근 평균 sale_average_manwon 은 null).
    """
    return value or None


def _range(value: DabangHighLowModel | None) -> DabangPriceRange | None:
    if value is None or (value.highest is None and value.lowest is None):
        return None
    return DabangPriceRange(highest_manwon=value.highest, lowest_manwon=value.lowest)


def get_price_trend(client: DabangClient, complex_id: str, *, space_seq: int | None) -> DabangPriceTrend:
    """평형 하나의 36달 시세 흐름 (요청 1회, 평형을 안 주면 대표 평형을 찾느라 +1).

    Raises:
        JibsaError: 단지가 없을 때 (NOT_FOUND), 단지에 없는 평형 번호를 줬을 때 (INVALID_ARGUMENT).
    """
    notes: list[str] = []
    if space_seq is None:
        space_seq, name = primary_space_seq(client, complex_id)
        notes.append(f'--pyeong 을 주지 않아 다방 대표 평형({name}, space_seq {space_seq})으로 찾았습니다')
    try:
        result = client.run_request_real_price_complex_charts_v5(
            DabangRealPriceComplexChartsV5RequestParameterModel(complex_id=complex_id, space_seq=space_seq)
        ).result
    except HTTPStatusError as exc:
        error = _complex_error(exc, complex_id, space_seq)
        if error is not None:
            raise error from None
        raise
    if result is None:
        raise JibsaError(code='NOT_FOUND', message=f'다방 시세 흐름이 없습니다: {complex_id}', hint='단지 ID·평형 번호를 확인하세요')
    sale = result.sale or DabangChartSeriesModel()
    lease = result.lease_monthly or DabangChartSeriesModel()
    lease_by_month = {row.date: row for row in lease.statistics}
    # 달 목록은 매매 쪽으로 만든다. 매매·전월세는 늘 같은 36달이고, 매매가 한 건도 없는 평형도 sale 이 null 이 아니라
    # 거래 0건인 36달로 온다 (2026-10-25 실측: 은마·오피스텔 2곳 8개 평형, 매매 0건인 메이플자이 299902)
    months = [
        DabangTrendMonth(
            month=_month(row.date),
            sale_average_manwon=_average(row.average_price),
            sale_count=row.volume,
            lease_average_manwon=_average(lease_by_month[row.date].average_price) if row.date in lease_by_month else None,
            lease_count=lease_by_month[row.date].lease_volume if row.date in lease_by_month else None,
            rent_count=lease_by_month[row.date].monthly_volume if row.date in lease_by_month else None,
        )
        for row in sale.statistics
    ]
    gap = result.gap.recent_info if result.gap else None
    year = result.year_price
    return DabangPriceTrend(
        complex_id=complex_id,
        space_seq=space_seq,
        sale_average_manwon=sale.per_space.average_price if sale.per_space else None,
        sale_per_pyeong_manwon=sale.per_space.average_pyeong_price if sale.per_space else None,
        lease_average_manwon=lease.per_space.average_price if lease.per_space else None,
        lease_rate_percent=gap.lease_rate if gap else None,
        gap_manwon=gap.range_average_price if gap else None,
        sale_1y=_range(year.sale.one_year) if year and year.sale else None,
        sale_3y=_range(year.sale.three_years) if year and year.sale else None,
        lease_1y=_range(year.lease.one_year) if year and year.lease else None,
        lease_3y=_range(year.lease.three_years) if year and year.lease else None,
        months=months,
        notes=notes,
    )

