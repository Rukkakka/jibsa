"""요청 모델: 동·지도 범위 매물 검색 (search listings)."""

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.models.request.common import (
    DaangnBoundsLocationFilterModel,
    DaangnPropertyFilterModel,
    is_empty_property_filter,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnArticleFeedInputModel(RequestModel):
    """`articleFeed` 의 `input`. 웹 지도 화면의 매물 목록처럼 좌표 범위와 `resolution` 으로 부른다.

    웹의 동 페이지(검색 엔진용 첫 화면)는 동 하나(`originalRegionId`)로 부르지만 주변 동 매물이 섞여 jibsa 는 쓰지 않는다.
    동 매물은 동 클러스터 목록(`articleByClusterId`)이다 (#215).
    """

    location_filter: Annotated[
        DaangnBoundsLocationFilterModel,
        Field(description='지도 화면의 좌표 범위', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
    resolution: Annotated[
        int | None,
        Field(ge=0, le=15, description='지도 줌을 바꾼 H3 해상도. 웹은 좌표 범위로 찾을 때만 보낸다')
    ] = None
    surface: Annotated[
        Literal['MAP'],
        Field(description='피드를 보여 주는 화면. 웹 지도 패널과 같은 MAP')
    ] = 'MAP'


class DaangnArticleFeedRequestPayloadModel(RequestModel):
    """GraphQL `articleFeed` 쿼리 변수 (`variables`)."""

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 매물 수')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnArticleFeedInputModel,
        Field(description='지역·매물 조건')
    ]


class DaangnArticlesCountInputModel(RequestModel):
    """`articlesCount` 의 `input`. `articleFeed` 와 같은 조건이고 `surface` 는 없다."""

    location_filter: Annotated[
        DaangnBoundsLocationFilterModel,
        Field(description='지도 화면의 좌표 범위', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
    resolution: Annotated[
        int | None,
        Field(ge=0, le=15, description='지도 줌을 바꾼 H3 해상도 (articleFeed 와 같다). 웹은 좌표 범위로 셀 때만 보낸다')
    ] = None


class DaangnArticlesCountRequestPayloadModel(RequestModel):
    """GraphQL `articlesCount` 쿼리 변수 (웹의 `MapFloatingControlsArticleCountQuery`, 조건에 맞는 매물 수)."""

    input: Annotated[
        DaangnArticlesCountInputModel,
        Field(description='지역·매물 조건')
    ]


class DaangnArticleByClusterIdInputModel(RequestModel):
    """`articleByClusterId` 의 `input`."""

    cluster_id: Annotated[
        str,
        Field(pattern=r'^REGION:\d+$', description="지도 지역 클러스터 ID ('REGION:<동 ID>')", alias='clusterId')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(
            description='매물 조건 (articleFeed 와 같다). 조건이 하나도 없으면 웹처럼 null 을 보낸다 (`with_null_property_filter`)',
            alias='propertyFilter',
        )
    ] = Field(default_factory=DaangnPropertyFilterModel)

    @model_serializer(mode='wrap')
    def serialize_with_null_filter(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, Any]:
        return with_null_property_filter(self.property_filter, handler(self), info)


class DaangnArticleByClusterIdRequestPayloadModel(RequestModel):
    """GraphQL `articleByClusterId` 쿼리 변수 (웹 지도의 동 클러스터 매물 목록 `ArticleListPanelPaginationQuery`).

    첫 페이지용 `ArticleListPanelQuery` 와 루트 필드·변수가 같고 `after` 를 받아 페이지 넘김 쿼리 하나만 쓴다. 그 동 매물만 준다
    (2026-11-11 실측: 역삼동 월세 100건 모두 역삼동. 동 피드 `articleFeed(originalRegionId)` 는 주변 동을 섞는다).
    """

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 매물 수')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnArticleByClusterIdInputModel,
        Field(description='클러스터·매물 조건')
    ]


class DaangnArticleClustersInputModel(RequestModel):
    """`articleClusters` 의 `input` (웹 지도의 지역 거품)."""

    cluster_type: Annotated[
        Literal['REGION'],
        Field(description='거품 종류. 웹 지도의 지역 거품은 REGION', alias='clusterType')
    ] = 'REGION'
    location_filter: Annotated[
        DaangnBoundsLocationFilterModel,
        Field(description='지도 화면의 좌표 범위', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(
            description='매물 조건 (articleFeed 와 같다). 조건이 하나도 없으면 웹처럼 null 을 보낸다 (`with_null_property_filter`)',
            alias='propertyFilter',
        )
    ] = Field(default_factory=DaangnPropertyFilterModel)
    zoom_level: Annotated[
        Literal[7, 8],
        Field(description='거품 단위. 7 은 구, 8 은 동 (웹 mapDev 의 `s`: 지역 거품을 그리는 줌 8~13 중 동 거품 줌 12 보다 낮으면 7)', alias='zoomLevel')
    ] = 8

    @model_serializer(mode='wrap')
    def serialize_with_null_filter(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, Any]:
        return with_null_property_filter(self.property_filter, handler(self), info)


class DaangnArticleClustersRequestPayloadModel(RequestModel):
    """GraphQL `articleClusters` 쿼리 변수 (웹 지도의 `MapViewRegionClustersQuery`, 지역 거품의 매물 수)."""

    input: Annotated[
        DaangnArticleClustersInputModel,
        Field(description='범위·매물 조건·거품 단위')
    ]
    include_boundaries: Annotated[
        bool,
        Field(
            description=(
                '지역 경계를 함께 받을지. 웹은 데스크톱에서만 true 다 (MapView 의 `useIsDesktop`). jibsa 는 경계를 쓰지 않아 false 다 '
                '(2026-11-12 실측: 역삼동 줌 12 범위 true 1.4MB, false 18KB)'
            ),
            alias='includeBoundaries',
        )
    ] = False


def with_null_property_filter(
    property_filter: DaangnPropertyFilterModel,
    data: dict[str, Any],
    info: SerializationInfo,
) -> dict[str, Any]:
    """`input` 모델의 매물 조건이 하나도 없으면 직렬화 결과에 null 로 넣는다 (`input` 모델의 `model_serializer` 용).

    웹은 동 클러스터 목록(`articleByClusterId`)과 지역 거품(`articleClusters`)에 조건이 없으면 `propertyFilter: null` 을 명시해
    보낸다 (mapQueryFilter 의 atom 이 null, 2026-11-12 번들 대조). GraphQL 은 변수 생략과 null 을 구분할 수 있어 웹과 같게 null
    을 보낸다. client 가 변수를 `exclude_none` 으로 직렬화해도 여기서 넣은 null 은 남는다. 빈 조건인지(`is_empty_property_filter`)
    여기서 가려 부르는 쪽은 조건을 그대로 넘긴다. 예전에는 부르는 쪽이 빈 조건을 None 으로 바꿔 넘겨야 해서, 빠뜨리면 빈 필터
    `{salesTypes: []}` 가 나갔다 (2026-11-12 리뷰. 결과는 같았다: 역삼동 둘레 거품 142개·역삼동 6,426건).

    키 이름은 직렬화하는 이름을 따른다 (alias 면 `propertyFilter`, 아니면 `property_filter`). 늘 `propertyFilter` 로 넣으면 alias
    없이 직렬화할 때 `property_filter` 와 `propertyFilter: None` 이 함께 나왔다 (2026-11-12 리뷰).
    """
    if is_empty_property_filter(property_filter):
        data['propertyFilter' if info.by_alias else 'property_filter'] = None
    return data
