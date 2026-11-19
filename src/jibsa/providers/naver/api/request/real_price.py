"""요청 모델: 단지·평형별 실거래가 (real-price)."""

from pydantic import Field

from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongRequestParameterModel,
    NaverComplexRequestParameterModel,
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
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ] = 'A1'
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
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ] = 'A1'
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0
    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기')
    ] = 10


class NaverComplexVillaRealPricePyeongPriceV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/villa/realPricePyeongPrice` 쿼리. 빌라 단지의 평당 실거래가.

    웹 빌라 단지 실거래 탭은 `startDate` 를 오늘의 5년 전으로 보내고, 평형을 고르면 `pyeongTypeNumber` 를 붙인다.
    월세(B2)는 웹이 이 칸을 그리지 않아 묻지 않는다.
    """

    pyeong_type_number: Annotated[
        int | None,
        Field(gt=0, description='평형 번호 (pyeongList 의 number). 빼면 단지 전체', alias='pyeongTypeNumber')
    ] = None
    trade_type: Annotated[
        Literal['A1', 'B1'],
        Field(description='거래 유형 (A1 매매, B1 전세)', alias='tradeType')
    ]
    start_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='시작일 (YYYY-MM-DD). 웹은 오늘의 5년 전', alias='startDate')
    ]


class NaverComplexVillaRealPriceAroundV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/villa/realPriceAround` 쿼리. 지도 범위 안 빌라 실거래.

    범위 네 값과 `zoom` 이 모두 필요하다 (2026-11-19 실측: zoom 16 이면 결과가 오고 14 면 0건, 빼면 400). 서버는 범위 안
    거래를 10건까지만 준다. `pyeongTypeNumber` 를 주면 그 평형과 비슷한 면적의 거래까지 함께 준다.
    """

    pyeong_type_number: Annotated[
        int | None,
        Field(gt=0, description='평형 번호 (pyeongList 의 number). 빼면 단지 전체', alias='pyeongTypeNumber')
    ] = None
    trade_type: Annotated[
        Literal['A1', 'B1', 'B2'],
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ]
    top: Annotated[
        float,
        Field(ge=-90, le=90, description='범위의 북쪽 위도')
    ]
    bottom: Annotated[
        float,
        Field(ge=-90, le=90, description='범위의 남쪽 위도')
    ]
    left: Annotated[
        float,
        Field(ge=-180, le=180, description='범위의 서쪽 경도')
    ]
    right: Annotated[
        float,
        Field(ge=-180, le=180, description='범위의 동쪽 경도')
    ]
    zoom: Annotated[
        int,
        Field(ge=1, le=22, description='지도 줌. 웹이 16 을 보낸다. 14 는 같은 범위에도 0건이다')
    ] = 16


class NaverComplexPyeongRealPriceListV1RequestParameterModel(NaverComplexPyeongRequestParameterModel):
    """`GET /front-api/v1/complex/pyeong/realPrice/list` 쿼리. 기간 안 실거래를 페이지 없이 다 준다.

    `realEstateType`·`endDate` 가 빠지면 400 이다. 유형 값은 결과에 영향이 없다 (아파트 단지에 A01·A02·A04 모두
    같은 결과, 2026-10-10 확인). 빌라 단지는 거래가 있어도 빈 목록이라 `complex/villa/realPricePage` 로 받는다.
    """

    real_estate_type: Annotated[
        NaverRealEstateType,
        Field(description='단지 유형 코드. 서버가 요구하지만 결과에 영향이 없다', alias='realEstateType')
    ] = 'A01'
    trade_type: Annotated[
        Literal['A1', 'B1', 'B2'],
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ]
    start_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='시작일 (YYYY-MM-DD)', alias='startDate')
    ]
    end_date: Annotated[
        str,
        Field(pattern=r'^\d{4}-\d{2}-\d{2}$', description='끝일 (YYYY-MM-DD)', alias='endDate')
    ]


class NaverComplexPyeongRealPriceGroupV1RequestParameterModel(NaverComplexRequestParameterModel):
    """`GET /front-api/v1/complex/pyeong/realPrice/group` 쿼리. 평형 묶음 하나의 실거래.

    평형 번호는 `pyeongTypeNumbers[]=19&pyeongTypeNumbers[]=16` 처럼 키에 `[]` 를 붙여 반복한다.
    웹은 `[대표 번호, ...나머지 번호순]` 으로 보낸다.
    """

    pyeong_type_numbers: Annotated[
        list[Annotated[int, Field(gt=0)]],
        Field(min_length=1, description='묶음에 든 평형 번호 (pyeongGroups 의 pyeongTypes[].number)', alias='pyeongTypeNumbers[]')
    ]
    trade_type: Annotated[
        NaverTradeType,
        Field(description='거래 유형 (A1 매매, B1 전세, B2 월세)', alias='tradeType')
    ] = 'A1'
    page: Annotated[
        int,
        Field(ge=0, description='페이지 (0부터)')
    ] = 0
    size: Annotated[
        int,
        Field(ge=1, le=100, description='페이지 크기. 사이트는 전체 보기 100, 요약 5')
    ] = 10
