"""환경 변수·OS 프록시 설정을 Chromium 프록시 설정으로 바꾼다."""

import urllib.request
from urllib.parse import (
    unquote,
    urlsplit,
)

from httpx import ProxyError

from typing import Literal


# Chromium 이 받는 프록시 스킴과, curl·httpx 에서 쓰던 스킴을 Chromium 스킴으로 바꾸는 표 (`proxy_settings`)
BROWSER_PROXY_SCHEMES: frozenset[str] = frozenset({'http', 'https', 'socks4', 'socks5'})
PROXY_SCHEME_ALIASES: dict[str, str] = {'socks5h': 'socks5', 'socks4a': 'socks4'}


def proxy_settings(proxy: str | None, target_url: str) -> dict[str, str] | Literal['direct'] | None:
    """브라우저에 넘길 Playwright 프록시 설정. 'direct' 면 프록시 없이 바로 연결하고, None 이면 Chromium 이 OS 프록시 설정을 쓴다.

    `proxy` 를 주지 않았으면 환경 변수(`HTTPS_PROXY`·`ALL_PROXY`·`NO_PROXY`, 소문자도)를 읽는다. httpx 는 transport 를
    넘기면 환경 변수 프록시를 쓰지 않고, Chromium 은 GNOME 리눅스·Windows·macOS 에서 환경 변수 대신 OS 설정을 봐서
    예전(httpx)처럼 환경 변수에 기대던 사용자가 프록시를 잃는다 (2026-11-09 실측: GNOME 세션에서 HTTP_PROXY 무시).
    `NO_PROXY=*` 는 httpx 처럼 어떤 프록시도 쓰지 않는다는 뜻이라, None 으로 두면 Chromium 이 OS 프록시로 보내 'direct' 다.
    scrapling 의 문자열 `proxy` 는 비밀번호의 `%XX` 를 풀지 않고 스킴 없는 주소(`127.0.0.1:8080`)를 받지 않아 직접 나눈다.

    Chromium 은 http·https·socks4·socks5 프록시만 받는다. curl·httpx 의 `socks5h`(프록시가 이름을 푼다)·`socks4a` 는 Chromium 의
    socks5·socks4 가 이미 그렇게 해 바꿔 넘긴다. 그대로 넘기면 `ERR_NO_SUPPORTED_PROXIES` 였다 (2026-11-09 실측).

    Raises:
        ProxyError: 프록시 주소를 해석할 수 없거나(포트가 숫자가 아님 등), Chromium 이 받지 않는 스킴이거나, SOCKS 프록시에
            아이디·비밀번호가 있을 때 (Chromium 이 지원하지 않아 띄우다 실패하고 BROWSER_UNAVAILABLE 이 됐다, 같은 날 실측).
            메시지에 비밀번호는 넣지 않는다.
    """
    bypass: list[str] = []
    # 빈 문자열(`proxy=''`)은 '프록시 없음'이 아니라 잘못된 주소로 보고 아래에서 ProxyError 를 낸다. 0.10.0 의 httpx
    # 도 `proxy=''` 를 `ValueError: Unknown scheme for proxy URL` 로 거절했다 (2026-11-10 리뷰에서 확인하고 그대로 둠). 환경
    # 변수를 따르려면 None, 프록시 없이 바로 연결하려면 `NO_PROXY=*` 다
    if proxy is None:
        proxies = urllib.request.getproxies_environment()
        proxy = proxies.get(urlsplit(target_url).scheme) or proxies.get('all')
        no_proxy = [entry.strip() for entry in proxies.get('no', '').split(',') if entry.strip()]
        if '*' in no_proxy:
            return 'direct'
        if not proxy:
            return None
        for entry in no_proxy:
            entry = entry.split('://', 1)[-1]
            # 스킴만 적은 항목(`http://`)은 뺄 호스트가 없어 건너뛴다 (빈 문자열이면 아래 entry[0] 이 IndexError 였다)
            if not entry:
                continue
            bypass.append(entry)
            # curl·httpx 처럼 example.com 이 하위 도메인까지 덮게 한다 (Chromium 은 그 호스트만 뺀다)
            if entry[0].isalpha() and entry != 'localhost' and not entry.startswith('.'):
                bypass.append(f'*.{entry}')
    parts = urlsplit(proxy if '://' in proxy else f'http://{proxy}')
    # 아이디·비밀번호를 뺀 주소. 에러 메시지에 쓴다
    shown = f'{parts.scheme}://{parts.netloc.rpartition("@")[2]}'
    scheme = PROXY_SCHEME_ALIASES.get(parts.scheme.lower(), parts.scheme.lower())
    hostname = parts.hostname
    try:
        port = parts.port
    except ValueError as error:
        raise ProxyError(f'프록시 주소를 해석하지 못했습니다 ({shown}): {error}') from None
    if scheme not in BROWSER_PROXY_SCHEMES or not hostname:
        raise ProxyError(
            f'브라우저가 쓸 수 없는 프록시 주소입니다 ({shown}). http·https·socks4·socks5 프록시만 쓸 수 있습니다'
        )
    if scheme.startswith('socks') and (parts.username or parts.password):
        raise ProxyError(f'브라우저(Chromium)는 아이디·비밀번호가 있는 SOCKS 프록시를 쓰지 못합니다 ({shown})')
    host = f'[{hostname}]' if ':' in hostname else hostname
    settings = {'server': f'{scheme}://{host}' + (f':{port}' if port else '')}
    if parts.username:
        settings['username'] = unquote(parts.username)
    if parts.password:
        settings['password'] = unquote(parts.password)
    if bypass:
        settings['bypass'] = ','.join(bypass)
    return settings
