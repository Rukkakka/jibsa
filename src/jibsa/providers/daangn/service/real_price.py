"""단지·매물·지역 실거래가와 시세 추이 (real-price, region-real-price, price-trend)."""

from collections.abc import Callable
from datetime import (
    date,
    datetime,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    KST,
    NOT_APPLICABLE_PRICE_FIELDS,
    normalize_address,
    normalize_date,
    normalize_floor,
    won_to_manwon,
    years_ago,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import DaangnExclusiveUseAreaModel
from jibsa.providers.daangn.api.request.real_price import (
    DaangnArticleByOriginalArticleIdRequestPayloadModel,
    DaangnComplexByOriginalIdRequestPayloadModel,
    DaangnComplexPriceChartRequestPayloadModel,
    DaangnPriceChartTradeType,
    DaangnRealsaleFeedInputModel,
    DaangnRealsaleFeedRequestPayloadModel,
    DaangnRealsaleNewHighFeedInputModel,
    DaangnRealsaleNewHighFeedRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnPageInfoModel,
    DaangnTransactionModel,
)
from jibsa.providers.daangn.api.response.real_price import (
    DaangnComplexTransactionsModel,
    DaangnRealsaleFeedItemModel,
    DaangnRealsaleFeedModel,
)
from jibsa.providers.daangn.service.common import (
    T,
    article_url,
    complex_not_found,
    complex_url,
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
)

from typing import (
    Annotated,
    Any,
)


RENT_TYPE_BY_TRADE_TYPE: dict[str, str] = {'전세': 'BORROW', '월세': 'MONTHLY'}
PRESALE_LABELS: dict[str, str] = {'PRE_SALE_RIGHT': '분양권', 'PRE_SALE_OWNER': '입주권'}
# 실거래 한 번에 받는 수와, 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건)
REAL_PRICE_PAGE_SIZE: int = 50
REAL_PRICE_MAX_PAGES: int = 24
# real-price·region-real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES
# 지역 실거래 피드 정렬 (라벨 → 당근 값)
REALSALE_SORT_BY_LABEL: dict[str, str] = {'최신': 'LATEST', '가격': 'TRADE_PRICE_DESC'}
# 단지 시세 추이: 거래 유형(차트는 매매·전세만 있다), 기간, 변화율을 낼 때 거래 수로 가중 평균하는 개월 수
# (한 달만 비교하면 거래가 1~2건인 달이 많아 튄다)
PRICE_CHART_TRADE_BY_TRADE_TYPE: dict[str, DaangnPriceChartTradeType] = {'매매': 'BUY', '전세': 'BORROW'}
PRICE_TREND_WINDOW_MONTHS: int = 3
# 마지막 거래가 이 개월 수보다 오래됐으면 최근 시세가 아니라고 알린다
PRICE_TREND_STALE_MONTHS: int = 6
# 비교 구간 거래가 이보다 적으면 변화율이 튈 수 있다고 알린다
PRICE_TREND_FEW_TRANSACTIONS: int = 3


class DaangnRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    registered: Annotated[
        bool | None,
        Field(description='등기까지 마친 거래 (매매만)')
    ] = None
    presale: Annotated[
        str | None,
        Field(description='분양권 / 입주권 거래 (매매만, 해당할 때만 키가 있다)')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신·재계약 (전월세만). 새 계약보다 낮게 잡히는 경우가 많다. 당근이 계약 종류를 주지 않으면 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('renewal')
        else:
            fields |= {'cancelled', 'registered', 'presale'}
        if self.presale is None:
            fields.add('presale')
        for field in fields:
            data.pop(field, None)
        return data


class DaangnRealPriceBaseResult(BaseModel):
    """실거래 내역 공통."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 오래된 거래가 더 있는지 (--years 를 줬으면 그 기간 안에서)')
    ]
    since: Annotated[
        str | None,
        Field(description='--years 로 준 기간의 시작일 (YYYY-MM-DD, 이날부터 계약). 주지 않았으면 키가 없다')
    ] = None
    transactions: Annotated[
        list[DaangnRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='전월세를 넘겨 본 범위, 거래가 없는 이유 안내. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_unused_since(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.since is None:
            data.pop('since', None)
        return data


class DaangnRealPriceResult(DaangnRealPriceBaseResult):
    """단지 실거래 내역."""

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음. null 이면 전체 평형')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 그래프는 여기서 본다)')
    ]


class DaangnListingRealPriceResult(DaangnRealPriceBaseResult):
    """매물이 있는 건물(단지)의 비슷한 면적 실거래 내역."""

    listing_id: Annotated[
        str,
        Field(description='매물 ID')
    ]
    url: Annotated[
        str,
        Field(description='매물 페이지 URL')
    ]


def _trade_date(node: DaangnTransactionModel) -> str | None:
    if node.deal_year is None or node.deal_month is None or node.deal_day is None:
        return None
    return f'{node.deal_year:04d}-{node.deal_month:02d}-{node.deal_day:02d}'


def _renewal(contract_type: str | None, used_renewal_right: bool | None) -> bool | None:
    """전월세가 갱신 계약인지. 갱신요구권을 썼거나 RENEWAL 이면 True, NEW 면 False, 계약 종류를 모르면 None.

    갱신요구권을 쓰지 않은 재계약(RENEWAL)도 많아 요구권을 안 썼다는 것만으로 신규라고 보지 않는다. 지역 실거래는
    계약 종류 없이 오기도 하고, 같은 거래가 단지 실거래에 NEW·RENEWAL 로 두 번 있기도 하다 (2026-10-10 실측:
    봉천동·신림동 등 전월세 약 600건 중 14건이 계약 종류 없음).
    """
    if used_renewal_right or contract_type == 'RENEWAL':
        return True
    if contract_type == 'NEW':
        return False
    return None


def transaction_to_real_price(node: DaangnTransactionModel, trade_type: str) -> DaangnRealPrice:
    """실거래 한 건을 `DaangnRealPrice` 로 바꾼다. 금액은 원래 만원이다."""
    buy = trade_type == '매매'
    return DaangnRealPrice(
        trade_type=trade_type,
        trade_date=_trade_date(node),
        area_m2=node.exclusive_use_area,
        floor=normalize_floor(node.floor),
        price_manwon=node.deal_amount if buy else None,
        deposit_manwon=None if buy else node.deposit,
        rent_manwon=node.monthly_rent if trade_type == '월세' else None,
        cancelled=node.deal_canceled if buy else None,
        registered=node.registrated_at is not None if buy else None,
        presale=PRESALE_LABELS.get(node.ownership or '') if buy else None,
        renewal=None if buy else _renewal(node.contract_type, node.use_renewal_of_contract_right),
    )


TransactionFetch = Callable[[int, str | None], DaangnComplexTransactionsModel]
# (받을 수, 커서) → (한 페이지의 거래, 페이지 정보)
PageFetch = Callable[[int, str | None], tuple[list[T], DaangnPageInfoModel | None]]


def _collect_pages(
    fetch: PageFetch[T],
    matches: Callable[[T], bool],
    trade_type: str,
    limit: int,
    *,
    more_note: str,
    since: str | None = None,
    date_of: Callable[[T], str | None] | None = None,
) -> tuple[list[T], bool, list[str]]:
    """실거래를 받은 순서(최근 순)대로 `limit` 건까지 모은다. 단지·매물 실거래와 지역 실거래가 함께 쓴다.

    매매는 필요한 만큼만 받고, 전세·월세는 당근이 전월세를 섞어 주므로 50건씩 최근 1200건까지 넘겨 보며
    `matches` 로 고른다. 커서가 반복되거나 다음 페이지가 비면 안내하고 멈춘다.

    Args:
        fetch: (받을 수, 커서) → (한 페이지의 거래, 페이지 정보).
        matches: 검색한 거래 유형의 거래인지.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        more_note: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때의 안내 (당근 사이트 링크).
        since: 이날(YYYY-MM-DD)보다 앞선 거래는 빼고, 그런 거래가 나온 페이지에서 멈춘다. 당근은 기간을 받지 않아
            최근 계약 순으로 넘기다 멈춘다 (계약 순으로 오는 단지·매물 실거래만 준다). 날짜를 모르는 거래는 남긴다.
        date_of: `since` 와 견줄 거래의 계약일.

    Returns:
        (거래, 더 있는지, 안내).
    """
    buy = trade_type == '매매'
    collected: list[T] = []
    after = None
    has_more = False
    scanned = 0
    pages = 0
    notes: list[str] = []
    for pages in range(1, REAL_PRICE_MAX_PAGES + 1):
        size = min(REAL_PRICE_PAGE_SIZE, limit - len(collected)) if buy else REAL_PRICE_PAGE_SIZE
        nodes, page_info = fetch(size, after)
        if after is not None and page_info and page_info.end_cursor == after:
            has_more = True
            notes.append('실거래의 다음 페이지 커서가 반복되어 조회를 중단했습니다. 나머지는 당근에서 확인하세요')
            break
        scanned += len(nodes)
        kept = nodes
        if since is not None and date_of is not None:
            kept = [node for node in nodes if (day := date_of(node)) is None or day >= since]
        collected += [node for node in kept if matches(node)]
        has_more = bool(page_info and page_info.has_next_page) or len(collected) > limit
        if len(kept) < len(nodes):
            # 최근 계약 순이라 기간보다 앞선 거래가 나오면 그 뒤도 모두 기간 밖이다. 3년치를 보려고 --limit 1200 으로 전부 받으면
            # 2018년 거래까지 938건(약 5만 토큰)이 왔다 (2026-10-31 에이전트 검증, 헬리오시티 84㎡ 매매. 3년 안은 452건)
            has_more = len(collected) > limit
            break
        if len(collected) >= limit or not has_more or page_info is None:
            break
        if not nodes or not page_info.end_cursor:
            notes.append('실거래의 다음 페이지가 비어 있거나 커서가 없어 조회를 중단했습니다. 나머지는 당근에서 확인하세요')
            break
        after = page_info.end_cursor

    if not buy and has_more and len(collected) < limit:
        notes.append(
            f'최근 전월세 실거래 {scanned}건 중 {trade_type} {len(collected)}건입니다. '
            '더 오래된 거래는 당근 사이트에서 확인하세요'
        )
    notes += truncation_notes(len(collected), limit, subject='실거래')
    if has_more and len(collected) >= limit and pages < REAL_PRICE_MAX_PAGES:
        # --limit 에서 멈췄으면 늘려서 더 받을 수 있다. 사이트에서 보라는 안내는 페이지 상한까지 보고도 남았을 때만 맞다
        # (2026-10-11 실측: 헬리오시티 --limit 3 에도 '당근에서 직접 확인' 이 붙었다)
        notes.append(
            f'거래가 더 남아 있습니다. --limit 을 늘리면 (최대 {REAL_PRICE_MAX_LIMIT}건) 더 받습니다'
        )
    elif has_more:
        notes.append(more_note)
    return collected[:limit], has_more, notes


def _collect_transactions(
    fetch: TransactionFetch,
    trade_type: str,
    limit: int,
    *,
    more_note: str,
    since: str | None = None,
) -> tuple[list[DaangnTransactionModel], bool, list[str]]:
    """단지·매물 실거래를 최근 계약 순으로 `limit` 건까지 모은다 (`_collect_pages`).

    Args:
        fetch: (받을 수, 커서) → 단지·매물의 실거래 연결. 매매면 매매 연결의, 아니면 전월세 연결의 크기·커서다.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        more_note: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때의 안내.
        since: 이날(YYYY-MM-DD)부터의 계약만 받는다 (`--years`).

    Returns:
        (거래, 더 있는지, 안내).
    """
    buy = trade_type == '매매'

    def page(size: int, after: str | None) -> tuple[list[DaangnTransactionModel], DaangnPageInfoModel | None]:
        transactions = fetch(size, after)
        connection = transactions.buy_transactions if buy else transactions.borrow_transactions
        if connection is None:
            return [], None
        return [edge.node for edge in connection.edges if edge.node], connection.page_info

    return _collect_pages(
        page,
        lambda node: buy or node.type == RENT_TYPE_BY_TRADE_TYPE[trade_type],
        trade_type,
        limit,
        more_note=more_note,
        since=since,
        date_of=_trade_date,
    )


def get_real_prices(
    client: DaangnClient,
    complex_id: int,
    *,
    trade_type: str = '매매',
    area_group: int | None = None,
    limit: int = 120,
    years: int | None = None,
    today: date | None = None,
) -> DaangnRealPriceResult:
    """단지 실거래가를 최근 계약 순으로 `limit` 건까지 모은다 (`_collect_transactions`).

    `years` 를 주면 그 햇수 전 오늘(한국 날짜)부터의 계약만 받고 그보다 앞선 거래가 나오면 멈춘다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND, 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래가 쿼리를 바꿨을 때.
    """
    buy = trade_type == '매매'

    def fetch(size: int, after: str | None) -> DaangnComplexTransactionsModel:
        response = client.run_request_complex_by_original_id(
            DaangnComplexByOriginalIdRequestPayloadModel(
                complex_id=str(complex_id),
                buy_first=size if buy else 1,
                buy_after=after if buy else None,
                borrow_first=1 if buy else size,
                borrow_after=None if buy else after,
                exclusive_use_area_group=area_group,
            )
        )
        result = unwrap_graphql(
            response, response.data.complex_by_original_id if response.data else None, '실거래가'
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        return result.complex

    since = years_ago(today or datetime.now(KST).date(), years) if years is not None else None
    collected, has_more, notes = _collect_transactions(
        fetch, trade_type, limit,
        more_note=f'더 오래된 거래가 남아 있습니다. 당근에서 직접 확인해 주세요: {complex_url(complex_id)}',
        since=since,
    )
    return DaangnRealPriceResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        area_group=area_group,
        returned=len(collected),
        has_more=has_more,
        since=since,
        transactions=[transaction_to_real_price(node, trade_type) for node in collected],
        url=complex_url(complex_id),
        notes=notes,
    )


class DaangnPricePoint(BaseModel):
    """월별 평균 실거래가 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    year_month: Annotated[
        str,
        Field(description='계약 연월 (YYYY-MM)')
    ]
    average_manwon: Annotated[
        float | None,
        Field(description='그 달 실거래 평균가 (만원, 전세는 보증금)')
    ] = None
    transaction_count: Annotated[
        int | None,
        Field(description='그 달 거래 수. 적으면 평균이 튈 수 있다')
    ] = None


class DaangnPriceTrendSummary(BaseModel):
    """최근과 N년 전의 평균가 비교. 각 시점은 3개월 거래를 거래 수로 가중 평균한다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    recent_period: Annotated[
        str,
        Field(description='최근 구간 (마지막 거래 달까지 3개월, YYYY-MM~YYYY-MM)')
    ]
    recent_average_manwon: Annotated[
        float,
        Field(description='최근 구간 평균가 (만원)')
    ]
    recent_transactions: Annotated[
        int,
        Field(description='최근 구간 거래 수')
    ]
    base_period: Annotated[
        str,
        Field(description='비교 구간 (최근 구간의 N년 전 3개월)')
    ]
    base_average_manwon: Annotated[
        float,
        Field(description='비교 구간 평균가 (만원)')
    ]
    base_transactions: Annotated[
        int,
        Field(description='비교 구간 거래 수')
    ]
    change_percent: Annotated[
        float,
        Field(description='비교 구간 대비 최근 구간 변화율 (%)')
    ]


class DaangnPriceTrendResult(BaseModel):
    """단지 시세 추이 (국토부 실거래 월별 평균)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='당근 단지 ID')
    ]
    trade_type: Annotated[
        str,
        Field(description='매매 / 전세')
    ]
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (㎡). null 이면 전 평형을 섞은 평균')
    ] = None
    years: Annotated[
        int,
        Field(description='points 기간 (년)')
    ]
    total_transactions: Annotated[
        int,
        Field(description='points 기간의 거래 수')
    ]
    summary: Annotated[
        DaangnPriceTrendSummary | None,
        Field(description='최근과 years 년 전 비교. 비교 구간에 거래가 없으면 null')
    ] = None
    points: Annotated[
        list[DaangnPricePoint],
        Field(description='월별 평균 (오래된 달부터). 거래가 없는 달은 빠진다')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평균의 한계, 평형·기간 안내. CLI 가 결과 위에 붙인다')
    ] = []


def _month_index(year_month: str) -> int:
    """'YYYYMM' 을 달 번호로 바꾼다 (달끼리 빼면 개월 수)."""
    return int(year_month[:4]) * 12 + int(year_month[4:6]) - 1


def _month_label(index: int) -> str:
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def _window_average(points: dict[int, tuple[float, int]], end: int) -> tuple[float, int] | None:
    """`end` 달까지 `PRICE_TREND_WINDOW_MONTHS` 개월의 거래 수 가중 평균 (만원)과 거래 수. 거래가 없으면 None."""
    window = [points[index] for index in range(end - PRICE_TREND_WINDOW_MONTHS + 1, end + 1) if index in points]
    count = sum(transactions for _, transactions in window)
    if count == 0:
        return None
    return round(sum(average * transactions for average, transactions in window) / count, 1), count


def get_price_trend(
    client: DaangnClient,
    complex_id: int,
    *,
    trade_type: str = '매매',
    area_group: int | None = None,
    years: int = 3,
    today: date | None = None,
) -> DaangnPriceTrendResult:
    """단지의 월별 평균 실거래가와 변화율을 받는다 (`complexByOriginalId.complex.priceChart`, 요청 1회).

    당근 웹 시세 그래프와 같은 데이터로, 매매·전세만 있다. 당근은 15년치를 원 단위로 주므로 만원으로
    바꾸고 오늘(`today`, 기본 한국 시간 오늘)부터 `years` 년 안의 달만 `points` 로 준다. 변화율(`summary`)은 마지막
    거래 달까지 3개월과 그 `years` 년 전 3개월을 각각 거래 수로 가중 평균해 비교한다. `area_group` 은
    `real-price --area` 와 같은 전용면적 묶음이고, 없으면 전 평형 평균이다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND, 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 시세 차트 쿼리를 바꿨을 때.
    """
    buy = trade_type == '매매'
    response = client.run_request_complex_price_chart(
        DaangnComplexPriceChartRequestPayloadModel(
            original_id=str(complex_id),
            chart_trade_types=[PRICE_CHART_TRADE_BY_TRADE_TYPE[trade_type]],
            exclude_monthly_rent=not buy,
            exclusive_use_area=(
                DaangnExclusiveUseAreaModel(min=area_group, max=area_group + 1) if area_group is not None else None
            ),
        )
    )
    result = unwrap_graphql(response, response.data.complex_by_original_id if response.data else None, '시세 차트')
    if result.complex is None:
        raise complex_not_found(complex_id)

    monthly: dict[int, tuple[float, int]] = {}
    for point in result.complex.price_chart.average_points if result.complex.price_chart else []:
        average = won_to_manwon(point.average_amount)
        # 평균 0(또는 500원 미만이라 0.0만원)은 실제 거래가가 아니라 빈 값으로 본다. 넣으면 구간 평균이 끌려 내려가고,
        # 비교 구간이 이런 달뿐이면 변화율에서 0 으로 나눈다 (실제 응답에서는 아직 보지 못한 방어 코드)
        if average and point.transaction_count:
            monthly[_month_index(point.year_month)] = (average, point.transaction_count)

    # 실거래 달은 한국 날짜라 컴퓨터 시간대와 상관없이 한국 시간으로 센다 (UTC 컴퓨터는 매달 1일 0~9시에 지난달이 된다)
    today = today or datetime.now(KST).date()
    this_month = today.year * 12 + today.month - 1
    start = this_month - years * 12 + 1
    shown = sorted(index for index in monthly if index >= start)
    points = [
        DaangnPricePoint(year_month=_month_label(index), average_manwon=monthly[index][0], transaction_count=monthly[index][1])
        for index in shown
    ]

    notes: list[str] = []
    if area_group is None:
        notes.append('평형을 정하지 않아 모든 평형을 섞은 평균입니다. 평형마다 보려면 complex 결과의 pyeongs[].area_group 을 --area 로 주세요')
    summary = None
    if not shown:
        notes.append(f'최근 {years}년 동안 이 조건의 {trade_type} 실거래가 없습니다')
    else:
        latest = shown[-1]
        recent = _window_average(monthly, latest)
        base_end = latest - years * 12
        base = _window_average(monthly, base_end)
        window = PRICE_TREND_WINDOW_MONTHS - 1
        if recent is not None and base is not None:
            summary = DaangnPriceTrendSummary(
                recent_period=f'{_month_label(latest - window)}~{_month_label(latest)}',
                recent_average_manwon=recent[0],
                recent_transactions=recent[1],
                base_period=f'{_month_label(base_end - window)}~{_month_label(base_end)}',
                base_average_manwon=base[0],
                base_transactions=base[1],
                change_percent=round((recent[0] / base[0] - 1) * 100, 1),
            )
            if min(recent[1], base[1]) < PRICE_TREND_FEW_TRANSACTIONS:
                notes.append(
                    f'비교 구간 거래가 적어(최근 {recent[1]}건, {years}년 전 {base[1]}건) 변화율이 실제 시세 변화와 '
                    '크게 다를 수 있습니다. points 의 흐름을 함께 보세요'
                )
        else:
            notes.append(
                f'{_month_label(base_end - window)}~{_month_label(base_end)} 에 거래가 없어 {years}년 전 대비 변화율을 내지 못했습니다'
            )
        if this_month - latest >= PRICE_TREND_STALE_MONTHS:
            notes.append(f'마지막 거래가 {_month_label(latest)} 에 있어 최근 시세와 다를 수 있습니다')
        notes.append('월별 평균은 그 달 실거래 평균이라 거래가 적은 달(transaction_count)은 튈 수 있습니다')
    return DaangnPriceTrendResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        area_group=area_group,
        years=years,
        total_transactions=sum(monthly[index][1] for index in shown),
        summary=summary,
        points=points,
        url=complex_url(complex_id),
        notes=notes,
    )


def get_listing_real_prices(
    client: DaangnClient,
    original_id: int,
    *,
    trade_type: str = '매매',
    limit: int = 120,
    years: int | None = None,
    today: date | None = None,
) -> DaangnListingRealPriceResult:
    """매물이 있는 건물(단지)의 비슷한 면적 실거래가를 최근 계약 순으로 모은다 (`_collect_transactions`).

    `years` 는 `get_real_prices` 와 같다. 당근이 매물의 건물을 찾은 경우에만 거래가 온다. 오피스텔·아파트는 대개 있고 빌라·주택은 대부분
    없어, 없으면 그 이유를 `notes` 로 알린다.

    Raises:
        ListingUnavailableError: 없거나 지워진 매물.
        JibsaError: 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래가 쿼리를 바꿨을 때.
    """
    buy = trade_type == '매매'

    def fetch(size: int, after: str | None) -> DaangnComplexTransactionsModel:
        response = client.run_request_article_by_original_article_id(
            DaangnArticleByOriginalArticleIdRequestPayloadModel(
                article_id=str(original_id),
                buy_first=size if buy else 1,
                buy_after=after if buy else None,
                borrow_first=1 if buy else size,
                borrow_after=None if buy else after,
            )
        )
        if any((error.extensions or {}).get('code') == 'recordNotFound' for error in response.errors):
            raise ListingUnavailableError('daangn', original_id)
        return unwrap_graphql(
            response,
            response.data.article_by_original_article_id if response.data else None,
            '매물 실거래가',
        )

    since = years_ago(today or datetime.now(KST).date(), years) if years is not None else None
    collected, has_more, notes = _collect_transactions(
        fetch, trade_type, limit,
        more_note=f'더 오래된 거래가 남아 있습니다. 당근에서 직접 확인해 주세요: {article_url(original_id)}',
        since=since,
    )
    if not collected:
        notes.append(
            f'이 매물 건물의 {trade_type} 실거래가 없습니다. 당근이 매물의 건물을 찾은 경우(오피스텔·아파트 등)에만 '
            '나오며 빌라·주택은 대부분 없습니다. 주변 시세는 daangn search listings 의 비슷한 매물로 비교하세요'
        )
    return DaangnListingRealPriceResult(
        listing_id=str(original_id),
        trade_type=trade_type,
        returned=len(collected),
        has_more=has_more,
        since=since,
        transactions=[transaction_to_real_price(node, trade_type) for node in collected],
        url=article_url(original_id),
        notes=notes,
    )


class DaangnRegionRealPrice(BaseModel):
    """지역 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형·피드에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]
    new_high: Annotated[
        bool,
        Field(exclude=True, description='신고가 피드인지. 이전 최고가 필드를 고르는 데만 쓴다')
    ] = False

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    published_at: Annotated[
        str | None,
        Field(description='실거래가 공개된 날 (YYYY-MM-DD). 신고가 피드에는 없다')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물·단지 이름')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='당근 단지 ID (daangn complex·real-price 에 넘긴다). 당근 단지가 아니면 키가 없다')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신 계약 (전월세만). 당근이 계약 종류를 주지 않으면 null')
    ] = None
    previous_high_manwon: Annotated[
        float | None,
        Field(description='이전 최고가 (만원, 신고가만)')
    ] = None
    previous_high_date: Annotated[
        str | None,
        Field(description='이전 최고가 계약일 (YYYY-MM-DD, 신고가만)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('renewal')
        else:
            fields |= {'cancelled', 'deal_type'}
        if self.new_high:
            fields.add('published_at')
        else:
            fields |= {'previous_high_manwon', 'previous_high_date'}
        if self.complex_id is None:
            fields.add('complex_id')
        for field in fields:
            data.pop(field, None)
        return data


class DaangnRegionRealPriceResult(BaseModel):
    """동·구의 최근 실거래 또는 신고가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    new_high: Annotated[
        bool,
        Field(description='신고가 매매만 모았는지')
    ]
    sort: Annotated[
        str,
        Field(description='최신 (최근 공개 순) / 가격 (가격 높은 순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 있는지')
    ]
    transactions: Annotated[
        list[DaangnRegionRealPrice],
        Field(description='실거래')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='지역을 고른 방법, 넘겨 본 범위 안내. CLI 가 결과 위에 붙인다')
    ] = []


def realsale_to_real_price(item: DaangnRealsaleFeedItemModel, trade_type: str, new_high: bool) -> DaangnRegionRealPrice:
    """지역 피드 한 칸을 `DaangnRegionRealPrice` 로 바꾼다. 금액은 원래 만원이다."""
    realsale = item.realsale
    assert realsale is not None
    danji = item.danji
    insight = item.price_insight
    buy = trade_type == '매매'
    return DaangnRegionRealPrice(
        trade_type=trade_type,
        new_high=new_high,
        trade_date=normalize_date(realsale.contact_date),
        published_at=normalize_date(item.data_date),
        address=normalize_address(item.region_name),
        building_name=(danji.name if danji else None) or (item.complex.name if item.complex else None),
        complex_id=item.complex.original_id if item.complex else None,
        households=danji.households if danji else None,
        approved_at=normalize_date(danji.build_date) if danji else None,
        area_m2=realsale.exclusive_area,
        floor=normalize_floor(realsale.floor),
        price_manwon=realsale.trade_price if buy else None,
        deposit_manwon=None if buy else realsale.deposit,
        rent_manwon=realsale.month_rent_fee if trade_type == '월세' else None,
        cancelled=realsale.cancel if buy else None,
        deal_type=(
            {'DIRECT': '직거래', 'BROKERED': '중개거래'}.get(realsale.transaction_type or '', realsale.transaction_type)
            if buy else None
        ),
        renewal=None if buy else _renewal(realsale.lease_contract_type, None),
        previous_high_manwon=insight.previous_max_price if new_high and insight else None,
        previous_high_date=normalize_date(insight.previous_max_contact_date) if new_high and insight else None,
    )


def _realsale_matches(item: DaangnRealsaleFeedItemModel, trade_type: str) -> bool:
    """고를 거래인지. 매매·전월세는 서버가 `tradeType` 으로 거르고 신고가는 매매만 오므로 거래 종류는 다시 보지 않는다.

    서버가 섞어 주는 전월세에서 전세·월세만 직접 가른다 (2026-10-11 실측: SALE 피드 172건·BORROW 피드 293건 모두 요청한 종류).
    """
    realsale = item.realsale
    if realsale is None:
        return False
    if trade_type == '매매':
        return True
    monthly = (realsale.month_rent_fee or 0) > 0
    return monthly if trade_type == '월세' else not monthly


def get_region_real_prices(
    client: DaangnClient,
    query: str,
    *,
    city: str | None = None,
    trade_type: str = '매매',
    new_high: bool = False,
    sort: str = '최신',
    limit: int = 120,
) -> DaangnRegionRealPriceResult:
    """동·구의 최근 실거래(`realsaleFeed`) 또는 신고가 매매(`realsaleNewHighFeed`)를 모은다.

    당근은 전월세를 섞어 주므로 전세·월세는 50건씩 최근 1200건까지 넘겨 보며 고른다 (`_collect_pages`).
    신고가는 매매만이고 웹처럼 가격 높은 순이다.

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        JibsaError: GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래 쿼리를 바꿨을 때.
    """
    region, notes = resolve_realsale_region(client, query, city=city, sejong_whole=True)
    buy = trade_type == '매매'

    def fetch(count: int, cursor: str | None) -> DaangnRealsaleFeedModel:
        if new_high:
            response = client.run_request_realsale_new_high_feed(
                DaangnRealsaleNewHighFeedRequestPayloadModel(
                    count=count,
                    cursor=cursor,
                    input=DaangnRealsaleNewHighFeedInputModel(region_id=region.region_id),
                )
            )
            return unwrap_graphql(
                response, response.data.realsale_new_high_feed if response.data else None, '신고가'
            )
        feed_response = client.run_request_realsale_feed(
            DaangnRealsaleFeedRequestPayloadModel(
                count=count,
                cursor=cursor,
                input=DaangnRealsaleFeedInputModel(
                    region_id=region.region_id,
                    trade_type='SALE' if buy else 'BORROW',
                    sort=REALSALE_SORT_BY_LABEL[sort],
                ),
            )
        )
        return unwrap_graphql(feed_response, feed_response.data.realsale_feed if feed_response.data else None, '지역 실거래')

    def page(count: int, cursor: str | None) -> tuple[list[DaangnRealsaleFeedItemModel], DaangnPageInfoModel | None]:
        feed = fetch(count, cursor)
        return [edge.node for edge in feed.edges if edge.node], feed.page_info

    collected, has_more, page_notes = _collect_pages(
        page, lambda item: _realsale_matches(item, trade_type), trade_type, limit,
        more_note='추가 거래가 남아 있습니다. 당근에서 직접 확인해 주세요: https://realty.daangn.com/',
    )
    notes += page_notes
    return DaangnRegionRealPriceResult(
        region=region,
        trade_type=trade_type,
        new_high=new_high,
        sort='가격' if new_high else sort,
        returned=len(collected),
        has_more=has_more,
        transactions=[_with_town(realsale_to_real_price(item, trade_type, new_high), region) for item in collected],
        notes=notes,
    )


def _with_town(price: DaangnRegionRealPrice, region: DaangnRealsaleRegion) -> DaangnRegionRealPrice:
    """읍·면으로 조회한 리 거래 주소에 그 읍·면을 넣는다.

    실거래 피드의 주소(`regionName`)는 리 앞의 읍·면을 빼고 준다 (2026-10-11 실측: 양평읍 → '경기 양평군 공흥리',
    조치원읍 → '세종 세종시 신안리'). 읍·면으로 조회했으면 그 읍·면 안의 리라 넣고, 군으로 조회했으면 리마다 어느 읍·면인지
    몰라 그대로 둔다.
    """
    words = (price.address or '').split()
    if region.level != '동' or not region.name3.endswith(('읍', '면')) or not words or region.name3 in words:
        return price
    if not words[-1].endswith('리'):
        return price
    return price.model_copy(update={'address': ' '.join([*words[:-1], region.name3, words[-1]])})
