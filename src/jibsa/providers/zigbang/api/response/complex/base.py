"""응답 모델: 아파트 단지 기능(complex)의 상세·시세 추이가 같이 쓰는 것."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import (
    ZigbangBaseResponseModel,
    ZigbangRoomTypeTitleModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/room_types
# ---------------------------------------------------------------------------

class ZigbangDanjiRoomTypeAreaModel(ZigbangBaseResponseModel):
    """평형의 면적 (㎡·평 모두 숫자). 매물 요약의 면적(`ZigbangAreaModel`)은 평이 문자열이라 따로 둔다."""

    m2: Annotated[
        float | None,
        Field(description='면적 (㎡)')
    ] = None
    p: Annotated[
        float | None,
        Field(description='면적 (평)')
    ] = None


class ZigbangDanjiRoomTypeManageCostModel(ZigbangBaseResponseModel):
    """평형의 월 관리비 (**만원**). 이 밖에 개별난방 여부(`개별난방`)가 오지만 읽지 않는다."""

    average: Annotated[
        int | float | None,
        Field(description='평균 월 관리비 (만원)', alias='관리비')
    ] = None
    summer: Annotated[
        int | float | None,
        Field(description='여름 월 관리비 (만원)', alias='여름관리비')
    ] = None
    winter: Annotated[
        int | float | None,
        Field(description='겨울 월 관리비 (만원)', alias='겨울관리비')
    ] = None


class ZigbangDanjiRoomTypePriceModel(ZigbangBaseResponseModel):
    """평형의 직방 시세 범위 (매매 `sales_price`·전세 `rent_price`). 금액은 **만원**, 평당 값은 만원/3.3㎡ 다."""

    min: Annotated[
        int | None,
        Field(description='최저 시세 (만원)')
    ] = None
    max: Annotated[
        int | None,
        Field(description='최고 시세 (만원)')
    ] = None
    avg: Annotated[
        int | float | None,
        Field(description='평균 시세 (만원). 2026-11-19 표본 평형 30개 모두 null')
    ] = None
    per_area: Annotated[
        int | float | None,
        Field(description='평당 시세 (만원/3.3㎡)')
    ] = None
    change: Annotated[
        int | float | None,
        Field(description='시세 변동 (단위를 확인하지 못했다. 2026-11-19 표본 평형 30개 모두 null)')
    ] = None


class ZigbangDanjiRoomTypeModel(ZigbangBaseResponseModel):
    """단지 평형. 매물 목록(`danjiRoomTypes`)은 `id`·`room_type_title` 만 주고, 평형 조회(`room_types`)는 모두 준다.

    분양가·평면도 그림·공시가격·유형 구분 등 이 밖의 키는 읽지 않는다.
    """

    id: Annotated[
        int,
        Field(description='평형 ID (danjiRoomTypeIds 조건 값)')
    ]
    room_type_title: Annotated[
        ZigbangRoomTypeTitleModel | None,
        Field(description='평형 이름', alias='roomTypeTitle')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='그 평형의 세대수', alias='총세대수')
    ] = None
    supply_area: Annotated[
        ZigbangDanjiRoomTypeAreaModel | None,
        Field(description='공급면적', alias='공급면적')
    ] = None
    exclusive_area: Annotated[
        ZigbangDanjiRoomTypeAreaModel | None,
        Field(description='전용면적', alias='전용면적')
    ] = None
    contract_area: Annotated[
        ZigbangDanjiRoomTypeAreaModel | None,
        Field(description='계약면적', alias='계약면적')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수', alias='방')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수', alias='욕실')
    ] = None
    entrance_type: Annotated[
        str | None,
        Field(description="현관 구조 (예: '계단식')", alias='현관구조')
    ] = None
    manage_cost: Annotated[
        ZigbangDanjiRoomTypeManageCostModel | None,
        Field(description='월 관리비 (만원)')
    ] = None
    resale_available_from: Annotated[
        str | None,
        Field(description='거래 가능 시점 (YYYYMMDD). 2026-11-19 단지 38487 평형 30개 중 23개 20160601, 7개 null', alias='거래가능시점')
    ] = None
    sales_price: Annotated[
        ZigbangDanjiRoomTypePriceModel | None,
        Field(description='매매 시세')
    ] = None
    rent_price: Annotated[
        ZigbangDanjiRoomTypePriceModel | None,
        Field(description='전세 시세')
    ] = None


class ZigbangDanjisRoomTypesResponseModel(ZigbangBaseResponseModel):
    """단지의 평형 목록과 단지 평균 시세. 금액은 **만원**이고 평당 값은 만원/3.3㎡ 다.

    분양예정 단지는 `room_types` 가 빈 목록이고 평균도 null 이다 (2026-11-19 실측: 헬리오시티 38487 은 평형 30개, 가락미륭재건축
    94457 은 빈 목록). 단지 이름·유형·채권할인률 등 이 밖의 키는 읽지 않는다.
    """

    room_types: Annotated[
        list[ZigbangDanjiRoomTypeModel] | None,
        Field(description='평형. 키가 없거나 null 이면 None (모름)')
    ] = None
    average_sales_price: Annotated[
        int | float | None,
        Field(description='단지 평균 매매 시세 (만원/3.3㎡)')
    ] = None
    average_rent_price: Annotated[
        int | float | None,
        Field(description='단지 평균 전세 시세 (만원/3.3㎡)')
    ] = None
    min_sales_price: Annotated[
        int | None,
        Field(description='단지 최저 매매 시세 (만원). 분양예정 단지는 키가 없다', alias='minSalesPrice')
    ] = None
    max_sales_price: Annotated[
        int | None,
        Field(description='단지 최고 매매 시세 (만원). 분양예정 단지는 키가 없다', alias='maxSalesPrice')
    ] = None
