"""`station.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from typing import (
    Annotated,
)


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
