"""지역·역·단지·재개발 구역 이름과 좌표 해석, 시·도·시·군·구 목록의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)

from typing import (
    Annotated,
)


class NaverRegion(BaseModel):
    """검색 중심점. 직방 지역 검색 결과(`ZigbangRegion`)와 같은 모양이라 출력의 `region` 이 어느 쪽으로 찾든 같다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='지역·역·단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='전체 주소 (역은 null)')
    ] = None
    lat: Annotated[
        float,
        Field(description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(description='중심 경도')
    ]
    legal_division_code: Annotated[
        str | None,
        Field(description='법정동코드 (10자리, 역은 null)')
    ] = None


class NaverRegionEntry(BaseModel):
    """지역 목록의 지역 하나. 지역 후보라 중심 좌표를 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='지역 이름 (예: 강남구, 개포동, 성남시 분당구). 다른 명령의 지역 인자에 넣는다')
    ]
    level: Annotated[
        str | None,
        Field(description='단위 (시·도, 시·군·구, 읍·면·동)')
    ] = None
    legal_division_code: Annotated[
        str,
        Field(description='법정동 코드 (10자리)')
    ]
    lat: Annotated[
        float | None,
        Field(description='중심 위도')
    ] = None
    lng: Annotated[
        float | None,
        Field(description='중심 경도')
    ] = None


class NaverRegionList(Result):
    """지역 하나의 바로 아래 지역 목록 (지역을 주지 않으면 시·도 전체).

    `notes`: 같은 이름이 여러 곳일 때 안내 등. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    parent: Annotated[
        str | None,
        Field(description='상위 지역 (예: 서울시 강남구). 시·도 전체 목록이면 null')
    ] = None
    parent_legal_division_code: Annotated[
        str | None,
        Field(description='상위 지역 법정동 코드 (10자리). 시·도 전체 목록이거나 구가 있는 시면 null')
    ] = None
    regions: Annotated[
        list[NaverRegionEntry],
        Field(description='하위 지역 (네이버 순서, 대개 가나다순)')
    ]
