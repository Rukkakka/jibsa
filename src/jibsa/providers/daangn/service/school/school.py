"""학교 (school)."""

from jibsa.core.errors import JibsaError
from jibsa.core.korean import (
    particle,
    quoted,
)
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    holding_unread_dates,
    keep_unread_dates,
    more_hint,
    normalize_address,
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.school.school import (
    DaangnSchoolByCodeRequestPayloadModel,
    DaangnSearchSchoolsInputModel,
    DaangnSearchSchoolsRequestPayloadModel,
)
from jibsa.providers.daangn.api.models.response.common import DaangnPageInfoModel
from jibsa.providers.daangn.api.models.response.school.school import (
    DaangnSchoolSearchNodeModel,
)
from jibsa.providers.daangn.service.common.complex import (
    complex_list_notes,
    region_complex_of,
)
from jibsa.providers.daangn.service.common.constants import (
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
)
from jibsa.providers.daangn.service.common.location import coordinate_point
from jibsa.providers.daangn.service.common.models import DaangnRegionComplex
from jibsa.providers.daangn.service.common.response import (
    code_label,
    next_cursor,
    stalled_page,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.school.constants import (
    COEDU_LABELS,
    SCHOOL_AMBIGUOUS_SHOWN,
    SCHOOL_CANDIDATE_LIMIT,
    SCHOOL_CODE_PATTERN,
    SCHOOL_KIND_SHORT_NAMES,
    SCHOOL_NAME_CHECK_MAX_PAGES,
    SCHOOL_TYPE_LABELS,
    SCHOOL_URL,
)
from jibsa.providers.daangn.service.school.models import (
    DaangnSchool,
    DaangnSchoolResult,
)


def _searchable(nodes: list[DaangnSchoolSearchNodeModel]) -> list[DaangnSchoolSearchNodeModel]:
    """좌표가 있는 학교만. 당근 웹 검색창도 좌표 없는 학교를 뺀다 (2026-11-12 실측: '중앙초등학교' 50곳 중 1곳)."""
    return [node for node in nodes if coordinate_point(node.coordinate) is not None]


def _school_page(
    client: DaangnClient, name: str, after: str | None = None
) -> tuple[list[DaangnSchoolSearchNodeModel], DaangnPageInfoModel | None]:
    """이름이 들어간 학교 한 쪽 (`searchSchools`, 요청 1회). 좌표 없는 학교도 섞여 있고, 쪽 정보는 그대로 돌려준다."""
    response = client.run_request_search_schools(
        DaangnSearchSchoolsRequestPayloadModel(
            first=SCHOOL_CANDIDATE_LIMIT, after=after, input=DaangnSearchSchoolsInputModel(name=name)
        )
    )
    found = unwrap_graphql(response, response.data.search_schools if response.data else None, '학교 검색', conditions=False)
    return [edge.node for edge in found.edges if edge.node], found.page_info


def search_school_candidates(client: DaangnClient, name: str) -> tuple[list[DaangnSchoolSearchNodeModel], bool]:
    """이름이 들어간 초·중·고 후보 첫 쪽 (`searchSchools`, 요청 1회). 웹 지도 검색창의 학교 칸이다.

    `search locations` 의 학교 칸이 쓰며 다음 쪽은 받지 않는다. 당근은 이름이 그대로 같은 학교를 맨 앞에 주지만(2026-11-12
    실측: '중앙초등학교' 86곳 중 같은 이름 6곳이 1~6번째, '동산초등학교' 7곳·'신흥초등학교' 3곳·'중앙중학교' 2곳도 맨 앞.
    2026-11-20 에도 같았다), 이름으로 학교 하나를 고르는 `resolve_school` 은 첫 쪽만 보고 같은 이름이 하나라고 정하지 않고
    다음 쪽이 있으면 더 본다 (`_confirm_unique_name`). 잘렸는지는 두 번째 값으로 알린다.

    Returns:
        (좌표가 있는 후보, 서버에 후보가 더 있는지). 후보는 첫 `SCHOOL_CANDIDATE_LIMIT` 곳까지다.
    """
    nodes, page_info = _school_page(client, name)
    return _searchable(nodes), bool(page_info and page_info.has_next_page)


def _confirm_unique_name(
    client: DaangnClient,
    name: str,
    pending: list[tuple[str, DaangnPageInfoModel | None, int]],
    candidates: list[DaangnSchoolSearchNodeModel],
) -> bool:
    """이름이 똑같은 학교가 하나뿐인지, 다음 쪽이 있던 검색어마다 다음 쪽을 이어 받아 확인한다. 끝까지 봤으면 True.

    같은 이름이 둘 이상 나오면 바로 멈추고(True. 호출부가 여럿으로 다룬다), `candidates` 에 받은 학교를 더한다. 검색어마다 첫 쪽
    포함 `SCHOOL_NAME_CHECK_MAX_PAGES` 쪽까지만 보고, 그래도 다음 쪽이 남았거나 다음이 있다면서 커서가 없거나·되풀이되거나·빈
    쪽이거나 쪽 정보가 없으면(`next_cursor`·`stalled_page`) 다 보지 못한 것이라 False 다. 요청이 실패하면 첫 쪽과 같게 올린다.

    Args:
        pending: 다음 쪽이 있다던 검색어와 그 첫 쪽의 쪽 정보, 그 쪽에서 받은 학교 수.
    """
    for query, page_info, received in pending:
        after: str | None = None
        for _ in range(SCHOOL_NAME_CHECK_MAX_PAGES - 1):
            cursor = next_cursor(page_info, after, received=received)
            if cursor is None:
                return False
            nodes, page_info = _school_page(client, query, cursor)
            if stalled_page(page_info, cursor):
                return False
            after, received = cursor, len(nodes)
            seen = {school.sch_cd for school in candidates}
            candidates += [school for school in _searchable(nodes) if school.sch_cd not in seen]
            if sum(school.sch_nm == name for school in candidates) > 1:
                return True
            if not (page_info and page_info.has_next_page):
                break
        else:
            return False
    return True


def _school_not_found(name: str) -> JibsaError:
    return JibsaError(
        code='NOT_FOUND',
        message=f"당근에서 '{name}' 학교를 찾지 못했습니다",
        hint="당근 학교 이름은 '서울대치초등학교' 처럼 시·도가 붙기도 합니다. '대치초' 처럼 줄이거나 시·도를 붙여 다시 찾으세요",
    )


def resolve_school(client: DaangnClient, name: str) -> str:
    """학교 이름이나 학교 코드로 학교 코드 하나를 고른다 (`searchSchools`, 보통 요청 1~2회, 이름이 같은 학교 하나에 다음 쪽이 있으면 검색어마다 최대 2회 더. 코드면 요청 없음).

    당근 웹 검색창처럼 이름이 들어간 학교를 한 번 찾고, 좌표 없는 학교는 뺀다. 웹은 후보를 보여 주고 사람이 고르므로 jibsa 도
    여럿이면 고르지 않고 후보(이름·주소·학교 코드)를 알린다. 예전에는 첫 후보를 저절로 골라 엉뚱한 지역 학교로 답할 수 있었고
    `--city` 로 주소를 걸렀다 (#215). 이름이 그대로 같은 학교가 하나뿐이면 그 학교다.
    검색 결과에 다음 쪽이 남았는데 확인하지 못했으면 후보가 하나여도 고르지 않는다.

    '○○초등학교' 처럼 종류 이름까지 주면 줄임('○○초')으로도 한 번 더 찾아 합친다 (`SCHOOL_KIND_SHORT_NAMES`). 당근 웹에는 없는
    jibsa 개선이다. 당근 검색은 '대치초등학교' 로 서울대치초등학교를 못 찾고(웹도 0건) '대치초' 로는 찾는다 (2026-11-12 실측,
    #133. 2026-11-12 사용자 결정으로 남김). 첫 검색에 이름이 그대로 같은 학교가 하나면 더 찾지 않는다. 줄임 검색이 더 찾는 학교
    중 이름이 그대로 같은 학교는 첫 검색에도 나와 답이 같고, 요청만 하나 더 쓴다 (2026-11-12 리뷰). 같은 이름 학교가 여럿이면
    후보를 알리므로 줄임 검색까지 해 후보에 넣는다. 첫 검색만 보면 '도곡초등학교' 의 후보가 경기 광주·화순 두 곳뿐이고
    서울도곡초등학교가 빠졌다 (2026-11-13 리뷰·실측).

    이름이 똑같은 학교가 하나뿐이어도 검색 결과에 다음 쪽이 있으면 뒤쪽에 같은 이름 학교가 또 있을 수 있어, 다음 쪽을 이어 받아
    세고(`_confirm_unique_name`, 검색어마다 첫 쪽 포함 `SCHOOL_NAME_CHECK_MAX_PAGES` 쪽까지) 하나뿐일 때만 정한다. 같은 이름이 더
    나오면 여럿으로 알리고, 쪽 상한까지 봐도 다음 쪽이 남으면 고르지 않는다 (2026-11-20 사용자 결정).

    Raises:
        JibsaError: 학교를 찾지 못했을 때 (NOT_FOUND), 여럿일 때 (REGION_AMBIGUOUS. 지역 후보와 같은 코드라 에이전트가 같은 방법으로
            고르고, `candidates` 에는 학교마다 이름·주소·학교 코드가 있다).
    """
    # 앞뒤·사이 공백을 정리한다. 웹 검색창도 trim 해서 보내고, 공백이 붙으면 학교 코드 판정(fullmatch)과 이름 비교(==·endswith)가
    # 틀어진다 (' B100000749' 가 NOT_FOUND, '도곡초등학교 ' 가 줄임 검색·정확 일치 실패). 비면 못 찾은 것과 같다
    original = name
    name = ' '.join(name.split())
    if not name:
        raise _school_not_found(original)
    if SCHOOL_CODE_PATTERN.fullmatch(name):
        return name.upper()
    queries = [name]
    for kind, short in SCHOOL_KIND_SHORT_NAMES:
        if name.endswith(kind) and len(name) > len(kind):
            queries.append(name.removesuffix(kind) + short)
            break
    candidates: list[DaangnSchoolSearchNodeModel] = []
    # 후보가 다 오지 않았으면 True ('N곳 이상')
    truncated = False
    # 다음 쪽이 있던 검색어: (검색어, 첫 쪽의 쪽 정보, 첫 쪽에서 받은 학교 수). 이름이 같은 학교가 하나일 때 `_confirm_unique_name` 이 본다
    pending: list[tuple[str, DaangnPageInfoModel | None, int]] = []
    for query in queries:
        nodes, page_info = _school_page(client, query)
        has_more = bool(page_info and page_info.has_next_page)
        if has_more:
            pending.append((query, page_info, len(nodes)))
        seen = {school.sch_cd for school in candidates}
        candidates += [school for school in _searchable(nodes) if school.sch_cd not in seen]
        truncated = truncated or has_more
        # 이름이 같은 학교가 하나면 그 학교라 줄인 이름으로 더 찾지 않는다. 여럿이면 후보 목록이 되므로 줄인 이름으로만 나오는
        # 학교('서울도곡초등학교')까지 넣는다 (2026-11-13 리뷰: 여럿일 때도 멈춰 후보에서 빠졌다)
        if sum(school.sch_nm == name for school in candidates) == 1:
            break
    if not candidates:
        raise _school_not_found(name)
    # 이름이 똑같은 학교가 하나뿐이라도 다음 쪽에 같은 이름이 더 있을 수 있어 다음 쪽이 있던 검색어는 이어 받아 센다 (2026-11-20 사용자 결정)
    checked = True
    if pending and sum(school.sch_nm == name for school in candidates) == 1:
        checked = _confirm_unique_name(client, name, pending, candidates)
    # 같은 이름 학교를 맨 앞에 둔다 (이어 받은 쪽에서 나온 학교가 후보 10곳 밖으로 밀리지 않게). 서버도 같은 이름을 앞에 준다
    exact = [school for school in candidates if school.sch_nm == name]
    candidates = exact + [school for school in candidates if school.sch_nm != name]
    # 이름이 같은 학교가 하나면 다음 쪽까지 확인했을 때만, 이름이 같지 않은 후보 하나(줄임 검색으로만 나온 학교)면 검색 결과에 다음 쪽이
    # 남지 않았을 때만 고른다 (남았으면 다른 후보가 더 있을 수 있다)
    if (len(exact) == 1 and checked) or (not exact and len(candidates) == 1 and not truncated):
        return (exact or candidates)[0].sch_cd
    shown = [
        {'name': school.sch_nm, 'address': school.sch_addr, 'school_code': school.sch_cd}
        for school in candidates[:SCHOOL_AMBIGUOUS_SHOWN]
    ]
    if len(exact) == 1:
        # 같은 이름이 하나뿐이지만 쪽 상한에 닿거나 쪽 넘김이 멈춰 뒤에 같은 이름이 더 있는지 알 수 없다. 고르면 엉뚱한 학교일 수 있다
        raise JibsaError(
            code='REGION_AMBIGUOUS',
            message=(
                f"{quoted(name, '이/가')} 들어간 학교가 {len(candidates)}곳 이상이라, "
                '이름이 같은 학교가 더 있을 수 있어 고르지 않았습니다'
            ),
            hint=f'찾는 학교가 맞으면 school_code 로 다시 부르세요 (예: jibsa daangn school {exact[0].sch_cd})',
            details={'candidates': shown, 'candidate_count': None},
        )
    count = f"{len(candidates)}곳{' 이상' if truncated else ''}"
    raise JibsaError(
        code='REGION_AMBIGUOUS',
        message=f"{quoted(name, '이/가')} 들어간 학교가 {count}이라 고르지 않았습니다",
        hint=f"candidates 의 school_code 로 다시 부르세요 (예: jibsa daangn school {shown[0]['school_code']})",
        # 다 받지 못했으면 전체 수를 모른다 (모름 → null)
        details={'candidates': shown, 'candidate_count': None if truncated else len(candidates)},
    )


def get_school(
    client: DaangnClient,
    name: str,
    *,
    complex_types: list[str] | None = None,
    household_min: int | None = None,
    limit: int = 120,
) -> DaangnSchoolResult:
    """학교 정보와 그 학교에 배정되는 단지를 받는다 (`searchSchools` → `schoolByCode`, 요청 2회. 학교 찾기 요청 수는 `resolve_school`).

    배정 단지는 초등학교에만 있다 (중·고등학교는 학교군 배정). 당근 웹 학교 화면(SchoolDetail)처럼 서버가 준 순서 그대로
    보여 주고, 단지마다 최근 매매 실거래는 취소되지 않은 첫 1건이다 (ComplexListItem). 예전에는 세대수 많은 순으로 다시 세우고
    3건을 붙였다 (#215, 2026-11-12 실측: 대치초 15곳에서 래미안대치팰리스가 웹은 맨 뒤, jibsa 는 맨 앞). `complex_types`
    ('아파트' 는 주상복합 포함)·`household_min`·`limit` 은 서버가 받지 않는 조건이라 그 순서에서 거르고 자른다. 단지 유형이나
    세대수를 몰라 조건을 확인할 수 없는 단지는 빼고 그 수를 [제외] 로 알리며, 맞는지 모르는 단지가 있으니 `total` 은
    null 이다. 조건에 맞지만 단지 ID 가 없는 단지도 빼고 [제외] 로 알리되 `total` 에는 센다. 당근이 배정 단지를
    주지 않으면(null) `complexes`·`total` 을 null 로 낸다.

    Raises:
        JibsaError: 학교를 찾지 못했을 때 (NOT_FOUND), 여럿일 때 (REGION_AMBIGUOUS), GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 웹이 학교 쿼리를 바꿨을 때.
    """
    school_code = resolve_school(client, name)
    response = client.run_request_school_by_code(DaangnSchoolByCodeRequestPayloadModel(sch_cd=school_code))
    if response.data is not None and response.data.school_by_code is None and not response.errors:
        # 없는 학교 코드는 HTTP 200 에 schoolByCode: null 이다 (2026-11-12 실측: B199999999)
        raise JibsaError(
            code='NOT_FOUND',
            message=f'당근에 없는 학교 코드입니다: {school_code}',
            hint='학교 이름으로 찾거나 jibsa daangn search locations <학교 이름> 의 schools 에서 school_code 를 확인하세요',
        )
    detail = unwrap_graphql(response, response.data.school_by_code if response.data else None, '학교 정보', conditions=False)
    notes: list[str] = []

    types: set[str] = set()
    for label in complex_types or []:
        code = COMPLEX_TYPE_FILTER_BY_LABEL[label]
        # 단지 목록의 '아파트' 처럼 주상복합도 함께 본다
        types |= {code, 'MIXED_USE'} if code == 'APARTMENT' else {code}
    # 배정 단지를 주지 않았으면(null) 빈 목록([])과 다른 모름이다 (`list_preschools` 의 근처 시설과 같다)
    assigned = detail.assigned_complexes
    complexes: list[DaangnRegionComplex] = []
    # complexes 와 같은 차례로 맡아 둔 못 읽은 날짜. 자른 뒤 보여 주는 단지의 것만 안내에 센다
    held: list[list[tuple[str, str]]] = []
    # 조건을 확인할 수 없어 뺀 단지 수와 그때 몰랐던 칸. 단지 유형(-t)이나 세대수(--household-min)를 모르면 조건에 맞는지 알 수 없어
    # 빼되 센다 (조용히 빼면 알리지 않은 채 결과가 줄어든다). 다른 조건이 이미 틀린 단지는 모르는 칸과 상관없이 빠지니 세지 않는다
    unknown_count = 0
    unknown_columns: set[str] = set()
    # 조건에 맞지만 당근이 단지 ID 를 주지 않아 뺀 단지 수 (ID 가 없으면 가리킬 수 없다)
    no_id_count = 0
    # 배정 단지 목록에서 빈 항목을 뺐으면 단지 수를 알 수 없다 (null). 안내 문장의 수도 뺀다. 조건을 확인하지 못한 단지가 있어도 수를
    # 모른다 (null). ID 가 없는 단지는 조건에 맞는 것이 확실해 total 에 센다
    dropped = detail.null_items('assigned_complexes')
    for node in assigned or []:
        checks: list[tuple[str, bool | None]] = []
        if types:
            node_type = (node.type or '').strip()
            checks.append(('유형', None if node_type in ('', '-') else node_type in types))
        # 세대수 하한이 0 이하면 모든 단지가 만족해 아무것도 빼지 않는다 (세대수를 모르는 단지도)
        if household_min is not None and household_min > 0:
            households = node.danji.households if node.danji else None
            checks.append(('세대수', None if households is None else households >= household_min))
        if any(matched is False for _, matched in checks):
            continue
        unknown = [column for column, matched in checks if matched is None]
        if unknown:
            unknown_count += 1
            unknown_columns.update(unknown)
            continue
        if node.original_id is None:
            no_id_count += 1
            continue
        with holding_unread_dates() as dates:
            complexes.append(region_complex_of(node, '매매', max_trades=1))
        held.append(dates)

    # 배정 단지가 있는지를 먼저 본다. 학교 유형 안내는 배정 단지가 없을 때만 붙인다 (유형을 모르는 학교에 단지가 오면 목록과
    # '단지 목록이 없습니다' 가 함께 나가고 --limit 으로 잘려도 [일부] 가 빠졌다)
    if assigned is None:
        notes.append(note('실패', f'당근이 이 학교의 배정 단지 정보를 주지 않았습니다. API 가 바뀌었을 수 있어 {UPDATE_MAYBE_NEEDED}'))
    elif not assigned and not dropped:
        # 빈 항목만 와서 목록이 빈 것은 배정 단지가 없는 것이 아니라 모름이라 이 안내 대신 아래 [제외] 만 낸다
        if detail.sch_type in ('MIDDLE', 'HIGH'):
            notes.append('배정 단지는 초등학교에만 있습니다. 중·고등학교는 학교군으로 배정돼 단지 목록이 없습니다')
        else:
            notes.append('당근에 이 학교의 배정 단지 정보가 없습니다')
    else:
        if unknown_count:
            columns = '·'.join(column for column in ('유형', '세대수') if column in unknown_columns)
            marker = particle(columns, '을/를')
            # dropped 가 있으면 아래 null_items_note 가 이미 total 이 null 이라고 말한다
            total_null = '' if dropped else '. 조건에 맞는 단지 수를 몰라 total 은 null 입니다'
            notes.append(note('제외', f'{columns}{marker} 몰라 조건을 확인할 수 없는 단지 {unknown_count}곳은 뺐습니다{total_null}'))
        if no_id_count:
            # total 이 숫자로 나갈 때만 ID 없는 단지를 센다고 알린다
            counted = '' if unknown_count or dropped else ' (total 에는 셉니다)'
            notes.append(note('제외', f'당근이 단지 ID 를 주지 않은 {no_id_count}곳은 뺐습니다{counted}'))
        if not complexes:
            # 안내가 없으면 배정 단지가 없는 학교와 구별되지 않았다 (2026-11-12 리뷰). 조건을 확인하지 못해 뺀 단지, ID 가 없어 뺀
            # 단지, 빈 항목으로 와서 뺀 단지가 있으면 조건에 맞는 곳이 없다고 단정할 수 없어 [제외] 안내만 남긴다
            if not unknown_count and not no_id_count and not dropped:
                notes.append(note(
                    '참고',
                    f'배정 단지 {len(assigned)}곳 중 단지 유형(-t)·세대수(--household-min) 조건에 맞는 곳이 없습니다',
                ))
        elif len(complexes) > limit:
            count = '' if dropped or unknown_count else f' {len(complexes) + no_id_count}곳'
            notes.append(note(
                '일부',
                f'배정 단지{count} 중 당근 순서로 앞 {limit}곳만 보여 줍니다. '
                + more_hint(limit, COMPLEX_LIST_MAX_LIMIT, '단지 유형(-t)·세대수(--household-min) 조건'),
            ))
    if dropped:
        notes.append(null_items_note('당근 배정 단지', dropped, ('total',)))
    shown = complexes[:limit]
    for dates in held[:len(shown)]:
        keep_unread_dates(dates)
    return DaangnSchoolResult(
        school=DaangnSchool(
            school_code=detail.sch_cd,
            name=detail.sch_nm,
            school_type=code_label(SCHOOL_TYPE_LABELS, detail.sch_type),
            address=normalize_address(detail.sch_addr),
            foundation=detail.fond_sch_cd,
            coed=code_label(COEDU_LABELS, detail.coedu),
            students=detail.tot_std_cnt,
            students_per_class=detail.cls_std_cnt,
            students_per_teacher=detail.tch_std_cnt,
            base_year=int(detail.student_std_date) if detail.student_std_date and detail.student_std_date.isdecimal() else None,
        ),
        total=(
            len(complexes) + no_id_count if assigned is not None and not dropped and not unknown_count else None
        ),
        returned=len(shown),
        complexes=shown if assigned is not None else None,
        url=SCHOOL_URL.format(detail.sch_cd),
        notes=notes + complex_list_notes(shown),
    )
