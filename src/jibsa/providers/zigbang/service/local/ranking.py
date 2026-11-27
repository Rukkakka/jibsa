"""동·구의 단지 랭킹 (region-ranking): 직방 웹 지역 화면 '단지랭킹'과 랭킹 화면의 거래량·상승·하락률·시세·평당가·인기·전세가율 순위."""

from datetime import datetime

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    KST,
    lookup_failure_note,
    more_hint,
    note,
    null_items_note,
    read_date,
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
from jibsa.providers.zigbang.service.common.constants import (
    OPTIONAL_LOOKUP_ERRORS,
    UNEXPECTED_FORMAT_TEXT,
    UPSTREAM_RETRY_HINT,
)
from jibsa.providers.zigbang.service.common.ids import (
    apt_complex_id,
)
from jibsa.providers.zigbang.service.common.text import (
    text_or_none,
)
from jibsa.providers.zigbang.service.local.common import (
    dong_not_applicable,
    local_region_of,
    local_sort_of,
    resolve_local_area,
)
from jibsa.providers.zigbang.service.local.constants import (
    DEFAULT_RANKING_LIMIT,
    RANK_FIELDS_BY_SORT,
    RANKING_MAX_RANKS,
    RANKING_PAGE_SIZE,
    SORT_ONLY_FIELDS,
    SORT_TYPE_BY_TRADE,
    SORTS_WITH_START_DATE,
    SORTS_WITH_UPDATED_AT,
    TRAN_TYPE_BY_TRADE,
    VIEW_PERIOD_BY_LABEL,
    LocalRankingPeriod,
    LocalTrade,
)
from jibsa.providers.zigbang.service.local.models import (
    LocalLevel,
    ZigbangDanjiRank,
    ZigbangRegionRankingResult,
)

from typing import NamedTuple


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


def _rank_of(
    item: ZigbangDanjiRankingModel,
    sort_type: ZigbangDanjiRankingSortType,
    trade: LocalTrade,
    level: LocalLevel,
) -> ZigbangDanjiRank:
    """랭킹 한 줄을 만든다. 그 정렬에 오지 않는 칸과 동 단위 조회의 동은 키를 뺀다 (`not_applicable`)."""
    # 정렬·거래 유형에서 줄에 키가 있는 칸. 하락·상승률의 가격 칸은 매매가 `price_manwon`, 전세가 `deposit_manwon` 이다
    present = RANK_FIELDS_BY_SORT[sort_type]
    if sort_type in ('decrease_rate_desc', 'increase_rate_desc'):
        present = present | {'price_manwon' if trade == '매매' else 'deposit_manwon'}
    return ZigbangDanjiRank(
        rank=item.ranking_number,
        complex_id=None if item.area_danji_id is None else apt_complex_id(item.area_danji_id),
        name=text_or_none(item.area_danji_name),
        dong=text_or_none(item.local),
        trade_count=item.volume,
        approved_date=read_date(item.approved_date, '사용승인일'),
        household_count=item.household_count,
        latest_trade_date=read_date(item.rt_deal_date, '최근 실거래 계약일'),
        price_manwon=item.rt_price,
        deposit_manwon=item.rt_price,
        prev_trade_diff_manwon=item.diff_rt_price,
        prev_trade_diff_percent=item.percent_rt_price,
        area_type=text_or_none(item.danji_room_type_name),
        estimated_price_manwon=item.price,
        estimated_price_per_pyeong_manwon=item.unit_price,
        view_count=item.view_count,
        jeonse_ratio_percent=item.charter_rate,
        gap_manwon=item.gap,
        not_applicable=(SORT_ONLY_FIELDS - present) | dong_not_applicable(level),
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
        except OPTIONAL_LOOKUP_ERRORS as exc:
            if first is None:
                raise
            return _RankingPages(first, rows, received, dropped, False, (page, exc))
        if response.rankings is None:
            if first is None:
                raise JibsaError(
                    code='UPSTREAM_ERROR',
                    message='직방이 단지 랭킹 목록을 주지 않았습니다',
                    hint=UPSTREAM_RETRY_HINT,
                )
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
            notes.append(note(
                '실패',
                f'직방이 단지 랭킹 {failed_page}쪽 목록을 주지 않았습니다. {UNEXPECTED_FORMAT_TEXT}. '
                f'앞 {len(rankings)}곳까지만 냅니다',
            ))
        else:
            notes.append(lookup_failure_note(exc, '직방', f'단지 랭킹 {failed_page}쪽', f'앞 {len(rankings)}곳까지만 냅니다'))
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
    # 서버의 UTC 일시('2026-11-22T00:00:00.367Z')를 한국 시간 'YYYY-MM-DD HH:MM' 으로. 읽지 못하면 None
    updated_at: str | None = None
    if pages.first.updated_date is not None:
        try:
            moment = datetime.fromisoformat(pages.first.updated_date.strip().replace('Z', '+00:00'))
        except ValueError:
            pass
        else:
            if moment.tzinfo is None:
                # 시간대가 없으면 한국 시간으로 본다 (`normalize_date` 와 같다)
                moment = moment.replace(tzinfo=KST)
            updated_at = moment.astimezone(KST).strftime('%Y-%m-%d %H:%M')
    return ZigbangRegionRankingResult(
        region=local_region_of(area),
        trade_type=trade,
        sort=sort_label,
        period=period,
        start_date=read_date(pages.first.start_date, '집계 시작일'),
        end_date=read_date(pages.first.end_date, '집계 끝 날짜'),
        updated_at=updated_at,
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
