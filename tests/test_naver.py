import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from jibsa.cli.app import run
from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    months_ago,
    years_ago,
)
from jibsa.providers.naver.api.client import (
    NaverClient,
    should_retry_naver,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverComplexArticlePriceModel,
    NaverDuplicatedArticleInfoModel,
    NaverFacilityInfoModel,
    NaverResponseModel,
)
from jibsa.providers.naver.api.models.response.listing.detail import (
    NaverDevelopmentArticleModel,
)
from jibsa.providers.naver.api.models.response.search.common import (
    NaverArticleClusteredArticlesV1ResponseModel,
)
from jibsa.providers.naver.service.common.listing import (
    article_info_to_listing,
    group_fields,
)
from jibsa.providers.naver.service.common.models import (
    NaverTradeConditions,
    PageScan,
)
from jibsa.providers.naver.service.common.paging import (
    pagination_notes,
    scan_pages,
)
from jibsa.providers.naver.service.common.price import (
    rent_asking_range,
)
from jibsa.providers.naver.service.common.response import (
    result_or_empty,
    result_or_none,
)
from jibsa.providers.naver.service.listing.complex import list_complex_articles
from jibsa.providers.naver.service.listing.detail import get_listing
from jibsa.providers.naver.service.real_price.constants import (
    MAX_VILLA_PERIOD_PAGES,
)
from jibsa.providers.naver.service.real_price.real_price import get_real_prices
from jibsa.providers.naver.service.region.constants import (
    WIDE_REGION_NOTE_MARK,
)
from jibsa.providers.naver.service.region.resolve import (
    resolve_complex_number,
    resolve_redevelopment_number,
)
from jibsa.providers.naver.service.region.search import (
    legal_division_code_at,
    resolve_search_region,
)
from jibsa.providers.naver.service.school.school import list_school_complexes
from jibsa.providers.naver.service.search.constants import (
    COMPLEX_FILTER_NOTE,
    ENTRANCE_FILTER_NOTE,
    ENTRANCE_WITH_COMPLEX_FILTER_NOTE,
    ONE_ROOM_SHAPE_NOTE,
)
from jibsa.providers.naver.service.search.listings import search_area
from jibsa.providers.naver.service.search.models import NaverListingConditions
from jibsa.providers.naver.service.trend.trend import get_district_trend

from typing import Any


FIXTURES = Path(__file__).parent / 'fixtures' / 'naver'
ROUTES = {
    '/front-api/v1/complex': 'complex_v1',
    '/front-api/v1/complex/pyeong': 'complex_pyeong_v1',
    '/front-api/v1/complex/v2/pyeong/realPrice': 'complex_pyeong_real_price_v2',
    '/front-api/v1/legalDivision/searchByCoordinate': 'legal_division_search_by_coordinate_v1',
    '/front-api/v1/legalDivision/infoList': 'legal_division_info_list_v1',
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
    '/front-api/v1/development/article': 'development_article_v1',
}
# 픽스처 파일 없이 코드로 둔 응답. 근처 개발 예정은 두 목록이 모두 빈 매물이 많다 (원룸, 2026-11-18 실측)
INLINE_RESPONSES = {
    'development_article_v1': {'isSuccess': True, 'detailCode': 'success', 'result': {'railList': [], 'jiguList': []}},
}


def load(name: str) -> dict:
    if name in INLINE_RESPONSES:
        return INLINE_RESPONSES[name]
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
    from jibsa.providers.naver.api.models.response.common import NaverPyeongModel
    from jibsa.providers.naver.service.complex.complex import _pyeong

    def pyeong(supply: float, contract: float) -> NaverPyeongModel:
        return NaverPyeongModel.model_validate(
            {'number': 1, 'name': '30B', 'exclusiveArea': 20.89, 'supplyArea': supply, 'contractArea': contract}
        )

    copied = _pyeong(pyeong(30.59, 30.59), is_officetel=True)
    assert (copied.supply_area_m2, copied.contract_area_m2) == (None, 30.59)
    assert _pyeong(pyeong(40.66, 57.51), is_officetel=True).supply_area_m2 == 40.66
    assert _pyeong(pyeong(30.59, 30.59)).supply_area_m2 == 30.59


def test_real_prices_in_manwon() -> None:
    requests: list[httpx.Request] = []
    with make_client(requests) as client:
        result = get_real_prices(client, 100001, 1, pages=3)
    first = result.trades[0]
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
    from jibsa.providers.naver.api.models.response.listing.detail import (
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
    sale = real['trades'][0]
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
    assert not {'complex_id', 'complex_name', 'building_dong', 'pyeong_id'} & set(dumped)

    # 단지 매물은 그대로 낸다
    with make_client() as client:
        dumped = get_listing(client, '1000000001').model_dump(mode='json')
    assert (dumped['complex_id'], dumped['complex_name'], dumped['building_dong'], dumped['pyeong_id']) == (100001, '테스트아파트', '101', 1)


def test_loan_distinguishes_none_from_unknown() -> None:
    from jibsa.providers.naver.api.models.response.listing.detail import (
        NaverPriceInfoModel,
    )
    from jibsa.providers.naver.service.listing.detail import _loan_manwon

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
    # 세대수·주차는 단지가 없는 빌라를, 현관 구조·원룸 구조는 그 값을 입력하지 않은 매물을 빼므로 모두 알린다
    assert COMPLEX_FILTER_NOTE in result.notes
    assert ENTRANCE_WITH_COMPLEX_FILTER_NOTE in result.notes
    assert ENTRANCE_FILTER_NOTE not in result.notes
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
        if request.url.path.endswith('/oldMaintenanceFee'):
            # 관리비 칸을 못 만들면 옛 형식 관리비를 묻는다. 금액이 없으면 웹처럼 빈 객체다 (토지 2663300403, 2026-11-24)
            return httpx.Response(200, json={'isSuccess': True, 'result': {}})
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
    from jibsa.providers.naver.api.models.response.listing.detail import (
        NaverMovingInInfoModel,
    )
    from jibsa.providers.naver.service.listing.detail import _move_in_label

    def label(code: str, date: str | None, negotiation: bool = False, notes: list[str] | None = None) -> str | None:
        return _move_in_label(NaverMovingInInfoModel.model_validate(
            {'movingInType': code, 'movingInDate': date, 'movingInNegotiation': negotiation},
        ), [] if notes is None else notes)

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
    # 못 읽는 날짜는 입주일로 내지 않고 [참고] 안내를 붙인다. 협의 가능이면 '협의 가능' 만 낸다 ('0000-00 초순' 을 내지 않는다, 2026-11-17 리뷰)
    notes: list[str] = []
    assert label('MID', 'abc', True, notes) == '협의 가능'
    assert len(notes) == 1 and "(중순입주, 날짜 'abc')" in notes[0]
    # 날짜 지정도 연월만 오면 연월로 낸다 (안내 없음)
    notes = []
    assert label('MV004', '202612', True, notes) == '2026-12 (협의 가능)'
    assert notes == []
    notes = []
    assert label('EARLY', '0000-00-00', notes=notes) is None
    assert len(notes) == 1
    notes = []
    assert label('MV002', '2026-02-30', notes=notes) is None
    assert len(notes) == 1


def test_detail_manage_cost_itemized_sums_every_item_and_includes_only_fixed() -> None:
    # 웹은 항목별형의 합계에 정액·실비를 가리지 않고 모든 항목 금액을 더한다. 포함 항목은 정액 항목만 남긴다
    from jibsa.providers.naver.api.models.response.listing.detail import (
        NaverArticleMaintenanceFeeModel,
    )
    from jibsa.providers.naver.service.listing.cost import manage_cost as _manage_cost

    fee = NaverArticleMaintenanceFeeModel.model_validate({'typeCode': '01', 'fixDetailList': [
        {'type': '01', 'unitType': '01', 'amount': 100000},
        {'type': '11', 'unitType': '02', 'amount': 30000},
        {'type': '12', 'unitType': '02'},
    ]})
    manage_cost, includes = _manage_cost(fee, [])
    assert manage_cost == 13.0
    assert includes is not None and len(includes) == 1


@pytest.mark.parametrize(
    ('registration', 'expected'),
    [
        # 매물이 0대·불가인데 대장에 8대가 있으면 웹이 '주차 8대' 를 그린다
        ({'parkingInfo': {'totalParkingCount': 8, 'parkingCountPerHousehold': 0.5}}, '불가 (총 8대, 세대당 0.5대)'),
        ({'parkingInfo': {'totalParkingCount': 0, 'parkingCountPerHousehold': 0}}, '불가 (총 0대)'),
        # 대장에 주차 값이 없으면 웹도 '주차 N대' 칸을 그리지 않아 가능 여부만 낸다
        ({'coordinates': None}, '불가'),
    ],
)
def test_detail_building_registration_parking_fills_in_zero_listing_count(registration: dict, expected: str) -> None:
    key = _ok({
        'key': {'pnu': '1100000000100010000'}, 'type': {'realEstateType': 'C01', 'tradeType': 'B2'},
        'address': {'legalDivisionNumber': '1162010200', 'jibun': '255-134'},
    })
    basic = load('article_basic_info_v1')
    basic['result']['detailInfo']['facilityInfo'].update({'totalParkingCount': 0, 'isParkingPossible': False})
    basic['result'].pop('communalComplexInfo', None)
    requests: list[httpx.Request] = []
    overrides = {'/article/key': key, '/article/basicInfo': basic, '/complex/buildingRegistration': _ok(registration)}
    with make_path_client(requests, overrides) as client:
        detail = get_listing(client, '1000000001')
    assert detail.parking == expected
    registry_requests = [request for request in requests if request.url.path.endswith('/complex/buildingRegistration')]
    assert len(registry_requests) == 1
    assert registry_requests[0].url.params['pnu'] == '1100000000100010000'
    assert registry_requests[0].url.params['realEstateType'] == 'C01'


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
    assert (detail.nearby_stations, detail.bus_routes, detail.schools) == (None, None, None)
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
    dumped = result.trades[0].model_dump()
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
    from jibsa.providers.naver.service.listing.constants import (
        MAX_COMPLEX_ARTICLE_PAGE_REQUESTS,
    )

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
    # 되풀이된 쪽은 세지 않고, 더 있다면서 새 매물을 주지 않아 멈췄다고 알린다 ('전부입니다' 가 아니다)
    assert any(note.startswith('[일부]') and '새 매물을 주지 않아' in note for note in result.notes)
    assert not any('전부입니다' in note for note in result.notes)
    # 단지 매물은 이어 받지 않아 has_more 가 받지 않은 매물이 남았다는 뜻이다. [일부] 안내와 같게 true 다
    assert result.has_more is True


# --- 매물 상세 중개보수·세금·시설 글자 ------------------------------------------


def test_monthly_rent_detail_has_agent_fee_but_no_taxes() -> None:
    # 중개보수는 월세 매물에도 있고(웹도 '최대 28만원' 을 보여 준다), 세금은 매매만 조회한다
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/key'):
            body['result']['type']['tradeType'] = 'B2'
        if request.url.path.endswith('/basicInfo'):
            body['result']['priceInfo'] = {'tradeType': 'B2', 'warrantyAmount': 10_000_000, 'rentAmount': 830_000, 'loan': 0}
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        dumped = get_listing(client, '1000000002').model_dump(mode='json')
    assert dumped['broker_fee_manwon'] == 1050
    assert not {'acquisition_tax_manwon', 'property_tax_manwon', 'comprehensive_real_estate_tax_manwon'} & set(dumped)
    paths = _paths(requests)
    assert '/article/agentFee' in paths and '/article/tax' not in paths


@pytest.mark.parametrize(('real_estate_type', 'absent', 'present', 'taxes_requested'), [
    # 토지는 웹에 방·층·난방·시설 칸이 없고 세금은 취득세만 그린다
    ('E03', {'room_count', 'floor', 'floor_number', 'heating', 'options', 'property_tax_manwon'}, {'acquisition_tax_manwon'}, True),
    ('A01', set(), {'room_count', 'floor', 'heating', 'options', 'property_tax_manwon', 'acquisition_tax_manwon'}, True),
    # 원룸은 매매여도 세금 칸이 없어 세금을 조회하지 않는다
    ('C01', {'acquisition_tax_manwon', 'property_tax_manwon', 'comprehensive_real_estate_tax_manwon'}, {'room_count'}, False),
])
def test_detail_drops_fields_the_web_does_not_draw_by_type(
    real_estate_type: str, absent: set[str], present: set[str], taxes_requested: bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/key'):
            body['result']['type']['realEstateType'] = real_estate_type
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        dumped = get_listing(client, '1000000001').model_dump(mode='json')
    assert not absent & set(dumped)
    assert present <= set(dumped)
    assert ('/article/tax' in _paths(requests)) is taxes_requested


def test_unknown_facility_code_is_not_a_known_label() -> None:
    # 표에 없는 시설 코드는 코드 글자도 null 도 아니라 못 읽었다는 글자로 낸다. 화면 글자(인덕션레인지)는 그대로 낸다
    def handler(request: httpx.Request) -> httpx.Response:
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/basicInfo'):
            body['result']['detailInfo']['facilityInfo']['life'] = ['INDUCTION_RANGE', 'XYZ01']
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        detail = get_listing(client, '1000000001')
    assert detail.options == ['인덕션레인지', '알 수 없는 시설 (XYZ01)']


def test_unknown_direct_trade_skips_agent_fee_and_keeps_keys_null() -> None:
    # 상세 정보(articleDetailInfo)를 못 읽어 직거래인지 모르면 agentFee 를 부르지 않고 둘 다 모름(null)으로 낸다
    # (agentFee 는 직거래에도 금액을 주므로, 모르는 채로 내면 웹이 그리지 않는 값이 나갈 수 있다)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = load(ROUTES[request.url.path])
        if request.url.path.endswith('/basicInfo'):
            del body['result']['detailInfo']['articleDetailInfo']
        return httpx.Response(200, json=body)

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    with client:
        dumped = get_listing(client, '1000000001').model_dump(mode='json')
    assert '/article/agentFee' not in _paths(requests)
    assert dumped['broker_fee_manwon'] is None
    assert dumped['broker_fee_individual_check_required'] is None


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
    assert detail.broker_fee_manwon == 1050
    assert detail.model_dump()['acquisition_tax_manwon'] is None


def test_detail_optional_lookup_failure_is_unknown() -> None:
    # 관리비·법정동·단지 조회가 HTTP 오류가 아닌 이유(응답 모양이 바뀜)로 실패해도 상세는 내보내고 그 값만 모름이다
    broken = ('/article/maintenanceFee', '/article/oldMaintenanceFee', '/legalDivision/infoList', '/complex')

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


@pytest.mark.parametrize(
    ('real_estate_type', 'detail_info', 'li', 'expected'),
    [
        # 웹 위치 칸 규칙: 지번 노출 표의 유형은 isJibunAddressExposed 가 없으면 숨기고 true 면 보인다
        ('D02', {}, None, '서울특별시 강남구 개포동'),
        ('D02', {'isJibunAddressExposed': True}, None, '서울특별시 강남구 개포동 100-1'),
        ('C02', {}, None, '서울특별시 강남구 개포동 100-1'),
        # 단독(C0301)은 표에 없는 유형이어도 노출 값을 따른다
        ('C03', {'buildingType': 'C0301'}, None, '서울특별시 강남구 개포동'),
        # 리는 지번 앞에 붙는다
        ('C02', {}, '다문리', '서울특별시 강남구 개포동 다문리 100-1'),
    ],
)
def test_detail_address_follows_web_jibun_rule(real_estate_type: str, detail_info: dict, li: str | None, expected: str) -> None:
    key = load('article_key_v1')
    key['result']['type']['realEstateType'] = real_estate_type
    if li:
        key['result']['address']['li'] = li
    basic = load('article_basic_info_v1')
    basic['result']['detailInfo']['articleDetailInfo'].update(detail_info)
    with make_path_client([], {'/article/key': key, '/article/basicInfo': basic}) as client:
        assert get_listing(client, '1000000001').address == expected


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
    assert (detail.nearby_stations, detail.bus_routes) == (None, None)
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
    # 되풀이된 쪽은 세지 않고, 더 있다면서 새 매물을 주지 않아 멈췄다고 알린다 ('전부입니다' 가 아니다)
    assert any(note.startswith('[일부]') and '새 매물을 주지 않아' in note for note in result.notes)
    assert not any('전부입니다' in note for note in result.notes)


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
    from jibsa.providers.naver.service.search.constants import (
        MAX_LEGAL_DIVISION_PAGE_REQUESTS,
    )

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
    assert trend.asking_price_per_pyeong is None and trend.listing_count_trend is not None
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


def _redevelopment_item(number: int, name: str, dong: str) -> dict:
    return {
        'redevelopmentAreaNumber': number, 'name': name,
        'legalDivisionName': f'서울시 용산구 {dong}', 'legalDivisionNumber': '1117013000',
    }


@pytest.mark.parametrize(
    'items,expected',
    [
        # 이름이 정확히 같은 구역이 하나면 그 번호다 (이름이 비슷한 구역이 더 있어도, 후보를 다 받았을 때)
        ([_redevelopment_item(1, '한남3구역', '한남동'), _redevelopment_item(2, '한남3구역 일부', '보광동')], 1),
        # 같은 이름이 법정동마다 번호를 달리해 여럿 오면 하나를 고르지 않고 후보를 알린다 (한남제3재정비촉진구역
        # 10017678 한남동·1000208 보광동, 2026-11-18 실측)
        ([_redevelopment_item(10017678, '한남3구역', '한남동'), _redevelopment_item(1000208, '한남3구역', '보광동')], None),
    ],
)
def test_redevelopment_name_picks_only_unique_exact_match(items: list[dict], expected: int | None) -> None:
    body = _ok({'hasNextPage': False, 'totalCount': len(items), 'list': items})
    with make_path_client([], {'/search/autocomplete/redevelopmentAreas': body}) as client:
        if expected is not None:
            assert resolve_redevelopment_number(client, '한남3구역') == (expected, [])
        else:
            with pytest.raises(JibsaError) as exc:
                resolve_redevelopment_number(client, '한남3구역')
            assert exc.value.code == 'REGION_AMBIGUOUS'
            assert exc.value.details['candidate_count'] == 2
            assert exc.value.details['candidates'][0] == '한남3구역 (서울특별시 용산구 한남동, 구역 번호 10017678)'
            assert '10017678' in (exc.value.hint or '')


@pytest.mark.parametrize('items', [[], None])
def test_redevelopment_name_without_candidates_is_not_found(items: list | None) -> None:
    # 후보 목록이 비어도 null 이어도 후보 없음이다. 단지 이름(`resolve_complex_number`)과 같은 NOT_FOUND 로 낸다
    body = _ok({'hasNextPage': False, 'totalCount': 0, 'list': items})
    with make_path_client([], {'/search/autocomplete/redevelopmentAreas': body}) as client, pytest.raises(JibsaError) as exc:
        resolve_redevelopment_number(client, '없는구역')
    assert exc.value.code == 'NOT_FOUND'
    assert exc.value.message == "'없는구역' 에 해당하는 네이버 재개발 구역을 찾지 못했습니다"


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
    # hasNextPage 가 비어 와도 totalCount 가 받은 수보다 크면 다음 쪽이 남았다 (`has_more`). 첫 쪽에 '○가' 동이 없는
    # '종로'(totalCount 90)에서 하위 지역 목록을 부르지 않으면 종로1가 하나만 남아 말없이 골랐다 (2026-11-16 리뷰)
    from jibsa.providers.naver.service.region.search import _check_ga_dongs

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
    from jibsa.providers.naver.service.region.search import _check_ga_dongs

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


@pytest.mark.parametrize(
    'city,code,sub_regions,has_district',
    [
        # 구 있는 시: 시·도 아래 목록에 시 코드와 앞 네 자리가 같은 구가 있다 (시 코드 + GUN 은 오류 없이 0건이라 경계로 찾지 않는다)
        (
            '성남시', '4113000000',
            [('4113100000', '경기도 성남시 수정구'), ('4113500000', '경기도 성남시 분당구'), ('4131000000', '경기도 구리시')],
            True,
        ),
        # 구 없는 시: 같은 네 자리의 다른 곳이 없어 시·군·구 경계다
        ('구리시', '4131000000', [('4113500000', '경기도 성남시 분당구'), ('4131000000', '경기도 구리시')], False),
        # 시 자신도 그 시의 구도 없는 목록(빈 목록 포함)은 구가 있는지 모르는 것이라 경계로 찾지 않는다
        ('구리시', '4131000000', [], None),
    ],
)
def test_city_name_is_boundary_only_when_it_has_no_district(
    city: str, code: str, sub_regions: list[tuple[str, str]], has_district: bool | None,
) -> None:
    from jibsa.cli.naver import _area_location

    sub_info = _ok([
        {'legalDivisionNumber': number, 'legalDivisionName': name, 'legalDivisionLevelType': 'GUN'}
        for number, name in sub_regions
    ])
    requests: list[httpx.Request] = []
    overrides = {'/maps-search/address': _address_list([f'경기도 {city}'], code), '/legalDivision/subInfoList': sub_info}
    with make_path_client(requests, overrides) as client:
        region, notes, boundary_code, scope = _area_location(client, city, None, None, None)
    assert _paths(requests).count('/legalDivision/subInfoList') == 1
    if has_district:
        assert (boundary_code, scope) == (None, {'radius_km': 1.0})
        # 구 이름은 시 이름을 붙여 줘야 그대로 찾을 수 있다 ('남구' 만으로는 REGION_AMBIGUOUS)
        assert any('구가 있는 시' in text and '(성남시 수정구, 성남시 분당구)' in text for text in notes)
        assert not any(WIDE_REGION_NOTE_MARK in text for text in notes)
    elif has_district is None:
        assert (boundary_code, scope) == (None, {'radius_km': 1.0})
        # 이유가 다른 넓은 지역 안내는 [실패] 안내로 대신한다
        assert sum('[실패]' in text for text in notes) == 1
        assert not any(WIDE_REGION_NOTE_MARK in text for text in notes)
    else:
        assert (boundary_code, scope) == (code, {'boundary': city})


@pytest.mark.parametrize(
    'sub_info,expected',
    [
        # 시·군·구가 하나뿐인 시·도(세종)는 그 시·군·구(GUN) 경계 전체다
        (_ok([{'legalDivisionNumber': '3611000000', 'legalDivisionName': '세종시', 'legalDivisionLevelType': 'GUN'}]), 'boundary'),
        # 시·군·구가 여럿이면 지금처럼 시·도 중심 반경이고 넓은 지역 안내가 그대로다
        (_ok([
            {'legalDivisionNumber': '4111000000', 'legalDivisionName': '경기도 수원시', 'legalDivisionLevelType': 'GUN'},
            {'legalDivisionNumber': '4113000000', 'legalDivisionName': '경기도 성남시', 'legalDivisionLevelType': 'GUN'},
        ]), 'wide'),
        # 조회가 실패하면 반경으로 찾고 넓은 지역 안내 대신 [실패] 로 알린다
        ({'isSuccess': False, 'detailCode': 'INTERNAL_ERROR'}, 'failed'),
    ],
)
def test_province_name_is_boundary_only_when_it_has_a_single_district(sub_info: dict, expected: str) -> None:
    from jibsa.cli.naver import _area_location

    requests: list[httpx.Request] = []
    overrides = {'/maps-search/address': _address_list(['세종특별자치시'], '3600000000'), '/legalDivision/subInfoList': sub_info}
    with make_path_client(requests, overrides) as client:
        region, notes, boundary_code, scope = _area_location(client, '세종시', None, None, None)
        radius_code = _area_location(client, '세종시', None, None, 1.0)[2]
    assert radius_code is None  # --radius 를 주면 시·군·구를 묻지 않고 반경이다
    assert _paths(requests).count('/legalDivision/subInfoList') == 1
    if expected == 'boundary':
        assert (boundary_code, scope) == ('3611000000', {'boundary': region.name})
        assert not any(WIDE_REGION_NOTE_MARK in text for text in notes)
    elif expected == 'wide':
        assert (boundary_code, scope) == (None, {'radius_km': 1.0})
        assert any(WIDE_REGION_NOTE_MARK in text for text in notes)
    else:
        assert (boundary_code, scope) == (None, {'radius_km': 1.0})
        assert sum('[실패]' in text for text in notes) == 1
        assert not any(WIDE_REGION_NOTE_MARK in text for text in notes)


# --- 학교 배정 단지 ----------------------------------------------------------


def _school_complex_item(number: int, all_assigned: bool = False, groups: list[list[str]] | None = None) -> dict:
    return {
        'complexInfo': {
            'complexNumber': number, 'name': f'단지{number}', 'type': 'A01', 'buildingCount': 10,
            'totalHouseholdNumber': 500, 'useApprovalDate': '20100706',
        },
        'articleCountInfoDto': {'dealCount': 1, 'leaseDepositCount': 0, 'leaseMonthlyCount': 0, 'leaseShortTerm': 0},
        'articlePriceInfoDto': {},
        'isAllBuildingAssigned': all_assigned,
        'convertedBuildingNameGroups': groups or [],
    }


def _school_complex_client(pages: list[dict], requests: list[httpx.Request]) -> NaverClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_ok(pages[int(request.url.params['page'])]))

    client = NaverClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_school_complexes_take_total_from_the_first_page_only() -> None:
    # 끝 쪽(둘째 쪽)은 totalCount 가 0 으로 온다 (2026-11-18 실측). 총수를 마지막 쪽 것으로 덮지 않는다
    pages = [
        {'totalCount': 3, 'hasNextPage': True, 'list': [_school_complex_item(1), _school_complex_item(2)]},
        {'totalCount': 0, 'hasNextPage': False, 'list': [_school_complex_item(3)]},
    ]
    requests: list[httpx.Request] = []
    with _school_complex_client(pages, requests) as client:
        result = list_school_complexes(client, 'B100000898', sort='세대수순', limit=20)
    assert (result.total, result.returned, result.has_more) == (3, 3, False)
    assert [request.url.params['page'] for request in requests] == ['0', '1']
    assert requests[0].url.params['sortType'] == 'HOUSEHOLD_COUNT'


@pytest.mark.parametrize(
    'all_assigned,groups,expected',
    [
        (True, [], ['전체 동']),
        (False, [['101', '102', '103'], ['105']], ['101동~103동', '105동']),
        # 전체 배정이 아닌데 동 묶음이 비면 어느 동인지 모른다 (배정 동 없음 [] 이 아니다)
        (False, [], None),
    ],
)
def test_school_complex_assigned_dongs(all_assigned: bool, groups: list[list[str]], expected: list[str] | None) -> None:
    pages = [{'totalCount': 1, 'hasNextPage': False, 'list': [_school_complex_item(1, all_assigned, groups)]}]
    with _school_complex_client(pages, []) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=20)
    assert result.complexes[0].assigned_dongs == expected


def test_school_complexes_null_cells_are_unknown_not_a_parse_error() -> None:
    # 총수·다음 쪽·동 묶음·목록이 null 로 와도 명령이 깨지지 않고 모름(null)으로 낸다. 단지 정보가 없는 항목은 건너뛰고 [제외] 로 알린다
    item = _school_complex_item(1)
    item['convertedBuildingNameGroups'] = None
    pages = [{'totalCount': None, 'hasNextPage': None, 'list': [item, {'isAllBuildingAssigned': True}]}]
    with _school_complex_client(pages, []) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=20)
    assert (result.total, result.returned, result.has_more) == (None, 1, None)
    assert result.complexes[0].assigned_dongs is None
    assert [text for text in result.notes if text.startswith('[제외]')] == ['[제외] 네이버가 단지 정보를 주지 않은 1곳은 뺐습니다']
    # 목록 자체가 null 이면 그 쪽은 0곳이다
    with _school_complex_client([{'totalCount': None, 'hasNextPage': None, 'list': None}], []) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=20)
    assert (result.total, result.returned, result.has_more, result.notes) == (None, 0, None, [])


def test_school_complexes_empty_page_with_next_page_is_reported_without_asking_for_more_limit() -> None:
    # 다음 쪽이 있다면서 빈 쪽을 주면 거기서 멈춘다. --limit 을 늘려도 같은 빈 쪽이라 늘리라고 하지 않는다
    pages = [
        {'totalCount': 30, 'hasNextPage': True, 'list': [_school_complex_item(1), _school_complex_item(2)]},
        {'totalCount': 0, 'hasNextPage': True, 'list': []},
    ]
    requests: list[httpx.Request] = []
    with _school_complex_client(pages, requests) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=20)
    assert (result.total, result.returned, result.has_more) == (30, 2, True)
    assert len(requests) == 2
    assert result.notes == ['[일부] 네이버가 더 있다면서 빈 쪽을 줘 2곳까지만 받았습니다']


def _school_complex_page(start: int, count: int, *, total: int, has_next: bool | None) -> dict:
    return {'totalCount': total, 'hasNextPage': has_next, 'list': [_school_complex_item(start + index) for index in range(count)]}


def test_school_complexes_null_next_page_uses_first_page_total() -> None:
    # 다음 쪽 여부가 null 이어도 첫 쪽 총수(35)가 받은 수(20)보다 크면 더 있는 것이다. 이어 받아 총수까지 채우면 더 없다
    pages = [_school_complex_page(0, 20, total=35, has_next=None), _school_complex_page(20, 15, total=0, has_next=None)]
    requests: list[httpx.Request] = []
    with _school_complex_client(pages, requests) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=40)
    assert (result.total, result.returned, result.has_more, len(requests)) == (35, 35, False, 2)
    # limit 에서 멈추면 더 있다고 알리고 --limit 을 늘리라고 한다 (늘리면 위처럼 이어 받는다)
    with _school_complex_client(pages, []) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=20)
    assert (result.returned, result.has_more) == (20, True)
    assert result.notes == ['[일부] 학교에 배정되는 단지가 35곳 있고, 그중 20곳만 보여 줍니다. 더 보려면 --limit 을 늘리세요']


@pytest.mark.parametrize('limit', [60, 100])
def test_school_complexes_request_cap_with_short_pages_does_not_ask_for_more_limit(limit: int) -> None:
    # 네이버가 쪽을 10곳씩 짧게 주면 요청 상한(5쪽)에서 50곳만 받는다. --limit 을 늘려도(최대값이면 '최대값은 100') 같은 곳에서 멈춘다
    pages = [_school_complex_page(page * 10, 10, total=200 if page == 0 else 0, has_next=True) for page in range(5)]
    requests: list[httpx.Request] = []
    with _school_complex_client(pages, requests) as client:
        result = list_school_complexes(client, 'B100000898', sort='거리순', limit=limit)
    assert (len(requests), result.returned, result.has_more) == (5, 50, True)
    assert result.notes == ['[일부] 네이버가 쪽을 짧게 줘 요청 상한(5쪽)까지 50곳만 받았습니다 (학교에 배정되는 단지는 200곳)']


# --- 평형 묶음 실거래 ------------------------------------------------------------


@pytest.mark.parametrize('groups', [[], None])
def test_real_price_group_without_groups_is_one_not_found(groups: list | None) -> None:
    # 없는 단지 번호(99999999)와 빌라 단지(673573)가 모두 isSuccess true·result [] 라 서버 응답으로 가를 수 없다 (2026-11-18). result null 도 같다
    requests: list[httpx.Request] = []
    with make_path_client(requests, {'/complex/pyeongGroups': _ok(groups)}) as client, pytest.raises(JibsaError) as exc:
        get_real_prices(client, 99999999, 1, group=True)
    assert exc.value.code == 'NOT_FOUND'
    assert '평형 묶음을 찾지 못했습니다' in exc.value.message
    assert exc.value.hint is not None and '(jibsa naver complex 99999999)' in exc.value.hint
    assert _paths(requests) == ['/complex/pyeongGroups']


def test_complex_pyeong_groups_null_result_is_empty_but_failure_is_unknown() -> None:
    from jibsa.providers.naver.service.complex.complex import _pyeong_groups

    # 성공인데 result 가 null 이면 real-price --group 과 같게 묶음 없음([])이고, 조회 실패(isSuccess false)만 모름(null)이다
    with make_path_client([], {'/complex/pyeongGroups': _ok(None)}) as client:
        assert _pyeong_groups(client, 100001, []) == []
    failure = {'isSuccess': False, 'detailCode': 'ERROR', 'result': {}}
    with make_path_client([], {'/complex/pyeongGroups': failure}) as client:
        notes: list[str] = []
        assert _pyeong_groups(client, 100001, notes) is None
    # 실패는 [실패] 안내로 알린다 (isSuccess false 는 거절이라 업데이트 안내가 붙는다)
    assert len(notes) == 1 and notes[0].startswith('[실패] ') and 'pyeong_groups' in notes[0]


def test_pyeong_group_with_null_pyeong_types_is_unknown_for_that_group_only() -> None:
    from jibsa.providers.naver.service.complex.complex import _pyeong_groups
    from jibsa.providers.naver.service.real_price.real_price import _find_pyeong_group

    groups = [
        {'representativePyeongName': '33평', 'representativePyeongNumber': 1, 'householdCount': 10, 'pyeongTypes': None},
        # 묶음 평형은 번호만 쓴다 (name 이 null 이어도 깨지지 않는다)
        {'representativePyeongName': '40평', 'representativePyeongNumber': 3, 'householdCount': 5, 'pyeongTypes': [{'number': 3}, {'number': 2, 'name': None}]},
    ]
    with make_path_client([], {'/complex/pyeongGroups': _ok(groups)}) as client:
        # complex: 그 묶음만 pyeong_ids 가 null(모름)이다
        assert [group.pyeong_ids for group in _pyeong_groups(client, 100001, []) or []] == [None, [2, 3]]
        # real-price --group: 번호를 모르는 묶음은 건너뛰고 번호가 든 묶음에서 짝을 찾는다
        group, request_numbers = _find_pyeong_group(client, 100001, 2)
        assert (group.name, group.pyeong_ids, request_numbers) == ('40평', [2, 3], [3, 2])
        with pytest.raises(JibsaError) as exc:
            _find_pyeong_group(client, 100001, 1)
    assert exc.value.code == 'NOT_FOUND'


def test_price_per_pyeong_null_region_list_keeps_the_price() -> None:
    from jibsa.providers.naver.service.complex.pyeong_details import _price_per_pyeong

    # 지역 목록이 null 이어도 평당가는 그대로 내고 지역·기준일만 모름(null)이다
    null_regions = _ok({'pricePerPyeong': 150000000, 'legalDivisionPricePerPyeongList': None})
    with make_path_client([], {'/complex/pyeongPrice/pyeongType': null_regions}) as client:
        trade = _price_per_pyeong(client, 100001, 1, 'A01', [])['sale']
    assert trade is not None
    assert (trade.price_per_pyeong_manwon, trade.base_date, trade.regions) == (15000, None, None)
    # 성공인데 result 가 null 이면 평당가를 주지 않은 것이라 키를 빼고(월세와 같다), 조회 실패만 null(모름)이다
    with make_path_client([], {'/complex/pyeongPrice/pyeongType': _ok(None)}) as client:
        assert _price_per_pyeong(client, 100001, 1, 'A01', []) == {}
    failure = {'isSuccess': False, 'detailCode': 'ERROR', 'result': {}}
    with make_path_client([], {'/complex/pyeongPrice/pyeongType': failure}) as client:
        assert _price_per_pyeong(client, 100001, 1, 'A01', []) == {'sale': None, 'jeonse': None}


# --- 빌라 단지 실거래 두 칸 (평당 실거래가·주변 실거래) ---------------------------------

VILLA_CENTER = {'xCoordinate': 127.0301, 'yCoordinate': 37.5001}


def _around_trade(date_: str | None, area: float, completion: str | None, floor: str | None, price: dict | None, renew: bool = False) -> dict:
    return {
        'contractDate': date_, 'exclusiveArea': area, 'completionYearMonth': completion, 'floor': floor,
        'isRenewRequestRight': renew, 'price': price,
    }


def _villa_overrides(*, coordinates: dict | None = VILLA_CENTER, **extra: dict) -> dict[str, dict]:
    """가상 빌라 단지 100002 가 실거래 두 칸까지 묻는 요청마다 가짜 응답을 준다. 아파트 목록·평형 목록은 비어 와 빌라로 정해진다."""
    deposit = {'dealPrice': 0, 'deposit': 250_000_000, 'monthlyRent': 0}
    around = {'aroundRealPriceList': [
        {
            'complexInfo': {'realEstateType': 'A06', 'coordinatesDto': VILLA_CENTER},
            'realPriceList': [
                _around_trade('2026-09-05', 40.5, '20120315', '2', deposit),
                _around_trade('2026-09-18', 30.2, '20120315', '4', deposit, renew=True),
            ],
        },
        # 단지 번호는 오지 않고 좌표만 온다. 다른 건물(약 350m 남쪽): 같은 계약일이면 준공연도가 큰 쪽이 앞이다
        {
            'complexInfo': {'realEstateType': 'A05', 'coordinatesDto': {'xCoordinate': 127.0307, 'yCoordinate': 37.4970}},
            'realPriceList': [_around_trade('2026-09-18', 30.2, '20170501', '3', deposit)],
        },
        # 건물 정보·층·금액·준공 연월이 비어 와도 깨지지 않고, 거리·같은 단지 여부는 모름이다
        {'complexInfo': None, 'realPriceList': [_around_trade('2020-01-01', 20.0, None, '-', None)]},
        {'complexInfo': {'realEstateType': None, 'coordinatesDto': {}}, 'realPriceList': None},
    ]}
    return {
        '/complex/v2/pyeong/realPrice': _ok({'list': [], 'hasNextPage': False}),
        '/complex/pyeongList': _ok([]),
        '/complex/villa/pyeongList': _ok([{'number': 4, 'name': '29A'}]),
        '/complex/villa/realPricePage': _ok({'totalCount': 0, 'hasNextPage': False, 'realPriceList': []}),
        '/complex/villa/realPricePyeongPrice': _ok([
            {'tradeDate': '2026-09-30', 'pyeongPrice': 18_500_000},
            {'tradeDate': None, 'pyeongPrice': None},
        ]),
        '/complex/villa': _ok({'name': '예시빌라', 'coordinates': coordinates}),
        '/complex/villa/realPriceAround': _ok(around),
        **extra,
    }


def test_villa_real_price_adds_per_pyeong_and_sorted_nearby_trades() -> None:
    requests: list[httpx.Request] = []
    with make_path_client(requests, _villa_overrides()) as client:
        data = get_real_prices(client, 100002, 4, trade_type='전세', today=date(2026, 11, 19)).model_dump(mode='json')
    # 평당 실거래가는 서버 순서 그대로다 (모르는 칸은 null)
    assert data['price_per_pyeong_trades'] == [
        {'trade_date': '2026-09-30', 'price_per_pyeong_manwon': 1850}, {'trade_date': None, 'price_per_pyeong_manwon': None},
    ]
    nearby = data['nearby_trades']
    # 웹 작은 지도 크기 (위도 37.5 에서 위도 폭 약 0.001702°·경도 폭 0.0041628°)
    assert (nearby['height_km'], nearby['width_km']) == (0.188, 0.365)
    # 계약일 내림차순 → 준공연도 내림차순 → 전용면적 내림차순
    assert [(trade['trade_date'], trade['completed_year']) for trade in nearby['trades']] == [
        ('2026-09-18', 2017), ('2026-09-18', 2012), ('2026-09-05', 2012), ('2020-01-01', None),
    ]
    other, same, _, unknown = nearby['trades']
    assert (same['same_complex'], same['distance_m'], same['renewal_right']) == (True, 0, True)
    assert other['same_complex'] is False and 300 < other['distance_m'] < 400 and other['renewal_right'] is None
    # 전세 거래에 없는 가격 키는 빼고, 층이 '-' 이거나 금액이 비면 null 이다
    assert other['deposit_manwon'] == 25000 and not {'price_manwon', 'rent_manwon', 'trade_type'} & set(other)
    assert (unknown['floor'], unknown['deposit_manwon'], unknown['distance_m'], unknown['same_complex']) == (None, None, None, None)
    # 요청: 아파트 실거래·평형 둘(아파트·빌라)·빌라 실거래 + 평당 1 + 좌표 1 + 주변 1. 주변은 웹처럼 줌 16 과 평형·거래 유형을 보낸다
    assert _paths(requests)[-3:] == ['/complex/villa/realPricePyeongPrice', '/complex/villa', '/complex/villa/realPriceAround']
    assert len(requests) == 7
    assert requests[-3].url.params['startDate'] == '2021-11-19'
    assert (requests[-1].url.params['zoom'], requests[-1].url.params['pyeongTypeNumber'], requests[-1].url.params['tradeType']) == ('16', '4', 'B1')


def test_villa_period_keeps_unknown_trade_date_and_does_not_stop_on_it() -> None:
    # 계약일이 '-' 인 거래는 결과에 trade_date null 로 남고, 기간보다 오래된 거래로 치지 않아 쪽 넘김을 멈추지 않는다
    deposit = {'dealPrice': 0, 'deposit': 250_000_000, 'monthlyRent': 0}
    page = _ok({'totalCount': 99, 'hasNextPage': True, 'realPriceList': [
        {'tradeDate': '-', 'floor': 3, **deposit},
        {'tradeDate': '2026-09-05', 'floor': 2, **deposit},
    ]})
    requests: list[httpx.Request] = []
    # 기간 조회는 아파트 단지 기간 목록을 먼저 묻고, 비어 오면 빌라로 넘어간다
    overrides = _villa_overrides(**{'/complex/villa/realPricePage': page, '/complex/pyeong/realPrice/list': _ok([])})
    with make_path_client(requests, overrides) as client:
        result = get_real_prices(client, 100002, 4, trade_type='전세', period='1년', today=date(2026, 11, 19))
    assert _paths(requests).count('/complex/villa/realPricePage') == MAX_VILLA_PERIOD_PAGES
    assert [trade.trade_date for trade in result.trades[:2]] == [None, '2026-09-05']
    assert any(text.startswith('[일부]') for text in result.notes)


def test_villa_around_km_sends_the_box_and_monthly_has_no_per_pyeong_key() -> None:
    requests: list[httpx.Request] = []
    with make_path_client(requests, _villa_overrides()) as client:
        data = get_real_prices(client, 100002, 4, trade_type='월세', around_km=0.5).model_dump(mode='json')
    # 월세는 웹이 평당 실거래가 칸을 그리지 않아 키가 없고 요청도 하지 않는다. 주변 실거래는 그대로 있다
    assert 'price_per_pyeong_trades' not in data
    assert '/complex/villa/realPricePyeongPrice' not in _paths(requests)
    assert (data['nearby_trades']['height_km'], data['nearby_trades']['width_km']) == (1.0, 1.0)
    params = requests[-1].url.params
    assert abs(float(params['top']) - float(params['bottom']) - 0.5 * 2 / 110.574) < 1e-6
    assert 'deposit_manwon' in data['nearby_trades']['trades'][0] and 'rent_manwon' in data['nearby_trades']['trades'][0]


def test_villa_trade_info_failure_is_unknown_and_empty_is_empty() -> None:
    failure = {'isSuccess': False, 'detailCode': 'ERROR', 'result': {}}
    # 평당 실거래가 조회 실패와 단지 좌표를 모름은 null 이다 (성공한 빈 응답과 다르다)
    with make_path_client([], _villa_overrides(coordinates=None, **{'/complex/villa/realPricePyeongPrice': failure})) as client:
        result = get_real_prices(client, 100002, 4, trade_type='매매')
    data = result.model_dump(mode='json')
    assert data['price_per_pyeong_trades'] is None and data['nearby_trades'] is None
    # 실패한 평당 실거래가만 [실패] 안내를 남긴다 (isSuccess false 라 업데이트 안내가 붙는다). 단지 좌표가 성공인데 없는 것은 실패가 아니라 안내가 없다
    failure_notes = [text for text in result.notes if text.startswith('[실패] ')]
    assert len(failure_notes) == 1 and '평당 실거래가' in failure_notes[0] and UPDATE_MAYBE_NEEDED in failure_notes[0]
    assert not any('단지 좌표' in text for text in result.notes)
    # 성공한 빈 응답은 [] 이다 (result 가 null 이어도 같다). 매매 거래에는 갱신 키가 없다
    empty = {
        '/complex/villa/realPricePyeongPrice': _ok(None),
        '/complex/villa/realPriceAround': _ok({'aroundRealPriceList': None}),
    }
    with make_path_client([], _villa_overrides(**empty)) as client:
        data = get_real_prices(client, 100002, 4, trade_type='매매').model_dump(mode='json')
    assert data['price_per_pyeong_trades'] == [] and data['nearby_trades']['trades'] == []


def _raise(exc: Exception):
    def request() -> NaverResponseModel[int]:
        raise exc

    return request


@pytest.mark.parametrize(('exc', 'needs_update'), [
    (httpx.ConnectError('연결 실패'), False),
    (httpx.HTTPStatusError('서버 오류', request=httpx.Request('GET', 'https://x'), response=httpx.Response(503)), False),
    (httpx.HTTPStatusError('거절', request=httpx.Request('GET', 'https://x'), response=httpx.Response(403)), True),
    (ValueError('응답 형식'), True),
])
def test_optional_lookup_failure_note(exc: Exception, needs_update: bool) -> None:
    # 일시 장애(5xx·연결 실패)는 업데이트 안내 없이, 거절(4xx)·응답 형식 변경은 업데이트 안내를 붙인다 (매일 감시가 둘을 가른다)
    notes: list[str] = []
    assert result_or_none(_raise(exc), notes=notes, what='관리비', unknown='모름(null)으로 낸 칸: fee') is None
    # 같은 실패를 거듭 불러도 안내는 하나다
    assert result_or_none(_raise(exc), notes=notes, what='관리비', unknown='모름(null)으로 낸 칸: fee') is None
    assert len(notes) == 1 and notes[0].startswith('[실패] ') and (UPDATE_MAYBE_NEEDED in notes[0]) is needs_update


def test_result_or_empty_is_success_false_notes_update_hint() -> None:
    notes: list[str] = []
    response = NaverResponseModel[list[int]].model_validate({'isSuccess': False, 'detailCode': 'ERROR'})
    assert result_or_empty(lambda: response, list, notes=notes, what='관리비', unknown='모름(null)으로 낸 칸: fee') is None
    assert len(notes) == 1 and notes[0].startswith('[실패] ') and UPDATE_MAYBE_NEEDED in notes[0]
    # notes 가 None 이면 호출부가 스스로 알리는 것이라 안내를 더하지 않는다
    assert result_or_empty(lambda: response, list, notes=None, what='관리비', unknown='') is None


def test_pagination_notes_do_not_say_both_all_and_partial() -> None:
    # 인자는 (total, returned, limit, inspected). 서버가 더 주지 않고 끝났으면 '전부' 와 '[일부]' 를 함께 내지 않는다
    def notes(total: int, returned: int, limit: int, inspected: int, **kwargs: Any) -> list[str]:
        kwargs.setdefault('stalled', False)
        kwargs.setdefault('exhausted', False)
        return pagination_notes(total, returned, limit, inspected, narrow='조건·지역', **kwargs)

    # 다음 쪽이 있다며 새 항목을 주지 않고 멈췄다 → '없습니다' 없이 확인한 데까지만 알린다
    stalled = notes(500, 0, 120, 0, stalled=True)
    assert len(stalled) == 1 and stalled[0].startswith('[일부] ') and '없습니다' not in stalled[0] and '500건' in stalled[0]
    # 같은 쪽을 되풀이했어도 서버가 센 수를 다 받았으면 멈춘 게 아니라 다 받은 것이다 (판정은 PageScan.stopped_short, 이어 받기는 견주지 않는다)
    assert not PageScan(limit=120, max_requests=5, received=30, total=30, stalled=True).stopped_short(resumed=False)
    assert PageScan(limit=120, max_requests=5, received=30, total=500, stalled=True).stopped_short(resumed=False)
    assert PageScan(limit=120, max_requests=5, received=30, total=30, stalled=True).stopped_short(resumed=True)
    assert notes(30, 30, 120, 30) == ['조건에 맞는 매물은 이 30건이 전부입니다']
    # 끝까지 받았는데 서버 수가 더 크면 '전부' 와 [참고]. 반경 검색(total_basis)은 총수가 사각형 기준이라 [참고] 가 없다
    done = notes(150, 40, 120, 40)
    assert '전부입니다' in done[0] and done[1].startswith('[참고] ') and len(done) == 2
    radius = notes(150, 40, 120, 40, total_basis='반경을 감싼 사각형 안')
    assert len(radius) == 1 and '전부입니다' in radius[0]
    excluded = notes(150, 30, 120, 40)
    assert '더 받을 매물 없음' in excluded[0] and excluded[1].startswith('[참고] ') and len(excluded) == 2
    # 할당량을 다 쓰고 서버 수가 더 크면 [일부]
    assert '최대값' in notes(1000, 120, 120, 120)[0] and '--limit 을 늘리' in notes(1000, 20, 20, 20)[0]
    # 이어 받은 결과의 total 은 앞 결과까지 센 수라 [참고] 를 붙이지 않는다
    assert all(not item.startswith('[참고]') for item in notes(500, 10, 120, 40, resumed=True))
    # 이어 받다 멈추면 전체 수 대신 이번에 받은 수만 말한다
    resumed_stalled = notes(500, 10, 120, 10, stalled=True, resumed=True)
    assert len(resumed_stalled) == 1 and '500건' not in resumed_stalled[0] and '이번에는 10건까지만' in resumed_stalled[0]
    # 서버가 끝났다고 한 마지막 쪽이 마침 --limit 에 닿았으면 더 있다고 하지 않는다 ([참고] 만, 경계 검색)
    exhausted = notes(500, 120, 120, 120, exhausted=True)
    assert len(exhausted) == 1 and exhausted[0].startswith('[참고] ')


class _FakePage:
    """`scan_pages` 가 읽는 것만 가진 가짜 쪽."""

    def __init__(self, items: list[Any], has_next_page: bool = True) -> None:
        self.items = items
        self.has_next_page = has_next_page
        self.total_count = 99
        self.seed = None
        self.last_info = None

    def null_items(self, field: str) -> int:
        return 0


def _scan_fake_pages(pages: list[_FakePage], keep: Any) -> PageScan:
    scan = PageScan(limit=100, max_requests=2)
    queue = iter(pages)
    scan_pages(scan, lambda size, seed, last_info: next(queue), keep, page_size=10)
    return scan


def test_scan_pages_counts_pages_without_ids_or_with_only_empty_items() -> None:
    # 번호를 모르는 항목(keep 이 None)뿐인 쪽은 되풀이인지 알 수 없어 멈추지 않고 센다
    scan = _scan_fake_pages([_FakePage(['a', 'b']), _FakePage(['c', 'd'])], lambda item: 1 if item in 'ab' else None)
    assert not scan.stalled and scan.received == 4
    scan = _scan_fake_pages([_FakePage(['a']), _FakePage(['x', 'y'])], lambda item: None)
    assert not scan.stalled and scan.received == 3 and scan.truncated
    # 이미 받은 번호만 되풀이하면 멈춘다
    scan = _scan_fake_pages([_FakePage(['a']), _FakePage(['a'])], lambda item: item)
    assert scan.stalled and scan.received == 1
    # 항목 없이 빈 항목(null)만 있는 쪽은 서버가 센 자리라 null_items 에 세고 멈추지 않는다
    empty = _FakePage([])
    empty.null_items = lambda field: 2
    scan = _scan_fake_pages([_FakePage(['a']), empty], lambda item: item)
    assert not scan.stalled and scan.received == 3 and scan.null_items == 2


def test_real_price_around_km_is_rejected_for_apartment_complex() -> None:
    requests: list[httpx.Request] = []
    with make_client(requests) as client, pytest.raises(JibsaError) as exc:
        get_real_prices(client, 100001, 1, pages=3, around_km=0.5)
    # 아파트 첫 쪽으로 단지 종류가 정해진 직후 막아 더 받지 않는다. 옵션을 빼면 성공한다
    assert exc.value.code == 'INVALID_ARGUMENT' and exc.value.hint == '옵션을 빼고 다시 부르세요'
    assert len(requests) == 1
    with make_client() as client:
        assert 'nearby_trades' not in get_real_prices(client, 100001, 1).model_dump(mode='json')


# --- 사용법 오류 ----------------------------------------------------------------


def test_real_price_group_rejects_period(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_request(*args, **kwargs) -> None:
        raise AssertionError('입력 오류 검증에서 HTTP 요청을 보내면 안 됩니다')

    monkeypatch.setattr(httpx.Client, 'send', unexpected_request)
    assert run(['naver', 'real-price', '100001', '--pyeong', '1', '--group', '--period', '1년']) == 2
    assert json.loads(capsys.readouterr().err)['error']['code'] == 'INVALID_ARGUMENT'


# --- 호가 짝·기간 --------------------------------------------------------------


def test_rent_asking_range_pairs_deposit_with_rent_of_the_first_listing() -> None:
    # 헬리오시티 111515 (2026-11-18): 보증금 낮은 첫 매물의 월세가 보증금 높은 첫 매물의 월세보다 크다
    price = NaverComplexArticlePriceModel.model_validate({
        'rentMonthlyLeaseMinPrice': 50000000, 'rentMonthlyMinPrice': 4200000,
        'rentMonthlyLeaseMaxPrice': 7000000000, 'rentMonthlyMaxPrice': 2400000,
    })
    result = rent_asking_range(price, 'monthly')
    assert result is not None
    assert (result.lowest.deposit_manwon, result.lowest.rent_manwon) == (5000, 420)
    assert (result.highest.deposit_manwon, result.highest.rent_manwon) == (700000, 240)
    # 단기임대 매물이 없으면 단기 키가 오지 않는다
    assert rent_asking_range(price, 'short') is None


def test_rent_asking_range_empties_a_pair_whose_deposit_and_rent_are_both_zero() -> None:
    # 한 짝의 보증금·월세가 모두 0 이면 서버가 비운 짝이라 보증금 0 을 내지 않는다
    price = NaverComplexArticlePriceModel.model_validate({
        'rentMonthlyLeaseMinPrice': 0, 'rentMonthlyMinPrice': 0,
        'rentMonthlyLeaseMaxPrice': 100000000, 'rentMonthlyMaxPrice': 1000000,
    })
    result = rent_asking_range(price, 'monthly')
    assert result is not None
    assert (result.lowest.deposit_manwon, result.lowest.rent_manwon) == (None, None)
    assert (result.highest.deposit_manwon, result.highest.rent_manwon) == (10000.0, 100.0)


def test_group_fields_reads_zero_rent_as_unknown() -> None:
    # 월세 0원 매물은 없어 서버가 비운 값이다 (보증금 0 과 달리 null). 보증금이 아는 값이면 그 칸은 그대로 낸다
    for max_rent, expected_rent in ((0, None), (500000, 50)):
        model = NaverDuplicatedArticleInfoModel.model_validate({
            'realtorCount': 3,
            'representativePriceInfo': {
                'warrantyPrice': {'minPrice': 5000000, 'maxPrice': 10000000},
                'rentPrice': {'minPrice': 0, 'maxPrice': max_rent},
            },
        })
        result = group_fields(model, '월세')['asking_range'].model_dump()
        assert result['lowest'] == {'deposit_manwon': 500, 'rent_manwon': None}
        assert result['highest'] == {'deposit_manwon': 1000, 'rent_manwon': expected_rent}


def test_months_ago_clamps_to_month_end_and_matches_years_ago() -> None:
    assert months_ago(date(2026, 5, 31), 3) == '2026-02-28'
    assert months_ago(date(2026, 1, 31), 3) == '2025-10-31'
    assert months_ago(date(2024, 5, 31), 3) == '2024-02-29'
    # 1년·3년·5년은 기존 years_ago 와 같은 날이다 (2월 29일 포함)
    for today in (date(2024, 2, 29), date(2026, 11, 18)):
        for years in (1, 3, 5):
            assert months_ago(today, years * 12) == years_ago(today, years)


def test_null_list_fields_read_as_missing_keys() -> None:
    # 서버가 목록 칸에 null 을 줘도 ValidationError 로 조회 전체가 깨지지 않고, 키가 없을 때와 같은 빈 목록이 된다
    facility = NaverFacilityInfoModel.model_validate({'life': None, 'security': ['CCTV'], 'etc': None})
    assert (facility.life, facility.security, facility.etc, facility.aircon) == ([], ['CCTV'], [], [])
    # `| None` 칸은 null 이 모름이라 빈 목록으로 바꾸지 않는다 (재개발 역·지구)
    assert NaverDevelopmentArticleModel.model_validate({'railList': None}).rail_list is None


def test_null_items_make_computed_values_unknown() -> None:
    # 목록 안에 빈 항목(null)이 와서 뺐으면 그 목록으로 계산한 값을 완전한 값처럼 내지 않고 모름(null)으로 두며 [제외] 로 알린다.
    # 실제로 온 적이 없는 응답이라 가짜 응답으로만 확인한다
    fee = _ok({'typeCode': '01', 'fixDetailList': [
        {'type': '01', 'unitType': '01', 'amount': 100000}, None, {'type': '11', 'unitType': '02'},
    ]})
    with make_path_client([], {'/article/maintenanceFee': fee}) as client:
        detail = get_listing(client, '1000000001')
    assert (detail.manage_cost_manwon, detail.manage_cost_includes) == (None, None)
    assert any(note.startswith('[제외] 네이버 관리비 항목 목록에 빈 항목 1개') for note in detail.notes)

    weekly = _ok([{'firstDayOfWeek': '2026-11-02', 'averagePyeongPrice': 50_000_000}, None])
    with make_path_client([], {'/legalDivision/pyeongPriceWeeklyList': weekly}) as client:
        trend = get_district_trend(client, '1100010100')
    assert trend.asking_price_per_pyeong is not None
    # 받은 주는 그대로 두고 최근 주만 모른다 (빈 항목이 마지막 주였는지 알 수 없다)
    assert [week.week_start for week in trend.asking_price_per_pyeong.weeks] == ['2026-11-02']
    assert trend.asking_price_per_pyeong.latest_manwon is None
    assert any(note.startswith('[제외] 네이버 평당가 추이 목록에 빈 항목 1개') for note in trend.notes)
