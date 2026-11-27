"""`complexes.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.naver.service.common.constants import (
    ASKING_RANGES_DESCRIPTION,
)

from typing import (
    Annotated,
)


class NaverAreaComplex(BaseModel):
    """지역 단지 목록의 단지 한 곳. 좌표·대표 사진·주민 댓글은 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호 (naver complex / items / real-price 에 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 빌라, 재건축, 분양권, 오피스텔분양권)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심(동·시·군·구면 그 지역 중심)에서의 거리 (km)')
    ] = None
    listing_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수. 서버가 매물 수를 주지 않으면 null (모름)')
    ] = None
    asking_ranges: Annotated[
        dict[str, AmountRange] | None,
        Field(description=ASKING_RANGES_DESCRIPTION)
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class NaverAreaComplexesResult(Result):
    """지역 단지 목록.

    `notes`: 일부만 보여 준다는 안내 등
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 단지 수 (동·시·군·구면 그 경계 안, 반경이면 반경을 감싸는 사각형 안. limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[NaverAreaComplex],
        Field(description='단지 (네이버 정렬 순서)')
    ]
