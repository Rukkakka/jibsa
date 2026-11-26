"""요청 모델: 분양 단지 상세 (sale)."""

from pydantic import (
    Field,
)

from jibsa.providers.dabang.api.request.common import (
    COMPLEX_ID_PATTERN_TEXT,
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
)


class DabangSaleInLotsDetail2V3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/detail2` 쿼리 (분양 단지 하나).

    Args:
        id: 분양 ID (28자리 16진수).
    """

    id: Annotated[
        str,
        Field(pattern=COMPLEX_ID_PATTERN_TEXT, description='분양 ID')
    ]
