import base64
import gzip
import json
from pathlib import Path

import httpx
import pytest

from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.parser import (
    parse_articles_html,
    parse_complexes_html,
    parse_map_html,
)
from jibsa.providers.daangn.api.relay import resolve
from jibsa.providers.daangn.service.common import (
    DaangnListingConditions,
    article_to_listing,
)
from jibsa.providers.daangn.service.commute import search_commute
from jibsa.providers.daangn.service.complex import (
    list_region_complexes,
    search_complexes,
)
from jibsa.providers.daangn.service.listing import (
    detail_to_listing,
    get_listing,
)
from jibsa.providers.daangn.service.real_price import get_real_prices
from jibsa.providers.daangn.service.region import resolve_regions
from jibsa.providers.daangn.service.search import search_listings


FIXTURES = Path(__file__).parent / 'fixtures' / 'daangn'


def html(name: str) -> str:
    return gzip.open(FIXTURES / f'{name}.html.gz', 'rt', encoding='utf-8').read()


def regions() -> dict:
    return json.loads((FIXTURES / 'regions_keyword_v1.json').read_text(encoding='utf-8'))


def article_feed() -> dict:
    return json.loads((FIXTURES / 'article_feed.json').read_text(encoding='utf-8'))


def articles_count() -> dict:
    return json.loads((FIXTURES / 'articles_count.json').read_text(encoding='utf-8'))


def make_client(requests: list[httpx.Request] | None = None) -> DaangnClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.host == 'www.daangn.com':
            return httpx.Response(200, json=regions())
        if request.url.host == 'realty.kr.karrotmarket.com':
            query_id = json.loads(request.content)['extensions']['persistedQuery']['sha256Hash']
            return httpx.Response(200, json=articles_count() if query_id == DaangnClient.articles_count_query_id else article_feed())
        if request.url.path.startswith('/map/'):
            # 픽스처 지역 검색의 용인시 처인구 역삼동은 행정동이라 실제 당근도 지도가 404 다
            return httpx.Response(404 if '처인구' in request.url.path else 200, text=html('map'))
        return httpx.Response(200, text=html('articles'))

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return client


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


def test_search_listings_filters_on_server() -> None:
    # 조건이 있으면 지도 페이지의 첫 20건(조건 없음)은 쓰지 않고 서버가 거른 피드를 받는다
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = search_listings(
            client,
            resolve_regions(client, '역삼동'),
            conditions=DaangnListingConditions(trade_types=['월세'], rent_max=100),
            limit=3,
        )
    payload = _feed_payloads(requests)[0]
    assert payload['extensions']['persistedQuery']['sha256Hash'] == DaangnClient.article_feed_query_id
    assert payload['variables'] == {
        'first': 3,
        'input': {
            'locationFilter': {'originalRegionId': 6035},
            'propertyFilter': {'salesTypes': [], 'tradeTypes': ['MONTH'], 'monthlyPay': {'maxAmount': 100}},
            'surface': 'MAP',
        },
    }
    # 조건에 맞는 매물 수는 피드와 같은 조건으로 따로 센다 (surface 없음)
    assert _graphql_payloads(requests, DaangnClient.articles_count_query_id)[0]['variables'] == {
        'input': {
            'locationFilter': {'originalRegionId': 6035},
            'propertyFilter': {'salesTypes': [], 'tradeTypes': ['MONTH'], 'monthlyPay': {'maxAmount': 100}},
        },
    }
    # 조건에 맞는 매물(150건)이 많아, limit 이 찰 때까지 다음 페이지를 커서로 이어 받는다 (동마다 최대 3페이지)
    assert [body['variables'].get('after') for body in _feed_payloads(requests)] == [None]
    # 픽스처 피드는 요청한 수와 상관없이 6건을 주지만 쓰는 건 limit 건까지다. 남은 매물은 다음 페이지에서 다시 받는다
    assert result.fetched == 3
    assert result.total == 150
    assert {listing.id for listing in result.listings} == {'1000101'}
    assert result.listings[0].trade_type == '월세'
    assert result.notes[0] == (
        'total 150건은 조건에 맞는 매물을 주변 동 매물까지 센 당근 집계입니다 (동마다 1000에서 잘림). '
        '그중 최근 3건을 받았습니다 (동마다 최대 120건)'
    )


def _paged_stub_client(count: int | None, payloads: list):
    """피드는 늘 다음 페이지가 있는 픽스처(6건씩)를, 조건에 맞는 매물 수는 `count` 를 주는 가짜 client."""
    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleFeedResponseModel,
    )

    client = _stub_client(parse_map_html(html('map'), '역삼동'), [], count=count)

    def feed(payload):
        payloads.append(payload)
        return DaangnArticleFeedResponseModel.model_validate(article_feed())

    client.run_request_article_feed = feed
    return client


def test_search_listings_does_not_refill_when_few_match() -> None:
    # 조건에 맞는 매물이 100건 이하면 limit 와 상관없이 끝까지 받는다 (30건 → 20건씩 2페이지)
    payloads: list = []
    result = search_listings(_paged_stub_client(30, payloads), [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']), limit=1)
    assert [payload.after for payload in payloads] == [None]
    assert result.total == 30
    assert payloads[0].first == 1
    assert '조건 불일치를 빼고' not in ' '.join(result.notes)  # 반환 제한으로 잘린 정상 매물이다.

    # 100건이 넘으면 지금처럼 limit 이 차면 멈춘다
    payloads = []
    result = search_listings(_paged_stub_client(101, payloads), [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']), limit=1)
    assert len(payloads) == 1
    assert result.notes[0].endswith('그중 최근 1건을 받았습니다 (동마다 최대 120건)')


def test_search_listings_continues_when_count_fails() -> None:
    # 수 조회가 실패해도 검색은 하고, 모르는 수는 내지 않는다
    payloads: list = []
    result = search_listings(_paged_stub_client(None, payloads), [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']), limit=1)
    assert len(payloads) == 1
    assert result.listings
    assert result.total is None


def test_count_does_not_swallow_rate_limit() -> None:
    from jibsa.core.ratelimit import RateLimitedError

    client = _paged_stub_client(30, [])
    client.run_request_articles_count = _rate_limited
    with pytest.raises(RateLimitedError):
        search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']))


def _regions_client(locations: list[dict]) -> DaangnClient:
    def handler(request: httpx.Request) -> httpx.Response:
        # 같은 이름 동이 여럿이면 지도가 있는지(법정동인지) 본다. 여기 후보는 모두 지도가 있다
        if request.url.path.startswith('/map/'):
            return httpx.Response(200, text=html('map'))
        return httpx.Response(200, json={'locations': locations})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


# --city 를 글자가 들어 있는지로만 보면 '동구' 가 성동구에, '남구' 가 강남구에 맞아 엉뚱한 동을 고른다.
# '서울시' 는 서울의 송정동 두 곳에 맞아 첫 곳을 고르지 않고 멈춘다
@pytest.mark.parametrize(
    ('city', 'expected'),
    [('동구', '대구광역시'), ('성동', '서울특별시'), ('서울시', 'REGION_AMBIGUOUS'), ('남구', None)],
)
def test_city_matches_start_of_district_name(city: str, expected: str | None) -> None:
    from jibsa.core.errors import (
        RegionAmbiguousError,
        RegionNotFoundError,
    )

    locations = [
        {'id': 1, 'name1': '서울특별시', 'name2': '성동구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
        {'id': 2, 'name1': '대구광역시', 'name2': '동구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
        {'id': 3, 'name1': '서울특별시', 'name2': '강남구', 'name3': '송정동', 'name': '송정동', 'depth': 3},
    ]
    with _regions_client(locations) as client:
        if expected is None:
            with pytest.raises(RegionNotFoundError):
                resolve_regions(client, '송정동', city=city)
            return
        if expected == 'REGION_AMBIGUOUS':
            with pytest.raises(RegionAmbiguousError) as error:
                resolve_regions(client, '송정동', city=city)
            assert error.value.details['candidates'] == ['서울특별시 성동구 송정동', '서울특별시 강남구 송정동']
            return
        [region] = resolve_regions(client, '송정동', city=city)
    assert region.name1 == expected


def test_unavailable_articles_are_excluded() -> None:
    from jibsa.core.errors import ListingUnavailableError

    page = parse_map_html(html('map'), '역삼동')
    traded = page.articles[0].model_copy(update={'status': 'TRADED'})
    denied = page.articles[1].model_copy(update={'invisible_reason': 'CHECK_DENY'})
    hidden = page.articles[2].model_copy(update={'is_hide': True})
    from jibsa.providers.daangn.service.common import is_available
    assert is_available(page.articles[3])
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


def test_missing_article_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='<html></html>')

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client, pytest.raises(ListingUnavailableError):
        get_listing(client, 2000000)


def test_search_listings_matches_non_preferred_trade() -> None:
    # 대표 조건이 매매여도 함께 올린 월세 조건이 필터에 맞으면 월세로 내보낸다.
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel
    from jibsa.providers.daangn.service.common import DaangnRegion

    page = parse_map_html(html('map'), '역삼동')
    article = page.articles[3].model_copy(update={
        'trades': [
            DaangnTradeModel.model_validate({'type': 'BUY', 'preferred': True, 'price': 39500}),
            DaangnTradeModel.model_validate({'type': 'MONTH', 'preferred': False, 'deposit': 1200, 'monthlyPay': 120}),
        ],
    })
    client = _stub_client(page.model_copy(update={'articles': [article]}), [article])
    region = DaangnRegion(name1='서울특별시', name2='강남구', name3='역삼동', region_id=6035)

    monthly = search_listings(client, [region], conditions=DaangnListingConditions(trade_types=['월세'])).listings
    assert [(listing.trade_type, listing.deposit_manwon, listing.rent_manwon) for listing in monthly] == [('월세', 1200, 120)]
    sale = search_listings(client, [region]).listings
    assert [(listing.trade_type, listing.price_manwon) for listing in sale] == [('매매', 39500)]


def _yeoksam():
    from jibsa.providers.daangn.service.common import DaangnRegion
    return DaangnRegion(name1='서울특별시', name2='강남구', name3='역삼동', region_id=6035)


def _feed_response(articles: list, *, errors: list | None = None):
    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleFeedResponseModel,
    )

    edges = [{'node': {'type': 'ARTICLE', 'article': article.model_dump(by_alias=True)}} for article in articles]
    data = {'articleFeed': {'edges': edges, 'pageInfo': {'endCursor': None, 'hasNextPage': False}}}
    return DaangnArticleFeedResponseModel.model_validate({'data': None if errors else data, 'errors': errors or []})


def _stub_client(
    page,
    feed_articles: list,
    payloads: list | None = None,
    errors: list | None = None,
    count: int | None = None,
):
    """지도 페이지는 `page`, 피드는 `feed_articles` (또는 GraphQL `errors`) 를 주는 가짜 client.

    조건에 맞는 매물 수는 `count` 다. None 이면 수 조회가 실패한다 (수를 모를 때의 동작).
    """
    from types import SimpleNamespace

    from jibsa.providers.daangn.api.response.search import (
        DaangnArticlesCountResponseModel,
    )

    def feed(payload):
        if payloads is not None:
            payloads.append(payload)
        return _feed_response(feed_articles, errors=errors)

    def articles_count(_):
        if count is None:
            return DaangnArticlesCountResponseModel.model_validate({'errors': [{'message': '알 수 없는 오류가 발생했어요'}]})
        return DaangnArticlesCountResponseModel.model_validate({'data': {'count': count}})

    return SimpleNamespace(run_request_map=lambda _: page, run_request_article_feed=feed, run_request_articles_count=articles_count)


def _region(name3: str):
    from jibsa.providers.daangn.service.common import DaangnRegion
    return DaangnRegion(name1='제주특별자치도', name2='제주시', name3=name3, region_id=1)


def _not_found(_) -> None:
    request = httpx.Request('GET', 'https://realty.daangn.com/map/x')
    raise httpx.HTTPStatusError('404', request=request, response=httpx.Response(404, request=request))


@pytest.mark.parametrize('timed', [True, False])
def test_dong_feeds_are_merged_by_time_across_pages(timed: bool) -> None:
    # 당근은 동마다 주변 동 매물을 섞어 줘 같은 매물이 두 동 피드에 같은 시각으로 온다. 동 피드를 시각 순으로 합쳐야 다음
    # 페이지에 앞 매물이 다시 나오지 않는다. 커서의 시각을 못 읽으면(형식 변경) 동 순서로 주고 next 를 주지 않는다
    from types import SimpleNamespace

    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleFeedResponseModel,
    )
    from jibsa.providers.daangn.service.common import DaangnRegion

    base = parse_map_html(html('map'), '역삼동')
    x1, x2, y1, y2, shared = base.articles[:5]
    feeds = {1: [(x1, '12'), (shared, '10'), (x2, '08')], 2: [(y1, '11'), (shared, '10'), (y2, '09')]}
    cursors = {
        region_id: [
            base64.b64encode(f'2026-10-21T{at}:00:00.000Z|{position}|0'.encode()).decode() if timed else f'cursor-{at}'
            for position, (_, at) in enumerate(rows)
        ]
        for region_id, rows in feeds.items()
    }
    region_ids = {'역삼동': 1, '논현동': 2}

    def map_page(parameter):
        # 지도 페이지는 피드 첫 2건이다 (실제는 20건)
        region_id = region_ids[parameter.name3]
        return base.model_copy(update={
            'articles': [article for article, _ in feeds[region_id][:2]], 'cursors': cursors[region_id][:2],
            'end_cursor': cursors[region_id][1], 'has_next_page': True,
        })

    def feed(payload):
        region_id = payload.input.location_filter.original_region_id
        start = cursors[region_id].index(payload.after) + 1
        rows = list(zip(feeds[region_id], cursors[region_id], strict=True))[start:start + payload.first]
        edges = [{'node': {'type': 'ARTICLE', 'article': article.model_dump(by_alias=True)}, 'cursor': cursor} for (article, _), cursor in rows]
        page_info = {'endCursor': rows[-1][1] if rows else None, 'hasNextPage': start + len(rows) < len(feeds[region_id])}
        return DaangnArticleFeedResponseModel.model_validate({'data': {'articleFeed': {'edges': edges, 'pageInfo': page_info}}})

    client = SimpleNamespace(run_request_map=map_page, run_request_article_feed=feed)
    regions = [DaangnRegion(name1='서울특별시', name2='강남구', name3=name, region_id=region_id) for name, region_id in region_ids.items()]
    first = search_listings(client, regions, limit=3)
    if not timed:
        assert first.next_position is None
        assert first.notes[0].startswith('[실패] 당근 피드의 시각을 읽지 못해')
        return
    assert [listing.id for listing in first.listings] == [x1.original_id, y1.original_id, shared.original_id]
    # 논현동 피드의 같은 매물(같은 시각)은 다시 내지 않고, 두 동의 남은 매물을 시각 순으로 잇는다
    second = search_listings(client, regions, limit=3, resume=first.next_position)
    assert [listing.id for listing in second.listings] == [y2.original_id, x2.original_id]
    assert not second.has_more


def test_missing_map_page_among_expanded_dongs_is_skipped() -> None:
    from types import SimpleNamespace

    page = parse_map_html(html('map'), '역삼동')
    client = SimpleNamespace(
        run_request_map=lambda parameter: _not_found(parameter) if parameter.name3 == '이도이동' else page
    )
    result = search_listings(client, [_region('이도이동'), _region('노형동')])
    assert result.fetched == 20


def test_search_listings_notes_neighbor_dongs() -> None:
    # 픽스처의 역삼동 피드에는 논현동·도곡동 매물이 섞여 있다. 빼지 않고 in_regions 로 표시하고 알린다.
    with make_client() as client:
        result = search_listings(client, resolve_regions(client, '역삼동'))
    assert {listing.address for listing in result.listings} >= {'서울특별시 강남구 논현동', '서울특별시 강남구 역삼동'}
    assert all(listing.in_regions == listing.address.endswith('역삼동') for listing in result.listings)
    assert result.notes[-1] == '[범위] 20건 중 10건은 당근이 섞어 준 주변 동(논현동, 도곡동) 매물입니다 (in_regions: false)'


def _rate_limited(_) -> None:
    from jibsa.core.ratelimit import RateLimitedError

    raise RateLimitedError('daangn', 300.0, 'cooldown')


# 시·도 채우기는 주소를 다듬는 보조 조회라, 요청 제한에 걸려도 받아 둔 매물을 버리지 않는다
@pytest.mark.parametrize('lookup', [_not_found, _rate_limited])
def test_missing_sido_stays_when_lookup_fails(lookup) -> None:
    from types import SimpleNamespace

    page = parse_map_html(html('map'), '역삼동')
    neighbor = page.articles[0].region.model_copy(update={'name1': None, 'name2': '고양시 덕양구', 'name3': '향동동'})
    article = page.articles[0].model_copy(update={'region': neighbor})
    client = SimpleNamespace(
        run_request_map=lambda _: page.model_copy(update={'articles': [article]}),
        run_request_regions_keyword_v1=lookup,
    )
    assert search_listings(client, [_region('신사동')]).listings[0].address == '고양시 덕양구 향동동'


def test_short_trade_is_short_term_rent() -> None:
    # 당근 단기임대(ShortTrade)는 보증금·월세가 있다. 모르는 조건으로 버리지 않고 단기임대로 내보낸다.
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel
    from jibsa.providers.daangn.service.common import DaangnRegion

    page = parse_map_html(html('map'), '역삼동')
    short = DaangnTradeModel.model_validate(
        {'__typename': 'ShortTrade', 'type': 'SHORT', 'preferred': True, 'deposit': 200, 'monthlyPay': 130}
    )
    article = page.articles[3].model_copy(update={'trades': [short]})
    listing = article_to_listing(article)
    assert (listing.trade_type, listing.deposit_manwon, listing.rent_manwon) == ('단기임대', 200, 130)

    client = _stub_client(page.model_copy(update={'articles': [article]}), [article])
    region = DaangnRegion(name1='서울특별시', name2='강남구', name3='역삼동', region_id=6035)
    assert [item.trade_type for item in search_listings(client, [region], conditions=DaangnListingConditions(trade_types=['단기임대'])).listings] == ['단기임대']
    assert search_listings(client, [region], conditions=DaangnListingConditions(trade_types=['월세'])).listings == []


def _multi_trade_detail():
    from jibsa.providers.daangn.api.response.common import DaangnTradeModel

    response = parse_articles_html(html('articles'), 1000001)
    trades = [
        DaangnTradeModel.model_validate({'type': 'BUY', 'preferred': True, 'price': 17500}),
        DaangnTradeModel.model_validate({'type': 'BORROW', 'preferred': False, 'deposit': 16000}),
        DaangnTradeModel.model_validate({'type': 'MONTH', 'preferred': False, 'deposit': 12500, 'monthlyPay': 30}),
    ]
    return response.model_copy(update={'article': response.article.model_copy(update={'trades': trades})})


def test_detail_with_trade_not_offered_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError

    with pytest.raises(ListingUnavailableError) as exc:
        detail_to_listing(_multi_trade_detail(), '단기임대')
    assert exc.value.details['reason'] == 'TRADE_NOT_OFFERED'
    assert exc.value.details['offered_trades'] == ['매매 17500', '전세 16000', '월세 12500/30']


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


def test_server_filtered_feed_rechecks_only_what_the_list_shows() -> None:
    # 서버가 거른 매물도 거래 조건은 다시 고른다. 면적과 관리비 포함 월세는 서버에 맡긴다.
    page = parse_map_html(html('map'), '역삼동')
    article = page.articles[0].model_copy(update={'area': 99.0})
    client = _stub_client(page, [article])
    rent = article_to_listing(article).rent_manwon
    assert search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(area_max=30)).listings
    assert search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(rent_min=rent + 1, rent_includes_manage_cost=True)).listings
    assert not search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(rent_min=rent + 1)).listings
    # 관리비를 몰라도 총액 상한보다 비싼 월세를 대표 조건으로 선택하면 안 된다.
    preferred = article.trades[0].model_copy(update={'monthly_pay': int(rent) + 100, 'preferred': True})
    affordable = article.trades[0].model_copy(update={'preferred': False})
    article = article.model_copy(update={'trades': [preferred, affordable]})
    client = _stub_client(page, [article])
    result = search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(rent_max=rent + 10, rent_includes_manage_cost=True))
    assert result.listings[0].rent_manwon == rent


@pytest.mark.parametrize('field,condition', [
    ('monthly_pay', {'rent_max': 80}),
    ('deposit', {'deposit_max': 1000}),
])
def test_unknown_amount_does_not_pass_budget(field: str, condition: dict) -> None:
    page = parse_map_html(html('map'), '역삼동')
    article = page.articles[0]
    trade = article.trades[0].model_copy(update={field: None})
    article = article.model_copy(update={'trades': [trade]})
    client = _stub_client(page, [article])
    assert search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세'])).listings
    assert not search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세'], **condition)).listings


def test_server_filtered_feed_keeps_category_and_notes_unselected_trade() -> None:
    # 서버가 원룸 조건으로 준 매물은 카테고리가 달라도 다시 거르지 않고, 거래 조건을 못 고른 매물은 사유를 알린다
    page = parse_map_html(html('map'), '역삼동')
    article = page.articles[0]
    officetel = article.model_copy(update={'sales_type': article.sales_type.model_copy(update={'type': 'OFFICETEL'})})
    unknown = page.articles[3].model_copy(update={
        'original_id': 'unknown-rent',
        'trades': [page.articles[3].trades[0].model_copy(update={'monthly_pay': None})],
    })
    result = search_listings(_stub_client(page, [officetel, unknown]), [_yeoksam()], conditions=DaangnListingConditions(property_types=['원룸'], rent_max=1000))
    assert [(listing.id, listing.property_type) for listing in result.listings] == [(officetel.original_id, '오피스텔')]
    assert any(note.startswith('[제외] 서버 필터를 통과한 매물 1건은') for note in result.notes)

    # 필터 API 를 못 써 조건 없는 지도 페이지로 대체 조회하면 유형을 직접 확인해 뺀다
    rejected = [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]
    fallback = page.model_copy(update={'articles': [officetel]})
    result = search_listings(_stub_client(fallback, [], errors=rejected), [_yeoksam()], conditions=DaangnListingConditions(property_types=['원룸']))
    assert result.listings == []
    assert not any(note.startswith('[제외] 서버 필터를 통과한') for note in result.notes)


@pytest.mark.parametrize('sales_type,room_count,room_type', [
    # 분리형원룸으로 올렸어도 방이 2개면 투룸이다 (실측). 방 수를 모르는 목록은 원룸 구조를 쓴다
    ('SPLIT_ONE_ROOM', 2, '투룸'),
    ('SPLIT_ONE_ROOM', None, '분리형원룸'),
    ('OFFICETEL', 4, '포룸이상'),
    ('OFFICETEL', 1, None),
])
def test_room_type_prefers_room_count(sales_type: str, room_count: int | None, room_type: str | None) -> None:
    article = parse_map_html(html('map'), '역삼동').articles[0]
    article = article.model_copy(update={
        'sales_type': article.sales_type.model_copy(update={'type': sales_type}),
        'room_count': room_count,
    })
    assert article_to_listing(article).room_type == room_type


def test_feed_excludes_invisible_articles() -> None:
    page = parse_map_html(html('map'), '역삼동')
    blocked = page.articles[0].model_copy(update={'invisible_infos': [{'__typename': 'CheckDenyInvisibleInfo'}]})
    client = _stub_client(page, [blocked, page.articles[3]])
    result = search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세', '매매', '전세', '단기임대']))
    assert [listing.id for listing in result.listings] == [page.articles[3].original_id]


def test_rejected_feed_query_falls_back_to_map_page() -> None:
    # 웹이 쿼리를 바꿔 해시가 거절되면 예전처럼 지도 페이지 20건에 직접 조건을 건다
    page = parse_map_html(html('map'), '역삼동')
    rejected = [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]
    payloads: list = []
    client = _stub_client(page, [], payloads, errors=rejected, count=50)
    result = search_listings(client, [_yeoksam(), _yeoksam()], conditions=DaangnListingConditions(trade_types=['월세'], rent_max=100, area_min=10))
    assert len(payloads) == 1
    assert result.fetched == 20
    assert result.listings
    assert all(listing.trade_type == '월세' and listing.rent_manwon <= 100 for listing in result.listings)
    assert result.notes[0].startswith('[실패] 당근 필터 API 를 쓸 수 없어')
    assert '조건은 받아 온 최근 20건(동마다 최대 20건)에만 걸었으니' in result.notes[1]


def test_rejected_feed_query_without_conditions_notes() -> None:
    # 조건 없이 찾다가 다음 페이지 해시가 거절되면 지도 페이지 20건뿐이다. 실제 서버는 해시를 받아 주어 재현할 수 없다
    page = parse_map_html(html('map'), '역삼동').model_copy(update={'end_cursor': 'next'})
    rejected = [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]
    client = _stub_client(page, [], errors=rejected)
    result = search_listings(client, [_yeoksam()], limit=120)
    assert result.fetched == 20
    assert result.notes[0].startswith('[실패] 당근 매물 피드 API 를 쓸 수 없어') and '조건을 적용' not in result.notes[0]
    assert result.notes[1].endswith('그중 최근 20건을 받았습니다 (동마다 최대 20건)')
    assert not any('전부입니다' in note or '--limit' in note for note in result.notes)


def test_rejected_feed_query_with_server_only_condition_is_an_error() -> None:
    from jibsa.core.errors import JibsaError

    page = parse_map_html(html('map'), '역삼동')
    rejected = [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]
    client = _stub_client(page, [], errors=rejected)
    with pytest.raises(JibsaError) as exc:
        search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(floors=['1층'], move_in_now=True))
    assert exc.value.code == 'UPSTREAM_ERROR'
    assert exc.value.message.endswith('floor, moveInNow')


def test_feed_graphql_error_is_upstream_error() -> None:
    from jibsa.core.errors import JibsaError

    page = parse_map_html(html('map'), '역삼동')
    client = _stub_client(page, [], errors=[{'message': '알 수 없는 오류가 발생했어요'}])
    with pytest.raises(JibsaError) as exc:
        search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']))
    assert exc.value.code == 'UPSTREAM_ERROR'
    assert '알 수 없는 오류' in exc.value.message


# --- 좌표 반경 검색 (articleMapPoints → articlesByOriginalArticleIds) ----------

def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


def make_graphql_client(
    responses: dict[str, dict] | None = None,
    requests: list[httpx.Request] | None = None,
) -> DaangnClient:
    """GraphQL 은 persisted query 해시로 응답을 고른다. `responses` 로 해시별 응답을 바꾼다."""
    client = DaangnClient()
    by_hash = {
        client.article_map_points_query_id: fixture('article_map_points'),
        client.articles_by_original_article_ids_query_id: fixture('articles_by_original_article_ids'),
        client.get_region_by_coordinate_query_id: fixture('get_region_by_coordinate'),
        **(responses or {}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.host == 'www.daangn.com':
            return httpx.Response(200, json=regions())
        query_id = json.loads(request.content)['extensions']['persistedQuery']['sha256Hash']
        return httpx.Response(200, json=by_hash[query_id])

    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return client


REJECTED = {'errors': [{'message': 'PersistedQueryNotFound', 'extensions': {'code': 'PERSISTED_QUERY_NOT_IN_LIST'}}]}


@pytest.mark.parametrize('missing_cards', [False, True])
def test_search_area_fetches_only_enough_card_chunks(missing_cards: bool) -> None:
    from jibsa.providers.daangn.service.search import (
        CARD_CHUNK_SIZE,
        search_area,
    )

    points = [
        {'coordinate': {'lat': f'{37.5 + index * 1e-5:.6f}', 'lon': '127.036000'}, 'originalArticleId': str(3000000 + index)}
        for index in range(100)
    ]

    def cards_for(ids: list[str]) -> dict:
        base = fixture('articles_by_original_article_ids')['data']['articles'][1]
        return {'data': {'articles': [{**base, 'originalId': article_id} for article_id in ids if not missing_cards or int(article_id) >= 3000005]}}

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        query_id = body['extensions']['persistedQuery']['sha256Hash']
        if query_id == DaangnClient.article_map_points_query_id:
            return httpx.Response(200, json={'data': {'articleMapPoints': points}})
        if query_id == DaangnClient.articles_by_original_article_ids_query_id:
            return httpx.Response(200, json=cards_for(body['variables']['originalArticleIds']))
        return httpx.Response(200, json=fixture('get_region_by_coordinate'))

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = search_area(client, 37.5, 127.036, limit=25)
    card_requests = [
        request for request in requests
        if json.loads(request.content)['extensions']['persistedQuery']['sha256Hash'] == DaangnClient.articles_by_original_article_ids_query_id
    ]
    # 25건을 채우는 데 20개씩 두 번이면 된다
    assert len(card_requests) == 2 and CARD_CHUNK_SIZE == 20
    assert result.returned == (20 if missing_cards else 25)
    assert [len(json.loads(request.content)['variables']['originalArticleIds']) for request in card_requests] == [20, 5]
    assert '이어 보려면 결과의 next' in result.notes[-1]


def test_search_area_notes_truncated_pins() -> None:
    from jibsa.providers.daangn.service.search import (
        PIN_LIMIT,
        search_area,
    )

    point = {'coordinate': {'lat': '37.501000', 'lon': '127.036000'}, 'originalArticleId': '2000101'}
    truncated = {'data': {'articleMapPoints': [point] * PIN_LIMIT}}
    with make_graphql_client({DaangnClient.article_map_points_query_id: truncated}) as client:
        result = search_area(client, 37.5, 127.036, radius_km=5.0)
    assert result.notes[0].startswith(f'[일부] 당근은 넓은 범위의 매물을 {PIN_LIMIT}건에서 잘라')


def test_search_area_continues_without_region() -> None:
    # 검색 중심의 동은 표시용이라 못 찾아도 매물은 찾는다
    from jibsa.providers.daangn.service.search import search_area

    with make_graphql_client({DaangnClient.get_region_by_coordinate_query_id: REJECTED}) as client:
        result = search_area(client, 37.5, 127.036)
    assert result.region is None
    assert result.returned == 3


def test_search_area_rejected_pins_query_raises_for_fallback() -> None:
    from jibsa.providers.daangn.service.common import FeedQueryRejectedError
    from jibsa.providers.daangn.service.search import search_area

    with make_graphql_client({DaangnClient.article_map_points_query_id: REJECTED}) as client:
        with pytest.raises(FeedQueryRejectedError):
            search_area(client, 37.5, 127.036)


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


# 같은 이름의 역은 첫 역을 쓰고 다른 역을 알린다. --city 를 주면 역 위치의 동으로 그 지역의 역을 고른다
def test_same_name_station_is_noted_and_city_picks_it() -> None:
    from jibsa.core.errors import RegionNotFoundError
    from jibsa.providers.daangn.service.region import (
        find_station,
        same_station_notes,
    )

    requests: list[httpx.Request] = []
    with _same_name_stations_client(requests) as client:
        first = find_station(client, '테스트역')
        assert first is not None and first.lines == ['테스트1호선']
        assert first.others == ['테스트5호선 테스트역']
        assert same_station_notes(first, '다른 역이면 --city') != []
        # --city 가 없으면 역 검색 한 번뿐이다
        assert len(requests) == 1

        chosen = find_station(client, '테스트역', city='서울')
        assert chosen is not None and chosen.lines == ['테스트5호선']
        assert chosen.others == []

        with pytest.raises(RegionNotFoundError) as caught:
            find_station(client, '테스트역', city='부산')
    assert '양평군' in caught.value.hint and '영등포구' in caught.value.hint


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
    assert any('커서' in note for note in result.notes)


# --- 출퇴근 검색 (nearestCommuteStation → commuteFeed → commuteStationArticleConnection) ----

def commute_client(
    requests: list[tuple[str, dict]] | None = None,
    nearest: dict | None = None,
    feed_body: dict | None = None,
) -> DaangnClient:
    # 역마다 다른 매물을 준다. 2000101 은 두 역에 걸린다 (지하철 시간이 짧은 역으로 둔다)
    ids_by_station = {'테스트역': ['2000101', '2000102'], '가까운역': ['2000104', '2000101'], '먼역': ['2000103']}
    # 역 주변 매물은 카드(articlesByOriginalArticleIds)와 같은 필드로 온다 (2026-10-11 실측)
    cards = {card['originalId']: card for card in fixture('articles_by_original_article_ids')['data']['articles']}
    walk = {'2000101': ('테스트역', 5), '2000104': ('가까운역', 4)}
    for article_id, (name, minutes) in walk.items():
        cards[article_id]['subwayStations'] = [
            {'station': {'stationName': name, 'lineNumber': ['테스트1호선']}, 'durationMinutes': minutes},
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'www.daangn.com':
            # 카드에 시·도가 없는 동은 지역 검색으로 채운다
            return httpx.Response(200, json=regions())
        body = json.loads(request.content)
        query = body['extensions']['persistedQuery']['sha256Hash']
        variables = body['variables']
        if query == DaangnClient.nearest_commute_station_query_id:
            name = 'nearest'
            data = nearest or fixture('nearest_commute_station')
        elif query == DaangnClient.commute_feed_query_id:
            name = 'feed'
            data = feed_body or fixture('commute_feed')
        elif query == DaangnClient.commute_station_article_connection_query_id:
            name = 'station'
            data = fixture('commute_station_article_connection')
            data['data']['commuteStationArticleConnection']['edges'] = [
                {'node': {'article': cards[article_id]}} for article_id in ids_by_station[variables['stationName']]
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
    assert all(item.commute_minutes is None for item in result.listings)


def test_commute_unknown_subway_time_is_not_zero() -> None:
    feed = fixture('commute_feed')
    feed['data']['commuteFeed']['edges'][0]['node']['durationMinutes'] = None
    feed['data']['commuteFeed']['edges'][1]['node']['transferCount'] = None
    with commute_client(feed_body=feed) as client:
        result = search_commute(client, 37.5, 127.03)
    assert '가까운역' not in [station.station_name for station in result.stations]
    assert not any(item.commute_station == '가까운역' for item in result.listings)
    assert all(item.transfers is None for item in result.listings if item.commute_station == '먼역')
    assert any('지하철 시간을 모르는 역' in note for note in result.notes)


# --- 단지 매물 목록 (complexByOriginalId.complex.articles) ------------------------


@pytest.mark.parametrize('limit', [1, 100])
def test_commute_limit_is_per_station_and_keeps_cross_station_matches(limit: int) -> None:
    requests: list[tuple[str, dict]] = []
    with commute_client(requests) as client:
        result = search_commute(client, 37.5, 127.03, limit=limit)
    station_requests = [variables for name, variables in requests if name == 'station']
    assert len(station_requests) == 3
    assert all(variables['first'] == limit for variables in station_requests)
    # 모든 검색 대상 역을 조회하며 전체 결과 수로 조기 종료하지 않는다.
    assert len(result.stations) == 3
    assert all(group.returned <= limit for group in result.stations)
    assert result.returned == sum(group.returned for group in result.stations)
    assert result.unique_returned == len({listing.id for group in result.stations for listing in group.listings})


def test_dong_budget_does_not_refill_expired_articles() -> None:
    import copy

    from jibsa.providers.daangn.api.response.search import (
        DaangnArticleFeedResponseModel,
    )

    payloads: list = []
    client = _paged_stub_client(200, payloads)
    data = article_feed()
    template = data['data']['articleFeed']['edges'][0]
    edges = []
    for index in range(20):
        edge = copy.deepcopy(template)
        edge['node']['article']['originalId'] = str(9000000 + index)
        edge['node']['article']['isHide'] = index < 5
        edges.append(edge)
    data['data']['articleFeed']['edges'] = edges

    def feed(payload):
        payloads.append(payload)
        return DaangnArticleFeedResponseModel.model_validate(data)

    client.run_request_article_feed = feed
    result = search_listings(client, [_yeoksam()], conditions=DaangnListingConditions(trade_types=['월세']), limit=20)
    assert len(payloads) == 1 and payloads[0].first == 20
    assert result.fetched == 20 and result.returned == 15
    assert any('다시 채우지 않음' in note for note in result.notes)


@pytest.mark.parametrize(('limit', 'total', 'expected_sizes'), [
    (120, 1201, [50, 50, 20]),
    (1200, 1201, [50] * 24),
    (1200, 1200, [50] * 24),
])
def test_region_complexes_paginates_and_notices_remaining(limit: int, total: int, expected_sizes: list[int]) -> None:
    import copy

    sizes: list[int] = []
    data = fixture('region_complexes')
    template = data['data']['searchComplexes']['edges'][0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'www.daangn.com':
            return httpx.Response(200, json=regions())
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
        return httpx.Response(200, json={'data': {'searchComplexes': {
            'edges': edges, 'pageInfo': {'endCursor': str(end), 'hasNextPage': end < total},
        }}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_region_complexes(client, '역삼동', city='강남구', limit=limit)
    assert sizes == expected_sizes
    assert result.returned == limit
    assert result.has_more is (total > limit)
    assert any('최대값은 1200' in note for note in result.notes) is (limit == 1200 and total > limit)


def test_region_complexes_notices_oversized_final_response() -> None:
    import copy

    template = fixture('region_complexes')['data']['searchComplexes']['edges'][0]
    edges = []
    for index in range(1201):
        edge = copy.deepcopy(template)
        edge['node']['originalId'] = str(9120000 + index)
        edges.append(edge)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'www.daangn.com':
            return httpx.Response(200, json=regions())
        return httpx.Response(200, json={'data': {'searchComplexes': {
            'edges': edges, 'pageInfo': {'endCursor': None, 'hasNextPage': False},
        }}})

    client = DaangnClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_region_complexes(client, '역삼동', city='강남구', limit=1200)
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
                and variables['stationName'] == '테스트역':
            sent.append(('station', variables))
            ids, cursor, has_next = pages[variables.get('after')]
            return httpx.Response(200, json={'data': {'commuteStationArticleConnection': {
                'edges': [{'node': {'article': {'originalId': article_id}}} for article_id in ids],
                'pageInfo': {'endCursor': cursor, 'hasNextPage': has_next},
            }}})
        return handler(request)

    client._client._transport.handler = routed
    with client:
        result = search_commute(client, 37.5, 127.03, max_minutes=0, limit=2)

    # 받은 수(1건)로 예산을 세고 남은 1건만 다음 페이지에서 받는다
    station_pages = [(variables['first'], variables.get('after')) for name, variables in sent
                     if name == 'station' and variables['stationName'] == '테스트역']
    assert station_pages == [(2, None), (1, 'cursor-1')]
    assert result.stations[0].inspected == 2
