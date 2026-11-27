"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
