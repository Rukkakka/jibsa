"""주변 단지 목록 (nearby-complexes)."""

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.listing import (
    join_address,
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.compare.nearby import (
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnComplexRegionRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.compare.nearby import DaangnComplexCardModel
from jibsa.providers.daangn.service.common.complex import (
    complex_not_found,
    truncation_notes,
)
from jibsa.providers.daangn.service.common.constants import COMPLEX_TYPE_LABELS
from jibsa.providers.daangn.service.common.models import DaangnRegion
from jibsa.providers.daangn.service.common.response import (
    code_label,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.compare.constants import NEARBY_COMPLEXES_MAX
from jibsa.providers.daangn.service.compare.models import (
    DaangnNearbyComplex,
    DaangnNearbyComplexesResult,
)


def list_nearby_complexes(client: DaangnClient, complex_id: int, *, limit: int = 50) -> DaangnNearbyComplexesResult:
    """기준 단지와 같은 동의 다른 단지를 세대수 많은 순으로 (요청 3회: 단지의 동 → 동 단지 → 단지 카드).

    당근 웹 단지 화면에서 이 칸은 '함께 본 단지' 추천(실험 기능)으로 바뀌었고, 같은 동 단지 목록(`ComplexNearbySectionQuery`)은
    단지 페이지의 검색 엔진용 본문에만 남았다 (2026-11-12 번들 대조). 그 본문(ComplexTopicPanel `to`)은 300곳을 받아 기타 유형
    (ETC)과 기준 단지를 빼고 단지 ID 순으로 세운 뒤 기준 단지 ID 앞뒤에서 번갈아 10곳만 링크로 쓴다. 사용자가 보는 화면이 없는
    자료라 jibsa 는 웹에 남은 쿼리로 같은 동 단지를 모두 주고 세대수 순으로 세운다 (2026-11-12 사용자 결정, 웹과 다른 범위·정렬.
    기타 유형 제외는 웹과 같다). 동 ID 는 단지 페이지 쿼리(`ComplexIdSeoQuery`)에서 받고, 카드는 지도 단지 목록 카드
    (`ComplexListPanelMapPinsQuery`)다. 예전에는 동을 이름으로 다시 찾고(요청 1회 더, 다른 동으로 바뀔 수 있었다) 웹에서 사라진
    카드 쿼리를 썼다 (#215). 동 단지는 `NEARBY_COMPLEXES_MAX` 곳까지 한 번에 받고 (페이지 정보가 없다), 그만큼 받았으면 더 있을
    수 있다고 `notes` 로 알린다. 단지 카드도 ID 를 한 번에 보낸다.

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 동을 모르는 단지 (REGION_NOT_FOUND), 기타 유형 단지 (INVALID_ARGUMENT), 그 밖의 GraphQL 에러.
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    region_response = client.run_request_complex_region(DaangnComplexRegionRequestPayloadModel(complex_id=str(complex_id)))
    outer = region_response.data.complex_by_original_id if region_response.data else None
    # 바깥이 null 인 것도 안의 단지가 null 인 것과 같은 없는 단지다 (`compare_column` 과 같다). GraphQL errors 가 있으면 그 에러가 먼저다
    if outer is None and not region_response.errors:
        raise complex_not_found(complex_id)
    output = unwrap_graphql(region_response, outer, '단지 지역', conditions=False)
    if output.complex is None:
        raise complex_not_found(complex_id)
    dong = output.complex.region
    # 웹도 기타 유형(ETC)이거나 동을 모르는 단지는 같은 동 단지를 부르지 않는다. 이 쿼리도 region.depth 를 준다 (2026-11-12 실측:
    # 헬리오시티 → 가락동 depth 3. 리뷰가 depth 가 늘 None 이라 모든 단지가 실패한다고 했으나 오탐)
    if dong is None or dong.original_id is None or dong.depth != 3 or not dong.name3:
        raise RegionNotFoundError(f'단지 {complex_id} 의 동', hint='jibsa daangn search complexes <동 이름> 으로 찾으세요')
    full_name = join_address(dong.name1, dong.name2, dong.name3)
    if output.complex.type == 'ETC':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=(
                f'단지 {complex_id} 의 유형이 기타라 같은 동 단지 목록이 없습니다 (당근 웹도 기타 유형 단지에는 같은 동 단지를 보여 주지 않습니다)'
            ),
            hint=f"그 동의 단지는 jibsa daangn search complexes '{full_name}' 으로 찾으세요",
        )
    region = DaangnRegion(sido=dong.name1 or '', sigungu=dong.name2 or '', dong=dong.name3 or '', region_id=dong.original_id)
    response = client.run_request_nearby_complexes(
        DaangnNearbyComplexesRequestPayloadModel(region3_id=region.region_id, first=NEARBY_COMPLEXES_MAX)
    )
    nodes = unwrap_graphql(response, response.data.complexes if response.data else None, '같은 동 단지', conditions=False)
    # 서버는 빈 edge(null)도 한 자리로 세어 `NEARBY_COMPLEXES_MAX` 까지 준다. 빼고 읽은 수를 받은 자리에 더한다
    null_edges = nodes.null_items('edges')
    # 더 있을 수 있다는 안내라 [일부] 다. 지금은 가장 큰 동도 상한에 닿지 않지만 (2026-11-10 실측: 화곡동 705곳) 동이 커지면
    # 나온다 (2026-11-10 리뷰: 태그가 없어 [참고] 로 나갈 뻔했다). 동 이름은 같은 이름의 동이 REGION_AMBIGUOUS 가 되지 않게
    # 시·구·동 전체 이름을 작은따옴표로 감싸고 조사는 '명령에' 로 고정한다. `search complexes` 도 `--limit` 최대가 같은 1200 이라
    # 나머지를 받으려면 조건으로 좁혀야 한다
    capped_notes = (
        [note(
            '일부',
            f'당근에서 같은 동 단지를 {NEARBY_COMPLEXES_MAX}곳까지만 받아 더 있을 수 있습니다. '
            f"나머지는 jibsa daangn search complexes '{join_address(region.sido, region.sigungu, region.dong)}' 명령에 조건"
            '(--type·--trade·가격·--area-min/--area-max·세대수 등)을 줘 좁혀 찾으세요',
        )]
        if len(nodes.edges) + null_edges >= NEARBY_COMPLEXES_MAX else []
    )
    # 웹 `to` 처럼 기준 단지와 기타 유형(ETC) 단지는 뺀다
    ids = [
        edge.node.original_id for edge in nodes.edges
        if edge.node and edge.node.original_id != str(complex_id) and edge.node.type != 'ETC'
    ]
    cards: list[DaangnComplexCardModel] = []
    null_cards = 0
    # 웹(300곳)보다 많아도 한 번에 보낸다 (리뷰 오탐 2026-11-12, 근거 고침 2026-11-20. 실측(2026-11-20): 서로 다른 단지 ID 1097개를
    # 보내 카드 1097개가 모두 왔고, 중복 ID 로 채운 1250개도 모두 왔다. ID 수는 `first=1200` 으로 막혀 서버가 자를 일이 없다.
    # 2026-11-12 에는 화곡동 강서힐스테이트 705곳이 한 번에 모두 왔다)
    if ids:
        cards_response = client.run_request_complexes_by_original_complex_ids(
            DaangnComplexesByOriginalComplexIdsRequestPayloadModel(original_ids=ids)
        )
        cards = unwrap_graphql(
            cards_response,
            cards_response.data.complexes_by_original_complex_ids if cards_response.data else None,
            '단지 카드',
            conditions=False,
        )
        # 단지 카드 목록에서 빈 항목을 뺐으면 같은 동 단지 수를 알 수 없다 (null)
        null_cards = cards_response.data.null_items('complexes_by_original_complex_ids') if cards_response.data else 0
    nearby = [
        DaangnNearbyComplex(
            complex_id=card.original_id,
            name=card.name,
            complex_type=code_label(COMPLEX_TYPE_LABELS, card.type),
            household_count=card.proptier_danji.total_tot_hseh_cnt if card.proptier_danji else None,
            listing_counts={
                'sale': card.live_article_count.buy if card.live_article_count else None,
                'jeonse': card.live_article_count.borrow if card.live_article_count else None,
                'wolse': card.live_article_count.month if card.live_article_count else None,
            },
        )
        for card in cards
    ]
    nearby.sort(key=lambda item: (item.household_count is None, -(item.household_count or 0)))
    null_notes = [
        null_items_note(what, count, unknown)
        for what, count, unknown in (('당근 같은 동 단지', null_edges, ()), ('당근 단지 카드', null_cards, ('total',)))
        if count
    ]
    return DaangnNearbyComplexesResult(
        complex_id=str(complex_id),
        region=region,
        total=None if null_cards else len(nearby),
        returned=min(len(nearby), limit),
        sort='세대수',
        complexes=nearby[:limit],
        notes=capped_notes + truncation_notes(len(nearby), limit, subject='단지', unit='곳', max_limit=NEARBY_COMPLEXES_MAX) + null_notes,
    )
