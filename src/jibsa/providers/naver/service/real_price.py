"""단지·평형별 실거래가 (real-price)."""

from datetime import date
from math import (
    atan,
    cos,
    degrees,
    exp,
    log,
    pi,
    radians,
    tan,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    KM_PER_LAT_DEGREE,
    box_around,
    haversine_km,
)
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    SAME_AREA_PYEONG_TRADES_NOTE,
    iso_date,
    months_ago,
    note,
    null_items_note,
    won_to_manwon,
    years_ago,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongGroupsV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.real_price import (
    NaverComplexPyeongRealPriceGroupV1RequestParameterModel,
    NaverComplexPyeongRealPriceListV1RequestParameterModel,
    NaverComplexPyeongRealPriceV2RequestParameterModel,
    NaverComplexVillaRealPriceAroundV1RequestParameterModel,
    NaverComplexVillaRealPricePageV1RequestParameterModel,
    NaverComplexVillaRealPricePyeongPriceV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import NaverResponseModel
from jibsa.providers.naver.api.response.real_price import (
    NaverRealPriceListModel,
    NaverRealPriceModel,
    NaverVillaAroundModel,
    NaverVillaAroundPriceModel,
)
from jibsa.providers.naver.service.common import (
    PERIOD_MONTHS_BY_NAME,
    SALE_JEONSE_CODE_BY_NAME,
    TRADE_CODE_BY_NAME,
    check_pyeong_numbers,
    group_pyeong_numbers,
    kst_today,
    result_or_empty,
    result_or_none,
    unwrap,
)

from typing import (
    Annotated,
    Any,
)


def _drop_trade_type_fields(data: dict[str, Any], trade_type: str) -> None:
    """출력 dict 에서 거래 유형에 없는 가격 필드와 (매매의) 갱신 키를 뺀다. 실거래 행과 주변 실거래 행이 같은 규칙을 쓴다."""
    for field in NOT_APPLICABLE_PRICE_FIELDS.get(trade_type, frozenset()):
        data.pop(field, None)
    # 갱신 계약은 전월세에만 있다
    if trade_type == '매매':
        data.pop('renewal', None)


def _renewal_by_right(is_renew_request_right: bool | None) -> bool | None:
    """빌라 실거래의 갱신 여부. 갱신 계약 여부 대신 계약갱신요구권 사용 여부만 준다. 썼으면 갱신이지만,
    안 썼어도 합의 갱신일 수 있어 그때는 모름(None)이다."""
    return True if is_renew_request_right else None


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
        Field(description='계약일 (YYYY-MM-DD). 읽지 못하면 null')
    ]
    floor: Annotated[
        int | None,
        Field(description='층')
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
    category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신 계약')
    ] = None
    previous_deposit_manwon: Annotated[
        float | None,
        Field(description='갱신 계약의 종전 보증금 (만원)')
    ] = None
    previous_rent_manwon: Annotated[
        float | None,
        Field(description='갱신 계약의 종전 월세 (만원). 월세·단기임대 갱신 거래만')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        _drop_trade_type_fields(data, self.trade_type)
        # 종전 보증금·월세는 갱신 계약에만 있다 (갱신이 아니거나 모르면 해당 없음)
        # 둘 다 0 이거나 없으면 웹은 '기존 …' 을 그리지 않는다 (빌라 실거래 표 `alreadyDeposit || alreadyMonthlyDeposit`, 2026-11-18
        # 번들 청크 1un70f33iojlw). '종전 0원' 으로 읽히지 않게 두 키를 지운다 (2026-11-18 사용자 결정, 아파트도 같은 규칙)
        no_previous = not (self.previous_deposit_manwon or self.previous_rent_manwon)
        # 리뷰 오탐 (2026-11-17): isRenew 가 null 이면 종전 금액을 지우는 것은 웹과 같다 (웹도 isRenew 가 참일 때만 '기존 …' 을 그린다)
        # 전세 행은 종전 월세도 없다 (웹 실거래 행의 '기존 …' 은 getPriceLabel 로 그려 전세면 보증금만, 월세·단기임대일 때만
        # '보증금/월세' 를 그린다, 2026-11-17 번들 확인). 전세 갱신은 종전 월세로 대부분 0 이 오므로 rent_manwon 처럼 뺀다
        for field in ('previous_deposit_manwon', 'previous_rent_manwon'):
            if field == 'previous_rent_manwon' and 'rent_manwon' in NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()):
                data.pop(field, None)
            elif self.trade_type == '매매' or self.renewal is not True or no_previous:
                data.pop(field, None)
        return data


class NaverRealPricePyeongGroup(BaseModel):
    """실거래를 묶어 받은 평형 묶음 (대표 평수 하나, 예: 33평 묶음에 61A·61B)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='묶음 이름 (대표 평수, 예: 33평)')
    ] = None
    pyeong_numbers: Annotated[
        list[int],
        Field(description='묶음에 든 평형 번호 (번호순). 이 평형들의 거래가 transactions 에 섞여 있다')
    ] = []


class NaverRealPricePerPyeong(BaseModel):
    """빌라 단지 평당 실거래가 한 건. 신고된 거래의 평당가라 `complex --pyeong` 의 호가 평당가(`price_per_pyeong`)와 다르다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 읽지 못하면 null')
    ]
    manwon_per_pyeong: Annotated[
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

    contract_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD). 읽지 못하면 null')
    ]
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ]
    built_year: Annotated[
        int | None,
        Field(description='준공 연도. 준공 연월을 읽지 못하면 null')
    ]
    floor: Annotated[
        str | None,
        Field(description="층 (네이버가 준 글자). 비어 있거나 '-' 면 null")
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
    renewal: Annotated[
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
        return data


class NaverNearbyRange(BaseModel):
    """주변 실거래를 찾은 지도 범위. 단지 좌표가 가운데다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    north_south_m: Annotated[
        int,
        Field(description='남북 길이 (m)')
    ]
    east_west_m: Annotated[
        int,
        Field(description='동서 길이 (m)')
    ]


class NaverNearbyTransactions(BaseModel):
    """빌라 단지 둘레의 주변 실거래 (네이버 웹 빌라 실거래 탭의 '주변 실거래가')."""

    model_config = ConfigDict(
        extra='forbid',
    )

    range: Annotated[
        NaverNearbyRange,
        Field(description='찾은 범위. --around-km 을 주지 않으면 네이버 웹 작은 지도 크기이고, 주면 그 반경을 감싼 정사각형이다')
    ]
    trades: Annotated[
        list[NaverNearbyTrade],
        Field(description=(
            '범위 안 거래. 네이버가 10건까지만 주고 계약일 → 준공연도 → 전용면적이 큰 순이다 (네이버 웹 표와 같다). '
            '--pyeong 평형과 비슷한 면적의 거래도 함께 오니 area_m2 로 가린다. 단지 이름은 오지 않는다. 범위에 거래가 없으면 []'
        ))
    ]


class NaverRealPriceResult(BaseModel):
    """평형별 실거래 내역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_number: Annotated[
        int,
        Field(description='단지 번호')
    ]
    pyeong_number: Annotated[
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
    since: Annotated[
        str | None,
        Field(description='기간 시작일 (YYYY-MM-DD). --period 를 주지 않았으면 키가 없다')
    ] = None
    pyeong_group: Annotated[
        NaverRealPricePyeongGroup | None,
        Field(description='--group 으로 받은 평형 묶음. --group 을 주지 않았으면 키가 없다')
    ] = None
    transactions: Annotated[
        list[NaverRealPrice],
        Field(description='최근 순 실거래. --group 이면 묶음에 든 모든 평형의 거래가 섞여 있고 거래마다 어느 평형인지 알 수 없다')
    ]
    price_per_pyeong_trades: Annotated[
        list[NaverRealPricePerPyeong] | None,
        Field(description=(
            '최근 5년(--period·--pages 와 상관없이) 이 평형의 평당 실거래가 (만원/평, 서버 순서). 빌라 단지의 매매·전세만 키가 있다 '
            '(아파트·월세는 키가 없다). 거래가 없으면 [], 조회가 실패하면 null. 호가 평당가(complex 의 price_per_pyeong)가 아니라 신고된 거래의 평당가다'
        ))
    ] = None
    nearby_transactions: Annotated[
        NaverNearbyTransactions | None,
        Field(description='단지 둘레 범위 안 주변 실거래. 빌라 단지만 키가 있다 (아파트는 키가 없다). 단지 좌표를 모르거나 조회가 실패하면 null')
    ] = None
    notes: Annotated[
        list[str],
        Field(exclude=True, description='기간 안 거래를 다 받지 못했다는 안내 등. CLI 가 결과 위에 붙인다')
    ] = []

    # 빌라 단지의 평당 실거래가를 물었는지(매매·전세). 아니면(아파트·월세) price_per_pyeong_trades 는 해당 없음이라 키를 뺀다
    _price_per_pyeong_scoped: bool = PrivateAttr(default=False)
    # 빌라 단지의 주변 실거래를 물었는지. 아니면(아파트) nearby_transactions 는 해당 없음이라 키를 뺀다
    _nearby_scoped: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.period is None:
            data.pop('period', None)
            data.pop('since', None)
        if self.pyeong_group is None:
            data.pop('pyeong_group', None)
        # 두 칸은 빌라 단지에만 있다 (웹 빌라 실거래 탭). 조회 실패는 null 이고 해당 없음은 키를 뺀다
        if not self._price_per_pyeong_scoped:
            data.pop('price_per_pyeong_trades', None)
        if not self._nearby_scoped:
            data.pop('nearby_transactions', None)
        return data


# 실거래가 한 페이지 크기. 예전 엔드포인트(complex/pyeong/realPrice)와 같은 10건으로 둬 --pages 의 뜻을 유지한다
REAL_PRICE_PAGE_SIZE: int = 10
# 기간 조회에서 빌라 단지 실거래를 받는 페이지 크기와 페이지 수 상한. 빌라 단지는 거래가 적어 보통 한 페이지로 끝난다
VILLA_PERIOD_PAGE_SIZE: int = 100
MAX_VILLA_PERIOD_PAGES: int = 5
PYEONG_GROUP_TRADES_NOTE: str = note(
    '참고',
    '같은 묶음의 다른 평형 거래가 섞여 있고, 거래마다 어느 평형인지는 알려 주지 않습니다. 묶음에 든 평형은 pyeong_group.pyeong_numbers 입니다',
)
# 평당 실거래가의 시작일은 오늘의 몇 년 전인지 (웹 `VILLA_TRANSACTION_PER_PYEONG_YEAR_RANGE`, 청크 26e0315e74_3kmdmwb6eaqal)
PRICE_PER_PYEONG_YEARS: int = 5
# 웹 주변 실거래 칸이 단지 좌표를 가운데로 잡는 작은 지도(388×200px, zoom 16)의 범위. 이 축척이면 572549(위도 37.47)에서
# 2026-11-19 실측한 위도 폭 0.001703°·경도 폭 0.0041628° 와 같다. 위도 폭은 메르카토르라 위도마다 다르다
# (웹이 이 크기를 바꾸면 기본값이 달라질 수 있다). `--around-km` 을 주면 `box_around` 사각형을 쓴다
AROUND_WEB_MAP_WIDTH_PX: int = 388
AROUND_WEB_MAP_HEIGHT_PX: int = 200
AROUND_WEB_DEGREES_PER_PX: float = 360 / (256 * 2 ** 17)
# 주변 실거래를 받는 줌. 웹이 16 을 보낸다. 14 는 같은 범위에도 0건이고 빼면 400 이다 (2026-11-19 실측)
AROUND_ZOOM: int = 16
# 네이버가 범위 안 주변 실거래를 이 수까지만 준다. 이만큼 받았으면 더 있을 수 있다
AROUND_TRADES_LIMIT: int = 10
NEARBY_TRADES_LIMIT_NOTE: str = note(
    '일부',
    f'네이버는 범위 안 거래를 {AROUND_TRADES_LIMIT}건까지만 줍니다 (고르는 기준은 확인하지 못했습니다). '
    '범위(--around-km)를 바꾸면 보이는 거래가 달라질 수 있습니다',
)


def _real_price(item: NaverRealPriceModel, trade_type: str) -> NaverRealPrice:
    return NaverRealPrice(
        trade_type=trade_type,
        trade_date=iso_date(item.trade_date),
        floor=item.floor,
        price_manwon=won_to_manwon(item.deal_price),
        deposit_manwon=won_to_manwon(item.deposit),
        rent_manwon=won_to_manwon(item.monthly_rent),
        category=item.trade_category or None,
        cancelled=item.is_delete,
        renewal=item.is_renew,
        previous_deposit_manwon=won_to_manwon(item.already_deposit),
        previous_rent_manwon=won_to_manwon(item.already_monthly_rent),
    )


def get_real_prices(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str = '매매',
    pages: int = 1,
    period: str | None = None,
    group: bool = False,
    around_km: float | None = None,
    today: date | None = None,
) -> NaverRealPriceResult:
    """평형별 실거래가를 `pages` 페이지(페이지당 `REAL_PRICE_PAGE_SIZE` 건)까지 모아 만원으로 환산한다.

    빌라 단지는 아파트 단지 실거래가가 비어 오므로, 첫 페이지가 비면 평형 번호를 확인하면서 단지 종류를 정하고
    (1~2회 추가) 빌라 단지면 빌라 단지 실거래가로 다시 묻는다. 아파트 단지면 거래가 없는 평형으로 보고 0건이다.
    빌라 단지면 웹 빌라 실거래 탭의 두 칸도 붙인다: 최근 5년 평당 실거래가 `price_per_pyeong_trades`(매매·전세만, 1회 추가)와
    단지 둘레 주변 실거래 `nearby_transactions`(단지 좌표 1회 + 주변 실거래 1회 추가).

    Args:
        period: `PERIOD_MONTHS_BY_NAME` 의 이름. 주면 `pages` 대신 그 기간 안 거래를 모두 받는다
            (아파트 단지는 1회 호출). `group` 과 함께 줄 수 없다.
        group: 주면 그 평형이 든 평형 묶음(`complex/pyeongGroups`, 1회 호출)의 모든 평형 거래를 `pages` 페이지까지 받는다.
            웹 평형 묶음 화면과 같은 요청이다. 묶음이 없는 단지(빌라 단지 등)는 다른 API 로 대신 찾지 않고 에러로 낸다.
        around_km: 빌라 단지의 주변 실거래 범위 (km, 단지 좌표를 가운데로 한 정사각형 한 변의 절반). 빼면 네이버 웹 작은 지도 크기.
            아파트 단지에 주면 단지 종류를 정한 직후 INVALID_ARGUMENT 로 막는다 (그 뒤 요청은 보내지 않는다). `group` 과 함께 줄 수 없다.
        today: 기간의 기준일. Defaults to 오늘(한국 시간).

    Raises:
        ValueError: `group` 과 `period`, `group` 과 `around_km` 을 함께 줬을 때 (CLI 가 먼저 막는다).
        JibsaError: 거래가 0건인데 평형 번호가 그 단지에 없으면 NOT_FOUND. `group` 이면 단지에 평형 묶음이 없을 때와
            묶음에 그 평형 번호가 없을 때 NOT_FOUND. 아파트 단지에 `around_km` 을 줬으면 INVALID_ARGUMENT.
    """
    if group and period is not None:
        raise ValueError('group 과 period 는 함께 쓸 수 없습니다')
    if group and around_km is not None:
        raise ValueError('group 과 around_km 은 함께 쓸 수 없습니다')
    today = today or kst_today()
    if period is not None:
        result, villa = _get_real_prices_in_period(
            client, complex_number, pyeong_number, trade_type=trade_type, period=period, around_km=around_km, today=today,
        )
    else:
        result, villa = _get_real_prices_by_page(
            client, complex_number, pyeong_number, trade_type=trade_type, pages=pages, group=group, around_km=around_km,
        )
    if villa:
        # 두 조회(평당 실거래가, 주변 실거래)는 `--period`·`--pages` 와 상관없다 (웹 칸도 실거래 목록과 따로 부른다)
        # 빌라 단지 평당 실거래가를 받는 거래 유형. 웹은 매매·전세일 때만 이 칸을 그리고 월세면 칸이 없다 (청크 b042d8aace_1okty1145x932, 2026-11-18)
        if result.trade_type in SALE_JEONSE_CODE_BY_NAME:
            # 시작일은 오늘의 5년 전이다 (웹과 같다). 조회가 실패하면 모름(None)이고 `[실패]` 안내를 붙인다. 거래가 없으면 `[]` 이고, 성공인데 `result` 가 null 이어도 거래 없음(`[]`)이다
            rows = result_or_empty(
                lambda: client.run_request_complex_villa_real_price_pyeong_price_v1(
                    NaverComplexVillaRealPricePyeongPriceV1RequestParameterModel(
                        complex_number=result.complex_number,
                        pyeong_type_number=result.pyeong_number,
                        trade_type=SALE_JEONSE_CODE_BY_NAME[result.trade_type],
                        start_date=years_ago(today, PRICE_PER_PYEONG_YEARS),
                    )
                ),
                list,
                notes=result.notes,
                what='평당 실거래가',
                unknown='모름(null)으로 낸 칸: price_per_pyeong_trades',
            )
            result.price_per_pyeong_trades = None if rows is None else [
                NaverRealPricePerPyeong(trade_date=iso_date(row.trade_date), manwon_per_pyeong=won_to_manwon(row.pyeong_price))
                for row in rows
            ]
            result._price_per_pyeong_scoped = True
        # 단지 둘레 주변 실거래 (단지 좌표 1회 + 주변 실거래 1회). 단지 좌표를 모르거나 조회가 실패하면 모름(None)이다
        complex_ = result_or_none(
            lambda: client.run_request_complex_villa_v1(
                NaverComplexVillaV1RequestParameterModel(complex_number=result.complex_number)
            ),
            notes=result.notes,
            what='단지 좌표',
            unknown='모름(null)으로 낸 칸: nearby_transactions',
        )
        center = None if complex_ is None else complex_.coordinates
        result.nearby_transactions = None
        if center is not None:
            lat, lng = center.y_coordinate, center.x_coordinate
            # 범위는 단지 좌표를 가운데로 `around_km` 을 주면 그 반경을 감싼 사각형(`box_around`), 아니면 웹 작은 지도 크기다
            if around_km is not None:
                south, north, west, east = box_around(lat, lng, around_km)
            else:
                # 웹 주변 실거래 칸이 단지 좌표를 가운데로 잡는 작은 지도의 범위를 (남, 북, 서, 동) 도로 구한다. 경도 폭은 위도와
                # 상관없이 같고, 위도 폭은 메르카토르 투영이라 위도마다 다르다
                half_lng = AROUND_WEB_MAP_WIDTH_PX / 2 * AROUND_WEB_DEGREES_PER_PX
                half_y = AROUND_WEB_MAP_HEIGHT_PX / 2 * radians(AROUND_WEB_DEGREES_PER_PX)
                y = log(tan(pi / 4 + radians(lat) / 2))
                south = degrees(2 * atan(exp(y - half_y)) - pi / 2)
                north = degrees(2 * atan(exp(y + half_y)) - pi / 2)
                west, east = lng - half_lng, lng + half_lng
            around = result_or_empty(
                lambda: client.run_request_complex_villa_real_price_around_v1(
                    NaverComplexVillaRealPriceAroundV1RequestParameterModel(
                        complex_number=result.complex_number,
                        pyeong_type_number=result.pyeong_number,
                        trade_type=TRADE_CODE_BY_NAME[result.trade_type],
                        top=north,
                        bottom=south,
                        left=west,
                        right=east,
                        zoom=AROUND_ZOOM,
                    )
                ),
                NaverVillaAroundModel,
                notes=result.notes,
                what='주변 실거래',
                unknown='모름(null)으로 낸 칸: nearby_transactions',
            )
            if around is not None:
                trades: list[NaverNearbyTrade] = []
                # 빈 항목(null)이라 빼고 읽은 수. 서버는 그 자리도 거래로 세어 10건까지 주므로 상한에 닿았는지 볼 때 더한다
                dropped = around.null_items('bundles')
                for bundle in around.bundles or []:
                    dropped += bundle.null_items('trades')
                    point = None if bundle.complex_info is None else bundle.complex_info.coordinates
                    distance_m = (
                        None if point is None or point.x_coordinate is None or point.y_coordinate is None
                        else round(haversine_km(lat, lng, point.y_coordinate, point.x_coordinate) * 1000)
                    )
                    for trade in bundle.trades or []:
                        price = trade.price or NaverVillaAroundPriceModel()
                        floor = (trade.floor or '').strip()
                        completion = (trade.completion_year_month or '').strip()
                        trades.append(NaverNearbyTrade(
                            trade_type=result.trade_type,
                            contract_date=iso_date(trade.contract_date),
                            area_m2=trade.exclusive_area,
                            # 준공 연월일(`20100628`)의 연도. 앞 네 자리가 숫자가 아니거나 0000 이면 모름(None)이다
                            built_year=(
                                (int(completion[:4]) or None)
                                if len(completion) >= 4 and completion[:4].isascii() and completion[:4].isdigit() else None
                            ),
                            floor=None if floor in ('', '-') else floor,
                            price_manwon=won_to_manwon(price.deal_price),
                            deposit_manwon=won_to_manwon(price.deposit),
                            rent_manwon=won_to_manwon(price.monthly_rent),
                            renewal=_renewal_by_right(trade.is_renew_request_right),
                            distance_m=distance_m,
                            # 네이버가 건물 번호를 주지 않아 단지 좌표와 같은 점인지로 가린다. 좌표의 소수 자릿수가 달라도(6~7자리) 같게 보도록
                            # 반올림한 거리가 0(0.5m 안)이면 같은 건물이다
                            same_complex=None if distance_m is None else distance_m == 0,
                        ))
                # 건물마다 묶어 오는 거래를 한 목록으로 폈다. 웹 표(`ComplexVillaTransactionPriceForAround`)와 같은 순서(계약일 →
                # 준공연도 → 전용면적이 큰 순)로 세우고 값이 없는 칸은 가장 뒤로 보낸다
                trades.sort(key=lambda trade: (trade.contract_date or '', trade.built_year or 0, trade.area_m2 or 0), reverse=True)
                if len(trades) + dropped >= AROUND_TRADES_LIMIT:
                    result.notes.append(NEARBY_TRADES_LIMIT_NOTE)
                if dropped:
                    result.notes.append(null_items_note('네이버 주변 실거래', dropped))
                box_range = NaverNearbyRange(
                    north_south_m=round((north - south) * KM_PER_LAT_DEGREE * 1000),
                    east_west_m=round((east - west) * KM_PER_LAT_DEGREE * cos(radians(lat)) * 1000),
                )
                result.nearby_transactions = NaverNearbyTransactions(range=box_range, trades=trades)
        result._nearby_scoped = True
    return result


def _require_villa_for_around_km(around_km: float | None, villa: bool) -> None:
    """`--around-km` 은 빌라 단지의 주변 실거래 범위라 아파트 단지에 주면 막는다.

    단지 종류는 실거래 응답을 받고서야 알 수 있어 그 직후에 부른다 (옵션을 빼고 다시 부르면 성공한다).
    """
    if around_km is not None and not villa:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='--around-km 은 빌라 단지의 주변 실거래 범위입니다',
            hint='옵션을 빼고 다시 부르세요',
        )


def _get_real_prices_by_page(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str,
    pages: int,
    group: bool,
    around_km: float | None,
) -> tuple[NaverRealPriceResult, bool]:
    """실거래를 `pages` 페이지까지 받는다 (`get_real_prices` 의 `period` 를 주지 않은 갈래).

    Returns:
        tuple[NaverRealPriceResult, bool]: 결과, 빌라 단지인지.
    """
    # 묶음 조회는 이 목록 요청 앞에서 한다 (없는 묶음이면 요청 없이 멈춘다)
    pyeong_group, group_numbers = _find_pyeong_group(client, complex_number, pyeong_number) if group else (None, [])

    def fetch_page(page: int) -> NaverResponseModel[NaverRealPriceListModel]:
        if pyeong_group is not None:
            return client.run_request_complex_pyeong_real_price_group_v1(
                NaverComplexPyeongRealPriceGroupV1RequestParameterModel(
                    complex_number=complex_number,
                    pyeong_type_numbers=group_numbers,
                    trade_type=TRADE_CODE_BY_NAME[trade_type],
                    page=page,
                    size=REAL_PRICE_PAGE_SIZE,
                )
            )
        return client.run_request_complex_pyeong_real_price_v2(
            NaverComplexPyeongRealPriceV2RequestParameterModel(
                complex_number=complex_number,
                pyeong_type_number=pyeong_number,
                trade_type=TRADE_CODE_BY_NAME[trade_type],
                page=page,
                size=REAL_PRICE_PAGE_SIZE,
            )
        )

    transactions: list[NaverRealPrice] = []
    villa = False
    # 빈 항목(null)이라 빼고 읽은 수. 서버는 그 자리도 거래로 센 쪽이라 쪽이 비었는지 볼 때 더한다
    dropped = 0
    for page in range(pages):
        result = unwrap(fetch_page(page), '실거래가')
        page_dropped = result.null_items('items')
        dropped += page_dropped
        empty = not result.items and not page_dropped
        if page == 0:
            # 아파트 목록이 비어 오면 평형 번호를 확인하면서 단지 종류를 정한다. 묶음으로 받을 때는 그 평형이 든 묶음을 이미
            # 찾았으니 빌라 단지가 아니다 (빌라 단지는 묶음을 찾는 데서 에러). 목록이 비지 않았으면 아파트 단지다
            villa = (
                empty and pyeong_group is None
                and check_pyeong_numbers(client, complex_number, [pyeong_number], pyeong_required=True)
            )
            # 아파트 단지에는 주변 실거래 범위가 없어 더 받기 전에 막는다 (거래 없는 아파트 평형도 단지 종류는 정해졌다)
            _require_villa_for_around_km(around_km, villa)
            if villa:
                transactions, _, dropped = _villa_real_prices(
                    client, complex_number, pyeong_number, trade_type=trade_type, size=REAL_PRICE_PAGE_SIZE, max_pages=pages,
                )
                break
        if empty:
            break
        transactions.extend(_real_price(item, trade_type) for item in result.items or [])
        if result.has_next_page is False:
            break
    # 네이버는 같은 거래를 면적이 다른 평형 여러 곳에 함께 주기도 하고 거래마다 면적은 주지 않아 가려낼 수 없다
    # (2026-10-24 실측: 단지 65 전세 평형 1·2 응답에 2026-09-11 3층 19억 등 3건이 같이 있었다. 요청의 pyeongTypeNumber 는
    # 1·2 로 달랐다. 당근 실거래로는 84.81㎡ 거래). docs/naver.md 가 당근 area_m2 로 확인하라고 안내하고, 전용면적이 같은
    # 평형끼리는 거의 모두 겹쳐 결과에도 SAME_AREA_PYEONG_TRADES_NOTE 를 붙인다
    notes: list[str] = []
    if transactions and pyeong_group is not None:
        notes.append(PYEONG_GROUP_TRADES_NOTE)
    elif transactions and not villa:
        notes.append(SAME_AREA_PYEONG_TRADES_NOTE)
    if dropped:
        notes.append(null_items_note('네이버 실거래', dropped))
    real_prices = NaverRealPriceResult(
        complex_number=complex_number,
        pyeong_number=pyeong_number,
        trade_type=trade_type,
        pyeong_group=pyeong_group,
        transactions=transactions,
        notes=notes,
    )
    return real_prices, villa


def _find_pyeong_group(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
) -> tuple[NaverRealPricePyeongGroup, list[int]]:
    """평형이 든 평형 묶음을 찾는다 (1회 호출). 조회가 실패하면 삼키지 않고 `unwrap` 이 에러로 올린다.

    웹은 단지형 빌라에서 묶음을 부르지 않는다. 묶음이 없는 단지(빌라 단지 등)는 다른 API 로 대신 찾지 않고 묶음 없이 부르라고 알린다.
    없는 단지 번호와 빌라 단지가 모두 `isSuccess: true, result: []` 로 와서(없는 단지 99999999·빌라 단지 673573·572549, 2026-11-18 실측)
    응답으로 둘을 가를 수 없다. `result: null` 도 같게 본다.

    Returns:
        tuple[NaverRealPricePyeongGroup, list[int]]: 출력용 묶음 정보, 요청에 보낼 평형 번호 (웹과 같게 대표 번호가 먼저, 나머지는 번호순).

    Raises:
        JibsaError: 단지에 평형 묶음이 없거나 묶음에 그 평형 번호가 없으면 NOT_FOUND (평형 번호를 주지 않은 묶음은 없는 것으로 본다).
            조회가 실패하면(`isSuccess` false) UPSTREAM_ERROR.
    """
    response = client.run_request_complex_pyeong_groups_v1(NaverComplexPyeongGroupsV1RequestParameterModel(complex_number=complex_number))
    # 성공인데 result 가 null 이어도 `[]` 와 같다 (`unwrap` 은 이것을 다른 NOT_FOUND 로 낸다). 실패 응답은 그대로 `unwrap` 이 에러로 올린다
    groups = [] if response.is_success and response.result is None else unwrap(response, '평형 묶음')
    if not groups:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'단지 {complex_number} 의 평형 묶음을 찾지 못했습니다 (없는 단지 번호이거나 단지형 빌라처럼 평형 묶음이 없는 단지)',
            # 번호 끝자리마다 '로/으로' 가 갈려 조사 없이 쓴다 (convention-2)
            hint=f'단지가 있는지 확인하고(jibsa naver complex {complex_number}), 있으면 --group 없이 평형 하나의 실거래를 조회하세요',
        )
    # 네이버가 평형 번호를 주지 않은 묶음(`pyeongTypes` null 등)은 번호를 짝지을 수 없어 건너뛴다
    numbers_by_group = [(item, group_pyeong_numbers(item)) for item in groups]
    known = [(item, numbers) for item, numbers in numbers_by_group if numbers]
    found = next(((item, numbers) for item, numbers in known if pyeong_number in numbers), None)
    if found is None:
        available = '; '.join(f"{item.representative_pyeong_name or '이름 없음'}: {', '.join(map(str, numbers))}" for item, numbers in known)
        raise JibsaError(
            code='NOT_FOUND',
            message=f'단지 {complex_number} 의 평형 묶음에 없는 평형 번호입니다: {pyeong_number}',
            hint=(
                f'묶음별 평형 번호: {available}. 위 묶음의 평형 번호 중 하나로 다시 부르세요' if available
                else '네이버가 묶음의 평형 번호를 주지 않았습니다. --group 없이 평형 하나의 실거래를 조회하세요'
            ),
        )
    group, numbers = found
    request_numbers = sorted(numbers, key=lambda number: (number != group.representative_pyeong_number, number))
    return NaverRealPricePyeongGroup(name=group.representative_pyeong_name, pyeong_numbers=numbers), request_numbers


def _villa_real_prices(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str,
    size: int,
    max_pages: int,
    since: str | None = None,
) -> tuple[list[NaverRealPrice], bool, int]:
    """빌라 단지 실거래를 최근 순으로 `max_pages` 쪽까지 받는다. `since` 를 주면 그보다 오래된 거래가 나온 쪽에서 멈춘다.

    `check_pyeong_numbers` 로 빌라 단지임을 정한 뒤에만 부른다. 빌라 단지에 그 거래가 없으면 서버는 실패가 아니라
    빈 목록을 주므로(서진빌라 724112 월세: isSuccess true·0건, 2026-10-10) 실패 응답은 0건으로 보지 않고 에러로 낸다.

    Returns:
        tuple[list[NaverRealPrice], bool, int]: 거래, 쪽 수 상한에 걸려 멈췄는지 (더 있을 수 있음), 빈 항목(null)이라 빼고 읽은 수.
    """
    transactions: list[NaverRealPrice] = []
    dropped = 0
    for page in range(max_pages):
        result = unwrap(
            client.run_request_complex_villa_real_price_page_v1(
                NaverComplexVillaRealPricePageV1RequestParameterModel(
                    complex_number=complex_number,
                    pyeong_type_number=pyeong_number,
                    trade_type=TRADE_CODE_BY_NAME[trade_type],
                    page=page,
                    size=size,
                )
            ),
            '실거래가',
        )
        page_dropped = result.null_items('items')
        dropped += page_dropped
        recent = [
            NaverRealPrice(
                trade_type=trade_type,
                trade_date=iso_date(item.trade_date),
                floor=item.floor,
                price_manwon=won_to_manwon(item.deal_price),
                deposit_manwon=won_to_manwon(item.deposit),
                rent_manwon=won_to_manwon(item.monthly_rent),
                category=item.trade_category or None,
                cancelled=item.is_canceled,
                renewal=_renewal_by_right(item.is_renew_request_right),
                # 종전 보증금·월세: 빌라 실거래 행에도 alreadyDeposit·alreadyMonthlyDeposit(아파트의 alreadyMonthlyRent 와 키 이름이
                # 다르다)가 오고, 웹 빌라 실거래 표는 isRenewRequestRight 행에 '기존 …' 으로 보여 준다 (2026-11-18 번들 청크
                # 1un70f33iojlw). drop_not_applicable 이 아파트와 같은 규칙(갱신 전세·월세만, 전세는 종전 월세 삭제)으로 키를 지운다
                previous_deposit_manwon=won_to_manwon(item.already_deposit),
                previous_rent_manwon=won_to_manwon(item.already_monthly_deposit),
            )
            for item in result.items
        ]
        # 계약일을 모르는 거래(None)는 서버가 준 거래라 남기되, 기간 안인지 알 수 없으므로 멈춤 판정(`len(kept) < len(recent)`)
        # 에는 세지 않는다 (모르는 날짜 하나 때문에 다음 쪽의 기간 안 거래를 놓치지 않게). 그래서 멈춤은 날짜가 있고 `since`
        # 보다 오래된 거래가 있을 때만 일어나고, 한 쪽이 전부 계약일 모름이면 멈추지 않고 쪽 수 상한까지 가서 truncated 로 끝난다
        kept = recent if since is None else [item for item in recent if item.trade_date is None or item.trade_date >= since]
        transactions.extend(kept)
        # 마지막 쪽을 넘겨도 result=null 이 아니라 빈 목록이 와서(hasNextPage false) unwrap 이 에러를 내지
        # 않는다 (2026-10-09 확인). 빈 항목(null)만 온 쪽은 비지 않은 쪽이다 (서버가 그 자리를 거래로 센다)
        if len(kept) < len(recent) or (not result.items and not page_dropped) or result.has_next_page is False:
            return transactions, False, dropped
    return transactions, True, dropped


def _get_real_prices_in_period(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    *,
    trade_type: str,
    period: str,
    around_km: float | None,
    today: date,
) -> tuple[NaverRealPriceResult, bool]:
    """기간 안 실거래 전부. 아파트 단지는 기간 목록 1회, 비어 오면 평형 번호를 확인하면서 단지 종류를 정하고
    빌라 단지면 빌라 단지 페이지를 기간 시작일까지 넘긴다.

    기간 목록은 빌라 단지에 거래가 있어도 빈 목록을 준다 (서진빌라 전세 4건, 2026-10-10 확인).

    Returns:
        tuple[NaverRealPriceResult, bool]: 결과, 빌라 단지인지.
    """
    since = months_ago(today, PERIOD_MONTHS_BY_NAME[period])
    response = client.run_request_complex_pyeong_real_price_list_v1(
        NaverComplexPyeongRealPriceListV1RequestParameterModel(
            complex_number=complex_number,
            pyeong_type_number=pyeong_number,
            trade_type=TRADE_CODE_BY_NAME[trade_type],
            start_date=since,
            end_date=today.isoformat(),
        )
    )
    items = unwrap(response, '실거래가')
    # 빈 항목(null)이라 빼고 읽은 수. 서버는 그 자리도 거래로 센 목록이라 목록이 비었는지 볼 때 더한다
    dropped = response.null_items('result')
    transactions = [_real_price(item, trade_type) for item in items]
    notes: list[str] = [SAME_AREA_PYEONG_TRADES_NOTE] if transactions else []
    # 목록이 비어 오면 평형 번호를 확인하면서 단지 종류를 정한다. 비지 않았으면 아파트 단지다
    villa = not transactions and not dropped and check_pyeong_numbers(
        client, complex_number, [pyeong_number], pyeong_required=True,
    )
    # 아파트 단지에는 주변 실거래 범위가 없어 빌라 실거래를 받기 전에 막는다
    _require_villa_for_around_km(around_km, villa)
    if villa:
        transactions, truncated, dropped = _villa_real_prices(
            client, complex_number, pyeong_number,
            trade_type=trade_type, size=VILLA_PERIOD_PAGE_SIZE, max_pages=MAX_VILLA_PERIOD_PAGES, since=since,
        )
        if truncated:
            notes.append(note(
                '일부',
                f'빌라 단지 실거래를 {MAX_VILLA_PERIOD_PAGES * VILLA_PERIOD_PAGE_SIZE}건까지만 받았습니다. '
                '기간 안 거래가 더 있을 수 있으니 --period 를 줄여 보세요',
            ))
    if dropped:
        notes.append(null_items_note('네이버 실거래', dropped))
    real_prices = NaverRealPriceResult(
        complex_number=complex_number,
        pyeong_number=pyeong_number,
        trade_type=trade_type,
        period=period,
        since=since,
        transactions=transactions,
        notes=notes,
    )
    return real_prices, villa
