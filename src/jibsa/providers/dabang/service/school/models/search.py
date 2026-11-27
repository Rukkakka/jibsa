"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import Result
from jibsa.providers.dabang.service.common.models import DabangPlace
from jibsa.providers.dabang.service.school.constants import (
    EducationLevel,
)

from typing import (
    Annotated,
    Any,
)


class DabangRegionalAdvancement(BaseModel):
    """동 안 학교 목록의 진학률 한 갈래 (중·고등학교)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    destination: Annotated[
        str | None,
        Field(description="갈래 (다방 이름 그대로: 중학교 '과고'·'외고'·'자사고'·'예고' 등)")
    ] = None
    percent: Annotated[
        float | None,
        Field(description='진학률 (%)')
    ] = None


class DabangRegionalSchool(BaseModel):
    """동 안 학교·유치원·어린이집 하나. 진학률은 중·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드. jibsa dabang school <school_code> --level <level> 로 상세를 본다')
    ]
    level: Annotated[
        EducationLevel,
        Field(description='초등학교 / 중학교 / 고등학교 / 유치원 / 어린이집. school 명령의 --level 값')
    ]
    name: Annotated[
        str | None,
        Field(description='이름')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description="설립 구분 (학교·유치원 '국공립'·'사립', 어린이집 '공공'·'민간'·'가정'·'직장'·'협동'). 모르는 값이면 null")
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    advancement: Annotated[
        list[DabangRegionalAdvancement] | None,
        Field(description='진학률 (중·고등학교, 다방 웹 목록의 꼬리표). 다방이 주지 않으면 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_levels(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level not in ('중학교', '고등학교'):
            data.pop('advancement', None)
        return data


class DabangSchoolListResult(Result):
    """동 안 학교·유치원·어린이집 목록 (다방 동네정보 '학군' 상세 목록, 다방 목록 순).

    `notes`: 일부만 받은 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 동')
    ]
    level: Annotated[
        EducationLevel,
        Field(description='단계')
    ]
    establishment: Annotated[
        str,
        Field(description="고른 설립 구분 (--establishment). 주지 않았으면 '전체'")
    ]
    total: Annotated[
        int | None,
        Field(description='그 동의 그 단계 전체 수 (설립 구분 적용 뒤)')
    ] = None
    returned: Annotated[
        int,
        Field(description='돌려준 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='다방에 더 있는지')
    ]
    schools: Annotated[
        list[DabangRegionalSchool],
        Field(description='학교 (다방 목록 순)')
    ]
