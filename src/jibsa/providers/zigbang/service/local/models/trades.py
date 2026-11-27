"""`trades.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.zigbang.service.local.constants import (
    LOCAL_DONG_DESCRIPTION,
    LocalTrade,
    LocalTradePeriod,
)
from jibsa.providers.zigbang.service.local.models.common import (
    ZigbangLocalModel,
    ZigbangLocalRegion,
)

from typing import (
    Annotated,
)


class ZigbangRegionTrade(ZigbangLocalModel):
    """지역 최근 실거래 한 줄. 거래 유형에 해당하지 않는 칸은 키가 없다 (매매 가격·비교는 매매만, 보증금은 전세·월세, 월세료는 월세만).

    웹은 정렬마다 비교 한 가지(직전 거래·직방시세·공시가격·분양가·전세가)만 그리지만, 여기서는 같은 응답의 비교 칸을 모두 낸다. 금액은 만원이다.
    """

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    area_type: Annotated[
        str | None,
        Field(description="평형 이름 (웹 '{평형 이름}㎡', 예: 110D). 직방이 주지 않으면 null")
    ]
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내). 목록은 계약일 순이 아니라 등록일 기준이다')
    ]
    presale: Annotated[
        str | None,
        Field(description='분양권·입주권 거래 (해당할 때만 키가 있다. real-price 의 presale 과 같다)')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='매매가 (만원). 매매만 있고 전세·월세는 키가 없다')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='보증금·전세금 (만원). 전세·월세만 있고 매매는 키가 없다')
    ]
    rent_manwon: Annotated[
        int | float | None,
        Field(description='월세 (만원). 월세만 있고 매매·전세는 키가 없다')
    ]
    prev_trade_diff_manwon: Annotated[
        int | float | None,
        Field(
            description=(
                "직전 거래 대비 차액 (만원, 매매·전세). 직방이 칸을 주지 않으면 null (웹 '직전거래 없음'), 0 은 웹 '차이 없음'. "
                '입주권 줄은 웹이 그리지 않아 키가 없고, 입주 전 계약 전세 줄도 웹이 그리지 않아 null. 월세는 키가 없다'
            )
        )
    ]
    prev_trade_diff_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, prev_trade_diff_manwon 과 같은 규칙)')
    ]
    estimated_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="직방시세 대비 차액 (만원, 매매만). 분양권·입주권이거나 직방시세가 없으면(isNoMarketPriceGap) 웹이 '직방시세 없음' 이라 null. 직방시세가 있는데 0 이면 진짜 0")
    ]
    estimated_price_diff_percent: Annotated[
        int | float | None,
        Field(description='직방시세 대비 변동률 (%, estimated_price_diff_manwon 과 같은 규칙)')
    ]
    public_price_diff_manwon: Annotated[
        int | float | None,
        Field(description="공시가격 대비 차액 (만원, 매매만). 공시가격이 없으면(isNoPublicPriceGap) 웹이 '공시가격 업데이트 예정' 이라 null. 공시가격이 있는데 0 이면 진짜 0")
    ]
    public_price_diff_percent: Annotated[
        int | float | None,
        Field(description='공시가격 대비 변동률 (%, public_price_diff_manwon 과 같은 규칙)')
    ]
    presale_price_diff_manwon: Annotated[
        int | float | None,
        Field(description='분양가 대비 차액 (만원, 분양권·입주권 매매 줄에만 키가 있다). 직방이 분양가 대비 값을 주지 않으면(isNoOfferPriceGap) null')
    ]
    presale_price_diff_percent: Annotated[
        int | float | None,
        Field(description='분양가 대비 변동률 (%, presale_price_diff_manwon 과 같은 규칙)')
    ]
    jeonse_comparison_diff_manwon: Annotated[
        int | float | None,
        Field(description="전세가 비교 차액 (만원, 전세만). 웹 '전세가 비교': 갱신 거래(renewal)는 이전 전세가 대비, 아니면 2년 전 평균 전세가 대비. 입주 전 계약 거래(pre_move_in_contract)는 웹이 차액을 그리지 않아 null")
    ]
    jeonse_comparison_diff_percent: Annotated[
        int | float | None,
        Field(description='전세가 비교 변동률 (%, jeonse_comparison_diff_manwon 과 같은 규칙)')
    ]
    pre_move_in_contract: Annotated[
        bool | None,
        Field(description="입주 전 계약 거래 (웹 '입주 전 계약 거래', 전세만). 직방이 칸을 주지 않으면 false")
    ]
    new_high: Annotated[
        bool | None,
        Field(description='신고가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    new_low: Annotated[
        bool | None,
        Field(description='신저가 (웹 배지, 매매·전세. 월세는 키가 없다). 직방이 칸을 주지 않으면 false')
    ]
    renewal: Annotated[
        bool | None,
        Field(description="갱신 계약 (웹 '계약갱신' 배지, 전세만. 매매에는 웹이 그리지 않아 키가 없고, 월세는 직방이 값을 줘도 웹이 그리지 않아 키가 없다). 직방이 칸을 주지 않으면 false")
    ]


class ZigbangRegionTradesResult(ZigbangLocalModel, Result):
    """동·구의 최근 실거래 (직방 웹 지역 화면 '실거래', 등록일 기준). 기간이 오늘이 아니면 `updated_today` 키가 없다.

    `notes`: 일부만 받았다는 안내·실거래가 없다는 안내·아직 반영 전이라는 안내·빈 항목을 빼고 읽었다는 안내. CLI 가 결과 위에 붙인다
    """

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    period: Annotated[
        LocalTradePeriod,
        Field(description='등록 기간. 오늘·어제·7일(최근 일주일)·15일·30일')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 최신 등록순)')
    ]
    registered_period: Annotated[
        str | None,
        Field(
            description=(
                "직방이 준 기간과 등록 건수 문구 (예: '10. 23 ~ 11. 22 등록 135건'). 직방이 주지 않으면 null. "
                '기간이 오늘이고 직방이 아직 반영 전(updated_today false)이면 웹처럼 숨겨 null'
            )
        )
    ]
    updated_today: Annotated[
        bool | None,
        Field(
            description=(
                "직방이 오늘 등록된 실거래를 반영했는지 (직방은 매일 낮 12시에 반영한다. false 면 직방 웹은 '오늘 12시에 실거래가 업데이트 될 예정입니다' 를 보여 준다). "
                '--period 오늘 일 때만 있고 다른 기간은 키가 없다. 직방이 주지 않으면 null'
            )
        )
    ]
    total: Annotated[
        int | None,
        Field(description='기간 안 등록된 실거래 전체 건수 (limit 적용 전). 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 실거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='--limit 을 늘리면 더 받을 수 있는 실거래가 남았는지 (직방이 --limit 보다 적게 줘 더 받을 수 없으면 false. 이어 받기는 없다)')
    ]
    trades: Annotated[
        list[ZigbangRegionTrade],
        Field(description='최근 실거래 (정렬 순서 그대로)')
    ]
