"""응답 모델: 학교 상세와 배정 동 (school)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import NaverResponseModel

from typing import Annotated


class NaverSchoolStudentModel(ResponseModel):
    """학교 학생 공시."""

    base_date: Annotated[
        str | None,
        Field(description='공시 기준일 (YYYY-MM-DD)')
    ] = Field(default=None, alias='baseDate')
    count_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = Field(default=None, alias='countPerTeacher')
    count_per_classroom: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = Field(default=None, alias='countPerClassroom')
    total_count: Annotated[
        int | None,
        Field(description='전체 학생 수')
    ] = Field(default=None, alias='totalCount')


class NaverRegionStudentModel(ResponseModel):
    """시·구 평균 학생 수 (비교용)."""

    region_name: Annotated[
        str | None,
        Field(description='지역 이름 (서울시, 강남구 ...)')
    ] = Field(default=None, alias='regionName')
    count_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = Field(default=None, alias='countPerTeacher')
    count_per_classroom: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = Field(default=None, alias='countPerClassroom')


class NaverSchoolDetailModel(ResponseModel):
    """학교 상세 (학교알리미 공시). 전화·홈페이지·좌표·학구도 경계(vertexes)도 오지만 쓰지 않는다."""

    school_code: Annotated[
        str,
        Field(description='학교 코드')
    ] = Field(alias='schoolCode')
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    office_of_education_in_charge: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = Field(default=None, alias='officeOfEducationInCharge')
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = Field(default=None, alias='operationType')
    establishment_type: Annotated[
        str | None,
        Field(description='설립 형태 (단설, 병설 ...)')
    ] = Field(default=None, alias='establishmentType')
    establishment_date: Annotated[
        str | None,
        Field(description='개교일 (YYYY-MM-DD)')
    ] = Field(default=None, alias='establishmentDate')
    student: Annotated[
        NaverSchoolStudentModel | None,
        Field(description='학생 공시')
    ] = None
    city_student: Annotated[
        NaverRegionStudentModel | None,
        Field(description='시·도 평균')
    ] = Field(default=None, alias='cityStudent')
    division_student: Annotated[
        NaverRegionStudentModel | None,
        Field(description='시·군·구 평균')
    ] = Field(default=None, alias='divisionStudent')


class NaverSchoolAllocationDongsModel(ResponseModel):
    """단지에서 그 학교에 배정되는 동."""

    is_all_building_assigned: Annotated[
        bool | None,
        Field(description='단지 전체 동이 배정되는지')
    ] = Field(default=None, alias='isAllBuildingAssigned')
    converted_building_name_groups: Annotated[
        list[list[str]],
        Field(description='배정되는 동 이름 묶음. 사이트는 묶음마다 첫~끝 동으로 보여 준다 (101~105동)')
    ] = Field(default=[], alias='convertedBuildingNameGroups')


class NaverEducationSchoolV1ResponseModel(NaverResponseModel[NaverSchoolDetailModel]):
    """`GET /front-api/v1/education/school` 응답."""


class NaverEducationComplexSchoolAllocationDongsV1ResponseModel(NaverResponseModel[NaverSchoolAllocationDongsModel]):
    """`GET /front-api/v1/education/complex/school/allocation-dongs` 응답."""
