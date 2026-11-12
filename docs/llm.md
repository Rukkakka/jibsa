# jibsa LLM 사용 가이드

셸로 `jibsa` 를 불러 집을 찾는 LLM 에이전트용 요약이다 (`jibsa guide` 가 그대로 출력한다). 옵션은 `jibsa <소스> <명령> --help`, 더 깊은 설명은 `jibsa guide <소스> <명령>` 으로 그 절만 읽는다.

## 꼭 지킬 규칙

- 사용자가 소스(사이트)를 정하지 않았으면 매물 검색은 **직방·네이버·당근·다방 네 곳을 모두** 부른다. 소스마다 올라온 매물이 달라 한두 곳만 보면 빠진다. 같은 조건은 [소스마다 다른 점](#소스마다-다른-점) 표대로 소스마다 같은 뜻의 옵션으로 옮긴다. 답에는 찾은 소스와, 찾지 못한 소스와 그 이유(에러·0건·그 조건이 없음)를 적는다.
- 결과는 stdout 에 JSON 하나, 에러는 stderr 에 `{"error": {"code", "message", "hint", ...}}`. exit 0 성공, 1 실행 에러, 2 입력 오류. 터미널(PTY)이라 JSON 이 들여쓰기로 나오면 명령 끝에 `--compact` 를 붙인다.
- 금액은 소스와 상관없이 **만원**(`*_manwon`)이다. 사용자에게는 억·만 원으로 옮겨 쓴다 (만원 숫자를 그대로 옮겨 적으면 자리를 틀리기 쉽다): `1000` = 1,000만 원, `10000` = 1억 원, `119700` = 11억 9,700만 원, `210000` = 21억 원. 면적은 `area_m2`(전용)·`area_pyeong`.
- **키 없음** = 그 거래에 해당 없음 (`--fields` 로 고르지 않은 필드는 빼고), **`null`** = 모름 (0·없음이 아니다), **`[]`** = 알려 줬는데 비어 있음. 관리비가 `null` 이면 월세와 더하지 말고 `listing` 상세를 본다.
- `notes` 는 꼭 읽는다. 앞의 종류: `[일부]` 더 받을 게 있다, `[범위]` 찾은 범위가 요청과 다르다, `[제외]` 뺀 매물이 있다, `[모호]` 같은 이름 중 하나를 골랐다, `[거래]` 거래 유형을 좁혔다, `[실패]` 덤 조회 실패 또는 대체 경로로 찾음(사용자에게 알린다), `[참고]` 그 밖.
- `--limit` 은 들여다볼 개수라 뺀 매물만큼 `returned` 가 적을 수 있다. 처음에는 작게 잡고, 한 번에 매물 50건 이하로 본다 (100건이면 4만 자가 넘어 잘린다). `search commute` 는 역마다 `--limit` 건(최대 10역)이라 역당 5건 이하로 시작한다.
- 매물 목록의 `has_more` 가 `true` 이고 `next` 가 있으면 **같은 명령·지역·조건에 `--next <next>` 만 붙여** 이어 받는다 (`--limit`·`--fields` 는 바꿔도 된다, 하루 동안 쓴다). `--limit` 을 늘려 다시 부르면 앞 매물을 또 받는다. `next` 가 없으면 `notes` 대로 `--limit` 을 늘리거나(최대값 전까지) 가격·면적·거래 유형이나 더 좁은 지역으로 나눠 찾는다.
- 후보를 훑을 때는 `--fields id,title,deposit_manwon,rent_manwon,manage_cost_manwon,area_m2,floor,address,url` 처럼 필요한 필드만 받는다 (출력이 절반쯤 준다). 사용자에게 줄 링크인 `url` 은 빼지 않고, 받은 글자 그대로 옮긴다 (ID 로 주소를 만들거나 경로를 고치지 않는다). `--fields` 는 매물 목록 명령(`search listings …`·`search commute`·`popular-listings`)에만 있고 상세 `listing` 에는 없다.
- 층은 `floor`(`"3"`·`"반지하"`·`"중층"`)와 숫자 `floor_number`(지하는 음수, 모르면 `null`).
- 사진·매물 설명·중개사 연락처·매물 좌표는 없다. 확인·문의·계약은 `url` 로 안내한다.
- ID 는 받은 그대로 같은 소스 명령에 넣는다. 소스끼리 통하지 않고, 접두사(`apt-`, `officetel-`, `store-`, `stay-`, `coalition-`)를 떼지 않는다. 여러 소스의 같은 집을 합쳐 주지 않는다. 같은 집인지 가리려고 `listing` 을 여러 번 부르지 않고, 가격·면적·층이 같으면 '같은 집일 수 있다' 고만 알린다 (사용자가 상세 비교를 원하면 그 후보만 `listing` 으로 본다).
- 명령은 동시에(병렬 호출·`&`) 부르지 않는다. 모든 jibsa 프로세스가 요청 간격을 함께 지켜 빨라지지 않는다. 후보 여러 개의 `listing` 은 셸 호출 한 번에 `;` 로 잇는다. 요청 간격은 네이버 1초, 당근·다방 0.5초, 직방 0.2초다 (분당 상한은 직방 120, 나머지 60).
- `--verbose` 는 쓰지 않는다 (stderr 에 로그가 섞인다).

## 무엇을 하려면

| 하려는 일 | 명령 |
| --- | --- |
| 유형을 정하지 않은 집 | `zigbang search listings room`·`apt` · `naver search listings <동·역>` (`-t` 없이 주거용 전체) · `daangn search listings <동> -t 아파트,오피스텔,원룸,투룸,주택` · `dabang search listings room`·`villa`·`officetel`·`apt` |
| 원룸·투룸·빌라·오피스텔 | `zigbang search listings room <동·역>` · `daangn search listings <동>` (역은 `--station <역>`, 대학은 `--university <대학>`) · `naver search listings <동·역> -t 원룸,빌라,오피스텔` · `dabang search listings room <동·역>` (빌라 `villa`, 오피스텔 `officetel`) |
| 아파트 매물 | `zigbang search listings apt <동·구·역>` · `naver search listings <동> -t 아파트` · `daangn search listings <동> -t 아파트` · `dabang search listings apt <동·역>` |
| 단지 하나 안 매물 | `<소스> search listings --complex <단지 ID>` (네이버는 이름도 된다) |
| 상가·사무실 | `zigbang search listings store <동·역>` · `naver search listings <동·역> -t 상가,사무실` · `daangn search listings <동> -t 상가,사무실` (단지 안 상가도 `--complex <ID> -t 상가` 처럼 종류를 줘야 온다. 다방은 상가가 없다) |
| 단기임대 | 주 단위는 `zigbang search listings stay <지역> --check-in … --check-out …` · 월 단위 매물은 직방 `search listings room`·네이버·당근 `search listings` 에 `--trade 단기임대` (다방은 `search listings room`·`villa`·`officetel`·`apt` 에 `--condition 단기임대`) |
| 회사 통근 기준 | `daangn search commute --station <회사 역> --max-minutes 30` (통근 시간 조건은 당근만 있다. 다른 소스는 결과의 역 이름으로 그 역 주변을 찾는다) |
| 매물 하나 상세 | `<소스> listing <id>` |
| 단지 찾기 | `zigbang search locations <이름>` · `daangn search locations <이름>` · `dabang search locations <이름>` · `naver complex <이름>` · 지역 안 목록 `naver search complexes <지역>` · `daangn search complexes <동·구>` · `dabang search complexes <동·역>` |
| 단지 정보 | `<소스> complex <ID>` (네이버는 이름도 된다) |
| 실거래가 | `zigbang real-price apt-…` · `naver real-price <단지 번호> --pyeong <평형 번호>` (평형 하나씩만 주어 단지 전체는 직방·당근으로 보고, 네이버는 평형을 정해 볼 때 쓴다. 전용면적이 같은 평형끼리 거래가 겹친다) · `daangn real-price <단지 ID>` (단지 없는 건물은 `--item <매물 ID>`) · `dabang real-price <단지 ID>` (단지 없는 매물은 `--listing <매물 ID>`, 그 동의 같은 건물 유형 거래) · 동·구 단위 `daangn region-real-price <동·구>` (신고가는 `--new-high`, 웹처럼 최근 공개일 하루치라 비면 `--previous-days`) |
| 시세·가격 흐름 | `naver market-price <단지> --pyeong <평형 번호>` (기관 시세) · `naver trend <동·구>` (아파트 주간) · `daangn price-trend <단지 ID>` (평형 하나, 기본 대표 평형) · `dabang price-trend <단지 ID> --pyeong <space_seq>` (월별 실거래 평균) |
| 학교 | `naver school <school_code>` (`complex`·`listing` 의 `schools[]` 에서) · `daangn school <학교 이름\|school_code>` (배정 단지, 여러 곳이면 `candidates` 의 `school_code` 로) · `dabang school <school_code> --level <level>` (`dabang complex` 의 `schools[]` 에서, 중학교 특목고·자사고 진학률, 고등학교 대학 진학률) · 단지 근처 어린이집·유치원 `daangn preschools <단지 ID>` (지역·역 이름으로는 찾지 않는다) |
| 재개발 | `naver search redevelopment <지역>` → `naver redevelopment <구역 번호>` → `naver search listings --redevelopment <구역 번호>` |
| 단지 비교 | `daangn compare <ID> <ID> …` (최대 10곳, 비슷한 크기 평형끼리) · `daangn nearby-complexes <ID>` |
| 동네 고르기 | `daangn good-neighborhoods --lifestyle …` · `region-reviews <동>` · `trending-complexes [시·도·구]` (조회 급상승, 빼면 전국) · `popular-listings <동>` (모두 `daangn`) · 동 요약 숫자와 순위 `dabang neighborhood <동>` · `dabang popular-listings <동>` |
| 역 둘레 시세·주변 | 역 둘레 평균 매물가(호가) `dabang station-prices <역>` · 매물·단지 둘레 역·버스·시설 `dabang nearby <ID>` |
| 분양·청약 | `dabang search sales <동·구>` → `dabang sale <sale_id>` (일정·평형별 분양가) · 날짜별 전국 일정 `dabang sale-schedule --region 서울` |
| 동네·단지 순위 | 구·시도·전국 안 `dabang region-ranking <범위> --by 평균가` (전세가율·갭가격은 `--unit 단지`, 신고가 단지는 `--by 최고가증감 --unit 단지`) · 학군·생활 동 순위 `--by 과학고진학률`·`대학교진학률`·`학원수 --kind 입시`·`인구증감`·`의료시설` 등 · 전국 `dabang trending-complexes` (조회) · `dabang trade-rankings` (거래) |
| 구 안의 동 이름 | `naver regions <시·도 또는 시·군·구>` |

## 위치 입력

- 동 이름은 그 동 안을 찾는다. 역·장소 이름, `--lat`·`--lng`(함께, 한국 안), `--radius` 는 반경 검색이고 기본 1km다 (매물 검색 최대: 직방 `apt` 2km, 네이버 3km, 다방·직방 나머지 5km). 다만 역 이름은 다방이 다방이 정한 역 반경(강남역 750m)으로 찾아 범위가 다르다.
- 당근은 반경이 없고 당근 웹 화면별로 받는다: 동·구 이름, 역 `--station`, 대학 `--university`, 도로명 주소 `--address`, 좌표 `--lat/--lng`. 역·대학은 당근 주변 목록(역은 도보 `walk_minutes`), 구·좌표·주소는 웹 지도 화면 범위(기본 줌: 구 12 약 12.8×13.6km, 좌표·주소 15 약 1.6×1.7km, `--zoom` 으로 바꿈)를 최근 순으로 준다. 주소는 도로명 주소(`'테헤란로 152'`)만 되고 후보가 여럿이면 `REGION_AMBIGUOUS` 의 `candidates` 그대로 다시 준다. 건물·리 이름은 받지 않는다. 후보는 `daangn search locations <이름>` 이 칸별로 준다.
- 동 이름은 법정동(`역삼동`)으로 준다. 행정동(`역삼1동`)은 직방·당근·다방이 `REGION_NOT_FOUND` 힌트로 법정동을 알려 주고, 네이버는 행정동 중심 반경으로 찾는다.
- 같은 이름의 동·구가 여러 곳이면 `REGION_AMBIGUOUS` 와 `candidates` 가 온다. 구 이름을 앞에 붙인다 (`강남구 신사동`. 구 이름까지 겹치면 `hint` 의 예처럼 시·도도 붙인다: `서울 중구 태평로2가`. 직방은 시·도까지 붙인 전체 주소는 못 찾는다. 당근 `광주시` 는 경기도, 옛 광주광역시는 `전남광주`나 구 이름). 같은 이름의 역은 첫 역으로 찾고 `notes` 로 알린다 (당근은 노선을 붙여 고른다: `--station '서울5호선 양평역'`).
- 매물 검색은 `성수동` 처럼 `○가` 로 나뉜 동을 1가·2가 합쳐 찾고 `--limit` 을 나눠 쓴다 (동 수보다 작으면 뒤쪽 동은 `notes` 로 알리고 건너뛴다). 당근은 합치지 않고 `REGION_AMBIGUOUS` 로 `성수동1가`·`성수동2가` 를 고르게 한다. 네이버 재개발 구역 검색처럼 첫 동만 찾는 명령은 `notes` 로 알리니 나머지 `○가` 동을 따로 찾는다.

## 소스마다 다른 점

다른 소스의 옵션을 옮겨 쓰면 에러 `hint` 가 이 명령의 옵션이나 이 소스에 그 조건이 없다는 것을 알려 준다.

| 조건 | 직방 `room` | 네이버 | 당근 | 다방 |
| --- | --- | --- | --- | --- |
| 방 2개 이상 | `--room 투룸,쓰리룸,포룸이상` | `--room 투룸,쓰리룸,포룸이상` | `--room-count 2개,3개,4개이상` | `villa`·`officetel`·`apt` 에 `--room 투룸,쓰리룸,포룸이상`, `room` 에 `--room 투룸` (`room` 은 투룸까지) |
| 원룸 구조 | `--room 오픈형원룸` | `--one-room-shape 오픈형` | `--structure 오픈형` | `--condition 분리형` 또는 `복층` |
| 엘리베이터·주차 | `--condition 엘리베이터,주차` | `--facility 엘리베이터,주차` | `--option 엘리베이터,주차가능` | `--condition 엘리베이터,주차` |
| 반려동물 | `--condition 반려동물` | 없음 | `--option 반려동물가능` | 없음 |
| 즉시 입주 | `--condition 즉시입주` | `--move-in 바로입주` | `--move-in-now` | 없음 |
| 욕실 수 | `--bathroom 1` | `--bathroom 1개` | 없음 | 없음 |
| 면적 | `--area-min` (전용 ㎡) | `--area-min` (전용 ㎡, `--area-basis 공급` 이면 공급) | `--area-min` (전용 ㎡) | `--area-pyeong-min` (평, 정수. 아파트는 공급 평) |
| 아파트 공급 ○평대 (예: 30평대) | `apt --supply-area-min 99 --supply-area-max 132` | `-t 아파트 --area-basis 공급 --area-min 99 --area-max 132` | 공급 조건이 없어 전용 ㎡ 로 옮긴다: 공급 ㎡ × 0.75 쯤 (전용 59㎡형 ≈ 공급 24~26평, 84㎡형 ≈ 32~35평이라 20평대에 84㎡ 는 넣지 않는다). 답에 기준을 적는다 | `apt --area-pyeong-min 30 --area-pyeong-max 39` |
| 반지하·지하 빼기 | `--floor 지상,옥탑방` (`지상` 만이면 옥탑방도 빠진다) | `--floor 1층,저층,중층,고층,탑층` | `--floor 1층,2~5층,6~9층,10층이상` | `--floor 1층,2층이상,옥탑` |

평형을 고르는 값도 소스마다 다르다: 직방 `pyeongs[].id` → `--pyeong`, 네이버 `pyeongs[].number` → `--pyeong`, 다방 `pyeongs[].space_seq` → `--pyeong` (셋 다 평수가 아니라 평형 ID), 당근 아파트형 단지는 `pyeongs[].pyeong`(공급 평) → `--pyeong`, 그 밖은 `pyeongs[].area_group`(전용 ㎡) → `--area`.

### '원룸' 의 뜻

- 직방: 방 하나짜리라 원룸형 오피스텔도 나온다 (`property_type: "오피스텔"`). 빌라는 투룸 이상만 있다. 방 1개짜리 아파트는 `search listings apt --supply-area-max 50` 으로 찾는다.
- 네이버: `-t 원룸` 은 건물 분류라 방이 여럿인 매물도 섞인다. 방 하나만이면 `--room 원룸` 을 함께 준다. 목록의 `room_type` 은 `null` 이다.
- 당근: 작성자가 고른 분류라 방 1개 오피스텔·아파트·주택은 빠지고 방 2개 매물이 섞일 수 있다 (오피스텔도 보려면 `-t 원룸,오피스텔`). `-t 투룸` 은 투룸 **이상**이다. 목록의 `room_type` 은 원룸에만 붙고 방 2개 매물에도 붙을 수 있다.
- 다방: `room` 은 다방 '원룸·투룸' 목록이라 방 1~2개짜리 오피스텔·아파트도 나온다 (`property_type`). `villa` 는 방 하나짜리 빌라도 나오고 `property_type` 이 늘 `빌라` 다.
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
- `trend --pyeong-range 30` 은 30~40평 범위다 (평형 번호가 아니다). 최근 4주쯤의 `trade_count` 는 신고가 덜 모여 적으니 거래가 줄었다고 읽지 않는다.
- 매매 상세에는 세금·중개보수 추정치가 붙고, `loan_manwon` 이 양수면 융자가 있다.

### 당근

- 동 이름 검색은 그 동 매물만 최근 게시 순이다. 구·좌표 검색은 지도 화면 사각형이라 이웃 동·구 매물도 섞인다. `status: 예약중` 은 계약이 깨질 수 있어 나오는 매물이라 사용자에게 예약중이라고 알린다.
- `--trade` 없이 금액 조건만 주면 당근 웹처럼 다른 거래 유형도 나온다 (`--rent-max` 만 주면 전세·매매도). 한 거래 유형만 볼 때는 `--trade` 를 함께 준다.
- 제주에는 연세(`trade_type: 연세`)가 많다. 1년치 월세를 한 번에 내는 거래라 `yearly_rent_manwon` 은 월세가 아니다 (`1400` = 1년에 1,400만 원, `rent_manwon` 키는 없다). 연세만 찾으려면 `--trade 연세 --yearly-rent-max <만원>` (`--rent-*` 는 받지 않는다). 제주에서 월세를 찾는 사용자에게는 연세 매물도 있다고 알린다.
- 목록에는 관리비·등록일·번지가 없다 (`null`). 필요하면 `--details` 로 상세를 붙인다 (매물마다 요청 1회 더).
- `--station` 검색은 매물마다 역까지 도보 `walk_minutes` 를, `search commute` 는 매물마다 `walk_to_station_minutes`, 역 묶음마다 편도 `one_way_minutes`(지하철 + 회사 도보)를 준다. 문 앞까지는 둘을 더한다. `--max-minutes` 는 총 통근 시간이 아니라 역 사이 지하철 시간 상한이다 (60분까지).
- 거래 조건이 여럿인 매물은 `trade_type` 과 `other_trades` 로 온다. 그 조건의 상세는 `listing <id> --trade <trade_type>`.
- `search complexes` 의 가격 조건은 과거 실거래 기준이다 (그 가격의 현재 매물은 `search listings --complex`). `good-neighborhoods` 의 `dong` 은 행정동이라 매물은 법정동 이름으로 찾는다.
- `watch_count` 는 관심 수다 (조회수가 아니다).

### 다방

- 매물 검색은 유형별 하위 명령(`room`·`villa`·`officetel`·`apt`)이다. 결과는 **다방 목록 순**이라 거리순이 아니다 (역·좌표 검색은 `distance_km` 로 고른다).
- 동·역·대학 이름을 받고 구·시 이름은 못 찾는다 (`REGION_NOT_SUPPORTED`). 역은 다방이 정한 역 반경(강남역 750m)이다. `apt` 는 동 검색이 없어 동 경계를 덮는 사각형에서 그 동 매물만 남겨 `returned` 가 적을 수 있다.
- 아파트 매물 목록(`apt`·단지 매물·인기 매물, `room` 에 섞인 아파트)은 다방이 공급면적만 줘서 `area_m2` 가 `null` 이고 `supply_area_m2` 가 공급면적이다. 다른 소스의 전용면적과 견주려면 `listing` 의 `area_m2` 를 본다. `--area-pyeong-min` 도 아파트는 공급 평이다.
- 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는 표시라 `trade_type: 월세` 에 `short_lease: true` 다. 보증금이 월세 한두 달치(95/95)면 단기 계약 가격일 수 있다. 단기임대 가능 매물만은 `--condition 단기임대`.
- 목록의 `address` 는 찾은 동의 매물만 시·구까지다 (역·좌표 검색은 동 이름만). `listing` 은 `id` 대신 다방 화면의 매물번호(`listing_number`)도 받는다.
- `real-price --listing` 은 그 건물이 아니라 그 동의 같은 건물 유형 거래다 (`basis`). `area_m2` 가 비슷한 거래만 견준다.
- `region-ranking` 의 값은 항목에 맞는 키에만 있다 (평균가 `value_manwon`, 거래량·학원수 `count`, 전세가율·진학률 `percent`, 시세증감 `change_percent`). 시세증감·최고가증감의 `change_manwon` 은 오른 금액이지 현재가가 아니다 (새 최고가 = `prev_price_manwon + change_manwon`). `search sales` 는 다방이 지도 사각형만 받아 역·좌표 둘레는 반경을 덮는 사각형 전체다.
- `school` 은 `--level` 이 학교 코드와 맞아야 한다 (`dabang complex` 의 `schools[].level` 을 그대로). 틀리면 다방이 서버 고장과 같은 500 을 줘서 `UPSTREAM_ERROR`(`status` 500)이니 코드·단계부터 다시 본다. 다방 학교 코드는 네이버 `school` 코드와 다르다.
- `station-prices` 는 실거래가가 아니라 지금 올라온 원룸·투룸 매물의 평균(다방 '평균 매물가')이다. `neighborhood` 의 `rank` 는 1 이 가장 많거나 높고, 동 하나만 받는다 (`성수동` 은 `성수동1가` 처럼 고른다).

## 실거래·시세 읽기

- 호가(현재 매물 가격), 실거래, 기관 시세는 서로 다르다. 섞어 말하지 않는다.
- `cancelled: true` 는 해제된 거래라 평균·시세에서 뺀다. 네이버·직방 전월세의 `renewal: true` 는 갱신 계약이라 새 계약보다 낮을 수 있다. 당근은 `renewal` 대신 `contract_type: 재계약` 과 `renewal_right: true`(갱신요구권 사용)로 나눠 주고, 둘 다 새 계약보다 낮을 수 있다.
- 학교 배정은 참고용이니 최종 확인은 교육청 학구도 안내로 하라고 알린다.

## 에러가 나면

먼저 `hint` 를 따른다. 아래 표가 다시 부르라고 한 경우가 아니면 같은 명령을 그대로 다시 부르지 않는다.

| code | 할 일 |
| --- | --- |
| `INVALID_ARGUMENT` | `hint` 의 옵션대로 고친다. 없으면 `message` 와 `--help` 를 본다 |
| `REGION_NOT_FOUND` · `REGION_AMBIGUOUS` | `hint` 대로 다시 찾는다. 같은 이름이 여러 곳이면 이름 앞에 구·시·도를 붙이고(`'강남구 신사동'`·`'서울 중구'`), `REGION_AMBIGUOUS` 는 `candidates` 에서 고른다. 좌표(`--lat`·`--lng`)는 그 명령이 받을 때만 쓴다 |
| `REGION_NOT_SUPPORTED` · `UPSTREAM_ERROR` · `PARSE_ERROR` | 다른 소스를 쓴다. 뒤의 둘은 사용자에게 `uv tool upgrade jibsa` 를 권한다. 단 `hint` 가 사이트 장애(첫 화면 서버 오류)를 가리키면 업데이트를 권하지 않고 잠시 뒤 한 번만 다시 부르고, `blocked: true`(사이트가 접속을 막음)면 업데이트를 권하지 않고 다른 소스만 쓴다 |
| `NOT_FOUND` | 단지·학교·평형 ID 나 이름을 같은 소스의 결과에서 그대로 옮겼는지 본다 |
| `LISTING_UNAVAILABLE` | 매물 ID 를 같은 소스의 결과에서 옮겼는지 본다. 맞으면 내려간 매물이라 후보에서 뺀다 |
| `RATE_LIMITED` | `retry_after_seconds` 만큼 기다리거나 다른 소스를 쓴다 (`jibsa limits` 로 상태 확인) |
| `NETWORK_ERROR` | 잠시 뒤 한 번만 다시 부른다. `hint` 가 프록시·인증서 설정을 가리키면 다시 부르지 말고 사용자에게 알린다 |
| `BROWSER_UNAVAILABLE` | 모든 소스가 같이 실패하니 다른 소스로 돌지 않는다. `hint` 의 명령(`jibsa install-browser`, 리눅스 라이브러리는 `sudo …`)을 사용자에게 알린다 |
| `INTERNAL_ERROR` | 에러 JSON 을 `jibsa --version` 과 함께 사용자에게 그대로 보여 준다 |

## 더 읽을 곳

`jibsa guide <소스>` 는 절 목록, `jibsa guide <소스> <절 이름>` 은 그 절만 쓴다 (예: `jibsa guide daangn search listings`, `jibsa guide common 에러 대응`). 같은 문서: [공통](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md) · [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md) · [네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md) · [당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md) · [다방](https://github.com/Rukkakka/jibsa/blob/main/docs/dabang.md)
