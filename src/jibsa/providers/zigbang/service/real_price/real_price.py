"""아파트 실거래가의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""

from datetime import datetime

from jibsa.core.dates import (
    KST,
    read_date,
)
from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    floor_text,
    rescale,
)
from jibsa.core.notes import (
    UPDATE_MAYBE_NEEDED,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.real_price import (
    ZigbangDanjisRoomTypesRtPricesRequestParameterModel,
    ZigbangDanjisRtPricesRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.response.real_price import (
    ZigbangDanjisRtPricesResponseModel,
    ZigbangRtPriceModel,
)
from jibsa.providers.zigbang.service.common.constants import APT_DANJI_URL
from jibsa.providers.zigbang.service.common.danji import (
    fetch_danji,
)
from jibsa.providers.zigbang.service.common.ids import (
    parse_complex_id,
)
from jibsa.providers.zigbang.service.real_price.constants import (
    REAL_PRICE_CATEGORY_BY_METHOD,
    REAL_PRICE_DEAL_TYPE_BY_TRADE,
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_MAX_PAGES,
    REAL_PRICE_PAGE_SIZE,
    RT_DEAL_DATE_PATTERN,
    TRADE_BY_RT_DEAL_TYPE,
    RealPriceTradeType,
)
from jibsa.providers.zigbang.service.real_price.models import (
    ZigbangRealPrice,
    ZigbangRealPriceResult,
)


def rt_deal_date(value: str | None) -> str | None:
    """직방 계약일 '26. 9. 8' 을 2026-09-08 로 바꾼다. 두 자리 연도는 올해 이후면 1900년대로 본다.

    날짜로 읽지 못하면(꼴이 다르거나 달력에 없는 날) None 이고 원래 글자를 [참고] 로 알린다 (`read_date`).
    """
    if value is None:
        return None
    text = value.strip()
    match = RT_DEAL_DATE_PATTERN.match(text)
    if match is None:
        return read_date(text, '계약일')
    year, month, day = (int(part) for part in match.groups())
    if year < 100:
        this_year = datetime.now(KST).year
        year += 2000 if 2000 + year <= this_year + 1 else 1900
    return read_date(f'{year:04d}{month:02d}{day:02d}', '계약일', raw=text)


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
        floor=floor_text(transaction.floor),
        price_manwon=transaction.price if is_sale else None,
        deposit_manwon=None if is_sale else transaction.price,
        rent_manwon=transaction.price_rent if trade_type == '월세' else None,
        deal_type=REAL_PRICE_CATEGORY_BY_METHOD.get(transaction.method or '', transaction.method),
        cancelled=transaction.is_cancellation,
        presale=transaction.offer_type or None,
        building_dong=transaction.dong_name or None,
        # 직방은 등기·신고가·신저가를 참일 때만 값을 준다. 신고가·신저가는 표시가 없으면 아닌 것이지만(false), 등기는
        # 표시가 없는 이유를 알 수 없어 null 로 둔다 (2023년 이전 계약이거나 아직 등기 전)
        registered=True if transaction.is_registration else None,
        new_high=bool(transaction.is_new_highest),
        new_low=bool(transaction.is_new_lowest),
        price_per_pyeong_manwon=transaction.pyn_price,
        jeonse_ratio_percent=rescale(transaction.charter_rate, '100'),
        presale_price_diff_manwon=transaction.offer_price_diff,
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
    # 고른 거래 (받은 꼴 그대로). --limit 에서 자른 뒤에 출력 꼴로 바꾼다 (아래 `transactions`)
    kept: list[ZigbangRtPriceModel] = []
    has_next = False
    unknown = 0
    # 쪽의 거래 목록에서 뺀 빈 항목(null) 수 (받은 쪽 전부의 합)
    dropped_transactions = 0
    page = 0
    while len(kept) < limit and page < REAL_PRICE_MAX_PAGES:
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
            # 없는 단지·평형이면 0건 대신 에러로 알린다. 실거래 API 는 없는 단지에도 빈 성공을 준다.
            # 없는 단지는 평형 정보가 비어 오고, 거래가 없는 단지도 평형 정보는 온다 (2026-10-10 실측: 없는 단지 2곳
            # 0개, 실제 단지 3곳 8~30개, 2028년 입주 예정 단지 8개). 평형을 지정해도 단지 전체 평형이 온다.
            # 평형이 아직 없는 새 단지일 수도 있어, 비었을 때만 단지 정보로 있는지 확인한다 (요청 1회, 없으면 NOT_FOUND)
            if not response.pyeongs:
                fetch_danji(client, complex_id, number)
            elif pyeong_id is not None and str(pyeong_id) not in response.pyeongs:
                raise JibsaError(
                    code='INVALID_ARGUMENT',
                    message=f'{complex_id} 단지에 없는 평형 ID 입니다: {pyeong_id}',
                    hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 --pyeong 에 주세요',
                )
        page += 1
        has_next = response.has_next
        dropped_transactions += response.null_items('transactions')
        for transaction in response.transactions:
            # 거래 유형은 `rt_price_to_real_price` 와 같은 표로 가린다
            transaction_trade = TRADE_BY_RT_DEAL_TYPE.get(transaction.deal_type or '')
            if transaction_trade is None:
                # 이미 limit 건을 모았으면 이 거래는 어차피 잘려 안 보일 자리라 세지 않는다
                if len(kept) < limit:
                    unknown += 1
            elif all_types or transaction_trade == trade_type:
                kept.append(transaction)
        # 빈 항목만 온 쪽을 빈 쪽으로 보고 멈추지 않는다
        if not has_next or not (response.transactions or response.null_items('transactions')):
            break
    notes: list[str] = []
    if deal_type == 'rent' and has_next and len(kept) < limit:
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
    has_more = has_next or len(kept) > limit
    filled = len(kept) >= limit
    # 잘려 안 보일 거래까지 바꾸면 그 계약일을 못 읽은 날짜 안내([참고], `rt_deal_date`)에 세어 건수가 출력과 어긋난다.
    # 거래 유형을 위에서 가렸으므로 None 은 나오지 않는다
    transactions = [
        real_price for transaction in kept[:limit]
        if (real_price := rt_price_to_real_price(transaction, show_trade_type=all_types)) is not None
    ]
    url = APT_DANJI_URL.format(number)
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
        trades=transactions,
        url=url,
        notes=notes,
    )
