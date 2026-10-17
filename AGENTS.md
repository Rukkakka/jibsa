# AGENTS.md

직방·네이버 부동산·당근부동산의 **현재 거래 가능한 매물**을 조회하는 CLI (`jibsa`).
LLM 에이전트가 셸로 호출하는 도구라, 출력 형식과 에러 형식이 곧 API 다.
CLI 코드는 모두 `src/jibsa/` 아래에 있다.
개발 문서(구현 규약·소스별 개발 가이드)는 `references/`, 사용자 문서(CLI 사용법)는 `docs/`에 있다.
매일 새벽 직방·당근의 모든 CLI 명령을 실제로 불러 보는 감시(네이버는 로컬에서)는 `scripts/monitor/` 와 `.github/workflows/api-monitor.yml` 이다 ([매일 API 감시](references/development.md#매일-api-감시)).

## 구조

| 경로 | 내용 |
| --- | --- |
| `cli/` | Typer 명령 (`limits`, `guide`, `zigbang`/`naver`/`daangn` 하위 명령), JSON·에러 출력, 공용 옵션 별칭 (`options.py`) |
| `core/http.py` | `BaseHTTPClient` — httpx 클라이언트 수명주기, 재시도 술어, `raise_for_status` |
| `core/ratelimit.py` | 프로세스 간 공유 요청 제한 (`RateLimiter`, `RateLimitedError`) |
| `core/listing.py` | 공통 `Listing` / `ListingDetail` 모델과 정규화 헬퍼 (만원 환산, 날짜, 주소) |
| `core/errors.py` | `JibsaError` 계열 — CLI 가 `{"error": {...}}` 로 내보내는 에러 |
| `core/schema.py` | `RequestModel` (`extra='forbid'`) / `ResponseModel` (`extra='allow'`) |
| `core/geo.py` | geohash·거리 계산, 한국 좌표 범위, 기본 검색 반경 |
| `core/korean.py` | 한글 이름 뒤 조사 고르기 (`particle`, `quoted`), 행정동 검색어에 법정동 힌트 (`legal_dong_hint`), 법정동 코드 단위 (`is_dong_code`, `is_ri_code`) |
| `providers/<source>/` | `api/` 아래층 (`client.py` · `request/` · `response/`, 당근은 `relay.py` · `parser.py` 도) → `service/` 윗층. request·response·service 는 같은 이름의 기능별 모듈 ([모듈 구성](references/provider-conventions.md#모듈-구성)) |

소스별 비공식 API 의 엔드포인트·필드 의미는 각 provider 의 `api/client.py` docstring 과
`api/response/` 모델 설명에 있다. 엔드포인트를 추가·수정하기 전에 먼저 읽고, 응답 형태는
CLI 직접 조회나 원본 응답으로 확인한다.

## 꼭 지킬 것

- **로그인 없는 기능만.** 계정·쿠키·API 키를 받지 않고, 로그인이 필요한 API(관심 단지·매물, 내 집 인증 등)나 사용자 대신 보내는 기능(문의·예약·신고)은 넣지 않는다. 새 엔드포인트는 로그인 없이 호출되는지 먼저 확인한다. ([README 원칙](README.md#원칙-로그인-없는-기능만))
- **금액은 전부 만원.** 필드 이름에 단위를 붙인다 (`deposit_manwon`). 네이버는 원 단위라 `won_to_manwon` 으로 환산.
- **조회 결과는 stdout JSON, 에러는 stderr JSON.** 도움말·자동완성·`guide`·`--version` 은 CLI 텍스트이며 `--verbose` 진행 로그는 stderr 로 나간다. 새 에러는 `JibsaError` 로 코드·힌트를 붙여 던진다.
- **값이 없을 때:** 해당 없음 → 키 삭제, 모름 → `null`, 비어 있음 → `[]`.
- **만료 매물은 내보내지 않는다.** 목록에서는 거르고, 상세에서는 `ListingUnavailableError`.
- **서버가 거른 결과를 같은 조건으로 다시 거르지 않는다.** 소스의 카테고리를 건물 용도나 방 개수로 다시 해석하지 않는다. 직접 거르는 건 서버가 받지 않는 조건과 서버 필터 없는 대체 조회뿐이고, 거래 조건을 못 골라 뺀 매물은 사유를 `notes`로 알린다. ([서버 필터와 클라이언트 후처리](references/provider-conventions.md#서버-필터와-클라이언트-후처리))
- **사진·중개사 연락처·본문(매물 설명)·매물 좌표는 출력하지 않는다.** 위치 검색의 지역 후보 좌표는 제공할 수 있다. 확인·문의는 `url` 의 원 사이트에서.
- **모든 HTTP 요청은 요청 제한 훅을 거친다.** 새 클라이언트도 `rate_limit_hooks()` 를 `event_hooks` 로 넘긴다.
- **검증은 실제 API 로, 테스트는 최소로.** 코드를 바꾸면 CLI 직접 조회 같은 실제 API 호출로 확인한다 (요청은 최소로). 테스트는 아주 드문 엣지케이스나 틀어지면 안 되는 핵심 동작일 때만 추가한다. 전체 `pytest` 는 먼저 묻고, 평소에는 바꾼 부분 테스트 몇 개만 이름으로 골라 한 번 돌린다. ([검증과 테스트](references/development.md#검증과-테스트))
- **명령을 추가·삭제하면 매일 API 감시 목록도 고친다.** `scripts/monitor/api_check.py` 의 `GROUPS` 에 넣고, 매물을 찾는 새 방식(동 이름·역·반경·단지처럼 다른 API 를 쓰는 경로)을 넣었으면 그 방식도 넣는다. 명령을 빠뜨리면 `test_every_source_command_is_in_api_monitor` 가 실패한다. ([매일 API 감시](references/development.md#매일-api-감시))

## 문서 지도

공통 개발 규약 (`references/`)

- [development.md](references/development.md) — 개발 환경 설치, 검증과 테스트 원칙
- [architecture.md](references/architecture.md) — 계층 구조, 요청 흐름, 요청 제한
- [provider-conventions.md](references/provider-conventions.md) — provider 모듈 작성 규칙 (action id 명명, 재시도, 모델 배치, 서버 필터와 클라이언트 후처리)
- [output-contract.md](references/output-contract.md) — CLI 출력·에러·exit code 규약, `Listing` 필드 규칙
- [code-style.md](references/code-style.md) — 문자열, import 순서, pydantic 선언, 타입 힌트, docstring, 테스트 코드 형식
- [workflow.md](references/workflow.md) — 이슈 → 브랜치 → 커밋 → PR 절차
- [release.md](references/release.md) — 버전 번호 규칙, CHANGELOG 쓰는 법, 릴리스·태그·GitHub Release 절차

소스별 개발 가이드 (`references/providers/`) — 그 소스에만 있는 구현·예외

- [당근](references/providers/daangn.md) · [네이버](references/providers/naver.md) · [직방](references/providers/zigbang.md)

## 문서 갱신

README는 제작 목적·설치·LLM 연결 방법·문서 링크를 담는다. 사용자 문서는 `docs/`, 개발 문서는 `references/`에 둔다. CLI 문서는 LLM 에이전트에게 주는 사용 규칙이기도 하다.

`docs/llm.md` 는 에이전트가 가장 먼저 읽는 요약이고 `jibsa guide` 가 그대로 출력한다. 소스 문서(`docs/common.md`·`zigbang.md`·`naver.md`·`daangn.md`)는 `jibsa guide <소스> [절 이름]` 으로 출력한다 (모두 설치본에는 패키지 안으로 복사된다). 그래서 절 제목에 명령 이름을 백틱으로 쓴다 (`jibsa guide zigbang listing` 이 그 절을 고른다). 짧게 유지하고 (200줄 이하), 링크는 설치본에서도 열리게 GitHub 전체 주소로 쓴다. 옵션 표·실측 근거는 넣지 않고 명령 고르기·출력 읽기·틀리기 쉬운 점·에러 대응만 적은 뒤 자세한 절로 링크한다.

| 바뀐 것 | 고칠 문서 |
| --- | --- |
| 한 소스의 명령·옵션·반환 필드·조회 한도 | `docs/<source>.md` |
| 명령 추가·삭제, 에이전트가 틀리기 쉬운 해석 규칙(단위·누락값·ID·원룸의 뜻 등)·에러 대응 | `docs/llm.md` |
| 명령 추가·삭제, 매물을 찾는 새 방식(다른 API 를 쓰는 경로) | `scripts/monitor/api_check.py` 의 `GROUPS` (매일 API 감시 목록) |
| 공통 사용법(출력·에러 대응)·요청 제한 정책 | `docs/common.md` |
| 한 소스의 구현·예외 | `references/providers/<source>.md` |
| 여러 소스에 공통인 개발 규약 | `references/` 바로 아래 문서 |
| 사용자(에이전트 포함)에게 보이는 변경 | `CHANGELOG.md` 의 `Unreleased` ([쓰는 법](references/release.md#changelog-쓰는-법)) |
| README 데모에 나오는 명령·출력 (`jibsa --version`, `zigbang search listings room`) | `docs/demo/demo.gif` — `vhs docs/demo/demo.tape` 로 다시 녹화 |
| README 맨 위 Claude Code 데모에 나오는 것 (`jibsa guide`, 직방 원룸 검색 출력) | `docs/demo/claude.gif` — `vhs docs/demo/claude.tape` 로 다시 녹화한 뒤 `python3 docs/demo/hide_plan.py docs/demo/claude.gif` |

한 소스에만 해당하는 규칙·예외는 공통 문서에 적지 않고 그 소스 문서에 적는다. 명령의 인자·기본값·조회 한도·반환값·오류·주의사항은 해당 명령 절에서 설명한다. 요약 표는 해당 절과 일치시키고 다른 명령 절에 설명을 복사하지 않는다. 공통 규칙은 복사하지 않고 링크로 연결한다.

## 작업 절차

커밋 전에 **[references/workflow.md](references/workflow.md)** 를 읽는다. 요약:
**커밋 전에 `.github/ISSUE_TEMPLATE/` 템플릿으로 이슈를 연다.** `main` 에 직접 커밋하지 않고
`<type>/<slug>` 브랜치에서 `Refs #12` 로 이슈를 달아 커밋한다. 모든 변경은 PR 템플릿을 채운 PR 로
들어가고, 이슈는 PR 본문(`Closes #12`)에서 닫는다. 커밋 하나에 관심사 하나, `git add -A` 금지.
사용자에게 보이는 변경은 그 PR 에서 `CHANGELOG.md` 에 적는다. 버전 올리기·태그·GitHub Release 는
[references/release.md](references/release.md) 를 따른다.
