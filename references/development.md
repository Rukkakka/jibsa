# 공통 개발 환경

[개발 규약](../AGENTS.md) · [코드 형식](code-style.md) · [작업 절차](workflow.md)

## 설치

코드를 고치려면 저장소를 받아 편집 가능 모드로 설치한다. 고친 코드가 바로 반영된다. Python·git 설치는 [README 준비물](../README.md#1-준비물)을 따른다.

```bash
# macOS·Linux
git clone https://github.com/Rukkakka/jibsa && cd jibsa

python3.11 -m venv .venv          # 또는 uv venv --python 3.11
.venv/bin/pip install -e ".[dev]" # 또는 uv pip install -e ".[dev]"

.venv/bin/jibsa --help            # source .venv/bin/activate 후에는 jibsa 만 쳐도 된다
```

```powershell
# Windows (PowerShell) — bin 대신 Scripts 폴더를 쓴다
git clone https://github.com/Rukkakka/jibsa; cd jibsa

py -m venv .venv                       # 또는 uv venv --python 3.11
.venv\Scripts\pip install -e ".[dev]"  # 또는 uv pip install -e ".[dev]"

.venv\Scripts\jibsa --help             # .venv\Scripts\Activate.ps1 후에는 jibsa 만 쳐도 된다
```

Windows 는 [README 의 Windows 주의사항](../README.md#4-windows-에서-쓸-때)(UTF-8 출력 설정, 동시 실행 금지)도 그대로 적용된다. `Activate.ps1` 이 실행 정책 때문에 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 를 한 번 실행한다.

## 코드 검사

[코드 형식](code-style.md) 규칙 중 도구로 잡을 수 있는 것은 ruff 와 mypy 가 검사한다. 설정은 `pyproject.toml` 에 있다. 코드를 고쳤으면 둘 다 0건이어야 한다.

```bash
.venv/bin/ruff check          # 따옴표, import 순서, 안 쓰는 import, 타입 힌트 누락
.venv/bin/ruff check --fix    # import 정렬·따옴표처럼 자동으로 고칠 수 있는 것은 고친다
.venv/bin/mypy                # src 전체 타입 검사
```

Windows 는 `.venv\Scripts\ruff`, `.venv\Scripts\mypy` 로 부른다.

- `ruff format` 은 쓰지 않는다. 여러 줄로 쓰는 필드 선언([코드 형식 §4](code-style.md#4-pydantic-선언))을 한 줄로 합친다.
- import 바로 위에 주석을 달면 ruff 가 그 앞에 빈 줄을 넣어 같은 그룹이 갈라진 것처럼 보인다. import 에 다는 주석은 줄 끝에 쓴다.
- mypy 오류를 `# type: ignore` 로 덮지 않는다. 앞에서 이미 확인해 None 일 수 없는 값이면 `assert` 로 좁히고 왜 그런지 주석을 단다. 정말 필요할 때만 오류 코드를 붙여 쓴다 (`# type: ignore[assignment]`).

## 검증과 테스트

### 검증은 실제 API 로

- 코드를 바꾸면 CLI 직접 조회나 원본 응답 확인처럼 실제 API 호출로 동작을 확인하는 것이 기본이다. 가짜 응답(픽스처·`MockTransport`)으로만 확인했다고 하지 않는다. 실제 API 를 부르는 테스트(live 테스트)는 두지 않고 CLI 직접 조회로 확인한다.
- 실제 API 로 재현할 수 없는 상태(커서가 멈춘 응답 등)만 가짜 응답으로 확인하고 그 이유를 적는다.
- 요청 수는 최소로 하고 요청 제한 훅을 거친다 (네이버는 차단 위험이 크다).
- 문서·문구만 바꿨으면 링크·코드 선언·출력 필드 대응만 검토하고 pytest·실제 호출은 하지 않는다.

### 테스트 추가는 두 경우만

1. 실제 API 로 재현하기 어려운 아주 드문 엣지케이스
2. 틀어지면 안 되는 핵심 동작 (출력 계약·만료 매물 제외·서버 필터 원칙 같은 공통 규칙)

기존 테스트를 넓히는 것도 같은 기준이다. 추가할 때는 둘 중 무엇인지 PR·보고에 적는다. 그 밖의 경우(일반 분기, 요청 파라미터 모양, 문구, 구현을 그대로 따라 쓰는 검증, 다른 테스트와 겹치는 검증)에는 추가하지 않는다.

### pytest 실행 범위

```bash
.venv/bin/pytest tests/test_naver.py::test_name   # 평소: 바꾼 부분 테스트 몇 개만 이름으로
.venv/bin/pytest                                  # 전체 (네트워크 없음) — 실행 전에 사용자에게 묻는다
```

Windows 는 `.venv/bin/pytest` 대신 `.venv\Scripts\pytest` 로 부른다.

- **전체 `pytest` 는 실행 전에 사용자에게 묻는다.** PR 에서는 [CI](../.github/workflows/ci.yml) 가 전체를 돌린다.
- 평소에는 바꾼 함수를 직접 검사하는 테스트 몇 개만 `tests/test_x.py::test_name` 으로 골라 한 번 실행한다. 파일 전체, 넓은 `-k` 키워드, 바꾼 함수를 부르는 테스트를 모두 모아 돌리는 것도 하지 않는다. 실패하면 그 테스트만 다시 돌린다.
- 문구·문서·이름 변경처럼 깨질 위험이 없으면 바꾼 부분의 테스트도 돌리지 않는다.

### 픽스처와 테스트 환경

- 픽스처는 `tests/fixtures/<source>/<action_id>.json` (당근 HTML 은 `.html.gz`). 실제 응답 구조를 본뜬 **가상 데이터**다. 실제 매물·단지·중개사 정보는 커밋하지 않는다. 만드는 법은 [새 엔드포인트 추가 순서](provider-conventions.md#새-엔드포인트-추가-순서)에 있다.
- 픽스처는 테스트가 읽는 것만 둔다. 응답 형태를 보여 주는 참고 자료로 두지 않고, 테스트를 지워 아무도 읽지 않게 된 픽스처는 함께 지운다.
- `conftest.py` 가 `JIBSA_STATE_DIR` 을 임시 디렉터리로 돌려 `~/.cache/jibsa` 를 건드리지 않는다.
- 테스트 코드 형식(파일·함수 이름, `MockTransport` 끼우는 법)은 [코드 형식](code-style.md#8-테스트-코드)에 있다.
