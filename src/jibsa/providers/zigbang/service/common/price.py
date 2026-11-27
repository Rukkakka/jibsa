"""직방 시세·가격 범위 묶기: 직방시세 매매·전세 값을 묶고, 매매가 범위를 만든다."""

from jibsa.core.listing import (
    AmountRange,
    AmountSet,
)
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice


def estimated_prices_of(
    sale_price_manwon: float | None,
    sale_price_per_pyeong_manwon: float | None,
    jeonse_price_manwon: float | None,
    jeonse_price_per_pyeong_manwon: float | None,
) -> dict[str, ZigbangEstimatedPrice | None]:
    """직방시세® 매매·전세 값을 estimated_prices 로 묶는다. 늘 'sale'·'jeonse' 두 키이고, 거래의 안 값이 모두 없으면 그 거래가 모름(null), 일부만 없으면 그 칸만 null 이다."""
    return {
        'sale': None if sale_price_manwon is None and sale_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            price_manwon=sale_price_manwon, price_per_pyeong_manwon=sale_price_per_pyeong_manwon,
        ),
        'jeonse': None if jeonse_price_manwon is None and jeonse_price_per_pyeong_manwon is None else ZigbangEstimatedPrice(
            deposit_manwon=jeonse_price_manwon, price_per_pyeong_manwon=jeonse_price_per_pyeong_manwon,
        ),
    }


def sale_price_range(lowest_manwon: float | None, highest_manwon: float | None) -> AmountRange | None:
    """매매가 범위 (직방시세 estimated_ranges 의 'sale', 평형 추이 trade_range). 두 끝이 모두 없으면 모름(None)이고, 한 끝만 없으면 그 price_manwon 만 null 이다."""
    if lowest_manwon is None and highest_manwon is None:
        return None
    return AmountRange(lowest=AmountSet(price_manwon=lowest_manwon), highest=AmountSet(price_manwon=highest_manwon))
