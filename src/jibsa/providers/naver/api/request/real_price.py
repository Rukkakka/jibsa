"""요청 모델: 단지·평형별 실거래가 (real-price)."""

from pydantic import Field

from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongRequestParameterModel,
    NaverRealEstateType,
    NaverTradeType,
)

from typing import (
    Annotated,
    Literal,
)


class NaverComplexPyeongRealPriceV2RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/v2/pyeong/realPrice` 쿼리."""

    trade_type: Annotated[
        NaverTradeType,
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)')
    ] = Field(default='A1', alias='tradeType')
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0
    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기. 사이트는 전체 보기 100, 요약 5')
    ] = 10


class NaverComplexVillaRealPricePageV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/villa/realPricePage` 쿼리."""

    trade_type: Annotated[
        NaverTradeType,
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)')
    ] = Field(default='A1', alias='tradeType')
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0
    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기')
    ] = 10


class NaverComplexPyeongRealPriceListV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/pyeong/realPrice/list` 쿼리. 기간 안 실거래를 페이지 없이 다 준다.

    `realEstateType`·`endDate` 가 빠지면 400 이다. 유형 값은 결과에 영향이 없다 (아파트 단지에 A01·A02·A04 모두
    같은 결과, 2026-10-10 확인). 빌라 단지는 거래가 있어도 빈 목록이라 `complex/villa/realPricePage` 로 받는다.
    """

    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='단지 유형 코드. 서버가 요구하지만 결과에 영향이 없다')
    ] = Field(default='A01', alias='realEstateType')
    trade_type: Annotated[
        Literal['A1', 'B1', 'B2'],
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)')
    ] = Field(alias='tradeType')
    start_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='시작일 (YYYY-MM-DD)')
    ] = Field(alias='startDate')
    end_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='끝일 (YYYY-MM-DD)')
    ] = Field(alias='endDate')
