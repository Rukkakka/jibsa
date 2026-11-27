"""`trades.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    Result,
    TradeType,
    with_floor_number,
)
from jibsa.providers.dabang.service.real_price.constants import RealPriceTrade

from typing import (
    Annotated,
    Any,
    Literal,
)


# 매물 실거래 줄의 면적 칸. 단지 실거래는 평형으로 고르므로 면적이 없다(none). 매물 실거래는 웹처럼 다세대·연립(MULTIPLEX)이면
# 전용면적·층, 그 밖(DETACHED 단독·다가구)이면 연면적·주택유형(매매만)이다 (room 청크 `ii` 가 MULTIPLEX 만 `Kr`, 나머지는 `ei`)
AreaKind = Literal['none', 'exclusive', 'total_floor']


class DabangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 금액은 키가 없다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        TradeType,
        Field(description='거래 유형 (매매·전세·월세)')
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 ('5', '지하1'). 모르면 null. 바로 뒤 floor_number 는 몇 층인지 아는 층의 숫자 (지하는 음수, 모르면 null)")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡, --listing 의 다세대·연립 거래만. 단지는 평형으로 고른다)')
    ] = None
    total_floor_area_m2: Annotated[
        float | None,
        Field(description='연면적 (㎡, 다방 화면의 이름. --listing 의 단독·다가구 거래만. 매물 전용면적과 기준이 달라 그대로 견주지 않는다)')
    ] = None
    house_type: Annotated[
        str | None,
        Field(description="주택 유형 ('단독', '다가구', --listing 의 단독·다가구 매매만)")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금·전세금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제된 거래')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description="거래 방식 ('직거래'·'중개거래'). 다방이 직거래 여부를 주지 않으면 null")
    ] = None
    # 리뷰 오탐 (2026-11-13): 단독·다가구 줄에 isRegistration 이 없어 키를 빼야 한다는 지적. 웹 단독·다가구 표(room 청크 `ei`)도
    # 다세대 표처럼 `e.isRegistration` 이 참이면 등기 표시를 그린다. 다방이 이 줄에 값을 주지 않을 뿐이라 해당 없음이 아니라 모름(null)이다
    registered: Annotated[
        bool | None,
        Field(description='등기된 거래 (다방 화면의 등기 표시). 다방이 주지 않으면 null (단독·다가구 거래)')
    ] = None
    newly_added: Annotated[
        bool | None,
        Field(description='다방이 새 거래로 표시한 거래 (화면의 새 거래 표시)')
    ] = None
    area_kind: Annotated[
        AreaKind,
        Field(exclude=True, description='낼 면적 키 (단지 실거래는 없음)')
    ] = 'none'

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        dropped = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.area_kind != 'exclusive':
            dropped.add('area_m2')
        if self.area_kind != 'total_floor':
            dropped |= {'total_floor_area_m2', 'house_type'}
        else:
            # 웹 단독·다가구 표에는 층 칸이 없고(`ei`) 원본 층도 'null' 글자다. 주택유형은 매매 표에만 있다
            dropped.add('floor')
            if self.trade_type != '매매':
                dropped.add('house_type')
        for field in dropped:
            data.pop(field, None)
        return with_floor_number(data)


class DabangRealPriceResult(Result):
    """실거래 내역.

    `notes`: 평형·범위 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 실거래만)')
    ] = None
    listing_id: Annotated[
        str | None,
        Field(description='매물 ID (--listing 만)')
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID (단지 실거래만)')
    ] = None
    trade_tab: Annotated[
        RealPriceTrade,
        Field(description='매매 또는 전월세')
    ]
    start_month: Annotated[
        str,
        Field(description='조회 시작 달 (YYYY-MM)')
    ]
    end_month: Annotated[
        str,
        Field(description='조회 끝 달 (YYYY-MM)')
    ]
    basis: Annotated[
        str | None,
        Field(description=(
            "거래를 모은 범위 (--listing 만): '이 집 (망원동 다세대·연립)' 은 이 매물과 같은 지번 건물, '역삼동 단독·다가구' 는 "
            '그 동의 같은 건물 유형. 다방이 범위를 알려 주지 않으면 null'
        ))
    ] = None
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='기간 안에 더 오래된 거래가 더 있는지')
    ]
    trades: Annotated[
        list[DabangRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    url: Annotated[
        str,
        Field(description='단지·매물 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('complex_id', 'listing_id', 'pyeong_id'):
            if data.get(key) is None:
                data.pop(key, None)
        # 기준 범위는 매물 실거래(--listing)에만 해당한다. 그때 비면 모름(null)으로 남긴다
        if self.listing_id is None:
            data.pop('basis', None)
        return data
