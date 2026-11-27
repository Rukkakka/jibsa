"""`complex.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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


class DaangnRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예: '3', '지하1'). 숫자는 floor_number")
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
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    registered: Annotated[
        bool | None,
        Field(description='등기까지 마친 거래 (매매만). 당근이 등기일을 주지 않은 거래는 false')
    ] = None
    presale: Annotated[
        str | None,
        Field(description='분양권 / 입주권 거래 (매매만). 일반 거래(소유 구분 REGISTERED_OWNER)는 키가 없고, 당근이 소유 구분을 주지 않았으면 null (모름), 표에 없는 코드는 원래 코드')
    ] = None
    not_presale: Annotated[
        bool,
        Field(exclude=True, description='분양권·입주권이 아닌 일반 거래인지 (소유 구분 REGISTERED_OWNER). presale 키를 빼는 데만 쓰고 출력하지 않는다')
    ] = False
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 배지 '재계약'). 재계약은 새 계약보다 낮게 잡히는 경우가 많다. 당근이 주지 않으면 null, 표에 없는 코드는 원래 코드")
    ] = None
    renewal_right: Annotated[
        bool | None,
        Field(description="계약갱신요구권을 쓴 계약 (전월세만, 당근 웹 배지 '갱신'. 인상률 상한이 있어 시세보다 낮다). 당근이 주지 않으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields |= {'contract_type', 'renewal_right'}
        else:
            fields |= {'cancelled', 'registered', 'presale'}
        if self.not_presale:
            fields.add('presale')
        for field in fields:
            data.pop(field, None)
        return with_floor_number(data)


class DaangnRealPriceBaseResult(Result):
    """실거래 내역 공통.

    `notes`: 전월세를 넘겨 본 범위, 거래가 없는 이유 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool | None,
        Field(description='더 오래된 거래가 더 있는지 (--years 를 줬으면 그 기간 안에서). 당근이 거래 목록을 주지 않았으면 null (모름)')
    ]
    start_date: Annotated[
        str | None,
        Field(description='--years 로 준 기간의 시작일 (YYYY-MM-DD, 이날부터 계약). 주지 않았으면 키가 없다')
    ] = None
    month: Annotated[
        str | None,
        Field(description='--month 로 준 계약 연월 (YYYY-MM). 그 달 거래만이다. 주지 않았으면 키가 없다')
    ] = None
    trades: Annotated[
        list[DaangnRealPrice] | None,
        Field(description='최근 계약 순 실거래. 거래가 없으면 [], 당근이 거래 목록을 주지 않았으면 null (모름)')
    ]

    @model_serializer(mode='wrap')
    def drop_unused_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.unused_keys():
            data.pop(field, None)
        return data

    def unused_keys(self) -> list[str]:
        """해당 없음이라 출력에서 뺄 키. 결과마다 더할 키는 이 메서드를 넓힌다 (직렬화 함수를 복사하지 않는다)."""
        return [field for field in ('start_date', 'month') if getattr(self, field) is None]


class DaangnRealPriceResult(DaangnRealPriceBaseResult):
    """단지 실거래 내역."""

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (--area). null 이면 전체 평형. --pyeong 으로 골랐으면 키가 없다')
    ] = None
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (--pyeong 으로 고른 아파트형 단지 평형). 주지 않았으면 키가 없다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 그래프는 여기서 본다)')
    ]

    def unused_keys(self) -> list[str]:
        # 평형은 공급 평형(--pyeong)이나 전용면적 묶음(--area) 중 하나로 고른다. --pyeong 이면 area_group 이 null 로 남아 그
        # 설명('null 이면 전체 평형')대로 거르지 않은 것으로 읽혔다 (2026-11-12 리뷰·실측: 헬리오시티 --pyeong 32)
        return super().unused_keys() + ['pyeong' if self.pyeong is None else 'area_group']


class DaangnListingRealPriceResult(DaangnRealPriceBaseResult):
    """매물이 있는 건물(단지)의 비슷한 면적 실거래 내역."""

    listing_id: Annotated[
        str,
        Field(description='매물 ID')
    ]
    url: Annotated[
        str,
        Field(description='매물 페이지 URL')
    ]
