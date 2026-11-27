"""`listings.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializeAsAny,
)

from jibsa.core.listing import (
    Listing,
    Result,
)

from typing import (
    Annotated,
)


class ZigbangComplexListingsResult(Result):
    """단지 하나의 매물 목록.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 단지 ID')
    ]
    total: Annotated[
        int,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지 목록에 아직 받지 않은 매물이 남았는지 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        # 아파트는 ZigbangAptListing 이라 서브클래스 필드(complex_id 등)까지 내보낸다
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물')
    ]
