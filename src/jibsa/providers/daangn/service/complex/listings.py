"""단지 매물 목록 (search listings --complex)."""

from jibsa.core.errors import JibsaError
from jibsa.core.listing import Listing
from jibsa.core.notes import (
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.common import is_empty_property_filter
from jibsa.providers.daangn.api.models.request.complex.listings import (
    DaangnComplexArticlesInputModel,
    DaangnComplexArticlesRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnArticleModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.service.common.complex import (
    complex_not_found,
)
from jibsa.providers.daangn.service.common.constants import (
    COMPLEX_URL,
    LISTING_MAX_LIMIT,
)
from jibsa.providers.daangn.service.common.listing import (
    article_to_listing,
    complex_building_notes,
    is_available,
    listing_budget_notes,
    no_trade_notes,
    trade_of,
)
from jibsa.providers.daangn.service.common.models import DaangnListingConditions
from jibsa.providers.daangn.service.common.response import (
    cursor_stopped_note,
    next_cursor,
    stalled_page,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.complex.constants import (
    COMPLEX_LISTING_DEFAULT_SALES_TYPES,
    COMPLEX_LISTINGS_MAX_PAGES,
    COMPLEX_LISTINGS_PAGE_SIZE,
)
from jibsa.providers.daangn.service.complex.models.listings import (
    DaangnComplexListingsResult,
)
from jibsa.providers.daangn.service.region.area import with_sido


def list_complex_listings(
    client: DaangnClient,
    complex_id: int,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnComplexListingsResult:
    """단지 하나의 현재 매물을 모은다 (당근 단지 화면의 매물 탭). 조건은 search listings 와 같고 서버에서 건다.

    거래 완료·숨김 매물은 빼고, 거래 조건이 여럿이면 조건에 맞는 거래로 가격을 보여 준다 (search 와 같다).
    단지 매물이라 세대수·주차대수 조건은 받지 않는다.

    Raises:
        JibsaError: 세대수·주차대수 조건을 주면 INVALID_ARGUMENT, 없는 단지면 NOT_FOUND, 그 밖의 GraphQL 에러면
            UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 단지 매물 쿼리를 바꿨을 때.
    """
    conditions = conditions or DaangnListingConditions()
    if conditions.household_min is not None or conditions.household_max is not None or conditions.parking_min is not None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='단지 매물에는 세대수·주차대수 조건을 쓸 수 없습니다',
            hint='단지 하나의 매물이라 세대수·주차대수는 이미 정해져 있습니다. 그 조건을 빼고 다시 찾으세요',
        )
    property_filter = conditions.property_filter
    filtered = not is_empty_property_filter(property_filter)  # 사용자 조건 없음 (아래에서 기본 종류를 채우기 전 값)
    if not conditions.property_types:
        # 웹 단지 매물 패널은 종류를 고르지 않으면 늘 주거 5종(아파트·주택·오피스텔·원룸·투룸)을 보낸다 (`ComplexArticleListPanel`
        # 의 `F`, 단지 페이지 SEO 본문도 같다). 빈 목록(전체)으로 부르는 경로가 없어 상가·사무실 등은 -t 로 골랐을 때만 온다
        # (2026-11-12 번들 대조. 예전에는 전체를 보내 상가 매물이 섞였다)
        property_filter = property_filter.model_copy(update={'sales_types': list(COMPLEX_LISTING_DEFAULT_SALES_TYPES)})
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel]] = []
    after = None
    inspected = 0
    seen: set[str] = set()
    # 받은 서로 다른 매물 (거래 불가도 센다). 멈춤 안내의 수다. inspected 는 edge 누계라 같은 쪽이 되풀이되면 두 번 센다
    # (2026-11-10 리뷰. 출퇴근 역 목록도 이름으로 센다)
    received_ids: set[str] = set()
    received: list[DaangnArticleModel] = []
    # 서버는 빈 edge(null)도 한 자리로 세므로 빼고 읽은 수를 받은 자리에 더한다
    null_edges = 0
    has_more = False
    stopped = False
    page_capped = False
    for _ in range(COMPLEX_LISTINGS_MAX_PAGES):
        response = client.run_request_complex_articles(
            DaangnComplexArticlesRequestPayloadModel(
                complex_id=str(complex_id),
                first=min(COMPLEX_LISTINGS_PAGE_SIZE, limit - inspected),
                after=after,
                input=DaangnComplexArticlesInputModel(property_filter=property_filter),
            )
        )
        result = unwrap_graphql(
            response, response.data.complex_by_original_id if response.data else None, '단지 매물', conditions=filtered
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        connection = result.complex.articles
        # 단지의 매물 목록(articles) 자체가 null 이어도 페이지 정보가 없는 것이라 앞 쪽이 다음이 있다고 했으면 멈춘다 (stalled_page)
        if stalled_page(connection.page_info if connection else None, after):
            stopped = True
            break
        if connection:
            null_edges += connection.null_items('edges')
            inspected += len(connection.edges) + connection.null_items('edges')
        articles = [edge.node for edge in connection.edges if edge.node] if connection else []
        received_ids.update(article.original_id for article in articles)
        received += articles
        for article in articles:
            if article.original_id in seen or not is_available(article):
                continue
            seen.add(article.original_id)
            trade = trade_of(article, conditions)
            if trade is not None:
                matched.append((article, trade))
        page_info = connection.page_info if connection else None
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page_info and page_info.has_next_page) or len(matched) > limit
        if inspected >= limit or not has_more or page_info is None:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 을 늘려도 더 받지 못하니
        # 아래의 --limit 안내 대신 멈췄다고 알린다 (2026-11-10 리뷰: 같은 커서를 되풀이하면 같은 쪽을 6번 받고 '--limit 의
        # 최대값은 120입니다' 라고 했고, 커서가 비면 안내 없이 has_more 만 true 였다). 마지막 허용 쪽(6쪽)에서도 본다. 다음이
        # 있다면서 커서를 주지 않는 것은 몇 쪽째든 응답이 바뀐 것이라 멈춤 안내(업데이트 문구)가 맞다. 서버가 쪽마다 first 만큼
        # 주면(COMPLEX_PAGE_SIZE 주석) 6쪽째에 inspected 가 --limit 최대 120 에 닿아 위에서 먼저 끝난다. 하지만 서버가 first 보다 적게
        # 주면 쪽 상한(for 가 break 없이 끝남)에 먼저 닿아 inspected < limit 이고 has_more 인 채 끝나, 아래 '더 있음' 안내의
        # 조건(limit >= max_limit 또는 inspected >= limit)이 거짓이라 안내 없이 has_more 만 true 였다. 그래서 쪽 상한은
        # `stopped` 와 같은 갈래로 보아 따로 알린다 (`page_capped`. 2026-11-10 리뷰의 6쪽째 멈춤 지적은 first 만큼 줄 때만 오탐이었다)
        cursor = next_cursor(page_info, after, received=len(articles))
        if cursor is None:
            stopped = True
            break
        after = cursor
    else:
        # break 없이 끝났으면 쪽 상한에 닿은 것이다. 닿기 전 끝 조건(--limit 만큼 받음·다음 없음·pageInfo 없음)은 모두 break 다
        page_capped = True

    # 카드에는 시·도가 없어 단지가 있는 동을 지역 검색으로 한 번 채운다 (with_sido)
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[Listing] = []
    shown: list[DaangnArticleModel] = []
    for article, trade in matched[:limit]:
        listing = article_to_listing(with_sido(client, article, sido_cache), trade=trade)
        if listing is not None:
            listings.append(listing)
            shown.append(article)
    return DaangnComplexListingsResult(
        complex_id=str(complex_id),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        url=COMPLEX_URL.format(complex_id),
        notes=listing_budget_notes(
            limit, inspected, len(listings), max_limit=LISTING_MAX_LIMIT, has_more=has_more, narrow='조건',
            eligible=len(matched), narrowable=not (stopped or page_capped), dropped=null_edges,
        )
            + no_trade_notes(received)
            + (
                [note('일부', cursor_stopped_note('단지 매물', f'{len(received_ids)}건') + '. 나머지는 url 의 단지 페이지에서 확인하세요')]
                if stopped else []
            )
            + (
                [note(
                    '일부',
                    f'단지 매물 {len(received_ids)}건을 받고 쪽 수 상한({COMPLEX_LISTINGS_MAX_PAGES}쪽)에 닿아 멈췄습니다. '
                    '--limit 을 늘려도 더 받지 못합니다. 나머지는 url 의 단지 페이지에서 확인하세요',
                )]
                if page_capped else []
            )
            + complex_building_notes(shown)
            + ([null_items_note('당근 단지 매물', null_edges)] if null_edges else []),
    )
