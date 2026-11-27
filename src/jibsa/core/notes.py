"""결과 `notes` 의 안내 문구 (종류 태그·업데이트 안내·빈 항목 안내·덤 조회 실패 안내·이어 보기 안내). 모든 소스의 service 와 CLI 가 쓴다."""

from collections.abc import (
    Callable,
    Sequence,
)

from httpx import HTTPStatusError

from jibsa.core.korean import particle
from jibsa.core.ratelimit import RateLimitedError

from typing import (
    Literal,
    get_args,
)


# 결과 notes 의 종류. 안내 앞에 '[일부] ' 처럼 붙여 LLM 이 문장을 다 읽지 않고도 무엇을 알리는지 가른다 (docs/llm.md).
# 일부: 더 받을 매물이 있다 / 범위: 찾은 범위가 요청과 다르다 / 제외: 받은 것 중 뺀 매물·후보가 있다 / 모호: 이름이 여러 곳이라
# 하나를 골랐다 / 거래: 거래 유형을 짐작해 좁혔다 / 실패: 덤 조회가 실패했거나 대체 경로로 찾았다 / 참고: 그 밖에 읽을 때 알 것
NoteKind = Literal['일부', '범위', '제외', '모호', '거래', '실패', '참고']
NOTE_KINDS: tuple[str, ...] = get_args(NoteKind)
# 결과는 냈지만 소스가 바뀌어 jibsa 를 고쳐야 한다는 `notes` 끝말. 매일 API 감시(scripts/monitor/api_check.py)가 이 말로
# 고장을 찾으니 손으로 쓰지 않고 이 상수를 쓴다. 차단 페이지일 수도 있는 형식 오류·GraphQL 에러(당근)나 읽지 못한 글자(다방)처럼
# 단정하지 못하면 MAYBE 를 쓰고, 감시는 주된 조회의 PARSE_ERROR·상태 없는 UPSTREAM_ERROR 처럼 둘 다 고장으로 센다
UPDATE_NEEDED: str = 'jibsa 업데이트가 필요합니다'
UPDATE_MAYBE_NEEDED: str = 'jibsa 업데이트가 필요할 수 있습니다'
# 빈 항목 안내(`null_items_note`·`null_items_total_note`)가 같이 쓰는 문구. 결과 notes 에 이미 빈 항목 안내가 있는지 이 말로 가른다
NULL_ITEMS_PHRASE: str = '개가 와서 빼고 읽었습니다'
# 이어 받을 수 있는 결과의 [일부] 안내 끝말. 예전 '결과의 next 를 --next 로 주세요' 는 --next 만 붙이라는 말로 읽혀,
# 값 없이 붙인 호출이 "Option '--next' requires an argument." 로 막혔다 (2026-11-10)
NEXT_HINT: str = '이어 보려면 같은 명령에 --next <결과의 next 값> 을 붙이세요'


def note(kind: NoteKind, text: str) -> str:
    """종류 태그를 붙인 안내 (`'[일부] 조건에 맞는 매물 ...'`). 태그 없이 둔 안내는 출력할 때 [참고] 가 붙는다 (`tagged_notes`)."""
    return f'[{kind}] {text}'


# 평형 하나를 묻는 실거래(네이버·다방)는 국토부 신고에 평형 타입이 없어 전용면적이 같은 평형끼리 같은 거래를 준다.
# 2026-10-31 실측: 헬리오시티 84㎡대 네이버 평형 5개(11·12·13·14·16)가 3년 매매 165건 안팎을 서로 164~166건씩 겹쳐 주어
# 합치면 1,309건이 실제 329건이었고, 다방 84.98㎡ 평형 둘(168340·168341)도 1년 32건 중 31건이 같았다. 에이전트가 평형별로
# 받아 더하면 몇 배로 세고, 평형 하나만 보면 그 타입 거래만 본 줄 안다 (docs 에만 적어 두었을 때 둘 다 일어났다)
SAME_AREA_PYEONG_TRADES_NOTE: str = note(
    '참고',
    '국토부 신고에 평형 타입이 없어 전용면적이 같은 다른 평형에도 같은 거래가 들어 있습니다. 평형 여러 개의 거래를 합칠 때는 '
    '같은 날·층·금액을 한 번만 세세요',
)


def null_items_note(what: str, count: int, unknown: Sequence[str] = ()) -> str:
    """사이트가 객체 목록 안에 빈 항목(null)을 줘서 빼고 읽었다는 안내. 그 목록으로 계산한 값을 모를 때 이 안내를 함께 낸다.

    응답 모델이 목록 칸의 null 원소를 빼고 그 수를 센다 (`ResponseModel.null_items`). 서비스는 그 목록으로 세거나 계산한 값을
    틀린 채로 내지 않고 null 로 두거나 목록 길이에 뺀 수를 더해 센 뒤, 이 안내로 알린다. 끝말이 `UPDATE_MAYBE_NEEDED` 라
    매일 API 감시(scripts/monitor/api_check.py)가 이런 응답을 고장으로 알린다.

    Args:
        what: 사이트 이름을 붙인 목록 이름 (예: '직방 단지 매물', '네이버 관리비 항목').
        count: 빼고 읽은 빈 항목 수.
        unknown: 그 때문에 알 수 없어 null 로 둔 출력 칸 이름. 비면 그 문장을 쓰지 않는다 (자리를 세는 값만 바로잡은 경우).
    """
    names = ', '.join(unknown)
    unknown_text = f' {names} 값은 알 수 없어 null 입니다.' if names else ''
    return note('제외', f'{what} 목록에 빈 항목 {count}{NULL_ITEMS_PHRASE}.{unknown_text} {UPDATE_MAYBE_NEEDED}')


def null_items_total_note(site: str, count: int) -> str:
    """응답 어디에서든 빈 항목(null) `count` 개를 빼고 읽었다는 공통 안내. 어느 목록인지는 말하지 않는다.

    계산에 쓰지 않고 보여 주기만 하는 목록도 조용히 빼지 않게, 명령이 뺀 수의 합이 0 보다 크고 결과 notes 에 `null_items_note` 가
    없을 때 `collected_notes` 를 거쳐 `cli.output.emit`·`with_notes` 가 붙인다 (`core.schema.null_item_tally`). 끝말이 `UPDATE_MAYBE_NEEDED` 라 매일 API 감시가 알린다.

    Args:
        site: 사이트 이름 ('직방', '네이버', '당근', '다방').
        count: 응답에서 빼고 읽은 빈 항목 수.
    """
    return null_items_note(f'{site} 응답의', count)


def is_rejected(exc: Exception | None) -> bool:
    """덤 조회 실패가 거절·형식 변경인지: ValueError, 4xx, `exc` 가 None(`isSuccess` false). 서버 오류(5xx)·연결 실패는 아니다.

    참이면 업데이트 안내를 붙여 매일 API 감시가 고장으로 잡는다. 네 소스가 같은 기준을 쓴다 (네이버·다방·직방은 `lookup_failure_note`·
    `lookup_failure_reason`, 당근 `needs_update` 는 이 기준에 당근만의 실패를 더한다).
    """
    return exc is None or isinstance(exc, ValueError) or (isinstance(exc, HTTPStatusError) and exc.response.status_code < 500)


class LookupFailures:
    """덤 조회를 여러 번 하는 반복(`--details` 등)의 실패를 모아 안내 이유를 고른다.

    이유는 실패 순서가 아니라 다음 할 일로 고른다 (업데이트 필요 > 요청 제한 > 서버 오류·연결 실패). 예전에는 첫 실패만
    알려 5xx 다음 403 이면 '잠시 뒤' 만 나가 매일 감시가 거절을 놓쳤다 (2026-11-20 리뷰·사용자 결정). 종류마다 첫 예외만
    남긴다. `needs_update` 는 소스가 업데이트 안내를 붙이는 갈래와 같게 넘긴다 (기본은 `lookup_failure_reason` 의 갈래, 당근은
    `needs_update`).

    Attributes:
        count: 실패한 수 + 요청 제한 뒤라 요청하지 않은 수.
    """

    def __init__(self, needs_update: Callable[[Exception], bool] = is_rejected) -> None:
        self._needs_update = needs_update
        self.count = 0
        self._rate_limited: RateLimitedError | None = None
        self._update_needed: Exception | None = None
        self._other: Exception | None = None

    def add(self, exc: Exception) -> None:
        """실패 하나를 센다. 종류(요청 제한·업데이트 필요·그 밖)마다 첫 예외만 남긴다."""
        self.count += 1
        if isinstance(exc, RateLimitedError):
            if self._rate_limited is None:
                self._rate_limited = exc
        elif self._needs_update(exc):
            if self._update_needed is None:
                self._update_needed = exc
        elif self._other is None:
            self._other = exc

    def skip(self) -> None:
        """요청 제한 뒤라 요청하지 않은 매물을 센다."""
        self.count += 1

    @property
    def stopped(self) -> bool:
        """요청 제한이 왔는지. 참이면 부르는 쪽이 남은 매물을 요청하지 않는다 (다음 요청도 같은 제한에 걸린다)."""
        return self._rate_limited is not None

    def reason(self, describe: Callable[[Exception], str]) -> str | None:
        """안내 이유 (`describe` 로 만든 문장). 실패가 없으면 None.

        업데이트 필요가 있으면 그 이유 (요청 제한도 왔으면 덧붙임), 없으면 요청 제한, 없으면 그 밖의 첫 실패 이유다.
        업데이트가 필요하면 그 밖의 실패(5xx 등)는 말하지 않는다.
        """
        if self._update_needed is not None:
            text = describe(self._update_needed)
            if self._rate_limited is not None:
                text += f'. 요청 제한에도 걸려 그 뒤로는 요청하지 않았습니다. {self._rate_limited.message}'
            return text
        if self._rate_limited is not None:
            return describe(self._rate_limited)
        if self._other is not None:
            return describe(self._other)
        return None


def lookup_failure_reason(exc: Exception | None, site: str, what: str) -> str:
    """덤 조회 실패의 이유 한 구절 (`note('실패', ...)` 문장 뒤에 이어 쓴다). 실패 이유마다 다음 행동이 달라 이유를 넣는다.

    사이트가 요청을 거절했거나(4xx) 응답 형식이 바뀌면 업데이트 안내를 붙인다 (매일 감시가 고장으로 본다). 요청 제한·서버
    오류(5xx)·연결 실패는 사이트가 바뀐 것이 아니라 붙이지 않는다 (감시는 확인 못 함으로 본다).

    Args:
        exc: 실패 예외. None 이면 응답이 isSuccess false 였던 것이라 거절로 본다 (네이버).
        site: 사이트 이름 ('다방', '직방'). 조사는 끝 글자에 맞춘다.
        what: 받지 못한 것 ('매물 상세').
    """
    if isinstance(exc, RateLimitedError):
        return f'요청 제한에 걸렸습니다. {exc.message}'
    if is_rejected(exc):
        return f"{site}{particle(site, '이/가')} {what} 요청을 거절했거나 응답 형식이 바뀌었습니다. {UPDATE_MAYBE_NEEDED}"
    return f'{site} {what} 요청이 실패했습니다 ({type(exc).__name__}). 잠시 뒤 다시 시도하세요'


def lookup_failure_note(exc: Exception | None, site: str, what: str, unknown: str) -> str:
    """덤 조회를 받지 못한 `[실패]` 안내. 무슨 일 → 할 일 → 모름이 된 칸 순서라 모름이 된 칸이 늘 끝이다.

    요청 제한이 아니면 `lookup_failure_reason` 의 문장에 모름이 된 칸을 잇는다. 요청 제한만 따로 쓰는 것은 reason 이 받지 못한 것을 말하는 앞 문장 뒤에
    이어 쓰는 구절이라 무엇을 받지 못했는지 넣지 않기 때문이다.

    Args:
        exc: 실패 예외. `None` 이면 응답이 `isSuccess` false 였던 것이라 거절로 본다 (네이버).
        site: 사이트 이름 ('다방', '네이버'). 조사는 끝 글자에 맞춘다.
        what: 받지 못한 조회 이름 ('최근 실거래 요약').
        unknown: 그 실패로 모름이 된 칸과 다음 할 일 (끝에 마침표 없음).
    """
    if isinstance(exc, RateLimitedError):
        return note('실패', f"요청 제한에 걸려 {what}{particle(what, '을/를')} 받지 못했습니다. {exc.message}. {unknown}")
    return note('실패', f'{lookup_failure_reason(exc, site, what)}. {unknown}')


def more_hint(limit: int, max_limit: int, narrow: str | None, *, option: str = '--limit') -> str:
    """결과가 더 남았을 때 더 보는 법 (끝에 마침표 없음). `--limit` 이 이미 최대값이면 늘리라고 하지 않는다.

    늘리면 옵션 검사에서 `INVALID_ARGUMENT` 로 막힌다. 소스마다 따로 쓰던 '--limit 의 최대값은 N입니다…' 를 여기 모은다.
    따로 고치다 반경 검색 일부만 '반경' 으로 바뀌었다 (2026-11-10 리뷰·실측: 직방 아파트 강남역 --limit 120·네이버 반경
    단지 강남역이 '조건·지역을 좁히세요', 직방 상가 강남역은 '…조건·반경을 좁히세요').

    Args:
        limit: 요청한 `--limit`.
        max_limit: 그 명령의 `--limit` 최대값.
        narrow: 좁히라고 권할 것. 그 명령에 있는 옵션만 적는다 (예: '조건·반경', '거래 유형·업종·가격 조건·지역').
            None 이면 좁힐 조건을 권하지 않고 `--limit` 만 말한다 (다방 동네정보 목록처럼 좁힐 옵션을 이미 골랐을 때).
        option: 개수를 정하는 옵션 이름. 당근 `region-reviews` 는 `--limit` 이 없고 `--top` 이다 (2026-11-20).
    """
    if narrow is None:
        if limit >= max_limit:
            return f'{option} 의 최대값은 {max_limit}입니다'
        return f'더 보려면 {option} 을 늘리세요'
    target = f"{narrow}{particle(narrow, '을/를')}"
    if limit >= max_limit:
        return f'{option} 의 최대값은 {max_limit}입니다. 더 보려면 {target} 좁히세요'
    return f'더 보려면 {option} 을 늘리거나 {target} 좁히세요'


def tagged_notes(notes: list[str]) -> list[str]:
    """출력할 안내마다 종류 태그를 붙인다. 이미 붙었으면 그대로, 없으면 [참고]. 같은 안내는 한 번만 남긴다."""
    tagged = [
        text if any(text.startswith(f'[{kind}] ') for kind in NOTE_KINDS) else note('참고', text)
        for text in notes
    ]
    return list(dict.fromkeys(tagged))


def limit_notes(
    total: int | None,
    returned: int,
    limit: int,
    *,
    max_limit: int,
    narrow: str | None,
    order: str = '검색 중심에서 가까운',
    approximate: bool = False,
    inspected: int,
    offset: int = 0,
    resumable: bool = False,
    has_more: bool | None,
) -> list[str]:
    """조건에 맞는 매물이 `limit` 보다 많아 일부만 돌려줄 때의 안내.

    "역삼동" 처럼 넓게 찾으면 네이버만 4천 건이 넘는데, 몇십 건만 받은 LLM 이 그게 전부라고
    오해하지 않도록 알리고 조건이나 지역을 좁히게 한다.

    Args:
        total: 조건에 맞는 매물 수 (모르면 None).
        returned: 돌려준 매물 수.
        limit: 요청한 최대 결과 수.
        max_limit: 그 명령의 `--limit` 최대값. 이미 최대값이면 늘리라고 하지 않는다. 늘리면 옵션 검사에서 막혀
            `INVALID_ARGUMENT` 가 난다 (2026-11-10 실측: 직방 stay 서울시 --limit 120 1917건·store 역삼역 --limit 120
            2580건에 '--limit 을 늘리거나'). 빠뜨리면 같은 문제가 다시 생기므로 기본값 없이 받는다.
        narrow: 좁히라고 권할 것 전체 (`more_hint`). 그 명령에 있는 옵션만 적고, 동 경계·시군구 검색이면 '·지역', 역·좌표·
            --radius 의 반경 검색이면 '·반경' 을 붙인다 (예: 상가 반경 검색 '거래 유형·업종·가격 조건·반경'). 반경 검색에 '지역'
            을 권하면 강남역처럼 이미 좁게 찾은 검색에도 '더 좁은 지역' 이 붙고, 단지 하나의 매물처럼 좁힐 범위가 없는데 붙이면
            다방 단지 매물이 '조건·지역을 좁히세요' 라고 했다 (2026-11-10 리뷰). 예전에는 '조건'·지역 기본값과 반경·범위 플래그로
            받았는데, 빠뜨려도 조용히 '조건·지역' 이 나가 `max_limit` 처럼 기본값 없이 받는다 (`pagination_notes`·
            `apt_pagination_notes` 와 같다, 2026-11-11 리뷰). None 이면 좁힐 조건을 권하지 않는다 (좁힐 옵션을 이미 모두 골랐을 때).
        order: 돌려준 매물을 고른 기준. 뒤에 '순으로' 를 붙여 쓴다 (예: '검색 중심에서 가까운', '최근 게시된', '다방 목록').
        approximate: `total` 이 근사값이면 True ('약 N건').
        inspected: 요약을 받아 확인한 매물 수 (조회 예산). `returned` 대신 이 값으로 `limit` 에 닿았는지 본다.
            받은 뒤 거래 불가로 뺀 매물만큼 다시 채우지 않으므로, 1건만 빠져도 `returned < limit` 이 되어 안내가
            사라지던 문제를 막는다 (직방 역삼동 원룸 --limit 15 에서 1건이 빠지면 '약 660건' 안내가 없었다).
        offset: 이어 받은 검색(`--next`)에서 앞서 받은 매물 수. 몇 번째부터인지 알린다.
        resumable: 결과의 `next` 로 이어 받을 수 있으면 True. --limit 을 늘리라는 대신 next 를 쓰라고 권한다.
        has_more: 결과의 `has_more`. False 면 안내하지 않는다. `total` 은 거래 불가로 빼기 전 수라 `returned` 와 견주면, 범위 안
            매물을 다 받고 1건만 빠져도 '더 보려면 --limit 을 늘리라' 고 했다 (직방 동 경계 안 15건을 --limit 15 로 다 받고 1건이
            빠진 경우, 2026-10-23 리뷰). `max_limit` 처럼 빠뜨리지 않게 기본값 없이 받는다.
    """
    if inspected < limit or has_more is False:
        return []
    if total is None or total <= offset + returned:
        return []
    # 전체 수를 먼저 말하고 그중 몇 건을 보여 주는지 잇는다. 예전 '약 41건 중 검색 중심에서 가까운 1건입니다' 는 무엇이
    # 1건인지 바로 와닿지 않았다 (2026-11-10). 1건만 준 까닭으로 --limit 을 들지 않는다: 확인한 뒤 뺀 매물이 있으면
    # '--limit 15 라 14건' 처럼 어긋나고, 이어 받을 수 있는 검색에서 next 대신 --limit 을 늘려 처음부터 다시 찾게 한다
    found = f"조건에 맞는 매물이 {'약 ' if approximate else ''}{total}건"
    start = f'{offset + 1}번째부터 ' if offset else ''
    if returned:
        shown = f"{found} 있고, 그중 {order} 순으로 {start}{returned}건{'을' if offset else '만'} 보여 줍니다"
    else:
        # 확인한 매물이 모두 빠지면(거래 불가 등) '0건만 보여 줍니다' 가 되어 따로 쓴다
        shown = f'{found} 있지만, {order} 순으로 {start}확인한 매물이 모두 빠져 보여 줄 매물이 없습니다'
    # 안내 문장은 끝에 마침표가 없어 다른 안내와 이어 붙일 수 있다
    if resumable:
        return [note('일부', f'{shown}. {NEXT_HINT}')]
    return [note('일부', f'{shown}. {more_hint(limit, max_limit, narrow)}')]
