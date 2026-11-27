"""직방 상세 404 처리: 상세 요청의 404 를 만료 매물 에러로 바꾼다."""

from collections.abc import Generator
from contextlib import contextmanager

from httpx import HTTPStatusError

from jibsa.core.errors import ListingUnavailableError


@contextmanager
def unavailable_on_404(listing_id: int | str, reason: str | None = None) -> Generator[None, None, None]:
    """상세 요청의 404 를 만료 매물(`ListingUnavailableError`)로 바꾼다. 그 밖의 HTTP 오류는 그대로 낸다.

    Args:
        listing_id: 매물 ID.
        reason: 직방 매물인 것을 알고 부른 상세면 그 사유. 없으면 다른 소스 ID 일 수 있다는 안내가 붙는다.
    """
    try:
        yield
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ListingUnavailableError('zigbang', listing_id, reason=reason) from None
        raise
