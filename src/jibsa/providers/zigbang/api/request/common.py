"""여러 기능이 같이 쓰는 요청 모델·필터 값과 기반 모델."""


from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Any,
    Literal,
    Self,
)


# '단기' 는 단기임대. 직방이 거래 유형 필터로 받는 값이고, 요약 응답에서는 월세에 contract '단기' 로 온다.
ZigbangSalesType = Literal['전세', '월세', '매매', '단기']
# 방 구조 필터 값. 요약 응답의 방 구조 코드(05, 06)를 웹은 '쓰리룸'·'포룸이상' 으로 보여 주지만
# 필터로는 '쓰리룸플러스'·'포룸플러스' 를 받고, '쓰리룸' 을 보내면 400 이다.
ZigbangRoomTypeFilter = Literal['오픈형원룸', '분리형원룸', '복층형원룸', '투룸', '쓰리룸플러스', '포룸플러스']
ZigbangFloorFilter = Literal['지상', '반지하', '옥탑방', '1층']
ZigbangOptionFilter = Literal[
    '에어컨', '냉장고', '세탁기', '가스레인지', '인덕션', '전자레인지',
    '책상', '책장', '침대', '옷장', '신발장', '싱크대',
]
# 아파트 거래 유형. 원룸·빌라와 달리 영어 코드를 받고 한글을 보내면 400 이다.
ZigbangAptTranType = Literal['trade', 'charter', 'rental']

# 직방은 배열 쿼리를 `salesTypes[0]=전세&salesTypes[1]=월세` 처럼 인덱스를 붙여 받는다.
INDEXED_ARRAY_KEYS: tuple[str, ...] = ('salesTypes', 'roomType', 'floor', 'options', 'tranTypeIn', 'danjiRoomTypeIds')


def _index_arrays(data: dict[str, Any]) -> dict[str, Any]:
    """배열 값을 `key[0]=a&key[1]=b` 모양의 쿼리 키로 펼친다. 빈 배열은 키째 뺀다."""
    for key in INDEXED_ARRAY_KEYS:
        values = data.pop(key, None) or []
        for index, value in enumerate(values):
            data[f'{key}[{index}]'] = value
    return data


class ZigbangItemsFiltersRequestParameterModel(RequestModel):
    """원룸·오피스텔·빌라 목록(지도 칸·역 반경·오피스텔 건물)이 공유하는 조건.

    금액 필터는 모두 **만원** 단위다. 배열 필터(`sales_types`, `room_types`, `floors`,
    `options`)는 직방이 요구하는 `salesTypes[0]=전세&salesTypes[1]=월세` 인덱스 표기로
    직렬화된다. 배열 안의 값은 OR (반지하 또는 옥탑방), 옵션만 AND (에어컨과 세탁기 모두) 다.
    참/거짓 조건은 True 일 때만 보낸다 (False 를 보내도 서버가 거르지 않는다).
    """

    sales_types: Annotated[
        list[ZigbangSalesType],
        Field(description="거래 유형 필터. 비우면 단기임대를 포함한 전체. '월세' 는 단기임대를 빼고, '단기' 는 단기임대만", alias='salesTypes')
    ] = []
    deposit_min: Annotated[
        int | None,
        Field(ge=0, description='보증금 하한 (만원)', alias='depositMin')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(ge=0, description='보증금 상한 (만원)', alias='depositMax')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(ge=0, description='월세 하한 (만원)', alias='rentMin')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(ge=0, description='월세 상한 (만원)', alias='rentMax')
    ] = None
    sales_price_min: Annotated[
        int | None,
        Field(ge=0, description='매매가 하한 (만원)', alias='salesPriceMin')
    ] = None
    sales_price_max: Annotated[
        int | None,
        Field(ge=0, description='매매가 상한 (만원)', alias='salesPriceMax')
    ] = None
    manage_cost_min: Annotated[
        int | None,
        Field(ge=0, description='관리비 하한 (만원)', alias='manageCostMin')
    ] = None
    manage_cost_max: Annotated[
        int | None,
        Field(ge=0, description='관리비 상한 (만원)', alias='manageCostMax')
    ] = None
    no_manage_cost: Annotated[
        bool | None,
        Field(description='관리비 없는 매물만. 관리비 범위 조건과 함께 보내지 않는다 (웹도 둘 중 하나만 보낸다)', alias='isNoneManageCost')
    ] = None
    room_types: Annotated[
        list[ZigbangRoomTypeFilter],
        Field(description='방 구조 (OR)', alias='roomType')
    ] = []
    size_min_m2: Annotated[
        float | None,
        Field(ge=0, description='면적 하한 (㎡)', alias='sizeMinM2')
    ] = None
    size_max_m2: Annotated[
        float | None,
        Field(ge=0, description='면적 상한 (㎡)', alias='sizeMaxM2')
    ] = None
    size_min_pyeong: Annotated[
        float | None,
        Field(ge=0, description='면적 하한 (평). 직방이 ㎡ 조건과 같은 기준으로 거르고, 함께 주면 둘 다 만족해야 한다', alias='sizeMin')
    ] = None
    size_max_pyeong: Annotated[
        float | None,
        Field(ge=0, description='면적 상한 (평)', alias='sizeMax')
    ] = None
    floors: Annotated[
        list[ZigbangFloorFilter],
        Field(description='층 (OR). 지상은 반지하·옥탑방을 뺀 층', alias='floor')
    ] = []
    bathroom_count: Annotated[
        int | None,
        Field(ge=1, le=3, description='욕실 수. 1·2 는 정확히 그 수, 3 은 3개 이상', alias='bathroomCount')
    ] = None
    options: Annotated[
        list[ZigbangOptionFilter],
        Field(description='옵션 (AND. 모두 갖춘 매물만)')
    ] = []
    immediate_move: Annotated[
        bool | None,
        Field(description='즉시 입주 가능', alias='isImmediateMove')
    ] = None
    south_facing: Annotated[
        bool | None,
        Field(description='남향', alias='isSouth')
    ] = None
    elevator: Annotated[
        bool | None,
        Field(description='엘리베이터', alias='isElevator')
    ] = None
    parking: Annotated[
        bool | None,
        Field(description='주차 가능')
    ] = None
    cctv: Annotated[
        bool | None,
        Field(description='CCTV')
    ] = None
    pet: Annotated[
        bool | None,
        Field(description='반려동물 가능')
    ] = None
    loan_lease: Annotated[
        bool | None,
        Field(description='전세자금대출 가능', alias='loanLease')
    ] = None
    ev_station: Annotated[
        bool | None,
        Field(description='전기차 충전시설', alias='evStation')
    ] = None

    @model_validator(mode='after')
    def manage_cost_conditions_exclusive(self) -> Self:
        if self.no_manage_cost and (self.manage_cost_min is not None or self.manage_cost_max is not None):
            raise ValueError('관리비 없음과 관리비 범위 조건은 함께 쓸 수 없습니다')
        return self

    @model_serializer(mode='wrap')
    def serialize_arrays(
        self,
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 참/거짓 조건은 켤 때만 보낸다. False 는 '조건 없음' 과 같다.
        data = {key: value for key, value in data.items() if value is not False}
        return _index_arrays(data)


class ZigbangOfficetelOrderMixin(RequestModel):
    """오피스텔 목록(지도 칸·역 반경)과 오피스텔 건물만 받는 정렬 조건."""

    without_random: Annotated[
        bool | None,
        Field(description='서버의 무작위 섞기를 생략한다. 일정한 순서를 보장하지 않는다', alias='withoutRandom')
    ] = None


class ZigbangItemsListV1RequestPayloadModel(RequestModel):
    """`POST /house/property/v1/items/list` 본문. 한 번에 최대 15건."""

    item_ids: Annotated[
        list[int],
        Field(
            min_length=1,
            max_length=15,
            description='요약을 받을 매물 ID 목록. 서버가 15개 초과를 400 으로 거절한다',
            alias='itemIds'
        )
    ]


class ZigbangDanjisRequestParameterModel(RequestModel):
    """`GET /apt/danjis/{danjiId}` 경로. 아파트 단지 정보."""

    danji_id: Annotated[
        int,
        Field(gt=0, exclude=True, description='단지 ID. 경로에 들어가며 쿼리로는 보내지 않는다')
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
        return _index_arrays(handler(self))
