from jibsa.providers.daangn.api.relay import (
    RelayRecordNotFoundError,
    RelayStore,
    extract_json_ld,
    extract_relay_store,
    records_of_type,
    resolve,
    root_field,
)
from jibsa.providers.daangn.api.response.common import DaangnArticleModel
from jibsa.providers.daangn.api.response.complex import DaangnComplexesResponseModel
from jibsa.providers.daangn.api.response.listing import DaangnArticlesResponseModel
from jibsa.providers.daangn.api.response.review import DaangnMapReviewsResponseModel

from typing import Any


def _article(store: RelayStore, record: dict[str, Any]) -> DaangnArticleModel:
    return DaangnArticleModel.model_validate(resolve(store, record))


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
