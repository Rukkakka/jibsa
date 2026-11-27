"""`trend.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.zigbang.service.complex.constants import (
    ZigbangPriceTrendPeriod,
    ZigbangPyeongTrendTrade,
)
from jibsa.providers.zigbang.service.complex.models.common import ZigbangRelatedComplex

from typing import (
    Annotated,
    Any,
    Literal,
)


ZigbangPriceLineKind = Literal['단지', '비교 단지', '구']


class ZigbangComplexPricePoint(BaseModel):
    """직방시세 추이의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 평당가 (만원/3.3㎡). 직방이 0 을 준 달은 시세가 없는 달이라 null (점은 남는다)')
    ]


class ZigbangComplexPriceLine(BaseModel):
    """직방시세 추이의 줄 하나 (조회 단지, 비교 단지, 그 구). 직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='줄 이름 (직방이 준 label: 단지 이름 또는 구 이름)')
    ]
    kind: Annotated[
        ZigbangPriceLineKind | None,
        Field(
            description=(
                "줄 종류. 이름이 --compare 로 준 단지의 이름이면 '비교 단지', 마지막 줄이면 '구', 남은 줄이면 '단지'(조회 단지). "
                '직방이 줄 순서를 단지 ID 순으로 줘서 위치로는 알 수 없다. 직방시세가 없는 단지는 조회 단지 줄 없이 (비교 단지와) 구 줄만 와서 '
                "그때도 마지막 줄이 '구' 다. 이름이 겹치거나 줄 수가 (조회 단지 + 비교 단지 + 구)·(비교 단지 + 구) 와 다르거나 "
                '빈 줄을 뺐으면 판정하지 않고 null'
            )
        )
    ]
    complex_id: Annotated[
        str | None,
        Field(description="비교 단지의 단지 ID (kind 가 '비교 단지' 인 줄에만 있고 그 밖은 키가 없다)")
    ] = None
    months: Annotated[
        list[ZigbangComplexPricePoint] | None,
        Field(description='월별 매매 직방시세 평당가 (오래된 달부터). 직방이 월 목록을 주지 않으면 null')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.kind != '비교 단지':
            data.pop('complex_id', None)
        return data


class ZigbangPriceTrendResult(Result):
    """단지 직방시세 추이 (웹 단지 화면 직방시세 그래프 '3.3㎡ 당 평균가격', 기간 탭·단지 비교).

    `notes`: 비교 후보를 받지 못했다는 [실패] 안내, 시세 추이가 없다·줄 목록을 주지 않았다·구 줄만 있다는 [참고] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    comparable_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(
            description=(
                "웹 '단지 비교하기' 의 '단지 선택' 창 후보 (같이 많이 본 단지, 직방이 준 순서). --compare 에는 이 목록의 단지만 받는다. "
                '후보가 없으면 [], 직방이 주지 않았거나 받지 못하면 모름(null)'
            )
        )
    ]
    lines: Annotated[
        list[ZigbangComplexPriceLine] | None,
        Field(
            description=(
                '직방시세 그래프의 줄 (직방 응답 순서 그대로). 값은 매매 직방시세(직방이 실거래를 분석한 추정값)의 평당가이고 실거래가가 아니다. '
                '직방은 줄을 단지 ID 오름차순으로 주고 구를 끝에 붙여, 첫 줄이 조회 단지가 아닐 수 있다 (줄 종류는 kind). '
                '직방이 줄 목록을 주지 않으면 null (줄 목록 null 의 [참고] 안내), 줄이 없으면 []. '
                '직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다 (구 줄만 있다는 [참고] 안내)'
            )
        )
    ]


class ZigbangPyeongSale(BaseModel):
    """평형 하나의 한 달 매매 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달(입주 전 등)은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(description='그 달 매매 거래의 가격 범위 (lowest 최저가·highest 최고가, price_manwon). 시세가 없는 달과, 거래가 0건인 달(직방이 시세 값을 대신 채워 준다)은 null')
    ]
    trade_count: Annotated[
        int | None,
        Field(description='그 달 매매 거래 건수 (0 도 진짜 값)')
    ]
    estimated_price_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongJeonseWolse(BaseModel):
    """평형 하나의 한 달 전월세 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_deposit_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 전세 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(
            description=(
                '그 달 전세·월세 거래를 합친 가격 범위 (lowest 최저가·highest 최고가, 둘 다 converted_price_manwon 하나뿐). 월세는 직방이 '
                '보증금 + 월세 × 300 으로 환산한 값이고 (2026-11-22 실측) 보증금이 아니다. 시세가 없는 달과, 거래가 0건인 달은 null'
            )
        )
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="그 달 거래 건수. 늘 'jeonse'·'wolse' 두 키이고 값은 건수 (0 도 진짜 값, 직방이 주지 않으면 null)")
    ]
    estimated_deposit_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 전세 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongPriceMonth(BaseModel):
    """평형 시세 추이의 한 달. 고르지 않은 거래 탭의 키는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade: Annotated[
        ZigbangPyeongTrendTrade,
        Field(exclude=True, description='고른 거래 탭. 해당 없는 탭의 키를 빼는 데 쓰고 출력하지 않는다')
    ]
    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    sale: Annotated[
        ZigbangPyeongSale | None,
        Field(description='매매 시세·거래. 직방이 그 달의 매매 기록을 주지 않았으면 null. --trade 전월세 에는 키가 없다')
    ]
    jeonse_wolse: Annotated[
        ZigbangPyeongJeonseWolse | None,
        Field(description='전월세 시세·거래. 직방이 그 달의 전월세 기록을 주지 않았으면 null. --trade 매매 에는 키가 없다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.trade == '매매':
            data.pop('jeonse_wolse', None)
        elif self.trade == '전월세':
            data.pop('sale', None)
        return data


class ZigbangPyeongPriceTrendResult(Result):
    """평형 하나의 월별 시세·거래 추이 (웹 단지 화면 평형 탭의 직방시세 그래프, 전체·매매·전월세 탭). 거래 점과 전세가율은 내지 않는다.

    `notes`: 평형 시세 기록이 없다는 [참고] 안내, 월 목록을 주지 않았다는 [참고] 안내, 빈 항목을 뺐다는 [제외] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (complex 결과의 pyeongs[].pyeong_id)')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    trade_tab: Annotated[
        ZigbangPyeongTrendTrade,
        Field(description='거래 탭 (--trade 값: 전체·매매·전월세)')
    ]
    months: Annotated[
        list[ZigbangPyeongPriceMonth] | None,
        Field(description='월별 시세·거래 (오래된 달부터). 매매·전월세 기록을 월로 맞춘 목록이고 기록이 없으면 [], 직방이 월 목록을 주지 않았으면 null')
    ]
