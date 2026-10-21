# Release

버전 번호를 정하는 규칙과 릴리스 절차. 변경이 `main` 에 들어가기까지의 절차는 [workflow.md](workflow.md) 를 본다.

## 버전은 `pyproject.toml` 한 곳에

버전은 `pyproject.toml` 의 `version` 에만 적는다. `jibsa --version` 은 설치 메타데이터에서 읽으므로
(`cli/app.py` 의 `version_text()`) 코드나 문서에 버전 문자열을 복사하지 않는다.

사용자는 PyPI 에서 릴리스한 버전을 설치하거나(`uv tool install jibsa`, 기본), `git+https://github.com/Rukkakka/jibsa`
로 `main` 의 최신 커밋을 설치한다. git 주소 설치는 릴리스 사이의 커밋도 버전이 같아 `jibsa --version` 이 설치한
커밋을 함께 보여 준다.

| 설치 방법 | `jibsa --version` |
| --- | --- |
| PyPI (`uv tool install jibsa`, `pipx install jibsa`, `pip install jibsa`) | `jibsa 0.2.0` |
| git 주소 (`uv tool install git+...`, `pipx`, `pip`) | `jibsa 0.2.0 (커밋 a1b2c3d)` |
| 편집 가능 설치 (`pip install -e .`) | `jibsa 0.2.0 (개발 설치)` |
| 로컬 경로 (`uv tool install .`) | `jibsa 0.2.0` |

## 번호 붙이는 법

[SemVer](https://semver.org/lang/ko/) 를 따르고 `0.작은.패치` 로 시작한다. jibsa 는 출력 JSON 이 곧 API 라서,
[출력 규약](output-contract.md)과 에이전트가 읽는 출력이 어떻게 바뀌었는지로 올릴 자리를 정한다.

| 바뀐 것 | 올리는 자리 | 예 |
| --- | --- | --- |
| 버그 수정, 사이트 API 변경 대응 (출력 모양은 그대로), 문서 오류 수정 | 패치 | 0.1.0 → 0.1.1 |
| 명령·옵션·출력 필드·에러 코드 추가, 기본값·조회 한도 변경 | 작은 | 0.1.1 → 0.2.0 |
| 명령·옵션·필드 이름 변경·삭제, 값의 뜻·단위 변경, 에러 코드·exit code 변경 (호환 깨짐) | 작은 + `⚠️ 호환 깨짐` 표시 | 0.2.0 → 0.3.0 |

- 한 릴리스에 여러 종류가 섞이면 가장 큰 것 하나를 기준으로 한다. 작은 자리를 올리면 패치는 0 으로 돌아간다.
- 출력 규약이 안정되면 1.0.0 을 낸다. 그 뒤로는 호환 깨짐이 앞자리를 올린다 (1.4.2 → 2.0.0).
- 의존성·도구·테스트·내부 리팩터링만 바꾼 변경은 버전을 올릴 이유가 아니다. 다른 변경과 함께 나간다.

## CHANGELOG 쓰는 법

사용자(에이전트 포함)에게 보이는 변경은 **그 PR 에서** [CHANGELOG.md](../CHANGELOG.md) 의 `## Unreleased` 아래에
적는다. 릴리스할 때 몰아서 쓰면 왜 바꿨는지 잊는다.

- 분류는 `⚠️ 호환 깨짐` · `추가` · `변경` · `수정` 네 가지를 이 순서로 둔다. 항목이 없는 분류 제목은 쓰지 않는다.
  - `⚠️ 호환 깨짐` — 위 표의 호환 깨짐. 삭제도 여기에 적는다.
  - `추가` — 새 명령·옵션·출력 필드·에러 코드.
  - `변경` — 호환은 지키면서 동작이 달라진 것 (기본값·조회 한도·정렬 등).
  - `수정` — 버그, 사이트 API 변경 대응, 문서 오류.
- 한 줄에 하나, 사용자 입장에서 무엇이 달라졌는지와 이슈 번호를 적는다 (이슈는 PR 보다 먼저 열어 번호를 알 수 있다).
  내부 리팩터링·테스트·도구 변경은 적지 않는다.
- 호환 깨짐은 쓰는 쪽이 무엇을 고쳐야 하는지까지 적는다.

```markdown
## Unreleased

### ⚠️ 호환 깨짐

- 출력 필드 `deposit` 을 `deposit_manwon` 으로 바꿈. 읽는 쪽도 새 이름으로 고친다 (#28)

### 추가

- 당근 `preschools` 명령 (#25)

### 수정

- 네이버 `real-price` 가 응답 구조 변경으로 `PARSE_ERROR` 를 내던 문제 (#31)
```

## 릴리스 절차

변경이 어느 정도 모이면 릴리스한다. 정해진 주기는 없다. 다만 PyPI 로 설치한 사용자는 릴리스해야 수정을 받으므로,
사이트 API 변경 대응처럼 조회가 깨진 것을 고친 수정은 머지 뒤 바로 패치를 릴리스한다. git 주소로 설치한 사용자는
`upgrade` 할 때 `main` 을 바로 받는다.

1. 🧹 잡무 템플릿으로 이슈를 열고 `chore/release-0.2.0` 브랜치를 딴다 ([workflow.md](workflow.md)).
2. 한 커밋으로 아래 두 가지를 바꾼다.
   - `pyproject.toml` 의 `version` 을 올린다. `Unreleased` 에 `수정` 만 있으면 패치, 다른 분류가 하나라도 있으면
     작은 자리 (1.0 이후 `⚠️ 호환 깨짐` 은 앞자리).
   - `## Unreleased` 를 `## 0.2.0 — 2026-11-02` 로 바꾸고, 그 위에 빈 `## Unreleased` 를 새로 둔다.
3. PR 을 열고 머지한다.
4. 머지된 `main` 커밋에 태그를 달고 push 한다.

   ```
   git switch main && git pull
   git tag -a v0.2.0 -m 'v0.2.0'
   git push origin v0.2.0
   ```

5. 태그 push 가 [Release 워크플로](../.github/workflows/release.yml)를 돌린다. 끝까지 통과했는지 Actions 에서 본다.
   1. 태그 확인 — 태그 커밋이 `main` 에 있는지, 태그가 `pyproject.toml` 버전과 같은지, CHANGELOG 에 그 버전 절이 있는지
   2. CI — [ci.yml](../.github/workflows/ci.yml) 전체. 설치본 확인이 sdist·wheel 을 빌드하고 `twine check`·설치 확인을 한다
   3. PyPI — 2 에서 빌드한 파일을 신뢰 게시(Trusted Publishing)로 올린다. API 토큰은 없다
   4. GitHub Release — 본문은 CHANGELOG 의 그 버전 절, 빌드한 파일을 첨부한다

   태그 확인이나 CI 가 실패하면 아무것도 올라가지 않는다. 고친 커밋을 머지하고 태그를 지운 뒤
   (`git push origin :refs/tags/v0.2.0 && git tag -d v0.2.0`) 새 `main` 커밋에 다시 단다. PyPI 단계만 실패했으면
   (pypi.org 게시자 설정 등) 원인을 고치고 그 실행의 실패한 잡을 다시 돌린다.

   Release 워크플로가 끝까지 통과하면 릴리스는 끝난다. PyPI 에서 다시 설치해 보지 않는다. 올라간 파일은 CI 의 설치본
   확인이 새 가상환경에 설치해 돌려 본 바로 그 파일이고, 실제 API 로 도는지는 [매일 API 감시](development.md#매일-api-감시)가
   `main` 으로 본다.

6. README 데모에 나오는 출력(`jibsa --version`·`jibsa guide`·직방 `search listings room`)이 이 버전에서 바뀌었으면, PyPI 에
   올라간 뒤 별도 PR 로 `docs/demo/demo.gif`·`claude.gif` 를 다시 녹화한다 ([문서 갱신](../AGENTS.md#문서-갱신)). 녹화 대본이
   PyPI 에서 설치한 jibsa 를 써서, 올리기 전에 찍으면 이전 버전의 출력이 녹화된다.

태그는 머지 뒤 `main` 에만 단다. 브랜치 커밋에 달면 squash·rebase 머지 때 `main` 에 없는 커밋을 가리키고,
Release 워크플로가 거절한다.

PyPI 에 한 번 올린 버전은 지우거나 같은 번호로 다시 올릴 수 없다. 잘못 올렸으면 pypi.org 에서 그 버전을 yank 하고
고친 패치를 릴리스한다.
