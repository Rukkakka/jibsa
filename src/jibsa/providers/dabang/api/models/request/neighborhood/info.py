"""요청 모델: 동 하나의 동네정보 (neighborhood)."""
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
# 학교·편의·교통·안전 탭의 요약 종류 (웹 요약 칸의 고르기 값, school·facility·traffic·life-safety 청크 tabList, 2026-11-13).
# 학원(ACADEMY)은 요약 종류 이름표에만 있고 요약 칸 고르기에는 없다
DabangSchoolSummaryType = Literal['NURSERY_SCHOOL', 'KINDER_SCHOOL', 'ELEMENTARY_SCHOOL', 'MIDDLE_SCHOOL', 'HIGH_SCHOOL']
DabangAmenitySummaryType = Literal['LIVING', 'MEDICAL', 'DINING', 'SHOPPING', 'SPORTS']
DabangMobilitySummaryType = Literal['TRANSIT', 'PARKING_LOT', 'CHARGE_STATION', 'MAINTENANCE_SHOP']
DabangLifeSafetySummaryType = Literal['SAFETY_FACILITY', 'SAFETY_ORGANIZATION', 'INCONVENIENCE']
# 탭(경로) → 요약 종류를 받는 요청 칸. 인구는 종류가 없다
SUMMARY_TYPE_FIELD_BY_TOPIC: dict[str, str] = {
    'room': 'summary_type',
    'real-estate': 'summary_type',
    'school': 'school_type',
    'amenity': 'amenity_type',
    'mobility': 'mobility_type',
    'life-safety': 'life_safety_type',
}


class DabangRegionInfoRegionalSummaryV5RequestParameterModel(RequestModel):
    """`GET /api/v5/region-info/{topic}/regional/summary` 쿼리 (동네정보 탭 종류 하나의 요약과 전국·시도·구 순위).

    탭마다 종류를 받는 키가 다르다 (room-info·real-estate·school·facility·traffic·life-safety 청크, 2026-11-13): 매물정보·시세정보는
    `summaryType`, 학군 `schoolType`, 편의시설 `amenityType`, 교통/차량 `mobilityType`, 생활안전 `lifeSafetyType`, 인구는 없다.
    학교·안전의 종류 값은 순위 항목 이름과 다르다 (`schoolType=ELEMENTARY`·`lifeSafetyType=SAFETY` 는 400 '유형은 필수입니다',
    2026-11-14 실측. 웹 값은 `ELEMENTARY_SCHOOL`·`SAFETY_FACILITY`).

    Args:
        topic: 'room' 매물정보, 'real-estate' 시세정보, 'population' 인구, 'school' 학군, 'amenity' 편의시설, 'mobility' 교통/차량,
            'life-safety' 생활안전 (경로).
        region_gid: 다방 동 번호.
        summary_type: 매물정보·시세정보의 항목 (ROOM_COUNT 매물수, TRADE_VOLUME 거래량, REACTION_SCORE 선호도,
            AVERAGE_PRICE 평균가, PYEONG_PRICE 평당가).
        school_type: 학군 종류 (어린이집·유치원·초·중·고등학교).
        amenity_type: 편의시설 종류 (생활 편의·의료·외식·대형 쇼핑·체육).
        mobility_type: 교통/차량 종류 (교통·주차·주유·차량관리).
        life_safety_type: 생활안전 종류 (안전시설·안전기관·불편요소).
    """

    topic: Annotated[
        DabangRegionInfoSummaryTopic | DabangRegionInfoCountTopic,
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
    school_type: Annotated[
        DabangSchoolSummaryType | None,
        Field(description='학군 종류', alias='schoolType')
    ] = None
    amenity_type: Annotated[
        DabangAmenitySummaryType | None,
        Field(description='편의시설 종류', alias='amenityType')
    ] = None
    mobility_type: Annotated[
        DabangMobilitySummaryType | None,
        Field(description='교통/차량 종류', alias='mobilityType')
    ] = None
    life_safety_type: Annotated[
        DabangLifeSafetySummaryType | None,
        Field(description='생활안전 종류', alias='lifeSafetyType')
    ] = None

    @model_validator(mode='after')
    def type_matches_topic(self) -> Self:
        # 탭에 맞는 종류 칸 하나만 있어야 한다. 빠지면 다방이 400 '유형은 필수입니다' 를 준다
        wanted = SUMMARY_TYPE_FIELD_BY_TOPIC.get(self.topic)
        for field in dict.fromkeys(SUMMARY_TYPE_FIELD_BY_TOPIC.values()):
            given = getattr(self, field) is not None
            if field == wanted and not given:
                raise ValueError(f'{self.topic} 요약에 빠진 칸: {field}')
            if field != wanted and given:
                raise ValueError(f'{self.topic} 요약이 받지 않는 칸: {field}')
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
