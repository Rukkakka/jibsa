from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
    Self,
)


DabangRankingComplexType = Literal['APT', 'OFFICETEL']
DabangWatchBaseOn = Literal['JUST_BEFORE', 'YESTERDAY', 'LAST_WEEK', 'LAST_MONTH']
DabangTradeBaseOn = Literal['CURRENT_WEEK', 'LAST_WEEK', 'CURRENT_MONTH', 'LAST_MONTH', 'CURRENT_YEAR']
DabangRankingUnit = Literal['region', 'complex']
DabangRankingMetric = Literal[
    'average-price', 'pyeong-price', 'trade-volume', 'room-count', 'average-price-change', 'max-price-change',
    'reaction-score', 'household-count', 'age', 'lease-rate', 'gap-price',
]
DabangRankingPriceType = Literal['SALE', 'LEASE', 'MONTHLY_RENT']
# 순위 한 번에 받을 수 있는 수 (웹은 10~20, 50 까지 확인)
RANKING_PAGE_LIMIT: int = 50
# 단지 순위에만 있는 항목
COMPLEX_ONLY_METRICS: frozenset[str] = frozenset({'lease-rate', 'gap-price'})
# 동네정보 순위 (동 단위만): 학교·학원·진학률, 인구, 편의·교통·안전 시설 수
DabangRegionInfoTopic = Literal['school', 'population', 'amenity', 'mobility', 'life-safety']
DabangRegionInfoRankingMetric = Literal[
    'school-advancement', 'academy', 'elementary-school', 'middle-school', 'high-school', 'kinder-school', 'nursery-school',
    'count', 'year-of-year-change',
    'living', 'medical', 'dining', 'shopping', 'sports',
    'transit', 'parking-lot', 'charge-station', 'maintenance-shop',
    'safety-facility', 'safety-organization', 'inconvenience',
]
DabangSchoolAdvancementType = Literal[
    'SCIENCE_HIGH_SCHOOL', 'FOREIGN_HIGH_SCHOOL', 'AUTONOMOUS_PRIVATE_HIGH_SCHOOL', 'ART_PHYSICAL_HIGH_SCHOOL',
    'UNIVERSITY', 'COLLEGE',
]
DabangAcademyType = Literal[
    'ADMISSION_EXAM', 'ARTS_SPORTS', 'FOREIGN_LANGUAGE', 'SPECIALIZED', 'COMPREHENSIVE', 'HUMANITIES_SOCIAL', 'PROGRAMMING',
]
DabangSchoolEstablishmentType = Literal['PUBLIC', 'PRIVATE', 'HOME', 'WORKPLACE', 'COOPERATIVE']
# 동네정보 순위 한 번에 받을 수 있는 수. 넘으면 400 '페이지 당 호출 가능한 최대 행수는 30를 초과할 수 없습니다' (2026-10-25
# 실측: 학교·학원·진학률·인구·인구 증감·의료·교통·안전 모두 31 이면 400, 부동산 순위는 50 까지 된다)
REGION_INFO_RANKING_PAGE_LIMIT: int = 30


class DabangRealTimeWatchRankingsV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-time-watch-rankings/{unit}` 쿼리 (전국에서 지금 많이 보는 단지·동, 늘 50곳).

    Args:
        unit: 'complex' 단지, 'region' 동 (경로).
        complex_type: 아파트·오피스텔.
        base_on: 방금전·어제·지난주·지난달 (웹 고르기 값).
        limit: 웹 값 50 (적게 줘도 50곳을 준다, 2026-10-25 실측).
    """

    unit: Annotated[
        DabangRankingUnit,
        Field(exclude=True, description='단지·동 (경로)')
    ]
    complex_type: Annotated[
        DabangRankingComplexType,
        Field(description='단지 유형', alias='complexType')
    ] = 'APT'
    base_on: Annotated[
        DabangWatchBaseOn,
        Field(description='기간', alias='baseOn')
    ] = 'JUST_BEFORE'
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='순위 수')
    ] = 50


class DabangRealPriceTradeRankingsComplexV5RequestParameterModel(RequestModel):
    """`GET /api/v5/real-price/trade/rankings/complex` 쿼리 (전국에서 거래 많은 단지).

    Args:
        complex_type: 아파트·오피스텔.
        real_price_type: 'SALE' 매매, 'LEASE' 전세.
        base_on: 이번주·지난주·이번달·지난달·올해 (웹 고르기 값).
        limit: 순위 수. 웹 값 50 을 쓴다 (작게 주면 500 을 줄 때가 있다, 2026-10-25 실측: limit 2 는 500, 50 은 200).
    """

    complex_type: Annotated[
        DabangRankingComplexType,
        Field(description='단지 유형', alias='complexType')
    ] = 'APT'
    real_price_type: Annotated[
        Literal['SALE', 'LEASE'],
        Field(description='매매·전세', alias='realPriceType')
    ] = 'SALE'
    base_on: Annotated[
        DabangTradeBaseOn,
        Field(description='기간', alias='baseOn')
    ] = 'CURRENT_WEEK'
    limit: Annotated[
        int,
        Field(ge=1, le=50, description='순위 수')
    ] = 50


class DabangRegionInfoRealEstateRankingV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/real-estate/ranking/{unit}/{metric}` 쿼리 (범위 안 동·단지 순위).

    항목마다 받는 값이 다르다 (real-estate 청크, 2026-10-25): 평균가·평당가·시세증감·최고가증감은 `priceType` 하나,
    거래량·매물수·선호도는 `priceTypeList`, 전세가율·갭가격(단지만)은 유형만, 세대수·연식은 유형도 받지 않는다.

    Args:
        unit: 'region' 동, 'complex' 단지 (경로).
        metric: 항목 (경로).
        scope_region_gid: 범위 (시·도 또는 시·군·구의 다방 번호). 없으면 전국.
        complex_type: 아파트·오피스텔.
        price_type: 거래 유형 하나 (평균가·평당가·시세증감·최고가증감).
        price_type_list: 거래 유형 여럿 (거래량·매물수·선호도).
        sort: 'DESC' 높은 순, 'ASC' 낮은 순.
        page: 쪽 번호.
        limit: 한 쪽 수 (최대 50).
    """

    unit: Annotated[
        DabangRankingUnit,
        Field(exclude=True, description='동·단지 (경로)')
    ]
    metric: Annotated[
        DabangRankingMetric,
        Field(exclude=True, description='항목 (경로)')
    ]
    scope_region_gid: Annotated[
        int | None,
        Field(gt=0, description='범위 다방 번호 (없으면 전국)', alias='scopeRegionGid')
    ] = None
    complex_type: Annotated[
        DabangRankingComplexType | None,
        Field(description='단지 유형', alias='complexType')
    ] = None
    price_type: Annotated[
        Literal['SALE', 'LEASE'] | None,
        Field(description='거래 유형', alias='priceType')
    ] = None
    price_type_list: Annotated[
        list[DabangRankingPriceType] | None,
        Field(description='거래 유형 여럿', alias='priceTypeList')
    ] = None
    sort: Annotated[
        Literal['DESC', 'ASC'],
        Field(description='정렬')
    ] = 'DESC'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
    limit: Annotated[
        int,
        Field(ge=1, le=RANKING_PAGE_LIMIT, description='한 쪽 수')
    ] = 20

    @model_validator(mode='after')
    def metric_matches_unit(self) -> Self:
        if self.unit == 'region' and self.metric in COMPLEX_ONLY_METRICS:
            raise ValueError(f'{self.metric} 순위는 단지 단위에만 있습니다')
        return self



class DabangRegionInfoRankingV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/{topic}/ranking/{metric}` 쿼리 (범위 안 동 순위: 학교·학원 수, 진학률, 인구, 시설 수).

    주제마다 받는 값이 다르다 (school·population·facility·life-safety·traffic 청크, 2026-10-25): 진학률은 `schoolType`
    (중학교 → 고교 유형, 고등학교 → 대학)과 `schoolAdvancementType`, 학원은 `academyType`(없거나 'ALL' 이면 빈 목록이라
    꼭 준다), 학교 수는 `schoolEstablishmentType`, 시설 수는 `facilityType`(없으면 전체). 인구는 성별·연령을 주지 않으면 전체다.
    `regionGid` 를 주면 그 동의 순위(`currentRank`)도 오지만 쓰지 않는다.

    Args:
        topic: 주제 (경로).
        metric: 항목 (경로).
        scope_region_gid: 범위 (시·도 또는 시·군·구의 다방 번호). 없으면 전국.
        school_type: 진학률의 학교 ('MIDDLE_SCHOOL' 고교 진학, 'HIGH_SCHOOL' 대학 진학).
        school_advancement_type: 진학 갈래.
        academy_type: 학원 종류.
        school_establishment_type: 학교 설립 구분.
        facility_type: 시설 종류 (주제마다 다른 값, 웹 고르기 값 그대로).
        sort: 'DESC' 높은 순, 'ASC' 낮은 순.
        page: 쪽 번호.
        limit: 한 쪽 수 (최대 30).
    """

    topic: Annotated[
        DabangRegionInfoTopic,
        Field(exclude=True, description='주제 (경로)')
    ]
    metric: Annotated[
        DabangRegionInfoRankingMetric,
        Field(exclude=True, description='항목 (경로)')
    ]
    scope_region_gid: Annotated[
        int | None,
        Field(gt=0, description='범위 다방 번호 (없으면 전국)', alias='scopeRegionGid')
    ] = None
    school_type: Annotated[
        Literal['MIDDLE_SCHOOL', 'HIGH_SCHOOL'] | None,
        Field(description='진학률의 학교', alias='schoolType')
    ] = None
    school_advancement_type: Annotated[
        DabangSchoolAdvancementType | None,
        Field(description='진학 갈래', alias='schoolAdvancementType')
    ] = None
    academy_type: Annotated[
        DabangAcademyType | None,
        Field(description='학원 종류', alias='academyType')
    ] = None
    school_establishment_type: Annotated[
        DabangSchoolEstablishmentType | None,
        Field(description='학교 설립 구분', alias='schoolEstablishmentType')
    ] = None
    facility_type: Annotated[
        str | None,
        Field(pattern=r'^[A-Z_0-9]+$', description='시설 종류', alias='facilityType')
    ] = None
    sort: Annotated[
        Literal['DESC', 'ASC'],
        Field(description='정렬')
    ] = 'DESC'
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
    limit: Annotated[
        int,
        Field(ge=1, le=REGION_INFO_RANKING_PAGE_LIMIT, description='한 쪽 수')
    ] = 20

    @model_validator(mode='after')
    def required_types(self) -> Self:
        if self.metric == 'academy' and self.academy_type is None:
            raise ValueError('학원 순위는 학원 종류가 필요합니다 (없으면 다방이 빈 목록을 준다)')
        if self.metric == 'school-advancement' and (self.school_type is None or self.school_advancement_type is None):
            raise ValueError('진학률 순위는 학교와 진학 갈래가 필요합니다')
        return self
