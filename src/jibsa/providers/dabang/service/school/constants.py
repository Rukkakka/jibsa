"""학교 기능(school)의 상수: 교육 단계·학교 단계 경로·학교 코드 패턴·시설 그룹 이름."""
import re

from jibsa.providers.dabang.api.models.request.school.common import (
    DabangSchoolLevelPath,
)
from jibsa.providers.dabang.api.models.request.school.detail import (
    SCHOOL_CODE_PATTERN_TEXT,
)
from jibsa.providers.dabang.api.models.request.school.search import (
    DabangRegionalSchoolPath,
)
from jibsa.providers.dabang.service.common.constants import (
    SCHOOL_LEVELS,
    SchoolLevel,
)

from typing import Literal


# 유치원·어린이집. 학교와 상세 응답이 달라(유치원알리미·어린이집정보공개포털) 따로 둔다
ChildcareLevel = Literal['유치원', '어린이집']
CHILDCARE_LEVELS: tuple[ChildcareLevel, ...] = ('유치원', '어린이집')
# school --level 과 search schools --level 이 받는 단계 (학교 다음 유치원·어린이집)
EducationLevel = Literal['초등학교', '중학교', '고등학교', '유치원', '어린이집']
EDUCATION_LEVELS: tuple[EducationLevel, ...] = (*SCHOOL_LEVELS, *CHILDCARE_LEVELS)

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

# 학교 코드 (학교 'S010000743', 어린이집 '11680000021', 유치원 UUID). 경로에 들어가 영문·숫자·'-' 만 받는다
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(SCHOOL_CODE_PATTERN_TEXT)

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
