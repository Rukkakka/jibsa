
from jibsa.core.listing import Listing, ListingDetail, normalize_date


def listing(trade_type: str, **values: object) -> Listing:
    return Listing(source='zigbang', id='1', url='https://example.com/1', trade_type=trade_type, property_type='원룸', **values)


def test_not_applicable_price_fields_are_omitted() -> None:
    assert set(listing('매매', price_manwon=1).model_dump()) & {'deposit_manwon', 'rent_manwon'} == set()
    assert set(listing('전세', deposit_manwon=1).model_dump()) & {'price_manwon', 'rent_manwon'} == set()
    monthly = listing('월세', deposit_manwon=1, rent_manwon=2).model_dump()
    assert 'price_manwon' not in monthly and monthly['rent_manwon'] == 2


def test_unknown_fields_stay_null() -> None:
    dumped = listing('월세', deposit_manwon=1000).model_dump(mode='json')
    # 월세라 해당은 되지만 값을 모르는 월세·관리비는 null
    assert dumped['rent_manwon'] is None
    assert dumped['manage_cost_manwon'] is None
    # 검색 중심점이 없으면 거리는 해당 없음이라 키를 뺀다
    assert 'distance_km' not in dumped
    assert listing('월세', distance_km=0.3).model_dump()['distance_km'] == 0.3
    # 좌표는 출력하지 않는다
    assert 'lat' not in dumped and 'lng' not in dumped


def test_detail_has_no_distance() -> None:
    detail = ListingDetail(source='naver', id='1', url='https://example.com/1', trade_type='매매', property_type='아파트')
    dumped = detail.model_dump(mode='json')
    assert 'distance_km' not in dumped
    assert dumped['elevator'] is None and dumped['options'] is None


def test_rule_applies_inside_wrapper_models() -> None:
    from pydantic import BaseModel

    class Wrapper(BaseModel):
        listings: list[Listing]

    dumped = Wrapper(listings=[listing('전세', deposit_manwon=1)]).model_dump(mode='json')
    assert 'price_manwon' not in dumped['listings'][0]


def test_list_fields_distinguish_unknown_from_empty() -> None:
    unknown = ListingDetail(source='naver', id='1', url='u', trade_type='매매', property_type='아파트')
    empty = unknown.model_copy(update={'nearby_subways': []})
    assert unknown.model_dump(mode='json')['nearby_subways'] is None
    assert empty.model_dump(mode='json')['nearby_subways'] == []


def test_normalize_date_drops_time_in_kst() -> None:
    # 직방 목록(KST), 직방 상세(시간대 없음 = KST), 당근(UTC), 네이버(날짜만) 모두 날짜만 남긴다
    assert normalize_date('2026-09-17T16:49:37+09:00') == '2026-09-17'
    assert normalize_date('2026-09-17 16:49:37') == '2026-09-17'
    assert normalize_date('2026-10-06T09:59:43.801Z') == '2026-10-06'
    # UTC 15시 이후는 한국 날짜로 다음 날
    assert normalize_date('2026-10-06T16:30:00.000Z') == '2026-10-07'
    assert normalize_date('2026-09-29') == '2026-09-29'
    # 직방 사용승인일은 '년 월 일' 로도 오고, '일' 이 빠지기도 한다
    assert normalize_date('1984년 10월 26일') == '1984-10-26'
    assert normalize_date('2011년 7월 1') == '2011-07-01'
    assert normalize_date('어제') == '어제'
    # 연월만 있는 값은 날짜로 지어내지 않는다 (예전 정규식은 '202411' 을 2024-01-01 로 읽었다)
    assert normalize_date('202411') == '202411'
    assert normalize_date('2024.11') == '2024.11'


def test_limit_notes_only_when_more_than_returned() -> None:
    from jibsa.core.listing import limit_notes

    # limit 을 다 못 채웠거나, 전체 수를 모르거나, 더 없으면 안내가 없다
    assert limit_notes(100, 5, 10) == []
    assert limit_notes(None, 10, 10) == []
    assert limit_notes(10, 10, 10) == []

    [note] = limit_notes(1576, 10, 10, approximate=True, basis='가격 조건 적용 전')
    assert note.startswith('조건에 맞는 매물 약 1576건(가격 조건 적용 전) 중 검색 중심에서 가까운 10건입니다. ')
    # 통합 검색이 다른 안내와 마침표로 이어 붙이므로 끝에 마침표가 없다
    assert not note.endswith('.')

    [note] = limit_notes(15, 10, 10, order='최근 게시된')
    assert note.startswith('조건에 맞는 매물 15건 중 최근 게시된 10건입니다')

    # 확인한 수(inspected)가 limit 에 닿았으면 받은 뒤 뺀 매물이 있어도 안내한다 (뺀 만큼 다시 채우지 않는다)
    [note] = limit_notes(660, 14, 15, approximate=True, inspected=15)
    assert note.startswith('조건에 맞는 매물 약 660건 중 검색 중심에서 가까운 14건입니다')
    assert limit_notes(660, 5, 15, inspected=5) == []


