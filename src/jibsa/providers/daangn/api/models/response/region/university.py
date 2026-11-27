"""응답 모델: 대학 이름 검색 (search locations 의 대학)."""

from pydantic import Field

from jibsa.providers.daangn.api.models.response.common import (
    DaangnBaseResponseModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


class DaangnSchoolPoiModel(DaangnBaseResponseModel):
    """대학 검색 결과 하나 (캠퍼스 하나)."""

    id: Annotated[
        str,
        Field(description='대학 ID (universityArticleConnection 의 schoolPoiId 로 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='대학 이름. 캠퍼스가 여럿이면 모두 같다 (예: 연세대학교)')
    ]
    full_name: Annotated[
        str | None,
        Field(description='캠퍼스까지 붙인 이름 (예: 연세대학교 신촌캠퍼스). 캠퍼스가 하나뿐이면 null 이기도 하다', alias='fullName')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description='지번 주소', alias='jibunAddress')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='대학 좌표')
    ] = None


class DaangnSchoolPoiEdgeModel(DaangnBaseResponseModel):
    """대학 연결의 edge."""

    node: Annotated[
        DaangnSchoolPoiModel | None,
        Field(description='대학')
    ] = None


class DaangnSchoolPoiConnectionModel(DaangnBaseResponseModel):
    """대학 연결."""

    edges: Annotated[
        list[DaangnSchoolPoiEdgeModel],
        Field(description='대학')
    ] = []


class DaangnSearchSchoolPoisDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    search_school_pois: Annotated[
        DaangnSchoolPoiConnectionModel | None,
        Field(description='대학 검색 결과', alias='searchSchoolPois')
    ] = None


class DaangnSearchSchoolPoisResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchSchoolPois` 응답."""

    data: Annotated[
        DaangnSearchSchoolPoisDataModel | None,
        Field(description='결과')
    ] = None
