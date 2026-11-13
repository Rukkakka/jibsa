# 네이버 개발 가이드

[CLI 사용법](../../naver.md) · [개발 환경·검증](../README.md) · [공통 아키텍처](../architecture.md) · [provider 작성 규약](../provider-conventions.md) · [출력 계약](../output-contract.md) · [코드 형식](../code-style.md)

공통 규약에 없는, 네이버에만 있는 구현과 예외를 적는다.

## 명령과 요청 흐름

| CLI 명령 | 주요 경로 | service 모듈 |
| --- | --- | --- |
| `search listings` | 지역 해석 → 동 경계 목록, 반경이면 사각형 정렬 목록 (`--sort 가까운순` 만 지도 칸 → 칸 매물) | `search` |
| `search complexes` | 지역 해석 → 단지 목록·마커 | `search` |
| `complex` | 이름/번호 해석 → 기본 정보·통계·평형·학교, 재건축 단지면 사업 단계, 선택 평형 부가 정보 | `complex` |
| `search listings --complex` | 단지 해석 → 동·평형 검증 → 단지 매물 페이지 | `listing` |
| `listing` | 매물 키 → 기본 정보 → 관리비·법정동 이름 → 교통·학교, 매매 비용 부가 조회 | `listing` |
| `real-price` | 단지·평형별 실거래 페이지, `--period` 면 기간 목록 1회 (빌라는 페이지를 기간 시작일까지) | `real_price` |
| `market-price` | 단지 해석 → 기관별 주간 시세 기간 목록 1회 | `market_price` |
| `redevelopment` | 구역 기본 정보 → 구역 매물 통계 | `redevelopment` |
| `regions` | 시·도 목록 → 시·도면 하위 목록, 아니면 자동완성 → 시·군·구 하위 목록 | `region` |
| `school` | 학교 상세, `--complex` 면 배정 동 (단지 번호만이면 빌라 여부 확인 1회, 빌라면 단지가 있는지 확인 1회 더) | `school` |
| `search redevelopment` | 지역 해석 → 재개발 구역 목록·마커 | `redevelopment` |
| `search listings --redevelopment` | 구역 번호 → 재개발 매물 페이지 | `redevelopment` |
| `trend` | 법정동 코드 해석 → 매물 수·평당 호가·거래 건수 3종 조회 | `trend` |

## 소스 고유 구현

모든 응답이 `{isSuccess, detailCode, message, result}` 봉투다
 (`NaverResponseModel[T]`). service 는 `unwrap()` 으로 `result` 를 꺼내고, 실패면 `JibsaError`
 (`NOT_FOUND` / `UPSTREAM_ERROR`)를 던진다. 실패 봉투는 HTTP 상태와 별도로 검사한다. 금액은 원 단위라
 `won_to_manwon`을 거친다. 가장 차단이 잦은 소스라 요청 수를 늘리는 변경(매물마다 추가 조회 등)은 피한다.
 429 는 봇 차단이라 일반 재시도 대상이 아니다. `should_retry_naver`는 5xx 와 `RETRYABLE_TRANSPORT_ERRORS`(timeout·연결 실패 등)만 재시도한다.

빌라 단지(A05·A06·A07)인지는 명령 맨 앞에서 한 번에 정하지 않고, 아파트 쪽 응답이 비었을 때 그 자리에서 정한다 (`villa_by_complex_response` docstring). 맨 앞에서 정하면 단지 종류를 모를 때마다(대부분 아파트) 요청이 1회 늘기 때문이다. 판별이 여러 곳에 흩어진 것은 이 때문이며, 한 번 빌라로 정해지면 빌라 엔드포인트의 실패 응답은 0건이 아니라 에러로 낸다. 단지 매물 목록은 아파트·빌라 모두 없는 단지 번호에도 빈 성공 응답을 줘서(2026-10-23 실측: 99999999 와 헬리오시티 111515 의 빌라 목록이 같은 `totalCount: 0`), 단지 번호만 받아 종류를 모른 채 0건이면 단지 정보(아파트 → 빌라)로 단지가 있는지 확인한다 (`_raise_if_missing_complex`). 빌라 단지에 거래·동이 없을 때 빌라 엔드포인트는 실패가 아니라 빈 목록을 주고(서진빌라 724112 월세 실거래 0건), 아파트 동 목록(`complex/buildingList`)도 빌라 단지에 `result=null` 이 아니라 빈 목록을 준다 (2026-10-10 실측).

응답 값을 요청 모델(Literal·pattern)에 다시 넣을 때는 먼저 아는 값인지 확인한다. 요청 모델 검증 실패는 `handle_errors` 가 사용자 입력 오류(`INVALID_ARGUMENT`)로 내기 때문이다. 매물 상세는 모르는 매물 유형을 `KNOWN_REAL_ESTATE_TYPES` 로 걸러 볼 수 없는 매물로 내고, 반경 검색은 클러스터 ID 형식이 다르면 `PARSE_ERROR` 로 바꾼다.

service 가 부르지 않는 엔드포인트 3개(`article/agent`, `complex/holdingTax`, `complex/declaredValue/pyeongType`)는 라이브러리용으로 client 메서드만 있다 (`article/agent` 는 중개사 정보라 출력하지 않는다는 원칙에 따라 쓰지 않는다). 모델은 [기준 7](../provider-conventions.md#service-모듈을-나누는-기준)대로 경로가 같은 기능 모듈에 둔다 (`article/agent` → `listing`, 나머지 둘 → `complex`).

### 브라우저 요청

(2026-11-09 실측) 공통 동작은 [브라우저 요청](../architecture.md#브라우저-요청). 네이버만의 값:

- 첫 화면은 `https://fin.land.naver.com/` (지도 `/map?...` 으로 넘어간다). load 시점 쿠키는 0~6개였다가 2초 안에 8개가 다 생겨
  `NNB`(400일)를 기다린다. 그 밖에 `NAC`·`BUC`(400일), `NACT`(24시간), `SRT30`(30분), `SRT5`(5분). `BUC` 는 front-api 응답마다
  서버가 새 값으로 바꿔, 명령이 끝날 때 남기는 쿠키에 따라 들어간다. 쿠키는 몇백 ms 에 걸쳐 나눠 생겨, `NNB` 가 생긴 뒤에도
  쿠키가 0.5초 동안 더 바뀌지 않을 때까지 기다린다 (`READY_COOKIE_SETTLE_SECONDS`). `NNB` 만 보고 멈추면 같은 순간에 생기는
  `NAC`·`NACT` 를 놓쳐 6개만 남았다. 30분 뒤 다시 열 때는 남긴 `NNB` 등 영구 쿠키를 넣고 열어 `NNB` 가 그대로다. `NNB` 가
  처음부터 있어 `NNB` 로는 첫 화면이 돌았는지 알 수 없으니, 이번 방문에서 사이트가 쿠키를 심거나 바꾼 것도 본다
  (2026-11-10 실측: 처음 열면 load 뒤 1.4초에 8개가 한 번에, 다시 열면 load 뒤 0.2초에 `BUC`·`SRT5`, 0.4초에 `NAC`·`NACT`).
- 첫 화면이 front-api 를 18~22번 부른다. 그래서 분당 상한을 예전 우리 요청 몫 30 에 그만큼 더한 60 으로 둔다. 상한은 첫
  화면 요청과 우리 요청을 합친 수에 걸려, 남긴 쿠키로만 보내는 명령(30분 중 대부분)은 우리 요청만 분당 60건(1초 간격의 최대)까지
  나간다. 아래 실측이 그 속도라 일부러 둔 값이다. 429 에 `Retry-After` 가 없어 차단이 얼마나 가는지 몰라, 쿨다운은 5분이고
  쿨다운 뒤 첫 명령은 첫 화면을 연 지 30분 안이면 남긴 쿠키로 요청 1건만 보내 풀렸는지 본다. 30분이 지났으면 첫 화면부터 다시
  연다 (아직 막혀 문서가 429 면 그 1건, API 만 막혀 있으면 첫 화면 요청 18~22건). 예전 쿨다운 15분은 첫 코드의 초깃값이고
  차단 길이를 잰 값이 아니다.
  2026-11-09 실측: 첫 화면을 새로 연 뒤 `search listings`·`listing` 을 쉬지 않고 10분 이어 불러(명령 102개, 요청 596건,
  1분 창 최대 60건) 429 가 한 번도 없었다. 첫 화면을 다시 여는 30분 주기와 차단 길이는 재지 못했다.
- 헤더 (2026-11-12 웹 화면 8개 요청 324건 실측과 번들): 웹은 front-api 를 모두 axios 인스턴스 하나로 불러 경로와 상관없이 같은
  헤더를 붙인다. 고정값은 axios 기본 `Accept: application/json, text/plain, */*` 와 본문이 있을 때의 `content-type` 뿐이고 jibsa
  와 같다 (`base_header`). 나머지 넷은 요청·페이지마다 바뀌어 넣지 않는다:
  - `x-page-url`: 보낸 순간의 주소창 주소 (`window.location.href`, 지도 상태가 다 들어 있다). 요청 인터셉터가 붙인다.
  - `x-attest`: 요청마다 다른 136자 서명 (11-09 에는 118자). 서버가 렌더링해 페이지에 넣은 토큰(페이지 로드마다 다름)을 시각·난수와
    함께 가려 만든다. 요청 인터셉터가 붙인다. 서버에는 헤더가 없을 때(`ABSENT`)를 포함한 상태값이 있고 지금은 없어도 200 이다.
    네이버가 진짜 웹에서 보낸 요청인지 보려는 값이라, 이 헤더를 요구하기 시작하면 네이버 명령이 모두 막힐 수 있다.
  - `sentry-trace`·`baggage`: Sentry 가 같은 출처 XHR 에 붙이는 추적 ID. 페이지 로드나 라우터 이동마다 새 값이다.
  사이트가 `window.fetch` 가 아니라 자기 API 클라이언트에서 `x-page-url`·`x-attest` 를 붙여 main world fetch 에도 붙지 않는다.
- 첫 화면의 front-api 요청을 막으면 쿠키가 `map_snb_collapsed` 하나만 생긴다. 이미지·지도 타일(`map.pstatic.net`)만 막는다.
- GitHub 러너 IP 는 브라우저로도 응답을 받지 못한다 ([매일 API 감시](../README.md#매일-api-감시)).

## 페이지네이션과 조건 처리

경계 검색·반경 검색·단지 검색·재개발 검색의 페이지 예산과 집계 범위는 서로 다르므로 해당 service 상수와 `PageScan`/`scan_pages`를 읽는다. 반환 개수와 서버 집계를 같은 값으로 취급하지 않는다. `--limit` 은 요청한 크기가 아니라 받은 개수로 센다. 검색 모드의 최대값은 `MAX_LIST_LIMIT`(120) 하나를 CLI 옵션과 상한 안내가 함께 쓴다.

매물 목록 항목은 대표 매물(`representativeArticleInfo`)과 중복 묶음(`duplicatedArticleInfo`: 같은 집을 올린 중개사 수, 거래별 호가 범위 `representativePriceInfo`, 묶인 매물 전부)이다. 묶인 매물 목록은 매우 커서 받지 않고 수와 범위만 `NaverListing` 의 `realtor_count`·`*_range_manwon` 으로 낸다. 서버 가격순은 이 범위로 정렬한다 (2026-10-31 실측: 헬리오시티 84㎡ 매매 가격높은순 첫 매물이 대표 30억, 범위 30억~33억, 다음이 32억들. 가격낮은순은 범위 최저 순). 대표 가격만 내던 때는 33억 호가가 보이지 않았다. 범위로 다시 정렬하지 않는다 (서버 정렬 그대로). 가격 조건도 대표 호가로만 걸린다 (같은 날 실측: 가격 30억~30억에는 그 묶음이 나오고 33억~33억은 0건). 범위 필드만 두자 에이전트가 가격 조건 0건을 믿어, `group_sort_notes` 가 끝 호가 값과 이 동작을 함께 알린다.

사각형 목록(`boundedArticles`·`boundedComplexes`)은 지도 줌(`precision`)이 높을수록 사각형을 다 주지 않고 중심 근처만 준다. 그래서 가까운순이 아닌 반경 검색과 `search complexes` 반경 검색은 반경에 맞춘 줌(`bounded_precision`: 1.5km 까지 16, 2km 까지 15, 3km 까지 14)을 보낸다. 모델 기본값 16 만 보내던 때는 반경 2km 부터 가장자리 매물이 빠져, 빠진 매물만 조건에 맞으면 '0건이 전부' 라고 냈다 (2026-10-31 강남역 2km 아파트 전세 5억 이하 + 500세대 이상: 가격낮은순 0건, 가까운순 6건). 세대수 조건 탓으로 보였지만 세대수만 걸면 줌 16 에서도 1,129건 중 673건으로 줄어 서버가 받는다. 줌별 실측 수는 `bounded_precision` 주석에 있다.

단지 매물(`complex/article/list`)의 `lastInfo` 는 다음 쪽이 있는 동안 리스트로 온다 (`[1, 점수, 매물 번호]`, 가격순·최신순은 가격·날짜가 하나 더. 헬리오시티 1,774건 랭킹·가격낮은·최신순 각 3쪽, 2026-10-10). 정수 커서를 막는 검사는 응답 형식이 바뀌었을 때를 위한 것이다. 마지막 쪽과 재개발 구역 매물(`redevelopmentArea/articleList`)도 리스트로만 온다 (개포자이 6쪽, 봉천4-1-3·봉천14구역 3개 정렬 12쪽, 2026-10-11). 그래서 재개발 매물에는 정수 커서 검사를 두지 않고, 단지 매물의 검사가 멈출 때 따로 안내하지 않는다 (실제로 오지 않는 경우라 코드를 늘리지 않음). 이 검사를 `scan_pages` 로 옮겨 모든 목록에 걸지 않는다: 지역·클러스터 매물(`NaverArticlePagingRequestModel`)은 커서가 리스트 또는 정수다.

필터는 request 모델의 서버 코드로 변환한다. 거래 유형·가격 조건 `NaverTradeConditions`(`common`, 단지·재개발 매물)를 지도 검색 조건
`NaverListingConditions`(`search`)가 이어받는다 ([공통 규칙](../provider-conventions.md#검색-조건-묶음)). 단지·재개발 목록은
`price_filter_of`, 지도 검색은 `listing_filter_of` 로 원 단위 필터를 만든다. 시설·주차의 AND와 나머지 다중 조건의 OR, 가격별 거래 유형 추론을 유지한다. 지역·정렬·동 전체·단지·재개발 매물은 모두 서버 필터 응답이라 [공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)대로 가격·유형을 다시 거르지 않는다 (`listing_keeper`. 2026-10-10 실측: 가격 조건 4종 지역 검색 118건, 단지 매물 38건 모두 조건 안). 받은 뒤 빼는 것은 중복·모르는 거래 유형 코드와, 사각형으로 받은 반경 검색의 반경 밖·좌표 모름뿐이다. 목록 응답에는 매물 상태·노출 여부 필드가 없어 거래 불가로 뺄 매물이 없다 (`EXCLUDED_REASON`. 2026-10-14 실측: 역삼동 동 전체 목록 20건). 네이버 매물은 거래 조건이 하나라 거래 조건 선택이 없다. 서버는 틀린 필터 키를 조용히 무시하므로 필터 키를 바꾸면 원본 응답이 조건 안인지 live로 확인한다. 단지·재개발 모드는 지역 검색의 모든 옵션을 지원하지 않으므로 CLI 분기의 검증을 먼저 확인한다. 부가 조회 실패로 정보가 `null`인 경우와 거래 불가를 구분한다.

## 위치 찾기 (웹 검색창)

`resolve_search_region` 이 `search listings`·`search complexes`·`search redevelopment`·`trend` 의 검색어를 위치로 바꾼다.
주소 검색(`maps-search/address`) → 동 자동완성(`search/autocomplete/legalDivisions`) → 역 자동완성
(`search/autocomplete/subwayStations`) → 단지 자동완성(`search/autocomplete/complexes`) 순으로 묻고 처음 맞는 종류를 쓴다
('역' 으로 끝나면 역을 먼저). 웹 검색창도 이 API 들로 후보를 섹션별로 보여 주고 사용자가 고른다. jibsa 는 각 종류에서 이름이
검색어와 같은 곳만 쓰고, 여럿이면 `REGION_AMBIGUOUS`(`_ambiguous`·`RegionAmbiguousError`, 후보는 앞 `MAX_CANDIDATES_SHOWN`
곳. 받은 후보 목록이 잘려 전체 수를 모르면 `candidate_count` 가 null), 넷 다 없으면 `REGION_NOT_FOUND` 로 멈춘다. 이름이 같지
않은 첫 후보를 고르지 않는다 (2026-11-13 웹 대조). 단지 명령(`complex`·`search listings --complex`·`market-price`·
`school --complex`)의 단지 이름은 `resolve_complex_number` 가 단지 자동완성만으로 같은 규칙을 따른다.

자동완성은 첫 쪽만 받고 같은 이름을 앞쪽에 모아 주지 않는다. 그래서 다음 쪽(`hasNextPage`)이 있으면 이름이 같은 동·역·단지가
한 곳뿐이어도 정하지 않고, 그 한 곳을 후보로 `candidate_count` null 인 `REGION_AMBIGUOUS` 로 멈춘다 (2026-11-13 실측: 단지
'삼익' 은 0쪽에 수서동 1곳·1쪽에 4곳, '우성' 은 0쪽 0곳·1쪽 2곳. 잠실엘스·래미안대치팰리스·헬리오시티 같은 흔한 구체 이름은
`hasNextPage` false 라 그대로 정한다). 후보 수는 `totalCount` 로 세지 않는다. `totalCount` 는 '중앙동1가' 같은 비슷한 이름도
세어 같은 이름의 수가 아니다 ('송정' 은 첫 쪽 다섯 곳이 모두 송정동이고 totalCount 14, 2026-10-11).

- 주소 검색은 동 이름 일부에 대표 한 곳만 준다 (`송정` → 부산 해운대구 송정동 1곳, `송정동` → 15곳. `역삼`·`역삼동` 은 둘 다
  1곳. `대치` 는 대치동·대치면 2곳, 2026-10-11). 그래서 `_find_address` 는 찾은 동 이름이 검색어와 다르면 동 이름 전체로 1회
  더 물어 여러 곳이면 멈춘다. 번지('신사동 535-1')나 이름 그대로('역삼동')는 다시 묻지 않는다.
- 주소 검색의 모호 후보는 법정동 코드(`addressElements.bcode`)가 있는 결과만이다 (`_unique_address`). 웹 검색창의 지역 후보가
  법정동만이라 행정동 결과(관악구 신사동, `hcode` 만 있음)는 빼고, 받은 목록이 다 왔는데 법정동이 한 곳만 남으면 그곳이다
  (`신사동` → 강남구·은평구, 2026-11-13 웹 대조). 법정동 결과가 없으면(행정동만 여러 곳) 그 행정동들을 후보로 준다. 목록은
  앞 10곳만 와서 전체 수가 더 많으면 `candidate_count` 가 null 이다. 잘린 목록에 법정동이 한 곳만 보여도 뒤쪽에 더 있을 수
  있어 정하지 않고 그 한 곳을 후보로 멈추며, `hint` 는 고르라는 말 대신 같은 이름이 더 있을 수 있으니 시·구를 붙이라고 한다
  (2026-11-13 사용자 결정).
- 행정동(역삼1동)·리(양근리)는 동 경계로 찾지 않고 주소 검색이 주는 대표 좌표에서 반경을 찾고 `[범위]` 안내를 붙인다. 행정동은
  법정동 코드가 비어 있어서다. 행정동이면 안내 끝에 원본의 `relatedRegionAddressList`(응답 모델에 없는 키,
  `[{'address': '역삼동', 'linkQuery': '서울특별시 강남구 역삼동'}]`)를 관련 법정동으로 붙인다 (`_related_legal_dongs`,
  2026-11-13 캡처). 웹 검색창은 이 값을 그리지 않는다. 주소 섹션은 `addressElements.jibun` 이 있는 결과만 보여 줘 행정동·리
  결과를 숨기고, 지역 섹션(legalDivisions 자동완성)에도 행정동·리가 없다 (2026-11-13 웹 대조: 역삼1동·양근리 → 단지 섹션만).
- 주소 검색이 못 찾은 이름(`신흥`)은 동 자동완성으로 넘어가며, 검색어 끝 단어에 동·구·시·군·읍·면을 붙인 이름
  (`DIVISION_NAME_SUFFIXES`)과 끝 단어가 같은 곳만 쓴다. 첫 결과로 고르면 `신흥` 이 인천 신흥동1가가 되고 같은 이름 신흥동
  여러 곳을 알리지 않았다 (2026-10-11). 그런 곳이 없으면 역·단지로 넘어간다. 여러 곳이면 이름 전체로 주소 검색을 1회 더 해
  `신흥동`·`신사동` 과 같은 후보로 멈춘다 (자동완성은 신흥 2곳·totalCount 12, 주소 검색 신흥동은 14곳. 신사 2곳 ↔ 신사동 3곳).
  자동완성은 한 쪽에 다섯 곳만 줘서 다음 쪽이 있으면 `candidate_count` 가 null 이다.
- 주소 검색은 `○가` 로 나뉜 동의 앞 이름('성수동')에도 한 곳(성수동1가)만 주고 2가는 알리지 않는다 (2026-10-15 실측). '동' 을
  뺀 '성수' 도 같아서 (2026-10-28 실측) `_ga_dong_base` 가 둘 다 앞 이름 '성수동' 의 `○가` 동으로 본다. 그러면 주소 결과의
  시·군·구(`addressElements.sigugun`)와 앞 이름('성동구 성수동')을 동 자동완성에 1회 더 물어 `○가` 동(성수동1가·성수동2가,
  2026-11-13 캡처)을 모으고, 둘 이상이면 고르지 않고 그 동들을 `서울특별시 성동구 성수동1가` 꼴의 후보로 주는
  `REGION_AMBIGUOUS` 로 멈춘다 (`_ga_dong_ambiguous`). 사용자 검색어로 물으면 자동완성이 정식 시·도 이름('서울특별시 성동구
  성수동')을 받지 않아 빈 목록이고 1가로 조용히 정했다 (2026-11-13 실측). `○가` 동을 한 곳 이하로 받으면 다른 `○가` 동이
  있는지 알 수 없어 그 한 곳(없으면 주소 결과)을 후보로 멈춘다. 주소 검색이 못 찾는 앞
  이름('부민')은 동 자동완성이 1가·2가·3가를 모두 주므로 (2026-10-30 실측) 같은 후보로 멈춘다. 동 매물 목록
  (`legalDivisionArticleList`)이 법정동 코드를 하나만 받고(둘이면 400, 2026-10-15 실측) 웹에도 두 동을 한 목록으로 보는 화면이
  없어, 합치지 않고 웹 검색창처럼 하나를 고르게 한다 (당근과 같다). `--radius` 를 줘도 같다.
- 역 자동완성은 역 이름·노선·좌표만 주고 시·구가 없다 (2026-11-13). 이름이 검색어(또는 검색어+'역')와 같은 역이 여럿이면
  (`신흥역` → 8호선 성남·대전 1호선) 이름으로 가를 수 없어 `{name, lines, lat, lng}` 후보와 `--lat/--lng` 로 다시 찾으라는
  `hint` 로 멈춘다. 이름이 같은 역이 없으면 받은 역을 비슷한 후보로 모아 두고 단지로 넘어간다.
- 단지 자동완성은 `size` 가 없으면 서버 기본 5곳이라 같은 이름 단지를 놓친다. 웹 검색창처럼 `size=10` 을 보낸다 (2026-11-13
  캡처). 단지 이름은 `_complex_key`(띄어쓰기·영문 대소문자만 무시)가 같은 곳이 한 곳일 때만 정한다 (`_same_name_complex`).
  여럿이면 `REGION_AMBIGUOUS` 로 `{name, legal_division, complex_number}` 후보를 준다 ('현대' → 보령·용인·관악, 2026-11-13).
  위치 검색이면 후보에 `lat`·`lng` 도 싣고 `--lat/--lng` 를, 단지 명령이면 `complex_number` 로 다시 부르라고 `hint` 를 준다.
  같은 이름이 없으면 단지 명령은 `NOT_FOUND`, 위치 검색은 `REGION_NOT_FOUND` 이고 이름이 비슷한 역·단지를 `candidates` 에
  싣는다. 위치 검색의 후보는 `REGION_AMBIGUOUS` 와 같은 객체(역 `_station_candidate`, 단지 `_complex_candidate`)라 `lat`·`lng`
  로 다시 찾는다. 다음 쪽이 있어 뒤쪽에 같은 이름이 있을 수 있으면 `message` 가 알리고, `hint` 는 `search complexes <동 이름>`
  으로 단지 번호를 찾으라고 한다 (단지 명령의 `NOT_FOUND` 도 같다).
- 법정동·단지 자동완성의 `legalDivisionName` 은 `서울시 강남구 역삼동`·`세종시 세종시 반곡동`·`강원도 원주시` 처럼 옛·줄인 시·도
  이름이라, 검색 중심 `region.address` 와 후보 이름에 넣을 때 `normalize_address` 로 매물 주소와 같은 정식 이름으로 바꾼다.
  주소 검색(`maps-search/address`)의 `fullAddress` 는 처음부터 `서울특별시 …` 다 (2026-10-11 실측).

## 원룸 구조 메모

(2026-10-10 실측)

- 상세 `detailInfo.shape` 는 원룸 구조 코드('10' 오픈형, '20' 분리형)이고 지도 필터 `oneRoomShapeTypes` 와 같다. 방이 여럿인 매물도 '20' 으로 오므로 `room_type` 은 방 수(`spaceInfo.roomCount`)를 먼저 보고, 방 1개일 때만 `spaceInfo.duplex`(복층)와 `shape` 로 정한다 (`_room_type`).
- `oneRoomShapeTypes` 는 `shape` 가 있는 매물만 건다. 단지 매물(아파트 A01·오피스텔 A02·단지형 빌라 A06·재건축 A04·분양권 B01 확인)은 `shape` 키가 없어 오픈형·분리형 어느 쪽이든 모두 빠진다 (역삼동 방 1개: 아파트 435건·오피스텔 2,074건 → 0건, 대치동 재건축 1,024건 → 0건). 원룸·빌라·상가주택 등도 중개사가 구조를 입력하지 않으면 `shape` 가 null 이라 빠진다 (역삼동 원룸 전세 35건 → 26건, 상가주택 73건 → 11건). `shape` 가 있는 매물은 필터와 상세가 일치한다. 서버 필터라 다시 거르지 않고, 구조 조건을 주면 유형과 무관하게 `ONE_ROOM_SHAPE_NOTE` 로 알린다.

## 재개발·추이 엔드포인트 메모

(2026-10-10 실측)

- 재개발 구역 목록·매물 목록은 페이지 30건까지다 (31부터 400). 목록 응답에 좌표가 없어 반경 검색은 `redevelopmentArea/markers`(페이지 없음)로 위치를 받아 반경 밖을 뺀다.
- 구역 목록·마커의 지도 줌(`precision`)이 결과를 바꾼다. 12 이하는 400, 줌이 높을수록 중심 근처만 준다. `REDEVELOPMENT_PRECISION = 14` 는 반경 1·3km 안 구역을 13 과 같이 모두 주면서 반경 밖은 덜 섞인다 (15 는 3km 에서 빠짐).
- 동 경계는 `redevelopmentArea/legalDivisionList` (EUP 코드 하나). 네이버는 한 구역을 법정동마다 따로 등록하기도 해 이름이 같은 구역이 번호를 달리해 여러 번 온다.
- 구역 목록(반경·동 경계 모두)은 `filter.tradeTypes` 로 구역을 거르지 않는다. `hasArticle: true` 를 함께 보내도 같고, 매물수순 정렬 순서만 바뀐다 (한강진역 1.5km 7곳: 단기임대만·매매만·기본 필터 모두 같은 구역, 매매만 주어도 매매 0건 구역이 옴). `articleCountInfoDto` 도 필터와 상관없이 네 거래를 모두 세서 상세(`redevelopment`)의 수와 같다 (한남4 매매 43 = 43). 그래서 `--trade` 는 받은 뒤 `article_counts` 로 거르고 `notes` 로 알린다 ([서버 필터와 클라이언트 후처리](../provider-conventions.md#서버-필터와-클라이언트-후처리)의 "서버가 받지 않는 조건"). 7곳 모두 `articleCountInfoDto` 가 있었고, 단지 목록도 매물 없는 빌라 단지까지 0 으로 채워 준다 (역삼동 빌라 `--include-empty` 60곳, 매물 0건 36곳 포함). 없으면 `article_counts` 는 `null`(모름)이다. 실서버로는 재현할 수 없어 fixture 에서 이 키를 지워 확인했다 (2026-10-10 실측).
- 재개발(F01) 매물은 목록에서 전용면적을 0, 해당 층·전체 층을 `'0'` 으로 주고, 상세에서는 전용면적 키 없이 층·전체 층을 `'-'` 로 준다. `article_info_to_listing`·`known_floor` 가 목록·상세 모두 모름(null)으로 바꾼다.
- `legalDivision/*Weekly*` 추이는 아파트(A01)만 값이 있다. 오피스텔·빌라 코드도 받지만 모두 0, 월세는 400. 구 단위 코드도, 시·도 코드도 받는다 (서울 1100000000 세 엔드포인트 200). 평당가는 원 단위. 셋 중 하나가 실패하면 그 값만 `null` 이고 429 는 `RateLimitedError` 라 삼키지 않는다.
- 단지 학교 `education/complex/school` 은 단지형 빌라를 `itemType=villa` 로 물어야 한다 (complex 로 물으면 빈 목록).
- `complex/redevelopment` 는 없는 구역 번호에도 `isSuccess: true, result: {}` 를 준다. 이름이 비면 NOT_FOUND 로 바꾼다. `redevelopmentArea/articleStats` 는 단지 매물 통계와 같은 모양이고 `tradeTypes[]`·가격 키를 서버가 거른다.
- `complex/reconstruction` 은 재건축(A04) 단지용이다. 단계 코드 01~11 은 사이트 `COMPLEX_RECONSTRUCTION_STEP` 라벨로 바꾸고, 날짜 없는 단계(아직 안 거친 단계)는 내보내지 않는다.

## 기간 조회·지역 목록·학교 엔드포인트 메모

(2026-10-10 실측)

- `complex/pyeong/realPrice/list` 는 `startDate`~`endDate` 거래를 페이지 없이 다 준다 (대단지 전세 5년 833건 한 번에). `realEstateType`·`endDate` 가 빠지면 400 이지만 유형 값은 결과에 영향이 없어 A01 을 보낸다. 빌라 단지는 거래가 있어도 빈 목록이라 `complex/villa/realPricePage`(size 100 가능, 최근 순)를 시작일까지 넘긴다.
- `complex/marketPrice/list` 는 유형 코드 없이도 같은 값을 준다. 기관마다 기준일을 키로 한 dict 들이 온다 (1년이면 기관당 51~52점).
- `legalDivision/subInfoList` 의 `legalDivisionLevelType` 은 하위 목록을 볼 지역의 단위다 (시·도 코드 + SI, 구 코드 + GUN). GU 는 400. 시·도의 하위 목록은 구가 있는 시를 `성남시 분당구` 처럼 펼쳐 주고, `성남시` 자신의 코드(4113000000)로는 빈 목록이다. 시·도 목록(`infoListByLevel`, SI)은 16곳이다 (전남광주통합특별시 포함). 세종의 시·도 하위 목록은 `세종시`(3611000000) 하나뿐이고 `세종시` 가 시·도 별칭이라, `regions` 는 하위가 시·군·구 하나뿐이면 그 아래 읍·면·동(GUN)을 준다. 그러지 않으면 `regions 세종시` 가 같은 목록을 되풀이했다. 하위 목록의 리(LI)는 웹 지역 선택처럼 빼고 읍·면·동(EUP)까지만 준다 (`_region_entries`). 리는 좌표도 0,0 으로 와 위치로 쓸 수 없다 (2026-11-13 웹 대조: 세종 하위 150곳 중 117곳이 리).
- 동 경계 목록(`article/legalDivisionArticleList`·`complex/legalDivisionComplexList`)의 `filter.legalDivisionType` 은 EUP(동·읍·면)·GUN(시·군·구)이 200, GU·SI 는 400 이다 (2026-11-13 실측). jibsa 는 EUP 만 보낸다. 요청 모델(`NaverArticleFilterModel.legal_division_type`)의 Literal 은 `EUP`·`GUN`·`SI` 다.
- 법정동 자동완성은 시·도를 주지 않고 한 쪽에 다섯 곳만 준다. 그래서 `regions` 는 시·도 목록을 먼저 받아 이름(서울·서울시·서울특별시·충북 등)을 맞춰 본다. `regions` 는 같은 이름이 여러 곳이면 `REGION_AMBIGUOUS` 이고 다음 쪽이 있으면 `candidate_count` 가 null 이다 (`송정동` 은 첫 쪽 5곳에 hasNextPage true·totalCount 14, 2026-11-13). 첫 쪽에 이름이 같은 곳이 한 곳뿐이면 다음 쪽이 있어도 그곳으로 본다. 위치 검색처럼 멈추면 `강남구` 처럼 그 안의 동이 함께 와 다음 쪽이 있는 평소 이름까지 막힐 수 있어서다 (2026-11-13 사용자 결정).
- 법정동 자동완성은 네이버식 시·도 이름으로만 찾는다. `서울특별시 강남구`·`부산광역시 중구` 는 빈 목록이고, `서울 강남구` 는 `서울시 강남구` 를 준다. 그래서 `regions` 는 첫 단어가 시·도면 시·도 목록의 `legalDivisionName`(`서울시`)으로 바꿔 묻는다 (2026-10-10 실측). 시·도 이름은 매물 주소와 같은 `SIDO_OFFICIAL_NAMES` 로 `cityFullName` 에 맞춘다 (옛 이름 `광주`·`전남`, 네이버 줄임 이름 `전남광주시`·`전북도` 포함). 옛 이름 그대로인 `광주 광산구` 는 자동완성이 빈 목록이라 `전남광주시 광산구` 로 바꿔 묻는다 (2026-10-11). 한 단어 `광주시` 만 경기도 광주시로 본다 (`core/listing.py` 의 `CITY_NAMES_NOT_SIDO`, 세 소스 공통).
- `education/school` 은 학교 코드로 공시 정보를 준다 (전화·홈페이지·좌표·학구도 경계는 내보내지 않는다). `education/complex/school/allocation-dongs` 는 단지·학교·itemType 으로 배정 동 묶음(`convertedBuildingNameGroups`)을 주고, 사이트처럼 묶음의 첫~끝 동으로 보여 준다. 없는 단지 번호(99999999)와 이 학교에 배정되지 않은 단지(헬리오시티 111515 ↔ B100000747)도 일부 배정처럼 `isAllBuildingAssigned: false, convertedBuildingNameGroups: []` 로 와서 구분되지 않는다. 없는 단지 번호는 `complex`·`complex/villa` 모두 `result: null` 이라, 번호로 받은 빌라 단지는 `complex/villa` 로 있는지 먼저 확인한다 (2026-10-11 실측).
- `article/tax` 는 면제되는 항목도 null 이 아니라 0 으로 준다 (85㎡ 이하 취득 농특세, 종부세 대상 아님. 헬리오시티 39·85·111·150㎡·일신동 빌라 2건, 2026-10-11 실측). 그래서 세금 합계(`_sum_manwon`)에서 일부 항목만 null 인 경우는 실제 응답에 없다. 세금 묶음(`acquisitionTax`·`propertyTax`·`totalRealEstateTax`)이 통째로 null 인 응답은 있다. 재산세·종부세 묶음이 null 이면 오피스텔·상가 매매처럼 웹도 그 칸을 보여 주지 않는 것이라 해당 없음으로 키를 뺀다 (`not_applicable_costs`, 2026-11-13 웹 대조). 취득세 묶음이 null 인 매물은 찾지 못해(매매 4건 모두 값이 있었다, 2026-11-13) 해당 없음인지 알 수 없으므로 키를 남겨 null(모름)로 두고 `UNKNOWN_ACQUISITION_TAX_NOTE` 로 네이버 매물 화면에서 확인하라고 알린다 (2026-11-13 사용자 결정). 조회가 실패한 값도 그대로 null(모름)이다.
- `article/agentFee` 의 `isIndividualCheckRequired` 가 true 면 웹은 금액 대신 '개별확인' 을 보여 준다. 그래서 `agent_fee_manwon` 을 null 로 두고 `INDIVIDUAL_AGENT_FEE_NOTE` 를 `listing` 의 `notes` 로 낸다 (2026-11-13 웹 대조).
- `article/maintenanceFee` 의 미확인(typeCode '03')은 `uncheckDetail.type` 이 '99' 면 웹이 '없음' 으로 보여 주는 관리비 없는 매물이라 0만원·[] 이고, 그 밖의 값은 웹 '확인 어려움' 이라 모름(null)이다 (`_manage_cost`, 웹 번들 2026-11-13. 실매물 표본에는 '99' 가 없어 픽스처로만 확인했다).
- 입주 시기(`movingInType`)는 웹 번들 `ARTICLE_MOVING_IN_TYPE` 과 같다: MV001 즉시입주, MV002 날짜 이내, MV003 날짜 이후, MV004 지정 날짜, EARLY·MID·LATE 는 그 달 초·중·하순 (2026-11-13). MV002·MV003 은 날짜만 내면 뜻이 반대로 읽혀 `이내`·`이후` 를 붙인다 (`MOVING_IN_DATE_SUFFIXES`).
- `legalDivision/infoList` 는 법정동 코드(키에 `[]` 를 붙여 반복: `legalDivisionNumbers[]=1171010700`)를 이름으로 풀어 코드를 키로 하는 객체로 준다. 웹 매물 화면이 '위치' 를 만들 때 부르는 API 라 `listing` 의 주소도 `article/key` 의 법정동 코드로 이것을 불러 만든다 (`_jibun_address`). `regionName`(`fullAddress` 와 같은 값)은 시·도가 줄인 이름(`서울시 송파구 가락동`)이라 `normalize_address` 로 정식 이름으로 바꾼다. 읍·면 매물은 `article/key` 가 리 코드가 아니라 읍·면 코드와 리 이름(`address.li`)을 따로 줘서 리를 동 이름 뒤에 붙인다 (양평읍 전원주택 3건). 리 코드를 물으면 읍·면이 빠진다 (4183025021 → `경기도 양평군 양근리`, 2026-11-13). 좌표 역조회(`legalDivision/searchByCoordinate`)는 `trend` 가 위치의 법정동을 찾는 데 쓴다.
- 실거래(`complex/v2/pyeong/realPrice`·`complex/pyeong/realPrice/list`)의 `propertyType` 은 NORMAL 일반, PRESALE 분양권, OCCUPANCY_RIGHT 입주권이다. 웹 번들 표 그대로 이름을 붙이고(`REAL_PRICE_PROPERTY_TYPE_LABELS`) NORMAL 은 키를 빼며, 모르는 코드는 코드 그대로 둔다. 빌라 실거래(`complex/villa/realPricePage`)에는 이 키가 없다 (2026-11-13. 올림픽파크포레온 155817 평형 9 매매 3년 200건 중 153건이 입주권).
- 재검토 후 넣지 않은 엔드포인트: `complex/asking-price`(단지 매물 목록과 같은 정보), `article/boundedArticlesCount`(검색의 `total_count` 와 같음), `search/articles`(`listing` 과 같고 중개사·본문이 섞임), `complex/villa/asking-price`(빈 결과), `complex/villa/realPriceAround`(파라미터를 찾지 못해 400).

## API 변경 시 점검

client의 action별 endpoint/docstring → request 별칭·필터 → response 봉투와 중첩 모델 → service unwrap·만원 변환 → CLI 모드별 검증 순으로 확인한다. 학교·교통·세금·선택 평형 시세는 부가 요청 경로도 따로 확인한다. 재개발은 구역 목록과 매물 목록, trend는 호가와 실거래 건수를 구분한다.

## 웹과 다른 점

[웹 화면과의 대응](../provider-conventions.md#웹-화면과의-대응) 원칙 안에서 네이버 웹(fin.land.naver.com)과 다르게 한 곳을 모은다. 2026-11-13 웹 요청 캡처·번들 대조이고, 여기 적지 않은 명령·필드는 웹과 같은 API·파라미터로 확인했다. 항목마다 무엇이 다르고 왜 사실이 어긋나지 않는지만 적는다.

- **검색 기본값.** `search listings` 의 거래 유형 기본은 매매·전세·월세·단기임대(A1·B1·B2·B3) 전부이고 매물 유형 기본은 주거 유형 전부(아파트·오피스텔·빌라·원룸·단독·다가구·전원주택·상가주택)다. 웹 지도 기본(`DEFAULT_MAP_FILTER`)은 매매·전세에 아파트·재건축·분양권(A01·A04·B01)이다. 둘 다 웹 필터 단추(거래 단추 넷, `MAIN_PROPERTY_TYPES`·`SUB_PROPERTY_TYPES`)로 고를 수 있는 조합이라 나온 매물은 웹에서 그 단추를 누르면 나오는 매물이다. 집을 찾는 CLI 라 기본값 때문에 빠지는 매물이 없게 넓혔다. 면적 기준 기본은 전용(`filtersExclusiveSpace: true`)이고 웹 기본은 공급이다. 결과 `area_m2` 가 전용면적이라 필터와 출력의 기준을 맞췄고, 서버가 받는 같은 필터 키다. `search complexes` 기본은 아파트(A01)만·거래 넷·매물 있는 단지만(`hasArticle: true`)이고 웹 단지 목록 기본은 A01·A04·B01·매매·전세·전체 단지다 (대치동 웹 79곳 ↔ jibsa 61곳). 매물을 찾는 CLI 라 매물 있는 단지를 보이고 `--include-empty`·`-t` 로 넓힌다 (재건축·분양권 단지는 아직 고를 수 없다). `trend` 기본 기간은 1년이고 웹은 5년(`P-5Y`)이다. 주별 점이 세 묶음에 260여 개씩이면 에이전트가 읽기에 많아 줄였고, `--period 5년` 이면 웹과 같다. `search redevelopment` 정렬 기본은 웹 구역 목록과 같은 세대수순(`DEFAULT_REDEVELOPMENT_LIST_SORT_TYPE`)이다.
- **한 번에 더 받기, 탭을 한 번에.** 매물·단지·구역 목록은 `--limit`(최대 `MAX_LIST_LIMIT`)까지 30건씩 이어 받고 `--next` 로 이어 간다. 웹 무한 스크롤도 같은 커서(`withSeed`·`seed`·`lastInfo`)로 다음 쪽을 받는다. `real-price` 는 10건씩 최대 10쪽(`--pages`)이다. 웹 단지 상세 실거래도 같은 API·같은 계약일 내림차순으로 100건까지 스크롤한다. `market-price` 는 기관 세 곳을 한 번에 준다 (웹은 기관 하나씩). 시작일은 웹 시세 탭 차트와 같은 `subYears` 다 (흐름 차트의 월초 시작일과는 다르다). `complex --pyeong` 은 매매·전세 실거래 요약을 한 번에 준다 (웹은 탭마다). 같은 API 를 더 받거나 탭을 합친 것이라 거래·시세 한 건 한 건은 웹과 같다.
- **웹이 그리기만 하는 값을 표로.** 3년 실거래 요약의 `average_manwon` 은 같은 응답의 `avgPrice` 다 (웹 3년 칸은 최고·최저만 보여 준다). `real-price --period` 는 웹 실거래 차트가 쓰는 기간 목록(`complex/pyeong/realPrice/list`)을 거래 표로 준다. 웹이 받는 응답의 값 그대로다.
- **웹 UI 에 없지만 서버가 받는 조합.** `complex --dong` 과 여러 `--pyeong` 의 매물 통계는 `complex/article/stats` 에 `buildingNumbers[]`·`pyeongTypes[]` 를 보낸다 (비로그인 웹은 평형 하나만 고른다). `trend` 는 동·읍·면과 좌표 자리의 법정동도 받는다 (웹 추이 화면은 전국·시·도·시·군·구만). `-t` 의 건물·상가건물·숙박·기타는 웹 '건물' 단추 하나(D03·D04·E01·Z00)를 나눈 것이고, 한옥(C06)·고시원(G01)은 웹 지도 필터에 없는 코드다. `redevelopment --trade` 는 웹 지도 구역 팝업과 같은 `articleStats` 에 `tradeTypes` 를 더 보낸다. 모두 서버가 거른 결과를 그대로 주는 것이라 나온 매물·수는 네이버가 준 값이고 매물은 웹 매물 화면에서 그대로 열린다.
- **받은 결과의 부분집합.** 반경 검색은 반경을 감싼 정사각형을 반경에 맞춘 줌(`bounded_precision`: 1.5km 까지 16, 2km 까지 15, 3km 까지 14)으로 받아 반경 밖을 빼고 `notes` 로 알린다. 웹 지도 옆 목록은 보이는 화면 범위와 그 줌이다. 같은 정렬 목록(`boundedArticles`)에서 반경 밖만 뺀 것이라 순서는 웹 목록 그대로다. 재개발 반경 검색도 줌 14 사각형으로 받아 마커 좌표(`redevelopmentArea/markers`)로 반경 밖을 뺀다. `search redevelopment --trade` 는 서버가 구역을 거래 유형으로 거르지 않아 받은 뒤 `article_counts` 로 그 거래 매물이 없는 구역을 빼고 `notes` 로 알린다 (웹은 거래 유형을 골라도 매물 0건 구역을 보여 준다). 빌라 `real-price --period` 는 웹 빌라 화면에 기간 보기가 없어 `complex/villa/realPricePage` 를 시작일까지 넘기고 그 앞 거래를 자른다. 모두 웹이 같은 API 로 주는 목록의 일부라 매물·구역·거래는 웹에도 있다 ([재개발·추이 엔드포인트 메모](#재개발추이-엔드포인트-메모), [기간 조회·지역 목록·학교 엔드포인트 메모](#기간-조회지역-목록학교-엔드포인트-메모)).
- **`--sort 가까운순`.** 웹 매물 목록의 정렬은 랭킹순·가격·최신·면적뿐이고 거리순이 없다. jibsa 는 반경 검색 기본을 웹 지도 옆 목록과 같은 랭킹순으로 두고, `--sort 가까운순` 을 줄 때만 지도 칸(`articleClusters`, 약 240m)을 가까운 칸부터 열어 칸 매물(`clusteredArticles`)을 거리로 세운다. 매물은 웹 지도 칸에 있는 실제 매물이고 순서만 jibsa 가 세운 근사라, 줄 때마다 `[참고]` `notes`(`NEAREST_SORT_NOTE`)로 웹에 없는 근사 순서이고 요청이 많이 든다고 알린다 ([되는 것](../provider-conventions.md#되는-것), 2026-11-13 사용자 결정). 반경 안 매물이 `--limit` 보다 적으면 반경을 덮어 받은 칸의 반경 밖 매물도 가까운 순으로 잇고 `notes`(`beyond_radius_notes`)로 알린다. 그 매물도 웹 지도 칸에 있는 실제 매물이고 거리(`distance_km`)를 그대로 보인다. 기본 랭킹순은 반경 밖을 뺀다.
- **방 구조·관리비 포함 항목.** `listing` 의 `room_type` 투룸·쓰리룸·포룸이상은 방 수(`spaceInfo.roomCount`)로 나눈 분류라 웹에 없는 이름이다. 방 1개의 복층·오픈형·분리형은 웹 값(`duplex`·`shape`) 그대로다 ([원룸 구조 메모](#원룸-구조-메모)). `manage_cost_includes` 는 항목별 관리비에서 정액 항목만 모은 목록이다 (웹은 항목마다 정액·실비를 보여 준다). 같은 응답의 값을 묶어 이름만 붙인 것이라 방 수·금액은 웹과 같다.
- **계산·표기.** 같은 값을 자릿수·표기만 달리한다. 세금 합계는 원을 만원으로 바꿔 0.1만원까지 준다 (웹은 `Math.round(합/1만)*1만` 으로 "약 N만원"). `trend` 증감률 `change_rate_pct` 는 서버값 소수 둘째 자리다. 웹은 같은 식 `floor((마지막 주 - 첫 주) / 첫 주 * 1000) / 10` 을 소수 첫째 자리에서 버린다 (강남구 1년 69.79 ↔ 69.7). 평당가는 0.1만원까지 주고 웹은 만원 아래를 버린다. 용적률·건폐율은 원값이고 웹은 `Math.floor` 다. 주소의 시·도는 정식 이름(`서울특별시`)이다. 웹 매물 화면 '위치' 는 같은 `legalDivision/infoList` 의 `regionName`(`서울시`)을 쓰는데, 다른 명령·소스의 주소와 맞추려 `normalize_address` 로 바꾼다. 오피스텔은 네이버가 주는 공급면적 값이 계약면적과 같아 `supply_area_m2` 를 null 로 두고 `contract_area_m2` 로 준다. 단지 매물 목록은 `size=min(30, --limit)` 을 보낸다 (웹은 늘 30, 같은 정렬 목록의 앞부분이다). 랭킹순은 요청마다 서버가 seed 를 새로 정해 순서가 조금 다를 수 있다. 웹도 목록을 열 때마다 같다.
- **전월세 중개보수를 부르지 않는다.** 웹은 전월세 매물에도 중개보수(`agentFee`)를 보여 주지만 jibsa 는 요청을 아끼려 매매만 부르고 전월세 `listing` 에는 `agent_fee_manwon` 키가 없다. 웹에 있는데 jibsa 에 없는 값일 뿐 다른 값을 내지 않는다. 1회 더 불러 넣을 후보다.
- **위치 해석.** 행정동·리는 주소 검색 대표 좌표의 반경으로 찾는다. 웹 검색창에는 행정동·리 지역 항목이 없고 번지 없는 주소 결과를 숨긴다 (`!!addressElements.jibun`, 2026-11-13 웹 대조). 찾은 매물은 그 좌표 주변의 실제 매물이고 `[범위]` 로 알린다. 행정동 안내의 관련 법정동은 같은 주소 검색 응답의 `relatedRegionAddressList` 로, 웹은 그리지 않는 값을 `[범위]` 알림에만 쓴다. 단지 이름은 띄어쓰기·대소문자를 빼고 이름이 정확히 같은 단지가 한 곳이면 그 단지로 정한다 (웹은 늘 사용자가 자동완성 목록에서 고른다). 같은 이름이 둘 이상이거나 없으면 고르지 않는다. jibsa 는 주소 → 동 → 역 → 단지 순서로 처음 맞는 종류를 쓰고 ('역삼' 은 역삼동, '잠실' 은 잠실동이고 역삼역·잠실역은 알리지 않는다. 리뷰에서 역을 놓친다고 지적됐지만 웹 검색창도 주소·지역 섹션을 지하철보다 먼저 보여 주고, 역은 '역' 을 붙이면 먼저 찾아 고치지 않았다, 2026-11-13), 웹은 같은 검색을 섹션 순서(주소 → 지역 → 지하철 → 분양 → 재개발 → 단지)로 보여 주기만 한다. 고른 종류 안에서는 이름이 같은 한 곳만 쓰므로 웹에서 그 섹션의 그 항목을 누른 것과 같은 위치다. 단지 이름을 위치로 주면 그 단지 좌표 주변 반경을 찾는다 (웹은 단지 상세로 간다. 단지 안 매물만은 `--complex`). 자세한 규칙은 [위치 찾기](#위치-찾기-웹-검색창).
