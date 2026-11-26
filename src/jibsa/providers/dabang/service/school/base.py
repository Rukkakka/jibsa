"""학교 기능(school)의 상세·목록이 같이 쓰는 것: 학교 단계 경로."""


from jibsa.providers.dabang.api.request.school.base import (
    DabangSchoolLevelPath,
)
from jibsa.providers.dabang.service.common.functions import (
    SchoolLevel,
)


LEVEL_PATH_BY_LABEL: dict[SchoolLevel, DabangSchoolLevelPath] = {
    '초등학교': 'elementary-school',
    '중학교': 'middle-school',
    '고등학교': 'high-school',
}
