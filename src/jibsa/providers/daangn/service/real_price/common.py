"""실거래가 기능(real_price)의 단지·지역·시세 추이가 같이 쓰는 것."""

from collections.abc import Callable

from jibsa.core.errors import (
    JibsaError,
)
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    note,
)
from jibsa.providers.daangn.api.models.response.common import (
    DaangnPageInfoModel,
)
from jibsa.providers.daangn.api.models.response.compare.common import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
)
from jibsa.providers.daangn.service.common.complex import (
    pyeong_groups,
    truncation_notes,
)
from jibsa.providers.daangn.service.common.response import (
    T,
    code_label,
    cursor_stopped_note,
    next_cursor,
    stalled_page,
)
from jibsa.providers.daangn.service.real_price.constants import (
    CONTRACT_TYPE_LABELS,
    REAL_PRICE_MAX_LIMIT,
    REAL_PRICE_MAX_PAGES,
    REAL_PRICE_PAGE_SIZE,
)

from typing import (
    Generic,
    NamedTuple,
)


# (받을 수, 커서) → (한 페이지의 거래, 페이지 정보). 당근이 그 페이지를 주지 않았으면(연결이나 edges 가 null) 거래가 None 이다
PageFetch = Callable[[int, str | None], tuple[list[T] | None, DaangnPageInfoModel | None]]



class Collected(NamedTuple, Generic[T]):
    """`collect_pages` 가 모은 실거래와, 거래가 없을 때 그 까닭을 가를 값."""

    items: list[T]
    has_more: bool
    notes: list[str]
    # 기간(since) 시작일 앞의 거래가 나와 멈췄는지. 그렇다면 기간 앞에는 거래가 있다
    reached_since: bool
    # 받은 원본 거래 수 (기간·거래 유형으로 고르기 전)
    scanned: int
    # 당근이 첫 쪽을 주지 않아(연결이나 edges 가 null) 거래가 없는 것이 아니라 모르는지. 그렇다면 items·has_more 는 모름이라 뜻이 없다
    unknown: bool = False



class DaangnPyeongChoice(NamedTuple):
    """실거래·시세 그래프를 거를 평형. 공급 평형(아파트형)이면 평형 타입 코드를, 아니면 전용면적 묶음을 보낸다."""

    pyeong: int | None
    area_group: int | None
    ptp_cds: list[int] | None



def contract_type_of(contract_type: str | None) -> str | None:
    """전월세 계약 종류(서버 `contractType`·`leaseContractType`)를 한국어 라벨로. 없음은 None, 표에 없는 코드는 원래 코드.

    웹 배지(ComplexTopicPanel `pd`)와 1:1 이다: `RENEWAL` → 재계약, 갱신요구권(`useRenewalOfContractRight`)은 따로
    `renewal_right` 로 낸다 (예전 `renewal` 은 둘을 합쳐 True 로 냈다, #215). 지역 실거래는 계약 종류 없이 오기도 하고, 같은
    거래가 단지 실거래에 NEW·RENEWAL 로 두 번 있기도 하다 (2026-10-10 실측: 봉천동·신림동 등 전월세 약 600건 중 14건이 계약
    종류 없음).
    """
    return code_label(CONTRACT_TYPE_LABELS, contract_type)



def site_note(url: str) -> str:
    """`--limit` 을 늘려도 받을 수 없는 거래를 당근 웹에서 보라는 말 (`collect_pages` 의 `site`)."""
    return f'당근에서 직접 확인하세요: {url}'



def is_rent_type(monthly_rent: int | None, trade_type: str) -> bool:
    """전월세 거래가 고른 유형(전세·월세)인지. 당근이 전세·월세를 섞어 주므로 웹 카드가 전세·월세 표시를 가르는 월세로 가른다.

    월세가 0 보다 크면 월세, 아니면(0·없음) 전세다. 단지·매물 실거래와 지역 실거래가 같은 식을 쓴다 (서버 `type` 은 보지 않는다).
    """
    monthly = (monthly_rent or 0) > 0
    return monthly if trade_type == '월세' else not monthly



def collect_pages(
    fetch: PageFetch[T],
    matches: Callable[[T], bool],
    trade_type: str,
    limit: int,
    *,
    site: str,
    remaining: str = '더 오래된 거래가 남아 있습니다',
    since: str | None = None,
    date_of: Callable[[T], str | None] | None = None,
) -> Collected[T]:
    """실거래를 받은 순서(최근 순)대로 `limit` 건까지 모은다. 단지·매물 실거래와 지역 실거래가 함께 쓴다.

    매매는 필요한 만큼만 받고, 전세·월세는 당근이 전월세를 섞어 주므로 50건씩 최근 1200건까지 넘겨 보며
    `matches` 로 고른다. 커서가 반복되거나 다음 페이지가 비면 안내하고 멈춘다.

    Args:
        fetch: (받을 수, 커서) → (한 페이지의 거래, 페이지 정보). 당근이 그 페이지를 주지 않았으면 거래를 None 으로 준다.
        matches: 검색한 거래 유형의 거래인지.
        trade_type: 매매, 전세, 월세.
        limit: 최대 거래 수.
        site: `--limit` 을 늘려도 받을 수 없는 거래가 남았을 때 안내 끝에 붙일 말. 당근 웹에서 볼 수 있는 거래면 그 페이지로 보내고
            (`site_note`), 웹에도 없는 거래면 보낼 곳이 없으니 더 받을 수 없다고 알린다.
        remaining: 그 안내의 앞말 (예: '더 오래된 거래가 남아 있습니다'). `since` 의 기간 시작일에 닿기 전에 멈췄으면 쓰지
            않고 받지 못한 기간을 알린다.
        since: 이날(YYYY-MM-DD)보다 앞선 거래는 빼고, 그런 거래가 나온 페이지에서 멈춘다. 당근은 기간을 받지 않아
            최근 계약 순으로 넘기다 멈춘다 (계약 순으로 오는 단지·매물 실거래만 준다). 날짜를 모르는 거래는 남긴다.
        date_of: `since` 와 견줄 거래의 계약일.

    Returns:
        거래, 더 있는지, 안내와 함께 기간 시작일 앞에서 멈췄는지·받은 원본 거래 수 (`Collected`). 뒤의 둘은 빈 결과의
        까닭을 가르는 데 쓴다 (`_empty_result_note`). 첫 쪽을 주지 않았으면 `unknown` 이 True 인 빈 결과다.
    """
    buy = trade_type == '매매'
    collected: list[T] = []
    after = None
    has_more = False
    # 마지막으로 받은 쪽에서 서버가 다음 쪽이 있다고 했는지. 기간(since) 밖에서 멈췄으면 남은 거래는 찾는 거래가 아니라 False
    server_more = False
    # 기간(since) 시작일 앞의 거래가 나와 멈췄는지, 마지막으로 센 쪽의 가장 오래된 계약일 (기간을 다 받지 못했을 때 알린다)
    reached_since = False
    oldest: str | None = None
    scanned = 0
    pages = 0
    notes: list[str] = []
    for pages in range(1, REAL_PRICE_MAX_PAGES + 1):
        size = min(REAL_PRICE_PAGE_SIZE, limit - len(collected)) if buy else REAL_PRICE_PAGE_SIZE
        fetched, page_info = fetch(size, after)
        if fetched is None:
            if after is None:
                # 첫 쪽부터 주지 않았으면 거래가 없는 것이 아니라 모르는 것이다 (빈 결과로 내면 '없음' 으로 읽힌다)
                return Collected([], False, [], False, 0, unknown=True)
            # 이어 받는 쪽을 주지 않았으면 페이지 정보가 없는 쪽과 같게 다룬다 (아래 stalled_page 가 멈춤 안내를 붙이고 멈춘다)
            fetched, page_info = [], None
        nodes = fetched
        server_more = bool(page_info and page_info.has_next_page)
        # 커서가 되풀이되거나 페이지 정보가 없으면(stalled_page) 그 쪽을 세기 전에 멈춘다. 거래에는 ID 가 없어 단지 목록처럼 같은 쪽을 걸러 낼 수 없다. 아래
        # next_cursor 도 되풀이를 보지만 그때는 이미 그 쪽을 센 뒤라 여기서 먼저 본다 (2026-11-10 리뷰가 두 검사가 겹친다고
        # 했으나, 실제 응답의 커서만 되풀이되게 바꿔 보니 늘 이 검사에서 걸려 거래 수에 다시 더해지지 않았다. next_cursor 는
        # 단지 후보·지역 단지와 함께 쓰는 도우미라 되풀이 검사를 빼지 않는다).
        # 멈춘 까닭은 [참고] 이고, 더 있다는 [일부] 는 함수 끝의 안내 하나에만 붙인다 (아래 멈춤 안내도 같다).
        # 서버가 다음 쪽이 없다고 했으면 되풀이로 보지 않고 마지막 쪽으로 받는다. 보면 끝난 목록을 '다음 페이지가 있다고 하면서'
        # 멈췄다고 하고 has_more 를 true 로 냈으며 마지막 쪽 거래도 뺐다 (2026-11-10 리뷰·실측: 역삼IPARK 10699288 매매 474건의
        # 마지막 10쪽 커서만 요청 커서로 바꾸니 450건·has_more true. 실제 응답은 50건씩·79건씩 모두 마지막 쪽이 hasNextPage
        # false 에 새 커서였고, 끝 뒤를 요청하면 edges 0·endCursor null 이었다)
        if stalled_page(page_info, after):
            has_more = True
            notes.append(note('참고', cursor_stopped_note('실거래', f'{scanned}건')))
            break
        scanned += len(nodes)
        if date_of is not None and nodes:
            oldest = date_of(nodes[-1]) or oldest
        kept = nodes
        if since is not None and date_of is not None:
            kept = [node for node in nodes if (day := date_of(node)) is None or day >= since]
        collected += [node for node in kept if matches(node)]
        has_more = server_more or len(collected) > limit
        if len(kept) < len(nodes):
            # 최근 계약 순이라 기간보다 앞선 거래가 나오면 그 뒤도 모두 기간 밖이다. 3년치를 보려고 --limit 1200 으로 전부 받으면
            # 2018년 거래까지 938건(약 5만 토큰)이 왔다 (2026-10-31 에이전트 검증, 헬리오시티 84㎡ 매매. 3년 안은 452건)
            has_more = len(collected) > limit
            server_more = False
            reached_since = True
            break
        if len(collected) >= limit or not has_more or page_info is None:
            break
        cursor = next_cursor(page_info, after, received=len(nodes))
        if cursor is None:
            notes.append(note('참고', cursor_stopped_note('실거래', f'{scanned}건')))
            break
        after = cursor

    if not buy and has_more and len(collected) < limit:
        # 몇 건 중에서 골랐는지 설명이라 [참고] 다. 당근 사이트로 가라는 말은 아래 [일부] 안내 하나에만 둔다 (2026-11-10 리뷰·
        # 실측: 헬리오시티 월세 --limit 1200 에 이 안내의 '더 오래된 거래는 당근 사이트에서 확인하세요' 와 [일부] 의 '당근에서
        # 직접 확인하세요: URL' 이 함께 나왔다. 커서가 멈추면 멈춤 안내의 '나머지는 당근에서 확인하세요' 까지 세 번이었다)
        notes.append(note('참고', f'최근 전월세 실거래 {scanned}건 중 {trade_type} {len(collected)}건입니다'))
    if since is not None and not reached_since:
        # 기간 시작일에 닿기 전에 멈췄으면(24쪽 상한·--limit 최대값·쪽 멈춤) 남은 거래는 기간 안이다. '더 오래된 거래가 남아
        # 있습니다' 는 기간보다 오래된 거래로 읽혀, 에이전트가 2026-01-10 까지 받은 결과를 '최근 1년' 이라고 전했다 (2026-11-11
        # LLM 사용 시험: 헬리오시티 10667600 월세 --years 1 --limit 1200 은 2026-01-10 까지 756건)
        more_note = (
            f'요청한 기간({since}부터) 중 {oldest} 이전 거래는 받지 못했습니다. {site}' if oldest
            else f'요청한 기간({since}부터)의 거래를 다 받지 못했습니다. {site}'
        )
    else:
        more_note = f'{remaining}. {site}'
    # 받은 거래를 --limit 으로 잘랐으면 이 안내가 '더 있다' 와 '--limit 을 늘리라' 를 함께 말한다. 그때 아래 '--limit 을 늘리면'
    # 안내를 또 붙이면 [일부] 가 둘이 된다 (2026-11-10 실측: 헬리오시티 월세 --limit 3 에 '32건 중 3건만' 과 '거래가 더 남아 있습니다')
    truncated = truncation_notes(len(collected), limit, subject='실거래', max_limit=REAL_PRICE_MAX_LIMIT)
    notes += truncated
    # 아래 두 분기의 조건을 '늘릴 수 있는지' 하나로 모으지 않는다. 잘랐으면 `truncation_notes` 가 이미 --limit 을 늘리라고 해서
    # 사이트 안내를 덧붙일지만 정하고, 안 잘랐으면 늘리라는 안내와 사이트 안내 중 하나를 고른다. 묻는 것이 달라 조건도 다르다.
    # `server_more` 는 서버가 다음 쪽이 있다고 했는지만 담아(기간 밖에서 멈추면 False) 24쪽 뒤에 남았는지 보는 데 쓰고,
    # `has_more` 는 --limit 을 넘겨 받았거나 쪽이 멈춘 것도 더 있다고 본다 (2026-11-11 리뷰·실측: 헬리오시티 10667600 매매
    # --limit 3 은 '--limit 을 늘리면', 월세 --limit 3 은 '35건 중 3건만 … 늘리세요' 로 둘 다 맞았다)
    if truncated:
        # 잘랐어도 24쪽까지 보고 서버에 거래가 남았거나 --limit 이 이미 최대값이면, --limit 을 늘려도 받지 못하는 거래가 남아
        # 사이트 안내도 붙인다 (2026-11-10 리뷰·실측: 헬리오시티 월세는 23쪽까지 727건·24쪽 755건이라 --limit 728~754 가
        # 24쪽째에서 잘린다. 늘리라는 안내만 따르면 24쪽을 다시 받고 27건을 더 받은 뒤에야 사이트 안내를 봤다)
        if (pages >= REAL_PRICE_MAX_PAGES and server_more) or limit >= REAL_PRICE_MAX_LIMIT:
            notes.append(note('일부', more_note))
    elif has_more:
        if len(collected) >= limit and pages < REAL_PRICE_MAX_PAGES and limit < REAL_PRICE_MAX_LIMIT:
            # --limit 에서 멈췄으면 늘려서 더 받을 수 있다. 사이트에서 보라는 안내는 페이지 상한까지 보고도 남았거나 --limit 이
            # 이미 최대값일 때만 맞다 (2026-10-11 실측: 헬리오시티 --limit 3 에도 '당근에서 직접 확인' 이 붙었다). 최대값이면
            # 늘리라고 하지 않는다. 서버가 요청보다 많이 주면 24쪽 전에 1200건이 차서, 늘리면 INVALID_ARGUMENT 인데 늘리라고
            # 했다 (2026-11-11 리뷰. 요청한 만큼 주면 1200건은 24쪽째라 아래 사이트 안내로 간다)
            notes.append(note('일부', f'거래가 더 남아 있습니다. --limit 을 늘리면 (최대 {REAL_PRICE_MAX_LIMIT}건) 더 받습니다'))
        else:
            notes.append(note('일부', more_note))
    return Collected(collected[:limit], has_more, notes, reached_since, scanned)



def _supply_choice(column: DaangnCompareComplexModel, group: DaangnCompareAreaGroupModel) -> DaangnPyeongChoice:
    """공급 평 묶음의 평형 타입 코드로 고른 평형.

    평형을 주지 않은 `price-trend` 의 대표 평형도 이 에러로 끝낸다. 모든 평형 평균으로 물러서는 길은 두지 않았다: 2026-11-12
    실측 아파트·주상복합 14곳의 공급 평 묶음에 모두 타입 코드가 있어 한 번도 돌지 않을 코드이고, 생기면 에러가 원인을 알린다
    (2026-11-12 리뷰에서 물러서라고 했으나 그대로 둔다).

    Raises:
        JibsaError: 묶음에 평형 타입 코드가 하나도 없을 때 (UPSTREAM_ERROR). 빈 코드로 보내면 평형을 거르지 않은 전체
            평형 값에 그 평형 이름이 붙는다 (2026-11-12 리뷰).
    """
    ptp_cds = [info.ptp_cd for info in group.py_infos if info.ptp_cd is not None]
    if not ptp_cds:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'당근 단지 {column.original_id} 의 {group.label}평 묶음에 평형 타입 코드가 없어 그 평형만 고를 수 없습니다',
            hint=f'응답 형식이 바뀌었을 수 있습니다. {UPDATE_MAYBE_NEEDED}',
        )
    return DaangnPyeongChoice(group.label, None, ptp_cds)



def choose_pyeong(
    column: DaangnCompareComplexModel,
    *,
    pyeong: int | None = None,
    area_group: int | None = None,
    representative: bool = False,
) -> DaangnPyeongChoice | None:
    """`--pyeong`·`--area` 로 평형을 고른다. 둘 다 없고 `representative` 면 웹처럼 대표 평형 묶음(없으면 첫 묶음)이다.

    None 이면 평형으로 거르지 않는다 (real-price 는 모든 평형의 거래, price-trend 는 웹처럼 그래프 없음). 평형 묶음이 없거나 대표
    묶음에 평형 값(`label`)이 없으면 고를 평형을 알 수 없어 None 이다. 예전에는 값 없는 평형을 골라 거르지 않으면서 '대표
    평형(None㎡)' 이라고 알렸다 (2026-11-12 리뷰. 실측 응답에서 label 이 빈 묶음은 아직 보지 못했다).

    Raises:
        JibsaError: 평형 묶음이 없는 단지에 `pyeong`·`area_group` 을, 아파트형이 아닌 단지에 `pyeong` 을, 아파트형(공급 평
            묶음) 단지에 `area_group` 을 주거나, 단지에 없는 평형·묶음이면 INVALID_ARGUMENT. 고른 공급 평 묶음에 평형 타입
            코드가 없으면 UPSTREAM_ERROR.
    """
    supply, groups = pyeong_groups(column)
    if (pyeong is not None or area_group is not None) and not any(group.label is not None for group in groups):
        # 고를 묶음이 없으면 아래 '있는 평형' 안내가 빈 목록이라 다시 줄 값이 없었다 (2026-11-12 리뷰). 웹도 평형 탭이 없어
        # 고를 수 없다. 옵션을 빼면 real-price 는 전체 평형이지만 price-trend 는 웹처럼 그래프가 없어 명령마다 알린다
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'당근에 단지 {column.original_id} 의 평형 묶음 정보가 없어 평형을 고를 수 없습니다',
            hint='real-price 는 --pyeong·--area 를 빼면 모든 평형의 거래를 봅니다. price-trend 는 당근 웹처럼 이런 단지의 시세 그래프가 없습니다',
        )
    if pyeong is not None:
        if not supply:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'아파트형이 아닌 단지 {column.original_id} 에는 공급 평형(--pyeong)이 없습니다',
                hint=f'jibsa daangn complex {column.original_id} 의 pyeongs[].area_group 을 --area 로 주세요',
            )
        group = next((group for group in groups if group.label == pyeong), None)
        if group is None:
            labels = ', '.join(f'{group.label}평' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'단지 {column.original_id} 에 {pyeong}평 묶음이 없습니다',
                hint=f'있는 평형: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].pyeong)',
            )
        return _supply_choice(column, group)
    if area_group is not None:
        if supply:
            # 웹은 공급 평 묶음이 있는 단지에서는 늘 평형 타입 코드(ptpCds)로만 묻고 전용면적 묶음을 섞지 않는다
            # (ComplexTopicPanel `jd` 의 `s`). 84㎡ 묶음은 32평·33평을 함께 가져 웹의 32평 목록과 달랐다 (2026-11-12 번들 대조)
            labels = ', '.join(f'{group.label}평' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'아파트형 단지 {column.original_id} 에서는 당근 웹처럼 공급 평형(--pyeong)으로만 고릅니다',
                hint=f'--area 대신 --pyeong 을 주세요. 있는 평형: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].pyeong)',
            )
        if all(group.label != area_group for group in groups):
            labels = ', '.join(f'{group.label}㎡' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'단지 {column.original_id} 에 전용 {area_group}㎡ 묶음이 없습니다',
                hint=f'있는 묶음: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].area_group)',
            )
        return DaangnPyeongChoice(None, area_group, None)
    if not representative or not groups:
        return None
    chosen = next((group for group in groups if group.is_representative), groups[0])
    if chosen.label is None:
        return None
    if supply:
        return _supply_choice(column, chosen)
    return DaangnPyeongChoice(None, chosen.label, None)
