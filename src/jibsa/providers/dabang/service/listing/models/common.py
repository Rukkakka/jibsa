"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
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
from jibsa.providers.dabang.api.models.request.common import DabangBboxModel
from jibsa.providers.dabang.service.common.models import (
    DabangPlace,
)

from typing import (
    Annotated,
    Any,
)


class DabangListPosition(BaseModel):
    """매물 검색을 이어 받을 위치 (`--next`). 받은 매물 수가 아니라 다방 쪽 번호와 그 쪽에서 쓴 칸으로 기억한다.

    다방 목록은 번호 쪽 넘김이고 한 쪽이 24건보다 적게 올 때가 있다 (2026-11-13 웹 캡처: 아파트 강남역 1쪽 23건, 대치동 2쪽
    23건). 예전처럼 받은 수로 쪽을 셈하면(`수 // 24 + 1` 쪽의 `수 % 24` 번째) 23건짜리 1쪽 뒤에 2쪽 첫 건까지 받아 24건을
    주고, 다음 호출이 2쪽을 처음부터 다시 받아 같은 매물이 또 나왔다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    page: Annotated[
        int,
        Field(ge=1, description='다음에 물을 다방 쪽 번호')
    ] = 1
    skip: Annotated[
        int,
        Field(ge=0, description='그 쪽에서 앞 결과가 이미 쓴 칸 수 (그다음 칸부터 받는다)')
    ] = 0
    received: Annotated[
        int,
        Field(ge=0, description="앞 결과들까지 받은 칸 수 (다방이 빈 항목으로 줘서 뺀 칸 포함). '[일부] N번째부터' 안내에만 쓴다")
    ] = 0
    bbox: Annotated[
        DabangBboxModel | None,
        Field(description='아파트 동 검색의 동 경계 사각형. 남기면 이어 받을 때 경계를 다시 받지 않는다')
    ] = None


class DabangSearchResult(Result):
    """매물 검색 결과.

    `notes`: 범위·제외·일부 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치')
    ]
    scope: Annotated[
        str,
        Field(description="찾은 범위 ('역삼동 안', '강남역 다방 역 반경 750m', '반경 1km')")
    ]
    radius_km: Annotated[
        float | None,
        Field(description='반경 (km). 역·좌표·--radius 검색만')
    ] = None
    total: Annotated[
        int | None,
        Field(description='다방이 센 범위 안 매물 수 (limit·jibsa 제외 전). 반경·아파트 동 검색은 반경·동을 덮는 사각형 안의 수다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='같은 조건으로 더 받을 매물이 있는지. 있으면 CLI 가 이어 받기 표(next)를 붙인다')
    ] = False
    next_position: Annotated[
        DabangListPosition | None,
        Field(exclude=True, description='이어 받을 위치 (다음 쪽 번호·그 쪽에서 쓴 칸·받은 수). 더 없으면 None')
    ] = None
    listings: Annotated[
        list[SerializeAsAny[Listing]],
        Field(description='다방 목록 순 매물')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_radius(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.radius_km is None:
            data.pop('radius_km', None)
        return data
