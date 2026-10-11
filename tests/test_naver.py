import json
from pathlib import Path

import httpx
import pytest

from jibsa.core.errors import JibsaError
from jibsa.providers.naver.api.client import (
    NaverClient,
    should_retry_naver,
)
from jibsa.providers.naver.api.response.search import (
    NaverArticleClusteredArticlesV1ResponseModel,
)
from jibsa.providers.naver.service.common import (
    NaverTradeConditions,
    article_info_to_listing,
)
from jibsa.providers.naver.service.listing import (
    get_listing,
    list_complex_articles,
)
from jibsa.providers.naver.service.real_price import get_real_prices
from jibsa.providers.naver.service.region import legal_division_code_at
from jibsa.providers.naver.service.search import (
    COMPLEX_FILTER_NOTE,
    ONE_ROOM_SHAPE_NOTE,
    NaverListingConditions,
    search_area,
)
from jibsa.providers.naver.service.trend import get_district_trend


FIXTURES = Path(__file__).parent / 'fixtures' / 'naver'
ROUTES = {
    '/front-api/v1/complex': 'complex_v1',
    '/front-api/v1/complex/v2/pyeong/realPrice': 'complex_pyeong_real_price_v2',
    '/front-api/v1/legalDivision/searchByCoordinate': 'legal_division_search_by_coordinate_v1',
    '/front-api/v1/data-service/transport': 'data_service_transport_v1',
    '/front-api/v1/education/building/school': 'education_building_school_v1',
    '/front-api/v1/article/key': 'article_key_v1',
    '/front-api/v1/article/basicInfo': 'article_basic_info_v1',
    '/front-api/v1/article/maintenanceFee': 'article_maintenance_fee_v1',
    '/front-api/v1/article/tax': 'article_tax_v1',
    '/front-api/v1/article/agentFee': 'article_agent_fee_v1',
    '/front-api/v1/complex/article/list': 'complex_article_list_v1',
    '/front-api/v1/article/map/articleClusters': 'article_map_article_clusters_v1',
    '/front-api/v1/article/clusteredArticles': 'article_clustered_articles_v1',
    '/front-api/v1/legalDivision/articleCountWeeklyInfo': 'legal_division_article_count_weekly_info_v1',
    '/front-api/v1/legalDivision/realTradeCountWeeklyList': 'legal_division_real_trade_count_weekly_list_v1',
}


def load(name: str) -> dict:
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


def make_client(requests: list[httpx.Request] | None = None) -> NaverClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


# --- response / normalisation ----------------------------------------------

def test_listing_converts_won_to_manwon() -> None:
    page = NaverArticleClusteredArticlesV1ResponseModel.model_validate(load('article_clustered_articles_v1'))
    listing = article_info_to_listing(page.result.items[0])
    assert listing.trade_type == '월세'
    assert (listing.deposit_manwon, listing.rent_manwon) == (5000, 200)
    assert listing.price_manwon is None
    assert listing.url.startswith('https://fin.land.naver.com/articles/')


def test_unknown_trade_code_is_skipped_in_list() -> None:
    # 모르는 거래 유형을 매매로 잘못 내보내지 않도록 목록에서 뺀다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        body['result']['list'][0]['representativeArticleInfo']['tradeType'] = 'B9'
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_complex_articles(client, 100001, limit=10)
    first_id = load('complex_article_list_v1')['result']['list'][0]['representativeArticleInfo']['articleNumber']
    assert result.returned == 2
    assert first_id not in {listing.id for listing in result.listings}


def test_unknown_trade_code_detail_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/key'):
            body['result']['type']['tradeType'] = 'B9'
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client, pytest.raises(ListingUnavailableError) as exc:
        get_listing(client, '1000000001')
    assert exc.value.details['reason'] == 'UNKNOWN_TRADE_TYPE'
    assert exc.value.details['listing_status'] == 'B9'
    # 거래 유형을 모르면 나머지 요청은 보내지 않는다
    assert [request.url.path for request in requests] == ['/front-api/v1/article/key']


def test_naver_does_not_retry_429() -> None:
    request = httpx.Request('GET', 'https://fin.land.naver.com/')
    blocked = httpx.HTTPStatusError('429', request=request, response=httpx.Response(429, request=request))
    server = httpx.HTTPStatusError('502', request=request, response=httpx.Response(502, request=request))
    assert should_retry_naver(blocked) is False
    assert should_retry_naver(server) is True


# --- service ----------------------------------------------------------------


def test_officetel_pyeong_supply_equal_to_contract_is_unknown() -> None:
    # 오피스텔 평형표의 공급 칸에 계약면적이 그대로 오면(공급 = 계약) 공급면적을 모름으로 둔다.
    # 실제 공급면적이 따로 오면(공급 40.66 < 계약 57.51) 그대로 둔다. 아파트는 손대지 않는다.
    from jibsa.providers.naver.api.response.common import NaverPyeongModel
    from jibsa.providers.naver.service.complex import _pyeong

    def pyeong(supply: float, contract: float) -> NaverPyeongModel:
        return NaverPyeongModel.model_validate(
            {'number': 1, 'name': '30B', 'exclusiveArea': 20.89, 'supplyArea': supply, 'contractArea': contract}
        )

    copied = _pyeong(pyeong(30.59, 30.59), is_officetel=True)
    assert (copied.supply_m2, copied.contract_m2) == (None, 30.59)
    assert _pyeong(pyeong(40.66, 57.51), is_officetel=True).supply_m2 == 40.66
    assert _pyeong(pyeong(30.59, 30.59)).supply_m2 == 30.59


def test_real_prices_in_manwon() -> None:
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = get_real_prices(client, 100001, 1, pages=3)
    first = result.transactions[0]
    assert (first.trade_date, first.price_manwon) == ('2026-01-10', 145000)
    # v2 는 페이지가 0부터고, 다음 페이지가 없다고 하면(hasNextPage false) 더 묻지 않는다
    [request] = requests
    assert (request.url.params['page'], request.url.params['size']) == ('0', '10')


def test_get_listing_monthly_rent_uses_warranty_and_rent_amount() -> None:
    # 전세·월세 상세는 price 대신 warrantyAmount / rentAmount 로 온다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/key'):
            body['result']['type']['tradeType'] = 'B2'
        if request.url.path.endswith('/basicInfo'):
            body['result']['priceInfo'] = {'tradeType': 'B2', 'warrantyAmount': 10_000_000, 'rentAmount': 830_000, 'loan': 0}
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000002')
    assert (detail.trade_type, detail.deposit_manwon, detail.rent_manwon, detail.price_manwon) == ('월세', 1000, 83, None)


def test_search_area_stops_at_page_request_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # 매물이 limit 보다 적으면 클러스터를 끝까지 훑게 되므로 요청 상한에서 멈추고 알린다
    import jibsa.providers.naver.service.search as naver_search

    monkeypatch.setattr(naver_search, 'MAX_CLUSTER_PAGE_REQUESTS', 2)
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = search_area(client, 37.4928, 127.0305, conditions=NaverListingConditions(trade_types=['월세']), radius_km=3.0, limit=90)
    assert sum(request.url.path.endswith('/clusteredArticles') for request in requests) == 2
    assert result.notes[0].startswith('네이버 차단을 피하려고 검색 중심에서 가까운 지도 칸')
    assert 'notes' not in result.model_dump()

    # limit 을 채워 멈추면 상한에 걸린 게 아니라 안내가 없다
    with make_client() as client:
        notes = search_area(client, 37.4928, 127.0305, radius_km=3.0, limit=1).notes
    assert not any(note.startswith('네이버 차단을 피하려고') for note in notes)


def test_search_area_moves_on_from_sparse_cluster() -> None:
    # 칸에 매물이 limit 보다 적으면 요청한 수만큼 썼다고 치지 않고 다음 칸에서 나머지를 받는다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/clusteredArticles'):
            cluster_id = json.loads(request.content)['clusterId']
            body['result']['hasNextPage'] = False
            for index, item in enumerate(body['result']['list']):
                item['representativeArticleInfo']['articleNumber'] = f'{cluster_id}-{index}'
        return httpx.Response(200, json=body)

    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(recording))
    with client:
        result = search_area(client, 37.4928, 127.0305, radius_km=3.0, limit=30)
    # 픽스처의 지도 칸 5개에 3건씩이라 칸을 모두 열어 15건을 받는다
    assert sum(request.url.path.endswith('/clusteredArticles') for request in requests) == 5
    assert len(result.listings) == 15


def test_search_area_puts_unknown_distance_last() -> None:
    # 좌표가 없어 거리를 모르는 매물을 가장 가까운 매물처럼 맨 앞에 두지 않는다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/clusteredArticles'):
            body['result']['list'][0]['representativeArticleInfo']['address'].pop('coordinates', None)
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = search_area(client, 37.4928, 127.0305, radius_km=3.0, limit=50)
    distances = [listing.distance_km for listing in result.listings]
    assert distances[-1] is None
    assert None not in distances[:-1]
    assert distances[:-1] == sorted(distances[:-1])


def test_removed_article_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError
    from jibsa.providers.naver.api.response.listing import (
        NaverArticleKeyV1ResponseModel,
    )

    # 내려간 매물은 {"isSuccess": false, "result": {}} 로 온다
    response = NaverArticleKeyV1ResponseModel.model_validate({'isSuccess': False, 'result': {}})
    assert response.result is None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'isSuccess': False, 'result': {}})

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client, pytest.raises(ListingUnavailableError):
        get_listing(client, '2500000000')


def test_malformed_article_number_is_unavailable() -> None:
    from jibsa.core.errors import ListingUnavailableError

    # 형식에 안 맞는 번호는 400 FST_ERR_VALIDATION 으로 거절된다
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={'detailCode': 'FST_ERR_VALIDATION', 'message': ''})

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client, pytest.raises(ListingUnavailableError):
        get_listing(client, '1')


def test_complex_articles_and_real_price_omit_not_applicable() -> None:
    with make_client() as client:
        articles = list_complex_articles(client, 100001, limit=1).model_dump(mode='json')
        real = get_real_prices(client, 100001, 1).model_dump(mode='json')
    assert 'distance_km' not in articles['listings'][0]
    sale = real['transactions'][0]
    assert 'price_manwon' in sale and 'deposit_manwon' not in sale and 'trade_type' not in sale
    # 갱신 계약은 전월세에만 있다
    assert 'renewal' not in sale


def test_detail_without_complex_omits_complex_fields() -> None:
    # 단지에 속하지 않는 빌라는 단지·동·평형 번호가 해당 없음이라 null 이 아니라 키를 뺀다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/key'):
            body['result'].pop('key', None)
        if request.url.path.endswith('/basicInfo'):
            body['result'].pop('communalComplexInfo', None)
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        dumped = get_listing(client, '1000000001').model_dump(mode='json')
    assert not {'complex_number', 'complex_name', 'dong', 'pyeong_number'} & set(dumped)

    # 단지 매물은 그대로 낸다
    with make_client() as client:
        dumped = get_listing(client, '1000000001').model_dump(mode='json')
    assert (dumped['complex_number'], dumped['complex_name'], dumped['dong'], dumped['pyeong_number']) == (100001, '테스트아파트', '101', 1)


def test_loan_distinguishes_none_from_unknown() -> None:
    from jibsa.providers.naver.api.response.listing import NaverPriceInfoModel
    from jibsa.providers.naver.service.listing import _loan_manwon

    assert _loan_manwon(NaverPriceInfoModel.model_validate({'loan': 755150000, 'loanCode': '2'})) == 75515
    assert _loan_manwon(NaverPriceInfoModel.model_validate({'loan': 0, 'loanCode': '0'})) == 0
    assert _loan_manwon(NaverPriceInfoModel.model_validate({'loan': 0})) is None


def _cluster_filters(requests: list[httpx.Request]) -> list[dict]:
    return [
        json.loads(request.content)['filter']
        for request in requests if request.url.path.endswith('/articleClusters')
    ]


def test_search_area_sends_server_filters() -> None:
    # 가격(만원 → 원)·방 수·전용면적·층·방향은 서버 필터 키로 보낸다 (키가 틀리면 서버가 조용히 무시한다)
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        search_area(
            client, 37.4928, 127.0305, radius_km=1.0, limit=5, conditions=NaverListingConditions(
                deposit_max=1000, rent_max=50, price_max=50000,
                room_types=['투룸', '포룸이상'], area_min=33, area_max=49.5,
                floors=['1층', '지하층'], directions=['남향', '남동향'],
            ),
        )
    [filter_] = _cluster_filters(requests)
    assert filter_['warrantyPrice'] == {'max': 10_000_000}
    assert filter_['rentPrice'] == {'max': 500_000}
    assert filter_['dealPrice'] == {'max': 500_000_000}
    assert filter_['roomCount'] == ['RCF02', 'RCF04']
    assert filter_['space'] == {'min': 33, 'max': 49.5}
    assert filter_['filtersExclusiveSpace'] is True
    assert filter_['floorTypes'] == ['FLF01', 'FLF06']
    # 상세 응답의 SE 가 아니라 필터가 받는 ES 로 보낸다
    assert filter_['directionTypes'] == ['SS', 'ES']


def test_search_area_sends_extended_filters() -> None:
    # 관리비·욕실·시설·원룸 구조·입주·융자·사진·단지(세대수·주차·현관)·사용승인 연차도 서버 필터로 보낸다
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = search_area(
            client, 37.4928, 127.0305, radius_km=1.0, limit=5, conditions=NaverListingConditions(
                deposit_min=500, rent_min=30, price_min=10000,
                manage_cost_min=12, manage_cost_max=47,
                bathrooms=['2개'], facilities=['주차', '엘리베이터'], one_room_shapes=['분리형'],
                move_in=['바로입주', '90일내'], loan='없음', photo_only=True,
                household_min=1400, parking=['세대당1대'], entrances=['계단식'],
                building_age_min=5, building_age_max=19, subway_minutes=8,
            ),
        )
    [filter_] = _cluster_filters(requests)
    assert filter_['warrantyPrice'] == {'min': 5_000_000}
    assert filter_['rentPrice'] == {'min': 300_000}
    assert filter_['dealPrice'] == {'min': 100_000_000}
    assert filter_['managementFee'] == {'min': 120_000, 'max': 470_000}
    assert filter_['bathRoomCount'] == ['RCF02']
    assert filter_['optionTypes'] == ['OPF02', 'OPF01']
    assert filter_['oneRoomShapeTypes'] == ['20']
    assert filter_['moveInTypes'] == ['MVF01', 'MVF02']
    assert filter_['loanRatioType'] == '00'
    assert filter_['hasArticlePhoto'] is True
    assert filter_['householdNumber'] == {'min': 1400}
    assert filter_['parkingTypes'] == ['PKF01']
    assert filter_['entranceTypes'] == ['10']
    assert filter_['approvalElapsedYear'] == {'min': 5, 'max': 19}
    # 역세권은 사이트처럼 하한 0 을 함께 보낸다
    assert filter_['walkingMinuteToSubwayStation'] == {'min': 0, 'max': 8}
    # 단지 정보 필터는 단지가 없는 빌라를, 원룸 구조는 구조를 입력하지 않은 매물을 빼므로 둘 다 알린다
    assert COMPLEX_FILTER_NOTE in result.notes
    assert ONE_ROOM_SHAPE_NOTE in result.notes


@pytest.mark.parametrize(
    ('fee', 'expected'),
    [
        # 중개사가 0원으로 입력했다
        ({'typeCode': '02', 'etcDetail': {'amount': 0, 'type': '02'}, 'criteriaType': '02'}, 0),
        # 관리비를 확인하지 않았다. 목록에서는 이것도 0 으로 온다
        ({'typeCode': '03', 'uncheckDetail': {'type': '03'}}, None),
        # 정액 합계를 etcDetail 이 아닌 fixNonDetailList 로 준다 (원룸 2652339975, 2026-10-11)
        (
            {'typeCode': '04', 'criteriaType': '02',
             'fixNonDetailList': {'type': '98', 'categoryList': ['01', '12', '15'], 'amount': 130000}},
            13.0,
        ),
        # 항목별로 입력했다. 정액 항목을 더한 값이 관리비이고 실비 항목은 금액이 없다
        (
            {'typeCode': '01', 'criteriaType': '01', 'fixDetailList': [
                {'type': '01', 'unitType': '01', 'amount': 100000}, {'type': '11', 'unitType': '02'},
            ]},
            10.0,
        ),
    ],
)
def test_detail_manage_cost_zero_is_known_unchecked_is_unknown(fee: dict, expected: float | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/maintenanceFee'):
            return httpx.Response(200, json={'isSuccess': True, 'result': fee})
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert detail.manage_cost_manwon == expected


# --- 빌라 단지 (연립·다세대) -------------------------------------------------

def make_path_client(requests: list[httpx.Request], overrides: dict[str, dict]) -> NaverClient:
    """경로별로 픽스처 대신 다른 응답을 준다 (`overrides` 의 키는 /front-api/v1 뒤 경로)."""
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path.removeprefix('/front-api/v1')
        return httpx.Response(200, json=overrides.get(path) or load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def _paths(requests: list[httpx.Request]) -> list[str]:
    return [request.url.path.removeprefix('/front-api/v1') for request in requests]


def test_detail_surroundings_failure_is_unknown() -> None:
    # 교통·학교 조회가 실패해도 상세는 내보내고 그 값만 모름(null)이다
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(('/data-service/transport', '/education/building/school')):
            return httpx.Response(404, json={'isSuccess': False})
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert (detail.nearby_subways, detail.bus_routes, detail.schools) == (None, None, None)
    assert detail.price_manwon is not None


def test_list_complex_articles_price_filter() -> None:
    # 가격은 만원으로 받아 원으로 보내고, 서버가 걸러 준 매물은 다시 거르지 않는다
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = list_complex_articles(
            client, 100001, conditions=NaverTradeConditions(price_min=160000, price_max=170000, deposit_max=50000), limit=10,
        )
    body = json.loads(requests[0].content)
    assert (body['minDealPrice'], body['maxDealPrice'], body['maxWarrantyPrice']) == (1600000000, 1700000000, 500000000)
    assert 'minRentPrice' not in body and 'maxRentPrice' not in body
    # 픽스처는 가격 밖 매물도 담고 있지만 서버 응답으로 보고 그대로 둔다
    assert [listing.id for listing in result.listings] == ['1000000001', '1000000002', '1000000003']


def test_real_prices_keep_zero_deposit() -> None:
    # 보증금 0원 월세는 모름(null)이 아니라 0이다
    data = load('complex_pyeong_real_price_v2')
    data['result']['list'] = [{**data['result']['list'][0], 'dealPrice': 0, 'deposit': 0, 'monthlyRent': 1500000}]
    with make_path_client([], {'/complex/v2/pyeong/realPrice': data}) as client:
        result = get_real_prices(client, 100001, 1, trade_type='월세')
    dumped = result.transactions[0].model_dump()
    assert (dumped['deposit_manwon'], dumped['rent_manwon']) == (0, 150)
    assert 'price_manwon' not in dumped


def _complex_article_page(numbers: list[str], has_next: bool) -> dict:
    base = load('complex_article_list_v1')
    item = base['result']['list'][0]
    items = [
        {**item, 'representativeArticleInfo': {**item['representativeArticleInfo'], 'articleNumber': number}}
        for number in numbers
    ]
    return {**base, 'result': {**base['result'], 'list': items, 'hasNextPage': has_next, 'lastInfo': [1, 100.0, numbers[-1]]}}


def test_list_complex_articles_stops_at_request_cap() -> None:
    # 페이지마다 매물이 적어 limit 을 못 채워도 요청은 상한에서 멈추고 안내한다
    from jibsa.providers.naver.service.listing import MAX_COMPLEX_ARTICLE_PAGE_REQUESTS

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = len(requests) * 100
        return httpx.Response(200, json=_complex_article_page([str(start + i) for i in range(3)], has_next=True))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_complex_articles(client, 100001, limit=180)
    assert len(requests) == MAX_COMPLEX_ARTICLE_PAGE_REQUESTS
    assert len(result.listings) == 3 * MAX_COMPLEX_ARTICLE_PAGE_REQUESTS
    assert any('번까지만 받았습니다' in note for note in result.notes)


def test_list_complex_articles_stops_when_cursor_stalls() -> None:
    # 다음 페이지가 있다면서 같은 매물만 다시 주면 커서가 멈춘 것으로 보고 끝낸다 (중복도 내보내지 않는다)
    stuck = _complex_article_page(['1000000001', '1000000002'], has_next=True)
    requests: list[httpx.Request] = []
    with make_path_client(requests, {'/complex/article/list': stuck}) as client:
        result = list_complex_articles(client, 100001, limit=90)
    assert _paths(requests) == ['/complex/article/list', '/complex/article/list']
    assert [listing.id for listing in result.listings] == ['1000000001', '1000000002']
    assert any('중복' in note for note in result.notes)


# --- 매매 매물 중개보수·세금 -------------------------------------------------


def test_sale_cost_lookup_failure_is_unknown() -> None:
    # 세금 조회가 실패해도 상세는 그대로 주고 그 값만 모름(null)으로 둔다
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/article/tax'):
            return httpx.Response(400, json={'isSuccess': False})
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert detail.agent_fee_manwon == 1050
    assert detail.model_dump()['acquisition_tax_manwon'] is None


def test_detail_optional_lookup_failure_is_unknown() -> None:
    # 관리비·법정동·단지 조회가 HTTP 오류가 아닌 이유(응답 모양이 바뀜)로 실패해도 상세는 내보내고 그 값만 모름이다
    broken = ('/article/maintenanceFee', '/legalDivision/searchByCoordinate', '/complex')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.removeprefix('/front-api/v1') in broken:
            return httpx.Response(200, json={'isSuccess': True, 'result': 'unexpected'})
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert (detail.manage_cost_manwon, detail.address) == (None, None)
    assert detail.price_manwon is not None


def test_detail_transport_error_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    # 재시도 뒤에도 남은 연결 오류는 부가 조회면 그 값만 모름이다
    from tenacity import wait_none

    from jibsa.providers.naver.api.client import NaverClient as Client

    monkeypatch.setattr(Client.run_request_data_service_transport_v1.retry, 'wait', wait_none())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/data-service/transport'):
            raise httpx.ConnectTimeout('timeout', request=request)
        return httpx.Response(200, json=load(ROUTES[request.url.path]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert (detail.nearby_subways, detail.bus_routes) == (None, None)
    assert detail.schools


# --- 정렬 검색 ---------------------------------------------------------------


def test_complex_listing_budget_preserves_cursor_without_refilling() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        # seed 가 빠지면 랭킹순이 페이지마다 다시 섞인다
        if len(requests) > 1:
            assert body['seed'] == 'test-seed'
            assert body['lastInfo'] == [len(requests) - 1]
        else:
            assert 'seed' not in body
        page = _complex_article_page(['1000000001', '1000000002'] + [f'{len(requests)}{i:08d}' for i in range(28)], has_next=True)
        page['result'].update(seed='test-seed', lastInfo=[len(requests)], totalCount=200)
        return httpx.Response(200, json=page)
    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = list_complex_articles(client, 100001, limit=120)
    assert len(requests) == 4
    assert all(json.loads(request.content)['size'] == 30 for request in requests)
    assert result.returned == 114
    assert any('추가 조회하지 않았습니다' in note for note in result.notes)
    assert any('최대값은 120' in note for note in result.notes)
    assert not any('--limit을 늘리' in note for note in result.notes)


def test_whole_dong_budget_carries_seed_and_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        paging = json.loads(request.content)['articlePagingRequest']
        assert paging['size'] == 30
        if len(requests) > 1:
            assert paging['seed'] == 'test-seed'
            assert paging['lastInfo'] == [len(requests) - 1]
        page = _complex_article_page([f'{len(requests)}{i:08d}' for i in range(30)], has_next=True)
        page['result'].update(seed='test-seed', lastInfo=[len(requests)], totalCount=200)
        return httpx.Response(200, json=page)
    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        result = search_area(client, 37.5, 127.0, legal_division_code='1168010100', sort='랭킹순', limit=120)
    assert len(requests) == 4
    assert result.returned == 120


def test_whole_dong_stops_when_cursor_stalls() -> None:
    # 받은 개수로 세므로, 다음 페이지가 있다면서 같은 매물만 주면 상한까지 가지 않고 멈춘다
    stuck = _complex_article_page(['1000000001', '1000000002'], has_next=True)
    requests: list[httpx.Request] = []
    with make_path_client(requests, {'/article/legalDivisionArticleList': stuck}) as client:
        result = search_area(client, 37.5, 127.0, legal_division_code='1168010100', sort='랭킹순', limit=120)
    assert len(requests) == 2
    assert [listing.id for listing in result.listings] == ['1000000001', '1000000002']
    assert any('추가 조회하지 않았습니다' in note for note in result.notes)


def _short_page_client(requests: list[httpx.Request], path: str, make_page) -> NaverClient:
    """`path` 에는 페이지마다 새 항목을 조금씩 주며 다음 페이지가 있다고 답한다 (요청 상한 확인용)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.removeprefix('/front-api/v1') != path:
            return httpx.Response(200, json=load(ROUTES[request.url.path]))
        requests.append(request)
        return httpx.Response(200, json=make_page(len(requests)))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def _short_article_page(index: int) -> dict:
    return _complex_article_page([f'{index}{i:08d}' for i in range(5)], has_next=True)


def test_whole_dong_stops_at_request_cap() -> None:
    # 받은 개수로 세므로 덜 찬 페이지가 이어지면 limit 전에 요청 상한에서 멈춘다.
    # 안내의 건수는 상한 × 페이지 크기가 아니라 실제로 받은 수다
    from jibsa.providers.naver.service.search import MAX_LEGAL_DIVISION_PAGE_REQUESTS

    requests: list[httpx.Request] = []
    with _short_page_client(requests, '/article/legalDivisionArticleList', _short_article_page) as client:
        result = search_area(client, 37.5, 127.0, legal_division_code='1168010100', sort='랭킹순', limit=120)
    assert len(requests) == MAX_LEGAL_DIVISION_PAGE_REQUESTS
    assert result.returned == 5 * MAX_LEGAL_DIVISION_PAGE_REQUESTS
    assert any(f'{5 * MAX_LEGAL_DIVISION_PAGE_REQUESTS}건까지만' in note for note in result.notes)


# --- 동네 추이 --------------------------------------------------------------------


def test_district_trend_partial_failure_and_total_failure() -> None:
    def failing(paths: set[str]):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.rsplit('/', 1)[-1] in paths:
                return httpx.Response(400, json={})
            return httpx.Response(200, json=load(ROUTES[request.url.path]))
        client = NaverClient()
        client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
        return client

    with failing({'pyeongPriceWeeklyList'}) as client:
        trend = get_district_trend(client, '1100010100')
    assert trend.price_per_pyeong is None and trend.listing_count is not None
    all_paths = {'articleCountWeeklyInfo', 'pyeongPriceWeeklyList', 'realTradeCountWeeklyList'}
    with failing(all_paths) as client, pytest.raises(JibsaError) as exc:
        get_district_trend(client, '1100010100')
    assert exc.value.code == 'UPSTREAM_ERROR'


def test_coordinate_lookup_failure_is_upstream_error_not_missing_dong() -> None:
    # 이 엔드포인트의 실패 봉투는 실측으로 재현되지 않아(잘못된 좌표는 HTTP 400) 가짜 응답으로 확인한다.
    # 실패를 '법정동 없음' 으로 보면 trend 가 REGION_NOT_FOUND 로 멀쩡한 검색어를 바꾸게 한다
    def client_returning(body: dict) -> NaverClient:
        client = NaverClient()
        client.__dict__['_client'] = httpx.Client(
            base_url=client.base_url, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
        )
        return client

    with client_returning({'isSuccess': True, 'detailCode': 'success', 'result': None}) as client:
        assert legal_division_code_at(client, 34.0, 125.0) is None
    with client_returning({'isSuccess': False, 'detailCode': 'INTERNAL_ERROR'}) as client, pytest.raises(JibsaError) as exc:
        legal_division_code_at(client, 37.5, 127.0)
    assert exc.value.code == 'UPSTREAM_ERROR'
