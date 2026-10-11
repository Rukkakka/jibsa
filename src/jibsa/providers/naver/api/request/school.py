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
        Field(pattern=r'^[A-Za-z0-9]+$', description='학교 코드 (예: B100000747)')
    ] = Field(alias='schoolCode')


class NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/complex/school/allocation-dongs` 쿼리. 단지에서 그 학교에 배정되는 동."""

    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호')
    ] = Field(alias='complexNumber')
    school_code: Annotated[
        str,
        Field(pattern=r'^[A-Za-z0-9]+$', description='학교 코드')
    ] = Field(alias='schoolCode')
    item_type: Annotated[
        Literal['complex', 'villa'],
        Field(description='단지 종류 (사이트 ArticleSchoolItemType)')
    ] = Field(default='complex', alias='itemType')
