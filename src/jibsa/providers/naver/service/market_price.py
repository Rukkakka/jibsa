"""단지·평형별 기관 시세 추이 (market-price)."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    iso_date,
    months_ago,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.market_price import (
    NaverComplexMarketPriceListV1RequestParameterModel,
)
from jibsa.providers.naver.service.common import (
    MARKET_PRICE_PROVIDER_NAMES,
    PERIOD_MONTHS_BY_NAME,
    NaverMarketBand,
    check_pyeong_numbers,
    complex_url,
    kst_today,
    market_price_fields,
    unwrap,
)

from typing import Annotated


class NaverMarketPricePoint(BaseModel):
    """한 기준일의 기관 시세 (만원). (`naver complex --pyeong` 의 `estimated_prices` 원소와 같은 모양)"""

    model_config = ConfigDict(
        extra='forbid',
    )

    base_date: Annotated[
        str | None,
        Field(description="시세 기준일 (YYYY-MM-DD). 네이버가 날짜 자리를 빈 값·'-' 로 주거나 읽을 수 없으면 null")
    ]
    sale: Annotated[
        NaverMarketBand | None,
        Field(description='매매 시세 (평균·하위·상위, 만원). 세 값을 모두 모르면 null, 일부만 모르면 그 칸만 null')
    ]
    jeonse: Annotated[
        NaverMarketBand | None,
        Field(description='전세 시세 (평균·하위·상위, 만원). 세 값을 모두 모르면 null, 일부만 모르면 그 칸만 null')
    ]
    jeonse_ratio_low_percent: Annotated[
        float | None,
        Field(description='전세가율 하한 (%). 시세가 없으면(0 포함) null')
    ] = None
    jeonse_ratio_high_percent: Annotated[
        float | None,
        Field(description='전세가율 상한 (%). 시세가 없으면(0 포함) null')
    ] = None


class NaverMarketPriceSeries(BaseModel):
    """한 기관의 기간 안 시세."""

    model_config = ConfigDict(
        extra='forbid',
    )

    provider: Annotated[
        str,
        Field(description='시세 기관 (한국부동산원, KB부동산, 부동산뱅크)')
    ]
    weeks: Annotated[
        list[NaverMarketPricePoint],
        Field(description='기준일별 시세 (오래된 것부터, 보통 주 1회). 점마다 base_date 가 있다')
    ]


class NaverMarketPriceHistory(BaseModel):
    """평형의 기관별 시세 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 번호')
    ]
    period: Annotated[
        str,
        Field(description='기간 (3개월, 1년, 3년, 5년)')
    ]
    start_date: Annotated[
        str,
        Field(description='기간 시작일 (YYYY-MM-DD)')
    ]
    providers: Annotated[
        list[NaverMarketPriceSeries],
        Field(description='기관별 시세. 시세가 없는 평형이면 []')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


def get_market_price_history(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    period: str = '1년',
    villa: bool | None = None,
    today: date | None = None,
) -> NaverMarketPriceHistory:
    """평형의 기관별(한국부동산원·KB부동산·부동산뱅크) 주별 시세를 기간만큼 받는다 (1회 호출).

    Args:
        period: `PERIOD_MONTHS_BY_NAME` 의 이름.
        villa: 빌라 단지인지 (`resolve_complex_number` 결과). 알면 시세가 0건일 때 평형 확인에서 단지 정보를 묻지 않는다.
        today: 기간의 기준일. Defaults to 오늘(한국 시간).

    Raises:
        JibsaError: 시세가 0건인데 평형 번호가 그 단지에 없으면 NOT_FOUND.
    """
    today = today or kst_today()
    since = months_ago(today, PERIOD_MONTHS_BY_NAME[period])
    items = unwrap(
        client.run_request_complex_market_price_list_v1(
            NaverComplexMarketPriceListV1RequestParameterModel(
                complex_number=complex_number,
                pyeong_type_number=pyeong_number,
                start_date=since,
                end_date=today.isoformat(),
            )
        ),
        '시세',
    )
    # 없는 평형 번호면 기관별 항목 없이 빈 목록이 와서 여기서 NOT_FOUND 가 난다 (헬리오시티 111515 평형 999, 2026-10-11).
    # 날짜 없는 기관 항목(빈 dict)은 평형은 있고 그 기관 시세만 없는 것이라 평형을 다시 확인하지 않는다
    if not items:
        check_pyeong_numbers(client, complex_number, [pyeong_number], villa=villa, pyeong_required=True)
    providers: list[NaverMarketPriceSeries] = []
    for item in items:
        # dates 는 dict 키라 None 은 없다. ''·'-' 와 못 읽는 글자는 base_date null 이 된다. 정렬은 원 글자 키로 하므로 빈 값·'-' 인
        # 점은 맨 앞에, 못 읽는 글자인 점은 원 글자 순서 자리에 온다. 점은 빼지 않는다 (이 결과에는 notes 가 없어 뺀 것을 알릴 곳이 없다)
        dates = sorted(set(item.deal_prices) | set(item.deposit_prices))
        if not dates:
            continue
        providers.append(NaverMarketPriceSeries(
            provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
            weeks=[
                NaverMarketPricePoint(
                    base_date=iso_date(day),
                    **market_price_fields(
                        item.deal_prices.get(day),
                        item.deal_price_ranges.get(day),
                        item.deposit_prices.get(day),
                        item.deposit_price_ranges.get(day),
                        item.lease_per_deal_rates.get(day),
                    ),
                )
                for day in dates
            ],
        ))
    return NaverMarketPriceHistory(
        complex_id=complex_number,
        pyeong_id=pyeong_number,
        period=period,
        start_date=since,
        providers=providers,
        url=complex_url(complex_number),
    )
