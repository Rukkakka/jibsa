"""응답 모델: 청약 일정 (sale-schedule)."""
from pydantic import (
    Field,
    PrivateAttr,
    RootModel,
    ValidatorFunctionWrapHandler,
    model_validator,
)

from jibsa.core.schema import add_null_item_tally
from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
)
from jibsa.providers.dabang.api.models.response.sale.common import (
    DabangSaleInLotsRowModel,
)

from typing import (
    Annotated,
    Any,
    Generic,
    TypeVar,
)


T = TypeVar('T')


class DabangRootListModel(RootModel[list[T]], Generic[T]):
    """봉투 없이 목록 하나가 오는 응답의 기반. 목록 안의 null 원소는 빼고 그 수를 `null_items` 로 센다.

    `ResponseModel.null_items` 는 모델 칸의 목록만 다뤄 루트 목록에는 닿지 않아, 같은 규칙(빼고 읽고, 계산하는 쪽이 뺀 수를
    알게 한다)을 여기서 따로 붙인다. 원소가 `None` 일 수 있는 자료형이 아니라 모델이어야 뺄 수 있다.
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


class DabangSaleScheduleEntryModel(DabangBaseResponseModel):
    """청약 일정 한 줄 ('[청약접수] 인천 … (~10/27)')."""

    id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None
    schedule_str: Annotated[
        str | None,
        Field(description='일정 글')
    ] = None


class DabangSaleScheduleTypeModel(DabangBaseResponseModel):
    """하루 일정의 종류 묶음 ('접수 16건')."""

    type: Annotated[
        int | None,
        Field(description='종류 번호 (1 접수, 4 발표, 5 계약 등). 하루 상세 줄의 `grouping` 과 같은 값이다')
    ] = None
    type_title: Annotated[
        str | None,
        Field(description="종류와 건수 ('접수 16건')")
    ] = None
    schedules: Annotated[
        list[DabangSaleScheduleEntryModel],
        Field(description='일정')
    ] = []


class DabangSaleScheduleDayModel(DabangBaseResponseModel):
    """청약 일정 하루."""

    date: Annotated[
        str,
        Field(description='날 (YYYY-MM-DD)')
    ]
    schedule_count: Annotated[
        int | None,
        Field(description='일정 수')
    ] = None
    schedule_by_type: Annotated[
        list[DabangSaleScheduleTypeModel],
        Field(description='종류별 일정')
    ] = []


class DabangSaleInLotsListScheduleV3ResponseModel(DabangRootListModel[DabangSaleScheduleDayModel]):
    """`GET /api/3/sale-in-lots/list/schedule` 응답 (날 목록, 봉투 없음)."""


class DabangSaleScheduleTableRowModel(DabangSaleInLotsRowModel):
    """청약 일정 하루 표(`list/schedule/search`)의 단지 하나. 요약 줄과 맞춰 보는 데만 쓴다.

    분양 ID 가 없는 줄도 받아 두고(요약 줄 `DabangSaleScheduleEntryModel.id` 도 null 일 수 있다), 맞추는 쪽이 ID·종류 번호가
    모두 있는 줄만 쓴다. 한 줄이 ID 를 안 줘도 표 전체가 응답 검증에서 터지지 않게 하려는 것이다.

    Args:
        grouping: 그 날 일정의 종류 번호 (1 접수, 4 발표, 5 계약 등, 요약의 `type` 과 같다).
    """

    id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None
    grouping: Annotated[
        int | None,
        Field(description='그 날 일정의 종류 번호')
    ] = None


class DabangSaleInLotsListScheduleSearchV3ResponseModel(DabangRootListModel[DabangSaleScheduleTableRowModel]):
    """`GET /api/3/sale-in-lots/list/schedule/search` 응답 (그 날 일정의 분양 단지, 봉투 없음).

    요약(`list/schedule`)의 그 날 일정과 같은 단지가 같은 순서로 온다 (2026-11-13 캡처: 11-16 24건, 분양 ID 와 종류 번호가
    모두 같았다).
    """
