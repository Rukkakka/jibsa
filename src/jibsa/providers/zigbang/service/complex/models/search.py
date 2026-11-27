"""`search.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    Result,
)
from jibsa.providers.zigbang.service.complex.constants import (
    ZigbangComplexPlaceType,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


# 검색어가 가리키는 곳의 종류. `search complexes` 가 검색어 끝 글자로 가른다 (`query_place_kind`)
QueryPlaceKind = Literal['역', '학교', '동·구']


class ZigbangPlaceComplex(BaseModel):
    """역·학교·동·구 주변 아파트 단지 하나. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='주소. 역은 지번 주소, 학교·동·구는 직방 단지 카드의 구·동까지의 주소 (예: 송파구 가락동)')
    ]
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ]
    distance_km: Annotated[
        float | None,
        Field(description='역·학교에서의 거리 (km). 직방이 준 m 값(학교는 거리 문구 462m·1.1km 를 m 로 바꾼 값)을 km 로 바꿔 소수 둘째 자리까지. 동·구에는 키가 없다')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    highlight: Annotated[
        str | None,
        Field(
            description=(
                '웹 단지 카드 둘째 줄 글자 그대로. --order 마다 뜻이 다르다: 인기는 지역 순위 (예: 가락동 1위 · 송파구 1위), '
                "최근입주는 입주 시기 (예: '2026. 1 입주'), 시세급변동은 1주 시세 변동률 (예: -3.23%), 평당가는 평당가 "
                "(예: '14,758만 / 3.3㎡'). 카드를 받지 못했거나 직방이 주지 않으면 모름(null)"
            )
        )
    ]
    has_distance: Annotated[
        bool,
        Field(exclude=True, description='거리가 있는 곳(역·학교)의 단지인지. 동·구는 해당 없어 출력에서 distance_km 키를 뺀다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.has_distance:
            data.pop('distance_km', None)
        return data


class ZigbangMiddleAdvancement(BaseModel):
    """중학교의 고등학교 진학 현황 (웹 학교 화면 '고등학교 진학 현황': 특목고·일반고·기타)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    special_high: Annotated[
        int | float | None,
        Field(description='특목고 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    special_high_percent: Annotated[
        int | float | None,
        Field(description='특목고 진학 비율 (%). 직방이 주지 않으면 null')
    ]
    general_high: Annotated[
        int | float | None,
        Field(description='일반고 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    general_high_percent: Annotated[
        int | float | None,
        Field(description='일반고 진학 비율 (%). 직방이 주지 않으면 null')
    ]
    other: Annotated[
        int | float | None,
        Field(description='기타 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    other_percent: Annotated[
        int | float | None,
        Field(description='기타 진학 비율 (%). 직방이 주지 않으면 null')
    ]


class ZigbangHighAdvancement(BaseModel):
    """고등학교의 대학 진학 현황 (웹 학교 화면 '대학교 진학 현황': 일반대·전문대·기타)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    university: Annotated[
        int | float | None,
        Field(description='일반대 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    university_percent: Annotated[
        int | float | None,
        Field(description='일반대 진학 비율 (%). 직방이 주지 않으면 null')
    ]
    college: Annotated[
        int | float | None,
        Field(description='전문대 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    college_percent: Annotated[
        int | float | None,
        Field(description='전문대 진학 비율 (%). 직방이 주지 않으면 null')
    ]
    other: Annotated[
        int | float | None,
        Field(description='기타 진학 인원 (명). 직방이 주지 않으면 null')
    ]
    other_percent: Annotated[
        int | float | None,
        Field(description='기타 진학 비율 (%). 직방이 주지 않으면 null')
    ]


class ZigbangSchoolInfo(BaseModel):
    """학교 정보 (직방 웹 학교 화면 `/home/apt/schools/{학교코드}`, 출처 학교알리미·학구도안내서비스). 전화·홈페이지·주소·좌표는 담지 않는다.

    `sigungu_` 로 시작하는 값은 웹이 '{구} 평균' 으로 보여 주는 같은 구 학교 평균이다. 웹은 값이 없거나 0 인 칸을 숨기지만 여기서는 없으면
    null, 0 은 0 으로 낸다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    stage: Annotated[
        str | None,
        Field(exclude=True, description='직방 학교급 원문 (elementary·middle·high). 학교급에 해당하지 않는 키를 빼는 데 쓰고 출력하지 않는다')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ]
    level: Annotated[
        str | None,
        Field(description="학교급 ('초등학교'·'중학교'·'고등학교'). 직방이 모르는 값을 주면 그 원문 그대로, 주지 않으면 null")
    ]
    founding_type: Annotated[
        str | None,
        Field(description="설립 구분 (직방 글자 그대로, 예: '공립')")
    ]
    gender: Annotated[
        str | None,
        Field(description="남녀 구분 (직방 글자 그대로, 예: '공학')")
    ]
    established_date: Annotated[
        str | None,
        Field(description='설립일 (YYYY-MM-DD). 직방이 주지 않으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    high_school_type: Annotated[
        str | None,
        Field(description="고등학교 구분 (직방 글자 그대로, 예: '일반고'). 고등학교만 있고 다른 학교는 키가 없다. 직방이 주지 않으면 null")
    ]
    students: Annotated[
        int | float | None,
        Field(description='전체 학생 수 (명)')
    ]
    male_percent: Annotated[
        int | float | None,
        Field(description='남학생 비율 (%)')
    ]
    female_percent: Annotated[
        int | float | None,
        Field(description='여학생 비율 (%)')
    ]
    sigungu: Annotated[
        str | None,
        Field(description="같은 구 평균의 구 (직방 학교 정보의 구, 예: '송파구'). 직방이 주지 않으면 null")
    ]
    sigungu_students_average: Annotated[
        int | float | None,
        Field(description='같은 구 학교의 평균 학생 수 (명). 직방이 소수로 준 그대로 (웹은 반올림해 보여 준다)')
    ]
    sigungu_male_percent: Annotated[
        int | float | None,
        Field(description='같은 구 평균 남학생 비율 (%)')
    ]
    sigungu_female_percent: Annotated[
        int | float | None,
        Field(description='같은 구 평균 여학생 비율 (%)')
    ]
    freshmen: Annotated[
        int | float | None,
        Field(description='입학생 수 (명)')
    ]
    sigungu_freshmen_average: Annotated[
        int | float | None,
        Field(description='같은 구 학교의 평균 입학생 수 (명)')
    ]
    sigungu_freshmen_change_percent: Annotated[
        int | float | None,
        Field(description='같은 구 평균 입학생의 전년 대비 증감 (%, 음수는 감소, 0 은 변화 없음). 웹 입학생 칸의 (전년대비 N% 감소)')
    ]
    students_per_class: Annotated[
        int | float | None,
        Field(description='학급당 학생 수 (명)')
    ]
    sigungu_students_per_class: Annotated[
        int | float | None,
        Field(description='같은 구 평균 학급당 학생 수 (명)')
    ]
    tuition_manwon: Annotated[
        int | float | None,
        Field(
            description=(
                '학비 (만원). 직방이 원 단위로 준 값을 만원으로 바꾼 그대로라 웹이 만원 미만을 버려 보여 주는 값(예: 78만원)과 소수 자리가 다르다. '
                '연간인지 월인지는 웹도 적지 않아 모른다'
            )
        )
    ]
    sigungu_tuition_manwon: Annotated[
        int | float | None,
        Field(description='같은 구 평균 학비 (만원)')
    ]
    meal_cost_manwon: Annotated[
        int | float | None,
        Field(description='급식비 (만원, 원 단위 값을 환산). 1식인지 기간 합인지는 웹도 적지 않아 모른다')
    ]
    meal_type: Annotated[
        str | None,
        Field(description="급식 방식 (직방 글자 그대로, 예: '직영'·'일부위탁')")
    ]
    sigungu_meal_cost_manwon: Annotated[
        int | float | None,
        Field(description='같은 구 평균 급식비 (만원)')
    ]
    advancement: Annotated[
        ZigbangMiddleAdvancement | ZigbangHighAdvancement | None,
        Field(
            description=(
                '진학 현황. 중학교는 고등학교 진학(special_high·general_high·other), 고등학교는 대학 진학(university·college·other)이고 '
                '초등학교는 키가 없다. 칸이 모두 비면 null (직방이 아직 채우지 않은 학교가 많다)'
            )
        )
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 웹 학교 화면은 초등학교에 진학 현황이 없고 고등학교 구분은 고등학교에만 있다. 학교급을 모르면 해당 여부를 몰라 키를 둔다 (null)
        if self.stage == 'elementary':
            data.pop('advancement', None)
        if self.stage in ('elementary', 'middle'):
            data.pop('high_school_type', None)
        return data


class ZigbangPlaceComplexesResult(Result):
    """역·학교·동·구 주변 아파트 단지 목록 (직방 웹 목록 --order 탭의 단지와 순서).

    `notes`: 어느 웹 목록인지·일부만 보여 준다는 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    place: Annotated[
        str,
        Field(description='찾은 역·학교·동·구 이름')
    ]
    place_type: Annotated[
        ZigbangComplexPlaceType,
        Field(description="찾은 곳의 종류. 시·군은 '구', 리는 상위 읍·면이라 '동' 이다")
    ]
    place_address: Annotated[
        str | None,
        Field(description='찾은 곳의 주소')
    ] = None
    total: Annotated[
        int | None,
        Field(
            description=(
                '고른 목록(--order)의 단지 수 (limit 적용 전). 역은 역에서 1.5km 안이다. 최근입주·시세급변동은 그 조건에 든 단지만 담아 '
                '그 곳의 전체 단지 수가 아니다. 직방이 주지 않으면 모름(null)'
            )
        )
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='받지 않은 단지가 남았는지 (이어 받기는 없다. --limit 으로). 직방이 --limit 보다 적게 줬으면 단지 수가 더 커도 false')
    ]
    complexes: Annotated[
        list[ZigbangPlaceComplex],
        Field(description='직방 웹 목록(--order 탭)의 단지. 그 탭의 순서 그대로다')
    ]
    school: Annotated[
        ZigbangSchoolInfo | None,
        Field(description='학교 정보 (직방 웹 학교 화면). 학교가 아닌 곳에는 키가 없다')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.place_type != '학교':
            data.pop('school', None)
        return data
