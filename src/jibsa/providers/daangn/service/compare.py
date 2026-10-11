"""단지 비교와 주변 단지 (compare, nearby-complexes)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import RegionNotFoundError
from jibsa.core.listing import (
    normalize_address,
    normalize_date,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.compare import (
    DaangnComplexCompareRequestPayloadModel,
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.compare import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
    DaangnCompareRealsaleConnectionModel,
    DaangnCompareSubwayModel,
    DaangnComplexCardModel,
)
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    DaangnRegion,
    complex_not_found,
    complex_url,
    truncation_notes,
    unwrap_graphql,
)
from jibsa.providers.daangn.service.region import search_locations

from typing import Annotated


class DaangnPriceRange(BaseModel):
    """호가 매물의 금액 범위 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    count: Annotated[int, Field(description='매물 수')]
    min_manwon: Annotated[int, Field(description='최저 (만원)')]
    max_manwon: Annotated[int, Field(description='최고 (만원)')]


class DaangnAskingPrices(BaseModel):
    """현재 호가 매물(아파트 매물 앞 30건)의 거래 유형별 금액 범위. 해당 매물이 없으면 null."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale: Annotated[
        DaangnPriceRange | None,
        Field(description='매매가')
    ] = None
    jeonse: Annotated[
        DaangnPriceRange | None,
        Field(description='전세금')
    ] = None
    monthly_rent: Annotated[
        DaangnPriceRange | None,
        Field(description='월세 (보증금 제외)')
    ] = None


class DaangnCompareSchool(BaseModel):
    """배정 학교."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='학교 이름')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    walk_minutes: Annotated[
        int | None,
        Field(description='도보 (분)')
    ] = None


class DaangnCompareSubway(BaseModel):
    """주변 역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    station: Annotated[str, Field(description="역 이름 ('역' 까지)")]
    line: Annotated[
        str | None,
        Field(description='노선 (예: 2호선)')
    ] = None
    distance_m: Annotated[
        int | None,
        Field(description='거리 (m)')
    ] = None
    walk_minutes: Annotated[
        int | None,
        Field(description='도보 (분)')
    ] = None


class DaangnKbRange(BaseModel):
    """KB 시세 범위 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    low_manwon: Annotated[
        int | None,
        Field(description='하위가')
    ] = None
    mid_manwon: Annotated[
        int | None,
        Field(description='일반가')
    ] = None
    high_manwon: Annotated[
        int | None,
        Field(description='상위가')
    ] = None


class DaangnCompareRecentTrade(BaseModel):
    """평형 최근 실거래 하나 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    contract_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    price_manwon: Annotated[
        int | None,
        Field(description='매매가 (매매만)')
    ] = None
    deposit_manwon: Annotated[
        int | None,
        Field(description='보증금 (전월세만)')
    ] = None
    rent_manwon: Annotated[
        int | None,
        Field(description='월세 (전세면 0)')
    ] = None


class DaangnCompareAreaGroup(BaseModel):
    """전용면적 묶음 하나의 KB 시세와 최근 실거래."""

    model_config = ConfigDict(
        extra='forbid',
    )

    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음 (real-price·price-trend 의 --area)')
    ] = None
    representative: Annotated[
        bool,
        Field(description='대표 평형')
    ] = False
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    exclusive_area_m2: Annotated[
        float | None,
        Field(description='전용면적 (첫 평형, ㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (첫 평형, ㎡)')
    ] = None
    kb_sale: Annotated[
        DaangnKbRange | None,
        Field(description='KB 매매 시세')
    ] = None
    kb_jeonse: Annotated[
        DaangnKbRange | None,
        Field(description='KB 전세 시세')
    ] = None
    kb_survey_date: Annotated[
        str | None,
        Field(description='KB 조사 기준일')
    ] = None
    recent_sale: Annotated[
        DaangnCompareRecentTrade | None,
        Field(description='가장 최근 매매 실거래')
    ] = None
    recent_rent: Annotated[
        DaangnCompareRecentTrade | None,
        Field(description='가장 최근 전월세 실거래')
    ] = None


class DaangnComplexComparison(BaseModel):
    """단지 하나의 비교 칸. 후기 요약 글은 내보내지 않는다 (후기 수만)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='주소 (첫 건물 도로명, 없으면 지번)')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    buildings: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    min_floor: Annotated[
        int | None,
        Field(description='최저 층')
    ] = None
    max_floor: Annotated[
        int | None,
        Field(description='최고 층')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='현재 매물 수')
    ] = None
    asking: Annotated[DaangnAskingPrices, Field(description='현재 호가 범위')]
    manage_cost_per_m2_manwon: Annotated[
        float | None,
        Field(description='최근 달 ㎡당 관리비 (만원, K-apt)')
    ] = None
    manage_cost_month: Annotated[
        str | None,
        Field(description='관리비 기준 연월 (YYYY-MM)')
    ] = None
    review_count: Annotated[
        int | None,
        Field(description='거주 후기 수 (내용은 url 에서)')
    ] = None
    schools: Annotated[
        list[DaangnCompareSchool] | None,
        Field(description='배정 학교. 단지 공공 정보가 없으면 null (모름)')
    ] = None
    subways: Annotated[
        list[DaangnCompareSubway] | None,
        Field(description='주변 역. 단지 공공 정보가 없으면 null (모름)')
    ] = None
    area_groups: Annotated[
        list[DaangnCompareAreaGroup] | None,
        Field(description='전용면적 묶음별 시세·실거래. 단지 공공 정보가 없으면 null (모름)')
    ] = None
    url: Annotated[str, Field(description='당근 단지 페이지')]


class DaangnCompareResult(BaseModel):
    """단지 비교 결과."""

    model_config = ConfigDict(
        extra='forbid',
    )

    returned: Annotated[int, Field(description='비교한 단지 수')]
    complexes: Annotated[list[DaangnComplexComparison], Field(description='넣은 순서대로 단지')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='호가 범위 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def _price_range(values: list[int]) -> DaangnPriceRange | None:
    return DaangnPriceRange(count=len(values), min_manwon=min(values), max_manwon=max(values)) if values else None


def _asking_prices(complex_: DaangnCompareComplexModel) -> DaangnAskingPrices:
    """호가 매물 거래 조건을 매매·전세·월세로 나눠 범위를 낸다. 매물 하나에 거래 조건이 여럿이면 각각 센다.

    거래 종류(`__typename`)가 아니라 채워진 금액으로 나눠도 같다. 비교 쿼리는 종류마다 정해진 금액만 준다
    (2026-10-11 실측: 단지 7곳(10697092, 잠실엘스 10677393 등) 거래 64건이 BuyTrade 는 price 만, BorrowTrade 는
    deposit 만, MonthTrade 는 deposit·monthlyPay 만, ShortTrade 는 금액 없이 왔다). 그래서 단기임대는 월세에 섞이지 않고
    세지 않는다.
    """
    sale: list[int] = []
    jeonse: list[int] = []
    rent: list[int] = []
    edges = complex_.asking_articles.edges if complex_.asking_articles else []
    for edge in edges:
        for trade in edge.node.trades if edge.node else []:
            if trade.price is not None:
                sale.append(trade.price)
            elif trade.monthly_pay:
                rent.append(trade.monthly_pay)
            elif trade.deposit is not None:
                jeonse.append(trade.deposit)
    return DaangnAskingPrices(sale=_price_range(sale), jeonse=_price_range(jeonse), monthly_rent=_price_range(rent))


def _subways(rows: list[DaangnCompareSubwayModel]) -> list[DaangnCompareSubway]:
    """역마다 거리·도보 두 줄로 오는 것을 한 줄로 합친다."""
    merged: dict[tuple[str, str | None], DaangnCompareSubway] = {}
    for row in rows:
        if not row.station_nm:
            continue
        key = (row.station_nm, row.simple_line_nm)
        subway = merged.setdefault(key, DaangnCompareSubway(station=f'{row.station_nm}역', line=row.simple_line_nm))
        value = int(row.data_value) if row.data_value and row.data_value.isdigit() else None
        if row.data_type == 'DISTANCE':
            subway.distance_m = value
        elif row.data_type == 'WALKING':
            subway.walk_minutes = value
    return list(merged.values())


def _recent_trade(connections: list[DaangnCompareRealsaleConnectionModel | None]) -> DaangnCompareRecentTrade | None:
    """평형들의 실거래 중 계약일이 가장 최근인 하나."""
    trades = [
        edge.node for connection in connections if connection for edge in connection.edges
        if edge.node and edge.node.contact_date
    ]
    if not trades:
        return None
    latest = max(trades, key=lambda trade: trade.contact_date or '')
    # 이 쿼리의 borrowRealsale 에는 tradePrice 가 오지 않아 None 이면 전월세다. 지역 실거래 피드
    # (`realsale_to_real_price`)는 전월세에도 tradePrice 0 을 주지만 여기는 아니다 (2026-10-10 실측: 역삼래미안)
    return DaangnCompareRecentTrade(
        contract_date=normalize_date(latest.contact_date),
        floor=latest.floor,
        price_manwon=latest.trade_price,
        deposit_manwon=latest.deposit if latest.trade_price is None else None,
        rent_manwon=latest.month_rent_fee if latest.trade_price is None else None,
    )


def _area_group(group: DaangnCompareAreaGroupModel) -> DaangnCompareAreaGroup:
    first = group.py_infos[0] if group.py_infos else None
    kb = next(
        (edge.node for info in group.py_infos if info.kb_prices for edge in info.kb_prices.edges if edge.node),
        None,
    )
    return DaangnCompareAreaGroup(
        area_group=group.label,
        representative=bool(group.is_representative),
        households=group.total_cnt,
        exclusive_area_m2=first.exclusive_area if first else None,
        supply_area_m2=first.supply_area if first else None,
        kb_sale=DaangnKbRange(
            low_manwon=kb.sale_lower_limit, mid_manwon=kb.sale_std_price, high_manwon=kb.sale_upper_limit,
        ) if kb and kb.sale_std_price else None,
        kb_jeonse=DaangnKbRange(
            low_manwon=kb.lease_lower_limit, mid_manwon=kb.lease_std_price, high_manwon=kb.lease_upper_limit,
        ) if kb and kb.lease_std_price else None,
        kb_survey_date=normalize_date(kb.survey_base_date) if kb else None,
        recent_sale=_recent_trade([info.sale_realsale for info in group.py_infos]),
        recent_rent=_recent_trade([info.borrow_realsale for info in group.py_infos]),
    )


def _comparison(complex_: DaangnCompareComplexModel) -> DaangnComplexComparison:
    danji = complex_.proptier_danji
    building = next((edge.node for edge in complex_.buildings.edges if edge.node), None) if complex_.buildings else None
    costs = [
        cost for cost in (complex_.kapt.monthly_management_costs_per_square_meter if complex_.kapt else [])
        if cost.year_month and cost.cost_per_square_meter is not None
    ]
    latest_cost = max(costs, key=lambda cost: cost.year_month or '') if costs else None
    return DaangnComplexComparison(
        complex_id=complex_.original_id,
        name=complex_.name,
        type=COMPLEX_TYPE_LABELS.get(complex_.type or '', complex_.type),
        address=normalize_address(building.road_address or building.jibun_address) if building else None,
        approved_at=normalize_date(danji.build_date) if danji else None,
        buildings=danji.tot_dong_cnt if danji else None,
        households=danji.total_tot_hseh_cnt if danji else None,
        parking_per_household=danji.hseh_parking_cnt if danji else None,
        min_floor=danji.min_floor if danji else None,
        max_floor=danji.max_floor if danji else None,
        listing_count=complex_.live_article_count.total if complex_.live_article_count else None,
        asking=_asking_prices(complex_),
        manage_cost_per_m2_manwon=round(latest_cost.cost_per_square_meter / 10000, 4) if latest_cost and latest_cost.cost_per_square_meter is not None else None,
        manage_cost_month=f'{latest_cost.year_month[:4]}-{latest_cost.year_month[4:6]}' if latest_cost and latest_cost.year_month else None,
        review_count=complex_.lived_review_count,
        # 단지 공공 정보가 없으면 학교·역·면적 묶음은 모른다 (null). `complex_to_summary` 와 같다.
        # 2026-10-11 실측: 화곡동·역삼동·이도2동의 소규모 아파트·오피스텔·도시형 15곳 모두 있었다
        schools=[
            DaangnCompareSchool(name=school.school.sch_nm if school.school else None, distance_m=school.distance, walk_minutes=school.working_time)
            for school in danji.assigned_schools
        ] if danji else None,
        subways=_subways(danji.subway_info) if danji else None,
        area_groups=[_area_group(group) for group in danji.exclusive_area_groups] if danji else None,
        url=complex_url(complex_.original_id),
    )


def _compare_column(client: DaangnClient, complex_id: int) -> DaangnCompareComplexModel:
    response = client.run_request_complex_compare(DaangnComplexCompareRequestPayloadModel(original_id=str(complex_id)))
    output = response.data.complex_by_original_id if response.data else None
    found = output.complex if output else None
    if found is None and not response.errors:
        raise complex_not_found(complex_id)
    return unwrap_graphql(response, found, '단지 비교')


def compare_complexes(client: DaangnClient, complex_ids: list[int]) -> DaangnCompareResult:
    """단지 여러 곳(최대 `COMPARE_MAX_COMPLEXES`)을 같은 항목으로 나란히 본다 (단지마다 `complexByOriginalId` 1회).

    세대수·준공·주차·층, 배정 학교, 주변 역, 전용면적 묶음별 KB 시세와 최근 실거래, 현재 호가 범위,
    ㎡당 관리비를 준다. 후기 요약 글은 읽지 않는다 (후기 수만).

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    complexes = [_comparison(_compare_column(client, complex_id)) for complex_id in dict.fromkeys(complex_ids)]
    return DaangnCompareResult(
        returned=len(complexes),
        complexes=complexes,
        notes=['asking 은 당근에 올라온 아파트 매물 앞 30건의 호가 범위입니다. 실제 거래가는 area_groups 의 recent_sale·recent_rent 를 보세요'],
    )


# 같은 동 단지를 한 번에 받을 수이자 CLI --limit 최대값. 웹은 300 을 보내지만 300 을 넘는 동이 있고 페이지
# 정보가 오지 않아 한 번에 크게 받는다. 당근의 다른 목록 최대값(1200)에 맞췄다 (2026-10-10 실측: 화곡동 703곳,
# 봉천동 380곳. 1200 을 보내도 거절하지 않고, 단지 카드도 703개를 한 번에 준다)
NEARBY_COMPLEXES_MAX: int = 1200


class DaangnNearbyComplex(BaseModel):
    """같은 동 단지 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='단지 ID')]
    name: Annotated[
        str | None,
        Field(description='단지 이름')
    ] = None
    type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    households: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='현재 매물 수')
    ] = None


class DaangnNearbyComplexesResult(BaseModel):
    """같은 동 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='기준 단지 ID')]
    region: Annotated[DaangnRegion, Field(description='기준 단지가 있는 동')]
    total: Annotated[int, Field(description='기준 단지를 뺀 같은 동 단지 수 (limit 적용 전). 1200곳에서 잘리면 notes 로 알린다')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    complexes: Annotated[list[DaangnNearbyComplex], Field(description='세대수 많은 순 단지')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도 안내. CLI 가 notice 아래에 붙인다')
    ] = []


def list_nearby_complexes(client: DaangnClient, complex_id: int, *, limit: int = 50) -> DaangnNearbyComplexesResult:
    """기준 단지와 같은 동의 다른 단지를 세대수 많은 순으로 (요청 4회: 단지 → 동 ID → 동 단지 → 단지 카드).

    동 단지는 `NEARBY_COMPLEXES_MAX` 곳까지 한 번에 받고 (페이지 정보가 없다), 그만큼 받았으면 더 있을 수
    있다고 `notes` 로 알린다. 단지 카드도 ID 를 한 번에 보낸다.

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 동을 찾지 못함 (REGION_NOT_FOUND), 그 밖의 GraphQL 에러.
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    base = _compare_column(client, complex_id)
    known = base.region
    # 지역 검색은 이름이 비슷한 읍·면도 섞어 주고, 같은 시·군·구의 그런 후보가 정확한 동보다 먼저 오기도 해서 동 이름이
    # 같은 후보를 먼저 고른다 (2026-10-11 실측: '신동' 은 아산시 선장면·춘천시 신동면이 아산시 신동·춘천시 신동보다 먼저 왔다)
    same_sigungu = [
        location for location in search_locations(client, known.name3)
        if location.name1 == known.name1 and location.name2 == known.name2
    ] if known and known.name3 else []
    location = next(
        (location for location in same_sigungu if known and location.name3 == known.name3),
        same_sigungu[0] if same_sigungu else None,
    )
    if known is None or location is None:
        raise RegionNotFoundError(f'단지 {complex_id} 의 동', hint='jibsa daangn search complexes <동 이름> 으로 찾으세요')
    region = DaangnRegion(name1=location.name1 or '', name2=location.name2 or '', name3=location.name3 or '', region_id=location.id)
    response = client.run_request_nearby_complexes(
        DaangnNearbyComplexesRequestPayloadModel(region3_id=region.region_id, first=NEARBY_COMPLEXES_MAX)
    )
    nodes = unwrap_graphql(response, response.data.complexes if response.data else None, '같은 동 단지')
    capped_notes = (
        [
            f'당근에서 같은 동 단지를 {NEARBY_COMPLEXES_MAX}곳까지만 받아 더 있을 수 있습니다. '
            f'jibsa daangn search complexes {region.name3} 로도 찾아보세요'
        ]
        if len(nodes.edges) >= NEARBY_COMPLEXES_MAX else []
    )
    ids = [edge.node.original_id for edge in nodes.edges if edge.node and edge.node.original_id != str(complex_id)]
    cards: list[DaangnComplexCardModel] = []
    if ids:
        cards_response = client.run_request_complexes_by_original_complex_ids(
            DaangnComplexesByOriginalComplexIdsRequestPayloadModel(complex_ids=ids)
        )
        cards = unwrap_graphql(
            cards_response,
            cards_response.data.complexes_by_original_complex_ids if cards_response.data else None,
            '단지 카드',
        )
    nearby = [
        DaangnNearbyComplex(
            complex_id=card.original_id,
            name=card.name,
            type=COMPLEX_TYPE_LABELS.get(card.type or '', card.type),
            households=card.proptier_danji.total_tot_hseh_cnt if card.proptier_danji else None,
            listing_count=card.live_article_count.total if card.live_article_count else None,
        )
        for card in cards
    ]
    nearby.sort(key=lambda item: (item.households is None, -(item.households or 0)))
    return DaangnNearbyComplexesResult(
        complex_id=str(complex_id),
        region=region,
        total=len(nearby),
        returned=min(len(nearby), limit),
        complexes=nearby[:limit],
        notes=capped_notes + truncation_notes(len(nearby), limit, subject='단지', unit='곳', max_limit=NEARBY_COMPLEXES_MAX),
    )
