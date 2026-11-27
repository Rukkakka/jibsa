"""폴더 안 명령 둘 이상이나 `common.py` 가 같이 쓰는 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    Field,
)

from jibsa.core.listing import (
    Listing,
)

from typing import (
    Annotated,
)


class ZigbangStayListing(Listing):
    """직방 단기임대 서비스 매물. 요금이 주 단위라 월세·월 관리비 대신 주당 금액을 준다."""

    weekly_rent_manwon: Annotated[
        float | None,
        Field(description='주당 임대료 (만원)')
    ] = None
    weekly_manage_cost_manwon: Annotated[
        float | None,
        Field(description='주당 관리비 (만원)')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    discounts: Annotated[
        list[str] | None,
        Field(description="할인 조건 (예: '4주 이상 10% 할인')")
    ] = None

    def not_applicable_fields(self) -> frozenset[str]:
        # 요금이 주 단위라 월세·월 관리비가 해당 없다
        return super().not_applicable_fields() | {'rent_manwon', 'manage_cost_manwon'}
