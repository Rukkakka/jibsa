"""요청 모델: 아파트 매물 검색 (search listings apt): 지역 목록과 반경(nearby-danjis) 검색."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import (
    ZigbangAptTranType,
    _index_arrays,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangLocalsItemCatalogsRequestParameterModel(RequestModel):
    """`GET /apt/locals/{localCode}/item-catalogs` 경로 + 쿼리. 지역 안의 아파트 매물.

    금액은 모두 **만원** 이다. 면적은 공급면적(㎡)이다 (웹은 평 × 3.3 으로 보낸다).
    `limit` 은 서버가 20 을 넘으면 400 으로 거절한다.
    """

    local_code: Annotated[
        str,
        Field(
            pattern=r'^\d{2}(\d{3}(\d{3})?)?$',
            exclude=True,
            description='지역 코드. 법정동코드 앞 5자리(시·군·구), 8자리(읍·면·동). 2자리(시·도)와 10자리는 에러 없이 늘 0건이다 (2026-10-11 실측)'
        )
    ]
    tran_types: Annotated[
        list[ZigbangAptTranType],
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세). 비우면 전체', alias='tranTypeIn')
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
    supply_area_min_m2: Annotated[
        float | None,
        Field(ge=0, description='공급면적 하한 (㎡)', alias='sizeContractM2Min')
    ] = None
    supply_area_max_m2: Annotated[
        float | None,
        Field(ge=0, description='공급면적 상한 (㎡)', alias='sizeContractM2Max')
    ] = None
    offset: Annotated[
        int,
        Field(ge=0, description='건너뛸 매물 수')
    ] = 0
    limit: Annotated[
        int,
        Field(ge=1, le=20, description='한 번에 받을 매물 수. 20 초과는 서버가 400 으로 거절한다')
    ] = 20

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return _index_arrays(handler(self))


class ZigbangNearbyDanjisRequestParameterModel(RequestModel):
    """`GET /apt/nearby-danjis` 쿼리. 좌표 반경 안의 아파트 단지 (가까운 순)."""

    lat: Annotated[
        float,
        Field(ge=-90, le=90, description='중심 위도')
    ]
    lng: Annotated[
        float,
        Field(ge=-180, le=180, description='중심 경도')
    ]
    radius: Annotated[
        float,
        Field(gt=0, le=5, description='반경 (km). 강남역 1km 에 54곳, 2km 에 204곳')
    ]
    limit: Annotated[
        int,
        Field(ge=1, le=1000, description='최대 단지 수. 빼면 반경 안 전부지만 서버가 요구하는 값이라 넉넉히 보낸다')
    ] = 1000
