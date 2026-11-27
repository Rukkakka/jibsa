"""`trending.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
)

from jibsa.core.listing import (
    AmountSet,
    Result,
)
from jibsa.providers.daangn.service.common.models import (
    region_name_parts,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnTrendingComplex(BaseModel):
    """인기 급상승 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[int | None, Field(description='순위. 당근이 빈 항목을 줘 셀 수 없으면 null')]
    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='시·도·구')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    representative_area_m2: Annotated[
        float | None,
        Field(description='대표 평형 전용면적 (㎡). 당근이 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    latest_trades: Annotated[
        dict[str, AmountSet | None],
        Field(description="대표 평형의 가장 최근 실거래. 거래 키('sale')이고 그 안 price_manwon 은 최근 매매가 (만원). 최근 매매가 없거나 매매가가 0 이면(당근 웹도 비운다) 키가 없고({}), 대표 평형을 모르거나(당근이 빈 항목을 줘 셀 수 없을 때 포함) 당근이 실거래 칸이나 그 목록을 주지 않거나 목록에 빈 항목이 섞이거나 매매가를 모르면 'sale' 이 null")
    ]


class DaangnTrendingRegion(BaseModel):
    """인기 급상승 단지를 본 범위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sido: Annotated[
        str,
        Field(description='시/도. 전국이면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    sigungu: Annotated[
        str,
        Field(description='시/군/구. 시·도 범위면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    region_id: Annotated[
        int | None,
        Field(description='당근 지역 ID. 전국이면 null')
    ] = None
    level: Annotated[
        Literal['전국', '시도', '구'],
        Field(description='전국·시도·구(시·군 포함)')
    ]

    @model_serializer
    def with_name(self) -> dict[str, Any]:
        if self.level == '전국':
            return {'name': '전국', 'region_id': self.region_id, 'level': self.level}
        return {**region_name_parts(self.sido, self.sigungu), 'region_id': self.region_id, 'level': self.level}


class DaangnTrendingComplexesResult(Result):
    """인기 급상승 단지 목록.

    `notes`: 빈 결과 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnTrendingRegion, Field(description='본 범위')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    complexes: Annotated[list[DaangnTrendingComplex], Field(description='어제 대비 오늘 조회가 급상승한 순 단지')]
