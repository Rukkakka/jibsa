"""순위의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""
import re
from collections.abc import Mapping

from jibsa.core.errors import JibsaError
from jibsa.core.korean import full_legal_division_code
from jibsa.core.listing import (
    add_unread_date,
    more_hint,
    normalize_address,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import (
    REGION_INFO_PAGE_LIMIT,
    DabangRoomBuildingCategory,
)
from jibsa.providers.dabang.api.request.ranking import (
    RANKING_PAGE_LIMIT,
    DabangRankingMetric,
    DabangRankingPriceType,
    DabangRealPriceTradeRankingsComplexV5RequestParameterModel,
    DabangRealTimeWatchRankingsV5RequestParameterModel,
    DabangRegionInfoRankingMetric,
    DabangRegionInfoRankingV5RequestParameterModel,
    DabangRegionInfoRealEstateRankingV5RequestParameterModel,
    DabangRegionInfoRoomRankingV5RequestParameterModel,
    DabangRegionInfoTopic,
    DabangRoomRankingMetric,
    DabangSchoolAdvancementType,
    DabangTradeBaseOn,
    DabangWatchBaseOn,
)
from jibsa.providers.dabang.api.response.ranking import (
    DabangRegionRankingItemModel,
    DabangRegionRankingResultModel,
)
from jibsa.providers.dabang.service.common.functions import (
    COMPLEX_TYPE_BY_LABEL,
    ESTABLISHMENT_BY_LABEL,
    NURSERY_ESTABLISHMENT_BY_LABEL,
    POPULAR_BUILDING_BY_LABEL,
    VILLA_LABEL,
    building_years,
    count_of,
    household_count,
    manwon_from_text,
    more_after,
    number_of,
)
from jibsa.providers.dabang.service.ranking.models import (
    DabangRegionRanking,
    DabangRegionRankingEntry,
    DabangTradeRanking,
    DabangTradeRankings,
    DabangWatchRanking,
    DabangWatchRankings,
)
from jibsa.providers.dabang.service.region.functions import DONG_NAME_PATTERN
from jibsa.providers.dabang.service.region.models import DabangScope

from typing import (
    Any,
    Literal,
    NamedTuple,
)


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
REGION_RANKING_MAX_LIMIT: int = 100
# 동네정보 '매물정보' 랭킹 (room-info 청크, 2026-11-13). 매물 유형에 주택/빌라가 있는 순위는 이 화면뿐이라 -t 빌라 로 고른다.
# 항목은 매물수·거래량·선호도, 동 순위만 있다 (빌라 이름은 service/common/functions.py 의 `VILLA_LABEL`)
ROOM_RANKING_METRIC_BY_LABEL: dict[str, DabangRoomRankingMetric] = {
    '매물수': 'room-count', '거래량': 'trade-volume', '선호도': 'reaction-score',
}
# -t 라벨 → 매물 유형 값과 웹 고르기 이름. 웹 순서(주택/빌라·오피스텔·아파트)대로 둔다. 값은 인기 매물(`popular-listings`)의
# 매물 유형과 같은 buildingCategoryList 라 그 표에서 만들고, 웹 이름이 라벨과 다른 빌라만 따로 적는다
ROOM_RANKING_WEB_NAME_BY_LABEL: dict[str, str] = {VILLA_LABEL: '주택/빌라'}
ROOM_RANKING_BUILDING_BY_LABEL: dict[str, tuple[DabangRoomBuildingCategory, str]] = {
    label: (value, ROOM_RANKING_WEB_NAME_BY_LABEL.get(label, label)) for label, value in POPULAR_BUILDING_BY_LABEL.items()
}
# 웹 동네정보 탭 이름 (어느 랭킹 화면의 순위인지). 부동산 순위는 '시세정보', 매물 유형 순위는 '매물정보' 탭이다
TAB_BY_TOPIC: dict[DabangRegionInfoTopic, str] = {
    'school': '학군', 'population': '인구수', 'amenity': '편의시설', 'mobility': '교통/차량', 'life-safety': '생활안전',
}
REAL_ESTATE_TAB: str = '시세정보'
ROOM_TAB: str = '매물정보'
AGE_YEARS_PATTERN: re.Pattern[str] = re.compile(r'(\d+)\s*년')
# 기준 달 글자: '26년 10월'
MONTH_TEXT_PATTERN: re.Pattern[str] = re.compile(r'(\d{2})년\s*(\d{1,2})월')
ValueKind = Literal['price', 'count', 'percent', 'change', 'age', 'score', 'population-change', 'count-change']


class MetricSpec(NamedTuple):
    """부동산 순위 항목 하나 (동·단지): 경로 이름, 값 종류, 받는 거래 유형 꼴, 받는 단지 유형 꼴, 단지만인지.

    `types` 는 웹 랭킹 화면의 단지 유형 고르기 꼴이다 (real-estate 청크, 2026-11-13): 'one' 은 하나만 고르고 기본 아파트
    (평균가·평당가·시세증감·최고가증감), 'many' 는 아파트·오피스텔을 함께 고를 수 있고 기본이 둘 다라 `complexType` 을 빼고
    보내 합산 순위를 받는다 (거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격, `complexType: size===2 ? null : 하나`),
    'none' 은 받지 않는다. `comparison` 은 증감 항목이 무엇과 견준 수인지 웹 화면 문구다.
    """

    metric: DabangRankingMetric
    kind: ValueKind
    trade: Literal['one', 'many', 'none']
    types: Literal['one', 'many', 'none']
    complex_only: bool = False
    comparison: str | None = None


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
    kinds: Mapping[str, str] | None = None
    default_kind: str | None = None


# --kind 값: 웹 고르기 이름에서 띄어쓰기·'/'·괄호를 뺀 것 (school·facility·traffic·life-safety 청크, 2026-10-25)
ACADEMY_KIND_BY_LABEL: dict[str, str] = {
    '입시': 'ADMISSION_EXAM', '예체능': 'ARTS_SPORTS', '외국어': 'FOREIGN_LANGUAGE', '특성화': 'SPECIALIZED',
    '종합': 'COMPREHENSIVE', '인문사회': 'HUMANITIES_SOCIAL', '코딩': 'PROGRAMMING',
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


def _school_count(metric: DabangRegionInfoRankingMetric, kinds: Mapping[str, str]) -> InfoMetricSpec:
    # 학교·유치원 수의 --kind 는 search schools --establishment 와 같은 설립 구분 표다 (어린이집만 공공·민간·가정·직장·협동)
    return InfoMetricSpec('school', metric, 'count', kind_field='school_establishment_type', kinds=kinds)


def _advancement(school_type: Literal['MIDDLE_SCHOOL', 'HIGH_SCHOOL'], advancement: DabangSchoolAdvancementType) -> InfoMetricSpec:
    return InfoMetricSpec('school', 'school-advancement', 'percent', school_type=school_type, advancement=advancement)


# 다방 '부동산 랭킹' 항목 (real-estate 청크의 이름표와 요청 값, 2026-10-25)과 동네정보 랭킹 항목 (동만)
METRIC_BY_LABEL: dict[str, MetricSpec | InfoMetricSpec] = {
    '평균가': MetricSpec('average-price', 'price', 'one', 'one'),
    '평당가': MetricSpec('pyeong-price', 'price', 'one', 'one'),
    '거래량': MetricSpec('trade-volume', 'count', 'many', 'many'),
    '매물수': MetricSpec('room-count', 'count', 'many', 'many'),
    '시세증감': MetricSpec('average-price-change', 'change', 'one', 'one'),
    '최고가증감': MetricSpec('max-price-change', 'change', 'one', 'one'),
    # 거래증감·매물증감은 웹 기본이 아파트·오피스텔 합산, 매매·전세·월세 모두다 (real-estate 청크 TradeVolumeChange·
    # RoomCountChange 스토어, 2026-11-13). 비교 기준은 웹 화면 문구 그대로다 (같은 청크의 설명 글 '전월대비'·'최근 30일 전 대비')
    '거래증감': MetricSpec('trade-volume-change', 'count-change', 'many', 'many', comparison='전월대비'),
    '매물증감': MetricSpec('room-count-change', 'count-change', 'many', 'many', comparison='최근 30일 전 대비'),
    '선호도': MetricSpec('reaction-score', 'score', 'many', 'many'),
    '세대수': MetricSpec('household-count', 'count', 'none', 'none'),
    '연식': MetricSpec('age', 'age', 'none', 'none'),
    '전세가율': MetricSpec('lease-rate', 'percent', 'none', 'many', complex_only=True),
    '갭가격': MetricSpec('gap-price', 'price', 'none', 'many', complex_only=True),
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
    '초등학교수': _school_count('elementary-school', ESTABLISHMENT_BY_LABEL),
    '중학교수': _school_count('middle-school', ESTABLISHMENT_BY_LABEL),
    '고등학교수': _school_count('high-school', ESTABLISHMENT_BY_LABEL),
    '유치원수': _school_count('kinder-school', ESTABLISHMENT_BY_LABEL),
    '어린이집수': _school_count('nursery-school', NURSERY_ESTABLISHMENT_BY_LABEL),
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
    'count-change': frozenset({'count', 'prev_count', 'change_count', 'change_percent'}),
}


def _manwon(text: str | None) -> float | None:
    """'61.1억', '4,762만', '+1.2억' 같은 금액 글을 만원으로. 부호는 지킨다."""
    if not text:
        return None
    value = text.strip()
    sign = -1 if value.startswith('-') else 1
    amount = manwon_from_text(value.lstrip('+-').removesuffix('만'))
    return None if amount is None else sign * amount


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
                legal_division_code=full_legal_division_code(row.dong_code) if row.dong_code else None,
                viewer_count=row.watch_count,
                change=(
                    None if row.fluctuation is None or row.fluctuation.type is None
                    else f'{FLUCTUATION_LABELS.get(row.fluctuation.type, row.fluctuation.type)} {row.fluctuation.rank}'
                    if row.fluctuation.type in ('UP', 'DOWN') and row.fluctuation.rank
                    else FLUCTUATION_LABELS.get(row.fluctuation.type, row.fluctuation.type)
                ),
            )
            for row in rows
        ],
    )


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
            occupancy_years=building_years(row.description), household_count=household_count(row.description),
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
        trade_type=trade,
        period=period,
        base_period=result.format_base_period if result else None,
        returned=len(rankings),
        rankings=rankings,
        notes=notes,
    )


def _month(text: str | None) -> str | None:
    """'26년 10월' → '2026-10'. 꼴이 다르거나 달력에 없는 달('26년 13월')이면 None."""
    match = MONTH_TEXT_PATTERN.search(text or '')
    return f'20{match.group(1)}-{int(match.group(2)):02d}' if match and 1 <= int(match.group(2)) <= 12 else None


def _price_month(text: str | None, field: str, unreadable: dict[str, list[str]]) -> str | None:
    """다방 기준 달 글자('26년 10월')를 'YYYY-MM' 으로. 값이 없으면('-'·빈 글자) 안내 없이 None 이고, 글자가 있는데 읽지 못하면
    None 으로 내면서 `unreadable[field]` 에 원래 글자를 모으고 공용 모음(`add_unread_date`)에 넣어 `emit` 이 칸별로 한 줄 알린다.
    """
    if text is None or text.strip() in ('', '-'):
        return None
    month = _month(text)
    if month is None:
        unreadable.setdefault(field, []).append(text)
        add_unread_date('시세 기준 달' if field == 'price_month' else '앞 최고가 달', text)
    return month


def _entry(row: DabangRegionRankingItemModel, kind: ValueKind, unreadable: dict[str, list[str]]) -> DabangRegionRankingEntry:
    text = (
        row.formatted_price or row.formatted_count or row.formatted_percentage or row.formatted_age
        or row.formatted_change_rate or row.formatted_score or row.formatted_volume
    )
    entry = DabangRegionRankingEntry(
        rank=row.rank,
        name=row.complex_name or row.region_name,
        area=row.parent_region_name,
        complex_id=row.complex_id,
        value_text=text,
        pyeong_name=row.formatted_pyeong,
        price_month=_price_month(row.formatted_price_date, 'price_month', unreadable),
        price_detail=row.formatted_price_detail,
    )
    if kind == 'price':
        entry.value_manwon = _manwon(row.formatted_price)
    elif kind == 'count':
        # 매물정보 탭 거래량은 formattedVolume 으로 온다
        entry.count = count_of(row.formatted_count or row.formatted_volume)
    elif kind == 'percent':
        entry.percent = number_of(row.formatted_percentage)
    elif kind == 'score':
        entry.score = count_of(row.formatted_score)
    elif kind == 'change':
        entry.value_text = row.formatted_change_rate or text
        entry.change_percent = number_of(row.formatted_change_rate, signed=True)
        entry.change_manwon = _manwon(row.formatted_price)
        if entry.change_manwon is not None and entry.change_percent is not None and entry.change_percent < 0:
            entry.change_manwon = -abs(entry.change_manwon)
        # 최고가증감은 앞 최고가가 formattedMaxPrice 로 온다 (시세증감은 formattedPrevPrice)
        entry.prev_price_manwon = _manwon(row.formatted_prev_price or row.formatted_max_price)
        entry.prev_price_month = _price_month(row.formatted_max_price_date, 'prev_price_month', unreadable)
    elif kind == 'population-change':
        _fill_count_change(entry, row, row.formatted_year_of_year_change_count, row.formatted_year_of_year_change_percentage)
    elif kind == 'count-change':
        # 거래증감·매물증감: formattedCount 가 변화 수, 앞·지금 수가 따로 온다 (2026-11-13 강남구 논현동 '73개' = 72 → 145)
        _fill_count_change(entry, row, row.formatted_count, row.formatted_change_rate)
    else:
        # '44년 6개월' → 44, '1개월 미만'·'8개월' → 0
        years = AGE_YEARS_PATTERN.search(row.formatted_age or '')
        entry.age_years = int(years.group(1)) if years else (0 if '개월' in (row.formatted_age or '') else None)
    return entry


def _fill_count_change(
    entry: DabangRegionRankingEntry,
    row: DabangRegionRankingItemModel,
    change_text: str | None,
    rate_text: str | None,
) -> None:
    """인구증감·거래증감·매물증감 값. 변화 수는 부호 없이('327명', '73개') 온다.

    변화 수는 앞·지금 수가 둘 다 오면 그 차로 낸다. 차는 늘 `formattedCount`·`formattedYearOfYearChangeCount` 와 같았다
    (2026-11-14 약 700행). 둘 중 하나라도 없으면 부호 없는 변화 수에 changeStatus(DECREASE)·변화율 부호로 부호를 붙인다
    (2026-10-25 강남구 도곡동 -0.6%). changeStatus 는 모든 행에 왔지만 빠지고 변화율이 '0%' 로 반올림되면 줄어도 부호를 모른다.
    다방이 '-' 로 주는 칸은 값이 없는 것이라 `value_text` 에 붙이지 않는다 (둘 다 '-' 면 '-').
    """
    shown = [text for text in (change_text, rate_text) if text and text.strip() != '-']
    entry.value_text = f'{shown[0]} ({shown[1]})' if len(shown) == 2 else (shown[0] if shown else change_text or rate_text)
    entry.count = count_of(row.formatted_curr_count)
    entry.prev_count = count_of(row.formatted_prev_count)
    entry.change_percent = number_of(rate_text, signed=True)
    if entry.count is not None and entry.prev_count is not None:
        entry.change_count = entry.count - entry.prev_count
        return
    change = count_of(change_text)
    decreased = row.change_status == 'DECREASE' or (entry.change_percent is not None and entry.change_percent < 0)
    entry.change_count = -abs(change) if change is not None and decreased else change


def is_room_ranking(complex_types: list[str]) -> bool:
    """`-t` 에 빌라가 있어 동네정보 '매물정보' 탭 순위(`region-info/room/ranking`)로 받는지. 부동산 순위('시세정보' 탭)는 아파트·
    오피스텔 단지만 있어 주택/빌라를 받는 순위는 이 탭뿐이다."""
    return VILLA_LABEL in complex_types


def takes_dong_scope(metric_label: str, unit: Literal['동', '단지']) -> bool:
    """동 이름을 범위로 받는 순위인지. 웹 랭킹은 단지 순위(부동산 항목)만 고른 동을 범위로 보낸다. 동 순위와 동네정보 순위는
    시·군·구·시·도만 보낸다 (real-estate·school·facility·population 청크 `city.gid → state.gid`, 2026-11-13). 동 안의 동 순위는 없다.
    """
    return unit == '단지' and not isinstance(METRIC_BY_LABEL[metric_label], InfoMetricSpec)


def check_scope_name(query: str, *, metric_label: str, unit: Literal['동', '단지'], complex_types: list[str]) -> None:
    """동 범위를 받지 않는 순위(동 순위·동네정보)에 동 모양의 이름이 오면 장소 검색 없이 막는다. 동이 아닌 이름(역·오타)은
    `resolve_scope(dong=False)` 가 요청 없이 REGION_NOT_FOUND 로 막는다 (동을 찾게 두면 요청 1회 뒤 동 이름을 권하는 안내가 나가,
    따르면 다시 막혔다. 2026-11-13 리뷰).

    Args:
        complex_types: `-t` 값. 빌라 순위(`is_room_ranking`)면 동 순위만 있어 hint 가 --unit 단지 를 권하지 않는다.

    Raises:
        JibsaError: 동 범위를 받지 않는 순위에 동 이름을 줄 때 (INVALID_ARGUMENT).
    """
    # 리뷰 오탐 (2026-11-14, 근거 고침 2026-11-20): resolve_scope(dong=False) 와 겹치는 검사가 아니다. resolve_scope 는 동 이름을
    # REGION_NOT_FOUND 로 막아 있는 동을 못 찾았다고 알리고 --unit 단지 를 권하지 못한다. 안내(hint)를 만들려면 지표·단위·빌라
    # 순위 여부가 필요한데 resolve_scope 는 이것들을 받지 않아 여기 따로 둔다
    words = query.split()
    if words and not takes_dong_scope(metric_label, unit) and DONG_NAME_PATTERN.fullmatch(words[-1]):
        info = isinstance(METRIC_BY_LABEL[metric_label], InfoMetricSpec)
        what = f'{metric_label} 순위는 동네정보 항목이라' if info else '동 안의 동 순위는 없어'
        # 빌라 순위('매물정보' 탭)는 동 순위만 있어 --unit 단지 를 권하면 따른 뒤 다시 막힌다 (2026-11-14 리뷰)
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'{what} 동 범위({query.strip()})를 받지 않습니다',
            hint=(
                "시·군·구 이름(예: '강남구')을 범위로 주세요" if info or is_room_ranking(complex_types)
                else "동 안 단지 순위는 --unit 단지 를 주고, 동 순위는 시·군·구 이름(예: '강남구')을 범위로 주세요"
            ),
        )


def get_region_ranking(
    client: DabangClient,
    scope: DabangScope,
    *,
    metric_label: str,
    unit: Literal['동', '단지'],
    complex_types: list[str],
    trades: list[str],
    order: Literal['높은순', '낮은순'],
    limit: int,
    kind_label: str | None = None,
) -> DabangRegionRanking:
    """범위(전국·시도·시군구, 단지 순위는 동도) 안 동·단지 순위 (부동산은 50곳, 동네정보는 30곳마다 요청 1회).

    거래 유형은 항목에 맞게 보낸다: 평균가·평당가·시세증감·최고가증감은 하나(기본 매매), 거래량·매물수·거래증감·매물증감·
    선호도는 여럿(기본 전체). 단지 유형도 웹처럼 보낸다: 평균가·평당가·시세증감·최고가증감은 하나(기본 아파트),
    거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 `complex_types` 가 비거나 둘이면 유형을 빼고 보내
    아파트·오피스텔 합산 순위다 (웹 기본). 동네정보 항목(학교·학원·진학률·인구·시설)은 동 단위만 있고 `kind_label` 로 종류를
    고른다 (학원은 기본 입시). `complex_types` 에 빌라가 있으면(`is_room_ranking`) 매물수·거래량·선호도를 동네정보 '매물정보' 탭
    순위로 받는다: 고른 매물 유형(주택/빌라·오피스텔·아파트) 합산 동 순위이고 30곳씩이다 (웹 값).
    동 범위는 부동산 단지 순위만 받는다 (웹도 같다). 동 범위는 `resolve_scope(dong=takes_dong_scope(...))` 가 그럴 때만 만들고,
    동 이름은 CLI 가 `check_scope_name` 으로 먼저 막는다.
    """
    spec = METRIC_BY_LABEL[metric_label]
    sort: Literal['DESC', 'ASC'] = 'ASC' if order == '낮은순' else 'DESC'
    shown_type: str | None = None
    shown_building: str | None = None
    # 여러 거래 유형을 받는 항목(매물정보 탭·부동산 'many')이 보낼 거래 유형. 고르지 않았으면 전체다 (웹 기본)
    chosen_prices = [RANKING_TRADE_BY_LABEL[trade] for trade in trades] or list(RANKING_TRADE_BY_LABEL.values())
    if isinstance(spec, MetricSpec) and is_room_ranking(complex_types):
        tab = ROOM_TAB
        page_limit = REGION_INFO_PAGE_LIMIT
        room_metric = ROOM_RANKING_METRIC_BY_LABEL[metric_label]
        buildings = [value for label, value in ROOM_RANKING_BUILDING_BY_LABEL.items() if label in complex_types]
        names = [name for _, name in buildings]
        shown_building = names[0] if len(names) == 1 else f"{'·'.join(names)} 합산"

        def fetch(page: int, size: int) -> DabangRegionRankingResultModel | None:
            return client.run_request_region_info_room_ranking_v5(DabangRegionInfoRoomRankingV5RequestParameterModel(
                metric=room_metric,
                scope_region_gid=scope.gid,
                building_category_list=[category for category, _ in buildings],
                price_type_list=chosen_prices,
                sort=sort,
                page=page,
                limit=size,
            )).result
    elif isinstance(spec, MetricSpec):
        tab = REAL_ESTATE_TAB
        page_limit = RANKING_PAGE_LIMIT
        complex_type: Literal['APT', 'OFFICETEL'] | None = None
        chosen_types = complex_types
        if spec.types == 'one':
            shown_type = chosen_types[0] if chosen_types else '아파트'
            complex_type = COMPLEX_TYPE_BY_LABEL[shown_type]
        elif spec.types == 'many':
            # 웹은 둘 다 고르면(기본) complexType 을 빼고 보낸다. 강남구 동 거래량 1위가 합산 역삼동 298개, 아파트만 개포동 233개
            # (2026-11-13 웹 캡처·직접 조회)
            if len(chosen_types) == 1:
                shown_type = chosen_types[0]
                complex_type = COMPLEX_TYPE_BY_LABEL[shown_type]
            else:
                shown_type = '아파트·오피스텔 합산'
        price_type: Literal['SALE', 'LEASE'] | None = None
        price_type_list = None
        if spec.trade == 'one':
            price_type = 'LEASE' if trades[:1] == ['전세'] else 'SALE'
        elif spec.trade == 'many':
            price_type_list = chosen_prices

        def fetch(page: int, size: int) -> DabangRegionRankingResultModel | None:
            assert isinstance(spec, MetricSpec)
            return client.run_request_region_info_real_estate_ranking_v5(DabangRegionInfoRealEstateRankingV5RequestParameterModel(
                unit='complex' if unit == '단지' else 'region',
                metric=spec.metric,
                scope_region_gid=scope.gid,
                complex_type=complex_type,
                price_type=price_type,
                price_type_list=price_type_list,
                sort=sort,
                page=page,
                limit=size,
            )).result
    else:
        tab = TAB_BY_TOPIC[spec.topic]
        page_limit = REGION_INFO_PAGE_LIMIT
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
    # 못 읽은 기준 달 글자 (칸 이름 → 원래 글자들)
    unreadable: dict[str, list[str]] = {}
    total: int | None = None
    # 쪽마다 받은 기준 달 글자. 처음 읽은 달이 base_month 다
    base_texts: list[str] = []
    has_more = False
    # 다방이 순위 목록에 섞어 줘서 뺀 빈 항목 수. 뺀 자리도 서버의 순위 칸이라 limit 을 채웠는지 셀 때 더한다 (빼고 센 수로
    # 첫 쪽이 찼는지 보면 limit 이 한도보다 작을 때 다음 쪽을 한도 크기로 물어 첫 쪽 뒤 순위를 건너뛴다)
    dropped = 0
    page = 1
    while len(entries) + dropped < limit:
        # 쪽 크기를 바꾸면 쪽 번호가 어긋나 둘째 쪽부터는 한도(page_limit)로 받는다. limit 이 한도보다 크면 첫 쪽도 한도다
        result = fetch(page, min(page_limit, limit - len(entries)) if page == 1 else page_limit)
        ranking = result.ranking if result else None
        if result is None or ranking is None:
            break
        total = ranking.total if total is None else total
        if result.formatted_price_date is not None:
            base_texts.append(result.formatted_price_date)
        rows = ranking.list_
        page_dropped = ranking.null_items('list_')
        dropped += page_dropped
        taken = [_entry(row, spec.kind, unreadable) for row in rows[:limit - len(entries)]]
        entries += taken
        # 둘째 쪽부터는 한도만큼 받아 limit 에 맞춰 자르므로, 자른 줄이 있으면 서버 hasMore 가 false 여도 더 있다
        # (2026-10-25 실측: 울산 동 84곳을 --limit 70 으로 받으면 둘째 쪽 34곳 중 20곳만 넣는다). 빈 쪽이면 hasMore 가 와도 더 없다
        has_more = more_after(bool(ranking.has_more), len(rows) + page_dropped, cut=len(rows) - len(taken))
        if not ranking.has_more or not (ranking.list_ or page_dropped):
            break
        page += 1
    base_month = next((month for text in base_texts if (month := _month(text))), None)
    unread_base = [text for text in base_texts if text.strip() not in ('', '-')] if base_month is None else []
    if unread_base:
        # 출력 칸 base_month 하나가 null 이라 처음 못 읽은 글자 하나만 알린다
        add_unread_date('순위 기준 달', unread_base[0])
    # 다방은 값이 없는 줄을 '-' 로 준다 (2026-10-25 실측: 세종 동 평균가 33곳 중 8곳). 다른 줄에 값이 있는 칸은 이 항목에
    # 해당하는 칸이라 '-' 인 줄에서는 키를 지우지 않고 null(모름)로 둔다
    applicable = frozenset({'rank', 'name', *VALUE_FIELDS_BY_KIND[spec.kind]})
    applicable |= {key for entry in entries for key, value in entry if value is not None}
    # 글자가 있었는데 못 읽어 null 로 낸 칸은 모름이라 키를 지우지 않는다
    applicable |= set(unreadable)
    for entry in entries:
        entry._applicable = applicable
    shown_kind = kind_label if isinstance(spec, InfoMetricSpec) and spec.kinds else None
    notes = []
    if has_more:
        among = f' {total}곳 중' if total is not None else ''
        label = f'{metric_label}({shown_kind or shown_building})' if shown_kind or shown_building else metric_label
        # --limit 이 이미 최대값이면 늘리라고 하지 않는다 (2026-11-10 리뷰·실측: 서울 단지 평균가 --limit 100 11135곳에 '--limit 을
        # 늘리세요'). 시·도·전국은 범위를 좁히라고 하고, 더 좁힐 수 없는 시·군·구는 --order 로 반대쪽 끝을 보라고 한다
        if scope.kind not in ('district', 'dong'):
            # '범위' 만 쓰면 무엇을 좁히라는지(반경·--limit 으로도 읽힌다) 알 수 없어 줄 범위를 예로 든다 (2026-11-11 리뷰)
            into = '시·군·구(예: 강남구)로' if scope.kind == 'state' else '시·도(예: 서울)나 시·군·구로'
            more = (
                f'--limit 의 최대값은 {REGION_RANKING_MAX_LIMIT}입니다. 더 보려면 범위를 {into} 좁히세요'
                if limit >= REGION_RANKING_MAX_LIMIT else f'더 보려면 --limit 을 늘리거나 범위를 {into} 좁히세요'
            )
        else:
            more = more_hint(limit, REGION_RANKING_MAX_LIMIT, None)
            if limit >= REGION_RANKING_MAX_LIMIT:
                more += '. 반대쪽 끝은 --order 를 바꿔 보세요'
        notes.append(note('일부', f'{scope.name} 안 {unit}{among} {label} {order} 앞 {len(entries)}곳입니다. {more}'))
    if dropped:
        notes.append(null_items_note('다방 순위', dropped))
    # 학원수·진학률 순위는 상위 지역을 시·도까지만 준다 (2026-10-25 실측: 전국 외국어 학원 1위 '신사동' area '서울')
    if scope.kind not in ('district', 'dong') and any(entry.area and ' ' not in entry.area for entry in entries):
        notes.append(note('참고', 'area 가 시·도까지만 와서 같은 이름의 동은 어느 시·군·구인지 알 수 없습니다. 범위를 시·군·구로 주면 그 안의 동만 나옵니다'))
    ranking_result = DabangRegionRanking(
        scope=scope, unit=unit, metric=metric_label, tab=tab, complex_type=shown_type, property_type=shown_building, kind=shown_kind,
        comparison=spec.comparison if isinstance(spec, MetricSpec) else None, base_month=base_month, total=total,
        returned=len(entries), has_more=has_more, rankings=entries, notes=notes,
    )
    ranking_result._base_month_unread = bool(unread_base)
    return ranking_result
