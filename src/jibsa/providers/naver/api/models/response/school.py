"""응답 모델: 학교 상세와 배정 동 (school)."""

from pydantic import Field

from jibsa.providers.naver.api.models.response.common import (
    NaverBaseResponseModel,
    NaverComplexArticleCountModel,
    NaverComplexArticlePriceModel,
    NaverComplexListInfoModel,
    NaverResponseModel,
)

from typing import Annotated


class NaverSchoolStudentModel(NaverBaseResponseModel):
    """학교 학생 공시."""

    base_date: Annotated[
        str | None,
        Field(description='공시 기준일 (YYYY-MM-DD)', alias='baseDate')
    ] = None
    count_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수', alias='countPerTeacher')
    ] = None
    count_per_classroom: Annotated[
        float | None,
        Field(description='학급당 학생 수', alias='countPerClassroom')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='전체 학생 수', alias='totalCount')
    ] = None


class NaverRegionStudentModel(NaverBaseResponseModel):
    """시·구 평균 학생 수 (비교용)."""

    region_name: Annotated[
        str | None,
        Field(description='지역 이름 (서울시, 강남구 ...)', alias='regionName')
    ] = None
    count_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수', alias='countPerTeacher')
    ] = None
    count_per_classroom: Annotated[
        float | None,
        Field(description='학급당 학생 수', alias='countPerClassroom')
    ] = None


class NaverSchoolDetailModel(NaverBaseResponseModel):
    """학교 상세 (학교알리미 공시). 전화·홈페이지·좌표·학구도 경계(vertexes)도 오지만 쓰지 않는다."""

    school_code: Annotated[
        str,
        Field(description='학교 코드', alias='schoolCode')
    ]
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
        Field(description='관할 교육청', alias='officeOfEducationInCharge')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)', alias='operationType')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 형태 (단설, 병설 ...)', alias='establishmentType')
    ] = None
    establishment_date: Annotated[
        str | None,
        Field(description='개교일 (YYYY-MM-DD)', alias='establishmentDate')
    ] = None
    student: Annotated[
        NaverSchoolStudentModel | None,
        Field(description='학생 공시')
    ] = None
    city_student: Annotated[
        NaverRegionStudentModel | None,
        Field(description='시·도 평균', alias='cityStudent')
    ] = None
    division_student: Annotated[
        NaverRegionStudentModel | None,
        Field(description='시·군·구 평균', alias='divisionStudent')
    ] = None


class NaverSchoolAllocationDongsModel(NaverBaseResponseModel):
    """단지에서 그 학교에 배정되는 동."""

    is_all_building_assigned: Annotated[
        bool | None,
        Field(description='단지 전체 동이 배정되는지', alias='isAllBuildingAssigned')
    ] = None
    converted_building_name_groups: Annotated[
        list[list[str]] | None,
        Field(description='배정되는 동 이름 묶음. 사이트는 묶음마다 첫~끝 동으로 보여 준다 (101~105동). 서버가 null 로 줄 수 있어 모름이다', alias='convertedBuildingNameGroups')
    ] = None


class NaverSchoolComplexItemModel(NaverBaseResponseModel):
    """학교에 배정되는 단지 한 곳. 단지 정보·매물 수·호가 범위는 단지 목록(`legalDivisionComplexList`)의 항목과 같은 모양이다."""

    complex_info: Annotated[
        NaverComplexListInfoModel | None,
        Field(description='아파트·오피스텔 단지 정보. `villaInfo` 도 없는 항목은 단지 번호·이름을 알 수 없어 service 가 건너뛰고 `[제외]` 로 알린다', alias='complexInfo')
    ] = None
    villa_info: Annotated[
        NaverComplexListInfoModel | None,
        Field(
            description='빌라 단지 정보 (지역 단지 목록 `NaverComplexListEntryModel.villa_info` 와 같은 모양). 배정 빌라가 이 키로 오는지는 확인하지 못했다 '
            '(2026-11-18 인천일신초 E100000875: 배정 빌라 가람아트빌이 목록에 없었다). 미리 받아 둔다',
            alias='villaInfo'
        )
    ] = None
    article_count_info: Annotated[
        NaverComplexArticleCountModel | None,
        Field(description='거래 유형별 매물 수', alias='articleCountInfoDto')
    ] = None
    article_price_info: Annotated[
        NaverComplexArticlePriceModel | None,
        Field(description='호가 범위 (원). 매물이 없으면 빈 객체', alias='articlePriceInfoDto')
    ] = None
    is_all_building_assigned: Annotated[
        bool | None,
        Field(description='단지 전체 동이 그 학교에 배정되는지', alias='isAllBuildingAssigned')
    ] = None
    converted_building_name_groups: Annotated[
        list[list[str]] | None,
        Field(description='배정되는 동 이름 묶음 (`NaverSchoolAllocationDongsModel` 과 같다)', alias='convertedBuildingNameGroups')
    ] = None


class NaverSchoolComplexPageModel(NaverBaseResponseModel):
    """학교에 배정되는 단지 한 페이지.

    끝 쪽을 넘긴 페이지(예: page=9)는 `list: []`·`hasNextPage: false`·`totalCount: 0` 으로 온다 (2026-11-18 실측).
    총수는 첫 쪽에서만 믿는다. 세 칸은 서버가 null 로 줄 수 있어 모두 모름(None)을 받는다 (null 이라고 명령 전체가 깨지지 않게).
    """

    total_count: Annotated[
        int | None,
        Field(description='전체 단지 수. 첫 쪽에서만 믿는다. null 이면 모름', alias='totalCount')
    ] = None
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 존재 여부. null 이면 모름', alias='hasNextPage')
    ] = None
    items: Annotated[
        list[NaverSchoolComplexItemModel] | None,
        Field(description='단지. null 이면 이 쪽은 0곳으로 본다', alias='list')
    ] = None


class NaverEducationSchoolV1ResponseModel(NaverResponseModel[NaverSchoolDetailModel]):
    """`GET /front-api/v1/education/school` 응답."""


class NaverEducationComplexSchoolAllocationDongsV1ResponseModel(NaverResponseModel[NaverSchoolAllocationDongsModel]):
    """`GET /front-api/v1/education/complex/school/allocation-dongs` 응답."""


class NaverEducationComplexPagesV1ResponseModel(NaverResponseModel[NaverSchoolComplexPageModel]):
    """`GET /front-api/v1/education/complex/pages` 응답."""
