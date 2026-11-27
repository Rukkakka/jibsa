"""단지 요약 상수: 평당가·실거래 요약 기간, 재건축 단계 이름, 평형을 하나 줄 때만 붙이는 칸."""

from typing import Literal


# 평당가(complex/pyeongPrice/pyeongType)를 묻는 단지 유형: 아파트 A01·오피스텔 A02·재건축 A04·아파트분양권 B01·오피스텔분양권 B02.
# 단지형 빌라(A05~A07)는 웹이 이 박스를 쓰는지 몰라 묻지 않는다. 웹 단지 화면 ComplexAreaPrice 는 pricePerPyeong 이 없으면
# 박스를 그리지 않는다 (2026-11-18 번들 청크 b042d8aace_1okty1145x932)
PRICE_PER_PYEONG_COMPLEX_TYPES: frozenset[str] = frozenset({'A01', 'A02', 'A04', 'B01', 'B02'})


# 평당가를 묻는 거래 유형. 출력 키 → 요청 값 (월세(B2)는 서버가 pricePerPyeong 키 없이 빈 목록을 줘 묻지 않는다, 2026-11-18 확인)
PRICE_PER_PYEONG_TRADE_TYPES: dict[str, Literal['A1', 'B1']] = {'sale': 'A1', 'jeonse': 'B1'}


# 평당가 지역 단위 (서버 legalDivisionLevelType)
PRICE_PER_PYEONG_LEVEL_LABELS: dict[str, str] = {'SI': '시·도', 'GUN': '시·군·구', 'EUP': '읍·면·동'}


# 실거래 요약 기간. 웹 단지 화면 실거래 요약(ComplexTransactionPriceSummary)과 같다. 비면 5년
REAL_PRICE_SUMMARY_YEARS: int = 3


REAL_PRICE_SUMMARY_FALLBACK_YEARS: int = 5


# 요약에 덧붙이는 최근 평균 기간 (웹 매물 상세 RecentTransaction 의 '3개월 평균 실거래' 와 같은 요청)
REAL_PRICE_RECENT_MONTHS: int = 3


# 재건축 단지 유형. 이 유형이면 사업 단계를 함께 묻는다
RECONSTRUCTION_CODE: str = 'A04'


RECONSTRUCTION_STEP_LABELS: dict[str, str] = {
    '01': '기본계획수립', '02': '안전진단', '03': '구역지정', '04': '추진위승인', '05': '조합설립인가',
    '06': '사업시행인가', '07': '관리처분인가', '08': '이주 및 철거', '09': '착공 및 분양', '10': '준공', '11': '이전고지',
}


"""재건축 사업 단계 코드 (사이트 COMPLEX_RECONSTRUCTION_STEP, 2026-10-10 확인)."""


# 단지 요약에서 --pyeong 을 하나만 줄 때만 붙이는 평형 정보
PYEONG_SCOPED_FIELDS: frozenset[str] = frozenset({'pyeong_manage_cost', 'estimated_prices', 'trade_summary', 'asking_price_per_pyeong'})
