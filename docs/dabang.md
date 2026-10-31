# 다방 CLI 사용법 (`jibsa dabang`)

[설치](../README.md) · [공통 사용 규칙](common.md) · [개발 가이드](development/providers/dabang.md)

> 금액은 **만원**, 면적은 **㎡**다. 다만 매물 검색의 방 크기 조건은 다방이 **평(정수)** 으로만 받는다. 출력 형식·누락값·에러 대응·요청 제한 같은 공통 규칙은 [공통 사용 규칙](common.md)에 있고, 이 문서는 다방에만 있는 내용을 적는다.

## 한눈에 보기

| 명령 | 하는 일 | 무엇을 넣나 | 다음에 쓰는 곳 |
| --- | --- | --- | --- |
| `search locations` | 동·역·대학·단지 후보 찾기 | 이름 | `complex`, `search listings --complex`, `real-price` |
| `search listings room` | 원룸·투룸 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing` |
| `search listings villa` | 주택·빌라 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing`, `real-price --listing` |
| `search listings officetel` | 오피스텔 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing` |
| `search listings apt` | 아파트 매물 찾기 | 동·역 이름 또는 좌표 | `listing` |
| `search complexes` | 아파트·오피스텔 단지 목록 | 동·역·대학 이름 또는 좌표 | `complex`, `search listings --complex`, `real-price`, `price-trend` |
| `complex` | 단지 정보·평형·학교 | 단지 ID | `search listings --complex`, `real-price`, `price-trend`, `school` |
| `school` | 학교 하나: 학급당·교원당 학생 수, 진학률 (학교알리미 공시) | 학교 코드와 `--level` (`complex` 의 `schools[]`) | — |
| `search listings --complex` | 단지 안 매물 | 단지 ID | `listing` |
| `real-price` | 평형별 실거래가 (단지 없는 매물은 그 동의 같은 건물 유형) | 단지 ID 또는 `--listing` | — |
| `price-trend` | 평형 하나의 36달 시세 흐름 | 단지 ID | — |
| `listing` | 매물 하나 상세 | 매물 ID 또는 매물번호 | `nearby` |
| `neighborhood` | 동네정보: 매물 수·거래량·평균가·인구와 순위, 학교·편의·교통·안전 시설 수 | 동 이름 | `popular-listings` |
| `popular-listings` | 동 안 인기 매물 순위 | 동 이름 | `listing` |
| `nearby` | 매물·단지 둘레 지하철역·버스 노선·가까운 시설·학교 | 매물 ID 또는 단지 ID | — |
| `station-prices` | 역 둘레 평균 매물가 (빌라·오피스텔·아파트 × 원룸·투룸) | 역 이름 | `search listings` |
| `search sales` | 분양 단지 목록 (새 아파트·오피스텔 청약) | 동·시군구·역·대학 이름 또는 좌표 | `sale` |
| `sale` | 분양 단지 하나: 일정·평형별 분양가 | 분양 ID | — |
| `sale-schedule` | 날짜별 전국 청약 일정 (7일까지) | 시작 날 | `sale` |
| `trending-complexes` | 전국에서 지금 많이 보는 단지·동 순위 | — | `complex` |
| `trade-rankings` | 전국에서 거래 많은 단지 순위 | — | `complex`, `real-price` |
| `region-ranking` | 시군구·시도·전국 안 동·단지 순위 (평균가·전세가율·신고가, 동은 진학률·학원 수·인구·시설 수도) | 범위 이름 | `complex` |

### 보통 이렇게 이어서 쓴다

```text
지역에서 집 찾기   search listings room / villa / officetel / apt → listing
단지 골라 집 찾기  search locations 또는 search complexes → complex → search listings --complex → listing
                                                             └→ real-price / price-trend
동네 비교하기     neighborhood · station-prices → popular-listings → listing → nearby
                  region-ranking · trending-complexes · trade-rankings → complex
학군 보기         complex → school · region-ranking --by 과학고진학률 / 학원수
분양 보기         search sales 또는 sale-schedule → sale
```

## 옵션 읽는 법

각 표는 현재 CLI 의 인자·옵션·기본값을 기준으로 한다. `미지정`은 그 조건을 걸지 않는다는 뜻이다. 범위는 양 끝을 포함한다. 목록형 옵션은 반복하거나 쉼표로 지정한다. 매물 검색 조건은 모두 다방 서버가 거른다. 다방은 범위 값을 999999 까지만 받는다 (금액은 만원이라 약 100억). 더 큰 상한은 상한 없이 찾고, 더 큰 하한은 `INVALID_ARGUMENT` 다.

```bash
jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
jibsa dabang search listings villa 성수동 --room 투룸 --room 쓰리룸
```

좌표는 `--lat`·`--lng`를 함께 주고 대한민국 좌표를 쓴다. 좌표를 주면 이름 인자는 생략할 수 있다.

## 1. `search locations` — 동·역·대학·단지 후보 찾기

이름 하나로 동·역·대학·단지 후보를 한꺼번에 받는다 (요청 1회).

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·역·대학·단지 이름 (예: 역삼동, 강남역, 홍익대학교, 은마) | 필수 |
| `--limit` | 종류마다 최대 후보 수 범위: 1~50. | 10 |

**사용 예시**

```bash
jibsa dabang search locations 은마
```

**반환값**

`regions`(동: 이름·주소·10자리 법정동코드·중심 좌표), `stations`(역: 노선·다방 역 반경 `radius_m`), `universities`, `complexes`(단지: `complex_id`·이름·유형·주소), `sales`(분양 단지: `sale_id`·이름·상태·주소)를 준다.

**주의사항**

`complexes[].complex_id`(28자리)를 `complex`·`search listings --complex`·`real-price`·`price-trend` 에 넘긴다. 이름이 비슷한 다른 지역 단지도 섞이니 주소로 고른다. 다방은 시·군·구를 따로 주지 않아 `강남구` 를 찾으면 그 안의 동들이 온다.

## 2. `search listings room` — 원룸·투룸 매물 찾기

다방 '원룸·투룸' 목록이다. 원룸은 방 하나짜리를 뜻해 다방이 섞어 주는 오피스텔·아파트(방 1~2개)도 그대로 둔다 (`property_type` 으로 구분). 매매는 없다 (다방이 받지 않는다).

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·역·대학 이름 (예: 역삼동, '강남구 신사동', 강남역, 홍익대학교). --lat/--lng 를 주면 생략 | 미지정 |
| `--lat` / `--lng` | 중심 좌표 (이름 대신) | 미지정 |
| `--radius` | 반경 (km). 주면 반경을 덮는 사각형으로 받고 반경 밖은 뺀다 범위: 0.1~5.0. | 미지정 |
| `--trade` | 거래 유형: 월세, 전세. 반복하거나 쉼표로 구분 | 전체 |
| `--deposit-min` / `--deposit-max` | 보증금·전세금 (만원) | 미지정 |
| `--rent-min` / `--rent-max` | 월세 (만원) | 미지정 |
| `--rent-includes-manage-cost` | 월세 범위를 월세 + 관리비로 본다 | 꺼짐 |
| `--area-pyeong-min` / `--area-pyeong-max` | 방 크기 (평, 정수) | 미지정 |
| `--built-within` | 사용승인 뒤 이 햇수 이내 (년) | 미지정 |
| `--floor` | 층: 1층, 2층이상, 반지하, 옥탑. 반복하거나 쉼표로 구분 (OR) | 전체 |
| `--room` | 방 개수: 원룸, 투룸. 반복하거나 쉼표로 구분 (OR) | 전체 |
| `--condition` | 기타 조건: 주차, 엘리베이터, 단기임대, 분리형, 복층. 반복하거나 쉼표로 구분 (AND) | 미지정 |
| `--limit` | 받을 매물 수 (제외 전) 범위: 1~120. | 24 |
| `--next` | 앞 결과의 `next`. 같은 지역·조건에 주면 받은 매물 다음부터 이어 받는다 | 미지정 |
| `--fields` | 매물마다 낼 필드만 고른다 | 전체 |

**사용 예시**

```bash
jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
jibsa dabang search listings room 강남역 --room 투룸 --condition 주차,엘리베이터
jibsa dabang search listings room 역삼동 --trade 월세 --next <앞 결과의 next>
```

**반환값**

`region`(찾은 위치), `scope`(찾은 범위), `radius_km`(역·좌표·`--radius` 만), `total`, `returned`, `has_more`, `next`(더 있을 때만), `listings` 를 준다. 매물마다 다방 필드 `listing_number`(화면의 매물번호), `short_lease`(월세만), `complex_name`(오피스텔·아파트만)이 붙는다.

**오류와 대응**

`--trade 매매` 는 `INVALID_ARGUMENT` (원룸·투룸에는 매매가 없다). 구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 동 이름이나 `--lat/--lng --radius` 를 쓰라고 알린다. 행정동(`역삼1동`)은 `REGION_NOT_FOUND` 와 법정동 힌트, 같은 이름의 동(`신사동`)은 `REGION_AMBIGUOUS` 와 `candidates` 다. 줄인 대학 이름이 여러 캠퍼스에 맞으면(`연세대`) 첫 곳으로 찾고 `[모호]` 안내에 다른 캠퍼스 이름을 준다. 그 이름을 따옴표로 감싸 그대로 주면(`'연세대학교(원주캠퍼스)'`) 그 캠퍼스로 찾는다. 다른 소스 옵션을 옮겨 쓰면(`--area-min`, `--option`, `--condition 반려동물`) 에러 `hint` 가 다방에서 주는 법이나 다방에 그 조건이 없다는 것을 알린다.

**주의사항**

결과는 **다방 목록 순**이다 (거리순이 아니다). 역·좌표 검색은 `distance_km` 를 주니 가까운 매물이 필요하면 그것으로 고른다. 다방 광고 칸(중개사 추천 매물)은 넣지 않고 `notes` 에 뺀 수를 알린다.

## 3. `search listings villa` — 주택·빌라 매물 찾기

다방 '주택·빌라' 목록이다. 다방이 이 목록의 매물을 방 개수(원룸·투룸)로 표시해 건물 종류를 알 수 없어 `property_type` 은 늘 `"빌라"` 다 (단독·다가구도 포함). 옵션은 `room` 과 같고 `--trade` 에 매매, `--price-min/--price-max`(매매가, 만원)가 더 있다. `--room` 은 원룸, 투룸, 쓰리룸, 포룸이상(4개 이상)이고 `--condition` 은 주차, 엘리베이터, 단기임대다.

```bash
jibsa dabang search listings villa 성수동 --trade 전세 --deposit-max 30000 --room 투룸,쓰리룸
```

## 4. `search listings officetel` — 오피스텔 매물 찾기

다방 '오피스텔' 목록이다. 옵션은 `villa` 와 같고 층(`--floor`) 조건이 없다.

```bash
jibsa dabang search listings officetel 강남역 --trade 월세 --rent-max 100 --condition 주차
```

## 5. `search listings apt` — 아파트 매물 찾기

다방 '아파트' 목록이다 (주상복합·도시형 생활주택 포함). 옵션은 `officetel` 과 같고 `--households-min/--households-max`(단지 세대수)가 더 있으며 `--condition` 은 단기임대만 있다.

```bash
jibsa dabang search listings apt 대치동 --trade 매매 --price-max 300000
jibsa dabang search listings apt 강남역 --trade 전세 --households-min 500
```

다방은 아파트에 동·대학 검색을 주지 않는다. 동 이름은 동 경계를 덮는 사각형으로 받아 그 동 매물만 남기고(경계 요청 1회 추가), 다른 동 매물을 뺀 수를 `notes` 로 알린다. 그래서 `returned` 가 `--limit` 보다 꽤 적을 수 있다 (뺀 만큼 다시 채우지 않는다). 대학 이름은 그 대학 중심 1km 반경으로 찾는다.

다방 목록은 아파트 면적을 **공급면적**으로만 준다. 그래서 아파트 매물은 `area_m2`·`area_pyeong` 이 `null` 이고 공급면적이 `supply_area_m2` 에 있다 (전용면적은 `listing` 상세). `--area-pyeong-min/max` 도 아파트는 공급 평으로 걸린다 (34평 = 공급 약 112㎡).

## 6. `search complexes` — 단지 목록

동·역·대학 둘레의 아파트·오피스텔 단지를 다방 목록 순으로 준다. 조건 없이 그 범위의 단지를 모두 주며 매물이 없는 단지도 나온다.

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·역·대학 이름. --lat/--lng 를 주면 생략 | 미지정 |
| `--type` / `-t` | 단지 유형: 아파트, 오피스텔 | 아파트 |
| `--lat` / `--lng` / `--radius` | 좌표와 반경 (km) | 미지정 |
| `--limit` | 받을 단지 수 (제외 전) 범위: 1~120. | 24 |

```bash
jibsa dabang search complexes 대치동
jibsa dabang search complexes 강남역 -t 오피스텔
```

**반환값**

단지마다 `complex_id`, `name`, `complex_type`, `years`(입주 연차), `household_count`, `address`, `listing_count`·`rent_listing_count`·`lease_listing_count`·`sale_listing_count`(지금 올라온 매물 수), `recent_sale_manwon`·`recent_lease_manwon`(최근 실거래가, 다방이 고른 대표 평형)을 준다. 아파트 동 검색은 매물 검색처럼 동 경계를 덮는 사각형에서 그 동 단지만 남긴다. 아파트 대학 검색은 대학 중심 1km 반경을 덮는 사각형으로 찾고 `[범위]` 로 알린다. 다방이 다음 쪽에 같은 단지를 다시 주기도 해서 한 번만 넣고 `notes` 로 알린다 (다시 채우지 않는다).

## 7. `complex` — 단지 정보

```bash
jibsa dabang complex 58291f830ff9bd73a07ca123c632
```

세대수·동 수·주차 대수(세대당)·최저/최고층·용적률·건폐율·시공사·사용승인일·난방·연료·현관 구조·지금 매물 수, `pyeongs`(평형: `space_seq`, 이름, 전용·공급·계약 면적, 방·욕실 수, 월 관리비 총액), `primary_space_seq`(다방 대표 평형), `area_prices`(이 단지·동·구의 매매·전세 평당 평균가), `recent_sale`·`recent_lease`(최근 실거래 한 건씩: 금액·계약일·층, 거래한 평형 `space_seq` 와 그 전용면적 `area_m2`), `schools`(배정 초등학교와 단지가 든 학교군의 가까운 중·고등학교 2곳씩)를 준다. 요청 2회. 최근 실거래 요약을 받지 못하면 `recent_sale`·`recent_lease` 를 `null` 로 두고 `[실패]` 로 알린다.

`pyeongs[].space_seq` 를 `search listings --complex`·`real-price`·`price-trend` 의 `--pyeong` 에 준다. 평형 이름은 아파트가 공급 평(`"30"`), 오피스텔이 다방 표기(`"13B1"`)다.

`schools[]` 는 `level`(초등학교·중학교·고등학교), `school_code`, `name`, `establishment`(공립·사립), `distance_m`, `district`(초등학교는 배정 통학구역, 중·고등학교는 단지가 든 학교군), `students_per_class`(학급당 학생 수)이고, 중학교는 `special_high_entrants`·`autonomous_high_entrants`(특목고·자율형 진학 인원), 고등학교는 `university_entrants`(대학교 진학 인원)도 있다. 진학률과 시·도 평균 비교는 `school_code`·`level` 을 `school` 에 준다.

## 8. `school` — 학교 하나 상세

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `SCHOOL_CODE` | 학교 코드 (`complex` 의 `schools[].school_code`, 예: `S010000704`) | 필수 |
| `--level` | 초등학교, 중학교, 고등학교 (`schools[].level`). 코드와 맞아야 한다 | 필수 |

```bash
jibsa dabang school S010000704 --level 중학교
```

다방이 보여 주는 학교알리미 공시다. `name`, `establishment`(국공립·사립), `address`, `office_of_education`, `stats_period`(공시 기준, `"2026년 상반기"`), `students_per_class`, `students_per_teacher`, `afterschool_programs`(방과후 프로그램 수, 초등학교는 대개 `null`), 비교용 `city_average`·`district_average`(시·도·시·군·구 평균), `url`(학교알리미 공시 페이지)을 준다. 중·고등학교는 `advancement`(졸업생 진학: `destination`, `count`(명), `percent`(%))도 준다. 중학교는 일반고·특성화고·특목고·자율고와 그 안의 과학고·외국어고·예술체육고(특목고)·자사고(자율고), 고등학교는 대학교·전문대학·국외·취업·기타다. 특목고·자율고 안의 갈래는 다방이 비율만 줘서 `count` 가 `null` 이다. 요청 1회. 전화·홈페이지·좌표는 주지 않는다.

학교 코드는 `complex` 결과에만 있다 (`nearby` 의 학교에는 없다). `--level` 이 코드와 다르거나 없는 코드면 다방이 서버 고장과 같은 500 을 줘서 `UPSTREAM_ERROR`(`status` 500)다. 코드와 단계를 `complex` 결과에서 그대로 옮겼는지 먼저 보고, 맞으면 잠시 후 다시 부른다. 네이버 `school` 의 학교 코드와는 다른 체계라 서로 바꿔 쓰지 못한다.

## 9. `search listings --complex` — 단지 안 매물

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--complex` | 단지 ID (28자리) | 필수 |
| `--pyeong` | 평형 번호(`space_seq`). 반복하거나 쉼표로 구분 (OR) | 전체 평형 |
| `--trade` | 거래 유형: 월세, 전세, 매매 | 전체 |
| `--deposit-min/max`, `--rent-min/max`, `--price-min/max` | 금액 (만원) | 미지정 |
| `--limit` | 받을 매물 수 범위: 1~120. | 24 |

```bash
jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 매매
```

단지 상세 1회 + 24건마다 1회. 단지에 없는 평형 번호는 `INVALID_ARGUMENT` 다.

## 10. `real-price` — 실거래가

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `COMPLEX_ID` | 단지 ID. 단지 없는 매물은 빼고 `--listing` | 미지정 |
| `--listing` | 단지 없는 매물(빌라·주택·원룸)의 매물 ID | 미지정 |
| `--pyeong` | 평형 번호 (단지만) | 다방 대표 평형 |
| `--trade` | 매매, 전월세 (전세·월세를 함께 준다) | 매매 |
| `--years` | 최근 몇 년 (1~3, 다방은 3년까지) | 3 |
| `--limit` | 최대 거래 수 범위: 1~200. | 30 |

```bash
jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --trade 매매
jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --pyeong 817 --trade 전월세 --years 1
jibsa dabang real-price --listing 6abb32f72f9f803f9c6f3830 --trade 전월세
```

`transactions[]` 는 최근 계약 순이고 거래마다 `trade_type`(매매·전세·월세), `trade_date`, `floor`, 금액, `cancelled`(해제된 거래), `direct`(직거래)를 준다. `total` 은 기간 안 거래 수다. `--pyeong` 을 안 주면 대표 평형으로 찾고 `notes` 로 알린다 (단지 상세 요청 1회 추가). 단지에 없는 평형 번호는 `INVALID_ARGUMENT`, 없는 단지는 `NOT_FOUND` 다.

국토부 신고에 평형 타입이 없어 전용면적이 같은 평형끼리는 거래가 거의 모두 겹친다 (헬리오시티 84.98㎡ 평형 둘이 1년 32건 중 31건 같음). 거래가 있으면 `notes` 가 알린다. 평형 여러 개를 합칠 때는 같은 날·층·금액을 한 번만 센다.

`--listing` 은 그 건물의 거래가 **아니라** 그 매물이 있는 동의 같은 건물 유형 거래다 (다방 매물 화면과 같다, `basis` 에 `"역삼동 단독·다가구"` 처럼 범위가 있다). 거래마다 `area_m2` 가 있으니 면적이 비슷한 거래만 견준다. 없는 매물이나 단지 매물(오피스텔·아파트) ID 는 `NOT_FOUND` 다 (단지 매물은 `listing` 결과의 `complex_id` 로 찾는다).

## 11. `price-trend` — 시세 흐름

```bash
jibsa dabang price-trend 58291f830ff9bd73a07ca123c632 --pyeong 817
```

평형 하나의 36달 흐름이다 (요청 1회). `months[]` 는 오래된 달부터 달마다 매매·전세 평균 실거래가와 매매·전세·월세 거래 수다. 거래가 없는 달은 다방이 앞 달 평균을 이어 준다(`sale_count: 0`). 이을 앞 달 평균도 없으면(그때까지 거래가 없던 평형) 평균은 `null` 이다. `sale_average_manwon`·`lease_average_manwon`(최근 평균), `lease_rate_percent`(전세가율), `gap_manwon`(매매 − 전세), `sale_1y`·`sale_3y`·`lease_1y`·`lease_3y`(최고·최저)도 준다. 단지에 없는 평형 번호는 `INVALID_ARGUMENT` 다.

## 12. `listing` — 매물 하나 상세

```bash
jibsa dabang listing 6abb32f72f9f803f9c6f3830
jibsa dabang listing 59136486
```

검색 결과의 `id`(24자리) 또는 다방 화면의 매물번호(`listing_number`)를 받는다 (매물번호면 요청 1회 추가). 가격·관리비(`manage_cost_includes`: 관리비에 든 항목. 정액 관리비가 10만원 이상인 매물은 항목마다 정액·실비로 나뉘어 와서 정액 항목만 넣고 실비로 따로 내는 전기·수도 등은 빠진다)·전용/공급면적·층/건물 층수·방향과 기준(`direction_criterion`)·입주 가능일·주차(총 대수)·엘리베이터·옵션·보안 시설(`safety`)·난방·건물 용도(`residence_type`)·융자(`loan`)·등록일·사용승인일을 준다. 단기임대를 받는 월세 매물은 `short_lease_term`(예: `"1개월(이상 협의가능)"`), 오피스텔·아파트는 `complex_id` 가 붙는다. 상세의 `property_type` 은 다방 표시대로 `"오피스텔(분리형)"`·`"원룸(분리형,복층)"` 처럼 구조가 붙기도 한다. 에어컨은 `options` 에 `"벽걸이형 에어컨"`·`"스탠드형 에어컨"`·`"천장형 에어컨"` 으로 나온다. 다방이 공급면적을 0 으로 주는 오피스텔은 `supply_area_m2` 가 `null` 이다.

없는 매물·비공개·계약 완료는 `LISTING_UNAVAILABLE` 이다.

## 13. `neighborhood` — 동네정보

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 법정동 이름 (예: 역삼동, '강남구 신사동') | 필수 |
| `--topic` | 주제: 매물, 거래, 시세, 인구, 학교, 편의, 교통, 안전. 반복하거나 쉼표로 구분 | 전체 |

```bash
jibsa dabang neighborhood 역삼동
jibsa dabang neighborhood 역삼동 --topic 매물,인구,학교
```

다방 '동네정보' 화면의 숫자다. 주제마다 요청 1회 (전부면 위치 찾기와 합쳐 9회). `base_month` 는 다방 집계 기준 달이다.

| 주제 | 필드 | 내용 (출처) |
| --- | --- | --- |
| 매물 | `listings` | 지금 다방에 올라온 매물 수: 합계, 주택/빌라·오피스텔·아파트별 월세·전세·매매 수, 순위 (다방) |
| 거래 | `trades` | 거래량: 같은 모양 (국토교통부 신고 기준) |
| 시세 | `prices` | 아파트·오피스텔 평균 매매가·전세가 (만원, 국토교통부 실거래 기준)와 순위 |
| 인구 | `population` | 인구·남녀·연령대(수와 %)와 순위 (행정안전부) |
| 학교 | `schools` | 학교 종류별 설립 구분 수(`{"초등학교": {"국공립": 2}}`)와 학원 종류별 수(`"학원"`) |
| 편의 | `amenities` | 생활편의·의료·외식·쇼핑·체육 시설 수 (`{"생활편의시설": {"편의점": 204}}`) |
| 교통 | `transport` | 지하철역·버스정류장·주차장·주유소·전기차 충전소·차량관리 시설 수 |
| 안전 | `safety` | CCTV·가로등·지구대·119안전센터·공사현장 수 |

`rank` 는 `national`(전국)·`state`(시·도 안)·`district`(시·군·구 안) 순위이고 1 이 가장 많거나 높다. 고르지 않은 주제는 키가 없다. 동 하나만 받는다: `성수동` 처럼 `○가` 로 나뉜 동은 `REGION_AMBIGUOUS` 로 `성수동1가` 처럼 하나를 고르게 하고, 역·대학 이름은 `INVALID_ARGUMENT` 다.

## 14. `popular-listings` — 동 안 인기 매물

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 법정동 이름 | 필수 |
| `--type` / `-t` | 매물 유형: 빌라, 오피스텔, 아파트 | 전체 |
| `--trade` | 거래 유형: 월세, 전세, 매매 | 전체 |
| `--limit` | 받을 매물 수 범위: 1~100. | 20 |
| `--fields` | 매물마다 낼 필드만 고른다 | 전체 |

```bash
jibsa dabang popular-listings 역삼동 -t 빌라,오피스텔 --trade 월세 --limit 10
```

다방 선호도(조회수·찜수·문의수를 합친 점수) 높은 순이고 매물마다 `rank`(1 이 가장 높다)가 붙는다. 50건마다 요청 1회. `total` 은 고른 유형·거래 유형에서 순위가 있는 매물 수다. 매물 필드는 `search listings` 와 같고, 유형을 하나만 고르면 그 유형으로 `property_type` 을 붙인다. 여럿이면 다방 표시대로 오피스텔·아파트이고, 방 개수(원룸·투룸)로 표시된 주택·빌라 매물은 `"빌라"` 다.

## 15. `nearby` — 매물·단지 둘레

```bash
jibsa dabang nearby 6abb32f72f9f803f9c6f3830
jibsa dabang nearby 58291f830ff9bd73a07ca123c632
```

매물 ID(24자리)나 단지 ID(28자리)를 받는다 (요청 2회, 매물번호는 받지 않는다). `stations`(1km 안 지하철역: 노선·거리), `bus_route_count`(500m 안 정류장을 지나는 버스 노선 수), `nearest`(종류마다 가장 가까운 시설. 다방이 주는 종류가 달라 매물은 버스정류장·편의점·카페·은행·공공기관·경찰, 단지는 버스정류장·마트·편의점·은행·약국·경찰), `schools`(가장 가까운 어린이집·유치원·초·중·고등학교)를 준다. 거리는 직선 거리(m)다. 다방이 범위 안에서 찾지 못한 종류는 목록에 없다. `schools` 는 가까운 학교이지 배정 학교가 아니다 (단지의 배정 초등학교는 `complex` 의 `schools`).

## 16. `station-prices` — 역 둘레 평균 매물가

```bash
jibsa dabang station-prices 강남역
```

다방 화면의 '평균 매물가'다. 실거래가가 **아니라** 지금 다방 역 반경(`radius_m`, 강남역 750m) 안에 올라온 원룸·투룸 목록 매물(방 1~2개)의 평균이다. `prices[]` 는 건물 유형(빌라·오피스텔·아파트) × 방(원룸·투룸)마다 `lease_average_manwon`(전세 평균), `rent_deposit_average_manwon`·`rent_average_manwon`(월세 평균 보증금·월세)이다. 다방이 그 유형 × 방 칸을 주지 않으면 `prices` 에 그 칸이 없고(홍대입구역은 오피스텔 투룸·아파트 투룸이 없다), 칸은 있는데 그 거래 매물이 없으면 그 값만 `null` 이다. 쓰리룸 이상은 다방이 주지 않는다. 요청 2회 (역 찾기 + 지도 집계). 역 이름이 아니면 `INVALID_ARGUMENT` 다.

## 17. `search sales` — 분양 단지 목록

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·시군구·역·대학 이름 (예: 역삼동, 강남구, '성남시 분당구', 강남역). --lat/--lng 를 주면 생략 | 미지정 |
| `--lat` / `--lng` / `--radius` | 좌표와 반경 (km, 역·대학·좌표 둘레) 범위: 0.1~5.0. | 1km |
| `--type` / `-t` | 건물 유형: 아파트, 오피스텔, 도시형생활주택, 지식산업센터 | 전체 |
| `--state` | 분양 상태: 분양예정, 접수중, 접수마감, 입주예정, 입주모집 | 전체 |
| `--supply` | 공급 유형: 공공분양, 민간분양, 공공임대, 민간임대 | 전체 |
| `--limit` | 받을 단지 수 (제외 전) 범위: 1~120. | 24 |

```bash
jibsa dabang search sales 강남구 --state 분양예정,접수중
jibsa dabang search sales 강남역 --radius 3 -t 아파트
```

단지마다 `sale_id`, `name`, `state`, `building_type`, `supply_type`, `address`, `household_count`, `price_kind`(분양가·보증금), `price_manwon`(다방 대표 가격, 없으면 `null`), `next_schedule`(다음 일정 글)을 준다. 다방 분양 목록은 지도 범위(사각형)만 받는다. 동·시군구는 경계를 덮는 사각형으로 받아 주소가 그 동·시군구인 단지만 남기고(경계 요청 1회 추가), 역·대학·좌표는 반경을 덮는 사각형 그대로다 (분양 칸에 좌표가 없어 반경 밖을 뺄 수 없다). 시·도·전국과 구가 있는 시(`성남시`)는 `REGION_NOT_SUPPORTED`, 여러 시·도에 있는 시·군·구 이름(`중구`)은 `REGION_AMBIGUOUS` 다 (`'서울 중구'` 처럼 시·도를 붙인다). 시·군·구 이름에 `--radius` 를 주면 `INVALID_ARGUMENT` 다 (시·군·구는 그 경계 안 전체를 찾는다). `광주시` 는 경기도 광주시이고 옛 광주광역시는 구 이름(`광산구`, `광주시 광산구`)으로 준다.

## 18. `sale` — 분양 단지 하나

```bash
jibsa dabang sale 6a7a774cf962bc11cafe5cd6d0f1
```

상태, 건물·공급 유형, 지번·도로명 주소, 총·분양 세대수, 동 수·층수, `builder`(시공사)·`developer`(시행사), `price_min_manwon`·`price_max_manwon`·`price_per_pyeong_manwon`, `move_in`(입주 예정 `YYYY-MM`), 규제 지역·분양가 상한제·전매 가능(모르면 `null`), `schedules`(모집공고·특별공급·1·2순위 청약·당첨자발표·계약기간·입주예정일의 `start`·`end`, 달만 알면 `YYYY-MM`. 하루짜리는 `end` 가 `start` 와 같고, 모집공고·당첨자발표·입주예정일처럼 한 시점인 단계는 `end` 키가 없다), `pyeongs`(평형별 전용·공급 면적·세대수·분양가), `notice_url`(입주자 모집공고), `applyhome_url`(청약홈)을 준다. 상담 전화는 주지 않는다. 요청 1회.

## 19. `sale-schedule` — 날짜별 청약 일정

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--from` | 시작 날 (YYYY-MM-DD) | 오늘 (한국 날짜) |
| `--days` | 며칠 범위: 1~7. (다방은 7일까지) | 7 |
| `--region` | 시·도 (서울, 경기, 충청북도 …). 일정 글의 시·도로 jibsa 가 거른다. 시·군·구는 `INVALID_ARGUMENT` | 전국 |
| `--limit` | 최대 일정 수 범위: 1~300. | 50 |

```bash
jibsa dabang sale-schedule --region 서울
```

`schedules[]` 는 날마다 `kind`(접수·발표 등), `region`, `text`('[청약접수] 서울 [임의공급] 마곡스카이온 (~10/28)'), `sale_id` 다. `region` 은 일정 글 앞의 시·도이고, 글이 시·도 없이 시나 단지 이름으로 시작하면(`'익산 부송에코르 …'`) `null` 이다. `--region` 을 주면 이 일정은 지역을 몰라 빼고 `notes` 로 수를 알린다. `total` 은 `--region` 으로 거르기 전 기간 안 일정 수다. 요청 1회.

## 20. `trending-complexes` — 지금 많이 보는 단지·동

| 옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--type` / `-t` | 아파트, 오피스텔 | 아파트 |
| `--period` | 방금전, 어제, 지난주, 지난달 | 방금전 |
| `--unit` | 단지, 동 | 단지 |
| `--limit` | 범위: 1~50. | 20 |

전국 단위다 (지역으로 좁히지 못한다). `rankings[]` 는 `rank`, 단지면 `complex_id`·`name`·`address`, 동이면 `name`·`address`(시·도)·`legal_division_code`, `view_count`(기간 안 다방 조회 수), `change`(앞 기간 대비 `상승 2`·`하락 1`·`유지`·`신규`)다. `base_period` 는 다방이 센 기간이다. 요청 1회.

## 21. `trade-rankings` — 거래 많은 단지

| 옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--type` / `-t` | 아파트, 오피스텔 | 아파트 |
| `--trade` | 매매, 전세 | 매매 |
| `--period` | 이번주, 지난주, 이번달, 지난달, 올해 | 이번주 |
| `--limit` | 범위: 1~50. | 20 |

전국에서 기간 안 실거래(국토교통부 신고)가 많은 단지다. `rankings[]` 는 `rank`, `complex_id`, `name`, `trade_count`, `years`(입주 연차), `household_count`, `address` 다. 이번주·이번달·올해가 비면 기간이 막 시작돼 아직 세지 않았을 수 있다는 `[참고]` 와 함께 지난 기간(`--period 지난주` 등)을 권한다. 요청 1회.

## 22. `region-ranking` — 범위 안 동·단지 순위

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `SCOPE` | 시·군·구(강남구, '성남시 분당구'), 시·도(서울), 전국 | 필수 |
| `--by` | 부동산(동·단지): 평균가, 평당가, 거래량, 매물수, 시세증감, 최고가증감, 선호도, 세대수, 연식, 전세가율(단지만), 갭가격(단지만). 동네정보(동만): 과학고진학률, 외국어고진학률, 자사고진학률, 예술체육고진학률, 대학교진학률, 전문대학진학률, 학원수, 초등학교수, 중학교수, 고등학교수, 유치원수, 어린이집수, 인구, 인구증감, 생활편의시설, 의료시설, 외식시설, 대형쇼핑시설, 체육시설, 교통시설, 주차시설, 주유시설, 차량관리시설, 안전시설, 안전기관, 불편요소 | 필수 |
| `--unit` | 동, 단지 (동네정보 항목은 동만) | 동 |
| `--type` / `-t` | 아파트, 오피스텔 (부동산 항목만. 세대수·연식과 동네정보 항목에 주면 INVALID_ARGUMENT) | 아파트 |
| `--trade` | 평균가·평당가·시세증감·최고가증감은 매매·전세 중 하나, 거래량·매물수·선호도는 매매·전세·월세 여럿. 동네정보 항목은 받지 않는다 | 매매 / 전체 |
| `--kind` | 동네정보 항목의 종류 하나 (아래 표) | 전체 (학원수는 입시) |
| `--order` | 높은순, 낮은순 | 높은순 |
| `--limit` | 범위: 1~100. (부동산 50곳, 동네정보 30곳마다 요청 1회) | 20 |

| `--by` | `--kind` |
| --- | --- |
| 학원수 | 입시, 예체능, 외국어, 특성화, 종합, 인문사회, 코딩 (늘 하나를 보낸다) |
| 초등학교수·중학교수·고등학교수·유치원수 | 국공립, 사립 |
| 어린이집수 | 공공, 민간, 가정, 직장, 협동 |
| 생활편의시설 | 편의점, 세탁소, 헬스장, 공원, 도서관 |
| 의료시설 | 병원, 의원, 약국, 응급의료센터 |
| 외식시설 | 음식점, 카페, 주점 |
| 대형쇼핑시설 | 대형마트, 백화점, 복합쇼핑몰 |
| 체육시설 | 수영장, 테니스장, 암벽장, 골프장, 축구장, 야구장, 당구장, 체육관, 기타 |
| 교통시설 | 지하철, 버스 |
| 주차시설 | 공영, 민영 |
| 주유시설 | 주유소, 전기차충전소 |
| 차량관리시설 | 자동차수리점, 세차장, 타이어전문점 |
| 안전시설 | CCTV, 가로등 |
| 안전기관 | 경찰서, 지구대파출소, 치안센터, 소방서, 119안전센터 |
| 불편요소 | 공사현장, 소음구역 |

```bash
jibsa dabang region-ranking 강남구 --by 평균가
jibsa dabang region-ranking 서울 --by 전세가율 --unit 단지 --limit 10
jibsa dabang region-ranking 강남구 --by 최고가증감 --unit 단지
jibsa dabang region-ranking 강남구 --by 과학고진학률
jibsa dabang region-ranking 서울 --by 학원수 --kind 입시 --limit 10
```

다방 '부동산 랭킹'과 '동네정보' 랭킹이다. 금액·거래량은 국토교통부 실거래, 매물수·선호도(조회수·찜수·문의수 등을 합친 점수)는 다방, 진학률은 학교알리미 공시(그 동 학교 졸업생 중 그 학교로 간 비율), 인구는 행정안전부 기준이다. `rankings[]` 는 `rank`, `name`, `area`(상위 지역), 단지면 `complex_id`, `value_text`(다방 표시 값)와 항목에 맞는 값만 있다: 평균가·평당가·갭가격 `value_manwon`, 거래량·매물수·세대수·학교·학원·시설 수·인구 `count`, 전세가율·진학률 `percent`, 선호도 `score`, 시세증감·최고가증감 `change_manwon`(오른 금액, 현재가가 아니다)·`change_percent`·`prev_price_manwon`(앞 시세·앞 최고가), 인구증감 `count`(올해 인구)·`prev_count`·`change_count`(줄면 음수)·`change_percent`, 연식 `age_years`. 최고가증감은 `prev_price_date`(앞 최고가 달)도 주고 새 최고가는 `prev_price_manwon + change_manwon` 이다. 단지 순위는 `pyeong`(평형), `price_date`(기준 달, 최고가증감은 새 최고가 달), `price_detail`('매매 90억 / 전세 14.5억')도 준다. 시세증감·최고가증감 동 순위는 다방이 센 달을 `base_month`(YYYY-MM)로, 고른 종류는 `kind` 로 알린다. 다방이 값을 `'-'` 로 주는 줄(거래·매물이 없는 동·단지)은 `value_text` 가 `"-"` 이고 그 항목의 값 필드는 `null` 이다.

학원수·진학률 순위는 `area` 가 시·도(`"서울"`)까지만 와서 범위가 전국·시·도면 같은 이름의 동(신사동)을 구별하지 못한다 (`[참고]` 로 알린다). 범위 찾기에 요청 1~2회가 더 든다. 구가 있는 시(`성남시`)는 구 이름을 붙이라고 `REGION_NOT_SUPPORTED`, 여러 시·도에 있는 시·군·구 이름(`중구`·`고성군`)은 시·도를 붙이라고(`'서울 중구'`) `REGION_AMBIGUOUS` 로 알린다. `광주시` 는 경기도 광주시이고 전남광주통합특별시는 `광주`·`전남광주` 로 준다.

## 검색 범위

| 입력 | room · villa · officetel | apt |
| --- | --- | --- |
| 동 이름 | 그 동 안 (`scope: "역삼동 안"`) | 동 경계를 덮는 사각형에서 그 동 매물만 |
| `○동N가` 로만 나뉜 동 (성수동) | 1가·2가를 합쳐 찾는다 (`--limit` 을 동마다 나누고, 덜 오면 남은 몫을 매물이 남은 다른 동이 받는다. 동이 `--limit` 보다 많으면 몫이 없는 동은 `next` 로 넘기고 `total` 은 `null`) | 경계를 합친 사각형에서 그 동들 매물만 |
| 역 이름 | 다방이 정한 역 반경 (강남역 750m, `radius_km` 에 있다) | 같음 |
| 대학 이름 | 다방 대학 검색 범위 | 대학 중심 1km 반경 |
| `--lat/--lng` | 반경 1km | 같음 |
| `--radius` | 이름의 중심에서 그 반경 (`○가` 로 나뉜 동은 동 중심들의 가운데) | 같음 |

반경은 반경을 덮는 사각형으로 받아 반경 밖을 빼고 뺀 수를 `notes` 로 알린다. 이때와 아파트 동 검색의 `total` 은 사각형 안의 수라 근사값이다. 매물 좌표는 다방이 몇 m 흔든 값이라 반경 경계 근처는 조금 다를 수 있다. 구·시 이름은 찾지 못한다 (`REGION_NOT_SUPPORTED`).

## 조회 한도

매물 검색(`room`·`villa`·`officetel`·`apt`·`--complex`)의 `--limit` 은 기본 24·최대 120이다. 다방은 한 번에 24건씩 주므로 요청은 24건마다 1회다. 받은 원본 수로 조회 예산을 세고, 받은 뒤 뺀 매물(반경 밖·다른 동·광고)만큼 다시 채우지 않는다. `total`·`has_more` 는 다방이 센 값이라 `next` 로 끝까지 이어 받을 수 있다. `search complexes` 는 기본 24·최대 120이고 매물 검색처럼 받은 단지 수로 센다 (아파트 동 검색에서 뺀 다른 동 단지만큼 다시 채우지 않는다). `real-price` 는 기본 30·최대 200(50건마다 1회)이다.

가격 조건만 주고 `--trade` 를 생략하면 그 금액이 있는 거래로 좁히고 `notes` 로 알린다 ([공통 규칙](common.md#출력-규칙)).

## 출력 읽기

| 필드 | 용도 |
| --- | --- |
| 매물 `id` | `listing`·`real-price --listing` 에 그대로 전달 |
| `listing_number` | 다방 화면의 매물번호. `listing` 에 `id` 대신 줄 수 있다 |
| `complex_id` | `complex`·`search listings --complex`·`real-price`·`price-trend` |
| `pyeongs[].space_seq` | 평형 조건 `--pyeong` |
| `schools[].school_code` · `level` | `school` 의 학교 코드와 `--level` |
| `scope` · `radius_km` | 찾은 범위 |
| `notes` | 범위·제외·일부 안내 |
| `url` | 원 사이트(다방 지도 화면)에서 확인·문의 |

## 소스별 반환 필드와 해석

| 조회 | 필드 | 뜻 |
| --- | --- | --- |
| 매물 목록 | `short_lease` | 단기임대(1개월 이상) 계약도 받는 월세 매물. 다방의 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는 표시라 `trade_type` 은 `"월세"` 다. 보증금이 월세 한두 달치(예: 95/95)면 단기 계약 가격일 수 있다. 월세가 아니면 키가 없다 |
| 매물 목록 | `address` | 찾은 동의 매물은 시·구까지, 그 밖의 매물은 동 이름만이다. 그래서 동 이름에 `--radius` 를 주면 둘이 섞이고, 역·대학·좌표로 찾으면 모두 동 이름만이다. 시·구까지는 `listing` 상세 |
| 매물 목록 | `area_m2`·`supply_area_m2` | 아파트(아파트 목록·단지 매물·인기 매물, 원룸·투룸 목록에 섞인 아파트)는 다방이 공급면적만 줘서 `area_m2` 가 `null` 이고 `supply_area_m2` 가 공급면적이다. 그 밖은 `area_m2` 가 전용면적이고 `supply_area_m2` 키가 없다 |
| 매물 목록 | `floor` | `"5"`, `"반지하"`, `"저층"`·`"중층"`·`"고층"` (다방이 층을 숨긴 매물) |
| 매물 목록 | `room_type` | 다방이 투룸·쓰리룸으로 밝힐 때만. 원룸은 오픈형·분리형을 알 수 없어 `null` |
| 매물 목록·상세 | `manage_cost_manwon` | 목록은 다방 표시('관리비 7만')를 읽은 값이고 `0` 은 관리비 없음, `null` 은 모름이다 |
| 상세 | `residence_type` | 건축물 용도 (`"단독주택"`, `"공동주택"` ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다 |

## 매물 해석 시 주의사항

다방은 웹에서 중개 매물만 보여 준다 (직거래 없음). 원룸·투룸 목록에는 오피스텔·아파트(방 1~2개)가 섞이고, 아파트 목록에는 다방이 아파트로 분류한 주상복합·도시형 건물이 섞인다. 다방의 분류를 다시 거르지 않으니 `property_type`·`complex_name`·상세의 `residence_type` 으로 본다.

`short_lease: true` 매물은 같은 지역 월세의 절반을 넘기도 한다 (역삼동 원룸 월세에서 약 2/3). 보증금이 아주 낮은 월세는 단기 계약 가격일 수 있으니 `listing` 상세의 `short_lease_term` 과 원 사이트에서 장기 계약 조건을 확인한다.
