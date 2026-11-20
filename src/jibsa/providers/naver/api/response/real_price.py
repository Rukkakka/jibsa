"""응답 모델: 단지·평형별 실거래가 (real-price)."""

from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.naver.api.response.common import NaverResponseModel

from typing import Annotated


class NaverRealPriceModel(ResponseModel):
    """실거래 한 건 (원)."""

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 네이버가 null 을 주기도 한다', alias='tradeDate')
    ] = None
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
    already_deposit: Annotated[
        int | None,
        Field(description='갱신 계약의 종전 보증금 (원). 갱신 거래에만 온다', alias='alreadyDeposit')
    ] = None
    already_monthly_rent: Annotated[
        int | None,
        Field(description='갱신 계약의 종전 월세 (원). 갱신 거래에만 온다', alias='alreadyMonthlyRent')
    ] = None


class NaverRealPriceListModel(ResponseModel):
    """실거래 목록."""

    items: Annotated[
        list[NaverRealPriceModel] | None,
        Field(description='최근 순 실거래. 서버가 null 로 줄 수 있어 읽는 쪽이 빈 쪽으로 본다 (`real-price --group` 도 이 모델을 쓴다)', alias='list')
    ] = None
    has_next_page: Annotated[
        bool | None,
        Field(description='다음 페이지 여부', alias='hasNextPage')
    ] = None


class NaverVillaRealPriceModel(ResponseModel):
    """빌라 단지 실거래 한 건 (원). 아파트(`NaverRealPriceModel`)와 키 이름이 일부 다르다."""

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 네이버가 null 을 주기도 한다', alias='tradeDate')
    ] = None
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
    already_deposit: Annotated[
        int | None,
        Field(description='갱신 계약의 종전 보증금 (원). 갱신이 아니면 0', alias='alreadyDeposit')
    ] = None
    already_monthly_deposit: Annotated[
        int | None,
        Field(description='갱신 계약의 종전 월세 (원). 아파트(`alreadyMonthlyRent`)와 키 이름이 다르다. 갱신이 아니면 0', alias='alreadyMonthlyDeposit')
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


class NaverVillaPyeongPriceModel(ResponseModel):
    """빌라 단지 평당 실거래가 한 건 (원/평). 지금은 만원 자리로 떨어지는 값이 오지만 소수로 와도 받는다."""

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)', alias='tradeDate')
    ] = None
    pyeong_price: Annotated[
        float | None,
        Field(description='평당 실거래가 (원/평)', alias='pyeongPrice')
    ] = None


class NaverVillaAroundCoordinatesModel(ResponseModel):
    """주변 실거래 묶음(건물)의 좌표. `NaverCoordinatesModel` 과 달리 칸이 비어 와도 받는다."""

    x_coordinate: Annotated[
        float | None,
        Field(description='경도', alias='xCoordinate')
    ] = None
    y_coordinate: Annotated[
        float | None,
        Field(description='위도', alias='yCoordinate')
    ] = None


class NaverVillaAroundComplexInfoModel(ResponseModel):
    """주변 실거래 묶음의 건물 정보. 단지 번호·이름은 오지 않는다."""

    real_estate_type: Annotated[
        str | None,
        Field(description='건물 유형 코드 (A05·A06 ...)', alias='realEstateType')
    ] = None
    coordinates: Annotated[
        NaverVillaAroundCoordinatesModel | None,
        Field(description='건물 좌표. 묶음이 단지 자신인지 가리는 데만 쓴다', alias='coordinatesDto')
    ] = None


class NaverVillaAroundPriceModel(ResponseModel):
    """주변 실거래의 금액 (원)."""

    deal_price: Annotated[
        int | None,
        Field(description='매매가 (원). 전월세는 0', alias='dealPrice')
    ] = None
    deposit: Annotated[
        int | None,
        Field(description='보증금 (원). 매매는 0')
    ] = None
    monthly_rent: Annotated[
        int | None,
        Field(description='월세 (원). 매매·전세는 0', alias='monthlyRent')
    ] = None


class NaverVillaAroundTradeModel(ResponseModel):
    """주변 실거래 한 건. 빌라 단지 실거래(`NaverVillaRealPriceModel`)와 달리 면적·준공 연월을 주고 층은 글자로 온다."""

    contract_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)', alias='contractDate')
    ] = None
    exclusive_area: Annotated[
        float | None,
        Field(description='전용면적 (㎡)', alias='exclusiveArea')
    ] = None
    completion_year_month: Annotated[
        str | None,
        Field(description='준공 연월일 (YYYYMMDD, 예: 20100628)', alias='completionYearMonth')
    ] = None
    floor: Annotated[
        str | None,
        Field(description='층 (글자, 예: 5)')
    ] = None
    is_renew_request_right: Annotated[
        bool | None,
        Field(description='계약갱신요구권 사용 여부 (전월세)', alias='isRenewRequestRight')
    ] = None
    price: Annotated[
        NaverVillaAroundPriceModel | None,
        Field(description='금액')
    ] = None


class NaverVillaAroundBundleModel(ResponseModel):
    """주변 실거래 묶음: 한 건물의 거래들."""

    complex_info: Annotated[
        NaverVillaAroundComplexInfoModel | None,
        Field(description='건물 정보', alias='complexInfo')
    ] = None
    trades: Annotated[
        list[NaverVillaAroundTradeModel] | None,
        Field(description='이 건물의 거래. 서버가 null 로 줄 수 있어 읽는 쪽이 빈 쪽으로 본다', alias='realPriceList')
    ] = None


class NaverVillaAroundModel(ResponseModel):
    """범위 안 주변 실거래. 서버는 모두 합쳐 10건까지만 준다."""

    bundles: Annotated[
        list[NaverVillaAroundBundleModel] | None,
        Field(description='건물별 거래 묶음. 서버가 null 로 줄 수 있어 읽는 쪽이 빈 쪽으로 본다', alias='aroundRealPriceList')
    ] = None


class NaverComplexVillaRealPricePageV1ResponseModel(NaverResponseModel[NaverVillaRealPricePageModel]):
    """`GET /front-api/v1/complex/villa/realPricePage` 응답."""


class NaverComplexPyeongRealPriceV2ResponseModel(NaverResponseModel[NaverRealPriceListModel]):
    """`GET /front-api/v1/complex/v2/pyeong/realPrice` 응답."""


class NaverComplexPyeongRealPriceListV1ResponseModel(NaverResponseModel[list[NaverRealPriceModel]]):
    """`GET /front-api/v1/complex/pyeong/realPrice/list` 응답. 최근 순."""


class NaverComplexPyeongRealPriceGroupV1ResponseModel(NaverResponseModel[NaverRealPriceListModel]):
    """`GET /front-api/v1/complex/pyeong/realPrice/group` 응답. `complex/v2/pyeong/realPrice` 와 같은 모양이다."""


class NaverComplexVillaRealPricePyeongPriceV1ResponseModel(NaverResponseModel[list[NaverVillaPyeongPriceModel]]):
    """`GET /front-api/v1/complex/villa/realPricePyeongPrice` 응답. 거래가 없으면 `result` 가 `[]` 다."""


class NaverComplexVillaRealPriceAroundV1ResponseModel(NaverResponseModel[NaverVillaAroundModel]):
    """`GET /front-api/v1/complex/villa/realPriceAround` 응답."""
