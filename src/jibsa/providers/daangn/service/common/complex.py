"""당근 단지 공용: 비교 칸·평형 묶음·지역 단지 카드·안내 문구."""

from collections.abc import (
    Callable,
    Sequence,
)

from jibsa.core.dates import read_date
from jibsa.core.errors import JibsaError
from jibsa.core.notes import note
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.compare.common import (
    DaangnComplexCompareRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnRegionComplexNodeModel,
)
from jibsa.providers.daangn.api.models.response.compare.common import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
)
from jibsa.providers.daangn.service.common.constants import (
    APARTMENT_COMPLEX_TYPES,
    COMPLEX_RECENT_TRADES,
    COMPLEX_TYPE_LABELS,
    COMPLEX_URL,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnRecentTrade,
    DaangnRegionComplex,
)
from jibsa.providers.daangn.service.common.response import (
    T,
    code_label,
    unwrap_graphql,
)


def truncation_notes(
    received: int,
    limit: int,
    *,
    subject: str = '매물',
    unit: str = '건',
    max_limit: int | None = None,
) -> list[str]:
    """받은 유효 결과를 출력 한도로 자를 때 실제 개수와 다음에 할 일을 알린다.

    `max_limit` 를 주면 `--limit` 이 최대값보다 작을 때 늘리라고 덧붙인다. `--limit` 이 이미 최대값이면 늘리라는
    안내는 옵션 검사에서 막히므로 붙이지 않는다. 매물 목록(`listing_budget_notes`)처럼 `--limit` 안내를 따로 붙이는
    호출부는 `max_limit` 를 넘기지 않는다. 같은 말이 두 번 나온다 (2026-10-11 실측: daangn search listings 역삼동
    --limit 2 에 '검색 범위를 좁혀 주세요' 가 두 번). 실거래는 반대로 `max_limit` 를 넘기고, 이 안내가 나오면 따로
    붙이던 '--limit 을 늘리면' 안내를 빼서 [일부] 를 하나만 낸다 (`collect_pages`).
    """
    if received <= limit:
        return []
    text = f'조회된 {subject} {received}{unit} 중 --limit {limit} 에 맞춰 {limit}{unit}만 보여 줍니다'
    if max_limit is not None and limit < max_limit:
        text += f'. --limit 을 최대 {max_limit}까지 늘리세요'
    return [note('일부', text)]


def complex_not_found(complex_id: str | int) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f'당근 단지를 찾지 못했습니다: {complex_id}',
        hint=(
            "단지 ID 는 'jibsa daangn search locations <단지 이름>' 의 complexes 나 아파트·오피스텔 매물 "
            'item 의 complex_id 에서 얻습니다'
        ),
    )


def compare_column(client: DaangnClient, complex_id: int) -> DaangnCompareComplexModel:
    """단지 비교 칸 (`ComplexCompareColumnQuery`, 요청 1회, 약 78KB). 평형 묶음·평형 타입 코드·노드 ID 도 여기서 받는다.

    단지 비교(`compare`)와 평형을 고르는 실거래·시세 추이(`real-price`·`price-trend`)가 같이 쓴다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND.
    """
    response = client.run_request_complex_compare(DaangnComplexCompareRequestPayloadModel(original_id=str(complex_id)))
    output = response.data.complex_by_original_id if response.data else None
    found = output.complex if output else None
    if found is None and not response.errors:
        raise complex_not_found(complex_id)
    return unwrap_graphql(response, found, '단지 비교', conditions=False)


def uses_supply_pyeong(complex_type: str | None, supply_groups: Sequence[object]) -> bool:
    """평형을 공급 평 묶음으로 고르는 단지인지. 당근 웹처럼 아파트형 단지(아파트·주상복합·재개발)에 공급 평 묶음이 있으면 그것으로,
    아니면 전용면적 묶음으로 고른다 (utils `n()`, 2026-11-12 번들 대조). 단지 평형 목록(`complex_pyeongs`)과 비교·실거래의
    평형 고르기(`pyeong_groups`)가 같이 쓴다."""
    return complex_type in APARTMENT_COMPLEX_TYPES and bool(supply_groups)


def pyeong_groups(column: DaangnCompareComplexModel) -> tuple[bool, list[DaangnCompareAreaGroupModel]]:
    """단지의 평형 묶음과, 그것이 공급 평 묶음인지 (`uses_supply_pyeong`). 단지 비교와 실거래·시세 추이의 평형 고르기가 같이 쓴다."""
    danji = column.proptier_danji
    if danji is None:
        return False, []
    supply = uses_supply_pyeong(column.type, danji.supply_pyeong_area_groups)
    return supply, danji.supply_pyeong_area_groups if supply else danji.exclusive_area_groups


def pyeong_null_items(column: DaangnCompareComplexModel) -> int:
    """대표 평형을 고르는 목록(평형 묶음과 그 안의 평형)에서 빈 항목을 빼고 읽은 수.

    그 목록에서 대표 묶음(`is_representative` 없으면 첫 묶음)과 묶음의 세대수 최다 평형을 고르므로, 빈 항목을 뺐으면 고른 평형이
    웹의 대표 평형이 아닐 수 있다. 호출부가 `null_items_note` 로 알린다.
    """
    danji = column.proptier_danji
    if danji is None:
        return 0
    groups = danji.supply_pyeong_area_groups + danji.exclusive_area_groups
    return danji.null_items('supply_pyeong_area_groups', 'exclusive_area_groups') + sum(
        group.null_items('py_infos') for group in groups
    )


def most_households(infos: Sequence[T], households: Callable[[T], int | None]) -> T | None:
    """평형 목록에서 세대수가 가장 많은 평형 (같으면 앞 평형, 웹 reduce 도 더 클 때만 바꾼다). 없으면 None.

    비교 화면(`compare.complexes._select_pyeong`)과 인기 급상승 단지(`list_trending_complexes`)가 같이 쓴다. 두 응답 모델의 세대수 칸 이름이 달라 칸을 함수로 받는다.
    세대수를 모르는 평형은 0 으로 센다.
    """
    return max(infos, key=lambda info: households(info) or 0) if infos else None


def is_year_month(value: str | None) -> bool:
    """연월이 'YYYYMM' 꼴이고 달이 1~12 인지. 단지 비교 관리비와 시세 추이가 같이 쓴다.

    당근이 값 없음을 빈 문자열이나 '-' 로 주기도 해 그런 값은 거짓이다. 공백은 지우지 않는다 (' 202601' 을 맞는 꼴로 보면
    뒤에서 달 번호를 틀리게 읽는다).
    """
    return value is not None and len(value) == 6 and value.isdecimal() and 1 <= int(value[4:6]) <= 12


def _recent_trades(node: DaangnRegionComplexNodeModel, trade_type: str, max_trades: int) -> list[DaangnRecentTrade] | None:
    """단지 카드의 최근 실거래에서 요청한 거래 유형만 골라 앞에서부터 `max_trades` 건.

    전월세는 전세·월세가 섞여 오므로 월세가 0 이면 전세로 본다. 해제(취소)된 매매는 뺀다. 당근이 실거래 연결(`transactions`)이나
    그 목록(`edges`)을 null 로 주면 거래가 없는 것이 아니라 모름이라 None 이다 (빈 목록 `[]` 은 거래가 없다).
    """
    if node.transactions is None or node.transactions.edges is None:
        return None
    edges = node.transactions.edges
    trades: list[DaangnRecentTrade] = []
    for edge in edges:
        transaction = edge.node
        if transaction is None or transaction.deal_canceled:
            continue
        if trade_type == '매매':
            if transaction.deal_amount is None:
                continue
            trade = DaangnRecentTrade(
                trade_type=trade_type,
                area_m2=transaction.exclusive_use_area,
                price_manwon=transaction.deal_amount,
            )
        else:
            monthly = bool(transaction.monthly_rent)
            if transaction.deposit is None or monthly != (trade_type == '월세'):
                continue
            trade = DaangnRecentTrade(
                trade_type=trade_type,
                area_m2=transaction.exclusive_use_area,
                deposit_manwon=transaction.deposit,
                rent_manwon=transaction.monthly_rent if monthly else None,
            )
        trades.append(trade)
        if len(trades) >= max_trades:
            break
    return trades


def region_complex_of(
    node: DaangnRegionComplexNodeModel, trade_type: str, max_trades: int = COMPLEX_RECENT_TRADES,
) -> DaangnRegionComplex:
    """단지 카드를 `DaangnRegionComplex` 로 바꾼다. 후기 본문·요약은 내보내지 않고 있는지만 알린다.

    최근 실거래는 `max_trades` 건까지다. 당근 웹 단지 카드(ComplexListItem)는 취소되지 않은 첫 1건만 보여 주는데, 지역 단지
    목록은 더 많이 보여 주는 jibsa 개선으로 3건을 두고(2026-11-12 사용자 결정), 학교 배정 단지는 웹처럼 1건이다.

    단지 ID 가 없는 카드는 가리킬 수 없어, 부르는 쪽이 먼저 걸러 이 함수에 넘기지 않는다 (`node.original_id` 가 None 이면 ValueError).
    """
    if node.original_id is None:
        raise ValueError('단지 ID 가 없는 단지 카드는 걸러서 넘겨야 합니다')
    danji = node.danji
    counts = node.live_article_count
    # 단지 카드에 거주 후기가 있는지. 후기 요약이 있으면 있다. 요약이 없을 때 후기 연결(`livedReviews`)이나 그 목록(`edges`)을
    # 당근이 null 로 주면 없는 것이 아니라 모름(None)이다. 리뷰 오탐 (2026-11-19): 지역 단지 쿼리는 두 키를 모두 요청하므로
    # (school 배정 단지·search complexes 클러스터·좌표 목록에서 model_fields_set 로 확인) 키가 빠져 null 이 되는 일은 없고,
    # 서버가 null 로 준 것이다.
    has_reviews: bool | None
    if node.lived_review_summary is not None:
        has_reviews = True
    elif node.lived_reviews is None or node.lived_reviews.edges is None:
        has_reviews = None
    else:
        has_reviews = bool(node.lived_reviews.edges)
    return DaangnRegionComplex(
        complex_id=node.original_id,
        name=node.name,
        complex_type=code_label(COMPLEX_TYPE_LABELS, node.type),
        household_count=danji.households if danji else None,
        approved_date=read_date(danji.build_date, '사용승인일') if danji else None,
        listing_counts={
            'sale': counts.buy if counts else None,
            'jeonse': counts.borrow if counts else None,
            'wolse': counts.month if counts else None,
        },
        recent_trades=_recent_trades(node, trade_type, max_trades),
        near_station=node.near_station,
        has_reviews=has_reviews,
        url=COMPLEX_URL.format(node.original_id),
    )


def complex_list_notes(complexes: list[DaangnRegionComplex]) -> list[str]:
    """단지 목록(지역 단지·학교 배정 단지) 공통 안내: 최근 실거래에 날짜가 없고, 후기는 있는지만 알린다.

    매번 같은 안내지만 원룸 종류 안내처럼 docs/llm.md 로 옮기지 않는다. 가이드는 모든 세션이 읽어 이 명령을 쓰지 않는
    세션까지 토큰을 쓰고, 여기서는 이 명령을 부를 때만 나온다 (2026-10-23 실측: `search complexes 대치동` 안내 두 개
    162자 / 출력 21,471자, 0.8%).
    """
    notes: list[str] = []
    if any(complex_.recent_trades for complex_ in complexes):
        notes.append('recent_trades 는 당근 단지 목록의 최근 실거래라 계약일·층이 없습니다. 날짜까지 보려면 real-price <complex_id> 를 쓰세요')
    if any(complex_.has_reviews for complex_ in complexes):
        notes.append('거주 후기는 있는지(has_reviews)만 알려 줍니다. 후기 내용은 url 의 단지 페이지에서 확인하세요')
    return notes
