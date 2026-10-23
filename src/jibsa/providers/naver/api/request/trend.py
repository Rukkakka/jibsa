"""요청 모델: 법정동 매물 수·호가·거래 추이 (trend)."""

from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


NaverTrendOffset = Literal['P-1M', 'P-6M', 'P-1Y', 'P-3Y', 'P-5Y']
"""동네 추이 기간. 1개월·6개월·1년·3년·5년 (사이트 APARTMENT_ARTICLE_TREND_DATE_TYPE_LABEL, 2026-10-10)."""


class NaverLegalDivisionTrendRequestParameterModel(RequestModel):
    """동네 주간 추이(매물 수·평당가·거래량) 쿼리. 사이트 지역 화면의 아파트 시세 추이다.

    오피스텔·빌라 코드도 받지만 값이 모두 0 이고(역삼동, 2026-10-10 확인) 월세는 400 이라 아파트 매매·전세만 쓴다.
    구 단위 법정동 코드도 받는다.
    """

    legal_division_number: Annotated[
        str,
        Field(pattern=r'^\d{10}$', description='법정동 코드 (동·구)', alias='legalDivisionNumber')
    ]
    real_estate_type_code: Annotated[
        Literal['A01'],
        Field(description='매물 유형. 아파트만 값이 있다', alias='realEstateTypeCode')
    ] = 'A01'
    trade_type: Annotated[
        Literal['A1', 'B1'],
        Field(description='거래 유형 (A1 매매, B1 전세). 월세는 400', alias='tradeType')
    ] = 'A1'
    offset: Annotated[
        NaverTrendOffset,
        Field(description='기간')
    ] = 'P-1Y'
    pyeong_range_lower: Annotated[
        int | None,
        Field(ge=0, description='평형대 하한 (평). 사이트는 10평 단위 (10~20 … 50~60)', alias='pyeongRangeLower')
    ] = None
    pyeong_range_upper: Annotated[
        int | None,
        Field(ge=0, description='평형대 상한 (평)', alias='pyeongRangeUpper')
    ] = None


class NaverLegalDivisionArticleCountWeeklyInfoV1RequestParameterModel(NaverLegalDivisionTrendRequestParameterModel):
    """`GET /front-api/v1/legalDivision/articleCountWeeklyInfo` 쿼리."""


class NaverLegalDivisionPyeongPriceWeeklyListV1RequestParameterModel(NaverLegalDivisionTrendRequestParameterModel):
    """`GET /front-api/v1/legalDivision/pyeongPriceWeeklyList` 쿼리."""


class NaverLegalDivisionRealTradeCountWeeklyListV1RequestParameterModel(NaverLegalDivisionTrendRequestParameterModel):
    """`GET /front-api/v1/legalDivision/realTradeCountWeeklyList` 쿼리."""
