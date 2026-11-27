import re

from jibsa.providers.daangn.api.models.response.common import DaangnArticleModel
from jibsa.providers.daangn.api.models.response.complex.detail import (
    DaangnComplexesResponseModel,
)
from jibsa.providers.daangn.api.models.response.listing import (
    DaangnArticlesResponseModel,
)
from jibsa.providers.daangn.api.models.response.review import (
    DaangnMapReviewsResponseModel,
)
from jibsa.providers.daangn.api.relay import (
    RelayRecordNotFoundError,
    RelayStore,
    extract_json_ld,
    extract_relay_store,
    records_of_type,
    resolve,
    root_field,
)

from typing import Any


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
        article=DaangnArticleModel.model_validate(resolve(store, record)),
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


def _region_field(store: RelayStore, prefix: str, region_id: int) -> Any:
    """`client:root` 에서 `prefix(` 로 시작하고 인자의 `regionId` 가 `region_id` 인 필드 값을 꺼낸다.

    `root_field` 는 접두어가 같은 첫 필드를 주므로, 다른 지역의 같은 필드가 스토어에 있어도 섞이지 않게 ID 로 고른다. 키 꼴은 두 가지다:
    `complexes(first:20,input:{"regionId":3363,"sort":"LIVED_REVIEW_COUNT_DESC"})`, `livedReviewDongPagesByRegion(regionId:3363)`.
    """
    pattern = re.compile(rf'regionId"?:{region_id}(?!\d)')
    for key, value in store.get('client:root', {}).items():
        if key.startswith(f'{prefix}(') and pattern.search(key):
            return value
    return None


def _ref_records(store: RelayStore, value: Any, depth: int) -> list[dict[str, Any]] | None:
    """`{'__refs': [...]}` 배열 참조를 레코드 목록으로 푼다. 배열 참조가 아니면(키가 없으면) None, 빈 배열이면 [].

    `depth` 는 `resolve` 와 같다. 레코드 안의 참조(건물 등)까지 펴려면 하나 더 준다.
    """
    if not (isinstance(value, dict) and '__refs' in value):
        return None
    return [record for record in resolve(store, value, depth=depth) if isinstance(record, dict)]


def _ref_count(value: Any) -> int:
    """`{'__refs': [...]}` 배열 참조의 원래 길이. `_ref_records` 가 null 참조·못 푼 레코드를 빼기 전의 수다. 배열 참조가 아니면 0."""
    refs = value.get('__refs') if isinstance(value, dict) else None
    return len(refs) if isinstance(refs, list) else 0


def parse_map_reviews_html(html: str, region_id: int) -> DaangnMapReviewsResponseModel:
    """구·동의 동네 후기 페이지 HTML 에서 후기 많은 단지·동별·건물별 후기 수를 꺼낸다. 후기 본문·작성자·이미지는 읽지 않는다.

    스토어 루트의 `complexes(...)`·`livedReviewDongPagesByRegion(...)`·`livedReviewBuildingPagesByRegion(...)` 중 인자의
    `regionId` 가 `region_id` 인 것만 읽는다. 동 목록은 구 후기 페이지에만 있다. 목록 키가 없으면 `dongs`·`buildings` 는 None(모름),
    빈 배열이면 [] 다. 단지 edge 는 null 이어도 한 자리로 넘겨 모델이 빈 항목으로 세게 하고(`null_items('complexes')`),
    동·건물 줄을 알 수 없어 뺀 수는 `dropped_dongs`·`dropped_buildings` 에 센다.

    Args:
        html: 후기 페이지 HTML.
        region_id: 페이지가 가리키는 구 또는 동의 당근 지역 ID.

    Raises:
        RelayStoreNotFoundError: HTML 에 스토어가 없을 때.
        RelayRecordNotFoundError: 스토어에 그 지역의 단지 목록(`complexes`) 연결이 없을 때.
    """
    store = extract_relay_store(html)
    connection = resolve(store, _region_field(store, 'complexes', region_id), depth=3)
    edges = connection.get('edges') if isinstance(connection, dict) else None
    # 단지 목록은 후기 많은 단지가 없는 구에도 빈 edges 로 온다 (2026-10-23 실측: 강남구 20곳, 울릉군 0곳). 없거나 모양이
    # 다르면 구조가 바뀐 것이라, 빈 목록으로 돌려 '이 지역에는 후기가 없다' 고 안내하지 않는다
    if not isinstance(edges, list):
        raise RelayRecordNotFoundError(f'complexes connection of region {region_id} not found in relay store')

    dong_ref = _region_field(store, 'livedReviewDongPagesByRegion', region_id)
    dong_records = _ref_records(store, dong_ref, depth=1)
    dongs: list[dict[str, Any]] | None = None
    if dong_records is not None:
        # 동 후기 줄의 `regionId` → 동 이름. 스토어의 `Region` 레코드(`originalId` ↔ `name3`)로 푼다.
        # `originalId` 가 없는 `Region` 레코드도 섞여 있고, 구·시도 레코드의 `name3` 은 빈 글자다.
        names: dict[str, str] = {}
        for region_record in records_of_type(store, 'Region'):
            original_id = region_record.get('originalId')
            name3 = region_record.get('name3')
            if original_id is not None and isinstance(name3, str) and name3:
                names[str(original_id)] = name3
        dongs = [
            {
                'regionId': record['regionId'],
                'name': names.get(str(record['regionId'])),
                'livedReviewCount': record.get('livedReviewCount'),
            }
            for record in dong_records
            if record.get('regionId') is not None
        ]

    building_ref = _region_field(store, 'livedReviewBuildingPagesByRegion', region_id)
    building_records = _ref_records(store, building_ref, depth=2)
    buildings: list[dict[str, Any]] | None = None
    if building_records is not None:
        # 건물을 가리키지 않거나 건물 ID 가 없는 줄은 건물을 알 수 없어 뺀다 (2026-11-20 실측: 강남구 1261개·역삼동 402개 모두 있었다)
        buildings = [
            {**record['building'], 'livedReviewCount': record.get('livedReviewCount')}
            for record in building_records
            if isinstance(record.get('building'), dict) and record['building'].get('originalId')
        ]

    # edge·node 가 null 이어도 자리를 지켜 None 으로 넘긴다. 모델이 null 원소를 빼며 세어 서비스가 상한 판정과 안내에 쓴다
    nodes: list[dict[str, Any] | None] = []
    for edge in edges:
        node = edge.get('node') if isinstance(edge, dict) else None
        nodes.append(node if isinstance(node, dict) else None)

    return DaangnMapReviewsResponseModel(
        complexes=nodes,
        dongs=dongs,
        buildings=buildings,
        dropped_dongs=_ref_count(dong_ref) - len(dongs) if dongs is not None else 0,
        dropped_buildings=_ref_count(building_ref) - len(buildings) if buildings is not None else 0,
    )
