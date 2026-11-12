"""학교·어린이집 (school, preschools, preschool)."""

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.korean import quoted
from jibsa.core.listing import (
    more_hint,
    normalize_address,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.school import (
    DaangnComplexSchoolsRequestPayloadModel,
    DaangnPreschoolByNoRequestPayloadModel,
    DaangnSchoolByCodeRequestPayloadModel,
    DaangnSearchSchoolsInputModel,
    DaangnSearchSchoolsRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.school import DaangnSchoolSearchNodeModel
from jibsa.providers.daangn.service.common import (
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    DaangnRegionComplex,
    complex_list_notes,
    complex_not_found,
    complex_url,
    coordinate_point,
    js_round,
    region_complex_of,
    unwrap_graphql,
)

from typing import Annotated


# 학교 (당근 웹 표기)
SCHOOL_TYPE_LABELS: dict[str, str] = {'ELEMENTARY': '초등학교', 'MIDDLE': '중학교', 'HIGH': '고등학교', 'ETC': '기타'}
COEDU_LABELS: dict[str, str] = {'MALE': '남학교', 'COED': '남녀공학', 'FEMALE': '여학교'}
# 학교 이름 검색이 한 번에 받는 후보 수. 웹 검색창은 4곳씩 넘기지만 한 번에 더 받는다 ('중앙초등학교' 는 전국에 86곳이다)
SCHOOL_CANDIDATE_LIMIT: int = 50
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
    stats_year: Annotated[
        str | None,
        Field(description='학생 수 기준 연도')
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
    total_complexes: Annotated[
        int,
        Field(description='조건에 맞는 배정 단지 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='배정 단지 (당근 웹 학교 화면과 같은 순서). recent_trades 는 최근 매매 1건이다')
    ]
    url: Annotated[
        str,
        Field(description='당근 학교 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='배정 단지 안내 (중·고등학교, 정보 없음, 조건·limit 으로 줄임). CLI 가 결과 위에 붙인다')
    ] = []


def school_url(school_code: str) -> str:
    return f'https://realty.daangn.com/schools/{school_code}'


def _searchable(nodes: list[DaangnSchoolSearchNodeModel]) -> list[DaangnSchoolSearchNodeModel]:
    """좌표가 있는 학교만. 당근 웹 검색창도 좌표 없는 학교를 뺀다 (2026-11-12 실측: '중앙초등학교' 50곳 중 1곳)."""
    return [node for node in nodes if coordinate_point(node.coordinate) is not None]


def search_school_candidates(client: DaangnClient, name: str) -> tuple[list[DaangnSchoolSearchNodeModel], bool]:
    """이름이 들어간 초·중·고 후보 (`searchSchools`, 요청 1회). 웹 지도 검색창의 학교 칸이다.

    다음 쪽은 받지 않는다. 당근은 이름이 그대로 같은 학교를 맨 앞에 주어, 이름으로 학교를 고르는 `resolve_school` 에는 첫 쪽으로
    충분하다 (2026-11-12 실측: '중앙초등학교' 86곳 중 같은 이름 6곳이 1~6번째, '동산초등학교' 7곳·'신흥초등학교' 3곳·
    '중앙중학교' 2곳도 맨 앞. 다음 쪽을 받아야 한다는 2026-11-12 리뷰 지적은 오탐). 잘렸는지는 두 번째 값으로 알린다.

    Returns:
        (좌표가 있는 후보, 서버에 후보가 더 있는지). 후보는 첫 `SCHOOL_CANDIDATE_LIMIT` 곳까지다.
    """
    response = client.run_request_search_schools(
        DaangnSearchSchoolsRequestPayloadModel(first=SCHOOL_CANDIDATE_LIMIT, input=DaangnSearchSchoolsInputModel(name=name))
    )
    found = unwrap_graphql(response, response.data.search_schools if response.data else None, '학교 검색')
    has_more = bool(found.page_info and found.page_info.has_next_page)
    return _searchable([edge.node for edge in found.edges if edge.node]), has_more


def resolve_school(client: DaangnClient, name: str) -> str:
    """학교 이름이나 학교 코드로 학교 코드 하나를 고른다 (`searchSchools`, 요청 1~2회. 코드면 요청 없음).

    당근 웹 검색창처럼 이름이 들어간 학교를 한 번 찾고, 좌표 없는 학교는 뺀다. 웹은 후보를 보여 주고 사람이 고르므로 jibsa 도
    여럿이면 고르지 않고 후보(이름·주소·학교 코드)를 알린다. 예전에는 첫 후보를 저절로 골라 엉뚱한 지역 학교로 답할 수 있었고
    `--city` 로 주소를 걸렀다 (#215). 이름이 그대로 같은 학교가 하나뿐이면 그 학교다.

    '○○초등학교' 처럼 종류 이름까지 주면 줄임('○○초')으로도 한 번 더 찾아 합친다 (`SCHOOL_KIND_SHORT_NAMES`). 당근 웹에는 없는
    jibsa 개선이다. 당근 검색은 '대치초등학교' 로 서울대치초등학교를 못 찾고(웹도 0건) '대치초' 로는 찾는다 (2026-11-12 실측,
    #133. 2026-11-12 사용자 결정으로 남김). 첫 검색에 이름이 그대로 같은 학교가 하나면 더 찾지 않는다. 줄임 검색이 더 찾는 학교
    중 이름이 그대로 같은 학교는 첫 검색에도 나와 답이 같고, 요청만 하나 더 쓴다 (2026-11-12 리뷰). 같은 이름 학교가 여럿이면
    후보를 알리므로 줄임 검색까지 해 후보에 넣는다. 첫 검색만 보면 '도곡초등학교' 의 후보가 경기 광주·화순 두 곳뿐이고
    서울도곡초등학교가 빠졌다 (2026-11-13 리뷰·실측).

    Raises:
        JibsaError: 학교를 찾지 못했을 때 (NOT_FOUND), 여럿일 때 (REGION_AMBIGUOUS. 지역 후보와 같은 코드라 에이전트가 같은 방법으로
            고르고, `candidates` 에는 학교마다 이름·주소·학교 코드가 있다).
    """
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
    for query in queries:
        found, has_more = search_school_candidates(client, query)
        seen = {school.sch_cd for school in candidates}
        candidates += [school for school in found if school.sch_cd not in seen]
        truncated = truncated or has_more
        # 이름이 같은 학교가 하나면 그 학교라 줄인 이름으로 더 찾지 않는다. 여럿이면 후보 목록이 되므로 줄인 이름으로만 나오는
        # 학교('서울도곡초등학교')까지 넣는다 (2026-11-13 리뷰: 여럿일 때도 멈춰 후보에서 빠졌다)
        if sum(school.sch_nm == name for school in candidates) == 1:
            break
    if not candidates:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"당근에서 '{name}' 학교를 찾지 못했습니다",
            hint="당근 학교 이름은 '서울대치초등학교' 처럼 시·도가 붙기도 합니다. '대치초' 처럼 줄이거나 시·도를 붙여 다시 찾으세요",
        )
    exact = [school for school in candidates if school.sch_nm == name]
    if len(candidates) == 1 or len(exact) == 1:
        return (exact or candidates)[0].sch_cd
    shown = [
        {'name': school.sch_nm, 'address': school.sch_addr, 'school_code': school.sch_cd}
        for school in candidates[:SCHOOL_AMBIGUOUS_SHOWN]
    ]
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
    ('아파트' 는 주상복합 포함)·`household_min`·`limit` 은 서버가 받지 않는 조건이라 그 순서에서 거르고 자른다.

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
    detail = unwrap_graphql(response, response.data.school_by_code if response.data else None, '학교 정보')
    notes: list[str] = []

    types: set[str] = set()
    for label in complex_types or []:
        code = COMPLEX_TYPE_FILTER_BY_LABEL[label]
        # 단지 목록의 '아파트' 처럼 주상복합도 함께 본다
        types |= {code, 'MIXED_USE'} if code == 'APARTMENT' else {code}
    nodes = [
        node for node in detail.assigned_complexes or []
        if (not types or node.type in types)
        and (household_min is None or (node.danji is not None and (node.danji.households or 0) >= household_min))
    ]
    complexes = [region_complex_of(node, '매매', max_trades=1) for node in nodes]

    if detail.sch_type != 'ELEMENTARY':
        notes.append('배정 단지는 초등학교에만 있습니다. 중·고등학교는 학교군으로 배정돼 단지 목록이 없습니다')
    elif not detail.assigned_complexes:
        notes.append('당근에 이 학교의 배정 단지 정보가 없습니다')
    elif not complexes:
        # 안내가 없으면 배정 단지가 없는 학교와 구별되지 않았다 (2026-11-12 리뷰)
        notes.append(note(
            '참고',
            f'배정 단지 {len(detail.assigned_complexes)}곳 중 단지 유형(-t)·세대수(--household-min) 조건에 맞는 곳이 없습니다',
        ))
    elif len(complexes) > limit:
        notes.append(note(
            '일부',
            f'배정 단지 {len(complexes)}곳 중 당근 순서로 앞 {limit}곳만 보여 줍니다. '
            + more_hint(limit, COMPLEX_LIST_MAX_LIMIT, '단지 유형(-t)·세대수(--household-min) 조건'),
        ))
    shown = complexes[:limit]
    return DaangnSchoolResult(
        school=DaangnSchool(
            school_code=detail.sch_cd,
            name=detail.sch_nm,
            school_type=SCHOOL_TYPE_LABELS.get(detail.sch_type or '', detail.sch_type),
            address=normalize_address(detail.sch_addr),
            foundation=detail.fond_sch_cd,
            coed=COEDU_LABELS.get(detail.coedu or '', detail.coedu),
            students=detail.tot_std_cnt,
            students_per_class=detail.cls_std_cnt,
            students_per_teacher=detail.tch_std_cnt,
            stats_year=detail.student_std_date,
        ),
        total_complexes=len(complexes),
        returned=len(shown),
        complexes=shown,
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

    id: Annotated[
        str,
        Field(description='시설 번호 (preschool 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='시설 이름')
    ] = None
    distance_km: Annotated[
        float | None,
        Field(description='단지에서 직선거리 (km). 단지나 시설 좌표가 없으면 null')
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


def _web_distance_m(origin: tuple[float, float], target: tuple[float, float]) -> int:
    """당근 웹(services2 의 하버사인, 반지름 6371km)과 같은 미터 거리를 JS `Math.round` 처럼 반올림한 정수.

    공통 `haversine_km` 의 기본 반지름(6371.0088km)으로는 미터 경계에서 어린이집 순서가 웹과 어긋날 수 있어 웹 반지름을 준다.
    """
    return js_round(haversine_km(*origin, *target, radius_km=WEB_EARTH_RADIUS_KM) * 1000)


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
        response, response.data.complex_by_original_id if response.data else None, '단지 근처 어린이집·유치원'
    )
    if result.complex is None:
        raise complex_not_found(complex_id)
    danji = result.complex.proptier_danji
    origin = (coordinate_point(danji.coordinate) if danji else None) or coordinate_point(result.complex.coordinate)
    # 학군 정보(proptierDanji)나 근처 시설 목록이 null 이면 모름이다. 웹(ComplexSchoolSection `nearbyPreschools??[]`)은 빈 목록과
    # 똑같이 유치원 탭을 비우지만, 출력은 complex·compare 의 학교처럼 모름(null)과 빈 목록([])을 나눈다
    nearby = danji.nearby_preschools if danji else None
    # (웹이 견주는 미터 정수 거리, 시설). 출력의 distance_km 는 그 거리를 km 소수 둘째 자리로 반올림해 순서와 어긋나지 않는다
    rows: list[tuple[int | None, DaangnPreschoolSummary]] = []
    for preschool in nearby or []:
        target = coordinate_point(preschool.coordinate)
        meters = _web_distance_m(origin, target) if origin and target else None
        rows.append((meters, DaangnPreschoolSummary(
            id=str(preschool.pre_school_no),
            name=preschool.school_nm,
            distance_km=None if meters is None else round(meters / 1000, 2),
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
    if nearby is None:
        notes.append(note('참고', '당근이 이 단지 근처 어린이집·유치원 정보를 주지 않았습니다. 시설이 없다는 뜻은 아닙니다'))
    elif not preschools:
        notes.append(note('참고', f'당근에 이 단지에서 {PRESCHOOL_SERVER_RADIUS_KM:g}km 안 어린이집·유치원이 없습니다'))
    elif len(preschools) >= PRESCHOOL_SERVER_MAX:
        notes.append(note(
            '일부',
            f'당근은 단지에서 {PRESCHOOL_SERVER_RADIUS_KM:g}km 안의 어린이집·유치원을 가까운 순으로 {PRESCHOOL_SERVER_MAX}곳까지만 '
            '줍니다. 더 먼 시설은 당근에 목록이 없습니다',
        ))
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

    id: Annotated[str, Field(description='시설 번호')]
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
    open_time: Annotated[
        str | None,
        Field(description='운영 시간')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 유형 (국공립·민간·직장 등)')
    ] = None
    established_at: Annotated[
        str | None,
        Field(description='설립일')
    ] = None
    opened_at: Annotated[
        str | None,
        Field(description='개원일')
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
    school_bus: Annotated[
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
            hint="시설 번호는 'jibsa daangn preschools <단지 ID>' 결과의 id 에서 얻습니다",
        )
    preschool = unwrap_graphql(response, found, '어린이집·유치원')
    region = preschool.region
    return DaangnPreschool(
        id=str(preschool_id),
        name=preschool.school_nm,
        type=PRESCHOOL_LABEL_BY_TYPE.get(preschool.type or ''),
        # 어린이집 주소는 옛 시·도 이름으로 온다 (2026-10-11 실측: 동구푸른길어린이집 '광주광역시 동구 …')
        address=normalize_address(preschool.addr),
        region=' '.join(part for part in (region.name2, region.name3) if part) or None if region else None,
        open_time=preschool.open_time,
        establishment_type=preschool.estbshm_type,
        established_at=preschool.estbshm_date,
        opened_at=preschool.open_date,
        authority=preschool.jrsdt_admnstrt,
        # 당근 웹은 childCnt 를 '정원' 으로 보여 준다 (PreschoolDetailPanel). 예전 이름 children 은 다니는 원아 수로 읽혔다 (#215)
        capacity=preschool.child_cnt,
        classes=preschool.class_cnt,
        teachers=preschool.teacher_cnt,
        school_bus=preschool.school_bus,
        # 웹 상세(`Mu`)는 `surveyResult?.responseCount ?? 0` 이라 설문이 없어도 0 이다 (목록의 review_count 와 같다)
        survey_responses=(preschool.survey_result.response_count if preschool.survey_result else None) or 0,
    )


# 단지 비교에 넣는 단지 수 상한. 당근 웹 비교 화면이 10곳까지다 ('최대 10개까지 비교할 수 있어요', 예전에는 5)
COMPARE_MAX_COMPLEXES: int = 10
