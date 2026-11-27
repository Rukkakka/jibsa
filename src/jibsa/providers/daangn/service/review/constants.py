from jibsa.providers.daangn.api.client import DAANGN_WEB_URL


"""동네 후기 요약(region-reviews)의 상수: --top 기본값·최대값과 후기 페이지가 주는 단지 수."""

# `--top`(후기 많은 단지·건물 수)의 기본값과 최대값. 동 후기 페이지가 단지를 500곳까지 준다
TOP_DEFAULT: int = 20


TOP_MAX: int = 500


# 당근 후기 페이지가 단지를 주는 수. 구 후기 페이지와 구가 없는 시(세종)의 동 페이지는 20곳(reviewsDistrictQuery first:20),
# 동 후기 페이지는 500곳이다 (2026-11-20 실측: 역삼동 260곳 중 후기가 있는 단지 154곳)
DISTRICT_PAGE_COMPLEXES: int = 20


DONG_PAGE_COMPLEXES: int = 500
# 출력 url 칸의 건물 거주 후기 웹 페이지 주소 틀 (`.format(건물 번호)`)
REVIEW_BUILDING_URL: str = f'{DAANGN_WEB_URL}/lived-reviews/buildings/{{}}'
