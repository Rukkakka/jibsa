"""요청 모델: 단지 기능(complex)의 상세·검색·인기 단지가 같이 쓰는 것."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
)


class DaangnSearchComplexesInputModel(RequestModel):
    """`searchComplexes` 의 `input`."""

    name: Annotated[
        str,
        Field(min_length=1, description='단지 이름 (일부만 줘도 된다)')
    ]



class DaangnSearchComplexesRequestPayloadModel(RequestModel):
    """GraphQL `searchComplexes` 쿼리 변수 (웹의 `fetchComplexSearchResultQuery`)."""

    input: Annotated[
        DaangnSearchComplexesInputModel,
        Field(description='검색어')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 단지 수. 웹은 20')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
