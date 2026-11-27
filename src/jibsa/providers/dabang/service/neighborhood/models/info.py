"""`info.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountSet,
    Result,
)
from jibsa.providers.dabang.service.common.models import (
    DabangPlace,
)
from jibsa.providers.dabang.service.neighborhood.constants import FIELD_BY_TOPIC

from typing import (
    Annotated,
    Any,
)


class DabangRank(BaseModel):
    """동네정보 순위 (작을수록 높다)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    national_rank: Annotated[
        int | None,
        Field(description='전국 순위')
    ] = None
    sido_rank: Annotated[
        int | None,
        Field(description='시·도 안 순위')
    ] = None
    sido: Annotated[
        str | None,
        Field(description="시·도 ('서울')")
    ] = None
    sigungu_rank: Annotated[
        int | None,
        Field(description='시·군·구 안 순위')
    ] = None
    sigungu: Annotated[
        str | None,
        Field(description="시·군·구 ('강남구')")
    ] = None


class DabangTypeCount(BaseModel):
    """매물 유형 하나의 수와 거래 유형별 나눔."""

    model_config = ConfigDict(
        extra='forbid',
    )

    property_type: Annotated[
        str,
        Field(description='매물 유형 (주택/빌라, 오피스텔, 아파트)')
    ]
    count: Annotated[
        int | None,
        Field(description='수')
    ] = None
    counts: Annotated[
        dict[str, int | None],
        Field(description="거래별 수. 키는 'sale'·'jeonse'·'wolse' 늘 세 개 (다방이 주지 않은 수는 null). 매물 수(listings)나 거래 수(trades)다")
    ]


class DabangCountStats(BaseModel):
    """매물 수 또는 거래량."""

    model_config = ConfigDict(
        extra='forbid',
    )

    count: Annotated[
        int | None,
        Field(description='합계')
    ] = None
    by_type: Annotated[
        list[DabangTypeCount],
        Field(description='매물 유형별')
    ]
    ranking: Annotated[
        DabangRank | None,
        Field(description='합계 순위')
    ] = None


class DabangTypePrice(BaseModel):
    """매물 유형 하나의 평균가 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_type: Annotated[
        str,
        Field(description='단지 유형 (아파트, 오피스텔)')
    ]
    trade_averages: Annotated[
        dict[str, AmountSet | None],
        Field(description="거래별 평균가 (만원). 키는 'sale'(price_manwon)·'jeonse'(deposit_manwon) 늘 두 개이고, 다방이 평균을 주지 않으면 그 거래가 null")
    ]


class DabangPriceStats(BaseModel):
    """시세정보 평균가."""

    model_config = ConfigDict(
        extra='forbid',
    )

    by_type: Annotated[
        list[DabangTypePrice],
        Field(description='단지 유형별 평균가')
    ]
    ranking: Annotated[
        DabangRank | None,
        Field(description="아파트 평균 매매가 순위 (다방 화면 '아파트/매매 기준'. 오피스텔·전세가는 순위에 들지 않는다)")
    ] = None


class DabangAgeGroup(BaseModel):
    """연령대 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    age: Annotated[
        str,
        Field(description="연령대 ('20대', '10대 이하', '60대 이상')")
    ]
    count: Annotated[
        int | None,
        Field(description='인구')
    ] = None
    percent: Annotated[
        float | None,
        Field(description='비율 (%)')
    ] = None


class DabangPopulation(BaseModel):
    """인구."""

    model_config = ConfigDict(
        extra='forbid',
    )

    population: Annotated[
        int | None,
        Field(description='인구')
    ] = None
    male: Annotated[
        int | None,
        Field(description='남성')
    ] = None
    female: Annotated[
        int | None,
        Field(description='여성')
    ] = None
    ages: Annotated[
        list[DabangAgeGroup],
        Field(description='연령대별')
    ]
    ranking: Annotated[
        DabangRank | None,
        Field(description='인구 순위')
    ] = None


class DabangCategoryRank(BaseModel):
    """학교·편의·교통·안전 탭 종류 하나의 합계·구성과 순위 (웹 요약 칸, `--ranks`)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    topic: Annotated[
        str,
        Field(description="주제 ('학교', '편의', '교통', '안전')")
    ]
    type: Annotated[
        str,
        Field(description="종류 (다방 요약 칸 이름표: '어린이집', '생활 편의시설', '교통시설', '안전시설' 등)")
    ]
    count: Annotated[
        int | None,
        Field(description='그 종류의 합계 (시설·학교 수)')
    ] = None
    counts: Annotated[
        dict[str, int | None] | None,
        Field(description="구성 ({'편의점': 204, '세탁소': 62}, 어린이집은 설립 구분 {'공공': 3})")
    ] = None
    ranking: Annotated[
        DabangRank | None,
        Field(description='합계 순위 (전국·시도·구)')
    ] = None


class DabangNeighborhood(Result):
    """다방 동네정보 요약. 고르지 않은 주제는 키가 없다.

    `notes`: 빈 항목 안내
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DabangPlace,
        Field(description='동')
    ]
    base_month: Annotated[
        str | None,
        Field(description='다방 동네정보 기준 달 (YYYY-MM)')
    ] = None
    listings: Annotated[
        DabangCountStats | None,
        Field(description='지금 올라온 다방 매물 수 (매물 유형·거래 유형별)')
    ] = None
    trades: Annotated[
        DabangCountStats | None,
        Field(description='거래량 (국토교통부 신고 기준, 다방 집계, 매물 유형·거래 유형별)')
    ] = None
    prices: Annotated[
        DabangPriceStats | None,
        Field(description='아파트·오피스텔 평균 매매가·전세가 (국토교통부 실거래 기준, 다방 집계)')
    ] = None
    population: Annotated[
        DabangPopulation | None,
        Field(description='인구·성별·연령대 (행정안전부)')
    ] = None
    schools: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="학교 종류별 설립 구분 수와 학원 종류별 수 ({'초등학교': {'국공립': 2}, '학원': {'예체능': 92}})")
    ] = None
    amenities: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="편의시설 묶음별 시설 수 ({'생활편의시설': {'편의점': 204}})")
    ] = None
    transport: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="교통·차량 시설 수 ({'교통시설': {'지하철': 5, '버스': 73}})")
    ] = None
    safety: Annotated[
        dict[str, dict[str, int | None]] | None,
        Field(description="생활안전 시설 수 ({'안전시설': {'CCTV': 1074}})")
    ] = None
    ranks: Annotated[
        list[DabangCategoryRank],
        Field(description='학교·편의·교통·안전 종류마다 합계·구성과 전국·시도·구 순위 (--ranks 일 때만)')
    ] = []
    topics: Annotated[
        list[str],
        Field(exclude=True, description='고른 주제')
    ] = []
    with_ranks: Annotated[
        bool,
        Field(exclude=True, description='--ranks 를 줬는지')
    ] = False

    @model_serializer(mode='wrap')
    def drop_unrequested(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for topic, field in FIELD_BY_TOPIC.items():
            if topic not in self.topics:
                data.pop(field, None)
        if not self.with_ranks:
            data.pop('ranks', None)
        return data
