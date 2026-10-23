"""응답 모델: 개발 호재 목록·상세 (developments, development)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.daangn.api.response.common import (
    DaangnCoordinateModel,
    DaangnGraphQLResponseModel,
    LooseFloat,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# POST realty.kr.karrotmarket.com/graphql — 개발 호재, 어린이집·유치원
# ---------------------------------------------------------------------------

class DaangnDevelopmentDistrictModel(ResponseModel):
    """개발 사업 하나 (지도 표시용). 경계(`geometry`)는 크고 쓰지 않아 읽지 않는다."""

    dev_busi_no: Annotated[
        int,
        Field(description='사업 번호', alias='devBusiNo')
    ]
    dev_busi_nm: Annotated[
        str | None,
        Field(description='사업 이름', alias='devBusiNm')
    ] = None
    category: Annotated[
        str | None,
        Field(description='ROAD / RAIL / HOUSING')
    ] = None
    busi_prgrs_cd: Annotated[
        str | None,
        Field(description='진행 코드. S11 예정, S12 진행, E01 은 웹이 지도에서 숨긴다', alias='busiPrgrsCd')
    ] = None
    center_coordinate: Annotated[
        DaangnCoordinateModel | None,
        Field(description='사업 구역 중심', alias='centerCoordinate')
    ] = None


class DaangnDevelopmentDistrictsDataModel(ResponseModel):
    """GraphQL `data`."""

    development_districts: Annotated[
        list[DaangnDevelopmentDistrictModel],
        Field(description='좌표 범위 안의 개발 사업', alias='developmentDistricts')
    ] = []


class DaangnDevelopmentDistrictsResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `developmentDistricts` 응답."""

    data: Annotated[
        DaangnDevelopmentDistrictsDataModel | None,
        Field(description='결과')
    ] = None


class DaangnDevelopmentDetailModel(ResponseModel):
    """개발 사업 상세. 사진(`images`)은 읽지 않는다."""

    dev_busi_nm: Annotated[
        str | None,
        Field(description='사업 이름', alias='devBusiNm')
    ] = None
    dev_busi_sort: Annotated[
        str | None,
        Field(description='사업 분류 (예: 정비사업)', alias='devBusiSort')
    ] = None
    dev_busi_type: Annotated[
        str | None,
        Field(description='사업 종류 (예: 재건축)', alias='devBusiType')
    ] = None
    busi_prgrs: Annotated[
        str | None,
        Field(description='진행 상태 (예: 사업진행)', alias='busiPrgrs')
    ] = None
    busi_step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 착공및분양)', alias='busiStep')
    ] = None
    busi_term: Annotated[
        str | None,
        Field(description='사업 기간', alias='busiTerm')
    ] = None
    busi_area: Annotated[
        LooseFloat,
        Field(description='사업 면적 (㎡)', alias='busiArea')
    ] = None
    busi_size: Annotated[
        str | None,
        Field(description='사업 규모 (예: 1,802명/721세대)', alias='busiSize')
    ] = None
    location: Annotated[
        str | None,
        Field(description='위치 (지번 일부)')
    ] = None
    developer_nm: Annotated[
        str | None,
        Field(description='사업 시행자', alias='developerNm')
    ] = None
    developer_type: Annotated[
        str | None,
        Field(description='시행 방식 (예: 조합방식)', alias='developerType')
    ] = None
    cstr_cp_nm: Annotated[
        str | None,
        Field(description='시공사', alias='cstrCpNm')
    ] = None
    plan_hseh_cnt: Annotated[
        int | None,
        Field(description='계획 세대수', alias='planHsehCnt')
    ] = None
    building_coverage: Annotated[
        LooseFloat,
        Field(description='건폐율 (%)', alias='buildingCoverage')
    ] = None
    floor_space_idx: Annotated[
        LooseFloat,
        Field(description='용적률 (%)', alias='floorSpaceIdx')
    ] = None
    basic_plan_floor_cnt: Annotated[
        str | None,
        Field(description='계획 최고 층수', alias='basicPlanFloorCnt')
    ] = None
    target_y: Annotated[
        str | None,
        Field(description='목표 연도', alias='targetY')
    ] = None
    area_designation_date: Annotated[
        str | None,
        Field(description='구역 지정일', alias='areaDesignationDate')
    ] = None
    committee_apprv_date: Annotated[
        str | None,
        Field(description='추진위원회 승인일', alias='committeeApprvDate')
    ] = None
    estbm_union_date: Annotated[
        str | None,
        Field(description='조합 설립 인가일', alias='estbmUnionDate')
    ] = None
    dev_plan_aprv_date: Annotated[
        str | None,
        Field(description='개발 계획 승인일', alias='devPlanAprvDate')
    ] = None
    impl_plan_aprv_date: Annotated[
        str | None,
        Field(description='실시 계획 승인일', alias='implPlanAprvDate')
    ] = None
    proj_implmtt_date: Annotated[
        str | None,
        Field(description='사업 시행 인가일', alias='projImplmttDate')
    ] = None
    mngm_disps_date: Annotated[
        str | None,
        Field(description='관리 처분 인가일', alias='mngmDispsDate')
    ] = None


class DaangnDevelopmentByBusiNoDataModel(ResponseModel):
    """GraphQL `data`."""

    development_by_busi_no: Annotated[
        DaangnDevelopmentDetailModel | None,
        Field(description='사업 상세. 없는 번호면 null', alias='developmentByBusiNo')
    ] = None


class DaangnDevelopmentByBusiNoResponseModel(DaangnGraphQLResponseModel):
    """GraphQL `developmentByBusiNo` 응답."""

    data: Annotated[
        DaangnDevelopmentByBusiNoDataModel | None,
        Field(description='결과')
    ] = None
