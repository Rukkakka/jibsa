"""학교 상세 (school)."""
import re

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import normalize_address
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.school import (
    DabangEducationV3RequestParameterModel,
    DabangSchoolLevelPath,
)
from jibsa.providers.dabang.api.response.school import DabangEducationV3ResponseModel
from jibsa.providers.dabang.service.common import (
    SchoolLevel,
    is_missing_id,
)

from typing import (
    Annotated,
    Any,
)


# 학교알리미 학교 코드 ('S010000743'). 경로에 들어가 영문·숫자만 받는다
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(r'^[A-Za-z0-9]+$')
LEVEL_PATH_BY_LABEL: dict[SchoolLevel, DabangSchoolLevelPath] = {
    '초등학교': 'elementary-school',
    '중학교': 'middle-school',
    '고등학교': 'high-school',
}


class DabangSchoolAverage(BaseModel):
    """지역 평균 (비교용)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='지역 (서울특별시, 강남구 ...)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    afterschool_programs: Annotated[
        float | None,
        Field(description='방과후 프로그램 수')
    ] = None


class DabangAdvancement(BaseModel):
    """진학 한 갈래."""

    model_config = ConfigDict(
        extra='forbid',
    )

    destination: Annotated[
        str,
        Field(description=(
            '진학 갈래. 중학교: 일반고·특성화고·특목고·자율고, 그 안의 과학고·외국어고·예술체육고(특목고)·자사고(자율고). '
            '고등학교: 대학교·전문대학·국외·취업·기타'
        ))
    ]
    count: Annotated[
        int | None,
        Field(description='인원 (명). 특목고·자율고 안의 갈래는 다방이 비율만 줘서 null')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='졸업생 중 비율 (%)')
    ] = None


class DabangSchoolDetail(BaseModel):
    """학교 하나의 학교알리미 공시 (다방 제공). 진학은 중·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드')
    ]
    level: Annotated[
        SchoolLevel,
        Field(description='초등학교 / 중학교 / 고등학교')
    ]
    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    establishment: Annotated[
        str | None,
        Field(description='설립 (국공립, 사립)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    office_of_education: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = None
    stats_period: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기')")
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    afterschool_programs: Annotated[
        float | None,
        Field(description='방과후 프로그램 수 (초등학교는 대개 null)')
    ] = None
    city_average: Annotated[
        DabangSchoolAverage,
        Field(description='시·도 평균')
    ]
    district_average: Annotated[
        DabangSchoolAverage,
        Field(description='시·군·구 평균')
    ]
    advancement: Annotated[
        list[DabangAdvancement] | None,
        Field(description='졸업생 진학 (중·고등학교). 초등학교는 키가 없다')
    ] = None
    url: Annotated[
        str | None,
        Field(description='학교알리미 공시 페이지 URL')
    ] = None

    @model_serializer(mode='wrap')
    def drop_elementary_advancement(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level == '초등학교':
            data.pop('advancement', None)
        return data


def _advancement(school: DabangEducationV3ResponseModel, level: SchoolLevel) -> list[DabangAdvancement] | None:
    if level == '중학교':
        rows: list[tuple[str, int | None, float | None]] = [
            ('일반고', school.enter_regular_high_school, school.enter_regular_high_school_ratio),
            ('특성화고', school.enter_characterization_high_school, school.enter_characterization_high_school_ratio),
            ('특목고', school.total_enter_special_high_school, school.total_enter_special_high_school_ratio),
            ('자율고', school.total_enter_autonomous_high_school, school.total_enter_autonomous_high_school_ratio),
            ('과학고', None, school.enter_science_high_school_ratio),
            ('외국어고', None, school.enter_foreign_high_school_ratio),
            ('예술체육고', None, school.enter_art_physical_high_school_ratio),
            ('자사고', None, school.enter_autonomous_private_high_school_ratio),
        ]
    elif level == '고등학교':
        rows = [
            ('대학교', school.enter_university, school.enter_university_ratio),
            ('전문대학', school.enter_college, school.enter_college_ratio),
            ('국외', school.total_enter_foreign, school.total_enter_foreign_ratio),
            ('취업', school.enter_employed, school.enter_employed_ratio),
            ('기타', school.etc_unknown, school.etc_unknown_ratio),
        ]
    else:
        return None
    return [DabangAdvancement(destination=name, count=count, percent=percent) for name, count, percent in rows]


def get_school(client: DabangClient, school_code: str, level: SchoolLevel) -> DabangSchoolDetail:
    """학교 하나의 학교알리미 공시 (요청 1회). 전화·홈페이지·좌표는 옮기지 않는다.

    Raises:
        JibsaError: 다방이 학교를 주지 않을 때 (4xx 는 NOT_FOUND). 단계와 코드가 맞지 않거나 없는 코드면 다방이 500 을
            줘서, 서버 고장과 가르지 못해 UPSTREAM_ERROR(status 500)로 두고 hint 로 입력을 다시 보게 한다.
    """
    try:
        school = client.run_request_education_v3(
            DabangEducationV3RequestParameterModel(level=LEVEL_PATH_BY_LABEL[level], school_code=school_code)
        )
    except HTTPStatusError as exc:
        status = exc.response.status_code
        hint = (
            'complex 결과 schools[] 의 school_code 와 level 을 그대로 옮기세요 (jibsa dabang school <school_code> '
            '--level <level>)'
        )
        if is_missing_id(exc):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방에서 학교를 찾지 못했습니다: {level} {school_code} (HTTP {status})',
                hint=hint,
            ) from None
        # 단계와 코드가 맞지 않거나 없는 코드면 404 대신 500 "일시적으로 서비스가 지연" 을 준다. 서버 고장도 같은 응답이라
        # (2026-10-25 실측: 휘문중 S010000736 을 고등학교로, 없는 코드 S999999999 를 중학교로 물어도 같은 본문) 없는 학교로
        # 단정하지 않는다. 서버 오류로 두어야 매일 감시도 다방이 잠깐 아픈 날을 '확인 못 함'으로 본다
        if status == 500:
            raise JibsaError(
                code='UPSTREAM_ERROR',
                message=f'다방이 학교 상세에 서버 오류를 주었습니다: {level} {school_code} (HTTP 500)',
                hint=f'다방은 코드나 단계가 틀려도 500 을 줍니다. {hint}. 그대로 옮겼다면 잠시 후 다시 시도하세요',
                details={'status': status},
            ) from None
        raise
    return DabangSchoolDetail(
        school_code=school_code,
        level=level,
        name=school.name,
        establishment=school.establish_divide,
        address=normalize_address(school.address),
        office_of_education=school.office_edu_name,
        stats_period=school.base_date.removesuffix('기준').strip() if school.base_date else None,
        students_per_class=school.avg_students_per_class,
        students_per_teacher=school.students_per_teacher,
        afterschool_programs=school.afterschool_program,
        city_average=DabangSchoolAverage(
            region=school.state_name,
            students_per_class=school.avg_students_per_class_state,
            students_per_teacher=school.students_per_teacher_state,
            afterschool_programs=school.afterschool_program_state,
        ),
        district_average=DabangSchoolAverage(
            region=school.city_name,
            students_per_class=school.avg_students_per_class_city,
            students_per_teacher=school.students_per_teacher_city,
            afterschool_programs=school.afterschool_program_city,
        ),
        advancement=_advancement(school, level),
        url=school.link_url,
    )
