from jibsa.providers.daangn.api.relay import (
    RelayRecordNotFoundError,
    RelayStore,
    extract_json_ld,
    extract_relay_store,
    records_of_type,
    resolve,
    root_field,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnRegionModel,
)
from jibsa.providers.daangn.api.response.complex import DaangnComplexesResponseModel
from jibsa.providers.daangn.api.response.listing import DaangnArticlesResponseModel
from jibsa.providers.daangn.api.response.review import DaangnMapReviewsResponseModel
from jibsa.providers.daangn.api.response.search import DaangnMapResponseModel

from typing import Any


def _article(store: RelayStore, record: dict[str, Any]) -> DaangnArticleModel:
    return DaangnArticleModel.model_validate(resolve(store, record))


def _feed_articles(store: RelayStore) -> tuple[list[tuple[dict[str, Any], str | None]], dict[str, Any] | None]:
    """지도 패널 피드(`surface: MAP`)의 (Article 레코드, edge 커서) 를 노출 순서대로 꺼낸다.

    피드 연결을 못 찾으면 스토어의 모든 Article 을 커서 없이 대신 돌려준다.
    """
    root = store.get('client:root', {})
    connection_keys = [
        key for key in root
        if key.startswith('articleFeed(') and '"surface":"MAP"' in key
    ] or [key for key in root if key.startswith('articleFeed(')]
    for key in connection_keys:
        # 피드 연결은 늘 참조(__ref)로 온다. 지도 페이지가 없는 동은 404 라 키 자체가 없다
        # (2026-10-10 실측: 역삼동은 참조, 잘못된 동·이도이동은 404). edges·node·article 도 null 이 아니라
        # 늘 객체로 온다 (같은 날 실측: 동 9곳, 매물 0건인 옹진군 연평면도 edges 는 빈 목록). 광고 카드처럼 article 이
        # null 인 카드는 없어 null 검사를 두지 않는다. 웹도 `e.node.article.region.name3` 를 검사 없이 읽는다
        # (2026-10-11 실측: SSR 5개 동 카드 200장·GraphQL 3개 동 180장 모두 article 이 객체였고 type 은 ARTICLE 만 왔다)
        connection = store.get(root[key].get('__ref', ''), {})
        articles: list[tuple[dict[str, Any], str | None]] = []
        for edge_ref in connection.get('edges', {}).get('__refs', []):
            edge = store.get(edge_ref, {})
            card = store.get(edge.get('node', {}).get('__ref', ''), {})
            article = store.get(card.get('article', {}).get('__ref', ''))
            if article is not None:
                # edge 마다 커서가 있어 그 매물 다음부터 피드로 이어 받을 수 있다 (2026-10-20 실측: 역삼동 20개 edge 모두
                # cursor 가 있고, 2번째 edge 커서로 받은 피드가 지도 페이지 3번째 매물부터 똑같이 이어졌다)
                articles.append((article, edge.get('cursor')))
        # 피드가 비어 있으면(매물 0건) 스토어에도 Article 이 없어 아래 대체 결과도 빈 목록이다. 스토어의 Article 은
        # 피드 매물뿐이다 (2026-10-10 실측: 연평면 0건·0건, 역삼동 등 5곳은 피드 20건·Article 20건)
        if articles:
            page_info = store.get(connection.get('pageInfo', {}).get('__ref', ''))
            return articles, page_info
    return [(record, None) for record in records_of_type(store, 'Article')], None


def parse_map_html(html: str, name3: str | None = None) -> DaangnMapResponseModel:
    """지도 페이지 HTML 에서 동 단위 매물 피드를 꺼낸다.

    Raises:
        RelayStoreNotFoundError: HTML 에 스토어가 없을 때.
    """
    store = extract_relay_store(html)
    records, page_info = _feed_articles(store)

    # 주변 동 매물의 지역(200곳 남짓)까지 펼치지 않도록 원본 레코드의 depth·name3 로 먼저 고른다
    region = next(
        (
            DaangnRegionModel.model_validate(resolve(store, record))
            for record in records_of_type(store, 'Region')
            if record.get('depth') == 3 and (name3 is None or record.get('name3') == name3)
        ),
        None,
    )

    seen: set[str] = set()
    articles: list[DaangnArticleModel] = []
    cursors: list[str | None] = []
    for record, cursor in records:
        article = _article(store, record)
        if article.original_id not in seen:
            seen.add(article.original_id)
            articles.append(article)
            cursors.append(cursor)

    total_count = root_field(store, 'articlesCount')
    return DaangnMapResponseModel(
        region=region,
        articles=articles,
        cursors=cursors,
        total_count=total_count if isinstance(total_count, int) else None,
        has_next_page=page_info.get('hasNextPage') if page_info else None,
        end_cursor=page_info.get('endCursor') if page_info else None,
    )


def parse_articles_html(html: str, original_id: int) -> DaangnArticlesResponseModel:
    """상세 페이지 HTML 에서 매물 하나를 꺼낸다. 제목은 JSON-LD 의 Product.name.

    Raises:
        RelayStoreNotFoundError: HTML 에 스토어가 없을 때.
        RelayRecordNotFoundError: 스토어에 해당 매물이 없을 때.
    """
    store = extract_relay_store(html)
    record = next(
        (
            record
            for record in records_of_type(store, 'Article')
            if record.get('originalId') == str(original_id)
        ),
        None,
    )
    # 없는 매물·거래 끝난 매물은 404 라 `get_listing` 이 ListingUnavailableError 로 바꾼다. 200 은 올라온 매물에만
    # 와서, 200 인데 매물이 없으면 구조가 바뀐 것으로 본다 (2026-10-10 실측: 매물 ID 17개)
    if record is None:
        raise RelayRecordNotFoundError(f'article {original_id} not found in relay records')

    title = next(
        (node.get('name') for node in extract_json_ld(html) if node.get('@type') == 'Product'),
        None,
    )
    return DaangnArticlesResponseModel(
        title=title,
        article=_article(store, record),
    )


def parse_complexes_html(html: str) -> DaangnComplexesResponseModel:
    """단지 페이지 HTML 에서 단지 하나를 꺼낸다.

    스토어 루트의 `complexByOriginalId(...)` 결과가 단지를 가리킨다. 없는 단지면 그 값의
    `complex` 가 null 이다 (페이지도 404).

    Raises:
        RelayStoreNotFoundError: HTML 에 스토어가 없을 때.
        RelayRecordNotFoundError: 루트 필드나 그 필드가 가리키는 단지 레코드가 없을 때.
    """
    store = extract_relay_store(html)
    output = root_field(store, 'complexByOriginalId')
    # 루트 필드는 있는 단지(200)에도 없는 단지(404, `complex: null`)에도 온다 (2026-10-23 실측: 10697092·999999999).
    # 없으면 구조가 바뀐 것이라, 빈 결과로 돌려 '없는 단지(NOT_FOUND)' 로 안내하지 않는다
    if not isinstance(output, dict):
        raise RelayRecordNotFoundError('complexByOriginalId not found in relay store')
    output = store.get(output.get('__ref', ''), output)
    reference = output.get('complex')
    if not reference:
        return DaangnComplexesResponseModel()
    # 단지 → proptierDanji → 면적 묶음 → 평형 까지 펼친다. 학교 도보 경로 같은 더 깊은 참조는 읽지 않는다
    complex_ = resolve(store, reference, depth=5)
    if complex_ is None:
        raise RelayRecordNotFoundError('complex record referenced by complexByOriginalId not found in relay store')
    return DaangnComplexesResponseModel(complex=complex_)


def parse_map_reviews_html(html: str) -> DaangnMapReviewsResponseModel:
    """구의 동네 후기 페이지 HTML 에서 후기 많은 단지를 꺼낸다. 후기 본문은 읽지 않는다.

    Raises:
        RelayStoreNotFoundError: HTML 에 스토어가 없을 때.
        RelayRecordNotFoundError: 스토어에 단지 목록(`complexes`) 연결이 없을 때.
    """
    store = extract_relay_store(html)
    connection = resolve(store, root_field(store, 'complexes'), depth=3)
    edges = connection.get('edges') if isinstance(connection, dict) else None
    # 단지 목록은 후기 많은 단지가 없는 구에도 빈 edges 로 온다 (2026-10-23 실측: 강남구 20곳, 울릉군 0곳). 없거나 모양이
    # 다르면 구조가 바뀐 것이라, 빈 목록으로 돌려 '이 지역에는 후기가 없다' 고 안내하지 않는다
    if not isinstance(edges, list):
        raise RelayRecordNotFoundError('complexes connection not found in relay store')
    return DaangnMapReviewsResponseModel(
        complexes=[edge['node'] for edge in edges if edge and edge.get('node')],
    )
