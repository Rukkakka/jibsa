"""요청 모델: 동 안 학교·유치원·어린이집 목록 (search schools)."""
from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.models.request.common import (
    REGION_INFO_PAGE_LIMIT,
    DabangSchoolEstablishmentType,
)
from jibsa.providers.dabang.api.models.request.school.common import (
    DabangSchoolLevelPath,
)

from typing import (
    Annotated,
    Literal,
    Self,
)


# 동 안 학교 목록의 단계 (경로). 웹 동네정보 '학군' 상세 목록의 탭 다섯 개다 (school-regional 청크, 2026-11-13)
DabangRegionalSchoolPath = DabangSchoolLevelPath | Literal['kinder-school', 'nursery-school']


class DabangRegionInfoSchoolRegionalV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/school/regional/{level}` 쿼리 (동 안 학교·유치원·어린이집 목록, 웹 동네정보 '학군' 상세 목록).

    웹은 `regionGid`·`schoolEstablishmentType`('전체' 면 보내지 않음)·`limit` 30·`page` 를 보낸다 (school-regional 청크,
    2026-11-13 웹 캡처: 역삼동 초등학교 `regionGid=10063&limit=30&page=1`).

    Args:
        level: 단계 (경로).
        region_gid: 다방 동 번호.
        school_establishment_type: 설립 구분. 없으면 전체.
        limit: 한 쪽 수 (최대 30).
        page: 쪽 번호 (1부터).
    """

    level: Annotated[
        DabangRegionalSchoolPath,
        Field(exclude=True, description='단계 (경로)')
    ]
    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]
    school_establishment_type: Annotated[
        DabangSchoolEstablishmentType | None,
        Field(description='설립 구분', alias='schoolEstablishmentType')
    ] = None
    limit: Annotated[
        int,
        Field(ge=1, le=REGION_INFO_PAGE_LIMIT, description='한 쪽 수')
    ] = REGION_INFO_PAGE_LIMIT
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1

    # 리뷰 오탐 (2026-11-14, 근거 고침 2026-11-20): CLI 라벨 검사·service 표와 겹쳐 보이지만 요청 모델이 막는 층이다. 서버는 그
    # 단계에 없는 설립 구분을 거절하지 않고 무시해 거르지 않은 목록을 준다 (2026-11-20 regionGid 10063 초등학교: 조건 없음 →
    # total 2, PUBLIC → 2, PRIVATE → 0 으로 서버가 거른다, HOME → 2 로 걸러지지 않은 전체). 조용히 틀린 결과가 되므로 요청
    # 모델에서 막는다 (provider-conventions 의 안 되는 것). CLI 로는 닿지 않는다
    @model_validator(mode='after')
    def establishment_matches_level(self) -> Self:
        # 가정·직장·협동은 어린이집 탭에만 있다
        if self.level != 'nursery-school' and self.school_establishment_type not in (None, 'PUBLIC', 'PRIVATE'):
            raise ValueError(f'{self.level} 설립 구분은 PUBLIC·PRIVATE 만 있습니다: {self.school_establishment_type}')
        return self
