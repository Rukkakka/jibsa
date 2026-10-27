import multiprocessing
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from jibsa.cli.app import app
from jibsa.core.ratelimit import (
    RateLimitedError,
    RateLimiter,
    RateLimitPolicy,
)
from jibsa.providers.naver.api.client import NaverClient
from jibsa.providers.naver.api.request.common import NaverComplexV1RequestParameterModel


def limiter(**policy: object) -> RateLimiter:
    return RateLimiter('test', RateLimitPolicy(**policy))


def test_min_interval_spaces_reservations(monkeypatch: pytest.MonkeyPatch) -> None:
    # 기다릴 초는 '예약 시각 - 지금' 이라 예약마다 상태 파일을 잠그고 쓴 시간이 빠진다. 시계를 멈춰 느린 러너에서도
    # 간격만 본다 (멈추지 않았을 때 CI 에서 세 번 예약에 0.09초가 걸려 셋째가 1.91초로 나왔다)
    monkeypatch.setattr('jibsa.core.ratelimit.time', SimpleNamespace(time=lambda: 1000.0, sleep=time.sleep))
    first, second = limiter(min_interval=1.0), limiter(min_interval=1.0)
    # 다른 인스턴스(= 다른 프로세스)라도 같은 상태 파일을 공유한다
    assert first.reserve() == 0
    assert second.reserve() == 1.0
    assert first.reserve() == 2.0


def _reserve_many(count: int) -> None:
    worker = RateLimiter('test', RateLimitPolicy(min_interval=0))
    for _ in range(count):
        worker.reserve()


def test_concurrent_processes_keep_every_reservation() -> None:
    # 여러 jibsa 프로세스가 동시에 예약해도 상태 파일을 잠가 예약이 사라지거나 상태 쓰기가 실패하지 않는다.
    # Windows 는 fcntl 이 없어 msvcrt 로 잠근다 (잠그지 않던 때는 동시 실행이 StateDirError 로 끝날 수 있었다)
    context = multiprocessing.get_context('spawn')
    workers = [context.Process(target=_reserve_many, args=(30,)) for _ in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
    assert [worker.exitcode for worker in workers] == [0, 0, 0]
    assert limiter().status()['requests_last_minute'] == 90


def test_per_minute_budget_refuses_long_waits() -> None:
    budget = limiter(min_interval=0, max_per_minute=2, max_wait=5)
    budget.reserve()
    budget.reserve()
    with pytest.raises(RateLimitedError) as exc:
        budget.reserve()
    assert exc.value.reason == 'budget'
    assert exc.value.details['retry_after_seconds'] >= 55


def test_cooldown_blocks_until_expiry() -> None:
    cooled = limiter(min_interval=0, cooldown=60)
    cooled.block()
    with pytest.raises(RateLimitedError) as exc:
        cooled.reserve()
    assert exc.value.reason == 'cooldown'
    assert 55 <= exc.value.retry_after <= 60


def test_cooldown_set_while_waiting_stops_reserved_request() -> None:
    # 슬롯을 기다리는 동안 다른 프로세스가 429 를 받으면, 미리 잡아 둔 슬롯의 요청도 보내지 않는다
    first, second = limiter(min_interval=0.5, cooldown=60), limiter(min_interval=0.5, cooldown=60)
    first.reserve()
    blocker = threading.Timer(0.1, first.block)
    blocker.start()
    with pytest.raises(RateLimitedError) as exc:
        second.acquire()
    blocker.join()
    assert exc.value.reason == 'cooldown'


def test_retry_after_longer_than_cooldown_wins() -> None:
    cooled = limiter(cooldown=10)
    until = cooled.block(retry_after=120)
    assert until - time.time() == pytest.approx(120, abs=1)


def test_block_never_shortens_existing_cooldown() -> None:
    cooled = limiter(cooldown=10)
    long_until = cooled.block(retry_after=300)
    assert cooled.block() == long_until


def test_disabled_policy_is_noop() -> None:
    off = limiter(enabled=False, min_interval=10)
    off.block()
    assert off.reserve() == 0


def test_429_sets_cooldown_and_next_call_never_reaches_server() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(429, json={'detailCode': 'TOO_MANY_REQUESTS'})

    client = NaverClient(rate_limit=RateLimitPolicy(min_interval=0, cooldown=900))
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        event_hooks=client.rate_limit_hooks(),
    )
    parameter = NaverComplexV1RequestParameterModel(complex_number=100001)

    with client:
        # 429 를 받는 즉시 쿨다운 에러로 끝난다 (재시도 대기 없음)
        with pytest.raises(RateLimitedError) as exc:
            client.run_request_complex_v1(parameter)
        assert exc.value.reason == 'cooldown' and exc.value.retry_after > 800
        with pytest.raises(RateLimitedError):
            client.run_request_complex_v1(parameter)

    assert len(sent) == 1
    # 새 클라이언트(= 다음 CLI 실행)도 같은 쿨다운을 본다
    assert NaverClient().rate_limiter.status()['cooldown_remaining_seconds'] > 800


def test_cli_reports_cooldown_as_rate_limited() -> None:
    NaverClient().rate_limiter.block()
    result = CliRunner().invoke(app, ['naver', 'complex', '100001'])
    assert result.exit_code == 1
    assert '"code":"RATE_LIMITED"' in result.output
    assert '"retry_after_seconds"' in result.output


def test_429_on_retrying_client_fails_fast_without_waiting() -> None:
    # 직방·당근은 429 를 재시도 대상으로 두지만, 쿨다운이 걸리므로 Retry-After 만큼 기다리지 않는다.
    from jibsa.providers.zigbang.api.client import ZigbangClient
    from jibsa.providers.zigbang.api.request.region import (
        ZigbangSearchV2RequestParameterModel,
    )

    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(429, headers={'Retry-After': '30'}, json={})

    client = ZigbangClient(rate_limit=RateLimitPolicy(min_interval=0, cooldown=120))
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        event_hooks=client.rate_limit_hooks(),
    )
    started = time.monotonic()
    with client, pytest.raises(RateLimitedError):
        client.run_request_search_v2(ZigbangSearchV2RequestParameterModel(q='역삼동'))
    assert time.monotonic() - started < 1
    assert len(sent) == 1


def test_429_with_disabled_policy_stays_http_error() -> None:
    off = limiter(enabled=False)
    off.on_rate_limited(httpx.Response(429))  # 제한을 끄면 그대로 둔다 (재시도에 맡김)
