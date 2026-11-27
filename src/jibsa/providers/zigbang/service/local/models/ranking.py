"""`ranking.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.zigbang.service.local.constants import (
    LOCAL_DONG_DESCRIPTION,
    LocalRankingPeriod,
    LocalTrade,
)
from jibsa.providers.zigbang.service.local.models.common import (
    ZigbangLocalModel,
    ZigbangLocalRegion,
)

from typing import (
    Annotated,
)


class ZigbangDanjiRank(ZigbangLocalModel):
    """단지 랭킹 한 줄. 정렬마다 오는 칸이 달라 해당하지 않는 칸은 키가 없다. 금액은 만원이다."""

    rank: Annotated[
        int | None,
        Field(description='순위 (직방 rankingNumber). 같은 값이면 같은 순위로 오고 다음 순위가 건너뛴다 (예: 1·1·1·4). 직방이 주지 않으면 null')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 건수 (건, 거래량 많은순만)')
    ]
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 하락률·상승률 정렬에는 키가 없다). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    household_count: Annotated[
        int | None,
        Field(description='총세대수 (하락률·상승률 정렬에는 키가 없다)')
    ]
    latest_trade_date: Annotated[
        str | None,
        Field(description='가장 최근 계약일 (YYYY-MM-DD, 하락률·상승률 정렬만). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래가 (만원, 매매의 하락률·상승률 정렬만)')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래의 보증금 (만원, 전세의 하락률·상승률 정렬만)')
    ]
    prev_trade_diff_manwon: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 차액 (만원, 하락률·상승률 정렬만)')
    ]
    prev_trade_diff_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, 하락률·상승률 정렬만)')
    ]
    area_type: Annotated[
        str | None,
        Field(description='가장 최근 거래의 평형 이름 (하락률·상승률 정렬만)')
    ]
    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 (만원, 시세 높은순만). 웹 설명: 단지 중 가장 시세가 높은 타입을 기준으로 한 값이라 공급 면적별 차이가 있다')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 기준 평당가 (만원/3.3㎡, 평당가 높은순만)')
    ]
    view_count: Annotated[
        int | None,
        Field(description='기간 안 조회수 (인기 단지순만)')
    ]
    jeonse_ratio_percent: Annotated[
        int | float | None,
        Field(description='직방 매매 시세 대비 전세 시세 비율 (%, 전세가율 높은순만)')
    ]
    gap_manwon: Annotated[
        int | float | None,
        Field(description='매매 시세와 전세 시세의 차이 (만원, 전세가율 높은순만)')
    ]


class ZigbangRegionRankingResult(ZigbangLocalModel, Result):
    """동·구의 단지 랭킹 (직방 웹 지역 화면 '단지랭킹', 웹처럼 100위까지).

    `notes`: 일부만 받았다는 안내·100위까지만 본다는 안내·쪽을 받지 못했다는 안내. CLI 가 결과 위에 붙인다
    """

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 거래량 많은순)')
    ]
    period: Annotated[
        LocalRankingPeriod,
        Field(description='기간. 시세 높은순·평당가 높은순·전세가율 높은순은 기간과 상관없이 시세 기준일의 순위다')
    ]
    start_date: Annotated[
        str | None,
        Field(description='집계 시작일 (YYYY-MM-DD, 한국 날짜. 서버는 UTC 로 주지만 한국 날짜로 바꾼다). 거래량·하락률·상승률·인기 정렬만 있고 시세·평당가·전세가율에는 키가 없다. 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    end_date: Annotated[
        str | None,
        Field(description='집계 끝 날짜 (YYYY-MM-DD, 한국 날짜). 거래량·하락률·상승률은 집계 기간의 끝, 시세·평당가·전세가율은 직방 시세 기준일, 인기는 조회 집계의 끝이다. 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    updated_at: Annotated[
        str | None,
        Field(description='갱신 시각 (YYYY-MM-DD HH:MM, 한국 시간). 거래량·하락률·상승률 정렬만 있고 시세·평당가·전세가율·인기는 서버가 주지 않아 키가 없다. 읽지 못하면 null')
    ]
    total: Annotated[
        int | None,
        Field(description='직방이 준 순위 수 (count). 서버가 200 에서 막아 실제 단지가 더 많을 수 있고 웹은 100위까지만 보여 준다. 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='웹이 보여 주는 100위 안에 --limit 을 늘리면 더 받을 수 있는 단지가 남았는지 (직방이 목록을 순위 수보다 일찍 끝내면 false. 이어 받기는 없다)')
    ]
    rankings: Annotated[
        list[ZigbangDanjiRank],
        Field(description='단지 랭킹 (직방 순위 순서 그대로)')
    ]
