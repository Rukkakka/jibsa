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
    AmountSet,
    NumberRange,
    floor_text,
    join_address,
    js_round,
    normalize_address,
    note,
    null_items_note,
    number_range,
    read_date,
    with_floor_number,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.request.compare import (
    DaangnComplexesByOriginalComplexIdsRequestPayloadModel,
    DaangnComplexRegionRequestPayloadModel,
    DaangnNearbyComplexesRequestPayloadModel,
)
from jibsa.providers.daangn.api.response.compare import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
    DaangnComparePyInfoModel,
    DaangnCompareRealsaleConnectionModel,
    DaangnCompareRealsaleModel,
    DaangnCompareSubwayModel,
    DaangnComplexCardModel,
)
from jibsa.providers.daangn.service.common import (
    COMPLEX_TYPE_LABELS,
    DaangnKbEstimatedPrices,
    DaangnRegion,
    code_label,
    compare_column,
    complex_not_found,
    complex_url,
    is_year_month,
    most_households,
    pyeong_groups,
    pyeong_null_items,
    truncation_notes,
    unwrap_graphql,
)

from typing import (
    Annotated,
    Any,
    Literal,
)


class DaangnAskingAverage(AmountSet):
    """호가 매물의 평균 금액 (만원). 금액 칸은 거래에 맞는 것 하나다 (매매 `price_manwon`, 전세·월세 `deposit_manwon`)."""

    count: Annotated[int, Field(description='평균을 낸 거래 조건 수')]


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
        float | None,
        Field(description='거리 (m, 당근 값 그대로. 소수일 수 있다)')
    ] = None
    walk_minutes: Annotated[
        float | None,
        Field(description='도보 (분, 당근 값 그대로. 소수일 수 있다)')
    ] = None


class DaangnCompareSubway(BaseModel):
    """주변 역."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[str, Field(description="역 이름 ('역' 까지)")]
    line: Annotated[
        str | None,
        Field(description='노선 (예: 2호선)')
    ] = None
    distance_m: Annotated[
        float | None,
        Field(description='거리 (m, 당근 값 그대로. 소수일 수 있다)')
    ] = None
    walk_minutes: Annotated[
        float | None,
        Field(description='도보 (분, 당근 값 그대로. 소수일 수 있다)')
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


class DaangnCompareEstimatedPrices(DaangnKbEstimatedPrices):
    """KB 시세 (출처 `provider`, 기준일 `base_date`). 거래 칸(sale·jeonse·wolse)이 키이고, 그 거래의 시세가 없으면 null 이다."""

    sale: Annotated[
        DaangnKbRange | None,
        Field(description='KB 매매 시세')
    ] = None
    jeonse: Annotated[
        DaangnKbRange | None,
        Field(description='KB 전세 시세')
    ] = None
    wolse: Annotated[
        DaangnKbMonthly | None,
        Field(description='KB 월세 시세')
    ] = None


class DaangnCompareRecentTrade(BaseModel):
    """평형 최근 실거래 하나 (만원). 거래 유형에 없는 금액은 키를 뺀다 (해당 없음: 매매는 보증금·월세, 전세는 매매가·월세, 월세는 매매가)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        str | None,
        Field(description="층 (예: '3', '지하1'). 숫자는 floor_number")
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
        return with_floor_number(data)


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
    household_count: Annotated[
        int | None,
        Field(description='이 평형 세대수')
    ] = None
    area_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    supply_area_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡)')
    ] = None
    estimated_prices: Annotated[
        DaangnCompareEstimatedPrices | None,
        Field(description='KB 시세. 세 거래와 기준일이 모두 없으면 null, 아니면 sale·jeonse·wolse 키를 늘 두고 시세가 없는 거래는 null')
    ] = None
    latest_trades: Annotated[
        dict[str, DaangnCompareRecentTrade | None],
        Field(description=(
            '이 평형의 거래별 최근 실거래 (sale·jeonse·wolse). 최근 실거래가 없는 거래는 키가 없고, 세 거래 모두 없으면 {}. '
            '당근이 실거래 칸이나 그 목록을 주지 않거나 목록에 빈 항목이 섞이면 있는지 몰라 그 거래 키가 null, 빈 목록이면 키 없음'
        ))
    ]

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
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소 (첫 건물)')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소 (첫 건물)')
    ] = None
    approved_date: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    building_floor_range: Annotated[
        NumberRange | None,
        Field(description='동 꼭대기 층수의 최소(lowest)·최대(highest). 모르면 null')
    ] = None
    listing_count: Annotated[
        int | None,
        Field(description='현재 매물 수')
    ] = None
    asking_averages: Annotated[
        dict[str, DaangnAskingAverage],
        Field(description=(
            "현재 호가 매물(아파트 매물 앞 30건)의 거래별 평균 (당근 웹 비교 화면의 '평균 호가'). 거래 키(sale·jeonse·wolse)이고 월세는 웹처럼 보증금 평균이다. "
            '매물이 없는 거래는 키가 없고 세 거래 모두 없으면 {}'
        ))
    ] = {}
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
    stations: Annotated[
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


def _asking_averages(complex_: DaangnCompareComplexModel) -> dict[str, DaangnAskingAverage]:
    """호가 매물 거래 조건을 매매·전세·월세로 나눠 평균을 낸다 (당근 웹 비교 화면 `je`). 매물 하나에 거래 조건이 여럿이면 각각 센다.

    웹처럼 거래 종류(`__typename`)로 나누고 0원은 뺀다. 매매는 매매가, 전세는 전세금, 월세는 보증금 평균이다 (월세액이 아니다).
    단기임대는 세지 않는다. 매물이 없는 거래는 키를 넣지 않는다. 예전에는 최저~최고 범위였고 0원도 셌으며 월세는 월세액이었다 (#215,
    2026-11-12 번들 대조).
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
    averages: dict[str, DaangnAskingAverage] = {}
    # 웹(compare `je`)은 Math.round 로 만원 정수를 보여 주지만 jibsa 는 원 단위(만원 소수 넷째 자리)까지 낸다
    if sale:
        averages['sale'] = DaangnAskingAverage(price_manwon=round(sum(sale) / len(sale), 4), count=len(sale))
    if jeonse:
        averages['jeonse'] = DaangnAskingAverage(deposit_manwon=round(sum(jeonse) / len(jeonse), 4), count=len(jeonse))
    if deposit:
        averages['wolse'] = DaangnAskingAverage(deposit_manwon=round(sum(deposit) / len(deposit), 4), count=len(deposit))
    return averages


def _subways(rows: list[DaangnCompareSubwayModel]) -> list[DaangnCompareSubway]:
    """역마다 거리·도보 두 줄로 오는 것을 한 줄로 합친다. 값은 웹처럼 당근 값 그대로 낸다 (반올림·최소 1분 없음)."""
    merged: dict[tuple[str, str | None], DaangnCompareSubway] = {}
    for row in rows:
        if not row.station_nm:
            continue
        key = (row.station_nm, row.simple_line_nm)
        subway = merged.setdefault(key, DaangnCompareSubway(name=f'{row.station_nm}역', line=row.simple_line_nm))
        value = row.data_value
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
        trade_date=read_date(node.contact_date, '최근 실거래 계약일'),
        floor=floor_text(node.floor),
        price_manwon=node.trade_price if trade_type == '매매' else None,
        deposit_manwon=None if trade_type == '매매' else node.deposit,
        rent_manwon=node.month_rent_fee if trade_type == '월세' else None,
        trade_type=trade_type,
    )


def _select_pyeong(
    column: DaangnCompareComplexModel, target_m2: float | None,
) -> tuple[bool, DaangnCompareAreaGroupModel, DaangnComparePyInfoModel] | None:
    """비교할 평형을 웹 비교 화면(`ve`·`_e`)처럼 고른다: 목표 면적이 없으면 대표 묶음(없으면 첫 묶음), 있으면 묶음마다 세대수가
    가장 많은 평형의 전용면적 정수가 목표와 가장 가까운 묶음 (같으면 대표 묶음, 그다음 세대수 많은 묶음). 그 묶음에서 세대수가
    가장 많은 평형이다."""
    supply, groups = pyeong_groups(column)
    # 대표 묶음은 평형이 있는 묶음 중에서 고른다. 인기 급상승 단지(`list_trending_complexes`)는 웹 식이 달라 평형이 없는 묶음까지
    # 포함한 묶음 전체에서 대표 묶음을 고른다 (합치지 않는다)
    # 묶음마다 세대수가 가장 많은 평형 (웹 compare 의 `$`)
    tops = [
        (group, info) for group in groups
        if (info := most_households(group.py_infos, lambda py_info: py_info.ptp_tot_hseh_cnt)) is not None
    ]
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


def _blank_trades(connection: DaangnCompareRealsaleConnectionModel | None) -> int:
    """실거래 연결에서 빈 항목(null 원소, node 가 null 인 항목) 수. 연결이나 목록이 null 이면 0 이다 (그 경우는 호출부가 모름으로 본다)."""
    if connection is None:
        return 0
    return connection.null_items('edges') + sum(1 for edge in connection.edges or [] if edge.node is None)


def _compare_pyeong(column: DaangnCompareComplexModel, target_m2: float | None, notes: list[str]) -> DaangnComparePyeong | None:
    """고른 평형의 KB 시세와 최근 실거래. 평형 자료는 전용면적 묶음 쪽에 있어 평형 타입 코드로 찾는다 (웹 `ge`).

    실거래에 빈 항목이 있어 모름이 된 거래가 있으면 `notes` 에 안내를 붙인다.
    """
    selected = _select_pyeong(column, target_m2)
    danji = column.proptier_danji
    if selected is None or danji is None:
        return None
    supply, group, chosen = selected
    # 리뷰 오탐 (2026-11-19): 웹 compare 의 ge 도 평형 코드가 null 이면 바로 null 이라 칸을 비운다 (번들 compare-C6ozJ7Nu.js 대조)
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
    borrows = [edge.node for edge in info.borrow_realsale.edges if edge.node] if info.borrow_realsale and info.borrow_realsale.edges else []
    sale = next((edge.node for edge in info.sale_realsale.edges if edge.node), None) if info.sale_realsale and info.sale_realsale.edges else None
    # 실거래 칸이나 그 목록(edges)이 null 이거나 목록에 빈 항목이 있으면 최근 실거래가 있는지 모른다. 그 거래 키를 두고 null 이다
    # (빈 목록 [] 만 해당 없음). 전월세 5건은 빈 항목이 고른 거래보다 앞에 있었는지 위치를 알 수 없어(빈 원소는 위치 없이 빠진다)
    # 빈 항목이 하나라도 있으면 전세·월세 모두 모른다
    sale_blank = _blank_trades(info.sale_realsale)
    borrow_blank = _blank_trades(info.borrow_realsale)
    blank_unknown = ({'sale'} if sale_blank else set()) | ({'jeonse', 'wolse'} if borrow_blank else set())
    unknown = (
        blank_unknown
        | ({'sale'} if info.sale_realsale is None or info.sale_realsale.edges is None else set())
        | ({'jeonse', 'wolse'} if info.borrow_realsale is None or info.borrow_realsale.edges is None else set())
    )
    if blank_unknown:
        notes.append(null_items_note(
            f'당근 단지 비교 {column.name} 최근 실거래' if column.name else '당근 단지 비교 최근 실거래',
            sale_blank + borrow_blank,
            tuple(f'pyeong.latest_trades 의 {trade}' for trade in ('sale', 'jeonse', 'wolse') if trade in blank_unknown),
        ))
    kb_sale = DaangnKbRange(
        low_manwon=kb.sale_lower_limit, mid_manwon=kb.sale_std_price, high_manwon=kb.sale_upper_limit,
    ) if kb and kb.sale_std_price else None
    kb_jeonse = DaangnKbRange(
        low_manwon=kb.lease_lower_limit, mid_manwon=kb.lease_std_price, high_manwon=kb.lease_upper_limit,
    ) if kb and kb.lease_std_price else None
    # 웹 `Ue` 는 KB 월세를 보증금과 월세 상한이 모두 있을 때만 보여 준다 (`c?.monthlyDeposit&&c?.monthlyUpperLimit`)
    kb_monthly = DaangnKbMonthly(
        deposit_manwon=kb.monthly_deposit, rent_low_manwon=kb.monthly_lower_limit, rent_high_manwon=kb.monthly_upper_limit,
    ) if kb and kb.monthly_deposit and kb.monthly_upper_limit else None
    kb_base_date = read_date(kb.survey_base_date, 'KB 시세 기준일') if kb else None
    return DaangnComparePyeong(
        pyeong=group.label if supply else None,
        area_group=exclusive_group.label,
        representative=bool(group.is_representative),
        type_name=chosen.ptp,
        household_count=chosen.ptp_tot_hseh_cnt,
        area_m2=info.exclusive_area,
        supply_area_m2=info.supply_area,
        # 세 거래와 기준일이 모두 없으면 KB 시세를 모른다 (null). 하나라도 있으면 시세가 없는 거래만 null 이다
        estimated_prices=DaangnCompareEstimatedPrices(
            base_date=kb_base_date, sale=kb_sale, jeonse=kb_jeonse, wolse=kb_monthly,
        ) if any(value is not None for value in (kb_sale, kb_jeonse, kb_monthly, kb_base_date)) else None,
        # 웹(compare `Ue`)처럼 매매는 첫 실거래(매매가가 있으면), 전세는 전월세 5건 중 월세 없는 첫 건, 월세는 월세 있는 첫 건이되
        # 보증금도 있어야 보여 준다 (`e?.deposit&&e.monthRentFee`. 보증금 0 인 월세는 웹이 비운다)
        # 최근 실거래가 없는 거래는 해당 없음이라 키를 뺀다 (호가 평균 asking_averages 의 매물 0건 거래와 같다, 2026-11-25 사용자 결정).
        # 모르면(연결·목록이 null 이거나 빈 항목이 있으면) 키를 두고 null 이다. 빈 항목 뒤의 더 오래된 거래를 최근 거래로 내지 않는다
        latest_trades={trade: None if trade in unknown else found for trade, found in (
            ('sale', _trade(sale if sale and sale.trade_price else None, '매매')),
            ('jeonse', _trade(next((node for node in borrows if node.deposit and not node.month_rent_fee), None), '전세')),
            ('wolse', _trade(next((node for node in borrows if (node.month_rent_fee or 0) > 0 and node.deposit), None), '월세')),
        ) if found is not None or trade in unknown},
    )


def _comparison(complex_: DaangnCompareComplexModel, target_m2: float | None, notes: list[str]) -> DaangnComplexComparison:
    danji = complex_.proptier_danji
    building = next((edge.node for edge in complex_.buildings.edges if edge.node), None) if complex_.buildings else None
    # 웹(managementCost `g`·`_`)처럼 달이 1~12 로 읽히는 달만 평균 낸다. 숫자가 아닌 연월은 웹이 NaN 으로 읽어 건너뛰니 jibsa 도
    # 건너뛴다 (int 로 바꾸면 ValueError 로 비교 전체가 PARSE_ERROR 였다. 2026-11-12 리뷰. 같은 날 실측 14곳은 모두 6자리 숫자).
    # ㎡당 관리비가 null 인 달은 빼지 않는다. 웹은 연월의 달이 1~12 면 값이 null 이어도 배열에 넣고 `reduce((e,t)=>e+t,0)` 로 더해
    # (JS 에서 null 은 0) 개수로 나눠 `Math.round` 하므로, null 인 달은 0 으로 더하고 개수에도 센다. 모든 달이 null 이면 합 0 / 개수
    # 로 0 이다 (웹도 '0원'). 실측(2026-11-20, 단지 5곳 57달)에는 null 이 없었지만 서버가 줄 수 있는 값이라 웹 식에 맞춘다
    costs = [
        cost for cost in (complex_.kapt.monthly_management_costs_per_square_meter if complex_.kapt else [])
        if is_year_month(cost.year_month)
    ]
    months = sorted(cost.year_month or '' for cost in costs)
    per_m2 = js_round(sum(cost.cost_per_square_meter or 0 for cost in costs) / len(costs)) if costs else None
    pyeong = _compare_pyeong(complex_, target_m2, notes) if danji else None
    return DaangnComplexComparison(
        complex_id=complex_.original_id,
        name=complex_.name,
        complex_type=code_label(COMPLEX_TYPE_LABELS, complex_.type),
        address=normalize_address(building.jibun_address) if building else None,
        road_address=normalize_address(building.road_address) if building else None,
        approved_date=read_date(danji.build_date, '사용승인일') if danji else None,
        dong_count=danji.tot_dong_cnt if danji else None,
        household_count=danji.total_tot_hseh_cnt if danji else None,
        parking_per_household=danji.hseh_parking_cnt if danji else None,
        building_floor_range=number_range(danji.min_floor, danji.max_floor) if danji else None,
        listing_count=complex_.live_article_count.total if complex_.live_article_count else None,
        asking_averages=_asking_averages(complex_),
        # 리뷰 오탐 (2026-11-19, 근거 고침 2026-11-20): 원 단위까지 내는 값이다 (AGENTS.md 금액 규칙). 웹 표시(managementCost `v`)는
        # 1만원 이상이면 `Math.round(e/1e4)` 만원 정수, 그 아래는 `Math.round(e)` 원이라 jibsa 값과 소수 아래가 다르다. 이 차이는
        # 개발 가이드 daangn.md 의 '웹과 다른 점' 절(관리비 항목)에 적는다 (단지 비교 설명은 같은 가이드 '단지·실거래' 절)
        manage_cost_manwon=(
            round(per_m2 * pyeong.area_m2 / 10000, 4)
            if per_m2 is not None and pyeong is not None and pyeong.area_m2 else None
        ),
        manage_cost_per_m2_manwon=round(per_m2 / 10000, 4) if per_m2 is not None else None,
        manage_cost_period=f'{months[0][:4]}-{months[0][4:]}~{months[-1][:4]}-{months[-1][4:]}' if months else None,
        review_count=complex_.lived_review_count,
        # 단지 공공 정보가 없으면 학교·역·면적 묶음은 모른다 (null). `complex_to_summary` 와 같다.
        # 2026-10-11 실측: 화곡동·역삼동·이도2동의 소규모 아파트·오피스텔·도시형 15곳 모두 있었다
        schools=[
            DaangnCompareSchool(
                name=school.school.sch_nm if school.school else None,
                distance_m=school.distance,
                walk_minutes=school.working_time,
            )
            for school in danji.assigned_schools
        ] if danji else None,
        stations=_subways(danji.subway_info) if danji else None,
        pyeong=pyeong,
        url=complex_url(complex_.original_id),
    )


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
    trade_notes: list[str] = []
    for index, column in enumerate(columns):
        comparison = _comparison(column, target, trade_notes)
        complexes.append(comparison)
        # 웹은 첫 단지 평형의 전용면적(정수로 버림)을 나머지 단지의 목표로 쓴다 (compare `ut`). 첫 단지에 평형이 없으면 목표가 없어
        # 나머지도 대표 평형이다. 예전에는 평형이 있는 다음 단지의 면적을 목표로 이어 써, 셋째 단지부터 둘째 단지 면적으로 고르면서
        # 안내는 '대표 평형' 이라고 했다 (2026-11-12 리뷰)
        if index == 0 and target is None and comparison.pyeong is not None and comparison.pyeong.area_m2:
            target = comparison.pyeong.area_m2
    first = complexes[0].pyeong if complexes else None
    dropped = sum(pyeong_null_items(column) for column in columns)
    basis = (
        f'전용 {_compared_area(area_m2)}와 가장 비슷한 평형' if area_m2 is not None
        else f'첫 단지는 대표 평형, 나머지는 그 전용면적 {_compared_area(first.area_m2)}와 가장 비슷한 평형'
        if first and first.area_m2 else '단지마다 대표 평형'
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
                'asking_averages 는 당근에 올라온 아파트 매물 앞 30건의 거래 유형별 평균 호가입니다 (0원 제외, 월세는 보증금 평균). '
                '실제 거래가는 pyeong 의 latest_trades 를 보세요',
            ),
        ] + ([null_items_note('당근 대표 평형 후보', dropped)] if dropped else []) + trade_notes,
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
    complex_type: Annotated[
        str | None,
        Field(description='아파트 / 오피스텔 / 주상복합 ...')
    ] = None
    household_count: Annotated[
        int | None,
        Field(description='세대수')
    ] = None
    listing_counts: Annotated[
        dict[str, int | None],
        Field(description='당근에 올라온 거래 유형별 현재 매물 수 (sale·jeonse·wolse)')
    ]


class DaangnNearbyComplexesResult(BaseModel):
    """같은 동 단지 목록."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_id: Annotated[str, Field(description='기준 단지 ID')]
    region: Annotated[DaangnRegion, Field(description='기준 단지가 있는 동')]
    total: Annotated[
        int | None,
        Field(description='기준 단지를 뺀 같은 동 단지 수 (limit 적용 전). 1200곳에서 잘리면 notes 로 알린다. 당근이 빈 항목을 줘 셀 수 없으면 null')
    ]
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
        JibsaError: 없는 단지 (NOT_FOUND), 동을 모르는 단지 (REGION_NOT_FOUND), 기타 유형 단지 (INVALID_ARGUMENT), 그 밖의 GraphQL 에러.
        FeedQueryRejectedError: 쿼리 해시가 거절됐을 때.
    """
    region_response = client.run_request_complex_region(DaangnComplexRegionRequestPayloadModel(complex_id=str(complex_id)))
    outer = region_response.data.complex_by_original_id if region_response.data else None
    # 바깥이 null 인 것도 안의 단지가 null 인 것과 같은 없는 단지다 (`compare_column` 과 같다). GraphQL errors 가 있으면 그 에러가 먼저다
    if outer is None and not region_response.errors:
        raise complex_not_found(complex_id)
    output = unwrap_graphql(region_response, outer, '단지 지역', conditions=False)
    if output.complex is None:
        raise complex_not_found(complex_id)
    dong = output.complex.region
    # 웹도 기타 유형(ETC)이거나 동을 모르는 단지는 같은 동 단지를 부르지 않는다. 이 쿼리도 region.depth 를 준다 (2026-11-12 실측:
    # 헬리오시티 → 가락동 depth 3. 리뷰가 depth 가 늘 None 이라 모든 단지가 실패한다고 했으나 오탐)
    if dong is None or dong.original_id is None or dong.depth != 3 or not dong.name3:
        raise RegionNotFoundError(f'단지 {complex_id} 의 동', hint='jibsa daangn search complexes <동 이름> 으로 찾으세요')
    full_name = join_address(dong.name1, dong.name2, dong.name3)
    if output.complex.type == 'ETC':
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=(
                f'단지 {complex_id} 의 유형이 기타라 같은 동 단지 목록이 없습니다 (당근 웹도 기타 유형 단지에는 같은 동 단지를 보여 주지 않습니다)'
            ),
            hint=f"그 동의 단지는 jibsa daangn search complexes '{full_name}' 으로 찾으세요",
        )
    region = DaangnRegion(sido=dong.name1 or '', sigungu=dong.name2 or '', dong=dong.name3 or '', region_id=dong.original_id)
    response = client.run_request_nearby_complexes(
        DaangnNearbyComplexesRequestPayloadModel(region3_id=region.region_id, first=NEARBY_COMPLEXES_MAX)
    )
    nodes = unwrap_graphql(response, response.data.complexes if response.data else None, '같은 동 단지', conditions=False)
    # 서버는 빈 edge(null)도 한 자리로 세어 `NEARBY_COMPLEXES_MAX` 까지 준다. 빼고 읽은 수를 받은 자리에 더한다
    null_edges = nodes.null_items('edges')
    # 더 있을 수 있다는 안내라 [일부] 다. 지금은 가장 큰 동도 상한에 닿지 않지만 (2026-11-10 실측: 화곡동 705곳) 동이 커지면
    # 나온다 (2026-11-10 리뷰: 태그가 없어 [참고] 로 나갈 뻔했다). 동 이름은 같은 이름의 동이 REGION_AMBIGUOUS 가 되지 않게
    # 시·구·동 전체 이름을 작은따옴표로 감싸고 조사는 '명령에' 로 고정한다. `search complexes` 도 `--limit` 최대가 같은 1200 이라
    # 나머지를 받으려면 조건으로 좁혀야 한다
    capped_notes = (
        [note(
            '일부',
            f'당근에서 같은 동 단지를 {NEARBY_COMPLEXES_MAX}곳까지만 받아 더 있을 수 있습니다. '
            f"나머지는 jibsa daangn search complexes '{join_address(region.sido, region.sigungu, region.dong)}' 명령에 조건"
            '(--type·--trade·가격·--area-min/--area-max·세대수 등)을 줘 좁혀 찾으세요',
        )]
        if len(nodes.edges) + null_edges >= NEARBY_COMPLEXES_MAX else []
    )
    # 웹 `to` 처럼 기준 단지와 기타 유형(ETC) 단지는 뺀다
    ids = [
        edge.node.original_id for edge in nodes.edges
        if edge.node and edge.node.original_id != str(complex_id) and edge.node.type != 'ETC'
    ]
    cards: list[DaangnComplexCardModel] = []
    null_cards = 0
    # 웹(300곳)보다 많아도 한 번에 보낸다 (리뷰 오탐 2026-11-12, 근거 고침 2026-11-20. 실측(2026-11-20): 서로 다른 단지 ID 1097개를
    # 보내 카드 1097개가 모두 왔고, 중복 ID 로 채운 1250개도 모두 왔다. ID 수는 `first=1200` 으로 막혀 서버가 자를 일이 없다.
    # 2026-11-12 에는 화곡동 강서힐스테이트 705곳이 한 번에 모두 왔다)
    if ids:
        cards_response = client.run_request_complexes_by_original_complex_ids(
            DaangnComplexesByOriginalComplexIdsRequestPayloadModel(original_ids=ids)
        )
        cards = unwrap_graphql(
            cards_response,
            cards_response.data.complexes_by_original_complex_ids if cards_response.data else None,
            '단지 카드',
            conditions=False,
        )
        # 단지 카드 목록에서 빈 항목을 뺐으면 같은 동 단지 수를 알 수 없다 (null)
        null_cards = cards_response.data.null_items('complexes_by_original_complex_ids') if cards_response.data else 0
    nearby = [
        DaangnNearbyComplex(
            complex_id=card.original_id,
            name=card.name,
            complex_type=code_label(COMPLEX_TYPE_LABELS, card.type),
            household_count=card.proptier_danji.total_tot_hseh_cnt if card.proptier_danji else None,
            listing_counts={
                'sale': card.live_article_count.buy if card.live_article_count else None,
                'jeonse': card.live_article_count.borrow if card.live_article_count else None,
                'wolse': card.live_article_count.month if card.live_article_count else None,
            },
        )
        for card in cards
    ]
    nearby.sort(key=lambda item: (item.household_count is None, -(item.household_count or 0)))
    null_notes = [
        null_items_note(what, count, unknown)
        for what, count, unknown in (('당근 같은 동 단지', null_edges, ()), ('당근 단지 카드', null_cards, ('total',)))
        if count
    ]
    return DaangnNearbyComplexesResult(
        complex_id=str(complex_id),
        region=region,
        total=None if null_cards else len(nearby),
        returned=min(len(nearby), limit),
        sort='세대수',
        complexes=nearby[:limit],
        notes=capped_notes + truncation_notes(len(nearby), limit, subject='단지', unit='곳', max_limit=NEARBY_COMPLEXES_MAX) + null_notes,
    )
