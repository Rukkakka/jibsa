"""응답 모델: 단지 요약·평형·관리비·시세·실거래 요약 (complex)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import (
    NaverComplexArticleStatsModel,
    NaverPriceRangeModel,
    NaverPropertyTaxModel,
    NaverResponseModel,
    NaverSchoolModel,
    NaverTotalRealEstateTaxModel,
)

from typing import Annotated


class NaverComplexMaintenanceFeeModel(ResponseModel):
    """평형의 월 관리비 (원). 관리비 자료가 없는 단지는 빈 객체라 모두 None 이다."""

    year_month: Annotated[
        str | None,
        Field(description='가장 최근 달 (YYYY-MM)')
    ] = Field(default=None, alias='yearMonth')
    year_month_fee: Annotated[
        int | None,
        Field(description='가장 최근 달 관리비')
    ] = Field(default=None, alias='yearMonthFee')
    month_average_fee: Annotated[
        int | None,
        Field(description='월평균 관리비')
    ] = Field(default=None, alias='monthAverageFee')
    summer_average_fee: Annotated[
        int | None,
        Field(description='여름 평균 관리비')
    ] = Field(default=None, alias='summerAverageFee')
    winter_average_fee: Annotated[
        int | None,
        Field(description='겨울 평균 관리비 (난방비 때문에 높다)')
    ] = Field(default=None, alias='winterAverageFee')


class NaverMarketPriceModel(ResponseModel):
    """한 시세 제공처의 최신 시세 (원). 함께 오는 중개사 이름·전화(realtors)는 쓰지 않는다."""

    cp: Annotated[
        str | None,
        Field(description='제공처 (kab 한국부동산원, kbstar KB부동산, neonet 부동산뱅크)')
    ] = None
    base_date: Annotated[
        str | None,
        Field(description='시세 기준일 (YYYY-MM-DD)')
    ] = Field(default=None, alias='baseDate')
    deal_price_range: Annotated[
        NaverPriceRangeModel | None,
        Field(description='매매 시세 범위')
    ] = Field(default=None, alias='dealPriceRange')
    deal_average_price: Annotated[
        int | None,
        Field(description='매매 시세 평균')
    ] = Field(default=None, alias='dealAveragePrice')
    deposit_price_range: Annotated[
        NaverPriceRangeModel | None,
        Field(description='전세 시세 범위')
    ] = Field(default=None, alias='depositPriceRange')
    lease_per_deal_rate: Annotated[
        NaverPriceRangeModel | None,
        Field(description='전세가율 범위 (%)')
    ] = Field(default=None, alias='leasePerDealRate')


class NaverRealPriceSummaryTradeModel(ResponseModel):
    """실거래 요약의 최저·최고 거래 한 건 (원)."""

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = Field(default=None, alias='tradeDate')
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    deal_price: Annotated[
        int | None,
        Field(description='매매가')
    ] = Field(default=None, alias='dealPrice')
    deposit: Annotated[
        int | None,
        Field(description='보증금')
    ] = None
    is_delete: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = Field(default=None, alias='isDelete')
    trade_category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래')
    ] = Field(default=None, alias='tradeCategory')


class NaverRealPriceSummaryModel(ResponseModel):
    """기간 안 실거래 최저·최고·평균. 거래가 없으면 빈 객체라 모두 None 이다."""

    min_price: Annotated[
        NaverRealPriceSummaryTradeModel | None,
        Field(description='최저가 거래')
    ] = Field(default=None, alias='minPrice')
    max_price: Annotated[
        NaverRealPriceSummaryTradeModel | None,
        Field(description='최고가 거래')
    ] = Field(default=None, alias='maxPrice')
    avg_price: Annotated[
        int | None,
        Field(description='평균가 (매매는 매매가, 전세는 보증금)')
    ] = Field(default=None, alias='avgPrice')


class NaverReconstructionStepModel(ResponseModel):
    """재건축 사업 단계 하나. 아직 거치지 않은 단계는 날짜가 없다."""

    step_type: Annotated[
        str | None,
        Field(description='단계 코드 (사이트 COMPLEX_RECONSTRUCTION_STEP: 01 기본계획수립 … 11 이전고지)')
    ] = Field(default=None, alias='stepType')
    implementation_date: Annotated[
        str | None,
        Field(description='그 단계에 이른 날 (YYYY-MM-DD)')
    ] = Field(default=None, alias='implementationDate')


class NaverComplexReconstructionModel(ResponseModel):
    """재건축 단지의 사업 정보."""

    construction_company: Annotated[
        str | None,
        Field(description='시공사 (선정된 곳)')
    ] = Field(default=None, alias='constructionCompany')
    current_business_step: Annotated[
        NaverReconstructionStepModel | None,
        Field(description='현재 단계')
    ] = Field(default=None, alias='currentBusinessStep')
    business_steps: Annotated[
        list[NaverReconstructionStepModel],
        Field(description='단계 전체 (01~11 순서, 지나지 않은 단계는 날짜 없음)')
    ] = Field(default=[], alias='businessSteps')
    household_count: Annotated[
        int | None,
        Field(description='재건축 후 계획 세대수')
    ] = Field(default=None, alias='householdCount')
    building_area_to_land_ratio: Annotated[
        float | None,
        Field(description='재건축 계획 용적률 (%)')
    ] = Field(default=None, alias='buildingAreaToLandRatio')


class NaverDeclaredValueModel(ResponseModel):
    """공시가격 (원)."""

    base_date: Annotated[
        str | None,
        Field(description='기준일')
    ] = Field(default=None, alias='baseDate')
    min_price: Annotated[
        int | None,
        Field(description='최저 공시가격 (원)')
    ] = Field(default=None, alias='minPrice')
    max_price: Annotated[
        int | None,
        Field(description='최고 공시가격 (원)')
    ] = Field(default=None, alias='maxPrice')


class NaverHoldingTaxRangeModel(ResponseModel):
    """보유세 한쪽 끝 (최소 또는 최대 공시가 기준)."""

    property_tax: Annotated[
        NaverPropertyTaxModel | None,
        Field(description='재산세')
    ] = Field(default=None, alias='propertyTax')
    total_real_estate_tax: Annotated[
        NaverTotalRealEstateTaxModel | None,
        Field(description='종합부동산세')
    ] = Field(default=None, alias='totalRealEstateTax')


class NaverHoldingTaxModel(ResponseModel):
    """보유세 범위 (원, 1주택 기준 추정)."""

    min: Annotated[
        NaverHoldingTaxRangeModel | None,
        Field(description='최저 공시가 기준')
    ] = None
    max: Annotated[
        NaverHoldingTaxRangeModel | None,
        Field(description='최고 공시가 기준')
    ] = None


class NaverComplexArticleStatsV1ResponseModel(NaverResponseModel[NaverComplexArticleStatsModel]):
    """`GET /front-api/v1/complex/article/stats` 응답."""


class NaverComplexVillaArticleStatsV1ResponseModel(NaverResponseModel[NaverComplexArticleStatsModel]):
    """`GET /front-api/v1/complex/villa/article/stats` 응답. 월세 호가는 아파트와 다른 키로 온다(읽지 않는다)."""


class NaverComplexMaintenanceFeeV1ResponseModel(NaverResponseModel[NaverComplexMaintenanceFeeModel]):
    """`GET /front-api/v1/complex/maintenanceFee` 응답."""


class NaverComplexMarketPriceRecentV1ResponseModel(NaverResponseModel[list[NaverMarketPriceModel]]):
    """`GET /front-api/v1/complex/marketPrice/recent` 응답."""


class NaverComplexPyeongRealPriceSummaryV1ResponseModel(NaverResponseModel[NaverRealPriceSummaryModel]):
    """`GET /front-api/v1/complex/pyeong/realPrice/summary` 응답."""


class NaverComplexDeclaredValuePyeongTypeV1ResponseModel(NaverResponseModel[NaverDeclaredValueModel]):
    """`GET /front-api/v1/complex/declaredValue/pyeongType` 응답."""


class NaverComplexHoldingTaxV1ResponseModel(NaverResponseModel[NaverHoldingTaxModel]):
    """`GET /front-api/v1/complex/holdingTax` 응답."""


class NaverEducationComplexSchoolV1ResponseModel(NaverResponseModel[list[NaverSchoolModel]]):
    """`GET /front-api/v1/education/complex/school` 응답."""


class NaverComplexReconstructionV1ResponseModel(NaverResponseModel[NaverComplexReconstructionModel]):
    """`GET /front-api/v1/complex/reconstruction` 응답."""
