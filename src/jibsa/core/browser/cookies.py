"""명령이 끝날 때 남기고 다음 명령이 이어 쓰는 쿠키 (`<state_dir>/browser/<source>.json`)와 첫 화면이 쿠키를 다 심었는지 보는 판정."""

import json
from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import Path
from urllib.parse import urlsplit

from jibsa.core.state import state_dir

from typing import Any


# ready_cookie 가 생긴 뒤에도 쿠키가 이 시간 동안 더 바뀌지 않아야 다 심은 것으로 본다. 사이트는 쿠키를 몇백 ms 에 걸쳐 나눠
# 심어, ready_cookie 만 보고 멈추면 뒤의 것을 놓쳤다 (2026-11-10 네이버 실측: 처음 열면 NNB 와 NAC·NACT 가 같은 200ms 안에
# 생겨 NNB 만 본 jibsa 는 6개만 남겼고, 다시 열면 BUC·SRT5 0.2초 뒤에 NAC·NACT. 그 뒤 2초쯤 BUC 만 한 번 더 바뀐다)
READY_COOKIE_SETTLE_SECONDS: float = 0.5
# 첫 화면을 다시 여는 간격. 네이버 세션 쿠키 SRT30 의 수명(30분)과 같다. 사람이 30분 넘게 쉬었다 들어오면 첫 화면부터
# 여는 것과 같은 모양이고, 에이전트가 명령을 몰아 쓰면 첫 화면은 30분에 한 번만 열린다
REFRESH_SECONDS: float = 1800


class EntryCookies:
    """새로 연 첫 화면이 쿠키를 다 심었는지 본다 (`_launch` 가 load 뒤 `READY_COOKIE_POLL_MS` 마다 부른다).

    `ready_cookie` 가 있고, 이번 방문에서 사이트가 쿠키를 하나라도 심거나 바꿨고(넣어 둔 `returning` 뿐이면 사이트 JS 가 아직
    돌지 않은 것이다. ready_cookie 를 넣어 두고 다시 열면 처음부터 있다), 그 뒤 `READY_COOKIE_SETTLE_SECONDS` 동안 더
    바뀌지 않았으면 다 심은 것이다. `ready_cookie` 가 없는 소스는 기다리지 않는다.
    """

    def __init__(self, ready_cookie: str | None, returning: Sequence[Mapping[str, object]]) -> None:
        self.ready_cookie = ready_cookie
        self.returning = _cookie_keys(returning)
        self.last: frozenset[tuple[object, ...]] | None = None
        self.changed_at = 0.0

    def ready(self, cookies: Sequence[Mapping[str, object]], now: float) -> bool:
        if self.ready_cookie is None:
            return True
        keys = _cookie_keys(cookies)
        if keys != self.last:
            self.last, self.changed_at = keys, now
        return (
            has_cookie(cookies, self.ready_cookie) and bool(keys - self.returning)
            and now - self.changed_at >= READY_COOKIE_SETTLE_SECONDS
        )


def has_cookie(cookies: Sequence[Mapping[str, object]], name: str) -> bool:
    return any(cookie.get('name') == name for cookie in cookies)


def state_path(source: str) -> Path:
    return state_dir() / 'browser' / f'{source}.json'


def load_state(source: str) -> dict[str, Any]:
    """남긴 쿠키 상태. 없거나 깨졌으면 빈 상태라 첫 화면부터 연다. 쓰기는 원자적이라 잠그지 않고 읽는다."""
    try:
        data = json.loads(state_path(source).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def usable_cookies(
    state: Mapping[str, Any], entry_url: str, ready_cookie: str | None, now: float
) -> list[dict[str, Any]] | None:
    """남긴 쿠키로 바로 요청해도 되면 아직 살아 있는 쿠키, 첫 화면을 다시 열어야 하면 None.

    첫 화면을 연 지 `REFRESH_SECONDS` 가 지났거나, 시각이 앞뒤가 안 맞거나, 남긴 페이지 주소가 지금 첫 화면(`entry_url`)과
    출처가 다르거나, `ready_cookie` 가 없거나 만료됐으면 다시 연다. 출처를 보는 것은 jibsa 를 업데이트해 첫 화면 출처가
    바뀌었을 때 옛 주소로 띄우면 `finish_entry` 가 다른 출처로 보고 명령을 실패시키기 때문이다.

    `ready_cookie` 가 없는 상태는 첫 화면이 `READY_COOKIE_TIMEOUT_SECONDS` 안에 그 쿠키를 심지 못한 것이다. 이어 쓰지 않고
    다음 명령이 첫 화면을 다시 열어 쿠키를 받게 한다. 일부러 그렇다: 그 쿠키는 사이트가 사람 브라우저마다 심는 식별 쿠키라
    (네이버 `NNB`) 없는 채로 30분을 이어 보내는 것보다 다시 여는 쪽이 사람 방문과 같다. 늦게 심는 환경이면 명령마다 첫 화면
    요청(네이버 18~22건)이 더 나가지만 `RateLimiter.record` 로 세어 요청 제한은 지킨다. 실측으로는 2초 안에 생긴다.
    """
    opened_at, page_url, cookies = state.get('opened_at'), state.get('page_url'), state.get('cookies')
    # 빼지 않고 비교만 한다. 상태 파일에 실수로 바꿀 수 없을 만큼 큰 정수가 있으면 `now - opened_at` 이 OverflowError 를
    # 내 그 소스의 모든 명령이 INTERNAL_ERROR 로 실패했다 (2026-11-23 리뷰·재현). 비교는 크기와 상관없이 터지지 않는다
    if not isinstance(opened_at, (int, float)) or not now - REFRESH_SECONDS < opened_at <= now:
        return None
    if not isinstance(page_url, str) or not isinstance(cookies, list) or origin(page_url) != origin(entry_url):
        return None
    alive = [
        cookie for cookie in cookies
        if isinstance(cookie, dict) and isinstance(cookie.get('name'), str)
        and not (isinstance(cookie.get('expires'), (int, float)) and 0 < cookie['expires'] <= now)
    ]
    if ready_cookie is not None and not has_cookie(alive, ready_cookie):
        return None
    return alive


def returning_cookies(state: Mapping[str, Any], entry_url: str, now: float) -> list[dict[str, Any]]:
    """첫 화면을 다시 열 때 먼저 넣을 쿠키. 남긴 쿠키 중 만료 시각이 있고 아직 살아 있는 것(방문자 식별 쿠키 등)이다.

    브라우저를 닫았다 다시 들어온 사람과 같게, 닫으면 사라지는 세션 쿠키(만료 시각 없음)는 넣지 않는다. 아무것도 넣지
    않으면 30분마다 사이트가 400일짜리 방문자 쿠키를 새로 심었다 (2026-11-10 실측: 네이버 `NNB`·`BUC` 가 새 값, 넣고 열면
    `NNB` 그대로). 403 으로 버린 쿠키는 파일이 없어 넣지 않고, 남긴 페이지 출처가 지금 첫 화면과 다르면(`usable_cookies` 와
    같은 이유) 넣지 않는다.
    """
    page_url, cookies = state.get('page_url'), state.get('cookies')
    if not isinstance(page_url, str) or not isinstance(cookies, list) or origin(page_url) != origin(entry_url):
        return []
    return [
        cookie for cookie in cookies
        if isinstance(cookie, dict) and isinstance(cookie.get('name'), str)
        and isinstance(cookie.get('expires'), (int, float)) and cookie['expires'] > now
    ]


def _cookie_keys(cookies: Sequence[Mapping[str, object]]) -> frozenset[tuple[object, ...]]:
    return frozenset(
        (cookie.get('name'), cookie.get('domain'), cookie.get('path'), cookie.get('value')) for cookie in cookies
    )


def origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme, parts.netloc
