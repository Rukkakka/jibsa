"""`complex.py` 의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    Result,
)
from jibsa.providers.naver.service.common.constants import (
    ASKING_RANGES_DESCRIPTION,
)
from jibsa.providers.naver.service.common.models import (
    NaverAssignedSchool,
)
from jibsa.providers.naver.service.complex.constants import PYEONG_SCOPED_FIELDS
from jibsa.providers.naver.service.complex.models.common import (
    NaverComplexMaintenanceFee,
    NaverMarketPrice,
    NaverPricePerPyeong,
    NaverRealPriceSummary,
)

from typing import (
    Annotated,
    Any,
)


class NaverPyeong(BaseModel):
    """평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong_id: Annotated[
        int,
        Field(description='평형 ID (real-price 의 --pyeong)')
    ]
    name: Annotated[
        str,
        Field(description='평형 이름 (공급면적 ㎡)')
    ]
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 전용+주거공용이라 평형 이름보다 작다. 오피스텔인데 계약면적과 같게 오면 공급 칸에 계약면적이 채워진 것이라 null')
    ] = None
    contract_area_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡). 오피스텔은 평형 이름·매물 상세의 공급면적이 이 값이다')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None


class NaverPyeongGroup(BaseModel):
    """평형 묶음 하나. 네이버는 평형이 많은 단지를 대표 평수(33평 등)로 묶어 보여 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='묶음 이름 (대표 평수, 예: 33평)')
    ] = None
    representative_pyeong_id: Annotated[
        int | None,
        Field(description='대표 평형 ID (real-price 의 --pyeong). 묶음에 든 평형 ID 중 하나다')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='묶음의 세대수')
    ] = None
    pyeong_ids: Annotated[
        list[int] | None,
        Field(description='묶음에 든 평형 ID (번호순, pyeongs[].pyeong_id). 네이버가 이 묶음의 평형 목록을 주지 않으면 null (모름)')
    ] = None


class NaverReconstructionStep(BaseModel):
    """재건축 사업 단계 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    step: Annotated[
        str,
        Field(description='단계 이름 (예: 조합설립인가)')
    ]
    date: Annotated[
        str | None,
        Field(description='그 단계에 이른 날 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ] = None


class NaverReconstruction(BaseModel):
    """재건축 단지의 사업 진행."""

    model_config = ConfigDict(
        extra='forbid',
    )

    current_step: Annotated[
        str | None,
        Field(description='현재 단계')
    ] = None
    current_step_date: Annotated[
        str | None,
        Field(description='현재 단계에 이른 날 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='선정된 시공사')
    ] = None
    planned_household_count: Annotated[
        int | None,
        Field(description='재건축 후 계획 세대수')
    ] = None
    planned_floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='재건축 계획 용적률 (%)')
    ] = None
    steps: Annotated[
        list[NaverReconstructionStep],
        Field(description='지나온 단계 (날짜가 있는 단계만, 단계 순서)')
    ] = []


class NaverComplexSummary(Result):
    """단지 요약. 매물과 마찬가지로 좌표는 담지 않는다 (위치는 주소와 원 사이트로).

    `notes`: 평형 정보를 붙이지 못한 이유 등. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형')
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
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    listing_counts: Annotated[
        dict[str, int],
        Field(description='거래 유형별 매물 수')
    ] = {}
    asking_ranges: Annotated[
        dict[str, AmountRange] | None,
        Field(description=ASKING_RANGES_DESCRIPTION)
    ] = None
    pyeongs: Annotated[
        list[NaverPyeong],
        Field(description='평형 목록')
    ] = []
    pyeong_groups: Annotated[
        list[NaverPyeongGroup] | None,
        Field(description='평형 묶음 (대표 평수별 평형 번호). 빌라 단지는 키가 없고, 서버가 묶음을 주지 않으면 [], 조회 실패면 null. --pyeong 을 몇 개 주든 붙는다')
    ] = None
    pyeong_manage_cost: Annotated[
        NaverComplexMaintenanceFee | None,
        Field(description='--pyeong 평형의 월 관리비. 평형을 하나만 줄 때만 키가 있고, 자료가 없으면 null')
    ] = None
    estimated_prices: Annotated[
        list[NaverMarketPrice] | None,
        Field(description='--pyeong 평형의 기관별 최신 시세. 평형을 하나만 줄 때만 키가 있고, 시세가 없으면 []. 단지 유형을 몰라 시세를 묻지 않았거나 조회에 실패하면 null')
    ] = None
    trade_summary: Annotated[
        NaverRealPriceSummary | None,
        Field(description=(
            '--pyeong 평형의 최근 3년 매매·전세 실거래 요약. 평형을 하나만 줄 때만 키가 있다. 그 거래 유형의 3년 거래가 없으면 5년으로 '
            '요약하고 그 유형에 start_date 가 붙는다. 3개월 평균 recent_3m_average_manwon 은 5년으로 요약했으면 null 이다. 조회가 실패한 유형은 null'
        ))
    ] = None
    asking_price_per_pyeong: Annotated[
        dict[str, NaverPricePerPyeong | None] | None,
        Field(description=(
            '--pyeong 평형의 평당 호가(만원/평)와 같은 동·구·시 평균 비교. {sale: …, jeonse: …}. 공급 평수 기준, 네이버 매물 호가 기준 '
            '주간값(매주 월요일 갱신)이다. 평형을 하나만 줄 때, 아파트·오피스텔·재건축·분양권 단지만 키가 있다(빌라 등 다른 단지는 키가 없고, '
            '단지 유형을 모르면 null). 네이버가 평당가를 주지 않는 거래 유형은 그 키가 없고(둘 다 없으면 {}), 조회가 실패한 유형은 null'
        ))
    ] = None
    schools: Annotated[
        list[NaverAssignedSchool] | None,
        Field(description='배정 초등학교. 조회 실패면 null')
    ] = None
    reconstruction: Annotated[
        NaverReconstruction | None,
        Field(description='재건축 사업 진행. 재건축 단지만 키가 있고, 조회 실패면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]

    # --pyeong 을 하나만 줘서 평형 정보(관리비·시세·실거래 요약·평당가)를 조회했는지. 아니면 그 키는 해당 없음이라 뺀다
    _pyeong_scoped: bool = PrivateAttr(default=False)
    # 재건축 단지인지. 아니면 reconstruction 은 해당 없음이라 뺀다
    _reconstruction_scoped: bool = PrivateAttr(default=False)
    # 평당가를 묻는 단지 유형이거나 유형을 모르는지 (`pyeong_details` 가 키를 넣었는지). 아니면(빌라 등) asking_price_per_pyeong 은 해당 없음이라 뺀다
    _price_per_pyeong_scoped: bool = PrivateAttr(default=False)
    # 평형 묶음을 조회했는지. 빌라 단지는 웹도 묻지 않아 pyeong_groups 는 해당 없음이라 뺀다
    _pyeong_groups_scoped: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self._pyeong_scoped:
            for field in PYEONG_SCOPED_FIELDS:
                data.pop(field, None)
        # 평당가를 주지 않는 단지 유형(빌라 등)은 해당 없음이라 키를 뺀다. 단지 유형을 모르면 키는 있고 null(모름)이다 (시세 `estimated_prices` 와 같다).
        # 조회 실패는 거래 유형 안의 null 이다
        if not self._price_per_pyeong_scoped:
            data.pop('asking_price_per_pyeong', None)
        if not self._reconstruction_scoped:
            data.pop('reconstruction', None)
        if not self._pyeong_groups_scoped:
            data.pop('pyeong_groups', None)
        return data
