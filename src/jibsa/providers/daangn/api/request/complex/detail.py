"""요청 모델: 단지 정보·단지 매물 (complex, search listings --complex)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnPropertyFilterModel,
)

from typing import (
    Annotated,
)


class DaangnComplexesRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/complexes/{originalId}` 경로."""

    original_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='숫자 단지 ID (PropComplex.originalId)')
    ]



class DaangnComplexArticlesInputModel(RequestModel):
    """단지 매물 목록의 `input`."""

    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)



class DaangnComplexArticlesRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId { complex { articles } }` 쿼리 변수 (웹의 `ComplexArticleListPanelQuery`).

    루트 필드가 단지 실거래가와 같은 `complexByOriginalId` 라 action id 는 `complex_articles` 로 구분한다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 매물 수. 웹은 10')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnComplexArticlesInputModel,
        Field(description='매물 조건')
    ] = Field(default_factory=DaangnComplexArticlesInputModel)
