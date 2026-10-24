from typing import Any


class JibsaError(Exception):
    """CLI 가 구조화된 에러로 보고하는 애플리케이션 에러.

    Args:
        code: 기계가 읽는 에러 코드 (예: REGION_NOT_FOUND).
        message: 사람이 읽는 설명.
        hint: 다음에 시도할 행동. Defaults to None.
        details: 에러 JSON 에 함께 실을 추가 필드. Defaults to None.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}


class RegionNotFoundError(JibsaError):
    """지역명을 찾지 못했을 때.

    Args:
        query: 사용자가 준 지역명.
        hint: 다음에 시도할 행동. 기본값은 역 이름·`--lat/--lng` 를 받는 명령(직방·네이버)
            용이라, 그렇지 않은 명령(당근)은 자기 힌트를 넘긴다. Defaults to None.
    """

    def __init__(self, query: str, hint: str | None = None) -> None:
        super().__init__(
            code='REGION_NOT_FOUND',
            message=f"'{query}' 에 해당하는 지역을 찾지 못했습니다",
            hint=hint or "동 이름(예: '역삼동')이나 역 이름(예: '강남역')으로 다시 검색하거나 --lat/--lng 로 좌표를 직접 주세요",
        )


class RegionAmbiguousError(JibsaError):
    """주소·동 이름이 여러 곳에 맞아 어느 곳인지 정할 수 없을 때.

    첫 번째 후보로 검색하면 엉뚱한 지역 결과가 나오기 쉬워('중앙동 1' 은 21곳) 검색하지 않고
    후보를 알려 정확한 주소로 다시 묻게 한다.

    Args:
        query: 사용자가 준 검색어.
        candidates: 후보 주소 (앞의 몇 곳).
        total: 전체 후보 수.
        hint: 다시 묻는 법. 소스마다 받는 검색어가 달라 바꿔 줄 수 있다 (직방은 전체 주소를 받지 못한다).
            Defaults to None (첫 후보 주소를 예로 든다).
    """

    def __init__(self, query: str, candidates: list[str], total: int, hint: str | None = None) -> None:
        example = candidates[0] if candidates else '서울특별시 강남구 역삼동'
        super().__init__(
            code='REGION_AMBIGUOUS',
            message=f"'{query}' 에 해당하는 곳이 {total}곳입니다",
            hint=hint or f'시·구를 붙여 정확한 주소로 다시 검색하세요 (예: {example})',
            details={'candidates': candidates, 'candidate_count': total},
        )


class UnsupportedRegionError(JibsaError):
    """소스가 그 지역을 다루지 않을 때.

    명령에서는 에러로 보고한다. `skip_note` 는 여러 소스를 함께 찾을 때 그 소스를 건너뛴 안내로 쓰려고 둔 값이다.

    Args:
        code: 에러 코드 (REGION_NOT_FOUND, REGION_NOT_SUPPORTED).
        message: 사람이 읽는 설명.
        hint: 다음에 시도할 행동.
        skip_note: 이 소스를 건너뛰었다고 알릴 안내 (안내와 힌트를 한 문장에).
    """

    def __init__(self, code: str, message: str, hint: str, skip_note: str) -> None:
        super().__init__(code=code, message=message, hint=hint)
        self.skip_note = skip_note


class ListingUnavailableError(JibsaError):
    """매물이 없거나, 내려갔거나, 거래 완료·숨김 상태이거나, 거래 조건이 없을 때.

    Args:
        source: 소스 이름.
        listing_id: 매물 ID.
        status: 소스가 알려준 상태값 (예: TRADED, closed). 모르면 None.
        reason: 숨김·노출 거부 사유 (예: CHECK_DENY, NO_TRADE_INFO). 모르면 None.
    """

    def __init__(
        self,
        source: str,
        listing_id: str | int,
        status: str | None = None,
        reason: str | None = None
    ) -> None:
        detail = ', '.join(part for part in (status and f'status={status}', reason and f'reason={reason}') if part)
        hint = '거래할 수 없는 매물입니다 (만료·거래완료·숨김·거래 조건 없음). 이 매물은 빼고 search 로 현재 매물을 다시 찾으세요'
        if not detail:
            # 상태값이 없으면 없는 ID 라서, 다른 소스에서 받은 ID 를 넣은 경우와 가릴 수 없다. 그대로 빼라고 하면 멀쩡한 후보를
            # 버린다 (2026-10-23 실측: 직방 ID 를 naver·daangn listing 에, 네이버 ID 를 zigbang listing 에 주면 모두 이 에러)
            hint = f'다른 소스에서 받은 ID 면 그 소스의 명령으로 부르세요 (ID 는 소스끼리 통하지 않습니다). 아니면 {hint}'
        super().__init__(
            code='LISTING_UNAVAILABLE',
            message=f'현재 거래할 수 없는 {source} 매물입니다: {listing_id}' + (f' ({detail})' if detail else ' (없거나 내려간 매물)'),
            hint=hint,
            details={'listing_id': str(listing_id), 'listing_status': status, 'reason': reason},
        )
