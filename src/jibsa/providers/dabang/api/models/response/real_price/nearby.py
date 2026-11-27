"""응답 모델: 평형대 평당가와 주변 단지 비교 (nearby-complexes)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangAreaAveragePriceModel,
    DabangBaseResponseModel,
    DabangV5ResponseModel,
    Meters,
)

from typing import Annotated


class DabangNearComplexModel(DabangBaseResponseModel):
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


class DabangNearComplexesModel(DabangBaseResponseModel):
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


class DabangRealPriceComplexPricePerPyResultModel(DabangBaseResponseModel):
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
