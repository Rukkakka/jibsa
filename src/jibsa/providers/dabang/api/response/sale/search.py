"""응답 모델: 분양 단지 목록 (search sales)."""
from pydantic import (
    Field,
)

from jibsa.providers.dabang.api.response.common import (
    DabangBaseResponseModel,
    DabangV5ResponseModel,
)
from jibsa.providers.dabang.api.response.sale.base import DabangSaleInLotsRowModel

from typing import (
    Annotated,
    Any,
)


class DabangSaleItemModel(DabangBaseResponseModel):
    """분양 지도 목록의 단지 하나. 좌표·동 번호는 오지 않는다 (2026-10-25 실측).

    Args:
        state_name: '분양예정', '접수중', '접수마감', '입주예정', '입주모집'.
        price_title: 분양가 글자 ('7억9096', '준비중').
        schedule_title: 다음 일정 ('26.12.07 ~ 26.12.10 계약기간').
    """

    id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    state_name: Annotated[
        str | None,
        Field(description='분양 상태', alias='stateName')
    ] = None
    building_type_title: Annotated[
        str | None,
        Field(description="건물 유형 ('아파트')", alias='buildingTypeTitle')
    ] = None
    supply_type_name: Annotated[
        str | None,
        Field(description="공급 유형 ('공공분양')", alias='supplyTypeName')
    ] = None
    building_name: Annotated[
        str,
        Field(description='단지 이름', alias='buildingName')
    ]
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    household_num_title: Annotated[
        str | None,
        Field(description="분양 세대수 ('87세대'. 상세의 lots_household_num 이고 총세대수가 아니다)", alias='householdNumTitle')
    ] = None
    supply_price_type_name: Annotated[
        str | None,
        Field(description="가격 종류 ('분양가', 공공·민간임대 공급이면 '임대가')", alias='supplyPriceTypeName')
    ] = None
    price_title: Annotated[
        str | None,
        Field(description='가격 글자 (만원)', alias='priceTitle')
    ] = None
    schedule_title: Annotated[
        str | None,
        Field(description='다음 일정', alias='scheduleTitle')
    ] = None


class DabangSaleListResultModel(DabangBaseResponseModel):
    """분양 지도 목록 `result`. `recommendList` 는 범위와 상관없는 추천 칸이라 쓰지 않는다 (서울 범위에 부산 단지, 2026-10-25)."""

    sale_list: Annotated[
        list[DabangSaleItemModel],
        Field(description='분양 단지', alias='saleList')
    ] = []
    recommend_list: Annotated[
        list[DabangSaleItemModel],
        Field(description='추천 칸', alias='recommendList')
    ] = []
    total: Annotated[
        int | None,
        Field(description='범위 안 분양 단지 수')
    ] = None
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지', alias='hasMore')
    ] = None


class DabangSaleListCategoryBboxV5ResponseModel(DabangV5ResponseModel[DabangSaleListResultModel]):
    """`GET /api/v5/sale-list/category/bbox` 응답."""


class DabangSaleInLotsItemModel(DabangSaleInLotsRowModel):
    """분양 지역 목록(`list/search3`)의 단지 하나. 결과 줄이라 분양 ID 와 단지 이름이 꼭 있어야 한다.

    Args:
        title: 웹 목록의 일정 줄 ('26.11.16 특별공급', '28.08월 입주예정일', '분양일정 준비중').
    """

    id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    building_name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    title: Annotated[
        str | None,
        Field(description='일정 줄')
    ] = None


class DabangSaleInLotsListSearch3V3ResponseModel(DabangBaseResponseModel):
    """`GET /api/3/sale-in-lots/list/search3` 응답 (봉투 없음).

    `features` 는 분양 홈 위쪽의 추천 단지 칸(home 청크 `features`)과 같은 꼴이고 웹 지역 목록은 그리지 않는다
    (list 청크는 `saleInLotses`·`total` 만 쓴다, 2026-11-13). 전국 1쪽에 1곳, 김포시는 0곳이었다.
    """

    sale_in_lotses: Annotated[
        list[DabangSaleInLotsItemModel] | None,
        Field(description='분양 단지. null 이면 이 쪽은 빈 쪽', alias='saleInLotses')
    ] = None
    features: Annotated[
        list[dict[str, Any]] | None,
        Field(description='추천 칸 (웹 지역 목록에 없다). 개수만 세어 줄 내용은 검사하지 않는다. null 이면 추천 칸 없음')
    ] = None
    total: Annotated[
        int | None,
        Field(description="범위 안 분양 단지 수 (웹 '분양목록 총 N건')")
    ] = None
    # 리뷰 오탐 (2026-11-14): search3(v3)는 has_more 를 snake_case 로 준다 (실측: 서울 97곳 1쪽 has_more true, --limit 50 이 3쪽 받음)
    has_more: Annotated[
        bool | None,
        Field(description='다음 쪽이 있는지')
    ] = None
