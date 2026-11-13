---
name: pr-ready
description: PR 을 열기 전에 바뀐 파일을 AGENTS.md "문서 갱신" 표와 workflow.md "PR 을 열기 전에" 체크리스트에 대조해 빠진 문서·감시 목록·CHANGELOG 를 찾고 ruff·mypy 를 돌린다.
argument-hint: "[기준 브랜치, 기본 main]"
disable-model-invocation: true
effort: high
allowed-tools: Bash(git diff *) Bash(git status *) Bash(.venv/bin/ruff *) Bash(.venv/bin/mypy *) Read Grep Glob
---

기준 브랜치는 `$ARGUMENTS` (비어 있으면 `main`). PR 을 만들거나 커밋하지 않는다. 점검 결과만 보고한다.

1. `git diff --name-status <기준>...HEAD` 와 `git status --short` 로 바뀐 파일을 모은다.
2. `AGENTS.md` 의 "문서 갱신" 표와 `docs/development/workflow.md` 의 "PR 을 열기 전에" 를 읽고, 바뀐 파일마다 함께 고쳐야 하는 것이 diff 에 있는지 본다.
   - `src/jibsa/cli/<source>.py` 또는 `providers/<source>/` → `docs/<source>.md`, 명령·옵션·필드 변경이면 `docs/llm.md`(200줄 이하), 명령 추가·삭제나 매물 찾는 새 방식이면 `scripts/monitor/api_check.py` 의 `GROUPS`.
   - 사용자(에이전트 포함)에게 보이는 변경 → `CHANGELOG.md` 의 `Unreleased`.
   - 모듈 추가·이름 변경·삭제 → `AGENTS.md` 구조 표와 `docs/development/providers/<source>.md`.
   - `scripts/install/` → `docs/install.md` 한 줄 설치 절. `pyproject.toml` 의존성 → 상한 규칙.
   - 웹과 다르게 한 곳 → 그 소스 가이드 "웹과 다른 점".
3. `.venv/bin/ruff check` 와 `.venv/bin/mypy` 를 돌린다 (0건이어야 한다). 전체 `pytest` 는 돌리지 않는다 (CI 가 돌린다).
4. diff 에 토큰·쿠키·중개사 이름·전화번호 같은 개인정보나 실제 매물 데이터 픽스처가 없는지 `grep` 으로 훑는다.
5. 보고: 빠진 문서·목록을 "파일 → 고쳐야 할 곳" 으로, ruff·mypy 결과, 의심되는 개인정보 위치. 다 맞으면 "PR 템플릿의 변경 종류와 Closes #이슈 를 채우면 된다" 고 끝낸다.
