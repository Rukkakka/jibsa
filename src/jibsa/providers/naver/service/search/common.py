"""지도 매물 검색·지역 단지 목록이 같이 쓰는 것: 범위 필터 변환, 정렬 목록의 지도 줌."""

from jibsa.providers.naver.api.models.request.common import (
    NaverRangeModel,
)


def filter_range(low: float | None, high: float | None, scale: int = 1) -> NaverRangeModel | None:
    """하한·상한을 서버 필터 범위로 바꾼다. 둘 다 없으면 None (키째 빠져 제한 없음)."""
    if low is None and high is None:
        return None
    return NaverRangeModel(
        min=None if low is None else low * scale,
        max=None if high is None else high * scale,
    )


def bounded_precision(radius_km: float) -> int:
    """정렬 목록(boundedArticles·boundedComplexes)에 보낼 지도 줌. 반경을 다 덮는 가장 높은 줌이다.

    줌이 높을수록 사각형을 다 주지 않고 중심 근처만 준다. 모델 기본값 16 이면 반경 2km 부터 가장자리 매물이 빠져,
    빠진 매물만 조건에 맞을 때 '0건이 전부' 라고 냈다 (2026-10-31 강남역 2km 아파트 전세 5억 이하 + 500세대 이상:
    줌 16 0건, 지도 칸 매물(clusteredArticles) 6건). 같은 날 강남역 아파트 전세 4~5억의 반경 안 매물 수:
    1.5km 줌 16·15 모두 10건, 2km 줌 16 21건·15 33건·14 33건, 3km 줌 15 60건·14 62건·13 62건.
    단지 목록도 같다 (3km 아파트 단지 total 줌 16 242곳, 14 1,048곳). 줌을 더 낮추면 반경 밖 매물이 섞여 `--limit`
    몫을 쓴다 (1km 줌 14 는 51건 중 22건이 반경 밖, 줌 16 과 반경 안 수가 같음). 재개발 구역 목록은 따로 14 를 쓴다.
    """
    if radius_km <= 1.5:
        return 16
    if radius_km <= 2:
        return 15
    return 14
