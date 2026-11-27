"""당근 매물 카드 변환·거래 선택·노출 판정과 조건 안내 문구."""

from collections.abc import Iterable

from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    NEXT_HINT,
    Listing,
    join_address,
    m2_to_pyeong,
    more_hint,
    note,
    read_date,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnArticleModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.service.common.constants import (
    AMBIGUOUS_FLOOR_LABELS,
    ARTICLE_URL,
    COMPLEX_TYPE_LABELS,
    LISTING_STATUS_BY_STATUS,
    MONTHLY_TRADES,
    PROPERTY_TYPE_BY_SALES_TYPE,
    ROOM_SALES_TYPES,
    ROOM_TYPE_BY_SALES_TYPE,
    TRADE_FILTER_BY_TRADE_TYPE,
    TRADE_TYPE_BY_TRADE,
    TRADE_TYPES,
)
from jibsa.providers.daangn.service.common.models import (
    DaangnListingConditions,
    DaangnNearbyListing,
)
from jibsa.providers.daangn.service.common.response import code_label


def is_available(article: DaangnArticleModel) -> bool:
    """내보낼 매물인지. 판매중(ON_GOING)이나 예약중(RESERVED)이고 숨김·노출 제한이 없어야 한다.

    거래완료(TRADED)는 만료 매물이라 뺀다. 예약중은 계약이 깨질 수 있어 당근 웹처럼 보여 주고 `status` 로 알린다 (2026-11-11
    사용자 결정). 숨김(작성자가 내림)과 노출 제한(당근이 막음)은 웹 상세도 매물 대신 안내 문구를 보여 주는 매물이다. 노출 제한은
    SSR 스토어에는 `invisibleReason`, GraphQL 피드에는 `invisibleInfos` 로 온다.

    비활성 중개소 매물은 여기서 보지 않는다. 목록 카드의 `bizProfile` 에는 중개소 상태가 없고(id·badges 만) 상세 SSR 에만
    `status` 가 있다 (2026-11-11 실측). 당근 웹도 목록에는 그 매물을 그대로 보여 주고 상세에서만 "비활성화된 중개소의
    매물이에요" 로 막아, jibsa 도 웹처럼 상세(`listing`·`--details`)에서만 막는다 (`listing.listing.detail_to_listing`). 목록에서 막으려면
    매물마다 상세를 받아야 해 요청이 매물 수만큼 늘고 웹과도 달라진다 (2026-11-11 사용자 결정).
    """
    return (
        article.status in LISTING_STATUS_BY_STATUS
        and not article.is_hide
        and article.invisible_reason is None
        and not article.invisible_infos
    )


def trades_preferred_first(article: DaangnArticleModel) -> list[DaangnTradeModel]:
    """jibsa 가 아는 거래(`TRADE_TYPE_BY_TRADE`)를 대표(preferred) 거래 먼저 세운다.

    웹 목록(`services2` 의 `Fo`)의 후보 BORROW·BUY·MONTH·SHORT·YEAR 와 같다. 예전에는 제주 연세(YEAR)를 표현하지 않아
    빼서, 연세가 대표인 매물은 웹과 다른 거래를 보여 주고 연세만 있는 매물은 목록에서 빠졌다 (2026-11-13 연세 지원).
    유형(`type`)이 null 인 거래도 모르는 유형처럼 뺀다 (그런 거래만 있는 매물은 `no_trade_notes` 가 알린다).
    """
    known = [trade for trade in article.trades if trade.type in TRADE_TYPE_BY_TRADE]
    return sorted(known, key=lambda trade: not trade.preferred)


def floor_of(article: DaangnArticleModel) -> str | None:
    """해당 층. 작성자가 층을 저층·중층·고층으로만 밝혔으면(숫자 층은 비어 있다) 그 표기를 쓴다.

    저·중·고층 코드가 비었거나 '-' 면(`code_label` 이 None) 숫자 층을 본다 (`FloorText` 가 빈 글자·'-' 를 None 으로 받는다). 둘 다 모르면 None(모름)이다.
    결과는 `Listing.floor` 검증기(`normalize_floor`)가 '-1' → '지하1' 처럼 다시 맞춘다.
    """
    if article.is_ambiguous_floor:
        label = code_label(AMBIGUOUS_FLOOR_LABELS, article.ambiguous_floor)
        if label is not None:
            return label
    return article.floor


def property_type_of(article: DaangnArticleModel) -> str | None:
    """작성자가 고른 매물 유형. `salesTypeV3` 나 그 `type` 이 null·빈 글자·'-' 이면 유형을 모르는 것이라 None(모름)이다. 표에 없는 코드는 원래 코드 그대로."""
    if article.sales_type is None:
        return None
    return code_label(PROPERTY_TYPE_BY_SALES_TYPE, article.sales_type.type)


def room_type_of(article: DaangnArticleModel) -> str | None:
    """방 구조. 방 수를 알면(상세) 유형과 상관없이 방 수로 투룸·쓰리룸·포룸이상을 가리고,
    방 1개거나 방 수를 모르면(목록) 원룸 구조(오픈형·분리형)를 쓴다. 그 밖은 None.

    원룸 카테고리에도 방 2개 매물이 있어 방 수를 먼저 본다 (2026-10-10 실측: 분리형원룸으로 올린 방 2개 매물).
    """
    count = article.room_count
    if count is not None and count >= 2:
        if count == 2:
            return '투룸'
        if count == 3:
            return '쓰리룸'
        return '포룸이상'
    sales_type = article.sales_type.type if article.sales_type else None
    return ROOM_TYPE_BY_SALES_TYPE.get(sales_type or '')


def article_to_listing(
    article: DaangnArticleModel,
    center: tuple[float, float] | None = None,
    fallback_title: str | None = None,
    trade: DaangnTradeModel | None = None,
) -> Listing | None:
    """Article 하나를 공통 `Listing` 으로 바꾼다. 거래 조건이 없거나 모르는 거래 유형(`type` 이 null 이거나 `TRADE_TYPE_BY_TRADE` 에
    없음)이면 None.

    `trade` 를 주지 않으면 대표(preferred) 조건을 쓴다. 금액은 원래 만원 단위다.
    제목은 목록과 상세가 같도록 작성자 소개(`addressInfo`) → 건물 이름 →
    `fallback_title`(상세 페이지의 자동 요약) 순으로 고른다. `center` 를 주면 거리를 재고
    `DaangnNearbyListing` 으로 준다 (거리를 모르면 null).
    """
    if trade is None:
        trades = trades_preferred_first(article)
        trade = trades[0] if trades else None
    trade_type = TRADE_TYPE_BY_TRADE.get(trade.type or '') if trade is not None else None
    if trade is None or trade_type is None:
        return None

    # 주소를 숨긴 매물(isHideAddress)의 공개 좌표는 실제 위치가 아니어서 거리를 재지 않는다 (null, `hidden_location_notes`).
    # 2026-10-28 실측: 강남역 역 주변 100건 중 숨긴 18건은 역까지 도보 1~6분인데 공개 좌표가 역에서 0.35~1.78km, 숨기지 않은
    # 82건은 모두 0.21km 안 (출퇴근 역별 매물 100건도 같은 18:82). 숨긴 매물은 지도 핀에 없고 상세 주소도 동까지만 온다
    coordinate = None if article.is_hide_address else article.public_coordinate
    lat = coordinate.lat if coordinate else None
    lng = coordinate.lon if coordinate else None
    distance = None
    if center is not None and lat is not None and lng is not None:
        distance = round(haversine_km(center[0], center[1], lat, lng), 2)

    region = article.region
    # 지번 주소가 빈 글자·'-' 로 오면 비어 있는 것이라 지역 이름으로 채운다. 지역도 없으면 빈 글자·'-' 가 아니라 모름(None)이다
    address = article.public_jibun_address
    if address is None or address.strip() in ('', '-'):
        address = join_address(region.name1, region.name2, region.name3) if region is not None else None

    model = Listing if center is None else DaangnNearbyListing
    return model(
        source='daangn',
        id=article.original_id,
        url=ARTICLE_URL.format(article.original_id),
        trade_type=trade_type,
        status=LISTING_STATUS_BY_STATUS.get(article.status or ''),
        property_type=property_type_of(article),
        room_type=room_type_of(article),
        title=article.address_info or article.building_name or fallback_title or None,
        price_manwon=trade.price if trade.type == 'BUY' else None,
        deposit_manwon=trade.deposit if trade.type != 'BUY' else None,
        rent_manwon=trade.monthly_pay if trade.type in MONTHLY_TRADES else None,
        # 연세는 월로 나누지 않고 당근 웹 카드('연세 1,000 / 1,400만원')처럼 1년치 그대로 준다
        yearly_rent_manwon=trade.yearly_pay if trade.type == 'YEAR' else None,
        manage_cost_manwon=article.total_manage_cost,
        area_m2=article.area,
        area_pyeong=m2_to_pyeong(article.area),
        floor=floor_of(article),
        building_floor=article.top_floor,
        address=address,
        lat=lat,
        lng=lng,
        distance_km=distance,
        # 지도 피드(목록)에는 날짜 필드가 아예 없어 search 결과는 None 이다. 등록일은
        # 상세 페이지에만 있다. 매물마다 상세를 더 조회하면 동마다 최대 20회 요청이
        # 늘어(약 10초) 목록에서는 채우지 않는다. 필요하면 daangn listing 으로 확인한다.
        registered_date=read_date(article.published_at, '등록일'),
        # 사용승인일도 상세 페이지에만 있어 목록에서는 None 이다.
        approved_date=read_date(article.building_approval_date, '사용승인일'),
    )


def trade_of(article: DaangnArticleModel, conditions: DaangnListingConditions) -> DaangnTradeModel | None:
    """매물 카드에 보여 줄 거래 하나를 당근 웹 목록처럼 고른다 (웹 `services2` 의 `Fo`). 거래 조건이 없으면 None.

    웹은 거래 유형만 보고 금액은 다시 보지 않는다. 거래가 하나면 그것, 검색한 거래 유형(없으면 모든 유형)과 겹치는 거래가
    하나면 그것, 겹치는 거래가 없으면 대표(preferred) 거래, 여럿이면 그중 대표 거래나 첫 거래다. 예전에는 jibsa 가 금액 조건까지
    다시 보고 맞는 거래가 없으면 매물을 뺐는데, 당근 서버가 조건에 맞다고 준 매물을 웹보다 적게 보여 줘 웹처럼 바꿨다 (#215).
    """
    trades = trades_preferred_first(article)
    if not trades:
        return None
    wanted = {TRADE_FILTER_BY_TRADE_TYPE[trade_type] for trade_type in conditions.trade_types or TRADE_TYPES}
    matching = [trade for trade in trades if trade.type in wanted]
    # trades_preferred_first 가 대표 거래를 앞에 두어, 웹 `Fo` 의 갈래(거래 하나, 겹치는 거래 하나·여럿·없음)가 모두 그 목록의
    # 첫 거래다: 겹치는 거래가 있으면 그중 대표 거래나 첫 거래, 없으면 대표 거래 (2026-11-12 리뷰로 한 줄로 줄임)
    return (matching or trades)[0]


def no_trade_notes(articles: Iterable[DaangnArticleModel]) -> list[str]:
    """받은 매물 중 jibsa 가 아는 거래(`TRADE_TYPE_BY_TRADE`)가 없어 뺀 매물을 알린다 (`trade_of` 가 None).

    거래 조건이 비었거나 당근이 새 거래 유형(유형이 null 인 거래 포함)만 올린 매물이다. 웹 목록(`Fo`)의 후보 다섯(매매·전세·월세·단기임대·연세)을 모두
    다뤄 지금은 나오지 않는다 (2026-11-13 연세 지원 전에는 제주 연세만 올린 매물이 여기로 빠졌다: 노형동 40건 중 13건).
    거래 조건을 못 골라 뺀 매물은 사유를 알린다 (AGENTS.md). 예산 안내(`listing_budget_notes`)의 사유 목록만으로는 서버
    조건에 맞는 매물이 왜 빠졌는지 알 수 없었다 (2026-11-12 리뷰). 거래 불가 매물은 거기서 세므로 여기서 세지 않는다.
    """
    count = len({
        article.original_id for article in articles if is_available(article) and not trades_preferred_first(article)
    })
    if count == 0:
        return []
    return [note(
        '제외',
        f"{'·'.join(TRADE_TYPES)} 거래가 없는 매물 {count}건은 jibsa 가 가격을 보여 줄 수 없어 뺐습니다. 당근 웹에서는 보일 수 있습니다",
    )]


def listing_budget_notes(
    limit: int,
    inspected: int,
    returned: int,
    *,
    max_limit: int,
    has_more: bool,
    narrow: str | None,
    eligible: int | None = None,
    narrowable: bool = True,
    resumable: bool = False,
    resumed: bool = False,
    dropped: int = 0,
) -> list[str]:
    """조회한 원본은 제외 여부와 무관하게 예산에 포함한다.

    `has_more` 가 False 면 서버에 더 받을 매물이 없다. 그때 '추가 조회하지 않았다' 고 하면 LLM 이 limit 을
    늘려 다시 조회하므로 끝까지 받았다고 알린다 (2026-10-11 실측: 오산역 매매 limit 120, 55건 반환·has_more false).

    Args:
        max_limit: 그 명령의 `--limit` 최대값. 이미 최대값이면 늘리라고 하지 않는다 (`limit_notes` 와 같이 기본값 없이 받는다.
            인기 매물은 30, 나머지는 120).
        narrow: 더 있을 때 좁히라고 권할 것 (`more_hint` 의 `narrow`). 그 명령에 있는 옵션만 적는다. 좁혀도 남은 매물을 볼 수
            없는 명령(인기 매물은 조건이 `-t` 하나뿐이다)은 None 으로 주어 `--limit` 만 말하게 한다.
        narrowable: `--limit`·필터로 더 받을 수 있는지. 단지 매물처럼 다음 페이지를 이어 받지 못해 멈췄을 때는 limit 을
            늘리거나 필터를 걸어도 더 받지 못해 False 로 주어 그 안내를 붙이지 않는다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        resumed: 이어 받기(`--next`)로 앞 결과 다음부터 받았으면 True. 이번 쪽만 센 수를 전부라고 하지 않는다.
        dropped: `inspected` 중 빈 항목(null)으로 와서 빼고 읽은 수. 예산(`inspected`)에는 세지만 `[제외]` 의 '중복·거래 불가·거래
            조건이 없는 매물' 수에서는 뺀다 (빈 항목은 `null_items_note` 가 따로 알린다. 넣으면 빈 항목을 그 이유로 뺀 것처럼 읽힌다).
    """
    notes: list[str] = []
    # 빈 항목을 뺀 실제로 받은 매물 수. 예산을 다 썼는지는 아래에서 `inspected` 로 본다
    received = inspected - dropped
    excluded = received - returned if eligible is None else received - eligible + min(eligible, limit) - returned
    if excluded > 0 and returned < limit:
        # 당근은 받은 매물을 조건으로 다시 거르지 않아(`trade_of`) 뺀 사유는 이 셋뿐이다. 예전 문구의 '조건 불일치' 는 #215
        # 뒤로 없는 사유라, 거래를 못 고른 매물만 빠진 결과도 서버가 조건에 안 맞는 매물을 준 것처럼 읽혔다 (2026-11-12 리뷰.
        # 그때는 제주 연세만 있는 매물이 빠졌고, 2026-11-13 연세 지원 뒤로는 아는 거래가 하나도 없는 매물만 빠진다)
        head = f'{received}건을 받아 중복·거래 불가·거래 조건이 없는 매물을 빼고 {returned}건입니다'
        notes.append(note('제외', f'{head} (뺀 만큼 다시 채우지 않음)' if has_more else f'{head} (더 받을 매물 없음)'))
    elif returned < limit and not has_more and resumed:
        # 이어 받은 마지막 쪽에서 '이 N건이 전부' 라고 하면 앞 결과의 매물을 빼고 센 말이 된다 (2026-10-28 실측: 사근동 원룸
        # 월세 3쪽째 1건에 '이 1건이 전부입니다', 앞 두 쪽에서 6건을 받았다)
        notes.append(
            f'앞 결과에 이어 남은 매물 {returned}건을 받았고, 더 받을 매물은 없습니다'
            if returned else '앞 결과 뒤로 더 받을 매물이 없습니다'
        )
    elif returned < limit and not has_more:
        # 0건이면 '이 0건이 전부입니다' 대신 없다고 한다 (2026-11-11 LLM 사용 시험: 출퇴근 '판교역: … 이 0건이 전부입니다')
        notes.append(f'조건에 맞는 매물은 이 {returned}건이 전부입니다' if returned else '조건에 맞는 매물이 없습니다')
    if not narrowable:
        return notes
    if has_more and resumable:
        notes.append(note('일부', f'더 있습니다. {NEXT_HINT}'))
    elif has_more and (limit >= max_limit or inspected >= limit):
        # 좁힐 것(`narrow`)에 지역·범위를 붙이지 않는다. 단지 매물·출퇴근 역별 매물은 좁힐 범위가 없고, 인기 매물은 조건이 -t 하나뿐이라
        # 좁혀도 남은 순위를 볼 수 없어 narrow 를 None 으로 받아 --limit 만 말한다 (--limit 이 최대값보다 작을 때만 더 있다고 해
        # 늘리면 된다). 매물 검색(동·지도·역·대학)은 더 있으면 늘 next 로 이어 받게 해 이 안내는 이어 받기가
        # 깨졌을 때(피드 시각을 못 읽음·커서를 잃음·목록이 커서 없이 다음이 있다고 함)만 나간다 (2026-11-11 리뷰·실측: 역삼역·역삼동
        # --limit 3 모두 next 를 줬다)
        notes.append(note('일부', more_hint(limit, max_limit, narrow)))
    return notes


def complex_building_notes(articles: list[DaangnArticleModel]) -> list[str]:
    """원룸·투룸으로 올렸지만 오피스텔·아파트 같은 단지에 있는 매물을 알린다. 매물은 빼지 않는다."""
    found: list[str] = []
    for article in articles:
        if article.sales_type is None or article.sales_type.type not in ROOM_SALES_TYPES:
            continue
        complex_ = article.complex
        building = COMPLEX_TYPE_LABELS.get(complex_.type or '') if complex_ else None
        if complex_ is None or building is None:
            continue
        found.append(f'{article.original_id}({complex_.name or "단지 이름 없음"}, {building})')
    if not found:
        return []
    shown = ', '.join(found[:5]) + (f' 외 {len(found) - 5}건' if len(found) > 5 else '')
    return [
        f'원룸·투룸으로 올렸지만 단지 건물에 있는 매물 {len(found)}건: {shown}. '
        'property_type 은 작성자가 고른 종류이고, 건물 종류는 이 안내와 listing 의 complex_type 으로 확인하세요'
    ]


def property_type_notes(property_types: list[str], structures: list[str] | None = None) -> list[str]:
    """매물 종류 조건의 한계를 알린다. 당근 종류는 작성자가 고른 것이라 건물·방 수와 어긋날 수 있다."""
    # 원룸·오피스텔·투룸 종류의 한계(작성자가 고른 종류, 투룸은 투룸 이상)는 찾을 때마다 같은 안내라 docs/llm.md 로 옮겼다
    notes: list[str] = []
    # 방 구조(subSalesTypes)를 주면 당근은 거의 원룸만 돌려준다 (2026-10-10 실측: 원룸·오피스텔 등 + 분리형 →
    # 동 20건 모두 원룸, 역 20건·통근 50건 중 단지 없는 오피스텔 1건씩만 섞임)
    others = [property_type for property_type in property_types if property_type != '원룸']
    if structures and others:
        notes.append(note(
            '제외',
            f"--structure 를 주면 당근은 거의 원룸만 돌려주어 함께 준 {', '.join(others)} 매물은 대부분 빠집니다. "
            '다른 유형도 보려면 --structure 없이 따로 찾으세요',
        ))
    return notes
