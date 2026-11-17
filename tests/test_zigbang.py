import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from jibsa.core.errors import (
    JibsaError,
    ListingUnavailableError,
)
from jibsa.core.geo import (
    encode_geohash,
    geohashes_covering,
    haversine_km,
)
from jibsa.core.listing import NEXT_HINT
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.listing import (
    ZigbangItemsVillasV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangItemCatalogModel,
    ZigbangItemsListV1ResponseModel,
    ZigbangItemSummaryModel,
)
from jibsa.providers.zigbang.api.response.listing import (
    ZigbangAptManageCostModel,
    ZigbangItemCatalogsItemsResponseModel,
    ZigbangItemsDetailV1ResponseModel,
)
from jibsa.providers.zigbang.api.response.store import (
    ZigbangStoreArticleStoreV2ResponseModel,
)
from jibsa.providers.zigbang.service.apt import (
    ZigbangAptConditions,
    search_apt_listings,
)
from jibsa.providers.zigbang.service.common import (
    ZigbangRegion,
    ZigbangRoomConditions,
    catalog_to_listing,
    summary_to_listing,
)
from jibsa.providers.zigbang.service.complex import search_station_complexes
from jibsa.providers.zigbang.service.detail import get_any_listing
from jibsa.providers.zigbang.service.listing import (
    detail_to_listing,
    search_listings,
)
from jibsa.providers.zigbang.service.real_price import get_real_prices
from jibsa.providers.zigbang.service.region import resolve_region_scope
from jibsa.providers.zigbang.service.store import (
    ZigbangStoreConditions,
    search_store_listings,
    store_detail_to_listing,
)


FIXTURES = Path(__file__).parent / 'fixtures' / 'zigbang'


def load(name: str) -> dict:
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


# --- normalisation ----------------------------------------------------------


def test_summary_to_listing_uses_exclusive_area_not_size_m2() -> None:
    # 오피스텔은 size_m2 가 공급면적(50.0)이라 전용면적(25.0)을 써야 한다.
    summary = ZigbangItemsListV1ResponseModel.model_validate(load('items_list_v1')).items[1]
    assert summary.service_type == '오피스텔'
    listing = summary_to_listing(summary)
    assert listing.area_m2 == 25.0
    assert listing.area_pyeong == 7.6


def test_summary_to_listing_officetel_without_exclusive_area_is_unknown() -> None:
    # 오피스텔은 전용면적이 빠져도 공급면적(size_m2)을 전용으로 내보내지 않는다. 원룸은 둘이 같아 대신 쓴다.
    items = ZigbangItemsListV1ResponseModel.model_validate(load('items_list_v1')).items
    officetel = items[1].model_copy(update={'exclusive_area': None})
    assert summary_to_listing(officetel).area_m2 is None
    oneroom = items[0].model_copy(update={'exclusive_area': None})
    assert oneroom.service_type == '원룸'
    assert summary_to_listing(oneroom).area_m2 == oneroom.size_m2


def test_summary_to_listing_sale_moves_deposit_to_price() -> None:
    summary = ZigbangItemSummaryModel.model_validate({
        'item_id': 1,
        'sales_type': '매매',
        'deposit': 190000,
        'rent': 0,
        'service_type': '빌라',
    })
    listing = summary_to_listing(summary)
    assert (listing.price_manwon, listing.deposit_manwon, listing.rent_manwon) == (190000, None, None)


def test_detail_to_listing_keeps_only_discovery_fields() -> None:
    detail = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(load('items_detail_v1')))
    assert detail.manage_cost_manwon == 10
    assert detail.address == '서울특별시 서초구 서초동 100-1'
    assert detail.bathroom_count == 1
    # 직방은 사용승인일을 '20000101' / '2020.01.22' 로 준다
    assert detail.approved_at == '2000-01-01'
    # 본문은 내보내지 않는다 (원 사이트에서 확인)
    assert 'description_excerpt' not in detail.model_dump(mode='json')
    dumped = detail.model_dump(mode='json', exclude_none=True)
    for removed in ('agent', 'images', 'description', 'thumbnail_url', 'lat', 'lng'):
        assert removed not in dumped
    assert '020000002' not in json.dumps(dumped, ensure_ascii=False)


# --- geo --------------------------------------------------------------------

def test_geohash_matches_reference() -> None:
    # 문서의 검증 타일 (서울 강남/서초)
    assert encode_geohash(37.49, 127.02, 5) == 'wydm6'


def test_geohashes_covering_does_not_skip_cells_for_large_radius() -> None:
    # 상가(정밀도 6)는 반경이 칸보다 훨씬 커서, 고정 격자면 중심 바로 옆 칸까지 빠졌다
    lat, lng, radius = 37.5005, 127.0365, 4.0
    cells = set(geohashes_covering(lat, lng, radius, 6))
    for step in range(-40, 41):
        for other in range(-40, 41):
            point_lat, point_lng = lat + step * 0.0009, lng + other * 0.00113
            if haversine_km(lat, lng, point_lat, point_lng) <= radius:
                assert encode_geohash(point_lat, point_lng, 6) in cells


# --- auth flow --------------------------------------------------------------

def make_client(handler) -> ZigbangClient:
    client = ZigbangClient()
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


# --- service ----------------------------------------------------------------

def _search_with_fixtures(requested_batches: list[list[int]] | None = None, **kwargs):
    pins = load('items_onerooms_v1')
    summaries = load('items_list_v1')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/items/list'):
            if requested_batches is not None:
                requested_batches.append(json.loads(request.content)['itemIds'])
            return httpx.Response(200, json=summaries)
        return httpx.Response(200, json=pins)

    first = pins['items'][0]
    region = ZigbangRegion(name='center', lat=first['lat'], lng=first['lng'])
    with make_client(handler) as client:
        return first, search_listings(client, region, **{'property_types': ['원룸'], **kwargs})


def test_search_listings_oneroom_keeps_one_room_officetel() -> None:
    # 원룸은 방 하나짜리라, 원룸 목록에 섞여 온 원룸형 오피스텔도 결과로 둔다.
    # 투룸 오피스텔은 원룸형 구조만 서버에 요청해 처음부터 받지 않는다.
    # 서버가 준 매물은 유형·방 구조를 다시 거르지 않는다 (998 은 서버가 잘못 준 경우를 흉내 낸다)
    # 원룸 핀에는 건물 ID 가 없어 같은 조건의 오피스텔 목록으로 999 의 complex_id 를 채운다
    summaries = load('items_list_v1')
    officetel = dict(summaries['items'][0], item_id=999, service_type='오피스텔')
    villa = dict(summaries['items'][0], item_id=998, service_type='빌라', room_type='04')
    summaries['items'] += [officetel, villa]
    pins = load('items_onerooms_v1')
    pins['items'] += [dict(pins['items'][0], id=999), dict(pins['items'][0], id=998)]
    officetel_pins = {'items': [dict(pins['items'][0], id=999, buildingId=20227)]}
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/items/list'):
            return httpx.Response(200, json=summaries)
        sent.append(dict(request.url.params))
        if request.url.path.endswith('/officetels'):
            return httpx.Response(200, json=officetel_pins)
        return httpx.Response(200, json=pins)

    first = pins['items'][0]
    region = ZigbangRegion(name='center', lat=first['lat'], lng=first['lng'])
    with make_client(handler) as client:
        result = search_listings(client, region, property_types=['원룸'], radius_km=5, limit=10)

    assert {'999', '998'} <= {listing.id for listing in result.listings}
    assert {listing.property_type for listing in result.listings} == {'원룸', '오피스텔', '빌라'}
    assert next(listing for listing in result.listings if listing.id == '999').complex_id == 'officetel-20227'
    assert all(
        [params[f'roomType[{index}]'] for index in range(3)] == ['오픈형원룸', '분리형원룸', '복층형원룸']
        and 'roomType[3]' not in params
        for params in sent
    )


def test_search_listings_does_not_refill_excluded() -> None:
    # 받은 뒤 뺀 매물만큼 다음 핀을 더 받지 않고 알린다 (직방 목록 순 앞 3건 중 1000003 은 요약이 없다)
    requested_batches: list[list[int]] = []
    _, result = _search_with_fixtures(requested_batches, radius_km=5, limit=3, conditions=ZigbangRoomConditions(trade_types=['전세']))
    assert sum(len(batch) for batch in requested_batches) == 3
    assert result.returned < 3
    assert any('다시 채우지 않음' in note for note in result.notes)


def test_search_listings_follows_section_order_and_keeps_radius() -> None:
    # 웹 목록처럼 섹션 순서(안심추천 → 안심일반)·섹션 안 서버 순서로 내고 거리순으로 다시 세우지 않는다.
    # 반경 밖 매물(1000002, 약 1.6km)은 반경 안이 --limit 보다 적어도 채우지 않는다
    pins = load('items_onerooms_v1')
    pins['sections'] = [
        {'type': 'PREMIUM_RECOMMEND', 'ids': [1000004, 1000002]},
        {'type': 'PREMIUM', 'ids': [1000005, 1000001]},
    ]
    template = load('items_list_v1')['items'][0]
    requested: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/items/list'):
            ids = json.loads(request.content)['itemIds']
            requested.extend(ids)
            # 요약 응답 순서가 달라도 보낸 순서로 낸다
            return httpx.Response(200, json={'items': [dict(template, item_id=item_id) for item_id in reversed(ids)]})
        return httpx.Response(200, json=pins)

    center = pins['items'][0]
    region = ZigbangRegion(name='center', lat=center['lat'], lng=center['lng'])
    with make_client(handler) as client:
        result = search_listings(client, region, property_types=['원룸'], radius_km=1, limit=10)

    # 섹션에 없는 1000003 은 맨 뒤다
    assert requested == [1000004, 1000005, 1000001, 1000003]
    assert [listing.id for listing in result.listings] == ['1000004', '1000005', '1000001', '1000003']
    assert result.total == 4 and not result.has_more


def test_closed_items_are_excluded() -> None:
    from jibsa.core.errors import ListingUnavailableError
    from jibsa.providers.zigbang.service.listing import get_listing

    summaries = load('items_list_v1')
    summaries['items'][0]['status'] = False
    pins = load('items_onerooms_v1')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/items/list'):
            return httpx.Response(200, json=summaries)
        if request.url.path.endswith('/detail'):
            detail = load('items_detail_v1')
            detail['item']['status'] = 'closed'
            return httpx.Response(200, json=detail)
        return httpx.Response(200, json=pins)

    first = pins['items'][0]
    region = ZigbangRegion(name='center', lat=first['lat'], lng=first['lng'])
    with make_client(handler) as client:
        result = search_listings(client, region, property_types=['원룸'], radius_km=5)
        assert str(summaries['items'][0]['item_id']) not in {listing.id for listing in result.listings}
        with pytest.raises(ListingUnavailableError):
            get_listing(client, 1000001)


def test_items_without_status_are_excluded() -> None:
    from jibsa.core.errors import ListingUnavailableError
    from jibsa.providers.zigbang.service.listing import get_listing

    summaries = load('items_list_v1')
    del summaries['items'][0]['status']
    pins = load('items_onerooms_v1')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/items/list'):
            return httpx.Response(200, json=summaries)
        if request.url.path.endswith('/detail'):
            detail = load('items_detail_v1')
            del detail['item']['status']
            return httpx.Response(200, json=detail)
        return httpx.Response(200, json=pins)

    first = pins['items'][0]
    region = ZigbangRegion(name='center', lat=first['lat'], lng=first['lng'])
    with make_client(handler) as client:
        result = search_listings(client, region, property_types=['원룸'], radius_km=5)
        assert str(summaries['items'][0]['item_id']) not in {listing.id for listing in result.listings}
        with pytest.raises(ListingUnavailableError):
            get_listing(client, 1000001)


# --- 단기임대 ---------------------------------------------------------------

def test_short_term_summary_is_not_monthly_rent() -> None:
    # 직방은 단기임대를 월세로 주고 contract '단기' 로만 구분한다. 월세로 옮기면 싼 월세처럼 보인다.
    summary = ZigbangItemsListV1ResponseModel.model_validate(load('items_list_v1')).items[0]
    short = summary.model_copy(update={'contract': '단기', 'deposit': 75, 'rent': 75})
    listing = summary_to_listing(short)
    assert listing.trade_type == '단기임대'
    assert (listing.deposit_manwon, listing.rent_manwon) == (75, 75)
    assert 'price_manwon' not in listing.model_dump()
    # 일반 월세는 contract 가 빈 문자열이다
    assert summary_to_listing(summary.model_copy(update={'contract': ''})).trade_type == '월세'


# --- 원룸·오피스텔·빌라 상세 필터 ----------------------------------------------

def test_items_filters_serialize_for_server() -> None:
    parameter = ZigbangItemsVillasV1RequestParameterModel(
        geohash='wydm6',
        room_types=['투룸', '쓰리룸플러스'],
        floors=['지상'],
        options=['에어컨', '세탁기'],
        size_min_m2=33,
        size_max_pyeong=15,
        bathroom_count=2,
        manage_cost_max=10,
        elevator=True,
        pet=False,
    )
    assert parameter.model_dump(by_alias=True, exclude_none=True) == {
        'geohash': 'wydm6',
        'manageCostMax': 10,
        'sizeMinM2': 33,
        'sizeMax': 15,
        'bathroomCount': 2,
        'isElevator': True,
        'roomType[0]': '투룸',
        'roomType[1]': '쓰리룸플러스',
        'floor[0]': '지상',
        'options[0]': '에어컨',
        'options[1]': '세탁기',
    }


# --- 아파트 ------------------------------------------------------------------


def test_locals_item_catalogs_serializes_trade_codes_and_path() -> None:
    parameter = ZigbangLocalsItemCatalogsRequestParameterModel(
        local_code='11680101',
        tran_types=['charter', 'rental'],
        deposit_max=80000,
    )
    assert parameter.model_dump(by_alias=True, exclude_none=True) == {
        'maxRentDeposit': 80000,
        'offset': 0,
        'limit': 20,
        'tranTypeIn[0]': 'charter',
        'tranTypeIn[1]': 'rental',
    }
    with pytest.raises(ValidationError):
        ZigbangLocalsItemCatalogsRequestParameterModel(local_code='1168010100')
    with pytest.raises(ValidationError):
        ZigbangLocalsItemCatalogsRequestParameterModel(local_code='11680101', limit=21)


def apt_detail_handler(apt_response: httpx.Response, requested: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(f'{request.url.path}?{request.url.query.decode()}')
        if request.url.path.startswith('/apt/item-catalogs/items/'):
            return apt_response
        if request.url.path.endswith('/detail'):
            # 새 주거 상세는 아파트 매물에 code 가 있는 404 를 준다 (2026-11-15 실측). 없는 매물의 404 에는 code 가 없다
            return httpx.Response(404, json={
                'statusCode': 404, 'code': 'ITEM_QUERY_DETAIL_SERVICE_TYPE_NOT_SUPPORTED', 'metadata': {'serviceType': '아파트'},
            })
        pytest.fail(f'아파트 상세에 쓰지 않는 요청입니다: {request.url.path}')
    return handler


def test_apt_listing_uses_apt_detail_when_house_detail_rejects_apartment() -> None:
    from jibsa.providers.zigbang.service.listing import get_listing

    # 아파트 매물은 웹 아파트 화면처럼 아파트 상세 하나로 만든다. 주거 상세의 404 를 내려간 매물로 읽으면
    # 살아 있는 아파트 매물이 모두 LISTING_UNAVAILABLE 이 된다 (2026-11-14 실측)
    requested: list[str] = []
    handler = apt_detail_handler(httpx.Response(200, json=load('item_catalogs_items')), requested)
    with make_client(handler) as client:
        dumped = get_listing(client, 1000001).model_dump()
    assert [line.split('?')[0] for line in requested] == [
        '/house/property/v1/items/1000001/detail', '/apt/item-catalogs/items/1000001',
    ]
    assert 'itemSource=zigbang' in requested[1]
    assert dumped['property_type'] == '아파트' and dumped['complex_name'] == '가상아파트 101동'
    assert dumped['url'] == 'https://www.zigbang.com/home/apt/item/v2/1000001/zigbang/0'
    # 세대수는 아파트에도 있지만 아파트 상세가 주지 않아 모름이다
    assert dumped['direction_criterion'] == '거실' and dumped['household_count'] is None

    # 아파트 상세도 404 면 내려간 매물이다
    handler = apt_detail_handler(httpx.Response(404, json={'code': 404, 'message': 'not found item'}), [])
    with make_client(handler) as client, pytest.raises(ListingUnavailableError):
        get_listing(client, 1000001)


def test_apt_listing_kind_from_item_type() -> None:
    from jibsa.providers.zigbang.service.common import ZigbangAptListing
    from jibsa.providers.zigbang.service.listing import apt_item_to_listing

    # 신규분양 카드는 출처가 coalition 이라 coalition- 줄이 되고, 분양가가 집주인 호가로 읽히지 않게 종류를 알린다
    card = load('locals_item_catalogs')['list'][0]
    card['itemIdList'] = [{'itemSource': 'coalition', 'itemId': 3000009}]

    def kind(item_type: str | None) -> str | None:
        line = catalog_to_listing(ZigbangItemCatalogModel.model_validate({**card, 'itemType': item_type}), '서울특별시')
        assert line is not None and line.id == 'coalition-3000009'
        return line.listing_kind

    assert kind('offer') == '신규분양' and kind('self_ad') == '중개사' and kind('partner') == '집주인'
    assert kind('unknown_kind') == 'unknown_kind' and kind(None) is None

    # 섞인 묶음은 직방 응답 순서 그대로라 id 는 묶음 종류·제목·층을 정하는 맨 앞 매물이다 (제휴가 앞이면 제휴 매물)
    def mixed(id_list: list[dict[str, object]]) -> ZigbangAptListing:
        item = ZigbangItemCatalogModel.model_validate({**card, 'itemType': 'partner', 'itemIdList': id_list})
        line = catalog_to_listing(item, '서울특별시')
        assert line is not None
        return line

    line = mixed([{'itemSource': 'coalition', 'itemId': 3000009}, {'itemSource': 'zigbang', 'itemId': 3000010}])
    assert line.id == 'coalition-3000009' and line.listing_ids == ['coalition-3000009', '3000010']
    assert line.listing_kind == '집주인'
    # 맨 앞이 상세를 볼 수 없는 출처면 id 는 묶음 종류를 정한 매물이 아니라 종류를 모른다
    line = mixed([{'itemSource': 'other', 'itemId': 3000009}, {'itemSource': 'zigbang', 'itemId': 3000010}])
    assert line.id == '3000010' and line.listing_kind is None

    # 상세·묶음 줄도 같은 값이고, 직방이 종류를 주지 않았으면 모름(null)이다
    apt = ZigbangItemCatalogsItemsResponseModel.model_validate(load('item_catalogs_items')).item
    assert apt_item_to_listing(apt, 'zigbang').model_dump()['listing_kind'] == '중개사'
    apt.item_type = None
    assert apt_item_to_listing(apt, 'zigbang').model_dump()['listing_kind'] is None


def test_apt_manage_cost_unconfirmed_is_unknown() -> None:
    from jibsa.providers.zigbang.service.listing import apt_item_to_listing

    apt = ZigbangItemCatalogsItemsResponseModel.model_validate(load('item_catalogs_items')).item
    apt.manage_cost = ZigbangAptManageCostModel(type='unconfirmed')
    detail = apt_item_to_listing(apt, 'zigbang')
    assert detail.manage_cost_manwon is None and detail.manage_cost_includes is None
    assert detail.room_count == 3


def test_non_apt_detail_omits_apt_only_fields() -> None:
    dumped = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(load('items_detail_v1'))).model_dump()
    assert 'complex_name' not in dumped and 'supply_area_m2' not in dumped and 'listing_kind' not in dumped


# --- 상가 --------------------------------------------------------------------


def test_store_detail_drops_contact_and_photos() -> None:
    response = ZigbangStoreArticleStoreV2ResponseModel.model_validate(load('store_article_store_v2'))
    detail = store_detail_to_listing(response).model_dump()
    assert detail['id'] == 'store-4000001'
    assert detail['building_floor'] == '5' and detail['elevator'] is True
    assert detail['nearby_subways'] == ['가상역 (2호선)']
    text = json.dumps(detail, ensure_ascii=False)
    assert '010-0000-0000' not in text and 'photo.jpg' not in text and '가상 설명' not in text


def test_store_detail_closed_is_unavailable() -> None:
    data = load('store_article_store_v2')
    data['item']['status'] = 'close'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    with make_client(handler) as client, pytest.raises(ListingUnavailableError):
        get_any_listing(client, 'store-4000001')


# --- 단기임대 ----------------------------------------------------------------


def test_stay_detail_not_reviewed_is_unavailable() -> None:
    data = dict(load('guest_items'), checkStatus='PENDING')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    with make_client(handler) as client, pytest.raises(ListingUnavailableError):
        get_any_listing(client, 'stay-5001')


# --- 아파트 제휴(집주인·신규분양) 매물 ---------------------------------------------


def test_coalition_listing_gone_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={'message': 'not found item'})

    with make_client(handler) as client, pytest.raises(ListingUnavailableError):
        get_any_listing(client, 'coalition-3000002')


# --- search room 동 경계 ----------------------------------------------------------------

# 1000001·1000003·1000004·1000005 (127.012~127.015) 만 들어가고 1000002 (127.031) 는 밖인 가상 동 경계
BOUNDARY_SQUARE = [[[[127.010, 37.485], [127.020, 37.485], [127.020, 37.495], [127.010, 37.495], [127.010, 37.485]]]]


def test_in_multipolygon_respects_holes() -> None:
    from jibsa.core.geo import in_multipolygon

    with_hole = [[BOUNDARY_SQUARE[0][0], [[127.0125, 37.4875], [127.0175, 37.4875], [127.0175, 37.4925], [127.0125, 37.4925], [127.0125, 37.4875]]]]
    assert in_multipolygon(37.486, 127.011, with_hole)
    assert not in_multipolygon(37.49, 127.015, with_hole)  # 구멍 안
    assert not in_multipolygon(37.49, 127.031, with_hole)


# --- 상가 가격 필터 ----------------------------------------------------------

@pytest.mark.parametrize('field, wire, amount', [
    ('deposit', '보증금액', 3000),
    ('rent', '월세금액', 200),
    ('price', '매매금액', 90000),
    ('manage_cost', '관리금액', 20),
    ('key_money', '권리금액', 0),
])
def test_store_price_filter_inclusive_and_unknown(field: str, wire: str, amount: int) -> None:
    base = load('store_article_stores_list_v2')[1 if field == 'price' else 0]
    summaries = []
    for index, value in enumerate((amount - 1, amount, amount + 1, None), start=1):
        summaries.append({**base, 'item_id': index, wire: value})
    summaries.append({**base, 'item_id': 5, wire: amount, 'status': 'close'})
    pins = [{'title': '이 지역 상가', 'item_locations': [
        {'item_id': item['item_id'], 'lat': 37.5, 'lng': 127.03} for item in summaries
    ]}]
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/stores/list'):
            return httpx.Response(200, json=summaries)
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=pins)

    region = ZigbangRegion(name='center', lat=37.5, lng=127.03)
    lower = max(0, amount - 1)
    with make_client(handler) as client:
        result = search_store_listings(client, region, conditions=ZigbangStoreConditions(**{
            f'{field}_min': lower, f'{field}_max': amount,
        }))
    expected = ['store-2'] if amount == 0 else ['store-1', 'store-2']
    assert [item.id for item in result.listings] == expected
    assert payloads[0]['sales_type'] == ('매매' if field == 'price' else '전체' if field == 'manage_cost' else '임대')
    data = result.model_dump()
    assert data['total'] == 5
    assert data['inspected_in_radius'] == 5
    assert data['price_matched_in_radius'] == len(expected)


@pytest.mark.parametrize('mode, expected_ids, batch_sizes, capped', [
    ('next', ['store-51'], [50, 10], False),
    ('cap', [], [50, 10], True),
    ('stop', ['store-1'], [50], False),
])
def test_store_price_filter_batches_and_cap(
    mode: str, expected_ids: list[str], batch_sizes: list[int], capped: bool,
) -> None:
    count = 70 if mode in ('cap', 'stop') else 60
    base = load('store_article_stores_list_v2')[0]
    requested = []
    pins = [{'title': '이 지역 상가', 'item_locations': [
        {'item_id': index, 'lat': 37.5 + index * 0.000001, 'lng': 127.03}
        for index in range(1, count + 1)
    ]}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/stores/list'):
            ids = json.loads(request.content)['item_ids']
            requested.append(ids)
            return httpx.Response(200, json=[{
                **base, 'item_id': item_id,
                '월세금액': 100 if item_id == (1 if mode == 'stop' else 70 if mode == 'cap' else 51) else 500,
            } for item_id in reversed(ids)])
        return httpx.Response(200, json=pins)

    region = ZigbangRegion(name='center', lat=37.5, lng=127.03)
    with make_client(handler) as client:
        result = search_store_listings(client, region, conditions=ZigbangStoreConditions(rent_max=100), limit=1)
    assert [item.id for item in result.listings] == expected_ids
    assert [len(batch) for batch in requested] == batch_sizes
    assert result.inspected_in_radius == sum(batch_sizes)
    assert result.price_matched_in_radius == len(expected_ids)
    assert any('후보 조회 상한' in note for note in result.notes) is capped
    assert any('전체 가격 조건 일치 수는 모릅니다' in note for note in result.notes) is (count == 70)


# --- 역 반경 전용 API --------------------------------------------------------


def test_apt_supply_area_region_does_not_refill_filtered_results() -> None:
    offsets = []
    fixture = load('locals_item_catalogs')

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params['sizeContractM2Min'] == '80.0'
        assert request.url.params['sizeContractM2Max'] == '110.0'
        offset = int(request.url.params['offset'])
        offsets.append(offset)
        data = dict(fixture, count=21)
        # 첫 페이지는 공급면적에 맞지만 전용면적에는 맞지 않는다.
        data['list'] = [fixture['list'][0]] if offset == 0 else [fixture['list'][1]]
        return httpx.Response(200, json=data)

    with make_client(handler) as client:
        result = search_apt_listings(client, ZigbangRegion(
            name='가상동', lat=37.5, lng=127.03, legal_division_code='1168010100',
        ), conditions=ZigbangAptConditions(supply_area_min_m2=80, supply_area_max_m2=110, area_max_m2=60), limit=1)
    assert offsets == [0]
    assert result.listings == []
    assert any('다시 채우지 않음' in note for note in result.notes)
    # 받아 온 것 안에서만 걸러 적게 나오니, 서버에서 거르는 공급면적 조건을 안내한다
    assert any('받아 온 1건에서만' in note and '--supply-area-min' in note for note in result.notes)
    assert result.total == 21


@pytest.mark.parametrize('primary_status,legacy_status,http_status', [
    ('closed', 'open', 200), (None, 'open', 200),
    ('open', 'closed', 200), ('open', None, 200), ('open', 'open', 404),
])
def test_new_house_detail_unavailable(primary_status: str | None, legacy_status: str | None, http_status: int) -> None:
    from jibsa.providers.zigbang.service.listing import get_listing
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith('/detail'):
            data = load('items_detail_v1')
            data['item']['status'] = primary_status
            data['item']['residence']['moveInAt'] = None
            return httpx.Response(200, json=data)
        if request.url.path.startswith('/v3/items/'):
            data = load('items_v3')
            data['item']['status'] = legacy_status
            return httpx.Response(http_status, json=data)
        pytest.fail('만료 매물의 요약을 요청했습니다')

    with make_client(handler) as client, pytest.raises(ListingUnavailableError):
        get_listing(client, 1000001)
    if primary_status != 'open':
        assert calls == ['/house/property/v1/items/1000001/detail']


def test_new_house_detail_manage_cost_units() -> None:
    # 금액은 원 단위까지: 직방이 0.1만원 아래를 버린 amount(만원) 대신 원 단위 fee 를 쓴다 (실측 51105591)
    data = load('items_detail_v1')
    data['item']['manageCost'] = {'amount': 37.5, 'fee': 375700, 'include': [{'code': '01', 'name': '수도'}]}
    result = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(data))
    assert result.manage_cost_manwon == 37.57
    assert result.manage_cost_includes == ['수도']

    # 내역 없이 fee 만 있으면 웹(amount 만 봄)은 '관리비 없음' 이라 두 칸이 어긋나 모름이다
    data['item']['manageCost'] = {'fee': 153000, 'include': [{'code': '01', 'name': '수도'}]}
    result = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(data))
    assert result.manage_cost_manwon is None
    assert result.manage_cost_includes is None


@pytest.mark.parametrize(('detail', 'expected'), [
    # 정액 관리비는 웹이 항목별로 보여 준다. 실비로 따로 내는 항목은 include 에 있어도 관리비에 든 것이 아니다
    (
        {
            'type': 'FixedManageCost', 'hasInformed': True, 'normalManageCost': {'type': 'fixed', 'amount': 90000},
            'usageFee': {'electricity': {'type': 'actual'}, 'water': {'type': 'fixed', 'amount': 10000}},
        },
        (10, ['일반(공용) 관리비', '수도']),
    ),
    # 항목별 내역을 알리지 않았으면 웹도 include 목록을 보여 준다. 순서는 웹처럼 일반(공용)·전기·수도·…·TV 이고,
    # 웹 이름표에 없는 '기타 관리비'(웹은 '기타관리비')는 맨 뒤다 (2026-11-15 실측: 50905571)
    (
        {'type': 'FixedManageCost', 'hasInformed': False, 'normalManageCost': {'type': 'fixed', 'amount': 90000}},
        (10, ['일반(공용) 관리비', '전기', '수도', 'TV', '기타 관리비']),
    ),
    # 관리비 확인 불가는 금액도 항목도 모름이다 (실측 표본이 없어 실제 응답의 detail 만 바꿨다)
    ({'type': 'UnknownManageCost'}, (None, None)),
])
def test_new_house_detail_manage_cost_includes_follow_web_rule(detail: dict, expected: tuple) -> None:
    data = load('items_detail_v1')
    data['item']['manageCost'] = {
        'amount': 10, 'fee': 100000, 'detail': detail,
        'include': [
            {'code': '06', 'name': '기타 관리비'}, {'code': '05', 'name': 'TV'}, {'code': '03', 'name': '수도'},
            {'code': '01', 'name': '전기'}, {'code': '00', 'name': '일반(공용) 관리비'},
        ],
    }
    result = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(data))
    assert (result.manage_cost_manwon, result.manage_cost_includes) == expected


@pytest.mark.parametrize('limit', [20, 120])
def test_apt_budget_counts_received_catalogs_before_filtering(limit: int) -> None:
    calls: list[tuple[int, int]] = []
    fixture = load('locals_item_catalogs')

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params['offset'])
        size = int(request.url.params['limit'])
        calls.append((offset, size))
        return httpx.Response(200, json=dict(fixture, count=200, list=[fixture['list'][0]] * size))

    with make_client(handler) as client:
        result = search_apt_listings(client, ZigbangRegion(
            name='가상동', lat=37.5, lng=127.03, legal_division_code='1168010100',
        ), conditions=ZigbangAptConditions(area_max_m2=0), limit=limit)
    assert calls == [(offset, 20) for offset in range(0, limit, 20)]
    assert result.returned == 0
    assert any('다시 채우지 않음' in note for note in result.notes)
    # 남은 매물은 --limit 을 늘리는 대신 next 로 이어 받는다
    assert result.has_more and result.next_position == {'code': '11680101', 'offset': limit}
    assert any(NEXT_HINT in note for note in result.notes)


# --- 없는 단지 실거래 · ○가 동 ------------------------------------------------------------

@pytest.mark.parametrize('danji_status,expected', [(404, 'NOT_FOUND'), (200, 0)])
def test_real_price_empty_pyeongs_checks_danji(danji_status: int, expected: str | int) -> None:
    # 실거래 API 는 없는 단지에도 빈 성공을 준다. 평형 정보가 비면 단지 정보로 있는지 확인한다
    # (평형이 아직 없는 새 단지는 0건, 없는 단지는 NOT_FOUND)
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/rt-prices'):
            return httpx.Response(200, json={'data': [], 'hasNext': False, 'areaInfos': {}})
        return httpx.Response(danji_status, json=load('danjis') if danji_status == 200 else {})

    with make_client(handler) as client:
        if expected == 'NOT_FOUND':
            with pytest.raises(JibsaError) as error:
                get_real_prices(client, 'apt-100')
            assert error.value.code == 'NOT_FOUND'
        else:
            assert get_real_prices(client, 'apt-100').returned == expected


def _search_items(*names: tuple[str, str]) -> dict:
    return {'success': True, 'items': [
        {'id': index + 1, 'type': 'address', 'name': name, 'description': f'서울특별시 {district} {name}',
         'lat': 37.54 + index * 0.001, 'lng': 127.05, '_source': {'local1': '서울시', 'local2': district, 'local3': name,
                                                                   '법정동코드': f'11200{index + 1:03d}00'}}
        for index, (name, district) in enumerate(names)
    ]}


@pytest.mark.parametrize('query,items,split,note', [
    # 같은 이름의 동 없이 '○가' 로만 나뉘면 합칠 동을 준다 (다른 구의 같은 이름은 빼고)
    ('성수동', [('성수동1가', '성동구'), ('성수동2가', '성동구'), ('성수동3가', '중구')], ['성수동1가', '성수동2가'], '성수동1가를 기준'),
    # 같은 이름의 동이 따로 있으면 그 동만 찾고 빠진 '○가' 를 알린다
    ('당산동', [('당산동', '영등포구'), ('당산동1가', '영등포구'), ('당산동2가', '영등포구')], [], '당산동1가·당산동2가는 따로'),
    ('역삼동', [('역삼동', '강남구')], [], None),
])
def test_ga_dong_scope(query: str, items: list[tuple[str, str]], split: list[str], note: str | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_items(*items))

    with make_client(handler) as client:
        _, split_note, regions = resolve_region_scope(client, query)
    assert [region.name for region in regions] == split
    assert (split_note is None) if note is None else (note in split_note)


@pytest.mark.parametrize('query,items,candidates', [
    # '○가' 로만 나뉜 동과 구가 있는 시는 직방 웹이 지역 목록을 따로 보여 줘, 합치지 않고 어느 곳인지 묻는다
    ('성수동', [('성수동1가', '성동구'), ('성수동2가', '성동구')], ['서울특별시 성동구 성수동1가', '서울특별시 성동구 성수동2가']),
])
def test_apt_region_divided_into_several_lists_is_ambiguous(query: str, items: list[tuple[str, str]], candidates: list[str]) -> None:
    from jibsa.providers.zigbang.service.apt import resolve_apt_region

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_search_items(*items))

    with make_client(handler) as client, pytest.raises(JibsaError) as caught:
        resolve_apt_region(client, query)
    assert caught.value.code == 'REGION_AMBIGUOUS'
    assert caught.value.details['candidates'] == candidates


def test_store_dong_codes_never_send_a_code_the_server_does_not_know() -> None:
    # 직방 상가는 모르는 법정동 코드(리 코드 등)에 에러 없이 전국 매물을 준다. 리는 읍·면 코드로 바꾸고 코드가 없으면 막는다
    from jibsa.providers.zigbang.service.store import store_region_codes

    ri = ZigbangRegion(name='가상리', lat=37.49, lng=127.49, legal_division_code='4183025021')
    codes, notes = store_region_codes([ri])
    assert codes == ['4183025000'] and any('읍·면 전체' in note for note in notes)
    with pytest.raises(JibsaError) as caught:
        store_region_codes([ZigbangRegion(name='가상역', lat=37.5, lng=127.03)])
    assert caught.value.code == 'REGION_NOT_SUPPORTED'


def test_stay_marker_order_breaks_ties_like_web_map_list() -> None:
    # 웹 지도 목록(sortStayMarkers): 추천순은 점수 높은 순·같으면 ID 큰 순, 가격순·최신순은 같은 값끼리 추천순 규칙
    from jibsa.providers.zigbang.api.response.stay import ZigbangStayMarkerModel
    from jibsa.providers.zigbang.service.stay import stay_marker_order

    markers = [
        ZigbangStayMarkerModel.model_validate(dict(id=item_id, lat=37.5, lng=127.03, weeklyPrice=price, reviewedAt=at, totalScore=score))
        for item_id, price, at, score in [
            (1, 30, '2026-11-01T00:00:00.000Z', 0.5),
            (2, 30, '2026-11-02T00:00:00.000Z', 0.9),
            (3, 20, '2026-11-02T00:00:00.000Z', 0.5),
        ]
    ]
    assert stay_marker_order(markers, 'recommended') == [2, 3, 1]
    assert stay_marker_order(markers, 'price') == [3, 2, 1]
    assert stay_marker_order(markers, 'newest') == [2, 3, 1]


def _station_items(*dongs: str) -> dict:
    return {'success': True, 'items': [
        {'id': index + 1, 'type': 'subway', 'name': '가상역', 'description': f'서울특별시 가상구 {dong}',
         'lat': 37.55 + index * 0.005, 'lng': 126.93}
        for index, dong in enumerate(dongs)
    ]}


@pytest.mark.parametrize('query,expected', [
    # 이름이 같은 역이 여러 곳이면 첫 역으로 찾지 않고 묻는다. 같은 구라 구 이름으로 못 갈라 동 이름을 붙이라고 알린다
    ('가상역', 'REGION_AMBIGUOUS'),
    # 직방은 동 이름을 붙여도 두 역을 다 준다. 붙인 낱말이 주소에 있는 후보가 하나면 그 역으로 찾는다
    ('둘째동 가상역', '서울특별시 가상구 둘째동'),
])
def test_same_name_station_asks_unless_query_picks_one(query: str, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_station_items('첫째동', '둘째동'))

    with make_client(handler) as client:
        if expected == 'REGION_AMBIGUOUS':
            with pytest.raises(JibsaError) as caught:
                resolve_region_scope(client, query)
            assert caught.value.code == expected and "'첫째동 가상역'" in caught.value.hint
        else:
            region, _, _ = resolve_region_scope(client, query)
            assert region.address == expected


# --- 역 주변 단지 -------------------------------------------------------------

def test_station_complexes_keep_view_count_order_and_add_distance() -> None:
    # 순서·수는 웹 주변단지 목록(/apt/danjis/ids, 조회수 순) 그대로다. 거리는 역 주변 단지 정보(거리순)에서 붙이고 다시 세우지
    # 않는다. 주변 단지 정보에 없는 단지는 빼지 않고 이름·거리를 모름으로 둔다
    requested: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        if request.url.path == '/v2/search':
            return httpx.Response(200, json=_station_items('가상동'))
        if request.url.path == '/apt/subways/1':
            return httpx.Response(200, json={'id': 1, 'name': '가상역', 'aptList': [
                {'id': 1001, 'name': '[가상] 가까운단지', '구주소': '서울시 가상구 가상동 000-1', 'household': '1,000세대', 'distanceNum': 100},
                {'id': 1003, 'name': '[가상] 먼단지', '구주소': '서울시 가상구 가상동 000-3', 'household': '세대수 모름', 'distanceNum': 300},
            ]})
        assert request.url.path == '/apt/danjis/ids'
        return httpx.Response(200, json={'count': 5, 'ids': [1003, 1001, 1009]})

    with make_client(handler) as client:
        result = search_station_complexes(client, '가상역', limit=3)

    # 순서·수를 주는 본 조회를 덤 조회(/apt/subways)보다 먼저 부른다
    assert [url.path for url in requested[1:]] == ['/apt/danjis/ids', '/apt/subways/1']
    assert dict(requested[1].params) == {
        'type': 'subway', 'id': '1', 'order': 'viewCount', 'limit': '3',
        'serviceType[0]': 'apt', 'serviceType[1]': 'offer', 'serviceType[2]': 'preOffer',
    }
    assert [(c.complex_id, c.name, c.households, c.distance_m) for c in result.complexes] == [
        ('apt-1003', '[가상] 먼단지', None, 300),
        ('apt-1001', '[가상] 가까운단지', 1000, 100),
        ('apt-1009', None, None, None),
    ]
    assert result.complexes[1].address == '서울특별시 가상구 가상동 000-1'
    assert (result.total, result.returned, result.has_more) == (5, 3, True)
