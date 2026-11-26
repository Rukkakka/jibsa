"""요청 모델: 지역 안 단지 목록 (search complexes)."""
from pydantic import (
    model_validator,
)

from jibsa.providers.dabang.api.request.common import (
    DabangCategoryListRequestParameterModel,
)

from typing import (
    Self,
)


class DabangComplexListCategoryV5RequestParameterModel(DabangCategoryListRequestParameterModel):
    """`GET /api/v5/complex-list/category/{category}/{search_type}` 쿼리 (단지 지도 목록, 아파트·오피스텔)."""

    @model_validator(mode='after')
    def complex_category(self) -> Self:
        if self.category not in ('apt', 'officetel'):
            raise ValueError(f'단지 목록은 아파트·오피스텔만 있습니다: {self.category}')
        return self
