"""네이버 목록 쪽 넘김 (`scan_pages`)과 목록 안내 (`pagination_notes`), 경계·반경 범위."""

from collections.abc import Callable

from jibsa.core.geo import box_around
from jibsa.core.korean import (
    is_district_code,
    particle,
)
from jibsa.core.listing import (
    NEXT_HINT,
    more_hint,
    note,
    null_items_note,
)
from jibsa.providers.naver.api.models.request.common import (
    NaverArticleFilterModel,
    NaverBoundingBoxModel,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverArticlePageModel,
    NaverComplexListPageModel,
    NaverRedevelopmentAreaPageModel,
)
from jibsa.providers.naver.service.common.constants import (
    EXCLUDED_REASON,
    MAX_LIST_LIMIT,
    RADIUS_TOTAL_BASIS,
)
from jibsa.providers.naver.service.common.models import PageScan

from typing import (
    Any,
    NamedTuple,
)


_Page = NaverArticlePageModel | NaverComplexListPageModel | NaverRedevelopmentAreaPageModel


class AreaScope(NamedTuple):
    """지역 안을 찾는 검색(매물·단지·재개발 구역)이 동·시·군·구 경계인지 반경인지에 따라 달라지는 안내 말 (`area_scope`)."""

    scope: str  # pagination_notes 의 scope ('전부'·'없습니다' 가 어느 범위인지)
    total_basis: str  # pagination_notes 의 total_basis
    narrow: str  # pagination_notes 의 narrow
    narrow_action: str  # 요청 상한 안내 끝의 좁히는 법 ('조건을 좁혀' / '반경을 줄이거나 조건을 좁혀')


def scan_pages(
    scan: PageScan,
    fetch: Callable[[int, str | None, Any], _Page | None],
    keep: Callable[[Any], Any],
    *,
    page_size: int,
    start: tuple[str | None, Any] | None = None,
) -> None:
    """`fetch(size, seed, last_info)` 로 페이지를 차례로 받아 항목마다 `keep(item)` 을 부른다.

    할당량(`scan.limit`)은 받은 개수로 센다. 받은 뒤 `keep` 이 버린 항목은 센 채로 두어 다시 채우지 않는다
    (docs/development/output-contract.md 의 개수 상한). 빈 항목(null)이라 빼고 읽은 자리도 서버가 센 자리라 센다
    (`scan.null_items`). 할당량을 다 쓰거나, 다음 페이지가 없거나, 다음 페이지가 있다는데 준 항목이 모두
    이미 받은 번호이거나 쪽이 완전히 빈 페이지(커서가 멈춤)가 오거나(`scan.stalled` 를 켜고 그 쪽은 세지 않는다), `fetch` 가 None 을 주면 멈춘다. 받을 게 남았는데 요청이
    `scan.max_requests` 에 닿으면 `scan.truncated` 를 켠다. 다음 요청에는 앞 페이지의 seed·lastInfo 를 넘긴다
    (seed 가 빠지면 랭킹순이 페이지마다 다시 섞인다).

    멈출 때 다음 페이지를 받을 커서를 `scan.cursor` 에 남긴다 (다음 페이지가 없으면 None). 다음 호출에서 `start` 로
    주면 그 페이지부터 받는다 (이어 받기). 네이버 커서는 마지막 항목의 정렬 값이라 페이지 크기가 달라도 이어진다.

    Args:
        keep: 항목을 걸러 담고 그 항목의 번호를 돌려준다 (모르면 None).
        start: 이어 받을 (seed, lastInfo). 없으면 첫 페이지부터.
    """
    seed, last_info = start if start is not None else (None, None)
    scan.cursor = start
    while True:
        if scan.received >= scan.limit:
            return
        if scan.page_requests >= scan.max_requests:
            scan.truncated = True
            return
        scan.page_requests += 1
        page = fetch(min(page_size, scan.limit - scan.received), seed, last_info)
        if page is None:
            scan.cursor = None
            return
        scan.total = page.total_count
        ids = [keep(item) for item in page.items]
        new_ids = set(ids) - {None} - scan.seen
        dropped = page.null_items('items')
        # 다음 쪽이 있다는데 준 항목이 모두 이미 받은 번호이거나 쪽이 완전히 빈 쪽이면 되풀이된 쪽이라 세기 전에 멈추고 호출부가
        # 일부만 받았다고 알리게 한다. 번호를 모르는 항목(keep 이 None)·빈 항목(null)은 되풀이인지 알 수 없어 세고 넘어간다
        # (되풀이면 요청 상한에서 truncated 로 멈춘다)
        if page.has_next_page and not new_ids and None not in ids and not dropped:
            scan.stalled = True
            scan.cursor = None
            return
        # 빈 항목(null)을 뺐어도 서버는 그 자리를 센 쪽이라 받은 수에 더한다 (쪽 넘김이 일찍 멈추거나 같은 매물을 다시 받지 않게)
        scan.received += len(page.items) + dropped
        scan.null_items += dropped
        scan.seen |= new_ids
        if not page.has_next_page:
            scan.cursor = None
            return
        # seed 는 첫 응답 값이 마지막 페이지까지 그대로 오고 null 로 온 적이 없어 응답 값을 그대로 넘긴다
        # (단지 매물·동 전체·최신순·지도 칸 매물(clusteredArticles)·재개발 구역·단지 목록 6종 22쪽, 2026-10-10 확인)
        seed, last_info = page.seed, page.last_info
        scan.cursor = (seed, last_info)


def scan_null_items_notes(scan: PageScan, what: str) -> list[str]:
    """`scan_pages` 가 빈 항목(null)을 빼고 읽었으면 그 안내 한 줄. 없으면 빈 목록.

    받은 수(`scan.received`)에는 뺀 자리가 이미 들어 있어 쪽 넘김 판정은 맞다. 이 안내는 받은 매물·단지가 서버가 센 수보다 적게
    보이는 까닭을 알린다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 ('네이버 단지 매물').
    """
    return [null_items_note(what, scan.null_items)] if scan.null_items else []


def boundary_filter(filter_: NaverArticleFilterModel, legal_division_code: str) -> NaverArticleFilterModel:
    """경계 검색 필터. 법정동 코드 하나를 넣는다. 시·군·구 코드면 시·군·구 단위(GUN), 아니면 읍·면·동 단위(EUP)다.

    동 매물·단지·재개발 구역 목록이 같은 꼴을 받는다 (성동구 + GUN 도 같은 API 다, 2026-11-18 실측). 단위는 코드로 정한다
    (`is_district_code`). 리 코드는 `is_dong_code` 가 아니라서 `not is_dong_code` 로 가르면 시·군·구로 잘못 읽힌다.
    """
    unit = 'GUN' if is_district_code(legal_division_code) else 'EUP'
    return filter_.model_copy(update={'legal_division_numbers': [legal_division_code], 'legal_division_type': unit})


def area_scope(legal_division_code: str | None, radius_km: float) -> AreaScope:
    """법정동 코드가 있으면 동·시·군·구 경계, 없으면 반경 검색의 안내 말."""
    if legal_division_code is not None:
        return AreaScope(scope='', total_basis='', narrow='조건·지역', narrow_action='조건을 좁혀')
    return AreaScope(
        scope=f'반경 {radius_km:g}km 안에서 ', total_basis=RADIUS_TOTAL_BASIS, narrow='조건·반경',
        narrow_action='반경을 줄이거나 조건을 좁혀',
    )


def pagination_notes(
    total: int,
    returned: int,
    limit: int,
    inspected: int,
    *,
    subject: str = '매물',
    truncated: bool = False,
    excluded_reason: str = EXCLUDED_REASON,
    resumable: bool = False,
    resumed: bool = False,
    scope: str = '',
    total_basis: str = '',
    null_items: int = 0,
    stalled: bool,
    exhausted: bool,
    narrow: str,
) -> list[str]:
    """조회 예산과 실제 제외 결과에 맞춰 추가 조회 없이 안내한다.

    `truncated`(요청 상한에 걸려 멈춤)면 호출한 쪽의 상한 안내가 '더 있을 수 있다' 고 알리므로, 검색을 마쳤다는
    안내와 --limit·필터를 좁히라는 안내를 붙이지 않는다 (홍천 월세 120건 → 지도 칸 24/40개, 49건에서 둘이 함께
    나와 서로 어긋났다, 2026-10-10).

    Args:
        excluded_reason: 제외 안내에서 `subject` 앞에 붙는 제외 사유 (관형어). 반경으로 거르는 검색은
            `RADIUS_EXCLUDED_REASON`.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        resumed: 이어 받기(`--next`)로 받은 결과면 True. 앞 결과에서 받은 매물이 있어 '전부' 대신 '남은 매물' 이라 한다.
        scope: '전부' 가 어느 범위인지 앞에 붙일 말 (예: '반경 1km 안에서 '). 반경을 넓히면 더 나오는데 '전부' 만 쓰면
            찾은 범위의 전부인지 알 수 없다 (2026-10-20 LLM 사용 시험: 1km '26건이 전부' 뒤 2km 85건).
        total_basis: `total` 이 정확한 범위의 수가 아니면 그 범위 (반경 검색은 `RADIUS_TOTAL_BASIS`). 주면 '약 N건(범위)' 으로
            쓴다. 반경 검색에 '조건에 맞는 매물이 1197건' 이라고 하면 사각형 모서리까지 센 수를 반경 안의 수로 읽는다
            (2026-11-11 LLM 사용 시험: 합정역 1km 상가).
        null_items: `inspected` 에 든 빈 항목(null) 수 (`PageScan.null_items`). 서버가 센 자리라 `inspected` 에는 들어 있어 남은 매물을 셀 때 쓰지만,
            중복·거래 유형으로 뺀 수에서는 뺀다 (빈 항목은 따로 안내하므로 그 이유로 뺐다고 하지 않는다).
        stalled: 호출부가 `scan.stopped_short(resumed=...)` 를 넘긴다. 켜지면 '전부' 대신 확인한 데까지만 알린다.
        exhausted: 호출부가 `scan.exhausted` 를 넘긴다.
        narrow: 더 남았을 때 좁히라고 권할 것 (`more_hint`). 동·구 검색은 '조건·지역', 반경 검색은 '조건·반경', 단지·재개발
            구역 하나의 매물은 좁힐 지역이 없어 그 매물의 조건만 준다 (2026-11-10 리뷰·실측: 헬리오시티 111515 2,257건
            --limit 120 에 '조건·지역을 좁히세요'). 기본값을 두지 않는다. 두었더니 재개발 구역 반경 검색이 값을 빠뜨려
            '조건·지역' 이 나갔다 (2026-11-10 리뷰).
    """
    notes: list[str] = []
    excluded = min(inspected - null_items, limit) - returned
    # 단지·구역은 다른 소스처럼 '곳' 으로 센다 (2026-11-10 리뷰: 재개발 구역이 '전체 45건 중 2건입니다')
    unit = '곳' if subject in ('단지', '구역') else '건'
    # 할당량을 다 써서 멈췄으면 서버 수가 받은 수보다 클 때 더 받을 매물이 남았다. 서버가 더 주지 않고 끝났으면(할당량 전에 멈춤)
    # 서버 수가 커도 남은 매물이 아니다. 이어 받을 수 있거나, 요청 상한에서 멈췄거나, 다음 쪽이 있다며 새 항목을 주지 않았으면(stalled)
    # 더 있다. 이어 받은 결과의 total 은 앞 결과까지 센 수라 받은 수와 견주지 않는다 (next 가 없으면 남은 매물이 없다)
    reached = inspected >= limit and not exhausted
    more = resumable or truncated or stalled or (not resumed and reached and total > inspected)
    if returned < limit and excluded > 0:
        notes.append(note(
            '제외',
            f"{excluded_reason} {subject}{particle(subject, '을/를')} 빼고 {returned}{unit}입니다 "
            + ('(뺀 만큼 다시 채우지 않음)' if more else f'(더 받을 {subject} 없음)'),
        ))
    elif returned < limit and not truncated and not stalled:
        what = scope + (f'남은 {subject}' if resumed else f'조건에 맞는 {subject}')
        # 0건이면 '이 0건이 전부입니다' 대신 없다고 한다 (2026-11-11 LLM 사용 시험: 수완동 아파트 전세 3억 이하)
        notes.append(
            f"{what}{particle(subject, '은/는')} 이 {returned}{unit}이 전부입니다" if returned
            else f"{what}{particle(subject, '이/가')} 없습니다"
        )
    # 다른 소스의 [일부](`limit_notes`)처럼 전체 수를 먼저 말하고 그중 몇 건을 보여 주는지 잇는다. 네이버만 '전체 38건 중
    # 일부입니다' 라 몇 건을 보여 주는지 없었고, --limit 이 최대값이면 수 없이 '--limit 의 최대값은 …' 만 나갔다 (2026-11-11
    # LLM 사용 시험: 역삼역 원룸·강남역 단지)
    found = f"조건에 맞는 {subject}{particle(subject, '이/가')} {'약 ' if total_basis else ''}{total}{unit}" + (
        f'({total_basis})' if total_basis else ''
    )
    if not returned:
        shown = f"{found} 있지만, 확인한 {subject}{particle(subject, '이/가')} 모두 빠져 보여 줄 {subject}{particle(subject, '이/가')} 없습니다"
    else:
        shown = f"{found} 있고, {'이어서' if resumed else '그중'} {returned}{unit}{'을' if resumed else '만'} 보여 줍니다"
    if resumable:
        notes.append(note('일부', f'{shown}. {NEXT_HINT}'))
        return notes
    if stalled:
        got = inspected - null_items
        stall = f"네이버가 더 있다면서 새 {subject}{particle(subject, '을/를')} 주지 않아"
        narrow_hint = f"더 보려면 {narrow}{particle(narrow, '을/를')} 좁혀 다시 찾으세요"
        if resumed:
            notes.append(note('일부', f'{stall} 이번에는 {got}{unit}까지만 받았습니다. {narrow_hint}'))
        else:
            notes.append(note('일부', f'{stall} {got}{unit}까지만 받았습니다 ({found}). {narrow_hint}'))
        return notes
    # 이어 받은 결과의 returned 는 이번 몫이라 전체 수와 견주면 앞 결과에서 받은 매물을 빼먹는다
    if truncated or resumed:
        return notes
    # 더 받을 것이 남았는지는 받은 수(inspected)로 본다. 돌려준 수와 견주면 다 받고 뺐을 뿐인데 '더 있다' 고 하거나, 1건만
    # 빠져도 더 있다는 안내가 사라졌다 (2026-10-23 리뷰: 반경 단지 --limit 1 이 전체 89건에 '[제외] … 0건' 만 냈다)
    # 서버가 더 주지 않고 끝났으면(할당량 전에 멈춤) '더 보려면' 을 권하지 않는다. 반경 검색은 total 이 반경을 감싼 사각형 기준이라
    # 받은 수보다 큰 것이 정상이므로 아무것도 더하지 않고, 경계 검색·단지·구역 매물만 총수가 다르다는 것을 알린다
    if total > inspected and not reached:
        if not total_basis:
            notes.append(note('참고', f'네이버가 센 수는 {total}{unit}이지만 더 주지 않아 받은 {inspected - null_items}{unit}까지입니다'))
        return notes
    if total > inspected and reached:
        notes.append(note('일부', f'{shown}. {more_hint(limit, MAX_LIST_LIMIT, narrow)}'))
    return notes


def bounding_box(lat: float, lng: float, radius_km: float) -> NaverBoundingBoxModel:
    south, north, west, east = box_around(lat, lng, radius_km)
    return NaverBoundingBoxModel(left=west, right=east, top=north, bottom=south)
