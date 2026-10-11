"""아파트 실거래가 (real-price)."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    KST,
    NOT_APPLICABLE_PRICE_FIELDS,
    TradeType,
    normalize_date,
    normalize_floor,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.real_price import (
    ZigbangDanjisRoomTypesRtPricesRequestParameterModel,
    ZigbangDanjisRtPricesRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.real_price import (
    ZigbangDanjisRtPricesResponseModel,
    ZigbangRtPriceModel,
)
from jibsa.providers.zigbang.service.common import (
    apt_danji_url,
    fetch_danji,
    parse_complex_id,
)

from typing import (
    Annotated,
    Any,
)


REAL_PRICE_TRADE_TYPES: tuple[TradeType, ...] = ('매매', '전세', '월세')
REAL_PRICE_DEAL_TYPE_BY_TRADE: dict[str, str] = {'매매': 'sales', '전세': 'rent', '월세': 'rent'}
TRADE_BY_RT_DEAL_TYPE: dict[str, TradeType] = {'sales': '매매', 'charter': '전세', 'rent': '월세'}
REAL_PRICE_CATEGORY_BY_METHOD: dict[str, str] = {'relay': '중개거래', 'direct': '직거래'}
REAL_PRICE_PAGE_SIZE: int = 50
# 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건, 당근과 같다). 매매는 --limit 1200 도 24쪽이면 된다
REAL_PRICE_MAX_PAGES: int = 24
# real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES
RT_DEAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2,4})\.\s*(\d{1,2})\.\s*(\d{1,2})')


class ZigbangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데만 쓰고 출력하지 않는다')
    ]

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    pyeong_name: Annotated[
        str | None,
        Field(description='평형 이름 (공급면적 평 기준, 예: 34A)')
    ] = None
    floor: Annotated[
        str | None,
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
        Field(description='중개거래 / 직거래 (매매만)')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='신고 뒤 해제(취소)된 거래 (매매만)')
    ] = None
    presale: Annotated[
        str | None,
        Field(description='분양권 / 입주권 거래 (매매만, 해당할 때만 키가 있다)')
    ] = None
    renewal: Annotated[
        bool | None,
        Field(description='갱신·재계약 (전월세만). 직방은 알려 주지 않아 항상 null')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        fields = set(NOT_APPLICABLE_PRICE_FIELDS.get(self.trade_type, frozenset()))
        if self.trade_type == '매매':
            fields.add('renewal')
        else:
            fields |= {'category', 'cancelled', 'presale'}
        if self.presale is None:
            fields.add('presale')
        for field in fields:
            data.pop(field, None)
        return data


class ZigbangRealPriceResult(BaseModel):
    """아파트 단지 실거래 내역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    trade_type: Annotated[
        str,
        Field(description='거래 유형')
    ]
    pyeong_id: Annotated[
        int | None,
        Field(description='평형 ID. null 이면 전체 평형')
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 거래 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 오래된 거래가 더 있는지')
    ]
    transactions: Annotated[
        list[ZigbangRealPrice],
        Field(description='최근 계약 순 실거래')
    ]
    url: Annotated[
        str,
        Field(description='단지 페이지 URL (시세 그래프는 여기서 본다)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='전월세를 넘겨 본 범위 안내. CLI 가 결과 위에 붙인다')
    ] = []


def rt_deal_date(value: str | None) -> str | None:
    """직방 계약일 '26. 9. 8' 을 2026-09-08 로 바꾼다. 두 자리 연도는 올해 이후면 1900년대로 본다."""
    if value is None:
        return None
    match = RT_DEAL_DATE_PATTERN.match(value.strip())
    if match is None:
        return value.strip() or None
    year, month, day = (int(part) for part in match.groups())
    if year < 100:
        this_year = datetime.now(KST).year
        year += 2000 if 2000 + year <= this_year + 1 else 1900
    return normalize_date(f'{year:04d}{month:02d}{day:02d}')


def rt_price_to_real_price(transaction: ZigbangRtPriceModel) -> ZigbangRealPrice | None:
    """실거래 한 건을 `ZigbangRealPrice` 로 바꾼다. 거래 유형을 모르면 None."""
    trade_type = TRADE_BY_RT_DEAL_TYPE.get(transaction.deal_type or '')
    if trade_type is None:
        return None
    is_sale = trade_type == '매매'
    title = transaction.area_infos[0] if transaction.area_infos else None
    return ZigbangRealPrice(
        trade_type=trade_type,
        trade_date=rt_deal_date(transaction.deal_date),
        area_m2=transaction.area_m2,
        pyeong_name=title.p if title else None,
        # 매물 목록·상세(Listing 검증기)와 당근 실거래가처럼 지하층을 '지하1' 로 맞춘다
        floor=None if transaction.floor is None else normalize_floor(str(transaction.floor)),
        price_manwon=transaction.price if is_sale else None,
        deposit_manwon=None if is_sale else transaction.price,
        rent_manwon=transaction.price_rent if trade_type == '월세' else None,
        category=REAL_PRICE_CATEGORY_BY_METHOD.get(transaction.method or '', transaction.method),
        cancelled=transaction.is_cancellation,
        presale=transaction.offer_type or None,
    )


def _check_real_price_scope(
    client: ZigbangClient,
    complex_id: str,
    danji_id: int,
    response: ZigbangDanjisRtPricesResponseModel,
    pyeong_id: int | None,
) -> None:
    """없는 단지·평형이면 0건 대신 에러로 알린다. 실거래 API 는 없는 단지에도 빈 성공을 준다.

    없는 단지는 평형 정보가 비어 오고, 거래가 없는 단지도 평형 정보는 온다 (2026-10-10 실측: 없는 단지 2곳
    0개, 실제 단지 3곳 8~30개, 2028년 입주 예정 단지 8개). 평형을 지정해도 단지 전체 평형이 온다.
    평형이 아직 없는 새 단지일 수도 있어, 비었을 때만 단지 정보로 있는지 확인한다 (요청 1회, 없으면 NOT_FOUND).

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 단지에 없는 평형 (INVALID_ARGUMENT).
    """
    if not response.pyeongs:
        fetch_danji(client, complex_id, danji_id)
        return
    if pyeong_id is not None and str(pyeong_id) not in response.pyeongs:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'{complex_id} 단지에 없는 평형 ID 입니다: {pyeong_id}',
            hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].id 를 --pyeong 에 주세요',
        )


def get_real_prices(
    client: ZigbangClient,
    complex_id: str,
    *,
    trade_type: TradeType = '매매',
    pyeong_id: int | None = None,
    limit: int = 120,
) -> ZigbangRealPriceResult:
    """아파트 단지(또는 평형 하나)의 실거래가를 최근 계약 순으로 `limit` 건 모은다.

    직방은 전세·월세를 한데 묶어 줘서(`rent`), 한쪽만 고르면 받은 뒤에 거르고 쪽을 더 넘긴다.
    `REAL_PRICE_MAX_PAGES` 쪽(최근 1200건)에서 멈추고, 그래도 모자라면 본 범위를 `notes` 로 알린다.
    갱신 계약 여부는 직방이 주지 않는다.

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 오피스텔 건물·없는 평형일 때 (INVALID_ARGUMENT), 없는 단지일 때 (NOT_FOUND).
    """
    kind, number = parse_complex_id(complex_id)
    if kind != 'apt':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='직방 실거래가는 아파트 단지만 있습니다',
            hint='아파트 단지 ID(apt-…)를 주세요. 오피스텔 시세는 naver real-price 나 daangn real-price --item 으로 보세요',
        )
    deal_type = REAL_PRICE_DEAL_TYPE_BY_TRADE[trade_type]
    transactions: list[ZigbangRealPrice] = []
    has_next = False
    page = 0
    while len(transactions) < limit and page < REAL_PRICE_MAX_PAGES:
        if pyeong_id is None:
            response: ZigbangDanjisRtPricesResponseModel = client.run_request_danjis_rt_prices(
                ZigbangDanjisRtPricesRequestParameterModel(
                    danji_id=number, deal_type=deal_type, offset=page, limit=REAL_PRICE_PAGE_SIZE,
                )
            )
        else:
            response = client.run_request_danjis_room_types_rt_prices(
                ZigbangDanjisRoomTypesRtPricesRequestParameterModel(
                    danji_id=number, room_type_id=pyeong_id, deal_type=deal_type, offset=page, limit=REAL_PRICE_PAGE_SIZE,
                )
            )
        if page == 0:
            _check_real_price_scope(client, complex_id, number, response, pyeong_id)
        page += 1
        has_next = response.has_next
        for transaction in response.transactions:
            real_price = rt_price_to_real_price(transaction)
            if real_price is not None and real_price.trade_type == trade_type:
                transactions.append(real_price)
        if not has_next or not response.transactions:
            break
    notes: list[str] = []
    if deal_type == 'rent' and has_next and len(transactions) < limit:
        notes.append(
            f'직방은 전세·월세를 함께 줘서 최근 거래 {page * REAL_PRICE_PAGE_SIZE}건 중 {trade_type}만 골랐습니다. '
            '더 오래된 거래는 보지 않았습니다'
        )
    has_more = has_next or len(transactions) > limit
    filled = len(transactions) >= limit
    transactions = transactions[:limit]
    url = apt_danji_url(number)
    if not has_more:
        notes.append('직방 API가 제공하는 마지막 실거래가 페이지까지 조회했습니다')
    elif filled and page < REAL_PRICE_MAX_PAGES:
        # --limit 에서 멈췄으면 늘려서 더 받을 수 있다. 직방에서 직접 보라는 안내는 쪽 상한까지 보고도 남았을 때만 맞다
        notes.append(
            '더 조회할 실거래가가 있습니다. '
            f'--limit 을 늘리면 (최대 {REAL_PRICE_MAX_LIMIT}건) 더 오래된 거래까지 받습니다'
        )
    else:
        notes.append(f'더 조회할 실거래가가 있습니다. 더 오래된 거래는 직방에서 직접 확인해 주세요: {url}')
    return ZigbangRealPriceResult(
        complex_id=complex_id,
        trade_type=trade_type,
        pyeong_id=pyeong_id,
        returned=len(transactions),
        has_more=has_more,
        transactions=transactions,
        url=url,
        notes=notes,
    )
