"""요청 모델: 아파트 매물 검색 (search listings apt): 지역 목록과 좌표가 속한 동 찾기."""


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
    Literal,
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


class ZigbangLocalsPolygonRequestParameterModel(RequestModel):
    """`GET /apt/locals/polygon` 쿼리. geohash 칸 중심이 속한 동.

    웹 아파트 지도는 지도 가운데 geohash 로 이 API 를 불러 '○○동 주변 매물보기' 의 동을 정한다 (2026-11-15 캡처). 웹은
    geohash 를 암호화해 보내지만 평문도 받는다.
    """

    geohash: Annotated[
        str,
        Field(
            pattern=r'^[0-9bcdefghjkmnpqrstuvwxyz]{5,12}$',
            description=(
                '찾을 위치. 칸이 크면 옆 동이 잡혀 정밀도 10 으로 보낸다 (2026-11-15 실측: 강남역은 정밀도 5 에 논현동, '
                '6 에 역삼동, 7·8 에 서초동, 9·10·12 에 역 주소와 같은 역삼동)'
            )
        )
    ]
    level: Annotated[
        Literal['local3'],
        Field(description='행정 단계. 웹 지도의 주변 매물보기는 local3(읍·면·동)만 보낸다')
    ] = 'local3'
    polygon: Annotated[
        bool,
        Field(description='경계 좌표(geojson)를 받을지. False 면 geojson 이 null 이다')
    ] = False
