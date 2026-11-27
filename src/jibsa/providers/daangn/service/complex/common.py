"""단지 기능(complex)의 상세·검색·인기 단지가 같이 쓰는 것."""

import logging

from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.complex.base import (
    DaangnSearchComplexesInputModel,
    DaangnSearchComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.service.common.constants import (
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_LABELS,
    OPTIONAL_LOOKUP_ERRORS,
)
from jibsa.providers.daangn.service.common.response import (
    code_label,
    cursor_stopped_note,
    next_cursor,
    partial_failure_note,
    stalled_page,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.complex.constants import (
    COMPLEX_CANDIDATE_LIMIT,
    COMPLEX_PAGE_SIZE,
)
from jibsa.providers.daangn.service.complex.models import DaangnComplexCandidate


logger = logging.getLogger(__name__)


def search_complexes(
    client: DaangnClient,
    name: str,
    limit: int = COMPLEX_CANDIDATE_LIMIT,
    *,
    notes: list[str],
) -> list[DaangnComplexCandidate] | None:
    """단지 이름으로 단지 후보를 찾는다 (전국, 이름이 비슷한 순). 50개씩 페이지를 넘겨 받는다.

    단지 후보는 지역 검색(search locations)에 덤으로 붙는 결과라, 어느 페이지에서 실패하든(쿼리 변경·요청
    제한·서버 오류) 그때까지 받은 후보를 돌려주고 이유를 `notes` 로 알린다 (`partial_failure_note`). 첫 쪽부터 실패해
    받은 후보가 없으면 '후보 없음' 이 아니라 모름이라 None 이다 (search locations 의 다른 칸과 같다, 2026-11-12 리뷰).
    """
    candidates: list[DaangnComplexCandidate] = []
    seen: set[str] = set()
    after = None
    inspected = 0
    has_more = False
    stopped = False
    while inspected < limit:
        try:
            response = client.run_request_search_complexes(
                DaangnSearchComplexesRequestPayloadModel(
                    input=DaangnSearchComplexesInputModel(name=name),
                    first=min(COMPLEX_PAGE_SIZE, limit - inspected),
                    after=after,
                )
            )
            result = unwrap_graphql(response, response.data.search_complexes if response.data else None, '단지 검색', conditions=False)
        except OPTIONAL_LOOKUP_ERRORS as exc:
            logger.warning('daangn complex search failed after %d candidates (%s)', len(candidates), exc)
            received = f'단지 후보는 {len(candidates)}곳까지만 받았습니다. ' if candidates else ''
            notes.append(note('실패', received + partial_failure_note(exc, '단지 검색', '나머지 단지 후보를' if candidates else '단지 후보를')))
            # 더 있는지는 모르므로 아래의 '--limit 을 늘리라' 안내는 붙이지 않는다
            return candidates[:limit] if candidates else None
        if stalled_page(result.page_info, after):
            stopped = True
            break
        nodes = [edge.node for edge in result.edges if edge.node]
        inspected += len(nodes)
        for node in nodes:
            if node.original_id not in seen:
                buildings = [edge.node for edge in (node.buildings.edges if node.buildings else []) if edge.node]
                # 건물의 지번 주소를 먼저, 없으면 도로명 주소를 쓴다
                address = next((building.jibun_address for building in buildings if building.jibun_address), None)
                address = address or next((building.road_address for building in buildings if building.road_address), None)
                candidates.append(DaangnComplexCandidate(
                    complex_id=node.original_id,
                    complex_type=code_label(COMPLEX_TYPE_LABELS, node.type),
                    name=node.name,
                    address=normalize_address(address),
                ))
                seen.add(node.original_id)
        page = result.page_info
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page and page.has_next_page) or len(candidates) > limit
        if not has_more or inspected >= limit:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 에 닿은 것이 아니라
        # --limit 을 늘려도 더 받지 못하니, 아래의 '--limit 을 늘리면' 안내 대신 멈췄다고 알린다
        cursor = next_cursor(page, after, received=len(nodes))
        if cursor is None:
            stopped = True
            break
        after = cursor
    if stopped:
        notes.append(note('일부', cursor_stopped_note('단지 후보', f'{len(candidates)}곳') + '. 더 구체적인 단지 이름으로 검색하세요'))
    elif has_more:
        if limit >= COMPLEX_LIST_MAX_LIMIT:
            notes.append(note('일부', f'단지 후보는 최대 {COMPLEX_LIST_MAX_LIMIT}곳까지 조회할 수 있습니다. 더 구체적인 단지 이름으로 검색하세요'))
        else:
            notes.append(note(
                '일부',
                f'단지 후보가 더 있습니다. --limit 을 늘리면 최대 {COMPLEX_LIST_MAX_LIMIT}곳까지 조회할 수 있습니다 (현재 {limit}곳 한도)',
            ))
    return candidates[:limit]
