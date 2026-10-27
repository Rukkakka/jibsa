"""순위 (trending-complexes · trade-rankings · region-ranking)."""
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.ranking import (
    RANKING_PAGE_LIMIT,
    REGION_INFO_RANKING_PAGE_LIMIT,
    DabangRankingMetric,
    DabangRankingPriceType,
    DabangRealPriceTradeRankingsComplexV5RequestParameterModel,
    DabangRealTimeWatchRankingsV5RequestParameterModel,
    DabangRegionInfoRankingMetric,
    DabangRegionInfoRankingV5RequestParameterModel,
    DabangRegionInfoRealEstateRankingV5RequestParameterModel,
    DabangRegionInfoTopic,
    DabangSchoolAdvancementType,
    DabangTradeBaseOn,
    DabangWatchBaseOn,
)
from jibsa.providers.dabang.api.response.ranking import (
    DabangFluctuationModel,
    DabangRegionRankingItemModel,
    DabangRegionRankingResultModel,
)
from jibsa.providers.dabang.service.common import (
    building_years,
    household_count,
    manwon_from_text,
)
from jibsa.providers.dabang.service.region import (
    DabangScope,
    legal_division_code,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


COMPLEX_TYPE_BY_LABEL: dict[str, Literal['APT', 'OFFICETEL']] = {'아파트': 'APT', '오피스텔': 'OFFICETEL'}
WATCH_PERIOD_BY_LABEL: dict[str, DabangWatchBaseOn] = {
    '방금전': 'JUST_BEFORE',
    '어제': 'YESTERDAY',
    '지난주': 'LAST_WEEK',
    '지난달': 'LAST_MONTH',
}
TRADE_PERIOD_BY_LABEL: dict[str, DabangTradeBaseOn] = {
    '이번주': 'CURRENT_WEEK',
    '지난주': 'LAST_WEEK',
    '이번달': 'CURRENT_MONTH',
    '지난달': 'LAST_MONTH',
    '올해': 'CURRENT_YEAR',
}
# 막 시작한 기간은 다방이 아직 세지 않아 순위가 빈다 (2026-10-26 월 아침 실측: 이번주 0곳, 지난주·이번달은 있음). 비면 권할 기간
PREVIOUS_TRADE_PERIOD: dict[str, str] = {'이번주': '지난주', '이번달': '지난달', '올해': '지난달'}
RANKING_TRADE_BY_LABEL: dict[str, DabangRankingPriceType] = {'매매': 'SALE', '전세': 'LEASE', '월세': 'MONTHLY_RENT'}
FLUCTUATION_LABELS: dict[str, str] = {'UP': '상승', 'DOWN': '하락', 'STEADY': '유지', 'NEW': '신규'}
NUMBER_PATTERN: re.Pattern[str] = re.compile(r'[+-]?\d[\d,]*(?:\.\d+)?')
REGION_RANKING_MAX_LIMIT: int = 100
AGE_YEARS_PATTERN: re.Pattern[str] = re.compile(r'(\d+)\s*년')
# 기준 달 글자: '26년 10월'
MONTH_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d{2})년\s*(\d{1,2})월')
ValueKind = Literal['price', 'count', 'percent', 'change', 'age', 'score', 'population-change']


class MetricSpec(NamedTuple):
    """부동산 순위 항목 하나 (동·단지): 경로 이름, 값 종류, 받는 거래 유형 꼴, 유형을 받는지, 단지만인지."""

    metric: DabangRankingMetric
    kind: ValueKind
    trade: Literal['one', 'many', 'none']
    complex_type: bool
    complex_only: bool = False


class InfoMetricSpec(NamedTuple):
    """동네정보 순위 항목 하나 (동만): 주제·항목 경로, 값 종류, 늘 보내는 진학 값, --kind 로 고르는 종류.

    `kinds` 는 --kind 라벨 → 요청 값이고 `kind_field` 요청 칸에 넣는다. `default_kind` 가 있으면 --kind 가 없어도 그 값을
    보낸다 (학원은 종류가 없으면 다방이 빈 목록을 준다).
    """

    topic: DabangRegionInfoTopic
    metric: DabangRegionInfoRankingMetric
    kind: ValueKind
    school_type: Literal['MIDDLE_SCHOOL', 'HIGH_SCHOOL'] | None = None
    advancement: DabangSchoolAdvancementType | None = None
    kind_field: Literal['academy_type', 'school_establishment_type', 'facility_type'] | None = None
    kinds: dict[str, str] | None = None
    default_kind: str | None = None


# --kind 값: 웹 고르기 이름에서 띄어쓰기·'/'·괄호를 뺀 것 (school·facility·traffic·life-safety 청크, 2026-10-25)
ACADEMY_KIND_BY_LABEL: dict[str, str] = {
    '입시': 'ADMISSION_EXAM', '예체능': 'ARTS_SPORTS', '외국어': 'FOREIGN_LANGUAGE', '특성화': 'SPECIALIZED',
    '종합': 'COMPREHENSIVE', '인문사회': 'HUMANITIES_SOCIAL', '코딩': 'PROGRAMMING',
}
SCHOOL_KIND_BY_LABEL: dict[str, str] = {'국공립': 'PUBLIC', '사립': 'PRIVATE'}
NURSERY_KIND_BY_LABEL: dict[str, str] = {
    '공공': 'PUBLIC', '민간': 'PRIVATE', '가정': 'HOME', '직장': 'WORKPLACE', '협동': 'COOPERATIVE',
}
FACILITY_KIND_BY_LABEL: dict[DabangRegionInfoRankingMetric, dict[str, str]] = {
    'living': {'편의점': 'CONVENIENCE_STORE', '세탁소': 'LAUNDRY', '헬스장': 'GYM', '공원': 'PARK', '도서관': 'LIBRARY'},
    'medical': {'병원': 'HOSPITAL', '의원': 'CLINIC', '약국': 'PHARMACY', '응급의료센터': 'EMERGENCY'},
    'dining': {'음식점': 'FOOD', '카페': 'CAFE', '주점': 'BAR'},
    'shopping': {'대형마트': 'LARGE_STORE', '백화점': 'DEPARTMENT_STORE', '복합쇼핑몰': 'SHOPPING_MALL'},
    'sports': {
        '수영장': 'SWIMMING_POOL', '테니스장': 'TENNIS_COURT', '암벽장': 'CLIMBING_WALL', '골프장': 'GOLF_COURSE',
        '축구장': 'SOCCER_FIELD', '야구장': 'BASEBALL_FIELD', '당구장': 'BILLIARD_ROOM', '체육관': 'GYM', '기타': 'ETC',
    },
    'transit': {'지하철': 'SUBWAY', '버스': 'BUS_STOP'},
    'parking-lot': {'공영': 'PUBLIC_PARKING_LOT', '민영': 'COMMERCIAL_PARKING_LOT'},
    'charge-station': {'주유소': 'GAS_STATION', '전기차충전소': 'EV_CHARGING_STATION'},
    'maintenance-shop': {'자동차수리점': 'CAR_REPAIR_SHOP', '세차장': 'CAR_WASH', '타이어전문점': 'TIRE_SHOP'},
    'safety-facility': {'CCTV': 'CCTV', '가로등': 'STREET_LAMP'},
    'safety-organization': {
        '경찰서': 'POLICE_STATION', '지구대파출소': 'LOCAL_SUBSTATION', '치안센터': 'SECURITY_CENTER', '소방서': 'FIRE_STATION',
        '119안전센터': 'SAFETY_CENTER',
    },
    'inconvenience': {'공사현장': 'CONSTRUCTION', '소음구역': 'NOISE'},
}


def _facility(topic: DabangRegionInfoTopic, metric: DabangRegionInfoRankingMetric) -> InfoMetricSpec:
    return InfoMetricSpec(topic, metric, 'count', kind_field='facility_type', kinds=FACILITY_KIND_BY_LABEL[metric])


def _school_count(metric: DabangRegionInfoRankingMetric, kinds: dict[str, str]) -> InfoMetricSpec:
    return InfoMetricSpec('school', metric, 'count', kind_field='school_establishment_type', kinds=kinds)


def _advancement(school_type: Literal['MIDDLE_SCHOOL', 'HIGH_SCHOOL'], advancement: DabangSchoolAdvancementType) -> InfoMetricSpec:
    return InfoMetricSpec('school', 'school-advancement', 'percent', school_type=school_type, advancement=advancement)


# 다방 '부동산 랭킹' 항목 (real-estate 청크의 이름표와 요청 값, 2026-10-25)과 동네정보 랭킹 항목 (동만)
METRIC_BY_LABEL: dict[str, MetricSpec | InfoMetricSpec] = {
    '평균가': MetricSpec('average-price', 'price', 'one', True),
    '평당가': MetricSpec('pyeong-price', 'price', 'one', True),
    '거래량': MetricSpec('trade-volume', 'count', 'many', True),
    '매물수': MetricSpec('room-count', 'count', 'many', True),
    '시세증감': MetricSpec('average-price-change', 'change', 'one', True),
    '최고가증감': MetricSpec('max-price-change', 'change', 'one', True),
    '선호도': MetricSpec('reaction-score', 'score', 'many', True),
    '세대수': MetricSpec('household-count', 'count', 'none', False),
    '연식': MetricSpec('age', 'age', 'none', False),
    '전세가율': MetricSpec('lease-rate', 'percent', 'none', True, complex_only=True),
    '갭가격': MetricSpec('gap-price', 'price', 'none', True, complex_only=True),
    # 진학률은 그 동 학교 졸업생 기준 (학교알리미 공시): 중학교 → 고교 유형, 고등학교 → 대학
    '과학고진학률': _advancement('MIDDLE_SCHOOL', 'SCIENCE_HIGH_SCHOOL'),
    '외국어고진학률': _advancement('MIDDLE_SCHOOL', 'FOREIGN_HIGH_SCHOOL'),
    '자사고진학률': _advancement('MIDDLE_SCHOOL', 'AUTONOMOUS_PRIVATE_HIGH_SCHOOL'),
    '예술체육고진학률': _advancement('MIDDLE_SCHOOL', 'ART_PHYSICAL_HIGH_SCHOOL'),
    '대학교진학률': _advancement('HIGH_SCHOOL', 'UNIVERSITY'),
    '전문대학진학률': _advancement('HIGH_SCHOOL', 'COLLEGE'),
    '학원수': InfoMetricSpec(
        'school', 'academy', 'count', kind_field='academy_type', kinds=ACADEMY_KIND_BY_LABEL, default_kind='입시',
    ),
    '초등학교수': _school_count('elementary-school', SCHOOL_KIND_BY_LABEL),
    '중학교수': _school_count('middle-school', SCHOOL_KIND_BY_LABEL),
    '고등학교수': _school_count('high-school', SCHOOL_KIND_BY_LABEL),
    '유치원수': _school_count('kinder-school', SCHOOL_KIND_BY_LABEL),
    '어린이집수': _school_count('nursery-school', NURSERY_KIND_BY_LABEL),
    '인구': InfoMetricSpec('population', 'count', 'count'),
    '인구증감': InfoMetricSpec('population', 'year-of-year-change', 'population-change'),
    '생활편의시설': _facility('amenity', 'living'),
    '의료시설': _facility('amenity', 'medical'),
    '외식시설': _facility('amenity', 'dining'),
    '대형쇼핑시설': _facility('amenity', 'shopping'),
    '체육시설': _facility('amenity', 'sports'),
    '교통시설': _facility('mobility', 'transit'),
    '주차시설': _facility('mobility', 'parking-lot'),
    '주유시설': _facility('mobility', 'charge-station'),
    '차량관리시설': _facility('mobility', 'maintenance-shop'),
    '안전시설': _facility('life-safety', 'safety-facility'),
    '안전기관': _facility('life-safety', 'safety-organization'),
    '불편요소': _facility('life-safety', 'inconvenience'),
}


# 항목의 값 종류마다 늘 해당하는 값 칸
VALUE_FIELDS_BY_KIND: dict[ValueKind, frozenset[str]] = {
    'price': frozenset({'value_manwon'}),
    'count': frozenset({'count'}),
    'percent': frozenset({'percent'}),
    'change': frozenset({'change_manwon', 'change_percent', 'prev_price_manwon'}),
    'age': frozenset({'age_years'}),
    'score': frozenset({'score'}),
    'population-change': frozenset({'count', 'prev_count', 'change_count', 'change_percent'}),
}


def _number(text: str | None) -> float | None:
    match = NUMBER_PATTERN.search((text or '').replace(' ', ''))
    return float(match.group().replace(',', '')) if match else None


def _int(text: str | None) -> int | None:
    number = _number(text)
    return None if number is None else int(number)


def _manwon(text: str | None) -> float | None:
    """'61.1억', '4,762만', '+1.2억' 같은 금액 글을 만원으로. 부호는 지킨다."""
    if not text:
        return None
    value = text.strip()
    sign = -1 if value.startswith('-') else 1
    amount = manwon_from_text(value.lstrip('+-').removesuffix('만'))
    return None if amount is None else sign * amount


def _change(fluctuation: DabangFluctuationModel | None) -> str | None:
    if fluctuation is None or fluctuation.type is None:
        return None
    label = FLUCTUATION_LABELS.get(fluctuation.type, fluctuation.type)
    return f'{label} {fluctuation.rank}' if fluctuation.type in ('UP', 'DOWN') and fluctuation.rank else label


class DabangWatchRanking(BaseModel):
    """조회 순위 한 칸. 단지면 단지 필드, 동이면 동 필드가 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    unit: Annotated[
        Literal['단지', '동'],
        Field(exclude=True, description='단지 / 동 (다른 쪽 필드는 해당 없어 키를 뺀다)')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 순위)')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름 또는 동 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='단지 주소 (동까지) 또는 동의 시·도')
    ] = None
    legal_division_code: Annotated[
        str | None,
        Field(description='동의 법정동코드 (동 순위, 10자리)')
    ] = None
    view_count: Annotated[
        int | None,
        Field(description='기간 안 조회 수')
    ] = None
    change: Annotated[
        str | None,
        Field(description="앞 기간 대비 ('상승 3', '하락 2', '유지', '신규')")
    ] = None

    @model_serializer(mode='wrap')
    def drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 해당하는 쪽 필드가 비면 모름(null)으로 남긴다
        data.pop('legal_division_code' if self.unit == '단지' else 'complex_id', None)
        return data


class DabangWatchRankings(BaseModel):
    """전국 조회 순위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    unit: Annotated[
        str,
        Field(description='단지 / 동')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 / 오피스텔')
    ]
    period: Annotated[
        str,
        Field(description='기간 (방금전·어제·지난주·지난달)')
    ]
    base_period: Annotated[
        str | None,
        Field(description="다방이 센 기간 ('26.10.12 ~ 26.10.18', '26.10.25 17:09 기준')")
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수 (다방은 50곳까지 준다)')
    ]
    rankings: Annotated[
        list[DabangWatchRanking],
        Field(description='순위')
    ]


def get_watch_rankings(
    client: DabangClient, *, unit: Literal['단지', '동'], complex_type: str, period: str, limit: int,
) -> DabangWatchRankings:
    """전국에서 지금 많이 보는 단지·동 (요청 1회, 다방은 늘 50곳). 지역으로 좁히지 못한다."""
    result = client.run_request_real_time_watch_rankings_v5(DabangRealTimeWatchRankingsV5RequestParameterModel(
        unit='complex' if unit == '단지' else 'region',
        complex_type=COMPLEX_TYPE_BY_LABEL[complex_type],
        base_on=WATCH_PERIOD_BY_LABEL[period],
    )).result
    rows = (result.list_ if result else [])[:limit]
    return DabangWatchRankings(
        unit=unit,
        complex_type=complex_type,
        period=period,
        base_period=result.format_base_period if result else None,
        returned=len(rows),
        rankings=[
            DabangWatchRanking(
                rank=row.rank,
                unit=unit,
                complex_id=row.complex_id,
                name=row.complex_name or row.dong_name,
                address=normalize_address(row.address) if unit == '단지' else row.state_name,
                legal_division_code=legal_division_code(row.dong_code) if row.dong_code else None,
                view_count=row.watch_count,
                change=_change(row.fluctuation),
            )
            for row in rows
        ],
    )


class DabangTradeRanking(BaseModel):
    """거래 순위 한 칸."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID')
    ] = None
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 수 (국토교통부 신고)')
    ] = None
    years: Annotated[
        int | None,
        Field(description='입주 연차')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None


class DabangTradeRankings(BaseModel):
    """전국 거래 순위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_type: Annotated[
        str,
        Field(description='아파트 / 오피스텔')
    ]
    trade: Annotated[
        str,
        Field(description='매매 / 전세')
    ]
    period: Annotated[
        str,
        Field(description='기간')
    ]
    base_period: Annotated[
        str | None,
        Field(description="다방이 센 기간 ('26.10.19 ~ 26.10.25')")
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수')
    ]
    rankings: Annotated[
        list[DabangTradeRanking],
        Field(description='순위')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='빈 순위 안내')
    ] = []


def get_trade_rankings(
    client: DabangClient, *, complex_type: str, trade: str, period: str, limit: int,
) -> DabangTradeRankings:
    """전국에서 기간 안 거래가 많은 단지 (요청 1회, 다방은 50곳을 준다)."""
    result = client.run_request_real_price_trade_rankings_complex_v5(DabangRealPriceTradeRankingsComplexV5RequestParameterModel(
        complex_type=COMPLEX_TYPE_BY_LABEL[complex_type],
        real_price_type='SALE' if trade == '매매' else 'LEASE',
        base_on=TRADE_PERIOD_BY_LABEL[period],
    )).result
    rankings = []
    # 웹처럼 50곳을 받아 자른다. limit 을 작게(2) 보내면 다방이 500 을 준다 (2026-10-25 실측: 같은 조건 limit 50 은 200)
    for row in (result.list_ if result else [])[:limit]:
        # '11년차ㆍ3636세대ㆍ서울특별시 송파구 문정동'. 주소 칸을 골라야 해 칸으로 나눠 읽는다
        # 설명이 비면 주소도 모름(null)이다
        parts = [part.strip() for part in (row.description or '').split('ㆍ')]
        address = next((part for part in parts if part and not part.endswith(('년차', '세대'))), None)
        rankings.append(DabangTradeRanking(
            rank=row.rank, complex_id=row.complex_id, name=row.complex_name, trade_count=row.trade_count,
            years=building_years(row.description), household_count=household_count(row.description),
            address=normalize_address(address),
        ))
    notes = []
    if not rankings and period in PREVIOUS_TRADE_PERIOD:
        notes.append(note('참고', (
            f'{period} 순위가 비었습니다. 기간이 막 시작돼 다방이 아직 세지 않았을 수 있습니다. '
            f'--period {PREVIOUS_TRADE_PERIOD[period]} 로 보세요'
        )))
    return DabangTradeRankings(
        complex_type=complex_type,
        trade=trade,
        period=period,
        base_period=result.format_base_period if result else None,
        returned=len(rankings),
        rankings=rankings,
        notes=notes,
    )


class DabangRegionRankingEntry(BaseModel):
    """범위 안 순위 한 칸. 값 필드는 항목에 맞는 것만 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    name: Annotated[
        str | None,
        Field(description='동 이름 또는 단지 이름')
    ] = None
    area: Annotated[
        str | None,
        Field(description="상위 지역 ('서울 강남구', 단지는 동까지)")
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 순위)')
    ] = None
    value_text: Annotated[
        str | None,
        Field(description="다방 표시 값 ('61.1억', '27개', '133.3%', '44년 6개월', '19점', 인구증감 '327명 (-0.6%)')")
    ] = None
    value_manwon: Annotated[
        float | None,
        Field(description='금액 (만원, 평균가·평당가·갭가격)')
    ] = None
    count: Annotated[
        int | None,
        Field(description='수 (거래량·매물수·세대수, 학교·학원·시설 수, 인구. 인구증감은 올해 인구)')
    ] = None
    prev_count: Annotated[
        int | None,
        Field(description='한 해 전 인구 (인구증감)')
    ] = None
    change_count: Annotated[
        int | None,
        Field(description='한 해 사이 인구 변화 (명, 줄면 음수, 인구증감)')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='비율 (%, 전세가율·진학률)')
    ] = None
    score: Annotated[
        int | None,
        Field(description='다방 선호도 점수 (조회수·찜수·문의수 등을 합친 점수)')
    ] = None
    change_manwon: Annotated[
        float | None,
        Field(description='금액 변화 (만원, 시세증감·최고가증감. 현재가가 아니다)')
    ] = None
    change_percent: Annotated[
        float | None,
        Field(description='변화율 (%, 시세증감·최고가증감·인구증감)')
    ] = None
    prev_price_manwon: Annotated[
        float | None,
        Field(description='비교 기준 금액 (만원, 시세증감은 앞 시세, 최고가증감은 앞 최고가)')
    ] = None
    prev_price_date: Annotated[
        str | None,
        Field(description="앞 최고가 달 (최고가증감, '23년 10월')")
    ] = None
    age_years: Annotated[
        int | None,
        Field(description='연식 (년, 연식)')
    ] = None
    pyeong: Annotated[
        str | None,
        Field(description="평형 ('93평', 단지)")
    ] = None
    price_date: Annotated[
        str | None,
        Field(description="금액 기준 ('26년 5월', 최고가증감 단지는 새 최고가 달)")
    ] = None
    price_detail: Annotated[
        str | None,
        Field(description="금액 설명 ('매매 90억 / 전세 14.5억')")
    ] = None

    # 이 순위 결과에 해당하는 칸 (`get_region_ranking` 이 채운다). 해당하는데 값이 없으면 null(모름)로 둔다
    _applicable: frozenset[str] = PrivateAttr(default=frozenset({'rank', 'name'}))

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {key: value for key, value in data.items() if value is not None or key in self._applicable}


class DabangRegionRanking(BaseModel):
    """범위 안 동·단지 순위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        DabangScope,
        Field(description='범위')
    ]
    unit: Annotated[
        str,
        Field(description='동 / 단지')
    ]
    metric: Annotated[
        str,
        Field(description='항목')
    ]
    kind: Annotated[
        str | None,
        Field(description='--kind 로 고른 종류 (학원·학교·시설). 학원은 주지 않으면 입시')
    ] = None
    base_month: Annotated[
        str | None,
        Field(description='다방이 센 기준 달 (YYYY-MM, 시세증감·최고가증감 동 순위)')
    ] = None
    total: Annotated[
        int | None,
        Field(description='범위 안 순위가 있는 동·단지 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='순위가 더 있는지')
    ] = False
    rankings: Annotated[
        list[DabangRegionRankingEntry],
        Field(description='순위')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부 안내')
    ] = []

    @model_serializer(mode='wrap')
    def drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('kind', 'base_month'):
            if data.get(key) is None:
                data.pop(key, None)
        return data


def _month(text: str | None) -> str | None:
    """'26년 10월' → '2026-10'."""
    match = MONTH_TEXT_PATTERN.search(text or '')
    return f'20{match.group(1)}-{int(match.group(2)):02d}' if match else None


def _entry(row: DabangRegionRankingItemModel, kind: ValueKind) -> DabangRegionRankingEntry:
    text = (
        row.formatted_price or row.formatted_count or row.formatted_percentage or row.formatted_age
        or row.formatted_change_rate or row.formatted_score
    )
    entry = DabangRegionRankingEntry(
        rank=row.rank,
        name=row.complex_name or row.region_name,
        area=row.parent_region_name,
        complex_id=row.complex_id,
        value_text=text,
        pyeong=row.formatted_pyeong,
        price_date=row.formatted_price_date,
        price_detail=row.formatted_price_detail,
    )
    if kind == 'price':
        entry.value_manwon = _manwon(row.formatted_price)
    elif kind == 'count':
        entry.count = _int(row.formatted_count)
    elif kind == 'percent':
        entry.percent = _number(row.formatted_percentage)
    elif kind == 'score':
        entry.score = _int(row.formatted_score)
    elif kind == 'change':
        entry.value_text = row.formatted_change_rate or text
        entry.change_percent = _number(row.formatted_change_rate)
        entry.change_manwon = _manwon(row.formatted_price)
        if entry.change_manwon is not None and entry.change_percent is not None and entry.change_percent < 0:
            entry.change_manwon = -abs(entry.change_manwon)
        # 최고가증감은 앞 최고가가 formattedMaxPrice 로 온다 (시세증감은 formattedPrevPrice)
        entry.prev_price_manwon = _manwon(row.formatted_prev_price or row.formatted_max_price)
        entry.prev_price_date = row.formatted_max_price_date
    elif kind == 'population-change':
        change_text = row.formatted_year_of_year_change_count
        rate_text = row.formatted_year_of_year_change_percentage
        entry.value_text = f'{change_text} ({rate_text})' if change_text and rate_text else change_text or rate_text
        entry.count = _int(row.formatted_curr_count)
        entry.prev_count = _int(row.formatted_prev_count)
        entry.change_percent = _number(rate_text)
        # 변화 수는 부호 없이('327명') 온다. 줄었는지는 changeStatus 와 변화율 부호로 본다 (2026-10-25 강남구 도곡동 -0.6%)
        change = _int(change_text)
        decreased = row.change_status == 'DECREASE' or (entry.change_percent is not None and entry.change_percent < 0)
        entry.change_count = -abs(change) if change is not None and decreased else change
    else:
        # '44년 6개월' → 44, '1개월 미만'·'8개월' → 0
        years = AGE_YEARS_PATTERN.search(row.formatted_age or '')
        entry.age_years = int(years.group(1)) if years else (0 if '개월' in (row.formatted_age or '') else None)
    return entry


def get_region_ranking(
    client: DabangClient,
    scope: DabangScope,
    *,
    metric_label: str,
    unit: Literal['동', '단지'],
    complex_type: str,
    trades: list[str],
    order: Literal['높은순', '낮은순'],
    limit: int,
    kind_label: str | None = None,
) -> DabangRegionRanking:
    """범위(전국·시도·시군구) 안 동·단지 순위 (부동산은 50곳, 동네정보는 30곳마다 요청 1회).

    거래 유형은 항목에 맞게 보낸다: 평균가·평당가·시세증감·최고가증감은 하나(기본 매매), 거래량·매물수·선호도는 여럿(기본 전체).
    동네정보 항목(학교·학원·진학률·인구·시설)은 동 단위만 있고 `kind_label` 로 종류를 고른다 (학원은 기본 입시).
    """
    spec = METRIC_BY_LABEL[metric_label]
    sort: Literal['DESC', 'ASC'] = 'ASC' if order == '낮은순' else 'DESC'
    if isinstance(spec, MetricSpec):
        page_limit = RANKING_PAGE_LIMIT
        price_type: Literal['SALE', 'LEASE'] | None = None
        price_type_list = None
        if spec.trade == 'one':
            price_type = 'LEASE' if trades[:1] == ['전세'] else 'SALE'
        elif spec.trade == 'many':
            price_type_list = [RANKING_TRADE_BY_LABEL[trade] for trade in trades] or list(RANKING_TRADE_BY_LABEL.values())

        def fetch(page: int, size: int) -> DabangRegionRankingResultModel | None:
            assert isinstance(spec, MetricSpec)
            return client.run_request_region_info_real_estate_ranking_v5(DabangRegionInfoRealEstateRankingV5RequestParameterModel(
                unit='complex' if unit == '단지' else 'region',
                metric=spec.metric,
                scope_region_gid=scope.gid,
                complex_type=COMPLEX_TYPE_BY_LABEL[complex_type] if spec.complex_type else None,
                price_type=price_type,
                price_type_list=price_type_list,
                sort=sort,
                page=page,
                limit=size,
            )).result
    else:
        page_limit = REGION_INFO_RANKING_PAGE_LIMIT
        kind_label = kind_label or spec.default_kind
        kinds: dict[str, Any] = {}
        if spec.kind_field and spec.kinds and kind_label:
            kinds[spec.kind_field] = spec.kinds[kind_label]

        def fetch(page: int, size: int) -> DabangRegionRankingResultModel | None:
            assert isinstance(spec, InfoMetricSpec)
            return client.run_request_region_info_ranking_v5(DabangRegionInfoRankingV5RequestParameterModel(
                topic=spec.topic,
                metric=spec.metric,
                scope_region_gid=scope.gid,
                school_type=spec.school_type,
                school_advancement_type=spec.advancement,
                sort=sort,
                page=page,
                limit=size,
                **kinds,
            )).result

    entries: list[DabangRegionRankingEntry] = []
    total: int | None = None
    base_month: str | None = None
    has_more = False
    page = 1
    while len(entries) < limit:
        # 쪽 크기를 바꾸면 쪽 번호가 어긋나 둘째 쪽부터는 한도(page_limit)로 받는다. limit 이 한도보다 크면 첫 쪽도 한도다
        result = fetch(page, min(page_limit, limit - len(entries)) if page == 1 else page_limit)
        ranking = result.ranking if result else None
        if result is None or ranking is None:
            break
        total = ranking.total if total is None else total
        base_month = base_month or _month(result.formatted_price_date)
        rows = [_entry(row, spec.kind) for row in ranking.list_]
        taken = rows[:limit - len(entries)]
        entries += taken
        # 둘째 쪽부터는 한도만큼 받아 limit 에 맞춰 자르므로, 자른 줄이 있으면 서버 hasMore 가 false 여도 더 있다
        # (2026-10-25 실측: 울산 동 84곳을 --limit 70 으로 받으면 둘째 쪽 34곳 중 20곳만 넣는다)
        has_more = bool(ranking.has_more) or len(taken) < len(rows)
        if not ranking.has_more or not ranking.list_:
            break
        page += 1
    # 다방은 값이 없는 줄을 '-' 로 준다 (2026-10-25 실측: 세종 동 평균가 33곳 중 8곳). 다른 줄에 값이 있는 칸은 이 항목에
    # 해당하는 칸이라 '-' 인 줄에서는 키를 지우지 않고 null(모름)로 둔다
    applicable = frozenset({'rank', 'name', *VALUE_FIELDS_BY_KIND[spec.kind]})
    applicable |= {key for entry in entries for key, value in entry if value is not None}
    for entry in entries:
        entry._applicable = applicable
    shown_kind = kind_label if isinstance(spec, InfoMetricSpec) and spec.kinds else None
    notes = []
    if has_more:
        among = f' {total}곳 중' if total is not None else ''
        label = f'{metric_label}({shown_kind})' if shown_kind else metric_label
        notes.append(note('일부', f'{scope.name} 안 {unit}{among} {label} {order} 앞 {len(entries)}곳입니다. 더 보려면 --limit 을 늘리세요'))
    # 학원수·진학률 순위는 상위 지역을 시·도까지만 준다 (2026-10-25 실측: 전국 외국어 학원 1위 '신사동' area '서울')
    if scope.kind != 'district' and any(entry.area and ' ' not in entry.area for entry in entries):
        notes.append(note('참고', 'area 가 시·도까지만 와서 같은 이름의 동은 어느 시·군·구인지 알 수 없습니다. 범위를 시·군·구로 주면 그 안의 동만 나옵니다'))
    return DabangRegionRanking(
        scope=scope, unit=unit, metric=metric_label, kind=shown_kind, base_month=base_month, total=total,
        returned=len(entries), has_more=has_more, rankings=entries, notes=notes,
    )
