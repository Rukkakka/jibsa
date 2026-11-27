"""단지 비교 (compare)."""

from math import trunc

from jibsa.core.dates import read_date
from jibsa.core.listing import (
    floor_text,
    js_round,
    normalize_address,
    number_range,
)
from jibsa.core.notes import (
    note,
    null_items_note,
)
from jibsa.providers.daangn.api.client import DaangnClient
from jibsa.providers.daangn.api.models.response.compare.common import (
    DaangnCompareAreaGroupModel,
    DaangnCompareComplexModel,
    DaangnComparePyInfoModel,
    DaangnCompareRealsaleConnectionModel,
    DaangnCompareRealsaleModel,
    DaangnCompareSubwayModel,
)
from jibsa.providers.daangn.service.common.complex import (
    compare_column,
    is_year_month,
    most_households,
    pyeong_groups,
    pyeong_null_items,
)
from jibsa.providers.daangn.service.common.constants import (
    COMPLEX_TYPE_LABELS,
    COMPLEX_URL,
)
from jibsa.providers.daangn.service.common.response import code_label
from jibsa.providers.daangn.service.compare.models.complexes import (
    DaangnAskingAverage,
    DaangnCompareEstimatedPrices,
    DaangnComparePyeong,
    DaangnCompareRecentTrade,
    DaangnCompareResult,
    DaangnCompareSchool,
    DaangnCompareSubway,
    DaangnComplexComparison,
    DaangnKbMonthly,
    DaangnKbRange,
)

from typing import Literal


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
        url=COMPLEX_URL.format(complex_.original_id),
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
