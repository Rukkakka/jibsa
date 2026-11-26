"""요청 모델: 단지 매물 목록·매물 상세가 같이 쓰는 것."""

from pydantic import (
    Field,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
)


class NaverArticleRequestParameterModel(RequestModel):
    """매물 계열 GET 엔드포인트가 공유하는 쿼리. 이름이 `articleId` 가 아님에 주의."""

    article_number: Annotated[
        str,
        Field(pattern=r'^\d+$', description='매물 번호', alias='articleNumber')
    ]


class NaverArticleAgentV1RequestParameterModel(NaverArticleRequestParameterModel):
    """`GET /front-api/v1/article/agent` 쿼리."""
