"""분양 (search sales · sale · sale-schedule)."""
import re
from datetime import (
    date,
    timedelta,
)

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import JibsaError
from jibsa.core.geo import (
    DEFAULT_RADIUS_KM,
    box_around,
)
from jibsa.core.listing import (
    UPDATE_MAYBE_NEEDED,
    more_hint,
    normalize_address,
    note,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.request.sale import (
    ALL_SALE_BUILDING_TYPES,
    ALL_SALE_STATES,
    ALL_SALE_SUPPLY_TYPES,
    SALE_BUILDING_TYPE_NUMBERS,
    SALE_SEARCH_PAGE_SIZE,
    SALE_STATE_NUMBERS,
    SALE_SUPPLY_TYPE_NUMBERS,
    DabangSaleBuildingType,
    DabangSaleInLotsDetail2V3RequestParameterModel,
    DabangSaleInLotsFiltersModel,
    DabangSaleInLotsListScheduleSearchV3RequestParameterModel,
    DabangSaleInLotsListScheduleV3RequestParameterModel,
    DabangSaleInLotsListSearch3V3RequestParameterModel,
    DabangSaleInLotsSearchFiltersModel,
    DabangSaleListCategoryBboxV5RequestParameterModel,
    DabangSaleState,
    DabangSaleSupplyType,
)
from jibsa.providers.dabang.api.response.sale import (
    DabangSaleInLotsItemModel,
    DabangSaleInLotsRowModel,
    DabangSaleItemModel,
    DabangSaleScheduleTableRowModel,
)
from jibsa.providers.dabang.service.common import (
    MAX_LIST_LIMIT,
    DabangPage,
    DabangPages,
    DabangPlace,
    bbox_of,
    count_of,
    fetch_pages,
    household_count,
    is_missing_id,
    manwon_from_text,
    more_list_notes,
    number_of,
    sale_url,
)
from jibsa.providers.dabang.service.region import (
    DabangScope,
    dong_bbox,
    state_name,
)

from typing import (
    Annotated,
    Any,
)


SALE_BUILDING_TYPE_BY_LABEL: dict[str, DabangSaleBuildingType] = {
    '아파트': 'APT',
    '오피스텔': 'OFFICETEL',
    '도시형생활주택': 'URBAN_HOUSE',
    '지식산업센터': 'KNOWLEDGE_INDUSTRY_CENTER',
}
SALE_STATE_BY_LABEL: dict[str, DabangSaleState] = {
    '분양예정': 'EXPECTED',
    '접수중': 'ACCEPTING',
    '접수마감': 'ACCEPT_COMPLETE',
    '입주예정': 'MOVE_IN_EXPECTED',
    '입주모집': 'MOVE_IN_RECRUIT',
}
SALE_SUPPLY_BY_LABEL: dict[str, DabangSaleSupplyType] = {
    '공공분양': 'PUBLIC_SALE',
    '민간분양': 'PRIVATE_SALE',
    '공공임대': 'PUBLIC_RENTAL',
    '민간임대': 'PRIVATE_RENTAL',
}
# 분양 일정 날짜 꼴: '26.09.07' (날), '26.08월' (달)
SALE_DAY_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})\.(\d{1,2})$')
SALE_MONTH_PATTERN: re.Pattern[str] = re.compile(r'^(\d{2})\.(\d{1,2})월$')
# sale-schedule 의 --limit 최대값. CLI 옵션의 max 와 더 보는 법 안내가 함께 쓴다
SALE_SCHEDULE_MAX_LIMIT: int = 300
# 청약 일정 글: '[청약접수] 인천 인천계양 A17블록 … (~10/27)'
SCHEDULE_REGION_PATTERN: re.Pattern[str] = re.compile(r'^(?:\[[^\]]+\]\s*)+(\S+)')
# 웹은 공급 유형 코드가 4·5(공공임대·민간임대)면 가격 이름표를 '임대가', 아니면 '분양가' 로 쓴다 (ic_24_download 청크 `x`,
# 2026-11-13. 민간임대 6acca80f… 화면 '임대가 4억7770')
RENTAL_SUPPLY_TYPES: frozenset[int] = frozenset({4, 5})


def sale_date(text: str | None) -> str | None:
    """다방 분양 날짜 글을 'YYYY-MM-DD' 나 'YYYY-MM' 으로 ('26.09.07' → '2026-09-07', '26.08월' → '2026-08'). 다른 꼴은 그대로."""
    if text is None or not text.strip():
        return None
    value = text.strip()
    if (match := SALE_DAY_PATTERN.fullmatch(value)) is not None:
        return f'20{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
    if (match := SALE_MONTH_PATTERN.fullmatch(value)) is not None:
        return f'20{match.group(1)}-{int(match.group(2)):02d}'
    return value


class DabangSaleSummary(BaseModel):
    """분양 단지 하나 (목록)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale_id: Annotated[
        str,
        Field(description='분양 ID. jibsa dabang sale 에 넘긴다')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    state: Annotated[
        str | None,
        Field(description='분양 상태 (분양예정·접수중·접수마감·입주예정·입주모집)')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형 (공공분양·민간분양·공공임대·민간임대)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    sale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수 (다방 목록의 세대수 칸. 총세대수가 아니다, 총세대수는 household_count)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총세대수. 시·도·시군구·전국 범위(다방 지역 목록)만 다방이 주고 동·역·대학·좌표 범위(지도 목록)는 null')
    ] = None
    price_kind: Annotated[
        str | None,
        Field(description="가격 종류 (다방 표시. 보통 '분양가', 임대 공급이면 지역 목록은 '임대가', 지도 목록은 '보증금')")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='대표 가격 (만원, 다방 표시). 아직 없으면 null')
    ] = None
    next_schedule: Annotated[
        str | None,
        Field(description="다음 일정 ('26.12.07 ~ 26.12.10 계약기간')")
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]


class DabangSaleListResult(BaseModel):
    """분양 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    scope: Annotated[
        str,
        Field(description='찾은 범위')
    ]
    total: Annotated[
        int | None,
        Field(description=(
            "다방이 센 분양 단지 수. 전국·시·도·시군구는 다방 분양 지역 목록의 '총 N건', 동·역·대학·좌표는 지도 범위(사각형) 안 "
            '수 (동은 주소로 거르기 전)'
        ))
    ] = None
    returned: Annotated[
        int,
        Field(description='반환한 단지 수')
    ]
    has_more: Annotated[
        bool,
        Field(description='더 받을 단지가 있는지')
    ] = False
    sales: Annotated[
        list[DabangSaleSummary],
        Field(description='다방 목록 순 분양 단지')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='범위·제외 안내')
    ] = []


def _summary(item: DabangSaleItemModel) -> DabangSaleSummary:
    """지도 목록(`sale-list/category/bbox`)의 한 줄. 총세대수가 오지 않는다."""
    return DabangSaleSummary(
        sale_id=item.id,
        name=item.building_name,
        state=item.state_name,
        building_type=item.building_type_title,
        supply_type=item.supply_type_name,
        address=normalize_address(item.address),
        sale_household_count=household_count(item.household_num_title),
        price_kind=item.supply_price_type_name,
        price_manwon=manwon_from_text(item.price_title),
        next_schedule=item.schedule_title,
        url=sale_url(item.id),
    )


def _in_lots_fields(item: DabangSaleInLotsRowModel) -> dict[str, Any]:
    """분양 지역 목록(`list/search3`)·청약 일정 표(`list/schedule/search`) 한 줄의 상태·유형·주소·세대수·가격 칸.

    두 목록은 같은 줄 꼴이라 `DabangSaleSummary`·`DabangSaleScheduleSale` 가 같이 쓴다. 웹 목록의 세대수 칸은 분양
    세대수(`lots_household_num`)다. 응답 줄은 공통 칸을 부모(`DabangSaleInLotsRowModel`)로 올렸지만 출력 모델 두 개의 필드
    선언은 올리지 않는다 (pydantic 은 부모 필드를 앞에 둬 search sales 의 키 순서가 sale_id·name 보다 앞으로 바뀐다).
    """
    return {
        'state': item.state_title,
        'building_type': item.building_types_title,
        'supply_type': item.supply_type_title,
        'address': normalize_address(item.address),
        'sale_household_count': item.lots_household_num,
        'household_count': item.total_household_num,
        'price_kind': item.price_supply_type_str,
        'price_manwon': manwon_from_text(item.price_str),
    }


def _region_summary(item: DabangSaleInLotsItemModel) -> DabangSaleSummary:
    """지역 목록(`list/search3`)의 한 줄."""
    return DabangSaleSummary(
        sale_id=item.id,
        name=item.building_name,
        **_in_lots_fields(item),
        next_schedule=item.title,
        url=sale_url(item.id),
    )


def _search_filters(
    building_types: list[str] | None, states: list[str] | None, supply_types: list[str] | None,
) -> DabangSaleInLotsSearchFiltersModel:
    """지역 목록 필터. 고르지 않은 항목은 웹 초기값처럼 빈 목록(전체)으로 보낸다."""
    return DabangSaleInLotsSearchFiltersModel(
        building_type=[SALE_BUILDING_TYPE_NUMBERS[SALE_BUILDING_TYPE_BY_LABEL[label]] for label in building_types or []],
        state=[SALE_STATE_NUMBERS[SALE_STATE_BY_LABEL[label]] for label in states or []],
        supply_type=[SALE_SUPPLY_TYPE_NUMBERS[SALE_SUPPLY_BY_LABEL[label]] for label in supply_types or []],
    )


def _sale_list_notes(pages: DabangPages[Any], limit: int, *, in_box: bool, narrow_end: str) -> list[str]:
    """분양 목록(지도·지역)의 [일부] 안내.

    Args:
        in_box: 지도 목록(범위 사각형)이면 True. 다방이 센 수가 사각형 안 수라 '약' 을 붙인다.
        narrow_end: 좁히라고 권할 범위 ('반경' 또는 '지역').
    """
    total, received = pages.total, len(pages.rows)
    narrow = f'건물 유형·분양 상태·공급 유형 조건·{narrow_end}'
    among = f" {'약 ' if in_box else ''}{total}곳 중" if total is not None else ''
    # --limit 이 이미 최대값이면 늘리라고 하지 않고 좁힐 조건을 권한다 (2026-11-10 리뷰: --limit 120 에도 '--limit 을 늘리세요' 뿐)
    seen = f'범위 사각형 안 분양 단지{among} 다방 목록 순 앞 {received}곳을 봤습니다' if in_box else (
        f'분양 단지{among} 다방 목록 순 앞 {received}곳입니다'
    )
    return more_list_notes(pages, limit, seen=seen, max_limit=MAX_LIST_LIMIT, narrow=narrow)


def search_sales(
    client: DabangClient,
    *,
    place: DabangPlace | None = None,
    scope: DabangScope | None = None,
    dong: DabangPlace | None = None,
    radius_km: float | None = None,
    building_types: list[str] | None = None,
    states: list[str] | None = None,
    supply_types: list[str] | None = None,
    limit: int,
) -> DabangSaleListResult:
    """분양 단지 (다방 목록 순, 24곳씩).

    전국·시·도·시·군·구(`scope`)는 웹 분양 지역 목록(`list/search3`)과 같은 주소로 받아 목록·순서·`total` 이 웹과 같다.
    동·역·대학·좌표는 지도 목록(`sale-list/category/bbox`)이다. 웹도 그 범위는 지도에서 본다. 지도 목록은 범위(사각형)만
    받아, 동은 경계를 덮는 사각형으로 받고 주소가 그 동인 단지만 남긴다 (분양 칸에는 좌표·동 번호가 없어 주소로 본다).
    역·대학·좌표는 반경을 덮는 사각형이다 (좌표가 없어 반경 밖을 뺄 수 없다). 추천 칸(지도 목록 `recommendList`, 지역 목록
    `features`)은 웹 목록에 없어 넣지 않는다.

    Args:
        place: 역·대학·좌표 (반경 사각형).
        scope: 전국·시·도·시·군·구 (지역 목록).
        dong: 동 (경계 사각형).
    """
    if scope is not None:
        return _search_region_sales(client, scope, _search_filters(building_types, states, supply_types), limit)
    notes: list[str] = []
    prefixes: list[str] = []
    if dong is not None:
        bbox = dong_bbox(client, dong)
        prefixes = [dong.address or dong.name]
        scope_name = f'{dong.name} 안'
    else:
        assert place is not None  # CLI 가 셋 중 하나를 준다
        radius = radius_km or DEFAULT_RADIUS_KM
        bbox = bbox_of(*box_around(place.lat, place.lng, radius))
        scope_name = f'{place.name} 반경 {radius:g}km (사각형)'
    filters = DabangSaleInLotsFiltersModel(
        building_type_list=[SALE_BUILDING_TYPE_BY_LABEL[label] for label in building_types or []] or list(ALL_SALE_BUILDING_TYPES),
        state_list=[SALE_STATE_BY_LABEL[label] for label in states or []] or list(ALL_SALE_STATES),
        supply_type_list=[SALE_SUPPLY_BY_LABEL[label] for label in supply_types or []] or list(ALL_SALE_SUPPLY_TYPES),
    )

    def fetch(page: int) -> DabangPage[DabangSaleItemModel] | None:
        result = client.run_request_sale_list_category_bbox_v5(
            DabangSaleListCategoryBboxV5RequestParameterModel(filters=filters, bbox=bbox, page=page)
        ).result
        return None if result is None else DabangPage(result.sale_list, result.total, bool(result.has_more))

    # 쪽 수는 limit 을 24건으로 나눠 정하지 않고 limit 이 찰 때까지 받는다 (`fetch_pages`). limit 은 받은 단지 수로 센다
    pages = fetch_pages(fetch, limit)
    sales: list[DabangSaleSummary] = []
    outside = 0
    for item in pages.rows:
        address = normalize_address(item.address) or ''
        if prefixes and not any(address == prefix or address.startswith(f'{prefix} ') for prefix in prefixes):
            outside += 1
            continue
        sales.append(_summary(item))
    if outside:
        notes.append(note('제외', f'경계를 덮는 사각형에서 받은 단지 중 주소가 다른 {outside}곳을 뺐습니다 (뺀 만큼 다시 채우지 않음)'))
    # 역·대학·좌표(place)는 반경 사각형이라 반경을, 동은 지역을 좁히라고 한다
    notes += _sale_list_notes(pages, limit, in_box=True, narrow_end='반경' if place is not None else '지역')
    return DabangSaleListResult(
        scope=scope_name, total=pages.total, returned=len(sales), has_more=pages.has_more, sales=sales, notes=notes,
    )


def _search_region_sales(
    client: DabangClient, scope: DabangScope, filters: DabangSaleInLotsSearchFiltersModel, limit: int,
) -> DabangSaleListResult:
    """전국·시·도·시·군·구 안 분양 단지 (웹 분양 지역 목록 `list/search3`, 24곳씩). 거르지 않고 다방 목록 그대로 낸다.

    웹은 시·군·구를 고르면 시·도 코드와 시·군·구 코드를 함께 보낸다 (2026-11-13 캡처: 강남구 `state_code=11&city_code=11680`).
    두 값은 범위를 찾은 시·도 목록·시·군·구 목록(`resolve_scope`)의 `code` 다. 웹 지역 고르기도 같은 목록의 값을 보낸다.
    """
    state_code = scope.state_code if scope.kind in ('state', 'district') else None
    city_code = scope.code if scope.kind == 'district' else None
    recommended = 0

    def fetch(page: int) -> DabangPage[DabangSaleInLotsItemModel]:
        nonlocal recommended
        result = client.run_request_sale_in_lots_list_search3_v3(DabangSaleInLotsListSearch3V3RequestParameterModel(
            page=page, state_code=state_code, city_code=city_code, filters=filters,
        ))
        if page == 1:
            recommended = len(result.features or [])
        # 줄 목록이 null 이면 빈 쪽이라 거기서 멈춘다
        return DabangPage(result.sale_in_lotses or [], result.total, bool(result.has_more))

    # 지역 목록의 쪽 크기는 분양 검색 요청의 값이다 (지도 목록은 매물 목록과 같은 기본값)
    pages = fetch_pages(fetch, limit, page_size=SALE_SEARCH_PAGE_SIZE)
    notes: list[str] = []
    if recommended:
        notes.append(note('제외', f'다방 추천 칸(features) {recommended}곳은 웹 분양 목록에 없어 넣지 않았습니다'))
    notes += _sale_list_notes(pages, limit, in_box=False, narrow_end='지역')
    return DabangSaleListResult(
        scope=scope.name if scope.kind == 'national' else f'{scope.name} 안', total=pages.total, returned=len(pages.rows),
        has_more=pages.has_more, sales=[_region_summary(item) for item in pages.rows], notes=notes,
    )


class DabangSaleStep(BaseModel):
    """분양 일정 한 단계."""

    model_config = ConfigDict(
        extra='forbid',
    )

    step: Annotated[
        str,
        Field(description="단계 ('모집공고', '특별공급', '1순위 청약', '2순위 청약', '당첨자발표', '계약기간', '입주예정일')")
    ]
    start: Annotated[
        str | None,
        Field(description='시작 (YYYY-MM-DD, 달만 알면 YYYY-MM)')
    ] = None
    # 다방은 한 시점인 단계에만 끝을 주지 않는다. 하루짜리 청약은 끝이 시작과 같은 날로 온다 (2026-10-28 실측: 분양 3곳
    # 모두 모집공고·당첨자발표·입주예정일만 끝이 없음). 끝이 해당 없는 단계라 null(모름) 대신 키를 뺀다
    end: Annotated[
        str | None,
        Field(exclude_if=lambda value: value is None, description='끝 (하루짜리는 시작과 같은 날. 모집공고·당첨자발표·입주예정일처럼 한 시점인 단계는 키 없음)')
    ] = None


class DabangSalePyeong(BaseModel):
    """분양 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="평형 ('55A')")
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='분양가, 임대 공급이면 임대가 (만원, 대표값. 단지의 price_kind)')
    ] = None


class DabangSubscriptionPyeong(BaseModel):
    """청약 결과의 평형 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description="평형 ('59A')")
    ] = None
    household_count: Annotated[
        int | None,
        Field(description="이 평형의 분양 세대수 (다방 '분양/총세대' 의 앞 값)")
    ] = None
    competition_rate: Annotated[
        float | None,
        Field(description="경쟁률 (5.52 = '5.52:1'). 다방 표시가 숫자가 아니면 null")
    ] = None
    winning_point: Annotated[
        int | None,
        Field(description='당첨가점 (점). 다방 표시가 숫자가 아니면 null')
    ] = None


class DabangSubscriptionResult(BaseModel):
    """청약 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    min_winning_point: Annotated[
        int | None,
        Field(description="최저 당첨가점 (점, 다방 '당첨가점(커트라인)')")
    ] = None
    max_competition_rate: Annotated[
        float | None,
        Field(description="최고 경쟁률 (5.52 = '5.52:1')")
    ] = None
    pyeongs: Annotated[
        list[DabangSubscriptionPyeong] | None,
        Field(description='평형별 경쟁률·당첨가점. 다방이 평형별 결과를 주지 않으면 null (모름, 없다는 뜻이 아니다)')
    ] = None


class DabangSaleDetail(BaseModel):
    """분양 단지 정보. 상담 전화·사진·좌표는 내보내지 않는다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale_id: Annotated[
        str,
        Field(description='분양 ID')
    ]
    name: Annotated[
        str,
        Field(description='단지 이름')
    ]
    state: Annotated[
        str | None,
        Field(description='분양 상태')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    sale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수')
    ] = None
    building_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    floors: Annotated[
        int | None,
        Field(description='지상 층수')
    ] = None
    basement_floors: Annotated[
        int | None,
        Field(description='지하 층수')
    ] = None
    builder: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    developer: Annotated[
        str | None,
        Field(description='시행사')
    ] = None
    price_kind: Annotated[
        str,
        Field(description="가격이 무엇인지 ('분양가', 공공임대·민간임대는 '임대가'. 다방 화면 이름표)")
    ]
    price_min_manwon: Annotated[
        float | None,
        Field(description='가격 최저 (만원, price_kind 의 분양가 또는 임대가)')
    ] = None
    price_max_manwon: Annotated[
        float | None,
        Field(description='가격 최고 (만원, price_kind 의 분양가 또는 임대가)')
    ] = None
    price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='평당가 (만원/3.3㎡, price_kind 기준)')
    ] = None
    region_average_price_per_pyeong_manwon: Annotated[
        float | None,
        Field(description='최근 6개월 이 지역 평균 평당가 (만원/3.3㎡, 다방 표시). 다방이 주지 않으면 null')
    ] = None
    move_in: Annotated[
        str | None,
        Field(description='입주 예정 (YYYY-MM)')
    ] = None
    regulation_area: Annotated[
        str | None,
        Field(description='규제 지역. 모르면 null')
    ] = None
    price_cap: Annotated[
        bool | None,
        Field(description='분양가 상한제. 모르면 null')
    ] = None
    resalable: Annotated[
        bool | None,
        Field(description='전매 가능. 모르면 null')
    ] = None
    schedules: Annotated[
        list[DabangSaleStep],
        Field(description='일정 (모집공고부터 입주까지)')
    ]
    pyeongs: Annotated[
        list[DabangSalePyeong],
        Field(description='평형별 분양가(임대가)·세대수')
    ]
    subscription_result: Annotated[
        DabangSubscriptionResult | None,
        Field(description='청약 결과 (최저 당첨가점·최고 경쟁률·평형별 값). 청약 전이거나 다방에 결과가 없으면 null')
    ] = None
    notice_url: Annotated[
        str | None,
        Field(description='입주자 모집공고 파일 주소')
    ] = None
    applyhome_url: Annotated[
        str | None,
        Field(description='청약홈 주소')
    ] = None
    url: Annotated[
        str,
        Field(description='분양 페이지 URL')
    ]


def get_sale(client: DabangClient, sale_id: str) -> DabangSaleDetail:
    """분양 단지 하나 (요청 1회).

    Raises:
        JibsaError: 없는 분양 ID (NOT_FOUND).
    """
    try:
        response = client.run_request_sale_in_lots_detail2_v3(DabangSaleInLotsDetail2V3RequestParameterModel(id=sale_id))
    except HTTPStatusError as exc:
        # 분양 ID 는 쿼리로 간다. 없는 ID 는 400 '존재하지 않는 분양정보입니다.' (2026-10-27 실측)
        if is_missing_id(exc, in_path=False):
            raise JibsaError(
                code='NOT_FOUND',
                message=f'다방 분양 단지를 찾지 못했습니다: {sale_id}',
                hint='jibsa dabang search sales 나 search locations 결과의 sale_id 를 그대로 주세요',
            ) from None
        raise
    info = response.sale_in_lots
    # '12억9990 ~ 22억7680' (2026-10-26 실측 19곳 모두 이 꼴). '~' 가 없으면 한 가격이라 최고가도 같고, 있는데 뒤를 못 읽으면
    # 최고가를 모르는 것이라 null 로 둔다 (최저가로 채우면 범위가 정해진 것처럼 보인다)
    low, separator, high = ((info.price_info.price_str if info.price_info else None) or '').partition('~')
    subscription = response.subscription_result
    return DabangSaleDetail(
        sale_id=info.id,
        name=info.building_name,
        state=info.state_str,
        building_type=info.building_types_str,
        supply_type=info.supply_type_str,
        address=normalize_address(info.jibun_address or info.address),
        road_address=normalize_address(info.road_address),
        household_count=info.total_household_num,
        sale_household_count=info.lots_household_num,
        building_count=info.dong_count,
        floors=info.ground_floor,
        basement_floors=info.underground_floor,
        builder=info.provider_name,
        developer=info.constructor_name,
        price_kind='임대가' if info.supply_type in RENTAL_SUPPLY_TYPES else '분양가',
        price_min_manwon=manwon_from_text(low),
        price_max_manwon=manwon_from_text(high if separator else low),
        price_per_pyeong_manwon=manwon_from_text(info.price_info.pyeong_price) if info.price_info else None,
        region_average_price_per_pyeong_manwon=(
            manwon_from_text(info.price_info.region_average_pyeong_price) if info.price_info else None
        ),
        move_in=sale_date(info.moving_date_str),
        regulation_area=info.regulation_area_str,
        price_cap=info.is_price_cap,
        resalable=info.is_resalable,
        schedules=[
            DabangSaleStep(step=step.type_str or '', start=sale_date(step.from_str), end=sale_date(step.to_str))
            for step in response.schedules
        ],
        pyeongs=[
            DabangSalePyeong(
                name=space.space_name,
                area_m2=space.exclusive_space,
                supply_area_m2=space.supply_space,
                household_count=space.household_num,
                price_manwon=manwon_from_text(space.price_str),
            )
            for space in response.spaces
        ],
        subscription_result=None if subscription is None else DabangSubscriptionResult(
            min_winning_point=count_of(subscription.min_winning_point_str),
            max_competition_rate=number_of(subscription.max_competitive_rate_str),
            # 평형별 결과가 null 이면 모름이라 [] (없음) 로 바꾸지 않는다
            pyeongs=None if subscription.subscription_spaces is None else [
                DabangSubscriptionPyeong(
                    name=space.space_name,
                    household_count=count_of(space.household_num_str),
                    competition_rate=number_of(space.competitive_rate_str),
                    winning_point=count_of(space.winning_point_str),
                )
                for space in subscription.subscription_spaces
            ],
        ),
        notice_url=info.notice_url,
        applyhome_url=info.applyhome_link,
        url=sale_url(info.id),
    )


class DabangSaleScheduleSale(BaseModel):
    """청약 일정 줄의 분양 단지 정보 (`--details`, 다방 청약 일정 화면에서 날짜를 누르면 나오는 표)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    state: Annotated[
        str | None,
        Field(description='분양 상태 (분양예정·접수중·접수마감·입주예정·입주모집)')
    ] = None
    building_type: Annotated[
        str | None,
        Field(description='건물 유형')
    ] = None
    supply_type: Annotated[
        str | None,
        Field(description='공급 유형 (공공분양·민간분양·공공임대·민간임대)')
    ] = None
    address: Annotated[
        str | None,
        Field(description='동까지의 주소')
    ] = None
    sale_household_count: Annotated[
        int | None,
        Field(description='분양 세대수 (다방 표의 세대수 칸. 총세대수가 아니다)')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='총세대수')
    ] = None
    price_kind: Annotated[
        str | None,
        Field(description="가격 종류 ('분양가', 공공임대·민간임대는 '임대가')")
    ] = None
    price_manwon: Annotated[
        float | None,
        Field(description='대표 가격 (만원, 다방 표시). 아직 없으면 null')
    ] = None


class DabangSaleScheduleItem(BaseModel):
    """청약 일정 한 줄."""

    model_config = ConfigDict(
        extra='forbid',
    )

    date: Annotated[
        str,
        Field(description='날 (YYYY-MM-DD)')
    ]
    kind: Annotated[
        str | None,
        Field(description="종류 ('접수', '당첨자발표' 등 다방 표시)")
    ] = None
    region: Annotated[
        str | None,
        Field(description="일정 글의 시·도 ('서울', '경기'). 글이 시·도 없이 시나 단지 이름으로 시작하면 null")
    ] = None
    text: Annotated[
        str,
        Field(description="일정 글 ('[청약접수] 인천 … (~10/27)')")
    ]
    sale_id: Annotated[
        str | None,
        Field(description='분양 ID')
    ] = None
    # 그 날 상세를 받지 않은 줄(--details·--region 없이)은 해당 없음이라 키를 빼고, 받았는데 그 날
    # 상세에서 이 줄을 찾지 못하면 모름이라 null 로 낸다 (`fetched`)
    sale: Annotated[
        DabangSaleScheduleSale | None,
        Field(description='분양 단지 정보 (--details·--region 일 때만. 그 날 상세에서 같은 분양·종류를 찾지 못한 줄은 null)')
    ] = None
    fetched: Annotated[
        bool,
        Field(exclude=True, description='그 날 분양 단지 표(상세)를 받았는지. 받지 않았으면 sale 키를 뺀다')
    ] = False

    @model_serializer(mode='wrap')
    def drop_unfetched_sale(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.fetched:
            data.pop('sale', None)
        return data


class DabangSaleSchedule(BaseModel):
    """날짜별 청약 일정."""

    model_config = ConfigDict(
        extra='forbid',
    )

    from_date: Annotated[
        str,
        Field(description='시작 날')
    ]
    to_date: Annotated[
        str,
        Field(description='끝 날')
    ]
    total: Annotated[
        int,
        Field(description='기간 안 일정 수 (--region 으로 거르기 전)')
    ]
    returned: Annotated[
        int,
        Field(description='반환한 일정 수')
    ]
    schedules: Annotated[
        list[DabangSaleScheduleItem],
        Field(description='날짜 순 일정')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='일부·거르기 안내')
    ] = []


def _schedule_sale(item: DabangSaleScheduleTableRowModel) -> DabangSaleScheduleSale:
    return DabangSaleScheduleSale(**_in_lots_fields(item))


def get_sale_schedule(
    client: DabangClient, *, start: date, days: int, region: str | None = None, details: bool = False, limit: int,
) -> DabangSaleSchedule:
    """`start` 부터 `days` 일(최대 7일)의 청약 일정 (요청 1회).

    `details` 면 일정이 있는 날마다 그 날의 분양 단지 표(`list/schedule/search`, 웹 청약 일정 화면에서 날짜를 누르면 나오는
    표)를 받아 줄마다 주소·유형·세대수·가격을 붙인다 (날마다 요청 1회 더). 내보낼 줄(`limit`)이 든 날만 받는다. 줄은 분양 ID 와
    종류 번호(요약 `type` = 상세 `grouping`)가 모두 같은 상세 줄과 맞춘다. 웹도 두 목록을 같은 서버 순서로 그린다.

    `region` 을 주면 상세를 받아(`details` 와 같다) 주소의 시·도로 거른다. 남긴 줄이 `limit` 을 넘으면(더 있는지 알려고
    `limit`+1 줄) 그 뒤 날은 받지 않고 멈춘다. 뒷날 줄을 일정 글의 시·도만으로 거르면 앞날과 기준이 달라져 아예 보지 않는다.
    상세에서 찾지 못한 줄만 일정 글 앞의 시·도로 보고, 그것도 없으면 지역을 몰라 뺀다.

    Raises:
        JibsaError: `region` 이 시·도 이름이 아닐 때 (INVALID_ARGUMENT).
    """
    wanted = state_name(region.strip()) if region else None
    if region and wanted is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"--region 은 시·도 이름이어야 합니다: '{region}'",
            hint='서울·경기·충북처럼 줄임말이나 충청북도 같은 정식 이름을 주세요. 시·군·구로는 거르지 못합니다',
        )
    details = details or wanted is not None
    end = start + timedelta(days=days - 1)
    result = client.run_request_sale_in_lots_list_schedule_v3(
        DabangSaleInLotsListScheduleV3RequestParameterModel(from_date=start, to_date=end)
    ).root
    rows: list[DabangSaleScheduleItem] = []
    # rows 와 같은 순서로, 그 줄을 그 날 분양 단지 표와 맞춰 봤는지 (표를 받았고 분양 ID·종류가 모두 있을 때). 출력 필드는 아니다
    matched_lookup: list[bool] = []
    total = sum(len(group.schedules) for day in result for group in day.schedule_by_type)
    unknown = 0
    requests = 0
    # 지역으로 거르다 limit 을 넘겨 멈춘 날과 그 앞날까지 본 일정 수 (멈추지 않으면 None)
    stopped_at: str | None = None
    seen = 0
    for day in result:
        entries = [(group, entry) for group in day.schedule_by_type for entry in group.schedules]
        if wanted is not None and entries and len(rows) > limit:
            stopped_at = day.date
            break
        seen += len(entries)
        sales: dict[tuple[str, int], DabangSaleScheduleTableRowModel] | None = None
        # 지역으로 거르지 않으면 앞 limit 줄이 든 날까지만 상세를 받는다 (뒷날 줄은 내보내지 않는다)
        if details and entries and (wanted is not None or len(rows) < limit):
            response = client.run_request_sale_in_lots_list_schedule_search_v3(
                DabangSaleInLotsListScheduleSearchV3RequestParameterModel(from_date=date.fromisoformat(day.date))
            )
            requests += 1
            sales = {}
            for row in response.root:
                # 분양 ID·종류 번호가 없는 줄은 요약 줄과 맞출 수 없어 넣지 않는다 (그 줄과 맞출 요약 줄은 sale 이 null)
                if row.id is not None and row.grouping is not None:
                    sales.setdefault((row.id, row.grouping), row)
        for group, entry in entries:
            kind = (group.type_title or '').split(' ')[0] or None
            text = entry.schedule_str or ''
            match = SCHEDULE_REGION_PATTERN.match(text)
            # 글은 '[청약접수] 인천 …' 처럼 시·도 줄임말로 시작하지만 시·도 없이 시나 단지 이름으로 시작하기도 한다
            # (2026-10-25 실측 7일 83건 중 '익산 부송에코르'·'한양립스 에듀포레', 태그가 둘인 '[계약기간]  [무순위] 올 뉴
            # 챔피언스시티'). 칸에는 좌표뿐이라 시·도가 아니면 모름(None)으로 둔다. '광주시' 로 시작하면 경기도 광주시라
            # 다른 시('익산')처럼 모름이다 (`state_name`)
            where = match.group(1) if match and state_name(match.group(1)) else None
            found: DabangSaleScheduleTableRowModel | None = None
            # 종류 번호가 없으면 맞추지 않는다. 분양 ID 만으로 맞추면 같은 날 두 종류(접수·계약)인 단지의 줄을 가르지 못한다
            looked_up = False
            if sales is not None and entry.id is not None and group.type is not None:
                looked_up = True
                found = sales.get((entry.id, group.type))
            if wanted is not None:
                address = normalize_address(found.address) if found is not None else None
                state = state_name(address.split(' ')[0]) if address else state_name(where) if where else None
                if state != wanted:
                    unknown += state is None
                    continue
            rows.append(DabangSaleScheduleItem(
                date=day.date, kind=kind, region=where, text=text, sale_id=entry.id,
                sale=None if found is None else _schedule_sale(found), fetched=sales is not None,
            ))
            matched_lookup.append(looked_up)
    shown = rows[:limit]
    # 맞춰 본 줄만 찾지 못한 것으로 센다. 표를 받았어도 다방이 분양 ID·종류를 주지 않아 맞춰 보지 못한 줄은 따로 센다
    tried = sum(matched_lookup[:len(shown)])
    unmatched = sum(item.sale is None and looked for item, looked in zip(shown, matched_lookup))
    unchecked = sum(item.fetched and not looked for item, looked in zip(shown, matched_lookup))
    notes: list[str] = []
    if requests:
        notes.append(note('참고', f'일정이 있는 날 {requests}곳의 분양 단지 표를 더 받았습니다 (요청 {requests + 1}회)'))
    if unmatched:
        # 한 줄도 맞추지 못했으면 다방이 두 목록의 꼴을 바꾼 것이다 (매일 감시가 이 말로 고장을 찾는다)
        notes.append(note(
            '참고',
            f'{unmatched}건은 그 날 분양 단지 표에서 같은 분양·종류를 찾지 못해 sale 이 null 입니다'
            + (f'. {UPDATE_MAYBE_NEEDED}' if unmatched == tried else ''),
        ))
    if unchecked:
        # 맞춰 보지 못했으니 다방이 두 목록의 꼴을 바꾼 신호가 아니다 (업데이트 안내를 붙이지 않는다)
        notes.append(note('참고', f'{unchecked}건은 다방이 분양 ID·종류를 주지 않아 맞춰 보지 못해 sale 이 null 입니다'))
    if wanted is not None and stopped_at is None:
        notes.append(note('참고', f"주소의 시·도가 '{region}' 인 일정만 남겼습니다 ({total}건 중 {len(rows)}건)"))
    elif wanted is not None:
        notes.append(note('참고', (
            f"주소의 시·도가 '{region}' 인 일정만 남겼습니다 ({stopped_at} 전날까지 본 {seen}건 중 {len(rows)}건). "
            f'--limit 을 넘겨 {stopped_at}부터는 보지 않았습니다'
        )))
    if unknown:
        seen_days = '' if stopped_at is None else f'{stopped_at} 전날까지 본 일정 중 '
        notes.append(note(
            '제외', f'{seen_days}주소도 일정 글의 시·도도 없어 지역을 모르는 {unknown}건을 뺐습니다 (--region 없이 부르면 나옵니다)',
        ))
    if len(rows) > limit:
        # --limit 이 이미 최대값이면 늘리라고 하지 않는다 (2026-11-10 리뷰). 멈췄으면 뒷날을 보지 않아 남은 수를 모른다
        at_least = '' if stopped_at is None else '적어도 '
        notes.append(note(
            '일부',
            f'일정 {at_least}{len(rows)}건 중 앞 {limit}건입니다. '
            + more_hint(limit, SALE_SCHEDULE_MAX_LIMIT, '기간(--days)·지역(--region) 조건'),
        ))
    return DabangSaleSchedule(
        from_date=start.isoformat(), to_date=end.isoformat(), total=total, returned=len(shown), schedules=shown, notes=notes,
    )
