"""단지 요약·평형·관리비·시세·실거래 요약 (complex)."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from jibsa.core.listing import (
    join_address,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    won_to_manwon,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.request.complex import (
    NaverComplexArticleStatsV1RequestParameterModel,
    NaverComplexMaintenanceFeeV1RequestParameterModel,
    NaverComplexMarketPriceRecentV1RequestParameterModel,
    NaverComplexPyeongRealPriceSummaryV1RequestParameterModel,
    NaverComplexReconstructionV1RequestParameterModel,
    NaverComplexVillaArticleStatsV1RequestParameterModel,
    NaverEducationComplexSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.response.common import NaverPyeongModel
from jibsa.providers.naver.api.response.complex import (
    NaverMarketPriceModel,
    NaverRealPriceSummaryModel,
    NaverRealPriceSummaryTradeModel,
)
from jibsa.providers.naver.service.common import (
    MARKET_PRICE_PROVIDER_NAMES,
    OFFICETEL_CODE,
    PROPERTY_NAME_BY_CODE,
    NaverAssignedSchool,
    assigned_schools,
    complex_url,
    kst_today,
    manwon_range,
    pyeong_list,
    raise_missing_pyeongs,
    resolve_dong_numbers,
    result_or_none,
    trade_article_counts,
    unwrap,
    villa_by_complex_response,
    won_to_manwon_range,
    years_ago,
)

from typing import (
    Annotated,
    Any,
)


class NaverPyeong(BaseModel):
    """평형."""

    model_config = ConfigDict(
        extra='forbid',
    )

    number: Annotated[
        int,
        Field(description='평형 번호 (real-price 의 --pyeong)')
    ]
    name: Annotated[
        str,
        Field(description='평형 이름 (공급면적 ㎡)')
    ]
    exclusive_m2: Annotated[
        float | None,
        Field(description='전용면적 (㎡)')
    ] = None
    exclusive_pyeong: Annotated[
        float | None,
        Field(description='전용면적 (평)')
    ] = None
    supply_m2: Annotated[
        float | None,
        Field(description='공급면적 (㎡). 오피스텔은 전용+주거공용이라 평형 이름보다 작다. 오피스텔인데 계약면적과 같게 오면 공급 칸에 계약면적이 채워진 것이라 null')
    ] = None
    contract_m2: Annotated[
        float | None,
        Field(description='계약면적 (㎡). 오피스텔은 평형 이름·매물 상세의 공급면적이 이 값이다')
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
        Field(description='세대수')
    ] = None


class NaverComplexMaintenanceFee(BaseModel):
    """평형의 월 관리비 (만원, 네이버가 단지 관리비 자료로 보여 주는 값)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    year_month: Annotated[
        str | None,
        Field(description='가장 최근 달 (YYYY-MM)')
    ] = None
    latest_manwon: Annotated[
        float | None,
        Field(description='가장 최근 달 관리비 (만원)')
    ] = None
    monthly_average_manwon: Annotated[
        float | None,
        Field(description='월평균 관리비 (만원)')
    ] = None
    summer_average_manwon: Annotated[
        float | None,
        Field(description='여름 평균 관리비 (만원)')
    ] = None
    winter_average_manwon: Annotated[
        float | None,
        Field(description='겨울 평균 관리비 (만원, 난방비 때문에 높다)')
    ] = None


class NaverMarketPrice(BaseModel):
    """한 기관의 최신 시세 (만원). 기관이 추정한 값이라 실제 거래가가 아니다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    provider: Annotated[
        str,
        Field(description='시세 기관 (한국부동산원, KB부동산, 부동산뱅크)')
    ]
    base_date: Annotated[
        str | None,
        Field(description='시세 기준일 (YYYY-MM-DD)')
    ] = None
    sale_average_manwon: Annotated[
        float | None,
        Field(description='매매 시세 평균 (만원)')
    ] = None
    sale_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_ratio_percent: Annotated[
        list[float | None] | None,
        Field(description='전세가율 [하한, 상한] (%)')
    ] = None


class NaverRealPriceExtreme(BaseModel):
    """실거래 요약의 최저·최고 거래 한 건."""

    model_config = ConfigDict(
        extra='forbid',
    )

    price_manwon: Annotated[
        float | None,
        Field(description='거래가 (만원, 매매는 매매가, 전세는 보증금)')
    ] = None
    trade_date: Annotated[
        str | None,
        Field(description='계약일 (YYYY-MM-DD)')
    ] = None
    floor: Annotated[
        int | None,
        Field(description='층')
    ] = None
    trade_category: Annotated[
        str | None,
        Field(description='중개거래 / 직거래. 직거래는 가족 간 거래처럼 시세와 동떨어진 값일 수 있다')
    ] = None
    cancelled: Annotated[
        bool | None,
        Field(description='해제(취소)된 거래')
    ] = None


class NaverRealPriceTradeSummary(BaseModel):
    """한 거래 유형의 기간 안 실거래 요약."""

    model_config = ConfigDict(
        extra='forbid',
    )

    average_manwon: Annotated[
        float | None,
        Field(description='평균 거래가 (만원)')
    ] = None
    lowest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최저가 거래')
    ] = None
    highest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최고가 거래')
    ] = None


class NaverRealPriceSummary(BaseModel):
    """평형의 최근 실거래 요약 (매매·전세)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    since: Annotated[
        str,
        Field(description='이 날짜 이후 거래 (YYYY-MM-DD, 3년 전 오늘)')
    ]
    sale: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='매매. 기간 안 거래가 없거나 조회 실패면 null')
    ] = None
    jeonse: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='전세. 기간 안 거래가 없거나 조회 실패면 null')
    ] = None


class NaverReconstructionStep(BaseModel):
    """재건축 사업 단계 하나."""

    model_config = ConfigDict(
        extra='forbid',
    )

    step: Annotated[
        str,
        Field(description='단계 이름 (예: 조합설립인가)')
    ]
    date: Annotated[
        str | None,
        Field(description='그 단계에 이른 날 (YYYY-MM-DD)')
    ] = None


class NaverReconstruction(BaseModel):
    """재건축 단지의 사업 진행."""

    model_config = ConfigDict(
        extra='forbid',
    )

    current_step: Annotated[
        str | None,
        Field(description='현재 단계')
    ] = None
    current_step_date: Annotated[
        str | None,
        Field(description='현재 단계에 이른 날 (YYYY-MM-DD)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='선정된 시공사')
    ] = None
    planned_households: Annotated[
        int | None,
        Field(description='재건축 후 계획 세대수')
    ] = None
    planned_floor_area_ratio: Annotated[
        float | None,
        Field(description='재건축 계획 용적률 (%)')
    ] = None
    steps: Annotated[
        list[NaverReconstructionStep],
        Field(description='지나온 단계 (날짜가 있는 단계만, 단계 순서)')
    ] = []


class NaverComplexSummary(BaseModel):
    """단지 요약. 매물과 마찬가지로 좌표는 담지 않는다 (위치는 주소와 원 사이트로)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    complex_number: Annotated[
        int,
        Field(description='단지 번호')
    ]
    name: Annotated[
        str,
        Field(description='단지명')
    ]
    property_type: Annotated[
        str | None,
        Field(description='단지 유형')
    ] = None
    address: Annotated[
        str | None,
        Field(description='지번 주소')
    ] = None
    road_address: Annotated[
        str | None,
        Field(description='도로명 주소')
    ] = None
    households: Annotated[
        int | None,
        Field(description='총 세대수')
    ] = None
    dong_count: Annotated[
        int | None,
        Field(description='동 수')
    ] = None
    approved_at: Annotated[
        str | None,
        Field(description='사용승인일 (YYYY-MM-DD)')
    ] = None
    construction_company: Annotated[
        str | None,
        Field(description='시공사')
    ] = None
    parking_per_household: Annotated[
        float | None,
        Field(description='세대당 주차 대수')
    ] = None
    floor_area_ratio: Annotated[
        float | None,
        Field(description='용적률 (%)')
    ] = None
    article_counts: Annotated[
        dict[str, int],
        Field(description='거래 유형별 매물 수')
    ] = {}
    sale_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 호가 [최저, 최고] (만원)')
    ] = None
    jeonse_asking_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 호가 [최저, 최고] (만원)')
    ] = None
    pyeongs: Annotated[
        list[NaverPyeong],
        Field(description='평형 목록')
    ] = []
    pyeong_maintenance_fee: Annotated[
        NaverComplexMaintenanceFee | None,
        Field(description='--pyeong 평형의 월 관리비. 평형을 하나만 줄 때만 키가 있고, 자료가 없으면 null')
    ] = None
    market_prices: Annotated[
        list[NaverMarketPrice] | None,
        Field(description='--pyeong 평형의 기관별 최신 시세. 평형을 하나만 줄 때만 키가 있고, 시세가 없으면 []')
    ] = None
    real_price_summary: Annotated[
        NaverRealPriceSummary | None,
        Field(description='--pyeong 평형의 최근 3년 매매·전세 실거래 요약. 평형을 하나만 줄 때만 키가 있다')
    ] = None
    schools: Annotated[
        list[NaverAssignedSchool] | None,
        Field(description='배정 초등학교. 조회 실패면 null')
    ] = None
    reconstruction: Annotated[
        NaverReconstruction | None,
        Field(description='재건축 사업 진행. 재건축 단지만 키가 있고, 조회 실패면 null')
    ] = None
    url: Annotated[
        str,
        Field(description='단지 페이지 URL')
    ]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='평형 정보를 붙이지 못한 이유 등. CLI 가 결과 위에 붙인다')
    ] = []

    # --pyeong 을 하나만 줘서 평형 정보(관리비·시세·실거래 요약)를 조회했는지. 아니면 그 키는 해당 없음이라 뺀다
    _pyeong_scoped: bool = PrivateAttr(default=False)
    # 재건축 단지인지. 아니면 reconstruction 은 해당 없음이라 뺀다
    _reconstruction_scoped: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self._pyeong_scoped:
            for field in PYEONG_SCOPED_FIELDS:
                data.pop(field, None)
        if not self._reconstruction_scoped:
            data.pop('reconstruction', None)
        return data


# 단지 요약에서 --pyeong 을 하나만 줄 때만 붙이는 평형 정보
PYEONG_SCOPED_FIELDS: frozenset[str] = frozenset({'pyeong_maintenance_fee', 'market_prices', 'real_price_summary'})
# 실거래 요약 기간. 사이트 매물 상세의 요약과 같다
REAL_PRICE_SUMMARY_YEARS: int = 3


def _pyeong(pyeong: NaverPyeongModel, is_officetel: bool = False) -> NaverPyeong:
    supply = pyeong.supply_area
    if is_officetel and supply is not None and supply == pyeong.contract_area:
        # 오피스텔 공급면적은 계약면적보다 작다. 같으면 네이버가 공급 칸에 계약면적을 채운 것이라
        # (예: 공급 30.59 / 계약 30.59) 공급면적으로 내보내면 틀린 값이 되므로 모름으로 둔다.
        # 매물 상세가 오피스텔 공급면적을 None 으로 두는 것과 맞춘다.
        supply = None
    return NaverPyeong(
        number=pyeong.number,
        name=pyeong.name,
        exclusive_m2=pyeong.exclusive_area,
        exclusive_pyeong=m2_to_pyeong(pyeong.exclusive_area),
        supply_m2=supply,
        contract_m2=pyeong.contract_area,
        room_count=pyeong.room_count,
        bathroom_count=pyeong.bath_room_count,
        household_count=pyeong.household_count,
    )


# 재건축 단지 유형. 이 유형이면 사업 단계를 함께 묻는다
RECONSTRUCTION_CODE: str = 'A04'
RECONSTRUCTION_STEP_LABELS: dict[str, str] = {
    '01': '기본계획수립', '02': '안전진단', '03': '구역지정', '04': '추진위승인', '05': '조합설립인가',
    '06': '사업시행인가', '07': '관리처분인가', '08': '이주 및 철거', '09': '착공 및 분양', '10': '준공', '11': '이전고지',
}
"""재건축 사업 단계 코드 (사이트 COMPLEX_RECONSTRUCTION_STEP, 2026-10-10 확인)."""


def _reconstruction(client: NaverClient, complex_number: int) -> NaverReconstruction | None:
    """재건축 단지의 사업 진행 (1회 호출). 조회가 실패하면 모름(None)."""
    result = result_or_none(lambda: client.run_request_complex_reconstruction_v1(
        NaverComplexReconstructionV1RequestParameterModel(complex_number=complex_number)
    ))
    if result is None:
        return None
    current = result.current_business_step

    def label(code: str | None) -> str | None:
        return RECONSTRUCTION_STEP_LABELS.get(code or '', code)

    return NaverReconstruction(
        current_step=label(current.step_type) if current else None,
        current_step_date=normalize_date(current.implementation_date) if current else None,
        construction_company=result.construction_company or None,
        planned_households=result.household_count,
        planned_floor_area_ratio=result.building_area_to_land_ratio,
        steps=[
            NaverReconstructionStep(step=label(step.step_type), date=normalize_date(step.implementation_date))
            for step in result.business_steps
            if step.step_type and step.implementation_date
        ],
    )


def get_complex(
    client: NaverClient,
    complex_number: int,
    *,
    pyeong_numbers: list[int] | None = None,
    dong_names: list[str] | None = None,
    villa: bool | None = None,
    today: date | None = None,
) -> NaverComplexSummary:
    """단지 정보·매물 수·호가 범위·평형·배정 초등학교를 한 번에 모은다 (4회 호출, 빌라 단지는 5회, 종류를 알면 4회).

    재건축(A04) 단지는 사업 단계·시공사·계획 세대수를 1회 더 물어 `reconstruction` 으로 붙인다.

    단지로 등록된 빌라(A05·A06·A07)는 아파트 단지 엔드포인트가 성공 응답에 빈 결과를 주므로,
    그때 빌라 단지 엔드포인트로 다시 묻는다. 빌라 단지에는 동 수·건설사·방 수가 없다.

    Args:
        pyeong_numbers: 평형 번호. 주면 매물 수·호가 범위를 그 평형 매물로만 센다. 평형 목록에 없으면 NOT_FOUND.
        dong_names: 동 이름 ('104', '104동'). 주면 매물 수·호가 범위를 그 동 매물로만 센다 (동 목록 조회 1회 추가).
        villa: 빌라 단지인지 (`resolve_complex_number` 결과). 알면 빌라 단지는 아파트 단지 정보를 묻지 않는다 (1회 절약).
        today: 실거래 요약 기간(3년 전 오늘부터)의 기준일. Defaults to 오늘(한국 시간).

    평형을 하나만 주면 그 평형의 관리비·최신 시세·최근 3년 매매/전세 실거래 요약을 더 붙인다 (4회 추가).
    빌라 단지는 네이버가 이 정보를 주지 않아(모두 빈 결과, 2026-10-09 확인) 묻지 않고 notes 로 알린다.
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
    # 단지형 빌라는 villa 로 물어야 한다 (complex 로 물으면 빈 목록, 2026-10-10 확인)
    schools = result_or_none(lambda: client.run_request_education_complex_school_v1(
        NaverEducationComplexSchoolV1RequestParameterModel(
            complex_number=complex_number, item_type='villa' if villa else 'complex',
        )
    ))

    is_reconstruction = not villa and complex_.type == RECONSTRUCTION_CODE
    reconstruction = _reconstruction(client, complex_number) if is_reconstruction else None

    notes: list[str] = []
    pyeong_details: dict[str, Any] = {}
    unique_pyeongs = list(dict.fromkeys(pyeong_numbers or []))
    if len(unique_pyeongs) == 1 and not villa:
        pyeong_details = _pyeong_details(client, complex_number, unique_pyeongs[0], complex_.type, today or kst_today())
    elif len(unique_pyeongs) == 1:
        notes.append('빌라 단지는 네이버가 평형 관리비·시세·실거래 요약을 주지 않습니다. 실거래는 naver real-price 로 보세요')
    elif len(unique_pyeongs) > 1:
        notes.append('평형 관리비·시세·실거래 요약은 --pyeong 을 하나만 줄 때 붙습니다')

    address = complex_.address
    summary = NaverComplexSummary(
        complex_number=complex_number,
        name=complex_.name,
        property_type=PROPERTY_NAME_BY_CODE.get(complex_.type or '', complex_.type),
        address=normalize_address(
            join_address(address.city, address.division, address.sector, address.jibun)
        ) if address else None,
        road_address=normalize_address(
            join_address(address.city, address.division, address.road_name)
        ) if address and address.road_name else None,
        households=complex_.total_household_number,
        dong_count=complex_.dong_count,
        approved_at=normalize_date(complex_.use_approval_date),
        construction_company=complex_.construction_company,
        parking_per_household=complex_.parking_info.parking_count_per_household if complex_.parking_info else None,
        floor_area_ratio=complex_.building_ratio_info.floor_area_ratio if complex_.building_ratio_info else None,
        article_counts=trade_article_counts(counts),
        sale_asking_range_manwon=won_to_manwon_range(prices.deal_min_price, prices.deal_max_price),
        jeonse_asking_range_manwon=won_to_manwon_range(prices.rent_min_price, prices.rent_max_price),
        pyeongs=[_pyeong(pyeong, complex_.type == OFFICETEL_CODE) for pyeong in pyeongs],
        schools=None if schools is None else assigned_schools(schools),
        reconstruction=reconstruction,
        url=complex_url(complex_number),
        notes=notes,
        **pyeong_details,
    )
    summary._pyeong_scoped = bool(pyeong_details)
    summary._reconstruction_scoped = is_reconstruction
    return summary


def _market_price(item: NaverMarketPriceModel) -> NaverMarketPrice:
    # 함께 오는 중개사 이름·전화(realtors)는 옮기지 않는다
    return NaverMarketPrice(
        provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
        base_date=normalize_date(item.base_date),
        sale_average_manwon=won_to_manwon(item.deal_average_price),
        sale_range_manwon=manwon_range(item.deal_price_range),
        jeonse_range_manwon=manwon_range(item.deposit_price_range),
        jeonse_ratio_percent=manwon_range(item.lease_per_deal_rate, scale=False),
    )


def _real_price_extreme(trade: NaverRealPriceSummaryTradeModel | None, jeonse: bool) -> NaverRealPriceExtreme | None:
    if trade is None:
        return None
    return NaverRealPriceExtreme(
        price_manwon=won_to_manwon(trade.deposit if jeonse else trade.deal_price),
        trade_date=normalize_date(trade.trade_date),
        floor=trade.floor,
        trade_category=trade.trade_category or None,
        cancelled=trade.is_delete,
    )


def _real_price_trade_summary(summary: NaverRealPriceSummaryModel | None, jeonse: bool) -> NaverRealPriceTradeSummary | None:
    """거래가 없으면 서버가 빈 객체를 줘 None 이다."""
    if summary is None or (summary.avg_price is None and summary.min_price is None and summary.max_price is None):
        return None
    return NaverRealPriceTradeSummary(
        average_manwon=won_to_manwon(summary.avg_price),
        lowest=_real_price_extreme(summary.min_price, jeonse),
        highest=_real_price_extreme(summary.max_price, jeonse),
    )


def _pyeong_details(
    client: NaverClient,
    complex_number: int,
    pyeong_number: int,
    real_estate_type: str | None,
    today: date,
) -> dict[str, Any]:
    """평형의 관리비·최신 시세·최근 3년 매매/전세 실거래 요약 (4회 호출). 조회가 실패하면 그 값만 None."""
    fee = result_or_none(lambda: client.run_request_complex_maintenance_fee_v1(
        NaverComplexMaintenanceFeeV1RequestParameterModel(complex_number=complex_number, pyeong_type_number=pyeong_number)
    ))
    # 단지 유형은 늘 온다 (아파트·오피스텔·빌라 6곳). 시세가 없으면 서버가 [] 를 줘 그대로 [] 이고,
    # None 은 조회 실패(모름)일 때뿐이다 (2026-10-09 확인)
    market = None
    if real_estate_type:
        market = result_or_none(lambda: client.run_request_complex_market_price_recent_v1(
            NaverComplexMarketPriceRecentV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, real_estate_type=real_estate_type,
            )
        ))
    since = years_ago(today, REAL_PRICE_SUMMARY_YEARS)

    def real_price_summary(trade_type: str) -> NaverRealPriceSummaryModel | None:
        return result_or_none(lambda: client.run_request_complex_pyeong_real_price_summary_v1(
            NaverComplexPyeongRealPriceSummaryV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type, start_date=since,
            )
        ))

    sale_summary = real_price_summary('A1')
    jeonse_summary = real_price_summary('B1')
    maintenance = None
    if fee is not None and fee.month_average_fee is not None:
        maintenance = NaverComplexMaintenanceFee(
            year_month=fee.year_month,
            latest_manwon=won_to_manwon(fee.year_month_fee),
            monthly_average_manwon=won_to_manwon(fee.month_average_fee),
            summer_average_manwon=won_to_manwon(fee.summer_average_fee),
            winter_average_manwon=won_to_manwon(fee.winter_average_fee),
        )
    return {
        'pyeong_maintenance_fee': maintenance,
        'market_prices': None if market is None else [_market_price(item) for item in market],
        'real_price_summary': NaverRealPriceSummary(
            since=since,
            sale=_real_price_trade_summary(sale_summary, jeonse=False),
            jeonse=_real_price_trade_summary(jeonse_summary, jeonse=True),
        ),
    }
