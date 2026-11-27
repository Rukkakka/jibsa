"""요청 모델: 지역 정보·거래량·평당 추이·인구·세대 (region-info)."""


from pydantic import Field

from jibsa.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# 웹 평당 추이 그래프의 평형 탭. 2026-11-22 실측: '10평이하'·'60평대이상' 도 200
ZigbangPynAreaType = Literal['전체', '10평이하', '10평대', '20평대', '30평대', '40평대', '50평대', '60평대이상']


class ZigbangLocalsRequestParameterModel(RequestModel):
    """`GET /apt/locals/{localCode}` 경로. 동·구·시도의 지역 정보 (웹 지역정보 화면 `/home/apt/locals/{코드}`).

    구가 있는 시(예: 41130)의 5자리 코드는 404 'INVALID LOCAL ID' 다 (2026-11-22 실측).
    """

    local_code: Annotated[
        str,
        Field(
            pattern=r'^\d{2}(\d{3}(\d{3})?)?$',
            exclude=True,
            description='지역 코드. 법정동코드 앞 8자리(동)·5자리(구)·2자리(시도). 경로에 들어간다'
        )
    ]


class ZigbangLocalsTradingVolumeChartRequestParameterModel(RequestModel):
    """`GET /apt/locals/trading-volume-chart` 쿼리. 지역의 월별 거래량."""

    local_code: Annotated[
        str,
        Field(pattern=r'^\d{2}(\d{3}(\d{3})?)?$', description='지역 코드 (동 8자리·구 5자리·시도 2자리)', alias='localCd')
    ]


class ZigbangLocalsPynChartPriceRequestParameterModel(RequestModel):
    """`GET /apt/locals/pyn-chart-price` 쿼리. 지역의 평당가 추이 (평형 탭 하나)."""

    local_code: Annotated[
        str,
        Field(pattern=r'^\d{2}(\d{3}(\d{3})?)?$', description='지역 코드 (동 8자리·구 5자리·시도 2자리)', alias='localCd')
    ]
    pyn_area_type: Annotated[
        ZigbangPynAreaType,
        Field(description="평형 탭. 웹 기본은 '전체'", alias='pynAreaType')
    ]


class ZigbangLocalsTotalPeopleTimeRequestParameterModel(RequestModel):
    """`GET /apt/locals/{localCode}/total_people_time` 경로 + 쿼리. 지역의 월별 연령대별 인구.

    웹은 `startDate=202110&endDate=202610` 처럼 다섯 해 전 달부터 지난달까지 보낸다 (2026-11-19 캡처).
    """

    local_code: Annotated[
        str,
        Field(pattern=r'^\d{2}(\d{3}(\d{3})?)?$', exclude=True, description='지역 코드 (동 8자리·구 5자리·시도 2자리). 경로에 들어간다')
    ]
    start_date: Annotated[
        str,
        Field(pattern=r'^\d{6}$', description='시작 월 (YYYYMM)', alias='startDate')
    ]
    end_date: Annotated[
        str,
        Field(pattern=r'^\d{6}$', description='끝 월 (YYYYMM)', alias='endDate')
    ]


class ZigbangLocalsTotalHouseholdsTimeRequestParameterModel(ZigbangLocalsTotalPeopleTimeRequestParameterModel):
    """`GET /apt/locals/{localCode}/total_households_time` 경로 + 쿼리. 지역의 월별 가구원 수별 세대. 요청 모양은 인구 조회와 같다."""
