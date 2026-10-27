from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangV5ResponseModel

from typing import Annotated


class DabangFluctuationModel(ResponseModel):
    """앞 기간 대비 순위 변동 (type: UP·DOWN·STEADY·NEW)."""

    type: Annotated[
        str | None,
        Field(description='변동 종류')
    ] = None
    rank: Annotated[
        int | None,
        Field(description='변동 폭')
    ] = None


class DabangWatchRankingItemModel(ResponseModel):
    """조회 순위 한 칸. 단지면 `complexId`·`complexName`·`address`, 동이면 `dongCode`·`dongName`·`stateName` 이다."""

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    watch_count: Annotated[
        int | None,
        Field(description='기간 안 조회 수', alias='watchCount')
    ] = None
    fluctuation: Annotated[
        DabangFluctuationModel | None,
        Field(description='순위 변동')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID', alias='complexId')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='complexName')
    ] = None
    address: Annotated[
        str | None,
        Field(description='단지 동까지의 주소')
    ] = None
    dong_code: Annotated[
        str | None,
        Field(description='동 코드 (법정동코드 앞 8자리)', alias='dongCode')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description="동 이름 ('의정부시 의정부동')", alias='dongName')
    ] = None
    state_name: Annotated[
        str | None,
        Field(description='시·도', alias='stateName')
    ] = None


class DabangWatchRankingsResultModel(ResponseModel):
    """조회 순위 `result`."""

    format_base_period: Annotated[
        str | None,
        Field(description="기준 기간 ('26.10.12 ~ 26.10.18', '26.10.25 17:09 기준')", alias='formatBasePeriod')
    ] = None
    list_: Annotated[
        list[DabangWatchRankingItemModel],
        Field(description='순위', alias='list')
    ] = []


class DabangRealTimeWatchRankingsV5ResponseModel(DabangV5ResponseModel[DabangWatchRankingsResultModel]):
    """`GET /api/v5/real-time-watch-rankings/{unit}` 응답."""


class DabangTradeRankingItemModel(ResponseModel):
    """거래 순위 한 칸."""

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 수', alias='tradeCount')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID', alias='complexId')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='complexName')
    ] = None
    description: Annotated[
        str | None,
        Field(description="'11년차ㆍ3636세대ㆍ서울특별시 송파구 문정동'")
    ] = None


class DabangTradeRankingsResultModel(ResponseModel):
    """거래 순위 `result`."""

    format_base_period: Annotated[
        str | None,
        Field(description="기준 기간 ('26.10.19 ~ 26.10.25')", alias='formatBasePeriod')
    ] = None
    list_: Annotated[
        list[DabangTradeRankingItemModel],
        Field(description='순위', alias='list')
    ] = []


class DabangRealPriceTradeRankingsComplexV5ResponseModel(DabangV5ResponseModel[DabangTradeRankingsResultModel]):
    """`GET /api/v5/real-price/trade/rankings/complex` 응답."""


class DabangRegionRankingItemModel(ResponseModel):
    """범위 안 순위 한 칸. 값은 항목마다 다른 글자 키로 온다: `formattedPrice`('61.1억'), `formattedCount`('27개',
    '6,702세대', '86,513명'), `formattedPercentage`('133.3%', 진학률 '2%'), `formattedAge`('44년 6개월'),
    `formattedChangeRate`('+0.8%'), `formattedScore`('19점').

    최고가증감은 `formattedPrice` 가 오른 금액이고 `formattedMaxPrice` 가 앞 최고가다 (2026-10-25 강남구 단지 1위
    아이파크삼성: 15.2억 = 62.8억 × 24.2%). 인구 증감은 `formattedYearOfYearChangeCount` 가 부호 없이('327명') 오고
    줄었는지는 `changeStatus`(INCREASE·DECREASE)와 `formattedYearOfYearChangePercentage`('-0.6%')로 안다.
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
        Field(description="수 글자 ('27개', '6,702세대')", alias='formattedCount')
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
        Field(description="변화율 ('+0.8%')", alias='formattedChangeRate')
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
    formatted_curr_count: Annotated[
        str | None,
        Field(description="올해 인구 (인구 증감, '68,936명')", alias='formattedCurrCount')
    ] = None
    formatted_prev_count: Annotated[
        str | None,
        Field(description='한 해 전 인구 (인구 증감)', alias='formattedPrevCount')
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


class DabangRegionRankingPageModel(ResponseModel):
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


class DabangRegionRankingResultModel(ResponseModel):
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
