"""응답 모델: 단지 평형과 단지 없는 매물의 실거래 (real-price)."""
from pydantic import Field

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangRealPriceHistoryModel(DabangBaseResponseModel):
    """실거래 한 건 (만원, 국토부 신고 기준).

    매매는 `tradePrice`, 전세는 `deposit`, 월세는 `deposit`·`monthlyPrice` 에 온다. `isRelease` 는 해제된 거래다.
    `priceType` 은 SALE·LEASE·MONTHLY (2026-10-25 실측). 웹은 `isRegistration`·`isDirect` 가 참이면 금액 옆에 등기·직거래
    표시를, `isNew` 가 참이면 계약일 옆에 새 거래 표시를 붙인다 (room 청크 `Kr`·`ei`, 2026-11-13). 단독·다가구 거래 줄에는
    `isRegistration` 이 없다 (2026-11-13 실측: 망원동 단독 매매·전월세).

    Args:
        contract_date: 계약일 ('26.01.14').
        price_type: 'SALE', 'LEASE', 'MONTHLY'.
        format_floor: 층 (모르면 'null' 글자로 온다).
        size: 매물 실거래만. 다세대·연립(`MULTIPLEX`)은 전용면적, 그 밖(`DETACHED` 단독·다가구)은 웹이 연면적이라 부르는 값 (㎡).
        building_type: 주택 유형 ('단독', '다가구'). 단독·다가구 매매만 온다.
    """

    contract_date: Annotated[
        str | None,
        Field(description="계약일 ('26.01.14')", alias='contractDate')
    ] = None
    price_type: Annotated[
        str | None,
        Field(description='SALE·LEASE·MONTHLY', alias='priceType')
    ] = None
    format_floor: Annotated[
        str | None,
        Field(description='층', alias='formatFloor')
    ] = None
    trade_price: Annotated[
        float | None,
        Field(description='매매가 (만원)', alias='tradePrice')
    ] = None
    deposit: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    monthly_price: Annotated[
        float | None,
        Field(description='월세 (만원)', alias='monthlyPrice')
    ] = None
    size: Annotated[
        float | None,
        Field(description='면적 (㎡). 다세대·연립은 전용면적, 단독·다가구는 연면적')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description="주택 유형 ('단독', '다가구', 단독·다가구 매매만)", alias='buildingType')
    ] = None
    is_release: Annotated[
        bool | None,
        Field(description='해제된 거래', alias='isRelease')
    ] = None
    is_direct: Annotated[
        bool | None,
        Field(description='직거래', alias='isDirect')
    ] = None
    is_registration: Annotated[
        bool | None,
        Field(description='등기된 거래', alias='isRegistration')
    ] = None
    is_new: Annotated[
        bool | None,
        Field(description='다방이 새 거래로 표시한 거래', alias='isNew')
    ] = None


class DabangRealPriceComplexHistoriesResultModel(DabangBaseResponseModel):
    """단지 실거래 `result`."""

    list_: Annotated[
        list[DabangRealPriceHistoryModel],
        Field(description='최근 계약 순 실거래', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRealPriceComplexHistoriesV5ResponseModel(DabangV5ResponseModel[DabangRealPriceComplexHistoriesResultModel]):
    """`GET /api/v5/real-price/complex/histories` 응답."""


class DabangRealPriceHousePageModel(DabangBaseResponseModel):
    """매물 실거래 한 쪽."""

    histories: Annotated[
        list[DabangRealPriceHistoryModel],
        Field(description='최근 계약 순 실거래')
    ] = []
    total: Annotated[
        int | None,
        Field(description='기간 안 거래 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangRealPriceHouseScopeModel(DabangBaseResponseModel):
    """매물 실거래를 모은 범위와 건물 유형.

    `historyBaseType` 이 `JIBUN` 이면 이 집(같은 지번) 거래, `DONG` 이면 같은 동의 같은 건물 유형 거래다. 웹은 그대로
    '이 집의 ○○ 거래정보는?'·'{동} ○○ 거래정보는?' 이라 쓴다 (room 청크 `ii`, 2026-11-13 웹 캡처: 망원동·역삼동 다세대 `JIBUN`
    1건·12건, 망원동 단독 `DONG` 전월세 2,407건). `buildingViewType` 이 `MULTIPLEX` 면 웹 표가 전용면적·층수, 그 밖이면
    연면적·주택유형(매매만)이다 (`Kr`·`ei`). 없는 매물·단지 매물에는 셋 다 null 이다.
    """

    dong_name: Annotated[
        str | None,
        Field(description='동 이름', alias='dongName')
    ] = None
    history_base_type: Annotated[
        str | None,
        Field(description="거래를 모은 범위 ('JIBUN' 이 집, 'DONG' 같은 동)", alias='historyBaseType')
    ] = None
    building_view_type: Annotated[
        str | None,
        Field(description="건물 유형 ('MULTIPLEX' 다세대·연립, 'DETACHED' 단독·다가구)", alias='buildingViewType')
    ] = None

    @property
    def is_known_listing(self) -> bool:
        """다방이 아는 매물인가. 없는 매물·단지 매물은 동 이름·범위가 모두 null 이다."""
        return self.dong_name is not None or self.history_base_type is not None


class DabangRealPriceHouseHistoryResultModel(DabangRealPriceHousePageModel, DabangRealPriceHouseScopeModel):
    """단지 없는 매물 실거래 `result`. 범위는 `DabangRealPriceHouseScopeModel` 을 본다."""


class DabangRealPriceHouseHistoryV5ResponseModel(DabangV5ResponseModel[DabangRealPriceHouseHistoryResultModel]):
    """`GET /api/v5/real-price/house/history` 응답."""


class DabangRealPriceHouseInitResultModel(DabangRealPriceHouseScopeModel):
    """단지 없는 매물 실거래 첫 화면 `result`.

    `searchType` 은 매물의 거래 유형을 따른다: 매매 매물은 SALE, 월세·전세 매물은 LEASE (2026-11-13 웹 캡처: 망원동 다세대
    매매 매물 SALE, 단독 월세 매물 LEASE). 웹은 이 값으로 제목을 쓰고 목록도 같은 기준(`sellingType === 2 ? SALE : LEASE`)으로
    받는다 (room 청크 `ii`·`Rr`). 없는 매물에는 `searchType`·범위·건물 유형이 모두 null 이다 (2026-11-13 실측).
    `compare`(시세 대비 오름·내림과 %)도 오지만 모델에 두지 않는다. 다방이 이 표시를 꺼 두어(`settings.isPriceCompareExpose:
    false`, 값도 null) 웹 매물 화면에 '시세대비' 칸이 나오지 않는다 (room 청크 `pn`, 2026-11-13 웹 캡처 5건).
    """

    search_type: Annotated[
        str | None,
        Field(description="매물의 거래 유형으로 고른 실거래 ('SALE' 매매, 'LEASE' 전월세)", alias='searchType')
    ] = None
    history: Annotated[
        DabangRealPriceHousePageModel | None,
        Field(description='첫 거래 (limit 만큼)')
    ] = None


class DabangRealPriceHouseInitV5ResponseModel(DabangV5ResponseModel[DabangRealPriceHouseInitResultModel]):
    """`GET /api/v5/real-price/house/init` 응답."""
