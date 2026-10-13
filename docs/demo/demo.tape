# README 데모 녹화 대본 (VHS, https://github.com/charmbracelet/vhs).
# 저장소 루트에서 `vhs docs/demo/demo.tape` 로 다시 찍는다. uv·jq 가 필요하다.
#
# 설치 장면은 PyPI 에서 진짜로 설치한다 (임시 폴더에 설치해 쓰던 jibsa 는 건드리지 않는다).
# 조회 장면의 `jibsa` 는 설치한 jibsa 를 fake_jibsa.py 로 실행해 직방 응답만 가상 매물(zigbang.json)로 바꾼다.
# VHS 의 Type 은 한글을 입력하지 못해, 한글 단어는 숨긴 준비에서 zsh 단축키(Ctrl+X 숫자)에 묶어 두고 그 키로 넣는다.
# 한글 고정폭 글꼴 D2Coding 이 필요하다 (`brew install --cask font-d2coding`).

Output docs/demo/demo.gif

Require uv
Require jq

Set Shell zsh
Set FontFamily "D2Coding"
Set FontSize 17
Set Width 1200
Set Height 880
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set WaitTimeout 180s

Env LANG "en_US.UTF-8"

Hide
Type `export DEMO="$PWD/docs/demo" T="$(mktemp -d)"` Enter
Type `export UV_TOOL_DIR="$T/tools" UV_TOOL_BIN_DIR="$T/bin" UV_CACHE_DIR="$T/cache" JIBSA_STATE_DIR="$T/state" PATH="$T/bin:$PATH" PROMPT='$ '` Enter
# Ctrl+X 1 → 강남역, Ctrl+X 2 → 월세, Ctrl+X 3 → 아래 매물은 데모용 가상 데이터입니다
# 무엇이 실제 정보이고 무엇이 지어낸 값인지는 README 의 데모 설명에만 적는다
Type `bindkey -s '^X1' $'\uac15\ub0a8\uc5ed' && bindkey -s '^X2' $'\uc6d4\uc138'` Enter
Type `bindkey -s '^X3' $'\uc544\ub798 \ub9e4\ubb3c\uc740 \ub370\ubaa8\uc6a9 \uac00\uc0c1 \ub370\uc774\ud130\uc785\ub2c8\ub2e4'` Enter
# 조회 전 '# …' 안내 줄을 칠 수 있게 프롬프트의 # 를 주석으로 받는다
Type `setopt interactive_comments` Enter
Type `jibsa() { "$UV_TOOL_DIR/jibsa/bin/python" "$DEMO/fake_jibsa.py" "$@"; }` Enter
Type "clear" Enter
Sleep 500ms
Show

Type "uv tool install jibsa"
Sleep 600ms
Enter
Wait+Screen /Installed 1 executable/
Sleep 2s

Type "jibsa --version"
Sleep 400ms
Enter
# 설치 직후 첫 실행은 import 가 느려 출력이 뜰 때까지 기다린다
Wait+Screen /jibsa \d/
Sleep 2s

Hide
Type "clear" Enter
Sleep 300ms
Show

Type "# "
Ctrl+X
Type "3"
Sleep 300ms
Enter
Sleep 1s

Type "jibsa zigbang search listings room "
Ctrl+X
Type "1"
Type " --trade "
Ctrl+X
Type "2"
Type " --rent-max 70 --limit 1 | jq"
Sleep 600ms
Enter
Wait+Screen /approved_at/
Sleep 8s

Hide
Type `rm -rf "$T"` Enter
