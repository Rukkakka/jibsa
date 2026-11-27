"""`schedule.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.core.schema import drop_unset_fields
from jibsa.providers.dabang.service.sale.constants import GIVEN_AMOUNT_FIELDS

from typing import (
    Annotated,
    Any,
)


class DabangSaleScheduleSale(BaseModel):
    """청약 일정 줄의 분양 단지 정보 (`--details`, 다방 청약 일정 화면에서 날짜를 누르면 나오는 표)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    status: Annotated[
        str | None,
        Field(description='분양 상태 (분양예정·접수중·접수마감·입주예정·입주모집)')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형 (공공분양·민간분양·공공임대·민간임대)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    presale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수 (다방 표의 세대수 칸. 총세대수가 아니다)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총세대수')
    ] = None
    price_kind: Annotated[
        str | None,
        Field(description="가격 종류 (다방 표시. '분양가', 공공·민간임대 공급이면 '임대가'(임대 보증금이라 금액이 deposit_manwon 에 있다))")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description="분양가 (만원, 다방 표시). price_kind 가 '임대가'면 키가 없고 deposit_manwon 이다. 아직 없으면 null")
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description="임대 보증금 (만원, 다방 표시. price_kind '임대가'). 분양가면 키가 없다. 아직 없으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def keep_given_amounts(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unset_fields(self, handler(self), GIVEN_AMOUNT_FIELDS)


class DabangSaleScheduleItem(BaseModel):
    """청약 일정 한 줄."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str,
        Field(description='날 (YYYY-MM-DD)')
    ]
    kind: Annotated[
        str | None,
        Field(description="종류 ('접수', '당첨자발표' 등 다방 표시)")
    ] = None
    sido: Annotated[
        str | None,
        Field(description="일정 글의 시·도 ('서울', '경기'). 글이 시·도 없이 시나 단지 이름으로 시작하면 null")
    ] = None
    text: Annotated[
        str,
        Field(description="일정 글 ('[청약접수] 인천 … (~10/27)')")
    ]
    presale_id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None
    # 그 날 상세를 받지 않은 줄(--details·--region 없이)은 해당 없음이라 키를 빼고, 받았는데 그 날
    # 상세에서 이 줄을 찾지 못하면 모름이라 null 로 낸다 (`fetched`)
    presale: Annotated[
        DabangSaleScheduleSale | None,
        Field(description='분양 단지 정보 (--details·--region 일 때만. 그 날 상세에서 같은 분양·종류를 찾지 못한 줄은 null)')
    ] = None
    fetched: Annotated[
        bool,
        Field(exclude=True, description='그 날 분양 단지 표(상세)를 받았는지. 받지 않았으면 presale 키를 뺀다')
    ] = False

    @model_serializer(mode='wrap')
    def drop_unfetched_sale(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.fetched:
            data.pop('presale', None)
        return data


class DabangSaleSchedule(Result):
    """날짜별 청약 일정.

    `notes`: 일부·거르기 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    start_date: Annotated[
        str,
        Field(description='시작 날')
    ]
    end_date: Annotated[
        str,
        Field(description='끝 날')
    ]
    total: Annotated[
        int | None,
        Field(description='기간 안 일정 수 (--region 으로 거르기 전). 다방이 빈 항목을 줘 셀 수 없으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 일정 수')
    ]
    schedules: Annotated[
        list[DabangSaleScheduleItem],
        Field(description='날짜 순 일정')
    ]
