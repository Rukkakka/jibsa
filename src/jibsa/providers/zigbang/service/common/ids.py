"""직방 단지·건물 ID 와 단지 주소 글자: `apt-<번호>`·`officetel-<번호>` 를 만들고 읽는다."""

from jibsa.core.errors import JibsaError
from jibsa.providers.zigbang.service.common.constants import (
    COMPLEX_ID_PATTERN,
    ComplexKind,
)


def apt_complex_id(danji_id: int) -> str:
    return f'apt-{danji_id}'


def officetel_complex_id(building_id: int) -> str:
    return f'officetel-{building_id}'


def parse_complex_id(complex_id: str) -> tuple[ComplexKind, int]:
    """`apt-68579` / `officetel-20227` 를 (종류, 번호) 로 나눈다.

    Raises:
        JibsaError: 형식이 맞지 않을 때 (INVALID_ARGUMENT).
    """
    match = COMPLEX_ID_PATTERN.match(complex_id.strip())
    if match is None:
        raise JibsaError(
            code='INVALID_ARGUMENT',
            message=f"직방 단지 ID 형식이 아닙니다: '{complex_id}'",
            hint="jibsa zigbang search locations <단지 이름> 결과의 complexes[].complex_id 나 검색 결과의 complex_id "
                 "(예: 'apt-68579', 'officetel-20227') 를 그대로 주세요",
        )
    kind, number = match.groups()
    return kind, int(number)  # type: ignore[return-value]
