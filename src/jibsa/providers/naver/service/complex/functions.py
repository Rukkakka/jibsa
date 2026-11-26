"""단지 요약·평형·평형 묶음·관리비·시세·실거래 요약·평당가의 조회·변환 함수. 모델은 같은 폴더의 models 에 있다."""

from datetime import date

from jibsa.core.listing import (
    floor_text,
    holding_unread_dates,
    join_address,
    keep_unread_dates,
    m2_to_pyeong,
    months_ago,
    normalize_address,
    normalize_date,
    read_date,
    read_month,
    won_to_manwon,
    years_ago,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexPyeongGroupsV1RequestParameterModel,
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.complex import (
    NaverComplexArticleStatsV1RequestParameterModel,
    NaverComplexMaintenanceFeeV1RequestParameterModel,
    NaverComplexMarketPriceRecentV1RequestParameterModel,
    NaverComplexPyeongPricePyeongTypeV1RequestParameterModel,
    NaverComplexPyeongRealPriceSummaryV1RequestParameterModel,
    NaverComplexReconstructionV1RequestParameterModel,
    NaverComplexVillaArticleStatsV1RequestParameterModel,
    NaverEducationComplexSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import NaverPyeongModel
from jibsa.providers.naver.api.response.complex import (
    NaverComplexPyeongPriceModel,
    NaverRealPriceSummaryModel,
    NaverRealPriceSummaryTradeModel,
)
from jibsa.providers.naver.service.common.functions import (
    MARKET_PRICE_PROVIDER_NAMES,
    OFFICETEL_CODE,
    TRADE_NAME_BY_CODE,
    assigned_schools,
    complex_row_fields,
    complex_url,
    group_pyeong_numbers,
    kst_today,
    market_price_fields,
    pyeong_list,
    raise_missing_pyeongs,
    resolve_dong_numbers,
    result_or_empty,
    result_or_none,
    unwrap,
    villa_by_complex_response,
)
from jibsa.providers.naver.service.complex.models import (
    NaverComplexMaintenanceFee,
    NaverComplexSummary,
    NaverMarketPrice,
    NaverPricePerPyeong,
    NaverPricePerPyeongRegion,
    NaverPyeong,
    NaverPyeongGroup,
    NaverRealPriceExtreme,
    NaverRealPriceRange,
    NaverRealPriceSummary,
    NaverRealPriceTradeSummary,
    NaverReconstruction,
    NaverReconstructionStep,
)

from typing import (
    Any,
    Literal,
)


# 평당가(complex/pyeongPrice/pyeongType)를 묻는 단지 유형: 아파트 A01·오피스텔 A02·재건축 A04·아파트분양권 B01·오피스텔분양권 B02.
# 단지형 빌라(A05~A07)는 웹이 이 박스를 쓰는지 몰라 묻지 않는다. 웹 단지 화면 ComplexAreaPrice 는 pricePerPyeong 이 없으면
# 박스를 그리지 않는다 (2026-11-18 번들 청크 b042d8aace_1okty1145x932)
PRICE_PER_PYEONG_COMPLEX_TYPES: frozenset[str] = frozenset({'A01', 'A02', 'A04', 'B01', 'B02'})


# 평당가를 묻는 거래 유형. 출력 키 → 요청 값 (월세(B2)는 서버가 pricePerPyeong 키 없이 빈 목록을 줘 묻지 않는다, 2026-11-18 확인)
PRICE_PER_PYEONG_TRADE_TYPES: dict[str, Literal['A1', 'B1']] = {'sale': 'A1', 'jeonse': 'B1'}


# 평당가 지역 단위 (서버 legalDivisionLevelType)
PRICE_PER_PYEONG_LEVEL_LABELS: dict[str, str] = {'SI': '시·도', 'GUN': '시·군·구', 'EUP': '읍·면·동'}


# 실거래 요약 기간. 웹 단지 화면 실거래 요약(ComplexTransactionPriceSummary)과 같다. 비면 5년
REAL_PRICE_SUMMARY_YEARS: int = 3


REAL_PRICE_SUMMARY_FALLBACK_YEARS: int = 5


# 요약에 덧붙이는 최근 평균 기간 (웹 매물 상세 RecentTransaction 의 '3개월 평균 실거래' 와 같은 요청)
REAL_PRICE_RECENT_MONTHS: int = 3

# 재건축 단지 유형. 이 유형이면 사업 단계를 함께 묻는다
RECONSTRUCTION_CODE: str = 'A04'


RECONSTRUCTION_STEP_LABELS: dict[str, str] = {
    '01': '기본계획수립', '02': '안전진단', '03': '구역지정', '04': '추진위승인', '05': '조합설립인가',
    '06': '사업시행인가', '07': '관리처분인가', '08': '이주 및 철거', '09': '착공 및 분양', '10': '준공', '11': '이전고지',
}


"""재건축 사업 단계 코드 (사이트 COMPLEX_RECONSTRUCTION_STEP, 2026-10-10 확인)."""


def _pyeong(pyeong: NaverPyeongModel, is_officetel: bool = False) -> NaverPyeong:
    supply = pyeong.supply_area
    if is_officetel and supply is not None and supply == pyeong.contract_area:
        # 오피스텔 공급면적은 계약면적보다 작다. 같으면 네이버가 공급 칸에 계약면적을 채운 것이라
        # (예: 공급 30.59 / 계약 30.59) 공급면적으로 내보내면 틀린 값이 되므로 모름으로 둔다.
        # 매물 상세가 오피스텔 공급면적을 None 으로 두는 것과 맞춘다.
        supply = None
    return NaverPyeong(
        pyeong_id=pyeong.number,
        name=pyeong.name,
        area_m2=pyeong.exclusive_area,
        area_pyeong=m2_to_pyeong(pyeong.exclusive_area),
        supply_area_m2=supply,
        contract_area_m2=pyeong.contract_area,
        room_count=pyeong.room_count,
        bathroom_count=pyeong.bath_room_count,
        household_count=pyeong.household_count,
    )


def _reconstruction(client: NaverClient, complex_number: int, notes: list[str]) -> NaverReconstruction | None:
    """재건축 단지의 사업 진행 (1회 호출). 조회가 실패하면 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다."""
    result = result_or_none(lambda: client.run_request_complex_reconstruction_v1(
        NaverComplexReconstructionV1RequestParameterModel(complex_number=complex_number)
    ), notes=notes, what='재건축 정보', unknown='모름(null)으로 낸 칸: reconstruction')
    if result is None:
        return None
    current = result.current_business_step

    def label(code: str | None) -> str | None:
        return None if not code else RECONSTRUCTION_STEP_LABELS.get(code, code)

    return NaverReconstruction(
        current_step=label(current.step_type) if current else None,
        current_step_date=read_date(current.implementation_date, '재건축 현재 단계 날짜') if current else None,
        construction_company=result.construction_company or None,
        planned_household_count=result.household_count,
        planned_floor_area_ratio_percent=result.building_area_to_land_ratio,
        # 날짜가 없는 단계(없음·빈 글자·'-')는 아직 거치지 않은 단계라 뺀다. 날짜가 있는데 읽지 못하면(연월만 등) 단계는 남기고
        # date 는 모름(null)이다 (current_step_date 와 같다, 2026-11-24 리뷰)
        steps=[
            NaverReconstructionStep(step=label(step.step_type), date=read_date(step.implementation_date, '재건축 단계 날짜'))
            for step in result.business_steps
            if step.step_type and normalize_date(step.implementation_date) is not None
        ],
    )


def _pyeong_groups(client: NaverClient, complex_number: int, notes: list[str]) -> list[NaverPyeongGroup] | None:
    """평형 묶음 (1회 호출). 네이버가 묶음을 주지 않으면(빈 목록이거나 성공인데 `result` 가 null) [], 조회가 실패하면 모름(None).

    `real-price --group` 의 `_find_pyeong_group` 도 성공인데 `result` 가 null 인 응답을 빈 목록과 같게 읽는다. 묶음의 평형 목록을 주지 않으면
    (`pyeongTypes` null) 그 묶음만 `pyeong_ids` 가 모름(None)이다. 조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다.
    """
    groups = result_or_empty(lambda: client.run_request_complex_pyeong_groups_v1(
        NaverComplexPyeongGroupsV1RequestParameterModel(complex_number=complex_number)
    ), list, notes=notes, what='평형 묶음', unknown='모름(null)으로 낸 칸: pyeong_groups')
    if groups is None:
        return None
    return [
        NaverPyeongGroup(
            name=group.representative_pyeong_name,
            representative_pyeong_id=group.representative_pyeong_number,
            household_count=group.household_count,
            pyeong_ids=group_pyeong_numbers(group),
        )
        for group in groups
    ]


def get_complex(
    client: NaverClient,
    complex_number: int,
    *,
    pyeong_numbers: list[int] | None = None,
    dong_names: list[str] | None = None,
    villa: bool | None = None,
    today: date | None = None,
) -> NaverComplexSummary:
    """단지 정보·매물 수·호가 범위·평형·배정 초등학교·평형 묶음을 한 번에 모은다 (아파트 단지 5회, 빌라 단지는 종류를 모르면 5회·알면 4회).

    재건축(A04) 단지는 사업 단계·시공사·계획 세대수를 1회 더 물어 `reconstruction` 으로 붙인다.
    평형 묶음(`pyeong_groups`)은 `--pyeong` 과 상관없이 1회 물어 붙인다 (웹은 단지형 빌라에서 부르지 않아 빌라 단지는 묻지 않고 키가 없다).

    단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 성공 응답에 빈 결과를 주므로,
    그때 빌라 단지 엔드포인트로 다시 묻는다. 빌라 단지에는 동 수·건설사·방 수가 없다.

    Args:
        pyeong_numbers: 평형 번호. 주면 매물 수·호가 범위를 그 평형 매물로만 센다. 평형 목록에 없으면 NOT_FOUND.
        dong_names: 동 이름 ('104', '104동'). 주면 매물 수·호가 범위를 그 동 매물로만 센다 (동 목록 조회 1회 추가).
        villa: 빌라 단지인지 (`resolve_complex_number` 결과). 알면 빌라 단지는 아파트 단지 정보를 묻지 않는다 (1회 절약).
        today: 실거래 요약 기간(3년 전 오늘부터)의 기준일. Defaults to 오늘(한국 시간).

    평형을 하나만 주면 그 평형의 관리비·최신 시세·최근 3년 매매/전세 실거래 요약·평당가를 더 붙인다 (`_pyeong_details`: 관리비 1 + 시세 1 + 매매·전세 각 1~2 +
    평당가 매매·전세 각 1 = 최대 8회).
    빌라 단지는 네이버가 관리비·시세·실거래 요약을 주지 않아(모두 빈 결과, 2026-10-09 확인) 묻지 않고 notes 로 알린다. 평당가도
    웹이 빌라 단지에서 쓰는지 몰라 묻지 않는다 (`PRICE_PER_PYEONG_COMPLEX_TYPES`).
    """
    response = None
    if villa is None:
        response = client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number))
        villa = villa_by_complex_response(response)
    if villa:
        complex_ = unwrap(
            client.run_request_complex_villa_v1(NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)),
            '단지',
        )
    else:
        complex_ = unwrap(
            response or client.run_request_complex_v1(NaverComplexV1RequestParameterModel(complex_number=complex_number)),
            '단지',
        )
    pyeongs = pyeong_list(client, complex_number, villa)
    # 평형 번호가 틀리면 서버는 0건을 줘 매물이 없는 것처럼 보이므로 먼저 막는다
    raise_missing_pyeongs(complex_number, pyeong_numbers, pyeongs)
    dong_numbers = resolve_dong_numbers(client, complex_number, dong_names, villa=villa)[0] if dong_names else []
    stats_filter = {'pyeong_types': list(dict.fromkeys(pyeong_numbers or [])), 'dong_numbers': dong_numbers}
    if villa:
        stats = unwrap(
            client.run_request_complex_villa_article_stats_v1(
                NaverComplexVillaArticleStatsV1RequestParameterModel(complex_number=complex_number, **stats_filter)
            ),
            '매물 통계',
        )
    else:
        stats = unwrap(
            client.run_request_complex_article_stats_v1(
                NaverComplexArticleStatsV1RequestParameterModel(complex_number=complex_number, **stats_filter)
            ),
            '매물 통계',
        )
    counts, prices = stats.count, stats.price
    notes: list[str] = []
    # 단지형 빌라는 villa 로 물어야 한다 (complex 로 물으면 빈 목록, 2026-10-10 확인)
    schools = result_or_none(lambda: client.run_request_education_complex_school_v1(
        NaverEducationComplexSchoolV1RequestParameterModel(
            complex_number=complex_number, item_type='villa' if villa else 'complex',
        )
    ), notes=notes, what='배정 학교', unknown='모름(null)으로 낸 칸: schools')

    is_reconstruction = not villa and complex_.type == RECONSTRUCTION_CODE
    reconstruction = _reconstruction(client, complex_number, notes) if is_reconstruction else None
    # 웹은 단지형 빌라에서 평형 묶음을 부르지 않는다 (`!isVilla`)
    pyeong_groups = None if villa else _pyeong_groups(client, complex_number, notes)

    pyeong_details: dict[str, Any] = {}
    unique_pyeongs = list(dict.fromkeys(pyeong_numbers or []))
    if villa and unique_pyeongs:
        notes.append('빌라 단지는 네이버가 평형 관리비·시세·실거래 요약을 주지 않습니다. 실거래는 naver real-price 로 보세요')
    elif len(unique_pyeongs) == 1:
        # 단지 유형이 빈 글자로 오면 유형을 모르는 것이다 (시세·평당가가 같은 판정으로 None 을 모름으로 읽는다)
        pyeong_details = _pyeong_details(
            client, complex_number, unique_pyeongs[0], complex_.type or None, today or kst_today(), notes,
        )
    elif len(unique_pyeongs) > 1:
        notes.append('평형 관리비·시세·실거래 요약·평당가는 --pyeong 을 하나만 줄 때 붙습니다')

    address = complex_.address
    summary = NaverComplexSummary(
        complex_id=complex_number,
        name=complex_.name,
        address=normalize_address(
            join_address(address.city, address.division, address.sector, address.jibun)
        ) if address else None,
        road_address=normalize_address(
            join_address(address.city, address.division, address.road_name)
        ) if address and address.road_name else None,
        construction_company=complex_.construction_company,
        parking_per_household=complex_.parking_info.parking_count_per_household if complex_.parking_info else None,
        floor_area_ratio_percent=complex_.building_ratio_info.floor_area_ratio if complex_.building_ratio_info else None,
        pyeongs=[_pyeong(pyeong, complex_.type == OFFICETEL_CODE) for pyeong in pyeongs],
        pyeong_groups=pyeong_groups,
        schools=None if schools is None else assigned_schools(schools, notes),
        reconstruction=reconstruction,
        url=complex_url(complex_number),
        notes=notes,
        **complex_row_fields(
            type_code=complex_.type,
            households=complex_.total_household_number,
            dong_count=complex_.dong_count,
            use_approval_date=complex_.use_approval_date,
            counts=counts,
            prices=prices,
        ),
        **pyeong_details,
    )
    summary._pyeong_scoped = bool(pyeong_details)
    summary._price_per_pyeong_scoped = 'asking_price_per_pyeong' in pyeong_details
    summary._reconstruction_scoped = is_reconstruction
    summary._pyeong_groups_scoped = not villa
    return summary


def _real_price_extreme(trade: NaverRealPriceSummaryTradeModel | None, jeonse: bool) -> NaverRealPriceExtreme | None:
    if trade is None:
        return None
    # 전세는 보증금을 deposit_manwon 에, 매매는 매매가를 price_manwon 에 담는다 (넘기지 않은 쪽은 키가 없다)
    amount = {'deposit_manwon': won_to_manwon(trade.deposit)} if jeonse else {'price_manwon': won_to_manwon(trade.deal_price)}
    return NaverRealPriceExtreme(
        **amount,
        trade_date=read_date(trade.trade_date, '최저·최고 실거래 계약일'),
        floor=floor_text(trade.floor),
        deal_type=trade.trade_category or None,
        cancelled=trade.is_delete,
    )


def _real_price_trade_summary(summary: NaverRealPriceSummaryModel | None, jeonse: bool) -> NaverRealPriceTradeSummary | None:
    """거래가 없으면 서버가 빈 객체를 줘 None 이다."""
    if summary is None or (summary.avg_price is None and summary.min_price is None and summary.max_price is None):
        return None
    lowest = _real_price_extreme(summary.min_price, jeonse)
    highest = _real_price_extreme(summary.max_price, jeonse)
    return NaverRealPriceTradeSummary(
        average_manwon=won_to_manwon(summary.avg_price),
        # 두 거래를 모두 모르면 범위가 없어 null
        trade_range=None if lowest is None and highest is None else NaverRealPriceRange(lowest=lowest, highest=highest),
    )


def _price_per_pyeong(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    real_estate_type: str | None,
    notes: list[str],
) -> dict[str, NaverPricePerPyeong | None] | None:
    """평형의 매매·전세 평당 호가와 시·구·동 평균 (거래 유형마다 1회, 2회 호출).

    단지 유형을 모르면(None) 묻지 않고 None (모름). 서버가 빈 글자로 줘도 부르는 쪽이 None 으로 바꿔 넘긴다. 단지 유형이
    `PRICE_PER_PYEONG_COMPLEX_TYPES` 가 아니면(빌라 등, 해당 없음) 부르는 쪽(`_pyeong_details`)이 이 함수를 부르지 않고 키를 둔다.
    거래 유형마다 조회가 실패하면 그 값만 None(모름)이고, 네이버가 평당가를 주지 않으면(`pricePerPyeong` 이 없거나 0, 성공인데 `result` 가
    null) 그 거래 유형의 키를 뺀다. 조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다.
    """
    if real_estate_type is None:
        return None
    prices: dict[str, NaverPricePerPyeong | None] = {}
    for key, trade_type in PRICE_PER_PYEONG_TRADE_TYPES.items():
        # 성공인데 result 가 null 이면 빈 객체(월세처럼 평당가를 주지 않음)와 같게 읽어 그 거래 유형의 키를 뺀다. 조회 실패만 None(모름)이다
        result = result_or_empty(lambda: client.run_request_complex_pyeong_price_pyeong_type_v1(
            NaverComplexPyeongPricePyeongTypeV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type,
            )
        ), NaverComplexPyeongPriceModel, notes=notes, what=f'{TRADE_NAME_BY_CODE[trade_type]} 평당 호가',
            unknown=f'모름(null)으로 낸 칸: asking_price_per_pyeong.{key}')
        if result is None:
            # 조회 실패(모름)다. 평당가가 없는 것(키 삭제)과 섞지 않는다
            prices[key] = None
        elif result.price_per_pyeong:
            # 서버 목록은 큰 단위부터(서울시·송파구·가락동)라 웹 막대 순서(동·구·시)로 뒤집는다. 목록을 주지 않으면(null)
            # 평당가는 그대로 내고 지역·기준일만 모름(None)이다
            regions = None if result.legal_division_price_per_pyeong_list is None else list(reversed(result.legal_division_price_per_pyeong_list))
            texts = [region.first_day_of_week for region in regions or []]
            with holding_unread_dates() as held:
                days = [read_date(text, '평당 호가 기준일') for text in texts]
            # 날짜가 있는데 못 읽은 지역이 있으면 가장 늦은 날을 알 수 없어 기준일을 모름으로 둔다. 지역 항목에는 날짜 칸이 없고
            # null 이 되는 칸은 거래마다 기준일 하나라 처음 못 읽은 글자 하나만 [참고] 로 알린다
            unreadable = any(day is None and normalize_date(text) is not None for text, day in zip(texts, days))
            if unreadable:
                keep_unread_dates(held[:1])
            readable = [day for day in days if day]
            prices[key] = NaverPricePerPyeong(
                price_per_pyeong_manwon=won_to_manwon(result.price_per_pyeong),
                base_date=None if unreadable or not readable else max(readable),
                regions=None if regions is None else [
                    NaverPricePerPyeongRegion(
                        name=region.legal_division_name,
                        level=None if not region.legal_division_level_type else PRICE_PER_PYEONG_LEVEL_LABELS.get(region.legal_division_level_type, region.legal_division_level_type),
                        # 평당가 0 은 없음으로 본다 (시세 평균·범위와 같은 규칙)
                        price_per_pyeong_manwon=won_to_manwon(region.price_per_pyeong) if region.price_per_pyeong else None,
                    )
                    for region in regions
                ],
            )
    return prices


def _pyeong_details(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    real_estate_type: str | None,
    today: date,
    notes: list[str],
) -> dict[str, Any]:
    """평형의 관리비·최신 시세·최근 3년(비면 5년) 매매/전세 실거래 요약과 3개월 평균·평당가.

    요청은 관리비 1 + 시세 1(단지 유형이 있을 때) + 매매·전세 실거래 각 1~2 + 평당가 매매·전세 각 1(단지 유형이 `PRICE_PER_PYEONG_COMPLEX_TYPES` 일 때)
    = 최대 8회, 단지 유형이 없으면 3~5회다. 조회가 실패하면 그 값만 None. 단지 유형이 `PRICE_PER_PYEONG_COMPLEX_TYPES` 가 아닌 값이면
    (빌라 등) 평당가는 해당 없음이라 `asking_price_per_pyeong` 키를 이 결과에 넣지 않고, 단지 유형을 모르면 요청 없이 `asking_price_per_pyeong` 이 None(모름)이다.
    조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다 (같은 안내는 한 번만).

    Args:
        real_estate_type: 단지 유형 코드. 모르면 None. 서버가 빈 글자로 줘도 None 으로 넘긴다 (시세와 평당가 두 판정이 같은 값을 보게
            호출부 `get_complex` 가 `complex_.type or None` 으로 바꾼다).
    """
    fee = result_or_none(lambda: client.run_request_complex_maintenance_fee_v1(
        NaverComplexMaintenanceFeeV1RequestParameterModel(complex_number=complex_number, pyeong_type_number=pyeong_number)
    ), notes=notes, what='평형 관리비', unknown='모름(null)으로 낸 칸: pyeong_manage_cost')
    # 단지 유형은 늘 온다 (아파트·오피스텔·빌라 6곳). 시세가 없으면 서버가 [] 를 줘 그대로 [] 이고,
    # None 은 조회 실패(모름)일 때뿐이다 (2026-10-09 확인)
    market = None
    if real_estate_type is not None:
        market = result_or_none(lambda: client.run_request_complex_market_price_recent_v1(
            NaverComplexMarketPriceRecentV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, real_estate_type=real_estate_type,
            )
        ), notes=notes, what='시세', unknown='모름(null)으로 낸 칸: estimated_prices')
    since = years_ago(today, REAL_PRICE_SUMMARY_YEARS)

    def real_price_summary(trade_type: str, start_date: str, *, average_3m: bool = False) -> NaverRealPriceSummaryModel | None:
        # 3년·5년 요약 조회가 실패하면 요약 칸 전체가, 3개월 평균 조회가 실패하면 그 평균 칸만 모름이다
        key = 'sale' if trade_type == 'A1' else 'jeonse'
        column = f'trade_summary.{key}' + ('.recent_3m_average_manwon' if average_3m else '')
        return result_or_none(lambda: client.run_request_complex_pyeong_real_price_summary_v1(
            NaverComplexPyeongRealPriceSummaryV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type, start_date=start_date,
            )
        ), notes=notes, what=f'{TRADE_NAME_BY_CODE[trade_type]} 실거래 요약', unknown=f'모름(null)으로 낸 칸: {column}')

    def trade_summary(trade_type: str, jeonse: bool) -> NaverRealPriceTradeSummary | None:
        raw = real_price_summary(trade_type, since)
        if raw is None:
            # 조회 실패(모름)다. 빈 것으로 보고 5년으로 다시 부르지 않는다
            return None
        summary = _real_price_trade_summary(raw, jeonse)
        if summary is None:
            # 웹 단지 화면은 거래 유형마다 3년 요약이 비면 5년으로 한 번 더 부른다
            fallback_since = years_ago(today, REAL_PRICE_SUMMARY_FALLBACK_YEARS)
            summary = _real_price_trade_summary(real_price_summary(trade_type, fallback_since), jeonse)
            if summary is None:
                return None
            summary.start_date = fallback_since
            # 3개월 구간은 3년 구간 안이라 3년이 비었으면 3개월도 비어 요청하지 않는다
            return summary
        # 3개월 안 거래가 없으면 서버가 빈 객체를 줘 평균이 없다
        recent = real_price_summary(trade_type, months_ago(today, REAL_PRICE_RECENT_MONTHS), average_3m=True)
        if recent is not None and recent.avg_price:
            summary.recent_3m_average_manwon = won_to_manwon(recent.avg_price)
        return summary

    sale_summary = trade_summary('A1', jeonse=False)
    jeonse_summary = trade_summary('B1', jeonse=True)
    maintenance = None
    if fee is not None and fee.month_average_fee is not None:
        maintenance = NaverComplexMaintenanceFee(
            latest_month=read_month(fee.year_month, '관리비 최근 달'),
            latest_manage_cost_manwon=won_to_manwon(fee.year_month_fee),
            manage_cost_manwon=won_to_manwon(fee.month_average_fee),
            summer_manage_cost_manwon=won_to_manwon(fee.summer_average_fee),
            winter_manage_cost_manwon=won_to_manwon(fee.winter_average_fee),
        )
    details: dict[str, Any] = {
        'pyeong_manage_cost': maintenance,
        # 함께 오는 중개사 이름·전화(realtors)는 옮기지 않는다
        'estimated_prices': None if market is None else [
            NaverMarketPrice(
                provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
                base_date=read_date(item.base_date, '추정 시세 기준일'),
                **market_price_fields(
                    item.deal_average_price,
                    item.deal_price_range,
                    item.lease_average_price,
                    item.deposit_price_range,
                    item.lease_per_deal_rate,
                ),
            )
            for item in market
        ],
        'trade_summary': NaverRealPriceSummary(
            start_date=since,
            sale=sale_summary,
            jeonse=jeonse_summary,
        ),
    }
    # 평당가를 주지 않는 단지 유형(빌라 등)은 해당 없음이라 키를 두지 않는다. 단지 유형을 모르면 칸은 있는 것이라 null(모름)이다
    if real_estate_type is None or real_estate_type in PRICE_PER_PYEONG_COMPLEX_TYPES:
        details['asking_price_per_pyeong'] = _price_per_pyeong(client, complex_number, pyeong_number, real_estate_type, notes)
    return details
