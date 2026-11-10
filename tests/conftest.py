import pytest

from jibsa.core.browser import BrowserTransport


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """요청 제한 상태 파일을 테스트마다 임시 디렉터리에 둔다 (~/.cache 를 건드리지 않음)."""
    monkeypatch.setenv('JIBSA_STATE_DIR', str(tmp_path / 'state'))


@pytest.fixture(autouse=True)
def no_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트가 실수로 브라우저를 띄워 실제 사이트에 요청하지 않게 막는다 (CI 에는 Chromium 이 없다).

    `httpx.HTTPTransport` 를 바꿔 끼우던 테스트가 브라우저 transport 로 바뀐 뒤 실제 네이버에 요청한 일이 있었다.
    첫 화면 실패 기억(`core.browser._failed_entries`)은 `_open_page` 안에서만 읽고 쓰므로, 이것을 막으면 테스트 사이에
    남을 일이 없어 따로 비우지 않는다. 진짜 `_open_page` 를 부르는 테스트를 더하면 그 테스트에서 비운다.
    비동기 transport 는 동기 transport 를 감싸 같은 `_open_page` 를 부르므로 함께 막힌다.
    """
    message = (
        '테스트가 실제 브라우저를 띄우려 했다. client.__dict__["_client"] 에 MockTransport 를 끼우거나 '
        'BrowserTransport.handle_request 를 바꿔 끼운다'
    )

    def refuse(self: object) -> None:
        raise AssertionError(message)

    monkeypatch.setattr(BrowserTransport, '_open_page', refuse)
