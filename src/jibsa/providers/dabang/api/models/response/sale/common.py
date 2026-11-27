"""응답 모델: 분양 기능(sale)의 목록·일정이 같이 쓰는 것: 분양 단지 줄."""
from pydantic import (
    Field,
)

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
)

from typing import (
    Annotated,
)


class DabangSaleInLotsRowModel(DabangBaseResponseModel):
    """분양 지역 목록(`list/search3`)·청약 일정 하루 표(`list/schedule/search`)의 한 줄에 공통인 칸. 키는 snake_case 다.

    웹 목록 표는 단계·건물유형·공급유형·단지명/주소/일정·분양가(`price_str`)·세대수(`lots_household_num`)·전용면적을
    그린다 (sale-in-lots-list·schedule 청크, 2026-11-13). 좌표(`location`)·사진(`represent_image`)은 모델에 두지 않는다.
    분양 ID·일정 줄은 두 목록이 달라 자식 모델에 둔다 (`DabangSaleInLotsItemModel`·`DabangSaleScheduleTableRowModel`).
    """

    state_title: Annotated[
        str | None,
        Field(description="분양 상태 ('접수중')")
    ] = None
    building_types_title: Annotated[
        str | None,
        Field(description="건물 유형 ('아파트')")
    ] = None
    supply_type_title: Annotated[
        str | None,
        Field(description="공급 유형 ('민간분양')")
    ] = None
    address: Annotated[
        str | None,
        Field(description="동까지의 주소 ('경기도 김포시 사우동')")
    ] = None
    total_household_num: Annotated[
        int | None,
        Field(description='총 세대수 (상세의 total_household_num)')
    ] = None
    lots_household_num: Annotated[
        int | None,
        Field(description='분양 세대수 (상세의 lots_household_num, 웹 목록의 세대수 칸)')
    ] = None
    price_supply_type_str: Annotated[
        str | None,
        Field(description="가격 종류 ('분양가', 공공임대·민간임대는 '임대가')")
    ] = None
    price_str: Annotated[
        str | None,
        Field(description="대표 가격 글자 ('5억5720', '준비중', 만원)")
    ] = None
