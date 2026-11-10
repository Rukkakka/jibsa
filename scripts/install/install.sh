#!/bin/sh
# jibsa 설치 스크립트 (macOS·Linux)
#
#   curl -LsSf https://raw.githubusercontent.com/Rukkakka/jibsa/main/scripts/install/install.sh | sh
#
# 하는 일 (다시 실행하면 jibsa 를 최신 버전으로 올린다)
#   1. uv 가 없으면 설치한다 (https://docs.astral.sh/uv/)
#   2. uv 로 jibsa 를 설치하거나 최신 버전으로 올린다
#   3. jibsa 폴더를 셸 설정 파일의 PATH 에 등록한다 (uv tool update-shell)
#   4. jibsa 가 사이트를 열 때 쓰는 Chromium 을 받는다 (jibsa install-browser, 이미 있으면 건너뛴다)
#   5. Codex·Claude Code 를 쓰고 있으면 지침 파일에 jibsa 사용 규칙 한 줄을 넣는다
#
# main 브랜치의 이 파일을 사용자가 바로 받아 실행하므로, 머지하는 즉시 모든 사용자에게 적용된다.
# JIBSA_INSTALL_SPEC 로 설치할 대상(기본 PyPI 의 jibsa)을 바꿀 수 있다. CI 가 PR 의 코드를 이 스크립트로 설치해 보려고 쓴다
# (.github/workflows/ci.yml 의 '브라우저 확인').
# 내려받다 끊긴 스크립트가 반쯤 실행되지 않게 모든 일을 main 안에 두고 마지막 줄에서 부른다.

set -eu

ISSUES='https://github.com/Rukkakka/jibsa/issues'
AGENT_LINE='집을 찾을 때는 jibsa CLI 를 쓴다. 처음 쓰기 전에 `jibsa guide` 를 실행해 읽고 그 규칙을 따른다.'
# jibsa 가 지금 보장하는 Python (CI 가 세 운영체제에서 확인한 범위). jibsa 는 requires-python 에 상한을 두지 않고, uv 는
# 상한이 있어도 보지 않아 Python 이 없는 컴퓨터에서는 가장 새 Python(2026-11 기준 3.15)을 받아 설치했다. 그래서 여기서 범위를
# 준다. 이미 이 범위의 Python 이 있으면 그것을 쓰고, 없으면 uv 가 범위 안에서 받는다 (docs/development/release.md '새 Python 지원')
PYTHON_RANGE='>=3.11,<3.15'

step() { printf '\n==> %s\n' "$1"; }

fail() {
    printf '\n설치하지 못했다: %s\n' "$1" >&2
    printf '해결되지 않으면 이 화면을 캡처해 이슈로 알려 준다: %s\n' "$ISSUES" >&2
    exit 1
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    for dir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
            printf '%s\n' "$dir/uv"
            return 0
        fi
    done
    return 1
}

add_agent_line() {
    name=$1
    dir=$2
    file="$dir/$3"
    [ -d "$dir" ] || return 0
    if [ -f "$file" ] && grep -q 'jibsa guide' "$file"; then
        printf '%s 지침 파일에 이미 jibsa 규칙이 있다: %s\n' "$name" "$file"
        return 0
    fi
    if [ -s "$file" ]; then
        # 마지막 줄에 줄바꿈이 없으면 붙이고, 기존 내용과 한 줄 띄운다
        [ -z "$(tail -c 1 "$file")" ] || printf '\n' >>"$file"
        printf '\n' >>"$file"
    fi
    printf '%s\n' "$AGENT_LINE" >>"$file"
    printf '%s 지침 파일에 jibsa 규칙을 넣었다: %s\n' "$name" "$file"
}

main() {
    step '1/5 uv 확인'
    if uv=$(find_uv); then
        printf 'uv 가 이미 있다: %s\n' "$uv"
    else
        printf 'uv 가 없어 설치한다\n'
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        elif command -v wget >/dev/null 2>&1; then
            wget -qO- https://astral.sh/uv/install.sh | sh
        else
            fail 'curl 이나 wget 이 필요하다 (Ubuntu·Debian: sudo apt install curl)'
        fi
        uv=$(find_uv) || fail 'uv 설치가 끝나지 않았다. 위의 uv 설치 메시지를 확인한다'
    fi

    step '2/5 jibsa 설치 (이미 있으면 최신 버전으로 올린다)'
    "$uv" tool install --upgrade --python "$PYTHON_RANGE" "${JIBSA_INSTALL_SPEC:-jibsa}" || fail 'jibsa 를 설치하지 못했다'

    step '3/5 PATH 등록'
    bin=$("$uv" tool dir --bin)
    jibsa="$bin/jibsa"
    [ -x "$jibsa" ] || fail "jibsa 를 찾지 못했다: $jibsa"
    if ! "$uv" tool update-shell; then
        printf '셸 설정 파일에 PATH 를 넣지 못했다. 쓰는 셸의 설정 파일(~/.zshrc, ~/.bashrc 등)에 아래 줄을 직접 넣는다\n'
        printf '    export PATH="%s:$PATH"\n' "$bin"
    fi

    step '4/5 브라우저(Chromium) 설치 (이미 있으면 건너뛴다)'
    # 이 스크립트는 main 에서 바로 받지만 jibsa 는 PyPI 에서 온다. install-browser 가 없는 jibsa 면 건너뛴다.
    # 브라우저를 받지 못하면 에이전트 지침(5단계) 전에 멈춘다. 쓸 수 없는 도구를 지침에 넣지 않으려는 것이다. 고친 뒤 이
    # 스크립트를 다시 실행하면 지침까지 넣으므로, 실패 안내도 install-browser 만이 아니라 스크립트를 다시 실행하라고 한다.
    # exit 2 만 없는 명령(옛 jibsa)이다. 그 밖의 실패는 jibsa 가 뜨지도 않은 것이라(import 실패 등은 1) 건너뛰지 않고 멈춘다
    browser_help=0
    "$jibsa" install-browser --help >/dev/null 2>&1 || browser_help=$?
    if [ "$browser_help" -eq 2 ]; then
        printf '이 jibsa 버전은 브라우저를 쓰지 않아 건너뛴다\n'
    elif [ "$browser_help" -ne 0 ]; then
        # 버린 에러를 보이려고 한 번 더 부른다
        "$jibsa" install-browser --help >&2 || true
        fail "jibsa 를 실행하지 못했다 (exit $browser_help). 위 에러를 해결한 뒤 이 설치 스크립트를 다시 실행한다"
    else
        # 결과 JSON 은 버리고, 내려받기 진행과 실패 안내(에러 JSON 의 hint)는 stderr 로 보인다
        "$jibsa" install-browser >/dev/null \
            || fail "브라우저(Chromium)를 설치하지 못했다. 위 에러의 hint 를 따른 뒤 이 설치 스크립트를 다시 실행한다 ('jibsa install-browser' 만 다시 하면 에이전트 지침 단계가 빠진다)"
    fi

    step '5/5 에이전트 지침'
    codex_home=${CODEX_HOME:-$HOME/.codex}
    claude_home=$HOME/.claude
    if [ ! -d "$codex_home" ] && [ ! -d "$claude_home" ]; then
        printf 'Codex·Claude Code 설정 폴더가 없어 건너뛴다. 다른 에이전트는 지침 파일에 아래 한 줄을 적는다\n'
        printf '  %s\n' "$AGENT_LINE"
    fi
    add_agent_line 'Codex' "$codex_home" 'AGENTS.md'
    add_agent_line 'Claude Code' "$claude_home" 'CLAUDE.md'

    step '설치 확인'
    "$jibsa" --version || fail 'jibsa --version 이 실패했다'

    printf '\n설치를 마쳤다.\n'
    case ":$PATH:" in
        *":$bin:"*)
            printf '%s\n' '- 이 창에서 바로 jibsa 를 쓸 수 있다'
            ;;
        *)
            printf '%s\n' '- 새 터미널을 열면 jibsa 를 쓸 수 있다. 이 창에서 바로 쓰려면 아래 줄을 먼저 실행한다'
            printf '    export PATH="%s:$PATH"\n' "$bin"
            printf '%s\n' '- 에이전트(Codex 등)도 새로 연 터미널에서 켠다. 예전 창에서 켜면 jibsa 를 못 찾는다'
            ;;
    esac
    printf '%s\n' '- 해 보기: jibsa zigbang search listings room 강남역 --trade 월세 --limit 3'
    printf '%s\n' '- Codex 에서 조회가 막히면 Codex 안에서 /permissions 로 Full Access 를 고른다 (기본 샌드박스가 인터넷과 작업 폴더 밖 쓰기를 막는다)'
}

main "$@"
