---
name: api-broken
description: 매일 API 감시가 연 api-broken 이슈(또는 고장 난 명령)를 받아 깨진 명령을 재현하고, 원인과 고칠 계획을 보고한다. 감시 고장 대응을 요청받았을 때 쓴다.
argument-hint: "[이슈 번호, 비우면 열린 api-broken 이슈]"
effort: high
---

`docs/development/README.md` 의 "매일 API 감시" 와 소스 가이드의 "API 변경 시 점검" 을 따른다. 이 명령은 원인을 찾고 계획을 보고하는 데까지다. 고치는 것은 허락받은 뒤 한다. 대상: `$ARGUMENTS`.

`api-blocked` 이슈(사흘 연속 확인 못 함)는 이 명령의 대상이 아니다. 고장이 아니라 요청 제한·차단으로 확인하지 못한 상태라, README "매일 API 감시" 대로 그 소스를 덜 자주 돌릴지를 사용자와 정한다.

1. **이슈 읽기.** `gh issue view <번호> --comments` (번호가 없으면 `gh issue list --label api-broken --state open` 으로 찾는다). 가장 최근 본문·댓글의 표에서 고장 난 소스·명령과 사유를 뽑는다. 주 1회 검사(웹 번들 값 대조)의 고장이면 감시가 알려 준 웹의 새 값도 적어 둔다.
2. **재현.** 고장 난 명령을 표에 나온 그대로 `.venv/bin/jibsa ...` 로 부른다. 요청은 최소로 한다 (네이버는 특히). 결과를 판정 사유와 견준다.
   - 지금은 정상이면 그날만 난 장애일 수 있다. 재현 결과와 함께 보고하고 멈춘다.
   - `RATE_LIMITED`·`blocked` 면 고장이 아니라 확인 못 함이다. 요청 제한이 풀린 뒤 다시 본다.
3. **원인 찾기.** 그 소스 가이드(`docs/development/providers/<소스>.md`) "API 변경 시 점검" 의 순서대로 client → request → response → service → CLI 를 본다.
   - 고장 난 소스가 하나면 직접 찾는다. 웹이 지금 쓰는 API·해시·헤더·필드를 캡처해야 하면 출력이 커서 `web-parity-investigator` 하나에 맡긴다 (Opus high, 질문: "이 명령이 왜 깨졌나. 웹이 지금 보내는 요청·응답과 jibsa 의 것이 어디서 다른가").
   - 둘 이상이면 소스마다 조사원 하나를 한 번에 띄운다 (실제 API 를 부르는 에이전트는 소스당 하나).
4. **보고와 계획.** AGENTS.md 작업 절차대로 쉬운 말로 설명하고 허락을 받는다.
   - 원인과 근거 (재현 명령, 응답의 핵심 필드, 웹 값)
   - 고칠 파일과 내용, 직접 할지 나눌지
   - 확인 방법: 고친 명령의 실제 조회, 필요하면 그 소스 감시를 로컬로 한 번 (`.venv/bin/python scripts/monitor/api_check.py run <소스> --out <scratchpad>/result.json`, 요청이 수십 번 나간다). 주 1회 검사(직방·당근·다방의 웹 번들 값 대조)는 한국 시간 월요일에는 저절로 돌고, 다른 요일에는 `--weekly` 를 붙여야 돈다. 그 검사의 고장이면 요일과 상관없이 `--weekly` 를 붙인다. 네이버는 차단 위험이 커서 고친 명령만 조회하고, 전체 감시(`run naver`)는 왜 필요한지 계획에 적어 허락받을 때만 돌린다.
   - 머지 뒤 바로 패치 릴리스가 필요하다는 것 (`docs/development/release.md` "릴리스 절차": 조회가 깨진 것을 고친 수정). 릴리스는 사용자가 `/release` 로 시작한다.
