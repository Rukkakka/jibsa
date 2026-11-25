# Output Contract

jibsa 는 LLM 에이전트가 셸로 호출하는 도구라, CLI 의 출력 형식이 곧 공개 API 다.
여기 적힌 규칙을 바꾸는 변경은 `docs/common.md`와 해당 소스 CLI 문서의 출력 규칙·사용 지침도 함께 고친다.
구현은 `cli/output.py`, `cli/app.py` 의 `run()`, `core/listing.py`.

## stdout / stderr

아래 JSON 계약은 조회 결과와 에러에 적용한다. `--help`·자동완성·`guide`(LLM 가이드 `docs/llm.md`)·`--version`은 CLI 텍스트를 출력하고, `--verbose`는 stderr에 진행 로그를 추가한다.

`--help` 는 stdout 이 터미널이면 Rich 표로, 아니면(파이프·LLM 셸) 줄글로 쓴다 (`use_plain_help`). Rich 는 터미널이 아니면 폭을 80칸으로 잡아 옵션 설명을 `…` 로 자르고 공백이 출력의 대부분이라, 셸로 부르는 에이전트에게는 줄바꿈만 있는 텍스트가 맞다. 도움말 문구(docstring)는 두 모양 모두에서 줄바꿈대로 나오니 예시 명령은 한 줄에 하나씩 쓴다.

- **결과는 stdout 에 JSON 하나.** `emit()` 으로만 쓴다. `print` 나 로그를 stdout 에 쓰지 않는다.
  상세(`listing`)도 ID 를 하나만 받는다. 후보 여러 개는 셸 호출 한 번에 `;` 로 이어 부르면 매물마다 JSON 한 줄이
  차례로 나오고, 실패한 매물은 그 자리에 `listing_id` 가 든 에러 JSON 이 나와 여러 ID 를 받는 것과 출력·호출 수가
  같다 (2026-10-23 실측: 직방 `listing` 3개 중 가운데 없는 ID 하나가 그 순서로 에러). 그래서 docs/llm.md 가 `;` 로
  이으라고 안내한다.
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
  `listing_id` 는 `listing` 에 넘길 수 있는 매물 ID 만 싣는다. 매물이 아닌 묶음 ID(직방 `catalog` 의 빈 묶음)는 `catalog_id` 로 싣는다.
  LLM 이 hint 를 보고 재시도·옵션 수정·소스 변경을 고르므로, 새 에러에는 구체적인 hint 를 단다.
- 애플리케이션 에러는 `core.errors.JibsaError` (또는 서브클래스)로 던진다. 추가 필드는 `details` 에
  넣으면 에러 JSON 에 평탄하게 실린다. 값이 없을 때도 출력 규칙과 같다: `details` 의 `None` 은 `null`(모름, 예: 후보를 다 세지
  못한 `candidate_count`)로 실리고, 해당 없음이면 그 키를 `details` 에 넣지 않는다 (`ListingUnavailableError` 의 상태·사유).
- CLI 명령은 본문을 `with handle_errors(SOURCE):` 로 감싼다. 예외 → 코드 매핑:

| 예외 | code | exit |
| --- | --- | --- |
| `JibsaError` | 예외의 `code` | 1 (`INVALID_ARGUMENT` 는 2) |
| pydantic `ValidationError` — 요청 모델(`RequestModel`) | `INVALID_ARGUMENT` | 2 |
| pydantic `ValidationError` — 응답 모델·`Listing` (응답 형식 변경) | `PARSE_ERROR` | 1 |
| `HTTPStatusError` 404 / 429 / 그 밖 | `NOT_FOUND` / `RATE_LIMITED` / `UPSTREAM_ERROR` | 1 |
| `CorsBlockedError` (브라우저가 CORS 로 응답을 막음, `core/browser.py`) | `UPSTREAM_ERROR` (다른 소스를 가리키는 hint) | 1 |
| httpx `ProxyError` (프록시 주소를 해석하지 못함·브라우저가 쓸 수 없는 프록시·프록시에 닿지 못함·프록시가 이 사이트를 거절함) | `NETWORK_ERROR` (프록시 설정을 가리키는 hint) | 1 |
| `CertificateError` (브라우저가 우리 요청의 사이트 인증서를 믿지 못함, `core/browser.py`) | `NETWORK_ERROR` (인증서를 OS 에 설치하라는 hint) | 1 |
| 그 밖의 `HTTPError` | `NETWORK_ERROR` | 1 |
| `ValueError` (JSON 아닌 응답의 `JSONDecodeError`, `RelayStoreNotFoundError`·`RelayRecordNotFoundError`) | `PARSE_ERROR` | 1 |
| 그 밖의 모든 예외 | `INTERNAL_ERROR` | 1 |
| Click `UsageError` (`run()` 에서) | `INVALID_ARGUMENT` | 2 |
| 그 밖의 Click `ClickException` (`run()` 에서, 파일 인자 오류 등. 지금은 나오지 않음) | `CLI_ERROR` | 예외의 `exit_code` |
| `KeyboardInterrupt` (Typer 가 `Exit(130)` 으로 바꾼 것), Click `Abort` (`run()` 에서) | `INTERRUPTED` | 130 (`Abort` 는 1) |

- `CorsBlockedError`·`ProxyError`·`CertificateError` 는 `JibsaError` 가 아니라 httpx 전송 오류(`TransportError`)다. transport
  안에서 나는 전송 오류라 덤 조회(`OPTIONAL_LOOKUP_BASE_ERRORS` 의 `HTTPError`)가 삼켜야 주된 결과를 돌려줄 수 있어서다. 그래서
  코드·hint 는 `handle_errors` 가 위 표대로 붙인다. 모두 재시도 술어의 `RETRYABLE_TRANSPORT_ERRORS` 에 들지 않아 재시도하지 않는다.
  첫 화면이 열리지 않은 `EntryPageError` 는 `JibsaError` 라 `OPTIONAL_LOOKUP_BASE_ERRORS` 만 잡는 덤 조회는 삼키지 않는다.
  `JibsaError` 까지 잡는 소스(당근 `OPTIONAL_LOOKUP_ERRORS`)는 삼켜 `notes` 에 남기지만, 다시 열지 않는 첫 화면 실패는
  기억돼(`_failed_entries`) 같은 클라이언트의 본 요청도 같은 에러로 끝나 결과가 같다 ([브라우저 요청](architecture.md#브라우저-요청)).
- 쓰이는 코드: `INVALID_ARGUMENT`, `REGION_NOT_FOUND`, `REGION_AMBIGUOUS`, `REGION_NOT_SUPPORTED`, `LISTING_UNAVAILABLE`,
  `NOT_FOUND`, `RATE_LIMITED`, `UPSTREAM_ERROR`, `NETWORK_ERROR`, `PARSE_ERROR`, `BROWSER_UNAVAILABLE`, `BROWSER_INSTALL_FAILED`,
  `INTERNAL_ERROR`, `INTERRUPTED`, `CLI_ERROR`. 새 코드를 만들면 공통 사용 문서의 exit code 표와 오류 대응에 추가한다.
- 입력 검증 실패는 항상 exit 2. 사용자 정의 hint 가 필요한 사용법 오류는 `HintedUsageError` 를, 옵션 값 오류는
  `HintedBadParameter` 를 쓴다 (예: `require_korea`, `split_csv`). 다른 소스의 옵션·값을 옮겨 쓴 오류(직방 `--option
  반려동물가능`, 직방에 네이버 `--facility`)는 명령마다 둔 `UsageHints` 표로 이 명령에서 주는 법을 hint 에 싣는다. 목록 옵션의
  틀린 값은 `split_csv` 가, 없는 옵션과 숫자로 못 바꾸는 값은 `run()` 이 찾는다. 표에 없는 옵션이 다른 소스 매물 검색에
  있으면 그 명령을 알린다 (`foreign_usage_hint`). 표가 없는 소스 명령(상세·단지·실거래 등)에 없는 옵션이면 이 명령의 옵션을
  알리고 (그 옵션이 있는 다른 명령을 알리면 `real-price --limit` 처럼 같은 일을 하는 `--pages` 를 가렸다), 그룹에 없는 하위 명령이면 그 그룹의 하위 명령을 알린다 (`subcommand_hint`). 표는 각 소스 CLI 의 `USAGE_HINTS` 에 명령 경로(`jibsa naver search listings`)로 등록한다. 값을 바꿔
  받지는 않는다 (뜻이 조금 다른 조건을 멋대로 옮기지 않는다).
- 지역·장소·학교·단지 이름을 위치 인자 하나로 받는 명령은 따옴표 없이 띄어 쓴 이름(`송파구 신천동`)을 `run()` 이 Click 에
  넘기기 전에 한 인자로 잇는다 (`joined_name_args`). 새 명령의 이름 인자는 그 이름을 `NAME_ARGUMENTS` 에 넣는다. ID 인자는
  넣지 않는다 (ID 두 개를 이어 찾지 않고 'unexpected extra argument' 로 알린다). 옵션 값은 잇지 않지만, 이름 위치 인자와
  함께 줄 수 없는 이름 옵션(`NAME_OPTIONS`: 당근 `search listings`·`search commute` 의 `--station`·`--university`·`--address`)은
  값 바로 뒤의 낱말을 그 값에 잇는다 (`--address 테헤란로 152`. 뒤 낱말을 위치 인자로 보면 둘을 함께 준 것이 되어 막혔다).
  뒤 낱말을 이을 앞 낱말의 모양을 아는 옵션은 마지막 낱말이 그 모양일 때만 잇는다 (`NAME_OPTION_PREFIX_WORDS`: 역 이름은
  노선 이름 뒤에 한 낱말이라 `--station 서울5호선 양평역` 은 잇고 `--station 강남 역삼동` 의 역삼동은 위치 인자다). 다음 옵션에서
  끝나고, 모르는 옵션이나 `--` 가 있으면 아무것도 잇지 않아 Click 이 알린다.
- 요청 모델 검증 실패의 message 는 검증 함수가 던진 문구 그대로다 (pydantic 이 붙이는 `Value error, ` 를 뗀다).
  hint 는 사용법 오류와 같은 `'<명령> --help' 로 사용법을 확인하세요` 다.
- `--trade` 와 맞지 않는 가격 조건(전세 + 월세 상한 등)은 `infer_trade_types` 가 사용법 오류로 막는다. 직방·네이버·당근은
  서버가 그 조건을 조용히 무시한다 (2026-10-10 실측). 어느 거래에 쓰라는 안내는 `allowed` 를 주지 않으면 네 소스 공통 유형
  (`SHARED_TRADE_TYPES`)만 들어, 연세가 없는 소스에 '연세 거래에만 쓰세요' 라고 하지 않는다. 당근은 연세 범위(`yearly`)와
  당근 거래 유형(`allowed`)을 넘긴다.
- 에러 JSON 의 `source` 는 기본으로 명령의 소스지만, `JibsaError.details['source']` 가 있으면 그 값이 이긴다.
  소스끼리 부르지 않으므로([계층](architecture.md#계층)) 다른 소스 이름이 붙는 에러는 없다.

## 매물 출력

- 넓은 지역 안내(직방 `wide_area_note` 등), 거래 유형을 좁힌 안내(`infer_trade_types`), 조건에 맞는 매물이 `limit` 보다 많아 일부만 돌려준다는 안내(`core.listing.limit_notes`)는 `emit(..., notes=...)` 로 맨 앞 `notes` 에 붙이고, 없으면 키를 뺀다. 안내는 짧게 쓴다 (매번 나오는 안내는 출력 토큰을 늘린다). 예전의 `notice`(원 사이트에서 확인하라는 같은 문장)는 매 응답 토큰만 늘려 뺐다. 그 안내는 `docs/llm.md` 에 있다.
- 안내마다 앞에 종류 태그를 붙인다 (`core.listing.note`, `NoteKind`): `[일부]` 더 받을 결과가 있다, `[범위]` 찾은 범위가 요청과 다르다, `[제외]` 받은 것 중 뺀 매물·후보가 있다, `[모호]` 같은 이름 중 하나를 골랐다, `[거래]` 거래 유형을 짐작해 좁혔다, `[실패]` 덤 조회가 실패했거나 대체 경로로 찾았다, `[참고]` 그 밖. 새 안내는 만드는 자리에서 `note(종류, 문장)` 으로 만든다. 태그 없이 둔 안내는 `emit` 이 `[참고]` 를 붙이고(`tagged_notes`), 같은 안내가 두 번이면 하나만 남긴다. 태그는 `[실패]` 처럼 LLM 이 문장을 다 읽지 않고도 사용자에게 알릴지 가르는 데 쓴다.
- `[제외]` 중 응답의 객체 목록 안에 빈 항목(null)이 섞여 와서 빼고 읽었다는 안내는 `core.listing.null_items_note` 로 만든다. 끝말이 `UPDATE_MAYBE_NEEDED` 라 매일 API 감시가 그런 응답을 고장으로 알리고, 그 목록으로 계산한 값은 `null`(모름)이다. 계산에 쓰지 않고 보여 주기만 하는 목록처럼 자리별 안내가 없는 곳은 `emit` 이 명령 전체의 뺀 수 합(`core.schema.null_item_tally`)으로 공통 안내(`core.listing.null_items_total_note`, 어느 목록인지는 말하지 않는다)를 `notes` 끝에 붙인다. 결과에 `null_items_note` 가 이미 있으면 붙이지 않고, 끝말은 같아 매일 API 감시가 알린다. `handle_errors` 가 명령 시작에 집계를 0 으로 돌리고 소스를 `emit` 에 넘긴다. 어디서 뺀 수를 보고 무엇을 null 로 두는지의 규칙은 [모듈 구성](provider-conventions.md#모듈-구성)에 있다.
- 찾을 때마다 같은 안내 중 거의 모든 세션이 부르는 매물 검색의 것(직방·당근 원룸 종류의 한계)은 `notes` 에 붙이지 않고 `docs/llm.md` 에 둔다. 드물게 부르는 명령의 같은 안내(당근 단지 목록의 `recent_trades`·후기 안내, `complex_list_notes`)는 `notes` 에 둔다. 가이드는 모든 세션이 읽어, 그 명령을 쓰지 않는 세션까지 토큰을 쓴다.
- 출력에 1억(`10000` 만원) 이상 `*_manwon` 값이 있으면 `emit` 이 그 값으로 만든 억 환산 예시(`manwon_note`)를 `notes` 끝에 붙인다. 가이드의 환산 규칙만으로는 에이전트가 큰 금액의 자리를 틀려(440000 → 4억 4,000만) 숫자 옆에 정답을 둔다. `--fields` 로 고른 뒤의 값으로 만든다.
- 같은 방식으로 출력에 연세 `yearly_rent_manwon`(당근 제주)이 있으면 `emit` 이 그 결과의 첫 값으로 읽는 법(`yearly_rent_note`,
  `[참고] 연세는 1년치 월세를 한 번에 내는 제주 거래입니다: yearly_rent_manwon 1400 = 1년에 1,400만 원 (월세 아님)`)을 억 환산
  안내 앞에 붙인다. 만원 숫자만 보면 월세로 읽기 쉬워서다.
- 리스트를 그대로 내보내면 `notes` 를 붙이기 위해 `{"items": [...]}` 로 감싼다.
- 매물·단지 검색 결과의 찾은 위치는 `region` 객체이고 안의 칸은 네 소스가 맞다: 직방·네이버·다방은 `name`·`address`·`lat`·`lng`·`legal_division_code`, 당근은 `name`(가장 작은 단위 이름)·`sido`·`sigungu`·`dong`·`region_id`다. 직방 지역 화면(`region-info`·`region-trades`·`region-ranking`)의 `region` 은 `name`·`level`·`address`·`legal_division_code` 로 따로다. 옆 키(직방·네이버 `boundary`·`radius_km`, 다방 `scope`, 당근 지도 화면 범위면 `zoom`·`width_km`·`height_km`)는 사이트마다 찾는 방식이 달라 맞추지 않는다. 옛 '맞추지 않는다' 결정을 `region` 객체 안에 한해 2026-11-25 에 바꿨다 (사용자 결정). 2026-10-31 에이전트 검증(6회)에서 옆 키 차이로 틀린 일은 없었고, 에이전트는 범위를 `[범위]` 안내로 읽었다.
- 매물 목록은 `has_more`(같은 조건으로 더 받을 매물이 있는지)를 준다. 이어 받을 수 있는 검색은 서비스 결과의 `next_position`(출력하지 않음)을 CLI 가 `jibsa.cli.paging.encode_next` 로 감싸 `emit(..., next_token=...)` 으로 `has_more` 뒤에 `next` 로 붙인다. 이어 받기 표에는 명령·지역·조건과 소스가 이어 받을 위치(핀 순서·커서·지역마다 offset)를 담고, 소스에 따라 찾은 지역도 담아 이어 받을 때 지역을 다시 찾지 않는다. 표는 `<state_dir>/next/<번호>.json` 에 하루 동안 두고 `next` 에는 표 내용으로 만든 10자 번호만 준다 (표를 값에 담으면 500~600자라 에이전트가 베껴 쓰는 데 토큰이 들고 틀리기 쉽다). `--next` 는 `decode_next` 가 표를 읽어 명령·조건이 다르면 다른 옵션을 `message` 에 적어 `INVALID_ARGUMENT` 로 막고, 표가 없거나(하루 지남·다른 컴퓨터) 표를 만든 jibsa 버전(`jibsa --version` 한 줄)이 다르면 처음부터 다시 찾으라고 알린다. 업데이트로 옵션이 없어지거나 위치의 꼴이 바뀌면 옛 표를 조건 비교·소스가 읽지 못해서다. 둘 다 명령의 `handle_errors` 밖에서 부르므로 사용법 오류(`HintedBadParameter`)로만 끝낸다. `--limit`·`--details`·`--fields`·`--pretty` 는 이어 받는 동안 바꿀 수 있다 (`RESUMABLE_PARAMS`).
- 좌표(`lat`·`lng`)는 `emit` 이 소수 일곱째 자리로 반올림한다 (원본의 부동소수점 찌꺼기 `127.04934499999999` 를 지운다). 소수점 아래가 없는 실수는 정수로 쓴다 (`1000.0` → `1000`, `_tidy_numbers`). 매물마다 금액·면적에 붙는 `.0` 이 토큰만 쓴다.
- 매물 목록 명령은 `FieldsOption`(`--fields`)을 받아 `emit(..., fields=...)` 로 넘긴다. `emit` 은 `listings` 키의 매물(통근 검색은 역마다의 `listings`)에서 고른 필드와 `ALWAYS_FIELDS`(다음 명령에 넘길 `id`, 네이버 중복 묶음의 `realtor_count`·`asking_range`, 직방 아파트 묶음의 `mixed_prices`·`catalog_id`·`listing_ids`·`realtor_count`·`listing_kind`, 직방 상가 공실 묶음의 `vacant_section`)만 남긴다. 필드 이름은 `Listing` 과 하위 모델의 필드(`listing_field_names`)로 옵션을 읽을 때 검증해, 틀린 이름이 빠진 키(해당 없음)로 읽히지 않게 한다. 한 명령도 모드(동·역·단지·`--details`)마다 매물 모델이 달라 이 검증은 모든 명령의 필드로 보므로, 결과의 매물 모델에 없는 필드를 골랐으면 `emit` 이 `missing_fields_note` 로 `notes` 에 이 명령의 매물 필드를 알린다. 매물 목록을 내는 새 명령도 이 옵션을 단다.

### 값이 없을 때

| 상태 | 표현 | 구현 |
| --- | --- | --- |
| 해당 없음 (그 거래·조회에 원래 없는 항목) | **키를 뺀다** | `Listing.not_applicable_fields()` + `@model_serializer` |
| 모름 (해당은 되지만 소스가 알려 주지 않음) | `null` | 필드 기본값 `None` |
| 알려 줬는데 비어 있음 | `[]` | 빈 리스트 |

- 해당 없음 예: 월세의 `price_manwon`, 매매의 `deposit_manwon`·`rent_manwon`, 연세의 `rent_manwon`, 연세가 아닌 거래의
  `yearly_rent_manwon` (`NOT_APPLICABLE_PRICE_FIELDS`), 중심점 없는 조회와 상세의 `distance_km`.
- service 에서 "모름"과 "없음"을 섞지 않는다. 소스가 옵션 목록을 주지 않았으면 `options=None`,
  줬는데 비었으면 `options=[]`.
- 매물 유형 `property_type` 도 소스가 유형을 주지 않으면 `null`(모름)이다 (`str | None`, 기본값 없음). 당근의 `salesTypeV3` 가 null 인 매물이 그 예다. 유형 글자로 매물을 가르는 코드(`startswith` 등)는 `None` 을 먼저 처리한다.
- 소스 고유 필드가 있는 상세 모델은 `not_applicable_fields()` 를 넓혀 같은 방식으로 키를 뺀다
  (예: `DaangnListingDetail` 은 상가가 아닌 매물의 권리금, 직거래의 중개보수, 단지 없는 매물의 단지 필드).

### 금액·단위

- 금액 필드는 전부 **만원**이고 이름이 `_manwon` 으로 끝난다.
- 금액(가격·보증금·월세·관리비·할인·중개보수·시세·평균·변동액 등 돈인 값)은 반올림·버림·올림 없이 **원 단위까지** 낸다.
  만원 필드는 소수로 원까지 남긴다 (375,700원 → `37.57`, 2,500원 → `0.25`). 원 단위 원본은 `won_to_manwon`(`core/listing.py`)으로
  바꾼다. 만원 소수 넷째 자리가 1원이라 1원 아래만 반올림해 부동소수점 찌꺼기를 지운다. jibsa 가 계산하는 평균·변동액도 같다.
  - 사이트 웹 화면이 줄여 보여 줘도(직방 목록 카드의 관리비는 0.1만원 아래를 버린다) jibsa 는 실제 금액을 낸다. 돈은 10원 단위라도
    틀린 숫자를 사실처럼 보여 주면 안 된다. 웹과 같은 금액을 더 자세히 쓰는 것이라 사이트가 보여 주는 사실과 어긋나지 않으며,
    소스 개발 가이드의 "웹과 다른 점" 에 그 차이를 적는다.
  - 금액을 글자(라벨·안내 문구)로 쓸 때도 `:g`(유효숫자 6자리라 12345.6789 → `12345.7`)·`:.1f`·`round`·`floor` 를 쓰지 않고 `format_manwon` 을 쓴다
    (37.57 → `'37.57'`, 3.0 → `'3'`).
  - 돈이 아닌 값은 줄여도 된다: 거리(`distance_km` 는 소수 둘째 자리)·면적·평·비율.
- 면적은 `area_m2` + `area_pyeong`.
- 날짜 칸은 끝말이 꼴을 정한다 ([칸 이름 규칙](#칸-이름-규칙)): `_date` 는 한국 날짜 `YYYY-MM-DD` 한 꼴이고, `_month` 는 `YYYY-MM`, `_year` 는 숫자이고, 시각까지 있는 값만 `_at` 이다. 소스가 준 꼴(`20100706`·`2018.04.27`·`1991년 6월 5일`, 시각이 붙은 일시)은
  `normalize_date` 로 이 꼴로 바꾼다 (UTC 는 한국 날짜로 바꾸고 시각은 버린다).
  - 소스가 값 없음으로 준 것(없음·빈 글자·`-`)은 안내 없이 `null` 이다.
  - 값이 있는데 날짜로 읽지 못하면(연월만 `201005`, 문장, 달력에 없는 날 `2026-02-30`) 받은 글자를 내지 않고 `null` 로 낸 뒤
    `notes` 의 `[참고]` 로 어느 칸을 못 읽었는지와 원래 글자를 알린다: `[참고] 네이버가 준 사용승인일을 읽지 못했습니다 ('201005'). url 의 매물 화면에서 확인하세요`.
    읽기는 `iso_date`(못 읽으면 None)로 한다. `normalize_date` 는 못 읽으면 원래 글자를 돌려주므로 출력 칸에 바로 쓰지 않는다.
  - 항목이 여럿인 목록(매물·실거래 등)은 항목마다 안내를 붙이지 않고 칸별로 모아 한 줄로 알린다 (못 읽은 수와 원래 글자 예).
  - 연월을 내기로 한 칸(실거래 월 등)과 날짜에 글자를 붙이는 칸(입주일 `move_in` 의 `2026-12-01 이내`)은 그 칸의 규칙을 따른다.
  - 이 규칙은 2026-11-24 에 세웠다 (사용자 결정). 지금 따르는 곳은 네이버 `listing` 의 `registered_date`·`approved_date`(`_readable_date`)과
    입주일뿐이고, 다른 날짜 칸은 못 읽으면 안내 없이 `null`(`iso_date`)이거나 받은 글자 그대로(`normalize_date`)다. 날짜 칸을 새로
    만들거나 고칠 때 이 규칙으로 맞춘다. 목록에서 모아 알리는 공용 함수는 아직 없어 처음 맞추는 사람이 `core/` 에 만든다. 사용자
    문서(`docs/common.md` 공통 필드)는 지금 동작대로 '못 읽으면 받은 글자 그대로나 `null` 일 수 있다' 고 알리고, 모든 날짜 칸이
    맞춘 뒤 이 규칙(`null` 과 `[참고]`)으로 바꾼다.
- 층(`floor`)은 `normalize_floor` 로 표기를 맞춘다 (지하 `지하1`, 반지하, 저·중·고 → 저층·중층·고층). `Listing` 출력에는 `floor` 바로 뒤에 숫자 `floor_number` 가 붙는다 (지하는 음수, 몇 층인지 모르면 `null`). 매물 유형에 층 칸이 없어 `floor` 가 해당 없음(키 없음)이면 `floor_number` 도 없다. 실거래 행(`trades`)과 단지 요약의 최저·최고 거래 같은 거래 하나의 층도 같은 꼴이라 `floor`(글자) 뒤에 `floor_number` 가 붙는다 (`core.listing.with_floor_number`).
- 주소의 시·도는 정식 명칭(`서울특별시`, `강원특별자치도`)으로 맞춘다. `Listing.address` 는 검증기가
  `normalize_address` 를 거치므로 provider 가 따로 부르지 않아도 된다. 단지 정보처럼 `Listing` 밖의 주소는 직접 부른다.

### 거래 유형

- `trade_type` 은 `매매`·`전세`·`월세`·`단기임대`·`연세` 다섯이다 (`TradeType`). 연세는 당근(제주)만 주고, 네 소스가 함께 쓰는 넷은 `SHARED_TRADE_TYPES` 다. 지원 거래 유형·기본값·가격 조건에 따른 거래 유형 추론은 명령별 CLI 선언과 사용자 문서를 따른다. 아파트·실거래·단기임대 서비스처럼 일부 유형만 지원하거나 기본 매매인 명령도 있다.
- 단기임대를 월세로 내보내지 않는다. 보증금이 월세 한두 달치라 싼 월세로 읽힌다. 소스 표기: 네이버 `B3`,
  당근 `SHORT`, 직방은 요약의 `sales_type: 월세` + `contract: 단기` (거래 유형 필터 값은 `단기`).
- 연세(당근 `YEAR`)도 월세로 내보내지 않는다. 1년치를 한 번에 내는 금액이라 월세로 읽으면 열두 배로 셈한다. `yearly_rent_manwon`
  에 1년치 그대로 두고(월로 나눈 값은 당근 웹에도 없다) `rent_manwon` 은 해당 없음으로 키를 뺀다. `yearly_rent_manwon` 은 연세가 아닌
  거래와 다른 소스에서 늘 키가 없다 (`NOT_APPLICABLE_PRICE_FIELDS`).

### 거래 상태

- `status` 는 `판매중`·`예약중` 둘이다. 예약 상태를 알려 주는 소스(지금은 당근)만 채우고, 그 밖의 소스는 해당 없음이라
  키를 뺀다. 예약중은 계약이 깨질 수 있어 원 사이트처럼 내보낸다 (만료 매물이 아니다. 아래 표).

### 방 구조

- `room_type` 은 실제 방 구조만 쓴다. 소스 카테고리 이름으로 추측하지 않고, 알 수 없으면 `null`(모름)이다.
  소스별로 방 구조를 정하는 방법은 각 provider 가이드에 있다.

### 내보내지 않는 정보

jibsa 는 **찾기까지만** 한다. 원 사이트를 대신하게 되는 정보는 모델에 넣지 않는다.

- 매물 출력에서는 사진, 본문(매물 설명), 중개사 정보(이름·전화·주소·등록번호), 도로명 주소, 조회수, 원본 응답 통째를 내보내지 않는다. 단지 정보의 구조화된 `road_address`는 제공할 수 있다.
  관심(찜) 수(`favorite_count`)는 조회수가 아니라 매물을 고르는 데 쓰는 사실이라 내보낸다.
- 본문은 일부도 내보내지 않는다. 중개사가 쓴 자유 형식 글이라 전화번호·중개사 이름·사무소명이 섞이는데,
  정규식으로 가리면 빠짐이 생기고 넓히면 매물 설명이 지워진다. 고르는 데 필요한 사실은 구조화 필드로 준다.
- 매물 좌표(`lat`/`lng`)는 거리 계산용으로 모델에 있지만 `Field(exclude=True)`라 출력되지 않는다. 위치 검색의 지역 후보·검색 중심 좌표는 이 금지 대상이 아니다. 단지 좌표는 내보내지 않는다.
- 응답 모델(`api/response/`)에는 이런 필드가 있어도 되지만, `Listing` 으로 옮기지 않는다.

### 만료 매물

결과는 항상 실시간 조회다. 캐시를 두지 않는다. 소스별 거래 가능 조건:

| 소스 | 거래 가능 조건 | 목록 | 상세 |
| --- | --- | --- | --- |
| 직방 | 요약 `status: true`, 상세 `status: "open"`. 상가 `status: "open"`, 단기임대 상세 `status: true` + `checkStatus: COMPLETE`. 아파트 목록·묶음(`catalog`)은 노출 중인 매물만 온다. 아파트 상세(숫자 ID 아파트·`coalition-`)는 상태 필드가 없고 내려간 매물은 404 다 | 제외 | `ListingUnavailableError` (아파트 상세 404 는 `reason: APT_ITEM_NOT_FOUND`, 모르는 거래 유형이면 `UNKNOWN_TRADE_TYPE`). `catalog` 는 묶음에 매물이 없으면(첫 쪽 404) `LISTING_UNAVAILABLE` 에 `catalog_id`·`reason: EMPTY_CATALOG` |
| 네이버 | 응답 `isSuccess: true`, 아는 거래 유형 코드 (`TRADE_NAME_BY_CODE`) | 노출 중인 매물만 온다. 모르는 코드는 제외 | `ListingUnavailableError` (모르는 거래 유형이면 `reason: UNKNOWN_TRADE_TYPE`, 모르는 매물 유형이면 `UNKNOWN_REAL_ESTATE_TYPE`) |
| 당근 | `ON_GOING`(판매중)·`RESERVED`(예약중)이고 `isHide`·`invisibleReason`·`invisibleInfos` 없음 (`is_available`), 아는 거래 조건이 있음. 상세는 비활성 중개소(`bizProfile.status` 가 `ACTIVE` 아님)도 막는다 | 제외. 목록 카드에는 중개소 상태가 없어 비활성 중개소 매물은 당근 웹처럼 목록에 나온다 | `ListingUnavailableError` (상태·사유 포함, 거래 조건이 없으면 `reason: NO_TRADE_INFO`, 비활성 중개소면 `BIZ_PROFILE_INACTIVE`) |
| 다방 | 상세 `status` 가 비공개(0·3·4)가 아니고 `is_contract` 아님, 아는 거래 유형 (`TRADE_BY_SELLING_CODE`) | 목록 칸에 상태가 없어 다방 웹 목록과 같은 매물이 온다. 가격·거래 유형을 읽지 못한 매물은 제외 | `ListingUnavailableError` (비공개면 `status`, 계약 완료면 `status: contract`, 모르는 거래 유형이면 `reason: UNKNOWN_TRADE_TYPE`) |

## 칸 이름 규칙

출력 칸의 이름과 모양은 네 소스가 용어집 하나로 맞춘다 (2026-11-25 사용자 결정). 같은 뜻의 칸은 소스가 달라도 같은 이름이고, 한 이름은 한 뜻만 가진다. **새 칸을 만들거나 고칠 때 이 절을 따른다.** 용어집에 없는 개념은 아래 짜는 순서로 이름을 만들고 이 표에 한 줄 더한다. 옛 이름에서 새 이름으로의 대응은 [옛 이름 → 새 이름 표](../field-renames.md)에 있다 (사용자·에이전트용 문서라 규칙은 여기에만 둔다).

### 이름 짜는 순서

`[재료]_[한정어(시점·기간·계절·지역·출처)]_[대상]_[통계]_[단위]` 순서이고 단위(`_manwon`·`_m2`·`_pyeong`·`_percent`·`_km`·`_m`·`_minutes`·`_years`)는 늘 맨 끝이다. 예: `estimated_price_per_pyeong_manwon`, `summer_manage_cost_manwon`, `presale_price_average_manwon`, `prev_trade_diff_manwon`.
여러 거래에 한 통계면 통계를 부모 이름에 두고 키를 거래로 한다: `asking_ranges`, `asking_averages`, `trade_averages`, `trade_counts`, `estimated_prices`, `listing_counts`.

### 규칙

1. **거래별로 묶는 객체의 키는 용어집의 영어 거래 낱말이다**: `{"sale": …, "jeonse": …, "wolse": …, "short_term": …, "yeonse": …}`. 직방 평형 시세 추이의 탭 묶음만 `"jeonse_wolse"` 키를 쓴다. 매물 `trade_type` 값과 `--trade` 입력은 한국어 그대로라 `sale`=매매, `jeonse`=전세, `wolse`=월세, `short_term`=단기임대, `yeonse`=연세, `jeonse_wolse`=전월세 로 잇는다. 거래가 여럿인 값은 칸 이름에 거래를 넣지 않고(`sale_count`·`jeonse_count` 가 아니라 `trade_counts.sale`) 이 객체로 묶는다. 그 거래의 매물이 없어 해당 없으면 그 거래 키가 없고, 모든 거래가 없으면 `{}`(비어 있음)이다. 값을 모르면 키는 두고 `null`(모름)이다. 거래 값 안의 칸을 모두 모르면 그 거래 값이 `null` 이고, 안쪽만 `null` 인 객체(`{"jeonse": {"deposit_manwon": null}}`)로 내지 않는다. 한 거래 안에서 일부 칸만 모르면 객체를 두고 그 칸만 `null` 이다 (2026-11-25 사용자 결정). 다방 최근 실거래(`latest_trades`)는 다방이 거래가 없는 것과 받지 못한 것을 가르지 않아 `sale`·`jeonse` 키를 늘 두고 둘 다 `null`(모름)로 낸다.
   - 코드의 속성 이름이 곧 출력 키다 (`sale`·`jeonse`·`wolse`·`short_term`·`yeonse`·`jeonse_wolse`). 출력할 때 한국어로 바꾸는 단계는 없다. 한국어 거래 이름(매물 값·`--trade` 입력)에서 출력 키를 만들 때는 `core.listing.TRADE_KEY_BY_NAME`(한국어 이름 → 키) 한 곳을 쓰고, 소스마다 따로 짝을 만들지 않는다.
   - 낱말 기준: 외국에도 있는 거래는 영어 뜻(`sale`·`short_term`), 한국에만 있는 임대 제도는 소리대로(`jeonse`·`wolse`·`yeonse`·`jeonse_wolse`)다 (2026-11-25 사용자 결정).
   - 다방 `price-trend` 의 `trade_ranges.<거래>` 안 기간 키도 jibsa 가 정한 키라 영어다 (`one_year`·`three_years`). 입력 옵션 `--period 1년` 과는 별개다.
   - **한국어 키로 두는 예외 (2026-11-25 사용자 결정).** 사이트가 보내는 이름표를 그대로 키로 쓰는 칸이다: 다방 `neighborhood` 의 `schools`·`amenities`·`transport`·`safety`(예 `{"생활편의시설": {"편의점": 204}}`)와 `ranks[].counts`, 네이버 `listing` 의 `bus_routes`(예 `{"간선": ["146", "341"]}`). 거래 키는 여섯 개로 정해져 있고 영어 낱말도 용어집에 있지만, 이 칸들은 사이트가 그때 보내는 종류 이름을 그대로 키로 써서 어떤 이름이 올지 미리 다 알 수 없다. 영어로 바꾸려면 사이트에 없는 대응 표를 jibsa 가 지어야 하고, 사이트가 새 이름을 더하면 표에 없는 이름이 한국어로 섞이거나 빠진다. 다방 `neighborhood` 의 `schools` 안 `학원` 키는 다방이 이름 없이 따로 주는 칸이라 jibsa 가 붙이는 키지만, 같은 객체의 다른 키(`초등학교` 등)가 다방 이름표라 한 객체 안에서 두 말이 섞이지 않게 한국어로 둔다. 코드에도 같은 이유를 주석으로 남겼다 (`providers/dabang/service/neighborhood.py`, `providers/naver/service/listing.py`).
2. **날짜의 끝말이 꼴을 정한다**: `_date` 는 `YYYY-MM-DD`, `_month` 는 `YYYY-MM`, `_year` 는 숫자, `_at` 은 시각까지 있는 값만, `_period` 는 소스 글자 그대로다 (`"2026년 상반기"`). 소스가 날짜로 읽을 수 없는 글자를 준 값은 [금액·단위](#금액단위)의 날짜 규칙을 따르고, 아직 맞추지 않은 칸은 받은 글자 그대로일 수 있다. 날짜 낱말은 `registered_date`·`approved_date`·`confirmed_date`·`opened_date`·`established_date`·`published_date` 처럼 `_date` 로 쓰고 `_on` 은 쓰지 않는다. 기간의 시작·끝은 `start_<단위>`·`end_<단위>`, 기준 시점은 `base_date`·`base_month`·`base_year`·`base_period` 다.
3. **범위는 늘 `<무엇>_range: {"lowest": …, "highest": …}` 객체이고**, 거래가 여럿이면 `<무엇>_ranges: {거래: {lowest, highest}}` 다. 금액 범위의 두 끝 안은 매물 금액 칸 이름을 쓴다 (매매 `price_manwon`, 전세 `deposit_manwon`, 월세·단기임대 `deposit_manwon`+`rent_manwon` 짝). 숫자 하나짜리 범위(동 층수 등)는 `{"lowest": 5, "highest": 35}` 다. `min`·`max` 는 입력 옵션·조건 모델(`*Conditions`)에만 남는다. 기관 시세의 하위·일반·상위 띠는 범위가 아니라 `low_manwon`·`mid_manwon`(또는 `average_manwon`)·`high_manwon` 이다. 월세·단기임대의 두 끝은 월세 최저·최고가 아니라 보증금 순으로 첫 매물과 끝 매물의 짝이라 `lowest` 의 월세가 더 클 수 있다.
4. **실거래 낱말은 `trade` 다**: 목록 `trades`, 계약일 `trade_date`, 수 `trade_count`·`trade_counts`, 평균 `trade_averages`, 범위 `trade_range(s)`, 가장 최근 한 건 `latest_trades`. `transaction`·`contract_date`·`deal`(`deal_type` 말고)은 칸 이름에 쓰지 않는다. 호가는 `asking`, 기관·직방 등의 추정 시세는 `estimated`(출처는 `provider` 칸)를 재료로 쓴다.
5. **값의 규격도 맞춘다**: 퍼센트는 `_percent` 이고 0~100 이다 (0~1 비율을 칸 이름만 바꿔 내지 않는다). 층은 `floor`(글자)+`floor_number`(숫자)다. 법정동 코드는 늘 10자리 `legal_division_code` 다. 기간 값은 소스가 달라도 같은 표기다 (`1년`·`3년`·`전체`. 직방 `--period` 도 같다. 이는 입력과 `period` 값이고 다방 `trade_ranges` 의 기간 키는 위 규칙 1 대로 영어다). 매물 0건이라 해당 없는 거래는 `null` 이 아니라 키 없음이다.

### 용어집

한 개념에 영어 낱말 하나를 쓰고, 오른쪽 열의 이름은 쓰지 않는다.

| 개념 | 낱말 | 없애는 이름 |
| --- | --- | --- |
| 매매 / 전세 / 월세 / 단기임대 / 연세 / 전월세 (칸 이름·코드 속성) | `sale` / `jeonse` / `wolse` / `short_term` / `yeonse` / `jeonse_wolse` — 외국에도 있는 거래는 영어 뜻, 한국에만 있는 임대 제도는 소리대로 (2026-11-25 사용자 결정). 칸 이름·코드 속성·거래별 묶음 키가 모두 이 낱말이다. 한국어 이름 → 키 짝은 `core.listing.TRADE_KEY_BY_NAME` 한 곳 | `lease`, `monthly`(월세 뜻), `rent`(월세 거래 뜻), `short_lease` |
| 분양 | `presale` (`presale_id`, `presale_price_manwon`, `presale_household_count`) | 다방의 분양 뜻 `sale` (`sale_id` 등). 명령 이름 `sale` 은 그대로 |
| 매물 | `listing` (`listing_count`, `listing_counts`) | `article` |
| 실거래 | `trade` (결정 4) | `transaction`, `contract_date`, `deal` |
| 중개거래·직거래 | `deal_type` ('중개거래'·'직거래') | `category`, `trade_category`, `direct` |
| 거래 유형 / 거래 탭 묶음 | `trade_type` / `trade_tab` | 값이 거래 유형인 `trade` |
| 매매가 / 보증금·전세금 / 월세액 / 연세액 | `price` / `deposit` / `rent` / `yearly_rent` | 전세금을 `price_manwon` 에 담는 것 |
| 관리비 / 권리금 / 중개보수 | `manage_cost` / `key_money` / `broker_fee` | `maintenance_fee`, `agent_fee` |
| 평당가 | `price_per_pyeong_manwon` | `manwon_per_pyeong`, `per_pyeong_manwon`, `sale_per_pyeong_manwon` |
| 공시가격 / 전세 환산가 | `public_price` / `converted_price` | |
| 호가 / 시세(추정·기관) / 실거래 (재료, 집계 값에만 붙임) | `asking` / `estimated` (출처는 `provider` 칸) / `trade` | `market_price`, `kb_`, `offer_price`(분양가 뜻이면 `presale_price`) |
| 평균 / 변동(시점 간) / 차이(다른 기준과) / 갭(매매−전세) | `average` / `change` / `<기준>_diff` / `gap` | |
| 가장 최근 한 건 / 최근 기간 / 직전 | `latest` / `recent` / `prev` | `previous` |
| 전세가율 | `jeonse_ratio_percent` | `jeonse_ratio`(0~1), `jeonse_rate_percent`, `lease_rate_percent` |
| 퍼센트 | `<개념>_percent` (0~100), 객체 자체가 비율이면 `percent` | `_pct`, `_rate`, `_rate_percent`, 0~1 값 |
| N:1 배수 (경쟁률) | `<개념>_ratio` | `competition_rate` |
| 용적률·건폐율 | `floor_area_ratio_percent` / `building_coverage_ratio_percent` | 단위 없는 `floor_area_ratio` |
| 전용 / 공급 / 계약 면적 | `area` / `supply_area` / `contract_area` + `_m2`·`_pyeong` | `exclusive_area_*`, `exclusive_m2`, `supply_m2`, `contract_m2` |
| 평형 / 평형 ID / 평형 이름 | `pyeong` / `pyeong_id`(목록 `pyeong_ids`, 대표 `representative_pyeong_id`) / `pyeong_name` | `pyeong_number`, `number`, `space_seq`, 평형 객체의 `id` |
| 층(그 매물·거래) / 건물 층수 / 지하 층수 | `floor`(글자)+`floor_number` / `building_floor` / `basement_floor` | |
| 단지 안 동 층수의 최소·최대 | `building_floor_range: {lowest, highest}` | `max_floor`, `min_floor`, `lowest_top_floor`, `highest_top_floor`, `lowest_floor`, `highest_floor` |
| 세대수 / 동 수 / 주차 대수 / 세대당 주차 | `household_count` / `dong_count` / `parking_count` / `parking_per_household` | `households`, `buildings`, `building_count`, `total_parking_count` |
| 준공 / 사용승인 / 연식 | `completed_*` / `approved_*` / `age_years` | `built_year`, `years`(연차) |
| 단지 유형 / 매물 유형 / 건축물 용도 | `complex_type` / `property_type` / `residence_type` | 단지 유형의 `property_type`·`type`·`building_type`(다방) |
| 시공사 / 난방 / 연료 / 현관 | `construction_company` / `heating` / `heating_fuel` / `entrance` | `builder`, `fuel`, `entrance_type` |
| ID | `<대상>_id`, 목록 `_ids` (매물 자기 행만 `id`) | `complex_number`, `redevelopment_number`, 자기 행 `id`(매물 밖) |
| 공공 코드 | `<대상>_code` (`school_code`), 법정동은 늘 10자리 `legal_division_code` | `local_code`, `code`, `parent_code` |
| 이름 | 행이 그 대상이면 `name`, 다른 대상을 가리키면 `<대상>_name` | |
| 시·도 / 시·군·구 / 읍·면·동 / 건물 동 | `sido` / `sigungu` / `dong` / `building_dong` | `name1~3`, `state`, `district`, `city`(지역 단계 뜻) |
| 지역 단계 순위 / 평균 | `<단계>_rank` / `<단계>_average` | `national`·`state`·`district`(순위 int), `city_average`, `district_average` |
| 지번 주소 / 도로명 주소 | `address` / `road_address` | `jibun_address`, `region_address` |
| 거리 / 반경 | 검색 중심에서 결과까지·검색 반경·지도 범위는 `_km`, 시설·단지 사이와 사이트가 정한 시설 반경은 `_m` | |
| 도보 시간 / 탑승 시간 / 수단이 섞인 시간 | `walk_minutes` / `subway_minutes` / `travel_minutes` | `walking_minutes`, `walk_to_station_minutes`, 조건의 `subway_minutes`(도보 상한) |
| 역 / 노선 | `station`(`stations`, `nearby_stations`) / `line`·`lines` | `subways`, `nearby_subways` |
| 외부 페이지 주소 | 원 사이트만 `url`, 다른 페이지는 `<무엇>_url` | 공시 페이지의 `url`, `homepage` |
| 기간 시작·끝 / 기간 길이 | `start_<단위>` / `end_<단위>` / `<명사>_<단위>`(`span_months`) | `since`, `from_*`/`to_*`, `start`/`end`, 단위 없는 `years`·`months`·`weeks` int |
| 기준일 | `base_date` / `base_month` / `base_year` / `base_period` | `as_of`, `survey_date`, `kb_survey_date`, `stats_date`, `stats_year`, `stats_period` |
| 달 / 해 (객체 자체가 그 시점) | `month` / `year` | `year_month` |
| 수 / 키별 수 / 결과 총수·반환 수 | `<명사>_count` / `<명사>_counts` / `total`·`returned` (껍데기에만) | 껍데기 밖 합계 `total`, int 인 `*_transactions` |
| 찜 수 / 조회 수 / 조회한 사람 수 | `favorite_count` / `view_count` / `viewer_count` | `zzim_count`, `watch_count` |
| 중개사 수 | `realtor_count` | 직방 아파트 목록의 `listing_count`(중개사 수 뜻) |
| 불리언 | 접두어 없이 (`cancelled`·`duplex`), 있음은 `has_<명사>` | `is_` (`is_new_high`, `is_price_range`) |
| 상태 / 단계 | `status` / `step`·`current_step` | 분양 상태 `state` |
| 순위 | `rank`(int), `<기준>_rank`, 순위 객체 `ranking`, 순위 목록 `rankings` | 객체인 `rank` |
| 위치 검색 껍데기 | 검색어 `query`, 지역 후보 `regions` | `keyword`, 지역만 담은 `results` |
| 시계열 점 목록 | 달 `months`(점 안 `month`), 주 `weeks` | `points`, `weekly` |

## 개수 상한

`--limit`의 최대값은 CLI 정책이며 서버의 요청당 최대 개수와 구분한다.

- 매물 검색의 `--limit` 은 조회 할당량이다. 실제로 받은 원본 수로 세고, 받은 뒤 중복·거래 불가·조건 불일치로 뺀 만큼 다시 채우지 않는다.
- 요청보다 적게 받으면 남은 몫을 다음 페이지·지도 칸·단지에서 받을 수 있다. 다음 페이지가 없거나 커서가 진행하지 않거나 요청 횟수 상한에 닿으면 중단한다.
- `returned`는 실제 반환 수이며 요청한 `limit`과 같다는 보장이 없다. 집계 범위·일부 조회·제외 사유는 `notes`로 설명한다.
- 단지·지역 후보, 실거래, 통근처럼 결과 상한과 원본 조회 상한·페이지·역별 예산이 따로 있는 명령도 있다.
- 더 남았을 때 더 보는 법(`--limit` 을 늘리거나 좁히라는 말, 이미 최대값이면 `--limit 의 최대값은 N입니다`)은 `core/listing.py` 의 `more_hint` 로 만든다. 좁히라고 권할 것은 그 명령에 있는 옵션만 기본값 없이 넘기고, 반경 검색은 '지역' 대신 '반경', 단지 하나처럼 좁힐 범위가 없으면 조건만 넘긴다. 좁힐 옵션을 이미 다 골라 권할 것이 없으면 `narrow` 에 None 을 넘겨 `--limit` 만 말한다 (최대값보다 작으면 `더 보려면 --limit 을 늘리세요`, 이미 최대값이면 `--limit 의 최대값은 N입니다` 로 끝낸다). '~을 좁히세요' 꼴에 맞지 않는 안내(더 구체적인 이름으로 찾기, 정렬 바꾸기, 기간 줄이기, 최대 몇 건까지 받는지 밝히기)는 직접 쓰되, 그때도 `--limit` 이 최대값이면 늘리라고 하지 않는다.

조회 방식별 예산과 한 소스에만 있는 예외는 그 소스의 provider 가이드(`docs/development/providers/`)에, 명령별 기본값·최대값은
사용자 문서의 해당 명령 절에 적는다. 상한을 올리면 요청 수가 늘 수 있으므로 요청 제한 정책과 함께 검토한다.
