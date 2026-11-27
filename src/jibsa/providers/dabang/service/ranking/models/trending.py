"""`trending.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import Result

from typing import (
    Annotated,
    Any,
    Literal,
)


class DabangWatchRanking(BaseModel):
    """조회 순위 한 칸. 단지면 단지 필드, 동이면 동 필드가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    unit: Annotated[
        Literal['단지', '동'],
        Field(exclude=True, description='단지 / 동 (다른 쪽 필드는 해당 없어 키를 뺀다)')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 순위)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름 또는 동 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='단지 주소 (동까지) 또는 동의 시·도')
    ] = None
    legal_division_code: Annotated[
        str | None,
        Field(description='동의 법정동코드 (동 순위, 10자리)')
    ] = None
    viewer_count: Annotated[
        int | None,
        Field(description="기간 안 조회한 사람 수 (다방 화면 'N명'. 조회 횟수가 아니다)")
    ] = None
    change: Annotated[
        str | None,
        Field(description="앞 기간 대비 ('상승 3', '하락 2', '유지', '신규')")
    ] = None

    @model_serializer(mode='wrap')
    def drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 해당하는 쪽 필드가 비면 모름(null)으로 남긴다
        data.pop('legal_division_code' if self.unit == '단지' else 'complex_id', None)
        return data


class DabangWatchRankings(Result):
    """전국 조회 순위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    unit: Annotated[
        str,
        Field(description='단지 / 동')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 / 오피스텔')
    ]
    period: Annotated[
        str,
        Field(description='기간 (방금전·어제·지난주·지난달)')
    ]
    base_period: Annotated[
        str | None,
        Field(description="다방이 센 기간 ('26.10.12 ~ 26.10.18', '26.10.25 17:09 기준')")
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수 (다방은 50곳까지 준다)')
    ]
    rankings: Annotated[
        list[DabangWatchRanking],
        Field(description='순위')
    ]
