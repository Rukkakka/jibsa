---
name: web-parity
description: jibsa 명령이 그 사이트 웹과 어긋나는지 소스별로 조사해 A(어긋남)·B(의도한 차이)·C(같음)·D(웹에만 있음)로 가른다. 읽기 전용. 웹 대조 조사를 요청받았을 때 쓴다.
argument-hint: "<소스...> [범위: 명령·옵션·궁금한 점]"
effort: high
---

`docs/development/provider-conventions.md` 의 "웹 화면과의 대응" 기준으로 조사한다. 저장소 파일은 고치지 않는다. 대상: `$ARGUMENTS`.

1. **대상 정하기.** 소스(`zigbang`·`naver`·`daangn`·`dabang`)와 소스마다 볼 범위(명령·옵션·궁금한 점)를 정한다.
   - 범위가 비었으면 그 소스의 명령 목록(`.venv/bin/jibsa <소스> --help`)을 보여 주고 무엇을 볼지 묻는다.
   - 소스 하나의 범위는 하나로 합친다 (실제 API 를 부르는 에이전트는 소스당 하나).
   - 조사원 하나의 요청 한도(페이지 열기 15회·네이버는 첫 화면 3회, jibsa 명령 10개 안쪽. `web-parity-investigator` 정의)에 들어가지 않을 만큼 넓으면, 명령 몇 개로 줄이거나 여러 번에 나눠 차례로 돈다.
   - 어떻게 돌릴지(소스, 범위, 조사원 수)를 알린다. 사용자가 `/web-parity` 를 직접 쳤으면 바로 돌리고, 치지 않았는데 이 명령을 골랐으면 허락받은 뒤 돌린다 (Opus 조사원이라 비용이 크다).
2. **조사 돌리기.** 웹 캡처는 출력이 커서 주 에이전트가 직접 하지 않고 조사원에게 맡긴다. 브라우저 조사라 모델은 Opus 만 쓴다.
   - **소스 하나:** `web-parity-investigator` 를 Agent 로 하나 띄운다 (`model: opus`, effort 는 xhigh, 명령 하나·옵션 몇 개처럼 범위가 좁으면 high). 지시서는 `docs/development/agents.md` "맡길 때 지시서에 넣는 것" 대로 쓰고, 확인할 것은 가설이 아니라 질문으로 준다.
   - **소스 둘 이상:** `web-parity-panel` 워크플로(`.claude/workflows/web-parity-panel.js`)를 부른다. 소스마다 조사원 하나가 동시에 돈다.

     ```
     args: { targets: [ { source: "zigbang", scope: "범위", effort?: "xhigh" | "high" }, ... ] }
     ```

     Workflow 도구가 없는 환경에서는 소스마다 Agent 를 하나씩 한 번에 띄운다.
3. **합치기와 보고.** 결과에 `failed` 가 있으면 그 소스는 조사되지 않았다고 먼저 적는다. 소스별로 표 하나: 명령·옵션 / 판정 / 웹 동작 / jibsa 동작(`파일:줄`) / 이유. 순서는 A(근거와 함께) → B 중 "웹과 다른 점" 에 아직 없는 것 → 미확인 → D(엔드포인트) 이고, C 는 건수만 적는다. 조사원이 "확인했다" 고 한 A 는 핵심 하나를 직접 다시 본다 (`docs/development/agents.md` "검증 분담").
4. A 를 고치거나 B 를 문서에 적는 것은 AGENTS.md 작업 절차대로 계획을 설명하고 허락받은 뒤 한다.
