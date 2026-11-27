"""`jibsa install-browser` 가 부르는 Chromium 설치."""

import logging
import subprocess
import sys

from jibsa.core.browser.errors import (
    launch_error,
    playwright_error,
)
from jibsa.core.errors import JibsaError


logger = logging.getLogger(__name__)


def install_chromium() -> dict[str, str]:
    """jibsa 가 쓰는 Chromium 을 내려받고(이미 있으면 건너뛴다) 실제로 한 번 띄워 본다 (`jibsa install-browser`).

    jibsa 의 patchright 로 받으므로 patchright 버전에 맞는 Chromium 이 깔린다. jibsa 는 전체 Chromium
    (`channel='chromium'`)만 띄워 headless 셸은 받지 않는다 (`--no-shell`, 약 270MB 덜 받는다). 내려받기 진행은
    사람이 볼 때(stderr 가 터미널이거나 `--verbose`)만 patchright 가 stderr(fd 2)에 바로 쓴다. 에이전트처럼 stderr 를
    파이프로 읽으면 에러 JSON 만 가도록 진행 출력을 받아 두었다가, 실패하면 원인 몇 줄을 에러 JSON 의 `output` 에 싣는다.

    Raises:
        JibsaError: 내려받지 못했으면 BROWSER_INSTALL_FAILED, 받았는데 띄우지 못했으면 BROWSER_UNAVAILABLE.
    """
    show_progress = sys.stderr.isatty() or logger.isEnabledFor(logging.INFO)
    done = subprocess.run(
        [sys.executable, '-m', 'patchright', 'install', '--no-shell', 'chromium'],
        stdout=2 if show_progress else subprocess.PIPE, stderr=None if show_progress else subprocess.STDOUT, check=False,
    )
    if done.returncode != 0:
        # Node 스택 줄(`at ...`)은 빼고 원인 문장만 싣는다
        output = [] if show_progress else [
            line for line in done.stdout.decode(errors='replace').splitlines()
            if line.strip() and not line.lstrip().startswith('at ')
        ][-5:]
        raise JibsaError(
            code='BROWSER_INSTALL_FAILED',
            message=f'Chromium 을 내려받지 못했습니다 (patchright install 종료 코드 {done.returncode})',
            hint=(
                f"{'위에 나온 patchright 메시지' if show_progress else '이 에러의 output'}에 원인(네트워크·권한 등)이 있습니다. "
                '네트워크(회사망·프록시 차단 등)면 확인하고 다시 실행하고, 권한 오류(PermissionError 등)면 보안 프로그램이 '
                '막았거나 설치가 깨진 것이라 jibsa 를 다시 설치하세요'
            ),
            details={'output': output} if output else None,
        )
    # 모듈 docstring 대로 브라우저를 쓸 때만 불러온다
    from patchright.sync_api import sync_playwright

    # OSError(드라이버 node 를 실행하지 못함)는 `_launch` 와 달리 잡지 않는다. 그때는 위 `patchright install` 하위 프로세스가
    # 같은 드라이버를 먼저 실행하다 실패해 BROWSER_INSTALL_FAILED 로 끝나 여기까지 오지 않는다 (2026-11-10 실측: 드라이버
    # 실행 권한을 뺀 patchright 사본에서 install 이 PermissionError, 종료 코드 1)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel='chromium')
            version = browser.version
            browser.close()
            executable = playwright.chromium.executable_path
    except playwright_error() as error:
        raise launch_error(error) from error
    return {'browser': 'chromium', 'version': version, 'executable': executable}
