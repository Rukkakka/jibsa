"""네이버 단지 평형 목록·평형 번호 확인·동 이름 → 동 번호 해석."""

from jibsa.core.errors import JibsaError
from jibsa.core.korean import particle
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.models.request.common import (
    NaverComplexBuildingListV1RequestParameterModel,
    NaverComplexPyeongListV1RequestParameterModel,
    NaverComplexVillaBuildingListV1RequestParameterModel,
    NaverComplexVillaPyeongListV1RequestParameterModel,
)
from jibsa.providers.naver.api.models.response.common import (
    NaverPyeongGroupModel,
    NaverPyeongModel,
)
from jibsa.providers.naver.service.common.labels import (
    dong_key,
    dong_label,
)
from jibsa.providers.naver.service.common.response import (
    unwrap,
    villa_fallback_found,
)


def raise_missing_pyeongs(
    complex_number: int,
    pyeong_numbers: list[int] | None,
    pyeongs: list[NaverPyeongModel],
    *,
    no_pyeong_hint: str = '네이버에 평형 정보가 없는 단지입니다. --pyeong 없이 조회하세요',
) -> None:
    """단지 평형 목록에 없는 평형 번호가 있으면 이 단지의 평형 번호를 알려 주며 멈춘다.

    Args:
        no_pyeong_hint: 평형 목록이 비었을 때의 hint. 기본값은 단지가 있다고 확인했고 `--pyeong` 을 뺄 수 있는 명령(complex)용.

    Raises:
        JibsaError: NOT_FOUND.
    """
    known_numbers = {pyeong.number for pyeong in pyeongs}
    missing = [number for number in pyeong_numbers or [] if number not in known_numbers]
    if missing:
        available = ', '.join(f'{pyeong.number}({pyeong.name})' for pyeong in pyeongs)
        raise JibsaError(
            code='NOT_FOUND',
            message=f"단지 {complex_number} 에 없는 평형 번호입니다: {', '.join(map(str, missing))}",
            hint=f'이 단지의 평형 번호(이름): {available}' if available else no_pyeong_hint,
        )


def pyeong_list(client: NaverClient, complex_number: int, villa: bool) -> list[NaverPyeongModel]:
    """단지 평형 목록. 빌라 단지는 빌라 평형 목록을 묻는다 (1회)."""
    if villa:
        return unwrap(
            client.run_request_complex_villa_pyeong_list_v1(
                NaverComplexVillaPyeongListV1RequestParameterModel(complex_number=complex_number)
            ),
            '평형',
        )
    return unwrap(
        client.run_request_complex_pyeong_list_v1(NaverComplexPyeongListV1RequestParameterModel(complex_number=complex_number)),
        '평형',
    )


def group_pyeong_numbers(group: NaverPyeongGroupModel) -> list[int] | None:
    """평형 묶음에 든 평형 번호 (번호순). 대표 번호가 `pyeongTypes` 의 첫 항목이 아닐 수 있어 순서를 믿지 않고 정렬한다.

    네이버가 평형 목록을 주지 않거나(`pyeongTypes` null) 번호가 빈 평형이 있으면 묶음의 번호를 다 알 수 없어 모름(None)이다.
    """
    if group.pyeong_types is None:
        return None
    numbers = {pyeong.number for pyeong in group.pyeong_types}
    if None in numbers:
        return None
    return sorted(number for number in numbers if number is not None)


def check_pyeong_numbers(
    client: NaverClient,
    complex_number: int,
    pyeong_numbers: list[int],
    *,
    villa: bool | None = None,
    pyeong_required: bool = False,
) -> bool:
    """결과가 비었을 때 평형 번호가 단지에 있는지 확인하고, 빌라 단지인지 돌려준다 (1~2회 호출).

    평형 번호가 틀려도 서버는 매물·실거래·시세를 0건으로 줘서 '없음' 과 구분되지 않는다
    (헬리오시티 평형 999: 단지 매물·실거래·시세 모두 0건, 2026-10-10). 단지 종류를 모르면(None) 아파트 평형 목록을
    먼저 묻고, 비었을 때만 빌라 평형 목록을 묻는다. 아파트 평형 목록은 빌라 단지(가람아트빌 673573)와 없는 단지 번호
    (99999999)에 빈 목록을 준다 (2026-10-11). 단지 정보로 종류를 먼저 정하면 대부분인 아파트에서 1회가 더 든다.

    Args:
        pyeong_required: `--pyeong` 이 필수인 명령(real-price·market-price)인지. 평형 목록이 비었을 때 hint 가
            '--pyeong 없이 조회하세요' 대신 단지를 확인하게 한다.

    Raises:
        JibsaError: 평형 목록에 없는 번호가 있으면 NOT_FOUND.
    """
    if villa is None:
        pyeongs = pyeong_list(client, complex_number, False)
        villa = not pyeongs
        if villa:
            pyeongs = pyeong_list(client, complex_number, True)
    else:
        pyeongs = pyeong_list(client, complex_number, villa)
    # 없는 단지 번호도 아파트·빌라 평형 목록이 모두 빈 성공 응답이라(99999999, 2026-10-28 실측) 평형 정보가 없는 단지와
    # 가르려면 단지 정보를 1~2회 더 물어야 한다. 요청을 늘리지 않고 두 경우를 함께 알린다. real-price·market-price 는
    # --pyeong 이 필수라 '--pyeong 없이 조회하세요' 를 따를 수 없었다 (2026-10-28 리뷰)
    action = (
        f"'jibsa naver complex {complex_number}' 로 단지가 있는지와 평형 번호(pyeongs)를 확인하세요"
        if pyeong_required else '--pyeong 없이 조회하세요'
    )
    raise_missing_pyeongs(
        complex_number, pyeong_numbers, pyeongs,
        no_pyeong_hint=f'없는 단지 번호이거나 네이버에 평형 정보가 없는 단지입니다. {action}',
    )
    return villa


def resolve_dong_numbers(
    client: NaverClient,
    complex_number: int,
    dong_names: list[str],
    *,
    villa: bool | None = None,
) -> tuple[list[str], bool]:
    """동 이름을 단지 매물 필터가 받는 동 번호로 바꾼다. 빌라 단지인지도 함께 돌려준다.

    `villa` 를 모르면(None) 아파트 단지 동 목록부터 묻고, 비면 빌라 동 목록을 다시 묻는다. 빌라 엔드포인트가
    답하지 않으면 동 정보가 없는 아파트 단지다 (`villa_fallback_found`). 알면 그쪽 목록만 묻는다.

    Raises:
        JibsaError: 단지에 없는 동 이름이면 NOT_FOUND (힌트에 그 단지의 동 이름).
    """
    buildings = []
    if not villa:
        # 빌라 단지에도 아파트 동 목록은 result=null 이 아니라 빈 목록이 와서 unwrap 이 에러를 내지 않고 아래 빌라 동
        # 목록으로 넘어간다 (서진빌라 724112 → 빌라 동 목록 '1동', 2026-10-10)
        buildings = unwrap(
            client.run_request_complex_building_list_v1(
                NaverComplexBuildingListV1RequestParameterModel(complex_number=complex_number)
            ),
            '단지 동 목록',
        )
    # 아파트 단지라고 이미 알면 빈 동 목록이어도 빌라로 다시 묻지 않는다
    if not buildings and villa is not False:
        response = client.run_request_complex_villa_building_list_v1(
            NaverComplexVillaBuildingListV1RequestParameterModel(complex_number=complex_number)
        )
        if villa or villa_fallback_found(response):
            villa = True
            buildings = unwrap(response, '단지 동 목록')
    number_by_key = {dong_key(building.name): str(building.number) for building in buildings}
    missing = [name for name in dong_names if dong_key(name) not in number_by_key]
    if missing:
        available = ', '.join(dong_label(building.name) for building in buildings)
        # 동 표기는 건물 이름('청림빌라1차')일 수도 있어 조사를 끝 글자로 고른다
        labels = ', '.join(dong_label(dong_key(name)) for name in missing)
        raise JibsaError(
            code='NOT_FOUND',
            message=f"단지 {complex_number} 에 {labels}{particle(labels, '이/가')} 없습니다",
            hint=f'이 단지의 동: {available}' if available else '없는 단지 번호이거나 네이버에 동 정보가 없는 단지입니다. 단지 번호를 확인하고, 맞으면 --dong 없이 조회하세요',
        )
    numbers: list[str] = []
    for name in dong_names:
        number = number_by_key[dong_key(name)]
        if number not in numbers:
            numbers.append(number)
    return numbers, bool(villa)
