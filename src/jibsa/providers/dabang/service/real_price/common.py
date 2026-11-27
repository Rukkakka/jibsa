"""실거래가 기능(real_price)의 실거래·시세 흐름·단지 비교가 같이 쓰는 것: 대표 평형 찾기."""
from collections.abc import Callable

from httpx import HTTPStatusError

from jibsa.core.errors import JibsaError
from jibsa.core.notes import note
from jibsa.providers.dabang.api.client import DabangClient
from jibsa.providers.dabang.service.common.complex import (
    complex_not_found,
    fetch_complex,
    first_space_notes,
    primary_space_of,
)
from jibsa.providers.dabang.service.common.error import error_message

from typing import (
    TypeVar,
)


T = TypeVar('T')


def fetch_complex_space(fetch: Callable[[], T], complex_id: str, space_seq: int) -> T:
    """단지 평형 요청 하나. 없는 단지·평형이라는 다방 오류를 NOT_FOUND·INVALID_ARGUMENT 로 바꾼다.

    Raises:
        JibsaError: 없는 단지·평형일 때. 다른 HTTP 오류는 그대로 올린다.
    """
    try:
        return fetch()
    except HTTPStatusError as exc:
        # 다방은 없는 단지·평형에 400 과 사유를 준다 (2026-10-25 실측: 평형 1 → '존재하지 않는 평형 정보입니다.',
        # 없는 단지 → histories '존재하지 않는 단지입니다.'·charts '존재하지 않는 단지 정보입니다.'). 단지 ID 가 쿼리로 가서 403 은
        # 없는 단지가 아니라 다방 주소가 바뀐 것이다 (`is_missing_id`).
        if exc.response.status_code == 400:
            message = error_message(exc) or ''
            if '평형' in message:
                raise JibsaError(
                    code='INVALID_ARGUMENT',
                    message=f'이 단지에 없는 평형 번호입니다: {space_seq}',
                    hint=f'jibsa dabang complex {complex_id} 결과의 pyeongs[].pyeong_id 를 주세요',
                ) from None
            if '단지' in message:
                raise complex_not_found(complex_id) from None
        raise


def primary_space(client: DabangClient, complex_id: str, *, verb: str) -> tuple[int, list[str]]:
    """`--pyeong` 을 안 준 조회의 (평형 번호, 대표 평형으로 조회했다는 안내들) (단지 상세 1회).

    다방이 대표를 주지 않으면(없거나 0) 웹처럼 첫 평형을 고른다. 그때 평형 목록에서 빈 항목을 뺐으면 그 안내가 더 붙는다.

    Args:
        verb: 안내 끝말 ('찾았습니다'·'비교했습니다').

    Raises:
        JibsaError: 단지가 없거나 평형이 없을 때 (NOT_FOUND).
    """
    result = fetch_complex(client, complex_id)
    chosen = primary_space_of(result)
    if chosen is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'다방 단지의 평형을 찾지 못했습니다: {complex_id}',
            hint='jibsa dabang complex <단지ID> 결과의 pyeongs[].pyeong_id 를 --pyeong 으로 주세요',
        )
    seq, from_dabang = chosen
    name = next((space.pyeong_type for space in result.spaces or [] if space.space_seq == seq), None)
    return seq, [primary_space_note(name or str(seq), seq, verb=verb, from_dabang=from_dabang), *first_space_notes(result)]


def primary_space_note(name: str, space_seq: int, *, verb: str, from_dabang: bool) -> str:
    """`--pyeong` 을 안 줘 대표 평형으로 조회했다는 안내 (`verb`: '찾았습니다'·'비교했습니다').

    Args:
        from_dabang: 다방이 대표 평형을 줬는지. 아니면 다방 웹처럼 첫 평형을 고른 것이라 그렇게 알린다.
    """
    if not from_dabang:
        return note(
            '참고',
            f'--pyeong 을 주지 않았고 다방이 대표 평형을 주지 않아 다방 웹처럼 첫 평형({name}, pyeong_id {space_seq})으로 {verb}. '
            '다른 평형은 complex 결과의 pyeongs 에서 고르세요',
        )
    return note(
        '참고',
        f'--pyeong 을 주지 않아 다방 대표 평형({name}, pyeong_id {space_seq})으로 {verb}. '
        '다른 평형은 complex 결과의 pyeongs 에서 고르세요',
    )
