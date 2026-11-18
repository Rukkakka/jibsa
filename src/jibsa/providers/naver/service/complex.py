"""단지 요약·평형·평형 묶음·관리비·시세·실거래 요약 (complex)."""

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
    months_ago,
    normalize_address,
    normalize_date,
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
    MONTHLY_ASKING_DESCRIPTION,
    OFFICETEL_CODE,
    SHORT_TERM_ASKING_DESCRIPTION,
    NaverAssignedSchool,
    NaverRentAskingRange,
    assigned_schools,
    complex_row_fields,
    complex_url,
    group_pyeong_numbers,
    kst_today,
    manwon_range,
    pyeong_list,
    raise_missing_pyeongs,
    resolve_dong_numbers,
    result_or_empty,
    result_or_none,
    unwrap,
    villa_by_complex_response,
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


class NaverPyeongGroup(BaseModel):
    """평형 묶음 하나. 네이버는 평형이 많은 단지를 대표 평수(33평 등)로 묶어 보여 준다."""

    model_config = ConfigDict(
        extra='forbid',
    )

    name: Annotated[
        str | None,
        Field(description='묶음 이름 (대표 평수, 예: 33평)')
    ] = None
    representative_pyeong: Annotated[
        int | None,
        Field(description='대표 평형 번호 (real-price 의 --pyeong). 묶음에 든 평형 번호 중 하나다')
    ] = None
    households: Annotated[
        int | None,
        Field(description='묶음의 세대수')
    ] = None
    pyeong_numbers: Annotated[
        list[int] | None,
        Field(description='묶음에 든 평형 번호 (번호순, pyeongs[].number). 네이버가 이 묶음의 평형 목록을 주지 않으면 null (모름)')
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
        Field(description='매매 시세 평균 (만원). 없으면 null')
    ] = None
    sale_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='매매 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_average_manwon: Annotated[
        float | None,
        Field(description='전세 시세 평균 (만원). 없으면 null')
    ] = None
    jeonse_range_manwon: Annotated[
        list[float | None] | None,
        Field(description='전세 시세 [하한, 상한] (만원)')
    ] = None
    jeonse_ratio_percent: Annotated[
        list[float | None] | None,
        Field(description='전세가율 [하한, 상한] (%). 시세가 없으면(0 포함) null')
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

    since: Annotated[
        str | None,
        Field(description='3년 안에 거래가 없어 5년으로 다시 받았을 때만 있는 시작일 (YYYY-MM-DD, 5년 전 오늘). 3년으로 받았으면 키가 없다')
    ] = None
    average_manwon: Annotated[
        float | None,
        Field(description='평균 거래가 (만원)')
    ] = None
    average_3m_manwon: Annotated[
        float | None,
        Field(description='최근 3개월 평균 거래가 (만원). 3개월 안 거래가 없거나 조회 실패면 null')
    ] = None
    lowest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최저가 거래')
    ] = None
    highest: Annotated[
        NaverRealPriceExtreme | None,
        Field(description='최고가 거래')
    ] = None

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.since is None:
            data.pop('since', None)
        return data


class NaverRealPriceSummary(BaseModel):
    """평형의 최근 실거래 요약 (매매·전세)."""

    model_config = ConfigDict(
        extra='forbid',
    )

    since: Annotated[
        str,
        Field(description='이 날짜 이후 거래 (YYYY-MM-DD, 3년 전 오늘). 3년 안 거래가 없는 유형은 5년으로 다시 받고 그 유형의 요약에 since 가 따로 있다')
    ]
    sale: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='매매. 5년 안에도 거래가 없거나 조회 실패면 null')
    ] = None
    jeonse: Annotated[
        NaverRealPriceTradeSummary | None,
        Field(description='전세. 5년 안에도 거래가 없거나 조회 실패면 null')
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
    monthly_asking: Annotated[
        NaverRentAskingRange | None,
        Field(description=MONTHLY_ASKING_DESCRIPTION)
    ] = None
    short_term_asking: Annotated[
        NaverRentAskingRange | None,
        Field(description=SHORT_TERM_ASKING_DESCRIPTION)
    ] = None
    pyeongs: Annotated[
        list[NaverPyeong],
        Field(description='평형 목록')
    ] = []
    pyeong_groups: Annotated[
        list[NaverPyeongGroup] | None,
        Field(description='평형 묶음 (대표 평수별 평형 번호). 빌라 단지는 키가 없고, 서버가 묶음을 주지 않으면 [], 조회 실패면 null. --pyeong 을 몇 개 주든 붙는다')
    ] = None
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
        Field(description=(
            '--pyeong 평형의 최근 3년 매매·전세 실거래 요약. 평형을 하나만 줄 때만 키가 있다. 그 거래 유형의 3년 거래가 없으면 5년으로 '
            '요약하고 그 유형에 since 가 붙는다. 3개월 평균 average_3m_manwon 은 5년으로 요약했으면 null 이다. 조회가 실패한 유형은 null'
        ))
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
    # 평형 묶음을 조회했는지. 빌라 단지는 웹도 묻지 않아 pyeong_groups 는 해당 없음이라 뺀다
    _pyeong_groups_scoped: bool = PrivateAttr(default=False)

    @model_serializer(mode='wrap')
    def drop_not_applicable(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self._pyeong_scoped:
            for field in PYEONG_SCOPED_FIELDS:
                data.pop(field, None)
        if not self._reconstruction_scoped:
            data.pop('reconstruction', None)
        if not self._pyeong_groups_scoped:
            data.pop('pyeong_groups', None)
        return data


# 단지 요약에서 --pyeong 을 하나만 줄 때만 붙이는 평형 정보
PYEONG_SCOPED_FIELDS: frozenset[str] = frozenset({'pyeong_maintenance_fee', 'market_prices', 'real_price_summary'})
# 실거래 요약 기간. 웹 단지 화면 실거래 요약(ComplexTransactionPriceSummary)과 같다. 비면 5년
REAL_PRICE_SUMMARY_YEARS: int = 3
REAL_PRICE_SUMMARY_FALLBACK_YEARS: int = 5
# 요약에 덧붙이는 최근 평균 기간 (웹 매물 상세 RecentTransaction 의 '3개월 평균 실거래' 와 같은 요청)
REAL_PRICE_RECENT_MONTHS: int = 3


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


def _pyeong_groups(client: NaverClient, complex_number: int) -> list[NaverPyeongGroup] | None:
    """평형 묶음 (1회 호출). 네이버가 묶음을 주지 않으면(빈 목록이거나 성공인데 `result` 가 null) [], 조회가 실패하면 모름(None).

    `real-price --group` 의 `_find_pyeong_group` 도 성공인데 `result` 가 null 인 응답을 빈 목록과 같게 읽는다. 묶음의 평형 목록을 주지 않으면
    (`pyeongTypes` null) 그 묶음만 `pyeong_numbers` 가 모름(None)이다.
    """
    groups = result_or_empty(lambda: client.run_request_complex_pyeong_groups_v1(
        NaverComplexPyeongGroupsV1RequestParameterModel(complex_number=complex_number)
    ), list)
    if groups is None:
        return None
    return [
        NaverPyeongGroup(
            name=group.representative_pyeong_name,
            representative_pyeong=group.representative_pyeong_number,
            households=group.household_count,
            pyeong_numbers=group_pyeong_numbers(group),
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

    평형을 하나만 주면 그 평형의 관리비·최신 시세·최근 3년 매매/전세 실거래 요약을 더 붙인다 (관리비 1 + 시세 1(단지 유형이 있을 때) + 매매·전세 각 1~2 = 4~6회, 시세 요청이 없으면 3~5회).
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
    # 웹은 단지형 빌라에서 평형 묶음을 부르지 않는다 (`!isVilla`)
    pyeong_groups = None if villa else _pyeong_groups(client, complex_number)

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
        address=normalize_address(
            join_address(address.city, address.division, address.sector, address.jibun)
        ) if address else None,
        road_address=normalize_address(
            join_address(address.city, address.division, address.road_name)
        ) if address and address.road_name else None,
        construction_company=complex_.construction_company,
        parking_per_household=complex_.parking_info.parking_count_per_household if complex_.parking_info else None,
        floor_area_ratio=complex_.building_ratio_info.floor_area_ratio if complex_.building_ratio_info else None,
        pyeongs=[_pyeong(pyeong, complex_.type == OFFICETEL_CODE) for pyeong in pyeongs],
        pyeong_groups=pyeong_groups,
        schools=None if schools is None else assigned_schools(schools),
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
    summary._reconstruction_scoped = is_reconstruction
    summary._pyeong_groups_scoped = not villa
    return summary


def _market_price(item: NaverMarketPriceModel) -> NaverMarketPrice:
    # 함께 오는 중개사 이름·전화(realtors)는 옮기지 않는다
    return NaverMarketPrice(
        provider=MARKET_PRICE_PROVIDER_NAMES.get(item.cp or '', item.cp or '알 수 없음'),
        base_date=normalize_date(item.base_date),
        # 평균 0 은 범위(manwon_range)처럼 없음으로 본다 (네이버 웹도 0 이면 시세를 그리지 않는다)
        sale_average_manwon=won_to_manwon(item.deal_average_price) if item.deal_average_price else None,
        sale_range_manwon=manwon_range(item.deal_price_range),
        jeonse_average_manwon=won_to_manwon(item.lease_average_price) if item.lease_average_price else None,
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
    """평형의 관리비·최신 시세·최근 3년(비면 5년) 매매/전세 실거래 요약과 3개월 평균 (관리비 1 + 시세 1(단지 유형이 있을 때) + 매매·전세 각 1~2 = 4~6회, 시세 요청이 없으면 3~5회). 조회가 실패하면 그 값만 None."""
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

    def real_price_summary(trade_type: str, start_date: str) -> NaverRealPriceSummaryModel | None:
        return result_or_none(lambda: client.run_request_complex_pyeong_real_price_summary_v1(
            NaverComplexPyeongRealPriceSummaryV1RequestParameterModel(
                complex_number=complex_number, pyeong_type_number=pyeong_number, trade_type=trade_type, start_date=start_date,
            )
        ))

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
            summary.since = fallback_since
            # 3개월 구간은 3년 구간 안이라 3년이 비었으면 3개월도 비어 요청하지 않는다
            return summary
        # 3개월 안 거래가 없으면 서버가 빈 객체를 줘 평균이 없다
        recent = real_price_summary(trade_type, months_ago(today, REAL_PRICE_RECENT_MONTHS))
        if recent is not None and recent.avg_price:
            summary.average_3m_manwon = won_to_manwon(recent.avg_price)
        return summary

    sale_summary = trade_summary('A1', jeonse=False)
    jeonse_summary = trade_summary('B1', jeonse=True)
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
            sale=sale_summary,
            jeonse=jeonse_summary,
        ),
    }
