# 네이버 CLI 사용법 (`jibsa naver`)

[설치](../README.md) · [공통 사용 규칙](common.md) · [개발 가이드](../references/providers/naver.md) · [매물 검색](#1-search-listings--매물-찾기) · [단지 검색](#2-search-complexes--지역-안-단지-목록)

> 금액은 **만원**, 면적은 **㎡** (1평 = 3.3㎡)다. 출력 형식·누락값·에러 대응·요청 제한 같은 공통 규칙은 [공통 사용 규칙](common.md)에 있고, 이 문서는 네이버에만 있는 내용을 적는다.

## 한눈에 보기

| 명령 | 하는 일 | 무엇을 넣나 | 다음에 쓰는 곳 |
| --- | --- | --- | --- |
| `search listings` | 매물 찾기 | 지역 (동·주소·역·단지) | `listing` |
| `search complexes` | 지역 안 **단지** 목록 | 지역 | `complex`, `search listings --complex` |
| `complex` | 단지 하나의 정보 | 단지 이름 또는 번호 | `search listings --complex`, `real-price`, `market-price`, `school` |
| `search listings --complex` | 단지 안 **매물** 목록 | 단지 이름 또는 번호 | `listing` |
| `real-price` | 단지 평형별 **실거래가** | 단지 번호 | — |
| `market-price` | 단지 평형별 **기관 시세 추이** | 단지 이름 또는 번호 | `real-price` |
| `listing` | 매물 하나 **상세** | 매물 ID | `school` |
| `search redevelopment` | 지역의 재개발 구역 | 지역 또는 좌표 | `redevelopment`, `search listings --redevelopment` |
| `redevelopment` | 재개발 구역 하나의 정보 | 구역 번호 | `search listings --redevelopment` |
| `search listings --redevelopment` | 구역 안 현재 매물 | 구역 번호 | `listing` |
| `trend` | 동·구 아파트 주간 추이 | 지역 또는 좌표 | — |
| `regions` | 시·도·구의 **하위 지역** 목록 | 시·도 또는 시·군·구 이름 | `search listings`, `search complexes`, `trend` |
| `school` | 초등학교 하나 **상세** | 학교 코드 | — |

### 보통 이렇게 이어서 쓴다

```
지역으로 매물 찾기     search listings ──────────────────────────────▶ listing
지역으로 단지 고르기   search complexes ─▶ complex ─┬─▶ search listings --complex ──────▶ listing
                                             ├─▶ real-price / market-price
                                             └─▶ school (schools[].school_code)
재개발 구역 고르기     search redevelopment ─▶ redevelopment ─▶ search listings --redevelopment ─▶ listing
동네 흐름 보기         trend
동네 하나씩 훑기       regions <구> ─▶ (동마다) search listings / search complexes
```

---

## 1. `search listings` — 매물 찾기

동 경계 또는 위치 반경에서 현재 매물을 찾는다.

**무엇을 넣느냐에 따라 찾는 방식이 다르다**

재개발 구역 매물은 `search listings --redevelopment <구역 번호>`로 찾는다. 지원 옵션은 8절에 있다.

특정 단지의 매물은 `search listings --complex <단지 이름 또는 번호>`로 찾는다. 지역·좌표와 함께 사용할 수 없다. `--complex` 모드의 지원 옵션은 4절에 있다.

| 넣은 것 | 찾는 범위 | 기본 순서 |
| --- | --- | --- |
| 동 이름 (`역삼동`) | 그 동 전체 | 랭킹순 |
| 주소·역·단지 (`강남역`, `'역삼동 719-28'`) | 그 지점 반경 (기본 1km) | 가까운순 |
| `--lat` / `--lng` | 그 좌표 반경 | 가까운순 |

**인자·옵션**

| 분류 | 옵션 | 넣을 수 있는 값 |
| --- | --- | --- |
| 위치 | `--lat`, `--lng` | 중심 좌표 (지역 이름 대신) |
| | `--radius` | 반경 km (0.1~3.0, 기본 1) |
| 종류 | `-t`, `--type` | 아파트, 오피스텔, 빌라, 원룸, 단독·다가구, 전원주택, 상가주택, 한옥, 고시원, 재건축, 분양권, 오피스텔분양권, 재개발, 사무실, 상가, 건물, 상가건물, 숙박, 공장·창고, 토지, 지식산업센터, 기타 |
| | `--trade` | 매매, 전세, 월세, 단기임대 |
| 가격 | `--deposit-min` / `--deposit-max` | 보증금·전세금 |
| | `--rent-min` / `--rent-max` | 월세 |
| | `--price-min` / `--price-max` | 매매가 |
| | `--manage-cost-min` / `--manage-cost-max` | 관리비 |
| | `--loan` | 융자금: 없음, 30%이하 |
| 방·면적 | `--room` | 원룸, 투룸, 쓰리룸, 포룸이상 |
| | `--one-room-shape` | 오픈형, 분리형 |
| | `--area-min` / `--area-max` | 면적 (㎡) |
| | `--area-basis` | 전용(기본), 공급 |
| | `--bathroom` | 1개, 2개, 3개, 4개이상 |
| 층·방향 | `--floor` | 1층, 저층, 중층, 고층, 탑층, 지하층 |
| | `--direction` | 동향, 서향, 남향, 북향, 북동향, 남동향, 북서향, 남서향 |
| 시설 | `--facility` | 엘리베이터, 주차, 보안시설, 풀옵션, 에어컨, 테라스, 베란다, 마당, 복층 (**모두** 갖춘 매물만) |
| 입주 | `--move-in` | 바로입주, 90일내 |
| 단지 | `--household-min` / `--household-max` | 세대수 |
| | `--parking` | 세대당1대, 세대당1.5대, 전기차충전 |
| | `--entrance` | 계단식, 복도식, 복합식 |
| 건물 | `--building-age-min` / `--building-age-max` | 사용승인 후 햇수 (min 5 → 5년 이상, max 5 → 5년 이내) |
| 기타 | `--subway-minutes` | 역까지 걸어서 N분 안 (1~25) |
| | `--owner-verified` | 집주인 확인 매물만 |
| | `--photo-only` | 사진 있는 매물만 |
| 결과 | `--sort` | 가까운순, 랭킹순, 가격낮은순, 가격높은순, 최신순, 면적좁은순, 면적넓은순 |
| | `--limit` | 최대 결과 수 (1~120, 기본 30) |
| | `--next` | 앞 결과의 `next` 값. 지역·조건을 그대로 두고 주면 받은 매물 다음부터 이어 받는다 (`--limit` 은 바꿀 수 있다) |

**사용 예시**

```bash
jibsa naver search listings 역삼동 -t 오피스텔 --trade 월세 --deposit-max 3000 --rent-max 150
jibsa naver search listings 역삼동 -t 오피스텔 --trade 월세 --deposit-max 3000 --rent-max 150 --next <앞 결과의 next>
```

**반환값**

`region`, `boundary`(동 검색) 또는 `radius_km`(반경 검색), `total`, `returned`, `has_more`, `next`(더 있을 때만), `listings[]`를 준다. `total` 은 서버 집계다 (동 검색은 동 안, 반경 검색은 반경을 감싸는 사각형 안).

`next` 를 같은 지역·조건에 `--next` 로 주면 이어 받는다. 이어 받을 때는 지역을 다시 찾지 않아(앞 결과가 찾은 위치·동·정렬을 `next` 에 담는다) 네이버 요청이 그만큼 준다. 동 검색은 동마다의 목록 커서로(`○가` 동도 동마다 이어 받을 곳을 남겨 앞 페이지와 겹치지 않고 `total` 도 같다), 가까운순 반경 검색은 이어 받을 지도 칸과 그 칸의 커서로, 다른 정렬은 정렬 목록 커서로 이어 간다. 차단을 피하려고 요청 상한에서 멈춘 결과(`[일부]` 안내)도 `next` 로 이어 받는다. 가까운순은 페이지마다 가까운 순으로 세워 주므로 앞 페이지 끝보다 조금 가까운 매물이 다음 페이지에 올 수 있다 (지도 칸 단위 근사). 단지·재개발 구역 매물(`--complex`·`--redevelopment`)은 `has_more` 만 주고 이어 받지 않는다. 매물마다 `id`, `url`, 거래 유형, 매물 유형, 제목(단지명), 가격, 관리비, 전용면적, 층, 주소(동까지), 거리, 등록일이 있다.

**오류와 대응**

모호한 주소·동은 `REGION_AMBIGUOUS`(시·구를 붙여 다시 찾는다), 위치 미발견은 `REGION_NOT_FOUND`. 동 이름을 끝말 없이 줘도(`송정`, `신흥`) `송정동`처럼 같은 이름 동이 여러 곳인지 보고 멈춘다 (요청 1회 더 들 수 있다). `○가` 로 나뉜 동(성수동 → 성수동1가·2가)은 `성수` 처럼 `동` 을 빼고 줘도 직방처럼 모두 찾아 합친다 (`boundary`·`region.name` 은 `"성수동1가·성수동2가"`). 동 목록 API 가 법정동을 하나만 받아 동마다 따로 찾고 `--limit` 을 동끼리 나눠 쓰며, 형제 동을 찾는 요청 1회와 동마다의 목록 요청이 더 든다. 목록 옵션에 없는 값이나 다른 소스의 옵션을 옮겨 쓰면(`--bathroom 1`, `--room 2`, `--condition 엘리베이터`, `--room-count 2개`) 에러 `hint` 가 맞는 옵션(`--bathroom 1개`, `--room 투룸`, `--facility 엘리베이터`, `--room 투룸`)이나 네이버에 그 조건이 없다는 것(`--option 반려동물가능`, `--city`)을 알려 준다. `--next` 가 다른 지역·조건의 값이면 `INVALID_ARGUMENT` 다. 좌표 누락·옵션 범위·모드 충돌은 `INVALID_ARGUMENT`.

**주의사항**

> 목록형 옵션은 반복하거나 쉼표로 넣는다: `--trade 전세,월세`, `-t 아파트 -t 오피스텔`. `--loan`·`--area-basis`·`--sort`는 하나만 받으며, 여러 번 주면 마지막 값을 쓴다.

옵션을 생략하면 가격·면적·층·시설 등의 조건은 적용하지 않는다. `--type` 기본값은 아파트·오피스텔·빌라·원룸·단독·다가구·전원주택·상가주택 전체다. `--trade`는 기본 전체이며 월세·매매가·보증금 조건만 주면 거래 유형을 자동으로 좁히고 `notes`로 안내한다. `--trade`와 맞지 않는 가격 조건은 [공통 규칙](common.md#출력-규칙)대로 입력 오류다. `--owner-verified`·`--photo-only`는 기본 꺼짐이다. 가격·면적·세대수·연식의 최솟값은 0이며, 하한이 상한보다 크면 입력 오류다.

- 조건은 모두 네이버 서버 필터로 보내 조건에 맞는 매물만 받는다.
- 검색어는 네이버 주소 검색 → 검색창 자동완성(동 → 역 → 단지) 순으로 찾는다 ('역' 으로 끝나면 역을 먼저). 넷 다 없으면 `REGION_NOT_FOUND` 다.
- 목록에는 방 수가 없어 `room_type` 은 `null`. 방 수·방 구조는 `listing` 에서 본다.
- 가까운순은 약 200m 단위로 대략 맞춘 순서다.
- 가격순은 매매가와 전세·월세 보증금을 섞어 한 줄로 세우므로 거래 유형이 여럿이면 `notes` 로 알린다 (기본은 모든 거래 유형이다). 가격을 비교할 때는 `--trade` 를 하나만 준다. 월세 가격순은 보증금 순도 월세 순도 아닌 네이버 기준이다.
- 동 이름에도 `--radius` 또는 `--sort 가까운순`을 주면 동 중심 반경으로 검색한다.
- 단지 이름을 위치 인자로 넣으면 단지 주변을 검색한다. 그 단지 안의 매물만 보려면 `--complex`를 사용한다.
- `--lat`·`--lng`는 둘 다 필요하고 대한민국 좌표만 받는다.
- 네이버 원룸 분류는 건물 분류라 방이 여러 개인 매물도 포함될 수 있다. 방 하나만 찾으려면 `--room 원룸`을 함께 준다.
- `-t 빌라` 에는 일반 빌라 외에 네이버가 단지로 따로 분류한 연립·다세대(도시형생활주택 포함)도 들어간다.
- `--one-room-shape`(오픈형·분리형)는 중개사가 원룸 구조를 입력한 매물에만 걸린다. 단지로 등록된 매물(아파트·오피스텔·단지형 빌라)은 구조 값이 없어 모두 빠지고, 원룸·빌라·상가주택 등도 구조를 입력하지 않은 매물은 빠진다 (역삼동 원룸 전세 35건 중 9건). 이 옵션을 주면 `notes` 로 알린다. 빠짐없이 보려면 `--room 원룸` 으로 찾고 `listing` 의 `room_type` 으로 구조를 확인한다.
- 세대수·단지 주차·현관 구조 조건은 단지가 없는 빌라 등을 제외할 수 있다.
- `--facility`, `--parking` 만 "모두 해당"(AND)이고, 나머지 여러 값은 "하나라도 해당"(OR)이다.

## 2. `search complexes` — 지역 안 단지 목록

지역의 단지 후보를 세대수·연식·매물 수 등으로 고른다.

| 옵션 | 넣을 수 있는 값 |
| --- | --- |
| 지역 인자 | 동·주소·역·단지 이름. 좌표를 주면 생략 가능 |
| `--lat`, `--lng` | 중심 좌표. 둘 다 필요 |
| `--radius` | 반경 km (0.1~3.0, 기본 1) |
| `-t`, `--type` | 아파트(기본), 오피스텔, 빌라 |
| `--sort` | 인기순(기본), 세대수순, 최근입주순, 매물수순 |
| `--include-empty` | 매물 없는 단지도 포함 (기본은 매물 있는 단지만) |
| `--household-min` / `--household-max` | 세대수 |
| `--building-age-min` / `--building-age-max` | 사용승인 후 햇수 (min 5 → 5년 이상, max 5 → 5년 이내) |
| `--limit` | 최대 단지 수 (1~120, 기본 30) |

**사용 예시**

```bash
jibsa naver search complexes 역삼동 --sort 세대수순
```

**반환값**

검색 범위, `total`, `returned`, `complexes[]`를 준다. 단지마다 `complex_number`(단지 번호), 단지명, 유형, 주소, 세대수, 동 수, 사용승인일, 거리, 거래 유형별 매물 수(`article_counts`, 네이버가 주지 않으면 `null`), 매매·전세 호가 범위, `url`이 있다.

**오류와 대응**

지역 모호·미발견은 `REGION_AMBIGUOUS`·`REGION_NOT_FOUND`. 필터 범위·유형 위반은 `INVALID_ARGUMENT`.

**주의사항**

동 이름은 동 경계 안, 주소·역·단지·좌표는 반경 안에서 찾는다. 동 이름에 `--radius`를 주면 동 중심 반경을 사용한다. 아파트·오피스텔·단지형 빌라를 지원하며 모든 일반 건물을 검색하는 명령은 아니다. 유형은 반복하거나 쉼표로 지정할 수 있다.

## 3. `complex` — 단지 하나 정보

단지 정보와 선택한 평형·동의 매물 통계를 확인한다.

| 넣는 것 | 설명 |
| --- | --- |
| 단지 (필수) | 단지 이름 (`개포자이`) 또는 번호 |
| `--pyeong` | 평형 번호 (평형 ID, 평수 아님). 그 평형만으로 매물 수·호가를 센다. **하나만** 주면 관리비·시세·최근 3년 실거래 요약도 붙는다 (요청 4회 추가) |
| `--dong` | 동 (`104` 또는 `104동`). 그 동만으로 센다 |

**사용 예시**

```bash
jibsa naver complex 개포자이 --pyeong 1
```

**반환값**

- 기본: 단지 번호, 단지명, 주소(지번·도로명), 세대수, 동 수, 사용승인일, 시공사, 세대당 주차, 용적률, 거래 유형별 매물 수, 매매·전세 호가 범위
- `pyeongs[]`: 평형 번호 (평형 ID, 평수 아님), 전용·공급·계약면적, 방·욕실 수, 세대수 → **이 번호를 `search listings --complex`, `real-price` 의 `--pyeong` 에 넣는다**
- `schools[]`: 배정 초등학교. 학교마다 `school_code`(→ `naver school` 에 넣는다), `name`, `assignment`(배정·선택), `operation_type`(공립·혁신 등), `walking_minutes`, `distance_m`, `students_per_class`, `students_per_teacher`. 요청을 1회 더 해 붙이고, 단지형 빌라도 준다. 조회에 실패하면 `null`, 배정 정보가 없으면 `[]`
- `reconstruction`: **재건축 단지만** 키가 있다. 현재 사업 단계와 그 날짜(`current_step`, `current_step_date`), 선정된 시공사, 재건축 후 계획 세대수(`planned_households`), 계획 용적률(`planned_floor_area_ratio`), 지나온 단계와 날짜(`steps[]`, 날짜가 있는 단계만). 요청을 1회 더 한다. 조회에 실패하면 `null`
- `--pyeong` 을 하나만 주면 추가로: 월 관리비(최근·평균·여름·겨울), 기관별 시세(한국부동산원·KB 등), 최근 3년 매매·전세 실거래 요약(평균·최저·최고). 필드는 [선택 평형 부가 정보](#선택-평형-부가-정보-complex---pyeong)

**오류와 대응**

없는 단지·평형·동은 `NOT_FOUND`이며, 평형·동이면 그 단지의 평형·동 목록을 `hint` 로 준다. 부가 정보 미제공은 빈 값이나 안내로 구분한다.

**주의사항**

`--pyeong`(평형 번호, 결과의 `pyeongs[].number`)과 `--dong`(동 이름)은 반복 또는 쉼표로 지정한다. 주면 `article_counts` 와 호가 범위를 그 평형·동 매물만으로 세고 `notes` 로 알린다 (단지 정보와 `pyeongs` 는 그대로 단지 전체). 주지 않으면 단지 전체로 센다.

단지 번호는 `naver complex <단지 이름>`(네이버 단지 검색, 이름이 똑같은 단지 우선. 비슷한 후보는 `notes` 로 알린다), `fin.land.naver.com/complexes/{번호}`, 매물 상세(`listing`)에서 얻는다. 단지로 등록된 빌라(연립·다세대, 빌라 매물의 `complex_number`)도 `complex`·`search listings --complex`·`real-price` 로 볼 수 있다 (빌라 단지에는 동 수·건설사·방 수가 없다).

빌라 단지에는 단일 평형 선택 시의 관리비·기관별 시세·실거래 요약을 붙이지 않고 `notes`로 알린다. 개별 실거래는 `real-price`로 확인한다.

## 4. `search listings --complex` — 단지 안 매물 목록

고른 단지의 매물을 평형·동·가격 조건으로 찾는다.

| 옵션 | 넣을 수 있는 값 |
| --- | --- |
| `--complex` (필수) | 단지 이름 또는 번호 |
| `--trade` | 매매, 전세, 월세, 단기임대 |
| `--pyeong` | 평형 번호 (평형 ID, 평수 아님) (`complex` 결과의 `pyeongs[].number`). 반복하거나 쉼표로 구분 (`--pyeong 7,8,19`) |
| `--dong` | 동 (`104`, `104동`). 요청이 1~2회 늘어난다 |
| `--sort` | 랭킹순(기본), 가격낮은순, 가격높은순, 최신순, 면적좁은순, 면적넓은순 |
| `--deposit-min` / `--deposit-max` | 보증금·전세금 |
| `--rent-min` / `--rent-max` | 월세 |
| `--price-min` / `--price-max` | 매매가 |
| `--limit` | 최대 결과 수 (1~120, 기본 30) |

**사용 예시**

```bash
jibsa naver search listings --complex 개포자이 --trade 매매 --dong 104 --price-max 300000 --sort 가격낮은순
```

**반환값**

`complex_number`(고른 단지 번호. 이름으로 찾았으면 `real-price`·`complex` 에 이 번호를 넣는다), `total`, `returned`, `listings[]`(지역 검색과 같은 매물 모양)를 준다.

**오류와 대응**

지역·좌표·지원하지 않는 지역 필터와 `--complex` 동시 지정은 `INVALID_ARGUMENT`. 없는 단지·동은 `NOT_FOUND`이며, 동이면 그 단지의 동 이름을 `hint` 로 준다. 단지 번호로 찾았는데 0건이면 단지가 있는지 확인한다(요청 1~2회 추가). `--pyeong` 을 주었는데 0건이면 평형 번호를 확인해(요청 1~2회 추가), 그 단지에 없는 번호면 `NOT_FOUND` 와 함께 이 단지의 평형 번호를 `hint` 로 준다.

**주의사항**

`--complex`에서는 거래 유형·평형·동·가격·정렬·결과 수 옵션만 지원한다. 지역 인자·좌표·반경·유형·방 수·면적·관리비·시설·연식 등 지역 검색 옵션은 쓸 수 없다. `--pyeong`은 반복, `--dong`은 반복 또는 쉼표로 지정한다. 단지는 이름 또는 번호로 넣는다 ([단지 번호 얻는 곳](#3-complex--단지-하나-정보)).

가격은 지역 검색처럼 네이버 서버 필터로 걸고, 그 금액이 없는 거래는 거르지 않는다. `--trade` 없이 월세·매매가 조건만 주면 그 거래 유형으로 좁히고 `notes` 로 알린다.

정렬은 네이버가 해 준다. 거리가 없어 가까운순은 없다. 가격순은 매매가와 전세·월세 보증금을 섞어 한 줄로 세우므로 거래 유형이 여럿이면 `notes` 로 알린다. 가격을 비교할 때는 `--trade` 를 하나만 준다. 월세 가격순은 보증금 순도 월세 순도 아닌 네이버 기준이라 `notes` 로 알리니, 월세가 싼 순서는 `rent_manwon` 을 직접 비교한다.

네이버 차단을 피하려고 요청 수를 제한해 `--limit` 을 못 채우면 `notes` 로 알린다.

## 5. `real-price` — 평형별 실거래가

단지의 특정 평형 실거래를 확인한다.

| 옵션 | 넣을 수 있는 값 |
| --- | --- |
| 단지 번호 (필수) | 숫자 (이름 안 됨) |
| `--pyeong` | 평형 번호 (평형 ID, 평수 아님) (필수) |
| `--trade` | 매매(기본), 전세, 월세 |
| `--pages` | 몇 페이지 받을지 (1~10, 페이지당 10건, 기본 1) |
| `--period` | 기간: 1년, 3년, 5년. 주면 페이지 대신 그 기간 안 거래를 **모두** 준다. `--pages` 와 함께 쓸 수 없다 |

**사용 예시**

```bash
jibsa naver real-price 12345 --pyeong 2 --trade 전세 --pages 3
jibsa naver real-price 12345 --pyeong 2 --period 3년
```

**반환값**

`complex_number`, `pyeong_number`, `trade_type`, `transactions[]`를 준다. `--period` 를 주면 `period`·`since`(기간 시작일)가 붙는다. 거래마다 계약일, 층, 가격(매매가 또는 보증금·월세), 중개거래/직거래, 해제(취소) 여부, 갱신 계약 여부가 있다. 국토부 신고 기준이고 최근 순이다.

**오류와 대응**

평형 번호 누락·여러 거래 유형·페이지 범위 위반·없는 기간·`--period` 와 `--pages` 동시 지정은 `INVALID_ARGUMENT`. 조회 대상 미발견은 `NOT_FOUND`. 거래가 0건이면 평형 번호를 확인해(요청 1~2회 추가), 그 단지에 없는 번호면 `NOT_FOUND` 와 함께 이 단지의 평형 번호를 `hint` 로 준다. 평형 목록이 비면(없는 단지 번호이거나 평형 정보가 없는 단지) `complex` 로 단지를 확인하라고 `hint` 로 준다.

**주의사항**

`--pages` 기본값은 1이다. 최대 10페이지, 페이지당 10건을 요청하며 거래가 끝나면 일찍 멈춘다. 단지 번호와 평형 ID는 `complex` 결과에서 확인한다.

`--period` 는 아파트·오피스텔 단지면 요청 1회로 기간 안 거래를 모두 받는다. 거래가 많은 평형은 수백 건이 될 수 있다 (대단지 전세 5년 800건 이상). 빌라 단지는 네이버가 기간 조회를 주지 않아 페이지(100건씩, 최대 5페이지)를 받아 기간 시작일 전 거래를 뺀다. 그래도 다 받지 못하면 `notes` 로 알린다. 기간 안 거래가 없으면 `transactions` 가 `[]` 다.

네이버는 같은 거래를 면적이 다른 평형 여러 곳에 함께 주기도 한다 (개포우성1,2차 전세: 84㎡ 평형과 127㎡ 평형에 같은 날·층·금액의 거래 3건). 거래마다 면적을 주지 않아 jibsa 가 가려낼 수 없으니, 평형별 시세를 말할 때는 당근 `real-price` 의 거래별 `area_m2` 로 확인한다.

## 6. `listing` — 매물 상세

매물 상세와 교통·학교·매매 비용을 확인한다.

| 넣는 것 | 설명 |
| --- | --- |
| 매물 ID (필수) | `search listings` / `search listings --complex` 결과의 `id` |

**사용 예시**

```bash
jibsa naver listing 2512345678
```

**반환값**

- 공통 매물 필드(상세에 해당하지 않는 거리 등은 제외) + 방·욕실 수, 방 구조(`room_type`), 방향, 입주 가능일, 주차, 엘리베이터, 옵션, 관리비 포함 항목, 근처 지하철역
- 단지: 단지 번호, 단지명, 동, 평형 번호 (평형 ID, 평수 아님), 공급·계약면적
- 돈: 융자금, 중개보수 상한, 취득세, 재산세, 종부세 (세금·중개보수는 **매매만**, 네이버 계산값)
- 주변: 버스 노선, 배정 초등학교

필드 뜻은 [소스별 반환 필드와 해석](#소스별-반환-필드와-해석)에 있다.

**오류와 대응**

삭제·만료 매물은 `LISTING_UNAVAILABLE`. 부가 조회 실패는 모르는 필드와 요청 제한 오류를 구분한다.

## 7. `search redevelopment` — 재개발 구역 찾기

동 경계 또는 위치 반경에서 재개발 구역을 찾아 사업 단계·계획 세대수·현재 매물 수를 비교한다. 실제 매물은 구역 번호로 다음 절의 단지와 다른 모드를 사용한다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·주소·역·단지 이름. 좌표를 주면 생략 가능 | 미지정 |
| `--lat`, `--lng` | 함께 지정하는 한국 내 좌표. 이름도 주면 좌표 우선 | 미지정 |
| `--radius` | 0.1~3km. 동 이름에도 지정하면 동 중심 반경 | 반경 모드 1km |
| `--trade` | 매매·전세·월세·단기임대. 반복·쉼표 가능. 주면 그 거래 매물이 1건 이상인 구역만 남긴다 | 미지정 (거르지 않음) |
| `--sort` | 매물수순·세대수순 | 매물수순 |
| `--limit` | 1~120 | 30 |

**사용 예시**

```bash
jibsa naver search redevelopment 한남동
jibsa naver search redevelopment 한강진역 --radius 1 --trade 매매 --sort 세대수순
```

**반환값**

`region`, `boundary` 또는 `radius_km`, `total`, `returned`, `areas[]`를 반환한다.

| 구역 필드 | 의미 |
| --- | --- |
| `redevelopment_number` | `search listings --redevelopment`에 전달하는 구역 번호 |
| `name`, `legal_division` | 구역 이름·대표 법정동 |
| `households`, `business_step` | 계획 세대수·사업 단계 |
| `distance_km` | 대표 위치까지 거리. 동 경계 조회는 `null` |
| `article_counts` | 거래 유형별 현재 매물 수 (매매·전세·월세·단기임대). `--trade` 와 상관없이 네 거래를 모두 센다. 네이버가 매물 수를 주지 않으면 `null` |
| `sale_asking_range_manwon` | 매매 호가 범위(만원) |
| `url` | 원 사이트 구역 페이지 |

**오류와 대응**

이름·좌표 모두 누락, 좌표 한쪽 누락, 정렬·거래 유형·반경·한도 위반은 `INVALID_ARGUMENT`다. 모호한 지역은 `REGION_AMBIGUOUS`, 미발견은 `REGION_NOT_FOUND`다.

**주의사항**

동 이름만 주면 동 경계 전체, 주소·역·좌표는 반경 검색이다. 반경 검색은 구역 위치를 받는 요청이 1회 더 들고, 위치를 모르는 구역은 반경 안인지 알 수 없어 뺀다. 네이버는 구역 목록을 거래 유형으로 거르지 않으므로, `--trade` 를 주면 받은 뒤 `article_counts` 로 그 거래 매물이 없는(또는 매물 수를 모르는) 구역을 빼고 뺀 수를 `notes` 로 알린다. 뺀 구역도 `--limit` 에 세며 다시 채우지 않는다. 같은 사업 구역이 법정동마다 별도로 등록될 수 있으므로 이름만으로 중복 제거하지 않는다. `total`은 반경을 감싸는 지도 범위 집계일 수 있어 실제 반경 내 반환 수와 다르다. 사업 단계·계획 세대수와 현재 매물의 계약 조건을 구분한다.

## 8. `search listings --redevelopment` — 구역 안 매물 찾기

앞 절에서 고른 재개발 구역의 현재 매물을 거래 유형과 가격으로 좁힌다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `--redevelopment` | 1 이상의 구역 번호 | 필수 |
| `--trade` | 매매·전세·월세·단기임대. 반복·쉼표 가능 | 미지정 |
| `--deposit-min/max` | 보증금·전세금, 0 이상 만원 | 미지정 |
| `--rent-min/max` | 월세, 0 이상 만원 | 미지정 |
| `--price-min/max` | 매매가, 0 이상 만원 | 미지정 |
| `--sort` | 랭킹순·가격낮은순·가격높은순·최신순·면적좁은순·면적넓은순 | 랭킹순 |
| `--limit` | 1~120 | 30 |

**사용 예시**

```bash
jibsa naver search listings --redevelopment 9000001 --trade 매매 --price-max 300000
```

구역 번호는 문법 설명용 가상 값이다. `search redevelopment`의 실제 결과를 사용한다.

**반환값**

`redevelopment_number`, `total`, `returned`, `listings`를 준다. 매물의 `id`를 `listing`에 넘긴다.

**오류와 대응**

지역·좌표·`--complex`·`--pyeong`·`--dong`과 함께 사용하거나 유형·면적·방·관리비·시설 등 이 표에 없는 지역 검색 조건을 지정하면 `INVALID_ARGUMENT`다. 하한이 상한보다 큰 가격 범위와 가까운순 정렬도 입력 오류다. 조회 실패는 에러의 `code`·`hint`를 확인한다.

**주의사항**

재개발 매물은 건물이 아니라 대지지분 단위라 `area_m2`·`area_pyeong`가 `null`이고, 층이 없는 매물은 `floor`·`building_floor`도 `null`이다 (면적은 원 사이트에서, `listing` 상세도 같다). 가격 조건은 서버 필터이며 명시하지 않은 거래 유형을 가격 조건에 맞게 추론하면 `notes`로 알린다. 가격순은 네이버 기준이므로 여러 거래 유형의 가격을 같은 척도로 단정하지 않는다 (거래 유형이 여럿이면 `notes` 로 알린다). 페이지 요청 예산 때문에 한도보다 적게 반환될 수 있다. 예산을 다 쓴 결과는 구역 전체를 끝까지 조회한 결과가 아니다.

## 9. `trend` — 동네 아파트 주간 추이

동·구의 아파트 매물 수, 평균 평당 호가, 실거래 건수의 주간 추이를 본다. 개별 단지 실거래는 `real-price`로 확인한다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·구 이름. 역·주소·단지는 해당 위치의 법정동 | 미지정 |
| `--lat`, `--lng` | 함께 지정하는 한국 내 좌표. 이름도 주면 좌표 우선 | 미지정 |
| `--trade` | 매매·전세 | 매매 |
| `--period` | 1개월·6개월·1년·3년·5년 | 1년 |
| `--pyeong-range` | 10·20·30·40·50. 하한부터 +10평 범위 | 전체 |

**사용 예시**

```bash
jibsa naver trend 역삼동 --trade 전세 --period 3년 --pyeong-range 30
```

**반환값**

`legal_division`, `trade_type`, `period`, `pyeong_range`와 아래 세 묶음을 준다. 조회 실패한 묶음은 `null`일 수 있다.

| 필드 | 의미 |
| --- | --- |
| `listing_count` | 기간 평균·최근·최저·최고 매물 수, 증감률(`change_rate_pct`), 주별 `weekly[].week_start/count` |
| `price_per_pyeong` | 최근 평균 평당 호가(`latest_manwon`), 주별 `weekly[].week_start/price_per_pyeong_manwon` |
| `trade_count` | 기간 평균·최근 거래 건수, 주별 `weekly[].week_start/count` |

**오류와 대응**

월세·없는 기간·허용되지 않은 평형대, 이름·좌표 누락은 `INVALID_ARGUMENT`다. 지역 미발견과 위치(역·단지·좌표)의 법정동을 찾지 못한 경우(바다 좌표 등)는 `REGION_NOT_FOUND`, 모호하면 `REGION_AMBIGUOUS`다.

**주의사항**

아파트만 제공하며 오피스텔·빌라·월세 추이는 없다. 리 단위 추이도 네이버가 주지 않아, 리를 넣으면 그 리가 속한 읍·면 추이를 주고 `notes` 로 알린다. 번지·도로명 주소를 넣으면 `legal_division` 은 주소가 아니라 그 자리의 법정동 이름이다. 평균 평당 호가는 실제 거래 가격과 다르다. `--pyeong-range 30`은 평형 번호가 아니라 30~40평 범위다. 기본 조회는 세 종류의 데이터 요청이며 위치 해석 요청이 추가될 수 있다.

## 10. `market-price` — 기관 시세 추이

단지 평형의 기관별(한국부동산원·KB부동산·부동산뱅크) 시세를 주별로 본다. `complex --pyeong` 은 최신 시세 한 점만 주고, 이 명령은 흐름을 준다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `COMPLEX` | 단지 이름 또는 번호 | 필수 |
| `--pyeong` | 평형 번호 (평형 ID, 평수 아님) | 필수 |
| `--period` | 1년, 3년, 5년 | 1년 |

**사용 예시**

```bash
jibsa naver market-price 개포자이 --pyeong 1 --period 3년
```

**반환값**

`complex_number`, `pyeong_number`, `period`, `since`, `providers[]`, `url`. 기관마다 `provider` 와 `points[]`(오래된 것부터, 보통 주 1회)를 주고, 점마다 `base_date`, `sale_manwon`(매매 시세 평균), `sale_range_manwon`, `jeonse_manwon`, `jeonse_range_manwon`, `jeonse_ratio_percent`(전세가율 범위, %)가 있다.

**오류와 대응**

평형 번호 누락·없는 기간은 `INVALID_ARGUMENT`, 없는 단지 이름은 `NOT_FOUND`다. 시세가 0건이면 평형 번호를 확인해(요청 1~2회 추가), 그 단지에 없는 번호면 `NOT_FOUND` 와 함께 이 단지의 평형 번호를 `hint` 로 준다. 평형 목록이 비면(없는 단지 번호이거나 평형 정보가 없는 단지) `complex` 로 단지를 확인하라고 `hint` 로 준다.

**주의사항**

요청 1회다 (단지 이름이면 단지 검색 1회 추가). 시세는 기관 추정값이라 실제 거래와 다르다. 실제 거래는 `real-price` 로 확인한다. 시세가 없는 기관은 빠지고, 시세가 없는 평형(빌라 단지 등)은 `providers` 가 `[]` 다. 5년이면 기관마다 260여 점이 나온다.

## 11. `redevelopment` — 재개발 구역 하나

`search redevelopment` 에서 고른 구역의 계획과 현재 매물 통계를 본다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `REDEVELOPMENT_NUMBER` | 구역 번호 (`search redevelopment` 결과의 `redevelopment_number`) | 필수 |
| `--trade` | 매매·전세·월세·단기임대. 반복·쉼표 가능. 주면 매물 수·호가 범위를 그 거래만으로 센다 | 미지정 (전체) |

**사용 예시**

```bash
jibsa naver redevelopment 9000001 --trade 매매
```

구역 번호는 문법 설명용 가상 값이다.

**반환값**

`redevelopment_number`, `name`, `legal_division`, `households`(계획 세대수), `business_step`(사업 단계), `construction_company`(시공사), `floor_area_ratio`·`building_coverage_ratio`(계획 용적률·건폐율, %), `article_counts`(거래 유형별 현재 매물 수. `--trade` 를 주면 그 거래 유형만 센다), `sale_asking_range_manwon`, `jeonse_asking_range_manwon`, `url`.

**오류와 대응**

없는 구역 번호는 `NOT_FOUND`, 잘못된 거래 유형은 `INVALID_ARGUMENT`다.

**주의사항**

요청 2회다. 조합 연락처와 구역 좌표는 내보내지 않는다. 매물 목록은 `search listings --redevelopment` 로 본다. `--trade` 를 주면 `notes` 로 그 거래만 센 값이라고 알린다.

## 12. `regions` — 하위 지역 목록

시·도 안의 시·군·구, 시·군·구 안의 읍·면·동과 법정동 코드를 본다. 구 안의 동을 하나씩 검색할 때 동 이름을 정확히 얻는 데 쓴다.

| 인자 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `QUERY` | 시·도 (`서울`, `경기도`, `충북`) 또는 시·군·구 (`강남구`, `성남시`, `부산시 중구`) | 생략하면 시·도 전체 |

**사용 예시**

```bash
jibsa naver regions            # 시·도 전체
jibsa naver regions 강남구      # 강남구의 동
jibsa naver regions 성남시      # 성남시의 구 (성남시 분당구 …)
jibsa naver regions 세종        # 세종의 읍·면·동 (시·군·구가 세종시 하나뿐이라 바로 동을 준다)
```

**반환값**

`parent`(상위 지역, 시·도 전체 목록이면 `null`), `parent_code`(상위 지역 법정동 코드. 시·도 전체나 구가 있는 시는 `null`), `regions[]`. 지역마다 `name`, `level`(시·도, 시·군·구, 읍·면·동), `legal_division_code`, 중심 `lat`·`lng`.

**오류와 대응**

찾지 못한 지역은 `REGION_NOT_FOUND`, 읍·면·동처럼 하위 지역이 없는 이름은 `NOT_FOUND`다.

**주의사항**

요청은 시·도 전체 1회, 시·도 2회, 시·군·구 3회다. 세종(`세종`·`세종시`)은 시·군·구가 세종시 하나뿐이라 그 아래 읍·면·동을 바로 주고(요청 3회) `notes` 로 알린다. `중구`처럼 같은 이름이 여러 곳이면 고르지 않고 `REGION_AMBIGUOUS` 로 후보(`candidates`)를 알린다. `부산시 중구`처럼 시·도를 붙여 다시 준다. 시·도는 `부산`·`부산시`·`부산광역시` 어느 이름이든 되므로 결과의 `parent`(`부산광역시 중구`)를 그대로 다시 넣어도 된다. 구가 있는 시(성남시·수원시 등)는 네이버가 시를 따로 두지 않아 `성남시 분당구` 처럼 시 이름이 붙은 구를 준다. `경기도 성남시`·`경기 성남시` 처럼 시·도를 붙여도 된다. 네이버 시·도 목록에는 광주광역시·전라남도가 따로 없고 전남광주통합특별시 하나로 나온다. `전남`·`전라남도`·`광주`·`광주광역시` 로 찾으면 전남광주통합특별시의 하위 지역을 주고 `notes` 로 알린다. `광주 광산구`·`전남 여수시` 처럼 옛 시·도 이름을 붙인 시·군·구도 된다. `광주시` 는 경기도 광주시다 (`광주` 로 찾으면 `notes` 에 함께 알린다. `search listings 광주` 는 두 곳이 겹쳐 `REGION_AMBIGUOUS` 다). 결과의 `name` 은 `search listings`·`search complexes`·`trend` 의 지역 인자로 넣는다. 같은 이름의 동이 여러 곳이면 그 명령도 `REGION_AMBIGUOUS` 로 후보를 알린다.

## 13. `school` — 초등학교 상세

`complex`·`listing` 의 `schools[].school_code` 로 학교 하나의 공시 정보를 본다.

| 인자·옵션 | 허용값·의미 | 기본값 |
| --- | --- | --- |
| `SCHOOL_CODE` | 학교 코드 (예: `B100000747`) | 필수 |
| `--complex` | 단지 이름 또는 번호. 주면 그 단지에서 이 학교에 배정되는 동을 붙인다 | 미지정 |

**사용 예시**

```bash
jibsa naver school B100000747 --complex 개포자이
```

**반환값**

`school_code`, `name`, `address`, `office_of_education`, `operation_type`, `establishment_type`, `opened_at`(개교일), `stats_date`(공시 기준일), `students`, `students_per_class`, `students_per_teacher`, 비교용 `city_average`·`district_average`(지역, 학급당·교원당 학생 수), `url`. `--complex` 를 주면 `complex_number`, `all_dongs_assigned`, `assigned_dongs`(예: `["101동~103동", "105동"]`, 전체 배정이면 `["전체 동"]`)가 붙는다.

**오류와 대응**

없는 학교 코드나 `--complex` 의 없는 단지 번호는 `NOT_FOUND`, 영문·숫자가 아닌 코드는 `INVALID_ARGUMENT`다.

**주의사항**

요청 1회, `--complex` 를 주면 2~3회 추가다 (단지 이름이면 단지 검색 1회, 단지 번호면 빌라 단지인지 확인 1회, 번호로 준 빌라 단지는 단지가 있는지 확인 1회 더). 배정 동 조회에 실패하면 `all_dongs_assigned`·`assigned_dongs` 가 `null` 이다. 전체 배정이 아닌데(`all_dongs_assigned: false`) 네이버가 어느 동인지 주지 않으면 `assigned_dongs` 만 `null` 이다. 일부 동만 배정된 단지와 이 학교에 배정되지 않은 단지가 같은 모양으로 와서 구분할 수 없다 (배정 동이 없다는 뜻도, 일부 배정이라는 뜻도 아니다). 전화·홈페이지·좌표는 내보내지 않는다. 학교 배정은 교육청 학구도 안내로 최종 확인한다.

## 조회 개수와 페이지 처리

검색 모드(`search listings`, `search listings --complex`, `search complexes`, `search redevelopment`, `search listings --redevelopment`) 모두 `--limit` 기본 30, 범위 1~120이다. `complex`·`listing`·`trend`·`market-price`·`redevelopment`·`regions`·`school`에는 `--limit`이 없고, `real-price`는 `--pages` 또는 `--period`를 사용한다.

```bash
jibsa naver search listings 역삼동 --trade 전세 --limit 120
jibsa naver search listings --complex 개포자이 --trade 전세 --limit 60
jibsa naver search complexes 역삼동 -t 오피스텔 --limit 90
```

API 요청당 최대 30건이다. 명령 한 번 안에서 이전 응답의 `lastInfo`와 `seed`를 다음 요청에 넘긴다 (모든 검색 모드). `seed`가 빠지면 랭킹순이 페이지마다 다시 섞여 매물이 겹치거나 빠진다. CLI에 `--offset`·`--cursor`·`--seed` 옵션은 없다.

`--limit`은 들여다볼 건수(조회 할당량)이고, 실제로 받은 개수로 센다. 120건이면 보통 30건씩 네 번 요청한다. 페이지가 덜 차서 오면 남은 몫을 다음 페이지(가까운순은 다음 지도 영역)에서 받고, 결과가 끝나거나 커서가 진행되지 않거나 요청 횟수 상한에 닿으면 멈춘다. 상한에 닿아 멈추면 `notes`로 알린다. 받은 뒤 중복·알 수 없는 거래 유형으로 빠진 결과(가까운순이 아닌 반경 검색은 반경 밖도)는 채우기 위한 추가 조회를 하지 않는다. 검색 조건은 네이버 서버가 걸어 주므로 받은 뒤 다시 거르지 않는다. `returned`가 실제 반환 개수이며 항상 `--limit`과 같지는 않다.

부족한 이유를 확인할 수 있으면 `notes`로 안내한다. 예를 들어 가까운순이 아닌 반경 검색에서 120건을 조회하고 6건이 제외되면 다음처럼 나온다. 반경 밖을 빼지 않는 검색(동 전체·단지·재개발 매물·가까운순)은 "중복이거나 알 수 없는 거래 유형인 매물을 빼고"로 나온다. 네이버 목록에는 거래 상태가 없어 거래 불가로 빼는 매물은 없다.

```json
{
  "notes": [
    "[제외] 중복이거나 알 수 없는 거래 유형 또는 검색 범위(반경) 밖의 매물을 빼고 114건입니다 (뺀 만큼 다시 채우지 않음)",
    "[일부] --limit 의 최대값은 120입니다. 더 보려면 조건·지역을 좁히세요"
  ]
}
```

더 받을 매물이 남지 않았으면 제외 안내 끝이 `(더 받을 매물 없음)` 이다 (단지 목록은 `(더 받을 단지 없음)`).

서버 집계 `total`에는 반경 밖·중복·출력에서 제외된 항목이 포함될 수 있으므로 `returned`와 차이가 난다. 새 검색은 목록·순서가 달라질 수 있다.

## 출력 읽기

공통으로 읽는 법은 [공통 사용 규칙](common.md#반환값을-읽을-때)에 있다. 아래는 실제 매물을 포함하지 않은 **주요 필드 발췌 예시**다. 전체 응답에는 매물의 다른 필드와 `notes` 등이 추가된다.

```json
{
  "total": 1,
  "returned": 1,
  "listings": [
    {
      "id": "1000000001",
      "trade_type": "월세",
      "deposit_manwon": 3000,
      "rent_manwon": 100,
      "complex_number": 100001,
      "pyeong_number": 2
    }
  ]
}
```

| 필드 | 다음에 사용할 곳 |
| --- | --- |
| 매물 `id` | `jibsa naver listing <id>` |
| 단지 `complex_number` | `complex`, `search listings --complex`, `real-price`, `market-price` |
| 학교 `schools[].school_code` | `school` |
| 구역 `redevelopment_number` | `redevelopment`, `search listings --redevelopment` |
| 단지 상세 `pyeongs[].number` | `--pyeong`. 평수가 아니라 평형 ID |
| 지역 검색 `boundary` | 동 경계 안을 검색했다는 표시 |
| 지역 검색 `radius_km` | 중심점 반경으로 검색했다는 표시 |
| `notes` | 범위·일부 반환·정렬·조회 제한 안내 |

단지가 없는 매물은 단지 관련 키가 없을 수 있다. 목록 주소는 동까지이며 번지·방 수 등은 `listing`에서 확인한다.

## 요청 제한

네이버는 세 소스 중 요청 제한이 가장 엄격하다. 정책과 `jibsa limits` 사용법은 [공통 사용 규칙](common.md#요청-제한과-limits)에 있다. 지역명 해석과 상세의 교통·학교·세금 같은 부가 정보 요청도 이 제한에 포함된다.

## 도움말과 이전 명령

```bash
jibsa naver --help
jibsa naver search listings --help
jibsa naver search complexes --help
jibsa naver complex --help
jibsa naver listing --help
jibsa naver real-price --help
jibsa naver market-price --help
jibsa naver redevelopment --help
jibsa naver regions --help
jibsa naver school --help
jibsa naver search redevelopment --help
jibsa naver trend --help
```

| 이전 명령 | 현재 명령 |
| --- | --- |
| `naver search <지역>` | `naver search listings <지역>` |
| `naver complexes <지역>` | `naver search complexes <지역>` |
| `naver items <단지>` | `naver search listings --complex <단지>` |
| `naver item <매물 ID>` | `naver listing <매물 ID>` |

이전 명령의 별칭은 제공하지 않는다.

## 소스별 반환 필드와 해석

[공통 사용 규칙](common.md#반환값을-읽을-때)과 함께 읽는다. 아래 필드는 조회 모드·유형에 따라 제공된다.

| 소스·조회 유형 | 필드 | 뜻 |
| --- | --- | --- |
| 네이버 | `complex_number`, `complex_name`, `dong`, `pyeong_number` | 단지 번호·단지명·동·평형 번호. 단지 번호는 `naver complex`·`naver real-price` 에, 평형 번호는 `real-price --pyeong` 에 넘긴다. 단지가 없는 빌라 등은 키가 없다 |
| 네이버 | `supply_area_m2` | 공급면적 (㎡). 오피스텔은 네이버가 계약면적만 줘서 `null` |
| 네이버 | `contract_area_m2` | 계약면적 (㎡). 오피스텔만 있고 나머지 유형은 키가 없다 |
| 네이버 | `loan_manwon` | 융자금 (만원). `0` 은 융자 없음, `null` 은 모름 |
| 네이버 (`listing`) | `manage_cost_manwon`, `manage_cost_includes` | 월 관리비(만원)와 관리비에 포함된 항목 (공용·전기·수도·가스·난방·인터넷·TV·기타). 항목별로 입력한 매물은 정액 항목을 더한 값이 관리비이고, 실비(쓴 만큼 따로 냄) 항목은 포함 항목에서 빠진다. 그래서 항목이 모두 실비면 `0`, `[]` 이다 (정액 관리비가 없고 공과금은 따로 낸다는 뜻이며 모름이 아니다). 중개사가 관리비를 확인하지 않았으면 둘 다 `null`, 금액만 입력하고 항목을 입력하지 않았으면 `manage_cost_includes` 만 `null` 이다 |
| 네이버 (`listing`) | `parking` | 주차 가능 여부와 총 주차 대수. 예: `"불가 (총 4대)"`, `"가능 (단지 전체 398대)"`. 가능 여부를 주지 않은 매물은 대수만(`"단지 전체 626대"`), 대수를 주지 않은 매물은 가능 여부만 나온다. 대수가 있어도 그 매물은 주차 불가일 수 있다. 단지 매물의 대수는 매물마다 달라 `complex` 의 단지 주차 대수와 다를 수 있다 |
| 네이버 (`listing`) | `move_in` | 입주 가능일. `"즉시입주"`, `"2026-11-27"`, `"2027-02 초순"` (중순·하순도), 협의할 수 있으면 뒤에 `" (협의 가능)"`. 모르면 `null` |
| 네이버 (`listing`) | `nearby_subways`, `bus_routes`, `schools` | 가까운 지하철역 (예: `"대청역 (3호선, 도보 9분)"`, 노선이 여럿이면 `2호선·신분당선`), 주변 정류장의 버스 노선 (종류별, 예: `{"간선": ["146", "341"], "마을": ["강남01"]}`), 배정 초등학교 (`complex` 의 `schools[]` 와 같은 모양, `school_code` 는 `naver school` 에 넣는다). 요청을 1~2회 더 해 붙인다. 학교는 단지·동 번호가 있는 매물(아파트·오피스텔·단지형 빌라)만이고 나머지는 `schools` 키가 없다. 학교 조회에 실패하면 `null`. 네이버에 역·버스 정보가 통째로 없는 매물이나 조회 실패도 `null` 이다 (주변에 역이 없다는 뜻이 아니다) |
| 네이버 (매매만) | `agent_fee_manwon`, `acquisition_tax_manwon`, `property_tax_manwon`, `comprehensive_real_estate_tax_manwon` | 중개보수 상한, 취득세 합계(지방교육세·농특세 포함), 연 재산세 합계, 연 종부세 합계 (만원). 네이버 사이트의 계산값이라 실제와 다를 수 있다 (보유세는 공시가 기준). 매매 매물 상세만 요청 2회를 더 해 붙이고, 전월세에는 키가 없다 |

### 선택 평형 부가 정보 (`complex --pyeong`)

| 필드 | 설명 |
|---|---|
| `pyeong_maintenance_fee` | 월 관리비 (만원): 최근 달(`year_month`, `latest_manwon`), 월평균, 여름·겨울 평균. 자료가 없으면 `null` |
| `market_prices` | 기관별 최신 시세 (한국부동산원, KB부동산, 부동산뱅크): 기준일, 매매 시세 평균·범위, 전세 시세 범위, 전세가율(%). 시세가 없으면 `[]` |
| `real_price_summary` | 최근 3년(`since`) 매매(`sale`)·전세(`jeonse`) 실거래의 평균과 최저·최고 거래 (가격·계약일·층·중개/직거래·해제 여부). 기간 안 거래가 없으면 그 거래 유형이 `null` |

## 매물·시세 해석 시 주의사항

상세 `loan_manwon`이 양수면 융자가 표시된 매물이므로 계약 전에 등기부등본으로 확인한다. `null`은 융자 없음이 아니다. 학교·교통 정보가 `null`인 것도 주변에 학교·역이 없다는 뜻이 아니다.

`complex`의 `market_prices`는 기관 추정 시세다. 기관 이름과 `base_date`를 함께 읽고 실제 거래는 `real_price_summary`·`real-price`로 확인한다. 실거래 요약의 최저가가 직거래(`trade_category`)면 일반 중개 거래와 차이가 날 수 있다. 해제된 거래는 시세 계산에서 제외한다.

목록의 방 구조는 모르는 값이므로 상세의 방 수로 확인한다. 상세 `room_type` 은 방 2개 이상이면 투룸·쓰리룸·포룸이상, 방 1개면 복층형원룸·오픈형원룸·분리형원룸이다. 구조를 모르는 복층이 아닌 방 1개(단지 매물 전부와 구조를 입력하지 않은 매물)는 `room_type` 이 `null` 이고 `room_count` 가 1이다.
