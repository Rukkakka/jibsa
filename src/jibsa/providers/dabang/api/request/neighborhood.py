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


DabangRegionInfoSummaryTopic = Literal['room', 'real-estate', 'population']
DabangRegionInfoCountTopic = Literal['school', 'amenity', 'mobility', 'life-safety']
DabangPopularBuildingCategory = Literal['HOUSE_VILLA', 'OFFICETEL', 'APT']
DabangPopularPriceType = Literal['MONTHLY_RENT', 'LEASE', 'SALE']
# 인기 매물 한 번에 받을 수 있는 수 (웹은 30, 50 까지 확인, 2026-10-25)
POPULAR_ROOM_PAGE_LIMIT: int = 50


class DabangRegionInfoRegionalSummaryV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/{topic}/regional/summary` 쿼리 (동네정보 탭 하나의 요약과 전국·시도·구 순위).

    Args:
        topic: 'room' 매물정보, 'real-estate' 시세정보, 'population' 인구 (경로).
        region_gid: 다방 동 번호.
        summary_type: 매물정보·시세정보의 항목 (ROOM_COUNT 매물수, TRADE_VOLUME 거래량, REACTION_SCORE 선호도,
            AVERAGE_PRICE 평균가, PYEONG_PRICE 평당가). 인구는 없다.
    """

    topic: Annotated[
        DabangRegionInfoSummaryTopic,
        Field(exclude=True, description='동네정보 탭 (경로)')
    ]
    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]
    summary_type: Annotated[
        Literal['ROOM_COUNT', 'TRADE_VOLUME', 'REACTION_SCORE', 'AVERAGE_PRICE', 'PYEONG_PRICE'] | None,
        Field(description='요약 항목 (매물정보·시세정보)', alias='summaryType')
    ] = None

    @model_validator(mode='after')
    def summary_type_matches_topic(self) -> Self:
        if self.topic == 'population' and self.summary_type is not None:
            raise ValueError('인구 요약은 summaryType 을 받지 않습니다')
        if self.topic != 'population' and self.summary_type is None:
            raise ValueError(f'{self.topic} 요약에는 summaryType 이 있어야 합니다')
        return self


class DabangRegionInfoRegionalCountV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/{topic}/regional/count` 쿼리 (동네정보 탭의 시설·학교 수를 한 번에).

    Args:
        topic: 'school' 학군, 'amenity' 편의시설, 'mobility' 교통/차량, 'life-safety' 생활안전 (경로).
        region_gid: 다방 동 번호.
    """

    topic: Annotated[
        DabangRegionInfoCountTopic,
        Field(exclude=True, description='동네정보 탭 (경로)')
    ]
    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]


class DabangRegionInfoRoomRegionalPopularRoomV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/room/regional/popular-room` 쿼리 (동 안 인기 매물).

    Args:
        region_gid: 다방 동 번호.
        building_category_list: 매물 유형 (주택·빌라, 오피스텔, 아파트). 같은 키를 값마다 반복해 보낸다.
        price_type_list: 거래 유형.
        sort: 선호도 높은 순 (웹 값 'DESC').
        limit: 한 쪽 매물 수 (최대 50).
        page: 쪽 번호 (1부터).
    """

    region_gid: Annotated[
        int,
        Field(gt=0, description='다방 동 번호', alias='regionGid')
    ]
    building_category_list: Annotated[
        list[DabangPopularBuildingCategory],
        Field(min_length=1, description='매물 유형', alias='buildingCategoryList')
    ] = ['HOUSE_VILLA', 'OFFICETEL', 'APT']
    price_type_list: Annotated[
        list[DabangPopularPriceType],
        Field(min_length=1, description='거래 유형', alias='priceTypeList')
    ] = ['MONTHLY_RENT', 'LEASE', 'SALE']
    sort: Annotated[
        Literal['DESC'],
        Field(description='선호도 높은 순')
    ] = 'DESC'
    limit: Annotated[
        int,
        Field(ge=1, le=POPULAR_ROOM_PAGE_LIMIT, description='한 쪽 매물 수')
    ] = POPULAR_ROOM_PAGE_LIMIT
    page: Annotated[
        int,
        Field(ge=1, description='쪽 번호')
    ] = 1
