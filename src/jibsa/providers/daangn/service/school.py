"""학교·어린이집 (school, preschools, preschool)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.listing import normalize_address
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.school import (
    DaangnEducationMapPointsInputModel,
    DaangnEducationMapPointsRequestPayloadModel,
    DaangnEducationType,
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
    region_complex_of,
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    bounds_around,
    place_in,
)

from typing import Annotated


# 학교 (당근 웹 표기)
SCHOOL_TYPE_LABELS: dict[str, str] = {'ELEMENTARY': '초등학교', 'MIDDLE': '중학교', 'HIGH': '고등학교', 'ETC': '기타'}
COEDU_LABELS: dict[str, str] = {'MALE': '남학교', 'COED': '남녀공학', 'FEMALE': '여학교'}
# 학교 이름 검색: 한 번에 받는 후보 수와, --city 로 좁힐 때 넘겨 보는 최대 페이지
# ('중앙초등학교' 는 전국에 86곳이다)
SCHOOL_CANDIDATE_LIMIT: int = 50
SCHOOL_SEARCH_MAX_PAGES: int = 3
# 학교가 여럿일 때 안내에 보여 줄 다른 후보 수
SCHOOL_OTHER_CANDIDATES: int = 3


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
        Field(description='배정 단지 (세대수 많은 순). recent_trades 는 매매다')
    ]
    url: Annotated[
        str,
        Field(description='당근 학교 페이지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='학교를 고른 방법, 배정 단지 안내. CLI 가 결과 위에 붙인다')
    ] = []


def school_url(school_code: str) -> str:
    return f'https://realty.daangn.com/schools/{school_code}'


def resolve_school(
    client: DaangnClient,
    name: str,
    *,
    city: str | None = None,
) -> tuple[DaangnSchoolSearchNodeModel, list[str]]:
    """학교 이름으로 학교 하나를 고른다 (`searchSchools`).

    `city` 를 주면 주소에 그 이름으로 시작하는 단어가 있는 학교만 보며 (`place_in`), 후보를 `SCHOOL_SEARCH_MAX_PAGES` 페이지까지 넘겨
    본다. 이름이 똑같은 학교를 먼저, 없으면 첫 후보를 고르고 다른 후보가 있으면 `notes` 로 알린다
    ('역삼초등학교' 로 '서울역삼초등학교' 가 나온다).

    Raises:
        JibsaError: 학교를 찾지 못했을 때 (NOT_FOUND).
    """
    candidates: list[DaangnSchoolSearchNodeModel] = []
    cursor = None
    # 후보가 다 오지 않았으면 True ('N곳 이상')
    truncated = False
    for _ in range(SCHOOL_SEARCH_MAX_PAGES if city else 1):
        response = client.run_request_search_schools(
            DaangnSearchSchoolsRequestPayloadModel(
                first=SCHOOL_CANDIDATE_LIMIT,
                after=cursor,
                input=DaangnSearchSchoolsInputModel(name=name),
            )
        )
        found = unwrap_graphql(response, response.data.search_schools if response.data else None, '학교 검색')
        seen = {school.sch_cd for school in candidates}
        candidates += [edge.node for edge in found.edges if edge.node and edge.node.sch_cd not in seen]
        page_info = found.page_info
        truncated = bool(page_info and page_info.has_next_page and page_info.end_cursor)
        if not truncated or page_info is None:
            break
        cursor = page_info.end_cursor
    if city:
        # 학교 주소도 지역 검색처럼 통합 이름으로 와서 normalize_address 없이 비교한다 (2026-10-11 실측: 목포·순천·영암·
        # 광주 남구 학교 모두 '전남광주통합특별시 …'. --city 전남·전라남도·광주·전남광주통합특별시 모두 찾았다)
        candidates = [school for school in candidates if place_in(city, school.sch_addr)]
    if not candidates:
        raise JibsaError(
            code='NOT_FOUND',
            message=f"당근에서 '{name}' 학교를 찾지 못했습니다" + (f" (--city '{city}')" if city else ''),
            hint="학교 이름을 줄여(예: '역삼초') 다시 찾거나 --city 를 빼 보세요",
        )
    school = next((school for school in candidates if school.sch_nm == name), candidates[0])
    notes: list[str] = []
    others = [school_ for school_ in candidates if school_ is not school]
    if others:
        listed = ', '.join(f"{other.sch_nm}({other.sch_addr or '주소 모름'})" for other in others[:SCHOOL_OTHER_CANDIDATES])
        more = f' 외 {len(others) - SCHOOL_OTHER_CANDIDATES}곳' if len(others) > SCHOOL_OTHER_CANDIDATES else ''
        notes.append(
            f"'{name}' 검색으로 찾은 학교가 {len(candidates)}곳{' 이상' if truncated else ''}이라 "
            f"{school.sch_nm}({school.sch_addr or '주소 모름'})로 조회했습니다. "
            f'다른 학교: {listed}{more}. --city 로 좁히세요'
        )
    return school, notes


def get_school(
    client: DaangnClient,
    name: str,
    *,
    city: str | None = None,
    complex_types: list[str] | None = None,
    household_min: int | None = None,
    limit: int = 120,
) -> DaangnSchoolResult:
    """학교 정보와 그 학교에 배정되는 단지를 받는다 (`searchSchools` → `schoolByCode`, 요청 2회).

    배정 단지는 초등학교에만 있다 (중·고등학교는 학교군 배정). 당근은 순서 없이 소규모 빌라형 단지까지
    주므로, `complex_types`('아파트' 는 주상복합 포함)·`household_min` 으로 거르고 세대수 많은 순으로
    `limit` 곳을 돌려준다. 단지 카드는 지역 단지 목록과 같다 (`region_complex_of`, 최근 실거래는 매매).

    Raises:
        JibsaError: 학교를 찾지 못했을 때 (NOT_FOUND), GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 웹이 학교 쿼리를 바꿨을 때.
    """
    found, notes = resolve_school(client, name, city=city)
    response = client.run_request_school_by_code(DaangnSchoolByCodeRequestPayloadModel(sch_cd=found.sch_cd))
    detail = unwrap_graphql(response, response.data.school_by_code if response.data else None, '학교 정보')

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
    complexes = sorted(
        (region_complex_of(node, '매매') for node in nodes),
        key=lambda complex_: -(complex_.households or 0),
    )

    if detail.sch_type != 'ELEMENTARY':
        notes.append('배정 단지는 초등학교에만 있습니다. 중·고등학교는 학교군으로 배정돼 단지 목록이 없습니다')
    elif not detail.assigned_complexes:
        notes.append('당근에 이 학교의 배정 단지 정보가 없습니다')
    elif len(complexes) > limit:
        notes.append(
            f'배정 단지 {len(complexes)}곳 중 세대수 많은 {limit}곳만 보여 줍니다. '
            + (f'최대 {COMPLEX_LIST_MAX_LIMIT}곳까지 표시할 수 있습니다. -t·--household-min 으로 좁히세요'
               if limit >= COMPLEX_LIST_MAX_LIMIT
               else f'--limit 을 최대 {COMPLEX_LIST_MAX_LIMIT}까지 늘리거나 -t·--household-min 으로 좁히세요')
        )
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


PRESCHOOL_TYPE_BY_LABEL: dict[str, DaangnEducationType] = {
    '어린이집': 'DAYCARE',
    '유치원': 'KINDERGARTEN',
}
PRESCHOOL_LABEL_BY_TYPE: dict[str, str] = {code: label for label, code in PRESCHOOL_TYPE_BY_LABEL.items()}
# 지도 교육 시설은 범위 안 500개에서 잘린다 (2026-10-10 실측: 강남 반경 5km 부터 500개)
EDUCATION_POINT_LIMIT: int = 500
PRESCHOOL_ID_PREFIX: str = 'pre_'
# preschools 의 --limit 최대값. CLI 옵션의 max 와 잘렸을 때의 안내가 함께 쓴다
PRESCHOOL_MAX_LIMIT: int = 200


class DaangnPreschoolSummary(BaseModel):
    """어린이집·유치원 하나 (목록)."""

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
    type: Annotated[
        str | None,
        Field(description='어린이집 / 유치원')
    ] = None
    distance_km: Annotated[
        float,
        Field(description='검색 중심에서 거리 (km)')
    ]


class DaangnPreschoolsResult(BaseModel):
    """반경 안 어린이집·유치원 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    radius_km: Annotated[
        float,
        Field(description='검색 반경 (km)')
    ]
    total: Annotated[
        int,
        Field(description='반경 안 시설 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 시설 수')
    ]
    preschools: Annotated[
        list[DaangnPreschoolSummary],
        Field(description='가까운 순 시설')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def list_preschools(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    radius_km: float = 1.0,
    types: list[str] | None = None,
    limit: int = 30,
) -> DaangnPreschoolsResult:
    """좌표 반경 안의 어린이집·유치원을 가까운 순으로 `limit` 건 준다 (`educationMapPoints`, 요청 1회).

    서버는 좌표 범위 안의 시설을 500개에서 자른다 (페이지 없음). 500개를 받으면 가까운 시설이 빠졌을 수 있어 알린다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    bounds = bounds_around(lat, lng, radius_km)
    response = client.run_request_education_map_points(
        DaangnEducationMapPointsRequestPayloadModel(
            input=DaangnEducationMapPointsInputModel(
                sw_coordinate=bounds.sw_coordinate,
                ne_coordinate=bounds.ne_coordinate,
                types=[PRESCHOOL_TYPE_BY_LABEL[label] for label in types or PRESCHOOL_TYPE_BY_LABEL],
            )
        )
    )
    points = unwrap_graphql(response, response.data.education_map_points if response.data else None, '어린이집·유치원')
    found: list[DaangnPreschoolSummary] = []
    for point in points:
        coordinate = point.coordinate
        if point.type not in PRESCHOOL_LABEL_BY_TYPE or coordinate is None or coordinate.lat is None or coordinate.lon is None:
            continue
        distance = haversine_km(lat, lng, coordinate.lat, coordinate.lon)
        if distance > radius_km:
            continue
        found.append(DaangnPreschoolSummary(
            id=point.id.removeprefix(PRESCHOOL_ID_PREFIX),
            name=point.name,
            type=PRESCHOOL_LABEL_BY_TYPE[point.type],
            distance_km=round(distance, 2),
        ))
    found.sort(key=lambda preschool: preschool.distance_km)
    notes = truncation_notes(
        len(found), limit, subject='어린이집·유치원', unit='곳', max_limit=PRESCHOOL_MAX_LIMIT, narrow='-t·--radius',
    )
    if len(points) >= EDUCATION_POINT_LIMIT:
        notes.append(
            f'당근은 넓은 범위의 시설을 {EDUCATION_POINT_LIMIT}개에서 잘라 주어 가까운 시설이 빠졌을 수 있습니다. --radius 를 줄이세요'
        )
    return DaangnPreschoolsResult(
        radius_km=radius_km,
        total=len(found),
        returned=min(len(found), limit),
        preschools=found[:limit],
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
    children: Annotated[
        int | None,
        Field(description='원아 수')
    ] = None
    classes: Annotated[
        int | None,
        Field(description='반 수')
    ] = None
    teachers: Annotated[
        int | None,
        Field(description='교사 수')
    ] = None
    school_bus: Annotated[
        bool | None,
        Field(description='통학버스 운영')
    ] = None


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
            hint="시설 번호는 'jibsa daangn preschools <지역·역>' 결과의 id 에서 얻습니다",
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
        children=preschool.child_cnt,
        classes=preschool.class_cnt,
        teachers=preschool.teacher_cnt,
        school_bus=preschool.school_bus,
    )


COMPARE_MAX_COMPLEXES: int = 5
