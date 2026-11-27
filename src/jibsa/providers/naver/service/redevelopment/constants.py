"""재개발 구역 목록·매물의 상수: 쪽 크기, 요청 상한, 구역 유형 코드, 지도 줌, 정렬 이름표."""

from jibsa.providers.naver.api.client import NAVER_WEB_URL
from jibsa.providers.naver.api.models.request.common import (
    NaverRealEstateType,
)
from jibsa.providers.naver.api.models.request.redevelopment.search import (
    NaverRedevelopmentAreaSortType,
)


REDEVELOPMENT_PAGE_SIZE: int = 30


MAX_REDEVELOPMENT_ARTICLE_PAGE_REQUESTS: int = 5


# 재개발 구역(F01) 목록·매물. 페이지는 30건까지(31부터 400, 2026-10-10 확인). 네이버 목록 공통으로 기본 30·최대 120
REDEVELOPMENT_CODE: NaverRealEstateType = 'F01'


MAX_REDEVELOPMENT_PAGE_REQUESTS: int = 4


# 목록·마커의 지도 줌. 12 이하는 400 이고 높을수록 중심 근처만 준다. 14 는 반경 1·3km 안 구역을 모두 주면서
# 반경 밖은 13 보다 덜 섞인다 (역 3곳 × 반경 2가지 모두 13 과 같은 구역, 15 는 3km 에서 1~4곳 빠짐, 2026-10-10).
# 반경 밖은 마커 좌표로 뺀다
REDEVELOPMENT_PRECISION: int = 14


REDEVELOPMENT_SORT_TYPE_BY_NAME: dict[str, NaverRedevelopmentAreaSortType] = {
    '매물수순': 'ARTICLE_COUNT_DESC',
    '세대수순': 'HOUSEHOLD_NUMBER_DESC',
}
# 출력 url 칸의 재개발 구역 웹 페이지 주소 틀 (`.format(구역 번호)`)
REDEVELOPMENT_URL: str = f'{NAVER_WEB_URL}/redevelopments/{{}}'
