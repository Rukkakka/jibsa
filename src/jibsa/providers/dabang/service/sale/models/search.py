"""`search.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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


class DabangSaleSummary(BaseModel):
    """분양 단지 하나 (목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    presale_id: Annotated[
        str,
        Field(description='분양 ID. jibsa dabang sale 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
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
        Field(description='분양 세대수 (다방 목록의 세대수 칸. 총세대수가 아니다, 총세대수는 household_count)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총세대수. 시·도·시군구·전국 범위(다방 지역 목록)만 다방이 주고 동·역·대학·좌표 범위(지도 목록)는 null')
    ] = None
    price_kind: Annotated[
        str | None,
        Field(description="가격 종류 (다방 표시. 보통 '분양가', 공공·민간임대 공급이면 '임대가'(임대 보증금이라 금액이 deposit_manwon 에 있다))")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description="분양가 (만원, 다방 표시). price_kind 가 '임대가'면 키가 없고 deposit_manwon 이다. 아직 없으면 null")
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description="임대 보증금 (만원, 다방 표시. price_kind '임대가'). 분양가면 키가 없다. 아직 없으면 null")
    ] = None
    next_schedule: Annotated[
        str | None,
        Field(description="다음 일정 ('26.12.07 ~ 26.12.10 계약기간')")
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def keep_given_amounts(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unset_fields(self, handler(self), GIVEN_AMOUNT_FIELDS)


class DabangSaleListResult(Result):
    """분양 단지 목록.

    `notes`: 범위·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description=(
            "다방이 센 분양 단지 수. 전국·시·도·시군구는 다방 분양 지역 목록의 '총 N건', 동·역·대학·좌표는 지도 범위(사각형) 안 "
            '수 (동은 주소로 거르기 전)'
        ))
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    presales: Annotated[
        list[DabangSaleSummary],
        Field(description='다방 목록 순 분양 단지')
    ]
