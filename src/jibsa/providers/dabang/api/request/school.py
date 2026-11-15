from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    REGION_INFO_PAGE_LIMIT,
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
    Self,
)


DabangSchoolLevelPath = Literal['elementary-school', 'middle-school', 'high-school']
# 동 안 학교 목록의 단계 (경로). 웹 동네정보 '학군' 상세 목록의 탭 다섯 개다 (school-regional 청크, 2026-11-13)
DabangRegionalSchoolPath = DabangSchoolLevelPath | Literal['kinder-school', 'nursery-school']
# 설립 구분. 학교·유치원은 PUBLIC 국공립·PRIVATE 사립, 어린이집은 PUBLIC 공공·PRIVATE 민간·HOME 가정·WORKPLACE 직장·
# COOPERATIVE 협동이다 (school-regional 청크의 탭, 2026-11-13). 웹은 '전체' 면 값을 보내지 않는다
DabangSchoolEstablishmentType = Literal['PUBLIC', 'PRIVATE', 'HOME', 'WORKPLACE', 'COOPERATIVE']
# 학교 코드. 학교는 학교알리미 'S010000743', 어린이집은 숫자 '11680000021', 유치원은 UUID '1ecec08c-fea6-b044-e053-0a32095ab044'
# 라 '-' 도 받는다 (2026-11-13 단지 상세·웹 캡처). 경로에 들어간다
SCHOOL_CODE_PATTERN_TEXT: str = r'^[A-Za-z0-9-]+$'


class DabangEducationV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/education/{level}/{school_code}` 쿼리 (학교 상세, 학교알리미 공시).

    경로의 단계와 학교 코드가 맞지 않거나 없는 코드면 다방이 500 "일시적으로 서비스가 지연되고 있습니다." 를 준다
    (2026-10-25 실측: 초등학교 코드로 중학교 주소, 없는 코드 'S999999999' 모두 500). 그래서 코드만으로 단계를 찾지 않는다.

    Args:
        level: 학교 단계 (경로).
        school_code: 학교 코드 (경로, 학교알리미 'S010000743').
    """

    level: Annotated[
        DabangSchoolLevelPath,
        Field(exclude=True, description='학교 단계 (경로)')
    ]
    school_code: Annotated[
        str,
        Field(exclude=True, pattern=SCHOOL_CODE_PATTERN_TEXT, description='학교 코드 (경로)')
    ]


class DabangEducationNurserySchoolV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/education/nursery-school/{school_code}` 쿼리 (어린이집 상세, 어린이집정보공개포털 공시).

    없는 코드도 학교 상세처럼 500 "일시적으로 서비스가 지연되고 있습니다." 다 (2026-11-14 실측: '99999999999').

    Args:
        school_code: 어린이집 코드 (경로, '11680000021').
    """

    school_code: Annotated[
        str,
        Field(exclude=True, pattern=SCHOOL_CODE_PATTERN_TEXT, description='어린이집 코드 (경로)')
    ]


class DabangEducationKinderSchoolV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/education/kinder-school/{school_code}` 쿼리 (유치원 상세, 유치원알리미 공시).

    없는 코드도 학교 상세처럼 500 이다 (2026-11-14 실측).

    Args:
        school_code: 유치원 코드 (경로, UUID '1ecec08c-fea6-b044-e053-0a32095ab044').
    """

    school_code: Annotated[
        str,
        Field(exclude=True, pattern=SCHOOL_CODE_PATTERN_TEXT, description='유치원 코드 (경로)')
    ]


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

    # 리뷰 오탐 (2026-11-14): CLI 라벨 검사·service 표와 겹쳐 보이지만, 요청 모델은 서버가 거절할 와이어 값을 막는 층이다
    # (provider-conventions '서버가 거절할 조합은 요청 모델에서 막는다'). CLI 로는 닿지 않는다
    @model_validator(mode='after')
    def establishment_matches_level(self) -> Self:
        # 가정·직장·협동은 어린이집 탭에만 있다
        if self.level != 'nursery-school' and self.school_establishment_type not in (None, 'PUBLIC', 'PRIVATE'):
            raise ValueError(f'{self.level} 설립 구분은 PUBLIC·PRIVATE 만 있습니다: {self.school_establishment_type}')
        return self
