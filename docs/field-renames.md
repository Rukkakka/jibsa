# 출력 칸 이름 바뀜 (옛 이름 → 새 이름)

네 소스의 출력 칸 이름·모양을 용어집 하나로 맞추며 바뀐 칸 전부다 (CHANGELOG 의 같은 버전 "호환 깨짐" 항목). 옛 이름으로 칸을 읽던 프롬프트·스크립트·`--fields` 는 이 표대로 새 이름으로 바꾼다. 이름 규칙은 [출력 규약의 칸 이름 규칙](https://github.com/Rukkakka/jibsa/blob/main/docs/development/output-contract.md) 에 있다.

## 읽는 법

- **새 이름** 이 점으로 이어지면 모양이 바뀐 것이다: `trade_averages.sale.price_manwon` 은 `trade_averages` 객체의 `"sale"` 키 안 `price_manwon` 이다.
- 거래별로 묶은 객체의 키는 영어 거래 낱말(`"sale"`=매매·`"jeonse"`=전세·`"wolse"`=월세·`"short_term"`=단기임대·`"yeonse"`=연세, 직방 탭 `"jeonse_wolse"`=전월세)이다. 매물 `trade_type` 값과 `--trade` 입력은 한국어 그대로다. 다방 `price-trend` 의 `trade_ranges` 안 기간 키는 `one_year`·`three_years` 다. 그 거래가 해당 없으면(매물 0건 등) 키가 없고, 모두 비면 `{}` 다.
- 범위는 `{"lowest": …, "highest": …}` 객체다. 금액 범위의 두 끝 안에는 매물과 같은 금액 칸(`price_manwon`·`deposit_manwon`·`rent_manwon`)이 들어간다.
- `{a,b}` 는 두 경로에 같은 규칙, `a + b` 는 칸이 둘로 나뉘거나 하나가 붙는다는 뜻이다.

## 값 표기가 바뀐 칸

- 직방 실거래 전세가율 `jeonse_ratio`(0~1) → `jeonse_ratio_percent`(0~100)
- 층이 숫자로 나오던 실거래·거래 행 → 매물과 같은 `floor`(글자, 예 `"3"`·`"지하1"`) + `floor_number`(숫자). 글자 층이던 실거래 행에도 `floor_number` 가 붙는다
- 다방 지역 순위 기준 달 `"26년 5월"` → `price_month` `"2026-05"` (못 읽으면 `null` 과 `[참고]`)
- 다방 실거래 `direct`(true/false) → `deal_type`(`"직거래"`/`"중개거래"`)
- 직방·다방 지역 코드 2·5·8자리 → 10자리 `legal_division_code`
- 직방 `search complexes` 의 검색 중심→단지 거리 m → `distance_km`, 당근 보육시설 목록 거리 km → `distance_m`(웹과 같은 미터)
- 당근 단지 `heating`("개별난방, 도시가스") → `heating`(방식) + `heating_fuel`(연료)
- 당근 `compare` 의 `address` 가 도로명 우선 → 지번 주소가 되고 도로명은 새 `road_address`
- 네이버 단지·재개발 호가, 당근 `compare` 호가 평균에서 매물 0건인 거래와 당근 `compare` 평형의 최근 실거래(`latest_trades`)에서 실거래가 없는 거래는 `null` 대신 키 없음
- 거래별로 묶은 값에서 그 거래의 값을 모두 모르면 `{"jeonse": {"deposit_manwon": null}}` 이 아니라 `{"jeonse": null}`: 다방 `trade_averages`·`trade_ranges`·`asking_averages`·`area_prices[].price_per_pyeong`, 직방 `estimated_prices`, 네이버 `estimated_prices[].sale`·`jeonse`·`market-price` 의 `weeks[].sale`·`jeonse`, 당근 `price-trend` 의 `estimated_prices.sale`. 일부 칸만 모르면 그 칸만 `null`
- 당근 `trending-complexes` 의 `latest_trades`·`compare` 의 `pyeong.latest_trades` 는 당근이 실거래 목록을 주지 않거나 목록에 빈 항목이 섞이면 그 거래 키가 `null`(모름), 빈 목록일 때만 키 없음
- 네이버 중복 매물 묶음 `asking_range` 의 월세 끝이 0 이면 그 끝의 `rent_manwon` 이 `null`
- 직방 `price-trend --period` 값 `최근1년`·`최근3년`·`전체기간` → `1년`·`3년`·`전체` (출력 `period` 도 같다)

## 공통 (네 소스의 매물)

| 명령 | 옛 이름 | 새 이름 | 비고 |
| --- | --- | --- | --- |
| listing (네 소스) | `elevator` | `has_elevator` |  |
| listing (네 소스) | `nearby_subways` | `nearby_stations` |  |
| 모든 매물 목록(search listings*·--complex·catalog·popular-listings)·listing | `registered_at` | `registered_date` |  |
| 모든 매물 목록·listing | `approved_at` | `approved_date` |  |

## 직방

| 명령 | 옛 이름 | 새 이름 | 비고 |
| --- | --- | --- | --- |
| catalog | `change_rate` | `change_percent` |  |
| catalog | `estimated_jeonse_price_manwon` | `estimated_prices.jeonse.deposit_manwon` | 모양 바뀜 |
| catalog | `estimated_jeonse_price_per_pyeong_manwon` | `estimated_prices.jeonse.price_per_pyeong_manwon` | 모양 바뀜 |
| catalog | `estimated_sale_price_manwon` | `estimated_prices.sale.price_manwon` | 모양 바뀜 |
| catalog | `estimated_sale_price_per_pyeong_manwon` | `estimated_prices.sale.price_per_pyeong_manwon` | 모양 바뀜 |
| catalog | `presale_average_price_manwon` | `presale_price_average_manwon` |  |
| catalog | `presale_type_price_manwon` | `type_presale_price_manwon` |  |
| catalog | `price_manwon` | `public_price_manwon` |  |
| complex | `approved_at` | `approved_date` |  |
| complex | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세` 에서 `sale`·`jeonse`·`wolse` 로 바뀜 |
| complex | `completed_at` | `completed_month` |  |
| complex | `elevator` | `has_elevator` |  |
| complex | `entrance_type` | `entrance` |  |
| complex | `estimated_jeonse_price_manwon` | `estimated_prices.jeonse.deposit_manwon` | 모양 바뀜 |
| complex | `estimated_jeonse_price_per_pyeong_manwon` | `estimated_prices.jeonse.price_per_pyeong_manwon` | 모양 바뀜 |
| complex | `estimated_sale_price_manwon` | `estimated_prices.sale.price_manwon` | 모양 바뀜 |
| complex | `estimated_sale_price_max_manwon` | `estimated_ranges.sale.highest.price_manwon` | 모양 바뀜 |
| complex | `estimated_sale_price_min_manwon` | `estimated_ranges.sale.lowest.price_manwon` | 모양 바뀜 |
| complex | `estimated_sale_price_per_pyeong_manwon` | `estimated_prices.sale.price_per_pyeong_manwon` | 모양 바뀜 |
| complex | `exclusive_area_m2` | `area_m2` |  |
| complex | `exclusive_area_pyeong` | `area_pyeong` |  |
| complex | `floor_area_ratio` | `floor_area_ratio_percent` |  |
| complex | `households` | `household_count` |  |
| complex | `id` | `pyeong_id` |  |
| complex | `manage_cost_summer_manwon` | `summer_manage_cost_manwon` |  |
| complex | `manage_cost_winter_manwon` | `winter_manage_cost_manwon` |  |
| complex | `max_floor` | `building_floor_range.highest` | 모양 바뀜 |
| complex | `property_type` | `complex_type` |  |
| complex | `rank` | `ranking` |  |
| complex | `resale_available_from` | `resale_available_date` |  |
| complex·price-trend | `households` | `household_count` |  |
| listing (단기임대) | `end` | `end_date` |  |
| listing (단기임대) | `max_contract_weeks` | `contract_weeks_range.highest` | 모양 바뀜 |
| listing (단기임대) | `min_contract_weeks` | `contract_weeks_range.lowest` | 모양 바뀜 |
| listing (단기임대) | `start` | `start_date` |  |
| listing·catalog | `confirmed_at` | `confirmed_date` |  |
| listing·catalog | `exclusive_area_m2` | `area_m2` |  |
| listing | `building_trades[].floor` | `building_trades[].floor + floor_number` | 값 표기 바뀜 (`floor_number` 가 붙음) |
| listing·catalog | `minutes` | `travel_minutes` |  |
| listing·catalog | `total_parking_count` | `parking_count` |  |
| listing·catalog | `zzim_count` | `favorite_count` |  |
| price-trend | `period` | `period` | 값 표기 바뀜 |
| price-trend | `points` | `months` |  |
| price-trend | `price_per_pyeong_manwon` | `estimated_price_per_pyeong_manwon` |  |
| price-trend --pyeong | `change_manwon` | `months[].sale.estimated_price_change_manwon` |  |
| price-trend --pyeong | `change_manwon` | `months[].jeonse_wolse.estimated_deposit_change_manwon` |  |
| price-trend --pyeong | `count` | `months[].sale.trade_count` |  |
| price-trend --pyeong | `estimated_jeonse_price_manwon` | `months[].jeonse_wolse.estimated_deposit_manwon` |  |
| price-trend --pyeong | `jeonse_count` | `months[].jeonse_wolse.trade_counts.jeonse` | 모양 바뀜 |
| price-trend --pyeong | `jeonse_wolse` | `months[].jeonse_wolse` |  |
| price-trend --pyeong | `max_price_manwon` | `months[].sale.trade_range.highest.price_manwon` | 모양 바뀜 |
| price-trend --pyeong | `max_price_manwon` | `months[].jeonse_wolse.trade_range.highest.converted_price_manwon` | 모양 바뀜 |
| price-trend --pyeong | `min_price_manwon` | `months[].sale.trade_range.lowest.price_manwon` | 모양 바뀜 |
| price-trend --pyeong | `min_price_manwon` | `months[].jeonse_wolse.trade_range.lowest.converted_price_manwon` | 모양 바뀜 |
| price-trend --pyeong | `period` | `period` | 값 표기 바뀜 |
| price-trend --pyeong | `sale` | `months[].sale` |  |
| price-trend --pyeong | `trade` | `trade_tab` |  |
| price-trend --pyeong | `wolse_count` | `months[].jeonse_wolse.trade_counts.wolse` | 모양 바뀜 |
| real-price | `category` | `deal_type` |  |
| real-price | `dong` | `building_dong` |  |
| real-price | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| real-price | `jeonse_ratio` | `jeonse_ratio_percent` | 값 표기 바뀜 |
| real-price | `offer_price_diff_manwon` | `presale_price_diff_manwon` |  |
| real-price | `transactions` | `trades` |  |
| region-info | `complexes` | `complex_count` |  |
| region-info | `estimated_prices` | `by_pyeong_range` |  |
| region-info | `estimated_sale_price_max_manwon` | `estimated_ranges.sale.highest.price_manwon` | 모양 바뀜 |
| region-info | `estimated_sale_price_min_manwon` | `estimated_ranges.sale.lowest.price_manwon` | 모양 바뀜 |
| region-info | `households` | `household_count` |  |
| region-info | `households` | `population.household_months` |  |
| region-info | `jeonse_count` | `monthly_volumes[].trade_counts.jeonse` | 모양 바뀜 |
| region-info | `points` | `price_trend.lines[].months` |  |
| region-info | `range` | `by_pyeong_range[].pyeong_range` |  |
| region-info | `range` | `price_trend.pyeong_range` |  |
| region-info | `sale_count` | `monthly_volumes[].trade_counts.sale` | 모양 바뀜 |
| region-info | `sale_price_max_manwon` | `by_pyeong_range[].estimated_ranges.sale.highest.price_manwon` | 모양 바뀜 |
| region-info | `sale_price_min_manwon` | `by_pyeong_range[].estimated_ranges.sale.lowest.price_manwon` | 모양 바뀜 |
| region-info | `sale_price_per_pyeong_manwon` | `by_pyeong_range[].estimated_prices.sale.price_per_pyeong_manwon` | 모양 바뀜 |
| region-info | `total` | `population.people[].population` |  |
| region-info | `total` | `population.household_months[].household_count` |  |
| region-info | `weeks` | `price_movement.streak_weeks` |  |
| region-info | `wolse_count` | `monthly_volumes[].trade_counts.wolse` | 모양 바뀜 |
| region-info·region-ranking·region-trades | `code` | `region.legal_division_code` | 값 표기 바뀜 |
| region-ranking | `approved_at` | `approved_date` |  |
| region-ranking | `change_rate_percent` | `prev_trade_diff_percent` |  |
| region-ranking | `complex_name` | `name` |  |
| region-ranking | `contract_date` | `latest_trade_date` |  |
| region-ranking | `diff_manwon` | `prev_trade_diff_manwon` |  |
| region-ranking | `households` | `household_count` |  |
| region-ranking | `jeonse_rate_percent` | `jeonse_ratio_percent` |  |
| region-trades | `contract_date` | `trade_date` |  |
| region-trades | `jeonse_price_diff_manwon` | `jeonse_comparison_diff_manwon` |  |
| region-trades | `jeonse_price_diff_rate_percent` | `jeonse_comparison_diff_percent` |  |
| region-trades | `market_price_diff_manwon` | `estimated_price_diff_manwon` |  |
| region-trades | `market_price_diff_rate_percent` | `estimated_price_diff_percent` |  |
| region-trades | `offer_price_diff_manwon` | `presale_price_diff_manwon` |  |
| region-trades | `offer_price_diff_rate_percent` | `presale_price_diff_percent` |  |
| region-trades | `prev_diff_manwon` | `prev_trade_diff_manwon` |  |
| region-trades | `prev_diff_rate_percent` | `prev_trade_diff_percent` |  |
| region-trades | `public_price_diff_rate_percent` | `public_price_diff_percent` |  |
| search complexes | `distance_m` | `distance_km` | 값 표기 바뀜 |
| search complexes | `district` | `sigungu` |  |
| search complexes | `district_avg_freshmen` | `sigungu_freshmen_average` |  |
| search complexes | `district_avg_students` | `sigungu_students_average` |  |
| search complexes | `district_female_percent` | `sigungu_female_percent` |  |
| search complexes | `district_freshmen_change_percent` | `sigungu_freshmen_change_percent` |  |
| search complexes | `district_male_percent` | `sigungu_male_percent` |  |
| search complexes | `district_meal_cost_manwon` | `sigungu_meal_cost_manwon` |  |
| search complexes | `district_students_per_class` | `sigungu_students_per_class` |  |
| search complexes | `district_tuition_manwon` | `sigungu_tuition_manwon` |  |
| search complexes | `founded_on` | `established_date` |  |
| search complexes | `households` | `household_count` |  |
| search listings apt | `is_price_range` | `mixed_prices` |  |
| search listings apt | `listing_count` | `realtor_count` |  |
| search listings apt | `local_code` | `(없앰)` | 지움 |
| search locations | `approved_at` | `approved_date` |  |
| search locations | `households` | `household_count` |  |
| search locations | `property_type` | `complex_type` |  |

## 네이버

| 명령 | 옛 이름 | 새 이름 | 비고 |
| --- | --- | --- | --- |
| complex | `approved_at` | `approved_date` |  |
| complex | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세`·`단기임대` 에서 `sale`·`jeonse`·`wolse`·`short_term` 으로 바뀜 |
| complex | `complex_number` | `complex_id` |  |
| complex | `contract_m2` | `contract_area_m2` |  |
| complex | `exclusive_m2` | `area_m2` |  |
| complex | `exclusive_pyeong` | `area_pyeong` |  |
| complex | `floor_area_ratio` | `floor_area_ratio_percent` |  |
| complex | `households` | `household_count` |  |
| complex | `jeonse_asking_range_manwon` | `asking_ranges.jeonse.{lowest,highest}.deposit_manwon` | 모양 바뀜 |
| complex | `monthly_asking` | `asking_ranges.wolse` | 모양 바뀜 |
| complex | `number` | `pyeong_id` |  |
| complex | `planned_floor_area_ratio` | `planned_floor_area_ratio_percent` |  |
| complex | `planned_households` | `planned_household_count` |  |
| complex | `property_type` | `complex_type` |  |
| complex | `pyeong_numbers` | `pyeong_ids` |  |
| complex | `representative_pyeong` | `representative_pyeong_id` |  |
| complex | `sale_asking_range_manwon` | `asking_ranges.sale.{lowest,highest}.price_manwon` | 모양 바뀜 |
| complex | `short_term_asking` | `asking_ranges.short_term` | 모양 바뀜 |
| complex | `supply_m2` | `supply_area_m2` |  |
| complex --pyeong | `as_of` | `asking_price_per_pyeong.{sale,jeonse}.base_date` |  |
| complex --pyeong | `average_3m_manwon` | `trade_summary.{sale,jeonse}.recent_3m_average_manwon` |  |
| complex --pyeong | `floor` | `trade_summary.{sale,jeonse}.trade_range.{lowest,highest}.floor + floor_number` | 값 표기 바뀜 |
| complex --pyeong | `highest` | `trade_summary.{sale,jeonse}.trade_range.highest` | 모양 바뀜 |
| complex --pyeong | `jeonse` | `trade_summary.jeonse` |  |
| complex --pyeong | `jeonse_average_manwon` | `estimated_prices[].jeonse.average_manwon` | 모양 바뀜 |
| complex --pyeong | `jeonse_range_manwon` | `estimated_prices[].jeonse.{low_manwon,high_manwon}` | 모양 바뀜 |
| complex --pyeong | `jeonse_ratio_percent` | `estimated_prices[].{jeonse_ratio_low_percent,jeonse_ratio_high_percent}` | 모양 바뀜 |
| complex --pyeong | `latest_manwon` | `pyeong_manage_cost.latest_manage_cost_manwon` |  |
| complex --pyeong | `lowest` | `trade_summary.{sale,jeonse}.trade_range.lowest` | 모양 바뀜 |
| complex --pyeong | `manwon_per_pyeong` | `asking_price_per_pyeong.{sale,jeonse}.price_per_pyeong_manwon` |  |
| complex --pyeong | `manwon_per_pyeong` | `asking_price_per_pyeong.{sale,jeonse}.regions[].price_per_pyeong_manwon` |  |
| complex --pyeong | `market_prices` | `estimated_prices` |  |
| complex --pyeong | `monthly_average_manwon` | `pyeong_manage_cost.manage_cost_manwon` |  |
| complex --pyeong | `price_manwon` | `trade_summary.sale.trade_range.{lowest,highest}.price_manwon / trade_summary.jeonse.trade_range.{lowest,highest}.deposit_manwon` |  |
| complex --pyeong | `price_per_pyeong` | `asking_price_per_pyeong` |  |
| complex --pyeong | `price_per_pyeong.jeonse` | `asking_price_per_pyeong.jeonse` |  |
| complex --pyeong | `price_per_pyeong.sale` | `asking_price_per_pyeong.sale` |  |
| complex --pyeong | `pyeong_maintenance_fee` | `pyeong_manage_cost` |  |
| complex --pyeong | `real_price_summary` | `trade_summary` |  |
| complex --pyeong | `sale` | `trade_summary.sale` |  |
| complex --pyeong | `sale_average_manwon` | `estimated_prices[].sale.average_manwon` | 모양 바뀜 |
| complex --pyeong | `sale_range_manwon` | `estimated_prices[].sale.{low_manwon,high_manwon}` | 모양 바뀜 |
| complex --pyeong | `since` | `trade_summary.start_date` |  |
| complex --pyeong | `since` | `trade_summary.{sale,jeonse}.start_date` |  |
| complex --pyeong | `summer_average_manwon` | `pyeong_manage_cost.summer_manage_cost_manwon` |  |
| complex --pyeong | `trade_category` | `trade_summary.{sale,jeonse}.trade_range.{lowest,highest}.deal_type` |  |
| complex --pyeong | `winter_average_manwon` | `pyeong_manage_cost.winter_manage_cost_manwon` |  |
| complex --pyeong | `year_month` | `pyeong_manage_cost.latest_month` |  |
| complex·listing | `walking_minutes` | `walk_minutes` |  |
| listing | `agent_fee_individual_check_required` | `broker_fee_individual_check_required` |  |
| listing | `agent_fee_manwon` | `broker_fee_manwon` |  |
| listing | `complex_number` | `complex_id` |  |
| listing | `confirmed_at` | `confirmed_date` |  |
| listing | `dong` | `building_dong` |  |
| listing | `opens` | `open_year` | 값 표기 바뀜 |
| listing | `period` | `project_period` |  |
| listing | `pyeong_number` | `pyeong_id` |  |
| listing | `station` | `name` |  |
| listing | `walking_minutes` | `walk_minutes` |  |
| market-price | `complex_number` | `complex_id` |  |
| market-price | `jeonse_manwon` | `providers[].weeks[].jeonse.average_manwon` | 모양 바뀜 |
| market-price | `jeonse_range_manwon` | `providers[].weeks[].jeonse.{low_manwon,high_manwon}` | 모양 바뀜 |
| market-price | `jeonse_ratio_percent` | `providers[].weeks[].{jeonse_ratio_low_percent,jeonse_ratio_high_percent}` | 모양 바뀜 |
| market-price | `points` | `providers[].weeks` |  |
| market-price | `pyeong_number` | `pyeong_id` |  |
| market-price | `sale_manwon` | `providers[].weeks[].sale.average_manwon` | 모양 바뀜 |
| market-price | `sale_range_manwon` | `providers[].weeks[].sale.{low_manwon,high_manwon}` | 모양 바뀜 |
| market-price | `since` | `start_date` |  |
| real-price | `built_year` | `completed_year` |  |
| real-price | `category` | `deal_type` |  |
| real-price | `complex_number` | `complex_id` |  |
| real-price | `contract_date` | `trade_date` |  |
| real-price | `east_west_m` | `nearby_trades.width_km` | 값 표기 바뀜 |
| real-price | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| real-price | `manwon_per_pyeong` | `price_per_pyeong_manwon` |  |
| real-price | `nearby_transactions` | `nearby_trades` |  |
| real-price | `north_south_m` | `nearby_trades.height_km` | 값 표기 바뀜 |
| real-price | `previous_deposit_manwon` | `prev_deposit_manwon` |  |
| real-price | `previous_rent_manwon` | `prev_rent_manwon` |  |
| real-price | `pyeong_number` | `pyeong_id` |  |
| real-price | `pyeong_numbers` | `pyeong_ids` |  |
| real-price | `range` | `nearby_trades.{height_km,width_km}` | 모양 바뀜 |
| real-price | `renewal` | `renewal_right` | 주변 실거래 `nearby_trades.trades[]` 와 빌라 단지 실거래 `trades[]` (계약갱신요구권 사용). 아파트 실거래 `trades[]` 의 `renewal`(갱신 계약)은 그대로 |
| real-price | `since` | `start_date` |  |
| real-price | `transactions` | `trades` |  |
| redevelopment | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세`·`단기임대` 에서 `sale`·`jeonse`·`wolse`·`short_term` 으로 바뀜 |
| redevelopment | `building_coverage_ratio` | `building_coverage_ratio_percent` |  |
| redevelopment | `floor_area_ratio` | `floor_area_ratio_percent` |  |
| redevelopment | `households` | `planned_household_count` |  |
| redevelopment | `jeonse_asking_range_manwon` | `asking_ranges.jeonse.{lowest,highest}.deposit_manwon` | 모양 바뀜 |
| redevelopment | `redevelopment_number` | `redevelopment_id` |  |
| redevelopment | `sale_asking_range_manwon` | `asking_ranges.sale.{lowest,highest}.price_manwon` | 모양 바뀜 |
| regions | `parent_code` | `parent_legal_division_code` |  |
| school | `approved_at` | `approved_date` |  |
| school | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세`·`단기임대` 에서 `sale`·`jeonse`·`wolse`·`short_term` 으로 바뀜 |
| school | `city_average` | `sido_average` |  |
| school | `complex_number` | `complex_id` |  |
| school | `district_average` | `sigungu_average` |  |
| school | `households` | `household_count` |  |
| school | `jeonse_asking_range_manwon` | `asking_ranges.jeonse.{lowest,highest}.deposit_manwon` | 모양 바뀜 |
| school | `monthly_asking` | `asking_ranges.wolse` | 모양 바뀜 |
| school | `opened_at` | `opened_date` |  |
| school | `property_type` | `complex_type` |  |
| school | `sale_asking_range_manwon` | `asking_ranges.sale.{lowest,highest}.price_manwon` | 모양 바뀜 |
| school | `short_term_asking` | `asking_ranges.short_term` | 모양 바뀜 |
| school | `stats_date` | `base_date` |  |
| search complexes | `approved_at` | `approved_date` |  |
| search complexes | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세`·`단기임대` 에서 `sale`·`jeonse`·`wolse`·`short_term` 으로 바뀜 |
| search complexes | `complex_number` | `complex_id` |  |
| search complexes | `households` | `household_count` |  |
| search complexes | `jeonse_asking_range_manwon` | `asking_ranges.jeonse.{lowest,highest}.deposit_manwon` | 모양 바뀜 |
| search complexes | `monthly_asking` | `asking_ranges.wolse` | 모양 바뀜 |
| search complexes | `property_type` | `complex_type` |  |
| search complexes | `sale_asking_range_manwon` | `asking_ranges.sale.{lowest,highest}.price_manwon` | 모양 바뀜 |
| search complexes | `short_term_asking` | `asking_ranges.short_term` | 모양 바뀜 |
| search listings | `confirmed_at` | `confirmed_date` |  |
| search listings | `deposit_range_manwon` | `asking_range.{lowest,highest}.deposit_manwon` | 모양 바뀜 |
| search listings | `rent_range_manwon` | `asking_range.{lowest,highest}.rent_manwon` | 모양 바뀜 |
| search listings (·--complex·--redevelopment) | `price_range_manwon` | `asking_range.{lowest,highest}.price_manwon` | 모양 바뀜 |
| search listings --complex | `complex_number` | `complex_id` |  |
| search listings --redevelopment | `redevelopment_number` | `redevelopment_id` |  |
| search redevelopment | `article_counts` | `listing_counts` | 키도 `매매`·`전세`·`월세`·`단기임대` 에서 `sale`·`jeonse`·`wolse`·`short_term` 으로 바뀜 |
| search redevelopment | `households` | `planned_household_count` |  |
| search redevelopment | `redevelopment_number` | `redevelopment_id` |  |
| search redevelopment | `sale_asking_range_manwon` | `asking_ranges.sale.{lowest,highest}.price_manwon` | 모양 바뀜 |
| trend | `change_rate_pct` | `listing_count_trend.change_percent` |  |
| trend | `listing_count` | `listing_count_trend` |  |
| trend | `max` | `listing_count_trend.count_range.highest` | 모양 바뀜 |
| trend | `min` | `listing_count_trend.count_range.lowest` | 모양 바뀜 |
| trend | `price_per_pyeong` | `asking_price_per_pyeong` |  |
| trend | `trade_count` | `trade_count_trend` |  |
| trend | `weekly` | `listing_count_trend.weeks` |  |
| trend | `weekly` | `trade_count_trend.weeks` |  |
| trend | `weekly` | `asking_price_per_pyeong.weeks` |  |

## 당근

| 명령 | 옛 이름 | 새 이름 | 비고 |
| --- | --- | --- | --- |
| search complexes·region-real-price·region-reviews | `region.name`(전체 이름) | `region.name`(가장 작은 단위 이름) + `region.sido`·`region.sigungu`·`region.dong` | 값 표기 바뀜 |
| compare | `address` | `address + road_address` | 값 표기 바뀜 |
| compare | `approved_at` | `approved_date` |  |
| compare | `asking` | `asking_averages` | 모양 바뀜 |
| compare | `average_manwon` | `price_manwon / deposit_manwon` |  |
| compare | `buildings` | `dong_count` |  |
| compare | `contract_date` | `trade_date` |  |
| compare | `exclusive_area_m2` | `area_m2` |  |
| compare | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| compare | `households` | `household_count` |  |
| compare | `jeonse` | `asking_averages.jeonse` |  |
| compare | `kb_jeonse` | `pyeong.estimated_prices.jeonse` | 모양 바뀜 |
| compare | `kb_monthly` | `pyeong.estimated_prices.wolse` | 모양 바뀜 |
| compare | `kb_sale` | `pyeong.estimated_prices.sale` | 모양 바뀜 |
| compare | `kb_survey_date` | `pyeong.estimated_prices.base_date` | 모양 바뀜 |
| compare | `max_floor` | `building_floor_range.highest` | 모양 바뀜 |
| compare | `min_floor` | `building_floor_range.lowest` | 모양 바뀜 |
| compare | `monthly_deposit` | `asking_averages.wolse` |  |
| compare | `recent_jeonse` | `pyeong.latest_trades.jeonse` | 모양 바뀜 |
| compare | `recent_monthly` | `pyeong.latest_trades.wolse` | 모양 바뀜 |
| compare | `recent_sale` | `pyeong.latest_trades.sale` | 모양 바뀜 |
| compare | `sale` | `asking_averages.sale` |  |
| compare | `station` | `name` |  |
| compare | `subways` | `stations` |  |
| compare | `type` | `complex_type` |  |
| complex | `approved_at` | `approved_date` |  |
| complex | `building_coverage_ratio` | `building_coverage_ratio_percent` |  |
| complex | `exclusive_m2` | `area_m2` |  |
| complex | `exclusive_pyeong` | `area_pyeong` |  |
| complex | `floor_area_ratio` | `floor_area_ratio_percent` |  |
| complex | `heating` | `heating + heating_fuel` | 값 표기 바뀜 |
| complex | `highest_top_floor` | `building_floor_range.highest` | 모양 바뀜 |
| complex | `households` | `household_count` |  |
| complex | `lowest_top_floor` | `building_floor_range.lowest` | 모양 바뀜 |
| complex | `nearby_subways` | `nearby_stations` |  |
| complex | `property_type` | `complex_type` |  |
| complex | `supply_m2` | `supply_area_m2` |  |
| complex | `supply_pyeong` | `supply_area_pyeong` |  |
| listing | `watch_count` | `favorite_count` |  |
| nearby-complexes | `households` | `household_count` |  |
| nearby-complexes | `type` | `complex_type` |  |
| preschool | `established_at` | `established_date` |  |
| preschool | `id` | `preschool_id` |  |
| preschool | `open_time` | `operating_hours` |  |
| preschool | `opened_at` | `opened_date` |  |
| preschool | `school_bus` | `has_school_bus` |  |
| preschools | `distance_km` | `distance_m` | 값 표기 바뀜 |
| preschools | `id` | `preschool_id` |  |
| price-trend | `high_manwon` | `estimated_prices.sale.high_manwon` | 모양 바뀜 |
| price-trend | `kb_sale` | `estimated_prices` | 모양 바뀜 |
| price-trend | `low_manwon` | `estimated_prices.sale.low_manwon` | 모양 바뀜 |
| price-trend | `months` | `summary.span_months` |  |
| price-trend | `points` | `months` |  |
| price-trend | `recent_transactions` | `recent_trade_count` |  |
| price-trend | `survey_date` | `estimated_prices.base_date` | 모양 바뀜 |
| price-trend | `total_transactions` | `total_trade_count` |  |
| price-trend | `transaction_count` | `months[].trade_count` |  |
| price-trend | `year_month` | `months[].month` |  |
| real-price (·--item) | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| real-price (·--item) | `since` | `start_date` |  |
| real-price (·--item) | `transactions` | `trades` |  |
| region-real-price | `approved_at` | `approved_date` |  |
| region-real-price | `data_date` | `latest_published_date` |  |
| region-real-price | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| region-real-price | `households` | `household_count` |  |
| region-real-price | `is_new_high` | `new_high` |  |
| region-real-price | `new_high` | `new_high_only` |  |
| region-real-price | `previous_high_change_percent` | `prev_high_diff_percent` |  |
| region-real-price | `previous_high_date` | `prev_high_date` |  |
| region-real-price | `previous_high_manwon` | `prev_high_manwon` |  |
| region-real-price | `published_at` | `published_date` |  |
| region-real-price | `transactions` | `trades` |  |
| region-reviews | `jibun_address` | `address` |  |
| region-reviews | `property_type` | `complex_type` |  |
| school | `stats_year` | `base_year` | 값 표기 바뀜 |
| school | `total_complexes` | `total` |  |
| search commute | `from_station` | `from_station_name` |  |
| search commute | `reachable_stations` | `reachable_station_count` |  |
| search commute | `to_station` | `to_station_name` |  |
| search commute | `walk_to_station_minutes` | `walk_minutes` |  |
| search complexes·nearby-complexes·school | `listing_counts` | `listing_counts` | 이름은 같고 키만 `매매`·`전세`·`월세` 에서 `sale`·`jeonse`·`wolse` 로 바뀜 |
| search complexes·school | `approved_at` | `approved_date` |  |
| search complexes·school | `households` | `household_count` |  |
| search complexes·school | `property_type` | `complex_type` |  |
| search listings --address | `place` | `building_name` |  |
| search listings --address | `region_address` | `address` |  |
| search listings·search complexes·nearby-complexes·popular-listings | `name1` | `region.sido` | 모양 바뀜 |
| search listings·search complexes·nearby-complexes·popular-listings | `name2` | `region.sigungu` | 모양 바뀜 |
| search listings·search complexes·nearby-complexes·popular-listings | `name3` | `region.dong` | 모양 바뀜 |
| search locations | `keyword` | `query` |  |
| search locations | `property_type` | `complex_type` |  |
| search locations | `results` | `regions` |  |
| search locations | `results[].name1·name2·name3` | `regions[].{name, sido, sigungu, dong}` | 모양 바뀜 |
| trending-complexes | `approved_at` | `approved_date` |  |
| trending-complexes | `households` | `household_count` |  |
| trending-complexes | `recent_sale_manwon` | `latest_trades.sale.price_manwon` | 모양 바뀜. 최근 매매 없음·0 은 `{}`, 모름은 `sale: null` |
| trending-complexes | `region.name`(전체 이름) | `region.name`(가장 작은 단위 이름)·`region.sido`·`region.sigungu` | 뜻 바뀜 |
| trending-complexes | `type` | `complex_type` |  |

## 다방

| 명령 | 옛 이름 | 새 이름 | 비고 |
| --- | --- | --- | --- |
| complex | `approved_at` | `approved_date` |  |
| complex | `builder` | `construction_company` |  |
| complex | `building_count` | `dong_count` |  |
| complex | `building_coverage_ratio` | `building_coverage_ratio_percent` |  |
| complex | `code` | `school_code` |  |
| complex | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| complex | `floor_area_ratio` | `floor_area_ratio_percent` |  |
| complex | `fuel` | `heating_fuel` |  |
| complex | `highest_floor` | `building_floor_range.highest` | 모양 바뀜 |
| complex | `lowest_floor` | `building_floor_range.lowest` | 모양 바뀜 |
| complex | `price_manwon` | `latest_trades.sale.price_manwon / latest_trades.jeonse.deposit_manwon` |  |
| complex | `primary_space_seq` | `representative_pyeong_id` |  |
| complex | `recent_deal_count` | `recent_trade_count` |  |
| complex | `recent_lease` | `latest_trades.jeonse` | 모양 바뀜 |
| complex | `recent_sale` | `latest_trades.sale` | 모양 바뀜 |
| complex | `space_seq` | `pyeong_id` |  |
| complex·nearby-complexes | `lease_per_pyeong_manwon` | `area_prices[].price_per_pyeong.jeonse.price_per_pyeong_manwon` | 모양 바뀜 |
| complex·nearby-complexes | `sale_per_pyeong_manwon` | `area_prices[].price_per_pyeong.sale.price_per_pyeong_manwon` | 모양 바뀜 |
| listing | `lh_lease` | `lh_jeonse` |  |
| listing | `short_lease_term` | `short_term_period` |  |
| nearby | `id` | `listing_id / complex_id / presale_id` |  |
| nearby-complexes | `lease_nearby` | `nearby.jeonse` | 모양 바뀜 |
| nearby-complexes | `per_pyeong_manwon` | `price_per_pyeong_manwon` |  |
| nearby-complexes | `sale_nearby` | `nearby.sale` | 모양 바뀜 |
| nearby-complexes | `space_seq` | `pyeong_id` |  |
| nearby-complexes | `years` | `occupancy_years` |  |
| neighborhood | `district` | `sigungu_rank` |  |
| neighborhood | `district_name` | `sigungu` |  |
| neighborhood | `lease` | `counts.jeonse` | 모양 바뀜 |
| neighborhood | `lease_average_manwon` | `trade_averages.jeonse.deposit_manwon` | 모양 바뀜 |
| neighborhood | `national` | `national_rank` |  |
| neighborhood | `rank` | `ranking` |  |
| neighborhood | `rent` | `counts.wolse` | 모양 바뀜 |
| neighborhood | `sale` | `counts.sale` | 모양 바뀜 |
| neighborhood | `sale_average_manwon` | `trade_averages.sale.price_manwon` | 모양 바뀜 |
| neighborhood | `state` | `sido_rank` |  |
| neighborhood | `state_name` | `sido` |  |
| neighborhood | `total` | `listings.count / trades.count` |  |
| neighborhood | `total` | `count` |  |
| neighborhood | `total` | `population` |  |
| neighborhood | `type` | `property_type` |  |
| neighborhood | `type` | `complex_type` |  |
| price-trend | `highest_manwon` | `trade_ranges.{거래}.{기간}.highest.{price_manwon\|deposit_manwon}` | 모양 바뀜 |
| price-trend | `lease_1y` | `trade_ranges.jeonse.one_year` | 모양 바뀜 |
| price-trend | `lease_3y` | `trade_ranges.jeonse.three_years` | 모양 바뀜 |
| price-trend | `lease_average_manwon` | `trade_averages.jeonse.deposit_manwon` | 모양 바뀜 |
| price-trend | `lease_average_manwon` | `months[].trade_averages.jeonse.deposit_manwon` | 모양 바뀜 |
| price-trend | `lease_count` | `months[].trade_counts.jeonse` | 모양 바뀜 |
| price-trend | `lease_rate_percent` | `jeonse_ratio_percent` |  |
| price-trend | `lease_rate_percent` | `months[].jeonse_ratio_percent` |  |
| price-trend | `lowest_manwon` | `trade_ranges.{거래}.{기간}.lowest.{price_manwon\|deposit_manwon}` | 모양 바뀜 |
| price-trend | `rent_count` | `months[].trade_counts.wolse` | 모양 바뀜 |
| price-trend | `sale_1y` | `trade_ranges.sale.one_year` | 모양 바뀜 |
| price-trend | `sale_3y` | `trade_ranges.sale.three_years` | 모양 바뀜 |
| price-trend | `sale_average_manwon` | `trade_averages.sale.price_manwon` | 모양 바뀜 |
| price-trend | `sale_average_manwon` | `months[].trade_averages.sale.price_manwon` | 모양 바뀜 |
| price-trend | `sale_count` | `months[].trade_counts.sale` | 모양 바뀜 |
| price-trend | `sale_per_pyeong_manwon` | `trade_averages.sale.price_per_pyeong_manwon` | 모양 바뀜 |
| price-trend | `space_seq` | `pyeong_id` |  |
| real-price | `direct` | `deal_type` | 값 표기 바뀜 |
| real-price | `floor` | `floor + floor_number` | 값 표기 바뀜 |
| real-price | `from_month` | `start_month` |  |
| real-price | `space_seq` | `pyeong_id` |  |
| real-price | `to_month` | `end_month` |  |
| real-price | `trade` | `trade_tab` |  |
| real-price | `transactions` | `trades` |  |
| region-ranking | `building_type` | `property_type` |  |
| region-ranking | `code` | `scope.legal_division_code` | 값 표기 바뀜 |
| region-ranking | `prev_price_date` | `prev_price_month` | 값 표기 바뀜 |
| region-ranking | `price_date` | `price_month` | 값 표기 바뀜 |
| region-ranking | `pyeong` | `pyeong_name` |  |
| sale | `basement_floors` | `basement_floor` |  |
| sale | `builder` | `construction_company` |  |
| sale | `building_count` | `dong_count` |  |
| sale | `building_type` | `complex_type` |  |
| sale | `competition_rate` | `competition_ratio` |  |
| sale | `end` | `end_date / end_month` | 모양 바뀜 |
| sale | `floors` | `building_floor` |  |
| sale | `subscription_result.pyeongs[].household_count` | `subscription_result.pyeongs[].presale_household_count` | 상세의 `household_count`(총세대수)와 `pyeongs[].household_count` 는 그대로 |
| sale | `max_competition_rate` | `highest_competition_ratio` |  |
| sale | `min_winning_point` | `lowest_winning_point` |  |
| sale | `price_max_manwon` | `price_range.highest.price_manwon` | 모양 바뀜. 임대가면 `deposit_manwon` |
| sale | `price_min_manwon` | `price_range.lowest.price_manwon` | 모양 바뀜. 임대가면 `deposit_manwon` |
| sale | `pyeongs[].price_manwon` | `pyeongs[].deposit_manwon` | 임대가(공공·민간임대)일 때만. 분양가는 그대로 |
| sale | `region_average_price_per_pyeong_manwon` | `region_price_per_pyeong_average_manwon` |  |
| sale | `sale_household_count` | `presale_household_count` |  |
| sale | `sale_id` | `presale_id` |  |
| sale | `start` | `start_date / start_month` | 모양 바뀜 |
| sale | `state` | `status` |  |
| sale-schedule | `building_type` | `complex_type` |  |
| sale-schedule | `from_date` | `start_date` |  |
| sale-schedule | `region` | `sido` |  |
| sale-schedule | `sale` | `presale` |  |
| sale-schedule | `sale.price_manwon` | `presale.deposit_manwon` | 임대가(공공·민간임대)일 때만. 분양가는 `presale.price_manwon` |
| sale-schedule | `sale_household_count` | `presale_household_count` |  |
| sale-schedule | `sale_id` | `presale_id` |  |
| sale-schedule | `state` | `status` |  |
| sale-schedule | `to_date` | `end_date` |  |
| school | `city_average` | `sido_average` |  |
| school | `district_average` | `sigungu_average` |  |
| school | `homepage` | `homepage_url` |  |
| school | `stats_period` | `base_period` |  |
| school | `url` | `disclosure_url` |  |
| search complexes | `lease_listing_count` | `listing_counts.jeonse` | 모양 바뀜 |
| search complexes | `recent_lease_manwon` | `latest_trades.jeonse.deposit_manwon` | 모양 바뀜 |
| search complexes | `recent_sale_manwon` | `latest_trades.sale.price_manwon` | 모양 바뀜 |
| search complexes | `rent_listing_count` | `listing_counts.wolse` | 모양 바뀜 |
| search complexes | `sale_listing_count` | `listing_counts.sale` | 모양 바뀜 |
| search complexes | `years` | `occupancy_years` |  |
| search listings --complex | `space_seqs` | `pyeong_ids` |  |
| search listings·--complex·popular-listings | `short_lease` | `short_term` |  |
| search locations | `sales` | `presales` |  |
| search locations | `sales[].sale_id` | `presales[].presale_id` |  |
| search locations | `sales[].state` | `presales[].status` |  |
| search sales | `building_type` | `complex_type` |  |
| search sales | `price_manwon` | `presales[].deposit_manwon` | 임대가(공공·민간임대)일 때만. 분양가는 `presales[].price_manwon` |
| search sales | `sale_household_count` | `presale_household_count` |  |
| search sales | `sale_id` | `presale_id` |  |
| search sales | `sales` | `presales` |  |
| search sales | `state` | `status` |  |
| station-prices | `building_type` | `property_type` |  |
| station-prices | `lease_average_manwon` | `asking_averages.jeonse.deposit_manwon` | 모양 바뀜 |
| station-prices | `rent_average_manwon` | `asking_averages.wolse.rent_manwon` | 모양 바뀜 |
| station-prices | `rent_deposit_average_manwon` | `asking_averages.wolse.deposit_manwon` | 모양 바뀜 |
| station-prices | `room` | `room_type` |  |
| station-prices | `station` | `station_name` |  |
| trade-rankings | `trade` | `trade_type` |  |
| trade-rankings | `years` | `occupancy_years` |  |
| trending-complexes | `view_count` | `viewer_count` |  |
