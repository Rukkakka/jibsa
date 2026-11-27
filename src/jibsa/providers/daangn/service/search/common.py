"""동·지도 범위·역·대학 주변 검색이 같이 쓰는 매물 변환과 안내."""

from jibsa.core.listing import note
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.response.common import DaangnArticleModel
from jibsa.providers.daangn.service.common.constants import LISTING_MAX_LIMIT
from jibsa.providers.daangn.service.common.listing import (
    article_to_listing,
    complex_building_notes,
    is_available,
    listing_budget_notes,
    no_trade_notes,
    trade_of,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
    DaangnNearbyListing,
    DaangnRegion,
)
from jibsa.providers.daangn.service.common.nearby import hidden_location_notes
from jibsa.providers.daangn.service.common.response import cursor_stopped_note
from jibsa.providers.daangn.service.region.area import with_center_sido


def to_listings(
    client: DaangnClient,
    articles: list[DaangnArticleModel],
    conditions: DaangnListingConditions,
    center: tuple[float, float],
    region: DaangnRegion | None,
    sido_cache: dict[tuple[str, str], str | None],
) -> list[tuple[DaangnArticleModel, DaangnNearbyListing]]:
    """받은 매물을 목록 순서대로 (원본, 결과 매물) 로 바꾼다. 동·지도 범위·역·대학 검색이 같이 쓴다.

    겹친 매물, 거래할 수 없는 매물(`is_available`), 보여 줄 거래가 없는 매물(`trade_of`)은 빼고 다시 채우지 않는다. 카드에
    시·도가 빠지면 지역 검색으로 채운다 (`with_center_sido`. 검색 중심 동 `region` 은 세종 매물에만 바로 쓴다). `sido_cache` 는
    찾은 시·도이고 이어 받기 표에 담아 다음 쪽이 같은 구·동을 다시 찾지 않게 한다 (`sido_cache_rows`). 받은 매물을 `[:limit]` 로 자르지 않는다. 서버가 `first` 만큼만
    주고 요청 크기도 limit 을 넘지 않는다 (2026-11-12 실측: 동 목록 first 2·7 → 2·7건, 지도 범위 목록 3 → 3건, 역 주변 목록 3·7 →
    3·7건). 자르면 이어 받기 커서가 잘린 매물 뒤를 가리켜 그 매물이 빠진다 (2026-11-12 리뷰 오탐).
    겹친 매물은 한 번에 받은 매물 안에서만 뺀다. 이어 받은 쪽(`--next`)과 앞 쪽은 커서로 이어져 겹치지 않는다 (2026-11-12 리뷰
    오탐에 실측: 서버가 `hasNextPage: false` 를 준 뒤 이어 받은 홍천군 내면 20+6건, 역삼동 20+20건이 limit 40 한 번과 순서까지 같았다).
    """
    seen: set[str] = set()
    converted: list[tuple[DaangnArticleModel, DaangnNearbyListing]] = []
    for article in articles:
        if article.original_id in seen or not is_available(article):
            continue
        seen.add(article.original_id)
        trade = trade_of(article, conditions)
        if trade is None:
            continue
        listing = article_to_listing(with_center_sido(client, article, region, sido_cache), center, trade=trade)
        if isinstance(listing, DaangnNearbyListing):
            converted.append((article, listing))
    return converted


def listing_notes(
    limit: int,
    articles: list[DaangnArticleModel],
    shown: list[DaangnArticleModel],
    *,
    has_more: bool,
    resumable: bool,
    resumed: bool,
    stopped: bool,
) -> list[str]:
    """받은 수·뺀 매물·거래 조건·단지 건물·숨긴 주소 안내. 동·지도 범위·역·대학 검색이 같이 쓴다 (`shown` 은 결과에 넣은 원본).

    `stopped` 는 목록이 다음이 있다면서 이어 받을 쪽을 주지 않아 멈췄는지다 (`connection_edges`). --limit 을 늘려도 같은
    자리에서 멈춰 --limit 안내 대신 멈췄다고 알린다.
    """
    # `articles` 는 이번 호출에서 받은 수라, 이어 받은 쪽이면 앞 결과를 뺀 '이번 쪽' 의 수로 말한다. 그냥 'N건에서 멈췄습니다' 면
    # 앞 결과에서 40건을 받았어도 이어 받은 첫 쪽이 비어 '0건에서 멈췄습니다' 로 읽힌다 (`listing_budget_notes` 도 resumed 를 가른다)
    received = f'앞 결과에 이어 받은 이번 쪽 {len(articles)}건' if resumed else f'{len(articles)}건'
    stopped_notes = [note('일부', cursor_stopped_note('매물 목록', received))] if stopped else []
    return (
        listing_budget_notes(
            limit, len(articles), len(shown), max_limit=LISTING_MAX_LIMIT, has_more=has_more, narrow='조건',
            narrowable=not stopped, resumable=resumable, resumed=resumed,
        )
        + stopped_notes
        + no_trade_notes(articles)
        + complex_building_notes(shown)
        + hidden_location_notes(shown)
    )
