"""당근 GraphQL 응답 풀기·커서 이어 받기·부분 실패 안내와 서버 코드 → 라벨 변환."""

from collections.abc import Mapping

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.notes import (
    UPDATE_MAYBE_NEEDED,
    UPDATE_NEEDED,
)
from jibsa.core.ratelimit import RateLimitedError
from jibsa.providers.daangn.api.models.response.common import (
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)
from jibsa.providers.daangn.service.common.constants import (
    PERSISTED_QUERY_REJECTED_CODES,
)

from typing import TypeVar


T = TypeVar('T')


class FeedQueryRejectedError(JibsaError):
    """GraphQL 이 persisted query 해시를 거절했을 때. 웹이 쿼리를 바꿨다는 신호다.

    대체 경로나 따로 안내할 말이 있는 곳(단지 후보, 지도 범위·출퇴근 검색 등)은 이 예외를 먼저 잡아 처리하고,
    따로 처리하지 않은 명령은 `JibsaError` 라 `UPSTREAM_ERROR` 로 나간다.

    Args:
        codes: GraphQL 이 준 에러 코드 (예: PERSISTED_QUERY_NOT_IN_LIST).
        what: 에러 메시지에 쓸 조회 이름 (예: '매물 피드'). Defaults to '조회'.
    """

    def __init__(self, codes: str, what: str = '조회') -> None:
        super().__init__(
            code='UPSTREAM_ERROR',
            message=f'당근 {what} API 가 바뀌어(웹 쿼리 해시 거절) 조회할 수 없습니다 ({codes})',
            hint=f'{UPDATE_NEEDED}. 그동안 같은 조회가 다른 소스(직방·네이버·다방)에 있으면 그 소스를 쓰세요',
        )


def code_label(labels: Mapping[str, str], code: str | None) -> str | None:
    """서버 코드를 한국어 라벨로. 빈 글자·'-'·None 은 모름(None), 표에 없는 코드는 원래 코드 그대로.

    `labels.get(code or '', code)` 로 쓰면 당근이 '' 나 '-' 로 비워 준 값이 그대로 나가 모름(null)이 아니라 빈 값이 된다.
    표에 없는 코드는 당근이 새 값을 올린 것이라 버리지 않고 원래 코드를 낸다.

    Args:
        labels: 서버 코드 → 라벨 표.
        code: 서버가 준 코드.
    """
    stripped = (code or '').strip()
    if stripped in ('', '-'):
        return None
    return labels.get(stripped, stripped)


def unwrap_graphql(response: DaangnGraphQLResponseModel, value: T | None, what: str, *, conditions: bool) -> T:
    """GraphQL 응답에서 결과(`value`, 응답의 `data` 에서 꺼낸 값)를 꺼낸다.

    Args:
        response: GraphQL 응답.
        value: `response.data` 에서 꺼낸 결과. 없으면 None.
        what: 에러 메시지에 쓸 조회 이름 (예: '매물 피드').
        conditions: 그 조회의 요청 변수에 사용자가 고른 매물 조건(`propertyFilter`)이나 단지 조건(`complex_filter_of` 가 만든
            필터)이 들어가면 True. 웹 기본 종류처럼 jibsa 가 채운 값은 세지 않는다. 호출하는 쪽이 사용자 조건에서 바로 만든
            필터로 판정한다(`is_empty_property_filter`, `has_complex_conditions`). 잘못된 조건 조합도 이유 없이 GraphQL 에러로
            와서, True 일 때만 조건을 줄이라고 권한다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR). 잘못된 조건 조합도 이유 없이 여기로 온다.
    """
    codes = {(error.extensions or {}).get('code') for error in response.errors}
    if codes & PERSISTED_QUERY_REJECTED_CODES:
        raise FeedQueryRejectedError(', '.join(sorted(code for code in codes if code)), what)
    if response.errors or value is None:
        message = next((error.message for error in response.errors if error.message), None)
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'당근 {what} 조회가 실패했습니다' + (f': {message}' if message else ''),
            hint='조건을 줄여 다시 시도하거나, 잠시 뒤 다시 시도하세요' if conditions else '잠시 뒤 다시 시도하세요',
        )
    return value


def partial_failure_note(exc: Exception, what: str, missing: str) -> str:
    """덤으로 받는 조회가 실패했을 때 `notes` 에 붙일 안내. 이미 받은 결과는 버리지 않고 이 안내만 붙인다.

    주된 결과를 받는 조회가 실패하면 쓰지 않고 에러로 끝낸다. 실패 이유마다 다음 행동이 달라
    (업데이트·기다리기·다시 시도) 이유를 문구에 넣는다. 거절(4xx)은 사이트가 바뀌었거나 막은 것이라 기다려도 풀리지 않아
    업데이트 안내를 붙인다 (직방·다방 `lookup_failure_reason` 과 같은 갈래, 2026-11-20 사용자 결정).
    업데이트 안내를 붙이는 갈래는 `needs_update` 와 같다. 한쪽을 바꾸면 다른 쪽도 바꾼다.

    Args:
        exc: 조회가 낸 예외 (`OPTIONAL_LOOKUP_ERRORS` 중 하나).
        what: 조회 이름 (예: '단지 검색').
        missing: 받지 못한 것, 조사까지 (예: '단지 후보를').
    """
    if isinstance(exc, FeedQueryRejectedError):
        return f'당근 {what} API 가 바뀌어(웹 쿼리 해시 거절) {missing} 받지 못했습니다. {UPDATE_NEEDED}'
    if isinstance(exc, RateLimitedError):
        return f'요청 제한에 걸려 {missing} 받지 못했습니다. {exc.message}'
    if isinstance(exc, JibsaError) and exc.code == 'UPSTREAM_ERROR':
        # unwrap_graphql 의 GraphQL 에러. 서버 5xx 는 HTTPStatusError 로 와서 여기 오지 않는다
        return f'{missing} 받지 못했습니다: {exc.message}. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
    if isinstance(exc, JibsaError):
        return f'{missing} 받지 못했습니다: {exc.message}'
    if isinstance(exc, ValueError):
        return (
            f'당근 {what} 응답이 예상한 형식이 아니라 {missing} 받지 못했습니다. '
            f'차단 페이지이거나 API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
        )
    # core is_rejected 와 같은 기준 (4xx 는 거절)
    if isinstance(exc, HTTPStatusError) and exc.response.status_code < 500:
        return (
            f'당근이 {what} 요청을 거절해(HTTP {exc.response.status_code}) {missing} 받지 못했습니다. '
            f'API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
        )
    return f'당근 {what} 요청이 실패해 {missing} 받지 못했습니다 ({type(exc).__name__}). 잠시 뒤 다시 시도하세요'


def next_cursor(page_info: DaangnPageInfoModel | None, after: str | None, *, received: int) -> str | None:
    """다음 페이지가 있다는 쪽에서 이어 받을 커서. 빈 쪽·커서 없음·같은 커서 되풀이면 None 이라 그만 받는다.

    단지 후보·지역 단지·단지 매물·실거래 목록과 매물 목록(`connection_edges`)이 함께 쓴다. 호출부는 `has_next_page` 를 먼저
    보고 부르며, None 이면 멈춘 까닭을 안내한다. 목록 끝은 늘 항목과 함께 hasNextPage=False 로 와서(2026-11-10 실측: 역삼동 지역 단지 113곳 3쪽·
    헬리오시티 단지 후보 100곳 2쪽, 단지가 0곳인 서화면·북면은 edges 0·False), 다음이 있다면서 빈 쪽을 주면 끝이 아니라
    비정상이다. 그래서 '목록 끝' 으로 조용히 넘기지 않는다.

    네 목록(단지 후보·지역 단지·단지 매물·실거래)의 반복문을 커서 반복자 하나로 모으지 않는다. 반복문마다 --limit 예산을
    세는 법(단지 후보는 node, 지역 단지·단지 매물은 edge), 멈춤 밖의 끝 조건(실거래 --years 기간), 실패 처리(단지 후보는 받은
    데까지 돌려줌, 단지 매물은 단지가 없으면 NOT_FOUND)가 달라 반복자가 그만큼 갈래를 받아야 한다. 멈춤 판단만 `stalled_page`(세기 전)와 이 함수(센 뒤)에 모아 반복문마다 같은 자리에서 부른다
    (2026-11-11 리뷰가 반복자로 모으자고 했다).

    Args:
        page_info: 방금 받은 쪽의 페이지 정보.
        after: 그 쪽을 요청할 때 쓴 커서.
        received: 그 쪽에서 받은 쓸 수 있는 항목 수. node 가 null 인 edge 는 세지 않고, 매물 목록(`connection_edges`)은 node 안의
            `article` 이 null 인 edge 도 세지 않는다. 호출부마다 edge 수와 node 수를 섞어 넘기면 같은 쪽을 한쪽은 빈 쪽으로 멈추고 한쪽은
            계속 받는다 (2026-11-10 리뷰. 그날 실측 응답에는 null node 가 없었다: 헬리오시티 단지 후보 2쪽).
    """
    if not received or page_info is None or not page_info.end_cursor or page_info.end_cursor == after:
        return None
    return page_info.end_cursor


def stalled_page(page_info: DaangnPageInfoModel | None, after: str | None) -> bool:
    """다음이 있다던 쪽 뒤에 받은 쪽이 셀 수 없는 쪽인지. 호출부는 그 쪽을 세기 전에 멈춘다 (`cursor_stopped_note`).

    호출부는 다음이 있다는 쪽에서만 `after` 로 다음 쪽을 받으므로, `after` 가 있으면 앞 쪽이 다음이 있다고 한 것이다.
    그 뒤에 받은 쪽이 아래 둘 중 하나면 멈춘다.

    - 페이지 정보가 없다(null). 목록 끝은 늘 hasNextPage=False 로 오므로(`next_cursor`) 응답이 바뀐 것이다. 이 검사가 없을
      때는 다섯 목록 모두 has_more false 로 조용히 끝내 받은 일부를 전부처럼 냈다 (2026-11-11 리뷰·실측: 강남구 지역 실거래
      --limit 60 의 2쪽만 pageInfo null 로 바꾸니 50건·has_more false 에 멈춤 안내가 없었다).
    - 다음이 있다면서 요청한 커서를 그대로 돌려줬다. `next_cursor` 도 되풀이를 보지만 그 쪽을 센 뒤라, 되풀이된 쪽이
      --limit 의 남은 몫을 채우면 멈춤이 아니라 --limit 에 닿은 것으로 알렸다 (2026-11-10 리뷰: 지역 단지 --limit 100 의
      2쪽이 1쪽 50곳을 되풀이하면 '앞 50곳만 보여 줍니다. 더 보려면 --limit 을 늘리거나'). 다음이 없다는 마지막 쪽은
      되풀이로 보지 않는다 (실거래 `collect_pages` 주석의 실측).
    """
    if after is None:
        return False
    if page_info is None:
        return True
    return bool(page_info.has_next_page) and page_info.end_cursor == after


def cursor_stopped_note(subject: str, received: str) -> str:
    """`next_cursor` 가 None 이라 멈췄을 때 안내의 본문 (태그와 다음에 할 일은 호출부가 붙인다).

    목록 끝은 늘 hasNextPage=False 로 오므로(`next_cursor`) 응답이 바뀌었을 수 있다. 업데이트 문구를 넣어 매일 API 감시가
    결과가 비지 않은 날에도 고장으로 센다 (2026-11-10 리뷰: 2쪽에서 멈춘 역삼동 단지 50곳이 감시에서 정상으로 넘어갔다).

    태그와 다음 할 일을 여기서 정하지 않는 것은 멈춤이 결과에 끼치는 영향이 목록마다 달라서다. 단지 후보·지역 단지·단지
    매물은 못 받은 것이 결과에서 빠져 [일부] 다. 실거래는 멈춘 까닭을 [참고] 로, 더 있다는 말과 사이트 안내를 [일부] 하나로
    따로 낸다. 매물 목록(`connection_edges`: 동·지도 범위·역·대학 주변, 출퇴근 역별 매물)은 --limit 을 늘려도 같은 자리에서
    멈춰 [일부] 다 (2026-11-10 리뷰가 태그를 여기서 고르자고 했으나, 실측 출력으로 보니 다른 것은 위 차이 때문이었다).

    Args:
        subject: 무엇의 목록인지 (예: '단지 후보').
        received: 멈출 때까지 받은 수와 단위 (예: '50곳').
    """
    return (
        f'당근이 {subject} 다음 페이지가 있다고 하면서 이어 받을 페이지를 주지 않아 {received}에서 멈췄습니다. '
        f'API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'
    )
