"""`info.py` 의 결과 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    NumberRange,
    Result,
)
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice
from jibsa.providers.zigbang.service.complex.constants import (
    APT_ONLY_COMPLEX_FIELDS,
    OFFICETEL_ONLY_COMPLEX_FIELDS,
)
from jibsa.providers.zigbang.service.complex.models.common import ZigbangRelatedComplex

from typing import (
    Annotated,
    Any,
)


class ZigbangComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (zigbang complex·items 에 넘긴다)')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='단지가 있는 동까지의 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None


class ZigbangPyeong(BaseModel):
    """아파트 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (zigbang search listings --complex --pyeong 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 ㎡ 기준, 예: 111A)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 평 기준, 예: 34A)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 직방 평형 정보를 받지 못했거나 그 평형이 없으면 모름(null)')
    ] = None
    supply_area_pyeong: Annotated[
        float | None,
        Field(description='공급면적 (평). 직방이 준 값 그대로')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평). 직방이 준 값 그대로')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='그 평형의 세대수 (웹 평형 이름 옆 괄호, 예: 107A㎡ (731세대))')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    entrance: Annotated[
        str | None,
        Field(description="현관 구조 (직방 글자 그대로, 예: '계단식'·'복도식'). 직방이 주지 않으면 null")
    ] = None
    manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='평균 월 관리비 (만원, 직방 정수 그대로). 웹 안내: K-apt 최소 3개월~최대 24개월 평균. 0 이거나 직방이 주지 않으면 null (웹은 이때 관리비 줄을 숨긴다)')
    ] = None
    summer_manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='여름(6~8월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    winter_manage_cost_manwon: Annotated[
        int | float | None,
        Field(description='겨울(12~2월) 월 관리비 (만원). 0 이거나 직방이 주지 않으면 null (웹은 이때 -)')
    ] = None
    resale_available_date: Annotated[
        str | None,
        Field(description='전매제한이 풀려 매매할 수 있는 날 (직방 거래가능시점, YYYY-MM-DD). 이미 지난 날도 그대로 낸다 (웹은 오늘 뒤일 때만 안내). 직방이 주지 않으면 null')
    ] = None
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description=(
            "직방시세 (실거래를 머신러닝으로 분석한 직방 추정값이고 실거래 평균이 아니다). 늘 'sale'·'jeonse' 두 키이고, sale 은 price_manwon"
            '(직방 시세 범위의 최저값. 2026-11-19 표본 30개 평형은 최저 = 최고)·price_per_pyeong_manwon, jeonse 는 deposit_manwon·'
            'price_per_pyeong_manwon (만원, 평당가는 3.3㎡당 공급면적 평 기준). 그 거래의 안 칸이 모두 0 이거나 없으면 그 거래가 null (웹 시세없음), 일부만 그러면 그 칸만 null'
        ))
    ]


class ZigbangComplexRank(BaseModel):
    """단지 순위. 직방 웹 단지 화면의 '<동>에서 이 단지의 랭킹은?' 절."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='웹 제목 속 동 이름 (예: 가락동)')
    ]
    price_rank: Annotated[
        int | None,
        Field(description="웹 '시세 N위' 의 N (직방은 실거래가 순위로 준다). 순위 없음이면 null")
    ]
    popularity_rank: Annotated[
        int | None,
        Field(description="웹 '인기순 N위' 의 N (직방은 조회수 순위로 준다). 순위 없음이면 null")
    ]


class ZigbangLandTradePermitDay(BaseModel):
    """토지거래허가 일별 건수 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str | None,
        Field(description='날짜 (YYYY-MM-DD). 직방이 준 날짜를 읽지 못하면 모름(null, [참고] 안내)')
    ]
    count: Annotated[
        int | None,
        Field(description='그날의 토지거래허가 건수. 직방이 주지 않으면 모름(null)')
    ]


class ZigbangComplex(Result):
    """직방 단지 정보. 아파트와 오피스텔 건물은 직방이 주는 정보가 달라 한쪽에만 있는 필드는 키를 뺀다.

    `notes`: 후기가 있다는 안내와, 학군·평형 정보를 받지 못해 그 값을 모른다는 [실패] 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    complex_type: Annotated[
        str,
        Field(description='아파트 또는 오피스텔')
    ]
    address: Annotated[
        str | None,
        Field(description='지번 주소 (오피스텔은 동까지)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 층수 범위. 직방은 최고 층수만 주어 lowest 는 늘 null(모름)이고 highest 가 최고 층수다 (오피스텔은 건물 층수). 직방이 최고 층수를 주지 않으면 null')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수 (아파트만)')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 아파트만)')
    ] = None
    completed_month: Annotated[
        str | None,
        Field(description='준공 연월 (YYYY-MM, 오피스텔만). 읽지 못하면 null ([참고] 안내)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사 (아파트만)')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수 (아파트만)')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%, 아파트만)')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식 (아파트만)')
    ] = None
    has_elevator: Annotated[
        bool | None,
        Field(description='엘리베이터 (오피스텔만). 있다고 확인되면 true, 그 밖에는 모름(null). 매물 상세의 has_elevator 가 정확하다')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='지금 올라온 매물 수. 아파트는 같은 호·거래 유형을 묶은 수. 직방이 주지 않으면 모름(null)')
    ]
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='거래 유형별 매물 수 (아파트만). 직방이 주지 않은 유형은 모름(null)')
    ] = {}
    pyeongs: Annotated[
        list[ZigbangPyeong] | None,
        Field(description='평형 목록 (아파트만). 평형이 아직 없는 단지는 [], 직방이 평형 목록을 주지 않았으면 null')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 학교군 안 가까운 중·고등학교 2곳씩 (아파트만, 예: 서울개원초등학교 (배정, 180m)). 모르면 null')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수 (아파트만). 후기 내용은 url 의 직방 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    estimated_ranges: Annotated[
        dict[str, AmountRange | None],
        Field(description=(
            "단지 직방시세 범위 (아파트만). 'sale' 키 하나이고 lowest·highest 는 price_manwon (만원). 웹 전체 탭 \"매매 18억 8,000 ~ 61억 1,000\" 의 앞·뒤. "
            '직방 추정값이고 실거래 평균이 아니다. 평형 정보를 받지 못했거나 두 끝이 모두 0 이거나 없으면 "sale": null, 한 끝만 그러면 그 price_manwon 만 null'
        ))
    ] = {}
    estimated_prices: Annotated[
        dict[str, ZigbangEstimatedPrice | None],
        Field(description=(
            "단지 평균 직방시세의 평당 가격 (아파트만, 만원/3.3㎡). 늘 'sale'·'jeonse' 두 키이고 안은 price_per_pyeong_manwon. "
            '웹 전체 탭 "평균 1억 235/3.3㎡". 0 이거나 없으면 그 거래가 null'
        ))
    ] = {}
    ranking: Annotated[
        ZigbangComplexRank | None,
        Field(description="단지 순위 (아파트만, 웹 '<동>에서 이 단지의 랭킹은?'). 직방이 구·동 순위를 주지 않으면 웹이 절을 숨기므로 null")
    ] = None
    related_complexes: Annotated[
        list[ZigbangRelatedComplex] | None,
        Field(description="웹 '함께 보면 좋은 단지' (아파트만, 직방이 준 순서). 직방이 주지 않으면 모름(null), 없으면 []")
    ] = None
    land_trade_permits: Annotated[
        list[ZigbangLandTradePermitDay] | None,
        Field(description="최근 7일 토지거래허가 일별 건수 (아파트만, 직방이 준 순서). 웹 '토지거래허가 총 N건 (최근 7일)' 과 날짜별 그래프. 직방이 주지 않으면 모름(null)")
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = OFFICETEL_ONLY_COMPLEX_FIELDS if self.complex_type == '아파트' else APT_ONLY_COMPLEX_FIELDS
        for field in fields:
            data.pop(field, None)
        return data
