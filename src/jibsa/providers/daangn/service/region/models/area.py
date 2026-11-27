"""`area.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
)

from jibsa.core.listing import (
    join_address,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnRegion,
    region_name_parts,
)
from jibsa.providers.daangn.service.region.constants import AreaLevel

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnArea(BaseModel):
    """웹 지도 검색창의 지역 검색(`searchRegion`)으로 찾은 법정동·구·시·도."""

    model_config = ConfigDict(
        extra='forbid',
    )

    level: Annotated[
        AreaLevel,
        Field(description='동(읍·면 포함)·구(시·군 포함)·시도')
    ]
    name1: Annotated[
        str,
        Field(description='시/도')
    ]
    name2: Annotated[
        str,
        Field(description="시/군/구 ('수원시 권선구'). 시·도와 세종의 동은 빈 문자열")
    ] = ''
    name3: Annotated[
        str,
        Field(description='읍/면/동. 동이 아니면 빈 문자열')
    ] = ''
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]
    lat: Annotated[
        float,
        Field(description='지역 중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='지역 중심 경도')
    ]
    zoom: Annotated[
        int,
        Field(description='웹 지도가 이 지역을 여는 줌 (동 14, 구 12, 시·도 10)')
    ]
    node_id: Annotated[
        str | None,
        Field(exclude=True, description='지역 검색 결과의 Relay id. 매물 카드 지역의 id 와 같다 (`relay_id`, 시·도 채우기에 쓴다)')
    ] = None

    @property
    def full_name(self) -> str:
        """시·도부터 이어 붙인 이름 ('서울특별시 강남구 역삼동')."""
        return join_address(self.name1, self.name2, self.name3) or self.name1

    def as_region(self) -> DaangnRegion:
        """동 단위 검색이 쓰는 동 (`DaangnRegion`)."""
        return DaangnRegion(sido=self.name1, sigungu=self.name2, dong=self.name3, region_id=self.region_id)


class DaangnRealsaleRegion(BaseModel):
    """지역 실거래를 조회한 동 또는 구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="지역 전체 이름 ('서울특별시 강남구 역삼동'). 안내 문구에 쓴다. 출력의 name 은 가장 작은 단위 이름이다 (`region_name_parts`)")
    ]
    region_id: Annotated[
        int,
        Field(description='당근 지역 ID')
    ]
    level: Annotated[
        Literal['동', '구'],
        Field(description='동(읍·면 포함) 또는 구(시·군 포함, 구가 없는 세종은 세종특별자치시 전체)')
    ]
    name1: Annotated[
        str,
        Field(exclude=True, description='시/도. 후기 페이지 경로에 쓴다')
    ] = ''
    name2: Annotated[
        str,
        Field(exclude=True, description='시/군/구. 후기 페이지 경로에 쓴다')
    ] = ''
    name3: Annotated[
        str,
        Field(exclude=True, description='읍/면/동 (동일 때만)')
    ] = ''

    @model_serializer
    def with_name_parts(self) -> dict[str, Any]:
        # 검색 중심 region 은 네 소스가 같은 칸이다 (`DaangnRegion` 과 같은 name·sido·sigungu·dong, 2026-11-25 사용자 결정)
        return {**region_name_parts(self.name1, self.name2, self.name3), 'region_id': self.region_id, 'level': self.level}
