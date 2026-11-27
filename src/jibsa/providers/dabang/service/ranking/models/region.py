"""`region.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import Result
from jibsa.providers.dabang.service.region.models import DabangScope

from typing import (
    Annotated,
    Any,
)


class DabangRegionRankingEntry(BaseModel):
    """범위 안 순위 한 칸. 값 필드는 항목에 맞는 것만 있다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[
        int,
        Field(description='순위')
    ]
    name: Annotated[
        str | None,
        Field(description='동 이름 또는 단지 이름')
    ] = None
    area: Annotated[
        str | None,
        Field(description="상위 지역 ('서울 강남구', 단지는 동까지)")
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (단지 순위)')
    ] = None
    value_text: Annotated[
        str | None,
        Field(description=(
            "다방 표시 값 ('61.1억', '27개', '133.3%', '44년 6개월', '19점', 인구증감 '327명 (-0.6%)', 거래증감·매물증감 "
            "'73개 (+101.4%)')"
        ))
    ] = None
    value_manwon: Annotated[
        float | None,
        Field(description='금액 (만원, 평균가·평당가·갭가격)')
    ] = None
    count: Annotated[
        int | None,
        Field(description=(
            '수 (거래량·매물수·세대수, 학교·학원·시설 수, 인구. 인구증감은 올해 인구, 거래증감·매물증감은 지금 거래·매물 수)'
        ))
    ] = None
    prev_count: Annotated[
        int | None,
        Field(description='견준 앞 수 (인구증감은 한 해 전 인구, 거래증감·매물증감은 comparison 기준의 앞 거래·매물 수)')
    ] = None
    change_count: Annotated[
        int | None,
        Field(description='변화 수 (count - prev_count, 줄면 음수. 인구증감·거래증감·매물증감)')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='비율 (%, 전세가율·진학률)')
    ] = None
    score: Annotated[
        int | None,
        Field(description='다방 선호도 점수 (조회수·찜수·문의수 등을 합친 점수)')
    ] = None
    change_manwon: Annotated[
        float | None,
        Field(description='금액 변화 (만원, 시세증감·최고가증감. 현재가가 아니다)')
    ] = None
    change_percent: Annotated[
        float | None,
        Field(description="변화율 (%, 시세증감·최고가증감·인구증감·거래증감·매물증감. 다방은 앞 수가 0 이면 '0%' 로 준다)")
    ] = None
    prev_price_manwon: Annotated[
        float | None,
        Field(description='비교 기준 금액 (만원, 시세증감은 앞 시세, 최고가증감은 앞 최고가)')
    ] = None
    prev_price_month: Annotated[
        str | None,
        Field(description="앞 최고가 달 (최고가증감, '2023-10'). 다방 글자를 읽지 못하면 null")
    ] = None
    age_years: Annotated[
        int | None,
        Field(description='연식 (년, 연식)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description="평형 이름 ('93평', 단지)")
    ] = None
    price_month: Annotated[
        str | None,
        Field(description="금액 기준 달 ('2026-05', 최고가증감 단지는 새 최고가 달). 다방 글자를 읽지 못하면 null")
    ] = None
    price_detail: Annotated[
        str | None,
        Field(description="금액 설명 ('매매 90억 / 전세 14.5억')")
    ] = None

    # 이 순위 결과에 해당하는 칸 (`get_region_ranking` 이 채운다). 해당하는데 값이 없으면 null(모름)로 둔다
    _applicable: frozenset[str] = PrivateAttr(default=frozenset({'rank', 'name'}))

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {key: value for key, value in data.items() if value is not None or key in self._applicable}


class DabangRegionRanking(Result):
    """범위 안 동·단지 순위.

    `notes`: 일부 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        DabangScope,
        Field(description='범위')
    ]
    unit: Annotated[
        str,
        Field(description='동 / 단지')
    ]
    metric: Annotated[
        str,
        Field(description='항목')
    ]
    tab: Annotated[
        str,
        Field(description=(
            "다방 동네정보의 어느 탭 랭킹인지 ('시세정보' 아파트·오피스텔 단지 기준, '매물정보' 주택/빌라를 포함한 매물 유형 기준, "
            "'학군'·'인구수'·'편의시설'·'교통/차량'·'생활안전'). 매물수·거래량·선호도는 '시세정보'·'매물정보' 두 탭에 있고 값이 다르다"
        ))
    ]
    complex_type: Annotated[
        str | None,
        Field(description=(
            "어느 단지 유형의 순위인지 ('아파트', '오피스텔', 합산이면 '아파트·오피스텔 합산'). 단지 유형을 받지 않는 항목"
            "(세대수·연식·동네정보)과 '매물정보' 탭 순위는 키 없음"
        ))
    ] = None
    property_type: Annotated[
        str | None,
        Field(description=(
            "'매물정보' 탭 순위의 매물 유형 ('주택/빌라', 여럿이면 '주택/빌라·아파트 합산'). 다른 탭은 키 없음"
        ))
    ] = None
    kind: Annotated[
        str | None,
        Field(description='--kind 로 고른 종류 (학원·학교·시설). 학원은 주지 않으면 입시')
    ] = None
    comparison: Annotated[
        str | None,
        Field(description=(
            "증감을 무엇과 견줬는지 (다방 화면 문구: 거래증감 '전월대비', 매물증감 '최근 30일 전 대비'). 다른 항목은 키 없음"
        ))
    ] = None
    base_month: Annotated[
        str | None,
        Field(description='다방이 센 기준 달 (YYYY-MM, 시세증감·최고가증감 동 순위)')
    ] = None
    total: Annotated[
        int | None,
        Field(description='범위 안 순위가 있는 동·단지 수')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 순위 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='순위가 더 있는지')
    ] = False
    rankings: Annotated[
        list[DabangRegionRankingEntry],
        Field(description='순위')
    ]
    # 다방이 기준 달 글자를 줬는데 읽지 못해 base_month 가 null 이면 모름이라 키를 지우지 않는다 ([참고] 로 알린다)
    _base_month_unread: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('complex_type', 'property_type', 'kind', 'comparison', 'base_month'):
            if data.get(key) is None and not (key == 'base_month' and self._base_month_unread):
                data.pop(key, None)
        return data
