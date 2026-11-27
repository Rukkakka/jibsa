"""다방 글자 해석기 (금액·숫자·세대수·연차·계약일·층)."""
from math import isfinite

from jibsa.core.listing import read_date
from jibsa.providers.dabang.service.common.constants import (
    FLOOR_LABELS,
    FLOOR_NUMBER_PATTERN,
    HOUSEHOLDS_TEXT_PATTERN,
    MANWON_PER_EOK,
    MANWON_TEXT_PATTERN,
    NUMBER_TEXT_PATTERN,
    YEARS_TEXT_PATTERN,
)


def manwon_from_text(text: str | None) -> float | None:
    """다방 금액 글자를 만원 숫자로 바꾼다 ('3억9000' → 39000, '22억' → 220000, '31억 3,000' → 313000, '1000' → 1000).

    억 앞뒤의 띄어쓰기와 천 단위 쉼표는 무시한다. 금액 꼴이 아니면('준비중', 빈 글자) None.
    """
    if text is None:
        return None
    compact = text.replace(',', '').replace(' ', '')
    match = MANWON_TEXT_PATTERN.fullmatch(compact)
    if not compact or match is None or (match.group(1) is None and match.group(2) is None):
        return None
    value = float(match.group(1) or 0) * MANWON_PER_EOK + float(match.group(2) or 0)
    return round(value, 4) if isfinite(value) else None


def number_of(text: str | None, *, signed: bool = False) -> float | None:
    """글자의 첫 숫자 ('4.1명' → 4.1, '5.52:1' → 5.52, '대학교 163명' → 163, '115.54㎡' → 115.54). 띄어쓰기·천 단위 쉼표는
    무시한다. `signed` 면 앞의 부호도 읽는다 ('-0.6%' → -0.6). 숫자가 없으면('-', 빈 글자) None.

    다방은 수를 단위·이름표를 붙인 글자로 준다. 순위·분양 청약·단지 학교·어린이집·최근 거래·목록 설명이 모두 이 함수로 읽는다.
    """
    match = NUMBER_TEXT_PATTERN.search((text or '').replace(' ', ''))
    if match is None:
        return None
    value = float(match.group(2).replace(',', ''))
    return -value if signed and match.group(1) == '-' else value


def count_of(text: str | None) -> int | None:
    """'1,074개'·'60위'·'대학교 163명' 같은 글자의 (첫) 숫자를 정수로. 없으면 None."""
    number = number_of(text)
    return None if number is None else int(number)


def household_count(text: str | None) -> int | None:
    """세대수 글자('615세대', '1,234 세대')의 세대수. 단지 목록·분양 목록·거래 순위가 함께 쓴다. 없으면 None."""
    match = HOUSEHOLDS_TEXT_PATTERN.search(text or '')
    return int(match.group(1).replace(',', '')) if match else None


def building_years(text: str | None) -> int | None:
    """연차 글자('48년차')의 연차. 단지 목록·거래 순위가 함께 쓴다. 없으면 None."""
    match = YEARS_TEXT_PATTERN.search(text or '')
    return int(match.group(1)) if match else None


def contract_date(text: str | None, what: str) -> str | None:
    """두 자리 연도로 오는 다방 계약일 글자를 'YYYY-MM-DD' 로 (`read_date`, 원래 글자로 알린다). 실거래 목록과 단지 최근 실거래가 함께 쓴다.

    다방이 값 없음으로 주는 `-`·빈 글자는 안내 없는 None 이다 (앞에 '20' 을 붙이면 '20-' 가 되어 못 읽은 날짜로 알려진다).
    """
    if text is None or text.strip() in ('', '-'):
        return None
    return read_date(f'20{text}', what, raw=text)


def floor_label(text: str | None) -> str | None:
    """다방 층 글자를 jibsa 표기로 ('5층' → '5', '지하1층' → '지하1', '고층'·'반지하'·'옥탑' 은 그대로)."""
    if text is None or not text.strip():
        return None
    value = text.strip()
    match = FLOOR_NUMBER_PATTERN.fullmatch(value)
    if match is not None:
        return f"{'지하' if match.group(1) else ''}{int(match.group(2))}"
    return FLOOR_LABELS.get(value, value)
