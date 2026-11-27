"""네이버 학교 조회의 상수: 배정 단지 정렬 이름표, 쪽 크기·요청 상한·최대 개수, 배정 동 글자."""

from jibsa.providers.naver.api.client import NAVER_WEB_URL

from typing import Literal


SchoolComplexSortType = Literal['DISTANCE', 'HOUSEHOLD_COUNT']


SCHOOL_COMPLEX_SORT_TYPE_BY_NAME: dict[str, SchoolComplexSortType] = {
    '거리순': 'DISTANCE',
    '세대수순': 'HOUSEHOLD_COUNT',
}


# 학교 배정 단지 목록의 쪽 크기는 웹 학교 상세 화면(DETAIL)과 같은 20 이다 (웹 기본 10, 2026-11-18 실측). 요청은 이 횟수에서
# 멈춘다. 끝 쪽을 넘긴 쪽은 totalCount 가 0 으로 와서 총수는 첫 쪽에서만 믿는다 (`list_school_complexes`)
SCHOOL_COMPLEX_PAGE_SIZE: int = 20


MAX_SCHOOL_COMPLEX_PAGE_REQUESTS: int = 5


MAX_SCHOOL_COMPLEX_LIMIT: int = SCHOOL_COMPLEX_PAGE_SIZE * MAX_SCHOOL_COMPLEX_PAGE_REQUESTS


ALL_DONGS_LABEL: str = '전체 동'
# 출력 url 칸의 초등학교 웹 페이지 주소 틀 (`.format(학교 코드)`)
SCHOOL_URL: str = f'{NAVER_WEB_URL}/schools/elementary/{{}}'
