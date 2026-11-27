"""매물 검색(search listings)의 상수: 쪽 크기·거품 줌·지도 해상도·집계 상한·대학 기본 매물 종류."""

from jibsa.providers.daangn.api.request.common import DaangnSalesType


FEED_PAGE_SIZE: int = 20


# 웹 지도가 동 거품(`articleClusters`, zoomLevel 8)을 그리는 줌. 지역 거품은 줌 8 이상 13 미만에서만 요청하고, 동 거품 줌
# (mapDev `regionDongMinZoom` 12) 미만은 구 거품(7)이다 (2026-11-12 번들 대조: MapView `Mt`·`Pt`·`Ft`, mapDev `s`)
REGION_CLUSTER_ZOOM: int = 12


# 웹이 조건 없는 화면에 기본으로 보내는 매물 종류. 대학 페이지(`UniversityArticleListPanel` 의 `Go`)는 지도 필터가 비었을 때
# 원룸·투룸·오피스텔, 단지 매물 패널(`ComplexArticleListPanel` 의 `F`)은 늘 주거 5종이 기본이다 (2026-11-12 번들 대조).
# 역 주변·동·지도 범위 목록은 빈 목록(전체)이 기본이다
UNIVERSITY_DEFAULT_SALES_TYPES: tuple[DaangnSalesType, ...] = ('ONE_ROOM', 'TWO_ROOM', 'OFFICETEL')


# 웹 데스크톱의 줌 → H3 해상도 (mapDev 의 `T`). 위에서부터 처음 맞는 하한을 쓰고, 다 아니면 `MAP_RESOLUTION_MIN`
MAP_RESOLUTION_BY_ZOOM: tuple[tuple[float, int], ...] = ((17.5, 11), (16.5, 10), (15, 9), (14, 8), (13, 7), (12.5, 6))


MAP_RESOLUTION_MIN: int = 5


# articlesCount 는 이 수에서 잘린다 (웹은 '999+' 로 보여 준다)
COUNT_CAP: int = 1000
