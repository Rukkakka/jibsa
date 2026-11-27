"""동네정보 기능(neighborhood)의 핫플레이스·동네정보가 같이 쓰는 것: 기준 달."""
from jibsa.core.listing import (
    holding_unread_dates,
    keep_unread_dates,
    read_month,
)


def base_month(update_dates: list[str | None]) -> str | None:
    """요약·쪽마다 받은 갱신일 글자('26.10') 중 처음 읽은 달을 'YYYY-MM' 으로 (`read_month`, 13월 같은 달은 못 읽음).

    값 없음(None·빈 글자·`-`)은 건너뛴다. 읽은 달이 없는데 못 읽은 글자가 있으면 출력 칸 `base_month` 하나가 null 이라 처음 못 읽은
    글자 하나만 `[참고]` 로 알린다.
    """
    with holding_unread_dates() as held:
        months = [
            read_month(f'20{text.strip()}', '기준 달', raw=text)
            for text in update_dates if text is not None and text.strip() not in ('', '-')
        ]
    month = next((value for value in months if value), None)
    if month is None:
        keep_unread_dates(held[:1])
    return month
