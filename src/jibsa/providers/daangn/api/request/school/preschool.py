"""요청 모델: 어린이집 (preschools, preschool)."""

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
