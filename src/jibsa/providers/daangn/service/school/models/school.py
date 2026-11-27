"""`school.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import DaangnRegionComplex

from typing import Annotated


class DaangnSchool(BaseModel):
    """학교 정보 (학교알리미 공시 기준). 전화·홈페이지·좌표는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='당근 학교 코드 (school 에 다시 넘길 수 있다)')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    school_type: Annotated[
        str | None,
        Field(description='초등학교 / 중학교 / 고등학교 / 기타')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    foundation: Annotated[
        str | None,
        Field(description='설립 구분 (공립, 사립 ...)')
    ] = None
    coed: Annotated[
        str | None,
        Field(description='남녀공학 / 남학교 / 여학교')
    ] = None
    students: Annotated[
        int | None,
        Field(description='전체 학생 수')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    base_year: Annotated[
        int | None,
        Field(description='학생 수 기준 연도 (예: 2026). 당근이 주지 않으면 null')
    ] = None


class DaangnSchoolResult(Result):
    """학교 정보와 배정 단지.

    `notes`: 배정 단지 안내 (중·고등학교, 정보 없음, 조건·limit 으로 줄임, 조건을 확인할 수 없어 뺀 단지). CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    school: Annotated[
        DaangnSchool,
        Field(description='학교')
    ]
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 배정 단지 수 (limit 적용 전. 당근이 단지 ID 를 주지 않아 complexes 에서 뺀 단지도 센다). 당근이 배정 단지를 주지 않았거나 빈 항목을 줬거나, 단지 유형·세대수를 몰라 조건을 확인할 수 없는 단지가 있으면 null (모름)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex] | None,
        Field(description='배정 단지 (당근 웹 학교 화면과 같은 순서). recent_trades 는 최근 매매 1건이다. 배정 단지가 없으면 [], 당근이 배정 단지를 주지 않았으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 학교 페이지')
    ]
