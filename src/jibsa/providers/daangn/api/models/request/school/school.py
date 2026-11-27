"""요청 모델: 학교 (school)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnSearchSchoolsInputModel(RequestModel):
    """`searchSchools` 의 `input`."""

    name: Annotated[
        str,
        Field(min_length=1, description="학교 이름 (일부만 줘도 된다. '역삼초등학교' 로 '서울역삼초등학교' 가 나온다)")
    ]


class DaangnSearchSchoolsRequestPayloadModel(RequestModel):
    """GraphQL `searchSchools` 쿼리 변수 (웹의 `fetchSchoolSearchResultQuery`, 학교 이름 검색)."""

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 학교 수')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnSearchSchoolsInputModel,
        Field(description='검색어')
    ]


class DaangnSchoolByCodeRequestPayloadModel(RequestModel):
    """GraphQL `schoolByCode` 쿼리 변수 (웹의 `SchoolDetailQuery`, 학교 정보와 배정 단지)."""

    sch_cd: Annotated[
        str,
        Field(min_length=1, description='학교 코드 (searchSchools 의 schCd, 예: B100000775)', alias='schCd')
    ]
