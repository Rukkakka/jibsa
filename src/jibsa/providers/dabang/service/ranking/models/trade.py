"""`trade.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import Result

from typing import (
    Annotated,
)


class DabangTradeRanking(BaseModel):
    """거래 순위 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 수 (국토교통부 신고)')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description='입주 N년차 (사용승인한 해를 1년차로 센다)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None


class DabangTradeRankings(Result):
    """전국 거래 순위.

    `notes`: 빈 순위 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_type: Annotated[
        str,
        Field(description='아파트 / 오피스텔')
    ]
    trade_type: Annotated[
        str,
        Field(description='매매 / 전세')
    ]
    period: Annotated[
        str,
        Field(description='기간')
    ]
    base_period: Annotated[
        str | None,
        Field(description="다방이 센 기간 ('26.10.19 ~ 26.10.25')")
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수')
    ]
    rankings: Annotated[
        list[DabangTradeRanking],
        Field(description='순위')
    ]
