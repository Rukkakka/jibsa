"""네이버 호가·시세 금액 변환 (원 → 만원 범위), 단지 행 칸, 한국 시간 오늘."""

from datetime import (
    date,
    datetime,
)

from jibsa.core.listing import (
    KST,
    AmountRange,
    AmountSet,
    read_date,
    won_to_manwon,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverComplexArticleCountModel,
    NaverComplexArticlePriceModel,
    NaverPriceRangeModel,
    NaverRedevelopmentAreaCountModel,
)
from jibsa.providers.naver.service.common.constants import PROPERTY_NAME_BY_CODE
from jibsa.providers.naver.service.common.models import NaverMarketBand

from typing import (
    Any,
    Literal,
)


def won_to_manwon_range(low: float | None, high: float | None) -> list[float | None] | None:
    """원 단위 범위(호가·시세)를 만원으로. 둘 다 없으면 None.

    그 거래 매물이 없으면 호가는 0 이 아니라 null 로 온다 (더힐 725113 전세 0건: rentMinPrice·rentMaxPrice null,
    2026-10-11). 0 도 없음으로 보는 것은 0원 범위가 뜻이 없어서다.
    """
    if not low and not high:
        return None
    return [won_to_manwon(low), won_to_manwon(high)]


def amount_range(
    field: Literal['price_manwon', 'deposit_manwon'],
    low: float | None,
    high: float | None,
) -> AmountRange | None:
    """원 단위 호가 범위를 `field` 금액의 만원 범위로 (`won_to_manwon_range` 가 None 이면 그 거래 매물이 없어 None)."""
    values = won_to_manwon_range(low, high)
    if values is None:
        return None
    return AmountRange(lowest=AmountSet(**{field: values[0]}), highest=AmountSet(**{field: values[1]}))


def _rent_amount(deposit: int | None, rent: int | None) -> AmountSet:
    """한 짝의 보증금·월세(원)를 만원 짝으로. 월세만 0 이면 월세만 null, 보증금과 월세가 모두 0(또는 없음)이면 두 값 모두 null."""
    if not deposit and not rent:
        return AmountSet(deposit_manwon=None, rent_manwon=None)
    return AmountSet(deposit_manwon=won_to_manwon(deposit), rent_manwon=won_to_manwon(rent or None))


def rent_asking_range(
    price: NaverComplexArticlePriceModel | None,
    kind: Literal['monthly', 'short'],
) -> AmountRange | None:
    """단지 호가 범위(`NaverComplexArticlePriceModel`)의 월세·단기임대 짝을 만원으로 묶는다.

    웹 호가 범위가 '보증금min/월세min ~ 보증금max/월세max' 로 그리는 것과 같은 짝이다. 보증금이 낮은 매물이 월세는
    높을 수 있어 월세 lowest 가 highest 보다 클 수 있다. 그 종류의 네 값이 모두 없거나 0 이면 None 이다
    (단기임대 매물이 없으면 단기 키는 오지 않는다). 그 밖에 한 짝의 월세만 0 이면 서버가 비운 값이라 그 월세만 null 이고,
    한 짝의 보증금과 월세가 모두 0 이면 그 짝은 비어 있어 두 값 모두 null 이다. 월세가 있는 짝의 보증금 0 은 그대로 0 으로 낸다.

    Args:
        kind: 'monthly' 월세, 'short' 단기임대.
    """
    if price is None:
        return None
    if kind == 'monthly':
        values = (
            price.rent_monthly_lease_min_price, price.rent_monthly_min_price,
            price.rent_monthly_lease_max_price, price.rent_monthly_max_price,
        )
    else:
        values = (
            price.rent_short_lease_min_price, price.rent_short_min_price,
            price.rent_short_lease_max_price, price.rent_short_max_price,
        )
    # 월세 0원 매물은 없어 네 값이 모두 0 이면 서버가 0 으로 비운 것이라 그 거래 키가 없고, 한 짝의 월세만 0 이어도 비운 값이라
    # 그 월세만 null(모름)이다. 한 짝의 보증금과 월세가 모두 0 이면 그 짝이 비어 있어 두 값 모두 null 이다. 월세가 있는 짝의
    # 보증금 0 은 실제로 있을 수 있어 그대로 0 으로 낸다 (`won_to_manwon_range` 도 0 을 시세 없음으로 본다)
    if not any(values):
        return None
    low_deposit, low_rent, high_deposit, high_rent = values
    return AmountRange(
        lowest=_rent_amount(low_deposit, low_rent),
        highest=_rent_amount(high_deposit, high_rent),
    )


def asking_ranges(prices: NaverComplexArticlePriceModel | None) -> dict[str, AmountRange] | None:
    """단지의 거래 유형별 호가 범위 (`asking_ranges`). 키 순서는 sale·jeonse·wolse·short_term 이다.

    `prices` 가 없으면(서버가 호가를 주지 않음) None(모름)이고, 그 거래 매물이 없으면(값이 모두 없거나 0) 그 거래 키를 뺀다.
    """
    if prices is None:
        return None
    ranges: dict[str, AmountRange | None] = {
        'sale': amount_range('price_manwon', prices.deal_min_price, prices.deal_max_price),
        'jeonse': amount_range('deposit_manwon', prices.rent_min_price, prices.rent_max_price),
        'wolse': rent_asking_range(prices, 'monthly'),
        'short_term': rent_asking_range(prices, 'short'),
    }
    return {name: value for name, value in ranges.items() if value is not None}


def trade_article_counts(counts: NaverComplexArticleCountModel | NaverRedevelopmentAreaCountModel) -> dict[str, int]:
    """거래 유형별 매물 수 (단지·단지 목록·재개발 구역 목록·재개발 상세의 `listing_counts`)."""
    return {
        'sale': counts.deal_count,
        'jeonse': counts.lease_deposit_count,
        'wolse': counts.lease_monthly_count,
        'short_term': counts.lease_short_term,
    }


def complex_row_fields(
    *,
    type_code: str | None,
    households: int | None,
    dong_count: int | None,
    use_approval_date: str | None,
    counts: NaverComplexArticleCountModel | None,
    prices: NaverComplexArticlePriceModel | None,
) -> dict[str, Any]:
    """단지 한 곳의 공통 칸을 만든다: 단지 유형·세대수·동 수·사용승인일·거래 유형별 매물 수·거래 유형별 호가 범위.

    학교 배정 단지(`school`)·지역 단지 목록(`search complexes`)·단지 요약(`complex`)이 같은 값을 같은 식으로 내도록 한 곳에 둔다.
    호출부는 각 모델 생성자에 `**` 로 풀어 넣는다 (각 모델의 필드 순서와 `address`·`distance_km`·`url`·`assigned_dongs` 같은 자기 칸은
    호출부가 정한다). `counts`·`prices` 가 없으면(서버가 주지 않음) 그 칸은 `None`(모름)이다. 단지 요약의 두 값은 응답 모델이 빈 모델로 채워
    `None` 갈래에 닿지 않는다.

    Args:
        type_code: 단지 유형 코드. 표에 없는 코드는 코드 그대로 내고, 빈 글자는 모름(None)이다.
        dong_count: 동 수. 단지 목록 항목은 `buildingCount`, 단지 정보는 `dongCount` 라 호출부가 맞는 쪽을 넘긴다.
        use_approval_date: 사용승인일 (YYYYMMDD).
    """
    return {
        # 빈 글자는 단지 유형을 모르는 것이라 None 이다 (`complex` 의 시세·평당가 판정이 빈 글자를 모름으로 읽는 것과 같다)
        'complex_type': PROPERTY_NAME_BY_CODE.get(type_code or '', type_code or None),
        'household_count': households,
        'dong_count': dong_count,
        'approved_date': read_date(use_approval_date, '사용승인일'),
        'listing_counts': trade_article_counts(counts) if counts is not None else None,
        'asking_ranges': asking_ranges(prices),
    }


def kst_today() -> date:
    """한국 시간 기준 오늘. 실거래·시세 기간은 한국 날짜라 실행하는 컴퓨터의 시간대와 상관없이 맞춘다.

    `date.today()` 는 컴퓨터 시간대를 따라 GMT-12 에서는 하루 전 날짜가 됐다 (시세 since 2025-10-09, 한국 기준 2025-10-10, 2026-10-10).
    """
    return datetime.now(KST).date()


def market_band(average: float | None, price_range: list[float | None] | None) -> NaverMarketBand | None:
    """시세 평균(만원)과 [하한, 상한] 목록(`manwon_range`)을 한 거래 유형의 시세로. 목록이 None 이면 하위·상위 둘 다 null.

    평균·하위·상위를 모두 모르면 None(거래 값 null)이고, 하나라도 있으면 모르는 칸만 null 인 객체다.
    """
    low, high = price_range if price_range is not None else (None, None)
    if average is None and low is None and high is None:
        return None
    return NaverMarketBand(average_manwon=average, low_manwon=low, high_manwon=high)


def manwon_range(price_range: NaverPriceRangeModel | None, scale: bool = True) -> list[float | None] | None:
    """시세 범위(하한·상한)를 만원으로 (`won_to_manwon_range`). `scale` 이 False 면 비율(전세가율 %, 37~41)이라 그대로 둔다.

    둘 다 0·None 이면 없음이다 (기관이 0 을 주면 시세 없음이라 전세가율 0% 를 내지 않는다, 시세 평균·범위와 같은 규칙).
    """
    if price_range is None:
        return None
    if scale:
        return won_to_manwon_range(price_range.floor, price_range.ceiling)
    if not price_range.floor and not price_range.ceiling:
        return None
    return [price_range.floor, price_range.ceiling]


def market_price_fields(
    deal_average_won: int | float | None,
    deal_range: NaverPriceRangeModel | None,
    deposit_average_won: int | float | None,
    deposit_range: NaverPriceRangeModel | None,
    lease_per_deal_rate: NaverPriceRangeModel | None,
) -> dict[str, Any]:
    """기관 시세 한 점의 매매·전세 띠와 전세가율 하한·상한 (`NaverMarketPrice`·`NaverMarketPricePoint` 의 같은 칸).

    평균 0 은 범위(`manwon_range`)처럼 없음(None)으로 본다 (네이버 웹도 0 이면 시세를 그리지 않는다).
    """
    ratio = manwon_range(lease_per_deal_rate, scale=False)
    return {
        'sale': market_band(won_to_manwon(deal_average_won) or None, manwon_range(deal_range)),
        'jeonse': market_band(won_to_manwon(deposit_average_won) or None, manwon_range(deposit_range)),
        'jeonse_ratio_low_percent': ratio[0] if ratio is not None else None,
        'jeonse_ratio_high_percent': ratio[1] if ratio is not None else None,
    }
