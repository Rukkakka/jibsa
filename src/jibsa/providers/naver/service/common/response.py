"""네이버 응답 봉투 꺼내기 (`unwrap`)와 부가 정보 조회 결과 처리 (`result_or_*`, `[실패]` 안내), 빌라 판정 응답."""

from collections.abc import Callable

from jibsa.core.errors import JibsaError
from jibsa.core.listing import lookup_failure_note
from jibsa.providers.naver.api.models.response.common import NaverResponseModel
from jibsa.providers.naver.service.common.constants import OPTIONAL_LOOKUP_ERRORS

from typing import (
    Any,
    TypeVar,
)


T = TypeVar('T')


# 리뷰 오탐 (2026-11-24): hint 기본값은 번호 조회용이다. hint 없이 부르는 곳은 모두 평형·단지·구역·학교 번호로 부르고, 이름·좌표·목록 조회는 모두 hint 를 넘긴다
def unwrap(response: NaverResponseModel[T], what: str, *, hint: str | None = '번호가 맞는지 확인하세요') -> T:
    """봉투의 `result` 를 꺼낸다. 실패 응답이면 `JibsaError`.

    Args:
        hint: NOT_FOUND 에 붙일 안내 (UPSTREAM_ERROR 는 이 뒤에 스펙이 바뀌었을 수 있다는 말을 잇는다). 기본값은 번호를
            받는 호출용이다. 이름·좌표·목록을 받는 호출은 번호를 확인하라고 하지 않도록 그 입력에 맞는 안내를 넘기고,
            `None` 이면 번호를 말하지 않는 일반 안내를 쓴다.

    Raises:
        JibsaError: 성공 응답인데 `result` 가 비었으면 NOT_FOUND (없는 단지 번호 등),
            `isSuccess` 가 false 면 UPSTREAM_ERROR.
    """
    if response.is_success and response.result is None:
        raise JibsaError(
            code='NOT_FOUND',
            message=f'네이버 {what} 결과가 없습니다',
            hint=hint or '네이버가 결과를 주지 않았습니다. 잠시 뒤 다시 시도하세요',
        )
    if not response.is_success or response.result is None:
        raise JibsaError(
            code='UPSTREAM_ERROR',
            message=f'네이버 {what} 조회 실패: {response.detail_code or ""} {response.message or ""}'.strip(),
            hint=f'{hint}. 비공식 API 라 스펙이 바뀌었을 수 있습니다' if hint else '비공식 API 라 스펙이 바뀌었을 수 있습니다',
        )
    return response.result


def villa_fallback_found(response: NaverResponseModel[Any]) -> bool:
    """아파트 쪽이 비어 빌라 단지 엔드포인트로 다시 물은 응답이 쓸 만한지.

    아파트 단지는 매물·실거래가 없어도 아파트 쪽이 빈 목록으로 오므로 빌라로 다시 묻게 된다. 그때 빌라
    엔드포인트가 실패나 빈 `result` 를 주면 빌라 단지가 아닌 것이라, `unwrap` 처럼 에러를 내지 않고 0건으로 본다.
    """
    return response.is_success and response.result is not None


def villa_by_complex_response(response: NaverResponseModel[Any]) -> bool:
    """아파트 단지 정보(`complex`) 응답으로 빌라 단지인지 정한다.

    빌라 단지(A05·A06·A07)는 아파트 단지 엔드포인트가 성공 응답에 빈 결과(result=null)를 준다. 단지 종류를 정하는
    방법은 이것, 단지 이름 자동완성의 유형(`complex_is_villa`), 빌라 엔드포인트가 답하는지(`villa_fallback_found`)
    셋이다. 앞의 둘은 따로 묻는 1회가 들고, 셋째는 빌라 자료를 받는 요청이 곧 확인이라 아파트일 때만 1회가 헛돈다.
    판별을 명령 맨 앞에서 한 번에 하면 단지 종류를 모를 때마다(대부분 아파트) 1회가 늘어서, 일부러 아파트 쪽이
    비었을 때만 그 자리에서 정한다. 한 번 빌라로 정해지면 빌라 엔드포인트의 실패는 0건이 아니라 에러로 낸다.
    """
    return response.is_success and response.result is None


def add_failure_note(notes: list[str] | None, exc: Exception | None, what: str, unknown: str) -> None:
    """`[실패]` 안내를 notes 에 더한다. notes 가 None 이면 호출부가 스스로 알리는 것이라 아무것도 안 하고, 같은 안내는 한 번만 낸다.

    한 명령에서 같은 조회를 여러 번 부르는 자리(평형마다 등)가 있어 같은 글자를 거듭 붙이지 않는다.

    갈래(네이버가 거절(4xx·`isSuccess` false)했거나 응답 형식이 바뀌면 업데이트 안내, 서버 오류·연결 실패면 붙이지 않음)와
    문구는 core/listing.py 의 `lookup_failure_note` 다. 요청 제한 `RateLimitedError` 는 덤 조회가 잡지 않아 여기 오지 않는다.

    Args:
        exc: 실패 예외. `None` 이면 `isSuccess` 가 false 였던 것이다.
        what: 받지 못한 조회 이름 ('관리비').
        unknown: 그 실패로 모름이 된 칸 (끝에 마침표 없음). '모름(null)으로 낸 칸: a, b' 꼴로 써 영어 필드 이름 뒤에 조사가 붙지 않게 한다.
    """
    if notes is None:
        return
    text = lookup_failure_note(exc, '네이버', what, unknown)
    if text not in notes:
        notes.append(text)


def result_or_none(
    request: Callable[[], NaverResponseModel[T]],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> T | None:
    """부가 정보 조회. 실패하면 그 값만 모름(None)으로 두고 `notes` 에 `[실패]` 안내를 붙인다 (매물 상세·단지 요약 전체를 실패시키지 않는다).

    예외면 `[실패]` 안내를 붙인다. `isSuccess` false·`result` null 은 안내 없이 None 이다.

    Args:
        notes: 안내를 붙일 목록. `None` 은 호출부가 실패를 스스로 알린다는 뜻이다 (지역 해석).
        what: 조회 이름 ('관리비'). core/listing.py 의 `lookup_failure_note` 를 보라.
        unknown: 모름이 된 칸 ('모름(null)으로 낸 칸: a, b').
    """
    return result_with_null_items(request, notes=notes, what=what, unknown=unknown)[0]


def result_with_null_items(
    request: Callable[[], NaverResponseModel[T]],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> tuple[T, int] | tuple[None, int]:
    """`result_or_none` 와 같되, `result` 가 객체 목록일 때 그 목록에서 빈 항목(null)을 빼고 읽은 수도 돌려준다.

    목록이 `result` 자리라 `result_or_none` 은 봉투를 버리면서 뺀 수도 버린다. 그 목록으로 계산하거나 자리를 세는 호출부가 쓴다.
    조회가 실패했거나 `result` 가 비었으면 `(None, 0)` 이다. 반환형이 `tuple[T | None, int]` 가 아닌 것은 mypy 가 그 꼴이면 T 를
    `T | None` 으로 잘못 풀어 호출부가 타입 오류를 내서다.
    """
    try:
        response = request()
    except OPTIONAL_LOOKUP_ERRORS as exc:
        add_failure_note(notes, exc, what, unknown)
        return None, 0
    # 리뷰 오탐 (2026-11-24): isSuccess false 를 [실패] 로 보지 않는다. 네이버는 고장이 아닌 응답에도 200 + isSuccess false 를 준다 (상가 2662726134·토지 2663300403 의 article/maintenanceFee 가 {isSuccess: false, result: {}}, 웹 ArticlePriceInfo 는 이를 무시하고 article/oldMaintenanceFee 로 넘어간다). 진짜 거절과 가릴 수 없어 값 없음으로 둔다
    result = response.result
    if result is None:
        return None, 0
    return result, response.null_items('result')


def result_or_empty(
    request: Callable[[], NaverResponseModel[T]],
    empty: Callable[[], T],
    *,
    notes: list[str] | None,
    what: str,
    unknown: str,
) -> T | None:
    """부가 정보 조회. 실패하면(예외·`isSuccess` false) 모름(None)이고 `notes` 에 `[실패]` 안내를 붙인다. 성공했는데 `result` 가 null 이면 네이버가 주지 않은 것이라 `empty()`.

    `result_or_none` 은 `result` null 도 None 으로 합쳐, 성공 응답을 '조회 실패(모름)' 로 내게 된다. 서버가 빈 목록·빈 객체를 주는 자리에
    `result: null` 이 와도 그 빈 응답과 같게 읽을 때 쓴다 (`empty` 는 `list` 나 빈 모델 클래스처럼 빈 값을 만드는 호출 가능한 것).

    Args:
        notes: 안내를 붙일 목록. `None` 은 호출부가 실패를 스스로 알린다는 뜻이다.
        what: 조회 이름. unknown: 모름이 된 칸. `result_or_none` 과 같다.
    """
    try:
        response = request()
    except OPTIONAL_LOOKUP_ERRORS as exc:
        add_failure_note(notes, exc, what, unknown)
        return None
    if not response.is_success:
        add_failure_note(notes, None, what, unknown)
        return None
    return empty() if response.result is None else response.result
