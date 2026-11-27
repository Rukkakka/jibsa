"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

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


class NaverNearbyRail(BaseModel):
    """매물 근처에 생길 지하철역 한 곳. 좌표·ID 는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="역 이름 (서버 글자 그대로, 개통 예정 연도가 붙는다: '탄천역(2027년예정)')")
    ] = None
    line: Annotated[
        str | None,
        Field(description="노선 이름 (서버 글자 그대로: '위례신사선(예정)')")
    ] = None
    open_year: Annotated[
        int | None,
        Field(description='개통 예정 연도 (2027). 없거나 숫자로 읽지 못하면 null')
    ] = None
    distance_m: Annotated[
        int | float | None,
        Field(description='매물에서의 거리 (m)')
    ] = None
    walk_minutes: Annotated[
        int | float | None,
        Field(description='도보 시간 (분)')
    ] = None


class NaverNearbyArea(BaseModel):
    """매물 근처 개발 지구 한 곳. 사업 기간이 없으면 `project_period` 키를 뺀다 (웹도 그 줄을 그리지 않는다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='개발 지구 이름. 빈 글자나 없으면 null')
    ] = None
    type: Annotated[
        str | None,
        Field(description="사업 종류 ('재개발' 등, 서버 글자 그대로). 빈 글자나 없으면 null")
    ] = None
    step: Annotated[
        int | str | None,
        Field(description='사업 단계 (서버 값 그대로). 빈 글자나 없으면 null')
    ] = None
    project_period: Annotated[
        str | None,
        Field(description="사업 기간 ('2010-07-14~2027-12-31', 서버 글자 그대로). 없으면 키를 뺀다")
    ] = None

    @model_serializer(mode='wrap')
    def drop_missing_period(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.project_period is None:
            data.pop('project_period', None)
        return data


class NaverNearbyDevelopment(BaseModel):
    """매물 근처의 개발 예정 (네이버 웹 상세의 '주변 개발 예정'). 두 목록이 모두 빌 수 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rail: Annotated[
        list[NaverNearbyRail] | None,
        Field(description='근처 예정 지하철역. 없으면 [], 네이버가 이 목록만 비워(null) 주면 null(모름)')
    ] = []
    area: Annotated[
        list[NaverNearbyArea] | None,
        Field(description='근처 개발 지구. 없으면 [], 네이버가 이 목록만 비워(null) 주면 null(모름)')
    ] = []
