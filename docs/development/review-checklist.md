# 리뷰 체크리스트

[코드 리뷰 절차](agents.md#코드-리뷰) · [꼭 지킬 것](../../AGENTS.md#꼭-지킬-것) · [출력 규약](output-contract.md) · [웹 화면과의 대응](provider-conventions.md#웹-화면과의-대응)

지난 리뷰에서 실제로 나온 버그 패턴과 되풀이된 오탐을 관점별로 모았다. 리뷰어는 여섯 관점 절의 항목을 하나씩 바뀐 코드에 대
보고(해당 없는 항목은 건너뛴다), 그다음 목록에 없는 문제도 찾는다. 코드·문서를 고친 쪽(작업자·주 에이전트)도 끝내기 전에
자기 변경에 **언제** 신호가 있는 항목을 대 본다 ([검증 분담](agents.md#검증-분담)). 규칙 자체는 위 링크 문서에 있고 여기에는 옮겨 적지 않는다.

- 항목의 **언제** 는 그 항목을 볼 diff 의 신호다. 신호가 있으면 그 자리를 **확인** 대로 따라가고, 신호가 없어도 바뀐 코드가 그
  항목의 흐름에 닿으면 본다. 항목은 `<관점 키>-<번호>`(예: `correctness-4`)로 부른다.

- 진짜 문제의 가장 큰 덩어리는 **출력 값은 맞는데 안내(`notes`·`hint`)가 틀린 것**이다. 관점과 상관없이 첫 질문은 "이 안내를
  그대로 따라 하면 성공하는가" 다.
- 사례 경로는 `src/jibsa/` 기준이고 줄 번호는 적은 날의 것이라, 어긋나면 그 자리 주석의 날짜로 찾는다.
- 새 패턴을 더하는 법은 [코드 리뷰](agents.md#코드-리뷰) 6단계다.

## `correctness` 정확성·버그

1. **쪽 넘기기의 멈춤 조건.** 서버가 "더 있음" 이라면서 다음을 주지 않는 네 경우(빈 쪽, 커서 없음, 같은 커서 되풀이,
   pageInfo null)에 멈추고 알리는가. 되풀이된 쪽은 세기 전에 멈추고, `hasNext=false` 인 마지막 쪽을 되풀이로 보지 않는가.
   확인: 루프의 break 조건을 다섯 입력으로 따라가 `has_more`·`notes`·센 수를 본다. 예: `providers/daangn/service/common.py:754`
   (pageInfo null 에 조용히 끝나 일부를 전부처럼 냄), `providers/daangn/service/real_price.py:385` (마지막 쪽을 되풀이로 봄).
   언제: 쪽을 넘기는 루프(커서·offset·`has_next`·`hasMore`)나 그 `break` 를 바꾼 diff.
2. **"더 있음" 을 무엇으로 정하나.** `has_more`·`[일부]` 는 받은(확인한) 수 `inspected`·`received` 로 정한다. 뺀 뒤 돌려준 수나
   뺀 것까지 센 `total` 과 견주지 않는다. 서버가 준 총수(`total`·`count`)가 받은 수보다 커도 서버가 더 줄 것이 없으면(마지막 쪽이
   모자람, 요청한 수보다 적게 옴) 더 있음이 아니다 (총수와 목록이 어긋난 것을 `[참고]` 로 알린다). 확인: "다 받고 1건 뺌" 과
   "limit 에 닿고 1건 뺌", "총수 15·받은 수 13·마지막 쪽 3건" 으로 따라간다.
   예: `providers/zigbang/service/common/apt.py` `apt_pagination_notes`, `providers/zigbang/service/local/ranking.py`
   `get_region_ranking`·`providers/zigbang/service/local/trades.py` `get_region_trades` (순위 수·실거래 수가 받은 수보다 크면
   끝까지 받았는데도 '--limit 을 늘리세요' `[일부]`, 2026-11-22).
   언제: `has_more`·`[일부]`·`inspected`·`received`·`total` 을 정하는 줄이나 결과를 빼는(거르는) 줄을 바꾼 diff.
3. **덜 받은 것을 "전부·없음" 으로 단정.** 첫 쪽·상한·멈춘 목록의 수를 전체 수로 쓰거나, 남았는데 "없습니다"·"이 N건이 전부"
   라고 하지 않는가 ('이상'·`[일부]`·`null` 로 알린다). 확인: 수·'없'·'전부' 가 든 안내마다 그 수가 끝까지 받은 수인지 본다.
   예: `providers/daangn/service/region.py:575` (첫 쪽 100곳을 "100곳 있습니다", 실제 208곳).
   언제: 수를 담은 안내('곳'·'건'·'없'·'전부')나 `total` 을 쓰는 `+` 줄.
4. **후보를 다 모은 뒤 판정하나.** "하나뿐"·"없음"·"이름이 같은 것이 여럿" 을 판정하는 목록이 그 시점에 완전한가.
   - 좌표 없음 같은 이유로 **거른 뒤** 개수를 세지 않는가 (웹에는 후보가 둘인데 남은 하나를 고름).
   - 전체 수는 거르기 전 목록으로 셌어도, 그 안의 하위 판정(정확히 같은 이름 하나 고르기 등)을 거른 목록에서 세지 않는가 (거른 목록에서
     세면 같은 이름이 둘인데 하나뿐인 줄 알고 고른다). 예: `providers/daangn/service/region.py` `find_address` (정확 일치를 쓸 수 있는
     후보에서만 세어 같은 도로명 후보 중 건물 정보 있는 쪽을 말없이 골랐다, 2026-11-20).
   - **첫 쪽만** 보고 고르지 않는가 (다음 쪽이 있으면 뒤에 같은 이름이 더 있을 수 있다).
   - 여럿일 때 일찍 멈춰 빠뜨리지 않는가, 에러에 합친 이름이 아니라 실패한 이름을 대는가.
   - 여러 단어 검색어('수정구 신흥')에서 전체와 끝 단어를 섞어 비교하지 않는가.
   - 멈추는 데만 쓰던 결과("여럿이면 멈춘다")를 고르는 데("하나뿐이면 고른다")에도 쓰게 바꿨으면, 그 하나가 고르려는 것과 같은
     곳인지 대조하는가. 다른 자료(주소 검색 ↔ 자동완성)의 한 건은 다른 곳일 수 있다. 예: `providers/naver/service/region.py:269`
     (bcode 대조 없이 주소 검색 1건으로 자동완성 동을 골랐다, 2026-11-16).
   - "다 봤는지" 플래그로 고르는 판정에 `or` 로 붙은 다른 조건(후보가 하나뿐)이 그 플래그를 건너뛰지 않는가. 예:
     `providers/daangn/service/school.py` `resolve_school` (`len(candidates) == 1 or (len(exact) == 1 and checked)` 가 다음 쪽을 확인하지
     못했는데도 골랐다, 2026-11-22).
   - 거른 후보(쓸 수 없는 후보)를 같은 이름 수에 세는 처리가, 남은 후보가 0일 때도 닿는가. 남은 후보가 있는 갈래 안에서만 세면, 0일 때
     다음 갈래가 "이름이 같은 곳이 없다" 고 한다. 예: `providers/daangn/service/region.py` `resolve_area` (쓸 수 없는 같은 이름 동뿐이면
     '비슷한 지역' 으로 내려갔다, 2026-11-22).

   확인: 후보 목록에 걸린 `len(...) == 1`·`break`·`next(...)`·`[0]` 자리마다 그 목록이 어디서 왔는지 거슬러 본다.
   예: `providers/naver/service/region.py:225`·`:231`·`:254` (2026-11-16), `providers/daangn/service/school.py:204`.
   언제: 후보 목록에 `len(...) == 1`·`next(`·`[0]`·`break` 가 걸린 `+` 줄, 또는 이름·주소로 후보를 고르거나 거르는 줄,
   `> 1` 로 멈추던 결과에 `== 1` 갈래를 더한 diff. 한 자동완성 판정(다음 쪽·좌표 없는 후보)을 고친 diff 면 같은 자동완성을 쓰는
   짝 함수(동·역·단지·`regions`)도 본다. 예: `providers/naver/service/region.py:369`·`:1226` (동·단지만 고치고 역·`regions` 가
   첫 쪽만 봤다, 2026-11-17).
5. **누락값과 0.** 실패·모름은 `null`, 해당 없음은 키 삭제, 정말 빈 것만 `[]` 인가. `or`·`or 0`·`or inf`·`if not x` 로 0 과
   모름을 섞지 않는가. 날짜·층·이름·시각 자리와 `LABELS.get(raw or '', raw)` 같은 라벨 표 찾기에서 `'-'`·빈 글자를 그대로
   내지 않는가 (`.get` 의 두 번째 인자가 빈 글자를 돌려준다). 확인: 새 `or ...`·truthiness·기본값 `[]`·except 가 돌려주는 값을
   본다. 예: `cli/daangn.py:816` (실패한 칸을 `[]` 로), `providers/naver/service/listing.py:1003` ('-', 2026-11-16), 같은 파일 `get_listing` 의 `bool(article and article.is_direct_trade)` (직거래 여부를 모를 때를 '직거래 아님' 으로 보고 중개보수를 냈다, 2026-11-17),
   `providers/zigbang/service/stay/detail.py` 의 `stay_detail_to_listing` (입·퇴실 방식·주차 방식 빈 글자, 2026-11-17),
   `providers/zigbang/service/complex/trend.py` `_compare_candidates` (비교 후보 목록 null 을 `or []` 로 읽어 '후보를 주지 않는 단지'
   `INVALID_ARGUMENT` 를 냈다. 같은 함수의 비교 없는 갈래는 같은 null 을 모름으로 읽었다, 2026-11-22).
   언제: `+` 줄에 `or `·`if not `·`else None`·기본값 `[]`·값을 돌려주는 `except` 가 있을 때, 출력 필드를 더하거나 바꾼 diff.
6. **서버 값 한 칸이 결과 전체를 깨뜨림.** 서버 글자·목록·헤더를 `int()`·`[0]`·`del`·`.encode` 로 바로 다루지 않는가 (그 칸만
   `null`·건너뛰기여야 한다). 확인: diff 의 그 호출과 Optional 아닌 list 필드에 빈 글자·'-'·null·소수를 넣어 본다.
   예: `providers/daangn/service/compare.py:533` (연월 `int()` 로 비교 전체가 PARSE_ERROR).
   언제: 서버 값에 `int(`·`float(`·`[0]`·`del `·`.split(`·`.encode` 를 바로 쓰는 `+` 줄, `api/response/` 의 필드 자료형을 바꾸거나
   응답 모델을 새로 더한 diff (나눗셈·평균으로 나오는 값(원/평 등)을 `int` 로 받으면 소수 한 행에 ValidationError 가 나고, 덤
   조회면 `result_or_empty` 가 삼켜 목록 전체가 `null` 이 된다: `providers/naver/api/response/real_price.py`
   `NaverVillaPyeongPriceModel.pyeong_price`, 2026-11-19). 한 필드를 이 이유로 `float` 로 바꿨으면 같은 응답 모델 파일들의 다른 평균·나눗셈 필드(`average*`·`avg*`·`*AverageFee`)도 함께 본다 (2026-11-19 네이버 빌라 real-price 리뷰: 평당 호가 둘만 바꾸고 평균 관리비·시세 평균·실거래 평균·주간 평균 매물 수를 `int` 로 남김). 개수 평균은 출력 모델도 `int | float` 로 바꿔야 하고, `float` 만 쓰면 정수가 `1006.0` 으로 나가 출력이 바뀐다.
7. **지운 줄이 받던 입력.** `git diff` 의 `-` 줄이 받던 꼴(더 짧은 날짜, 다른 구분자, 빈 값)을 `+` 줄도 받는가. 고친 코드가
   예전보다 정보를 버리면 퇴보다. 확인: 지운 분기와 새 분기에 같은 입력을 넣어 비교한다.
   예: `providers/naver/service/listing.py:151` (연월만 온 날짜의 '초순' 이 빠졌다, 2026-11-16).
   언제: 파싱·분기·검사의 `-` 줄을 다른 코드로 바꾼 diff (지우기만 한 줄도).
8. **`--next` 로 이어 받을 때.** 첫 쪽 전용 안내를 되풀이하지 않는가, 앞 쪽의 모름(total None, 실패)을 이어 쓰지 않는가, 이어
   받은 첫 쪽이 비거나 null 일 때 "다 받음" 으로 끝내지 않는가. 확인: `resumed` 갈래마다 첫 쪽·이어 받은 쪽을 따라간다.
   예: `providers/daangn/service/search.py:381`, `providers/dabang/service/common.py:709`.
   언제: `resumed`·`--next`·커서 이어 받기(`cli/paging.py` 포함)를 건드리거나, 첫 쪽에만 붙는 안내를 더한 diff.
9. **실패·취소 경로 (주로 `core/`).** 예외·Ctrl+C·다른 프로세스와 겹칠 때 브라우저·잠금·쿠키 파일을 정리하는가, 다른 프로세스가
   새로 쓴 파일을 덮지 않는가, 잠깐의 실패에 오래 남는 상태를 만들지 않는가. 예: `core/browser.py:1389`·`:1308`·`:1667`.
   언제: `core/` 의 `try`·`except`·`finally`·잠금·파일 쓰기·브라우저 열고 닫기를 바꾼 diff.
10. **공백뿐이거나 앞뒤 공백이 붙은 사용자 입력.** 앞뒤 공백을 떼지 않으면 이름 비교(`==`·`endswith`)가 어긋나 맞는 후보를
    못 찾는다 (웹 검색창은 trim 해서 보낸다). 예: `providers/naver/service/region.py:839` ('파크리오 ' 가 후보 3곳으로 멈췄다,
    2026-11-17). 위치·이름 인자는 `min_length=1` 을 공백(`' '`)으로 지나므로 `.split()[-1]`·`[0]` 이 IndexError
    (INTERNAL_ERROR)가 된다. 서버가 빈 응답을 줘서 지금 안 닿는 것은 막는 이유가 아니다. 확인: `' '` 를 넣어 그 줄까지 따라간다.
    예: `providers/naver/service/region.py:221` (`words[-1]`, 요청 전에 `:843` 에서 INVALID_ARGUMENT 로 막았다, 2026-11-16).
    언제: 사용자 검색어에 `.split()`·인덱스를 쓰는 줄을 조건 밖으로 옮기거나 새로 더한 diff.
11. **목록 여럿을 이어 낼 때 쪽 사이 겹침과 자리.** 서로 겹치는 목록(직방 원룸 목록의 '이 지역 오피스텔' 과 오피스텔 목록)을
    이어 내며 겹침을 한 호출 안에서만 빼면, `--next` 의 다음 쪽에 앞 쪽 매물이 다시 나오고, 목록마다의 자리를 더한 수가 서로 다른
    매물 수(`total`)를 넘어 더 있는데도 `[일부]` 가 사라진다. 커서 하나로 이은 쪽은 겹치지 않아 해당 없다 (아래 "지적하지 말 것"
    3). 확인: 겹치는 두 목록으로 이어 받기를 끝까지 따라가 쪽마다 앞 쪽과 같은 ID 수와 `offset + returned` 를 `total` 과 견준다.
    예: `providers/zigbang/service/room/search.py` 의 `_collect_pins` (받기 전에 앞 목록의 ID 를 뒤 목록에서 뺐다, 2026-11-16).
    언제: 목록·종류 여럿을 한 결과로 잇고 이어 받기 표에 목록마다의 자리를 두는 diff.
12. **묶음 한 줄의 대표 값과 고른 `id`.** 서버가 여러 매물을 한 줄로 묶어 줄 때 그 줄의 종류·제목·층 같은 필드는 묶음 안 어느
    매물의 값인지 보고, `id` 를 서버와 다른 순서(출처 우선 등)로 고르면 `id` 와 그 필드가 다른 매물을 가리킨다. 확인: 섞인 묶음의
    원본 응답에서 목록 순서와 대표 필드를 대 보고, 줄의 필드를 `id` 상세와 견준다.
    예: `providers/zigbang/service/common/apt.py` 의 `catalog_to_listing` (직방 먼저 고른 `id` 가 중개사인데 `listing_kind` 는 집주인, 2026-11-17).
    언제: 묶음·카탈로그 줄에 필드를 더하거나 묶인 ID 중 대표를 고르는 순서를 정·바꾸는 diff.
13. **해당 없음으로 키를 뺀 필드에 조건을 걸 때.** 키를 뺀 매물도 내부 값은 `None` 이라 `in_range` 같은 거르기가 '모름' 처럼
    조용히 뺀다. 그 조건으로 뺀 해당 없음 매물을 `[제외]` 로 알리거나 문서에 적었는가. 확인: 키를 빼는 조건(`not_applicable_fields`)과
    같은 필드의 거르기 함수를 나란히 보고, 그 매물이 있는 범위에 조건을 걸어 notes 를 본다.
    예: `providers/zigbang/service/store.py:556` (권리금 조건에 사무실이 말없이 빠졌다, 2026-11-17).
    언제: `not_applicable_fields` 에 값에 따라 빠지는 키를 더하는 diff, 또는 그런 필드에 거르기 조건을 더하는 diff.
14. **모르는 값을 같은 diff 안에서 같은 기준으로 다루는가.** 값이 `None`·빈 글자일 때 한 곳은 '요청하지 않음', 다른 곳은 '요청함' 이거나
    한 필드는 키를 빼고 다른 필드는 `null` 로 두지 않는가 (같은 모름을 요청할지·키를 뺄지로 갈라 쓰지 않는다). 확인: 같은 입력(상태 `None`,
    `''`)을 요청 조건·키 제거 조건·출력 값 세 곳에 넣어 같은 결론인지 본다. 예: `providers/naver/service/listing.py:383`
    (`_draws_sale_taxes`, 분양 상태를 모를 때 요청 조건과 키 제거 조건이 한 판정을 쓰게 했다, 2026-11-17).
    언제: 직거래 여부·분양 상태처럼 '있는지 모르는' 값으로 요청이나 키 제거를 정하는 `+` 줄, 같은 값을 읽는 조건이 둘 이상 생긴 diff.
15. **0 을 `null` 로 바꾸면 같은 점의 파생 값도.** 시세 평균·범위의 0 을 시세 없음으로 바꾸면서 같은 점의 전세가율 같은 파생
    값(`[0, 0]`)을 그대로 두지 않는가. 확인: 바꾼 필드와 같은 응답 항목에서 나오는 다른 필드를 모두 보고 같은 0 을 넣어 본다.
    예: `providers/naver/service/common.py` 의 `manwon_range` (전세가율 `[0, 0]`, 2026-11-17).
    언제: 0·빈 값을 `null` 로 바꾸거나 거르는 `+` 줄 (같은 응답 항목에서 다른 필드를 함께 내는 곳).
16. **덤 조회 실패를 '빈 결과' 로 보고 대체 조회로 넘어가지 않는가.** `result_or_none` 처럼 실패와 빈 응답을 둘 다 `None` 으로
    주는 결과로 '비면 더 넓게 다시 묻기' 를 정하면, 실패가 다른 기간·범위의 값으로 나간다. 확인: 실패(`None`)와 빈 객체를 가르는
    갈래가 있는지 본다. 예: `providers/naver/service/complex.py` `_pyeong_details` (3년 요약 조회 실패를 거래 없음으로 보고
    5년 요약에 `since` 를 붙였다, 2026-11-18).
    언제: 결과가 비면 다른 조건으로 다시 묻는 대체 조회를 더한 diff.
17. **키가 없으면 `[]` 로 채우는 목록에서 계산한 값.** 응답 모델이 키가 없을 때 `[]` 를 채우는 목록(`default_factory=list`)에 `any`·`in`·개수를 계산하면, 목록을 받지 못한 모름이 '없음·불가(`false`·`0`)' 로 바뀐다. 같은 출력의 그 목록 필드를 `sent_or_none` 으로 `null` 로 낸다면 거기서 계산한 값도 `null` 인가. 확인: `any(`·`len(` 이 도는 응답 목록이 보냈는지(`model_fields_set`)를 먼저 가르는지 본다.
    바깥 연결 자체가 `null` 로 오는 경우도 같다: 안쪽 목록(`edges`)만 `null` 일 때는 모름으로 내면서 바깥 연결이 `null` 일 때
    `[]`·`false` 로 내지 않는가. 예: `providers/zigbang/service/stay/detail.py` `stay_detail_to_listing` 의 `pet_allowed` 계산 줄 (2026-11-17),
    `providers/daangn/service/common.py` 단지 카드의 `recent_trades`·`has_reviews` (`transactions`·`lived_reviews` 가 `null` 이면 '없음' 이었다, 2026-11-20).
    언제: 응답 목록 필드에 `any(`·`in`·`len(` 을 걸어 출력 필드(bool·수)를 정하는 `+` 줄, 응답의 연결·목록 칸을 `| None` 으로 바꾼 diff.
18. **모델 전체에 거는 검증기가 `| None` 칸까지 바꾸지 않는가.** 기반 응답 모델의 검증기(`validate_dropping_nulls` 가 부르는 `drop_null_lists`)가 기본값이 목록인 칸의 null 을 지우면, `list | None = []` 처럼 null 을 모름으로 읽는 칸의 모름이 없음(`[]`)으로 바뀐다. 확인: 검증기가 고르는 칸의 조건에 `| None` 을 받는 칸이 빠지는지, 그 칸을 읽는 서비스가 `None` 과 `[]` 를 가르는지 본다.
    예: `core/schema.py` `drop_null_lists` (다방 단지 학교·어린이집, 네이버 재개발 역·지구의 모름이 `[]` 가 되었다, 2026-11-20).
    언제: 응답 모델 전체에 걸리는 검증기·기반 모델의 필드 처리를 더하거나 고친 diff.
19. **좌표를 쓰지 않는 경로가 좌표를 요구하지 않는가.** 같은 해석 함수의 결과(`ZigbangRegion`)를 좌표를 쓰는 경로(room·store·stay 의 검색 중심)와 쓰지 않는 경로(아파트 동·구, `search complexes`)가 함께 쓰면, 쓰지 않는 쪽도 좌표 없는 후보에서 에러가 난다. 확인: 그 경로가 실제로 읽는 칸(법정동 코드·이름·주소)이 무엇인지 보고, 좌표가 없는 후보를 넣어 본다.
    예: `providers/zigbang/service/region.py` `resolve_apt_region` (아파트 동·구가 `region_from_search_item` 의 좌표 검사를 거쳐 좌표 없는 후보에서 `UPSTREAM_ERROR` 였다, 2026-11-21).
    언제: 지역·역·학교 해석 함수를 고치거나 새 경로가 부르게 한 diff, 같은 명령 안에서 경로마다 쓰는 칸이 다른 해석.
20. **응답 객체 목록의 길이·합으로 계산하거나 자리를 세는 코드가 뺀 빈 항목을 보는가.** 기반 모델이 목록 안 null 원소를 빼고 칸마다 센다 (`null_items`). 그 목록으로 합계·평균·개수·순위·대표 고르기를 하는 코드는 계산한 값을 `null`(모름)로 두고, 쪽 넘김·`--limit` 자리를 세는 코드는 `len(목록)` 에 뺀 수를 더하며, 둘 다 `null_items_note` 로 `[제외]` 안내를 붙인다. 안 보면 적은 합계가 완전한 값처럼 나가거나 다음 쪽에서 같은 항목을 다시 받는다. 확인: 목록 길이를 쓰는 `len(`·`sum(`·`enumerate(`·`[0]`·`== 1`·빈 쪽 판정마다 빈 항목 하나를 섞은 응답을 넣어 본다. 목록을 그대로 보여 주기만 하면 보지 않아도 되고, 자리별 안내가 없어도 `emit` 의 공통 안내(`null_items_total_note`)가 뺀 수를 알리니 자리별 안내를 요구하지 않는다.
    예: `providers/dabang/service/neighborhood.py` `_type_counts` (유형 목록에서 빈 항목을 뺀 합계는 모름이다, 2026-11-21).
    파서가 HTML·스토어에서 목록을 직접 만들어 모델에 넘기면, 파서가 null 원소를 미리 버려 모델이 세지 못한다 (null 도 넘겨 `null_items` 로 세게 한다).
    같은 함수 안에서 다른 이유(연월 없음·평균 없음)로 뺀 항목도 빈 항목과 같은 모름이다. 예: `providers/daangn/api/parser.py`
    `parse_map_reviews_html` (null 단지를 버려 상한 20곳 판정이 19곳으로 빗나갔다), `providers/daangn/service/real_price.py`
    `get_price_trend` (연월 없는 점은 빼기만 하고 총 거래 수·변화율을 확정값으로 냈다, 2026-11-22).
    언제: 응답 모델의 객체 목록 칸(`list[Model]`)을 읽는 `+` 줄에 `len(`·`sum(`·`enumerate(`·`[0]`·`== 1` 이 든 diff, 쪽 넘김 루프,
    목록을 만드는 파서의 `if edge`·`if node` 거르기, 같은 루프에서 `continue` 로 항목을 빼는 다른 갈래.
21. **쪽 넘김 중간 실패를 같게 다루는가.** 2쪽 이후를 받지 못한 갈래가 요청 예외와 응답 형식 오류(목록 칸 null)를 같게 다루는가. 예외만 받은 쪽까지 내고 목록 null 은 에러로 올리면 앞 쪽 결과를 버리고, 문서가 약속한 "받은 데까지 `[실패]`" 와 어긋난다. 확인: 쪽 반복에서 `first`(1쪽)가 있을 때 응답 목록이 None 인 갈래를 따라간다.
    예: `providers/zigbang/service/local/ranking.py` `_collect_pages` (2026-11-22).
    언제: 쪽을 차례로 받으며 중간 실패를 `[실패]` 로 넘기는 diff.
22. **서버가 정렬해 준 목록을 걸러 쓸 때 '더 있음'.** 서버가 거르는 값으로 정렬해 주는 목록(후기 수 내림차순 등)에서 그 값이 있는
    것만 남기면, 받은 수가 상한에 닿았어도 꼬리가 걸러지는 값이면 걸러 남을 것이 더 없다. 받은 수(`len(page)`)만으로 "더 있을 수
    있다" 고 하지 않고 목록 꼬리의 값까지 본다. 확인: 상한 판정 줄이 거르기 전 목록의 개수만 보는지, 서버 정렬 키가 거르는 값과 같은지 본다.
    예: `providers/daangn/service/review.py` 동 후기 페이지 단지 500곳 (강서구 화곡동: 후기 있는 단지 298곳뿐인데 "더 있을 수 있다", 2026-11-20).
    언제: 서버 목록을 값으로 걸러 낸 뒤 상한·`[일부]` 를 정하는 diff.
23. **실패를 여럿 모으는 반복에서 첫 실패만 기억.** 반복 안에서 예외를 잡아 모을 때 첫 예외만 남기면, 뒤에 온 요청 제한을 보고도
    멈추지 않고 안내 이유도 첫 실패의 것이 된다. 멈춤(요청 제한이면 남은 요청을 보내지 않음)은 실패마다 정하고, 안내는 무엇으로
    정하는지 적는다. 확인: 실패 순서를 바꿔(5xx 다음 요청 제한) 넣어 남은 요청이 나가는지 본다.
    예: `providers/dabang/service/listing.py` `attach_details` (매물 6건 모두 상세를 불렀다, 2026-11-20).
    언제: 반복 안에서 예외를 잡아 건너뛰거나 모으는 `+` 줄.
24. **상태 파일에서 읽은 큰 정수.** 상태 파일(`<state_dir>` 아래 JSON)에서 읽은 정수를 실수와 빼거나 `float()`·`isfinite` 에
    넘기면, 약 1.8×10³⁰⁸ 이상인 정수에서 OverflowError 가 나 그 소스의 모든 명령이 `INTERNAL_ERROR` 다. 한 번 비교에만 쓰면 빼지
    않고 비교로 쓰고(비교는 크기와 상관없이 터지지 않는다), 뒤에서 실수로 바꿔 쓰면 읽는 자리에서 버린다. 같은 종류 값을 읽는
    다른 상태 파일도 함께 본다. 확인: 그 칸에 `1` 뒤에 0 을 400개 붙인 정수를 넣고 명령을 불러 본다.
    예: `core/ratelimit.py` `_is_time`, `core/browser.py` `usable_cookies` (`opened_at`, 요청 제한 쪽만 고치고 빠졌다, 2026-11-23).
    언제: 상태 파일을 읽는 코드나 거기서 읽은 시각·수를 계산하는 `+` 줄.
25. **브라우저 이동 실패가 숨긴 상태 코드.** 첫 화면 문서의 4xx·5xx 판정을 `page.goto` 가 돌려준 응답에만 기대지 않는가. Chromium 은
    본문 없는 4xx·5xx 문서에서 goto 를 `net::ERR_HTTP_RESPONSE_CODE_FAILURE` 로 실패시켜 응답을 돌려주지 않는다. 그 갈래에서 판정만 맞추고
    정리를 빠뜨리기도 쉽다: `_close` 는 컨텍스트가 있을 때만 쿠키 정리(`finish`)를 하고, `discard_saved` 는 첫 화면 시각(`opened_at`)이
    0 이면 옛 쿠키 파일을 지우지 않는다. 확인: 가짜 첫 화면이 `Content-Length: 0` 으로 403·429·503 을 주게 하고 에러 종류·쿨다운·옛 쿠키
    파일이 본문 있는 경우와 같은지 본다 (`scripts/ci/browser_check.py` 7번). 예: `core/browser.py:1694` `_launch` 의 except 갈래 (그때 연결
    오류로 보고 첫 화면을 세 번 다시 연 뒤 `NETWORK_ERROR` 로 냈고 쿨다운·차단 판정이 빠졌다, 2026-11-24).
    언제: 첫 화면 문서 상태로 판정하는 코드나 `goto`·`_entry_error`·`_launch` 의 예외 처리를 바꾼 diff.

## `contract` 출력 계약

1. **안내를 따르면 되는가 (모든 모드에서).** `--limit` 이 이미 최대값인데 늘리라고 하지 않는가. 좁히라고 권하는 것('지역'·
   '반경'·평형)이 그 명령·검색 방식에 실제로 있는가. 한 명령의 여러 모드(`--complex`·`--redevelopment` 등)가 같은 hint 표를
   쓰면, 그 hint 가 권하는 옵션을 모든 모드가 받는가. 조건과 상관없이 섞이는 묶음(직방 상가의 공실 줄)이 `total` 에 들면 그 조건은 좁혀도 그 줄이 줄지 않으니 권하지 않는다. 확인: `more_hint`·`pagination_notes`·`UsageHints` 의 값을 그 모드의 옵션
   검사와 대조한다. 예: `core/listing.py:531`, `cli/naver.py:1239` (단지 모드에 받지 않는 `--radius` 를 권함, 2026-11-16), `providers/zigbang/service/store.py` `STORE_VACANT_NARROW` (공실 묶음이 있는데 업종을 좁히라고 권함, 2026-11-21).
   언제: `more_hint`·`pagination_notes`·`UsageHints`·`hint=` 를 바꾸거나, 한 명령에 모드·옵션을 더한 diff, 조건과 상관없는 묶음을 `total` 에 넣은 diff, `core/`·`cli/` 공용 모듈이 모든 명령에 붙이는 hint(`core/ratelimit.py` `RateLimitedError` 의 budget hint 가 `--limit`·`--radius` 가 없는 명령에도 그 옵션을 권했다, 2026-11-23 core 리뷰).
2. **예시 이름과 권하는 명령.** hint 의 예시·명령을 그대로 넣으면 그 명령이 받는가 (동을 받지 않는 명령에 동 이름, 여전히 모호한
   예시, 필수 옵션을 빼라는 안내). 확인: 예시를 그 명령의 인자 검사·resolver 에 넣어 따라간다.
   예: `providers/daangn/service/region.py:473`, `providers/daangn/service/commute.py:268`, `providers/zigbang/service/region.py:174`
   (같은 이름 구 '중구' 에 '구 이름을 붙이라' 고 했고, 좌표를 받지 않는 `search complexes` 에 `--lat/--lng` 를 권했다. 후보 하나로
   가려지는 예시만 들게 했다, 2026-11-16).
   언제: hint·notes·에러 message 에 `jibsa ` 명령이나 예시 이름이 든 `+` 줄, 여러 명령이 함께 쓰는 hint 를 새 명령이 부르게 한 diff, 기본 hint 가 `--lat/--lng` 를 권하는 `RegionNotFoundError` 를 좌표 옵션이 없는 명령이 hint 를 넘기지 않고 던지게 한 diff (`providers/zigbang/service/region.py` `resolve_station`, 2026-11-21).
3. **notes 태그.** 더 있음 `[일부]`, 뺀 것 `[제외]`, 찾은 범위가 다름 `[범위]`, 덤 조회 실패 `[실패]` 가 맞게 붙었는가 (맨
   문자열은 `[참고]` 로 나간다, [docs/common.md](../common.md)). 같은 뜻의 짝 안내(같은 명령의 다른 갈래, 다른 명령의 같은 상황)는
   같은 태그인가. 예: `providers/daangn/service/commute.py:260`, 당근 `popular-listings` 의 구 기준 안내(`[범위]`)와 세종의 같은 뜻 안내(`[참고]`),
   `good-neighborhoods` 의 '추천 동네를 주지 않았습니다'(`[참고]`)와 통근의 '역 매물 목록을 주지 않았습니다'(`[실패]`) (2026-11-20), 실거래·시세 그래프·학교 배정 단지의 같은 안내(`[참고]`)와 통근의 `[실패]` (2026-11-20 두 번째 사례).
   언제: `notes` 에 문자열을 더하는 `+` 줄. 짝 안내는 같은 문구의 앞부분이나 '주지 않았습니다'·'기준입니다' 로 grep 해 찾는다.
4. **한 결과 안 안내끼리.** "전부입니다" 와 `[일부]`, 같은 안내 여러 번, '곳'·'건' 섞임이 함께 나오지 않는가. 같은 목록을 안내마다 다른 이름으로 부르지도 않는가 (학교의 순서 안내는 '배정단지', `[일부]` 안내는 '주변 단지'). 확인: 여러 갈래가
   함께 참이 되는 입력을 찾는다. 예: `providers/zigbang/service/common/apt.py` `apt_pagination_notes`.
   언제: 한 결과에 안내를 붙이는 갈래가 둘 이상인 함수를 바꾼 diff, 같은 목록을 가리키는 안내 문구(순서 안내·`[일부]` 안내)를 따로 쓰거나 고친 diff (`providers/zigbang/service/complex/search.py` `SCOPE_NAME_BY_PLACE_TYPE`, 2026-11-21).
5. **에러 code·hint 가 원인과 맞는가.** 첫 화면 5xx 를 "스펙 변경" 으로, 형식 오류 400 을 "없는 ID" 로, 정상 0건을 에러로 알리지
   않는가. 감시·에이전트가 hint 문구가 아니라 `code`·`blocked` 같은 필드로 가르는가. 예: `cli/output.py:402`·`core/browser.py:1237`.
   언제: 에러 클래스·`code`·hint 를 고르는 갈래나 `raise ...Error(` 를 더하거나 바꾼 diff.
6. **사용법 오류 안내가 그 명령 기준인가.** 다른 명령의 hint 를 물려받아 원래 없던 옵션을 "없앴습니다" 라고 하지 않는가.
   한 값 옵션을 반복하면 마지막 값만 남는 것은 공통 층(`cli/app.py` 의 `repeated_option`)이 요청 전에 막고, 붙여 쓴 짧은 옵션
   (`-t아파트 -t오피스텔`, `--type 아파트 -t오피스텔`)도 같은 옵션으로 세므로 옵션마다 막지 않는다. 새 옵션이 한 값만 뜻이 있으면
   `list[str]` 이 아니라 `str` 로 선언해 공통 층에 맡기고, 반복을 받는 옵션만 `multiple`·`list[str]` 로 선언했는지 본다 (2026-11-20).
   공통 층이 못 막는 것은 둘이라 그 명령이 막아야 한다: 쉼표로 여럿 준 값(`--trade 전세,월세`)과, 값 하나만 뜻이 있는데
   목록(`list[str]`)으로 받는 옵션을 되풀이한 것(`-t 원룸 -t 투룸`)이다 (`check_choice`·`split_csv`, `cli/daangn.py` 의
   `popular_listings_command` 의 `-t`). 예: `cli/daangn.py:380`.
   언제: 옵션 검사·사용법 오류(`BadParameter`·`check_choice`·`UsageHints`)를 바꾼 diff, 옵션을 더하거나 `multiple`·`list` 로 선언을 바꾼 diff.
7. **help·Field description·`docs/<source>.md` 가 동작과 같은가.** 기본값·거르기를 바꾼 diff 면 셋을 함께 grep 한다. 동작 문장은
   명령 입구(CLI 옵션 검사)부터 따라가 확인한다. 서비스 함수만 보면 CLI 가 그 앞에서 막는 조합까지 된다고 적게 된다 (당근 `search complexes --trade`
   도움말이 보증금·월세 조건만 있어도 매매를 보낸다고 적었는데 CLI 는 그 조합을 `INVALID_ARGUMENT` 로 막았다, 2026-11-20).
   예: `cli/daangn.py:253`, `docs/llm.md` 의 네이버 경계 검색 줄 (`search listings`·`complexes`·`redevelopment` 를 묶어
   `has_more`·`next` 로 나눠 본다고 적었는데 그 키는 `search listings` 에만 있었다, 2026-11-18).
   언제: 기본값·거르기·옵션·출력 필드를 바꾼 diff (help·`Field(description=`·`docs/<source>.md` 중 일부만 바뀌었으면 특히),
   여러 명령을 한 문장에 묶어 설명한 diff.
8. **가격·값을 읽는 데 필요한 새 필드는 `--fields` 로 골라도 나오나.** 빠지면 다른 필드를 잘못 읽게 되는 필드(가격이 분양가인지,
   묶음 최저가인지)는 `cli/output.py` 의 `ALWAYS_FIELD_GROUPS` 에 넣는다. 확인: `--fields id,price_manwon` 으로 불러 그 필드가
   남는지 본다. 예: `cli/output.py:68` (`listing_kind` 가 빠져 분양가를 호가로 읽었다, 2026-11-17).
   언제: 묶음·매물 목록에 가격 해석을 바꾸는 필드를 더하는 diff.
9. **코드를 말로 바꾸는 표에서 모르는 코드.** `.get(코드)` 로 모르는 코드를 `None` 으로 버리면 '서버가 주지 않음(null)' 으로
   읽힌다. 다른 표처럼 `.get(코드, 코드)` 로 원본을 남기거나, 버린다면 설명에 적었는가. 확인: 새 이름표 dict 를 쓰는 `.get(`
   의 두 번째 인자와 Field 설명의 null 뜻을 대 본다. 예: `providers/zigbang/service/common/apt.py` `apt_listing_kind` (2026-11-17).
   언제: 서버 코드 → 한국어 이름표 dict 를 새로 두거나 값을 더하는 diff.
10. **같은 매물을 내는 목록·상세가 해당 없음과 모름을 같게 내는가.** 상세에서 키를 빼는(해당 없음) 필드를 목록 모델도 같은 표로
    빼는지, 목록이 `null` 로 내지 않는지 본다. 확인: 같은 매물 하나를 목록과 상세로 불러 같은 필드가 키 없음·`null` 로 갈리는지 비교한다.
    예: `providers/naver/service/common.py:340` (`NaverListing.not_applicable_fields`, 토지 목록에 방 수·층이 `null` 로 나갔다, 2026-11-17).
    언제: 상세 모델의 해당 없음 규칙(`not_applicable_fields`·유형별 표)을 더하거나 고친 diff, 같은 매물을 내는 목록 모델이 따로 있는 소스.
11. **문서에 적은 값의 뜻을 응답 키·번들 상수로.** 문서·Field description 이 적은 값의 뜻(빈 목록이 무엇을 뜻하는지, 날짜가
   어느 날짜인지)이 그 필드를 채우는 응답 키와 번들 상수(코드 표)의 모든 값과 맞는가. 확인: 필드를 채우는 줄의 응답 키를 보고,
   jibsa 표에 없는 코드까지 번들 상수에서 grep 한다. 예: `providers/naver/service/common.py` `verification_badges` (`[]` 에
   무검증 `NONE` 도 드는데 '확인하지 않은 매물이 아니다' 라고 적었다), 네이버 `registered_at` (노출 시작일인데 '확인 날짜' 라고
   적었다, 2026-11-17), 같은 `badges` 에 HUG 배지를 더한 뒤에도 "방식 배지가 없으면 `[]`" 가 남아 HUG 만 있는 매물과
   어긋났다 (2026-11-18).
   언제: 새 출력 필드의 뜻이나 빈 값의 뜻을 문서·Field description 에 적은 diff, 기존 필드에 값이 나오는 곳(갈래·출처)을 더한
   diff (전에 맞던 "비면 …" 문장이 새 조합에서 틀린다).
12. **번들 한 시점으로 웹 동작을 단정하지 않는가.** 문서·안내가 "네이버 화면도 그리지 않는다" 처럼 웹 동작을 근거로 에이전트
   행동(화면에서 확인하라고 권하지 말라 등)을 정할 때, 그 말이 jibsa 표를 베낀 그날 번들에서만 맞지 않는가 (사이트가 코드를
   더하면 웹 표도 함께 바뀌어 jibsa 표만 낡는다). 확인: 단정이 기대는 번들 상수가 jibsa 표의 사본인지, 소스 가이드가 "확인하지
   못했다" 고 적은 항목까지 한데 묶었는지 본다. 예: `docs/llm.md` 네이버 `알 수 없는 값` 줄 (화면에서 확인하라고 권하지 않는다고
   적었다, 2026-11-17).
   언제: `docs/llm.md`·`docs/<source>.md` 에 웹 화면 동작을 근거로 쓰는 쪽의 행동을 정한 문장.
13. **지역 이름 검사를 그 이름을 받는 모든 명령에 넣었는가.** 같은 지역 해석(`_resolve_location`)을 부르는 다른 명령에도 같은
    입력이 들어온다. 확인: 그 해석을 부르는 다른 명령에 그 입력을 넣어 본다. 예: `cli/naver.py` `_trend_district` (구 있는 시
    검사를 `search` 에만 넣어 `trend 성남시` 가 오류 없이 모두 0 을 냈다, 2026-11-18).
    언제: 지역 해석 뒤에 검사·갈래를 한 명령에 더한 diff.
14. **출력 날짜를 읽지 못하면 원래 글자를 돌려주는 함수로 만들지 않는가.** `normalize_date` 는 못 읽으면 원래 글자를 돌려줘 (소스가 값 없음으로 주는 `-` 만 `null`)
    설명이 'YYYY-MM-DD 아니면 `null`' 인 필드에는 `iso_date` 를 쓴다. 확인: 날짜 필드를 채우는 줄이 어느 함수를 부르는지와
    Field 설명을 대 본다. 예: `providers/naver/service/common.py` `confirmed_at` (2026-11-18).
    언제: 날짜 필드를 더한 diff.
15. **유형을 모르면 줄을 통째로 버리는 변환.** `… | None` 을 돌려주는 변환 함수가 모르는 유형에 `None` 을 주고 호출부가 그 줄을 빼면, 버린 수를 세어 `[제외]` 로 알리는가 (다방 `_unknown_trade_note`). 알리지 않으면 거래가 말없이 사라진다. 확인: 변환 결과가 `None` 일 때 건너뛰기로 끝나는 자리마다 센 수가 notes 에 가는지 본다 (`--limit` 으로 어차피 잘릴 자리는 세지 않아도 된다).
    예: `providers/zigbang/service/real_price.py:374` 의 `unknown` 을 세는 줄 (`--trade 전체`, 2026-11-17).
    언제: 변환 함수가 `None` 을 돌려주는 갈래를 더하거나 그 결과로 줄을 빼는 diff.
16. **다른 명령을 권하는 안내가 사용자가 붙인 앞 낱말을 버리지 않는가.** 같은 이름을 가리려고 사용자가 앞에 붙인 구·동 낱말(`영등포구 양평역`)을 빼고 찾은 이름(`양평역`)만 권하면, 권한 명령을 그대로 불렀을 때 `REGION_AMBIGUOUS` 가 난다. 확인: 안내에 든 명령을 그대로 불러 같은 곳을 찾는지 본다.
    예: `cli/zigbang.py` `search listings apt` 의 '역 주변 단지는 jibsa zigbang search complexes 양평역' (2026-11-20).
    언제: 안내·`hint` 가 다른 명령과 그 검색어를 글로 알리는 `+` 줄 (그 명령이 같은 이름 가림을 하는 경우).
17. **에러 `details` 의 None 을 빼지 않는가.** `details` 의 None 은 모름이라 출력에 `null` 로 남아야 한다 ([에러](output-contract.md#에러)). 확인: None 이 들어갈 수 있는 details 를 던지는 에러를 `handle_errors` 안에서 던져 stderr JSON 에 그 키가 `null` 로 있는지 본다.
    예: `cli/output.py` `emit_error` (2026-11-23 core 리뷰: `emit_error` 가 키워드 값의 None 을 빼 `RegionAmbiguousError(total=None)` 의 `candidate_count` 가 키째 빠졌다. 지금은 `details=` 로 따로 받아 None 을 싣는다).
    언제: 에러 details 에 None 일 수 있는 값을 넣거나 `emit_error`·`handle_errors` 를 고칠 때.

## `web` 웹 대응

1. **웹 식을 옮길 때 JS 의미까지.** `??` 와 `||`(0·빈 글자), `Math.round` 와 Python `round`(은행가 반올림), `toFixed` 와 Python
   `round`·`f'{x:.nf}'`(정확히 반인 값을 짝수로)·`Decimal(str(x))`(이진 값이 반보다 작은 소수를 올림), 정수 버림, 안정 정렬,
   "첫 항목 기준" 같은 기준점. `Math.round` 는 공용 `js_round`, `toFixed` 는 공용 `js_to_fixed` 로 옮기고 곳마다 따로 흉내 내지
   않는다. 확인: 주석의 번들 식과 한 줄씩 대조하고 0·x.5·동점·첫 항목 없음과 반올림이면 0.15·0.25·x.125·1.005·2.675 를 넣어 본다.
   예: `providers/daangn/service/real_price.py:1355` 의 `previous_high_change_percent`(Python `round` 로 0.25% 가 웹 0.3 과
   달랐다), `providers/daangn/service/complex.py:385` 의 `_web_school_card`(`??` 를 `or` 로 옮겨 0 이 모름이 됐다),
   `core/listing.py:161` 의 `js_to_fixed`
   (다방 거리·당근 면적이 따로 흉내 내다 어긋났다, 2026-11-20).
   그 식이 **그 칸을 그리는 화면**의 식인가. 같은 값도 화면마다 다르게 그린다. 다른 화면 식을 함수로 가져다 쓰면 근거 주석의 청크·함수가
   이 화면 것인지 본다. 예: `providers/daangn/service/compare.py` `_subways` (단지 화면 `Math.max(1, Math.round)` 를 썼는데 비교 화면은
   값 그대로라 '0' 이 1분이 됐다, 2026-11-22).
   언제: 주석에 번들 식(JS)이 붙은 계산, 또는 `round(`·`//`·`sorted(`·`max(`·`min(` 이 든 `+` 줄, 웹 식을 옮긴 공용 함수
   (`web_minutes` 등)를 새 화면에서 부르는 `+` 줄.
2. **웹이 보내는 변수 모양 그대로인가.** 조건이 없으면 웹처럼 null 을 보내는가(빈 객체·빈 목록이 아니라), 웹 화면이 받는 단위를
   넘는 조합을 만들지 않는가. 예: `providers/daangn/api/request/common.py:211` (`{salesTypes: []}`).
   언제: `api/request/` 의 변수·쿼리 모양이나 그 기본값을 바꾼 diff.
3. **사이트에 없는 결과.** 받은 결과를 같은 조건으로 다시 거르거나 다른 소스로 대신 찾지 않는가, 후보 중 하나를 임의로 고르지
   않는가 (위 `correctness` 4), `[제외]` 문구가 실제로 없는 사유("조건 불일치")를 말하지 않는가.
   예: `providers/daangn/service/common.py:924`.
   언제: 받은 목록을 거르기·합치기·다시 정렬하기·고르기 하는 `+` 줄, `[제외]` 문구.
4. **웹과 다른 개선을 적었는가.** 웹에 없는 동작이 그 소스 가이드 "웹과 다른 점" 에 있는가. 예: `providers/daangn/service/school.py:177`.
   언제: 웹에 없는 옵션·기본값·묶어 받기를 더한 diff.
5. **값을 바꿔 그리게 하는 옆 칸.** 응답에 웹이 값 대신 다른 글자를 그리게 하는 칸(`is…` 플래그 등)이 함께 오는데 jibsa 가
   값만 그대로 내지 않는가. 확인: 출력에 새로 내는 응답 필드의 응답 모델에서 옆 칸을 보고, 번들에서 그 칸 이름을 grep 한다.
   예: `providers/naver/service/listing.py` `_agent_fee` (`isIndividualCheckRequired` 면 웹은 '개별확인', 2026-11-17).
   언제: 응답 필드를 출력에 새로 내거나 내는 범위(거래 유형·매물 유형)를 넓힌 diff.
6. **칸을 붙이는 조건.** 웹이 그 칸(컴포넌트)을 붙이는 조건(매물 유형 목록, `!isDirectTrade` 같은 플래그)을 확인했는가. 조건
   밖의 매물에 값이나 `null` 을 내지 않고 키를 지우는가 (칸이 없으면 해당 없음). 확인: 번들에서 그 칸을 그리는 컴포넌트를 찾고,
   부모가 그것을 붙이는 조건식과 유형별 칸 목록 함수를 본다. 예: `providers/naver/service/common.py:282`
   `NOT_APPLICABLE_FIELDS_BY_TYPE` (토지에 방 수·난방을 `null` 로 냈다), `is_direct_trade` (직거래에 중개보수를 냈다, 2026-11-17).
   칸이 없는 매물이어도 웹이 받는 같은 상세 응답의 값을 같은 이름표로 옮기는 것은 키를 지우지 않아도 되지만, 그때는 그 소스 가이드 '웹과 다른 점' 에 적는다 (네이버 단지형 빌라·단지 번호가 없는 단지 유형의 현관 구조·주차, 2026-11-18). 방 수처럼 개념상 해당하지 않는 필드는 지금대로 키를 지운다.
   언제: 상세 출력 필드를 새로 내거나, 여러 매물 유형·거래 유형에 같은 필드를 내는 diff.
7. **칸이 거래·매물 유형마다 다르거나 단지 값으로 채우는가.** 웹이 거래 유형마다 칸을 다르게 그리는지(`getPriceLabel` 은 전세면 보증금만),
   매물 값이 비면 단지 값으로 채우는지(`매물 || 단지`)를 확인했는가. 값을 한 곳에서만 가져오거나 모든 유형에 같은 칸을 내지 않는다.
   확인: 번들에서 그 필드를 그리는 식을 찾아 `||`·삼항·유형 분기를 본다. 예: `providers/naver/service/real_price.py:159`
   (전세 갱신의 종전 월세), `providers/naver/service/listing.py:1247` (난방은 매물 값 `||` 단지 값, 2026-11-17).
   언제: 출력 필드의 출처를 바꾸거나 새 엔드포인트로 값을 채우는 diff, 거래 유형별로 키를 빼거나 내는 `+` 줄.
8. **웹 번들을 견주는 감시가 번들 모양에 기대거나 일부만 견주는가.** 매니페스트·조각 배열의 첫 항목처럼 순서에 기대지 않고
   이름으로 고르는가, jibsa 가 웹에서 옮긴 값(코드·행뿐 아니라 이름표처럼 출력에 나가는 글자)을 모두 견주는가. 웹이 다시
   배포해 순서만 바뀌면 고장으로 잘못 알리고, 견주지 않은 값이 바뀌면 정상으로 남는다. 확인: 정규식의 비포획 그룹과 `[0]` 을
   보고, 공유 조각이 앞에 오는 배열과 값 하나를 바꾼 번들 글자를 넣어 본다. 예: `scripts/monitor/api_check.py` 의
   `check_zigbang_stay_refund_rules` (`pages[0]`, 정책 이름표 `유연` 을 견주지 않음, 2026-11-17).
   언제: `scripts/monitor/` 에 웹 번들·매니페스트를 읽는 검사를 더하거나 바꾼 diff.
9. **웹 지도 크기로 잡는 범위를 한 곳에서 잰 도(°)로 고정하지 않았나.** 웹이 지도(픽셀 크기·줌)의 범위를 보내면 경도 폭은
   위도와 상관없이 같지만 위도 폭은 메르카토르라 위도마다 다르다 (같은 388×200px 지도의 위도 폭이 서울 37.47° 에서 0.001703°,
   제주 33.5° 에서 0.0017893°). 한 단지에서 잰 도 값을 상수로 두면 다른 위도에서 웹과 범위가 어긋난다. 확인: 상수가 실측한
   도 값인지, 픽셀·축척으로 단지 위도에서 계산하는지 보고, 위도가 다른 두 곳을 넣어 위도 폭을 견준다. 예:
   `providers/naver/service/real_price.py` 의 `get_real_prices` 안 웹 지도 범위 계산 (빌라 주변 실거래 기본 범위가 572549 에서 잰 도 상수였다, 2026-11-19).
   언제: 웹 지도 범위(`top`·`bottom`·`left`·`right`, bounds)를 흉내 내는 기본값을 더하거나 바꾼 diff.
10. **웹이 어떤 조건에서 칸을 숨기면 같은 응답의 다른 칸에도 그 조건을 똑같이 적용했는가.** 관리비 없음이면 웹은 '관리비 없음' 만 그리고
   미포함 항목 줄을 그리지 않는데, 포함 항목만 그 조건을 따르고 미포함 항목은 응답 그대로 내면 같은 매물에서 두 칸이 어긋난다.
   확인: 웹 렌더 함수가 그 조건에서 돌려주는 값에 그 칸이 있는지 번들로 본다.
   예: `providers/zigbang/service/room/detail.py:225` `manage_cost_excludes` (포함 항목만 관리비 없음을 `[]` 로 보고 미포함은 응답 그대로 냈다, 2026-11-20 직방 리뷰).
   언제: 웹이 값을 숨기거나 바꿔 그리는 조건(관리비 없음·확인 불가·유형 분기)을 옮긴 `+` 줄, 같은 응답의 칸 여럿 중 일부에만 그 조건을 건 diff.

## `requests` 요청 수·차단 위험

1. **이미 아는 것을 다시 묻지 않는가.** 앞 결과·캐시·방금 받은 응답으로 아는 값을 다시 묻거나, 답이 같을 두 번째 요청을 보내지
   않는가. 확인: 루프·후속 검사 안의 resolve·search 호출이 결과를 바꿀 입력이 실제로 있는지 따진다.
   예: `providers/daangn/service/region.py:640`, `providers/naver/service/region.py:291` (같은 자동완성 재호출, 2026-11-16).
   언제: 루프·후속 검사 안에 resolve·search·client 호출이 든 `+` 줄.
2. **결과가 정해진 뒤의 요청.** 더 없음을 알면서 빈 쪽을 한 번 더 받거나, 빈 쪽의 hasMore 를 믿고 쪽 상한까지 묻지 않는가.
   예: `providers/daangn/service/common.py:845`.
   언제: 쪽 넘기기 루프의 멈춤 조건을 바꾼 diff (`correctness-1` 과 같은 자리).
3. **덤 조회의 순서와 실패.** 수 세기·동 이름 같은 덤 조회를 본 조회 뒤에 하는가 (덤이 첫 요청이면 첫 화면 실패를 삼킨다), 덤이
   실패(요청 제한 포함)해도 받은 결과를 버리지 않는가. 예: `providers/daangn/service/search.py:113`.
   언제: 수 세기·이름 찾기 같은 덤 조회를 더하거나 순서를 바꾼 diff.
4. **요청 전에 막을 수 있는 입력.** 결과와 상관없이 막힐 입력을 요청 뒤에 막지 않는가 (이름 모양으로 짐작해야만 막을 수 있으면
   아래 "지적하지 말 것"). 예: `providers/dabang/service/ranking.py:763`.
   언제: 입력 검사·에러를 요청 뒤에 두는 `+` 줄.
5. **transport 밖 요청과 서버 신호 (`core/`).** CORS 사전 요청·redirect·첫 화면도 세는가, `Retry-After` 보다 짧게 쉬지 않는가,
   429 에 쿠키를 버려 첫 화면 요청을 다시 쏟지 않는가. 예: `core/browser.py:1227`·`:1189`.
   언제: `core/browser.py`·`core/http.py`·`core/ratelimit.py` 를 바꾼 diff.

## `design` 구조·중복·단순화

1. **같은 규칙 두 벌.** 같은 판정식·문구·흐름·필터가 다른 함수·파일에 또 있는가, 이미 있는 helper 를 다시 만들었는가.
   확인: 새 함수·식·문구의 핵심 낱말로 grep 한다. 예: `core/listing.py:531`, `providers/daangn/service/common.py:834`,
   `providers/naver/service/common.py:1203` (동 경계/반경 갈래가 세 함수에 따로 있었다, 2026-11-16). 공통 함수가 생긴 뒤에도 한 소스가 손으로
   쓴 문장을 남기면 그 소스만 갈래(요청 제한의 대기 시간 등)가 빠진다. 예: 직방 덤 조회 `[실패]` 14곳이 `core/listing.py` `lookup_failure_note`
   대신 `({type(exc).__name__})` 문장이라 요청 제한에 대기 시간이 없었다 (2026-11-22). `core/korean.py` `is_province_code` 를 더하며
   직방 `providers/zigbang/service/region.py` 의 `endswith('00000000')` 두 곳을 놓쳤고, `AGENTS.md` 구조 표의 `core/korean.py` 칸에도
   이름을 넣지 않았다 (2026-11-23 리뷰).
   언제: 새 함수·상수·문구·필터·갈래를 더한 diff, `core/` 에 여러 소스용 함수를 더하거나 바꾼 diff (그 일을 하는 소스별 문장을 grep 한다).
2. **호출부마다 달라야 할 인자에 기본값.** `narrow`·`max_limit` 처럼 호출부마다 값이 달라야 맞는 인자에 기본값을 두면 빠뜨려도
   조용히 틀린다. 설정을 dict 로 `**` 풀어 넘기지 않는다. 예: `providers/naver/service/common.py` `pagination_notes` 의 `narrow`.
   언제: 기본값이 있는 인자를 더하거나, 설정 dict 를 `**` 로 넘기는 `+` 줄.
3. **닿지 않는 갈래·쓰지 않는 인자.** 부르는 곳이 사라진 갈래·예외 클래스, 받기만 하고 쓰지 않는 인자, 늘 같은 값(`[]`·`None`)만
   돌려주게 된 반환값과 그 값을 받아 잇는 호출부가 남지 않았는가. 확인: 갈래를 지운 함수의 `return` 을 모두 보고 호출부를 grep 한다.
   예: `core/browser.py:448`, `providers/zigbang/service/region.py` `region_notes` (안내 갈래를 지운 뒤 늘 `[]` 였고 호출부 여섯 곳이
   이었다. 검사 함수 `settled_item` 으로 바꿨다, 2026-11-16), `providers/naver/service/real_price.py` `drop_not_applicable`
   (빌라도 종전 금액을 늘 넘기게 바꾼 뒤 '넘기지 않은 행' 갈래와 주석이 남았다, 2026-11-18). 공통 층을 새로 만들면 그것이 대신하는
   옛 개별 처리가 남지 않았는가도 같다 (당근 `--deal`·`--approval`·`--lifestyle` 을 `list[str]` 로 받아 옵션마다 막은 처리가 공통
   `repeated_option` 뒤에도 남아 두 번 막았다, 2026-11-20).
   언제: 코드를 지우거나, 부르는 곳을 옮기거나, 인자를 더한 diff, 함수의 갈래를 지워 돌려주는 값이 줄어든 diff, 선택이던 인자를
   모든 호출부에서 늘 넘기게 바꾼 diff, 여러 곳의 처리를 대신하는 공통 함수·층을 새로 둔 diff.
4. **따로 도는 CI 단계의 짝.** `.claude/` 처럼 문서로 분류돼 pytest 를 건너뛰는 파일을 지키는 테스트는 CI lint 단계에서 이름으로
   따로 돈다. 같은 종류의 테스트를 더했으면 그 단계 명령과 `workflow.md` 설명에도 더했는가. 확인: 새 테스트가 지키는 파일이
   `ci.yml` 의 `DOC_PATTERN` 에 드는지 보고 lint 단계의 `pytest` 명령과 대조한다.
   예: `.github/workflows/ci.yml:102` (`test_workflow_args_parsing_blocks_match` 가 빠져 있었다, 2026-11-16).
   언제: `.claude/`·`docs/` 를 읽는 테스트를 `tests/` 에 더한 diff.
5. **이유 없이 뺀 함수·구현이 하나뿐인 추상화.** 새 함수(비공개 포함)가 한 곳에서만 불리는데 함수로 둘 이유(두 곳 이상에서
   씀, 다른 파일이 부름, 함수를 넘기는 자리, 테스트가 바꿔 끼우는 자리, 부르는 함수가 다른 일도 하는데 `if`·`for`·`while`·`try`
   문이나 요청을 가진 자기 흐름인 덩어리)가 없지 않은가, 새 기반 클래스·Protocol·설정 dict 에 실제 갈래가 둘 이상인가, 일어날 수
   없는 경우를 처리하는 갈래가 없는가. 기준은 [함수와 추상화](code-style.md#9-함수와-추상화)에 있고 줄 수로 재지 않는다.
   확인: 새 `def` 이름으로 grep 해 부르는 곳을 세고(docstring·주석에 이름만 적힌 곳은 세지 않는다), 한 곳이면 위 이유 중 어디에
   드는지 본다. `if`·`for` 문 없이 결과 하나를 만들어 돌려주는 함수는 길이와 상관없이 합치라고 지적한다. 같은 자리의 나란한
   갈래 중 한쪽만 합쳤으면 그것도 지적한다 (예: 2026-11-23 리뷰에서 직방 `get_stay_listing` 의 후기와 임대인의 다른 방, 네이버
   `get_real_prices` 의 평당 실거래가와 주변 실거래, 직방 `get_complex` 의 순위와 관련 단지가 한쪽만 합쳐져 있었다). 합쳐서 부르는
   함수가 길어졌다는 것만으로는 지적하지 않는다. `if`·`for`·`while`·`try` 문이나 요청이 있는 덩어리를 합친 것도 지적하지 않는다 (남겨도 되는
   것이지 남겨야 하는 것은 아니다. 리뷰 오탐 2026-11-23). 나란한 갈래가 한쪽만 합쳐졌을 때만 지적한다. 짝 중 하나가 두 곳 이상에서
   불려 남은 것은 나란한 갈래 위반이 아니다 (리뷰 오탐 2026-11-23: 직방 `_merge_months` 의 매매 쪽만 합치고 두 곳에서 부르는
   `_jeonse_wolse_of` 는 남았다). 합친 덩어리의 들여쓰기가 주변과 같은지, 공백만 있는 줄이 남지 않았는지도 본다 (ruff 가 W 규칙을
   켜지 않아 잡지 못한다. 2026-11-23 리뷰: 네이버 `search_area` 의 `NaverArticleFilterModel(...)` 인자가 12칸이었다).
   함수를 합쳐 지운 diff 면, 주석으로 옮긴 docstring 의 이유가 부르는 함수 docstring 에 이미 있는지 보고 한 곳으로 모은다.
   docstring 이 무엇을 하는지 요약하고 옮긴 주석이 이유·근거(웹 청크, 실측 날짜, 예시 검색어를 고르는 순서)를 적는 것은 겹침이
   아니다 (리뷰 오탐 2026-11-23: 직방 `settled_item` 의 예시 검색어 주석, 네이버 `get_real_prices` 의 평당 실거래가 주석). 옮긴 주석이 바로 아래 조건과 맞는지도 본다 (옛 docstring 의 빠짐이 그대로 옮겨 온다). 줄이 밀린 파일을 가리키는 이 체크리스트의
   `파일:줄` 은 밀린 수만큼 숫자만 옮기지 말고 그 줄을 열어 설명한 코드에 맞춘다 (원래 어긋나 있던 번호가 그대로 남는다, 2026-11-23 리뷰).
   예: `cli/naver.py` 의 옛 `_is_province_region` (한 곳에서만 부르던 3줄 판정, 2026-11-23 규칙을 둘 때 본 예. 같은 날 종류 검사(`kind == '지역'`)는
   `_area_location` 에 합치고, 코드 모양 판정은 같은 판정을 하던 네이버 `_wide_region_unit` 과 함께 `core/korean.py` `is_province_code` 로 모았다).
   `core/browser.py` `raise_if_entry_failed` (`_fresh_error` 를 합치며 같은 이유가 docstring 과 주석에 근거 날짜를 나눠 두 번
   적혔다, 2026-11-23 리뷰). `providers/daangn/service/region.py` `_search_area_page` (`_area_of` docstring 을 옮긴 주석이
   바로 아래 조건의 시·도 이름 빠짐을 적지 않았다, 2026-11-23 리뷰). 같은 파일 `resolve_area` 의 `dong_hint` 주석
   (`_same_dong_hint` docstring 을 옮긴 주석이 쓸 수 있는 동의 빈 구 이름을 견주는 것을 빠뜨렸다, 2026-11-23 리뷰).
   언제: 함수·클래스를 새로 더하거나, 한 곳에서만 부르던 함수를 부르는 자리에 합친 diff.

## `convention` 규약 위반

1. **소스끼리 부르지 않기.** providers·cli 의 새 import 가 다른 소스를 가리키지 않는가, 실패를 다른 소스로 대신 찾지 않는가.
   언제: providers·cli 에 import 를 더하거나, 실패 뒤 다른 경로로 다시 찾는 갈래를 더한 diff.
2. **조사.** 이름 뒤 조사는 `particle` 로 고르고, '으로/로' 처럼 받지 않는 쌍은 문장을 바꾼다. 예: `providers/daangn/service/compare.py:831`.
   언제: f-string 의 `{이름}` 바로 뒤에 조사('이'·'가'·'을'·'를'·'은'·'는'·'으로'·'로')가 붙은 `+` 줄.
3. **바뀐 동작 근처의 주석·docstring.** 동작을 바꾼 diff 면 그 함수 docstring·주변 주석(요청 수, 예시, `리뷰 오탐` 주석)이 새
   동작과 맞는가. 예: `providers/naver/service/common.py:161` 위 주석 (단지 모드에도 붙는 hint 를 지역 검색에만 붙인다고 적었다, 2026-11-16).
   언제: 동작을 바꾼 diff 에서 그 함수의 docstring·주석이 함께 바뀌지 않았을 때.
4. **금액을 줄이지 않기.** 금액은 만원이고 반올림·버림·올림 없이 원 단위까지 낸다 ([금액·단위](output-contract.md#금액단위)). 금액
   필드·라벨·안내 문구에 `round`·`floor`·`:g`·`.1f` 나 반올림하는 식을 새로 쓰지 않았는가
   (`won_to_manwon`·`format_manwon` 을 쓴다). 거리·면적·비율은 줄여도 된다.
   언제: 금액(`*_manwon`)을 만들거나 글자로 쓰는 `+` 줄.
5. **CHANGELOG 절.** 문구·안내만 바뀐 줄은 `변경`, 받던 입력을 더는 받지 않거나 출력 꼴이 바뀐 줄은 `⚠️ 호환 깨짐` 이다
   ([release.md](release.md) 버전 번호 규칙). 다만 예전 안내·도움말이 실제 동작과 달랐던 것을 바로잡은 줄은 `수정`(문서 오류)이다 (네이버 `search listings --entrance` 안내 줄, 2026-11-18). 예: `CHANGELOG.md` 의 네이버 반경 안내 문구 줄 (호환 깨짐에 있었다, 2026-11-17).
   에러 `code` 가 바뀐 줄과 라이브러리로 쓰는 함수의 예외·반환 모양이 바뀐 줄도 `⚠️ 호환 깨짐` 이다. 같은 diff 의 같은 종류 변경이 한 절에
   모였는지 본다 (당근 `good-neighborhoods` 의 code 변경은 `변경`, `nearby-complexes` 의 code 변경은 `⚠️` 에 있었고 `find_station` 의 새 예외는 빠졌다, 2026-11-20).
   반대로 사용자(에이전트 포함)에게 보이는 출력·에러 `code`·옵션·`notes`·도움말이나 라이브러리 함수의 예외·반환 모양이 바뀌었는데
   `Unreleased` 에 줄이 없는지도 본다 (`CHANGELOG.md` 에 적힌 것만 따라가면 빠진 줄은 보이지 않는다, 2026-11-22).
   언제: `CHANGELOG.md` 에 줄을 더한 diff, 또는 `src/` 에서 출력·에러·옵션을 바꾼 diff.
6. **운용 규칙은 원문 한 곳.** 같은 규칙(작업자가 다르게 해도 되는 범위, 모델 기준, 검증 범위)을 `docs/development/agents.md`·
   `CLAUDE.md`·에이전트 정의·워크플로·skill 에 따로 옮겨 적지 않고 원문 한 곳을 가리키는가. 바꾼 규칙과 같은 주제의 다른 문장도
   함께 바뀌었는가. 예: 원문 `docs/development/agents.md` "지시서와 다르게 할 때" 문단과 그것을 가리키기만 하는
   `.claude/agents/coder.md:22` (2026-11-17 에는 이 규칙을 네 곳에 다른 말로 적어 `first` 묶음 이름만 막는 곳과 다른 묶음이 부르는
   이름까지 막는 곳이 갈렸고, `doc-writer` 를 Sonnet 고정에 넣으며 바로 위 "종합 문서는 Opus" 를 남겼다).
   언제: `.claude/`·`CLAUDE.md`·`AGENTS.md`·`docs/development/agents.md` 를 고친 diff.
7. **같은 소스의 기능 모듈끼리 import 하지 않기.** `service/` 의 새 import 가 [provider-conventions.md](provider-conventions.md#service-모듈을-나누는-기준) 기준 3 의 import 방향을 따르는가.
   확인: diff 의 `+from jibsa.providers.<source>.service.<기능>` 줄. 예: 네이버 `service/complex.py` 가 `service/market_price.py` 의
   `jeonse_ratio_range` 를 가져다 썼다 (2026-11-18).
   언제: `service/` 에 새 import 를 더한 diff.
8. **감시 단계는 비면 고장으로 잡히는 칸을 보는가.** `scripts/monitor/api_check.py` 의 `Step` 기대 칸(`expect`)이 늘 있는 바깥
   dict(`assigned_complexes`)면 키 이름이 바뀌어 안쪽 목록이 빈 채로 와도 정상으로 본다. 그 명령이 정상이면 비지 않는 목록
   (`assigned_complexes.complexes`)을 가리킨다. 확인: 새 `Step` 의 기대 칸이 정상 응답에서 늘 비지 않는 값인지, 그 값을 만드는
   응답 키가 바뀌면 빈 값(`[]`·`{}`·null)이 되는지 본다. 예: `scripts/monitor/api_check.py:214` (네이버 `school --complexes`
   단계가 바깥 dict 만 봤다, 2026-11-18). 명령 하나가 덤 엔드포인트를 여럿 부르면 덤마다 그 값을 기대 칸으로 보는 `Step` 이
   있는가도 본다. 덤 조회는 실패하면 `null` 로만 남아, 다른 덤을 보는 단계로는 못 잡는다 (네이버 빌라 `real-price` 가
   `nearby_transactions.trades` 만 보고 평당 실거래가 `price_per_pyeong_trades` 를 보지 않았다, 2026-11-19). 반대로 사이트가
   정상이어도 빌 수 있는 값을 기대 칸으로 걸면 고장 알림이 거짓으로 난다: 조건으로 고른 목록(최근입주), 시세 0 을 `null` 로
   내는 값, 신규분양처럼 값이 없는 대상을 고를 수 있는 `Capture` 는 `may_be_empty` 로 두거나 그 대상을 피해 고른다
   (`scripts/monitor/api_check.py` 의 직방 가락동 최근입주·`catalog` 직방시세·`{apt}` Capture, 2026-11-20). 안내 없이 `null` 이 되는 조건이 있는 값(단기임대 `host_other_listing_count` 는 임대인 ID 가 없으면 안내 없이 `null`)이나 정상 단지에도 `null` 일 수 있는 값(직방 `complex` 단지 직방시세, 2026-11-21)도 `also_expect` 에 걸지 않는다. 기간 기본값으로 부르는 단계도 감시 시각에 빌 수 있다: 등록 기준 '이번달' 집계(한국 날짜 기준)는 매달 1일 새벽(감시 04:17)에 비어 거짓 고장을 낼 수 있어 지난 기간(지난달·30일)으로 부른다 (`scripts/monitor/api_check.py` 의 직방 `region-ranking`, 2026-11-22).
   언제: `GROUPS` 에 `Step` 을 더하거나 기대 칸(`expect`·`also_expect`)을 바꾼 diff, 기존 명령에 덤 엔드포인트를 더한 diff.

## 지적하지 말 것

일부러 다르게 둔 이유가 코드·주석·소스 가이드에 있으면 지적하지 않는다. 다만 `# 리뷰 오탐` 주석이라도 근거가 "실측에 없었다"·
"문서에 그렇게 적었다" 뿐이면 이유가 아니다 ([코드 리뷰](agents.md#코드-리뷰) 2단계·3단계. 문서는 코드를 보고 쓴 것이라 제자리를 돈다).
주석이 설명하는 동작이 실제 코드 동작과 다르면 그 주석도 이유가 아니다 (당근 주차 주석이 코드와 반대였다, 2026-11-20). 그런
자리는 서버가 보낼 수 있는 값으로 다시 따져 지적해도 된다.

1. **"비슷한 두 함수·검사를 합쳐라".** 입력 형식, 실패 시 계약(키 하나 null 이냐 둘 이냐), 예산 세는 법, 층의 책임, 검사 시점,
   호출마다 다른 에러 문구가 달라서 따로 둔 것은 합치면 출력이 바뀌거나 갈래 인자가 붙은 함수가 된다. 그 차이가 주석에 있으면
   지적하지 않는다 (없으면 `design` 1 대로 지적한다). 예: `providers/dabang/service/school.py:482`, `core/schema.py:37`.
2. **닿지 않는 경로의 틀린 값.** 모든 호출부가 돌려받은 값을 바로 거절하거나, 값이 Literal 고정이라 받침이 늘 있거나, 앞 상한에
   먼저 닿아 그 갈래에 가지 않으면 오탐이다. 지적하기 전에 그 갈래에 닿는 입력을 하나 댈 수 있어야 한다.
   예: `providers/dabang/service/region.py:231`, `providers/daangn/service/complex.py:1076`.
3. **"받은 결과를 `[:limit]` 로 잘라라 / 쪽 사이 중복을 지워라".** 서버가 `first` 만큼만 주고, 자르면 커서가 잘린 매물 뒤를
   가리켜 빠진다. 커서로 이어진 쪽끼리는 겹치지 않는다. 예: `providers/daangn/service/search.py:208`.
4. **"0 과 null, null 과 키 삭제를 통일하라".** 웹이 0 을 그리는 법('0원' 이냐 '정보 없음' 이냐)이 칸마다 다르고, 웹이 그릴 수
   있는 칸인데 값만 없으면 해당 없음이 아니라 모름(`null`)이다. 예: `providers/dabang/service/real_price.py:854`.
5. **"요청 전에 막아라" (이름을 찾아봐야 종류를 아는 경우).** 동인지 구인지 모양으로 짐작해 막으면 잘못 막는다.
   예: `cli/daangn.py:1095`.
6. **"이름으로 중복을 지우면 다른 역이 합쳐진다".** 서버가 같은 이름 역을 노선 꼬리로 갈라 주고 이름이 곧 키다.
   예: `providers/daangn/service/commute.py:468`. 매물 카드 인근 역·출퇴근 경로처럼 역 **이름**으로 도보 분·경로를 맞추는 것도
   맞다 (2026-11-19 리뷰 오탐, 근거 고침 2026-11-20). 인근 역(`walk_minutes_to`)은 이름 첫 일치만 쓰는데, 서버가 같은 역을
   이름 하나에 노선 여럿으로 묶어 줘(신촌역은 두 노선이 한 역) 한 역이 둘로 오지 않는다. 이름이 같은 다른 역이 한 카드에 함께
   오지 않는다는 것은 코드로 막힌 것이 아니라 추론이다. 출퇴근 경로 `_route` 는 노선 꼬리가 어긋나 처음·끝 역 이름이 맞지 않으면
   None(모름)을 줘 틀린 경로가 나가지 않는다 (`providers/daangn/service/common.py`, `providers/daangn/service/commute.py`).
7. **응답 필드 표기·정밀도.** 엔드포인트마다 snake_case·camelCase 가 다르고(`providers/dabang/api/response/sale.py:471`), 거리를
   소수로 받는 것은 정렬 뒤 출력할 때만 웹 `d` 식(`_nearest` 의 `distance_m`)으로 반올림하려는 것이다 (`providers/dabang/service/nearby.py:375`).
8. **검토하고 그대로 둔 설계.** `proxy=''` 를 잘못된 주소로 보기, 요청 하나 전체에 시간 상한 없음, 탭이 닫히면 닫고 다시 띄우기
   (`core/browser.py:671`·`:818`·`:1761`), 평형 코드가 없을 때 전체 평균으로 물러서지 않기
   (`providers/daangn/service/compare.py:508`).
9. **꺼진 상태가 정상인 기능 스위치의 기본값.** 한 호출부만 켜고 나머지는 꺼야 맞는 bool(`listing_search`)은 `design` 2 가
   아니다. 지금 호출부는 모두 맞고, 틀리려면 호출부가 바뀌어야 한다. 예: `providers/naver/service/region.py:788`.
10. **"응답 모델 칸의 자료형이 바뀌면 그 응답을 같이 읽는 다른 명령까지 `PARSE_ERROR` 가 된다".** 글자 칸에 숫자가 오는 것처럼 응답 형식이 바뀌는 일은 [매일 API 감시](README.md#매일-api-감시)가 잡는 고장이라 칸마다 받는 형식을 미리 넓혀 두지 않는다 ([코드 리뷰](agents.md#코드-리뷰) 2단계). 서버가 소수·0 처럼 지금 값의 연장을 줄 수 있는 칸(`correctness` 6)과는 다르다. 예: 직방 단지 상세 `relateDanji`·`landTradePermit` (2026-11-21).
11. **웹이 만원 정수로만 보여 주는 금액을 원 단위로 반올림하는 식을 웹 `Math.round` 와 견주지 않는다.** 금액은 원 단위까지 내는
    것이 규약이고(`convention` 4), 견줄 웹 값이 없다. 예: `providers/daangn/service/compare.py` 관리비 (2026-11-19 리뷰 오탐).
