# Output Contract

jibsa 는 LLM 에이전트가 셸로 호출하는 도구라, CLI 의 출력 형식이 곧 공개 API 다.
여기 적힌 규칙을 바꾸는 변경은 `docs/common.md`와 해당 소스 CLI 문서의 출력 규칙·사용 지침도 함께 고친다.
구현은 `cli/output.py`, `cli/app.py` 의 `run()`, `core/listing.py`.

## stdout / stderr

아래 JSON 계약은 조회 결과와 에러에 적용한다. `--help`·자동완성·`guide`(LLM 가이드 `docs/llm.md`)·`--version`은 CLI 텍스트를 출력하고, `--verbose`는 stderr에 진행 로그를 추가한다.

`--help` 는 stdout 이 터미널이면 Rich 표로, 아니면(파이프·LLM 셸) 줄글로 쓴다 (`use_plain_help`). Rich 는 터미널이 아니면 폭을 80칸으로 잡아 옵션 설명을 `…` 로 자르고 공백이 출력의 대부분이라, 셸로 부르는 에이전트에게는 줄바꿈만 있는 텍스트가 맞다. 도움말 문구(docstring)는 두 모양 모두에서 줄바꿈대로 나오니 예시 명령은 한 줄에 하나씩 쓴다.

- **결과는 stdout 에 JSON 하나.** `emit()` 으로만 쓴다. `print` 나 로그를 stdout 에 쓰지 않는다.
- **에러는 stderr 에 `{"error": {...}}` JSON 하나.** `emit_error()` 로만 쓴다. 사용법 오류
  (없는 옵션, 잘못된 값, 인자 누락)도 마찬가지다. 이를 위해 `run()` 이 Typer 를
  `standalone_mode=False` 로 돌려 Click 예외를 직접 잡는다.
- 로그(`--verbose`)는 `logging` 으로 stderr 에 나간다. 기본 레벨은 ERROR.
- JSON 은 터미널이면 들여쓰기, 파이프면 한 줄. `--pretty/--compact` 로 강제한다.
  `ensure_ascii=False` 로 한글을 그대로 쓴다.

## 에러

```json
{"error": {"code": "LISTING_UNAVAILABLE", "message": "...", "hint": "...", "source": "zigbang", "listing_id": "..."}}
```

- `code` 는 기계가 읽는 값, `message` 는 사람이 읽는 설명, `hint` 는 **다음에 할 행동**이다.
  LLM 이 hint 를 보고 재시도·옵션 수정·소스 변경을 고르므로, 새 에러에는 구체적인 hint 를 단다.
- 애플리케이션 에러는 `core.errors.JibsaError` (또는 서브클래스)로 던진다. 추가 필드는 `details` 에
  넣으면 에러 JSON 에 평탄하게 실린다.
- CLI 명령은 본문을 `with handle_errors(SOURCE):` 로 감싼다. 예외 → 코드 매핑:

| 예외 | code | exit |
| --- | --- | --- |
| `JibsaError` | 예외의 `code` | 1 (`INVALID_ARGUMENT` 는 2) |
| pydantic `ValidationError` — 요청 모델(`RequestModel`) | `INVALID_ARGUMENT` | 2 |
| pydantic `ValidationError` — 응답 모델·`Listing` (응답 형식 변경) | `PARSE_ERROR` | 1 |
| `HTTPStatusError` 404 / 429 / 그 밖 | `NOT_FOUND` / `RATE_LIMITED` / `UPSTREAM_ERROR` | 1 |
| 그 밖의 `HTTPError` | `NETWORK_ERROR` | 1 |
| `ValueError` (JSON 아닌 응답의 `JSONDecodeError`, `RelayStoreNotFoundError`·`RelayRecordNotFoundError`) | `PARSE_ERROR` | 1 |
| 그 밖의 모든 예외 | `INTERNAL_ERROR` | 1 |
| Click `UsageError` (`run()` 에서) | `INVALID_ARGUMENT` | 2 |
| 그 밖의 Click `ClickException` (`run()` 에서, 파일 인자 오류 등. 지금은 나오지 않음) | `CLI_ERROR` | 예외의 `exit_code` |
| `KeyboardInterrupt` (Typer 가 `Exit(130)` 으로 바꾼 것), Click `Abort` (`run()` 에서) | `INTERRUPTED` | 130 (`Abort` 는 1) |

- 쓰이는 코드: `INVALID_ARGUMENT`, `REGION_NOT_FOUND`, `REGION_AMBIGUOUS`, `REGION_NOT_SUPPORTED`, `LISTING_UNAVAILABLE`,
  `NOT_FOUND`, `RATE_LIMITED`, `UPSTREAM_ERROR`, `NETWORK_ERROR`, `PARSE_ERROR`, `INTERNAL_ERROR`, `INTERRUPTED`, `CLI_ERROR`. 새 코드를 만들면
  공통 사용 문서의 exit code 표와 오류 대응에 추가한다.
- 입력 검증 실패는 항상 exit 2. 사용자 정의 hint 가 필요한 사용법 오류는 `HintedUsageError` 를, 옵션 값 오류는
  `HintedBadParameter` 를 쓴다 (예: `require_korea`, `split_csv`). 다른 소스의 옵션·값을 옮겨 쓴 오류(직방 `--option
  반려동물가능`, 직방에 네이버 `--facility`)는 명령마다 둔 `UsageHints` 표로 이 명령에서 주는 법을 hint 에 싣는다. 목록 옵션의
  틀린 값은 `split_csv` 가, 없는 옵션과 숫자로 못 바꾸는 값은 `run()` 이 찾는다. 표에 없는 옵션이 다른 소스 매물 검색에
  있으면 그 명령을 알린다. 표는 각 소스 CLI 의 `USAGE_HINTS` 에 명령 경로(`jibsa naver search listings`)로 등록한다. 값을 바꿔
  받지는 않는다 (뜻이 조금 다른 조건을 멋대로 옮기지 않는다).
- 요청 모델 검증 실패의 message 는 검증 함수가 던진 문구 그대로다 (pydantic 이 붙이는 `Value error, ` 를 뗀다).
  hint 는 사용법 오류와 같은 `'<명령> --help' 로 사용법을 확인하세요` 다.
- `--trade` 와 맞지 않는 가격 조건(전세 + 월세 상한 등)은 `infer_trade_types` 가 사용법 오류로 막는다. 세 소스 모두
  서버가 그 조건을 조용히 무시한다 (2026-10-10 실측).
- 에러 JSON 의 `source` 는 기본으로 명령의 소스지만, `JibsaError.details['source']` 가 있으면 그 값이 이긴다.
  한 소스의 명령이 위치 찾기에 다른 소스를 쓰면 그 단계의 에러(`REGION_NOT_FOUND`, `RATE_LIMITED`)는 위치를 찾은
  소스 이름을 단다. 소스별 위치 찾기 순서는 각 provider 가이드에 있다 (예: [당근](providers/daangn.md)은 직방 → 네이버).

## 매물 출력

- 모호하거나 넓은 지역 안내, 당근이 다른 지역으로 조회한 안내(`region_notes`), 거래 유형을 좁힌 안내(`infer_trade_types`), 조건에 맞는 매물이 `limit` 보다 많아 일부만 돌려준다는 안내(`core.listing.limit_notes`)는 `emit(..., notes=...)` 로 맨 앞 `notes` 에 붙이고, 없으면 키를 뺀다. 안내는 짧게 쓴다 (매번 나오는 안내는 출력 토큰을 늘린다). 예전의 `notice`(원 사이트에서 확인하라는 같은 문장)는 매 응답 토큰만 늘려 뺐다. 그 안내는 `docs/llm.md` 에 있다.
- 안내마다 앞에 종류 태그를 붙인다 (`core.listing.note`, `NoteKind`): `[일부]` 더 받을 결과가 있다, `[범위]` 찾은 범위가 요청과 다르다, `[제외]` 받은 것 중 뺀 매물이 있다, `[모호]` 같은 이름 중 하나를 골랐다, `[거래]` 거래 유형을 짐작해 좁혔다, `[실패]` 덤 조회가 실패했거나 대체 경로로 찾았다, `[참고]` 그 밖. 새 안내는 만드는 자리에서 `note(종류, 문장)` 으로 만든다. 태그 없이 둔 안내는 `emit` 이 `[참고]` 를 붙이고(`tagged_notes`), 같은 안내가 두 번이면 하나만 남긴다. 태그는 `[실패]` 처럼 LLM 이 문장을 다 읽지 않고도 사용자에게 알릴지 가르는 데 쓴다.
- 찾을 때마다 같은 안내(직방·당근 원룸 종류의 한계)는 `notes` 에 붙이지 않고 `docs/llm.md` 에 둔다.
- 리스트를 그대로 내보내면 `notes` 를 붙이기 위해 `{"items": [...]}` 로 감싼다.
- 좌표(`lat`·`lng`)는 `emit` 이 소수 일곱째 자리로 반올림한다 (원본의 부동소수점 찌꺼기 `127.04934499999999` 를 지운다).

### 값이 없을 때

| 상태 | 표현 | 구현 |
| --- | --- | --- |
| 해당 없음 (그 거래·조회에 원래 없는 항목) | **키를 뺀다** | `Listing.not_applicable_fields()` + `@model_serializer` |
| 모름 (해당은 되지만 소스가 알려 주지 않음) | `null` | 필드 기본값 `None` |
| 알려 줬는데 비어 있음 | `[]` | 빈 리스트 |

- 해당 없음 예: 월세의 `price_manwon`, 매매의 `deposit_manwon`·`rent_manwon`
  (`NOT_APPLICABLE_PRICE_FIELDS`), 중심점 없는 조회와 상세의 `distance_km`.
- service 에서 "모름"과 "없음"을 섞지 않는다. 소스가 옵션 목록을 주지 않았으면 `options=None`,
  줬는데 비었으면 `options=[]`.
- 소스 고유 필드가 있는 상세 모델은 `not_applicable_fields()` 를 넓혀 같은 방식으로 키를 뺀다
  (예: `DaangnListingDetail` 은 상가가 아닌 매물의 권리금, 직거래의 중개보수, 단지 없는 매물의 단지 필드).

### 금액·단위

- 금액 필드는 전부 **만원**이고 이름이 `_manwon` 으로 끝난다. 네이버는 원 단위라 `won_to_manwon`.
- 면적은 `area_m2` + `area_pyeong`, 날짜는 한국 날짜 `YYYY-MM-DD` (`normalize_date`).
- 층(`floor`)은 `normalize_floor` 로 표기를 맞춘다 (지하 `지하1`, 반지하, 저·중·고 → 저층·중층·고층). `Listing` 출력에는 `floor` 바로 뒤에 숫자 `floor_number` 가 붙는다 (지하는 음수, 몇 층인지 모르면 `null`).
- 주소의 시·도는 정식 명칭(`서울특별시`, `강원특별자치도`)으로 맞춘다. `Listing.address` 는 검증기가
  `normalize_address` 를 거치므로 provider 가 따로 부르지 않아도 된다. 단지 정보처럼 `Listing` 밖의 주소는 직접 부른다.

### 거래 유형

- `trade_type` 은 `매매`·`전세`·`월세`·`단기임대` 넷이다. 지원 거래 유형·기본값·가격 조건에 따른 거래 유형 추론은 명령별 CLI 선언과 사용자 문서를 따른다. 아파트·실거래·단기임대 서비스처럼 일부 유형만 지원하거나 기본 매매인 명령도 있다.
- 단기임대를 월세로 내보내지 않는다. 보증금이 월세 한두 달치라 싼 월세로 읽힌다. 소스 표기: 네이버 `B3`,
  당근 `SHORT`, 직방은 요약의 `sales_type: 월세` + `contract: 단기` (거래 유형 필터 값은 `단기`).

### 방 구조

- `room_type` 은 실제 방 구조만 쓴다. 소스 카테고리 이름으로 추측하지 않고, 알 수 없으면 `null`(모름)이다.
  소스별로 방 구조를 정하는 방법은 각 provider 가이드에 있다.

### 내보내지 않는 정보

jibsa 는 **찾기까지만** 한다. 원 사이트를 대신하게 되는 정보는 모델에 넣지 않는다.

- 매물 출력에서는 사진, 본문(매물 설명), 중개사 정보(이름·전화·주소·등록번호), 도로명 주소, 조회수, 원본 응답 통째를 내보내지 않는다. 단지 정보의 구조화된 `road_address`는 제공할 수 있다.
  관심(찜) 수(당근 `watch_count`)는 조회수가 아니라 매물을 고르는 데 쓰는 사실이라 내보낸다.
- 본문은 일부도 내보내지 않는다. 중개사가 쓴 자유 형식 글이라 전화번호·중개사 이름·사무소명이 섞이는데,
  정규식으로 가리면 빠짐이 생기고 넓히면 매물 설명이 지워진다. 고르는 데 필요한 사실은 구조화 필드로 준다.
- 매물 좌표(`lat`/`lng`)는 거리 계산용으로 모델에 있지만 `Field(exclude=True)`라 출력되지 않는다. 위치 검색의 지역 후보·검색 중심 좌표는 이 금지 대상이 아니다. 단지 좌표는 내보내지 않는다.
- 응답 모델(`api/response/`)에는 이런 필드가 있어도 되지만, `Listing` 으로 옮기지 않는다.

### 만료 매물

결과는 항상 실시간 조회다. 캐시를 두지 않는다. 소스별 거래 가능 조건:

| 소스 | 거래 가능 조건 | 목록 | 상세 |
| --- | --- | --- | --- |
| 직방 | 요약 `status: true`, 상세 `status: "open"`. 상가 `status: "open"`, 단기임대 상세 `status: true` + `checkStatus: COMPLETE`. 아파트 목록은 노출 중인 매물만 온다 | 제외 | `ListingUnavailableError` |
| 네이버 | 응답 `isSuccess: true`, 아는 거래 유형 코드 (`TRADE_NAME_BY_CODE`) | 노출 중인 매물만 온다. 모르는 코드는 제외 | `ListingUnavailableError` (모르는 거래 유형이면 `reason: UNKNOWN_TRADE_TYPE`, 모르는 매물 유형이면 `UNKNOWN_REAL_ESTATE_TYPE`) |
| 당근 | `ON_GOING` 이고 `isHide`·`invisibleReason`·`invisibleInfos` 없음 (`is_available`), 아는 거래 조건이 있음 | 제외 | `ListingUnavailableError` (상태·사유 포함, 거래 조건이 없으면 `reason: NO_TRADE_INFO`) |

## 개수 상한

`--limit`의 최대값은 CLI 정책이며 서버의 요청당 최대 개수와 구분한다.

- 매물 검색의 `--limit` 은 조회 할당량이다. 실제로 받은 원본 수로 세고, 받은 뒤 중복·거래 불가·조건 불일치로 뺀 만큼 다시 채우지 않는다.
- 요청보다 적게 받으면 남은 몫을 다음 페이지·지도 칸·단지에서 받을 수 있다. 다음 페이지가 없거나 커서가 진행하지 않거나 요청 횟수 상한에 닿으면 중단한다.
- `returned`는 실제 반환 수이며 요청한 `limit`과 같다는 보장이 없다. 집계 범위·일부 조회·제외 사유는 `notes`로 설명한다.
- 단지·지역 후보, 실거래, 통근처럼 결과 상한과 원본 조회 상한·페이지·역별 예산이 따로 있는 명령도 있다.

조회 방식별 예산과 한 소스에만 있는 예외는 그 소스의 provider 가이드(`references/providers/`)에, 명령별 기본값·최대값은
사용자 문서의 해당 명령 절에 적는다. 상한을 올리면 요청 수가 늘 수 있으므로 요청 제한 정책과 함께 검토한다.
