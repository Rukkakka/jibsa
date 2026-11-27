"""`hot_places.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.dabang.service.common.models import (
    DabangPlace,
)

from typing import (
    Annotated,
)


class DabangHotPlace(BaseModel):
    """핫플레이스 식당 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='식당 이름')
    ] = None
    guide: Annotated[
        str | None,
        Field(description="오른 가이드 ('미쉐린', '블루리본'. 다방 이름표가 없는 값이면 null)")
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (다방이 주지 않으면 null, 웹은 '주소 정보를 확인하고 있어요.')")
    ] = None
    labels: Annotated[
        list[str],
        Field(description="꼬리표 ('한식(일반한식)', '솥밥')")
    ]


class DabangHotPlacesResult(Result):
    """동 안 핫플레이스.

    `notes`: 일부 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    type: Annotated[
        str,
        Field(description="고른 가이드 ('전체', '미쉐린', '블루리본')")
    ]
    basis: Annotated[
        str,
        Field(description='무엇을 모은 목록인지')
    ]
    base_month: Annotated[
        str | None,
        Field(description='다방 기준 달 (YYYY-MM)')
    ] = None
    total: Annotated[
        int | None,
        Field(description='전체 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 있는지')
    ] = False
    places: Annotated[
        list[DabangHotPlace],
        Field(description='다방 목록 순 식당')
    ]
