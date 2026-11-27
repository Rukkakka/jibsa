"""직방 service 원룸·빌라·오피스텔의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Listing,
    Result,
)
from jibsa.providers.zigbang.service.common.models import (
    ZigbangListing,
    ZigbangRegion,
    drop_unused_scope,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangSearchResult(Result):
    """매물 검색 결과.

    `notes`: 매물이 limit 보다 많아 일부만 보여 준다는 안내
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
        Field(description='검색 반경 (km). 동 경계로 찾았으면 키가 없다')
    ] = None
    boundary: Annotated[
        str | None,
        Field(description='반경 대신 경계 안을 찾은 동 이름. 반경으로 찾았으면 키가 없다')
    ] = None
    total: Annotated[
        int,
        Field(description=(
            '범위(반경·동 경계, 역은 서버가 준 역 반경) 안 서로 다른 매물 수 근사값 (limit 적용 전, 거래 불가를 빼기 전). '
            '종류 여럿에 함께 있는 매물은 한 번만 센다'
        ))
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='범위 안에 아직 받지 않은 매물이 남은 종류가 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        dict[str, Any] | None,
        Field(exclude=True, description='이어 받을 위치 ({"offsets": {종류: 그 종류 직방 목록에서 다음에 받을 자리}}). 더 없으면 None')
    ] = None
    listings: Annotated[
        # 오피스텔의 complex_id 까지 내보낸다 (SerializeAsAny 가 없으면 공통 Listing 필드만 나간다)
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물. 종류 여럿이면 요청한 종류 순서로 종류별 묶음을 잇는다')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_scope(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 반경과 동 경계 중 쓰지 않은 쪽은 해당 없다
        return drop_unused_scope(handler(self))


class ZigbangDetailedListing(ZigbangListing):
    """`--details` 로 매물 상세를 1회 더 받아 건물 용도를 붙인 원룸·오피스텔·빌라 매물."""

    residence_type: Annotated[
        str | None,
        Field(description='건축물 용도 (예: 다가구, 다세대, 근린생활시설). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다. 모르면 null')
    ] = None
