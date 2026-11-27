"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.service.common.models import (
    ZigbangRegion,
    drop_unused_scope,
)
from jibsa.providers.zigbang.service.stay.models.common import ZigbangStayListing

from typing import (
    Annotated,
    Any,
)


class ZigbangStaySearchResult(Result):
    """직방 단기임대 검색 결과.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        ZigbangRegion,
        Field(description='검색 중심점')
    ]
    radius_km: Annotated[
        float | None,
        Field(description=(
            '검색 반경 (km). 역 이름 검색은 직방이 역에서 약 1km 안을 주어 1. 동·구 등 지역 이름·동 경계·학교 이름으로 찾았으면 '
            '키가 없다'
        ))
    ] = None
    boundary: Annotated[
        str | None,
        Field(description=(
            '반경 대신 찾은 지역 이름. 동·구 이름이면 직방 단기임대 지역 검색 결과라 이웃 동 매물이 섞일 수 있고, 동 경계로 '
            '찾았으면 그 경계 안만이다. 반경으로 찾았으면 키가 없다'
        ))
    ] = None
    total: Annotated[
        int,
        Field(description='범위 안 조건에 맞는 매물 수 (limit 적용 전). 이름 검색이면 직방 검색 결과 수, 지도로 찾았으면 반경·동 경계 안 핀 수')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위 안에 요약을 받지 않은 매물이 더 있는지 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        list[ZigbangStayListing],
        Field(description='선택한 정렬 순서의 매물 (직방이 준 순서 또는 웹 지도 목록과 같은 순서)')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unused_scope(handler(self))


class ZigbangStayConditions(RequestModel):
    """단기임대 매물 조건 (search listings stay). 주당 요금은 만원, 면적은 ㎡. 라벨은 `search_stay_listings` 가 서버 코드로 바꾼다."""

    weekly_price_min: Annotated[
        int | None,
        Field(description='주당 요금 하한 (만원)')
    ] = None
    weekly_price_max: Annotated[
        int | None,
        Field(description='주당 요금 상한 (만원)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    building_types: Annotated[
        list[str],
        Field(description='건물 유형 (STAY_BUILDING_TYPE_BY_LABEL)')
    ] = []
    area_min_m2: Annotated[
        float | None,
        Field(description='면적 하한 (㎡)')
    ] = None
    area_max_m2: Annotated[
        float | None,
        Field(description='면적 상한 (㎡)')
    ] = None
    discounts: Annotated[
        list[str],
        Field(description='할인 (STAY_DISCOUNT_TYPE_BY_LABEL)')
    ] = []
    pet_allowed: Annotated[
        bool,
        Field(description='반려동물 가능만')
    ] = False
    duplex: Annotated[
        bool | None,
        Field(description='복층이면 True, 아니면 False, 상관없으면 None')
    ] = None
    options: Annotated[
        list[str],
        Field(description='옵션 (STAY_OPTION_BY_LABEL)')
    ] = []
    parking: Annotated[
        bool,
        Field(description='주차 가능만')
    ] = False
    elevator: Annotated[
        bool,
        Field(description='엘리베이터 있는 매물만')
    ] = False
    floors: Annotated[
        list[str],
        Field(description='층 (STAY_FLOOR_TYPE_BY_LABEL)')
    ] = []
    check_in: Annotated[
        str | None,
        Field(description='입주일 (YYYY-MM-DD)')
    ] = None
    check_out: Annotated[
        str | None,
        Field(description='퇴거일 (YYYY-MM-DD)')
    ] = None
    flexibility: Annotated[
        int | None,
        Field(description='입주일 앞뒤로 허용하는 날 수')
    ] = None
