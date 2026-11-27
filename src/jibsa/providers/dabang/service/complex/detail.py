"""단지 정보 (complex)."""
from jibsa.core.listing import (
    lookup_failure_note,
    m2_to_pyeong,
    normalize_address,
    note,
    number_range,
    read_date,
    won_to_manwon,
)
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.api.models.request.complex.common import (
    DabangComplexCategory,
)
from jibsa.providers.dabang.api.models.request.complex.detail import (
    DabangComplexLoanCalcConditionV5RequestParameterModel,
    DabangComplexSummaryV5RequestParameterModel,
)
from jibsa.providers.dabang.api.models.response.common import (
    DabangComplexChildcareModel,
    DabangComplexSchoolModel,
    DabangComplexSpaceModel,
)
from jibsa.providers.dabang.api.models.response.complex.detail import (
    DabangLatelyPriceModel,
)
from jibsa.providers.dabang.service.common.complex import (
    area_price,
    fetch_complex,
    first_space_notes,
    primary_space_of,
)
from jibsa.providers.dabang.service.common.constants import (
    COMPLEX_KIND_BY_TYPE,
    COMPLEX_URL,
    OPTIONAL_LOOKUP_ERRORS,
    SchoolLevel,
)
from jibsa.providers.dabang.service.common.text import (
    contract_date,
    count_of,
    floor_label,
    manwon_from_text,
    number_of,
)
from jibsa.providers.dabang.service.complex.common import category_of
from jibsa.providers.dabang.service.complex.constants import (
    AREA_MATCH_TOLERANCE_M2,
    KINDER_ESTABLISHMENT_LABELS,
    NEAREST_SCHOOLS,
    NURSERY_ESTABLISHMENT_LABELS,
)
from jibsa.providers.dabang.service.complex.models import (
    DabangChildcare,
    DabangComplexDetail,
    DabangComplexSchool,
    DabangPyeong,
    DabangRecentTrade,
    RecentAreaKey,
)

from typing import Literal


def _school(school: DabangComplexSchoolModel, level: SchoolLevel) -> DabangComplexSchool:
    return DabangComplexSchool(
        level=level,
        school_code=school.code,
        name=school.name,
        establishment=school.establish_divide,
        distance_m=school.distance,
        district=school.hakgudo_name,
        students_per_class=count_of(school.avg_students_per_class),
        special_high_entrants=count_of(school.total_enter_special_high_school),
        autonomous_high_entrants=count_of(school.total_enter_autonomous_high_school),
        university_entrants=count_of(school.enter_university),
    )


def _childcare(facility: DabangComplexChildcareModel) -> DabangChildcare:
    # 어린이집은 `type`, 유치원은 `establishDivide` 에 설립 유형이 온다
    if facility.type:
        establishment: str | None = NURSERY_ESTABLISHMENT_LABELS.get(facility.type, facility.type)
    elif facility.establish_divide:
        establishment = KINDER_ESTABLISHMENT_LABELS.get(facility.establish_divide, facility.establish_divide)
    else:
        establishment = None
    return DabangChildcare(
        school_code=facility.code,
        name=facility.name,
        establishment=establishment,
        distance_m=facility.distance,
        children_per_teacher=number_of(facility.child_per_teacher),
    )


def _recent(
    trade: DabangLatelyPriceModel | None,
    spaces: list[DabangComplexSpaceModel] | None,
    category: DabangComplexCategory,
    label: Literal['매매', '전세'],
) -> tuple[DabangRecentTrade | None, list[str]]:
    """단지 요약의 최근 거래와 안내. 요약 면적은 전용이 아니라 아파트는 공급면적, 오피스텔은 계약면적이고 평형 번호가 없다
    (2026-10-26 실측: 은마 매매 115.54㎡ = 34평 공급, 전용 84.43㎡ / 역삼SK허브블루 매매 55.19㎡ = 16평 계약, 전용 30.06㎡).

    웹 요약은 면적만 보여 주므로 그 면적을 그대로 내고, 평형표에서 그 면적인 평형이 하나뿐일 때만 평형 ID·전용면적을 붙인다.
    공급면적이 같은 평형이 여럿인 단지가 있어 고르지 않는다 (2026-11-13 실측: 삼호1차 82.08㎡ 는 3526(24A)·286028(24C)).
    다방이 평형 목록을 주지 않으면(`spaces` 가 None) 맞출 평형이 없어 평형 ID·전용면적이 null 이다. '평형 없음' 같은 안내는
    쓰지 않는다 (모르는 것이라 pyeongs 가 null 이고, 이 두 칸은 원래 맞는 평형이 하나가 아니면 null 이다).
    """
    if trade is None or trade.format_price is None:
        return None, []
    size = number_of(trade.format_room_size)
    matches = [
        space for space in spaces or []
        if size is not None and any(
            value is not None and abs(value - size) < AREA_MATCH_TOLERANCE_M2 for value in (space.supply_space, space.contract_space)
        )
    ]
    space = matches[0] if len(matches) == 1 else None
    notes: list[str] = []
    if len(matches) > 1:
        candidates = ', '.join(f'{match.space_seq}({match.pyeong_type})' if match.pyeong_type else str(match.space_seq) for match in matches)
        # 고르지 않고 비운 것이라 '하나를 골랐다' 는 뜻의 [모호] 가 아니라 [참고] 로 알린다 (output-contract.md 의 꼬리표)
        notes.append(note(
            '참고',
            f'최근 {label} 거래의 면적 {size:g}㎡ 인 평형이 여럿이라 pyeong_id·area_m2 를 null 로 두었습니다. 후보 평형: {candidates}',
        ))
    area_key: RecentAreaKey = 'contract_area_m2' if category == 'officetel' else 'supply_area_m2'
    amount = manwon_from_text(trade.format_price)
    return DabangRecentTrade(
        price_manwon=amount if label == '매매' else None,
        deposit_manwon=amount if label == '전세' else None,
        trade_date=contract_date(trade.format_contract_date, '최근 실거래 계약일'),
        floor=floor_label(trade.format_floor),
        supply_area_m2=size if area_key == 'supply_area_m2' else None,
        contract_area_m2=size if area_key == 'contract_area_m2' else None,
        pyeong_id=space.space_seq if space else None,
        area_m2=space.room_space if space else None,
        area_key=area_key,
        trade_type=label,
    ), notes


def _floor_int(value: str | None) -> int | None:
    return int(value) if value and value.isdecimal() else None


def get_complex(client: DabangClient, complex_id: str) -> DabangComplexDetail:
    """단지 정보 (요청 3회: 단지 상세 + 최근 실거래 요약 + 대출 계산 조건). 사진·관리사무소 전화·광고 중개사는 옮기지 않는다.

    최근 실거래 요약과 대출 계산 조건은 덤이라 실패해도 단지 정보는 돌려주고 latest_trades 의 sale·jeonse·overheated_district 를
    모름(null)으로 둔다.
    """
    result = fetch_complex(client, complex_id)
    info = result.complex
    category = category_of(result)
    notes: list[str] = []
    try:
        summary = client.run_request_complex_summary_v5(
            DabangComplexSummaryV5RequestParameterModel(complex_type=category, complex_id=complex_id)
        ).result
    except OPTIONAL_LOOKUP_ERRORS as exc:
        summary = None
        notes.append(lookup_failure_note(exc, '다방', '최근 실거래 요약', 'latest_trades 의 sale·jeonse 는 모름(null)입니다. 실거래는 real-price 로 보세요'))
    # 웹 단지 화면이 단지 상세 바로 뒤에 부르는 대출 계산 조건이다 (complex 청크 `je`). 금리는 다방 계산기 기본값이라 내지 않는다
    try:
        loan = client.run_request_complex_loan_calc_condition_v5(
            DabangComplexLoanCalcConditionV5RequestParameterModel(complex_id=complex_id)
        ).result
    except OPTIONAL_LOOKUP_ERRORS as exc:
        loan = None
        notes.append(lookup_failure_note(exc, '다방', '대출 계산 조건', 'overheated_district 는 모름(null)입니다'))
    else:
        # 요청은 성공했는데 result 나 is_overheated_district 를 주지 않은 경우 (예외일 때의 안내와 겹치지 않게 else)
        if loan is None or loan.is_overheated_district is None:
            notes.append(note('실패', '다방이 대출 계산 조건 값을 주지 않아 overheated_district 는 모름(null)입니다'))
    education = result.education
    schools = nurseries = kindergartens = None
    if education is not None:
        # 중·고등학교는 거리순으로 온다 (2026-10-25 실측: 은마 중 17곳·고 22곳, 오피스텔 중 7곳·고 22곳). 목록이 null 로 오면
        # 그 목록은 모름이다 (단지 38곳 실측에서는 늘 목록이었고 없으면 [] 였다, 2026-11-14)
        levels: tuple[tuple[SchoolLevel, list[DabangComplexSchoolModel] | None, int | None], ...] = (
            ('초등학교', education.elementary_school, None),
            ('중학교', education.middle_school, NEAREST_SCHOOLS),
            ('고등학교', education.high_school, NEAREST_SCHOOLS),
        )
        if any(rows is not None for _, rows, _ in levels):
            schools = [_school(school, level) for level, rows, count in levels for school in (rows or [])[:count]]
            # 다른 학교급은 목록인데 null 로 온 학교급은 schools 에 빠져 '그 학교급 없음' 처럼 보여 모름이라고 알린다
            notes += [
                note('참고', f'다방이 {level} 목록을 주지 않아 schools 에 {level}가 없습니다 (없다는 뜻이 아니라 모름)')
                for level, rows, _ in levels if rows is None
            ]
        if education.nursery_school is not None:
            nurseries = [_childcare(facility) for facility in education.nursery_school[:NEAREST_SCHOOLS]]
        if education.kinder_school is not None:
            kindergartens = [_childcare(facility) for facility in education.kinder_school[:NEAREST_SCHOOLS]]
    recent_sale, sale_notes = _recent(summary.sell_lately_price if summary else None, result.spaces, category, '매매')
    recent_lease, lease_notes = _recent(summary.lease_lately_price if summary else None, result.spaces, category, '전세')
    approved = info.building_approval_date_name
    primary = primary_space_of(result)
    lowest_floor = _floor_int(info.complex_lowest_floor)
    highest_floor = _floor_int(info.complex_highest_floor)
    return DabangComplexDetail(
        complex_id=info.complex_id,
        name=info.complex_name,
        complex_type=info.complex_type_name or COMPLEX_KIND_BY_TYPE.get(info.complex_type or ''),
        address=normalize_address(info.jibun_address or info.address),
        road_address=normalize_address(info.road_address),
        household_count=info.household_num,
        dong_count=info.building_num,
        parking_count=info.parking_num,
        parking_per_household=info.parking_average,
        building_floor_range=number_range(lowest_floor, highest_floor),
        floor_area_ratio_percent=info.floor_area_ratio,
        building_coverage_ratio_percent=info.building_coverage_ratio,
        construction_company=info.provider_name,
        approved_date=read_date(approved, '사용승인일') if approved else None,
        heating=info.heat_type_name,
        heating_fuel=info.fuel_type_name,
        entrance=info.entrance_type_name,
        listing_count=result.room_count,
        recent_trade_count=info.recent_deal_count,
        tags=info.hash_tags,
        pyeongs=None if result.spaces is None else [
            DabangPyeong(
                pyeong_id=space.space_seq,
                name=space.pyeong_type,
                area_m2=space.room_space,
                area_pyeong=m2_to_pyeong(space.room_space),
                supply_area_m2=space.supply_space,
                contract_area_m2=space.contract_space,
                room_count=space.beds_num,
                bathroom_count=space.bath_num,
                manage_cost_manwon=won_to_manwon(space.maintenance_total_price),
            )
            for space in result.spaces
        ],
        representative_pyeong_id=primary[0] if primary else None,
        area_prices=None if result.area_average_price is None else [area_price(price) for price in result.area_average_price],
        latest_trades={'sale': recent_sale, 'jeonse': recent_lease},
        overheated_district=loan.is_overheated_district if loan else None,
        schools=schools,
        nurseries=nurseries,
        kindergartens=kindergartens,
        url=COMPLEX_URL.format(info.complex_id),
        notes=notes + sale_notes + lease_notes + first_space_notes(result),
    )
