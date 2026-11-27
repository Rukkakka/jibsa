"""응답 모델: 분양 단지 상세 (sale)."""
from pydantic import (
    Field,
)

from jibsa.providers.dabang.api.models.response.common import (
    DabangBaseResponseModel,
)

from typing import (
    Annotated,
)


class DabangSaleInLotsPriceInfoModel(DabangBaseResponseModel):
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


class DabangSubscriptionSpaceModel(DabangBaseResponseModel):
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


class DabangSubscriptionResultModel(DabangBaseResponseModel):
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


class DabangSaleInLotsModel(DabangBaseResponseModel):
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


class DabangSaleScheduleModel(DabangBaseResponseModel):
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


class DabangSaleSpaceModel(DabangBaseResponseModel):
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


class DabangSaleInLotsDetail2V3ResponseModel(DabangBaseResponseModel):
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
