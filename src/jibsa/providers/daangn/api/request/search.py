"""요청 모델: 매물 검색 조건과 동·반경·역 주변 매물 검색 (search listings)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import (
    DaangnCoordinateInputModel,
    DaangnLocationFilterModel,
    DaangnPropertyFilterModel,
)

from typing import (
    Annotated,
    Literal,
)


class DaangnMapRequestParameterModel(RequestModel):
    """`GET realty.daangn.com/map/{name1}/{name2}/{name3}` 경로.

    모두 경로에만 쓰이며 쿼리로는 보내지 않는다. 구가 없는 시(세종특별자치시)는
    `name2` 가 빈 문자열이고 경로에서 그 세그먼트를 뺀다 (`/map/세종특별자치시/반곡동`).
    """

    name1: Annotated[
        str,
        Field(min_length=1, exclude=True, description='시/도 (예: 서울특별시)')
    ]
    name2: Annotated[
        str,
        Field(exclude=True, description='시/군/구 (예: 강남구). 구가 없는 시는 빈 문자열')
    ]
    name3: Annotated[
        str,
        Field(min_length=1, exclude=True, description='읍/면/동 (예: 역삼동)')
    ]


class DaangnArticleFeedInputModel(RequestModel):
    """`articleFeed` 의 `input`."""

    location_filter: Annotated[
        DaangnLocationFilterModel,
        Field(description='지역 조건', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
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
        DaangnLocationFilterModel,
        Field(description='지역 조건', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)


class DaangnArticlesCountRequestPayloadModel(RequestModel):
    """GraphQL `articlesCount` 쿼리 변수 (웹의 `MapFloatingControlsArticleCountQuery`, 조건에 맞는 매물 수)."""

    input: Annotated[
        DaangnArticlesCountInputModel,
        Field(description='지역·매물 조건')
    ]


class DaangnBoundsLocationFilterModel(RequestModel):
    """좌표 범위 지역 조건 (웹 지도 화면의 북동·남서 꼭짓점)."""

    ne_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='북동 꼭짓점', alias='neCoordinate')
    ]
    sw_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='남서 꼭짓점', alias='swCoordinate')
    ]


class DaangnArticleMapPointsInputModel(RequestModel):
    """`articleMapPoints` 의 `input`."""

    location_filter: Annotated[
        DaangnBoundsLocationFilterModel,
        Field(description='좌표 범위', alias='locationFilter')
    ]
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)


class DaangnArticleMapPointsRequestPayloadModel(RequestModel):
    """GraphQL `articleMapPoints` 쿼리 변수 (웹의 `MapViewPinsQuery`)."""

    input: Annotated[
        DaangnArticleMapPointsInputModel,
        Field(description='좌표 범위·매물 조건')
    ]


class DaangnArticlesByOriginalArticleIdsRequestPayloadModel(RequestModel):
    """GraphQL `articlesByOriginalArticleIds` 쿼리 변수 (웹의 `PinArticleListPanelChunkQuery`)."""

    original_article_ids: Annotated[
        list[str],
        Field(min_length=1, max_length=20, description='숫자 매물 ID. 웹처럼 한 번에 20개까지', alias='originalArticleIds')
    ]


class DaangnSubwayStationArticleConnectionRequestPayloadModel(RequestModel):
    """GraphQL `subwayStationArticleConnection` 쿼리 변수 (웹의 `SubwayArticleListPanelPaginationQuery`, 역 주변 매물).

    첫 페이지용 `SubwayArticleListPanelQuery` 와 결과가 같고 `after` 를 받아 페이지 넘김 쿼리 하나만 쓴다.
    """

    subway_station_poi_id: Annotated[
        str,
        Field(min_length=1, description='역 ID (searchSubwayStationPois 의 id)', alias='subwayStationPoiId')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 매물 수 (서버는 100 까지 준다)')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
