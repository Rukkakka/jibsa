from pydantic import Field

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import (
    DabangRoomListResponseModel,
    DabangV5ResponseModel,
)

from typing import Annotated


class DabangComplexListRealPriceModel(ResponseModel):
    """단지 목록의 최근 실거래 글 ('31억 3,000', 만원)."""

    sale: Annotated[
        str | None,
        Field(description='매매')
    ] = None
    lease: Annotated[
        str | None,
        Field(description='전세')
    ] = None


class DabangComplexListRoomCountModel(ResponseModel):
    """단지 목록의 거래 유형별 매물 수."""

    total_count: Annotated[
        int | None,
        Field(description='전체', alias='totalCount')
    ] = None
    monthly_rent_count: Annotated[
        int | None,
        Field(description='월세', alias='monthlyRentCount')
    ] = None
    lease_count: Annotated[
        int | None,
        Field(description='전세', alias='leaseCount')
    ] = None
    sell_count: Annotated[
        int | None,
        Field(description='매매', alias='sellCount')
    ] = None


class DabangComplexListItemModel(ResponseModel):
    """단지 지도 목록의 단지 하나. 매물이 없는 단지도 온다 (`roomCount.totalCount: 0`, 2026-10-25 실측).

    Args:
        complex_desc: '아파트 · 48년차 · 615세대'.
    """

    complex_type: Annotated[
        str | None,
        Field(description="'APT' 또는 'OFFICETEL'", alias='complexType')
    ] = None
    complex_id: Annotated[
        str,
        Field(description='단지 ID', alias='complexId')
    ]
    complex_name: Annotated[
        str,
        Field(description='단지 이름', alias='complexName')
    ]
    complex_desc: Annotated[
        str | None,
        Field(description='종류 · 연차 · 세대수', alias='complexDesc')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    gid: Annotated[
        int | None,
        Field(description='동 번호')
    ] = None
    dong_name: Annotated[
        str | None,
        Field(description='동 이름', alias='dongName')
    ] = None
    real_price: Annotated[
        DabangComplexListRealPriceModel | None,
        Field(description='최근 실거래', alias='realPrice')
    ] = None
    room_count: Annotated[
        DabangComplexListRoomCountModel | None,
        Field(description='매물 수', alias='roomCount')
    ] = None


class DabangComplexListResultModel(ResponseModel):
    """단지 지도 목록 `result` (24곳씩)."""

    list_: Annotated[
        list[DabangComplexListItemModel],
        Field(description='단지', alias='list')
    ] = []
    total: Annotated[
        int | None,
        Field(description='단지 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangComplexListCategoryV5ResponseModel(DabangV5ResponseModel[DabangComplexListResultModel]):
    """`GET /api/v5/complex-list/category/{category}/{search_type}` 응답."""


class DabangRoomListCategoryComplexV5ResponseModel(DabangRoomListResponseModel):
    """`GET /api/v5/room-list/category/{category}/complex` 응답 (단지 하나의 매물)."""


class DabangLatelyPriceModel(ResponseModel):
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


class DabangComplexSummaryResultModel(ResponseModel):
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
