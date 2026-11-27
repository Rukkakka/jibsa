"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
    TradeType,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.service.common.models import (
    ZigbangAptListing,
    ZigbangAptRegion,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangAptSearchResult(Result):
    """아파트 지역 매물 검색 결과.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangAptRegion,
        Field(description='검색한 동·구. 좌표(lat·lng)는 이름으로 찾았는데 직방이 주지 않았으면 모름(null)')
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
        Field(description='직방 목록에 아직 받지 않은 매물이 남았는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 (지역 코드 code, 앞서 받은 수 offset). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[ZigbangAptListing],
        Field(description='직방이 보여 주는 순서의 매물')
    ]


class ZigbangAptConditions(RequestModel):
    """아파트 매물 조건 (search listings apt). 금액은 만원, 면적은 ㎡.

    거래 유형·가격·공급면적·신규분양 제외는 서버에서 거른다. 전용면적은 직방이 받지 않아 받은 뒤에 거른다.
    """

    trade_types: Annotated[
        list[TradeType],
        Field(description='거래 유형 (APT_TRADE_TYPES). 비면 전체')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원)')
    ] = None
    area_min_m2: Annotated[
        float | None,
        Field(description='전용면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='전용면적 상한 (㎡)')
    ] = None
    supply_area_min_m2: Annotated[
        float | None,
        Field(description='공급면적 하한 (㎡)')
    ] = None
    supply_area_max_m2: Annotated[
        float | None,
        Field(description='공급면적 상한 (㎡)')
    ] = None
    exclude_new_sale: Annotated[
        bool,
        Field(description="신규분양 매물을 빼고 볼지 (웹의 '신규 분양 포함' 을 끈 목록). 거짓이면 서버 기본(분양 포함)이다")
    ] = False
