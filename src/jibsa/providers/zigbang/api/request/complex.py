"""요청 모델: 아파트 단지·오피스텔 건물 정보와 단지 매물 목록, 역 주변 단지 (complex, search listings --complex, search complexes)."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import (
    ZigbangItemsFiltersRequestParameterModel,
    ZigbangOfficetelOrderMixin,
    _index_arrays,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


# 아파트 단지 목록의 단지 종류. 웹은 늘 셋을 모두 보낸다 (2026-11-15 번들 `getAPTTypedListIds`: apt·offer(분양)·preOffer(분양 예정))
ZigbangDanjiServiceType = Literal['apt', 'offer', 'preOffer']


class ZigbangItemsOfficetelsBuildingV1RequestParameterModel(ZigbangItemsFiltersRequestParameterModel, ZigbangOfficetelOrderMixin):
    """`GET /house/property/v1/items/officetels/{buildingId}` 경로 + 쿼리.

    건물 안의 매물. 가격·관리비는 만원이고 상세 조건은 지도 목록과 같다.
    """

    building_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='오피스텔 건물 ID (검색 결과의 id). 경로에 들어가며 쿼리로는 보내지 않는다')
    ]


class ZigbangDanjisSchoolsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/schools` 경로. 아파트 단지의 학군."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]


class ZigbangSubwaysRequestParameterModel(RequestModel):
    """`GET /apt/subways/{subwayId}` 경로. 역 정보와 역 주변 아파트 단지 (거리순)."""

    subway_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='직방 역 ID (지역 검색 결과의 역 id 와 같다). 경로에 들어간다')
    ]


class ZigbangDanjisIdsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/ids` 쿼리. 역 주변 아파트 단지 ID 를 웹 목록 순서로.

    웹 아파트 지도의 '<역> 주변단지' 패널이 `type=subway&id=…&order=viewCount&limit=5` 와 단지 종류 셋으로 부른다
    (2026-11-15 캡처·번들 `getAPTTypedListIds`). 더보기 화면은 `limit` 없이 모든 ID 를 받아 15곳씩 카드 내용을 받는다.
    쪽 넘김(offset)은 없다.
    """

    search_type: Annotated[
        Literal['subway'],
        Field(description='무엇의 주변 단지인지. 역만 쓴다 (웹은 school·local 도 보낸다)', alias='type')
    ] = 'subway'
    subway_id: Annotated[
        int,
        Field(gt=0, description='직방 역 ID', alias='id')
    ]
    order: Annotated[
        Literal['viewCount'],
        Field(description='순서. 웹 패널 기본 탭(주변단지)의 조회수 순만 쓴다')
    ] = 'viewCount'
    limit: Annotated[
        int | None,
        Field(ge=1, description='받을 단지 수. 없으면 모두')
    ] = None
    service_types: Annotated[
        list[ZigbangDanjiServiceType],
        Field(description='단지 종류. 웹처럼 셋을 모두 보낸다', alias='serviceType')
    ] = ['apt', 'offer', 'preOffer']

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return _index_arrays(handler(self))
