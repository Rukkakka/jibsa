# README 데모 녹화 대본 (VHS, https://github.com/charmbracelet/vhs).
# 저장소 루트에서 `vhs scripts/demo/demo.tape` 로 다시 찍는다. uv·jq 가 필요하다. 화면 설정과 숨긴 준비는 setup.tape 에 있다.
#
# 설치 장면은 PyPI 에서 진짜로 설치한다 (임시 폴더에 설치해 쓰던 jibsa 는 건드리지 않는다).
# 조회 장면의 `jibsa` 는 설치한 jibsa 를 fake_jibsa.py 로 실행해 직방 응답만 가상 매물(zigbang.json)로 바꾼다.

Output docs/demo/demo.gif

Require uv
Require jq

Source scripts/demo/setup.tape

# Ctrl+X 1 → 강남역, Ctrl+X 2 → 월세
Type `bindkey -s '^X1' $'\uac15\ub0a8\uc5ed' && bindkey -s '^X2' $'\uc6d4\uc138'` Enter
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
# 녹화가 끝나기 전에 지우기가 끝나도록 프롬프트가 돌아오기를 기다린다
Wait /\$ ?$/
