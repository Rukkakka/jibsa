"""응답 모델: 역·대학 주변 매물 검색 (search listings)."""

from pydantic import Field

from jibsa.providers.daangn.api.models.response.common import (
    DaangnBaseResponseModel,
    DaangnCommuteStationArticleConnectionModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — subwayStationArticleConnection / universityArticleConnection (역·대학 주변 매물)
# ---------------------------------------------------------------------------

class DaangnSubwayStationArticleConnectionDataModel(DaangnBaseResponseModel):
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


class DaangnUniversityArticleConnectionDataModel(DaangnBaseResponseModel):
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
