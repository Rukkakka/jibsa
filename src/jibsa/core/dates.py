"""날짜 읽기: 사이트의 날짜 글자를 `YYYY-MM-DD` 로 바꾸고, 못 읽은 글자를 모아 [참고] 안내로 만든다. 모든 소스의 service 가 쓴다."""

import re
from calendar import monthrange
from collections.abc import (
    Container,
    Generator,
    Iterable,
)
from contextlib import contextmanager
from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

from jibsa.core.korean import particle
from jibsa.core.notes import note


KST: timezone = timezone(timedelta(hours=9), 'KST')
# 구분자가 없으면 8자리만 받는다. 월·일을 한 자리로도 받으면 연월('202411')이 2024-01-01 로 읽힌다.
# '년 월 일' 은 직방 사용승인일에 섞여 온다 ('1984년 10월 26일', '일' 이 빠진 '2011년 7월 1', 2026-10-15 실측)
DATE_DIGITS_PATTERN: re.Pattern[str] = re.compile(
    r'^(\d{4})(?:(\d{2})(\d{2})|[-./](\d{1,2})[-./](\d{1,2})|년\s*(\d{1,2})월\s*(\d{1,2})일?)\.?$'
)

ISO_DATE_PATTERN: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# 연월 칸의 'YYYY-MM'·'YYYY.M'·'YYYYMM'. 구분자 없이는 두 자리 달만 받는다
YEAR_MONTH_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d{4})(?:[-.](\d{1,2})|(\d{2}))')

# 이 명령이 받은 날짜 중 값이 있는데 날짜로 읽지 못한 원래 글자 (안내에 쓰는 칸 이름 -> 받은 차례대로의 글자). `read_date`·`move_in_label` 이
# 모으고 `cli.output.emit` 이 칸마다 [참고] 안내 한 줄로 붙인다 (`unread_date_notes`). 명령 시작에 `handle_errors` 가 `reset_unread_dates` 로
# 비운다. 응답에서 뺀 빈 항목의 합(`core.schema.null_item_tally`)과 같은 방식이라 변환 함수마다 notes 를 넘기지 않는다
# 파이썬에서 부르는 정문(`jibsa.providers.<source>`) 함수는 `with_notes` 가 부를 때마다 비우고 결과 `notes` 에 붙인다
_unread_dates: dict[str, list[str]] = {}
# `holding_unread_dates` 블록이 받는 곳. 안쪽 블록이 끝이다
_held_unread_dates: list[list[tuple[str, str]]] = []
# 매물 목록 `--fields` 에서 고를 수 있는 날짜 칸의 안내 이름 -> 출력 칸 이름. 소스가 이 이름으로 `read_date`·`move_in_label` 을 부른다.
# `--fields` 로 칸을 고르지 않았으면 `unread_date_notes` 가 그 안내를 뺀다
UNREAD_DATE_FIELDS: dict[str, str] = {
    '등록일': 'registered_date',
    '사용승인일': 'approved_date',
    '매물 확인일': 'confirmed_date',
    '입주일': 'move_in',
}


def years_ago(today: date, years: int) -> str:
    """`years` 년 전 같은 날 (2월 29일이면 28일). 실거래 기간(`--period`·`--years`)의 시작일이다."""
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def months_ago(today: date, months: int) -> str:
    """`months` 개월 전 같은 날 (그 달에 없는 날이면 그 달 말일). 실거래·시세 기간(`--period`)의 시작일이다.

    12 의 배수는 `years_ago` 와 같은 날을 준다 (2월 29일 → 평년 2월 28일).
    """
    index = today.year * 12 + today.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return today.replace(year=year, month=month, day=min(today.day, monthrange(year, month)[1])).isoformat()


def normalize_date(value: str | None) -> str | None:
    """날짜를 한국 날짜 기준 `YYYY-MM-DD` 로 맞춘다.

    `20100706`, `2018.04.27`, `1995-10-26 `, `1991년 6월 5일` 같은 날짜와, 시각이 붙은 일시도 받는다.
    일시는 시각을 버리고 날짜만 남긴다 (네이버가 날짜만 주므로 소스끼리 맞춘다).
    시간대가 없으면 한국 시간으로 보고, UTC(`...Z`)는 한국 시간으로 바꾼 뒤 날짜를
    뽑는다 (UTC 15시 이후는 한국 날짜로 다음 날). 읽을 수 없으면 앞뒤 공백만 지운
    원래 값을 돌려준다 (정보를 버리지 않는다). 연월만 있는 값(`202411`, `2024.11`)도 그대로 둔다.
    소스가 값이 없다는 표시로 주는 `-` 는 값이 아니라 None 이다 (빈 글자도 None).
    """
    if value is None:
        return None
    text = value.strip()
    if text == '-':
        return None
    match = DATE_DIGITS_PATTERN.match(text)
    if match is not None:
        year, month, day = (int(part) for part in match.groups() if part is not None)
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return text
    try:
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text or None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(KST).date().isoformat()


def iso_date(value: str | None) -> str | None:
    """날짜 글자를 `YYYY-MM-DD` 로 읽으면 그 값, 읽지 못하면(연월만·'-'·빈 값·문장·없는 날짜) None.

    입주일처럼 날짜인지 가려야 할 때 쓴다 (`normalize_date` 는 못 읽으면 원래 값을 돌려준다). 꼴만 맞고 없는
    날짜('0000-00-00'·'2026-02-30')는 `normalize_date` 가 원래 값 그대로 돌려줘 꼴만 보면 날짜로 통과하므로 달력으로 확인한다.
    출력 날짜 칸에는 못 읽은 글자를 `[참고]` 로 알리는 `read_date` 를 쓴다.
    """
    text = normalize_date(value)
    if text is None or not ISO_DATE_PATTERN.match(text):
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def reset_unread_dates() -> None:
    """못 읽은 날짜 모음을 비운다. 명령이 시작할 때 `cli.output.handle_errors` 가, 정문 함수를 부르기 전에 `with_notes` 가 부른다."""
    _unread_dates.clear()


def add_unread_date(what: str, raw: str) -> None:
    """값이 있는데 날짜·연월로 읽지 못한 원래 글자를 명령 모음에 넣는다. `holding_unread_dates` 블록 안이면 그 블록이 받는다."""
    entry = raw.strip()
    if _held_unread_dates:
        _held_unread_dates[-1].append((what, entry))
    else:
        _unread_dates.setdefault(what, []).append(entry)


@contextmanager
def holding_unread_dates() -> Generator[list[tuple[str, str]], None, None]:
    """블록 안에서 모은 못 읽은 날짜를 명령 모음에 넣지 않고 돌려준다 ((칸 이름, 원래 글자) 목록).

    변환한 뒤에 거르거나(반경·중복) 자르는(`--limit`) 목록이 출력에 남지 않는 항목의 날짜까지 세지 않도록, 항목마다 이 블록
    안에서 바꾸고 최종 목록이 정해진 뒤 남은 항목의 것만 `keep_unread_dates` 로 넣는다.
    """
    held: list[tuple[str, str]] = []
    _held_unread_dates.append(held)
    try:
        yield held
    finally:
        _held_unread_dates.pop()


def keep_unread_dates(held: Iterable[tuple[str, str]], *, only: Container[str] | None = None) -> None:
    """`holding_unread_dates` 가 돌려준 것을 명령 모음에 넣는다. `only` 를 주면 그 칸 이름만 넣는다."""
    for what, raw in held:
        if only is None or what in only:
            add_unread_date(what, raw)


def read_date(value: str | None, what: str, *, raw: str | None = None) -> str | None:
    """출력 날짜 칸의 값을 `YYYY-MM-DD` 로 읽는다 (output-contract.md 날짜 칸 규칙).

    소스가 값 없음으로 준 것(None·빈 글자·'-')은 안내 없이 None 이다. 값이 있는데 날짜로 읽지 못하면(연월만·문장·달력에
    없는 날) 받은 글자를 내지 않고 None 을 돌려주며, 원래 글자를 `what` 칸으로 모아 `emit` 이 `[참고]` 로 알리게 한다.
    거르기·비교처럼 출력 칸이 아닌 자리는 `iso_date`·`normalize_date` 를 쓴다 (여기 쓰면 안내가 붙는다).

    Args:
        value: 소스가 준 날짜 글자.
        what: 안내에 쓰는 한국어 칸 이름 ('사용승인일', '계약일'). 같은 이름은 한 줄로 모인다.
        raw: 안내에 보일 원래 글자. 부르는 쪽이 글자를 조립해 넘길 때 소스가 준 글자를 준다 (다방 '20' + 계약일).
    """
    text = normalize_date(value)
    if text is None:
        return None
    date = iso_date(text)
    if date is None:
        add_unread_date(what, text if raw is None else raw)
    return date


def read_month(value: str | None, what: str, *, raw: str | None = None) -> str | None:
    """출력 연월 칸(`_month`)을 `YYYY-MM` 으로 읽는다. 'YYYY-MM'·'YYYYMM'·'YYYY.MM' 을 받는다.

    값 없음(None·빈 글자·'-')은 안내 없이 None 이다. 값이 있는데 못 읽으면(꼴이 다르거나 13월) None 을 돌려주고
    원래 글자를 `what` 칸으로 모은다 (`read_date` 와 같다).
    """
    if value is None:
        return None
    text = value.strip()
    if text in ('', '-'):
        return None
    match = YEAR_MONTH_TEXT_PATTERN.fullmatch(text)
    month = (match.group(2) or match.group(3)) if match else None
    if match is not None and month is not None and 1 <= int(month) <= 12:
        return f'{match.group(1)}-{int(month):02d}'
    add_unread_date(what, text if raw is None else raw)
    return None


def unread_date_notes(site: str, fields: Container[str] | None = None) -> list[str]:
    """이 명령에서 읽지 못한 날짜를 칸마다 `[참고]` 한 줄로. 모은 것이 없으면 빈 목록. `collected_notes` 가 모아 `cli.output.emit`·`with_notes` 가 notes 끝에 붙인다.

    Args:
        site: 사이트 이름 ('직방', '네이버', '당근', '다방'). 조사는 끝 글자에 맞춘다.
        fields: `--fields` 로 고른 칸. 고르지 않은 날짜 칸의 안내는 출력에 그 칸이 없어 뺀다.
    """
    notes: list[str] = []
    for what, texts in _unread_dates.items():
        if fields is not None and what in UNREAD_DATE_FIELDS and UNREAD_DATE_FIELDS[what] not in fields:
            continue
        # 예는 겹치지 않게 앞 셋만 보인다 (같은 글자가 여러 건이면 한 번만)
        examples = ', '.join(f"'{text}'" for text in list(dict.fromkeys(texts))[:3])
        subject = f"{site}{particle(site, '이/가')} 준 {what}"
        if len(texts) == 1:
            body = f"{subject}{particle(what, '을/를')} 읽지 못해 null 로 냈습니다 ({examples})"
        else:
            body = f'{subject} {len(texts)}건을 읽지 못해 null 로 냈습니다 (예: {examples})'
        notes.append(note('참고', f'{body}. 사이트 화면에서 확인하세요'))
    return notes
