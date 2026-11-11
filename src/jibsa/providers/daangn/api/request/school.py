"""요청 모델: 학교·어린이집 (school, preschools, preschool)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import Annotated


class DaangnComplexSchoolsRequestPayloadModel(RequestModel):
    """GraphQL `complexByOriginalId { complex { proptierDanji { nearbyPreschools } } }` 쿼리 변수.

    웹의 `ComplexSchoolListPanelQuery` (단지 화면 학군의 '더 보기', 근처 학교·어린이집). 루트 필드가 단지 실거래가와 같은
    `complexByOriginalId` 라 action id 는 `complex_schools` 로 구분한다.
    """

    complex_id: Annotated[
        str,
        Field(min_length=1, description='숫자 단지 ID', alias='complexId')
    ]


class DaangnPreschoolByNoRequestPayloadModel(RequestModel):
    """GraphQL `preschoolByNo` 쿼리 변수 (웹의 `PreschoolDetailPanelQuery`, 어린이집·유치원 상세).

    번호는 숫자로 보내야 한다 (문자열·'pre_' 접두어면 "알 수 없는 오류").
    """

    pre_school_no: Annotated[
        int,
        Field(gt=0, description='시설 번호 (단지 근처 어린이집 nearbyPreschools 의 preSchoolNo)', alias='preSchoolNo')
    ]


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
        Field(min_length=1, description='학교 코드 (searchSchools 의 schCd, 예: B100000775)', alias='schCd')
    ]
