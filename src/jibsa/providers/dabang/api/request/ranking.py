from pydantic import (
    Field,
    model_validator,
)

from jibsa.core.schema import RequestModel
from jibsa.providers.dabang.api.request.common import (
    REGION_INFO_PAGE_LIMIT,
    DabangRoomBuildingCategory,
)
from jibsa.providers.dabang.api.request.school import DabangSchoolEstablishmentType

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
    'trade-volume-change', 'room-count-change', 'reaction-score', 'household-count', 'age', 'lease-rate', 'gap-price',
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
# 동네정보 '매물정보' 랭킹 항목과 매물 유형 (room-info 청크, 2026-11-13). 매물 유형은 여럿 고르고 기본은 셋 다다
DabangRoomRankingMetric = Literal['room-count', 'trade-volume', 'reaction-score']


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
    거래량·매물수·거래증감·매물증감·선호도는 `priceTypeList`, 전세가율·갭가격(단지만)은 유형만, 세대수·연식은 유형도 받지 않는다.

    Args:
        unit: 'region' 동, 'complex' 단지 (경로).
        metric: 항목 (경로).
        scope_region_gid: 범위 (시·도 또는 시·군·구의 다방 번호, 단지 순위는 동 번호도). 없으면 전국. 웹 단지 순위는 고른 동이
            있으면 동 번호를 보낸다 (real-estate 청크 `dong.gid → city.gid → state.gid`, 2026-11-13. 역삼동 10063 → 개나리푸르지오
            1위). 동 순위는 시·군·구·시·도만 보낸다.
        complex_type: 아파트·오피스텔. 거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 빼면 아파트·오피스텔 합산
            순위다 (웹은 두 유형을 모두 고르면 빼고 보낸다, 2026-11-13 real-estate 청크·캡처).
        price_type: 거래 유형 하나 (평균가·평당가·시세증감·최고가증감).
        price_type_list: 거래 유형 여럿 (거래량·매물수·거래증감·매물증감·선호도).
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
        Field(ge=1, le=REGION_INFO_PAGE_LIMIT, description='한 쪽 수')
    ] = 20

    @model_validator(mode='after')
    def required_types(self) -> Self:
        if self.metric == 'academy' and self.academy_type is None:
            raise ValueError('학원 순위는 학원 종류가 필요합니다 (없으면 다방이 빈 목록을 준다)')
        if self.metric == 'school-advancement' and (self.school_type is None or self.school_advancement_type is None):
            raise ValueError('진학률 순위는 학교와 진학 갈래가 필요합니다')
        return self


class DabangRegionInfoRoomRankingV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/room/ranking/{metric}` 쿼리 (범위 안 동 순위: 동네정보 '매물정보' 랭킹의 매물수·거래량·선호도).

    부동산 랭킹(`real-estate/ranking`, 아파트·오피스텔 단지 기준)과 다른 화면이다. 매물 유형에 주택/빌라가 있고 여럿을 함께 고르며
    (웹 기본 셋 다), 동 순위만 있다 (room-info 청크 2026-11-13: `buildingCategoryList`·`priceTypeList` 기본 전체, `limit` 30,
    범위는 고른 시·군·구 → 시·도 `gid`). 웹 거래량 화면은 `baseMonth`(이번 달)도 보내지만 부동산 순위처럼 보내지 않는다
    (2026-11-14 실측: 강남구 빌라 거래량이 보낸 것과 같았다).

    Args:
        metric: 'room-count' 매물수, 'trade-volume' 거래량, 'reaction-score' 선호도 (경로).
        scope_region_gid: 범위 (시·도 또는 시·군·구의 다방 번호). 없으면 전국.
        building_category_list: 매물 유형 (주택/빌라·오피스텔·아파트). 같은 키를 값마다 반복해 보낸다.
        price_type_list: 거래 유형.
        sort: 'DESC' 높은 순, 'ASC' 낮은 순.
        page: 쪽 번호.
        limit: 한 쪽 수 (웹 값 30).
    """

    metric: Annotated[
        DabangRoomRankingMetric,
        Field(exclude=True, description='항목 (경로)')
    ]
    scope_region_gid: Annotated[
        int | None,
        Field(gt=0, description='범위 다방 번호 (없으면 전국)', alias='scopeRegionGid')
    ] = None
    building_category_list: Annotated[
        list[DabangRoomBuildingCategory],
        Field(min_length=1, description='매물 유형', alias='buildingCategoryList')
    ] = ['HOUSE_VILLA', 'OFFICETEL', 'APT']
    price_type_list: Annotated[
        list[DabangRankingPriceType],
        Field(min_length=1, description='거래 유형', alias='priceTypeList')
    ] = ['SALE', 'LEASE', 'MONTHLY_RENT']
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
        Field(ge=1, le=REGION_INFO_PAGE_LIMIT, description='한 쪽 수')
    ] = REGION_INFO_PAGE_LIMIT
