"""아파트 단지·오피스텔 건물 정보 (complex)와 단지 후보 (search locations)."""

from jibsa.core.listing import (
    TRADE_KEY_BY_NAME,
    holding_unread_dates,
    join_address,
    keep_unread_dates,
    lookup_failure_note,
    normalize_address,
    note,
    number_range,
    read_date,
    read_month,
)
from jibsa.providers.zigbang.api.client import ZigbangClient
from jibsa.providers.zigbang.api.models.request.complex.common import (
    ZigbangDanjisItemCatalogsRequestParameterModel,
    ZigbangDanjisRoomTypesRequestParameterModel,
    ZigbangItemsOfficetelsBuildingV1RequestParameterModel,
)
from jibsa.providers.zigbang.api.models.request.complex.info import (
    ZigbangDanjisSchoolsRequestParameterModel,
)
from jibsa.providers.zigbang.api.models.response.common import ZigbangSearchItemModel
from jibsa.providers.zigbang.api.models.response.complex.common import (
    ZigbangDanjisRoomTypesResponseModel,
)
from jibsa.providers.zigbang.api.models.response.complex.info import (
    ZigbangDanjisSchoolsResponseModel,
)
from jibsa.providers.zigbang.service.common.constants import (
    APT_DANJI_URL,
    NEAREST_SCHOOLS,
    OPTIONAL_LOOKUP_ERRORS,
    TRADE_BY_APT_TRAN_TYPE,
    UNEXPECTED_FORMAT_TEXT,
)
from jibsa.providers.zigbang.service.common.danji import fetch_danji
from jibsa.providers.zigbang.service.common.ids import (
    parse_complex_id,
)
from jibsa.providers.zigbang.service.common.models import ZigbangEstimatedPrice
from jibsa.providers.zigbang.service.common.price import (
    estimated_prices_of,
    sale_price_range,
)
from jibsa.providers.zigbang.service.common.text import (
    school_label,
    text_or_none,
    to_int,
)
from jibsa.providers.zigbang.service.complex.common import (
    fetch_building,
    related_complex_of,
)
from jibsa.providers.zigbang.service.complex.constants import (
    COMPLEX_KIND_BY_SEARCH_TYPE,
    OFFICETEL_DANJI_ITEMS_URL,
    PROPERTY_TYPE_BY_COMPLEX_KIND,
)
from jibsa.providers.zigbang.service.complex.models import (
    ZigbangComplex,
    ZigbangComplexCandidate,
    ZigbangComplexRank,
    ZigbangLandTradePermitDay,
    ZigbangPyeong,
)
from jibsa.providers.zigbang.service.region import search_regions

from typing import TypeVar


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
        building = fetch_building(
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
            url=OFFICETEL_DANJI_ITEMS_URL.format(number),
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
        url=APT_DANJI_URL.format(number),
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
            [f'이 단지에 거주 후기 {danji.review_count}개가 있습니다. 후기 내용은 직방 단지 페이지({APT_DANJI_URL.format(number)})에서 확인하세요']
            if danji.review_count else []
        ),
    )
