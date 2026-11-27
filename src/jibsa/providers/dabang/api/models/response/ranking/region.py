"""응답 모델: 범위 안 동·단지 순위 (region-ranking)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangRegionRankingItemModel(DabangBaseResponseModel):
    """범위 안 순위 한 칸. 값은 항목마다 다른 글자 키로 온다: `formattedPrice`('61.1억'), `formattedCount`('27개',
    '6,702세대', '86,513명'), `formattedPercentage`('133.3%', 진학률 '2%'), `formattedAge`('44년 6개월'),
    `formattedChangeRate`('+0.8%'), `formattedScore`('19점'). 동네정보 '매물정보' 랭킹의 거래량만 `formattedVolume`('266개')이다.

    최고가증감은 `formattedPrice` 가 오른 금액이고 `formattedMaxPrice` 가 앞 최고가다 (2026-10-25 강남구 단지 1위
    아이파크삼성: 15.2억 = 62.8억 × 24.2%). 인구 증감은 `formattedYearOfYearChangeCount` 가 부호 없이('327명') 오고
    줄었는지는 `changeStatus`(INCREASE·DECREASE)와 `formattedYearOfYearChangePercentage`('-0.6%')로 안다.
    거래증감·매물증감은 `formattedCount` 가 변화 수, `formattedPrevCount`·`formattedCurrCount` 가 앞·지금 수,
    `formattedChangeRate` 가 변화율이다 (2026-11-13 강남구 동 거래증감 1위 논현동: '73개' = 72개 → 145개, '+101.4%'). 단지 순위
    (`--unit 단지`)도 같은 키로 온다 (2026-11-14 강남구 단지 거래증감 '43개 (+477.8%)' = 9 → 52, 매물증감 '2개 (+28.6%)' = 7 → 9).
    거래·매물이 없는 줄은 '-' 가 아니라 '0개'·'0%' 로 온다 (2026-11-14 세종 동 33곳·단지 하위 100곳).
    """

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    parent_region_name: Annotated[
        str | None,
        Field(description="상위 지역 ('서울 강남구', 단지는 동까지)", alias='parentRegionName')
    ] = None
    region_name: Annotated[
        str | None,
        Field(description='동 이름 (동 순위)', alias='regionName')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 순위)', alias='complexId')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름 (단지 순위)', alias='complexName')
    ] = None
    formatted_price: Annotated[
        str | None,
        Field(description="금액 글자 ('61.1억', '4,762만')", alias='formattedPrice')
    ] = None
    formatted_count: Annotated[
        str | None,
        Field(description="수 글자 ('27개', '6,702세대', 거래증감·매물증감은 변화 수 '73개')", alias='formattedCount')
    ] = None
    formatted_percentage: Annotated[
        str | None,
        Field(description="비율 글자 ('133.3%')", alias='formattedPercentage')
    ] = None
    formatted_age: Annotated[
        str | None,
        Field(description="연식 ('44년 6개월')", alias='formattedAge')
    ] = None
    formatted_change_rate: Annotated[
        str | None,
        Field(description="변화율 ('+0.8%', 거래증감 '+101.4%')", alias='formattedChangeRate')
    ] = None
    formatted_prev_price: Annotated[
        str | None,
        Field(description='비교 기준 금액', alias='formattedPrevPrice')
    ] = None
    formatted_price_date: Annotated[
        str | None,
        Field(description="금액 기준 달 ('26년 5월')", alias='formattedPriceDate')
    ] = None
    formatted_pyeong: Annotated[
        str | None,
        Field(description="평형 ('93평')", alias='formattedPyeong')
    ] = None
    formatted_price_detail: Annotated[
        str | None,
        Field(description="금액 설명 ('매매 90억 / 전세 14.5억')", alias='formattedPriceDetail')
    ] = None
    formatted_max_price: Annotated[
        str | None,
        Field(description="앞 최고가 (최고가증감, '62.8억')", alias='formattedMaxPrice')
    ] = None
    formatted_max_price_date: Annotated[
        str | None,
        Field(description="앞 최고가 달 (최고가증감, '23년 10월')", alias='formattedMaxPriceDate')
    ] = None
    formatted_score: Annotated[
        str | None,
        Field(description="선호도 점수 ('19점')", alias='formattedScore')
    ] = None
    formatted_volume: Annotated[
        str | None,
        Field(description="거래량 ('266개', 동네정보 '매물정보' 랭킹)", alias='formattedVolume')
    ] = None
    formatted_curr_count: Annotated[
        str | None,
        Field(description="지금 수 (인구 증감은 올해 인구 '68,936명', 거래증감·매물증감은 '145개')", alias='formattedCurrCount')
    ] = None
    formatted_prev_count: Annotated[
        str | None,
        Field(description="앞 수 (인구 증감은 한 해 전 인구, 거래증감·매물증감은 '72개')", alias='formattedPrevCount')
    ] = None
    formatted_year_of_year_change_count: Annotated[
        str | None,
        Field(description="한 해 사이 인구 변화 (부호 없음, '327명')", alias='formattedYearOfYearChangeCount')
    ] = None
    formatted_year_of_year_change_percentage: Annotated[
        str | None,
        Field(description="한 해 사이 인구 변화율 ('-0.6%')", alias='formattedYearOfYearChangePercentage')
    ] = None
    change_status: Annotated[
        str | None,
        Field(description='변화 방향 (INCREASE·DECREASE·UNCHANGED)', alias='changeStatus')
    ] = None


class DabangRegionRankingPageModel(DabangBaseResponseModel):
    """순위 한 쪽."""

    list_: Annotated[
        list[DabangRegionRankingItemModel],
        Field(description='순위', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='범위 안 순위가 있는 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRegionRankingResultModel(DabangBaseResponseModel):
    """범위 안 순위 `result`."""

    ranking: Annotated[
        DabangRegionRankingPageModel | None,
        Field(description='순위')
    ] = None
    formatted_price_date: Annotated[
        str | None,
        Field(description="기준 달 (시세증감·최고가증감, '26년 10월')", alias='formattedPriceDate')
    ] = None


class DabangRegionInfoRealEstateRankingV5ResponseModel(DabangV5ResponseModel[DabangRegionRankingResultModel]):
    """`GET /api/v5/region-info/real-estate/ranking/{unit}/{metric}` 응답."""


class DabangRegionInfoRankingV5ResponseModel(DabangV5ResponseModel[DabangRegionRankingResultModel]):
    """`GET /api/v5/region-info/{topic}/ranking/{metric}` 응답 (부동산 순위와 같은 모양)."""


class DabangRegionInfoRoomRankingV5ResponseModel(DabangV5ResponseModel[DabangRegionRankingResultModel]):
    """`GET /api/v5/region-info/room/ranking/{metric}` 응답 (부동산 순위와 같은 모양, 거래량 값만 `formattedVolume`)."""
