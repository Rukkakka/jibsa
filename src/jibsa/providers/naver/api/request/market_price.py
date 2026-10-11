"""요청 모델: 단지·평형별 기관 시세 추이 (market-price)."""

from pydantic import Field

from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongRequestParameterModel,
)

from typing import (
    Annotated,
    Literal,
)


class NaverComplexMarketPriceListV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/marketPrice/list` 쿼리. 기간 안 주별 시세.

    사이트는 단지 유형(realEstateType)도 보내지만 빼도, 다른 유형을 줘도 같은 값이 온다 (2026-10-10 확인).
    """

    start_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='시작일 (YYYY-MM-DD)')
    ] = Field(alias='startDate')
    end_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='끝일 (YYYY-MM-DD)')
    ] = Field(alias='endDate')
    cp_list: Annotated[
        list[Literal['kab', 'kbstar', 'neonet']],
        Field(description='시세 제공처. kab 한국부동산원, kbstar KB부동산, neonet 부동산뱅크')
    ] = Field(default=['kab', 'kbstar', 'neonet'], alias='cpList[]')
