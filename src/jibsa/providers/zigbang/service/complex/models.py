"""직방 service 단지의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Listing,
    NumberRange,
    Result,
)
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice

from typing import (
    Annotated,
    Any,
    Literal,
)


# 단지 정보에서 한쪽 유형에만 있는 필드. 다른 유형은 출력에서 키를 뺀다
APT_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({
    'dong_count', 'approved_date', 'construction_company', 'parking_per_household',
    'floor_area_ratio_percent', 'heating', 'listing_counts', 'pyeongs', 'review_count', 'schools',
    'estimated_ranges', 'estimated_prices', 'ranking', 'related_complexes', 'land_trade_permits',
})
OFFICETEL_ONLY_COMPLEX_FIELDS: frozenset[str] = frozenset({'completed_month', 'has_elevator'})

ZigbangComplexPlaceType = Literal['역', '학교', '동', '구']

ZigbangPriceTrendPeriod = Literal['1년', '3년', '전체']
ZigbangPyeongTrendTrade = Literal['전체', '매매', '전월세']

ZigbangPriceLineKind = Literal['단지', '비교 단지', '구']


class ZigbangRelatedComplex(BaseModel):
    """직방이 단지끼리 이어 주는 단지 하나: 웹 단지 화면의 '함께 보면 좋은 단지', 직방시세 그래프 '단지 비교하기' 의 후보 ('단지 선택' 창)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (zigbang complex·search listings --complex 에 넘긴다). 직방이 ID 를 주지 않으면 모름(null)')
    ]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ]
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ]


class ZigbangComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·items 에 넘긴다)')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='단지가 있는 동까지의 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None


class ZigbangPyeong(BaseModel):
    """아파트 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (zigbang search listings --complex --pyeong 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 ㎡ 기준, 예: 111A)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 평 기준, 예: 34A)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 직방 평형 정보를 받지 못했거나 그 평형이 없으면 모름(null)')
    ] = None
    supply_area_pyeong: Annotated[
        float | None,
        Field(description='공급면적 (평). 직방이 준 값 그대로')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평). 직방이 준 값 그대로')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='그 평형의 세대수 (웹 평형 이름 옆 괄호, 예: 107A㎡ (731세대))')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    entrance: Annotated[
        str | None,
        Field(description="현관 구조 (직방 글자 그대로, 예: '계단식'·'복도식'). 직방이 주지 않으면 null")
    ] = None
    manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='평균 월 관리비 (만원, 직방 정수 그대로). 웹 안내: K-apt 최소 3개월~최대 24개월 평균. 0 이거나 직방이 주지 않으면 null (웹은 이때 관리비 줄을 숨긴다)')
    ] = None
    summer_manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='여름(6~8월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    winter_manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='겨울(12~2월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    resale_available_date: Annotated[
        str | None,
        Field(description='전매제한이 풀려 매매할 수 있는 날 (직방 거래가능시점, YYYY-MM-DD). 이미 지난 날도 그대로 낸다 (웹은 오늘 뒤일 때만 안내). 직방이 주지 않으면 null')
    ] = None
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description=(
            "직방시세 (실거래를 머신러닝으로 분석한 직방 추정값이고 실거래 평균이 아니다). 늘 'sale'·'jeonse' 두 키이고, sale 은 price_manwon"
            '(직방 시세 범위의 최저값. 2026-11-19 표본 30개 평형은 최저 = 최고)·price_per_pyeong_manwon, jeonse 는 deposit_manwon·'
            'price_per_pyeong_manwon (만원, 평당가는 3.3㎡당 공급면적 평 기준). 그 거래의 안 칸이 모두 0 이거나 없으면 그 거래가 null (웹 시세없음), 일부만 그러면 그 칸만 null'
        ))
    ]


class ZigbangComplexRank(BaseModel):
    """단지 순위. 직방 웹 단지 화면의 '<동>에서 이 단지의 랭킹은?' 절."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='웹 제목 속 동 이름 (예: 가락동)')
    ]
    price_rank: Annotated[
        int | None,
        Field(description="웹 '시세 N위' 의 N (직방은 실거래가 순위로 준다). 순위 없음이면 null")
    ]
    popularity_rank: Annotated[
        int | None,
        Field(description="웹 '인기순 N위' 의 N (직방은 조회수 순위로 준다). 순위 없음이면 null")
    ]


class ZigbangLandTradePermitDay(BaseModel):
    """토지거래허가 일별 건수 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str | None,
        Field(description='날짜 (YYYY-MM-DD). 직방이 준 날짜를 읽지 못하면 모름(null, [참고] 안내)')
    ]
    count: Annotated[
        int | None,
        Field(description='그날의 토지거래허가 건수. 직방이 주지 않으면 모름(null)')
    ]


class ZigbangComplex(Result):
    """직방 단지 정보. 아파트와 오피스텔 건물은 직방이 주는 정보가 달라 한쪽에만 있는 필드는 키를 뺀다.

    `notes`: 후기가 있다는 안내와, 학군·평형 정보를 받지 못해 그 값을 모른다는 [실패] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소 (오피스텔은 동까지)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 층수 범위. 직방은 최고 층수만 주어 lowest 는 늘 null(모름)이고 highest 가 최고 층수다 (오피스텔은 건물 층수). 직방이 최고 층수를 주지 않으면 null')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수 (아파트만)')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 아파트만)')
    ] = None
    completed_month: Annotated[
        str | None,
        Field(description='준공 연월 (YYYY-MM, 오피스텔만). 읽지 못하면 null ([참고] 안내)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사 (아파트만)')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수 (아파트만)')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%, 아파트만)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (아파트만)')
    ] = None
    has_elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 (오피스텔만). 있다고 확인되면 true, 그 밖에는 모름(null). 매물 상세의 has_elevator 가 정확하다')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수. 아파트는 같은 호·거래 유형을 묶은 수. 직방이 주지 않으면 모름(null)')
    ]
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='거래 유형별 매물 수 (아파트만). 직방이 주지 않은 유형은 모름(null)')
    ] = {}
    pyeongs: Annotated[
        list[ZigbangPyeong] | None,
        Field(description='평형 목록 (아파트만). 평형이 아직 없는 단지는 [], 직방이 평형 목록을 주지 않았으면 null')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 학교군 안 가까운 중·고등학교 2곳씩 (아파트만, 예: 서울개원초등학교 (배정, 180m)). 모르면 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수 (아파트만). 후기 내용은 url 의 직방 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    estimated_ranges: Annotated[
        dict[str, AmountRange | None],
        Field(description=(
            "단지 직방시세 범위 (아파트만). 'sale' 키 하나이고 lowest·highest 는 price_manwon (만원). 웹 전체 탭 \"매매 18억 8,000 ~ 61억 1,000\" 의 앞·뒤. "
            '직방 추정값이고 실거래 평균이 아니다. 평형 정보를 받지 못했거나 두 끝이 모두 0 이거나 없으면 "sale": null, 한 끝만 그러면 그 price_manwon 만 null'
        ))
    ] = {}
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description=(
            "단지 평균 직방시세의 평당 가격 (아파트만, 만원/3.3㎡). 늘 'sale'·'jeonse' 두 키이고 안은 price_per_pyeong_manwon. "
            '웹 전체 탭 "평균 1억 235/3.3㎡". 0 이거나 없으면 그 거래가 null'
        ))
    ] = {}
    ranking: Annotated[
        ZigbangComplexRank | None,
        Field(description="단지 순위 (아파트만, 웹 '<동>에서 이 단지의 랭킹은?'). 직방이 구·동 순위를 주지 않으면 웹이 절을 숨기므로 null")
    ] = None
    related_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(description="웹 '함께 보면 좋은 단지' (아파트만, 직방이 준 순서). 직방이 주지 않으면 모름(null), 없으면 []")
    ] = None
    land_trade_permits: Annotated[
        list[ZigbangLandTradePermitDay] | None,
        Field(description="최근 7일 토지거래허가 일별 건수 (아파트만, 직방이 준 순서). 웹 '토지거래허가 총 N건 (최근 7일)' 과 날짜별 그래프. 직방이 주지 않으면 모름(null)")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = OFFICETEL_ONLY_COMPLEX_FIELDS if self.complex_type == '아파트' else APT_ONLY_COMPLEX_FIELDS
        for field in fields:
            data.pop(field, None)
        return data


class ZigbangComplexListingsResult(Result):
    """단지 하나의 매물 목록.

    `notes`: 일부만 보여 준다는 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 단지 ID')
    ]
    total: Annotated[
        int,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지 목록에 아직 받지 않은 매물이 남았는지 (이어 받기는 없다. --limit·조건으로)')
    ] = False
    listings: Annotated[
        # 아파트는 ZigbangAptListing 이라 서브클래스 필드(complex_id 등)까지 내보낸다
        list[SerializeAsAny[Listing]],
        Field(description='직방 목록 순서의 매물')
    ]


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


class ZigbangComplexPricePoint(BaseModel):
    """직방시세 추이의 한 달."""

    model_config = ConfigDict(
        extra='forbid',
    )

    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 평당가 (만원/3.3㎡). 직방이 0 을 준 달은 시세가 없는 달이라 null (점은 남는다)')
    ]


class ZigbangComplexPriceLine(BaseModel):
    """직방시세 추이의 줄 하나 (조회 단지, 비교 단지, 그 구). 직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='줄 이름 (직방이 준 label: 단지 이름 또는 구 이름)')
    ]
    kind: Annotated[
        ZigbangPriceLineKind | None,
        Field(
            description=(
                "줄 종류. 이름이 --compare 로 준 단지의 이름이면 '비교 단지', 마지막 줄이면 '구', 남은 줄이면 '단지'(조회 단지). "
                '직방이 줄 순서를 단지 ID 순으로 줘서 위치로는 알 수 없다. 직방시세가 없는 단지는 조회 단지 줄 없이 (비교 단지와) 구 줄만 와서 '
                "그때도 마지막 줄이 '구' 다. 이름이 겹치거나 줄 수가 (조회 단지 + 비교 단지 + 구)·(비교 단지 + 구) 와 다르거나 "
                '빈 줄을 뺐으면 판정하지 않고 null'
            )
        )
    ]
    complex_id: Annotated[
        str | None,
        Field(description="비교 단지의 단지 ID (kind 가 '비교 단지' 인 줄에만 있고 그 밖은 키가 없다)")
    ] = None
    months: Annotated[
        list[ZigbangComplexPricePoint] | None,
        Field(description='월별 매매 직방시세 평당가 (오래된 달부터). 직방이 월 목록을 주지 않으면 null')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.kind != '비교 단지':
            data.pop('complex_id', None)
        return data


class ZigbangPriceTrendResult(Result):
    """단지 직방시세 추이 (웹 단지 화면 직방시세 그래프 '3.3㎡ 당 평균가격', 기간 탭·단지 비교).

    `notes`: 비교 후보를 받지 못했다는 [실패] 안내, 시세 추이가 없다·줄 목록을 주지 않았다·구 줄만 있다는 [참고] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    comparable_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(
            description=(
                "웹 '단지 비교하기' 의 '단지 선택' 창 후보 (같이 많이 본 단지, 직방이 준 순서). --compare 에는 이 목록의 단지만 받는다. "
                '후보가 없으면 [], 직방이 주지 않았거나 받지 못하면 모름(null)'
            )
        )
    ]
    lines: Annotated[
        list[ZigbangComplexPriceLine] | None,
        Field(
            description=(
                '직방시세 그래프의 줄 (직방 응답 순서 그대로). 값은 매매 직방시세(직방이 실거래를 분석한 추정값)의 평당가이고 실거래가가 아니다. '
                '직방은 줄을 단지 ID 오름차순으로 주고 구를 끝에 붙여, 첫 줄이 조회 단지가 아닐 수 있다 (줄 종류는 kind). '
                '직방이 줄 목록을 주지 않으면 null (줄 목록 null 의 [참고] 안내), 줄이 없으면 []. '
                '직방시세가 없는 단지는 조회 단지 줄 없이 구 줄만 온다 (구 줄만 있다는 [참고] 안내)'
            )
        )
    ]


class ZigbangPyeongSale(BaseModel):
    """평형 하나의 한 달 매매 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 매매 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달(입주 전 등)은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(description='그 달 매매 거래의 가격 범위 (lowest 최저가·highest 최고가, price_manwon). 시세가 없는 달과, 거래가 0건인 달(직방이 시세 값을 대신 채워 준다)은 null')
    ]
    trade_count: Annotated[
        int | None,
        Field(description='그 달 매매 거래 건수 (0 도 진짜 값)')
    ]
    estimated_price_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongJeonseWolse(BaseModel):
    """평형 하나의 한 달 전월세 시세·거래. 금액은 만원이다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    estimated_deposit_manwon: Annotated[
        int | float | None,
        Field(description='그 달의 전세 직방시세 (직방이 실거래를 분석한 추정값). 직방이 0 을 준 달은 시세가 없어 null')
    ]
    trade_range: Annotated[
        AmountRange | None,
        Field(
            description=(
                '그 달 전세·월세 거래를 합친 가격 범위 (lowest 최저가·highest 최고가, 둘 다 converted_price_manwon 하나뿐). 월세는 직방이 '
                '보증금 + 월세 × 300 으로 환산한 값이고 (2026-11-22 실측) 보증금이 아니다. 시세가 없는 달과, 거래가 0건인 달은 null'
            )
        )
    ]
    trade_counts: Annotated[
        dict[str, int | None],
        Field(description="그 달 거래 건수. 늘 'jeonse'·'wolse' 두 키이고 값은 건수 (0 도 진짜 값, 직방이 주지 않으면 null)")
    ]
    estimated_deposit_change_manwon: Annotated[
        int | float | None,
        Field(description='전달 대비 전세 직방시세 변화. 시세가 없는 달은 null (변화가 없으면 0)')
    ]


class ZigbangPyeongPriceMonth(BaseModel):
    """평형 시세 추이의 한 달. 고르지 않은 거래 탭의 키는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade: Annotated[
        ZigbangPyeongTrendTrade,
        Field(exclude=True, description='고른 거래 탭. 해당 없는 탭의 키를 빼는 데 쓰고 출력하지 않는다')
    ]
    month: Annotated[
        str | None,
        Field(description='월 (YYYY-MM). 직방이 날짜를 주지 않았으면 null, 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    sale: Annotated[
        ZigbangPyeongSale | None,
        Field(description='매매 시세·거래. 직방이 그 달의 매매 기록을 주지 않았으면 null. --trade 전월세 에는 키가 없다')
    ]
    jeonse_wolse: Annotated[
        ZigbangPyeongJeonseWolse | None,
        Field(description='전월세 시세·거래. 직방이 그 달의 전월세 기록을 주지 않았으면 null. --trade 매매 에는 키가 없다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.trade == '매매':
            data.pop('jeonse_wolse', None)
        elif self.trade == '전월세':
            data.pop('sale', None)
        return data


class ZigbangPyeongPriceTrendResult(Result):
    """평형 하나의 월별 시세·거래 추이 (웹 단지 화면 평형 탭의 직방시세 그래프, 전체·매매·전월세 탭). 거래 점과 전세가율은 내지 않는다.

    `notes`: 평형 시세 기록이 없다는 [참고] 안내, 월 목록을 주지 않았다는 [참고] 안내, 빈 항목을 뺐다는 [제외] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='조회한 아파트 단지 ID')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (complex 결과의 pyeongs[].pyeong_id)')
    ]
    period: Annotated[
        ZigbangPriceTrendPeriod,
        Field(description='기간 (--period 값: 1년·3년·전체)')
    ]
    trade_tab: Annotated[
        ZigbangPyeongTrendTrade,
        Field(description='거래 탭 (--trade 값: 전체·매매·전월세)')
    ]
    months: Annotated[
        list[ZigbangPyeongPriceMonth] | None,
        Field(description='월별 시세·거래 (오래된 달부터). 매매·전월세 기록을 월로 맞춘 목록이고 기록이 없으면 [], 직방이 월 목록을 주지 않았으면 null')
    ]
