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
from jibsa.providers.naver.service.region import (
    legal_division_code_at,
    resolve_complex_number,
    resolve_search_region,
)
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
    # 지도 범위 목록은 지도 칸 매물(clusteredArticles)과 같은 매물 목록 모양이다
    '/front-api/v1/article/boundedArticles': 'article_clustered_articles_v1',
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


def _bounded_filters(requests: list[httpx.Request]) -> list[dict]:
    """반경 검색(boundedArticles)에 보낸 필터. 픽스처 한 쪽이 3건이라 limit 3 이면 요청이 한 번이다."""
    return [
        json.loads(request.content)['filter']
        for request in requests if request.url.path.endswith('/boundedArticles')
    ]


def test_search_area_sends_server_filters() -> None:
    # 가격(만원 → 원)·방 수·전용면적·층·방향은 서버 필터 키로 보낸다 (키가 틀리면 서버가 조용히 무시한다)
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        search_area(
            client, 37.4928, 127.0305, radius_km=1.0, limit=3, conditions=NaverListingConditions(
                deposit_max=1000, rent_max=50, price_max=50000,
                room_types=['투룸', '포룸이상'], area_min=33, area_max=49.5,
                floors=['1층', '지하층'], directions=['남향', '남동향'],
            ),
        )
    [filter_] = _bounded_filters(requests)
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
            client, 37.4928, 127.0305, radius_km=1.0, limit=3, conditions=NaverListingConditions(
                deposit_min=500, rent_min=30, price_min=10000,
                manage_cost_min=12, manage_cost_max=47,
                bathrooms=['2개'], facilities=['주차', '엘리베이터'], one_room_shapes=['분리형'],
                move_in=['바로입주', '90일내'], loan='없음', photo_only=True,
                household_min=1400, parking=['세대당1대'], entrances=['계단식'],
                building_age_min=5, building_age_max=19, subway_minutes=8,
            ),
        )
    [filter_] = _bounded_filters(requests)
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
        ({'typeCode': '03'}, None),
        # 확인 불가 사유가 '없음'(99)이면 웹이 관리비 '없음' 으로 보여 준다
        ({'typeCode': '03', 'uncheckDetail': {'type': '99'}}, 0),
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
    # 포함 항목은 관리비 없음일 때만 빈 목록이고, 모르면 null 이다
    if fee.get('uncheckDetail') == {'type': '99'}:
        assert detail.manage_cost_includes == []
    elif fee['typeCode'] == '03':
        assert detail.manage_cost_includes is None


def test_detail_move_in_within_and_after_keep_the_bound() -> None:
    # 웹은 이내입주·이후입주를 날짜 뒤에 붙여 구분해 보여 준다
    from jibsa.providers.naver.api.response.listing import NaverMovingInInfoModel
    from jibsa.providers.naver.service.listing import _move_in_label

    def label(code: str, date: str | None, negotiation: bool = False) -> str | None:
        return _move_in_label(NaverMovingInInfoModel.model_validate(
            {'movingInType': code, 'movingInDate': date, 'movingInNegotiation': negotiation},
        ))

    assert label('MV002', '20261201') == '2026-12-01 이내'
    assert label('MV003', '20261201', True) == '2026-12-01 이후 (협의 가능)'
    assert label('MV004', '20261201') == '2026-12-01'
    assert label('MV002', None) is None
    # 초순·중순·하순은 달만 있으면 돼 연월만 와도 낸다. 날짜 자리의 '-' 는 값이 없다는 표시라 모름이다 (실측에 없는 값)
    assert label('EARLY', '2026-11') == '2026-11 초순'
    assert label('LATE', '202611') == '2026-11 하순'
    assert label('MV002', '-') is None
    assert label('EARLY', '-') is None
    # 이내·이후도 연월만 오면 연월로 낸다. 못 읽는 글자도 협의 가능은 붙인다 (2026-11-16 리뷰)
    assert label('MV003', '202612') == '2026-12 이후'
    assert label('MID', 'abc', True) == 'abc (협의 가능)'
    # 꼴만 맞고 없는 날짜는 날짜로 읽지 않고 받은 글자 그대로 둔다 ('0000-00 초순' 을 내지 않는다, 2026-11-17 리뷰)
    assert label('EARLY', '0000-00-00') == '0000-00-00'
    assert label('MV002', '2026-02-30') == '2026-02-30'


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
    assert any('다시 채우지 않음' in note for note in result.notes)
    assert any('최대값은 120' in note for note in result.notes)
    assert not any('--limit 을 늘리' in note for note in result.notes)


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
    # 끝 문구(더 받을 매물이 남았는지)는 받은 수와 서버 수로 정해져 여기서는 보지 않는다
    assert any(note.startswith('[제외]') for note in result.notes)


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


# --- 위치·단지 이름 해석 -----------------------------------------------------------


def _ok(result: object) -> dict:
    return {'isSuccess': True, 'detailCode': 'success', 'result': result}


def _complex_item(number: int, name: str) -> dict:
    return {
        'complexNumber': number, 'complexName': name, 'type': 'A01',
        'legalDivisionName': '서울시 강남구 개포동', 'legalDivisionNumber': '1168010300',
        'coordinates': {'xCoordinate': 127.05, 'yCoordinate': 37.48},
    }


@pytest.mark.parametrize(
    'items,total,expected',
    [
        # 이름이 정확히 같은 후보가 하나면 그 단지다 (비슷한 이름 후보가 더 있어도, 후보를 다 받았을 때)
        ([_complex_item(1, '현대아이파크'), _complex_item(2, '현대')], 2, 2),
        # 이름이 같은 단지가 여럿이면 첫 후보를 고르지 않고 후보를 알린다 (네이버 웹은 목록에서 사람이 고른다)
        ([_complex_item(1, '현대'), _complex_item(2, '현대'), _complex_item(3, '현대아이파크')], 3924, None),
        # 다음 쪽이 남았으면 정확히 같은 이름이 하나여도 고르지 않는다 (뒤쪽에 같은 이름이 더 있을 수 있다)
        ([_complex_item(1, '현대아이파크'), _complex_item(2, '현대')], 852, None),
    ],
)
def test_complex_name_picks_only_unique_exact_match(items: list[dict], total: int, expected: int | None) -> None:
    requests: list[httpx.Request] = []
    body = _ok({'hasNextPage': total > len(items), 'totalCount': total, 'list': items})
    with make_path_client(requests, {'/search/autocomplete/complexes': body}) as client:
        if expected is not None:
            assert resolve_complex_number(client, '현대')[0] == expected
        else:
            with pytest.raises(JibsaError) as exc:
                resolve_complex_number(client, '현대')
            assert exc.value.code == 'REGION_AMBIGUOUS'
            assert exc.value.details['candidate_count'] == total
            assert exc.value.details['candidates'][0].startswith(f'{items[0]["complexName"]} (')


def _ga_dong_address(full_address: str, code: str) -> dict:
    return _ok({'type': 'jibun-address', 'jibunAddress': {'totalCount': 1, 'list': [{
        'fullAddress': full_address, 'itemLevel': 8, 'x': 127.05, 'y': 37.54,
        'addressElements': {
            'sido': '서울특별시', 'sigugun': full_address.split()[1], 'dongmyun': full_address.split()[-1], 'bcode': code,
        },
    }]}})


@pytest.mark.parametrize(
    'query,found,dongs,expected',
    [
        # '성수동' 은 주소 검색이 성수동1가 한 곳만 준다. 첫 동을 고르거나 합치지 않고 '○가' 동을 모두 알린다
        (
            '성수동',
            ('서울특별시 성동구 성수동1가', '1120011400'),
            [('1120011400', '서울시 성동구 성수동1가'), ('1120011500', '서울시 성동구 성수동2가')],
            ['서울특별시 성동구 성수동1가', '서울특별시 성동구 성수동2가'],
        ),
        # 같은 앞 이름의 '○가' 동이 다른 구에 있어도 한 동만 조용히 찾지 않는다 (충정로1가는 중구, 2가·3가는 서대문구)
        (
            '충정로',
            ('서울특별시 중구 충정로1가', '1114017000'),
            [
                ('1114017000', '서울시 중구 충정로1가'),
                ('1141010200', '서울시 서대문구 충정로3가'),
                ('1141010100', '서울시 서대문구 충정로2가'),
            ],
            ['서울특별시 중구 충정로1가', '서울특별시 서대문구 충정로2가', '서울특별시 서대문구 충정로3가'],
        ),
    ],
)
def test_ga_dong_base_name_is_ambiguous(
    query: str, found: tuple[str, str], dongs: list[tuple[str, str]], expected: list[str],
) -> None:
    requests: list[httpx.Request] = []
    autocomplete = _ok({'hasNextPage': False, 'totalCount': len(dongs), 'list': [
        {
            'legalDivisionNumber': code, 'legalDivisionName': name, 'legalDivisionLevelType': 'EUP',
            'coordinates': {'xCoordinate': 127.05, 'yCoordinate': 37.54},
        }
        for code, name in dongs
    ]})
    overrides = {'/maps-search/address': _ga_dong_address(*found), '/search/autocomplete/legalDivisions': autocomplete}
    with make_path_client(requests, overrides) as client:
        with pytest.raises(JibsaError) as exc:
            resolve_search_region(client, query)
    assert exc.value.code == 'REGION_AMBIGUOUS'
    assert exc.value.details == {'candidates': expected, 'candidate_count': len(expected)}


def test_ga_dong_check_sees_total_count_when_has_next_page_is_empty() -> None:
    # hasNextPage 가 비어 와도 totalCount 가 받은 수보다 크면 다음 쪽이 남았다 (`_has_more`). 첫 쪽에 '○가' 동이 없는
    # '종로'(totalCount 90)에서 하위 지역 목록을 부르지 않으면 종로1가 하나만 남아 말없이 골랐다 (2026-11-16 리뷰)
    from jibsa.providers.naver.service.region import _check_ga_dongs

    requests: list[httpx.Request] = []
    autocomplete = _ok({'hasNextPage': None, 'totalCount': 90, 'list': [
        _legal_division('1111000000', '서울시 종로구'), _legal_division('1111010100', '서울시 종로구 청운동'),
    ]})
    sub_regions = _ok([
        {'legalDivisionNumber': code, 'legalDivisionName': name, 'legalDivisionLevelType': 'EUP'}
        for code, name in [('1111016400', '종로1가'), ('1111016500', '종로2가')]
    ])
    overrides = {'/search/autocomplete/legalDivisions': autocomplete, '/legalDivision/subInfoList': sub_regions}
    with make_path_client(requests, overrides) as client:
        with pytest.raises(JibsaError) as exc:
            _check_ga_dongs(client, '종로', '종로', '1111016400', '서울시 종로구 종로1가')
    assert exc.value.code == 'REGION_AMBIGUOUS'
    assert exc.value.details['candidates'] == ['서울특별시 종로구 종로1가', '서울특별시 종로구 종로2가']


def test_ga_dong_check_stops_on_single_dong_when_next_page_remains() -> None:
    # 하위 지역 목록은 찾은 동의 시·구만 덮는다. 자동완성 다음 쪽이 남았는데 '○가' 동이 한 곳만 모이면 다음 쪽에 다른
    # 시·구의 '○가' 동이 있을 수 있어 고르지 않는다 (2026-11-17 리뷰. 실제로 이런 앞 이름은 아직 찾지 못했다)
    from jibsa.providers.naver.service.region import _check_ga_dongs

    requests: list[httpx.Request] = []
    autocomplete = _ok({'hasNextPage': True, 'totalCount': 7, 'list': [
        _legal_division('1114000000', '서울시 중구'), _legal_division('1114010100', '서울시 중구 무교동'),
    ]})
    sub_regions = _ok([
        {'legalDivisionNumber': code, 'legalDivisionName': name, 'legalDivisionLevelType': 'EUP'}
        for code, name in [('1114010100', '무교동'), ('1114017500', '가나로1가')]
    ])
    overrides = {'/search/autocomplete/legalDivisions': autocomplete, '/legalDivision/subInfoList': sub_regions}
    with make_path_client(requests, overrides) as client:
        with pytest.raises(JibsaError) as exc:
            _check_ga_dongs(client, '가나로', '가나로', '1114017500', '서울시 중구 가나로1가')
    assert exc.value.code == 'REGION_AMBIGUOUS'
    assert exc.value.details == {'candidates': ['서울특별시 중구 가나로1가'], 'candidate_count': None}


def _legal_division(code: str, name: str, *, coordinates: bool = True) -> dict:
    return {
        'legalDivisionNumber': code, 'legalDivisionName': name, 'legalDivisionLevelType': 'EUP',
        'coordinates': {'xCoordinate': 127.05, 'yCoordinate': 37.54} if coordinates else None,
    }


def _address_list(full_addresses: list[str], bcode: str = '') -> dict:
    return _ok({'type': 'jibun-address', 'jibunAddress': {'totalCount': len(full_addresses), 'list': [
        {'fullAddress': address, 'itemLevel': 8, 'x': 127.05, 'y': 37.54, 'addressElements': {'bcode': bcode}}
        for address in full_addresses
    ]}})


@pytest.mark.parametrize(
    'dongs,expected',
    [
        # 좌표 없는 후보도 센다. 먼저 빼면 웹에는 후보가 둘인데 남은 하나를 '후보가 하나뿐' 으로 골랐다
        (
            [
                _legal_division('1100010100', '서울시 가구 가나동', coordinates=False),
                _legal_division('1100010200', '서울시 가구 가다동'),
            ],
            'REGION_AMBIGUOUS',
        ),
        # 고른 동에 좌표가 없으면 다른 후보로 바꾸지 않고 멈춘다
        ([_legal_division('1100010300', '서울시 가구 가동', coordinates=False)], 'REGION_NOT_FOUND'),
        # 이름이 맞는 곳이 끝말만 다르면(가동·가면) 첫 끝말 하나를 고르지 않는다 (2026-11-16 리뷰: '신평' 신평동·신평면)
        (
            [_legal_division('1100010300', '서울시 가구 가동'), _legal_division('4400025000', '충남 가군 가면')],
            'REGION_AMBIGUOUS',
        ),
    ],
)
def test_legal_division_counts_candidates_without_coordinates(dongs: list[dict], expected: str) -> None:
    requests: list[httpx.Request] = []
    autocomplete = _ok({'hasNextPage': False, 'totalCount': len(dongs), 'list': dongs})
    overrides = {'/maps-search/address': _address_list([]), '/search/autocomplete/legalDivisions': autocomplete}
    with make_path_client(requests, overrides) as client:
        with pytest.raises(JibsaError) as exc:
            resolve_search_region(client, '가')
    assert exc.value.code == expected


@pytest.mark.parametrize(
    'same_name,bcode,expected',
    [
        # 이름 전체('신흥동')로 물으니 같은 이름 동이 여럿이면 그 후보로 멈춘다
        (['대전광역시 동구 신흥동', '경기도 성남시 수정구 신흥동'], '', 'REGION_AMBIGUOUS'),
        # 한 곳뿐이고 그곳이 고른 동이면 그 동이다
        (['대전광역시 동구 신흥동'], '3011010600', '3011010600'),
        # 한 곳뿐이어도 고른 동과 다른 곳이거나 bcode 가 비었으면 같은 곳인지 몰라 고르지 않는다 (2026-11-16 리뷰. 주소 검색은
        # 자동완성에 없는 곳도 bcode 를 비워 섞어 준다)
        (['경기도 부천시 오정구 신흥동'], '', 'REGION_AMBIGUOUS'),
        (['경기도 안성시 신흥동'], '4155011200', 'REGION_AMBIGUOUS'),
        # 주소 검색이 못 찾아 하나뿐인지 확인할 수 없으면 고르지 않는다 (2026-11-16 결정)
        ([], '', 'REGION_AMBIGUOUS'),
    ],
)
def test_named_dong_with_next_page_is_checked_by_full_name(same_name: list[str], bcode: str, expected: str) -> None:
    # 이름이 맞는 동이 첫 쪽(5곳)에 하나뿐이어도 다음 쪽이 남았으면 뒤쪽에 같은 이름 동이 더 있을 수 있다
    autocomplete = _ok({'hasNextPage': True, 'totalCount': 12, 'list': [
        _legal_division('2817010100', '인천시 중구 신흥동1가'),
        _legal_division('2817010200', '인천시 중구 신흥동2가'),
        _legal_division('3011010600', '대전시 동구 신흥동'),
    ]})

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix('/front-api/v1')
        if path == '/search/autocomplete/legalDivisions':
            return httpx.Response(200, json=autocomplete)
        # 주소 검색은 끝말 없는 '신흥' 을 못 찾고 이름 전체 '신흥동' 에만 답한다
        return httpx.Response(200, json=_address_list(same_name if request.url.params.get('query') == '신흥동' else [], bcode))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        if expected.startswith('REGION_'):
            with pytest.raises(JibsaError) as exc:
                resolve_search_region(client, '신흥')
            assert exc.value.code == expected
        else:
            region, kind, _ = resolve_search_region(client, '신흥')
            assert (region.legal_division_code, kind) == (expected, '동')
