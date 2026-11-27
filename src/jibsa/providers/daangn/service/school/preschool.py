"""어린이집 (preschools, preschool)."""

from jibsa.core.errors import JibsaError
from jibsa.core.geo import haversine_km
from jibsa.core.listing import (
    js_round,
    normalize_address,
    note,
    null_items_note,
    read_date,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.request.school.preschool import (
    DaangnComplexSchoolsRequestPayloadModel,
    DaangnPreschoolByNoRequestPayloadModel,
)
from jibsa.providers.daangn.service.common.complex import (
    complex_not_found,
)
from jibsa.providers.daangn.service.common.constants import COMPLEX_URL
from jibsa.providers.daangn.service.common.location import coordinate_point
from jibsa.providers.daangn.service.common.response import (
    code_label,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.school.constants import (
    PRESCHOOL_LABEL_BY_TYPE,
    PRESCHOOL_SERVER_MAX,
    PRESCHOOL_SERVER_RADIUS_KM,
    WEB_EARTH_RADIUS_KM,
)
from jibsa.providers.daangn.service.school.models import (
    DaangnPreschool,
    DaangnPreschoolsResult,
    DaangnPreschoolSummary,
)


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
        url=COMPLEX_URL.format(complex_id),
        notes=notes,
    )


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
        established_date=read_date(preschool.estbshm_date, '설립일'),
        opened_date=read_date(preschool.open_date, '개원일'),
        authority=preschool.jrsdt_admnstrt,
        # 당근 웹은 childCnt 를 '정원' 으로 보여 준다 (PreschoolDetailPanel). 예전 이름 children 은 다니는 원아 수로 읽혔다 (#215)
        capacity=preschool.child_cnt,
        classes=preschool.class_cnt,
        teachers=preschool.teacher_cnt,
        has_school_bus=preschool.school_bus,
        # 웹 상세(`Mu`)는 `surveyResult?.responseCount ?? 0` 이라 설문이 없어도 0 이다 (목록의 review_count 와 같다)
        survey_responses=(preschool.survey_result.response_count if preschool.survey_result else None) or 0,
    )
