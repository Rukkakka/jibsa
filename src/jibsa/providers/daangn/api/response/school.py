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


class DaangnEducationMapPointModel(ResponseModel):
    """지도 교육 시설 하나."""

    id: Annotated[
        str,
        Field(description="시설 ID. 어린이집·유치원은 'pre_' + 시설 번호, 학교는 학교 코드")
    ]
    type: Annotated[
        str | None,
        Field(description='DAYCARE / KINDERGARTEN / ELEMENTARY / MIDDLE / HIGH')
    ] = None
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='좌표')
    ] = None


class DaangnEducationMapPointsDataModel(ResponseModel):
    """GraphQL `data`."""

    education_map_points: Annotated[
        list[DaangnEducationMapPointModel],
        Field(description='좌표 범위 안의 시설 (500개에서 잘린다)', alias='educationMapPoints')
    ] = []


class DaangnEducationMapPointsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `educationMapPoints` 응답."""

    data: Annotated[
        DaangnEducationMapPointsDataModel | None,
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
        Field(description='원아 수', alias='childCnt')
    ] = None
    class_cnt: Annotated[
        int | None,
        Field(description='반 수', alias='classCnt')
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
    """이름으로 찾은 학교. 좌표도 오지만 쓰지 않는다."""

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
            '순서가 정해져 있지 않으며, 소규모 빌라형 단지도 섞인다. 최근 실거래는 매매다',
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
