"""학교·어린이집 (school, preschools, preschool)."""

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.korean import (
    particle,
    quoted,
)
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    js_round,
    more_hint,
    normalize_address,
    normalize_date,
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.school import (
    DaangnComplexSchoolsRequestPayloadModel,
    DaangnPreschoolByNoRequestPayloadModel,
    DaangnSchoolByCodeRequestPayloadModel,
    DaangnSearchSchoolsInputModel,
    DaangnSearchSchoolsRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import DaangnPageInfoModel
from jibsa.providers.daangn.api.response.school import DaangnSchoolSearchNodeModel
from jibsa.providers.daangn.service.common import (
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    DaangnRegionComplex,
    code_label,
    complex_list_notes,
    complex_not_found,
    complex_url,
    coordinate_point,
    next_cursor,
    region_complex_of,
    stalled_page,
    unwrap_graphql,
)

from typing import Annotated


# 학교 (당근 웹 표기)
SCHOOL_TYPE_LABELS: dict[str, str] = {'ELEMENTARY': '초등학교', 'MIDDLE': '중학교', 'HIGH': '고등학교', 'ETC': '기타'}
COEDU_LABELS: dict[str, str] = {'MALE': '남학교', 'COED': '남녀공학', 'FEMALE': '여학교'}
# 학교 이름 검색이 한 번에 받는 후보 수. 웹 검색창은 4곳씩 넘기지만 한 번에 더 받는다 ('중앙초등학교' 는 전국에 86곳이다)
SCHOOL_CANDIDATE_LIMIT: int = 50
# 이름이 똑같은 학교가 하나뿐일 때 같은 이름이 더 있는지 보려고 검색어마다 받는 쪽 수 (첫 쪽 포함, 50곳씩 150곳). 같은 이름 학교는
# 첫 쪽 맨 앞에 오지만(2026-11-20 실측: '중앙초등학교' 86곳·2쪽에서 이름이 똑같은 6곳이 모두 첫 쪽 1~6번째, '중앙초' 도 86곳·2쪽)
# 서버가 늘 그렇게 준다는 보장은 없어, 다음 쪽이 있으면 3쪽까지 보고 그래도 남으면 고르지 않는다 (2026-11-20 사용자 결정)
SCHOOL_NAME_CHECK_MAX_PAGES: int = 3
# 학교 코드 (당근·학교알리미, 2026-11-12 실측: 52곳 모두 지역 글자 하나 + 숫자 9자리, 예: B100000749). 소문자로 줘도 코드로
# 보고 대문자로 바꾼다
SCHOOL_CODE_PATTERN: re.Pattern[str] = re.compile(r'[A-Za-z]\d{9}')
# 학교가 여럿일 때 에러에 실을 후보 수
SCHOOL_AMBIGUOUS_SHOWN: int = 10
# 학교 종류 이름과 그 줄임. 당근 검색은 '○○초등학교' 로 '서울○○초등학교' 를 찾기도 못 찾기도 해서 줄임으로 한 번 더 찾는다
# (2026-10-23 실측: '대치초등학교' 0건·'대치초' 서울대치초등학교, '도곡초등학교' 는 경기 광주·화순 도곡초등학교만이고
# '도곡초' 에는 서울도곡초등학교도 나온다, '역삼초등학교' 는 서울역삼초등학교. 진선여자고·숙명여자중·단국대학교사범대학부속중
# 처럼 줄인 이름은 시험한 학교 모두 원래 이름의 결과를 포함했다)
SCHOOL_KIND_SHORT_NAMES: tuple[tuple[str, str], ...] = (('초등학교', '초'), ('중학교', '중'), ('고등학교', '고'))


class DaangnSchool(BaseModel):
    """학교 정보 (학교알리미 공시 기준). 전화·홈페이지·좌표는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='당근 학교 코드 (school 에 다시 넘길 수 있다)')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    school_type: Annotated[
        str | None,
        Field(description='초등학교 / 중학교 / 고등학교 / 기타')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    foundation: Annotated[
        str | None,
        Field(description='설립 구분 (공립, 사립 ...)')
    ] = None
    coed: Annotated[
        str | None,
        Field(description='남녀공학 / 남학교 / 여학교')
    ] = None
    students: Annotated[
        int | None,
        Field(description='전체 학생 수')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None
    base_year: Annotated[
        int | None,
        Field(description='학생 수 기준 연도 (예: 2026). 당근이 주지 않으면 null')
    ] = None


class DaangnSchoolResult(BaseModel):
    """학교 정보와 배정 단지."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school: Annotated[
        DaangnSchool,
        Field(description='학교')
    ]
    total: Annotated[
        int | None,
        Field(description='조건에 맞는 배정 단지 수 (limit 적용 전. 당근이 단지 ID 를 주지 않아 complexes 에서 뺀 단지도 센다). 당근이 배정 단지를 주지 않았거나 빈 항목을 줬거나, 단지 유형·세대수를 몰라 조건을 확인할 수 없는 단지가 있으면 null (모름)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex] | None,
        Field(description='배정 단지 (당근 웹 학교 화면과 같은 순서). recent_trades 는 최근 매매 1건이다. 배정 단지가 없으면 [], 당근이 배정 단지를 주지 않았으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 학교 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='배정 단지 안내 (중·고등학교, 정보 없음, 조건·limit 으로 줄임, 조건을 확인할 수 없어 뺀 단지). CLI 가 결과 위에 붙인다')
    ] = []


def school_url(school_code: str) -> str:
    return f'https://realty.daangn.com/schools/{school_code}'


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
        complexes.append(region_complex_of(node, '매매', max_trades=1))

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
        url=school_url(detail.sch_cd),
        notes=notes + complex_list_notes(shown),
    )


# 어린이집·유치원 종류 (당근 표기). 상세(preschoolByNo)에만 온다
PRESCHOOL_LABEL_BY_TYPE: dict[str, str] = {'DAYCARE': '어린이집', 'KINDERGARTEN': '유치원'}
# 당근이 단지 근처 어린이집·유치원을 주는 범위: 단지에서 1km 안을 가까운 순으로 20곳까지 (2026-11-11 실측, 예전 반경 쿼리
# educationMapPoints 와 대조: 역삼래미안 10697092 는 1km 안 31곳 중 0.6km 안의 20곳, 양평역한라비발디2단지 20839190 은
# 1km 안 11곳 모두이고 1.23km 부터 빠짐)
PRESCHOOL_SERVER_RADIUS_KM: float = 1.0
PRESCHOOL_SERVER_MAX: int = 20
# 당근 웹 거리 계산(services2 하버사인)의 지구 반지름 (km)
WEB_EARTH_RADIUS_KM: float = 6371.0


class DaangnPreschoolSummary(BaseModel):
    """단지 근처 어린이집·유치원 하나 (목록). 어린이집·유치원 구분은 목록에 없어 preschool 상세에서 본다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    preschool_id: Annotated[
        str,
        Field(description='시설 번호 (preschool 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='단지에서 직선거리 (m, 웹과 같은 반올림). 단지나 시설 좌표가 없으면 null')
    ] = None
    resident_count: Annotated[
        int | None,
        Field(description='이 단지 주민 중 다니는 수 (당근 집계)')
    ] = None
    review_count: Annotated[
        int,
        Field(description='당근 설문 후기 수')
    ]


class DaangnPreschoolsResult(BaseModel):
    """단지 근처 어린이집·유치원 목록 (당근 단지 화면 학군의 유치원 탭)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 시설 수. 당근은 단지에서 1km 안을 가까운 순으로 20곳까지 준다')
    ]
    preschools: Annotated[
        list[DaangnPreschoolSummary] | None,
        Field(description='이 단지 주민이 많이 다니는 순, 같으면 가까운 순 시설. 당근이 근처 시설 정보를 주지 않으면 null (모름)')
    ]
    url: Annotated[
        str,
        Field(description='당근 단지 페이지 (학군에 같은 목록이 있다)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='정보 없음·빈 결과·20곳 한도 안내. CLI 가 결과 위에 붙인다')
    ] = []


def list_preschools(client: DaangnClient, complex_id: int) -> DaangnPreschoolsResult:
    """단지 근처 어린이집·유치원을 당근 단지 화면(학군 → 유치원 탭)과 같은 목록·순서로 준다 (`complexByOriginalId`, 요청 1회).

    당근 웹은 범위 안 시설을 지도에 띄우던 쿼리(`EducationPoiLayerQuery`)를 없애고 단지마다 근처 시설 목록만 준다
    (2026-11-10 번들 대조). 당근은 단지에서 1km 안을 가까운 순으로 20곳까지 주고(`PRESCHOOL_SERVER_MAX`), 20곳을 받으면
    더 있을 수 있어 [일부] 로 알린다. 출력 순서가 거리 순이 아니라 잘린 것이 결과만으로는 보이지 않는다. 순서는 웹처럼 이 단지 주민이 많이 다니는 곳 먼저, 같으면 가까운 곳 먼저다. 거리도 웹처럼 학군 정보의 단지 좌표(없으면
    단지 좌표)에서 시설까지 직선거리다. 어린이집·유치원 구분은 오지 않는다.

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
    """
    response = client.run_request_complex_schools(DaangnComplexSchoolsRequestPayloadModel(complex_id=str(complex_id)))
    result = unwrap_graphql(
        response, response.data.complex_by_original_id if response.data else None, '단지 근처 어린이집·유치원', conditions=False
    )
    if result.complex is None:
        raise complex_not_found(complex_id)
    danji = result.complex.proptier_danji
    origin = (coordinate_point(danji.coordinate) if danji else None) or coordinate_point(result.complex.coordinate)
    # 학군 정보(proptierDanji)나 근처 시설 목록이 null 이면 모름이다. 웹(ComplexSchoolSection `nearbyPreschools??[]`)은 빈 목록과
    # 똑같이 유치원 탭을 비우지만, 출력은 complex·compare 의 학교처럼 모름(null)과 빈 목록([])을 나눈다
    nearby = danji.nearby_preschools if danji else None
    # (웹이 견주는 미터 정수 거리, 시설). 출력의 distance_m 도 그 미터 거리다
    rows: list[tuple[int | None, DaangnPreschoolSummary]] = []
    for preschool in nearby or []:
        target = coordinate_point(preschool.coordinate)
        # 웹과 같은 미터 거리를 JS `Math.round` 처럼 반올림한다. 공통 `haversine_km` 의 기본 반지름(6371.0088km)으로는 미터 경계에서
        # 어린이집 순서가 웹과 어긋날 수 있어 웹 반지름을 준다
        meters = js_round(haversine_km(*origin, *target, radius_km=WEB_EARTH_RADIUS_KM) * 1000) if origin and target else None
        rows.append((meters, DaangnPreschoolSummary(
            preschool_id=str(preschool.pre_school_no),
            name=preschool.school_nm,
            distance_m=meters,
            resident_count=preschool.complex_resident_count,
            # 당근은 설문 응답이 없는 시설의 surveyResult 를 null 로 준다 (2026-11-11 실측: 역삼래미안 20곳 중 17곳 null, 나머지
            # 3곳 reviewCount 1). 그래서 0 은 모름이 아니라 후기 없음이고, 웹도 `surveyResult?.reviewCount ?? 0` 으로 0개로
            # 보인다 (번들 ComplexSchoolSection 대조). 설문이 있는데 reviewCount 만 null 인 응답은 보지 못했다
            review_count=(preschool.survey_result.review_count if preschool.survey_result else None) or 0,
        )))
    # 웹 순서: 이 단지 주민이 많이 다니는 곳 먼저, 같으면 가까운 곳 먼저 (거리를 모르면 뒤로). 웹(ComplexSchoolSection)은 미터로
    # 반올림한 정수 거리로 견주고 같으면 서버 순서를 지킨다 (sort 는 안정 정렬이다). 예전 주석의 '반올림 전 거리' 는 틀렸다
    # (2026-11-12 번들 대조). 당근 서버도 거리 순으로 주지만 (2026-11-11 실측: 역삼래미안 20곳) 그 순서에 기대지 않는다
    rows.sort(key=lambda row: (-(row[1].resident_count or 0), row[0] is None, row[0] or 0))
    preschools = [summary for _, summary in rows]
    notes: list[str] = []
    # 서버는 빈 항목(null)도 한 자리로 세어 20곳까지 준다. 빼고 읽은 수를 받은 자리에 더한다
    dropped = danji.null_items('nearby_preschools') if danji else 0
    if nearby is None:
        notes.append(note('참고', '당근이 이 단지 근처 어린이집·유치원 정보를 주지 않았습니다. 시설이 없다는 뜻은 아닙니다'))
    elif not preschools and not dropped:
        notes.append(note('참고', f'당근에 이 단지에서 {PRESCHOOL_SERVER_RADIUS_KM:g}km 안 어린이집·유치원이 없습니다'))
    elif len(preschools) + dropped >= PRESCHOOL_SERVER_MAX:
        notes.append(note(
            '일부',
            f'당근은 단지에서 {PRESCHOOL_SERVER_RADIUS_KM:g}km 안의 어린이집·유치원을 가까운 순으로 {PRESCHOOL_SERVER_MAX}곳까지만 '
            '줍니다. 더 먼 시설은 당근에 목록이 없습니다',
        ))
    if dropped:
        notes.append(null_items_note('당근 어린이집·유치원', dropped))
    return DaangnPreschoolsResult(
        complex_id=str(complex_id),
        returned=len(preschools),
        preschools=preschools if nearby is not None else None,
        url=complex_url(complex_id),
        notes=notes,
    )


class DaangnPreschool(BaseModel):
    """어린이집·유치원 상세. 전화번호·홈페이지는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    preschool_id: Annotated[str, Field(description='시설 번호')]
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='어린이집 / 유치원')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    region: Annotated[
        str | None,
        Field(description='구·동 (예: 강남구 역삼동)')
    ] = None
    operating_hours: Annotated[
        str | None,
        Field(description='운영 시간')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 유형 (국공립·민간·직장 등)')
    ] = None
    established_date: Annotated[
        str | None,
        Field(description="설립일 (YYYY-MM-DD, 읽을 수 없는 꼴은 원래 글자 그대로, 당근이 '-' 로 비운 값은 null)")
    ] = None
    opened_date: Annotated[
        str | None,
        Field(description="개원일 (YYYY-MM-DD, 읽을 수 없는 꼴은 원래 글자 그대로, 당근이 '-' 로 비운 값은 null)")
    ] = None
    authority: Annotated[
        str | None,
        Field(description='관할 기관')
    ] = None
    capacity: Annotated[
        int | None,
        Field(description='정원 (명). 지금 다니는 원아 수가 아니다')
    ] = None
    classes: Annotated[
        int | None,
        Field(description='학급 수')
    ] = None
    teachers: Annotated[
        int | None,
        Field(description='교사 수')
    ] = None
    has_school_bus: Annotated[
        bool | None,
        Field(description='통학버스 운영')
    ] = None
    survey_responses: Annotated[
        int,
        Field(description="당근 학부모 설문 응답 수 (웹 어린이집 화면의 '후기 N'). 설문이 없으면 0")
    ] = 0


def get_preschool(client: DaangnClient, preschool_id: int) -> DaangnPreschool:
    """어린이집·유치원 하나의 운영 정보 (`preschoolByNo`, 요청 1회).

    Raises:
        JibsaError: 없는 시설 번호 (NOT_FOUND), 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    response = client.run_request_preschool_by_no(DaangnPreschoolByNoRequestPayloadModel(pre_school_no=preschool_id))
    found = response.data.preschool_by_no if response.data else None
    if found is None and not response.errors:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'당근 어린이집·유치원을 찾지 못했습니다: {preschool_id}',
            hint="시설 번호는 'jibsa daangn preschools <단지 ID>' 결과의 preschool_id 에서 얻습니다",
        )
    preschool = unwrap_graphql(response, found, '어린이집·유치원', conditions=False)
    region = preschool.region
    return DaangnPreschool(
        preschool_id=str(preschool_id),
        name=preschool.school_nm,
        type=code_label(PRESCHOOL_LABEL_BY_TYPE, preschool.type),
        # 어린이집 주소는 옛 시·도 이름으로 온다 (2026-10-11 실측: 동구푸른길어린이집 '광주광역시 동구 …')
        address=normalize_address(preschool.addr),
        region=' '.join(part for part in (region.name2, region.name3) if part) or None if region else None,
        operating_hours=preschool.open_time,
        establishment_type=preschool.estbshm_type,
        established_date=normalize_date(preschool.estbshm_date),
        opened_date=normalize_date(preschool.open_date),
        authority=preschool.jrsdt_admnstrt,
        # 당근 웹은 childCnt 를 '정원' 으로 보여 준다 (PreschoolDetailPanel). 예전 이름 children 은 다니는 원아 수로 읽혔다 (#215)
        capacity=preschool.child_cnt,
        classes=preschool.class_cnt,
        teachers=preschool.teacher_cnt,
        has_school_bus=preschool.school_bus,
        # 웹 상세(`Mu`)는 `surveyResult?.responseCount ?? 0` 이라 설문이 없어도 0 이다 (목록의 review_count 와 같다)
        survey_responses=(preschool.survey_result.response_count if preschool.survey_result else None) or 0,
    )
