"""학교 상세와 배정 동 (school)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    normalize_address,
    normalize_date,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.school import (
    NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel,
    NaverEducationSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.school import NaverRegionStudentModel
from jibsa.providers.naver.service.common import (
    dong_label,
    result_or_none,
    unwrap,
    villa_by_complex_response,
)

from typing import (
    Annotated,
    Any,
)


def _is_villa_complex(client: NaverClient, complex_number: int) -> bool:
    """단지 종류를 모를 때 아파트 단지 정보를 1회 물어 빌라 단지인지 정한다 (`villa_by_complex_response`)."""
    return villa_by_complex_response(
        client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number))
    )


class NaverSchoolRegionAverage(BaseModel):
    """시·도 또는 시·군·구 평균 (학교와 비교용)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='지역 (서울시, 강남구 ...)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None


class NaverSchoolDetail(BaseModel):
    """초등학교 상세 (학교알리미 공시 기준). 전화·홈페이지·좌표·학구도 경계는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    office_of_education: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 형태 (단설, 병설 ...)')
    ] = None
    opened_at: Annotated[
        str | None,
        Field(description='개교일 (YYYY-MM-DD)')
    ] = None
    stats_date: Annotated[
        str | None,
        Field(description='학생 수 공시 기준일 (YYYY-MM-DD)')
    ] = None
    students: Annotated[
        int | None,
        Field(description='전체 학생 수')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    city_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·도 평균')
    ] = None
    district_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·군·구 평균')
    ] = None
    complex_number: Annotated[
        int | None,
        Field(description='--complex 로 준 단지 번호. 주지 않았으면 키가 없다')
    ] = None
    all_dongs_assigned: Annotated[
        bool | None,
        Field(description='그 단지 전체 동이 이 학교에 배정되는지. --complex 를 주지 않았으면 키가 없고, 조회 실패면 null')
    ] = None
    assigned_dongs: Annotated[
        list[str] | None,
        Field(description="그 단지에서 이 학교에 배정되는 동 (예: '101동~105동'). 전체 배정이면 ['전체 동']. --complex 를 주지 않았으면 키가 없고, 조회 실패이거나 일부 동만 배정인데 어느 동인지 네이버가 주지 않으면 null")
    ] = None
    url: Annotated[
        str,
        Field(description='학교 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_number is None:
            for field in ('complex_number', 'all_dongs_assigned', 'assigned_dongs'):
                data.pop(field, None)
        return data


def school_url(school_code: str) -> str:
    return f'https://fin.land.naver.com/schools/elementary/{school_code}'


def _dong_group_label(names: list[str]) -> str:
    """사이트처럼 묶음의 첫~끝 동으로 ('101', '105' → '101동~105동'). 건물 이름('가람아트빌라')에는 '동' 을 붙이지 않는다."""
    def with_dong(name: str) -> str:
        return name if name.endswith('동') else dong_label(name)
    return with_dong(names[0]) if len(names) == 1 else f'{with_dong(names[0])}~{with_dong(names[-1])}'


def get_school(
    client: NaverClient,
    school_code: str,
    *,
    complex_number: int | None = None,
    villa: bool | None = None,
) -> NaverSchoolDetail:
    """초등학교 상세 (1회 호출). 단지를 주면 그 단지에서 이 학교에 배정되는 동을 붙인다 (1~3회 추가).

    Args:
        complex_number: 단지 번호. 주면 배정 동을 묻는다.
        villa: 단지형 빌라인지. 모르면(None) 단지 정보를 1회 더 물어 정하고, 빌라면 빌라 단지가 있는지 1회 더 묻는다
            (빌라 단지는 villa 로 물어야 한다).

    Raises:
        JibsaError: 없는 학교 코드나 없는 단지 번호면 NOT_FOUND.
    """
    school = unwrap(
        client.run_request_education_school_v1(NaverEducationSchoolV1RequestParameterModel(school_code=school_code)),
        '학교',
    )
    all_assigned: bool | None = None
    assigned: list[str] | None = None
    if complex_number is not None:
        if villa is None:
            # 배정 동은 빌라 단지를 complex 로 물어도 villa 로 물어도 false·[] 라 (가람아트빌 673573 ↔ E100000875,
            # 2026-10-11) 평형 확인처럼 응답을 보고 나중에 정할 수 없어 단지 종류를 먼저 정한다
            villa = _is_villa_complex(client, complex_number)
            # 없는 단지 번호도 아파트 단지 정보가 빈 결과라 빌라로 보이고, 배정 동은 배정 안 된 단지와 같은
            # false·[] 로 와서 구분되지 않는다 (99999999 ↔ 헬리오시티 111515, 2026-10-11). 빌라 단지 정보로 확인한다
            if villa:
                unwrap(
                    client.run_request_complex_villa_v1(NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)),
                    '단지',
                )
        allocation = result_or_none(lambda: client.run_request_education_complex_school_allocation_dongs_v1(
            NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel(
                complex_number=complex_number, school_code=school_code, item_type='villa' if villa else 'complex',
            )
        ))
        if allocation is not None:
            all_assigned = allocation.is_all_building_assigned
            groups = [group for group in allocation.converted_building_name_groups if group]
            # 전체 배정이 아닌데 동 목록이 비어 오면 어느 동인지 모른다. 일부 동만 배정된 단지(가람아트빌 673573, 2026-10-10)와
            # 배정 안 된 단지(헬리오시티 111515 ↔ B100000747, 2026-10-11)가 같은 모양이다. [] 는 '배정 동 없음' 으로 읽혀 None
            assigned = ['전체 동'] if all_assigned else ([_dong_group_label(group) for group in groups] if groups else None)
    student = school.student

    def average(region: NaverRegionStudentModel | None) -> NaverSchoolRegionAverage | None:
        if region is None:
            return None
        return NaverSchoolRegionAverage(
            region=region.region_name,
            students_per_class=region.count_per_classroom,
            students_per_teacher=region.count_per_teacher,
        )

    return NaverSchoolDetail(
        school_code=school.school_code,
        name=school.name,
        address=normalize_address(school.address) if school.address else None,
        office_of_education=school.office_of_education_in_charge,
        operation_type=school.operation_type,
        establishment_type=school.establishment_type,
        opened_at=normalize_date(school.establishment_date),
        stats_date=normalize_date(student.base_date) if student else None,
        students=student.total_count if student else None,
        students_per_class=student.count_per_classroom if student else None,
        students_per_teacher=student.count_per_teacher if student else None,
        city_average=average(school.city_student),
        district_average=average(school.division_student),
        complex_number=complex_number,
        all_dongs_assigned=all_assigned,
        assigned_dongs=assigned,
        url=school_url(school.school_code),
    )
