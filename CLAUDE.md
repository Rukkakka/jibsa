# CLAUDE.md

이 저장소의 작업 지침은 AGENTS.md 다. 아래 줄이 Claude Code 를 켤 때 그 내용을 함께 불러온다.
AGENTS.md에서 연결한 공통 규약과 소스별 개발 가이드도 작업 범위에 맞게 참고한다.

@AGENTS.md

## Claude Code 에서 서브에이전트를 쓸 때

운용 규칙은 [docs/development/agents.md](docs/development/agents.md) 다. 아래는 Claude Code 에만 해당하는 값이다.

- 모델은 일에 맞춰 고른다. **최소선은 Sonnet `effort: high`** 고 Haiku 는 쓰지 않는다. 범위가 좁고 지시서가 구체적인 수정·API
  찔러 보기·데이터 대조는 Sonnet high, 얽힌 코드를 지우거나 여러 명령으로 번지는 변경·브라우저 조작이 든 조사·여러 사실을 종합하는
  문서는 Opus high, 그중 얽힘이 크거나(지우는 코드가 여러 명령에 걸림) 종합할 사실이 많으면 Opus xhigh. 웹 대조 조사는 명령 여럿을
  판정해 종합할 사실이 많으므로 xhigh, 명령 하나·옵션 몇 개처럼 범위가 좁거나 질문이 하나(감시 고장 원인 등)면 high 다.
  이 기준은 여기에만 두고 에이전트 정의에는 옮겨 적지 않는다 (명령은 이 기준으로 그 일의 값을 정해 적는다). 정의된 에이전트(`claude-code-guide` 등)도 기본 모델이 낮을 수 있으니 띄울 때 `model` 을 명시한다.
- 미리 정의한 역할은 `.claude/agents/` 에 있다: `web-parity-investigator`(웹 대조 조사, 읽기 전용), `jibsa-coder`(코드 작업),
  `jibsa-docs`(문서 작업), `jibsa-reviewer`(리뷰 지적 모으기, 읽기 전용), `review-verifier`(리뷰 지적 재검증, 읽기 전용).
  파일의 모델·effort 는 흔한 값이고 호출 때 덮어쓴다. 모두 git 은 읽기 명령만 쓴다 (작업 트리에 사용자의 커밋 전 변경이 있을 수 있다).
- 슬래시 명령은 `.claude/skills/` 에 있다.
  - `/review` — 변경 크기로 리뷰어 수를 정해 관점별 리뷰 → 재검증 → 분류 ([코드 리뷰](docs/development/agents.md#코드-리뷰))
  - `/web-parity` — 소스별 웹 대조 조사 (A·B·C·D), 읽기 전용
  - `/api-broken` — 매일 API 감시의 고장 이슈를 재현하고 원인과 고칠 계획을 보고
  - `/new-endpoint` — 새 엔드포인트를 더하는 확인 순서와 구현 순서
  - `/release` — 릴리스 절차. 사용자가 직접 칠 때만 돌고, 바깥으로 나가는 단계마다 다시 허락받는다
  - `/pr-ready` — PR 열기 전 점검
- 워크플로(여러 에이전트를 정해진 순서로 돌리는 스크립트)는 `.claude/workflows/` 에 있다.
  - `review-panel` — `/review` 가 부른다. 관점 묶음마다 `jibsa-reviewer` 를 동시에 → 소스마다 `review-verifier` 하나 (지적이 10건을 넘으면 같은 소스에 더, 동시에 셋까지, 네이버는 하나씩)
  - `web-parity-panel` — `/web-parity` 가 조사원이 둘 이상일 때 부른다. 소스·범위마다 `web-parity-investigator` 하나 (Opus, 같은 소스는 동시에 셋까지, 네이버는 하나씩)
  - `implement-bundles` — 허락받은 구현 계획의 묶음을 `jibsa-coder` 로 돌린다 (공통 묶음 먼저, 소스마다 `first` 묶음 먼저, 나머지는
    파일이 겹치지 않아 같은 소스도 동시에 셋까지·네이버는 하나씩, 소스끼리는 동시에. 동시에 돌 수 있는 묶음끼리 같은 파일을
    고치면 시작하지 않는다) → `jibsa-docs` 하나. 작업자는 자기 파일만 고치고 CHANGELOG·`docs/llm.md`·감시 목록 같은 공용 파일은
    고칠 내용만 보고한다. 작업자는 실제 조회를 하지 않고, 고치기 전·후 출력 비교는 주 에이전트가 한다 (고치기 전 출력을 저장한
    경로를 `baseline` 으로 넘겨야 시작한다). 인자 형식은 그 파일의
    `meta.whenToUse` 에 있다.

  **언제 돌리나.** 에이전트를 여러 개 써 비용이 크다.
  - `review-panel`·`web-parity-panel`: 사용자가 `/review`·`/web-parity` 를 직접 쳤으면 돌린다. 치지 않았는데 요청을 보고 그 명령을
    골랐으면 에이전트 수를 알리고 허락받은 뒤 돌린다.
  - `implement-bundles`: "implement-bundles 로 구현한다" 고 적은 구현 계획을 사용자가 허락했을 때만 돌린다. 고칠 코드가 많으면
    (`src/` 코드 파일 다섯 개를 넘게 고치고 파일이 겹치지 않는 묶음이 둘 이상, 같은 소스여도) 계획에 그렇게 적어 나눠 제안하고,
    적으면 직접 고친다 ([나눌지 정하기](docs/development/agents.md#나눌지-정하기)).

  **만들 때.** 저장한 워크플로는 슬래시 명령 목록에도 이름으로 올라가므로 명령과 이름이 겹치지 않게 짓는다. 인자 없이 불리면
  아무것도 띄우지 않고 안내만 돌려주게 한다.
- hooks 는 두지 않았다 (2026-11-13 사용자 결정: 저장소 설정은 모든 사용자 환경에 걸린다).
