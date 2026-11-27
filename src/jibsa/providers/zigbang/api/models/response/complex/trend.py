"""응답 모델: 단지 직방시세 추이 (price-trend)."""

from pydantic import Field

from jibsa.providers.zigbang.api.models.response.common import (
    ZigbangBaseResponseModel,
    ZigbangRelatedDanjiModel,
)

from typing import Annotated


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/price-chart
# ---------------------------------------------------------------------------

class ZigbangDanjiPriceChartPointModel(ZigbangBaseResponseModel):
    """직방시세 추이의 한 달."""

    date: Annotated[
        str | None,
        Field(description='월 (YYYY-MM-01)')
    ] = None
    price: Annotated[
        int | float | None,
        Field(description='3.3㎡ 당 직방시세 (만원/3.3㎡). 0 이면 시세가 없는 달일 수 있다')
    ] = None


class ZigbangDanjiPriceChartLineModel(ZigbangBaseResponseModel):
    """직방시세 추이의 줄 하나 (조회 단지, 비교 단지, 그 구)."""

    label: Annotated[
        str | None,
        Field(description='줄 이름 (단지 이름 또는 구 이름)')
    ] = None
    type: Annotated[
        str | None,
        Field(description="줄 종류 ('sale' 매매 시세)")
    ] = None
    data: Annotated[
        list[ZigbangDanjiPriceChartPointModel] | None,
        Field(description='월별 시세 (오래된 달부터)')
    ] = None


class ZigbangDanjiPriceChartSummaryModel(ZigbangBaseResponseModel):
    """직방시세 그래프의 범위."""

    min_price: Annotated[
        int | float | None,
        Field(description='가장 낮은 시세 (만원/3.3㎡)', alias='minPrice')
    ] = None
    max_price: Annotated[
        int | float | None,
        Field(description='가장 높은 시세 (만원/3.3㎡)', alias='maxPrice')
    ] = None
    start_date: Annotated[
        str | None,
        Field(description='시작 월 (YYYY-MM-01)', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='끝 월 (YYYY-MM-01)', alias='endDate')
    ] = None


class ZigbangDanjisPriceChartResponseModel(ZigbangBaseResponseModel):
    """단지 직방시세 추이. 키 이름이 `list` 라 `lines` 로 받는다 (속성 `list` 가 내장 `list` 를 가린다).

    비교 단지(`addDanjiIds`)를 주면 줄이 늘어난다 (2026-11-22 표본: 조회 단지 + 비교 셋 + 구, 단지 ID 오름차순 뒤에 구가 왔다).
    없는 단지도 200 에 빈 `list` 가 온다 (2026-11-22 실측).
    직방시세가 없는 단지(분양예정 등)는 조회 단지 줄 없이 구 줄만 온다 (2026-11-22 실측: apt-90913 `[서초구]`, apt-94457 + 비교 헬리오시티
    `[헬리오시티, 송파구]`). 구 줄은 늘 마지막이고 서울 밖도 시·군·세종 줄이 마지막에 온다 (apt-52058 `[양평하늘채센트로힐스, 양평군]`).
    """

    lines: Annotated[
        list[ZigbangDanjiPriceChartLineModel] | None,
        Field(description='줄 (응답 순서 그대로)', alias='list')
    ] = None
    summary: Annotated[
        ZigbangDanjiPriceChartSummaryModel | None,
        Field(description='그래프 범위')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/price-chart/related-danjis
# ---------------------------------------------------------------------------

class ZigbangDanjisPriceChartRelatedDanjisResponseModel(ZigbangBaseResponseModel):
    """직방시세 그래프에서 비교할 만한 단지. 키 이름이 `list` 라 `danjis` 로 받는다 (속성 `list` 가 내장 `list` 를 가린다).

    웹 '+ 단지 비교하기' 의 후보다. 항목은 단지 상세의 관련 단지(`relateDanji`)와 같은 모양이다.
    """

    danjis: Annotated[
        list[ZigbangRelatedDanjiModel] | None,
        Field(description='비교 후보 단지', alias='list')
    ] = None


# ---------------------------------------------------------------------------
# GET /apt/danjis/{danjiId}/room-types/{danjiRoomTypeId}/price-chart
# ---------------------------------------------------------------------------

class ZigbangRoomTypePriceGapModel(ZigbangBaseResponseModel):
    """전달 대비 변화 (snake_case)."""

    price: Annotated[
        int | float | None,
        Field(description='직방시세 변화 (만원)')
    ] = None
    price_rate: Annotated[
        int | float | None,
        Field(description='직방시세 변화율 (0~1 비율, 0.05 는 5%)')
    ] = None
    volume: Annotated[
        int | None,
        Field(description='거래 건수 변화 (건)')
    ] = None
    rent_volume: Annotated[
        int | None,
        Field(description='월세 거래 건수 변화 (건, 전월세 탭만)')
    ] = None


class ZigbangRoomTypePriceMonthModel(ZigbangBaseResponseModel):
    """평형 하나의 한 달 시세·거래 (snake_case). 금액은 만원이다. 그 달 거래 목록(`trades`)은 읽지 않는다."""

    date: Annotated[
        str | None,
        Field(description='월 (YYYY-MM-01)')
    ] = None
    min_price: Annotated[
        int | float | None,
        Field(description='그 달 거래의 최저가 (만원)')
    ] = None
    max_price: Annotated[
        int | float | None,
        Field(description='그 달 거래의 최고가 (만원)')
    ] = None
    average_price: Annotated[
        int | float | None,
        Field(description='그 달 직방시세 (만원). 입주 전 달처럼 0 인 달은 시세가 없는 달이다')
    ] = None
    volume: Annotated[
        int | None,
        Field(description='그 달 거래 건수 (매매 탭은 매매, 전월세 탭은 전세)')
    ] = None
    rent_volume: Annotated[
        int | None,
        Field(description='그 달 월세 거래 건수 (전월세 탭만 온다)')
    ] = None
    monthly_gap: Annotated[
        ZigbangRoomTypePriceGapModel | None,
        Field(description='전달 대비 변화')
    ] = None


class ZigbangRoomTypePriceByTypeModel(ZigbangBaseResponseModel):
    """평형 시세의 거래 탭별 월 목록. 평형 ID 가 틀리면 빈 객체 `{}` 라 두 칸 모두 None 이다 (2026-11-22 실측).

    기록이 없는 탭도 키가 없다 (2026-11-22 실측: apt-94091 평형 442794 dealType rent 도 `{}`). 그래서 응답만으로는 없는 평형과 기록 없는
    평형을 가를 수 없다.
    """

    trade: Annotated[
        list[ZigbangRoomTypePriceMonthModel] | None,
        Field(description='매매 월별 시세 (`dealType` 이 all·sales 일 때)')
    ] = None
    deposit: Annotated[
        list[ZigbangRoomTypePriceMonthModel] | None,
        Field(description='전월세 월별 시세 (`dealType` 이 all·rent 일 때)')
    ] = None


class ZigbangRoomTypePriceChartSummaryModel(ZigbangBaseResponseModel):
    """평형 시세 그래프의 범위 (camelCase. 월 항목은 snake_case 라 키가 다르다)."""

    min_price: Annotated[
        int | float | None,
        Field(description='월별 `min_price` 중 가장 낮은 값 (만원)', alias='minPrice')
    ] = None
    max_price: Annotated[
        int | float | None,
        Field(description='월별 `max_price` 중 가장 높은 값 (만원)', alias='maxPrice')
    ] = None
    start_date: Annotated[
        str | None,
        Field(description='시작 월 (YYYY-MM-01)', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='끝 월 (YYYY-MM-01)', alias='endDate')
    ] = None
    max_size: Annotated[
        int | None,
        Field(description='그래프 막대의 최댓값 (건). 한 달의 거래 건수(`volume` + `rent_volume`)의 최댓값과 같았다 (2026-11-22 표본)', alias='maxSize')
    ] = None
    move_in_date: Annotated[
        str | None,
        Field(description='단지 입주일 (YYYY-MM-DD)', alias='입주일')
    ] = None


class ZigbangDanjisRoomTypesPriceChartResponseModel(ZigbangBaseResponseModel):
    """평형 하나의 월별 시세 추이. 키 이름이 `list` 라 `months_by_type` 으로 받는다 (속성 `list` 가 내장 `list` 를 가린다)."""

    months_by_type: Annotated[
        ZigbangRoomTypePriceByTypeModel | None,
        Field(description='거래 탭별 월 목록', alias='list')
    ] = None
    summary: Annotated[
        ZigbangRoomTypePriceChartSummaryModel | None,
        Field(description='그래프 범위')
    ] = None
