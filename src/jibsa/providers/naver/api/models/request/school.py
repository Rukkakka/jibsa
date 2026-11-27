"""요청 모델: 학교 상세와 배정 동 (school)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


class NaverEducationSchoolV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/school` 쿼리. 학교 하나의 상세 (학교알리미 공시)."""

    school_code: Annotated[
        str,
        Field(pattern=r'^[A-Za-z0-9]+$', description='학교 코드 (예: B100000747)', alias='schoolCode')
    ]


class NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/complex/school/allocation-dongs` 쿼리. 단지에서 그 학교에 배정되는 동."""

    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호', alias='complexNumber')
    ]
    school_code: Annotated[
        str,
        Field(pattern=r'^[A-Za-z0-9]+$', description='학교 코드', alias='schoolCode')
    ]
    item_type: Annotated[
        Literal['complex', 'villa'],
        Field(description='단지 종류 (사이트 ArticleSchoolItemType)', alias='itemType')
    ] = 'complex'


class NaverEducationComplexPagesV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/complex/pages` 쿼리. 학교에 배정되는 단지 목록 (학교 상세의 '배정 단지' 칸).

    `sortType` 은 `DISTANCE`·`HOUSEHOLD_COUNT` 만 받는다 (그 밖은 400 FST_ERR_VALIDATION, 웹 enum
    `ELEMENTARY_SCHOOL_SORT_TYPE`, 2026-11-18). 웹 페이지 크기는 기본 10, 상세 화면 20 이다.
    """

    school_code: Annotated[
        str,
        Field(pattern=r'^[A-Za-z0-9]+$', description='학교 코드 (예: B100000898)', alias='schoolCode')
    ]
    size: Annotated[
        int,
        Field(ge=1, description='한 페이지 결과 수 (웹 기본 10, 상세 화면 20)')
    ] = 10
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0
    sort_type: Annotated[
        Literal['DISTANCE', 'HOUSEHOLD_COUNT'],
        Field(description='정렬. DISTANCE 가까운 순, HOUSEHOLD_COUNT 세대수 순', alias='sortType')
    ] = 'DISTANCE'
