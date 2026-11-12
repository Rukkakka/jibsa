"""단지 비교와 주변 단지 (compare, nearby-complexes)."""

from math import trunc

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.errors import (
    JibsaError,
    RegionNotFoundError,
)
from jibsa.core.listing import (
    NOT_APPLICABLE_PRICE_FIELDS,
    UPDATE_MAYBE_NEEDED,
    normalize_address,
    normalize_date,
    note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.compare import (
    DaangnComplexCompareRequestPayloadModel,
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnComplexRegionRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.compare import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
    DaangnComparePyInfoModel,
    DaangnCompareRealsaleModel,
    DaangnCompareSubwayModel,
    DaangnComplexCardModel,
)
from jibsa.providers.daangn.service.common import (
    APARTMENT_COMPLEX_TYPES,
    COMPLEX_TYPE_LABELS,
    DaangnRegion,
    complex_not_found,
    complex_url,
    js_round,
    truncation_notes,
    unwrap_graphql,
)

from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
)


class DaangnAskingAverage(BaseModel):
    """호가 매물의 평균 금액 (만원)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    average_manwon: Annotated[int, Field(description='평균 (만원, 0원 매물은 뺀다)')]
    count: Annotated[int, Field(description='평균을 낸 거래 조건 수')]


class DaangnAskingPrices(BaseModel):
    """현재 호가 매물(아파트 매물 앞 30건)의 거래 유형별 평균. 당근 웹 비교 화면의 '평균 호가'다. 해당 매물이 없으면 null."""

    model_config = ConfigDict(
        extra='forbid',
    )

    sale: Annotated[
        DaangnAskingAverage | None,
        Field(description='매매가 평균')
    ] = None
    jeonse: Annotated[
        DaangnAskingAverage | None,
        Field(description='전세금 평균')
    ] = None
    monthly_deposit: Annotated[
        DaangnAskingAverage | None,
        Field(description='월세 매물의 보증금 평균 (웹과 같이 월세액이 아니다)')
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


class DaangnKbMonthly(BaseModel):
    """KB 월세 시세 (만원). 웹은 '보증금 / 월세 상위' 와 그 아래 '월차임 하위~상위' 로 보여 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    deposit_manwon: Annotated[
        int | None,
        Field(description='보증금')
    ] = None
    rent_low_manwon: Annotated[
        int | None,
        Field(description='월세 하위')
    ] = None
    rent_high_manwon: Annotated[
        int | None,
        Field(description='월세 상위')
    ] = None


class DaangnCompareRecentTrade(BaseModel):
    """평형 최근 실거래 하나 (만원). 거래 유형에 없는 금액은 키를 뺀다 (해당 없음: 매매는 보증금·월세, 전세는 매매가·월세, 월세는 매매가)."""

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
        Field(description='보증금 (전세·월세만)')
    ] = None
    rent_manwon: Annotated[
        int | None,
        Field(description='월세 (월세만)')
    ] = None
    trade_type: Annotated[
        Literal['매매', '전세', '월세'],
        Field(exclude=True, description='거래 유형. 해당 없는 금액 키를 고르는 데만 쓴다')
    ]

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        # 전세 칸도 월세 기준으로 빼면 당근이 주는 월세 0 이 'rent_manwon: 0' 으로 남았다 (2026-11-12 리뷰)
        for field in NOT_APPLICABLE_PRICE_FIELDS[self.trade_type]:
            data.pop(field, None)
        return data


class DaangnComparePyeong(BaseModel):
    """비교한 평형 하나의 KB 시세와 최근 실거래 (당근 웹 비교 화면이 단지마다 고르는 평형)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    pyeong: Annotated[
        int | None,
        Field(description='공급 평형 묶음 (아파트형 단지, real-price·price-trend --pyeong). 아니면 키가 없다')
    ] = None
    area_group: Annotated[
        int | None,
        Field(description='전용면적 묶음. 아파트형이 아닌 단지만 real-price·price-trend --area 에 넘긴다 (아파트형은 pyeong 을 --pyeong 에)')
    ] = None
    representative: Annotated[
        bool,
        Field(description='대표 평형 묶음인지')
    ] = False
    type_name: Annotated[
        str | None,
        Field(description="평형 타입 (예: 'A')")
    ] = None
    households: Annotated[
        int | None,
        Field(description='이 평형 세대수')
    ] = None
    exclusive_area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    kb_sale: Annotated[
        DaangnKbRange | None,
        Field(description='KB 매매 시세')
    ] = None
    kb_jeonse: Annotated[
        DaangnKbRange | None,
        Field(description='KB 전세 시세')
    ] = None
    kb_monthly: Annotated[
        DaangnKbMonthly | None,
        Field(description='KB 월세 시세')
    ] = None
    kb_survey_date: Annotated[
        str | None,
        Field(description='KB 조사 기준일')
    ] = None
    recent_sale: Annotated[
        DaangnCompareRecentTrade | None,
        Field(description='이 평형의 최근 매매 실거래')
    ] = None
    recent_jeonse: Annotated[
        DaangnCompareRecentTrade | None,
        Field(description='이 평형의 최근 전세 실거래')
    ] = None
    recent_monthly: Annotated[
        DaangnCompareRecentTrade | None,
        Field(description='이 평형의 최근 월세 실거래')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # 공급 평형 묶음은 아파트형 단지에만 있다
        data: dict[str, Any] = handler(self)
        if self.pyeong is None:
            data.pop('pyeong', None)
        return data


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
    asking: Annotated[DaangnAskingPrices, Field(description='현재 평균 호가')]
    manage_cost_manwon: Annotated[
        float | None,
        Field(description='비교한 평형의 월 관리비 추정 (만원, K-apt). 받은 달들의 ㎡당 관리비 평균 × 전용면적이다 (웹과 같다)')
    ] = None
    manage_cost_per_m2_manwon: Annotated[
        float | None,
        Field(description='받은 달들의 ㎡당 관리비 평균 (만원, K-apt)')
    ] = None
    manage_cost_period: Annotated[
        str | None,
        Field(description='관리비 평균을 낸 달 (YYYY-MM~YYYY-MM)')
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
    pyeong: Annotated[
        DaangnComparePyeong | None,
        Field(description='비교한 평형의 시세·실거래 (첫 단지는 대표 평형, 나머지는 그 전용면적과 가장 비슷한 평형). 단지 공공 정보가 없으면 null (모름)')
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
        Field(exclude=True, description='비교한 평형 기준과 평균 호가 안내. CLI 가 결과 위에 붙인다')
    ] = []


def _average(values: list[int]) -> DaangnAskingAverage | None:
    # 웹(compare `je`)처럼 Math.round
    return DaangnAskingAverage(average_manwon=js_round(sum(values) / len(values)), count=len(values)) if values else None


def _asking_prices(complex_: DaangnCompareComplexModel) -> DaangnAskingPrices:
    """호가 매물 거래 조건을 매매·전세·월세로 나눠 평균을 낸다 (당근 웹 비교 화면 `je`). 매물 하나에 거래 조건이 여럿이면 각각 센다.

    웹처럼 거래 종류(`__typename`)로 나누고 0원은 뺀다. 매매는 매매가, 전세는 전세금, 월세는 보증금 평균이다 (월세액이 아니다).
    단기임대는 세지 않는다. 예전에는 최저~최고 범위였고 0원도 셌으며 월세는 월세액이었다 (#215, 2026-11-12 번들 대조).
    """
    sale: list[int] = []
    jeonse: list[int] = []
    deposit: list[int] = []
    edges = complex_.asking_articles.edges if complex_.asking_articles else []
    for edge in edges:
        for trade in edge.node.trades if edge.node else []:
            if trade.typename == 'BuyTrade' and trade.price:
                sale.append(trade.price)
            elif trade.typename == 'BorrowTrade' and trade.deposit:
                jeonse.append(trade.deposit)
            elif trade.typename == 'MonthTrade' and trade.deposit:
                deposit.append(trade.deposit)
    return DaangnAskingPrices(sale=_average(sale), jeonse=_average(jeonse), monthly_deposit=_average(deposit))


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


def _trade(
    node: DaangnCompareRealsaleModel | None, trade_type: Literal['매매', '전세', '월세'],
) -> DaangnCompareRecentTrade | None:
    if node is None:
        return None
    return DaangnCompareRecentTrade(
        contract_date=normalize_date(node.contact_date),
        floor=node.floor,
        price_manwon=node.trade_price if trade_type == '매매' else None,
        deposit_manwon=None if trade_type == '매매' else node.deposit,
        rent_manwon=node.month_rent_fee if trade_type == '월세' else None,
        trade_type=trade_type,
    )


def _top_info(group: DaangnCompareAreaGroupModel) -> DaangnComparePyInfoModel | None:
    """묶음에서 세대수가 가장 많은 평형 (같으면 앞 평형, 웹 compare 의 `$`)."""
    return max(group.py_infos, key=lambda info: info.ptp_tot_hseh_cnt or 0) if group.py_infos else None


def _select_pyeong(
    column: DaangnCompareComplexModel, target_m2: float | None,
) -> tuple[bool, DaangnCompareAreaGroupModel, DaangnComparePyInfoModel] | None:
    """비교할 평형을 웹 비교 화면(`ve`·`_e`)처럼 고른다: 목표 면적이 없으면 대표 묶음(없으면 첫 묶음), 있으면 묶음마다 세대수가
    가장 많은 평형의 전용면적 정수가 목표와 가장 가까운 묶음 (같으면 대표 묶음, 그다음 세대수 많은 묶음). 그 묶음에서 세대수가
    가장 많은 평형이다."""
    supply, groups = pyeong_groups(column)
    tops = [(group, info) for group in groups if (info := _top_info(group)) is not None]
    if not tops:
        return None
    if target_m2 is None:
        group, info = next(((group, info) for group, info in tops if group.is_representative), tops[0])
        return supply, group, info
    target = trunc(target_m2)
    # 웹 `_e` 는 세대수 최다 평형의 전용면적을 모르는 묶음을 건너뛴다 (`if(e==null)continue`). 모두 모르면 고를 수 없다
    sized = [pair for pair in tops if pair[1].exclusive_area is not None]
    if not sized:
        return None
    group, info = min(
        sized,
        key=lambda pair: (
            abs(trunc(pair[1].exclusive_area or 0) - target), not pair[0].is_representative, -(pair[0].total_cnt or 0),
        ),
    )
    return supply, group, info


def _compared_area(area_m2: float) -> str:
    """안내에 적는 목표 면적. 고를 때 견준 값(웹처럼 정수로 버림, `_select_pyeong`)이다.

    예전에는 버리기 전 값(84.97㎡)을 적어 실제로 견준 84㎡ 와 달랐다 (2026-11-12 리뷰).
    """
    return f'{trunc(area_m2)}㎡' + ('(소수점 아래 버림)' if area_m2 != trunc(area_m2) else '')


def _compare_pyeong(column: DaangnCompareComplexModel, target_m2: float | None) -> DaangnComparePyeong | None:
    """고른 평형의 KB 시세와 최근 실거래. 평형 자료는 전용면적 묶음 쪽에 있어 평형 타입 코드로 찾는다 (웹 `ge`)."""
    selected = _select_pyeong(column, target_m2)
    danji = column.proptier_danji
    if selected is None or danji is None:
        return None
    supply, group, chosen = selected
    found = next(
        (
            (candidate, item) for candidate in danji.exclusive_area_groups for item in candidate.py_infos
            if chosen.ptp_cd is not None and item.ptp_cd == chosen.ptp_cd
        ),
        None,
    )
    if found is None:
        # 웹 `ge` 는 전용면적 묶음에서 평형 타입 코드를 못 찾으면 null 이라 평형 칸이 빈다. 공급 평 묶음 쪽 값으로 대신 채우지 않는다
        return None
    exclusive_group, info = found
    kb = next((edge.node for edge in info.kb_prices.edges if edge.node), None) if info.kb_prices else None
    borrows = [edge.node for edge in info.borrow_realsale.edges if edge.node] if info.borrow_realsale else []
    sale = next((edge.node for edge in info.sale_realsale.edges if edge.node), None) if info.sale_realsale else None
    return DaangnComparePyeong(
        pyeong=group.label if supply else None,
        area_group=exclusive_group.label,
        representative=bool(group.is_representative),
        type_name=chosen.ptp,
        households=chosen.ptp_tot_hseh_cnt,
        exclusive_area_m2=info.exclusive_area,
        supply_area_m2=info.supply_area,
        kb_sale=DaangnKbRange(
            low_manwon=kb.sale_lower_limit, mid_manwon=kb.sale_std_price, high_manwon=kb.sale_upper_limit,
        ) if kb and kb.sale_std_price else None,
        kb_jeonse=DaangnKbRange(
            low_manwon=kb.lease_lower_limit, mid_manwon=kb.lease_std_price, high_manwon=kb.lease_upper_limit,
        ) if kb and kb.lease_std_price else None,
        # 웹 `Ue` 는 KB 월세를 보증금과 월세 상한이 모두 있을 때만 보여 준다 (`c?.monthlyDeposit&&c?.monthlyUpperLimit`)
        kb_monthly=DaangnKbMonthly(
            deposit_manwon=kb.monthly_deposit, rent_low_manwon=kb.monthly_lower_limit, rent_high_manwon=kb.monthly_upper_limit,
        ) if kb and kb.monthly_deposit and kb.monthly_upper_limit else None,
        kb_survey_date=normalize_date(kb.survey_base_date) if kb else None,
        # 웹(compare `Ue`)처럼 매매는 첫 실거래(매매가가 있으면), 전세는 전월세 5건 중 월세 없는 첫 건, 월세는 월세 있는 첫 건이되
        # 보증금도 있어야 보여 준다 (`e?.deposit&&e.monthRentFee`. 보증금 0 인 월세는 웹이 비운다)
        recent_sale=_trade(sale if sale and sale.trade_price else None, '매매'),
        recent_jeonse=_trade(next((node for node in borrows if node.deposit and not node.month_rent_fee), None), '전세'),
        recent_monthly=_trade(next((node for node in borrows if (node.month_rent_fee or 0) > 0 and node.deposit), None), '월세'),
    )


def _comparison(complex_: DaangnCompareComplexModel, target_m2: float | None) -> DaangnComplexComparison:
    danji = complex_.proptier_danji
    building = next((edge.node for edge in complex_.buildings.edges if edge.node), None) if complex_.buildings else None
    # 웹(managementCost `g`)처럼 달이 1~12 로 읽히는 달만 평균 낸다. 숫자가 아닌 연월은 웹이 NaN 으로 읽어 건너뛰니 jibsa 도
    # 건너뛴다 (int 로 바꾸면 ValueError 로 비교 전체가 PARSE_ERROR 였다. 2026-11-12 리뷰. 같은 날 실측 14곳은 모두 6자리 숫자)
    costs = [
        cost for cost in (complex_.kapt.monthly_management_costs_per_square_meter if complex_.kapt else [])
        if cost.year_month and len(cost.year_month) == 6 and cost.year_month.isdecimal()
        and 1 <= int(cost.year_month[4:6]) <= 12 and cost.cost_per_square_meter is not None
    ]
    months = sorted(cost.year_month or '' for cost in costs)
    per_m2 = js_round(sum(cost.cost_per_square_meter or 0 for cost in costs) / len(costs)) if costs else None
    pyeong = _compare_pyeong(complex_, target_m2) if danji else None
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
        manage_cost_manwon=(
            round(per_m2 * pyeong.exclusive_area_m2 / 10000, 1)
            if per_m2 is not None and pyeong is not None and pyeong.exclusive_area_m2 else None
        ),
        manage_cost_per_m2_manwon=round(per_m2 / 10000, 4) if per_m2 is not None else None,
        manage_cost_period=f'{months[0][:4]}-{months[0][4:]}~{months[-1][:4]}-{months[-1][4:]}' if months else None,
        review_count=complex_.lived_review_count,
        # 단지 공공 정보가 없으면 학교·역·면적 묶음은 모른다 (null). `complex_to_summary` 와 같다.
        # 2026-10-11 실측: 화곡동·역삼동·이도2동의 소규모 아파트·오피스텔·도시형 15곳 모두 있었다
        schools=[
            DaangnCompareSchool(name=school.school.sch_nm if school.school else None, distance_m=school.distance, walk_minutes=school.working_time)
            for school in danji.assigned_schools
        ] if danji else None,
        subways=_subways(danji.subway_info) if danji else None,
        pyeong=pyeong,
        url=complex_url(complex_.original_id),
    )


def compare_column(client: DaangnClient, complex_id: int) -> DaangnCompareComplexModel:
    """단지 비교 칸 (`ComplexCompareColumnQuery`, 요청 1회, 약 78KB). 평형 묶음·평형 타입 코드·노드 ID 도 여기서 받는다.

    Raises:
        JibsaError: 없는 단지면 NOT_FOUND.
    """
    response = client.run_request_complex_compare(DaangnComplexCompareRequestPayloadModel(original_id=str(complex_id)))
    output = response.data.complex_by_original_id if response.data else None
    found = output.complex if output else None
    if found is None and not response.errors:
        raise complex_not_found(complex_id)
    return unwrap_graphql(response, found, '단지 비교')


class DaangnPyeongChoice(NamedTuple):
    """실거래·시세 그래프를 거를 평형. 공급 평형(아파트형)이면 평형 타입 코드를, 아니면 전용면적 묶음을 보낸다."""

    pyeong: int | None
    area_group: int | None
    ptp_cds: list[int] | None


def pyeong_groups(column: DaangnCompareComplexModel) -> tuple[bool, list[DaangnCompareAreaGroupModel]]:
    """단지의 평형 묶음과, 그것이 공급 평 묶음인지. 당근 웹처럼 아파트형 단지(아파트·주상복합·재개발)에 공급 평 묶음이 있으면
    그것으로, 아니면 전용면적 묶음으로 평형을 고른다 (utils `n()`, 2026-11-12 번들 대조)."""
    danji = column.proptier_danji
    if danji is None:
        return False, []
    supply = column.type in APARTMENT_COMPLEX_TYPES and bool(danji.supply_pyeong_area_groups)
    return supply, danji.supply_pyeong_area_groups if supply else danji.exclusive_area_groups


def _supply_choice(column: DaangnCompareComplexModel, group: DaangnCompareAreaGroupModel) -> DaangnPyeongChoice:
    """공급 평 묶음의 평형 타입 코드로 고른 평형.

    평형을 주지 않은 `price-trend` 의 대표 평형도 이 에러로 끝낸다. 모든 평형 평균으로 물러서는 길은 두지 않았다: 2026-11-12
    실측 아파트·주상복합 14곳의 공급 평 묶음에 모두 타입 코드가 있어 한 번도 돌지 않을 코드이고, 생기면 에러가 원인을 알린다
    (2026-11-12 리뷰에서 물러서라고 했으나 그대로 둔다).

    Raises:
        JibsaError: 묶음에 평형 타입 코드가 하나도 없을 때 (UPSTREAM_ERROR). 빈 코드로 보내면 평형을 거르지 않은 전체
            평형 값에 그 평형 이름이 붙는다 (2026-11-12 리뷰).
    """
    ptp_cds = [info.ptp_cd for info in group.py_infos if info.ptp_cd is not None]
    if not ptp_cds:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'당근 단지 {column.original_id} 의 {group.label}평 묶음에 평형 타입 코드가 없어 그 평형만 고를 수 없습니다',
            hint=f'응답 형식이 바뀌었을 수 있습니다. {UPDATE_MAYBE_NEEDED}',
        )
    return DaangnPyeongChoice(group.label, None, ptp_cds)


def choose_pyeong(
    column: DaangnCompareComplexModel,
    *,
    pyeong: int | None = None,
    area_group: int | None = None,
    representative: bool = False,
) -> DaangnPyeongChoice | None:
    """`--pyeong`·`--area` 로 평형을 고른다. 둘 다 없고 `representative` 면 웹처럼 대표 평형 묶음(없으면 첫 묶음)이다.

    None 이면 평형으로 거르지 않는다 (real-price 는 모든 평형의 거래, price-trend 는 웹처럼 그래프 없음). 평형 묶음이 없거나 대표
    묶음에 평형 값(`label`)이 없으면 고를 평형을 알 수 없어 None 이다. 예전에는 값 없는 평형을 골라 거르지 않으면서 '대표
    평형(None㎡)' 이라고 알렸다 (2026-11-12 리뷰. 실측 응답에서 label 이 빈 묶음은 아직 보지 못했다).

    Raises:
        JibsaError: 평형 묶음이 없는 단지에 `pyeong`·`area_group` 을, 아파트형이 아닌 단지에 `pyeong` 을, 아파트형(공급 평
            묶음) 단지에 `area_group` 을 주거나, 단지에 없는 평형·묶음이면 INVALID_ARGUMENT. 고른 공급 평 묶음에 평형 타입
            코드가 없으면 UPSTREAM_ERROR.
    """
    supply, groups = pyeong_groups(column)
    if (pyeong is not None or area_group is not None) and not any(group.label is not None for group in groups):
        # 고를 묶음이 없으면 아래 '있는 평형' 안내가 빈 목록이라 다시 줄 값이 없었다 (2026-11-12 리뷰). 웹도 평형 탭이 없어
        # 고를 수 없다. 옵션을 빼면 real-price 는 전체 평형이지만 price-trend 는 웹처럼 그래프가 없어 명령마다 알린다
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f'당근에 단지 {column.original_id} 의 평형 묶음 정보가 없어 평형을 고를 수 없습니다',
            hint='real-price 는 --pyeong·--area 를 빼면 모든 평형의 거래를 봅니다. price-trend 는 당근 웹처럼 이런 단지의 시세 그래프가 없습니다',
        )
    if pyeong is not None:
        if not supply:
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'아파트형이 아닌 단지 {column.original_id} 에는 공급 평형(--pyeong)이 없습니다',
                hint=f'jibsa daangn complex {column.original_id} 의 pyeongs[].area_group 을 --area 로 주세요',
            )
        group = next((group for group in groups if group.label == pyeong), None)
        if group is None:
            labels = ', '.join(f'{group.label}평' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'단지 {column.original_id} 에 {pyeong}평 묶음이 없습니다',
                hint=f'있는 평형: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].pyeong)',
            )
        return _supply_choice(column, group)
    if area_group is not None:
        if supply:
            # 웹은 공급 평 묶음이 있는 단지에서는 늘 평형 타입 코드(ptpCds)로만 묻고 전용면적 묶음을 섞지 않는다
            # (ComplexTopicPanel `jd` 의 `s`). 84㎡ 묶음은 32평·33평을 함께 가져 웹의 32평 목록과 달랐다 (2026-11-12 번들 대조)
            labels = ', '.join(f'{group.label}평' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'아파트형 단지 {column.original_id} 에서는 당근 웹처럼 공급 평형(--pyeong)으로만 고릅니다',
                hint=f'--area 대신 --pyeong 을 주세요. 있는 평형: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].pyeong)',
            )
        if all(group.label != area_group for group in groups):
            labels = ', '.join(f'{group.label}㎡' for group in groups if group.label is not None)
            raise JibsaError(
                code='INVALID_ARGUMENT',
                message=f'단지 {column.original_id} 에 전용 {area_group}㎡ 묶음이 없습니다',
                hint=f'있는 묶음: {labels} (jibsa daangn complex {column.original_id} 의 pyeongs[].area_group)',
            )
        return DaangnPyeongChoice(None, area_group, None)
    if not representative or not groups:
        return None
    chosen = next((group for group in groups if group.is_representative), groups[0])
    if chosen.label is None:
        return None
    if supply:
        return _supply_choice(column, chosen)
    return DaangnPyeongChoice(None, chosen.label, None)


def compare_complexes(client: DaangnClient, complex_ids: list[int], *, area_m2: float | None = None) -> DaangnCompareResult:
    """단지 여러 곳(최대 `COMPARE_MAX_COMPLEXES`)을 당근 웹 비교 화면처럼 나란히 본다 (단지마다 `complexByOriginalId` 1회).

    웹처럼 단지마다 평형 하나로 비교한다: 첫 단지는 대표 평형, 나머지는 첫 단지 평형의 전용면적과 가장 비슷한 평형이다. 그 평형의
    KB 시세와 최근 실거래(매매·전세·월세 따로), 평균 호가, 월 관리비 추정(받은 달 평균 ㎡당 관리비 × 전용면적)을 준다. 예전에는
    단지마다 모든 전용면적 묶음을 늘어놓고 호가는 최저~최고, 관리비는 최근 한 달 ㎡당 값이었다 (#215, 2026-11-12 번들 대조).
    웹은 매매·전세·월세를 탭으로 하나씩 보여 주지만 jibsa 는 한 번에 준다. `area_m2` 를 주면 모든 단지를 그 전용면적과 가장
    비슷한 평형으로 비교한다 (jibsa 개선, 2026-11-12 사용자 결정). 세대수·준공·주차·층, 배정 학교, 주변 역도 준다. 후기 요약
    글은 읽지 않는다 (후기 수만).

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 그 밖의 GraphQL 에러 (UPSTREAM_ERROR).
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    columns = [compare_column(client, complex_id) for complex_id in dict.fromkeys(complex_ids)]
    target = area_m2
    complexes: list[DaangnComplexComparison] = []
    for index, column in enumerate(columns):
        comparison = _comparison(column, target)
        complexes.append(comparison)
        # 웹은 첫 단지 평형의 전용면적(정수로 버림)을 나머지 단지의 목표로 쓴다 (compare `ut`). 첫 단지에 평형이 없으면 목표가 없어
        # 나머지도 대표 평형이다. 예전에는 평형이 있는 다음 단지의 면적을 목표로 이어 써, 셋째 단지부터 둘째 단지 면적으로 고르면서
        # 안내는 '대표 평형' 이라고 했다 (2026-11-12 리뷰)
        if index == 0 and target is None and comparison.pyeong is not None and comparison.pyeong.exclusive_area_m2:
            target = comparison.pyeong.exclusive_area_m2
    first = complexes[0].pyeong if complexes else None
    basis = (
        f'전용 {_compared_area(area_m2)}와 가장 비슷한 평형' if area_m2 is not None
        else f'첫 단지는 대표 평형, 나머지는 그 전용면적 {_compared_area(first.exclusive_area_m2)}와 가장 비슷한 평형'
        if first and first.exclusive_area_m2 else '단지마다 대표 평형'
    )
    return DaangnCompareResult(
        returned=len(complexes),
        complexes=complexes,
        notes=[
            # 단지 전체가 아니라 웹 기본값대로 평형 하나씩 본 것이라 [범위] 다. --area 로 크기를 골랐으면 고른 대로라 [참고] 다
            note(
                '참고' if area_m2 is not None else '범위',
                f'당근 웹 비교처럼 단지마다 평형 하나로 비교합니다 ({basis}). 다른 크기로 비교하려면 --area <전용 ㎡> 를 주세요',
            ),
            note(
                '참고',
                'asking 은 당근에 올라온 아파트 매물 앞 30건의 거래 유형별 평균 호가입니다 (0원 제외, 월세는 보증금 평균). '
                '실제 거래가는 pyeong 의 recent_sale·recent_jeonse·recent_monthly 를 보세요',
            ),
        ],
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
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (매매·전세·월세)')
    ]


class DaangnNearbyComplexesResult(BaseModel):
    """같은 동 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='기준 단지 ID')]
    region: Annotated[DaangnRegion, Field(description='기준 단지가 있는 동')]
    total: Annotated[int, Field(description='기준 단지를 뺀 같은 동 단지 수 (limit 적용 전). 1200곳에서 잘리면 notes 로 알린다')]
    returned: Annotated[int, Field(description='반환한 단지 수')]
    sort: Annotated[str, Field(description="정렬. 늘 '세대수' (많은 순. jibsa 정렬이며 웹 검색 엔진용 본문은 단지 ID 순 10곳이다)")]
    complexes: Annotated[list[DaangnNearbyComplex], Field(description='세대수 많은 순 단지')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='조회 한도 안내. CLI 가 결과 위에 붙인다')
    ] = []


def list_nearby_complexes(client: DaangnClient, complex_id: int, *, limit: int = 50) -> DaangnNearbyComplexesResult:
    """기준 단지와 같은 동의 다른 단지를 세대수 많은 순으로 (요청 3회: 단지의 동 → 동 단지 → 단지 카드).

    당근 웹 단지 화면에서 이 칸은 '함께 본 단지' 추천(실험 기능)으로 바뀌었고, 같은 동 단지 목록(`ComplexNearbySectionQuery`)은
    단지 페이지의 검색 엔진용 본문에만 남았다 (2026-11-12 번들 대조). 그 본문(ComplexTopicPanel `to`)은 300곳을 받아 기타 유형
    (ETC)과 기준 단지를 빼고 단지 ID 순으로 세운 뒤 기준 단지 ID 앞뒤에서 번갈아 10곳만 링크로 쓴다. 사용자가 보는 화면이 없는
    자료라 jibsa 는 웹에 남은 쿼리로 같은 동 단지를 모두 주고 세대수 순으로 세운다 (2026-11-12 사용자 결정, 웹과 다른 범위·정렬.
    기타 유형 제외는 웹과 같다). 동 ID 는 단지 페이지 쿼리(`ComplexIdSeoQuery`)에서 받고, 카드는 지도 단지 목록 카드
    (`ComplexListPanelMapPinsQuery`)다. 예전에는 동을 이름으로 다시 찾고(요청 1회 더, 다른 동으로 바뀔 수 있었다) 웹에서 사라진
    카드 쿼리를 썼다 (#215). 동 단지는 `NEARBY_COMPLEXES_MAX` 곳까지 한 번에 받고 (페이지 정보가 없다), 그만큼 받았으면 더 있을
    수 있다고 `notes` 로 알린다. 단지 카드도 ID 를 한 번에 보낸다.

    Raises:
        JibsaError: 없는 단지 (NOT_FOUND), 동을 모르는 단지 (REGION_NOT_FOUND), 그 밖의 GraphQL 에러.
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    region_response = client.run_request_complex_region(DaangnComplexRegionRequestPayloadModel(complex_id=str(complex_id)))
    output = unwrap_graphql(
        region_response, region_response.data.complex_by_original_id if region_response.data else None, '단지 지역'
    )
    if output.complex is None:
        raise complex_not_found(complex_id)
    dong = output.complex.region
    # 웹도 기타 유형(ETC)이거나 동을 모르는 단지는 같은 동 단지를 부르지 않는다. 이 쿼리도 region.depth 를 준다 (2026-11-12 실측:
    # 헬리오시티 → 가락동 depth 3. 리뷰가 depth 가 늘 None 이라 모든 단지가 실패한다고 했으나 오탐)
    if dong is None or dong.original_id is None or dong.depth != 3 or output.complex.type == 'ETC':
        raise RegionNotFoundError(f'단지 {complex_id} 의 동', hint='jibsa daangn search complexes <동 이름> 으로 찾으세요')
    region = DaangnRegion(name1=dong.name1 or '', name2=dong.name2 or '', name3=dong.name3 or '', region_id=dong.original_id)
    response = client.run_request_nearby_complexes(
        DaangnNearbyComplexesRequestPayloadModel(region3_id=region.region_id, first=NEARBY_COMPLEXES_MAX)
    )
    nodes = unwrap_graphql(response, response.data.complexes if response.data else None, '같은 동 단지')
    # 더 있을 수 있다는 안내라 [일부] 다. 지금은 가장 큰 동도 상한에 닿지 않지만 (2026-11-10 실측: 화곡동 705곳) 동이 커지면
    # 나온다 (2026-11-10 리뷰: 태그가 없어 [참고] 로 나갈 뻔했다). 동 이름 뒤 '로도' 는 '화곡동 로도' 처럼 틀려 '명령으로'
    # 로 조사를 고정한다 (particle 은 ㄹ 받침 예외로 '으로/로' 를 받지 않는다)
    capped_notes = (
        [note(
            '일부',
            f'당근에서 같은 동 단지를 {NEARBY_COMPLEXES_MAX}곳까지만 받아 더 있을 수 있습니다. '
            f'나머지는 jibsa daangn search complexes {region.name3} 명령으로 찾아보세요',
        )]
        if len(nodes.edges) >= NEARBY_COMPLEXES_MAX else []
    )
    # 웹 `to` 처럼 기준 단지와 기타 유형(ETC) 단지는 뺀다
    ids = [
        edge.node.original_id for edge in nodes.edges
        if edge.node and edge.node.original_id != str(complex_id) and edge.node.type != 'ETC'
    ]
    cards: list[DaangnComplexCardModel] = []
    # 웹(300곳)보다 많아도 한 번에 보낸다 (2026-11-12 실측: 화곡동 강서힐스테이트 → 705곳 카드가 한 번에 모두 왔다. 리뷰가 서버가
    # 목록을 자를 수 있다고 했으나 오탐)
    if ids:
        cards_response = client.run_request_complexes_by_original_complex_ids(
            DaangnComplexesByOriginalComplexIdsRequestPayloadModel(original_ids=ids)
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
            listing_counts={
                '매매': card.live_article_count.buy if card.live_article_count else None,
                '전세': card.live_article_count.borrow if card.live_article_count else None,
                '월세': card.live_article_count.month if card.live_article_count else None,
            },
        )
        for card in cards
    ]
    nearby.sort(key=lambda item: (item.households is None, -(item.households or 0)))
    return DaangnNearbyComplexesResult(
        complex_id=str(complex_id),
        region=region,
        total=len(nearby),
        returned=min(len(nearby), limit),
        sort='세대수',
        complexes=nearby[:limit],
        notes=capped_notes + truncation_notes(len(nearby), limit, subject='단지', unit='곳', max_limit=NEARBY_COMPLEXES_MAX),
    )
