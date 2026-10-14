# 네이버 개발 가이드

[CLI 사용법](../../docs/naver.md) · [개발 환경·검증](../development.md) · [공통 아키텍처](../architecture.md) · [provider 작성 규약](../provider-conventions.md) · [출력 계약](../output-contract.md) · [코드 형식](../code-style.md)

공통 규약에 없는, 네이버에만 있는 구현과 예외를 적는다.

## 명령과 요청 흐름

| CLI 명령 | 주요 경로 | service 모듈 |
| --- | --- | --- |
| `search listings` | 지역 해석 → 경계 또는 지도 범위 → 매물 목록 | `search` |
| `search complexes` | 지역 해석 → 단지 목록·마커 | `search` |
| `complex` | 이름/번호 해석 → 기본 정보·통계·평형·학교, 재건축 단지면 사업 단계, 선택 평형 부가 정보 | `complex` |
| `search listings --complex` | 단지 해석 → 동·평형 검증 → 단지 매물 페이지 | `listing` |
| `listing` | 매물 기본 정보 → 교통·학교, 매매 비용 부가 조회 | `listing` |
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
 429 는 봇 차단이라 일반 재시도 대상이 아니다. `should_retry_naver`는 5xx·timeout·transport만 재시도한다.

빌라 단지(A05·A06·A07)인지는 명령 맨 앞에서 한 번에 정하지 않고, 아파트 쪽 응답이 비었을 때 그 자리에서 정한다 (`villa_by_complex_response` docstring). 맨 앞에서 정하면 단지 종류를 모를 때마다(대부분 아파트) 요청이 1회 늘기 때문이다. 판별이 여러 곳에 흩어진 것은 이 때문이며, 한 번 빌라로 정해지면 빌라 엔드포인트의 실패 응답은 0건이 아니라 에러로 낸다. 빌라 단지에 거래·동이 없을 때 빌라 엔드포인트는 실패가 아니라 빈 목록을 주고(서진빌라 724112 월세 실거래 0건), 아파트 동 목록(`complex/buildingList`)도 빌라 단지에 `result=null` 이 아니라 빈 목록을 준다 (2026-10-10 실측).

응답 값을 요청 모델(Literal·pattern)에 다시 넣을 때는 먼저 아는 값인지 확인한다. 요청 모델 검증 실패는 `handle_errors` 가 사용자 입력 오류(`INVALID_ARGUMENT`)로 내기 때문이다. 매물 상세는 모르는 매물 유형을 `KNOWN_REAL_ESTATE_TYPES` 로 걸러 볼 수 없는 매물로 내고, 반경 검색은 클러스터 ID 형식이 다르면 `PARSE_ERROR` 로 바꾼다.

service 가 부르지 않는 엔드포인트 3개(`article/agent`, `complex/holdingTax`, `complex/declaredValue/pyeongType`)는 라이브러리용으로 client 메서드만 있다 (`article/agent` 는 중개사 정보라 출력하지 않는다는 원칙에 따라 쓰지 않는다). 모델은 [기준 7](../provider-conventions.md#service-모듈을-나누는-기준)대로 경로가 같은 기능 모듈에 둔다 (`article/agent` → `listing`, 나머지 둘 → `complex`).

## 페이지네이션과 조건 처리

경계 검색·반경 검색·단지 검색·재개발 검색의 페이지 예산과 집계 범위는 서로 다르므로 해당 service 상수와 `PageScan`/`scan_pages`를 읽는다. 반환 개수와 서버 집계를 같은 값으로 취급하지 않는다. `--limit` 은 요청한 크기가 아니라 받은 개수로 센다. 검색 모드의 최대값은 `MAX_LIST_LIMIT`(120) 하나를 CLI 옵션과 상한 안내가 함께 쓴다.

단지 매물(`complex/article/list`)의 `lastInfo` 는 다음 쪽이 있는 동안 리스트로 온다 (`[1, 점수, 매물 번호]`, 가격순·최신순은 가격·날짜가 하나 더. 헬리오시티 1,774건 랭킹·가격낮은·최신순 각 3쪽, 2026-10-10). 정수 커서를 막는 검사는 응답 형식이 바뀌었을 때를 위한 것이다. 마지막 쪽과 재개발 구역 매물(`redevelopmentArea/articleList`)도 리스트로만 온다 (개포자이 6쪽, 봉천4-1-3·봉천14구역 3개 정렬 12쪽, 2026-10-11). 그래서 재개발 매물에는 정수 커서 검사를 두지 않고, 단지 매물의 검사가 멈출 때 따로 안내하지 않는다 (실제로 오지 않는 경우라 코드를 늘리지 않음). 이 검사를 `scan_pages` 로 옮겨 모든 목록에 걸지 않는다: 지역·클러스터 매물(`NaverArticlePagingRequestModel`)은 커서가 리스트 또는 정수다.

필터는 request 모델의 서버 코드로 변환한다. 거래 유형·가격 조건 `NaverTradeConditions`(`common`, 단지·재개발 매물)를 지도 검색 조건
`NaverListingConditions`(`search`)가 이어받는다 ([공통 규칙](../provider-conventions.md#검색-조건-묶음)). 단지·재개발 목록은
`price_filter_of`, 지도 검색은 `listing_filter_of` 로 원 단위 필터를 만든다. 시설·주차의 AND와 나머지 다중 조건의 OR, 가격별 거래 유형 추론을 유지한다. 지역·정렬·동 전체·단지·재개발 매물은 모두 서버 필터 응답이라 [공통 기준](../provider-conventions.md#서버-필터와-클라이언트-후처리)대로 가격·유형을 다시 거르지 않는다 (`listing_keeper`. 2026-10-10 실측: 가격 조건 4종 지역 검색 118건, 단지 매물 38건 모두 조건 안). 받은 뒤 빼는 것은 중복·모르는 거래 유형 코드와, 사각형으로 받은 반경 검색의 반경 밖·좌표 모름뿐이다. 목록 응답에는 매물 상태·노출 여부 필드가 없어 거래 불가로 뺄 매물이 없다 (`EXCLUDED_REASON`. 2026-10-14 실측: 역삼동 동 전체 목록 20건). 네이버 매물은 거래 조건이 하나라 거래 조건 선택이 없다. 서버는 틀린 필터 키를 조용히 무시하므로 필터 키를 바꾸면 원본 응답이 조건 안인지 live로 확인한다. 단지·재개발 모드는 지역 검색의 모든 옵션을 지원하지 않으므로 CLI 분기의 검증을 먼저 확인한다. 부가 조회 실패로 정보가 `null`인 경우와 거래 불가를 구분한다.

## 원룸 구조 메모 (2026-10-10 실측)

- 상세 `detailInfo.shape` 는 원룸 구조 코드('10' 오픈형, '20' 분리형)이고 지도 필터 `oneRoomShapeTypes` 와 같다. 방이 여럿인 매물도 '20' 으로 오므로 `room_type` 은 방 수(`spaceInfo.roomCount`)를 먼저 보고, 방 1개일 때만 `spaceInfo.duplex`(복층)와 `shape` 로 정한다 (`_room_type`).
- `oneRoomShapeTypes` 는 `shape` 가 있는 매물만 건다. 단지 매물(아파트 A01·오피스텔 A02·단지형 빌라 A06·재건축 A04·분양권 B01 확인)은 `shape` 키가 없어 오픈형·분리형 어느 쪽이든 모두 빠진다 (역삼동 방 1개: 아파트 435건·오피스텔 2,074건 → 0건, 대치동 재건축 1,024건 → 0건). 원룸·빌라·상가주택 등도 중개사가 구조를 입력하지 않으면 `shape` 가 null 이라 빠진다 (역삼동 원룸 전세 35건 → 26건, 상가주택 73건 → 11건). `shape` 가 있는 매물은 필터와 상세가 일치한다. 서버 필터라 다시 거르지 않고, 구조 조건을 주면 유형과 무관하게 `ONE_ROOM_SHAPE_NOTE` 로 알린다.

## 재개발·추이 엔드포인트 메모 (2026-10-10 실측)

- 재개발 구역 목록·매물 목록은 페이지 30건까지다 (31부터 400). 목록 응답에 좌표가 없어 반경 검색은 `redevelopmentArea/markers`(페이지 없음)로 위치를 받아 반경 밖을 뺀다.
- 구역 목록·마커의 지도 줌(`precision`)이 결과를 바꾼다. 12 이하는 400, 줌이 높을수록 중심 근처만 준다. `REDEVELOPMENT_PRECISION = 14` 는 반경 1·3km 안 구역을 13 과 같이 모두 주면서 반경 밖은 덜 섞인다 (15 는 3km 에서 빠짐).
- 동 경계는 `redevelopmentArea/legalDivisionList` (EUP 코드 하나). 네이버는 한 구역을 법정동마다 따로 등록하기도 해 이름이 같은 구역이 번호를 달리해 여러 번 온다.
- 구역 목록(반경·동 경계 모두)은 `filter.tradeTypes` 로 구역을 거르지 않는다. `hasArticle: true` 를 함께 보내도 같고, 매물수순 정렬 순서만 바뀐다 (한강진역 1.5km 7곳: 단기임대만·매매만·기본 필터 모두 같은 구역, 매매만 주어도 매매 0건 구역이 옴). `articleCountInfoDto` 도 필터와 상관없이 네 거래를 모두 세서 상세(`redevelopment`)의 수와 같다 (한남4 매매 43 = 43). 그래서 `--trade` 는 받은 뒤 `article_counts` 로 거르고 `notes` 로 알린다 ([서버 필터와 클라이언트 후처리](../provider-conventions.md#서버-필터와-클라이언트-후처리)의 "서버가 받지 않는 조건"). 7곳 모두 `articleCountInfoDto` 가 있었고, 단지 목록도 매물 없는 빌라 단지까지 0 으로 채워 준다 (역삼동 빌라 `--include-empty` 60곳, 매물 0건 36곳 포함). 없으면 `article_counts` 는 `null`(모름)이다. 실서버로는 재현할 수 없어 fixture 에서 이 키를 지워 확인했다 (2026-10-10 실측).
- 재개발(F01) 매물은 목록에서 전용면적을 0, 해당 층·전체 층을 `'0'` 으로 주고, 상세에서는 전용면적 키 없이 층·전체 층을 `'-'` 로 준다. `article_info_to_listing`·`known_floor` 가 목록·상세 모두 모름(null)으로 바꾼다.
- `legalDivision/*Weekly*` 추이는 아파트(A01)만 값이 있다. 오피스텔·빌라 코드도 받지만 모두 0, 월세는 400. 구 단위 코드도, 시·도 코드도 받는다 (서울 1100000000 세 엔드포인트 200). 평당가는 원 단위. 셋 중 하나가 실패하면 그 값만 `null` 이고 429 는 `RateLimitedError` 라 삼키지 않는다.
- 단지 학교 `education/complex/school` 은 단지형 빌라를 `itemType=villa` 로 물어야 한다 (complex 로 물으면 빈 목록).
- `complex/redevelopment` 는 없는 구역 번호에도 `isSuccess: true, result: {}` 를 준다. 이름이 비면 NOT_FOUND 로 바꾼다. `redevelopmentArea/articleStats` 는 단지 매물 통계와 같은 모양이고 `tradeTypes[]`·가격 키를 서버가 거른다.
- `complex/reconstruction` 은 재건축(A04) 단지용이다. 단계 코드 01~11 은 사이트 `COMPLEX_RECONSTRUCTION_STEP` 라벨로 바꾸고, 날짜 없는 단계(아직 안 거친 단계)는 내보내지 않는다.

## 기간 조회·지역 목록·학교 엔드포인트 메모 (2026-10-10 실측)

- `complex/pyeong/realPrice/list` 는 `startDate`~`endDate` 거래를 페이지 없이 다 준다 (대단지 전세 5년 833건 한 번에). `realEstateType`·`endDate` 가 빠지면 400 이지만 유형 값은 결과에 영향이 없어 A01 을 보낸다. 빌라 단지는 거래가 있어도 빈 목록이라 `complex/villa/realPricePage`(size 100 가능, 최근 순)를 시작일까지 넘긴다.
- `complex/marketPrice/list` 는 유형 코드 없이도 같은 값을 준다. 기관마다 기준일을 키로 한 dict 들이 온다 (1년이면 기관당 51~52점).
- `legalDivision/subInfoList` 의 `legalDivisionLevelType` 은 하위 목록을 볼 지역의 단위다 (시·도 코드 + SI, 구 코드 + GUN). GU 는 400. 시·도의 하위 목록은 구가 있는 시를 `성남시 분당구` 처럼 펼쳐 주고, `성남시` 자신의 코드(4113000000)로는 빈 목록이다. 시·도 목록(`infoListByLevel`, SI)은 16곳이다 (전남광주통합특별시 포함). 세종의 시·도 하위 목록은 `세종시`(3611000000) 하나뿐이고 `세종시` 가 시·도 별칭이라, `regions` 는 하위가 시·군·구 하나뿐이면 그 아래 읍·면·동(GUN)을 준다 (2026-10-11 실측: 150곳). 그러지 않으면 `regions 세종시` 가 같은 목록을 되풀이했다.
- 주소 검색(`maps/search/address`)은 동 이름 일부에 대표 한 곳만 준다 (`송정` → 부산 해운대구 송정동 1곳, `송정동` → 15곳. `역삼`·`역삼동` 은 둘 다 1곳. `대치` 는 대치동·대치면 2곳, 2026-10-11). 그래서 `_find_address` 는 찾은 동 이름이 검색어와 다르면 동 이름 전체로 1회 더 물어 여러 곳이면 `REGION_AMBIGUOUS` 로 멈춘다. 주소 검색이 못 찾은 이름(`신흥`)은 동 자동완성으로 넘어가며, 자동완성의 첫 결과(인천 신흥동1가) 대신 검색어에 동·구·시·군·읍·면을 붙인 이름(`DIVISION_NAME_SUFFIXES`)으로 고른다. 그 이름이 여러 곳이면 이름 전체로 주소 검색을 1회 더 해 `신흥동`·`신사동` 과 같은 후보로 멈춘다 (자동완성은 신흥 2곳·totalCount 12, 주소 검색 신흥동은 14곳. 신사 2곳 ↔ 신사동 3곳).
- 법정동 자동완성은 시·도를 주지 않고 한 쪽에 다섯 곳만 준다. 그래서 `regions` 는 시·도 목록을 먼저 받아 이름(서울·서울시·서울특별시·충북 등)을 맞춰 본다.
- 법정동 자동완성은 네이버식 시·도 이름으로만 찾는다. `서울특별시 강남구`·`부산광역시 중구` 는 빈 목록이고, `서울 강남구` 는 `서울시 강남구` 를 준다. 그래서 `regions` 는 첫 단어가 시·도면 시·도 목록의 `legalDivisionName`(`서울시`)으로 바꿔 묻는다 (2026-10-10 실측). 시·도 이름은 매물 주소와 같은 `SIDO_OFFICIAL_NAMES` 로 `cityFullName` 에 맞춘다 (옛 이름 `광주`·`전남`, 네이버 줄임 이름 `전남광주시`·`전북도` 포함). 옛 이름 그대로인 `광주 광산구` 는 자동완성이 빈 목록이라 `전남광주시 광산구` 로 바꿔 묻는다 (2026-10-11). 한 단어 `광주시` 만 경기도 광주시로 본다 (`CITY_NOT_PROVINCE_NAMES`).
- 법정동·단지 자동완성의 `legalDivisionName` 은 `서울시 강남구 역삼동`·`세종시 세종시 반곡동`·`강원도 원주시` 처럼 옛·줄인 시·도 이름이라, 검색 중심 `region.address` 에 넣을 때 `normalize_address` 로 매물 주소와 같은 정식 이름으로 바꾼다. 주소 검색(`maps/search/address`)의 `fullAddress` 는 처음부터 `서울특별시 …` 다 (2026-10-11 실측).
- `education/school` 은 학교 코드로 공시 정보를 준다 (전화·홈페이지·좌표·학구도 경계는 내보내지 않는다). `education/complex/school/allocation-dongs` 는 단지·학교·itemType 으로 배정 동 묶음(`convertedBuildingNameGroups`)을 주고, 사이트처럼 묶음의 첫~끝 동으로 보여 준다. 없는 단지 번호(99999999)와 이 학교에 배정되지 않은 단지(헬리오시티 111515 ↔ B100000747)도 일부 배정처럼 `isAllBuildingAssigned: false, convertedBuildingNameGroups: []` 로 와서 구분되지 않는다. 없는 단지 번호는 `complex`·`complex/villa` 모두 `result: null` 이라, 번호로 받은 빌라 단지는 `complex/villa` 로 있는지 먼저 확인한다 (2026-10-11 실측).
- `article/tax` 는 면제되는 항목도 null 이 아니라 0 으로 준다 (85㎡ 이하 취득 농특세, 종부세 대상 아님. 헬리오시티 39·85·111·150㎡·일신동 빌라 2건, 2026-10-11 실측). 그래서 세금 합계(`_sum_manwon`)에서 일부 항목만 null 인 경우는 실제 응답에 없다.
- 재검토 후 넣지 않은 엔드포인트: `complex/asking-price`(단지 매물 목록과 같은 정보), `article/boundedArticlesCount`(검색의 `total_count` 와 같음), `search/articles`(`listing` 과 같고 중개사·본문이 섞임), `legalDivision/infoList`, `complex/villa/asking-price`(빈 결과), `complex/villa/realPriceAround`(파라미터를 찾지 못해 400).

## API 변경 시 점검

client의 action별 endpoint/docstring → request 별칭·필터 → response 봉투와 중첩 모델 → service unwrap·만원 변환 → CLI 모드별 검증 순으로 확인한다. 학교·교통·세금·선택 평형 시세는 부가 요청 경로도 따로 확인한다. 재개발은 구역 목록과 매물 목록, trend는 호가와 실거래 건수를 구분한다.
