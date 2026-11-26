"""아파트 실거래가의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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
    with_floor_number,
)

from typing import (
    Annotated,
    Any,
)


class ZigbangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다.

    거래 유형(`trade_type`)은 보통 결과 맨 위에 있어 거래마다 내지 않고, 전체 조회에서만 거래마다 낸다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데 쓰고, 전체 조회(show_trade_type)가 아니면 출력하지 않는다')
    ]
    show_trade_type: Annotated[
        bool,
        Field(exclude=True, description='거래마다 trade_type 을 맨 앞에 낼지 (전체 조회만 참, 거래 유형이 거래마다 달라서)')
    ] = False
    dropped_candidates: Annotated[
        int,
        Field(exclude=True, description=(
            '평형 후보 목록(areaInfos)에서 뺀 빈 항목(null) 수. 0 보다 크면 후보 수를 몰라 pyeong_name 은 null 이고, '
            '후보가 하나만 남아도 pyeong_names 키를 지우지 않는다. 결과의 안내(notes)를 만드는 데 쓴다'
        ))
    ] = 0

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description=(
            '평형 이름 (공급면적 평 기준, 예: 34A). 후보가 여럿이면 "32A 외 4" '
            '(같은 전용면적의 평형이 여럿이라 어느 평형인지 직방도 모른다). 직방이 후보를 주지 않거나 첫 후보의 평 이름을 주지 않거나 '
            '빈 항목을 줘 셀 수 없으면 null (후보는 pyeong_names)'
        ))
    ] = None
    pyeong_names: Annotated[
        list[str | None] | None,
        Field(description=(
            '평형 후보 이름 전부 (응답 순서, 직방이 평 이름을 주지 않은 후보는 null). 후보가 하나면 키가 없고, 직방이 후보를 주지 않으면 null. '
            '직방이 후보 목록에 빈 항목을 줘 뺐으면 받은 후보만 담고 하나여도 키를 둔다 (후보가 정말 하나인지 알 수 없다)'
        ))
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    presale: Annotated[
        str | None,
        Field(description='분양권 / 입주권 거래 (매매만, 해당할 때만 키가 있다)')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신·재계약 (전월세만). 직방은 알려 주지 않아 항상 null')
    ] = None
    building_dong: Annotated[
        str | None,
        Field(description="동 ('132' 처럼 '동' 없이 직방 글자 그대로, 모든 거래). 직방이 주지 않으면 null (지금까지 본 전월세는 늘 null)")
    ] = None
    registered: Annotated[
        bool | None,
        Field(description=(
            '등기까지 마무리된 거래 (매매만). 직방은 2023년 1월 이후 계약만 표시하고 등기된 것에만 값을 줘서, 표시가 없으면 '
            '2023년 이전 계약인지 아직 등기 전인지 알 수 없어 false 가 아니라 null. 전월세는 키가 없다'
        ))
    ] = None
    new_high: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 높은 거래가를 경신한 신고가 거래 (매매·전세). 직방이 표시하지 않은 거래는 false. 단지 전체 최고가와 견준 값이 아니다. 월세는 키가 없다')
    ] = None
    new_low: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 낮은 거래가를 경신한 신저가 거래 (매매·전세). 표시 규칙은 new_high 와 같다. 월세는 키가 없다')
    ] = None
    price_per_pyeong_manwon: Annotated[
        int | None,
        Field(description='공급면적 3.3㎡당 가격 (만원 정수). 직방이 계산해 만원으로 반올림한 값을 그대로 낸다 (매매만, 직방이 주지 않으면 null). 전월세는 키가 없다')
    ] = None
    jeonse_ratio_percent: Annotated[
        float | None,
        Field(description=(
            '전세가율 (%, 직방이 준 0~1 비율에 100 을 곱한 반올림하지 않은 값. 웹은 정수 % 로 반올림해 보여 준다). 분모는 그 달 직방 시세다 (실거래 평균이 아님). '
            '전세이고 직방이 값을 준 거래에만 키가 있다 (평형을 지정한 조회에서만 온다)'
        ))
    ] = None
    presale_price_diff_manwon: Annotated[
        int | None,
        Field(description='분양가 대비 차액 (만원 정수, 양수면 거래가가 분양가보다 높고 0·음수도 그대로). 분양권 거래에 있고 직방이 주지 않으면 null. 분양권이 아닌 거래(입주권 포함)는 직방이 값을 주지 않으면 키가 없다')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('renewal')
        else:
            fields |= {'deal_type', 'cancelled', 'presale'}
        if self.presale is None:
            fields.add('presale')
        # 등기·평당가는 직방이 매매에만 주고(동은 웹이 전월세에도 그려 모든 거래에 낸다), 신고가·신저가는 월세에는 주지 않는다. 전세가율은 전세에 값이 있을 때만 키를 둔다.
        # 분양가 대비 차액은 분양권이면 값이 없어도 모름(null)으로 키를 두고, 그 밖에는 값이 있을 때만 둔다
        if self.trade_type != '매매':
            fields |= {'registered', 'price_per_pyeong_manwon'}
        if self.trade_type == '월세':
            fields |= {'new_high', 'new_low'}
        if self.trade_type != '전세' or self.jeonse_ratio_percent is None:
            fields.add('jeonse_ratio_percent')
        if self.presale_price_diff_manwon is None and self.presale != '분양권':
            fields.add('presale_price_diff_manwon')
        # 후보가 하나면 해당 없음이라 키를 지운다. 후보를 주지 않았으면(None) 모름이라 null 로 둔다. 빈 항목을 뺐으면 하나인지 알 수 없어 둔다
        if self.pyeong_names is not None and len(self.pyeong_names) == 1 and not self.dropped_candidates:
            fields.add('pyeong_names')
        for field in fields:
            data.pop(field, None)
        data = with_floor_number(data)
        if self.show_trade_type:
            data = {'trade_type': self.trade_type, **data}
        return data


class ZigbangRealPriceResult(Result):
    """아파트 단지 실거래 내역.

    `notes`: 전월세를 넘겨 본 범위 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID. null 이면 전체 평형')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 오래된 거래가 더 있는지')
    ]
    trades: Annotated[
        list[ZigbangRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 추이는 `jibsa zigbang price-trend <complex_id>` 로 본다)')
    ]
