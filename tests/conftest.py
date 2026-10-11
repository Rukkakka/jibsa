import pytest


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """요청 제한 상태 파일을 테스트마다 임시 디렉터리에 둔다 (~/.cache 를 건드리지 않음)."""
    monkeypatch.setenv('JIBSA_STATE_DIR', str(tmp_path / 'state'))
