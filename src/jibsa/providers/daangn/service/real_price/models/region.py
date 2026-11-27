"""`region.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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
from jibsa.providers.daangn.service.region.models.area import DaangnRealsaleRegion

from typing import (
    Annotated,
    Any,
)


class DaangnRegionRealPrice(BaseModel):
    """지역 실거래 한 건 (만원, 국토부 신고 기준). 거래 유형·피드에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]
    from_new_high_feed: Annotated[
        bool,
        Field(exclude=True, description='신고가 피드인지. 신고가 피드에 없는 published_date 키를 빼는 데만 쓴다')
    ] = False

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    published_date: Annotated[
        str | None,
        Field(description='실거래가 공개된 날 (YYYY-MM-DD). 신고가 피드에는 없다')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='건물·단지 이름')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='당근 단지 ID (daangn complex·real-price 에 넘긴다). 당근 단지가 아니면 키가 없다')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
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
        Field(description='신고 뒤 해제(취소)된 거래. 웹처럼 매매·전월세 모두 (전월세는 드물다)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    contract_type: Annotated[
        str | None,
        Field(description="계약 종류 (전월세만): '신규' / '재계약' (당근 웹 카드 배지 '갱신' 은 재계약이다). 당근이 주지 않으면 null, 표에 없는 코드는 원래 코드. 갱신요구권 사용 여부는 지역 피드에 없다")
    ] = None
    new_high: Annotated[
        bool | None,
        Field(description="이 거래가 이 단지·평형의 신고가인지 (매매만, 당근 웹 카드의 '신고가' 배지. 해제된 거래는 false)")
    ] = None
    prev_high_manwon: Annotated[
        float | None,
        Field(description='직전 최고가 (만원, 매매만). 당근이 비교 자료를 주지 않으면 null')
    ] = None
    prev_high_date: Annotated[
        str | None,
        Field(description='직전 최고가 계약일 (YYYY-MM-DD, 매매만)')
    ] = None
    prev_high_diff_percent: Annotated[
        float | None,
        Field(description="직전 최고가 대비 변화율 (%, 소수 둘째 자리, 매매만. 당근 웹 카드의 '직전 최고가 대비 ±N%' 와 같은 비율이고 웹은 정수로 보여 준다). 해제된 거래나 직전 최고가가 없으면 null")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('contract_type')
        else:
            # 거래 취소는 웹 카드가 거래 유형과 상관없이 보여 준다 (`yc` 의 `s.cancel===!0`). 직거래 표시와 신고가·직전 최고가는
            # 매매에만 둔다 (웹 카드도 SALE 에만 계산한다)
            fields |= {'deal_type', 'new_high', 'prev_high_manwon', 'prev_high_date', 'prev_high_diff_percent'}
        if self.from_new_high_feed:
            fields.add('published_date')
        if self.complex_id is None:
            fields.add('complex_id')
        for field in fields:
            data.pop(field, None)
        return with_floor_number(data)


class DaangnRealsaleSummary(BaseModel):
    """지역 실거래 화면 머리의 요약 (웹 'MM월 DD일 매매 N건 · 신고가 N건')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    latest_published_date: Annotated[
        str | None,
        Field(description='가장 최근 공개일 (YYYY-MM-DD)')
    ] = None
    sale_count: Annotated[
        int | None,
        Field(description='그 공개일의 매매 거래 수')
    ] = None
    new_high_count: Annotated[
        int | None,
        Field(description='그 공개일의 신고가 수')
    ] = None


class DaangnRegionRealPriceResult(Result):
    """동·구의 최근 실거래 또는 신고가.

    `notes`: 지역을 고른 방법, 넘겨 본 범위 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    new_high_only: Annotated[
        bool,
        Field(description='신고가 매매만 모았는지')
    ]
    sort: Annotated[
        str,
        Field(description='가격 (매매·신고가: 최근 공개일부터, 같은 날 안에서 가격 높은 순. 당근 웹과 같다) / 최신 (전세·월세: 최근 공개 순)')
    ]
    summary: Annotated[
        DaangnRealsaleSummary | None,
        Field(description='가장 최근 공개일과 그날의 매매·신고가 수 (웹 실거래 화면 머리). 받지 못하면 null 이고 notes 가 알린다')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 있는지')
    ]
    trades: Annotated[
        list[DaangnRegionRealPrice],
        Field(description='실거래')
    ]
