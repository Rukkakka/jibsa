"""단지의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountSet,
    NumberRange,
    Result,
    with_floor_number,
)
from jibsa.providers.dabang.service.common.functions import SchoolLevel
from jibsa.providers.dabang.service.common.models import (
    DabangAreaPrice,
    DabangListing,
    DabangPlace,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


# 최근 거래의 면적을 내는 키. 다방 요약의 면적은 아파트면 공급, 오피스텔이면 계약이다
RecentAreaKey = Literal['supply_area_m2', 'contract_area_m2']

# 중·고등학교·어린이집·유치원은 가까운 순 3곳. 웹 '주변 보육/교육시설' 탭이 3곳씩 보이고 '더보기' 로 3곳씩 늘린다
# (education 청크 `Y`·`X`·`Q`·`$` = 3, 2026-11-13)
NEAREST_SCHOOLS: int = 3

DEFAULT_COMPLEX_SORT: str = '랭킹순'


class DabangComplexSummary(BaseModel):
    """단지 목록의 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID. dabang complex·search listings --complex·real-price 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    occupancy_years: Annotated[
        int | None,
        Field(description='입주 N년차 (사용승인한 해를 1년차로 센다. 연식 age_years 보다 1 크다)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 매물 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (다방이 주지 않은 수는 null)")
    ]
    latest_trades: Annotated[
        dict[str, AmountSet | None],
        Field(description=(
            "거래별 가장 최근 실거래가 (평형과 상관없이 단지의 가장 최근 거래. 다방 목록 카드와 같다). 키는 'sale'(price_manwon)·"
            "'jeonse'(deposit_manwon) 늘 두 개이고 거래가 없거나 받지 못하면 null (complex 의 latest_trades 와 같다)"
        ))
    ]


class DabangComplexListResult(Result):
    """단지 목록.

    `notes`: 범위·제외 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='찾은 위치')
    ]
    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description='다방이 센 범위 안 단지 수 (반경·아파트 동 검색은 사각형 안의 수)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    complexes: Annotated[
        list[DabangComplexSummary],
        Field(description='다방 목록 순 단지')
    ]


class DabangPyeong(BaseModel):
    """단지의 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_id: Annotated[
        int,
        Field(description='평형 ID. real-price·price-trend·search listings --complex 의 --pyeong 값')
    ]
    name: Annotated[
        str | None,
        Field(description="평형 이름 (아파트는 공급 평 '30', 오피스텔은 '13B1')")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 대개 null')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡, 오피스텔)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='월 관리비 총액 (만원, 다방 단지 정보)')
    ] = None


class DabangRecentTrade(BaseModel):
    """최근 실거래 한 건 (단지 요약). 면적은 다방 화면처럼 아파트는 공급면적, 오피스텔은 계약면적 키 하나만 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원). 매매 거래에만 있다')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='전세금 (만원). 전세 거래에만 있다')
    ] = None
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 ('5', '지하1', '고층'). 바로 뒤 floor_number 는 몇 층인지 아는 층의 숫자 (지하는 음수, 모르면 null)")
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='거래 공급면적 (㎡, 아파트. 다방 화면의 면적)')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='거래 계약면적 (㎡, 오피스텔. 다방 화면의 면적)')
    ] = None
    pyeong_id: Annotated[
        int | None,
        Field(description='거래한 평형 ID (pyeongs[].pyeong_id). 면적이 맞는 평형이 하나일 때만, 없거나 여럿이면 null')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='거래한 평형의 전용면적 (㎡). pyeong_id 가 null 이면 null')
    ] = None
    area_key: Annotated[
        RecentAreaKey,
        Field(exclude=True, description='단지 유형에 맞는 면적 키')
    ]
    trade_type: Annotated[
        Literal['매매', '전세'],
        Field(exclude=True, description='어느 거래의 최근 거래인지. 금액 칸 이름(매매 price_manwon, 전세 deposit_manwon)을 정한다')
    ]

    @model_serializer(mode='wrap')
    def drop_other_area(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        data.pop('contract_area_m2' if self.area_key == 'supply_area_m2' else 'supply_area_m2', None)
        data.pop('deposit_manwon' if self.trade_type == '매매' else 'price_manwon', None)
        return with_floor_number(data)


class DabangComplexSchool(BaseModel):
    """단지 근처 학교 하나. 진학 인원은 중학교·고등학교에만 키가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    level: Annotated[
        SchoolLevel,
        Field(description='초등학교 / 중학교 / 고등학교. school 명령의 --level 값')
    ]
    school_code: Annotated[
        str | None,
        Field(description='학교 코드. jibsa dabang school <school_code> --level <level> 로 학교 상세를 본다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='학교 이름 (다방이 주지 않으면 null)')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description='설립 (공립, 사립)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선 거리 (m)')
    ] = None
    district: Annotated[
        str | None,
        Field(description='초등학교는 단지가 든 통학구역(배정 학구), 중·고등학교는 단지가 든 학교군')
    ] = None
    students_per_class: Annotated[
        int | None,
        Field(description='학급당 학생 수')
    ] = None
    special_high_entrants: Annotated[
        int | None,
        Field(description='특목고(과학고·외고·국제고·예술고 등) 진학 인원 (명, 중학교, 학교알리미 공시)')
    ] = None
    autonomous_high_entrants: Annotated[
        int | None,
        Field(description='자율형(자사고·자공고) 고등학교 진학 인원 (명, 중학교, 학교알리미 공시)')
    ] = None
    university_entrants: Annotated[
        int | None,
        Field(description='대학교(4년제) 진학 인원 (명, 고등학교, 학교알리미 공시)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_other_levels(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.level != '중학교':
            data.pop('special_high_entrants', None)
            data.pop('autonomous_high_entrants', None)
        if self.level != '고등학교':
            data.pop('university_entrants', None)
        return data


class DabangChildcare(BaseModel):
    """단지 근처 어린이집·유치원 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str | None,
        Field(description='다방 시설 코드. jibsa dabang school <school_code> --level 어린이집 (nurseries) 또는 --level 유치원 (kindergartens) 으로 상세를 본다')
    ] = None
    name: Annotated[
        str | None,
        Field(description='시설 이름 (다방이 주지 않으면 null)')
    ] = None
    establishment: Annotated[
        str | None,
        Field(description="설립 유형 (어린이집 '공공'·'민간'·'가정'·'직장'·'협동', 유치원 '국공립'·'사립'. search schools·school 과 같은 이름)")
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선 거리 (m)')
    ] = None
    children_per_teacher: Annotated[
        float | None,
        Field(description='교사당 아동 수')
    ] = None


class DabangComplexDetail(Result):
    """단지 정보.

    `notes`: 덤 조회 실패·최근 거래 평형 안내
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
        str | None,
        Field(description='아파트 / 오피스텔')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 층수의 최소·최대. 둘 다 모르면 null')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    building_coverage_ratio_percent: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방')
    ] = None
    heating_fuel: Annotated[
        str | None,
        Field(description='연료')
    ] = None
    entrance: Annotated[
        str | None,
        Field(description='현관 구조 (계단식·복도식)')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수')
    ] = None
    recent_trade_count: Annotated[
        int | None,
        Field(description="최근 거래 수 (다방 화면의 '최근 거래수 N건', 다방이 기간을 밝히지 않는다)")
    ] = None
    tags: Annotated[
        list[str],
        Field(description="다방 단지 꼬리표 (예: '입주 5년차', '고속터미널역 도보 7분', '초품아'). 없으면 []")
    ] = []
    pyeongs: Annotated[
        list[DabangPyeong] | None,
        Field(description='평형. null 이면 다방이 평형을 주지 않은 것이라 모름')
    ]
    representative_pyeong_id: Annotated[
        int | None,
        Field(description=(
            '대표 평형 ID (real-price·price-trend·nearby-complexes 에 --pyeong 이 없을 때 쓴다). 다방이 대표를 주지 않으면 '
            '다방 웹처럼 첫 평형이고, 평형이 없으면 null'
        ))
    ] = None
    area_prices: Annotated[
        list[DabangAreaPrice] | None,
        Field(description=(
            "평당 평균가 비교 (이 단지·동·구, 다방 웹 평당가 칸의 '전체 평형 비교' 탭). 기본 탭 'N평대 비교' 는 "
            'jibsa dabang nearby-complexes <complex_id>. null 이면 다방이 주지 않은 것이라 모름'
        ))
    ]
    latest_trades: Annotated[
        dict[str, DabangRecentTrade | None],
        Field(description="거래별 가장 최근 실거래. 키는 'sale'·'jeonse' 늘 두 개이고 거래가 없거나 받지 못하면 null")
    ]
    overheated_district: Annotated[
        bool | None,
        Field(description=(
            "다방 대출 계산기가 대출 비율을 50%로 묶는 지역인지 (다방 단지 대출 계산 조건 isOverheatedDistrict). 웹 대출 계산기는 "
            "true 면 대출 가능액을 집값의 절반으로 셈하고, 자본금이 모자랄 때 '투기지역 (대출 비율 50% 제한) 입니다.' 라고 알린다. "
            "받지 못하면 null"
        ))
    ] = None
    schools: Annotated[
        list[DabangComplexSchool] | None,
        Field(description=f'배정 초등학교와 단지가 든 학교군의 가까운 중·고등학교 {NEAREST_SCHOOLS}곳씩. 모르면 null')
    ] = None
    nurseries: Annotated[
        list[DabangChildcare] | None,
        Field(description=f'가까운 어린이집 {NEAREST_SCHOOLS}곳. 없으면 [], 모르면 null')
    ] = None
    kindergartens: Annotated[
        list[DabangChildcare] | None,
        Field(description=f'가까운 유치원 {NEAREST_SCHOOLS}곳. 없으면 [], 모르면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class DabangComplexListingsResult(Result):
    """단지 하나의 매물.

    `notes`: 평형·제외·일부 안내
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
    pyeong_ids: Annotated[
        list[int] | None,
        Field(description='고른 평형 ID. null 이면 전체 평형')
    ] = None
    sort: Annotated[
        str,
        Field(description="매물 순서 (다방 웹 단지 매물 정렬: '랭킹순'·'최신순'·'높은가격순'·'낮은가격순'·'면적넓은순'·'면적좁은순')")
    ] = DEFAULT_COMPLEX_SORT
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 매물 수 (limit 적용 전)')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 매물이 있는지')
    ] = False
    listings: Annotated[
        list[DabangListing],
        Field(description='sort 순서 그대로의 매물 (다방이 정렬한 순서)')
    ]
