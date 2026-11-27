"""인기 단지 (trending-complexes)."""

from jibsa.core.errors import JibsaError
from jibsa.core.korean import quoted
from jibsa.core.listing import (
    AmountSet,
    join_address,
    normalize_address,
    null_items_note,
    read_date,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.complex.trending import (
    DaangnTrendingComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.service.common.complex import most_households
from jibsa.providers.daangn.service.common.constants import COMPLEX_TYPE_LABELS
from jibsa.providers.daangn.service.common.response import (
    code_label,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.complex.constants import APPROVAL_DATE_PATTERN
from jibsa.providers.daangn.service.complex.models import (
    DaangnTrendingComplex,
    DaangnTrendingComplexesResult,
    DaangnTrendingRegion,
)
from jibsa.providers.daangn.service.region.models import DaangnArea


def trending_region_of(area: DaangnArea | None) -> DaangnTrendingRegion:
    """인기 급상승 단지의 범위. 지역이 없으면 전국이다.

    Raises:
        JibsaError: 동이면 INVALID_ARGUMENT. 당근 웹은 전국·시·도 탭과 시·군·구 페이지로만 부른다 (2026-11-12 번들 대조).
    """
    if area is None:
        return DaangnTrendingRegion(level='전국')
    if area.level == '동':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"인기 급상승 단지는 전국·시·도·구 단위만 있습니다 ({quoted(area.full_name, '은/는')} 동입니다)",
            hint=f"구로 찾으려면 jibsa daangn trending-complexes '{join_address(area.name1, area.name2)}'. 지역을 빼면 전국입니다",
        )
    return DaangnTrendingRegion(
        sido=area.name1,
        sigungu=area.name2 if area.level == '구' else '',
        region_id=area.region_id,
        level='시도' if area.level == '시도' else '구',
    )



def list_trending_complexes(client: DaangnClient, region: DaangnTrendingRegion) -> DaangnTrendingComplexesResult:
    """어제 대비 오늘 조회가 급상승한 단지 (`trendingComplexes`, 요청 1회). 웹의 인기 급상승 단지 패널처럼 50곳까지다.

    대표 평형은 웹(MapShell `zu`)처럼 대표 전용면적 묶음(없으면 첫 묶음)에서 세대수가 가장 많은 평형이다. 예전에는 묶음의 첫
    평형을 써서 전국 50곳 중 10곳이 웹과 달랐다 (2026-11-12 실측). 같으면 앞 평형이다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_trending_complexes(
        DaangnTrendingComplexesRequestPayloadModel(region_id='ALL' if region.region_id is None else str(region.region_id))
    )
    found = unwrap_graphql(response, response.data.trending_complexes if response.data else None, '인기 단지', conditions=False)
    # 목록에서 빈 항목을 빼고 읽었으면 순위를 매길 자리를 알 수 없어 순위는 모두 모른다 (null)
    dropped_complexes = response.data.null_items('trending_complexes') if response.data else 0
    dropped_pyeongs = 0
    dropped_trades = 0
    complexes: list[DaangnTrendingComplex] = []
    for rank, item in enumerate(found, start=1):
        danji = item.proptier_danji
        groups = danji.exclusive_area_groups if danji else []
        # 대표 묶음은 평형이 없는 묶음까지 포함한 묶음 전체에서 고른다 (웹 MapShell `zu`). 단지 비교(`_select_pyeong`)는 웹 식이
        # 달라 평형이 있는 묶음 중에서 고른다 (합치지 않는다)
        group = next((group for group in groups if group.is_representative), groups[0] if groups else None)
        info = most_households(group.py_infos if group else [], lambda py: py.households)
        # 대표 묶음·대표 평형을 고르는 목록에서 빈 항목을 빼고 읽었으면 고른 평형이 웹의 대표 평형이 아닐 수 있어 모른다 (null)
        dropped = (danji.null_items('exclusive_area_groups') if danji else 0) + (group.null_items('py_infos') if group else 0)
        if dropped:
            info = None
            dropped_pyeongs += dropped
        latest_trades: dict[str, AmountSet | None]
        realsale = info.sale_realsale if info else None
        # 실거래 칸이나 그 목록(edges)이 null 이거나 목록에 빈 항목(null 원소, node 가 null 인 항목)이 있으면 최근 매매가 있는지 모른다
        # (null). 빈 목록 [] 만 해당 없음이다
        blank_trades = (
            realsale.null_items('edges') + sum(1 for edge in realsale.edges or [] if edge.node is None) if realsale else 0
        )
        if realsale is None or realsale.edges is None or blank_trades:
            latest_trades = {'sale': None}
            dropped_trades += blank_trades
        else:
            # 최근 매매가 없거나(노드가 없음) 매매가가 0 이면 해당 없음이라 키를 뺀다 (웹 카드 `zu` 의 `price:o?…:null` 도 0 이면 비운다)
            node = realsale.edges[0].node if realsale.edges else None
            if node is None or node.trade_price == 0:
                latest_trades = {}
            else:
                latest_trades = {'sale': None if node.trade_price is None else AmountSet(price_manwon=node.trade_price)}
        approval = APPROVAL_DATE_PATTERN.search(item.approval_date_text or '')
        # 응답 설명이 '사용승인일 2022.04.28(4년차)' 꼴인데 날짜가 없는 단지가 어떤 글자를 주는지 확인되지 않았다.
        # 그래서 매치되지 않는 글자는 값 없음으로 보고, 매치됐는데 없는 날이면 못 읽은 날짜로 알린다
        approved_date = (
            read_date('-'.join(approval.groups()), '사용승인일', raw=item.approval_date_text) if approval else None
        )
        complexes.append(DaangnTrendingComplex(
            rank=None if dropped_complexes else rank,
            complex_id=item.original_id,
            name=item.name,
            complex_type=code_label(COMPLEX_TYPE_LABELS, item.type),
            address=normalize_address(join_address(item.region.name1, item.region.name2)) if item.region else None,
            household_count=item.households,
            approved_date=approved_date,
            representative_area_m2=info.exclusive_area if info else None,
            latest_trades=latest_trades,
        ))
    # 동으로 부를 때는 이른 아침마다 비었다 (2026-10-27 실측). 웹 범위(전국·시·도·구)에서도 비면 단지가 없다는 뜻으로 읽히지 않게 알린다
    region_name = ' '.join(part for part in (region.sido, region.sigungu) if part) or '전국'
    notes = [] if complexes else [
        f'당근이 {region_name} 인기 급상승 단지를 주지 않았습니다. 단지가 없다는 뜻은 아닙니다. 때에 따라 달라 나중에 다시 부르면 '
        '나올 수 있고, 지역 단지 목록은 jibsa daangn search complexes <동·구> 에서 봅니다'
    ]
    if dropped_complexes:
        notes.append(null_items_note('당근 인기 급상승 단지', dropped_complexes, ('rank',)))
    if dropped_pyeongs:
        notes.append(null_items_note('당근 인기 단지 평형', dropped_pyeongs, ('representative_area_m2', 'latest_trades 의 sale')))
    if dropped_trades:
        notes.append(null_items_note('당근 인기 단지 최근 매매', dropped_trades, ('latest_trades 의 sale',)))
    return DaangnTrendingComplexesResult(region=region, returned=len(complexes), complexes=complexes, notes=notes)
