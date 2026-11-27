"""네이버 배정 초등학교 목록 (`assigned_schools`)."""

from jibsa.core.listing import note
from jibsa.providers.naver.api.response.common import NaverSchoolModel
from jibsa.providers.naver.service.common.constants import SCHOOL_ALLOCATION_LABELS
from jibsa.providers.naver.service.common.labels import unknown_code_label
from jibsa.providers.naver.service.common.models import NaverAssignedSchool


def assigned_schools(schools: list[NaverSchoolModel], notes: list[str]) -> list[NaverAssignedSchool]:
    """배정 초등학교 목록. 이름이 없는 항목은 빼고 `notes` 에 `[제외]` 안내를 붙인다.

    배정 방식 코드가 `SCHOOL_ALLOCATION_LABELS` 에 없으면 `unknown_code_label` 글자로 낸다 (코드가 없거나 '-' 면 null).
    """
    named = [school for school in schools if school.name]
    if len(named) < len(schools):
        notes.append(note('제외', f'이름이 없는 배정 학교 {len(schools) - len(named)}곳은 넣지 않았습니다'))
    result: list[NaverAssignedSchool] = []
    for school in named:
        # 날짜·층 칸처럼 '-' 는 값 없음 표시다
        allocation = (school.allocation_type or '').strip()
        result.append(NaverAssignedSchool(
            school_code=school.code,
            name=school.name,
            assignment=(
                None if allocation in ('', '-')
                else SCHOOL_ALLOCATION_LABELS.get(allocation) or unknown_code_label('값', allocation)
            ),
            operation_type=school.operation_type,
            walk_minutes=school.walking_minute,
            distance_m=school.distance,
            students_per_class=school.students_per_classroom,
            students_per_teacher=school.students_per_teacher,
        ))
    return result
