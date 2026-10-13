# README 'LLM 에이전트에 연결하기' 데모 녹화 대본 (VHS, https://github.com/charmbracelet/vhs).
# 저장소 루트에서 `vhs docs/demo/claude.tape` 로 다시 찍고, `python3 docs/demo/hide_plan.py docs/demo/claude.gif` 로
# 배너의 요금제 글자(녹화한 계정의 요금제)를 덮는다. uv·Claude Code(`claude`, 로그인)·ffmpeg 가 필요하다.
#
# 실제 Claude Code 에 "직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘" 라고 시킨다. 작업 폴더(/tmp/jibsa-demo)에는
# README 가 권하는 지침 한 줄과 데모용 한 줄(claude-instructions.md → CLAUDE.md), jibsa 만 허용하는 권한과 녹화가 길어지지
# 않게 줄인 생각 깊이(claude-settings.json)를 둔다.
# Claude 가 부르는 `jibsa` 는 PyPI 에서 임시 폴더에 설치한 jibsa 를 fake_jibsa.py 로 실행해 직방 응답만 가상 매물
# (zigbang.json)로 바꾸고 그 밖의 요청은 404 로 막는다. 그래서 실제 매물은 나오지 않는다.
# Claude 의 답은 매번 조금씩 달라 깔끔한 장면이 나올 때까지 다시 찍을 수 있다.
# 녹화 전에 숨긴 채로 claude 를 한 번 열어, 처음 여는 폴더면 신뢰 질문에서 'Yes' 를 고르고 닫는다.
# 한글은 demo.tape 처럼 zsh 단축키(Ctrl+X 숫자)로 넣는다. 한글 고정폭 글꼴 D2Coding 이 필요하다.

Output docs/demo/claude.gif

Require uv
Require claude

Set Shell zsh
Set FontFamily "D2Coding"
Set FontSize 17
Set Width 1200
Set Height 880
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set WaitTimeout 300s

Env LANG "en_US.UTF-8"

Hide
Type `export DEMO="$PWD/docs/demo" T="$(mktemp -d)" W=/tmp/jibsa-demo` Enter
Type `export UV_TOOL_DIR="$T/tools" UV_TOOL_BIN_DIR="$T/tools-bin" UV_CACHE_DIR="$T/cache" JIBSA_STATE_DIR="$T/state" PROMPT='$ '` Enter
Type `uv tool install -q jibsa` Enter
# Claude 의 Bash 가 부를 수 있게 셸 함수 대신 PATH 의 실행 파일로 가상 응답 jibsa 를 둔다
Type `mkdir -p "$T/bin" && printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$UV_TOOL_DIR/jibsa/bin/python" "$DEMO/fake_jibsa.py" > "$T/bin/jibsa" && chmod +x "$T/bin/jibsa" && export PATH="$T/bin:$PATH"` Enter
Type `rm -rf "$W" && mkdir -p "$W/.claude" && cp "$DEMO/claude-instructions.md" "$W/CLAUDE.md" && cp "$DEMO/claude-settings.json" "$W/.claude/settings.json" && cd "$W"` Enter
# Ctrl+X 3 → 아래 매물은 데모용 가상 데이터입니다, Ctrl+X 4 → 직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘
Type `bindkey -s '^X3' $'\uc544\ub798 \ub9e4\ubb3c\uc740 \ub370\ubaa8\uc6a9 \uac00\uc0c1 \ub370\uc774\ud130\uc785\ub2c8\ub2e4'` Enter
Type `bindkey -s '^X4' $'\uc9c1\ubc29\uc5d0\uc11c \uac15\ub0a8\uc5ed \uadfc\ucc98 \uc6d4\uc138 70\ub9cc\uc6d0 \uc774\ud558 \uc6d0\ub8f8 \ucc3e\uc544\uc918'` Enter
Type "setopt interactive_comments" Enter
# 폴더 신뢰: 질문이 뜨면 기본값이 'No, exit' 라 아래로 옮겨 고른다. 이미 신뢰한 폴더면 빈 입력창이라 아무 일도 없다
Type "claude" Enter
Wait+Screen /trust this folder|Claude Code v/
Sleep 1s
Down
Enter
Wait+Screen /Claude Code v/
Sleep 1s
Type "/exit"
Sleep 1s
Enter
Sleep 2s
Type "clear" Enter
Sleep 500ms
Show

Type "# "
Ctrl+X
Type "3"
Sleep 300ms
Enter
Sleep 1s

Type "cat CLAUDE.md"
Sleep 400ms
Enter
Sleep 2s

Type `claude "`
Ctrl+X
Type "4"
Type `"`
Sleep 600ms
Enter
# 답이 끝나면 '… for 30s · done' 줄이 뜬다. 답을 읽을 시간을 둔다
Wait+Screen /\d+s · done/
Sleep 10s

Hide
Ctrl+C
Ctrl+C
Type `cd / && rm -rf "$T" "$W"` Enter
