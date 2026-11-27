"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from typing import (
    Annotated,
)


class DaangnComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘긴다)')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...)')
    ] = None
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='주소 (지번, 없으면 도로명)')
    ] = None
