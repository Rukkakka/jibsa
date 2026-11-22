"""요청 모델: 지역 단지 랭킹 (region-ranking)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.zigbang.api.request.common import ZigbangAptTranType

from typing import (
    Annotated,
    Literal,
)


ZigbangDanjiRankingViewPeriod = Literal['this_week', 'last_week', 'this_month', 'last_month', 'this_year', 'last_year']
ZigbangDanjiRankingSortType = Literal[
    'volume_desc', 'decrease_rate_desc', 'increase_rate_desc', 'price_desc', 'unit_price_desc', 'view_count_desc', 'charter_rate_desc',
]


class ZigbangLocalsDanjiRankingRequestParameterModel(RequestModel):
    """`GET /apt/locals/danji/ranking` 쿼리. 지역 안 단지 랭킹 (웹 지역정보 화면의 랭킹).

    웹 요청의 쿼리 순서 `page`·`limit`·`bjdCode`·`viewPeriod`·`sortType`·`tranType` 과 같게 선언한다. `limit` 은 11 이상이면
    서버가 400 ('limit must not be greater than 10'), 200위를 넘는 쪽(page 21 은 limit 10 에서)은 400 ('최대 200개까지 조회 가능합니다.') 이다
    (2026-11-22 실측).
    """

    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호 (1부터)')
    ]
    limit: Annotated[
        int,
        Field(ge=1, le=10, description='쪽 크기. 서버가 10 을 넘으면 400 으로 거절한다')
    ]
    bjd_code: Annotated[
        str,
        Field(pattern=r'^\d{2}(\d{3}(\d{3})?)?$', description='지역 코드 (동 8자리·구 5자리·시도 2자리)', alias='bjdCode')
    ]
    view_period: Annotated[
        ZigbangDanjiRankingViewPeriod,
        Field(description='기간 (이번 주·지난주·이번 달·지난달·올해·작년)', alias='viewPeriod')
    ]
    sort_type: Annotated[
        ZigbangDanjiRankingSortType,
        Field(description='순위 기준 (거래량·하락률·상승률·가격·평당가·조회수·전세가율 높은 순)', alias='sortType')
    ]
    tran_type: Annotated[
        ZigbangAptTranType,
        Field(description='거래 유형 (trade 매매, charter 전세, rental 월세)', alias='tranType')
    ]
