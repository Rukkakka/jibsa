"""응답 모델: 단지 정보 (complex)."""
from pydantic import Field

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangLatelyPriceModel(DabangBaseResponseModel):
    """단지 요약의 최근 실거래 한 건 (글자로 온다)."""

    format_price: Annotated[
        str | None,
        Field(description="가격 ('34억 3,000')", alias='formatPrice')
    ] = None
    format_contract_date: Annotated[
        str | None,
        Field(description="계약일 ('26.10.06')", alias='formatContractDate')
    ] = None
    format_floor: Annotated[
        str | None,
        Field(description="층 ('3층')", alias='formatFloor')
    ] = None
    format_room_size: Annotated[
        str | None,
        Field(description="면적 ('115.54㎡')", alias='formatRoomSize')
    ] = None


class DabangComplexSummaryResultModel(DabangBaseResponseModel):
    """단지 요약 `result`."""

    sell_lately_price: Annotated[
        DabangLatelyPriceModel | None,
        Field(description='최근 매매', alias='sellLatelyPrice')
    ] = None
    lease_lately_price: Annotated[
        DabangLatelyPriceModel | None,
        Field(description='최근 전세', alias='leaseLatelyPrice')
    ] = None


class DabangComplexSummaryV5ResponseModel(DabangV5ResponseModel[DabangComplexSummaryResultModel]):
    """`GET /api/v5/complex/{complex_type}/summary` 응답."""


class DabangComplexLoanCalcConditionResultModel(DabangBaseResponseModel):
    """단지 대출 계산 조건 `result`. 금리 두 값(`saleLoanInterestRate`·`leaseLoanInterestRate`)은 다방 계산기의 기본값이라 두지
    않는다."""

    is_overheated_district: Annotated[
        bool | None,
        Field(description="다방 대출 계산기가 대출 비율을 50%로 묶는 지역인지 (웹 문구 '투기지역 (대출 비율 50% 제한)')", alias='isOverheatedDistrict')
    ] = None


class DabangComplexLoanCalcConditionV5ResponseModel(DabangV5ResponseModel[DabangComplexLoanCalcConditionResultModel]):
    """`GET /api/v5/complex/{complex_id}/loan-calc-condition` 응답. 없는 단지는 400 '존재하지 않는 단지 정보입니다.' 다
    (2026-11-14 실측)."""
