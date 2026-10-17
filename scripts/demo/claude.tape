# README 맨 위 Claude Code 데모 녹화 대본 (VHS, https://github.com/charmbracelet/vhs).
# 저장소 루트에서 `vhs scripts/demo/claude.tape` 로 다시 찍고, `python3 scripts/demo/hide_plan.py docs/demo/claude.gif` 로
# 배너의 요금제 글자(녹화한 계정의 요금제)를 덮는다. uv·Claude Code(`claude`, 로그인)·ffmpeg 가 필요하다.
# 화면 설정과 숨긴 준비는 setup.tape 에 있다.
# Claude Code·VS Code 안에서 찍으면 그 세션의 환경 변수(아래에서 지우는 CLAUDE* 말고도 VSCODE_*·TERM_PROGRAM 등)가 녹화하는
# claude 로 넘어가니 깨끗한 환경으로 돌린다:
#   env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" SHELL=/bin/zsh TMPDIR="$TMPDIR" LANG=en_US.UTF-8 \
#     PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" vhs scripts/demo/claude.tape
#
# 실제 Claude Code 에 "직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘" 라고 시킨다. 작업 폴더(/tmp/jibsa-demo)에는
# README 가 권하는 지침 한 줄과 데모용 한 줄(claude-instructions.md → CLAUDE.md), jibsa 만 허용하는 권한과 녹화가 길어지지
# 않게 줄인 생각 깊이(claude-settings.json)를 둔다.
# Claude 가 부르는 `jibsa` 는 PyPI 에서 임시 폴더에 설치한 jibsa 를 fake_jibsa.py 로 실행해 직방 응답만 가상 매물
# (zigbang.json)로 바꾸고 그 밖의 요청은 404 로 막는다. 그래서 실제 매물은 나오지 않는다.
# Claude 의 답은 매번 조금씩 달라 깔끔한 장면이 나올 때까지 다시 찍을 수 있다.
# 녹화 전에 숨긴 채로 claude 를 한 번 열어, 처음 여는 폴더면 신뢰 질문에서 'Yes' 를 고르고 닫는다.

Output docs/demo/claude.gif

Require uv
Require claude

Source scripts/demo/setup.tape

# Claude Code 안에서 vhs 를 돌리면 그 세션의 환경 변수(CLAUDE_CODE_CHILD_SESSION 등)가 넘어와, 녹화하는 claude 가 하위 세션 경고를
# 띄운다. 숨긴 준비에서 CLAUDE* 를 지우되, 녹화하는 사람의 로그인·설정 위치(CLAUDE_CONFIG_DIR 등)는 남긴다
Type `setopt extendedglob; unset -m 'CLAUDE*~(CLAUDE_CONFIG_DIR|CLAUDE_CODE_OAUTH_TOKEN|CLAUDE_CODE_USE_*)'; unset AI_AGENT` Enter
Type `export W=/tmp/jibsa-demo` Enter
Type `uv tool install -q jibsa` Enter
# Claude 의 Bash 가 부를 수 있게 셸 함수 대신 PATH 의 실행 파일로 가상 응답 jibsa 를 둔다. PATH 에서 설치한 jibsa 보다 앞에 둔다
Type `mkdir -p "$T/bin" && printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$UV_TOOL_DIR/jibsa/bin/python" "$DEMO/fake_jibsa.py" > "$T/bin/jibsa" && chmod +x "$T/bin/jibsa" && export PATH="$T/bin:$PATH"` Enter
Type `rm -rf "$W" && mkdir -p "$W/.claude" && cp "$DEMO/claude-instructions.md" "$W/CLAUDE.md" && cp "$DEMO/claude-settings.json" "$W/.claude/settings.json" && cd "$W"` Enter
# Ctrl+X 4 → 직방에서 강남역 근처 월세 70만원 이하 원룸 찾아줘
Type `bindkey -s '^X4' $'\uc9c1\ubc29\uc5d0\uc11c \uac15\ub0a8\uc5ed \uadfc\ucc98 \uc6d4\uc138 70\ub9cc\uc6d0 \uc774\ud558 \uc6d0\ub8f8 \ucc3e\uc544\uc918'` Enter
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
# Claude Code 가 끝나 프롬프트가 돌아온 뒤에 지운다. 그 전에 치면 앞 글자를 Claude Code 가 받아 버린다.
# 녹화가 끝나기 전에 지우기가 끝나도록 한 번 더 기다린다. Wait 를 쓰지 않는 것은 VHS 가 Wait 하나만 실패해도 GIF 를
# 만들지 않아서다 (Claude Code 가 끝나지 않으면 이미 찍은 녹화까지 잃는다)
Sleep 3s
Type `cd / && rm -rf "$T" "$W"` Enter
Sleep 2s
