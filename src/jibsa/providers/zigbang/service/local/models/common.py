"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


LocalLevel = Literal['동', '구']


class ZigbangLocalRegion(BaseModel):
    """지역 화면 명령 결과의 머리: 조회한 동·구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동·구 이름. region-info 는 직방 지역 정보의 이름 (예: 성남시 분당구), 그 밖은 찾은 지역 이름. 리는 상위 읍·면으로 찾아 notes 로 알린다')
    ]
    level: Annotated[
        LocalLevel,
        Field(description="조회 단위. 시·군·구는 '구', 읍·면·동은 '동' (리는 상위 읍·면이라 '동')")
    ]
    address: Annotated[
        str | None,
        Field(description='찾은 지역의 전체 주소')
    ]
    legal_division_code: Annotated[
        str,
        Field(description='법정동코드 (10자리). 직방이 지역 화면에 쓰는 5자리(구)·8자리(동) 코드 뒤를 0 으로 채운 값이다. 리는 상위 읍·면 코드다')
    ]


class ZigbangLocalModel(BaseModel):
    """결과·줄의 기반. 해당 없는 칸은 출력에서 키를 뺀다 (`not_applicable`).

    같은 모델이 거래 유형·정렬·조회 단위마다 다른 칸을 내므로, 만들 때 뺄 칸 이름을 정해 넘긴다. 값을 모르는 칸은 키를 두고 null 이다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    not_applicable: Annotated[
        frozenset[str],
        Field(exclude=True, description='이 결과·줄에 해당하지 않아 출력에서 키를 뺄 칸 이름. 출력하지 않는다')
    ] = frozenset()

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in self.not_applicable:
            data.pop(field, None)
        return data
