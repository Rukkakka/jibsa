from pydantic import (
    Field,
    RootModel,
)

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangV5ResponseModel

from typing import Annotated


class DabangSaleItemModel(ResponseModel):
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
        Field(description="세대수 ('594세대')", alias='householdNumTitle')
    ] = None
    supply_price_type_name: Annotated[
        str | None,
        Field(description="가격 종류 ('분양가', '보증금')", alias='supplyPriceTypeName')
    ] = None
    price_title: Annotated[
        str | None,
        Field(description='가격 글자 (만원)', alias='priceTitle')
    ] = None
    schedule_title: Annotated[
        str | None,
        Field(description='다음 일정', alias='scheduleTitle')
    ] = None


class DabangSaleListResultModel(ResponseModel):
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


class DabangSaleInLotsPriceInfoModel(ResponseModel):
    """분양가 범위와 평당가 (만원 글자)."""

    price_str: Annotated[
        str | None,
        Field(description="분양가 범위 ('7억9096 ~ 8억1214')")
    ] = None
    pyeong_price: Annotated[
        str | None,
        Field(description="평당 분양가 ('1789', 만원)")
    ] = None


class DabangSaleInLotsModel(ResponseModel):
    """분양 상세의 단지 (`saleInLots`). 키는 snake_case 다. 상담 전화(`contact`)·사진·좌표는 모델에 두지 않는다.

    `provider_name` 은 시공사, `constructor_name` 은 시행사다 (2026-10-25 실측: LH 신혼희망타운의 provider_name 이
    '(주)케이알산업, 동성건설(주)', constructor_name 이 '한국토지주택공사 서울지역본부'. 단지 상세 providerName 도 시공사다).
    """

    id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    building_name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    state_str: Annotated[
        str | None,
        Field(description='분양 상태')
    ] = None
    building_types_str: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type_str: Annotated[
        str | None,
        Field(description='공급 유형')
    ] = None
    jibun_address: Annotated[
        str | None,
        Field(description="지번 주소 ('… 신흥동 일원')")
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    total_household_num: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    lots_household_num: Annotated[
        int | None,
        Field(description='분양 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    ground_floor: Annotated[
        int | None,
        Field(description='지상 층수')
    ] = None
    underground_floor: Annotated[
        int | None,
        Field(description='지하 층수')
    ] = None
    provider_name: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    constructor_name: Annotated[
        str | None,
        Field(description='시행사')
    ] = None
    price_str: Annotated[
        str | None,
        Field(description="분양가 요약 ('7.9억~')")
    ] = None
    price_info: Annotated[
        DabangSaleInLotsPriceInfoModel | None,
        Field(description='분양가 범위·평당가')
    ] = None
    moving_date_str: Annotated[
        str | None,
        Field(description="입주 예정 ('30.05월')")
    ] = None
    regulation_area_str: Annotated[
        str | None,
        Field(description='규제 지역')
    ] = None
    is_price_cap: Annotated[
        bool | None,
        Field(description='분양가 상한제')
    ] = None
    is_resalable: Annotated[
        bool | None,
        Field(description='전매 가능')
    ] = None
    notice_url: Annotated[
        str | None,
        Field(description='입주자 모집공고 파일 주소')
    ] = None
    applyhome_link: Annotated[
        str | None,
        Field(description='청약홈 주소')
    ] = None


class DabangSaleScheduleModel(ResponseModel):
    """분양 일정 한 단계."""

    type_str: Annotated[
        str | None,
        Field(description="단계 ('모집공고', '특별공급', '1순위 청약', '당첨자발표', '계약기간', '입주예정일')")
    ] = None
    from_str: Annotated[
        str | None,
        Field(description="시작 ('26.09.07', 달만 알면 '26.08월')")
    ] = None
    to_str: Annotated[
        str | None,
        Field(description='끝')
    ] = None


class DabangSaleSpaceModel(ResponseModel):
    """분양 평형 하나."""

    space_name: Annotated[
        str | None,
        Field(description="평형 ('55A')")
    ] = None
    supply_space: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    exclusive_space: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    household_num: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    price_str: Annotated[
        str | None,
        Field(description="분양가 ('7억9297', 만원 글자)")
    ] = None


class DabangSaleInLotsDetail2V3ResponseModel(ResponseModel):
    """`GET /api/3/sale-in-lots/detail2` 응답. 봉투 없이 온다. 중개사(`agents`)·추천 단지·매물도 오지만 모델에 두지 않는다."""

    sale_in_lots: Annotated[
        DabangSaleInLotsModel,
        Field(description='단지', alias='saleInLots')
    ]
    schedules: Annotated[
        list[DabangSaleScheduleModel],
        Field(description='일정')
    ] = []
    spaces: Annotated[
        list[DabangSaleSpaceModel],
        Field(description='평형')
    ] = []


class DabangSaleScheduleEntryModel(ResponseModel):
    """청약 일정 한 줄 ('[청약접수] 인천 … (~10/27)')."""

    id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None
    schedule_str: Annotated[
        str | None,
        Field(description='일정 글')
    ] = None


class DabangSaleScheduleTypeModel(ResponseModel):
    """하루 일정의 종류 묶음 ('접수 16건')."""

    type_title: Annotated[
        str | None,
        Field(description="종류와 건수 ('접수 16건')")
    ] = None
    schedules: Annotated[
        list[DabangSaleScheduleEntryModel],
        Field(description='일정')
    ] = []


class DabangSaleScheduleDayModel(ResponseModel):
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


class DabangSaleInLotsListScheduleV3ResponseModel(RootModel[list[DabangSaleScheduleDayModel]]):
    """`GET /api/3/sale-in-lots/list/schedule` 응답 (날 목록, 봉투 없음)."""
