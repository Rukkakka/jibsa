"""매물 상세 (listing)."""

from httpx import HTTPStatusError
from pydantic import Field

from jibsa.core.errors import ListingUnavailableError
from jibsa.core.listing import (
    ListingDetail,
    ListingT,
    listing_as,
    move_in_label,
    parking_label,
    won_to_manwon,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.listing import (
    DaangnArticlesRequestParameterModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnManageCostOptionModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.api.response.listing import DaangnArticlesResponseModel
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    MONTHLY_TRADES,
    TRADE_TYPE_BY_TRADE,
    article_to_listing,
    is_available,
    station_name,
    trades_preferred_first,
)

from typing import Annotated


# --details 로 상세를 붙이는 매물 수. 한 건에 요청 1회라 목록이 길면 오래 걸린다
DETAILS_MAX: int = 30
OPTION_LABELS: dict[str, str] = {
    'PARKING': '주차',
    'WASHER': '세탁기',
    'AIRCON': '에어컨',
    'GAS_RANGE': '가스레인지',
    'INDUCTION': '인덕션',
    'ELEC_RANGE': '전기레인지',
    'FRIDGE': '냉장고',
    'REFRIGERATOR': '냉장고',
    'BED': '침대',
    'CLOSET': '옷장',
    'ELEVATOR': '엘리베이터',
    'PET': '반려동물',
    'BALCONY': '베란다',
    'MICROWAVE': '전자레인지',
    'TV': 'TV',
    'DESK': '책상',
    # 융자(근저당)가 아니라 전세자금대출 가능 여부다. 당근 웹은 필터에서 '대출 가능', 상세 JSON-LD 에서
    # mortgageAvailable(가능/불가능)로 보여 주고, YES 매물 본문에는 '전세자금대출 가능' 이라고 적혀 있다.
    # 시설은 아니지만 YES 일 때 알려야 하는 항목. README 가 options 에 섞여 나온다고 안내한다
    'MORTGAGE': '대출 가능',
    # MORTGAGE 처럼 시설이 아니라 YES 일 때 알릴 항목. 당근 웹 상세의 '전입신고 | 가능' 칸이다 (2026-10-24 실측: 4437264 가
    # MOVE_IN_REGISTRATION=YES 이고 페이지에 '전입신고 가능'. 이름표가 없어 영어 코드 그대로 options 에 나갔다)
    'MOVE_IN_REGISTRATION': '전입신고 가능',
}
DIRECTION_LABELS: dict[str, str] = {
    'SOUTH_FACING': '남향',
    'NORTH_FACING': '북향',
    'EAST_FACING': '동향',
    'WEST_FACING': '서향',
    'SOUTH_EAST_FACING': '남동향',
    'SOUTH_WEST_FACING': '남서향',
    'NORTH_EAST_FACING': '북동향',
    'NORTH_WEST_FACING': '북서향',
}
# 관리비 항목 (당근 웹 표기에서 '료'·'비' 를 뗐다. 직방 manage_cost_includes 의 '수도'·'전기'·'가스' 와 맞춘다)
MANAGE_COST_OPTION_LABELS: dict[str, str] = {
    'COMMON': '공용',
    'ELECTRIC': '전기',
    'WATERWORKS': '수도',
    'GAS': '가스',
    'BOILER': '난방',
    'INTERNET': '인터넷',
    'TV': 'TV',
    'PARKING': '주차',
    'CLEANING': '청소',
    'ELEVATOR': '승강기',
    'ETC': '기타',
}


class DaangnListingDetail(ListingDetail):
    """상세 페이지로 보강한 당근 매물.

    `key_money_manwon`·`key_money_negotiable` 은 상가에만, `broker_fee_manwon` 은 중개사 매물에만 있다
    (그 밖에는 키를 뺀다). 권리금 설명 글(`premiumMoneyDescription`)은 작성자가 쓴 자유 글이라 옮기지 않는다.
    """

    other_trades: Annotated[
        list[str],
        Field(description='보여 주는 조건 외에 함께 올라온 거래 조건 (만원, 예: 전세 20000)')
    ] = []
    manage_cost_excludes: Annotated[
        list[str] | None,
        Field(description='관리비와 따로 내는 항목 (쓴 만큼 내는 전기·수도 등). 소스가 알려 주지 않으면 null')
    ] = None
    key_money_manwon: Annotated[
        float | None,
        Field(description='권리금 (만원, 상가만)')
    ] = None
    key_money_negotiable: Annotated[
        bool | None,
        Field(description='권리금 협의 가능 여부 (상가만). true 면 권리금 금액은 참고용이다')
    ] = None
    broker_fee_manwon: Annotated[
        float | None,
        Field(description='보여 주는 거래 조건의 중개보수 (만원, 부가세 포함). 당근이 법정 상한 요율로 계산한 값이다')
    ] = None
    watch_count: Annotated[
        int | None,
        Field(description='당근에서 이 매물을 관심 목록에 넣은 사람 수')
    ] = None
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (daangn complex 에 넘긴다). 아파트·오피스텔 등 단지 매물만')
    ] = None
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='단지 종류 (아파트, 오피스텔, 주상복합 ...). property_type 은 작성자가 고른 매물 종류라 다를 수 있다')
    ] = None
    direct_deal: Annotated[
        bool,
        Field(exclude=True, description='직거래 매물인지. 중개보수가 해당 없는지 가리는 데만 쓴다')
    ] = False

    def not_applicable_fields(self) -> frozenset[str]:
        fields = super().not_applicable_fields()
        if self.property_type != '상가' and self.key_money_manwon is None:
            fields = fields | {'key_money_manwon', 'key_money_negotiable'}
        if self.direct_deal:
            fields = fields | {'broker_fee_manwon'}
        if self.complex_id is None:
            fields = fields | {'complex_id', 'complex_name', 'complex_type'}
        return fields


def _describe_trade(trade: DaangnTradeModel) -> str:
    """거래 조건 한 줄 표기 ('월세 500/50').

    당근은 거래 유형마다 금액을 늘 주어 None 을 따로 다루지 않는다 (2026-10-11 실측: 역삼역·신림역·오산역 주변 매물
    580건의 거래 600개 모두 매매가·보증금·월세가 있었다).
    """
    label = TRADE_TYPE_BY_TRADE.get(trade.type, trade.type)
    if trade.type == 'BUY':
        return f'{label} {trade.price}'
    if trade.type in MONTHLY_TRADES:
        return f'{label} {trade.deposit}/{trade.monthly_pay}'
    return f'{label} {trade.deposit}'


def _nearby_subways(article: DaangnArticleModel) -> list[str]:
    """도보 시간이 붙은 `subwayStations` 를 쓰고, 비어 있으면 이름뿐인 `nearbySubwayStations` 로 채운다.

    상세 페이지에서 `subwayStations` 가 비고 `nearbySubwayStations` 에만 역이 있는 매물이 있다
    (2026-10 실측). 뒤쪽은 '역' 없이 오므로 ('역삼') 앞쪽 표기('역삼역')에 맞춰 붙인다.
    """
    stations = [
        f'{item.station.station_name} (도보 {item.duration_minutes}분)'
        if item.duration_minutes is not None else item.station.station_name
        for item in article.subway_stations
        if item.station and item.station.station_name
    ]
    if stations:
        return stations
    names = [
        edge.node.station_name
        for edge in article.nearby_subway_stations
        if edge.node and edge.node.station_name
    ]
    return [station_name(name) for name in dict.fromkeys(names)]


def _manage_cost_label(option: DaangnManageCostOptionModel) -> str:
    if option.option == 'ETC' and option.custom_option_name:
        return option.custom_option_name
    return MANAGE_COST_OPTION_LABELS.get(option.option, option.option)


def _manage_cost_items(article: DaangnArticleModel) -> tuple[list[str] | None, list[str] | None]:
    """관리비에 포함된 항목과 따로 내는 항목. 소스가 알려 주지 않으면 (None, None).

    중개사 매물은 항목마다 정액(FIXED, 관리비에 포함)·쓴 만큼(USED, 따로 냄)을 밝히고, 없음(NONE)·
    확인 필요(NEED_TO_CHECK)는 어느 쪽에도 넣지 않는다. 항목을 밝히지 않은 매물
    (`manageCostDetailIsDisclosed: false`)도 껍데기 항목이 오므로 모름으로 둔다. 직거래 매물은
    포함 항목 목록과 미포함 항목 목록(`excludeManageCostOption`)을 따로 준다.
    """
    options = article.manage_cost_options
    if options is None or article.manage_cost_detail_is_disclosed is False:
        return None, None
    if article.manage_cost_charge_type is not None:
        includes = [_manage_cost_label(item) for item in options if item.pay_option == 'FIXED']
        excludes = [_manage_cost_label(item) for item in options if item.pay_option == 'USED']
        return includes, excludes
    excludes = [MANAGE_COST_OPTION_LABELS.get(code, code) for code in article.exclude_manage_cost_options or []]
    return [_manage_cost_label(item) for item in options], excludes


def _broker_fee_manwon(article: DaangnArticleModel, trade: DaangnTradeModel) -> float | None:
    """보여 주는 거래 조건의 중개보수 (부가세 포함, 만원)."""
    commission = next(
        (item for item in article.broker_commissions or [] if item.trade_type == trade.type),
        None,
    )
    return won_to_manwon(commission.total) if commission else None


def detail_to_listing(
    response: DaangnArticlesResponseModel,
    trade_type: str | None = None,
) -> DaangnListingDetail:
    """상세 페이지 결과를 `DaangnListingDetail` 로 바꾼다.

    사진·본문·중개사 정보·도로명 주소는 옮기지 않는다 (원 사이트에서 확인).

    거래 조건이 여러 개인 매물(예: 매매 + 월세)은 기본으로 대표 조건을 보여 준다. 목록은 필터를
    통과한 조건으로 내보내므로(월세로 찾으면 월세), `trade_type` 으로 그 조건을 골라 목록과 같은
    가격을 보여 준다. 나머지 조건은 `other_trades` 로 간다.

    Raises:
        ListingUnavailableError: 거래 완료·예약·숨김·노출 제한 매물이거나, 아는 거래 조건
            (월세·전세·매매·단기임대)이 없을 때 (reason NO_TRADE_INFO). 목록에서 빠지는 매물과 같다.
            `trade_type` 조건이 없으면 reason TRADE_NOT_OFFERED 이고 `offered_trades` 에 있는 조건을 싣는다.
    """
    article = response.article
    if not is_available(article):
        # 노출 제한은 `invisibleReason` 대신 `invisibleInfos` 로만 올 수 있어 그 종류(`__typename`)도 사유로 쓴다. 없으면 진행 중
        # 매물이 왜 안 되는지 사유가 null 로 나갔다
        restriction = next(
            (str(info['__typename']) for info in article.invisible_infos or [] if info.get('__typename')), None,
        )
        raise ListingUnavailableError(
            'daangn',
            article.original_id,
            status=article.status,
            reason=article.invisible_reason or restriction or ('HIDDEN' if article.is_hide else None),
        )
    trades = trades_preferred_first(article)
    trade = trades[0] if trades else None
    if trade_type is not None and trades:
        trade = next((item for item in trades if TRADE_TYPE_BY_TRADE[item.type] == trade_type), None)
        if trade is None:
            error = ListingUnavailableError(
                'daangn', article.original_id, status=article.status, reason='TRADE_NOT_OFFERED'
            )
            error.details['offered_trades'] = [_describe_trade(item) for item in trades]
            raise error
    base = article_to_listing(article, fallback_title=response.title, trade=trade)
    if base is None:
        raise ListingUnavailableError('daangn', article.original_id, status=article.status, reason='NO_TRADE_INFO')
    # 거래 조건이 없으면 article_to_listing 이 None 을 줘 위에서 끝났다
    assert trade is not None

    option_values = {option.name: option.value for option in article.options}

    parking = None
    # 주차 대수를 먼저 봐도 작성자가 불가(NO)로 올린 매물을 가능으로 바꾸지 않는다. 불가인데 대수가 있는 매물은 보지 못했다
    # (2026-10-18 실측: 역삼동 상세 12건 중 YES 11건(대수 있음 9건), NO 1건(대수 없음)). 2026-10-18 리뷰 오탐 확인
    if option_values.get('PARKING') == 'YES' or (article.available_total_parking_spots or 0) > 0:
        spots = article.available_total_parking_spots
        parking = parking_label(True, f'{spots}대' if spots else None)
    elif option_values.get('PARKING') == 'NO':
        parking = parking_label(False)

    elevator = None
    if option_values.get('ELEVATOR') in ('YES', 'NO'):
        elevator = option_values['ELEVATOR'] == 'YES'

    move_in = move_in_label(article.move_in_date, negotiable=bool(article.move_in_date_negotiable))

    manage_cost_includes, manage_cost_excludes = _manage_cost_items(article)
    direct_deal = article.writer_type is not None and article.writer_type != 'BROKER'

    return listing_as(
        DaangnListingDetail,
        base,
        room_count=article.room_count,
        bathroom_count=article.bathroom_count,
        direction=DIRECTION_LABELS.get(article.building_orientation or '', article.building_orientation),
        move_in=move_in,
        parking=parking,
        elevator=elevator,
        # 상세 SSR 에는 options·subwayStations·nearbySubwayStations 키가 늘 있어 빈 목록은 '모름'(null) 이 아니라 '없음' 이다
        # (2026-10-11 실측: 원룸·아파트·상가·토지·공장·주택 8건 모두 키 있음. 상가·토지·공장은 options 가 빈 목록)
        options=[
            OPTION_LABELS.get(name, name)
            for name, value in option_values.items()
            if value == 'YES' and name not in ('PARKING', 'ELEVATOR')
        ],
        manage_cost_includes=manage_cost_includes,
        manage_cost_excludes=manage_cost_excludes,
        nearby_subways=_nearby_subways(article),
        key_money_manwon=article.premium_money,
        key_money_negotiable=article.premium_money_negotiable,
        broker_fee_manwon=None if direct_deal else _broker_fee_manwon(article, trade),
        watch_count=article.watch_count,
        complex_id=article.complex.original_id if article.complex else None,
        complex_name=article.complex.name if article.complex and article.complex.original_id else None,
        complex_type=(
            COMPLEX_TYPE_LABELS.get(article.complex.type or '', article.complex.type)
            if article.complex and article.complex.original_id else None
        ),
        direct_deal=direct_deal,
        other_trades=[
            _describe_trade(item)
            for item in article.trades
            if item is not trade and item.type in TRADE_TYPE_BY_TRADE
        ],
    )


def get_listing(
    client: DaangnClient,
    original_id: int,
    trade_type: str | None = None,
) -> DaangnListingDetail:
    """매물 하나의 상세를 조회한다. `trade_type` 은 보여 줄 거래 조건 (`detail_to_listing`)."""
    try:
        response = client.run_request_articles(
            DaangnArticlesRequestParameterModel(original_id=original_id)
        )
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ListingUnavailableError('daangn', original_id) from None
        raise
    return detail_to_listing(response, trade_type)


def attach_details(client: DaangnClient, listings: list[ListingT]) -> tuple[list[ListingT], list[str]]:
    """목록 매물마다 상세를 1회씩 받아 목록에 없는 관리비·등록일·번지 주소·사용승인일·방 구조를 채운다 (`--details`).

    당근 목록은 관리비·등록일·번지를 주지 않아 `null` 이고, 방 구조도 원룸만 붙는다. 앞 `DETAILS_MAX` 건만 보고, 상세에서
    거래가 끝난 매물은 뺀다 (만료 매물은 내보내지 않는다).

    Returns:
        (채운 매물, 안내).
    """
    kept: list[ListingT] = []
    gone = 0
    for index, listing in enumerate(listings):
        if index >= DETAILS_MAX:
            kept.append(listing)
            continue
        try:
            detail = get_listing(client, int(listing.id), listing.trade_type)
        except ListingUnavailableError:
            gone += 1
            continue
        kept.append(listing.model_copy(update={
            'manage_cost_manwon': detail.manage_cost_manwon,
            'registered_at': detail.registered_at,
            'address': detail.address,
            'approved_at': detail.approved_at,
            'room_type': detail.room_type,
        }))
    notes = []
    if gone:
        # 검색이 만든 안내('이 N건이 전부입니다' 등)는 빼기 전 개수라 returned 와 다를 수 있다
        notes.append(f'{gone}건은 상세를 보니 거래가 끝나 뺐습니다 (앞 안내의 건수는 빼기 전 기준)')
    if len(listings) > DETAILS_MAX:
        notes.append(f'상세(--details)는 앞 {DETAILS_MAX}건에만 붙였습니다')
    return kept, notes
