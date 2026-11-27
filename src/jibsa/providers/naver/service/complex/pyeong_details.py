"""선택 평형 부가 정보 (`pyeong_details`): 관리비·최신 시세·실거래 요약·평당가."""

from datetime import date

from jibsa.core.listing import (
    floor_text,
    holding_unread_dates,
    keep_unread_dates,
    months_ago,
    normalize_date,
    read_date,
    read_month,
    won_to_manwon,
    years_ago,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.complex import (
    NaverComplexMaintenanceFeeV1RequestParameterModel,
    NaverComplexMarketPriceRecentV1RequestParameterModel,
    NaverComplexPyeongPricePyeongTypeV1RequestParameterModel,
    NaverComplexPyeongRealPriceSummaryV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.complex import (
    NaverComplexPyeongPriceModel,
    NaverRealPriceSummaryModel,
    NaverRealPriceSummaryTradeModel,
)
from jibsa.providers.naver.service.common.constants import (
    MARKET_PRICE_PROVIDER_NAMES,
    TRADE_NAME_BY_CODE,
)
from jibsa.providers.naver.service.common.price import market_price_fields
from jibsa.providers.naver.service.common.response import (
    result_or_empty,
    result_or_none,
)
from jibsa.providers.naver.service.complex.constants import (
    PRICE_PER_PYEONG_COMPLEX_TYPES,
    PRICE_PER_PYEONG_LEVEL_LABELS,
    PRICE_PER_PYEONG_TRADE_TYPES,
    REAL_PRICE_RECENT_MONTHS,
    REAL_PRICE_SUMMARY_FALLBACK_YEARS,
    REAL_PRICE_SUMMARY_YEARS,
)
from jibsa.providers.naver.service.complex.models import (
    NaverComplexMaintenanceFee,
    NaverMarketPrice,
    NaverPricePerPyeong,
    NaverPricePerPyeongRegion,
    NaverRealPriceExtreme,
    NaverRealPriceRange,
    NaverRealPriceSummary,
    NaverRealPriceTradeSummary,
)

from typing import (
    Any,
)


def _real_price_extreme(trade: NaverRealPriceSummaryTradeModel | None, jeonse: bool) -> NaverRealPriceExtreme | None:
    if trade is None:
        return None
    # 전세는 보증금을 deposit_manwon 에, 매매는 매매가를 price_manwon 에 담는다 (넘기지 않은 쪽은 키가 없다)
    amount = {'deposit_manwon': won_to_manwon(trade.deposit)} if jeonse else {'price_manwon': won_to_manwon(trade.deal_price)}
    return NaverRealPriceExtreme(
        **amount,
        trade_date=read_date(trade.trade_date, '최저·최고 실거래 계약일'),
        floor=floor_text(trade.floor),
        deal_type=trade.trade_category or None,
        cancelled=trade.is_delete,
    )


def _real_price_trade_summary(summary: NaverRealPriceSummaryModel | None, jeonse: bool) -> NaverRealPriceTradeSummary | None:
    """거래가 없으면 서버가 빈 객체를 줘 None 이다."""
    if summary is None or (summary.avg_price is None and summary.min_price is None and summary.max_price is None):
        return None
    lowest = _real_price_extreme(summary.min_price, jeonse)
    highest = _real_price_extreme(summary.max_price, jeonse)
    return NaverRealPriceTradeSummary(
        average_manwon=won_to_manwon(summary.avg_price),
        # 두 거래를 모두 모르면 범위가 없어 null
        trade_range=None if lowest is None and highest is None else NaverRealPriceRange(lowest=lowest, highest=highest),
    )


def _price_per_pyeong(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    real_estate_type: str | None,
    notes: list[str],
) -> dict[str, NaverPricePerPyeong | None] | None:
    """평형의 매매·전세 평당 호가와 시·구·동 평균 (거래 유형마다 1회, 2회 호출).

    단지 유형을 모르면(None) 묻지 않고 None (모름). 서버가 빈 글자로 줘도 부르는 쪽이 None 으로 바꿔 넘긴다. 단지 유형이
    `PRICE_PER_PYEONG_COMPLEX_TYPES` 가 아니면(빌라 등, 해당 없음) 부르는 쪽(`pyeong_details`)이 이 함수를 부르지 않고 키를 둔다.
    거래 유형마다 조회가 실패하면 그 값만 None(모름)이고, 네이버가 평당가를 주지 않으면(`pricePerPyeong` 이 없거나 0, 성공인데 `result` 가
    null) 그 거래 유형의 키를 뺀다. 조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다.
    """
    if real_estate_type is None:
        return None
    prices: dict[str, NaverPricePerPyeong | None] = {}
    for key, trade_type in PRICE_PER_PYEONG_TRADE_TYPES.items():
        # 성공인데 result 가 null 이면 빈 객체(월세처럼 평당가를 주지 않음)와 같게 읽어 그 거래 유형의 키를 뺀다. 조회 실패만 None(모름)이다
        result = result_or_empty(lambda: client.run_request_complex_pyeong_price_pyeong_type_v1(
            NaverComplexPyeongPricePyeongTypeV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type,
            )
        ), NaverComplexPyeongPriceModel, notes=notes, what=f'{TRADE_NAME_BY_CODE[trade_type]} 평당 호가',
            unknown=f'모름(null)으로 낸 칸: asking_price_per_pyeong.{key}')
        if result is None:
            # 조회 실패(모름)다. 평당가가 없는 것(키 삭제)과 섞지 않는다
            prices[key] = None
        elif result.price_per_pyeong:
            # 서버 목록은 큰 단위부터(서울시·송파구·가락동)라 웹 막대 순서(동·구·시)로 뒤집는다. 목록을 주지 않으면(null)
            # 평당가는 그대로 내고 지역·기준일만 모름(None)이다
            regions = None if result.legal_division_price_per_pyeong_list is None else list(reversed(result.legal_division_price_per_pyeong_list))
            texts = [region.first_day_of_week for region in regions or []]
            with holding_unread_dates() as held:
                days = [read_date(text, '평당 호가 기준일') for text in texts]
            # 날짜가 있는데 못 읽은 지역이 있으면 가장 늦은 날을 알 수 없어 기준일을 모름으로 둔다. 지역 항목에는 날짜 칸이 없고
            # null 이 되는 칸은 거래마다 기준일 하나라 처음 못 읽은 글자 하나만 [참고] 로 알린다
            unreadable = any(day is None and normalize_date(text) is not None for text, day in zip(texts, days))
            if unreadable:
                keep_unread_dates(held[:1])
            readable = [day for day in days if day]
            prices[key] = NaverPricePerPyeong(
                price_per_pyeong_manwon=won_to_manwon(result.price_per_pyeong),
                base_date=None if unreadable or not readable else max(readable),
                regions=None if regions is None else [
                    NaverPricePerPyeongRegion(
                        name=region.legal_division_name,
                        level=None if not region.legal_division_level_type else PRICE_PER_PYEONG_LEVEL_LABELS.get(region.legal_division_level_type, region.legal_division_level_type),
                        # 평당가 0 은 없음으로 본다 (시세 평균·범위와 같은 규칙)
                        price_per_pyeong_manwon=won_to_manwon(region.price_per_pyeong) if region.price_per_pyeong else None,
                    )
                    for region in regions
                ],
            )
    return prices


def pyeong_details(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    real_estate_type: str | None,
    today: date,
    notes: list[str],
) -> dict[str, Any]:
    """평형의 관리비·최신 시세·최근 3년(비면 5년) 매매/전세 실거래 요약과 3개월 평균·평당가.

    요청은 관리비 1 + 시세 1(단지 유형이 있을 때) + 매매·전세 실거래 각 1~2 + 평당가 매매·전세 각 1(단지 유형이 `PRICE_PER_PYEONG_COMPLEX_TYPES` 일 때)
    = 최대 8회, 단지 유형이 없으면 3~5회다. 조회가 실패하면 그 값만 None. 단지 유형이 `PRICE_PER_PYEONG_COMPLEX_TYPES` 가 아닌 값이면
    (빌라 등) 평당가는 해당 없음이라 `asking_price_per_pyeong` 키를 이 결과에 넣지 않고, 단지 유형을 모르면 요청 없이 `asking_price_per_pyeong` 이 None(모름)이다.
    조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다 (같은 안내는 한 번만).

    Args:
        real_estate_type: 단지 유형 코드. 모르면 None. 서버가 빈 글자로 줘도 None 으로 넘긴다 (시세와 평당가 두 판정이 같은 값을 보게
            호출부 `get_complex` 가 `complex_.type or None` 으로 바꾼다).
    """
    fee = result_or_none(lambda: client.run_request_complex_maintenance_fee_v1(
        NaverComplexMaintenanceFeeV1RequestParameterModel(complex_number=complex_number, pyeong_type_number=pyeong_number)
    ), notes=notes, what='평형 관리비', unknown='모름(null)으로 낸 칸: pyeong_manage_cost')
    # 단지 유형은 늘 온다 (아파트·오피스텔·빌라 6곳). 시세가 없으면 서버가 [] 를 줘 그대로 [] 이고,
    # None 은 조회 실패(모름)일 때뿐이다 (2026-10-09 확인)
    market = None
    if real_estate_type is not None:
        market = result_or_none(lambda: client.run_request_complex_market_price_recent_v1(
            NaverComplexMarketPriceRecentV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, real_estate_type=real_estate_type,
            )
        ), notes=notes, what='시세', unknown='모름(null)으로 낸 칸: estimated_prices')
    since = years_ago(today, REAL_PRICE_SUMMARY_YEARS)

    def real_price_summary(trade_type: str, start_date: str, *, average_3m: bool = False) -> NaverRealPriceSummaryModel | None:
        # 3년·5년 요약 조회가 실패하면 요약 칸 전체가, 3개월 평균 조회가 실패하면 그 평균 칸만 모름이다
        key = 'sale' if trade_type == 'A1' else 'jeonse'
        column = f'trade_summary.{key}' + ('.recent_3m_average_manwon' if average_3m else '')
        return result_or_none(lambda: client.run_request_complex_pyeong_real_price_summary_v1(
            NaverComplexPyeongRealPriceSummaryV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type, start_date=start_date,
            )
        ), notes=notes, what=f'{TRADE_NAME_BY_CODE[trade_type]} 실거래 요약', unknown=f'모름(null)으로 낸 칸: {column}')

    def trade_summary(trade_type: str, jeonse: bool) -> NaverRealPriceTradeSummary | None:
        raw = real_price_summary(trade_type, since)
        if raw is None:
            # 조회 실패(모름)다. 빈 것으로 보고 5년으로 다시 부르지 않는다
            return None
        summary = _real_price_trade_summary(raw, jeonse)
        if summary is None:
            # 웹 단지 화면은 거래 유형마다 3년 요약이 비면 5년으로 한 번 더 부른다
            fallback_since = years_ago(today, REAL_PRICE_SUMMARY_FALLBACK_YEARS)
            summary = _real_price_trade_summary(real_price_summary(trade_type, fallback_since), jeonse)
            if summary is None:
                return None
            summary.start_date = fallback_since
            # 3개월 구간은 3년 구간 안이라 3년이 비었으면 3개월도 비어 요청하지 않는다
            return summary
        # 3개월 안 거래가 없으면 서버가 빈 객체를 줘 평균이 없다
        recent = real_price_summary(trade_type, months_ago(today, REAL_PRICE_RECENT_MONTHS), average_3m=True)
        if recent is not None and recent.avg_price:
            summary.recent_3m_average_manwon = won_to_manwon(recent.avg_price)
        return summary

    sale_summary = trade_summary('A1', jeonse=False)
    jeonse_summary = trade_summary('B1', jeonse=True)
    maintenance = None
    if fee is not None and fee.month_average_fee is not None:
        maintenance = NaverComplexMaintenanceFee(
            latest_month=read_month(fee.year_month, '관리비 최근 달'),
            latest_manage_cost_manwon=won_to_manwon(fee.year_month_fee),
            manage_cost_manwon=won_to_manwon(fee.month_average_fee),
            summer_manage_cost_manwon=won_to_manwon(fee.summer_average_fee),
            winter_manage_cost_manwon=won_to_manwon(fee.winter_average_fee),
        )
    details: dict[str, Any] = {
        'pyeong_manage_cost': maintenance,
        # 함께 오는 중개사 이름·전화(realtors)는 옮기지 않는다
        'estimated_prices': None if market is None else [
            NaverMarketPrice(
                provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
                base_date=read_date(item.base_date, '추정 시세 기준일'),
                **market_price_fields(
                    item.deal_average_price,
                    item.deal_price_range,
                    item.lease_average_price,
                    item.deposit_price_range,
                    item.lease_per_deal_rate,
                ),
            )
            for item in market
        ],
        'trade_summary': NaverRealPriceSummary(
            start_date=since,
            sale=sale_summary,
            jeonse=jeonse_summary,
        ),
    }
    # 평당가를 주지 않는 단지 유형(빌라 등)은 해당 없음이라 키를 두지 않는다. 단지 유형을 모르면 칸은 있는 것이라 null(모름)이다
    if real_estate_type is None or real_estate_type in PRICE_PER_PYEONG_COMPLEX_TYPES:
        details['asking_price_per_pyeong'] = _price_per_pyeong(client, complex_number, pyeong_number, real_estate_type, notes)
    return details
