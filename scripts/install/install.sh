#!/bin/sh
# jibsa 설치 스크립트 (macOS·Linux)
#
#   curl -LsSf https://raw.githubusercontent.com/Rukkakka/jibsa/main/scripts/install/install.sh | sh
#
# 하는 일 (다시 실행하면 jibsa 를 최신 버전으로 올린다)
#   1. uv 가 없으면 설치한다 (https://docs.astral.sh/uv/)
#   2. uv 로 jibsa 를 설치하거나 최신 버전으로 올린다
#   3. jibsa 폴더를 셸 설정 파일의 PATH 에 등록한다 (uv tool update-shell)
#   4. Codex·Claude Code 를 쓰고 있으면 지침 파일에 jibsa 사용 규칙 한 줄을 넣는다
#
# main 브랜치의 이 파일을 사용자가 바로 받아 실행하므로, 머지하는 즉시 모든 사용자에게 적용된다.
# 내려받다 끊긴 스크립트가 반쯤 실행되지 않게 모든 일을 main 안에 두고 마지막 줄에서 부른다.

set -eu

ISSUES='https://github.com/Rukkakka/jibsa/issues'
AGENT_LINE='집을 찾을 때는 jibsa CLI 를 쓴다. 처음 쓰기 전에 `jibsa guide` 를 실행해 읽고 그 규칙을 따른다.'

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
    step '1/4 uv 확인'
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

    step '2/4 jibsa 설치 (이미 있으면 최신 버전으로 올린다)'
    "$uv" tool install --upgrade jibsa || fail 'jibsa 를 설치하지 못했다'

    step '3/4 PATH 등록'
    bin=$("$uv" tool dir --bin)
    jibsa="$bin/jibsa"
    [ -x "$jibsa" ] || fail "jibsa 를 찾지 못했다: $jibsa"
    if ! "$uv" tool update-shell; then
        printf '셸 설정 파일에 PATH 를 넣지 못했다. 쓰는 셸의 설정 파일(~/.zshrc, ~/.bashrc 등)에 아래 줄을 직접 넣는다\n'
        printf '    export PATH="%s:$PATH"\n' "$bin"
    fi

    step '4/4 에이전트 지침'
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
