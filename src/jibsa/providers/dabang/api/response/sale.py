from pydantic import (
    Field,
    RootModel,
)

from jibsa.core.schema import ResponseModel
from jibsa.providers.dabang.api.response.common import DabangV5ResponseModel

from typing import (
    Annotated,
    Any,
)


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
        Field(description="분양 세대수 ('87세대'. 상세의 lots_household_num 이고 총세대수가 아니다)", alias='householdNumTitle')
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
    region_average_pyeong_price: Annotated[
        str | None,
        Field(description="최근 6개월 이 지역 평균 평당가 ('1294', 만원/3.3㎡). 없으면 null")
    ] = None


class DabangSubscriptionSpaceModel(ResponseModel):
    """청약 결과의 평형 하나 (웹 '청약결과' 표: 평형명·분양/총세대·경쟁률·당첨가점·분양가)."""

    space_name: Annotated[
        str | None,
        Field(description="평형 ('59A')")
    ] = None
    household_num_str: Annotated[
        str | None,
        Field(description="분양/총세대 ('261/1071')")
    ] = None
    competitive_rate_str: Annotated[
        str | None,
        Field(description="경쟁률 ('5.52:1')")
    ] = None
    winning_point_str: Annotated[
        str | None,
        Field(description="당첨가점 ('43점')")
    ] = None
    price_str: Annotated[
        str | None,
        Field(description="분양가(임대면 임대가) ('5.5억')")
    ] = None


class DabangSubscriptionResultModel(ResponseModel):
    """청약 결과 (`subscriptionResult`, 안쪽 키는 snake_case). 청약 전이면 `subscriptionResult` 가 null 이다 (2026-11-13 실측)."""

    min_winning_point_str: Annotated[
        str | None,
        Field(description="최저 당첨가점 ('35점', 웹 '당첨가점(커트라인)')")
    ] = None
    max_competitive_rate_str: Annotated[
        str | None,
        Field(description="최고 경쟁률 ('5.52:1')")
    ] = None
    subscription_spaces: Annotated[
        list[DabangSubscriptionSpaceModel] | None,
        Field(description='평형별 결과. null 이면 다방이 평형별 결과를 주지 않은 것이라 모름')
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
    supply_type: Annotated[
        int | None,
        Field(description='공급 유형 코드 (1 민간분양, 5 민간임대 등). 웹은 4·5 면 가격을 임대가, 아니면 분양가로 쓴다')
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
    subscription_result: Annotated[
        DabangSubscriptionResultModel | None,
        Field(description='청약 결과 (청약 전이면 null)', alias='subscriptionResult')
    ] = None


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


class DabangSaleInLotsRowModel(ResponseModel):
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


class DabangSaleInLotsListSearch3V3ResponseModel(ResponseModel):
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


class DabangSaleInLotsListScheduleSearchV3ResponseModel(RootModel[list[DabangSaleScheduleTableRowModel]]):
    """`GET /api/3/sale-in-lots/list/schedule/search` 응답 (그 날 일정의 분양 단지, 봉투 없음).

    요약(`list/schedule`)의 그 날 일정과 같은 단지가 같은 순서로 온다 (2026-11-13 캡처: 11-16 24건, 분양 ID 와 종류 번호가
    모두 같았다).
    """
