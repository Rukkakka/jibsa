"""요청 모델: 청약 일정 (sale-schedule)."""
from datetime import date

from pydantic import (
    Field,
    field_serializer,
    model_validator,
)

from jibsa.providers.dabang.api.models.request.common import (
    DabangV3RequestParameterModel,
)

from typing import (
    Annotated,
    Self,
)


# 청약 일정 한 번에 받을 수 있는 날 수. 그보다 길면 400 "최대 일주일의 데이터를 요청할 수 있습니다." (2026-10-25 실측: 10-26~11-01 은 200)
SALE_SCHEDULE_MAX_DAYS: int = 7


class DabangSaleInLotsListScheduleV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/list/schedule` 쿼리 (날짜별 청약 일정, 최대 7일).

    Args:
        from_date: 시작 날 (YYYY-MM-DD).
        to_date: 끝 날 (YYYY-MM-DD, 시작 날부터 7일 안).
    """

    from_date: Annotated[
        date,
        Field(description='시작 날', alias='from')
    ]
    to_date: Annotated[
        date,
        Field(description='끝 날', alias='to')
    ]

    @field_serializer('from_date', 'to_date')
    def as_text(self, value: date) -> str:
        return value.isoformat()

    @model_validator(mode='after')
    def within_a_week(self) -> Self:
        days = (self.to_date - self.from_date).days + 1
        if days < 1:
            raise ValueError(f'끝 날({self.to_date})이 시작 날({self.from_date})보다 빠릅니다')
        if days > SALE_SCHEDULE_MAX_DAYS:
            raise ValueError(f'다방 청약 일정은 한 번에 {SALE_SCHEDULE_MAX_DAYS}일까지 받습니다 ({days}일)')
        return self


class DabangSaleInLotsListScheduleSearchV3RequestParameterModel(DabangV3RequestParameterModel):
    """`GET /api/3/sale-in-lots/list/schedule/search` 쿼리 (청약 일정 하루의 분양 단지).

    Args:
        from_date: 그 날. 웹처럼 날만 0 을 채우지 않고 보낸다 ('2026-11-5', schedule 청크 `yyyy-MM-d`).
    """

    from_date: Annotated[
        date,
        Field(description='그 날', alias='from')
    ]

    @field_serializer('from_date')
    def as_text(self, value: date) -> str:
        return f'{value.year}-{value.month:02d}-{value.day}'
