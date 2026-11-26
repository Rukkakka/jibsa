"""단지 정보·단지 이름 검색·지역·지도 범위 단지 목록·인기 단지·단지 매물 (complex, search complexes, trending-complexes, search listings --complex)."""

import logging
import re
from collections.abc import Callable
from math import inf

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.korean import quoted
from jibsa.core.listing import (
    AmountSet,
    Listing,
    NumberRange,
    Result,
    holding_unread_dates,
    join_address,
    keep_unread_dates,
    m2_to_pyeong,
    more_hint,
    normalize_address,
    note,
    null_items_note,
    number_range,
    read_date,
)
from jibsa.core.schema import RequestModel
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.common import (
    DaangnComplexFilterModel,
    DaangnComplexTradeType,
    DaangnExclusiveUseAreaModel,
    is_empty_property_filter,
)
from jibsa.providers.daangn.api.request.complex import (
    DaangnComplexArticlesInputModel,
    DaangnComplexArticlesRequestPayloadModel,
    DaangnComplexByClusterIdInputModel,
    DaangnComplexByClusterIdRequestPayloadModel,
    DaangnComplexesRequestParameterModel,
    DaangnComplexSort,
    DaangnSearchComplexesInputModel,
    DaangnSearchComplexesRequestPayloadModel,
    DaangnSearchComplexesViewportInputModel,
    DaangnSearchComplexesViewportRequestPayloadModel,
    DaangnTrendingComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.common import (
    DaangnArticleModel,
    DaangnTradeModel,
)
from jibsa.providers.daangn.api.response.complex import (
    DaangnAreaGroupModel,
    DaangnComplexModel,
    DaangnNearbySchoolModel,
    DaangnProptierDanjiModel,
    DaangnRegionComplexesModel,
)
from jibsa.providers.daangn.service.common import (
    BUILDING_APPROVAL_FILTER_BY_LABEL,
    COMPLEX_LIST_MAX_LIMIT,
    COMPLEX_LISTING_DEFAULT_SALES_TYPES,
    COMPLEX_TYPE_FILTER_BY_LABEL,
    COMPLEX_TYPE_LABELS,
    LISTING_MAX_LIMIT,
    OPTIONAL_LOOKUP_ERRORS,
    POINT_ZOOM,
    DaangnListingConditions,
    DaangnRegion,
    DaangnRegionComplex,
    amount_range,
    article_to_listing,
    code_label,
    complex_building_notes,
    complex_list_notes,
    complex_not_found,
    complex_url,
    cursor_stopped_note,
    is_available,
    label_codes,
    listing_budget_notes,
    map_view_bounds,
    most_households,
    next_cursor,
    no_trade_notes,
    partial_failure_note,
    region_complex_of,
    region_name_parts,
    stalled_page,
    station_name,
    trade_of,
    unwrap_graphql,
    uses_supply_pyeong,
    web_minutes,
)
from jibsa.providers.daangn.service.region import (
    DaangnArea,
    DaangnRealsaleRegion,
    region_or_none,
    resolve_realsale_region,
    with_sido,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


logger = logging.getLogger(__name__)
# 단지 정보의 중·고등학교는 학군 전체(수십 곳)가 와서, 당근 웹 학군 카드처럼 `_web_school_card` 규칙으로 남긴 앞 몇 곳만
# 보여 준다 (ComplexSchoolSection `slice(0,2)`)
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
# 웹 지도 단지 탭의 기본 거래 유형 (ChatPanelActionsContext `d`: 거래 칩이 없으면 BUY)
DEFAULT_COMPLEX_TRADE_TYPE: str = '매매'
COMPLEX_SORT_BY_LABEL: dict[str, DaangnComplexSort] = {
    '세대수': 'HOUSEHOLD_COUNT_DESC',
    '가격높은순': 'TRADE_PRICE_DESC',
    '가격낮은순': 'TRADE_PRICE_ASC',
    '입주최신순': 'MOVE_IN_DATE_DESC',
    '입주오래된순': 'MOVE_IN_DATE_ASC',
}
# 입주일 순은 사용승인일 순과 어긋나는 단지가 섞여 온다 (2026-10 역삼동 실측)
MOVE_IN_SORT_NOTE: str = (
    '입주일 순은 당근이 정한 순서라 사용승인일(approved_date) 순서와 어긋나는 단지가 있습니다. '
    '새 단지·오래된 단지는 approved_date 로 다시 확인하세요'
)
# 단지 매물 목록은 20건씩 최대 6페이지. 제외된 만큼 추가 조회하지 않는다
COMPLEX_LISTINGS_PAGE_SIZE: int = 20
COMPLEX_LISTINGS_MAX_PAGES: int = 6


class DaangnPyeong(BaseModel):
    """단지 평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    area_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    supply_area_pyeong: Annotated[
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
        Field(description='세대수. 당근이 묶음별로만 주므로 한 묶음에 평형이 여럿이면 null. 당근이 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (예: 32. 아파트형 단지만, real-price·price-trend --pyeong 에 넘긴다)')
    ] = None
    representative: Annotated[
        bool,
        Field(description='당근 웹이 처음 보여 주는 대표 평형 묶음인지 (price-trend 의 기본 평형)')
    ] = False
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음. 아파트형이 아닌 단지만 real-price·price-trend --area 에 넘긴다 (아파트형은 pyeong 을 --pyeong 에)')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 공급 평형 묶음은 아파트형 단지에만 있어 그 밖에는 해당 없음이라 키를 뺀다
        data: dict[str, Any] = handler(self)
        if self.pyeong is None:
            data.pop('pyeong', None)
        return data


class DaangnComplex(Result):
    """단지 정보. 매물과 마찬가지로 좌표·사진·관리사무소 전화·후기 본문은 담지 않는다.

    `notes`: 후기를 원 사이트에서 보라는 안내. CLI 가 결과 위에 붙인다
    """

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
    complex_type: Annotated[
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
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 꼭대기 층수의 최소(lowest)·최대(highest). 모르면 null')
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
        Field(description='난방 방식 (예: 개별난방)')
    ] = None
    heating_fuel: Annotated[
        str | None,
        Field(description='난방 연료 (예: 도시가스)')
    ] = None
    floor_area_ratio_percent: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    building_coverage_ratio_percent: Annotated[
        float | None,
        Field(description='건폐율 (%)')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='당근에 올라온 이 단지의 현재 주거용 매물 수')
    ] = None
    pyeongs: Annotated[
        list[DaangnPyeong] | None,
        Field(description='평형 목록 (전용면적 순). 아파트형 단지는 공급 평 묶음(pyeong)이 붙는다. 단지 공공 정보가 없으면 null')
    ] = []
    nearby_stations: Annotated[
        list[str] | None,
        Field(description='가까운 지하철역 (예: 신사역 (신분당선, 도보 4분)). 도보 시간이 짧은 순 (당근 웹 단지 화면 가까운 역 순서). 단지 공공 정보가 없으면 null')
    ] = []
    schools: Annotated[
        list[str] | None,
        Field(description='배정 초등학교와 당근 웹 학군 카드의 중·고등학교 2곳씩 (이 단지 주민이 많이 다니는 순, 같으면 도보 순. 예: 서울가락초등학교 (배정, 도보 6분, 이 단지 20명 이상)). 단지 공공 정보가 없으면 null')
    ] = []
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수. 후기 내용은 url 의 당근 단지 페이지에서 본다')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]


class DaangnComplexCandidate(BaseModel):
    """이름으로 찾은 단지 후보. 좌표는 담지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[
        str,
        Field(description='단지 ID (daangn complex 에 넘긴다)')
    ]
    complex_type: Annotated[
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


def _school_walk(item: DaangnNearbySchoolModel, assigned: bool) -> float | None:
    """웹이 쓰는 도보 시간. 배정 학교는 walkingTimeMin 이 없으면 길찾기 시간(workingTime)이다 (ComplexSchoolSection `Re`)."""
    return item.walking_time_min if item.walking_time_min is not None or not assigned else item.working_time


def _school_distance(item: DaangnNearbySchoolModel, assigned: bool) -> float | None:
    """웹이 쓰는 도보 거리. 배정 학교는 walkingDistanceMeters 가 없으면 직선거리(distance)다 (ComplexSchoolSection `Re`)."""
    return item.walking_distance_m if item.walking_distance_m is not None or not assigned else item.distance


def _or_inf(value: float | None) -> float:
    """모르는 값(None)을 맨 뒤로 보내는 정렬 키. 0 은 그대로 둔다 (웹 `R` 의 `?? 2**53-1`)."""
    return inf if value is None else value


def _resident_count(item: DaangnNearbySchoolModel) -> int:
    return (item.school.resident_count if item.school else None) or 0


def _web_school_order(items: list[DaangnNearbySchoolModel], assigned: bool) -> list[DaangnNearbySchoolModel]:
    """당근 웹 단지 학군 순서 (ComplexSchoolSection `W`): 이 단지 주민이 많이 다니는 곳, 같으면 도보 시간·거리 순 (모르면 뒤)."""
    def key(item: DaangnNearbySchoolModel) -> tuple[int, bool, float, bool, float]:
        walk = _school_walk(item, assigned)
        distance = _school_distance(item, assigned)
        return (-_resident_count(item), walk is None, walk or 0, distance is None, distance or 0)
    return sorted(items, key=key)


def _web_school_card(items: list[DaangnNearbySchoolModel]) -> list[DaangnNearbySchoolModel]:
    """당근 웹 단지 학군 카드에 보이는 중·고등학교 (ComplexSchoolSection `Ve(list).slice(0,2)`).

    웹 순서로 세운 뒤 도보 20분 안 학교(없으면 도보 시간·거리 순으로 가장 가까운 한 곳. 둘 다 모르면 첫 학교), 이 단지 주민이
    다니는 학교, 학교가 5곳 이하면 자동 배정에 도보 40분 안 학교만 남겨 앞 `NEAREST_SCHOOLS` 곳이다. 분은 웹처럼 반올림해 견준다
    (`He`·`Ue` 의 `Math.round`). 예전에는 도보 가까운 2곳이라 주민이 많이 다니는 먼 학교나 20분 안에 학교가 없는 단지에서 웹과
    달랐다 (#215, 2026-11-12 번들 대조).
    """
    ordered = _web_school_order(items, assigned=False)
    walks = {id(item): _school_walk(item, False) for item in ordered}
    near = {id(item) for item in ordered if (walk := walks[id(item)]) is not None and web_minutes(walk) <= 20}
    if not near and ordered:
        # 웹 `[...e].sort(G).slice(0,1)`: 시간, 같으면 거리 순 (모르면 뒤). 모두 모르면 안정 정렬이라 첫 학교. 웹 비교(`R`)는
        # `e ?? 2**53-1` 이라 0 분·0 m 도 값이다. `or inf` 로 두면 거리 0 이 '모름' 이 됐다 (2026-11-12 리뷰, 웹 배포 2026-11-v73 번들 대조)
        nearest = min(ordered, key=lambda item: (_or_inf(walks[id(item)]), _or_inf(_school_distance(item, False))))
        near = {id(nearest)}
    kept = [
        item for item in ordered
        if id(item) in near
        or _resident_count(item) > 0
        or (
            len(items) <= 5 and item.allocation_method == '자동'
            and (walk := walks[id(item)]) is not None and web_minutes(walk) <= 40
        )
    ]
    return kept[:NEAREST_SCHOOLS]


def _school(item: DaangnNearbySchoolModel, assigned: bool = False) -> str | None:
    if item.school is None or not item.school.name:
        return None
    details = ['배정'] if assigned else []
    walk = _school_walk(item, assigned)
    if walk is not None:
        details.append(f'도보 {web_minutes(walk)}분')
    if _resident_count(item) > 0:
        details.append(f'이 단지 {_resident_count(item)}명 이상')
    return f'{item.school.name} ({", ".join(details)})' if details else item.school.name


def _pyeong_groups(complex_type: str | None, danji: DaangnProptierDanjiModel) -> tuple[bool, list[DaangnAreaGroupModel]]:
    """단지 평형을 묶는 평형 묶음과, 그것이 공급 평 묶음인지 (`complex_pyeongs`)."""
    supply = uses_supply_pyeong(complex_type, danji.supply_pyeong_area_groups)
    return supply, danji.supply_pyeong_area_groups if supply else danji.area_groups


def complex_pyeongs(complex_type: str | None, danji: DaangnProptierDanjiModel) -> list[DaangnPyeong]:
    """단지 평형 목록. 당근 웹처럼 아파트형 단지는 공급 평 묶음으로, 그 밖은 전용면적 묶음으로 묶는다 (utils `n()`).

    공급 평 묶음의 평형은 같은 타입 코드(ptpCd)가 든 전용면적 묶음도 함께 적는다 (어느 전용면적 묶음의 평형인지 보이게).
    `--area` 는 아파트형이 아닌 단지만 받아(`choose_pyeong`) 아파트형은 `pyeong` 으로 고른다 (2026-11-12 실측: 헬리오시티
    real-price·price-trend --area 84 는 INVALID_ARGUMENT). 예전에는 늘 전용면적 묶음이라 헬리오시티 84㎡ 묶음에 32평·33평이
    섞였다 (#215, 2026-11-12 실측).
    """
    exclusive_by_code = {
        info.ptp_cd: group.label for group in danji.area_groups for info in group.py_infos if info.ptp_cd is not None
    }
    supply, groups = _pyeong_groups(complex_type, danji)
    return [
        DaangnPyeong(
            area_m2=info.exclusive_area,
            area_pyeong=m2_to_pyeong(info.exclusive_area),
            supply_area_m2=info.supply_area,
            supply_area_pyeong=m2_to_pyeong(info.supply_area),
            room_count=info.room_count,
            bathroom_count=info.bathroom_count,
            # 평형에서 빈 항목을 뺐으면 묶음의 평형이 하나였는지 알 수 없어 세대수도 모른다 (null)
            household_count=group.total_count if len(group.py_infos) == 1 and not group.null_items('py_infos') else None,
            pyeong=group.label if supply else None,
            representative=bool(group.is_representative),
            area_group=(exclusive_by_code.get(info.ptp_cd) if info.ptp_cd is not None else None) if supply else group.label,
        )
        for group in groups
        for info in group.py_infos
    ]


def complex_to_summary(complex_: DaangnComplexModel) -> DaangnComplex:
    """단지 페이지 레코드를 `DaangnComplex` 로 바꾼다.

    후기는 본문을 옮기지 않고 수만 담는다. 후기가 있으면 원 사이트에서 보라는 안내를 `notes` 로 붙인다.
    """
    danji = complex_.proptier_danji
    address = danji.addresses[0] if danji and danji.addresses else None
    region = complex_.region
    pyeongs = complex_pyeongs(complex_.type, danji) if danji else []
    schools = []
    if danji:
        schools = [_school(item, assigned=True) for item in _web_school_order(danji.assigned_schools, assigned=True)]
        schools += [_school(item) for item in _web_school_card(danji.middle_schools)]
        schools += [_school(item) for item in _web_school_card(danji.high_schools)]
    review_count = complex_.lived_review_count
    url = complex_url(complex_.original_id)
    notes = [
        f'이 단지에 거주 후기 {review_count}개가 있습니다. 후기 내용은 당근 단지 페이지({url})에서 확인하세요'
    ] if review_count else []
    # 평형이 하나뿐인 묶음에서 빈 항목을 빼고 읽었으면 그 묶음의 세대수를 모른다 (`complex_pyeongs`)
    dropped = sum(
        group.null_items('py_infos') for group in _pyeong_groups(complex_.type, danji)[1] if len(group.py_infos) == 1
    ) if danji else 0
    if dropped:
        notes.append(null_items_note('당근 단지 평형', dropped, ('pyeongs 의 household_count',)))
    # 당근 웹 단지 화면 '가까운 역' 순서 (`Ye`): 도보 시간이 짧은 순 (모르면 뒤). 같으면 서버 순서를 지킨다 (안정 정렬).
    # 웹은 같을 때 거리도 견주지만 jibsa 가 받는 단지 응답의 역(`DaangnSubwayInfoModel`)에는 거리 칸이 없다. 웹과 달리 같은 이름 역을 합치거나
    # 앞 2곳으로 자르지 않고 (역, 노선)마다 모두 낸다.
    nearby_stations: list[str] | None = None
    if danji:
        nearby_stations = []
        for subway_item in sorted(danji.subways, key=lambda subway: _or_inf(subway.walking_time_min)):
            if not subway_item.station_name:
                continue
            details = [subway_item.line_name] if subway_item.line_name else []
            if subway_item.walking_time_min is not None:
                details.append(f'도보 {web_minutes(subway_item.walking_time_min)}분')
            name = station_name(subway_item.station_name)
            nearby_stations.append(f'{name} ({", ".join(details)})' if details else name)
    return DaangnComplex(
        complex_id=complex_.original_id,
        name=complex_.name,
        complex_type=code_label(COMPLEX_TYPE_LABELS, complex_.type),
        address=normalize_address(
            address.jibun_address if address and address.jibun_address
            else join_address(region.name1, region.name2, region.name3) if region else None
        ),
        road_address=normalize_address(address.road_address if address else None),
        household_count=danji.households if danji and danji.households is not None else complex_.households,
        dong_count=danji.dong_count if danji and danji.dong_count is not None else complex_.building_count,
        approved_date=read_date(complex_.approval_date, '사용승인일'),
        building_floor_range=number_range(danji.min_floor, danji.max_floor) if danji else None,
        construction_company=danji.constructor_name if danji else None,
        parking_count=danji.parking_count if danji else None,
        parking_per_household=danji.parking_per_household if danji else None,
        # 값이 없는 방식·연료는 모름(null)이다 (빈 글자도 같다)
        heating=(danji.heating_method or None) if danji else None,
        heating_fuel=(danji.heating_fuel or None) if danji else None,
        floor_area_ratio_percent=danji.floor_area_ratio if danji else None,
        building_coverage_ratio_percent=danji.building_coverage_ratio if danji else None,
        listing_count=complex_.live_article_count.total if complex_.live_article_count else None,
        # 단지 공공 정보가 없으면 평형·역·학교는 모른다 (null). 2026-10-10 실측: 아파트·오피스텔·주상복합·도시형 13곳 모두 있었다
        pyeongs=sorted(pyeongs, key=lambda pyeong: pyeong.area_m2 or 0) if danji else None,
        nearby_stations=nearby_stations,
        schools=[school for school in schools if school] if danji else None,
        review_count=review_count,
        url=url,
        notes=notes,
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


def search_complexes(
    client: DaangnClient,
    name: str,
    limit: int = COMPLEX_CANDIDATE_LIMIT,
    *,
    notes: list[str],
) -> list[DaangnComplexCandidate] | None:
    """단지 이름으로 단지 후보를 찾는다 (전국, 이름이 비슷한 순). 50개씩 페이지를 넘겨 받는다.

    단지 후보는 지역 검색(search locations)에 덤으로 붙는 결과라, 어느 페이지에서 실패하든(쿼리 변경·요청
    제한·서버 오류) 그때까지 받은 후보를 돌려주고 이유를 `notes` 로 알린다 (`partial_failure_note`). 첫 쪽부터 실패해
    받은 후보가 없으면 '후보 없음' 이 아니라 모름이라 None 이다 (search locations 의 다른 칸과 같다, 2026-11-12 리뷰).
    """
    candidates: list[DaangnComplexCandidate] = []
    seen: set[str] = set()
    after = None
    inspected = 0
    has_more = False
    stopped = False
    while inspected < limit:
        try:
            response = client.run_request_search_complexes(
                DaangnSearchComplexesRequestPayloadModel(
                    input=DaangnSearchComplexesInputModel(name=name),
                    first=min(COMPLEX_PAGE_SIZE, limit - inspected),
                    after=after,
                )
            )
            result = unwrap_graphql(response, response.data.search_complexes if response.data else None, '단지 검색', conditions=False)
        except OPTIONAL_LOOKUP_ERRORS as exc:
            logger.warning('daangn complex search failed after %d candidates (%s)', len(candidates), exc)
            received = f'단지 후보는 {len(candidates)}곳까지만 받았습니다. ' if candidates else ''
            notes.append(note('실패', received + partial_failure_note(exc, '단지 검색', '나머지 단지 후보를' if candidates else '단지 후보를')))
            # 더 있는지는 모르므로 아래의 '--limit 을 늘리라' 안내는 붙이지 않는다
            return candidates[:limit] if candidates else None
        if stalled_page(result.page_info, after):
            stopped = True
            break
        nodes = [edge.node for edge in result.edges if edge.node]
        inspected += len(nodes)
        for node in nodes:
            if node.original_id not in seen:
                buildings = [edge.node for edge in (node.buildings.edges if node.buildings else []) if edge.node]
                # 건물의 지번 주소를 먼저, 없으면 도로명 주소를 쓴다
                address = next((building.jibun_address for building in buildings if building.jibun_address), None)
                address = address or next((building.road_address for building in buildings if building.road_address), None)
                candidates.append(DaangnComplexCandidate(
                    complex_id=node.original_id,
                    complex_type=code_label(COMPLEX_TYPE_LABELS, node.type),
                    name=node.name,
                    address=normalize_address(address),
                ))
                seen.add(node.original_id)
        page = result.page_info
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page and page.has_next_page) or len(candidates) > limit
        if not has_more or inspected >= limit:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 에 닿은 것이 아니라
        # --limit 을 늘려도 더 받지 못하니, 아래의 '--limit 을 늘리면' 안내 대신 멈췄다고 알린다
        cursor = next_cursor(page, after, received=len(nodes))
        if cursor is None:
            stopped = True
            break
        after = cursor
    if stopped:
        notes.append(note('일부', cursor_stopped_note('단지 후보', f'{len(candidates)}곳') + '. 더 구체적인 단지 이름으로 검색하세요'))
    elif has_more:
        if limit >= COMPLEX_LIST_MAX_LIMIT:
            notes.append(note('일부', f'단지 후보는 최대 {COMPLEX_LIST_MAX_LIMIT}곳까지 조회할 수 있습니다. 더 구체적인 단지 이름으로 검색하세요'))
        else:
            notes.append(note(
                '일부',
                f'단지 후보가 더 있습니다. --limit 을 늘리면 최대 {COMPLEX_LIST_MAX_LIMIT}곳까지 조회할 수 있습니다 (현재 {limit}곳 한도)',
            ))
    return candidates[:limit]


class DaangnRegionComplexesResult(Result):
    """동·구의 단지 목록.

    `notes`: 지역을 고른 방법, 정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

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


class DaangnComplexConditions(RequestModel):
    """지역 단지 목록 조건 (search complexes). 웹 지도 단지 탭 필터와 같고 당근 서버에서 건다.

    가격 조건은 지금 매물 가격이 아니라 단지의 과거 실거래 가격으로 거른다 (`list_region_complexes`).
    """

    complex_types: Annotated[
        list[str],
        Field(description='단지 유형 (COMPLEX_TYPE_FILTER_BY_LABEL). 비면 전체 (도시형 생활주택도 섞인다)')
    ] = []
    # 리뷰 오탐 (2026-11-20): CLI(search complexes)는 --trade 없이 보증금·월세 조건을 막지만, 이 설명은 라이브러리로 직접 부를 때의
    # 동작이다 (complex.py 의 조건 만들기와 맞다)
    trade_type: Annotated[
        str | None,
        Field(description='가격 조건과 단지마다 붙는 최근 실거래의 거래 유형 (매매·전세·월세). 없으면 매매로 보여 주고, 필터로는 가격 조건(보증금·월세·매매가 중 하나)이 있을 때만 기본 매매를 보낸다')
    ] = None
    deposit_min: Annotated[
        int | None,
        Field(description='보증금·전세금 하한 (만원, 과거 실거래 기준)')
    ] = None
    deposit_max: Annotated[
        int | None,
        Field(description='보증금·전세금 상한 (만원, 과거 실거래 기준)')
    ] = None
    rent_min: Annotated[
        int | None,
        Field(description='월세 하한 (만원, 과거 실거래 기준)')
    ] = None
    rent_max: Annotated[
        int | None,
        Field(description='월세 상한 (만원, 과거 실거래 기준)')
    ] = None
    price_min: Annotated[
        int | None,
        Field(description='매매가 하한 (만원, 과거 실거래 기준)')
    ] = None
    price_max: Annotated[
        int | None,
        Field(description='매매가 상한 (만원, 과거 실거래 기준)')
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
    """지역 단지 목록 조건을 웹 단지 탭 필터로 바꾼다.

    `propertyFilter.tradeType` 은 웹이 거래 유형 칩을 골랐을 때만 보낸다 (complexFilter 의 `p`: `tradeType: r.length>0 ? r : void 0`,
    기본 필터는 `tradeTypes: []`). jibsa 는 `--trade` 를 줬거나 가격 조건이 있을 때만 넣고, 보여 줄 실거래의 거래 유형은 최상위
    `tradeType`(기본 BUY)으로만 보낸다 (2026-11-12 번들 대조. 예전에는 기본 매매를 늘 필터에도 넣었다).
    """
    has_price = any(
        value is not None for value in (
            conditions.deposit_min, conditions.deposit_max, conditions.rent_min, conditions.rent_max,
            conditions.price_min, conditions.price_max,
        )
    )
    return DaangnComplexFilterModel(
        type=label_codes(conditions.complex_types, COMPLEX_TYPE_FILTER_BY_LABEL),
        trade_type=(
            [COMPLEX_TRADE_BY_TRADE_TYPE[conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE]]
            if conditions.trade_type is not None or has_price else None
        ),
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


def has_complex_conditions(conditions: DaangnComplexConditions) -> bool:
    """사용자가 단지 조건을 하나라도 줬는지 (기본값 모델과 견준다). 에러 hint 가 조건을 줄이라고 권할지 정한다."""
    return conditions != DaangnComplexConditions()


def list_region_complexes(
    client: DaangnClient,
    query: str,
    *,
    conditions: DaangnComplexConditions | None = None,
    sort: str = '세대수',
    limit: int = 120,
) -> DaangnRegionComplexesResult:
    """동·구의 단지 목록을 정렬해 받는다 (웹 지도 단지 탭에서 지역 거품을 누른 목록, `complexByClusterId`).

    웹처럼 `REGION:<동·구 ID>` 클러스터로 부른다. 예전에는 동·구 ID 를 지도 범위 쿼리(`searchComplexes`)에 넣었는데 웹은 그렇게
    부르지 않는다. 결과는 같았다 (2026-11-12 실측: 역삼동 첫 50곳이 순서·커서까지 같음, #215). 단지마다 최근 실거래는 웹
    카드(1건)보다 많은 3건이다 (jibsa 개선, 2026-11-12 사용자 결정).

    지역은 `resolve_realsale_region` 으로 고른다 (동 또는 구). 조건은 웹 단지 탭 필터와 같고 당근
    서버에서 건다. 가격 조건은 지금 매물 가격이 아니라 단지의 과거 실거래 가격으로 거른다 (2026-10 역삼동
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
    trade_type = conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE
    region, notes = resolve_realsale_region(client, query)
    complex_filter = complex_filter_of(conditions)
    filtered = has_complex_conditions(conditions)
    exclusive_use_area = _exclusive_use_area(conditions)

    def fetch(first: int, after: str | None) -> DaangnRegionComplexesModel:
        response = client.run_request_complex_by_cluster_id(
            DaangnComplexByClusterIdRequestPayloadModel(
                first=first,
                after=after,
                input=DaangnComplexByClusterIdInputModel(
                    cluster_id=f'REGION:{region.region_id}',
                    property_filter=complex_filter,
                    sort=COMPLEX_SORT_BY_LABEL[sort],
                ),
                trade_type=COMPLEX_TRADE_BY_TRADE_TYPE[trade_type],
                exclusive_use_area=exclusive_use_area,
            )
        )
        return unwrap_graphql(response, response.data.complex_by_cluster_id if response.data else None, '지역 단지 목록', conditions=filtered)

    complexes, has_more = _collect_complexes(fetch, trade_type, limit, sort, notes, narrow='지역·단지 유형·세대수·가격 조건')
    return DaangnRegionComplexesResult(
        region=region,
        trade_type=trade_type,
        sort=sort,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )


def _exclusive_use_area(conditions: DaangnComplexConditions) -> DaangnExclusiveUseAreaModel | None:
    """면적 조건을 단지마다 보여 줄 최근 실거래의 전용면적 범위로. 조건이 없으면 None (전체)."""
    if conditions.area_min is None and conditions.area_max is None:
        return None
    return DaangnExclusiveUseAreaModel(
        min=conditions.area_min or 0,
        **({'max': conditions.area_max} if conditions.area_max is not None else {}),
    )


def _collect_complexes(
    fetch: Callable[[int, str | None], DaangnRegionComplexesModel],
    trade_type: str,
    limit: int,
    sort: str,
    notes: list[str],
    *,
    narrow: str,
) -> tuple[list[DaangnRegionComplex], bool]:
    """단지 목록을 50곳씩 `limit` 곳까지 커서로 이어 받는다. 동·구 클러스터 목록과 지도 범위 목록이 함께 쓴다.

    받은 수로 예산을 세고 같은 단지는 한 번만 넣는다. 커서가 멈추면(`stalled_page`·`next_cursor`) 받은 것만 주고 알린다.

    Args:
        fetch: (받을 수, 커서) → 한 쪽.
        trade_type: 단지마다 붙는 최근 실거래의 거래 유형.
        limit: 최대 단지 수.
        sort: 정렬 라벨 (입주일 순이면 안내를 붙인다).
        notes: 안내를 덧붙일 목록.
        narrow: 더 남았을 때 좁히라고 권할 조건 (`more_hint`).

    Returns:
        (단지, 더 있는지).
    """
    complexes: list[DaangnRegionComplex] = []
    seen: set[str] = set()
    # 단지별로 못 읽은 날짜를 맡아 뒀다가 자른 뒤 남은 단지의 것만 안내에 센다
    held: dict[str, list[tuple[str, str]]] = {}
    after: str | None = None
    inspected = 0
    # 서버는 빈 edge(null)도 한 자리로 세므로 빼고 읽은 수를 받은 자리에 더한다
    null_edges = 0
    # 당근이 단지 ID 를 주지 않아 뺀 단지 수. 받은 수(inspected)에는 세어 예산은 그대로다
    no_id_count = 0
    has_more = False
    stopped = False
    while inspected < limit:
        connection = fetch(min(COMPLEX_PAGE_SIZE, limit - inspected), after)
        if stalled_page(connection.page_info, after):
            stopped = True
            break
        null_edges += connection.null_items('edges')
        inspected += len(connection.edges) + connection.null_items('edges')
        nodes = [edge.node for edge in connection.edges if edge.node]
        for node in nodes:
            if node.original_id is None:
                no_id_count += 1
                continue
            with holding_unread_dates() as dates:
                complex_ = region_complex_of(node, trade_type)
            if complex_.complex_id not in seen:
                seen.add(complex_.complex_id)
                complexes.append(complex_)
                held[complex_.complex_id] = dates
        page_info = connection.page_info
        has_more = bool(page_info and page_info.has_next_page)
        if inspected >= limit or not has_more:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 에 닿은 것이 아니라
        # --limit 을 늘려도 더 받지 못하니, 아래의 --limit 안내 대신 멈췄다고 알린다
        cursor = next_cursor(page_info, after, received=len(nodes))
        if cursor is None:
            stopped = True
            break
        after = cursor
    # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
    has_more = has_more or len(complexes) > limit
    complexes = complexes[:limit]
    for complex_ in complexes:
        keep_unread_dates(held[complex_.complex_id])
    if stopped:
        notes.append(note('일부', cursor_stopped_note('단지 목록', f'{len(complexes)}곳') + '. 지원되는 필터로 범위를 좁히세요'))
    elif has_more:
        # 멈추지 않고 더 남았으면 --limit 에 닿은 것이다 (루프는 inspected >= limit 일 때만 has_more 를 남기고 끝난다).
        # 같은 단지가 두 번 오면 한 번만 넣어 limit 보다 적을 수 있어, 숫자는 보여 준 수로 쓴다
        notes.append(note('일부', f'단지가 더 있어 앞 {len(complexes)}곳만 보여 줍니다. ' + more_hint(limit, COMPLEX_LIST_MAX_LIMIT, narrow)))
    if no_id_count:
        notes.append(note('제외', f'당근이 단지 ID 를 주지 않은 {no_id_count}곳은 뺐습니다'))
    if null_edges:
        notes.append(null_items_note('당근 지역 단지', null_edges))
    if sort.startswith('입주'):
        notes.append(MOVE_IN_SORT_NOTE)
    notes += complex_list_notes(complexes)
    return complexes, has_more


class DaangnBoundsComplexesResult(Result):
    """지도 화면 범위의 단지 목록 (웹 지도 단지 탭의 '이 영역 단지').

    `notes`: 범위·정렬·후기 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[
        DaangnRegion | None,
        Field(description='화면 가운데가 속한 동. 모르면 null')
    ] = None
    zoom: Annotated[
        int,
        Field(description='웹 지도 줌. 범위는 데스크톱 지도 화면(1440×900 창에서 목록 패널을 뺀 영역) 기준이다')
    ]
    width_km: Annotated[
        float,
        Field(description='화면 범위의 가로 (km)')
    ]
    height_km: Annotated[
        float,
        Field(description='화면 범위의 세로 (km)')
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


def list_bounds_complexes(
    client: DaangnClient,
    lat: float,
    lng: float,
    *,
    zoom: int = POINT_ZOOM,
    conditions: DaangnComplexConditions | None = None,
    sort: str = '세대수',
    limit: int = 120,
) -> DaangnBoundsComplexesResult:
    """(`lat`, `lng`) 를 가운데에 둔 웹 지도 화면 범위의 단지 목록 (웹 지도 단지 탭의 '이 영역 단지', `searchComplexes`).

    웹은 지도 화면의 북동·남서 꼭짓점을 `input.locationFilter` 로 보내고 조건·정렬·거래 유형은 동·구 클러스터 목록과 같다
    (ComplexListPanel `Z`, 2026-11-12 번들 대조). 범위는 지도 범위 매물 목록과 같은 데스크톱 화면 계산(`map_view_bounds`)이고
    줌 기본도 좌표 매물 검색과 같은 15 다. 화면 가운데의 동(`region`)은 결과 표시용 덤 조회라 실패해도 단지는 돌려준다.

    Raises:
        FeedQueryRejectedError: 웹이 단지 목록 쿼리를 바꿨을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    conditions = conditions or DaangnComplexConditions()
    trade_type = conditions.trade_type or DEFAULT_COMPLEX_TRADE_TYPE
    complex_filter = complex_filter_of(conditions)
    filtered = has_complex_conditions(conditions)
    exclusive_use_area = _exclusive_use_area(conditions)
    bounds, width_km, height_km = map_view_bounds(lat, lng, zoom)
    notes: list[str] = []

    def fetch(first: int, after: str | None) -> DaangnRegionComplexesModel:
        response = client.run_request_search_complexes_viewport(
            DaangnSearchComplexesViewportRequestPayloadModel(
                first=first,
                after=after,
                input=DaangnSearchComplexesViewportInputModel(
                    location_filter=bounds,
                    property_filter=complex_filter,
                    sort=COMPLEX_SORT_BY_LABEL[sort],
                ),
                trade_type=COMPLEX_TRADE_BY_TRADE_TYPE[trade_type],
                exclusive_use_area=exclusive_use_area,
            )
        )
        return unwrap_graphql(response, response.data.search_complexes if response.data else None, '지도 범위 단지 목록', conditions=filtered)

    complexes, has_more = _collect_complexes(fetch, trade_type, limit, sort, notes, narrow='범위(--zoom)·단지 유형·세대수·가격 조건')
    # 동 이름은 결과 표시에만 쓰여 못 찾아도 단지는 보여 준다. 본 조회 뒤에 묻는다 (덤 조회가 첫 요청이 되면 첫 화면 실패를 삼킨다).
    # 단지가 없어도 찾는다. null 은 '모름' 이라 찾지 않고 null 을 주면 당근이 위치를 못 찾은 것으로 읽힌다 (2026-11-12 리뷰·실측:
    # 역삼동 좌표 세대수 99999 이상 0곳에 region null. 매물 지도 검색과 같다)
    region = region_or_none(client, lat, lng, notes=notes)
    return DaangnBoundsComplexesResult(
        region=region,
        zoom=zoom,
        width_km=width_km,
        height_km=height_km,
        trade_type=trade_type,
        sort=sort,
        returned=len(complexes),
        has_more=has_more,
        complexes=complexes,
        notes=notes,
    )


class DaangnComplexListingsResult(Result):
    """단지 하나의 매물 목록.

    `notes`: 일부만 보여 준다·더 받지 못하고 멈췄다는 안내, 거래를 몰라 뺀 매물·빈 항목을 뺐다는 안내, 원룸·투룸으로 올린 단지 매물 안내
    """

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
    filtered = not is_empty_property_filter(property_filter)  # 사용자 조건 없음 (아래에서 기본 종류를 채우기 전 값)
    if not conditions.property_types:
        # 웹 단지 매물 패널은 종류를 고르지 않으면 늘 주거 5종(아파트·주택·오피스텔·원룸·투룸)을 보낸다 (`ComplexArticleListPanel`
        # 의 `F`, 단지 페이지 SEO 본문도 같다). 빈 목록(전체)으로 부르는 경로가 없어 상가·사무실 등은 -t 로 골랐을 때만 온다
        # (2026-11-12 번들 대조. 예전에는 전체를 보내 상가 매물이 섞였다)
        property_filter = property_filter.model_copy(update={'sales_types': list(COMPLEX_LISTING_DEFAULT_SALES_TYPES)})
    matched: list[tuple[DaangnArticleModel, DaangnTradeModel]] = []
    after = None
    inspected = 0
    seen: set[str] = set()
    # 받은 서로 다른 매물 (거래 불가도 센다). 멈춤 안내의 수다. inspected 는 edge 누계라 같은 쪽이 되풀이되면 두 번 센다
    # (2026-11-10 리뷰. 출퇴근 역 목록도 이름으로 센다)
    received_ids: set[str] = set()
    received: list[DaangnArticleModel] = []
    # 서버는 빈 edge(null)도 한 자리로 세므로 빼고 읽은 수를 받은 자리에 더한다
    null_edges = 0
    has_more = False
    stopped = False
    page_capped = False
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
            response, response.data.complex_by_original_id if response.data else None, '단지 매물', conditions=filtered
        )
        if result.complex is None:
            raise complex_not_found(complex_id)
        connection = result.complex.articles
        # 단지의 매물 목록(articles) 자체가 null 이어도 페이지 정보가 없는 것이라 앞 쪽이 다음이 있다고 했으면 멈춘다 (stalled_page)
        if stalled_page(connection.page_info if connection else None, after):
            stopped = True
            break
        if connection:
            null_edges += connection.null_items('edges')
            inspected += len(connection.edges) + connection.null_items('edges')
        articles = [edge.node for edge in connection.edges if edge.node] if connection else []
        received_ids.update(article.original_id for article in articles)
        received += articles
        for article in articles:
            if article.original_id in seen or not is_available(article):
                continue
            seen.add(article.original_id)
            trade = trade_of(article, conditions)
            if trade is not None:
                matched.append((article, trade))
        page_info = connection.page_info if connection else None
        # 서버가 first 보다 많이 주면 자른 만큼을 '더 있음' 으로 센다 (COMPLEX_PAGE_SIZE 주석)
        has_more = bool(page_info and page_info.has_next_page) or len(matched) > limit
        if inspected >= limit or not has_more or page_info is None:
            break
        # 다음 페이지가 있다면서 빈 쪽을 주거나 커서가 없거나 되풀이되면 멈춘다 (next_cursor). --limit 을 늘려도 더 받지 못하니
        # 아래의 --limit 안내 대신 멈췄다고 알린다 (2026-11-10 리뷰: 같은 커서를 되풀이하면 같은 쪽을 6번 받고 '--limit 의
        # 최대값은 120입니다' 라고 했고, 커서가 비면 안내 없이 has_more 만 true 였다). 마지막 허용 쪽(6쪽)에서도 본다. 다음이
        # 있다면서 커서를 주지 않는 것은 몇 쪽째든 응답이 바뀐 것이라 멈춤 안내(업데이트 문구)가 맞다. 서버가 쪽마다 first 만큼
        # 주면(COMPLEX_PAGE_SIZE 주석) 6쪽째에 inspected 가 --limit 최대 120 에 닿아 위에서 먼저 끝난다. 하지만 서버가 first 보다 적게
        # 주면 쪽 상한(for 가 break 없이 끝남)에 먼저 닿아 inspected < limit 이고 has_more 인 채 끝나, 아래 '더 있음' 안내의
        # 조건(limit >= max_limit 또는 inspected >= limit)이 거짓이라 안내 없이 has_more 만 true 였다. 그래서 쪽 상한은
        # `stopped` 와 같은 갈래로 보아 따로 알린다 (`page_capped`. 2026-11-10 리뷰의 6쪽째 멈춤 지적은 first 만큼 줄 때만 오탐이었다)
        cursor = next_cursor(page_info, after, received=len(articles))
        if cursor is None:
            stopped = True
            break
        after = cursor
    else:
        # break 없이 끝났으면 쪽 상한에 닿은 것이다. 닿기 전 끝 조건(--limit 만큼 받음·다음 없음·pageInfo 없음)은 모두 break 다
        page_capped = True

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
        notes=listing_budget_notes(
            limit, inspected, len(listings), max_limit=LISTING_MAX_LIMIT, has_more=has_more, narrow='조건',
            eligible=len(matched), narrowable=not (stopped or page_capped), dropped=null_edges,
        )
            + no_trade_notes(received)
            + (
                [note('일부', cursor_stopped_note('단지 매물', f'{len(received_ids)}건') + '. 나머지는 url 의 단지 페이지에서 확인하세요')]
                if stopped else []
            )
            + (
                [note(
                    '일부',
                    f'단지 매물 {len(received_ids)}건을 받고 쪽 수 상한({COMPLEX_LISTINGS_MAX_PAGES}쪽)에 닿아 멈췄습니다. '
                    '--limit 을 늘려도 더 받지 못합니다. 나머지는 url 의 단지 페이지에서 확인하세요',
                )]
                if page_capped else []
            )
            + complex_building_notes(shown)
            + ([null_items_note('당근 단지 매물', null_edges)] if null_edges else []),
    )


APPROVAL_DATE_PATTERN: re.Pattern[str] = re.compile(r'(\d{4})\.(\d{2})\.(\d{2})')


class DaangnTrendingComplex(BaseModel):
    """인기 급상승 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    rank: Annotated[int | None, Field(description='순위. 당근이 빈 항목을 줘 셀 수 없으면 null')]
    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='시·도·구')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    representative_area_m2: Annotated[
        float | None,
        Field(description='대표 평형 전용면적 (㎡). 당근이 빈 항목을 줘 셀 수 없으면 null')
    ] = None
    latest_trades: Annotated[
        dict[str, AmountSet | None],
        Field(description="대표 평형의 가장 최근 실거래. 거래 키('sale')이고 그 안 price_manwon 은 최근 매매가 (만원). 최근 매매가 없거나 매매가가 0 이면(당근 웹도 비운다) 키가 없고({}), 대표 평형을 모르거나(당근이 빈 항목을 줘 셀 수 없을 때 포함) 당근이 실거래 칸이나 그 목록을 주지 않거나 목록에 빈 항목이 섞이거나 매매가를 모르면 'sale' 이 null")
    ]


class DaangnTrendingRegion(BaseModel):
    """인기 급상승 단지를 본 범위."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sido: Annotated[
        str,
        Field(description='시/도. 전국이면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    sigungu: Annotated[
        str,
        Field(description='시/군/구. 시·도 범위면 빈 문자열이고 출력에서 키를 뺀다')
    ] = ''
    region_id: Annotated[
        int | None,
        Field(description='당근 지역 ID. 전국이면 null')
    ] = None
    level: Annotated[
        Literal['전국', '시도', '구'],
        Field(description='전국·시도·구(시·군 포함)')
    ]

    @model_serializer
    def with_name(self) -> dict[str, Any]:
        if self.level == '전국':
            return {'name': '전국', 'region_id': self.region_id, 'level': self.level}
        return {**region_name_parts(self.sido, self.sigungu), 'region_id': self.region_id, 'level': self.level}


class DaangnTrendingComplexesResult(Result):
    """인기 급상승 단지 목록.

    `notes`: 빈 결과 안내. CLI 가 결과 위에 붙인다
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    region: Annotated[DaangnTrendingRegion, Field(description='본 범위')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    complexes: Annotated[list[DaangnTrendingComplex], Field(description='어제 대비 오늘 조회가 급상승한 순 단지')]


def trending_region_of(area: DaangnArea | None) -> DaangnTrendingRegion:
    """인기 급상승 단지의 범위. 지역이 없으면 전국이다.

    Raises:
        JibsaError: 동이면 INVALID_ARGUMENT. 당근 웹은 전국·시·도 탭과 시·군·구 페이지로만 부른다 (2026-11-12 번들 대조).
    """
    if area is None:
        return DaangnTrendingRegion(level='전국')
    if area.level == '동':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"인기 급상승 단지는 전국·시·도·구 단위만 있습니다 ({quoted(area.full_name, '은/는')} 동입니다)",
            hint=f"구로 찾으려면 jibsa daangn trending-complexes '{join_address(area.name1, area.name2)}'. 지역을 빼면 전국입니다",
        )
    return DaangnTrendingRegion(
        sido=area.name1,
        sigungu=area.name2 if area.level == '구' else '',
        region_id=area.region_id,
        level='시도' if area.level == '시도' else '구',
    )


def list_trending_complexes(client: DaangnClient, region: DaangnTrendingRegion) -> DaangnTrendingComplexesResult:
    """어제 대비 오늘 조회가 급상승한 단지 (`trendingComplexes`, 요청 1회). 웹의 인기 급상승 단지 패널처럼 50곳까지다.

    대표 평형은 웹(MapShell `zu`)처럼 대표 전용면적 묶음(없으면 첫 묶음)에서 세대수가 가장 많은 평형이다. 예전에는 묶음의 첫
    평형을 써서 전국 50곳 중 10곳이 웹과 달랐다 (2026-11-12 실측). 같으면 앞 평형이다.

    Raises:
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
        JibsaError: 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
    """
    response = client.run_request_trending_complexes(
        DaangnTrendingComplexesRequestPayloadModel(region_id='ALL' if region.region_id is None else str(region.region_id))
    )
    found = unwrap_graphql(response, response.data.trending_complexes if response.data else None, '인기 단지', conditions=False)
    # 목록에서 빈 항목을 빼고 읽었으면 순위를 매길 자리를 알 수 없어 순위는 모두 모른다 (null)
    dropped_complexes = response.data.null_items('trending_complexes') if response.data else 0
    dropped_pyeongs = 0
    dropped_trades = 0
    complexes: list[DaangnTrendingComplex] = []
    for rank, item in enumerate(found, start=1):
        danji = item.proptier_danji
        groups = danji.exclusive_area_groups if danji else []
        # 대표 묶음은 평형이 없는 묶음까지 포함한 묶음 전체에서 고른다 (웹 MapShell `zu`). 단지 비교(`_select_pyeong`)는 웹 식이
        # 달라 평형이 있는 묶음 중에서 고른다 (합치지 않는다)
        group = next((group for group in groups if group.is_representative), groups[0] if groups else None)
        info = most_households(group.py_infos if group else [], lambda py: py.households)
        # 대표 묶음·대표 평형을 고르는 목록에서 빈 항목을 빼고 읽었으면 고른 평형이 웹의 대표 평형이 아닐 수 있어 모른다 (null)
        dropped = (danji.null_items('exclusive_area_groups') if danji else 0) + (group.null_items('py_infos') if group else 0)
        if dropped:
            info = None
            dropped_pyeongs += dropped
        latest_trades: dict[str, AmountSet | None]
        realsale = info.sale_realsale if info else None
        # 실거래 칸이나 그 목록(edges)이 null 이거나 목록에 빈 항목(null 원소, node 가 null 인 항목)이 있으면 최근 매매가 있는지 모른다
        # (null). 빈 목록 [] 만 해당 없음이다
        blank_trades = (
            realsale.null_items('edges') + sum(1 for edge in realsale.edges or [] if edge.node is None) if realsale else 0
        )
        if realsale is None or realsale.edges is None or blank_trades:
            latest_trades = {'sale': None}
            dropped_trades += blank_trades
        else:
            # 최근 매매가 없거나(노드가 없음) 매매가가 0 이면 해당 없음이라 키를 뺀다 (웹 카드 `zu` 의 `price:o?…:null` 도 0 이면 비운다)
            node = realsale.edges[0].node if realsale.edges else None
            if node is None or node.trade_price == 0:
                latest_trades = {}
            else:
                latest_trades = {'sale': None if node.trade_price is None else AmountSet(price_manwon=node.trade_price)}
        approval = APPROVAL_DATE_PATTERN.search(item.approval_date_text or '')
        # 응답 설명이 '사용승인일 2022.04.28(4년차)' 꼴인데 날짜가 없는 단지가 어떤 글자를 주는지 확인되지 않았다.
        # 그래서 매치되지 않는 글자는 값 없음으로 보고, 매치됐는데 없는 날이면 못 읽은 날짜로 알린다
        approved_date = (
            read_date('-'.join(approval.groups()), '사용승인일', raw=item.approval_date_text) if approval else None
        )
        complexes.append(DaangnTrendingComplex(
            rank=None if dropped_complexes else rank,
            complex_id=item.original_id,
            name=item.name,
            complex_type=code_label(COMPLEX_TYPE_LABELS, item.type),
            address=normalize_address(join_address(item.region.name1, item.region.name2)) if item.region else None,
            household_count=item.households,
            approved_date=approved_date,
            representative_area_m2=info.exclusive_area if info else None,
            latest_trades=latest_trades,
        ))
    # 동으로 부를 때는 이른 아침마다 비었다 (2026-10-27 실측). 웹 범위(전국·시·도·구)에서도 비면 단지가 없다는 뜻으로 읽히지 않게 알린다
    region_name = ' '.join(part for part in (region.sido, region.sigungu) if part) or '전국'
    notes = [] if complexes else [
        f'당근이 {region_name} 인기 급상승 단지를 주지 않았습니다. 단지가 없다는 뜻은 아닙니다. 때에 따라 달라 나중에 다시 부르면 '
        '나올 수 있고, 지역 단지 목록은 jibsa daangn search complexes <동·구> 에서 봅니다'
    ]
    if dropped_complexes:
        notes.append(null_items_note('당근 인기 급상승 단지', dropped_complexes, ('rank',)))
    if dropped_pyeongs:
        notes.append(null_items_note('당근 인기 단지 평형', dropped_pyeongs, ('representative_area_m2', 'latest_trades 의 sale')))
    if dropped_trades:
        notes.append(null_items_note('당근 인기 단지 최근 매매', dropped_trades, ('latest_trades 의 sale',)))
    return DaangnTrendingComplexesResult(region=region, returned=len(complexes), complexes=complexes, notes=notes)
