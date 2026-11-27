"""`university.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from typing import (
    Annotated,
)


class DaangnUniversity(BaseModel):
    """웹 지도 검색창의 대학 검색(`searchSchoolPois`)으로 찾은 대학 캠퍼스 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='캠퍼스까지 붙인 대학 이름 (예: 연세대학교 신촌캠퍼스). 당근이 캠퍼스 이름을 주지 않으면 대학 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    lat: Annotated[
        float,
        Field(description='대학 위도')
    ]
    lng: Annotated[
        float,
        Field(description='대학 경도')
    ]
    university_id: Annotated[
        str,
        Field(exclude=True, description='당근 대학 ID (대학 주변 매물 조회에 쓴다)')
    ]
    cut: Annotated[
        bool,
        Field(exclude=True, description='대학 검색이 후보 상한에서 잘려 이름이 같은 캠퍼스가 더 있을 수 있다 (안내에 쓴다)')
    ] = False
