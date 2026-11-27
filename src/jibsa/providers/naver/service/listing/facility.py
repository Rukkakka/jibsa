"""매물 상세의 단지·건물 시설 (난방·난방 연료·현관 구조·주차·단지 사용승인일)."""

from decimal import (
    ROUND_FLOOR,
    Decimal,
)

from jibsa.core.dates import normalize_date
from jibsa.core.listing import parking_label
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.common import (
    NaverComplexV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.request.listing.detail import (
    NaverComplexBuildingRegistrationV1RequestParameterModel,
    NaverComplexPyeongV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverComplexModel,
    NaverFacilityInfoModel,
)
from jibsa.providers.naver.api.models.response.listing.detail import (
    NaverArticleKeyModel,
)
from jibsa.providers.naver.service.common.constants import VILLA_COMPLEX_CODES
from jibsa.providers.naver.service.common.response import result_or_none
from jibsa.providers.naver.service.listing.common import coded_label
from jibsa.providers.naver.service.listing.constants import (
    BUILDING_REGISTRATION_TYPES,
    COMPLEX_INFO_TYPES,
    ENTRANCE_LABELS,
    HEATING_FUEL_LABELS,
    HEATING_LABELS,
)

from typing import NamedTuple


class _FacilityValues(NamedTuple):
    """난방·난방 연료·현관 구조·주차 (`NaverListingDetail` 의 같은 이름 필드)."""

    heating: str | None
    heating_fuel: str | None
    entrance: str | None
    parking: str | None


def _parking_label(facility: NaverFacilityInfoModel | None, in_complex: bool) -> str | None:
    """매물 상세(facilityInfo)의 주차 가능 여부와 총 주차 대수를 문구로 만든다 ('불가 (총 4대)', '단지 전체 398대').

    아파트·오피스텔·재건축·분양권(`COMPLEX_INFO_TYPES`)은 웹이 매물 주차 값을 쓰지 않아 이 함수를 거치지 않고, 단지형 빌라는
    매물 대수가 0 보다 클 때만 이 함수를 쓴다 (`facility_values`). 단지 조회가 실패했고 매물 대수가 0 이거나 없으면
    이 함수를 거치지 않고 가능 여부만 낸다.
    건축물대장 유형(원룸·빌라·단독 등 `BUILDING_REGISTRATION_TYPES`)은 `_building_parking` 으로 가 이 함수를 거치지 않는다.
    이 함수는 단지형 빌라와, 마지막 갈래에 오는 단지 번호 없는 단지 유형·토지·고시원 등이 쓴다.
    대수가 있어도 이 매물은 주차 불가일 수 있어(2026-10-10 실측: 총 6대·불가) 가능 여부를
    앞에 붙인다. 단지 안(`in_complex`)일 때만 '단지 전체' 를 붙이고 아니면 '총' 이다. 0대는 모름이 아니라 0대다.
    """
    if facility is None:
        return None
    count = facility.total_parking_count
    count_text = None if count is None else f'{"단지 전체" if in_complex else "총"} {count}대'
    return parking_label(facility.is_parking_possible, count_text)


def complex_overview(
    client: NaverClient,
    complex_number: int | None,
    real_estate_type: str,
    notes: list[str],
) -> NaverComplexModel | None:
    """난방·주차·사용승인일에 쓸 단지 정보. 단지 유형은 `/complex`, 단지형 빌라는 `/complex/villa` 를 한 번 받는다 (1회).

    그 밖의 유형이거나 단지 번호가 없으면 요청하지 않고 None, 조회가 실패해도 None 이다 (그 값만 모름). 실패하면 `notes` 에 `[실패]` 안내를
    붙인다. 안내에 적는 칸은 단지 값이 없어 달라지는 칸이다: 단지 유형은 사용승인일·주차가 null, 난방·난방 연료는 매물 값만 남고,
    단지형 빌라는 난방·난방 연료가 null, 주차는 매물 값만 남는다 (사용승인일은 동 목록을 따로 받아 그대로다, `facility_values`·`complex_approved_at`).
    """
    if complex_number is None:
        return None
    if real_estate_type in COMPLEX_INFO_TYPES:
        return result_or_none(
            lambda: client.run_request_complex_v1(
                NaverComplexV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='단지 정보',
            unknown='모름(null)으로 낸 칸: approved_date, parking. 단지 값 없이 낸 칸: heating, heating_fuel',
        )
    if real_estate_type in VILLA_COMPLEX_CODES:
        return result_or_none(
            lambda: client.run_request_complex_villa_v1(
                NaverComplexVillaV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='단지 정보',
            unknown='모름(null)으로 낸 칸: heating, heating_fuel. 단지 값 없이 낸 칸: parking',
        )
    return None


def complex_approved_at(
    client: NaverClient,
    complex_number: int | None,
    key: NaverArticleKeyModel,
    complex_: NaverComplexModel | None,
    notes: list[str],
) -> str | None:
    """단지의 사용승인일 (YYYY-MM-DD). 단지 유형은 늘, 그 밖의 유형은 매물 상세에 건물 날짜가 없을 때만 부른다 (`get_listing`. 사용승인일 칸이 없는 토지·고시원은 부르지 않는다).

    단지 유형(`COMPLEX_INFO_TYPES`)은 `complex_overview` 가 받은 단지 정보(`complex_`)의 날짜를 쓴다 (같은 요청을 두 번 하지 않는다).
    빌라 단지(A05·A06·A07)는 아파트 단지 엔드포인트가 result=null 이라 빌라 동 목록에서 매물의 동
    (article/key 의 buildingNumber)을 찾아 그 동의 날짜를 쓴다. 빌라 단지 정보에는 날짜가 없는 단지가
    있고(진명하이츠 등), 동마다 날짜가 다른 단지도 있어서다 (성재하이빌 에이동 2003-08-11·비동
    2003-09-05, 2026-10-09 확인).

    단지 번호가 없거나 단지 조회가 실패하면(단지가 아닌 매물 등) 모름(None)이다. 이 함수가 보내는 조회가 실패하면 `notes` 에 `[실패]` 안내를 붙인다
    (단지 유형이 쓰는 `complex_` 의 실패 안내는 `complex_overview` 가 붙인다).
    """
    if complex_number is None:
        return None
    if key.type.real_estate_type in VILLA_COMPLEX_CODES:
        building_number = key.key.building_number if key.key else None
        if building_number is None:
            return None
        buildings = result_or_none(
            lambda: client.run_request_complex_villa_building_list_v1(
                NaverComplexVillaBuildingListV1RequestParameterModel(complex_number=complex_number)
            ),
            notes=notes,
            what='사용승인일',
            unknown='모름(null)으로 낸 칸: approved_date',
        )
        building = next((item for item in buildings or [] if item.number == building_number), None)
        return normalize_date(building.use_approval_date) if building is not None else None
    if key.type.real_estate_type in COMPLEX_INFO_TYPES:
        return normalize_date(complex_.use_approval_date) if complex_ is not None else None
    other_complex = result_or_none(
        lambda: client.run_request_complex_v1(
            NaverComplexV1RequestParameterModel(complex_number=complex_number)
        ),
        notes=notes,
        what='사용승인일',
        unknown='모름(null)으로 낸 칸: approved_date',
    )
    return normalize_date(other_complex.use_approval_date) if other_complex is not None else None


def _complex_parking_text(complex_: NaverComplexModel | None, *, with_parentheses: bool) -> str | None:
    """단지 주차 대수 글자 ('단지 전체 12602대 (세대당 1.32대)'). 대수를 모르거나 단지 조회가 실패했으면 None.

    세대당 대수는 불필요한 0 없이 낸다 (1.32·0.5). 버려 0 이 되는 값(0.009)·0 은 '세대당 0대' 로 낸다 (웹 단지 쪽은 0 이어도 붙이고,
    건축물대장 쪽 `_building_parking` 은 붙이지 않는다). 세대당 대수가 없으면 대수만. `with_parentheses` 가 거짓이면 가능 여부 뒤 괄호 안에
    들어갈 꼴('단지 전체 8대, 세대당 0.5대')이다.
    """
    info = complex_.parking_info if complex_ else None
    if info is None or info.total_parking_count is None:
        return None
    text = f'단지 전체 {info.total_parking_count}대'
    per_household = info.parking_count_per_household
    if per_household is None:
        return text
    # 웹 ComplexParkingInfo(청크 00-c-lsvp5jax, 2026-11-25 번들 확인)는 floor(parkingCountPerHousehold ?? 0, 2) 를 조건 없이 '(세대당 N대)' 로 그리고,
    # 호출하는 ArticleComplexInfo 도 주차 칸을 조건 없이 넣는다. 그래서 버려 0 이 되는 값(0.009)·0 도 '세대당 0대' 로 낸다
    per_household = _floor_per_household(per_household) or 0
    return f'{text} ({_per_household_text(per_household)})' if with_parentheses else f'{text}, {_per_household_text(per_household)}'


def _per_household_text(per_household: float) -> str:
    """세대당 주차 대수 글자 ('세대당 0.5대'·'세대당 1대'). 불필요한 0 없이 낸다."""
    return f'세대당 {per_household:g}대'


def _floor_per_household(per_household: float | None) -> float | None:
    """세대당 주차 대수를 소수 둘째 자리 아래를 버려 정한다 (웹 lodash `floor(값 || 0, 2)`). 0 이거나 없으면 None.

    건축물대장 쪽 웹(ArticleBuildingInfo)은 이 값이 0 이면 '(세대당 N대)' 를 붙이지 않는다. 단지 쪽(`_complex_parking_text`)은 웹이 0 이어도 붙여
    이 함수가 None 을 주면 0 으로 쓴다. 버림은 십진 글자로 계산해 1.33 이 1.32 가 되지 않게 한다.
    """
    if not per_household:
        return None
    return float(Decimal(str(per_household)).quantize(Decimal('0.01'), rounding=ROUND_FLOOR)) or None


def _building_parking(
    client: NaverClient,
    key: NaverArticleKeyModel,
    facility: NaverFacilityInfoModel | None,
    notes: list[str],
) -> str | None:
    """건축물대장 유형(`BUILDING_REGISTRATION_TYPES`)의 주차 ('가능 (총 8대, 세대당 0.5대)', 가능 여부를 모르면 '총 8대 (세대당 0.5대)').

    웹처럼 매물 주차 대수가 참(0 이 아닌 수)이면 매물 대수와 매물 세대당 대수를, 아니면 건축물대장 값을 쓴다 (대장은 1회 호출).
    대장에도 대수가 없으면 대수는 모름이라 가능 여부만 낸다. 세대당 대수가 0 이거나 없으면 붙이지 않는다.
    """
    possible = facility.is_parking_possible if facility else None
    # 총 주차 대수와 세대당 대수 (웹 ArticleBuildingInfo 의 `[W, J]`)
    if facility is not None and facility.total_parking_count:
        total = facility.total_parking_count
        per_household = _floor_per_household(facility.parking_count_per_household)
    else:
        # 건축물대장 조회가 실패했을 때만 `notes` 에 `[실패]` 안내를 붙인다 (pnu 가 없거나 대장에 대수가 없는 것은 실패가 아니다).
        # 웹(ArticleBuildingInfo)은 pnu 가 없으면 이 요청을 보내지 않는다 (`enabled: !!pnu`). 0 대도 대수라 그대로 쓴다.
        pnu = key.key.pnu if key.key else None
        registration = None
        if pnu:
            registration = result_or_none(
                lambda: client.run_request_complex_building_registration_v1(
                    NaverComplexBuildingRegistrationV1RequestParameterModel(pnu=pnu, real_estate_type=key.type.real_estate_type)
                ),
                notes=notes,
                what='건축물대장 주차 대수',
                unknown='주차 대수 없이 낸 칸: parking',
            )
        info = registration.parking_info if registration else None
        if info is None or info.total_parking_count is None:
            return parking_label(possible)
        total = info.total_parking_count
        per_household = _floor_per_household(info.parking_count_per_household)
    # 웹 건축물 정보(ArticleBuildingInfo)는 '주차 N대' 하나뿐이라 매물 대수도 '단지 전체' 없이 늘 '총' 이다
    detail = f'총 {total}대'
    if per_household is not None:
        # 가능 여부가 있으면 그 뒤 괄호 안에 함께 넣고, 없으면 대수가 앞이라 세대당을 괄호로 붙인다
        per_household_text = _per_household_text(per_household)
        detail = f'{detail}, {per_household_text}' if possible is not None else f'{detail} ({per_household_text})'
    return parking_label(possible, detail)


def facility_values(
    client: NaverClient,
    key: NaverArticleKeyModel,
    facility: NaverFacilityInfoModel | None,
    complex_number: int | None,
    complex_: NaverComplexModel | None,
    notes: list[str],
) -> _FacilityValues:
    """난방·난방 연료·현관 구조·주차. 웹 화면이 매물 유형마다 값을 가져오는 곳이 달라 같은 곳에서 가져온다 (0~1회 호출).

    웹 근거 (2026-11-17 번들 청크 0l4pkwg0qhg2t, 화면 실측):
    - 단지 유형(`COMPLEX_INFO_TYPES`, ArticleComplexInfo): 난방·연료는 `facilityInfo?.heatingAndCoolingSystemType ||
      complex.heatingAndCoolingInfo?.heatingAndCoolingSystemType` (연료도 따로 같은 꼴)이라 매물 값이 비면(빈 글자도, JS `||`)
      단지 값을 쓴다. 현관은 `facilityInfo?.entranceType || complexPyeong.entranceType` 이라 매물 값이 비어 있고 평형 번호가 있을 때만
      `/complex/pyeong` 을 부른다. 주차는 단지 parkingInfo 만 쓰고 매물 주차 값과 '주차가능여부' 칸은 없어 가능 여부를 붙이지
      않는다. 헬리오시티 2662350994 는 매물 난방이 비고 단지(111515)의 heatingAndCoolingInfo 가 {HT005, HF002} 라 웹이
      '지역난방 / 열병합', 주차 '12,602대 (세대당 1.32대)' (매물 값은 12456). 오피스텔 2661748606 은 매물 현관이 비고
      평형(189377, 4)의 entranceType 이 '10' 이라 웹 '계단식'이다.
    - 단지형 빌라(`VILLA_COMPLEX_CODES`, ArticleVillaBuildingInfo): 난방·연료는 `/complex/villa` 의 heatingAndCoolingInfo 만 쓴다
      (매물 facilityInfo 는 보지 않는다). 주차는 매물 totalParkingCount 가 0 보다 크면 매물 값, 아니면 단지 parkingInfo 이고
      주차가능여부 칸은 매물 값이다. 2661158391(A06, 단지 479920)은 매물이 0대·가능이라 웹이 '주차 8대 (세대당 0.5대)',
      '주차가능여부 가능' 이고 jibsa 는 '가능 (단지 전체 8대, 세대당 0.5대)' 로 낸다. 현관 구조는 건드리지 않는다.
    - 건축물대장 유형(`BUILDING_REGISTRATION_TYPES` 15개, ArticleBuildingInfo): 주차 대수는 매물 totalParkingCount 가 참(0 이 아닌 수)이면
      매물 값, 아니면(0·null·facilityInfo 없음) `GET /complex/buildingRegistration?pnu=&realEstateType=` 의 parkingInfo.totalParkingCount
      이고, 그 값이 수(0 포함)일 때만 '주차 N대' 칸을 그린다. 세대당 대수도 같은 쪽의 `parkingCountPerHousehold` 를 소수 둘째 자리까지 버린 값
      (lodash `floor(값 || 0, 2)`)이고, 0 이면 '(세대당 N대)' 를 붙이지 않는다 (번들 `L` 은 lodash floor 다, 2026-11-18).
      웹은 '주차가능여부'(매물 값)와 '주차 N대 (세대당 M대)' 두 칸으로 그리고 jibsa 는 '가능 (총 8대, 세대당 0.5대)' 로 합친다
      (가능 여부를 모르면 '총 8대 (세대당 0.5대)', 세대당이 0·없음이면 '가능 (총 8대)').
      pnu 는 article/key 의 key.pnu 고, 없으면 웹도 요청하지 않는다. 원룸 2661724695 는 매물이 0대·불가이고 대장이 0대라 웹이 '주차 0대',
      2661862868 은 매물이 8대라 대장을 부르지 않는다. 대장 조회가 실패하거나 대수가 없으면 대수는 모름이라 가능 여부만 낸다 (`_building_parking`).
    그 밖의 유형은 매물 값 그대로다. 단지 조회(`complex_`)가 실패하면 그 값만 모름이다 (단지형 빌라 주차는 매물 대수가 0 보다 클 때만 매물 값이고, 0 이거나 없으면 대수 없이 가능 여부만 낸다).
    이 함수가 보내는 조회(평형·건축물대장)가 실패하면 `notes` 에 `[실패]` 안내를 붙인다 (`complex_` 의 실패 안내는 `complex_overview` 가 붙인다).
    """
    real_estate_type = key.type.real_estate_type
    system = facility.heating_and_cooling_system_type if facility else None
    energy = facility.heating_energy_type if facility else None
    entrance = facility.entrance_type if facility else None
    heating_info = complex_.heating_and_cooling_info if complex_ else None
    complex_system = heating_info.heating_and_cooling_system_type if heating_info else None
    complex_energy = heating_info.heating_energy_type if heating_info else None

    if complex_number is not None and real_estate_type in COMPLEX_INFO_TYPES:
        pyeong_number = key.key.pyeong_type_number if key.key else None
        if not entrance and pyeong_number:
            pyeong = result_or_none(
                lambda: client.run_request_complex_pyeong_v1(
                    NaverComplexPyeongV1RequestParameterModel(complex_number=complex_number, pyeong_type_number=pyeong_number)
                ),
                notes=notes,
                what='현관 구조',
                unknown='모름(null)으로 낸 칸: entrance',
            )
            entrance = pyeong.entrance_type if pyeong else None
        return _FacilityValues(
            heating=coded_label(HEATING_LABELS, system or complex_system),
            heating_fuel=coded_label(HEATING_FUEL_LABELS, energy or complex_energy),
            entrance=coded_label(ENTRANCE_LABELS, entrance),
            parking=_complex_parking_text(complex_, with_parentheses=True),
        )
    if complex_number is not None and real_estate_type in VILLA_COMPLEX_CODES:
        if facility is not None and (facility.total_parking_count or 0) > 0:
            parking = _parking_label(facility, True)
        elif complex_ is None:
            # 매물 대수 0 은 웹이 단지 대수로 바꿔 그리는 '모름' 이라, 단지 값도 없으면 대수 없이 가능 여부만 낸다 (2026-11-24 리뷰: '가능 (단지 전체 0대)' 가 나갔다)
            parking = parking_label(facility.is_parking_possible if facility else None)
        else:
            # 가능 여부를 모르면 parking_label 이 대수 글자만 돌려주므로 단지 유형과 같은 괄호 꼴로 낸다
            possible = facility.is_parking_possible if facility else None
            parking = parking_label(possible, _complex_parking_text(complex_, with_parentheses=possible is None))
        return _FacilityValues(
            heating=coded_label(HEATING_LABELS, complex_system),
            heating_fuel=coded_label(HEATING_FUEL_LABELS, complex_energy),
            entrance=coded_label(ENTRANCE_LABELS, entrance),
            parking=parking,
        )
    # 건축물대장 유형은 웹이 매물 대수가 0 이어도 쓰지 않고 대장 대수만 '주차 N대' 로 그린다. 대장에 대수가 없으면 칸이 없어 가능 여부만 낸다 ('총 0대' 를 내지 않는다)
    parking = (
        _building_parking(client, key, facility, notes)
        if real_estate_type in BUILDING_REGISTRATION_TYPES
        # 여기 오는 유형 중 단지 번호가 있는 것은 토지·고시원뿐이고 둘은 나중에 parking 키를 지운다 (common.py). 그래서 단지 안이 아니다
        # (근거: 2026-11-18 가산동·신림동 목록 160건과 지식산업센터 2662172371 에는 단지 번호가 없었다)
        else _parking_label(facility, False)
    )
    return _FacilityValues(
        heating=coded_label(HEATING_LABELS, system),
        heating_fuel=coded_label(HEATING_FUEL_LABELS, energy),
        entrance=coded_label(ENTRANCE_LABELS, entrance),
        parking=parking,
    )
