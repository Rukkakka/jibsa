"""응답 모델: 매물 검색 조건과 동·지도 범위·역·대학 주변 매물 검색 (search listings)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnCommuteStationArticleConnectionModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleFeed
# ---------------------------------------------------------------------------

class DaangnArticleFeedCardModel(ResponseModel):
    """피드 카드 한 장. 실제로는 늘 매물 카드(ARTICLE)에 매물이 있다.

    광고 카드처럼 article 이 null 인 카드는 보지 못했고 웹도 `e.node.article.region.name3` 를 검사 없이 읽는다 (2026-10-11
    실측: SSR 5개 동 카드 200장·GraphQL 3개 동 180장 모두 article 이 객체였고 type 은 ARTICLE 만 왔다).
    """

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
    cursor: Annotated[
        str | None,
        Field(description=(
            '이 카드 다음부터 받을 커서. base64 로 감싼 "정렬 시각|순번|0" 이고, 같은 매물은 어느 동 피드에서나 시각이 같다'
        ))
    ] = None


class DaangnArticleFeedModel(ResponseModel):
    """`articleFeed` 연결. 최근 게시 순이다."""

    edges: Annotated[
        list[DaangnArticleFeedEdgeModel],
        Field(description='카드')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnArticleFeedDataModel(ResponseModel):
    """GraphQL `data`."""

    article_feed: Annotated[
        DaangnArticleFeedModel | None,
        Field(description='매물 피드', alias='articleFeed')
    ] = None


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
        Field(description="지도 화면의 좌표 범위에서 조건에 맞는 매물 수 (웹 지도의 '매물 N개'). 1000 에서 잘린다 (웹은 '999+')")
    ] = None


class DaangnArticlesCountResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articlesCount` 응답."""

    data: Annotated[
        DaangnArticlesCountDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleByClusterId (지도 동 클러스터 매물 목록)
# ---------------------------------------------------------------------------

class DaangnArticleByClusterIdDataModel(ResponseModel):
    """GraphQL `data`. 동 피드와 같은 연결 타입(ArticleFeedConnection)이다."""

    article_by_cluster_id: Annotated[
        DaangnArticleFeedModel | None,
        Field(description='동 클러스터 매물', alias='articleByClusterId')
    ] = None


class DaangnArticleByClusterIdResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleByClusterId` 응답."""

    data: Annotated[
        DaangnArticleByClusterIdDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — articleClusters (지도 지역 거품의 매물 수)
# ---------------------------------------------------------------------------

class DaangnArticleClusterModel(ResponseModel):
    """지도 지역 거품 하나."""

    original_id: Annotated[
        str,
        Field(description="클러스터 ID ('REGION:<동 ID>')", alias='originalId')
    ]
    name: Annotated[
        str | None,
        Field(description='지역 이름')
    ] = None
    count: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수 (웹 거품의 "매물 N개")')
    ] = None


class DaangnArticleClustersDataModel(ResponseModel):
    """GraphQL `data`."""

    article_clusters: Annotated[
        list[DaangnArticleClusterModel],
        Field(description='범위 안 지역 거품', alias='articleClusters')
    ] = []


class DaangnArticleClustersResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `articleClusters` 응답."""

    data: Annotated[
        DaangnArticleClustersDataModel | None,
        Field(description='결과')
    ] = None


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — subwayStationArticleConnection / universityArticleConnection (역·대학 주변 매물)
# ---------------------------------------------------------------------------

class DaangnSubwayStationArticleConnectionDataModel(ResponseModel):
    """GraphQL `data`. 출퇴근 역 매물과 같은 연결 타입(CommuteArticleConnection)이다."""

    subway_station_article_connection: Annotated[
        DaangnCommuteStationArticleConnectionModel | None,
        Field(description='역 주변 매물. 카드에 상태·거래 조건·역별 도보 시간이 다 있다', alias='subwayStationArticleConnection')
    ] = None


class DaangnSubwayStationArticleConnectionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `subwayStationArticleConnection` 응답."""

    data: Annotated[
        DaangnSubwayStationArticleConnectionDataModel | None,
        Field(description='결과')
    ] = None


class DaangnUniversityArticleConnectionDataModel(ResponseModel):
    """GraphQL `data`. 역 주변 매물과 같은 연결 타입(CommuteArticleConnection)이다 (2026-11-11 실측)."""

    university_article_connection: Annotated[
        DaangnCommuteStationArticleConnectionModel | None,
        Field(description='대학 주변 매물. 카드에 상태·거래 조건이 다 있다', alias='universityArticleConnection')
    ] = None


class DaangnUniversityArticleConnectionResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `universityArticleConnection` 응답."""

    data: Annotated[
        DaangnUniversityArticleConnectionDataModel | None,
        Field(description='결과')
    ] = None
