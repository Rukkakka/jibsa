"""응답 모델: 어린이집 (preschools, preschool)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId (단지 근처 어린이집·유치원, complex_schools)
# ---------------------------------------------------------------------------

class DaangnSchoolSurveyResultModel(DaangnBaseResponseModel):
    """당근 학교·어린이집 설문. 웹 쿼리가 응답 수(`responseCount`)를 `reviewCount` 로 받는다."""

    review_count: Annotated[
        int | None,
        Field(description='설문 후기 수', alias='reviewCount')
    ] = None



class DaangnNearbyPreschoolModel(DaangnBaseResponseModel):
    """단지 근처 어린이집·유치원 하나 (`ProptierPreschool`). 어린이집·유치원 구분은 오지 않는다."""

    # 필수로 둔다. 웹도 null 검사 없이 키로 쓰고, 빠지면 응답 형식이 바뀐 것이라 한 곳만 빼고 넘기지 않고 PARSE_ERROR 로
    # 드러나게 한다 (2026-11-11 실측: 역삼래미안 20곳 모두 있음)
    pre_school_no: Annotated[
        int,
        Field(description='시설 번호 (preschoolByNo 에 넘긴다)', alias='preSchoolNo')
    ]
    school_nm: Annotated[
        str | None,
        Field(description='시설 이름', alias='schoolNm')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='좌표 (단지에서 거리를 재는 데만 쓴다)')
    ] = None
    complex_resident_count: Annotated[
        int | None,
        Field(description='이 단지 주민 중 다니는 수 (당근 집계)', alias='complexResidentCount')
    ] = None
    survey_result: Annotated[
        DaangnSchoolSurveyResultModel | None,
        Field(description='설문. 응답이 없으면 null', alias='surveyResult')
    ] = None



class DaangnComplexSchoolsDanjiModel(DaangnBaseResponseModel):
    """단지의 학군 정보 (`proptierDanji`). 배정 초등학교·중·고등학교도 오지만 읽지 않는다."""

    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='학군 정보의 단지 좌표. 웹은 이 좌표에서 시설까지 거리를 잰다')
    ] = None
    nearby_preschools: Annotated[
        list[DaangnNearbyPreschoolModel] | None,
        Field(
            description=(
                '근처 어린이집·유치원. 단지에서 1km 안을 가까운 순으로 20곳까지 준다(2026-11-11 실측). 웹은 주민 이용 수로 '
                '다시 정렬한다'
            ),
            alias='nearbyPreschools',
        )
    ] = None



class DaangnComplexSchoolsComplexModel(DaangnBaseResponseModel):
    """단지 (좌표와 학군 정보만 받는다)."""

    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='단지 좌표. 학군 정보에 좌표가 없을 때 웹이 쓴다')
    ] = None
    proptier_danji: Annotated[
        DaangnComplexSchoolsDanjiModel | None,
        Field(description='학군 정보. 없는 단지면 null', alias='proptierDanji')
    ] = None



class DaangnComplexSchoolsOutputModel(DaangnBaseResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexSchoolsComplexModel | None,
        Field(description='단지')
    ] = None



class DaangnComplexSchoolsDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    complex_by_original_id: Annotated[
        DaangnComplexSchoolsOutputModel | None,
        Field(description='단지 조회 결과', alias='complexByOriginalId')
    ] = None



class DaangnComplexSchoolsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL 단지 근처 학교·어린이집 응답 (웹의 `ComplexSchoolListPanelQuery`)."""

    data: Annotated[
        DaangnComplexSchoolsDataModel | None,
        Field(description='결과')
    ] = None



class DaangnPreschoolRegionModel(DaangnBaseResponseModel):
    """어린이집·유치원이 있는 구·동."""

    name2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    name3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None



class DaangnPreschoolSurveyResultModel(DaangnBaseResponseModel):
    """어린이집·유치원 상세의 당근 설문 (`surveyResult`). 목록 쿼리와 달리 `responseCount` 이름 그대로 온다."""

    response_count: Annotated[
        int | None,
        Field(description='설문 응답 수', alias='responseCount')
    ] = None



class DaangnPreschoolModel(DaangnBaseResponseModel):
    """어린이집·유치원 상세. 전화번호·홈페이지는 학교 정보처럼 내보내지 않아 읽지 않는다."""

    school_nm: Annotated[
        str | None,
        Field(description='시설 이름', alias='schoolNm')
    ] = None
    type: Annotated[
        str | None,
        Field(description='DAYCARE / KINDERGARTEN')
    ] = None
    addr: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    open_time: Annotated[
        str | None,
        Field(description='운영 시간', alias='openTime')
    ] = None
    estbshm_type: Annotated[
        str | None,
        Field(description='설립 유형 (국공립·민간·직장 등)', alias='estbshmType')
    ] = None
    estbshm_date: Annotated[
        str | None,
        Field(description='설립일', alias='estbshmDate')
    ] = None
    open_date: Annotated[
        str | None,
        Field(description='개원일', alias='openDate')
    ] = None
    jrsdt_admnstrt: Annotated[
        str | None,
        Field(description='관할 기관', alias='jrsdtAdmnstrt')
    ] = None
    child_cnt: Annotated[
        int | None,
        Field(description='정원 (당근 웹 어린이집 화면의 "정원 N명")', alias='childCnt')
    ] = None
    class_cnt: Annotated[
        int | None,
        Field(description='학급 수', alias='classCnt')
    ] = None
    teacher_cnt: Annotated[
        int | None,
        Field(description='교사 수', alias='teacherCnt')
    ] = None
    school_bus: Annotated[
        bool | None,
        Field(description='통학버스 운영', alias='schoolBus')
    ] = None
    region: Annotated[
        DaangnPreschoolRegionModel | None,
        Field(description='구·동')
    ] = None
    survey_result: Annotated[
        DaangnPreschoolSurveyResultModel | None,
        Field(description='당근 설문. 응답이 없으면 null (2026-11-12 실측: 역삼몬테소리어린이집 responseCount 1)', alias='surveyResult')
    ] = None



class DaangnPreschoolByNoDataModel(DaangnBaseResponseModel):
    """GraphQL `data`."""

    preschool_by_no: Annotated[
        DaangnPreschoolModel | None,
        Field(description='시설 상세. 없는 번호면 null', alias='preschoolByNo')
    ] = None



class DaangnPreschoolByNoResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `preschoolByNo` 응답."""

    data: Annotated[
        DaangnPreschoolByNoDataModel | None,
        Field(description='결과')
    ] = None
