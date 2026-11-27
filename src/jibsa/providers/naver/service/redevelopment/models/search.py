"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)

from typing import (
    Annotated,
)


class NaverRedevelopmentArea(BaseModel):
    """재개발 구역 한 곳. 좌표는 담지 않는다 (위치는 원 사이트로)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    redevelopment_id: Annotated[
        int,
        Field(description='구역 번호. naver search listings --redevelopment 에 넘긴다')
    ]
    name: Annotated[
        str | None,
        Field(description='구역 이름 (예: 한남4재정비촉진구역)')
    ] = None
    legal_division: Annotated[
        str | None,
        Field(description='구역 대표 위치의 법정동 (예: 서울특별시 용산구 보광동). 동 경계로 찾으면 그 동, 시·군·구 경계로 찾으면 그 시·군·구 (목록이 구역의 동을 주지 않는다)')
    ] = None
    planned_household_count: Annotated[
        int | None,
        Field(description='계획 세대수')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 조합설립인가, 사업시행인가)')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='검색 중심에서 구역 대표 위치까지 거리 (km). 동·시·군·구 경계로 찾으면 좌표를 받지 않아 null')
    ] = None
    listing_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수 (매매·전세·월세·단기임대). 서버가 매물 수를 주지 않으면 null (모름)')
    ]
    asking_ranges: Annotated[
        dict[str, AmountRange] | None,
        Field(description='거래 유형별 호가 범위 {sale: {lowest, highest}} (구역 목록은 매매만, 만원). 매매 매물이 없으면 sale 키가 없어 {}. 네이버가 호가 정보를 주지 않으면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='구역 페이지 URL')
    ]


class NaverRedevelopmentAreasResult(Result):
    """지역 재개발 구역 목록.

    `notes`: 일부만 보여 준다는 안내 등
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int,
        Field(description='서버 집계 구역 수 (동·시·군·구면 그 경계 안, 반경이면 반경을 감싸는 지도 범위 안. limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 구역 수')
    ]
    areas: Annotated[
        list[NaverRedevelopmentArea],
        Field(description='구역 (네이버 정렬 순서)')
    ]
