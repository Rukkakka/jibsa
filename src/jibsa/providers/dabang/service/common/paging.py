"""다방 목록 쪽 넘김 따라가기와 더 있다·멈췄다·제외 안내."""
from collections.abc import Callable
from math import ceil

from jibsa.core.korean import particle
from jibsa.core.notes import (
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.models.response.common import (
    DabangRoomItemModel,
    DabangRoomListResultModel,
)
from jibsa.providers.dabang.service.common.constants import (
    MAX_LIST_LIMIT,
    PAGE_SIZE,
    REGION_INFO_MAX_LIMIT,
)
from jibsa.providers.dabang.service.common.models import (
    DabangPage,
    DabangPages,
    T,
)

from typing import Any


def more_after(server_has_more: bool, rows: int, *, cut: int = 0) -> bool:
    """다방 목록 한 쪽 뒤에 더 있는지.

    limit 에 맞춰 잘라 내고 쓰지 않은 줄(`cut`)이 있으면 서버 hasMore 와 상관없이 더 있다. 잘라 낸 줄이 없으면 서버 hasMore 를
    따르되, 빈 쪽(`rows` 0)이면 hasMore 가 와도 더 없다고 본다 (빈 쪽을 상한까지 묻고 '다방에 더 있음' 이라고 잘못 알리지
    않게, 2026-11-14 리뷰).

    Args:
        server_has_more: 서버가 준 hasMore.
        rows: 그 쪽에 온 줄 수. 빈 항목(null)만 와서 뺀 쪽은 빈 쪽이 아니라 뺀 수까지 더해 준다.
        cut: limit 에 맞춰 잘라 내고 쓰지 않은 줄 수. Defaults to 0.
    """
    return cut > 0 or (server_has_more and rows > 0)


def room_list_page(result: DabangRoomListResultModel) -> tuple[DabangPage[DabangRoomItemModel], int]:
    """매물 목록 응답 한 쪽을 (그 쪽, 함께 온 광고 수) 로.

    광고는 첫 쪽에만 와서 쪽마다 더해도 같은 광고를 두 번 세지 않는다 (2026-10-28 실측: 역삼동 원룸 1~3쪽 광고 8·0·0건).
    """
    # 광고 칸에서 뺀 빈 항목도 광고가 있던 자리라 광고 수에 센다
    premium = sum(len(group.room_list) + group.null_items('room_list') for group in result.premium_list)
    return DabangPage(result.room_list, result.total, bool(result.has_more), result.null_items('room_list')), premium


def fetch_pages(
    fetch: Callable[[int], DabangPage[T] | None],
    limit: int,
    *,
    page: int = 1,
    skip: int = 0,
    page_size: int = PAGE_SIZE,
    max_limit: int = MAX_LIST_LIMIT,
) -> DabangPages[T]:
    """다방 목록(매물·단지 매물·단지·분양, 동네정보 학교·핫플레이스)을 `page` 쪽의 `skip` 칸 뒤부터 `limit` 줄이 찰 때까지 다음 쪽으로 따라간다.

    다방 목록은 번호 쪽 넘김이고 한 쪽이 늘 `PAGE_SIZE` 건은 아니다 (2026-11-13 웹 캡처: 아파트 강남역 1쪽 23건, 대치동 2쪽
    23건). 그래서 쪽 수를 `limit` 을 쪽 크기로 나눠 정하지 않고 `limit` 이 찰 때까지 받으며(상한은 아래 `max_pages`), 이어 받을
    위치도 받은 수로 셈하지 않고 읽은 쪽과 그 쪽에서 쓴 칸으로 둔다. 다음 쪽은 서버 hasMore 로만 본다. 받은 수가 쪽 크기보다
    적다고 끝내면 남은 것을 놓친다. 빈 쪽이면 hasMore 가 와도 더 묻지 않는다 (빈 쪽을 상한까지 묻고 '다방에 더 있음' 이라고
    잘못 알리지 않게). 다방이 목록에 섞어 줘서 뺀 빈 항목(`DabangPage.dropped`)은 `limit` 의 줄로 세지 않는다. 다만 서버의
    칸이라 빈 쪽을 가를 때와 이어 받은 위치의 칸 수(`DabangPages.dropped_used`)에는 더한다.

    Args:
        fetch: 쪽 번호 → 그 쪽. 결과가 없으면(`result` 가 null) None 이고 거기서 멈춘다 (has_more 는 그 전 값. 처음 물은 쪽이면
            이어 받기인지).
        limit: 받을 줄 수.
        page: 처음 물을 쪽. Defaults to 1.
        skip: 그 쪽에서 앞 결과가 이미 쓴 칸 수. Defaults to 0.
        page_size: 그 목록의 한 쪽 크기 (동네정보 목록은 30줄). Defaults to `PAGE_SIZE`.
        max_limit: 그 명령의 --limit 최대값. 쪽 수 상한을 정한다. Defaults to `MAX_LIST_LIMIT`.
    """
    # 쪽은 쪽 크기보다 짧을 수 있어(2026-11-14 강남역 아파트 반경 3km 6~8쪽 22·22·21건) --limit 이 찰 때까지 다음 쪽을 받되,
    # 끝없이 묻지 않게 --limit 최대값을 꽉 찬 쪽으로 채우는 쪽 수의 두 배에서 멈춘다. 멈췄는데 다방에 더 있으면
    # `fetch_stop_notes` 로 알린다
    max_pages = 2 * ceil(max_limit / page_size)
    rows: list[T] = []
    total: int | None = None
    # 이어 받는 위치(1쪽 처음이 아님)는 앞 결과가 다방에 더 있다고 했을 때만 만든다. 그래서 처음 물은 쪽이 None 이면 처음 부른
    # 것은 끝(잘린 것이 아님)이고, 이어 받은 것은 잘린 것이다. 이어 받기도 같은 위치의 next 를 그대로 남겨 앞 결과의 안내와 맞춘다
    # (2026-11-14 리뷰: 이어 받은 첫 쪽이 null 이면 next·안내 없이 '다 받았다' 로 끝났다)
    has_more = page > 1 or skip > 0
    capped = False
    cut_short = False
    dropped = dropped_used = 0
    for _ in range(max_pages):
        got = fetch(page)
        if got is None:
            cut_short = has_more
            break
        if total is None:
            total = got.total
        dropped += got.dropped
        remaining = got.rows[skip:]
        taken = remaining[:limit - len(rows)]
        rows += taken
        if len(taken) < len(remaining):
            # 쪽 중간에서 몫을 채웠다. 남은 칸이 있어 더 있고, 다음에는 같은 쪽의 남은 칸부터 받는다
            skip += len(taken)
            has_more = True
            break
        # 쪽을 다 썼다 (앞 결과가 쓴 칸보다 쪽이 짧아졌으면 남은 칸이 없다). 다음에는 다음 쪽 처음부터 받는다. 빈 항목만 온 쪽은
        # 빈 쪽이 아니다
        dropped_used += got.dropped
        has_more = more_after(got.has_more, len(got.rows) + got.dropped)
        page, skip = page + 1, 0
        if not has_more or len(rows) >= limit:
            break
    else:
        capped = True
    return DabangPages(rows, total, has_more, capped, cut_short, page, skip, page_size, max_pages, dropped, dropped_used)


def fetch_stop_notes(
    pages: DabangPages[Any],
    limit: int,
    *,
    cap_next: str,
    cut_next: str = '다시 찾아 보세요',
    unit: str = '건',
) -> list[str]:
    """`fetch_pages` 가 `limit` 을 못 채우고 멈췄는데 다방에 더 있을 때의 안내. 그렇지 않으면 빈 목록.

    목록의 [일부] 안내(`limit_notes` 등)는 받은 수가 `limit` 보다 적으면 다 받은 것으로 보고 안내하지 않아, 그대로 두면 더
    있는데 적게 받은 이유를 모른다 (2026-11-14 리뷰). 두 경우는 함께 일어나지 않는다.

    - 쪽 수 상한(`pages.max_pages`)까지 받음 (`pages.capped`). 쪽이 `pages.page_size` 보다 짧게 와야 닿는다.
    - 앞 쪽이 hasMore 인데 다방이 다음 쪽 결과를 주지 않음(result null) (`pages.cut_short`).

    Args:
        pages: `fetch_pages` 가 받은 쪽 모음. 받은 수는 뺀 것까지 센 `len(pages.rows)` 다.
        limit: 요청한 수.
        cap_next: 쪽 수 상한에서 이어서 할 일 (예: `NEXT_HINT`, `narrow_again(...)`).
        cut_next: 다음 쪽 결과가 없을 때 이어서 할 일. Defaults to '다시 찾아 보세요'.
        unit: 세는 단위 (단지·분양·학교·핫플레이스는 '곳'). Defaults to '건'.
    """
    received = len(pages.rows)
    if pages.capped:
        object_particle = particle(unit, '을/를')
        return [note(
            '일부',
            f'다방이 쪽을 {pages.page_size}{unit}보다 짧게 줘 {pages.max_pages}쪽까지 {received}{unit}{object_particle} 받고 '
            f'멈췄습니다 (요청 {limit}{unit}, 다방에 더 있음). {cap_next}',
        )]
    if pages.cut_short:
        return [note(
            '일부', f'다방이 다음 쪽 결과를 주지 않아 {received}{unit}에서 멈췄습니다 (요청 {limit}{unit}, 다방은 더 있다고 했음). {cut_next}',
        )]
    return []


def narrow_again(narrow: str) -> str:
    """쪽 수 상한 안내(`fetch_stop_notes`)의 cap_next. 좁힐 조건 이름 뒤에 조사를 맞춘다 (예: '설립 구분(--establishment) 조건을 좁혀 다시 찾으세요')."""
    return f"{narrow}{particle(narrow, '을/를')} 좁혀 다시 찾으세요"


def more_list_notes(
    pages: DabangPages[Any],
    limit: int,
    *,
    seen: str,
    max_limit: int,
    narrow: str | None,
) -> list[str]:
    """'곳' 으로 세는 목록(단지·분양·동네정보)이 다방의 전부가 아닐 때의 안내. 다 받았으면 빈 목록.

    멈춤 안내(`fetch_stop_notes`)가 있으면 그것만 돌려준다. 없으면 `has_more` 만 본다: `fetch_pages` 는 limit 을 채웠거나(쪽
    중간에서 끊음 포함) 다방에 더 없을 때만 상한·끊김 없이 끝나므로, 멈춤 안내가 없고 has_more 면 받은 수가 limit 이상이다.
    그래서 '[일부]' 와 멈춤 안내는 함께 나오지 않는다 (`fetch_stop_notes` 와 같다).

    Args:
        pages: `fetch_pages` 가 받은 쪽 모음.
        limit: 요청한 수.
        seen: 마침표 없는 '본 것' 문장 (예: '역삼동 어린이집 23곳 중 다방 목록 순으로 앞 1곳입니다').
        max_limit: 그 명령의 --limit 최대값.
        narrow: 좁히라고 권할 조건 (예: '설립 구분(--establishment) 조건'). 좁힐 옵션을 아직 고르지 않았을 때만 좁히라고
            권하므로 이미 골랐으면 None.
    """
    # 쪽 수 상한까지 받고도 limit 을 못 채웠으면 --limit 을 늘려도 같은 곳에서 멈춘다 (narrow 가 None 일 때)
    stop = fetch_stop_notes(
        pages, limit, cap_next=narrow_again(narrow) if narrow else '--limit 을 늘려도 같은 곳에서 멈춥니다', unit='곳',
    )
    if stop:
        return stop
    if not pages.has_more:
        return []
    return [note('일부', f'{seen}. {more_hint(limit, max_limit, narrow)}')]


def region_info_list_notes(pages: DabangPages[Any], limit: int, *, subject: str, narrow: str | None) -> list[str]:
    """동네정보 목록(search schools·hot-places)이 다방의 전부가 아닐 때의 안내. 다 받았으면 빈 목록.

    받은 줄과 결과 줄이 1:1 이라 `len(pages.rows)` 가 결과 수다.

    Args:
        pages: `fetch_pages` 가 받은 쪽 모음.
        limit: 요청한 수.
        subject: 안내 앞머리 (예: '역삼동 어린이집', '역삼동 핫플레이스').
        narrow: 좁히라고 권할 조건 (예: '설립 구분(--establishment) 조건'). 좁힐 옵션을 아직 고르지 않았을 때만 좁히라고
            권하므로 이미 골랐으면 None.
    """
    # 다방이 total 을 null 로 줘도 hasMore 면 알린다 (2026-11-14 리뷰)
    among = f'{pages.total}곳 중 ' if pages.total is not None else ''
    dropped = [null_items_note(f'다방 {subject}', pages.dropped)] if pages.dropped else []
    return dropped + more_list_notes(
        pages, limit, seen=f'{subject} {among}다방 목록 순으로 앞 {len(pages.rows)}곳입니다',
        max_limit=REGION_INFO_MAX_LIMIT, narrow=narrow,
    )


def duplicate_note(count: int, *, what: str = '매물', unit: str = '건') -> list[str]:
    """다방 목록에 두 번 나온 줄을 한 번만 넣었다는 안내."""
    if count <= 0:
        return []
    return [note('제외', f'다방 목록에 두 번 나온 {what} {count}{unit}은 한 번만 넣었습니다 (다시 채우지 않음)')]
