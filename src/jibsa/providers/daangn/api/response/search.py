"""응답 모델: 매물 검색 조건과 동·반경·역 주변 매물 검색 (search listings)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# SSR Relay store records (map / articles pages)
# ---------------------------------------------------------------------------

class DaangnMapResponseModel(ResponseModel):
    """지도 페이지에서 추출한 동 단위 매물 피드 (최대 20건)."""

    region: Annotated[
        DaangnRegionModel | None,
        Field(description='조회한 동')
    ] = None
    articles: Annotated[
        list[DaangnArticleModel],
        Field(description='최근 매물 (SSR 첫 페이지)')
    ] = []
    total_count: Annotated[
        int | None,
        Field(description='동 전체 매물 수 (서버가 1000 으로 자르는 것으로 보인다)')
    ] = None
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 존재 여부')
    ] = None
    end_cursor: Annotated[
        str | None,
        Field(description='첫 페이지의 pageInfo.endCursor. GraphQL `articleFeed` 의 after 로 다음 페이지를 받는다')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleFeed
# ---------------------------------------------------------------------------

class DaangnArticleFeedCardModel(ResponseModel):
    """피드 카드 한 장. 실제로는 늘 매물 카드(ARTICLE)에 매물이 있다 (`parser._feed_articles` 주석 참고)."""

    type: Annotated[
        str | None,
        Field(description='카드 종류 (ARTICLE ...)')
    ] = None
    article: Annotated[
        DaangnArticleModel | None,
        Field(description='매물. 지역(region)에 시·도(name1)와 지역 ID 가 없다')
    ] = None


class DaangnArticleFeedEdgeModel(ResponseModel):
    """피드 연결의 edge."""

    node: Annotated[
        DaangnArticleFeedCardModel | None,
        Field(description='카드')
    ] = None


class DaangnArticleFeedModel(ResponseModel):
    """`articleFeed` 연결. 최근 게시 순이다."""

    edges: Annotated[
        list[DaangnArticleFeedEdgeModel],
        Field(description='카드')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보')
    ] = Field(default=None, alias='pageInfo')


class DaangnArticleFeedDataModel(ResponseModel):
    """GraphQL `data`."""

    article_feed: Annotated[
        DaangnArticleFeedModel | None,
        Field(description='매물 피드')
    ] = Field(default=None, alias='articleFeed')


class DaangnArticleFeedResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleFeed` 응답."""

    data: Annotated[
        DaangnArticleFeedDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articlesCount
# ---------------------------------------------------------------------------

class DaangnArticlesCountDataModel(ResponseModel):
    """GraphQL `data`. 웹 쿼리가 루트 필드에 `count` 별칭을 붙인다."""

    count: Annotated[
        int | None,
        Field(description=(
            '조건에 맞는 매물 수. 동으로 찾으면 articleFeed 가 섞어 주는 주변 동 매물까지 센 수로, '
            'articleFeed 를 끝까지 넘긴 매물 수와 같다. 1000 에서 잘린다'
        ))
    ] = None


class DaangnArticlesCountResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articlesCount` 응답."""

    data: Annotated[
        DaangnArticlesCountDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleMapPoints
# ---------------------------------------------------------------------------

class DaangnArticlePointModel(ResponseModel):
    """지도 핀 하나. 매물 ID 와 좌표만 있다."""

    original_article_id: Annotated[
        str,
        Field(description='숫자 매물 ID')
    ] = Field(alias='originalArticleId')
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='매물 좌표')
    ] = None


class DaangnArticleMapPointsDataModel(ResponseModel):
    """GraphQL `data`."""

    article_map_points: Annotated[
        list[DaangnArticlePointModel] | None,
        Field(description='좌표 범위 안 핀. 순서는 정해져 있지 않고, 넓은 범위는 10000 개에서 잘린다')
    ] = Field(default=None, alias='articleMapPoints')


class DaangnArticleMapPointsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleMapPoints` 응답."""

    data: Annotated[
        DaangnArticleMapPointsDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articlesByOriginalArticleIds
# ---------------------------------------------------------------------------

class DaangnArticlesByOriginalArticleIdsDataModel(ResponseModel):
    """GraphQL `data`. 웹 쿼리가 루트 필드에 `articles` 별칭을 붙인다."""

    articles: Annotated[
        list[DaangnArticleModel] | None,
        Field(description='매물 카드 (articleFeed 카드와 같은 필드). 지역에 시·도(name1)와 지역 ID 가 없다')
    ] = None


class DaangnArticlesByOriginalArticleIdsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articlesByOriginalArticleIds` 응답."""

    data: Annotated[
        DaangnArticlesByOriginalArticleIdsDataModel | None,
        Field(description='결과')
    ] = None


class DaangnSubwayStationArticleConnectionDataModel(ResponseModel):
    """GraphQL `data`. 출퇴근 역 매물과 같은 연결 타입(CommuteArticleConnection)이다."""

    subway_station_article_connection: Annotated[
        DaangnCommuteStationArticleConnectionModel | None,
        Field(description='역 주변 매물. 카드에 상태·거래 조건·역별 도보 시간이 다 있다')
    ] = Field(default=None, alias='subwayStationArticleConnection')


class DaangnSubwayStationArticleConnectionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `subwayStationArticleConnection` 응답."""

    data: Annotated[
        DaangnSubwayStationArticleConnectionDataModel | None,
        Field(description='결과')
    ] = None
