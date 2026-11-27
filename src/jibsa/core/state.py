"""상태 폴더(요청 제한 기록·브라우저 쿠키·이어 받기 표를 담는 폴더)의 위치와 안전하게 쓰기. `core/ratelimit.py`·`core/browser/`·`cli/paging.py` 가 쓴다."""

import os
import threading
import time
from contextlib import suppress
from pathlib import Path

from jibsa.core.errors import JibsaError


# Windows 는 다른 프로세스가 상태 파일을 읽는 동안(잠그지 않고 읽는 `limits`) 바꿔치기를 PermissionError 로 거절한다.
# 읽기는 금방 끝나므로 잠깐 기다려 다시 바꾼다
REPLACE_ATTEMPTS: int = 5
REPLACE_RETRY_SECONDS: float = 0.05


class StateDirError(JibsaError):
    """요청 제한 기록·브라우저 쿠키·이어 받기 표를 담는 상태 폴더를 읽거나 쓰지 못했을 때 (권한·샌드박스·디스크).

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
            message=f'상태 폴더({directory})를 쓸 수 없습니다 ({type(exc).__name__}: {exc.strerror or exc})',
            hint=(
                '모든 소스가 같은 이유로 실패하니 다른 소스로 다시 시도하지 마세요. '
                'JIBSA_STATE_DIR 환경 변수로 쓸 수 있는 폴더(예: 작업 폴더 안)를 지정하고, '
                '샌드박스에서 실행 중이면 그 폴더 쓰기와 네트워크 접근을 허용하세요'
            ),
            details={'state_dir': str(directory)},
        )


def state_dir() -> Path:
    """상태 파일 디렉터리. `JIBSA_STATE_DIR` > `$XDG_CACHE_HOME/jibsa` > `~/.cache/jibsa`."""
    override = os.environ.get('JIBSA_STATE_DIR')
    if override:
        return Path(override)
    cache_home = os.environ.get('XDG_CACHE_HOME')
    base = Path(cache_home) if cache_home else Path.home() / '.cache'
    return base / 'jibsa'


def replace_file(tmp: Path, path: Path) -> None:
    """임시 파일로 상태 파일을 바꿔치기한다. Windows 에서 다른 프로세스가 읽는 중이라 거절되면 잠깐 뒤 다시 한다."""
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_RETRY_SECONDS)


def write_text_atomic(path: Path, text: str) -> None:
    """상태 폴더의 파일을 원자적으로 바꿔 쓴다: 같은 폴더의 임시 파일에 쓴 뒤 바꿔치기한다 (`replace_file`).

    잠그지 않고 읽는 쪽(브라우저 쿠키, 이어 받기 표)도 반쯤 쓴 파일을 보지 않는다. 여러 jibsa 프로세스나 한 프로세스의 여러
    스레드가 동시에 써도 서로의 임시 파일을 덮지 않게 임시 파일 이름에 PID 와 스레드 ID 를 붙인다. PID 만 붙였을 때는 같은
    소스 클라이언트 둘을 두 스레드에서 같이 닫으면 반쯤 쓴 쿠키 파일이 올라가거나 FileNotFoundError 가 났다 (2026-11-09
    실측: 두 스레드가 300번씩 쓰니 쓰기 실패 86번, 깨진 읽기 14번). 요청 제한 상태 파일·브라우저 쿠키(`core/browser/`)·이어
    받기 표(`cli/paging.py`)가 같이 쓴다. 폴더는 부르는 쪽이 만든다.

    임시 파일은 쓰기와 바꿔치기 사이에 프로세스가 죽었을 때만 남는다. 그 사이가 아주 짧고 남아도 읽는 쪽이 보지 않아 따로
    지우지 않는다 (이어 받기 폴더는 `cli/paging.py` 가 하루 지난 파일을 지운다).

    Raises:
        OSError: 쓰거나 바꾸지 못했을 때. 임시 파일은 지운다.
    """
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        replace_file(tmp, path)
    except OSError:
        with suppress(OSError):
            tmp.unlink()
        raise
