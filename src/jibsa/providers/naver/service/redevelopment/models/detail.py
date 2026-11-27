"""`detail.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
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


class NaverRedevelopmentDetail(Result):
    """재개발 구역 하나의 정보와 현재 매물 통계. 조합 연락처와 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    redevelopment_id: Annotated[
        int,
        Field(description='구역 번호. naver search listings --redevelopment 에 넘긴다')
    ]
    name: Annotated[
        str | None,
        Field(description='구역 이름')
    ] = None
    legal_division: Annotated[
        str | None,
        Field(description='대표 법정동 (예: 서울특별시 용산구 한남동)')
    ] = None
    planned_household_count: Annotated[
        int | None,
        Field(description='계획 세대수')
    ] = None
    business_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 이주및철거)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='계획 용적률 (%)')
    ] = None
    building_coverage_ratio_percent: Annotated[
        float | None,
        Field(description='계획 건폐율 (%)')
    ] = None
    listing_counts: Annotated[
        dict[str, int],
        Field(description='거래 유형별 현재 매물 수 (매매·전세·월세·단기임대). 거래 유형을 고르면 그 유형만')
    ]
    asking_ranges: Annotated[
        dict[str, AmountRange],
        Field(description='거래 유형별 호가 범위 {sale: {lowest, highest}, jeonse: …} (만원). sale 은 price_manwon, jeonse 는 deposit_manwon. 그 거래 매물이 없거나 --trade 로 고르지 않은 거래는 키가 없다. 한 끝만 비면 그 끝 금액만 null')
    ]
    url: Annotated[
        str,
        Field(description='구역 페이지 URL')
    ]
