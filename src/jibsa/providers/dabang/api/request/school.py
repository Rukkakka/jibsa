from pydantic import Field

from jibsa.providers.dabang.api.request.common import DabangV3RequestParameterModel

from typing import (
    Annotated,
    Literal,
)


DabangSchoolLevelPath = Literal['elementary-school', 'middle-school', 'high-school']


class DabangEducationV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/education/{level}/{school_code}` 쿼리 (학교 상세, 학교알리미 공시).

    경로의 단계와 학교 코드가 맞지 않거나 없는 코드면 다방이 500 "일시적으로 서비스가 지연되고 있습니다." 를 준다
    (2026-10-25 실측: 초등학교 코드로 중학교 주소, 없는 코드 'S999999999' 모두 500). 그래서 코드만으로 단계를 찾지 않는다.

    Args:
        level: 학교 단계 (경로).
        school_code: 학교 코드 (경로, 학교알리미 'S010000743').
    """

    level: Annotated[
        DabangSchoolLevelPath,
        Field(exclude=True, description='학교 단계 (경로)')
    ]
    school_code: Annotated[
        str,
        Field(exclude=True, pattern=r'^[A-Za-z0-9]+$', description='학교 코드 (경로)')
    ]
