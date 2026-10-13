import asyncio
import json
import os
import time
from collections.abc import (
    Awaitable,
    Callable,
    Iterator,
)
from contextlib import contextmanager
from math import isfinite
from pathlib import Path

from httpx import (
    Request,
    Response,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from jibsa.core.errors import JibsaError

from typing import (
    Annotated,
    Any,
)


try:
    import fcntl
except ImportError:  # Windows: 잠금 없이 동작한다 (동시 실행 시 간격이 어긋날 수 있음)
    fcntl = None  # type: ignore[assignment]


WINDOW_SECONDS: float = 60.0


class RateLimitedError(JibsaError):
    """요청을 보내기 전에 로컬 제한으로 거절했을 때.

    Args:
        source: 소스 이름 (naver, zigbang, daangn).
        retry_after: 다시 시도할 수 있을 때까지 남은 초.
        reason: 'cooldown' (429 이후 대기 중) 또는 'budget' (분당 상한 초과).
    """

    def __init__(self, source: str, retry_after: float, reason: str) -> None:
        seconds = max(int(retry_after + 0.999), 1)
        if reason == 'cooldown':
            message = f'{source} 요청이 429 로 차단되어 쿨다운 중입니다. {seconds}초 뒤 다시 시도하세요'
            hint = '쿨다운 중에는 요청을 보내지 않습니다. 그동안 다른 소스를 쓰세요'
        else:
            message = f'{source} 분당 요청 상한에 도달했습니다. {seconds}초 뒤 다시 시도하세요'
            hint = '조회 범위(--limit, --radius)를 줄이거나 잠시 뒤 다시 시도하세요'
        super().__init__(
            code='RATE_LIMITED',
            message=message,
            hint=hint,
            details={'retry_after_seconds': seconds, 'reason': reason},
        )
        self.retry_after = retry_after
        self.reason = reason


class StateDirError(JibsaError):
    """요청 제한 상태 파일을 읽거나 쓰지 못했을 때 (권한·샌드박스·디스크).

    모든 요청이 상태 파일을 거치므로 어느 소스를 써도 같은 이유로 실패한다. 기본 INTERNAL_ERROR 힌트('다른
    소스를 쓰세요')를 따르면 에이전트가 세 소스를 헛되이 돌기 때문에 원인과 `JIBSA_STATE_DIR` 를 알린다
    (2026-10-11 실측: 쓰기 막힌 상태 폴더에서 limits·직방 검색이 모두 PermissionError).

    Args:
        directory: 상태 파일 디렉터리.
        exc: 파일 작업이 낸 예외.
    """

    def __init__(self, directory: Path, exc: OSError) -> None:
        super().__init__(
            code='INTERNAL_ERROR',
            message=f'요청 제한 상태 폴더({directory})를 쓸 수 없습니다 ({type(exc).__name__}: {exc.strerror or exc})',
            hint=(
                '모든 소스가 같은 이유로 실패하니 다른 소스로 다시 시도하지 마세요. '
                'JIBSA_STATE_DIR 환경 변수로 쓸 수 있는 폴더(예: 작업 폴더 안)를 지정하고, '
                '샌드박스에서 실행 중이면 그 폴더 쓰기와 네트워크 접근을 허용하세요'
            ),
            details={'state_dir': str(directory)},
        )


class RateLimitPolicy(BaseModel):
    """소스별 요청 제한 정책. 같은 소스를 쓰는 모든 프로세스가 공유한다.

    Args:
        min_interval: 요청 사이 최소 간격 (초).
        max_per_minute: 최근 60초 동안 허용하는 최대 요청 수. None 이면 제한 없음.
        cooldown: 429 를 받은 뒤 요청을 보내지 않는 시간 (초). 응답에
            `Retry-After` 가 있으면 그 값과 이 값 중 큰 쪽을 쓴다.
        max_wait: 한 요청이 슬롯을 기다릴 최대 시간 (초). 넘으면 기다리지 않고
            `RateLimitedError` 를 낸다.
        enabled: False 면 제한을 끈다.
    """

    model_config = ConfigDict(
        extra='forbid',
    )

    min_interval: Annotated[
        float,
        Field(ge=0, description='요청 사이 최소 간격 (초)')
    ] = 0.5
    max_per_minute: Annotated[
        int | None,
        Field(ge=1, description='최근 60초 동안 최대 요청 수')
    ] = None
    cooldown: Annotated[
        float,
        Field(ge=0, description='429 이후 요청을 멈추는 시간 (초)')
    ] = 300.0
    max_wait: Annotated[
        float,
        Field(ge=0, description='슬롯 대기 최대 시간 (초)')
    ] = 60.0
    enabled: Annotated[
        bool,
        Field(description='제한 사용 여부')
    ] = True


def _clean_state(data: Any) -> dict[str, Any]:
    """읽은 상태에서 숫자가 아닌 시각을 버린다.

    손으로 고쳤거나 깨진 값(`null`, 문자열)이 `float()` 에서 터지면 그 소스의 모든 요청과 `limits --reset` 까지
    PARSE_ERROR·INTERNAL_ERROR('다른 소스를 쓰세요')로 실패했다 (2026-10-11 실측: `{"recent": ["abc"]}`).
    다음에 쓸 때 정리된 상태로 덮어쓴다.
    """
    if not isinstance(data, dict):
        return {}
    state: dict[str, Any] = {}
    blocked_until = data.get('blocked_until')
    if isinstance(blocked_until, (int, float)) and isfinite(blocked_until):
        state['blocked_until'] = blocked_until
    recent = data.get('recent')
    if isinstance(recent, list):
        state['recent'] = [slot for slot in recent if isinstance(slot, (int, float)) and isfinite(slot)]
    return state


def state_dir() -> Path:
    """상태 파일 디렉터리. `JIBSA_STATE_DIR` > `$XDG_CACHE_HOME/jibsa` > `~/.cache/jibsa`."""
    override = os.environ.get('JIBSA_STATE_DIR')
    if override:
        return Path(override)
    cache_home = os.environ.get('XDG_CACHE_HOME')
    base = Path(cache_home) if cache_home else Path.home() / '.cache'
    return base / 'jibsa'


class RateLimiter:
    """파일 기반 요청 제한기. 프로세스가 달라도 같은 소스는 같은 파일을 공유한다.

    상태 파일(`<state_dir>/ratelimit/<source>.json`)에 최근 요청 슬롯과 쿨다운
    종료 시각을 기록하고, 읽고 쓰는 동안 `flock` 으로 잠근다. 잠금은 슬롯을
    예약하는 짧은 순간만 잡고, 실제 대기는 잠금 밖에서 한다.

    Args:
        source: 소스 이름. 상태 파일 이름이 된다.
        policy: 제한 정책.
    """

    def __init__(self, source: str, policy: RateLimitPolicy) -> None:
        self.source = source
        self.policy = policy

    @property
    def path(self) -> Path:
        return state_dir() / 'ratelimit' / f'{self.source}.json'

    def _read_state(self) -> dict[str, Any]:
        """상태 파일을 읽는다. 없거나 깨졌으면(JSON·UTF-8 해석 실패) 빈 상태.

        쓰기는 임시 파일을 바꿔치기해 원자적이라 잠그지 않고 읽어도 반쯤 쓴 파일을 보지 않는다.
        """
        try:
            state = _clean_state(json.loads(self.path.read_text(encoding='utf-8')))
        except (FileNotFoundError, ValueError):
            return {}
        except OSError as exc:
            raise StateDirError(state_dir(), exc) from exc
        # 슬롯은 예약한 때부터 max_wait 안에만 잡힌다. 그보다 먼 미래 슬롯은 시계가 뒤로 갔거나(NTP 보정·VM 복원) 손으로 고친
        # 값이라 버린다 (2026-10-11 실측: recent 에 1시간 뒤 슬롯 하나로 직방 요청이 '3600초 뒤' RATE_LIMITED). 쿨다운
        # (blocked_until)은 서버 Retry-After 만큼 길 수 있어 상한을 몰라 그대로 둔다. 풀려면 limits --reset
        if 'recent' in state:
            latest = time.time() + self.policy.max_wait
            state['recent'] = [slot for slot in state['recent'] if slot <= latest]
        return state

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, Any]]:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lock = open(path.with_suffix('.lock'), 'a+')
        except OSError as exc:
            raise StateDirError(state_dir(), exc) from exc
        with lock:
            if fcntl is not None:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                except OSError as exc:
                    # 잠금을 지원하지 않는 파일 시스템(NFS·SMB 의 ENOLCK 등)도 모든 소스에서 같이 실패한다
                    raise StateDirError(state_dir(), exc) from exc
            try:
                state = self._read_state()
                yield state
                tmp = path.with_suffix('.tmp')
                try:
                    tmp.write_text(json.dumps(state), encoding='utf-8')
                    tmp.replace(path)
                except OSError as exc:
                    raise StateDirError(state_dir(), exc) from exc
            finally:
                if fcntl is not None:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def reserve(self) -> float:
        """다음 요청 슬롯을 예약하고 그때까지 기다릴 초를 돌려준다.

        Raises:
            RateLimitedError: 쿨다운 중이거나, 슬롯까지 `max_wait` 보다 오래
                기다려야 할 때. 이 경우 슬롯을 예약하지 않는다.
        """
        if not self.policy.enabled:
            return 0.0
        with self._locked_state() as state:
            now = time.time()
            blocked_until = float(state.get('blocked_until', 0.0))
            if blocked_until > now:
                raise RateLimitedError(self.source, blocked_until - now, 'cooldown')

            recent = sorted(
                float(slot) for slot in state.get('recent', [])
                if float(slot) > now - WINDOW_SECONDS
            )
            slot = now
            if recent:
                slot = max(slot, recent[-1] + self.policy.min_interval)
            limit = self.policy.max_per_minute
            if limit is not None and len(recent) >= limit:
                slot = max(slot, recent[-limit] + WINDOW_SECONDS)

            delay = slot - now
            if delay > self.policy.max_wait:
                raise RateLimitedError(self.source, delay, 'budget')

            recent.append(slot)
            state['recent'] = recent
            return delay

    def acquire(self) -> None:
        delay = self.reserve()
        if delay > 0:
            time.sleep(delay)

    async def aacquire(self) -> None:
        # reserve() 는 상태 파일 잠금(flock)을 기다린다. 다른 jibsa 프로세스가 잠금을 잡고 있을 때 이벤트 루프가 멈추지
        # 않도록 스레드에서 부른다
        delay = await asyncio.to_thread(self.reserve)
        if delay > 0:
            await asyncio.sleep(delay)

    def block(self, retry_after: float | None = None) -> float:
        """429 를 받았을 때 쿨다운을 건다. 이미 더 긴 쿨다운이 있으면 유지한다.

        Returns:
            float: 쿨다운 종료 시각 (epoch 초).
        """
        if not self.policy.enabled:
            return 0.0
        seconds = max(self.policy.cooldown, retry_after or 0.0)
        with self._locked_state() as state:
            blocked_until = max(float(state.get('blocked_until', 0.0)), time.time() + seconds)
            state['blocked_until'] = blocked_until
            return blocked_until

    def reset(self) -> None:
        """쿨다운과 요청 기록을 지운다."""
        with self._locked_state() as state:
            state.clear()

    def status(self) -> dict[str, Any]:
        """현재 쿨다운·최근 60초 요청 수를 돌려준다. 읽기만 해서 쓰기 막힌 상태 폴더에서도 볼 수 있다."""
        state = self._read_state()
        now = time.time()
        blocked_until = float(state.get('blocked_until', 0.0))
        recent = [float(slot) for slot in state.get('recent', []) if float(slot) > now - WINDOW_SECONDS]
        return {
            'source': self.source,
            'cooldown_remaining_seconds': max(int(blocked_until - now + 0.999), 0),
            'requests_last_minute': len(recent),
            'policy': self.policy.model_dump(),
        }

    def _retry_after(self, response: Response) -> float | None:
        # core.http 의 파서를 쓰되 순환 import 를 피하려고 여기서 가져온다.
        from jibsa.core.http import retry_after_seconds

        header = response.headers.get('Retry-After')
        return retry_after_seconds(header) if header else None

    def on_rate_limited(self, response: Response) -> None:
        """429 응답이면 쿨다운을 걸고 곧바로 `RateLimitedError` 를 낸다.

        쿨다운(최소 2분)이 재시도 대기 상한(60초)보다 길어 재시도는 어차피 로컬에서
        거절된다. `HTTPStatusError` 로 두면 tenacity 가 `Retry-After` 만큼 헛되이
        기다리므로, 재시도 대상이 아닌 에러로 바로 끝낸다. 제한을 끈 정책이면
        아무것도 하지 않아 기존 429 재시도가 그대로 동작한다.
        """
        if response.status_code != 429 or not self.policy.enabled:
            return
        blocked_until = self.block(self._retry_after(response))
        raise RateLimitedError(self.source, blocked_until - time.time(), 'cooldown')

    def event_hooks(self) -> dict[str, list[Callable[..., None]]]:
        """sync httpx `Client` 용 event hooks: 요청 전 슬롯 대기, 429 응답 시 쿨다운."""
        def on_request(request: Request) -> None:
            self.acquire()

        def on_response(response: Response) -> None:
            self.on_rate_limited(response)

        return {'request': [on_request], 'response': [on_response]}

    def async_event_hooks(self) -> dict[str, list[Callable[..., Awaitable[None]]]]:
        """`AsyncClient` 용 event hooks. 동작은 `event_hooks` 와 같다."""
        async def on_request(request: Request) -> None:
            await self.aacquire()

        async def on_response(response: Response) -> None:
            # 429 면 block() 이 상태 파일 잠금을 기다리므로 aacquire 처럼 스레드에서 부른다
            if response.status_code == 429:
                await asyncio.to_thread(self.on_rate_limited, response)

        return {'request': [on_request], 'response': [on_response]}
