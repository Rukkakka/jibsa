"""아파트 단지·오피스텔 건물 정보와 단지 매물 목록 (complex, search listings --complex)."""

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.listing import (
    TRADE_KEY_BY_NAME,
    Listing,
    holding_unread_dates,
    join_address,
    keep_unread_dates,
    limit_notes,
    lookup_failure_note,
    normalize_address,
    note,
    null_items_note,
    number_range,
    read_date,
    read_month,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.request.complex.base import (
    ZigbangDanjisRoomTypesRequestParameterModel,
)
from jibsa.providers.zigbang.api.request.complex.detail import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
    ZigbangDanjisSchoolsRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.response.common import (
    ZigbangSearchItemModel,
)
from jibsa.providers.zigbang.api.response.complex.base import (
    ZigbangDanjisRoomTypesResponseModel,
)
from jibsa.providers.zigbang.api.response.complex.detail import (
    ZigbangDanjisSchoolsResponseModel,
    ZigbangItemsOfficetelsBuildingV1ResponseModel,
)
from jibsa.providers.zigbang.service.common.apt import (
    APT_TRAN_TYPE_BY_TRADE,
    TRADE_BY_APT_TRAN_TYPE,
    apt_pagination_notes,
    catalog_null_notes,
    catalog_to_listing,
)
from jibsa.providers.zigbang.service.common.base import (
    MAX_LIST_LIMIT,
    NEAREST_SCHOOLS,
    OPTIONAL_LOOKUP_ERRORS,
    UNEXPECTED_FORMAT_TEXT,
    ComplexKind,
    apt_danji_url,
    complex_not_found,
    estimated_prices_of,
    fetch_danji,
    parse_complex_id,
    sale_price_range,
    school_label,
    text_or_none,
)
from jibsa.providers.zigbang.service.common.models import (
    ZigbangEstimatedPrice,
    ZigbangRoomConditions,
)
from jibsa.providers.zigbang.service.common.room import (
    ROOM_TYPE_FILTER_BY_LABEL,
    SALES_TYPE_BY_TRADE,
    excluded_notes,
    pin_null_notes,
    room_filter_of,
    section_ordered_ids,
    summary_to_listing,
    tradeable_summaries,
)
from jibsa.providers.zigbang.service.complex.base import related_complex_of
from jibsa.providers.zigbang.service.complex.models import (
    ZigbangComplex,
    ZigbangComplexCandidate,
    ZigbangComplexListingsResult,
    ZigbangComplexRank,
    ZigbangLandTradePermitDay,
    ZigbangPyeong,
)
from jibsa.providers.zigbang.service.region import (
    search_regions,
    to_int,
)

from typing import TypeVar


COMPLEX_KIND_BY_SEARCH_TYPE: dict[str, ComplexKind] = {
    'apartment': 'apt',
    'officetel': 'officetel',
}
PROPERTY_TYPE_BY_COMPLEX_KIND: dict[ComplexKind, str] = {
    'apt': '아파트',
    'officetel': '오피스텔',
}

DANJI_CATALOG_PAGE_SIZE: int = 50

NumberT = TypeVar('NumberT', bound=float)


def danji_schools(response: ZigbangDanjisSchoolsResponseModel) -> list[str]:
    """아파트 단지 학군을 당근 `schools` 와 같은 문구로 바꾼다.

    초등은 통학구역 안 학교를 '배정' 으로, 중·고는 학교군 안에서 가까운 `NEAREST_SCHOOLS` 곳을 학교군 이름과 함께 준다.
    """
    labels: list[str | None] = []
    if response.elementary:
        labels += [school_label(school.name, '배정', school.distance) for school in response.elementary.schools]
    # 중·고교는 거리순으로 와서 정렬하지 않고 앞에서 자른다. 매물 학군(`building_schools`)은 거리 숫자를 받아 정렬한다
    # (2026-10-14 실측: 단지 6곳(apt-38487·946·33293·2873·2942·4567) 중학교 9~17곳·고등학교 21~26곳 모두 거리 오름차순)
    for level in (response.middle, response.high):
        if level:
            labels += [
                school_label(school.name, level.zone_name, school.distance)
                for school in level.schools[:NEAREST_SCHOOLS]
            ]
    return [label for label in labels if label]


def complex_candidate_of(item: ZigbangSearchItemModel) -> ZigbangComplexCandidate | None:
    """검색 결과 한 건을 단지 후보로 바꾼다. 아파트·오피스텔이 아니면 None."""
    kind = COMPLEX_KIND_BY_SEARCH_TYPE.get(item.type)
    if kind is None:
        return None
    source = item.source
    return ZigbangComplexCandidate(
        complex_id=f'{kind}-{item.id}',
        complex_type=PROPERTY_TYPE_BY_COMPLEX_KIND[kind],
        name=item.name,
        address=normalize_address(item.description),
        household_count=source.household if source else None,
        approved_date=read_date(source.approval_date, '사용승인일') if source else None,
    )


def search_regions_and_complexes(
    client: ZigbangClient,
    query: str,
    *,
    limit: int,
) -> tuple[list[ZigbangSearchItemModel], list[ZigbangComplexCandidate]]:
    """이름으로 지역·역·학교와 아파트 단지·오피스텔 건물 후보를 함께 찾는다 (2회 호출, 관련도 순).

    직방 검색은 서비스 유형마다 다른 결과를 준다. 오피스텔로 찾으면 원룸으로 찾을 때와 같은
    지역·역·학교·대학교에 오피스텔 건물이 더해지고, 아파트로 찾아야 아파트 단지가 나온다
    (아파트로 찾으면 대학교가 빠진다). 그래서 오피스텔·아파트로 한 번씩 찾는다.
    예전 이름·별칭으로도 맞추므로 이름이 달라 보이는 후보가 섞일 수 있다.

    Returns:
        (지역 결과, 단지 후보). 지역 결과에는 단지가 없다. 단지 후보는 `limit` 곳까지.
    """
    # 후보 목록이라 하나를 고르지 않고 좌표(`search locations` 가 지역마다 lat·lng 로 낸다)를 그대로 내보낸다. 좌표 없는 후보는
    # 위치를 줄 수 없어 지금처럼 뺀다
    officetel_items = search_regions(client, query, service_type='오피스텔', require_coordinates=True)
    regions = [item for item in officetel_items if item.type not in COMPLEX_KIND_BY_SEARCH_TYPE]
    candidates: dict[str, ZigbangComplexCandidate] = {}
    held: dict[str, list[tuple[str, str]]] = {}
    for item in [*search_regions(client, query, service_type='아파트', require_coordinates=True), *officetel_items]:
        with holding_unread_dates() as dates:
            candidate = complex_candidate_of(item)
        if candidate is not None and candidate.complex_id not in candidates:
            candidates[candidate.complex_id] = candidate
            held[candidate.complex_id] = dates
    result = list(candidates.values())[:limit]
    for candidate in result:
        keep_unread_dates(held[candidate.complex_id])
    return regions, result


def _fetch_building(
    client: ZigbangClient,
    complex_id: str,
    parameter: ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
) -> ZigbangItemsOfficetelsBuildingV1ResponseModel:
    try:
        return client.run_request_items_officetels_building_v1(parameter)
    except HTTPStatusError as exc:
        # 없는 건물이면 404 가 아니라 400 ("오피스텔 건물을 찾을 수 없습니다") 이다. 필터 값 오류도 400 이지만 요청 모델
        # Literal·ge=0 이 서버 허용값과 같아 보내기 전에 막히고, 범위 역전 같은 조합은 200 빈 목록이다 (2026-10-11 실측)
        if exc.response.status_code in (400, 404):
            raise complex_not_found(complex_id) from None
        raise


def _positive_or_none(value: NumberT | None) -> NumberT | None:
    """0 이하이거나 빠진 값은 모름(None). 웹이 0 을 '시세없음'·'-' 로 그리고 관리비 줄을 숨기는 값에 쓴다 (평형 시세·관리비)."""
    return value if value is not None and value > 0 else None


def get_complex(client: ZigbangClient, complex_id: str) -> ZigbangComplex:
    """단지 정보와 지금 올라온 매물 수를 모은다 (아파트 4회: 단지·매물 수·학군·평형 정보, 오피스텔 1회 호출).

    학군과 평형 정보(`room_types`, 평형 목록(매물 목록 응답의 `danjiRoomTypes`, 출처·순서는 그대로)에 면적·관리비·직방시세를
    붙인다)는 덤 조회라, 실패하면 그 값만 모름(null)이고 `[실패]` 안내가 붙는다. 순위·관련 단지·토지거래허가는 단지 정보 응답에 있어
    요청이 늘지 않는다.

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나 (INVALID_ARGUMENT) 없는 단지일 때 (NOT_FOUND).
    """
    kind, number = parse_complex_id(complex_id)
    if kind == 'officetel':
        building = _fetch_building(
            client, complex_id, ZigbangItemsOfficetelsBuildingV1RequestParameterModel(building_id=number)
        ).building
        return ZigbangComplex(
            complex_id=complex_id,
            name=building.name,
            complex_type='오피스텔',
            # 건물 주소는 시·도를 줄여 주기도 한다 (2026-10-11 실측: '서울시 강남구 역삼동', '제주도 제주시 연동')
            address=normalize_address(building.address.full_text if building.address else None),
            household_count=to_int(building.household),
            # 직방은 동 최고 층수만 줘서 lowest 는 늘 null(모름)이다. 최고 층수를 모르면 범위도 모름(None)
            building_floor_range=number_range(None, to_int(building.floor)),
            completed_month=read_month(building.established, '준공 연월'),
            # 건물 API 의 false 는 믿을 수 없어 모름으로 둔다. 2026-10-10 실측: 건물 53곳 중 false 30곳(6~41층)이
            # 모두 그 건물 매물 상세에서는 엘리베이터 있음이었고, false 가 맞은 곳은 없었다 (true 23곳은 모두 일치)
            has_elevator=True if building.elevator else None,
            # 매물이 없으면 itemCount 0 이 온다 (2026-10-10 실측 29곳). 빠지면 0 이 아니라 모름이다
            listing_count=building.item_count,
            # 웹은 건물 ID 를 이 경로의 area_danji_id 자리에 넣는다
            url=f'https://www.zigbang.com/home/officetel/danjis/{number}/items',
        )

    danji = fetch_danji(client, complex_id, number)
    catalogs = client.run_request_danjis_item_catalogs(
        ZigbangDanjisItemCatalogsRequestParameterModel(danji_id=number, limit=1)
    )
    school_notes: list[str] = []
    try:
        schools = danji_schools(client.run_request_danjis_schools(ZigbangDanjisSchoolsRequestParameterModel(danji_id=number)))
    except OPTIONAL_LOOKUP_ERRORS as exc:
        # 학군을 못 받아도 단지 정보는 돌려준다 (모름)
        schools = None
        school_notes = [lookup_failure_note(
            exc, '직방', '단지 학군 정보', 'schools 값을 모릅니다 (url 의 직방 단지 페이지에서 확인)',
        )]
    # 평형 정보 조회(덤). 실패(요청 제한 포함)하면 모름(None)과 `[실패]` 안내
    room_info: ZigbangDanjisRoomTypesResponseModel | None
    lookup_notes: list[str] = []
    try:
        room_info = client.run_request_danjis_room_types(ZigbangDanjisRoomTypesRequestParameterModel(danji_id=number))
    except OPTIONAL_LOOKUP_ERRORS as exc:
        room_info = None
        lookup_notes = [lookup_failure_note(
            exc, '직방', '평형 정보',
            '평형별 면적·관리비·직방시세와 단지 직방시세를 모릅니다 (url 의 직방 단지 페이지에서 확인)',
        )]
    details = {room_type.id: room_type for room_type in room_info.room_types or []} if room_info else {}
    average_sales = _positive_or_none(room_info.average_sales_price) if room_info else None
    average_rent = _positive_or_none(room_info.average_rent_price) if room_info else None
    pyeong_notes: list[str] = []
    if catalogs.room_types is None:
        # 평형 목록(매물 목록 응답의 danjiRoomTypes)이 없으면 모름이라, 평형이 없는 단지([])와 가른다
        pyeong_notes.append(note('참고', f'직방이 단지 평형 목록을 주지 않아 pyeongs 를 모릅니다. {UNEXPECTED_FORMAT_TEXT}'))
    pyeongs: list[ZigbangPyeong] | None = None
    if catalogs.room_types is not None:
        pyeongs = []
        for room_type in catalogs.room_types:
            # 평형 정보 조회(`detail`)의 값은 같은 ID 로 붙이고, 없으면 새 값은 모름(null)이다
            detail = details.get(room_type.id)
            title = room_type.room_type_title
            supply = detail.supply_area if detail else None
            exclusive = detail.exclusive_area if detail else None
            cost = detail.manage_cost if detail else None
            sales = detail.sales_price if detail else None
            rent = detail.rent_price if detail else None
            pyeongs.append(ZigbangPyeong(
                pyeong_id=room_type.id,
                name=title.m2 if title else None,
                pyeong_name=text_or_none(title.p) if title else None,
                supply_area_m2=supply.m2 if supply else None,
                supply_area_pyeong=supply.p if supply else None,
                area_m2=exclusive.m2 if exclusive else None,
                area_pyeong=exclusive.p if exclusive else None,
                household_count=detail.household_count if detail else None,
                room_count=detail.room_count if detail else None,
                bathroom_count=detail.bathroom_count if detail else None,
                entrance=text_or_none(detail.entrance_type) if detail else None,
                # 웹 ManageCost 는 평균 관리비가 0 이나 null 이면 여름·겨울이 든 줄 전체를 숨기고, 평균이 있을 때 여름·겨울이 0 이나 null 이면 '-' 로
                # 그린다 (2026-11-19 번들). jibsa 는 평균이 없어도 직방이 준 여름·겨울 값을 내므로 셋을 따로 거른다 (웹과 다른 점, 소스 가이드)
                manage_cost_manwon=_positive_or_none(cost.average) if cost else None,
                summer_manage_cost_manwon=_positive_or_none(cost.summer) if cost else None,
                winter_manage_cost_manwon=_positive_or_none(cost.winter) if cost else None,
                resale_available_date=read_date(detail.resale_available_from, '전매 가능일') if detail else None,
                estimated_prices=estimated_prices_of(
                    _positive_or_none(sales.min) if sales else None,
                    _positive_or_none(sales.per_area) if sales else None,
                    _positive_or_none(rent.min) if rent else None,
                    _positive_or_none(rent.per_area) if rent else None,
                ),
            ))
    return ZigbangComplex(
        complex_id=complex_id,
        name=danji.name,
        # 아파트 API 로 받은 단지다. real_type('연립' 등)을 쓰면 오피스텔로 보고 아파트 필드를 지운다
        complex_type='아파트',
        address=normalize_address(join_address(danji.local1, danji.jibun_address)),
        household_count=danji.households,
        # 동 최고 층수만 줘서 lowest 는 null(모름)
        building_floor_range=number_range(None, danji.max_floor),
        dong_count=danji.dong_count,
        approved_date=read_date(danji.approval_date, '사용승인일'),
        construction_company=danji.construction_company,
        parking_per_household=danji.parking_per_household,
        floor_area_ratio_percent=danji.floor_area_ratio,
        heating=danji.heating,
        # 응답 모델은 totalCount 가 빠지면 페이지 계산용으로 0 을 채우지만, 여기서는 모름(null)이다 (실측 40곳 모두 왔다)
        listing_count=catalogs.total_count if 'total_count' in catalogs.model_fields_set else None,
        # 매물 없는 유형도 0 으로 온다 (2026-10-10 실측 40곳 모두 세 유형). 빠진 유형은 모름이다
        listing_counts={
            TRADE_KEY_BY_NAME[trade]: catalogs.count_by_tran_type.get(tran_type)
            for tran_type, trade in TRADE_BY_APT_TRAN_TYPE.items()
        },
        pyeongs=pyeongs,
        schools=schools,
        review_count=danji.review_count,
        url=apt_danji_url(number),
        estimated_ranges={'sale': sale_price_range(
            _positive_or_none(room_info.min_sales_price) if room_info else None,
            _positive_or_none(room_info.max_sales_price) if room_info else None,
        )},
        estimated_prices={
            'sale': None if average_sales is None else ZigbangEstimatedPrice(price_per_pyeong_manwon=average_sales),
            'jeonse': None if average_rent is None else ZigbangEstimatedPrice(price_per_pyeong_manwon=average_rent),
        },
        # 단지 상세의 순위를 웹 '<동>에서 이 단지의 랭킹은?' 절 값으로 낸다. 웹처럼 구·동 순위 중 하나라도 없으면 None 이다.
        # 웹은 `!순위 || !순위.local2 || !순위.local3` 이면 절을 그리지 않는다 (2026-11-19 번들 `Components_Rank`).
        # 순위 값 -1 은 웹이 '순위 없음' 으로 그리는 값이다
        ranking=(
            None if danji.rank is None or danji.rank.local2 is None or danji.rank.local3 is None
            else ZigbangComplexRank(
                region=text_or_none(danji.rank.local3.name),
                price_rank=None if danji.rank.trade_price_rank == -1 else danji.rank.trade_price_rank,
                popularity_rank=None if danji.rank.view_count_rank == -1 else danji.rank.view_count_rank,
            )
        ),
        # 관련 단지('함께 보면 좋은 단지')를 직방이 준 순서대로. 목록을 주지 않았으면(키 없음·null) 모름(None), 빈 목록이면 []
        related_complexes=(
            None if danji.relate_danji is None or danji.relate_danji.list is None
            else [related_complex_of(item) for item in danji.relate_danji.list]
        ),
        # 최근 7일 토지거래허가 일별 건수를 직방이 준 순서대로. 일별 건수를 주지 않았으면(키 없음·null) 모름(None)
        land_trade_permits=(
            None if danji.land_trade_permit is None or danji.land_trade_permit.daily_counts is None
            else [ZigbangLandTradePermitDay(date=read_date(day.date, '토지거래허가 날짜'), count=day.count) for day in danji.land_trade_permit.daily_counts]
        ),
        notes=school_notes + lookup_notes + pyeong_notes + (
            [f'이 단지에 거주 후기 {danji.review_count}개가 있습니다. 후기 내용은 직방 단지 페이지({apt_danji_url(number)})에서 확인하세요']
            if danji.review_count else []
        ),
    )


def list_complex_listings(
    client: ZigbangClient,
    complex_id: str,
    *,
    conditions: ZigbangRoomConditions | None = None,
    pyeong_ids: list[int] | None = None,
    limit: int = 20,
) -> ZigbangComplexListingsResult:
    """단지 하나의 매물을 직방이 보여 주는 순서로 `limit` 건 조회한다.

    아파트는 단지 정보(시·도 주소용)와 단지 매물 목록(같은 호·거래 유형을 묶은 카탈로그)을 50건씩,
    오피스텔은 건물의 매물 핀·섹션을 받아 웹 건물 화면처럼 섹션 순서로 세운 뒤 15개씩 요약을 받는다
    (`_list_officetel_building_listings`). 거래 유형·가격(만원)·평형 조건은 서버에서
    거른다. 평형은 아파트만 있다. 관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔만 받으며
    건물 API 에 그대로 보내 서버에서 거른다.

    응답 목록에 빈 항목(null)이 섞여 오면 빼고 읽되 아파트는 직방 offset 이 그 자리도 세므로 받은 수(`offset`·`inspected`)에 더해 센다.
    오피스텔 건물은 핀·섹션의 빈 항목을 `[제외]` 로만 알린다 (`catalog_null_notes`·`pin_null_notes`).

    Raises:
        JibsaError: 단지 ID 형식이 맞지 않거나, 오피스텔에 평형 조건을 줬거나,
            아파트에 오피스텔 전용 조건을 줬거나, 단지에 없는 평형 ID 를 줬을 때 (INVALID_ARGUMENT).
            없는 단지일 때 (NOT_FOUND).
    """
    conditions = conditions or ZigbangRoomConditions()
    kind, number = parse_complex_id(complex_id)
    building_filters: dict[str, object] = {
        # 오피스텔 건물 매물은 섞지 않은 순서로 받는다 (지도 목록과 같다, room.search_listings). 아파트는 이 값을 쓰지 않는다
        'without_random': True if kind == 'officetel' else None,
        'room_types': [ROOM_TYPE_FILTER_BY_LABEL[room] for room in conditions.room_types],
        **room_filter_of(conditions),
    }
    if kind == 'apt' and any(value is not None and value != [] for value in building_filters.values()):
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message='관리비·방 구조·면적·층·욕실·옵션·시설 조건은 오피스텔 건물에서만 사용할 수 있습니다',
            hint='해당 조건을 빼거나 officetel-... 건물 ID 를 사용하세요',
        )
    trade_types = conditions.trade_types
    if kind == 'officetel':
        if pyeong_ids:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message='오피스텔 건물에는 평형 조건이 없습니다',
                hint='--pyeong 을 빼고 다시 조회하세요. 평형은 아파트 단지(apt-...)에만 있습니다',
            )
        return _list_officetel_building_listings(
            client, complex_id, number, conditions=conditions, limit=limit, filters=building_filters,
        )

    tran_types = [APT_TRAN_TYPE_BY_TRADE[trade] for trade in trade_types if trade in APT_TRAN_TYPE_BY_TRADE]
    # 단지 매물 목록에는 시·도가 없어 단지 정보에서 받는다 (없는 단지도 여기서 알 수 있다)
    local1 = fetch_danji(client, complex_id, number).local1
    if trade_types and not tran_types:
        # 아파트에는 단기임대가 없다 (CLI 가 먼저 막는다). 조건을 비워 보내면 전체가 오므로 조회하지 않는다.
        # 없는 단지가 0건 성공으로 보이지 않도록 단지를 확인한 뒤에 돌려준다
        return ZigbangComplexListingsResult(complex_id=complex_id, total=0, returned=0, listings=[])
    listings: list[Listing] = []
    total = 0
    offset = 0
    inspected = 0
    # 목록에서 뺀 빈 항목 수와, 카탈로그의 묶인 매물 ID 목록에서 뺀 빈 항목 수 (`catalog_null_notes`)
    dropped_catalogs = 0
    dropped_id_lists = 0
    # 평형 목록(`danjiRoomTypes`)에서 뺀 빈 항목 수. 평형 ID 를 확인할 수 없을 때만 안내한다
    dropped_room_types = 0
    # 직방이 평형 목록을 주지 않아(모름) 평형 ID 를 확인하지 못했는지
    room_types_unknown = False
    seen: set[str] = set()
    while inspected < limit:
        page_size = min(DANJI_CATALOG_PAGE_SIZE, limit - inspected)
        response = client.run_request_danjis_item_catalogs(
            ZigbangDanjisItemCatalogsRequestParameterModel(
                danji_id=number,
                tran_types=tran_types,
                room_type_ids=pyeong_ids or [],
                sales_price_min=conditions.price_min,
                sales_price_max=conditions.price_max,
                deposit_min=conditions.deposit_min,
                deposit_max=conditions.deposit_max,
                rent_min=conditions.rent_min,
                rent_max=conditions.rent_max,
                offset=offset,
                limit=page_size,
            )
        )
        if offset == 0:
            if response.room_types is None:
                # 평형 목록이 없으면(모름) 평형이 없는 단지(빈 목록)와 달라, 확인하지 않고 그 평형으로 찾은 뒤 알린다
                room_types_unknown = bool(pyeong_ids)
            elif response.null_items('room_types'):
                # 평형 목록에서 빈 항목을 뺐으면 준 평형 ID 가 그 항목이었을 수 있어 단지에 있는지 확인하지 않는다
                dropped_room_types = response.null_items('room_types') if pyeong_ids else 0
            else:
                # 단지에 없는 평형이면 0건 대신 에러로 알린다. 단지 매물 목록은 없는 평형에도 빈 성공을 준다.
                # 평형 조건을 줘도 응답의 평형 목록(danjiRoomTypes)은 단지 전체라 첫 페이지로 확인한다 (2026-10-12 실측:
                # apt-68579 에 평형 999 를 주면 0건과 평형 30개, 조건 없이도 같은 30개). 평형 목록이 비어 오면(평형이 아직 없는
                # 단지) 확인하지 않는다
                known = {room_type.id for room_type in response.room_types}
                unknown = [pyeong_id for pyeong_id in pyeong_ids or [] if pyeong_id not in known]
                if known and unknown:
                    raise JibsaError(
                        code='INVALID_ARGUMENT',
                        message=f"{complex_id} 단지에 없는 평형 ID 입니다: {', '.join(map(str, unknown))}",
                        hint=f'jibsa zigbang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 --pyeong 에 주세요',
                    )
        total = response.total_count
        # 직방 offset 은 빈 항목(null)도 한 자리로 센다. 빈 항목을 빼고 읽었어도 받은 자리 수에 더해야 같은 매물을 다시 받거나 일찍 멈추지 않는다
        received = len(response.catalogs) + response.null_items('catalogs')
        dropped_catalogs += response.null_items('catalogs')
        dropped_id_lists += sum(catalog.null_items('item_id_list') for catalog in response.catalogs)
        inspected += received
        for catalog in response.catalogs:
            listing = catalog_to_listing(catalog, local1)
            if listing is not None and listing.id not in seen:
                seen.add(listing.id)
                listings.append(listing)
        offset += received
        if not received or offset >= total:
            break
    listings = listings[:limit]
    notes = apt_pagination_notes(
        # 단지 하나라 지역 대신 단지 매물의 조건만 좁히라고 한다 (오피스텔 건물·다방 단지 매물과 같다)
        len(listings), limit, inspected, has_more=offset < total, narrow='거래 유형·평형·가격 조건',
    ) + catalog_null_notes('직방 단지', dropped_catalogs, dropped_id_lists)
    if dropped_room_types:
        # 평형 ID 가 단지에 있는지 볼 수 없어 확인하지 않고 그 평형으로 찾았다
        notes.append(null_items_note('직방 단지 평형', dropped_room_types))
    if room_types_unknown:
        notes.append(note(
            '참고',
            f'직방이 단지 평형 목록을 주지 않아 --pyeong 평형 ID 가 이 단지의 것인지 확인하지 못했습니다. {UNEXPECTED_FORMAT_TEXT}',
        ))
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=offset < total,
        listings=listings,
        notes=notes,
    )


def _list_officetel_building_listings(
    client: ZigbangClient,
    complex_id: str,
    building_id: int,
    *,
    conditions: ZigbangRoomConditions,
    limit: int,
    filters: dict[str, object],
) -> ZigbangComplexListingsResult:
    """오피스텔 건물 하나의 매물을 웹 건물 화면 순서로 `limit` 건 조회한다 (건물 핀 1회 + 요약 15개에 1회).

    웹 건물 화면처럼 섹션 순서대로 매물 ID 를 잇는다 (2026-11-15 번들 `loadItemsV2`: `sections.flatMap(ids)`. 실측
    officetel-20227: 핀 순서는 51154972·51094170·51155651 인데 섹션은 안심추천 51094170·51155651, 안심일반 51154972). 핀
    순서는 이 순서와 달라 쓰지 않고, 어느 섹션에도 없는 핀만 잃지 않게 맨 뒤에 핀 순서로 붙인다 (지도 목록과 같은
    `section_ordered_ids`). 섹션 안은 서버가 섞지 않은 순서(`withoutRandom`)로 받는다. 앞 `limit` 개의 요약을 받아 그 순서대로 낸다.
    """
    response = _fetch_building(
        client,
        complex_id,
        ZigbangItemsOfficetelsBuildingV1RequestParameterModel(
            building_id=building_id,
            sales_types=[SALES_TYPE_BY_TRADE[trade] for trade in conditions.trade_types],
            deposit_min=conditions.deposit_min,
            deposit_max=conditions.deposit_max,
            rent_min=conditions.rent_min,
            rent_max=conditions.rent_max,
            sales_price_min=conditions.price_min,
            sales_price_max=conditions.price_max,
            **filters,
        )
    )
    ids = section_ordered_ids([response])
    # 조회 예산은 요약을 받는 매물 수다. 받은 뒤 뺀 매물은 다시 채우지 않는다
    scanned = ids[:limit]
    tradeable = tradeable_summaries(client, scanned)
    summaries = {summary.item_id: summary for summary in tradeable.items}
    # 요약 응답 순서에 기대지 않고 섹션 순서로 세운다
    listings: list[Listing] = [
        summary_to_listing(summaries[item_id], building_id=building_id) for item_id in scanned if item_id in summaries
    ]
    # 건물 매물은 서버가 거래 유형으로 이미 걸러 준 거래 중 매물뿐이라 매물 수가 곧 조건에 맞는 수다.
    total = len(ids)
    has_more = len(scanned) < total
    return ZigbangComplexListingsResult(
        complex_id=complex_id,
        total=total,
        returned=len(listings),
        has_more=has_more,
        listings=listings,
        notes=(
            # 아래 [일부] 안내의 '직방 목록 순으로' 와 같은 말로 쓴다 (한 응답에 '순서로'·'순으로' 가 섞였다, 2026-11-10 리뷰)
            excluded_notes(
                limit, len(scanned), len(listings), order='직방 목록 순으로 앞의', has_more=has_more,
                null_items=tradeable.null_items,
            )
            # 요약을 받은 핀 수(inspected)로 limit 에 닿았는지 본다. 받은 뒤 거래 불가로 뺀 만큼 다시 채우지 않아, 돌려준 수로
            # 보면 1건만 빠져도 안내가 사라진다. 단지 하나라 지역·반경 대신 단지 매물의 조건만 좁히라고 한다. 오피스텔 건물에는
            # 평형 조건이 없어(--pyeong 은 INVALID_ARGUMENT) 오피스텔에만 있는 방 구조·면적 조건을 권한다 (2026-11-10 실측:
            # officetel-2795 --limit 5 에 '평형' 을 권했다)
            + limit_notes(
                total, len(listings), limit, max_limit=MAX_LIST_LIMIT, order='직방 목록',
                narrow='거래 유형·방 구조·면적·가격 조건', inspected=len(scanned), has_more=has_more,
            )
            + pin_null_notes('직방 오피스텔 건물 매물 핀·섹션', [response])
        ),
    )
