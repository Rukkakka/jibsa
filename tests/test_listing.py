
import httpx
import pytest

from jibsa.core.listing import (
    NULL_ITEMS_PHRASE,
    Listing,
    ListingDetail,
    Result,
    add_unread_date,
    holding_unread_dates,
    keep_unread_dates,
    lookup_failure_note,
    move_in_label,
    normalize_date,
    read_date,
    read_month,
    reset_unread_dates,
    unread_date_notes,
    with_notes,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.core.schema import (
    add_null_item_tally,
    reset_null_item_tally,
)


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
    assert dumped['has_elevator'] is None and dumped['options'] is None


def test_rule_applies_inside_wrapper_models() -> None:
    from pydantic import BaseModel

    class Wrapper(BaseModel):
        listings: list[Listing]

    dumped = Wrapper(listings=[listing('전세', deposit_manwon=1)]).model_dump(mode='json')
    assert 'price_manwon' not in dumped['listings'][0]


def test_list_fields_distinguish_unknown_from_empty() -> None:
    unknown = ListingDetail(source='naver', id='1', url='u', trade_type='매매', property_type='아파트')
    empty = unknown.model_copy(update={'nearby_stations': []})
    assert unknown.model_dump(mode='json')['nearby_stations'] is None
    assert empty.model_dump(mode='json')['nearby_stations'] == []


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
    # 소스가 값이 없다는 표시로 주는 '-' 는 날짜 칸에 나가지 않는다
    assert normalize_date('-') is None
    assert normalize_date(' - ') is None
    assert normalize_date('') is None


def test_read_date_collects_unreadable_dates_per_field() -> None:
    # 값 없음은 안내 없이 None, 값이 있는데 못 읽으면 None 과 칸별 [참고] 한 줄 (output-contract.md 날짜 칸)
    reset_unread_dates()
    assert read_date(None, '계약일') is None
    assert read_date('', '계약일') is None
    assert read_date(' - ', '계약일') is None
    assert read_date('20260908', '계약일') == '2026-09-08'
    assert read_date('201005', '계약일') is None
    assert read_date('2026-02-30', '계약일') is None
    assert read_date('201005', '계약일') is None
    assert read_date('20260230', '사용승인일', raw='26.02.30') is None
    assert unread_date_notes('직방') == [
        "[참고] 직방이 준 계약일 3건을 읽지 못해 null 로 냈습니다 (예: '201005', '2026-02-30'). 사이트 화면에서 확인하세요",
        "[참고] 직방이 준 사용승인일을 읽지 못해 null 로 냈습니다 ('26.02.30'). 사이트 화면에서 확인하세요",
    ]
    # 입주일도 못 읽으면 받은 글자 대신 None 이고 원래 글자(괄호 포함)를 알린다
    reset_unread_dates()
    assert move_in_label('2026.10.15 이후 입주 가능 (협의가능)') == '2026-10-15 (협의 가능)'
    # '협의가능' 이 아닌 괄호 설명은 직방 웹처럼 그대로 붙인다
    assert move_in_label('2026.10.15 이후 입주 가능 (입주협의)') == '2026-10-15 (입주협의)'
    assert move_in_label('2026.13.01 (협의 가능)') is None
    assert unread_date_notes('다방') == [
        "[참고] 다방이 준 입주일을 읽지 못해 null 로 냈습니다 ('2026.13.01 (협의 가능)'). 사이트 화면에서 확인하세요",
    ]
    # 입주일 '-' 는 값 없음이라 안내가 없다 (날짜 자리가 비고 괄호 설명만 있어도 같다)
    reset_unread_dates()
    assert move_in_label('-') is None
    assert move_in_label('- (협의가능)') is None
    assert unread_date_notes('다방') == []
    # 연월 칸: 받는 꼴, 값 없음, 못 읽음
    assert read_month('2026-07', '관리비 최근 달') == '2026-07'
    assert read_month('202607', '관리비 최근 달') == '2026-07'
    assert read_month('2026.7', '관리비 최근 달') == '2026-07'
    assert read_month('-', '관리비 최근 달') is None
    assert read_month('2026-13', '관리비 최근 달') is None
    assert unread_date_notes('네이버') == [
        "[참고] 네이버가 준 관리비 최근 달을 읽지 못해 null 로 냈습니다 ('2026-13'). 사이트 화면에서 확인하세요",
    ]
    # 블록 안에서 모은 것은 남긴 항목의 것만 넣는다
    reset_unread_dates()
    with holding_unread_dates() as dropped:
        read_date('201005', '등록일')
    with holding_unread_dates() as kept:
        read_date('2026-02-30', '등록일')
    assert unread_date_notes('네이버') == []
    keep_unread_dates(kept)
    assert dropped == [('등록일', '201005')]
    assert len(unread_date_notes('네이버')) == 1 and "('2026-02-30')" in unread_date_notes('네이버')[0]
    # --fields 로 고르지 않은 날짜 칸의 안내는 뺀다. 표에 없는 이름은 늘 낸다
    add_unread_date('계약일', '미상')
    only_id = unread_date_notes('네이버', frozenset({'id'}))
    assert len(only_id) == 1 and '준 계약일을 읽지 못해' in only_id[0]
    assert len(unread_date_notes('네이버', frozenset({'registered_date'}))) == 2
    reset_unread_dates()
    assert unread_date_notes('다방') == []


@pytest.mark.parametrize(
    ('exc', 'expected'),
    [
        (RateLimitedError('dabang', 5, 'cooldown'), '[실패] 요청 제한에 걸려 매물 상세를 받지 못했습니다. dabang 요청이 429 로 차단되어 쿨다운 중입니다. 5초 뒤 다시 시도하세요. 모름 칸'),
        (ValueError('x'), '[실패] 다방이 매물 상세 요청을 거절했거나 응답 형식이 바뀌었습니다. jibsa 업데이트가 필요할 수 있습니다. 모름 칸'),
        (None, '[실패] 다방이 매물 상세 요청을 거절했거나 응답 형식이 바뀌었습니다. jibsa 업데이트가 필요할 수 있습니다. 모름 칸'),
        (httpx.HTTPStatusError('서버 오류', request=httpx.Request('GET', 'https://x'), response=httpx.Response(503)), '[실패] 다방 매물 상세 요청이 실패했습니다 (HTTPStatusError). 잠시 뒤 다시 시도하세요. 모름 칸'),
    ],
)
def test_lookup_failure_note_branches(exc: Exception | None, expected: str) -> None:
    # 무슨 일 → 할 일 → 모름이 된 칸 순서이고 모름이 된 칸이 늘 끝이다
    assert lookup_failure_note(exc, '다방', '매물 상세', '모름 칸') == expected


def test_limit_notes_only_when_more_than_returned() -> None:
    from jibsa.core.listing import NEXT_HINT, limit_notes

    # limit 을 다 못 채웠거나, 전체 수를 모르거나, 더 없으면 안내가 없다
    assert limit_notes(100, 5, 10, max_limit=120, narrow='조건·지역', inspected=5, has_more=True) == []
    assert limit_notes(None, 10, 10, max_limit=120, narrow='조건·지역', inspected=10, has_more=True) == []
    assert limit_notes(10, 10, 10, max_limit=120, narrow='조건·지역', inspected=10, has_more=True) == []

    [note] = limit_notes(1576, 10, 10, max_limit=120, narrow='조건·지역', inspected=10, approximate=True, has_more=True)
    assert note.startswith('[일부] 조건에 맞는 매물이 약 1576건 있고, 그중 검색 중심에서 가까운 순으로 10건만 보여 줍니다. ')
    # 통합 검색이 다른 안내와 마침표로 이어 붙이므로 끝에 마침표가 없다
    assert not note.endswith('.')

    [note] = limit_notes(15, 10, 10, max_limit=120, narrow='조건·지역', inspected=10, order='최근 게시된', has_more=True)
    assert note.startswith('[일부] 조건에 맞는 매물이 15건 있고, 그중 최근 게시된 순으로 10건만 보여 줍니다')

    # 확인한 수(inspected)가 limit 에 닿았으면 받은 뒤 뺀 매물이 있어도 안내한다 (뺀 만큼 다시 채우지 않는다)
    [note] = limit_notes(660, 14, 15, max_limit=120, narrow='조건·지역', approximate=True, inspected=15, has_more=True)
    assert note.startswith('[일부] 조건에 맞는 매물이 약 660건 있고, 그중 검색 중심에서 가까운 순으로 14건만 보여 줍니다')
    assert limit_notes(660, 5, 15, max_limit=120, narrow='조건·지역', inspected=5, has_more=True) == []

    # --limit 이 이미 최대값이면 늘리라고 하지 않는다 (늘리면 INVALID_ARGUMENT)
    [note] = limit_notes(1917, 120, 120, max_limit=120, narrow='조건·지역', inspected=120, has_more=True)
    assert note.endswith('--limit 의 최대값은 120입니다. 더 보려면 조건·지역을 좁히세요')

    # 확인한 매물이 모두 빠지면 '0건만 보여 줍니다' 대신 보여 줄 매물이 없다고 한다
    [note] = limit_notes(41, 0, 1, max_limit=120, narrow='조건·지역', approximate=True, inspected=1, resumable=True, has_more=True)
    assert note == (
        '[일부] 조건에 맞는 매물이 약 41건 있지만, 검색 중심에서 가까운 순으로 확인한 매물이 모두 빠져 보여 줄 매물이 없습니다. '
        + NEXT_HINT
    )


def test_amount_set_dumps_only_given_fields() -> None:
    from jibsa.core.listing import AmountRange, AmountSet

    assert AmountSet(price_manwon=None).model_dump(mode='json') == {'price_manwon': None}
    assert AmountSet().model_dump(mode='json') == {}
    amount_range = AmountRange(lowest=AmountSet(deposit_manwon=1000, rent_manwon=58), highest=None)
    dumped = amount_range.model_dump(mode='json')
    assert dumped == {'lowest': {'deposit_manwon': 1000.0, 'rent_manwon': 58.0}, 'highest': None}
    # dump 한 dict 로 다시 만들어도 같은 키가 나온다
    assert AmountRange.model_validate(dumped).model_dump(mode='json') == dumped


def test_with_notes_puts_collected_notes_in_result_once() -> None:
    # 파이썬에서 정문 함수를 부르면 CLI 처럼 [참고]·[제외] 가 결과 notes 에 들어가고, 연달아 불러도 앞 호출의 안내가 섞이지 않는다
    def fake() -> Result:
        add_unread_date('등록일', '어제')
        add_null_item_tally(2)
        return Result(notes=['[일부] 앞 안내'])

    wrapped = with_notes('naver')(fake)
    try:
        for _ in range(2):
            notes = wrapped().notes
            assert notes[0] == '[일부] 앞 안내'
            assert sum(text.startswith('[참고]') and '등록일' in text for text in notes) == 1
            assert sum(NULL_ITEMS_PHRASE in text for text in notes) == 1
        assert with_notes('naver')(lambda: ['그대로'])() == ['그대로']
    finally:
        reset_unread_dates()
        reset_null_item_tally()
