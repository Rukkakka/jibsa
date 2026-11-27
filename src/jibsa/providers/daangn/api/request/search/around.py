"""요청 모델: 역·대학 주변 매물 검색 (search listings)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnPropertyFilterModel

from typing import Annotated


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


class DaangnUniversityArticleConnectionRequestPayloadModel(RequestModel):
    """GraphQL `universityArticleConnection` 쿼리 변수 (웹 대학 페이지의 `UniversityArticleListPanelPaginationQuery`).

    첫 페이지용 `UniversityArticleListPanelQuery` 와 루트 필드·변수가 같고 `after` 를 받아, 역 주변 매물처럼 페이지 넘김
    쿼리 하나만 쓴다. 대학 둘레 범위(웹의 `landingRadiusMeter`)는 서버가 정한다.
    """

    school_poi_id: Annotated[
        str,
        Field(min_length=1, description='대학 ID (searchSchoolPois 의 id)', alias='schoolPoiId')
    ]
    first: Annotated[
        int,
        Field(ge=1, le=100, description='한 번에 받을 매물 수. 웹은 10건씩 받는다')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    property_filter: Annotated[
        DaangnPropertyFilterModel,
        Field(description='매물 조건 (articleFeed 와 같다)', alias='propertyFilter')
    ] = Field(default_factory=DaangnPropertyFilterModel)
