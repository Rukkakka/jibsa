"""학교·유치원·어린이집 상세 (school)."""
from collections.abc import Callable

from httpx import HTTPStatusError
from pydantic import BaseModel

from jibsa.core.browser import EntryOpenError
from jibsa.core.errors import JibsaError
from jibsa.core.listing import normalize_address
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.school.detail import (
    DabangEducationKinderSchoolV3RequestParameterModel,
    DabangEducationNurserySchoolV3RequestParameterModel,
    DabangEducationV3RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.school.detail import (
    DabangEducationV3ResponseModel,
)
from jibsa.providers.dabang.service.common.constants import SchoolLevel
from jibsa.providers.dabang.service.common.error import is_missing_id
from jibsa.providers.dabang.service.school.constants import (
    KINDER_GROUPS,
    KINDER_TEACHERS,
    LEVEL_PATH_BY_LABEL,
    NURSERY_GROUPS,
    NURSERY_TEACHERS,
    EducationLevel,
)
from jibsa.providers.dabang.service.school.models import (
    DabangAdvancement,
    DabangChildcareDetail,
    DabangChildGroup,
    DabangSchoolAverage,
    DabangSchoolDetail,
    DabangTeacherGrade,
)

from typing import TypeVar


T = TypeVar('T')


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


def _fetch_education(fetch: Callable[[], T], level: EducationLevel, school_code: str) -> T:
    """학교·유치원·어린이집 상세 요청 하나. 다방 오류를 입력을 다시 보라는 안내로 바꾼다.

    Raises:
        JibsaError: 다방이 시설을 주지 않을 때 (4xx 는 NOT_FOUND). 단계와 코드가 맞지 않거나 없는 코드면 다방이 500 을
            줘서, 서버 고장과 가르지 못해 UPSTREAM_ERROR(status 500)로 두고 hint 로 입력을 다시 보게 한다.
    """
    try:
        return fetch()
    except HTTPStatusError as exc:
        # 첫 화면(다방 홈)의 5xx(`EntryStatusError`)는 상세 응답이 아니다. 아래에서 읽으면 홈 장애를 '코드나 단계가
        # 틀려도 500' 으로 안내했다 (2026-11-10 로컬 실측). 다른 명령처럼 HTTP 오류로 올린다
        if isinstance(exc, EntryOpenError):
            raise
        status = exc.response.status_code
        hint = (
            'complex 결과 schools[] 의 school_code·level, nurseries[]·kindergartens[] 의 school_code, search schools 결과의 '
            'school_code·level 을 그대로 옮기세요 (jibsa dabang school <코드> --level <level>)'
        )
        if is_missing_id(exc):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방에서 {level} 정보를 찾지 못했습니다: {school_code} (HTTP {status})',
                hint=hint,
            ) from None
        # 단계와 코드가 맞지 않거나 없는 코드면 404 대신 500 "일시적으로 서비스가 지연" 을 준다. 서버 고장도 같은 응답이라
        # (2026-10-25 실측: 휘문중 S010000736 을 고등학교로, 없는 코드 S999999999 를 중학교로 물어도 같은 본문. 2026-11-14
        # 실측: 없는 어린이집·유치원 코드도 같다) 없는 시설로 단정하지 않는다. 서버 오류로 두어야 매일 감시도 다방이 잠깐
        # 아픈 날을 '확인 못 함'으로 본다
        if status == 500:
            raise JibsaError(
                code='UPSTREAM_ERROR',
                message=f'다방이 {level} 상세에 서버 오류를 주었습니다: {school_code} (HTTP 500)',
                hint=f'다방은 코드나 단계가 틀려도 500 을 줍니다. {hint}. 그대로 옮겼다면 잠시 후 다시 시도하세요',
                details={'status': status},
            ) from None
        raise


def _stats_period(base_date: str | None) -> str | None:
    return base_date.removesuffix('기준').strip() if base_date else None


def _groups(model: BaseModel, groups: tuple[tuple[str, str], ...]) -> list[DabangChildGroup] | None:
    """원아 구성. 웹처럼 원아가 있는(0 이 아닌) 반·나이만 낸다 (school 청크 `w`·`Ie` 의 `e.class0&&…`).

    다방이 반·나이별 수를 하나도 주지 않으면(모두 None) 모름이라 None 이다. 하나라도 값(0 포함)이 있으면 0 이 아닌 것만 낸다.
    """
    if all(getattr(model, field) is None for _, field in groups):
        return None
    rows: list[DabangChildGroup] = []
    for name, field in groups:
        count = getattr(model, field)
        if count:
            rows.append(DabangChildGroup(group=name, count=count, percent=getattr(model, f'{field}_ratio')))
    return rows


def _teachers(model: BaseModel, grades: tuple[tuple[str, str], ...]) -> list[DabangTeacherGrade]:
    return [DabangTeacherGrade(grade=name, count=getattr(model, field)) for name, field in grades]


def _services(values: list[str] | None) -> list[str] | None:
    # 다방이 null 로 주면 모름(null)이고 빈 목록으로 주면 없음([])이다. 유치원은 ' 특수학급' 처럼 앞에 빈칸이 붙어 온다 (2026-11-14 실측)
    if values is None:
        return None
    return [value.strip() for value in values if value.strip()]


def get_school(client: DabangClient, school_code: str, level: EducationLevel) -> DabangSchoolDetail | DabangChildcareDetail:
    """학교·유치원·어린이집 하나의 공시 (요청 1회). 전화·좌표는 옮기지 않는다 (학교는 홈페이지도).

    Raises:
        JibsaError: 다방이 시설을 주지 않을 때 (`_fetch_education`).
    """
    if level == '어린이집':
        nursery = _fetch_education(
            lambda: client.run_request_education_nursery_school_v3(
                DabangEducationNurserySchoolV3RequestParameterModel(school_code=school_code)
            ),
            level,
            school_code,
        )
        return DabangChildcareDetail(
            school_code=school_code,
            level='어린이집',
            name=nursery.name,
            establishment=nursery.type,
            address=normalize_address(nursery.address),
            base_period=_stats_period(nursery.base_date),
            operating_hours=nursery.operating_time,
            school_bus=nursery.schoolbus,
            children_total=nursery.total_class,
            children=_groups(nursery, NURSERY_GROUPS),
            teachers=_teachers(nursery, NURSERY_TEACHERS),
            children_per_teacher=nursery.child_per_teacher,
            services=_services(nursery.provide_service),
            disclosure_url=nursery.link_url,
        )
    if level == '유치원':
        kinder = _fetch_education(
            lambda: client.run_request_education_kinder_school_v3(
                DabangEducationKinderSchoolV3RequestParameterModel(school_code=school_code)
            ),
            level,
            school_code,
        )
        # 리뷰 오탐 (2026-11-14, 근거 고침 2026-11-20): 단위 글자를 짐작하는 common.count_of 와 달리 숫자만 있는 글자만 받아, 꼴이 바뀌면
        # (예: 1~2) 첫 숫자로 짐작하지 않고 모름(null)으로 둔다. 웹(school 청크 `Ue`)은 글자를 그대로 보인다
        vehicles_text = (kinder.commute_school_car or '').strip()
        return DabangChildcareDetail(
            school_code=school_code,
            level='유치원',
            name=kinder.name,
            establishment=kinder.establish_divide,
            address=normalize_address(kinder.road_address),
            base_period=_stats_period(kinder.base_date),
            operating_hours=kinder.operating_hour,
            school_bus_vehicles=int(vehicles_text) if vehicles_text.isdecimal() else None,
            homepage_url=kinder.homepage or None,
            children_total=kinder.total_current,
            children=_groups(kinder, KINDER_GROUPS),
            teachers=_teachers(kinder, KINDER_TEACHERS),
            children_per_teacher=kinder.child_per_teacher,
            services=_services(kinder.provide_service),
            disclosure_url=kinder.link_url,
        )
    school_level: SchoolLevel = level
    school = _fetch_education(
        lambda: client.run_request_education_v3(
            DabangEducationV3RequestParameterModel(level=LEVEL_PATH_BY_LABEL[school_level], school_code=school_code)
        ),
        level,
        school_code,
    )
    return DabangSchoolDetail(
        school_code=school_code,
        level=school_level,
        name=school.name,
        establishment=school.establish_divide,
        address=normalize_address(school.address),
        office_of_education=school.office_edu_name,
        base_period=_stats_period(school.base_date),
        students_per_class=school.avg_students_per_class,
        students_per_teacher=school.students_per_teacher,
        afterschool_programs=school.afterschool_program,
        sido_average=DabangSchoolAverage(
            region=school.state_name,
            students_per_class=school.avg_students_per_class_state,
            students_per_teacher=school.students_per_teacher_state,
            afterschool_programs=school.afterschool_program_state,
        ),
        sigungu_average=DabangSchoolAverage(
            region=school.city_name,
            students_per_class=school.avg_students_per_class_city,
            students_per_teacher=school.students_per_teacher_city,
            afterschool_programs=school.afterschool_program_city,
        ),
        advancement=_advancement(school, school_level),
        disclosure_url=school.link_url,
    )
