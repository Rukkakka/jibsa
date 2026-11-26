"""요청 모델: 평형대 평당가와 주변 단지 비교 (nearby-complexes)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
)

from typing import (
    Annotated,
)


class DabangRealPriceComplexPricePerPyV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-price/complex/price-per-py` 쿼리 (평형대 평당가와 반경 1km 주변 단지 비교).

    웹 단지 화면 평당가 칸의 기본 탭('N평대 비교')이 고른 평형으로 부른다 (complex 청크 `Ut`, 2026-11-13 웹 캡처:
    `complexId=…&spaceSeq=817`). 없는 평형은 400 '존재하지 않는 평형 정보입니다.' 다 (2026-11-14 실측).

    Args:
        complex_id: 단지 ID.
        space_seq: 평형 번호.
    """

    complex_id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='단지 ID', alias='complexId')
    ]
    space_seq: Annotated[
        int,
        Field(gt=0, description='평형 번호', alias='spaceSeq')
    ]
