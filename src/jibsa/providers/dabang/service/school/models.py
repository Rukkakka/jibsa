"""학교·유치원·어린이집의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import Result
from jibsa.providers.dabang.service.common.functions import (
    ChildcareLevel,
    EducationLevel,
    SchoolLevel,
)
from jibsa.providers.dabang.service.common.models import DabangPlace

from typing import (
    Annotated,
    Any,
)


class DabangSchoolAverage(BaseModel):
    """지역 평균 (비교용)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='지역 (서울특별시, 강남구 ...)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    afterschool_programs: Annotated[
        float | None,
        Field(description='방과후 프로그램 수')
    ] = None


class DabangAdvancement(BaseModel):
    """진학 한 갈래."""

    model_config = ConfigDict(
        extra='forbid',
    )

    destination: Annotated[
        str,
        Field(description=(
            '진학 갈래. 중학교: 일반고·특성화고·특목고·자율고, 그 안의 과학고·외국어고·예술체육고(특목고)·자사고(자율고). '
            '고등학교: 대학교·전문대학·국외·취업·기타'
        ))
    ]
    count: Annotated[
        int | None,
        Field(description='인원 (명). 특목고·자율고 안의 갈래는 다방이 비율만 줘서 null')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='졸업생 중 비율 (%)')
    ] = None


class DabangSchoolDetail(Result):
    """학교 하나의 학교알리미 공시 (다방 제공). 진학은 중·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드')
    ]
    level: Annotated[
        SchoolLevel,
        Field(description='초등학교 / 중학교 / 고등학교')
    ]
    name: Annotated[
        str,
        Field(description='학교 이름')
    ]
    establishment: Annotated[
        str | None,
        Field(description='설립 (국공립, 사립)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    office_of_education: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = None
    base_period: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기')")
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    afterschool_programs: Annotated[
        float | None,
        Field(description='방과후 프로그램 수 (초등학교는 대개 null)')
    ] = None
    sido_average: Annotated[
        DabangSchoolAverage,
        Field(description='시·도 평균')
    ]
    sigungu_average: Annotated[
        DabangSchoolAverage,
        Field(description='시·군·구 평균')
    ]
    advancement: Annotated[
        list[DabangAdvancement] | None,
        Field(description='졸업생 진학 (중·고등학교). 초등학교는 키가 없다')
    ] = None
    disclosure_url: Annotated[
        str | None,
        Field(description='학교알리미 공시 페이지 URL')
    ] = None

    @model_serializer(mode='wrap')
    def drop_elementary_advancement(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level == '초등학교':
            data.pop('advancement', None)
        return data


class DabangChildGroup(BaseModel):
    """원아 구성 한 칸 (어린이집은 반, 유치원은 나이)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    group: Annotated[
        str,
        Field(description="반·나이 (어린이집 '0세반'~'5세반'·'영아 혼합'·'유아 혼합'·'영유아 혼합'·'특수/장애아', 유치원 '만 3세'·'만 4세'·'만 5세 이상'·'혼합')")
    ]
    count: Annotated[
        int,
        Field(description='원아 수 (명)')
    ]
    percent: Annotated[
        float | None,
        Field(description='전체 원아 중 비율 (%)')
    ] = None


class DabangTeacherGrade(BaseModel):
    """교사 급수·자격 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    grade: Annotated[
        str,
        Field(description="급수·자격 (어린이집 '1급'·'2급'·'3급', 유치원 '수석교사'·'정교사 1급'·'정교사 2급'·'준교사')")
    ]
    count: Annotated[
        int | None,
        Field(description='교사 수 (명)')
    ] = None


class DabangChildcareDetail(Result):
    """유치원·어린이집 하나의 공시 (다방 제공: 유치원알리미·어린이집정보공개포털). 다방 웹 상세 화면이 그리는 값이다.

    어린이집에만 `school_bus`, 유치원에만 `school_bus_vehicles`·`homepage_url` 키가 있다. 유치원 교육비는 다방 값이 유치원알리미
    공시의 학부모 부담금과 맞지 않아 내지 않는다 (원비는 `disclosure_url` 의 '비용·회계' 에서 본다).
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='시설 코드 (complex 결과 nurseries[]·kindergartens[] 의 school_code, search schools 결과의 school_code)')
    ]
    level: Annotated[
        ChildcareLevel,
        Field(description='유치원 / 어린이집')
    ]
    name: Annotated[
        str,
        Field(description='이름')
    ]
    establishment: Annotated[
        str | None,
        Field(description="설립 유형 (어린이집 '공공'·'민간'·'가정'·'직장'·'협동', 유치원 '국공립'·'사립')")
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    base_period: Annotated[
        str | None,
        Field(description="공시 기준 ('2026년 상반기')")
    ] = None
    operating_hours: Annotated[
        str | None,
        Field(description="운영 시간 (다방 글 그대로: 어린이집 '평일기준시간 : 07:30 ~ 19:30', 유치원 '09시00분~13시30분')")
    ] = None
    school_bus: Annotated[
        str | None,
        Field(description="통학버스 ('운영', '미운영', 어린이집)")
    ] = None
    school_bus_vehicles: Annotated[
        int | None,
        Field(description="통학 차량 수 (대, 유치원. 유치원알리미 '통학차량 현황'의 운행 차량수라 0 은 통학차량을 운영하지 않는 것이다. 다방 웹은 0 을 '-' 로 쓴다)")
    ] = None
    homepage_url: Annotated[
        str | None,
        Field(description='홈페이지 (유치원)')
    ] = None
    children_total: Annotated[
        int | None,
        Field(description='원아 수 (명. 어린이집은 반별 원아 수의 합, 유치원은 현원)')
    ] = None
    children: Annotated[
        list[DabangChildGroup] | None,
        Field(description='원아 구성 (원아가 있는 반·나이만, 다방 웹과 같다). 다방이 반·나이별 수를 하나도 주지 않으면 null')
    ] = None
    teachers: Annotated[
        list[DabangTeacherGrade],
        Field(description='교사 급수·자격별 수')
    ] = []
    children_per_teacher: Annotated[
        float | None,
        Field(description='교사 1명당 아동 수')
    ] = None
    services: Annotated[
        list[str] | None,
        Field(description="제공 서비스 (어린이집 '야간연장형'·'일반', 유치원 '방과후 과정' 등). 다방이 주지 않으면 null")
    ] = None
    disclosure_url: Annotated[
        str | None,
        Field(description="공시 페이지 URL (어린이집정보공개포털·유치원알리미). 유치원 원비는 이 페이지의 '비용·회계' 에서 본다")
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_level_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level == '어린이집':
            for key in ('school_bus_vehicles', 'homepage_url'):
                data.pop(key, None)
        else:
            data.pop('school_bus', None)
        return data


class DabangRegionalAdvancement(BaseModel):
    """동 안 학교 목록의 진학률 한 갈래 (중·고등학교)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    destination: Annotated[
        str | None,
        Field(description="갈래 (다방 이름 그대로: 중학교 '과고'·'외고'·'자사고'·'예고' 등)")
    ] = None
    percent: Annotated[
        float | None,
        Field(description='진학률 (%)')
    ] = None


class DabangRegionalSchool(BaseModel):
    """동 안 학교·유치원·어린이집 하나. 진학률은 중·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드. jibsa dabang school <school_code> --level <level> 로 상세를 본다')
    ]
    level: Annotated[
        EducationLevel,
        Field(description='초등학교 / 중학교 / 고등학교 / 유치원 / 어린이집. school 명령의 --level 값')
    ]
    name: Annotated[
        str | None,
        Field(description='이름')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description="설립 구분 (학교·유치원 '국공립'·'사립', 어린이집 '공공'·'민간'·'가정'·'직장'·'협동'). 모르는 값이면 null")
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    advancement: Annotated[
        list[DabangRegionalAdvancement] | None,
        Field(description='진학률 (중·고등학교, 다방 웹 목록의 꼬리표). 다방이 주지 않으면 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_levels(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level not in ('중학교', '고등학교'):
            data.pop('advancement', None)
        return data


class DabangSchoolListResult(Result):
    """동 안 학교·유치원·어린이집 목록 (다방 동네정보 '학군' 상세 목록, 다방 목록 순).

    `notes`: 일부만 받은 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 동')
    ]
    level: Annotated[
        EducationLevel,
        Field(description='단계')
    ]
    establishment: Annotated[
        str,
        Field(description="고른 설립 구분 (--establishment). 주지 않았으면 '전체'")
    ]
    total: Annotated[
        int | None,
        Field(description='그 동의 그 단계 전체 수 (설립 구분 적용 뒤)')
    ] = None
    returned: Annotated[
        int,
        Field(description='돌려준 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='다방에 더 있는지')
    ]
    schools: Annotated[
        list[DabangRegionalSchool],
        Field(description='학교 (다방 목록 순)')
    ]
