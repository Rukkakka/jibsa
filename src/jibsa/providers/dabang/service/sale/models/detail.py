"""`detail.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.core.schema import drop_unset_fields
from jibsa.providers.dabang.service.sale.constants import GIVEN_AMOUNT_FIELDS

from typing import (
    Annotated,
    Any,
)


class DabangSaleStep(BaseModel):
    """분양 일정 한 단계. 시작·끝은 날이면 `*_date`, 달만 알면 `*_month` 키 하나만 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    step: Annotated[
        str,
        Field(description="단계 ('모집공고', '특별공급', '1순위 청약', '2순위 청약', '당첨자발표', '계약기간', '입주예정일')")
    ]
    start_date: Annotated[
        str | None,
        Field(description='시작 날 (YYYY-MM-DD). 달만 알면 키 없이 start_month. 다방이 시작을 주지 않았거나 읽지 못하면 null')
    ] = None
    start_month: Annotated[
        str | None,
        Field(description='시작 달 (YYYY-MM, 달만 아는 단계. 날을 알면 키 없음)')
    ] = None
    # 다방은 한 시점인 단계에만 끝을 주지 않는다. 하루짜리 청약은 끝이 시작과 같은 날로 온다 (2026-10-28 실측: 분양 3곳
    # 모두 모집공고·당첨자발표·입주예정일만 끝이 없음). 끝이 해당 없는 단계라 null(모름) 대신 키를 뺀다
    end_date: Annotated[
        str | None,
        Field(description='끝 날 (YYYY-MM-DD, 하루짜리는 시작과 같은 날. 달만 알면 키 없이 end_month. 모집공고·당첨자발표·입주예정일처럼 한 시점인 단계는 키 없음. 다방이 준 끝을 읽지 못하면 null)')
    ] = None
    end_month: Annotated[
        str | None,
        Field(description='끝 달 (YYYY-MM, 달만 아는 단계. 날을 알면 키 없음)')
    ] = None

    @model_serializer(mode='wrap')
    def keep_given_times(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 생성할 때 넘긴 시각 칸만 낸다 (넘기지 않은 칸은 해당 없음)
        data: dict[str, Any] = handler(self)
        return drop_unset_fields(self, data, data.keys() - {'step'})


class DabangSalePyeong(BaseModel):
    """분양 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="평형 ('55A')")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description="분양가 (만원, 대표값). 임대 공급(단지 price_kind '임대가')이면 키가 없고 deposit_manwon 이다")
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description="임대 보증금 (만원, 대표값, 단지 price_kind '임대가'). 분양가면 키가 없다")
    ] = None

    @model_serializer(mode='wrap')
    def keep_given_amounts(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return drop_unset_fields(self, handler(self), GIVEN_AMOUNT_FIELDS)


class DabangSubscriptionPyeong(BaseModel):
    """청약 결과의 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="평형 ('59A')")
    ] = None
    presale_household_count: Annotated[
        int | None,
        Field(description="이 평형의 분양 세대수 (다방 '분양/총세대' 의 앞 값)")
    ] = None
    competition_ratio: Annotated[
        float | None,
        Field(description="경쟁률 (5.52 = '5.52:1'). 다방 표시가 숫자가 아니면 null")
    ] = None
    winning_point: Annotated[
        int | None,
        Field(description='당첨가점 (점). 다방 표시가 숫자가 아니면 null')
    ] = None


class DabangSubscriptionResult(BaseModel):
    """청약 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    lowest_winning_point: Annotated[
        int | None,
        Field(description="최저 당첨가점 (점, 다방 '당첨가점(커트라인)')")
    ] = None
    highest_competition_ratio: Annotated[
        float | None,
        Field(description="최고 경쟁률 (5.52 = '5.52:1')")
    ] = None
    pyeongs: Annotated[
        list[DabangSubscriptionPyeong] | None,
        Field(description='평형별 경쟁률·당첨가점. 다방이 평형별 결과를 주지 않으면 null (모름, 없다는 뜻이 아니다)')
    ] = None


class DabangSaleDetail(Result):
    """분양 단지 정보. 상담 전화·사진·좌표는 내보내지 않는다.

    `notes`: 못 읽은 일정 날짜 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    presale_id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    status: Annotated[
        str | None,
        Field(description='분양 상태')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    presale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    building_floor: Annotated[
        int | None,
        Field(description='지상 층수')
    ] = None
    basement_floor: Annotated[
        int | None,
        Field(description='지하 층수')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    developer: Annotated[
        str | None,
        Field(description='시행사')
    ] = None
    price_kind: Annotated[
        str,
        Field(description="가격이 무엇인지 ('분양가', 공공임대·민간임대는 '임대가'. 다방 화면 이름표. 임대가는 임대 보증금이다)")
    ]
    price_range: Annotated[
        AmountRange | None,
        Field(description='가격 범위 (만원). 두 끝 안은 분양가면 price_manwon, 임대가(공공·민간임대)면 deposit_manwon(임대 보증금). 최저·최고를 모두 모르면 null')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당가 (만원/3.3㎡, price_kind 기준. 임대가면 보증금 평당가)')
    ] = None
    region_price_per_pyeong_average_manwon: Annotated[
        float | None,
        Field(description='최근 6개월 이 지역 평균 평당가 (만원/3.3㎡, 다방 표시). 다방이 주지 않으면 null')
    ] = None
    move_in: Annotated[
        str | None,
        Field(description='입주 예정 (YYYY-MM, 날까지 주면 YYYY-MM-DD). 날짜로 읽지 못하면 null 이고 notes 의 [참고] 가 원래 글자를 알린다')
    ] = None
    regulation_area: Annotated[
        str | None,
        Field(description='규제 지역. 모르면 null')
    ] = None
    price_cap: Annotated[
        bool | None,
        Field(description='분양가 상한제. 모르면 null')
    ] = None
    resalable: Annotated[
        bool | None,
        Field(description='전매 가능. 모르면 null')
    ] = None
    schedules: Annotated[
        list[DabangSaleStep],
        Field(description='일정 (모집공고부터 입주까지)')
    ]
    pyeongs: Annotated[
        list[DabangSalePyeong],
        Field(description='평형별 분양가(임대가)·세대수')
    ]
    subscription_result: Annotated[
        DabangSubscriptionResult | None,
        Field(description='청약 결과 (최저 당첨가점·최고 경쟁률·평형별 값). 청약 전이거나 다방에 결과가 없으면 null')
    ] = None
    notice_url: Annotated[
        str | None,
        Field(description='입주자 모집공고 파일 주소')
    ] = None
    applyhome_url: Annotated[
        str | None,
        Field(description='청약홈 주소')
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]
