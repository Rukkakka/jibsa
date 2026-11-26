"""단지·평형별 실거래가의 결과·조건 모델 (docs/development/provider-conventions.md '모듈 구성')."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    Result,
    with_floor_number,
)
from jibsa.core.schema import drop_unset_fields

from typing import (
    Annotated,
    Any,
)


class NaverRealPrice(BaseModel):
    """실거래 한 건 (만원). 거래 유형에 없는 가격 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 가격 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    floor: Annotated[
        str | None,
        Field(description="층 ('3'·'지하1'). 바로 뒤의 floor_number 는 층 숫자 (지하는 음수)")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    deal_type: Annotated[
        str | None,
        Field(description='중개거래 / 직거래')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신 계약 (아파트 실거래). 빌라 실거래는 이 키가 없고 renewal_right 를 준다')
    ] = None
    renewal_right: Annotated[
        bool | None,
        Field(description='계약갱신요구권을 쓴 갱신 거래면 true, 아니면 null (합의로 갱신했는지는 모른다). 빌라 실거래만')
    ] = None
    prev_deposit_manwon: Annotated[
        float | None,
        Field(description='갱신 계약의 종전 보증금 (만원)')
    ] = None
    prev_rent_manwon: Annotated[
        float | None,
        Field(description='갱신 계약의 종전 월세 (만원). 월세·단기임대 갱신 거래만')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 아파트는 갱신 계약(renewal), 빌라는 계약갱신요구권 사용(renewal_right)만 준다. 넣지 않은 쪽은 해당 없음이다
        data = drop_unset_fields(self, handler(self), ('renewal', 'renewal_right'))
        _drop_trade_type_fields(data, self.trade_type)
        # 종전 보증금·월세는 갱신 계약에만 있다 (갱신이 아니거나 모르면 해당 없음)
        # 둘 다 0 이거나 없으면 웹은 '기존 …' 을 그리지 않는다 (빌라 실거래 표 `alreadyDeposit || alreadyMonthlyDeposit`, 2026-11-18
        # 번들 청크 1un70f33iojlw). '종전 0원' 으로 읽히지 않게 두 키를 지운다 (2026-11-18 사용자 결정, 아파트도 같은 규칙)
        no_previous = not (self.prev_deposit_manwon or self.prev_rent_manwon)
        # 리뷰 오탐 (2026-11-17): isRenew 가 null 이면 종전 금액을 지우는 것은 웹과 같다 (웹도 isRenew 가 참일 때만 '기존 …' 을 그린다)
        # 전세 행은 종전 월세도 없다 (웹 실거래 행의 '기존 …' 은 getPriceLabel 로 그려 전세면 보증금만, 월세·단기임대일 때만
        # '보증금/월세' 를 그린다, 2026-11-17 번들 확인). 전세 갱신은 종전 월세로 대부분 0 이 오므로 rent_manwon 처럼 뺀다
        for field in ('prev_deposit_manwon', 'prev_rent_manwon'):
            if field == 'prev_rent_manwon' and 'rent_manwon' in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
                data.pop(field, None)
            elif self.trade_type == '매매' or not (self.renewal or self.renewal_right) or no_previous:
                data.pop(field, None)
        return with_floor_number(data)


class NaverRealPricePyeongGroup(BaseModel):
    """실거래를 묶어 받은 평형 묶음 (대표 평수 하나, 예: 33평 묶음에 61A·61B)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='묶음 이름 (대표 평수, 예: 33평)')
    ] = None
    pyeong_ids: Annotated[
        list[int],
        Field(description='묶음에 든 평형 번호 (번호순). 이 평형들의 거래가 trades 에 섞여 있다')
    ] = []


class NaverRealPricePerPyeong(BaseModel):
    """빌라 단지 평당 실거래가 한 건. 신고된 거래의 평당가라 `complex --pyeong` 의 호가 평당가(`asking_price_per_pyeong`)와 다르다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당 실거래가 (만원/평). 값이 없으면 null')
    ]


class NaverNearbyTrade(BaseModel):
    """주변 실거래 한 건 (만원). 거래 유형에 없는 가격 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 가격 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 날짜로 읽지 못하면 null ([참고] 안내)')
    ]
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ]
    completed_year: Annotated[
        int | None,
        Field(description='준공 연도. 준공 연월을 읽지 못하면 null')
    ]
    floor: Annotated[
        str | None,
        Field(description="층 (네이버가 준 글자를 매물과 같은 글자로 맞춤: '3'·'지하1'). 비어 있거나 '-' 면 null. 바로 뒤의 floor_number 는 층 숫자 (몇 층인지 모르는 표기는 null)")
    ]
    price_manwon: Annotated[
        float | None,
        Field(description='매매가 (만원)')
    ] = None
    deposit_manwon: Annotated[
        float | None,
        Field(description='보증금 (만원)')
    ] = None
    rent_manwon: Annotated[
        float | None,
        Field(description='월세 (만원)')
    ] = None
    renewal_right: Annotated[
        bool | None,
        Field(description='계약갱신요구권을 쓴 갱신 거래면 true, 아니면 null (합의로 갱신했는지는 모른다). 전월세만')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='이 거래가 난 건물과 이 단지 사이의 직선거리 (m). 건물 좌표를 주지 않으면 null')
    ]
    same_complex: Annotated[
        bool | None,
        Field(description=(
            '이 거래가 난 건물이 이 단지인지. 네이버가 건물 번호·이름을 주지 않아 좌표가 같은지로만 가린다 '
            '(반올림한 거리 distance_m 이 0 이면 true). 건물 좌표를 주지 않으면 null'
        ))
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        _drop_trade_type_fields(data, self.trade_type)
        return with_floor_number(data)


class NaverNearbyTransactions(BaseModel):
    """빌라 단지 둘레의 주변 실거래 (네이버 웹 빌라 실거래 탭의 '주변 실거래가')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    height_km: Annotated[
        float,
        Field(description='찾은 범위의 남북 길이 (km). --around-km 을 주지 않으면 네이버 웹 작은 지도 크기이고, 주면 그 반경을 감싼 정사각형이다. 단지 좌표가 가운데다')
    ]
    width_km: Annotated[
        float,
        Field(description='찾은 범위의 동서 길이 (km)')
    ]
    trades: Annotated[
        list[NaverNearbyTrade],
        Field(description=(
            '범위 안 거래. 네이버가 10건까지만 주고 계약일 → 준공연도 → 전용면적이 큰 순이다 (네이버 웹 표와 같다). '
            '--pyeong 평형과 비슷한 면적의 거래도 함께 오니 area_m2 로 가린다. 단지 이름은 오지 않는다. 범위에 거래가 없으면 []'
        ))
    ]


class NaverRealPriceResult(Result):
    """평형별 실거래 내역.

    `notes`: 기간 안 거래를 다 받지 못했다는 안내 등. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_id: Annotated[
        int,
        Field(description='평형 번호')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    period: Annotated[
        str | None,
        Field(description='--period 로 준 기간 (3개월, 1년, 3년, 5년). 주지 않았으면 키가 없다')
    ] = None
    start_date: Annotated[
        str | None,
        Field(description='기간 시작일 (YYYY-MM-DD). --period 를 주지 않았으면 키가 없다')
    ] = None
    pyeong_group: Annotated[
        NaverRealPricePyeongGroup | None,
        Field(description='--group 으로 받은 평형 묶음. --group 을 주지 않았으면 키가 없다')
    ] = None
    trades: Annotated[
        list[NaverRealPrice],
        Field(description='최근 순 실거래. --group 이면 묶음에 든 모든 평형의 거래가 섞여 있고 거래마다 어느 평형인지 알 수 없다')
    ]
    price_per_pyeong_trades: Annotated[
        list[NaverRealPricePerPyeong] | None,
        Field(description=(
            '최근 5년(--period·--pages 와 상관없이) 이 평형의 평당 실거래가 (만원/평, 서버 순서). 빌라 단지의 매매·전세만 키가 있다 '
            '(아파트·월세는 키가 없다). 거래가 없으면 [], 조회가 실패하면 null. 호가 평당가(complex 의 asking_price_per_pyeong)가 아니라 신고된 거래의 평당가다'
        ))
    ] = None
    nearby_trades: Annotated[
        NaverNearbyTransactions | None,
        Field(description='단지 둘레 범위 안 주변 실거래. 빌라 단지만 키가 있다 (아파트는 키가 없다). 단지 좌표를 모르거나 조회가 실패하면 null')
    ] = None

    # 빌라 단지의 평당 실거래가를 물었는지(매매·전세). 아니면(아파트·월세) price_per_pyeong_trades 는 해당 없음이라 키를 뺀다
    _price_per_pyeong_scoped: bool = PrivateAttr(default=False)
    # 빌라 단지의 주변 실거래를 물었는지. 아니면(아파트) nearby_trades 는 해당 없음이라 키를 뺀다
    _nearby_scoped: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.period is None:
            data.pop('period', None)
            data.pop('start_date', None)
        if self.pyeong_group is None:
            data.pop('pyeong_group', None)
        # 두 칸은 빌라 단지에만 있다 (웹 빌라 실거래 탭). 조회 실패는 null 이고 해당 없음은 키를 뺀다
        if not self._price_per_pyeong_scoped:
            data.pop('price_per_pyeong_trades', None)
        if not self._nearby_scoped:
            data.pop('nearby_trades', None)
        return data


def _drop_trade_type_fields(data: dict[str, Any], trade_type: str) -> None:
    """출력 dict 에서 거래 유형에 없는 가격 필드와 (매매의) 갱신 키를 뺀다. 실거래 행과 주변 실거래 행이 같은 규칙을 쓴다."""
    for field in NOT_APPLICABLE_PRICE_FIELDS.get(trade_type, frozenset()):
        data.pop(field, None)
    # 갱신 계약은 전월세에만 있다
    if trade_type == '매매':
        data.pop('renewal', None)
        data.pop('renewal_right', None)
