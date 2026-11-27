"""`nearby.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.dabang.service.common.models import DabangAreaPrice

from typing import (
    Annotated,
)


class DabangNearbyComplex(BaseModel):
    """반경 1km 주변 단지 하나 (평당가 비교)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (complex·real-price 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (동까지, '서울특별시 강남구 대치동')")
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description="그 평형대 평당가 (만원). nearby 의 'sale' 아래는 매매, 'jeonse' 아래는 전세. 다방 웹이 빈 칸으로 두는 값은 null")
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description="입주 N년차 (사용승인한 해를 1년차로 센다. 다방 '입주 37년차')")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='이 단지에서 거리 (m, 다방 값. 웹 목록은 거리를 그리지 않는다)')
    ] = None


class DabangNearbyComplexes(Result):
    """단지 평형대 평당가와 반경 1km 주변 단지 비교 (다방 웹 단지 화면 평당가 칸의 기본 탭 'N평대 비교').

    `notes`: 평형 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='고른 평형 ID (그 평형이 든 평형대로 비교한다)')
    ]
    # 리뷰 오탐 (2026-11-14): 'N평대 비교' 탭을 주지 않는 것은 다방이 값을 주지 않은 모름이라 키를 빼지 않고 null 로 둔다
    # (해당 없음 아님). 웹도 이때 이 탭을 그리지 않는다 (소스 가이드 평형대 평당가 비교)
    pyeong_range: Annotated[
        str | None,
        Field(description="비교한 평형대 (다방 탭 이름 '30평대 비교' 의 '30평대'). 다방이 이 평형에 평형대 탭을 주지 않으면 null")
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice] | None,
        Field(description=(
            "그 평형대의 평당 평균가 (이 단지·동·구, 만원). 다방 웹이 '정보 없음' 으로 쓰는 값(없거나 0)은 그 거래가 null. "
            "다방이 이 평형에 평형대 탭을 주지 않거나 이 목록을 null 로 주면 목록 전체가 null"
        ))
    ] = None
    nearby: Annotated[
        dict[str, list[DabangNearbyComplex] | None],
        Field(description=(
            "반경 1km 주변 단지의 거래별 평당가. 키는 'sale'·'jeonse' 늘 두 개. 'sale'은 다방 순서 그대로(평당가가 있는 단지를 가까운 "
            "순으로 앞에), 'jeonse'는 다방 웹 전월세 탭 순서 그대로. 다방이 평형대 탭이나 주변 단지(nearComplexes)나 그 거래 쪽을 "
            'null 로 주면 그 값이 null, 주었는데 그 쪽이 비었으면 []'
        ))
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
