"""응답 모델: 매물 상세 (listing)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import DaangnArticleModel

from typing import Annotated


class DaangnArticlesResponseModel(ResponseModel):
    """상세 페이지에서 추출한 매물."""

    title: Annotated[
        str | None,
        Field(description='JSON-LD Product.name (예: 역삼동 9평 단독/전원주택 월세 1,000 / 85만원)')
    ] = None
    article: Annotated[
        DaangnArticleModel,
        Field(description='매물 상세')
    ]
