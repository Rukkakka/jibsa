"""단지·평형별 기관 시세 추이의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""

from datetime import date

from jibsa.core.listing import (
    months_ago,
    read_date,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.market_price import (
    NaverComplexMarketPriceListV1RequestParameterModel,
)
from jibsa.providers.naver.service.common.functions import (
    MARKET_PRICE_PROVIDER_NAMES,
    PERIOD_MONTHS_BY_NAME,
    check_pyeong_numbers,
    complex_url,
    kst_today,
    market_price_fields,
    unwrap,
)
from jibsa.providers.naver.service.market_price.models import (
    NaverMarketPriceHistory,
    NaverMarketPricePoint,
    NaverMarketPriceSeries,
)


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
        # 점은 맨 앞에, 못 읽는 글자인 점은 원 글자 순서 자리에 온다. 점은 빼지 않는다 (못 읽는 글자는 `read_date` 가 모아 출력할 때 [참고] 로 알린다)
        dates = sorted(set(item.deal_prices) | set(item.deposit_prices))
        if not dates:
            continue
        providers.append(NaverMarketPriceSeries(
            provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
            weeks=[
                NaverMarketPricePoint(
                    base_date=read_date(day, '시세 기준일'),
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
