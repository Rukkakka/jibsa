"""개발 호재 목록·상세 (developments, development)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    haversine_km,
    within_radius,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.development import (
    DaangnDevelopmentByBusiNoRequestPayloadModel,
    DaangnDevelopmentCategory,
    DaangnDevelopmentDistrictsInputModel,
    DaangnDevelopmentDistrictsRequestPayloadModel,
)
from jibsa.providers.daangn.service.common import (
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import bounds_around

from typing import Annotated


DEVELOPMENT_CATEGORY_BY_LABEL: dict[str, DaangnDevelopmentCategory] = {
    '도로': 'ROAD',
    '철도': 'RAIL',
    '정비사업': 'HOUSING',
}
DEVELOPMENT_LABEL_BY_CATEGORY: dict[str, str] = {code: label for label, code in DEVELOPMENT_CATEGORY_BY_LABEL.items()}
# 웹 지도의 진행 표시. E01 은 웹이 지도에서 숨기는 사업이라 jibsa 도 뺀다
DEVELOPMENT_STATUS_BY_CODE: dict[str, str] = {'S11': '예정', 'S12': '진행'}
HIDDEN_DEVELOPMENT_STATUS: str = 'E01'
# developments 의 --limit 최대값. CLI 옵션의 max 와 잘렸을 때의 안내가 함께 쓴다
DEVELOPMENT_MAX_LIMIT: int = 300


class DaangnDevelopment(BaseModel):
    """개발 사업 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    id: Annotated[
        int,
        Field(description='사업 번호 (development 에 넘긴다)')
    ]
    name: Annotated[
        str | None,
        Field(description='사업 이름')
    ] = None
    category: Annotated[
        str | None,
        Field(description='도로 / 철도 / 정비사업')
    ] = None
    status: Annotated[
        str | None,
        Field(description='예정 / 진행. 모르면 null')
    ] = None
    distance_km: Annotated[
        float,
        Field(description='검색 중심에서 사업 구역 중심까지 거리 (km)')
    ]


class DaangnDevelopmentsResult(BaseModel):
    """반경 안 개발 사업 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    radius_km: Annotated[
        float,
        Field(description='검색 반경 (km)')
    ]
    total: Annotated[
        int,
        Field(description='반경 안 사업 수 (limit 적용 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 사업 수')
    ]
    developments: Annotated[
        list[DaangnDevelopment],
        Field(description='가까운 순 사업')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def list_developments(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    radius_km: float = 1.0,
    categories: list[str] | None = None,
    limit: int = 50,
) -> DaangnDevelopmentsResult:
    """좌표 반경 안의 개발 사업(도로·철도·정비사업)을 가까운 순으로 `limit` 건 준다 (`developmentDistricts`, 요청 1회).

    서버는 좌표 범위 안의 사업을 모두 준다 (페이지 없음, 2026-10-10 실측: 강남 반경 5km 102건). 범위를 감싸는
    사각형으로 받아 반경 밖은 빼고, 웹 지도가 숨기는 사업(진행 코드 E01)도 뺀다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때 (웹이 쿼리를 바꿈).
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    bounds = bounds_around(lat, lng, radius_km)
    response = client.run_request_development_districts(
        DaangnDevelopmentDistrictsRequestPayloadModel(
            input=DaangnDevelopmentDistrictsInputModel(
                sw_coordinate=bounds.sw_coordinate,
                ne_coordinate=bounds.ne_coordinate,
                categories=[DEVELOPMENT_CATEGORY_BY_LABEL[label] for label in categories or DEVELOPMENT_CATEGORY_BY_LABEL],
            )
        )
    )
    districts = unwrap_graphql(response, response.data.development_districts if response.data else None, '개발 호재')
    found: list[DaangnDevelopment] = []
    hidden = 0
    for district in districts:
        coordinate = district.center_coordinate
        if coordinate is None or coordinate.lat is None or coordinate.lon is None:
            continue
        distance = haversine_km(lat, lng, coordinate.lat, coordinate.lon)
        # 출력의 distance_km 처럼 반올림한 거리로 본다 (매물 반경 검색과 같다). 1.004km 를 '1.0km' 로 보이면서 1km 반경에서 빼지 않게
        if not within_radius(distance, radius_km):
            continue
        if district.busi_prgrs_cd == HIDDEN_DEVELOPMENT_STATUS:
            hidden += 1
            continue
        found.append(DaangnDevelopment(
            id=district.dev_busi_no,
            name=district.dev_busi_nm,
            category=DEVELOPMENT_LABEL_BY_CATEGORY.get(district.category or ''),
            status=DEVELOPMENT_STATUS_BY_CODE.get(district.busi_prgrs_cd or ''),
            distance_km=round(distance, 2),
        ))
    found.sort(key=lambda development: development.distance_km)
    notes = truncation_notes(
        len(found), limit, subject='개발 사업', max_limit=DEVELOPMENT_MAX_LIMIT, narrow='--category·--radius',
    )
    if hidden:
        notes.append(f'당근 웹 지도가 숨기는 사업(진행 코드 E01) {hidden}건은 뺐습니다')
    return DaangnDevelopmentsResult(
        radius_km=radius_km,
        total=len(found),
        returned=min(len(found), limit),
        developments=found[:limit],
        notes=notes,
    )


class DaangnDevelopmentDates(BaseModel):
    """개발 사업의 단계별 날짜. 당근이 주는 문자열 그대로 둔다 (모르면 null)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    area_designation: Annotated[
        str | None,
        Field(description='구역 지정')
    ] = None
    committee_approval: Annotated[
        str | None,
        Field(description='추진위원회 승인')
    ] = None
    union_establishment: Annotated[
        str | None,
        Field(description='조합 설립 인가')
    ] = None
    development_plan_approval: Annotated[
        str | None,
        Field(description='개발 계획 승인')
    ] = None
    implementation_plan_approval: Annotated[
        str | None,
        Field(description='실시 계획 승인')
    ] = None
    project_implementation: Annotated[
        str | None,
        Field(description='사업 시행 인가')
    ] = None
    management_disposal: Annotated[
        str | None,
        Field(description='관리 처분 인가')
    ] = None


class DaangnDevelopmentDetail(BaseModel):
    """개발 사업 상세. 사진은 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    id: Annotated[int, Field(description='사업 번호')]
    name: Annotated[
        str | None,
        Field(description='사업 이름')
    ] = None
    business_sort: Annotated[
        str | None,
        Field(description='사업 분류 (예: 정비사업)')
    ] = None
    business_type: Annotated[
        str | None,
        Field(description='사업 종류 (예: 재건축)')
    ] = None
    progress: Annotated[
        str | None,
        Field(description='진행 상태 (예: 사업진행)')
    ] = None
    step: Annotated[
        str | None,
        Field(description='사업 단계 (예: 착공및분양)')
    ] = None
    period: Annotated[
        str | None,
        Field(description='사업 기간')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='사업 면적 (㎡)')
    ] = None
    size: Annotated[
        str | None,
        Field(description='사업 규모 (예: 1,802명/721세대)')
    ] = None
    location: Annotated[
        str | None,
        Field(description='위치 (지번 일부)')
    ] = None
    developer: Annotated[
        str | None,
        Field(description='사업 시행자')
    ] = None
    developer_type: Annotated[
        str | None,
        Field(description='시행 방식 (예: 조합방식)')
    ] = None
    constructor: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    planned_households: Annotated[
        int | None,
        Field(description='계획 세대수')
    ] = None
    building_coverage_pct: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    floor_area_ratio_pct: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    max_floors: Annotated[
        str | None,
        Field(description='계획 최고 층수')
    ] = None
    target_year: Annotated[
        str | None,
        Field(description='목표 연도')
    ] = None
    dates: Annotated[DaangnDevelopmentDates, Field(description='단계별 날짜')]


def get_development(client: DaangnClient, development_id: int) -> DaangnDevelopmentDetail:
    """개발 사업 하나의 단계·규모·인가 날짜 (`developmentByBusiNo`, 요청 1회).

    Raises:
        JibsaError: 없는 사업 번호 (NOT_FOUND), 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    response = client.run_request_development_by_busi_no(
        DaangnDevelopmentByBusiNoRequestPayloadModel(dev_busi_no=development_id)
    )
    found = response.data.development_by_busi_no if response.data else None
    if found is None and not response.errors:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'당근 개발 사업을 찾지 못했습니다: {development_id}',
            hint="사업 번호는 'jibsa daangn developments <지역·역>' 결과의 id 에서 얻습니다",
        )
    detail = unwrap_graphql(response, found, '개발 사업')
    return DaangnDevelopmentDetail(
        id=development_id,
        name=detail.dev_busi_nm,
        business_sort=detail.dev_busi_sort,
        business_type=detail.dev_busi_type,
        progress=detail.busi_prgrs,
        step=detail.busi_step,
        period=detail.busi_term,
        area_m2=detail.busi_area,
        size=detail.busi_size,
        location=detail.location,
        developer=detail.developer_nm,
        developer_type=detail.developer_type,
        constructor=detail.cstr_cp_nm,
        planned_households=detail.plan_hseh_cnt,
        # 계획 수치를 모르면 0 으로 온다 (2026-10-10 실측: 역삼동 은하수 재건축 건폐율·용적률·층수 0)
        building_coverage_pct=detail.building_coverage or None,
        floor_area_ratio_pct=detail.floor_space_idx or None,
        max_floors=None if detail.basic_plan_floor_cnt in (None, '', '0') else detail.basic_plan_floor_cnt,
        target_year=detail.target_y,
        dates=DaangnDevelopmentDates(
            area_designation=detail.area_designation_date,
            committee_approval=detail.committee_apprv_date,
            union_establishment=detail.estbm_union_date,
            development_plan_approval=detail.dev_plan_aprv_date,
            implementation_plan_approval=detail.impl_plan_aprv_date,
            project_implementation=detail.proj_implmtt_date,
            management_disposal=detail.mngm_disps_date,
        ),
    )
