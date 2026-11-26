"""지도 매물 검색·지역 단지 목록이 같이 쓰는 것."""

from jibsa.providers.naver.api.request.common import (
    NaverRangeModel,
)


def _filter_range(low: float | None, high: float | None, scale: int = 1) -> NaverRangeModel | None:
    """하한·상한을 서버 필터 범위로 바꾼다. 둘 다 없으면 None (키째 빠져 제한 없음)."""
    if low is None and high is None:
        return None
    return NaverRangeModel(
        min=None if low is None else low * scale,
        max=None if high is None else high * scale,
    )
