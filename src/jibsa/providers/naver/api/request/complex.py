"""요청 모델: 단지 요약·평형·관리비·시세·실거래 요약 (complex)."""

from pydantic import Field

from jibsa.core.schema import RequestModel
from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongRequestParameterModel,
    NaverComplexRequestParameterModel,
    NaverRealEstateType,
)

from typing import (
    Annotated,
    Literal,
)


class NaverComplexArticleStatsRequestParameterModel(NaverComplexRequestParameterModel):
    """단지 매물 집계 쿼리. 평형·동으로 좁히면 건수와 호가 범위가 그 매물만으로 바뀐다.

    배열은 `pyeongTypes[]=1&pyeongTypes[]=2` 처럼 키에 `[]` 를 붙여 반복해야 한다
    (`pyeongTypes=1` 은 실패 응답, 2026-10-09 확인). 비우면 키가 빠져 단지 전체다.
    """

    pyeong_types: Annotated[
        list[int],
        Field(description='평형 번호 필터. 비우면 전체', alias='pyeongTypes[]')
    ] = []
    dong_numbers: Annotated[
        list[str],
        Field(description='동 번호 필터 (buildingList 의 number). 비우면 전체', alias='dongNumbers[]')
    ] = []


class NaverComplexArticleStatsV1RequestParameterModel(NaverComplexArticleStatsRequestParameterModel):
    """`GET /front-api/v1/complex/article/stats` 쿼리."""


class NaverComplexReconstructionV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/reconstruction` 쿼리. 재건축(A04) 단지의 사업 단계·시공사."""


class NaverComplexVillaArticleStatsV1RequestParameterModel(NaverComplexArticleStatsRequestParameterModel):
    """`GET /front-api/v1/complex/villa/article/stats` 쿼리."""


class NaverComplexMaintenanceFeeV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/maintenanceFee` 쿼리."""


class NaverComplexMarketPriceRecentV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/marketPrice/recent` 쿼리.

    시세 제공처 코드가 하나라도 틀리면 400 FST_ERR_VALIDATION 이다 (부동산뱅크는 neo 가 아니라 neonet,
    2026-10-09 확인). 배열은 `cpList[]=kab&cpList[]=kbstar` 처럼 키에 `[]` 를 붙여 반복한다.
    """

    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='단지 유형 코드 (complex 의 type)', alias='realEstateType')
    ]
    cp_list: Annotated[
        list[Literal['kab', 'kbstar', 'neonet']],
        Field(description='시세 제공처. kab 한국부동산원, kbstar KB부동산, neonet 부동산뱅크', alias='cpList[]')
    ] = ['kab', 'kbstar', 'neonet']


class NaverComplexPyeongRealPriceSummaryV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/pyeong/realPrice/summary` 쿼리. 사이트는 3년 전 오늘부터를 보낸다."""

    trade_type: Annotated[
        Literal['A1', 'B1', 'B2'],
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ]
    start_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='이 날짜 이후 거래만 (YYYY-MM-DD)', alias='startDate')
    ]


class NaverComplexDeclaredValuePyeongTypeV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/declaredValue/pyeongType` 쿼리."""


class NaverComplexHoldingTaxV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/holdingTax` 쿼리."""


class NaverEducationComplexSchoolV1RequestParameterModel(RequestModel):
    """`GET /front-api/v1/education/complex/school` 쿼리. 단지의 배정 초등학교를 준다.

    단지형 빌라(A05·A06·A07)는 villa 로 물어야 한다 (complex 로 물으면 빈 목록, 2026-10-10 확인).
    """

    complex_number: Annotated[
        int,
        Field(gt=0, description='단지 번호', alias='complexNumber')
    ]
    item_type: Annotated[
        Literal['complex', 'villa'],
        Field(description='단지 종류 (사이트 ArticleSchoolItemType)', alias='itemType')
    ] = 'complex'
