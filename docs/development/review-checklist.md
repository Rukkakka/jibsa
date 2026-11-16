# 리뷰 체크리스트

[코드 리뷰 절차](agents.md#코드-리뷰) · [꼭 지킬 것](../../AGENTS.md#꼭-지킬-것) · [출력 규약](output-contract.md) · [웹 화면과의 대응](provider-conventions.md#웹-화면과의-대응)

지난 리뷰에서 실제로 나온 버그 패턴과 되풀이된 오탐을 관점별로 모았다. 리뷰어는 여섯 관점 절의 항목을 하나씩 바뀐 코드에 대
보고(해당 없는 항목은 건너뛴다), 그다음 목록에 없는 문제도 찾는다. 규칙 자체는 위 링크 문서에 있고 여기에는 옮겨 적지 않는다.

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
   뺀 것까지 센 `total` 과 견주지 않는다. 확인: "다 받고 1건 뺌" 과 "limit 에 닿고 1건 뺌" 으로 따라간다.
   예: `providers/zigbang/service/common.py:613`.
   언제: `has_more`·`[일부]`·`inspected`·`received`·`total` 을 정하는 줄이나 결과를 빼는(거르는) 줄을 바꾼 diff.
3. **덜 받은 것을 "전부·없음" 으로 단정.** 첫 쪽·상한·멈춘 목록의 수를 전체 수로 쓰거나, 남았는데 "없습니다"·"이 N건이 전부"
   라고 하지 않는가 ('이상'·`[일부]`·`null` 로 알린다). 확인: 수·'없'·'전부' 가 든 안내마다 그 수가 끝까지 받은 수인지 본다.
   예: `providers/daangn/service/region.py:474` (첫 쪽 100곳을 "100곳 있습니다", 실제 208곳).
   언제: 수를 담은 안내('곳'·'건'·'없'·'전부')나 `total` 을 쓰는 `+` 줄.
4. **후보를 다 모은 뒤 판정하나.** "하나뿐"·"없음"·"이름이 같은 것이 여럿" 을 판정하는 목록이 그 시점에 완전한가.
   - 좌표 없음 같은 이유로 **거른 뒤** 개수를 세지 않는가 (웹에는 후보가 둘인데 남은 하나를 고름).
   - **첫 쪽만** 보고 고르지 않는가 (다음 쪽이 있으면 뒤에 같은 이름이 더 있을 수 있다).
   - 여럿일 때 일찍 멈춰 빠뜨리지 않는가, 에러에 합친 이름이 아니라 실패한 이름을 대는가.
   - 여러 단어 검색어('수정구 신흥')에서 전체와 끝 단어를 섞어 비교하지 않는가.
   - 멈추는 데만 쓰던 결과("여럿이면 멈춘다")를 고르는 데("하나뿐이면 고른다")에도 쓰게 바꿨으면, 그 하나가 고르려는 것과 같은
     곳인지 대조하는가. 다른 자료(주소 검색 ↔ 자동완성)의 한 건은 다른 곳일 수 있다. 예: `providers/naver/service/region.py:221`
     (bcode 대조 없이 주소 검색 1건으로 자동완성 동을 골랐다, 2026-11-16).

   확인: 후보 목록에 걸린 `len(...) == 1`·`break`·`next(...)`·`[0]` 자리마다 그 목록이 어디서 왔는지 거슬러 본다.
   예: `providers/naver/service/region.py:162`·`:191`·`:170` (2026-11-16), `providers/daangn/service/school.py:204`.
   언제: 후보 목록에 `len(...) == 1`·`next(`·`[0]`·`break` 가 걸린 `+` 줄, 또는 이름·주소로 후보를 고르거나 거르는 줄,
   `> 1` 로 멈추던 결과에 `== 1` 갈래를 더한 diff.
5. **누락값과 0.** 실패·모름은 `null`, 해당 없음은 키 삭제, 정말 빈 것만 `[]` 인가. `or`·`or 0`·`or inf`·`if not x` 로 0 과
   모름을 섞지 않는가. 날짜·층 자리의 `'-'`·빈 글자를 그대로 내지 않는가. 확인: 새 `or ...`·truthiness·기본값 `[]`·except 가
   돌려주는 값을 본다. 예: `cli/daangn.py:816` (실패한 칸을 `[]` 로), `providers/naver/service/listing.py:560` ('-', 2026-11-16).
   언제: `+` 줄에 `or `·`if not `·`else None`·기본값 `[]`·값을 돌려주는 `except` 가 있을 때, 출력 필드를 더하거나 바꾼 diff.
6. **서버 값 한 칸이 결과 전체를 깨뜨림.** 서버 글자·목록·헤더를 `int()`·`[0]`·`del`·`.encode` 로 바로 다루지 않는가 (그 칸만
   `null`·건너뛰기여야 한다). 확인: diff 의 그 호출과 Optional 아닌 list 필드에 빈 글자·'-'·null·소수를 넣어 본다.
   예: `providers/daangn/service/compare.py:533` (연월 `int()` 로 비교 전체가 PARSE_ERROR).
   언제: 서버 값에 `int(`·`float(`·`[0]`·`del `·`.split(`·`.encode` 를 바로 쓰는 `+` 줄, `api/response/` 의 필드 자료형을 바꾼 diff.
7. **지운 줄이 받던 입력.** `git diff` 의 `-` 줄이 받던 꼴(더 짧은 날짜, 다른 구분자, 빈 값)을 `+` 줄도 받는가. 고친 코드가
   예전보다 정보를 버리면 퇴보다. 확인: 지운 분기와 새 분기에 같은 입력을 넣어 비교한다.
   예: `providers/naver/service/listing.py:129` (연월만 온 날짜의 '초순' 이 빠졌다, 2026-11-16).
   언제: 파싱·분기·검사의 `-` 줄을 다른 코드로 바꾼 diff (지우기만 한 줄도).
8. **`--next` 로 이어 받을 때.** 첫 쪽 전용 안내를 되풀이하지 않는가, 앞 쪽의 모름(total None, 실패)을 이어 쓰지 않는가, 이어
   받은 첫 쪽이 비거나 null 일 때 "다 받음" 으로 끝내지 않는가. 확인: `resumed` 갈래마다 첫 쪽·이어 받은 쪽을 따라간다.
   예: `providers/daangn/service/search.py:381`, `providers/dabang/service/common.py:705`.
   언제: `resumed`·`--next`·커서 이어 받기(`cli/paging.py` 포함)를 건드리거나, 첫 쪽에만 붙는 안내를 더한 diff.
9. **실패·취소 경로 (주로 `core/`).** 예외·Ctrl+C·다른 프로세스와 겹칠 때 브라우저·잠금·쿠키 파일을 정리하는가, 다른 프로세스가
   새로 쓴 파일을 덮지 않는가, 잠깐의 실패에 오래 남는 상태를 만들지 않는가. 예: `core/browser.py:1363`·`:1630`.
   언제: `core/` 의 `try`·`except`·`finally`·잠금·파일 쓰기·브라우저 열고 닫기를 바꾼 diff.
10. **공백뿐인 사용자 입력.** 위치·이름 인자는 `min_length=1` 을 공백(`' '`)으로 지나므로 `.split()[-1]`·`[0]` 이 IndexError
    (INTERNAL_ERROR)가 된다. 서버가 빈 응답을 줘서 지금 안 닿는 것은 막는 이유가 아니다. 확인: `' '` 를 넣어 그 줄까지 따라간다.
    예: `providers/naver/service/region.py:172` (`words[-1]`, 요청 전에 `:740` 에서 INVALID_ARGUMENT 로 막았다, 2026-11-16).
    언제: 사용자 검색어에 `.split()`·인덱스를 쓰는 줄을 조건 밖으로 옮기거나 새로 더한 diff.

## `contract` 출력 계약

1. **안내를 따르면 되는가 (모든 모드에서).** `--limit` 이 이미 최대값인데 늘리라고 하지 않는가. 좁히라고 권하는 것('지역'·
   '반경'·평형)이 그 명령·검색 방식에 실제로 있는가. 한 명령의 여러 모드(`--complex`·`--redevelopment` 등)가 같은 hint 표를
   쓰면, 그 hint 가 권하는 옵션을 모든 모드가 받는가. 확인: `more_hint`·`pagination_notes`·`UsageHints` 의 값을 그 모드의 옵션
   검사와 대조한다. 예: `core/listing.py:333`, `cli/naver.py:991` (단지 모드에 받지 않는 `--radius` 를 권함, 2026-11-16).
   언제: `more_hint`·`pagination_notes`·`UsageHints`·`hint=` 를 바꾸거나, 한 명령에 모드·옵션을 더한 diff.
2. **예시 이름과 권하는 명령.** hint 의 예시·명령을 그대로 넣으면 그 명령이 받는가 (동을 받지 않는 명령에 동 이름, 여전히 모호한
   예시, 필수 옵션을 빼라는 안내). 확인: 예시를 그 명령의 인자 검사·resolver 에 넣어 따라간다.
   예: `providers/daangn/service/region.py:300`, `providers/daangn/service/commute.py:268`.
   언제: hint·notes·에러 message 에 `jibsa ` 명령이나 예시 이름이 든 `+` 줄.
3. **notes 태그.** 더 있음 `[일부]`, 뺀 것 `[제외]`, 찾은 범위가 다름 `[범위]`, 덤 조회 실패 `[실패]` 가 맞게 붙었는가 (맨
   문자열은 `[참고]` 로 나간다, [docs/common.md](../common.md)). 예: `providers/daangn/service/commute.py:260`.
   언제: `notes` 에 문자열을 더하는 `+` 줄.
4. **한 결과 안 안내끼리.** "전부입니다" 와 `[일부]`, 같은 안내 여러 번, '곳'·'건' 섞임이 함께 나오지 않는가. 확인: 여러 갈래가
   함께 참이 되는 입력을 찾는다. 예: `providers/zigbang/service/common.py:611`.
   언제: 한 결과에 안내를 붙이는 갈래가 둘 이상인 함수를 바꾼 diff.
5. **에러 code·hint 가 원인과 맞는가.** 첫 화면 5xx 를 "스펙 변경" 으로, 형식 오류 400 을 "없는 ID" 로, 정상 0건을 에러로 알리지
   않는가. 감시·에이전트가 hint 문구가 아니라 `code`·`blocked` 같은 필드로 가르는가. 예: `cli/output.py:375`.
   언제: 에러 클래스·`code`·hint 를 고르는 갈래나 `raise ...Error(` 를 더하거나 바꾼 diff.
6. **사용법 오류 안내가 그 명령 기준인가.** 다른 명령의 hint 를 물려받아 원래 없던 옵션을 "없앴습니다" 라고 하지 않는가, 한 값
   옵션을 반복하면 마지막 값만 남는 것을 막는가. 예: `cli/daangn.py:380`, `cli/daangn.py:1718`.
   언제: 옵션 검사·사용법 오류(`BadParameter`·`check_choice`·`UsageHints`)를 바꾼 diff.
7. **help·Field description·`docs/<source>.md` 가 동작과 같은가.** 기본값·거르기를 바꾼 diff 면 셋을 함께 grep 한다.
   예: `cli/daangn.py:253`.
   언제: 기본값·거르기·옵션·출력 필드를 바꾼 diff (help·`Field(description=`·`docs/<source>.md` 중 일부만 바뀌었으면 특히).

## `web` 웹 대응

1. **웹 식을 옮길 때 JS 의미까지.** `??` 와 `||`(0·빈 글자), `Math.round` 와 Python `round`(은행가 반올림), 정수 버림, 안정 정렬,
   "첫 항목 기준" 같은 기준점. 확인: 주석의 번들 식과 한 줄씩 대조하고 0·x.5·동점·첫 항목 없음을 넣어 본다.
   예: `providers/daangn/service/real_price.py:1175`, `providers/daangn/service/complex.py:378`.
   언제: 주석에 번들 식(JS)이 붙은 계산, 또는 `round(`·`//`·`sorted(`·`max(`·`min(` 이 든 `+` 줄.
2. **웹이 보내는 변수 모양 그대로인가.** 조건이 없으면 웹처럼 null 을 보내는가(빈 객체·빈 목록이 아니라), 웹 화면이 받는 단위를
   넘는 조합을 만들지 않는가. 예: `providers/daangn/api/request/common.py:211` (`{salesTypes: []}`).
   언제: `api/request/` 의 변수·쿼리 모양이나 그 기본값을 바꾼 diff.
3. **사이트에 없는 결과.** 받은 결과를 같은 조건으로 다시 거르거나 다른 소스로 대신 찾지 않는가, 후보 중 하나를 임의로 고르지
   않는가 (위 `correctness` 4), `[제외]` 문구가 실제로 없는 사유("조건 불일치")를 말하지 않는가.
   예: `providers/daangn/service/common.py:924`.
   언제: 받은 목록을 거르기·합치기·다시 정렬하기·고르기 하는 `+` 줄, `[제외]` 문구.
4. **웹과 다른 개선을 적었는가.** 웹에 없는 동작이 그 소스 가이드 "웹과 다른 점" 에 있는가. 예: `providers/daangn/service/school.py:177`.
   언제: 웹에 없는 옵션·기본값·묶어 받기를 더한 diff.

## `requests` 요청 수·차단 위험

1. **이미 아는 것을 다시 묻지 않는가.** 앞 결과·캐시·방금 받은 응답으로 아는 값을 다시 묻거나, 답이 같을 두 번째 요청을 보내지
   않는가. 확인: 루프·후속 검사 안의 resolve·search 호출이 결과를 바꿀 입력이 실제로 있는지 따진다.
   예: `providers/daangn/service/region.py:557`, `providers/naver/service/region.py:226` (같은 자동완성 재호출, 2026-11-16).
   언제: 루프·후속 검사 안에 resolve·search·client 호출이 든 `+` 줄.
2. **결과가 정해진 뒤의 요청.** 더 없음을 알면서 빈 쪽을 한 번 더 받거나, 빈 쪽의 hasMore 를 믿고 쪽 상한까지 묻지 않는가.
   예: `providers/daangn/service/common.py:845`.
   언제: 쪽 넘기기 루프의 멈춤 조건을 바꾼 diff (`correctness-1` 과 같은 자리).
3. **덤 조회의 순서와 실패.** 수 세기·동 이름 같은 덤 조회를 본 조회 뒤에 하는가 (덤이 첫 요청이면 첫 화면 실패를 삼킨다), 덤이
   실패(요청 제한 포함)해도 받은 결과를 버리지 않는가. 예: `providers/daangn/service/search.py:113`.
   언제: 수 세기·이름 찾기 같은 덤 조회를 더하거나 순서를 바꾼 diff.
4. **요청 전에 막을 수 있는 입력.** 결과와 상관없이 막힐 입력을 요청 뒤에 막지 않는가 (이름 모양으로 짐작해야만 막을 수 있으면
   아래 "지적하지 말 것"). 예: `providers/dabang/service/ranking.py:780`.
   언제: 입력 검사·에러를 요청 뒤에 두는 `+` 줄.
5. **transport 밖 요청과 서버 신호 (`core/`).** CORS 사전 요청·redirect·첫 화면도 세는가, `Retry-After` 보다 짧게 쉬지 않는가,
   429 에 쿠키를 버려 첫 화면 요청을 다시 쏟지 않는가. 예: `core/browser.py:1197`·`:1248`.
   언제: `core/browser.py`·`core/http.py`·`core/ratelimit.py` 를 바꾼 diff.

## `design` 구조·중복·단순화

1. **같은 규칙 두 벌.** 같은 판정식·문구·흐름·필터가 다른 함수·파일에 또 있는가, 이미 있는 helper 를 다시 만들었는가.
   확인: 새 함수·식·문구의 핵심 낱말로 grep 한다. 예: `core/listing.py:333`, `providers/daangn/service/common.py:834`,
   `providers/naver/service/common.py:824` (동 경계/반경 갈래가 세 함수에 따로 있었다, 2026-11-16).
   언제: 새 함수·상수·문구·필터·갈래를 더한 diff.
2. **호출부마다 달라야 할 인자에 기본값.** `narrow`·`max_limit` 처럼 호출부마다 값이 달라야 맞는 인자에 기본값을 두면 빠뜨려도
   조용히 틀린다. 설정을 dict 로 `**` 풀어 넘기지 않는다. 예: `providers/naver/service/common.py` `pagination_notes` 의 `narrow`.
   언제: 기본값이 있는 인자를 더하거나, 설정 dict 를 `**` 로 넘기는 `+` 줄.
3. **닿지 않는 갈래·쓰지 않는 인자.** 부르는 곳이 사라진 갈래·예외 클래스, 받기만 하고 쓰지 않는 인자, 늘 같은 값(`[]`·`None`)만
   돌려주게 된 반환값과 그 값을 받아 잇는 호출부가 남지 않았는가. 확인: 갈래를 지운 함수의 `return` 을 모두 보고 호출부를 grep 한다.
   예: `core/browser.py:448`, `providers/zigbang/service/region.py` `region_notes` (안내 갈래를 지운 뒤 늘 `[]` 였고 호출부 여섯 곳이
   이었다. 검사 함수 `settled_item` 으로 바꿨다, 2026-11-16).
   언제: 코드를 지우거나, 부르는 곳을 옮기거나, 인자를 더한 diff, 함수의 갈래를 지워 돌려주는 값이 줄어든 diff.
4. **따로 도는 CI 단계의 짝.** `.claude/` 처럼 문서로 분류돼 pytest 를 건너뛰는 파일을 지키는 테스트는 CI lint 단계에서 이름으로
   따로 돈다. 같은 종류의 테스트를 더했으면 그 단계 명령과 `workflow.md` 설명에도 더했는가. 확인: 새 테스트가 지키는 파일이
   `ci.yml` 의 `DOC_PATTERN` 에 드는지 보고 lint 단계의 `pytest` 명령과 대조한다.
   예: `.github/workflows/ci.yml:102` (`test_workflow_args_parsing_blocks_match` 가 빠져 있었다, 2026-11-16).
   언제: `.claude/`·`docs/` 를 읽는 테스트를 `tests/` 에 더한 diff.

## `convention` 규약 위반

1. **소스끼리 부르지 않기.** providers·cli 의 새 import 가 다른 소스를 가리키지 않는가, 실패를 다른 소스로 대신 찾지 않는가.
   언제: providers·cli 에 import 를 더하거나, 실패 뒤 다른 경로로 다시 찾는 갈래를 더한 diff.
2. **조사.** 이름 뒤 조사는 `particle` 로 고르고, '으로/로' 처럼 받지 않는 쌍은 문장을 바꾼다. 예: `providers/daangn/service/compare.py:831`.
   언제: f-string 의 `{이름}` 바로 뒤에 조사('이'·'가'·'을'·'를'·'은'·'는'·'으로'·'로')가 붙은 `+` 줄.
3. **바뀐 동작 근처의 주석·docstring.** 동작을 바꾼 diff 면 그 함수 docstring·주변 주석(요청 수, 예시, `리뷰 오탐` 주석)이 새
   동작과 맞는가. 예: `providers/naver/service/common.py:136` 위 주석 (단지 모드에도 붙는 hint 를 지역 검색에만 붙인다고 적었다, 2026-11-16).
   언제: 동작을 바꾼 diff 에서 그 함수의 docstring·주석이 함께 바뀌지 않았을 때.
4. **금액을 줄이지 않기.** 금액은 만원이고 반올림·버림·올림 없이 원 단위까지 낸다 ([금액·단위](output-contract.md#금액단위)). 금액
   필드·라벨·안내 문구에 `round`·`floor`·`:g`·`.1f` 나 0.1만원으로 반올림하는 `won_to_manwon` 을 새로 쓰지 않았는가
   (`won_to_manwon_exact`·`format_manwon` 을 쓴다). 거리·면적·비율은 줄여도 된다. 네이버·다방·당근의 기존 반올림은 #257 로 남겨 둔 것이라 지적하지 않는다.
   언제: 금액(`*_manwon`)을 만들거나 글자로 쓰는 `+` 줄.

## 지적하지 말 것

일부러 다르게 둔 이유가 코드·주석·소스 가이드에 있으면 지적하지 않는다. 다만 `# 리뷰 오탐` 주석이라도 근거가 "실측에 없었다"
뿐이면 이유가 아니다 ([코드 리뷰](agents.md#코드-리뷰) 2단계). 그런 자리는 서버가 보낼 수 있는 값으로 다시 따져 지적해도 된다.

1. **"비슷한 두 함수·검사를 합쳐라".** 입력 형식, 실패 시 계약(키 하나 null 이냐 둘 이냐), 예산 세는 법, 층의 책임, 검사 시점,
   호출마다 다른 에러 문구가 달라서 따로 둔 것은 합치면 출력이 바뀌거나 갈래 인자가 붙은 함수가 된다. 그 차이가 주석에 있으면
   지적하지 않는다 (없으면 `design` 1 대로 지적한다). 예: `providers/dabang/service/school.py:446`, `core/schema.py:37`.
2. **닿지 않는 경로의 틀린 값.** 모든 호출부가 돌려받은 값을 바로 거절하거나, 값이 Literal 고정이라 받침이 늘 있거나, 앞 상한에
   먼저 닿아 그 갈래에 가지 않으면 오탐이다. 지적하기 전에 그 갈래에 닿는 입력을 하나 댈 수 있어야 한다.
   예: `providers/dabang/service/region.py:232`, `providers/daangn/service/complex.py:1076`.
3. **"받은 결과를 `[:limit]` 로 잘라라 / 쪽 사이 중복을 지워라".** 서버가 `first` 만큼만 주고, 자르면 커서가 잘린 매물 뒤를
   가리켜 빠진다. 커서로 이어진 쪽끼리는 겹치지 않는다. 예: `providers/daangn/service/search.py:208`.
4. **"0 과 null, null 과 키 삭제를 통일하라".** 웹이 0 을 그리는 법('0원' 이냐 '정보 없음' 이냐)이 칸마다 다르고, 웹이 그릴 수
   있는 칸인데 값만 없으면 해당 없음이 아니라 모름(`null`)이다. 예: `providers/dabang/service/real_price.py:895`.
5. **"요청 전에 막아라" (이름을 찾아봐야 종류를 아는 경우).** 동인지 구인지 모양으로 짐작해 막으면 잘못 막는다.
   예: `cli/daangn.py:1095`.
6. **"이름으로 중복을 지우면 다른 역이 합쳐진다".** 서버가 같은 이름 역을 노선 꼬리로 갈라 주고 이름이 곧 키다.
   예: `providers/daangn/service/commute.py:468`.
7. **응답 필드 표기·정밀도.** 엔드포인트마다 snake_case·camelCase 가 다르고(`providers/dabang/api/response/sale.py:471`), 거리를
   소수로 받는 것은 정렬 뒤 출력할 때만 반올림하려는 것이다 (`providers/dabang/service/nearby.py:360`).
8. **검토하고 그대로 둔 설계.** `proxy=''` 를 잘못된 주소로 보기, 요청 하나 전체에 시간 상한 없음, 탭이 닫히면 닫고 다시 띄우기
   (`core/browser.py:671`·`:818`·`:1739`), 평형 코드가 없을 때 전체 평균으로 물러서지 않기
   (`providers/daangn/service/compare.py:611`).
