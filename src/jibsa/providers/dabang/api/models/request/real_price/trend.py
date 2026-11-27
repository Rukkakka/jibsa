"""요청 모델: 평형 하나의 시세 흐름 (price-trend)."""
from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
)

from typing import (
    Annotated,
)


class DabangRealPriceComplexChartsV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-price/complex/charts` 쿼리 (평형 하나의 36달 시세 흐름).

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
