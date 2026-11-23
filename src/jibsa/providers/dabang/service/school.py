"""학교·유치원·어린이집 상세 (school) 와 동 안 학교 목록 (search schools)."""
import re
from collections.abc import Callable

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.browser import EntryOpenError
from jibsa.core.errors import JibsaError
from jibsa.core.listing import normalize_address
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import REGION_INFO_PAGE_LIMIT
from jibsa.providers.dabang.api.request.school import (
    SCHOOL_CODE_PATTERN_TEXT,
    DabangEducationKinderSchoolV3RequestParameterModel,
    DabangEducationNurserySchoolV3RequestParameterModel,
    DabangEducationV3RequestParameterModel,
    DabangRegionalSchoolPath,
    DabangRegionInfoSchoolRegionalV5RequestParameterModel,
    DabangSchoolEstablishmentType,
    DabangSchoolLevelPath,
)
from jibsa.providers.dabang.api.response.school import (
    DabangEducationV3ResponseModel,
    DabangRegionalSchoolModel,
)
from jibsa.providers.dabang.service.common import (
    ESTABLISHMENT_BY_LABEL,
    NURSERY_ESTABLISHMENT_BY_LABEL,
    REGION_INFO_MAX_LIMIT,
    ChildcareLevel,
    DabangPage,
    DabangPlace,
    EducationLevel,
    SchoolLevel,
    fetch_pages,
    is_missing_id,
    region_info_list_notes,
)
from jibsa.providers.dabang.service.region import DabangDong

from typing import (
    Annotated,
    Any,
    TypeVar,
)


T = TypeVar('T')

# 학교 코드 (학교 'S010000743', 어린이집 '11680000021', 유치원 UUID). 경로에 들어가 영문·숫자·'-' 만 받는다
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(SCHOOL_CODE_PATTERN_TEXT)
LEVEL_PATH_BY_LABEL: dict[SchoolLevel, DabangSchoolLevelPath] = {
    '초등학교': 'elementary-school',
    '중학교': 'middle-school',
    '고등학교': 'high-school',
}
REGIONAL_PATH_BY_LEVEL: dict[EducationLevel, DabangRegionalSchoolPath] = dict([
    *LEVEL_PATH_BY_LABEL.items(),
    ('유치원', 'kinder-school'),
    ('어린이집', 'nursery-school'),
])
# 어린이집 반 이름 (웹 '원아구성', school 청크 `w`, 2026-11-13). 웹은 원아가 있는 반만 그린다
NURSERY_GROUPS: tuple[tuple[str, str], ...] = (
    ('0세반', 'class_0'),
    ('1세반', 'class_1'),
    ('2세반', 'class_2'),
    ('3세반', 'class_3'),
    ('4세반', 'class_4'),
    ('5세반', 'class_5'),
    ('영아 혼합', 'class_baby_mix'),
    ('유아 혼합', 'class_child_mix'),
    ('영유아 혼합', 'class_baby_child_mix'),
    ('특수/장애아', 'class_special'),
)
# 유치원 나이 이름 (웹 '원아구성', school 청크 `Ie`)
KINDER_GROUPS: tuple[tuple[str, str], ...] = (
    ('만 3세', 'current_three'),
    ('만 4세', 'current_four'),
    ('만 5세 이상', 'current_five_over'),
    ('혼합', 'current_mix'),
)
# 교사 급수 이름 (웹 '교사현황', school 청크 `ee`·`Le`). 웹은 0 명인 급수도 그린다
NURSERY_TEACHERS: tuple[tuple[str, str], ...] = (('1급', 'teacher_1st'), ('2급', 'teacher_2nd'), ('3급', 'teacher_3rd'))
KINDER_TEACHERS: tuple[tuple[str, str], ...] = (
    ('수석교사', 'staff_license_top_teacher'),
    ('정교사 1급', 'staff_license_first_teacher'),
    ('정교사 2급', 'staff_license_second_teacher'),
    ('준교사', 'staff_license_equivalent_teacher'),
)


def establishment_labels(level: EducationLevel) -> dict[str, DabangSchoolEstablishmentType]:
    """그 단계의 설립 구분 이름 → 다방 값 (어린이집만 공공·민간·가정·직장·협동)."""
    return NURSERY_ESTABLISHMENT_BY_LABEL if level == '어린이집' else ESTABLISHMENT_BY_LABEL


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


class DabangChildGroup(BaseModel):
    """원아 구성 한 칸 (어린이집은 반, 유치원은 나이)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    group: Annotated[
        str,
        Field(description="반·나이 (어린이집 '0세반'~'5세반'·'영아 혼합'·'유아 혼합'·'영유아 혼합'·'특수/장애아', 유치원 '만 3세'·'만 4세'·'만 5세 이상'·'혼합')")
    ]
    count: Annotated[
        int,
        Field(description='원아 수 (명)')
    ]
    percent: Annotated[
        float | None,
        Field(description='전체 원아 중 비율 (%)')
    ] = None


class DabangTeacherGrade(BaseModel):
    """교사 급수·자격 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    grade: Annotated[
        str,
        Field(description="급수·자격 (어린이집 '1급'·'2급'·'3급', 유치원 '수석교사'·'정교사 1급'·'정교사 2급'·'준교사')")
    ]
    count: Annotated[
        int | None,
        Field(description='교사 수 (명)')
    ] = None


class DabangChildcareDetail(BaseModel):
    """유치원·어린이집 하나의 공시 (다방 제공: 유치원알리미·어린이집정보공개포털). 다방 웹 상세 화면이 그리는 값이다.

    어린이집에만 `school_bus`, 유치원에만 `school_bus_vehicles`·`homepage` 키가 있다. 유치원 교육비는 다방 값이 유치원알리미
    공시의 학부모 부담금과 맞지 않아 내지 않는다 (원비는 `url` 의 '비용·회계' 에서 본다).
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='시설 코드 (complex 결과 nurseries[]·kindergartens[] 의 code, search schools 결과의 school_code)')
    ]
    level: Annotated[
        ChildcareLevel,
        Field(description='유치원 / 어린이집')
    ]
    name: Annotated[
        str,
        Field(description='이름')
    ]
    establishment: Annotated[
        str | None,
        Field(description="설립 유형 (어린이집 '공공'·'민간'·'가정'·'직장'·'협동', 유치원 '국공립'·'사립')")
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    stats_period: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기')")
    ] = None
    operating_hours: Annotated[
        str | None,
        Field(description="운영 시간 (다방 글 그대로: 어린이집 '평일기준시간 : 07:30 ~ 19:30', 유치원 '09시00분~13시30분')")
    ] = None
    school_bus: Annotated[
        str | None,
        Field(description="통학버스 ('운영', '미운영', 어린이집)")
    ] = None
    school_bus_vehicles: Annotated[
        int | None,
        Field(description="통학 차량 수 (대, 유치원. 유치원알리미 '통학차량 현황'의 운행 차량수라 0 은 통학차량을 운영하지 않는 것이다. 다방 웹은 0 을 '-' 로 쓴다)")
    ] = None
    homepage: Annotated[
        str | None,
        Field(description='홈페이지 (유치원)')
    ] = None
    children_total: Annotated[
        int | None,
        Field(description='원아 수 (명. 어린이집은 반별 원아 수의 합, 유치원은 현원)')
    ] = None
    children: Annotated[
        list[DabangChildGroup] | None,
        Field(description='원아 구성 (원아가 있는 반·나이만, 다방 웹과 같다). 다방이 반·나이별 수를 하나도 주지 않으면 null')
    ] = None
    teachers: Annotated[
        list[DabangTeacherGrade],
        Field(description='교사 급수·자격별 수')
    ] = []
    children_per_teacher: Annotated[
        float | None,
        Field(description='교사 1명당 아동 수')
    ] = None
    services: Annotated[
        list[str] | None,
        Field(description="제공 서비스 (어린이집 '야간연장형'·'일반', 유치원 '방과후 과정' 등). 다방이 주지 않으면 null")
    ] = None
    url: Annotated[
        str | None,
        Field(description="공시 페이지 URL (어린이집정보공개포털·유치원알리미). 유치원 원비는 이 페이지의 '비용·회계' 에서 본다")
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_level_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level == '어린이집':
            for key in ('school_bus_vehicles', 'homepage'):
                data.pop(key, None)
        else:
            data.pop('school_bus', None)
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
            'complex 결과 schools[] 의 school_code·level, nurseries[]·kindergartens[] 의 code, search schools 결과의 '
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
            stats_period=_stats_period(nursery.base_date),
            operating_hours=nursery.operating_time,
            school_bus=nursery.schoolbus,
            children_total=nursery.total_class,
            children=_groups(nursery, NURSERY_GROUPS),
            teachers=_teachers(nursery, NURSERY_TEACHERS),
            children_per_teacher=nursery.child_per_teacher,
            services=_services(nursery.provide_service),
            url=nursery.link_url,
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
            stats_period=_stats_period(kinder.base_date),
            operating_hours=kinder.operating_hour,
            school_bus_vehicles=int(vehicles_text) if vehicles_text.isdecimal() else None,
            homepage=kinder.homepage or None,
            children_total=kinder.total_current,
            children=_groups(kinder, KINDER_GROUPS),
            teachers=_teachers(kinder, KINDER_TEACHERS),
            children_per_teacher=kinder.child_per_teacher,
            services=_services(kinder.provide_service),
            url=kinder.link_url,
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
        stats_period=_stats_period(school.base_date),
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
        advancement=_advancement(school, school_level),
        url=school.link_url,
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


class DabangSchoolListResult(BaseModel):
    """동 안 학교·유치원·어린이집 목록 (다방 동네정보 '학군' 상세 목록, 다방 목록 순)."""

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
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 받은 안내')
    ] = []


def search_schools(
    client: DabangClient,
    dong: DabangDong,
    level: EducationLevel,
    *,
    establishment: str | None,
    limit: int,
) -> DabangSchoolListResult:
    """동 안 학교·유치원·어린이집 목록 (30곳마다 요청 1회). 웹 동네정보 '학군' 상세 목록과 같은 목록·순서·전체 수다.

    Args:
        dong: 찾은 동 (`resolve_dong`).
        establishment: 설립 구분 이름 (`establishment_labels(level)` 의 키). None 이면 전체.
    """
    place, gid = dong
    establishment_type = establishment_labels(level)[establishment] if establishment else None

    def fetch(page: int) -> DabangPage[DabangRegionalSchoolModel] | None:
        result = client.run_request_region_info_school_regional_v5(DabangRegionInfoSchoolRegionalV5RequestParameterModel(
            level=REGIONAL_PATH_BY_LEVEL[level], region_gid=gid, school_establishment_type=establishment_type, page=page,
        )).result
        return DabangPage(result.list_ or [], result.total, bool(result.has_more), result.null_items('list_')) if result else None

    pages = fetch_pages(fetch, limit, page_size=REGION_INFO_PAGE_LIMIT, max_limit=REGION_INFO_MAX_LIMIT)
    # 웹 목록 칩도 같은 표로 바꾸고 모르는 값은 빈 칩이다 (school-regional 청크 `f`). labels 는 다방 값 → 설립 구분 이름
    labels: dict[str, str] = {value: label for label, value in establishment_labels(level).items()}
    schools = [
        DabangRegionalSchool(
            school_code=row.school_code,
            level=level,
            name=row.school_name,
            establishment=labels.get(row.school_establishment_type or ''),
            address=normalize_address(row.address),
            advancement=None if row.advancement_list is None else [
                DabangRegionalAdvancement(destination=item.advancement_type_name, percent=item.advancement_percentage)
                for item in row.advancement_list
            ],
        )
        for row in pages.rows
    ]
    # 좁힐 옵션을 아직 고르지 않았을 때만 좁히라고 권한다
    narrow = '설립 구분(--establishment) 조건' if establishment is None else None
    notes = region_info_list_notes(pages, limit, subject=f'{place.name} {level}', narrow=narrow)
    return DabangSchoolListResult(
        region=place,
        level=level,
        establishment=establishment or '전체',
        total=pages.total,
        returned=len(schools),
        has_more=pages.has_more,
        schools=schools,
        notes=notes,
    )
