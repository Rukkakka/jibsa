"""지역·역·대학·주소 해석과 실거래 지역의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
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


class DaangnStation(BaseModel):
    """당근 역 검색으로 찾은 지하철역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description="역 이름 ('역' 까지, 예: 역삼역)")
    ]
    lines: Annotated[
        list[str],
        Field(description='노선 (예: 서울2호선)')
    ]
    lat: Annotated[
        float,
        Field(description='역 위도')
    ]
    lng: Annotated[
        float,
        Field(description='역 경도')
    ]
    station_id: Annotated[
        str,
        Field(exclude=True, description='당근 역 ID (역 주변 매물 조회에 쓴다)')
    ]
    others: Annotated[
        list[str],
        Field(
            exclude=True,
            description="이름이 같아 고르지 않은 다른 역 ('서울5호선 양평역'). 위치 정보가 없는 역은 이름 뒤에 `NO_LOCATION` 이 붙는다. 안내에 쓴다",
        )
    ] = []


class DaangnUniversity(BaseModel):
    """웹 지도 검색창의 대학 검색(`searchSchoolPois`)으로 찾은 대학 캠퍼스 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='캠퍼스까지 붙인 대학 이름 (예: 연세대학교 신촌캠퍼스). 당근이 캠퍼스 이름을 주지 않으면 대학 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    lat: Annotated[
        float,
        Field(description='대학 위도')
    ]
    lng: Annotated[
        float,
        Field(description='대학 경도')
    ]
    university_id: Annotated[
        str,
        Field(exclude=True, description='당근 대학 ID (대학 주변 매물 조회에 쓴다)')
    ]
    cut: Annotated[
        bool,
        Field(exclude=True, description='대학 검색이 후보 상한에서 잘려 이름이 같은 캠퍼스가 더 있을 수 있다 (안내에 쓴다)')
    ] = False


class DaangnAddress(BaseModel):
    """웹 검색창 주소 모드(`searchAddress`)로 찾은 도로명 주소와 `unitByAddress` 로 받은 그 좌표."""

    model_config = ConfigDict(
        extra='forbid',
    )

    road_address: Annotated[
        str,
        Field(description="도로명 주소 (예: '서울특별시 강남구 테헤란로 152 (역삼동)')")
    ]
    address: Annotated[
        str | None,
        Field(description="지번 주소 (건물 이름까지, 예: '서울특별시 강남구 역삼동 737 강남파이낸스센터')")
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='그 주소의 당근 단지·건물 이름. 당근이 모르면 null')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='그 주소가 당근 단지면 단지 ID (search listings --complex·complex 에 넘긴다). 단지가 아니면 키가 없다')
    ] = None
    lat: Annotated[
        float,
        Field(description='주소 위도')
    ]
    lng: Annotated[
        float,
        Field(description='주소 경도')
    ]

    @property
    def label(self) -> str:
        """안내에 쓰는 주소 이름 (`'서울특별시 강남구 테헤란로 152 (역삼동)' (강남파이낸스센터)`). 당근이 모르는 건물이면 이름을 붙이지 않는다."""
        return f"'{self.road_address}'" + (f' ({self.building_name})' if self.building_name else '')

    @model_serializer(mode='wrap')
    def drop_missing_complex(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_id is None:
            data.pop('complex_id', None)
        return data


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
