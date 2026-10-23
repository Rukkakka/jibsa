"""응답 모델: 단지·평형별 실거래가 (real-price)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import NaverResponseModel

from typing import Annotated


class NaverRealPriceModel(ResponseModel):
    """실거래 한 건 (원)."""

    trade_date: Annotated[
        str,
        Field(description='계약일 (YYYY-MM-DD)', alias='tradeDate')
    ]
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    deal_price: Annotated[
        int | None,
        Field(description='매매가 (원)', alias='dealPrice')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (원)')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (원)', alias='monthlyRent')
    ] = None
    is_delete: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래 여부', alias='isDelete')
    ] = None
    trade_category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래', alias='tradeCategory')
    ] = None
    registration_date: Annotated[
        str | None,
        Field(description='신고일', alias='registrationDate')
    ] = None
    is_renew: Annotated[
        bool | None,
        Field(description='갱신 계약 여부 (전월세)', alias='isRenew')
    ] = None


class NaverRealPriceListModel(ResponseModel):
    """실거래 목록."""

    items: Annotated[
        list[NaverRealPriceModel],
        Field(description='최근 순 실거래', alias='list')
    ] = []
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 여부', alias='hasNextPage')
    ] = None


class NaverVillaRealPriceModel(ResponseModel):
    """빌라 단지 실거래 한 건 (원). 아파트(`NaverRealPriceModel`)와 키 이름이 일부 다르다."""

    trade_date: Annotated[
        str,
        Field(description='계약일 (YYYY-MM-DD)', alias='tradeDate')
    ]
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    deal_price: Annotated[
        int | None,
        Field(description='매매가 (원). 전월세는 0', alias='dealPrice')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (원)')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (원)', alias='monthlyRent')
    ] = None
    is_canceled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래 여부', alias='isCanceled')
    ] = None
    trade_category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래', alias='tradeCategory')
    ] = None
    is_renew_request_right: Annotated[
        bool | None,
        Field(description='계약갱신요구권 사용 여부 (전월세)', alias='isRenewRequestRight')
    ] = None


class NaverVillaRealPricePageModel(ResponseModel):
    """빌라 단지 실거래 한 페이지."""

    total_count: Annotated[
        int | None,
        Field(description='전체 거래 수', alias='totalCount')
    ] = None
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 여부', alias='hasNextPage')
    ] = None
    items: Annotated[
        list[NaverVillaRealPriceModel],
        Field(description='최근 순 실거래', alias='realPriceList')
    ] = []


class NaverComplexVillaRealPricePageV1ResponseModel(NaverResponseModel[NaverVillaRealPricePageModel]):
    """`GET /front-api/v1/complex/villa/realPricePage` 응답."""


class NaverComplexPyeongRealPriceV2ResponseModel(NaverResponseModel[NaverRealPriceListModel]):
    """`GET /front-api/v1/complex/v2/pyeong/realPrice` 응답."""


class NaverComplexPyeongRealPriceListV1ResponseModel(NaverResponseModel[list[NaverRealPriceModel]]):
    """`GET /front-api/v1/complex/pyeong/realPrice/list` 응답. 최근 순."""
