# demo.tape·claude.tape 가 맨 앞에서 `Source` 로 불러 쓰는 공통 화면 설정과 숨긴 준비. 혼자 돌리지 않는다.
# 창 크기·글꼴·여백을 바꾸면 hide_plan.py 의 좌표(PLAN_BOX·LOGO_*)도 다시 잰다. 그 값은 이 설정으로 찍은 화면에서 쟀다.
# 한글 고정폭 글꼴 D2Coding 이 필요하다 (`brew install --cask font-d2coding`).
# VHS 의 Type 은 한글을 입력하지 못해, 한글 문장은 숨긴 준비에서 zsh 단축키(Ctrl+X 숫자)에 묶어 두고 그 키로 넣는다.

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
# jibsa 는 임시 폴더($T)에 설치해 쓰던 jibsa 를 건드리지 않는다. 각 대본이 녹화 끝에 $T 를 지운다
Type `export DEMO="$PWD/scripts/demo" T="$(mktemp -d)"` Enter
Type `export UV_TOOL_DIR="$T/tools" UV_TOOL_BIN_DIR="$T/tools-bin" UV_CACHE_DIR="$T/cache" JIBSA_STATE_DIR="$T/state" PATH="$T/tools-bin:$PATH" PROMPT='$ '` Enter
# Ctrl+X 3 → 아래 매물은 데모용 가상 데이터입니다
# 무엇이 실제 정보이고 무엇이 지어낸 값인지는 README 의 데모 설명에만 적는다
Type `bindkey -s '^X3' $'\uc544\ub798 \ub9e4\ubb3c\uc740 \ub370\ubaa8\uc6a9 \uac00\uc0c1 \ub370\uc774\ud130\uc785\ub2c8\ub2e4'` Enter
# 조회 전 '# …' 안내 줄을 칠 수 있게 프롬프트의 # 를 주석으로 받는다
Type `setopt interactive_comments` Enter
