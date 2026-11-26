"""요청 모델: 인기 단지 (trending-complexes)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
)


class DaangnTrendingComplexesRequestPayloadModel(RequestModel):
    """GraphQL `trendingComplexes` 쿼리 변수 (웹의 `TrendingComplexListPanelListQuery`, 인기 급상승 단지 더 보기 패널).

    웹은 전국(`ALL`)·시·도 탭과 시·군·구 페이지로만 부르고 동으로는 부르지 않는다 (2026-11-12 번들 대조). 지역 ID 는 문자열로
    보내야 한다 (숫자면 "알 수 없는 오류"). 동으로 부르면 수가 때마다 달랐다 (2026-10-27 실측: 0~22곳).
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='받을 단지 수 (웹 패널은 50)')
    ] = 50
    region_id: Annotated[
        str,
        Field(min_length=1, description="'ALL'(전국) 또는 당근 시·도·시·군·구 ID", alias='regionId')
    ]
