---
name: review
description: jibsa 변경을 관점별로 리뷰하고 지적마다 실제 조회로 재검증해 진짜 문제·오탐·미확인·일어날 수 없음으로 가른다. 변경 크기에 따라 리뷰어 수를 정한다. PR 전 코드 리뷰나 리뷰 지적 검토를 요청받았을 때 쓴다.
argument-hint: "[대상: 비우면 현재 diff, 또는 PR 번호·브랜치·경로]"
effort: high
---

`docs/development/agents.md` 의 "코드 리뷰" 절을 실행한다. 대상: `$ARGUMENTS` (비어 있으면 커밋 전 변경과 이 브랜치의 커밋 전부: `git diff HEAD`, `git status --short` 의 추적 안 된 파일, `git diff main...HEAD`. 에이전트는 시키지 않으면 커밋하지 않아 리뷰할 변경이 대개 커밋 전에 있다).

**PR 번호나 다른 브랜치가 대상이면** 재현은 지금 작업 트리의 코드로 돌아가 그 변경을 재현하지 못한다. 작업 트리를 바꾸지 않고(사용자의 커밋 전 변경이 있을 수 있다) 브랜치를 새로 받아 오지도 않는다. 재검증 없이(`verify: false`, 직접 재현도 하지 않음) 코드 리뷰만 하고, 보고 첫 줄에 "재현하지 않은 리뷰" 라고 적는다. 리뷰어는 파일을 작업 트리에서 열면 다른 코드를 읽게 되므로, `target` 에 그 코드를 읽는 법을 적고 "작업 트리 파일은 열지 않는다. 규칙 문서·소스 가이드도 그 리비전에서 읽는다" 를 넣는다.
- **로컬에 있는 브랜치:** 변경은 `git diff main...<브랜치>`, 파일 내용은 `git show <브랜치>:<경로>`.
- **PR:** 주 에이전트가 `gh pr diff <번호>` 를 scratchpad 에 저장해 그 경로를 `target` 에 준다. 파일 전체가 필요하면 `gh pr view <번호> --json headRefOid` 의 커밋으로 `gh api 'repos/{owner}/{repo}/contents/<경로>?ref=<커밋>' --jq .content | base64 -d`.

1. **크기 정하기.** 바뀐 코드 파일(`src/` 아래. 문서·테스트·픽스처는 세지 않는다)·소스·명령을 보고 정한다. 애매하면 큰 쪽으로 한다.

   | 크기 | 기준 | `groups` | 리뷰어 모델 | `verify` |
   | --- | --- | --- | --- | --- |
   | 작음 | 한 소스, 명령 하나, 코드 파일 다섯 개 안쪽 | `[["convention","correctness","contract","web","requests"]]` | Sonnet high | `false` |
   | 중간 | 한 소스 안에서 명령 둘 이상, 또는 코드 파일 다섯 개 넘음 | `[["convention","web"],["correctness","contract"],["requests"]]` | Sonnet high, 얽혔으면 Opus high | `true` |
   | 큼 | 소스 둘 이상, 또는 `core/`·소스에 매이지 않은 `cli/` 코드 | 관점마다 하나 | Opus high, 지우는 코드가 여러 명령에 걸리면 Opus xhigh | `true` |
   | 코드 아님 | 문서·에이전트 정의·명령·워크플로만 바뀜 (`src/` 코드 0개) | 파일 다섯 개 안쪽이면 작음과 같게, 넘으면 중간과 같게 | Sonnet high | `false` (재현할 jibsa 동작이 없다. 원문 대조와 워크플로 가짜 실행으로 확인한다) |

   대상이 PR·다른 브랜치면 크기와 상관없이 `verify: false` 이고 재현하지 않는다 (위 절). `groups`·리뷰어 모델은 표대로 정한다.

   사용자가 `/review` 를 직접 쳤으면 크기·리뷰어 수·모델을 한 줄로 알리고 바로 돌린다. 사용자가 치지 않았는데 요청을 보고 이 명령을 골랐으면, 같은 내용을 알리고 허락받은 뒤 돌린다 (에이전트 여러 개라 비용이 크다).

2. **지적 모으고 재검증하기.** `review-panel` 워크플로(`.claude/workflows/review-panel.js`)를 부른다. 관점 다섯 가지의 설명은 그 파일의 `PERSPECTIVES` 에 있고, 리뷰어는 읽기 전용 `jibsa-reviewer` 다.

   ```
   args: {
     target: "리뷰 대상 한 줄 + 리뷰어가 diff 를 볼 명령 (예: git diff HEAD, 추적 안 된 파일 경로)",
     groups: [...],               // 위 표
     reviewerModel: "sonnet",     // 또는 "opus"
     reviewerEffort: "high",      // 또는 "xhigh"
     verify: true,                // 작음이거나 PR·다른 브랜치면 false
     date: "YYYY-MM-DD"           // 오늘. 오탐 주석 제안에 쓴다
   }
   ```

   워크플로는 묶음마다 리뷰어를 동시에 돌리고, 지적을 합치지 않고 파일·줄 순으로 늘어놓은 뒤, 소스(파일 경로로 정함)마다 한 번에 `review-verifier` 하나로 하나씩 재현한다 (같은 소스의 API 를 동시에 부르지 않는다. 한 소스의 지적이 10건을 넘으면 같은 소스 안에서 차례로 더 띄우고, 공통 코드 지적은 마지막에). 같은 문제를 가리키는 지적은 검증자가 `duplicate` 로 묶는다.

   `verify: false` 로 돌렸으면 돌아온 `items` 를 직접 재현한다 (실제 CLI 조회나 원본 응답, 지적당 1~2회). 다섯 건이 넘으면 소스마다 `review-verifier` 하나(Sonnet high)에 넘긴다. 단 대상이 PR·다른 브랜치면 재현하지 않고, 지적을 읽어 같은 문제끼리만 묶는다.

   Workflow 도구가 없는 환경에서는 같은 크기·같은 관점으로 `jibsa-reviewer` 를 Agent 로 띄우고(모델은 위 표), 지적을 소스마다 `review-verifier` 하나(Sonnet high)로 재검증한다.

3. **결과 확인.** 돌려받은 값에서 먼저 본다.
   - `ok: false` 나 `failedReviewers`: 그 관점은 리뷰되지 않았다. 그 묶음만 다시 돌리거나, 리뷰되지 않았다고 보고 첫 줄에 적는다. 지적 0건이어도 깨끗한 리뷰로 보고하지 않는다.
   - `missingPerspectives`: 일부러 뺀 관점이 아니면 같은 처리를 한다.
   - `impossible`·`duplicate`: 근거를 훑어 잘못 갈린 것(진짜 문제인데 일어날 수 없다고 한 것 등)이 없는지 본다. 사용자에게는 건수만 적는다.
4. **보고.** 진짜 문제(`real`)와 오탐(`falsePositive`)을 근거(재현 명령·응답 핵심 필드·`파일:줄`)와 함께 보고한다. 근거가 "재현 못 함, 코드로 확인" 인 진짜 문제는 그렇게 밝히고 재현하지 못한 이유를 함께 적는다 (재현할 조건이 없어도 코드상 분명히 틀리면 진짜 문제다. `docs/development/agents.md` "코드 리뷰" 2단계. `verify: false` 로 직접 재현할 때도 같다). 서로 다른 검증자에게 가서 묶이지 않은 중복(같은 파일·줄 근처의 같은 문제)은 하나로 묶어 보고한다. 미확인(`unconfirmed`)은 무엇을 더 보면 가릴 수 있는지와 함께 따로 적는다. 오탐은 어디에 어떤 문장으로 남길지(코드 주석 `# 리뷰 오탐 (YYYY-MM-DD): 이유` 또는 소스 가이드 "웹과 다른 점")를 함께 제안한다.
5. 고치는 것과 오탐 기록 남기기는 **사용자가 정한 뒤** 한다 (AGENTS.md 작업 절차: 계획을 설명하고 허락받기). 커밋·PR 코멘트는 시킬 때만.
