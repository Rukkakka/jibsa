# 다방 개발 가이드

[CLI 사용법](../../dabang.md) · [개발 환경·검증](../README.md) · [공통 아키텍처](../architecture.md) · [provider 작성 규약](../provider-conventions.md) · [출력 계약](../output-contract.md) · [코드 형식](../code-style.md)

공통 규약에 없는, 다방에만 있는 구현과 예외를 적는다. 엔드포인트와 필드의 뜻은 `api/client.py` docstring 과 `api/response/` 모델에 있다.

## 명령과 요청 흐름

| CLI 명령 | 주요 경로 | service 모듈 |
| --- | --- | --- |
| `search locations` | `loc/search` (동·역·대학·단지 한 번에) | `region` |
| `search listings room·villa·officetel·apt` | 이름 해석(`loc/search`) → `room-list/category/{유형}/{region·subway·univ·bbox}` 24건씩. 아파트 동은 동 경계(CDN) → `bbox` | `listing` |
| `listing` | (매물번호면 `room/get-room-id`) → `new-room/detail` | `listing` |
| `search complexes` | 이름 해석 → `complex-list/category/{apt·officetel}/{…}` | `complex` |
| `complex` | `complex/{id}` + `complex/{apt·officetel}/summary` | `complex` |
| `school` | `3/education/{elementary·middle·high}-school/{코드}` | `school` |
| `search listings --complex` | `complex/{id}` (평형·유형) → `room-list/category/{apt·officetel}/complex` | `complex` |
| `real-price` | (`--pyeong` 없으면 `complex/{id}`) → `real-price/complex/histories`, `--listing` 은 `real-price/house/history` | `real_price` |
| `price-trend` | (`--pyeong` 없으면 `complex/{id}`) → `real-price/complex/charts` | `real_price` |
| `neighborhood` | 이름 해석 → 주제마다 `region-info/{room·real-estate·population}/regional/summary` 또는 `region-info/{school·amenity·mobility·life-safety}/regional/count` | `neighborhood` |
| `popular-listings` | 이름 해석 → `region-info/room/regional/popular-room` 50건씩 | `neighborhood` |
| `nearby` | `transit/near/{room·complex}` + `{room·complex}/{id}/near` | `nearby` |
| `station-prices` | 이름 해석 → `markers/category/one-two` (역을 덮는 지도 범위, 확대 16) | `nearby` |
| `search sales` | 동: 동 경계 / 시군구: `region?code=` → 시군구 경계(CDN) / 역·좌표: 반경 사각형 → `sale-list/category/bbox` 24곳씩 | `sale` |
| `sale` | `3/sale-in-lots/detail2` | `sale` |
| `sale-schedule` | `3/sale-in-lots/list/schedule` (7일까지) | `sale` |
| `trending-complexes` | `real-time-watch-rankings/{complex·region}` | `ranking` |
| `trade-rankings` | `real-price/trade/rankings/complex` | `ranking` |
| `region-ranking` | 범위 해석(`region/states` 또는 `loc/search` → `region?code=`) → 부동산 `region-info/real-estate/ranking/{region·complex}/{항목}` 50곳씩, 동네정보 `region-info/{school·population·amenity·mobility·life-safety}/ranking/{항목}` 30곳씩 | `ranking` |

단지 상세(`complex/{id}`)는 `complex`·`real_price` 가 같이 불러 요청·응답 모델과 `fetch_complex` 가 `common` 에 있다.

## 소스 고유 구현

### 두 API 방식과 헤더

- 새 방식 `/api/v5/` 는 웹이 붙이는 헤더(`D-Api-Version: 5.0.0`, `D-App-Version: 1`, `D-Call-Type: web`, `V5_HEADERS`)를 붙이고, 응답 봉투 `{code, msg, result}` 의 `result` 를 쓴다. 키는 camelCase.
- 옛 방식 `/api/3/`(상세·매물번호)은 헤더 대신 쿼리에 `api_version=3.0.1&call_type=web&version=1` 을 붙이고(`DabangV3RequestParameterModel`) 봉투 없이 snake_case 로 온다.
- 모든 요청에 웹 axios 인스턴스가 붙이는 `csrf: token` 헤더를 붙인다. 토큰·쿠키는 없다.
- 없는 주소·경로 값은 404 대신 **403 빈 응답** 이다 (아무 경로나 넣어도 같다). 요청 제한과 섞지 않는다. ID 가 경로에 들어가는 요청(단지 상세·주변 시설·학교)만 `is_missing_id` 로 빈 403 을 `NOT_FOUND` 로 본다. ID 가 쿼리로 가는 요청(분양 상세·교통·단지 실거래·매물 실거래·시군구 코드)은 없는 ID 에 400 이나 빈 결과를 줘서(2026-10-27 실측) 빈 403 이면 다방 주소가 바뀐 것으로 `UPSTREAM_ERROR` 다 (`in_path=False`).

### 매물 목록 (`search listings`)

- 다방 목록은 유형(`one-two`·`house-villa`·`officetel`·`apt`)마다 따로이고 필터 항목도 다르다. **필터 항목이 하나라도 빠지면 400** 으로 빠진 항목을 한국어로 알려 준다. 그래서 유형마다 요청 모델(`DabangOneTwoFiltersModel` 등)을 두고 주지 않은 항목을 '전체' 값(`{min: 0, max: 999999}`, 모든 목록 값)으로 채운다. `zoom`·`useMap=naver` 도 필수다 (`ZOOM_BY_SEARCH_TYPE`: 동 14, 역·대학 15, 지도 16).
- 필터 범위 값은 하한·상한 모두 999999 까지만 받는다 (넘으면 400 '최대값은 999999 이하로 입력해주세요'). 큰 상한은 `range_of` 가 999999 로 줄이고 큰 하한은 CLI 가 막는다. 압구정·청담·한남동 아파트 매매도 98억까지라 999999 로 빠지는 매물은 보지 못했다.
- 한 쪽은 24건 고정이고 `limit` 을 보내도 무시한다. `total`·`hasMore` 는 일반 목록 기준이라 정확하다. 이어 받기 위치는 범위마다 받은 수(`{"offsets": {범위: 수}}`)이고, 쪽 번호(`수 // 24 + 1`)와 쪽 안 위치(`수 % 24`)로 다시 묻는다.
- 가격·층·면적·관리비는 숫자 없이 글자(`priceTitle` '1억2000/50', `roomDesc` '5층, 19.83m², 관리비 7만')로만 온다. `manwon_from_text`·`listing_prices`·`parse_room_desc` 가 읽고, 읽지 못한 매물은 빼고 `notes` 로 알린다 (`tests/test_dabang.py`). 단지 목록·요약은 억 뒤에 띄어쓰기·쉼표를 넣는다('31억 3,000'). 다방은 반지하를 '반지층' 으로 쓴다.
- `roomDesc` 의 면적은 원룸·빌라·오피스텔이면 상세 전용면적(`room_size`)이지만 **아파트면 공급면적**(`provision_size`)이다. 아파트 목록·단지 매물·인기 매물과 원룸·투룸 목록에 섞인 아파트 모두 같고, 목록 칸에 전용면적은 없다. 그래서 아파트는 `area_m2` 를 `null` 로 두고 `supply_area_m2` 에 넣는다 (`room_item_to_listing`). 아파트 목록의 평 조건(`pyeongRange`)도 공급 평으로 걸린다 (34평 → 공급 112~113㎡).
- 다방 단지 목록(`complex-list`)은 쪽마다 순서가 흔들려 앞 쪽 끝 단지를 다음 쪽 첫머리에 다시 준다 (정렬 옵션 없음, 잠실동 3쪽 71줄 중 69곳). 단지 ID 로 한 번만 넣고 `[제외]` 로 알린다. 매물 목록은 이어 받기 결과가 한 번에 받은 결과와 같아 겹침을 보지 못했지만 같은 방법으로 거른다.
- 원룸·투룸 목록은 매매를 받지 않는다 (매매만 보내면 무시하고 월세를 준다). 그래서 `room` 의 `--trade` 에서 매매를 뺐다.
- 단기임대는 별도 거래가 아니라 월세 매물의 표시(`roomTypeName` 의 ' • 단기', 상세 `short_lease_str`)다. `trade_type` 을 단기임대로 바꾸지 않고 `short_lease` 로 알린다. 보증금 1000·월세 90 같은 보통 월세에도 붙어, 단기임대로 바꾸면 `--trade 월세` 검색에서 월세 대부분이 빠진다.
- 원룸·투룸 목록에 오피스텔·아파트가, 아파트 목록에 주상복합·도시형이 섞여 온다. [공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)대로 다시 거르지 않는다. 주택·빌라 목록은 매물을 방 개수(원룸·투룸)로 표시해 `property_type` 을 '빌라' 로 둔다.
- 광고(`premiumList`, 광고 중개사별 매물)는 일반 목록과 따로 오고 `total` 에 들지 않는다. 넣지 않고 뺀 수만 `notes` 로 알린다.
- 사용승인 조건(`useApprovalDateRange`, `--built-within`)은 날짜가 아니라 연도로 센다. 2026-10-31 실측: `{max: 2}` 에 2024-02-21 승인(신림동·화곡동 16건 중 가장 오래된 것), `{max: 10}` 에 2016-02-03 승인 건물이 들어오고 그 앞 해 승인은 없었다. 서버 필터라 다시 거르지 않고(목록에 사용승인일도 없다) `search_listings` 가 기준 날짜(`올해 - N` 년 1월 1일)를 `[참고]` 로 알린다. 날짜로 따지려면 `--details`(`attach_details`)가 앞 30건에 상세(`get_listing`, 1회씩)의 사용승인일·건물 용도를 붙인다. 상세에서 내려간 매물은 뺀다.
- 목록 좌표(`randomLocation`)는 다방이 몇 m 흔든 값이다. 거리(`distance_km`)와 반경 판정에만 쓰고 출력하지 않는다.

### 위치 해석 (`region`)

- `loc/search` 는 시·군·구를 주지 않는다 (`강남구` 를 찾으면 강남구의 동들). 구·시 이름은 `REGION_NOT_SUPPORTED` 로 막는다. 행정동은 결과가 없어 `legal_dong_hint` 를 붙인다.
- 고르는 순서는 이름이 똑같은 동 → 역('역' 으로 끝나면 역 먼저) → 대학 → `○동N가` 동이다. 같은 이름의 동이 여럿이면 `REGION_AMBIGUOUS`, '강남구 신사동' 처럼 앞 낱말이 있으면 동의 전체 이름에 그 낱말이 든 후보만 본다. 시·도 줄임말('서울 신사동')은 `SIDO_OFFICIAL_NAMES` 의 정식 이름으로도 맞춘다 (전체 이름은 '서울특별시 …'). 대학은 이름이 똑같은 곳을 먼저 보고, 없으면 앞부분이 맞는 곳 중 첫 곳을 `[모호]` 로 알린다 ('연세대' 는 세 캠퍼스). 장소 검색은 괄호가 든 검색어에 0건이라 괄호를 띄어 보낸다.
- `○동N가` 로만 나뉜 동(성수동)은 동마다 `region` 목록을 받아 합친다. `--limit` 을 아직 끝나지 않은 동끼리 나누고 앞 동이 덜 주면 남은 몫을 다음 동이 받는다. 마지막까지 남은 몫은 매물이 남은 앞 동부터 받는다 (그 동의 마지막 쪽에서 남긴 칸을 먼저 써 같은 쪽을 다시 묻지 않는다. 2026-10-25 실측: 문래동 원룸 `--limit 6` 이 7건 중 5건만 내던 것). 이어 받을 때는 끝난 동을 다시 받지 않고, 이어 받기 표(`finished`: 동마다 받은 수·다방이 센 수)에 남긴 수를 `total`·몇 번째에 더해 첫 결과와 같게 한다. 동이 `--limit` 보다 많아 몫이 0 인 동(을지로1가~7가를 `--limit 3` 으로)은 묻지 않고 이어 받기 표에 0 으로 남긴다. 그 동의 수를 몰라 `total` 은 `null` 이다. 이어 받기 표에는 첫 결과가 찾은 위치(동 코드·역 번호 포함)도 남겨 `--next` 때 장소 검색을 다시 묻지 않는다.
- 아파트 매물 목록·아파트 단지 목록은 동·대학 검색이 없다 (403). 오피스텔 단지 목록은 동(`region`)·대학(`univ`) 검색이 된다 (2026-10-26 실측: 역삼동 97곳, 홍익대학교). 동은 다방 지도 집계가 주는 동 경계 파일(`d2pi55cyzoqmrc.cloudfront.net/geojson/region/{8자리 코드}`)로 사각형을 만들어 `bbox` 로 받고, 목록의 동 번호(`gid`)가 그 동인 것만 남긴다. 대학은 1km 반경이다. 경계 파일도 같은 요청 제한 훅을 거친다. 아파트 매물 검색은 사각형을 이어 받기 표(`next`)에 남겨 `--next` 마다 경계를 다시 받지 않는다.
- 역은 다방이 정한 역 반경(강남역 750m, `loc/search` 의 `radius`)이고, `--radius` 를 주면 그 반경을 덮는 사각형으로 받아 반경 밖을 뺀다. `○가` 동 여럿에 `--radius` 를 주면 동 중심들의 가운데를 중심으로 한다 (`middle_place`, 매물·단지·분양 검색).
- 목록 주소는 찾은 동(`gid`)의 매물만 시·구까지 붙인다. 목록 칸에는 동 이름만 있어 다른 동의 시·구는 모른다. 그래서 동 이름에 `--radius` 를 주면 두 꼴이 섞인다.
- 동 코드는 법정동코드 앞 8자리다. 출력은 뒤에 `00` 을 붙여 10자리로 맞춘다. 다방은 이미 '전남광주통합특별시'(시·도 코드 12)를 쓴다.

### 상세·단지·학교·실거래

- 상세 유형(`room_type_str`)은 목록과 달리 구조를 붙여 온다 ('오피스텔(분리형)'·'원룸(분리형,복층)'). 단지 ID·이름은 다방이 주면 유형과 상관없이 두고, 없을 때만 앞부분이 오피스텔·아파트인지로 해당 없음(키 삭제)과 모름(`null`)을 가른다 (`is_complex_type`).
- 상세 `price_info` 는 `[보증금 또는 매매가, 월세, 거래 유형 코드]` 숫자(만원)다 (0 월세, 1 전세, 2 매매). 화면처럼 `status` 0·3·4 는 비공개로 보고, `is_contract` 도 거래 불가로 본다. 없는 매물은 400 "존재하지 않는 매물입니다."(매물번호는 "존재하지 않는 방입니다.")다. 다른 소스 ID 를 넣어도 이 응답이라 사유를 `ListingUnavailableError` 에 넘기지 않는다 (넘기면 다른 소스 ID 힌트가 빠진다).
- 관리비 포함 항목은 `maintenance_items_str` 이 비면 `maintenance_etc_fee_charge_detail.detail_include_types` 코드를 웹의 표(`MANAGE_ITEM_LABELS`)로 바꾼다. 정액 관리비가 10만원 이상인 매물(`maintenance_charge_detail_type: ABOVE_FIXED_FEE_THRESHOLD`)은 둘 다 비고 `maintenance_fixed_fee_charge_detail_list` 에 항목(F01 공용·F11 전기·F12 수도·F13 가스·F14 난방·F15 인터넷·F16 TV·F99 기타)마다 `FIXED_FEE`(관리비에 듦)·`ACTUAL_EXPENSE`(실비)로 온다. 웹처럼 정액 항목만 포함 항목으로 본다 (`FIXED_FEE_ITEM_LABELS`).
- 옵션의 '벽걸이형'·'스탠드형'·'천장형' 은 웹이 에어컨 목록(`airConditionerTypeList`)의 이름을 그대로 옵션에 섞은 것이라 '에어컨' 을 붙인다. 오피스텔은 공급면적(`provision_size`)을 0 으로 주기도 해서 `null` 로 둔다.
- 단지 상세의 `buildCovRatio`·`floorAreaIndex` 는 이름과 값이 뒤바뀌어 온다 (`buildCovRatio` 가 용적률). 응답 모델이 뜻대로 이름을 붙였다.
- 단지 상세의 학교(`education`)는 초등학교가 배정 학교(통학구역), 중·고등학교가 단지가 든 학교군의 학교 전부(은마 17곳·22곳)를 거리순으로 준다. 학급당 학생 수·진학 인원은 글자('24명', '대학교 163명')라 `count_of` 로 읽는다. 어린이집·유치원도 오지만 넣지 않는다.
- 학교 상세(`3/education/{단계}-school/{코드}`)는 단계와 코드가 맞지 않거나 없는 코드면 404 가 아니라 **500** "일시적으로 서비스가 지연되고 있습니다." 다. 코드만으로 단계를 알 수 없어 CLI 가 `--level` 을 받는다 (단계를 차례로 불러 보면 요청이 늘어난다). 다시 보내도 같은 500 이라 이 엔드포인트만 500 을 재시도하지 않는다 (`dabang_education_retry`, [재시도 규약](../provider-conventions.md#요청-메서드)의 예외). 서버 고장도 같은 500·같은 본문이라 가르지 못해, 500 이면 `NOT_FOUND` 로 단정하지 않고 `UPSTREAM_ERROR`(`status` 500)와 입력을 다시 보라는 hint 를 낸다 (매일 감시는 이것을 '확인 못 함'으로 본다). 개교일·개교기념일('1986.21')은 달이 맞지 않아 쓰지 않는다. 학교 코드는 학교알리미 코드('S010000743')라 네이버(`B10…`) 코드와 다르다.
- 단지 요약(`complex/{유형}/summary`)은 경로 가운데에 단지 ID 가 아니라 소문자 유형이 들어간다.
- 실거래 기간은 최대 36달이다 (37달이면 400). 요청 모델이 막는다. 한 번에 50건까지 받는다. 쪽은 `(page - 1) × limit` 번째부터라 쪽마다 `limit` 을 바꾸면 앞 쪽과 겹친다. 쪽 크기를 고정하고 넘치는 건 자른다 (인기 매물도 같다).
- 없는 단지·평형은 실거래·시세 흐름 모두 400 과 사유("존재하지 않는 단지입니다."·"존재하지 않는 평형 정보입니다.")를 준다. 사유를 보고 `NOT_FOUND`·`INVALID_ARGUMENT` 로 바꾼다.
- 단지 상세의 최근 실거래 요약(`complex/{유형}/summary`)은 덤 조회다. 실패하면 `recent_sale`·`recent_lease` 를 `null` 로 두고 `[실패]` 로 알린다. 요청 거절(4xx)·응답 형식 변경이면 `UPDATE_MAYBE_NEEDED` 를 붙이고, 요청 제한·5xx·연결 실패면 붙이지 않는다. 매일 감시는 은마의 `recent_sale` 로 요약이 깨졌는지 보고, 업데이트 문구 없는 `[실패]` 로 비면 확인 못 함으로 둔다. 요약 거래의 면적(`formatRoomSize`)은 아파트면 공급면적, 오피스텔이면 계약면적이고 평형 번호가 없다. 평형표의 공급·계약면적과 같은 평형을 찾아 `space_seq` 와 전용 `area_m2` 를 낸다 (은마 115.54㎡ → 34평 전용 84.43㎡).
- 시세 흐름의 달 목록은 매매 쪽(`sale.statistics`)으로 만든다. 매매가 한 건도 없는 평형도 `sale` 이 `null` 이 아니라 거래 0건인 36달로 오고, 전월세와 달이 같다. 거래 없는 달은 앞 달 평균을 잇는데 이을 평균이 없으면 `averagePrice` 가 0 이라 `null` 로 바꾼다.
- `real-price/house/history` 는 그 매물의 건물이 아니라 같은 동의 같은 건물 유형 거래를 준다 (`historyBaseType: DONG`). 결과 `basis` 와 `notes` 로 알린다. 없는 매물·단지 매물에는 에러 대신 `dongName`·`historyBaseType` 이 `null` 인 0건을 줘서 `NOT_FOUND` 로 바꾼다 (거래가 0건인 매물도 동·범위는 온다).
- 매물·단지 주소 `/room/{id}`·`/complex/{id}` 는 서버가 지도 화면으로 넘겨 준다 (302).

### 동네·주변 (`neighborhood`·`popular-listings`·`nearby`·`station-prices`)

- 동네정보는 탭마다 주소가 둘이다: `summary`(항목 하나의 값과 전국·시도·구 순위, `summaryType` 하나씩)와 `count`(그 탭 항목별 수를 한 번에). 요청을 아끼려고 매물·거래·시세·인구는 `summary`, 학교·편의·교통·안전은 `count` 만 부른다. 수와 순위는 글자('1,074개', '60위')로 와서 숫자로 바꾼다. 출처는 화면 문구대로 매물 수·선호도는 다방, 거래량·평균가는 국토교통부, 인구는 행정안전부다.
- 인기 매물은 선호도(조회수·찜수·문의수 종합 점수) 순위다. 매물 칸에 동 번호·좌표가 없어 주소는 찾은 동으로 채운다. 매물 유형은 주택/빌라·오피스텔·아파트뿐이다. 칸에 건물 유형도 없어 여러 유형을 섞어 받으면 '오피스텔'·'아파트' 표시는 그 이름으로, 방 개수 표시('원룸'·'투룸')는 빌라로 본다 (`POPULAR_KIND_BY_ROOM_TYPE`).
- `{target}/{id}/near` 의 시설 종류 `query` 는 카카오 장소 분류 코드(MT1·CS2·CE7·BK9·PM9·PO3·SW8)와 다방 코드(BS·POLICE·CCTV·NS·KS·ES·MS·HS)다. 대상마다 주는 종류가 다르다: 매물은 CS2·CE7·BK9·PO3, 단지는 MT1(마트)·CS2·BK9·PM9(약국). 웹에 코드 이름표가 없어 이름은 카카오 분류 뜻대로 붙인다. 시설 목록은 거리순이 아니라서 가장 가까운 곳은 거리로 고른다. CCTV 는 이름·범위가 없어 쓰지 않는다. 시설 좌표는 내보내지 않는다.
- 역 둘레 평균 매물가는 원룸·투룸 지도 집계(`markers`)의 역 표시에만 붙는다 (빌라 집계는 원룸·투룸 평균만, 아파트 집계는 없음). 웹은 '평균 매물가' 라고 부르며 실거래가가 아니다. 역을 덮는 작은 지도 범위(±0.3km, 확대 16)로 부르고 역 번호가 같은 표시를 고른다.

### 분양·순위 (`search sales`·`sale`·`sale-schedule`·`trending-complexes`·`trade-rankings`·`region-ranking`)

- 분양 목록은 지도 범위(`bbox`)만 받고 칸에 좌표·동 번호가 없다. 동·시군구 이름은 경계를 덮는 사각형으로 받아 주소(`address`)가 그 동·시군구로 시작하는 단지만 남긴다. 시군구 경계도 동 경계와 같은 CDN 에 5자리 코드로 있다. `recommendList` 는 범위와 상관없는 추천 칸이라 넣지 않는다.
- 분양 상세는 옛 방식(`/api/3/`)이고 `provider_name` 이 시공사, `constructor_name` 이 시행사다. 상담 전화(`contact`)는 옮기지 않는다. 일정 날짜는 '26.09.07'(날)·'26.08월'(달) 꼴이라 `sale_date` 가 `YYYY-MM-DD`·`YYYY-MM` 으로 바꾼다. 청약 일정은 7일을 넘기면 400 이라 요청 모델이 막는다. 일정 칸에는 글과 좌표뿐이라 `--region` 은 글 앞의 시·도 줄임말('충북')을 정식 이름으로 바꿔 비교한다. 글이 시·도 없이 시('익산')나 단지 이름으로 시작하면 지역을 모르는 것으로 두고 거를 때 빼서 수를 알린다.
- `search sales` 는 이름 모양(전국·시·도·구·군·시로 끝남)이면 먼저 `resolve_scope` 로 범위를 찾고, 범위로 찾지 못하면 동·역으로 다시 찾는다. '홍대입구'·'을지로입구' 같은 역도 '구' 로 끝나기 때문이다. 다시 찾을 때는 범위를 찾느라 받은 장소 검색 결과를 넘겨(`searched`) 같은 요청을 두 번 보내지 않는다.
- 범위 이름은 `resolve_scope` 가 푼다: 시·도는 `region/states`, 시·군·구는 장소 검색 동 코드 앞 5자리로 `region?code=`. 장소 검색은 '중구' 에 서울·부산·대구·대전·울산 중구의 동을 섞어 주므로 시·군·구가 둘 이상이면 `REGION_AMBIGUOUS` 로 시·도를 붙이게 한다 (장소 검색이 동을 50곳까지만 줘 후보에 빠진 시·도가 있을 수 있다). 다방은 구가 있는 시(성남시)를 지역으로 두지 않고, 시 코드(41130)를 물으면 다른 지역(서초동)을 돌려준다. 그래서 받은 코드가 물은 코드와 같은지 보고, 구가 있는 시는 구 이름을 붙이게 한다. 공통 시·도 표(`SIDO_OFFICIAL_NAMES`)에 옛 광주광역시로 있는 '광주시' 는 다른 소스(당근 `--city`·네이버 `regions`)처럼 경기도 광주시로 본다 (`state_name`, 범위·분양·청약 일정 지역). 동·범위 이름의 앞 낱말('광주시 송정동')도 경기도 광주시로 먼저 맞추고, 맞는 곳이 없을 때만(경기도 광주시에 없는 구를 붙인 '광주시 광산구') 시·도 표대로 넓힌다 (`_in_context`, 네이버 `regions` 와 같은 규칙). 늘 넓히면 '광주시 송정동' 이 경기도 광주시와 광산구 두 곳에 맞았고 (2026-10-28 실측), 넓히지 않으면 '광주시 광산구 송정동' 을 못 찾았다 (2026-10-30 실측). `search sales` 는 `--radius` 를 줘도 시·군·구 이름인지 먼저 보고 그러면 `INVALID_ARGUMENT` 로 막는다.
- 순위 항목마다 받는 값과 값 글자 키가 다르다 (`MetricSpec`): 평균가·평당가·시세증감은 `priceType` 하나, 거래량·매물수는 `priceTypeList`, 전세가율·갭가격은 단지 순위에만 있고 유형만, 세대수·연식은 아무것도 받지 않는다. 값은 '61.1억'·'27개'·'133.3%'·'44년 6개월'·'+0.8%' 글자라 항목에 맞는 숫자 필드로 바꾼다. 거래·매물이 없는 줄은 '-' 로 와서(세종 동 평균가 33곳 중 8곳) 그 결과의 다른 줄에 있는 칸을 `null` 로 둔다. 둘째 쪽부터는 50곳씩 받아 `--limit` 에 맞춰 자르므로 자른 줄이 있으면 서버 `hasMore` 와 상관없이 `has_more` 다. 시세증감의 `formattedPrice` 는 현재가가 아니라 변화 금액이다 (대우로얄카운티II 19.6억 = 27.7억 → 47.3억, +70.8%).
- 거래 순위는 `limit` 을 작게(2) 보내면 500 을 준다. 웹처럼 50으로 받고 자른다. 조회 순위는 `limit` 과 상관없이 늘 50곳이다. 둘 다 전국 단위다. 거래 순위는 막 시작한 기간(월요일 아침의 이번주)에 빈 목록이라, 비면 `PREVIOUS_TRADE_PERIOD` 의 지난 기간을 `[참고]` 로 권한다. 매일 감시는 이 때문에 `--period 지난주` 로 본다.
- 최고가증감은 시세증감처럼 `formattedPrice` 가 오른 금액이고, 앞 최고가는 `formattedPrevPrice` 가 아니라 `formattedMaxPrice`·`formattedMaxPriceDate` 로 온다 (강남구 단지 1위 아이파크삼성 15.2억 = 62.8억 × 24.2%). 단지 순위의 `formattedPriceDate` 는 새 최고가 달, 동 순위는 줄 대신 결과에 기준 달('26년 10월')이 와서 `base_month` 로 낸다.
- 동네정보 순위(`region-info/{주제}/ranking/{항목}`, `InfoMetricSpec`)는 동 단위만 있고 한 쪽이 **30곳까지** 다 (31 이면 400 '페이지 당 호출 가능한 최대 행수는 30를 초과할 수 없습니다'). 학원 순위는 `academyType` 이 없거나 'ALL' 이면 빈 목록이라 늘 보낸다 (기본 입시). 진학률은 `schoolType`(중학교 → 고교 유형, 고등학교 → 대학)과 `schoolAdvancementType` 을 늘 보낸다. 학교 수·시설 수의 종류(`schoolEstablishmentType`·`facilityType`)와 인구의 성별·연령은 주지 않으면 전체다. 인구 증감의 변화 수는 부호 없이('327명') 와서 `changeStatus`·변화율 부호로 음수를 만든다. 학원·진학률 순위는 `parentRegionName` 이 시·도('서울')뿐이라 범위가 시·군·구가 아니면 `[참고]` 로 알린다.

## 원본 금액 단위

| 원본 응답 | 단위·처리 |
| --- | --- |
| 목록 `priceTitle`, 상세 `price_info`, 실거래, 평당가, 시세 흐름 | 만원 |
| 목록 `roomDesc` 의 관리비 ('관리비 7만') | 만원 글자. '관리비 없음' 은 0 |
| 상세 `maintenance_cost` | 원. `won_to_manwon` |
| 단지 평형 `maintenanceTotalPrice` | 원. `won_to_manwon` |
| 동네정보 평균가 `salePrice`·`leasePrice` | 만원 |
| 역 평균 매물가 `lease`·`monthlyRent` | 만원 글자 ('2억1333', '7937/65') |
| 분양 `priceTitle`·`price_str`·`pyeong_price` | 만원 글자 ('7억9096', '7억9096 ~ 8억1214', '1789') |
| 순위 `formattedPrice` | 만원 글자 ('61.1억', '4,762만') |

## 페이지네이션과 조건 처리

모든 매물 조건은 다방 서버가 건다 (서버 필터를 적용한 조회). 받은 뒤 빼는 것은 반경 밖(반경 검색), 다른 동(아파트·단지 동 검색), 가격을 읽지 못한 매물, 다방 목록에 두 번 나온 매물·단지(두 동에 함께 나오거나 다음 쪽에 다시 온 것)뿐이고, 뺀 만큼 다시 채우지 않는다. 다방 매물은 거래 조건이 하나라 거래 조건 선택이 없다.

검색 조건 묶음은 `DabangListingConditions`(`common`) 하나다. 유형마다 받는 조건이 달라 CLI 가 유형별 하위 명령에 그 유형의 옵션만 열고(`TRADE_TYPES_BY_KIND`·`ROOM_LABELS_BY_KIND`·`CONDITIONS_BY_KIND`), `filters_of` 가 그 유형 필터 모델로 바꾼다. 방 크기 필터는 평(정수)만 받아 ㎡ 옵션을 두지 않았다. 주차 대수(`parkingNumRange`)·세입자 낀 매물(`hasTakeTenant`)·360° 사진(`hasPano`)은 뜻을 확인하지 않았거나 사진 기능이라 늘 '전체' 로 보낸다.

## API 변경 시 점검

웹을 다시 배포하면 스크립트 이름이 바뀌고 주소·헤더가 바뀔 수 있다. 헤더·버전 쿼리는 client(`V5_HEADERS`)와 `DabangV3RequestParameterModel`, 유형별 필터 항목은 `request/common.py`, 목록 글자 꼴은 `service/common.py` 의 해석기를 본다. 필터 항목이 늘면 400 본문의 `errorDetails` 가 빠진 항목을 알려 준다.
