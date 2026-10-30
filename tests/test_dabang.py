import pytest
from httpx import (
    HTTPStatusError,
    Request,
    Response,
)

from jibsa.providers.dabang.api.response.ranking import DabangRegionRankingItemModel
from jibsa.providers.dabang.service.common import (
    is_missing_id,
    listing_prices,
    manwon_from_text,
    parse_room_desc,
)
from jibsa.providers.dabang.service.ranking import _entry


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


# --- ranking values ---


def test_population_decrease_is_negative() -> None:
    # 다방은 인구 변화 수를 부호 없이('327명') 주고 줄었는지는 changeStatus·변화율로만 알린다
    row = DabangRegionRankingItemModel.model_validate({
        'rank': 1,
        'regionName': '[가상]동',
        'formattedCurrCount': '1,000명',
        'formattedPrevCount': '1,010명',
        'formattedYearOfYearChangeCount': '10명',
        'formattedYearOfYearChangePercentage': '-1%',
        'changeStatus': 'DECREASE',
    })
    entry = _entry(row, 'population-change')
    assert (entry.count, entry.prev_count, entry.change_count, entry.change_percent) == (1000, 1010, -10, -1)


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
