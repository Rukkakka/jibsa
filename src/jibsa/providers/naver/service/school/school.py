"""학교 상세와 배정 동·배정 단지의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""

from jibsa.core.listing import (
    more_hint,
    normalize_address,
    note,
    null_items_note,
    read_date,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.request.school import (
    NaverEducationComplexPagesV1RequestParameterModel,
    NaverEducationComplexSchoolAllocationDongsV1RequestParameterModel,
    NaverEducationSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.school import (
    NaverRegionStudentModel,
    NaverSchoolComplexItemModel,
)
from jibsa.providers.naver.service.common.labels import (
    dong_label,
)
from jibsa.providers.naver.service.common.price import (
    complex_row_fields,
)
from jibsa.providers.naver.service.common.response import (
    result_or_none,
    unwrap,
    villa_by_complex_response,
)
from jibsa.providers.naver.service.school.constants import (
    ALL_DONGS_LABEL,
    MAX_SCHOOL_COMPLEX_LIMIT,
    MAX_SCHOOL_COMPLEX_PAGE_REQUESTS,
    SCHOOL_COMPLEX_PAGE_SIZE,
    SCHOOL_COMPLEX_SORT_TYPE_BY_NAME,
    SCHOOL_URL,
)
from jibsa.providers.naver.service.school.models import (
    NaverSchoolComplex,
    NaverSchoolComplexesResult,
    NaverSchoolDetail,
    NaverSchoolRegionAverage,
)


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
        opened_date=read_date(school.establishment_date, '개교일'),
        base_date=read_date(student.base_date, '학생 수 기준일') if student else None,
        students=student.total_count if student else None,
        students_per_class=student.count_per_classroom if student else None,
        students_per_teacher=student.count_per_teacher if student else None,
        sido_average=average(school.city_student),
        sigungu_average=average(school.division_student),
        complex_id=complex_number,
        all_dongs_assigned=all_assigned,
        assigned_dongs=assigned,
        notes=notes,
        url=SCHOOL_URL.format(school.school_code),
    )


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
