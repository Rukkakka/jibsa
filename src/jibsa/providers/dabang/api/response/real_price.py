from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import (
    DabangAreaAveragePriceModel,
    DabangV5ResponseModel,
    Meters,
)

from typing import Annotated


class DabangRealPriceHistoryModel(ResponseModel):
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


class DabangRealPriceComplexHistoriesResultModel(ResponseModel):
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


class DabangRealPriceHousePageModel(ResponseModel):
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


class DabangRealPriceHouseScopeModel(ResponseModel):
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


class DabangChartStatisticModel(ResponseModel):
    """시세 흐름의 한 달 (만원). 거래가 없는 달도 앞 달 평균을 이어 준다 (`volume: 0`)."""

    date: Annotated[
        str,
        Field(description='달 (YYYYMM)')
    ]
    average_price: Annotated[
        float | None,
        Field(description='평균가 (만원)', alias='averagePrice')
    ] = None
    volume: Annotated[
        int | None,
        Field(description='거래 수 (전월세는 전세 + 월세)')
    ] = None
    lease_volume: Annotated[
        int | None,
        Field(description='전세 거래 수 (전월세만)', alias='leaseVolume')
    ] = None
    monthly_volume: Annotated[
        int | None,
        Field(description='월세 거래 수 (전월세만)', alias='monthlyVolume')
    ] = None


class DabangChartPerSpaceModel(ResponseModel):
    """평형의 최근 평균 (만원)."""

    average_price: Annotated[
        float | None,
        Field(description='평균가', alias='averagePrice')
    ] = None
    average_pyeong_price: Annotated[
        float | None,
        Field(description='평당 평균가', alias='averagePyeongPrice')
    ] = None


class DabangChartSeriesModel(ResponseModel):
    """매매 또는 전월세 시세 흐름."""

    statistics: Annotated[
        list[DabangChartStatisticModel],
        Field(description='36달')
    ] = []
    per_space: Annotated[
        DabangChartPerSpaceModel | None,
        Field(description='최근 평균', alias='perSpace')
    ] = None


class DabangChartGapRecentModel(ResponseModel):
    """최근 매매·전세 평균과 차이, 전세가율."""

    trade_average_price: Annotated[
        float | None,
        Field(description='매매 평균 (만원)', alias='tradeAveragePrice')
    ] = None
    lease_average_price: Annotated[
        float | None,
        Field(description='전세 평균 (만원)', alias='leaseAveragePrice')
    ] = None
    range_average_price: Annotated[
        float | None,
        Field(description='매매 − 전세 (만원)', alias='rangeAveragePrice')
    ] = None
    lease_rate: Annotated[
        float | None,
        Field(description='전세가율 (%)', alias='leaseRate')
    ] = None


class DabangChartGapStatisticModel(DabangChartGapRecentModel):
    """달마다 매매·전세 평균과 차이, 전세가율. 아직 거래가 없는 이번 달은 모두 null 로 온다 (2026-11-13 웹 캡처: 은마 202611)."""

    date: Annotated[
        str | None,
        Field(description='달 (YYYYMM). 없으면 그 줄은 어느 달인지 몰라 쓰지 않는다')
    ] = None


class DabangChartGapModel(ResponseModel):
    """매매·전세 차이."""

    statistics: Annotated[
        list[DabangChartGapStatisticModel] | None,
        Field(description='36달. null 이면 모름')
    ] = None
    recent_info: Annotated[
        DabangChartGapRecentModel | None,
        Field(description='최근', alias='recentInfo')
    ] = None


class DabangHighLowModel(ResponseModel):
    """기간 안 최고·최저 (만원)."""

    highest: Annotated[
        float | None,
        Field(description='최고')
    ] = None
    lowest: Annotated[
        float | None,
        Field(description='최저')
    ] = None


class DabangYearPriceRangeModel(ResponseModel):
    """1년·3년 최고·최저."""

    one_year: Annotated[
        DabangHighLowModel | None,
        Field(description='1년', alias='oneYear')
    ] = None
    three_years: Annotated[
        DabangHighLowModel | None,
        Field(description='3년', alias='threeYears')
    ] = None


class DabangYearPriceModel(ResponseModel):
    """매매·전세 1년·3년 최고·최저."""

    sale: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='매매')
    ] = None
    lease: Annotated[
        DabangYearPriceRangeModel | None,
        Field(description='전세')
    ] = None


class DabangRealPriceComplexChartsResultModel(ResponseModel):
    """시세 흐름 `result`. `leaseMonthly` 의 평균가는 전세 평균이다 (`perSpace` 가 `gap.recentInfo.leaseAveragePrice` 와 같다,
    2026-10-25 실측: 26000 = 26000).
    """

    sale: Annotated[
        DabangChartSeriesModel | None,
        Field(description='매매')
    ] = None
    lease_monthly: Annotated[
        DabangChartSeriesModel | None,
        Field(description='전월세 (평균가는 전세)', alias='leaseMonthly')
    ] = None
    gap: Annotated[
        DabangChartGapModel | None,
        Field(description='매매·전세 차이')
    ] = None
    year_price: Annotated[
        DabangYearPriceModel | None,
        Field(description='1년·3년 최고·최저', alias='yearPrice')
    ] = None


class DabangRealPriceComplexChartsV5ResponseModel(DabangV5ResponseModel[DabangRealPriceComplexChartsResultModel]):
    """`GET /api/v5/real-price/complex/charts` 응답."""


class DabangNearComplexModel(ResponseModel):
    """반경 1km 주변 단지 하나 (평당가 비교). 좌표(`location`)도 오지만 모델에 두지 않는다.

    웹은 이름과 `complexDesc`('입주 37년차 · 120세대'), 평당가를 그리고 평당가가 없으면 빈 칸이다 (complex 청크 `nn`,
    2026-11-13). `complexId` 가 없는 줄은 웹이 그리지 않는다.
    """

    complex_id: Annotated[
        str | None,
        Field(description='단지 ID', alias='complexId')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description="단지 유형 ('APT', 'OFFICETEL')", alias='complexType')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='complexName')
    ] = None
    address: Annotated[
        str | None,
        Field(description="주소 (동까지, '서울특별시 강남구 대치동')")
    ] = None
    complex_desc: Annotated[
        str | None,
        Field(description="연차·세대수 글 ('입주 37년차 · 120세대')", alias='complexDesc')
    ] = None
    average_pyeong_price: Annotated[
        float | None,
        Field(description='평당가 (만원). 매매 목록은 매매, 전월세 목록은 전세', alias='averagePyeongPrice')
    ] = None
    household_num: Annotated[
        int | None,
        Field(description='세대수', alias='householdNum')
    ] = None
    distance: Annotated[
        Meters,
        Field(description='이 단지에서 거리 (m)')
    ] = None


class DabangNearComplexesModel(ResponseModel):
    """주변 단지 (매매·전월세 탭). 서버 순서는 평당가가 있는 단지를 가까운 순으로 앞에, 없는 단지를 그 뒤에 둔다
    (2026-11-14 실측: 은마 30평대 매매 10곳)."""

    trade: Annotated[
        list[DabangNearComplexModel] | None,
        Field(description='매매 평당가 기준. null 이면 모름')
    ] = None
    lease: Annotated[
        list[DabangNearComplexModel] | None,
        Field(description='전세 평당가 기준 (웹 전월세 탭). null 이면 모름')
    ] = None


class DabangRealPriceComplexPricePerPyResultModel(ResponseModel):
    """평형대 평당가 비교 `result`. `pyeongRangeTabName` 이 비면 웹은 'N평대 비교' 탭을 그리지 않고 '전체 평형 비교'(단지 상세의
    `areaAveragePrice`)만 보여 준다 (complex 청크 `Ut`)."""

    pyeong_range_tab_name: Annotated[
        str | None,
        Field(description="탭 이름 ('30평대 비교')", alias='pyeongRangeTabName')
    ] = None
    area_average_price: Annotated[
        list[DabangAreaAveragePriceModel] | None,
        Field(description='이 단지·동·구의 그 평형대 평당가. null 이면 모름', alias='areaAveragePrice')
    ] = None
    near_complexes: Annotated[
        DabangNearComplexesModel | None,
        Field(description='반경 1km 주변 단지', alias='nearComplexes')
    ] = None


class DabangRealPriceComplexPricePerPyV5ResponseModel(DabangV5ResponseModel[DabangRealPriceComplexPricePerPyResultModel]):
    """`GET /api/v5/real-price/complex/price-per-py` 응답."""
