"""단지·평형별 기관 시세 추이 (market-price)."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    months_ago,
    normalize_date,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.market_price import (
    NaverComplexMarketPriceListV1RequestParameterModel,
)
from jibsa.providers.naver.service.common import (
    MARKET_PRICE_PROVIDER_NAMES,
    PERIOD_MONTHS_BY_NAME,
    check_pyeong_numbers,
    complex_url,
    kst_today,
    manwon_range,
    unwrap,
)

from typing import Annotated


class NaverMarketPricePoint(BaseModel):
    """한 기준일의 기관 시세 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    base_date: Annotated[
        str | None,
        Field(description="시세 기준일 (YYYY-MM-DD). 네이버가 날짜 자리를 빈 값·'-' 로 주면 null")
    ]
    sale_manwon: Annotated[
        float | None,
        Field(description='매매 시세 평균 (만원). 없으면 null')
    ] = None
    sale_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_manwon: Annotated[
        float | None,
        Field(description='전세 시세 평균 (만원). 없으면 null')
    ] = None
    jeonse_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_ratio_percent: Annotated[
        list[float | None] | None,
        Field(description='전세가율 [하한, 상한] (%). 시세가 없으면(0 포함) null')
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
    points: Annotated[
        list[NaverMarketPricePoint],
        Field(description='기준일별 시세 (오래된 것부터, 보통 주 1회)')
    ]


class NaverMarketPriceHistory(BaseModel):
    """평형의 기관별 시세 추이."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_number: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_number: Annotated[
        int,
        Field(description='평형 번호')
    ]
    period: Annotated[
        str,
        Field(description='기간 (3개월, 1년, 3년, 5년)')
    ]
    since: Annotated[
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
        # dates 는 dict 키라 None 은 없고 ''·'-' 만 올 수 있다 (base_date null 이 된다). 정렬은 원 글자 키로 하므로 그런 점은
        # 맨 앞에 온다. 점은 빼지 않는다 (이 결과에는 notes 가 없어 뺀 것을 알릴 곳이 없다)
        dates = sorted(set(item.deal_prices) | set(item.deposit_prices))
        if not dates:
            continue
        providers.append(NaverMarketPriceSeries(
            provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
            points=[
                NaverMarketPricePoint(
                    base_date=normalize_date(day),
                    # 평균 0 은 범위(manwon_range)처럼 없음으로 본다 (complex --pyeong 의 `_pyeong_details` 와 같다)
                    sale_manwon=won_to_manwon(item.deal_prices.get(day)) or None,
                    sale_range_manwon=manwon_range(item.deal_price_ranges.get(day)),
                    jeonse_manwon=won_to_manwon(item.deposit_prices.get(day)) or None,
                    jeonse_range_manwon=manwon_range(item.deposit_price_ranges.get(day)),
                    jeonse_ratio_percent=manwon_range(item.lease_per_deal_rates.get(day), scale=False),
                )
                for day in dates
            ],
        ))
    return NaverMarketPriceHistory(
        complex_number=complex_number,
        pyeong_number=pyeong_number,
        period=period,
        since=since,
        providers=providers,
        url=complex_url(complex_number),
    )
