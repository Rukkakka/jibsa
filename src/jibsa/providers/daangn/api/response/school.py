"""응답 모델: 학교·어린이집 (school, preschools, preschool)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionComplexNodeModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — complexByOriginalId (단지 근처 어린이집·유치원, complex_schools)
# ---------------------------------------------------------------------------

class DaangnSchoolSurveyResultModel(ResponseModel):
    """당근 학교·어린이집 설문. 웹 쿼리가 응답 수(`responseCount`)를 `reviewCount` 로 받는다."""

    review_count: Annotated[
        int | None,
        Field(description='설문 후기 수', alias='reviewCount')
    ] = None


class DaangnNearbyPreschoolModel(ResponseModel):
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


class DaangnComplexSchoolsDanjiModel(ResponseModel):
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


class DaangnComplexSchoolsComplexModel(ResponseModel):
    """단지 (좌표와 학군 정보만 받는다)."""

    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='단지 좌표. 학군 정보에 좌표가 없을 때 웹이 쓴다')
    ] = None
    proptier_danji: Annotated[
        DaangnComplexSchoolsDanjiModel | None,
        Field(description='학군 정보. 없는 단지면 null', alias='proptierDanji')
    ] = None


class DaangnComplexSchoolsOutputModel(ResponseModel):
    """`complexByOriginalId` 결과. 없는 단지면 `complex` 가 null 이다."""

    complex: Annotated[
        DaangnComplexSchoolsComplexModel | None,
        Field(description='단지')
    ] = None


class DaangnComplexSchoolsDataModel(ResponseModel):
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


class DaangnPreschoolRegionModel(ResponseModel):
    """어린이집·유치원이 있는 구·동."""

    name2: Annotated[
        str | None,
        Field(description='시/군/구')
    ] = None
    name3: Annotated[
        str | None,
        Field(description='읍/면/동')
    ] = None


class DaangnPreschoolSurveyResultModel(ResponseModel):
    """어린이집·유치원 상세의 당근 설문 (`surveyResult`). 목록 쿼리와 달리 `responseCount` 이름 그대로 온다."""

    response_count: Annotated[
        int | None,
        Field(description='설문 응답 수', alias='responseCount')
    ] = None


class DaangnPreschoolModel(ResponseModel):
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


class DaangnPreschoolByNoDataModel(ResponseModel):
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


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchSchools, schoolByCode (학교·배정 단지)
# ---------------------------------------------------------------------------

class DaangnSchoolSearchNodeModel(ResponseModel):
    """이름으로 찾은 학교. 좌표는 있는지만 본다 (웹 검색창은 좌표 없는 학교를 뺀다)."""

    sch_cd: Annotated[
        str,
        Field(description='학교 코드', alias='schCd')
    ]
    sch_nm: Annotated[
        str | None,
        Field(description="학교 이름 (예: '서울역삼초등학교')", alias='schNm')
    ] = None
    sch_addr: Annotated[
        str | None,
        Field(description='주소', alias='schAddr')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='학교 좌표. 내보내지 않고 있는지만 본다')
    ] = None


class DaangnSchoolSearchEdgeModel(ResponseModel):
    """학교 검색 연결의 edge."""

    node: Annotated[
        DaangnSchoolSearchNodeModel | None,
        Field(description='학교')
    ] = None


class DaangnSchoolSearchModel(ResponseModel):
    """`searchSchools` 연결. 전국 학교가 섞인다 ('중앙초등학교' 는 20곳이 넘는다)."""

    edges: Annotated[
        list[DaangnSchoolSearchEdgeModel],
        Field(description='학교')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None


class DaangnSearchSchoolsDataModel(ResponseModel):
    """GraphQL `data`."""

    search_schools: Annotated[
        DaangnSchoolSearchModel | None,
        Field(description='학교 검색 결과', alias='searchSchools')
    ] = None


class DaangnSearchSchoolsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `searchSchools` 응답."""

    data: Annotated[
        DaangnSearchSchoolsDataModel | None,
        Field(description='결과')
    ] = None


class DaangnSchoolDetailModel(ResponseModel):
    """학교 정보 (학교알리미 공시 기준)와 배정 단지. 전화·홈페이지·급식·통학버스 등은 쓰지 않는다."""

    sch_cd: Annotated[
        str,
        Field(description='학교 코드', alias='schCd')
    ]
    sch_nm: Annotated[
        str | None,
        Field(description='학교 이름', alias='schNm')
    ] = None
    sch_type: Annotated[
        str | None,
        Field(description='ELEMENTARY / MIDDLE / HIGH / ETC', alias='schType')
    ] = None
    sch_addr: Annotated[
        str | None,
        Field(description='주소', alias='schAddr')
    ] = None
    fond_sch_cd: Annotated[
        str | None,
        Field(description="설립 구분 (예: '공립', '사립')", alias='fondSchCd')
    ] = None
    coedu: Annotated[
        str | None,
        Field(description='MALE(남학교) / COED(남녀공학) / FEMALE(여학교)')
    ] = None
    tot_std_cnt: Annotated[
        int | None,
        Field(description='전체 학생 수', alias='totStdCnt')
    ] = None
    cls_std_cnt: Annotated[
        float | None,
        Field(description='학급당 학생 수', alias='clsStdCnt')
    ] = None
    tch_std_cnt: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수', alias='tchStdCnt')
    ] = None
    student_std_date: Annotated[
        str | None,
        Field(description="학생 수 기준 연도 (예: '2026')", alias='studentStdDate')
    ] = None
    assigned_complexes: Annotated[
        list[DaangnRegionComplexNodeModel] | None,
        Field(
            description='배정 단지 (초등학교만. 중·고등학교는 학교군 배정이라 빈 목록). 지역 단지 목록과 같은 카드이고 '
            '당근 웹 학교 화면과 같은 서버 순서다 (2026-11-12 실측: 대치초 15곳). 소규모 빌라형 단지도 섞인다. 최근 실거래는 매매다',
            alias='assignedComplexes'
        )
    ] = None


class DaangnSchoolByCodeDataModel(ResponseModel):
    """GraphQL `data`."""

    school_by_code: Annotated[
        DaangnSchoolDetailModel | None,
        Field(description='학교. 없는 코드면 null', alias='schoolByCode')
    ] = None


class DaangnSchoolByCodeResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `schoolByCode` 응답."""

    data: Annotated[
        DaangnSchoolByCodeDataModel | None,
        Field(description='결과')
    ] = None
