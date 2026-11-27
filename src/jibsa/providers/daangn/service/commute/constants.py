"""출퇴근 역 기준 매물 검색(search commute)의 상수: 찾아볼 역 수·역당 매물 수·지하철 시간·도보 한도."""

from jibsa.providers.daangn.service.common.constants import LISTING_MAX_LIMIT


# 역당 매물 수 상한 (CLI --limit 최대). 100건씩 페이지를 넘겨 받는다. 역마다 같은 상한 안내(`listing_budget_notes`)를 붙여서
# 매물 목록 상한과 같아야 한다
COMMUTE_STATION_MAX_LIMIT: int = LISTING_MAX_LIMIT


# 출퇴근 검색: 매물을 찾아볼 역 수 (역마다 요청 1회). 갈 수 있는 역 목록(`commuteStations`)은 요청 1회로 전부 받아 상한이 없다
COMMUTE_MAX_STATIONS: int = 10


# 역당 매물 수 기본값. 10곳 × 5건 = 50건으로 docs/llm.md 의 '한 번에 50건 이하' 에 맞는다. 매물 목록처럼 20 이면 셸 출력을
# 잘라 보여 주는 에이전트가 뒤쪽 역을 못 본다 (2026-10-23 실측: 강남역 20분 원룸 월세 10역 186건·86,469자)
COMMUTE_STATION_DEFAULT_LIMIT: int = 5


# 당근 출퇴근 지도가 주는 지하철 시간 상한 (2026-10-11 실측: 강남역 411곳·양평역 42곳 모두 60분에서 목록이 끝났다)
COMMUTE_SERVER_MAX_MINUTES: int = 60


# 회사에서 가장 가까운 역까지 이 도보 분을 넘으면 웹 출퇴근 지도는 '근처에 지하철역이 없어요' 로 끝낸다 (useNearestStation 의 `s`)
COMMUTE_MAX_WALK_TO_STATION: int = 60
