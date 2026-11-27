"""`station.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    AmountSet,
    Result,
)

from typing import (
    Annotated,
)


class DabangStationPrice(BaseModel):
    """역 둘레 평균 매물가 한 칸 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    property_type: Annotated[
        str,
        Field(description='매물 유형 (빌라, 오피스텔, 아파트)')
    ]
    room_type: Annotated[
        str,
        Field(description='방 개수 (원룸, 투룸)')
    ]
    asking_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 평균 매물가 (만원). 키는 'jeonse'(평균 전세금 deposit_manwon)·'wolse'(평균 보증금 deposit_manwon, "
            "평균 월세 rent_manwon) 늘 두 개다. 다방이 그 거래 평균을 주지 않으면(웹은 '-') 그 거래가 null(모름)이다. 월세는 보증금·월세 중 하나만 모르면 그 칸만 null 이다. "
            '다방이 매물 수를 주지 않아 그 거래 매물이 없는 것인지는 가를 수 없다'
        ))
    ]


class DabangStationPrices(Result):
    """역 둘레 평균 매물가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station_name: Annotated[
        str,
        Field(description='역 이름')
    ]
    radius_m: Annotated[
        int | None,
        Field(description='다방 역 반경 (m). 이 안 매물의 평균이다')
    ] = None
    basis: Annotated[
        str,
        Field(description='무엇의 평균인지')
    ]
    prices: Annotated[
        list[DabangStationPrice],
        Field(description='건물 유형 × 방 개수별 평균')
    ]
