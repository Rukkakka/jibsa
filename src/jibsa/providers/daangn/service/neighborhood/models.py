"""생활 방식에 맞는 동네 추천의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)

from typing import Annotated


class DaangnNeighborhood(BaseModel):
    """추천 동 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int | None,
        Field(description='순위')
    ] = None
    sigungu: Annotated[
        str | None,
        Field(description='시·군·구')
    ] = None
    dong: Annotated[
        str | None,
        Field(description='행정동 (예: 역삼1동)')
    ] = None
    region_id: Annotated[
        int | None,
        Field(description='당근 동 ID (법정동)')
    ] = None
    description: Annotated[
        str | None,
        Field(description='한 줄 설명')
    ] = None


class DaangnNeighborhoodsResult(Result):
    """좋은 동네 추천 결과.

    `notes`: 기본 지역([범위], --region 을 주지 않았을 때)·동 이름 안내. CLI 가 notes 로 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    lifestyle: Annotated[str, Field(description='라이프스타일')]
    indicators: Annotated[list[str], Field(description='쓴 지표')]
    regions: Annotated[list[str], Field(description='찾은 지역. --region 을 주지 않으면 당근 웹 첫 화면처럼 서울 (전국 순위는 없다)')]
    returned: Annotated[int, Field(description='반환한 동 수')]
    neighborhoods: Annotated[list[DaangnNeighborhood], Field(description='순위 순 동')]
