# 공통 CLI 사용 규칙

[설치](https://github.com/Rukkakka/jibsa/blob/main/README.md) · [LLM 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/llm.md) · [당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md) · [네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md) · [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md)

## 출력 규칙

- 결과는 stdout 에 JSON. 터미널이면 들여쓰기, 파이프면 한 줄 (`--pretty` / `--compact` 로 강제)
- 소수점 아래가 없는 숫자는 정수로 쓴다 (`1000.0` 이 아니라 `1000`). 같은 필드도 값에 따라 `1000` 과 `24.2` 처럼 섞여 나온다
- 매물 목록 명령(직방 `room`·`apt`·`store`·`stay`·`--complex`, 네이버 `search listings`, 당근 `search listings`·`search commute`·`popular-listings`)은 `--fields id,deposit_manwon,rent_manwon` 처럼 매물마다 낼 필드만 고를 수 있다. 결과의 매물 키 이름을 쉼표로 주고, `id` 와 `notes` 가 가리키는 필드(당근 `in_regions`, 네이버 중복 묶음의 `realtor_count`·`*_range_manwon`)는 늘 나온다. 고르지 않은 필드는 키가 없으니 이때는 키 없음을 해당 없음으로 읽지 않는다. 결과 머리(`total`·`notes` 등)는 그대로이고, 어느 명령에도 없는 필드 이름은 요청 전에 `INVALID_ARGUMENT` 로 막는다. 다른 명령에만 있는 필드(당근 역 검색의 `walk_minutes` 를 `search commute` 에)는 결과에서 빠지고 `notes` 에 이 명령의 매물 필드를 알린다
- 매물 필드에 값이 없을 때는 의미에 따라 다르게 나타낸다

  | 상태 | 표현 | 예 |
  |---|---|---|
  | 해당 없음 (그 거래·조회에 원래 없는 항목) | **키를 뺀다** | 월세의 `price_manwon`, 매매의 `deposit_manwon`·`rent_manwon`, 상세 조회의 `distance_km` |
  | 모름 (해당은 되지만 소스가 알려 주지 않음) | **`null`** | 당근 목록의 `manage_cost_manwon`·투룸 이상 `room_type`, 네이버 목록의 `room_type`, 네이버 상세에서 교통 정보가 없는 매물의 `nearby_subways`·`bus_routes`, 단지가 없는 매물의 `schools` |
  | 알려 줬는데 비어 있음 | `[]` | 옵션이 하나도 없는 매물의 `options` |
- 지역이 모호하거나(같은 이름이 여러 곳) 너무 넓으면(시·도·구 단위), 또는 가격 조건으로 거래 유형을 좁혔으면 검색 결과 맨 앞에 `notes` 로 안내한다. 안내할 게 없으면 키가 없다
- 결과에 1억(`10000` 만원) 이상 금액이 있으면 `notes` 끝에 그 결과의 값으로 억 환산 예시를 붙인다 (`[참고] 금액은 만원이다: 440000 = 44억 원, 119700 = 11억 9,700만 원`). 사용자에게 억으로 옮길 때 이 예시대로 자리를 맞춘다
- `notes` 의 안내는 앞에 종류가 붙는다: `[일부]` 더 받을 결과가 있다, `[범위]` 찾은 범위가 요청과 다르다(동 경계·반경 밖·주변 동·다른 지역), `[제외]` 받은 것 중 뺀 매물이 있다, `[모호]` 같은 이름이 여러 곳이라 하나를 골랐다, `[거래]` 거래 유형을 짐작해 좁혔다, `[실패]` 덤 조회가 실패했거나 대체 경로로 찾았다, `[참고]` 그 밖에 읽을 때 알 것
- 매물 목록은 `has_more`(같은 조건으로 더 받을 매물이 있는지)를 준다. 이어 받을 수 있는 검색은 `next` 도 준다. 같은 명령·지역·조건에 `--next <next>` 를 붙이면 받은 매물 다음부터 이어 받는다 (`--limit`·`--details`·`--fields` 는 바꿀 수 있다). `next` 는 10자 번호이고, 어디까지 받았는지는 상태 폴더(`~/.cache/jibsa/next/`, `JIBSA_STATE_DIR` 로 변경)에 하루 동안 남는다. 하루가 지났거나 다른 컴퓨터에서 받은 번호, 지역·조건이 다른 검색에 준 번호는 `INVALID_ARGUMENT` 로 막고, 조건이 다르면 `message` 에 어느 옵션이 다른지 적는다. `has_more` 가 `true` 인데 `next` 가 없으면 이어 받을 수 없는 검색이라 `--limit`·조건으로 찾는다
- 가격 조건은 그 금액이 있는 거래에만 걸린다: 월세(`--rent-*`)는 월세·단기임대, 매매가(`--price-*`)는 매매, 보증금(`--deposit-*`)은 전세·월세·단기임대. `--trade` 를 줬는데 가격 조건이 걸릴 거래 유형이 하나도 없으면(전세 + `--rent-max`, 매매 + `--deposit-max`) 서버가 조건을 무시해 조건 없는 결과가 나오므로 `INVALID_ARGUMENT` 로 막는다. 일부만 겹치면(`--trade 전세,월세 --rent-max 50`) 해당 거래에만 걸고 나머지는 그대로 둔다
- `--lat/--lng` 가 한국 밖이거나 둘 중 하나만 주면 `INVALID_ARGUMENT` 로 막는다
- 인자 하나에 공백과 옵션이 함께 들면(`'--complex 111515 --pyeong 8,9'`, `'대치동 --city 강남구'`) 셸이 옵션을 나누지 않은 것이라 요청 전에 `INVALID_ARGUMENT` 로 막는다. 셸 변수에 옵션을 담아 넘길 때 생기며, zsh 는 따옴표 없는 `$VAR` 도 나누지 않는다. 옵션을 명령에 바로 쓰거나 zsh 는 `${=VAR}` 로 넘긴다. `guide` 의 절 이름(`'search listings --complex'`)은 막지 않는다
- 숫자 범위(`--area-min/max` 등)의 하한이 상한보다 크거나, 숫자 옵션(범위·`--radius`)에 `inf`·`nan` 을 주면 모든 소스가 요청 전에 `INVALID_ARGUMENT` 로 막는다
- 에러는 **항상** stderr 에 `{"error": {"code", "message", "hint", ...}}` JSON 으로 쓴다. 사용법 오류(없는 옵션·잘못된 값·인자 누락)도 마찬가지
- **금액은 소스와 무관하게 전부 만원 단위**로 정규화 (`price_manwon`, `deposit_manwon`, `rent_manwon`, `manage_cost_manwon`). 네이버 원본은 원 단위라 환산한다

| exit code | 뜻 | 출력 |
|---|---|---|
| 0 | 성공 (`--help`, 인자 없이 실행 포함) | stdout 에 결과 JSON (도움말·`jibsa guide`·`jibsa --version` 은 텍스트) |
| 1 | 실행 중 에러 (`LISTING_UNAVAILABLE`, `NOT_FOUND`, `RATE_LIMITED`, `REGION_NOT_FOUND`, `REGION_AMBIGUOUS`, `REGION_NOT_SUPPORTED`, `UPSTREAM_ERROR`, `NETWORK_ERROR`, `PARSE_ERROR`, `INTERNAL_ERROR`) | stderr 에 에러 JSON |
| 2 | 입력 오류 (`INVALID_ARGUMENT`) | stderr 에 에러 JSON |
| 130 | 인터럽트로 중단 (`INTERRUPTED`, Ctrl+C·SIGINT) | stderr 에 에러 JSON |

## 반환값을 읽을 때

`id`는 해당 소스의 `listing`에 그대로 넘긴다. 금액은 모두 만원, 면적은 기본 전용면적 ㎡다. `notes`는 조회 범위·제한·조건 해석을 설명하므로 결과와 함께 읽는다. `null`을 0이나 “없음”으로 해석하지 않는다. 관리비가 모르면 월세와 합산하지 말고 상세에서 확인한다.

목록은 매물을 고르는 데 필요한 가격·면적·층·주소·거래 유형·거리 등을, 상세는 방·욕실·관리비·입주·주차·옵션 등 구조화 정보를 제공한다. 사진·매물 설명 본문·중개사 연락처·매물 좌표는 제공하지 않는다. 위치 검색의 지역 후보 좌표는 매물 좌표와 다르다. 매물 확인·사진·문의·계약은 `url`의 원 사이트에서 한다.

현재 매물과 실거래가·시세·단지 정보를 구분한다. `cancelled: true`인 실거래는 취소된 거래이므로 시세·평균에서 제외한다. `renewal: true`는 갱신 계약이라 새 계약과 가격 차이가 날 수 있다. 학교 배정은 교육청 자료 기준이므로 실제 배정은 교육청 학구도 안내에서 확인한다. 후기 본문은 제공하지 않으며 후기 수로 내용을 추측하지 않는다.

### 공통 매물 필드

| 필드 | 의미 |
| --- | --- |
| `source`, `id`, `url` | 소스·매물 ID·원 사이트 확인 링크 |
| `trade_type`, `property_type`, `room_type`, `title` | 거래·매물 유형·방 구조·제목 |
| `price_manwon`, `deposit_manwon`, `rent_manwon`, `manage_cost_manwon` | 거래에 해당하는 매매가·보증금·월세·관리비(만원) |
| `area_m2`, `area_pyeong` | 전용면적 ㎡·평 |
| `floor`, `floor_number`, `building_floor` | 해당 층·그 층의 숫자·전체 층수. `floor` 는 `"3"`·`"지하1"`·`"반지하"`·`"저층"`·`"중층"`·`"고층"`·`"옥탑"` 처럼 오고, `floor_number` 는 지상 양수·지하 음수다 (`"지하1"` → `-1`). 반지하·저층처럼 몇 층인지 모르면 `floor_number` 는 `null` |
| `address`, `distance_km` | 지번 주소·검색 중심까지 거리. 주소 상세도와 거리 제공 여부는 조회 모드별로 다름. 반경 안·밖은 출력한 `distance_km`(km, 소수 둘째 자리)로 가르고 `total`·반경 밖 안내도 같은 기준이다. 거리를 모르는 매물(`null`)은 반경 안으로 세지 않는다 |
| `registered_at`, `approved_at` | 등록일·사용승인일 (`YYYY-MM-DD`). 소스가 알려 주지 않으면 `null` |
| 상세 방·시설 | `room_count`, `bathroom_count`, `direction`, `move_in`, `parking`, `elevator`, `options` 등 |
| `move_in`, `parking` | 모든 소스가 같은 꼴이다. 입주 가능일은 `"2026-10-24"`·`"즉시입주"`·`"2026-11 초순"`, 협의할 수 있으면 뒤에 `" (협의 가능)"`. 주차는 `"가능"`·`"불가"`, 대수가 있으면 `"가능 (총 4대)"` 처럼 괄호로 붙는다 |
| 상세 관리비·교통 | `manage_cost_includes`, `nearby_subways` 등. 소스별 추가 필드는 해당 문서 참고 |

입주·주차·역 설명에 작성자가 입력한 문구가 포함될 수 있다. 목록과 상세에서 제공하는 주소·필드는 다르며 상세에 거리처럼 해당하지 않는 키는 없다.

## JSON 응답 예시

아래는 가상 ID·값으로 만든 **필드 발췌 예시**다. 전체 스키마가 아니며 실제 응답의 다른 필드는 생략했다. 숫자 ID·`next` 값은 실제 조회에 사용하지 않는다.

### 매물 목록

```json
{
  "notes": ["[일부] 조건에 맞는 매물 약 40건 중 검색 중심에서 가까운 1건입니다. 이어 보려면 결과의 next 를 --next 로 주세요"],
  "returned": 1,
  "has_more": true,
  "next": "0000000001",
  "listings": [
    {
      "source": "daangn",
      "id": "9000001",
      "trade_type": "월세",
      "deposit_manwon": 1000,
      "rent_manwon": 70,
      "manage_cost_manwon": null,
      "floor": "반지하",
      "floor_number": null,
      "building_floor": "5"
    }
  ]
}
```

관리비 `null`은 0이 아니다. 월세에 해당하지 않는 `price_manwon`은 키가 없다. 다음 매물은 같은 명령에 `--next 0000000001` 을 붙여 받는다.

### 매물 상세

```json
{
  "source": "daangn",
  "id": "9000001",
  "trade_type": "월세",
  "room_count": 1,
  "manage_cost_manwon": 5,
  "options": []
}
```

상세는 목록과 달리 매물 객체 자체를 반환한다. 위의 `options: []`는 알려진 옵션 목록이 비어 있다는 뜻이다.

### 실거래 목록

```json
{
  "complex_id": "9000002",
  "trade_type": "매매",
  "returned": 1,
  "has_more": false,
  "transactions": [
    {
      "trade_date": "2026-09-01",
      "price_manwon": 50000,
      "cancelled": true
    }
  ]
}
```

당근 실거래 형식의 발췌다. `cancelled: true`인 거래는 현재 계약 가능한 매물이 아니며 시세 계산에서 제외한다. 네이버 등 소스별 최상위 필드는 해당 문서를 따른다.

### 에러

```json
{
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "지원하지 않는 옵션 값입니다",
    "hint": "해당 명령의 --help로 허용값을 확인하세요"
  }
}
```

에러는 stderr에 출력한다. 실제 `message`·`hint`는 상황에 따라 달라지며, `source`·`retry_after_seconds` 등 추가 키도 오류 종류에 따라 달라진다.

## 에러 대응

에러의 `code`와 `source`, `hint`를 읽는다. 소스 명령 안에서도 위치 검색에 다른 provider를 사용할 수 있다.

| 코드 | 발생 조건 | 대응 |
| --- | --- | --- |
| `INVALID_ARGUMENT` | 필수 인자 누락, 범위·허용값 위반, 지원하지 않는 옵션 조합 | 해당 명령의 `--help`와 옵션 표 확인 |
| `REGION_NOT_FOUND` | 이름이나 좌표에 해당하는 지역을 찾지 못함 | 구체적인 주소 또는 좌표 사용 |
| `REGION_AMBIGUOUS` | 같은 이름의 지역·주소 후보가 여러 곳 | `candidates`를 확인하고 시·구를 붙임 |
| `REGION_NOT_SUPPORTED` | 소스가 해당 지역을 다루지 않음 | 다른 소스 또는 주변 지역 조회 |
| `NOT_FOUND` | 단지·학교·평형·동 등 조회 대상 없음 | 이전 검색 결과의 ID와 후보 확인 |
| `LISTING_UNAVAILABLE` | 삭제·만료·거래 완료·숨김 등 현재 거래 불가 | 다른 소스에서 받은 ID 면 그 소스의 명령으로 부르고, 아니면 해당 매물 제외 후 다시 검색 |
| `RATE_LIMITED` | 로컬 요청 예산 초과 또는 429 이후 쿨다운 | `retry_after_seconds`가 있으면 해당 시간만큼 대기. 없으면 `hint`와 `jibsa limits` 확인 |
| `NETWORK_ERROR` | 연결·타임아웃 등 전송 실패 | 네트워크 상태 확인 후 재시도 |
| `UPSTREAM_ERROR`, `PARSE_ERROR` | API 거절·응답 구조 변경·파싱 실패 | 힌트 확인, 다른 소스 사용 또는 버전 갱신 |
| `INTERNAL_ERROR` | 처리하지 못한 실행 오류 | 에러 내용을 보존해 원인 확인 |
| `INTERRUPTED` | Ctrl+C 등 호출 중단 | 필요하면 같은 명령을 다시 실행 |

## 요청 제한과 `limits`

모든 jibsa 프로세스가 소스별 상태 파일(`~/.cache/jibsa/ratelimit/<source>.json`, `JIBSA_STATE_DIR` 로 변경)을 공유한다. 그래서 LLM 이 명령을 연달아 실행해도 간격이 지켜진다.

| 소스 | 요청 간격 | 분당 상한 | 429 후 쿨다운 |
|---|---|---|---|
| 직방 | 0.2초 | 120 | 2분 |
| 당근 | 0.5초 | 60 | 5분 |
| 네이버 | 1초 | 30 | 15분 |
| 다방 | 0.5초 | 60 | 5분 |

- 슬롯이 날 때까지 기다리되, 60초 넘게 기다려야 하면 기다리지 않고 `RATE_LIMITED` (`reason: budget`) 를 낸다
- 429 를 받으면 쿨다운 동안 그 소스로 요청을 아예 보내지 않고 `RATE_LIMITED` (`reason: cooldown`, `retry_after_seconds`) 를 낸다. `Retry-After` 가 더 길면 그 값을 따른다
- `jibsa limits` 로 상태를 보고, `jibsa limits --reset naver` 로 초기화한다

```bash
jibsa limits
jibsa limits --compact
jibsa limits --reset daangn
```

`limits`는 네트워크 호출 없이 상태를 확인한다. `--reset`은 `zigbang`, `naver`, `daangn`, `dabang`을 반복 또는 쉼표로 받으며 선택한 소스의 로컬 상태를 초기화한다. 서버 차단을 해제하는 명령은 아니다.

| 반환 필드 | 의미 |
| --- | --- |
| `state_dir` | 상태 파일 디렉터리 |
| `sources[].source` | 소스 이름 |
| `sources[].requests_last_minute` | 최근 60초 요청 슬롯 수 |
| `sources[].cooldown_remaining_seconds` | 남은 쿨다운 시간 |
| `sources[].policy` | 간격·분당 상한·쿨다운·최대 대기·활성화 정책 |

상태 파일 권한·디스크 오류도 stderr 에러 JSON으로 반환한다. 상태 폴더에 쓸 수 없으면(권한, 쓰기를 막은 샌드박스) 모든 소스가 `INTERNAL_ERROR` 로 실패하므로 다른 소스로 돌지 말고 `JIBSA_STATE_DIR` 로 쓸 수 있는 폴더를 지정한다. `--pretty` / `--compact`는 소스별 명령과 `limits`에서 동일하게 사용할 수 있다. 전역 `--verbose`는 진행 로그를 stderr에 추가하므로 에러 JSON만 파싱하는 호출에서는 사용하지 않는다.
