"""`address.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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
)


class DaangnAddress(BaseModel):
    """웹 검색창 주소 모드(`searchAddress`)로 찾은 도로명 주소와 `unitByAddress` 로 받은 그 좌표."""

    model_config = ConfigDict(
        extra='forbid',
    )

    road_address: Annotated[
        str,
        Field(description="도로명 주소 (예: '서울특별시 강남구 테헤란로 152 (역삼동)')")
    ]
    address: Annotated[
        str | None,
        Field(description="지번 주소 (건물 이름까지, 예: '서울특별시 강남구 역삼동 737 강남파이낸스센터')")
    ] = None
    building_name: Annotated[
        str | None,
        Field(description='그 주소의 당근 단지·건물 이름. 당근이 모르면 null')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='그 주소가 당근 단지면 단지 ID (search listings --complex·complex 에 넘긴다). 단지가 아니면 키가 없다')
    ] = None
    lat: Annotated[
        float,
        Field(description='주소 위도')
    ]
    lng: Annotated[
        float,
        Field(description='주소 경도')
    ]

    @property
    def label(self) -> str:
        """안내에 쓰는 주소 이름 (`'서울특별시 강남구 테헤란로 152 (역삼동)' (강남파이낸스센터)`). 당근이 모르는 건물이면 이름을 붙이지 않는다."""
        return f"'{self.road_address}'" + (f' ({self.building_name})' if self.building_name else '')

    @model_serializer(mode='wrap')
    def drop_missing_complex(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_id is None:
            data.pop('complex_id', None)
        return data
