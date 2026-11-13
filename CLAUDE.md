# CLAUDE.md

이 저장소의 작업 지침은 AGENTS.md 다. 아래 줄이 Claude Code 를 켤 때 그 내용을 함께 불러온다.
AGENTS.md에서 연결한 공통 규약과 소스별 개발 가이드도 작업 범위에 맞게 참고한다.

@AGENTS.md

## Claude Code 에서 서브에이전트를 쓸 때

운용 규칙은 [docs/development/agents.md](docs/development/agents.md) 다. 아래는 Claude Code 에만 해당하는 값이다.

- 모델은 일에 맞춰 고른다. **최소선은 Sonnet `effort: high`** 고 Haiku 는 쓰지 않는다. 범위가 좁고 지시서가 구체적인 수정·API
  찔러 보기·데이터 대조는 Sonnet high, 얽힌 코드를 지우거나 여러 명령으로 번지는 변경·브라우저 조작이 든 조사·여러 사실을 종합하는
  문서는 Opus high, 그중 얽힘이 크거나(지우는 코드가 여러 명령에 걸림) 종합할 사실이 많으면 Opus xhigh. 정의된 에이전트(`claude-code-guide` 등)도 기본 모델이 낮을 수 있으니 띄울 때 `model` 을 명시한다.
- 미리 정의한 역할은 `.claude/agents/` 에 있다: `web-parity-investigator`(웹 대조 조사, 읽기 전용), `jibsa-coder`(코드 작업),
  `jibsa-docs`(문서 작업), `review-verifier`(리뷰 지적 재검증). 파일의 모델·effort 는 흔한 값이고 호출 때 덮어쓴다.
- 슬래시 명령은 `.claude/skills/` 에 있다: `/review`(관점별 리뷰 → 재검증 → 분류, [코드 리뷰](docs/development/agents.md#코드-리뷰)),
  `/pr-ready`(PR 열기 전 점검). hooks 는 두지 않았다 (2026-11-13 사용자 결정: 저장소 설정은 모든 사용자 환경에 걸린다).
