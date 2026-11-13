---
name: release
description: jibsa 버전을 올리고 태그를 달아 PyPI·GitHub Release 로 내보낸다. 사용자가 직접 부를 때만 쓴다.
argument-hint: "[버전, 비우면 Unreleased 를 보고 제안]"
disable-model-invocation: true
effort: high
---

`docs/development/release.md` 의 "릴리스 절차" 를 따른다. 이 명령을 부른 것은 릴리스를 시작해도 된다는 뜻일 뿐이다. 바깥으로 나가거나 되돌리기 어려운 단계(이슈 만들기, 커밋, 푸시, PR 열기·머지, 태그 push, 태그 지우기)는 **그 단계마다** 무엇을 할지 보여 주고 허락받은 뒤 한다. 버전: `$ARGUMENTS`.

1. **준비 확인.** `git fetch origin` 으로 원격을 새로 받은 뒤 `git branch --show-current`·`git status`·`git rev-list --left-right --count main...origin/main`. 지금 브랜치가 `main` 이 아니거나, 작업 트리에 릴리스와 상관없는 변경이 있거나, `main` 이 원격과 다르면(앞서거나 뒤처짐) 알리고 멈춘다.
2. **버전 정하기.** `CHANGELOG.md` 의 `## Unreleased` 를 읽고 release.md "번호 붙이는 법" 표로 항목마다 자리를 정해 다음 버전을 제안한다 (`$ARGUMENTS` 가 있으면 그것과 견준다). `Unreleased` 가 비어 있으면 멈춘다.
3. **이슈와 브랜치** (허락 뒤). 🧹 잡무 템플릿으로 이슈를 열고 `git switch -c chore/release-X.Y.Z main` 으로 `main` 에서 브랜치를 딴다 (`docs/development/workflow.md`).
4. **버전 올리기 커밋** (허락 뒤). 한 커밋으로 `pyproject.toml` 의 `version` 을 올리고, `## Unreleased` 를 `## X.Y.Z — YYYY-MM-DD` 로 바꾼 뒤 그 위에 빈 `## Unreleased` 를 둔다. 커밋 메시지와 `Refs #이슈` 는 workflow.md 를 따른다.
5. **푸시와 PR** (허락 뒤). 브랜치를 `git push -u origin chore/release-X.Y.Z` 로 올리고, PR 템플릿을 채워 연다. 머지는 사용자가 하거나 시킬 때 한다.
6. **태그** (머지 뒤, 허락 뒤). 머지된 `main` 에만 단다.

   ```
   git switch main && git pull
   git tag -a vX.Y.Z -m 'vX.Y.Z'
   git push origin vX.Y.Z
   ```

7. **Release 워크플로 확인.** `gh run list --workflow release.yml` 로 태그 확인 → CI → PyPI → GitHub Release 가 끝까지 통과했는지 본다. 실패하면 release.md 대로 원인을 보고하고, 태그를 지우고 다시 다는 것은 허락받은 뒤 한다. 끝까지 통과하면 릴리스는 끝이다 (PyPI 에서 다시 설치해 보지 않는다).
8. **README 데모.** 이 버전에서 `jibsa --version`·`jibsa guide`·직방 `search listings room` 출력이 바뀌었으면, PyPI 에 올라간 뒤 데모를 다시 녹화해야 한다고 알린다 (release.md "README 데모 다시 만들기").
