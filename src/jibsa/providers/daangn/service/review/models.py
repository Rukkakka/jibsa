"""동네 후기 요약의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.region.models import DaangnRealsaleRegion

from typing import (
    Annotated,
    Any,
)


class DaangnReviewComplex(BaseModel):
    """거주 후기가 많은 단지."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘기면 그 단지의 후기 수와 단지 페이지가 나온다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름. 당근이 주지 않으면 null')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형. 당근이 주지 않으면 null. 동으로 찾으면 동 후기 페이지가 유형을 주지 않아 늘 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수')
    ] = None


class DaangnReviewDong(BaseModel):
    """거주 후기가 있는 동 (구의 후기 페이지)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str,
        Field(description='동 이름 (예: 역삼동)')
    ]
    region_id: Annotated[
        int,
        Field(description='동의 당근 지역 ID')
    ]
    review_count: Annotated[
        int | None,
        Field(description='그 동의 거주 후기 수')
    ] = None
    url: Annotated[
        str,
        Field(description='그 동의 당근 동네 후기 페이지')
    ]


class DaangnReviewBuilding(BaseModel):
    """거주 후기가 있는 건물. 단지가 아닌 건물(빌라·상가주택 등)도 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    building_id: Annotated[
        str,
        Field(description='당근 건물 ID')
    ]
    name: Annotated[
        str | None,
        Field(description='건물 이름. 이름이 없는 건물이 많아 그때는 null (주소로 알아본다)')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소. 당근이 주지 않으면 null')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소. 당근이 주지 않으면 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='그 건물의 거주 후기 수')
    ] = None
    url: Annotated[
        str,
        Field(description='그 건물의 당근 후기 페이지 (건물 후기는 여기서 본다)')
    ]


class DaangnRegionReviews(Result):
    """동네 거주 후기 안내. 후기 본문과 당근이 만든 요약 글은 담지 않는다 (url 의 원 사이트에서 본다).

    `notes`: 후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    has_reviews: Annotated[
        bool | None,
        Field(description='동네 후기가 있는지. 당근이 후기 수를 주지 않고 후기 미리보기·후기 많은 단지·건물·동 목록도 비어 있으면 null(모름)')
    ]
    review_count: Annotated[
        int | None,
        Field(description='동네 후기 수 (당근 웹 모바일 후기 화면의 "후기 N개"와 같은 실제 수). 동·구 모두 있다. 당근이 주지 않으면 null')
    ] = None
    dongs: Annotated[
        list[DaangnReviewDong] | None,
        Field(description='구로 찾았을 때 그 구에서 거주 후기가 있는 동과 동별 후기 수 (당근 순서인 후기 많은 순, 자르지 않는다). 동으로 찾으면 키가 없다. 당근 구 후기 페이지가 없어 모르면 null')
    ] = []
    top_complexes: Annotated[
        list[DaangnReviewComplex] | None,
        Field(description='후기가 있는 단지 (후기 많은 순, --top 개까지). 구로 찾으면 그 구의 단지 (당근 구 후기 페이지가 후기 많은 단지를 20곳까지만 줘 더 있을 수 있다), 동으로 찾으면 그 동의 단지 (동 후기 페이지가 500곳까지 주고 후기 없는 단지가 뒤에 붙어, 후기 있는 단지는 대개 다 온다), 구가 없는 시(세종)의 동은 그 동의 단지 (구 후기 페이지 모양이라 20곳까지). 단지 ID 가 없는 것은 뺀다. 후기 페이지가 없어 모르면 null')
    ] = []
    top_buildings: Annotated[
        list[DaangnReviewBuilding] | None,
        Field(description='후기가 있는 건물 (후기 많은 순, --top 개까지). 구로 찾으면 그 구의 건물, 동으로 찾으면 그 동의 건물 (당근은 개수를 제한하지 않는다). 후기 페이지가 없어 모르면 null')
    ] = []
    url: Annotated[
        str,
        Field(description='당근 동네 후기 페이지 (동이면 그 동의 후기 페이지, 구가 없는 시는 동 이름을 구 자리에 둔 후기 페이지). 후기 페이지가 없으면 당근 지도 페이지')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 동별 후기 수는 구의 후기 페이지에만 있어 동으로 찾으면 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.region.level == '동':
            data.pop('dongs', None)
        return data
