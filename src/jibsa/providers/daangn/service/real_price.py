"""단지·매물·지역 실거래가와 시세 추이 (real-price, region-real-price, price-trend)."""

import logging
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

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.listing import (
    KST,
    NOT_APPLICABLE_PRICE_FIELDS,
    UPDATE_MAYBE_NEEDED,
    normalize_address,
    normalize_date,
    normalize_floor,
    note,
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
    DaangnRealsaleFeedSummaryRequestPayloadModel,
    DaangnRealsaleNewHighFeedInputModel,
    DaangnRealsaleNewHighFeedRequestPayloadModel,
    DaangnRealsaleSummaryInputModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnPageInfoModel,
    DaangnTransactionModel,
)
from jibsa.providers.daangn.api.response.real_price import (
    DaangnComplexTransactionsModel,
    DaangnPriceChartModel,
    DaangnRealsaleFeedItemModel,
    DaangnRealsaleFeedModel,
)
from jibsa.providers.daangn.service.common import (
    OPTIONAL_LOOKUP_ERRORS,
    T,
    article_url,
    complex_not_found,
    complex_url,
    cursor_stopped_note,
    next_cursor,
    partial_failure_note,
    stalled_page,
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.compare import (
    choose_pyeong,
    compare_column,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
)

from typing import (
    Annotated,
    Any,
    Generic,
    Literal,
    NamedTuple,
    cast,
)


logger = logging.getLogger(__name__)
RENT_TYPE_BY_TRADE_TYPE: dict[str, str] = {'전세': 'BORROW', '월세': 'MONTHLY'}
PRESALE_LABELS: dict[str, str] = {'PRE_SALE_RIGHT': '분양권', 'PRE_SALE_OWNER': '입주권'}
# 전월세 계약 종류 (서버 contractType·leaseContractType). 웹 배지(ComplexTopicPanel `pd`)는 RENEWAL 을 '재계약', 갱신요구권을 쓴
# 계약(useRenewalOfContractRight)을 '갱신' 으로 따로 보여 준다
CONTRACT_TYPE_LABELS: dict[str, str] = {'NEW': '신규', 'RENEWAL': '재계약'}
# '직전 최고가 대비' 비율의 소수 자릿수 (`previous_high_change_percent`). 웹 카드는 정수로 보여 준다
PREVIOUS_HIGH_PERCENT_DIGITS: int = 2
# 실거래 한 번에 받는 수와, 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건)
REAL_PRICE_PAGE_SIZE: int = 50
REAL_PRICE_MAX_PAGES: int = 24
# real-price·region-real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES
# 지역 실거래 피드 정렬. 웹 실거래 화면은 매매를 가격 순(`TRADE_PRICE_DESC`)으로만 부른다 (RealsaleFeedListQuery `Z`). 전월세는
# 웹에 없고 서버가 가격 순을 거절해 최신 순(`LATEST`)이다. 둘 다 서버 값이라 고르는 옵션은 두지 않는다 (2026-11-12 번들 대조)
REALSALE_SORT_BY_TRADE_TYPE: dict[str, str] = {'매매': 'TRADE_PRICE_DESC', '전세': 'LATEST', '월세': 'LATEST'}
REALSALE_SORT_LABEL_BY_SORT: dict[str, str] = {'TRADE_PRICE_DESC': '가격', 'LATEST': '최신'}
# 단지 시세 추이의 거래 유형 (라벨 → 당근 값). 차트는 매매·전세만 있다. 변화율은 웹처럼 기간의 첫 거래 달과 마지막 거래 달을
# 견주고(`get_price_trend`), 그 달의 거래가 적으면 `PRICE_TREND_FEW_TRANSACTIONS` 로 알린다
PRICE_CHART_TRADE_BY_TRADE_TYPE: dict[str, DaangnPriceChartTradeType] = {'매매': 'BUY', '전세': 'BORROW'}
# 시세 추이 기간: 당근 웹 시세 그래프의 탭 (1년·3년·전체, PriceChart `X`). 전체는 쿼리가 받는 15년(180개월)이다
PRICE_TREND_PERIODS: dict[str, int] = {'1년': 12, '3년': 36, '전체': 180}
# 웹 그래프 머리의 '최근 3개월 평균': 이번 달과 그 전 3개월 (4개 달)
PRICE_TREND_RECENT_MONTHS: int = 3
# 마지막 거래가 이만큼 지났으면 오래된 시세라고 알린다
PRICE_TREND_STALE_MONTHS: int = 6
# 비교하는 달의 거래가 이보다 적으면 변화율이 튈 수 있다고 알린다
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
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 배지 '재계약'). 재계약은 새 계약보다 낮게 잡히는 경우가 많다. 당근이 주지 않으면 null")
    ] = None
    renewal_right: Annotated[
        bool | None,
        Field(description="계약갱신요구권을 쓴 계약 (전월세만, 당근 웹 배지 '갱신'. 인상률 상한이 있어 시세보다 낮다). 당근이 주지 않으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields |= {'contract_type', 'renewal_right'}
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
    month: Annotated[
        str | None,
        Field(description='--month 로 준 계약 연월 (YYYY-MM). 그 달 거래만이다. 주지 않았으면 키가 없다')
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
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.unused_keys():
            data.pop(field, None)
        return data

    def unused_keys(self) -> list[str]:
        """해당 없음이라 출력에서 뺄 키. 결과마다 더할 키는 이 메서드를 넓힌다 (직렬화 함수를 복사하지 않는다)."""
        return [field for field in ('since', 'month') if getattr(self, field) is None]


class DaangnRealPriceResult(DaangnRealPriceBaseResult):
    """단지 실거래 내역."""

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (--area). null 이면 전체 평형. --pyeong 으로 골랐으면 키가 없다')
    ] = None
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (--pyeong 으로 고른 아파트형 단지 평형). 주지 않았으면 키가 없다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 그래프는 여기서 본다)')
    ]

    def unused_keys(self) -> list[str]:
        # 평형은 공급 평형(--pyeong)이나 전용면적 묶음(--area) 중 하나로 고른다. --pyeong 이면 area_group 이 null 로 남아 그
        # 설명('null 이면 전체 평형')대로 거르지 않은 것으로 읽혔다 (2026-11-12 리뷰·실측: 헬리오시티 --pyeong 32)
        return super().unused_keys() + ['pyeong' if self.pyeong is None else 'area_group']


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


def contract_type_of(contract_type: str | None) -> str | None:
    """전월세 계약 종류(서버 `contractType`·`leaseContractType`)를 한국어 라벨로. 모르는 값·없음은 None.

    웹 배지(ComplexTopicPanel `pd`)와 1:1 이다: `RENEWAL` → 재계약, 갱신요구권(`useRenewalOfContractRight`)은 따로
    `renewal_right` 로 낸다 (예전 `renewal` 은 둘을 합쳐 True 로 냈다, #215). 지역 실거래는 계약 종류 없이 오기도 하고, 같은
    거래가 단지 실거래에 NEW·RENEWAL 로 두 번 있기도 하다 (2026-10-10 실측: 봉천동·신림동 등 전월세 약 600건 중 14건이 계약
    종류 없음).
    """
    return CONTRACT_TYPE_LABELS.get(contract_type or '')


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
        contract_type=None if buy else contract_type_of(node.contract_type),
        renewal_right=None if buy else node.use_renewal_of_contract_right,
    )


TransactionFetch = Callable[[int, str | None], DaangnComplexTransactionsModel]
# (받을 수, 커서) → (한 페이지의 거래, 페이지 정보)
PageFetch = Callable[[int, str | None], tuple[list[T], DaangnPageInfoModel | None]]


class _Collected(NamedTuple, Generic[T]):
    """`_collect_pages` 가 모은 실거래와, 거래가 없을 때 그 까닭을 가를 값."""

    items: list[T]
    has_more: bool
    notes: list[str]
    # 기간(since) 시작일 앞의 거래가 나와 멈췄는지. 그렇다면 기간 앞에는 거래가 있다
    reached_since: bool
    # 받은 원본 거래 수 (기간·거래 유형으로 고르기 전)
    scanned: int


def _collect_pages(
    fetch: PageFetch[T],
    matches: Callable[[T], bool],
    trade_type: str,
    limit: int,
    *,
    url: str,
    remaining: str = '더 오래된 거래가 남아 있습니다',
    since: str | None = None,
    date_of: Callable[[T], str | None] | None = None,
) -> _Collected[T]:
    """실거래를 받은 순서(최근 순)대로 `limit` 건까지 모은다. 단지·매물 실거래와 지역 실거래가 함께 쓴다.

    매매는 필요한 만큼만 받고, 전세·월세는 당근이 전월세를 섞어 주므로 50건씩 최근 1200건까지 넘겨 보며
    `matches` 로 고른다. 커서가 반복되거나 다음 페이지가 비면 안내하고 멈춘다.

    Args:
        fetch: (받을 수, 커서) → (한 페이지의 거래, 페이지 정보).
        matches: 검색한 거래 유형의 거래인지.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        url: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때 확인하라고 안내할 당근 페이지.
        remaining: 그 안내의 앞말 (예: '더 오래된 거래가 남아 있습니다'). `since` 의 기간 시작일에 닿기 전에 멈췄으면 쓰지
            않고 받지 못한 기간을 알린다.
        since: 이날(YYYY-MM-DD)보다 앞선 거래는 빼고, 그런 거래가 나온 페이지에서 멈춘다. 당근은 기간을 받지 않아
            최근 계약 순으로 넘기다 멈춘다 (계약 순으로 오는 단지·매물 실거래만 준다). 날짜를 모르는 거래는 남긴다.
        date_of: `since` 와 견줄 거래의 계약일.

    Returns:
        거래, 더 있는지, 안내와 함께 기간 시작일 앞에서 멈췄는지·받은 원본 거래 수 (`_Collected`). 뒤의 둘은 빈 결과의
        까닭을 가르는 데 쓴다 (`_empty_result_note`).
    """
    buy = trade_type == '매매'
    collected: list[T] = []
    after = None
    has_more = False
    # 마지막으로 받은 쪽에서 서버가 다음 쪽이 있다고 했는지. 기간(since) 밖에서 멈췄으면 남은 거래는 찾는 거래가 아니라 False
    server_more = False
    # 기간(since) 시작일 앞의 거래가 나와 멈췄는지, 마지막으로 센 쪽의 가장 오래된 계약일 (기간을 다 받지 못했을 때 알린다)
    reached_since = False
    oldest: str | None = None
    scanned = 0
    pages = 0
    notes: list[str] = []
    for pages in range(1, REAL_PRICE_MAX_PAGES + 1):
        size = min(REAL_PRICE_PAGE_SIZE, limit - len(collected)) if buy else REAL_PRICE_PAGE_SIZE
        nodes, page_info = fetch(size, after)
        server_more = bool(page_info and page_info.has_next_page)
        # 커서가 되풀이되거나 페이지 정보가 없으면(stalled_page) 그 쪽을 세기 전에 멈춘다. 거래에는 ID 가 없어 단지 목록처럼 같은 쪽을 걸러 낼 수 없다. 아래
        # next_cursor 도 되풀이를 보지만 그때는 이미 그 쪽을 센 뒤라 여기서 먼저 본다 (2026-11-10 리뷰가 두 검사가 겹친다고
        # 했으나, 실제 응답의 커서만 되풀이되게 바꿔 보니 늘 이 검사에서 걸려 거래 수에 다시 더해지지 않았다. next_cursor 는
        # 단지 후보·지역 단지와 함께 쓰는 도우미라 되풀이 검사를 빼지 않는다).
        # 멈춘 까닭은 [참고] 이고, 더 있다는 [일부] 는 함수 끝의 안내 하나에만 붙인다 (아래 멈춤 안내도 같다).
        # 서버가 다음 쪽이 없다고 했으면 되풀이로 보지 않고 마지막 쪽으로 받는다. 보면 끝난 목록을 '다음 페이지가 있다고 하면서'
        # 멈췄다고 하고 has_more 를 true 로 냈으며 마지막 쪽 거래도 뺐다 (2026-11-10 리뷰·실측: 역삼IPARK 10699288 매매 474건의
        # 마지막 10쪽 커서만 요청 커서로 바꾸니 450건·has_more true. 실제 응답은 50건씩·79건씩 모두 마지막 쪽이 hasNextPage
        # false 에 새 커서였고, 끝 뒤를 요청하면 edges 0·endCursor null 이었다)
        if stalled_page(page_info, after):
            has_more = True
            notes.append(note('참고', cursor_stopped_note('실거래', f'{scanned}건')))
            break
        scanned += len(nodes)
        if date_of is not None and nodes:
            oldest = date_of(nodes[-1]) or oldest
        kept = nodes
        if since is not None and date_of is not None:
            kept = [node for node in nodes if (day := date_of(node)) is None or day >= since]
        collected += [node for node in kept if matches(node)]
        has_more = server_more or len(collected) > limit
        if len(kept) < len(nodes):
            # 최근 계약 순이라 기간보다 앞선 거래가 나오면 그 뒤도 모두 기간 밖이다. 3년치를 보려고 --limit 1200 으로 전부 받으면
            # 2018년 거래까지 938건(약 5만 토큰)이 왔다 (2026-10-31 에이전트 검증, 헬리오시티 84㎡ 매매. 3년 안은 452건)
            has_more = len(collected) > limit
            server_more = False
            reached_since = True
            break
        if len(collected) >= limit or not has_more or page_info is None:
            break
        cursor = next_cursor(page_info, after, received=len(nodes))
        if cursor is None:
            notes.append(note('참고', cursor_stopped_note('실거래', f'{scanned}건')))
            break
        after = cursor

    if not buy and has_more and len(collected) < limit:
        # 몇 건 중에서 골랐는지 설명이라 [참고] 다. 당근 사이트로 가라는 말은 아래 [일부] 안내 하나에만 둔다 (2026-11-10 리뷰·
        # 실측: 헬리오시티 월세 --limit 1200 에 이 안내의 '더 오래된 거래는 당근 사이트에서 확인하세요' 와 [일부] 의 '당근에서
        # 직접 확인하세요: URL' 이 함께 나왔다. 커서가 멈추면 멈춤 안내의 '나머지는 당근에서 확인하세요' 까지 세 번이었다)
        notes.append(note('참고', f'최근 전월세 실거래 {scanned}건 중 {trade_type} {len(collected)}건입니다'))
    site = f'당근에서 직접 확인하세요: {url}'
    if since is not None and not reached_since:
        # 기간 시작일에 닿기 전에 멈췄으면(24쪽 상한·--limit 최대값·쪽 멈춤) 남은 거래는 기간 안이다. '더 오래된 거래가 남아
        # 있습니다' 는 기간보다 오래된 거래로 읽혀, 에이전트가 2026-01-10 까지 받은 결과를 '최근 1년' 이라고 전했다 (2026-11-11
        # LLM 사용 시험: 헬리오시티 10667600 월세 --years 1 --limit 1200 은 2026-01-10 까지 756건)
        more_note = (
            f'요청한 기간({since}부터) 중 {oldest} 이전 거래는 받지 못했습니다. {site}' if oldest
            else f'요청한 기간({since}부터)의 거래를 다 받지 못했습니다. {site}'
        )
    else:
        more_note = f'{remaining}. {site}'
    # 받은 거래를 --limit 으로 잘랐으면 이 안내가 '더 있다' 와 '--limit 을 늘리라' 를 함께 말한다. 그때 아래 '--limit 을 늘리면'
    # 안내를 또 붙이면 [일부] 가 둘이 된다 (2026-11-10 실측: 헬리오시티 월세 --limit 3 에 '32건 중 3건만' 과 '거래가 더 남아 있습니다')
    truncated = truncation_notes(len(collected), limit, subject='실거래', max_limit=REAL_PRICE_MAX_LIMIT)
    notes += truncated
    # 아래 두 분기의 조건을 '늘릴 수 있는지' 하나로 모으지 않는다. 잘랐으면 `truncation_notes` 가 이미 --limit 을 늘리라고 해서
    # 사이트 안내를 덧붙일지만 정하고, 안 잘랐으면 늘리라는 안내와 사이트 안내 중 하나를 고른다. 묻는 것이 달라 조건도 다르다.
    # `server_more` 는 서버가 다음 쪽이 있다고 했는지만 담아(기간 밖에서 멈추면 False) 24쪽 뒤에 남았는지 보는 데 쓰고,
    # `has_more` 는 --limit 을 넘겨 받았거나 쪽이 멈춘 것도 더 있다고 본다 (2026-11-11 리뷰·실측: 헬리오시티 10667600 매매
    # --limit 3 은 '--limit 을 늘리면', 월세 --limit 3 은 '35건 중 3건만 … 늘리세요' 로 둘 다 맞았다)
    if truncated:
        # 잘랐어도 24쪽까지 보고 서버에 거래가 남았거나 --limit 이 이미 최대값이면, --limit 을 늘려도 받지 못하는 거래가 남아
        # 사이트 안내도 붙인다 (2026-11-10 리뷰·실측: 헬리오시티 월세는 23쪽까지 727건·24쪽 755건이라 --limit 728~754 가
        # 24쪽째에서 잘린다. 늘리라는 안내만 따르면 24쪽을 다시 받고 27건을 더 받은 뒤에야 사이트 안내를 봤다)
        if (pages >= REAL_PRICE_MAX_PAGES and server_more) or limit >= REAL_PRICE_MAX_LIMIT:
            notes.append(note('일부', more_note))
    elif has_more:
        if len(collected) >= limit and pages < REAL_PRICE_MAX_PAGES and limit < REAL_PRICE_MAX_LIMIT:
            # --limit 에서 멈췄으면 늘려서 더 받을 수 있다. 사이트에서 보라는 안내는 페이지 상한까지 보고도 남았거나 --limit 이
            # 이미 최대값일 때만 맞다 (2026-10-11 실측: 헬리오시티 --limit 3 에도 '당근에서 직접 확인' 이 붙었다). 최대값이면
            # 늘리라고 하지 않는다. 서버가 요청보다 많이 주면 24쪽 전에 1200건이 차서, 늘리면 INVALID_ARGUMENT 인데 늘리라고
            # 했다 (2026-11-11 리뷰. 요청한 만큼 주면 1200건은 24쪽째라 아래 사이트 안내로 간다)
            notes.append(note('일부', f'거래가 더 남아 있습니다. --limit 을 늘리면 (최대 {REAL_PRICE_MAX_LIMIT}건) 더 받습니다'))
        else:
            notes.append(note('일부', more_note))
    return _Collected(collected[:limit], has_more, notes, reached_since, scanned)


def _collect_transactions(
    fetch: TransactionFetch,
    trade_type: str,
    limit: int,
    *,
    url: str,
    since: str | None = None,
    remaining: str = '더 오래된 거래가 남아 있습니다',
) -> _Collected[DaangnTransactionModel]:
    """단지·매물 실거래를 최근 계약 순으로 `limit` 건까지 모은다 (`_collect_pages`).

    Args:
        fetch: (받을 수, 커서) → 단지·매물의 실거래 연결. 매매면 매매 연결의, 아니면 전월세 연결의 크기·커서다.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        url: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때 확인하라고 안내할 당근 페이지.
        since: 이날(YYYY-MM-DD)부터의 계약만 받는다 (`--years`).
        remaining: 남은 거래 안내의 앞말 (`_collect_pages`). 한 달만 받으면 '더 오래된' 이 아니라 그 달 거래가 남았다고 한다.

    Returns:
        모은 거래와 안내 (`_collect_pages`).
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
        url=url,
        remaining=remaining,
        since=since,
        date_of=_trade_date,
    )


def _empty_result_note(found: _Collected[DaangnTransactionModel], trade_type: str, since: str | None) -> str | None:
    """받은 단지·매물 실거래가 없을 때, 거래가 있는데 요청 범위 밖이라 비었다면 그 까닭. 아니면 None.

    거래가 더 남았으면(`has_more`) 남았다는 [일부] 안내가 이미 있어 None 이다. 기간(`since`) 시작일 앞의 거래가 나와 멈췄으면
    기간 앞에는 거래가 있다고, 전월세 거래는 있는데 고른 유형(전세·월세)이 없으면 그 수를 알린다. 빈 결과를 '거래가 없다' 로만
    알리면 기간 앞이나 다른 유형에 있는 거래까지 없다고 읽힌다 (2026-11-13 리뷰·실측: 마지막 거래가 2026-03-23 인 매물
    3116252 를 오늘 2027-06-01 기준 --years 1 로 보니 '이 매물 건물의 매매 실거래가 없습니다 … 빌라·주택은 대부분 없습니다' 였다).
    """
    if found.items or found.has_more:
        return None
    if found.reached_since:
        kind = '매매' if trade_type == '매매' else '전월세'
        return note(
            '참고',
            f'요청한 기간({since}부터) 안 {trade_type} 실거래가 없습니다. 그보다 앞선 {kind} 거래는 있어 --years 를 늘리거나 '
            '빼면 그 앞 거래까지 찾습니다',
        )
    if trade_type != '매매' and found.scanned:
        # 기간 앞에서 멈추지 않았고 남은 거래도 없으니 받은 전월세가 그 조건(평형·--month·--years)의 전부다
        return note('참고', f'당근이 준 전월세 실거래 {found.scanned}건 중 {trade_type} 거래는 0건입니다')
    return None


def get_real_prices(
    client: DaangnClient,
    complex_id: int,
    *,
    trade_type: str = '매매',
    area_group: int | None = None,
    pyeong: int | None = None,
    limit: int = 120,
    years: int | None = None,
    month: str | None = None,
    today: date | None = None,
) -> DaangnRealPriceResult:
    """단지 실거래가를 최근 계약 순으로 `limit` 건까지 모은다 (`_collect_transactions`).

    `years` 를 주면 그 햇수 전 오늘(한국 날짜)부터의 계약만 받고 그보다 앞선 거래가 나오면 멈춘다. `month`(YYYY-MM)를 주면
    웹 시세 그래프에서 달을 눌렀을 때처럼 그 달 계약만 서버에 묻는다 (`tradeYearMonth`, 2026-11-12 실측: 역삼래미안 202608 →
    8월 계약 3건). 둘은 함께 쓰지 않는다 (CLI 가 막는다). 평형을 주지 않으면 모든
    평형이다 (거래마다 면적이 있어 섞여도 헷갈리지 않고, 웹처럼 평형마다 따로 부르지 않아도 된다. 2026-11-12 사용자 결정).
    `pyeong` 은 당근 웹처럼 아파트형 단지의 공급 평형 묶음이고 그 평형 타입 코드(ptpCds)로 거른다 (단지 비교 칸 요청 1회 더).
    웹은 `exclusiveUseAreaGroup: 84` 같은 전용면적 묶음을 아파트형에 쓰지 않아 jibsa 도 막는다. 84㎡ 묶음은 32평·33평이 섞여
    웹의 32평 목록과 달랐다 (2026-11-12 실측: 헬리오시티 매매 50건 중 28건이 33평, #215). `area_group` 은 아파트형이 아닌 단지의
    전용면적 묶음이다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND, 아파트형 단지에 `area_group` 을 주거나 단지에 없는 평형·묶음이면 INVALID_ARGUMENT,
            그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래가 쿼리를 바꿨을 때.
    """
    buy = trade_type == '매매'
    # 평형·묶음을 줬을 때만 단지 비교 칸(요청 1회)으로 평형 타입 코드를 받고 웹처럼 아파트형에 전용 묶음을 막는다 (`choose_pyeong`)
    choice = (
        choose_pyeong(compare_column(client, complex_id), pyeong=pyeong, area_group=area_group)
        if pyeong is not None or area_group is not None else None
    )

    def fetch(size: int, after: str | None) -> DaangnComplexTransactionsModel:
        response = client.run_request_complex_by_original_id(
            DaangnComplexByOriginalIdRequestPayloadModel(
                complex_id=str(complex_id),
                buy_first=size if buy else 1,
                buy_after=after if buy else None,
                borrow_first=1 if buy else size,
                borrow_after=None if buy else after,
                exclusive_use_area_group=area_group,
                ptp_cds=choice.ptp_cds if choice else None,
                trade_year_month=month.replace('-', '') if month else None,
            )
        )
        result = unwrap_graphql(
            response, response.data.complex_by_original_id if response.data else None, '실거래가'
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        return result.complex

    since = years_ago(today or datetime.now(KST).date(), years) if years is not None else None
    found = _collect_transactions(
        fetch, trade_type, limit,
        url=complex_url(complex_id),
        since=since,
        remaining=f'{month} 의 거래가 더 남아 있습니다' if month else '더 오래된 거래가 남아 있습니다',
    )
    notes = found.notes
    # 단지 실거래는 빈 결과에 '없다' 고 단정하지 않지만, 기간 앞·다른 유형에 거래가 있으면 매물 실거래처럼 알린다
    if (empty := _empty_result_note(found, trade_type, since)) is not None:
        notes.append(empty)
    return DaangnRealPriceResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        area_group=area_group,
        pyeong=pyeong,
        returned=len(found.items),
        has_more=found.has_more,
        since=since,
        month=month,
        transactions=[transaction_to_real_price(node, trade_type) for node in found.items],
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
    """기간 안의 첫 거래 달과 마지막 거래 달 평균가 비교 (당근 웹 시세 그래프의 'N개월간 X% 상승' 과 같은 계산)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    start_month: Annotated[
        str,
        Field(description='기간 안 첫 거래 달 (YYYY-MM)')
    ]
    start_average_manwon: Annotated[
        float,
        Field(description='첫 거래 달 평균가 (만원)')
    ]
    end_month: Annotated[
        str,
        Field(description='기간 안 마지막 거래 달 (YYYY-MM)')
    ]
    end_average_manwon: Annotated[
        float,
        Field(description='마지막 거래 달 평균가 (만원)')
    ]
    months: Annotated[
        int,
        Field(description='두 달 사이 개월 수 (웹의 "N개월간"·"N년간")')
    ]
    change_percent: Annotated[
        float,
        Field(description='첫 거래 달 대비 마지막 거래 달 변화율 (%, 오르면 양수)')
    ]
    change_manwon: Annotated[
        float,
        Field(description='마지막 거래 달 평균가 - 첫 거래 달 평균가 (만원)')
    ]


class DaangnKbSale(BaseModel):
    """최근 KB 매매 시세 (만원, 당근 웹 시세 그래프의 KB 시세 띠). 이름은 단지 비교의 `DaangnKbRange` 와 맞췄다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    low_manwon: Annotated[
        float | None,
        Field(description='하위 평균가 (만원)')
    ] = None
    high_manwon: Annotated[
        float | None,
        Field(description='상위 평균가 (만원)')
    ] = None
    survey_date: Annotated[
        str | None,
        Field(description='KB 시세 조사 기준일 (YYYY-MM-DD)')
    ] = None


def kb_sale_of(chart: DaangnPriceChartModel | None) -> DaangnKbSale | None:
    """시세 그래프 응답의 `latestKbSale`(원)을 만원으로. 없으면 None (모름).

    웹은 KB 시세를 매매 그래프의 띠로만 그리지만 응답에는 전세 그래프에도 함께 와서 거래 유형과 상관없이 낸다. KB 월세·전세 시세는
    이 응답에 없다 (단지 비교 `compare` 의 `pyeong.kb_*` 에 있다).
    """
    kb = chart.latest_kb_sale if chart else None
    if kb is None:
        return None
    return DaangnKbSale(
        low_manwon=won_to_manwon(kb.lower),
        high_manwon=won_to_manwon(kb.upper),
        survey_date=normalize_date(kb.survey_base_date),
    )


class DaangnPriceTrendResult(BaseModel):
    """단지 시세 추이 (국토부 실거래 월별 평균, 당근 웹 단지 화면 시세 그래프)."""

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
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (아파트형 단지). 전용면적 묶음으로 봤거나 평형 묶음이 없는 단지면 키가 없다')
    ] = None
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (㎡). 공급 평형으로 봤거나 평형 묶음이 없는 단지면 키가 없다')
    ] = None
    period: Annotated[
        Literal['1년', '3년', '전체'],
        Field(description='points 기간이자 변화율을 보는 기간')
    ]
    recent_average_manwon: Annotated[
        float | None,
        Field(description='최근 3개월(이번 달과 그 전 3개월) 거래 수 가중 평균 (만원). 없으면 12개월 안 마지막 거래 달. 그것도 없으면 null')
    ] = None
    recent_transactions: Annotated[
        int | None,
        Field(description='recent_average_manwon 의 거래 수')
    ] = None
    kb_sale: Annotated[
        DaangnKbSale | None,
        Field(description='이 평형의 최근 KB 매매 시세 (하위~상위 평균가, 조사 기준일). 당근이 주지 않으면 null')
    ] = None
    total_transactions: Annotated[
        int,
        Field(description='points 기간의 거래 수')
    ]
    summary: Annotated[
        DaangnPriceTrendSummary | None,
        Field(description='기간 안 첫·마지막 거래 달 비교. 거래 달이 둘이 안 되면 null')
    ] = None
    points: Annotated[
        list[DaangnPricePoint],
        Field(description='월별 평균 (오래된 달부터). 거래가 없는 달은 빠진다. 평형 묶음이 없는 단지는 당근 웹처럼 그래프가 없어 []')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평균의 한계, 평형·기간 안내. CLI 가 결과 위에 붙인다')
    ] = []

    @model_serializer(mode='wrap')
    def drop_other_pyeong_kind(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 평형은 공급 평형이나 전용면적 묶음 중 하나로 고르므로 다른 쪽은 해당 없음이라 키를 뺀다. 평형 묶음이 없는 단지는 고른
        # 평형이 없어(그래프도 없다) 둘 다 뺀다
        data: dict[str, Any] = handler(self)
        for field in ('pyeong', 'area_group'):
            if data.get(field) is None:
                data.pop(field, None)
        return data


def _month_index(year_month: str) -> int:
    """'YYYYMM' 을 달 번호로 바꾼다 (달끼리 빼면 개월 수)."""
    return int(year_month[:4]) * 12 + int(year_month[4:6]) - 1


def _month_label(index: int) -> str:
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def _weighted(points: list[tuple[float, int]]) -> tuple[float, int] | None:
    count = sum(transactions for _, transactions in points)
    if count == 0:
        return None
    return round(sum(average * transactions for average, transactions in points) / count, 1), count


def get_price_trend(
    client: DaangnClient,
    complex_id: int,
    *,
    trade_type: str = '매매',
    pyeong: int | None = None,
    area_group: int | None = None,
    period: str = '1년',
    today: date | None = None,
) -> DaangnPriceTrendResult:
    """단지의 월별 평균 실거래가와 변화율을 당근 웹 단지 화면의 시세 그래프처럼 받는다 (요청 2회: 단지 비교 칸 → 시세 그래프).

    웹처럼 평형 하나로 본다. `pyeong`(아파트형의 공급 평형)·`area_group`(전용면적 묶음)이 없으면 웹이 처음 보여 주는 대표
    평형이다. 크기가 다른 평형을 섞은 평균은 큰 평형 거래가 몰린 달에 튀어 추이가 틀어져서, 예전의 '모든 평형 평균' 기본을
    바꿨다 (#215, 2026-11-12 사용자 결정). 고를 평형이 없는 단지(평형 묶음이 없거나 대표 묶음에 평형 값이 없다)는 웹처럼 그래프를
    받지 않고 빈 `points` 를 준다 (요청 1회). 기간은 웹 탭(1년·3년·전체)이고, 오늘(한국 날짜)이 든 달과 그 전 N개월의 거래 달을
    `points` 로 준다. 변화율은 웹(PriceChart `Z`)처럼 기간 안 첫 거래 달과 마지막 거래 달 평균을 견준다. 예전에는 마지막 거래 달
    까지 3개월과 N년 전 3개월을 가중 평균해 웹과 숫자가 달랐다 (2026-11-12 실측: 헬리오시티 32평 1년, 웹 -0.6%).

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND, 고를 수 없는 평형이면 INVALID_ARGUMENT, 그 밖의 GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 시세 그래프 쿼리를 바꿨을 때.
    """
    column = compare_column(client, complex_id)
    choice = choose_pyeong(column, pyeong=pyeong, area_group=area_group, representative=True)
    if choice is None:
        # 웹 단지 화면 가격 칸(ComplexTopicPanel)은 고른 평형(`k`)이 없으면 그래프를 그리지 않고 '아직 등록된 실거래가가 없어요'
        # 만 보여 준다 (`xe=…&&k!=null`). 예전에는 평형 거르기 없이 그래프를 받아 모든 평형을 섞은 평균을 냈다 (2026-11-12 번들 대조)
        return DaangnPriceTrendResult(
            complex_id=str(complex_id),
            trade_type=trade_type,
            period=cast(Literal['1년', '3년', '전체'], period),
            total_transactions=0,
            points=[],
            url=complex_url(complex_id),
            notes=[note(
                '참고',
                "당근에 이 단지 평형 묶음 정보가 없어 당근 웹도 시세 그래프 없이 '아직 등록된 실거래가가 없어요' 로 보여 줍니다",
            )],
        )
    if column.id is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message='당근 단지 비교 칸에 노드 ID 가 없어 시세 그래프를 받지 못했습니다',
            hint=f'응답 형식이 바뀌었을 수 있습니다. {UPDATE_MAYBE_NEEDED}',
        )
    group = choice.area_group if not choice.ptp_cds else None
    response = client.run_request_complex_price_chart(
        DaangnComplexPriceChartRequestPayloadModel(
            id=column.id,
            chart_trade_type=PRICE_CHART_TRADE_BY_TRADE_TYPE[trade_type],
            ptp_cds=choice.ptp_cds or None,
            exclusive_use_area_group=group,
            exclusive_use_area=DaangnExclusiveUseAreaModel(min=group, max=group + 1) if group is not None else None,
        )
    )
    node = unwrap_graphql(response, response.data.node if response.data else None, '시세 그래프')

    monthly: dict[int, tuple[float, int]] = {}
    for point in node.price_chart.average_points if node.price_chart else []:
        average = won_to_manwon(point.average_amount)
        # 평균 0(또는 500원 미만이라 0.0만원)은 실제 거래가가 아니라 빈 값으로 본다. 넣으면 변화율이 0 으로 나뉜다
        # (실제 응답에서는 아직 보지 못한 방어 코드)
        if average and point.transaction_count:
            monthly[_month_index(point.year_month)] = (average, point.transaction_count)

    # 실거래 달은 한국 날짜라 컴퓨터 시간대와 상관없이 한국 시간으로 센다 (UTC 컴퓨터는 매달 1일 0~9시에 지난달이 된다)
    today = today or datetime.now(KST).date()
    this_month = today.year * 12 + today.month - 1
    # 웹은 new Date(올해, 이번 달 - N, 1) 부터라 이번 달까지 N+1 개 달이다 (1년이면 작년 같은 달부터)
    shown = sorted(index for index in monthly if index >= this_month - PRICE_TREND_PERIODS[period])
    points = [
        DaangnPricePoint(year_month=_month_label(index), average_manwon=monthly[index][0], transaction_count=monthly[index][1])
        for index in shown
    ]
    recent = _weighted([value for index, value in monthly.items() if index >= this_month - PRICE_TREND_RECENT_MONTHS])
    if recent is None:
        last = max((index for index in monthly if index >= this_month - 12), default=None)
        recent = monthly[last] if last is not None else None

    notes: list[str] = []
    chosen = f'{choice.pyeong}평' if choice.pyeong is not None else f'{choice.area_group}㎡'
    if pyeong is None and area_group is None:
        option = '--pyeong (complex 의 pyeongs[].pyeong)' if choice.pyeong is not None else '--area (complex 의 pyeongs[].area_group)'
        # 단지 전체를 물었는데 웹 기본값으로 평형 하나만 본 것이라 [범위] 다 (search listings --university 의 기본 종류와 같다)
        notes.append(note('범위', f'평형을 정하지 않아 당근 웹처럼 대표 평형({chosen})으로 봅니다. 다른 평형은 {option} 으로 주세요'))
    summary = None
    if len(shown) < 2:
        # '전체' 탭은 15년(PRICE_TREND_PERIODS)이라 '최근 전체 동안' 이 되지 않게 기간을 풀어 쓴다
        span = f'전체 기간(최근 {PRICE_TREND_PERIODS[period] // 12}년)' if period == '전체' else f'최근 {period}'
        notes.append(note(
            '참고',
            f'{span} 동안 {chosen} {trade_type} 거래가 있는 달이 {len(shown)}개라 변화율을 내지 못했습니다 '
            '(당근 웹도 이 기간 탭을 막습니다)',
        ))
    else:
        first, last_index = shown[0], shown[-1]
        start, end = monthly[first], monthly[last_index]
        summary = DaangnPriceTrendSummary(
            start_month=_month_label(first),
            start_average_manwon=start[0],
            end_month=_month_label(last_index),
            end_average_manwon=end[0],
            months=last_index - first,
            change_percent=round((end[0] / start[0] - 1) * 100, 1),
            change_manwon=round(end[0] - start[0], 1),
        )
        if min(start[1], end[1]) < PRICE_TREND_FEW_TRANSACTIONS:
            notes.append(note(
                '참고',
                f'비교한 달의 거래가 적어({_month_label(first)} {start[1]}건, {_month_label(last_index)} {end[1]}건) 변화율이 실제 '
                '시세 변화와 크게 다를 수 있습니다. points 의 흐름을 함께 보세요',
            ))
    if shown and this_month - shown[-1] >= PRICE_TREND_STALE_MONTHS:
        notes.append(f'마지막 거래가 {_month_label(shown[-1])} 에 있어 최근 시세와 다를 수 있습니다')
    if shown:
        notes.append('월별 평균은 그 달 실거래 평균이라 거래가 적은 달(transaction_count)은 튈 수 있습니다')
    return DaangnPriceTrendResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        pyeong=choice.pyeong,
        area_group=choice.area_group,
        period=cast(Literal['1년', '3년', '전체'], period),
        recent_average_manwon=recent[0] if recent else None,
        recent_transactions=recent[1] if recent else None,
        kb_sale=kb_sale_of(node.price_chart),
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
    없어, 없으면 그 이유를 `notes` 로 알린다. 거래가 기간 앞이나 다른 유형(전세·월세)에만 있어 비었으면 그렇게 알린다.

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
    found = _collect_transactions(
        fetch, trade_type, limit,
        url=article_url(original_id),
        since=since,
    )
    notes = found.notes
    # 거래가 더 남았으면(페이지가 멈췄거나 전월세 1200건 안에 그 유형이 없음) 없다고 단정하지 않는다. 남았다는 [일부] 와
    # '최근 전월세 실거래 N건 중 전세 0건' [참고] 가 이미 알리는데, 같은 결과에 '없습니다' 가 붙으면 에이전트가 없다고 전한다
    # (2026-11-11 리뷰). 기간 앞이나 다른 유형에 거래가 있으면 그 까닭을 알리고(`_empty_result_note`), 거래를 하나도 받지
    # 못했을 때만 건물을 찾지 못한 경우를 알린다
    if (empty := _empty_result_note(found, trade_type, since)) is not None:
        notes.append(empty)
    elif not found.items and not found.has_more:
        notes.append(
            f'이 매물 건물의 {trade_type} 실거래가 없습니다. 당근이 매물의 건물을 찾은 경우(오피스텔·아파트 등)에만 '
            '나오며 빌라·주택은 대부분 없습니다. 주변 시세는 daangn search listings 의 비슷한 매물로 비교하세요'
        )
    return DaangnListingRealPriceResult(
        listing_id=str(original_id),
        trade_type=trade_type,
        returned=len(found.items),
        has_more=found.has_more,
        since=since,
        transactions=[transaction_to_real_price(node, trade_type) for node in found.items],
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
        Field(exclude=True, description='신고가 피드인지. 신고가 피드에 없는 published_at 키를 빼는 데만 쓴다')
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
        Field(description='신고 뒤 해제(취소)된 거래. 웹처럼 매매·전월세 모두 (전월세는 드물다)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 카드 배지 '갱신' 은 재계약이다). 당근이 주지 않으면 null. 갱신요구권 사용 여부는 지역 피드에 없다")
    ] = None
    is_new_high: Annotated[
        bool | None,
        Field(description="이 거래가 이 단지·평형의 신고가인지 (매매만, 당근 웹 카드의 '신고가' 배지. 해제된 거래는 false)")
    ] = None
    previous_high_manwon: Annotated[
        float | None,
        Field(description='직전 최고가 (만원, 매매만). 당근이 비교 자료를 주지 않으면 null')
    ] = None
    previous_high_date: Annotated[
        str | None,
        Field(description='직전 최고가 계약일 (YYYY-MM-DD, 매매만)')
    ] = None
    previous_high_change_percent: Annotated[
        float | None,
        Field(description="직전 최고가 대비 변화율 (%, 소수 둘째 자리, 매매만. 당근 웹 카드의 '직전 최고가 대비 ±N%' 와 같은 비율이고 웹은 정수로 보여 준다). 해제된 거래나 직전 최고가가 없으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('contract_type')
        else:
            # 거래 취소는 웹 카드가 거래 유형과 상관없이 보여 준다 (`yc` 의 `s.cancel===!0`). 직거래 표시와 신고가·직전 최고가는
            # 매매에만 둔다 (웹 카드도 SALE 에만 계산한다)
            fields |= {'deal_type', 'is_new_high', 'previous_high_manwon', 'previous_high_date', 'previous_high_change_percent'}
        if self.new_high:
            fields.add('published_at')
        if self.complex_id is None:
            fields.add('complex_id')
        for field in fields:
            data.pop(field, None)
        return data


class DaangnRealsaleSummary(BaseModel):
    """지역 실거래 화면 머리의 요약 (웹 'MM월 DD일 매매 N건 · 신고가 N건')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    data_date: Annotated[
        str | None,
        Field(description='가장 최근 공개일 (YYYY-MM-DD)')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='그 공개일의 매매 거래 수')
    ] = None
    new_high_count: Annotated[
        int | None,
        Field(description='그 공개일의 신고가 수')
    ] = None


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
        Field(description='가격 (매매·신고가: 최근 공개일부터, 같은 날 안에서 가격 높은 순. 당근 웹과 같다) / 최신 (전세·월세: 최근 공개 순)')
    ]
    summary: Annotated[
        DaangnRealsaleSummary | None,
        Field(description='가장 최근 공개일과 그날의 매매·신고가 수 (웹 실거래 화면 머리). 받지 못하면 null 이고 notes 가 알린다')
    ] = None
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


def previous_high_change_percent(price: int | None, previous_high: int | None) -> float | None:
    """직전 최고가 대비 변화율 (%, 소수 둘째 자리). 당근 웹 실거래 카드(RealsaleFeedListQuery `g`)의 '직전 최고가 대비 ±N%' 와 같은 비율.

    웹은 정수로 반올림하고(JS `Math.round`) 0 이 되면 소수 첫째 자리(최소 0.1)로 보여 준다. jibsa 는 자릿수를 늘려 소수 셋째
    자리에서 .5 를 올려 반올림한다 (2026-11-13 사용자 결정, [웹과 다른 점](docs/development/providers/daangn.md)). 값이 바뀌었는데
    0.00 이 되면 웹처럼 0 대신 가장 작은 값(±0.01)이다. 반올림은 정수로 셈해 0.125 같은 경계가 부동소수 오차로 내려가지 않게
    한다. 예전에는 웹처럼 정수였고, 0 일 때의 소수 자리 반올림에 Python `round` 를 써 0.25% 가 웹(0.3)과 다른 0.2 였다
    (2026-11-13 리뷰). 직전 최고가가 없거나 0 이하면 없다.
    """
    if price is None or previous_high is None or previous_high <= 0:
        return None
    diff = price - previous_high
    if diff == 0:
        return 0.0
    scale = 10 ** PREVIOUS_HIGH_PERCENT_DIGITS
    # |diff| / previous_high * 100 * scale 를 .5 올림한 정수 (floor(x + 0.5))
    units = max((abs(diff) * 100 * scale * 2 + previous_high) // (2 * previous_high), 1)
    return units / scale * (1 if diff > 0 else -1)


def realsale_to_real_price(item: DaangnRealsaleFeedItemModel, trade_type: str, new_high: bool) -> DaangnRegionRealPrice:
    """지역 피드 한 칸을 `DaangnRegionRealPrice` 로 바꾼다. 금액은 원래 만원이다.

    신고가 배지와 '직전 최고가 대비' 는 웹 카드(MapShell `yc`)와 같다: 신고가는 `priceInsight.isNewHigh` 가 true 이고 해제되지
    않은 거래, 비율은 해제되지 않은 매매에만 `previousMaxPrice` 와 견준다. 일반 피드와 신고가 피드가 같은 카드라 둘 다 낸다.
    """
    realsale = item.realsale
    assert realsale is not None
    danji = item.danji
    insight = item.price_insight
    buy = trade_type == '매매'
    cancelled = realsale.cancel is True
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
        cancelled=realsale.cancel,
        deal_type=(
            {'DIRECT': '직거래', 'BROKERED': '중개거래'}.get(realsale.transaction_type or '', realsale.transaction_type)
            if buy else None
        ),
        contract_type=None if buy else contract_type_of(realsale.lease_contract_type),
        is_new_high=(bool(insight and insight.is_new_high) and not cancelled) if buy else None,
        previous_high_manwon=insight.previous_max_price if buy and insight else None,
        previous_high_date=normalize_date(insight.previous_max_contact_date) if buy and insight else None,
        previous_high_change_percent=(
            previous_high_change_percent(realsale.trade_price, insight.previous_max_price if insight else None)
            if buy and not cancelled else None
        ),
    )


def realsale_summary(client: DaangnClient, region_id: int, notes: list[str]) -> DaangnRealsaleSummary | None:
    """지역 실거래 화면 머리의 요약 (`realsaleFeedSummary`, 요청 1회). 덤 조회라 실패하면 None 과 `notes` 로 알린다.

    요청 제한(`RateLimitedError`)도 올리지 않고 같은 `[실패]` 안내로 남긴다. 이 요약은 실거래 피드를 다 받은 뒤의 마지막
    요청이라 뒤에 막힐 요청이 없고, 올리면 모아 둔 거래를 모두 버린다 (2026-11-13 리뷰·재현: 역삼동 피드 5건을 받은 뒤 요약만
    RateLimitedError 로 바꾸니 exit 1 에 stdout 이 비었다).
    """
    try:
        response = client.run_request_realsale_feed_summary(
            DaangnRealsaleFeedSummaryRequestPayloadModel(
                input=DaangnRealsaleSummaryInputModel(region_id=region_id),
                new_high_input=DaangnRealsaleSummaryInputModel(region_id=region_id),
            )
        )
        data = unwrap_graphql(response, response.data, '실거래 요약')
    except OPTIONAL_LOOKUP_ERRORS as exc:
        logger.warning('daangn realsale summary failed (%s); continuing without summary', exc)
        notes.append(note('실패', partial_failure_note(exc, '실거래 요약', '공개일 요약을')))
        return None
    sale = data.realsale_feed_summary
    new_high = data.realsale_new_high_feed_summary
    return DaangnRealsaleSummary(
        data_date=normalize_date(sale.data_date) if sale else None,
        sale_count=sale.sale_count if sale else None,
        new_high_count=new_high.new_high_count if new_high else None,
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
    trade_type: str = '매매',
    new_high: bool = False,
    previous_days: bool = False,
    limit: int = 120,
) -> DaangnRegionRealPriceResult:
    """동·구의 최근 실거래(`realsaleFeed`) 또는 신고가 매매(`realsaleNewHighFeed`)를 모은다.

    당근 웹 실거래 화면(`RealsaleFeedListQuery`)은 늘 매매를 가격 순(`TRADE_PRICE_DESC`: 최근 공개일부터, 같은 공개일 안에서
    가격 높은 순)으로 부르고 정렬·거래 유형을 바꾸는 버튼이 없다. 매매는 웹처럼 가격 순이고 정렬 옵션은 없다 (예전에는 기본
    최신 순에 `--sort` 가 있었다, #215). 전세·월세는 같은 API(`tradeType: BORROW`)로 받는 jibsa 옵션이고, 서버가 가격 순을
    거절해 최신 순(`LATEST`)이다 (`REALSALE_SORT_BY_TRADE_TYPE`). 당근은 전월세를 섞어 주므로 전세·월세는 50건씩 최근 1200건까지
    넘겨 보며 월세 유무(`monthRentFee`, 웹 카드가 전세·월세 표시를 가르는 값)로 고른다 (`_collect_pages`). 주소(`regionName`)는
    웹 카드처럼 그대로 준다 (예전에는 읍·면으로 조회하면 리 앞에 읍·면을 끼워 넣었다, #215).

    신고가는 매매만이고 웹처럼 가격 높은 순이다. 웹 신고가 화면처럼 가장 최근 공개일의 신고가만 받고, `previous_days` 를
    주면 이전 공개일 신고가까지 받는다 (`includePreviousDays`, 2026-11-12 사용자 결정).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        JibsaError: GraphQL 에러면 UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 실거래 쿼리를 바꿨을 때.
    """
    region, notes = resolve_realsale_region(client, query, sejong_whole=True)
    buy = trade_type == '매매'
    sort = REALSALE_SORT_BY_TRADE_TYPE[trade_type]

    def fetch(count: int, cursor: str | None) -> DaangnRealsaleFeedModel:
        if new_high:
            response = client.run_request_realsale_new_high_feed(
                DaangnRealsaleNewHighFeedRequestPayloadModel(
                    count=count,
                    cursor=cursor,
                    input=DaangnRealsaleNewHighFeedInputModel(
                        region_id=region.region_id, include_previous_days=previous_days,
                    ),
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
                    sort=sort,
                ),
            )
        )
        return unwrap_graphql(feed_response, feed_response.data.realsale_feed if feed_response.data else None, '지역 실거래')

    def page(count: int, cursor: str | None) -> tuple[list[DaangnRealsaleFeedItemModel], DaangnPageInfoModel | None]:
        feed = fetch(count, cursor)
        return [edge.node for edge in feed.edges if edge.node], feed.page_info

    found = _collect_pages(
        page, lambda item: _realsale_matches(item, trade_type), trade_type, limit,
        url='https://realty.daangn.com/', remaining='추가 거래가 남아 있습니다',
    )
    collected = found.items
    notes += found.notes
    # 요약은 덤 조회라 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이 되면 첫 화면 실패를 삼키고 본 조회가 브라우저를 다시 띄운다).
    # 마지막 요청이라 요청 제한에 걸려도 받은 거래를 돌려준다 (`realsale_summary`)
    summary = realsale_summary(client, region.region_id, notes)
    if new_high and not previous_days:
        # 웹처럼 하루치라 동처럼 좁은 지역은 자주 비고(2026-11-12 실측: 역삼동 0건), 빈 목록을 '신고가가 없다' 로 읽지 않게 알린다
        notes.append(note(
            '범위',
            ('가장 최근 공개일에 이 지역 신고가가 없습니다' if not collected else '당근 웹처럼 가장 최근 공개일의 신고가만 줍니다')
            + '. 이전 공개일 신고가까지 보려면 --previous-days 를 붙이세요',
        ))
    return DaangnRegionRealPriceResult(
        region=region,
        trade_type=trade_type,
        new_high=new_high,
        sort=REALSALE_SORT_LABEL_BY_SORT['TRADE_PRICE_DESC' if new_high else sort],
        summary=summary,
        returned=len(collected),
        has_more=found.has_more,
        transactions=[realsale_to_real_price(item, trade_type, new_high) for item in collected],
        notes=notes,
    )
