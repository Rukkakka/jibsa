"""요청 모델: 학교·어린이집 (school, preschools, preschool)."""


from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.request.common import DaangnCoordinateInputModel

from typing import (
    Annotated,
    Literal,
)


DaangnEducationType = Literal['DAYCARE', 'KINDERGARTEN', 'ELEMENTARY', 'MIDDLE', 'HIGH']


class DaangnEducationMapPointsInputModel(RequestModel):
    """`educationMapPoints` 의 `input`. 좌표 범위 안의 시설을 500개까지 준다 (2026-10-10 실측, 페이지 없음)."""

    sw_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='남서 꼭짓점')
    ] = Field(alias='swCoordinate')
    ne_coordinate: Annotated[
        DaangnCoordinateInputModel,
        Field(description='북동 꼭짓점')
    ] = Field(alias='neCoordinate')
    types: Annotated[
        list[DaangnEducationType],
        Field(min_length=1, description='DAYCARE(어린이집) / KINDERGARTEN(유치원) / ELEMENTARY·MIDDLE·HIGH')
    ]


class DaangnEducationMapPointsRequestPayloadModel(RequestModel):
    """GraphQL `educationMapPoints` 쿼리 변수 (웹의 `EducationPoiLayerQuery`, 지도 교육 시설)."""

    input: Annotated[
        DaangnEducationMapPointsInputModel,
        Field(description='좌표 범위·시설 종류')
    ]


class DaangnPreschoolByNoRequestPayloadModel(RequestModel):
    """GraphQL `preschoolByNo` 쿼리 변수 (웹의 `PreschoolDetailPanelQuery`, 어린이집·유치원 상세).

    번호는 숫자로 보내야 한다 (문자열·'pre_' 접두어면 "알 수 없는 오류").
    """

    pre_school_no: Annotated[
        int,
        Field(gt=0, description="시설 번호 (educationMapPoints 의 id 에서 'pre_' 를 뗀 숫자)")
    ] = Field(alias='preSchoolNo')


class DaangnSearchSchoolsInputModel(RequestModel):
    """`searchSchools` 의 `input`."""

    name: Annotated[
        str,
        Field(min_length=1, description="학교 이름 (일부만 줘도 된다. '역삼초등학교' 로 '서울역삼초등학교' 가 나온다)")
    ]


class DaangnSearchSchoolsRequestPayloadModel(RequestModel):
    """GraphQL `searchSchools` 쿼리 변수 (웹의 `fetchSchoolSearchResultQuery`, 학교 이름 검색)."""

    first: Annotated[
        int,
        Field(ge=1, le=50, description='한 번에 받을 학교 수')
    ] = 20
    after: Annotated[
        str | None,
        Field(description='이전 페이지의 pageInfo.endCursor. 없으면 첫 페이지')
    ] = None
    input: Annotated[
        DaangnSearchSchoolsInputModel,
        Field(description='검색어')
    ]


class DaangnSchoolByCodeRequestPayloadModel(RequestModel):
    """GraphQL `schoolByCode` 쿼리 변수 (웹의 `SchoolDetailQuery`, 학교 정보와 배정 단지)."""

    sch_cd: Annotated[
        str,
        Field(min_length=1, description='학교 코드 (searchSchools 의 schCd, 예: B100000775)')
    ] = Field(alias='schCd')
