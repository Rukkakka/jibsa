"""응답 모델: 학교 (school)."""

from pydantic import Field

from jibsa.providers.daangn.api.response.common import (
    DaangnBaseResponseModel,
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    DaangnPageInfoModel,
    DaangnRegionComplexNodeModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — searchSchools, schoolByCode (학교·배정 단지)
# ---------------------------------------------------------------------------

class DaangnSchoolSearchNodeModel(DaangnBaseResponseModel):
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



class DaangnSchoolSearchEdgeModel(DaangnBaseResponseModel):
    """학교 검색 연결의 edge."""

    node: Annotated[
        DaangnSchoolSearchNodeModel | None,
        Field(description='학교')
    ] = None



class DaangnSchoolSearchModel(DaangnBaseResponseModel):
    """`searchSchools` 연결. 전국 학교가 섞인다 ('중앙초등학교' 는 20곳이 넘는다)."""

    edges: Annotated[
        list[DaangnSchoolSearchEdgeModel],
        Field(description='학교')
    ] = []
    page_info: Annotated[
        DaangnPageInfoModel | None,
        Field(description='페이지 정보', alias='pageInfo')
    ] = None



class DaangnSearchSchoolsDataModel(DaangnBaseResponseModel):
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



class DaangnSchoolDetailModel(DaangnBaseResponseModel):
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



class DaangnSchoolByCodeDataModel(DaangnBaseResponseModel):
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
