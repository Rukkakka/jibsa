from pydantic import Field

from jibsa.core.schema import ResponseModel

from typing import Annotated


class DabangEducationV3ResponseModel(ResponseModel):
    """`GET /api/3/education/{level}/{school_code}` 응답 (옛 방식이라 봉투 없이 snake_case).

    학급당·교원당 학생 수와 방과후 프로그램 수는 이 학교 값과 시·도(`_state`)·시·군·구(`_city`) 평균이 함께 온다.
    진학은 중학교가 고등학교 유형별, 고등학교가 대학·취업 등으로 수와 비율(`_ratio`, %)이 온다 (2026-10-25 서일중·
    단국대사대부고·대곡초). 전화(`tel`)·홈페이지·좌표(`location`)도 오지만 모델에 두지 않는다. 개교일(`establish_date`)과
    개교기념일은 '1986.21' 처럼 달이 맞지 않는 값이라 두지 않는다.
    """

    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    base_date: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기 기준')")
    ] = None
    establish_divide: Annotated[
        str | None,
        Field(description="설립 ('국공립', '사립')")
    ] = None
    address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    office_edu_name: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = None
    state_name: Annotated[
        str | None,
        Field(description="시·도 ('서울특별시')")
    ] = None
    city_name: Annotated[
        str | None,
        Field(description="시·군·구 ('강남구')")
    ] = None
    avg_students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    avg_students_per_class_state: Annotated[
        float | None,
        Field(description='시·도 평균 학급당 학생 수')
    ] = None
    avg_students_per_class_city: Annotated[
        float | None,
        Field(description='시·군·구 평균 학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    students_per_teacher_state: Annotated[
        float | None,
        Field(description='시·도 평균 교원 1인당 학생 수')
    ] = None
    students_per_teacher_city: Annotated[
        float | None,
        Field(description='시·군·구 평균 교원 1인당 학생 수')
    ] = None
    afterschool_program: Annotated[
        float | None,
        Field(description='방과후 프로그램 수 (초등학교는 대개 null)')
    ] = None
    afterschool_program_state: Annotated[
        float | None,
        Field(description='시·도 평균 방과후 프로그램 수')
    ] = None
    afterschool_program_city: Annotated[
        float | None,
        Field(description='시·군·구 평균 방과후 프로그램 수')
    ] = None
    enter_regular_high_school: Annotated[
        int | None,
        Field(description='일반고 진학 인원 (중학교)')
    ] = None
    enter_regular_high_school_ratio: Annotated[
        float | None,
        Field(description='일반고 진학률 (%)')
    ] = None
    enter_characterization_high_school: Annotated[
        int | None,
        Field(description='특성화고 진학 인원 (중학교)')
    ] = None
    enter_characterization_high_school_ratio: Annotated[
        float | None,
        Field(description='특성화고 진학률 (%)')
    ] = None
    total_enter_special_high_school: Annotated[
        int | None,
        Field(description='특목고 진학 인원 (중학교)')
    ] = None
    total_enter_special_high_school_ratio: Annotated[
        float | None,
        Field(description='특목고 진학률 (%)')
    ] = None
    total_enter_autonomous_high_school: Annotated[
        int | None,
        Field(description='자율고 진학 인원 (중학교)')
    ] = None
    total_enter_autonomous_high_school_ratio: Annotated[
        float | None,
        Field(description='자율고 진학률 (%)')
    ] = None
    enter_science_high_school_ratio: Annotated[
        float | None,
        Field(description='과학고 진학률 (%, 특목고 안)')
    ] = None
    enter_foreign_high_school_ratio: Annotated[
        float | None,
        Field(description='외국어고 진학률 (%, 특목고 안)')
    ] = None
    enter_art_physical_high_school_ratio: Annotated[
        float | None,
        Field(description='예술·체육고 진학률 (%, 특목고 안)')
    ] = None
    enter_autonomous_private_high_school_ratio: Annotated[
        float | None,
        Field(description='자사고 진학률 (%, 자율고 안)')
    ] = None
    enter_university: Annotated[
        int | None,
        Field(description='대학교 진학 인원 (고등학교)')
    ] = None
    enter_university_ratio: Annotated[
        float | None,
        Field(description='대학교 진학률 (%)')
    ] = None
    enter_college: Annotated[
        int | None,
        Field(description='전문대학 진학 인원 (고등학교)')
    ] = None
    enter_college_ratio: Annotated[
        float | None,
        Field(description='전문대학 진학률 (%)')
    ] = None
    total_enter_foreign: Annotated[
        int | None,
        Field(description='국외 진학 인원 (고등학교)')
    ] = None
    total_enter_foreign_ratio: Annotated[
        float | None,
        Field(description='국외 진학률 (%)')
    ] = None
    enter_employed: Annotated[
        int | None,
        Field(description='취업 인원 (고등학교)')
    ] = None
    enter_employed_ratio: Annotated[
        float | None,
        Field(description='취업률 (%)')
    ] = None
    etc_unknown: Annotated[
        int | None,
        Field(description='기타 인원 (고등학교, 재수 등)')
    ] = None
    etc_unknown_ratio: Annotated[
        float | None,
        Field(description='기타 비율 (%)')
    ] = None
    link_url: Annotated[
        str | None,
        Field(description='학교알리미 공시 페이지')
    ] = None
