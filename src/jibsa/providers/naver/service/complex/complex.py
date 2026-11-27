"""단지 요약 (complex): 단지 정보·매물 수·호가 범위·평형·배정 초등학교·평형 묶음·재건축을 한 번에 모은다."""

from datetime import date

from jibsa.core.listing import (
    join_address,
    m2_to_pyeong,
    normalize_address,
    normalize_date,
    read_date,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.common import (
    NaverComplexPyeongGroupsV1RequestParameterModel,
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.request.complex import (
    NaverComplexArticleStatsV1RequestParameterModel,
    NaverComplexReconstructionV1RequestParameterModel,
    NaverComplexVillaArticleStatsV1RequestParameterModel,
    NaverEducationComplexSchoolV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.common import NaverPyeongModel
from jibsa.providers.naver.service.common.constants import COMPLEX_URL, OFFICETEL_CODE
from jibsa.providers.naver.service.common.price import (
    complex_row_fields,
    kst_today,
)
from jibsa.providers.naver.service.common.pyeong import (
    group_pyeong_numbers,
    pyeong_list,
    raise_missing_pyeongs,
    resolve_dong_numbers,
)
from jibsa.providers.naver.service.common.response import (
    result_or_empty,
    result_or_none,
    unwrap,
    villa_by_complex_response,
)
from jibsa.providers.naver.service.common.schools import assigned_schools
from jibsa.providers.naver.service.complex.constants import (
    RECONSTRUCTION_CODE,
    RECONSTRUCTION_STEP_LABELS,
)
from jibsa.providers.naver.service.complex.models import (
    NaverComplexSummary,
    NaverPyeong,
    NaverPyeongGroup,
    NaverReconstruction,
    NaverReconstructionStep,
)
from jibsa.providers.naver.service.complex.pyeong_details import (
    pyeong_details as _pyeong_details,
)

from typing import (
    Any,
)


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

    평형을 하나만 주면 그 평형의 관리비·최신 시세·최근 3년 매매/전세 실거래 요약·평당가를 더 붙인다 (`pyeong_details`: 관리비 1 + 시세 1 + 매매·전세 각 1~2 +
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
        url=COMPLEX_URL.format(complex_number),
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
