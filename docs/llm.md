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
- 후보를 훑을 때는 `--fields id,title,deposit_manwon,rent_manwon,manage_cost_manwon,area_m2,floor,address,url` 처럼 필요한 필드만 받는다 (출력이 절반쯤 준다). 사용자에게 줄 링크인 `url` 은 빼지 않고, 받은 글자 그대로 옮긴다 (ID 로 주소를 만들거나 경로를 고치지 않는다). `--fields` 는 매물 목록 명령(`search listings …`·`search commute`·`popular-listings`, 직방 `catalog`)에만 있고 상세 `listing` 에는 없다.
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
| 아파트 매물 | `zigbang search listings apt <동·구>` (역·좌표는 그 위치가 속한 동 목록) · `naver search listings <동> -t 아파트` · `daangn search listings <동> -t 아파트` · `dabang search listings apt <동·역>` |
| 단지 하나 안 매물 | `<소스> search listings --complex <단지 ID>` (네이버는 이름도 된다) |
| 상가·사무실 | `zigbang search listings store <동·역>` · `naver search listings <동·역> -t 상가,사무실` · `daangn search listings <동> -t 상가,사무실` (단지 안 상가도 `--complex <ID> -t 상가` 처럼 종류를 줘야 온다. 다방은 상가가 없다) |
| 단기임대 | 주 단위는 `zigbang search listings stay <지역> --check-in … --check-out …` · 월 단위 매물은 직방 `search listings room`·네이버·당근 `search listings` 에 `--trade 단기임대` (다방은 `search listings room`·`villa`·`officetel`·`apt` 에 `--condition 단기임대`) |
| 회사 통근 기준 | `daangn search commute --station <회사 역> --max-minutes 30` (통근 시간 조건은 당근만 있다. 다른 소스는 결과의 역 이름으로 그 역 주변을 찾는다) |
| 매물 하나 상세 | `<소스> listing <id>` |
| 단지 찾기 | `zigbang search locations <이름>` · 역 주변 아파트 단지 `zigbang search complexes <역>` · `daangn search locations <이름>` · `dabang search locations <이름>` · `naver complex <이름>` · 지역 안 목록 `naver search complexes <지역>` · `daangn search complexes <동·구>` · `dabang search complexes <동·역>` |
| 단지 정보 | `<소스> complex <ID>` (네이버는 이름도 된다) |
| 실거래가 | `zigbang real-price apt-…` · `naver real-price <단지 번호> --pyeong <평형 번호>` (평형 하나씩만 주어 단지 전체는 직방·당근으로 보고, 네이버는 평형을 정해 볼 때 쓴다. 전용면적이 같은 평형끼리 거래가 겹친다) · `daangn real-price <단지 ID>` (단지 없는 건물은 `--item <매물 ID>`) · `dabang real-price <단지 ID>` (단지 없는 매물은 `--listing <매물 ID>`, 이 집 또는 그 동의 같은 건물 유형 거래) · 동·구 단위 `daangn region-real-price <동·구>` (신고가는 `--new-high`, 웹처럼 최근 공개일 하루치라 비면 `--previous-days`) |
| 시세·가격 흐름 | `naver market-price <단지> --pyeong <평형 번호>` (기관 시세) · `naver trend <동·구>` (아파트 주간) · `daangn price-trend <단지 ID>` (평형 하나, 기본 대표 평형) · `dabang price-trend <단지 ID> --pyeong <space_seq>` (월별 실거래 평균) |
| 학교 | `naver school <school_code>` (`complex`·`listing` 의 `schools[]` 에서, 그 학교에 배정되는 단지는 `--complexes`) · `daangn school <학교 이름\|school_code>` (배정 단지, 여러 곳이면 `candidates` 의 `school_code` 로) · `dabang school <school_code> --level <level>` (`dabang complex` 의 `schools[]` 에서, 중학교 특목고·자사고 진학률, 고등학교 대학 진학률) · 동 안 학교·유치원·어린이집 목록 `dabang search schools <동> --level <단계>` · 단지 근처 어린이집·유치원 `daangn preschools <단지 ID>` (지역·역 이름으로는 찾지 않는다) · 다방 어린이집·유치원 상세 `dabang school <code> --level 어린이집`·`유치원` (`dabang complex` 의 `nurseries[]`·`kindergartens[]` 의 `code`) |
| 재개발 | `naver search redevelopment <지역>` → `naver redevelopment <구역 번호 또는 이름>` → `naver search listings --redevelopment <구역 번호 또는 이름>` |
| 단지 비교 | `daangn compare <ID> <ID> …` (최대 10곳, 비슷한 크기 평형끼리) · `daangn nearby-complexes <ID>` · 평형대 평당가와 1km 안 단지 `dabang nearby-complexes <ID>` |
| 동네 고르기 | `daangn good-neighborhoods --lifestyle …` · `region-reviews <동>` · `trending-complexes [시·도·구]` (조회 급상승, 빼면 전국) · `popular-listings <동>` (모두 `daangn`) · 동 요약 숫자와 순위 `dabang neighborhood <동>` (학교·편의·교통·안전 순위는 `--ranks`) · `dabang popular-listings <동>` · 미쉐린·블루리본 식당 `dabang hot-places <동>` |
| 역 둘레 시세·주변 | 역 둘레 평균 매물가(호가) `dabang station-prices <역>` · 매물·단지 둘레 역·버스·시설 `dabang nearby <ID>` (분양은 `nearby --sale <sale_id>`, 반려동물 장소·카셰어링은 `--with 반려동물,카셰어링`) |
| 분양·청약 | `dabang search sales <동·구·시도 또는 전국>` → `dabang sale <sale_id>` (일정·평형별 분양가) · 분양 둘레 `dabang nearby --sale <sale_id>` · 날짜별 전국 일정 `dabang sale-schedule --region 서울` (주소·가격은 `--details`) |
| 동네·단지 순위 | 구·시도·전국 안 `dabang region-ranking <범위> --by 평균가` (전세가율·갭가격은 `--unit 단지`, 신고가 단지는 `--by 최고가증감 --unit 단지`, 동 안 단지는 `region-ranking <동> --unit 단지`, 거래·매물이 는 곳은 `--by 거래증감`·`매물증감`, 빌라 매물 수는 `--by 매물수 -t 빌라`) · 학군·생활 동 순위 `--by 과학고진학률`·`대학교진학률`·`학원수 --kind 입시`·`인구증감`·`의료시설` 등 · 전국 `dabang trending-complexes` (조회) · `dabang trade-rankings` (거래) |
| 구 안의 동 이름 | `naver regions <시·도 또는 시·군·구>` |

## 위치 입력

- 동 이름은 그 동 안을 찾는다. 역·장소 이름, `--lat`·`--lng`(함께, 한국 안), `--radius` 는 반경 검색이고 기본 1km다 (매물 검색 최대: 네이버 3km, 다방·직방 5km). 다만 역 이름은 다방이 정한 역 반경(강남역 750m)으로 찾아 범위가 다르다. 직방 `apt` 는 반경이 없다: 역·좌표를 주면 그 위치가 속한 동 하나의 목록(이웃 동은 빠지고 거리 없음)이라, 역 근처 단지는 `zigbang search complexes <역>` 으로 본다.
- 당근은 반경이 없고 당근 웹 화면별로 받는다: 동·구 이름, 역 `--station`, 대학 `--university`, 도로명 주소 `--address`, 좌표 `--lat/--lng`. 역·대학은 당근 주변 목록(역은 도보 `walk_minutes`), 구·좌표·주소는 웹 지도 화면 범위(기본 줌: 구 12 약 12.8×13.6km, 좌표·주소 15 약 1.6×1.7km, `--zoom` 으로 바꿈)를 최근 순으로 준다. 주소는 도로명 주소(`'테헤란로 152'`)만 되고 후보가 여럿이면 `REGION_AMBIGUOUS` 의 `candidates` 그대로 다시 준다. 건물·리 이름은 받지 않는다. 후보는 `daangn search locations <이름>` 이 칸별로 준다.
- 동 이름은 법정동(`역삼동`)으로 준다. 행정동(`역삼1동`)은 직방·당근·다방이 `REGION_NOT_FOUND` 힌트로 법정동을 알려 주고, 네이버는 행정동 중심 반경으로 찾는다.
- 같은 이름의 동·구가 여러 곳이면 `REGION_AMBIGUOUS` 와 `candidates` 가 온다. 구 이름을 앞에 붙인다 (`강남구 신사동`. 구 이름까지 겹치면 `hint` 의 예처럼 시·도도 붙인다: `서울 중구 태평로2가`. 직방은 시·도까지 붙인 전체 주소는 못 찾는다. 당근 `광주시` 는 경기도, 옛 광주광역시는 `전남광주`나 구 이름). 같은 이름의 역은 당근만 첫 역으로 찾고 `notes` 로 알린다 (당근은 노선을 붙여 고른다: `--station '서울5호선 양평역'`. 직방은 역·학교도 `REGION_AMBIGUOUS` 라 `hint` 대로 `'영등포구 양평역'` 처럼 구·동 이름을 붙인다. 다방·네이버는 `REGION_AMBIGUOUS` 의 `candidates`·`hint` 대로 좌표로 찾는다).
- 직방 `room`·`store` 는 `성수동` 처럼 `○가` 로 나뉜 동을 1가·2가 합쳐 찾는다 (첫 동만 찾았으면 `notes` 로 알리니 나머지 `○가` 동을 따로 찾는다). 직방 `apt`·`stay`·네이버·당근·다방은 합치지 않고 `REGION_AMBIGUOUS` 로 `성수동1가`·`성수동2가` 를 고르게 한다 (직방 `apt`·`stay` 는 성남시처럼 구가 있는 시도 `성남시 분당구` 처럼 구를 고르게 한다). 다방은 여러 캠퍼스에 맞는 대학 이름(`연세대`)도 고르지 않고 `REGION_AMBIGUOUS` 로 캠퍼스 후보를 주니, 후보 이름 그대로(`'연세대학교(원주캠퍼스)'`) 다시 부른다. 네이버 단지 이름도 여러 단지에 맞으면 `REGION_AMBIGUOUS` 라 `candidates` 의 단지 번호로 다시 부른다 (위치로 준 단지 이름이면 `hint` 대로 단지 둘레는 후보의 동 이름으로). 네이버는 이름이 맞는 역·동이 없고 후보가 여럿일 때도 `REGION_AMBIGUOUS` 라 후보의 역·동 이름 그대로 다시 부른다.

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
| 면적 | `--area-min` (전용 ㎡) | `--area-min` (전용 ㎡, `--area-basis 공급` 이면 공급) | `--area-min` (전용 ㎡) | `--area-pyeong-min` (평, 정수. 빌라는 전용, 오피스텔은 계약, 아파트는 공급 평, `room` 은 매물 유형별) |
| 아파트 공급 ○평대 (예: 30평대) | `apt --supply-area-min 99 --supply-area-max 132` | `-t 아파트 --area-basis 공급 --area-min 99 --area-max 132` | 공급 조건이 없어 전용 ㎡ 로 옮긴다: 공급 ㎡ × 0.75 쯤 (전용 59㎡형 ≈ 공급 24~26평, 84㎡형 ≈ 32~35평이라 20평대에 84㎡ 는 넣지 않는다). 답에 기준을 적는다 | `apt --area-pyeong-min 30 --area-pyeong-max 39` |
| 반지하·지하 빼기 | `--floor 지상,옥탑방` (`지상` 만이면 옥탑방도 빠진다) | `--floor 1층,저층,중층,고층,탑층` | `--floor 1층,2~5층,6~9층,10층이상` | `--floor 1층,2층이상,옥탑` |

평형을 고르는 값도 소스마다 다르다: 직방 `pyeongs[].id` → `--pyeong`, 네이버 `pyeongs[].number` → `--pyeong`, 다방 `pyeongs[].space_seq` → `--pyeong` (셋 다 평수가 아니라 평형 ID), 당근 아파트형 단지는 `pyeongs[].pyeong`(공급 평) → `--pyeong`, 그 밖은 `pyeongs[].area_group`(전용 ㎡) → `--area`.

### '원룸' 의 뜻

- 직방: 방 하나짜리라 원룸형 오피스텔도 나온다 (`property_type: "오피스텔"`). 빌라는 투룸 이상만 있다. 방 1개짜리 아파트는 `search listings apt --supply-area-max 50` 으로 찾는다.
- 네이버: `-t 원룸` 은 건물 분류라 방이 여럿인 매물도 섞인다. 방 하나만이면 `--room 원룸` 을 함께 준다. 목록의 `room_type` 은 `null` 이다 (토지·사무실·상가·건물처럼 방 칸이 없는 유형은 키가 없다).
- 당근: 작성자가 고른 분류라 방 1개 오피스텔·아파트·주택은 빠지고 방 2개 매물이 섞일 수 있다 (오피스텔도 보려면 `-t 원룸,오피스텔`). `-t 투룸` 은 투룸 **이상**이다. 목록의 `room_type` 은 원룸에만 붙고 방 2개 매물에도 붙을 수 있다.
- 다방: `room` 은 다방 '원룸·투룸' 목록이라 방 1~2개짜리 오피스텔·아파트도 나온다 (`property_type`). `villa` 는 방 하나짜리 빌라도 나오고 `property_type` 이 늘 `빌라` 다.
- 방 수는 `listing` 상세의 `room_count` 로 본다. 이 안내는 결과 `notes` 에 다시 붙지 않는다.

### 직방

- 매물 검색은 유형별 하위 명령(`room`·`apt`·`store`·`stay`)이고, 단지 매물만 `search listings --complex <ID>` 다. `room`·`store` 결과는 **직방 목록 순**이라 거리순이 아니다 (가까운 매물은 `distance_km` 로 고른다). `room` 은 종류(원룸·오피스텔·빌라)마다 `--limit` 을 나눠 종류별 묶음으로 준다.
- 단지 ID 는 `apt-…`(아파트)·`officetel-…`. `real-price` 는 `apt-…` 만 받는다.
- 아파트 목록은 같은 호의 매물을 한 줄로 묶는다 (`listing_count`). `is_price_range: true` 면 가격은 묶음 최저가라 `id` 매물의 가격과 다를 수 있으니, 매물별 가격은 `zigbang catalog <catalog_id>` 한 번으로 본다 (묶음 매물 전부의 가격·상세. `listing_ids` 를 `listing` 으로 하나씩 보면 매물마다 요청 2회다). `catalog_id` 가 `null` 이면(직방이 호 ID 를 주지 않음) 묶음을 `catalog` 로 볼 수 없어 `listing_ids` 를 `listing` 으로 본다.
- 아파트 줄의 `listing_kind` 가 `신규분양` 이면 가격은 분양가다. `coalition-` ID 에는 집주인 매물뿐 아니라 신규분양도 있고, 지역 목록 앞쪽에 신규분양이 섞여 올 수 있어, 빼려면 `search listings apt` 에 `--no-new-sale` 을 준다 (동·구 목록만, 단지 매물에는 없다).
- 아파트 줄·상세의 `pyeong_id` 는 평형 ID 라 `search listings --complex <단지> --pyeong <pyeong_id>` 와 `real-price <단지> --pyeong <pyeong_id>` 에 그대로 넘겨 같은 평형의 매물·실거래를 잇는다.
- `real-price` 의 `registered: null` 은 '등기 안 됨' 이 아니라 모름이다 (직방은 2023년 1월 이후 계약만 표시). `new_high`·`new_low` 는 최근 3년 안 경신이라 단지 역대 최고·최저가가 아니고, `jeonse_ratio` 는 0~1 비율이다. `--trade 전체` 는 매매와 전월세를 최신 순으로 섞어 주니 전월세가 많은 단지는 앞쪽이 전월세뿐일 수 있다.
- `stay` 요금은 주 단위(`weekly_rent_manwon`)라 월세와 바로 비교하지 않는다. 기간 총비용은 직방이 로그인해야 보여 줘서 jibsa 가 주지 않는다 (주당 금액 × 주 수가 아니다). `listing stay-… --check-in … --check-out …` 은 그 기간에 예약할 수 있는지 `available` 만 주고, `--check-out` 은 **마지막으로 머무는 날**이다 (7~84일). `stay --sort distance` 는 `--radius` 없는 역 이름 검색에서만 된다 (기본은 직방 추천순). 상세의 반려동물은 `options` 가 아니라 `pet_allowed`(추가 청소비 `pet_cleaning_fee_manwon`)로 보고, 위약금은 `refund_rules` 다 (웹에 고정된 표라 계약 전 `url` 에서 확인).
- `store` 권리금 `0` 은 무권리, `null` 은 모름이다. 사무실은 권리금이 해당 없음이라 `key_money_manwon` 키가 없을 수 있고, 권리금 조건(`--key-money-*`)을 걸면 이런 사무실은 빠진다.
- 상세 `residence_type` 이 `근린생활시설` 이면 전입신고·전세대출이 막힐 수 있고, `다가구` 면 선순위 보증금을 확인하라고 알린다. 목록에서 보려면 `room` 에 `--details` (매물마다 요청 1회 더).

### 네이버

- `search listings` 는 지역, `--complex <이름|번호>`, `--redevelopment <구역 번호>` 세 모드다. 단지 모드는 거래 유형·평형·동·가격·정렬·`--limit` 만, 재개발 모드는 거래 유형·가격·정렬·`--limit` 만 받는다. `--redevelopment` 와 `redevelopment` 는 구역 이름도 받는데, 같은 사업 구역이 법정동마다 따로 등록돼 이름이 같은 구역이 여럿이면(한남제3재정비촉진구역) 하나를 고르지 않고 `REGION_AMBIGUOUS` 의 `candidates` 에 구역 번호를 주니 그 번호로 다시 부른다.
- 매물 순서는 네이버 정렬(기본 랭킹순)이라 역·좌표 검색도 거리순이 아니다. 네이버에는 가까운순이 없으니 가까운 매물은 `--radius` 를 줄이거나 `distance_km` 로 고른다.
- 가격순 정렬은 매매가와 보증금을 섞어 세운다. 가격을 비교할 때는 `--trade` 를 하나만 준다.
- `trend --pyeong-range 30` 은 30~40평 범위다 (평형 번호가 아니다). 최근 4주쯤의 `trade_count` 는 신고가 덜 모여 적으니 거래가 줄었다고 읽지 않는다.
- 상세에는 중개보수 상한(`agent_fee_manwon`, 네이버 계산)이 붙고 매매는 세금 추정치도 붙는다. `agent_fee_individual_check_required` 가 `true` 면 네이버가 금액 대신 '개별확인' 으로 보여 주는 매물이라 `agent_fee_manwon` 이 `null` 이다 (중개보수는 중개사에게 따로 확인). 둘 다 `null` 이면 조회에 실패했거나 직거래인지 알 수 없는 매물이다. 직거래 매물은 두 키가 없다. `loan_manwon` 이 양수면 융자가 있다.
- 상세와 `search listings` 목록은 매물 유형에 따라 네이버 화면에 없는 칸의 키가 없다 (토지·고시원은 방·층·면적·난방 등, 상가·사무실·건물은 방 수, 건물류는 해당층·공급면적도, 재개발은 방·면적. 재산세·종부세는 아파트·재건축·단지형 빌라만). 키가 없으면 그 유형에 해당 없는 것이고 `null` 이면 모르는 것이다.
- 상세 `parking` 은 아파트·오피스텔·재건축·분양권이면 단지 전체 대수 (`단지 전체 12602대 (세대당 1.32대)`, 가능·불가 없음)라 매물이 올린 대수와 다를 수 있다. 원룸·빌라 등은 매물이나 건축물대장의 대수라 `가능 (총 8대, 세대당 0.5대)` 꼴로도 온다.
- `badges` 는 네이버 화면의 확인 배지다 (`집주인`·`소유자`·`현장`, HUG 안심임대인 매물은 `HUG 안심임대인` 이 더 붙는다). `[]` 는 방식 배지·HUG 배지가 모두 없다는 뜻일 뿐이다. 전화·서류로 확인한 매물과 확인하지 않은 매물이 함께 들어 `[]` 만으로는 확인 여부를 알 수 없고, 이런 매물도 HUG 안심임대인이면 `["HUG 안심임대인"]` 이라 비어 있지 않다고 집주인·현장 확인 매물인 것은 아니다. 네이버가 확인한 날은 `confirmed_at` 이다.
- 지역 인자가 구·군·구 없는 시 이름(`성동구`, `구리시`)이나 시·군·구가 하나뿐인 `세종` 이면 `--radius` 없이는 그 구·군·시·세종 전체(`boundary`)를 찾는다 (`search listings`·`search complexes`·`search redevelopment`. `search listings` 는 매물이 많으면 `has_more`·`next` 로 나눠 본다). 구가 있는 시(`성남시`)는 시 전체로 찾을 수 없어 중심 반경이니 `성남시 분당구` 처럼 구 이름을 준다 (`notes` 가 구 이름을 알린다). `trend` 도 구가 있는 시 이름은 `REGION_AMBIGUOUS` 로 멈추니(네이버가 시 추이를 0 으로 준다) `trend '성남시 분당구'` 처럼 구 이름으로 부른다. `trend 전국` 은 전국 추이다.
- `complex`·`search complexes` 의 `monthly_asking`·`short_term_asking` 은 월세 최저·최고가 아니라 가격 낮은 순 첫 매물과 높은 순 첫 매물의 (보증금, 월세) 짝이다. `lowest` 의 월세가 `highest` 보다 클 수 있다 (`5000/420 ~ 700000/240`). 월세 범위로 읽지 않는다.
- `complex --pyeong` 의 `real_price_summary.sale`·`jeonse` 에 `since` 키가 있으면 3년 안 거래가 없어 5년 기준으로 받은 요약이고(이때 `average_3m_manwon` 은 `null`) 조회에 실패한 유형은 `null` 이다. `average_3m_manwon` 은 최근 3개월 평균이다.
- `complex` 의 `pyeong_groups[]` 는 비슷한 평형을 묶은 목록이다. 평형이 많은 단지는 묶음의 `representative_pyeong`(대표 평형 번호)을 `--pyeong` 에 넣고, `pyeong_numbers` 는 묶음에 든 평형 번호들이다 (대표 번호가 첫 항목이 아닐 수 있다). `real-price --pyeong N --group` 은 그 묶음의 모든 평형 거래가 섞여 와서 거래마다 평형을 알 수 없고 `--period` 와 함께 못 쓴다.
- `complex --pyeong` 하나의 `price_per_pyeong`(매매·전세, 월세 없음)은 공급 평수 기준 네이버 매물 호가의 주간 값이다. 실거래 평당가가 아니니 실거래는 `real_price_summary`·`real-price` 로 본다.
- 상세의 `nearby_development`(근처에 생길 지하철역 `rail`·개발 지구 `area`)는 `[]` 면 없는 것이고 `null` 이면 모름(조회 실패, 또는 네이버가 그 목록을 비워 줌)이다. `school --complexes` 의 단지 `assigned_dongs` 가 `null` 이면 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지(동 묶음)를 주지 않은 것이다.
- `알 수 없는 값 (HT009)`·`알 수 없는 시설 (…)`·`알 수 없는 항목 (…)` 은 네이버가 값을 줬는데 jibsa 가 그 코드를 읽지 못한 것이다 (`null` 과 다르다). 뜻을 짐작해 옮기지 말고 jibsa 가 읽지 못한 값이라고 그대로 알린다. 대개 네이버가 새 코드를 더했는데 jibsa 표가 아직 모르는 경우라, 뜻이 필요하면 `url` 의 네이버 화면에서 확인해 보라고 권한다 (화면이 그 코드를 그리는지는 보장하지 않는다).

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

- 매물 검색은 유형별 하위 명령(`room`·`villa`·`officetel`·`apt`)이다. 결과는 **다방 목록 순**이라 거리순이 아니다 (역·좌표 검색은 `distance_km` 로 고른다). 정렬은 단지 매물에만 있다: 단지에서 가장 싼 매물은 `search listings --complex <ID> --trade 매매 --sort 낮은가격순` (넓은 순은 `면적넓은순`).
- `apt --condition 세안고` 는 세입자 낀 매매 매물만이라 매매 없이 주면 `INVALID_ARGUMENT` 다. 단지 세대당 주차 대수는 `officetel`·`apt` 의 `--parking-min` 이고, `--condition 주차` 는 주차 가능 여부다.
- 매물 검색은 동·역·대학 이름을 받고 구·시 이름은 못 찾는다 (`REGION_NOT_SUPPORTED`). 역은 다방이 정한 역 반경(강남역 750m)이다. `apt` 는 동 검색이 없어 동 경계를 덮는 사각형에서 그 동 매물만 남겨 `returned` 가 적을 수 있다.
- 아파트 매물 목록(`apt`·단지 매물·인기 매물, `room` 에 섞인 아파트)은 다방이 공급면적만 줘서 `area_m2` 가 `null` 이고 `supply_area_m2` 가 공급면적이다. 다른 소스의 전용면적과 견주려면 `listing` 의 `area_m2` 를 본다. `--area-pyeong-min` 은 아파트는 공급 평, 오피스텔은 계약 평이다 (오피스텔 결과의 `area_m2` 는 전용이라 조건보다 작게 나온다).
- 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는 표시라 `trade_type: 월세` 에 `short_lease: true` 다. 보증금이 월세 한두 달치(95/95)면 단기 계약 가격일 수 있다. 단기임대 가능 매물만은 `--condition 단기임대`.
- 목록의 `address` 는 찾은 동의 매물만 시·구까지다 (역·좌표 검색은 동 이름만). `listing` 은 `id` 대신 다방 화면의 매물번호(`listing_number`)도 받는다.
- `real-price --listing` 은 `--trade` 를 빼면 매물의 거래 유형(매매 매물은 매매, 월세·전세 매물은 전월세)을 따른다. `basis` 가 `이 집 (…)` 이면 이 매물과 같은 지번 건물 거래(같은 건물 다른 집도 든다), 아니면 그 건물이 아니라 그 동의 같은 건물 유형 거래다. 다세대·연립은 `area_m2`(전용)가 비슷한 거래만 견주고, 단독·다가구의 `total_floor_area_m2` 는 건물 전체 연면적이라 매물 전용면적과 견주지 않는다.
- `region-ranking` 의 값은 항목에 맞는 키에만 있다 (평균가 `value_manwon`, 거래량·학원수 `count`, 전세가율·진학률 `percent`, 시세증감 `change_percent`). 시세증감·최고가증감의 `change_manwon` 은 오른 금액이지 현재가가 아니다 (새 최고가 = `prev_price_manwon + change_manwon`). 거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 기본이 아파트·오피스텔 합산(`complex_type`)이라 아파트만 보려면 `-t 아파트` 를 준다. 거래증감·매물증감은 `prev_count` → `count` 를 `comparison`(`전월대비`·`최근 30일 전 대비`) 기준으로 읽고 `change_count` 는 줄면 음수다. 동 이름 범위는 `--unit 단지` 만 받는다. 매물수·거래량·선호도는 `-t 빌라` 를 주면 '매물정보' 탭(빌라 포함, 동 순위만)이라 기본('시세정보' 탭, 아파트·오피스텔)과 값이 다르다. 결과의 `tab` 으로 구분한다.
- 분양 둘레는 `nearby --sale <sale_id>` 로 준다. 분양 ID 를 위치 인자로 주면 단지 ID 로 읽혀 `NOT_FOUND` 다. `nearby --with 반려동물` 은 단지 ID 만, `카셰어링` 은 매물·단지 ID 만 받는다.
- `search sales` 는 전국·시·도·시·군·구면 다방 분양 지역 목록 그대로(`total` 은 그 지역의 분양 수)이고, 동·역·좌표는 지도 사각형이라 역·좌표 둘레는 반경을 덮는 사각형 전체다. 목록의 `sale_household_count` 는 분양 세대수, `household_count` 는 총세대수다 (지도 사각형 결과는 `null`). `price_kind` 가 `임대가`·`보증금` 이면 가격이 분양가가 아니다.
- `school` 은 `--level` 이 코드와 맞아야 한다 (`dabang complex` 의 `schools[].level` 을 그대로, `nurseries[]` 는 어린이집, `kindergartens[]` 는 유치원). 틀리면 다방이 서버 고장과 같은 500 을 줘서 `UPSTREAM_ERROR`(`status` 500)이니 코드·단계부터 다시 본다. 다방 학교 코드는 네이버 `school` 코드와 다르다.
- `station-prices` 는 실거래가가 아니라 지금 올라온 원룸·투룸 매물의 평균(다방 '평균 매물가')이다. `neighborhood` 의 `rank` 는 1 이 가장 많거나 높고, 동 하나만 받는다.

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
| `NOT_FOUND` | 단지·학교·평형·재개발 구역 ID 나 이름을 같은 소스의 결과에서 그대로 옮겼는지 본다 |
| `LISTING_UNAVAILABLE` | 매물 ID 를 같은 소스의 결과에서 옮겼는지 본다. 맞으면 내려간 매물이라 후보에서 뺀다 |
| `RATE_LIMITED` | `retry_after_seconds` 만큼 기다리거나 다른 소스를 쓴다 (`jibsa limits` 로 상태 확인) |
| `NETWORK_ERROR` | 잠시 뒤 한 번만 다시 부른다. `hint` 가 프록시·인증서 설정을 가리키면 다시 부르지 말고 사용자에게 알린다 |
| `BROWSER_UNAVAILABLE` | 모든 소스가 같이 실패하니 다른 소스로 돌지 않는다. `hint` 의 명령(`jibsa install-browser`, 리눅스 라이브러리는 `sudo …`)을 사용자에게 알린다 |
| `INTERNAL_ERROR` | 에러 JSON 을 `jibsa --version` 과 함께 사용자에게 그대로 보여 준다 |

## 더 읽을 곳

`jibsa guide <소스>` 는 절 목록, `jibsa guide <소스> <절 이름>` 은 그 절만 쓴다 (예: `jibsa guide daangn search listings`, `jibsa guide common 에러 대응`). 같은 문서: [공통](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md) · [직방](https://github.com/Rukkakka/jibsa/blob/main/docs/zigbang.md) · [네이버](https://github.com/Rukkakka/jibsa/blob/main/docs/naver.md) · [당근](https://github.com/Rukkakka/jibsa/blob/main/docs/daangn.md) · [다방](https://github.com/Rukkakka/jibsa/blob/main/docs/dabang.md)
