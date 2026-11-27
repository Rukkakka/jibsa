"""네이버 동네 추이의 상수: 기간 이름표, 평형대 하한과 폭, 전국 이름·코드."""

from jibsa.providers.naver.api.request.trend import (
    NaverTrendOffset,
)


TREND_PERIOD_BY_NAME: dict[str, NaverTrendOffset] = {
    '1개월': 'P-1M',
    '6개월': 'P-6M',
    '1년': 'P-1Y',
    '3년': 'P-3Y',
    '5년': 'P-5Y',
}


# 평형대 하한 (평)과 폭. 사이트처럼 10평 단위로 하한~하한+10 평
TREND_PYEONG_RANGES: tuple[int, ...] = (10, 20, 30, 40, 50)


TREND_PYEONG_RANGE_WIDTH: int = 10


# 전국 추이. 웹 홈 아파트 동향의 시·도 '전체' 가 `ALL_LEGAL_DIVISION_CODE` 를 세 엔드포인트의 legalDivisionNumber 로 보낸다
# (2026-11-18 번들 청크 2d10adcfe2_2rlr6s-93gudx). 세 엔드포인트 모두 200 이고 값이 있다
NATIONWIDE_NAME: str = '전국'


NATIONWIDE_CODE: str = '0000000000'
