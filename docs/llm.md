# jibsa LLM 사용 가이드

셸로 `jibsa` 를 불러 집을 찾는 LLM 에이전트용 요약이다. `jibsa guide` 가 이 문서를 그대로 출력한다. 이 문서 하나로 시작하고, 옵션 세부는 `jibsa <소스> <명령> --help`, 더 깊은 설명은 `jibsa guide <소스> <명령>` 으로 그 명령 절만 골라 읽는다 (사용 문서 전체는 이 문서의 10배가 넘는다).

## 꼭 지킬 규칙

- 결과는 stdout 에 JSON 하나, 에러는 stderr 에 `{"error": {"code", "message", "hint", ...}}`. exit 0 성공, 1 실행 에러, 2 입력 오류, 130 중단.
- 금액은 소스와 상관없이 전부 **만원**(`*_manwon`), 면적은 `area_m2`(기본 전용면적)·`area_pyeong`.
- 값이 없을 때: **키 없음** = 그 거래에 해당 없음, **`null`** = 모름 (0·없음이 아니다), **`[]`** = 알려 줬는데 비어 있음. 관리비가 `null` 이면 월세와 더하지 말고 `listing` 상세를 본다.
- `notes` 는 꼭 읽는다. 검색 범위가 바뀌었는지, 일부만 돌려줬는지, 지역이 모호한지, 거래 유형을 좁혔는지, 뺀 매물이 있는지를 알려 준다. 안내할 게 없으면 키가 없다.
- `--limit` 은 들여다볼 개수다. 중복·거래 불가로 뺀 만큼 다시 채우지 않아 `returned` 가 더 적을 수 있다. 처음에는 작게 잡는다 (요청과 출력 토큰이 모두 준다).
- 한 번에 매물 50건 이하로 본다. 목록 매물은 1건에 JSON 약 450자라 100건이면 출력이 4만 자를 넘어, 셸 출력을 잘라 보여 주는 에이전트는 뒤쪽 매물을 못 본다. 더 필요하면 `--limit` 을 키우기보다 가격·면적·거래 유형이나 더 좁은 지역으로 나눠 찾는다. `search commute` 는 역마다 `--limit` 건(최대 10곳)이라 역당 5건 안팎으로 시작한다.
- 사진·매물 설명 본문·중개사 연락처·매물 좌표는 주지 않는다. 확인·문의·계약은 결과의 `url` 로 사용자에게 안내한다.
- ID 는 받은 그대로 같은 소스 명령에 넣는다. 소스끼리 ID 는 통하지 않고, 접두사(`apt-`, `officetel-`, `store-`, `stay-`, `coalition-`)를 떼지 않는다. 같은 집이 여러 소스에 올라와도 합쳐 주지 않는다.
- 명령은 하나씩 차례로 부른다. 요청 간격은 모든 jibsa 프로세스가 함께 지켜서 동시에 불러도 빨라지지 않는다. 네이버가 가장 엄격하다 (분당 30회, 차단되면 15분).
- `--verbose` 는 쓰지 않는다 (stderr 에 로그가 섞인다).

## 무엇을 하려면

| 하려는 일 | 명령 |
| --- | --- |
| 원룸·투룸·빌라·오피스텔 | `zigbang search listings room <동·역>` · `daangn search listings <동·역>` · `naver search listings <동·역> -t 원룸,빌라,오피스텔` |
| 아파트 매물 | `zigbang search listings apt <동·구·역>` · `naver search listings <동> -t 아파트` · `daangn search listings <동> -t 아파트` |
| 단지 하나 안 매물 | 단지 ID 를 찾은 뒤 `<소스> search listings --complex <ID>` (네이버는 단지 이름도 된다) |
| 상가·사무실 | `zigbang search listings store <동·역>` |
| 주 단위 단기임대 | `zigbang search listings stay <지역> --check-in YYYY-MM-DD --check-out YYYY-MM-DD` |
| 회사 통근 기준으로 찾기 | `daangn search commute <회사 역·장소> --max-minutes 30` |
| 매물 하나 상세 | `<소스> listing <id>` |
| 단지 찾기 | `zigbang search locations <이름>` · `daangn search locations <이름>` · `naver complex <이름>` · 지역 안 목록은 `naver search complexes <지역>` · `daangn search complexes <동·구>` |
| 단지 정보 | `<소스> complex <ID>` (네이버는 이름도 된다) |
| 실거래가 | `zigbang real-price apt-…` · `naver real-price <단지 번호> --pyeong <평형 번호>` · `daangn real-price <단지 ID>` (단지 없는 건물은 `--item <매물 ID>`) |
| 동·구 실거래·신고가 | `daangn region-real-price <동·구>` (`--new-high`) |
| 시세·가격 흐름 | `naver market-price <단지>` (기관 시세) · `naver trend <동·구>` (아파트 주간 추이) · `daangn price-trend <단지 ID>` (월별 실거래 평균) |
| 학교 | `naver school <school_code>` (`complex`·`listing` 의 `schools[]` 에서) · `daangn school <학교 이름>` (배정 단지 목록) |
| 재개발 | `naver search redevelopment <지역>` → `naver redevelopment <구역 번호>` → `naver search listings --redevelopment <구역 번호>` |
| 단지 비교 | `daangn compare <ID> <ID> …` (최대 5곳) · `daangn nearby-complexes <ID>` |
| 동네 고르기 | `daangn good-neighborhoods --lifestyle …` · `daangn region-reviews <동>` · `daangn developments <장소>` · `daangn preschools <장소>` · `daangn trending-complexes <동>` · `daangn popular-listings <동>` |
| 구 안의 동 이름 목록 | `naver regions <시·도 또는 시·군·구>` |
| 요청 제한 상태 | `jibsa limits` (네트워크 요청 없음) |
| 이 가이드 다시 보기 | `jibsa guide` (네트워크 요청 없음) |

## 자주 쓰는 흐름

```text
매물 찾기   search listings … ─▶ listing <id>
단지 고르기 search locations / search complexes / complex <이름> ─▶ complex <ID> ─▶ search listings --complex <ID> ─▶ listing <id>
실거래      complex <ID> ─▶ real-price
```

평형을 고르는 값은 소스마다 다르다: 직방 `pyeongs[].id` → `--pyeong`, 네이버 `pyeongs[].number` → `--pyeong` (둘 다 평수가 아니라 평형 ID), 당근 `pyeongs[].area_group` → `--area`.

## 위치 입력

- 동 이름은 그 동 안을 찾는다 (직방 `room`·`store`·네이버는 동 경계, 당근은 동 매물 피드). 역·장소 이름, `--lat/--lng`, `--radius` 는 반경 검색이고 기본 1km다.
- 최대 반경: 직방 `apt` 2km, 네이버 3km, 직방 `room`·`store`·`stay`·당근 5km.
- 같은 이름의 동·구가 여러 곳이면 세 소스 모두 고르지 않고 `REGION_AMBIGUOUS` 로 후보(`candidates`)를 알린다. 구 이름을 앞에 붙여 (`강남구 신사동`) 다시 찾는다. 직방은 전체 주소(`서울특별시 강남구 신사동`)로는 못 찾는다. 당근은 `--city` 로도 좁힌다 (`광주시` 는 경기도 광주시, 옛 광주광역시는 `전남광주`나 구 이름). 같은 이름의 역은 첫 역으로 찾고 `notes` 로 알린다.
- `성수동` 처럼 `○가` 로 나뉜 동은 세 소스 모두 1가·2가를 합쳐 찾고 `--limit` 을 동끼리 나눠 쓴다.
- 동 이름은 법정동(`역삼동`)으로 준다. 행정동(`역삼1동`)은 직방·당근이 `REGION_NOT_FOUND` 로 법정동 이름을 힌트에 알려 주고, 네이버는 행정동 중심 반경으로만 찾는다.
- 좌표는 `--lat`·`--lng` 를 함께, 한국 안만 받는다.

## 소스마다 다른 점

### '원룸' 의 뜻

- 직방: 방 하나짜리. 원룸형 오피스텔도 함께 나온다 (`property_type: "오피스텔"`). 빌라 목록에는 투룸 이상만 있다.
- 네이버: `-t 원룸` 은 건물 분류라 방이 여럿인 매물도 섞인다. 방 하나만 원하면 `--room 원룸` 을 함께 준다.
- 당근: 작성자가 고른 카테고리라 방 1개 오피스텔이 빠질 수 있다 → `-t 원룸,오피스텔`. `-t 투룸` 은 투룸 **이상**이다.
- 네이버·당근 목록의 `room_type` 은 `null`(모름)이다. 방 수는 `listing` 상세에서 본다.

### 직방

- 매물 검색은 유형별 하위 명령(`room`·`apt`·`store`·`stay`)이고, 단지 매물만 `search listings --complex <ID>` 로 하위 명령 없이 부른다.
- 단지 ID 는 `apt-…`(아파트)·`officetel-…`(오피스텔 건물). `real-price` 는 `apt-…` 만 받는다.
- `apt` 에 동·구 이름만 주면 그 동·구 전체(거리 없음), 역·좌표·`--radius` 면 반경이다.
- 아파트 목록은 같은 호를 올린 매물을 묶어 가격이 최솟값일 수 있다 (`is_price_range`, `listing_count`).
- `stay` 는 요금이 주 단위(`weekly_rent_manwon`)라 월세와 바로 비교하지 않는다. 기간 총비용은 `listing stay-… --check-in … --check-out …` 의 `period_cost`. 기간은 7~84일, `--check-out` 은 나가는 날이 아니라 **마지막으로 머무는 날**이다.
- `store` 권리금 `0` 은 무권리, `null` 은 모름이다.
- 상세 `residence_type` 에 `근린생활시설` 이 있으면 전입신고·전세대출이 막힐 수 있고, `다가구` 면 선순위 보증금을 확인하라고 사용자에게 알린다. 목록에는 이 값이 없어 `room` 에 `--details` 를 주면 매물마다 붙는다 (요청이 매물 수만큼 늘어 `--limit` 을 작게).

### 네이버

- 요청 제한이 가장 엄격하다. 꼭 필요한 조회만 한다.
- `search listings` 하나가 지역 검색, `--complex <이름|번호>`, `--redevelopment <구역 번호>` 세 모드다. 단지·재개발 모드는 거래 유형·평형·동·가격·정렬·`--limit` 만 받는다.
- `--limit` 은 기본 30, 최대 120.
- 가격순 정렬은 매매가와 보증금을 섞어 세운다. 가격을 비교할 때는 `--trade` 를 하나만 준다.
- `trend --pyeong-range 30` 은 30~40평 범위다 (평형 번호가 아니다).
- 매매 매물 상세에는 세금·중개보수 추정치가 붙는다. `loan_manwon` 이 양수면 융자가 있는 매물이다.

### 당근

- 동 이름 검색은 최근 게시 순이고 주변 동 매물이 섞여 온다. 매물마다 `in_regions` 가 `false` 면 주변 동 매물이다 (빼지 않는다). `--expand` 로 주변 동까지 보려면 `--limit` 도 늘린다 (기본 20은 첫 동에서 다 쓴다).
- 목록에는 관리비·등록일·번지가 없다 (`null`). 후보를 고를 때 필요하면 `--details` 로 매물마다 상세를 붙인다 (요청이 매물 수만큼 늘어 `--limit` 을 작게).
- 역 이름은 역 주변 매물이고 매물마다 역까지 도보 분(`walk_minutes`)이 붙는다.
- 거래 조건이 여럿인 매물은 `trade_type` 과 `other_trades` 로 온다. 같은 조건의 상세는 `listing <id> --trade <trade_type>`.
- `search complexes` 의 가격 조건은 과거 실거래 기준이다. 그 가격의 현재 매물은 `search listings --complex` 로 확인한다.
- `search commute` 의 `--max-minutes` 는 총 통근 시간이 아니라 역 사이 지하철 시간 상한(당근은 60분까지)이고, `--limit` 은 역마다 적용된다 (가까운 역 최대 10곳).
- `watch_count` 는 관심 수다 (조회수가 아니다). `good-neighborhoods` 의 `dong` 은 행정동이라 매물은 법정동 이름으로 찾는다.
- 이름으로 위치를 찾을 때 직방·네이버에도 요청해, 에러의 `source` 가 `zigbang`·`naver` 일 수 있다.

## 실거래·시세 읽기

- 호가(현재 매물 가격), 실거래, 기관 시세는 서로 다르다. 섞어 말하지 않는다.
- `cancelled: true` 는 해제된 거래라 평균·시세에서 뺀다. `renewal: true` 는 갱신 계약이라 새 계약보다 낮을 수 있다.
- 학교 배정은 참고용이다. 최종 확인은 교육청 학구도 안내로 하라고 알린다.

## 에러가 나면

| code | 할 일 |
| --- | --- |
| `INVALID_ARGUMENT` | `hint` 에 이 명령에서 쓰는 옵션이 있으면 그대로 고친다 (다른 소스의 옵션 이름·값을 옮겨 쓴 경우). 없으면 `message` 를 읽고 `--help` 로 고친다. 같은 명령을 그대로 다시 부르지 않는다 |
| `REGION_NOT_FOUND` | 더 구체적인 이름(구 + 동)이나 좌표로 다시 찾는다 |
| `REGION_AMBIGUOUS` | `candidates` 에서 골라 시·구를 붙이거나 `--city` 를 준다 |
| `REGION_NOT_SUPPORTED` | 다른 소스로 찾는다 |
| `NOT_FOUND` | ID 를 이전 결과에서 그대로 복사했는지 확인한다. `hint` 에 고를 값이 있기도 하다 |
| `LISTING_UNAVAILABLE` | 이미 거래가 끝났거나 내려간 매물이다. 후보에서 빼고 계속한다 |
| `RATE_LIMITED` | `retry_after_seconds` 만큼 기다리거나 다른 소스를 쓴다. 바로 다시 부르지 않는다 |
| `NETWORK_ERROR` | 잠시 뒤 한 번만 다시 부른다 |
| `UPSTREAM_ERROR`, `PARSE_ERROR` | 사이트가 바뀌었을 수 있다. 다른 소스를 쓰고, 사용자에게 jibsa 업데이트(`uv tool upgrade jibsa`)를 권한다 |
| `INTERNAL_ERROR` | 에러 JSON 을 `jibsa --version` 출력과 함께 그대로 사용자에게 보여 준다 |

## 더 읽을 곳

필요한 절만 읽는다. 설치본에도 들어 있어 `jibsa guide <소스> [절 이름]` 으로 네트워크 없이 읽는다 (설치한 버전과 같다). 예: `jibsa guide daangn 'search listings'`, `jibsa guide zigbang listing`, `jibsa guide common`.

- [공통 사용 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md) — 출력 규칙, 공통 매물 필드, 요청 제한 정책
- [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md) · [네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md) · [당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md) — 명령별 옵션 표·반환값·주의사항, 소스별 반환 필드
