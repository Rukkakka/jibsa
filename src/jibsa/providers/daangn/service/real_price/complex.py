"""단지·매물 실거래가 (real-price)."""

from collections.abc import Callable
from datetime import (
    date,
    datetime,
)

from jibsa.core.errors import (
    ListingUnavailableError,
)
from jibsa.core.listing import (
    KST,
    UPDATE_MAYBE_NEEDED,
    floor_text,
    note,
    read_date,
    years_ago,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.real_price.complex import (
    DaangnArticleByOriginalArticleIdRequestPayloadModel,
    DaangnComplexByOriginalIdRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnPageInfoModel,
    DaangnTransactionModel,
)
from jibsa.providers.daangn.api.models.response.real_price.complex import (
    DaangnComplexTransactionsModel,
)
from jibsa.providers.daangn.service.common.complex import (
    compare_column,
    complex_not_found,
)
from jibsa.providers.daangn.service.common.constants import ARTICLE_URL, COMPLEX_URL
from jibsa.providers.daangn.service.common.response import (
    code_label,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.real_price.common import (
    Collected,
    choose_pyeong,
    collect_pages,
    contract_type_of,
    is_rent_type,
    site_note,
)
from jibsa.providers.daangn.service.real_price.constants import (
    NOT_PRESALE_OWNERSHIP,
    PRESALE_LABELS,
)
from jibsa.providers.daangn.service.real_price.models import (
    DaangnListingRealPriceResult,
    DaangnRealPrice,
    DaangnRealPriceResult,
)


TransactionFetch = Callable[[int, str | None], DaangnComplexTransactionsModel]



def _trade_date(node: DaangnTransactionModel) -> str | None:
    if node.deal_year is None or node.deal_month is None or node.deal_day is None:
        return None
    return f'{node.deal_year:04d}-{node.deal_month:02d}-{node.deal_day:02d}'



def transaction_to_real_price(node: DaangnTransactionModel, trade_type: str) -> DaangnRealPrice:
    """실거래 한 건을 `DaangnRealPrice` 로 바꾼다. 금액은 원래 만원이다."""
    buy = trade_type == '매매'
    # 리뷰 오탐 (2026-11-22): 매물 기준 실거래(get_listing_real_prices, articleByOriginalArticleId)도 ownership 을 준다. ownership 을 못 받아
    # 모든 매매 거래가 presale: null 이 되는 경로는 없다 (2026-11-22 실측: 매물 4773364 매매 10건 모두 REGISTERED_OWNER 라 presale 키 없음)
    # 소유 구분: 일반 거래(REGISTERED_OWNER)는 분양권이 아니라 해당 없음(키 삭제)이고, 비었거나 '-' 면 모름(null)이다
    not_presale = (node.ownership or '').strip() == NOT_PRESALE_OWNERSHIP
    return DaangnRealPrice(
        trade_type=trade_type,
        # 달력에 없는 날(정수 연·월·일을 검사 없이 이어 붙였다)은 null 과 [참고]. `_trade_date` 는 기간 거르기(`date_of`)에도 쓰여 거기서 읽으면
        # 출력하지 않는 거래까지 안내에 센다
        trade_date=read_date(_trade_date(node), '계약일'),
        area_m2=node.exclusive_use_area,
        floor=floor_text(node.floor),
        price_manwon=node.deal_amount if buy else None,
        deposit_manwon=None if buy else node.deposit,
        rent_manwon=node.monthly_rent if trade_type == '월세' else None,
        cancelled=node.deal_canceled if buy else None,
        # 등기일이 있어야 등기를 마친 거래라 빈 글자·'-' 는 등기 전이다
        registered=(node.registrated_at or '').strip() not in ('', '-') if buy else None,
        presale=None if not buy or not_presale else code_label(PRESALE_LABELS, node.ownership),
        not_presale=buy and not_presale,
        contract_type=None if buy else contract_type_of(node.contract_type),
        renewal_right=None if buy else node.use_renewal_of_contract_right,
    )



def _collect_transactions(
    fetch: TransactionFetch,
    trade_type: str,
    limit: int,
    *,
    url: str,
    since: str | None = None,
    remaining: str = '더 오래된 거래가 남아 있습니다',
) -> Collected[DaangnTransactionModel]:
    """단지·매물 실거래를 최근 계약 순으로 `limit` 건까지 모은다 (`collect_pages`).

    Args:
        fetch: (받을 수, 커서) → 단지·매물의 실거래 연결. 매매면 매매 연결의, 아니면 전월세 연결의 크기·커서다.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        url: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때 확인하라고 안내할 당근 페이지.
        since: 이날(YYYY-MM-DD)부터의 계약만 받는다 (`--years`).
        remaining: 남은 거래 안내의 앞말 (`collect_pages`). 한 달만 받으면 '더 오래된' 이 아니라 그 달 거래가 남았다고 한다.

    Returns:
        모은 거래와 안내 (`collect_pages`). 당근이 첫 쪽의 거래 연결(또는 그 `edges`)을 주지 않았으면 `unknown` 이 True 다.
    """
    buy = trade_type == '매매'

    def page(size: int, after: str | None) -> tuple[list[DaangnTransactionModel] | None, DaangnPageInfoModel | None]:
        transactions = fetch(size, after)
        connection = transactions.buy_transactions if buy else transactions.borrow_transactions
        # 연결이나 edges 가 null 이면 거래가 0건인 것(edges []) 과 달라 모름이다 (`collect_pages`)
        if connection is None or connection.edges is None:
            return None, None
        return [edge.node for edge in connection.edges if edge.node], connection.page_info

    return collect_pages(
        page,
        lambda node: buy or is_rent_type(node.monthly_rent, trade_type),
        trade_type,
        limit,
        site=site_note(url),
        remaining=remaining,
        since=since,
        date_of=_trade_date,
    )



def _empty_result_note(found: Collected[DaangnTransactionModel], trade_type: str, since: str | None) -> str | None:
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
    전용면적 묶음이다. 당근이 거래 연결(또는 그 `edges`)을 null 로 주면 거래가 0건인 것이 아니라 모름이라 `trades`·`has_more` 를
    null 로 내고 알린다 (정말 0건이면 `[]`).

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
            response, response.data.complex_by_original_id if response.data else None, '실거래가', conditions=False
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        return result.complex

    since = years_ago(today or datetime.now(KST).date(), years) if years is not None else None
    found = _collect_transactions(
        fetch, trade_type, limit,
        url=COMPLEX_URL.format(complex_id),
        since=since,
        remaining=f'{month} 의 거래가 더 남아 있습니다' if month else '더 오래된 거래가 남아 있습니다',
    )
    notes = found.notes
    # 당근이 거래 목록을 주지 않았으면 거래가 0건인 것이 아니라 모름이라 trades·has_more 를 null 로 낸다.
    # 단지 실거래는 빈 결과에 '없다' 고 단정하지 않지만, 기간 앞·다른 유형에 거래가 있으면 매물 실거래처럼 알린다
    if found.unknown:
        notes.append(note('실패', f'당근이 이 단지의 {trade_type} 거래 목록을 주지 않았습니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'))
    elif (empty := _empty_result_note(found, trade_type, since)) is not None:
        notes.append(empty)
    return DaangnRealPriceResult(
        complex_id=str(complex_id),
        trade_type=trade_type,
        area_group=area_group,
        pyeong=pyeong,
        returned=len(found.items),
        has_more=None if found.unknown else found.has_more,
        start_date=since,
        month=month,
        trades=None if found.unknown else [transaction_to_real_price(node, trade_type) for node in found.items],
        url=COMPLEX_URL.format(complex_id),
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
    없어, 없으면 그 이유를 `notes` 로 알린다. 거래가 기간 앞이나 다른 유형(전세·월세)에만 있어 비었으면 그렇게 알린다. 당근이 거래
    연결(또는 그 `edges`)을 null 로 주면 모름이라 `trades`·`has_more` 를 null 로 내고 알린다 (`get_real_prices` 와 같다).

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
            conditions=False,
        )

    since = years_ago(today or datetime.now(KST).date(), years) if years is not None else None
    found = _collect_transactions(
        fetch, trade_type, limit,
        url=ARTICLE_URL.format(original_id),
        since=since,
    )
    notes = found.notes
    # 거래가 더 남았으면(페이지가 멈췄거나 전월세 1200건 안에 그 유형이 없음) 없다고 단정하지 않는다. 남았다는 [일부] 와
    # '최근 전월세 실거래 N건 중 전세 0건' [참고] 가 이미 알리는데, 같은 결과에 '없습니다' 가 붙으면 에이전트가 없다고 전한다
    # (2026-11-11 리뷰). 기간 앞이나 다른 유형에 거래가 있으면 그 까닭을 알리고(`_empty_result_note`), 거래를 하나도 받지
    # 못했을 때만 건물을 찾지 못한 경우를 알린다
    # 당근이 거래 목록을 주지 않았으면(연결이나 edges 가 null) 모름이라 trades·has_more 를 null 로 낸다. 연결이 있고 비어
    # 있을 때(edges [])의 아래 '없습니다' 안내와 다르다
    if found.unknown:
        notes.append(note('실패', f'당근이 이 건물의 {trade_type} 거래 목록을 주지 않았습니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'))
    elif (empty := _empty_result_note(found, trade_type, since)) is not None:
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
        has_more=None if found.unknown else found.has_more,
        start_date=since,
        trades=None if found.unknown else [transaction_to_real_price(node, trade_type) for node in found.items],
        url=ARTICLE_URL.format(original_id),
        notes=notes,
    )
