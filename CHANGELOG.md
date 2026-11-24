# Changelog

jibsa 의 버전별 변경 기록. 사용자(에이전트 포함)에게 보이는 변경만 적고, 아직 릴리스하지 않은 변경은
`Unreleased` 에 쌓는다. 번호 규칙과 쓰는 법은 [docs/development/release.md](docs/development/release.md) 에 있다.

## Unreleased

### ⚠️ 호환 깨짐

- 네이버 `listing`(상세)과 `search listings` 목록의 매물이 매물 유형에 따라 네이버 웹 상세에 칸이 없는 필드를 `null` 대신 키 없이 냄 (해당 없음. 목록에 없는 필드는 해당하지 않는다). 토지: `room_count`·`bathroom_count`·`room_type`·`direction`·`floor`·`building_floor`·`area_m2`·`area_pyeong`·`supply_area_m2`·`approved_at`·`heating`·`heating_fuel`·`entrance`·`parking`·`elevator`·`options`. 고시원: 토지와 같되 `elevator`·`options` 는 남고 `loan_manwon` 이 빠진다. 재개발: 방·욕실·방 구조·면적. 사무실·상가·지식산업센터: `room_count`·`room_type`. 건물·상가건물·숙박·공장·창고·기타: `room_count`·`room_type`·`floor`·`supply_area_m2`. 매매 세금은 웹이 그리는 것만 내 `property_tax_manwon`·`comprehensive_real_estate_tax_manwon` 은 아파트·재건축·단지형 빌라에만 있고, 원룸·고시원과 일반분양권이 아닌 분양권·오피스텔분양권 매매는 세금 요청을 하지 않아 세 키가 없고, 분양 상태를 모르는 분양권 매매도 세금을 요청하지 않아 `acquisition_tax_manwon` 이 `null` 이다 (두 키는 없다). 직거래 매물은 중개사가 없어 네이버 웹이 중개보수를 보여 주지 않으므로 `agent_fee_manwon`·`agent_fee_individual_check_required` 키가 없고 중개보수 요청도 하지 않는다 (예전에는 금액이 나갔다). 아파트·오피스텔·재건축·분양권 상세의 `parking` 은 매물 값(`가능 (단지 전체 12456대)`) 대신 네이버 웹 단지 칸과 같은 단지 값(`단지 전체 12602대 (세대당 1.32대)`)이고 가능·불가는 붙지 않는다. 같은 상세의 `approved_at` 도 네이버 웹처럼 단지 정보의 사용승인일만 쓴다 (예전에는 매물의 건물 날짜가 있으면 그것을 먼저 썼고, 단지 조회가 실패하면 `null` 이다). `floor` 가 없는 매물은 `floor_number` 도 없다. 이 필드를 늘 있다고 보고 읽던 쪽은 키가 없을 때와 `parking` 에 가능·불가가 없을 때를 처리한다 (#303, #304, #305)
- 라이브러리로 쓸 때: `core.browser` 의 `BrowserTransport` 는 설정을 `BrowserOptions` 하나로 받고(모두 키워드), `AsyncBrowserTransport` 는 감쌀 `BrowserTransport` 하나를 받는다. `BrowserTransport('naver', url, ready_cookie='NNB')` 는 `BrowserTransport(BrowserOptions(source='naver', entry_url=url, ready_cookie='NNB'))` 로, `AsyncBrowserTransport('naver', url, ready_cookie='NNB')` 는 `AsyncBrowserTransport(BrowserTransport(BrowserOptions(...)))` 로 고친다. 소스 client 의 `browser_transport()`·`async_browser_transport()` 를 쓰면 고칠 것이 없다 (#216)
- 라이브러리로 쓸 때: `core.browser` 의 `ProxyUnreachableError`·`SHARED_BROWSER_ERRORS` 와 브라우저 transport 의 `no_cors_hosts`(`BaseHTTPClient.browser_no_cors_hosts`)를 뺌. 프록시 오류는 모두 `ProxyError` 로 잡는다. 출처 탭(`no_cors_hosts`)과 소스 간 공통 실패 구분은 쓰던 당근 옛 지역 API·다른 소스로 위치 찾기를 빼 쓰는 곳이 없다 (#215)
- 라이브러리로 쓸 때: `jibsa.providers.zigbang` 의 `ZigbangGuestAuth` 와 `ZigbangClient` 의 `token`·`account_host`·`token_url`, `core.http` 의 `bearer_authorization` 을 뺌. 로그인하지 않은 직방 웹처럼 손님 토큰을 받지 않고 부른다. `ZigbangClient(token='x')` 처럼 주던 인자는 `ValidationError` 이니 지운다 (#220)
- 라이브러리로 쓸 때: `NaverLegalDivisionSubInfoListV1RequestParameterModel` 의 `legal_division_level_type` 이 그 지역 자신의 단위(`SI`·`GUN`) 대신 받을 하위 지역의 단위 `GUN`(시·도 코드의 시·군·구)·`EUP`(시·군·구 코드의 읍·면·동)을 받는다 (네이버 웹이 보내는 값). `'SI'` 는 `ValidationError` 이니 시·도 코드는 `'GUN'`, 시·군·구 코드는 `'EUP'` 로 바꾼다. 구 코드에 `SI` 를 주면 속한 시·도의 구를 주던 조합은 없어졌다 (#302)
- 라이브러리로 쓸 때: `jibsa.providers.naver` 의 `resolve_region_with_notes` 를 뺌. 당근이 네이버로 위치를 찾던 데만 썼다. 네이버 검색 위치는 `naver search listings` 와 같은 `jibsa.providers.naver.service.region.resolve_search_region`(주소 → 동 → 역 → 단지, 위치·종류·안내를 돌려준다)으로 찾는다 (#215)
- 라이브러리로 쓸 때: `jibsa.providers.daangn` 의 `resolve_regions`·`search_locations`·`search_listings`·`DaangnSearchResult` 를 뺌. 지역 후보는 `search_areas`, 동·구 하나는 `resolve_area`(같은 이름이면 `'강남구 신사동'` 처럼 앞에 붙인다), 역·대학·도로명 주소는 `find_station`·`find_university`·`find_address` 로 찾는다. 매물은 동 `search_dong`, 지도 화면 범위(구·좌표·주소) `search_map_area`, 역 `search_station`, 대학 `search_university` 로 받고, 결과는 `DaangnDongSearchResult`·`DaangnMapSearchResult`·`DaangnStationSearchResult`·`DaangnUniversitySearchResult` 다 (#215)
- 라이브러리로 쓸 때: `core.errors` 의 `UnsupportedRegionError` 를 뺌. 다방(시·군·구 전체, 구가 있는 시)과 당근(동에 속하지 않는 좌표)은 예전과 같은 `code`(`REGION_NOT_SUPPORTED`·`REGION_NOT_FOUND`)의 `JibsaError` 를 던지니 `code` 로 가른다. 읽는 곳이 없던 `skip_note` 도 함께 없어졌다
- 라이브러리로 쓸 때: `core.http` 의 `should_retry_non_idempotent` 와 `core.listing` 의 `beyond_radius_notes` 를 뺌 (쓰는 곳이 없었다). `BaseHTTPClient` 의 `url_schema` 필드를 뺌 (베이스 URL 은 늘 https 라 넘기면 `ValidationError`). `create_base_url(schema, host)` 는 `create_base_url(host)`, client 의 `default_rate_limit` 은 dict 대신 `RateLimitPolicy` 다 (서브클래스는 `RateLimitPolicy(min_interval=..., ...)` 로 선언한다). `raise_for_status`·`describe_failed_attempt` 의 `limit`, `wait_retry_after` 의 `default`·`maximum`, `limit_notes` 의 `basis` 인자를 뺐고, `limit_notes` 의 `inspected`·`has_more` 는 반드시 넘긴다
- 당근 `preschools` 가 지역·역·좌표 반경 대신 단지 ID 하나를 받아 그 단지 근처 어린이집·유치원을 줌. 당근 웹이 범위 안 시설을 지도에 띄우던 기능을 없애고 단지 화면 학군의 유치원 탭으로 옮겼다. 목록과 순서는 그 탭과 같다 (이 단지 주민이 많이 다니는 곳 먼저, 같으면 가까운 곳 먼저). `PLACE`·`--lat`·`--lng`·`--radius`·`-t`·`--limit` 을 뺐고, 결과는 `complex_id`·`returned`·`preschools[]`(`id`·`name`·`distance_km` 단지에서·`resident_count` 이 단지 주민 중 다니는 수·`review_count`)·`url` 이다 (`radius_km`·`total`·`type` 은 없다). 당근은 단지에서 1km 안을 가까운 순으로 20곳까지만 줘, 20곳이면 `[일부]` 로 알린다. 당근이 근처 시설 정보를 주지 않으면 `preschools` 는 `null`(모름)이고, 1km 안에 시설이 없으면 `[]` 다. 단지 ID 는 `search complexes <동>` 으로 찾고, 어린이집·유치원 구분은 `preschool <id>` 로 본다. 지역·역 이름이나 뺀 옵션을 주면 `INVALID_ARGUMENT` 이고 `hint` 가 이 방법을 알린다 (#192)
- 당근 `developments`·`development` 를 뺌. 당근 웹이 개발 호재 목록과 지도 표시를 없애 사업 번호를 얻을 곳이 없다. 재개발·재건축 구역은 네이버 `search redevelopment`·`redevelopment` 로 본다. 옛 명령을 부르면 `hint` 가 이 네이버 명령을 알린다 (#192)
- 당근 `search listings` 의 위치 입력을 당근 웹 화면별로 나눔. 이름 인자는 동·구 이름만 받고, 역은 `--station <역>`, 대학은 `--university <대학>`, 도로명 주소는 새 `--address <주소>`, 좌표는 `--lat/--lng` 로 준다. 역·장소·주소·건물·리 이름을 이름 인자로 주던 호출은 `REGION_NOT_FOUND`(역 이름이면 `hint` 가 `--station` 을 알린다)나 비슷한 지역을 후보로 주는 `REGION_AMBIGUOUS` 가 된다. 건물 이름은 당근 주소 검색이 찾지 않으니 그 건물의 도로명 주소(`--address`)나 `--lat/--lng` 로 준다 (#215)
- 당근 `search listings` 의 `--radius`·`--expand` 와 당근 명령 전체(`search listings`·`region-real-price`·`region-reviews`·`search complexes`·`trending-complexes`·`popular-listings`)의 `--city` 를 뺌. 같은 이름 지역은 `'강남구 신사동'`·`'서울 중구'` 처럼 이름 앞에 구·시·도를 붙인다. 뺀 옵션을 주면 `hint` 가 지금 쓰는 법을 알린다 (#215)
- 당근 구 이름·좌표 검색이 반경 안을 가까운 순으로 주던 것에서, 당근 웹 지도 화면 범위(데스크톱 기준, 구는 구 중심 줌 12, 좌표는 줌 15 약 1.6×1.7km)의 목록을 웹처럼 최근 순으로 주게 바뀜. 범위 크기는 `--zoom` 으로 준다. 결과의 `radius_km` 대신 `zoom`·`width_km`·`height_km` 가 오고, `total` 은 범위 안 당근 집계(1000 에서 잘림)다. 반경 밖 매물을 이어 붙이지 않는다. 구 이름은 예전에 그 구의 첫 동 하나로 찾았다 (#215)
- 당근 `성수동` 처럼 `○가` 로 나뉜 동은 1가·2가를 합치지 않고 `REGION_AMBIGUOUS` 로 `성수동1가`·`성수동2가` 중 하나를 고르게 함 (#215)
- 당근 `search commute` 의 회사 위치를 `WORKPLACE`(회사가 있는 동·구, 그 중심)·`--station`·`--university`·`--address`·`--lat/--lng` 로 받음. 역·장소 이름을 `WORKPLACE` 로 주던 호출은 `--station`·`--university` 로 바꾼다 (#215)
- 당근 `search listings --station`·`--university` 에 세대수·주차대수 조건(`--household-min`·`--household-max`·`--parking-min`)을 주면 `INVALID_ARGUMENT`. 역·대학 주변 목록은 이 조건을 받지 않아 결과가 조용히 틀린다. 예전에는 역 좌표의 반경 검색으로 바꿔 찾았다 (#215)
- 당근 `search locations` 의 `results[]` 에 시·도·구 후보도 오고 `level`(`시도`·`구`·`동`)이 붙음. 지역 후보는 법정동만 온다 (#215)
- 당근 동 이름 `search listings` 가 당근 웹 지도에서 동을 누른 목록처럼 그 동 매물만 줌. 결과의 `regions`·`fetched` 와 매물의 `in_regions` 를 없애고 `region`(찾은 동)을 준다. `total` 은 그 동의 거품 수(웹 지도의 "매물 N개", 1000 에서 잘리지 않음)다. 예전에는 조건이 없으면 주변 동 매물을 섞어 주고 `in_regions: false` 로 표시했다 (#215)
- 당근 매물 검색에서 거래 조건이 여럿인 매물은 당근 웹 목록처럼 `--trade` 의 거래 유형으로만 보여 줄 거래를 고르고 매물을 빼지 않음. 예전에는 금액까지 맞는 거래가 없으면 뺐다. `--trade` 에 여러 유형을 주면 보여 준 거래가 금액 조건에 맞은 거래가 아닐 수 있으니 가격 비교는 `--trade` 하나로 한다. 아는 거래(매매·전세·월세·단기임대·연세)가 없는 매물은 빼고 그 수를 `[제외]` `notes` 로 알린다 (`popular-listings` 도 같다) (#222)
- 당근 `--trade` 없이 금액 조건만 주면 거래 유형을 짐작하지 않음. `--rent-max` 만 주면 월세만 찾던 것이 당근 웹처럼 전세·매매도 나오고 `notes` 가 알린다. 한 거래 유형만 보려면 `--trade` 를 함께 준다 (#222)
- 당근 `popular-listings` 가 당근 웹 순위 화면처럼 `-t` 를 하나만 받고 30위까지만 줌 (`--limit` 최대 100 → 30, 기본 20 → 30). 쉼표로 잇거나 `-t` 를 되풀이해 둘 이상 주면 `INVALID_ARGUMENT` 다 (#222)
- 당근 `trending-complexes` 가 동 주변 대신 당근 웹의 인기 급상승 단지(어제 대비 오늘 조회 급상승)를 전국·시·도·구 안에서 줌. 인자는 시·도·구 이름이고 빼면 전국이며, 동 이름은 `INVALID_ARGUMENT` 다. 결과의 `region` 은 `name`·`region_id`·`level` 이고 50곳까지 온다. 대표 평형은 세대수가 가장 많은 평형이다 (#222)
- 당근 `preschool` 의 `children` 을 `capacity` 로 바꿈. 당근 웹이 '정원' 으로 보여 주는 값이라 지금 다니는 원아 수가 아니다. 읽는 쪽도 새 이름으로 고친다 (#222)
- 당근 `nearby-complexes` 의 단지마다 `listing_count`(전체 매물 수)를 `listing_counts`(매매·전세·월세별 매물 수)로 바꿈. 당근 웹에서 사라진 단지 카드 쿼리 대신 웹 지도 단지 카드를 쓰는데, 그 카드에는 전체 수가 없다. 읽는 쪽은 세 수를 더해 쓴다 (단기임대는 빠진다) (#222)
- 당근 `price-trend` 가 당근 웹 단지 화면 시세 그래프처럼 평형 하나로 보고 기간을 웹 탭으로 고름. 평형을 주지 않으면 모든 평형 평균 대신 대표 평형이고, 아파트형 단지는 `--pyeong <공급 평형>` 으로 고른다. `--years` 를 없애고 `--period 1년|3년|전체`(기본 1년)를 받는다. 변화율(`summary`)은 최근 3개월과 N년 전 3개월 비교 대신 웹처럼 기간 안 첫 거래 달과 마지막 거래 달을 견주어 `start_month`·`start_average_manwon`·`end_month`·`end_average_manwon`·`months`·`change_percent`·`change_manwon` 을 준다. 결과의 `years` 는 `period` 로 바뀌고, 웹 그래프 머리의 최근 3개월 평균(`recent_average_manwon`·`recent_transactions`)이 붙는다. 평형 묶음 정보가 없는 단지는 모든 평형을 섞은 평균 대신, 당근 웹처럼 그래프 없는 빈 결과(`points: []`, `summary: null`)와 `notes` 를 준다 (#222)
- 당근 `compare` 가 당근 웹 단지 비교처럼 단지마다 평형 하나로 비교함 (첫 단지는 대표 평형, 나머지는 그 전용면적과 가장 비슷한 평형. 첫 단지에 평형 자료가 없으면 모두 대표 평형). `area_groups[]` 대신 `pyeong`(그 평형의 KB 매매·전세·월세 시세와 최근 매매·전세·월세 실거래)을 주고, `asking` 은 최저~최고 범위 대신 거래 유형별 평균(`sale`·`jeonse`·`monthly_deposit`, 0원 제외, 월세는 보증금 평균)이다. 관리비는 최근 한 달 ㎡당 값(`manage_cost_month`) 대신 받은 달 평균(`manage_cost_per_m2_manwon`·`manage_cost_period`)과 그 평형의 월 관리비 추정(`manage_cost_manwon`)이다. 최대 단지 수는 5곳에서 웹과 같은 10곳이다 (#222)
- 당근 `good-neighborhoods` 가 당근 웹 좋은 동네 추천처럼 늘 5곳을 주고 `--limit` 을 없앰. `--region` 을 주지 않으면 전국 대신 웹 첫 화면처럼 서울에서 찾고 `notes` 로 알린다 (당근 웹에는 전국 순위가 없다). 다른 곳은 `--region` 으로 준다 (#222)
- 당근 `school` 이 이름이 들어간 학교가 여럿이면 첫 학교를 고르지 않고 `REGION_AMBIGUOUS` 로 후보(`name`·`address`·`school_code`)를 줌. 고른 학교의 학교 코드로 다시 부른다 (`jibsa daangn school B100000749`). `--city` 를 없앴고, 좌표가 없는 학교는 당근 웹처럼 뺀다. 이름이 똑같은 학교가 하나뿐이어도 검색 결과에 다음 쪽이 있으면 뒤쪽에 같은 이름이 더 있을 수 있어 검색어마다 최대 3쪽(150곳)까지 이어 받아 세고(요청 최대 2회 더), 같은 이름이 더 나오면 그 후보를 주며, 3쪽을 넘게 남거나 쪽 넘김이 멈추면 고르지 않고 `REGION_AMBIGUOUS`(`이름이 같은 학교가 더 있을 수 있어 고르지 않았습니다`, `candidate_count` 는 `null`)로 알린다. 이름이 같은 학교가 하나뿐이어도 이 에러가 나면 `hint` 대로 그 학교의 `school_code` 로 다시 부른다. 이름이 그대로 같지 않은 후보(줄인 이름 검색으로만 나온 학교 등)가 하나뿐이어도 검색 결과에 다음 쪽이 남았으면 고르지 않고 `REGION_AMBIGUOUS`(`… 1곳 이상이라 고르지 않았습니다`, `candidate_count` 는 `null`)로 알린다 (#215)
- 당근 `school` 의 배정 단지를 세대수 순 대신 당근 웹 학교 화면과 같은 순서로 주고, 단지마다 최근 매매를 3건 대신 웹처럼 1건 줌 (#222)
- 당근 `search commute` 가 회사 역 주변 매물(지하철 0분)을 넣지 않고, 매물을 통근 시간 순으로 다시 세우지 않고 역마다 당근 순서로 줌. `reachable_stations` 에서도 회사 역이 빠진다. 회사 역 주변은 `search listings --station <역>` 으로 본다 (`--max-minutes` 안에 조건에 맞는 매물이 있는 역이 없으면 빈 결과에 그 명령을 `notes` 로 알린다). 회사에서 걸어서 60분 안에 지하철역이 없으면 당근 웹처럼 `NOT_FOUND` 다 (#222)
- 당근 `search commute` 의 매물별 `commute_minutes`(매물 도보 + 지하철 + 회사 도보)를 뺌. 당근 웹에 없는 계산이다. 대신 역 묶음(`stations[]`)에 웹이 보여 주는 편도 시간 `one_way_minutes`(지하철 + 회사 역→회사 도보)가 붙고, 문 앞까지는 매물의 `walk_to_station_minutes` 를 더한다. 갈 수 있는 역은 웹 출퇴근 지도처럼 요청 1회로 전부 받아 `reachable_stations` 가 200곳에서 잘리지 않고, 역 목록이 멈췄다는 `notes` 도 없다 (#222)
- 당근 `region-real-price` 의 `--sort` 를 빼고, 매매의 순서를 최신 순에서 당근 웹 실거래 화면과 같은 가격 순(최근 공개일부터, 같은 날 안에서 가격 높은 순)으로 바꿈. 전세·월세는 그대로 최신 순이다. 매매를 최신 순으로 받는 방법은 없어졌고, `--sort` 를 주면 `INVALID_ARGUMENT` 이고 `hint` 가 정렬 규칙을 알린다. 리 거래 주소에 읍·면을 끼워 넣지 않고 당근이 준 그대로(`경기도 양평군 양근리`) 주며, `cancelled` 는 전세·월세에도 온다 (#222)
- 당근 `real-price`·`price-trend` 가 아파트형(공급 평형이 있는) 단지에 `--area` 를 주면 `INVALID_ARGUMENT` 로 `--pyeong` 을 안내함. 당근 웹은 그 단지에서 전용면적 묶음을 쓰지 않아 `--area 84` 가 32평·33평을 섞었다. 아파트형이 아닌 단지에 없는 묶음을 주어도 `INVALID_ARGUMENT` 다 (#222)
- 당근 `search listings --complex <단지 ID>` 가 `-t` 없이 당근 웹 단지 화면처럼 아파트·주택·오피스텔·원룸·투룸만 줌. 단지 안 상가·사무실은 `-t 상가` 처럼 골라야 온다 (예전에는 전체라 상가가 섞였다) (#222)
- 당근 `search listings --university <대학>` 이 조건을 하나도 주지 않으면 당근 웹 대학 페이지처럼 원룸·투룸·오피스텔만 찾고 `notes` 로 알림. 조건이 하나라도 있으면 그대로다 (#222)
- 당근 `popular-listings -t` 가 당근 웹 순위 화면처럼 원룸·투룸·아파트·오피스텔만 받음. 주택·상가 등 다른 종류는 `INVALID_ARGUMENT` 다 (#222)
- 당근 `search complexes --trade` 의 기본값을 없앰. 주지 않으면 매매로 보여 주되 당근 웹처럼 거래 유형을 단지 조건으로 보내지 않는다 (`--trade` 나 가격 조건이 있을 때만 보낸다). 결과의 `trade_type` 은 그대로 `매매` 다 (#222)
- 당근 `nearby-complexes` 가 당근 웹처럼 기타 유형 단지를 빼고, 결과에 `sort`(`세대수`)가 붙음 (#222)
- 당근 `real-price`·`region-real-price` 의 전월세 `renewal`(bool)을 당근 웹 배지와 같은 두 필드로 나눔: `contract_type`(`신규`·`재계약`, 당근이 계약 종류를 주지 않으면 `null`)과 계약갱신요구권을 쓴 계약 `renewal_right`(bool, `real-price` 만. 지역 실거래 피드에는 없어 `region-real-price` 에는 키가 없다). 예전 `renewal: true` 는 둘을 합친 값이었다. 읽는 쪽은 `contract_type == "재계약"` 또는 `renewal_right` 로 고친다 (#222)
- 당근 지역 이름을 당근 부동산 웹 지도 검색창과 같은 지역 검색으로 찾음. 이름이 정확히 같은 법정동·구만 쓰고, 이름이 같은 곳이 없으면 비슷한 지역(`역삼` → 역삼동)을 `REGION_AMBIGUOUS` 의 후보로 준다. 시·도(`서울`)를 주면 그 시·도의 구를 모두 후보로 준다. 예전에는 당근마켓(중고거래) 지역 검색을 써서, 못 찾은 이름은 직방(막히면 네이버) 지역 검색으로 좌표를 빌려 찾았다. 이제 당근 명령은 당근 요청만 쓴다. 예전에 찾히던 이름이 `REGION_AMBIGUOUS`·`REGION_NOT_FOUND` 일 수 있어, 쓰는 쪽은 에러의 후보 이름(`candidates`)을 그대로 다시 넣는다 (#215)
- 당근 `listing --trade` 에 매물에 없는 거래 조건을 주면 `LISTING_UNAVAILABLE`(`TRADE_NOT_OFFERED`) 대신 대표 조건을 보여 주고 `notes` 로 알림. `--details` 도 목록을 받은 뒤 그 거래 조건이 내려간 매물을 빼지 않고 대표 조건의 거래 유형·가격으로 바꿔 알린다. 쓰는 쪽은 `TRADE_NOT_OFFERED` 에러 대신 결과의 `trade_type` 과 `notes` 로 요청한 거래가 없는지 본다 (#222)
- 당근 `region-reviews` 의 `review_count` 가 동네 요약에 쓰인 후기 수(60 에서 잘림, 구는 `null`) 대신 동·구의 실제 후기 수를 줌 (당근 웹 모바일 화면의 '후기 N개'). `--top` 기본을 10 에서 당근 구 후기 페이지와 같은 20 으로 바꿈. 쓰는 쪽은 `review_count` 를 60 에서 잘린 요약 기준 수가 아니라 동·구의 전체 후기 수로 읽는다 (구도 수가 온다) (#222)
- 당근 `region-reviews` 에 동을 주면 `top_complexes` 가 구 전체의 단지 대신 그 동의 단지(후기가 있는 것, 후기 많은 순, 당근 동 후기 페이지가 주는 500곳까지. 후기 없는 단지가 뒤에 붙으므로 받은 500곳의 마지막 단지에도 후기가 있을 때만 `[일부]` 로 더 있을 수 있다고 알린다)가 됨. 동 후기 페이지가 단지 유형을 주지 않아 동으로 찾으면 `property_type` 은 늘 `null` 이다. 구 전체 기준이라는 `[참고]` `notes` 는 없어졌다. 구 전체 단지가 필요하면 구 이름으로 찾는다. 동 이름에 구 전체 기준 목록이 오리라 보고 읽던 쪽은 그 동의 단지로 읽는다. 동으로 찾으면 결과 `url` 과 안내의 후기 페이지 주소도 구 후기 페이지 대신 동 후기 페이지다 (#393)
- 당근 매물의 `trade_type` 에 `연세`(제주에서 1년치 월세를 한 번에 내는 거래)가 올 수 있음. 연세가 대표 거래인 매물은 당근 웹 목록처럼 연세로 보여 준다 (예전에는 같은 매물의 다른 거래를 보여 주거나 연세만 있으면 뺐다). 쓰는 쪽은 `연세` 를 처리하고, 금액은 `rent_manwon` 이 아니라 `yearly_rent_manwon`(1년치)으로 읽는다 (#222)
- 다방 `search listings`·`search complexes`·`search sales` 에 `성수동` 처럼 `○가` 로 나뉜 동을 주면 1가·2가를 합쳐 찾지 않고 `REGION_AMBIGUOUS` 로 `○가` 동을 모두 후보(전체 주소)로 줌. 다방 웹 검색창처럼 동 하나만 찾는다. 후보 하나(`성수동1가`)로 다시 부른다. 합친 이름(`"성수동1가·성수동2가"`)의 `region` 과 `--limit` 을 동마다 나눴다는 `notes` 는 없어졌다 (#235)
- 다방에 여러 캠퍼스에 맞는 줄인 대학 이름(`연세대`)을 주면 첫 캠퍼스로 찾고 `[모호]` 로 알리던 것을 고르지 않고 `REGION_AMBIGUOUS` 로 캠퍼스 이름을 후보로 줌. 후보 이름을 따옴표로 감싸 그대로(`'연세대학교(원주캠퍼스)'`) 다시 부른다. 이름이 똑같은 역이 여럿 와도 첫 역 대신 `REGION_AMBIGUOUS`(후보에 노선)이고 `hint` 대로 `search locations` 의 좌표로 찾는다 (매물·단지·분양 검색. 좌표를 받지 않는 `station-prices` 는 가려 받지 못한다고 알린다). 동만 받는 `neighborhood`·`popular-listings` 와 역만 받는 `station-prices` 는 받지 않는 종류의 이름에 후보를 고르라고 하지 않고 바로 `INVALID_ARGUMENT` 다 (#235)
- 다방 `real-price --listing` 의 `--trade` 기본값을 매매에서 다방 매물 화면처럼 매물의 거래 유형(매매 매물은 매매, 월세·전세 매물은 전월세)으로 바꿈. 매매 거래를 보려면 `--trade 매매` 를 준다. 범위·거래 유형을 다방에서 먼저 받아 요청이 1회 는다. `basis` 는 다방이 이 집(같은 지번 건물) 거래를 주면 `"이 집 (망원동 다세대·연립)"` 이고, 같은 동 거래면 전처럼 `"역삼동 단독·다가구"` 다 (예전에는 늘 같은 동 거래라고 알렸다). 범위는 거래 유형마다 달라 `--trade` 로 받은 거래의 범위를 알린다. 단독·다가구 거래는 `area_m2`·`floor` 대신 `total_floor_area_m2`(다방이 연면적이라 부르는 건물 전체 면적)와 매매만 `house_type`(`단독`·`다가구`)을 준다. 읽는 쪽은 단독·다가구 면적을 `total_floor_area_m2` 로 읽고 매물 전용면적과 견주지 않는다 (#235)
- 다방 `complex` 의 `recent_sale`·`recent_lease` 가 면적이 같은 평형이 여럿이면 `space_seq`·`area_m2` 를 `null` 로 두고 `[참고]` 로 후보 평형을 알림 (예전에는 첫 평형을 골랐다). 다방 화면의 면적은 새 `supply_area_m2`(아파트)·`contract_area_m2`(오피스텔)로 온다 (#235)
- 다방 `nearby` 의 `nearest`·`schools` 항목을 `{type, name, distance_m}` 하나에서 `{type, places: [{name, distance_m}, …]}` 로 바꿔 종류마다 다방 거리로 가까운 순 3곳까지 줌. 종류 이름도 다방 화면 이름표로 바꿈: 버스정류장 → 버스, 공공기관 → 관공서, 경찰 → 치안. 읽는 쪽은 가장 가까운 곳을 `places[0]` 으로 읽는다 (#235)
- 다방 `search sales` 의 `household_count` 를 `sale_household_count` 로 바꿈. 다방 목록의 값은 총세대수가 아니라 분양 세대수다. 총세대수는 `sale` 의 `household_count` 로 본다 (#235)
- 다방 `region-ranking` 의 거래량·매물수·선호도·전세가율·갭가격이 `-t` 없이 다방 웹 기본처럼 아파트·오피스텔 합산 순위를 줌 (예전에는 아파트만). 아파트만 보려면 `-t 아파트` 를 준다. `-t 아파트,오피스텔` 도 합산이고, 평균가·평당가·시세증감·최고가증감에 둘을 주면 `INVALID_ARGUMENT` 다. 결과에 `complex_type`(`아파트`·`오피스텔`·`아파트·오피스텔 합산`)이 붙는다 (#235)
- 다방 `search sales` 의 시·군·구 결과가 다방 웹 분양 지역 목록('분양정보' 목록)과 같은 목록·순서로 오고, `total` 이 경계를 덮는 사각형 안 수에서 그 시·군·구의 분양 단지 수(웹 '총 N건')로 바뀜 (김포시 74 → 37). 주소로 걸러 뺐다는 `[제외]` 안내는 없어졌고, 전국·시·도·시·군·구가 다방이 첫 쪽에 함께 주는 추천 칸(`features`)은 웹 분양 목록에 없어 넣지 않고 `[제외] 다방 추천 칸(features) N곳은 웹 분양 목록에 없어 넣지 않았습니다` 로 수만 알린다. 이 결과(새로 받는 전국·시·도도)에는 `household_count` 가 총세대수로 온다 (0.12.0 의 `household_count` 는 분양 세대수였고 지금은 `sale_household_count` 다). 공공·민간임대의 `price_kind` 는 `보증금` 대신 웹 목록처럼 `임대가` 다. 읽는 쪽은 `total` 을 그 지역 전체 분양 수로, `household_count` 를 총세대수로 읽고, `price_kind` 는 `임대가`·`보증금` 둘 다 분양가가 아닌 것으로 본다. 동·역·대학·좌표는 전처럼 지도 목록이고 `household_count` 는 `null` 이다 (#244)
- 직방 `search listings room` 이 검색 중심에서 가까운 순 대신 직방 웹 목록처럼 묶음 순서(안심추천 → 안심일반 → '이 지역 오피스텔' → 일반 등, 묶음 안은 직방이 준 순서)로 줌. 가까운 매물은 `distance_km` 로 고른다. 반경·동 경계 안 매물이 모자라도 반경 밖 매물로 채우지 않고, 반경은 반올림 전 거리로 가른다. 역 검색은 직방이 역 반경으로 준 결과 그대로다. 종류를 여럿 찾으면(기본 원룸·오피스텔·빌라) `--limit` 을 종류 수로 고르게 나눠 종류별 묶음으로 주고, 원룸 목록과 오피스텔 목록에 함께 있는 매물은 `--next` 로 이어 받아도 한 번만 내고 `notes` 로 알린다. `total` 은 범위 안 서로 다른 매물 수다. 오피스텔은 직방이 섞지 않은 순서(매물 번호순)로 받아 `--next` 의 자리가 흔들리지 않게 하고, `--without-random` 옵션은 없앴다 (늘 그렇게 받는다) (#272)
- 직방 `search listings --complex officetel-…` 이 직방 웹 건물 화면처럼 묶음 순서(안심추천 → 안심일반 → 일반 등)로 줌. `--without-random` 옵션은 없앴다 (늘 섞지 않은 순서로 받는다) (#272)
- 직방 `search listings store` 가 가까운 순 대신 직방 웹 상가 목록 순서 그대로 줌 (가까운 매물은 `distance_km`). 반경 밖 매물로 채우지 않고 반경은 반올림하지 않는다. 동 이름(`--radius` 없음)은 그 동 안을 찾고(`○가` 로 나뉜 동은 함께), 리·구·시·역·학교·좌표는 반경이다. 가격 조건은 가까운 후보 대신 직방 목록 앞의 후보를 확인한다. 직방 상가 순서는 시간이 지나면 바뀐다 (#273)
- 직방 `search listings stay` 의 기본 정렬을 가까운 순에서 직방 웹과 같은 추천순(`--sort recommended`)으로 바꿈. `--sort distance` 는 `--radius` 없는 역 이름 검색에서만 되고, 그 밖에는 `INVALID_ARGUMENT` 다. 역·학교·동·구 이름은 직방 단기임대 검색 결과를 직방 순서 그대로 주고(역은 역 1km 안이라 `radius_km` 1, 동·구는 이웃 동 매물이 섞일 수 있다고 알린다), 좌표·`--radius` 는 반경 안 지도 매물을 직방 웹 지도 목록과 같은 순서로 준다 (`--sort price` 는 웹처럼 핀이 주는 주당 합계 원 단위로 세워, 만원 단위로 같아 보이는 매물도 원 단위로 낮은 쪽이 앞이다). `성수동` 처럼 `○가` 로 나뉜 동과 성남시처럼 구가 있는 시를 합쳐 찾던 것을 없애고 `REGION_AMBIGUOUS` 로 `성수동1가`·`성남시 분당구` 같은 후보를 고르게 한다 (#274, #374)
- 직방 단기임대 기간 비용을 뺌: `search listings stay --details`, `listing stay-… --pet`, 결과의 `period_cost`. 직방 웹은 로그인해야 기간 요금을 보여 준다. `listing stay-…` 에 날짜를 주면 예약 가능 여부 `available` 만 붙고, 매물의 계약 기간에 맞지 않는 날짜는 `INVALID_ARGUMENT` 대신 `available: false` 다. 쓰던 쪽은 `--details`·`--pet` 을 지운다 (#275)
- 직방 `search listings apt` 의 `--radius` 를 뺌. 역·학교 이름과 `--lat/--lng` 는 반경 안 단지를 훑는 대신 그 위치가 속한 동의 매물 목록을 직방 웹 지도의 '○○동 주변 매물보기' 와 같게 준다 (역 주변 단지·학교 배정단지는 새 `search complexes` 이고 `notes` 가 그 명령을 알린다. 검색어는 `영등포구 양평역` 처럼 사용자가 앞에 붙인 구·동 낱말을 살려 같은 이름 역·학교 중 그 곳을 가린다. 학교 배정단지는 그 명령이 찾는 학교, 곧 직방 웹이 배정단지 목록을 보여 주는 학교에만 권한다). 동·구 이름은 법정동 코드로 찾고 좌표를 쓰지 않아 직방이 좌표를 주지 않은 동·구도 찾고 `region` 의 `lat`·`lng` 만 `null` 이다 (역·학교 이름은 그 좌표로 위치가 속한 동을 찾으므로 좌표가 없으면 `UPSTREAM_ERROR` 다). 시·도 이름은 반경으로 찾지 않고 `REGION_NOT_FOUND` 다. `성수동` 처럼 `○가` 로 나뉜 동과 성남시처럼 구가 있는 시는 목록을 합치지 않고 `REGION_AMBIGUOUS` 로 후보(`성수동1가`·`성남시 분당구` 등)를 알린다. `local_code` 는 늘 코드 하나다. `--radius` 를 주던 쪽은 지우고 동·구 이름이나 `search complexes` 를 쓴다 (#277, #376)
- 직방 지역 이름(역·학교·동·구)을 찾을 때 직방이 좌표를 주지 않은 결과도 같은 이름 후보로 셈. 같은 이름이 둘이고 한쪽에 좌표가 없으면 0.12.0 까지는 그쪽을 건너뛰고 남은 곳으로 찾았지만, 이제 고르지 않고 `REGION_AMBIGUOUS` 로 후보를 알린다 (후보 이름으로 다시 부른다). 고른 곳의 좌표를 검색 중심으로 쓰는 `search listings room`·`store`·`stay` 와 `search listings apt` 의 역·학교 이름은 그 곳에 좌표가 없으면 다른 후보로 넘어가지 않고 `UPSTREAM_ERROR` 다. `hint` 대로 같은 곳의 다른 이름(동·역 이름)으로 찾는다 (#376)
- 직방에서 같은 이름의 역·학교(양평역)를 첫 곳으로 찾고 `notes` 로 알리던 것을 없애고 `REGION_AMBIGUOUS` 로 후보를 알림. `hint` 대로 `영등포구 양평역`·`창천동 신촌역` 처럼 구·동 이름을 앞에 붙이면 그 후보로 찾는다 (#271)
- 직방 상가(`search listings store`·`listing store-…`)에서 업종이 사무실이고 직방이 권리금을 주지 않은 매물의 `key_money_manwon` 이 `null`(모름) 대신 키가 없음(해당 없음)이 됨. 직방 웹 상세도 사무실이면 권리금 줄을 숨긴다. 이 키를 바로 읽던 쪽은 키가 없을 때를 처리한다. 사무실이 아니거나 직방이 값을 준 매물은 그대로다 (`0` 은 무권리, 사무실이 아닌 매물의 값 없음은 `null`). 권리금 조건(`--key-money-*`)을 걸면 이런 사무실은 빠지고, 확인한 후보에서 뺀 건수를 `[제외]` 로 알린다 (#297)
- 직방 단기임대 `listing stay-…` 의 `refund_policy` 값 `보통` 을 직방 웹 위약금 정보의 이름 `표준` 으로, `parking` 값 `LIMITED` 를 웹 표기 `제한적 가능` 으로 바꿈 (주차 요금을 알리면 `가능` 처럼 `제한적 가능 (유료)` 로 붙는다). `보통`·`LIMITED` 로 비교하던 읽는 쪽은 새 값으로 고친다 (#299)
- 라이브러리로 쓸 때: `jibsa.providers.zigbang` 의 `search_apt_listings_near`·`ZigbangAptNearSearchResult`·`attach_stay_period_costs` 를 뺌. `search_listings` 의 `offset` 은 이어 받기 표 `start`(`{'offsets': {종류: 자리}}`)로, `search_apt_listings` 는 `extra_regions` 없이 지역 하나만 받고, `resolve_apt_region` 은 (지역, 안내) 두 값을 돌려준다. `search_store_listings` 는 `boundary` 대신 동 목록 `dongs` 를 받고, `get_stay_listing` 에는 `pet` 이 없다 (#272, #273, #275, #277)
- 네이버 `search listings` 의 가까운순 정렬을 없앰. 역·주소·단지·좌표 검색의 기본 순서가 가까운순에서 동 검색과 같은 랭킹순(네이버 지도 범위 목록 그대로, `distance_km` 순이 아니다)으로 바뀌고, `--sort 가까운순` 은 `INVALID_ARGUMENT` 다. 가까운순은 여러 지도 칸의 매물을 모아 거리로 다시 세운 목록이라 네이버 웹에 없었다. 반경 안 매물이 모자랄 때 반경 밖 매물을 덧붙이던 것도 없어져 반경 밖은 빼고 `[제외]` 로 알린다. 가까운 매물은 `--radius` 를 줄이거나 결과의 `distance_km` 로 고르고, 업데이트 전에 받은 `next` 는 버리고 처음부터 다시 찾는다
- 네이버 위치를 받는 명령(`search listings`·`search complexes`·`search redevelopment`·`trend`)에 `성수동`·`성수`·`부민` 처럼 `○가` 로 나뉜 동의 앞 이름을 주면 1가·2가를 합치거나 1가만 찾지 않고 `REGION_AMBIGUOUS` 로 `○가` 동을 다른 시·구의 것까지 모두 후보(전체 주소)로 줌 (`충정로` → 중구 충정로1가·서대문구 충정로2가·3가. 예전에는 충정로1가만 찾았다). 시·구를 붙이면(`서대문구 충정로`) 그 시·구의 동만 센다. 검색창 동 후보에 다음 쪽이 남아 다른 시·구의 `○가` 동을 다 보지 못했으면 한 곳만 모여도 고르지 않는다 (`candidate_count` 는 `null`). `--radius` 를 줘도 같고, 네이버 요청이 최대 2회 더 든다. 네이버 웹 검색창처럼 동 하나만 찾는다. 후보 하나(`성수동1가`)로 다시 부른다. 합친 이름(`"성수동1가·성수동2가"`)의 `region`·`boundary` 와 `--limit` 을 동마다 나눴다는 `notes`, 1가만 찾았다는 `notes` 는 없어졌다
- 네이버 단지 이름을 받는 명령(`complex`·`search listings --complex`·`market-price`·`school --complex`)과 위치로 준 단지 이름이 이름이 같은 첫 단지(없으면 첫 후보)를 골라 `[모호]` 로 알리던 것을, 네이버 검색창 단지 후보 전체가 첫 쪽 10건 안일 때(네이버가 다음 쪽이 있다고 하지 않고 전체 수도 10건 안일 때)만 그 안에서 이름이 정확히 같은 단지가 하나이거나 후보가 하나뿐이면 그 단지로 찾고 그 밖에는 고르지 않고 `REGION_AMBIGUOUS` 로 후보(`"이름 (주소, 단지 번호 N)"`)를 주게 바꿈. 네이버 웹 검색창은 후보를 10건씩 '더보기' 로 보여 줘 jibsa 는 다음 쪽을 부르지 않으므로, `한양`(852건)처럼 후보가 10건을 넘는 흔한 이름은 정확히 같은 이름이 하나여도 고르지 않는다. `래미안대치팰리스`·`잠실엘스`·`반포자이` 같은 구체적인 이름은 그대로 찾아진다. 쓰는 쪽은 후보의 단지 번호로 다시 부른다. 위치로 준 단지 이름의 `hint` 는 `search listings` 에서만 `--complex <번호>` 를 권하고, 모든 명령에서 단지 둘레는 `jibsa naver complex <후보의 단지 번호>` 의 `address`(번지 주소)로 다시 찾으라고 알린다 (후보의 동 이름으로 찾으면 동 전체다). 위치로 준 단지 이름이 네이버가 좌표를 주지 않는 단지로 정해지면 `지역을 찾지 못했습니다` 대신 그 단지로 찾았지만 좌표가 없다는 `REGION_NOT_FOUND` 이고, `hint` 가 단지 번호와 `complex <단지 번호>` 의 번지 주소·`--lat/--lng` 로 찾는 법을 알린다
- 네이버 위치를 받는 명령에 이름이 맞는 역·동이 없는 검색어를 주면 검색창 첫 후보를 말없이 쓰지 않음. 후보가 여럿이면 `REGION_AMBIGUOUS` 로 후보(역은 `"서울대입구역(2호선)"` 꼴, 동은 전체 주소)를 주고 (`서울대` → 서울대입구역·서울대벤처타운역, `인천공항` → 인천공항1터미널역·2터미널역), 하나뿐이면 그곳으로 찾고 `[참고]` 로 알린다. 후보를 셀 때 네이버가 좌표를 주지 않는 후보도 세고, 정한 동·역에 좌표가 없으면 다른 후보로 바꾸지 않고 `REGION_NOT_FOUND` 다. 이름이 맞는 동이 검색창 첫 쪽에 하나뿐이어도 다음 쪽이 남아 하나뿐인지 확인할 수 없으면 고르지 않고 `REGION_AMBIGUOUS` 다 (`신흥` 처럼 끝말 없는 이름. 이름 전체 주소 검색이 한 곳만 줘도 그곳이 찾은 동과 같은 곳일 때만 고른다). `수정구 신흥` 처럼 시·구를 붙인 검색어도 끝 단어로 이름을 맞춰 `[참고]` 없이 신흥동을 찾는다. 이름이 맞는 곳이 끝말만 다르면(신평동·신평면) 하나를 고르지 않고 둘 다 후보로 준다. 다음 쪽이 남았는데 네이버가 전체 수를 주지 않으면 `candidate_count` 는 `null` 이고 `message` 는 `N곳 이상` 이다 (단지 이름도 같다). 공백뿐인 지역 이름은 요청 없이 `INVALID_ARGUMENT` 고, 지역 이름의 앞뒤 공백은 뗀다 (`'파크리오 '` 도 파크리오로 찾는다). 쓰는 쪽은 후보의 역 이름 그대로(`서울대입구역`) 다시 부른다
- 네이버 위치를 받는 명령에 이름이 같은 역이 여러 곳인 역 이름(`시청역` → 서울·대전·부산 시청역)을 주면 첫 역으로 찾고 다른 역을 `[모호]` 로 알리던 것을, 고르지 않고 `REGION_AMBIGUOUS` 로 후보를 좌표와 함께(`"시청역(1호선) --lat 36.351677 --lng 127.386736"`, 좌표가 없으면 `(좌표 없음)`) 줌. 좌표 없는 같은 역도 후보로 세고, 같은 이름 역이 검색창 첫 쪽 끝까지 이어지면 다음 쪽을 최대 2회 더 받아 센다 (그래도 남으면 `candidate_count` 는 `null`). 역 이름·노선이 같은 역이 있어 쓰는 쪽은 고를 역의 `--lat/--lng` 로 다시 부른다
- 네이버 `listing` 의 `options` 글자 넷을 네이버 화면 글자로 바꿈: `인덕션` → `인덕션레인지`, `벽걸이 에어컨` → `벽걸이에어컨`, `스탠드 에어컨` → `스탠드에어컨`, `천장형 에어컨` → `천장에어컨`. jibsa 시설 표는 2026-11-17 네이버 웹 표와 같고, 그 뒤 네이버가 더한 시설 코드는 `알 수 없는 시설 (코드)` 로 알린다. `options` 를 글자로 비교하던 쪽은 새 글자로 바꾼다 (#306)
- 네이버 `listing` 이 jibsa 표에 없는 새 코드를 받으면 코드 글자를 그대로 내지 않고 못 읽었다는 글자로 냄: `알 수 없는 값 (HT009)`(방향·난방·난방 연료·현관 구조·건물 세부 유형. 방향 기준이 있으면 `알 수 없는 값 (XY, 거실 기준)`), `알 수 없는 시설 (XYZ01)`(`options`), `알 수 없는 항목 (XX)`(`manage_cost_includes`). 네이버가 값을 주지 않은 `null` 과 다르다. 이 값은 뜻으로 옮기지 말고 jibsa 가 읽지 못한 값으로 다룬다. 대개 네이버가 새 코드를 더했는데 jibsa 표가 아직 모르는 경우라 `url` 의 네이버 화면에서 뜻을 볼 수 있다 (화면이 그 코드를 그리는지는 보장하지 않는다). 예전에 코드 글자(`PRIVATE_SECURITY` 등)를 받던 쪽은 `알 수 없는 ` 으로 시작하는 값을 못 읽은 값으로 다룬다 (#306)
- 네이버 `search listings`·`search complexes`·`search redevelopment` 에 구·군 이름(`성동구`, `성남시 분당구`)이나 구 없는 시 이름(`구리시`)을 주고 `--radius` 를 주지 않으면 중심 반경 1km 대신 그 구·군·시 경계 전체를 찾음. 결과에 `radius_km` 대신 `boundary`(찾은 이름)가 오고 `total` 은 그 전체 수다. 하나는 매물이 많아 `has_more`·`next` 로 나눠 받는다. 구·군·시 경계 재개발 목록의 `legal_division` 은 모두 그 이름이다. 반경으로 찾으려면 `--radius` 를 준다 (구·군·시 이름에 `--radius` 를 주면 `notes` 가 '넓은 지역이라' 대신 `--radius` 를 빼면 경계 전체를 찾는다고 알린다). 구가 있는 시(`성남시`)는 시 전체로 찾을 수 없어 그대로 중심 반경이고 `notes` 가 시 이름을 붙인 구 이름(`성남시 분당구`·`성남시 수정구`·`성남시 중원구`)으로 찾으라고 알린다 (시 이름일 때만 요청 1회 더. 구가 있는지 확인하지 못하면 명령이 실패하지 않고 중심 반경으로 찾으며 `[실패]` 로 알린다). 시·도 이름은 그대로 중심 반경이다 (#322)
- 네이버 `trend` 에 구가 있는 시 이름(`성남시`)을 주면 추이를 모두 0 으로 내던 것을 `REGION_AMBIGUOUS` 로 바꿈. 네이버가 시 코드에는 매물 수·거래 수를 모두 0 으로 줘서(2026-11-18 실측) 0 을 내지 않고 `candidates` 로 구 이름(`성남시 분당구` 등)을 알린다. 구 이름으로 다시 부른다. 시 이름일 때만 구가 있는지 묻는 요청이 1회 더 들고, 구가 있는지 확인하지 못하면 그대로 추이를 내며 `[실패]` 로 알린다 (구 이름을 볼 `jibsa naver regions <시>` 도 알린다) (#323)
- 네이버 `complex --pyeong` 의 `real_price_summary` 가 매매·전세 각각 3년 안 거래가 없으면 `null` 대신 5년 안 거래로 요약하고, 그 유형의 요약에만 `since`(5년 전 날짜) 키가 붙음 (네이버 웹 실거래 요약도 3년이 비면 5년으로 다시 받는다). 3년으로 받은 유형은 키가 없다. 3년 요약 조회가 실패한 유형은 5년으로 바꾸지 않고 `null`(모름)이다. 윗단 `since` 는 그대로 3년 전 날짜라, `sale`·`jeonse` 를 읽는 쪽은 그 안에 `since` 키가 있으면 5년 요약으로 읽고, `null` 을 '3년 안 거래 없음' 으로 읽던 쪽은 이제 `null` 이 '5년 안에도 없음 또는 모름' 이라는 것에 맞춘다 (#316)
- 직방 `search listings store` 에 `--business` 를 주면 직방 웹처럼 업종 매물 뒤에 '이 지역 비어있는 상가' 묶음(업종과 상관없는 범위 안 공실)을 이어 줌. 예전에는 업종 조건을 지키도록 공실을 빼고 몇 건인지만 `notes` 로 알렸다. 결과 줄이 늘고 `total`·`--limit`·가격 조건을 확인하는 후보 수에 공실이 들어가며, 줄마다 `vacant_section`(공실 묶음에서 온 줄이면 `true`, 업종 매물이면 `false`)이 붙는다 (공실 묶음이 해당 없으면 키가 없고, `--fields` 로 골라도 늘 나온다). 업종 매물만 읽으려면 `vacant_section` 이 `false` 인 줄만 읽고, 공실 묶음이 있으면 `notes` 의 `[참고]` 가 `total` 을 업종 매물 수와 공실 수로 나눠 알린다. 공실 줄은 업종 조건으로 줄지 않아 `[일부]` 는 업종이 아니라 거래 유형·가격 조건(·반경 또는 지역)을 좁히라고 권한다. `--business` 도움말과 `search listings store --help` 도 공실 줄이 이어 섞이고 `total` 에 든다고 알린다. 공실 건수를 알리던 `notes` 는 없어졌다 (#377)
- 매물의 `property_type` 이 `null` 일 수 있음 (공통 `Listing`). 지금은 당근이 유형을 주지 않는 매물이 예전의 `"UNKNOWN"` 대신 `null`(모름)이다. 읽는 쪽은 `property_type` 이 늘 글자라고 보지 말고 `null` 을 처리한다. 유형을 모르는 당근 매물은 권리금 칸(`key_money_manwon`·`key_money_negotiable`)을 지우지 않고 `null`(모름)로 둔다 (키가 없는 것은 상가가 아닌 것으로 알고 권리금도 없을 때다) (#393)
- 당근 `region-reviews` 의 `has_reviews` 가 `null`(모름)일 수 있음. 당근이 후기 수를 주지 않고 후기 미리보기·후기 많은 단지·건물·동 목록도 비어 있으면, 예전처럼 `false` 와 '이 지역에는 당근 동네 후기가 아직 없습니다' 를 내지 않고 `null` 과 `[실패] 당근이 후기 수를 주지 않아 이 지역에 후기가 있는지 모릅니다. API 가 바뀌었을 수 있어 jibsa 업데이트가 필요할 수 있습니다` 를 낸다. 읽는 쪽은 `has_reviews` 가 늘 참·거짓이라고 보지 말고 `null` 을 처리한다 (#393)
- 값 하나만 받는 옵션을 같은 명령에서 두 번 주면(`daangn real-price 10697092 --trade 전세 --trade 월세`) 요청 전에 `INVALID_ARGUMENT`(`한 번만 받는 옵션이 두 번 왔습니다: --trade`, exit 2). 네 소스 공통이다. 예전에는 에러 없이 마지막 값만 써 앞 값이 조용히 버려졌다. 여러 값을 받는 옵션(`-t` 처럼 도움말에 '반복' 이 적힌 것)과 켜고 끄는 옵션(`--pretty`/`--compact`)은 그대로다. 붙여 쓴 짧은 옵션(`-t아파트 -t오피스텔`, `--type 아파트 -t오피스텔`)도 같은 옵션으로 세어 막는다. 당근 `search listings`·`search commute` 의 `--deal`·`--approval`, `search complexes` 의 `--approval`, `good-neighborhoods` 의 `--lifestyle` 도 값 하나만 받는 옵션이라 되풀이하면 이 문구로 막히고, 쉼표로 이어 둘 이상 주면 그 옵션의 `INVALID_ARGUMENT`(`사용승인일과 거래 방식은 하나만 받습니다` 등)다. 한 값만 준다. 여러 값을 받는 옵션 중 도움말에 '반복하거나 쉼표로 구분' 이 빠져 있던 것에도 적었다: 당근 `search listings`·`search commute` 의 `--trade`·`--structure`, 네이버 `search listings` 의 `--facility`·`--one-room-shape`·`--parking`·`--entrance`, 다방 `region-ranking` 의 `--trade`·`--type` (#393)
- 당근에서 값을 받지 못한 칸이 빈 값 대신 `null`(모름)로 나가는 곳이 늘었다. `school` 의 `complexes`·`total_complexes`(당근이 배정 단지를 주지 않을 때. 배정 단지가 정말 없으면 `[]`·0 그대로), `price-trend` 의 `points`·`total_transactions`(당근이 시세 그래프나 그 점 목록을 주지 않을 때. 그래프가 왔는데 거래 달이 없으면 `[]`·0 그대로), `region-reviews` 의 `top_complexes`·`top_buildings`·(구는) `dongs`(후기 페이지가 404 일 때), `real-price` 의 `presale`(당근이 소유 구분을 주지 않을 때. 일반 거래는 전과 같이 키가 없다), 단지·건물 `real-price` 의 `transactions`·`has_more`(당근이 거래 목록을 주지 않을 때. 목록이 왔는데 거래가 0건이면 `[]` 그대로), `search complexes`·`school` 단지 카드의 `has_reviews`(당근이 후기 요약을 주지 않고 후기 연결이나 그 목록을 `null` 로 줄 때)·`recent_trades`(당근이 실거래 연결이나 그 목록을 `null` 로 줄 때. 거래가 없으면 `[]`)·`name`(당근이 단지 이름을 주지 않을 때. 단지 ID 가 없는 단지는 `[제외]` 로 빼고 알린다), `region-reviews` 후기 단지의 `name`(당근이 주지 않을 때. 단지 ID 가 없는 후기 단지는 `[제외]` 로 빼고 알린다), `search commute` 역별 `listings`(당근이 그 역의 매물 목록을 주지 않을 때, 그 역만 `[실패]` 로 알리고 다른 역은 그대로). 읽는 쪽은 `null` 을 없음이 아니라 모름으로 읽는다. 단지·건물 `real-price`·`price-trend`·`school` 의 `null` 안내는 `[실패]` 로 나가고 `API 가 바뀌었을 수 있어 jibsa 업데이트가 필요할 수 있습니다` 가 붙는다 (`search commute`·`good-neighborhoods` 의 같은 안내와 같다) (#393)
- 당근의 코드 라벨 칸이 당근이 비워 준 값(빈 글자·`-`)을 `null` 로, 표에 없는 코드를 원래 코드 그대로 냄: 단지 유형(`property_type`·`type`·`complex_type`), `school` 의 `school_type`·`coed`, 어린이집 `type`, 실거래 `deal_type`·`contract_type`, 매물 `property_type`·`direction`. 매물 `floor` 는 저·중·고층 코드가 빈 값·`-` 면 숫자 층을 쓰고, 숫자 층도 빈 값·`-` 면 `null` 이다 (`building_floor` 도 빈 값·`-` 면 `null`). 단지·건물 `real-price` 와 `region-real-price` 거래의 `floor` 도 빈 값·`-` 면 `null` 이다. 예전에는 빈 글자·`-` 가 그대로 나갔고, 어린이집 구분은 표에 없는 코드가 `null` 이었다 (#393)
- 당근 `nearby-complexes` 의 기타 유형 단지가 `REGION_NOT_FOUND` 대신 `INVALID_ARGUMENT`(`hint` 가 `search complexes '<시·구·동>'` 를 알림)이고, 동을 모르는 단지만 `REGION_NOT_FOUND` 다. 공백만 있는 `search locations` 검색어는 `INVALID_ARGUMENT` 대신 `REGION_NOT_FOUND` 다. 에러 코드로 갈래를 나누던 쪽은 새 코드를 처리한다 (#393)
- 당근 `good-neighborhoods` 가 추천 지역 목록이 비어 오면 `REGION_NOT_FOUND` 대신 `UPSTREAM_ERROR`(업데이트 필요 안내)다. 지역 목록이 빈 것은 이름 문제가 아니라 API 문제라서다. 쓰는 쪽은 `UPSTREAM_ERROR` 도 처리한다 (#393)
- 라이브러리로 쓸 때: `jibsa.providers.daangn.search_areas` 가 지역 목록 대신 `(지역 목록, 뒤에 더 있는지, 쓸 수 없어 뺀 지역 수(위치·ID·시·도 이름이 없거나 단계를 모름))` 튜플을 돌려줌. `areas, more, unusable = search_areas(client, '중구')` 로 받고 `more` 가 참이면 후보가 잘린 것이다 (#393)
- 라이브러리로 쓸 때: `jibsa.providers.daangn.find_station` 이 이름이 맞는 같은 이름 역의 첫 역(당근 웹이 고르는 역)에 위치 정보가 없으면, 그 역을 건너뛰고 위치가 있는 다음 역을 고르던 것과 모두 위치가 없으면 `None` 을 돌려주던 것 대신 `LocationMissingError`(`REGION_NOT_FOUND` 계열)를 던진다. `None` 만 역이 없는 경우로 처리하던 쪽은 이 에러(`JibsaError`)도 처리한다 (#393)
- 라이브러리로 쓸 때: `DaangnClient.run_request_map_reviews` 에 넘기는 `DaangnMapReviewsRequestParameterModel` 에 읽을 지역 ID `region_id` 가 필수가 됨 (후기 페이지 스토어에 다른 지역 목록이 섞여 이 ID 의 것만 읽는다). `name1`·`name2` 만 주던 쪽은 `region_id` 를 더한다 (#393)
- 당근 `compare` 의 배정 학교·주변 역 `distance_m`·`walk_minutes` 가 정수로 반올림하지 않고 당근 비교 화면처럼 값 그대로라 소수일 수 있음 (0 이면 0분). 읽는 쪽이 정수만 온다고 보았다면 소수도 받도록 고친다 (#393)
- 사이트 첫 화면이 서버 오류(5xx, 또는 요청 제한을 끈 429)와 `Retry-After` 를 주면 그 시간만큼 쉬고 다시 엶 (전에는 1초 뒤 다시 열었다). 60초보다 길면 다시 열지 않고 `UPSTREAM_ERROR`(429 는 `RATE_LIMITED`)로 멈추며, `retry_after_seconds` 와 `hint` 가 몇 초 뒤에 다시 부를지 알림. CLI 의 `code` 는 전과 같다. 라이브러리로 쓸 때 이 경우 transport 가 `EntryStatusError`(`httpx.HTTPStatusError`) 대신 `EntryPageError`(`JibsaError`)를 던지니, `HTTPStatusError` 로 첫 화면 5xx 를 잡던 쪽은 `JibsaError` 도 잡는다 (#419, #423)
- 사이트 첫 화면이 본문 없이 4xx·5xx 를 주면 연결 오류로 보고 브라우저를 새로 띄워 첫 화면을 세 번 연 뒤 `NETWORK_ERROR`("네트워크 상태를 확인")로 알리던 것을, 본문이 있을 때와 같게 판정함: 4xx 는 `UPSTREAM_ERROR`(401·403·451 은 `blocked: true`), 429 는 쿨다운(`RATE_LIMITED`), 5xx 는 `Retry-After` 만큼 쉬고 다시 연 뒤 `UPSTREAM_ERROR`. 이 경우를 `NETWORK_ERROR` 로 받아 다시 부르던 쪽은 `code`·`blocked` 대로 다른 소스를 쓰거나 쿨다운을 기다린다. 라이브러리로 쓸 때 transport 가 던지던 `EntryConnectError`(`httpx.ConnectError`)는 `EntryPageError`·`RateLimitedError`(`JibsaError`)나 `EntryStatusError`(`httpx.HTTPStatusError`)가 된다 (#426)

### 추가

- 당근 `region-reviews` 에 후기가 있는 건물(`top_buildings`: `building_id`·`name`·`road_address`·`jibun_address`·`review_count`·`url`, 후기 많은 순, `--top` 개까지)을 더하고, 구를 주면 구 안 동별 후기 수(`dongs`: `name`·`region_id`·`review_count`·`url`, 후기 많은 순, 자르지 않음, 동을 주면 키가 없음)도 줌. 구는 구 후기 페이지, 동은 동 후기 페이지 한 번(요청 수는 그대로)으로 받는다. `name` 은 없을 때가 많아 `null` 이고 건물 후기는 `url` 에서 본다. 구의 건물이 `--top` 최대(500)에서도 잘리면 '동의 건물은 `region-reviews '<시·구·동>'` 으로 보세요' 가 붙는다. 후기 페이지가 404 면 `top_buildings`·`dongs` 도 `null` 이다. 후기 단지 목록에 빈 항목이 섞여 오면 `[제외]` 로 알리고 상한(`[일부]`) 판정에 그 자리도 세며(이때 `--top` 으로 자른 `[일부]` 는 후기 있는 단지 수를 쓰지 않는다), 건물 ID 가 없어 뺀 후기 건물과 지역 ID 가 없어 뺀 동도 `[제외]` 로 수를 알린다 (#393)
- 당근 `search listings --address <도로명 주소>`·`search commute --address`: 당근 웹 검색창 주소 검색과 같이 도로명 주소 후보를 찾아 그 좌표의 지도 화면 범위 매물(줌 15, `--zoom` 으로 바꿈)·회사 위치로 쓴다. 찾은 주소는 `search listings` 결과에는 `address`(도로명·지번 주소, 그 자리의 단지·건물 이름, 좌표)로 붙고 `search commute` 에는 `[범위]` `notes` 로 알린다. 후보가 여럿이면 `REGION_AMBIGUOUS` 로 도로명 주소 후보를 준다. 후보가 첫 20곳보다 많으면 `20곳이 넘습니다` 로 알리고 전체 수를 모르므로 `candidate_count` 는 `null` 이다. 띄어 쓴 주소는 따옴표 없이 줘도 된다 (`--address 테헤란로 152`, `--station`·`--university` 도 같다) (#215)
- 당근 `search complexes --lat/--lng [--zoom]`: 당근 웹 지도 단지 탭의 '이 영역 단지' 처럼 좌표를 가운데에 둔 지도 화면 범위(기본 줌 15)의 단지 목록. 결과에 `zoom`·`width_km`·`height_km` 와 화면 가운데의 `region` 이 붙는다 (#215)
- 당근 `real-price --month YYYY-MM`: 당근 웹 시세 그래프에서 달을 누른 목록처럼 그 달 계약만 (단지만, `--years` 와 함께 쓰지 않는다). 결과에 `month` 가 붙는다 (#222)
- 당근 `region-real-price` 에 당근 웹 실거래 화면 머리의 `summary`(`data_date` 가장 최근 공개일, 그날의 `sale_count`·`new_high_count`)가 붙음 (요청 1회 더. 실패하면 `null` 과 `notes`). 매매 거래마다 당근 웹 카드처럼 신고가 배지 `is_new_high` 와 직전 최고가 `previous_high_manwon`·`previous_high_date`·`previous_high_change_percent`(웹의 '직전 최고가 대비 ±N%' 와 같은 비율을 소수 둘째 자리까지. 웹은 정수로 보여 준다)가 `--new-high` 없이도 온다 (#222)
- 당근 `region-real-price --new-high --previous-days`: 당근 웹 신고가 화면이 보여 주는 가장 최근 공개일 말고 이전 공개일의 신고가까지 받는다 (최근 몇 달 치). `--new-high` 없이 주면 `INVALID_ARGUMENT` 다 (#222)
- 당근 `price-trend` 에 그 평형의 최근 KB 매매 시세 `kb_sale`(`low_manwon`·`high_manwon`·`survey_date`)이 붙음 (당근 웹 시세 그래프의 KB 시세 띠) (#222)
- 당근 `search commute` 의 역 묶음(`stations[]`)에 타는 역에서 회사 역까지 출근 방향 구간 `route[]`(`from_station`·`to_station`·`line`, 역·노선은 당근 출퇴근 지도의 역 상세 경로와 같음)가 붙음. 경로를 모르거나 모양이 다르면 `null` (#222)
- 당근 `preschool` 에 당근 학부모 설문 응답 수 `survey_responses`(웹 '후기 N', 없으면 0)가 붙음 (#222)

- 당근 `search listings --university <대학>`: 당근 웹 대학 페이지의 대학 주변 매물 목록. 캠퍼스가 여럿이면 `REGION_AMBIGUOUS` 로 캠퍼스 이름(`연세대학교 신촌캠퍼스`)을 고르게 한다 (#215)
- 당근 `search listings --zoom`: 구 이름·좌표 검색의 웹 지도 줌 (8~18) (#215)
- 당근 `search locations` 가 웹 지도 검색창처럼 `stations[]`(지하철역)·`universities[]`(대학)·`schools[]`(초·중·고) 후보도 줌. 이름을 `--station`·`--university`·`school` 에 그대로 넘긴다. 칸의 검색이 실패하면 그 칸은 `null` 이고(단지 칸은 하나도 받지 못했을 때) `notes` 가 이유를 알린다 (#215)
- 당근 `school` 이 학교 코드(`B100000749`)도 받음. `search locations` 의 `schools[]` 에 `school_code` 가 붙는다 (#215)
- 당근 `real-price --pyeong <공급 평형>`: 아파트형 단지의 실거래를 당근 웹 평형 탭처럼 공급 평형(예: 32평)으로 거름. `complex` 의 `pyeongs[]` 에 `pyeong`(공급 평형 묶음)·`representative`(대표 평형)가 붙는다 (#222)
- 당근 `compare --area <㎡>`: 모든 단지를 그 전용면적과 가장 비슷한 평형으로 비교 (#222)
- 매물 `status` 필드 (`판매중`·`예약중`). 예약 상태를 주는 당근만 채운다. 당근 예약중 매물은 계약이 깨질 수 있어 당근 웹처럼 내보낸다 (예전에는 뺐다) (#222)
- 당근 연세를 `trade_type: 연세` 와 `deposit_manwon`·`yearly_rent_manwon`(만원, 1년치)으로 줌. 연세 매물에는 `rent_manwon` 키가 없고, 결과에 연세가 있으면 `notes` 가 그 값으로 읽는 법을 알린다. 예전에는 연세만 올린 매물을 목록에서 빼고 `listing` 은 `LISTING_UNAVAILABLE` 이었다 (#222)
- 당근 `search listings`·`search commute` 에 `--trade 연세` 와 연세 범위 `--yearly-rent-min`/`--yearly-rent-max`(만원), `listing` 에 `--trade 연세`. `--trade 연세` 에 `--rent-*` 를 주거나 연세 없는 `--trade` 에 `--yearly-rent-*` 를 주면 `INVALID_ARGUMENT` (#222)
- 다방 `listing` 에 다방 상세 화면의 값: 관리비 부과 방식 `manage_cost_charge_type`(`정액관리비`·`기타부과`·`확인불가`)과 실비로 따로 내는 항목 `manage_cost_excludes`, 오피스텔 계약면적 `contract_area_m2`, 세입자 낀 매매 `with_tenant` 와 기존 세입자의 `tenant_deposit_manwon`·`tenant_rent_manwon`, LH 전세임대 `lh_lease`, 임차권 등기명령 `leasehold_registration`, 미등기 건물 `unregistered_building`, 위반건축물 `non_compliant_building` (#235)
- 다방 `real-price` 거래마다 등기 표시 `registered` 와 새 거래 표시 `newly_added` (#235)
- 다방 `complex` 에 최근 거래 수 `recent_deal_count`, 단지 꼬리표 `tags`, 가까운 어린이집 `nurseries`·유치원 `kindergartens`(3곳씩, 설립 유형·거리·교사당 아동 수) (#235)
- 다방 `price-trend` 의 `months[]` 에 그 달 전세가율 `lease_rate_percent` 와 매매·전세 평균 차이 `gap_manwon` (#235)
- 다방 `sale` 에 가격 종류 `price_kind`(`분양가`, 공공임대·민간임대는 `임대가`), 최근 6개월 지역 평균 평당가 `region_average_price_per_pyeong_manwon`, 청약 결과 `subscription_result`(최저 당첨가점·최고 경쟁률·평형별 경쟁률과 당첨가점, 청약 전이면 `null`) (#235)
- 다방 `search locations` 가 종류마다 `--limit` 보다 많은 후보를 잘랐으면 `[일부]` 로 몇 곳 중 몇 곳인지 알림 (다방은 종류마다 50곳까지 준다) (#235)
- 다방 `search listings --complex <단지 ID> --sort`: 다방 웹 단지 매물 정렬 메뉴 그대로 `랭킹순`(기본)·`최신순`·`높은가격순`·`낮은가격순`·`면적넓은순`·`면적좁은순` 중 하나. 결과에 고른 정렬 `sort` 가 붙고, `[일부]` 안내도 `다방 목록 순` 대신 `다방 랭킹 순`·`다방 낮은 가격 순` 처럼 고른 정렬을 쓴다. 동·역·대학 매물 목록(`room`·`villa`·`officetel`·`apt`)에는 다방 웹처럼 정렬이 없다 (#240)
- 다방 `search listings apt --condition 세안고`: 세입자가 있는 채로 파는 매매 매물만 (다방 웹 아파트 '추가필터'). 검색할 거래 유형에 매매가 없으면 `INVALID_ARGUMENT` (#240)
- 다방 `search listings officetel`·`apt --parking-min <대>`: 단지 세대당 주차 대수 하한 (다방 웹 주차 필터 '세대당 1대 이상'·'2대 이상'). `--condition 주차`(주차 가능 여부)와 다른 조건이다 (#240)
- 다방 `region-ranking <동> --unit 단지`: 그 동 안 단지 순위 (다방 웹 단지 순위의 동 범위). 결과 `scope.kind` 가 `dong` 이다. 동 순위·동네정보 항목에 동 이름을 주면 `INVALID_ARGUMENT` (#240)
- 다방 `region-ranking --by 거래증감`·`매물증감` (동·단지): 줄마다 `count`(지금 수)·`prev_count`(앞 수)·`change_count`(줄면 음수)·`change_percent`, 결과에 견준 기준 `comparison`(`전월대비`·`최근 30일 전 대비`). 기본은 거래량처럼 아파트·오피스텔 합산·모든 거래 유형 (#240)
- 다방 `nearby --sale <분양 ID>`: 분양 단지 둘레의 지하철역·버스 노선·가까운 시설·학교 (`target` `분양`). 분양 ID 는 단지 ID 와 길이가 같아 옵션으로 받고, 이때는 위치 인자를 주지 않는다 (둘 다 주면 `INVALID_ARGUMENT`) (#240)
- 다방 `search sales <시·도>`·`search sales 전국`: 다방 웹 분양 지역 목록 그대로 (예전에는 `REGION_NOT_SUPPORTED`). 전국·시·도·시·군·구에 `--radius` 를 주면 `INVALID_ARGUMENT` (전국·시·도는 요청 없이) (#244)
- 다방 `sale-schedule --details`: 줄마다 다방 청약 일정에서 날짜를 누르면 나오는 표의 분양 단지 정보 `sale`(`state`·`building_type`·`supply_type`·`address`·`sale_household_count`·`household_count`·`price_kind`·`price_manwon`). 내보낼 줄이 든 날마다 요청 1회 더. 그 날 표에서 짝을 찾지 못한 줄은 `sale` 이 `null` (다방이 분양 ID·종류를 주지 않아 맞춰 보지 못한 줄도 `null` 이고 `[참고]` 가 따로 알리며 업데이트 안내는 붙이지 않는다), 표를 받지 않은 결과(`--details`·`--region` 없이)는 `sale` 키가 없다 (#244)
- 다방 `search schools <동> --level <초등학교|중학교|고등학교|유치원|어린이집>`: 동 안 학교·유치원·어린이집 목록 (다방 동네정보 '학군' 상세 목록과 같은 목록·순서·전체 수). `--establishment` 로 설립 구분, `--limit` 기본 30·최대 120. `school_code`·`level` 을 `school` 에 그대로 넘긴다 (#246)
- 다방 `school --level 유치원`·`어린이집`: 유치원·어린이집 공시 (설립 유형·운영 시간·통학버스·원아 구성·교사 급수별 수·교사 1명당 아동 수·제공 서비스, 유치원은 홈페이지와 통학 차량 수도. 유치원 원비는 다방 값이 공시와 맞지 않아 주지 않고 결과 `url` 의 공시 페이지에서 본다). 코드는 `complex` 의 `nurseries[].code`·`kindergartens[].code` 나 `search schools` 의 `school_code` 이고, 유치원 코드(UUID)처럼 `-` 가 든 코드도 받는다 (#246)
- 다방 `nearby-complexes <단지 ID> [--pyeong <space_seq>]`: 다방 단지 화면 평당가 칸의 기본 탭 'N평대 비교'. 그 평형대의 이 단지·동·구 매매·전세 평당가와 반경 1km 주변 단지의 평당가·세대수·연차·거리. 다방이 그 평형에 평형대 탭이나 주변 단지를 주지 않으면 그 목록이 `null` (#245)
- 다방 `complex` 에 다방 대출 계산기가 대출 비율을 50%로 묶는 지역인지 `overheated_district` (다방 단지 화면의 대출 계산 조건, 웹 문구 '투기지역 (대출 비율 50% 제한)'. 받지 못하거나 다방이 값을 비워 주면 `null` 과 `[실패]`) (#245)
- 다방 `neighborhood --ranks`: 학교·편의·교통·안전 주제의 종류마다 합계·구성과 전국·시도·구 순위 `ranks[]`. 종류마다 요청 1회 더 (넷 다면 17회) (#247)
- 다방 `hot-places <동>`: 다방 동네정보 '핫플레이스' 의 미쉐린·블루리본 식당 (이름·가이드·주소·꼬리표, 기준 달). `--type 전체|미쉐린|블루리본`, `--limit` 기본 30·최대 120 (#247)
- 다방 `nearby --with 반려동물,카셰어링`: 다방 '펫세권'(동물병원·미용실·카페·호텔, 단지만)·'Car세권'(쏘카존·그린존, 매물·단지만) 2km 안 가까운 순 3곳. 받지 못하는 대상에 주면 `INVALID_ARGUMENT` (#248)
- 직방 `catalog <catalog_id>`: 같은 호를 여러 중개사가 올린 아파트 매물 묶음(직방 웹 묶음 화면)의 매물 전부를 매물마다 가격·관리비·입주일 등 `listing` 상세와 같은 필드로 준다 (20건마다 요청 1회, 앞 120건까지). `search listings apt`·`search listings --complex <apt-…>` 매물에 그 묶음 ID `catalog_id` 가 붙는다. `is_price_range: true` 인 줄의 매물별 가격을 매물마다 `listing` 하지 않고(매물마다 요청 2회) 한 번에 본다. `--fields` 로 매물마다 낼 필드를 고른다. `total` 은 묶음의 매물 수이고 직방이 알려 주지 않으면 `null` 이다. 묶음에 매물이 없으면(첫 쪽이 404 이거나 빈 목록) `LISTING_UNAVAILABLE`(`reason: EMPTY_CATALOG`, 묶음 ID 는 `listing_id` 가 아니라 `catalog_id` 에). 묶음 ID 형식이 아니면 `INVALID_ARGUMENT` 이고 `hint` 가 결과의 `catalog_id` 를 그대로 주라고 알린다 (#262)
- 직방 `search listings apt`·`search listings --complex <apt-…>` 매물에 `listing_ids`: 같은 호를 올린 매물 중 `listing` 으로 상세를 볼 수 있는 ID 전부 (`id` 가 맨 앞) (#261)
- 직방 `real-price` 거래에 `pyeong_names`: 같은 전용면적의 평형이 여럿이라 직방이 평형 후보를 모두 준 거래의 후보 이름 전부 (후보가 하나면 키가 없고, 직방이 후보를 주지 않은 거래는 `null`, 평 이름을 주지 않은 후보 자리는 `null`) (#261)
- 직방 `search complexes <역·학교·동·구 이름>`: 직방 웹 아파트 지도의 '역 주변단지'(역 1.5km 안)·'학교 배정단지'·동 화면의 최근입주 목록처럼 아파트 단지를 웹 순서로 주고(가까운 순이 아니다), 이름 끝 글자로 역·학교·동·구를 가른다. 결과에 `place`·`place_type`·`place_address`가 있고, 단지마다 세대수 `households`·주소·웹 단지 카드 둘째 줄 `highlight`(`--order` 마다 뜻이 다르다)와 역·학교에서의 거리 `distance_m`(학교는 직방 거리 문구를 m 로 바꾼 값, 동·구는 키 없음)을 붙인다. `--order`(인기·최근입주·시세급변동·평당가, 동·구는 최근입주만)로 웹 탭을 고른다. 최근입주·시세급변동은 순서가 아니라 그 조건에 든 단지만 담은 목록이라 `total` 도 그 수이고 그 곳의 전체 단지 수가 아니다 (강남역 인기 112곳·최근입주 2곳·시세급변동 55곳, 가락동 최근입주 1곳). `notes` 가 이를 알리고 `[일부]` 도 `배정단지 4곳 중 앞 3곳` 처럼 어느 목록의 수인지 밝히며 (역은 '주변 단지', 동·구는 '단지', 최근입주·시세급변동이면 앞에 순서 이름), 역·학교 주변 단지 전체에서 가까운 곳은 `--order` 를 빼고(인기) `--limit` 을 늘려 받아 `distance_m` 으로 고른다. 리(양근리)는 상위 읍·면의 목록이라 순서 안내의 이름이 읍·면이고, 단지 `address` 가 읍·면까지라 리 안의 단지를 가를 수 없다고 `[범위]` 로 알린다. `--limit` 기본 20·최대 120, 이어 받기는 없다. 역 이름 검색 결과가 하나도 없으면 `REGION_NOT_FOUND`(`hint` 가 역 이름 전체와 학교·동·구 예시를 알린다), 결과는 있는데 그 이름의 역이 없거나 직방 웹이 배정단지를 보여 주지 않는 학교(학교 코드가 없거나 `NL_` 로 시작하는 학교), 시·도 이름, 동·구에 최근입주가 아닌 `--order` 는 `INVALID_ARGUMENT` 다. 행정동 이름은 `REGION_NOT_FOUND` 이고 `hint` 가 법정동 이름으로 찾으라고 알린다 (`search listings apt` 와 같다). 같은 이름 역·학교·동·구가 둘이면 좌표가 없는 쪽도 후보로 세어 `REGION_AMBIGUOUS` 로 묻고 (이 명령은 좌표를 쓰지 않아 좌표 없는 곳도 그대로 찾는다), 직방이 단지 수만 주고 단지 ID 목록을 주지 않으면 `UPSTREAM_ERROR` 다 (학교 정보에 학교 ID 가 없거나 0 이하여도 `UPSTREAM_ERROR`). `has_more` 는 직방이 `--limit` 만큼 줬고 더 있을 때만 `true` 이고, `--limit` 보다 적게 왔는데 단지 수가 더 크면 `false` 와 `[참고]` 로 알린다. 요청은 이름 찾기·단지 ID 각 1회, 역은 주변 단지 정보 1회, 학교는 학교 정보 1회(배정단지 이름·세대수·거리도 이 응답), 받는 단지 15곳마다 단지 카드 1회라 `--limit` 이 크면 늘어난다 (#276, #376, #389)
- 직방 단기임대 `listing stay-… --check-in … --check-out …` 에 그 기간을 예약할 수 있는지 `available`: 직방 웹 날짜 고르기 창이 막는 규칙(오늘 이후, 최소 계약 주 이상·84일 이하, 예약·막힌 날 없음) 그대로다. 직방이 일정을 주지 않으면 `null` 이다 (#275)
- 직방 아파트 매물(`search listings apt`·`search listings --complex <apt-…>`·`catalog`·`listing` 의 아파트·제휴 매물)에 `listing_kind`: 직방 웹 카드의 '신규분양' 배지와 상세 안내 문구에 해당하는 매물 종류 (`신규분양`·`집주인`·`중개사`, 처음 보는 종류는 직방 코드 그대로, 직방이 주지 않으면 `null`). `신규분양` 이면 가격은 분양가다. 목록에서는 `--fields` 로 골라도 늘 나온다. `coalition-` ID 줄에는 집주인 매물뿐 아니라 신규분양도 있고, 직방 웹 기본 화면처럼 `search listings apt` 지역 목록 앞쪽에 신규분양 매물이 섞여 온다. 원룸·빌라·오피스텔·상가·단기임대에는 키가 없다 (#296)
- 다방 `region-ranking -t 빌라`: 매물수·거래량·선호도의 동 순위를 다방 동네정보 '매물정보' 탭(주택/빌라 포함, 고른 유형 합산)으로 받는다. 결과에 `building_type` 이 붙는다. 모든 `region-ranking` 결과에 어느 탭 순위인지 `tab`(`시세정보`·`매물정보`·`학군` 등)이 붙는다 (#247)
- 네이버 `listing` 의 중개보수 상한 `agent_fee_manwon` 이 매매뿐 아니라 전세·월세·단기임대에도 나옴 (네이버 웹도 월세 매물에 '최대 28만원' 처럼 보여 준다). 취득세·재산세·종부세는 그대로 매매만이다. 상세가 직거래가 아닌 모든 거래 유형에서 네이버 요청을 1회 더 한다. 네이버가 금액 대신 '개별확인' 으로 보여 주는 매물은 `agent_fee_manwon` 이 `null` 이고 새 필드 `agent_fee_individual_check_required` 가 `true` 다 (금액을 보여 주면 `false`, 조회 실패나 직거래인지 모르면 `null`) (#304)
- 네이버 `listing` 에 단지가 아닌 매물의 건물 이름 `building_name`(예: `새롬빌`, 이름이 없으면 키 없음)과 건물 세부 유형 `building_type`(다세대·연립·빌라·다가구·일반원룸 등. 토지는 지목 `대`·`전` 등, 사무실·숙박 등은 그 구분, 단지 매물은 키 없음, 단지가 아닌데 네이버가 주지 않았으면 `null`) (#305)
- 네이버 `listing` 에 난방 방식 `heating`(개별난방·중앙난방·지역난방 등), 난방 연료 `heating_fuel`(도시가스·전기·LPG 등), 현관 구조 `entrance`(계단식·복도식·복합식). 네이버가 주지 않았거나 '미노출' 이면 `null`. 아파트·오피스텔·재건축·분양권은 매물 값이 없으면 네이버 웹처럼 단지 정보 값(현관 구조는 평형 정보 값)으로 채우고, 단지형 빌라의 난방은 단지 정보 값만 쓴다. 상세가 단지 유형·단지형 빌라에서 단지 정보 요청을 늘 하고(예전에는 건물 날짜가 없을 때만), 현관 구조가 빈 단지 유형 매물은 평형 요청 1회를 더 한다 (#305)
- 네이버 `search listings`(지역·`--complex`·`--redevelopment`)와 `listing` 의 매물에 네이버 화면의 확인 배지 `badges`: `"집주인"`(상가·사무실·토지 등 비주거 매물은 `"소유자"`), `"현장"`. 방식 배지·HUG 배지가 모두 없으면 `[]` 이고 네이버가 확인 정보를 주지 않으면 `null` 이다. `[]` 에는 전화·서류로 확인한 매물과 확인하지 않은 매물이 함께 들어 `[]` 만으로는 확인 여부를 알 수 없고, 이런 매물도 HUG 안심임대인이면 `["HUG 안심임대인"]` 이라 비어 있지 않다고 집주인·현장 확인 매물인 것은 아니다. `--owner-verified` 로 찾은 매물에는 보통 `"집주인"`(또는 `"소유자"`)이 붙는다 (#307)
- 네이버 `real-price` 의 갱신 계약(`renewal: true`) 전세·월세 거래에 종전 보증금 `previous_deposit_manwon` 과 (월세·단기임대 갱신만) 종전 월세 `previous_rent_manwon`. 갱신이 아니거나 매매면 키가 없고, 전세 갱신에는 종전 월세 키가 없다 (네이버 웹도 전세는 종전 보증금만 보여 준다). 빌라 단지 실거래도 갱신(계약갱신요구권을 쓴 거래)이면 같은 규칙으로 붙는다. 종전 보증금·월세가 둘 다 0 이거나 없으면 네이버 웹처럼 두 키를 내지 않는다 (#308)
- 네이버 `complex --pyeong` 의 `market_prices[]` 에 기관의 전세 시세 평균 `jeonse_average_manwon` (기관이 주지 않았으면 `null`) (#309)
- 네이버 `search listings`(지역·`--complex`·`--redevelopment`)와 `listing` 의 매물에 `confirmed_at`(네이버가 매물을 확인한 날, `YYYY-MM-DD`, 모르거나 읽지 못하면 `null`)과 `badges` 의 `"HUG 안심임대인"`(HUG 안심임대인 매물에 확인 방식 배지 뒤로 붙고, 확인 정보를 모르면 `badges` 는 `null` 그대로) (#318)
- 네이버 `complex` 요약과 `search complexes` 행에 월세·단기임대 호가 `monthly_asking`·`short_term_asking`(`{lowest, highest}` 각 `{deposit_manwon, rent_manwon}`, 그 거래 매물이 없거나 네이버가 네 값을 모두 0 으로 주면 `null`. 다른 값이 있는데 월세만 0 이면 그 `rent_manwon` 만 `null`, 보증금 0 은 그대로. 한 짝의 보증금·월세가 모두 0 이면 그 짝은 두 값 모두 `null`). 월세 최저·최고가 아니라 가격 낮은 순 첫 매물과 높은 순 첫 매물의 (보증금, 월세) 짝이라 `lowest` 의 월세가 `highest` 보다 클 수 있다 (헬리오시티 `5000/420 ~ 700000/240`) (#319)
- 네이버 `complex --pyeong` 의 `real_price_summary.sale`·`jeonse` 에 최근 3개월 평균 `average_3m_manwon`(3개월 안 거래가 없으면 `null`). 추가 요청이 최대 4회에서 최대 6회로 늘어난다. 5년으로 요약한 유형은 3개월 요청을 하지 않아 `average_3m_manwon` 이 `null` 이다 (#316)
- 네이버 `search complexes -t` 에 `재건축`·`분양권`·`오피스텔분양권`. 단지 행 모양은 아파트와 같다 (#317)
- 네이버 `real-price`·`market-price` 의 `--period` 에 `3개월` (선택지 3개월·1년·3년·5년) (#315)
- 네이버 `trend 전국`: 지역을 찾지 않고 네이버 홈의 전국(시·도 전체) 추이를 준다 (`legal_division` 은 `"전국"`) (#324)
- 직방 `real-price` 거래에 직방 웹 실거래 탭이 보여 주는 값: `dong`(동, 직방이 주지 않으면 `null`. 지금까지 본 전월세는 늘 `null`)·`registered`(등기까지 마무리된 거래, 매매만)·`new_high`·`new_low`(최근 3년 안 신고가·신저가, 매매·전세)·`price_per_pyeong_manwon`(직방이 계산한 공급면적 3.3㎡당 가격, 매매만)·`jeonse_ratio`(전세가율, 0~1 비율. 전세이고 `--pyeong` 을 준 조회에서만)·`offer_price_diff_manwon`(분양가 대비 차액, 분양권 거래만. 직방이 주지 않으면 `null`). 그 거래 유형에 없는 값은 키가 없다. `registered` 는 표시가 없으면 `false` 가 아니라 `null`(모름)이다. 직방은 2023년 1월 이후 계약만 등기 여부를 표시한다 (#334, #375)
- 직방 `real-price --trade 전체`: 매매와 전월세를 계약일 최신 순으로 한 목록에 주고 거래마다 `trade_type` 을 붙인다 (직방 웹 실거래 탭의 '전체'). 전월세가 많은 단지는 앞쪽이 전월세뿐일 수 있다 (#334)
- 직방 아파트 매물(`search listings apt`·`search listings --complex <apt-…>`·`catalog`·`listing`)에 `pyeong_id`·`pyeong_name`(평형 ID·이름, `pyeong_id` 는 `--pyeong` 에 그대로 넘긴다)이 붙고, 상세·`catalog` 매물에는 직방이 매물을 확인한 날짜 `confirmed_at`·직방 웹의 '실매물 확인' 배지 `actual_listing_checked`·위반 건축물 여부 `non_compliant_building` 도 붙음. 직방이 주지 않으면(제휴 매물의 위반 건축물 등) `null` 이다 (#336)
- 직방 `search listings apt --no-new-sale`: 직방 웹의 '신규 분양 포함' 을 끈 동·구 목록처럼 신규분양 매물을 빼고 `total` 도 그만큼 준다 (이어 받을 때도 같은 옵션을 준다). 단지 매물(`--complex`)에는 없다 (#337)
- 직방 단기임대 `listing stay-…` 상세에 `kitchen_count`·`living_room_count`(주방·거실 수), `parking_count`·`parking_method`(주차 대수·방식, 주차 불가면 키 없음), `pet_allowed`·`pet_cleaning_fee_manwon`(반려동물 동반 여부·추가 청소비. 동반 여부는 직방이 옵션 목록을 주지 않으면 `null`, 청소비는 직방 웹처럼 동반 불가여도 0 보다 크면 나오고 동반 불가이고 0 이면 키 없음), `check_in_time`·`check_out_time`·`check_in_method`·`check_out_method`(입·퇴실 시각·방식), `unavailable_periods`(예약할 수 없는 기간), `refund_rules`(위약금 표, 정책을 모르면 `null`)가 붙음. `refund_rules` 는 직방 웹에 고정된 표를 옮긴 것이라 임대인 설정에 따라 다를 수 있으니 계약 전 `url` 에서 확인한다 (#338)
- 직방 `search listings stay --floor` 에 `2-10층`·`11층이상` (#339)
- 직방 원룸·빌라·오피스텔 `listing` 상세에 직방 웹 매물 화면이 보여 주던 값: `confirmed_at`(직방이 매물을 확인한 날짜)·`actual_listing_checked`('실매물 확인' 꼬리표, 확인 실패도 `false`)·`non_compliant_building`(위반 건축물 여부)·`hug_lessor`(HUG 안심임대인), `nearby_facilities`(주변 생활 시설과 걸리는 분·거리 m)·`delivery_services`(배송 업체), `manage_cost_excludes`(관리비 미포함 항목. 관리비 없음이거나 정액 관리비의 항목별 내역을 알린 매물은 웹이 이 줄을 보여 주지 않아 `[]`)·`manage_cost_period`(부과 기준)·`manage_cost_method`(부과 방식), `building_trades`(같은 건물(필지)의 실거래 전부. 이 매물의 거래가 아니다). 직방이 주지 않으면 `null` 이고 거래·시설이 없으면 `[]` 다. 필지가 있으면 건물 실거래 요청 1회가 더 든다 (받지 못하면 그 값만 `null` 이고 `notes` 의 `[실패]` 가 알린다. 학군도 같다) (#378)
- 직방 원룸·빌라·오피스텔 목록 줄(`search listings room`·`search listings --complex officetel-…`)에 `hug_lessor`·`actual_listing_checked`: 직방 웹 목록 카드가 읽는 배지 목록(`itemSummaries[].badges`, 키가 없으면 `items[].badges`)에서 읽은 'HUG안심임대인'·'실매물 확인' 꼬리표다 (배지 목록을 받지 못하면 `null`). `--details` 줄은 이 키 둘이 붙어 `residence_type` 의 JSON 키 위치가 뒤로 밀린다 (#378)
- 직방 아파트 `listing`·`catalog` 매물에 `hug_lessor`(HUG 안심임대인)·`zzim_count`(찜 수, 0 도 그대로)와 `manage_cost_excludes`·`manage_cost_period`·`manage_cost_method`(관리비 미포함 항목·부과 기준·부과 방식) (#378)
- 직방 `catalog` 에 호의 직방시세·공시가격·분양가: `estimated_sale_price_manwon`·`estimated_jeonse_price_manwon`(직방이 실거래를 분석해 낸 추정값이라 호가도 실거래가도 아니다)와 평당 가격, `public_prices`(해마다 공시가격과 전년 대비 변동률, 가격 0 은 `price_manwon` 이 `null`), `presale_price_manwon`(호 분양가)·`presale_average_price_manwon`(같은 타입 평균)·`presale_type_price_manwon`(타입 분양가)·`presale_price_per_pyeong_manwon`(웹이 보여 주는 분양가의 평당가). 요청이 1회 늘고, 호 정보를 받지 못하면 이 값들은 `null` 이고 `[실패]` 로 알린다 (`catalog --help` 도 20건마다 요청 1회와 호 정보 요청 1회, 실패 시 `[실패]` 를 알린다) (#379)
- 직방 `complex apt-…` 에 직방 웹 단지 화면의 평형 정보와 단지 값: `pyeongs[]` 마다 공급·전용면적(㎡·평)·세대수·방·욕실·현관 구조·평균/여름/겨울 월 관리비·전매제한 해제일 `resale_available_from`·직방시세(매매·전세와 평당 가격), 단지의 직방시세 범위·평균 평당 가격(`estimated_*`, 실거래 평균이 아니다)·`rank`(구·동 순위)·`related_complexes`(함께 보면 좋은 단지)·`land_trade_permits`(최근 7일 토지거래허가). 시세·관리비 0 은 `null` 이다. 요청이 1회 늘어 4회이고, 평형 정보를 받지 못하면 그 값만 `null` 이고 `[실패]` 로 알린다 (#380)
- 직방 단기임대 `listing stay-…` 상세에 `review_count`·`review_rating`(후기 수와 직방 원값 평균 평점, 후기가 없으면 평점 키 없음)과 `host_other_listings`(같은 임대인의 다른 방 앞 10건)·`host_other_listing_count`(전체 수). 요청이 2회 늘어 4회이고 받지 못하면 그 값만 `null` 이며 `notes` 에 `[실패]` 안내가 붙는다 (직방이 임대인의 다른 방 목록을 주지 않아도 상세는 실패하지 않고 `host_other_listings` 가 `null` 이다). 임대인 ID 가 없거나 0 이하면 다른 방을 조회하지 않아 `host_other_listings`·`host_other_listing_count` 가 안내 없이 `null` 이다 (#381)
- 직방 `price-trend <apt-…>`: 단지의 월별 직방시세 평당가 추이 (직방 웹 단지 화면 직방시세 그래프). `--period`(최근1년·최근3년·전체기간, 기본 최근3년)와 `--compare`(웹 '단지 비교하기' 후보 `comparable_complexes` 안의 단지를 최대 3곳, 웹은 1곳)로 줄을 더한다. 줄은 직방이 단지 ID 순으로 주고 구를 끝에 붙여 첫 줄이 조회 단지가 아닐 수 있으니 `lines[].kind`(`단지`·`비교 단지`·`구`)로 가른다. `--pyeong <평형 ID>`(`--trade` 전체·매매·전월세)를 주면 그 평형의 월별 직방시세와 거래(최저·최고가·건수·전달 대비 변화)를 준다. 직방시세는 직방이 실거래를 분석한 추정값이지 실거래가가 아니다. 직방시세가 없는 단지(분양예정 등)는 조회 단지 줄 없이 구 줄만 오고(`kind` 는 `구`, 비교 단지가 있으면 비교 단지와 구) `notes` 가 알린다. 평형을 확인했는데 고른 탭에 기록이 없으면 `months` 가 `[]` 이고 `notes` 가 기록이 없다고 알린다 (#385)
- 직방 `region-info <동·구>`: 직방 웹 지역정보 화면의 단지·세대 수, 평형대별 직방시세 `estimated_prices`, 월별 거래량 `monthly_volumes`, 평당가 추이 `price_trend`(`--range` 로 평형대를 고른다), 구는 월별 인구·세대 `population`. 시·도 이름은 `INVALID_ARGUMENT` 다. 거래량·평당가 추이·인구·세대는 덤 조회라 실패하거나 직방이 목록을 주지 않으면 그 값만 `null` 이고 `[실패]` 로 알린다 (#386)
- 직방 `region-trades <동·구>`: 직방 웹 지역 화면 '실거래'처럼 동·구에 최근 등록된 실거래 (`--trade` 매매·전세·월세, `--period` 오늘·어제·7일·15일·30일, `--sort`, `--limit` 기본 20·최대 120). 등록일 기준이고 기본 기간이 오늘이라 비기 쉬우니 `--period 30일` 로 넓힌다. 직방이 낮 12시에 그날 실거래를 반영하므로 오늘 기간에는 `updated_today` 를 주고, 반영 전이면 `false` 와 `[참고]` 로 알린다. 직전 거래·직방시세·공시가격·분양가·전세가 대비 값이 줄마다 온다 (#387)
- 직방 `region-ranking <동·구>`: 직방 웹 지역 화면 '단지랭킹' (`--trade`, `--sort` 거래량·하락률·상승률·시세·평당가·인기·전세가율, `--period`, `--limit` 기본 10·최대 100). 직방 웹처럼 100위까지만 주고 정렬마다 줄의 칸이 다르다 (#388)
- 직방 `search complexes <학교 이름>` 결과 맨 끝에 `school`: 직방 웹 학교 화면의 학교 정보 (학생 수·같은 구 평균·입학생·학급당 학생 수, 학비·급식비는 만원, 중학교 고등학교 진학·고등학교 대학 진학 `advancement`). 학교 정보 조회를 먼저 불러 웹 학교 화면처럼 그 응답의 학교 번호로 배정단지를 찾는다 (검색 결과의 학교 번호는 직방이 번호를 다시 매기면 다른 학교를 가리킬 수 있다). 배정단지가 0곳이어도 학교 정보를 내고, 학교 정보 조회가 실패하면 에러다 (#389)
- 네이버 `school` 에 `--complexes`(`--sort 거리순|세대수순`, `--limit` 기본 20·최대 100): 그 학교에 배정되는 단지 `assigned_complexes`(`total`·`returned`·`has_more`·`complexes[]`)를 붙임. 단지마다 단지 번호·이름·유형·세대수·동 수·사용승인일·거래 유형별 매물 수·호가 범위·배정 동 `assigned_dongs`(전체 배정이면 `["전체 동"]`, 아니면 동 묶음마다 `"101동~105동"`, 전체 배정이 아니거나 전체 배정 여부를 주지 않았는데 네이버가 어느 동인지 주지 않으면 `null`)가 있다. 네이버가 총수를 주지 않으면 `total` 이, 다음 쪽 여부와 총수를 모두 주지 않고 받은 것이 `--limit` 안이면 `has_more` 가 `null`(모름)이다. 20곳마다 요청 1회가 더 든다. `--sort`·`--limit` 은 `--complexes` 없이 주면 `INVALID_ARGUMENT` 다 (#343)
- 네이버 `complex` 에 평형 묶음 `pyeong_groups[]`(`name`·`representative_pyeong`(대표 평형 번호)·`households`·`pyeong_numbers`)와 `real-price --group`(그 평형이 든 묶음의 거래를 함께 받음, 결과에 `pyeong_group`). 평형이 많은 단지에서 평수로 평형을 고를 수 있다. `pyeong_groups` 는 `--pyeong` 과 상관없이 요청 1회를 더 해 붙이고 빌라 단지는 키가 없다 (묶음이 없으면 `[]`, 조회 실패면 `null`). `--group` 은 묶음 안 모든 평형의 거래가 섞여 오고 거래마다 평형을 알 수 없으며 `--period` 와 함께 쓸 수 없다. 묶음이 없는 단지(없는 단지 번호이거나 단지형 빌라처럼 평형 묶음이 없는 단지. 네이버 응답으로 둘을 가를 수 없다)와 묶음에 없는 평형 번호는 `NOT_FOUND` 다 (#345)
- 네이버 `complex --pyeong`(하나만 줄 때)에 평당 호가 `price_per_pyeong`(`{sale, jeonse}` 각 `manwon_per_pyeong`·`as_of`·동·구·시 평균 `regions[]`, 만원/평). 공급 평수 기준 네이버 매물 호가의 주간 값이라 실거래 평당가가 아니다. 월세는 네이버가 주지 않아 키가 없고, 아파트·오피스텔·재건축·분양권·오피스텔분양권 단지만 있다(단지 유형을 모르면 `null`). 추가 요청이 최대 6회에서 최대 8회로 늘어난다 (#346)
- 네이버 `listing` 에 주변 개발 예정 `nearby_development`(`rail[]`: 근처에 생길 지하철역의 `station`·`line`·`opens`·`distance_m`·`walking_minutes`, `area[]`: 개발 지구의 `name`·`type`·`step`·`period`). 근처에 없으면 `rail`·`area` 가 `[]`, 조회에 실패하면 `null` 이다. 모든 매물 유형에 붙고 요청이 1회 더 든다 (#344)
- 네이버 `redevelopment` 와 `search listings --redevelopment` 가 구역 번호 외에 구역 이름(`성수전략정비구역제3지구`)도 받음. 이름이 정확히 같은 구역이 하나이거나 후보가 하나뿐일 때 정하고(이름이 다른 한 곳이면 `[참고]` 로 어느 구역인지 알림), 맞는 구역이 없으면 `NOT_FOUND`(단지 이름과 같다), 그 밖에는 `REGION_AMBIGUOUS` 로 후보의 구역 번호를 알린다. 같은 구역이 법정동마다 따로 등록돼 이름이 같은 후보가 여럿인 경우(한남제3재정비촉진구역)가 여기 든다. 이름으로 주면 요청이 1회 더 든다 (#347)
- 네이버 `real-price` 가 빌라 단지에서 웹 빌라 실거래 탭의 두 칸을 더 줌. `price_per_pyeong_trades[]`(`trade_date`·`manwon_per_pyeong`, 만원/평)는 이 평형의 최근 5년 평당 실거래가로 매매·전세만 있고(월세는 키 없음) `--period`·`--pages` 와 상관없다. 호가 평당가(`complex` 의 `price_per_pyeong`)가 아니라 신고된 거래의 평당가다. `nearby_transactions`(`range`: 찾은 범위의 남북·동서 m, `trades[]`: 계약일·`area_m2`·`built_year`·`floor`·금액·`renewal`·`distance_m`·`same_complex`)는 단지 둘레 범위 안 거래로 계약일 → 준공연도 → 전용면적 큰 순이고, 네이버가 10건까지만 주며 단지 이름은 주지 않는다. 새 옵션 `--around-km`(0.1~1.0)으로 범위를 정하고 빼면 웹 작은 지도 크기(서울에서 약 188×365m, 남쪽일수록 조금 넓다)다. 거래가 없으면 `[]`, 조회 실패나 단지 좌표를 모르면 `null` 이고 아파트 단지는 두 키가 없다. 아파트 단지에 `--around-km` 을 주면 `INVALID_ARGUMENT`, `--group` 과 함께 줘도 `INVALID_ARGUMENT` 다. 빌라 단지는 요청이 매매·전세 3회, 월세 2회 더 든다 (#357)

### 변경

- 분당 요청 상한(`RATE_LIMITED`, reason `budget`)의 `hint` 가 그 옵션이 없는 명령에도 `--limit, --radius` 를 권하던 것을 "조회 범위를 줄이거나 잠시 뒤 다시 시도하세요" 로 바꿈
- Chromium 을 띄우지 못했을 때(리눅스 밖)의 `hint` 가 `jibsa install-browser` 로 "다시 받아" 보라고 하던 것을 "설치와 실행을 확인" 으로 바꿈 (그 명령은 이미 받은 Chromium 을 다시 받지 않는다)
- `limits`·`install-browser` 의 `--pretty/--compact` 도움말을 다른 명령과 같게 하고, `--next` 도움말에 이어 받는 동안 바꿀 수 있는 옵션(`--limit`·`--details`·`--fields`)을 적음
- README 설정 절에 프록시 환경 변수(`HTTPS_PROXY`·`ALL_PROXY`·`NO_PROXY`)를 적음
- 당근 `region-reviews --top` 의 최대를 20 에서 500 으로 늘림. 단지와 건물에 함께 걸린다. 구(와 세종 동)의 단지는 당근 후기 페이지가 후기 많은 단지를 20곳까지만 주므로 20곳을 꽉 채워 주면 `--top` 과 상관없이(기본값 포함) `[일부]` 로 알리고(구는 동 이름으로 다시 보라고), `--top` 으로 자르면 '당근 구 후기 페이지가 준 단지 20곳 중 앞 N곳입니다' 로 알린다. 목록이 `--top` 보다 길면 '더 보려면 --top 을 늘리세요' 로 알린다 (#393)
- 네이버 `search listings`·`search complexes`·`search redevelopment` 가 `세종`·`세종시` 처럼 시·군·구가 하나뿐인 시·도 이름을 `--radius` 없이 주면 중심 반경 1km 대신 세종 전체(그 시·군·구 경계, `boundary`)로 찾음. 서울·경기도 같은 시·도는 그대로 중심 반경이다. 시·도 이름일 때만 시·도 아래 시·군·구를 확인하는 요청이 1회 더 들고, 확인하지 못하면 중심 반경으로 찾으며 `[실패]` 로 알린다 (#353)
- 네이버 덤 조회(`listing` 의 중개보수·세금·교통·주변 학교·주변 개발 예정·단지 정보·관리비 등, `complex` 의 재건축 정보·평형 묶음·배정 학교·평당 호가·평형 관리비·시세·실거래 요약, 빌라 `real-price` 의 평당 실거래가·주변 실거래, `trend` 의 매물 수·평당가·실거래 수, `school` 의 배정 동)가 실패하면 그 칸은 전처럼 `null`(모름)이고, 이제 `notes` 에 `[실패]` 안내가 붙어 끝에 모름이 된 칸 이름을 알림. 서버 오류(5xx)·연결 실패·시간 초과면 '잠시 뒤 다시 시도하세요', 네이버가 요청을 거절했거나 응답 형식이 바뀌었으면 'jibsa 업데이트가 필요할 수 있습니다' 가 붙고, 같은 안내는 한 번만 나온다. 요청 제한은 덤 조회도 전처럼 에러로 끝난다. `listing`·`trend`·`school`(상세)은 다른 안내가 없으면 `notes` 키가 없던 결과인데, 덤 조회가 실패하면 `notes` 가 생긴다. 읽는 쪽은 칸의 `null` 이 '네이버가 값을 주지 않음' 인지 '조회 실패' 인지 `[실패]` 안내로 가린다 (#356)
- 다방 `complex` 의 최근 실거래 요약·대출 계산 조건 덤 조회 실패 `[실패]` 안내를 네이버 덤 조회와 같은 순서(무슨 일 → 할 일 → 모름이 된 칸 안내)로 바꿈. 요청 제한은 제한 안내를 괄호에 넣지 않고 마침표로 이어 (`요청 제한에 걸려 최근 실거래 요약을 받지 못했습니다. <제한 안내>. recent_sale·recent_lease 는 모름(null)입니다. 실거래는 real-price 로 보세요`), 다방이 요청을 거절했거나 응답 형식이 바뀌었으면 'jibsa 업데이트가 필요할 수 있습니다' 가 모름이 된 칸 안내 앞에 온다 (예전에는 칸 안내 뒤). 서버 오류·연결 실패 안내는 그대로다. 안내 글자를 통째로 비교하던 쪽은 새 순서에 맞춘다 (#393)
- 라이브러리로 쓸 때: client 의 `timeout` 은 응답 헤더가 올 때까지(연결 포함)와 본문 조각 사이 간격의 제한이다 (httpx 의 읽기 제한처럼 조금씩 계속 오는 응답은 전체가 더 길어도 받는다). 예전에는 요청 하나의 연결부터 본문 끝까지 전체 시간이었다 (#217)
- 라이브러리로 쓸 때: 1MB 보다 큰 응답 본문을 브라우저에서 1MB 씩 나눠 받아 빨라진다. jibsa 소스 응답은 1MB 보다 작아 CLI 에서는 달라지지 않는다 (#217)
- 매물 검색의 `--next` 는 그 `next` 를 받은 jibsa 버전에서만 쓴다. 업데이트한 뒤 앞 버전의 `next` 를 주면 `INVALID_ARGUMENT` 이고 `hint` 가 처음부터 다시 찾으라고 알린다. 예전에는 업데이트로 없어진 옵션까지 '지역·조건이 다릅니다' 에 들어, 따를 수 없는 안내가 나왔다 (#221)
- `jibsa --version` 이 설치하지 않고 소스 폴더를 바로 실행했을 때는 `jibsa (설치 정보 없음)`, 설치 출처 파일(`direct_url.json`)이 깨졌을 때는 `jibsa 0.12.0 (설치 출처 모름)` 처럼 버전 줄을 보여 줌. 예전에는 에러 JSON 으로 끝났다 (#221)
- 당근 `search locations`·`search complexes` 에 위치를 주지 않았을 때의 사용법 오류가 그 명령이 받는 입력(`지역·역·대학·학교·단지 이름`, `동·구 이름`)을 알림. 예전에는 늘 `동 이름` 이라고 했다 (#215)
- 당근 단지 ID 를 받는 명령(`complex`·`real-price`·`price-trend`·`compare`·`nearby-complexes`·`search listings --complex`)에 단지·지역 이름처럼 숫자가 아닌 값을 주면 `is not a valid int range` 대신 `단지 ID 가 아닙니다` 로 알리고, `hint` 가 단지 ID 를 찾는 법(`search complexes`·`search locations`)을 알림 (#192)
- 당근 같은 이름의 역은 `notes` 에 나온 노선 붙인 이름(`--station '서울5호선 양평역'`)으로 고름 (#215)
- 당근 `search listings` 의 세대수·주차대수 조건을 당근 웹처럼 `-t` 없이도, 아파트·오피스텔을 넣은 여러 유형과도 받음. 예전에는 `-t 아파트` 하나일 때만 받았다 (#222)
- 당근 `listing` 과 `--details` 가 비활성 중개소의 매물을 당근 웹 상세처럼 `LISTING_UNAVAILABLE`(`reason: BIZ_PROFILE_INACTIVE`)로 막음. 목록 카드에는 중개소 상태가 없어 목록에는 웹처럼 나온다 (#222)
- 당근 `complex` 의 아파트형 단지 평형을 전용면적 묶음 대신 당근 웹처럼 공급 평 묶음으로 나누고, `schools` 의 중·고등학교를 도보 가까운 2곳 대신 웹 학군 카드처럼 이 단지 주민이 많이 다니는 순(같으면 도보 순)으로 고르며 주민 수를 붙임 (#222)
- 당근 웹 쿼리 해시가 거절되면 동 지도 페이지 20건에 조건을 직접 걸어 찾던 대체 경로를 없애 `UPSTREAM_ERROR` 로 끝냄. 당근 웹에 없는 동작이었다 (#215)
- 당근 `region-real-price --new-high` 가 당근 웹 신고가 화면처럼 가장 최근 공개일의 신고가만 줌. 그날 신고가가 없으면 빈 목록이고 `notes` 가 알린다. 예전처럼 이전 공개일 신고가까지 보려면 새 옵션 `--previous-days` 를 붙인다 (#222)
- 다방 `complex` 의 중·고등학교를 2곳에서 다방 화면처럼 가까운 3곳씩 줌 (#235)
- 다방 `complex` 의 요청이 2회에서 3회로 늘어남 (`overheated_district` 를 받는 대출 계산 조건) (#245)
- 다방 `sale-schedule --region` 이 일정 글 앞의 시·도가 아니라 그 날 분양 단지 표의 주소로 시·도를 가림. 일정이 있는 날마다 요청이 1회 늘고(7일이면 최대 8회) 줄에 `sale` 이 붙는다. 남긴 일정이 `--limit` 을 넘으면 그 뒤 날은 받지 않고, `[일부]` 의 전체 수를 '적어도 N건' 으로 알린다. 글이 시·도 없이 시작해 지역을 몰라 빠지던 일정(`'남춘천 센트레빌'`)도 주소로 가린다 (#244)
- 다방 `region-ranking`·`search sales` 의 시·도·시·군·구 범위를 다방 웹 지역 고르기와 같은 시·도·시·군·구 목록에서 찾음. `'서울 중구'` 처럼 시·도를 붙인 이름은 장소 검색 없이 찾고, `search sales '서울 홍대입구'` 처럼 '입구' 로 끝나는 역 이름은 범위 목록을 묻지 않고 바로 장소 검색으로 찾는다 (`region-ranking` 은 목록을 묻지 않고 바로 에러로 알린다). 찾는 범위와 결과는 같다 (#244)
- 다방 `price-trend` 가 `--pyeong` 없이 대표 평형으로 찾았다는 `[참고]` 에 다른 평형은 `complex` 결과의 `pyeongs` 에서 고르라는 말을 붙임 (`real-price`·`nearby-complexes` 와 같은 안내). `real-price`·`price-trend`·`nearby-complexes` 는 다방이 대표 평형을 주지 않아 다방 웹처럼 첫 평형으로 찾았으면 `[참고]` 가 다방 대표 평형이라 하지 않고 첫 평형을 골랐다고 알린다. `complex` 의 `primary_space_seq` 도 같은 첫 평형을 낸다 (다방이 준 0 을 그대로 내던 것) (#245)
- 하나만 받는 옵션이 앞뒤 공백을 다듬어 받고, 쉼표로 여러 값을 주면 `INVALID_ARGUMENT` 의 message 가 '허용되지 않는 값' 대신 `하나만 주세요: …` 로 바뀜 (같은 값만 반복했으면 그 값으로 받고, 틀린 조각이 있으면 그 조각으로 '허용되지 않는 값'). 바뀌는 옵션: 네이버 `search complexes`·`search redevelopment`·`search listings` 의 `--sort`, `search listings` 의 `--area-basis`·`--loan`, `trend` 의 `--trade`·`--period`, `real-price`·`market-price` 의 `--period`, 직방 `search listings store` 의 `--trade`, `search listings stay` 의 `--structure`, 다방 `school` 의 `--level`, `region-ranking` 의 `--by`, `jibsa guide` 의 `TOPIC` (#243)
- 다방 동만 받는 명령(`neighborhood`·`popular-listings`·`hot-places`·`search schools`)에 시·군·구 이름(`강남구`)을 주면 `REGION_NOT_SUPPORTED` 의 `hint` 가 '그 안의 동 이름(예: '강남구 역삼동')으로 다시 주세요' 로, 역만 받는 `station-prices` 는 '역 이름(예: '강남역')으로 주세요' 로 그 명령이 받는 이름만 권함. 역·대학 이름을 준 `INVALID_ARGUMENT` 는 명령마다 주어를 달리해 '동네정보는/인기 매물은/동 안 학교는/핫플레이스는 동 이름으로만 찾습니다: <이름>' 이라 하고, `hint` 는 역 둘레를 볼 수 있는 명령만 권한다 (`neighborhood` 는 `station-prices`·`search listings`, `popular-listings` 는 `search listings`. `hot-places`·`search schools` 는 역 둘레를 볼 명령이 없어 '이 명령은 역·대학 둘레를 찾지 않습니다') (#249)
- 다방 `region-ranking <동> -t 빌라` 가 동 범위를 막을 때의 `hint` 가 `--unit 단지` 를 권하지 않고 시·군·구 이름을 범위로 주라고만 알림 (빌라 순위는 동 순위만 있어 `--unit 단지` 를 따르면 다시 막혔다). `--limit` 도움말은 '부동산 50곳, 동네정보·`-t 빌라` 30곳마다 요청 1회' 다 (#247)
- 직방 아파트 목록(`search listings apt`·`search listings --complex <apt-…>`)의 `url` 이 매물 하나의 페이지 대신 직방 웹 카드를 누르면 가는 그 호의 묶음 화면(중개사별 매물 목록)이 됨. 직방이 호 ID 를 주지 않은 줄만 `id` 매물의 페이지다 (이때 `catalog_id` 는 `null`) (#261)
- 직방 단기임대(`search listings stay`·`listing stay-…`)의 `url` 이 단기임대 안내 페이지에서 그 매물의 직방 웹 페이지(`https://www.zigbang.com/stay/item/<번호>`)로 바뀌고, 웹 매물 페이지가 없어 앱에서 찾으라던 `notes` 가 없어짐 (#261)
- 직방 단기임대 즉시입주 할인 문구가 `즉시 7만원 할인` 대신 직방 웹 상세처럼 입주 시점 조건을 담음 (`오늘 입주 시 7만원 할인`·`오늘부터 1일 이내 입주 시 7만원 할인`). 할인 금액은 반올림 없이 원 단위까지 만원으로 쓴다 (2,500원 → `0.25만원 할인`). 직방 웹이 보여 주지 않는 금액 없는 즉시입주 할인(`즉시 5% 할인`)은 내지 않는다. 장기계약 할인도 직방 웹 상세처럼 주 수·할인율·주당 임대료가 모두 있을 때만 `4주 이상 10% 할인` 으로 내고, 할인율 없이 금액만 있는 장기계약 할인·주 수 없는 할인·두 종류 밖의 할인은 내지 않는다. 직방 웹처럼 할인의 켜짐 여부(`isActive`)로는 거르지 않는다 (#261)
- 직방 제휴 아파트 매물 상세(`listing coalition-…`)에 직방이 주는 방향 기준 `direction_criterion` 이 붙고, `total_parking_count`·`household_count` 가 키 없음(해당 없음) 대신 `null`(모름)로 나옴 (#261)
- 직방 아파트 목록(`search listings apt`·`search listings --complex <apt-…>`)의 `is_price_range`·`catalog_id`·`listing_ids`·`listing_count` 가 `--fields` 로 고르지 않아도 늘 나옴 (네이버 묶음 필드와 같다). 빠지면 가격이 묶음 최저가인지 모르고 매물별 가격을 볼 ID 도 없었다. `--fields` 도움말에도 늘 나오는 필드로 적었다 (#261)
- 직방 `real-price` 의 `pyeong_name` 이 평형 후보가 여럿인 거래에서 첫 후보 이름 대신 직방 웹처럼 `32A 외 4` 로 나옴. 후보 전부는 새 `pyeong_names` 에 있다 (#261)
- 직방 금액을 반올림 없이 원 단위까지 냄. 단기임대(`search listings stay`·`listing stay-…`)의 주당 임대료·관리비·보증금·청소비, 원룸·빌라·오피스텔·아파트의 관리비가 0.1만원(1,000원) 단위로 반올림하지 않고 원 단위까지 나온다 (375,700원 → `37.57`. 직방 웹 목록 카드는 0.1만원 아래를 버려 `37.5만원` 으로 보여 준다). 원룸·빌라·오피스텔 `listing` 관리비도 직방이 0.1만원 아래를 버린 값(`37.5`) 대신 원 단위 금액(`37.57`, 웹 상세와 같은 금액)을 낸다. (#259)
- 네이버 금액을 반올림 없이 원 단위까지 냄. 매물 가격·보증금·월세·관리비·융자금·중개보수·세금, 단지의 호가·시세·실거래·평형 관리비 평균, `real-price`·`market-price`·`trend` 평당가가 0.1만원(1,000원) 단위로 반올림하지 않고 원 단위까지 나온다 (평형 관리비 평균 138,435원 → `13.8` 대신 `13.8435`, 재산세 5,602,410원 → `560.2` 대신 `560.241`). `search listings` 가격순 안내 문구의 금액도 원 단위까지 쓴다. (#257)
- 다방·당근 금액을 반올림 없이 원 단위까지 냄. 다방 매물·단지 평형 관리비, 당근 중개보수·KB 시세·시세 평균·시세 변동액(`change_manwon`)·단지 비교 관리비가 0.1만원(1,000원) 단위로 반올림하지 않고 원 단위까지 나온다 (관리비 85,800원 → `8.6` 대신 `8.58`). 당근 `compare` 의 평균 호가(`asking.*.average_manwon`)도 웹처럼 만원 정수로 반올림하지 않고 같은 매물들의 평균을 원 단위까지 낸다 (예: `10500` 대신 `10500.3333`), 그 값이 정수가 아니게 되므로 정수로 읽던 쪽은 고친다 (#257)
- 직방 `listing` 에 매물 ID 형식이 아닌 값을 주면 `INVALID_ARGUMENT` 의 message 앞 `Invalid value for ITEM_ID:` 가 없어지고, `hint` 가 `--help` 를 보라는 말 대신 검색 결과의 id 를 그대로 주라는 안내(숫자, `store-123`, `stay-123`, `coalition-123`)가 됨 (#261)
- 직방 아파트 목록(`search listings apt`·`search listings --complex <apt-…>`)에서 직방 매물과 제휴 매물이 함께 묶인 줄의 `id` 가 직방 매물 대신 직방이 맨 앞에 둔 매물(직방 웹 카드가 대표로 보여 주는 매물, 제휴면 `coalition-…`)이 됨. `listing_ids` 도 직방이 준 순서다. 줄의 제목·층·`listing_kind` 는 원래 그 맨 앞 매물의 값이라, 예전에는 `id` 만 다른 매물을 가리켰다 (#295)
- 직방 상가의 거래 유형(`trade_type`)을 직방 웹 카드·상세처럼 직방이 준 거래 이름(매매·전세·월세)으로 정함. 이름이 비었거나 모르는 값이면 예전처럼 월세금액 유무로 가른다. 지금까지 본 상가는 두 규칙의 답이 같아 출력은 그대로다 (#298)
- 다방 `popular-listings` 가 더 있을 때 `-t`·`--trade` 를 이미 하나씩 골랐으면 조건을 좁히라고 권하지 않고 `--limit` 만 알리며, 한쪽만 골랐으면 나머지 한쪽만 권함 (예전에는 늘 둘 다 권했다) (#249)
- 다방 `sale-schedule --details` 에서 다방이 분양 ID·종류를 주지 않아 맞춰 보지 못한 줄을 '그 날 분양 단지 표에서 찾지 못해' 가 아니라 '다방이 분양 ID·종류를 주지 않아 맞춰 보지 못해 sale 이 null' 이라는 `[참고]` 로 따로 알림. 그런 줄뿐이어도 업데이트 안내는 붙이지 않는다 (#244)
- 네이버 `search complexes`·`search redevelopment` 를 반경으로 찾으면 '조건에 맞는 단지는 이 N곳이 전부입니다'·'조건에 맞는 단지(구역)가 없습니다' 앞에 `반경 Nkm 안에서 ` 가 붙음 (`search listings` 와 같다. 예: `반경 0.3km 안에서 조건에 맞는 단지가 없습니다`)
- 직방 아파트 매물 상세(`listing`·`catalog`)의 `residence_type` 이 `null` 대신 직방의 중개대상물 종류(`아파트`)로 나옴. 제휴 매물은 직방이 주지 않아 그대로 `null` 이다 (#336)
- 직방 덤 조회(호 정보·후기·임대인의 다른 방·건물 학군·건물 실거래·단지 학군·평형 정보·역 주변 단지 정보·단지 카드·원룸 목록에 섞인 오피스텔의 건물 ID·시세 추이의 비교 후보·지역 정보의 거래량·평당가 추이·인구·세대·단지 랭킹 2쪽 이후)의 `[실패]` 안내를 네이버·다방·당근과 같은 공통 꼴로 바꿈. 무슨 일 → 할 일 → 모름이 된 칸 순서이고, 요청 제한이면 기다릴 시간(몇 초 뒤 다시 시도)이, 서버 오류(5xx)·연결 실패면 '잠시 뒤 다시 시도하세요' 가, 직방이 요청을 거절했거나(4xx) 응답 형식이 바뀌었으면 'jibsa 업데이트가 필요할 수 있습니다' 가 들어간다 (요청 제한·서버 오류·연결 실패에는 업데이트 문구가 없고, 4xx 안내의 'HTTP 403' 숫자는 없어졌다. 직방이 목록 자체를 주지 않은 경우도 같은 순서다). 단지 `complex` 의 학군과 원룸 목록(`search listings room -t 원룸` 등)에 섞인 오피스텔의 `complex_id` 는 받지 못해도 안내 없이 `null` 이었는데, 이제 `[실패]` 로 알린다 (#382)
- 당근 `complex` 의 `nearby_subways` 가 서버 순서 대신 당근 웹 단지 화면처럼 도보 시간이 짧은 순(첫 항목이 가장 가까운 역)이고, 도보 분을 웹처럼 반올림해 최소 1분으로 냄. 웹처럼 같은 이름 역을 합치거나 2곳으로 자르지 않고 (역, 노선)마다 모두 준다 (#393)
- 당근 `price-trend` 의 `change_percent` 를 웹 시세 그래프와 같은 소수 첫째 자리 반올림으로 냄 (예전에는 Python `round` 라 .5 에서 값이 어긋날 수 있었다). 웹이 숨기는 변화율(차이 500만원 미만 등)도 값을 계속 낸다 (#393)
- 당근 `region-real-price` 의 남은 거래 안내가 조회마다 다름. 웹에 있는 조회(매매)는 `당근에서 직접 확인하세요` 를 붙이고, 웹에 없는 조회(전월세·`--previous-days`)는 사이트로 보내지 않고 구면 `동 이름으로 좁혀 다시 조회하세요`, 동이면 `이 조건의 남은 거래는 당근 웹에도 없어 더 받을 수 없습니다` 라고 한다. 단지·매물 실거래와 지역 실거래가 전세·월세를 같은 식(월세 > 0 이면 월세)으로 가른다 (#393)
- 당근 `school` 이 이름·코드의 앞뒤 공백을 정리하고, 단지 유형(`-t`)·세대수(`--household-min`)를 몰라 조건을 확인할 수 없는 배정 단지를 빼면서 `[제외]` 로 수를 알림 (조건에 맞는 곳이 없다고 단정하지 않는다). 이때 맞는 단지 수를 알 수 없어 `total_complexes` 는 `null` 이고 `--limit` 으로 잘린 `[일부]` 안내도 수를 쓰지 않는다. 단지 ID 가 없어 `complexes` 에서 뺀 단지는 조건에 맞는 것이 확실해 `total_complexes` 에 센다. 유형을 모르는 학교에 배정 단지가 와도 목록과 `--limit` 안내가 나온다. 배정 단지가 없을 때 학교 종류가 중·고등학교일 때만 '학교군으로 배정돼 단지 목록이 없습니다' 라고 하고, 종류를 모르거나 기타면 '당근에 이 학교의 배정 단지 정보가 없습니다' 라고 한다 (#393)
- 당근 `popular-listings` 가 더 있을 때 조건을 좁히라는 말 없이 `--limit` 만 안내함. 구 전체(구가 없는 세종은 그 동 안) 조회수 기준이라는 안내는 `[범위]` 태그가 붙는다 (#393)
- 당근 `search locations` 가 지역 후보가 100곳에서 잘리면 `[일부]`(곳 수는 쓸 수 없어 뺀 곳까지 센 받은 수), 쓸 수 없는(위치·ID·시·도 이름이 없거나 단계를 모르는) 지역 후보와 위치 정보가 없는 역·대학 캠퍼스를 빼면 `[제외]` 로 알림 (#393)
- 당근 덤 조회(`search locations` 의 역·대학·학교·단지 칸, 조건에 맞는 매물 수, 실거래 공개일 요약, 단지 후보 이어 받기, 지도 범위 검색의 중심 동, `--details` 상세)가 거절(4xx)로 실패하면 `[실패]` 안내가 `잠시 뒤 다시 시도하세요` 대신 `당근이 … 요청을 거절해(HTTP 403) … 받지 못했습니다. API 가 바뀌었을 수 있어 jibsa 업데이트가 필요할 수 있습니다` 다. 서버 오류(5xx)·연결 실패는 그대로 `잠시 뒤 다시 시도하세요` 다. 직방·다방과 같은 갈래이고, 매일 API 감시는 이 경우를 고장으로 본다 (#393)
- 당근 `region-reviews` 가 세종 동(구가 없는 시)도 웹처럼 동 이름을 구 자리에 둔 후기 페이지에서 후기 많은 단지를 줌. 후기 페이지가 404 면 `top_complexes` 가 `null` 이고 `[실패]` 로 알린다 (#393)
- 당근 `good-neighborhoods` 가 지역은 찾았는데 추천 동네가 0곳이면 API 변경 안내를 `[실패]` `notes` 에 붙임 (#393)
- 당근 `nearby-complexes` 의 1200곳 안내가 `search complexes '<시·구·동 전체 이름>'` 에 조건을 줘 좁히라고 함 (#393)
- 당근 GraphQL 에러의 `hint` 가 매물·단지 조건을 준 조회에서만 `조건을 줄여` 를 권하고, 조건을 주지 않은 조회(`jibsa daangn search listings 역삼동`)와 조건 옵션이 없는 명령은 `잠시 뒤 다시 시도하세요` 만 말함. 웹 기본 종류처럼 jibsa 가 채운 값은 조건으로 세지 않는다. 웹 쿼리 해시가 거절된 `UPSTREAM_ERROR` 의 `hint` 는 `같은 조회가 다른 소스(직방·네이버·다방)에 있으면 그 소스를 쓰세요` 를 덧붙인다 (#393)
- 다방 `nearby` 의 `nearest`·`schools` 항목 `distance_m` 을 다방 웹처럼 반올림함: 1m 미만은 소수 한 자리(`0.4`), 그 위는 .5 를 올려 정수 (예전에는 .5 를 짝수로 보내 `88.5` → `88`). 1m 미만 거리가 소수라 라이브러리로 읽는 쪽은 `distance_m` 이 `int` 가 아니라 `float` 일 수 있다 (#393)

### 수정

- 에러 JSON 의 `candidate_count` 를 모를 때(후보가 다 세어지지 않음) 키째 빼던 것을 문서대로 `null` 로 냄 (예: `jibsa daangn search listings --address 테헤란로`)
- `--next` 의 조건이 다르다는 에러와 범위 옵션 순서 에러(`--area-min` 이 `--area-max` 보다 큼 등)가 소수를 유효숫자 6자리로 줄여 앞·지금 값이 똑같이 보이던 것을 받은 값 그대로 씀 (`--lat (앞: 37.497942, 지금: 37.497943)`)
- `--next` 의 조건이 다르다는 에러의 `hint` 가 `--details` 가 없는 명령(네이버 `search listings`, 직방 `search listings apt`)에도 `--details` 를 바꿀 수 있다고 하던 것을 그 명령에 있는 옵션만 적게 고침
- 사이트가 준 4xx·5xx 본문을 에러 `message` 에 실을 때, 따옴표 친 키(HTML 안 JSON 의 `"accessToken":"…"`, JS 문자열 안의 `\"token\":\"…\"`)의 값, 공백이 든 따옴표 값의 뒤 토막, `Authorization: <스킴> …` 의 값, `Cookie:` 의 두 번째 쌍부터를 가리지 못하던 것을 고침 (#424)
- 상태 폴더(`JIBSA_STATE_DIR`)의 잠깐 난 오류(잠금 경합 등)를 첫 화면 실패로 60초 동안 기억해 같은 프로세스의 다음 요청까지 실패시키던 것과, 첫 화면을 열다 실패했을 때 그 오류가 원래 에러를 덮던 것을 고침
- 요청 제한 상태 파일(`<state_dir>/ratelimit/<소스>.json`)에 실수로 바꿀 수 없을 만큼 큰 정수(약 1.8×10³⁰⁸ 이상)가 들어 있으면 그 소스의 모든 명령과 `jibsa limits`·`jibsa limits --reset` 이 `INTERNAL_ERROR`(OverflowError)로 실패하던 것을 고침. 이제 그 값은 깨진 값으로 버린다. 브라우저 쿠키 상태 파일(`<state_dir>/browser/<소스>.json`)의 첫 화면 연 시각이 그런 정수일 때도 그 소스의 모든 명령이 같은 에러로 실패하고 `limits --reset` 으로도 풀리지 않던 것을, 이제 첫 화면을 다시 열게 고침
- 당근 `search commute` 등 매물 목록에서 매물 하나의 인근 역(`subwayStations`·`nearbySubwayStations`)이 `null` 로 오면 검색 전체가 `PARSE_ERROR` 로 실패하던 것을 그 매물만 역 정보 없이 내게 고침 (#331)
- 네이버 `listing` 의 매매 매물을 네이버가 중개보수 '개별확인' 으로 보여 주면 `agent_fee_manwon` 이 금액 대신 `null` 임 (예전에는 금액이 나갔다. 네이버 웹은 그 매물에 금액을 보여 주지 않는다). 그런 매물은 `agent_fee_individual_check_required` 가 `true` 다 (#304)
- 네이버 `complex --pyeong` 의 `market_prices[].sale_average_manwon` 과 `market-price` 의 `points[].sale_manwon`·`jeonse_manwon` 이 기관이 시세를 0 으로 주면 `0.0` 이던 것을 `null` 로 냄 (같은 항목의 시세 범위처럼 0 을 시세 없음으로 본다. `complex` 화면도 0 이면 시세를 그리지 않는다). 두 명령의 `jeonse_ratio_percent` 도 기관이 0 을 줘 둘 다 0 이면 `[0, 0]` 대신 `null` 이다 (#309)
- 네이버 `listing` 의 단지형 빌라 `parking` 이 매물 주차 대수가 0 이거나 없으면 단지 값을 씀 (`가능 (단지 전체 0대)` → `가능 (단지 전체 8대, 세대당 0.5대)`, 가능 여부를 모르면 `단지 전체 8대 (세대당 0.5대)`. 네이버 웹은 매물 대수가 0 보다 크지 않으면 단지 주차 정보를 그린다) (#305)
- 네이버 `listing` 의 항목별 관리비(`manage_cost_manwon`)가 네이버 웹처럼 정액·실비를 가리지 않고 모든 항목의 금액을 더함 (예전에는 정액 항목만 더했다. 실비 항목은 지금까지 본 응답에서 금액이 없어 값이 바뀐 매물은 아직 없다). `manage_cost_includes` 는 그대로 정액 항목만 남는다 (#313)
- 네이버 `listing` 의 원룸·빌라·단독 등(단지가 아닌 건축물대장 유형 15개) `parking` 이 매물 주차 대수가 0 이거나 없으면 네이버 웹처럼 건축물대장의 총 주차 대수를 씀 (대장이 8대면 `불가` 나 `불가 (총 0대)` 였던 것이 `불가 (총 8대)` 가 된다. 매물 대수가 0 인데 대장에 대수가 없거나 대장 조회가 실패하거나 pnu 가 없으면 `불가 (총 0대)` 였던 것이 `불가` 로, 가능 여부만 낸다). 이 경우 건축물대장 요청을 1회 더 한다. 이 유형은 단지 번호가 있어도 `단지 전체 N대` 가 아니라 웹 건축물 정보('주차 N대')처럼 `총 N대` 로 낸다. 대수를 가져온 쪽(매물 또는 대장)에 세대당 대수가 있으면 `가능 (총 8대, 세대당 0.5대)`(가능 여부를 모르면 `총 8대 (세대당 0.5대)`)처럼 붙인다 (소수 둘째 자리 아래를 버리고 0 이면 붙이지 않는다) (#320)
- 네이버 `search listings --entrance` 가 단지가 없는 매물이 빠졌다고 알리던 것을, 현관 구조가 등록되지 않은 매물이 빠졌다는 `[제외]` 안내로 바꿈. 네이버는 단지가 아닌 빌라도 현관 구조가 등록돼 있으면 결과에 준다. `--household-min`·`--household-max`·`--parking` 의 `[제외]` 안내는 빠진 조건 목록에서 현관 구조만 빠지고 그대로다. 둘을 함께 주면 단지 매물만 남으므로 현관 구조 안내에 '단지가 아닌 빌라도 나온다' 는 말이 붙지 않는다 (#310)
- 응답 헤더를 받은 뒤 본문이 멈춘 4xx·5xx 응답을 시간 초과 대신 그 상태로 알림. 429 면 `Retry-After` 대로 요청 제한 쿨다운을 건다 (#217)
- 라이브러리로 쓸 때: client 의 `timeout` 을 약 24.8일(2³¹−1ms)보다 크게 주면 기다리지 않고 바로 시간 초과가 나던 것을 고침. 그 값에서 자른다 (#217)
- 당근 `region-reviews`·`school`·`preschool` 이 쓰는 웹 쿼리 해시를 당근 웹이 바꾼 해시로 갱신. 당근이 옛 해시를 막으면 이 명령들이 `UPSTREAM_ERROR` 로 실패했을 것이다 (#192)
- 당근 `complex` 의 중·고등학교 카드가 당근 웹과 같게 고름: 도보 20분 안 학교가 없으면 시간·거리 순으로 가장 가까운 한 곳(예전에는 비웠다), 도보 분은 웹처럼 반올림·최소 1분, 배정 학교 정렬에 직선거리 대체값 사용 (#222)
- 당근 `compare` 가 당근 웹처럼 보증금 0 인 월세 실거래와 월세 상한 없는 KB 월세는 비우고, 전용면적을 모르는 평형 묶음은 건너뛰며, 평형 타입을 못 찾으면 `pyeong` 을 `null` 로 줌 (#222)
- 당근 동 이름 `search listings` 의 `total`(동 거품 수)을 당근 웹이 동 거품을 그리는 줌 12 범위로 묻고, 조건이 없으면 웹처럼 필터를 `null` 로 보냄. (#215)
- 당근 지도·역·대학·출퇴근·인기 매물·단지 매물 카드의 주소에 시·도를 채울 때, 구·동 이름이 같은 동이 여러 시·도에 있으면(서울·대구 중구 태평로1가, 대구·울산 중구 교동) 시·도 없이 `중구 교동` 으로 내던 것을 카드의 당근 지역 ID 로 가려 채움 (#215)
- 당근 매물 검색이 덤으로 세는 매물 수(`total`) 조회에서 요청 제한에 걸리면 받은 매물까지 버리고 `RATE_LIMITED` 로 끝나던 것을 고침. `total` 을 `null` 로 두고 이유를 `notes` 로 알린다 (#215)
- 당근 `real-price` 가 거래를 받지 못했을 때 까닭을 가려 알림. `--years` 기간 앞에만 거래가 있으면 그 기간 안에는 없고 그 앞 거래는 있다고, 전월세 거래는 있는데 고른 전세·월세가 없으면 받은 전월세 수와 함께 0건이라고 알린다. 예전에는 `--item` 이 이때도 '이 매물 건물의 실거래가 없습니다 … 빌라·주택은 대부분 없습니다' 라고 했고, 단지는 안내 없이 빈 목록이었다 (#222)
- 당근 `search listings --university 고려대학교` 가 늘 `REGION_AMBIGUOUS`(후보 `고려대학교 세종캠퍼스`·`고려대학교`)였고 후보 `고려대학교` 를 다시 넣어도 같던 것을 고침. `search locations` 의 `universities[].name` 과 같은 이름이 하나면 그 캠퍼스(캠퍼스 이름이 없는 본교)를 쓴다 (#215)
- 당근 대학 후보를 20곳만 받아 뒤의 캠퍼스·대학원(고려대학교 23곳 중 `고려대학교 치의학대학원 안암캠퍼스` 등 3곳)이 `search locations` 에서 알림 없이 빠지고 `--university` 는 `REGION_NOT_FOUND` 이던 것을 고침. 50곳까지 받고, 50곳이 다 오면 `[일부]` `notes`·`hint` 로 알린다 (#215)
- 당근 구 이름까지 같은 동(`태평로2가` → 서울·대구 중구)의 `REGION_AMBIGUOUS` 힌트 예시가 `'중구 태평로2가'` 라 다시 넣어도 모호하던 것을 고침. 시·도까지 붙인 이름을 예로 든다 (#215)
- 당근 `trending-complexes 신사동` 처럼 같은 이름 동을 주면 `'강남구 신사동'` 을 권해 따르면 `INVALID_ARGUMENT` 이던 것을 고침. 바로 `INVALID_ARGUMENT` 로 그 동들의 구(`candidates`)를 준다 (#222)
- 당근 `popular-listings` 가 여러 시·도에 있는 구 이름(중구·남구)의 동에서 시·도를 채우려 지역 검색을 더 보내던 것을 고침 (`'서울 중구 명동2가'` 요청 5회 → 2회) (#215)
- `jibsa guide common` 이 `--fields` 를 받는 매물 목록 명령에 다방(`search listings` 의 `room`·`villa`·`officetel`·`apt`·`--complex` 와 `popular-listings`)을 빠뜨려, 다방에서는 `--fields` 를 쓸 수 없는 것처럼 읽히던 문제 (#227)
- 직방 아파트 매물 상세(`listing <숫자 ID>`)가 살아 있는 매물도 모두 `LISTING_UNAVAILABLE` 로 끝나던 문제. 직방 주거 상세가 아파트 매물을 받지 않게 바뀌어, 직방 웹 아파트 매물 화면과 같은 아파트 상세 하나로 만든다. 직방 웹처럼 `floor` 는 `저층`·`중층`·`고층` 이고, `registered_at`·`nearby_subways`·`elevator`·`residence_type`·`room_type`·`household_count`·`address` 는 `null`(주소는 `complex` 에서 본다), `total_parking_count` 는 단지 전체 주차 대수다. 직방이 제목·층·방향을 빈 글자로 주면 `title`·`floor`·`direction` 은 `null` 이다. 아파트·제휴(`coalition-…`) 매물이 없거나 내려갔으면 `LISTING_UNAVAILABLE` 에 `reason: APT_ITEM_NOT_FOUND` 를 붙이고, 다른 소스 ID·접두어를 확인하라는 안내는 붙이지 않는다. 관리비가 0원으로 오면 직방 웹처럼 비워 `manage_cost_manwon` 이 `null` 이다 (`catalog` 도 같다) (#261)
- 직방 원룸·빌라·오피스텔 목록에서 관리비가 없는 매물의 `manage_cost_manwon` 이 `null`(모름)로 나오던 문제. 직방 웹 목록 카드와 같은 관리비를 읽어 `0` 으로 낸다 (#261)
- 직방 원룸·빌라·오피스텔 `listing` 의 `manage_cost_includes` 가 실비로 따로 내는 전기·가스·수도 등도 관리비에 포함된 것처럼 내던 문제. 직방 웹 매물 화면처럼, 정액 관리비에서 항목별 내역을 알린 매물은 관리비 금액에 든 항목만 낸다. 실비 관리비나 내역을 알리지 않은 매물은 직방이 준 포함 항목 그대로(웹 화면과 같다)이고, 내역이 없고 관리비가 0원이거나 없으면 웹처럼 '관리비 없음'(금액 `0`, 항목 `[]`)이고, 직방이 준 두 관리비 칸이 어긋나면(웹은 '관리비 없음' 인데 원 단위 금액이 있음) 금액·항목 모두 `null` 이다. 순서는 웹 화면 순서(일반(공용) 관리비·전기·수도·…)다. 직방 웹이 '관리비 확인 불가' 로 보여 주는 매물은 `manage_cost_manwon`·`manage_cost_includes` 모두 `null` 이다 (#261)
- 다방 매물 검색의 `--next` 가 다방이 한 쪽을 23건만 준 뒤 앞 결과의 매물을 다시 주던 문제. 다방 쪽 번호와 그 쪽에서 쓴 칸으로 이어 받는다. 다방이 쪽끼리 같은 매물을 겹쳐 주는 것은 웹처럼 남는다 (#235)
- 다방 매물 검색(`--next` 로 이어 받을 때 포함)·`search listings --complex`·`search complexes`·`search sales` 가 다방이 한 쪽을 24건보다 짧게 주면 다방에 더 있어도 `--limit` 을 다 채우지 못하고 안내 없이 멈추던 문제. `--limit` 이 찰 때까지 쪽을 더 받고(쪽 수 상한은 그 목록의 쪽 크기를 따라 24건씩 오는 목록은 10쪽까지, 30곳씩 오는 `search schools`·`hot-places` 는 8쪽까지), 그래도 못 채우거나 다방이 더 있다고 한 뒤 다음 쪽 결과를 주지 않아 멈추면 `[일부]` 로 알린다 (#235)
- 다방 `popular-listings` 의 `rank` 를 받은 수로 세어, 다방이 한 쪽을 덜 채우면 그 뒤 순위가 앞으로 당겨질 수 있던 문제. 쪽과 그 쪽 안 위치로 센다 (#235)
- 다방 `listing` 의 `manage_cost_includes` 가 공용 관리비를 실비로 표시한 매물에서 비던 문제. 다방 화면처럼 공용은 관리비 합계에 들어 `공용 관리비` 를 넣고, 포함 항목을 다방 화면의 규칙(관리비 입력 방식·부과 방식)대로 고른다 (#235)
- 다방 `listing` 의 `manage_cost_includes` 가 기타부과 매물과 항목을 적지 않은 정액관리비 매물에서 다방이 포함 항목을 빈 목록으로 주면 `[]` 가 아니라 `null`(모름)로 나가던 문제 (#241)
- 다방 `popular-listings`·`region-ranking`·`real-price` 가 다방이 빈 쪽에 '더 있음' 을 주면 `has_more` 를 `true` 로 내던 문제. 빈 쪽이면 `false` 로 두고, `real-price` 는 빈 쪽 뒤를 더 묻지 않는다 (#241)
- 다방 `complex` 의 `area_prices` 가 다방이 평당가를 0 으로 주면 `0` 으로 내던 문제. 다방 화면이 '정보 없음' 으로 그리는 값(없거나 0)은 `null` 로 낸다 (#245)
- 다방 `complex` 가 다방이 평당가 비교(`area_prices`)나 평형 목록(`pyeongs`)을 `null` 로 주면 `PARSE_ERROR` 로 끝나던 문제. 그 칸을 `null`(모름)로 내고 나머지 결과는 그대로 낸다. 평형을 모르면 `recent_sale`·`recent_lease` 의 `space_seq`·`area_m2` 는 `null` 이다. `search listings --complex` 는 `--pyeong` 이 있으면 그 번호를 그대로 보내고(없는 번호라고 막지 않는다), 없으면 `NOT_FOUND` 다 (#245)
- 다방 `sale-schedule --details`·`--region` 이 청약 일정 표의 한 줄에 분양 ID 가 없을 때 `PARSE_ERROR` 로 끝나던 문제. 그 줄의 `sale` 이 `null` 이고 `[참고]` 가 그 날 분양 단지 표에서 같은 분양·종류를 찾지 못했다고 알린다 (#244)
- 다방 `search complexes` 의 `recent_sale_manwon`·`recent_lease_manwon` 을 '다방이 고른 대표 평형' 의 거래라고 적던 문서 오류. 평형과 상관없이 단지의 가장 최근 거래다 (다방 목록 카드와 같다) (#235)
- 다방 `trending-complexes` 의 `view_count` 를 조회 수로, `neighborhood` 의 `prices.rank` 를 평균가 순위로만 적던 문서 오류. `view_count` 는 기간 안 조회한 사람 수(다방 화면의 'N명'), `prices.rank` 는 아파트 매매 기준 순위다 (#235)
- 다방 `search complexes --radius` 도움말이 반경 밖 단지를 뺀다고 하던 문제 (반경을 덮는 사각형을 그대로 받는다). 매물 검색의 방 크기 옵션 도움말이 아파트 공급 평만 적던 것도 고쳐 유형별 기준 면적(원룸·투룸 매물 유형별, 빌라 전용, 오피스텔 계약, 아파트 공급)을 적는다 (#235)
- 네이버 `listing` 의 `move_in` 이 이내입주·이후입주 매물에 날짜만(`2026-12-01`) 내 '이내' 와 '이후' 가 구분되지 않던 문제. 네이버 매물 화면처럼 `2026-12-01 이내`·`2026-12-01 이후` 로 낸다 (네이버가 연월만 주면 `2026-12 이내`)
- 네이버 `listing` 의 `move_in` 이 초순·중순·하순 매물에 네이버가 날짜를 비우거나 날짜로 읽을 수 없는 값을 주면 `"  초순"` 같은 글자를 내던 문제. 날짜 지정 매물과 같은 규칙으로 날짜 자리가 `-` 거나 비었으면 `null`, 읽을 수 없으면 받은 글자 그대로 낸다. 꼴만 맞고 달력에 없는 날짜(`0000-00-00`·`2026-02-30`)도 읽을 수 없는 값으로 본다 (예전에는 `0000-00 초순` 을 낼 수 있었다). 네이버가 연월만(`2026-11`) 줘도 `2026-11 초순` 으로 낸다
- 네이버·당근 `listing` 의 `move_in` 이 날짜로 읽을 수 없는 글자를 그대로 낼 때 협의 가능 매물이어도 ` (협의 가능)` 을 붙이지 않던 문제. 날짜일 때처럼 뒤에 붙인다
- 네이버 `regions` 가 같은 이름의 시·군·구를 검색창 첫 쪽(다섯 곳)만 보고 세어, 여섯 곳 이상이면 `5곳입니다` 로 단정하고 첫 쪽에 하나뿐이면 다음 쪽을 보지 않고 고를 수 있던 문제. 이름이 맞는 곳이 첫 쪽 끝까지 이어지면 다음 쪽을 최대 2회 더 받아 센다 (`중구`·`동구` 는 요청 1회 더)
- 네이버 `listing` 이 네이버가 관리비 '없음' 으로 보여 주는 매물의 `manage_cost_manwon`·`manage_cost_includes` 를 모름(`null`)으로 내던 문제. `0`·`[]` 로 낸다 (관리비를 확인할 수 없는 다른 사유는 그대로 `null`)
- 로컬 폴더·파일에서 설치한 jibsa(`uv tool install .`·`pip install .`)가 같은 버전 번호로 코드만 바꿔 다시 설치해도 그 전에 받은 `next` 를 받아, 위치 꼴이 바뀐 명령이 엉뚱한 오류를 내거나 앞 결과와 겹쳐 이어 받을 수 있던 문제. 이제 `다른 버전의 jibsa 가 만든 next` 로 멈춰 처음부터 다시 찾게 한다. `jibsa --version` 출력은 그대로다
- 직방 단기임대 상세의 `options` 에 반려동물 가능 매물이면 직방 코드 `PET_ALLOWED` 가 그대로 섞여 나오던 문제. 직방 웹처럼 옵션 목록에서 빼고 반려동물은 새 `pet_allowed` 로 낸다 (#338)
- 직방 `real-price` 가 거래 유형을 읽지 못한 실거래(jibsa 가 모르는 유형이거나 유형이 빈 거래)를 알리지 않고 빼던 문제. `--trade` 가 무엇이든 `[제외] 거래 유형을 읽지 못한 실거래 N건을 뺐습니다. jibsa 업데이트가 필요할 수 있습니다` 로 `notes` 가 알린다 (#335)
- 직방·네이버·당근·다방 응답의 목록 칸(검색 결과·옵션·가까운 역·할인 등)에 사이트가 `null` 을 주면 그 명령이 `PARSE_ERROR` 로 끝나거나 덤 값을 통째로 잃던 문제. 키가 없을 때와 같게 검색 결과는 빈 목록, 직방 상세의 옵션·가까운 역·할인 같은 값은 모름(`null`)으로 낸다. `null` 이 모름인 칸(다방 단지 학교·어린이집, 네이버 재개발 역·지구, 직방 건물 실거래·호 공시가격)은 그대로 모름(`null`)이다. 목록 안에 빈 항목이 섞여 와도 명령이 끝나지 않고 그 항목을 빼고 읽는다. 어느 목록이든 빈 항목을 빼면 `[제외]` 안내가 붙고(끝에 'jibsa 업데이트가 필요할 수 있습니다' 가 붙는다), 그 목록으로 계산한 값은 `null` 로 둔다. 계산에 쓰지 않고 보여 주기만 하는 목록은 어느 목록인지 말하지 않는 `[제외] 직방 응답의 목록에 빈 항목 2개가 와서 빼고 읽었습니다. jibsa 업데이트가 필요할 수 있습니다` 한 줄로 알린다. 직방 원룸·빌라·오피스텔 검색과 건물 매물 목록의 요약 응답에서 뺀 빈 항목은 뺀 매물 안내에 이유로 함께 밝힌다. 그래서 숫자·목록이던 일부 칸이 `null`(모름)일 수 있다: 직방 상가 `total`, 단기임대 상세의 `available`·`unavailable_periods`·`pet_allowed`·`host_other_listings`·`host_other_listing_count`, 실거래의 `pyeong_name`, 원룸·빌라·오피스텔 상세의 `manage_cost_includes`·`manage_cost_excludes`, 아파트 목록의 `listing_kind`, 네이버 관리비 합계·포함 항목과 동네 추이의 최근 평당가(`latest_manwon`), 당근 `price-trend` 의 `total_transactions`·`summary`·`recent_*`, `school` 의 `total_complexes`, `nearby-complexes` 의 `total`, `popular-listings`·`trending-complexes` 의 `rank`, 다방 동네정보의 `total`, `popular-listings` 의 `rank`, `sale-schedule` 의 `total`, 관리비 항목. 당근 매물 목록은 빈 항목도 받은 자리로 세어 `--limit` 을 다시 채우지 않고, `[제외] N건을 받아…` 의 N 은 빈 항목을 뺀 수다 (#383)
- 직방이 단지 평형 목록(매물 목록 응답의 `danjiRoomTypes`)을 주지 않으면 `complex apt-…` 가 평형이 없는 단지처럼 `pyeongs: []` 를 내고, `search listings --complex apt-… --pyeong` 이 평형 ID 를 확인하지 않고 안내 없이 그 평형으로 찾던 문제. 이제 `complex` 는 `pyeongs: null` 과 끝에 'jibsa 업데이트가 필요할 수 있습니다' 가 붙은 `[참고]` 를 내고, `search listings --complex` 는 평형 ID 를 확인하지 못한 채 그 평형으로 찾으며 같은 꼴의 `[참고]` 로 알린다. 평형이 아직 없는 단지(분양예정)는 그대로 `pyeongs: []` 다 (#390)
- 당근 `search locations`·`search listings`·`search commute` 가 이름이 같은 역·대학·주소·지역 후보 중 당근이 위치(좌표·건물 정보·ID·시·도 이름)를 주지 않거나 단계를 모르는 후보를 빼고 세어, 후보가 둘인데 하나뿐인 줄 알고 남은 하나를 말없이 고르던 문제. 쓸 수 없는 후보도 세어 모호하면 `REGION_AMBIGUOUS` 로, 웹이 고르는 후보에 위치가 없으면 `REGION_NOT_FOUND` 로 알린다. 이름이 같은 동·구가 있지만 모두 쓸 수 없는 것뿐일 때도 '없다' 고 하거나 비슷한 지역을 권하지 않고 `REGION_NOT_FOUND`(`이름이 같은 지역이 N곳 있지만, 당근이 위치·ID·시·도 이름을 주지 않거나 단계를 몰라 고를 수 없습니다`, `hint` 는 이웃한 동·구 이름으로 찾으라는 것)로 알린다. 동을 받지 않는 `trending-complexes` 는 그때도 그 동의 구를 권하는 `INVALID_ARGUMENT` 다. 주소(`--address`)는 입력과 도로명·지번 주소가 정확히 같은 후보도 건물 정보가 없는 후보까지 센다: 정확히 같은 후보가 둘 이상이면 `REGION_AMBIGUOUS` 이고 `hint` 가 `--address` 예시 대신 좌표(`--lat/--lng`)를 권하며, 정확히 같은 하나에 건물 정보가 없으면 다른 후보를 고르지 않고 `REGION_NOT_FOUND` 다 (예전에는 같은 도로명 후보 중 건물 정보가 있는 쪽을 말없이 골랐다). 같은 이름 동의 `REGION_AMBIGUOUS` 는 `message` 의 '…곳입니다' 와 `candidate_count` 가 쓸 수 있는 곳과 쓸 수 없는 곳을 합친 수이고 (`message` 끝에 ` (위치·ID·시·도 이름이 없거나 단계를 몰라 고를 수 없는 같은 이름 지역 N곳)` 이 붙고 `candidates` 에는 쓸 수 있는 곳만 온다. 동을 받지 않는 `trending-complexes` 에 같은 이름 동을 줘 구를 권하는 `INVALID_ARGUMENT` 만 예외로, 쓸 수 없는 동의 구도 `candidates` 에 넣고 `candidate_count` 는 겹침을 지운 구 수이며 `message` 의 동 수만 합친 수다), 쓸 수 없는 같은 이름 동의 구가 겹치면 `hint` 의 예시를 시·도까지 붙인 이름으로 준다. 대학 후보가 50곳에서 잘렸는데 맞는 곳이 하나면 `[모호]` 로 알린다 (#393)
- 당근 비슷한 지역 `hint` 의 예시가 `신사동` 처럼 같은 이름이 여러 곳인 이름이던 것을 후보의 전체 이름으로, 동만 받는 `popular-listings` 에 같은 이름 구(`중구`)를 주면 구를 고르게 하던 안내를 시·도부터 붙인 동 이름 후보로 고침. 역 이름을 지역 자리에 줄 때 `--station` 예시(`'서울 강남역'` → `--station 강남역`, 숫자만 쓴 노선 `'2호선 강남역'` → `--station '강남역'`, '역' 을 띄어 쓴 `'강남 역'` → `--station 강남역` (예전에는 `--station '역'` 이라 그대로 넣으면 찾지 못했다). 당근은 숫자 노선에 `서울2호선` 처럼 지역을 붙여 `2호선` 을 그대로 넣으면 찾지 못한다)와 단지 이름이라고 단정해 리 이름·행정동 안내를 지우던 `hint` 도 바로잡았다. `jibsa guide`(`docs/llm.md`)의 당근 절에도 `--station` 에는 당근 노선 이름만 붙이고 `2호선` 처럼 숫자만 쓴 노선은 빼라고 적었다 (#393)
- 당근 동·지도 범위·역·대학·통근 매물 목록의 둘째 쪽 이후 `pageInfo` 가 `null` 이면 `이 N건이 전부입니다` 라고 하던 문제. 그 쪽을 세지 않고 `[일부]` 멈춤 안내와 `has_more: true` 로 알리고, 매물 칸이 모두 비어 있는 쪽 뒤에는 `next` 를 내지 않는다. 지번 주소가 빈 글자인 매물은 지역 이름으로 채운다 (#393)
- 당근 매물 하나의 `trades`·`images`·`options`·역 노선이 `null` 이거나 거래 유형이 비어 와도 검색 전체가 `PARSE_ERROR` 가 되지 않음 (그 매물의 해당 칸만 비운다). 매물 유형 코드·옵션 이름·관리비 항목 코드가 `null` 이어도 같다: 유형은 `property_type: null`, 이름을 모르는(`null`·빈 글자·`-`) 옵션은 그 옵션만, 관리비 항목(코드가 빈 글자·`-` 인 것도)은 직접 입력한 이름이 있으면 그 이름으로 하고 없으면 그 항목만 빠진다 (직접 입력한 이름이 빈 글자·`-` 면 없는 것으로 본다). 포함·따로 내는 항목이 있는데 이름을 하나도 모르면 `manage_cost_includes`·`manage_cost_excludes` 그 칸이 `null`(모름), 일부만 알면 아는 이름만 준다. 직거래 매물의 미포함 관리비 목록(`excludeManageCostOption`)에 `null` 항목이 와도 `listing` 이 `PARSE_ERROR` 로 깨지지 않고 그 항목만 빼며, 목록이 통째로 `null` 이면 `manage_cost_excludes` 가 `[]` 대신 `null`(모름)이다 (#393)
- 당근 `compare` 가 관리비·배정 학교 거리·도보 시간·주변 역 값이 소수로 오면 `PARSE_ERROR` 로 끝나던 문제. 소수를 읽어 당근 비교 화면처럼 값 그대로 낸다. 바깥 단지가 `null` 인 `nearby-complexes` 도 없는 단지(`NOT_FOUND`)로 알린다 (#393)
- 당근 `listing` 의 `parking` 이 작성자가 주차 불가로 올린 매물에 주차 대수가 있으면 `가능 (N대)` 로 내던 것을 `불가` 로 냄. 작성자가 주차 여부를 고르지 않았고 대수가 1 이상이면 전처럼 `가능 (N대)` 다 (#393)
- 당근 `price-trend` 가 시세 그래프의 점 하나에 연월이 없거나(null·빈 값·`-`) 읽을 수 없으면 명령 전체가 `PARSE_ERROR` 로 끝나던 문제. 그 점만 빼고 `[제외] 당근이 연월이나 평균 가격을 주지 않은 시세 점 N개는 뺐습니다` 로 알린다. 거래가 있는데 평균 가격이 없거나 0 인 점도 같고, 어느 달의 얼마인지 몰라 `total_transactions`·`summary`·`recent_average_manwon`·`recent_transactions` 를 `null`(모름)로 낸다 (빈 항목을 뺐을 때와 같고 안내가 알린다. `points` 는 연월을 아는 달만 준다). 당근이 그래프의 점 목록을 `null` 로 줄 때도 그래프를 주지 않았을 때처럼 `points`·`total_transactions`·`summary`·`recent_*` 가 `null`(모름)이다 (예전에는 `PARSE_ERROR`) (#393)
- 직방·다방·당근 `--details` 가 상세 한 건의 실패(요청 제한·거절(4xx)·서버 오류·응답 형식 변경) 때문에 이미 받은 목록 전체를 잃던 문제. 실패한 매물은 목록 값만 두고(직방은 건물 용도 `residence_type` 이 `null`) `[실패]` 하나로 수와 이유를 알린다. 이유는 실패 순서가 아니라 할 일로 고른다: 업데이트가 필요한 실패가 한 건이라도 있으면 그 이유(요청 제한도 왔으면 `요청 제한에도 걸려 그 뒤로는 요청하지 않았습니다` 를 덧붙인다), 없으면 요청 제한(그때부터 남은 매물의 상세는 요청하지 않는다), 없으면 첫 실패의 이유다. 거절(4xx)·응답 형식 변경이면 `jibsa 업데이트가 필요할 수 있습니다`, 서버 오류·연결 실패면 `잠시 뒤 다시 시도하세요` 를 붙인다 (세 소스 같다). 거래가 끝난 매물만 전처럼 뺀다 (#393)
- 당근 `search locations` 의 역·대학·학교·단지 칸이 요청 제한에 걸리면 받은 지역 칸까지 잃고 `RATE_LIMITED` 로 끝나던 문제. 이제 받은 칸은 돌려주고 걸린 칸은 `null` + `[실패]` 이며, 이후 칸은 요청하지 않는다 (#393)
- 당근 지도 범위 거절 에러의 문구가 입력에 맞춰 `좌표`·`구 이름`·`주소` 조회라고 하고, 통근 검색의 `--sort` 사용법 `hint`·`WORKPLACE` 도움말의 `--address`·`search complexes` 의 `--trade`·`--area-min/--area-max` 도움말이 동작대로 바로잡힘. 통근 검색의 안내가 지하철 시간을 모르는 역만 있을 때 `--max-minutes` 를, 조건이 없을 때 `조건을 넓히라` 고 하지 않고, 회사에서 도보 60분 안에 역이 없다는 `hint` 에 실제 좌표를 넣는다. 당근이 준 역이 모두 지하철 시간을 모르면 '역이 없습니다' 대신 `[범위] 당근이 준 역 N곳 모두 지하철 시간을 몰라 --max-minutes 안인지 확인할 수 없습니다` 한 줄과 회사 역 주변을 볼 명령만 알린다 (#393)
- 직방·네이버·당근·다방의 날짜 칸에 소스가 값이 없다는 표시로 준 `-` 가 그대로 나가던 것을 `null`(모름)로 냄. 네 소스 공통 날짜 변환(`normalize_date`)이 `-` 를 `null` 로 바꾸고, 당근 어린이집 `established_at`·`opened_at` 도 이 변환을 쓴다. 당근 실거래 `registered` 도 등기일이 `-` 면 `false` 이고, 당근 매물 지번 주소가 빈 글자나 `-` 면 지역 이름(시·구·동)으로 채운다 (지역도 모르면 `null`). 연월만 있는 값 등 읽을 수 없는 다른 값은 전처럼 원래 글자 그대로다. 네이버 `real-price` 의 계약일 `trade_date` 와 `market-price` 의 시세 점 `points[].base_date` 도 네이버가 값을 주지 않았거나 빈 값·`-` 로 주면 `null` 이다 (예전에는 `-` 가 그대로 나갔고 `real-price` 는 계약일이 `null` 이면 명령이 `PARSE_ERROR` 였다. 계약일을 모르는 거래와 기준일을 모르는 시세 점도 빼지 않는다). 빌라 단지 `real-price --period` 는 계약일을 모르는 거래(`trade_date` `null`)를 기간 안인지 알 수 없어 결과에 남기고, 쪽 넘김을 멈추는 판정에는 세지 않는다. 날짜 칸을 늘 글자로 읽던 쪽은 `null` 도 처리한다 (#393)
- 네이버 `listing` 의 `address` 에서 읍·면 매물의 리 이름이 빠지던 문제 (`경기도 양평군 용문면 다문리 677-3`). 동 이름을 매물 좌표 대신 매물의 법정동 코드로 찾아(네이버 웹 매물 화면과 같은 조회, 법정동 코드가 있는 매물은 요청 1회) 경계 근처 매물에 옆 동 이름이 붙지 않는다. 사무실·상가·빌딩·상가건물·숙박·공장·토지·지식산업센터·재개발·기타·전원주택·한옥과 건물 유형이 단독인 매물은 웹처럼 중개사가 지번을 공개했을 때만 지번을 붙인다. 법정동 이름을 받지 못하면 `address` 는 `null` 이고 `[실패]` 로 알린다 (#393)
- 당근 `search listings` 를 `--next` 로 이어 받은 결과가 다음 쪽 문제로 멈추면 멈춤 안내가 앞 결과를 뺀 이번 쪽의 수(`앞 결과에 이어 받은 이번 쪽 N건에서 멈췄습니다`)를 말함. 앞 결과를 받은 뒤 이어 받은 첫 쪽이 비어 있으면 0건에서 멈췄다고 읽히던 문제 (#393)
- 당근 면적 조건(`--area-min`·`--area-max`)을 소수 둘째 자리 글자(`84.9` → `'84.90'`)로 보냄 (당근 웹 매물 필터와 같다). 1만㎡ 이상에서 소수가 반올림돼 조건 경계가 바뀌던 문제 (`12345.67` → `12345.7`). 정확히 반인 값도 웹 `toFixed` 처럼 올린다 (`84.125` → `'84.13'`) (#393)
- 당근 `search listings --complex` 가 당근이 쪽마다 요청한 건수보다 적게 줘 쪽 수 상한(6쪽)에 닿아 멈추면 안내 없이 `has_more: true` 만 나가던 문제. `[일부]` 로 알리고 `--limit` 을 늘려도 더 받지 못하니 나머지는 `url` 의 단지 페이지에서 보라고 한다 (#393)
- 당근 `compare` 의 관리비(`manage_cost_manwon`·`manage_cost_per_m2_manwon`) 평균이 ㎡당 관리비가 비어 온 달을 건너뛰던 문제. 웹처럼 그 달을 0 으로 세어 평균에 넣는다 (받은 달이 있는데 모두 비어 오면 0) (#393)
- 당근이 숫자 칸에 글자 `NaN`·`Infinity` 를 주면 출력 JSON 에 `NaN` 이 그대로 나가던 문제. 그 칸을 `null`(모름)로 낸다 (#393)

## 0.12.0 — 2026-11-11

### 변경

- 일부만 돌려준 검색의 `[일부]` 안내를 전체 수부터 말하도록 바꿈: `조건에 맞는 매물 약 41건 중 검색 중심에서 가까운 1건입니다` → `조건에 맞는 매물이 약 41건 있고, 그중 검색 중심에서 가까운 순으로 1건만 보여 줍니다`. 확인한 매물이 모두 빠졌을 때 나오던 `가까운 0건입니다` 는 `보여 줄 매물이 없습니다` 로 알린다 (#205)
- 이어 받기 안내를 `이어 보려면 결과의 next 를 --next 로 주세요` 에서 `이어 보려면 같은 명령에 --next <결과의 next 값> 을 붙이세요` 로 바꿈. 예전 문구는 `--next` 만 붙이라는 말로 읽혀 값 없이 붙이면 `INVALID_ARGUMENT` 로 막혔다. `--help` 와 `jibsa guide` 문서의 이어 받기 설명도 `--next <결과의 next 값> 을 붙여` 꼴로 맞춤 (#205)
- 당근 지역 단지 목록이 `--limit` 에 닿았을 때 `최대 20개 단지를 조회했습니다` 대신 `단지가 더 있어 앞 20곳만 보여 줍니다` 로 알림. 좁힐 것은 `--limit` 이 최대값일 때와 같이 `지역·단지 유형·세대수·가격 조건` 으로 적는다 (#205)
- 당근에서 거래 조건을 고르지 못해 뺀 매물 안내를 `서버 필터를 통과한 매물 N건은 응답의 거래 조건 중 …` 에서 `당근이 조건에 맞다고 준 매물 중 N건은 목록만으로 거래 유형·금액이 맞는지 알 수 없어 … 뺐습니다` 로 줄임 (#205)
- 직방 실거래를 끝까지 받았을 때 `직방 API가 제공하는 마지막 실거래가 페이지까지 조회했습니다` 대신 `직방이 주는 실거래를 끝까지 받았습니다` 로 알림 (#205)
- 직방 오피스텔 건물 매물의 `[일부]` 안내를 다른 검색과 같은 꼴(`조건에 맞는 매물이 N건 있고, 그중 직방 목록 순으로 M건만 보여 줍니다`)로 바꾸고, `[제외]` 안내도 `직방 목록 순으로 앞의 매물` 로 맞춤 (#205)
- 금액 환산 안내를 `금액은 만원이다` 에서 `금액은 만원 단위입니다` 로 바꿈 (#205)
- 안내의 말투를 `보여 줍니다`·`~하세요` 로 맞추고, 당근 단지와 어린이집·유치원은 다른 소스처럼 `곳` 으로 셈 (#205)
- 네이버 단지 목록·재개발 구역 목록의 안내도 다른 소스처럼 `곳` 으로 셈 (`전체 45건 중 2건입니다` → `전체 45곳 중 2곳입니다`) (#205)
- 당근 학교 배정 단지의 `[일부]` 안내를 다른 목록과 같은 꼴(`더 보려면 --limit 을 늘리거나 단지 유형(-t)·세대수(--household-min) 조건을 좁히세요`, 최대값이면 `--limit 의 최대값은 1200입니다. …`)로 맞춤 (#205)
- 당근 실거래를 `--limit` 으로 잘랐을 때 `거래가 더 남아 있습니다` 를 따로 붙이지 않고 `조회된 실거래 N건 중 --limit M 에 맞춰 M건만 보여 줍니다. --limit 을 최대 1200까지 늘리세요` 한 줄로 알림. 24페이지(최근 1200건)째에서 잘렸고 그 뒤에도 거래가 남았으면 `--limit` 을 늘려도 받지 못하므로 당근 사이트 안내도 함께 붙인다 (#205)
- 당근 실거래의 `최근 전월세 실거래 N건 중 월세 M건입니다` 안내에서 `더 오래된 거래는 당근 사이트에서 확인하세요` 를 뺌. 같은 결과의 `[일부] 더 오래된 거래가 남아 있습니다. 당근에서 직접 확인하세요: URL` 과 같은 말이었다 (#205)
- `jibsa guide` 의 `[실패]` 설명에 대체 경로로 찾은 경우를 넣어 `docs/common.md` 와 맞춤. 직방 단기임대를 지도로 다시 찾거나 직방 위치를 네이버로 찾은 경우다 (#205)
- 네이버 목록의 `[일부]` 안내를 다른 소스처럼 전체 수부터 말하도록 바꿈: `전체 38건 중 일부입니다` → `조건에 맞는 매물이 38건 있고, 그중 30건만 보여 줍니다` (단지·재개발 구역은 `곳`). `--limit` 이 최대값일 때도 수를 함께 알린다. 반경 검색의 수는 반경을 감싼 사각형 안의 서버 집계라 `약 1197건(반경을 감싼 사각형 안)` 처럼 알린다 (#206)
- 당근이 역·장소를 중심으로 반경 검색했다는 `[범위]` 안내에 반경을 넣음: `… 위치(역삼역)를 중심으로 반경 1km 안을 찾았습니다` (매물 검색·개발 사업·어린이집) (#206)
- `jibsa guide` 의 상가·사무실 줄에 네이버·당근 `-t 상가,사무실` 을 넣고 다방은 상가가 없다고 적음. 당근은 역 이름에 `--radius` 를 주면 `walk_minutes` 대신 `distance_km` 가 온다는 것과, 네이버 실거래는 평형 하나씩이라 단지 전체는 직방·당근으로 본다는 것도 적음 (#206)
- 조건에 맞는 매물이 없을 때 `조건에 맞는 매물은 이 0건이 전부입니다` 대신 `조건에 맞는 매물이 없습니다` 로 알림 (직방·네이버·당근, 당근 출퇴근 역별 안내도) (#207)
- `jibsa guide` 의 단기임대 줄에 월 단위 단기임대(직방 `room`·네이버·당근 `--trade 단기임대`, 다방은 `--condition 단기임대`)를, 통근 줄에 통근 시간 조건은 당근만 있다는 것을 적음 (#207)
- 직방 아파트 동 검색에 이웃 동 단지가 섞였다는 `[범위]` 안내를 `동 안에 아파트가 적으면 이웃 동 단지도 함께 줍니다` 에서 `그 동 단지 뒤에 이웃 동 단지를 이어서 주고, total 도 이웃 동까지 센 수입니다` 로 바꾸고, 이웃 동이 대부분인 쪽이면 이어 받아도 그 동 매물이 거의 없다고 알림 (#208)
- 당근이 찾지 못한 이름을 직방·네이버 지역 검색으로 찾았을 때 `[범위]` 안내에 `당근이 찾지 못해` 를 붙임 (`'양근리' 는 당근이 찾지 못해 직방 지역 검색으로 찾은 위치 …`) (#208)
- `jibsa guide` 의 당근 주변 동 설명을 `jibsa 가 빼지 않으니 동 안 매물만 필요하면 in_regions 로 가린다` 로, 같은 집 규칙에 `사용자가 상세 비교를 원하면 그 후보만 listing 으로 본다` 를 덧붙임 (#208)

### 수정

- 더 받을 결과가 있다는 안내에 태그가 없어 `[일부]` 대신 `[참고]` 로 나가던 문제 (직방 단지 매물·상가 가격 조건·실거래, 당근 단지 목록·단지 후보·실거래·학교 주변 시설·같은 동 단지) (#205)
- 뺀 사업·찾은 범위·대체 경로 안내 5곳에 태그가 없어 `[참고]` 로 나가던 문제. 당근 개발 사업에서 뺀 사업은 `[제외]`, 당근 출퇴근의 시간 모르는 역·역 수·시간 상한은 `[범위]`, 직방 단기임대를 지도로 다시 찾은 경우는 `[실패]` 로 붙인다. 단기임대는 지금 매물이 없는 곳도 지역 검색이 찾으므로, 이 경로를 타면 `jibsa 업데이트가 필요할 수 있습니다` 도 붙인다 (#205)
- 직방 상가 반경 검색에 가격 조건을 주면 `--limit` 에 잘린 매물이 반경 밖뿐이라 더 없는데도 `가까운 N건만 보여 줍니다` 안내가 붙던 문제 (#205)
- 직방 오피스텔 건물 매물에서 확인한 매물이 모두 빠지면 `앞의 0건만 보여 줍니다` 로 나오던 문제 (#205)
- 직방 오피스텔 건물 매물의 `[일부]` 안내가 오피스텔에는 없는 평형 조건을 좁히라고 해, 따라 하면 `--pyeong` 이 `INVALID_ARGUMENT` 로 막히던 문제. `거래 유형·방 구조·면적·가격 조건을 좁히세요` 로 알린다 (#205)
- 직방 단기임대·상가·오피스텔 건물 매물과 다방 단지 매물·인기 매물·단지 목록·분양·청약 일정·지역 순위가 `--limit` 이 이미 최대값인데도 `--limit 을 늘리거나` 로 안내하던 문제. 늘리면 `INVALID_ARGUMENT` 로 막혀 `--limit 의 최대값은 120입니다` (다방 인기 매물·지역 순위는 100, 청약 일정은 300) 로 알린다. 다방 지역 순위는 시·도·전국이면 범위를 좁히라고, 시·군·구면 `--order` 를 바꿔 반대쪽 끝을 보라고 알린다 (#205)
- 단지·재개발 구역 하나의 매물을 찾는데도 `--limit` 이 최대값이면 `조건·지역을 좁히세요` 로 안내하던 문제 (다방 단지 매물, 직방 아파트 단지 매물, 네이버 단지·재개발 구역 매물). 다방·직방은 `거래 유형·평형·가격 조건을`, 네이버 단지는 `거래 유형·평형·동·가격 조건을`, 네이버 재개발 구역은 `거래 유형·가격 조건을` 좁히라고 알린다 (#205)
- 당근 단지 후보·지역 단지·단지 매물이 다음 페이지를 받지 못해(빈 페이지·커서 없음·되풀이) 멈췄을 때도 `--limit 을 늘리면`·`--limit 의 최대값은` 안내가 붙던 문제. `--limit` 을 늘려도 더 받지 못하므로 멈췄다는 `[일부]` 안내만 남긴다. 단지 매물은 같은 커서를 되풀이받으면 같은 페이지를 6번까지 다시 받았고, 커서가 비면 안내 없이 멈췄다 (#205)
- 당근 목록이 다음 페이지를 받지 못해 멈췄다는 안내를 `당근이 … 다음 페이지가 있다고 하면서 이어 받을 페이지를 주지 않아 N곳에서 멈췄습니다. API 가 바뀌었을 수 있어 jibsa 업데이트가 필요할 수 있습니다` 로 맞춤 (단지 후보·지역 단지·단지 매물·실거래·출퇴근 역 목록). 목록 끝은 늘 다음 페이지가 없다고 오므로 응답이 바뀐 것일 수 있다. 출퇴근 역 목록은 다음이 있다면서 역이 없는 페이지를 주면 안내 없이 끝냈다 (#205)
- 당근 출퇴근 역 목록이 다음 페이지를 받지 못해 멈췄을 때 `역 N곳 중 가까운 10곳 주변만 찾았습니다` 에 `이상` 이 빠지던 문제 (#205)
- 반경 검색인데 `--limit` 이 최대값이면 `조건·지역을 좁히세요` 로 안내하던 문제 (직방 아파트 반경, 네이버 반경 매물·반경 단지·반경 재개발 구역). 직방 원룸·상가·단기임대처럼 `조건·반경을 좁히세요` 로 알린다. `--limit` 이 최대값이 아닐 때도 좁힐 것이 늘 `조건` 이던 것을 최대값일 때와 같게 맞춤 (직방 아파트·단지 매물, 네이버 목록·단지 매물) (#205)
- 다방 인기 매물이 동 하나의 순위인데 `조건·지역을 좁히세요` 로 안내하던 문제. `매물 유형·거래 유형 조건을 좁히세요` 로 알린다 (#205)
- 직방 상가 검색에 가격 조건을 주고 일부만 보여 줄 때 `[일부]` 안내에 더 보는 법이 없던 문제. `--limit` 을 늘리라고(이미 최대값이면 그렇다고) 하고 좁힐 조건을 알린다. 후보 조회 상한에 걸렸으면 가격 조건은 좁혀도 같은 가까운 후보만 다시 보므로 `거래 유형·업종·반경을 좁히세요` 로 알리고, 상한이 `--limit` 의 5배(최소 60건)라 `--limit` 을 늘리면 더 확인한다는 것도 알린다 (#205, #206)
- 직방 단기임대가 함께 찾는 동·구(성수동1가·2가, 성남시의 구) 중 한 곳만 지역 검색에서 찾지 못해도 대체 경로 안내에 모두를 합친 이름을 대던 문제. 처음 못 찾은 곳을 댄다. 세종의 동은 `세종특별자치시 세종 반곡동` 이 아니라 `세종특별자치시 반곡동` 으로 댄다 (#205)
- 당근 출퇴근 역 목록이 같은 페이지를 되풀이해 멈추면 멈춤 안내의 역 수가 같은 역을 두 번 세던 문제 (`reachable_stations` 51 에 `101곳에서 멈췄습니다`). 또 가까운 역 10곳을 받기 전에 멈추면 찾는 역이 줄었는데도 `[참고]` 로 알리던 문제. 그때는 `[일부]` 로 알린다 (#205)
- 당근 단지 매물이 같은 페이지를 되풀이받아 멈추면 멈춤 안내의 매물 수가 되풀이된 페이지까지 세던 문제. 받은 서로 다른 매물 수로 알린다 (#205)
- 당근 단지 후보·지역 단지·단지 매물이 같은 페이지를 되풀이받았을 때 그 페이지가 `--limit` 의 남은 몫을 채우면 멈춤 대신 `--limit` 에 닿았다고(`더 보려면 --limit 을 늘리거나 …`) 알리던 문제. 되풀이된 페이지는 세기 전에 멈춘다 (#205)
- 당근 실거래의 마지막 페이지가 다음 페이지가 없다고 하면서 요청한 커서를 그대로 돌려주면, 끝난 목록을 `has_more: true` 와 멈춤 안내로 내고 그 페이지의 거래를 빼던 문제 (#205)
- 당근 단지 후보·지역 단지·단지 매물·실거래·출퇴근 역 목록이 다음 페이지가 있다고 한 뒤 페이지 정보 없이(null) 응답하면 안내 없이 `has_more: false` 로 끝내, 받은 일부를 전부처럼 내던 문제. 멈췄다고 알린다 (#205)
- 당근 `real-price --item` 이 거래가 더 남았는데도(페이지가 멈췄거나 전월세 1200건 안에 그 유형이 없을 때) `이 매물 건물의 전세 실거래가 없습니다` 를 붙이던 문제 (#205)
- 당근 실거래가 `--limit 1200` 에서 거래가 더 남으면 `--limit 을 늘리면` 으로 안내하던 문제 (서버가 요청보다 많이 줄 때). 당근 사이트 확인을 안내한다 (#205)
- 다방 `search complexes` 를 역·대학으로 찾았는데 단지가 더 있으면 `지역을 좁히세요` 로 안내하던 문제. `반경을 좁히세요` 로 알린다 (#205)
- 당근 실거래에 `--years` 를 줬는데 기간 시작일에 닿기 전에(24페이지 상한 등) 멈추면 `더 오래된 거래가 남아 있습니다` 로 안내해, 요청한 기간 안의 거래가 빠진 것을 기간 밖 거래로 읽게 하던 문제. `요청한 기간(2025-11-11부터) 중 2026-01-10 이전 거래는 받지 못했습니다` 로 알린다 (#206)
- 당근 출퇴근이 가까운 역 10곳만 찾았을 때 `더 멀리 보려면 조건을 좁히거나` 로 안내하던 문제. 찾는 역은 조건과 상관없이 가까운 10곳이라 `더 먼 역은 jibsa daangn search listings <역 이름> 으로 그 역 주변을 따로 찾으세요` 로 알린다 (#206)
- 당근 단지 목록·지역 실거래·지역 후기에 역 이름(`강남역`)을 주면, 이름에 그 역이 들어간 단지가 있어 `REGION_NOT_FOUND` 의 `hint` 가 `'강남역' 은 동·구가 아니라 단지 이름입니다` 라고 하던 문제. 역 이름이라고 알리고 역이 있는 동 이름으로 찾으라고 한다. 단지 목록은 다방·네이버 `search complexes <역 이름>` 도 알린다 (#206)
- 다방 지역 순위가 시·도·전국에서 `범위를 좁히세요` 로만 안내해 무엇을 좁히라는지 알 수 없던 문제. `범위를 시·군·구(예: 강남구)로 좁히세요` (전국은 `시·도(예: 서울)나 시·군·구로`) 로 알린다 (#206)
- 네이버 `trend` 의 최근 몇 주 실거래 건수가 신고가 덜 모여 적게 나오는데 안내가 없어, 줄어드는 끝을 거래가 줄었다고 읽게 하던 문제. 실거래는 계약 뒤 30일 안에 신고해 최근 4주쯤은 적게 나온다고 `[참고]` 로 알린다 (#207)
- `jibsa guide` 가 `naver market-price <단지>` 로 적어 그대로 부르면 `--pyeong` 이 없어 `INVALID_ARGUMENT` 로 막히던 문제. `--pyeong <평형 번호>` 를 넣었다. `○가` 동을 합쳐 찾는 것은 매물 검색이고, 네이버 재개발 구역 검색처럼 첫 동만 찾는 명령도 있다고 적었다 (#207)
- 당근 `preschools` 에 `-t` 로 유형을 골라도 안내가 `조회된 어린이집·유치원 N곳 중` 이라 하던 문제. 고른 유형 이름(`조회된 어린이집 N곳 중`)으로 알린다 (#207)
- 다방 `--condition 단기임대` 를 거래 유형 없이 주면 다방이 이 조건을 월세에만 걸어 단기임대가 아닌 전세 매물이 섞이던 문제 (정자동 10건 중 전세 7건). 월세만 찾고 `[거래]` 로 알린다. `--trade` 에 월세가 없으면 입력 오류다 (#207)
- `jibsa guide` 가 `next` 가 없으면 조건을 나눠 찾으라고만 해 `--limit` 을 늘리라는 `[일부]` 안내와 어긋나 보이던 문제. `notes` 대로 `--limit` 을 늘리거나(최대값 전까지) 나눠 찾는다고 적었다. `네이버가 가장 엄격하다`·`세 소스 중` 도 소스별 요청 간격(네이버 1초, 당근·다방 0.5초, 직방 0.2초)으로 바로잡았다 (#208)
- 당근 `region-reviews` 의 후기 많은 단지(`top_complexes`)가 구 전체 값인데 안내가 없어 동의 단지로 읽히던 문제. `송파구 전체 기준이라 잠실동 밖 단지도 들어 있습니다` 로 알린다 (#208)
- 다방 매물의 다른 동·반경 밖 `[제외]` 안내가 더 받을 매물이 없어도 `(뺀 만큼 다시 채우지 않음)` 이라 하던 문제. 그때는 `(더 받을 매물 없음)` 이다 (#208)
- 다방 아파트 동 단지 목록이 동을 덮는 사각형 목록에서 그 동만 남겨 `--limit` 을 늘려도 다른 동이 대부분인데 `지역을 좁히세요` 로 안내하던 문제. 사각형 목록 중 이 동이 몇 곳인지와 당근·네이버 `search complexes <동>` 을 알린다 (#208)
- 당근 문서 `기본값과 조회 한도` 표에 `search locations` 단지 후보 기본값이 120으로 적혀 있던 문제. 0.9.0 에서 20으로 줄였는데 표만 그대로였다 (#205)
- README 빠른 시작에 `jibsa install-browser` 가 빠져 있어 그대로 따라 하면 `BROWSER_UNAVAILABLE` 로 멈추던 문제. 설치 뒤 Chromium 을 받는 줄을 넣었다 (#203)

## 0.11.0 — 2026-11-10

### ⚠️ 호환 깨짐

- 모든 조회 명령이 요청을 사이트 화면을 실제로 연 Chromium 으로 보냄. 처음 한 번과 jibsa 를 업데이트한 뒤 `jibsa install-browser` 로 Chromium(내려받기 약 170MB, 풀면 약 400MB)을 받아야 하고, 없으면 `BROWSER_UNAVAILABLE` 로 멈춘다 (설치 스크립트는 대신 받는다). jibsa 패키지도 브라우저 드라이버(patchright) 등이 더해져 설치 크기가 약 200MB 늘어난다. Chromium 이 돌지 않는 환경(Alpine 리눅스 등)에서는 쓸 수 없다. 리눅스에서 시스템 라이브러리가 없다고 하면 안내된 `sudo … install-deps chromium` 을 한 번 실행한다 (#198)
- 라이브러리로 쓸 때: client 의 `user_agent` 옵션을 뺌. UA 는 브라우저가 맡는다. 넘기면 검증 오류가 나니 지운다. `verify`·`proxy` 는 브라우저가 쓴다. `url_schema` 는 `'https'` 만 받는다 (https 첫 화면에서 보내는 http 요청은 브라우저가 막는다). client 마다 Chromium 을 하나씩 띄우므로 `with`·`close()`(비동기는 `aclose()`)로 닫는다. 닫지 않으면 프로세스가 끝날 때까지 Chromium 이 남는다. 비동기 client 로 동시에 보낸 요청도 차례로 나간다. `timeout` 은 httpx 처럼 연결·읽기 단계마다가 아니라 요청 하나의 연결부터 본문 끝까지 전체 시간이다 (#198)
- TLS 인증서를 Chromium 이 검사해 `SSL_CERT_FILE`·`SSL_CERT_DIR` 환경 변수를 더 이상 보지 않는다. Chromium 은 내장 목록과 OS 에 설치된 인증서(Windows 인증서 저장소, macOS 키체인, Linux `~/.pki/nssdb`)를 믿으므로, 회사 인증서는 OS 에 설치한다. 인증서를 믿지 못하면 재시도 없이 `NETWORK_ERROR` 이고 `hint` 가 OS 에 설치하라고 안내한다 (#198)

### 추가

- `jibsa install-browser`: 요청을 보낼 Chromium 을 받고(이미 있으면 건너뜀) 한 번 띄워 본 뒤 버전·경로를 JSON 으로 쓴다. 내려받기 진행은 터미널에서 실행했거나 `jibsa --verbose install-browser` 로 실행했을 때만 보이고, 내려받지 못하면 원인을 에러 JSON 의 `output` 에 싣는다. 설치 스크립트도 이 명령으로 Chromium 을 받는다 (#198)
- 에러 코드 `BROWSER_UNAVAILABLE`(Chromium 이 없거나 띄우지 못함, 모든 소스가 같이 실패)·`BROWSER_INSTALL_FAILED`(Chromium 을 내려받지 못함) (#198)
- 에러 JSON 의 `blocked: true`: 사이트 첫 화면이 접속을 막았을 때(401·403·451) 붙는다. 업데이트로 풀리지 않으니 다른 소스를 쓴다 (#198)
- 설치 스크립트: Windows 는 PowerShell 에서 `irm https://raw.githubusercontent.com/Rukkakka/jibsa/main/scripts/install/install.ps1 | iex`, macOS·Linux 는 `curl -LsSf https://raw.githubusercontent.com/Rukkakka/jibsa/main/scripts/install/install.sh | sh` 한 줄로 uv·jibsa 설치, PATH 등록, Windows 한글 출력 설정(`PYTHONUTF8=1`), Codex·Claude Code 지침 한 줄까지 한다. 다시 실행하면 최신 버전으로 올린다. Windows 에서 uv 를 설치한 창을 새로 열지 않으면 `uv`·`jibsa` 를 못 찾았고, PATH 가 바뀌기 전에 연 창에서 켠 Codex 도 jibsa 를 못 찾았다. Windows 스크립트는 지금 창에도 PATH 를 넣어 그 창에서 바로 쓸 수 있다 (#190)

### 변경

- 요청이 일반 Chrome 과 같은 헤더·쿠키·TLS 로 나감. 사이트가 브라우저 검사를 강화해도 버티려는 것이다. 사이트 첫 화면은 30분에 한 번 열고(그 명령은 2~3초 더 걸린다), 그 사이 명령은 사이트가 심은 쿠키(`<상태 폴더>/browser/`, 로그인 쿠키 아님)를 이어 써 0.3초쯤만 더 걸린다. 30분 뒤 첫 화면을 다시 열 때도 사이트가 심은 방문자 쿠키(만료 시각이 있는 것)는 이어 써, 30분마다 새 방문자로 보이지 않는다. 첫 화면이 스스로 부르는 사이트 요청과 브라우저가 보내는 CORS 사전 요청(OPTIONS, 직방·당근)도 요청 제한에 든다. 첫 화면 문서가 40초 안에 오지 않으면 다시 열지 않고 `NETWORK_ERROR`(사이트 밖 광고·분석 스크립트가 늦으면 10초만 기다리고 넘어간다), 차단 응답(401·403·451, `blocked: true`)이거나 그 밖의 4xx, 보안 확인 화면 같은 다른 주소로 넘어가면 `UPSTREAM_ERROR` 로 멈춘다. 첫 화면 문서가 서버 오류(5xx)면 재시도한 뒤 `UPSTREAM_ERROR` 이고 `hint` 가 사이트 장애이니 잠시 뒤 다시 부르라고 한다. Chromium 을 띄우지 못하면 재시도 없이 `BROWSER_UNAVAILABLE` 이다. 당근이 못 찾은 장소 이름을 직방으로 찾다가 직방 첫 화면이 막혀도 네이버로 넘어간다 (#198)
- 프록시는 브라우저가 쓴다. `HTTPS_PROXY`·`ALL_PROXY`·`NO_PROXY` 환경 변수를 읽고, 없으면 OS 프록시 설정을 따른다. SOCKS 프록시(`socks5h://` 포함)도 쓸 수 있지만 아이디·비밀번호가 있는 SOCKS 프록시는 Chromium 이 지원하지 않는다. 프록시 주소가 잘못됐거나 쓸 수 없거나 프록시에 연결하지 못하면 재시도 없이 `NETWORK_ERROR` 이고 `hint` 가 프록시 설정을 가리킨다 (#198)
- 보장하는 Python 을 3.11~3.14 로 명시함. CI 가 Windows·macOS·Linux 에서 네 버전을 모두 확인한다. 3.15 는 확인한 뒤 보장한다. 패키지의 `requires-python` 에는 상한을 두지 않는다 (두면 새 Python 의 pip 가 옛 버전을 에러 없이 받는다). 설치 스크립트는 보장 범위의 Python 으로 설치하고, Python 이 없으면 uv 가 그 범위에서 받는다 (#199)
- 네이버 요청 제한을 분당 30회 → 60회, 429 뒤 쿨다운 15분 → 5분으로 바꿈. 첫 화면을 열 때 네이버 페이지가 스스로 부르는 요청(약 20건)이 분당 상한에 들어 그만큼 늘렸다. 쿨다운 뒤에는 사이트 화면을 연 지 30분 안이면 요청 1건으로 풀렸는지 본다 (#198)

### 수정

- 당근에서 이름으로 위치를 찾는 명령(`search listings --radius`·`search commute`·`developments`·`preschools`)이 당근 요청 제한 중이면 직방·네이버로 위치를 찾느라 요청을 더 보낸 뒤 `RATE_LIMITED` 로 끝나고, 주소(`테헤란로 152`)는 `REGION_NOT_FOUND` 로 잘못 알리던 문제. 이제 바로 `source` 가 `daangn` 인 `RATE_LIMITED` 로 멈춘다 (#198)
- 당근에서 이름으로 위치를 찾다 직방·네이버 모두 실패했을 때 에러가 원인과 상관없이 늘 `status` 없는 `UPSTREAM_ERROR` 이던 문제. 이제 직방이 실패한 원인대로 연결 실패는 `NETWORK_ERROR`, 서버 오류는 `status`, 첫 화면 차단은 `blocked: true` 를 알린다 (`source` 는 그대로 `zigbang`) (#198)

## 0.10.0 — 2026-11-02

### 변경

- `jibsa guide`: 사용자가 사이트를 정하지 않은 매물 부탁은 네 소스를 모두 찾고, 찾은 소스와 못 찾은 소스·이유를 답에 적으라고 안내함. 사이트 이름 없는 부탁 6번 중 3번이 한두 소스를 빼먹었고 그중 2번은 빠진 소스를 말하지 않았다. 소스별 옵션 표에 '방 2개 이상'(전부 적은 값)·'아파트 공급 30평대'·면적 기준(전용·공급)과 '유형을 정하지 않은 집' 명령을 더하고, 역 이름의 기본 범위가 당근(역 주변 목록)·다방(다방 역 반경)은 다르니 견줄 때 `--radius` 를 맞추라고 고침. 표의 `--room 투룸` 예시를 그대로 옮겨 방 3개 이상을 빼거나, 소스마다 면적 기준을 다르게 환산했다. `url` 은 글자 그대로 옮기고, 같은 집인지 가리려고 상세를 여러 번 부르지 말라는 안내도 더함 (#181)
- 지역·장소·학교·단지 이름을 받는 명령이 따옴표 없이 띄어 쓴 이름(`송파구 신천동`)을 한 이름으로 받음. 전에는 'unexpected extra argument (신천동)' 로 막고 `--help` 만 안내해, `REGION_AMBIGUOUS` 힌트의 이름을 따옴표 없이 옮긴 호출이 한 번 더 들었다 (#182)

### 수정

- 당근 `--city` 에 시와 구를 띄어 쓴 이름(`'성남시 분당구'`)을 주면 당근 구 이름과 같은데도 `REGION_NOT_FOUND` 이던 문제. 마디마다 맞는 곳을 고른다 (#183)
- `jibsa guide common`·`jibsa guide <소스>` 로 출력한 문서의 다른 문서 링크가 설치본에서 열리지 않던 문제. GitHub 전체 주소로 쓴다 (#179)

## 0.9.0 — 2026-10-31

### ⚠️ 호환 깨짐

- 당근 `search commute` 의 `--household-min`·`--household-max`·`--parking-min` 을 뺌. 당근 역 주변 매물 목록이 이 조건을 받지 않아 주어도 걸리지 않았다. 단지 조건은 `search listings <역 이름> --radius 1 -t 아파트 --household-min …` 으로 찾는다 (#169)

### 추가

- 다방 `search listings room`·`villa`·`officetel`·`apt` 에 `--details`: 앞 30건에 상세의 사용승인일(`approved_at`)과 건물 용도(`residence_type`)를 붙인다 (매물당 요청 1회). 목록에 사용승인일이 없어 `--built-within`(연도로 센다) 결과를 날짜로 따지려면 매물마다 `listing` 을 불러야 했다. `--built-within` 과 함께 주면 오늘 기준 그 햇수가 넘은 매물을 `notes` 로 짚는다 (#170)
- 네이버 `search listings`(지역·단지·재개발 매물)에서 같은 집을 중개사 여럿이 올려 네이버가 한 매물로 묶은 매물에 `realtor_count`(중개사 수)와, 중개사마다 호가가 다르면 묶음의 호가 범위 `price_range_manwon`·`deposit_range_manwon`·`rent_range_manwon` 을 붙임. 가격 필드는 대표 매물 하나의 호가라 최고 호가가 보이지 않았고(헬리오시티 84㎡: 대표 30억, 묶음 30억~33억), 네이버 가격순이 묶음 범위로 정렬해 순서가 어긋나 보였다. 가격순에 그런 매물이 있으면 `notes` 로 알린다. 이 필드들은 `--fields` 로 고르지 않아도 늘 나온다. 네이버 가격 조건은 대표 호가로만 걸려 묶음 안의 다른 호가를 찾지 못하므로, 가격순 `notes` 가 그 결과의 묶음 끝 호가를 값으로 알린다 (#168)
- 당근 `real-price --years N`: 최근 N년 안 계약만 받고 그 앞 거래가 나오면 멈춘다. 결과에 기간 시작일 `since` 가 붙는다. 기간 옵션이 없어 3년치를 보려면 `--limit 1200` 으로 오래된 거래까지 모두 받아야 했다 (헬리오시티 84㎡ 매매: 938건 → 468건) (#169)
- 직방 `search listings stay --details`: `--check-in`/`--check-out` 과 함께 주면 앞 30건에 그 기간의 실제 비용(`period_cost`, 청소비·직방 이용료·장기 할인 포함)을 붙인다 (매물당 요청 1회). 목록 금액과 가격순은 주당 요금이라 주당 요금 × 주 수로 기간 비용을 어림하면 틀렸다. 날짜를 주고 `--details` 를 빼면 `notes` 로 알린다 (#171)

### 변경

- 당근 `region-real-price`·`search complexes`·`region-reviews` 에 단지 이름을 주어 지역을 못 찾으면(`REGION_NOT_FOUND`) `hint` 가 그 이름의 단지 ID·주소와 `complex`·`real-price`·`search listings --complex` 를 알림 (단지 후보 요청 1회). 전에는 동·구 이름으로 다시 찾으라고만 해 단지 ID 를 찾는 데 호출이 한 번 더 들었다 (#169)
- 당근 `search locations <단지 이름>` 의 단지 후보 기본 수를 120 → 20 으로 줄임. 당근은 이름이 조금 비슷한 단지까지 100곳 넘게 줘 찾는 단지는 앞쪽에 있고 나머지는 토큰만 썼다 ('헬리오시티': 약 4,900 → 1,000토큰). 더 있으면 `notes` 가 `--limit` 을 늘리라고 알린다 (#169)
- 인자 하나에 공백과 옵션이 함께 든 호출(셸 변수에 담아 나뉘지 않은 `'--complex 111515 --pyeong 8,9'`, `'대치동 --city 강남구'`)을 요청 전에 `INVALID_ARGUMENT` 로 막고 셸이 나누지 않았다고 알림. 전에는 없는 옵션·없는 지역으로 끝나 '--help 를 보라' 만 안내했고, 지역 인자는 요청까지 보냈다 (#167)
- 당근 `search listings`·`search commute` 에 `--with-manage-cost` 를 주면 `notes` 에 관리비가 `null` 이어도 당근이 월세+관리비로 걸렀다는 안내를 붙임 (`--details` 를 주면 관리비가 채워져 붙이지 않는다). 관리비를 모른다며 조건에 맞는 매물을 빼는 일이 있었다 (#169)
- 네이버·다방 `real-price` 에 거래가 있으면 `notes` 에 전용면적이 같은 다른 평형에도 같은 거래가 들어 있다는 안내를 붙임. 평형마다 받아 더하면 몇 배로 세었다 (헬리오시티 84㎡대 네이버 평형 5개: 1,309건 → 실제 329건) (#168, #170)
- 직방 `search listings room --details` 가 건물 용도와 함께 같은 상세의 사용승인일(`approved_at`)도 채움. 직방에는 연식 조건이 없어 연식을 확인하려면 매물마다 `listing` 을 따로 불러야 했다 (#171)

### 수정

- 네이버 `search listings`·`search complexes`·`search redevelopment` 에 `○가` 로 나뉜 동(성수동)을 `--radius`·가까운순으로 주면, 반경 안의 성수동2가 결과가 함께 나오는데도 '성수동1가만 찾았습니다. 2가는 각각 검색하세요' 라고 알리던 문제. 이제 1가 중심 반경으로 찾았다고 알린다 (#168)
- 다방 `search listings` 의 `--built-within` 이 날짜가 아니라 사용승인 연도로 걸리는데(2026년에 `10` 이면 2016-02 승인도 들어온다) 도움말·문서는 '햇수 이내' 라고만 하던 문제. 이제 `notes` 에 연도 기준(`2016-01-01 이후 승인`)과 오늘 기준 날짜(`2016-10-31 이후 승인`)를 함께 알린다 (#170)
- 당근 `search listings` 에 역 이름과 `--household-min`·`--household-max`·`--parking-min` 을 함께 주면 이 조건이 걸리지 않은 매물(도시형·소규모 단지)을 '조건에 맞는 매물' 로 주던 문제. 이제 이 조건을 받는 역 위치 반경 검색으로 찾고 `notes` 로 알린다 (#169)
- 네이버 `search listings` 를 가까운순이 아닌 정렬(`--sort 가격낮은순` 등)로 반경 1.5km 넘게 찾거나 `search complexes` 를 반경 1.5km 넘게 찾으면 반경 가장자리 매물·단지가 빠지던 문제. 빠진 매물만 조건에 맞으면 '0건이 전부입니다' 라고 알렸다 (강남역 2km 아파트 전세 5억 이하 500세대 이상: 0건 → 6건, 강남역 3km 아파트 단지: 242곳 → 1,048곳) (#168)

## 0.8.0 — 2026-10-30

### ⚠️ 호환 깨짐

- 다방 `sale` 의 `schedules[]` 에서 끝이 없는 한 시점 단계(모집공고·당첨자발표·입주예정일)는 `end: null` 대신 `end` 키를 뺌. 하루짜리 청약은 전처럼 `end` 가 `start` 와 같다. 키가 없으면 끝이 해당 없는 단계로 읽는다 (#152)
- 당근 `search listings`(동·역·반경)·`search commute` 에서 작성자가 주소를 숨긴 매물의 `distance_km` 를 `null`(모름)로 줌. 당근이 이런 매물에 실제 위치가 아닌 좌표를 주어 역 앞 도보 2분 매물이 1km 넘게 떨어진 것처럼 나왔다. 거리로 고르거나 정렬할 때 `null` 은 거리를 모르는 매물로 다룬다 (`notes` 가 몇 건인지 알린다) (#155)

### 수정

- 다방에 '광주시 송정동' 처럼 경기도 광주시의 동을 주면 전남광주통합특별시 광산구 송정동도 후보로 잡아 `REGION_AMBIGUOUS` 로 멈추던 문제. 이제 경기도 광주시 송정동을 찾는다 ('광주 송정동'·'광주시 광산구 송정동' 은 광산구) (#152)
- 다방에 '연세대학교 원주캠퍼스' 처럼 띄어 쓴 캠퍼스 이름을 주면 `REGION_NOT_FOUND` 가 나던 문제 (#152)
- 다방이 요청 형식 오류에 주는 400 을 없는 매물·단지·분양(`LISTING_UNAVAILABLE`·`NOT_FOUND`)으로 알리던 문제. 사유가 '존재하지 않…' 일 때만 없는 ID 로 보고, 다른 400 은 `UPSTREAM_ERROR` 로 알린다 (#152)
- 다방 `search sales` 에 시·도 이름(서울)을 주면 요청을 1회 보낸 뒤에야 `REGION_NOT_SUPPORTED` 로 막던 것을 요청 없이 막음 (#152)
- 직방 `search listings apt`·`stay` 에 '시' 를 빼고 쓴 구 있는 시 이름('성남'·'고양' 등)을 주면 첫 구만 찾고 다른 구가 빠졌다는 안내도 없던 문제. 이제 '성남시' 와 똑같이 모든 구를 합쳐 찾는다 (#153)
- 직방 `search listings room --details` 에서 상세를 붙이지 않는 31번째부터의 매물에 `residence_type` 키가 빠져 해당 없음으로 읽히던 문제. 이제 `null`(모름)로 준다 (#153)
- 네이버 `search listings`·`search complexes`·`search redevelopment`·`trend` 에 `○가` 로 나뉜 동을 '동' 없이 주면('성수'·'부민') 1가만 찾고 안내도 없던 문제. 이제 '성수동' 과 똑같이 1가·2가를 합쳐 찾거나 나뉜 동이라고 알린다 (#154)
- 네이버 `real-price`·`market-price` 에 없는 단지 번호나 평형 정보가 없는 단지를 주면 따를 수 없는 `hint`('--pyeong 없이 조회하세요', `--pyeong` 은 필수)를 주던 문제. 이제 `jibsa naver complex <번호>` 로 단지와 평형 번호를 확인하라고 알린다 (#154)
- 당근 `region-real-price`·`search complexes`·`region-reviews` 에 시·도 이름(서울·경기도)을 주면 첫 동 하나(종로구 부암동)로 조회하던 문제. 이제 수원시처럼 `REGION_AMBIGUOUS` 로 그 시·도의 구 예를 알린다 ('광주' 는 경기도 광주시를 시 이름 그대로 찾으라고 따로 알린다) (#155)
- 당근 `search listings` 를 `--next` 로 이어 받은 마지막 쪽에서 '조건에 맞는 매물은 이 N건이 전부입니다' 라고 이번 쪽만 세어 알리던 문제 (#155)
- 당근 `search listings --details` 에서 상세를 보니 거래가 끝나 뺀 매물 안내가 `[제외]` 가 아니라 `[참고]` 로 나가던 문제 (#155)

## 0.7.0 — 2026-10-27

### 추가

- 다방(`jibsa dabang`)을 네 번째 소스로 추가. 매물 찾기 `search listings room`(원룸·투룸)·`villa`(주택·빌라)·`officetel`·`apt` (동·역·대학 이름 또는 좌표, `--next` 이어 받기), 장소 후보 `search locations`, 단지 목록 `search complexes`, 단지 정보 `complex`(배정 초등학교와 가까운 중·고등학교의 학급당 학생 수·진학 인원 포함), 학교 상세 `school`(학교알리미 공시: 학급당·교원당 학생 수와 시·도 평균, 중학교 특목고·자사고 진학률, 고등학교 대학 진학률), 단지 매물 `search listings --complex`, 실거래가 `real-price`(단지 없는 매물은 `--listing`), 시세 흐름 `price-trend`, 매물 상세 `listing`(매물번호도 받는다), 동네정보 `neighborhood`(매물 수·거래량·평균가·인구와 순위, 학교·편의·교통·안전 시설 수), 동 안 인기 매물 `popular-listings`, 매물·단지 둘레 역·버스·시설 `nearby`, 역 둘레 평균 매물가 `station-prices`, 분양 단지 `search sales`·`sale`·청약 일정 `sale-schedule`, 전국 조회·거래 순위 `trending-complexes`·`trade-rankings`, 시군구·시도·전국 안 동·단지 순위 `region-ranking`(부동산: 평균가·전세가율·신고가 단지 등, 동: 진학률·학원 수·인구 증감·편의·교통·안전 시설 수). 로그인 없이 다방 웹이 쓰는 API 를 부른다. 요청 제한은 0.5초 간격·분당 60회·429 뒤 5분이다 (`jibsa limits`) (#144)

### 변경

- 당근 `trending-complexes` 가 빈 목록이면 `notes` 에 이른 아침엔 자주 비니 낮에 다시 불러 보라는 안내를 더함. 같은 동도 때에 따라 0곳에서 20여 곳까지 달라진다. 도움말·문서의 '9곳쯤 준다' 도 고침 (#142)

## 0.6.0 — 2026-10-24

### ⚠️ 호환 깨짐

- 당근 `--with-manage-cost` 를 월세 범위 없이 주면 `INVALID_ARGUMENT` (exit 2). 혼자서는 아무것도 거르지 않았다. `--rent-min`·`--rent-max` 와 함께 준다 (#133)
- 해당 없는 값을 `null` 대신 키를 빼서 줌: 당근 `compare` 최근 실거래(매매의 `deposit_manwon`·`rent_manwon`, 전월세의 `price_manwon`), 당근 세종 지역의 `name2`(`""` 였다), 네이버 `redevelopment --trade` 의 `article_counts` 에서 고르지 않은 거래 유형(`0` 이었다). 키가 없으면 해당 없음으로 읽는다 (#133)

### 변경

- 당근 `search commute` 의 `--limit` 기본값을 역당 20건에서 5건으로 낮춤. 역을 최대 10곳 찾아 기본값으로 부르면 매물이 200건 가까이(8만 자 넘게) 나와 셸 출력이 잘렸다. 더 보려면 `--limit` 을 준다 (#133)
- `jibsa guide`(LLM 가이드)를 약 15% 줄임 (9,948자 → 8,454자). 명령의 `--help`·소스 문서에 있는 설명과 두 번 적힌 문장을 뺐다. 만원 값을 사용자에게 억·만 원으로 옮겨 쓰라는 규칙과 예시, 들여쓰기로 나오면 `--compact` 를 붙이라는 안내를 더했다 (#134)
- 네이버 `search listings --complex`·`complex`, 직방 `search listings --complex` 의 `--pyeong` 이 다른 목록 옵션처럼 쉼표를 받는다 (`--pyeong 7,8,19`) (#134)
- `jibsa guide <소스>` 의 절 이름을 따옴표 없이 여러 단어로 줘도 읽는다 (`jibsa guide daangn search listings`) (#134)
- 하위 명령을 빼먹은 호출(`jibsa zigbang search listings 역삼동`)의 에러 `hint` 가 `--help` 안내에 더해 하위 명령 목록과 (지역 이름을 줬으면) 예시를 준다. 상세·실거래처럼 매물 검색이 아닌 명령에 없는 옵션을 준 호출(`listing … --fields`, `naver real-price … --limit`)은 이 명령의 옵션을 알린다. 하위 명령의 옵션을 명령 이름보다 앞에 준 호출(`jibsa --compact daangn school …`)은 명령 뒤에 주라고 알린다. 네이버 `search listings` 의 단지·재개발 모드에 받지 않는 옵션을 준 호출은 그 모드가 받는 옵션을 알린다 (단지 매물을 면적으로 고르려면 `--pyeong`) (#134)
- 없는 ID 의 `LISTING_UNAVAILABLE` `hint` 가 매물을 빼라고만 하지 않고 다른 소스에서 받은 ID 인지 먼저 확인하라고 안내한다 (#134)
- 결과에 1억 이상 금액이 있으면 `notes` 에 그 결과의 값으로 억 환산 예시를 붙인다 (`[참고] 금액은 만원이다: 440000 = 44억 원, 439000 = 43억 9,000만 원`). 실거래 `440000` 을 `4억 4,000만 원` 으로 옮기는 실수가 잦았다 (#135)
- `jibsa guide naver real-price` 에 네이버가 같은 거래를 면적이 다른 평형 여러 곳에 함께 주기도 한다는 주의를 더함. 평형별 시세는 당근 `real-price` 의 거래별 `area_m2` 로 확인한다 (#134)

### 수정

- 429 로 쿨다운이 걸려도 그 전에 차례를 받아 기다리던 다른 jibsa 프로세스가 막힌 소스로 요청을 보내던 문제. 이제 `RATE_LIMITED` (`reason: cooldown`) 로 끝낸다 (#131)
- 네이버 `search listings --complex` 에 없는 단지 번호를 주면 `NOT_FOUND` 대신 '0건이 전부' 라고 하던 문제 (단지 번호로 찾아 0건이면 단지가 있는지 확인하느라 요청이 1~2회 더 든다) (#133)
- 네이버 `○가` 동(성수동 → 1가·2가) 매물 검색에서 뒤 동의 매물이 적으면 남은 몫을 앞 동이 받지 않아 `--limit` 보다 적게 주고 '전부' 와 `[일부]` 안내가 함께 나오던 문제 (#133)
- 네이버 번지 주소('신사동 535-1')·`○가` 동('성수동') 위치 찾기가 주소 검색을 한 번 더 보내던 문제 (#133)
- `--next` 가 같은 조건을 다르게 적은 옵션(`-t 원룸,오피스텔` 과 `-t 원룸 -t 오피스텔`, 쉼표 뒤 공백, 값 순서를 바꾼 `-t 오피스텔,원룸`)을 다른 검색이라며 막던 문제 (#134)
- 직방 여러 `○가` 동 아파트 검색(`apt 문래동`)을 `--next` 로 이어 받으면 앞 결과의 매물이 다시 나오던 문제 (#133)
- 매물을 다 받고 일부를 뺐을 뿐인데 `[일부]` 안내('매물이 더 있습니다', '--limit 의 최대값')가 붙던 문제 (직방 `room`·`apt`·`store`·`stay`·`--complex`, 직방 아파트 반경 검색은 `has_more` 도 true 였다). 반대로 네이버 단지 매물·지역 단지·재개발 구역 목록에서 1건만 빠져도 더 있다는 `[일부]` 안내가 사라지던 문제 (#132)
- 매물을 다 받고 일부만 뺀 결과의 `[제외]` 안내가 '(뺀 만큼 다시 채우지 않음)' 이라 더 받을 매물이 남은 것처럼 읽히던 문제 (직방·네이버). 이제 당근처럼 '(더 받을 매물 없음)' (#132)
- 네이버 일부 안내(요청 상한에서 멈춤, 거래 유형으로 뺀 재개발 구역, 빌라 실거래 상한, `trend` 의 범위)가 종류 태그 없이 `[참고]` 로 나가던 문제 (#132)
- 당근 노출 제한 매물의 `listing` 에러 `reason` 이 `null` 이던 문제. 노출 제한 종류를 준다 (#133)
- 당근 `preschools`·`developments` 가 반올림 전 거리로 반경을 재 `distance_km` 가 반경과 같은 시설(1.004km → 1.0)을 빼던 문제 (매물 반경 검색과 같게 맞춤) (#133)
- 당근 단지·구 후기 페이지 구조가 바뀌면 `complex` 가 `NOT_FOUND`, `region-reviews` 가 '후기가 없다' 로 답하던 문제. 이제 `PARSE_ERROR` (#133)
- `--fields` 로 다른 명령에만 있는 필드를 고르면(당근 역 검색의 `walk_minutes` 를 `search commute` 에) 에러도 안내도 없이 결과에서 빠지던 문제. 이제 `notes` 에 이 명령의 매물 필드를 알린다 (통근 검색의 역까지 도보는 `walk_to_station_minutes`). 없는 필드 에러의 `hint` 도 결과 맨 위 키(`notes`·`total` 등)는 `--fields` 로 거르지 않는다고 알린다 (#134)
- 당근 `school` 에 `대치초등학교` 처럼 종류 이름까지 주면 `서울대치초등학교` 를 못 찾던(`NOT_FOUND`) 문제와, `도곡초등학교` 가 다른 지역 학교만 고르고 `서울도곡초등학교` 를 다른 후보에도 알리지 않던 문제. `대치초` 처럼 줄인 이름으로도 찾아 합친다 (요청 1회, `--city` 를 주면 최대 3회 더) (#133)
- 당근 `listing` 의 `options` 에 전입신고 가능 표시가 영어 코드(`MOVE_IN_REGISTRATION`) 그대로 나가던 문제. 이제 `전입신고 가능` (#133)
- 네이버 `listing` 의 `options` 에 사설경비·에어컨·가스오븐·소파가 영어 코드(`PRIVATE_SECURITY` 등) 그대로 나가던 문제 (#133)
- 값을 빠뜨린 옵션으로 끝난 호출(`naver search listings … --sort`)의 에러가 명령을 `jibsa` 로 적고 `'jibsa --help'` 를 안내하던 문제. 이제 그 명령의 `--help` 를 안내한다 (#134)
- 당근 `school` 의 안내 종류 태그: 같은 이름의 학교 중 하나를 고른 안내는 `[모호]`, 배정 단지를 `--limit` 까지만 보여 준 안내는 `[일부]` 인데 둘 다 `[참고]` 로 나가던 문제 (#133)
- 문서 오류: `docs/llm.md` 의 네이버 재개발 모드가 받는 옵션, `docs/daangn.md` 통근 검색의 위치 찾는 순서, `docs/zigbang.md` 의 `--complex` 도움말 명령 (#134)

## 0.5.1 — 2026-10-21

### 수정

- `docs/llm.md` 와 `--fields` 도움말의 예시에 `url` 이 빠져, 예시를 그대로 쓴 에이전트가 링크 없이 매물을 안내하던 문제 (#118)

## 0.5.0 — 2026-10-21

### ⚠️ 호환 깨짐

- `notes` 의 안내 앞에 종류 태그(`[일부]`·`[범위]`·`[제외]`·`[모호]`·`[거래]`·`[실패]`·`[참고]`)를 붙임. 안내 문장을 그대로 비교하던 쪽은 앞의 태그를 떼고 비교한다 (#110)
- 당근 `search listings` 의 역 주변 검색 결과에서 찾은 역을 `station` 대신 다른 검색과 같은 `region` 으로 줌. `station.name` 을 읽던 쪽은 `region.name` 을 읽는다 (#111)
- 직방·네이버가 층을 `저`·`중`·`고` 로 주던 것을 당근과 같은 `저층`·`중층`·`고층` 으로 맞춤 (#107)
- 원룸을 찾을 때마다 붙던 같은 안내(직방 방 1개 아파트, 당근 원룸·오피스텔·투룸 종류의 한계)를 `notes` 에서 빼고 `docs/llm.md` 로 옮김 (#110)
- 당근 `search commute` 매물마다 붙던 `commute_station`·`subway_minutes`·`transfers` 와 결과의 `searched_stations` 를 뺌 (같은 값이 되풀이되어 출력의 13%였다). 매물이 들어 있는 역 묶음 `stations[]` 의 `station_name`·`subway_minutes`·`transfers` 를 읽는다 (#112)

### 추가

- 직방 `search listings room`·`apt`(동·구), 네이버·당근 `search listings` 에 `--next`. 결과의 `next`(10자 번호, 같은 컴퓨터에서 하루 동안 쓸 수 있다)를 같은 지역·조건에 주면 앞 결과 다음부터 이어 받는다. `--limit` 을 늘려 다시 부를 때처럼 앞 매물을 다시 받지 않고, 네이버·당근은 지역도 다시 찾지 않아 요청이 준다. 지역·조건이 다른 검색에 주면 에러 `message` 에 어느 옵션이 다른지 적는다 (#111)
- 매물 목록 명령(직방 `room`·`apt`·`store`·`stay`·`--complex`, 네이버 `search listings`, 당근 `search listings`·`search commute`·`popular-listings`)에 `--fields`. `--fields id,deposit_manwon,rent_manwon` 처럼 매물마다 낼 필드만 골라 출력을 줄인다 (`id` 와 당근 `in_regions` 는 늘 나온다) (#112)
- 매물 목록 결과에 `has_more` (같은 조건으로 더 받을 매물이 있는지). 직방 `room`·`apt`·`store`·`stay`·`--complex`, 네이버 `search listings`, 당근 동·반경 검색에 새로 붙는다 (#111)
- 매물의 숫자 층 `floor_number` (지하는 음수, 반지하·저층처럼 몇 층인지 모르면 `null`) (#107)
- 다른 소스의 옵션을 옮겨 쓴 사용법 오류(직방에 `--facility`·`--room-count`·`--move-in-now`, 직방 `--bathroom 1개` 등)에 이 명령에서 쓰는 옵션이나, 이 소스에 그 조건이 없다는 것을 에러 `hint` 로 알림. 표에 없는 옵션이 다른 소스의 매물 검색에 있으면 그 명령을 알린다 (#109)
- `docs/llm.md` 에 같은 조건의 소스별 옵션 표 (#109)

### 변경

- 소수점 아래가 없는 숫자를 `1000.0` 대신 `1000` 으로 씀 (금액·면적·거리 등). 매물마다 붙는 `.0` 이 토큰만 썼다 (#112)
- 당근 `search commute` 가 역마다 똑같이 붙이던 안내(`더 보려면 --limit 을 늘리거나…`)를 한 줄로 묶어 역 이름을 모아 알림 (모든 역이면 `찾아본 10곳 모두`) (#112)
- `docs/llm.md` 가 셸 호출 한 번에 `;` 로 명령을 이어 불러도 된다고 알림 (동시에만 부르지 않으면 된다). 후보 여러 개의 `listing` 을 호출 한 번에 본다 (#112)
- `jibsa guide <소스>` 가 문서 전체(3만~4만 자) 대신 절 목록을 줌. 절은 `jibsa guide <소스> <절 이름>`, 전체는 `--all` (#108)
- 반경 안 매물이 모자라 반경 밖 매물을 덧붙일 때 "반경 밖 가까운 매물" 대신 "반경을 덮어 받은 범위의 반경 밖 매물" 이라 알림. 반경을 감싼 사각형·지도 칸에서 받은 것이라 모서리 쪽만 들어와, 가까운 매물을 빠짐없이 고른 줄 알기 쉬웠다 (`--radius` 도움말도 같이) (#110)
- 당근 여러 동 검색(`○가` 동, `--expand`)이 동마다 `--limit` 을 나눠 받던 것을, 동 피드를 올라온 시각 순으로 합쳐 가장 최근 매물부터 줌. `--expand` 는 기본 `--limit` 에서도 주변 동을 함께 본다 (주변 동마다 지도 페이지 요청 1회) (#111)
- 당근 동 검색이 `--limit` 이 20보다 작아도 지도 첫 페이지 20건을 다 받은 것으로 세던 것을 `--limit` 건까지만 씀 (`fetched` 가 `--limit` 을 넘지 않는다). 남은 매물은 `next` 로 이어 받는다 (#111)
- 네이버 반경 검색의 "조건에 맞는 매물은 이 N건이 전부" 안내에 어느 범위의 전부인지(`반경 1km 안팎에서`) 붙임. 반경을 넓히면 더 나오는데 전체인 줄 알기 쉬웠다 (#110)

### 수정

- 당근 `search listings` 가 여러 동(`성수동` → 성수동1가·2가, `충무로` → 1가~5가)을 모두 끝까지 받아도 남은 매물이 있는 것처럼 안내하던 문제 (#111)
- 직방 `listing` 이 총 주차 대수가 소수(`0.4`)인 매물에서 `PARSE_ERROR` 로 끝나던 문제. 받은 값 그대로 `total_parking_count` 에 준다 (#106)
- 네이버 `search listings` 에 `--room 2` 처럼 숫자를 주면 힌트가 욕실 수(`--bathroom 2개`)를 알려 주던 문제. 이제 `--room 투룸` 을 알려 준다 (#109)
- `PARSE_ERROR` 메시지에 응답의 어느 필드가 틀렸는지 함께 적음 (#106)

## 0.4.1 — 2026-10-20

### 수정

- README 맨 위에 로고를 두고 흔히 쓰는 형식(배지·기능·빠른 시작·설정·기여)으로 다시 짜고, 자세한 설치(준비물·PATH·업데이트·삭제)는 `docs/install.md` 로 옮김 (#101)
- 당근에서 동 이름 앞뒤에 공백이 붙으면(`'신사동 '`) 같은 이름 동을 묻지 않고 첫 후보로 조회하던 문제. 공백 없이 찾을 때처럼 `REGION_AMBIGUOUS` 로 알린다 (#93)
- 당근 필터 API 를 쓸 수 없어 예전 방식(동마다 최근 20건)으로 찾을 때 `○가` 동(성수동)의 앞 동이 `--limit` 을 다 써 뒤 동을 조회하지 못하던 문제 (#94)
- 당근·직방 `--details` 가 상세에서 거래가 끝난 매물을 뺐을 때, 앞 안내(`이 N건이 전부입니다` 등)의 건수가 빼기 전 기준이라는 것을 함께 알림 (#95)

## 0.4.0 — 2026-10-17

### 변경

- 세 소스에 보내는 기본 `User-Agent` 를 크롬 131 에서 크롬 152 로 올림 (#86)
- 당근 역 이름 검색이 역 검색·역 주변 매물 목록 실패로 위치 반경으로 찾을 때와, 위치를 당근 대신 직방으로 찾을 때 `notes` 에 실패 이유(API 변경·요청 제한·서버 오류·응답 형식)를 함께 알림. 덤 조회가 GraphQL 에러로 실패했을 때의 안내에도 업데이트가 필요할 수 있다고 덧붙임 (#85)

### 수정

- 당근 실거래·단지 목록·후기처럼 매물 지도를 쓰지 않는 명령이 같은 이름 동(역삼동)을 고르다 지도 페이지를 읽지 못하면 `PARSE_ERROR` 로 끝나던 문제. 확인하지 못한 후보는 남기고 `notes` 로 알린다. 서버 오류로 확인하지 못했을 때도 이제 `notes` 로 알린다 (#84)

## 0.3.1 — 2026-10-17

### 수정

- README 맨 위·설치 데모 GIF 를 0.3.0 출력으로 다시 녹화하고(#66), 소개글을 처음 보는 사람이 읽기 좋게 다듬음 (#67)
- README 의 '데모 영상의 가상 데이터' 절을 빼고 영상 아래 "매물은 데모용 가상 데이터다" 문장만 남김 (#69)
- 당근 `search listings`·`listing`·`complex`·`region-reviews` 가 당근 웹 개편(페이지에 심는 데이터 형식 변경)으로 `PARSE_ERROR` 를 내던 문제. 같은 이름 동이 여러 곳인 지역(역삼동)을 찾을 때도 같은 에러가 났다 (#70)
- 네이버·당근에서 `○가` 동(성수동)을 `--limit` 보다 많은 동으로 나눠 찾을 때 네이버는 요청 없이 0건과 '이 0건이 전부입니다' 를 내고, 당근은 앞 동을 건너뛰던 문제. 직방처럼 앞 동부터 찾고 못 찾은 동은 `notes` 로 알린다 (#71)
- 직방 아파트 반경 검색이 단지 상한에서 멈췄는데도 '이 N건이 전부입니다' 를 함께 내던 문제 (#72)
- 직방 오피스텔 단지 매물(`search listings --complex officetel-…`)에서 거래 불가 매물이 1건만 빠져도 '매물이 더 있다' 안내가 사라지던 문제 (#72)
- 직방 역 주변·단기임대 반경 검색이 표시 거리(소수 둘째 자리)가 반경과 같은 매물을 빼던 문제. 동·좌표 검색처럼 넣는다 (#73)

## 0.3.0 — 2026-10-15

### ⚠️ 호환 깨짐

- 매물 결과 맨 앞의 `notice`(늘 같은 "원 사이트에서 확인하세요" 문장)를 뺌. 매 응답 토큰만 늘렸고 같은 안내는 `jibsa guide` 에 있다 (#58)
- 전체 수 칸 이름을 `total` 로 통일: 직방 room·store·stay·당근 반경 검색의 `total_in_radius`, 당근 동 검색의 `total_in_regions`, 네이버 매물·단지·재개발 구역 목록과 직방 단지 매물의 `total_count`. 읽는 쪽도 `total` 로 고친다 (#58)
- 매물 상세의 `move_in`·`parking` 을 세 소스 같은 꼴로 바꿈. 입주일 `"2026.10.24 이후 입주 가능"` → `"2026-10-24"`, `"즉시 입주 가능 (협의 가능)"` → `"즉시입주 (협의 가능)"`, 주차 `"주차 불가능"`·`"주차 불가 (총 4대)"` → `"불가"`·`"불가 (총 4대)"`, 직방 상가 `"가능 - 자주식 6대"` → `"가능 (자주식 6대)"`. 문자열을 그대로 비교하던 쪽은 새 꼴로 고친다 (#58)
- `naver regions 중구` 처럼 같은 이름의 시·군·구가 여러 곳이면 첫 곳의 하위 지역 대신 `REGION_AMBIGUOUS` 로 후보를 알림. `서울 중구` 처럼 시·도를 붙여 다시 부른다 (#59)
- 직방·당근에서 같은 이름의 동·구가 여러 곳이면(신사동 → 강남구·은평구) 첫 곳으로 찾던 것을 네이버처럼 `REGION_AMBIGUOUS`(exit 1)로 멈추고 후보(`candidates`)를 알림. 첫 곳이 소스마다 달라(직방 은평구, 당근 강남구) 다른 동네 매물을 섞어 비교할 수 있었다. 부르는 쪽은 구 이름을 붙이거나(직방 `강남구 신사동`) 당근은 `--city 강남구` 로 다시 부른다. 같은 이름의 역은 그대로 첫 역으로 찾는다 (#59)

### 추가

- 직방 `search listings room --details`: 매물마다 상세를 1회씩 더 받아 건물 용도(`residence_type`, 근린생활시설·고시원 등)를 붙인다. 목록 API 는 용도를 주지 않아 전입신고가 막힐 수 있는 매물을 고르려면 상세를 하나씩 열어야 했다 (#60)
- 당근 `search listings --details`: 매물마다 상세를 1회씩 더 받아 목록에 없는 관리비·등록일·번지 주소·사용승인일·방 구조를 채운다 (#60)
- 당근 동 검색 매물에 `in_regions` 칸: 조회한 동 안이면 `true`, 당근이 섞어 준 주변 동이면 `false`. 예전에는 `notes` 문장과 주소 글자로만 구분했다 (#59)
- `jibsa guide <소스> [절 이름]`: 직방·네이버·당근·공통 사용 문서를 설치본에서 네트워크 없이 읽는다 (`jibsa guide daangn 'search listings'` 처럼 그 절만). 예전에는 GitHub `main` 링크뿐이라 설치한 버전과 다를 수 있었다 (#61)

### 변경

- `--help` 를 터미널이 아닐 때(파이프·LLM 셸) Rich 표 대신 줄글로 씀. 80칸 표가 옵션 설명을 `…` 로 자르고 출력의 3/4 이 공백이었다 (`zigbang search listings room --help` 9,738자 → 2,773자). 터미널 화면은 그대로다 (#56)
- 세 소스 매물 검색에서 목록 옵션에 없는 값이 그 명령의 다른 옵션이나 다른 소스 표현이면 에러 `hint` 가 맞는 옵션을 알려 줌 (직방 `--option 반려동물가능` → `--condition 반려동물`, 네이버 `--bathroom 1` → `--bathroom 1개`). 값을 바꿔 받지는 않는다 (#57)
- 네이버·당근도 직방처럼 `○가` 로 나뉜 동(성수동 → 성수동1가·2가)을 모두 찾아 합침. 예전에는 네이버는 1가만, 당근은 2가만 찾아 절반쯤의 매물이 빠졌다. `--limit` 은 동끼리 나눠 쓴다 (#59)
- 당근은 같은 이름 동 후보 중 매물 지도가 있는 법정동만 세어, 행정동이 같은 이름인 역삼동(용인시 처인구)은 멈추지 않고 강남구로 찾는다 (#59)
- `notes` 문장을 짧게 바꿈 (일부만 보여 준다·뺀 매물·전체 수·동 경계·원룸 분류 안내). 뜻은 같다 (#58)
- 좌표(`lat`·`lng`)를 소수 일곱째 자리로 반올림 (`127.04934499999999` → `127.049345`) (#58)

### 수정

- 직방 매물 상세의 `approved_at` 이 `"2011년 7월 1"`, `"1984년 10월 26일"` 처럼 원본 그대로 나오던 문제. 다른 매물처럼 `YYYY-MM-DD` 로 맞춘다 (#55)
- 네이버 매물의 지하층 `floor` 가 `"B1"` 으로 나오던 문제. 직방·당근처럼 `"지하1"` 로 맞춘다 (#55)
- LLM 가이드가 당근 목록의 `room_type` 을 늘 `null` 이라고 설명하던 문서 오류. 원룸은 `오픈형원룸`·`분리형원룸` 이 붙는다 (#62)

## 0.2.2 — 2026-10-14

### 수정

- 당근 `popular-listings` 가 거래 불가 매물을 뺐을 때 뒤 순위가 남아 있는데도 "더 조회할 매물이 없습니다" 라고 안내하던 문제 (#46)
- 직방 room·store·stay 검색에서 받은 뒤 거래 불가 매물이 빠지면 "조건에 맞는 매물이 약 N건이라 일부만 보여 줍니다" 안내가 사라지던 문제 (#46)
- 네이버 목록 제외 안내가 하지 않는 '거래 불가' 제외를 말하던 문제. 실제 사유(중복·알 수 없는 거래 유형)로 알린다 (#46)
- `--trade` 와 맞지 않는 가격 조건 오류가 그 검색에 없는 거래 유형을 권하던 문제 (직방 아파트에 "월세·단기임대 거래에만 쓰세요") (#47)
- 출력을 받는 쪽이 먼저 닫으면(`| head` 등) `INTERNAL_ERROR` 와 Python 경고를 내고 exit code 120 으로 끝나던 문제. 에러 없이 exit 1 로 끝난다 (#47)
- Windows 에서 jibsa 를 동시에 실행하면 요청 제한 상태 쓰기가 실패(`INTERNAL_ERROR`)하거나 요청 간격이 어긋나던 문제. Windows 도 상태 파일을 잠가 macOS·Linux 처럼 동시에 실행할 수 있다 (#48)
- 프록시 거절(`ProxyError`)·지원하지 않는 URL 처럼 다시 보내도 같은 전송 오류를 1초씩 기다리며 3번 재시도하던 문제. 바로 `NETWORK_ERROR` 로 알리고, 시간 초과·연결 실패는 그대로 재시도한다 (#49)
- 직방 단기임대 거리순 조회 한도 설명이 역·학교 이름 검색 동작과 다르던 문서 오류 (#50)

## 0.2.1 — 2026-10-13

### 수정

- README(PyPI 프로젝트 페이지 포함) 맨 위에 Claude Code 가 jibsa 로 강남역 원룸을 찾는 데모를 두고, 설치 데모를 PyPI 설치(`uv tool install jibsa`)로 바꿈. 0.2.0 의 PyPI 페이지에는 Claude 데모가 없고 설치 데모가 GitHub 주소 설치였다 (#42)

## 0.2.0 — 2026-10-13

### 추가

- PyPI 에서 설치할 수 있다: `uv tool install jibsa`, `pipx install jibsa`, `pip install jibsa`, 설치 없이 `uvx jibsa`. `jibsa==0.2.0` 처럼 버전도 고를 수 있다 (#33)

## 0.1.1 — 2026-10-13

### 수정

- 직방 역·좌표 반경 검색에서 결과를 일부만 보여 줄 때 이미 역으로 찾았는데도 "역 이름처럼 더 좁은 지역으로 다시 검색하세요" 라고 안내하던 문제. 반경 검색은 "--radius 를 줄여 다시 검색하세요" 로 안내한다 (#8)
- 당근 `--city 광주시` 가 경기도 광주시와 전남광주통합특별시를 함께 골라 다른 지역으로 조회할 수 있던 문제. `광주시` 는 경기도 광주시만 가리키고, `--city` 를 줬는데도 여러 곳이 맞으면 구 이름으로 좁히라고 안내한다 (#14)
- 당근 장소 이름 검색에서 직방 지역 검색이 서버·네트워크 오류로 실패하면 당근 오류(`source: daangn`)로 끝나던 문제. 네이버로 다시 찾고, 그래도 못 찾으면 `source: zigbang` 으로 알린다 (#15)
- 직방 `search listings --complex apt-…` 에 단지에 없는 평형 ID 를 주면 0건으로 끝나던 문제. `INVALID_ARGUMENT` 로 알리고, 1 미만 평형 ID 는 조회 전에 막는다 (#16)
- 반경 검색의 `total_in_radius` 와 "반경 안 N건뿐" 안내의 건수가 반경 경계 근처 매물 때문에 어긋나던 문제 (직방 room·store·stay). 둘 다 출력한 `distance_km` 로 센다 (#17)
- 반경 밖 매물 안내가 거리를 모르는 매물(`distance_km: null`)을 반경 안으로 세던 문제 (#17)
- 직방 `search listings store --area-max 0` 이 요청을 보낸 뒤 영어 오류로 끝나던 문제. 조회 전에 `INVALID_ARGUMENT` 로 막는다 (#18)
- 직방 매물 상세와 단기임대 목록에서 응답에 옵션·인근 역·관리비 포함 항목·할인 정보가 빠지면 `[]`(없음)로 내보내던 것을 `null`(모름)로 바꿈 (#19)
- 당근 `search commute` 의 `WORKPLACE` 도움말이 직방으로만 위치를 찾는다고 설명하던 문서 오류 (#20)
- 라이브러리의 비동기 클라이언트가 요청 제한 상태 파일 잠금을 기다리는 동안 이벤트 루프 전체를 멈추던 문제 (#21)
- Windows 에서 요청 제한 상태 폴더 자리에 파일이 있어 상태를 쓸 수 없을 때 `jibsa limits` 가 에러 대신 빈 상태를 보여 주던 문제. macOS·Linux 처럼 `INTERNAL_ERROR` 로 알린다 (#30)

## 0.1.0 — 2026-10-11

### 추가

- 첫 릴리스: 직방·네이버·당근부동산의 현재 매물·실거래·단지 정보를 조회하는 CLI 와 `jibsa guide`
- `jibsa --version` — 설치한 버전과 커밋을 출력
