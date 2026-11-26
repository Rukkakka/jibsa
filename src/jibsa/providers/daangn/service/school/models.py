"""학교·어린이집의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.daangn.service.common.models import DaangnRegionComplex

from typing import Annotated


class DaangnSchool(BaseModel):
    """학교 정보 (학교알리미 공시 기준). 전화·홈페이지·좌표는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='당근 학교 코드 (school 에 다시 넘길 수 있다)')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    school_type: Annotated[
        str | None,
        Field(description='초등학교 / 중학교 / 고등학교 / 기타')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    foundation: Annotated[
        str | None,
        Field(description='설립 구분 (공립, 사립 ...)')
    ] = None
    coed: Annotated[
        str | None,
        Field(description='남녀공학 / 남학교 / 여학교')
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
    base_year: Annotated[
        int | None,
        Field(description='학생 수 기준 연도 (예: 2026). 당근이 주지 않으면 null')
    ] = None


class DaangnSchoolResult(Result):
    """학교 정보와 배정 단지.

    `notes`: 배정 단지 안내 (중·고등학교, 정보 없음, 조건·limit 으로 줄임, 조건을 확인할 수 없어 뺀 단지). CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    school: Annotated[
        DaangnSchool,
        Field(description='학교')
    ]
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 배정 단지 수 (limit 적용 전. 당근이 단지 ID 를 주지 않아 complexes 에서 뺀 단지도 센다). 당근이 배정 단지를 주지 않았거나 빈 항목을 줬거나, 단지 유형·세대수를 몰라 조건을 확인할 수 없는 단지가 있으면 null (모름)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex] | None,
        Field(description='배정 단지 (당근 웹 학교 화면과 같은 순서). recent_trades 는 최근 매매 1건이다. 배정 단지가 없으면 [], 당근이 배정 단지를 주지 않았으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 학교 페이지')
    ]


class DaangnPreschoolSummary(BaseModel):
    """단지 근처 어린이집·유치원 하나 (목록). 어린이집·유치원 구분은 목록에 없어 preschool 상세에서 본다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    preschool_id: Annotated[
        str,
        Field(description='시설 번호 (preschool 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선거리 (m, 웹과 같은 반올림). 단지나 시설 좌표가 없으면 null')
    ] = None
    resident_count: Annotated[
        int | None,
        Field(description='이 단지 주민 중 다니는 수 (당근 집계)')
    ] = None
    review_count: Annotated[
        int,
        Field(description='당근 설문 후기 수')
    ]


class DaangnPreschoolsResult(Result):
    """단지 근처 어린이집·유치원 목록 (당근 단지 화면 학군의 유치원 탭).

    `notes`: 정보 없음·빈 결과·20곳 한도 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 시설 수. 당근은 단지에서 1km 안을 가까운 순으로 20곳까지 준다')
    ]
    preschools: Annotated[
        list[DaangnPreschoolSummary] | None,
        Field(description='이 단지 주민이 많이 다니는 순, 같으면 가까운 순 시설. 당근이 근처 시설 정보를 주지 않으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지 (학군에 같은 목록이 있다)')
    ]


class DaangnPreschool(Result):
    """어린이집·유치원 상세. 전화번호·홈페이지는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    preschool_id: Annotated[str, Field(description='시설 번호')]
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='어린이집 / 유치원')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    region: Annotated[
        str | None,
        Field(description='구·동 (예: 강남구 역삼동)')
    ] = None
    operating_hours: Annotated[
        str | None,
        Field(description='운영 시간')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 유형 (국공립·민간·직장 등)')
    ] = None
    established_date: Annotated[
        str | None,
        Field(description="설립일 (YYYY-MM-DD, 당근이 '-' 로 비운 값은 null, 날짜로 읽지 못하면 null ([참고] 안내))")
    ] = None
    opened_date: Annotated[
        str | None,
        Field(description="개원일 (YYYY-MM-DD, 당근이 '-' 로 비운 값은 null, 날짜로 읽지 못하면 null ([참고] 안내))")
    ] = None
    authority: Annotated[
        str | None,
        Field(description='관할 기관')
    ] = None
    capacity: Annotated[
        int | None,
        Field(description='정원 (명). 지금 다니는 원아 수가 아니다')
    ] = None
    classes: Annotated[
        int | None,
        Field(description='학급 수')
    ] = None
    teachers: Annotated[
        int | None,
        Field(description='교사 수')
    ] = None
    has_school_bus: Annotated[
        bool | None,
        Field(description='통학버스 운영')
    ] = None
    survey_responses: Annotated[
        int,
        Field(description="당근 학부모 설문 응답 수 (웹 어린이집 화면의 '후기 N'). 설문이 없으면 0")
    ] = 0
