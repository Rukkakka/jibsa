# 공통 개발 환경

[개발 규약](../AGENTS.md) · [코드 형식](code-style.md) · [작업 절차](workflow.md)

## 설치

코드를 고치려면 저장소를 받아 편집 가능 모드로 설치한다. 고친 코드가 바로 반영된다. Python·git 설치는 [설치 문서의 준비물](../docs/install.md#1-준비물)을 따른다.

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

Windows 는 [README 의 Windows 에서 쓸 때](../README.md#windows-에서-쓸-때)(UTF-8 출력 설정)도 그대로 적용된다. `Activate.ps1` 이 실행 정책 때문에 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 를 한 번 실행한다.

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

- 코드를 바꾸면 CLI 직접 조회나 원본 응답 확인처럼 실제 API 호출로 동작을 확인하는 것이 기본이다. 가짜 응답(픽스처·`MockTransport`)으로만 확인했다고 하지 않는다. 실제 API 를 부르는 테스트(live 테스트)는 두지 않고 CLI 직접 조회로 확인한다. 매일 새벽 도는 [API 감시](#매일-api-감시)만 예외다 (pytest 가 아니라 따로 도는 워크플로다).
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

## 매일 API 감시

비공식 API 는 사이트가 응답을 바꾸면 조용히 깨진다 (당근 웹 개편으로 SSR 페이지를 못 읽은 #70 처럼). 사용자보다 먼저 알려고
[API 감시 워크플로](../.github/workflows/api-monitor.yml)가 한국 시간 매일 04:17 에 직방·당근의 모든 CLI 명령을 실제로 부른다
([scripts/monitor/api_check.py](../scripts/monitor/api_check.py)). 네이버는 GitHub 러너에서 응답을 받지 못해 매일 실행에서 빼고(`DAILY_GROUPS`),
감시 목록에는 남겨 필요할 때 로컬에서 돌린다. CI 는 여전히 실제 API 를 부르지 않는다.

- **무엇을 부르나:** 사이트에 요청하는 명령 모두 (`limits`·`guide` 만 뺀다). 매물 검색은 찾는 방식(동 이름 경계·역 반경·좌표 반경·단지·재개발
  구역)마다 쓰는 API 가 달라 방식별로 부르고, 상세 명령은 앞 결과의 번호(매물 ID·단지 번호·평형·학교 코드·사업·시설 번호)를 이어 받는다.
  지역은 결과가 0건일 리 없는 곳(역삼동·강남역·강남구·한남동)이고 `--limit` 은 작게 준다. 소스마다 러너를 나눠, 한 소스가 막혀도 다른 소스
  검사는 그대로 된다.
- **판정:** 명령마다 셋으로 나눈다.

  | 판정 | 기준 |
  | --- | --- |
  | 정상 | exit 0, 그 명령에 정한 칸(`Step.expect`)에 값이 있음 |
  | 고장 | `PARSE_ERROR`·`INTERNAL_ERROR`·`NOT_FOUND`·`REGION_NOT_FOUND`·4xx 이거나 상태 없는 `UPSTREAM_ERROR`(웹 쿼리 해시 거절 등) 같은 에러, 정한 칸이 비어 있음, JSON 이 아닌 출력, `notes` 의 "jibsa 업데이트가 필요합니다"·"jibsa 업데이트가 필요할 수 있습니다"(당근 필터 API 대신 예전 방식으로 돎, 단지 후보·매물 수·역 검색 같은 덤 조회·대체 경로가 깨져 그 값만 빠짐. 당근 `UPDATE_NEEDED`·`UPDATE_MAYBE_NEEDED` 를 감시가 그대로 가져다 쓴다), 결과 파일 없음(조회 잡 실패) |
  | 확인 못 함 | `RATE_LIMITED`, `NETWORK_ERROR`, 5xx `UPSTREAM_ERROR`, `LISTING_UNAVAILABLE`(검색 직후 내려간 매물), 5분 안에 끝나지 않음, 앞 명령이 번호를 주지 않아 건너뛴 상세 |

- **알림:** 고장이면 `api-broken` 이슈를 열고(열려 있으면 댓글) 실행이 실패로 끝나 GitHub 이 메일로 알린다. 모든 소스가 정상이면 그
  이슈를 닫는다. 같은 소스가 사흘 연속 확인 못 함이면 `api-blocked` 이슈를 열고, 확인 못 함이 없어지면 닫는다. 막힘이 이어지면 그 소스를
  덜 자주 돌리는 것을 검토한다.
- **명령을 추가·삭제하면** `api_check.py` 의 `GROUPS` 도 고친다. 매물을 찾는 새 방식(다른 API 를 쓰는 경로)을 넣었으면 그 방식도 넣는다.
  `tests/test_cli.py::test_every_source_command_is_in_api_monitor` 가 CLI 명령 목록과 대조해 명령을 빠뜨리면 실패한다.
- **수동 실행:** Actions 의 "API 감시" → Run workflow, 또는 `gh workflow run api-monitor.yml`. 로컬에서는
  `.venv/bin/python scripts/monitor/api_check.py run zigbang --out result.json` 처럼 소스 하나를 돌린다. 요청이 수십 번 나가니 필요할 때만
  돌린다. 네이버는 매일 실행에 없어 로컬 `run naver` 로만 본다. 이슈 처리는 `report result.json --issues --dry-run` 으로 보낼
  `gh` 명령만 본다.
- 감시 파일(`scripts/monitor/`, 워크플로)을 고친 PR 에서도 한 번 돌고, 이슈는 건드리지 않는다. 고장이면 그 PR 의 검사가 실패한다 (필수 검사는
  아니다).
- 공개 저장소라 실행 기록에는 요청 로그만 남기고, 결과 본문(매물 제목·주소)은 고장·확인 못 함일 때만 앞부분을 남긴다.
- 공개 저장소에 60일 동안 활동이 없으면 GitHub 이 예약 실행을 끈다. 꺼졌으면 Actions 의 "API 감시" 에서 다시 켠다.
