# 기여하기

버그 제보, 기능 제안, 코드 수정 모두 환영한다.

## 이슈

버그나 제안은 [이슈](https://github.com/Rukkakka/jibsa/issues/new/choose)로 연다. 버그·기능·문서·잡무·작업 템플릿 중 맞는 것을 골라 채운다.

## 코드 고치기

1. [AGENTS.md](AGENTS.md)의 "꼭 지킬 것"을 먼저 읽는다. 로그인 없는 기능만, 금액은 만원, 출력 규약 같은 원칙이 있다.
2. [개발 환경](docs/development/README.md)대로 설치하고, 고친 뒤 ruff·mypy 를 돌리고 실제 API 로 확인한다.
3. [작업 절차](docs/development/workflow.md)대로 이슈 → 브랜치 → 커밋 → PR 순서로 올린다. CI(ruff·mypy·pytest·설치 확인)를 통과해야 머지된다.

나머지 개발 문서(구조, 출력 규약, 코드 형식, 소스별 개발 가이드)는 [docs/development/](docs/development/)에 있다.
