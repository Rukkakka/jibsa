"""응답 모델: 지역 정보·거래량·평당 추이·인구·세대 (region-info)."""

from pydantic import (
    Field,
    PrivateAttr,
    RootModel,
    ValidatorFunctionWrapHandler,
    model_validator,
)

from jibsa.core.schema import add_null_item_tally
from jibsa.providers.zigbang.api.response.common import ZigbangBaseResponseModel

from typing import (
    Annotated,
    Any,
    Generic,
    TypeVar,
)


T = TypeVar('T')


class ZigbangRootListModel(RootModel[list[T]], Generic[T]):
    """봉투 없이 목록 하나가 오는 응답의 기반. 목록 안의 null 원소는 빼고 그 수를 `null_items` 로 센다.

    `ZigbangBaseResponseModel.null_items` 는 모델 칸의 목록만 다뤄 루트 목록에는 닿지 않아, 같은 규칙(빼고 읽고, 계산하는 쪽이 뺀 수를
    알게 한다)을 여기서 따로 붙인다. 원소가 `None` 일 수 있는 자료형이 아니라 모델이어야 뺄 수 있다. 항목 목록은 `.root` 다.
    """

    # 목록에서 뺀 null 원소의 수
    _null_items: int = PrivateAttr(default=0)

    @model_validator(mode='wrap')
    @classmethod
    def drop_null_items(cls, data: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        dropped = 0
        if isinstance(data, list) and None in data:
            kept = [item for item in data if item is not None]
            data, dropped = kept, len(data) - len(kept)
        result = handler(data)
        if dropped:
            result._null_items = dropped
            # 명령 전체의 합에도 더한다 (`null_item_tally`)
            add_null_item_tally(dropped)
        return result

    def null_items(self) -> int:
        """목록에서 null 원소를 빼고 읽은 수."""
        return self._null_items


# ---------------------------------------------------------------------------
# GET /apt/locals/{localCode}
# ---------------------------------------------------------------------------

class ZigbangLocalPriceModel(ZigbangBaseResponseModel):
    """지역 정보의 평형대별 시세 한 줄. 모두 만원 단위다."""

    area: Annotated[
        str | None,
        Field(description="평형대 구분 ('0'·'10'~'60'·'total'). 글자로 온다")
    ] = None
    sales_price: Annotated[
        int | float | None,
        Field(description='평균 매매 평당가 (만원/3.3㎡)', alias='salesPrice')
    ] = None
    min_sales_price: Annotated[
        int | float | None,
        Field(description='최저 매매가 (만원)', alias='minSalesPrice')
    ] = None
    max_sales_price: Annotated[
        int | float | None,
        Field(description='최고 매매가 (만원)', alias='maxSalesPrice')
    ] = None
    rent_price: Annotated[
        int | float | None,
        Field(description='평균 전월세 평당가 (만원/3.3㎡)', alias='rentPrice')
    ] = None


class ZigbangMarketPriceMovementModel(ZigbangBaseResponseModel):
    """시세 흐름 (몇 주째 오르거나 내리는지). 해당 없으면 빈 객체 `{}` 로 와서 두 칸 모두 None 이다 (2026-11-22 표본에서는 늘 `{}` 였다)."""

    updown_week_count: Annotated[
        int | None,
        Field(description='같은 흐름이 이어진 주 수', alias='updownWeekCount')
    ] = None
    updown_sign: Annotated[
        str | None,
        Field(description="흐름 ('상승'·'하락'·'지속')", alias='updownSign')
    ] = None


class ZigbangLocalsResponseModel(ZigbangBaseResponseModel):
    """지역 정보 (동·구·시도). 중심 좌표(`lat`·`lng`)와 월간 리포트 안내(`monthlyReportInfluxInfo`)는 읽지 않는다."""

    name: Annotated[
        str | None,
        Field(description="지역 이름 (예: '성남시 분당구')")
    ] = None
    address: Annotated[
        str | None,
        Field(description="전체 주소 (예: '경기도 성남시 분당구')")
    ] = None
    step: Annotated[
        str | None,
        Field(description="행정 단계 ('1' 시도, '2' 구, '3' 동). 글자로 온다")
    ] = None
    apts: Annotated[
        int | None,
        Field(description='단지 수')
    ] = None
    total_apts: Annotated[
        int | None,
        Field(description='단지 수 (`description` 앞의 수와 같다. 2026-11-22 표본에서 서울은 apts 4713 · totalApts 4923 · description 4,923 단지로 `apts` 와 달랐다)', alias='totalApts')
    ] = None
    household: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    description: Annotated[
        str | None,
        Field(description="단지·세대 요약 문구 (예: '39 단지 · 23,634 세대')")
    ] = None
    sales_area_price: Annotated[
        int | float | None,
        Field(description='평균 매매 평당가 (만원/3.3㎡)')
    ] = None
    rent_area_price: Annotated[
        int | float | None,
        Field(description='평균 전월세 평당가 (만원/3.3㎡)')
    ] = None
    price: Annotated[
        list[ZigbangLocalPriceModel] | None,
        Field(description='평형대별 시세 (`area` 가 0·10…60·total 순)')
    ] = None
    market_price_movement_info: Annotated[
        ZigbangMarketPriceMovementModel | None,
        Field(description='시세 흐름. 없으면 빈 객체로 온다', alias='marketPriceMovementInfo')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/locals/trading-volume-chart
# ---------------------------------------------------------------------------

class ZigbangLocalVolumeMonthModel(ZigbangBaseResponseModel):
    """한 달의 거래량 (건)."""

    date: Annotated[
        str | None,
        Field(description='월 (YYYY-MM)')
    ] = None
    sales_volume: Annotated[
        int | None,
        Field(description='매매 건수', alias='salesVolume')
    ] = None
    charter_volume: Annotated[
        int | None,
        Field(description='전세 건수', alias='charterVolume')
    ] = None
    rent_volume: Annotated[
        int | None,
        Field(description='월세 건수', alias='rentVolume')
    ] = None


class ZigbangLocalVolumeSummaryModel(ZigbangBaseResponseModel):
    """거래량 그래프의 범위."""

    start_date: Annotated[
        str | None,
        Field(description='시작 월 (YYYY-MM)', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='끝 월 (YYYY-MM)', alias='endDate')
    ] = None
    max_volume: Annotated[
        int | None,
        Field(description='가장 많은 달의 건수 (세 거래 유형 통틀어)', alias='maxVolume')
    ] = None
    min_volume: Annotated[
        int | None,
        Field(description='가장 적은 달의 건수', alias='minVolume')
    ] = None


class ZigbangLocalsTradingVolumeChartDataModel(ZigbangBaseResponseModel):
    """거래량 그래프. 키 이름이 `list` 라 `months` 로 받는다 (속성 `list` 가 내장 `list` 를 가린다)."""

    months: Annotated[
        list[ZigbangLocalVolumeMonthModel] | None,
        Field(description='월별 거래량 (오래된 달부터). 구가 있는 시의 5자리 코드(예: 41130)는 빈 목록이다 (2026-11-22 표본)', alias='list')
    ] = None
    summary: Annotated[
        ZigbangLocalVolumeSummaryModel | None,
        Field(description='그래프 범위')
    ] = None


class ZigbangLocalsTradingVolumeChartResponseModel(ZigbangBaseResponseModel):
    """지역의 월별 거래량 응답. `data` 봉투에 싸여 온다."""

    data: Annotated[
        ZigbangLocalsTradingVolumeChartDataModel | None,
        Field(description='거래량 그래프')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/locals/pyn-chart-price
# ---------------------------------------------------------------------------

class ZigbangLocalPynPointModel(ZigbangBaseResponseModel):
    """평당가 추이의 한 달."""

    date: Annotated[
        str | None,
        Field(description='월 (YYYY-MM)')
    ] = None
    price: Annotated[
        int | float | None,
        Field(description='평당가 (만원/3.3㎡)')
    ] = None


class ZigbangLocalPynLineModel(ZigbangBaseResponseModel):
    """평당가 추이의 줄 하나 (단지 또는 그 지역)."""

    label: Annotated[
        str | None,
        Field(description='줄 이름 (단지 이름 또는 지역 이름)')
    ] = None
    data: Annotated[
        list[ZigbangLocalPynPointModel] | None,
        Field(description='월별 평당가 (오래된 달부터)')
    ] = None


class ZigbangLocalPynSummaryModel(ZigbangBaseResponseModel):
    """평당가 추이 그래프의 범위."""

    min_price: Annotated[
        int | float | None,
        Field(description='가장 낮은 평당가 (만원/3.3㎡)', alias='minPrice')
    ] = None
    max_price: Annotated[
        int | float | None,
        Field(description='가장 높은 평당가 (만원/3.3㎡)', alias='maxPrice')
    ] = None
    start_date: Annotated[
        str | None,
        Field(description='시작 월 (YYYY-MM)', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='끝 월 (YYYY-MM)', alias='endDate')
    ] = None


class ZigbangLocalsPynChartPriceDataModel(ZigbangBaseResponseModel):
    """평당가 추이 그래프. 키 이름이 `list` 라 `lines` 로 받는다 (속성 `list` 가 내장 `list` 를 가린다)."""

    lines: Annotated[
        list[ZigbangLocalPynLineModel] | None,
        Field(description='줄 (2026-11-22 표본: 서울은 단지 셋과 지역 줄 하나)', alias='list')
    ] = None
    summary: Annotated[
        ZigbangLocalPynSummaryModel | None,
        Field(description='그래프 범위')
    ] = None
    market_price_movement_info: Annotated[
        ZigbangMarketPriceMovementModel | None,
        Field(description='시세 흐름. 없으면 빈 객체로 온다', alias='marketPriceMovementInfo')
    ] = None


class ZigbangLocalsPynChartPriceResponseModel(ZigbangBaseResponseModel):
    """지역의 평당가 추이 응답. `data` 봉투에 싸여 온다."""

    data: Annotated[
        ZigbangLocalsPynChartPriceDataModel | None,
        Field(description='평당가 추이 그래프')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/locals/{localCode}/total_people_time · total_households_time
# ---------------------------------------------------------------------------

class ZigbangLocalPeopleMonthModel(ZigbangBaseResponseModel):
    """한 달의 연령대별 인구 (명)."""

    yearmonth: Annotated[
        int | None,
        Field(description='월 (YYYYMM 정수)')
    ] = None
    age_all: Annotated[
        int | None,
        Field(description='전체 인구 (명)')
    ] = None
    age_0_9: Annotated[
        int | None,
        Field(description='0~9세 (명)')
    ] = None
    age_10_19: Annotated[
        int | None,
        Field(description='10~19세 (명)')
    ] = None
    age_20_29: Annotated[
        int | None,
        Field(description='20~29세 (명)')
    ] = None
    age_30_39: Annotated[
        int | None,
        Field(description='30~39세 (명)')
    ] = None
    age_40_49: Annotated[
        int | None,
        Field(description='40~49세 (명)')
    ] = None
    age_50_59: Annotated[
        int | None,
        Field(description='50~59세 (명)')
    ] = None
    age_60_69: Annotated[
        int | None,
        Field(description='60~69세 (명)')
    ] = None


class ZigbangLocalHouseholdsMonthModel(ZigbangBaseResponseModel):
    """한 달의 가구원 수별 세대 (세대)."""

    yearmonth: Annotated[
        int | None,
        Field(description='월 (YYYYMM 정수)')
    ] = None
    people_all: Annotated[
        int | None,
        Field(description='전체 세대 (세대)')
    ] = None
    people_1: Annotated[
        int | None,
        Field(description='1인 세대 (세대)')
    ] = None
    people_2: Annotated[
        int | None,
        Field(description='2인 세대 (세대)')
    ] = None
    people_3: Annotated[
        int | None,
        Field(description='3인 세대 (세대)')
    ] = None
    people_4: Annotated[
        int | None,
        Field(description='4인 세대 (세대)')
    ] = None
    people_5_: Annotated[
        int | None,
        Field(description='5인 이상 세대 (세대)')
    ] = None


class ZigbangLocalsTotalPeopleTimeResponseModel(ZigbangRootListModel[ZigbangLocalPeopleMonthModel]):
    """지역의 월별 연령대별 인구. 최상위가 배열이다(`.root`). 시도·구 코드는 값이 있고 동 코드면 빈 배열이다 (2026-11-19 캡처·2026-11-22 표본)."""


class ZigbangLocalsTotalHouseholdsTimeResponseModel(ZigbangRootListModel[ZigbangLocalHouseholdsMonthModel]):
    """지역의 월별 가구원 수별 세대. 최상위가 배열이다(`.root`). 구 코드는 값이 있고 동 코드면 빈 배열이다 (2026-11-19 캡처)."""
