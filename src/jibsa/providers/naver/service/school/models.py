"""학교 상세와 배정 동·배정 단지의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.naver.service.common.functions import (
    ASKING_RANGES_DESCRIPTION,
)

from typing import (
    Annotated,
    Any,
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


class NaverSchoolDetail(Result):
    """초등학교 상세 (학교알리미 공시 기준). 전화·홈페이지·좌표·학구도 경계는 담지 않는다.

    `notes`: 덤 조회가 실패한 [실패] 안내 등. CLI 가 결과 위에 붙인다
    """

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
    opened_date: Annotated[
        str | None,
        Field(description='개교일 (YYYY-MM-DD)')
    ] = None
    base_date: Annotated[
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
    sido_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·도 평균')
    ] = None
    sigungu_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·군·구 평균')
    ] = None
    complex_id: Annotated[
        int | None,
        Field(description='--complex 로 준 단지 번호. 주지 않았으면 키가 없다')
    ] = None
    all_dongs_assigned: Annotated[
        bool | None,
        Field(description='그 단지 전체 동이 이 학교에 배정되는지. --complex 를 주지 않았으면 키가 없고, 조회 실패면 null')
    ] = None
    assigned_dongs: Annotated[
        list[str] | None,
        Field(description="그 단지에서 이 학교에 배정되는 동 (예: '101동~105동'). 전체 배정이면 ['전체 동']. --complex 를 주지 않았으면 키가 없고, 조회 실패이거나 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지(동 묶음) 주지 않으면 null (일부 동만 배정된 단지와 배정되지 않은 단지가 같은 모양이다)")
    ] = None
    url: Annotated[
        str,
        Field(description='학교 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_id is None:
            for field in ('complex_id', 'all_dongs_assigned', 'assigned_dongs'):
                data.pop(field, None)
        return data


class NaverSchoolComplex(BaseModel):
    """학교에 배정되는 단지 한 곳. 좌표·주소·사진은 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호 (naver complex / school --complex / real-price 에 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 빌라 ...). 표에 없는 유형 코드는 코드 그대로')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    listing_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수. 서버가 매물 수를 주지 않으면 null (모름)')
    ] = None
    asking_ranges: Annotated[
        dict[str, AmountRange] | None,
        Field(description=ASKING_RANGES_DESCRIPTION)
    ] = None
    assigned_dongs: Annotated[
        list[str] | None,
        Field(description="이 학교에 배정되는 동 (예: '101동~105동'). 단지 전체가 배정이면 ['전체 동']. 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지(동 묶음) 주지 않으면 null")
    ] = None


class NaverSchoolComplexesResult(Result):
    """학교에 배정되는 단지 목록.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int | None,
        Field(description='학교에 배정되는 전체 단지 수 (서버 집계, limit 적용 전). 네이버가 주지 않으면 null (모름)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool | None,
        Field(description='네이버 목록에 아직 받지 않은 단지가 남았는지. 네이버가 다음 쪽이 있는지 주지 않으면 첫 쪽 총수와 받은 수로 정하고, 총수도 모르고 받은 것이 limit 안이면 null (모름)')
    ]
    complexes: Annotated[
        list[NaverSchoolComplex],
        Field(description='단지 (선택한 정렬 순서. 거리순은 학교에서 가까운 순)')
    ]
