# 당근 개발 가이드

[CLI 사용법](../../docs/daangn.md) · [개발 환경·검증](../development.md) · [공통 아키텍처](../architecture.md) · [provider 작성 규약](../provider-conventions.md) · [출력 계약](../output-contract.md) · [코드 형식](../code-style.md)

공통 규약에 없는, 당근에만 있는 구현과 예외를 적는다.

## 명령과 요청 흐름

| CLI 명령 | 주요 경로 | service 모듈 |
| --- | --- | --- |
| `search locations` | 지역 JSON 검색 + GraphQL searchComplexes | `region` (단지 후보는 `complex`) |
| `search listings` | 동: articleFeed / 역: searchSubwayStationPois → subwayStationArticleConnection / 반경: articleMapPoints → articlesByOriginalArticleIds | `search` |
| `listing` | articles SSR → Relay·JSON-LD → 거래 조건 선택 | `listing` |
| `search complexes` | 지역 해석 → region_complexes (searchComplexes) | `complex` |
| `complex` | complexes SSR → 평형·학교·단지 정규화 | `complex` |
| `search listings --complex` | complex_articles (complexByOriginalId.complex.articles) | `complex` |
| `real-price` | complexByOriginalId / articleByOriginalArticleId → _collect_transactions → _collect_pages | `real_price` |
| `region-real-price` | realsaleFeed / realsaleNewHighFeed → _collect_pages | `real_price` |
| `price-trend` | complex_price_chart → 월별 평균·비교 구간 | `real_price` |
| `school` | searchSchools → schoolByCode → 로컬 필터·세대수 정렬 | `school` |
| `search commute` | nearestCommuteStation → commuteFeed → commuteStationArticleConnection → 카드 조회 | `commute` |
| `region-reviews` | regionByOriginalRegionId·livedReviewsByRegion·map_reviews SSR | `review` |
| `developments` / `development` | developmentDistricts / developmentByBusiNo | `development` |
| `preschools` / `preschool` | educationMapPoints / preschoolByNo | `school` |
| `compare` | complexByOriginalId 비교 칸 (complex_compare) × 단지 수 | `compare` |
| `nearby-complexes` | complex_compare → regions/keyword → complexes(region3Id) → complexesByOriginalComplexIds | `compare` |
| `good-neighborhoods` | livableRegionScopes → recommendNeighborhoods | `neighborhood` |
| `trending-complexes` / `popular-listings` | trendingComplexes / getViewRankingArticles | `complex` / `popular` |

## 소스 고유 구현

### 응답 형식과 요청 규칙

- 동 정보·상세는 SSR HTML 에 seroval JS 식으로 심긴 라우터 상태(`$_TSR.router=($R=>$R[0]={...})`)의 `dehydratedData.relayRecords`(Relay 정규화 스토어)를 `relay.py` 가 꺼내 `__ref`/`__refs` 를 펼치고, `parser.py` 가 응답 모델로 만든다. 상세의 일부 값은 JSON-LD 에서 읽는다. 스토어가 없으면 `RelayStoreNotFoundError` (CLI 에서 `PARSE_ERROR`).
- 조건을 건 매물 목록과 다음 페이지는 웹이 쓰는 GraphQL `articleFeed` (persisted query 만 받음)로 받는다. 실패도 HTTP 200 의 `errors` 로 와서 service 의 `unwrap_feed()` 가 판정한다. 해시가 거절되면 지도 페이지 20건에 조건을 직접 거는 방식으로 돌아간다.
- 지역 해석만 `www.daangn.com` 의 JSON API 를 쓴다.
- 입력 타입이 틀리면 "알 수 없는 오류" 가 와서 preschoolByNo·getViewRankingArticles 는 숫자, trendingComplexes 의 regionId 는 문자열로 보낸다 (2026-10-10 실측).

### 매물 목록 경로

- 지도 피드(동 단위)는 동 ID 로 걸러도 주변 동 매물을 섞어 준다. 빼지 않고 `neighbor_notes` 로 알리며, 시·도(`name1`)가 빠진 주변 동 매물은 지역 검색으로 채운다 (`with_sido`, 동마다 1회).
- 좌표 반경 검색(`search_area`)은 웹 지도처럼 `articleMapPoints` 로 좌표 범위의 핀(ID·좌표)을 받아 가까운 순으로 정렬하고, `articlesByOriginalArticleIds` 로 20개씩 카드를 받는다. `jibsa daangn search listings` 에 역·장소 이름을 주면(또는 이름 + `--radius`) CLI 가 당근 역·주소 검색으로, 못 찾으면 직방 지역 검색으로 좌표를 찾아 (`_geocode`, 아래 '위치 찾기') `search_area` 를 부른다. 좌표 → 동은 `getRegionByCoordinate`. GraphQL 좌표는 문자열로 보내야 한다. 카드에는 시·도가 없어 검색 중심과 같은 구의 동은 중심의 시·도로, 나머지는 `with_sido` 로 채운다.
- 역 이름의 `search listings` 는 역 주변 목록(`subwayStationArticleConnection`, 페이지 넘김 쿼리)을 쓰며 카드에 상태·거래 조건·역별 도보 시간이 다 있어 카드를 다시 받지 않는다.
- `search listings --city` 는 역 좌표의 동(`getRegionByCoordinate`, 역마다 1회)으로 그 시·도·구의 역을 고른다 (`_station_in_city`).
- 출퇴근 검색(`search_commute`)은 `nearestCommuteStation` → `commuteFeed` → 역마다 `commuteStationArticleConnection` 으로 매물을 모은다. 역별 매물은 `articlesByOriginalArticleIds` 카드와 필드·값이 같아 (2026-10-11 실측: 역삼역·합정역 20건씩 모양·값 모두 같음) 역 주변 목록처럼 카드를 다시 받지 않는다. 역별 매물은 페이지 넘김 쿼리(`CommuteStationDetailPaginationQuery`)라 `after` 로 100건씩 이어 받는다 (첫 페이지는 기존 `CommuteStationDetailQuery` 와 결과가 같다, 2026-10-10 실측).

### 위치 찾기 (`find_place`·`_geocode`)

- 역·장소 이름 → 좌표(`find_place`)는 당근 역 검색(`searchSubwayStationPois`, 이름이 같은 역만)과 주소 검색 (`find_address`: `searchAddress` → `geocodeAddress`) 순서다. `search listings` 처럼 역 검색을 먼저 한 곳은 `_geocode(..., check_station=False)` 로 주소 검색만 해 같은 역 검색을 되풀이하지 않고, 역 주변 목록만 실패했으면 이미 찾은 역 좌표를 반경 중심으로 쓴다.
- 주소 검색은 비슷한 이름을 먼저 주기도 해서 (연세대학교 → 아산 '연세대학교 연세유업', 63빌딩 → 'PA63빌딩', 테헤란로 15 → 테헤란로2길 15) 검색어 끝이 도로명(`…로/길 번호`)·지번(`…동/가/리/읍/면 번지`)이면 번호까지 같고 앞에 붙인 시·구도 들어 있는 결과만, 아니면 지번 주소 끝 건물 이름이 같은 결과만 쓴다 (`_address_matches`). 숫자가 든 건물 이름(래미안3차)은 주소로 보지 않는다. 맞는 결과가 여러 시·군·구에 있으면 (중앙로 1 은 10곳 넘음) `RegionAmbiguousError` 를 내고 `_geocode` 도 직방으로 넘기지 않는다. 직방은 주소·건물 이름을 찾지 못해(2026-10-10 실측: 테헤란로 152·63빌딩 모두 못 찾음) 넘기면 '찾지 못했다' 로 바뀌기 때문이다. 이름이 정확히 같은 다른 건물은 막지 못한다 (63빌딩 → 인천 학익동 '63빌딩'. 여의도 63빌딩은 그 이름으로 검색되지 않는다).
- 나머지는 CLI 의 `_geocode` 가 직방 → 네이버로 넘긴다. 직방이 요청 제한이나 서버 오류·네트워크·응답 형식 오류(`GEOCODE_FALLBACK_ERRORS`)로 실패하면 네이버로 넘기고, 직방이 찾지 못한 이름(`REGION_NOT_FOUND`)은 넘기지 않는다. 네이버도 막혔거나 실패했거나 찾지 못하면 `zigbang.service.geocoding_failed` (`source: zigbang`, 당근 동 이름·`--lat/--lng` 힌트) 에러를 낸다. 직방 요청 제한은 그 `RATE_LIMITED` 를, 그 밖의 실패는 `UPSTREAM_ERROR` 를 낸다. 그대로 올리면 `source: daangn` 으로 보고돼 에이전트가 멀쩡한 당근을 버린다 (2026-10-12 리뷰).
- 역 검색 결과에는 주소가 없고 노선·좌표만 와서 같은 이름의 역(양평: 경의중앙선·서울5호선)은 첫 역을 쓰고 다른 역을 노선과 함께 `notes` 로 알린다 (`same_station_notes`).
- `--city`·주소 검색 앞의 시·구는 주소 단어의 앞부분으로 맞춘다 (`place_in`. '강남' 은 강남구에 맞고 '남구' 는 강남구, '동구' 는 성동구에 맞지 않는다).

### 세종·구가 있는 시·리

- 세종은 시·군·구가 없어 매물·지역 검색 모두 `name2` 가 `''` 로 오므로 빈 구 이름도 채우는 대상이다 (2026-10-11 실측: 빼면 주소가 '반곡동' 만 나갔다).
- 인기 매물 순위는 동이 속한 구 단위인데, 세종은 그 동 안에서만 매긴다 (새롬동 7건·반곡동 1건이 모두 그 동, 자곡동은 강남구 다른 동 28건).
- 리 안내(`region_notes`)도 세종이면 구 대신 시·도를 쓴다.
- 지역 실거래·후기·단지 목록의 지역(`resolve_realsale_region`)은 구가 있는 시('수원시')를 받으면 같은 이름의 구가 없어 예전에는 첫 동(인계동)으로 대신 찾았다. 이제 지역 검색 후보의 `name2`('수원시 팔달구')를 모아 `REGION_AMBIGUOUS` 로 다시 묻는다. 지역 검색은 100건에서 잘려(창원시·서울 2026-10-11 실측) 구가 빠질 수 있어 그때는 힌트에 '등' 을 붙인다 (`REGION_KEYWORD_MAX_RESULTS`).
- 같은 이름의 동(`resolve_regions`)·동·구(`resolve_realsale_region`)가 여러 곳이면 예전에는 첫 곳으로 찾고 `notes` 로 알렸다. 첫 곳이 소스마다 달라(2026-10-15 실측: 신사동은 당근 강남구, 직방 은평구, 네이버는 `REGION_AMBIGUOUS`) 이제 후보와 `--city` 예시를 싣고 `REGION_AMBIGUOUS` 로 멈춘다. 같은 이름 동은 멈추기 전에 앞 다섯 곳의 지도 페이지를 1회씩 보고 404(지도가 없는 행정동)를 뺀다(`_dongs_with_map`). 404 가 아닌 오류(서버 오류·페이지 형식 변경)로 확인하지 못한 후보는 남기고 `partial_failure_note` 로 알린다. 실거래·단지 목록·후기는 지도 페이지를 쓰지 않아 이 확인 때문에 명령이 실패하면 안 돼서다. 요청 제한과 연결 실패·시간 초과는 다음 요청도 같은 이유로 실패하니 바로 올린다. 남기면 원인 대신 `REGION_AMBIGUOUS` 로 끝나고, 응답 없는 서버를 후보마다 재시도하며 기다린다. 같은 이름의 리(`same_ri`)는 읍·면 후보로 짐작한 것이라 그대로 첫 곳 + 안내다.
- 세종(`세종`·`세종시`·`세종특별자치시`)은 시·군·구가 없어(`name2Id` 0) 예전에는 첫 동(조치원읍)으로 대신 찾았다. 세종 동의 `name1Id`(1241)로 부르면 실거래 피드는 세종 전체를 주지만 단지 목록(`searchComplexes`)은 0건이고 구 후기 페이지도 없어 (2026-10-11 실측) 지역 실거래만 세종 전체로 찾고 단지 목록·후기는 동 이름으로 다시 묻는다(`_sejong_realsale_region`).
- 실거래 피드의 주소(`regionName`)는 리 앞 읍·면을 빼고 줘서('경기 양평군 공흥리') 읍·면으로 조회했을 때만 그 읍·면을 넣는다(`_with_town`).

### 단지·실거래

- 단지 정보(`get_complex`)는 단지 페이지(`/complexes/{id}`)의 스토어에서, 단지 이름 검색(`search_complexes`)은 GraphQL `searchComplexes` 로, 단지 매물 목록(`list_complex_listings`)은 `complexByOriginalId.complex.articles` 로, 단지 실거래가(`get_real_prices`)는 GraphQL `complexByOriginalId`, 매물 건물 실거래가(`get_listing_real_prices`)는 `articleByOriginalArticleId` 로 받는다. 둘 다 `_collect_transactions` 가 페이지를 넘긴다. 동·구의 최근 실거래·신고가(`get_region_real_prices`)는 `realsaleFeed`·`realsaleNewHighFeed` 로 받고, 동·구는 지역 검색 결과에서 고른다 (`resolve_realsale_region`). 세 실거래 모두 `_collect_pages` 하나가 페이지를 넘기고(한 페이지 받기와 거래 유형 고르기만 바꿔 끼운다), 전월세의 갱신 여부는 `_renewal` 이 정한다. 지역 실거래는 계약 종류 없이 오기도 해서 그때는 `null` 이다.
- `trendingComplexes` 는 동에 따라 빈 목록이다 (대치동 3곳·역삼동 4곳, 자곡동·세종 새롬동·도담동 0곳, 기준은 모름). 빈 결과는 `notes` 로 알린다.

### 동네 정보 (후기·개발 호재·교육 시설·좋은 동네)

- 동네 후기(`get_region_reviews`)는 동 후기 수(`regionByOriginalRegionId`)·후기 유무(`livedReviewsByRegion`)와 구의 후기 페이지(`/map/{name1}/{name2}/reviews`) 스토어의 후기 많은 단지만 쓰고, 후기 본문·요약 글은 읽지 않는다.
- 개발 호재·교육 시설은 좌표 범위를 받는 지도 쿼리라 반경을 감싸는 사각형으로 받아 반경 밖을 뺀다. 개발 호재는 페이지 없이 모두 오고 웹이 숨기는 진행 코드 E01 은 뺀다. 교육 시설은 500개에서 잘린다.
- 어린이집 전화번호·홈페이지, 개발 사업·인기 단지 사진, 단지 비교·좋은 동네의 후기 요약 글은 읽지 않는다.
- 좋은 동네 추천의 라이프스타일 지표(`LIFESTYLE_INDICATORS`)와 기준 연도는 웹 번들에서 옮겼다. 추천 지역(`livableRegionScopes`)은 통계 기준 연도의 시·도 이름이라 광주광역시(24)·전라남도(36)가 아직 따로다 (2026-10-10 실측). `--region` 의 시·도 줄임말·옛 이름·통합 이름은 시·도 앞부분과 시·군·구 이름('광주시' 는 경기도 광주시)을 먼저 본 뒤 정식 명칭으로 맞추고, 전남광주통합특별시('전남')는 두 곳을 모두 넣는다 (`_scope_sidos`). 구가 있는 시의 구는 추천 지역에 '수원시 장안구' 처럼 두 단어로 와서(2026-10-11 실측: 경기 20곳 등 37곳) 전체 이름·구 이름·시 이름(그 시의 구 모두)으로 맞춘다 (`_region_codes`). 옛 이름('광주'·'전라남도')이 한 곳만 찾는 건 추천 데이터가 둘을 나눠 주기 때문이고 `--city` 와 다른 건 의도다.

## 페이지네이션과 조건 처리

매물 피드는 20건씩 최대 6페이지, 카드 조회는 ID 20개씩, 역 주변 매물과 출퇴근 역별 매물은 100건씩(역당 CLI 최대 120)이다. 원본 수 또는 카드 조회에 보낸 ID 수로 예산을 세고 제외된 결과를 채우지 않는다. 단지 후보·지역 단지는 50개씩 커서로 받고 CLI 기본 120·최대 1200을 적용한다. 실거래는 50건씩 최대 24페이지이며 전세·월세는 섞인 전월세에서 골라낸다. 학교는 API에 limit을 보내지 않고 받은 배정 단지를 필터·정렬한 뒤 자른다. 이 숫자는 CLI 조회 예산이며 서버의 보편적인 한도로 간주하지 않는다.

실거래의 다음 페이지 커서가 없거나 같은 커서가 반복되면 안내하고 중단한다. 반복된 페이지를 거래 수에 다시 더하지 않는다. 통근 역 목록(`commuteFeed`)도 커서가 진행되지 않으면 중단한다. 통근 역 목록은 50곳씩 최대 4쪽(200곳)만 받는다. 매물은 가까운 10곳만 찾아서 그 이상은 역 수만 정확해지기 때문이다. 4쪽을 받고도 시간 상한 안 역이 남으면 `notes`로 알린다. 서버는 지하철 60분 안 역까지만 주어(`COMMUTE_SERVER_MAX_MINUTES`) `--max-minutes`가 60을 넘으면 안내한다 (2026-10-11 실측: 강남역 9쪽 411곳·양평역 42곳 모두 60분에서 목록이 끝났다). 역 주변 매물과 출퇴근 역별 매물은 limit 최대 120·한 페이지 100건이라 요청 2번 안에 끝나 커서 반복 검사를 두지 않는다 (2026-10-10 실측: 역삼역 120건 = 요청 2번, 커서 진행). 지하철 시간이 없는 역은 시간 상한을 확인할 수 없어 제외하며 환승 횟수와 회사까지 도보 시간이 없으면 0으로 만들지 않는다.

CLI는 위치 조회 전에 검색 조건을 검증해 잘못된 조합이 위치 API 요청 제한에 가려지지 않게 한다. 요청 모델도 역전된 금액·면적·세대수 범위와 유한하지 않은 면적·주차 수를 거절한다. 매물 검색 조건 묶음 `DaangnListingConditions`(`common`, 동·반경·역·출퇴근·단지 매물 공통)는 [공통 규칙](../provider-conventions.md#검색-조건-묶음)과 달리 조건 조합(원룸이 아닌데 방 구조, 아파트만이 아닌데 세대수·주차대수)도 모델에서 검사한다. 지역 단지 목록은 `DaangnComplexConditions`(`complex`)다. 로컬 금액 비교에서 모르는 값은 조건이 없을 때만 통과한다. 관리비 포함 월세의 하한은 서버에 맡기되, 복수 거래 조건을 고를 때 월세 자체가 총액 상한을 넘는 조건은 제외한다.

매물 유형은 건축물 용도와 방 구조가 섞인 당근 카테고리다. `ONE_ROOM`은 `OPEN_ONE_ROOM`·`SPLIT_ONE_ROOM`을 찾으며 아파트·오피스텔의 방 1개를 포함하는 보편적인 방 수 조건이 아니다. 웹의 방 수 조건도 `TWO`·`THREE`·`FOUR_OR_MORE`뿐이다. 이를 CLI의 원룸 검색 안내와 사용자 문서에 명시한다. 매물 종류는 작성자가 고른 하나라 같은 건물도 갈린다 (2026-10-10 실측: 오피스텔 단지 '엘리젠트' 매물 3건 중 방 1개 1건은 원룸, 2건은 오피스텔로 올라 `-t 원룸`에 1건만 나왔다). 목록 카드에는 방 수(`roomCnt`)가 없고 상세 SSR에만 있으며(목록 5경로·`articleByOriginalArticleId` 원본 확인), 단지 종류(`complex.type`)는 모든 목록 카드에 온다. 그래서 종류를 다시 거르지 않고 안내만 한다. 원룸·오피스텔·투룸 검색의 한계와 `-t 원룸,오피스텔` 은 찾을 때마다 같은 안내라 `notes` 대신 `docs/llm.md` 에 두고, `property_type_notes`는 원룸 외 유형과 `--structure`를 함께 주면 거의 원룸만 오는 점(같은 날 실측: 동 20건 모두 원룸, 역 20건·통근 50건 중 단지 없는 오피스텔 1건씩만 섞임)을 알리고, `complex_building_notes`는 원룸·투룸으로 올렸지만 오피스텔·아파트 단지에 있는 매물을 ID·단지 이름으로 알린다 (추가 요청 없음). `-t 투룸`(TWO_ROOM 카테고리)은 **투룸 이상**(쓰리룸·포룸이상 포함)이고 목록에 방 수가 없어 좁힐 수 없다. 이 점도 `docs/llm.md` 에 있고, 목록의 `room_type` 은 `null`(모름)이다. 상세의 `room_type` 은 유형과 상관없이 방 수를 먼저 보고(2개 이상이면 투룸·쓰리룸·포룸이상), 방 1개거나 방 수를 모르면 원룸 구조만 쓴다 (`room_type_of`, 2026-10-10 실측: 분리형원룸으로 올린 방 2개 매물). 네이버 `_room_type` 과 같은 기준이다. 상세의 `complex_type` 은 SSR 단지(`PropComplex.type`)를 `COMPLEX_TYPE_LABELS` 로 바꾼 것이다. 당근은 도시형생활주택 단지를 `APARTMENT`·`MIXED_USE` 로 준다 (2026-10-10 실측: 블루밍하우스(도시형)·경원하이츠텔(도시형) 등). 이름의 "(도시형)"으로 종류를 바꾸지 않는다. 카테고리·이름으로 추측하지 않는다는 [공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)을 따른다. ㎡ 면적은 일반 매물 전용, 주택·건물·공장 연면적, 토지 대지면적이므로 모든 유형을 전용면적이라고 설명하지 않는다.

### 서버 필터와 직접 거르는 조건

[공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)을 따른다. 동 피드(`articleFeed`)·역 주변 매물·좌표 반경 카드·출퇴근·단지 매물은 서버가 조건을 건 응답이라 유형·면적을 다시 거르지 않는다. `-t 원룸`에 다른 카테고리가 섞여 와도 그대로 둔다 (2026-10-10 실측: 역삼동·신림동 원룸·오피스텔·투룸·아파트 피드 433건 모두 요청 카테고리 안이었다). 받은 뒤에는 중복·거래 불가를 빼고, 거래 조건이 여럿인 매물에서 검색한 거래 유형·금액에 맞는 거래를 고른다(`_matching_trade`, `property_types=None`). 고를 거래가 없으면 대표 가격을 내지 않고 빼며 `trade_unselected_notes`로 수와 사유를 알린다.

유형·거래·금액·면적을 직접 확인하는 곳은 필터 API(persisted query)가 거절돼 조건 없는 지도 페이지 20건으로 대체 조회할 때(`_FeedScan.take(..., server=False)`)뿐이다. 이때 판정할 값이 없는 매물은 통과시키지 않는다.

GraphQL의 HTTP 200도 `errors`를 검사한다. persisted-query 거절과 그 밖의 upstream 실패를 구분하고, 동 검색의 SSR 대체 경로가 지원하는 조건만 허용한다. 거절은 `FeedQueryRejectedError`(`JibsaError`, `UPSTREAM_ERROR`)라 대체 경로가 있는 곳만 먼저 잡고, 나머지 명령은 그대로 `UPSTREAM_ERROR`와 업데이트 안내로 끝난다. 좌표 → 동(`region_or_none`)은 결과 표시와 시·도 채우기에만 쓰여 실패해도(요청 제한 포함) 받아 둔 매물을 돌려준다. 역 이름 검색은 역 검색·역 주변 목록이 실패하면 반경 검색으로 넘어가고 `notes`로 실패 이유(`partial_failure_note`)와 함께 알리지만, 요청 제한은 다음 경로도 당근에 요청해 같은 제한에 걸리므로 바로 올린다. 덤으로 받는 조회(이름 검색의 단지 후보, 동 후기 수, 조건에 맞는 매물 수, 반경 검색의 중심 동, 같은 이름 동의 지도 확인)가 실패하면 받은 결과는 그대로 돌려주고 `partial_failure_note` 로 이유(API 변경·요청 제한·서버 오류·응답 형식 변경)를 `notes` 에 붙인다. 이유마다 다음 행동(업데이트·기다리기·다시 시도)이 달라서다. 위치 찾기(`_geocode`)가 당근에서 실패해 직방으로 넘어갈 때도 같은 이유를 붙인다. 업데이트가 필요하다는 끝말은 `UPDATE_NEEDED`·`UPDATE_MAYBE_NEEDED` 상수로만 쓴다. 매일 API 감시가 이 상수를 가져와 `notes` 에서 고장을 찾기 때문이다. 덤 조회(시·도 채우기 `sido_of` 포함)와 대체 경로(`_geocode` 의 직방 넘김 등)가 잡는 실패는 `JibsaError`·`HTTPError`(요청 제한 포함)와, JSON 이 아닌 응답·응답 모델 검증 실패(`ValueError`)다 (`OPTIONAL_LOOKUP_ERRORS` = 세 소스 공통 `OPTIONAL_LOOKUP_BASE_ERRORS` 에 `JibsaError` 를 더한 것). 덤 조회 하나가 차단 페이지를 받았다고 모아 둔 매물을 버리지 않고, `partial_failure_note` 가 '응답 형식이 달라 업데이트가 필요할 수 있다' 고 알린다. 주된 결과를 받는 조회는 에러(형식 오류는 `PARSE_ERROR`)로 끝내고, 요청 제한은 다음 요청도 같은 제한에 걸릴 때 바로 올린다. 좌표 검색의 실패를 동 검색 성공처럼 출력하지 않는다. 거래 조건이 여럿이면 선택한 거래의 가격·중개보수를 같이 정규화한다. 상태뿐 아니라 숨김·노출 제한·거래 조건 존재도 검사한다. 목록·핀/카드·SSR 상세가 같은 노출 상태를 주지는 않는다 (2026-10-10 실측: 목록은 통과했지만 상세에 `ArticleInvisibleInfo_NotVerified` 가 있어 상세가 거절된 매물). 목록에서 매물마다 상세를 다시 부르지 않으므로 상세 수준의 거래 가능 여부를 목록 전체에 보장하지 못한다.

## Action id 목록

명명 규칙은 [provider 작성 규약](../provider-conventions.md#action-id-명명)을 따른다. JSON API 는 `/kr/api` 접두어를 버리고, 페이지는 경로 파라미터를 뺀 세그먼트로, GraphQL 은 루트 필드 이름으로 짓는다. 루트 필드나 페이지 이름이 겹치는 경우는 괄호에 구분한 이유를 적었다.

| 엔드포인트 | Action id |
| --- | --- |
| `/kr/api/v1/regions/keyword` | `regions_keyword_v1` |
| `/map/{name1}/{name2}/{name3}` (페이지) | `map` |
| `/complexes/{originalId}` (페이지) | `complexes` |
| `/map/{name1}/{name2}/reviews` (페이지, `map` 과 겹치지 않게 세그먼트를 잇는다) | `map_reviews` |
| `POST /graphql` 의 `articleFeed` (GraphQL) | `article_feed` |
| `POST /graphql` 의 `articleMapPoints` (GraphQL) | `article_map_points` |
| `POST /graphql` 의 `articlesByOriginalArticleIds` (GraphQL) | `articles_by_original_article_ids` |
| `POST /graphql` 의 `getRegionByCoordinate` (GraphQL) | `get_region_by_coordinate` |
| `POST /graphql` 의 `searchComplexes` (GraphQL) | `search_complexes` |
| `POST /graphql` 의 `complexByOriginalId` (GraphQL, 단지 실거래가) | `complex_by_original_id` |
| `POST /graphql` 의 `complexByOriginalId.complex.articles` (GraphQL, 단지 매물. 루트가 위와 같아 구분) | `complex_articles` |
| `POST /graphql` 의 `articleByOriginalArticleId` (GraphQL, 매물 실거래가) | `article_by_original_article_id` |
| `POST /graphql` 의 `realsaleFeed` (GraphQL, 지역 실거래) | `realsale_feed` |
| `POST /graphql` 의 `realsaleNewHighFeed` (GraphQL, 지역 신고가) | `realsale_new_high_feed` |
| `POST /graphql` 의 `nearestCommuteStation` (GraphQL, 출퇴근) | `nearest_commute_station` |
| `POST /graphql` 의 `commuteFeed` (GraphQL, 출퇴근) | `commute_feed` |
| `POST /graphql` 의 `commuteStationArticleConnection` (GraphQL, 출퇴근) | `commute_station_article_connection` |
| `POST /graphql` 의 `regionByOriginalRegionId` (GraphQL, 동네 후기 요약) | `region_by_original_region_id` |
| `POST /graphql` 의 `livedReviewsByRegion` (GraphQL, 동네 후기) | `lived_reviews_by_region` |
| `POST /graphql` 의 `searchSubwayStationPois` (GraphQL, 역 검색) | `search_subway_station_pois` |
| `POST /graphql` 의 `searchAddress` (GraphQL, 주소·건물 검색) | `search_address` |
| `POST /graphql` 의 `geocodeAddress` (GraphQL, 주소 → 좌표) | `geocode_address` |
| `POST /graphql` 의 `subwayStationArticleConnection` (GraphQL, 역 주변 매물) | `subway_station_article_connection` |
| `POST /graphql` 의 `developmentDistricts` (GraphQL, 개발 호재) | `development_districts` |
| `POST /graphql` 의 `developmentByBusiNo` (GraphQL, 개발 사업 상세) | `development_by_busi_no` |
| `POST /graphql` 의 `educationMapPoints` (GraphQL, 교육 시설) | `education_map_points` |
| `POST /graphql` 의 `preschoolByNo` (GraphQL, 어린이집·유치원 상세) | `preschool_by_no` |
| `POST /graphql` 의 `complexByOriginalId` (GraphQL, 단지 비교 칸. 루트가 complex_by_original_id 와 같아 구분) | `complex_compare` |
| `POST /graphql` 의 `complexes` (GraphQL, 같은 동 단지. 페이지 `complexes` 와 겹쳐 구분) | `nearby_complexes` |
| `POST /graphql` 의 `complexesByOriginalComplexIds` (GraphQL, 단지 카드) | `complexes_by_original_complex_ids` |
| `POST /graphql` 의 `livableRegionScopes` (GraphQL, 좋은 동네 지역) | `livable_region_scopes` |
| `POST /graphql` 의 `recommendNeighborhoods` (GraphQL, 좋은 동네 추천) | `recommend_neighborhoods` |
| `POST /graphql` 의 `trendingComplexes` (GraphQL, 인기 단지) | `trending_complexes` |
| `POST /graphql` 의 `getViewRankingArticles` (GraphQL, 인기 매물) | `get_view_ranking_articles` |

## API 변경 시 점검

해시와 GraphQL 헤더는 client, 변수·필터 코드와 좌표 문자열 직렬화는 request, 연결·커서·거래 필드는 response에서 확인한다. SSR 변경은 relay → parser → 응답 모델 순으로 추적한다. 라우터 상태의 seroval 문법(`$R[n]=` 등록·`$R[n]` 참조, `!0`·`!1`, 문자열 이스케이프)과 `__ref`/`__refs`를 별도로 확인한다 (2026-10-17 웹 배포 전에는 `window.RELAY_STORE = "..."` 였다). 원본 본문·사진·연락처가 출력 모델로 새지 않도록 최종 service 모델도 검토한다.
