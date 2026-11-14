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
| `real-price` | (`--pyeong` 없으면 `complex/{id}`) → `real-price/complex/histories`, `--listing` 은 `real-price/house/init` → `real-price/house/history` | `real_price` |
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
- 모든 요청에 웹 axios 인스턴스(v5·v3 둘 다)가 붙이는 기본 헤더 `Accept: application/json, text/plain, */*`·`csrf: token`·`Cache-Control: no-cache`·`Pragma: no-cache`·`Expires: -1` 을 붙인다 (`base_header`, 2026-11-12 웹 화면 8개 요청 109건 실측과 번들. 요청마다 바뀌는 헤더는 없다). v5 인스턴스만 `V5_HEADERS` 를 더 붙인다. 토큰·쿠키는 없다.
- 없는 주소·경로 값은 404 대신 **403 빈 응답** 이다 (아무 경로나 넣어도 같다). 요청 제한과 섞지 않는다. ID 가 경로에 들어가는 요청(단지 상세·주변 시설·학교)만 `is_missing_id` 로 빈 403 을 `NOT_FOUND` 로 본다. ID 가 쿼리로 가는 요청(분양 상세·교통·단지 실거래·매물 실거래·시군구 코드)은 없는 ID 에 400 이나 빈 결과를 줘서(2026-10-27 실측) 빈 403 이면 다방 주소가 바뀐 것으로 `UPSTREAM_ERROR` 다 (`in_path=False`).

### 브라우저 요청

(2026-11-09 실측) 공통 동작은 [브라우저 요청](../architecture.md#브라우저-요청). 다방만의 값:

- 첫 화면은 `https://www.dabangapp.com/`. 다방이 심는 쿠키는 분석·광고용(`_ga`·`wcs_bt`·`dable_uid` 등)뿐이고 API 는 쿠키 없이
  응답해 기다릴 쿠키가 없다 (`browser_ready_cookie = None`). 첫 화면이 다방 API 를 XHR 로 11번 부른다. JS 파일(`/_next/static`)도
  같은 호스트라 요청 제한에는 XHR·fetch 만 센다.
- 403 이 없는 주소라 `browser_discard_statuses` 를 비운다 (403 에 쿠키를 버리지 않는다). API 가 쿠키를 보지 않아 막힌 403
  이어도 쿠키를 버려서 풀릴 것이 없다. 다방이 방문자 쿠키(WAF 토큰 등)를 요구하기 시작하면 본문이 있는 403 만 버리게 바꾼다.
- 동 경계 CDN(`geojson_host`)은 `Access-Control-Allow-Origin: *` 라 다른 출처 fetch 가 되지만, `csrf` 헤더를 붙이면 브라우저의
  사전 확인(OPTIONS)이 403 이다. 웹도 이 파일은 axios 가 아니라 `fetch(url)` 로 받아 헤더를 하나도 붙이지 않으므로, 동 경계
  요청에서는 기본 헤더를 모두 뺀다 (`_geojson_request`, 2026-11-12 실측).

### 매물 목록 (`search listings`)

- 다방 목록은 유형(`one-two`·`house-villa`·`officetel`·`apt`)마다 따로이고 필터 항목도 다르다. **필터 항목이 하나라도 빠지면 400** 으로 빠진 항목을 한국어로 알려 준다. 그래서 유형마다 요청 모델(`DabangOneTwoFiltersModel` 등)을 두고 주지 않은 항목을 '전체' 값(`{min: 0, max: 999999}`, 모든 목록 값)으로 채운다. `zoom`·`useMap=naver` 도 필수다 (`ZOOM_BY_SEARCH_TYPE`: 동 14, 역·대학 15, 지도 16).
- 필터 범위 값은 하한·상한 모두 999999 까지만 받는다 (넘으면 400 '최대값은 999999 이하로 입력해주세요'). 큰 상한은 `range_of` 가 999999 로 줄이고 큰 하한은 CLI 가 막는다. 압구정·청담·한남동 아파트 매매도 98억까지라 999999 로 빠지는 매물은 보지 못했다.
- 한 쪽은 24건이고 `limit` 을 보내도 무시한다. 다만 다음 쪽이 있어도 더 적게 줄 때가 있다 (2026-11-13 웹 캡처: 아파트 강남역 1쪽·대치동 화면 2쪽 23건. 2026-11-14 실측: 아파트 강남역 반경 3km 6~8쪽 22·22·21건). `total`·`hasMore` 는 일반 목록 기준이라 정확하다. 그래서 이어 받기 위치를 받은 수로 셈하지 않는다. 이어 받기 표(`DabangListPosition`)에 다음에 물을 다방 쪽(`page`)·그 쪽에서 쓴 칸(`skip`)·받은 수(`received`, `[일부] N번째부터` 안내에만 쓴다)·아파트 동 사각형(`bbox`)을 담고, 다음 호출은 그 쪽의 남은 칸부터(다 썼으면 다음 쪽 처음부터) 받는다. 받은 수로 쪽을 셈하면(`수 // 24 + 1` 쪽의 `수 % 24` 번째) 23건짜리 쪽 뒤에 다음 쪽 첫 건을 다시 받아 같은 매물이 또 나온다 (`test_next_resumes_after_short_page_without_repeating_listings`). 단지 매물(`search listings --complex`)·단지 목록·분양 목록도 받은 수가 24건보다 적다고 끝내지 않고 `hasMore` 로만 다음 쪽을 본다. 네 목록은 쪽 따라가기를 `fetch_pages`(`service/common.py`) 하나로 해 이 규칙이 한 곳에 있다. 빈 쪽이면 `hasMore` 가 와도 더 묻지 않고 더 없다(`has_more` false)로 본다 (빈 쪽을 10쪽까지 묻고 '다방에 더 있음' 이라 잘못 알리지 않게, 2026-11-14 리뷰). 쪽 수도 `--limit` 을 24건으로 나눠 정하지 않고 `--limit` 이 찰 때까지 받는다 (네 목록이 같이 쓰는 상한 `MAX_FETCH_PAGES` 10쪽). 10쪽까지 받고도 못 채웠는데 더 있으면 `page_cap_note` 가 `[일부]` 로 알린다 (`limit_notes` 는 받은 수가 `--limit` 보다 적으면 다 받은 것으로 보고 안내하지 않는다). 쪽이 평균 12건 아래여야 닿는 상한이라 실측에서는 닿지 않았고, 상한을 낮춰 그 안내를 확인했다 (2026-11-14).
- 가격·층·면적·관리비는 숫자 없이 글자(`priceTitle` '1억2000/50', `roomDesc` '5층, 19.83m², 관리비 7만')로만 온다. `manwon_from_text`·`listing_prices`·`parse_room_desc` 가 읽고, 읽지 못한 매물은 빼고 `notes` 로 알린다 (`tests/test_dabang.py`). 단지 목록·요약은 억 뒤에 띄어쓰기·쉼표를 넣는다('31억 3,000'). 다방은 반지하를 '반지층' 으로 쓴다.
- `roomDesc` 의 면적은 원룸·빌라·오피스텔이면 상세 전용면적(`room_size`)이지만 **아파트면 공급면적**(`provision_size`)이다. 아파트 목록·단지 매물·인기 매물과 원룸·투룸 목록에 섞인 아파트 모두 같고, 목록 칸에 전용면적은 없다. 그래서 아파트는 `area_m2` 를 `null` 로 두고 `supply_area_m2` 에 넣는다 (`room_item_to_listing`). 아파트 목록의 평 조건(`pyeongRange`)도 공급 평으로 걸린다 (34평 → 공급 112~113㎡).
- 다방 단지 목록(`complex-list`)은 쪽마다 순서가 흔들려 앞 쪽 끝 단지를 다음 쪽 첫머리에 다시 준다 (정렬 옵션 없음, 잠실동 3쪽 71줄 중 69곳). 단지 ID 로 한 번만 넣고 `[제외]` 로 알린다. 매물 목록도 쪽끼리 같은 매물을 겹쳐 준다 (2026-11-13: 아파트 강남역 1~5쪽 120줄 중 108곳만 서로 달랐고, `--next` 1·2차 사이에 3건이 겹쳤다). 한 호출 안에서는 매물 ID 로 한 번만 넣고 `[제외]` 로 알린다. 호출과 호출 사이(`--next`)의 겹침은 웹도 쪽을 넘기면 그대로 보여 주는 서버 동작이라 그대로 둔다.
- 원룸·투룸 목록은 매매를 받지 않는다 (매매만 보내면 무시하고 월세를 준다). 그래서 `room` 의 `--trade` 에서 매매를 뺐다.
- 단기임대는 별도 거래가 아니라 월세 매물의 표시(`roomTypeName` 의 ' • 단기', 상세 `short_lease_str`)다. `trade_type` 을 단기임대로 바꾸지 않고 `short_lease` 로 알린다. 보증금 1000·월세 90 같은 보통 월세에도 붙어, 단기임대로 바꾸면 `--trade 월세` 검색에서 월세 대부분이 빠진다.
- 원룸·투룸 목록에 오피스텔·아파트가, 아파트 목록에 주상복합·도시형이 섞여 온다. [공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)대로 다시 거르지 않는다. 주택·빌라 목록은 매물을 방 개수(원룸·투룸)로 표시해 `property_type` 을 '빌라' 로 둔다.
- 광고(`premiumList`, 광고 중개사별 매물)는 일반 목록과 따로 오고 `total` 에 들지 않는다. 넣지 않고 뺀 수만 `notes` 로 알린다.
- 사용승인 조건(`useApprovalDateRange`, `--built-within`)은 날짜가 아니라 연도로 센다. 2026-10-31 실측: `{max: 2}` 에 2024-02-21 승인(신림동·화곡동 16건 중 가장 오래된 것), `{max: 10}` 에 2016-02-03 승인 건물이 들어오고 그 앞 해 승인은 없었다. 서버 필터라 다시 거르지 않고(목록에 사용승인일도 없다) `search_listings` 가 기준 날짜(`올해 - N` 년 1월 1일)를 `[참고]` 로 알린다. 날짜로 따지려면 `--details`(`attach_details`)가 앞 30건에 상세(`get_listing`, 1회씩)의 사용승인일·건물 용도를 붙인다. 상세에서 내려간 매물은 뺀다.
- 목록 좌표(`randomLocation`)는 다방이 몇 m 흔든 값이다. 거리(`distance_km`)와 반경 판정에만 쓰고 출력하지 않는다.

### 위치 해석 (`region`)

- `loc/search` 는 시·군·구를 주지 않는다 (`강남구` 를 찾으면 강남구의 동들). 구·시 이름은 `REGION_NOT_SUPPORTED` 로 막는다. 행정동은 결과가 없어 `legal_dong_hint` 를 붙인다.
- 고르는 순서는 이름이 똑같은 동 → 역('역' 으로 끝나면 역 먼저) → 대학 → `○동N가` 동이다. 같은 이름의 동이 여럿이면 `REGION_AMBIGUOUS`, '강남구 신사동' 처럼 앞 낱말이 있으면 동의 전체 이름에 그 낱말이 든 후보만 본다. 시·도 줄임말('서울 신사동')은 `SIDO_OFFICIAL_NAMES` 의 정식 이름으로도 맞춘다 (전체 이름은 '서울특별시 …'). 대학은 이름이 똑같은 곳을 먼저 보고, 없으면 앞부분이 맞는 곳을 본다. 앞부분이 맞는 곳이 둘 이상이면('연세대' 는 세 캠퍼스) 고르지 않고 `REGION_AMBIGUOUS` 로 대학 이름을 후보로 준다 (후보 이름을 그대로 주면 이름이 똑같은 대학으로 찾는다). 장소 검색은 괄호가 든 검색어에 0건이라 괄호를 띄어 보낸다. 이름이 똑같은 역이 여럿 와도 `REGION_AMBIGUOUS` 이고 후보 글에 노선을 붙인다. 다방은 같은 이름의 역을 '양평역'·'양평역(중앙선)' 처럼 이름으로 갈라 주어(2026-11-13 실측) 드물고, 이름으로는 다시 가를 수 없어 `hint` 가 `search locations` 의 좌표로 찾게 한다. 한 종류만 받는 명령은 `resolve_places(only=)` 로 그 종류를 알린다 (`neighborhood`·`popular-listings` 는 `'dong'`, `station-prices` 는 `'station'`). 받지 않는 종류의 후보가 여럿이면 고르라고 알리지 않고 첫 후보를 돌려줘, 부른 쪽이 '동 이름으로만 찾습니다'·'역 이름이 아닙니다'(`INVALID_ARGUMENT`)로 막는다. 이때 첫 후보의 이름은 사용자가 준 이름으로 바꿔, 에러 문구에 고르지도 않은 후보('성수동1가')가 아니라 준 이름('성수동')이 찍힌다. 후보를 골라 다시 줘도 그 명령이 받지 못하기 때문이다 (2026-11-13 리뷰: `neighborhood 연세대` 가 대학을 고르라고 한 뒤 다시 막았다). 좌표를 받지 않는 `station-prices` 는 이름이 똑같은 역을 가려 받지 못한다고 `hint` 로 알린다.
- 위치 찾기(`resolve_places`)는 위치 하나만 돌려주고 매물·단지·분양 검색, 동네정보, 인기 매물, 역 평균 매물가가 모두 이것을 쓴다. `○동N가` 로만 나뉜 동(성수동)은 `○가` 동이 둘 이상이면 합쳐 찾지 않고 `REGION_AMBIGUOUS` 로 전체 주소 후보를 모두 준다 (같은 동의 `○가` 는 몇 곳뿐이라 자르지 않는다). 다방 웹 검색창도 성수동1가·성수동2가를 따로 보여 주고 고른 동 하나의 목록만 연다 (2026-11-13 웹 대조). 시·도가 다른 `○가` 동이면 시·도를 후보로 준다. 이어 받기 표에는 첫 결과가 찾은 위치(동 코드·역 번호 포함)도 남겨 `--next` 때 장소 검색을 다시 묻지 않는다.
- 아파트 매물 목록·아파트 단지 목록은 동·대학 검색이 없다 (403). 오피스텔 단지 목록은 동(`region`)·대학(`univ`) 검색이 된다 (2026-10-26 실측: 역삼동 97곳, 홍익대학교). 동은 다방 지도 집계가 주는 동 경계 파일(`d2pi55cyzoqmrc.cloudfront.net/geojson/region/{8자리 코드}`)로 사각형을 만들어 `bbox` 로 받고, 목록의 동 번호(`gid`)가 그 동인 것만 남긴다. 대학은 1km 반경이다. 경계 파일도 같은 요청 제한 훅을 거친다. 아파트 매물 검색은 사각형을 이어 받기 표(`next`)에 남겨 `--next` 마다 경계를 다시 받지 않는다.
- 역은 다방이 정한 역 반경(강남역 750m, `loc/search` 의 `radius`)이고, `--radius` 를 주면 그 반경을 덮는 사각형으로 받아 반경 밖을 뺀다. 단지 목록은 반경을 덮는 사각형을 그대로 받고 반경 밖을 빼지 않는다 (CLI 도움말도 그렇게 적는다, `ComplexRadiusOption`).
- 목록 주소는 찾은 동(`gid`)의 매물만 시·구까지 붙인다. 목록 칸에는 동 이름만 있어 다른 동의 시·구는 모른다. 그래서 동 이름에 `--radius` 를 주면 두 꼴이 섞인다.
- 동 코드는 법정동코드 앞 8자리다. 출력은 뒤에 `00` 을 붙여 10자리로 맞춘다. 다방은 이미 '전남광주통합특별시'(시·도 코드 12)를 쓴다.

### 상세·단지·학교·실거래

- 상세 유형(`room_type_str`)은 목록과 달리 구조를 붙여 온다 ('오피스텔(분리형)'·'원룸(분리형,복층)'). 단지 ID·이름은 다방이 주면 유형과 상관없이 두고, 없을 때만 앞부분이 오피스텔·아파트인지로 해당 없음(키 삭제)과 모름(`null`)을 가른다 (`is_complex_type`).
- 상세 `price_info` 는 `[보증금 또는 매매가, 월세, 거래 유형 코드]` 숫자(만원)다 (0 월세, 1 전세, 2 매매). 화면처럼 `status` 0·3·4 는 비공개로 보고, `is_contract` 도 거래 불가로 본다. 없는 매물은 400 "존재하지 않는 매물입니다."(매물번호는 "존재하지 않는 방입니다.")다. 다른 소스 ID 를 넣어도 이 응답이라 사유를 `ListingUnavailableError` 에 넘기지 않는다 (넘기면 다른 소스 ID 힌트가 빠진다).
- 관리비 포함 항목(`_manage_cost`)은 웹 관리비 칸과 상세보기(safety-option-chunk `E`, room-chunk, 2026-11-13)를 따른다. 입력 방식(`maintenance_input_type`)이 `DETAIL` 이 아니면 웹처럼 포함 항목 글(`maintenance_items_str`)만 본다. `DETAIL` 이면 부과 방식(`maintenance_charge_type`: `FIXED_FEE_CHARGE` 정액관리비·`ETC_FEE_CHARGE` 기타부과·`UNABLE_CHECK` 확인불가)으로 가른다. 정액관리비이고 세부 종류(`maintenance_charge_detail_type`)가 없거나 `ABOVE_FIXED_FEE_THRESHOLD` 이면 `maintenance_fixed_fee_charge_detail_list` 에 항목(F01 공용·F11 전기·F12 수도·F13 가스·F14 난방·F15 인터넷·F16 TV·F99 기타)마다 `FIXED_FEE`·`ACTUAL_EXPENSE`(실비)로 온다. 공용(F01)은 실비로 와도 웹이 금액과 함께 보여 주고 합계에 넣어 포함 항목이고(`E` 의 `h`), 나머지는 `FIXED_FEE` 면 포함, `ACTUAL_EXPENSE` 면 `manage_cost_excludes` 다 (`FIXED_FEE_ITEM_LABELS`). 예: 6ae45e683b53321aea64a773 관리비 20만원은 공용이 실비로 와서 포함 항목이 `['공용 관리비']` 다 (웹 상세보기 '공용 200,000원 · 사용료 실비'). `BELOW_FIXED_FEE_THRESHOLD`·`ABOVE_FIXED_FEE_THRESHOLD_NO_DETAILS` 정액관리비와 기타부과는 `maintenance_etc_fee_charge_detail.detail_include_types` 코드를 웹의 표(`MANAGE_ITEM_LABELS`)로 바꾸고(`E` 의 `g`), 따로 내는 항목은 웹도 보여 주지 않아 `null` 이다. 확인불가는 웹도 항목을 보여 주지 않아 항목이 `null` 이다 (`E` 의 `_`). 부과 방식은 `manage_cost_charge_type` 으로 낸다 (`MANAGE_CHARGE_TYPE_LABELS`).
- 계약면적(`contract_size`)은 오피스텔만 값이 오고 다른 유형은 0 이라 (2026-11-13 실측: 상세 46건 중 오피스텔 5건만 값) 0 이면 키를 뺀다. 유형이 `오피스텔` 로 시작하는 매물은 0 이 와도 해당 없음이 아니라 모름이라 `null` 로 둔다 (2026-11-13 실측: 오피스텔 34건은 모두 값이 있어 0 인 매물은 아직 보지 못했다). 웹은 유형 코드가 오피스텔(`roomType === 3`)이고 상세 응답의 `complex.isUrbanOfficetel` 이 false 인 매물에 '전용/계약면적' 으로, 그 밖에는 '전용/공급면적' 으로 보여 준다 (room-chunk). jibsa 는 유형 글자(`room_type_str`)가 `오피스텔` 로 시작하는지로 가르는데, 유형 코드와 글자는 늘 같이 왔다 (2026-11-13 실측: 상세 29건, 3 은 `오피스텔`·`오피스텔(분리형)`, 4 는 `아파트`·`아파트(복층)`). 이름에 '(도시형)' 이 붙은 단지는 오피스텔이 아니라 아파트 유형으로 와서(다방 단지 검색 50곳 모두 아파트, 5곳 매물 17건 모두 `roomType` 4·계약면적 0·`isUrbanOfficetel` false) 키가 빠지고 웹도 공급면적을 보여 준다. 세입자 낀 매물(`is_take_tenant`)·LH 전세임대(`is_lh_lease`)·임차권 등기명령(`is_leasehold`)·미등기 건물(`is_new_construction`)은 `null` 이면 웹이 없는 것으로 본다 (safety-option-chunk 의 `?? false`). 위반건축물(`is_non_compliant_building`)만 `null` 이면 웹이 그 줄을 감춰 `null`(모름)로 둔다 (room-chunk, true·false 는 '해당'·'해당없음'). 기존 세입자 금액(`take_tenant_price_title`)은 '20억'·'1억/50' 같은 만원 글자라 `_tenant_prices` 가 보증금·월세로 나누고, 읽지 못하면 둘 다 `null` 이다. 세입자 낀 매물은 매매, LH 전세임대는 매매가 아닌 거래에만 키를 두되 다방이 표시를 붙였으면 웹처럼 둔다 (`not_applicable_fields`).
- 옵션의 '벽걸이형'·'스탠드형'·'천장형' 은 웹이 에어컨 목록(`airConditionerTypeList`)의 이름을 그대로 옵션에 섞은 것이라 '에어컨' 을 붙인다. 오피스텔은 공급면적(`provision_size`)을 0 으로 주기도 해서 `null` 로 둔다.
- 단지 상세의 `buildCovRatio`·`floorAreaIndex` 는 이름과 값이 뒤바뀌어 온다 (`buildCovRatio` 가 용적률). 응답 모델이 뜻대로 이름을 붙였다.
- 단지 상세의 학교(`education`)는 초등학교가 배정 학교(통학구역), 중·고등학교가 단지가 든 학교군의 학교 전부(은마 17곳·22곳)를 거리순으로 준다. 학급당 학생 수·진학 인원은 글자('24명', '대학교 163명')라 `count_of` 로 읽는다. 어린이집(`nurserySchool`)·유치원(`kinderSchool`)도 거리순으로 온다 (2026-11-13: 단지 20곳 어린이집 422곳·유치원 71곳 모두). 설립 유형은 어린이집 `type`, 유치원 `establishDivide` 에 오고 교사당 아동 수는 글자('4.1명')다. 전화·좌표는 오지 않는다. 중·고등학교·어린이집·유치원은 웹 '주변 보육/교육시설' 탭처럼 가까운 3곳씩 낸다 (`NEAREST_SCHOOLS`, education 청크 `Y`·`X`·`Q`·`$` = 3. 웹은 '더보기' 로 3곳씩 늘린다).
- 단지 상세의 `recentDealCount` 는 웹 '최근 거래수 N건' 이다 (기간은 다방이 밝히지 않는다). 빈 글자('')로 오면 웹이 '-' 로 써 모름(`null`)으로 받는다. `hashTags`(단지 꼬리표)는 `null` 이면 웹이 칸을 그리지 않아 `[]` 로 받는다.
- 학교 상세(`3/education/{단계}-school/{코드}`)는 단계와 코드가 맞지 않거나 없는 코드면 404 가 아니라 **500** "일시적으로 서비스가 지연되고 있습니다." 다. 코드만으로 단계를 알 수 없어 CLI 가 `--level` 을 받는다 (단계를 차례로 불러 보면 요청이 늘어난다). 다시 보내도 같은 500 이라 이 엔드포인트만 500 을 재시도하지 않는다 (`dabang_education_retry`, [재시도 규약](../provider-conventions.md#요청-메서드)의 예외). 서버 고장도 같은 500·같은 본문이라 가르지 못해, 500 이면 `NOT_FOUND` 로 단정하지 않고 `UPSTREAM_ERROR`(`status` 500)와 입력을 다시 보라는 hint 를 낸다 (매일 감시는 이것을 '확인 못 함'으로 본다). 개교일·개교기념일('1986.21')은 달이 맞지 않아 쓰지 않는다. 학교 코드는 학교알리미 코드('S010000743')라 네이버(`B10…`) 코드와 다르다.
- 단지 요약(`complex/{유형}/summary`)은 경로 가운데에 단지 ID 가 아니라 소문자 유형이 들어간다.
- 실거래 기간은 최대 36달이다 (37달이면 400). 요청 모델이 막는다. 한 번에 50건까지 받는다. 쪽은 `(page - 1) × limit` 번째부터라 쪽마다 `limit` 을 바꾸면 앞 쪽과 겹친다. 쪽 크기를 고정하고 넘치는 건 자른다 (인기 매물도 같다).
- 없는 단지·평형은 실거래·시세 흐름 모두 400 과 사유("존재하지 않는 단지입니다."·"존재하지 않는 평형 정보입니다.")를 준다. 사유를 보고 `NOT_FOUND`·`INVALID_ARGUMENT` 로 바꾼다.
- 단지 상세의 최근 실거래 요약(`complex/{유형}/summary`)은 덤 조회다. 실패하면 `recent_sale`·`recent_lease` 를 `null` 로 두고 `[실패]` 로 알린다. 요청 거절(4xx)·응답 형식 변경이면 `UPDATE_MAYBE_NEEDED` 를 붙이고, 요청 제한·5xx·연결 실패면 붙이지 않는다. 매일 감시는 은마의 `recent_sale` 로 요약이 깨졌는지 보고, 업데이트 문구 없는 `[실패]` 로 비면 확인 못 함으로 둔다. 요약 거래의 면적(`formatRoomSize`)은 아파트면 공급면적, 오피스텔이면 계약면적이고 평형 번호가 없다. 웹처럼 그 면적을 `supply_area_m2`(아파트)·`contract_area_m2`(오피스텔)로 내고, 평형표의 공급·계약면적과 같은 평형이 하나일 때만 `space_seq` 와 전용 `area_m2` 를 붙인다 (은마 115.54㎡ → 34평 전용 84.43㎡). 같은 면적인 평형이 여럿이면 고르지 않고 둘 다 `null` 로 두고 `[참고]` 로 후보 평형을 알린다 (고른 것이 없어 `[모호]` 가 아니다) (2026-11-13 실측: 삼호1차 82.08㎡ → 3526(24A)·286028(24C)).
- 시세 흐름의 달 목록은 매매 쪽(`sale.statistics`)으로 만든다. 매매가 한 건도 없는 평형도 `sale` 이 `null` 이 아니라 거래 0건인 36달로 오고, 전월세와 달이 같다. 거래 없는 달은 앞 달 평균을 잇는데 이을 평균이 없으면 `averagePrice` 가 0 이라 `null` 로 바꾼다. 달마다 전세가율·갭은 웹 갭 그래프가 쓰는 `gap.statistics` 에서 낸다. 웹은 전세가율 0 을 '-' 로 써(`leaseRate||'-'`) `null` 로 바꾸고, 거래가 아직 없는 이번 달은 모두 `null` 로 온다 (2026-11-13 웹 캡처: 은마 202611).
- 매물 실거래(`--listing`)는 `--trade` 를 주지 않으면 웹 매물 화면처럼 `real-price/house/init`(`roomId`·기간·`limit=1`)을 먼저 받고 `real-price/house/history` 를 받는다 (요청 +1). `init` 이 주는 `searchType` 은 매물의 거래 유형을 따른다 (매매 매물 `SALE`, 월세·전세 매물 `LEASE`. 웹 목록도 `sellingType === 2 ? 'SALE' : 'LEASE'`, room 청크 `Rr`). `--trade` 를 주지 않으면 이 값을 쓴다. `--trade` 를 주면 `init` 을 받지 않는다. 거래 유형을 정할 일이 없고, 범위·동·건물 유형은 `house/history` 첫 쪽이 준다 (2026-11-14 실측: 매물 7곳 × 매매·전월세 모두 거래 0건인 기간에도 `dongName`·`historyBaseType`·`buildingViewType` 이 왔고 `init` 과 같았다). 출력은 같고 요청만 1회 줄어든다. 그래서 매일 감시는 `--trade 전월세`(요청 1회)와 `--trade` 없는 기본(요청 2회)을 함께 불러 `init` 도 본다. `historyBaseType` 이 `JIBUN` 이면 이 집(같은 지번) 거래, `DONG` 이면 같은 동의 같은 건물 유형 거래이고, 웹 제목도 '이 집의 ○○ 거래정보는?'·'{동} ○○ 거래정보는?' 이다 (room 청크 `ii`, 2026-11-13 웹 캡처: 망원동·역삼동 다세대 `JIBUN`, 망원동 단독 `DONG`). 범위는 거래 유형마다 다르다 (2026-11-13 실측: 역삼동 월세 다세대 매물 하나가 전월세는 `JIBUN` 2건, 매매는 `DONG` 585건). `init` 의 범위는 매물의 거래 유형 것이라, `--trade` 로 다른 유형을 받을 때도 맞도록 `basis` 와 안내는 받은 `house/history` 응답의 `historyBaseType`·`dongName`·`buildingViewType` 으로 만든다. 그 응답이 범위를 주지 않으면 `init` 으로 매물이 있는지 확인하고, `init` 의 범위는 찾는 거래 유형이 매물의 유형과 같을 때만 쓴다 (아니면 범위를 모른다고 `[참고]`). `basis` 는 `JIBUN` 이면 `'이 집 (망원동 다세대·연립)'`, `DONG` 이면 `'역삼동 단독·다가구'` 이고, 모르는 값이면 짐작하지 않고 `null` 과 `[참고]` 업데이트 안내다. `buildingViewType` 이 `MULTIPLEX`(다세대·연립)면 웹 표가 전용면적·층수(`Kr`)라 `area_m2`·`floor`, 그 밖(`DETACHED` 단독·다가구)은 연면적·주택유형(매매만)이고 층 칸이 없어(`ei`) `total_floor_area_m2`·`house_type` 으로 낸다. 단독·다가구의 면적은 164~1,214㎡ 같은 건물 전체 값이라 매물 전용면적과 견주지 않게 알린다. 거래 줄의 `isRegistration`(등기)·`isNew`(새 거래) 표시는 `registered`·`newly_added` 로 내고, 단독·다가구 줄에는 `isRegistration` 이 없다 (2026-11-13 실측). 없는 매물·단지 매물에는 `init`·`house/history` 가 에러 대신 `searchType`·`dongName`·`historyBaseType` 이 모두 `null` 인 결과를 줘서 `NOT_FOUND` 로 바꾼다 (2026-11-13·11-14 실측. 거래가 0건인 매물도 동·범위는 온다). `init` 의 `compare`(시세 대비 값)는 다방이 표시를 꺼 두어 웹에 나오지 않아 모델에 두지 않는다 ([아직 가리지 못한 것](#아직-가리지-못한-것)).
- 매물·단지 주소 `/room/{id}`·`/complex/{id}` 는 서버가 지도 화면으로 넘겨 준다 (302).

### 동네·주변 (`neighborhood`·`popular-listings`·`nearby`·`station-prices`)

- 동네정보는 탭마다 주소가 둘이다: `summary`(항목 하나의 값과 전국·시도·구 순위, `summaryType` 하나씩)와 `count`(그 탭 항목별 수를 한 번에). 요청을 아끼려고 매물·거래·시세·인구는 `summary`, 학교·편의·교통·안전은 `count` 만 부른다. 수와 순위는 글자('1,074개', '60위')로 와서 숫자로 바꾼다. 출처는 화면 문구대로 매물 수·선호도는 다방, 거래량·평균가는 국토교통부, 인구는 행정안전부다. 시세 탭의 순위(`rankingGroup`)는 웹 표시대로 '아파트/매매 기준' 이다 (오피스텔·전세 평균가는 순위에 들지 않는다).
- 인기 매물은 선호도(조회수·찜수·문의수 종합 점수) 순위다. 순위(`rank`)는 받은 수가 아니라 `(page - 1) × 쪽 크기 + 칸` 으로 센다. 다방이 한 쪽을 덜 채워도 다음 쪽은 그 자리부터라, 받은 수로 세면 그 뒤 순위가 앞으로 당겨진다. 매물 칸에 동 번호·좌표가 없어 주소는 찾은 동으로 채운다. 매물 유형은 주택/빌라·오피스텔·아파트뿐이다. 칸에 건물 유형도 없어 여러 유형을 섞어 받으면 '오피스텔'·'아파트' 표시는 그 이름으로, 방 개수 표시('원룸'·'투룸')는 빌라로 본다 (`POPULAR_KIND_BY_ROOM_TYPE`).
- `{target}/{id}/near` 의 시설 종류 `query` 는 카카오 장소 분류 코드(MT1·CS2·CE7·BK9·PM9·PO3·SW8)와 다방 코드(BS·POLICE·CCTV·NS·KS·ES·MS·HS)다. 대상마다 주는 종류가 다르다: 매물은 CS2·CE7·BK9·PO3, 단지는 MT1·CS2·BK9·PM9. 종류 이름은 웹 주변 지도의 이름표 그대로다 (`NEAR_LABELS`, distance-km-m 청크, 2026-11-13: BS 버스, SW8 지하철역, MT1 마트, CS2 편의점, CE7 카페, BK9 은행, PM9 약국, PO3 관공서, POLICE 치안, NS 어린이집, KS 유치원, ES 초등학교, MS 중학교, HS 고등학교). 편의 종류는 거리순 15곳까지 오고 어린이집·CCTV 는 순서가 섞여 와서(2026-11-13 실측: 역삼동 매물 어린이집 6곳), 종류마다 다방 거리 값으로 세워 가까운 순 3곳(`NEAR_PLACES_PER_TYPE`)을 낸다. 치안은 이름 대신 `gubun`('지구대'), CCTV 는 `usage`('생활방범')가 와서 치안은 `name` 이 `null` 이고 CCTV 는 쓰지 않는다. 시설 좌표·전화는 내보내지 않는다.
- 역 둘레 평균 매물가는 원룸·투룸 지도 집계(`markers`)의 역 표시에만 붙는다 (빌라 집계는 원룸·투룸 평균만, 아파트 집계는 없음). 웹은 '평균 매물가' 라고 부르며 실거래가가 아니다. 역을 덮는 작은 지도 범위(±0.3km, 확대 16)로 부르고 역 번호가 같은 표시를 고른다.

### 분양·순위 (`search sales`·`sale`·`sale-schedule`·`trending-complexes`·`trade-rankings`·`region-ranking`)

- 분양 목록은 지도 범위(`bbox`)만 받고 칸에 좌표·동 번호가 없다. 동·시군구 이름은 경계를 덮는 사각형으로 받아 주소(`address`)가 그 동·시군구로 시작하는 단지만 남긴다. 시군구 경계도 동 경계와 같은 CDN 에 5자리 코드로 있다. `recommendList` 는 범위와 상관없는 추천 칸이라 넣지 않는다. 목록 칸의 `householdNumTitle`('87세대')은 총세대수가 아니라 분양 세대수(상세 `lots_household_num`)라 `sale_household_count` 로 낸다 (2026-11-13: 김포시 37곳 중 2곳에서 상세 총세대수와 달랐다).
- 분양 상세는 옛 방식(`/api/3/`)이고 `provider_name` 이 시공사, `constructor_name` 이 시행사다. 가격 이름표는 웹처럼 공급 유형 코드(`supply_type`)가 4·5(공공임대·민간임대)면 '임대가', 아니면 '분양가' 이고 (ic_24_download 청크 `x`, 2026-11-13. 민간임대 6acca80f… 화면 '임대가 4억7770') `price_kind` 로 알린다. 지역 평균 평당가(`price_info.region_average_pyeong_price`, 최근 6개월)는 만원 글자다. 청약 결과(`subscriptionResult`)는 바깥 키만 camelCase 이고 안쪽 키는 snake_case 이며(2026-11-13 실측), 청약 전이면 `null` 이다. 경쟁률('5.52:1')·당첨가점('43점')·분양/총세대('261/1071')는 글자라 앞 숫자를 읽는다. 상담 전화(`contact`)는 옮기지 않는다. 일정 날짜는 '26.09.07'(날)·'26.08월'(달) 꼴이라 `sale_date` 가 `YYYY-MM-DD`·`YYYY-MM` 으로 바꾼다. 청약 일정은 7일을 넘기면 400 이라 요청 모델이 막는다. 일정 칸에는 글과 좌표뿐이라 `--region` 은 글 앞의 시·도 줄임말('충북')을 정식 이름으로 바꿔 비교한다. 글이 시·도 없이 시('익산')나 단지 이름으로 시작하면 지역을 모르는 것으로 두고 거를 때 빼서 수를 알린다.
- `search sales` 는 이름 모양(전국·시·도·구·군·시로 끝남)이면 먼저 `resolve_scope` 로 범위를 찾고, 범위로 찾지 못하면 동·역으로 다시 찾는다. '홍대입구'·'을지로입구' 같은 역도 '구' 로 끝나기 때문이다. 다시 찾을 때는 범위를 찾느라 받은 장소 검색 결과를 넘겨(`searched`) 같은 요청을 두 번 보내지 않는다.
- 범위 이름은 `resolve_scope` 가 푼다: 시·도는 `region/states`, 시·군·구는 장소 검색 동 코드 앞 5자리로 `region?code=`. 장소 검색은 '중구' 에 서울·부산·대구·대전·울산 중구의 동을 섞어 주므로 시·군·구가 둘 이상이면 `REGION_AMBIGUOUS` 로 시·도를 붙이게 한다 (장소 검색이 동을 50곳까지만 줘 후보에 빠진 시·도가 있을 수 있다). 다방은 구가 있는 시(성남시)를 지역으로 두지 않고, 시 코드(41130)를 물으면 다른 지역(서초동)을 돌려준다. 그래서 받은 코드가 물은 코드와 같은지 보고, 구가 있는 시는 구 이름을 붙이게 한다. 공통 시·도 표(`SIDO_OFFICIAL_NAMES`)에 옛 광주광역시로 있는 '광주시' 는 다른 소스(당근 지역 이름·네이버 `regions`)처럼 경기도 광주시로 본다 (`state_name`, 범위·분양·청약 일정 지역). 동·범위 이름의 앞 낱말('광주시 송정동')도 경기도 광주시로 먼저 맞추고, 맞는 곳이 없을 때만(경기도 광주시에 없는 구를 붙인 '광주시 광산구') 시·도 표대로 넓힌다 (`_in_context`, 네이버 `regions` 와 같은 규칙). 늘 넓히면 '광주시 송정동' 이 경기도 광주시와 광산구 두 곳에 맞았고 (2026-10-28 실측), 넓히지 않으면 '광주시 광산구 송정동' 을 못 찾았다 (2026-10-30 실측). `search sales` 는 `--radius` 를 줘도 시·군·구 이름인지 먼저 보고 그러면 `INVALID_ARGUMENT` 로 막는다.
- 순위 항목마다 받는 값과 값 글자 키가 다르다 (`MetricSpec`): 평균가·평당가·시세증감은 `priceType` 하나, 거래량·매물수는 `priceTypeList`, 전세가율·갭가격은 단지 순위에만 있고 유형만, 세대수·연식은 아무것도 받지 않는다. 단지 유형(`MetricSpec.types`)은 웹 랭킹 스토어를 따른다 (real-estate 청크 `E()`·`T()`·`b()`, 2026-11-13). 거래량·매물수·선호도·전세가율·갭가격('many')은 웹 기본 `buildingTypeList` 가 {OFFICETEL, APT} 이고 둘이면 `complexType` 을 빼고 보내 아파트·오피스텔 합산 순위를 받는다 (`size===2 ? null : 하나`. 강남구 동 거래량 1위가 합산 역삼동 298개, 아파트만 개포동 233개). 평균가·평당가·시세증감·최고가증감('one')은 하나만 고르고 기본 아파트, 세대수·연식('none')은 받지 않는다. 어느 유형의 순위인지 결과 `complex_type` 으로 알린다. 값은 '61.1억'·'27개'·'133.3%'·'44년 6개월'·'+0.8%' 글자라 항목에 맞는 숫자 필드로 바꾼다. 거래·매물이 없는 줄은 '-' 로 와서(세종 동 평균가 33곳 중 8곳) 그 결과의 다른 줄에 있는 칸을 `null` 로 둔다. 둘째 쪽부터는 50곳씩 받아 `--limit` 에 맞춰 자르므로 자른 줄이 있으면 서버 `hasMore` 와 상관없이 `has_more` 다. 시세증감의 `formattedPrice` 는 현재가가 아니라 변화 금액이다 (대우로얄카운티II 19.6억 = 27.7억 → 47.3억, +70.8%).
- 거래 순위는 `limit` 을 작게(2) 보내면 500 을 준다. 웹처럼 50으로 받고 자른다. 조회 순위는 `limit` 과 상관없이 늘 50곳이고, `watchCount` 는 조회 횟수가 아니라 웹이 'N명' 으로 보여 주는 조회한 사람 수다. 둘 다 전국 단위다. 거래 순위는 막 시작한 기간(월요일 아침의 이번주)에 빈 목록이라, 비면 `PREVIOUS_TRADE_PERIOD` 의 지난 기간을 `[참고]` 로 권한다. 매일 감시는 이 때문에 `--period 지난주` 로 본다.
- 최고가증감은 시세증감처럼 `formattedPrice` 가 오른 금액이고, 앞 최고가는 `formattedPrevPrice` 가 아니라 `formattedMaxPrice`·`formattedMaxPriceDate` 로 온다 (강남구 단지 1위 아이파크삼성 15.2억 = 62.8억 × 24.2%). 단지 순위의 `formattedPriceDate` 는 새 최고가 달, 동 순위는 줄 대신 결과에 기준 달('26년 10월')이 와서 `base_month` 로 낸다.
- 동네정보 순위(`region-info/{주제}/ranking/{항목}`, `InfoMetricSpec`)는 동 단위만 있고 한 쪽이 **30곳까지** 다 (31 이면 400 '페이지 당 호출 가능한 최대 행수는 30를 초과할 수 없습니다'). 학원 순위는 `academyType` 이 없거나 'ALL' 이면 빈 목록이라 늘 보낸다 (기본 입시). 진학률은 `schoolType`(중학교 → 고교 유형, 고등학교 → 대학)과 `schoolAdvancementType` 을 늘 보낸다. 학교 수·시설 수의 종류(`schoolEstablishmentType`·`facilityType`)와 인구의 성별·연령은 주지 않으면 전체다. 인구 증감의 변화 수는 부호 없이('327명') 와서, 앞·지금 수가 둘 다 오면 그 차(`count - prev_count`)로 내고 하나라도 없을 때만 `changeStatus`·변화율 부호로 음수를 만든다 (`_fill_count_change`). 학원·진학률 순위는 `parentRegionName` 이 시·도('서울')뿐이라 범위가 시·군·구가 아니면 `[참고]` 로 알린다.

## 원본 금액 단위

| 원본 응답 | 단위·처리 |
| --- | --- |
| 목록 `priceTitle`, 상세 `price_info`, 실거래, 평당가, 시세 흐름 | 만원 |
| 목록 `roomDesc` 의 관리비 ('관리비 7만') | 만원 글자. '관리비 없음' 은 0 |
| 상세 `maintenance_cost` | 원. `won_to_manwon` |
| 상세 `take_tenant_price_title` | 만원 글자 ('20억', '1억/50') |
| 단지 평형 `maintenanceTotalPrice` | 원. `won_to_manwon` |
| 동네정보 평균가 `salePrice`·`leasePrice` | 만원 |
| 역 평균 매물가 `lease`·`monthlyRent` | 만원 글자 ('2억1333', '7937/65') |
| 분양 `priceTitle`·`price_str`·`pyeong_price`·`region_average_pyeong_price` | 만원 글자 ('7억9096', '7억9096 ~ 8억1214', '1789', '1294') |
| 순위 `formattedPrice` | 만원 글자 ('61.1억', '4,762만') |

## 페이지네이션과 조건 처리

모든 매물 조건은 다방 서버가 건다 (서버 필터를 적용한 조회). 받은 뒤 빼는 것은 반경 밖(반경 검색), 다른 동(아파트·단지 동 검색), 가격을 읽지 못한 매물, 한 호출 안에서 다방 목록에 두 번 나온 매물·단지(다음 쪽에 다시 온 것)뿐이고, 뺀 만큼 다시 채우지 않는다. 다방 매물은 거래 조건이 하나라 거래 조건 선택이 없다.

검색 조건 묶음은 `DabangListingConditions`(`common`) 하나다. 유형마다 받는 조건이 달라 CLI 가 유형별 하위 명령에 그 유형의 옵션만 열고(`TRADE_TYPES_BY_KIND`·`ROOM_LABELS_BY_KIND`·`CONDITIONS_BY_KIND`), `filters_of` 가 그 유형 필터 모델로 바꾼다. 방 크기 필터(`pyeongRange`)는 평(정수)만 받아 ㎡ 옵션을 두지 않았다. 기준 면적은 웹 필터 이름표대로 원룸·투룸 '매물유형별 기준면적', 주택·빌라 전용, 오피스텔 계약, 아파트 공급이다 (room-size-type-chunk, 2026-11-13. 오피스텔 강남역 `--area-pyeong-min 17` 결과 23건이 모두 전용 17평 미만). 목록의 `area_m2` 는 전용이라 기준이 다른 유형은 도움말(`AREA_BASIS_BY_KIND`)에 적는다. 주차 대수(`parkingNumRange`)·세입자 낀 매물(`hasTakeTenant`)·360° 사진(`hasPano`)은 뜻을 확인하지 않았거나 사진 기능이라 늘 '전체' 로 보낸다.

## API 변경 시 점검

웹을 다시 배포하면 스크립트 이름이 바뀌고 주소·헤더가 바뀔 수 있다. 헤더·버전 쿼리는 client(`V5_HEADERS`)와 `DabangV3RequestParameterModel`, 유형별 필터 항목은 `request/common.py`, 목록 글자 꼴은 `service/common.py` 의 해석기를 본다. 필터 항목이 늘면 400 본문의 `errorDetails` 가 빠진 항목을 알려 준다. 버전 값(v5 `D-Api-Version`·`D-App-Version`, v3 `api_version`·`version`)은 서버가 옛 값도 받으면 명령이 정상으로 돌아, 매주 월요일 API 감시가 첫 화면 스크립트(2026-11-13 `atoms-chunk`)의 값과 대조해 다르면 고장으로 알린다 (`check_dabang_versions`, [매일 API 감시](../README.md#매일-api-감시)). 감시 내용의 웹 값으로 맞춘다.

## 웹과 다른 점

[웹 화면과의 대응](../provider-conventions.md#웹-화면과의-대응) 원칙 안에서 다방 웹과 다르게 한 곳을 모은다. 2026-11-13 에 다방 명령 전체를 다방 웹(번들 `web.DNlAthXv.js` 판)과 대조했다. 자세한 근거는 각 절에 있고 여기서는 무엇이 다르고 왜 사실이 어긋나지 않는지만 적는다.

### 매물 찾기 (`search locations`·`search listings`·`listing`)

- **아파트 동 검색은 동 경계 사각형에서 그 동만.** 웹 아파트 목록은 bbox·역 검색만 있어 동을 고르면 동 목록 없이 줌 16 지도 화면의 bbox 목록을 보여 준다. jibsa 는 동 경계를 덮는 사각형으로 받아 그 동(`gid`) 매물만 서버 순서 그대로 남기고 뺀 수를 `notes` 로 알린다. 같은 bbox 목록의 부분집합이고 줌은 결과에 영향이 없으며(z16 = z12), `total` 은 사각형 안 수다 ([위치 해석](#위치-해석-region), 2026-11-13 web.js `en`).
- **반경으로 좁히기.** 아파트 대학(1km)·`--lat/--lng`(1km)·`--radius` 는 반경을 덮는 bbox(줌 16)로 받아 반경 밖을 뺀다. 웹은 지도 화면 bbox 를 그대로 보여 준다. 같은 bbox 목록의 부분집합이고 뺀 수를 알린다 (2026-11-13).
- **한 번에 최대 120건.** 웹은 24건씩 번호 쪽이다. 쪽이 24건보다 짧을 수 있어 `--limit` 이 찰 때까지 다음 쪽을 받는다 (상한 10쪽). 같은 쪽을 차례로 받은 것이라 매물·순서는 웹 쪽 넘김과 같다 ([매물 목록](#매물-목록-search-listings), 2026-11-13).
- **광고 칸 빼기.** 웹은 목록 위에 중개사별 `premiumList` 를 보여 준다. jibsa 는 넣지 않고 뺀 수만 `notes` 로 알린다. 광고는 일반 목록과 따로 오고 `total` 에 들지 않아 일반 목록의 매물·순서·수는 그대로다 (2026-11-13 onetwo·house·officetel·apt 청크).
- **한 호출 안의 겹친 매물은 한 번만.** 서버가 쪽끼리 같은 매물을 겹쳐 주고 웹은 그대로 보여 준다 (아파트 강남역 1~5쪽 120줄 중 108곳만 서로 달랐다). jibsa 는 한 호출 안에서 같은 ID 를 한 번만 넣고 `[제외]` 로 알린다. 남은 매물은 모두 웹 목록에 있는 것이고, 호출과 호출 사이(`--next`)의 겹침은 웹처럼 남긴다 ([매물 목록](#매물-목록-search-listings), 2026-11-13).
- **조건 값을 눈금 밖으로.** 웹 UI 는 눈금·선택지만 준다: 보증금·월세·매매가 슬라이더 눈금(slider-options-chunk), 방 크기 0~50평에서 50 은 무제한(room-size-for-api-chunk `[0,50]→{0,999999}`), 사용승인 5·10·15년 이내와 세대수 100 미만·100·500·1000 이상(parking-chunk). jibsa 는 아무 정수나 보내고 서버가 받는다. 웹의 방 크기 50 은 999999 로 바뀌지만 jibsa `--area-pyeong-max 50` 은 서버에서 그대로 50평 이하다 (대치동 화면 206 → 165건). 웹 UI 에 없지만 서버가 받는 값이라 서버가 거른 결과 그대로다 (2026-11-13).
- **`--condition 단기임대` 와 가격 조건의 거래 좁히기.** 단기임대를 주면 월세로 좁힌다. 웹은 월세+전세에 '단기월세만 보기' 를 켜면 전세가 섞여 오고, jibsa 결과는 웹에서 월세만 고르고 단기월세만 보기를 켠 것과 같다 (filter-chunk). 가격 조건만 줄 때 그 금액이 있는 거래로 좁히는 것도 웹에서 그 거래만 고른 것과 같다 (2026-11-13).
- **`search locations` 후보 수.** 종류마다 `--limit`(기본 10, 최대 50) 앞부분만 준다. 웹은 API 가 준 후보(종류마다 최대 50)를 모두 보여 준다. 순서는 같고, 자른 종류가 있으면 `[일부]` 로 몇 곳 중 몇 곳인지 알린다 (2026-11-13 web.js `In`).
- **검색어 괄호를 띄어 보내기.** 웹은 그대로 보내 '연세대학교(원주캠퍼스)' 가 0건이다. jibsa 는 '연세대학교 원주캠퍼스' 로 보내고, 이것은 웹 검색창에 그렇게 넣은 것과 같은 요청이다 ([위치 해석](#위치-해석-region), 2026-11-13 debounce-chunk `ae`).
- **표기 다듬기.** 빌라 `property_type` '빌라'(웹 카드는 '쓰리룸' 등), '오피스텔 • 단기' → 오피스텔 + `short_lease`, 에어컨 옵션 이름에 '에어컨' 붙이기(listing-request 청크), 목록 주소에 시·구 채우기, `distance_km`. 매물·가격·순서·수를 바꾸지 않는 표기다 ([매물 목록](#매물-목록-search-listings)·[상세](#상세단지학교실거래), 2026-11-13).
- **관리비 포함 항목의 순서·이름 (바꾸지 않기로 함).** 기타부과 매물은 웹이 공용→전기→수도→인터넷→난방→가스→TV→기타 순으로 세우고 jibsa 는 응답 순서다. 이름도 웹 정액 표는 '공용'·'기타', jibsa 는 '공용 관리비'·'기타 관리비' 다. 항목 집합과 관리비 금액은 웹과 같아 사실이 어긋나지 않아, 대조에서 지적됐지만 이번에는 고치지 않았다 (2026-11-13 safety-option-chunk `E`).
- **이름 해석 요청.** 웹은 동을 고르면 `/api/v5/region/{gid}` 로 code 를 다시 받고 jibsa 는 `loc/search` 의 code 를 쓴다 (같은 값). 웹은 동·역·대학 목록에도 지도 bbox·zoom 을 붙이지만 결과에 영향이 없다 (대학 zoom 14 와 15 도 같다, 2026-11-13 web.js `en`).

### 단지·실거래·학교 (`search complexes`·`complex`·`search listings --complex`·`real-price`·`price-trend`·`school`)

- **`search complexes` 아파트 동 이름.** 웹 아파트 단지 목록은 bbox·역 검색만 쓰고, 동을 찾으면 지도를 그 동 중심(줌 14)으로 옮긴 화면 범위를 보여 준다 (대치동이면 잠실까지 849곳). jibsa 는 동 경계를 덮는 사각형으로 받고 `gid` 가 그 동인 단지만 남긴 뒤 `notes` 로 알린다. 같은 bbox 목록의 부분집합이다 ([위치 해석](#위치-해석-region), 2026-11-13).
- **`search complexes` 아파트 대학·좌표와 `--radius`.** 반경을 덮는 사각형을 그대로 bbox 로 보낸다 (반경 밖을 빼지 않는다). 웹에서 지도 범위를 그만큼 잡은 결과와 같다 (2026-11-13).
- **다음 쪽에 다시 나온 단지는 한 번만.** 다방 단지 목록은 쪽마다 순서가 흔들려 앞 쪽 끝 단지를 다음 쪽에 다시 준다. 한 호출 안에서 한 번만 넣고 알린다. 남은 단지는 모두 웹 목록에 있는 것이다 ([매물 목록](#매물-목록-search-listings), 2026-11-13).
- **단지 목록을 여러 쪽 한 번에.** 웹은 24곳씩, jibsa 는 최대 120곳이다. 같은 쪽을 차례로 받은 것이다 (2026-11-13).
- **`complex` 의 `area_prices` 는 웹의 '전체 평형 비교' 탭.** 웹 평당가 칸의 기본 탭은 'N평대 비교'(`real-price/complex/price-per-py`)이고 '전체 평형 비교' 탭이 `complex/{id}` 의 `areaAveragePrice` 다. jibsa 는 이 탭 값만 낸다. 웹 한 탭의 값 그대로다 (2026-11-13 complex-chunk).
- **`complex` 의 학교·어린이집·유치원은 3곳씩.** 웹 '주변 보육/교육시설' 탭은 응답 순서(거리순)로 3곳씩 보여 주고 '더보기' 로 늘린다. jibsa 는 '더보기' 앞 화면처럼 중·고·어린이집·유치원을 3곳씩 낸다. `district`(`hakgudoName`)는 웹이 화면에 보여 주지 않는 같은 응답의 값이고, 초등학교를 "배정" 으로 부르는 것은 응답이 통학구역 학교를 주어서 붙인 jibsa 의 해석이다 (웹에 그 문구가 없다) ([상세·단지·학교·실거래](#상세단지학교실거래), 2026-11-13 education 청크 `Y`·`X`·`Q`·`$`).
- **평형의 환산 값.** 웹 평은 `Math.floor(㎡/3.3058)` 정수(은마 '23평'), 관리비는 원 단위('237,845원')다. jibsa 는 `area_pyeong` 23.2 와 `manage_cost_manwon` 23.8 (만원 규약). 같은 값의 정밀도 차이다 (2026-11-13 constants-chunk).
- **`complex` 의 최근 거래에 평형 번호·전용면적 덧붙임.** 웹 요약은 공급·계약㎡만 보여 준다. jibsa 는 그 면적을 그대로 내고, 면적이 같은 평형이 하나일 때만 `space_seq`·전용 `area_m2` 를 덧붙인다. 여럿이면 고르지 않고 `null` 과 후보 평형을 알린다 ([상세·단지·학교·실거래](#상세단지학교실거래), 2026-11-13).
- **`search listings --complex`.** 가격 조건만 주면 그 금액이 있는 거래 유형으로 좁히고 알린다. 광고(`premiumList`)는 빼고 수만 알린다. 웹 `limit` 24 쪽 넘김을 최대 120건까지 한 번에 받는다. 위 매물 목록과 같은 성격이다 (2026-11-13).
- **`real-price` 의 쪽 크기·기간·거래 유형.** 쪽마다 50건씩 최대 200건 받는다 (웹은 5건씩 '더보기'). `--years 2` 는 웹에 없다 (웹은 1년·3년). `--listing` 의 `--years 1·2` 도 웹에 없다 (웹은 36달 고정). `--listing` 에 `--trade` 를 주어 매물과 다른 거래 유형(매매 매물의 전월세 등)을 보는 것도 웹에 없다 (웹은 탭 없이 매물의 거래 유형만 보여 준다). 모두 서버가 받는 같은 파라미터라 거래 한 건 한 건은 웹 자료 그대로다 (2026-11-13 room 청크 `Rr`).
- **`price-trend` 를 한 번에.** 웹이 토글로 나눠 보여 주는 1년·3년 최고·최저와 매매·전월세·갭 값을 한 번에 낸다. 평균 0 은 `null` 로 바꾼다. 같은 `charts` 응답의 값이다 ([상세·단지·학교·실거래](#상세단지학교실거래), 2026-11-13).
- **`school` 의 진학 갈래.** 웹은 인원이 0 인 갈래(특성화고·취업자)를 숨기고 과학고·외국어고·예술체육고·자사고 비율은 그리지 않는다. jibsa 는 같은 응답에서 모두 낸다. 갈래 이름도 줄였다 (특수목적고→특목고, 자율형고→자율고, 국외진학→국외, 취업자→취업). 웹이 숨긴 값을 더 보여 준 것이라 값은 같다 (2026-11-13 school-chunk).

### 동네·주변·분양·순위

- **`popular-listings` 한 쪽 크기.** 웹은 `limit 30`·쪽 번호이고 순위 배지는 쪽마다 앞 3개에만 붙인다. jibsa 는 50건씩 받고 쪽·칸 위치로 이어지는 `rank` 를 붙인다. 역삼동 빌라 60건이 웹 30+30 과 집합이 같았다. 붙은 두세 쌍의 순서가 뒤바뀌는 것은 웹과 똑같은 요청을 두 번 보내도 생기는 서버 쪽 흔들림이다 ([동네·주변](#동네주변-neighborhoodpopular-listingsnearbystation-prices), 2026-11-13 hot-room-list-chunk).
- **`neighborhood` 는 탭 여덟 개를 한 번에.** 웹은 학교·편의·교통·안전 탭마다 `regional/summary`(종류별 합계와 순위)와 `regional/count` 를 둘 다 부르고, jibsa 는 `count` 만 불러 이 네 주제에는 순위가 없다. 웹에 있는 값을 덜 낸 것이고 수는 같다 (2026-11-13 school·facility·traffic·life-safety 청크).
- **`nearby` 는 종류마다 가까운 3곳 (사용자 결정).** 웹은 `/{room|complex}/{id}/near` 의 시설 전부(편의 종류는 15곳)를 지도에 찍는다. jibsa 는 종류마다 다방 거리 값으로 가까운 순 3곳만 낸다. 같은 서버 거리 값으로 가까운 곳만 고른 것이라 시설·거리는 웹 지도에 있는 그대로다 ([동네·주변](#동네주변-neighborhoodpopular-listingsnearbystation-prices), 2026-11-13 distance-km-m 청크).
- **`station-prices` 의 범위·확대.** jibsa 는 역을 덮는 ±0.3km·확대 16, 웹은 역을 검색한 화면 범위·확대 15 다. 역 번호가 같은 표시의 평균을 고르므로 강남역 다섯 칸의 값이 모두 같았다 (2026-11-13 map-chunk `markers/category`).
- **`search sales` 동·시군구.** 웹 지역 목록은 `api/3/sale-in-lots/list/search3`(`state_code`·`city_code`)로 찾고, jibsa 는 지도 목록(`sale-list/category/bbox`)에 경계 사각형과 주소 거르기를 쓴다. 김포시 37/37곳이 순서까지 같았고 강남구·역삼동도 같았다. 다만 `total` 은 사각형 안 수라 김포시는 74 다 (웹은 37) (2026-11-13 list-chunk).
- **`search sales` 역·대학·좌표의 기본 범위 (사용자 결정).** jibsa 는 1km 반경을 덮는 사각형(2×2km)·확대 14, 웹은 역을 고른 화면 범위(1440×900 기준 약 3.6×2.9km, 확대 15)다. 강남역은 웹 3곳, jibsa 1곳이고 jibsa 결과는 웹에서 확대하면 보이는 부분집합이다 (확대 값은 결과에 영향이 없다). 웹 범위는 화면 크기에 따라 달라 기준으로 삼지 않았다 (2026-11-13 사용자 결정).
- **`sale-schedule` 기간.** jibsa 기본은 오늘부터 7일, 웹은 그 날짜가 든 주(일~토)를 `list/schedule` 로 부르고 하루 목록은 `list/schedule/search` 로 받는다. 하루 24건이 웹과 집합·순서 모두 같았다. `--region` 은 웹에 없는 조건으로 좁히기이고 거른 수를 알린다 (2026-11-13 schedule-chunk).
- **`region-ranking` 쪽 크기와 인구증감.** 부동산 순위는 jibsa 50곳씩, 웹 30곳씩이다 (동네정보 순위는 둘 다 30). `인구증감` 은 성별 없이 부른다. 웹에는 남성·여성 인구증감만 있고, 성별 없는 응답은 남+여 합계다 (역삼동 68,936 = 32,746 + 36,190). 서버가 받는 조합이다. 단지 유형의 기본은 웹과 같고(거래량·매물수·선호도·전세가율·갭가격은 합산), `-t` 로 하나만 고르는 것은 웹에서 한쪽을 끈 것과 같다 ([분양·순위](#분양순위-search-salessalesale-scheduletrending-complexestrade-rankingsregion-ranking), 2026-11-13 real-estate 청크).
- **`trending-complexes`·`trade-rankings` 기본 개수.** jibsa 기본 20곳은 웹이 받는 50곳 목록의 앞부분이다 (2026-11-13 complex-chunk·map-chunk).
- **`region-ranking`·`search sales` 의 시·군·구 찾기 경로.** jibsa 는 `loc/search` → 동 코드 앞 5자리 → `region?code=`, 웹은 `region/states` → `region/cities?stateCode=` 로 고른다. 강남구는 둘 다 gid 5547 이고 순위 결과도 같았다 (2026-11-13 useSiGuDong-chunk).

### 아직 가리지 못한 것

사례를 찾지 못해 웹과 같은지 가리지 못했다. 다음 대조 때 본다.

- `listing`: `is_contract` 가 true 인 매물 (jibsa 는 `LISTING_UNAVAILABLE`, 웹은 이 값을 화면에서 쓰지 않는다), 건물 전체 매물(`is_building_unit_all`)의 면적·층 표시 (웹은 연/대지면적·지상/지하층). `complex.isUrbanOfficetel` 이 true 인 오피스텔 매물 (웹은 계약면적 대신 공급면적을 보여 준다. jibsa 는 이 값을 보지 않아 계약면적이 오면 그대로 내고 0 이면 `null` 로 둔다. 2026-11-13 오피스텔 12건·도시형 단지 매물 17건은 모두 false 라 true 인 매물을 보지 못했다).
- `search listings`: 원룸·투룸 목록에 섞여 오는 오피스텔·아파트에 걸리는 방 크기 기준, 서버 순서가 시간이 지나며 바뀌는 주기.
- `complex`: `buildingApprovalTypeName` 이 '사용승인일' 이 아닌 단지의 `approved_at`, `complexType` 이 APT·OFFICETEL 밖인 단지의 유형 가르기.
- `search complexes`: 오피스텔 대학(`univ`) 목록은 번들만 대조했다.
- `real-price --listing`: `JIBUN` 이 다세대·연립에서만 나오는지. `real-price/house/init` 의 `compare`(시세 대비 오름·내림과 %)는 다방이 표시를 꺼 두어(`settings.isPriceCompareExpose: false`, 값도 null) 웹에 나오지 않아 넣지 않았다. 다방이 켜면 웹 '시세대비' 칸이 무엇과 견준 값인지 보고 넣는다.
- `region-ranking`: 달이 바뀐 직후 `baseMonth` 를 보내지 않아도 웹과 같은지.
- `trade-rankings`: `sameAddressComplexCount` 가 1 보다 큰 단지 (웹은 '+N' 표시).
- `search sales`: 사각형 안 분양이 120곳을 넘는 시군구, 동 범위에 분양이 여러 곳일 때의 순서.
