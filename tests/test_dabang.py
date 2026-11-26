import pytest
from httpx import (
    Client,
    HTTPStatusError,
    MockTransport,
    Request,
    Response,
)

from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.response.common import (
    DabangComplexEducationModel,
    DabangRoomListResultModel,
)
from jibsa.providers.dabang.api.response.ranking.region import (
    DabangRegionRankingItemModel,
)
from jibsa.providers.dabang.service.common.functions import (
    is_missing_id,
    listing_prices,
    manwon_from_text,
    parse_room_desc,
)
from jibsa.providers.dabang.service.common.models import DabangPlace
from jibsa.providers.dabang.service.complex.detail import list_complex_listings
from jibsa.providers.dabang.service.listing.functions import search_listings
from jibsa.providers.dabang.service.neighborhood.info import get_neighborhood
from jibsa.providers.dabang.service.neighborhood.popular import get_popular_listings
from jibsa.providers.dabang.service.ranking.region import (
    ValueKind,
    _entry,
    get_region_ranking,
)
from jibsa.providers.dabang.service.region.functions import DabangDong
from jibsa.providers.dabang.service.region.models import DabangScope


# --- price text ---


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('1000', 1000),
        ('3억9000', 39000),
        ('22억', 220000),
        # 단지 목록·요약은 억 뒤에 띄어쓰기와 천 단위 쉼표를 넣는다
        ('31억 3,000', 313000),
        ('61.1억', 611000),
        # 금액은 반올림 없이 원 단위(만원 소수 넷째 자리)까지 읽는다 (85,800원)
        ('8.58', 8.58),
        ('준비중', None),
        ('', None),
    ],
)
def test_price_text_is_read_in_manwon(text: str, expected: float | None) -> None:
    # 다방 목록은 가격을 글자로만 준다. 억을 잘못 풀면 금액이 10배씩 틀린다
    assert manwon_from_text(text) == expected


def test_listing_price_and_description_are_split_by_trade_type() -> None:
    assert listing_prices('월세', '1억2000/50') == {'deposit_manwon': 12000, 'rent_manwon': 50}
    assert listing_prices('전세', '2억5000') == {'deposit_manwon': 25000}
    assert listing_prices('매매', '3억9000') == {'price_manwon': 39000}
    # 월세인데 보증금/월세 꼴이 아니면 임의의 값을 내지 않는다
    assert listing_prices('월세', '3억9000') is None
    assert parse_room_desc('5층, 19.83m², 관리비 7만') == ('5', 19.83, 7)
    assert parse_room_desc('반지층, 26.44m², 관리비 9.9만') == ('반지하', 26.44, 9.9)
    # '관리비 없음' 은 0, 관리비 칸이 없으면 모름(None)
    assert parse_room_desc('고층, 17.34m², 관리비 없음') == ('고층', 17.34, 0)
    assert parse_room_desc('3층, 23.14m²') == ('3', 23.14, None)


# --- listing search paging ---


def test_next_resumes_after_short_page_without_repeating_listings() -> None:
    # 다방 목록은 한 쪽이 24건보다 적게 올 때가 있다 (2026-11-13 웹 캡처: 아파트 강남역 1쪽 23건). 받은 수로 쪽을 셈하면
    # 23건 쪽 뒤에 2쪽 첫 건까지 받은 다음, 이어 받을 때 2쪽을 처음부터 다시 받아 같은 매물을 또 줬다
    sizes = {1: 23, 2: 24, 3: 24}
    starts = {1: 0, 2: 23, 3: 47}

    def handler(request: Request) -> Response:
        page = int(request.url.params['page'])
        rows = [
            {
                'id': f'{number:024x}',
                'roomTypeName': '원룸',
                'roomDesc': '3층, 20m², 관리비 5만',
                'priceTypeName': '월세',
                'priceTitle': '1000/50',
            }
            for number in range(starts[page], starts[page] + sizes[page])
        ]
        return Response(200, json={'code': 200, 'result': {'roomList': rows, 'total': 71, 'hasMore': page < 3}})

    client = DabangClient()
    client.__dict__['_client'] = Client(base_url=client.base_url, transport=MockTransport(handler))
    place = DabangPlace(kind='dong', name='[가상]동', lat=37.5, lng=127.0, code='00000001', gid=1)
    with client:
        first = search_listings(client, 'room', place, limit=24)
        second = search_listings(client, 'room', place, limit=24, resume=first.next_position)
    assert [listing.id for listing in first.listings] == [f'{number:024x}' for number in range(24)]
    assert [listing.id for listing in second.listings] == [f'{number:024x}' for number in range(24, 48)]
    # 사용자에게 보이는 '몇 번째부터' 는 받은 수 기준이다
    assert second.next_position is not None and second.next_position.received == 48


def test_complex_listings_fill_max_limit_when_pages_are_short() -> None:
    # 단지 매물은 이어 받기(--next)가 없다. 쪽 수 상한이 --limit 최대값을 채우는 다섯 쪽이면 다방이 쪽마다 23건만 줄 때
    # 115건에서 멈춰 남은 매물을 받을 길이 없었다
    complex_id = '0000000000000000000000000001'  # 다방 단지 ID 꼴(16진수 28자)의 가짜 값
    pages: list[int] = []

    def handler(request: Request) -> Response:
        if request.url.path.endswith(f'/complex/{complex_id}'):
            return Response(200, json={'code': 200, 'result': {
                'complex': {'complexId': complex_id, 'complexType': 'APT', 'complexName': '[가상]아파트'},
                'spaces': [{'spaceSeq': 1}],
            }})
        page = int(request.url.params['page'])
        pages.append(page)
        rows = [
            {
                'id': f'{number:024x}',
                'roomTypeName': '아파트',
                'roomDesc': '3층, 84m², 관리비 20만',
                'priceTypeName': '전세',
                'priceTitle': '5억',
            }
            for number in range((page - 1) * 23, page * 23)
        ]
        return Response(200, json={'code': 200, 'result': {'roomList': rows, 'total': 200, 'hasMore': True}})

    client = DabangClient()
    client.__dict__['_client'] = Client(base_url=client.base_url, transport=MockTransport(handler))
    with client:
        result = list_complex_listings(client, complex_id, limit=120)
    assert pages == [1, 2, 3, 4, 5, 6]
    assert result.returned == 120
    assert result.has_more


# --- ranking values ---


@pytest.mark.parametrize(
    ('kind', 'values'),
    [
        ('population-change', {
            'formattedCurrCount': '2,000명',
            'formattedPrevCount': '2,001명',
            'formattedYearOfYearChangeCount': '1명',
            'formattedYearOfYearChangePercentage': '0%',
        }),
        # 거래증감·매물증감도 변화 수를 부호 없이 준다 (2026-11-13 강남구 매물증감 낮은순 신사동 '2개'·'-9.1%')
        ('count-change', {
            'formattedCurrCount': '2,000개',
            'formattedPrevCount': '2,001개',
            'formattedCount': '1개',
            'formattedChangeRate': '0%',
        }),
    ],
)
def test_change_count_decrease_is_negative(kind: ValueKind, values: dict[str, str]) -> None:
    # 다방은 인구·거래·매물 변화 수를 부호 없이('327명') 준다. 앞·지금 수가 있으면 그 차로 내서, changeStatus 가 빠지고
    # 변화율이 '0%' 로 반올림돼도 줄었으면 음수다
    row = DabangRegionRankingItemModel.model_validate({'rank': 1, 'regionName': '[가상]동', **values})
    entry = _entry(row, kind, {})
    assert (entry.count, entry.prev_count, entry.change_count, entry.change_percent) == (2000, 2001, -1, 0)


@pytest.mark.parametrize(
    ('metric', 'types', 'sent', 'shown'),
    [
        # 웹 기본은 아파트·오피스텔을 둘 다 골라 complexType 을 빼고 보낸다 (합산 순위)
        ('거래량', [], None, '아파트·오피스텔 합산'),
        ('거래량', ['아파트', '오피스텔'], None, '아파트·오피스텔 합산'),
        ('거래량', ['오피스텔'], 'OFFICETEL', '오피스텔'),
        # 평균가는 웹도 하나만 고르고 기본이 아파트다
        ('평균가', [], 'APT', '아파트'),
    ],
)
def test_region_ranking_sends_complex_type_like_the_web(
    metric: str, types: list[str], sent: str | None, shown: str,
) -> None:
    queries = []

    def handler(request: Request) -> Response:
        queries.append(request.url.params)
        return Response(200, json={'code': 200, 'result': {'ranking': {'list': [], 'total': 0, 'hasMore': False}}})

    client = DabangClient()
    client.__dict__['_client'] = Client(base_url=client.base_url, transport=MockTransport(handler))
    scope = DabangScope(kind='district', name='[가상]구', gid=1)
    with client:
        result = get_region_ranking(
            client, scope, metric_label=metric, unit='동', complex_types=types, trades=[], order='높은순', limit=5,
        )
    assert queries[0].get('complexType') == sent
    assert result.complex_type == shown


# --- null lists ---


def test_null_list_fields_read_as_missing_keys() -> None:
    # 서버가 비운 목록 칸에 null 을 주면 조회 전체가 파싱 에러로 끝나지 않고 키가 없을 때처럼 빈 목록이 된다.
    # 실제 응답으로는 재현되지 않아 null 을 직접 넣는다
    result = DabangRoomListResultModel.model_validate({'roomList': None, 'premiumList': None, 'total': 0})
    assert result.room_list == [] and result.premium_list == []
    # `| None` 칸은 null 이 모름이라 빈 목록으로 바꾸지 않는다 (단지 학교·어린이집)
    assert DabangComplexEducationModel.model_validate({'nurserySchool': None}).nursery_school is None


def test_null_items_make_computed_values_unknown() -> None:
    # 다방이 객체 목록 안에 빈 항목(null)을 섞어 주면 빼고 읽되, 그 목록으로 계산한 값은 받은 것만으로 낸 틀린 값이 되지 않고
    # 모름(null)이다. 실제 응답으로는 재현되지 않아 null 을 직접 넣는다
    def room(number: int) -> dict[str, str]:
        return {
            'id': f'{number:024x}',
            'roomTypeName': '원룸',
            'roomDesc': '3층, 20m², 관리비 5만',
            'priceTypeName': '월세',
            'priceTitle': '1000/50',
        }

    def handler(request: Request) -> Response:
        if request.url.path.endswith('/room/regional/summary'):
            return Response(200, json={'code': 200, 'result': {'distributionList': [
                {'name': '아파트', 'value': 3}, None, {'name': '오피스텔', 'value': 2},
            ]}})
        return Response(200, json={'code': 200, 'result': {'list': [room(1), None, room(2)], 'total': 3, 'hasMore': False}})

    client = DabangClient()
    client.__dict__['_client'] = Client(base_url=client.base_url, transport=MockTransport(handler))
    dong = DabangDong(DabangPlace(kind='dong', name='[가상]동', lat=37.5, lng=127.0, code='00000001', gid=1), 1)
    with client:
        neighborhood = get_neighborhood(client, dong, ['매물'])
        popular = get_popular_listings(client, dong, building_types=[], trade_types=[], limit=3)
    # 유형별 합계: 뺀 유형의 수를 몰라 받은 유형만 더한 5 를 내지 않고 null 이다
    assert neighborhood.listings is not None and neighborhood.listings.count is None
    assert [item.property_type for item in neighborhood.listings.by_type] == ['아파트', '오피스텔']
    assert any(text.startswith('[제외]') and 'listings.count' in text for text in neighborhood.notes)
    # 인기 매물 순위: 빈 항목을 뺀 쪽은 어느 자리가 빠졌는지 몰라 순위를 셀 수 없다 (받은 순서로 1·2 를 매기면 틀린다)
    assert [listing.rank for listing in popular.listings] == [None, None]
    assert any(text.startswith('[제외]') and 'rank' in text for text in popular.notes)


# --- missing ID ---


def test_empty_403_means_missing_id_only_when_the_id_is_in_the_path() -> None:
    # 다방은 없는 주소에 403 빈 응답을 준다. ID 가 쿼리로 가는 요청은 없는 ID 에 400·빈 결과를 줘서 그 403 은 주소가 바뀐 것이다.
    # 실제로는 다방이 주소를 바꿔야 재현돼 응답을 만들어 본다
    def error(status: int, body: bytes = b'') -> HTTPStatusError:
        request = Request('GET', 'https://www.dabangapp.com/api/3/sale-in-lots/detail2')
        return HTTPStatusError('', request=request, response=Response(status, content=body, request=request))

    assert is_missing_id(error(403)) and not is_missing_id(error(403), in_path=False)
    # 400 은 사유가 '존재하지 않…' 일 때만 없는 ID 다. 요청 형식 오류의 400 은 다방이 바뀐 것이다 (2026-10-28 실측 본문)
    assert is_missing_id(error(400, '{"msg":"존재하지 않는 분양정보입니다."}'.encode()), in_path=False)
    assert not is_missing_id(error(400, '{"msg":"사용이 중지된 버전입니다."}'.encode()), in_path=False)
    # 본문이 있는 403 은 차단 페이지일 수 있다
    assert not is_missing_id(error(403, b'<html>blocked</html>'))
