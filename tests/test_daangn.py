import gzip
import json
from pathlib import Path

import httpx
import pytest

from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.parser import (
    parse_articles_html,
    parse_complexes_html,
)
from jibsa.providers.daangn.api.relay import resolve
from jibsa.providers.daangn.service.common import (
    DaangnListingConditions,
    article_to_listing,
)
from jibsa.providers.daangn.service.commute import search_commute
from jibsa.providers.daangn.service.complex import (
    list_complex_listings,
    list_region_complexes,
    search_complexes,
)
from jibsa.providers.daangn.service.listing import (
    detail_to_listing,
    get_listing,
)
from jibsa.providers.daangn.service.real_price import get_real_prices
from jibsa.providers.daangn.service.region import resolve_area


FIXTURES = Path(__file__).parent / 'fixtures' / 'daangn'


def html(name: str) -> str:
    return gzip.open(FIXTURES / f'{name}.html.gz', 'rt', encoding='utf-8').read()


def search_region() -> dict:
    return json.loads((FIXTURES / 'search_region.json').read_text(encoding='utf-8'))


def article_feed() -> dict:
    return json.loads((FIXTURES / 'article_feed.json').read_text(encoding='utf-8'))


def articles_count() -> dict:
    return json.loads((FIXTURES / 'articles_count.json').read_text(encoding='utf-8'))


def _is_region_search(request: httpx.Request) -> bool:
    """웹 지역 검색(`searchRegion`) 요청인지. 시·도 채우기·지역 해석이 부른다."""
    if request.url.host != 'realty.kr.karrotmarket.com':
        return False
    return json.loads(request.content)['extensions']['persistedQuery']['sha256Hash'] == DaangnClient.search_region_query_id


# --- client -----------------------------------------------------------------

def test_every_query_hash_has_web_query_name() -> None:
    # 주간 API 감시가 이 짝으로 웹 번들의 같은 이름 쿼리와 해시를 견준다 (#214). 짝이 빠진 해시는 바뀌어도 알 수 없다
    hashes = {name for name in dir(DaangnClient) if name.endswith('_query_id')}
    assert set(DaangnClient.web_query_names) == hashes


# --- relay ------------------------------------------------------------------

def test_resolve_stops_at_depth() -> None:
    store = {
        'a': {'__typename': 'A', 'next': {'__ref': 'b'}},
        'b': {'__typename': 'B', 'next': {'__ref': 'a'}},
    }
    resolved = resolve(store, store['a'], depth=2)
    assert resolved['next']['next']['next'] is None


# --- normalisation ----------------------------------------------------------

def test_undisclosed_manage_cost_items_are_unknown() -> None:
    # 항목을 밝히지 않은 매물도 껍데기 항목(COMMON/USED)이 오므로 모름(null)으로 둔다
    response = parse_articles_html(html('articles'), 1000001)
    article = response.article.model_copy(update={'manage_cost_detail_is_disclosed': False})
    detail = detail_to_listing(response.model_copy(update={'article': article}))
    assert (detail.manage_cost_includes, detail.manage_cost_excludes) == (None, None)


# --- service ----------------------------------------------------------------


def _graphql_payloads(requests: list[httpx.Request], query_id: str = DaangnClient.article_feed_query_id) -> list[dict]:
    bodies = [json.loads(request.content) for request in requests if request.url.host == 'realty.kr.karrotmarket.com']
    return [body for body in bodies if body['extensions']['persistedQuery']['sha256Hash'] == query_id]


def _feed_payloads(requests: list[httpx.Request]) -> list[dict]:
    return _graphql_payloads(requests)


def _feed_articles() -> list:
    """피드 픽스처의 매물 6건 (역삼동 5건·논현동 1건, 모두 판매중)."""
    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleFeedResponseModel,
    )

    feed = DaangnArticleFeedResponseModel.model_validate(article_feed()).data.article_feed
    return [edge.node.article for edge in feed.edges]


def _yeoksam_articles() -> list:
    """피드 픽스처의 역삼동 매물 5건. 동 클러스터 목록은 그 동 매물만 준다 (논현동 매물을 넣으면 시·도를 찾으려 지역 검색을 부른다)."""
    return [article for article in _feed_articles() if article.region and article.region.name3 == '역삼동']


def _yeoksam_area():
    from jibsa.providers.daangn.service.region import DaangnArea
    return DaangnArea(level='동', name1='서울특별시', name2='강남구', name3='역삼동', region_id=6035, lat=37.4954, lng=127.0333, zoom=14)


def _cluster_page(articles: list, first: int, *, has_next: bool = False, errors: list | None = None):
    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleByClusterIdResponseModel,
    )

    edges = [{'node': {'type': 'ARTICLE', 'article': article.model_dump(by_alias=True)}} for article in articles[:first]]
    page = {'edges': edges, 'pageInfo': {'endCursor': 'next' if has_next else None, 'hasNextPage': has_next}}
    return DaangnArticleByClusterIdResponseModel.model_validate(
        {'data': None if errors else {'articleByClusterId': page}, 'errors': errors or []}
    )


def _dong_client(articles: list, *, count: int | None = 30, payloads: list | None = None, errors: list | None = None):
    """동 클러스터 목록은 `articles` (또는 GraphQL `errors`), 동 거품 수는 `count` 를 주는 가짜 client. count 가 None 이면 수 조회가 실패한다."""
    from types import SimpleNamespace

    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleClustersResponseModel,
    )

    def cluster_list(payload):
        if payloads is not None:
            payloads.append(payload)
        return _cluster_page(articles, payload.first, errors=errors)

    def clusters(_):
        if count is None:
            return DaangnArticleClustersResponseModel.model_validate({'errors': [{'message': '알 수 없는 오류가 발생했어요'}]})
        return DaangnArticleClustersResponseModel.model_validate({'data': {'articleClusters': [
            {'originalId': 'REGION:6034', 'name': '논현동', 'count': 99},
            {'originalId': 'REGION:6035', 'name': '역삼동', 'count': count},
        ]}})

    return SimpleNamespace(run_request_article_by_cluster_id=cluster_list, run_request_article_clusters=clusters)


# 동 매물은 조건이 있든 없든 웹 지도에서 동을 누른 목록(articleByClusterId)으로 받고, 수는 그 동 거품의 수다
def test_dong_search_uses_web_cluster_list_and_bubble_count() -> None:
    from jibsa.providers.daangn.service.search import (
        REGION_CLUSTER_ZOOM,
        map_view_bounds,
        search_dong,
    )

    area = _yeoksam_area()
    feed = article_feed()['data']['articleFeed']
    clusters = {'data': {'articleClusters': [
        {'originalId': 'REGION:6034', 'name': '논현동', 'count': 99}, {'originalId': 'REGION:6035', 'name': '역삼동', 'count': 726},
    ]}}
    requests: list[httpx.Request] = []
    responses = {
        DaangnClient.article_by_cluster_id_query_id: {'data': {'articleByClusterId': {**feed, 'edges': feed['edges'][:3]}}},
        DaangnClient.article_clusters_query_id: clusters,
    }
    with make_graphql_client(responses, requests) as client:
        result = search_dong(client, area, conditions=DaangnListingConditions(trade_types=['월세'], rent_max=100), limit=3)
    property_filter = {'salesTypes': [], 'tradeTypes': ['MONTH'], 'monthlyPay': {'maxAmount': 100}}
    assert _graphql_payloads(requests, DaangnClient.article_by_cluster_id_query_id)[0]['variables'] == {
        'first': 3, 'input': {'clusterId': 'REGION:6035', 'propertyFilter': property_filter},
    }
    # 거품 수는 웹이 동 거품을 그리는 줌(12)의 화면 범위로 묻고, 쓰지 않는 지역 경계(1.4MB)는 받지 않는다
    bounds, _, _ = map_view_bounds(area.lat, area.lng, REGION_CLUSTER_ZOOM)
    assert _graphql_payloads(requests, DaangnClient.article_clusters_query_id)[0]['variables'] == {
        'input': {
            'clusterType': 'REGION', 'locationFilter': bounds.model_dump(by_alias=True), 'propertyFilter': property_filter,
            'zoomLevel': 8,
        },
        'includeBoundaries': False,
    }
    assert result.total == 726 and result.region.name3 == '역삼동'
    assert [listing.id for listing in result.listings] == ['1000101', '1000102', '1000103']
    assert result.has_more and result.next_position == {'after': 'cursor-5', 'total': 726, 'received': 3}

    # 조건이 하나도 없으면 웹처럼 propertyFilter 를 null 로 명시해 보낸다 (변수 생략이 아니다)
    requests.clear()
    with make_graphql_client(responses, requests) as client:
        search_dong(client, area, limit=3)
    assert _graphql_payloads(requests, DaangnClient.article_by_cluster_id_query_id)[0]['variables']['input'] == {
        'clusterId': 'REGION:6035', 'propertyFilter': None,
    }
    assert _graphql_payloads(requests, DaangnClient.article_clusters_query_id)[0]['variables']['input']['propertyFilter'] is None


# 동 목록은 매물이 남았는데도 hasNextPage 를 false 로 준다 (2026-11-12 실측: 홍천군 내면 26건이 20건 쪽에서 false). 쪽이 꽉 차면
# 다음 쪽도 받고, 받은 수가 동 거품 수에 닿으면 더 없다고 한다
def test_dong_search_reads_past_false_has_next_page() -> None:
    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleByClusterIdResponseModel,
    )
    from jibsa.providers.daangn.service.search import search_dong

    template = _feed_articles()[0]
    articles = [template.model_copy(update={'original_id': str(9000000 + index)}) for index in range(26)]
    payloads: list = []
    client = _dong_client(articles, count=26)

    def cluster_list(payload):
        payloads.append(payload)
        start = int(payload.after or 0)
        edges = [
            {'node': {'type': 'ARTICLE', 'article': article.model_dump(by_alias=True)}}
            for article in articles[start:start + payload.first]
        ]
        return DaangnArticleByClusterIdResponseModel.model_validate({'data': {'articleByClusterId': {
            'edges': edges, 'pageInfo': {'endCursor': str(start + len(edges)), 'hasNextPage': False},
        }}})

    client.run_request_article_by_cluster_id = cluster_list
    result = search_dong(client, _yeoksam_area(), limit=30)
    assert [payload.first for payload in payloads] == [20, 10]
    assert result.returned == 26 and not result.has_more
    assert any('이 26건이 전부' in note for note in result.notes)

    # 거품 수만큼 받았으면 쪽이 꽉 찼어도 더 없다. 이어 받기는 앞 결과가 받은 수까지 센다
    first = search_dong(client, _yeoksam_area(), limit=20)
    assert first.has_more and first.next_position == {'after': '20', 'total': 26, 'received': 20}
    rest = search_dong(client, _yeoksam_area(), limit=6, after='20', total=26, received=20)
    assert rest.returned == 6 and not rest.has_more


def test_dong_search_continues_when_count_fails() -> None:
    # 수 조회가 실패해도 검색은 하고, 모르는 수는 내지 않는다
    from jibsa.providers.daangn.service.search import search_dong

    result = search_dong(_dong_client(_yeoksam_articles(), count=None), _yeoksam_area())
    assert result.listings
    assert result.total is None
    assert result.notes[0].startswith('[실패]')


def test_dong_count_rate_limit_keeps_received_listings() -> None:
    # 수는 매물을 받은 뒤 세어, 요청 제한을 올리면 받은 매물까지 잃는다 (2026-11-12 리뷰)
    from jibsa.providers.daangn.service.search import search_dong

    client = _dong_client(_yeoksam_articles())
    client.run_request_article_clusters = _rate_limited
    result = search_dong(client, _yeoksam_area())
    assert result.listings and result.total is None
    assert result.notes[0].startswith('[실패] 요청 제한에 걸려')


def test_dong_graphql_error_is_upstream_error() -> None:
    from jibsa.core.errors import JibsaError
    from jibsa.providers.daangn.service.search import search_dong

    with pytest.raises(JibsaError) as exc:
        search_dong(_dong_client([], errors=[{'message': '알 수 없는 오류가 발생했어요'}]), _yeoksam_area())
    assert exc.value.code == 'UPSTREAM_ERROR'
    assert '알 수 없는 오류' in exc.value.message


def test_dong_budget_does_not_refill_expired_articles() -> None:
    from jibsa.providers.daangn.service.search import search_dong

    template = _feed_articles()[0]
    articles = [
        template.model_copy(update={'original_id': str(9000000 + index), 'is_hide': index < 5}) for index in range(20)
    ]
    payloads: list = []
    client = _dong_client(articles, payloads=payloads)
    client.run_request_article_by_cluster_id = lambda payload: (
        payloads.append(payload) or _cluster_page(articles, payload.first, has_next=True)
    )
    result = search_dong(client, _yeoksam_area(), limit=20)
    assert len(payloads) == 1 and payloads[0].first == 20
    assert result.returned == 15
    assert any('다시 채우지 않음' in note for note in result.notes)


def test_dong_search_excludes_invisible_and_keeps_reserved() -> None:
    from jibsa.providers.daangn.service.search import search_dong

    articles = _feed_articles()
    blocked = articles[0].model_copy(update={'invisible_infos': [{'__typename': 'CheckDenyInvisibleInfo'}]})
    reserved = articles[3].model_copy(update={'status': 'RESERVED'})
    traded = articles[5].model_copy(update={'status': 'TRADED'})
    result = search_dong(_dong_client([blocked, reserved, traded]), _yeoksam_area())
    assert [(listing.id, listing.status) for listing in result.listings] == [(reserved.original_id, '예약중')]


def _rate_limited(_) -> None:
    from jibsa.core.ratelimit import RateLimitedError

    raise RateLimitedError('daangn', 300.0, 'cooldown')


def _not_found(_) -> None:
    request = httpx.Request('GET', 'https://realty.daangn.com/map/x')
    raise httpx.HTTPStatusError('404', request=request, response=httpx.Response(404, request=request))


# 시·도 채우기는 주소를 다듬는 보조 조회라, 요청 제한에 걸려도 받아 둔 매물을 버리지 않는다
@pytest.mark.parametrize('lookup', [_not_found, _rate_limited])
def test_missing_sido_stays_when_lookup_fails(lookup) -> None:
    from jibsa.providers.daangn.service.search import search_dong

    article = _feed_articles()[0]
    neighbor = article.region.model_copy(update={'name1': None, 'name2': '고양시 덕양구', 'name3': '향동동'})
    client = _dong_client([article.model_copy(update={'region': neighbor})])
    client.run_request_search_region = lookup
    assert search_dong(client, _yeoksam_area()).listings[0].address == '고양시 덕양구 향동동'


# 웹 목록처럼 거래 유형만 보고 보여 줄 거래를 고르며, 맞는 거래가 없어도 매물을 빼지 않는다 (금액은 서버가 걸렀다)
@pytest.mark.parametrize(('conditions', 'expected'), [
    ({'trade_types': ['월세']}, 'MONTH'),
    ({}, 'BUY'),
    ({'trade_types': ['전세']}, 'BUY'),
    ({'rent_max': 50}, 'BUY'),
    ({'trade_types': ['매매', '월세']}, 'BUY'),
])
def test_trade_of_picks_by_trade_type_like_web(conditions: dict, expected: str) -> None:
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel
    from jibsa.providers.daangn.service.common import trade_of

    article = _feed_articles()[3].model_copy(update={
        'trades': [
            DaangnTradeModel.model_validate({'type': 'BUY', 'preferred': True, 'price': 39500}),
            DaangnTradeModel.model_validate({'type': 'MONTH', 'preferred': False, 'deposit': 1200, 'monthlyPay': 120}),
        ],
    })
    trade = trade_of(article, DaangnListingConditions(**conditions))
    assert trade is not None and trade.type == expected


def test_short_trade_is_short_term_rent() -> None:
    # 당근 단기임대(ShortTrade)는 보증금·월세가 있다. 모르는 조건으로 버리지 않고 단기임대로 내보낸다.
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel

    short = DaangnTradeModel.model_validate(
        {'__typename': 'ShortTrade', 'type': 'SHORT', 'preferred': True, 'deposit': 200, 'monthlyPay': 130}
    )
    listing = article_to_listing(_feed_articles()[3].model_copy(update={'trades': [short]}))
    assert (listing.trade_type, listing.deposit_manwon, listing.rent_manwon) == ('단기임대', 200, 130)


def test_year_trade_is_yearly_rent_without_monthly_rent() -> None:
    # 제주 연세(YearTrade)는 1년치를 한 번에 내는 거래라 월세로 읽히지 않게 rent_manwon 키 없이 yearly_rent_manwon 으로 낸다
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel

    year = DaangnTradeModel.model_validate(
        {'__typename': 'YearTrade', 'type': 'YEAR', 'preferred': True, 'deposit': 1000, 'yearlyPay': 1400}
    )
    data = article_to_listing(_feed_articles()[3].model_copy(update={'trades': [year]})).model_dump()
    assert (data['trade_type'], data['deposit_manwon'], data['yearly_rent_manwon']) == ('연세', 1000, 1400)
    assert 'rent_manwon' not in data and 'price_manwon' not in data


def _regions_client(nodes: list[dict]) -> DaangnClient:
    """지역 검색(`searchRegion`)이 `nodes` 중 검색어가 이름에 든 곳을 주는 클라이언트 (실제 검색도 이름이 비슷한 곳을 준다)."""
    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)['variables']['input']['query']
        edges = [
            {'node': {'centerCoordinate': {'lat': '37.5', 'lon': '127.0'}, 'mapViewDefaultZoomLevel': 5, **node}}
            for node in nodes if any(query in node[key] for key in ('name1', 'name2', 'name3'))
        ]
        return httpx.Response(200, json={'data': {'searchRegion': {'edges': edges, 'pageInfo': {'hasNextPage': False}}}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


# 같은 이름 동은 이름 앞에 붙인 구·시·도로 고른다. 글자가 들어 있는지로만 보면 '동구' 가 성동구에, '남구' 가 강남구에 맞아
# 엉뚱한 동을 고른다. '서울시' 는 서울의 송정동 두 곳에 맞아 첫 곳을 고르지 않고 멈춘다. 띄어 쓴 이름은 마디마다 맞아야 한다
@pytest.mark.parametrize(
    ('query', 'expected'),
    [
        ('동구 송정동', '대구광역시'), ('성동 송정동', '서울특별시'), ('서울시 송정동', 'REGION_AMBIGUOUS'), ('남구 송정동', None),
        ('서울 성동구 송정동', '서울특별시'), ('송정동', 'REGION_AMBIGUOUS'),
    ],
)
def test_qualified_name_matches_start_of_district_name(query: str, expected: str | None) -> None:
    from jibsa.core.errors import (
        RegionAmbiguousError,
        RegionNotFoundError,
    )

    nodes = [
        {'originalId': 1, 'name1': '서울특별시', 'name2': '성동구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
        {'originalId': 2, 'name1': '대구광역시', 'name2': '동구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
        {'originalId': 3, 'name1': '서울특별시', 'name2': '강남구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
    ]
    with _regions_client(nodes) as client:
        if expected is None:
            with pytest.raises(RegionNotFoundError):
                resolve_area(client, query)
            return
        if expected == 'REGION_AMBIGUOUS':
            with pytest.raises(RegionAmbiguousError) as error:
                resolve_area(client, query)
            assert error.value.details['candidates'][:2] == ['서울특별시 성동구 송정동', '서울특별시 강남구 송정동'] or query == '송정동'
            return
        area = resolve_area(client, query)
    assert area.name1 == expected and area.level == '동'


# 웹 검색창처럼 이름이 정확히 같은 곳만 쓴다. 시·도와 구가 있는 시는 그 아래 구를, 이름이 같은 곳이 없으면 비슷한 지역을 후보로 준다.
# 후보는 그대로 다시 넣으면 찾히는 이름이다 (시·도의 구는 시·도까지 붙인다. 짧은 '강서구' 는 부산·서울 2곳이다)
@pytest.mark.parametrize(('query', 'candidates'), [
    ('서울', ['서울특별시 강남구', '서울특별시 강동구']),
    ('수원시', ['수원시 권선구', '수원시 영통구']),
    ('성수동', ['서울특별시 성동구 성수동1가', '서울특별시 성동구 성수동2가']),
])
def test_region_that_cannot_be_searched_as_is_asks_to_choose(query: str, candidates: list[str]) -> None:
    from jibsa.core.errors import JibsaError

    nodes = [
        {'originalId': 1, 'name1': '서울특별시', 'name2': '', 'name3': '', 'name': '서울특별시', 'depth': 1},
        {'originalId': 381, 'name1': '서울특별시', 'name2': '강남구', 'name3': '', 'name': '강남구', 'depth': 2},
        {'originalId': 382, 'name1': '서울특별시', 'name2': '강동구', 'name3': '', 'name': '강동구', 'depth': 2},
        {'originalId': 1270, 'name1': '경기도', 'name2': '수원시 권선구', 'name3': '', 'name': '수원시 권선구', 'depth': 2},
        {'originalId': 1271, 'name1': '경기도', 'name2': '수원시 영통구', 'name3': '', 'name': '수원시 영통구', 'depth': 2},
        {'originalId': 6100, 'name1': '서울특별시', 'name2': '성동구', 'name3': '성수동1가', 'name': '성수동1가', 'depth': 3},
        {'originalId': 6101, 'name1': '서울특별시', 'name2': '성동구', 'name3': '성수동2가', 'name': '성수동2가', 'depth': 3},
    ]
    with _regions_client(nodes) as client, pytest.raises(JibsaError) as error:
        resolve_area(client, query)
    assert error.value.code == 'REGION_AMBIGUOUS'
    assert error.value.details['candidates'][:2] == candidates


# 안내의 예시는 그대로 다시 넣으면 찾혀야 한다. 구 이름까지 같은 동(서울·대구 중구 태평로2가)은 시·도까지 붙이고, 동을 받지 않는
# 명령(인기 급상승 단지)은 동을 고르게 하지 않고 그 동들의 구를 준다. 예전에는 둘 다 예시를 따르면 또 막혔다
def test_same_name_dong_hint_resolves_when_reentered() -> None:
    from jibsa.core.errors import (
        JibsaError,
        RegionAmbiguousError,
    )

    nodes = [
        {'originalId': 1, 'name1': '서울특별시', 'name2': '중구', 'name3': '태평로2가', 'name': '태평로2가', 'depth': 3},
        {'originalId': 2, 'name1': '대구광역시', 'name2': '중구', 'name3': '태평로2가', 'name': '태평로2가', 'depth': 3},
    ]
    with _regions_client(nodes) as client:
        with pytest.raises(RegionAmbiguousError) as ambiguous:
            resolve_area(client, '태평로2가')
        assert "'서울특별시 중구 태평로2가'" in (ambiguous.value.hint or '')
        assert resolve_area(client, '서울특별시 중구 태평로2가').name1 == '서울특별시'
        with pytest.raises(JibsaError) as invalid:
            resolve_area(client, '태평로2가', levels=frozenset({'구', '시도'}))
    assert invalid.value.code == 'INVALID_ARGUMENT'
    assert invalid.value.details['candidates'] == ['서울특별시 중구', '대구광역시 중구']


def test_unavailable_articles_are_excluded() -> None:
    from jibsa.core.errors import ListingUnavailableError
    from jibsa.providers.daangn.service.common import is_available

    articles = _feed_articles()
    traded = articles[0].model_copy(update={'status': 'TRADED'})
    denied = articles[1].model_copy(update={'invisible_reason': 'CHECK_DENY'})
    hidden = articles[2].model_copy(update={'is_hide': True})
    # 예약중은 계약이 깨질 수 있어 웹처럼 보여 주고 status 로 알린다
    reserved = articles[3].model_copy(update={'status': 'RESERVED'})
    assert is_available(articles[3]) and is_available(reserved)
    assert article_to_listing(reserved).status == '예약중' and article_to_listing(articles[3]).status == '판매중'
    assert not any(is_available(article) for article in (traded, denied, hidden))

    response = parse_articles_html(html('articles'), 1000001)
    response.article.status = 'TRADED'
    with pytest.raises(ListingUnavailableError) as exc:
        detail_to_listing(response)
    assert exc.value.details['listing_status'] == 'TRADED'

    # 진행 중이어도 아는 거래 조건이 없으면 목록에서처럼 거래 불가로 본다
    response = parse_articles_html(html('articles'), 1000001)
    response.article.trades = []
    with pytest.raises(ListingUnavailableError) as exc:
        detail_to_listing(response)
    assert exc.value.code == 'LISTING_UNAVAILABLE'
    assert exc.value.details['reason'] == 'NO_TRADE_INFO'
    assert '거래 조건 없음' in exc.value.hint


# 웹 상세처럼 비활성 중개소의 매물은 막는다. 목록 카드에는 중개소 상태가 없어 상세에서만 본다. 상태를 모르면 막지 않는다
@pytest.mark.parametrize(('status', 'blocked'), [('INACTIVE', True), ('ACTIVE', False), (None, False)])
def test_detail_blocks_inactive_broker(status: str | None, blocked: bool) -> None:
    from jibsa.core.errors import ListingUnavailableError
    from jibsa.providers.daangn.api.response.common import DaangnBizProfileModel

    response = parse_articles_html(html('articles'), 1000001)
    article = response.article.model_copy(update={'biz_profile': DaangnBizProfileModel(originalId='1', status=status)})
    response = response.model_copy(update={'article': article})
    if not blocked:
        assert detail_to_listing(response).id == '1000001'
        return
    with pytest.raises(ListingUnavailableError) as exc:
        detail_to_listing(response)
    assert exc.value.details['reason'] == 'BIZ_PROFILE_INACTIVE'


def test_missing_article_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='<html></html>')

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client, pytest.raises(ListingUnavailableError):
        get_listing(client, 2000000)


def _multi_trade_detail():
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel

    response = parse_articles_html(html('articles'), 1000001)
    trades = [
        DaangnTradeModel.model_validate({'type': 'BUY', 'preferred': True, 'price': 17500}),
        DaangnTradeModel.model_validate({'type': 'BORROW', 'preferred': False, 'deposit': 16000}),
        DaangnTradeModel.model_validate({'type': 'MONTH', 'preferred': False, 'deposit': 12500, 'monthlyPay': 30}),
    ]
    return response.model_copy(update={'article': response.article.model_copy(update={'trades': trades})})


def test_detail_with_trade_not_offered_shows_representative_trade() -> None:
    # 매물에 없는 거래 조건을 달라면 웹 상세처럼 대표 조건을 보여 주고 알린다 (예전에는 TRADE_NOT_OFFERED 에러)
    detail = detail_to_listing(_multi_trade_detail(), '단기임대')
    assert (detail.trade_type, detail.price_manwon) == ('매매', 17500)
    assert detail.other_trades == ['전세 16000', '월세 12500/30']
    assert detail.notes == ['[참고] 이 매물에는 단기임대 조건이 없어 대표 조건(매매 17500)을 보여 줍니다. 다른 조건은 other_trades 에 있습니다']
    assert detail_to_listing(_multi_trade_detail(), '월세').notes == []


# --- property filter ----------------------------------------------------------

def test_property_filter_uses_daangn_web_codes() -> None:
    property_filter = DaangnListingConditions(
        property_types=['원룸', '공장·창고'],
        trade_types=['월세', '단기임대'],
        deposit_min=500,
        rent_max=70,
        rent_includes_manage_cost=True,
        area_min=20,
        area_max=33.5,
        floors=['반지하', '10층이상'],
        room_counts=['2개'],
        structures=['분리형'],
        building_approval='10년이내',
        deal='직거래',
        options=['반려동물가능', '엘리베이터'],
        move_in_now=True,
    ).property_filter
    assert property_filter.model_dump(by_alias=True, exclude_none=True) == {
        'salesTypes': ['ONE_ROOM', 'FACTORY'],
        'tradeTypes': ['MONTH', 'SHORT'],
        'depositPay': {'minAmount': 500},
        'monthlyPay': {'maxAmount': 70},
        'monthlyPayIncludesManageCost': True,
        # 면적은 문자열로 보내야 하고 단위가 꼭 있어야 한다
        'minArea': '20',
        'maxArea': '33.5',
        'areaUnit': 'SQUARE_METER',
        'floor': ['SEMI_BASEMENT', 'TENTH_OR_MORE'],
        'roomCounts': ['TWO'],
        'subSalesTypes': ['SPLIT_ROOM'],
        'buildingApprovalDate': ['LESS_10YEARS'],
        'dealType': 'DIRECT',
        'options': ['PET', 'ELEVATOR'],
        'moveInNow': True,
    }


@pytest.mark.parametrize('sales_type,room_count,room_type', [
    # 분리형원룸으로 올렸어도 방이 2개면 투룸이다 (실측). 방 수를 모르는 목록은 원룸 구조를 쓴다
    ('SPLIT_ONE_ROOM', 2, '투룸'),
    ('SPLIT_ONE_ROOM', None, '분리형원룸'),
    ('OFFICETEL', 4, '포룸이상'),
    ('OFFICETEL', 1, None),
])
def test_room_type_prefers_room_count(sales_type: str, room_count: int | None, room_type: str | None) -> None:
    article = _feed_articles()[0]
    article = article.model_copy(update={
        'sales_type': article.sales_type.model_copy(update={'type': sales_type}),
        'room_count': room_count,
    })
    assert article_to_listing(article).room_type == room_type


# --- 지도 범위 검색 (articleFeed 좌표 범위) ---------------------------------

def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


def make_graphql_client(
    responses: dict[str, dict] | None = None,
    requests: list[httpx.Request] | None = None,
) -> DaangnClient:
    """GraphQL 은 persisted query 해시로 응답을 고른다. `responses` 로 해시별 응답을 바꾼다."""
    client = DaangnClient()
    by_hash = {
        client.article_feed_query_id: article_feed(),
        client.articles_count_query_id: articles_count(),
        client.get_region_by_coordinate_query_id: fixture('get_region_by_coordinate'),
        client.search_region_query_id: search_region(),
        **(responses or {}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        query_id = json.loads(request.content)['extensions']['persistedQuery']['sha256Hash']
        return httpx.Response(200, json=by_hash[query_id])

    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return client


REJECTED = {'errors': [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]}


# 웹 지도 목록과 같이 데스크톱 화면 범위와 줌의 resolution 을 보내고, 순서를 바꾸지 않는다
def test_map_area_sends_web_view_bounds_and_keeps_order() -> None:
    from jibsa.providers.daangn.service.search import (
        map_view_bounds,
        search_map_area,
    )

    requests: list[httpx.Request] = []
    with make_graphql_client(requests=requests) as client:
        result = search_map_area(client, 37.5, 127.036, zoom=15, limit=5)
    payload = _graphql_payloads(requests)[0]['variables']
    bounds, width_km, height_km = map_view_bounds(37.5, 127.036, 15)
    assert payload['input']['locationFilter'] == bounds.model_dump(by_alias=True)
    assert payload['input']['resolution'] == 9 and payload['first'] == 5
    assert (width_km, height_km) == (result.width_km, result.height_km) == (1.6, 1.7)
    feed_ids = [edge['node']['article']['originalId'] for edge in article_feed()['data']['articleFeed']['edges']]
    assert [listing.id for listing in result.listings] == [id_ for id_ in feed_ids if id_ in {listing.id for listing in result.listings}]


def test_map_area_rejected_feed_query_raises() -> None:
    from jibsa.providers.daangn.service.common import FeedQueryRejectedError
    from jibsa.providers.daangn.service.search import search_map_area

    with make_graphql_client({DaangnClient.article_feed_query_id: REJECTED}) as client:
        with pytest.raises(FeedQueryRejectedError):
            search_map_area(client, 37.5, 127.036, zoom=15)


# 첫 결과가 동을 못 찾았으면(region None) 역·대학 주변 목록처럼 이어 받기에서 다시 찾는다. 매물 수는 다시 세지 않는다
# (첫 결과의 좌표 → 동 조회 실패는 실제 API 로 만들 수 없다)
def test_map_area_resume_finds_missing_region_again() -> None:
    from jibsa.providers.daangn.service.search import search_map_area

    requests: list[httpx.Request] = []
    with make_graphql_client(requests=requests) as client:
        result = search_map_area(client, 37.5, 127.036, zoom=15, limit=5, after='c1', total=30)
    assert len(_graphql_payloads(requests, DaangnClient.get_region_by_coordinate_query_id)) == 1
    assert not _graphql_payloads(requests, DaangnClient.articles_count_query_id)
    assert result.region is not None and result.total == 30


def _same_name_stations_client(requests: list[httpx.Request]) -> DaangnClient:
    """이름이 같은 역 두 곳(경기·서울)을 주고, 좌표 → 동은 위도로 어느 역인지 가려 답한다."""
    stations = {'data': {'searchSubwayStationPois': [
        {'id': '1', 'stationName': '테스트', 'lineNames': ['테스트1호선'], 'coordinate': {'lat': '37.49', 'lon': '127.49'}},
        {'id': '2', 'stationName': '테스트', 'lineNames': ['테스트5호선'], 'coordinate': {'lat': '37.52', 'lon': '126.88'}},
        {'id': '3', 'stationName': '테스트구청', 'lineNames': ['테스트2호선'], 'coordinate': {'lat': '37.51', 'lon': '127.04'}},
    ]}}

    def region(name1: str, name2: str) -> dict:
        return {'data': {'getRegionByCoordinate': {'name1': name1, 'name2': name2, 'name3': '테스트동', 'depth': 3, 'originalId': 1}}}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if body['extensions']['persistedQuery']['sha256Hash'] == DaangnClient.search_subway_station_pois_query_id:
            return httpx.Response(200, json=stations)
        lat = float(body['variables']['coordinate']['lat'])
        return httpx.Response(200, json=region('경기도', '양평군') if lat < 37.5 else region('서울특별시', '영등포구'))

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


# 같은 이름의 역은 웹 역 화면처럼 첫 역을 쓰고 다른 역을 알린다. 안내에 나온 노선 붙인 이름을 주면 그 역을 고른다
def test_same_name_station_is_noted_and_line_picks_it() -> None:
    from jibsa.providers.daangn.service.region import (
        find_station,
        same_station_notes,
    )

    requests: list[httpx.Request] = []
    with _same_name_stations_client(requests) as client:
        first = find_station(client, '테스트역')
        assert first is not None and first.lines == ['테스트1호선']
        assert first.others == ['테스트5호선 테스트역']
        assert "--station '테스트5호선 테스트역'" in same_station_notes(first)[0]
        chosen = find_station(client, '테스트5호선 테스트역')
        assert chosen is not None and chosen.lines == ['테스트5호선'] and chosen.others == []
        assert find_station(client, '테스트9호선 테스트역') is None
    # 역 검색 한 번씩이다 (좌표 → 동을 묻지 않는다)
    assert len(requests) == 3


# --- 단지 (complexes 페이지, searchComplexes) ----------------------------------


def test_parse_missing_complex_page_returns_none() -> None:
    # 없는 단지 페이지(404)도 스토어는 있고 결과의 complex 가 null 이다
    page = (
        '<script>$_TSR.router=($R=>$R[0]={dehydratedData:$R[1]={relayRecords:$R[2]={'
        '"client:root":$R[3]={"complexByOriginalId(originalId:\\"1\\")":$R[4]={__ref:"out"}},'
        'out:$R[5]={__typename:"ComplexByOriginalIdOutput",complex:null}}}})($R["tsr"])</script>'
    )
    assert parse_complexes_html(page).complex is None


# --- 단지 실거래가 (complexByOriginalId) ----------------------------------------

def real_price_client(
    requests: list[dict] | None = None,
    body: dict | None = None,
) -> DaangnClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(json.loads(request.content)['variables'])
        data = body or json.loads((FIXTURES / 'complex_by_original_id.json').read_text(encoding='utf-8'))
        return httpx.Response(200, json=data)

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_real_prices_rent_scans_limited_pages() -> None:
    # 전월세가 계속 이어지는데 원하는 유형이 모자라면 최근 24페이지까지만 보고 안내한다
    body = json.loads((FIXTURES / 'complex_by_original_id.json').read_text(encoding='utf-8'))
    body['data']['complexByOriginalId']['complex']['borrowTransactions']['pageInfo']['hasNextPage'] = True
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content)['variables'])
        body['data']['complexByOriginalId']['complex']['borrowTransactions']['pageInfo']['endCursor'] = f'r{len(requests) + 14}'
        return httpx.Response(200, json=body)

    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        result = get_real_prices(client, 9000001, trade_type='전세', limit=120)
    assert len(requests) == 24
    assert requests[1]['borrowAfter'] == 'r15'
    assert result.has_more is True
    assert result.notes and '120건' in result.notes[0]


@pytest.mark.parametrize('cursor,requests_count', [(None, 1), ('repeated', 2)])
def test_real_prices_do_not_repeat_broken_pages(cursor: str | None, requests_count: int) -> None:
    body = fixture('complex_by_original_id')
    body['data']['complexByOriginalId']['complex']['borrowTransactions']['pageInfo'] = {
        'hasNextPage': True, 'endCursor': cursor,
    }
    requests: list[dict] = []
    with real_price_client(requests, body) as client:
        result = get_real_prices(client, 9000001, trade_type='전세', limit=120)
    assert len(requests) == requests_count
    assert result.returned == 3
    assert result.has_more
    # 멈춘 까닭은 업데이트 문구와 함께 알리고, 당근 사이트로 가라는 말은 [일부] 한 줄에만 둔다
    assert any('멈췄습니다' in note and UPDATE_MAYBE_NEEDED in note for note in result.notes)
    assert sum('당근' in note and '확인' in note for note in result.notes) == 1


def test_real_prices_last_page_echoing_cursor_is_the_end() -> None:
    # 다음 페이지가 없다는 마지막 쪽이면 커서가 요청 커서와 같아도 되풀이로 보지 않는다. 실제 당근은 늘 새 커서나 null 을
    # 주어 실제 API 로는 이 상태를 만들 수 없다 (_collect_pages 주석)
    def handler(request: httpx.Request) -> httpx.Response:
        body = fixture('complex_by_original_id')
        first = json.loads(request.content)['variables'].get('borrowAfter') is None
        body['data']['complexByOriginalId']['complex']['borrowTransactions']['pageInfo'] = {
            'hasNextPage': first, 'endCursor': 'c1',
        }
        return httpx.Response(200, json=body)

    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        result = get_real_prices(client, 9000001, trade_type='전세', limit=120)
    assert result.returned == 6
    assert result.has_more is False
    assert not any('멈췄습니다' in note for note in result.notes)


def test_real_prices_null_page_info_after_next_page_stops_with_notice() -> None:
    # 다음이 있다던 쪽 뒤에 pageInfo 가 null 이면 목록 끝이 아니라 응답이 바뀐 것이다. 조용히 끝내면 받은 일부를 전부처럼
    # 내고 매일 API 감시도 정상으로 센다 (stalled_page. 실제 API 로는 응답을 바꿔야만 만들 수 있다)
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        variables = json.loads(request.content)['variables']
        requests.append(variables)
        body = fixture('complex_by_original_id')
        body['data']['complexByOriginalId']['complex']['borrowTransactions']['pageInfo'] = (
            None if variables.get('borrowAfter') else {'hasNextPage': True, 'endCursor': 'c1'}
        )
        return httpx.Response(200, json=body)

    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        result = get_real_prices(client, 9000001, trade_type='전세', limit=120)
    assert [variables.get('borrowAfter') for variables in requests] == [None, 'c1']
    assert result.returned == 3
    assert result.has_more is True
    assert any('멈췄습니다' in note and UPDATE_MAYBE_NEEDED in note for note in result.notes)


# --- 출퇴근 검색 (nearestCommuteStation → commuteStations → commuteStationArticleConnection) ----

def complex_article_cards() -> list[dict]:
    return [edge['node'] for edge in fixture('complex_articles')['data']['complexByOriginalId']['complex']['articles']['edges']]


def commute_client(
    requests: list[tuple[str, dict]] | None = None,
    nearest: dict | None = None,
    stations_body: dict | None = None,
) -> DaangnClient:
    # 역마다 다른 매물을 준다. 2000101 은 두 역에 걸린다. 회사 역(테스트역)은 웹처럼 찾지 않는다
    ids_by_station = {'가까운역': ['2000104', '2000101'], '먼역': ['2000103', '2000101']}
    # 역 주변 매물도 단지 매물 목록과 같은 매물 카드(DaangnArticleModel)로 온다
    cards = {card['originalId']: card for card in complex_article_cards()}
    walk = {'2000101': ('먼역', 5), '2000104': ('가까운역', 4)}
    for article_id, (name, minutes) in walk.items():
        cards[article_id]['subwayStations'] = [
            {'station': {'stationName': name, 'lineNumber': ['테스트1호선']}, 'durationMinutes': minutes},
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_region_search(request):
            # 카드에 시·도가 없는 동은 지역 검색으로 채운다
            return httpx.Response(200, json=search_region())
        body = json.loads(request.content)
        query = body['extensions']['persistedQuery']['sha256Hash']
        variables = body['variables']
        if query == DaangnClient.nearest_commute_station_query_id:
            name = 'nearest'
            data = nearest or fixture('nearest_commute_station')
        elif query == DaangnClient.commute_stations_query_id:
            name = 'stations'
            data = stations_body or fixture('commute_stations')
        elif query == DaangnClient.commute_station_article_connection_query_id:
            name = 'station'
            data = fixture('commute_station_article_connection')
            # 당근처럼 요청한 수(first)까지만 준다 (2026-11-12 실측: 강남역 통근 --limit 1 은 10역 모두 1건)
            data['data']['commuteStationArticleConnection']['edges'] = [
                {'node': {'article': cards[article_id]}}
                for article_id in ids_by_station[variables['stationName']][:variables['first']]
            ]
        else:
            name = 'region'
            data = fixture('get_region_by_coordinate')
        if requests is not None:
            requests.append((name, variables))
        return httpx.Response(200, json=data)

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_commute_unknown_workplace_walk_is_not_zero() -> None:
    nearest = fixture('nearest_commute_station')
    nearest['data']['nearestCommuteStation']['walkingMinutesToStation'] = None
    with commute_client(nearest=nearest) as client:
        result = search_commute(client, 37.5, 127.03)
    assert result.listings
    # 웹의 '편도 N분' 은 회사 도보 + 지하철이라 회사 도보를 모르면 null 이다
    assert all(group.one_way_minutes is None for group in result.stations)


def test_commute_unknown_subway_time_is_not_zero() -> None:
    stations = fixture('commute_stations')
    stations['data']['commuteStations'][0]['durationMinutes'] = None
    stations['data']['commuteStations'][1]['transferCount'] = None
    with commute_client(stations_body=stations) as client:
        result = search_commute(client, 37.5, 127.03)
    assert '가까운역' not in [station.station_name for station in result.stations]
    assert not any(item.commute_station == '가까운역' for item in result.listings)
    assert all(group.transfers is None for group in result.stations if group.station_name == '먼역')
    assert any('지하철 시간을 모르는 역' in note for note in result.notes)


# 회사 역은 웹처럼 넣지 않아 --max-minutes 안에 역이 없으면 빈 결과다. 에러 대신 회사 역 주변을 볼 명령을 알린다
def test_commute_no_station_within_max_minutes_notes_workplace_station() -> None:
    requests: list[tuple[str, dict]] = []
    with commute_client(requests) as client:
        result = search_commute(client, 37.5, 127.03, max_minutes=1)
    assert result.stations == [] and result.listings == []
    assert not [name for name, _ in requests if name == 'station']
    assert any(
        '지하철 1분 안에는 조건에 맞는 매물이 있는 역이 없습니다' in note and "--station '테스트1호선 테스트역'" in note
        and '--max-minutes 를 늘리고' in note
        for note in result.notes
    )


# --- 단지 매물 목록 (complexByOriginalId.complex.articles) ------------------------


@pytest.mark.parametrize('limit', [1, 100])
def test_commute_limit_is_per_station_and_keeps_cross_station_matches(limit: int) -> None:
    requests: list[tuple[str, dict]] = []
    with commute_client(requests) as client:
        result = search_commute(client, 37.5, 127.03, limit=limit)
    station_requests = [variables for name, variables in requests if name == 'station']
    assert len(station_requests) == 2
    assert all(variables['first'] == limit for variables in station_requests)
    # 모든 검색 대상 역(30분 안 가까운역·먼역)을 조회하며 전체 결과 수로 조기 종료하지 않는다.
    assert len(result.stations) == 2
    assert all(group.returned <= limit for group in result.stations)
    assert result.returned == sum(group.returned for group in result.stations)
    assert result.unique_returned == len({listing.id for group in result.stations for listing in group.listings})


@pytest.mark.parametrize(('limit', 'total', 'expected_sizes'), [
    (120, 1201, [50, 50, 20]),
    (1200, 1201, [50] * 24),
    (1200, 1200, [50] * 24),
])
def test_region_complexes_paginates_and_notices_remaining(limit: int, total: int, expected_sizes: list[int]) -> None:
    import copy

    sizes: list[int] = []
    data = fixture('search_complexes_viewport')
    template = data['data']['searchComplexes']['edges'][0]

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_region_search(request):
            return httpx.Response(200, json=search_region())
        variables = json.loads(request.content)['variables']
        start = int(variables.get('after', '0'))
        size = variables['first']
        sizes.append(size)
        end = min(start + size, total)
        edges = []
        for index in range(start, end):
            edge = copy.deepcopy(template)
            edge['node']['originalId'] = str(9000000 + index)
            edges.append(edge)
        return httpx.Response(200, json={'data': {'complexByClusterId': {
            'edges': edges, 'pageInfo': {'endCursor': str(end), 'hasNextPage': end < total},
        }}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_region_complexes(client, '강남구 역삼동', limit=limit)
    assert sizes == expected_sizes
    assert result.returned == limit
    assert result.has_more is (total > limit)
    assert any('최대값은 1200' in note for note in result.notes) is (limit == 1200 and total > limit)


def test_region_complexes_notices_oversized_final_response() -> None:
    import copy

    template = fixture('search_complexes_viewport')['data']['searchComplexes']['edges'][0]
    edges = []
    for index in range(1201):
        edge = copy.deepcopy(template)
        edge['node']['originalId'] = str(9120000 + index)
        edges.append(edge)

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_region_search(request):
            return httpx.Response(200, json=search_region())
        return httpx.Response(200, json={'data': {'complexByClusterId': {
            'edges': edges, 'pageInfo': {'endCursor': None, 'hasNextPage': False},
        }}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_region_complexes(client, '강남구 역삼동', limit=1200)
    assert result.returned == 1200 and result.has_more
    assert any('최대값은 1200' in note for note in result.notes)
    assert not any('거래 불가' in note for note in result.notes)


@pytest.mark.parametrize('limit', [120, 1200])
def test_real_prices_large_limit_follows_cursor(limit: int) -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        variables = json.loads(request.content)['variables']
        requests.append(variables)
        offset = int(variables.get('buyAfter', '0'))
        size = variables['buyFirst']
        body = json.loads((FIXTURES / 'complex_by_original_id.json').read_text(encoding='utf-8'))
        connection = body['data']['complexByOriginalId']['complex']['buyTransactions']
        connection['edges'] = [connection['edges'][0]] * size
        connection['pageInfo'] = {'hasNextPage': True, 'endCursor': str(offset + size)}
        return httpx.Response(200, json=body)

    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        result = get_real_prices(client, 9000001, limit=limit)
    assert result.returned == limit
    assert sum(request['buyFirst'] for request in requests) == limit
    assert all(request['buyFirst'] <= 50 for request in requests)
    assert [request.get('buyAfter', '0') for request in requests] == [str(offset) for offset in range(0, limit, 50)]
    assert result.has_more
    # --limit 에서 멈추면 늘리라고, 24페이지(1200건)까지 받고도 남아야 당근 사이트로 안내한다
    assert any(result.url in note for note in result.notes) is (limit == 1200)
    assert any('--limit 을 늘리면' in note for note in result.notes) is (limit < 1200)


@pytest.mark.parametrize('limit', [120, 1200])
def test_complex_candidates_follow_cursor_and_notice_limit(limit: int) -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        variables = json.loads(request.content)['variables']
        requests.append(variables)
        offset = int(variables.get('after', '0'))
        body = json.loads((FIXTURES / 'search_complexes.json').read_text(encoding='utf-8'))
        connection = body['data']['searchComplexes']
        template = connection['edges'][0]
        connection['edges'] = []
        for index in range(offset, offset + variables['first']):
            edge = json.loads(json.dumps(template))
            edge['node']['originalId'] = str(9000000 + index)
            connection['edges'].append(edge)
        connection['pageInfo'] = {'hasNextPage': True, 'endCursor': str(offset + variables['first'])}
        return httpx.Response(200, json=body)

    notes: list[str] = []
    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        candidates = search_complexes(client, '테스트', limit=limit, notes=notes)
    assert len(candidates) == limit
    assert len({candidate.complex_id for candidate in candidates}) == limit
    assert [request.get('after', '0') for request in requests] == [str(offset) for offset in range(0, limit, 50)]
    assert all(request['first'] <= 50 for request in requests)
    assert notes and '1200' in notes[-1]


@pytest.mark.parametrize('empty', [False, True])
def test_complex_candidates_stalled_page_does_not_suggest_limit(empty: bool) -> None:
    # 커서가 되풀이되거나 다음 페이지가 있다면서 빈 페이지를 주어 멈춘 것은 --limit 에 닿은 것이 아니라,
    # --limit 을 늘리라는 안내를 붙이면 틀린 말이 된다. 응답이 바뀐 것일 수 있어 매일 API 감시가 고장으로 세도록
    # 업데이트 문구를 넣는다
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads((FIXTURES / 'search_complexes.json').read_text(encoding='utf-8'))
        connection = body['data']['searchComplexes']
        if empty:
            connection['edges'] = []
        connection['pageInfo'] = {'hasNextPage': True, 'endCursor': 'same'}
        return httpx.Response(200, json=body)

    notes: list[str] = []
    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        search_complexes(client, '테스트', limit=100, notes=notes)
    assert len(notes) == 1
    assert notes[0].startswith('[일부] 당근이 단지 후보 다음 페이지가 있다고 하면서 이어 받을 페이지를 주지 않아')
    assert UPDATE_MAYBE_NEEDED in notes[0]
    assert '--limit' not in notes[0]


def test_complex_listings_null_articles_after_next_page_stops_with_notice() -> None:
    # 다음이 있다던 단지 매물의 다음 응답에 articles 가 null 이면 목록 끝이 아니라 응답이 바뀐 것이다 (stalled_page.
    # 2026-11-11 실측: 헬리오시티 10667600 의 2쪽만 articles null 로 바꾸니 고치기 전에는 안내 없이 끝났다)
    cards = complex_article_cards()
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_region_search(request):
            # 카드에 시·도가 없는 동은 지역 검색으로 채운다
            return httpx.Response(200, json=search_region())
        body = json.loads(request.content)
        if body['extensions']['persistedQuery']['sha256Hash'] != DaangnClient.complex_articles_query_id:
            return httpx.Response(200, json=fixture('get_region_by_coordinate'))
        sent.append(body['variables'])
        articles = None if body['variables'].get('after') else {
            'edges': [{'node': card} for card in cards],
            'pageInfo': {'hasNextPage': True, 'endCursor': 'c1'},
        }
        return httpx.Response(200, json={'data': {'complexByOriginalId': {'complex': {'articles': articles}}}})

    with DaangnClient() as client:
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        result = list_complex_listings(client, 9000001, limit=40)
    assert [variables.get('after') for variables in sent] == [None, 'c1']
    assert result.has_more is True
    assert any(
        note.startswith(f'[일부] 당근이 단지 매물 다음 페이지가 있다고 하면서 이어 받을 페이지를 주지 않아 {len(cards)}건에서 멈췄습니다')
        and UPDATE_MAYBE_NEEDED in note
        for note in result.notes
    )


def test_search_station_counts_received_cards_and_keeps_walk_minutes() -> None:
    from jibsa.providers.daangn.service.region import DaangnStation
    from jibsa.providers.daangn.service.search import search_station

    page = fixture('subway_station_article_connection')
    sent: list[dict] = []

    def connection(variables: dict) -> dict:
        sent.append(variables)
        body = json.loads(json.dumps(page))
        connection = body['data']['subwayStationArticleConnection']
        connection['edges'] = connection['edges'][:variables['first']]
        connection['pageInfo']['hasNextPage'] = True
        return body

    client = make_graphql_client()
    handler = client._client._transport.handler

    def routed(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if body.get('extensions', {}).get('persistedQuery', {}).get('sha256Hash') == DaangnClient.subway_station_article_connection_query_id:
            return httpx.Response(200, json=connection(body['variables']))
        return handler(request)

    client._client._transport.handler = routed
    station = DaangnStation(name='테스트역', lines=['테스트1호선'], lat=37.497, lng=127.03, station_id='91')
    with client:
        result = search_station(client, station, conditions=DaangnListingConditions(trade_types=['월세']), limit=3)

    # 3건만 받고, 거래 완료(2000102)로 뺀 몫을 다음 페이지에서 채우지 않는다
    assert [(variables['first'], variables.get('after')) for variables in sent] == [(3, None)]
    assert sent[0]['subwayStationPoiId'] == '91' and sent[0]['propertyFilter']['tradeTypes'] == ['MONTH']
    assert [(listing.id, listing.walk_minutes) for listing in result.listings] == [('2000101', 3), ('2000103', 6)]
    assert result.has_more is True
    assert any('다시 채우지 않음' in note for note in result.notes)


def test_search_commute_pages_station_listings_up_to_limit() -> None:
    sent: list[tuple[str, dict]] = []
    client = commute_client(sent)
    handler = client._client._transport.handler
    pages = {None: (['2000101'], 'cursor-1', True), 'cursor-1': (['2000104'], None, False)}

    def routed(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        variables = body['variables']
        if body['extensions']['persistedQuery']['sha256Hash'] == DaangnClient.commute_station_article_connection_query_id \
                and variables['stationName'] == '가까운역':
            sent.append(('station', variables))
            ids, cursor, has_next = pages[variables.get('after')]
            return httpx.Response(200, json={'data': {'commuteStationArticleConnection': {
                'edges': [{'node': {'article': {'originalId': article_id}}} for article_id in ids],
                'pageInfo': {'endCursor': cursor, 'hasNextPage': has_next},
            }}})
        return handler(request)

    client._client._transport.handler = routed
    with client:
        result = search_commute(client, 37.5, 127.03, limit=2)

    # 받은 수(1건)로 예산을 세고 남은 1건만 다음 페이지에서 받는다
    station_pages = [(variables['first'], variables.get('after')) for name, variables in sent
                     if name == 'station' and variables['stationName'] == '가까운역']
    assert station_pages == [(2, None), (1, 'cursor-1')]
    assert result.stations[0].inspected == 2


# --- 출퇴근 경로·주소·지도 범위 단지·실거래 필드 (#215) ----------------------------

def test_commute_station_groups_carry_route() -> None:
    from jibsa.providers.daangn.service.commute import DaangnCommuteLeg

    stations = fixture('commute_stations')
    # 서버 경로가 회사 역(테스트역)에서 시작하지 않으면 방향을 짐작하지 않는다
    stations['data']['commuteStations'][0]['routeWaypoints'].reverse()
    with commute_client(stations_body=stations) as client:
        result = search_commute(client, 37.5, 127.03)
    routes = {group.station_name: group.route for group in result.stations}
    # 서버 경로(회사 역 → 타는 역, 역마다 다음 구간 노선)를 타는 역에서 회사 역으로 가는 구간으로 뒤집는다
    assert routes['먼역'] == [
        DaangnCommuteLeg(from_station='먼역', to_station='환승역', line='테스트2호선'),
        DaangnCommuteLeg(from_station='환승역', to_station='테스트역', line='테스트1호선'),
    ]
    assert routes['가까운역'] is None


def test_real_prices_month_is_sent_as_trade_year_month_and_splits_contract_fields() -> None:
    requests: list[dict] = []
    with real_price_client(requests) as client:
        result = get_real_prices(client, 9000001, trade_type='월세', limit=3, month='2026-08')
        without_month = get_real_prices(client, 9000001, trade_type='월세', limit=3).model_dump()
    assert requests[0]['tradeYearMonth'] == '202608' and result.month == '2026-08'
    assert 'tradeYearMonth' not in requests[-1] and 'month' not in without_month
    first = result.transactions[0].model_dump()
    # 예전 renewal 은 계약 종류와 갱신요구권을 합쳤다. 웹 배지처럼 둘로 나눈다 (NEW → 신규, useRenewalOfContractRight → renewal_right)
    assert (first['contract_type'], first['renewal_right']) == ('신규', False) and 'renewal' not in first


def _realsale_feed_client(requests: list[httpx.Request], *, summary_rejected: bool = False) -> DaangnClient:
    """역삼동 매매 피드 3건(신고가·내림·해제)과 요약을 준다."""
    def sale(price: int, previous: int | None, new_high: bool, cancel: bool = False) -> dict:
        return {'node': {
            'realsale': {'id': str(price), 'tradeType': 'SALE', 'tradePrice': price, 'deposit': 0, 'monthRentFee': 0,
                         'exclusiveArea': 84.9, 'floor': 10, 'contactDate': '20261103', 'cancel': cancel, 'transactionType': 'BROKERED'},
            'dataDate': '20261112', 'danji': {'danjiAreaNm': '테스트아파트', 'totalTotHsehCnt': 100, 'buildDate': '2008-12-02'},
            'complex': None, 'regionName': '서울 강남구 역삼동',
            'priceInsight': None if previous is None else {'previousMaxPrice': previous, 'previousMaxContactDate': '20250509', 'isNewHigh': new_high},
        }}

    feed = {'data': {'realsaleFeed': {
        'edges': [sale(360000, 295000, True), sale(150000, 180000, False), sale(300000, 295000, True, cancel=True), sale(100000, None, False)],
        'pageInfo': {'endCursor': 'c1', 'hasNextPage': False},
    }}}
    summary = {'data': {'realsaleFeedSummary': {'dataDate': '20261112', 'saleCount': 4}, 'realsaleNewHighFeedSummary': {'newHighCount': 1}}}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if _is_region_search(request):
            return httpx.Response(200, json=search_region())
        query_id = json.loads(request.content)['extensions']['persistedQuery']['sha256Hash']
        if query_id == DaangnClient.realsale_feed_summary_query_id:
            return httpx.Response(200, json=REJECTED if summary_rejected else summary)
        return httpx.Response(200, json=feed)

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_region_real_prices_mark_new_high_like_web_card_and_add_summary() -> None:
    from jibsa.providers.daangn.service.real_price import get_region_real_prices

    requests: list[httpx.Request] = []
    with _realsale_feed_client(requests) as client:
        result = get_region_real_prices(client, '강남구 역삼동', limit=10)
    rows = [row.model_dump() for row in result.transactions]
    # 웹 카드(MapShell `yc`): 신고가 배지는 isNewHigh 이고 해제되지 않은 거래, '직전 최고가 대비' 는 웹과 같은 비율의 소수 둘째 자리
    assert [(row['is_new_high'], row.get('previous_high_change_percent')) for row in rows] == [(True, 22.03), (False, -16.67), (False, None), (False, None)]
    assert rows[0]['previous_high_manwon'] == 295000 and rows[0]['previous_high_date'] == '2025-05-09'
    assert 'renewal' not in rows[0] and 'contract_type' not in rows[0]
    assert result.summary is not None and result.summary.model_dump() == {'data_date': '2026-11-12', 'sale_count': 4, 'new_high_count': 1}
    # 요약은 본 조회 뒤의 덤 조회다
    hashes = [json.loads(request.content)['extensions']['persistedQuery']['sha256Hash'] for request in requests]
    assert hashes.index(DaangnClient.realsale_feed_summary_query_id) > hashes.index(DaangnClient.realsale_feed_query_id)


def test_region_real_prices_summary_failure_keeps_transactions() -> None:
    from jibsa.providers.daangn.service.real_price import get_region_real_prices

    with _realsale_feed_client([], summary_rejected=True) as client:
        result = get_region_real_prices(client, '강남구 역삼동', limit=10)
    assert result.returned == 4 and result.summary is None
    assert any(note.startswith('[실패]') and '실거래 요약' in note for note in result.notes)


# 소수 셋째 자리에서 .5 를 올린다 (0.25% 는 Python round 로 0.2 가 됐다). 바뀌었는데 0.00 이면 ±0.01
@pytest.mark.parametrize(
    'price,previous,expected',
    [(295000, 295000, 0.0), (80200, 80000, 0.25), (100125, 100000, 0.13), (250001, 250000, 0.01), (294999, 295000, -0.01), (1000, 0, None)],
)
def test_previous_high_change_percent_rounds_to_two_decimals(price: int, previous: int, expected: float | None) -> None:
    from jibsa.providers.daangn.service.real_price import previous_high_change_percent

    assert previous_high_change_percent(price, previous) == expected


def test_kb_sale_is_converted_from_won() -> None:
    from jibsa.providers.daangn.api.response.real_price import DaangnPriceChartModel
    from jibsa.providers.daangn.service.real_price import kb_sale_of

    chart = DaangnPriceChartModel.model_validate({'averagePoints': [], 'latestKbSale': {'surveyBaseDate': '20261102', 'lower': 2700000000, 'upper': 2910000000}})
    kb_sale = kb_sale_of(chart)
    assert kb_sale is not None and kb_sale.model_dump() == {'low_manwon': 270000, 'high_manwon': 291000, 'survey_date': '2026-11-02'}
    assert kb_sale_of(DaangnPriceChartModel.model_validate({'averagePoints': []})) is None


def test_preschool_survey_responses_default_to_zero_like_web() -> None:
    from jibsa.providers.daangn.service.school import get_preschool

    bodies = iter([{'surveyResult': {'responseCount': 3}}, {'surveyResult': None}])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'data': {'preschoolByNo': {'schoolNm': '테스트어린이집', 'type': 'DAYCARE', **next(bodies)}}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        assert get_preschool(client, 1).survey_responses == 3
        # 웹 상세(`Mu`)는 surveyResult?.responseCount ?? 0 이라 설문이 없으면 0 이다
        assert get_preschool(client, 2).survey_responses == 0


def test_bounds_complexes_send_map_view_bounds_instead_of_cluster() -> None:
    from jibsa.providers.daangn.service.common import map_view_bounds
    from jibsa.providers.daangn.service.complex import list_bounds_complexes

    requests: list[httpx.Request] = []
    with make_graphql_client({DaangnClient.search_complexes_viewport_query_id: fixture('search_complexes_viewport')}, requests) as client:
        result = list_bounds_complexes(client, 37.5006, 127.0366, limit=5)
    payload = _graphql_payloads(requests, DaangnClient.search_complexes_viewport_query_id)[0]['variables']
    bounds, width_km, height_km = map_view_bounds(37.5006, 127.0366, 15)
    assert payload['input']['locationFilter'] == bounds.model_dump(by_alias=True) and 'clusterId' not in payload['input']
    assert (payload['input']['sort'], payload['tradeType'], payload['first']) == ('HOUSEHOLD_COUNT_DESC', 'BUY', 5)
    assert (result.zoom, result.width_km, result.height_km) == (15, width_km, height_km)
    assert [complex_.complex_id for complex_ in result.complexes] == ['10000001', '10000002'] and result.region is not None


def _address_client(candidates: list[dict], unit: dict | None) -> DaangnClient:
    def handler(request: httpx.Request) -> httpx.Response:
        query_id = json.loads(request.content)['extensions']['persistedQuery']['sha256Hash']
        if query_id == DaangnClient.search_address_query_id:
            edges = [{'cursor': str(index), 'node': node} for index, node in enumerate(candidates)]
            return httpx.Response(200, json={'data': {'searchAddress': {'edges': edges, 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}})
        return httpx.Response(200, json={'data': {'unitByAddress': {'unit': unit}}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_find_address_resolves_one_candidate_and_refuses_many() -> None:
    from jibsa.core.errors import (
        RegionAmbiguousError,
        RegionNotFoundError,
    )
    from jibsa.providers.daangn.service.region import find_address

    def candidate(number: int) -> dict:
        return {'regionAddress': f'서울특별시 강남구 역삼동 {number} 테스트빌딩', 'roadAddress': f'서울특별시 강남구 테스트로 {number} (역삼동)',
                'originalRoadAddress': f'서울특별시 강남구 테스트로 {number} (역삼동)', 'bdMgtSn': f'11680101001{number:05d}'}

    unit = {'location': {'lat': '37.5000', 'lon': '127.0365'}, 'complex': None,
            'building': {'id': 'b', 'originalId': '10486373', 'buildingName': '테스트빌딩', 'coordinate': {'lat': '37.5', 'lon': '127.03'}}}
    with _address_client([candidate(152)], unit) as client:
        found = find_address(client, '테스트로 152')
    # 좌표는 웹처럼 주소 좌표(location)이고, 단지가 아니라 complex_id 키가 없다
    assert (found.lat, found.lng, found.place) == (37.5, 127.0365, '테스트빌딩') and 'complex_id' not in found.model_dump()
    with _address_client([candidate(101), candidate(103)], unit) as client:
        with pytest.raises(RegionAmbiguousError) as ambiguous:
            find_address(client, '테스트로')
        assert ambiguous.value.details['candidates'] == ['서울특별시 강남구 테스트로 101 (역삼동)', '서울특별시 강남구 테스트로 103 (역삼동)']
        # 후보가 여럿이어도 도로명 주소가 정확히 같은 하나는 고른다 (REGION_AMBIGUOUS 가 알린 이름 그대로 다시 준 경우)
        assert find_address(client, '서울특별시 강남구 테스트로 103 (역삼동)').road_address.endswith('103 (역삼동)')
    with _address_client([candidate(152)], None) as client:
        with pytest.raises(RegionNotFoundError):
            find_address(client, '테스트로 152')
