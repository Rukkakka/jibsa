"""응답 모델: 지역 단지 랭킹 (region-ranking)."""

from pydantic import Field

from jibsa.providers.zigbang.api.response.common import ZigbangBaseResponseModel

from typing import Annotated


class ZigbangDanjiRankingModel(ZigbangBaseResponseModel):
    """단지 랭킹 한 줄. 순위 기준(`sortType`)과 거래 유형에 따라 채워지는 칸이 다르고 나머지는 키가 없다. 금액은 만원 단위다.

    2026-11-22 표본: 평당가 순은 `unit_price`, 가격 순은 `price`, 거래량 순은 `volume`, 조회수 순은 `view_count`, 전세가율 순은
    `gap`·`charter_rate`, 상승·하락률 순은 `rt_deal_date`·`rt_price`·`diff_rt_price`·`percent_rt_price`·`danji_room_type_name` 이
    왔고, 시도·구 조회는 `local` 이 더해졌다 (구 조회는 동 이름만). 사진·좌표는 읽지 않는다.
    """

    area_danji_id: Annotated[
        int | None,
        Field(description='단지 ID', alias='areaDanjiId')
    ] = None
    area_danji_name: Annotated[
        str | None,
        Field(description='단지 이름', alias='areaDanjiName')
    ] = None
    ranking_number: Annotated[
        int | None,
        Field(description='순위 (1부터)', alias='rankingNumber')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYYMMDD)', alias='사용승인일')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수', alias='총세대수')
    ] = None
    local: Annotated[
        str | None,
        Field(description="구·동 이름 (예: '강남구 대치동'). 시도 조회에서 왔고 동 조회에는 없었다 (2026-11-22 표본). 구 조회는 동 이름만 온다 (2026-11-22 실측: 송파구 → '거여동'·'문정동'·'가락동')")
    ] = None
    volume: Annotated[
        int | None,
        Field(description='기간 안 거래 건수 (거래량 순)')
    ] = None
    rt_deal_date: Annotated[
        str | None,
        Field(description='가장 최근 계약일 (YYYY-MM-DD, 상승·하락률 순)', alias='rtDealDate')
    ] = None
    rt_price: Annotated[
        int | float | None,
        Field(description='가장 최근 거래가 (만원, 상승·하락률 순)', alias='rtPrice')
    ] = None
    diff_rt_price: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 차액 (만원, 상승·하락률 순)', alias='diffRtPrice')
    ] = None
    percent_rt_price: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, 상승·하락률 순)', alias='percentRtPrice')
    ] = None
    danji_room_type_name: Annotated[
        str | None,
        Field(description="평형 이름 (예: '102B', 상승·하락률 순)", alias='danjiRoomTypeName')
    ] = None
    price: Annotated[
        int | float | None,
        Field(description='가격 (만원, 가격 순)')
    ] = None
    unit_price: Annotated[
        int | float | None,
        Field(description='평당가 (만원/3.3㎡, 평당가 순)', alias='unitPrice')
    ] = None
    gap: Annotated[
        int | float | None,
        Field(description='매매가와 전세가의 차이 (만원, 전세가율 순)')
    ] = None
    charter_rate: Annotated[
        int | float | None,
        Field(description='전세가율 (%, 전세가율 순)', alias='charterRate')
    ] = None
    view_count: Annotated[
        int | None,
        Field(description='조회수 (조회수 순)', alias='viewCount')
    ] = None


class ZigbangLocalsDanjiRankingResponseModel(ZigbangBaseResponseModel):
    """지역 단지 랭킹 응답. 봉투가 없다. 기간 칸(`startDate`)은 어떤 순위에는 오지 않는다."""

    start_date: Annotated[
        str | None,
        Field(description='집계 시작 (ISO 8601 UTC, 예: 2026-10-31T15:00:00.000Z). 오지 않는 순위가 있다', alias='startDate')
    ] = None
    end_date: Annotated[
        str | None,
        Field(description='집계 끝 (ISO 8601 UTC)', alias='endDate')
    ] = None
    updated_date: Annotated[
        str | None,
        Field(description='갱신 시각 (ISO 8601 UTC). 오지 않는 순위가 있다', alias='updatedDate')
    ] = None
    count: Annotated[
        int | None,
        Field(description='전체 순위 수 (서버는 200위까지만 준다)')
    ] = None
    rankings: Annotated[
        list[ZigbangDanjiRankingModel] | None,
        Field(description='이 쪽의 순위', alias='list')
    ] = None
