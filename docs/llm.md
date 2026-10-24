# jibsa LLM 사용 가이드

셸로 `jibsa` 를 불러 집을 찾는 LLM 에이전트용 요약이다 (`jibsa guide` 가 그대로 출력한다). 옵션은 `jibsa <소스> <명령> --help`, 더 깊은 설명은 `jibsa guide <소스> <명령>` 으로 그 절만 읽는다.

## 꼭 지킬 규칙

- 결과는 stdout 에 JSON 하나, 에러는 stderr 에 `{"error": {"code", "message", "hint", ...}}`. exit 0 성공, 1 실행 에러, 2 입력 오류. 터미널(PTY)이라 JSON 이 들여쓰기로 나오면 명령 끝에 `--compact` 를 붙인다.
- 금액은 소스와 상관없이 **만원**(`*_manwon`)이다. 사용자에게는 억·만 원으로 옮겨 쓴다 (만원 숫자를 그대로 옮겨 적으면 자리를 틀리기 쉽다): `1000` = 1,000만 원, `10000` = 1억 원, `119700` = 11억 9,700만 원, `210000` = 21억 원. 면적은 `area_m2`(전용)·`area_pyeong`.
- **키 없음** = 그 거래에 해당 없음 (`--fields` 로 고르지 않은 필드는 빼고), **`null`** = 모름 (0·없음이 아니다), **`[]`** = 알려 줬는데 비어 있음. 관리비가 `null` 이면 월세와 더하지 말고 `listing` 상세를 본다.
- `notes` 는 꼭 읽는다. 앞의 종류: `[일부]` 더 받을 게 있다, `[범위]` 찾은 범위가 요청과 다르다, `[제외]` 뺀 매물이 있다, `[모호]` 같은 이름 중 하나를 골랐다, `[거래]` 거래 유형을 좁혔다, `[실패]` 덤 조회 실패(사용자에게 알린다), `[참고]` 그 밖.
- `--limit` 은 들여다볼 개수라 뺀 매물만큼 `returned` 가 적을 수 있다. 처음에는 작게 잡고, 한 번에 매물 50건 이하로 본다 (100건이면 4만 자가 넘어 잘린다). `search commute` 는 역마다 `--limit` 건(최대 10역)이라 역당 5건 이하로 시작한다.
- 매물 목록의 `has_more` 가 `true` 이고 `next` 가 있으면 **같은 명령·지역·조건에 `--next <next>` 만 붙여** 이어 받는다 (`--limit`·`--fields` 는 바꿔도 된다, 하루 동안 쓴다). `--limit` 을 늘려 다시 부르면 앞 매물을 또 받는다. `next` 가 없으면 가격·면적·거래 유형이나 더 좁은 지역으로 나눠 찾는다.
- 후보를 훑을 때는 `--fields id,title,deposit_manwon,rent_manwon,manage_cost_manwon,area_m2,floor,address,url` 처럼 필요한 필드만 받는다 (출력이 절반쯤 준다). 사용자에게 줄 링크인 `url` 은 빼지 않는다. `--fields` 는 매물 목록 명령(`search listings …`·`search commute`·`popular-listings`)에만 있고 상세 `listing` 에는 없다.
- 층은 `floor`(`"3"`·`"반지하"`·`"중층"`)와 숫자 `floor_number`(지하는 음수, 모르면 `null`).
- 사진·매물 설명·중개사 연락처·매물 좌표는 없다. 확인·문의·계약은 `url` 로 안내한다.
- ID 는 받은 그대로 같은 소스 명령에 넣는다. 소스끼리 통하지 않고, 접두사(`apt-`, `officetel-`, `store-`, `stay-`, `coalition-`)를 떼지 않는다. 여러 소스의 같은 집을 합쳐 주지 않는다.
- 명령은 동시에(병렬 호출·`&`) 부르지 않는다. 모든 jibsa 프로세스가 요청 간격을 함께 지켜 빨라지지 않는다. 후보 여러 개의 `listing` 은 셸 호출 한 번에 `;` 로 잇는다. 네이버가 가장 엄격하다 (분당 30회, 차단되면 15분).
- `--verbose` 는 쓰지 않는다 (stderr 에 로그가 섞인다).

## 무엇을 하려면

| 하려는 일 | 명령 |
| --- | --- |
| 원룸·투룸·빌라·오피스텔 | `zigbang search listings room <동·역>` · `daangn search listings <동·역>` · `naver search listings <동·역> -t 원룸,빌라,오피스텔` |
| 아파트 매물 | `zigbang search listings apt <동·구·역>` · `naver search listings <동> -t 아파트` · `daangn search listings <동> -t 아파트` |
| 단지 하나 안 매물 | `<소스> search listings --complex <단지 ID>` (네이버는 이름도 된다) |
| 상가·사무실 / 주 단위 단기임대 | `zigbang search listings store <동·역>` / `zigbang search listings stay <지역> --check-in … --check-out …` |
| 회사 통근 기준 | `daangn search commute <회사 역·장소> --max-minutes 30` |
| 매물 하나 상세 | `<소스> listing <id>` |
| 단지 찾기 | `zigbang search locations <이름>` · `daangn search locations <이름>` · `naver complex <이름>` · 지역 안 목록 `naver search complexes <지역>` · `daangn search complexes <동·구>` |
| 단지 정보 | `<소스> complex <ID>` (네이버는 이름도 된다) |
| 실거래가 | `zigbang real-price apt-…` · `naver real-price <단지 번호> --pyeong <평형 번호>` · `daangn real-price <단지 ID>` (단지 없는 건물은 `--item <매물 ID>`) · 동·구 단위 `daangn region-real-price <동·구>` (신고가는 `--new-high`) |
| 시세·가격 흐름 | `naver market-price <단지>` (기관 시세) · `naver trend <동·구>` (아파트 주간) · `daangn price-trend <단지 ID>` (월별 실거래 평균) |
| 학교 | `naver school <school_code>` (`complex`·`listing` 의 `schools[]` 에서) · `daangn school <학교 이름>` (배정 단지) |
| 재개발 | `naver search redevelopment <지역>` → `naver redevelopment <구역 번호>` → `naver search listings --redevelopment <구역 번호>` |
| 단지 비교 | `daangn compare <ID> <ID> …` (최대 5곳) · `daangn nearby-complexes <ID>` |
| 동네 고르기 | `daangn good-neighborhoods --lifestyle …` · `region-reviews <동>` · `developments <장소>` · `preschools <장소>` · `trending-complexes <동>` · `popular-listings <동>` (모두 `daangn`) |
| 구 안의 동 이름 | `naver regions <시·도 또는 시·군·구>` |

## 위치 입력

- 동 이름은 그 동 안을 찾는다. 역·장소 이름, `--lat`·`--lng`(함께, 한국 안), `--radius` 는 반경 검색이고 기본 1km다 (매물 검색 최대: 직방 `apt` 2km, 네이버 3km, 나머지 5km).
- 동 이름은 법정동(`역삼동`)으로 준다. 행정동(`역삼1동`)은 직방·당근이 `REGION_NOT_FOUND` 힌트로 법정동을 알려 주고, 네이버는 행정동 중심 반경으로 찾는다.
- 같은 이름의 동·구가 여러 곳이면 `REGION_AMBIGUOUS` 와 `candidates` 가 온다. 구 이름을 앞에 붙인다 (`강남구 신사동`, 직방은 시·도까지 붙인 전체 주소는 못 찾는다). 당근은 `--city` 로도 좁힌다 (`광주시` 는 경기도, 옛 광주광역시는 `전남광주`나 구 이름). 같은 이름의 역은 첫 역으로 찾고 `notes` 로 알린다.
- `성수동` 처럼 `○가` 로 나뉜 동은 1가·2가를 합쳐 찾고 `--limit` 을 나눠 쓴다 (동 수보다 작으면 뒤쪽 동은 `notes` 로 알리고 건너뛴다).

## 소스마다 다른 점

다른 소스의 옵션을 옮겨 쓰면 에러 `hint` 가 이 명령의 옵션이나 이 소스에 그 조건이 없다는 것을 알려 준다.

| 조건 | 직방 `room` | 네이버 | 당근 |
| --- | --- | --- | --- |
| 방 개수 | `--room 투룸` | `--room 투룸` | `--room-count 2개` |
| 원룸 구조 | `--room 오픈형원룸` | `--one-room-shape 오픈형` | `--structure 오픈형` |
| 엘리베이터·주차 | `--condition 엘리베이터,주차` | `--facility 엘리베이터,주차` | `--option 엘리베이터,주차가능` |
| 반려동물 | `--condition 반려동물` | 없음 | `--option 반려동물가능` |
| 즉시 입주 | `--condition 즉시입주` | `--move-in 바로입주` | `--move-in-now` |
| 욕실 수 | `--bathroom 1` | `--bathroom 1개` | 없음 |
| 반지하·지하 빼기 | `--floor 지상,옥탑방` (`지상` 만이면 옥탑방도 빠진다) | `--floor 1층,저층,중층,고층,탑층` | `--floor 1층,2~5층,6~9층,10층이상` |

평형을 고르는 값도 소스마다 다르다: 직방 `pyeongs[].id` → `--pyeong`, 네이버 `pyeongs[].number` → `--pyeong` (둘 다 평수가 아니라 평형 ID), 당근 `pyeongs[].area_group` → `--area`.

### '원룸' 의 뜻

- 직방: 방 하나짜리라 원룸형 오피스텔도 나온다 (`property_type: "오피스텔"`). 빌라는 투룸 이상만 있다. 방 1개짜리 아파트는 `search listings apt --supply-area-max 50` 으로 찾는다.
- 네이버: `-t 원룸` 은 건물 분류라 방이 여럿인 매물도 섞인다. 방 하나만이면 `--room 원룸` 을 함께 준다. 목록의 `room_type` 은 `null` 이다.
- 당근: 작성자가 고른 분류라 방 1개 오피스텔·아파트·주택은 빠지고 방 2개 매물이 섞일 수 있다 (오피스텔도 보려면 `-t 원룸,오피스텔`). `-t 투룸` 은 투룸 **이상**이다. 목록의 `room_type` 은 원룸에만 붙고 방 2개 매물에도 붙을 수 있다.
- 방 수는 `listing` 상세의 `room_count` 로 본다. 이 안내는 결과 `notes` 에 다시 붙지 않는다.

### 직방

- 매물 검색은 유형별 하위 명령(`room`·`apt`·`store`·`stay`)이고, 단지 매물만 `search listings --complex <ID>` 다.
- 단지 ID 는 `apt-…`(아파트)·`officetel-…`. `real-price` 는 `apt-…` 만 받는다.
- 아파트 목록은 같은 호의 매물을 묶어 가격이 최솟값일 수 있다 (`is_price_range`, `listing_count`).
- `stay` 요금은 주 단위(`weekly_rent_manwon`)라 월세와 바로 비교하지 않는다. 기간 총비용은 `listing stay-… --check-in … --check-out …` 의 `period_cost` 이고, `--check-out` 은 **마지막으로 머무는 날**이다 (7~84일).
- `store` 권리금 `0` 은 무권리, `null` 은 모름이다.
- 상세 `residence_type` 이 `근린생활시설` 이면 전입신고·전세대출이 막힐 수 있고, `다가구` 면 선순위 보증금을 확인하라고 알린다. 목록에서 보려면 `room` 에 `--details` (매물마다 요청 1회 더).

### 네이버

- `search listings` 는 지역, `--complex <이름|번호>`, `--redevelopment <구역 번호>` 세 모드다. 단지 모드는 거래 유형·평형·동·가격·정렬·`--limit` 만, 재개발 모드는 거래 유형·가격·정렬·`--limit` 만 받는다.
- 가격순 정렬은 매매가와 보증금을 섞어 세운다. 가격을 비교할 때는 `--trade` 를 하나만 준다.
- `trend --pyeong-range 30` 은 30~40평 범위다 (평형 번호가 아니다).
- 매매 상세에는 세금·중개보수 추정치가 붙고, `loan_manwon` 이 양수면 융자가 있다.

### 당근

- 동 이름 검색은 최근 게시 순이고 주변 동 매물이 섞인다 (`in_regions: false`, 빼지 않는다). 여러 동을 찾으면(`--expand`·`○가` 동) 같은 매물이 겹쳐 `returned` 가 꽤 적을 수 있다.
- 목록에는 관리비·등록일·번지가 없다 (`null`). 필요하면 `--details` 로 상세를 붙인다 (매물마다 요청 1회 더).
- 역 이름 검색은 매물마다 역까지 도보 `walk_minutes` 를, `search commute` 는 `walk_to_station_minutes` 와 예상 통근 `commute_minutes` 를 준다. `--max-minutes` 는 총 통근 시간이 아니라 역 사이 지하철 시간 상한이다 (60분까지).
- 거래 조건이 여럿인 매물은 `trade_type` 과 `other_trades` 로 온다. 그 조건의 상세는 `listing <id> --trade <trade_type>`.
- `search complexes` 의 가격 조건은 과거 실거래 기준이다 (그 가격의 현재 매물은 `search listings --complex`). `good-neighborhoods` 의 `dong` 은 행정동이라 매물은 법정동 이름으로 찾는다.
- `watch_count` 는 관심 수다 (조회수가 아니다). 이름으로 위치를 찾을 때 직방·네이버에도 요청해 에러 `source` 가 그쪽일 수 있다.

## 실거래·시세 읽기

- 호가(현재 매물 가격), 실거래, 기관 시세는 서로 다르다. 섞어 말하지 않는다.
- `cancelled: true` 는 해제된 거래라 평균·시세에서 뺀다. `renewal: true` 는 갱신 계약이라 새 계약보다 낮을 수 있다.
- 학교 배정은 참고용이니 최종 확인은 교육청 학구도 안내로 하라고 알린다.

## 에러가 나면

먼저 `hint` 를 따른다. 아래 표가 다시 부르라고 한 경우가 아니면 같은 명령을 그대로 다시 부르지 않는다.

| code | 할 일 |
| --- | --- |
| `INVALID_ARGUMENT` | `hint` 의 옵션대로 고친다. 없으면 `message` 와 `--help` 를 본다 |
| `REGION_NOT_FOUND` · `REGION_AMBIGUOUS` | 구 이름을 붙이거나 좌표·`--city` 로 다시 찾는다 (`REGION_AMBIGUOUS` 는 `candidates` 에서 고른다) |
| `REGION_NOT_SUPPORTED` · `UPSTREAM_ERROR` · `PARSE_ERROR` | 다른 소스를 쓴다. 뒤의 둘은 사용자에게 `uv tool upgrade jibsa` 를 권한다 |
| `NOT_FOUND` | 단지·학교·평형 ID 나 이름을 같은 소스의 결과에서 그대로 옮겼는지 본다 |
| `LISTING_UNAVAILABLE` | 매물 ID 를 같은 소스의 결과에서 옮겼는지 본다. 맞으면 내려간 매물이라 후보에서 뺀다 |
| `RATE_LIMITED` | `retry_after_seconds` 만큼 기다리거나 다른 소스를 쓴다 (`jibsa limits` 로 상태 확인) |
| `NETWORK_ERROR` | 잠시 뒤 한 번만 다시 부른다 |
| `INTERNAL_ERROR` | 에러 JSON 을 `jibsa --version` 과 함께 사용자에게 그대로 보여 준다 |

## 더 읽을 곳

`jibsa guide <소스>` 는 절 목록, `jibsa guide <소스> <절 이름>` 은 그 절만 쓴다 (예: `jibsa guide daangn search listings`, `jibsa guide common 에러 대응`). 같은 문서: [공통](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md) · [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md) · [네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md) · [당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md).
