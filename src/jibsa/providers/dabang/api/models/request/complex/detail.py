"""요청 모델: 단지 정보 (complex)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    DabangComplexV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.request.complex.common import (
    DabangComplexCategory,
)

from typing import (
    Annotated,
)


class DabangComplexSummaryV5RequestParameterModel(RequestModel):
    """`GET /api/v5/complex/{complex_type}/summary` 쿼리. 경로 가운데에 단지 ID 가 아니라 소문자 유형이 들어간다
    (단지 ID 를 넣으면 403 빈 응답, 2026-10-25 실측).

    Args:
        complex_type: 'apt' 또는 'officetel' (경로).
        complex_id: 단지 ID.
    """

    complex_type: Annotated[
        DabangComplexCategory,
        Field(exclude=True, description='단지 유형 (경로)')
    ]
    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]


class DabangComplexLoanCalcConditionV5RequestParameterModel(DabangComplexV5RequestParameterModel):
    """`GET /api/v5/complex/{complex_id}/loan-calc-condition` 의 경로 값 (단지 대출 계산 조건). 웹 단지 화면이 단지 상세 뒤에
    바로 부른다 (complex 청크 `je`, 2026-11-13 웹 캡처).

    Args:
        complex_id: 단지 ID (28자리 16진수).
    """
