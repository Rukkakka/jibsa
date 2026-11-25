"""학교 상세와 배정 동·배정 단지 (school)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    AmountRange,
    more_hint,
    normalize_address,
    normalize_date,
    note,
    null_items_note,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.school import (
    NaverEducationComplexPagesV1RequestParameterModel,
    NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel,
    NaverEducationSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.school import (
    NaverRegionStudentModel,
    NaverSchoolComplexItemModel,
)
from jibsa.providers.naver.service.common import (
    ASKING_RANGES_DESCRIPTION,
    complex_row_fields,
    dong_label,
    result_or_none,
    unwrap,
    villa_by_complex_response,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


SchoolComplexSortType = Literal['DISTANCE', 'HOUSEHOLD_COUNT']
SCHOOL_COMPLEX_SORT_TYPE_BY_NAME: dict[str, SchoolComplexSortType] = {
    '거리순': 'DISTANCE',
    '세대수순': 'HOUSEHOLD_COUNT',
}
# 학교 배정 단지 목록의 쪽 크기는 웹 학교 상세 화면(DETAIL)과 같은 20 이다 (웹 기본 10, 2026-11-18 실측). 요청은 이 횟수에서
# 멈춘다. 끝 쪽을 넘긴 쪽은 totalCount 가 0 으로 와서 총수는 첫 쪽에서만 믿는다 (`list_school_complexes`)
SCHOOL_COMPLEX_PAGE_SIZE: int = 20
MAX_SCHOOL_COMPLEX_PAGE_REQUESTS: int = 5
MAX_SCHOOL_COMPLEX_LIMIT: int = SCHOOL_COMPLEX_PAGE_SIZE * MAX_SCHOOL_COMPLEX_PAGE_REQUESTS
ALL_DONGS_LABEL: str = '전체 동'


class NaverSchoolRegionAverage(BaseModel):
    """시·도 또는 시·군·구 평균 (학교와 비교용)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        str | None,
        Field(description='지역 (서울시, 강남구 ...)')
    ] = None
    students_per_class: Annotated[
        float | None,
        Field(description='학급당 학생 수')
    ] = None
    students_per_teacher: Annotated[
        float | None,
        Field(description='교원 1인당 학생 수')
    ] = None


class NaverSchoolDetail(BaseModel):
    """초등학교 상세 (학교알리미 공시 기준). 전화·홈페이지·좌표·학구도 경계는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    school_code: Annotated[
        str,
        Field(description='학교 코드')
    ]
    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소')
    ] = None
    office_of_education: Annotated[
        str | None,
        Field(description='관할 교육청')
    ] = None
    operation_type: Annotated[
        str | None,
        Field(description='운영 구분 (공립, 사립, 혁신 ...)')
    ] = None
    establishment_type: Annotated[
        str | None,
        Field(description='설립 형태 (단설, 병설 ...)')
    ] = None
    opened_date: Annotated[
        str | None,
        Field(description='개교일 (YYYY-MM-DD)')
    ] = None
    base_date: Annotated[
        str | None,
        Field(description='학생 수 공시 기준일 (YYYY-MM-DD)')
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
    sido_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·도 평균')
    ] = None
    sigungu_average: Annotated[
        NaverSchoolRegionAverage | None,
        Field(description='시·군·구 평균')
    ] = None
    complex_id: Annotated[
        int | None,
        Field(description='--complex 로 준 단지 번호. 주지 않았으면 키가 없다')
    ] = None
    all_dongs_assigned: Annotated[
        bool | None,
        Field(description='그 단지 전체 동이 이 학교에 배정되는지. --complex 를 주지 않았으면 키가 없고, 조회 실패면 null')
    ] = None
    assigned_dongs: Annotated[
        list[str] | None,
        Field(description="그 단지에서 이 학교에 배정되는 동 (예: '101동~105동'). 전체 배정이면 ['전체 동']. --complex 를 주지 않았으면 키가 없고, 조회 실패이거나 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지(동 묶음) 주지 않으면 null (일부 동만 배정된 단지와 배정되지 않은 단지가 같은 모양이다)")
    ] = None
    notes: Annotated[
        list[str],
        Field(exclude=True, description='덤 조회가 실패한 [실패] 안내 등. CLI 가 결과 위에 붙인다')
    ] = []
    url: Annotated[
        str,
        Field(description='학교 페이지 URL')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.complex_id is None:
            for field in ('complex_id', 'all_dongs_assigned', 'assigned_dongs'):
                data.pop(field, None)
        return data


def _assigned_dongs(is_all_assigned: bool | None, groups: list[list[str]] | None) -> list[str] | None:
    """사이트(`formatAssignedDong`)처럼 배정 동 글자를. 전체 배정이면 ['전체 동'], 아니면 묶음마다 첫~끝 동 ('101동~105동').

    전체 배정이 아닌데 동 묶음이 비어 오거나(`[]`) 없으면(null) 어느 동인지 모른다. 일부 동만 배정된 단지(가람아트빌 673573, 2026-10-10)와
    배정 안 된 단지(헬리오시티 111515 ↔ B100000747, 2026-10-11)가 같은 모양이다. [] 는 '배정 동 없음' 으로 읽혀 None 이다.
    전체 배정 여부(`is_all_assigned`)를 주지 않았을 때도 묶음이 비면 None 이고, 묶음이 있으면 그 묶음의 동을 낸다.
    """
    if is_all_assigned:
        return [ALL_DONGS_LABEL]

    # 건물 이름('가람아트빌라')에는 '동' 을 붙이지 않는다
    def with_dong(name: str) -> str:
        return name if name.endswith('동') else dong_label(name)

    labels = [
        with_dong(group[0]) if len(group) == 1 else f'{with_dong(group[0])}~{with_dong(group[-1])}'
        for group in groups or []
        if group
    ]
    return labels or None


def get_school(
    client: NaverClient,
    school_code: str,
    *,
    complex_number: int | None = None,
    villa: bool | None = None,
) -> NaverSchoolDetail:
    """초등학교 상세 (1회 호출). 단지를 주면 그 단지에서 이 학교에 배정되는 동을 붙인다 (1~3회 추가).

    Args:
        complex_number: 단지 번호. 주면 배정 동을 묻는다.
        villa: 단지형 빌라인지. 모르면(None) 단지 정보를 1회 더 물어 정하고, 빌라면 빌라 단지가 있는지 1회 더 묻는다
            (빌라 단지는 villa 로 물어야 한다).

    Raises:
        JibsaError: 없는 학교 코드나 없는 단지 번호면 NOT_FOUND.
    """
    school = unwrap(
        client.run_request_education_school_v1(NaverEducationSchoolV1RequestParameterModel(school_code=school_code)),
        '학교',
    )
    all_assigned: bool | None = None
    assigned: list[str] | None = None
    notes: list[str] = []
    if complex_number is not None:
        if villa is None:
            # 배정 동은 빌라 단지를 complex 로 물어도 villa 로 물어도 false·[] 라 (가람아트빌 673573 ↔ E100000875,
            # 2026-10-11) 평형 확인처럼 응답을 보고 나중에 정할 수 없어 단지 종류를 먼저 정한다
            villa = villa_by_complex_response(
                client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number))
            )
            # 없는 단지 번호도 아파트 단지 정보가 빈 결과라 빌라로 보이고, 배정 동은 배정 안 된 단지와 같은
            # false·[] 로 와서 구분되지 않는다 (99999999 ↔ 헬리오시티 111515, 2026-10-11). 빌라 단지 정보로 확인한다
            if villa:
                unwrap(
                    client.run_request_complex_villa_v1(NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)),
                    '단지',
                )
        allocation = result_or_none(lambda: client.run_request_education_complex_school_allocation_dongs_v1(
            NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel(
                complex_number=complex_number, school_code=school_code, item_type='villa' if villa else 'complex',
            )
        ), notes=notes, what='배정 동', unknown='모름(null)으로 낸 칸: all_dongs_assigned, assigned_dongs')
        if allocation is not None:
            all_assigned = allocation.is_all_building_assigned
            assigned = _assigned_dongs(all_assigned, allocation.converted_building_name_groups)
    student = school.student

    def average(region: NaverRegionStudentModel | None) -> NaverSchoolRegionAverage | None:
        if region is None:
            return None
        return NaverSchoolRegionAverage(
            region=region.region_name,
            students_per_class=region.count_per_classroom,
            students_per_teacher=region.count_per_teacher,
        )

    return NaverSchoolDetail(
        school_code=school.school_code,
        name=school.name,
        address=normalize_address(school.address) if school.address else None,
        office_of_education=school.office_of_education_in_charge,
        operation_type=school.operation_type,
        establishment_type=school.establishment_type,
        opened_date=normalize_date(school.establishment_date),
        base_date=normalize_date(student.base_date) if student else None,
        students=student.total_count if student else None,
        students_per_class=student.count_per_classroom if student else None,
        students_per_teacher=student.count_per_teacher if student else None,
        sido_average=average(school.city_student),
        sigungu_average=average(school.division_student),
        complex_id=complex_number,
        all_dongs_assigned=all_assigned,
        assigned_dongs=assigned,
        notes=notes,
        url=f'https://fin.land.naver.com/schools/elementary/{school.school_code}',
    )


class NaverSchoolComplex(BaseModel):
    """학교에 배정되는 단지 한 곳. 좌표·주소·사진은 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        int,
        Field(description='단지 번호 (naver complex / school --complex / real-price 에 넘긴다)')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    complex_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 빌라 ...). 표에 없는 유형 코드는 코드 그대로')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    listing_counts: Annotated[
        dict[str, int] | None,
        Field(description='거래 유형별 매물 수. 서버가 매물 수를 주지 않으면 null (모름)')
    ] = None
    asking_ranges: Annotated[
        dict[str, AmountRange] | None,
        Field(description=ASKING_RANGES_DESCRIPTION)
    ] = None
    assigned_dongs: Annotated[
        list[str] | None,
        Field(description="이 학교에 배정되는 동 (예: '101동~105동'). 단지 전체가 배정이면 ['전체 동']. 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지(동 묶음) 주지 않으면 null")
    ] = None


class NaverSchoolComplexesResult(BaseModel):
    """학교에 배정되는 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    total: Annotated[
        int | None,
        Field(description='학교에 배정되는 전체 단지 수 (서버 집계, limit 적용 전). 네이버가 주지 않으면 null (모름)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool | None,
        Field(description='네이버 목록에 아직 받지 않은 단지가 남았는지. 네이버가 다음 쪽이 있는지 주지 않으면 첫 쪽 총수와 받은 수로 정하고, 총수도 모르고 받은 것이 limit 안이면 null (모름)')
    ]
    complexes: Annotated[
        list[NaverSchoolComplex],
        Field(description='단지 (선택한 정렬 순서. 거리순은 학교에서 가까운 순)')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부만 보여 준다는 안내. CLI 가 notes 아래에 붙인다')
    ] = []


def _school_complex(item: NaverSchoolComplexItemModel) -> NaverSchoolComplex | None:
    """단지 정보(`complexInfo`, 빌라는 `villaInfo`)가 둘 다 없는 항목은 단지 번호·이름을 알 수 없어 None 이다 (건너뛴다)."""
    # 지역 단지 목록(`search.py` 의 `_area_complex`)과 같게 아파트·오피스텔 칸이 없으면 빌라 칸을 본다
    info = item.complex_info or item.villa_info
    if info is None:
        return None
    return NaverSchoolComplex(
        complex_id=info.complex_number,
        name=info.name,
        assigned_dongs=_assigned_dongs(item.is_all_building_assigned, item.converted_building_name_groups),
        **complex_row_fields(
            type_code=info.type,
            households=info.total_household_number,
            dong_count=info.building_count,
            use_approval_date=info.use_approval_date,
            counts=item.article_count_info,
            prices=item.article_price_info,
        ),
    )


def list_school_complexes(
    client: NaverClient,
    school_code: str,
    *,
    sort: str,
    limit: int,
) -> NaverSchoolComplexesResult:
    """학교에 배정되는 단지를 네이버 정렬 순서대로 `limit` 곳까지 모은다 (20곳에 1회, 최대 `MAX_SCHOOL_COMPLEX_PAGE_REQUESTS` 회).

    웹 학교 상세의 '배정 단지' 칸과 같은 요청이다. 총수는 첫 쪽(page=0)의 `totalCount` 만 쓴다 (끝 쪽 이후는 0 으로 온다).
    `hasNextPage` 가 거짓이거나 `limit` 곳을 모았거나 쪽이 비면 더 받지 않는다. 쪽 사이 겹침·빠짐은 서버가 정한 순서를 따른다.
    서버가 null 로 준 칸은 모름이다: `totalCount` 가 null 이면 `total` 이 null 이고, `list` 가 null 이면 그 쪽은 0곳이다.
    `hasNextPage` 가 null 이면 첫 쪽 총수가 받은 수보다 클 때 더 있는 것으로 보고 이어 받으며 (그래야 `--limit` 을 늘리라는 안내가 맞다),
    총수도 모르면 더 받지 않고 받은 것이 `limit` 안일 때 `has_more` 가 null 이다.
    쪽 요청 상한(`MAX_SCHOOL_COMPLEX_PAGE_REQUESTS`)에 닿아 멈췄는데 받은 수가 `limit` 에 못 미치면 (네이버가 쪽을 20곳보다 짧게 줄 때)
    `--limit` 을 늘려도 같은 쪽 수에서 멈추니 늘리라고 하지 않고 받은 수와 상한을 알린다. 단지 정보가 없는 항목은 건너뛰고 `[제외]` 로 알린다.
    목록 안의 빈 항목(null)은 빼고 읽되 서버가 센 자리라 받은 수·쪽이 비었는지 셀 때 더하고, `[제외]` 로 알린다.

    Args:
        sort: 정렬 (`SCHOOL_COMPLEX_SORT_TYPE_BY_NAME` 의 이름).
        limit: 최대 단지 수 (`MAX_SCHOOL_COMPLEX_LIMIT` 이하).

    Raises:
        JibsaError: 응답이 비었거나 실패하면 NOT_FOUND·UPSTREAM_ERROR.
    """
    sort_type = SCHOOL_COMPLEX_SORT_TYPE_BY_NAME[sort]
    items: list[NaverSchoolComplexItemModel] = []
    # 빈 항목(null)이라 빼고 읽은 수. 서버는 그 자리도 단지로 센 쪽이라 받은 수·쪽이 비었는지 셀 때 더한다
    dropped = 0
    received = 0
    total: int | None = None
    more: bool | None = False
    for page_number in range(MAX_SCHOOL_COMPLEX_PAGE_REQUESTS):
        page = unwrap(
            client.run_request_education_complex_pages_v1(
                NaverEducationComplexPagesV1RequestParameterModel(
                    school_code=school_code, size=SCHOOL_COMPLEX_PAGE_SIZE, page=page_number, sort_type=sort_type,
                )
            ),
            '학교 배정 단지',
        )
        page_items = page.items or []
        page_dropped = page.null_items('items')
        dropped += page_dropped
        # 빈 항목(null)만 온 쪽은 서버가 단지가 든 쪽으로 센다 (빈 쪽이 아니다)
        page_slots = len(page_items) + page_dropped
        if page_number == 0:
            total = page.total_count
        items += page_items
        received = len(items) + dropped
        more = page.has_next_page
        if more is None and total is not None:
            # hasNextPage 를 주지 않아도 첫 쪽 총수가 받은 수보다 크면 더 있는 것이다. 총수도 모르면 이어 받을 근거가 없어 모름(None)으로 멈춘다
            more = total > received
        # 빈 쪽은 더 있다는 말을 믿지 않고 멈춘다 (빈 쪽을 요청 상한까지 되풀이해 받지 않는다)
        if not more or not page_slots or received >= limit:
            break
    complexes = [row for row in (_school_complex(item) for item in items[:limit]) if row is not None]
    skipped = min(len(items), limit) - len(complexes)
    # 마지막으로 받은 쪽에 limit 을 넘겨 받은 단지가 있어도 남은 것이다. 남은 근거가 없으면 hasNextPage·총수 그대로 (null 은 모름)
    has_more = True if more or received > limit else more
    # 위 break 조건에 하나도 걸리지 않고 쪽 요청 상한에서 끝났다 (받은 수가 limit 에 못 미치게 쪽이 짧았다)
    request_capped = bool(more) and bool(page_slots) and received < limit
    notes: list[str] = []
    if skipped:
        notes.append(note('제외', f'네이버가 단지 정보를 주지 않은 {skipped}곳은 뺐습니다'))
    if more and not page_slots:
        # 더 있다면서 빈 쪽을 줘 멈췄다. --limit 을 늘려도 같은 빈 쪽에서 멈추니 늘리라고 하지 않는다
        notes.append(note('일부', f'네이버가 더 있다면서 빈 쪽을 줘 {received}곳까지만 받았습니다'))
    elif request_capped:
        # --limit 을 늘려도 같은 쪽 수에서 멈추니 늘리라고 하지 않는다 (`limit` 이 최대값이어도 '최대값은 100' 이 맞지 않다)
        total_text = f' (학교에 배정되는 단지는 {total}곳)' if total is not None else ''
        notes.append(note(
            '일부',
            f'네이버가 쪽을 짧게 줘 요청 상한({MAX_SCHOOL_COMPLEX_PAGE_REQUESTS}쪽)까지 {received}곳만 받았습니다{total_text}',
        ))
    elif has_more:
        shown = f'학교에 배정되는 단지가 {total}곳 있고, 그중' if total is not None else '학교에 배정되는 단지 중'
        notes.append(note(
            '일부',
            f'{shown} {len(complexes)}곳만 보여 줍니다. {more_hint(limit, MAX_SCHOOL_COMPLEX_LIMIT, None)}',
        ))
    if dropped:
        notes.append(null_items_note('네이버 학교 배정 단지', dropped))
    return NaverSchoolComplexesResult(
        total=total, returned=len(complexes), has_more=has_more, complexes=complexes, notes=notes,
    )
