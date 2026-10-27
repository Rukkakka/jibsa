from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import (
    DabangRoomItemModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangRankingGroupModel(ResponseModel):
    """동네정보 요약의 순위 ('60위' 처럼 글자로 온다). 구는 `cityName` 이다."""

    formatted_national_rank: Annotated[
        str | None,
        Field(description="전국 순위 ('60위')", alias='formattedNationalRank')
    ] = None
    state_name: Annotated[
        str | None,
        Field(description="시·도 ('서울')", alias='stateName')
    ] = None
    formatted_state_rank: Annotated[
        str | None,
        Field(description='시·도 안 순위', alias='formattedStateRank')
    ] = None
    city_name: Annotated[
        str | None,
        Field(description="시·군·구 ('강남구')", alias='cityName')
    ] = None
    formatted_city_rank: Annotated[
        str | None,
        Field(description='시·군·구 안 순위', alias='formattedCityRank')
    ] = None


class DabangCompositionModel(ResponseModel):
    """요약 칸의 거래 유형별 수 (매매·전세·월세)."""

    name: Annotated[
        str,
        Field(description='거래 유형')
    ]
    value: Annotated[
        float | None,
        Field(description='수')
    ] = None


class DabangDistributionModel(ResponseModel):
    """요약의 매물 유형 칸 하나 (주택/빌라·오피스텔·아파트).

    매물수·거래량은 `value` 와 `compositionList`(거래 유형별), 평균가는 `salePrice`·`leasePrice`(만원)다.
    """

    name: Annotated[
        str,
        Field(description='매물 유형')
    ]
    value: Annotated[
        float | None,
        Field(description='수')
    ] = None
    sale_price: Annotated[
        float | None,
        Field(description='평균 매매가 (만원, 평균가)', alias='salePrice')
    ] = None
    lease_price: Annotated[
        float | None,
        Field(description='평균 전세가 (만원, 평균가)', alias='leasePrice')
    ] = None
    composition_list: Annotated[
        list[DabangCompositionModel],
        Field(description='거래 유형별 수', alias='compositionList')
    ] = []


class DabangPopulationGroupModel(ResponseModel):
    """인구 요약의 성별·연령 칸 하나."""

    gender_type_name: Annotated[
        str | None,
        Field(description="성별 ('남성')", alias='genderTypeName')
    ] = None
    age_type_name: Annotated[
        str | None,
        Field(description="연령대 ('20대')", alias='ageTypeName')
    ] = None
    count: Annotated[
        int | None,
        Field(description='인구')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='비율 (%)')
    ] = None


class DabangRegionInfoSummaryResultModel(ResponseModel):
    """동네정보 요약 `result`. 매물정보·시세정보는 `distributionList`·`distributionDetailList`, 인구는 `totalCount` 와
    성별·연령 목록이 온다. 모두 `rankingGroup`(전국·시도·구 순위)과 기준 달 `updateDate`('26.10')가 있다.
    """

    distribution_list: Annotated[
        list[DabangDistributionModel] | None,
        Field(description='매물 유형별 값', alias='distributionList')
    ] = None
    distribution_detail_list: Annotated[
        list[DabangDistributionModel] | None,
        Field(description='매물 유형별 거래 유형 나눔', alias='distributionDetailList')
    ] = None
    total_count: Annotated[
        int | None,
        Field(description='인구', alias='totalCount')
    ] = None
    gender_distribution_list: Annotated[
        list[DabangPopulationGroupModel],
        Field(description='성별', alias='genderDistributionList')
    ] = []
    age_distribution_list: Annotated[
        list[DabangPopulationGroupModel],
        Field(description='연령대', alias='ageDistributionList')
    ] = []
    ranking_group: Annotated[
        DabangRankingGroupModel | None,
        Field(description='순위', alias='rankingGroup')
    ] = None
    update_date: Annotated[
        str | None,
        Field(description="기준 달 ('26.10')", alias='updateDate')
    ] = None


class DabangRegionInfoRegionalSummaryV5ResponseModel(DabangV5ResponseModel[DabangRegionInfoSummaryResultModel]):
    """`GET /api/v5/region-info/{topic}/regional/summary` 응답."""


class DabangCountModel(ResponseModel):
    """시설·학교 수 한 칸. 수는 '1,074개' 처럼 글자로 온다. 이름 키는 시설(`facilityName`)·설립(`establishmentTypeName`)·
    학원 종류(`academyTypeName`) 중 하나다.
    """

    facility_name: Annotated[
        str | None,
        Field(description='시설 이름', alias='facilityName')
    ] = None
    establishment_type_name: Annotated[
        str | None,
        Field(description="설립 ('국공립', '사립')", alias='establishmentTypeName')
    ] = None
    academy_type_name: Annotated[
        str | None,
        Field(description="학원 종류 ('예체능')", alias='academyTypeName')
    ] = None
    formatted_count: Annotated[
        str | None,
        Field(description="수 ('204개')", alias='formattedCount')
    ] = None


class DabangCountGroupModel(ResponseModel):
    """시설·학교 묶음 하나. 묶음 이름 키는 탭마다 다르다 (`amenityTypeName`·`mobilityTypeName`·`lifeSafetyTypeName`·
    `schoolTypeName`).
    """

    amenity_type_name: Annotated[
        str | None,
        Field(description="편의시설 묶음 ('생활편의시설')", alias='amenityTypeName')
    ] = None
    mobility_type_name: Annotated[
        str | None,
        Field(description="교통 묶음 ('교통시설')", alias='mobilityTypeName')
    ] = None
    life_safety_type_name: Annotated[
        str | None,
        Field(description="안전 묶음 ('안전시설')", alias='lifeSafetyTypeName')
    ] = None
    school_type_name: Annotated[
        str | None,
        Field(description="학교 종류 ('초등학교')", alias='schoolTypeName')
    ] = None
    count_list: Annotated[
        list[DabangCountModel],
        Field(description='수', alias='countList')
    ] = []


class DabangAcademyCountModel(ResponseModel):
    """학원 종류별 수."""

    count_list: Annotated[
        list[DabangCountModel],
        Field(description='학원 종류별 수', alias='countList')
    ] = []


class DabangRegionInfoCountResultModel(ResponseModel):
    """동네정보 수 `result`. 편의·교통·안전은 `facilityCountList`, 학군은 `schoolCountList`·`academyCount` 다."""

    facility_count_list: Annotated[
        list[DabangCountGroupModel],
        Field(description='시설 묶음', alias='facilityCountList')
    ] = []
    school_count_list: Annotated[
        list[DabangCountGroupModel],
        Field(description='학교 종류', alias='schoolCountList')
    ] = []
    academy_count: Annotated[
        DabangAcademyCountModel | None,
        Field(description='학원', alias='academyCount')
    ] = None


class DabangRegionInfoRegionalCountV5ResponseModel(DabangV5ResponseModel[DabangRegionInfoCountResultModel]):
    """`GET /api/v5/region-info/{topic}/regional/count` 응답."""


class DabangPopularRoomResultModel(ResponseModel):
    """인기 매물 `result`. 매물 칸은 목록 칸과 같은 꼴이지만 동 번호·좌표가 없다."""

    list_: Annotated[
        list[DabangRoomItemModel],
        Field(description='선호도 높은 순 매물', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='순위가 있는 매물 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRegionInfoRoomRegionalPopularRoomV5ResponseModel(DabangV5ResponseModel[DabangPopularRoomResultModel]):
    """`GET /api/v5/region-info/room/regional/popular-room` 응답."""
