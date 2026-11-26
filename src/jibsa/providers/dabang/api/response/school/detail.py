"""응답 모델: 학교·유치원·어린이집 상세 (school)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
)

from typing import Annotated


class DabangEducationV3ResponseModel(DabangBaseResponseModel):
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


class DabangNurseryEducationV3ResponseModel(DabangBaseResponseModel):
    """`GET /api/3/education/nursery-school/{school_code}` 응답 (옛 방식이라 봉투 없이 snake_case, 어린이집정보공개포털 공시).

    `class_0`~`class_5`·혼합반·특수는 반 이름별 원아 수이고 `total_class` 가 그 합(총 원아 수)이다. 웹 '원아구성' 은
    '총 {total_class}명' 과 0 이 아닌 반을 '0세반 9명 9.6%' 로 그린다 (school 청크, 2026-11-13). 전화(`tel`)·좌표(`location`)도
    오지만 모델에 두지 않는다. 개원일(`permission_date`)은 '1998.-0' 처럼 달이 맞지 않는 값이라 두지 않는다 (2026-11-14 실측).
    평가인증(`certification_date`)은 웹이 받아 두기만 하고 화면에 그리지 않아 두지 않는다.
    """

    name: Annotated[
        str,
        Field(description='어린이집 이름')
    ]
    base_date: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기 기준')")
    ] = None
    type: Annotated[
        str | None,
        Field(description="유형 ('공공', '민간', '가정', '직장', '협동')")
    ] = None
    operating_time: Annotated[
        str | None,
        Field(description="운영 시간 ('평일기준시간 : 07:30 ~ 19:30')")
    ] = None
    schoolbus: Annotated[
        str | None,
        Field(description="통학버스 ('운영', '미운영')")
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    provide_service: Annotated[
        list[str] | None,
        Field(description="제공 서비스 ('야간연장형', '일반')")
    ] = None
    total_class: Annotated[
        int | None,
        Field(description='총 원아 수 (명, 반별 원아 수의 합)')
    ] = None
    class_0: Annotated[
        int | None,
        Field(description='0세반 원아 수')
    ] = None
    class_1: Annotated[
        int | None,
        Field(description='1세반 원아 수')
    ] = None
    class_2: Annotated[
        int | None,
        Field(description='2세반 원아 수')
    ] = None
    class_3: Annotated[
        int | None,
        Field(description='3세반 원아 수')
    ] = None
    class_4: Annotated[
        int | None,
        Field(description='4세반 원아 수')
    ] = None
    class_5: Annotated[
        int | None,
        Field(description='5세반 원아 수')
    ] = None
    class_baby_mix: Annotated[
        int | None,
        Field(description='영아 혼합반 원아 수')
    ] = None
    class_child_mix: Annotated[
        int | None,
        Field(description='유아 혼합반 원아 수')
    ] = None
    class_baby_child_mix: Annotated[
        int | None,
        Field(description='영유아 혼합반 원아 수')
    ] = None
    class_special: Annotated[
        int | None,
        Field(description='특수·장애아반 원아 수')
    ] = None
    class_0_ratio: Annotated[
        float | None,
        Field(description='0세반 비율 (%)')
    ] = None
    class_1_ratio: Annotated[
        float | None,
        Field(description='1세반 비율 (%)')
    ] = None
    class_2_ratio: Annotated[
        float | None,
        Field(description='2세반 비율 (%)')
    ] = None
    class_3_ratio: Annotated[
        float | None,
        Field(description='3세반 비율 (%)')
    ] = None
    class_4_ratio: Annotated[
        float | None,
        Field(description='4세반 비율 (%)')
    ] = None
    class_5_ratio: Annotated[
        float | None,
        Field(description='5세반 비율 (%)')
    ] = None
    class_baby_mix_ratio: Annotated[
        float | None,
        Field(description='영아 혼합반 비율 (%)')
    ] = None
    class_child_mix_ratio: Annotated[
        float | None,
        Field(description='유아 혼합반 비율 (%)')
    ] = None
    class_baby_child_mix_ratio: Annotated[
        float | None,
        Field(description='영유아 혼합반 비율 (%)')
    ] = None
    class_special_ratio: Annotated[
        float | None,
        Field(description='특수·장애아반 비율 (%)')
    ] = None
    teacher_1st: Annotated[
        int | None,
        Field(description='보육교사 1급 수')
    ] = None
    teacher_2nd: Annotated[
        int | None,
        Field(description='보육교사 2급 수')
    ] = None
    teacher_3rd: Annotated[
        int | None,
        Field(description='보육교사 3급 수')
    ] = None
    child_per_teacher: Annotated[
        float | None,
        Field(description='교사 1명당 아동 수')
    ] = None
    link_url: Annotated[
        str | None,
        Field(description='어린이집정보공개포털 공시 페이지')
    ] = None


class DabangKinderEducationV3ResponseModel(DabangBaseResponseModel):
    """`GET /api/3/education/kinder-school/{school_code}` 응답 (옛 방식이라 봉투 없이 snake_case, 유치원알리미 공시).

    교육비(`avg_base_cost`·`avg_care_cost`, 원 단위 월 평균)도 오지만 모델에 두지 않는다. 웹은 '지원금을 제외한 실제 학부모에게
    고지하는 금액' 이라고 설명하는데(school 청크 `Xe`), 유치원알리미 공시와 견주면 사립은 공시 부담금이 있어도 0 이고 0 이 아닌
    값은 수업료를 뺀 교재비였다 (2026-11-14 대조: 유치원 8곳). 웹 '통학버스' 칸은 `schoolbus` 가 아니라 통학 차량 수
    (`commute_school_car`, 글자 '2')를 쓰고 '0' 이면 '-' 다. 전화(`tel`)·좌표(`location`)도 오지만 모델에 두지 않는다. 개원일(`anniversary_date`)은 '1996.30' 처럼 달이
    맞지 않는 값이 와서 두지 않는다 (2026-11-14 실측). 정원(`total_approve`)은 웹이 그리지 않아 두지 않는다.
    """

    name: Annotated[
        str,
        Field(description='유치원 이름')
    ]
    base_date: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기 기준')")
    ] = None
    establish_divide: Annotated[
        str | None,
        Field(description="설립 ('국공립', '사립')")
    ] = None
    operating_hour: Annotated[
        str | None,
        Field(description="운영 시간 ('09시00분~13시30분')")
    ] = None
    commute_school_car: Annotated[
        str | None,
        Field(description="통학 차량 수 (글자 '2'). 유치원알리미 '통학차량 현황'의 운행 차량수와 같고 '0' 은 미운영이다 (2026-11-14 대조: 6곳)")
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    homepage: Annotated[
        str | None,
        Field(description='홈페이지')
    ] = None
    provide_service: Annotated[
        list[str] | None,
        Field(description="제공 서비스 ('방과후 과정', ' 특수학급' 처럼 앞에 빈칸이 붙기도 한다)")
    ] = None
    total_current: Annotated[
        int | None,
        Field(description='현원 (명)')
    ] = None
    current_three: Annotated[
        int | None,
        Field(description='만 3세 원아 수')
    ] = None
    current_four: Annotated[
        int | None,
        Field(description='만 4세 원아 수')
    ] = None
    current_five_over: Annotated[
        int | None,
        Field(description='만 5세 이상 원아 수')
    ] = None
    current_mix: Annotated[
        int | None,
        Field(description='혼합반 원아 수')
    ] = None
    current_three_ratio: Annotated[
        float | None,
        Field(description='만 3세 비율 (%)')
    ] = None
    current_four_ratio: Annotated[
        float | None,
        Field(description='만 4세 비율 (%)')
    ] = None
    current_five_over_ratio: Annotated[
        float | None,
        Field(description='만 5세 이상 비율 (%)')
    ] = None
    current_mix_ratio: Annotated[
        float | None,
        Field(description='혼합반 비율 (%)')
    ] = None
    staff_license_top_teacher: Annotated[
        int | None,
        Field(description='수석교사 수')
    ] = None
    staff_license_first_teacher: Annotated[
        int | None,
        Field(description='정교사 1급 수')
    ] = None
    staff_license_second_teacher: Annotated[
        int | None,
        Field(description='정교사 2급 수')
    ] = None
    staff_license_equivalent_teacher: Annotated[
        int | None,
        Field(description='준교사 수')
    ] = None
    child_per_teacher: Annotated[
        float | None,
        Field(description='교사 1명당 유아 수')
    ] = None
    link_url: Annotated[
        str | None,
        Field(description='유치원알리미 공시 페이지')
    ] = None
