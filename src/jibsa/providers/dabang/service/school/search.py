"""동 안 학교·유치원·어린이집 목록 (search schools)."""


from jibsa.core.listing import normalize_address
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.common import REGION_INFO_PAGE_LIMIT
from jibsa.providers.dabang.api.request.school.base import (
    DabangSchoolEstablishmentType,
)
from jibsa.providers.dabang.api.request.school.search import (
    DabangRegionalSchoolPath,
    DabangRegionInfoSchoolRegionalV5RequestParameterModel,
)
from jibsa.providers.dabang.api.response.school.search import DabangRegionalSchoolModel
from jibsa.providers.dabang.service.common.functions import (
    ESTABLISHMENT_BY_LABEL,
    NURSERY_ESTABLISHMENT_BY_LABEL,
    REGION_INFO_MAX_LIMIT,
    DabangPage,
    EducationLevel,
    fetch_pages,
    region_info_list_notes,
)
from jibsa.providers.dabang.service.region.functions import DabangDong
from jibsa.providers.dabang.service.school.base import LEVEL_PATH_BY_LABEL
from jibsa.providers.dabang.service.school.models import (
    DabangRegionalAdvancement,
    DabangRegionalSchool,
    DabangSchoolListResult,
)


REGIONAL_PATH_BY_LEVEL: dict[EducationLevel, DabangRegionalSchoolPath] = dict([
    *LEVEL_PATH_BY_LABEL.items(),
    ('유치원', 'kinder-school'),
    ('어린이집', 'nursery-school'),
])


def establishment_labels(level: EducationLevel) -> dict[str, DabangSchoolEstablishmentType]:
    """그 단계의 설립 구분 이름 → 다방 값 (어린이집만 공공·민간·가정·직장·협동)."""
    return NURSERY_ESTABLISHMENT_BY_LABEL if level == '어린이집' else ESTABLISHMENT_BY_LABEL


def search_schools(
    client: DabangClient,
    dong: DabangDong,
    level: EducationLevel,
    *,
    establishment: str | None,
    limit: int,
) -> DabangSchoolListResult:
    """동 안 학교·유치원·어린이집 목록 (30곳마다 요청 1회). 웹 동네정보 '학군' 상세 목록과 같은 목록·순서·전체 수다.

    Args:
        dong: 찾은 동 (`resolve_dong`).
        establishment: 설립 구분 이름 (`establishment_labels(level)` 의 키). None 이면 전체.
    """
    place, gid = dong
    establishment_type = establishment_labels(level)[establishment] if establishment else None

    def fetch(page: int) -> DabangPage[DabangRegionalSchoolModel] | None:
        result = client.run_request_region_info_school_regional_v5(DabangRegionInfoSchoolRegionalV5RequestParameterModel(
            level=REGIONAL_PATH_BY_LEVEL[level], region_gid=gid, school_establishment_type=establishment_type, page=page,
        )).result
        return DabangPage(result.list_ or [], result.total, bool(result.has_more), result.null_items('list_')) if result else None

    pages = fetch_pages(fetch, limit, page_size=REGION_INFO_PAGE_LIMIT, max_limit=REGION_INFO_MAX_LIMIT)
    # 웹 목록 칩도 같은 표로 바꾸고 모르는 값은 빈 칩이다 (school-regional 청크 `f`). labels 는 다방 값 → 설립 구분 이름
    labels: dict[str, str] = {value: label for label, value in establishment_labels(level).items()}
    schools = [
        DabangRegionalSchool(
            school_code=row.school_code,
            level=level,
            name=row.school_name,
            establishment=labels.get(row.school_establishment_type or ''),
            address=normalize_address(row.address),
            advancement=None if row.advancement_list is None else [
                DabangRegionalAdvancement(destination=item.advancement_type_name, percent=item.advancement_percentage)
                for item in row.advancement_list
            ],
        )
        for row in pages.rows
    ]
    # 좁힐 옵션을 아직 고르지 않았을 때만 좁히라고 권한다
    narrow = '설립 구분(--establishment) 조건' if establishment is None else None
    notes = region_info_list_notes(pages, limit, subject=f'{place.name} {level}', narrow=narrow)
    return DabangSchoolListResult(
        region=place,
        level=level,
        establishment=establishment or '전체',
        total=pages.total,
        returned=len(schools),
        has_more=pages.has_more,
        schools=schools,
        notes=notes,
    )
