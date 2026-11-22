import json
from datetime import date
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
from jibsa.core.listing import (
    NEXT_HINT,
    UPDATE_MAYBE_NEEDED,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.apt import (
    ZigbangLocalsItemCatalogsRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.room.search import (
    ZigbangItemsVillasV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.apt import (
    ZigbangAptManageCostModel,
    ZigbangItemCatalogsItemsResponseModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangDanjiRankModel,
    ZigbangItemCatalogModel,
    ZigbangItemsListV1ResponseModel,
    ZigbangItemSummaryModel,
)
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangDanjiRoomTypeModel,
    ZigbangDanjisRoomTypesResponseModel,
)
from jibsa.providers.zigbang.api.response.complex.search import ZigbangDanjiCardModel
from jibsa.providers.zigbang.api.response.complex.trend import (
    ZigbangDanjisPriceChartRelatedDanjisResponseModel,
    ZigbangDanjisPriceChartResponseModel,
    ZigbangDanjisRoomTypesPriceChartResponseModel,
)
from jibsa.providers.zigbang.api.response.local.info import ZigbangLocalPriceModel
from jibsa.providers.zigbang.api.response.room.base import (
    ZigbangItemsDetailV1ManageCostModel,
    ZigbangItemsDetailV1ResponseModel,
)
from jibsa.providers.zigbang.api.response.room.detail import (
    ZigbangBlsRtsV2ResponseModel,
    ZigbangBlsSchoolZonesV1ResponseModel,
)
from jibsa.providers.zigbang.api.response.stay.detail import (
    ZigbangGuestItemsResponseModel,
)
from jibsa.providers.zigbang.api.response.stay.search import ZigbangStayMarkerModel
from jibsa.providers.zigbang.api.response.store import (
    ZigbangStoreArticleStoresV2ResponseModel,
    ZigbangStoreArticleStoreV2ResponseModel,
    ZigbangStoreSummaryModel,
)
from jibsa.providers.zigbang.service.apt import (
    ZigbangAptConditions,
    apt_item_to_listing,
    search_apt_listings,
)
from jibsa.providers.zigbang.service.common.apt import catalog_to_listing
from jibsa.providers.zigbang.service.common.base import (
    ZigbangAptRegion,
    ZigbangRegion,
    failure_update_hint,
    sent_or_none,
)
from jibsa.providers.zigbang.service.common.room import (
    ZigbangRoomConditions,
    summary_to_listing,
)
from jibsa.providers.zigbang.service.complex.detail import (
    complex_rank_of,
    pyeong_of,
)
from jibsa.providers.zigbang.service.complex.search import (
    complex_order_of,
    distance_m_of,
    place_complex_of,
    search_place_complexes,
)
from jibsa.providers.zigbang.service.complex.trend import (
    get_price_trend,
    get_pyeong_price_trend,
)
from jibsa.providers.zigbang.service.listing import get_any_listing
from jibsa.providers.zigbang.service.local import (
    info as region_info,
)
from jibsa.providers.zigbang.service.real_price import get_real_prices
from jibsa.providers.zigbang.service.region import (
    divided_region_error,
    region_scope_items,
    resolve_apt_region,
    resolve_region_scope,
    resolve_school,
    resolve_station,
    search_regions,
    settled_item,
)
from jibsa.providers.zigbang.service.room.detail import (
    building_real_trades,
    building_schools,
    detail_to_listing,
)
from jibsa.providers.zigbang.service.room.search import search_listings
from jibsa.providers.zigbang.service.stay.detail import (
    STAY_REFUND_RULES,
    ZigbangStayListingDetail,
    _stay_host_others,
    stay_detail_to_listing,
)
from jibsa.providers.zigbang.service.stay.search import stay_marker_order
from jibsa.providers.zigbang.service.store import (
    STORE_VACANT_SECTION,
    ZigbangStoreConditions,
    ZigbangStoreSearchResult,
    search_store_listings,
    store_detail_to_listing,
    store_summary_to_listing,
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
    from jibsa.providers.zigbang.service.room.detail import get_listing

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
    from jibsa.providers.zigbang.service.room.detail import get_listing

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
    # 아파트 매물은 웹 아파트 화면처럼 아파트 상세 하나로 만든다. 주거 상세의 404 를 내려간 매물로 읽으면
    # 살아 있는 아파트 매물이 모두 LISTING_UNAVAILABLE 이 된다 (2026-11-14 실측)
    requested: list[str] = []
    handler = apt_detail_handler(httpx.Response(200, json=load('item_catalogs_items')), requested)
    with make_client(handler) as client:
        dumped = get_any_listing(client, '1000001').model_dump()
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
        get_any_listing(client, '1000001')


def test_apt_listing_kind_from_item_type() -> None:
    from jibsa.providers.zigbang.service.common.apt import ZigbangAptListing
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
    apt = ZigbangItemCatalogsItemsResponseModel.model_validate(load('item_catalogs_items')).item
    apt.manage_cost = ZigbangAptManageCostModel(type='unconfirmed')
    detail = apt_item_to_listing(apt, 'zigbang')
    assert detail.manage_cost_manwon is None and detail.manage_cost_includes is None
    assert detail.room_count == 3


def test_apt_line_and_detail_carry_pyeong_and_web_only_fields() -> None:
    # 목록 줄은 평형 ID·이름(평 기준)을 붙이고, 확인일·실매물·위반 건축물은 상세·묶음에만 있다
    card = load('locals_item_catalogs')['list'][0]
    line = catalog_to_listing(ZigbangItemCatalogModel.model_validate(card), '서울특별시')
    assert line is not None and (line.pyeong_id, line.pyeong_name) == (8001, '33A')
    dumped = line.model_dump()
    assert 'confirmed_at' not in dumped and 'actual_listing_checked' not in dumped

    # 직방 매물: 값이 그대로 나오고 확인 시각은 한국 날짜가 된다
    item = load('item_catalogs_items')['item']
    item.update({
        'roomTypeInfo': {'danjiRoomTypeId': 8001, 'roomTypeTitle': {'m2': '110A', 'p': '33A'}, 'floorPlanImageUrl': 'plan.png'},
        'effectivenessUpdatedAt': '2026-01-02T23:59:59+09:00', 'isActualItemChecked': True, 'hasViolations': False,
    })
    detail = apt_item_to_listing(ZigbangItemCatalogsItemsResponseModel.model_validate({'item': item}).item, 'zigbang').model_dump()
    assert (detail['pyeong_id'], detail['pyeong_name']) == (8001, '33A')
    assert detail['confirmed_at'] == '2026-01-02' and detail['actual_listing_checked'] is True
    assert detail['non_compliant_building'] is False and detail['residence_type'] == item['realType']
    assert 'plan.png' not in json.dumps(detail, ensure_ascii=False)

    # 제휴 매물은 위반 건축물·중개대상물 종류 키가 없어 모름(null), 평형 정보가 없어도 키는 나온다
    for key in ('hasViolations', 'realType', 'roomTypeInfo', 'effectivenessUpdatedAt', 'isActualItemChecked'):
        item.pop(key)
    partner = apt_item_to_listing(ZigbangItemCatalogsItemsResponseModel.model_validate({'item': item}).item, 'coalition').model_dump()
    for key in ('non_compliant_building', 'residence_type', 'pyeong_id', 'pyeong_name', 'confirmed_at', 'actual_listing_checked'):
        assert key in partner and partner[key] is None


def test_non_apt_detail_omits_apt_only_keys_and_has_web_checks() -> None:
    dumped = detail_to_listing(ZigbangItemsDetailV1ResponseModel.model_validate(load('items_detail_v1'))).model_dump()
    # 평형·찜 수·공급면적·매물 종류는 아파트에만 있어 키가 없다
    for key in ('complex_name', 'pyeong_id', 'pyeong_name', 'zzim_count', 'supply_area_m2', 'listing_kind'):
        assert key not in dumped
    # 확인일·실매물·위반 건축물은 원룸·빌라·오피스텔 상세에도 나온다 (값은 모를 수 있어 null)
    for key in ('confirmed_at', 'actual_listing_checked', 'non_compliant_building'):
        assert key in dumped


def test_apt_no_new_sale_sends_false_on_every_page() -> None:
    seen: list[dict[str, str]] = []
    fixture = load('locals_item_catalogs')

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=dict(fixture, count=100, list=[fixture['list'][0]] * int(request.url.params['limit'])))

    region = ZigbangAptRegion(name='가상동', lat=37.5, lng=127.03, legal_division_code='1168010100')
    with make_client(handler) as client:
        first = search_apt_listings(client, region, conditions=ZigbangAptConditions(exclude_new_sale=True), limit=40)
        search_apt_listings(client, region, conditions=ZigbangAptConditions(exclude_new_sale=True), limit=20, start=first.next_position)
        assert len(seen) == 3 and all(params['includeOfferItem'] == 'false' for params in seen)
        seen.clear()
        search_apt_listings(client, region, limit=20)
        assert len(seen) == 1 and 'includeOfferItem' not in seen[0]


# --- 상가 --------------------------------------------------------------------


def test_store_detail_drops_contact_and_photos() -> None:
    response = ZigbangStoreArticleStoreV2ResponseModel.model_validate(load('store_article_store_v2'))
    detail = store_detail_to_listing(response).model_dump()
    assert detail['id'] == 'store-4000001'
    assert detail['building_floor'] == '5' and detail['elevator'] is True
    assert detail['nearby_subways'] == ['가상역 (2호선)']
    text = json.dumps(detail, ensure_ascii=False)
    assert '010-0000-0000' not in text and 'photo.jpg' not in text and '가상 설명' not in text


@pytest.mark.parametrize('business, key_money, has_key', [
    ('사무실', None, False),
    ('사무실', 0, True),
    ('카페/커피', None, True),
])
def test_store_office_key_money_key_dropped_only_when_missing(business: str, key_money: int | None, has_key: bool) -> None:
    summary = ZigbangStoreSummaryModel.model_validate(load('store_article_stores_list_v2')[0])
    summary = summary.model_copy(update={'business': business, 'key_money': key_money})
    listing = store_summary_to_listing(summary).model_dump(mode='json')
    assert ('key_money_manwon' in listing) is has_key
    if has_key:
        assert listing['key_money_manwon'] == key_money
    data = load('store_article_store_v2')
    data['item']['업종'] = business
    data['item']['권리금액'] = key_money
    detail = store_detail_to_listing(ZigbangStoreArticleStoreV2ResponseModel.model_validate(data)).model_dump(mode='json')
    assert ('key_money_manwon' in detail) is has_key


@pytest.mark.parametrize('sales_title, rent, expected', [
    ('월세', 0, '월세'),
    ('가상값', 200, '월세'),
])
def test_store_trade_follows_sales_title_then_rent(sales_title: str | None, rent: int, expected: str) -> None:
    data = load('store_article_store_v2')
    data['item']['sales_title'] = sales_title
    data['item']['월세금액'] = rent
    detail = store_detail_to_listing(ZigbangStoreArticleStoreV2ResponseModel.model_validate(data)).model_dump(mode='json')
    assert detail['trade_type'] == expected
    if expected == '월세':
        assert detail['rent_manwon'] == rent


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


def stay_output(**changes) -> dict:
    data = load('guest_items')
    data.update(changes)
    detail = ZigbangGuestItemsResponseModel.model_validate(data)
    return stay_detail_to_listing(detail).model_dump(mode='json')


def test_stay_pet_option_moves_to_pet_allowed() -> None:
    pet = {'category': 'PET_FRIENDLY', 'optionName': 'PET_ALLOWED'}
    options = [{'category': 'BASIC', 'optionName': 'WIFI'}, pet, {'category': 'BASIC', 'optionName': 'TV'}]
    allowed = stay_output(itemOptions=options, petCleaningFee=0)
    assert allowed['options'] == ['와이파이', 'TV']
    assert allowed['pet_allowed'] is True
    assert allowed['pet_cleaning_fee_manwon'] == 0
    assert allowed['pet_cleaning_fee_manwon'] is not None
    denied = stay_output(itemOptions=options[:1] + options[2:], petCleaningFee=0)
    assert denied['pet_allowed'] is False
    assert 'pet_cleaning_fee_manwon' not in denied
    # 반려동물 가능인데 청소비를 주지 않으면 모름(null)
    unknown = stay_output(itemOptions=[pet])
    assert unknown['pet_cleaning_fee_manwon'] is None
    assert unknown['options'] == []


def test_stay_pet_fields_without_option_list_or_with_fee_when_denied() -> None:
    data = load('guest_items')
    data.pop('itemOptions', None)
    data['petCleaningFee'] = 0
    unknown = stay_detail_to_listing(ZigbangGuestItemsResponseModel.model_validate(data)).model_dump(mode='json')
    # 직방이 옵션 목록을 주지 않으면 모름(null). 청소비는 키가 남는다
    assert unknown['pet_allowed'] is None
    assert unknown['options'] is None
    assert unknown['pet_cleaning_fee_manwon'] is None
    # 동반 불가여도 웹처럼 추가 청소비가 0 보다 크면 낸다
    denied = stay_output(itemOptions=[{'category': 'BASIC', 'optionName': 'WIFI'}], petCleaningFee=50000)
    assert denied['pet_allowed'] is False
    assert denied['pet_cleaning_fee_manwon'] == 5


def test_stay_parking_count_is_not_applicable_when_unavailable() -> None:
    unavailable = stay_output(parkingType='UNAVAILABLE', parkingCount=None)
    assert 'parking_count' not in unavailable
    assert 'parking_method' not in unavailable
    unknown = stay_output(parkingType='LIMITED')
    assert unknown['parking_count'] is None
    assert unknown['parking_method'] is None
    known = stay_output(parkingType='AVAILABLE', parkingCount=2, parkingMethod='MECHANICAL')
    assert known['parking_count'] == 2
    assert known['parking_method'] == '기계식'


def test_stay_refund_rules_follow_policy_code() -> None:
    strict = stay_output(refundPolicy='STRICT')
    assert [(rule['when'], rule['penalty']) for rule in strict['refund_rules']] == list(STAY_REFUND_RULES['STRICT'])
    assert stay_output(refundPolicy='NEW_POLICY')['refund_rules'] is None
    assert stay_output(refundPolicy=None)['refund_rules'] is None


def test_stay_unavailable_periods_empty_schedule_is_empty_list() -> None:
    assert stay_output(schedules=[])['unavailable_periods'] == []
    blocked = {'scheduleType': 'BLOCKED', 'startDate': '2099-01-01', 'endDate': '2099-01-10'}
    assert stay_output(schedules=[blocked])['unavailable_periods'] == [
        {'start': '2099-01-01', 'end': '2099-01-10', 'kind': '막힘'},
    ]
    assert stay_output()['unavailable_periods'] is None


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


def _store_vacant_search(businesses: list[str] | None) -> tuple[ZigbangStoreSearchResult, list[dict]]:
    base = load('store_article_stores_list_v2')[0]
    # 공실 묶음이 응답에서 앞에 와도 업종 묶음 뒤에 이어지고, 두 묶음에 같은 ID(3)가 있으면 앞 것만 둔다
    pins = [
        {'title': STORE_VACANT_SECTION, 'item_locations': [
            {'item_id': item_id, 'lat': 37.5, 'lng': 127.03} for item_id in (3, 4)
        ]},
        {'title': '이 지역 카페 추천 상가', 'item_locations': [
            {'item_id': item_id, 'lat': 37.5, 'lng': 127.03} for item_id in (1, 2, 3)
        ]},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/stores/list'):
            ids = json.loads(request.content)['item_ids']
            return httpx.Response(200, json=[{**base, 'item_id': item_id} for item_id in ids])
        return httpx.Response(200, json=pins)

    region = ZigbangRegion(name='center', lat=37.5, lng=127.03)
    with make_client(handler) as client:
        result = search_store_listings(client, region, conditions=ZigbangStoreConditions(businesses=businesses or []))
    return result, [item.model_dump() for item in result.listings]


def test_store_business_search_appends_vacant_section_after_business_items() -> None:
    result, listings = _store_vacant_search(['카페/커피'])
    assert [item['id'] for item in listings] == ['store-1', 'store-2', 'store-3', 'store-4']
    assert [item['vacant_section'] for item in listings] == [False, False, False, True]
    assert result.total == 4
    assert any('vacant_section true' in note for note in result.notes)


def test_store_search_without_business_still_marks_vacant_section() -> None:
    # 업종 조건 없이도 공실 묶음이 오면 표시 없이 섞지 않는다 (실측으로는 업종 조건이 없으면 공실 묶음이 빈다)
    result, listings = _store_vacant_search(None)
    assert [item['vacant_section'] for item in listings] == [False, False, False, True]
    assert any('일반 매물 3건' in note for note in result.notes)


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
        result = search_apt_listings(client, ZigbangAptRegion(
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
    from jibsa.providers.zigbang.service.room.detail import get_listing
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
        result = search_apt_listings(client, ZigbangAptRegion(
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


def _tx(deal_type: str, **extra) -> dict:
    return {
        'rtId': 1, 'rtDealDate': '26. 1. 2', 'rtFloor': 3, 'rtArea': '84.0', 'rtDealType': deal_type,
        'rtPrice': 10000, 'dongName': None, 'areaInfos': [{'m2': '111Z', 'p': '99Z'}], 'isNew': False,
        'isCancellation': False, **extra,
    }


def _real_prices(transactions: list[dict], trade_type: str, requests: list | None = None) -> dict:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        pyeongs = {'1': [{'m2': '111Z', 'p': '99Z'}]}
        return httpx.Response(200, json={'data': transactions, 'hasNext': False, 'areaInfos': pyeongs})

    with make_client(handler) as client:
        return json.loads(get_real_prices(client, 'apt-100', trade_type=trade_type).model_dump_json())


def test_real_price_sale_registered_null_without_mark() -> None:
    # 등기 표시가 없으면 false 가 아니라 null (2023년 전 계약인지 등기 전인지 모른다), 신고가는 표시가 없으면 false
    plain, marked = _real_prices([
        _tx('sales', dongName='000', pynPrice=1111),
        _tx('sales', isRegistration=True, isNewHighest=True),
    ], '매매')['transactions']
    assert plain['registered'] is None
    assert plain['new_high'] is False
    assert plain['new_low'] is False
    assert plain['dong'] == '000'
    assert plain['price_per_pyeong_manwon'] == 1111
    assert marked['registered'] is True
    assert marked['new_high'] is True
    # 동·평당가는 직방이 안 줘도 모름(null) 으로 키가 남는다
    assert marked['dong'] is None
    assert marked['price_per_pyeong_manwon'] is None
    assert 'jeonse_ratio' not in plain
    assert 'offer_price_diff_manwon' not in plain


def test_real_price_monthly_rent_has_no_sale_only_keys() -> None:
    rent = _real_prices([_tx('rent', rtPriceRent=10, dongName='000', pynPrice=1)], '월세')['transactions'][0]
    for key in ('registered', 'new_high', 'new_low', 'price_per_pyeong_manwon', 'jeonse_ratio'):
        assert key not in rent
    # 동은 웹이 전월세에도 그려 모든 거래에 낸다 (직방이 주지 않으면 null)
    assert rent['dong'] == '000'
    charter = _real_prices([_tx('charter')], '전세')['transactions'][0]
    assert charter['new_high'] is False
    assert charter['dong'] is None
    assert 'registered' not in charter


def test_real_price_jeonse_ratio_only_for_charter_with_value() -> None:
    with_ratio, without = _real_prices([_tx('charter', charterRate=0.123456789), _tx('charter')], '전세')['transactions']
    assert with_ratio['jeonse_ratio'] == 0.123456789
    assert 'jeonse_ratio' not in without
    # 분양가 대비 차액은 0 이어도 값이 있으면 낸다
    sale = _real_prices([_tx('sales', offerPriceDiff=0)], '매매')['transactions'][0]
    assert sale['offer_price_diff_manwon'] == 0


def test_real_price_all_requests_deal_type_all_and_keeps_order() -> None:
    requests: list[httpx.Request] = []
    result = _real_prices([_tx('rent', rtPriceRent=10), _tx('sales'), _tx('charter')], '전체', requests)
    assert [request.url.params['dealType'] for request in requests if request.url.path.endswith('/rt-prices')] == ['all']
    assert result['trade_type'] == '전체'
    assert [transaction['trade_type'] for transaction in result['transactions']] == ['월세', '매매', '전세']
    # 거래마다 유형이 맨 앞에 오고 유형별 필드 규칙은 그대로다
    assert list(result['transactions'][0])[0] == 'trade_type'
    assert 'new_high' not in result['transactions'][0]
    assert 'new_high' in result['transactions'][1]
    # 매매·전세·월세 조회는 거래마다 유형을 내지 않는다
    assert 'trade_type' not in _real_prices([_tx('sales')], '매매')['transactions'][0]


def test_real_price_all_drops_unknown_deal_type_and_notes_it() -> None:
    # 모르는 거래 유형(낯선 값·null)은 빼고 [제외] 로 알린다 (limit 로 잘릴 자리의 거래는 세지 않는다)
    def handler(request: httpx.Request) -> httpx.Response:
        transactions = [_tx('sales'), _tx('lease'), _tx(None), _tx('charter')]
        return httpx.Response(200, json={'data': transactions, 'hasNext': False, 'areaInfos': {'1': [{'m2': '111Z', 'p': '99Z'}]}})

    with make_client(handler) as client:
        result = get_real_prices(client, 'apt-100', trade_type='전체')
        capped = get_real_prices(client, 'apt-100', trade_type='전체', limit=1)
    assert [transaction.trade_type for transaction in result.transactions] == ['매매', '전세']
    assert '[제외] 거래 유형을 읽지 못한 실거래 2건을 뺐습니다. jibsa 업데이트가 필요할 수 있습니다' in result.notes
    assert not any(text.startswith('[제외]') for text in capped.notes)
    # 분양권은 차액을 안 줘도 키를 null 로 두고, 입주권은 값이 없으면 키를 뺀다
    presale = _real_prices([_tx('sales', offerType='분양권'), _tx('sales', offerType='입주권')], '매매')['transactions']
    assert presale[0]['offer_price_diff_manwon'] is None
    assert 'offer_price_diff_manwon' not in presale[1]


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


def test_same_name_station_without_coordinates_still_counts_as_a_candidate() -> None:
    # 좌표 없는 같은 이름 역을 먼저 버리면 남은 한 곳을 묻지 않고 고른다
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _station_items('첫째동', '둘째동')
        del payload['items'][1]['lat'], payload['items'][1]['lng']
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        with pytest.raises(JibsaError) as caught:
            resolve_station(client, '가상역')
    assert caught.value.code == 'REGION_AMBIGUOUS'


def test_chosen_region_without_coordinates_is_reported_not_skipped() -> None:
    # 고른 곳에 좌표가 없으면 다른 후보로 넘어가거나 좌표를 채우지 않고 알린다
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _search_items(('가상동', '가상구'))
        del payload['items'][0]['lat'], payload['items'][0]['lng']
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        with pytest.raises(JibsaError) as caught:
            resolve_region_scope(client, '가상동')
    assert caught.value.code == 'UPSTREAM_ERROR' and "'가상동'" in caught.value.message


def test_apt_region_and_complex_places_do_not_need_coordinates() -> None:
    # 아파트 동·구와 search complexes 의 동·역은 법정동 코드·역 ID·이름·주소만 쓰므로 직방이 좌표를 주지 않아도 찾는다.
    # 좌표를 쓰는 검색 중심(room·store·stay)은 위 테스트처럼 그대로 UPSTREAM_ERROR 다
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/v2/search':
            payload = _station_items('가상동') if request.url.params['q'] == '가상역' else _search_items(('가상동', '가상구'))
            for item in payload['items']:
                del item['lat'], item['lng']
            return httpx.Response(200, json=payload)
        if request.url.path == '/apt/danjis/ids':
            return httpx.Response(200, json={'count': 1, 'ids': [1001]})
        if request.url.path == '/apt/subways/1':
            return httpx.Response(200, json={'id': 1, 'name': '가상역', 'aptList': []})
        assert request.url.path == '/apt/danjis/details'
        return httpx.Response(200, json={'apts': []})

    with make_client(handler) as client:
        region, _ = resolve_apt_region(client, '가상동')
        dong = search_place_complexes(client, '가상동', limit=1)
        station = search_place_complexes(client, '가상역', limit=1)
        with pytest.raises(JibsaError) as caught:
            resolve_region_scope(client, '가상동')
    assert region.model_dump() == {
        'name': '가상동', 'address': '서울특별시 가상구 가상동', 'lat': None, 'lng': None, 'legal_division_code': '1120000100',
    }
    assert [(result.place, result.place_type) for result in (dong, station)] == [('가상동', '동'), ('가상역', '역')]
    assert caught.value.code == 'UPSTREAM_ERROR'


def test_divided_dongs_are_decided_from_search_results_even_without_coordinates() -> None:
    # 어느 동인지 묻기(단기임대)는 좌표를 쓰지 않으므로, 동 하나에 좌표가 없어도 지역으로 바꾸기 전에 후보를 정해 묻는다
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _search_items(('성수동1가', '성동구'), ('성수동2가', '성동구'))
        del payload['items'][0]['lat'], payload['items'][0]['lng']
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        items = search_regions(client, '성수동')
    best, split_items = region_scope_items('성수동', items)
    assert (best.name, [item.name for item in split_items]) == ('성수동1가', ['성수동1가', '성수동2가'])
    error = divided_region_error('성수동', split_items)
    assert error.details['candidates'] == ['서울특별시 성동구 성수동1가', '서울특별시 성동구 성수동2가']


def test_duplicate_result_of_the_same_place_picks_the_one_with_coordinates() -> None:
    # 직방이 이름·종류·주소가 같은 결과를 둘 주면 같은 곳이다. 첫 결과에만 좌표가 없으면 좌표 있는 쪽을 고른다
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _search_items(('가상동', '가상구'), ('가상동', '가상구'))
        del payload['items'][0]['lat'], payload['items'][0]['lng']
        return httpx.Response(200, json=payload)

    with make_client(handler) as client:
        items = search_regions(client, '가상동')
    chosen = settled_item('가상동', items, items[0])
    assert (chosen.id, chosen.lat) == (2, items[1].lat) and chosen.lat is not None


# --- 역·학교·동·구 주변 단지 (search complexes) --------------------------------

def test_station_complexes_keep_view_count_order_and_add_distance_and_card() -> None:
    # 순서·수는 웹 주변단지 목록(/apt/danjis/ids, 조회수 순) 그대로다. 이름·주소·세대수·거리는 역 주변 단지 정보(거리순)에서, 둘째 줄은
    # 단지 카드(/apt/danjis/details)에서 붙이고 다시 세우지 않는다. 두 곳에 없는 단지는 빼지 않고 값을 모름으로 둔다
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
        if request.url.path == '/apt/danjis/details':
            return httpx.Response(200, json={'apts': [
                {'id': 1003, 'name': '[가상] 먼단지', 'desc1': '가상구 가상동 · 500세대', 'desc2': '가상동 2위 · 가상구 2위'},
                {'id': 1001, 'name': '[가상] 가까운단지', 'desc1': '가상구 가상동 · 1,000세대', 'desc2': '가상동 1위 · 가상구 1위'},
            ]})
        assert request.url.path == '/apt/danjis/ids'
        return httpx.Response(200, json={'count': 5, 'ids': [1003, 1001, 1009]})

    with make_client(handler) as client:
        result = search_place_complexes(client, '가상역', limit=3)

    # 순서·수를 주는 본 조회를 덤 조회(/apt/subways, /apt/danjis/details)보다 먼저 부른다
    assert [url.path for url in requested[1:]] == ['/apt/danjis/ids', '/apt/subways/1', '/apt/danjis/details']
    assert dict(requested[1].params) == {
        'type': 'subway', 'id': '1', 'order': 'viewCount', 'limit': '3',
        'serviceType[0]': 'apt', 'serviceType[1]': 'offer', 'serviceType[2]': 'preOffer',
    }
    assert (result.place, result.place_type, result.place_address) == ('가상역', '역', '서울특별시 가상구 가상동')
    assert [(c.complex_id, c.name, c.households, c.distance_m, c.highlight) for c in result.complexes] == [
        ('apt-1003', '[가상] 먼단지', None, 300, '가상동 2위 · 가상구 2위'),
        ('apt-1001', '[가상] 가까운단지', 1000, 100, '가상동 1위 · 가상구 1위'),
        ('apt-1009', None, None, None, None),
    ]
    assert result.complexes[1].address == '서울특별시 가상구 가상동 000-1'
    assert (result.total, result.returned, result.has_more) == (5, 3, True)


@pytest.mark.parametrize('text,expected', [
    ('462m', 462),
    ('1.1km', 1100),
    # 읽지 못하면 모름 (웹 학교 응답에는 숫자 거리가 없다)
    ('', None),
    ('가까움', None),
    (None, None),
])
def test_school_distance_text_becomes_meters(text: str | None, expected: int | None) -> None:
    assert distance_m_of(text) == expected


def test_region_complexes_only_take_newest_order_and_drop_distance_key() -> None:
    # 웹 지역 화면에는 최근입주 목록뿐이라 동·구는 다른 순서를 받지 않고, 지역을 찾기 전에 막는다. 기본도 동·구만 최근입주다
    with pytest.raises(JibsaError) as caught:
        complex_order_of('동·구', '인기')
    assert caught.value.code == 'INVALID_ARGUMENT'
    assert complex_order_of('동·구', None) == complex_order_of('동·구', '최근입주') == '최근입주'
    assert complex_order_of('역', None) == complex_order_of('학교', None) == '인기'
    # 동·구 줄에는 거리가 없다 (해당 없음이라 키 삭제). 이름·주소·세대수는 카드 첫째 줄에서 온다
    card = ZigbangDanjiCardModel.model_validate(
        {'id': 88494, 'name': '[가상] 단지', 'desc1': '송파구 가락동 · 1,179세대', 'desc2': '2026. 1 입주'},
    )
    region_line = place_complex_of(88494, '동', None, card).model_dump()
    assert 'distance_m' not in region_line
    assert (region_line['name'], region_line['address'], region_line['households'], region_line['highlight']) == (
        '[가상] 단지', '송파구 가락동', 1179, '2026. 1 입주',
    )
    # 역 줄은 주변 단지 정보를 못 받아도 distance_m 이 모름(null)으로 남는다
    assert place_complex_of(88494, '역', None, card).model_dump()['distance_m'] is None


def test_complexes_stop_when_upstream_gives_count_without_ids() -> None:
    # 단지 수만 주고 목록이 없으면 '앞 0곳입니다. --limit 을 늘리세요' 같은 소용없는 안내를 내지 않고 멈춘다. 덤 조회도 부르지 않는다
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/v2/search':
            return httpx.Response(200, json=_station_items('가상동'))
        assert request.url.path == '/apt/danjis/ids'
        return httpx.Response(200, json={'count': 5, 'ids': None})

    with make_client(handler) as client:
        with pytest.raises(JibsaError) as caught:
            search_place_complexes(client, '가상역', limit=3)
    assert caught.value.code == 'UPSTREAM_ERROR' and UPDATE_MAYBE_NEEDED in (caught.value.hint or '')


def test_same_name_school_without_coordinates_still_counts_as_a_candidate() -> None:
    # search complexes 의 학교 경로는 학교 ID 만 쓰고 좌표는 쓰지 않는다. 좌표 없는 같은 이름 학교를 먼저 버리면 남은 한 곳을 묻지 않고 고른다
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'success': True, 'items': [
            {'id': 1, 'type': 'school', 'name': '가상초등학교', 'description': '서울특별시 가상구 가상동', 'lat': 37.5, 'lng': 127.0},
            {'id': 2, 'type': 'school', 'name': '가상초등학교', 'description': '부산광역시 가상구 가상동'},
        ]})

    with make_client(handler) as client:
        with pytest.raises(JibsaError) as caught:
            resolve_school(client, '가상초등학교')
    assert caught.value.code == 'REGION_AMBIGUOUS'


# --- 단지 정보 (complex) --------------------------------------------------------

def test_complex_rank_minus_one_and_zero_prices_are_unknown() -> None:
    both = {'local2': {'name': '송파구', 'rank': 1, 'total': 10}, 'local3': {'name': '가락동', 'rank': 1, 'total': 3}}
    # -1 은 웹이 '순위 없음' 으로 그리는 값이다
    rank = complex_rank_of(ZigbangDanjiRankModel.model_validate({**both, 'viewCountRank': 7, 'tradePriceRank': -1}))
    assert rank is not None and (rank.region, rank.price_rank, rank.popularity_rank) == ('가락동', None, 7)
    # 웹은 구·동 순위 중 하나라도 없으면 절을 그리지 않는다
    assert complex_rank_of(ZigbangDanjiRankModel.model_validate({'local3': both['local3'], 'viewCountRank': 7})) is None
    # 0 인 시세·관리비는 웹이 '시세없음'·'-' 로 그리므로 모름(null)이다. 빠진 평형이면 새 값이 모두 null 이다
    detail = ZigbangDanjiRoomTypeModel.model_validate({
        'id': 1, '총세대수': 731, '현관구조': '', 'manage_cost': {'관리비': 0, '여름관리비': 0, '겨울관리비': 45},
        'sales_price': {'min': 0, 'per_area': 10533}, 'rent_price': {'min': 145000, 'per_area': 0}, '거래가능시점': '20160601',
    })
    pyeong = pyeong_of(ZigbangDanjiRoomTypeModel.model_validate({'id': 1}), detail).model_dump()
    assert (pyeong['manage_cost_manwon'], pyeong['manage_cost_summer_manwon'], pyeong['manage_cost_winter_manwon']) == (None, None, 45)
    assert (pyeong['estimated_sale_price_manwon'], pyeong['estimated_sale_price_per_pyeong_manwon']) == (None, 10533)
    assert (pyeong['estimated_jeonse_price_manwon'], pyeong['estimated_jeonse_price_per_pyeong_manwon']) == (145000, None)
    assert (pyeong['households'], pyeong['entrance_type'], pyeong['resale_available_from']) == (731, None, '2016-06-01')
    assert pyeong_of(ZigbangDanjiRoomTypeModel.model_validate({'id': 1}), None).model_dump()['households'] is None


# --- 원룸·빌라·오피스텔 상세 보강 -----------------------------------------------

def _room_detail(**item_extra: object) -> ZigbangItemsDetailV1ResponseModel:
    item: dict = {
        'id': 1000001, 'status': 'open', 'salesType': '월세', 'serviceType': '원룸', 'title': '[가상] 000-N',
        'address': {'pnu': '1111111111111111111'}, 'residence': {'sizeM2': 20.0},
    }
    return ZigbangItemsDetailV1ResponseModel.model_validate({'item': {**item, **item_extra}})


def test_nearby_facilities_follow_web_order_and_minutes() -> None:
    # 웹은 걸리는 시간 순(같으면 응답 순서)으로 세워 도보를 먼저, 그다음 차를 그린다. 이동 수단을 모르는 값('walk')은 도보다.
    # 분은 Math.round((초||1)/60)||1 이다: 150초 → 3분 (Python round 는 2.5 를 2 로 보낸다), 30초 → 1분, 0초 → 1분
    pois = [
        {'exists': True, 'poiType': '대형마트', 'distance': 900, 'transport': 'car', 'timeTaken': 60},
        {'exists': True, 'poiType': '약국', 'distance': 200, 'transport': 'foot', 'timeTaken': 150},
        {'exists': False, 'poiType': '지하철역'},
        {'exists': True, 'poiType': '카페', 'distance': 50, 'transport': 'foot', 'timeTaken': 90},
        {'exists': True, 'poiType': '편의점', 'distance': 10, 'transport': 'foot', 'timeTaken': 30},
        {'exists': True, 'poiType': '세탁소', 'distance': 5, 'transport': 'walk', 'timeTaken': 0},
    ]
    detail = detail_to_listing(_room_detail(neighborhoods={'nearbyPois': pois}))
    dumped = detail.model_dump(mode='json')['nearby_facilities']
    assert [(f['type'], f['minutes'], f['transport']) for f in dumped] == [
        ('세탁소', 1, '도보'), ('편의점', 1, '도보'), ('카페', 2, '도보'), ('약국', 3, '도보'), ('대형마트', 1, '차'),
    ]
    assert dumped[0]['distance_m'] == 5
    # 주변 정보가 없으면 모름, 있는데 가까운 시설이 없으면 빈 목록이고 배송 업체 키가 없으면 빈 목록이다
    assert detail_to_listing(_room_detail()).nearby_facilities is None
    empty = detail_to_listing(_room_detail(neighborhoods={'nearbyPois': [{'exists': False, 'poiType': '카페'}]}))
    assert empty.nearby_facilities == [] and empty.delivery_services == []


def test_badges_set_hug_lessor_and_actual_listing_checked() -> None:
    # 웹은 badges.includes('HUG')·includes('ITEM_VERIFICATION') 로 꼬리표를 붙인다 (ITEM_VERIFICATION_FAILED 는 아니다).
    # 배지 목록이 [] 면 false, 키가 없으면 모름이다. 목록 줄과 상세가 같은 값을 낸다
    cases = [
        (['HUG', 'ITEM_VERIFICATION'], True, True),
        (['ITEM_VERIFICATION_FAILED'], False, False),
        ([], False, False),
        (None, None, None),
    ]
    for badges, hug, verified in cases:
        detail = detail_to_listing(_room_detail(meta={'badges': badges} if badges is not None else {}))
        summary = {'item_id': 1000001, 'sales_type': '월세', 'service_type': '원룸', **({'badges': badges} if badges is not None else {})}
        line = summary_to_listing(ZigbangItemSummaryModel.model_validate(summary))
        assert (detail.hug_lessor, detail.actual_listing_checked) == (hug, verified)
        assert (line.hug_lessor, line.actual_listing_checked) == (hug, verified)

    # 웹 목록 카드는 itemSummaries[].badges 가 목록이면 그것을 읽는다 (items[].badges 에 없는 값이 올 수 있다). 목록이 아니면 그 칸을 모름으로 받아
    # (관리비를 잃지 않는다) items[].badges 를 읽고, 같은 매물이 itemSummaries 에 없어도 items[].badges 를 읽는다
    base = {'sales_type': '월세', 'service_type': '원룸'}
    response = ZigbangItemsListV1ResponseModel.model_validate({
        'items': [
            {'item_id': 1, **base, 'badges': []},
            {'item_id': 2, **base, 'badges': ['ITEM_VERIFICATION']},
            {'item_id': 3, **base, 'badges': ['ITEM_VERIFICATION']},
        ],
        'itemSummaries': [
            {'id': 1, 'fee': 0, 'badges': ['ITEM_VERIFICATION', 'RECOMMEND']},
            {'id': 2, 'fee': 10000, 'badges': 'ITEM_VERIFICATION'},
        ],
    })
    lines = [summary_to_listing(summary) for summary in response.items]
    assert [line.actual_listing_checked for line in lines] == [True, True, True]
    assert [line.manage_cost_manwon for line in lines] == [0, 1, None]


def test_null_values_in_room_detail_responses_are_unknown_not_errors() -> None:
    # 실제 응답으로 재현하지 못하는 null. 칸 하나 때문에 상세 전체(exists)나 덤 하나(rts·학교 목록)를 잃지 않는다.
    # exists 가 null 이면 시설이 없는 것으로 보고 그 시설만 뺀다
    detail = detail_to_listing(_room_detail(neighborhoods={'nearbyPois': [{'exists': None, 'poiType': '카페'}]}))
    assert detail.nearby_facilities == []
    # rts 가 null 이면 키가 없을 때처럼 모름이고, 학교 목록이 null 이면 그 학교급은 학교가 없다
    assert building_real_trades(ZigbangBlsRtsV2ResponseModel.model_validate({'rts': None})) is None
    assert building_schools(ZigbangBlsSchoolZonesV1ResponseModel.model_validate({'elementary': {'schools': None}})) == []


def test_building_trades_drop_price_keys_by_trade_type() -> None:
    rts = ZigbangBlsRtsV2ResponseModel.model_validate({'rts': [
        {'거래일': '2026-08-17', 'sales_type': '전세', '매매금액': None, '보증금액': 38000, '월세금액': 0, '전용면적': 53.72, 'floor': 4},
        {'거래일': '2026-08-17', 'sales_type': '매매', '매매금액': 58500, '보증금액': None, '월세금액': None, '전용면적': 53.72, 'floor': -1},
        {'거래일': '2026-01-15', 'sales_type': '월세', '매매금액': None, '보증금액': 34000, '월세금액': 55, '전용면적': 53.72, 'floor': 4},
        {'거래일': '2026-01-01', 'sales_type': '증여', '매매금액': 1, '보증금액': None, '월세금액': None, '전용면적': None, 'floor': None},
    ]})
    trades = building_real_trades(rts)
    assert trades is not None
    dumped = [trade.model_dump(mode='json') for trade in trades]
    assert 'price_manwon' not in dumped[0] and 'rent_manwon' not in dumped[0] and dumped[0]['deposit_manwon'] == 38000
    assert 'deposit_manwon' not in dumped[1] and 'rent_manwon' not in dumped[1] and dumped[1]['price_manwon'] == 58500
    assert dumped[1]['floor'] == '지하1'
    assert 'price_manwon' not in dumped[2] and dumped[2]['rent_manwon'] == 55
    # 모르는 거래 유형은 가격 키를 그대로 두고 유형을 모름(null)으로 둔다
    assert dumped[3]['trade_type'] is None and {'price_manwon', 'deposit_manwon', 'rent_manwon'} <= set(dumped[3])
    # 거래가 없는 필지는 빈 목록, rts 키가 없으면 모름
    assert building_real_trades(ZigbangBlsRtsV2ResponseModel.model_validate({'rts': []})) == []
    assert building_real_trades(ZigbangBlsRtsV2ResponseModel.model_validate({})) is None


# --- 단기임대 -------------------------------------------------------------------

def test_stay_marker_order_price_uses_weekly_total_price_then_recommended() -> None:
    # 웹 지도 목록 가격순은 weeklyTotalPrice(원)로 견준다. 같은 만원 단위(weeklyPrice 39) 안에서도 399,000원이 390,000원보다 뒤다
    # 합계가 없는 핀은 weeklyPrice × 10000 으로 견주고, 같은 값끼리는 추천순(점수 높은 순)이 남는다
    markers = [
        ZigbangStayMarkerModel.model_validate(dict(id=item_id, lat=37.5, lng=127.03, weeklyPrice=price, weeklyTotalPrice=total, totalScore=score))
        for item_id, price, total, score in [
            (1, 39, 399000, 0.9),
            (2, 39, 390000, 0.1),
            (3, 39, None, 0.5),
            (4, 40, 400000, 0.5),
        ]
    ]
    assert stay_marker_order(markers, 'price') == [3, 2, 1, 4]


def test_stay_host_others_without_items_is_unknown() -> None:
    # 실제 응답으로 재현하지 못하는 빈 응답. 목록 키가 없거나 null 이면 '다른 방 없음' 이 아니라 모름이다
    def run(body: dict) -> dict:
        with make_client(lambda request: httpx.Response(200, json=body)) as client:
            values, notes = _stay_host_others(client, 1, 2)
        assert notes == []
        return values

    assert run({}) == {'host_other_listings': None, 'host_other_listing_count': None}
    assert run({'items': None, 'totalCount': 3}) == {'host_other_listings': None, 'host_other_listing_count': 3}
    assert run({'items': []}) == {'host_other_listings': [], 'host_other_listing_count': 0}


def test_stay_host_others_skips_non_positive_host_id() -> None:
    # 요청 모델의 host_id 는 gt=0 이라 0 이하를 넣으면 ValidationError 로 '받지 못해' 로 잘못 알렸다. 부르지 않고 모름이다 (안내 없음)
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError('임대인 ID 가 0 이하면 요청을 보내지 않아야 한다')

    with make_client(refuse) as client:
        values, notes = _stay_host_others(client, 1, 0)
    assert values == {'host_other_listings': None, 'host_other_listing_count': None}
    assert notes == []


def test_failure_update_hint_only_for_response_format_errors() -> None:
    # 응답 형식 오류만 업데이트 문구로 매일 감시가 고장으로 잡게 하고, 연결 실패 같은 잠깐 실패는 붙이지 않는다
    with pytest.raises(ValidationError) as info:
        ZigbangItemsListV1ResponseModel.model_validate({'items': 'x'})
    assert UPDATE_MAYBE_NEEDED in failure_update_hint(info.value)
    assert failure_update_hint(httpx.ConnectError('연결 실패')) == ''


def test_stay_detail_drops_review_rating_when_no_reviews() -> None:
    base = dict(source='zigbang', id='stay-1', url='https://www.zigbang.com/stay/item/1', trade_type='단기임대', property_type='원룸')
    none = ZigbangStayListingDetail(**base, review_count=0, review_rating=None).model_dump()
    assert none['review_count'] == 0 and 'review_rating' not in none
    rated = ZigbangStayListingDetail(**base, review_count=3, review_rating=4.75).model_dump()
    assert rated['review_rating'] == 4.75
    failed = ZigbangStayListingDetail(**base, review_count=None, review_rating=None).model_dump()
    assert failed['review_count'] is None and failed['review_rating'] is None


def test_null_list_fields_read_as_missing_keys() -> None:
    # 실제 응답으로 재현하지 못하는 null. 목록 칸의 null 은 키가 없는 것과 같다: 기본값 [] 칸은 빈 목록, 키로 모름을 가르는 칸은 모름
    assert ZigbangStoreArticleStoresV2ResponseModel.model_validate({'sections': None}).sections == []
    manage = ZigbangItemsDetailV1ManageCostModel.model_validate({'include': [], 'exclude': None})
    assert sent_or_none(manage, 'includes', []) == [] and sent_or_none(manage, 'excludes', []) is None
    assert detail_to_listing(_room_detail(options=None)).options is None


def test_apt_region_offset_counts_dropped_null_catalogs() -> None:
    # 직방 offset 은 빈 항목(null)도 한 자리로 센다. 빼고 읽어도 받은 자리 수에 더해야 이어 받기가 같은 매물을 다시 받지 않는다
    fixture = load('locals_item_catalogs')
    body = dict(fixture, count=100, list=[fixture['list'][0], None, fixture['list'][0], None, None])
    region = ZigbangAptRegion(name='가상동', lat=37.5, lng=127.03, legal_division_code='1168010100')
    with make_client(lambda request: httpx.Response(200, json=body)) as client:
        result = search_apt_listings(client, region, limit=5)
    assert result.next_position == {'code': '11680101', 'offset': 5}
    assert any('빈 항목 3개' in note for note in result.notes)


def test_stay_schedule_with_dropped_null_makes_available_unknown() -> None:
    # 예약 일정에서 빈 항목(null)을 뺐으면 그 항목이 막힌 날이었을 수 있어 예약 가능 여부·막힌 기간은 '가능·없음' 이 아니라 모름이다
    detail = load('guest_items')
    blocked = {'scheduleType': 'BLOCKED', 'startDate': '2099-01-01', 'endDate': '2099-01-10'}
    schedules: list = [None, blocked]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/by-ids'):
            return httpx.Response(200, json={'items': []})
        if request.url.path.endswith('/reviews'):
            return httpx.Response(200, json={'summary': {'reviewCount': 0, 'averageRating': 0}})
        if '/host/' in request.url.path:
            return httpx.Response(200, json={'items': [], 'totalCount': 0})
        return httpx.Response(200, json=dict(detail, schedules=schedules))

    with make_client(handler) as client:
        dropped = get_any_listing(client, 'stay-5001', check_in='2099-06-01', check_out='2099-06-10')
    data = dropped.model_dump(mode='json')
    assert data['available'] is None and data['unavailable_periods'] is None
    assert any('빈 항목 1개' in note and 'available' in note for note in dropped.notes)
    # 빈 항목이 없으면 평소처럼 값이 나온다
    schedules.remove(None)
    with make_client(handler) as client:
        kept = get_any_listing(client, 'stay-5001', check_in='2099-06-01', check_out='2099-06-10')
    data = kept.model_dump(mode='json')
    assert data['available'] is True and len(data['unavailable_periods']) == 1


# --- 지역 화면 (region-info) ------------------------

def test_region_info_price_tabs_and_population_period() -> None:
    prices = [
        ZigbangLocalPriceModel.model_validate(item)
        for item in (
            {'area': '30', 'salesPrice': 5000, 'minSalesPrice': 1, 'maxSalesPrice': 2, 'rentPrice': 2000},
            {'area': '0', 'salesPrice': 0, 'rentPrice': 2000},
            {'area': '10', 'salesPrice': 4000, 'rentPrice': 0},
            {'area': '20', 'rentPrice': 2000},
            {'area': 'total', 'salesPrice': 5400, 'minSalesPrice': 7500, 'maxSalesPrice': 95000, 'rentPrice': 2400},
        )
    ]
    # 웹 탭처럼 평균 평당가가 0 인 평형대만 빼고 (값이 없는 칸은 남긴다), 전체 먼저 작은 평형대 순이다
    result = region_info._estimated_prices(prices)
    assert result is not None and [item.range for item in result] == ['전체', '20평대', '30평대']
    assert result[1].sale_price_per_pyeong_manwon is None
    assert region_info._sale_price_bounds(prices) == (7500, 95000)
    assert region_info._description_counts('4,923 단지 · 1,876,379 세대') == (4923, 1876379) and region_info._description_counts('') == (None, None)
    # 인구 그래프 기간: 끝은 지난달, 시작은 그 5년 전 같은 달 (2026-11-19 캡처 202110~202610)
    assert region_info.population_period(date(2026, 11, 22)) == ('202110', '202610')
    assert region_info.population_period(date(2027, 1, 5)) == ('202112', '202612')


# --- 시세 추이 (price-trend) -------------------------------------------

def _chart_line(label: str, prices: list[int]) -> dict:
    return {
        'label': label,
        'type': 'sale',
        'data': [{'date': f'2026-{month:02d}-01', 'price': price} for month, price in enumerate(prices, start=1)],
    }


class _FakePriceTrendClient:
    """직방 시세 추이 조회를 표본 모양의 가짜 응답으로 돌려주는 client."""

    def __init__(self, *, lines: list[dict], related: list[dict], room_types: list[int] | None = None, months: dict | None = None) -> None:
        self.lines = lines
        self.related = related
        self.room_types = room_types or []
        self.months = months or {}
        self.calls: list[str] = []

    def run_request_danjis_price_chart(self, parameter):
        self.calls.append(f'chart {parameter.danji_id} {parameter.add_danji_ids}')
        return ZigbangDanjisPriceChartResponseModel.model_validate({'list': self.lines})

    def run_request_danjis_price_chart_related_danjis(self, parameter):
        self.calls.append('related')
        return ZigbangDanjisPriceChartRelatedDanjisResponseModel.model_validate({'list': self.related})

    def run_request_danjis_room_types(self, parameter):
        self.calls.append('room_types')
        return ZigbangDanjisRoomTypesResponseModel.model_validate({'room_types': [{'id': rt} for rt in self.room_types]})

    def run_request_danjis_room_types_price_chart(self, parameter):
        self.calls.append(f'rt_chart {parameter.deal_type}')
        return ZigbangDanjisRoomTypesPriceChartResponseModel.model_validate({'list': self.months})


RELATED_COMPLEXES = [
    {'id': 900002, 'name': '가짜파크', 'household': '6,864세대', 'local1': '서울특별시', 'local2': '송파구', 'local3': '신천동'},
    {'id': 900003, 'name': '가짜포레', 'household': '12,032세대', 'local1': '서울특별시', 'local2': '강동구', 'local3': '둔촌동'},
]


def test_price_trend_line_kinds_follow_name_not_position() -> None:
    # 조회 900001 + 비교 900002: 직방은 ID 오름차순으로 줘 첫 줄이 비교 단지다
    client = _FakePriceTrendClient(
        lines=[_chart_line('가짜파크', [100, 0]), _chart_line('가짜헬리', [200, 210]), _chart_line('송파구', [300, 310])], related=RELATED_COMPLEXES,
    )
    result = get_price_trend(client, 'apt-900001', compare=['apt-900002'])  # type: ignore[arg-type]
    dumped = result.model_dump()
    assert [(line['name'], line['kind'], line.get('complex_id')) for line in dumped['lines']] == [
        ('가짜파크', '비교 단지', 'apt-900002'), ('가짜헬리', '단지', None), ('송파구', '구', None),
    ]
    # 0 은 점을 남기고 값만 null
    assert dumped['lines'][0]['points'] == [
        {'month': '2026-01', 'price_per_pyeong_manwon': 100}, {'month': '2026-02', 'price_per_pyeong_manwon': None},
    ]
    assert client.calls == ['related', 'chart 900001 [900002]']
    # 조회 단지가 비교보다 작으면 조회 단지가 첫 줄이다. 비교 둘은 이름으로 찾는다
    client = _FakePriceTrendClient(
        lines=[_chart_line('가짜헬리', [1, 2]), _chart_line('가짜파크', [3, 4]), _chart_line('가짜포레', [5, 6]), _chart_line('송파구', [7, 8])], related=RELATED_COMPLEXES,
    )
    result = get_price_trend(client, 'apt-1000', compare=['apt-900003', 'apt-900002'])  # type: ignore[arg-type]
    assert [(line.kind, line.complex_id) for line in result.lines or []] == [
        ('단지', None), ('비교 단지', 'apt-900002'), ('비교 단지', 'apt-900003'), ('구', None),
    ]
    # 줄 수가 맞지 않으면 판정하지 않는다 (kind null, complex_id 키 없음)
    client = _FakePriceTrendClient(
        lines=[_chart_line('가짜헬리', [1]), _chart_line('가짜파크', [2]), _chart_line('송파구', [3])], related=RELATED_COMPLEXES,
    )
    result = get_price_trend(client, 'apt-900001')  # type: ignore[arg-type]
    assert result.lines is not None and result.lines[0].kind is None and 'complex_id' not in result.model_dump()['lines'][0]
    assert not any('구 줄만' in text for text in result.notes)
    # 직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다 (2026-11-22 실측)
    client = _FakePriceTrendClient(lines=[_chart_line('송파구', [1])], related=RELATED_COMPLEXES)
    result = get_price_trend(client, 'apt-900001')  # type: ignore[arg-type]
    assert result.lines is not None and result.lines[0].kind == '구'
    assert any('구 줄만 있습니다' in text for text in result.notes)
    # 후보에 없는 단지는 요청 전에 후보를 보여 주며 막는다
    client = _FakePriceTrendClient(lines=[], related=RELATED_COMPLEXES)
    with pytest.raises(JibsaError) as error:
        get_price_trend(client, 'apt-900001', compare=['apt-5'])  # type: ignore[arg-type]
    assert 'apt-900002 가짜파크' in (error.value.hint or '') and client.calls == ['related']


def test_pyeong_price_trend_zero_months_and_month_merge() -> None:
    months = {
        'trade': [
            # 입주 전: 시세·최저·최고·변화가 모두 0, 건수만 양수
            {'date': '2018-11-01', 'min_price': 0, 'max_price': 0, 'average_price': 0, 'volume': 3, 'monthly_gap': {'price': 0, 'volume': 3}},
            {'date': '2018-12-01', 'min_price': 285000, 'max_price': 300000, 'average_price': 292000, 'volume': 2, 'monthly_gap': {'price': 0, 'volume': -1}},
            # 거래 0건인 달: 직방이 최저·최고에 시세를 채워 준다
            {'date': '2019-01-01', 'min_price': 292000, 'max_price': 292000, 'average_price': 292000, 'volume': 0, 'monthly_gap': {'price': 5000, 'volume': -2}},
        ],
        'deposit': [
            {'date': '2018-12-01', 'min_price': 90000, 'max_price': 120000, 'average_price': 100000, 'volume': 4, 'rent_volume': 0, 'monthly_gap': {'price': -1000}},
            {'date': '2019-02-01', 'min_price': 95000, 'max_price': 95000, 'average_price': 95000, 'volume': 0, 'rent_volume': 0, 'monthly_gap': {'price': 0}},
        ],
    }
    client = _FakePriceTrendClient(lines=[], related=[], room_types=[900004], months=months)
    result = get_pyeong_price_trend(client, 'apt-900001', 900004, trade='전체')  # type: ignore[arg-type]
    dumped = {month['month']: month for month in result.model_dump()['months']}
    assert list(dumped) == ['2018-11', '2018-12', '2019-01', '2019-02']
    assert dumped['2018-11']['sale'] == {
        'estimated_price_manwon': None, 'min_price_manwon': None, 'max_price_manwon': None, 'count': 3, 'change_manwon': None,
    }
    assert dumped['2018-11']['jeonse_wolse'] is None
    # 변화 0 은 시세가 있는 달에서는 진짜 0
    assert dumped['2018-12']['sale']['change_manwon'] == 0 and dumped['2018-12']['sale']['min_price_manwon'] == 285000
    assert dumped['2018-12']['jeonse_wolse']['wolse_count'] == 0
    assert dumped['2019-01']['sale']['count'] == 0 and dumped['2019-01']['sale']['min_price_manwon'] is None
    assert dumped['2019-01']['sale']['estimated_price_manwon'] == 292000
    # 전월세만 있는 달은 sale 이 null, 전세·월세 모두 0건이면 최저·최고가 null
    assert dumped['2019-02']['sale'] is None and dumped['2019-02']['jeonse_wolse']['min_price_manwon'] is None
    # 거래 탭을 고르면 다른 탭의 키가 없다
    only_sale = get_pyeong_price_trend(client, 'apt-900001', 900004, trade='매매').model_dump()['months']  # type: ignore[arg-type]
    assert all('jeonse_wolse' not in month and 'sale' in month for month in only_sale)
    only_rent = get_pyeong_price_trend(client, 'apt-900001', 900004, trade='전월세').model_dump()['months']  # type: ignore[arg-type]
    assert all('sale' not in month and 'jeonse_wolse' in month for month in only_rent)
    # 다른 단지의 평형 ID 는 평형 시세를 부르기 전에 막는다
    client = _FakePriceTrendClient(lines=[], related=[], room_types=[1, 2], months=months)
    with pytest.raises(JibsaError):
        get_pyeong_price_trend(client, 'apt-900001', 999)  # type: ignore[arg-type]
    assert client.calls == ['room_types']
