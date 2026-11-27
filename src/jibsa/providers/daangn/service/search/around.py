"""역·대학 주변 매물 검색 (search listings 의 --station·--university)."""

from collections.abc import Callable

from jibsa.core.listing import listing_as
from jibsa.core.notes import note
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.common import is_empty_property_filter
from jibsa.providers.daangn.api.models.request.search.around import (
    DaangnSubwayStationArticleConnectionRequestPayloadModel,
    DaangnUniversityArticleConnectionRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
)
from jibsa.providers.daangn.service.common.constants import STATION_PAGE_SIZE
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
    DaangnNearbyListing,
    DaangnRegion,
)
from jibsa.providers.daangn.service.common.nearby import (
    connection_edges,
    walk_minutes_to,
)
from jibsa.providers.daangn.service.common.response import unwrap_graphql
from jibsa.providers.daangn.service.region.area import (
    region_or_none,
    sido_cache_from_rows,
    sido_cache_rows,
)
from jibsa.providers.daangn.service.region.models.station import DaangnStation
from jibsa.providers.daangn.service.region.models.university import DaangnUniversity
from jibsa.providers.daangn.service.search.common import (
    listing_notes,
    to_listings,
)
from jibsa.providers.daangn.service.search.constants import (
    UNIVERSITY_DEFAULT_SALES_TYPES,
)
from jibsa.providers.daangn.service.search.models.around import (
    DaangnStationListing,
    DaangnStationSearchResult,
    DaangnUniversitySearchResult,
)

from typing import (
    Any,
    NamedTuple,
)


class _AroundListings(NamedTuple):
    """역·대학 주변 목록에서 한 번 받은 매물 (`_around_listings`)."""

    converted: list[tuple[DaangnArticleModel, DaangnNearbyListing]]
    has_more: bool
    next_position: dict[str, Any] | None
    notes: list[str]


def _around_listings(
    client: DaangnClient,
    fetch: Callable[[int, str | None], DaangnCommuteStationArticleConnectionModel],
    center: tuple[float, float],
    conditions: DaangnListingConditions,
    *,
    limit: int,
    after: str | None,
    region: DaangnRegion | None,
    sidos: list[list[str]] | None,
) -> _AroundListings:
    """역·대학 주변 목록을 `limit` 건 받아 결과 매물로 바꾼다. 같은 연결 타입이라 `search_station`·`search_university` 가 같이 쓴다.

    요청당 100건이고, 받은 카드 수로 예산을 세며 뺀 매물은 다시 채우지 않는다. 카드에는 시·도가 없어 지역 검색으로 채운다
    (`with_center_sido`). 검색 중심이 속한 동(`getRegionByCoordinate`)은 그때 세종 매물에만 쓰여, 못 찾아도 매물은 보여 줄 수
    있다. 받은 매물이 없으면 묻지 않는다. `region`·`sidos` 는 앞 결과가 찾은 동과 시·도다 (주면 다시 찾지 않는다). 예전에는 두
    검색이 이 흐름을 따로 두었다 (2026-11-12 리뷰).
    """
    edge_notes: list[str] = []
    edges, has_more, cursor, stopped, _ = connection_edges(fetch, limit, STATION_PAGE_SIZE, after=after, notes=edge_notes)
    articles = [edge.node.article for edge in edges if edge.node and edge.node.article]
    if region is None and articles:
        region = region_or_none(client, *center)
    sido_cache = sido_cache_from_rows(sidos)
    converted = to_listings(client, articles, conditions, center, region, sido_cache)
    resumable = bool(has_more and cursor)
    return _AroundListings(
        converted=converted,
        has_more=has_more,
        next_position=(
            {'after': cursor, 'region': region.model_dump() if region else None, 'sidos': sido_cache_rows(sido_cache)}
            if resumable else None
        ),
        notes=edge_notes + listing_notes(
            limit, articles, [article for article, _ in converted],
            has_more=has_more, resumable=resumable, resumed=after is not None, stopped=stopped,
        ),
    )


def search_station(
    client: DaangnClient,
    station: DaangnStation,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    after: str | None = None,
    region: DaangnRegion | None = None,
    sidos: list[list[str]] | None = None,
) -> DaangnStationSearchResult:
    """역 주변 매물을 당근 웹의 역 주변 목록 순서로 `limit` 건 조회한다 (`subwayStationArticleConnection`).

    조건(`DaangnListingConditions`)은 당근 서버에서 건다. 카드에 상태·거래 조건·역별 도보 시간이 다 있어 카드를
    다시 받지 않는다. 받는 방식은 대학 주변 목록과 같다 (`_around_listings`).
    `after`·`region`·`sidos` 는 이어 받기(`--next`)에서 앞 결과가 남긴 당근 커서, 역의 동, 찾은 시·도다 (주면 다시 찾지 않는다).

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    filtered = not is_empty_property_filter(property_filter)

    def fetch(size: int, after: str | None) -> DaangnCommuteStationArticleConnectionModel:
        response = client.run_request_subway_station_article_connection(
            DaangnSubwayStationArticleConnectionRequestPayloadModel(
                subway_station_poi_id=station.station_id,
                first=size,
                after=after,
                property_filter=property_filter,
            )
        )
        return unwrap_graphql(
            response,
            response.data.subway_station_article_connection if response.data else None,
            '역 주변 매물',
            conditions=filtered,
        )

    found = _around_listings(
        client, fetch, (station.lat, station.lng), conditions, limit=limit, after=after, region=region, sidos=sidos,
    )
    listings = [
        listing_as(DaangnStationListing, listing, walk_minutes=walk_minutes_to(article, station.name))
        for article, listing in found.converted
    ]
    return DaangnStationSearchResult(
        region=station,
        returned=len(listings),
        has_more=found.has_more,
        next_position=found.next_position,
        listings=listings,
        notes=found.notes,
    )


def search_university(
    client: DaangnClient,
    university: DaangnUniversity,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
    after: str | None = None,
    region: DaangnRegion | None = None,
    sidos: list[list[str]] | None = None,
) -> DaangnUniversitySearchResult:
    """대학 주변 매물을 웹 대학 페이지의 목록 순서로 `limit` 건 조회한다 (`universityArticleConnection`).

    역 주변 목록(`search_station`)과 같은 연결 타입이라 같은 방식으로 받는다 (`_around_listings`). 대학 둘레 범위는 당근
    서버가 정한다. 조건은 당근 서버에서 건다. `after`·`region`·`sidos` 는 이어 받기(`--next`)에서 앞 결과가 남긴 커서, 대학이
    있는 동, 찾은 시·도다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnListingConditions()
    property_filter = conditions.property_filter
    default_types = is_empty_property_filter(property_filter)  # 사용자 조건 없음 (아래에서 기본 종류를 채우기 전 값)
    if default_types:
        # 웹 대학 페이지는 지도 필터가 하나도 없을 때만 원룸·투룸·오피스텔을 기본으로 보낸다 (MapShell `Ff` 의 `??ke`, 조건이
        # 하나라도 있으면 그 필터 그대로). 역 주변 목록은 빈 필터(전체)가 기본이라 다르다 (2026-11-12 번들 대조)
        property_filter = property_filter.model_copy(update={'sales_types': list(UNIVERSITY_DEFAULT_SALES_TYPES)})

    def fetch(size: int, after: str | None) -> DaangnCommuteStationArticleConnectionModel:
        response = client.run_request_university_article_connection(
            DaangnUniversityArticleConnectionRequestPayloadModel(
                school_poi_id=university.university_id,
                first=size,
                after=after,
                property_filter=property_filter,
            )
        )
        return unwrap_graphql(
            response,
            response.data.university_article_connection if response.data else None,
            '대학 주변 매물',
            conditions=not default_types,
        )

    found = _around_listings(
        client, fetch, (university.lat, university.lng), conditions, limit=limit, after=after, region=region, sidos=sidos,
    )
    return DaangnUniversitySearchResult(
        region=university,
        returned=len(found.converted),
        has_more=found.has_more,
        next_position=found.next_position,
        listings=[listing for _, listing in found.converted],
        notes=(
            # 범위 안내는 다른 검색처럼 첫 결과에만 붙인다 (이어 받기는 같은 조건이다)
            (
                [note('범위', '조건이 없어 당근 웹 대학 페이지처럼 원룸·투룸·오피스텔만 찾았습니다. 다른 종류는 -t 로 고르세요')]
                if default_types and after is None else []
            )
            + found.notes
        ),
    )
