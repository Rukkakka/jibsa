"""동·구의 단지 랭킹 (region-ranking): 직방 웹 지역 화면 '단지랭킹'과 랭킹 화면의 거래량·상승·하락률·시세·평당가·인기·전세가율 순위."""

from datetime import datetime

from pydantic import Field

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    KST,
    iso_date,
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.common import ZigbangAptTranType
from jibsa.providers.zigbang.api.request.local.ranking import (
    ZigbangDanjiRankingSortType,
    ZigbangDanjiRankingViewPeriod,
    ZigbangLocalsDanjiRankingRequestParameterModel,
)
from jibsa.providers.zigbang.api.response.local.ranking import (
    ZigbangDanjiRankingModel,
    ZigbangLocalsDanjiRankingResponseModel,
)
from jibsa.providers.zigbang.service.common.base import (
    SCHOOL_LOOKUP_ERRORS,
    UNEXPECTED_FORMAT_TEXT,
    UPSTREAM_RETRY_HINT,
    apt_complex_id,
    failure_update_hint,
    text_or_none,
)
from jibsa.providers.zigbang.service.local.base import (
    LOCAL_DONG_DESCRIPTION,
    LocalLevel,
    LocalTrade,
    ZigbangLocalModel,
    ZigbangLocalRegion,
    dong_not_applicable,
    local_region_of,
    local_sort_of,
    resolve_local_area,
)

from typing import (
    Annotated,
    Literal,
    NamedTuple,
)


LocalRankingPeriod = Literal['이번주', '지난주', '이번달', '지난달', '올해', '작년']
RANKING_PERIODS: tuple[LocalRankingPeriod, ...] = ('이번주', '지난주', '이번달', '지난달', '올해', '작년')
DEFAULT_RANKING_LIMIT: int = 10
# 쪽 크기. 서버는 11 이상이면 400 이다 (2026-11-22 실측)
RANKING_PAGE_SIZE: int = 10
# 웹이 보여 주는 최대 순위. 랭킹 화면은 `list.length>=100` 에서 넘기기를 멈추고 '단지 랭킹은 100위까지만 제공됩니다.' 를 보여 준다
# (2026-11-22 번들 `onEndReached`). 서버는 200위까지 주지만 101위부터는 웹에서 볼 수 없어 받지 않는다
RANKING_MAX_RANKS: int = 100
# 웹 기간 탭 → 서버 viewPeriod
VIEW_PERIOD_BY_LABEL: dict[LocalRankingPeriod, ZigbangDanjiRankingViewPeriod] = {
    '이번주': 'this_week',
    '지난주': 'last_week',
    '이번달': 'this_month',
    '지난달': 'last_month',
    '올해': 'this_year',
    '작년': 'last_year',
}
TRAN_TYPE_BY_TRADE: dict[LocalTrade, ZigbangAptTranType] = {'매매': 'trade', '전세': 'charter', '월세': 'rental'}
# 웹 정렬 이름 → 서버 sortType (2026-11-19 번들 `T`). 첫 항목이 지역 화면 '단지랭킹' 패널의 기본이고(랭킹 화면 주소를 바로 열면 평당가
# 높은순이다, 2026-11-22 웹 조사) 거래 유형마다 정렬이 다르다 (월세는 거래량뿐)
SORT_TYPE_BY_TRADE: dict[LocalTrade, dict[str, ZigbangDanjiRankingSortType]] = {
    '매매': {
        '거래량 많은순': 'volume_desc',
        '하락률 높은순': 'decrease_rate_desc',
        '상승률 높은순': 'increase_rate_desc',
        '시세 높은순': 'price_desc',
        '평당가 높은순': 'unit_price_desc',
        '인기 단지순': 'view_count_desc',
    },
    '전세': {
        '거래량 많은순': 'volume_desc',
        '하락률 높은순': 'decrease_rate_desc',
        '상승률 높은순': 'increase_rate_desc',
        '시세 높은순': 'price_desc',
        '전세가율 높은순': 'charter_rate_desc',
    },
    '월세': {'거래량 많은순': 'volume_desc'},
}
# 정렬마다 줄에 오는 칸 (2026-11-22 표본: 정렬 일곱 가지를 모두 불렀다). 거래량·시세·평당가·인기·전세가율은 사용승인일·총세대수가 오고, 하락률·상승률은
# 직전 거래 대비 값이 오며 사용승인일·총세대수는 오지 않는다. 하락·상승률의 가격 칸은 거래 유형이 정한다 (`_present_fields`)
RATE_FIELDS: frozenset[str] = frozenset({'contract_date', 'diff_manwon', 'change_rate_percent', 'area_type'})
RANK_FIELDS_BY_SORT: dict[ZigbangDanjiRankingSortType, frozenset[str]] = {
    'volume_desc': frozenset({'trade_count', 'approved_at', 'households'}),
    'decrease_rate_desc': RATE_FIELDS,
    'increase_rate_desc': RATE_FIELDS,
    'price_desc': frozenset({'estimated_price_manwon', 'approved_at', 'households'}),
    'unit_price_desc': frozenset({'estimated_price_per_pyeong_manwon', 'approved_at', 'households'}),
    'view_count_desc': frozenset({'view_count', 'approved_at', 'households'}),
    'charter_rate_desc': frozenset({'jeonse_rate_percent', 'gap_manwon', 'approved_at', 'households'}),
}
SORT_ONLY_FIELDS: frozenset[str] = frozenset({'price_manwon', 'deposit_manwon'}).union(*RANK_FIELDS_BY_SORT.values())
# 결과 머리에서 서버가 주지 않는 정렬이라 키를 뺄 날짜 (2026-11-22 표본): 시세·평당가·전세가율은 기준일(end_date)뿐이고, 인기는 갱신 시각이 없다
# (웹 머리 `56955`: 거래량·하락률·상승률은 '{시작} ~ {끝} 실거래 등록 기준 {갱신 시각} 업데이트', 인기는 '{시작} ~ {끝} 조회 기준', 그 밖은 '{기준일} 직방 시세 기준')
SORTS_WITH_START_DATE: frozenset[ZigbangDanjiRankingSortType] = frozenset({
    'volume_desc', 'decrease_rate_desc', 'increase_rate_desc', 'view_count_desc',
})
SORTS_WITH_UPDATED_AT: frozenset[ZigbangDanjiRankingSortType] = frozenset({
    'volume_desc', 'decrease_rate_desc', 'increase_rate_desc',
})


class ZigbangDanjiRank(ZigbangLocalModel):
    """단지 랭킹 한 줄. 정렬마다 오는 칸이 달라 해당하지 않는 칸은 키가 없다. 금액은 만원이다."""

    rank: Annotated[
        int | None,
        Field(description='순위 (직방 rankingNumber). 같은 값이면 같은 순위로 오고 다음 순위가 건너뛴다 (예: 1·1·1·4). 직방이 주지 않으면 null')
    ]
    complex_id: Annotated[
        str | None,
        Field(description='단지 ID (apt-<번호>. jibsa zigbang complex·real-price·search listings --complex 에 넘긴다). 직방이 주지 않으면 null')
    ]
    complex_name: Annotated[
        str | None,
        Field(description='단지 이름')
    ]
    dong: Annotated[
        str | None,
        Field(description=LOCAL_DONG_DESCRIPTION)
    ]
    trade_count: Annotated[
        int | None,
        Field(description='기간 안 거래 건수 (건, 거래량 많은순만)')
    ]
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD, 하락률·상승률 정렬에는 키가 없다). 읽지 못하면 null')
    ]
    households: Annotated[
        int | None,
        Field(description='총세대수 (하락률·상승률 정렬에는 키가 없다)')
    ]
    contract_date: Annotated[
        str | None,
        Field(description='가장 최근 계약일 (YYYY-MM-DD, 하락률·상승률 정렬만). 읽지 못하면 null')
    ]
    price_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래가 (만원, 매매의 하락률·상승률 정렬만)')
    ]
    deposit_manwon: Annotated[
        int | float | None,
        Field(description='가장 최근 거래의 보증금 (만원, 전세의 하락률·상승률 정렬만)')
    ]
    diff_manwon: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 차액 (만원, 하락률·상승률 정렬만)')
    ]
    change_rate_percent: Annotated[
        int | float | None,
        Field(description='직전 거래 대비 변동률 (%, 하락률·상승률 정렬만)')
    ]
    area_type: Annotated[
        str | None,
        Field(description='가장 최근 거래의 평형 이름 (하락률·상승률 정렬만)')
    ]
    estimated_price_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 (만원, 시세 높은순만). 웹 설명: 단지 중 가장 시세가 높은 타입을 기준으로 한 값이라 공급 면적별 차이가 있다')
    ]
    estimated_price_per_pyeong_manwon: Annotated[
        int | float | None,
        Field(description='직방시세 기준 평당가 (만원/3.3㎡, 평당가 높은순만)')
    ]
    view_count: Annotated[
        int | None,
        Field(description='기간 안 조회수 (인기 단지순만)')
    ]
    jeonse_rate_percent: Annotated[
        int | float | None,
        Field(description='직방 매매 시세 대비 전세 시세 비율 (%, 전세가율 높은순만)')
    ]
    gap_manwon: Annotated[
        int | float | None,
        Field(description='매매 시세와 전세 시세의 차이 (만원, 전세가율 높은순만)')
    ]


class ZigbangRegionRankingResult(ZigbangLocalModel):
    """동·구의 단지 랭킹 (직방 웹 지역 화면 '단지랭킹', 웹처럼 100위까지)."""

    region: Annotated[
        ZigbangLocalRegion,
        Field(description='조회한 동·구')
    ]
    trade_type: Annotated[
        LocalTrade,
        Field(description='거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (웹 이름 그대로, 예: 거래량 많은순)')
    ]
    period: Annotated[
        LocalRankingPeriod,
        Field(description='기간. 시세 높은순·평당가 높은순·전세가율 높은순은 기간과 상관없이 시세 기준일의 순위다')
    ]
    start_date: Annotated[
        str | None,
        Field(description='집계 시작일 (YYYY-MM-DD, 한국 날짜. 서버는 UTC 로 주지만 한국 날짜로 바꾼다). 거래량·하락률·상승률·인기 정렬만 있고 시세·평당가·전세가율에는 키가 없다. 읽지 못하면 null')
    ]
    end_date: Annotated[
        str | None,
        Field(description='집계 끝 날짜 (YYYY-MM-DD, 한국 날짜). 거래량·하락률·상승률은 집계 기간의 끝, 시세·평당가·전세가율은 직방 시세 기준일, 인기는 조회 집계의 끝이다. 읽지 못하면 null')
    ]
    updated_at: Annotated[
        str | None,
        Field(description='갱신 시각 (YYYY-MM-DD HH:MM, 한국 시간). 거래량·하락률·상승률 정렬만 있고 시세·평당가·전세가율·인기는 서버가 주지 않아 키가 없다. 읽지 못하면 null')
    ]
    total: Annotated[
        int | None,
        Field(description='직방이 준 순위 수 (count). 서버가 200 에서 막아 실제 단지가 더 많을 수 있고 웹은 100위까지만 보여 준다. 직방이 주지 않으면 null')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='웹이 보여 주는 100위 안에 --limit 을 늘리면 더 받을 수 있는 단지가 남았는지 (직방이 목록을 순위 수보다 일찍 끝내면 false. 이어 받기는 없다)')
    ]
    rankings: Annotated[
        list[ZigbangDanjiRank],
        Field(description='단지 랭킹 (직방 순위 순서 그대로)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 받았다는 안내·100위까지만 본다는 안내·쪽을 받지 못했다는 안내. CLI 가 결과 위에 붙인다')
    ] = []


class _RankingPages(NamedTuple):
    """랭킹 쪽을 차례로 받은 결과."""

    first: ZigbangLocalsDanjiRankingResponseModel
    rows: list[ZigbangDanjiRankingModel]
    # 받은 자리 수. 서버가 준 빈 항목도 한 자리다
    received: int
    dropped: int
    # 마지막으로 받은 쪽이 한 쪽 크기보다 적어 끝까지 받았는지
    exhausted: bool
    # 2쪽 이후를 받지 못했으면 (쪽 번호, 예외). 예외가 None 이면 직방이 그 쪽 목록(list)을 주지 않았다
    failure: tuple[int, Exception | None] | None


def _kst_minute(value: str | None) -> str | None:
    """서버의 UTC 일시('2026-11-22T00:00:00.367Z')를 한국 시간 'YYYY-MM-DD HH:MM' 으로. 읽지 못하면 None."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        # 시간대가 없으면 한국 시간으로 본다 (`normalize_date` 와 같다)
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(KST).strftime('%Y-%m-%d %H:%M')


def _present_fields(sort_type: ZigbangDanjiRankingSortType, trade: LocalTrade) -> frozenset[str]:
    """정렬·거래 유형에서 줄에 키가 있는 칸. 하락·상승률의 가격 칸은 매매가 `price_manwon`, 전세가 `deposit_manwon` 이다."""
    fields = RANK_FIELDS_BY_SORT[sort_type]
    if sort_type in ('decrease_rate_desc', 'increase_rate_desc'):
        return fields | {'price_manwon' if trade == '매매' else 'deposit_manwon'}
    return fields


def _rank_of(
    item: ZigbangDanjiRankingModel,
    sort_type: ZigbangDanjiRankingSortType,
    trade: LocalTrade,
    level: LocalLevel,
) -> ZigbangDanjiRank:
    """랭킹 한 줄을 만든다. 그 정렬에 오지 않는 칸과 동 단위 조회의 동은 키를 뺀다 (`not_applicable`)."""
    return ZigbangDanjiRank(
        rank=item.ranking_number,
        complex_id=None if item.area_danji_id is None else apt_complex_id(item.area_danji_id),
        complex_name=text_or_none(item.area_danji_name),
        dong=text_or_none(item.local),
        trade_count=item.volume,
        approved_at=iso_date(item.approved_date),
        households=item.household_count,
        contract_date=iso_date(item.rt_deal_date),
        price_manwon=item.rt_price,
        deposit_manwon=item.rt_price,
        diff_manwon=item.diff_rt_price,
        change_rate_percent=item.percent_rt_price,
        area_type=text_or_none(item.danji_room_type_name),
        estimated_price_manwon=item.price,
        estimated_price_per_pyeong_manwon=item.unit_price,
        view_count=item.view_count,
        jeonse_rate_percent=item.charter_rate,
        gap_manwon=item.gap,
        not_applicable=(SORT_ONLY_FIELDS - _present_fields(sort_type, trade)) | dong_not_applicable(level),
    )


def _upstream_error() -> JibsaError:
    return JibsaError(
        code='UPSTREAM_ERROR',
        message='직방이 단지 랭킹 목록을 주지 않았습니다',
        hint=UPSTREAM_RETRY_HINT,
    )


def _collect_pages(
    client: ZigbangClient,
    code: str,
    view_period: ZigbangDanjiRankingViewPeriod,
    sort_type: ZigbangDanjiRankingSortType,
    tran_type: ZigbangAptTranType,
    limit: int,
) -> _RankingPages:
    """랭킹을 1쪽부터 `RANKING_PAGE_SIZE` 건씩 받는다 (웹 랭킹 화면과 같은 쪽 크기·변수).

    받은 자리 수(빈 항목 포함)가 `limit` 이상이거나 웹이 볼 수 있는 수(`count` 와 100위 가운데 작은 쪽) 이상이거나 한 쪽이 쪽 크기보다 적으면
    멈춘다 (웹 `onEndReached` 의 `count === list.length`·`list.length >= 100`). 2쪽 이후 요청이 실패하거나 직방이 목록(list)을 주지 않으면 받은 쪽까지 주고 실패를 함께 준다.

    Raises:
        JibsaError: 1쪽에서 직방이 목록(`list`)을 주지 않았을 때 (UPSTREAM_ERROR). 1쪽 요청의 실패는 그대로 올린다.
    """
    first: ZigbangLocalsDanjiRankingResponseModel | None = None
    rows: list[ZigbangDanjiRankingModel] = []
    received = 0
    dropped = 0
    cap = RANKING_MAX_RANKS
    page = 1
    while True:
        try:
            response = client.run_request_locals_danji_ranking(ZigbangLocalsDanjiRankingRequestParameterModel(
                page=page,
                limit=RANKING_PAGE_SIZE,
                bjd_code=code,
                view_period=view_period,
                sort_type=sort_type,
                tran_type=tran_type,
            ))
        except SCHOOL_LOOKUP_ERRORS as exc:
            if first is None:
                raise
            return _RankingPages(first, rows, received, dropped, False, (page, exc))
        if response.rankings is None:
            if first is None:
                raise _upstream_error()
            return _RankingPages(first, rows, received, dropped, False, (page, None))
        if first is None:
            first = response
            if response.count is not None:
                cap = min(response.count, RANKING_MAX_RANKS)
        rows.extend(response.rankings)
        page_dropped = response.null_items('rankings')
        page_received = len(response.rankings) + page_dropped
        dropped += page_dropped
        received += page_received
        if page_received < RANKING_PAGE_SIZE:
            return _RankingPages(first, rows, received, dropped, True, None)
        if received >= limit or received >= cap:
            return _RankingPages(first, rows, received, dropped, False, None)
        page += 1


def get_region_ranking(
    client: ZigbangClient,
    query: str,
    *,
    trade: LocalTrade = '매매',
    sort: str | None = None,
    period: LocalRankingPeriod = '이번달',
    limit: int = DEFAULT_RANKING_LIMIT,
) -> ZigbangRegionRankingResult:
    """동·구의 단지 랭킹을 직방 웹 랭킹 화면과 같은 요청(10건씩 쪽 넘김)으로 `limit` 개 받는다 (요청 수: 지역 검색 1회 + 랭킹 ceil(min(limit, 순위 수, 100) / 10) 쪽).

    서버는 200위까지 주지만 웹이 100위까지만 보여 주므로 101위부터는 받지 않는다. 같은 순위(rankingNumber)도 서버 순서 그대로 낸다.
    정렬 이름은 지역을 찾기 전에 검사한다.

    Raises:
        JibsaError: 그 거래에 없는 정렬일 때·시·도 이름일 때 (INVALID_ARGUMENT), 직방이 랭킹 목록을 주지 않았을 때(1쪽, UPSTREAM_ERROR).
        RegionNotFoundError: 동·구를 찾지 못했을 때.
        RegionAmbiguousError: 같은 이름의 동·구가 여럿이거나 구가 있는 시·'○가' 로만 나뉜 동일 때.
    """
    sort_label, sort_type = local_sort_of(trade, sort, SORT_TYPE_BY_TRADE[trade])
    area = resolve_local_area(client, query)
    pages = _collect_pages(client, area.code, VIEW_PERIOD_BY_LABEL[period], sort_type, TRAN_TYPE_BY_TRADE[trade], limit)
    notes = list(area.notes)
    total = pages.first.count
    rankings = [_rank_of(item, sort_type, trade, area.level) for item in pages.rows[:limit]]
    cut = len(pages.rows) > limit
    # 웹이 볼 수 있는 수. 서버가 순위 수를 주지 않으면 100위다
    cap = RANKING_MAX_RANKS if total is None else min(total, RANKING_MAX_RANKS)
    # 서버가 더 줄 쪽이 없으면(쪽이 모자람) 순위 수가 더 커도 더 받을 수 없다
    has_more = cut or (not pages.exhausted and pages.received < cap)
    if pages.dropped:
        notes.append(null_items_note('직방 단지 랭킹', pages.dropped))
    if pages.failure is not None:
        failed_page, exc = pages.failure
        if exc is None:
            failure_text = (
                f'직방이 단지 랭킹 {failed_page}쪽 목록을 주지 않아 앞 {len(rankings)}곳까지만 냅니다. '
                f'{UNEXPECTED_FORMAT_TEXT}'
            )
        else:
            failure_text = f'직방 단지 랭킹 {failed_page}쪽을 받지 못해({type(exc).__name__}) 앞 {len(rankings)}곳까지만 냅니다{failure_update_hint(exc)}'
        notes.append(note('실패', failure_text))
    if total is not None and total > RANKING_MAX_RANKS:
        notes.append(note('참고', f"직방 웹처럼 {RANKING_MAX_RANKS}위까지만 봅니다 (웹 '단지 랭킹은 100위까지만 제공됩니다')"))
    if not cut and total is not None and pages.exhausted and pages.received < cap:
        notes.append(note('참고', f'직방이 순위 수를 {total}곳이라 주었지만 목록은 {pages.received}곳에서 끝나 더 받을 수 없습니다'))
    if total == 0 and not rankings:
        notes.append(note('참고', "직방이 이 조건의 단지 랭킹을 주지 않았습니다 (직방 웹은 '선택한 기간 동안 등록된 실거래가 없습니다' 로 알립니다)"))
    if has_more:
        head = (
            f'랭킹 단지 {cap}곳 중 앞 {len(rankings)}곳입니다' if total is not None
            else f'앞 {len(rankings)}곳입니다. 직방이 전체 순위 수를 주지 않아 더 있을 수 있습니다'
        )
        # 쪽을 받지 못한 때는 --limit 을 늘려도 같은 곳에서 멈출 수 있어 더 보는 법 대신 실패 안내를 따른다
        notes.append(note('일부', head if pages.failure is not None else f'{head}. {more_hint(limit, RANKING_MAX_RANKS, None)}'))
    return ZigbangRegionRankingResult(
        region=local_region_of(area),
        trade_type=trade,
        sort=sort_label,
        period=period,
        start_date=iso_date(pages.first.start_date),
        end_date=iso_date(pages.first.end_date),
        updated_at=_kst_minute(pages.first.updated_date),
        total=total,
        returned=len(rankings),
        has_more=has_more,
        rankings=rankings,
        notes=notes,
        not_applicable=frozenset(
            ({'start_date'} if sort_type not in SORTS_WITH_START_DATE else set())
            | ({'updated_at'} if sort_type not in SORTS_WITH_UPDATED_AT else set())
        ),
    )
