"""다방 400 사유 읽기와 없는 ID 판정."""
from httpx import HTTPStatusError

from jibsa.core.http import error_body
from jibsa.providers.dabang.service.common.constants import MISSING_ID_MESSAGE


def error_message(exc: HTTPStatusError) -> str | None:
    """다방 400 본문의 사유 ("존재하지 않는 단지입니다." 등). 없거나 JSON 이 아니면 None."""
    message = (error_body(exc) or {}).get('msg')
    return message if isinstance(message, str) else None


def is_missing_id(exc: HTTPStatusError, *, in_path: bool = True) -> bool:
    """사용자 ID 로 묻는 요청의 '없는 ID' 응답인지: 사유가 '존재하지 않…' 인 400, 404, 그리고 ID 가 경로에 들어가는 요청이면
    본문이 빈 403.

    다방은 요청 형식 오류도 400 으로 준다 ("줌은 필수값 입니다.", 2026-10-28 실측: 매물 상세·매물번호를 쿼리 없이 물으면
    "사용이 중지된 버전입니다."). 사유를 보지 않으면 다방이 필수 값을 늘렸을 때 모든 ID 가
    '없는 ID' 로 끝나고, 매일 감시도 매물 상세의 LISTING_UNAVAILABLE 은 고장으로 세지 않아 바뀐 것을 놓친다. 그래서 다른
    사유의 400 은 부르는 쪽이 다시 던져 UPSTREAM_ERROR 가 된다.

    다방은 없는 주소에 404 대신 403 빈 응답을 준다. 요청 제한(429)과 다르다 (2026-10-25 실측: 아무 경로나
    `/api/v5/room-list/category/one-two/nothing-here` 를 넣어도 403 빈 본문). 클라이언트(`raise_for_status`) 한 곳에서 바꾸지
    않고 사용자 ID 로 묻는 요청만 부른다.

    ID 가 쿼리로 가는 요청(`in_path=False`)은 없는 ID 에 403 을 주지 않는다 (2026-10-27 실측: 분양 `detail2?id=` 는 400,
    `transit/near`·`real-price/house/history` 는 빈 결과, `region?code=99999` 는 다른 지역). 그 403 은 다방 주소가 바뀐
    것이라 UPSTREAM_ERROR 로 두어야 '없는 ID' 로 오해하지 않고 매일 감시도 고장으로 본다. 본문이 있는 403 은 차단 페이지일 수
    있어 어느 쪽이든 없는 ID 로 보지 않는다 (부르는 쪽이 다시 던져 UPSTREAM_ERROR 가 된다).
    """
    status = exc.response.status_code
    if status == 400:
        return MISSING_ID_MESSAGE in (error_message(exc) or '')
    return status == 404 or (in_path and status == 403 and not exc.response.content.strip())
