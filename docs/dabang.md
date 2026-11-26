# 다방 CLI 사용법 (`jibsa dabang`)

[설치](https://github.com/Rukkakka/jibsa/blob/main/README.md) · [공통 사용 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md) · [개발 가이드](https://github.com/Rukkakka/jibsa/blob/main/docs/development/providers/dabang.md)

> 금액은 **만원**, 면적은 **㎡**다. 다만 매물 검색의 방 크기 조건은 다방이 **평(정수)** 으로만 받는다. 출력 형식·누락값·에러 대응·요청 제한 같은 공통 규칙은 [공통 사용 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md)에 있고, 이 문서는 다방에만 있는 내용을 적는다.

## 한눈에 보기

| 명령 | 하는 일 | 무엇을 넣나 | 다음에 쓰는 곳 |
| --- | --- | --- | --- |
| `search locations` | 동·역·대학·단지 후보 찾기 | 이름 | `complex`, `search listings --complex`, `real-price` |
| `search listings room` | 원룸·투룸 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing` |
| `search listings villa` | 주택·빌라 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing`, `real-price --listing` |
| `search listings officetel` | 오피스텔 매물 찾기 | 동·역·대학 이름 또는 좌표 | `listing` |
| `search listings apt` | 아파트 매물 찾기 | 동·역 이름 또는 좌표 | `listing` |
| `search complexes` | 아파트·오피스텔 단지 목록 | 동·역·대학 이름 또는 좌표 | `complex`, `search listings --complex`, `real-price`, `price-trend` |
| `complex` | 단지 정보·평형·대출 비율 50% 제한 지역 여부·학교·어린이집·유치원 | 단지 ID | `search listings --complex`, `real-price`, `price-trend`, `nearby-complexes`, `school` |
| `school` | 학교·유치원·어린이집 하나의 공시: 학교는 학급당·교원당 학생 수와 진학률, 유치원·어린이집은 원아 구성·교사 수·운영 시간 | 코드와 `--level` (`complex` 의 `schools[]`·`nurseries[]`·`kindergartens[]`, `search schools`) | — |
| `search schools` | 동 안 학교·유치원·어린이집 목록 | 동 이름과 `--level` | `school` |
| `search listings --complex` | 단지 안 매물 (다방 웹 정렬: 랭킹순·가격순·면적순·최신순) | 단지 ID | `listing` |
| `real-price` | 평형별 실거래가 (단지 없는 매물은 이 집 또는 그 동의 같은 건물 유형) | 단지 ID 또는 `--listing` | — |
| `price-trend` | 평형 하나의 36달 시세 흐름 | 단지 ID | — |
| `nearby-complexes` | 평형대 평당가 (이 단지·동·구)와 반경 1km 주변 단지의 평당가 | 단지 ID | `complex` |
| `listing` | 매물 하나 상세 | 매물 ID 또는 매물번호 | `nearby` |
| `neighborhood` | 동네정보: 매물 수·거래량·평균가·인구와 순위, 학교·편의·교통·안전 시설 수 (`--ranks` 면 그 순위도) | 동 이름 | `popular-listings` |
| `hot-places` | 동 안 미쉐린·블루리본 식당 | 동 이름 | — |
| `popular-listings` | 동 안 인기 매물 순위 | 동 이름 | `listing` |
| `nearby` | 매물·단지·분양 둘레 지하철역·버스 노선·가까운 시설·학교 (`--with` 로 반려동물 장소·카셰어링) | 매물 ID 또는 단지 ID, 분양은 `--sale <분양 ID>` | — |
| `station-prices` | 역 둘레 평균 매물가 (빌라·오피스텔·아파트 × 원룸·투룸) | 역 이름 | `search listings` |
| `search sales` | 분양 단지 목록 (새 아파트·오피스텔 청약) | 동·시군구·시도 이름, `전국`, 역·대학 이름 또는 좌표 | `sale`, `nearby --sale` |
| `sale` | 분양 단지 하나: 일정·평형별 분양가·청약 결과 | 분양 ID | — |
| `sale-schedule` | 날짜별 전국 청약 일정 (7일까지, `--details` 면 주소·가격도) | 시작 날 | `sale` |
| `trending-complexes` | 전국에서 지금 많이 보는 단지·동 순위 | — | `complex` |
| `trade-rankings` | 전국에서 거래 많은 단지 순위 | — | `complex`, `real-price` |
| `region-ranking` | 시군구·시도·전국 안 동·단지 순위, 동 안 단지 순위 (평균가·전세가율·신고가·거래증감·매물증감, 동은 빌라 매물 수·진학률·학원 수·인구·시설 수도) | 범위 이름 | `complex` |

### 보통 이렇게 이어서 쓴다

```text
지역에서 집 찾기   search listings room / villa / officetel / apt → listing
단지 골라 집 찾기  search locations 또는 search complexes → complex → search listings --complex → listing
                                                             └→ real-price / price-trend / nearby-complexes
동네 비교하기     neighborhood · hot-places · station-prices → popular-listings → listing → nearby
                  region-ranking · trending-complexes · trade-rankings → complex
학군 보기         complex 또는 search schools → school · region-ranking --by 과학고진학률 / 학원수
분양 보기         search sales 또는 sale-schedule → sale
                  search sales → nearby --sale
```

## 옵션 읽는 법

각 표는 현재 CLI 의 인자·옵션·기본값을 기준으로 한다. `미지정`은 그 조건을 걸지 않는다는 뜻이다. 범위는 양 끝을 포함한다. 목록형 옵션은 반복하거나 쉼표로 지정한다. 매물 검색 조건은 모두 다방 서버가 거른다. 다방은 범위 값을 999999 까지만 받는다 (금액은 만원이라 약 100억). 더 큰 상한은 상한 없이 찾고, 더 큰 하한은 `INVALID_ARGUMENT` 다.

```bash
jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
jibsa dabang search listings villa 성수동1가 --room 투룸 --room 쓰리룸
```

좌표는 `--lat`·`--lng`를 함께 주고 대한민국 좌표를 쓴다. 좌표를 주면 이름 인자는 생략할 수 있다.

## 1. `search locations` — 동·역·대학·단지 후보 찾기

이름 하나로 동·역·대학·단지 후보를 한꺼번에 받는다 (요청 1회).

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·역·대학·단지 이름 (예: 역삼동, 강남역, 홍익대학교, 은마) | 필수 |
| `--limit` | 종류마다 최대 후보 수 범위: 1~50. (다방은 종류마다 50곳까지 준다) | 10 |

**사용 예시**

```bash
jibsa dabang search locations 은마
```

**반환값**

`regions`(동: 이름·주소·10자리 법정동코드·중심 좌표), `stations`(역: 노선·다방 역 반경 `radius_m`), `universities`, `complexes`(단지: `complex_id`·이름·유형·주소), `presales`(분양 단지: `presale_id`·이름·상태·주소)를 준다.

**주의사항**

`complexes[].complex_id`(28자리)를 `complex`·`search listings --complex`·`real-price`·`price-trend`·`nearby-complexes` 에 넘긴다. 이름이 비슷한 다른 지역 단지도 섞이니 주소로 고른다. 다방은 시·군·구를 따로 주지 않아 `강남구` 를 찾으면 그 안의 동들이 온다. 후보는 다방 순서 그대로 종류마다 앞 `--limit` 곳이고, 다방이 그보다 많이 준 종류가 있으면 `notes` 에 `[일부] 종류마다 다방 순서로 앞 10곳만 보여 줍니다 (동 50곳 중 10곳, …)` 처럼 알린다. 더 보려면 `--limit` 을 늘린다 (최대 50).

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
| `--area-pyeong-min` / `--area-pyeong-max` | 방 크기 (평, 정수). 다방 '매물유형별 기준면적' 으로 걸어 결과 `area_m2`(전용)와 기준이 다를 수 있다 | 미지정 |
| `--built-within` | 사용승인 뒤 이 햇수 이내 (년). 다방은 연도로 세어 10 이면 10년 전 해의 1월 1일 이후 승인 | 미지정 |
| `--floor` | 층: 1층, 2층이상, 반지하, 옥탑. 반복하거나 쉼표로 구분 (OR) | 전체 |
| `--room` | 방 개수: 원룸, 투룸. 반복하거나 쉼표로 구분 (OR) | 전체 |
| `--condition` | 기타 조건: 주차, 엘리베이터, 단기임대, 분리형, 복층. 반복하거나 쉼표로 구분 (AND). 단기임대는 다방이 월세 매물에만 걸어, 주면 월세만 찾고 `notes` 로 알린다 (`--trade` 에 월세가 없으면 입력 오류) | 미지정 |
| `--limit` | 받을 매물 수 (제외 전) 범위: 1~120. | 24 |
| `--next` | 앞 결과의 `next`. 같은 지역·조건에 주면 받은 매물 다음부터 이어 받는다 (`--limit`·`--details`·`--fields` 는 바꿀 수 있다) | 미지정 |
| `--details` | 매물마다 상세를 1회씩 더 받아 사용승인일(`approved_date`)과 건물 용도(`residence_type`)를 붙인다. 사용승인일을 날짜로 읽지 못하면 `null` 이고 `[참고]` 가 원래 글자를 알린다. 요청이 매물 수만큼 늘어난다 (앞 30건) | 꺼짐 |
| `--fields` | 매물마다 낼 필드만 고른다 | 전체 |

**사용 예시**

```bash
jibsa dabang search listings room 역삼동 --trade 월세 --deposit-max 1000 --rent-max 70
jibsa dabang search listings room 강남역 --room 투룸 --condition 주차,엘리베이터
jibsa dabang search listings room 역삼동 --trade 월세 --next <앞 결과의 next>
```

**반환값**

`region`(찾은 위치), `scope`(찾은 범위), `radius_km`(역·좌표·`--radius` 만), `total`, `returned`, `has_more`, `next`(더 있을 때만), `listings` 를 준다. 매물마다 다방 필드 `listing_number`(화면의 매물번호), `short_term`(월세만), `complex_name`(오피스텔·아파트만)이 붙는다.

**오류와 대응**

`--trade 매매` 는 `INVALID_ARGUMENT` (원룸·투룸에는 매매가 없다). 구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 동 이름이나 `--lat/--lng --radius` 를 쓰라고 알린다. 행정동(`역삼1동`)은 `REGION_NOT_FOUND` 와 법정동 힌트, 같은 이름의 동(`신사동`)은 `REGION_AMBIGUOUS` 와 `candidates` 다. `성수동` 처럼 `○가` 로 나뉜 동은 합쳐 찾지 않고 `REGION_AMBIGUOUS` 로 `○가` 동을 모두 후보로 주니 하나(`성수동1가`)로 다시 부른다. 줄인 대학 이름이 여러 캠퍼스에 맞으면(`연세대`) 고르지 않고 `REGION_AMBIGUOUS` 로 캠퍼스 이름을 후보로 준다. 그 이름을 따옴표로 감싸 그대로 주면(`'연세대학교(원주캠퍼스)'`) 그 캠퍼스로 찾는다. 이름이 똑같은 역이 여럿이어도 `REGION_AMBIGUOUS` 이고 후보에 노선이 붙는다 (`hint` 대로 `search locations` 의 좌표를 `--lat/--lng` 로 준다). 다른 소스 옵션을 옮겨 쓰면(`--area-min`, `--option`, `--condition 반려동물`) 에러 `hint` 가 다방에서 주는 법이나 다방에 그 조건이 없다는 것을 알린다.

**주의사항**

결과는 **다방 목록 순**이다 (거리순이 아니다). 다방 웹처럼 동·역·대학 매물 목록에는 정렬이 없어 `--sort` 를 주면 `INVALID_ARGUMENT` 이고 `hint` 가 단지 매물의 `--sort` 를 알린다. 역·좌표 검색은 `distance_km` 를 주니 가까운 매물이 필요하면 그것으로 고른다. 다방 광고 칸(중개사 추천 매물)은 넣지 않고 `notes` 에 뺀 수를 알린다. `--next` 는 다방 쪽 번호와 그 쪽에서 쓴 칸으로 이어 받아, 다방이 한 쪽을 23건만 줘도 앞 결과의 매물을 다시 주지 않는다. 다만 다방은 쪽끼리 같은 매물을 겹쳐 주기도 해서(웹도 그대로 보여 준다) 앞 결과에 있던 매물이 `--next` 결과에 다시 나올 수 있다. 한 결과 안에서는 한 번만 넣고 `notes` 로 알린다. `--built-within` 은 다방이 사용승인 연도로 세어 날짜로는 그 햇수보다 오래된 건물도 들어온다 (2026년에 `10` 이면 2016-02 승인도 들어온다). `notes` 가 연도 기준과 오늘 기준 날짜를 함께 알리고, 목록에는 사용승인일이 없어 날짜로 따져야 하면 `--details` 로 `approved_date` 을 채운다. `--details` 를 주면 오늘 기준 그 햇수가 넘은 매물을 `notes` 가 ID·승인일로 짚는다 (빼지는 않는다) (매물마다 `listing` 을 부르는 것과 같고 한 번에 된다). `--details` 는 `villa`·`officetel`·`apt` 에도 있고, 단지 매물(`--complex`)에는 없다. 상세 한 건이 거래가 끝난 것 말고 다른 이유(요청 제한·서버 오류·응답 형식 변경)로 실패해도 목록을 버리지 않고 그 매물은 목록 값만 둔다 (`approved_date`·`residence_type` 은 `null`, 모름). 못 붙인 매물 수와 이유는 `[실패] 매물 N건의 상세(사용승인일·건물 용도)를 받지 못해 목록 값만 넣었습니다: <이유>` 로 알린다. 이유는 실패 순서가 아니라 할 일로 고른다. 거절(4xx)·응답 형식 변경이 한 건이라도 있으면 그 이유(요청 제한도 왔으면 뒤에 '요청 제한에도 걸려 그 뒤로는 요청하지 않았습니다. <제한 안내>' 가 붙는다), 없으면 요청 제한(그때부터 남은 매물은 상세를 요청하지 않는다), 없으면 첫 실패의 이유다: 다방이 거절했거나(4xx) 응답 형식이 바뀌었으면 '다방이 매물 상세 요청을 거절했거나 응답 형식이 바뀌었습니다. jibsa 업데이트가 필요할 수 있습니다', 서버 오류·연결 실패면 '다방 매물 상세 요청이 실패했습니다 (예외 이름). 잠시 뒤 다시 시도하세요'.

## 3. `search listings villa` — 주택·빌라 매물 찾기

다방 '주택·빌라' 목록이다. 다방이 이 목록의 매물을 방 개수(원룸·투룸)로 표시해 건물 종류를 알 수 없어 `property_type` 은 늘 `"빌라"` 다 (단독·다가구도 포함). 옵션은 `room` 과 같고 `--trade` 에 매매, `--price-min/--price-max`(매매가, 만원)가 더 있다. `--room` 은 원룸, 투룸, 쓰리룸, 포룸이상(4개 이상)이고 `--condition` 은 주차, 엘리베이터, 단기임대다. 방 크기(`--area-pyeong-min/max`)는 전용면적 기준이다.

```bash
jibsa dabang search listings villa 성수동1가 --trade 전세 --deposit-max 30000 --room 투룸,쓰리룸
```

## 4. `search listings officetel` — 오피스텔 매물 찾기

다방 '오피스텔' 목록이다. 옵션은 `villa` 와 같고 층(`--floor`) 조건이 없으며 `--parking-min` 이 더 있다. 방 크기(`--area-pyeong-min/max`)는 다방이 **계약면적** 기준으로 걸어 결과 `area_m2`(전용)가 조건보다 작게 나온다 (강남역 `--area-pyeong-min 17` 결과가 모두 전용 17평 미만). 계약면적은 `listing` 의 `contract_area_m2` 로 본다.

| 옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--parking-min` | 단지 세대당 주차 대수 하한 (대, 정수) 범위: 1 이상. 다방 웹 주차 필터의 '세대당 1대 이상'·'2대 이상'이고, 그 밖의 정수도 다방이 받는 대로 보낸다 | 미지정 |

```bash
jibsa dabang search listings officetel 강남역 --trade 월세 --rent-max 100 --condition 주차
jibsa dabang search listings officetel 강남역 --parking-min 1
```

`--parking-min` 은 매물이 든 단지의 세대당 주차 대수이고, `--condition 주차`(이 매물이 주차할 수 있는지)와 다른 조건이다. 다방이 거른다 (강남역 오피스텔 126건 → 1대 이상 6건 → 2대 이상 0건, 2026-11-13). 원룸·빌라에는 이 옵션이 없고, 주면 `hint` 가 `officetel`·`apt` 에만 있다고 알린다.

## 5. `search listings apt` — 아파트 매물 찾기

다방 '아파트' 목록이다 (주상복합·도시형 생활주택 포함). 옵션은 `officetel` 과 같고(`--parking-min` 포함) `--households-min/--households-max`(단지 세대수)가 더 있으며 `--condition` 은 단기임대·세안고다.

```bash
jibsa dabang search listings apt 대치동 --trade 매매 --price-max 300000
jibsa dabang search listings apt 강남역 --trade 전세 --households-min 500
jibsa dabang search listings apt 강남역 --trade 매매 --condition 세안고
```

`--condition 세안고` 는 세입자가 있는 채로 파는 매매 매물만 찾는다 (다방 웹 아파트 '추가필터' 의 이름 그대로. 강남역 113건 → 7건, 모두 매매, 2026-11-13). 매매 조건이라 검색할 거래 유형에 매매가 없으면 `INVALID_ARGUMENT` 다: `--trade 전세`·`월세` 만 줄 때, `--condition 단기임대`(월세 매물 조건)와 함께 줄 때, 보증금·월세 조건만 주어 월세·전세로 좁혀질 때. 다방 웹도 거래 유형에 매매가 있을 때만 이 필터를 보여 준다. 기존 세입자의 보증금·월세는 `listing` 의 `with_tenant`·`tenant_deposit_manwon`·`tenant_rent_manwon` 으로 본다. 원룸·빌라·오피스텔에 주면 선택지 오류다.

아파트의 `--parking-min` 도 단지 세대당 주차 대수다 (강남역 113건 → 1대 이상 79건 → 2대 이상 19건, 2026-11-13). 아파트에는 `--condition 주차`(주차 가능 여부)가 없다.

다방은 아파트에 동·대학 검색을 주지 않는다. 동 이름은 동 경계를 덮는 사각형으로 받아 그 동 매물만 남기고(경계 요청 1회 추가), 다른 동 매물을 뺀 수를 `notes` 로 알린다. 그래서 `returned` 가 `--limit` 보다 꽤 적을 수 있다 (뺀 만큼 다시 채우지 않는다). 대학 이름은 그 대학 중심 1km 반경으로 찾는다.

다방 목록은 아파트 면적을 **공급면적**으로만 준다. 그래서 아파트 매물은 `area_m2`·`area_pyeong` 이 `null` 이고 공급면적이 `supply_area_m2` 에 있다 (전용면적은 `listing` 상세). `--area-pyeong-min/max` 도 아파트는 공급 평으로 걸린다 (34평 = 공급 약 112㎡).

## 6. `search complexes` — 단지 목록

동·역·대학 둘레의 아파트·오피스텔 단지를 다방 목록 순으로 준다. 조건 없이 그 범위의 단지를 모두 주며 매물이 없는 단지도 나온다.

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·역·대학 이름. --lat/--lng 를 주면 생략 | 미지정 |
| `--type` / `-t` | 단지 유형: 아파트, 오피스텔 | 아파트 |
| `--lat` / `--lng` / `--radius` | 좌표와 반경 (km). 반경을 덮는 사각형을 그대로 받아 사각형 모서리의 반경 밖 단지도 빼지 않는다 | 미지정 |
| `--limit` | 받을 단지 수 (제외 전) 범위: 1~120. | 24 |

```bash
jibsa dabang search complexes 대치동
jibsa dabang search complexes 강남역 -t 오피스텔
```

**반환값**

단지마다 `complex_id`, `name`, `complex_type`, `occupancy_years`(입주 연차), `household_count`, `address`, `listing_count`·`listing_counts`(지금 올라온 매물 수, `listing_counts` 는 `sale`·`jeonse`·`wolse` 키), `latest_trades`(최근 실거래가. `sale` 키 안 `price_manwon`, `jeonse` 키 안 `deposit_manwon`. 평형과 상관없이 단지의 가장 최근 거래로, 다방 목록 카드와 같고 거래가 없으면 금액이 `null`)을 준다. 아파트 동 검색은 매물 검색처럼 동 경계를 덮는 사각형에서 그 동 단지만 남긴다. 그래서 `--limit` 을 늘려도 다른 동 단지가 대부분이고 `total` 도 사각형 안 수다 (반포동 `--limit 60` 에 반포동 6곳, `total` 348). 더 있으면 `notes` 가 동 안 단지를 빠짐없이 주는 당근·네이버 `search complexes <동>` 을 알린다. 아파트 대학 검색은 대학 중심 1km 반경을 덮는 사각형으로 찾고 `[범위]` 로 알린다. 다방이 다음 쪽에 같은 단지를 다시 주기도 해서 한 번만 넣고 `notes` 로 알린다 (다시 채우지 않는다).

## 7. `complex` — 단지 정보

```bash
jibsa dabang complex 58291f830ff9bd73a07ca123c632
```

세대수·동 수·주차 대수(세대당)·최저/최고층·용적률·건폐율·시공사·사용승인일·난방(`heating`)·연료(`heating_fuel`)·현관 구조(`entrance`)·지금 매물 수, `recent_trade_count`(다방 화면의 '최근 거래수', 다방이 기간을 밝히지 않는다. 모르면 `null`), `tags`(다방 단지 꼬리표: `"입주 5년차"`, `"고속터미널역 도보 7분"`, `"초품아"`. 없으면 `[]`), `pyeongs`(평형: `pyeong_id`, 이름, 전용·공급·계약 면적, 방·욕실 수, 월 관리비 총액), `representative_pyeong_id`(대표 평형. `--pyeong` 없는 `real-price`·`price-trend`·`nearby-complexes` 가 쓰는 평형이고, 다방이 대표를 주지 않으면 다방 웹처럼 첫 평형), `area_prices`(이 단지·동·구의 매매·전세 평당 평균가. 다방 단지 화면 평당가 칸의 '전체 평형 비교' 탭이고, 기본 탭 'N평대 비교' 는 `nearby-complexes`. 다방 화면이 '정보 없음' 으로 쓰는 값(없거나 0)은 `null`), `latest_trades`(`sale`·`jeonse` 키마다 최근 실거래 한 건), `overheated_district`(다방 대출 계산기가 대출 비율을 50%로 묶는 지역인지), `schools`(배정 초등학교와 단지가 든 학교군의 가까운 중·고등학교 3곳씩), `nurseries`·`kindergartens`(가까운 어린이집·유치원 3곳씩)를 준다. 요청 3회. 최근 실거래 요약을 받지 못하면 `latest_trades` 의 `sale`·`jeonse` 를 `null` 로 두고 `[실패]` 로 알린다.

`overheated_district` 는 다방 단지 화면의 대출 계산 조건 값이다. 다방 웹 대출 계산기는 `true` 면 대출 가능액을 집값의 절반으로 셈하고, 자본금이 모자라면 '투기지역 (대출 비율 50% 제한) 입니다.' 라고 알린다. 다방 화면은 이 값을 따로 보여 주지 않고 그 문구로만 드러낸다. 요청이 실패했거나 다방이 값을 비워 주면 `null`(모름)이고 `[실패]` 로 알린다 (다방이 요청을 거절했거나 응답 형식이 바뀌었으면 업데이트 안내가 붙는다). 최근 실거래 요약(`latest_trades`)이 실패해도 안내 순서는 같다. 무슨 일(요청 제한이면 제한 안내, 거절·형식 변경이면 업데이트 안내) 다음에 모름이 된 칸 안내가 끝에 오고, 요약의 끝 안내는 `latest_trades` 의 `sale`·`jeonse` 가 모름이라는 것과 실거래는 `real-price` 로 보라는 말이다.

`latest_trades` 의 `sale`·`jeonse` 는 금액·계약일(날짜로 읽지 못하면 `null` 이고 `[참고]` 로 알린다)·층(`floor`+`floor_number`)과 다방 화면의 면적(아파트는 `supply_area_m2` 공급면적, 오피스텔은 `contract_area_m2` 계약면적)이다. 그 면적인 평형이 하나면 거래한 평형 `pyeong_id` 와 그 전용면적 `area_m2` 도 붙고, 같은 면적 평형이 여럿이면 둘 다 `null` 이고 `notes` 의 `[참고]` 가 후보 평형을 알린다 (삼호1차 82.08㎡ → `3526(24A), 286028(24C)`).

`nurseries`·`kindergartens` 는 거리순이고 시설마다 `school_code`(다방 시설 코드. `school <school_code> --level 어린이집`·`유치원` 으로 상세를 본다), `name`, `establishment`(어린이집 공공·민간·가정·직장·협동, 유치원 국공립·사립. `search schools`·`school` 과 같은 이름), `distance_m`, `children_per_teacher`(교사당 아동 수)다. 근처에 없으면 `[]`, 다방이 학교 정보를 주지 않으면 `null` 이다. 전화·좌표는 주지 않는다.

`pyeongs[].pyeong_id` 를 `search listings --complex`·`real-price`·`price-trend`·`nearby-complexes` 의 `--pyeong` 에 준다. 평형 이름은 아파트가 공급 평(`"30"`), 오피스텔이 다방 표기(`"13B1"`)다.

다방이 평형 목록(`pyeongs`)이나 평당가 비교(`area_prices`)를 `null` 로 주면 그 칸이 `null`(모름)이고 `PARSE_ERROR` 로 끝나지 않는다. 다른 칸은 그대로 오고, `pyeongs` 를 모르면 `latest_trades` 의 `pyeong_id`·`area_m2` 도 `null` 이다. 평형을 모르는 단지의 `search listings --complex` 는 `--pyeong` 번호를 그대로 보내고(단지에 없는 번호인지 가리지 않는다), `--pyeong` 도 없으면 보낼 평형이 없어 `NOT_FOUND` 다.

`schools[]` 는 `level`(초등학교·중학교·고등학교), `school_code`, `name`, `establishment`(공립·사립), `distance_m`, `district`(초등학교는 배정 통학구역, 중·고등학교는 단지가 든 학교군), `students_per_class`(학급당 학생 수)이고, 중학교는 `special_high_entrants`·`autonomous_high_entrants`(특목고·자율형 진학 인원), 고등학교는 `university_entrants`(대학교 진학 인원)도 있다. 진학률과 시·도 평균 비교는 `school_code`·`level` 을 `school` 에 준다. 다방이 한 학교급의 목록만 주지 않으면(모름) 그 학교급은 `schools[]` 에 없고 `[참고]` 로 알린다. 그 학교가 없다는 뜻이 아니다.

## 8. `school` — 학교·유치원·어린이집 하나 상세

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `SCHOOL_CODE` | 코드. 학교는 `complex` 의 `schools[].school_code`(예: `S010000704`), 어린이집은 `nurseries[].school_code`(숫자, 예: `11650000153`), 유치원은 `kindergartens[].school_code`(UUID, 예: `1ecec08c-fea6-b044-e053-0a32095ab044`), 또는 `search schools` 의 `school_code`. 영문·숫자·`-` | 필수 |
| `--level` | 초등학교, 중학교, 고등학교, 유치원, 어린이집 (`schools[].level`, `nurseries` 는 어린이집, `kindergartens` 는 유치원, `search schools` 의 `level`). 코드와 맞아야 한다 | 필수 |

```bash
jibsa dabang school S010000704 --level 중학교
jibsa dabang school 11650000153 --level 어린이집
```

요청 1회. 학교는 다방이 보여 주는 학교알리미 공시다. `name`, `establishment`(국공립·사립), `address`, `office_of_education`, `base_period`(공시 기준, `"2026년 상반기"`), `students_per_class`, `students_per_teacher`, `afterschool_programs`(방과후 프로그램 수, 초등학교는 대개 `null`), 비교용 `sido_average`·`sigungu_average`(시·도·시·군·구 평균), `disclosure_url`(학교알리미 공시 페이지)을 준다. 중·고등학교는 `advancement`(졸업생 진학: `destination`, `count`(명), `percent`(%))도 준다. 중학교는 일반고·특성화고·특목고·자율고와 그 안의 과학고·외국어고·예술체육고(특목고)·자사고(자율고), 고등학교는 대학교·전문대학·국외·취업·기타다. 특목고·자율고 안의 갈래는 다방이 비율만 줘서 `count` 가 `null` 이다. 전화·홈페이지·좌표는 주지 않는다.

유치원(유치원알리미)·어린이집(어린이집정보공개포털)은 다방 상세 화면이 그리는 값이다: `school_code`, `level`, `name`, `establishment`(어린이집 `공공`·`민간`·`가정`·`직장`·`협동`, 유치원 `국공립`·`사립`), `address`, `base_period`(공시 기준), `operating_hours`(다방 글 그대로, 예: `"평일기준시간 : 07:30 ~ 19:30"`), `children_total`(원아 수), `children`(원아가 있는 반·나이만 `group`·`count`·`percent`. 어린이집은 `0세반`~`5세반`·`영아 혼합`·`유아 혼합`·`영유아 혼합`·`특수/장애아`, 유치원은 `만 3세`·`만 4세`·`만 5세 이상`·`혼합`. 다방이 반·나이별 수를 하나도 주지 않으면 `null`(모름)이고, 원아가 없다는 뜻이 아니다), `teachers`(급수·자격마다 `grade`·`count`. 어린이집 `1급`·`2급`·`3급`, 유치원 `수석교사`·`정교사 1급`·`정교사 2급`·`준교사`), `children_per_teacher`(교사 1명당 아동 수), `services`(제공 서비스, 다방이 주지 않으면 `null`), `disclosure_url`(공시 페이지)을 준다. 어린이집만 `school_bus`(`"운영"`·`"미운영"`) 키가 있고, 유치원만 `school_bus_vehicles`(통학 차량 대수. 0 은 통학차량을 운영하지 않는 것이고 다방 화면은 `-` 로 쓴다), `homepage_url` 키가 있다. 유치원 원비(교육비)는 주지 않는다: 다방 값이 유치원알리미 공시의 학부모 부담금과 맞지 않아서다. 원비는 `disclosure_url`(유치원알리미)의 '비용·회계' 에서 본다. 전화·좌표는 주지 않는다.

학교 코드는 `complex` 결과와 `search schools` 에 있다 (`nearby` 의 학교에는 없다). `--level` 이 코드와 다르거나 없는 코드면 다방이 서버 고장과 같은 500 을 줘서 `UPSTREAM_ERROR`(`status` 500)다 (유치원·어린이집도 같다). 코드와 단계를 `complex`·`search schools` 결과에서 그대로 옮겼는지 먼저 보고, 맞으면 잠시 후 다시 부른다. 네이버 `school` 의 학교 코드와는 다른 체계라 서로 바꿔 쓰지 못한다.

## 9. `search schools` — 동 안 학교·유치원·어린이집 목록

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 법정동 이름 (예: 역삼동, '강남구 신사동') | 필수 |
| `--level` | 초등학교, 중학교, 고등학교, 유치원, 어린이집 중 하나 (다방 동네정보 학군 목록의 탭) | 필수 |
| `--establishment` | 설립 구분 하나 (다방 탭 이름 그대로). 초·중·고등학교·유치원은 국공립, 사립. 어린이집은 공공, 민간, 가정, 직장, 협동 | 전체 |
| `--limit` | 받을 수 범위: 1~120. (다방은 30곳씩 준다. 30곳마다 요청 1회) | 30 |

```bash
jibsa dabang search schools 역삼동 --level 초등학교
jibsa dabang search schools 역삼동 --level 어린이집 --establishment 공공
```

다방 동네정보 '학군' 상세 목록과 같은 목록·순서·전체 수다. 결과는 `region`(찾은 동), `level`, `establishment`(고른 설립 구분, 주지 않았으면 `"전체"`), `total`(그 동의 그 단계 수, 설립 구분 적용 뒤), `returned`, `has_more`, `schools[]` 이다. 줄마다 `school_code`, `level`, `name`, `establishment`, `address` 이고, 중·고등학교는 `advancement[]`(다방 목록의 진학률 꼬리표 `destination`·`percent`, 예: 중학교 `과고`·`외고`·`자사고`·`예고`. 다방이 주지 않으면 `null`)도 있다 (다른 단계는 키가 없다). `school_code`·`level` 을 `school` 에 그대로 넘긴다. 역삼동 초등학교는 2곳(서울도성초등학교 `S010000752` 등)이었다 (2026-11-14). 더 있으면 `[일부]` 로 알린다 (`--establishment` 를 주지 않았으면 설립 구분으로 좁히라고 권한다). 다방이 첫 쪽 결과를 주지 않으면 `total` 이 `null` 인 빈 목록이다. 요청은 위치 찾기 1회 + 30곳마다 1회다.

동 이름만 받는다: 역·대학 이름은 `INVALID_ARGUMENT`('동 안 학교는 동 이름으로만 찾습니다: <이름>'), 시·군·구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 이고 `hint` 대로 그 안의 동 이름(`'강남구 역삼동'`)으로 다시 준다. 같은 이름의 동(`신사동`)과 `○가` 로 나뉜 동(`성수동`)은 `REGION_AMBIGUOUS` 로 하나를 고르게 한다. 그 단계에 없는 설립 구분(초등학교에 `민간`)은 입력 오류다.

## 10. `search listings --complex` — 단지 안 매물

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--complex` | 단지 ID (28자리) | 필수 |
| `--pyeong` | 평형 번호(`pyeong_id`). 반복하거나 쉼표로 구분 (OR) | 전체 평형 |
| `--trade` | 거래 유형: 월세, 전세, 매매 | 전체 |
| `--deposit-min/max`, `--rent-min/max`, `--price-min/max` | 금액 (만원) | 미지정 |
| `--sort` | 매물 순서 (다방 웹 단지 매물 정렬 메뉴): 랭킹순, 최신순, 높은가격순, 낮은가격순, 면적넓은순, 면적좁은순 중 하나 | 랭킹순 |
| `--limit` | 받을 매물 수 범위: 1~120. | 24 |

```bash
jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 매매
jibsa dabang search listings --complex 58291f830ff9bd73a07ca123c632 --trade 매매 --sort 낮은가격순
```

단지 상세 1회 + 쪽(24건)마다 1회. 다방이 한 쪽을 23건만 줘도 다음 쪽을 이어 받는다. 단지에 없는 평형 번호는 `INVALID_ARGUMENT` 다.

매물은 다방이 `--sort` 로 정렬한 순서 그대로이고 jibsa 가 다시 세우지 않는다 (은마 매매 `낮은가격순` 은 30억7000 부터, `높은가격순` 은 34억부터, 2026-11-13). 결과의 `sort` 가 고른 정렬 이름(`"낮은가격순"`)이고, 다 받지 못했을 때의 `[일부]` 안내도 `다방 낮은 가격 순으로 앞 N건` 처럼 그 정렬을 따른다. 허용값이 아니거나 둘 이상이면 `INVALID_ARGUMENT` 다.

## 11. `real-price` — 실거래가

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `COMPLEX_ID` | 단지 ID. 단지 없는 매물은 빼고 `--listing` | 미지정 |
| `--listing` | 단지 없는 매물(빌라·주택·원룸)의 매물 ID | 미지정 |
| `--pyeong` | 평형 번호 (단지만) | 다방 대표 평형 |
| `--trade` | 매매, 전월세 (전세·월세를 함께 준다) | 단지는 매매, `--listing` 은 매물의 거래 유형 (매매 매물은 매매, 월세·전세 매물은 전월세) |
| `--years` | 최근 몇 년 (1~3, 다방은 3년까지) | 3 |
| `--limit` | 최대 거래 수 범위: 1~200. | 30 |

```bash
jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --trade 매매
jibsa dabang real-price 58291f830ff9bd73a07ca123c632 --pyeong 817 --trade 전월세 --years 1
jibsa dabang real-price --listing 6abb32f72f9f803f9c6f3830
```

`trades[]` 는 최근 계약 순이고 거래마다 `trade_type`(매매·전세·월세), `trade_date`(날짜로 읽지 못하면 `null` 이고 `[참고]` 로 알린다), `floor`(글자)·`floor_number`(숫자), 금액, `cancelled`(해제된 거래), `deal_type`(`중개거래`·`직거래`), `registered`(다방의 등기 표시, 다방이 주지 않으면 `null`), `newly_added`(다방이 새 거래로 표시한 거래)를 준다. `total` 은 기간 안 거래 수다. `--pyeong` 을 안 주면 다방 대표 평형으로 찾고 `[참고]` 로 알린다 (단지 상세 요청 1회 추가). 다방이 대표 평형을 주지 않거나 0 으로 주면 다방 웹처럼 첫 평형으로 찾고, `[참고]` 가 다방이 고른 평형이 아니라고 알린다 (`price-trend`·`nearby-complexes` 도 같다). 단지에 없는 평형 번호는 `INVALID_ARGUMENT`, 없는 단지는 `NOT_FOUND` 다.

국토부 신고에 평형 타입이 없어 전용면적이 같은 평형끼리는 거래가 거의 모두 겹친다 (헬리오시티 84.98㎡ 평형 둘이 1년 32건 중 31건 같음). 거래가 있으면 `notes` 가 알린다. 평형 여러 개를 합칠 때는 같은 날·층·금액을 한 번만 센다.

`--listing` 은 다방 매물 화면과 같은 범위의 거래다. 다방이 정한 범위가 `basis` 에 있다: `"이 집 (망원동 다세대·연립)"` 이면 이 매물과 같은 지번 건물(이 집)의 거래로, 같은 건물의 다른 집 거래도 들 수 있다. `"역삼동 단독·다가구"` 처럼 `이 집` 이 없으면 그 건물의 거래가 **아니라** 그 매물이 있는 동의 같은 건물 유형 거래이고 `notes` 의 `[범위]` 가 알린다. 다방이 범위를 알려 주지 않으면 `basis` 가 `null` 이고 `notes` 의 `[참고]` 가 알린다. `--trade` 를 주지 않으면 다방 매물 화면처럼 매물의 거래 유형을 따르고 `notes` 의 `[거래]` 가 알린다 (`--trade` 를 주면 매매 매물의 전월세처럼 다른 거래 유형도 본다. 다방은 범위를 거래 유형마다 따로 정해, 같은 매물도 전월세는 이 집·매매는 같은 동일 수 있다. `basis` 는 받은 거래 유형의 범위다). 다방이 매물의 거래 유형을 알려 주지 않으면 `UPSTREAM_ERROR` 이고 `hint` 대로 `--trade` 를 준다. 다방에서 범위·거래 유형을 먼저 받아 요청이 1회 더 든다.

거래의 면적 키는 건물 유형마다 다르다. 다세대·연립은 `area_m2`(전용면적)와 `floor` 이고, 단독·다가구는 `area_m2`·`floor` 키가 없고 `total_floor_area_m2`(다방이 연면적이라 부르는 건물 전체 면적, 164~1,214㎡ 같은 값)와 매매만 `house_type`(`"단독"`·`"다가구"`)이다. `total_floor_area_m2` 는 매물의 전용면적과 기준이 달라 그대로 견주지 않는다. 다세대·연립은 `area_m2`·`floor` 가 비슷한 거래만 견준다. 없는 매물이나 단지 매물(오피스텔·아파트) ID 는 `NOT_FOUND` 다 (단지 매물은 `listing` 결과의 `complex_id` 로 찾는다).

## 12. `price-trend` — 시세 흐름

```bash
jibsa dabang price-trend 58291f830ff9bd73a07ca123c632 --pyeong 817
```

평형 하나의 36달 흐름이다 (요청 1회). `--pyeong` 을 안 주면 대표 평형을 찾느라 단지 상세 1회가 더 들고 `[참고]` 가 고른 평형과 다른 평형을 고를 곳(`complex` 의 `pyeongs`)을 알린다 (대표 평형 고르기는 [`real-price`](#11-real-price--실거래가)). `months[]` 는 오래된 달부터 달마다 `month`(`YYYY-MM`, 읽지 못하면 `null` 이고 `[참고]` 로 알린다)·`trade_averages`(`sale` 키 안 `price_manwon`, `jeonse` 키 안 `deposit_manwon`: 평균 실거래가), `trade_counts`(`sale`·`jeonse`·`wolse` 거래 수), 그 달 전세가율 `jeonse_ratio_percent`(%, 0 이면 `null`)와 `gap_manwon`(그 달 매매 평균 − 전세 평균, 만원)이다. 거래가 없는 달은 다방이 앞 달 평균을 이어 준다(`trade_counts` 의 `sale` 이 `0`). 이을 앞 달 평균도 없으면(그때까지 거래가 없던 평형) 그 거래가 `null` 이다. 거래가 아직 없는 이번 달은 `jeonse_ratio_percent`·`gap_manwon` 이 `null` 이다. 결과 맨 위에도 `trade_averages`(최근 평균, `sale` 안에 평당가 `price_per_pyeong_manwon` 도. 다방이 그 거래 평균을 주지 않으면 그 거래가 `null`, 일부 칸만 모르면 그 칸만 `null`), `jeonse_ratio_percent`(전세가율), `gap_manwon`(매매 − 전세), `trade_ranges`(거래별 `one_year`·`three_years` 기간의 `lowest`(최저)·`highest`(최고). 두 끝을 모두 모르면 그 기간이 `null`, 두 기간 모두 모르면 그 거래가 `null`)도 준다. 단지에 없는 평형 번호는 `INVALID_ARGUMENT` 다.

## 13. `nearby-complexes` — 평형대 평당가와 주변 단지

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `COMPLEX_ID` | 단지 ID | 필수 |
| `--pyeong` | 평형 번호 (`complex` 의 `pyeongs[].pyeong_id`). 그 평형이 든 평형대로 비교한다 | 다방 대표 평형 |

```bash
jibsa dabang nearby-complexes 58291f830ff9bd73a07ca123c632
```

다방 단지 화면 평당가 칸의 기본 탭('N평대 비교')이다. 단지 전체 평형의 비교('전체 평형 비교' 탭)는 `complex` 의 `area_prices` 다. 요청 1회이고, `--pyeong` 을 안 주면 대표 평형을 찾느라 단지 상세 1회가 더 들고 `notes` 로 알린다 (대표 평형 고르기는 [`real-price`](#11-real-price--실거래가)).

결과는 `complex_id`, `pyeong_id`(고른 평형), `pyeong_range`(비교한 평형대, 예: `"30평대"`), `area_prices[]`(이 평형대의 `scope` 해당 단지·동·구마다 `price_per_pyeong`: `sale`·`jeonse` 키 안 `price_per_pyeong_manwon`, 만원/3.3㎡. 다방 화면이 '정보 없음' 으로 쓰는 값(없거나 0)이면 그 거래가 `null`. 다방이 이 목록을 주지 않으면 `area_prices` 가 `null`), `nearby`(`sale`·`jeonse` 키마다 반경 1km 주변 단지 목록, 평당가 10곳까지. 단지 ID 가 없는 줄은 다방 웹처럼 빼고 `[제외]` 로 그 수를 알려서 10곳보다 적을 수 있다. 다방이 주변 단지나 그 쪽 목록을 주지 않으면 그 쪽은 `null`(모름), 주었는데 비었으면 `[]`), `url` 이다. 주변 단지마다 `complex_id`, `name`, `complex_type`, `address`(동까지), `price_per_pyeong_manwon`(`null` 이면 다방 화면도 빈 칸. `0` 은 다방 화면도 '0원' 이다), `household_count`, `occupancy_years`(입주 연차), `distance_m`(이 단지에서 거리)이고, 순서는 다방 그대로다 (평당가가 있는 단지가 가까운 순으로 앞에, 없는 단지가 뒤에). 은마 대표 평형(817)은 `30평대` 이고 해당 단지 매매 평당가 10301 이었다 (2026-11-14).

다방이 그 평형에 평형대를 주지 않으면(다방 화면도 이 탭 없이 '전체 평형 비교' 만 보여 준다) `pyeong_range`·`area_prices`·`nearby` 가 모두 `null` 이고 `[참고]` 가 `complex` 의 `area_prices` 를 알린다. 단지에 없는 평형 번호는 `INVALID_ARGUMENT`, 없는 단지는 `NOT_FOUND` 다.

## 14. `listing` — 매물 하나 상세

```bash
jibsa dabang listing 6abb32f72f9f803f9c6f3830
jibsa dabang listing 59136486
```

검색 결과의 `id`(24자리) 또는 다방 화면의 매물번호(`listing_number`)를 받는다 (매물번호면 요청 1회 추가). 가격·관리비·전용/공급면적·층/건물 층수·방향과 기준(`direction_criterion`)·입주 가능일·주차(총 대수)·엘리베이터·옵션·보안 시설(`safety`)·난방·건물 용도(`residence_type`)·융자(`loan`)·등록일·사용승인일을 준다. 단기임대를 받는 월세 매물은 `short_term_period`(예: `"1개월(이상 협의가능)"`), 오피스텔·아파트는 `complex_id` 가 붙는다. 상세의 `property_type` 은 다방 표시대로 `"오피스텔(분리형)"`·`"원룸(분리형,복층)"` 처럼 구조가 붙기도 한다. 에어컨은 `options` 에 `"벽걸이형 에어컨"`·`"스탠드형 에어컨"`·`"천장형 에어컨"` 으로 나온다. 다방이 공급면적을 0 으로 주는 오피스텔은 `supply_area_m2` 가 `null` 이다. 오피스텔은 다방이 주는 계약면적 `contract_area_m2`(㎡)도 붙는다 (오피스텔에만 키가 있고, 다방이 값을 주지 않으면 `null` 이다).

관리비는 다방 상세의 관리비 칸과 같다. `manage_cost_charge_type` 은 부과 방식(`"정액관리비"`·`"기타부과"`·`"확인불가"`, 모르면 `null`), `manage_cost_includes` 는 관리비에 든 항목, `manage_cost_excludes` 는 관리비에 들지 않고 실비로 따로 내는 항목(예: `["전기", "수도"]`)이다. 실비 항목은 정액관리비를 항목마다 적은 매물(대개 정액 10만원 이상)만 알고 그 밖은 `null` 이다. 기타부과 매물과 항목을 적지 않은 정액관리비 매물(10만원 미만이거나 세부를 알리지 않은 매물)은 포함 항목만 알고, 다방이 포함 항목을 빈 목록으로 주면 `manage_cost_includes` 가 `[]`, 주지 않으면 `null` 이다. 공용 관리비는 다방이 실비로 표시해도 화면에서 금액과 함께 관리비 합계에 들어 `manage_cost_includes` 에 `"공용 관리비"` 로 넣는다. 확인불가 매물은 다방도 항목을 보여 주지 않아 항목이 `null` 이다. 다방이 정액관리비 항목 목록에 빈 항목을 섞어 보내 빼고 읽었으면 어느 항목이 빠졌는지 몰라 `manage_cost_includes`·`manage_cost_excludes` 가 `null` 이고 `[제외]` 로 알린다.

거래 관련 표시도 다방 화면대로 준다. `with_tenant` 는 세입자를 끼고 파는 매매(매매만 키가 있고, 다른 거래는 다방이 표시를 붙였을 때만)이고, `true` 면 기존 세입자의 `tenant_deposit_manwon`(보증금·전세금, 만원. `200000` = 다방 표시 `"20억"`)과 기존 세입자가 월세일 때만 `tenant_rent_manwon` 이 붙는다 (다방 표시를 읽지 못하면 둘 다 `null`). `lh_jeonse` 는 LH 전세임대 가능(매매는 표시가 없으면 키가 없다), `leasehold_registration` 은 임차권 등기명령 매물(기존 임차인의 권리가 우선이라 확인 후 거래), `unregistered_building` 은 미등기 건물, `non_compliant_building` 은 위반건축물 여부(`true`·`false`, 다방이 알려 주지 않으면 `null`)다.

없는 매물·비공개·계약 완료는 `LISTING_UNAVAILABLE` 이다.

## 15. `neighborhood` — 동네정보

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 법정동 이름 (예: 역삼동, '강남구 신사동') | 필수 |
| `--topic` | 주제: 매물, 거래, 시세, 인구, 학교, 편의, 교통, 안전. 반복하거나 쉼표로 구분 | 전체 |
| `--ranks` | 학교·편의·교통·안전 주제의 종류마다 합계·구성과 순위(`ranks`)를 더한다. 종류마다 요청 1회 더 (학교 5·편의 5·교통 4·안전 3, 넷 다면 17회) | 꺼짐 |

```bash
jibsa dabang neighborhood 역삼동
jibsa dabang neighborhood 역삼동 --topic 매물,인구,학교
jibsa dabang neighborhood 역삼동 --topic 편의,안전 --ranks
```

다방 '동네정보' 화면의 숫자다. 주제마다 요청 1회 (전부면 위치 찾기와 합쳐 9회, `--ranks` 까지면 26회). `base_month` 는 다방 집계 기준 달이다.

| 주제 | 필드 | 내용 (출처) |
| --- | --- | --- |
| 매물 | `listings` | 지금 다방에 올라온 매물 수: 합계(`count`), 주택/빌라·오피스텔·아파트별(`by_type[]`: `property_type`·`count`·`counts` 의 `wolse`·`jeonse`·`sale` 키별 수), 순위(`ranking`) (다방) |
| 거래 | `trades` | 거래량: 같은 모양 (국토교통부 신고 기준) |
| 시세 | `prices` | 아파트·오피스텔 평균 매매가·전세가(`by_type[]`: `complex_type`·`trade_averages`, 만원, 국토교통부 실거래 기준. 다방이 그 거래 평균을 주지 않으면 그 거래가 `null`)와 순위 (순위는 다방 화면대로 아파트 매매 기준이다) |
| 인구 | `population` | 인구·남녀·연령대(수와 %)와 순위 (행정안전부) |
| 학교 | `schools` | 학교 종류별 설립 구분 수(`{"초등학교": {"국공립": 2}}`)와 학원 종류별 수(`"학원"`) |
| 편의 | `amenities` | 생활편의·의료·외식·쇼핑·체육 시설 수 (`{"생활편의시설": {"편의점": 204}}`) |
| 교통 | `transport` | 지하철역·버스정류장·주차장·주유소·전기차 충전소·차량관리 시설 수 |
| 안전 | `safety` | CCTV·가로등·지구대·119안전센터·공사현장 수 |

`ranking` 은 `national_rank`(전국)·`sido_rank`(시·도 안, 시·도 이름 `sido`)·`sigungu_rank`(시·군·구 안, 시·군·구 이름 `sigungu`) 순위이고 1 이 가장 많거나 높다. 다방이 매물·거래의 유형별 목록에 빈 항목을 섞어 보내 빼고 읽었으면 그 주제의 합계 `count` 가 `null`(모름)이고 `[제외]` 로 알린다 (유형별 수는 받은 유형만이다). 고르지 않은 주제는 키가 없다. 동 하나만 받는다: `성수동` 처럼 `○가` 로 나뉜 동은 매물 검색처럼 `REGION_AMBIGUOUS` 로 `성수동1가` 처럼 하나를 고르게 하고, 역·대학 이름은 `INVALID_ARGUMENT`('동네정보는 동 이름으로만 찾습니다: <이름>', `hint` 가 역 둘레는 `station-prices`·`search listings` 로 보라고 알린다), 시·군·구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 그 안의 동 이름으로 다시 주라고 알린다.

`schools`·`amenities`·`transport`·`safety` 와 `ranks[].counts` 의 키(`초등학교`·`편의점`·`지하철` 등)는 다방이 그때 보내는 종류 이름표 그대로라 한국어다. jibsa 가 붙이는 `학원` 키도 같은 객체의 다른 키가 다방 이름표라 한국어로 맞춘다 (이유는 [출력 규약](https://github.com/Rukkakka/jibsa/blob/main/docs/development/output-contract.md#칸-이름-규칙)). 거래별 묶음인 `listings`·`trades` 의 `counts` 와 `prices` 의 `trade_averages` 만 영어 거래 키(`sale`·`jeonse`·`wolse`)다.

학교·편의·교통·안전 주제의 순위는 `--ranks` 를 줄 때만 받는다 (다방 동네정보 탭의 요약 칸, 종류마다 요청 1회). `ranks[]` 는 줄마다 `topic`(`학교`·`편의`·`교통`·`안전`), `type`(다방 요약 칸 이름표: 어린이집·유치원·초등학교·중학교·고등학교 / 생활 편의시설·의료시설·외식시설·대형 쇼핑시설·체육시설 / 교통시설·주차시설·주유시설·차량관리시설 / 안전시설·안전기관·불편요소), `count`(그 종류의 합계), `counts`(구성, 예: `{"지하철": 5, "버스": 73}`. 다방이 구성을 주지 않으면 `null`, 빈 구성이면 `{}`), `ranking`(다른 주제의 `ranking` 과 같은 꼴)다. 다방이 그 종류의 요약을 주지 않으면 `count`·`counts`·`ranking` 이 모두 `null` 이다. 역삼동 교통시설은 78(지하철 5·버스 73)이고 전국 747위·서울 37위·강남구 2위였다 (2026-11-14). `--topic` 으로 좁히면 고른 주제의 종류만 받고, `--topic` 에 이 네 주제가 하나도 없는데 `--ranks` 를 주면 입력 오류다. `--ranks` 가 없으면 `ranks` 키가 없다.

## 16. `hot-places` — 동 안 핫플레이스

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 법정동 이름 | 필수 |
| `--type` / `-t` | 가이드: 전체, 미쉐린, 블루리본 (다방 웹 고르기 이름 그대로) | 전체 |
| `--limit` | 받을 수 범위: 1~120. (다방은 30곳씩 준다. 30곳마다 요청 1회) | 30 |

```bash
jibsa dabang hot-places 역삼동
jibsa dabang hot-places 역삼동 --type 미쉐린
```

다방 동네정보 '핫플레이스' 로, 미쉐린·블루리본 가이드에 오른 식당을 다방 목록 순으로 준다. 결과는 `region`(찾은 동), `type`(고른 가이드), `basis`(무엇을 모은 목록인지, 다방 화면 문구), `base_month`(다방 기준 달, 역삼동은 `2026-05`, 2026-11-14), `total`, `returned`, `has_more`, `places[]` 이다. 식당마다 `name`, `guide`(`"미쉐린"`·`"블루리본"`, 다방 이름표가 없는 값이면 `null`), `address`(시·도는 정식 이름, 다방이 주지 않으면 `null`), `labels`(꼬리표, 예: `"한식(일반한식)"`. 없으면 `[]`)다. 사진은 주지 않는다. 더 있으면 `[일부]` 로 알린다 (`--type` 을 주지 않았으면 가이드로 좁히라고 권한다). 다방이 첫 쪽 결과를 주지 않으면 `total` 이 `null` 인 빈 목록이다. 요청은 위치 찾기 1회 + 30곳마다 1회다. 동 이름만 받는다: 역·대학 이름은 `INVALID_ARGUMENT`('핫플레이스는 동 이름으로만 찾습니다: <이름>', 이 명령은 역·대학 둘레를 찾지 않는다), 시·군·구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 그 안의 동 이름으로 다시 주라고 알린다. 같은 이름의 동과 `○가` 로 나뉜 동은 `REGION_AMBIGUOUS` 다.

## 17. `popular-listings` — 동 안 인기 매물

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

다방 선호도(조회수·찜수·문의수를 합친 점수) 높은 순이고 매물마다 `rank`(1 이 가장 높다)가 붙는다. 다방이 한 쪽에 빈 항목을 섞어 보내 빼고 읽었으면 그 쪽의 `rank` 는 셀 수 없어 `null` 이고 `[제외]` 로 알린다 (다른 쪽의 순위는 쪽 번호로 세어 그대로다). 50건마다 요청 1회. `total` 은 고른 유형·거래 유형에서 순위가 있는 매물 수다. 매물 필드는 `search listings` 와 같고, 유형을 하나만 고르면 그 유형으로 `property_type` 을 붙인다. 여럿이면 다방 표시대로 오피스텔·아파트이고, 방 개수(원룸·투룸)로 표시된 주택·빌라 매물은 `"빌라"` 다. 더 있으면 `[일부]` 로 알리고 좁히는 법을 권한다: `-t`·`--trade` 를 둘 다 안 골랐으면 둘 다, 하나만 골랐으면 나머지 하나만, 이미 하나씩 골랐으면 `--limit` 만 알린다. 동 이름만 받는다: 역·대학 이름은 `INVALID_ARGUMENT`('인기 매물은 동 이름으로만 찾습니다: <이름>', `hint` 가 역 둘레는 `search listings` 로 보라고 알린다), 시·군·구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 그 안의 동 이름으로 다시 주라고 알린다. 같은 이름의 동과 `○가` 로 나뉜 동은 `REGION_AMBIGUOUS` 다.

## 18. `nearby` — 매물·단지·분양 둘레

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `TARGET_ID` | 매물 ID(`id`, 24자리) 또는 단지 ID(`complex_id`, 28자리). 매물번호는 받지 않는다 | 미지정 |
| `--sale` | 분양 ID (`search sales` 의 `presale_id`, 28자리). 다방 분양 화면의 주변 정보 | 미지정 |
| `--with` | 더 받을 생활 정보: 반려동물(단지만), 카셰어링(매물·단지만). 반복하거나 쉼표로 구분. 하나마다 요청 1회 더 | 미지정 |

```bash
jibsa dabang nearby 6abb32f72f9f803f9c6f3830
jibsa dabang nearby 58291f830ff9bd73a07ca123c632 --with 반려동물,카셰어링
jibsa dabang nearby --sale 68f1ac43f6e4d16e5bf6b7fb2469
```

`TARGET_ID` 와 `--sale` 중 하나만 준다 (둘 다 주거나 둘 다 없으면 `INVALID_ARGUMENT`). 분양 ID 는 단지 ID 와 길이가 같아 위치 인자로 주면 단지로 찾아 `NOT_FOUND` 이니 꼭 `--sale` 로 준다. 요청 2회. 결과의 `target` 은 `"매물"`·`"단지"`·`"분양"`, `url` 은 그 매물·단지·분양 페이지(분양은 `https://www.dabangapp.com/sale-in-lots/{id}`)다. 없는 ID 는 `NOT_FOUND` 다. `stations`(1km 안 지하철역: 노선·거리), `bus_route_count`(500m 안 정류장을 지나는 버스 노선 수), `nearest`(가까운 시설), `schools`(가까운 어린이집·유치원·초·중·고등학교)를 준다. `nearest`·`schools` 는 종류마다 `{"type": "편의점", "places": [{"name": …, "distance_m": …}, …]}` 이고 `places` 는 다방 거리로 가까운 순 3곳까지다 (덜 있으면 있는 만큼). 종류 이름은 다방 화면 이름표이고 다방이 주는 종류가 달라 매물은 버스·편의점·카페·은행·관공서·치안, 단지·분양은 버스·마트·편의점·은행·약국·치안이다. 치안(지구대 등)은 다방이 이름을 주지 않아 `name` 이 `null` 이다. 거리는 직선 거리(m)다. `nearest`·`schools` 의 `distance_m` 은 웹처럼 1m 미만이면 소수 한 자리(예: `0.4`), 그 이상은 .5 를 올려 정수(`88.5` → `89`)다. 역·반려동물·카셰어링 거리는 정수(m)다. 다방이 범위 안에서 찾지 못한 종류는 목록에 없다. `schools` 는 가까운 학교이지 배정 학교가 아니다 (단지의 배정 초등학교는 `complex` 의 `schools`).

`--with 반려동물` 은 다방 단지 화면의 '펫세권'(2km 안)이고 `pet_places` 에 `radius_m` 과 `types[]`(종류 `type` `"동물병원"`·`"미용실"`·`"카페"`·`"호텔"` 마다 `places[]` 의 `name`·`road_address`·`distance_m`·`categories`)를 준다. `--with 카셰어링` 은 다방 매물·단지 화면의 'Car세권'(2km 안)이고 `car_share` 에 `radius_m` 과 `zones[]`(`service` `"쏘카존"`·`"그린존"`, `name`, `address`, `distance_m`)를 준다. 둘 다 다방 거리로 가까운 순 3곳까지다 (반려동물은 종류마다). 다방이 찾지 못한 반려동물 종류는 목록에 없고, 장소에 분류가 없으면 `categories` 는 `[]` 다. 다방이 목록을 주지 않으면 `pet_places`·`car_share` 는 `null`(모름)이다. 다방은 반려동물을 단지에만, 카셰어링을 매물·단지에만 주어 받지 못하는 대상(매물·분양의 반려동물, 분양의 카셰어링)에 주면 요청 없이 `INVALID_ARGUMENT` 다. 전화번호·좌표는 주지 않는다. `--with` 가 없으면 `pet_places`·`car_share` 키가 없다.

## 19. `station-prices` — 역 둘레 평균 매물가

```bash
jibsa dabang station-prices 강남역
```

다방 화면의 '평균 매물가'다. 실거래가가 **아니라** 지금 다방 역 반경(`radius_m`, 강남역 750m) 안에 올라온 원룸·투룸 목록 매물(방 1~2개)의 평균이다. `prices[]` 는 건물 유형(`property_type`: 빌라·오피스텔·아파트) × 방(`room_type`: 원룸·투룸)마다 `asking_averages`(`jeonse` 키 안 `deposit_manwon` 전세 평균, `wolse` 키 안 `deposit_manwon`·`rent_manwon` 월세 평균 보증금·월세)이다. 다방이 그 유형 × 방 칸을 주지 않으면 `prices` 에 그 칸이 없고(홍대입구역은 오피스텔 투룸·아파트 투룸이 없다), 칸은 있는데 다방이 그 거래 평균을 주지 않으면(다방 웹은 '-') 그 거래가 `null`(모름)이다 (예: `"jeonse": null`. 월세는 보증금·월세 둘 다 모를 때 `wolse` 가 `null` 이고 하나만 모르면 그 칸만 `null`). 다방이 매물 수를 주지 않아 그 거래 매물이 없는 것인지는 가를 수 없다. 쓰리룸 이상은 다방이 주지 않는다. 요청 2회 (역 찾기 + 지도 집계). 역 이름이 아니면 `INVALID_ARGUMENT` 이고, 시·군·구 이름(`강남구`)은 `REGION_NOT_SUPPORTED` 로 역 이름(`'강남역'`)으로 다시 주라고 알린다. 이름이 똑같은 역이 여럿이면 `REGION_AMBIGUOUS` 로 노선을 붙인 후보를 주지만, 이 명령은 역을 이름으로만 받아 그중 하나를 가려 받지 못한다 (다방은 대개 `양평역`·`양평역(중앙선)` 처럼 이름을 달리 줘서 드물다).

## 20. `search sales` — 분양 단지 목록

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `QUERY` | 동·시군구·시도·역·대학 이름이나 `전국` (예: 역삼동, 강남구, '성남시 분당구', 서울, 강남역). --lat/--lng 를 주면 생략 | 미지정 |
| `--lat` / `--lng` / `--radius` | 좌표와 반경 (km, 역·대학·좌표 둘레) 범위: 0.1~5.0. | 1km |
| `--type` / `-t` | 건물 유형: 아파트, 오피스텔, 도시형생활주택, 지식산업센터 | 전체 |
| `--state` | 분양 상태: 분양예정, 접수중, 접수마감, 입주예정, 입주모집 | 전체 |
| `--supply` | 공급 유형: 공공분양, 민간분양, 공공임대, 민간임대 | 전체 |
| `--limit` | 받을 단지 수 (동 이름이면 주소로 거르기 전) 범위: 1~120. | 24 |

```bash
jibsa dabang search sales 강남구 --state 분양예정,접수중
jibsa dabang search sales 서울 -t 아파트
jibsa dabang search sales 강남역 --radius 3 -t 아파트
```

단지마다 `presale_id`, `name`, `status`, `complex_type`, `supply_type`, `address`, `presale_household_count`(분양 세대수, 다방 목록의 세대수 칸. 총세대수가 아니다), `household_count`(총세대수, 아래), `price_kind`(가격 종류, 아래), 다방 대표 가격(`price_kind` 가 `"분양가"` 면 `price_manwon`, `"임대가"`(공공·민간임대)면 임대 보증금이라 `deposit_manwon`. 해당 없는 금액 키는 없고 다방이 가격을 아직 주지 않으면 `null`), `next_schedule`(다음 일정 글)을 준다. 다방이 24곳씩 주고 쪽마다 요청 1회다.

이름에 따라 다방의 두 목록 중 하나로 찾는다:

- **전국·시·도·시·군·구**는 다방 분양 지역 목록(다방 웹 '분양정보' 목록)이다. 웹 목록과 같은 목록·순서이고 `total` 은 웹의 '총 N건'(그 지역 분양 단지 수)이다 (김포시 37, 2026-11-14). `household_count` 가 오고(경희궁 에피트: `presale_household_count` 134, `household_count` 228), 공공·민간임대의 `price_kind` 는 웹처럼 `"임대가"` 다. 다방이 첫 쪽에 함께 주는 추천 칸은 웹 목록에 없어 넣지 않고 `[제외]` 로 수만 알린다. 범위 찾기에 시·도는 1회, 시·군·구는 2회가 더 든다 (전국은 없다).
- **동·역·대학·좌표**는 지도 목록이다. 동은 동 경계를 덮는 사각형으로 받아 주소가 그 동인 단지만 남기고(경계 요청 1회 추가, 뺀 수는 `[제외]`), 역·대학·좌표는 반경을 덮는 사각형 그대로다 (분양 칸에 좌표가 없어 반경 밖을 뺄 수 없다). `total` 은 사각형 안 수이고, `household_count` 는 다방이 주지 않아 `null` 이다. 임대 공급의 `price_kind` 는 지역 목록과 같이 두 목록 모두 `"임대가"` 다 (2026-11-25 `'군포시 둔대동'`·`군포시`).

구가 있는 시(`성남시`)는 `REGION_NOT_SUPPORTED` 로 구 이름(`'성남시 분당구'`)을 붙이게 하고, 여러 시·도에 있는 시·군·구 이름(`중구`)은 `REGION_AMBIGUOUS` 다 (`'서울 중구'` 처럼 시·도를 붙인다). 전국·시·도·시·군·구에 `--radius` 를 주면 `INVALID_ARGUMENT` 다 (그 지역 전체를 찾는다). `광주시` 는 경기도 광주시이고 옛 광주광역시는 구 이름(`광산구`, `광주시 광산구`)으로 준다.

## 21. `sale` — 분양 단지 하나

```bash
jibsa dabang sale 6a7a774cf962bc11cafe5cd6d0f1
```

상태, 건물·공급 유형, 지번·도로명 주소, 총·분양 세대수(`household_count`·`presale_household_count`), 동 수·층수, `construction_company`(시공사)·`developer`(시행사), `price_kind`, `price_range`(`lowest`·`highest` 의 금액 칸. 분양가면 `price_manwon`, 임대가면 `deposit_manwon`)·`price_per_pyeong_manwon`, `region_price_per_pyeong_average_manwon`(최근 6개월 이 지역 평균 평당가, 만원/3.3㎡, 예 `1294`. 다방이 주지 않으면 `null`), `move_in`(입주 예정 `YYYY-MM`, 날까지 주면 `YYYY-MM-DD`. 날짜로 읽지 못하면 `null` 이고 `notes` 의 `[참고]` 가 원래 글자를 알린다), 규제 지역·분양가 상한제·전매 가능(모르면 `null`), `schedules`(모집공고·특별공급·1·2순위 청약·당첨자발표·계약기간·입주예정일의 `step`·`start_date`·`end_date`, 달만 알면 `start_month`·`end_month`(`YYYY-MM`). 하루짜리는 `end_date` 가 `start_date` 와 같고, 모집공고·당첨자발표·입주예정일처럼 한 시점인 단계는 `end_date` 키가 없다), `pyeongs`(평형별 전용·공급 면적·세대수·가격 `price_manwon` 또는 `deposit_manwon`), `subscription_result`(청약 결과), `notice_url`(입주자 모집공고), `applyhome_url`(청약홈)을 준다. 상담 전화는 주지 않는다. 요청 1회.

`price_kind` 는 가격이 무엇인지다: 보통 `"분양가"` 이고 공공임대·민간임대는 다방 화면처럼 `"임대가"` 다. `price_range`·`price_per_pyeong_manwon`·`pyeongs[]` 의 금액이 이 종류의 값이다. `"임대가"` 면 분양가가 아니라 임대 보증금이라 `price_range` 두 끝과 `pyeongs[]` 는 `price_manwon` 대신 `deposit_manwon` 에 담고(`price_manwon` 키가 없다), `price_per_pyeong_manwon` 은 이름 그대로 보증금 평당가다 (군포대야미 A-1블록 6년 분양전환공공임대 55A 임대가 8561 = 모집공고 임대보증금 85,614,000원, 월임대료는 다방이 주지 않는다. 2026-11-25). 공급 유형은 다방이 매긴 대로 따르니 의심되면 `url` 의 공고문으로 확인한다.

`subscription_result` 는 `lowest_winning_point`(최저 당첨가점, 점), `highest_competition_ratio`(최고 경쟁률, `5.52` = 5.52:1), `pyeongs[]`(`name` `"59A"`, `presale_household_count` 그 평형의 분양 세대수, `competition_ratio`, `winning_point`)다. 다방 표시가 숫자가 아니면 그 값은 `null` 이고, 다방이 평형별 결과를 주지 않으면 `pyeongs` 가 `null`(모름)이다. 청약 전이거나 다방에 결과가 없으면 `subscription_result` 가 `null` 이다.

## 22. `sale-schedule` — 날짜별 청약 일정

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--from` | 시작 날 (YYYY-MM-DD) | 오늘 (한국 날짜) |
| `--days` | 며칠 범위: 1~7. (다방은 7일까지) | 7 |
| `--region` | 시·도 (서울, 경기, 충청북도 …). 하루 상세를 받아(`--details` 와 같다) 분양 단지 주소의 시·도로 jibsa 가 거른다. 시·군·구는 `INVALID_ARGUMENT` | 전국 |
| `--details` | 줄마다 분양 단지의 주소·건물 유형·공급 유형·세대수·가격(`presale`)을 붙인다. 내보낼 줄이 든 날마다 요청 1회 더 | 꺼짐 |
| `--limit` | 최대 일정 수 범위: 1~300. | 50 |

```bash
jibsa dabang sale-schedule --region 서울
jibsa dabang sale-schedule --from 2026-11-02 --days 3 --details
```

`schedules[]` 는 날마다 `kind`(접수·발표 등), `sido`, `text`('[청약접수] 서울 [임의공급] 마곡스카이온 (~10/28)'), `presale_id` 다. `sido` 는 일정 글 앞의 시·도이고, 글이 시·도 없이 시나 단지 이름으로 시작하면(`'익산 부송에코르 …'`) `null` 이다. `total` 은 `--region` 으로 거르기 전 기간 안 일정 수다 (다방이 날·일정 목록에 빈 항목을 섞어 보내 빼고 읽었으면 셀 수 없어 `null` 이고 `[제외]` 로 알린다). `--details`·`--region` 이 없으면 요청 1회이고 `presale` 키가 없다.

`--details` 는 다방 청약 일정에서 날짜를 누르면 나오는 그 날의 분양 단지 표를 받아, 줄마다 `presale`(`status`, `complex_type`, `supply_type`, `address`, `presale_household_count` 분양 세대수, `household_count` 총세대수, `price_kind` `"분양가"`·`"임대가"`, 금액은 분양가면 `price_manwon`·임대가면 `deposit_manwon`)을 붙인다. 내보낼 줄이 든 날마다 요청이 1회 늘고 `[참고]` 가 요청 수를 알린다 (`--limit 5` 면 대개 첫날 하나라 2회). 그 날 표를 받았는데 같은 분양·같은 일정 종류를 찾지 못한 줄은 `presale` 이 `null`(모름)이고 `[참고]` 로 수를 알린다. 다방이 일정에 분양 ID·종류를 주지 않아 맞춰 보지 못한 줄도 `presale` 이 `null` 이고, 따로 '다방이 분양 ID·종류를 주지 않아 맞춰 보지 못해 presale 이 null 입니다' 라고 알린다 (이 줄은 업데이트 안내를 붙이지 않는다). 표를 받지 않은 줄(`--details`·`--region` 없이 부른 결과)은 `presale` 키가 없다.

`--region` 은 일정이 있는 날마다 그 날 표를 받아(날마다 요청 1회, 7일이면 최대 요청 8회) 표의 주소로 시·도를 보고, 표에서 찾지 못한 줄만 일정 글의 시·도로 본다. 글에 시·도가 없는 일정(`'남춘천 센트레빌 …'`)도 표의 주소로 가린다. 주소도 글의 시·도도 없는 일정은 지역을 몰라 빼고 `[제외]` 로 수를 알린다. `--region` 결과 줄에도 `presale` 이 붙는다. 남긴 일정이 `--limit` 을 넘으면 그 뒤 날은 받지 않고 멈춘다. 이때 `[참고]` 가 `'{날} 전날까지 본 N건 중 M건'` 과 `'{날}부터는 보지 않았습니다'` 를 알리고, `[일부]` 의 전체 수는 `'일정 적어도 M건 중 앞 K건'` 처럼 하한이다 (`[제외]` 수도 본 날까지만 센다). 뒷날 일정은 `--from` 을 그 날로 다시 부른다.

## 23. `trending-complexes` — 지금 많이 보는 단지·동

| 옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--type` / `-t` | 아파트, 오피스텔 | 아파트 |
| `--period` | 방금전, 어제, 지난주, 지난달 | 방금전 |
| `--unit` | 단지, 동 | 단지 |
| `--limit` | 범위: 1~50. | 20 |

전국 단위다 (지역으로 좁히지 못한다). `rankings[]` 는 `rank`, 단지면 `complex_id`·`name`·`address`, 동이면 `name`·`address`(시·도)·`legal_division_code`, `viewer_count`(기간 안 다방에서 조회한 사람 수. 다방 화면의 'N명' 이고 조회 횟수가 아니다), `change`(앞 기간 대비 `상승 2`·`하락 1`·`유지`·`신규`)다. `base_period` 는 다방이 센 기간이다. 요청 1회.

## 24. `trade-rankings` — 거래 많은 단지

| 옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--type` / `-t` | 아파트, 오피스텔 | 아파트 |
| `--trade` | 매매, 전세 | 매매 |
| `--period` | 이번주, 지난주, 이번달, 지난달, 올해 | 이번주 |
| `--limit` | 범위: 1~50. | 20 |

전국에서 기간 안 실거래(국토교통부 신고)가 많은 단지다. `rankings[]` 는 `rank`, `complex_id`, `name`, `trade_count`, `occupancy_years`(입주 연차), `household_count`, `address` 다. 이번주·이번달·올해가 비면 기간이 막 시작돼 아직 세지 않았을 수 있다는 `[참고]` 와 함께 지난 기간(`--period 지난주` 등)을 권한다. 요청 1회.

## 25. `region-ranking` — 범위 안 동·단지 순위

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `SCOPE` | 시·군·구(강남구, '성남시 분당구'), 시·도(서울), 전국. `--unit 단지` 의 부동산 항목은 동(역삼동, '강남구 신사동')도 받는다 (그 동 안 단지 순위) | 필수 |
| `--by` | 부동산(동·단지): 평균가, 평당가, 거래량, 매물수, 시세증감, 최고가증감, 거래증감, 매물증감, 선호도, 세대수, 연식, 전세가율(단지만), 갭가격(단지만). 동네정보(동만): 과학고진학률, 외국어고진학률, 자사고진학률, 예술체육고진학률, 대학교진학률, 전문대학진학률, 학원수, 초등학교수, 중학교수, 고등학교수, 유치원수, 어린이집수, 인구, 인구증감, 생활편의시설, 의료시설, 외식시설, 대형쇼핑시설, 체육시설, 교통시설, 주차시설, 주유시설, 차량관리시설, 안전시설, 안전기관, 불편요소 | 필수 |
| `--unit` | 동, 단지 (동네정보 항목은 동만) | 동 |
| `--type` / `-t` | 아파트, 오피스텔, 빌라 (부동산 항목만. 세대수·연식과 동네정보 항목에 주면 INVALID_ARGUMENT). 평균가·평당가·시세증감·최고가증감은 아파트·오피스텔 중 하나만 (둘을 주면 INVALID_ARGUMENT), 거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 둘 다 주면(반복하거나 쉼표로 구분) 합산. 빌라를 넣으면 매물수·거래량·선호도의 동 순위를 '매물정보' 탭으로 받는다 (고른 유형 합산, 아래) | 평균가·평당가·시세증감·최고가증감은 아파트, 거래량·매물수·거래증감·매물증감·선호도·전세가율·갭가격은 아파트·오피스텔 합산 |
| `--trade` | 평균가·평당가·시세증감·최고가증감은 매매·전세 중 하나, 거래량·매물수·거래증감·매물증감·선호도는 매매·전세·월세 여럿(반복하거나 쉼표로 구분). 동네정보 항목은 받지 않는다 | 매매 / 전체 |
| `--kind` | 동네정보 항목의 종류 하나 (아래 표) | 전체 (학원수는 입시) |
| `--order` | 높은순, 낮은순 | 높은순 |
| `--limit` | 범위: 1~100. (부동산 50곳, 동네정보·`-t 빌라` 30곳마다 요청 1회) | 20 |

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
jibsa dabang region-ranking 역삼동 --by 평균가 --unit 단지
jibsa dabang region-ranking 강남구 --by 거래증감
jibsa dabang region-ranking 강남구 --by 매물수 -t 빌라
jibsa dabang region-ranking 강남구 --by 과학고진학률
jibsa dabang region-ranking 서울 --by 학원수 --kind 입시 --limit 10
```

다방 '부동산 랭킹'과 '동네정보' 랭킹이다. 결과의 `tab` 이 다방 동네정보의 어느 탭 순위인지 알린다: 부동산 항목은 `"시세정보"`(아파트·오피스텔 단지 기준), `-t 빌라` 는 `"매물정보"`, 동네정보 항목은 `"학군"`·`"인구수"`·`"편의시설"`·`"교통/차량"`·`"생활안전"`. 부동산 순위는 결과의 `complex_type` 이 어느 단지 유형의 순위인지 알린다 (`"아파트"`·`"오피스텔"`·`"아파트·오피스텔 합산"`, 단지 유형을 받지 않는 세대수·연식과 동네정보 항목, `-t 빌라` 는 키가 없다). 거래량·매물수·선호도·전세가율·갭가격은 `-t` 를 주지 않으면 다방 웹 기본처럼 아파트·오피스텔 합산이다 (동·단지 순위 모두): 강남구 `--by 거래량` 은 합산 1위가 역삼동 298개, `-t 아파트` 는 1위가 개포동 233개였다 (2026-11-13). 금액·거래량은 국토교통부 실거래, 매물수·선호도(조회수·찜수·문의수 등을 합친 점수)는 다방, 진학률은 학교알리미 공시(그 동 학교 졸업생 중 그 학교로 간 비율), 인구는 행정안전부 기준이다. `rankings[]` 는 `rank`, `name`, `area`(상위 지역), 단지면 `complex_id`, `value_text`(다방 표시 값)와 항목에 맞는 값만 있다: 평균가·평당가·갭가격 `value_manwon`, 거래량·매물수·세대수·학교·학원·시설 수·인구 `count`, 전세가율·진학률 `percent`, 선호도 `score`, 시세증감·최고가증감 `change_manwon`(오른 금액, 현재가가 아니다)·`change_percent`·`prev_price_manwon`(앞 시세·앞 최고가), 인구증감 `count`(올해 인구)·`prev_count`·`change_count`(줄면 음수)·`change_percent`, 거래증감·매물증감 `count`(지금 수)·`prev_count`(견준 앞 수)·`change_count`(줄면 음수)·`change_percent`, 연식 `age_years`. 최고가증감은 `prev_price_month`(앞 최고가 달 `YYYY-MM`)도 주고 새 최고가는 `prev_price_manwon + change_manwon` 이다. 단지 순위는 `pyeong_name`(평형 이름), `price_month`(기준 달 `YYYY-MM`, 최고가증감은 새 최고가 달. 다방 글자를 읽지 못하면 키를 지우지 않고 `null` 이고 `[참고]` 가 `다방이 준 시세 기준 달 3건을 읽지 못해 null 로 냈습니다 (예: …)` 처럼 알린다. `prev_price_month` 도 같다), `price_detail`('매매 90억 / 전세 14.5억')도 준다. 시세증감·최고가증감 동 순위는 다방이 센 달을 `base_month`(YYYY-MM)로, 고른 종류는 `kind` 로 알린다. 다방이 값을 `'-'` 로 주는 줄(평균가처럼 값이 없는 동·단지)은 `value_text` 가 `"-"` 이고 그 항목의 값 필드는 `null` 이다. 거래증감·매물증감은 거래·매물이 없는 줄을 `'-'` 가 아니라 `"0개 (0%)"` 로 준다.

거래증감·매물증감은 다방 웹 '거래증감'·'매물증감' 순위다 (동·단지 모두). 결과의 `comparison` 이 무엇과 견줬는지 다방 화면 문구로 알린다: 거래증감 `"전월대비"`, 매물증감 `"최근 30일 전 대비"`. 다른 항목은 `comparison` 키가 없다. 줄마다 `prev_count` → `count` 로 읽고 `value_text` 는 다방 표시(`"73개 (+101.4%)"`)다: 강남구 거래증감 1위 논현동은 72 → 145 (`change_count` 73, `change_percent` 101.4, 2026-11-13). 앞 수가 0 이면 다방이 변화율을 `0%` 로 줘서 `change_percent` 가 0 이니 `prev_count`·`change_count` 로 본다.

`-t` 에 빌라를 넣으면 매물수·거래량·선호도를 다방 동네정보 '매물정보' 탭 순위로 받는다 (`tab` `"매물정보"`). 주택/빌라가 있는 순위는 이 탭뿐이고 동 순위만 있다. 고른 매물 유형(빌라·오피스텔·아파트)의 합산이고, 결과에 `complex_type` 대신 `property_type`(`"주택/빌라"`, 여럿이면 `"주택/빌라·아파트 합산"`)이 붙는다. 거래 유형은 여럿을 받는다 (기본 전체). '시세정보' 탭의 매물수·거래량·선호도와 값이 다르다 (강남구 `--by 매물수 -t 빌라` 1위는 역삼동 262개, 2026-11-14). 다른 항목에 빌라를 주거나 `--unit 단지` 와 함께 주면 입력 오류다.

동 범위는 `--unit 단지` 의 부동산 항목만 받는다 (다방 웹 단지 순위의 동 범위): `region-ranking 역삼동 --by 평균가 --unit 단지` 는 역삼동 안 아파트 순위로 1위가 개나리푸르지오 39.5억이었다 (2026-11-13). 결과 `scope` 는 `kind` `"dong"`, `name` `"서울특별시 강남구 역삼동"`, `legal_division_code` 10자리 법정동코드(`"1168010100"`)다. `--unit` 을 주지 않거나 `동` 이면(동 안의 동 순위는 없다) `INVALID_ARGUMENT` 이고 `hint` 가 `--unit 단지` 나 시·군·구 범위를 알린다 (`-t 빌라` 는 동 순위만 있어 시·군·구 범위만 알린다). 동네정보 항목(학원수·진학률 등)도 동 범위는 `INVALID_ARGUMENT` 다 (다방 웹에도 없다). 같은 이름의 동이 여럿이면(`신사동`) `REGION_AMBIGUOUS` 로 `'강남구 신사동'` 처럼 고르게 하고, 역·대학 이름은 `INVALID_ARGUMENT` 다.

학원수·진학률 순위는 `area` 가 시·도(`"서울"`)까지만 와서 범위가 전국·시·도면 같은 이름의 동(신사동)을 구별하지 못한다 (`[참고]` 로 알린다). 범위 찾기에 요청 1~2회가 더 든다. 구가 있는 시(`성남시`)는 구 이름을 붙이라고 `REGION_NOT_SUPPORTED`, 여러 시·도에 있는 시·군·구 이름(`중구`·`고성군`)은 시·도를 붙이라고(`'서울 중구'`) `REGION_AMBIGUOUS` 로 알린다. `광주시` 는 경기도 광주시이고 전남광주통합특별시는 `광주`·`전남광주` 로 준다.

## 검색 범위

| 입력 | room · villa · officetel | apt |
| --- | --- | --- |
| 동 이름 | 그 동 안 (`scope: "역삼동 안"`) | 동 경계를 덮는 사각형에서 그 동 매물만 |
| `○동N가` 로만 나뉜 동 (성수동) | 합쳐 찾지 않고 `REGION_AMBIGUOUS` 로 `○가` 동을 모두 후보로 준다. 하나(`성수동1가`)로 다시 부른다 | 같음 |
| 역 이름 | 다방이 정한 역 반경 (강남역 750m, `radius_km` 에 있다) | 같음 |
| 대학 이름 | 다방 대학 검색 범위 | 대학 중심 1km 반경 |
| `--lat/--lng` | 반경 1km | 같음 |
| `--radius` | 이름의 중심에서 그 반경 | 같음 |

반경은 반경을 덮는 사각형으로 받아 반경 밖을 빼고 뺀 수를 `notes` 로 알린다. 이때와 아파트 동 검색의 `total` 은 사각형 안의 수라 근사값이다. 매물 좌표는 다방이 몇 m 흔든 값이라 반경 경계 근처는 조금 다를 수 있다. 구·시 이름은 찾지 못한다 (`REGION_NOT_SUPPORTED`).

위치는 늘 하나만 찾는다. 후보가 여럿인 이름(`○가` 로 나뉜 동, 여러 캠퍼스에 맞는 `연세대`)은 고르지 않고 `REGION_AMBIGUOUS` 로 후보를 주니 후보 하나(`성수동1가`, `'연세대학교(원주캠퍼스)'`)로 다시 부른다. 이름이 똑같은 역이 여럿이어도 `REGION_AMBIGUOUS` 지만 후보는 `역 이름 (노선)` 꼴이라 이름으로 다시 가를 수 없다. `hint` 대로 `search locations` 에서 그 역의 좌표를 보고 `--lat/--lng` 로 준다. 매물 검색·`search complexes`·`search sales` 모두 같다. 동만 받는 `neighborhood`·`hot-places`·`popular-listings`·`search schools` 와 역만 받는 `station-prices` 는 그 종류의 후보만 이렇게 알리고(`station-prices` 는 좌표를 받지 않아 이름이 똑같은 역을 가려 받지 못한다), 받지 않는 종류의 이름(`neighborhood 연세대`)은 후보를 고르라고 하지 않고 바로 `INVALID_ARGUMENT` 다.

## 조회 한도

매물 검색(`room`·`villa`·`officetel`·`apt`·`--complex`)의 `--limit` 은 기본 24·최대 120이다. 다방은 한 쪽에 24건씩(가끔 더 적게) 주고 요청은 쪽마다 1회다. 쪽이 짧으면 `--limit` 이 찰 때까지 쪽을 더 받고, 10쪽까지(그 목록의 최대 `--limit` 을 꽉 찬 쪽으로 채우는 쪽 수의 두 배, 30곳씩 오는 `search schools`·`hot-places` 는 8쪽) 받고도 못 채웠는데 더 있으면 `[일부]` 로 알린다 (매물 검색은 `next` 로 이어 받는다). 다방이 더 있다고 한 뒤 다음 쪽 결과를 주지 않아 멈춰도 `[일부]` 로 받은 수를 알린다 (`search complexes`·`search sales`·`search schools`·`hot-places` 도 같다). 받은 원본 수로 조회 예산을 세고, 받은 뒤 뺀 매물(반경 밖·다른 동·광고)만큼 다시 채우지 않는다. `total`·`has_more` 는 다방이 센 값이라 `next` 로 끝까지 이어 받을 수 있다. `search complexes` 는 기본 24·최대 120이고 매물 검색처럼 받은 단지 수로 센다 (아파트 동 검색에서 뺀 다른 동 단지만큼 다시 채우지 않는다). `search complexes`·`search sales` 도 10쪽까지 받고 못 채웠는데 더 있으면 `[일부]` 로 알린다. 둘은 `next` 가 없어 안내대로 지역·반경·조건을 좁혀 다시 찾는다. `real-price` 는 기본 30·최대 200(50건마다 1회)이다. `search schools`·`hot-places` 는 기본 30·최대 120(30곳마다 1회)이다.

가격 조건만 주고 `--trade` 를 생략하면 그 금액이 있는 거래로 좁히고 `notes` 로 알린다 ([공통 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/common.md#출력-규칙)).

## 출력 읽기

| 필드 | 용도 |
| --- | --- |
| 매물 `id` | `listing`·`real-price --listing` 에 그대로 전달 |
| `listing_number` | 다방 화면의 매물번호. `listing` 에 `id` 대신 줄 수 있다 |
| `complex_id` | `complex`·`search listings --complex`·`real-price`·`price-trend`·`nearby-complexes` (`nearby-complexes` 의 주변 단지 `nearby` 안 것도 같다) |
| `pyeongs[].pyeong_id` | 평형 조건 `--pyeong` |
| `schools[].school_code` · `level` | `school` 의 학교 코드와 `--level` (`complex`·`search schools`) |
| `nurseries[].school_code` · `kindergartens[].school_code` | `school <code> --level 어린이집`·`유치원` |
| `presale_id` | `sale`, `nearby --sale` (위치 인자가 아니다) |
| `scope` · `radius_km` | 찾은 범위 |
| `notes` | 범위·제외·일부 안내 |
| `url` | 원 사이트(다방 지도 화면)에서 확인·문의 |

다방이 목록 안에 빈 항목(null)을 보내면 그 항목을 빼고 읽고 `[제외]` 로 알린다 (안내 끝에 'jibsa 업데이트가 필요할 수 있습니다' 가 붙고 매일 감시가 고장으로 잡는다). 빈 항목도 서버가 센 한 칸이라 쪽 넘김과 `--limit` 을 채웠는지 셀 때 더하고, 그 목록으로 계산한 값(동네정보 `count`, 인기 매물 `rank`, `sale-schedule` 의 `total`, 관리비 항목)은 `null`(모름)이다.

## 소스별 반환 필드와 해석

| 조회 | 필드 | 뜻 |
| --- | --- | --- |
| 매물 목록 | `short_term` | 단기임대(1개월 이상) 계약도 받는 월세 매물. 다방의 단기임대는 따로 있는 거래가 아니라 월세 매물에 붙는 표시라 `trade_type` 은 `"월세"` 다. 보증금이 월세 한두 달치(예: 95/95)면 단기 계약 가격일 수 있다. 월세가 아니면 키가 없다 |
| 매물 목록 | `address` | 찾은 동의 매물은 시·구까지, 그 밖의 매물은 동 이름만이다. 그래서 동 이름에 `--radius` 를 주면 둘이 섞이고, 역·대학·좌표로 찾으면 모두 동 이름만이다. 시·구까지는 `listing` 상세 |
| 매물 목록 | `area_m2`·`supply_area_m2` | 아파트(아파트 목록·단지 매물·인기 매물, 원룸·투룸 목록에 섞인 아파트)는 다방이 공급면적만 줘서 `area_m2` 가 `null` 이고 `supply_area_m2` 가 공급면적이다. 그 밖은 `area_m2` 가 전용면적이고 `supply_area_m2` 키가 없다 |
| 매물 목록 | `floor` | `"5"`, `"반지하"`, `"저층"`·`"중층"`·`"고층"` (다방이 층을 숨긴 매물) |
| 매물 목록 | `room_type` | 다방이 투룸·쓰리룸으로 밝힐 때만. 원룸은 오픈형·분리형을 알 수 없어 `null` |
| 매물 목록·상세 | `manage_cost_manwon` | 목록은 다방 표시('관리비 7만')를 읽은 값이고 `0` 은 관리비 없음, `null` 은 모름이다 |
| 상세 | `residence_type` | 건축물 용도 (`"단독주택"`, `"공동주택"` ...). 근린생활시설이면 전입신고·전세대출이 막힐 수 있다 |

## 매물 해석 시 주의사항

다방은 웹에서 중개 매물만 보여 준다 (직거래 없음). 원룸·투룸 목록에는 오피스텔·아파트(방 1~2개)가 섞이고, 아파트 목록에는 다방이 아파트로 분류한 주상복합·도시형 건물이 섞인다. 다방의 분류를 다시 거르지 않으니 `property_type`·`complex_name`·상세의 `residence_type` 으로 본다.

`short_term: true` 매물은 같은 지역 월세의 절반을 넘기도 한다 (역삼동 원룸 월세에서 약 2/3). 보증금이 아주 낮은 월세는 단기 계약 가격일 수 있으니 `listing` 상세의 `short_term_period` 과 원 사이트에서 장기 계약 조건을 확인한다.
