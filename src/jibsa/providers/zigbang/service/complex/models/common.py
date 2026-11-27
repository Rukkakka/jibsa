"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from typing import (
    Annotated,
)


class ZigbangRelatedComplex(BaseModel):
    """직방이 단지끼리 이어 주는 단지 하나: 웹 단지 화면의 '함께 보면 좋은 단지', 직방시세 그래프 '단지 비교하기' 의 후보 ('단지 선택' 창)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다). 직방이 ID 를 주지 않으면 모름(null)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ]
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ]
