"""요청 모델: 매물 상세 (listing)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnArticlesRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/articles/{originalId}` 경로."""

    original_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='숫자 매물 ID (Article.originalId)')
    ]
