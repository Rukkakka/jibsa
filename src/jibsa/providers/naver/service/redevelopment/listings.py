"""재개발 구역 매물 (search listings --redevelopment)."""

from jibsa.core.dates import keep_unread_dates
from jibsa.core.listing import Listing
from jibsa.core.notes import note
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.redevelopment.listings import (
    NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
)
from jibsa.providers.naver.service.common.constants import (
    COMPLEX_SORT_TYPE_BY_NAME,
    TRADE_CODE_BY_NAME,
)
from jibsa.providers.naver.service.common.listing import (
    group_sort_notes,
    listing_keeper,
    price_filter_of,
    price_sort_notes,
)
from jibsa.providers.naver.service.common.models import (
    NaverListingsResult,
    NaverTradeConditions,
    PageScan,
)
from jibsa.providers.naver.service.common.paging import (
    pagination_notes,
    scan_null_items_notes,
    scan_pages,
)
from jibsa.providers.naver.service.common.response import (
    unwrap,
)
from jibsa.providers.naver.service.redevelopment.constants import (
    MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS,
    REDEVELOPMENT_PAGE_SIZE,
)

from typing import (
    Any,
)


def list_redevelopment_articles(
    client: NaverClient,
    area_number: int,
    *,
    conditions: NaverTradeConditions | None = None,
    sort: str = '랭킹순',
    limit: int = 30,
) -> NaverListingsResult:
    """재개발 구역 하나의 매물을 `lastInfo`·seed 커서로 넘기며 `limit` 건까지 모은다.

    가격 조건은 서버 필터로 보내고 받은 뒤 다시 거르지 않는다 (그 금액이 없는 거래 유형은 서버도 거르지 않는다).
    요청은 `MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS` 회에서 멈추고 `notes` 로 알린다.

    Args:
        conditions: 거래 유형·가격 조건 (`NaverTradeConditions`).
        sort: 정렬 (`COMPLEX_SORT_TYPE_BY_NAME` 의 이름). 서버가 정렬해 준다.
    """
    conditions = conditions or NaverTradeConditions()
    sort_type = COMPLEX_SORT_TYPE_BY_NAME[sort]
    price_filter = price_filter_of(conditions)
    listings: dict[str, Listing] = {}
    held: dict[str, list[tuple[str, str]]] = {}
    scan = PageScan(limit=limit, max_requests=MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS)

    # 구역 매물의 lastInfo 는 마지막 페이지까지 리스트로 온다 ([1, 710.5, '2652597531'] → [0, -279.6, …], 봉천4-1-3구역
    # 57건 2쪽, 2026-10-10 확인. 봉천4-1-3·봉천14구역 랭킹·가격낮은·최신순 12쪽, 2026-10-11 재확인. 봉천14구역 37건 2쪽,
    # 마지막 쪽 [1, 120.35…, '2649066878'], 2026-10-11 코드 리뷰 뒤 재확인). 실제로 정수가 오지 않아 단지 매물
    # (list_complex_articles)처럼 정수 커서를 따로 막지 않는다. 정수가 오면 요청 모델 검증에 걸리지만 일부러 두는 것이다
    # (docs/development/providers/naver.md 의 페이지네이션 절)
    def fetch(size: int, seed: str | None, last_info: Any) -> NaverArticlePageModel:
        return unwrap(
            client.run_request_complex_redevelopment_area_article_list_v1(
                NaverComplexRedevelopmentAreaArticleListV1RequestPayloadModel(
                    redevelopment_area_number=area_number,
                    size=size,
                    trade_types=[TRADE_CODE_BY_NAME[trade] for trade in conditions.trade_types],
                    article_sort_type=sort_type,
                    seed=seed,
                    last_info=last_info or [],
                    **price_filter,
                )
            ),
            '재개발 구역 매물',
        )

    scan_pages(scan, fetch, listing_keeper(listings, None, held=held), page_size=REDEVELOPMENT_PAGE_SIZE)
    notes: list[str] = []
    if scan.truncated:
        notes.append(note(
            '일부',
            f'네이버 차단을 피하려고 재개발 구역 매물 목록을 {MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS}번까지만 받았습니다. '
            '조건에 맞는 매물이 더 있을 수 있으니 조건을 좁혀 다시 검색하세요',
        ))
    notes += price_sort_notes(sort_type, conditions.trade_types)
    result = list(listings.values())[:limit]
    for listing in result:
        keep_unread_dates(held.get(listing.id, ()))
    notes += group_sort_notes(sort_type, result)
    # 구역 하나라 지역 대신 구역 매물의 조건만 좁히라고 한다 (단지 매물과 같다)
    notes += pagination_notes(
        scan.total, len(result), limit, scan.received, truncated=scan.truncated, null_items=scan.null_items,
        stalled=scan.stopped_short(resumed=False), exhausted=scan.exhausted, narrow='거래 유형·가격 조건',
    )
    notes += scan_null_items_notes(scan, '네이버 재개발 구역 매물')
    # 재개발 구역 매물은 이어 받지 않는다 (next 없음). 더 있는지만 알린다. 멈췄어도 네이버가 센 수를 다 받았으면 false,
    # 덜 받았으면 [일부] 안내와 같게 true 다 (단지 매물과 같다, 2026-11-24 리뷰)
    return NaverListingsResult(
        total=scan.total, returned=len(result), has_more=scan.cursor is not None or scan.stopped_short(resumed=False), listings=result,
        notes=notes,
    )
