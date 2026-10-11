## 요약

<!-- 무엇을 왜 바꾸나요? 닫는 이슈를 적어 주세요. 예: "Closes #12" -->

## 변경 종류

<!-- 해당하는 것을 모두 체크하세요. -->

- [ ] `fix` — 버그 수정
- [ ] `feature` — 새 소스, 명령, 옵션, 엔드포인트
- [ ] `docs` — 문서만
- [ ] `chore` — 의존성, 도구, 설정, 정리
- [ ] `task` — 그 밖의 작업

## 영향 범위

<!-- 예: providers/naver, cli 출력, search.py. 문서·도구만 바꿨다면 "없음". -->

## 어떻게 테스트했나요?

<!-- 실제로 실행한 것을 적어 주세요. 실제 API 로 확인한 명령(CLI 직접 조회)을 먼저, 돌린 pytest 가 있으면 그다음에.
     테스트를 추가했다면 드문 엣지케이스인지 핵심 동작인지 적어 주세요. "테스트 안 함"도 괜찮습니다 — 그렇다고 적어 주세요. -->

## 체크리스트

- [ ] [references/code-style.md](https://github.com/Rukkakka/jibsa/blob/main/references/code-style.md) 를 따른다
- [ ] 새로 만들거나 바꾼 엔드포인트가 [references/provider-conventions.md](https://github.com/Rukkakka/jibsa/blob/main/references/provider-conventions.md) 를 따른다
- [ ] 명령·옵션·출력 필드·에러 코드·요청 제한이 바뀌었다면 `docs/<source>.md`·`docs/common.md` 와 [references/output-contract.md](https://github.com/Rukkakka/jibsa/blob/main/references/output-contract.md) 를 고쳤다
- [ ] 명령을 추가·삭제했거나 에이전트가 틀리기 쉬운 해석 규칙이 바뀌었다면 `docs/llm.md` 를 고쳤다
- [ ] 사용자에게 보이는 변경이면 `CHANGELOG.md` 의 `Unreleased` 에 적었다 ([쓰는 법](https://github.com/Rukkakka/jibsa/blob/main/references/release.md#changelog-쓰는-법))
- [ ] 모듈을 추가·이름 변경·삭제했다면 `AGENTS.md` 구조 표와 해당 `references/providers/<source>.md` 를 고쳤다
- [ ] 새 픽스처와 diff 에 토큰, 쿠키, 중개사 연락처 같은 개인정보가 없다
