"""단지 정보·단지 매물이 같이 쓰는 함수: 단지 유형 읽기."""
from jibsa.providers.dabang.api.request.complex.base import DabangComplexCategory
from jibsa.providers.dabang.api.response.common import DabangComplexResultModel


def category_of(result: DabangComplexResultModel) -> DabangComplexCategory:
    """단지 상세의 유형 (아파트·오피스텔). 단지 매물·요약 요청의 경로 값이다."""
    return 'officetel' if result.complex.complex_type == 'OFFICETEL' else 'apt'
