"""청약 일정 (sale-schedule)."""
from datetime import (
    date,
    timedelta,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    more_hint,
    normalize_address,
    note,
    null_items_note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.sale.schedule import (
    DabangSaleInLotsListScheduleSearchV3RequestParameterModel,
    DabangSaleInLotsListScheduleV3RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.sale.schedule import (
    DabangSaleScheduleTableRowModel,
)
from jibsa.providers.dabang.service.region.region import (
    state_name,
)
from jibsa.providers.dabang.service.sale.common import in_lots_fields
from jibsa.providers.dabang.service.sale.constants import (
    SALE_SCHEDULE_MAX_LIMIT,
    SCHEDULE_REGION_PATTERN,
)
from jibsa.providers.dabang.service.sale.models.schedule import (
    DabangSaleSchedule,
    DabangSaleScheduleItem,
    DabangSaleScheduleSale,
)


def get_sale_schedule(
    client: DabangClient, *, start: date, days: int, region: str | None = None, details: bool = False, limit: int,
) -> DabangSaleSchedule:
    """`start` 부터 `days` 일(최대 7일)의 청약 일정 (요청 1회).

    `details` 면 일정이 있는 날마다 그 날의 분양 단지 표(`list/schedule/search`, 웹 청약 일정 화면에서 날짜를 누르면 나오는
    표)를 받아 줄마다 주소·유형·세대수·가격을 붙인다 (날마다 요청 1회 더). 내보낼 줄(`limit`)이 든 날만 받는다. 줄은 분양 ID 와
    종류 번호(요약 `type` = 상세 `grouping`)가 모두 같은 상세 줄과 맞춘다. 웹도 두 목록을 같은 서버 순서로 그린다.

    `region` 을 주면 상세를 받아(`details` 와 같다) 주소의 시·도로 거른다. 남긴 줄이 `limit` 을 넘으면(더 있는지 알려고
    `limit`+1 줄) 그 뒤 날은 받지 않고 멈춘다. 뒷날 줄을 일정 글의 시·도만으로 거르면 앞날과 기준이 달라져 아예 보지 않는다.
    상세에서 찾지 못한 줄만 일정 글 앞의 시·도로 보고, 그것도 없으면 지역을 몰라 뺀다.

    Raises:
        JibsaError: `region` 이 시·도 이름이 아닐 때 (INVALID_ARGUMENT).
    """
    wanted = state_name(region.strip()) if region else None
    if region and wanted is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"--region 은 시·도 이름이어야 합니다: '{region}'",
            hint='서울·경기·충북처럼 줄임말이나 충청북도 같은 정식 이름을 주세요. 시·군·구로는 거르지 못합니다',
        )
    details = details or wanted is not None
    end = start + timedelta(days=days - 1)
    schedule = client.run_request_sale_in_lots_list_schedule_v3(
        DabangSaleInLotsListScheduleV3RequestParameterModel(from_date=start, to_date=end)
    )
    day_rows = schedule.root
    rows: list[DabangSaleScheduleItem] = []
    # rows 와 같은 순서로, 그 줄을 그 날 분양 단지 표와 맞춰 봤는지 (표를 받았고 분양 ID·종류가 모두 있을 때). 출력 필드는 아니다
    matched_lookup: list[bool] = []
    # 날·종류 묶음·일정 어느 층에서든 빈 항목을 뺐으면 일정 수를 셀 수 없다 (받은 줄만 세면 적은 수가 완전한 값처럼 나간다)
    dropped = schedule.null_items() + sum(
        day.null_items('schedule_by_type') + sum(group.null_items('schedules') for group in day.schedule_by_type) for day in day_rows
    )
    total = None if dropped else sum(len(group.schedules) for day in day_rows for group in day.schedule_by_type)
    # 그 날 분양 단지 표(상세)에서 뺀 빈 항목 수
    table_dropped = 0
    unknown = 0
    requests = 0
    # 지역으로 거르다 limit 을 넘겨 멈춘 날과 그 앞날까지 본 일정 수 (멈추지 않으면 None)
    stopped_at: str | None = None
    seen = 0
    for day in day_rows:
        entries = [(group, entry) for group in day.schedule_by_type for entry in group.schedules]
        if wanted is not None and entries and len(rows) > limit:
            stopped_at = day.date
            break
        seen += len(entries)
        sales: dict[tuple[str, int], DabangSaleScheduleTableRowModel] | None = None
        # 지역으로 거르지 않으면 앞 limit 줄이 든 날까지만 상세를 받는다 (뒷날 줄은 내보내지 않는다)
        if details and entries and (wanted is not None or len(rows) < limit):
            response = client.run_request_sale_in_lots_list_schedule_search_v3(
                DabangSaleInLotsListScheduleSearchV3RequestParameterModel(from_date=date.fromisoformat(day.date))
            )
            requests += 1
            table_dropped += response.null_items()
            sales = {}
            for row in response.root:
                # 분양 ID·종류 번호가 없는 줄은 요약 줄과 맞출 수 없어 넣지 않는다 (그 줄과 맞출 요약 줄은 sale 이 null)
                if row.id is not None and row.grouping is not None:
                    sales.setdefault((row.id, row.grouping), row)
        for group, entry in entries:
            kind = (group.type_title or '').split(' ')[0] or None
            text = entry.schedule_str or ''
            match = SCHEDULE_REGION_PATTERN.match(text)
            # 글은 '[청약접수] 인천 …' 처럼 시·도 줄임말로 시작하지만 시·도 없이 시나 단지 이름으로 시작하기도 한다
            # (2026-10-25 실측 7일 83건 중 '익산 부송에코르'·'한양립스 에듀포레', 태그가 둘인 '[계약기간]  [무순위] 올 뉴
            # 챔피언스시티'). 칸에는 좌표뿐이라 시·도가 아니면 모름(None)으로 둔다. '광주시' 로 시작하면 경기도 광주시라
            # 다른 시('익산')처럼 모름이다 (`state_name`)
            where = match.group(1) if match and state_name(match.group(1)) else None
            found: DabangSaleScheduleTableRowModel | None = None
            # 종류 번호가 없으면 맞추지 않는다. 분양 ID 만으로 맞추면 같은 날 두 종류(접수·계약)인 단지의 줄을 가르지 못한다
            looked_up = False
            if sales is not None and entry.id is not None and group.type is not None:
                looked_up = True
                found = sales.get((entry.id, group.type))
            if wanted is not None:
                address = normalize_address(found.address) if found is not None else None
                state = state_name(address.split(' ')[0]) if address else state_name(where) if where else None
                if state != wanted:
                    unknown += state is None
                    continue
            rows.append(DabangSaleScheduleItem(
                date=day.date, kind=kind, sido=where, text=text, presale_id=entry.id,
                presale=None if found is None else DabangSaleScheduleSale(**in_lots_fields(found)), fetched=sales is not None,
            ))
            matched_lookup.append(looked_up)
    shown = rows[:limit]
    # 맞춰 본 줄만 찾지 못한 것으로 센다. 표를 받았어도 다방이 분양 ID·종류를 주지 않아 맞춰 보지 못한 줄은 따로 센다
    tried = sum(matched_lookup[:len(shown)])
    unmatched = sum(item.presale is None and looked for item, looked in zip(shown, matched_lookup))
    unchecked = sum(item.fetched and not looked for item, looked in zip(shown, matched_lookup))
    notes: list[str] = []
    if requests:
        notes.append(note('참고', f'일정이 있는 날 {requests}곳의 분양 단지 표를 더 받았습니다 (요청 {requests + 1}회)'))
    if unmatched:
        # 한 줄도 맞추지 못했으면 다방이 두 목록의 꼴을 바꾼 것이다 (매일 감시가 이 말로 고장을 찾는다)
        notes.append(note(
            '참고',
            f'{unmatched}건은 그 날 분양 단지 표에서 같은 분양·종류를 찾지 못해 presale 이 null 입니다'
            + (f'. {UPDATE_MAYBE_NEEDED}' if unmatched == tried else ''),
        ))
    if unchecked:
        # 맞춰 보지 못했으니 다방이 두 목록의 꼴을 바꾼 신호가 아니다 (업데이트 안내를 붙이지 않는다)
        notes.append(note('참고', f'{unchecked}건은 다방이 분양 ID·종류를 주지 않아 맞춰 보지 못해 presale 이 null 입니다'))
    if wanted is not None and stopped_at is None:
        among = f'{total}건 중 ' if total is not None else ''
        notes.append(note('참고', f"주소의 시·도가 '{region}' 인 일정만 남겼습니다 ({among}{len(rows)}건)"))
    elif wanted is not None:
        seen_count = f'{seen}건' if not dropped else '일정'
        notes.append(note('참고', (
            f"주소의 시·도가 '{region}' 인 일정만 남겼습니다 ({stopped_at} 전날까지 본 {seen_count} 중 {len(rows)}건). "
            f'--limit 을 넘겨 {stopped_at}부터는 보지 않았습니다'
        )))
    if unknown:
        seen_days = '' if stopped_at is None else f'{stopped_at} 전날까지 본 일정 중 '
        notes.append(note(
            '제외', f'{seen_days}주소도 일정 글의 시·도도 없어 지역을 모르는 {unknown}건을 뺐습니다 (--region 없이 부르면 나옵니다)',
        ))
    if len(rows) > limit:
        # --limit 이 이미 최대값이면 늘리라고 하지 않는다 (2026-11-10 리뷰). 멈췄으면 뒷날을 보지 않아 남은 수를 모른다
        at_least = '' if stopped_at is None and not dropped else '적어도 '
        notes.append(note(
            '일부',
            f'일정 {at_least}{len(rows)}건 중 앞 {limit}건입니다. '
            + more_hint(limit, SALE_SCHEDULE_MAX_LIMIT, '기간(--days)·지역(--region) 조건'),
        ))
    if dropped:
        notes.append(null_items_note('다방 청약 일정', dropped, ('total',)))
    if table_dropped:
        notes.append(null_items_note('다방 분양 단지 표', table_dropped))
    return DabangSaleSchedule(
        start_date=start.isoformat(), end_date=end.isoformat(), total=total, returned=len(shown), schedules=shown, notes=notes,
    )
