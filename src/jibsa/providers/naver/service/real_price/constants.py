"""네이버 실거래가의 상수: 쪽 크기·요청 상한, 빌라 주변 실거래의 지도 범위와 줌, 안내 문구."""

from jibsa.core.listing import note


# 실거래가 한 페이지 크기. 예전 엔드포인트(complex/pyeong/realPrice)와 같은 10건으로 둬 --pages 의 뜻을 유지한다
REAL_PRICE_PAGE_SIZE: int = 10


# 기간 조회에서 빌라 단지 실거래를 받는 페이지 크기와 페이지 수 상한. 빌라 단지는 거래가 적어 보통 한 페이지로 끝난다
VILLA_PERIOD_PAGE_SIZE: int = 100


MAX_VILLA_PERIOD_PAGES: int = 5


PYEONG_GROUP_TRADES_NOTE: str = note(
    '참고',
    '같은 묶음의 다른 평형 거래가 섞여 있고, 거래마다 어느 평형인지는 알려 주지 않습니다. 묶음에 든 평형은 pyeong_group.pyeong_ids 입니다',
)


# 평당 실거래가의 시작일은 오늘의 몇 년 전인지 (웹 `VILLA_TRANSACTION_PER_PYEONG_YEAR_RANGE`, 청크 26e0315e74_3kmdmwb6eaqal)
PRICE_PER_PYEONG_YEARS: int = 5


# 웹 주변 실거래 칸이 단지 좌표를 가운데로 잡는 작은 지도(388×200px, zoom 16)의 범위. 이 축척이면 572549(위도 37.47)에서
# 2026-11-19 실측한 위도 폭 0.001703°·경도 폭 0.0041628° 와 같다. 위도 폭은 메르카토르라 위도마다 다르다
# (웹이 이 크기를 바꾸면 기본값이 달라질 수 있다). `--around-km` 을 주면 `box_around` 사각형을 쓴다
AROUND_WEB_MAP_WIDTH_PX: int = 388


AROUND_WEB_MAP_HEIGHT_PX: int = 200


AROUND_WEB_DEGREES_PER_PX: float = 360 / (256 * 2 ** 17)


# 주변 실거래를 받는 줌. 웹이 16 을 보낸다. 14 는 같은 범위에도 0건이고 빼면 400 이다 (2026-11-19 실측)
AROUND_ZOOM: int = 16


# 네이버가 범위 안 주변 실거래를 이 수까지만 준다. 이만큼 받았으면 더 있을 수 있다
AROUND_TRADES_LIMIT: int = 10


NEARBY_TRADES_LIMIT_NOTE: str = note(
    '일부',
    f'네이버는 범위 안 거래를 {AROUND_TRADES_LIMIT}건까지만 줍니다 (고르는 기준은 확인하지 못했습니다). '
    '범위(--around-km)를 바꾸면 보이는 거래가 달라질 수 있습니다',
)
