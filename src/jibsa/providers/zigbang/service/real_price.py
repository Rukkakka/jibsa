"""아파트 실거래가 (real-price). 매매·전세·월세를 따로, 또는 전체(`dealType=all`)를 한 목록으로 받는다."""

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
    UPDATE_MAYBE_NEEDED,
    TradeType,
    normalize_date,
    normalize_floor,
    note,
    null_items_note,
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
from jibsa.providers.zigbang.service.common.base import (
    apt_danji_url,
    fetch_danji,
    parse_complex_id,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


# 실거래 조회가 받는 거래 유형. '전체' 는 직방이 매매와 전월세를 계약일 최신 순으로 합쳐 주는 조회 (웹 실거래 탭의 기본)
RealPriceTradeType = Literal['매매', '전세', '월세', '전체']
REAL_PRICE_TRADE_TYPES: tuple[RealPriceTradeType, ...] = ('매매', '전세', '월세', '전체')
REAL_PRICE_DEAL_TYPE_BY_TRADE: dict[str, str] = {'매매': 'sales', '전세': 'rent', '월세': 'rent', '전체': 'all'}
TRADE_BY_RT_DEAL_TYPE: dict[str, TradeType] = {'sales': '매매', 'charter': '전세', 'rent': '월세'}
REAL_PRICE_CATEGORY_BY_METHOD: dict[str, str] = {'relay': '중개거래', 'direct': '직거래'}
REAL_PRICE_PAGE_SIZE: int = 50
# 전세·월세를 골라 내느라 전월세를 넘겨 보는 최대 페이지 (최근 1200건, 당근과 같다). 매매는 --limit 1200 도 24쪽이면 된다
REAL_PRICE_MAX_PAGES: int = 24
# real-price 의 --limit 최대값. CLI 옵션의 max 와 '--limit 을 늘리면' 안내가 함께 쓴다
REAL_PRICE_MAX_LIMIT: int = REAL_PRICE_PAGE_SIZE * REAL_PRICE_MAX_PAGES
RT_DEAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2,4})\.\s*(\d{1,2})\.\s*(\d{1,2})')


class ZigbangRealPrice(BaseModel):
    """실거래 한 건 (만원, 국토부 신고 기준). 거래 유형에 없는 필드는 출력에서 뺀다.

    거래 유형(`trade_type`)은 보통 결과 맨 위에 있어 거래마다 내지 않고, 전체 조회에서만 거래마다 낸다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_type: Annotated[
        str,
        Field(exclude=True, description='거래 유형. 필드를 고르는 데 쓰고, 전체 조회(show_trade_type)가 아니면 출력하지 않는다')
    ]
    show_trade_type: Annotated[
        bool,
        Field(exclude=True, description='거래마다 trade_type 을 맨 앞에 낼지 (전체 조회만 참, 거래 유형이 거래마다 달라서)')
    ] = False
    dropped_candidates: Annotated[
        int,
        Field(exclude=True, description=(
            '평형 후보 목록(areaInfos)에서 뺀 빈 항목(null) 수. 0 보다 크면 후보 수를 몰라 pyeong_name 은 null 이고, '
            '후보가 하나만 남아도 pyeong_names 키를 지우지 않는다. 결과의 안내(notes)를 만드는 데 쓴다'
        ))
    ] = 0

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
        Field(description=(
            '평형 이름 (공급면적 평 기준, 예: 34A). 후보가 여럿이면 "32A 외 4" '
            '(같은 전용면적의 평형이 여럿이라 어느 평형인지 직방도 모른다). 직방이 후보를 주지 않거나 첫 후보의 평 이름을 주지 않거나 '
            '빈 항목을 줘 셀 수 없으면 null (후보는 pyeong_names)'
        ))
    ] = None
    pyeong_names: Annotated[
        list[str | None] | None,
        Field(description=(
            '평형 후보 이름 전부 (응답 순서, 직방이 평 이름을 주지 않은 후보는 null). 후보가 하나면 키가 없고, 직방이 후보를 주지 않으면 null. '
            '직방이 후보 목록에 빈 항목을 줘 뺐으면 받은 후보만 담고 하나여도 키를 둔다 (후보가 정말 하나인지 알 수 없다)'
        ))
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
    dong: Annotated[
        str | None,
        Field(description="동 ('132' 처럼 '동' 없이 직방 글자 그대로, 모든 거래). 직방이 주지 않으면 null (지금까지 본 전월세는 늘 null)")
    ] = None
    registered: Annotated[
        bool | None,
        Field(description=(
            '등기까지 마무리된 거래 (매매만). 직방은 2023년 1월 이후 계약만 표시하고 등기된 것에만 값을 줘서, 표시가 없으면 '
            '2023년 이전 계약인지 아직 등기 전인지 알 수 없어 false 가 아니라 null. 전월세는 키가 없다'
        ))
    ] = None
    new_high: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 높은 거래가를 경신한 신고가 거래 (매매·전세). 직방이 표시하지 않은 거래는 false. 단지 전체 최고가와 견준 값이 아니다. 월세는 키가 없다')
    ] = None
    new_low: Annotated[
        bool | None,
        Field(description='최근 3년 이내 가장 낮은 거래가를 경신한 신저가 거래 (매매·전세). 표시 규칙은 new_high 와 같다. 월세는 키가 없다')
    ] = None
    price_per_pyeong_manwon: Annotated[
        int | None,
        Field(description='공급면적 3.3㎡당 가격 (만원 정수). 직방이 계산해 만원으로 반올림한 값을 그대로 낸다 (매매만, 직방이 주지 않으면 null). 전월세는 키가 없다')
    ] = None
    jeonse_ratio: Annotated[
        float | None,
        Field(description=(
            '전세가율 (0~1 비율, 반올림하지 않은 직방 값. 웹은 정수 % 로 반올림해 보여 준다). 분모는 그 달 직방 시세다 (실거래 평균이 아님). '
            '전세이고 직방이 값을 준 거래에만 키가 있다 (평형을 지정한 조회에서만 온다)'
        ))
    ] = None
    offer_price_diff_manwon: Annotated[
        int | None,
        Field(description='분양가 대비 차액 (만원 정수, 양수면 거래가가 분양가보다 높고 0·음수도 그대로). 분양권 거래에 있고 직방이 주지 않으면 null. 분양권이 아닌 거래(입주권 포함)는 직방이 값을 주지 않으면 키가 없다')
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
        # 등기·평당가는 직방이 매매에만 주고(동은 웹이 전월세에도 그려 모든 거래에 낸다), 신고가·신저가는 월세에는 주지 않는다. 전세가율은 전세에 값이 있을 때만 키를 둔다.
        # 분양가 대비 차액은 분양권이면 값이 없어도 모름(null)으로 키를 두고, 그 밖에는 값이 있을 때만 둔다
        if self.trade_type != '매매':
            fields |= {'registered', 'price_per_pyeong_manwon'}
        if self.trade_type == '월세':
            fields |= {'new_high', 'new_low'}
        if self.trade_type != '전세' or self.jeonse_ratio is None:
            fields.add('jeonse_ratio')
        if self.offer_price_diff_manwon is None and self.presale != '분양권':
            fields.add('offer_price_diff_manwon')
        # 후보가 하나면 해당 없음이라 키를 지운다. 후보를 주지 않았으면(None) 모름이라 null 로 둔다. 빈 항목을 뺐으면 하나인지 알 수 없어 둔다
        if self.pyeong_names is not None and len(self.pyeong_names) == 1 and not self.dropped_candidates:
            fields.add('pyeong_names')
        for field in fields:
            data.pop(field, None)
        if self.show_trade_type:
            data = {'trade_type': self.trade_type, **data}
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


def rt_price_to_real_price(transaction: ZigbangRtPriceModel, *, show_trade_type: bool = False) -> ZigbangRealPrice | None:
    """실거래 한 건을 `ZigbangRealPrice` 로 바꾼다. 거래 유형을 모르면 None. `show_trade_type` 이면 거래마다 유형을 낸다."""
    trade_type = TRADE_BY_RT_DEAL_TYPE.get(transaction.deal_type or '')
    if trade_type is None:
        return None
    is_sale = trade_type == '매매'
    # 실거래 신고에는 전용면적만 있어 같은 전용면적의 평형이 여럿이면 직방이 후보를 모두 준다. 웹은 첫 후보의 ㎡ 이름과 나머지
    # 후보 수로 '107A㎡외4' 처럼 보여 준다. areaInfos 전부를 후보로 세고 평 이름이 빈 후보 자리는 모름(None)으로 남겨, 수와
    # 첫 후보를 웹(getTypeOrPrice·getType)과 맞춘다. 후보가 없으면(빈 목록) 직방이 후보를 주지 않은 것이라 pyeong_names 는 null
    names = [info.p or None for info in transaction.area_infos]
    # 후보 목록에서 빈 항목(null)을 뺐으면 후보 수를 몰라 '외 N' 을 만들지 않는다. 받은 후보(pyeong_names)는 그대로 낸다
    dropped = transaction.null_items('area_infos')
    return ZigbangRealPrice(
        trade_type=trade_type,
        show_trade_type=show_trade_type,
        dropped_candidates=dropped,
        trade_date=rt_deal_date(transaction.deal_date),
        area_m2=transaction.area_m2,
        pyeong_name=None if dropped else (
            (f'{names[0]} 외 {len(names) - 1}' if len(names) > 1 else names[0]) if names and names[0] else None
        ),
        pyeong_names=names or None,
        # 매물 목록·상세(Listing 검증기)와 당근 실거래가처럼 지하층을 '지하1' 로 맞춘다
        floor=None if transaction.floor is None else normalize_floor(str(transaction.floor)),
        price_manwon=transaction.price if is_sale else None,
        deposit_manwon=None if is_sale else transaction.price,
        rent_manwon=transaction.price_rent if trade_type == '월세' else None,
        category=REAL_PRICE_CATEGORY_BY_METHOD.get(transaction.method or '', transaction.method),
        cancelled=transaction.is_cancellation,
        presale=transaction.offer_type or None,
        dong=transaction.dong_name or None,
        # 직방은 등기·신고가·신저가를 참일 때만 값을 준다. 신고가·신저가는 표시가 없으면 아닌 것이지만(false), 등기는
        # 표시가 없는 이유를 알 수 없어 null 로 둔다 (2023년 이전 계약이거나 아직 등기 전)
        registered=True if transaction.is_registration else None,
        new_high=bool(transaction.is_new_highest),
        new_low=bool(transaction.is_new_lowest),
        price_per_pyeong_manwon=transaction.pyn_price,
        jeonse_ratio=transaction.charter_rate,
        offer_price_diff_manwon=transaction.offer_price_diff,
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
    trade_type: RealPriceTradeType = '매매',
    pyeong_id: int | None = None,
    limit: int = 120,
) -> ZigbangRealPriceResult:
    """아파트 단지(또는 평형 하나)의 실거래가를 최근 계약 순으로 `limit` 건 모은다.

    직방은 전세·월세를 한데 묶어 줘서(`rent`), 한쪽만 고르면 받은 뒤에 거르고 쪽을 더 넘긴다.
    '전체' 는 직방이 매매와 전월세를 계약일 최신 순으로 합쳐 주는 순서 그대로(`all`) 낸다 (거래마다 유형을 붙인다).
    거래 유형을 모르는 거래(`rtDealType` 이 모르는 값·null·없음)는 어느 조회에서든 빼고 `[제외]` 로 알린다
    (`--limit` 에서 이미 잘린 뒤의 거래는 어차피 보이지 않아 세지 않는다).
    `REAL_PRICE_MAX_PAGES` 쪽(최근 1200건)에서 멈추고, 그래도 모자라면 본 범위를 `notes` 로 알린다.
    갱신 계약 여부는 직방이 주지 않는다. 거래 목록·평형 후보 목록(`areaInfos`)에 빈 항목(null)이 섞여 오면 빼고 읽고 `[제외]` 로 알린다
    (후보에서 뺐으면 후보 수를 몰라 `pyeong_name` 은 null).

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
    all_types = trade_type == '전체'
    transactions: list[ZigbangRealPrice] = []
    has_next = False
    unknown = 0
    # 쪽의 거래 목록에서 뺀 빈 항목(null) 수 (받은 쪽 전부의 합)
    dropped_transactions = 0
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
        dropped_transactions += response.null_items('transactions')
        for transaction in response.transactions:
            real_price = rt_price_to_real_price(transaction, show_trade_type=all_types)
            if real_price is None:
                # 이미 limit 건을 모았으면 이 거래는 어차피 잘려 안 보일 자리라 세지 않는다
                if len(transactions) < limit:
                    unknown += 1
            elif all_types or real_price.trade_type == trade_type:
                transactions.append(real_price)
        # 빈 항목만 온 쪽을 빈 쪽으로 보고 멈추지 않는다
        if not has_next or not (response.transactions or response.null_items('transactions')):
            break
    notes: list[str] = []
    if deal_type == 'rent' and has_next and len(transactions) < limit:
        # 몇 건 중에서 골랐는지 설명이라 [참고] 다. 더 있다는 [일부] 는 아래 안내 하나 (2026-11-10 실측: 헬리오시티 월세
        # --limit 1200 에 '최근 거래 1200건 중 월세만' [참고] 과 '직방에서 직접 확인' [일부])
        notes.append(note(
            '참고',
            f'직방은 전세·월세를 함께 줘서 최근 거래 {page * REAL_PRICE_PAGE_SIZE}건 중 {trade_type}만 골랐습니다. '
            '더 오래된 거래는 보지 않았습니다',
        ))
    if all_types:
        notes.append(note(
            '참고',
            '매매와 전월세를 계약일 최신 순으로 합친 목록입니다 (거래마다 trade_type). '
            '전월세가 많은 단지는 앞쪽이 전월세뿐일 수 있으니 매매만 보려면 --trade 매매',
        ))
    has_more = has_next or len(transactions) > limit
    filled = len(transactions) >= limit
    transactions = transactions[:limit]
    url = apt_danji_url(number)
    if not has_more:
        notes.append(note('참고', '직방이 주는 실거래를 끝까지 받았습니다'))
    elif filled and page < REAL_PRICE_MAX_PAGES:
        # --limit 에서 멈췄으면 늘려서 더 받을 수 있다. 직방에서 직접 보라는 안내는 쪽 상한까지 보고도 남았을 때만 맞다.
        # 당근 `_collect_pages` 와 달리 `limit < REAL_PRICE_MAX_LIMIT` 는 보지 않는다. 직방은 요청한 수만큼만 줘서 --limit 1200
        # 은 24쪽째에야 차 위 조건(page < 24)에서 이미 빠진다 (2026-11-11 리뷰·실측: 헬리오시티 apt-38487 매매 limit 10·50·100
        # 이 10·50·100건, 전월세 limit 50 이 50건)
        notes.append(note(
            '일부',
            '더 조회할 실거래가가 있습니다. '
            f'--limit 을 늘리면 (최대 {REAL_PRICE_MAX_LIMIT}건) 더 오래된 거래까지 받습니다',
        ))
    else:
        notes.append(note('일부', f'더 조회할 실거래가가 있습니다. 더 오래된 거래는 직방에서 직접 확인하세요: {url}'))
    if unknown:
        notes.append(note('제외', f'거래 유형을 읽지 못한 실거래 {unknown}건을 뺐습니다. {UPDATE_MAYBE_NEEDED}'))
    if dropped_transactions:
        notes.append(null_items_note('직방 실거래', dropped_transactions))
    if dropped_candidates := sum(transaction.dropped_candidates for transaction in transactions):
        notes.append(null_items_note('직방 실거래 평형 후보', dropped_candidates, ('pyeong_name',)))
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
