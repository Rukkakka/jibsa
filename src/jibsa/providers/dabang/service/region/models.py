"""위치 찾기의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.korean import full_legal_division_code

from typing import (
    Annotated,
    Any,
    Literal,
)


class DabangScope(BaseModel):
    """순위·분양 범위: 전국, 시·도, 시·군·구, 동 (동은 단지 순위만)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    kind: Annotated[
        Literal['national', 'state', 'district', 'dong'],
        Field(description='범위 종류 (전국·시도·시군구·동)')
    ]
    name: Annotated[
        str,
        Field(description="범위 이름 ('전국', '서울특별시', '서울특별시 강남구', '서울특별시 강남구 역삼동')")
    ]
    code: Annotated[
        str | None,
        Field(description=(
            "다방 지역 코드 (시·도 2자리, 시·군·구 5자리, 동 10자리). 출력에서는 legal_division_code 로 10자리를 채워 낸다 "
            "(시·도 '11' → '1100000000'). 전국은 null"
        ))
    ] = None
    state_code: Annotated[
        str | None,
        Field(exclude=True, description='시·도 코드 (2자리, 시·도·시·군·구. 시·군·구 목록을 받은 시·도)')
    ] = None
    gid: Annotated[
        int | None,
        Field(exclude=True, description='다방 지역 번호 (전국은 없음)')
    ] = None

    @model_serializer(mode='wrap')
    def full_legal_division_code_key(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 출력은 키 이름을 법정동코드(legal_division_code)로 바꾸고 앞자리 코드를 10자리로 채운다. 요청에는 다방 코드를 그대로 쓴다
        data: dict[str, Any] = handler(self)
        return {
            ('legal_division_code' if key == 'code' else key): (full_legal_division_code(value) if key == 'code' and value else value)
            for key, value in data.items()
        }
