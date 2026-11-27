"""요청 모델: 아파트 단지 기능(complex)의 정보·단지 매물·시세 추이가 같이 쓰는 것."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import (
    ZigbangAptTranType,
    ZigbangItemsFiltersRequestParameterModel,
    ZigbangOfficetelOrderMixin,
    index_arrays,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangDanjisRoomTypesRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/room_types` 경로. 아파트 단지의 평형(공급·전용면적·방·관리비·시세). 경로가 하이픈이 아니라 밑줄이다."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어간다')
    ]


class ZigbangItemsOfficetelsBuildingV1RequestParameterModel(ZigbangItemsFiltersRequestParameterModel, ZigbangOfficetelOrderMixin):
    """`GET /house/property/v1/items/officetels/{buildingId}` 경로 + 쿼리.

    건물 안의 매물. 가격·관리비는 만원이고 상세 조건은 지도 목록과 같다.
    """

    building_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='오피스텔 건물 ID (검색 결과의 id). 경로에 들어가며 쿼리로는 보내지 않는다')
    ]


class ZigbangDanjisItemCatalogsRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}/item-catalogs` 경로 + 쿼리. 단지 하나의 아파트 매물.

    금액은 모두 **만원** 이다. 배열 조건은 `tranTypeIn[0]=charter` 인덱스 표기로 보낸다
    (`danjiRoomTypeIds=1` 처럼 인덱스 없이 보내면 서버가 조건을 무시한다).
    """

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어가며 쿼리로는 보내지 않는다')
    ]
    tran_types: Annotated[
        list[ZigbangAptTranType],
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세). 비우면 전체', alias='tranTypeIn')
    ] = []
    room_type_ids: Annotated[
        list[int],
        Field(description='평형 ID (OR). 비우면 전체', alias='danjiRoomTypeIds')
    ] = []
    sales_price_min: Annotated[
        int | None,
        Field(ge=0, description='매매가 하한 (만원)', alias='minSalesDeposit')
    ] = None
    sales_price_max: Annotated[
        int | None,
        Field(ge=0, description='매매가 상한 (만원)', alias='maxSalesDeposit')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 하한 (만원)', alias='minRentDeposit')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(ge=0, description='보증금·전세금 상한 (만원)', alias='maxRentDeposit')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(ge=0, description='월세 하한 (만원)', alias='minRent')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(ge=0, description='월세 상한 (만원)', alias='maxRent')
    ] = None
    offset: Annotated[
        int,
        Field(ge=0, description='건너뛸 매물 수')
    ] = 0
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 매물 수')
    ] = 50

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return index_arrays(handler(self))
