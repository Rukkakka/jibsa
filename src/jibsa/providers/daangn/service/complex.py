"""단지 정보·단지 이름 검색·지역 단지 목록·인기 단지·단지 매물 (complex, search complexes, trending-complexes, search listings --complex)."""

import logging
import re

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    Listing,
    join_address,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    note,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnComplexFilterModel,
    DaangnComplexTradeType,
    DaangnExclusiveUseAreaModel,
    DaangnLocationFilterModel,
)
from jibsa.providers.daangn.api.request.complex import (
    DaangnComplexArticlesInputModel,
    DaangnComplexArticlesRequestPayloadModel,
    DaangnComplexesRequestParameterModel,
    DaangnComplexSort,
    DaangnRegionComplexesInputModel,
    DaangnRegionComplexesRequestPayloadModel,
    DaangnSearchComplexesInputModel,
    DaangnSearchComplexesRequestPayloadModel,
    DaangnTrendingComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.api.response.complex import (
    DaangnComplexModel,
    DaangnNearbySchoolModel,
    DaangnSearchComplexNodeModel,
    DaangnSubwayInfoModel,
)
from jibsa.providers.daangn.service.common import (
    BUILDING_APPROVAL_FILTER_BY_LABEL,
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    COMPLEX_TYPE_LABELS,
    OPTIONAL_LOOKUP_ERRORS,
    DaangnListingConditions,
    DaangnRegion,
    DaangnRegionComplex,
    amount_range,
    article_to_listing,
    complex_building_notes,
    complex_list_notes,
    complex_not_found,
    complex_url,
    is_available,
    label_codes,
    listing_budget_notes,
    partial_failure_note,
    region_complex_of,
    station_name,
    trade_of,
    trade_unselected_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import (
    DaangnRealsaleRegion,
    resolve_realsale_region,
    with_sido,
)

from typing import Annotated


logger = logging.getLogger(__name__)
# 단지 정보의 중·고등학교는 학군 전체(수십 곳)가 와서 도보로 가까운 몇 곳만 보여 준다
NEAREST_SCHOOLS: int = 2
# 단지 이름 검색 후보 수. 당근 단지 검색은 이름이 조금 비슷한 단지까지 이름이 맞는 순으로 100곳 넘게 줘서, 찾는 단지는 앞쪽에
# 있고 나머지는 토큰만 쓴다 (2026-10-31 실측: '헬리오시티' 100곳 중 관련 5곳이 1~5위, '은마' 1~5위, '래미안대치팰리스' 1위,
# '잠실엘스'·'목동신시가지' 앞쪽 모두 관련. 120 이면 이름 하나 찾는 데 약 4,900토큰). 더 있으면 --limit 을 늘리라고 알린다
COMPLEX_CANDIDATE_LIMIT: int = 20
# 단지 후보(searchComplexes)·지역 단지(complexes)를 한 번에 받는 수 (서버 최대 50). 단지 후보·지역 단지·단지 매물은 남은
# 한도만큼(first)만 요청하고, 서버도 first 만큼만 준다 (2026-10-11 실측: 단지 매물 first 3·7 → 3·7건). 그래도 비공식
# API 라 넘게 주면 [:limit] 로 자르고, 잘린 만큼을 has_more('더 있음') 로 센다
COMPLEX_PAGE_SIZE: int = 50
COMPLEX_TRADE_BY_TRADE_TYPE: dict[str, DaangnComplexTradeType] = {'매매': 'BUY', '전세': 'BORROW', '월세': 'MONTH'}
COMPLEX_SORT_BY_LABEL: dict[str, DaangnComplexSort] = {
    '세대수': 'HOUSEHOLD_COUNT_DESC',
    '가격높은순': 'TRADE_PRICE_DESC',
    '가격낮은순': 'TRADE_PRICE_ASC',
    '입주최신순': 'MOVE_IN_DATE_DESC',
    '입주오래된순': 'MOVE_IN_DATE_ASC',
}
# 입주일 순은 사용승인일 순과 어긋나는 단지가 섞여 온다 (2026-10 역삼동 실측)
MOVE_IN_SORT_NOTE: str = (
    '입주일 순은 당근이 정한 순서라 사용승인일(approved_at) 순서와 어긋나는 단지가 있습니다. '
    '새 단지·오래된 단지는 approved_at 으로 다시 확인하세요'
)
# 단지 매물 목록은 20건씩 최대 6페이지. 제외된 만큼 추가 조회하지 않는다
COMPLEX_LISTINGS_PAGE_SIZE: int = 20
COMPLEX_LISTINGS_MAX_PAGES: int = 6


class DaangnPyeong(BaseModel):
    """단지 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    exclusive_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    exclusive_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    supply_pyeong: Annotated[
        float | None,
        Field(description='공급면적 (평). 흔히 말하는 "34평형" 이 이 값이다')
    ] = None
    room_count: Annotated[
        int | None,
        Field(description='방 수')
    ] = None
    bathroom_count: Annotated[
        int | None,
        Field(description='욕실 수')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수. 당근이 전용면적 묶음별로만 주므로 한 묶음에 평형이 여럿이면 null')
    ] = None
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (daangn real-price --area 에 넘긴다)')
    ] = None


class DaangnComplex(BaseModel):
    """단지 정보. 매물과 마찬가지로 좌표·사진·관리사무소 전화·후기 본문은 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소. 없으면 동까지')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    lowest_top_floor: Annotated[
        int | None,
        Field(description='가장 낮은 동의 층수')
    ] = None
    highest_top_floor: Annotated[
        int | None,
        Field(description='가장 높은 동의 층수')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    parking_count: Annotated[
        int | None,
        Field(description='총 주차 대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    heating: Annotated[
        str | None,
        Field(description='난방 방식·연료 (예: 개별난방, 도시가스)')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    building_coverage_ratio: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='당근에 올라온 이 단지의 현재 주거용 매물 수')
    ] = None
    pyeongs: Annotated[
        list[DaangnPyeong] | None,
        Field(description='평형 목록 (전용면적 순). 단지 공공 정보가 없으면 null')
    ] = []
    nearby_subways: Annotated[
        list[str] | None,
        Field(description='가까운 지하철역 (예: 신사역 (신분당선, 도보 4분)). 단지 공공 정보가 없으면 null')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 도보로 가까운 중·고등학교 (예: 서울논현초등학교 (배정, 도보 16분)). 단지 공공 정보가 없으면 null')
    ] = []
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기 내용은 url 의 당근 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다')
    ] = []


class DaangnComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘긴다)')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형 (아파트, 오피스텔, 주상복합 ...)')
    ] = None
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    address: Annotated[
        str | None,
        Field(description='주소 (지번, 없으면 도로명)')
    ] = None


def _subway(item: DaangnSubwayInfoModel) -> str:
    details = [item.line_name] if item.line_name else []
    if item.walking_time_min is not None:
        details.append(f'도보 {round(item.walking_time_min)}분')
    name = station_name(item.station_name or '')
    return f'{name} ({", ".join(details)})' if details else name


def _school(item: DaangnNearbySchoolModel, assigned: bool = False) -> str | None:
    if item.school is None or not item.school.name:
        return None
    details = ['배정'] if assigned else []
    if item.walking_time_min is not None:
        details.append(f'도보 {round(item.walking_time_min)}분')
    return f'{item.school.name} ({", ".join(details)})' if details else item.school.name


def _nearest_schools(items: list[DaangnNearbySchoolModel]) -> list[DaangnNearbySchoolModel]:
    return sorted(
        (item for item in items if item.walking_time_min is not None),
        key=lambda item: item.walking_time_min or 0,
    )[:NEAREST_SCHOOLS]


def complex_to_summary(complex_: DaangnComplexModel) -> DaangnComplex:
    """단지 페이지 레코드를 `DaangnComplex` 로 바꾼다.

    후기는 본문을 옮기지 않고 수만 담는다. 후기가 있으면 원 사이트에서 보라는 안내를 `notes` 로 붙인다.
    """
    danji = complex_.proptier_danji
    address = danji.addresses[0] if danji and danji.addresses else None
    region = complex_.region
    pyeongs = [
        DaangnPyeong(
            exclusive_m2=info.exclusive_area,
            exclusive_pyeong=m2_to_pyeong(info.exclusive_area),
            supply_m2=info.supply_area,
            supply_pyeong=m2_to_pyeong(info.supply_area),
            room_count=info.room_count,
            bathroom_count=info.bathroom_count,
            household_count=group.total_count if len(group.py_infos) == 1 else None,
            area_group=group.label,
        )
        for group in (danji.area_groups if danji else [])
        for info in group.py_infos
    ]
    schools = []
    if danji:
        schools = [_school(item, assigned=True) for item in danji.assigned_schools]
        schools += [_school(item) for item in _nearest_schools(danji.middle_schools)]
        schools += [_school(item) for item in _nearest_schools(danji.high_schools)]
    heating = ', '.join(value for value in (danji.heating_method, danji.heating_fuel) if value) if danji else ''
    review_count = complex_.lived_review_count
    url = complex_url(complex_.original_id)
    return DaangnComplex(
        complex_id=complex_.original_id,
        name=complex_.name,
        property_type=COMPLEX_TYPE_LABELS.get(complex_.type or '', complex_.type),
        address=normalize_address(
            address.jibun_address if address and address.jibun_address
            else join_address(region.name1, region.name2, region.name3) if region else None
        ),
        road_address=normalize_address(address.road_address if address else None),
        households=danji.households if danji and danji.households is not None else complex_.households,
        dong_count=danji.dong_count if danji and danji.dong_count is not None else complex_.building_count,
        approved_at=normalize_date(complex_.approval_date),
        lowest_top_floor=danji.min_floor if danji else None,
        highest_top_floor=danji.max_floor if danji else None,
        construction_company=danji.constructor_name if danji else None,
        parking_count=danji.parking_count if danji else None,
        parking_per_household=danji.parking_per_household if danji else None,
        heating=heating or None,
        floor_area_ratio=danji.floor_area_ratio if danji else None,
        building_coverage_ratio=danji.building_coverage_ratio if danji else None,
        listing_count=complex_.live_article_count.total if complex_.live_article_count else None,
        # 단지 공공 정보가 없으면 평형·역·학교는 모른다 (null). 2026-10-10 실측: 아파트·오피스텔·주상복합·도시형 13곳 모두 있었다
        pyeongs=sorted(pyeongs, key=lambda pyeong: pyeong.exclusive_m2 or 0) if danji else None,
        nearby_subways=[_subway(item) for item in danji.subways if item.station_name] if danji else None,
        schools=[school for school in schools if school] if danji else None,
        review_count=review_count,
        url=url,
        notes=[
            f'이 단지에 거주 후기 {review_count}개가 있습니다. 후기 내용은 당근 단지 페이지({url})에서 확인하세요'
        ] if review_count else [],
    )


def get_complex(client: DaangnClient, complex_id: int) -> DaangnComplex:
    """단지 정보를 조회한다 (단지 페이지 1회).

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND.
    """
    try:
        response = client.run_request_complexes(DaangnComplexesRequestParameterModel(original_id=complex_id))
    except HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise complex_not_found(complex_id) from None
        raise
    if response.complex is None:
        raise complex_not_found(complex_id)
    return complex_to_summary(response.complex)


def _candidate(node: DaangnSearchComplexNodeModel) -> DaangnComplexCandidate:
    buildings = [edge.node for edge in (node.buildings.edges if node.buildings else []) if edge.node]
    address = next((building.jibun_address for building in buildings if building.jibun_address), None)
    address = address or next((building.road_address for building in buildings if building.road_address), None)
    return DaangnComplexCandidate(
        complex_id=node.original_id,
        property_type=COMPLEX_TYPE_LABELS.get(node.type or '', node.type),
        name=node.name,
        address=normalize_address(address),
    )


def search_complexes(
    client: DaangnClient,
    name: str,
    limit: int = COMPLEX_CANDIDATE_LIMIT,
    *,
    notes: list[str],
) -> list[DaangnComplexCandidate]:
    """단지 이름으로 단지 후보를 찾는다 (전국, 이름이 비슷한 순). 50개씩 페이지를 넘겨 받는다.

    단지 후보는 지역 검색(search locations)에 덤으로 붙는 결과라, 어느 페이지에서 실패하든(쿼리 변경·요청
    제한·서버 오류) 그때까지 받은 후보를 돌려주고 이유를 `notes` 로 알린다 (`partial_failure_note`).
    """
    candidates: list[DaangnComplexCandidate] = []
    seen: set[str] = set()
    after = None
    inspected = 0
    has_more = False
    while inspected < limit:
        try:
            response = client.run_request_search_complexes(
                DaangnSearchComplexesRequestPayloadModel(
                    input=DaangnSearchComplexesInputModel(name=name),
                    first=min(COMPLEX_PAGE_SIZE, limit - inspected),
                    after=after,
                )
            )
            result = unwrap_graphql(response, response.data.search_complexes if response.data else None, '단지 검색')
        except OPTIONAL_LOOKUP_ERRORS as exc:
            logger.warning('daangn complex search failed after %d candidates (%s)', len(candidates), exc)
            received = f'단지 후보는 {len(candidates)}개까지만 받았습니다. ' if candidates else ''
            notes.append(note('실패', received + partial_failure_note(exc, '단지 검색', '나머지 단지 후보를' if candidates else '단지 후보를')))
            # 더 있는지는 모르므로 아래의 '--limit 을 늘리라' 안내는 붙이지 않는다
            return candidates[:limit]
        nodes = [edge.node for edge in result.edges if edge.node]
        inspected += len(nodes)
        for node in nodes:
            if node.original_id not in seen:
                candidates.append(_candidate(node))
                seen.add(node.original_id)
        page = result.page_info
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page and page.has_next_page) or len(candidates) > limit
        if not has_more or not nodes or inspected >= limit:
            break
        if page is None or not page.end_cursor or page.end_cursor == after:
            notes.append('단지 후보의 다음 페이지 커서를 받지 못해 조회를 중단했습니다')
            break
        after = page.end_cursor
    if has_more:
        if limit >= COMPLEX_LIST_MAX_LIMIT:
            notes.append(f'단지 후보는 최대 {COMPLEX_LIST_MAX_LIMIT}개까지 조회할 수 있습니다. 단지 이름을 더 구체적으로 입력해 주세요')
        else:
            notes.append(
                f'단지 후보가 더 있습니다. --limit 을 늘리면 최대 {COMPLEX_LIST_MAX_LIMIT}개까지 조회할 수 있습니다 (현재 {limit}개 한도)'
            )
    return candidates[:limit]


class DaangnRegionComplexesResult(BaseModel):
    """동·구의 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRealsaleRegion,
        Field(description='조회한 지역')
    ]
    trade_type: Annotated[
        str,
        Field(description='최근 실거래(recent_trades)와 가격 조건의 거래 유형')
    ]
    sort: Annotated[
        str,
        Field(description='정렬 (세대수, 가격높은순, 가격낮은순, 입주최신순, 입주오래된순)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='단지가 더 있는지')
    ]
    complexes: Annotated[
        list[DaangnRegionComplex],
        Field(description='정렬 순 단지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='지역을 고른 방법, 정렬·후기 안내. CLI 가 결과 위에 붙인다')
    ] = []


class DaangnComplexConditions(RequestModel):
    """지역 단지 목록 조건 (search complexes). 웹 지도 단지 탭 필터와 같고 당근 서버에서 건다.

    가격 조건은 지금 매물 가격이 아니라 단지의 예전 실거래 가격으로 거른다 (`list_region_complexes`).
    """

    complex_types: Annotated[
        list[str],
        Field(description='단지 유형 (COMPLEX_TYPE_FILTER_BY_LABEL). 비면 전체 (도시형 생활주택도 섞인다)')
    ] = []
    trade_type: Annotated[
        str,
        Field(description='가격 조건과 단지마다 붙는 최근 실거래의 거래 유형 (매매·전세·월세)')
    ] = '매매'
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원, 예전 실거래 기준)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원, 예전 실거래 기준)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원, 예전 실거래 기준)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원, 예전 실거래 기준)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원, 예전 실거래 기준)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원, 예전 실거래 기준)')
    ] = None
    area_min: Annotated[
        float | None,
        Field(description='면적 하한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    area_max: Annotated[
        float | None,
        Field(description='면적 상한 (㎡). 단지 조건과 최근 실거래 면적에 함께 건다')
    ] = None
    building_approval: Annotated[
        str | None,
        Field(description='사용승인일 (BUILDING_APPROVAL_FILTER_BY_LABEL)')
    ] = None
    household_min: Annotated[
        int | None,
        Field(description='세대수 하한')
    ] = None
    household_max: Annotated[
        int | None,
        Field(description='세대수 상한')
    ] = None
    parking_min: Annotated[
        float | None,
        Field(description='세대당 주차 대수 하한')
    ] = None


def complex_filter_of(conditions: DaangnComplexConditions) -> DaangnComplexFilterModel:
    """지역 단지 목록 조건을 웹 단지 탭 필터로 바꾼다."""
    return DaangnComplexFilterModel(
        type=label_codes(conditions.complex_types, COMPLEX_TYPE_FILTER_BY_LABEL),
        trade_type=[COMPLEX_TRADE_BY_TRADE_TYPE[conditions.trade_type]],
        deposit=amount_range(conditions.deposit_min, conditions.deposit_max),
        monthly_pay=amount_range(conditions.rent_min, conditions.rent_max),
        price=amount_range(conditions.price_min, conditions.price_max),
        building_approval_date=label_codes(
            [conditions.building_approval] if conditions.building_approval else None, BUILDING_APPROVAL_FILTER_BY_LABEL,
        ),
        min_area=conditions.area_min,
        max_area=conditions.area_max,
        min_household_count=conditions.household_min,
        max_household_count=conditions.household_max,
        min_parking_per_household=conditions.parking_min,
    )


def list_region_complexes(
    client: DaangnClient,
    query: str,
    *,
    city: str | None = None,
    conditions: DaangnComplexConditions | None = None,
    sort: str = '세대수',
    limit: int = 120,
) -> DaangnRegionComplexesResult:
    """동·구의 단지 목록을 정렬해 받는다 (웹 지도 단지 탭, `searchComplexes`).

    지역은 `resolve_realsale_region` 으로 고른다 (동 또는 구). 조건은 웹 단지 탭 필터와 같고 당근
    서버에서 건다. 가격 조건은 지금 매물 가격이 아니라 단지의 예전 실거래 가격으로 거른다 (2026-10 역삼동
    실측: '월세 50 이하' 20곳 중 지금 월세 매물이 있는 곳은 7곳, 최근 실거래에 50 이하 월세가 있는 곳은 17곳).
    단지 유형 '아파트' 는 주상복합도 함께 찾고, 유형을 주지 않으면 도시형 생활주택도
    섞인다. `conditions.trade_type` 은 가격 조건과 단지마다 붙는 최근 실거래의 거래 유형이다. 면적 조건은 단지
    조건과 최근 실거래 면적에 함께 건다 (웹과 같다).

    Raises:
        RegionNotFoundError: 지역을 찾지 못했을 때.
        FeedQueryRejectedError: 웹이 단지 목록 쿼리를 바꿨을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnComplexConditions()
    trade_type = conditions.trade_type
    region, notes = resolve_realsale_region(client, query, city=city)
    complex_filter = complex_filter_of(conditions)
    exclusive_use_area = None
    if conditions.area_min is not None or conditions.area_max is not None:
        exclusive_use_area = DaangnExclusiveUseAreaModel(
            min=conditions.area_min or 0,
            **({'max': conditions.area_max} if conditions.area_max is not None else {}),
        )
    complexes: list[DaangnRegionComplex] = []
    seen: set[str] = set()
    after: str | None = None
    inspected = 0
    has_more = False
    while inspected < limit:
        response = client.run_request_region_complexes(
            DaangnRegionComplexesRequestPayloadModel(
                first=min(COMPLEX_PAGE_SIZE, limit - inspected),
                after=after,
                input=DaangnRegionComplexesInputModel(
                    location_filter=DaangnLocationFilterModel(original_region_id=region.region_id),
                    property_filter=complex_filter,
                    sort=COMPLEX_SORT_BY_LABEL[sort],
                ),
                trade_type=COMPLEX_TRADE_BY_TRADE_TYPE[trade_type],
                exclusive_use_area=exclusive_use_area,
            )
        )
        connection = unwrap_graphql(response, response.data.search_complexes if response.data else None, '지역 단지 목록')
        inspected += len(connection.edges)
        for edge in connection.edges:
            if edge.node is None:
                continue
            complex_ = region_complex_of(edge.node, trade_type)
            if complex_.complex_id not in seen:
                seen.add(complex_.complex_id)
                complexes.append(complex_)
        page_info = connection.page_info
        has_more = bool(page_info and page_info.has_next_page)
        if inspected >= limit or not has_more or not connection.edges:
            break
        cursor = page_info.end_cursor if page_info else None
        if not cursor or cursor == after:
            notes.append('단지 목록의 다음 페이지 커서가 없거나 반복되어 조회를 중단했습니다. 지원되는 필터로 범위를 좁혀 주세요')
            break
        after = cursor
    # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
    has_more = has_more or len(complexes) > limit
    complexes = complexes[:limit]
    if has_more:
        if limit >= COMPLEX_LIST_MAX_LIMIT:
            notes.append(
                f'--limit의 최대값은 {COMPLEX_LIST_MAX_LIMIT}입니다. 더 많은 단지가 있어 일부만 보여 줍니다. '
                '지역·단지 유형·세대수·가격 등 지원되는 필터로 검색 범위를 좁혀 주세요'
            )
        elif inspected >= limit:
            notes.append(
                f'최대 {limit}개 단지를 조회했습니다. 더 보려면 --limit을 최대 {COMPLEX_LIST_MAX_LIMIT}까지 늘리거나 '
                '지원되는 필터로 검색 범위를 좁혀 주세요'
            )

    if sort.startswith('입주'):
        notes.append(MOVE_IN_SORT_NOTE)
    notes += complex_list_notes(complexes)
    return DaangnRegionComplexesResult(
        region=region,
        trade_type=trade_type,
        sort=sort,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )


class DaangnComplexListingsResult(BaseModel):
    """단지 하나의 매물 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 매물 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='조건에 맞는 매물이 더 있는지')
    ]
    listings: Annotated[
        list[Listing],
        Field(description='단지 매물 (당근 단지 화면 순)')
    ]
    notes: Annotated[list[str], Field(exclude=True)] = []
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


def list_complex_listings(
    client: DaangnClient,
    complex_id: int,
    *,
    conditions: DaangnListingConditions | None = None,
    limit: int = 20,
) -> DaangnComplexListingsResult:
    """단지 하나의 현재 매물을 모은다 (당근 단지 화면의 매물 탭). 조건은 search listings 와 같고 서버에서 건다.

    거래 완료·숨김 매물은 빼고, 거래 조건이 여럿이면 조건에 맞는 거래로 가격을 보여 준다 (search 와 같다).
    단지 매물이라 세대수·주차대수 조건은 받지 않는다.

    Raises:
        JibsaError: 세대수·주차대수 조건을 주면 INVALID_ARGUMENT, 없는 단지면 NOT_FOUND, 그 밖의 GraphQL 에러면
            UPSTREAM_ERROR.
        FeedQueryRejectedError: 웹이 단지 매물 쿼리를 바꿨을 때.
    """
    conditions = conditions or DaangnListingConditions()
    if conditions.household_min is not None or conditions.household_max is not None or conditions.parking_min is not None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='단지 매물에는 세대수·주차대수 조건을 쓸 수 없습니다',
            hint='단지 하나의 매물이라 세대수·주차대수는 이미 정해져 있습니다. 그 조건을 빼고 다시 찾으세요',
        )
    property_filter = conditions.property_filter
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel]] = []
    # 서버 필터를 통과했지만 검색에 맞는 거래 조건을 고르지 못해 뺀 매물 수
    unselected = 0
    after = None
    inspected = 0
    seen: set[str] = set()
    has_more = False
    for _ in range(COMPLEX_LISTINGS_MAX_PAGES):
        response = client.run_request_complex_articles(
            DaangnComplexArticlesRequestPayloadModel(
                complex_id=str(complex_id),
                first=min(COMPLEX_LISTINGS_PAGE_SIZE, limit - inspected),
                after=after,
                input=DaangnComplexArticlesInputModel(property_filter=property_filter),
            )
        )
        result = unwrap_graphql(
            response, response.data.complex_by_original_id if response.data else None, '단지 매물'
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        connection = result.complex.articles
        inspected += len(connection.edges) if connection else 0
        for edge in connection.edges if connection else []:
            article = edge.node
            if article is None or article.original_id in seen or not is_available(article):
                continue
            seen.add(article.original_id)
            trade = trade_of(article, None, conditions)
            if trade is not None:
                matched.append((article, trade))
            else:
                unselected += 1
        page_info = connection.page_info if connection else None
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page_info and page_info.has_next_page) or len(matched) > limit
        if inspected >= limit or not has_more or page_info is None or not page_info.end_cursor:
            break
        after = page_info.end_cursor

    # 카드에는 시·도가 없어 단지가 있는 동을 지역 검색으로 한 번 채운다 (with_sido)
    sido_cache: dict[tuple[str, str], str | None] = {}
    listings: list[Listing] = []
    shown: list[DaangnArticleModel] = []
    for article, trade in matched[:limit]:
        listing = article_to_listing(with_sido(client, article, sido_cache), trade=trade)
        if listing is not None:
            listings.append(listing)
            shown.append(article)
    return DaangnComplexListingsResult(
        complex_id=str(complex_id),
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        url=complex_url(complex_id),
        notes=listing_budget_notes(limit, inspected, len(listings), has_more=has_more, eligible=len(matched))
            + trade_unselected_notes(unselected)
            + complex_building_notes(shown),
    )


APPROVAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'(\d{4})\.(\d{2})\.(\d{2})')


class DaangnTrendingComplex(BaseModel):
    """요즘 많이 보는 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[int, Field(description='순위')]
    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='시·도·구')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    representative_area_m2: Annotated[
        float | None,
        Field(description='대표 평형 전용면적 (㎡)')
    ] = None
    recent_sale_manwon: Annotated[
        int | None,
        Field(description='대표 평형 최근 매매가 (만원)')
    ] = None


class DaangnTrendingComplexesResult(BaseModel):
    """요즘 많이 보는 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnRegion, Field(description='기준 동')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    complexes: Annotated[list[DaangnTrendingComplex], Field(description='인기 순 단지')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='빈 결과 안내. CLI 가 결과 위에 붙인다')
    ] = []


def list_trending_complexes(client: DaangnClient, region: DaangnRegion) -> DaangnTrendingComplexesResult:
    """동 주변에서 요즘 많이 보는 단지 (`trendingComplexes`, 요청 1회). 개수는 때마다 다르다 (0~20여 곳).

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_trending_complexes(
        DaangnTrendingComplexesRequestPayloadModel(region_id=str(region.region_id))
    )
    found = unwrap_graphql(response, response.data.trending_complexes if response.data else None, '인기 단지')
    complexes: list[DaangnTrendingComplex] = []
    for rank, item in enumerate(found, start=1):
        groups = item.proptier_danji.exclusive_area_groups if item.proptier_danji else []
        group = next((group for group in groups if group.is_representative), groups[0] if groups else None)
        info = group.py_infos[0] if group and group.py_infos else None
        sale = next(
            (edge.node.trade_price for edge in info.sale_realsale.edges if edge.node),
            None,
        ) if info and info.sale_realsale else None
        approval = APPROVAL_DATE_PATTERN.search(item.approval_date_text or '')
        complexes.append(DaangnTrendingComplex(
            rank=rank,
            complex_id=item.original_id,
            name=item.name,
            type=COMPLEX_TYPE_LABELS.get(item.type or '', item.type),
            address=normalize_address(join_address(item.region.name1, item.region.name2)) if item.region else None,
            households=item.households,
            approved_at='-'.join(approval.groups()) if approval else None,
            representative_area_m2=info.exclusive_area if info else None,
            recent_sale_manwon=sale,
        ))
    # 같은 동도 때에 따라 빈 목록이다. 이른 아침에 잦다 (2026-10-27 실측: 역삼동이 아침 6~8시 7번 중 5번 0곳, 낮·저녁
    # 10~22곳. 10-11 에 0곳이던 세종 새롬동·도담동도 저녁엔 6·7곳). 기준은 모르지만 근처에 단지가 없다는 뜻으로 읽히지 않게 알린다
    notes = [] if complexes else [
        f'당근이 {region.name3} 주변 인기 단지를 주지 않았습니다. 단지가 없다는 뜻은 아닙니다. '
        '이 목록은 때에 따라 달라 이른 아침엔 자주 비고, 낮에 다시 부르면 나올 수 있습니다. '
        f'지역 단지 목록은 jibsa daangn search complexes {region.name3} 에서 봅니다'
    ]
    return DaangnTrendingComplexesResult(region=region, returned=len(complexes), complexes=complexes, notes=notes)
